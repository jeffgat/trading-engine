#!/usr/bin/env python3
"""Save NQ Asia Continuation Long R9 anchor to main DB.

GO config from full optimization (R1-R9 + Grid R1 + robust pipeline):
  stop_orb=100%, rr=6.0, gap_orb=10%, tp1=0.3, ORB=15m, entry<=22:30,
  flat=04:00, long, excl-Tue, ICF=OFF, 1s magnifier
  746 trades, 44.8% WR, PF 1.49, Sharpe 2.71, 200.1R, DD -8.9R, Calmar 22.61
  Robust pipeline GO (5/5): WFE 0.969, stability 0.893, MC survival 92.6%.
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

DOW_EXCL = {1}  # excl Tuesday


def make_config():
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",
        entry_start="20:15",
        entry_end="22:30",
        flat_start="04:00",
        flat_end="07:00",
        stop_atr_pct=4.0,
        min_gap_atr_pct=0.9,
        stop_orb_pct=100.0,
        min_gap_orb_pct=10.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=6.0,
        tp1_ratio=0.3,
        atr_length=5,
        impulse_close_filter=False,
        name="NQ Asia Cont Long 2016-2026 GO",
        notes=(
            "NQ Asia continuation long R9 anchor (ORB-based). Full optimization: "
            "R1-R9 variable sweeps -> Grid R1 confirmed #1/400 (Calmar 22.61). "
            "Robust pipeline GO (5/5): WFE 0.969, stability 0.893 (high), "
            "OOS avg annual R 19.9, MC survival 92.6% at -25R ruin. "
            "0 negative full years. DOW excl Tue applied post-backtest. "
            "See run_nq_asia_long_robust_pipeline.py."
        ),
    )


def main():
    print("Saving NQ Asia Cont Long (GO) to DB")
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
