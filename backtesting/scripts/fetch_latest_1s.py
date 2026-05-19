#!/usr/bin/env python3
"""Fetch latest 1s data from Databento and append to existing parquet files.

Reads the current end date from each {SYMBOL}_1s.parquet, downloads the gap
from Databento, deduplicates, validates, and writes the merged file back.

Usage:
    python scripts/fetch_latest_1s.py NQ ES GC
    python scripts/fetch_latest_1s.py NQ ES GC --dry-run   # show what would be fetched
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from _env import load_backtesting_env

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

SYMBOL_MAP = {
    "NQ": "NQ.c.0",
    "ES": "ES.c.0",
    "GC": "GC.v.0",
    "SI": "SI.v.0",
    "YM": "YM.c.0",
    "RTY": "RTY.c.0",
}

DATASET = "GLBX.MDP3"


def get_current_end(symbol: str) -> pd.Timestamp:
    """Return the last timestamp in the existing 1s parquet."""
    path = DATA_DIR / f"{symbol}_1s.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    df = pd.read_parquet(path, columns=["close"])  # minimal read for index
    return df.index[-1]


def download_1s(client, symbol: str, start: str, end: str) -> pd.DataFrame:
    """Download 1s OHLCV from Databento."""
    db_symbol = SYMBOL_MAP[symbol]
    print(f"  Downloading {symbol} ({db_symbol}) 1s data: {start} → {end}")
    t0 = time.time()

    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[db_symbol],
        stype_in="continuous",
        schema="ohlcv-1s",
        start=start,
        end=end,
    )
    df = data.to_df()
    elapsed = time.time() - t0
    print(f"    Got {len(df):,} bars [{elapsed:.1f}s]")

    if df.empty:
        return df

    # Convert to Eastern, strip tz
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").tz_localize(None)
    else:
        df.index = df.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)

    # Normalize columns
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        for target in ["open", "high", "low", "close", "volume"]:
            if target in cl:
                col_map[c] = target
                break
    if col_map:
        df = df.rename(columns=col_map)

    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.index.name = "datetime"
    return df


def validate_new_data(df_new: pd.DataFrame, symbol: str) -> list[str]:
    """Run basic sanity checks on newly downloaded data. Returns list of warnings."""
    warnings = []

    if df_new.empty:
        warnings.append("No new data returned")
        return warnings

    # Check for NaN in OHLC
    nan_counts = df_new[["open", "high", "low", "close"]].isna().sum()
    if nan_counts.any():
        warnings.append(f"NaN values in OHLC: {nan_counts.to_dict()}")

    # Check OHLC consistency: high >= low, high >= open, high >= close, etc.
    bad_hl = (df_new["high"] < df_new["low"]).sum()
    if bad_hl > 0:
        warnings.append(f"{bad_hl} bars where high < low")

    bad_ho = (df_new["high"] < df_new["open"]).sum()
    if bad_ho > 0:
        warnings.append(f"{bad_ho} bars where high < open")

    bad_lc = (df_new["low"] > df_new["close"]).sum()
    if bad_lc > 0:
        warnings.append(f"{bad_lc} bars where low > close")

    # Check for negative prices
    neg = (df_new[["open", "high", "low", "close"]] <= 0).any().any()
    if neg:
        warnings.append("Negative or zero prices detected")

    # Check for duplicate index
    dupes = df_new.index.duplicated().sum()
    if dupes > 0:
        warnings.append(f"{dupes} duplicate timestamps")

    return warnings


def process_symbol(client, symbol: str, end_date: str, *, dry_run: bool = False) -> bool:
    """Fetch and append new 1s data for a single symbol. Returns True on success."""
    path = DATA_DIR / f"{symbol}_1s.parquet"

    current_end = get_current_end(symbol)
    print(f"\n{symbol}: current data ends at {current_end}")

    # Start fetching from the next second after current end
    fetch_start = (current_end + pd.Timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")
    # Databento needs UTC, but our timestamps are Eastern
    # Convert to a date string that gives us overlap safety
    fetch_start_date = (current_end + pd.Timedelta(days=0)).strftime("%Y-%m-%d")

    print(f"  Will fetch from {fetch_start_date} to {end_date}")

    if dry_run:
        print("  [DRY RUN] Skipping download")
        return True

    # Download new data
    df_new = download_1s(client, symbol, fetch_start_date, end_date)

    if df_new.empty:
        print(f"  No new data for {symbol}")
        return True

    # Validate
    warnings = validate_new_data(df_new, symbol)
    if warnings:
        for w in warnings:
            print(f"    WARNING: {w}")

    # Load existing data
    print(f"  Loading existing {path.name}...")
    t0 = time.time()
    df_existing = pd.read_parquet(path)
    print(f"    {len(df_existing):,} existing bars [{time.time() - t0:.1f}s]")

    # Filter new data to only include rows after current end
    df_new = df_new[df_new.index > current_end]
    print(f"    {len(df_new):,} genuinely new bars after dedup")

    if df_new.empty:
        print(f"  No new bars after deduplication for {symbol}")
        return True

    # Verify schema match
    if list(df_existing.columns) != list(df_new.columns):
        print(f"  ERROR: Column mismatch! existing={list(df_existing.columns)} new={list(df_new.columns)}")
        return False

    # Verify dtype match
    for col in df_existing.columns:
        if df_existing[col].dtype != df_new[col].dtype:
            print(f"    Casting {col}: {df_new[col].dtype} → {df_existing[col].dtype}")
            df_new[col] = df_new[col].astype(df_existing[col].dtype)

    # Concatenate
    df_merged = pd.concat([df_existing, df_new])
    df_merged = df_merged[~df_merged.index.duplicated(keep="first")]
    df_merged = df_merged.sort_index()

    print(f"  Merged: {len(df_existing):,} + {len(df_new):,} = {len(df_merged):,} bars")
    print(f"  New range: {df_merged.index[0]} → {df_merged.index[-1]}")

    # Write back
    print(f"  Writing {path.name}...")
    t0 = time.time()
    df_merged.to_parquet(path)
    elapsed = time.time() - t0
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"    Done [{elapsed:.1f}s, {size_mb:.0f} MB]")

    return True


def main():
    parser = argparse.ArgumentParser(description="Fetch latest 1s data from Databento")
    parser.add_argument("symbols", nargs="+", help="Symbols to update (e.g., NQ ES GC)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched without downloading")
    parser.add_argument("--end", default=None, help="End date (default: today)")
    args = parser.parse_args()

    symbols = [s.upper() for s in args.symbols]
    for s in symbols:
        if s not in SYMBOL_MAP:
            print(f"ERROR: Unsupported symbol '{s}'. Supported: {list(SYMBOL_MAP.keys())}")
            sys.exit(1)

    end_date = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        import databento as db
    except ImportError:
        print("ERROR: databento not installed. Run: uv pip install databento")
        sys.exit(1)

    load_backtesting_env()
    api_key = os.environ.get("DATABENTO_API_KEY")
    if not api_key:
        print("ERROR: DATABENTO_API_KEY not set. Add it to backtesting/.env.")
        sys.exit(1)

    client = db.Historical(api_key)

    print(f"Fetching 1s data up to {end_date}")
    print(f"Symbols: {', '.join(symbols)}")

    t_total = time.time()
    results = []
    for symbol in symbols:
        ok = process_symbol(client, symbol, end_date, dry_run=args.dry_run)
        results.append((symbol, ok))

    print(f"\n{'='*50}")
    print(f"Complete [{time.time() - t_total:.1f}s]")
    for sym, ok in results:
        status = "OK" if ok else "FAILED"
        print(f"  {sym}: {status}")

    if not all(ok for _, ok in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
