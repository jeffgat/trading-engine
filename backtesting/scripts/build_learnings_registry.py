#!/usr/bin/env python3
"""Build generated learnings briefs, indexes, and registry metadata."""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKTESTING_ROOT = REPO_ROOT / "backtesting"
LEARNINGS_ROOT = BACKTESTING_ROOT / "learnings"
ASSET_ROOT = LEARNINGS_ROOT / "asset"
REPORT_ROOT = LEARNINGS_ROOT / "reports"
RESULTS_ROOT = BACKTESTING_ROOT / "data" / "results"
BRIEF_ROOT = LEARNINGS_ROOT / "briefs"
ASSET_BRIEF_ROOT = BRIEF_ROOT / "assets"
INDEX_ROOT = LEARNINGS_ROOT / "indexes"
ASSET_INDEX_ROOT = INDEX_ROOT / "assets"
REGISTRY_PATH = LEARNINGS_ROOT / "registry" / "catalog.json"

PRIMARY_RESULT_FILES = [
    "summary.md",
    "summary.json",
    "phase_one_results.json",
    "phase_two_results.json",
    "pipeline_results.json",
    "discovery_results.json",
    "followup_results.json",
    "confirmation_results.json",
    "promotion_compare.json",
    "holdout_compare.json",
    "risk_sweep.json",
    "exact_replay_compare.json",
    "exact_replay_diff.json",
    "trace.json",
    "baseline_only.json",
    "baseline_no_go.json",
    "finalists.json",
    "selected_windows.json",
    "best_overall.json",
]


def repo_rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def link_path(from_path: Path, target: Path) -> str:
    rel_path = os.path.relpath(target, from_path.parent)
    return Path(rel_path).as_posix()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower())
    return slug.strip("_")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_asset_sections(path: Path) -> list[dict[str, str]]:
    lines = read_text(path).splitlines()
    sections: list[dict[str, str]] = []
    index = 0
    while index < len(lines):
        heading_match = re.match(r"^###\s+(.*)", lines[index])
        if not heading_match:
            index += 1
            continue

        title = heading_match.group(1).strip()
        section_lines: list[str] = []
        next_index = index + 1
        while next_index < len(lines) and not re.match(r"^###\s+", lines[next_index]):
            section_lines.append(lines[next_index])
            next_index += 1

        status = "UNSPECIFIED"
        for line in section_lines[:25]:
            status_match = re.search(r"- \*\*Status\*\*: (.+)", line)
            if status_match:
                status = status_match.group(1).strip()
                break

        sections.append(
            {
                "title": title,
                "status": status,
                "status_bucket": status_bucket(status),
            }
        )
        index = next_index
    return sections


def status_bucket(status: str) -> str:
    normalized = status.upper()
    if "NO-GO" in normalized:
        return "NO-GO"
    if "CONDITIONAL" in normalized:
        return "CONDITIONAL"
    if "SUPERSEDED" in normalized:
        return "SUPERSEDED"
    if "CORRUPT" in normalized or "INVALIDATED" in normalized:
        return "INVALIDATED_OR_CORRUPT"
    if "OPTIMIZATION COMPLETE" in normalized:
        return "OPTIMIZATION_COMPLETE"
    if "STRONG" in normalized:
        return "STRONG"
    if re.search(r"\bGO\b", normalized):
        return "GO"
    return "UNSPECIFIED"


def format_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def result_primary_files(path: Path) -> list[str]:
    files = sorted(
        rel_path.as_posix()
        for rel_path in (candidate.relative_to(path) for candidate in path.rglob("*") if candidate.is_file())
    )
    if not files:
        return []

    ranked: list[str] = []
    for priority_name in PRIMARY_RESULT_FILES:
        if priority_name in files:
            ranked.append(priority_name)

    for file_name in files:
        if file_name not in ranked:
            ranked.append(file_name)
        if len(ranked) >= 5:
            break

    return ranked[:5]


def asset_token_map(asset_symbols: list[str]) -> dict[str, str]:
    token_to_asset: dict[str, str] = {}
    for symbol in asset_symbols:
        token_to_asset[symbol.lower()] = symbol

    token_to_asset.update(
        {
            "6b": "6B",
            "mcl": "CL",
            "mgc": "GC",
            "mnq": "NQ",
            "mes": "ES",
            "mym": "YM",
        }
    )
    return token_to_asset


