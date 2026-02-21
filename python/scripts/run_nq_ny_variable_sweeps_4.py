#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 4: combined winners as new base.

Combined base from rounds 1-3:
  - Direction: long-only (Sharpe 1.63 → biggest single lever)
  - ORB window: 20m (09:30-09:50) (Sharpe 1.44 both, 1.68 long)
  - rr=2.0, tp1=0.5, stop=10.0%, gap=1.5% (confirmed optimal)
  - magnifier ON, continuation

Re-sweep all variables against this improved base to see if the landscape shifts.
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

# New combined base: long-only + 20m ORB
NY_20M = replace(
    NY_SESSION,
    orb_end="09:50",
    entry_start="09:50",
)

BASE_PARAMS = {
    "rr": 2.0,
    "tp1_ratio": 0.5,
    "ny_stop_atr_pct": 10.0,
    "ny_min_gap_atr_pct": 1.5,
}


def make_base(**extra):
    config = StrategyConfig(
        sessions=(NY_20M,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        name="NQ NY Long 20m Variable Sweep 4",
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
    print("NQ NY ORB — Variable Sweeps Round 4: Combined Winners Base")
    print("=" * 90)
    print("NEW BASE: long-only, 20m ORB (09:30-09:50), continuation, magnifier")
    print(f"Params: rr={BASE_PARAMS['rr']}, tp1={BASE_PARAMS['tp1_ratio']}, "
          f"stop={BASE_PARAMS['ny_stop_atr_pct']}%, gap={BASE_PARAMS['ny_min_gap_atr_pct']}%")

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    base = make_base()

    # ── 0. BASELINE ───────────────────────────────────────────────────
    print_header("0. BASELINE (long-only, 20m ORB)")
    m_base = run_and_metric(df_5m, df_1m, base)
    print_row(1, "BASELINE", m_base, is_base=True)
    print_year_breakdown(m_base)

    # ── 1. R:R RATIO ─────────────────────────────────────────────────
    rr_values = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5]
    print_header("1. R:R RATIO (base=2.0)")

    for i, rr in enumerate(rr_values, 1):
        config = with_overrides(base, rr=rr)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"rr={rr:.2f}", m, is_base=(rr == 2.0))

    # ── 2. TP1 RATIO ─────────────────────────────────────────────────
    tp1_values = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    print_header("2. TP1 RATIO (base=0.5)")

    for i, tp1 in enumerate(tp1_values, 1):
        config = with_overrides(base, tp1_ratio=tp1)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"tp1={tp1}", m, is_base=(tp1 == 0.5))

    # ── 3. STOP ATR % ────────────────────────────────────────────────
    stop_values = [5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0]
    print_header("3. STOP ATR % (base=10.0)")

    for i, stop in enumerate(stop_values, 1):
        config = with_overrides(base, ny_stop_atr_pct=stop)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"stop={stop}%", m, is_base=(stop == 10.0))

    # ── 4. MIN GAP ATR % ─────────────────────────────────────────────
    gap_values = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    print_header("4. MIN GAP ATR % (base=1.5)")

    for i, gap in enumerate(gap_values, 1):
        config = with_overrides(base, ny_min_gap_atr_pct=gap)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"gap={gap}%", m, is_base=(gap == 1.5))

    # ── 5. MAX GAP ATR % ─────────────────────────────────────────────
    mga_values = [0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0]
    print_header("5. MAX GAP ATR % (0=disabled/base)")

    for i, mga in enumerate(mga_values, 1):
        sess = replace(base.sessions[0], max_gap_atr_pct=mga)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        label = f"maxgap_atr={mga}%" if mga > 0 else "maxgap_atr=OFF"
        print_row(i, label, m, is_base=(mga == 0))

    # ── 6. MAX GAP POINTS ────────────────────────────────────────────
    mgp_values = [20, 30, 40, 50, 75, 100, 150, 0]
    print_header("6. MAX GAP POINTS (0=no limit, base=100)")

    for i, mg in enumerate(mgp_values, 1):
        sess = replace(base.sessions[0], max_gap_points=float(mg))
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        label = f"maxgap={mg}" if mg > 0 else "maxgap=OFF"
        print_row(i, label, m, is_base=(mg == 100))

    # ── 7. ATR LENGTH ─────────────────────────────────────────────────
    atr_values = [7, 10, 14, 20, 30, 50]
    print_header("7. ATR LENGTH (base=14)")

    for i, atr in enumerate(atr_values, 1):
        config = replace(base, atr_length=atr)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"atr={atr}", m, is_base=(atr == 14))

    # ── 8. ORB WINDOW (fine-tune around 20m) ──────────────────────────
    orb_windows = [
        ("15m", "09:30", "09:45", "09:45"),
        ("20m", "09:30", "09:50", "09:50"),
        ("25m", "09:30", "09:55", "09:55"),
        ("30m", "09:30", "10:00", "10:00"),
        # Shifted starts
        ("20m @09:35", "09:35", "09:55", "09:55"),
        ("20m @09:25", "09:25", "09:45", "09:45"),
        ("25m @09:35", "09:35", "10:00", "10:00"),
    ]
    print_header("8. ORB WINDOW (fine-tune + shifted starts)")

    for i, (label, orb_s, orb_e, entry_s) in enumerate(orb_windows, 1):
        sess = replace(base.sessions[0], orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"orb={label}", m, is_base=(label == "20m"))

    # ── 9. ENTRY END TIME ─────────────────────────────────────────────
    entry_ends = ["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "14:00", "15:00"]
    print_header("9. ENTRY END TIME (base=13:00)")

    for i, ee in enumerate(entry_ends, 1):
        sess = replace(base.sessions[0], entry_end=ee)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"end={ee}", m, is_base=(ee == "13:00"))

    # ── 10. FLAT TIME ─────────────────────────────────────────────────
    flat_times = [
        ("13:00", "13:00", "13:05"),
        ("14:00", "14:00", "14:05"),
        ("15:00", "15:00", "15:05"),
        ("15:30", "15:30", "15:35"),
        ("15:50", "15:50", "16:00"),
    ]
    print_header("10. FLAT TIME (base=15:50)")

    for i, (label, flat_s, flat_e) in enumerate(flat_times, 1):
        sess = replace(base.sessions[0], flat_start=flat_s, flat_end=flat_e)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"flat={label}", m, is_base=(label == "15:50"))

    # ── 11. DAY OF WEEK EXCLUSIONS ────────────────────────────────────
    DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    dow_combos = [
        ("none",      set()),
        ("Mon",       {0}),
        ("Tue",       {1}),
        ("Wed",       {2}),
        ("Thu",       {3}),
        ("Fri",       {4}),
        ("Thu+Fri",   {3, 4}),
        ("Mon+Fri",   {0, 4}),
        ("Mon+Thu",   {0, 3}),
        ("Wed+Fri",   {2, 4}),
    ]
    print_header("11. DAY OF WEEK EXCLUSIONS (base=none)")

    for i, (label, excl_days) in enumerate(dow_combos, 1):
        if excl_days:
            def gate(trades, _days=excl_days):
                return [t for t in trades if t.exit_type != EXIT_NO_FILL
                        and pd.Timestamp(t.date).dayofweek not in _days]
        else:
            gate = None
        m = run_and_metric(df_5m, df_1m, base, gate_fn=gate)
        print_row(i, f"excl={label}", m, is_base=(label == "none"))
        if label in ("none", "Thu+Fri", "Fri"):
            print_year_breakdown(m)

    # ── 12. DIRECTION COMPARISON (sanity check) ───────────────────────
    print_header("12. DIRECTION (sanity check with 20m ORB)")

    for i, d in enumerate(["both", "long", "short"], 1):
        config = with_overrides(base, direction_filter=d)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"dir={d}", m, is_base=(d == "long"))
        print_year_breakdown(m)

    # ── 13. ENTRY START DELAY ─────────────────────────────────────────
    entry_starts = ["09:50", "10:00", "10:15", "10:30"]
    print_header("13. ENTRY START DELAY (base=09:50 = ORB end)")

    for i, es in enumerate(entry_starts, 1):
        sess = replace(base.sessions[0], entry_start=es)
        config = replace(base, sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, f"start={es}", m, is_base=(es == "09:50"))

    # ── 14. HALF-DAY EXCLUSION ────────────────────────────────────────
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
    print_header("14. HALF-DAY HANDLING (base=include)")

    m_inc = run_and_metric(df_5m, df_1m, base)
    print_row(1, "half_days=include", m_inc, is_base=True)

    config_excl = replace(base, excluded_dates=HALF_DAYS)
    m_excl = run_and_metric(df_5m, df_1m, config_excl)
    print_row(2, "half_days=exclude", m_excl)

    # ── 15. RR + ORB INTERACTIONS ─────────────────────────────────────
    print_header("15. RR x ORB WINDOW INTERACTION")
    print(f"  (testing if optimal RR changes with ORB width)")

    orb_rr_combos = [
        ("15m rr=2.0",  "09:45", 2.0),
        ("15m rr=2.25", "09:45", 2.25),
        ("15m rr=2.5",  "09:45", 2.5),
        ("20m rr=2.0",  "09:50", 2.0),
        ("20m rr=2.25", "09:50", 2.25),
        ("20m rr=2.5",  "09:50", 2.5),
        ("25m rr=2.0",  "09:55", 2.0),
        ("25m rr=2.25", "09:55", 2.25),
        ("25m rr=2.5",  "09:55", 2.5),
        ("30m rr=2.0",  "10:00", 2.0),
        ("30m rr=2.25", "10:00", 2.25),
        ("30m rr=2.5",  "10:00", 2.5),
    ]
    for i, (label, orb_e, rr) in enumerate(orb_rr_combos, 1):
        sess = replace(base.sessions[0], orb_end=orb_e, entry_start=orb_e)
        config = replace(base, sessions=(sess,))
        config = with_overrides(config, rr=rr)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, label, m, is_base=(label == "20m rr=2.0"))

    # ── 16. STOP x RR INTERACTION ─────────────────────────────────────
    print_header("16. STOP x RR INTERACTION")

    stop_rr_combos = [
        ("stop=7.5 rr=2.0",   7.5,  2.0),
        ("stop=7.5 rr=2.25",  7.5,  2.25),
        ("stop=10 rr=2.0",    10.0, 2.0),
        ("stop=10 rr=2.25",   10.0, 2.25),
        ("stop=10 rr=2.5",    10.0, 2.5),
        ("stop=12.5 rr=2.0",  12.5, 2.0),
        ("stop=12.5 rr=2.25", 12.5, 2.25),
        ("stop=12.5 rr=2.5",  12.5, 2.5),
        ("stop=15 rr=2.0",    15.0, 2.0),
        ("stop=15 rr=2.25",   15.0, 2.25),
    ]
    for i, (label, stop, rr) in enumerate(stop_rr_combos, 1):
        config = with_overrides(base, ny_stop_atr_pct=stop, rr=rr)
        m = run_and_metric(df_5m, df_1m, config)
        print_row(i, label, m, is_base=(label == "stop=10 rr=2.0"))

    # ── SUMMARY ───────────────────────────────────────────────────────
    elapsed = time.time() - t_start
    print(f"\n{'='*90}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()
