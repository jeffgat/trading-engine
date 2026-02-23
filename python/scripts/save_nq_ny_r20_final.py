#!/usr/bin/env python3
"""Save NQ NY ICF=ON best clean config to the experiments DB.

Best clean config from 288-combo ICF=ON grid sweep (stop × rr × gap):
  stop=9.0%, rr=4.0, gap=3.5%, tp1=0.3, ORB=20m, ATR=12, dir=both, ICF=ON

Full-history (2016-2026): 1,785 trades, 49.0% WR, PF 1.21, Sharpe 1.30,
  190.8R (19.1 R/yr), DD -15.3R, Calmar 12.46, 0 negative years

Not adopted — R20 ICF=OFF (Calmar 16.36) dominates by 3.9 points.
Variable sweeps confirmed all dimensions at local optimum except long-only
(Calmar 13.52, still 2.84 below R20 ICF=OFF).
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics


def make_config():
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=3.5,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=4.0,
        tp1_ratio=0.3,
        atr_length=12,
        impulse_close_filter=True,
        name="NQ NY ICF ON Best Clean",
        notes=(
            "Best zero-neg-year config from 288-combo ICF=ON grid sweep "
            "(stop 5-12% × rr 1.5-4.0 × gap 1.0-3.5%). "
            "NOT ADOPTED — R20 ICF=OFF (Calmar 16.36) dominates by 3.9 points. "
            "Variable sweeps on this config: entry_end, tp1, ATR all at Δ=0. "
            "Long-only pushes to Calmar 13.52 but still 2.84 below R20 ICF=OFF. "
            "ICF definitively ruled out for NQ NY across full parameter space. "
            "Config: stop=9.0% rr=4.0 gap=3.5% tp1=0.3, ORB=20m (09:30-09:50), "
            "entry≤15:30, flat=15:50, ATR=12, both, ICF=ON, 1s magnifier."
        ),
    )


def main():
    print("Saving NQ NY ICF ON Best Clean to DB")
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