def asset_membership(name: str, token_to_asset: dict[str, str]) -> list[str]:
    tokens = {token for token in re.split(r"[^a-z0-9]+", name.lower()) if token}
    matches = {token_to_asset[token] for token in tokens if token in token_to_asset}
    return sorted(matches)


def report_group(path: Path, asset_symbols: list[str]) -> tuple[str, list[str]]:
    name = path.name
    stem = path.stem
    if name.startswith("council-report-") or name.startswith("council-transcript-"):
        return ("council", [])

    prefix = stem.split("_", 1)[0]
    if prefix in asset_symbols:
        return ("asset", [prefix])

    return ("cross_asset_or_other", [])


def build_catalog() -> dict:
    asset_files = sorted(ASSET_ROOT.glob("*.md"))
    asset_symbols = [path.stem for path in asset_files]
    token_to_asset = asset_token_map(asset_symbols)

    result_dirs = sorted(path for path in RESULTS_ROOT.iterdir() if path.is_dir())
    result_dir_index = {path.name: path for path in result_dirs}

    catalog: dict = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "paths": {
            "readme": "backtesting/learnings/README.md",
            "global_brief": "backtesting/learnings/briefs/GLOBAL.md",
            "strategy_memory": "backtesting/learnings/global/strategy-memory.md",
            "registry": repo_rel(REGISTRY_PATH),
        },
        "overview": {
            "asset_histories": len(asset_files),
            "report_files": len([path for path in REPORT_ROOT.iterdir() if path.is_file()]),
            "result_directories": len(result_dirs),
            "result_loose_files": len([path for path in RESULTS_ROOT.iterdir() if path.is_file()]),
        },
        "assets": {},
        "global": {
            "brief": "backtesting/learnings/briefs/GLOBAL.md",
            "strategy_memory": "backtesting/learnings/global/strategy-memory.md",
            "top_level_learnings": [
                repo_rel(path)
                for path in sorted(LEARNINGS_ROOT.glob("*.md"))
                if path.name != "README.md"
            ],
            "reports": {
                "council": [],
                "cross_asset_or_other": [],
            },
            "result_directories": [],
            "result_loose_files": [],
        },
    }

    report_membership: dict[str, list[dict]] = defaultdict(list)
    global_reports: dict[str, list[dict]] = defaultdict(list)

    for report_path in sorted(path for path in REPORT_ROOT.iterdir() if path.is_file()):
        group, direct_assets = report_group(report_path, asset_symbols)
        slug = slugify(report_path.stem)
        matched_result_dir = result_dir_index.get(slug)
        report_record = {
            "name": report_path.name,
            "path": repo_rel(report_path),
            "slug": slug,
            "mtime_utc": format_mtime(report_path),
            "matched_result_directory": repo_rel(matched_result_dir) if matched_result_dir else None,
        }
        if group == "asset":
            for asset in direct_assets:
                report_membership[asset].append(report_record)
        else:
            global_reports[group].append(report_record)

    result_membership: dict[str, list[dict]] = defaultdict(list)
    global_result_dirs: list[dict] = []

    for result_dir in result_dirs:
        assets = asset_membership(result_dir.name, token_to_asset)
        result_record = {
            "name": result_dir.name,
            "path": repo_rel(result_dir),
            "mtime_utc": format_mtime(result_dir),
            "file_count": sum(1 for path in result_dir.rglob("*") if path.is_file()),
            "primary_files": result_primary_files(result_dir),
            "assets": assets,
        }
        if assets:
            for asset in assets:
                result_membership[asset].append(result_record)
        else:
            global_result_dirs.append(result_record)

    loose_result_files = sorted(path for path in RESULTS_ROOT.iterdir() if path.is_file())
    catalog["global"]["result_loose_files"] = [
        {
            "name": path.name,
            "path": repo_rel(path),
            "mtime_utc": format_mtime(path),
        }
        for path in loose_result_files
    ]
    catalog["global"]["reports"] = global_reports
    catalog["global"]["result_directories"] = global_result_dirs

    for asset_path in asset_files:
        asset = asset_path.stem
        sections = parse_asset_sections(asset_path)
        status_counts = Counter(section["status_bucket"] for section in sections)
        catalog["assets"][asset] = {
            "brief": f"backtesting/learnings/briefs/assets/{asset}.md",
            "detail_history": repo_rel(asset_path),
            "index": f"backtesting/learnings/indexes/assets/{asset}.md",
            "strategy_sections": sections,
            "status_counts": dict(status_counts),
            "reports": report_membership.get(asset, []),
            "result_directories": result_membership.get(asset, []),
        }

    return catalog


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def render_asset_brief(asset: str, record: dict) -> str:
    detail_path = REPO_ROOT / record["detail_history"]
    index_path = REPO_ROOT / record["index"]
    global_brief_path = BRIEF_ROOT / "GLOBAL.md"
    sections = record["strategy_sections"]
    status_counts = Counter(record["status_counts"])
    rendered_sections = [section for section in sections if section["status_bucket"] != "UNSPECIFIED"][:12]
    if not rendered_sections:
        rendered_sections = sections[:12]

    lines = [
        "<!-- Generated by backtesting/scripts/build_learnings_registry.py. Do not edit directly. -->",
        f"# {asset} Brief",
        "",
        "This is the short entrypoint for agent and LLM context loading.",
        "",
        "## Read Order",
        f"1. [Global brief]({link_path(ASSET_BRIEF_ROOT / f'{asset}.md', global_brief_path)})",
        f"2. [Detailed asset history]({link_path(ASSET_BRIEF_ROOT / f'{asset}.md', detail_path)})",
        f"3. [Full {asset} index]({link_path(ASSET_BRIEF_ROOT / f'{asset}.md', index_path)})",
        "4. Open individual reports or result artifacts only when the brief or index points you there.",
        "",
        "## Coverage",
        f"- Strategy sections indexed: {len(sections)}",
        f"- Related reports indexed: {len(record['reports'])}",
        f"- Related result directories indexed: {len(record['result_directories'])}",
    ]

    if status_counts:
        status_summary = ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))
        lines.append(f"- Status mix: {status_summary}")

    lines.extend(["", "## Strategy Snapshot"])
    if not rendered_sections:
        lines.append("- No strategy sections were extracted from the detailed asset history yet.")
    else:
        for section in rendered_sections:
            lines.append(f"- `{section['title']}` -> `{section['status']}`")
        if len(sections) > len(rendered_sections):
            lines.append(
                f"- ... plus {len(sections) - len(rendered_sections)} more entries in the [full {asset} index]"
                f"({link_path(ASSET_BRIEF_ROOT / f'{asset}.md', index_path)})."
            )

    return "\n".join(lines)


