#!/usr/bin/env python3
"""Download 1-second OHLCV data from Databento and save as CSV.

Saves raw Databento CSV format (ts_event, rtype, publisher_id, instrument_id,
open, high, low, close, volume, symbol) so convert_to_parquet.py can normalize
them to Eastern tz-naive parquet files.

Usage:
    uv run python scripts/download_1s_data.py CL YM RTY 6B
    uv run python scripts/download_1s_data.py CL --start 2020-01-01
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

SYMBOL_MAP = {
    "NQ":  "NQ.c.0",
    "MNQ": "MNQ.c.0",
    "ES":  "ES.c.0",
    "MES": "MES.c.0",
    "YM":  "YM.c.0",
    "MYM": "MYM.c.0",
    "RTY": "RTY.c.0",
    "GC":  "GC.v.0",
    "MGC": "MGC.v.0",
    "CL":  "CL.c.0",
    "MCL": "MCL.c.0",
    "6B":  "6B.c.0",
}

DATASET = "GLBX.MDP3"


def download_1s(client, symbol: str, start: str, end: str) -> None:
    db_symbol = SYMBOL_MAP[symbol]
    output_path = DATA_DIR / f"{symbol}_1s.csv"

    if output_path.exists():
        print(f"  {symbol}: {output_path.name} already exists — skipping")
        return

    print(f"  {symbol} ({db_symbol}) {start} → {end} ...", flush=True)
    t0 = time.time()

    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[db_symbol],
        stype_in="continuous",
        schema="ohlcv-1s",
        start=start,
        end=end,
    )

    data.to_csv(output_path)
    elapsed = time.time() - t0
    size_mb = output_path.stat().st_size / 1_048_576
    print(f"    Saved {output_path.name} ({size_mb:.0f} MB) [{elapsed:.0f}s]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download 1s OHLCV data from Databento")
    parser.add_argument("symbols", nargs="+", help="Symbols to download")
    parser.add_argument("--start", default="2016-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD, default: today)")
    args = parser.parse_args()

    symbols = [s.upper() for s in args.symbols]
    for s in symbols:
        if s not in SYMBOL_MAP:
            print(f"ERROR: Unknown symbol '{s}'. Supported: {', '.join(sorted(SYMBOL_MAP.keys()))}")
            sys.exit(1)

    end = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        print("ERROR: DATABENTO_API_KEY not set")
        sys.exit(1)

    try:
        import databento as db
    except ImportError:
        print("ERROR: databento not installed. Run: uv pip install databento")
        sys.exit(1)

    client = db.Historical(api_key)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading 1s data: {', '.join(symbols)}")
    print(f"Range: {args.start} to {end}")
    print(f"Output: {DATA_DIR}\n")

    total_t0 = time.time()
    for symbol in symbols:
        download_1s(client, symbol, args.start, end)

    print(f"\nDone [{time.time() - total_t0:.0f}s total]")
    print("Now run: uv run python scripts/convert_to_parquet.py")


if __name__ == "__main__":
    main()
