#!/usr/bin/env python3
"""GC Inversion Longs v9 candidate — combo test.

Tests the two most promising filters from the v8 sweeps:
  1. 10% qualifying sweep depth (ATR-based)
  2. Friday exclusion

Tests each independently and combined, against the v8 baseline.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED_BASE = ("20241218",)
START = "2016-01-01"


def build_session(qualifying_move_atr_pct=0.0):
    return SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=1.0,
        qualifying_move_atr_pct=qualifying_move_atr_pct,
    )


def build_config(qualifying_move_atr_pct=0.0, exclude_fridays=False):
    session = build_session(qualifying_move_atr_pct=qualifying_move_atr_pct)
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
        excluded_dates=EXCLUDED_BASE,
    ), exclude_fridays


def run_test(df, df_1m, config, exclude_fridays=False):
    """Run backtest, optionally filtering out Friday trades post-hoc."""
    qm_pct = config.sessions[0].qualifying_move_atr_pct
    if qm_pct > 0:
        trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)
    else:
        trades = run_backtest(df, config, start_date=START, df_1m=df_1m)

    if exclude_fridays:
        trades = [
            t for t in trades
            if t.exit_type == EXIT_NO_FILL
            or datetime.strptime(t.date, "%Y-%m-%d").weekday() != 4  # 4 = Friday
        ]

    return trades


def print_full_metrics(label, trades):
    m = compute_metrics(trades)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    print(f"\n  {label}")
    print(f"  {'─'*60}")
    print(f"  Trades:  {m['total_trades']:>6d}     Win Rate: {m['win_rate']:>6.1%}")
    print(f"  Net R:   {m['total_r']:>6.1f}R     Avg R:    {m['avg_r']:>6.3f}R")
    print(f"  Sharpe:  {m['sharpe_ratio']:>6.3f}     PF:       {m['profit_factor']:>6.2f}")
    print(f"  Max DD:  {m['max_drawdown_r']:>6.1f}R     Calmar:   {m['calmar_ratio']:>6.2f}")

    # Yearly breakdown
    from collections import defaultdict
    yearly = defaultdict(lambda: {"r": 0.0, "trades": 0, "wins": 0})
    for t in filled:
        year = t.date[:4]
        yearly[year]["r"] += t.r_multiple
        yearly[year]["trades"] += 1
        if t.r_multiple > 0:
            yearly[year]["wins"] += 1

    print(f"\n  {'Year':>6s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s}")
    print(f"  {'─'*30}")
    for year in sorted(yearly):
        y = yearly[year]
        wr = y["wins"] / y["trades"] if y["trades"] > 0 else 0
        print(f"  {year:>6s} {y['trades']:>7d} {wr:>5.1%} {y['r']:>7.1f}")

    return m


def main():
    print("=" * 70)
    print("  GC Inversion Longs — v9 Combo Test")
    print("  Filters: 10% qualifying sweep + Friday exclusion")
    print("=" * 70)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    # ── A: v8 Baseline ──────────────────────────────────────────────────
    print("\n" + "═" * 70)
    config, _ = build_config(qualifying_move_atr_pct=0.0, exclude_fridays=False)
    trades_a = run_test(df, df_1m, config, exclude_fridays=False)
    m_a = print_full_metrics("A) v8 Baseline (no filters)", trades_a)

    # ── B: 10% qualifying sweep only ────────────────────────────────────
    print("\n" + "═" * 70)
    config, _ = build_config(qualifying_move_atr_pct=10.0, exclude_fridays=False)
    trades_b = run_test(df, df_1m, config, exclude_fridays=False)
    m_b = print_full_metrics("B) + 10% Qualifying Sweep", trades_b)

    # ── C: Friday exclusion only ────────────────────────────────────────
    print("\n" + "═" * 70)
    config, _ = build_config(qualifying_move_atr_pct=0.0, exclude_fridays=True)
    trades_c = run_test(df, df_1m, config, exclude_fridays=True)
    m_c = print_full_metrics("C) + Friday Exclusion", trades_c)

    # ── D: Both filters combined ────────────────────────────────────────
    print("\n" + "═" * 70)
    config, _ = build_config(qualifying_move_atr_pct=10.0, exclude_fridays=True)
    trades_d = run_test(df, df_1m, config, exclude_fridays=True)
    m_d = print_full_metrics("D) + 10% QM + Friday Exclusion (v9 candidate)", trades_d)

    # ── Summary ─────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  SUMMARY")
    print("═" * 70)
    print(f"  {'Config':>35s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Sharpe':>7s} {'PF':>6s} {'Max DD':>7s}")
    print(f"  {'─'*75}")
    for label, m in [
        ("A) v8 Baseline", m_a),
        ("B) + 10% QM", m_b),
        ("C) + No Fridays", m_c),
        ("D) + 10% QM + No Fridays", m_d),
    ]:
        print(
            f"  {label:>35s} {m['total_trades']:>7d} {m['win_rate']:>5.1%} "
            f"{m['total_r']:>7.1f} {m['sharpe_ratio']:>7.3f} {m['profit_factor']:>6.2f} "
            f"{m['max_drawdown_r']:>7.1f}"
        )

    print()


if __name__ == "__main__":
    main()
