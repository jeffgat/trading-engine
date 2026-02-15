"""One-time backfill of experiments.db from existing JSON result files."""

import json
import sqlite3
import sys
from pathlib import Path

# Ensure the package is importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orb_backtest.experiments import DB_PATH, _get_git_hash, init_db, log_run


def backfill_db() -> None:
    results_dir = Path(__file__).resolve().parents[1] / "data" / "results"
    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}")
        return

    json_files = sorted(results_dir.glob("*.json"))
    if not json_files:
        print("No JSON files found in results directory.")
        return

    # Init DB and get existing result_file values to skip duplicates
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        existing = {
            row[0]
            for row in conn.execute("SELECT result_file FROM runs").fetchall()
        }

    # Single git hash for all historical inserts
    git_hash = _get_git_hash()

    imported = 0
    skipped_invalid = []
    skipped_duplicate = []

    for fp in json_files:
        result_id = fp.stem

        if result_id in existing:
            skipped_duplicate.append(fp.name)
            continue

        try:
            data = json.loads(fp.read_text())
        except (json.JSONDecodeError, OSError) as e:
            skipped_invalid.append((fp.name, str(e)))
            continue

        if "config" not in data or "summary" not in data:
            skipped_invalid.append((fp.name, "missing config or summary"))
            continue

        try:
            log_run(data, result_id, git_hash=git_hash)
            imported += 1
        except Exception as e:
            skipped_invalid.append((fp.name, str(e)))

    print(f"Imported {imported} results into experiments.db")
    if skipped_duplicate:
        print(f"Skipped {len(skipped_duplicate)} duplicates: {', '.join(skipped_duplicate)}")
    if skipped_invalid:
        print(f"Skipped {len(skipped_invalid)} invalid files:")
        for name, reason in skipped_invalid:
            print(f"  {name}: {reason}")


if __name__ == "__main__":
    backfill_db()
