#!/usr/bin/env python3
"""Save NQ Asia R9 Restart Final to the experiments DB.

Config: stop=4.0%, rr=3.0, gap=0.90%, tp1=0.6, ORB=15m (20:00-20:15),
        entry<=22:30, flat=04:00, ATR=5, direction=long, excl-Tue, ICF=ON, 1s magnifier
        max_gap_points=75

Full-history (2016-2026): 770 trades, 45.5% WR, PF 1.42, Sharpe 2.52,
  176.2R (17.6 R/yr), DD -11.3R, Calmar 15.64, 0 negative years

WF: 7 folds, WF efficiency 0.797, stability 0.964 (high), combined OOS +100.2R
Hold-out (2025+): 89 trades, Sharpe 2.77, PF 1.49, +23.2R
Monte Carlo: 91.7% survival at -25R ruin
Verdict: GO — All 5 phases passed.
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter, TUE
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

DOW_EXCL = {TUE}  # excl Tuesday


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
        min_gap_atr_pct=0.90,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.6,
        atr_length=5,
        impulse_close_filter=True,
        name="NQ Asia Cont Long 2016-2026 Final (R9 restart)",
        notes=(
            "Full-optimization pipeline with tp1>=0.2 minimum. "
            "R1-R9 restart variable sweeps converged. Grid Sweep R2: anchor #2/500, "
            "Calmar delta <0.5, 135/500 combos with 0 neg years. "
            "Robust pipeline: 5/5 PASS — GO. "
            "WF efficiency 0.797, stability 0.964 (gap=0.9 stable 7/7 folds). "
            "Hold-out 2025+: 89 trades, Sharpe 2.77, PF 1.49, +23.2R. "
            "MC survival 91.7% at -25R ruin. "
            "Config: stop=4.0% rr=3.0 gap=0.90% tp1=0.6, ORB=15m (20:00-20:15), "
            "entry<=22:30, flat=04:00, ATR=5, long, excl-Tue, ICF=ON, 1s magnifier, "
            "max_gap_points=75."
        ),
    )


def main():
    print("Saving NQ Asia R9 Restart Final to DB")
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
