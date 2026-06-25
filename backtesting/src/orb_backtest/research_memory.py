"""Local research-memory retrieval for agent workflows.

This module is intentionally read-only: it retrieves source-linked context from
repo docs and learnings, while numeric truth remains in experiments/results.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


INDEX_VERSION = 1

DEFAULT_INCLUDE_GLOBS = (
    "AGENTS.md",
    "backtesting/AGENTS.md",
    "backtesting/README.md",
    "backtesting/learnings/**/*.md",
    "backtesting/learnings/registry/catalog.json",
)

DEFAULT_EXCLUDE_PARTS = (
    ".agent-memory",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "data",
    "dist",
    "node_modules",
)

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:%+-]*")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "use",
    "with",
}


class ResearchMemoryError(Exception):
    """Structured retrieval error that agents can recover from."""

    def __init__(self, code: str, reason: str, fix: str):
        self.code = code
        self.reason = reason
        self.fix = fix
        super().__init__(reason)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason, "fix": self.fix}


@dataclass(frozen=True)
class ResearchMemoryConfig:
    """Serializable config for local research-memory indexing."""

    repo_root: Path
    index_path: Path | None = None
    include_globs: tuple[str, ...] = DEFAULT_INCLUDE_GLOBS
    exclude_parts: tuple[str, ...] = DEFAULT_EXCLUDE_PARTS
    chunk_max_chars: int = 2400
    chunk_overlap_lines: int = 3

    def __post_init__(self) -> None:
        repo_root = Path(self.repo_root).expanduser().resolve()
        object.__setattr__(self, "repo_root", repo_root)
        if self.index_path is None:
            index_path = repo_root / "backtesting" / ".agent-memory" / "research-index.json"
        else:
            index_path = Path(self.index_path).expanduser()
            if not index_path.is_absolute():
                index_path = repo_root / index_path
        object.__setattr__(self, "index_path", index_path.resolve())

    def with_overrides(self, **kwargs: Any) -> "ResearchMemoryConfig":
        return replace(self, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["repo_root"] = str(self.repo_root)
        data["index_path"] = str(self.index_path)
        data["include_globs"] = list(self.include_globs)
        data["exclude_parts"] = list(self.exclude_parts)
        return data


@dataclass(frozen=True)
class DocumentChunk:
    """One source-linked retrieval unit."""

    chunk_id: str
    source_path: str
    heading: str
    start_line: int
    end_line: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SearchHit:
    """A scored retrieval result."""

    score: float
    chunk: DocumentChunk

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "chunk": self.chunk.to_dict()}


def default_config(repo_root: str | Path) -> ResearchMemoryConfig:
    return ResearchMemoryConfig(repo_root=Path(repo_root))


def discover_source_paths(config: ResearchMemoryConfig) -> list[Path]:
    """Return source files that should be indexed."""

    paths: dict[Path, None] = {}
    for pattern in config.include_globs:
        for path in config.repo_root.glob(pattern):
            if path.is_file() and not _is_excluded(path, config):
                paths[path.resolve()] = None
    return sorted(paths.keys())


def build_research_memory_index(config: ResearchMemoryConfig) -> dict[str, Any]:
    """Build and persist a local TF-IDF retrieval index."""

    source_paths = discover_source_paths(config)
    if not source_paths:
        raise ResearchMemoryError(
            code="RESEARCH_MEMORY_NO_SOURCES",
            reason=f"No research-memory source files found under {config.repo_root}",
            fix="Check repo_root and include_globs, then rerun the index command.",
        )

    source_files: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    document_frequency: Counter[str] = Counter()

    for path in source_paths:
        source_files.append(_source_record(path, config.repo_root))
        for chunk in chunk_source_file(path, config):
            term_counts = Counter(tokenize(f"{chunk.heading}\n{chunk.text}"))
            if not term_counts:
                continue
            record = chunk.to_dict()
            record["term_counts"] = dict(term_counts)
            chunk_records.append(record)
            document_frequency.update(term_counts.keys())

    if not chunk_records:
        raise ResearchMemoryError(
            code="RESEARCH_MEMORY_NO_CHUNKS",
            reason="Source files were found, but no searchable chunks were created.",
            fix="Check that source files contain readable markdown or text.",
        )

    chunk_count = len(chunk_records)
    idf = {
        term: math.log((chunk_count + 1) / (frequency + 1)) + 1.0
        for term, frequency in sorted(document_frequency.items())
    }

    for record in chunk_records:
        record["vector_norm"] = _weighted_norm(record["term_counts"], idf)

    built_at = datetime.now(timezone.utc)
    index = {
        "version": INDEX_VERSION,
        "built_at": built_at.isoformat(),
        "built_at_epoch": built_at.timestamp(),
        "config": config.to_dict(),
        "source_count": len(source_files),
        "chunk_count": chunk_count,
        "source_files": source_files,
        "idf": idf,
        "chunks": chunk_records,
    }

    config.index_path.parent.mkdir(parents=True, exist_ok=True)
    config.index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return index


def load_research_memory_index(config: ResearchMemoryConfig) -> dict[str, Any]:
    """Load a persisted research-memory index."""

    if not config.index_path.exists():
        raise ResearchMemoryError(
            code="RESEARCH_MEMORY_INDEX_MISSING",
            reason=f"Research-memory index not found at {config.index_path}",
            fix="Run: uv run python scripts/research_memory.py index",
        )
    index = json.loads(config.index_path.read_text())
    if index.get("version") != INDEX_VERSION:
        raise ResearchMemoryError(
            code="RESEARCH_MEMORY_INDEX_VERSION",
            reason=f"Unsupported research-memory index version: {index.get('version')}",
            fix="Rebuild the index with: uv run python scripts/research_memory.py index",
        )
    return index


def index_needs_rebuild(config: ResearchMemoryConfig, index: dict[str, Any]) -> bool:
    """Return True when sources changed since the index was built."""

    indexed_paths = {record["path"] for record in index.get("source_files", [])}
    current_paths = {_relative_path(path, config.repo_root) for path in discover_source_paths(config)}
    if indexed_paths != current_paths:
        return True

    built_at_epoch = float(index.get("built_at_epoch", 0.0))
    for path in discover_source_paths(config):
        if path.stat().st_mtime > built_at_epoch:
            return True
    return False


def ensure_research_memory_index(
    config: ResearchMemoryConfig,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Load the index, rebuilding when missing, stale, or explicitly requested."""

    if refresh or not config.index_path.exists():
        return build_research_memory_index(config)

    index = load_research_memory_index(config)
    if index_needs_rebuild(config, index):
        return build_research_memory_index(config)
    return index


