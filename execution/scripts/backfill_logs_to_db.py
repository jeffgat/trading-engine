"""One-time backfill: parse all local log files and POST to the remote main DB.

Usage (on the droplet):
    cd /opt/orb-trader
    .venv/bin/python scripts/backfill_logs_to_db.py

Or locally if logs are present:
    cd execution
    uv run python scripts/backfill_logs_to_db.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

# Add trader source to path so we can reuse the parse functions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trader.api import parse_trade_log_line, parse_main_log_line, parse_webhook_log_line

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
DB_URL = (
    os.environ.get("MAIN_DB_URL")
    or os.environ.get("EXPERIMENTS_DB_URL")
    or "http://143.110.148.234:8100"
).rstrip("/")
BATCH_SIZE = 500


def backfill_log_type(
    log_type: str,
    base_name: str,
    max_backups: int,
    parser,
) -> None:
    """Parse all rotated + current log files and batch-POST to the DB."""
    # Check if DB already has entries for this type
    try:
        req = urllib.request.Request(
            f"{DB_URL}/api/execution-logs/{log_type}/count",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        existing = result.get("result", {}).get("count", 0)
        if existing > 0:
            print(f"  {log_type}: skipping — DB already has {existing} entries (use --force to overwrite)")
            return
    except Exception as exc:
        print(f"  {log_type}: WARNING — could not check DB count: {exc}")

    # Collect files oldest-to-newest (rotated backups first, then current)
    files: list[Path] = []
    for i in range(max_backups, 0, -1):
        p = LOG_DIR / f"{base_name}.{i}"
        if p.exists():
            files.append(p)
    base = LOG_DIR / base_name
    if base.exists():
        files.append(base)

    if not files:
        print(f"  {log_type}: no log files found")
        return

    # Parse all lines
    all_entries: list[dict] = []
    for f in files:
        for line in f.read_text(errors="replace").splitlines():
            parsed = parser(line.strip())
            if parsed is not None:
                all_entries.append(parsed)

    print(f"  {log_type}: {len(all_entries)} entries from {len(files)} files")

    if not all_entries:
        return

    # Batch POST
    sent = 0
    for i in range(0, len(all_entries), BATCH_SIZE):
        batch = all_entries[i : i + BATCH_SIZE]
        payload = json.dumps({"entries": batch}).encode()
        req = urllib.request.Request(
            f"{DB_URL}/api/execution-logs/{log_type}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        sent += len(batch)
        print(f"    sent {sent}/{len(all_entries)}")

    print(f"  {log_type}: done")


def main() -> None:
    print(f"Backfilling logs from {LOG_DIR} to {DB_URL}")
    print()

    backfill_log_type("trades", "trades.log", 10, parse_trade_log_line)
    print()
    backfill_log_type("main", "trader.log", 5, parse_main_log_line)
    print()
    backfill_log_type("webhooks", "webhooks.log", 5, parse_webhook_log_line)

    print()
    print("Backfill complete.")


if __name__ == "__main__":
    main()