def render_asset_index(asset: str, record: dict) -> str:
    detail_path = REPO_ROOT / record["detail_history"]
    brief_path = REPO_ROOT / record["brief"]
    strategy_sections = record["strategy_sections"]
    report_entries = record["reports"]
    result_entries = record["result_directories"]
    index_file = ASSET_INDEX_ROOT / f"{asset}.md"

    lines = [
        "<!-- Generated by backtesting/scripts/build_learnings_registry.py. Do not edit directly. -->",
        f"# {asset} Index",
        "",
        f"- Brief: [backtesting/learnings/briefs/assets/{asset}.md]({link_path(index_file, brief_path)})",
        f"- Detailed history: [{repo_rel(detail_path)}]({link_path(index_file, detail_path)})",
        "",
        "## Strategy Sections",
    ]

    if not strategy_sections:
        lines.append("- No strategy sections found.")
    else:
        for section in strategy_sections:
            lines.append(f"- `{section['title']}` -> `{section['status']}`")

    lines.extend(["", f"## Reports ({len(report_entries)})"])
    if not report_entries:
        lines.append("- No asset-scoped reports matched this asset yet.")
    else:
        for report in report_entries:
            report_path = REPO_ROOT / report["path"]
            line = f"- [{report['name']}]({link_path(index_file, report_path)})"
            if report["matched_result_directory"]:
                result_path = REPO_ROOT / report["matched_result_directory"]
                line += f" -> [{result_path.name}]({link_path(index_file, result_path)})"
            lines.append(line)

    lines.extend(["", f"## Result Directories ({len(result_entries)})"])
    if not result_entries:
        lines.append("- No result directories matched this asset yet.")
    else:
        for result in result_entries:
            result_path = REPO_ROOT / result["path"]
            primary = ", ".join(result["primary_files"]) if result["primary_files"] else "none"
            lines.append(
                f"- [{result['name']}]({link_path(index_file, result_path)}) "
                f"({result['file_count']} files; primary: {primary})"
            )

    return "\n".join(lines)