def search_research_memory(
    query: str,
    config: ResearchMemoryConfig,
    *,
    top_k: int = 6,
    index: dict[str, Any] | None = None,
) -> list[SearchHit]:
    """Retrieve source-linked chunks relevant to a query."""

    if top_k <= 0:
        raise ResearchMemoryError(
            code="RESEARCH_MEMORY_INVALID_TOP_K",
            reason=f"top_k must be positive, got {top_k}",
            fix="Pass --top-k with a value greater than zero.",
        )

    index = index or load_research_memory_index(config)
    idf = index.get("idf", {})
    query_counts = Counter(tokenize(query))
    if not query_counts:
        raise ResearchMemoryError(
            code="RESEARCH_MEMORY_EMPTY_QUERY",
            reason="The query did not contain searchable terms.",
            fix="Ask a concrete research question, for example: strict stress NQ ORB.",
        )

    query_norm = _weighted_norm(query_counts, idf)
    if query_norm == 0.0:
        return []

    hits: list[SearchHit] = []
    query_lc = query.lower().strip()
    for record in index.get("chunks", []):
        term_counts = record.get("term_counts", {})
        chunk_norm = float(record.get("vector_norm", 0.0))
        if chunk_norm == 0.0:
            continue

        score = _cosine_score(query_counts, term_counts, idf, query_norm, chunk_norm)
        score += _source_boost(query_lc, query_counts, record)
        if score <= 0.0:
            continue

        chunk = DocumentChunk(
            chunk_id=record["chunk_id"],
            source_path=record["source_path"],
            heading=record["heading"],
            start_line=int(record["start_line"]),
            end_line=int(record["end_line"]),
            text=record["text"],
        )
        hits.append(SearchHit(score=score, chunk=chunk))

    hits.sort(key=lambda hit: (-hit.score, hit.chunk.source_path, hit.chunk.start_line))
    return hits[:top_k]


def chunk_source_file(path: Path, config: ResearchMemoryConfig) -> list[DocumentChunk]:
    """Split a source file into heading-aware chunks."""

    text = path.read_text(errors="replace")
    lines = text.splitlines()
    if not lines:
        return []

    if path.suffix.lower() == ".json":
        return _chunk_line_window(path, lines, config, heading=path.name)
    return _chunk_markdown(path, lines, config)


def tokenize(text: str) -> list[str]:
    """Tokenize text for deterministic local retrieval."""

    tokens: list[str] = []
    for raw in TOKEN_RE.findall(text):
        token = raw.lower().strip("._-/:+%")
        if len(token) < 2 or token in STOP_WORDS:
            continue
        tokens.append(token)
    return tokens


