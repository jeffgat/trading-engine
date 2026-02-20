#!/usr/bin/env python3
"""Convert intraday OHLCV CSV files to Parquet and create GC_30s from 1s data.

Run once after downloading new CSV data:
    uv run python scripts/convert_to_parquet.py

Converts:
  - All *_5m.csv and *_1m.csv  →  corresponding .parquet files
  - GC_1s.csv (Databento format) →  GC_1s.parquet  (normalized to Eastern tz-naive)
  - GC_1s.parquet  →  GC_30s.parquet  (resampled)

The loader will prefer .parquet over .csv automatically after this runs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def convert_standard(csv_path: Path) -> None:
    """Convert a standard *_5m.csv or *_1m.csv to Parquet."""
    parquet_path = csv_path.with_suffix(".parquet")
    print(f"  {csv_path.name} → {parquet_path.name} ...", end=" ", flush=True)
    df = pd.read_csv(csv_path, parse_dates=["datetime"], index_col="datetime")
    df.to_parquet(parquet_path)
    size_mb = parquet_path.stat().st_size / 1_048_576
    print(f"{len(df):,} bars, {size_mb:.1f} MB")


def convert_gc_1s(csv_path: Path) -> pd.DataFrame:
    """Normalize GC_1s.csv (Databento format) and save as Parquet.

    Databento format differences vs. standard files:
      - Column: ts_event  (not datetime)
      - Timezone: UTC with tz offset  (not Eastern tz-naive)
      - Extra columns: rtype, publisher_id, instrument_id, symbol

    Output is tz-naive Eastern to match all other files.
    """
    parquet_path = csv_path.with_suffix(".parquet")
    print(f"  {csv_path.name} → {parquet_path.name} (normalizing Databento format) ...", end=" ", flush=True)

    df = pd.read_csv(csv_path)

    # Convert ts_event (UTC) → Eastern tz-naive
    df["datetime"] = (
        pd.to_datetime(df["ts_event"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    df = df.set_index("datetime")[["open", "high", "low", "close", "volume"]]
    df.to_parquet(parquet_path)

    size_mb = parquet_path.stat().st_size / 1_048_576
    print(f"{len(df):,} bars, {size_mb:.1f} MB")
    return df


def create_gc_30s(df_1s: pd.DataFrame) -> None:
    """Resample 1s data to 30s and save as Parquet."""
    parquet_path = DATA_DIR / "GC_30s.parquet"
    print(f"  GC_1s → {parquet_path.name} (resampling to 30s) ...", end=" ", flush=True)

    df_30s = df_1s.resample("30s").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open"])

    df_30s.to_parquet(parquet_path)

    size_mb = parquet_path.stat().st_size / 1_048_576
    print(f"{len(df_30s):,} bars, {size_mb:.1f} MB")


def main() -> None:
    print(f"Data directory: {DATA_DIR}\n")

    if not DATA_DIR.exists():
        print(f"ERROR: Data directory does not exist: {DATA_DIR}")
        return

    # Standard intraday files: *_5m.csv and *_1m.csv
    standard = sorted(DATA_DIR.glob("*_[15]m.csv"))
    if standard:
        print("Converting standard intraday files:")
        for csv_path in standard:
            convert_standard(csv_path)
    else:
        print("No standard *_5m.csv / *_1m.csv files found.")

    # GC_1s.csv — Databento format, needs normalization
    gc_1s_path = DATA_DIR / "GC_1s.csv"
    gc_1s_parquet = DATA_DIR / "GC_1s.parquet"

    if gc_1s_path.exists():
        print("\nConverting GC_1s.csv (Databento format):")
        df_1s = convert_gc_1s(gc_1s_path)
        print("\nCreating GC_30s.parquet:")
        create_gc_30s(df_1s)
    elif gc_1s_parquet.exists():
        # Already converted; just create 30s if missing
        gc_30s_parquet = DATA_DIR / "GC_30s.parquet"
        if not gc_30s_parquet.exists():
            print("\nGC_1s.parquet exists; creating GC_30s.parquet:")
            df_1s = pd.read_parquet(gc_1s_parquet)
            create_gc_30s(df_1s)
        else:
            print("\nGC_1s.parquet and GC_30s.parquet already exist — skipping.")
    else:
        print(f"\nGC_1s.csv not found at {gc_1s_path} — skipping 1s/30s conversion.")

    print("\nDone.")


if __name__ == "__main__":
    main()
