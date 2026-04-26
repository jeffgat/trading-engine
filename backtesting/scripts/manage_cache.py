"""Inspect and prune generated backtesting cache files.

Examples
--------
Report current cache usage:
    python scripts/manage_cache.py report

Dry-run prune of files older than 7 days:
    python scripts/manage_cache.py prune --older-than-days 7

Delete only old large ORB signal caches:
    python scripts/manage_cache.py prune --prefix sigcache --older-than-days 7 --min-size-gb 0.5 --yes
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time


CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


@dataclass(frozen=True)
class CacheFile:
    path: Path
    size_bytes: int
    mtime: float
    prefix: str

    @property
    def age_days(self) -> float:
        return (time.time() - self.mtime) / 86400.0


def human_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def detect_prefix(path: Path) -> str:
    name = path.name
    if name.startswith("sigcache_"):
        return "sigcache"
    if name.startswith("vwap_sigcache_"):
        return "vwap_sigcache"
    if name.startswith("gapfill_sigcache_"):
        return "gapfill_sigcache"
    return "other"


def list_cache_files(cache_dir: Path) -> list[CacheFile]:
    if not cache_dir.exists():
        return []

    files: list[CacheFile] = []
    for path in cache_dir.glob("*.pkl"):
        stat = path.stat()
        files.append(
            CacheFile(
                path=path,
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
                prefix=detect_prefix(path),
            )
        )
    return files


def print_report(files: list[CacheFile], top_n: int) -> None:
    total_bytes = sum(f.size_bytes for f in files)
    print(f"Cache directory: {CACHE_DIR}")
    print(f"Files: {len(files)}")
    print(f"Total size: {human_bytes(total_bytes)}")

    if not files:
        return

    print("\nBy prefix:")
    by_prefix: dict[str, list[CacheFile]] = defaultdict(list)
    for file in files:
        by_prefix[file.prefix].append(file)

    for prefix, grouped in sorted(by_prefix.items(), key=lambda item: sum(f.size_bytes for f in item[1]), reverse=True):
        size = sum(f.size_bytes for f in grouped)
        print(f"  {prefix:16} {len(grouped):4d} files  {human_bytes(size):>10}")

    print("\nBy age:")
    age_buckets = [
        ("0-3d", 0, 3),
        ("4-7d", 4, 7),
        ("8-14d", 8, 14),
        ("15-30d", 15, 30),
        ("31d+", 31, float("inf")),
    ]
    now = time.time()
    for label, min_days, max_days in age_buckets:
        grouped = [
            f for f in files
            if min_days <= (now - f.mtime) / 86400.0 <= max_days
        ]
        size = sum(f.size_bytes for f in grouped)
        print(f"  {label:16} {len(grouped):4d} files  {human_bytes(size):>10}")

    print(f"\nTop {min(top_n, len(files))} largest:")
    for file in sorted(files, key=lambda f: f.size_bytes, reverse=True)[:top_n]:
        stamp = datetime.fromtimestamp(file.mtime).strftime("%Y-%m-%d %H:%M")
        print(
            f"  {human_bytes(file.size_bytes):>10}  {stamp}  "
            f"{file.prefix:16} {file.path.name}"
        )


def select_files(
    files: list[CacheFile],
    *,
    prefixes: set[str] | None,
    older_than_days: float | None,
    min_size_gb: float | None,
) -> list[CacheFile]:
    selected: list[CacheFile] = []
    min_size_bytes = None if min_size_gb is None else int(min_size_gb * 1024 ** 3)

    for file in files:
        if prefixes and file.prefix not in prefixes:
            continue
        if older_than_days is not None and file.age_days < older_than_days:
            continue
        if min_size_bytes is not None and file.size_bytes < min_size_bytes:
            continue
        selected.append(file)

    return sorted(selected, key=lambda f: (f.mtime, -f.size_bytes))


def print_selection(files: list[CacheFile], top_n: int) -> None:
    total_bytes = sum(f.size_bytes for f in files)
    print(f"Matched files: {len(files)}")
    print(f"Matched size: {human_bytes(total_bytes)}")
    if not files:
        return

    print(f"\nFirst {min(top_n, len(files))} matches:")
    for file in files[:top_n]:
        stamp = datetime.fromtimestamp(file.mtime).strftime("%Y-%m-%d %H:%M")
        print(
            f"  {human_bytes(file.size_bytes):>10}  {stamp}  "
            f"{file.prefix:16} {file.path.name}"
        )


def prune(files: list[CacheFile], confirm: bool) -> None:
    if not files:
        print("\nNothing matched; nothing to delete.")
        return

    if not confirm:
        print("\nDry run only. Re-run with --yes to delete these files.")
        return

    deleted_bytes = 0
    for file in files:
        file.path.unlink(missing_ok=True)
        deleted_bytes += file.size_bytes

    print(f"\nDeleted {len(files)} files and freed {human_bytes(deleted_bytes)}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=False)

    report = subparsers.add_parser("report", help="Show cache usage summary.")
    report.add_argument("--top", type=int, default=20, help="Number of largest files to show.")

    prune_parser = subparsers.add_parser("prune", help="Dry-run or delete matching cache files.")
    prune_parser.add_argument(
        "--prefix",
        action="append",
        choices=["sigcache", "vwap_sigcache", "gapfill_sigcache", "other"],
        help="Limit pruning to one or more cache families. Repeatable.",
    )
    prune_parser.add_argument(
        "--older-than-days",
        type=float,
        help="Match files at least this many days old.",
    )
    prune_parser.add_argument(
        "--min-size-gb",
        type=float,
        help="Match files at least this large.",
    )
    prune_parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="How many matches to preview.",
    )
    prune_parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete matched files.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "report"

    files = list_cache_files(CACHE_DIR)

    if command == "report":
        print_report(files, top_n=args.top)
        return

    if command == "prune":
        if args.older_than_days is None and args.min_size_gb is None and not args.prefix:
            parser.error("prune requires at least one filter: --older-than-days, --min-size-gb, or --prefix")

        selected = select_files(
            files,
            prefixes=set(args.prefix) if args.prefix else None,
            older_than_days=args.older_than_days,
            min_size_gb=args.min_size_gb,
        )
        print_selection(selected, top_n=args.top)
        prune(selected, confirm=args.yes)
        return

    parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
