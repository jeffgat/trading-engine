#!/usr/bin/env python3
"""GC NY Continuation Longs — Round 5 Variable Sweep (1s magnifier).

Anchor config (Round 4 adopted ATR 16):
  stop=4.0% ATR, min_gap=2.5%, rr=4.5, tp1=0.5
  ATR 16, 10m ORB (09:30-09:40), entry→11:00, flat_start=15:50, long-only

Sweeps each config dimension independently (all others held at anchor):
  1. ORB window       — 5m, 8m, 10m*, 12m, 15m
  2. ATR length       — 12, 13, 14, 15, 16*, 17, 18, 19, 20, 22
  3. entry_end        — 10:00 → 15:00 (9 values)
  4. flat_start       — 14:30 → 15:55 (7 values)
  5. direction        — long*, both, short
  6. DOW exclusion    — none*, Mon, Tue, Wed, Thu, Fri, Mon+Fri, Thu+Fri, Mon+Thu, Tue+Thu
  7. max_gap_points   — 0 (no limit), 10, 15, 20, 25*, 30, 40, 50
  8. max_gap_atr_pct  — 0* (disabled), 5, 8, 10, 15, 20, 25, 30

*=anchor value
Scoring: Calmar ratio (primary), then Sharpe.
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

# ── Anchor: Round 4 winner (ATR changed 14 → 16) ─────────────────────────────

GC_NY_ANCHOR = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:40",      # 10m ORB
    entry_start="09:40",
    entry_end="11:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=4.0,
    min_gap_atr_pct=2.5,
    max_gap_points=25.0,
)

ANCHOR = StrategyConfig(
    rr=4.5,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=16,        # ADOPTED from Round 4 (+0.43 Calmar)
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

# ── Module-level data (set in main) ──────────────────────────────────────────

df = None
df_1m = None
df_1s = None


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def best_of(results):
    lbl, m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {lbl} → Calmar {m['calmar_ratio']:.2f}, "
          f"Sharpe {m['sharpe_ratio']:.3f}, Net R {m['total_r']:.1f}R, "
          f"DD {m['max_drawdown_r']:.1f}R, NegYr {neg_years(m)}")
    return lbl, m


def make_sess(orb_end="09:40", entry_start="09:40", entry_end="11:00",
              flat_start="15:50", stop=4.0, min_gap=2.5, max_gap_pts=25.0,
              max_gap_atr=0.0):
    return SessionConfig(
        name="NY", orb_start="09:30", orb_end=orb_end,
        entry_start=entry_start, entry_end=entry_end,
        flat_start=flat_start, flat_end="16:00",
        stop_atr_pct=stop, min_gap_atr_pct=min_gap,
        max_gap_points=max_gap_pts, max_gap_atr_pct=max_gap_atr,
    )


# ── Sweep 1: ORB window ───────────────────────────────────────────────────────

def sweep_orb_window():
    section("SWEEP 1: ORB WINDOW")
    header()
    configs = [
        ("5m  09:30-09:35",           "09:35", "09:35"),
        ("8m  09:30-09:38",           "09:38", "09:38"),
        ("10m 09:30-09:40 [anchor]",  "09:40", "09:40"),
        ("12m 09:30-09:42",           "09:42", "09:42"),
        ("15m 09:30-09:45",           "09:45", "09:45"),
    ]
    results = []
    for label, orb_end, entry_start in configs:
        m = run(with_overrides(ANCHOR, sessions=(make_sess(orb_end=orb_end, entry_start=entry_start),)))
        print(row(label, m))
        results.append((label, m))
    return best_of(results)


# ── Sweep 2: ATR length ───────────────────────────────────────────────────────

def sweep_atr_length():
    section("SWEEP 2: ATR LENGTH (fine resolution around 16)")
    header()
    results = []
    for atr in [12, 13, 14, 15, 16, 17, 18, 19, 20, 22]:
        label = f"ATR {atr}" + (" [anchor]" if atr == 16 else "")
        m = run(with_overrides(ANCHOR, atr_length=atr))
        print(row(label, m))
        results.append((label, m))
    return best_of(results)


# ── Sweep 3: entry_end ────────────────────────────────────────────────────────

def sweep_entry_end():
    section("SWEEP 3: ENTRY END TIME")
    header()
    times = ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "14:00", "15:00"]
    results = []
    for t in times:
        label = f"entry_end={t}" + (" [anchor]" if t == "11:00" else "")
        m = run(with_overrides(ANCHOR, sessions=(make_sess(entry_end=t),)))
        print(row(label, m))
        results.append((label, m))
    return best_of(results)


# ── Sweep 4: flat_start ───────────────────────────────────────────────────────

def sweep_flat_start():
    section("SWEEP 4: FLAT START TIME")
    header()
    times = ["14:30", "15:00", "15:15", "15:30", "15:40", "15:50", "15:55"]
    results = []
    for t in times:
        label = f"flat_start={t}" + (" [anchor]" if t == "15:50" else "")
        m = run(with_overrides(ANCHOR, sessions=(make_sess(flat_start=t),)))
        print(row(label, m))
        results.append((label, m))
    return best_of(results)


# ── Sweep 5: direction ────────────────────────────────────────────────────────

def sweep_direction():
    section("SWEEP 5: DIRECTION FILTER")
    header()
    directions = [("long [anchor]", "long"), ("both", "both"), ("short", "short")]
    results = []
    for label, d in directions:
        m = run(with_overrides(ANCHOR, direction_filter=d))
        print(row(label, m))
        results.append((label, m))
    return best_of(results)


# ── Sweep 6: DOW exclusion ────────────────────────────────────────────────────

def sweep_dow():
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
        ("excl Mon+Thu",   {0, 3}),
        ("excl Tue+Thu",   {1, 3}),
    ]
    results = []
    for label, excl in dow_configs:
        m = run(ANCHOR, excluded_dow=excl if excl else None)
        print(row(label, m))
        results.append((label, m))
    return best_of(results)


# ── Sweep 7: max_gap_points ───────────────────────────────────────────────────

def sweep_max_gap_points():
    section("SWEEP 7: MAX GAP POINTS")
    header()
    values = [0, 10, 15, 20, 25, 30, 40, 50]
    results = []
    for v in values:
        label = f"max_gap_pts={v}" + (" [anchor]" if v == 25 else "") + (" (no limit)" if v == 0 else "")
        m = run(with_overrides(ANCHOR, sessions=(make_sess(max_gap_pts=float(v)),)))
        print(row(label, m))
        results.append((label, m))
    return best_of(results)


# ── Sweep 8: max_gap_atr_pct ──────────────────────────────────────────────────

def sweep_max_gap_atr_pct():
    section("SWEEP 8: MAX GAP ATR% (upper cap on FVG size as % of daily ATR)")
    header()
    values = [0.0, 5.0, 8.0, 10.0, 15.0, 20.0, 25.0, 30.0]
    results = []
    for v in values:
        label = f"max_gap_atr={v:.0f}%" + (" [anchor/off]" if v == 0.0 else "")
        m = run(with_overrides(ANCHOR, sessions=(make_sess(max_gap_atr=v),)))
        print(row(label, m))
        results.append((label, m))
    return best_of(results)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_anchor_summary(m):
    section("ANCHOR METRICS (Round 4 winner — ATR 16)")
    print(f"  stop=4.0% | min_gap=2.5% | rr=4.5 | tp1=0.5 | ATR 16 | 10m ORB | entry→11:00 | 1s")
    print()
    print(f"  {'Trades':<20s} {m['total_trades']:>12d}")
    print(f"  {'Win Rate':<20s} {m['win_rate']:>11.1%}")
    print(f"  {'PF':<20s} {m['profit_factor']:>12.2f}")
    print(f"  {'Net R':<20s} {m['total_r']:>11.1f}R")
    print(f"  {'R/yr':<20s} {r_per_year(m):>11.1f}R")
    print(f"  {'Max DD':<20s} {m['max_drawdown_r']:>11.1f}R")
    print(f"  {'Calmar':<20s} {m['calmar_ratio']:>12.2f}")
    print(f"  {'Sharpe':<20s} {m['sharpe_ratio']:>12.3f}")
    print(f"  {'Neg full years':<20s} {neg_years(m):>12d}")
    print()
    rby = m.get("r_by_year", {})
    if rby:
        print(f"  R by year:")
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY CONT LONGS — ROUND 5 VARIABLE SWEEP (1s magnifier)")
    print("  Anchor: stop=4.0% | min_gap=2.5% | rr=4.5 | tp1=0.5 | ATR 16 | 10m ORB | entry→11:00")
    print("  (ATR changed 14→16 in Round 4 — anchor changed, re-sweeping all)")
    print("=" * 70)

    print("\nLoading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})")
    if df_1m is not None:
        print(f"  1m: {len(df_1m):,} bars")
    if df_1s is not None:
        print(f"  1s: {len(df_1s):,} bars")
    else:
        print("  1s: not found — falling back to 1m only")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    print("\nRunning anchor config...")
    t0 = time.time()
    anchor_m = run(ANCHOR)
    print(f"  Done in {time.time() - t0:.1f}s")
    print_anchor_summary(anchor_m)

    best = {}
    best["orb"]         = sweep_orb_window()
    best["atr"]         = sweep_atr_length()
    best["entry_end"]   = sweep_entry_end()
    best["flat_start"]  = sweep_flat_start()
    best["direction"]   = sweep_direction()
    best["dow"]         = sweep_dow()
    best["max_gap_pts"] = sweep_max_gap_points()
    best["max_gap_atr"] = sweep_max_gap_atr_pct()

    print()
    print("=" * 70)
    print("  ROUND 5 SUMMARY — BEST PER DIMENSION")
    print("=" * 70)
    for dim, (lbl, m) in best.items():
        print(f"  {dim:<14s}  {lbl:<38s}  Calmar={m['calmar_ratio']:.2f}  DD={m['max_drawdown_r']:.1f}R  NegYr={neg_years(m)}")
    print()
    print("  Anchor Calmar: {:.2f}".format(anchor_m["calmar_ratio"]))
    print()
    print("  If any dimension improved Calmar by >0.3 over anchor → update anchor and re-sweep.")
    print("  Otherwise → anchor has stabilized. Proceed to grid sweep.")
    print("=" * 70)
    print()
