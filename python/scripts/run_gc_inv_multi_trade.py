#!/usr/bin/env python3
"""Test allowing 2 trades per day on GC Inversion Longs v8.

Approach: use two sessions sharing the same ORB but with separate entry
windows. Each session gets its own "one trade per day" slot, so up to 2
trades per day fire if signals appear in both windows.

Tests:
  1. Baseline: single session (1 trade/day max)
  2. Split at 11:00 (AM: 09:35-10:59, PM: 11:00-15:00)
  3. Split at 10:30 (AM: 09:35-10:29, PM: 10:30-15:00)
  4. Split at 10:00 (AM: 09:35-09:59, PM: 10:00-15:00)
  5. AM-only (09:35-10:59) — isolate weak morning
  6. PM-only (11:00-15:00) — isolate strong afternoon
  7. PM-only (10:00-15:00) — wider afternoon window
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


def make_session(name, entry_start, entry_end,
                 orb_start="09:30", orb_end="09:35"):
    return SessionConfig(
        name=name,
        orb_start=orb_start,
        orb_end=orb_end,
        entry_start=entry_start,
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=1.0,
        max_gap_points=25.0,
    )


def build_config(sessions):
    if not isinstance(sessions, (list, tuple)):
        sessions = (sessions,)
    return StrategyConfig(
        rr=3.5,
        tp1_ratio=0.2,
        risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0,
        qty_step=1.0,
        sessions=tuple(sessions),
        instrument=GC,
        strategy="inversion",
        direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS,
        excluded_dates=EXCLUDED,
    )


def print_metrics(label, m, trades=None):
    from orb_backtest.engine.simulator import EXIT_NO_FILL
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL] if trades else []

    # Count days with 2 trades
    from collections import Counter
    day_counts = Counter(t.date for t in filled)
    two_trade_days = sum(1 for c in day_counts.values() if c >= 2)

    print(f"\n  {label}")
    print(f"  {'─'*65}")
    print(f"  Trades:  {m['total_trades']:>6d}     Win Rate: {m['win_rate']:>6.1%}")
    print(f"  Net R:   {m['total_r']:>6.1f}R     Avg R:    {m['avg_r']:>6.3f}R")
    print(f"  Sharpe:  {m['sharpe_ratio']:>6.3f}     PF:       {m['profit_factor']:>6.2f}")
    print(f"  Max DD:  {m['max_drawdown_r']:>6.1f}R     Calmar:   {m['calmar_ratio']:>6.2f}")
    if trades:
        print(f"  Days w/ 2 trades: {two_trade_days}  ({two_trade_days}/{len(day_counts)} = {two_trade_days/max(len(day_counts),1):.0%})")


def main():
    print("=" * 70)
    print("  GC Inversion Longs v8 — Multi-Trade Per Day Test")
    print("=" * 70)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    # ── Test 1: Baseline (1 trade/day) ───────────────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 1: Baseline — Single session, 1 trade/day max")
    print("─" * 70)
    s_full = make_session("NY", "09:35", "15:00")
    config = build_config(s_full)
    t0 = time.time()
    trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
    m = compute_metrics(trades)
    print_metrics("Baseline (09:35-15:00, 1/day)", m, trades)
    print(f"  ({time.time() - t0:.1f}s)")

    # ── Test 2: Split at 11:00 (2 trades/day) ───────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 2: Split at 11:00 — AM (09:35-10:59) + PM (11:00-15:00)")
    print("─" * 70)
    s_am = make_session("NY_AM", "09:35", "10:59")
    s_pm = make_session("NY_PM", "11:00", "15:00")
    config = build_config([s_am, s_pm])
    t0 = time.time()
    trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
    m = compute_metrics(trades)
    print_metrics("Split 11:00 (2/day max)", m, trades)
    print(f"  ({time.time() - t0:.1f}s)")

    # ── Test 3: Split at 10:30 ──────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 3: Split at 10:30 — AM (09:35-10:29) + PM (10:30-15:00)")
    print("─" * 70)
    s_am = make_session("NY_AM", "09:35", "10:29")
    s_pm = make_session("NY_PM", "10:30", "15:00")
    config = build_config([s_am, s_pm])
    t0 = time.time()
    trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
    m = compute_metrics(trades)
    print_metrics("Split 10:30 (2/day max)", m, trades)
    print(f"  ({time.time() - t0:.1f}s)")

    # ── Test 4: Split at 10:00 ──────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 4: Split at 10:00 — AM (09:35-09:59) + PM (10:00-15:00)")
    print("─" * 70)
    s_am = make_session("NY_AM", "09:35", "09:59")
    s_pm = make_session("NY_PM", "10:00", "15:00")
    config = build_config([s_am, s_pm])
    t0 = time.time()
    trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
    m = compute_metrics(trades)
    print_metrics("Split 10:00 (2/day max)", m, trades)
    print(f"  ({time.time() - t0:.1f}s)")

    # ── Test 5: AM-only ─────────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 5: AM-Only (09:35-10:59)")
    print("─" * 70)
    s_am = make_session("NY", "09:35", "10:59")
    config = build_config(s_am)
    t0 = time.time()
    trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
    m = compute_metrics(trades)
    print_metrics("AM-only (09:35-10:59)", m, trades)
    print(f"  ({time.time() - t0:.1f}s)")

    # ── Test 6: PM-only (11:00+) ────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 6: PM-Only (11:00-15:00)")
    print("─" * 70)
    s_pm = make_session("NY", "11:00", "15:00")
    config = build_config(s_pm)
    t0 = time.time()
    trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
    m = compute_metrics(trades)
    print_metrics("PM-only (11:00-15:00)", m, trades)
    print(f"  ({time.time() - t0:.1f}s)")

    # ── Test 7: PM-only wider (10:00+) ──────────────────────────────────
    print("\n" + "─" * 70)
    print("  TEST 7: PM-Only wider (10:00-15:00)")
    print("─" * 70)
    s_pm = make_session("NY", "10:00", "15:00")
    config = build_config(s_pm)
    t0 = time.time()
    trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
    m = compute_metrics(trades)
    print_metrics("PM-only (10:00-15:00)", m, trades)
    print(f"  ({time.time() - t0:.1f}s)")

    # ── Summary table ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Config':>30s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Sharpe':>7s} {'PF':>6s} {'Max DD':>7s}")
    print(f"  {'─'*70}")

    configs = [
        ("Baseline (1/day)", s_full, False),
        ("Split 11:00 (2/day)", [make_session("NY_AM", "09:35", "10:59"),
                                  make_session("NY_PM", "11:00", "15:00")], False),
        ("Split 10:30 (2/day)", [make_session("NY_AM", "09:35", "10:29"),
                                  make_session("NY_PM", "10:30", "15:00")], False),
        ("Split 10:00 (2/day)", [make_session("NY_AM", "09:35", "09:59"),
                                  make_session("NY_PM", "10:00", "15:00")], False),
        ("AM-only (09:35-10:59)", make_session("NY", "09:35", "10:59"), False),
        ("PM-only (11:00-15:00)", make_session("NY", "11:00", "15:00"), False),
        ("PM-only (10:00-15:00)", make_session("NY", "10:00", "15:00"), False),
    ]

    for label, sess, _ in configs:
        config = build_config(sess if isinstance(sess, list) else sess)
        trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
        m = compute_metrics(trades)
        print(
            f"  {label:>30s} {m['total_trades']:>7d} {m['win_rate']:>5.1%} "
            f"{m['total_r']:>7.1f} {m['sharpe_ratio']:>7.3f} {m['profit_factor']:>6.2f} "
            f"{m['max_drawdown_r']:>7.1f}"
        )

    print()


if __name__ == "__main__":
    main()
