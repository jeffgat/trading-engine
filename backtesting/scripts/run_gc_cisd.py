#!/usr/bin/env python3
"""GC CISD (Change in State of Delivery) strategy test.

CISD concept:
  1. Price sweeps beyond ORB level (liquidity grab)
  2. A displacement candle reverses and closes above/below prior candle's body
  3. Enter at the displacement candle's close

Uses the same session windows as the winning GC inversion v8 config.
Tests both longs-only and both directions, plus rr/tp1 grid.
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

GC_NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",       # 5-min ORB (same as inversion v8)
    entry_start="09:35",
    entry_end="15:00",     # Extended entry window
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=1.0,   # Not used by CISD but needed by SessionConfig
    max_gap_points=25.0,   # Not used by CISD but needed by SessionConfig
)


def build_config(direction="long", rr=3.5, tp1_ratio=0.2, atr_length=50):
    return StrategyConfig(
        rr=rr,
        tp1_ratio=tp1_ratio,
        risk_usd=5000.0,
        atr_length=atr_length,
        min_qty=1.0,
        qty_step=1.0,
        sessions=(GC_NY_SESSION,),
        instrument=GC,
        strategy="cisd",
        direction_filter=direction,
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def print_metrics(label, m):
    print(f"\n  {label}")
    print(f"  {'─'*55}")
    print(f"  Trades:  {m['total_trades']:>6d}     Win Rate: {m['win_rate']:>6.1%}")
    print(f"  Net R:   {m['total_r']:>6.1f}R     Avg R:    {m['avg_r']:>6.3f}R")
    print(f"  Sharpe:  {m['sharpe_ratio']:>6.3f}     PF:       {m['profit_factor']:>6.2f}")
    print(f"  Max DD:  {m['max_drawdown_r']:>6.1f}R     Calmar:   {m['calmar_ratio']:>6.2f}")


def main():
    print("=" * 70)
    print("  GC CISD (Change in State of Delivery) — Strategy Test")
    print("=" * 70)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    # ── Test 1: Longs-only (matches GC inversion learnings) ──────────────
    print("\n" + "─" * 70)
    print("  TEST 1: CISD Longs Only (rr=3.5, tp1=0.2, atr=50)")
    print("─" * 70)
    config = build_config(direction="long")
    t0 = time.time()
    trades = run_backtest(df, config, start_date="2016-01-01", df_1m=df_1m)
    print(f"  Backtest: {time.time() - t0:.1f}s")
    m_long = compute_metrics(trades)
    print_metrics("CISD Longs Only", m_long)

    # ── Test 2: Shorts-only ──────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 2: CISD Shorts Only (rr=3.5, tp1=0.2, atr=50)")
    print("─" * 70)
    config = build_config(direction="short")
    t0 = time.time()
    trades = run_backtest(df, config, start_date="2016-01-01", df_1m=df_1m)
    print(f"  Backtest: {time.time() - t0:.1f}s")
    m_short = compute_metrics(trades)
    print_metrics("CISD Shorts Only", m_short)

    # ── Test 3: Both directions ──────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 3: CISD Both Directions (rr=3.5, tp1=0.2, atr=50)")
    print("─" * 70)
    config = build_config(direction="both")
    t0 = time.time()
    trades = run_backtest(df, config, start_date="2016-01-01", df_1m=df_1m)
    print(f"  Backtest: {time.time() - t0:.1f}s")
    m_both = compute_metrics(trades)
    print_metrics("CISD Both Directions", m_both)

    # ── Test 4: RR × TP1 sweep on best direction ────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 4: RR × TP1 Sweep (longs only)")
    print("─" * 70)

    rr_vals = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    tp1_vals = [0.15, 0.2, 0.3, 0.4, 0.5]

    print(f"\n  {'rr':>5s} {'tp1':>5s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Sharpe':>7s} {'PF':>6s} {'Max DD':>7s}")
    print(f"  {'─'*50}")

    for rr in rr_vals:
        for tp1 in tp1_vals:
            config = build_config(direction="long", rr=rr, tp1_ratio=tp1)
            trades = run_backtest(df, config, start_date="2016-01-01", df_1m=df_1m)
            m = compute_metrics(trades)
            marker = " *" if m["win_rate"] >= 0.35 and m["total_r"] > 0 and m["sharpe_ratio"] > 1.0 else ""
            print(
                f"  {rr:>5.1f} {tp1:>5.2f} {m['total_trades']:>7d} {m['win_rate']:>5.1%} "
                f"{m['total_r']:>7.1f} {m['sharpe_ratio']:>7.3f} {m['profit_factor']:>6.2f} "
                f"{m['max_drawdown_r']:>7.1f}{marker}"
            )

    print("\n  (* = WR >= 35%, Net R > 0, Sharpe > 1.0)")
    print()


if __name__ == "__main__":
    main()
