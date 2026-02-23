#!/usr/bin/env python3
"""GC NY Continuation Longs — Round 1 Config Variable Sweep.

Anchor config (best-Calmar from initial exploration):
  stop=4% ATR, min_gap=1%, rr=3.0, tp1=0.3, entry_end=12:00
  5m ORB (09:30-09:35), long-only, ATR 50, flat_start=15:50

Sweeps each config dimension independently (all others held at anchor):
  1. ORB window       — 5m, 10m, 15m, 20m
  2. ATR length       — 10, 14, 20, 30, 50*, 75
  3. entry_end        — 10:00 → 15:00 (9 values)
  4. flat_start       — 14:30 → 15:55 (7 values)
  5. direction        — long*, both, short
  6. DOW exclusion    — none*, Mon, Tue, Wed, Thu, Fri, Mon+Fri, Thu+Fri
  7. max_gap_points   — 0 (no limit), 10, 15, 20, 25*, 30, 40

Scoring: Calmar ratio (primary), then Sharpe.
*=anchor value
"""

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Instrument ────────────────────────────────────────────────────────────────

GC = get_instrument("GC")
START_DATE = "2016-01-01"
END_DATE = "2026-02-15"

# ── Anchor config ─────────────────────────────────────────────────────────────

GC_NY_ANCHOR = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",          # 5-min ORB (anchor)
    entry_start="09:35",
    entry_end="12:00",        # Cap at noon (anchor)
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=4.0,
    min_gap_atr_pct=1.0,
)

ANCHOR = StrategyConfig(
    rr=3.0,
    tp1_ratio=0.3,
    risk_usd=5000.0,
    atr_length=50,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY_ANCHOR,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

# ── Helpers ───────────────────────────────────────────────────────────────────

FULL_YEARS = [str(y) for y in range(2016, 2026)]  # 10 full years


def run(cfg, start=START_DATE, end=END_DATE, excluded_dow=None):
    """Run backtest, optionally filter by DOW, return metrics."""
    trades = run_backtest(df, cfg, start_date=start, df_1m=df_1m)
    if excluded_dow:
        trades = [
            t for t in trades
            if t.exit_type == EXIT_NO_FILL
            or datetime.strptime(t.date, "%Y-%m-%d").weekday() not in excluded_dow
        ]
    return compute_metrics(trades)


def r_per_year(m):
    """Average R per full calendar year from r_by_year metric."""
    rby = m.get("r_by_year", {})
    if not rby:
        return 0.0
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def row(label, m):
    rpy = r_per_year(m)
    dd = m["max_drawdown_r"]
    calmar = m["calmar_ratio"]
    neg = neg_years(m)
    return (
        f"  {label:<30s}"
        f"  {m['total_trades']:>6d}"
        f"  {m['win_rate']:>6.1%}"
        f"  {m['profit_factor']:>5.2f}"
        f"  {m['total_r']:>8.1f}"
        f"  {rpy:>7.1f}"
        f"  {dd:>8.1f}"
        f"  {calmar:>7.2f}"
        f"  {m['sharpe_ratio']:>7.3f}"
        f"  {m['avg_r']:>7.3f}"
        f"  {neg:>5d}"
    )


def header():
    print(
        f"  {'Config':<30s}"
        f"  {'Trades':>6s}"
        f"  {'  WR':>6s}"
        f"  {'   PF':>5s}"
        f"  {'  Net R':>8s}"
        f"  {' R/yr':>7s}"
        f"  {' Max DD':>8s}"
        f"  {'Calmar':>7s}"
        f"  {' Sharpe':>7s}"
        f"  {'R/trd':>7s}"
        f"  {'NegYr':>5s}"
    )
    print("  " + "-" * 110)


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def best_label(configs, metrics_list, key="calmar_ratio"):
    best_idx = max(range(len(metrics_list)), key=lambda i: metrics_list[i][key])
    return configs[best_idx], metrics_list[best_idx]


# ── Sweep 1: ORB window ───────────────────────────────────────────────────────

def sweep_orb_window():
    section("SWEEP 1: ORB WINDOW")
    header()

    configs = [
        ("5m  09:30-09:35 [anchor]", "09:35", "09:35"),
        ("10m 09:30-09:40",           "09:40", "09:40"),
        ("15m 09:30-09:45",           "09:45", "09:45"),
        ("20m 09:30-09:50",           "09:50", "09:50"),
        ("30m 09:30-10:00",           "10:00", "10:00"),
    ]

    results = []
    for label, orb_end, entry_start in configs:
        sess = SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end=orb_end,
            entry_start=entry_start,
            entry_end="12:00",
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=4.0,
            min_gap_atr_pct=1.0,
        )
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m))
        results.append((label, m))

    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")


# ── Sweep 2: ATR length ───────────────────────────────────────────────────────

def sweep_atr_length():
    section("SWEEP 2: ATR LENGTH")
    header()

    lengths = [10, 14, 20, 30, 50, 75]
    results = []
    for atr in lengths:
        label = f"ATR {atr}" + (" [anchor]" if atr == 50 else "")
        cfg = with_overrides(ANCHOR, atr_length=atr)
        m = run(cfg)
        print(row(label, m))
        results.append((label, m))

    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")


# ── Sweep 3: entry_end ────────────────────────────────────────────────────────

