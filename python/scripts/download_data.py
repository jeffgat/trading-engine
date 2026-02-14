#!/usr/bin/env python3
"""Download historical 5-minute futures data from Databento.

Setup:
    1. Sign up at https://databento.com (get $125 free credits)
    2. Set your API key: export DATABENTO_API_KEY=db-xxxxxxxxxxxxxxxx
    3. Install: uv pip install databento

Usage:
    # Download NQ front-month continuous, 2015 to today
    python scripts/download_data.py NQ --start 2015-01-01

    # Download multiple instruments
    python scripts/download_data.py NQ ES CL GC --start 2016-01-01

    # Download all supported instruments
    python scripts/download_data.py --all --start 2018-01-01

    # Download with explicit end date
    python scripts/download_data.py NQ --start 2015-01-01 --end 2026-01-01

    # Estimate cost before downloading
    python scripts/download_data.py NQ ES --start 2015-01-01 --cost-only

Data is saved to: python/data/raw/{SYMBOL}_5m.csv
Files are standard CSV with columns: datetime, open, high, low, close, volume
Timezone: America/New_York (Eastern)
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# Databento continuous front-month symbol mapping
# Format: {OUR_SYMBOL: DATABENTO_SYMBOL}
# .c.0 = front month continuous contract
SYMBOL_MAP = {
    "NQ": "NQ.c.0",
    "MNQ": "MNQ.c.0",
    "ES": "ES.c.0",
    "MES": "MES.c.0",
    "YM": "YM.c.0",
    "MYM": "MYM.c.0",
    "RTY": "RTY.c.0",
    "GC": "GC.c.0",
    "MGC": "MGC.c.0",
    "CL": "CL.c.0",
    "MCL": "MCL.c.0",
}

DATASET = "GLBX.MDP3"  # CME Globex


def get_api_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("ERROR: DATABENTO_API_KEY environment variable not set.")
        print()
        print("  1. Sign up at https://databento.com (free $125 credits)")
        print("  2. Go to https://databento.com/portal/keys")
        print("  3. Run: export DATABENTO_API_KEY=db-your-key-here")
        sys.exit(1)
    return key


def estimate_cost(client, symbols: list[str], start: str, end: str) -> None:
    """Estimate data cost before downloading."""
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
        except Exception as e:
            print(f"  {symbol:5s}: error estimating cost - {e}")


def download_symbol(
    client,
    symbol: str,
    start: str,
    end: str,
    output_dir: Path,
) -> Path | None:
    """Download 1-minute OHLCV data, resample to 5m, save as CSV.

    Downloads 1m bars because Databento may not support 5m directly,
    and 1m gives us flexibility to resample to any timeframe later.
    """
    import pandas as pd

    db_symbol = SYMBOL_MAP[symbol]
    output_file = output_dir / f"{symbol}_5m.csv"

    print(f"  Downloading {symbol} ({db_symbol}) from {start} to {end}...")
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

    t_dl = time.time() - t0
    print(f"    Downloaded {len(df):,} 1m bars [{t_dl:.1f}s]")

    # Databento returns UTC timestamps — convert to Eastern
    if df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York")
    else:
        df.index = df.index.tz_localize("UTC").tz_convert("America/New_York")

    # Keep only OHLCV columns (Databento may include extra fields)
    ohlcv_cols = []
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            ohlcv_cols.append(col)

    if len(ohlcv_cols) < 5:
        # Databento uses different column names — try to map them
        col_map = {}
        for c in df.columns:
            cl = c.lower()
            if "open" in cl:
                col_map[c] = "open"
            elif "high" in cl:
                col_map[c] = "high"
            elif "low" in cl:
                col_map[c] = "low"
            elif "close" in cl:
                col_map[c] = "close"
            elif "volume" in cl:
                col_map[c] = "volume"
        if col_map:
            df = df.rename(columns=col_map)

    df = df[["open", "high", "low", "close", "volume"]].copy()

    # Resample 1m → 5m
    df_5m = df.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open"])

    # Remove timezone info for cleaner CSV (it's all Eastern)
    df_5m.index = df_5m.index.tz_localize(None)
    df_5m.index.name = "datetime"

    # Save as CSV with header (datetime, open, high, low, close, volume)
    df_5m.to_csv(output_file)

    print(f"    Saved {len(df_5m):,} 5m bars → {output_file.name}")
    print(f"    Range: {df_5m.index[0]} to {df_5m.index[-1]}")

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Download historical 5m futures data from Databento",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/download_data.py NQ --start 2015-01-01
  python scripts/download_data.py NQ ES CL GC --start 2016-01-01
  python scripts/download_data.py --all --start 2018-01-01
  python scripts/download_data.py NQ ES --start 2015-01-01 --cost-only

Supported symbols: """ + ", ".join(sorted(SYMBOL_MAP.keys())),
    )

    parser.add_argument(
        "symbols", nargs="*",
        help="Instrument symbols to download (e.g., NQ ES CL GC)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Download all supported instruments",
    )
    parser.add_argument(
        "--start", required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", default=None,
        help="End date (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--cost-only", action="store_true",
        help="Only estimate cost, don't download",
    )

    args = parser.parse_args()

    if args.all:
        symbols = sorted(SYMBOL_MAP.keys())
    elif args.symbols:
        symbols = [s.upper() for s in args.symbols]
        for s in symbols:
            if s not in SYMBOL_MAP:
                print(f"ERROR: Unknown symbol '{s}'. Supported: {', '.join(sorted(SYMBOL_MAP.keys()))}")
                sys.exit(1)
    else:
        parser.error("Specify symbols or use --all")

    end = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Import databento
    try:
        import databento as db
    except ImportError:
        print("ERROR: databento package not installed.")
        print("  Run: uv pip install databento")
        print("  Or:  pip install databento")
        sys.exit(1)

    api_key = get_api_key()
    client = db.Historical(api_key)

    print(f"Databento data download")
    print(f"  Dataset:     {DATASET}")
    print(f"  Symbols:     {', '.join(symbols)}")
    print(f"  Date range:  {args.start} to {end}")
    print(f"  Output dir:  {DATA_DIR}")
    print()

    if args.cost_only:
        print("Estimated costs:")
        estimate_cost(client, symbols, args.start, end)
        total_msg = "\nNote: Costs are approximate. You have $125 free credits on signup."
        print(total_msg)
        return

    # Create output directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Download each symbol
    results = []
    total_t0 = time.time()

    for symbol in symbols:
        result = download_symbol(client, symbol, args.start, end, DATA_DIR)
        results.append((symbol, result))
        print()

    # Summary
    total_time = time.time() - total_t0
    succeeded = sum(1 for _, r in results if r is not None)
    failed = sum(1 for _, r in results if r is None)

    print("=" * 50)
    print(f"Download complete [{total_time:.1f}s]")
    print(f"  Succeeded: {succeeded}")
    if failed:
        print(f"  Failed:    {failed}")
        for sym, r in results:
            if r is None:
                print(f"    - {sym}")
    print()
    print(f"Data saved to: {DATA_DIR}/")
    print(f"Run backtests: python scripts/run_backtest.py --data {symbols[0]}_5m.csv --start {args.start}")


if __name__ == "__main__":
    main()
