#!/usr/bin/env python3
"""Step 2 — Variable Sweeps Round 6: GC NY Continuation Longs.

Anchor (from R5 adoptions):
  stop=4.0%, rr=7.0, tp1=0.5, ATR 7, min_gap=2.5%, max_gap_atr=25%
  ICF=True, 8m ORB (09:30-09:38), entry→12:00, flat 15:50, long-only, FOMC excluded
"""

import sys
import time
import datetime
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10.15
CURRENT_PARTIAL_YEAR = "2026"

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:38",       # 8m ORB (adopted R5)
    entry_start="09:38",
    entry_end="12:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=4.0,
    min_gap_atr_pct=2.5,
)

ANCHOR = StrategyConfig(
    rr=7.0,
    tp1_ratio=0.5,           # adopted R5
    risk_usd=5000.0,
    atr_length=7,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    impulse_close_filter=True,
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=FOMC_DATES,
)

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(GC.data_file, start=START_DATE)
df_1m = load_1m_for_5m(GC.data_file, start=START_DATE)
df_1s = load_1s_for_5m(GC.data_file, start=START_DATE)
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}")
print(f"  Loaded in {time.time() - t0:.1f}s")


def run_and_measure(config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    r_by_year = m.get("r_by_year", {})
    m["neg_full_years"] = sum(1 for y, r in r_by_year.items() if r < 0 and y != CURRENT_PARTIAL_YEAR)
    m["r_per_yr"] = m["total_r"] / DATA_YEARS
    return m

def run_and_get_trades(config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    r_by_year = m.get("r_by_year", {})
    m["neg_full_years"] = sum(1 for y, r in r_by_year.items() if r < 0 and y != CURRENT_PARTIAL_YEAR)
    m["r_per_yr"] = m["total_r"] / DATA_YEARS
    return trades, m

def print_sweep_table(results, dim_name, dim_key="value"):
    print(f"\n{'─'*90}")
    print(f"  DIMENSION: {dim_name}")
    print(f"{'─'*90}")
    print(f"  {'Value':<12} {'Trades':>7} {'WR':>7} {'PF':>6} {'Sharpe':>8} {'Net R':>8} {'R/yr':>7} {'MaxDD':>8} {'Calmar':>8} {'NegYr':>6}")
    print(f"  {'-'*86}")
    for r in results:
        marker = " ◄ANCHOR" if r.get("is_anchor") else ""
        print(f"  {str(r[dim_key]):<12} {r['total_trades']:>7} {r['win_rate']:>6.1%} {r['profit_factor']:>6.2f} {r['sharpe_ratio']:>8.3f} {r['total_r']:>8.1f} {r['r_per_yr']:>7.1f} {r['max_drawdown_r']:>8.1f} {r['calmar_ratio']:>8.2f} {r['neg_full_years']:>6}{marker}")

def apply_dow_filter(trades, exclude_days):
    return [t for t in trades if t.exit_type == EXIT_NO_FILL or datetime.date.fromisoformat(t.date).weekday() not in exclude_days]

# ── Sweeps ────────────────────────────────────────────────────────────────────

def sweep_stop_atr():
    results = []
    for v in [3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.5, 10.0, 12.0, 15.0]:
        cfg = replace(ANCHOR, sessions=(replace(GC_NY, stop_atr_pct=v),))
        m = run_and_measure(cfg); m["value"] = v; m["is_anchor"] = (v == 4.0)
        results.append(m)
    print_sweep_table(results, "Stop ATR % (floor 3.0%)")
    return results

def sweep_orb_window():
    results = []
    for label, s, e, es in [("5m","09:30","09:35","09:35"),("8m","09:30","09:38","09:38"),("10m","09:30","09:40","09:40"),("15m","09:30","09:45","09:45"),("20m","09:30","09:50","09:50"),("25m","09:30","09:55","09:55"),("30m","09:30","10:00","10:00")]:
        cfg = replace(ANCHOR, sessions=(replace(GC_NY, orb_start=s, orb_end=e, entry_start=es),))
        m = run_and_measure(cfg); m["value"] = label; m["is_anchor"] = (label == "8m")
        results.append(m)
    print_sweep_table(results, "ORB Window")
    return results

def sweep_atr_length():
    results = []
    for v in [3, 5, 7, 10, 12, 14, 16, 18, 20, 25, 30, 50]:
        m = run_and_measure(replace(ANCHOR, atr_length=v)); m["value"] = v; m["is_anchor"] = (v == 7)
        results.append(m)
    print_sweep_table(results, "ATR Length")
    return results

def sweep_entry_end():
    results = []
    for v in ["10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00"]:
        cfg = replace(ANCHOR, sessions=(replace(GC_NY, entry_end=v),))
        m = run_and_measure(cfg); m["value"] = v; m["is_anchor"] = (v == "12:00")
        results.append(m)
    print_sweep_table(results, "Entry End Time")
    return results

def sweep_flat_start():
    results = []
    for v in ["13:00", "14:00", "14:30", "15:00", "15:30", "15:50"]:
        cfg = replace(ANCHOR, sessions=(replace(GC_NY, flat_start=v),))
        m = run_and_measure(cfg); m["value"] = v; m["is_anchor"] = (v == "15:50")
        results.append(m)
    print_sweep_table(results, "Flat Start Time")
    return results

def sweep_direction():
    results = []
    for v in ["long", "both", "short"]:
        m = run_and_measure(replace(ANCHOR, direction_filter=v)); m["value"] = v; m["is_anchor"] = (v == "long")
        results.append(m)
    print_sweep_table(results, "Direction")
    return results

def sweep_rr():
    results = []
    for v in [2.0, 3.0, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 9.0, 10.0]:
        m = run_and_measure(replace(ANCHOR, rr=v)); m["value"] = v; m["is_anchor"] = (v == 7.0)
        results.append(m)
    print_sweep_table(results, "R:R Ratio")
    return results

def sweep_tp1_ratio():
    results = []
    for v in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        m = run_and_measure(replace(ANCHOR, tp1_ratio=v)); m["value"] = v; m["is_anchor"] = (v == 0.5)
        results.append(m)
    print_sweep_table(results, "TP1 Ratio")
    return results

def sweep_min_gap_atr():
    results = []
    for v in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]:
        cfg = replace(ANCHOR, sessions=(replace(GC_NY, min_gap_atr_pct=v),))
        m = run_and_measure(cfg); m["value"] = v; m["is_anchor"] = (v == 2.5)
        results.append(m)
    print_sweep_table(results, "Min Gap ATR %")
    return results

def sweep_dow_exclusion():
    trades_all = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    results = []
    for label, excl_set in [("none",set()),("Mon",{0}),("Tue",{1}),("Wed",{2}),("Thu",{3}),("Fri",{4}),("Mon+Fri",{0,4}),("Thu+Fri",{3,4})]:
        filtered = apply_dow_filter(trades_all, excl_set) if excl_set else trades_all
        m = compute_metrics(filtered)
        m["neg_full_years"] = sum(1 for y, r in m.get("r_by_year", {}).items() if r < 0 and y != CURRENT_PARTIAL_YEAR)
        m["r_per_yr"] = m["total_r"] / DATA_YEARS
        m["value"] = label; m["is_anchor"] = (label == "none")
        results.append(m)
    print_sweep_table(results, "DOW Exclusion")
    return results

def sweep_max_gap_atr():
    results = []
    for label, v in [("OFF",0.0),("15%",15.0),("20%",20.0),("25%",25.0),("30%",30.0),("40%",40.0),("50%",50.0),("75%",75.0)]:
        cfg = replace(ANCHOR, sessions=(replace(GC_NY, max_gap_atr_pct=v),))
        m = run_and_measure(cfg); m["value"] = label; m["is_anchor"] = (label == "25%")
        results.append(m)
    print_sweep_table(results, "Max Gap ATR %")
    return results

def sweep_icf():
    results = []
    for v in [False, True]:
        m = run_and_measure(replace(ANCHOR, impulse_close_filter=v)); m["value"] = v; m["is_anchor"] = (v == True)
        results.append(m)
    print_sweep_table(results, "Impulse Close Filter")
    return results

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 90)
    print("  GC NY CONTINUATION LONGS — VARIABLE SWEEPS ROUND 6")
    print("  Anchor: stop=4.0%, rr=7.0, tp1=0.5, ATR 7, gap=2.5%, max_gap_atr=25%")
    print("          ICF=True, 8m ORB, entry→12:00, flat 15:50, long-only, FOMC excl")
    print("=" * 90)

    t_start = time.time()

    print("\nRunning anchor + median stop tick check...")
    anchor_trades, anchor_m = run_and_get_trades(ANCHOR)
    filled = [t for t in anchor_trades if t.exit_type != EXIT_NO_FILL]
    if filled:
        stop_ticks = [abs(t.entry_price - t.stop_price) / GC.min_tick for t in filled]
        print(f"  Stop ticks — median: {np.median(stop_ticks):.0f}, p10: {np.percentile(stop_ticks,10):.0f}, p25: {np.percentile(stop_ticks,25):.0f}")
        if np.median(stop_ticks) < 10:
            print(f"  ⚠ WARNING: Median stop ticks ({np.median(stop_ticks):.0f}) is below 10!")

    print(f"  Anchor: {anchor_m['total_trades']} trades, Calmar {anchor_m['calmar_ratio']:.2f}, "
          f"Net R {anchor_m['total_r']:.1f}, DD {anchor_m['max_drawdown_r']:.1f}, Neg years {anchor_m['neg_full_years']}")

    r_by_year = anchor_m.get("r_by_year", {})
    print(f"\n  Anchor R by year:")
    for year, r_val in sorted(r_by_year.items()):
        flag = " ←NEG" if r_val < 0 and year != CURRENT_PARTIAL_YEAR else ""
        print(f"    {year}: {r_val:>+8.1f}{flag}")

    anchor_calmar = anchor_m["calmar_ratio"]
    anchor_neg_years = anchor_m["neg_full_years"]

    all_sweeps = {}
    for i, (name, fn) in enumerate([
        ("stop_atr_pct", sweep_stop_atr), ("orb_window", sweep_orb_window),
        ("atr_length", sweep_atr_length), ("entry_end", sweep_entry_end),
        ("flat_start", sweep_flat_start), ("direction", sweep_direction),
        ("rr", sweep_rr), ("tp1_ratio", sweep_tp1_ratio),
        ("min_gap_atr", sweep_min_gap_atr), ("dow_exclusion", sweep_dow_exclusion),
        ("max_gap_atr", sweep_max_gap_atr), ("icf", sweep_icf),
    ], 1):
        print(f"\n[{i}/12] {name}...")
        all_sweeps[name] = fn()

    print("\n" + "=" * 90)
    print(f"  ROUND 6 SUMMARY — Anchor Calmar: {anchor_calmar:.2f} | Neg full years: {anchor_neg_years}")
    print("=" * 90)

    adoptions = []
    print(f"  {'Dimension':<20} {'Best Value':<15} {'Best Calmar':>12} {'Δ Calmar':>10} {'Neg Yr':>8} {'Trades':>8} {'Decision':>12}")
    print(f"  {'-'*88}")

    for dim_name, results in all_sweeps.items():
        best = max(results, key=lambda r: r["calmar_ratio"])
        anchor_row = next((r for r in results if r.get("is_anchor")), results[0])
        delta = best["calmar_ratio"] - anchor_row["calmar_ratio"]
        if dim_name == "dow_exclusion":
            dec = "  SKIP-DOW"; adopt = False
        else:
            adopt = delta > 0.3 and best["neg_full_years"] <= anchor_neg_years and best["total_trades"] > 100
            dec = "→ ADOPT" if adopt else "  keep"
        if adopt:
            adoptions.append((dim_name, best["value"], best["calmar_ratio"], delta))
        print(f"  {dim_name:<20} {str(best['value']):<15} {best['calmar_ratio']:>12.2f} {delta:>+10.2f} {best['neg_full_years']:>8} {best['total_trades']:>8} {dec:>12}")

    print(f"\n  Total adoptions: {len(adoptions)}")
    if adoptions:
        print("\n  Adopted changes:")
        for dim, val, calmar, delta in adoptions:
            print(f"    {dim}: {val} (Calmar {calmar:.2f}, Δ={delta:+.2f})")
        print(f"\n  → Anchor changed. Must re-sweep (Round 7).")
    else:
        print(f"\n  → No changes. Anchor CONVERGED. Ready for grid sweep.")

    print(f"\n  Total elapsed: {time.time()-t_start:.0f}s ({(time.time()-t_start)/60:.1f}m)")
