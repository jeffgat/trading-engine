#!/usr/bin/env python3
"""Resample 1-second parquet files to 1-minute and 5-minute parquet files.

Matches the exact same aggregation and forward-fill logic used by download_data.py
so that resampled data is identical to pulling higher timeframes directly from Databento.

Usage:
    python scripts/resample_1s.py              # Process all *_1s.parquet files
    python scripts/resample_1s.py NQ ES        # Process specific symbols
    python scripts/resample_1s.py --validate   # Resample NQ and compare against existing 1m/5m
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

FFILL_LIMITS = {"1min": 300, "5min": 60}


def resample_ohlcv(df_1s: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Resample 1s OHLCV to a higher timeframe with forward-fill for gaps."""
    df = df_1s.resample(freq).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })

    limit = FFILL_LIMITS[freq]
    df["volume"] = df["volume"].fillna(0).astype(int)
    df["close"] = df["close"].ffill(limit=limit)
    df["open"] = df["open"].fillna(df["close"])
    df["high"] = df["high"].fillna(df["close"])
    df["low"] = df["low"].fillna(df["close"])
    df = df.dropna(subset=["open"])
    df.index.name = "datetime"
    return df


def process_symbol(symbol: str, *, validate: bool = False) -> None:
    src = DATA_DIR / f"{symbol}_1s.parquet"
    if not src.exists():
        print(f"  SKIP {symbol}: {src.name} not found")
        return

    print(f"  Loading {src.name}...")
    t0 = time.time()
    df_1s = pd.read_parquet(src)
    print(f"    {len(df_1s):,} 1s bars loaded [{time.time() - t0:.1f}s]")

    for freq, suffix in [("1min", "1m"), ("5min", "5m")]:
        t0 = time.time()
        df = resample_ohlcv(df_1s, freq)
        elapsed = time.time() - t0

        out = DATA_DIR / f"{symbol}_{suffix}.parquet"
        existing = out.exists()

        if validate and existing:
            df_existing = pd.read_parquet(out)
            # Compare on overlapping index
            common = df.index.intersection(df_existing.index)
            diff = (df.loc[common] - df_existing.loc[common]).abs()
            max_diff = diff[["open", "high", "low", "close"]].max().max()
            print(f"    {suffix}: {len(df):,} bars [{elapsed:.1f}s] "
                  f"| VALIDATE vs existing: {len(common):,} common bars, max price diff = {max_diff}")
            if max_diff > 1e-6:
                # Show first few diffs
                mask = diff[["open", "high", "low", "close"]].max(axis=1) > 1e-6
                print(f"    WARNING: {mask.sum()} bars differ!")
                print(diff[mask].head())
        else:
            action = "overwriting" if existing else "creating"
            df.to_parquet(out)
            print(f"    {suffix}: {len(df):,} bars [{elapsed:.1f}s] → {out.name} ({action})")


def main():
    parser = argparse.ArgumentParser(description="Resample 1s parquet to 1m and 5m")
    parser.add_argument("symbols", nargs="*", help="Symbols to process (default: all *_1s.parquet)")
    parser.add_argument("--validate", action="store_true",
                        help="Compare resampled output against existing files instead of overwriting")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    else:
        symbols = sorted(
            p.stem.replace("_1s", "")
            for p in DATA_DIR.glob("*_1s.parquet")
        )

    if not symbols:
        print("No *_1s.parquet files found in", DATA_DIR)
        sys.exit(1)

    print(f"Resampling 1s → 1m + 5m for: {', '.join(symbols)}")
    print(f"Data dir: {DATA_DIR}\n")

    t_total = time.time()
    for symbol in symbols:
        process_symbol(symbol, validate=args.validate)
        print()

    print(f"Done [{time.time() - t_total:.1f}s total]")


if __name__ == "__main__":
    main()
