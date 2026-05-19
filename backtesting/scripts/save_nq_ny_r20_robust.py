#!/usr/bin/env python3
"""Save NQ NY R20 robust pipeline anchor config to the main DB.

Config from R16-R20 optimization:
  stop=8.75%, rr=2.625, gap=2.25%, tp1=0.3, ORB=20m, ATR=12, dir=both
  1894 trades, 59.87% WR, PF 1.28, Sharpe 1.722, 204.05R, DD -12.84R, Calmar 16.36
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
        stop_atr_pct=8.75,
        min_gap_atr_pct=2.25,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=2.625,
        tp1_ratio=0.3,
        atr_length=12,
        name="NQ NY R20 Robust Anchor",
        notes=(
            "NQ NY R20 anchor config from R16-R20 optimization. "
            "stop=8.75% rr=2.625 gap=2.25% tp1=0.3, ORB=20m (09:30-09:50), "
            "entry≤15:30, flat=15:50, ATR=12, both, 1s magnifier."
        ),
    )


def main():
    print("Saving NQ NY R20 Robust Anchor to DB")
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
