#!/usr/bin/env python3
"""GC NY — DOW sweep with FOMC dates excluded (quick anchor check).

Anchor: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 16, 10m ORB, entry→11:00
+ FOMC dates excluded via excluded_dates

Question: does Wednesday exclusion still show meaningful benefit
once FOMC days are already removed?
"""

import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30", orb_end="09:40",
    entry_start="09:40", entry_end="11:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=4.0, min_gap_atr_pct=2.5, max_gap_points=25.0,
)

# Anchor now includes FOMC exclusion
ANCHOR = StrategyConfig(
    rr=4.5, tp1_ratio=0.5, risk_usd=5000.0, atr_length=16,
    min_qty=1.0, qty_step=1.0,
    sessions=(GC_NY,), instrument=GC,
    strategy="continuation", direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",) + FOMC_DATES,  # FOMC now baked in
)

df = df_1m = df_1s = None


def run(cfg, excluded_dow=None):
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    if excluded_dow:
        trades = [
            t for t in trades
            if t.exit_type == EXIT_NO_FILL
            or datetime.strptime(t.date, "%Y-%m-%d").weekday() not in excluded_dow
        ]
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


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY — DOW SWEEP WITH FOMC EXCLUDED (anchor check)")
    print("  Anchor: stop=4.0% | rr=4.5 | min_gap=2.5% | tp1=0.5 | ATR 16 | 10m ORB")
    print("  entry→11:00 | FOMC dates excluded")
    print("=" * 70)

    print("\nLoading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    print("\nRunning anchor (FOMC excluded)...")
    t0 = time.time()
    anchor_m = run(ANCHOR)
    print(f"  Done in {time.time() - t0:.1f}s")
    print(f"  Anchor: {anchor_m['total_trades']} trades, Calmar {anchor_m['calmar_ratio']:.2f}, "
          f"Sharpe {anchor_m['sharpe_ratio']:.3f}, DD {anchor_m['max_drawdown_r']:.1f}R, "
          f"NegYr {neg_years(anchor_m)}")

    print()
    print("=" * 70)
    print("  DOW SWEEP (FOMC already excluded from anchor)")
    print("=" * 70)
    header()

    dow_configs = [
        ("none [anchor]",  None),
        ("excl Monday",    {0}),
        ("excl Tuesday",   {1}),
        ("excl Wednesday", {2}),
        ("excl Thursday",  {3}),
        ("excl Friday",    {4}),
        ("excl Mon+Fri",   {0, 4}),
        ("excl Thu+Fri",   {3, 4}),
        ("excl Mon+Thu",   {0, 3}),
        ("excl Tue+Thu",   {1, 3}),
    ]

    results = []
    for label, excl in dow_configs:
        m = run(ANCHOR, excluded_dow=excl)
        print(row(label, m))
        results.append((label, m))

    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    anchor_calmar = results[0][1]["calmar_ratio"]

    print()
    print(f"  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f} "
          f"(Δ {best_m['calmar_ratio'] - anchor_calmar:+.2f} vs anchor)")
    print()
    print("  If best Calmar - anchor < 0.3 → DOW is clean, proceed to grid sweep.")
    print("  If any DOW still > 0.3 above anchor → investigate further.")
    print()

    # R by year for anchor
    print("  Anchor R by year (FOMC excluded):")
    rby = anchor_m.get("r_by_year", {})
    for y in sorted(rby):
        flag = " <--" if rby[y] < 0 else ""
        print(f"    {y}: {rby[y]:>8.1f}R{flag}")
    print()
