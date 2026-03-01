#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 2: finer grids + untested dimensions.

Base config: WF mode params from robust pipeline run.
  rr=2.0, tp1_ratio=0.5, stop_atr=10.0%, min_gap_atr=1.5%
  magnifier ON, continuation

Variables swept (one at a time, holding others at base):
  1. rr (finer):          1.25, 1.5, 1.75, 2.0*, 2.25, 2.5, 2.75, 3.0
  2. tp1_ratio (finer):   0.2, 0.3, 0.4, 0.5*, 0.6, 0.7, 0.8, 1.0
  3. stop_atr_pct (wider): 3, 5, 7.5, 10*, 12.5, 15, 17.5, 20, 25
  4. min_gap_atr_pct (finer): 0.5, 0.75, 1.0, 1.25, 1.5*, 2.0, 2.5, 3.0, 4.0
  5. Flat time:           14:30, 15:00, 15:30, 15:50*, 16:00
  6. Entry start delay:   09:45*, 10:00, 10:15, 10:30
  7. Day of week exclusion: none*, excl Mon, excl Tue, excl Wed, excl Thu, excl Fri

* = current base value
"""

import sys
import time
from dataclasses import replace

import pandas as pd

sys.path.insert(0, "src")

from orb_backtest.config import NY_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
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
        name="NQ NY Variable Sweep 2",
    )
    return with_overrides(config, **BASE_PARAMS)


def run_and_metric(df_5m, df_1m, config, gate_fn=None):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    if gate_fn:
        trades = gate_fn(trades)
    return compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Variable':>20} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*85}")
    print(f"  {title}")
    print(f"{'='*85}")
    print(HDR)
    print("-" * 85)


def print_row(i, label, m, is_base=False):
    marker = " <-- base" if is_base else ""
    print(
        f"{i:>3} {label:>20} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
        f"{m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} {m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def main():
    print("NQ NY ORB — Variable Sweeps Round 2 (magnifier)")
    print("=" * 85)
    print(f"Base: rr={BASE_PARAMS['rr']}, tp1={BASE_PARAMS['tp1_ratio']}, "
          f"stop={BASE_PARAMS['ny_stop_atr_pct']}%, gap={BASE_PARAMS['ny_min_gap_atr_pct']}%")

    # Load data
    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    base = make_base()
    all_results = []

    # ── 1. RR (finer) ─────────────────────────────────────────────────
    rr_values = [1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
    print_header(f"1. R:R RATIO (finer grid, base=2.0)")

    for i, rr in enumerate(rr_values, 1):
        config = with_overrides(base, rr=rr)
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (rr == 2.0)
        print_row(i, f"rr={rr:.2f}", m, is_base)
        all_results.append(("rr", rr, m))

    # ── 2. TP1 RATIO (finer) ──────────────────────────────────────────
    tp1_values = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    print_header(f"2. TP1 RATIO (finer grid, base=0.5)")

    for i, tp1 in enumerate(tp1_values, 1):
        config = with_overrides(base, tp1_ratio=tp1)
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (tp1 == 0.5)
        print_row(i, f"tp1={tp1:.1f}", m, is_base)
        all_results.append(("tp1_ratio", tp1, m))

    # ── 3. STOP ATR % (wider) ─────────────────────────────────────────
    stop_values = [3.0, 5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0, 25.0]
    print_header(f"3. STOP ATR % (wider range, base=10.0)")

    for i, stop in enumerate(stop_values, 1):
        config = with_overrides(base, ny_stop_atr_pct=stop)
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (stop == 10.0)
        print_row(i, f"stop={stop:.1f}%", m, is_base)
        all_results.append(("stop_atr_pct", stop, m))

    # ── 4. MIN GAP ATR % (finer) ──────────────────────────────────────
    gap_values = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]
    print_header(f"4. MIN GAP ATR % (finer grid, base=1.5)")

    for i, gap in enumerate(gap_values, 1):
        config = with_overrides(base, ny_min_gap_atr_pct=gap)
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (gap == 1.5)
        print_row(i, f"gap={gap:.2f}%", m, is_base)
        all_results.append(("min_gap_atr_pct", gap, m))

    # ── 5. FLAT TIME ──────────────────────────────────────────────────
    flat_times = [
        ("14:30", "14:30", "14:35"),
        ("15:00", "15:00", "15:05"),
        ("15:30", "15:30", "15:35"),
        ("15:50", "15:50", "16:00"),  # base
        ("16:00", "15:55", "16:00"),
    ]
    print_header(f"5. FLAT TIME (base=15:50)")

    for i, (label, flat_s, flat_e) in enumerate(flat_times, 1):
        sess = replace(base.sessions[0], flat_start=flat_s, flat_end=flat_e)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (label == "15:50")
        print_row(i, f"flat={label}", m, is_base)
        all_results.append(("flat_time", label, m))

    # ── 6. ENTRY START DELAY ──────────────────────────────────────────
    entry_starts = ["09:45", "10:00", "10:15", "10:30"]
    print_header(f"6. ENTRY START (delay after ORB, base=09:45)")

    for i, es in enumerate(entry_starts, 1):
        sess = replace(base.sessions[0], entry_start=es)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (es == "09:45")
        print_row(i, f"start={es}", m, is_base)
        all_results.append(("entry_start", es, m))

    # ── 7. DAY OF WEEK EXCLUSION ──────────────────────────────────────
    DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    print_header(f"7. DAY OF WEEK EXCLUSION (base=none)")

    # No exclusion (base)
    m = run_and_metric(df_5m, df_1m, base)
    print_row(1, "excl=none", m, is_base=True)
    print_year_breakdown(m)
    all_results.append(("dow_excl", "none", m))

    for dow in range(5):
        def dow_gate(trades, _dow=dow):
            return [t for t in trades if t.exit_type != EXIT_NO_FILL
                    and pd.Timestamp(t.date).dayofweek != _dow]

        m = run_and_metric(df_5m, df_1m, base, gate_fn=dow_gate)
        label = f"excl={DOW_NAMES[dow]}"
        print_row(dow + 2, label, m)
        all_results.append(("dow_excl", DOW_NAMES[dow], m))

    # ── SUMMARY ───────────────────────────────────────────────────────
    print(f"\n{'='*85}")
    print(f"  SUMMARY — Best value per variable (by Sharpe)")
    print(f"{'='*85}")
    print(f"  {'Variable':<20} {'Best Value':>12} {'Sharpe':>8} {'Net R':>8} {'DD R':>8} {'Trades':>8}")
    print(f"  {'-'*68}")

    from collections import defaultdict
    by_var = defaultdict(list)
    for var, val, m in all_results:
        by_var[var].append((val, m))

    for var in ["rr", "tp1_ratio", "stop_atr_pct", "min_gap_atr_pct",
                "flat_time", "entry_start", "dow_excl"]:
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
