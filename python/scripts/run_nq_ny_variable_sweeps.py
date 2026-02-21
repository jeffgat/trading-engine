#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps for dimensions not covered in the robust pipeline grid.

Base config: WF mode params from robust pipeline run.
  rr=2.0, tp1_ratio=0.5, stop_atr=10.0%, min_gap_atr=1.5%
  magnifier ON, continuation

Variables swept (one at a time, holding others at base):
  1. max_gap_points:  20, 30, 40, 50, 75, 100*, 150, 200, 0 (no limit)
  2. max_gap_atr_pct: 0*, 3, 5, 7.5, 10, 15, 20, 25
  3. atr_length:      7, 10, 14*, 20, 30, 50
  4. ORB window:      15m*, 30m, 45m, 60m
  5. Entry end time:  10:30, 11:00, 11:30, 12:00, 12:30, 13:00*, 14:00, 15:00
  6. Direction:        both*, long, short

* = current base value
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import NY_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"

# WF mode params from robust pipeline
BASE_PARAMS = {
    "rr": 2.0,
    "tp1_ratio": 0.5,
    "ny_stop_atr_pct": 10.0,
    "ny_min_gap_atr_pct": 1.5,
}


def make_base():
    config = StrategyConfig(
        sessions=(NY_SESSION,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        name="NQ NY Variable Sweep",
    )
    return with_overrides(config, **BASE_PARAMS)


def run_and_metric(df_5m, df_1m, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    return compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Variable':>16} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")
    print(HDR)
    print("-" * 80)


def print_row(i, label, m, is_base=False):
    marker = " <-- base" if is_base else ""
    print(
        f"{i:>3} {label:>16} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
        f"{m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} {m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        # Print on one line if compact enough
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def main():
    print("NQ NY ORB — Variable Sweeps (magnifier)")
    print("=" * 80)
    print(f"Base: rr={BASE_PARAMS['rr']}, tp1={BASE_PARAMS['tp1_ratio']}, "
          f"stop={BASE_PARAMS['ny_stop_atr_pct']}%, gap={BASE_PARAMS['ny_min_gap_atr_pct']}%")

    # Load data
    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    base = make_base()
    all_results = []  # collect (label, variable, value, metrics) for final summary

    # ── 1. MAX GAP POINTS ─────────────────────────────────────────────
    max_gap_values = [20, 30, 40, 50, 75, 100, 150, 200, 0]
    print_header(f"1. MAX GAP POINTS (0=no limit, base=100)")

    for i, mg in enumerate(max_gap_values, 1):
        sess = replace(base.sessions[0], max_gap_points=float(mg))
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        label = f"maxgap={mg}" if mg > 0 else "maxgap=OFF"
        is_base = (mg == 100)
        print_row(i, label, m, is_base)
        all_results.append(("max_gap_points", mg, m))

    # ── 2. MAX GAP ATR % ─────────────────────────────────────────────
    max_gap_atr_values = [0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0]
    print_header(f"2. MAX GAP ATR % (0=disabled/base)")

    for i, mga in enumerate(max_gap_atr_values, 1):
        sess = replace(base.sessions[0], max_gap_atr_pct=mga)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        label = f"maxgap_atr={mga}%" if mga > 0 else "maxgap_atr=OFF"
        is_base = (mga == 0)
        print_row(i, label, m, is_base)
        all_results.append(("max_gap_atr_pct", mga, m))

    # ── 3. ATR LENGTH ──────────────────────────────────────────────────
    atr_values = [7, 10, 14, 20, 30, 50]
    print_header(f"3. ATR LENGTH (base=14)")

    for i, atr in enumerate(atr_values, 1):
        config = replace(base, atr_length=atr)
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (atr == 14)
        print_row(i, f"atr={atr}", m, is_base)
        all_results.append(("atr_length", atr, m))

    # ── 4. ORB WINDOW ──────────────────────────────────────────────────
    orb_windows = [
        ("15m", "09:30", "09:45", "09:45"),
        ("30m", "09:30", "10:00", "10:00"),
        ("45m", "09:30", "10:15", "10:15"),
        ("60m", "09:30", "10:30", "10:30"),
    ]
    print_header(f"4. ORB WINDOW (base=15m)")

    for i, (label, orb_s, orb_e, entry_s) in enumerate(orb_windows, 1):
        sess = replace(base.sessions[0], orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (label == "15m")
        print_row(i, f"orb={label}", m, is_base)
        all_results.append(("orb_window", label, m))

    # ── 5. ENTRY END TIME ─────────────────────────────────────────────
    entry_ends = ["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "14:00", "15:00"]
    print_header(f"5. ENTRY END TIME (base=13:00)")

    for i, ee in enumerate(entry_ends, 1):
        sess = replace(base.sessions[0], entry_end=ee)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (ee == "13:00")
        print_row(i, f"end={ee}", m, is_base)
        all_results.append(("entry_end", ee, m))
        if is_base:
            print_year_breakdown(m)

    # ── 6. DIRECTION ──────────────────────────────────────────────────
    directions = ["both", "long", "short"]
    print_header(f"6. DIRECTION FILTER (base=both)")

    for i, d in enumerate(directions, 1):
        config = with_overrides(base, direction_filter=d)
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (d == "both")
        print_row(i, f"dir={d}", m, is_base)
        print_year_breakdown(m)
        all_results.append(("direction", d, m))

    # ── SUMMARY ───────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  SUMMARY — Best value per variable (by Sharpe)")
    print(f"{'='*80}")
    print(f"  {'Variable':<20} {'Best Value':>12} {'Sharpe':>8} {'Net R':>8} {'DD R':>8} {'Trades':>8}")
    print(f"  {'-'*68}")

    # Group by variable
    from collections import defaultdict
    by_var = defaultdict(list)
    for var, val, m in all_results:
        by_var[var].append((val, m))

    for var in ["max_gap_points", "max_gap_atr_pct", "atr_length", "orb_window",
                "entry_end", "direction"]:
        if var not in by_var:
            continue
        best = max(by_var[var], key=lambda x: x[1]["sharpe_ratio"])
        val, m = best
        print(f"  {var:<20} {str(val):>12} {m['sharpe_ratio']:>8.2f} "
              f"{m['total_r']:>8.1f} {m['max_drawdown_r']:>8.1f} {m['total_trades']:>8}")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
