#!/usr/bin/env python3
"""Seed execution dashboard default backtests into the local main DB."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

# This script is for the local SQLite DB used by start-dev.sh. Set this before
# importing orb_backtest.experiments so it does not switch to the remote client.
os.environ.setdefault("MAIN_DB_URL", "")
os.environ.setdefault("EXPERIMENTS_DB_URL", "")

from orb_backtest.experiments import get_backtest_result, log_run  # noqa: E402


DEFAULT_BACKTESTS = [
    {
        "id": "bt-exec-exact-alpha-v1-a-last-5y-2021-03-25-to-2026-b56228",
        "remote_url": "https://143.110.148.234.nip.io/bt-api/backtests/bt-exec-exact-alpha-v1-a-last-5y-2021-03-25-to-2026-b56228",
        "path": REPO_ROOT
        / "backtesting"
        / "data"
        / "results"
        / "alpha_v1_ath_refresh_20260608"
        / "ALPHA_V1-A_raw_result.json",
    },
]


def load_remote_result(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode())
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None

    if payload.get("success") and isinstance(payload.get("result"), dict):
        return payload["result"]
    return None


def load_result(item: dict) -> dict:
    remote = load_remote_result(item["remote_url"])
    if remote is not None:
        return remote

    path = item["path"]
    if not path.exists():
        raise FileNotFoundError(f"missing default backtest source: {path}")
    return json.loads(path.read_text())


def main() -> int:
    seeded = 0
    for item in DEFAULT_BACKTESTS:
        result_id = item["id"]
        if get_backtest_result(result_id) is not None:
            continue

        try:
            result = load_result(item)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

        log_run(result, result_id)
        seeded += 1

    if seeded:
        print(f"Seeded {seeded} execution default backtest(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
