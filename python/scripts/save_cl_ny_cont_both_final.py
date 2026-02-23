#!/usr/bin/env python3
"""Save CL NY Continuation Both best config to the experiment DB.

WF mode params (selected in ALL 7 folds):
  stop=0.75%, rr=7.0, gap=1.0%, tp1=0.7
  ATR 10, 10m ORB, entry→14:00, flat 15:50
  Both directions, 1s magnifier

Pipeline verdict: NO-GO (3/5) — Phase 3 worst month -12.8R, Phase 5 MC survival 43.3%.
Saving for reference. Strategy has genuine edge but tail risk exceeds prop firm limits.
"""

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

CL = get_instrument("CL")

NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30", orb_end="09:40",
    entry_start="09:40", entry_end="14:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=0.75,       # WF mode (7/7 folds)
    min_gap_atr_pct=1.0,     # WF mode (3/7 folds)
)

CONFIG = StrategyConfig(
    rr=7.0,                   # WF mode (7/7 folds)
    tp1_ratio=0.7,            # WF mode (5/7 folds)
    risk_usd=5000.0,
    atr_length=10,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(NY_SESSION,),
    instrument=CL,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
    name="CL NY Cont Both WF Mode (NO-GO)",
    notes="NO-GO config — pipeline 3/5. WF mode params (perfect stability 1.000). "
          "Phase 3 FAIL (worst month -12.8R), Phase 5 FAIL (MC survival 43.3% at -25R). "
          "Genuine edge but tail risk exceeds prop firm monthly loss limits.",
)

START_DATE = "2016-01-01"

if __name__ == "__main__":
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("CL_5m.csv")
    df_1m = load_1m_for_5m("CL_5m.csv")
    df_1s = load_1s_for_5m("CL_5m.csv")
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
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")

    print("\nSaving to DB...")
    result = results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    print("  View in dashboard -> Backtests tab")