def render_report_index(catalog: dict) -> str:
    index_file = INDEX_ROOT / "reports.md"
    lines = [
        "<!-- Generated by backtesting/scripts/build_learnings_registry.py. Do not edit directly. -->",
        "# Report Index",
        "",
        f"- Total report files: {catalog['overview']['report_files']}",
        "",
        "## Asset Reports",
    ]

    for asset, record in sorted(catalog["assets"].items()):
        lines.append(f"- {asset}: {len(record['reports'])} reports")
        for report in record["reports"]:
            report_path = REPO_ROOT / report["path"]
            lines.append(f"  - [{report['name']}]({link_path(index_file, report_path)})")

    lines.extend(["", "## Cross-Asset and Other"])
    cross_reports = catalog["global"]["reports"]["cross_asset_or_other"]
    if not cross_reports:
        lines.append("- None")
    else:
        for report in cross_reports:
            report_path = REPO_ROOT / report["path"]
            lines.append(f"- [{report['name']}]({link_path(index_file, report_path)})")

    lines.extend(["", "## Council"])
    council_reports = catalog["global"]["reports"]["council"]
    if not council_reports:
        lines.append("- None")
    else:
        for report in council_reports:
            report_path = REPO_ROOT / report["path"]
            lines.append(f"- [{report['name']}]({link_path(index_file, report_path)})")

    return "\n".join(lines)


def render_result_index(catalog: dict) -> str:
    index_file = INDEX_ROOT / "results.md"
    lines = [
        "<!-- Generated by backtesting/scripts/build_learnings_registry.py. Do not edit directly. -->",
        "# Results Index",
        "",
        f"- Result directories: {catalog['overview']['result_directories']}",
        f"- Loose result files: {catalog['overview']['result_loose_files']}",
        "",
        "## Asset Result Directories",
    ]

    for asset, record in sorted(catalog["assets"].items()):
        lines.append(f"- {asset}: {len(record['result_directories'])} directories")
        for result in record["result_directories"]:
            result_path = REPO_ROOT / result["path"]
            primary = ", ".join(result["primary_files"]) if result["primary_files"] else "none"
            lines.append(
                f"  - [{result['name']}]({link_path(index_file, result_path)}) "
                f"({result['file_count']} files; primary: {primary})"
            )

    lines.extend(["", "## Global Result Directories"])
    global_result_dirs = catalog["global"]["result_directories"]
    if not global_result_dirs:
        lines.append("- None")
    else:
        for result in global_result_dirs:
            result_path = REPO_ROOT / result["path"]
            primary = ", ".join(result["primary_files"]) if result["primary_files"] else "none"
            lines.append(
                f"- [{result['name']}]({link_path(index_file, result_path)}) "
                f"({result['file_count']} files; primary: {primary})"
            )

    lines.extend(["", "## Loose Result Files"])
    loose_files = catalog["global"]["result_loose_files"]
    if not loose_files:
        lines.append("- None")
    else:
        for result in loose_files:
            result_path = REPO_ROOT / result["path"]
            lines.append(f"- [{result['name']}]({link_path(index_file, result_path)})")

    return "\n".join(lines)


def main() -> None:
    catalog = build_catalog()

    write_text(REGISTRY_PATH, json.dumps(catalog, indent=2))
    write_text(INDEX_ROOT / "reports.md", render_report_index(catalog))
    write_text(INDEX_ROOT / "results.md", render_result_index(catalog))

    for asset, record in sorted(catalog["assets"].items()):
        write_text(ASSET_BRIEF_ROOT / f"{asset}.md", render_asset_brief(asset, record))
        write_text(ASSET_INDEX_ROOT / f"{asset}.md", render_asset_index(asset, record))


if __name__ == "__main__":
    main()
