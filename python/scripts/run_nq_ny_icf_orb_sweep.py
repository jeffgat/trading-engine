#!/usr/bin/env python3
"""NQ NY ORB — ORB window sweep on best ICF=ON config.

Best clean ICF=ON config from grid sweep:
  stop=9.0%, rr=4.0, gap=3.5%, tp1=0.3, Calmar 12.46, 0 neg years

Sweep ORB window from 10m to 30m to see if a different window helps ICF.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=3.5,
    max_gap_points=100.0,
)

BASE = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=4.0,
    tp1_ratio=0.3,
    atr_length=12,
    impulse_close_filter=True,
    name="NQ NY ICF ORB sweep",
)

ORB_WINDOWS = [
    ("10m", "09:30", "09:40", "09:40"),
    ("15m", "09:30", "09:45", "09:45"),
    ("20m", "09:30", "09:50", "09:50"),
    ("25m", "09:30", "09:55", "09:55"),
    ("30m", "09:30", "10:00", "10:00"),
]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


HDR = (
    f"    {'#':>3} {'ORB':>6} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>10}"
)


def main():
    print("NQ NY ORB — ORB window sweep on best ICF=ON config")
    print("=" * 95)
    print(f"Config: stop=9.0%, rr=4.0, gap=3.5%, tp1=0.3, ATR=12, dir=both, ICF=ON")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t0:.1f}s]")

    print(f"\n{HDR}")
    print(f"    {'─'*90}")

    for i, (label, orb_s, orb_e, entry_s) in enumerate(ORB_WINDOWS, 1):
        sess = replace(BASE_SESSION, orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        config = replace(BASE, sessions=(sess,))
        trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)
        neg = neg_year_set(m)
        r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
        neg_str = ",".join(str(y) for y in sorted(neg)) if neg else "none"
        marker = " <-- anchor" if label == "20m" else ""
        print(
            f"    {i:>3} {label:>6} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
            f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} "
            f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} "
            f"{neg_str:>10}{marker}"
        )
        if "r_by_year" in m:
            years = sorted(m["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
            print(f"      R by year: {yr_str}")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
