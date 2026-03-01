"""Sync local experiments.db to the shared remote API.

Reads all rows from the local runs and optimizations tables, then POSTs
them to the remote /api/sync/import endpoint. Sends one row at a time
because trades_json + equity_json can be several MB per row.

Idempotent — safe to run multiple times (uses INSERT OR REPLACE on
result_file / result_id).

Usage:
    uv run python scripts/sync_to_shared.py
    uv run python scripts/sync_to_shared.py --url http://143.110.148.234:8100
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Resolve the local DB path (same logic as experiments.py)
LOCAL_DB = Path(
    os.environ.get("EXPERIMENTS_DB_PATH")
    or str(Path(__file__).resolve().parents[1] / "data" / "results" / "experiments.db")
)

DEFAULT_URL = "http://143.110.148.234:8100"


def read_all_rows(db_path: Path, table: str, exclude_cols: set[str] | None = None) -> list[dict]:
    """Read all rows from a table, excluding specified columns."""
    exclude = exclude_cols or set()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()

    result = []
    for row in rows:
        d = {k: row[k] for k in row.keys() if k not in exclude}
        result.append(d)

    return result


def post_import(api_url: str, runs: list[dict], optimizations: list[dict]) -> dict:
    """POST runs/optimizations to the sync/import endpoint."""
    url = f"{api_url}/api/sync/import"
    payload = json.dumps({"runs": runs, "optimizations": optimizations}).encode()
    headers = {"Content-Type": "application/json"}

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main():
    parser = argparse.ArgumentParser(description="Sync local experiments DB to shared remote API")
    parser.add_argument("--url", default=os.environ.get("EXPERIMENTS_DB_URL", DEFAULT_URL),
                        help="Remote API URL")
    parser.add_argument("--runs-only", action="store_true",
                        help="Only sync runs table")
    parser.add_argument("--opts-only", action="store_true",
                        help="Only sync optimizations table")
    args = parser.parse_args()

    api_url = args.url.rstrip("/")

    if not LOCAL_DB.exists():
        print(f"Local DB not found: {LOCAL_DB}")
        sys.exit(1)

    print(f"Local DB: {LOCAL_DB}")
    print(f"Remote API: {api_url}")
    print()

    # Read local data
    runs = []
    optimizations = []

    if not args.opts_only:
        runs = read_all_rows(LOCAL_DB, "runs", exclude_cols={"id"})
        print(f"Local runs: {len(runs)}")

    if not args.runs_only:
        optimizations = read_all_rows(LOCAL_DB, "optimizations", exclude_cols={"id"})
        print(f"Local optimizations: {len(optimizations)}")

    if not runs and not optimizations:
        print("Nothing to sync.")
        return

    print()

    # Send runs one at a time (rows can be several MB due to trades_json/equity_json)
    total_runs = len(runs)
    failed_runs = 0
    for i, row in enumerate(runs):
        name = row.get("experiment_name", row.get("result_file", "?"))
        print(f"\r  Runs: {i + 1}/{total_runs} — {name[:60]}", end="", flush=True)

        try:
            post_import(api_url, [row], [])
        except Exception as e:
            failed_runs += 1
            print(f"\n    FAILED: {e}")

    if total_runs:
        print(f"\r  Runs: {total_runs}/{total_runs} — done!{' ' * 40}")

    # Send optimizations one at a time
    total_opts = len(optimizations)
    failed_opts = 0
    for i, row in enumerate(optimizations):
        name = row.get("result_id", "?")
        print(f"\r  Opts: {i + 1}/{total_opts} — {name[:60]}", end="", flush=True)

        try:
            post_import(api_url, [], [row])
        except Exception as e:
            failed_opts += 1
            print(f"\n    FAILED: {e}")

    if total_opts:
        print(f"\r  Opts: {total_opts}/{total_opts} — done!{' ' * 40}")

    print()
    imported_runs = total_runs - failed_runs
    imported_opts = total_opts - failed_opts
    print(f"Done! Imported {imported_runs}/{total_runs} runs, {imported_opts}/{total_opts} optimizations.")
    if failed_runs or failed_opts:
        print(f"  ({failed_runs + failed_opts} failures)")


if __name__ == "__main__":
    main()
