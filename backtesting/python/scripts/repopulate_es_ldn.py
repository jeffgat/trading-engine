#!/usr/bin/env python3
"""Repopulate ES LDN Continuation Both backtest with 1s bar magnifier."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

ES = get_instrument("ES")
START_DATE = "2016-03-02"
END_DATE = "2026-02-18"

ES_LDN_SESSION = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:10",
    entry_start="03:10",
    entry_end="08:25",
    flat_start="08:00",
    flat_end="08:25",
    stop_atr_pct=5.2,
    min_gap_atr_pct=1.25,
)

CONFIG = StrategyConfig(
    rr=2.0,
    tp1_ratio=0.40,
    risk_usd=5000.0,
    atr_length=50,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(ES_LDN_SESSION,),
    instrument=ES,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
    name="ES LDN Continuation Both 2016-2026",
)

if __name__ == "__main__":
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("ES_5m.csv", start=START_DATE, end=END_DATE)
    df_1m = load_1m_for_5m("ES_5m.csv", start=START_DATE, end=END_DATE)
    df_1s = load_1s_for_5m("ES_5m.csv", start=START_DATE, end=END_DATE)
    print(f"  5m: {len(df):,} bars")
    print(f"  1m: {len(df_1m):,} bars" if df_1m is not None else "  1m: NOT FOUND")
    print(f"  1s: {len(df_1s):,} bars" if df_1s is not None else "  1s: NOT FOUND")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    print("\nRunning backtest...")
    t0 = time.time()
    trades = run_backtest(df, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    elapsed = time.time() - t0

    print(f"\n  Trades:  {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  Net R:   {m['total_r']:.1f}R")
    print(f"  Max DD:  {m['max_drawdown_r']:.1f}R")
    print(f"  Sharpe:  {m['sharpe_ratio']:.3f}")
    print(f"  Calmar:  {m['calmar_ratio']:.3f}")
    print(f"  PF:      {m['profit_factor']:.2f}")
    print(f"  [{elapsed:.1f}s]")

    # Save to DB
    result = results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"\nSaved: {result_id}")
    print("View in dashboard → Backtests tab")