def format_search_hits(query: str, hits: list[SearchHit], *, max_chars: int = 900) -> str:
    """Format retrieval hits for CLI and agent prompts."""

    if not hits:
        return f"No research-memory hits found for: {query}"

    lines = [
        f"Research memory hits for: {query}",
        "",
        "Use these as source context. Query experiments/results for numeric truth.",
        "",
    ]
    for idx, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        lines.append(
            f"{idx}. score={hit.score:.3f} {chunk.source_path}:{chunk.start_line} "
            f"[{chunk.heading}]"
        )
        lines.append(_trim_text(chunk.text, max_chars=max_chars))
        lines.append("")
    return "\n".join(lines).rstrip()


def _chunk_markdown(path: Path, lines: list[str], config: ResearchMemoryConfig) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    current_lines: list[str] = []
    current_start = 1
    current_heading = path.name

    for line_no, line in enumerate(lines, start=1):
        heading_match = HEADING_RE.match(line)
        if heading_match and current_lines:
            chunks.extend(
                _split_chunk(path, current_heading, current_start, current_lines, config)
            )
            current_lines = []
            current_start = line_no

        if heading_match:
            current_heading = heading_match.group(2).strip()
        current_lines.append(line)

    if current_lines:
        chunks.extend(_split_chunk(path, current_heading, current_start, current_lines, config))

    return chunks


def _chunk_line_window(
    path: Path,
    lines: list[str],
    config: ResearchMemoryConfig,
    *,
    heading: str,
) -> list[DocumentChunk]:
    return _split_chunk(path, heading, 1, lines, config)


def _split_chunk(
    path: Path,
    heading: str,
    start_line: int,
    lines: list[str],
    config: ResearchMemoryConfig,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    start_idx = 0

    while start_idx < len(lines):
        end_idx = start_idx
        char_count = 0
        while end_idx < len(lines):
            next_len = len(lines[end_idx]) + 1
            if end_idx > start_idx and char_count + next_len > config.chunk_max_chars:
                break
            char_count += next_len
            end_idx += 1

        chunk_lines = lines[start_idx:end_idx]
        chunk_text = "\n".join(chunk_lines).strip()
        if chunk_text and _has_searchable_body(chunk_text):
            chunk_start_line = start_line + start_idx
            chunk_end_line = start_line + end_idx - 1
            chunk_id = _chunk_id(path, chunk_start_line, chunk_end_line, chunk_text)
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    source_path=_relative_path(path, config.repo_root),
                    heading=heading,
                    start_line=chunk_start_line,
                    end_line=chunk_end_line,
                    text=chunk_text,
                )
            )

        if end_idx >= len(lines):
            break
        start_idx = max(end_idx - config.chunk_overlap_lines, start_idx + 1)

    return chunks


def _cosine_score(
    query_counts: Counter[str],
    term_counts: dict[str, int],
    idf: dict[str, float],
    query_norm: float,
    chunk_norm: float,
) -> float:
    dot = 0.0
    for term, query_count in query_counts.items():
        chunk_count = term_counts.get(term, 0)
        if not chunk_count:
            continue
        weight = float(idf.get(term, 1.0))
        dot += (query_count * weight) * (chunk_count * weight)
    return dot / (query_norm * chunk_norm)


def _weighted_norm(term_counts: Counter[str] | dict[str, int], idf: dict[str, float]) -> float:
    total = 0.0
    for term, count in term_counts.items():
        weight = count * float(idf.get(term, 1.0))
        total += weight * weight
    return math.sqrt(total)


def _source_boost(query_lc: str, query_counts: Counter[str], record: dict[str, Any]) -> float:
    text_lc = str(record.get("text", "")).lower()
    heading_lc = str(record.get("heading", "")).lower()
    source_lc = str(record.get("source_path", "")).lower()
    source_terms = set(re.findall(r"[a-z0-9]+", source_lc))

    boost = 0.0
    if query_lc and query_lc in text_lc:
        boost += 0.12
    for term in query_counts:
        if term in heading_lc:
            boost += 0.03
        if term in source_terms:
            boost += 0.06
        elif term in source_lc:
            boost += 0.01
    return min(boost, 0.20)


def _source_record(path: Path, repo_root: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": _relative_path(path, repo_root),
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "sha1": _sha1(path),
    }


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _chunk_id(path: Path, start_line: int, end_line: int, text: str) -> str:
    digest = hashlib.sha1(f"{path}:{start_line}:{end_line}:{text}".encode()).hexdigest()
    return digest[:16]


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_excluded(path: Path, config: ResearchMemoryConfig) -> bool:
    return any(part in config.exclude_parts for part in path.parts)


def _has_searchable_body(text: str) -> bool:
    return any(line.strip() and not HEADING_RE.match(line) for line in text.splitlines())


def _trim_text(text: str, *, max_chars: int) -> str:
    compact = "\n".join(line.rstrip() for line in text.strip().splitlines())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."
