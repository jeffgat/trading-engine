#!/usr/bin/env python3
"""Save GC NY Continuation Longs R3 final config to the experiment DB.

R3 high-RR config with Friday exclusion:
  stop=4.5%, rr=9.0, tp1=0.35, ATR 7, gap=3.0%, max_gap_atr=30%
  ICF=True, 8m ORB (09:30-09:38), entry→12:00, flat 13:30
  Long-only, FOMC excluded, Friday excluded (post-backtest DOW filter)

Pipeline: Structural PASS, WF PASS (0.956 eff, 0.929 stab),
  Prop FAIL (worst month -8R), Hold-out PASS (Sharpe 4.256),
  MC FAIL (63.4% survival). User override → save as GO.
"""

import sys
import time
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import GC
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

EXCL_DAYS = {4}  # Friday

NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30", orb_end="09:38",
    entry_start="09:38", entry_end="12:00",
    flat_start="13:30", flat_end="16:00",
    stop_atr_pct=4.5,
    min_gap_atr_pct=3.0,
)

CONFIG = StrategyConfig(
    rr=9.0,
    tp1_ratio=0.35,
    risk_usd=5000.0,
    atr_length=7,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(NY_SESSION,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    impulse_close_filter=True,
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=FOMC_DATES,
    name="GC NY Cont Longs R3 High-RR Final (Fri Excl)",
    notes="R3 re-optimization. rr=9.0, tp1=0.35, ATR 7, 8m ORB, flat 13:30, ICF on, Fri excluded. "
          "Calmar 16.11, 0 neg years, WF eff 0.956, holdout Sharpe 4.256. "
          "Pipeline 3/5 (worst month -8R, MC 63.4%). User override GO.",
)

START_DATE = "2016-01-01"


def dow_filter(trades):
    return [t for t in trades if t.exit_type == EXIT_NO_FILL or
            datetime.date.fromisoformat(t.date).weekday() not in EXCL_DAYS]


if __name__ == "__main__":
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data(GC.data_file)
    df_1m = load_1m_for_5m(GC.data_file)
    df_1s = load_1s_for_5m(GC.data_file)
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} bars [{time.time()-t0:.1f}s]")

    print("Running backtest...")
    t0 = time.time()
    trades = run_backtest(df, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades = dow_filter(trades)
    print(f"  Done in {time.time()-t0:.1f}s")

    m = compute_metrics(trades)
    print(f"\n  Trades: {m['total_trades']}")
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
    print("  View in dashboard -> Backtests tab")
