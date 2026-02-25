#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 6: maximize R/year.

Objective: push R/year higher while keeping DD reasonable.

Levers tested:
  1. Higher RR (1.5 to 3.5) with current stacked base
  2. Add shorts back ("both" direction) with stacked improvements
  3. Lower gap + higher RR combos (gap × rr interaction grid)
  4. TP1 × RR interaction (higher RR may want different TP1)
  5. Stop × RR interaction
  6. "Both" direction with gap/rr/tp1 combos
  7. Entry end × RR interaction

Base: long-only, 20m ORB, entry 09:50-15:00, gap=3.0%, stop=10%, magnifier
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
DATA_YEARS = 11

NY_20M = replace(
    NY_SESSION,
    orb_end="09:50",
    entry_start="09:50",
)


def make_config(entry_start="09:50", entry_end="15:00", gap=3.0,
                rr=2.0, tp1=0.5, stop=10.0, direction="long", **extra):
    sess = replace(NY_20M,
                   entry_start=entry_start,
                   entry_end=entry_end,
                   min_gap_atr_pct=gap,
                   stop_atr_pct=stop)
    config = StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter=direction,
        rr=rr,
        tp1_ratio=tp1,
        name="NQ NY R/yr Sweep",
    )
    if extra:
        config = with_overrides(config, **extra)
    return config


def run_and_metric(df_5m, df_1m, config, gate_fn=None):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    if gate_fn:
        trades = gate_fn(trades)
    return compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Config':>40} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*105}")
    print(f"  {title}")
    print(f"{'='*105}")
    print(HDR)
    print("-" * 105)


