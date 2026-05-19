#!/usr/bin/env python3
"""Download historical futures data from Databento, build parquet files, and validate.

Downloads 1-minute OHLCV bars, saves as parquet, and resamples to 5m.
Then runs comprehensive data validation including gap detection.

Usage:
    # Download YM, RTY, SI (10 years) — fresh downloads
    uv run python scripts/download_and_validate.py YM RTY SI --start 2016-04-01

    # Update GC to latest (incremental from existing parquet)
    uv run python scripts/download_and_validate.py GC --update

    # All at once
    uv run python scripts/download_and_validate.py YM RTY SI --start 2016-04-01 --also-update GC

    # Dry run (show cost estimate only)
    uv run python scripts/download_and_validate.py YM RTY SI --start 2016-04-01 --cost-only

    # Validate existing files only (no download)
    uv run python scripts/download_and_validate.py YM RTY SI GC --validate-only
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from _env import load_backtesting_env

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# Databento continuous contract symbol mapping
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
    "SI":  "SI.v.0",   # Silver — volume roll (liquidity in specific months)
    "6B":  "6B.c.0",
}

DATASET = "GLBX.MDP3"

# CME Globex futures trade Sun 6 PM ET – Fri 5 PM ET
# Regular session gaps (no trading) are expected:
#   - Weekends: Fri 5 PM → Sun 6 PM (49 hours)
#   - Daily maintenance: ~5 PM – 6 PM ET (1 hour)
# Any gap longer than 6 hours during a weekday is suspicious.
MAX_EXPECTED_GAP_MINUTES_WEEKDAY = 360  # 6 hours
MAX_EXPECTED_GAP_MINUTES_WEEKEND = 3600  # 60 hours (Fri 5PM to Sun 6PM + buffer)

# CME holidays and early closes where gaps up to ~30h are normal.
# Christmas Eve (~1:15 PM close), New Year's Eve (~5 PM close),
# Good Friday (closed), Thanksgiving (early close), and special closures.
# We check if a gap starts on one of these dates (month, day).
CME_KNOWN_EARLY_CLOSE_DATES = {
    (12, 24),  # Christmas Eve — early close ~1:15 PM ET
    (12, 25),  # Christmas Day — closed
    (12, 31),  # New Year's Eve
    (1, 1),    # New Year's Day — closed
    (7, 3),    # July 3 — early close before July 4
    (7, 4),    # July 4 — Independence Day
    (11, 27),  # Day before Thanksgiving (approx)
    (11, 28),  # Thanksgiving (approx)
}

# Specific known full-day closures (year, month, day)
CME_SPECIAL_CLOSURES = {
    (2018, 12, 5),   # George H.W. Bush National Day of Mourning
    (2020, 6, 30),   # CME outage / reduced hours (known data gap across all instruments)
    (2025, 1, 9),    # Jimmy Carter National Day of Mourning
    (2001, 9, 11),   # 9/11
    (2001, 9, 12),
    (2001, 9, 13),
    (2001, 9, 14),
}


def get_api_key() -> str:
    load_backtesting_env()
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("ERROR: DATABENTO_API_KEY environment variable not set.")
        print("  1. Go to https://databento.com/portal/keys")
        print("  2. Add DATABENTO_API_KEY to backtesting/.env")
        sys.exit(1)
    return key


def estimate_cost(client, symbols: list[str], start: str, end: str) -> None:
    """Estimate data cost before downloading."""
    total = 0.0
    for symbol in symbols:
        db_symbol = SYMBOL_MAP[symbol]
        try:
            cost = client.metadata.get_cost(
                dataset=DATASET,
                symbols=[db_symbol],
                stype_in="continuous",
                schema="ohlcv-1m",
                start=start,
                end=end,
            )
            print(f"  {symbol:5s} ({db_symbol}): ${cost:.4f}")
            total += cost
        except Exception as e:
            print(f"  {symbol:5s}: error estimating cost - {e}")
    print(f"  {'TOTAL':5s}: ${total:.4f}")


def download_1m(client, symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """Download 1-minute OHLCV data from Databento. Returns DataFrame or None."""
    db_symbol = SYMBOL_MAP[symbol]
    print(f"\n  Downloading {symbol} ({db_symbol}) 1m data: {start} → {end}")
    t0 = time.time()

    try:
        data = client.timeseries.get_range(
            dataset=DATASET,
            symbols=[db_symbol],
            stype_in="continuous",
            schema="ohlcv-1m",
            start=start,
            end=end,
        )
        df = data.to_df()
    except Exception as e:
        print(f"    ERROR: {e}")
        return None

    if df.empty:
        print(f"    No data returned for {symbol}")
        return None

    elapsed = time.time() - t0
    print(f"    Downloaded {len(df):,} 1m bars [{elapsed:.1f}s]")

    # Convert UTC → Eastern, strip tz
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


def resample_and_save(df_1m: pd.DataFrame, symbol: str) -> dict[str, Path]:
    """Resample 1m data to 5m, save both as parquet. Returns paths."""
    paths = {}

    # Save 1m parquet
    path_1m = DATA_DIR / f"{symbol}_1m.parquet"
    df_1m.to_parquet(path_1m)
    size_mb = path_1m.stat().st_size / 1_048_576
    print(f"    Saved {symbol}_1m.parquet: {len(df_1m):,} bars, {size_mb:.1f} MB")
    paths["1m"] = path_1m

    # Resample to 5m
    df_5m = df_1m.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })

    # Forward-fill gaps during market hours (limit 60 bars = 5 hours for 5m)
    df_5m["volume"] = df_5m["volume"].fillna(0).astype(int)
    df_5m["close"] = df_5m["close"].ffill(limit=60)
    df_5m["open"] = df_5m["open"].fillna(df_5m["close"])
    df_5m["high"] = df_5m["high"].fillna(df_5m["close"])
    df_5m["low"] = df_5m["low"].fillna(df_5m["close"])
    df_5m = df_5m.dropna(subset=["open"])

    path_5m = DATA_DIR / f"{symbol}_5m.parquet"
    df_5m.to_parquet(path_5m)
    size_mb = path_5m.stat().st_size / 1_048_576
    print(f"    Saved {symbol}_5m.parquet: {len(df_5m):,} bars, {size_mb:.1f} MB")
    print(f"    Range: {df_5m.index[0]} → {df_5m.index[-1]}")
    paths["5m"] = path_5m

    return paths


def update_existing(client, symbol: str, end_date: str) -> bool:
    """Incrementally update existing parquet files for a symbol."""
    path_1m = DATA_DIR / f"{symbol}_1m.parquet"
    path_5m = DATA_DIR / f"{symbol}_5m.parquet"

    if not path_1m.exists():
        print(f"  ERROR: {path_1m.name} does not exist — cannot update. Use --start for fresh download.")
        return False

    # Read existing 1m data to find current end
    print(f"\n  Loading existing {symbol}_1m.parquet...")
    t0 = time.time()
    df_existing = pd.read_parquet(path_1m)
    current_end = df_existing.index[-1]
    print(f"    {len(df_existing):,} existing bars, ends at {current_end} [{time.time() - t0:.1f}s]")

    # Download from current end date (overlap for dedup safety)
    fetch_start = current_end.strftime("%Y-%m-%d")
    print(f"  Fetching {symbol} 1m data: {fetch_start} → {end_date}")

    df_new = download_1m(client, symbol, fetch_start, end_date)
    if df_new is None or df_new.empty:
        print(f"  No new data for {symbol}")
        return True

    # Filter to genuinely new bars
    df_new = df_new[df_new.index > current_end]
    print(f"    {len(df_new):,} genuinely new bars after dedup")

    if df_new.empty:
        print(f"  Already up to date for {symbol}")
        return True

    # Validate new data
    warnings = validate_ohlcv(df_new, symbol)
    if warnings:
        for w in warnings:
            print(f"    WARNING: {w}")

    # Ensure dtype consistency
    for col in df_existing.columns:
        if df_existing[col].dtype != df_new[col].dtype:
            print(f"    Casting {col}: {df_new[col].dtype} → {df_existing[col].dtype}")
            df_new[col] = df_new[col].astype(df_existing[col].dtype)

    # Merge
    df_merged = pd.concat([df_existing, df_new])
    df_merged = df_merged[~df_merged.index.duplicated(keep="first")]
    df_merged = df_merged.sort_index()

    print(f"  Merged: {len(df_existing):,} + {len(df_new):,} = {len(df_merged):,} bars")
    print(f"  New range: {df_merged.index[0]} → {df_merged.index[-1]}")

    # Save updated 1m and rebuild 5m
    resample_and_save(df_merged, symbol)
    return True


def validate_ohlcv(df: pd.DataFrame, symbol: str) -> list[str]:
    """Run OHLCV sanity checks. Returns list of warnings."""
    warnings = []

    if df.empty:
        warnings.append("Empty DataFrame")
        return warnings

    # NaN in OHLC
    nan_counts = df[["open", "high", "low", "close"]].isna().sum()
    if nan_counts.any():
        warnings.append(f"NaN values: {nan_counts.to_dict()}")

    # OHLC consistency
    bad_hl = (df["high"] < df["low"]).sum()
    if bad_hl > 0:
        warnings.append(f"{bad_hl} bars where high < low")

    bad_ho = (df["high"] < df["open"]).sum()
    if bad_ho > 0:
        warnings.append(f"{bad_ho} bars where high < open")

    bad_lc = (df["low"] > df["close"]).sum()
    if bad_lc > 0:
        warnings.append(f"{bad_lc} bars where low > close")

    bad_lo = (df["low"] > df["open"]).sum()
    if bad_lo > 0:
        warnings.append(f"{bad_lo} bars where low > open")

    bad_hc = (df["high"] < df["close"]).sum()
    if bad_hc > 0:
        warnings.append(f"{bad_hc} bars where high < close")

    # Negative/zero prices
    neg = (df[["open", "high", "low", "close"]] <= 0).any().any()
    if neg:
        warnings.append("Negative or zero prices detected")

    # Duplicate timestamps
    dupes = df.index.duplicated().sum()
    if dupes > 0:
        warnings.append(f"{dupes} duplicate timestamps")

    # Monotonic index
    if not df.index.is_monotonic_increasing:
        warnings.append("Index is NOT monotonically increasing")

    return warnings


def _is_known_closure(prev_ts: pd.Timestamp, ts: pd.Timestamp) -> bool:
    """Check if a gap spans a known CME holiday/early close or special closure."""
    # Check if the gap start date is a known early close (Christmas Eve, NYE, etc.)
    prev_md = (prev_ts.month, prev_ts.day)
    ts_md = (ts.month, ts.day)
    if prev_md in CME_KNOWN_EARLY_CLOSE_DATES or ts_md in CME_KNOWN_EARLY_CLOSE_DATES:
        return True

    # Check the day before ts (the closed day) — e.g., gap from Dec 24 → Dec 26
    closed_day = ts.date() - timedelta(days=1)
    if (closed_day.month, closed_day.day) in CME_KNOWN_EARLY_CLOSE_DATES:
        return True

    # Check specific known full-day closures
    prev_ymd = (prev_ts.year, prev_ts.month, prev_ts.day)
    ts_ymd = (ts.year, ts.month, ts.day)
    if prev_ymd in CME_SPECIAL_CLOSURES or ts_ymd in CME_SPECIAL_CLOSURES:
        return True

    # Check if the gap start or end is adjacent to a special closure
    for delta in range(0, 4):  # check up to 3 days between
        check_date = prev_ts.date() + timedelta(days=delta)
        if (check_date.year, check_date.month, check_date.day) in CME_SPECIAL_CLOSURES:
            return True

    # Good Friday: Friday before Easter (variable date) — detect by checking
    # if prev is Thursday and gap > 1 day ending on Sunday/Monday, in March/April
    if (prev_ts.weekday() == 3 and prev_ts.month in (3, 4)
            and (ts.date() - prev_ts.date()).days >= 2):
        return True

    return False


def detect_gaps(df: pd.DataFrame, symbol: str, timeframe: str = "1m") -> list[dict]:
    """Detect suspicious gaps in the data (beyond normal market closures).

    Returns list of gap info dicts for gaps that exceed expected thresholds.
    Classifies each gap as: WEEKEND, HOLIDAY, or UNEXPECTED.
    """
    if df.empty or len(df) < 2:
        return []

    # Compute time differences between consecutive bars
    diffs = df.index.to_series().diff()

    suspicious_gaps = []

    for i in range(1, len(diffs)):
        gap = diffs.iloc[i]
        if pd.isna(gap):
            continue

        gap_minutes = gap.total_seconds() / 60
        ts = df.index[i]
        prev_ts = df.index[i - 1]

        # Check if this gap spans a weekend (Friday to Sunday/Monday)
        is_weekend_gap = (
            prev_ts.weekday() == 4 and ts.weekday() in (0, 6)  # Fri → Sun/Mon
            or prev_ts.weekday() == 5  # Saturday (shouldn't have data)
            or prev_ts.weekday() == 6 and ts.weekday() == 0  # Sun → Mon
        )

        # Check if it's a multi-day gap (holidays, long weekends)
        is_multiday = (ts.date() - prev_ts.date()).days > 1

        # Check known CME holidays and special closures
        is_known_holiday = _is_known_closure(prev_ts, ts)

        if is_weekend_gap or is_multiday or is_known_holiday:
            threshold = MAX_EXPECTED_GAP_MINUTES_WEEKEND
        else:
            threshold = MAX_EXPECTED_GAP_MINUTES_WEEKDAY

        if gap_minutes > threshold:
            # Classify the gap
            if is_weekend_gap:
                gap_type = "WEEKEND"
            elif is_known_holiday:
                gap_type = "HOLIDAY"
            elif is_multiday:
                gap_type = "HOLIDAY"  # multi-day gaps are almost always holidays
            else:
                gap_type = "UNEXPECTED"

            suspicious_gaps.append({
                "from": prev_ts,
                "to": ts,
                "gap_hours": gap_minutes / 60,
                "gap_days": gap_minutes / 60 / 24,
                "gap_type": gap_type,
            })

    return suspicious_gaps


def validate_file(symbol: str, timeframe: str = "5m") -> bool:
    """Validate an existing parquet file. Returns True if valid."""
    suffix = f"_{timeframe}.parquet"
    path = DATA_DIR / f"{symbol}{suffix}"

    if not path.exists():
        print(f"  {path.name}: NOT FOUND")
        return False

    print(f"\n  Validating {path.name}...")
    df = pd.read_parquet(path)
    size_mb = path.stat().st_size / 1_048_576

    print(f"    Shape: {df.shape[0]:,} rows × {df.shape[1]} cols")
    print(f"    Size: {size_mb:.1f} MB")
    print(f"    Range: {df.index[0]} → {df.index[-1]}")
    print(f"    Columns: {list(df.columns)}")
    print(f"    Index name: {df.index.name}")

    # Basic year coverage
    years = sorted(df.index.year.unique())
    print(f"    Years covered: {years[0]}-{years[-1]} ({len(years)} unique years)")

    # Monthly bar counts (check for thin months)
    monthly = df.resample("MS").size()
    thin_months = monthly[monthly < 100]
    if len(thin_months) > 0 and timeframe in ("1m", "5m"):
        print(f"    WARNING: {len(thin_months)} months with <100 bars:")
        for dt, cnt in thin_months.items():
            if cnt > 0:  # skip zero months at boundaries
                print(f"      {dt.strftime('%Y-%m')}: {cnt} bars")

    # OHLCV validation
    warnings = validate_ohlcv(df, symbol)
    if warnings:
        for w in warnings:
            print(f"    WARNING: {w}")
    else:
        print(f"    OHLCV checks: PASS")

    # Gap detection
    gaps = detect_gaps(df, symbol, timeframe)
    if gaps:
        unexpected = [g for g in gaps if g["gap_type"] == "UNEXPECTED"]
        expected = [g for g in gaps if g["gap_type"] != "UNEXPECTED"]

        if expected:
            print(f"    Expected gaps (holidays/weekends): {len(expected)}")
        if unexpected:
            print(f"    UNEXPECTED GAPS ({len(unexpected)}):")
            for g in unexpected[:20]:
                print(f"      {g['from']} → {g['to']} ({g['gap_hours']:.1f}h / {g['gap_days']:.1f}d) [!!! UNEXPECTED]")
            if len(unexpected) > 20:
                print(f"      ... and {len(unexpected) - 20} more")
            print(f"\n    *** {len(unexpected)} UNEXPECTED GAPS (potential data corruption!) ***")
            return False
        else:
            print(f"    Gap detection: PASS (all {len(gaps)} gaps are holidays/weekends)")
    else:
        print(f"    Gap detection: PASS (no gaps above threshold)")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Download, build, and validate futures data from Databento",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("symbols", nargs="*", help="Symbols to download fresh (e.g., YM RTY SI)")
    parser.add_argument("--start", help="Start date for fresh downloads (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (default: yesterday)")
    parser.add_argument("--also-update", nargs="*", default=[], help="Symbols to incrementally update (e.g., GC)")
    parser.add_argument("--update", action="store_true", help="Treat all specified symbols as incremental updates")
    parser.add_argument("--cost-only", action="store_true", help="Only estimate cost, don't download")
    parser.add_argument("--validate-only", action="store_true", help="Only validate existing files, no download")

    args = parser.parse_args()

    # Default end = yesterday
    if args.end:
        end_date = args.end
    else:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = yesterday.strftime("%Y-%m-%d")

    all_symbols = list(args.symbols or [])
    update_symbols = list(args.also_update or [])

    if args.update:
        update_symbols = all_symbols
        all_symbols = []

    # Validate symbol names
    for s in all_symbols + update_symbols:
        s_upper = s.upper()
        if s_upper not in SYMBOL_MAP:
            print(f"ERROR: Unknown symbol '{s}'. Supported: {', '.join(sorted(SYMBOL_MAP.keys()))}")
            sys.exit(1)

    all_symbols = [s.upper() for s in all_symbols]
    update_symbols = [s.upper() for s in update_symbols]

    # Validate-only mode
    if args.validate_only:
        print(f"=== Validating existing data files ===\n")
        all_to_validate = all_symbols + update_symbols
        if not all_to_validate:
            # Validate all existing files
            existing = sorted(DATA_DIR.glob("*_5m.parquet"))
            all_to_validate = [p.stem.replace("_5m", "") for p in existing]
            print(f"Found {len(all_to_validate)} instruments: {', '.join(all_to_validate)}")

        results = {}
        for symbol in all_to_validate:
            for tf in ["1m", "5m"]:
                key = f"{symbol}_{tf}"
                results[key] = validate_file(symbol, tf)

        print(f"\n{'='*60}")
        print("VALIDATION SUMMARY:")
        for key, ok in results.items():
            status = "PASS" if ok else "FAIL"
            print(f"  {key:15s}: {status}")
        return

    # Need databento for download
    if not all_symbols and not update_symbols:
        parser.error("Specify symbols to download or use --validate-only")

    if all_symbols and not args.start and not args.cost_only:
        parser.error("--start is required for fresh downloads")

    try:
        import databento as db
    except ImportError:
        print("ERROR: databento not installed. Run: uv pip install databento")
        sys.exit(1)

    api_key = get_api_key()
    client = db.Historical(api_key)

    print(f"=== Databento Data Download & Validation ===")
    print(f"  Dataset:     {DATASET}")
    if all_symbols:
        print(f"  Fresh DL:    {', '.join(all_symbols)} ({args.start} → {end_date})")
    if update_symbols:
        print(f"  Update:      {', '.join(update_symbols)} (incremental → {end_date})")
    print(f"  Output dir:  {DATA_DIR}")
    print()

    # Cost estimation
    if args.cost_only:
        print("Estimated costs (1m OHLCV):")
        if all_symbols:
            estimate_cost(client, all_symbols, args.start, end_date)
        if update_symbols:
            print("\n  (Incremental updates — cost depends on gap size)")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    total_t0 = time.time()

    # Fresh downloads
    for symbol in all_symbols:
        print(f"\n{'='*50}")
        print(f"DOWNLOADING {symbol} (fresh, {args.start} → {end_date})")

        df_1m = download_1m(client, symbol, args.start, end_date)
        if df_1m is None:
            results.append((symbol, False, "Download failed"))
            continue

        # Validate raw data
        warnings = validate_ohlcv(df_1m, symbol)
        if warnings:
            for w in warnings:
                print(f"    WARNING: {w}")

        # Save parquet files
        resample_and_save(df_1m, symbol)
        results.append((symbol, True, f"{len(df_1m):,} 1m bars"))

    # Incremental updates
    for symbol in update_symbols:
        print(f"\n{'='*50}")
        print(f"UPDATING {symbol} (incremental → {end_date})")

        ok = update_existing(client, symbol, end_date)
        results.append((symbol, ok, "updated" if ok else "update failed"))

    # Post-download validation
    print(f"\n{'='*60}")
    print("POST-DOWNLOAD VALIDATION")
    print(f"{'='*60}")

    validation_results = {}
    for symbol in all_symbols + update_symbols:
        for tf in ["1m", "5m"]:
            key = f"{symbol}_{tf}"
            validation_results[key] = validate_file(symbol, tf)

    # Final summary
    total_time = time.time() - total_t0
    print(f"\n{'='*60}")
    print(f"COMPLETE [{total_time:.1f}s]")
    print(f"{'='*60}")

    print("\nDownload results:")
    for sym, ok, detail in results:
        status = "OK" if ok else "FAILED"
        print(f"  {sym:5s}: {status} ({detail})")

    print("\nValidation results:")
    for key, ok in validation_results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {key:15s}: {status}")

    all_ok = all(ok for _, ok, _ in results) and all(ok for ok in validation_results.values())
    if not all_ok:
        print("\n*** SOME CHECKS FAILED — review warnings above ***")
        sys.exit(1)
    else:
        print("\nAll downloads and validations passed!")


if __name__ == "__main__":
    main()
