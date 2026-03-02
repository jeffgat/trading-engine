#!/usr/bin/env python3
"""Step 2 — Variable Sweeps Round 3: NQ LDN Continuation Longs.

Anchor (from R2 adoptions):
  stop=2.5% ATR, rr=8.0, tp1=0.6, ATR 10, min_gap=1.0% ATR
  ICF=False, 30m ORB (03:00-03:30), entry->08:25, flat 08:20, long-only

13 dimensions: original 11 + stop_orb_pct + min_gap_orb_pct.
"""

import sys
import time
import datetime
from dataclasses import replace
from pathlib import Path
from statistics import median

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

# ── Config ────────────────────────────────────────────────────────────────────

START_DATE = "2016-01-01"
DATA_YEARS = 10.15
CURRENT_PARTIAL_YEAR = "2026"

NQ_LDN = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:30",       # 30m ORB (adopted R2)
    entry_start="03:30",
    entry_end="08:25",
    flat_start="08:20",
    flat_end="08:25",
    stop_atr_pct=2.5,      # adopted R2
    min_gap_atr_pct=1.0,
)

ANCHOR = StrategyConfig(
    rr=8.0,                 # adopted R2
    tp1_ratio=0.6,          # adopted R2
    risk_usd=5000.0,
    atr_length=10,          # adopted R2
    sessions=(NQ_LDN,),
    instrument=NQ,
    strategy="continuation",
    direction_filter="long",
    impulse_close_filter=False,
    use_bar_magnifier=True,
)

# ── Data ──────────────────────────────────────────────────────────────────────

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(NQ.data_file, start=START_DATE)
df_1m = load_1m_for_5m(NQ.data_file, start=START_DATE)
df_1s = load_1s_for_5m(NQ.data_file, start=START_DATE)
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}")
print(f"  Loaded in {time.time() - t0:.1f}s")


# ── Helpers ───────────────────────────────────────────────────────────────────

def median_stop_ticks(trades):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return 0.0
    return median(t.risk_points / NQ.min_tick for t in filled)


