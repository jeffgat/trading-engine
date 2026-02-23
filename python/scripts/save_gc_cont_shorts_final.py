#!/usr/bin/env python3
"""Save GC Continuation Shorts final config to the experiment DB.

WF mode params (use for live trading):
  rr=5.5, tp1=0.6, stop=2.5%, min_gap=5.5%
  ATR 10, 15m ORB, entry→15:00, max_gap_atr=25%, FOMC excluded
  Short-only, 1s magnifier

Pipeline verdict: CONDITIONAL GO
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

GC = get_instrument("GC")

NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30", orb_end="09:45",
    entry_start="09:45", entry_end="15:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=2.5,
    min_gap_atr_pct=5.5,
)

CONFIG = StrategyConfig(
    rr=7.0,                  # Structural anchor (WF mode 5.5 is worse — weak mode, 2/5 folds)
    tp1_ratio=0.6,
    risk_usd=5000.0,
    atr_length=10,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(NY_SESSION,),
    instrument=GC,
    strategy="continuation",
    direction_filter="short",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=FOMC_DATES,
    name="GC NY Cont Shorts Final (Structural)",
    notes="CONDITIONAL GO — Pipeline P1/P3/P4 PASS, P2 WF eff 0.28 (borderline), P5 MC 47.9%. Structural anchor params (WF mode rr=5.5 was weak — 2/5 folds, worse full-history metrics).",
)

START_DATE = "2016-01-01"

if __name__ == "__main__":
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} bars [{time.time()-t0:.1f}s]")

    print("Running backtest...")
    t0 = time.time()
    trades = run_backtest(df, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    print(f"  Done in {time.time()-t0:.1f}s")

    m = compute_metrics(trades)
    filled = m["total_trades"]
    print(f"\n  Trades: {filled}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  Net R: {m['total_r']:.1f}R")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f}")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  PF: {m['profit_factor']:.2f}")

    rby = m.get("r_by_year", {})
    if rby:
        print("\n  R by year:")
        for y, r in sorted(rby.items()):
            print(f"    {y}: {r:>8.1f}R")

    print("\nSaving to DB...")
    result = results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    print("  View in dashboard → Backtests tab")
