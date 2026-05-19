#!/usr/bin/env python3
"""Save ES Asia Long Prop Firm 2x Risk config to main DB.

Config from prop firm phase 1 sweep (best balanced by success rate + Calmar):
  stop=2.5%, rr=1.75, gap=1.0%, tp1=0.3, ORB=10m (20:00-20:10),
  entry<=03:00, flat=06:45, ATR=5, direction=long, ICF=OFF, bar magnifier
  risk_usd=10000 (2x risk for prop firm deployment)

Prop firm phase 1 (2Y, -4R/+5R, biweekly stagger):
  At 2x risk (-2R/+2.5R effective): 88% success, 46 payouts, 6 breaches,
  avg 46 days to payout, median 41 days
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics


def make_config():
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="03:00",
        flat_start="06:45",
        flat_end="07:00",
        stop_atr_pct=2.5,
        min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=10000.0,
        direction_filter="long",
        rr=1.75,
        tp1_ratio=0.3,
        atr_length=5,
        name="ES Asia Long ORB Final 2x Risk",
        notes=(
            "ES Asia continuation long — prop firm 2x risk config. "
            "From prop firm phase 1 sweep: best balanced config by success rate + Calmar. "
            "At 1x ($5K): 100% success, 0 breaches, Calmar 10.17, Sharpe 3.84, avg 110d payout. "
            "At 2x ($10K): 88% success, 46 payouts / 6 breaches, avg 46d payout. "
            "Config: stop=2.5% rr=1.75 gap=1.0% tp1=0.3, ORB=10m (20:00-20:10), "
            "entry<=03:00, flat=06:45, ATR=5, long only, ICF=OFF, bar magnifier."
        ),
    )


def main():
    print("Saving ES Asia Long ORB Final 2x Risk to DB")
    print("=" * 60)

    print("\nLoading data...")
    t0 = time.time()
    df_5m = load_5m_data("ES_5m.parquet")
    df_1m = load_1m_for_5m("ES_5m.parquet")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    config = make_config()
    print("Running backtest...")
    trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m)

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