def sweep_entry_end():
    section("SWEEP 3: ENTRY END TIME")
    header()

    times = [
        "10:00", "10:30", "11:00", "11:30",
        "12:00",  # anchor
        "12:30", "13:00", "14:00", "15:00",
    ]
    results = []
    for t in times:
        label = f"entry_end={t}" + (" [anchor]" if t == "12:00" else "")
        sess = SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end="09:35",
            entry_start="09:35",
            entry_end=t,
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=4.0,
            min_gap_atr_pct=1.0,
        )
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m))
        results.append((label, m))

    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")


# ── Sweep 4: flat_start ───────────────────────────────────────────────────────

def sweep_flat_start():
    section("SWEEP 4: FLAT START TIME")
    header()

    times = ["14:30", "15:00", "15:15", "15:30", "15:40", "15:50", "15:55"]
    results = []
    for t in times:
        label = f"flat_start={t}" + (" [anchor]" if t == "15:50" else "")
        sess = SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end="09:35",
            entry_start="09:35",
            entry_end="12:00",
            flat_start=t,
            flat_end="16:00",
            stop_atr_pct=4.0,
            min_gap_atr_pct=1.0,
        )
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m))
        results.append((label, m))

    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")


# ── Sweep 5: direction ────────────────────────────────────────────────────────

def sweep_direction():
    section("SWEEP 5: DIRECTION FILTER")
    header()

    directions = [
        ("long [anchor]", "long"),
        ("both",          "both"),
        ("short",         "short"),
    ]
    results = []
    for label, d in directions:
        cfg = with_overrides(ANCHOR, direction_filter=d)
        m = run(cfg)
        print(row(label, m))
        results.append((label, m))

    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")


# ── Sweep 6: DOW exclusion ────────────────────────────────────────────────────

def sweep_dow():
    section("SWEEP 6: DAY-OF-WEEK EXCLUSION")
    header()

    # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
    dow_configs = [
        ("none [anchor]",  set()),
        ("excl Monday",    {0}),
        ("excl Tuesday",   {1}),
        ("excl Wednesday", {2}),
        ("excl Thursday",  {3}),
        ("excl Friday",    {4}),
        ("excl Mon+Fri",   {0, 4}),
        ("excl Thu+Fri",   {3, 4}),
        ("excl Mon+Thu",   {0, 3}),
    ]
    results = []
    for label, excl in dow_configs:
        m = run(ANCHOR, excluded_dow=excl if excl else None)
        print(row(label, m))
        results.append((label, m))

    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")


# ── Sweep 7: max_gap_points ───────────────────────────────────────────────────

def sweep_max_gap_points():
    section("SWEEP 7: MAX GAP POINTS")
    header()

    values = [0, 10, 15, 20, 25, 30, 40, 50]
    results = []
    for v in values:
        label = f"max_gap_pts={v}" + (" [anchor]" if v == 25 else "") + (" (no limit)" if v == 0 else "")
        sess = SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end="09:35",
            entry_start="09:35",
            entry_end="12:00",
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=4.0,
            min_gap_atr_pct=1.0,
        )
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m))
        results.append((label, m))

    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(anchor_m):
    section("SUMMARY — ANCHOR METRICS")
    print(f"  Anchor: stop=4% | min_gap=1% | rr=3.0 | tp1=0.3 | entry→12:00 | 5m ORB | long | ATR 50")
    print()
    print(f"  {'Metric':<20s} {'Value':>12s}")
    print(f"  {'-'*34}")
    print(f"  {'Trades':<20s} {anchor_m['total_trades']:>12d}")
    print(f"  {'Win Rate':<20s} {anchor_m['win_rate']:>11.1%}")
    print(f"  {'PF':<20s} {anchor_m['profit_factor']:>12.2f}")
    print(f"  {'Net R':<20s} {anchor_m['total_r']:>11.1f}R")
    print(f"  {'R/yr':<20s} {r_per_year(anchor_m):>11.1f}R")
    print(f"  {'Max DD':<20s} {anchor_m['max_drawdown_r']:>11.1f}R")
    print(f"  {'Calmar':<20s} {anchor_m['calmar_ratio']:>12.2f}")
    print(f"  {'Sharpe':<20s} {anchor_m['sharpe_ratio']:>12.3f}")
    print(f"  {'Neg full years':<20s} {neg_years(anchor_m):>12d}")
    print()
    rby = anchor_m.get("r_by_year", {})
    if rby:
        print(f"  R by year:")
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY CONTINUATION LONGS — ROUND 1 CONFIG VARIABLE SWEEP")
    print("  Anchor: stop=4% | min_gap=1% | rr=3.0 | tp1=0.3 | entry→12:00")
    print("          5m ORB | long-only | ATR 50 | flat_start=15:50")
    print("=" * 70)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})")
    print(f"  1m: {len(df_1m):,} bars")

    # Run anchor once for summary
    anchor_m = run(ANCHOR)
    print_summary(anchor_m)

    sweep_orb_window()
    sweep_atr_length()
    sweep_entry_end()
    sweep_flat_start()
    sweep_direction()
    sweep_dow()
    sweep_max_gap_points()

    print()
    print("=" * 70)
    print("  DONE — Review each sweep for the best Calmar value.")
    print("  Next: anchor on best values, run Round 2 grid sweep (stop × rr × tp1).")
    print("=" * 70)
    print()
