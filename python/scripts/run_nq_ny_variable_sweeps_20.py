#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 20: re-sweep after fine-tune anchor change.

Fine-tune winner (0 neg years): stop=8.75% rr=2.625 gap=2.25% tp1=0.3
  Calmar=16.36, R/yr=21.3, DD=-13.0, N=1894

R20 anchor:
  ORB: 09:30-09:50 (20m), entry until 15:30, flat 15:50
  stop=8.75%, min_gap=2.25%, max_gap=100pt
  rr=2.625, tp1=0.3, ATR=12, direction=both, continuation, 1s magnifier

Purpose: verify structural vars are stable on new fine-tune anchor.
If no dimension shows Δ > 0.3 with no new negatives, proceed to robust pipeline.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",       # 20m ORB (stable)
    entry_start="09:50",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=8.75,     # Fine-tune winner
    min_gap_atr_pct=2.25,  # Fine-tune winner
    max_gap_points=100.0,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=2.625,              # Fine-tune winner
    tp1_ratio=0.3,         # Fine-tune winner
    atr_length=12,
    name="NQ NY R20 Anchor",
)


def run_and_metric(df_5m, df_1m, df_1s, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    return trades, compute_metrics(trades)


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
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    print("NQ NY ORB — Round 20: re-sweep after fine-tune (stop=8.75% rr=2.625 gap=2.25% tp1=0.3)")
    print("=" * 90)
    print(f"Anchor: dir=both, orb=20m, rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, "
          f"stop={ANCHOR_SESSION.stop_atr_pct}%, gap={ANCHOR_SESSION.min_gap_atr_pct}%, "
          f"atr={ANCHOR.atr_length}, end={ANCHOR_SESSION.entry_end}")

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
    print_header("1. DIRECTION (anchor=both)")
    for i, d in enumerate(["both", "long", "short"], 1):
        config = replace(ANCHOR, direction_filter=d)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"dir={d}", m, is_base=(d == "both"))
        print_years(m)
        all_results.append(("direction", d, m))

    # ── 2. ORB WINDOW ────────────────────────────────────────────────
    orb_windows = [
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
    atr_values = [7, 10, 12, 14, 16, 20]
    print_header("3. ATR LENGTH (anchor=12)")
    for i, atr in enumerate(atr_values, 1):
        config = replace(ANCHOR, atr_length=atr)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"atr={atr}", m, is_base=(atr == 12))
        all_results.append(("atr_length", atr, m))

    # ── 4. ENTRY END TIME ────────────────────────────────────────────
    entry_ends = ["12:00", "13:00", "14:00", "15:00", "15:30"]
    print_header("4. ENTRY END TIME (anchor=15:30)")
    for i, ee in enumerate(entry_ends, 1):
        sess = replace(ANCHOR_SESSION, entry_end=ee)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"end={ee}", m, is_base=(ee == "15:30"))
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

    # ── 6. MAX GAP POINTS ───────────────────────────────────────────
    max_gap_pts = [50, 75, 100, 150, 0]
    print_header("6. MAX GAP POINTS (anchor=100, 0=none)")
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
        "max_gap_points",
    ]

    any_adopted = False
    for var in dimension_order:
        if var not in by_var:
            continue
        best_val, best_m = max(by_var[var], key=lambda x: x[1]["calmar_ratio"])
        delta = best_m["calmar_ratio"] - anchor_calmar
        r_yr = best_m["total_r"] / DATA_YEARS
        best_neg = neg_year_set(best_m)
        new_neg = best_neg - anchor_neg
        adopt = "YES" if delta > 0.3 and len(new_neg) == 0 else "no"
        if adopt == "YES":
            any_adopted = True
        new_neg_str = str(sorted(new_neg)) if new_neg else "none"
        print(f"  {var:<20} {str(best_val):>12} {best_m['calmar_ratio']:>8.2f} "
              f"{delta:>+6.2f} {r_yr:>6.1f} {best_m['max_drawdown_r']:>6.1f} "
              f"{new_neg_str:>6} {adopt:>8}")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")

    if not any_adopted:
        print(f"\n  ** CONVERGED — No dimensions pass adoption threshold **")
        print(f"  Ready for robust pipeline")
    else:
        print(f"\n  ** NOT CONVERGED — Update anchor and re-sweep as R21 **")


if __name__ == "__main__":
    main()
