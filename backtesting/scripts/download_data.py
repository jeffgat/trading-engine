#!/usr/bin/env python3
"""Download historical futures data from Databento (1m bars, resampled to 5m).

Setup:
    1. Sign up at https://databento.com (get $125 free credits)
    2. Set DATABENTO_API_KEY in backtesting/.env
    3. Install: uv pip install databento

Usage:
    # Download NQ with both 5m and 1m data (always use --save-1m)
    python scripts/download_data.py NQ --start 2015-01-01 --save-1m

    # Download multiple instruments
    python scripts/download_data.py NQ ES CL GC --start 2016-01-01 --save-1m

    # Download all supported instruments
    python scripts/download_data.py --all --start 2018-01-01 --save-1m

    # Download with explicit end date
    python scripts/download_data.py NQ --start 2015-01-01 --end 2026-01-01 --save-1m

    # Estimate cost before downloading
    python scripts/download_data.py NQ ES --start 2015-01-01 --cost-only

Roll rules:
    Index futures (NQ, ES, YM, etc.): .c.0 calendar roll (front month is always liquid)
    Commodity futures (GC, MGC):      .v.0 volume roll (liquidity in specific months)

Data is saved to: python/data/raw/{SYMBOL}_5m.csv (+ {SYMBOL}_1m.csv with --save-1m)
The 1m data powers the trade chart magnifier in the dashboard.
Files are standard CSV with columns: datetime, open, high, low, close, volume
Timezone: America/New_York (Eastern)
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from _env import load_backtesting_env

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# Databento continuous contract symbol mapping
# Format: {OUR_SYMBOL: DATABENTO_SYMBOL}
# .c.0 = calendar roll (nearest expiration) — works for index futures
# .v.0 = volume roll (highest volume contract) — required for commodities
#         where liquidity concentrates in specific months (GC: even months only)
SYMBOL_MAP = {
    "NQ": "NQ.c.0",
    "MNQ": "MNQ.c.0",
    "ES": "ES.c.0",
    "MES": "MES.c.0",
    "YM": "YM.c.0",
    "MYM": "MYM.c.0",
    "RTY": "RTY.c.0",
    "GC": "GC.v.0",
    "MGC": "MGC.v.0",
    "CL": "CL.c.0",
    "MCL": "MCL.c.0",
    "SI": "SI.v.0",
    "6B": "6B.c.0",
}

DATASET = "GLBX.MDP3"  # CME Globex


def get_api_key() -> str:
    load_backtesting_env()
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        print("ERROR: DATABENTO_API_KEY environment variable not set.")
        print()
        print("  1. Sign up at https://databento.com (free $125 credits)")
        print("  2. Go to https://databento.com/portal/keys")
        print("  3. Add DATABENTO_API_KEY to backtesting/.env")
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
    *,
    save_1m: bool = True,
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

    # Optionally save 1m data (also forward-filled)
    if save_1m:
        output_1m = output_dir / f"{symbol}_1m.csv"
        df_1m = df.resample("1min").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        df_1m["volume"] = df_1m["volume"].fillna(0).astype(int)
        df_1m["close"] = df_1m["close"].ffill(limit=300)  # 5h limit
        df_1m["open"] = df_1m["open"].fillna(df_1m["close"])
        df_1m["high"] = df_1m["high"].fillna(df_1m["close"])
        df_1m["low"] = df_1m["low"].fillna(df_1m["close"])
        df_1m = df_1m.dropna(subset=["open"])
        df_1m.index = df_1m.index.tz_localize(None)
        df_1m.index.name = "datetime"
        df_1m.to_csv(output_1m)
        print(f"    Saved {len(df_1m):,} 1m bars → {output_1m.name}")

    # Resample 1m → 5m
    df_5m = df.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })

    # Forward-fill gaps during market hours so the backtest engine
    # and chart see continuous bars. CME Globex futures trade ~23h/day
    # (Sun 6 PM – Fri 5 PM ET). Bars with no trades get O=H=L=C=last
    # close, volume=0.  Limit to 60 bars (5h) so weekends/holidays
    # don't get filled.
    traded_mask = df_5m["open"].notna()
    df_5m["volume"] = df_5m["volume"].fillna(0).astype(int)
    df_5m["close"] = df_5m["close"].ffill(limit=60)
    df_5m["open"] = df_5m["open"].fillna(df_5m["close"])
    df_5m["high"] = df_5m["high"].fillna(df_5m["close"])
    df_5m["low"] = df_5m["low"].fillna(df_5m["close"])
    df_5m = df_5m.dropna(subset=["open"])

    filled_count = int((~traded_mask).sum()) - (len(traded_mask) - len(df_5m))
    if filled_count > 0:
        print(f"    Forward-filled {filled_count:,} empty 5m slots (vol=0)")

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
    parser.add_argument(
        "--save-1m", action="store_true",
        help="Also save the raw 1-minute data (in addition to 5m)",
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
        result = download_symbol(client, symbol, args.start, end, DATA_DIR, save_1m=args.save_1m)
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