def run_and_measure(config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    r_by_year = m.get("r_by_year", {})
    neg_years = sum(1 for y, r in r_by_year.items() if r < 0 and y != CURRENT_PARTIAL_YEAR)
    m["neg_full_years"] = neg_years
    m["r_per_yr"] = m["total_r"] / DATA_YEARS
    m["median_stop_ticks"] = median_stop_ticks(trades)
    return m


def run_and_get_trades(config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    r_by_year = m.get("r_by_year", {})
    neg_years = sum(1 for y, r in r_by_year.items() if r < 0 and y != CURRENT_PARTIAL_YEAR)
    m["neg_full_years"] = neg_years
    m["r_per_yr"] = m["total_r"] / DATA_YEARS
    m["median_stop_ticks"] = median_stop_ticks(trades)
    return trades, m


def print_sweep_table(results, dim_name, dim_key="value"):
    print(f"\n{'─'*100}")
    print(f"  DIMENSION: {dim_name}")
    print(f"{'─'*100}")
    header = f"  {'Value':<16} {'Trades':>7} {'WR':>7} {'PF':>6} {'Sharpe':>8} {'Net R':>8} {'R/yr':>7} {'MaxDD':>8} {'Calmar':>8} {'NegYr':>6} {'MedStop':>8}"
    print(header)
    print(f"  {'-'*97}")
    for r in results:
        marker = " <<ANCHOR" if r.get("is_anchor") else ""
        skip = ""
        if r.get("median_stop_ticks", 999) < 10:
            skip = " SKIP(<10t)"
        print(
            f"  {str(r[dim_key]):<16} "
            f"{r['total_trades']:>7} "
            f"{r['win_rate']:>6.1%} "
            f"{r['profit_factor']:>6.2f} "
            f"{r['sharpe_ratio']:>8.3f} "
            f"{r['total_r']:>8.1f} "
            f"{r['r_per_yr']:>7.1f} "
            f"{r['max_drawdown_r']:>8.1f} "
            f"{r['calmar_ratio']:>8.2f} "
            f"{r['neg_full_years']:>6} "
            f"{r.get('median_stop_ticks', 0):>7.0f}"
            f"{marker}{skip}"
        )


def apply_dow_filter(trades, exclude_days):
    return [
        t for t in trades
        if t.exit_type == EXIT_NO_FILL or datetime.date.fromisoformat(t.date).weekday() not in exclude_days
    ]


# ── Sweep functions ───────────────────────────────────────────────────────────

def sweep_stop_atr():
    values = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 7.5]
    results = []
    for v in values:
        sess = replace(NQ_LDN, stop_atr_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == NQ_LDN.stop_atr_pct)
        results.append(m)
    print_sweep_table(results, "Stop ATR %")
    return results


def sweep_stop_orb():
    """Sweep stop as % of ORB range instead of ATR.
    When stop_orb_pct > 0, it overrides stop_atr_pct in the engine."""
    values = [
        ("ATR 2.5%", 0.0),       # anchor (ATR-based)
        ("ORB 10%", 10.0),
        ("ORB 20%", 20.0),
        ("ORB 30%", 30.0),
        ("ORB 40%", 40.0),
        ("ORB 50%", 50.0),
        ("ORB 75%", 75.0),
        ("ORB 100%", 100.0),
        ("ORB 150%", 150.0),
    ]
    results = []
    for label, v in values:
        sess = replace(NQ_LDN, stop_orb_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = label
        m["is_anchor"] = (v == 0.0)
        results.append(m)
    print_sweep_table(results, "Stop ORB % (vs ATR baseline)")
    return results


def sweep_orb_window():
    windows = [
        ("5m",  "03:00", "03:05", "03:05"),
        ("10m", "03:00", "03:10", "03:10"),
        ("15m", "03:00", "03:15", "03:15"),
        ("20m", "03:00", "03:20", "03:20"),
        ("25m", "03:00", "03:25", "03:25"),
        ("30m", "03:00", "03:30", "03:30"),
        ("35m", "03:00", "03:35", "03:35"),
        ("45m", "03:00", "03:45", "03:45"),
        ("60m", "03:00", "04:00", "04:00"),
    ]
    results = []
    for label, orb_s, orb_e, entry_s in windows:
        sess = replace(NQ_LDN, orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = label
        m["is_anchor"] = (label == "30m")
        results.append(m)
    print_sweep_table(results, "ORB Window")
    return results


def sweep_atr_length():
    values = [3, 5, 7, 10, 14, 20, 30, 50]
    results = []
    for v in values:
        cfg = replace(ANCHOR, atr_length=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.atr_length)
        results.append(m)
    print_sweep_table(results, "ATR Length")
    return results


def sweep_entry_end():
    values = ["04:30", "05:00", "06:00", "07:00", "07:30", "08:00", "08:25"]
    results = []
    for v in values:
        sess = replace(NQ_LDN, entry_end=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == NQ_LDN.entry_end)
        results.append(m)
    print_sweep_table(results, "Entry End Time")
    return results


def sweep_flat_start():
    values = ["05:00", "06:00", "07:00", "07:30", "08:00", "08:20"]
    results = []
    for v in values:
        sess = replace(NQ_LDN, flat_start=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == NQ_LDN.flat_start)
        results.append(m)
    print_sweep_table(results, "Flat Start Time")
    return results


def sweep_direction():
    values = ["long", "both", "short"]
    results = []
    for v in values:
        cfg = replace(ANCHOR, direction_filter=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.direction_filter)
        results.append(m)
    print_sweep_table(results, "Direction")
    return results


def sweep_rr():
    values = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]
    results = []
    for v in values:
        cfg = replace(ANCHOR, rr=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.rr)
        results.append(m)
    print_sweep_table(results, "R:R Ratio")
    return results


def sweep_tp1_ratio():
    values = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    results = []
    for v in values:
        cfg = replace(ANCHOR, tp1_ratio=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.tp1_ratio)
        results.append(m)
    print_sweep_table(results, "TP1 Ratio (min 0.2)")
    return results


def sweep_min_gap_atr():
    values = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
    results = []
    for v in values:
        sess = replace(NQ_LDN, min_gap_atr_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == NQ_LDN.min_gap_atr_pct)
        results.append(m)
    print_sweep_table(results, "Min Gap ATR %")
    return results


def sweep_min_gap_orb():
    """Sweep min gap as % of ORB range instead of ATR.
    When min_gap_orb_pct > 0, it overrides min_gap_atr_pct in the engine."""
    values = [
        ("ATR 1.0%", 0.0),       # anchor (ATR-based)
        ("ORB 2%", 2.0),
        ("ORB 5%", 5.0),
        ("ORB 10%", 10.0),
        ("ORB 15%", 15.0),
        ("ORB 20%", 20.0),
        ("ORB 30%", 30.0),
        ("ORB 50%", 50.0),
    ]
    results = []
    for label, v in values:
        sess = replace(NQ_LDN, min_gap_orb_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = label
        m["is_anchor"] = (v == 0.0)
        results.append(m)
    print_sweep_table(results, "Min Gap ORB % (vs ATR baseline)")
    return results


def sweep_dow_exclusion():
    trades_all = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    exclusions = {
        "none": set(),
        "Mon": {0},
        "Tue": {1},
        "Wed": {2},
        "Thu": {3},
        "Fri": {4},
        "Mon+Fri": {0, 4},
        "Thu+Fri": {3, 4},
    }
    results = []
    for label, excl_set in exclusions.items():
        filtered = apply_dow_filter(trades_all, excl_set) if excl_set else trades_all
        m = compute_metrics(filtered)
        r_by_year = m.get("r_by_year", {})
        neg_years = sum(1 for y, r in r_by_year.items() if r < 0 and y != CURRENT_PARTIAL_YEAR)
        m["neg_full_years"] = neg_years
        m["r_per_yr"] = m["total_r"] / DATA_YEARS
        m["median_stop_ticks"] = median_stop_ticks(filtered)
        m["value"] = label
        m["is_anchor"] = (label == "none")
        results.append(m)
    print_sweep_table(results, "DOW Exclusion")
    return results


def sweep_icf():
    values = [False, True]
    results = []
    for v in values:
        cfg = replace(ANCHOR, impulse_close_filter=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.impulse_close_filter)
        results.append(m)
    print_sweep_table(results, "Impulse Close Filter")
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 90)
    print("  NQ LDN CONTINUATION LONGS — VARIABLE SWEEPS ROUND 3")
    print("  Anchor: stop=2.5% ATR, rr=8.0, tp1=0.6, ATR 10, gap=1.0% ATR")
    print("          ICF=False, 30m ORB (03:00-03:30), entry->08:25, flat 08:20, long-only")
    print("=" * 90)

    t_start = time.time()

    # Run anchor and check median stop ticks
    print("\nRunning anchor + median stop tick check...")
    anchor_trades, anchor_m = run_and_get_trades(ANCHOR)
    filled = [t for t in anchor_trades if t.exit_type != EXIT_NO_FILL]
    if filled:
        stop_ticks = [t.risk_points / NQ.min_tick for t in filled]
        median_ticks = np.median(stop_ticks)
        p10_ticks = np.percentile(stop_ticks, 10)
        p25_ticks = np.percentile(stop_ticks, 25)
        print(f"  Stop ticks — median: {median_ticks:.0f}, p10: {p10_ticks:.0f}, p25: {p25_ticks:.0f}")
        if median_ticks < 10:
            print(f"  WARNING: Median stop ticks ({median_ticks:.0f}) is below 10!")

    print(f"  Anchor: {anchor_m['total_trades']} trades, Calmar {anchor_m['calmar_ratio']:.2f}, "
          f"Net R {anchor_m['total_r']:.1f}, DD {anchor_m['max_drawdown_r']:.1f}, "
          f"Neg years {anchor_m['neg_full_years']}")

    r_by_year = anchor_m.get("r_by_year", {})
    print(f"\n  Anchor R by year:")
    for year, r_val in sorted(r_by_year.items()):
        flag = " <-NEG" if r_val < 0 and year != CURRENT_PARTIAL_YEAR else ""
        print(f"    {year}: {r_val:>+8.1f}{flag}")

    anchor_calmar = anchor_m["calmar_ratio"]
    anchor_neg_years = anchor_m["neg_full_years"]

    all_sweeps = {}

    print("\n[1/13] Stop ATR %...")
    all_sweeps["stop_atr_pct"] = sweep_stop_atr()

    print("\n[2/13] Stop ORB % (vs ATR)...")
    all_sweeps["stop_orb_pct"] = sweep_stop_orb()

    print("\n[3/13] ORB Window...")
    all_sweeps["orb_window"] = sweep_orb_window()

    print("\n[4/13] ATR Length...")
    all_sweeps["atr_length"] = sweep_atr_length()

    print("\n[5/13] Entry End...")
    all_sweeps["entry_end"] = sweep_entry_end()

    print("\n[6/13] Flat Start...")
    all_sweeps["flat_start"] = sweep_flat_start()

    print("\n[7/13] Direction...")
    all_sweeps["direction"] = sweep_direction()

    print("\n[8/13] R:R...")
    all_sweeps["rr"] = sweep_rr()

    print("\n[9/13] TP1 Ratio...")
    all_sweeps["tp1_ratio"] = sweep_tp1_ratio()

    print("\n[10/13] Min Gap ATR %...")
    all_sweeps["min_gap_atr"] = sweep_min_gap_atr()

    print("\n[11/13] Min Gap ORB % (vs ATR)...")
    all_sweeps["min_gap_orb"] = sweep_min_gap_orb()

    print("\n[12/13] DOW Exclusion...")
    all_sweeps["dow_exclusion"] = sweep_dow_exclusion()

    print("\n[13/13] Impulse Close Filter...")
    all_sweeps["icf"] = sweep_icf()

    # ── Summary ───────────────────────────────────────────────────────────────

    print("\n" + "=" * 90)
    print("  ROUND 3 SUMMARY — Adoption Decisions")
    print(f"  Anchor Calmar: {anchor_calmar:.2f} | Neg full years: {anchor_neg_years}")
    print("  Adoption rule: delta Calmar > +0.3 AND no new neg years AND trades > 100 AND median stop >= 10 ticks")
    print("=" * 90)

    adoptions = []
    header = f"  {'Dimension':<20} {'Best Value':<16} {'Best Calmar':>12} {'delta Cal':>10} {'Neg Yr':>8} {'Trades':>8} {'MedStop':>8} {'Decision':>12}"
    print(header)
    print(f"  {'-'*100}")

    for dim_name, results in all_sweeps.items():
        # Filter out configs with median stop < 10 ticks
        valid = [r for r in results if r.get("median_stop_ticks", 999) >= 10]
        if not valid:
            print(f"  {dim_name:<20} {'ALL SKIP':<16} {'---':>12} {'---':>10} {'---':>8} {'---':>8} {'---':>8} {'SKIP(<10t)':>12}")
            continue

        best = max(valid, key=lambda r: r["calmar_ratio"])
        anchor_row = next((r for r in results if r.get("is_anchor")), results[0])
        delta = best["calmar_ratio"] - anchor_row["calmar_ratio"]

        if dim_name == "dow_exclusion":
            decision_str = "  SKIP-DOW"
            adopt = False
        else:
            adopt = (
                delta > 0.3
                and best["neg_full_years"] <= anchor_neg_years
                and best["total_trades"] > 100
                and best.get("median_stop_ticks", 0) >= 10
            )
            decision_str = "-> ADOPT" if adopt else "  keep"

        if adopt:
            adoptions.append((dim_name, best["value"], best["calmar_ratio"], delta))

        print(
            f"  {dim_name:<20} {str(best['value']):<16} "
            f"{best['calmar_ratio']:>12.2f} "
            f"{delta:>+10.2f} "
            f"{best['neg_full_years']:>8} "
            f"{best['total_trades']:>8} "
            f"{best.get('median_stop_ticks', 0):>7.0f} "
            f"{decision_str:>12}"
        )

    print(f"\n  Total adoptions: {len(adoptions)}")
    if adoptions:
        print("\n  Adopted changes:")
        for dim, val, calmar, delta in adoptions:
            print(f"    {dim}: {val} (Calmar {calmar:.2f}, delta={delta:+.2f})")
        print(f"\n  -> Anchor changed. Must re-sweep all 13 dimensions (Round 4).")
    else:
        print(f"\n  -> No changes. Anchor converged. Ready for grid sweep.")

    elapsed = time.time() - t_start
    print(f"\n  Total elapsed: {elapsed:.0f}s ({elapsed/60:.1f}m)")
