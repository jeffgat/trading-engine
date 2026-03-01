#!/usr/bin/env python3
"""Save NQ Asia Continuation Short R6 anchor to experiments DB.

NO-GO config from full optimization (R4-R6 + Grid R2 + robust pipeline):
  stop=3.5%, rr=3.75, gap=1.0%, tp1=0.6, ATR=30, ORB=10m, entry<=01:00,
  flat=23:00, short, excl-Thu, ICF=ON, 1s magnifier
  874 trades, 40.7% WR, PF 1.24, Sharpe 1.40, 108.0R, DD -17.1R, Calmar 6.30
  Robust pipeline: 2/5 PASS (Structural + Hold-Out). NO-GO.
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

DOW_EXCL = {3}  # excl Thursday


def make_config():
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="01:00",
        flat_start="23:00",
        flat_end="07:00",
        stop_atr_pct=3.5,
        min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=3.75,
        tp1_ratio=0.6,
        atr_length=30,
        impulse_close_filter=True,
        name="NQ Asia Cont Short 2016-2026 NO-GO",
        notes=(
            "NQ Asia continuation short R6 anchor. Full optimization: "
            "R1-R3 sweeps -> Grid R1 -> R4-R6 sweeps -> Grid R2 confirmed #1/500. "
            "Robust pipeline NO-GO (2/5): WFE 0.467, OOS avg annual R 6.3, MC survival 62.9%. "
            "DOW excl Thu applied post-backtest. "
            "See run_nq_asia_short_robust_pipeline.py."
        ),
    )


def main():
    print("Saving NQ Asia Cont Short (NO-GO) to DB")
    print("=" * 60)

    print("\nLoading data...")
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    config = make_config()
    print("Running backtest...")
    trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCL)

    m = compute_metrics(trades)
    print(f"\n  Trades: {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  PF: {m['profit_factor']:.2f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.2f}")
    print(f"  Net R: {m['total_r']:.1f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")

    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"  R by year: {yr_str}")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)

    print(f"\n  Saved as: {result_id}")
    print("  Done.")


if __name__ == "__main__":
    main()
