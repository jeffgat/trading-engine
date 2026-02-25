#!/usr/bin/env python3
"""GC NY Continuation Longs — R3 Round 2 Variable Sweeps (post fill-bar fix).

R1 adopted: 5m ORB (Calmar +1.01), ATR 5 (Calmar +0.79).
Re-sweep all dimensions on updated anchor.

Anchor:
  rr=4.5, tp1=0.5, stop=3.0%, min_gap=3.5%, ATR 5
  5m ORB (09:30-09:35), entry→11:00, flat_start=15:50
  max_gap_points=25.0, max_gap_atr=30%
  Long-only, 1s magnifier, FOMC dates excluded

Sweeps each dimension independently:
  1. ORB window         — 5m*, 8m, 10m, 15m, 20m
  2. ATR length         — 3, 4, 5*, 6, 7, 8, 10, 12, 14
  3. entry_end          — 10:00, 10:30, 11:00*, 11:30, 12:00
  4. flat_start         — 13:00, 14:00, 14:30, 15:00, 15:30, 15:50*
  5. direction          — long*, both, short
  6. DOW exclusion      — none*, Mon, Tue, Wed, Thu, Fri, Mon+Fri, Thu+Fri
  7. max_gap_points     — 0(none), 15, 20, 25*, 30
  8. max_gap_atr_pct    — off, 15%, 20%, 25%, 30%*, 35%, 40%

Adoption rule: Calmar Δ > +0.3 AND no new negative years
*=anchor value
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

# ── Instrument ────────────────────────────────────────────────────────────────

GC = get_instrument("GC")
START_DATE = "2016-01-01"
END_DATE = "2026-02-19"
FULL_YEARS = [str(y) for y in range(2017, 2026)]

# ── Anchor config (R1 adopted: 5m ORB + ATR 5) ──────────────────────────────

GC_NY_ANCHOR = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",          # 5m ORB (adopted R1, was 10m)
    entry_start="09:35",
    entry_end="11:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,
    min_gap_atr_pct=3.5,
    max_gap_points=25.0,
    max_gap_atr_pct=30.0,
)

ANCHOR = StrategyConfig(
    rr=4.5,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=5,              # Adopted R1 (was 10)
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY_ANCHOR,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",) + FOMC_DATES,
)

# ── Globals ──────────────────────────────────────────────────────────────────

df = None
df_1m = None
df_1s = None

# ── Helpers ──────────────────────────────────────────────────────────────────


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


def row(label, m, anchor_calmar=None):
    calmar = m["calmar_ratio"]
    delta = f"  {calmar - anchor_calmar:>+7.2f}" if anchor_calmar is not None else ""
    return (
        f"  {label:<30s}"
        f"  {m['total_trades']:>6d}"
        f"  {m['win_rate']:>6.1%}"
        f"  {m['profit_factor']:>5.2f}"
        f"  {m['total_r']:>8.1f}"
        f"  {r_per_year(m):>7.1f}"
        f"  {m['max_drawdown_r']:>8.1f}"
        f"  {calmar:>7.2f}"
        f"  {m['sharpe_ratio']:>7.3f}"
        f"  {neg_years(m):>5d}"
        f"{delta}"
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
        f"  {'NegYr':>5s}"
        f"  {'  Delta':>7s}"
    )
    print("  " + "-" * 120)


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def make_session(**overrides):
    defaults = dict(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="11:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=3.0, min_gap_atr_pct=3.5,
        max_gap_points=25.0, max_gap_atr_pct=30.0,
    )
    defaults.update(overrides)
    return SessionConfig(**defaults)


# ── Sweep 1: ORB window ─────────────────────────────────────────────────────

def sweep_orb_window(anchor_calmar):
    section("SWEEP 1: ORB WINDOW")
    header()
    configs = [
        ("5m  09:30-09:35 [anchor]", "09:35", "09:35"),
        ("8m  09:30-09:38",  "09:38", "09:38"),
        ("10m 09:30-09:40",  "09:40", "09:40"),
        ("15m 09:30-09:45",  "09:45", "09:45"),
        ("20m 09:30-09:50",  "09:50", "09:50"),
    ]
    results = []
    for label, orb_end, entry_start in configs:
        sess = make_session(orb_end=orb_end, entry_start=entry_start)
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m, anchor_calmar))
        results.append((label, m))
    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")
    return results


# ── Sweep 2: ATR length (fine-grained around 5) ─────────────────────────────

def sweep_atr_length(anchor_calmar):
    section("SWEEP 2: ATR LENGTH (fine-grained around ATR 5)")
    header()
    lengths = [3, 4, 5, 6, 7, 8, 10, 12, 14]
    results = []
    for atr in lengths:
        label = f"ATR {atr}" + (" [anchor]" if atr == 5 else "")
        cfg = with_overrides(ANCHOR, atr_length=atr)
        m = run(cfg)
        print(row(label, m, anchor_calmar))
        results.append((label, m))
    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")
    return results


# ── Sweep 3: entry_end ──────────────────────────────────────────────────────

def sweep_entry_end(anchor_calmar):
    section("SWEEP 3: ENTRY END TIME")
    header()
    times = ["10:00", "10:30", "11:00", "11:30", "12:00"]
    results = []
    for t in times:
        label = f"entry_end={t}" + (" [anchor]" if t == "11:00" else "")
        sess = make_session(entry_end=t)
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m, anchor_calmar))
        results.append((label, m))
    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")
    return results


# ── Sweep 4: flat_start ─────────────────────────────────────────────────────

def sweep_flat_start(anchor_calmar):
    section("SWEEP 4: FLAT START TIME")
    header()
    times = ["13:00", "14:00", "14:30", "15:00", "15:30", "15:50"]
    results = []
    for t in times:
        label = f"flat_start={t}" + (" [anchor]" if t == "15:50" else "")
        sess = make_session(flat_start=t)
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m, anchor_calmar))
        results.append((label, m))
    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")
    return results


# ── Sweep 5: direction ──────────────────────────────────────────────────────

def sweep_direction(anchor_calmar):
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
        print(row(label, m, anchor_calmar))
        results.append((label, m))
    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")
    return results


# ── Sweep 6: DOW exclusion ──────────────────────────────────────────────────

def sweep_dow(anchor_calmar):
    section("SWEEP 6: DAY-OF-WEEK EXCLUSION")
    header()
    dow_configs = [
        ("none [anchor]",  set()),
        ("excl Monday",    {0}),
        ("excl Tuesday",   {1}),
        ("excl Wednesday", {2}),
        ("excl Thursday",  {3}),
        ("excl Friday",    {4}),
        ("excl Mon+Fri",   {0, 4}),
        ("excl Thu+Fri",   {3, 4}),
    ]
    results = []
    for label, excl in dow_configs:
        m = run(ANCHOR, excluded_dow=excl if excl else None)
        print(row(label, m, anchor_calmar))
        results.append((label, m))
    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")
    return results


# ── Sweep 7: max_gap_points ─────────────────────────────────────────────────

def sweep_max_gap_points(anchor_calmar):
    section("SWEEP 7: MAX GAP POINTS")
    header()
    values = [0, 15, 20, 25, 30]
    results = []
    for v in values:
        label = f"max_gap_pts={v}" + (" [anchor]" if v == 25 else "") + (" (no limit)" if v == 0 else "")
        sess = make_session(max_gap_points=float(v) if v > 0 else 0.0)
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m, anchor_calmar))
        results.append((label, m))
    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")
    return results


# ── Sweep 8: max_gap_atr_pct ────────────────────────────────────────────────

def sweep_max_gap_atr_pct(anchor_calmar):
    section("SWEEP 8: MAX GAP ATR %")
    header()
    values = [0.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0]
    results = []
    for v in values:
        label = (f"max_gap_atr={v:.0f}%" + (" [anchor]" if v == 30.0 else "")) if v > 0 else "off"
        sess = make_session(max_gap_atr_pct=v if v > 0 else 0.0)
        cfg = with_overrides(ANCHOR, sessions=(sess,))
        m = run(cfg)
        print(row(label, m, anchor_calmar))
        results.append((label, m))
    best_lbl, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best: {best_lbl} → Calmar {best_m['calmar_ratio']:.2f}")
    return results


# ── Summary ──────────────────────────────────────────────────────────────────

def print_anchor_metrics(m):
    section("ANCHOR METRICS (R1 adopted: 5m ORB + ATR 5)")
    print(f"  Config: stop=3.0% | rr=4.5 | min_gap=3.5% | tp1=0.5 | ATR 5")
    print(f"          5m ORB | entry→11:00 | long-only | FOMC excl | max_gap_atr=30% | 1s")
    print(f"  Changes from R1: ORB 10m→5m, ATR 10→5")
    print()
    print(f"  {'Metric':<20s} {'Value':>12s}")
    print(f"  {'-'*34}")
    print(f"  {'Trades':<20s} {m['total_trades']:>12d}")
    print(f"  {'Win Rate':<20s} {m['win_rate']:>11.1%}")
    print(f"  {'PF':<20s} {m['profit_factor']:>12.2f}")
    print(f"  {'Net R':<20s} {m['total_r']:>11.1f}R")
    print(f"  {'R/yr':<20s} {r_per_year(m):>11.1f}R")
    print(f"  {'Max DD':<20s} {m['max_drawdown_r']:>11.1f}R")
    print(f"  {'Calmar':<20s} {m['calmar_ratio']:>12.2f}")
    print(f"  {'Sharpe':<20s} {m['sharpe_ratio']:>12.3f}")
    print(f"  {'Neg years':<20s} {neg_years(m):>12d}")
    print()
    rby = m.get("r_by_year", {})
    if rby:
        print(f"  R by year:")
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY CONT LONGS — R3 VARIABLE SWEEPS Round 2 (post fill-bar fix)")
    print("  Anchor: stop=3.0% | rr=4.5 | min_gap=3.5% | tp1=0.5 | ATR 5")
    print("          5m ORB | entry→11:00 | FOMC excl | long-only | max_gap_atr=30%")
    print("  Changes from R1: ORB 10m→5m, ATR 10→5")
    print("=" * 70)

    print("\nLoading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars")
    print(f"  1m: {len(df_1m):,} bars")
    print(f"  1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    t_total = time.time()
    anchor_m = run(ANCHOR)
    anchor_calmar = anchor_m["calmar_ratio"]
    print_anchor_metrics(anchor_m)

    sweep_orb_window(anchor_calmar)
    sweep_atr_length(anchor_calmar)
    sweep_entry_end(anchor_calmar)
    sweep_flat_start(anchor_calmar)
    sweep_direction(anchor_calmar)
    sweep_dow(anchor_calmar)
    sweep_max_gap_points(anchor_calmar)
    sweep_max_gap_atr_pct(anchor_calmar)

    total_time = time.time() - t_total
    print()
    print("=" * 70)
    print(f"  COMPLETE — Total time: {total_time:.0f}s")
    print("  Review each sweep. Adopt if Calmar Δ > +0.3 AND no new neg years.")
    print("  If anchor changes, re-run sweeps on new anchor (R3 sweeps_3).")
    print("=" * 70)
    print()
