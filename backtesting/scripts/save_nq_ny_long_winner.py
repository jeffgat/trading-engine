#!/usr/bin/env python3
"""Save NQ NY Long continuation winner to the main DB.

Config: g=3.0 rr=2.25 tp1=0.7 stop=9% long-only 20m ORB entry 09:50-15:00
In-sample: 1167 trades, 46.1% WR, PF 1.30, 182.0R (16.5 R/yr), DD -10.6R, Calmar 17.17

This is the final candidate from 15 rounds of variable sweeps, ready for
robust pipeline validation.
"""

import sys

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics


def make_config():
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=3.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.25,
        tp1_ratio=0.7,
        atr_length=14,
        name="NQ NY Long Continuation Winner (R1-R15)",
        notes=(
            "Final candidate from 15 rounds of variable sweeps. "
            "Long-only, 20m ORB (09:30-09:50), entry 09:50-15:00, "
            "g=3.0% rr=2.25 tp1=0.7 stop=9%. "
            "All config variables, env filters, regime switches, and "
            "directional combos tested — this is the Calmar-optimal config. "
            "Awaiting robust pipeline validation."
        ),
    )


def main():
    print("Saving NQ NY Long Continuation Winner to DB")
    print("=" * 60)

    print("\nLoading data...")
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")

    config = make_config()
    print("Running backtest...")
    trades = run_backtest(df_5m, config, start_date="2015-01-01", df_1m=df_1m)

    m = compute_metrics(trades)
    print(f"\n  Trades: {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  Net R: {m['total_r']:.1f}")
    print(f"  R/yr: {m['total_r'] / 11:.1f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")
    print(f"  PF: {m['profit_factor']:.2f}")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)

    print(f"\n  Saved as: {result_id}")
    print("  Done.")


if __name__ == "__main__":
    main()
