#!/usr/bin/env python3
"""Sweep entry_start time for GC Inversion Longs v8.

Tests shifting the entry window start later to filter out weak morning signals.
ORB remains 09:30-09:35, entry_end stays 15:00.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED = ("20241218",)
START = "2016-01-01"


def build_config(entry_start="09:35"):
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start=entry_start,
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=3.5,
        tp1_ratio=0.2,
        risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0,
        qty_step=1.0,
        sessions=(session,),
        instrument=GC,
        strategy="inversion",
        direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS,
        excluded_dates=EXCLUDED,
    )


def main():
    print("=" * 75)
    print("  GC Inversion Longs v8 — Entry Start Time Sweep")
    print("=" * 75)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    entry_starts = [
        "09:35",  # baseline
        "09:40",
        "09:45",
        "09:50",
        "09:55",
        "10:00",
        "10:05",
        "10:10",
        "10:15",
        "10:20",
        "10:25",
        "10:30",
        "10:45",
        "11:00",
    ]

    print(f"\n  {'Start':>8s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Sharpe':>7s} {'PF':>6s} {'Max DD':>7s} {'Calmar':>7s} {'Avg R':>7s}")
    print(f"  {'─'*65}")

    t0 = time.time()
    for es in entry_starts:
        config = build_config(entry_start=es)
        trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
        m = compute_metrics(trades)
        marker = " <── base" if es == "09:35" else ""
        print(
            f"  {es:>8s} {m['total_trades']:>7d} {m['win_rate']:>5.1%} "
            f"{m['total_r']:>7.1f} {m['sharpe_ratio']:>7.3f} {m['profit_factor']:>6.2f} "
            f"{m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} {m['avg_r']:>7.3f}{marker}"
        )

    print(f"\n  ({time.time() - t0:.1f}s)")
    print()


if __name__ == "__main__":
    main()
