#!/usr/bin/env python3
"""Quick 2026 backtest for ES NY Cont Long to get R data for Alpha V1 analysis."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL

INSTRUMENT = get_instrument("ES")

NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=5.0,
    min_gap_atr_pct=0.25,
    min_stop_points=3.0,
    min_tp1_points=3.0,
)

config = StrategyConfig(
    strategy="continuation",
    direction_filter="long",
    rr=5.0,
    tp1_ratio=0.2,
    risk_usd=5000.0,
    atr_length=7,
    use_bar_magnifier=True,
    excluded_days=(3,),  # Thu excluded
    sessions=(NY_SESSION,),
    instrument=INSTRUMENT,
)

# Load data — include warmup period before 2026 for ATR init
data_path = Path(__file__).resolve().parent.parent / "data" / "raw" / "ES_5m.csv"
df = load_5m_data(data_path, start="2025-11-01", end="2026-04-03")

# Load 1m for magnifier
ohlcv_1m = load_1m_for_5m(data_path)

print(f"Data: {len(df)} bars from {df.index[0]} to {df.index[-1]}")

# Run backtest with start_date filter so warmup data is used but trades only from 2026
import pandas as pd
results = run_backtest(df, config, start_date="2026-01-01", df_1m=ohlcv_1m)

# Filter fills from raw results
filled_results = [r for r in results if r.exit_type != EXIT_NO_FILL]
print(f"\nTotal trades: {len(filled_results)}")

if len(filled_results) > 0:
    metrics = compute_metrics(results)
    net_r = sum(r.r_multiple for r in filled_results)
    wins = sum(1 for r in filled_results if r.r_multiple > 0)
    wr = wins / len(filled_results) * 100
    max_dd = metrics.get("max_dd_r", 0)

    print(f"Net R: {net_r:+.1f}")
    print(f"Win Rate: {wr:.1f}%")
    print(f"Max DD: {max_dd:.1f}R")
    print(f"Avg R/trade: {net_r / len(filled_results):.3f}")

    # Monthly breakdown
    from collections import defaultdict
    monthly = defaultdict(lambda: {"r": 0.0, "n": 0})
    for r in filled_results:
        month = str(r.fill_time)[:7]
        monthly[month]["r"] += r.r_multiple
        monthly[month]["n"] += 1

    print(f"\nMonthly breakdown:")
    for month in sorted(monthly.keys()):
        m = monthly[month]
        print(f"  {month}: {m['r']:+.1f}R ({m['n']} trades)")

    print(f"\n2026 YTD Net R: {net_r:+.1f}")
else:
    print("No trades found!")
