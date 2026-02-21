#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 3: more dimensions.

Base config: WF mode params from robust pipeline run.
  rr=2.0, tp1_ratio=0.5, stop_atr=10.0%, min_gap_atr=1.5%
  magnifier ON, continuation

Variables swept:
  1.  ORB window fine:       5m, 10m, 15m*, 20m, 25m, 30m
  2.  ORB start time:        09:25, 09:30*, 09:35
  3.  Strategy type:         continuation*, reversal, inversion
  4.  Multi-day exclusions:  none*, Thu+Fri, Mon+Fri, Mon+Thu, Tue+Thu, Wed+Fri
  5.  Excl-Friday deep:      no excl* | excl-Fri | excl-Fri (long-only) | excl-Thu (long-only)
  6.  Long-only key vars:    rr sweep with dir=long
  7.  Long-only ORB sweep:   5m, 10m, 15m, 20m, 25m, 30m with dir=long
  8.  Long-only entry end:   10:30, 11:00, 11:30, 12:00, 12:30, 13:00 with dir=long
  9.  Long-only max_gap_atr: 0, 3, 5, 7.5, 10 with dir=long
  10. Half-day handling:     include* vs exclude

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

BASE_PARAMS = {
    "rr": 2.0,
    "tp1_ratio": 0.5,
    "ny_stop_atr_pct": 10.0,
    "ny_min_gap_atr_pct": 1.5,
}

# Known half-day dates (early close at 13:00 ET)
HALF_DAYS = (
    "20150109", "20150703", "20151127", "20151224",
    "20160128", "20160701", "20161125", "20161223",
    "20170109", "20170703", "20171124", "20171222",
    "20180109", "20180703", "20181123", "20181224",
    "20190109", "20190703", "20191129", "20191224",
    "20200109", "20200703", "20201127", "20201224",
    "20210109", "20210702", "20211126", "20211223",
    "20220109", "20220701", "20221125", "20221223",
    "20230109", "20230703", "20231124", "20231222",
    "20240109", "20240703", "20241129", "20241224",
    "20250109", "20250703", "20251128", "20251224",
    "20260109",
)