def print_row(i, label, m, is_base=False):
    marker = " <--" if is_base else ""
    r_per_yr = m['total_r'] / DATA_YEARS
    print(
        f"{i:>3} {label:>40} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_per_yr:>6.1f} {m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} "
        f"{m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def main():
    print("NQ NY ORB — Round 6: Maximize R/year")
    print("=" * 105)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    # ── 1. RR SWEEP (long-only, full range) ───────────────────────────
    rr_values = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5]
    print_header("1. LONG-ONLY RR SWEEP (gap=3%, end=15:00)")
    for i, rr in enumerate(rr_values, 1):
        config = make_config(rr=rr)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long rr={rr:.2f}", m, is_base=(rr == 2.0))
        if rr in (2.0, 2.5, 2.75, 3.0, 3.5):
            print_year_breakdown(m)

    # ── 2. BOTH DIRECTION RR SWEEP ────────────────────────────────────
    print_header("2. BOTH DIRECTION RR SWEEP (gap=3%, end=15:00)")
    for i, rr in enumerate(rr_values, 1):
        config = make_config(rr=rr, direction="both")
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"both rr={rr:.2f}", m, is_base=(rr == 2.0))
        if rr in (2.0, 2.5, 2.75, 3.0, 3.5):
            print_year_breakdown(m)

    # ── 3. GAP × RR INTERACTION (long-only) ──────────────────────────
    gaps = [1.5, 2.0, 2.5, 3.0]
    rrs = [2.0, 2.25, 2.5, 2.75, 3.0, 3.5]
    print_header("3. GAP × RR INTERACTION (long-only, end=15:00)")
    idx = 1
    for gap in gaps:
        for rr in rrs:
            config = make_config(rr=rr, gap=gap)
            m = run_and_metric(df_5m, df_1m, config)
            is_base = (gap == 3.0 and rr == 2.0)
            print_row(idx, f"gap={gap}% rr={rr:.2f}", m, is_base)
            idx += 1
        print()  # separator between gap groups

    # ── 4. GAP × RR INTERACTION (both direction) ─────────────────────
    print_header("4. GAP × RR INTERACTION (both direction, end=15:00)")
    idx = 1
    for gap in gaps:
        for rr in rrs:
            config = make_config(rr=rr, gap=gap, direction="both")
            m = run_and_metric(df_5m, df_1m, config)
            print_row(idx, f"both gap={gap}% rr={rr:.2f}", m)
            idx += 1
        print()

    # ── 5. TP1 × RR (long-only, gap=3%) ──────────────────────────────
    tp1s = [0.3, 0.4, 0.5, 0.6, 0.7]
    rrs_tp1 = [2.0, 2.5, 3.0, 3.5]
    print_header("5. TP1 × RR INTERACTION (long, gap=3%, end=15:00)")
    idx = 1
    for tp1 in tp1s:
        for rr in rrs_tp1:
            config = make_config(rr=rr, tp1=tp1)
            m = run_and_metric(df_5m, df_1m, config)
            is_base = (tp1 == 0.5 and rr == 2.0)
            print_row(idx, f"tp1={tp1} rr={rr:.1f}", m, is_base)
            idx += 1
        print()

    # ── 6. STOP × RR (long-only, gap=3%) ─────────────────────────────
    stops = [7.5, 10.0, 12.5, 15.0]
    rrs_stop = [2.0, 2.5, 3.0, 3.5]
    print_header("6. STOP × RR INTERACTION (long, gap=3%, end=15:00)")
    idx = 1
    for stop in stops:
        for rr in rrs_stop:
            config = make_config(rr=rr, stop=stop)
            m = run_and_metric(df_5m, df_1m, config)
            is_base = (stop == 10.0 and rr == 2.0)
            print_row(idx, f"stop={stop}% rr={rr:.1f}", m, is_base)
            idx += 1
        print()

    # ── 7. ENTRY END × RR (long-only, gap=3%) ────────────────────────
    ends = ["12:00", "13:00", "14:00", "15:00"]
    rrs_end = [2.0, 2.5, 3.0, 3.5]
    print_header("7. ENTRY END × RR (long, gap=3%, end varies)")
    idx = 1
    for ee in ends:
        for rr in rrs_end:
            config = make_config(rr=rr, entry_end=ee)
            m = run_and_metric(df_5m, df_1m, config)
            is_base = (ee == "15:00" and rr == 2.0)
            print_row(idx, f"end={ee} rr={rr:.1f}", m, is_base)
            idx += 1
        print()

    # ── 8. BEST COMBOS (cherry-picked from above) ────────────────────
    print_header("8. BEST R/yr COMBOS (long + both, with year breakdown)")
    best_combos = [
        # label, direction, rr, gap, tp1, stop, entry_end
        ("R5 base (long g3 rr2)",           "long", 2.0,  3.0, 0.5, 10.0, "15:00"),
        ("long g3 rr2.5",                   "long", 2.5,  3.0, 0.5, 10.0, "15:00"),
        ("long g3 rr2.75",                  "long", 2.75, 3.0, 0.5, 10.0, "15:00"),
        ("long g3 rr3.0",                   "long", 3.0,  3.0, 0.5, 10.0, "15:00"),
        ("long g3 rr3.5",                   "long", 3.5,  3.0, 0.5, 10.0, "15:00"),
        ("long g2 rr2.5",                   "long", 2.5,  2.0, 0.5, 10.0, "15:00"),
        ("long g2 rr3.0",                   "long", 3.0,  2.0, 0.5, 10.0, "15:00"),
        ("long g2 rr3.5",                   "long", 3.5,  2.0, 0.5, 10.0, "15:00"),
        ("long g1.5 rr2.5",                 "long", 2.5,  1.5, 0.5, 10.0, "15:00"),
        ("long g1.5 rr3.0",                 "long", 3.0,  1.5, 0.5, 10.0, "15:00"),
        ("both g3 rr2.5",                   "both", 2.5,  3.0, 0.5, 10.0, "15:00"),
        ("both g3 rr3.0",                   "both", 3.0,  3.0, 0.5, 10.0, "15:00"),
        ("both g2 rr2.5",                   "both", 2.5,  2.0, 0.5, 10.0, "15:00"),
        ("both g2 rr3.0",                   "both", 3.0,  2.0, 0.5, 10.0, "15:00"),
        ("both g1.5 rr2.5",                 "both", 2.5,  1.5, 0.5, 10.0, "15:00"),
        ("both g1.5 rr3.0",                 "both", 3.0,  1.5, 0.5, 10.0, "15:00"),
        # tp1 variants
        ("long g3 rr3.0 tp1=0.4",           "long", 3.0,  3.0, 0.4, 10.0, "15:00"),
        ("long g3 rr3.5 tp1=0.4",           "long", 3.5,  3.0, 0.4, 10.0, "15:00"),
        ("long g2 rr3.0 tp1=0.4",           "long", 3.0,  2.0, 0.4, 10.0, "15:00"),
        ("both g3 rr3.0 tp1=0.4",           "both", 3.0,  3.0, 0.4, 10.0, "15:00"),
    ]
    for i, (label, d, rr, gap, tp1, stop, ee) in enumerate(best_combos, 1):
        config = make_config(rr=rr, gap=gap, tp1=tp1, stop=stop, direction=d, entry_end=ee)
        m = run_and_metric(df_5m, df_1m, config)
        is_base = (label == "R5 base (long g3 rr2)")
        print_row(i, label, m, is_base)
        print_year_breakdown(m)

    elapsed = time.time() - t_start
    print(f"\n{'='*105}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*105}")


if __name__ == "__main__":
    main()
