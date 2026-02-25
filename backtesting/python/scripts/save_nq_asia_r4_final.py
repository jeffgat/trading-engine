#!/usr/bin/env python3
"""Save NQ Asia R4 Final to the experiments DB.

Config: stop=3.7%, rr=1.75, gap=0.90%, tp1=0.35, ORB=10m (20:00-20:10),
        entry≤01:00, flat=00:00, ATR=5, direction=both, no-Thursday, ICF=OFF, 1s magnifier

Full-history (2016-2026): 1,593 trades, 66.8% WR, PF 1.43, Sharpe 2.53,
  211.2R (21.1 R/yr), DD -8.9R, Calmar 23.85, 0 negative years

Fixed-param WF: 6/6 folds profitable, combined OOS Calmar 2.17, +113.3R
Hold-out (2025+): 172 trades, Sharpe 2.94, PF 1.52, +27.2R, DD -6.4R
Verdict: GO
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

DOW_EXCL = {3}  # no-Thursday


def make_config():
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="01:00",
        flat_start="00:00",
        flat_end="07:00",
        stop_atr_pct=3.7,
        min_gap_atr_pct=0.90,
        max_gap_points=0.0,
        max_gap_atr_pct=5.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=1.75,
        tp1_ratio=0.35,
        atr_length=5,
        name="NQ Asia R4 Final",
        notes=(
            "Final config from R1-R4 variable sweep optimization with 1s magnifier. "
            "Fully converged at R4 — all dimensions Δ=0. "
            "Grid sweep: #1 of 2,016 combos overall AND #1 among 797 zero-neg-year configs. "
            "Fixed-param WF: 6/6 folds profitable, combined OOS +113.3R, Calmar 2.17. "
            "Hold-out 2025+: 172 trades, Sharpe 2.94, PF 1.52, +27.2R. "
            "Verdict: GO. "
            "Config: stop=3.7% rr=1.75 gap=0.90% tp1=0.35, ORB=10m (20:00-20:10), "
            "entry≤01:00, flat=00:00, ATR=5, both, no-Thursday, ICF=OFF, 1s magnifier."
        ),
    )


def main():
    print("Saving NQ Asia R4 Final to DB")
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
    print(f"  R/yr: {m['total_r'] / 10:.1f}")
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
