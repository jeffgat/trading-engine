#!/usr/bin/env python3
"""Index and query local research memory for agent workflows.

Examples:
    uv run python scripts/research_memory.py index
    uv run python scripts/research_memory.py ask "Have we tested NQ Asia ORB strict stress?"
    uv run python scripts/research_memory.py retrieve "promotion packet deployability" --top-k 4
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.research_memory import (  # noqa: E402
    DEFAULT_INCLUDE_GLOBS,
    ResearchMemoryConfig,
    ResearchMemoryError,
    build_research_memory_index,
    ensure_research_memory_index,
    format_search_hits,
    search_research_memory,
)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = config_from_args(args)

    try:
        if args.command == "index":
            index = build_research_memory_index(config)
            print(
                f"Indexed {index['source_count']} source file(s) into "
                f"{index['chunk_count']} chunk(s)."
            )
            print(f"Index: {config.index_path}")
            return 0

        index = ensure_research_memory_index(config, refresh=args.refresh)
        hits = search_research_memory(args.query, config, top_k=args.top_k, index=index)
        if args.json:
            payload = {
                "query": args.query,
                "index_path": str(config.index_path),
                "hits": [hit.to_dict() for hit in hits],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(format_search_hits(args.query, hits, max_chars=args.max_chars))
        return 0
    except ResearchMemoryError as exc:
        print(json.dumps({"success": False, "error": exc.to_dict()}, indent=2), file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local research-memory retrieval")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Trading engine repo root",
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=None,
        help="Override index path (default: backtesting/.agent-memory/research-index.json)",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help="Glob to index, relative to repo root. Repeatable.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("index", help="Build or rebuild the local research-memory index")

    for command in ("ask", "retrieve"):
        subparser = subparsers.add_parser(command, help=f"{command} local research memory")
        subparser.add_argument("query", help="Research question or search query")
        subparser.add_argument("--top-k", type=int, default=6, help="Number of chunks to return")
        subparser.add_argument(
            "--refresh",
            action="store_true",
            help="Force rebuild before retrieval",
        )
        subparser.add_argument(
            "--json",
            action="store_true",
            help="Emit structured JSON instead of text",
        )
        subparser.add_argument(
            "--max-chars",
            type=int,
            default=900,
            help="Maximum text characters per hit in text output",
        )

    return parser


def config_from_args(args: argparse.Namespace) -> ResearchMemoryConfig:
    include_globs = tuple(args.include) if args.include else DEFAULT_INCLUDE_GLOBS
    return ResearchMemoryConfig(
        repo_root=args.repo_root,
        index_path=args.index_path,
        include_globs=include_globs,
    )


if __name__ == "__main__":
    raise SystemExit(main())
