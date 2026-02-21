#!/usr/bin/env python3
"""Convert intraday OHLCV CSV files to Parquet and create 30s resampled files.

Run once after downloading new CSV data:
    uv run python scripts/convert_to_parquet.py

Converts:
  - All *_5m.csv and *_1m.csv  →  corresponding .parquet files
  - Any *_1s.csv (Databento format) →  *_1s.parquet  (normalized to Eastern tz-naive)
  - Each *_1s.parquet  →  *_30s.parquet, *_1m.parquet, *_5m.parquet  (resampled)

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


def convert_1s(csv_path: Path) -> pd.DataFrame:
    """Normalize a *_1s.csv (Databento format) and save as Parquet.

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


def _resample_agg(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open"])


def create_30s(df_1s: pd.DataFrame, symbol: str) -> None:
    """Resample 1s data to 30s and save as Parquet."""
    parquet_path = DATA_DIR / f"{symbol}_30s.parquet"
    print(f"  {symbol}_1s → {parquet_path.name} (resampling to 30s) ...", end=" ", flush=True)
    df = _resample_agg(df_1s, "30s")
    df.to_parquet(parquet_path)
    size_mb = parquet_path.stat().st_size / 1_048_576
    print(f"{len(df):,} bars, {size_mb:.1f} MB")


def create_1m(df_1s: pd.DataFrame, symbol: str) -> None:
    """Resample 1s data to 1m and save as Parquet."""
    parquet_path = DATA_DIR / f"{symbol}_1m.parquet"
    print(f"  {symbol}_1s → {parquet_path.name} (resampling to 1m) ...", end=" ", flush=True)
    df = _resample_agg(df_1s, "1min")
    df.to_parquet(parquet_path)
    size_mb = parquet_path.stat().st_size / 1_048_576
    print(f"{len(df):,} bars, {size_mb:.1f} MB")


def create_5m(df_1s: pd.DataFrame, symbol: str) -> None:
    """Resample 1s data to 5m and save as Parquet."""
    parquet_path = DATA_DIR / f"{symbol}_5m.parquet"
    print(f"  {symbol}_1s → {parquet_path.name} (resampling to 5m) ...", end=" ", flush=True)
    df = _resample_agg(df_1s, "5min")
    df.to_parquet(parquet_path)
    size_mb = parquet_path.stat().st_size / 1_048_576
    print(f"{len(df):,} bars, {size_mb:.1f} MB")


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

    # Any *_1s.csv — Databento format, needs normalization
    one_sec_csvs = sorted(DATA_DIR.glob("*_1s.csv"))
    for csv_path in one_sec_csvs:
        symbol = csv_path.stem.replace("_1s", "")
        parquet_1s = csv_path.with_suffix(".parquet")
        parquet_30s = DATA_DIR / f"{symbol}_30s.parquet"
        parquet_1m  = DATA_DIR / f"{symbol}_1m.parquet"
        parquet_5m  = DATA_DIR / f"{symbol}_5m.parquet"

        if csv_path.exists():
            print(f"\nConverting {csv_path.name} (Databento format):")
            df_1s = convert_1s(csv_path)
            print(f"\nCreating resampled files for {symbol}:")
            create_30s(df_1s, symbol)
            create_1m(df_1s, symbol)
            create_5m(df_1s, symbol)
        elif parquet_1s.exists():
            missing = [p for p in [parquet_30s, parquet_1m, parquet_5m] if not p.exists()]
            if missing:
                print(f"\n{parquet_1s.name} exists; creating missing resampled files:")
                df_1s = pd.read_parquet(parquet_1s)
                if not parquet_30s.exists():
                    create_30s(df_1s, symbol)
                if not parquet_1m.exists():
                    create_1m(df_1s, symbol)
                if not parquet_5m.exists():
                    create_5m(df_1s, symbol)
            else:
                print(f"\n{parquet_1s.name}, {parquet_30s.name}, {parquet_1m.name}, {parquet_5m.name} already exist — skipping.")

    if not one_sec_csvs:
        print("\nNo *_1s.csv files found — skipping 1s/30s conversion.")

    print("\nDone.")


if __name__ == "__main__":
    main()