def make_base(**extra):
    config = StrategyConfig(
        sessions=(NY_SESSION,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        name="NQ NY Variable Sweep 3",
    )
    params = {**BASE_PARAMS, **extra}
    return with_overrides(config, **params)


def run_and_metric(df_5m, df_1m, config, gate_fn=None):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    if gate_fn:
        trades = gate_fn(trades)
    return compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Variable':>24} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")
    print(HDR)
    print("-" * 90)


def print_row(i, label, m, is_base=False):
    marker = " <-- base" if is_base else ""
    print(
        f"{i:>3} {label:>24} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
        f"{m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} {m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def main():
    print("NQ NY ORB — Variable Sweeps Round 3 (magnifier)")
    print("=" * 90)
    print(f"Base: rr={BASE_PARAMS['rr']}, tp1={BASE_PARAMS['tp1_ratio']}, "
          f"stop={BASE_PARAMS['ny_stop_atr_pct']}%, gap={BASE_PARAMS['ny_min_gap_atr_pct']}%")

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    base = make_base()

    # ── 1. ORB WINDOW FINE ────────────────────────────────────────────
    orb_windows = [
        ("5m",  "09:30", "09:35", "09:35"),
        ("10m", "09:30", "09:40", "09:40"),
        ("15m", "09:30", "09:45", "09:45"),
        ("20m", "09:30", "09:50", "09:50"),
        ("25m", "09:30", "09:55", "09:55"),
        ("30m", "09:30", "10:00", "10:00"),
    ]
    print_header("1. ORB WINDOW FINE (5m to 30m, base=15m)")

    for i, (label, orb_s, orb_e, entry_s) in enumerate(orb_windows, 1):
        sess = replace(base.sessions[0], orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"orb={label}", m, is_base=(label == "15m"))

    # ── 2. ORB START TIME ─────────────────────────────────────────────
    orb_starts = [
        ("09:25", "09:25", "09:40", "09:40"),
        ("09:30", "09:30", "09:45", "09:45"),
        ("09:35", "09:35", "09:50", "09:50"),
    ]
    print_header("2. ORB START TIME (15m window, shifted, base=09:30)")

    for i, (label, orb_s, orb_e, entry_s) in enumerate(orb_starts, 1):
        sess = replace(base.sessions[0], orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"start={label}", m, is_base=(label == "09:30"))

    # ── 3. STRATEGY TYPE ──────────────────────────────────────────────
    strategies = ["continuation", "reversal", "inversion"]
    print_header("3. STRATEGY TYPE (base=continuation)")

    for i, strat in enumerate(strategies, 1):
        config = with_overrides(base, strategy=strat)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"strat={strat}", m, is_base=(strat == "continuation"))
        print_year_breakdown(m)

    # ── 4. MULTI-DAY EXCLUSIONS ───────────────────────────────────────
    DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    multi_excl = [
        ("none",      set()),
        ("Thu+Fri",   {3, 4}),
        ("Mon+Fri",   {0, 4}),
        ("Mon+Thu",   {0, 3}),
        ("Tue+Thu",   {1, 3}),
        ("Wed+Fri",   {2, 4}),
        ("Mon+Wed",   {0, 2}),
        ("Mon only",  {0}),
        ("Fri only",  {4}),
        ("Thu only",  {3}),
    ]
    print_header("4. MULTI-DAY EXCLUSIONS (base=none)")

    for i, (label, excl_days) in enumerate(multi_excl, 1):
        if excl_days:
            def gate(trades, _days=excl_days):
                return [t for t in trades if t.exit_type != EXIT_NO_FILL
                        and pd.Timestamp(t.date).dayofweek not in _days]
        else:
            gate = None
        m = run_and_metric(df_5m, df_1m, base, gate_fn=gate)
        print_row(i, f"excl={label}", m, is_base=(label == "none"))

    # ── 5. DIRECTION + DAY COMBOS ─────────────────────────────────────
    print_header("5. DIRECTION + DAY EXCLUSION COMBOS")

    combos_5 = [
        ("both, no excl",    "both",  set()),
        ("long, no excl",    "long",  set()),
        ("long, excl-Thu",   "long",  {3}),
        ("long, excl-Fri",   "long",  {4}),
        ("long, excl-Thu+Fri", "long", {3, 4}),
        ("long, excl-Mon",   "long",  {0}),
        ("short, no excl",   "short", set()),
        ("short, excl-Mon",  "short", {0}),
        ("short, excl-Fri",  "short", {4}),
    ]
    for i, (label, direction, excl_days) in enumerate(combos_5, 1):
        config = with_overrides(base, direction_filter=direction)
        if excl_days:
            def gate(trades, _days=excl_days):
                return [t for t in trades if t.exit_type != EXIT_NO_FILL
                        and pd.Timestamp(t.date).dayofweek not in _days]
        else:
            gate = None
        m = run_and_metric(df_5m, df_1m, config, gate_fn=gate)
        print_row(i, label, m, is_base=(label == "both, no excl"))
        if "long" in label:
            print_year_breakdown(m)

    # ── 6. LONG-ONLY RR SWEEP ────────────────────────────────────────
    rr_values = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5]
    print_header("6. LONG-ONLY R:R SWEEP")

    for i, rr in enumerate(rr_values, 1):
        config = with_overrides(base, rr=rr, direction_filter="long")
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long rr={rr:.2f}", m, is_base=(rr == 2.0))

    # ── 7. LONG-ONLY ORB WINDOW ──────────────────────────────────────
    print_header("7. LONG-ONLY ORB WINDOW (5m to 30m)")

    for i, (label, orb_s, orb_e, entry_s) in enumerate(orb_windows, 1):
        sess = replace(base.sessions[0], orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        config = replace(base, sessions=(sess,))
        config = with_overrides(config, direction_filter="long")
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long orb={label}", m, is_base=(label == "15m"))

    # ── 8. LONG-ONLY ENTRY END ────────────────────────────────────────
    entry_ends = ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "14:00"]
    print_header("8. LONG-ONLY ENTRY END TIME")

    for i, ee in enumerate(entry_ends, 1):
        sess = replace(base.sessions[0], entry_end=ee)
        config = replace(base, sessions=(sess,))
        config = with_overrides(config, direction_filter="long")
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long end={ee}", m, is_base=(ee == "13:00"))

    # ── 9. LONG-ONLY MAX GAP ATR ─────────────────────────────────────
    mga_values = [0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0]
    print_header("9. LONG-ONLY MAX GAP ATR % (0=disabled)")

    for i, mga in enumerate(mga_values, 1):
        sess = replace(base.sessions[0], max_gap_atr_pct=mga)
        config = replace(base, sessions=(sess,))
        config = with_overrides(config, direction_filter="long")
        m = run_and_metric(df_5m, df_1m, config)
        label = f"long mga={mga}%" if mga > 0 else "long mga=OFF"
        print_row(i, label, m, is_base=(mga == 0))

    # ── 10. LONG-ONLY STOP ATR ────────────────────────────────────────
    stop_values = [5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0]
    print_header("10. LONG-ONLY STOP ATR %")

    for i, stop in enumerate(stop_values, 1):
        config = with_overrides(base, ny_stop_atr_pct=stop, direction_filter="long")
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long stop={stop}%", m, is_base=(stop == 10.0))

    # ── 11. LONG-ONLY TP1 RATIO ──────────────────────────────────────
    tp1_values = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    print_header("11. LONG-ONLY TP1 RATIO")

    for i, tp1 in enumerate(tp1_values, 1):
        config = with_overrides(base, tp1_ratio=tp1, direction_filter="long")
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long tp1={tp1}", m, is_base=(tp1 == 0.5))

    # ── 12. LONG-ONLY MIN GAP ATR ────────────────────────────────────
    gap_values = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
    print_header("12. LONG-ONLY MIN GAP ATR %")

    for i, gap in enumerate(gap_values, 1):
        config = with_overrides(base, ny_min_gap_atr_pct=gap, direction_filter="long")
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long gap={gap}%", m, is_base=(gap == 1.5))

    # ── 13. HALF-DAY HANDLING ─────────────────────────────────────────
    print_header("13. HALF-DAY HANDLING (base=include)")

    # No half-day config (base)
    m_no = run_and_metric(df_5m, df_1m, base)
    print_row(1, "half_days=include", m_no, is_base=True)

    # Exclude half days
    config_hd = replace(base, excluded_dates=HALF_DAYS)
    m_hd = run_and_metric(df_5m, df_1m, config_hd)
    print_row(2, "half_days=exclude", m_hd)

    # Long-only with half-day exclusion
    config_hd_long = with_overrides(config_hd, direction_filter="long")
    m_hd_long = run_and_metric(df_5m, df_1m, config_hd_long)
    print_row(3, "long, half_days=excl", m_hd_long)

    # ── 14. LONG-ONLY ATR LENGTH ──────────────────────────────────────
    atr_values = [7, 10, 14, 20, 30, 50]
    print_header("14. LONG-ONLY ATR LENGTH")

    for i, atr in enumerate(atr_values, 1):
        config = with_overrides(base, direction_filter="long")
        config = replace(config, atr_length=atr)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long atr={atr}", m, is_base=(atr == 14))

    # ── 15. LONG-ONLY FLAT TIME ───────────────────────────────────────
    flat_times = [
        ("13:00", "13:00", "13:05"),
        ("14:00", "14:00", "14:05"),
        ("14:30", "14:30", "14:35"),
        ("15:00", "15:00", "15:05"),
        ("15:30", "15:30", "15:35"),
        ("15:50", "15:50", "16:00"),
    ]
    print_header("15. LONG-ONLY FLAT TIME")

    for i, (label, flat_s, flat_e) in enumerate(flat_times, 1):
        sess = replace(base.sessions[0], flat_start=flat_s, flat_end=flat_e)
        config = replace(base, sessions=(sess,))
        config = with_overrides(config, direction_filter="long")
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"long flat={label}", m, is_base=(label == "15:50"))

    # ── FINAL SUMMARY ─────────────────────────────────────────────────
    elapsed = time.time() - t_start
    print(f"\n{'='*90}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()
