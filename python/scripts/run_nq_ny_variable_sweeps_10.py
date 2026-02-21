#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 10: ultra-fine stop sweep for #1 config.

Config: g3.0 rr2.75 tp0.6 stop=? (long-only, 20m ORB, entry 09:50-15:00, magnifier)
Stop range: 8.5% to 9.5% in 0.1% increments (11 values)
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import NY_SESSION, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
DATA_YEARS = 11

NY_20M = replace(
    NY_SESSION,
    orb_end="09:50",
    entry_start="09:50",
)


def make_config(stop):
    sess = replace(NY_20M,
                   entry_start="09:50",
                   entry_end="15:00",
                   min_gap_atr_pct=3.0,
                   stop_atr_pct=stop)
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.75,
        tp1_ratio=0.6,
        name="NQ NY Stop Fine Sweep",
    )


def main():
    print("NQ NY ORB — Round 10: Ultra-Fine Stop Sweep (g3.0 rr2.75 tp0.6)")
    print("=" * 110)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    stops = [8.5 + i * 0.1 for i in range(11)]  # 8.5 to 9.5

    HDR = (
        f"{'#':>3} {'Stop%':>8} {'Trades':>7} {'WR':>6} {'PF':>6} "
        f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
    )
    print(f"\n{HDR}")
    print("-" * 110)

    best_calmar = -999
    best_stop = None

    for i, stop in enumerate(stops, 1):
        config = make_config(stop)
        trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
        m = compute_metrics(trades)
        r_per_yr = m['total_r'] / DATA_YEARS

        marker = ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_stop = stop

        print(
            f"{i:>3} {stop:>7.1f}% {m['total_trades']:>7} {m['win_rate']:>5.1%} "
            f"{m['profit_factor']:>6.2f} {m['total_r']:>7.1f} "
            f"{r_per_yr:>6.1f} {m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} "
            f"{m['avg_r']:>7.4f}"
        )
        if "r_by_year" in m:
            years = sorted(m["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
            print(f"    R by year: {yr_str}")

    print(f"\n  >> Best stop: {best_stop:.1f}% (Calmar {best_calmar:.2f})")

    elapsed = time.time() - t_start
    print(f"\n  Complete — {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
