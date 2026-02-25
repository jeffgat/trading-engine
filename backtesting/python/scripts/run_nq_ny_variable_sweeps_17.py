#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 17: updated anchor from R16.

Changes from R16 anchor:
  - direction: both → long (Calmar 4.40 → 6.01, removes 2022 negative year)
  - ORB window: 15m → 20m (Calmar 4.40 → 7.64, massive DD reduction)

New anchor:
  ORB: 09:30-09:50 (20m), entry until 13:00, flat 15:50
  stop=10.0%, min_gap=1.5%, max_gap=100pt
  rr=2.0, tp1=0.5, ATR=14, direction=long, continuation, 1s magnifier

All dimensions re-swept because anchor changed.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

# ── R17 Anchor (adopted from R16) ────────────────────────────────────
ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",       # Changed: 15m → 20m
    entry_start="09:50",   # Changed: matches ORB end
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=10.0,
    min_gap_atr_pct=1.5,
    max_gap_points=100.0,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",   # Changed: both → long
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=14,
    name="NQ NY R17 Anchor",
)


def run_and_metric(df_5m, df_1m, df_1s, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    return trades, compute_metrics(trades)


def run_dow_filtered(trades_all, excluded_days):
    filtered = apply_dow_filter(trades_all, excluded_days)
    return compute_metrics(filtered)


HDR = (
    f"    {'#':>3} {'Variable':>20} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}"
)


def print_header(title):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")
    print(HDR)
    print(f"    {'─'*85}")


def print_row(i, label, m, is_base=False):
    marker = " <-- anchor" if is_base else ""
    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
    print(
        f"    {i:>3} {label:>20} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f}{marker}"
    )


def print_years(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"      R by year: {yr_str}")


def neg_year_set(m):
    """Return set of negative full years (exclude current partial year)."""
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    print("NQ NY ORB — Round 17: long + 20m ORB (1s magnifier)")
    print("=" * 90)
    print(f"Anchor: dir=long, orb=20m, rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, "
          f"stop={ANCHOR_SESSION.stop_atr_pct}%, gap={ANCHOR_SESSION.min_gap_atr_pct}%")

    # ── Load data ─────────────────────────────────────────────────────
    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t_start:.1f}s]")

    all_results = []

    # ── 0. ANCHOR BASELINE ────────────────────────────────────────────
    print_header("0. ANCHOR BASELINE")
    anchor_trades, m_anchor = run_and_metric(df_5m, df_1m, df_1s, ANCHOR)
    print_row(0, "ANCHOR", m_anchor, is_base=True)
    print_years(m_anchor)
    anchor_calmar = m_anchor["calmar_ratio"]
    anchor_neg = neg_year_set(m_anchor)
    print(f"      Negative years: {sorted(anchor_neg) if anchor_neg else 'none'}")

    # ── 1. DIRECTION ──────────────────────────────────────────────────
    directions = ["long", "both", "short"]
    print_header("1. DIRECTION (anchor=long)")
    for i, d in enumerate(directions, 1):
        config = replace(ANCHOR, direction_filter=d)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"dir={d}", m, is_base=(d == "long"))
        print_years(m)
        all_results.append(("direction", d, m))

    # ── 2. ORB WINDOW ────────────────────────────────────────────────
    orb_windows = [
        ("5m",  "09:30", "09:35", "09:35"),
        ("10m", "09:30", "09:40", "09:40"),
        ("15m", "09:30", "09:45", "09:45"),
        ("20m", "09:30", "09:50", "09:50"),
        ("25m", "09:30", "09:55", "09:55"),
        ("30m", "09:30", "10:00", "10:00"),
    ]
    print_header("2. ORB WINDOW (anchor=20m)")
    for i, (label, orb_s, orb_e, entry_s) in enumerate(orb_windows, 1):
        sess = replace(ANCHOR_SESSION, orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"orb={label}", m, is_base=(label == "20m"))
        all_results.append(("orb_window", label, m))

    # ── 3. ATR LENGTH ────────────────────────────────────────────────
    atr_values = [7, 10, 12, 14, 16, 18, 20, 25]
    print_header("3. ATR LENGTH (anchor=14)")
    for i, atr in enumerate(atr_values, 1):
        config = replace(ANCHOR, atr_length=atr)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"atr={atr}", m, is_base=(atr == 14))
        all_results.append(("atr_length", atr, m))

    # ── 4. ENTRY END TIME ────────────────────────────────────────────
    entry_ends = ["12:00", "13:00", "14:00", "15:00", "15:30"]
    print_header("4. ENTRY END TIME (anchor=13:00)")
    for i, ee in enumerate(entry_ends, 1):
        sess = replace(ANCHOR_SESSION, entry_end=ee)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"end={ee}", m, is_base=(ee == "13:00"))
        print_years(m)
        all_results.append(("entry_end", ee, m))

    # ── 5. FLAT START ────────────────────────────────────────────────
    flat_starts = ["14:30", "15:00", "15:30", "15:50"]
    print_header("5. FLAT START (anchor=15:50)")
    for i, fs in enumerate(flat_starts, 1):
        sess = replace(ANCHOR_SESSION, flat_start=fs)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"flat={fs}", m, is_base=(fs == "15:50"))
        all_results.append(("flat_start", fs, m))

    # ── 6. MIN GAP ATR % ────────────────────────────────────────────
    gap_values = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    print_header("6. MIN GAP ATR % (anchor=1.5%)")
    for i, g in enumerate(gap_values, 1):
        sess = replace(ANCHOR_SESSION, min_gap_atr_pct=g)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"gap={g}%", m, is_base=(g == 1.5))
        all_results.append(("min_gap_atr_pct", g, m))

    # ── 7. STOP ATR % ───────────────────────────────────────────────
    stop_values = [6, 7, 8, 9, 10, 11, 12, 14]
    print_header("7. STOP ATR % (anchor=10%)")
    for i, s in enumerate(stop_values, 1):
        sess = replace(ANCHOR_SESSION, stop_atr_pct=float(s))
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"stop={s}%", m, is_base=(s == 10))
        print_years(m)
        all_results.append(("stop_atr_pct", s, m))

    # ── 8. REWARD:RISK ───────────────────────────────────────────────
    rr_values = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5]
    print_header("8. REWARD:RISK (anchor=2.0)")
    for i, rr in enumerate(rr_values, 1):
        config = replace(ANCHOR, rr=rr)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"rr={rr}", m, is_base=(rr == 2.0))
        print_years(m)
        all_results.append(("rr", rr, m))

    # ── 9. TP1 RATIO ────────────────────────────────────────────────
    tp1_values = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    print_header("9. TP1 RATIO (anchor=0.5)")
    for i, tp1 in enumerate(tp1_values, 1):
        config = replace(ANCHOR, tp1_ratio=tp1)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"tp1={tp1}", m, is_base=(tp1 == 0.5))
        all_results.append(("tp1_ratio", tp1, m))

    # ── 10. DOW EXCLUSION ────────────────────────────────────────────
    dow_sets = [
        ("none",     set()),
        ("excl Mon", {0}),
        ("excl Tue", {1}),
        ("excl Wed", {2}),
        ("excl Thu", {3}),
        ("excl Fri", {4}),
        ("excl M+F", {0, 4}),
        ("excl Th+F", {3, 4}),
    ]
    print_header("10. DOW EXCLUSION (anchor=none)")
    for i, (label, excluded) in enumerate(dow_sets, 1):
        m = run_dow_filtered(anchor_trades, excluded)
        print_row(i, label, m, is_base=(len(excluded) == 0))
        all_results.append(("dow_exclusion", label, m))

    # ── 11. MAX GAP POINTS ───────────────────────────────────────────
    max_gap_pts = [50, 75, 100, 150, 0]
    print_header("11. MAX GAP POINTS (anchor=100, 0=none)")
    for i, mg in enumerate(max_gap_pts, 1):
        sess = replace(ANCHOR_SESSION, max_gap_points=float(mg))
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        label = f"maxgap={mg}" if mg > 0 else "maxgap=OFF"
        print_row(i, label, m, is_base=(mg == 100))
        all_results.append(("max_gap_points", mg, m))

    # ══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print(f"  SUMMARY — Best value per dimension (by Calmar)")
    print(f"  Anchor Calmar: {anchor_calmar:.2f} | Anchor neg years: {sorted(anchor_neg)}")
    print(f"{'='*90}")
    print(f"  {'Variable':<20} {'Best Value':>12} {'Calmar':>8} {'Δ':>6} {'R/yr':>6} "
          f"{'DD':>6} {'NewNeg':>6} {'Adopt?':>8}")
    print(f"  {'─'*80}")

    from collections import defaultdict
    by_var = defaultdict(list)
    for var, val, m in all_results:
        by_var[var].append((val, m))

    dimension_order = [
        "direction", "orb_window", "atr_length", "entry_end", "flat_start",
        "min_gap_atr_pct", "stop_atr_pct", "rr", "tp1_ratio",
        "dow_exclusion", "max_gap_points",
    ]

    for var in dimension_order:
        if var not in by_var:
            continue
        best_val, best_m = max(by_var[var], key=lambda x: x[1]["calmar_ratio"])
        delta = best_m["calmar_ratio"] - anchor_calmar
        r_yr = best_m["total_r"] / DATA_YEARS
        best_neg = neg_year_set(best_m)
        new_neg = best_neg - anchor_neg  # years negative in best but NOT in anchor
        adopt = "YES" if delta > 0.3 and len(new_neg) == 0 else "no"
        new_neg_str = str(sorted(new_neg)) if new_neg else "none"
        print(f"  {var:<20} {str(best_val):>12} {best_m['calmar_ratio']:>8.2f} "
              f"{delta:>+6.2f} {r_yr:>6.1f} {best_m['max_drawdown_r']:>6.1f} "
              f"{new_neg_str:>6} {adopt:>8}")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
