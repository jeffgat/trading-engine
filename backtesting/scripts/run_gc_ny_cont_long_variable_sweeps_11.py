#!/usr/bin/env python3
"""Step 2 — Variable Sweeps Round 11: GC NY Continuation Longs.

Anchor (from R10 — top 3 adoptions):
  stop=4.5%, rr=8.0, tp1=0.35, ATR 7, min_gap=3.0%, max_gap_atr=30%
  ICF=True, 8m ORB (09:30-09:38), entry→12:00, flat 13:30, long-only, FOMC excluded
  Friday excluded (post-backtest filter)

Changes from R10: rr 9.0→8.0, tp1 0.4→0.35, flat 14:30→13:30
Deferred: ATR 7→10 (adopt next round if still beneficial)
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
CPY = "2026"
EXCL_DAYS = {4}  # Friday

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:38",
    entry_start="09:38",
    entry_end="12:00",
    flat_start="13:30",       # adopted R10
    flat_end="16:00",
    stop_atr_pct=4.5,
    min_gap_atr_pct=3.0,
)

ANCHOR = StrategyConfig(
    rr=8.0,                   # adopted R10
    tp1_ratio=0.35,           # adopted R10
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
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")


def dow_filter(trades):
    return [t for t in trades if t.exit_type == EXIT_NO_FILL or datetime.date.fromisoformat(t.date).weekday() not in EXCL_DAYS]

def run_and_measure(config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades = dow_filter(trades)
    m = compute_metrics(trades)
    m["neg_full_years"] = sum(1 for y, r in m.get("r_by_year", {}).items() if r < 0 and y != CPY)
    m["r_per_yr"] = m["total_r"] / DATA_YEARS
    return m

def run_and_get_trades(config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades = dow_filter(trades)
    m = compute_metrics(trades)
    m["neg_full_years"] = sum(1 for y, r in m.get("r_by_year", {}).items() if r < 0 and y != CPY)
    m["r_per_yr"] = m["total_r"] / DATA_YEARS
    return trades, m

def print_table(results, dim_name, dk="value"):
    print(f"\n{'─'*90}")
    print(f"  DIMENSION: {dim_name}")
    print(f"{'─'*90}")
    print(f"  {'Value':<12} {'Trades':>7} {'WR':>7} {'PF':>6} {'Sharpe':>8} {'Net R':>8} {'R/yr':>7} {'MaxDD':>8} {'Calmar':>8} {'NegYr':>6}")
    print(f"  {'-'*86}")
    for r in results:
        mk = " ◄ANCHOR" if r.get("is_anchor") else ""
        print(f"  {str(r[dk]):<12} {r['total_trades']:>7} {r['win_rate']:>6.1%} {r['profit_factor']:>6.2f} {r['sharpe_ratio']:>8.3f} {r['total_r']:>8.1f} {r['r_per_yr']:>7.1f} {r['max_drawdown_r']:>8.1f} {r['calmar_ratio']:>8.2f} {r['neg_full_years']:>6}{mk}")

def apply_dow_filter_custom(trades, exclude_days):
    return [t for t in trades if t.exit_type == EXIT_NO_FILL or datetime.date.fromisoformat(t.date).weekday() not in exclude_days]

def sweep_stop():
    R = []
    for v in [3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.5, 10.0, 12.0, 15.0]:
        m = run_and_measure(replace(ANCHOR, sessions=(replace(GC_NY, stop_atr_pct=v),)))
        m["value"] = v; m["is_anchor"] = (v == 4.5); R.append(m)
    print_table(R, "Stop ATR %"); return R

def sweep_orb():
    R = []
    for label, s, e, es in [("5m","09:30","09:35","09:35"), ("8m","09:30","09:38","09:38"),
                             ("10m","09:30","09:40","09:40"), ("15m","09:30","09:45","09:45"),
                             ("20m","09:30","09:50","09:50"), ("25m","09:30","09:55","09:55"),
                             ("30m","09:30","10:00","10:00")]:
        m = run_and_measure(replace(ANCHOR, sessions=(replace(GC_NY, orb_start=s, orb_end=e, entry_start=es),)))
        m["value"] = label; m["is_anchor"] = (label == "8m"); R.append(m)
    print_table(R, "ORB Window"); return R

def sweep_atr():
    R = []
    for v in [3, 5, 7, 10, 14, 16, 18, 20, 25, 30, 50]:
        m = run_and_measure(replace(ANCHOR, atr_length=v))
        m["value"] = v; m["is_anchor"] = (v == 7); R.append(m)
    print_table(R, "ATR Length"); return R

def sweep_entry_end():
    R = []
    for v in ["10:30", "11:00", "11:30", "12:00", "13:00"]:
        m = run_and_measure(replace(ANCHOR, sessions=(replace(GC_NY, entry_end=v),)))
        m["value"] = v; m["is_anchor"] = (v == "12:00"); R.append(m)
    print_table(R, "Entry End Time"); return R

def sweep_flat():
    R = []
    for v in ["12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:50"]:
        m = run_and_measure(replace(ANCHOR, sessions=(replace(GC_NY, flat_start=v),)))
        m["value"] = v; m["is_anchor"] = (v == "13:30"); R.append(m)
    print_table(R, "Flat Start Time"); return R

def sweep_dir():
    R = []
    for v in ["long", "both", "short"]:
        m = run_and_measure(replace(ANCHOR, direction_filter=v))
        m["value"] = v; m["is_anchor"] = (v == "long"); R.append(m)
    print_table(R, "Direction"); return R

def sweep_rr():
    R = []
    for v in [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 14.0]:
        m = run_and_measure(replace(ANCHOR, rr=v))
        m["value"] = v; m["is_anchor"] = (v == 8.0); R.append(m)
    print_table(R, "R:R Ratio"); return R

def sweep_tp1():
    R = []
    for v in [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7]:
        m = run_and_measure(replace(ANCHOR, tp1_ratio=v))
        m["value"] = v; m["is_anchor"] = (v == 0.35); R.append(m)
    print_table(R, "TP1 Ratio"); return R

def sweep_gap():
    R = []
    for v in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0]:
        m = run_and_measure(replace(ANCHOR, sessions=(replace(GC_NY, min_gap_atr_pct=v),)))
        m["value"] = v; m["is_anchor"] = (v == 3.0); R.append(m)
    print_table(R, "Min Gap ATR %"); return R

def sweep_dow():
    trades_all = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    R = []
    for label, excl_set in [("Fri only",{4}), ("none",set()), ("Mon+Fri",{0,4}),
                             ("Wed+Fri",{2,4}), ("Thu+Fri",{3,4})]:
        filtered = apply_dow_filter_custom(trades_all, excl_set) if excl_set else trades_all
        m = compute_metrics(filtered)
        m["neg_full_years"] = sum(1 for y, r in m.get("r_by_year", {}).items() if r < 0 and y != CPY)
        m["r_per_yr"] = m["total_r"] / DATA_YEARS
        m["value"] = label; m["is_anchor"] = (label == "Fri only"); R.append(m)
    print_table(R, "DOW Exclusion"); return R

def sweep_max_gap_atr():
    R = []
    for label, v in [("OFF",0.0), ("15%",15.0), ("20%",20.0), ("25%",25.0),
                      ("30%",30.0), ("35%",35.0), ("40%",40.0), ("50%",50.0), ("75%",75.0)]:
        m = run_and_measure(replace(ANCHOR, sessions=(replace(GC_NY, max_gap_atr_pct=v),)))
        m["value"] = label; m["is_anchor"] = (label == "30%"); R.append(m)
    print_table(R, "Max Gap ATR %"); return R

def sweep_icf():
    R = []
    for v in [False, True]:
        m = run_and_measure(replace(ANCHOR, impulse_close_filter=v))
        m["value"] = v; m["is_anchor"] = (v == True); R.append(m)
    print_table(R, "ICF"); return R


if __name__ == "__main__":
    print(f"\n{'='*90}")
    print("  GC NY CONT LONGS — VARIABLE SWEEPS ROUND 11")
    print("  Anchor: stop=4.5%, rr=8.0, tp1=0.35, ATR 7, gap=3.0%, max_gap_atr=30%")
    print("          ICF=True, 8m ORB, entry→12:00, flat 13:30, long-only, FOMC excl")
    print("          Friday excluded")
    print(f"{'='*90}")

    t_start = time.time()

    print("\nRunning anchor...")
    anchor_trades, anchor_m = run_and_get_trades(ANCHOR)
    filled = [t for t in anchor_trades if t.exit_type != EXIT_NO_FILL]
    if filled:
        stop_ticks = [abs(t.entry_price - t.stop_price) / GC.min_tick for t in filled]
        print(f"  Stop ticks — median: {np.median(stop_ticks):.0f}, p10: {np.percentile(stop_ticks,10):.0f}, p25: {np.percentile(stop_ticks,25):.0f}")

    print(f"  Anchor: {anchor_m['total_trades']} trades, Calmar {anchor_m['calmar_ratio']:.2f}, "
          f"Net R {anchor_m['total_r']:.1f}, DD {anchor_m['max_drawdown_r']:.1f}, Neg years {anchor_m['neg_full_years']}")

    print(f"\n  R by year:")
    for y, r in sorted(anchor_m.get("r_by_year", {}).items()):
        flag = " ←NEG" if r < 0 and y != CPY else ""
        print(f"    {y}: {r:>+8.1f}{flag}")

    anchor_calmar = anchor_m["calmar_ratio"]
    anchor_neg = anchor_m["neg_full_years"]

    all_sweeps = {}
    sweep_fns = [
        ("stop", sweep_stop), ("orb", sweep_orb), ("atr", sweep_atr),
        ("entry_end", sweep_entry_end), ("flat", sweep_flat), ("dir", sweep_dir),
        ("rr", sweep_rr), ("tp1", sweep_tp1), ("gap", sweep_gap),
        ("dow", sweep_dow), ("max_gap_atr", sweep_max_gap_atr), ("icf", sweep_icf),
    ]

    for i, (name, fn) in enumerate(sweep_fns, 1):
        print(f"\n[{i}/12] {name}...")
        all_sweeps[name] = fn()

    print(f"\n{'='*90}")
    print(f"  ROUND 11 SUMMARY — Anchor Calmar: {anchor_calmar:.2f} | Neg years: {anchor_neg}")
    print(f"{'='*90}")

    adoptions = []
    print(f"  {'Dim':<20} {'Best':<15} {'Calmar':>12} {'Δ':>10} {'NegYr':>8} {'Trades':>8} {'Decision':>12}")
    print(f"  {'-'*88}")

    for dn, res in all_sweeps.items():
        best = max(res, key=lambda r: r["calmar_ratio"])
        anch = next((r for r in res if r.get("is_anchor")), res[0])
        d = best["calmar_ratio"] - anch["calmar_ratio"]
        adopt = d > 0.3 and best["neg_full_years"] <= anchor_neg and best["total_trades"] > 100
        dec = "→ ADOPT" if adopt else "  keep"
        if adopt:
            adoptions.append((dn, best["value"], best["calmar_ratio"], d))
        print(f"  {dn:<20} {str(best['value']):<15} {best['calmar_ratio']:>12.2f} {d:>+10.2f} {best['neg_full_years']:>8} {best['total_trades']:>8} {dec:>12}")

    print(f"\n  Total adoptions: {len(adoptions)}")
    if adoptions:
        print("\n  Adopted:")
        for dn, v, c, d in adoptions:
            print(f"    {dn}: {v} (Calmar {c:.2f}, Δ={d:+.2f})")
        print(f"\n  → Re-sweep (Round 12).")
    else:
        print(f"\n  → CONVERGED. Ready for grid sweep.")

    print(f"\n  Elapsed: {time.time()-t_start:.0f}s ({(time.time()-t_start)/60:.1f}m)")
