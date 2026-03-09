#!/usr/bin/env python3
"""Seed missed live trades into the experiments DB.

Run after deploying the live-trades endpoint:
    python scripts/seed_missed_trades.py
"""

import json
import urllib.request

API_URL = "http://143.110.148.234:8100"

TRADES = [
    {
        "session": "NQ_NY",
        "date": "20260309",
        "direction": 1,
        "entry_price": 24530.0,
        "stop_price": 24499.32,
        "tp1_price": 24572.95,
        "tp2_price": 24637.37,
        "exit_type": "tp2",
        "tp1_hit": True,
        "exit_timestamp": "2026-03-09T15:50:00-05:00",
        "config_name": "FAST",
    },
    {
        "session": "NQ_NY",
        "date": "20260309",
        "direction": 1,
        "entry_price": 24530.0,
        "stop_price": 24499.32,
        "tp1_price": 24572.95,
        "tp2_price": 24637.37,
        "exit_type": "tp2",
        "tp1_hit": True,
        "exit_timestamp": "2026-03-09T15:50:00-05:00",
        "config_name": "SLOW",
    },
    {
        "session": "NQ_NY",
        "date": "20260309",
        "direction": 1,
        "entry_price": 24530.0,
        "stop_price": 24499.32,
        "tp1_price": 24572.95,
        "tp2_price": 24637.37,
        "exit_type": "tp2",
        "tp1_hit": True,
        "exit_timestamp": "2026-03-09T15:50:00-05:00",
        "config_name": "FAST_V2",
    },
]


def main():
    for i, trade in enumerate(TRADES, 1):
        payload = json.dumps({"trade": trade}).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/live-trades",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
            rowid = result.get("result", {}).get("rowid")
            print(f"[{i}/{len(TRADES)}] {trade['config_name']} {trade['session']} → rowid={rowid}")
        except Exception as exc:
            print(f"[{i}/{len(TRADES)}] FAILED: {exc}")


if __name__ == "__main__":
    main()
