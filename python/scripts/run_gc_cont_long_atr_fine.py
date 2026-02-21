#!/usr/bin/env python3
"""GC NY Continuation Longs — ATR Length Fine-Tune (1s magnifier).

Round 2 variable sweeps revealed ATR length is the dominant lever:
  ATR 10 → Calmar 8.02 (vs ATR 50 → Calmar 2.26)

This script sweeps ATR 7-25 at fine resolution to find the optimum.
Also sweeps ORB window (5m, 8m, 10m, 12m, 15m) to confirm 10m finding.

Anchor: stop=4.5%, min_gap=2.5%, rr=4.0, tp1=0.5, 10m ORB, long, entry→12:00
"""

import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
START_DATE = "2016-01-01"
END_DATE = "2026-02-15"
FULL_YEARS = [str(y) for y in range(2016, 2026)]

# Anchor uses 10m ORB (Round 2 winner) + ATR 10 (Round 2 winner)
GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:40",      # 10m ORB (Round 2 winner)
    entry_start="09:40",
    entry_end="12:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=4.5,
    min_gap_atr_pct=2.5,
    max_gap_points=25.0,
)

ANCHOR = StrategyConfig(
    rr=4.0,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=10,        # Round 2 winner
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

df = None
df_1m = None
df_1s = None


def run(cfg):
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    return compute_metrics(trades)


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def row(label, m):
    return (
        f"  {label:<32s}"
        f"  {m['total_trades']:>6d}"
        f"  {m['win_rate']:>6.1%}"
        f"  {m['profit_factor']:>5.2f}"
        f"  {m['total_r']:>8.1f}"
        f"  {r_per_year(m):>7.1f}"
        f"  {m['max_drawdown_r']:>8.1f}"
        f"  {m['calmar_ratio']:>7.2f}"
        f"  {m['sharpe_ratio']:>7.3f}"
        f"  {neg_years(m):>5d}"
    )


def header():
    print(
        f"  {'Config':<32s}"
        f"  {'Trades':>6s}"
        f"  {'  WR':>6s}"
        f"  {'   PF':>5s}"
        f"  {'  Net R':>8s}"
        f"  {' R/yr':>7s}"
        f"  {' Max DD':>8s}"
        f"  {'Calmar':>7s}"
        f"  {' Sharpe':>7s}"
        f"  {'NegYr':>5s}"
    )
    print("  " + "-" * 112)


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def best_of(results):
    lbl, m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {lbl} → Calmar {m['calmar_ratio']:.2f}, Sharpe {m['sharpe_ratio']:.3f}, Net R {m['total_r']:.1f}R, DD {m['max_drawdown_r']:.1f}R")
    return lbl, m


def sweep_atr_fine():
    section("SWEEP: ATR LENGTH FINE-TUNE (7 to 25)")
    print("  Base: 10m ORB, stop=4.5%, min_gap=2.5%, rr=4.0, tp1=0.5, long, entry→12:00")
    header()

    lengths = [5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 25, 30]
    results = []
    for atr in lengths:
        label = f"ATR {atr}" + (" [anchor]" if atr == 10 else "")
        m = run(with_overrides(ANCHOR, atr_length=atr))
        print(row(label, m))
        results.append((label, m))

    print()
    return best_of(results)


def sweep_orb_fine():
    section("SWEEP: ORB WINDOW FINE-TUNE (5m to 15m)")
    print("  Base: ATR 10, stop=4.5%, min_gap=2.5%, rr=4.0, tp1=0.5, long, entry→12:00")
    header()

    orb_configs = [
        ("5m  09:30-09:35",           "09:35", "09:35"),
        ("8m  09:30-09:38",           "09:38", "09:38"),
        ("10m 09:30-09:40 [anchor]",  "09:40", "09:40"),
        ("12m 09:30-09:42",           "09:42", "09:42"),
        ("15m 09:30-09:45",           "09:45", "09:45"),
    ]

    results = []
    for label, orb_end, entry_start in orb_configs:
        sess = SessionConfig(
            name="NY", orb_start="09:30", orb_end=orb_end,
            entry_start=entry_start, entry_end="12:00",
            flat_start="15:50", flat_end="16:00",
            stop_atr_pct=4.5, min_gap_atr_pct=2.5, max_gap_points=25.0,
        )
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m))
        results.append((label, m))

    print()
    return best_of(results)


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY CONT LONGS — ATR FINE-TUNE (1s magnifier)")
    print("  Base: 10m ORB, stop=4.5%, min_gap=2.5%, rr=4.0, tp1=0.5")
    print("  Round 2 winner: ATR 10 (Calmar 8.02)")
    print("=" * 70)

    print("\nLoading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars | 1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    best_atr_label, best_atr_m = sweep_atr_fine()
    best_orb_label, best_orb_m = sweep_orb_fine()

    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Best ATR:      {best_atr_label} → Calmar {best_atr_m['calmar_ratio']:.2f}")
    print(f"  Best ORB:      {best_orb_label} → Calmar {best_orb_m['calmar_ratio']:.2f}")
    print()
    print("  Next: run grid sweep with winning ATR + ORB combination.")
    print("=" * 70)
    print()
