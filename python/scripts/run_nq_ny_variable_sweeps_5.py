#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 5: stack DD-reducing improvements.

Objective: maximize R per year with the lowest drawdown (Calmar focus).

Stacking candidates from round 4 (all reduce DD):
  - entry_start=10:30  (Calmar 9.92, DD -14.1R)
  - entry_end=14:00    (Calmar 10.69, DD -13.2R)
  - gap=3.0%           (Calmar 9.84, DD -12.7R)
  - excl-Fri           (Calmar 9.90, DD -12.3R)
  - tp1=0.4            (Calmar 9.24, DD -11.4R)

Phase A: Test all stacking combos to find the best foundation.
Phase B: Full variable sweep against the best stacked base.
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
DATA_YEARS = 11  # 2015-2025 for R/year calc

NY_20M = replace(
    NY_SESSION,
    orb_end="09:50",
    entry_start="09:50",
)


def make_config(entry_start="09:50", entry_end="13:00", gap=1.5,
                rr=2.0, tp1=0.5, stop=10.0, **extra):
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
        direction_filter="long",
        rr=rr,
        tp1_ratio=tp1,
        name="NQ NY Stack Sweep",
    )
    if extra:
        config = with_overrides(config, **extra)
    return config


def excl_fri_gate(trades):
    return [t for t in trades if t.exit_type != EXIT_NO_FILL
            and pd.Timestamp(t.date).dayofweek != 4]


def excl_thu_fri_gate(trades):
    return [t for t in trades if t.exit_type != EXIT_NO_FILL
            and pd.Timestamp(t.date).dayofweek not in {3, 4}]


def run_and_metric(df_5m, df_1m, config, gate_fn=None):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    if gate_fn:
        trades = gate_fn(trades)
    return compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Config':>36} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Sharpe':>7} {'Net R':>7} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*110}")
    print(f"  {title}")
    print(f"{'='*110}")
    print(HDR)
    print("-" * 110)


def print_row(i, label, m, is_base=False):
    marker = " <--" if is_base else ""
    r_per_yr = m['total_r'] / DATA_YEARS
    print(
        f"{i:>3} {label:>36} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
        f"{r_per_yr:>6.1f} {m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} "
        f"{m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def main():
    print("NQ NY ORB — Round 5: Stack DD-Reducing Improvements")
    print("OBJECTIVE: Max R/year with lowest drawdown")
    print("=" * 110)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    # ══════════════════════════════════════════════════════════════════
    # PHASE A: STACKING COMBOS
    # ══════════════════════════════════════════════════════════════════
    print_header("PHASE A: STACKING COMBOS (sorted by Calmar)")

    combos = [
        # label, entry_start, entry_end, gap, rr, tp1, gate_fn
        ("R4 base",                          "09:50", "13:00", 1.5, 2.0, 0.5, None),
        # Single improvements
        ("+start 10:30",                     "10:30", "13:00", 1.5, 2.0, 0.5, None),
        ("+end 14:00",                       "09:50", "14:00", 1.5, 2.0, 0.5, None),
        ("+end 15:00",                       "09:50", "15:00", 1.5, 2.0, 0.5, None),
        ("+gap 3.0%",                        "09:50", "13:00", 3.0, 2.0, 0.5, None),
        ("+tp1 0.4",                         "09:50", "13:00", 1.5, 2.0, 0.4, None),
        ("+excl-Fri",                        "09:50", "13:00", 1.5, 2.0, 0.5, excl_fri_gate),
        # Double stacks
        ("+start 10:30 +end 14:00",          "10:30", "14:00", 1.5, 2.0, 0.5, None),
        ("+start 10:30 +end 15:00",          "10:30", "15:00", 1.5, 2.0, 0.5, None),
        ("+start 10:30 +gap 3.0%",           "10:30", "13:00", 3.0, 2.0, 0.5, None),
        ("+end 14:00 +gap 3.0%",             "09:50", "14:00", 3.0, 2.0, 0.5, None),
        ("+end 15:00 +gap 3.0%",             "09:50", "15:00", 3.0, 2.0, 0.5, None),
        ("+start 10:30 +excl-Fri",           "10:30", "13:00", 1.5, 2.0, 0.5, excl_fri_gate),
        ("+end 14:00 +excl-Fri",             "09:50", "14:00", 1.5, 2.0, 0.5, excl_fri_gate),
        ("+gap 3.0% +excl-Fri",             "09:50", "13:00", 3.0, 2.0, 0.5, excl_fri_gate),
        ("+end 14:00 +tp1 0.4",             "09:50", "14:00", 1.5, 2.0, 0.4, None),
        ("+start 10:30 +tp1 0.4",           "10:30", "13:00", 1.5, 2.0, 0.4, None),
        ("+gap 3.0% +tp1 0.4",              "09:50", "13:00", 3.0, 2.0, 0.4, None),
        # Triple stacks
        ("+s10:30 +e14:00 +gap3%",           "10:30", "14:00", 3.0, 2.0, 0.5, None),
        ("+s10:30 +e15:00 +gap3%",           "10:30", "15:00", 3.0, 2.0, 0.5, None),
        ("+s10:30 +e14:00 +exFri",           "10:30", "14:00", 1.5, 2.0, 0.5, excl_fri_gate),
        ("+s10:30 +gap3% +exFri",            "10:30", "13:00", 3.0, 2.0, 0.5, excl_fri_gate),
        ("+e14:00 +gap3% +exFri",            "09:50", "14:00", 3.0, 2.0, 0.5, excl_fri_gate),
        ("+s10:30 +e14:00 +tp1.4",           "10:30", "14:00", 1.5, 2.0, 0.4, None),
        ("+e14:00 +gap3% +tp1.4",            "09:50", "14:00", 3.0, 2.0, 0.4, None),
        ("+e15:00 +gap3% +tp1.4",            "09:50", "15:00", 3.0, 2.0, 0.4, None),
        # Quad stacks
        ("+s10:30 +e14:00 +gap3% +exFri",    "10:30", "14:00", 3.0, 2.0, 0.5, excl_fri_gate),
        ("+s10:30 +e15:00 +gap3% +exFri",    "10:30", "15:00", 3.0, 2.0, 0.5, excl_fri_gate),
        ("+s10:30 +e14:00 +gap3% +tp1.4",    "10:30", "14:00", 3.0, 2.0, 0.4, None),
        ("+e14:00 +gap3% +exFri +tp1.4",     "09:50", "14:00", 3.0, 2.0, 0.4, excl_fri_gate),
        # Full stack
        ("+s10:30 +e14 +g3 +exFri +tp1.4",   "10:30", "14:00", 3.0, 2.0, 0.4, excl_fri_gate),
        ("+s10:30 +e15 +g3 +exFri +tp1.4",   "10:30", "15:00", 3.0, 2.0, 0.4, excl_fri_gate),
    ]

    results_a = []
    for i, (label, es, ee, gap, rr, tp1, gate) in enumerate(combos, 1):
        config = make_config(entry_start=es, entry_end=ee, gap=gap, rr=rr, tp1=tp1)
        m = run_and_metric(df_5m, df_1m, config, gate_fn=gate)
        is_base = (label == "R4 base")
        print_row(i, label, m, is_base)
        if m['total_trades'] >= 50:
            print_year_breakdown(m)
        results_a.append((label, es, ee, gap, rr, tp1, gate, m))

    # Rank by Calmar (R/year per unit DD)
    print(f"\n--- TOP 10 BY CALMAR (R/year ÷ MaxDD) ---")
    ranked = sorted(results_a, key=lambda x: x[7]['calmar_ratio'], reverse=True)
    print(f"{'#':>3} {'Config':>36} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'Trades':>7}")
    print("-" * 70)
    for i, (label, *_, m) in enumerate(ranked[:10], 1):
        r_per_yr = m['total_r'] / DATA_YEARS
        print(f"{i:>3} {label:>36} {r_per_yr:>6.1f} {m['max_drawdown_r']:>7.1f} "
              f"{m['calmar_ratio']:>7.2f} {m['total_trades']:>7}")

    # Pick best foundation for Phase B
    # Filter: need at least 500 trades for WF viability
    viable = [(l, es, ee, g, rr, tp1, gate, m) for l, es, ee, g, rr, tp1, gate, m in ranked
              if m['total_trades'] >= 500]
    best = viable[0]
    best_label, best_es, best_ee, best_gap, best_rr, best_tp1, best_gate, best_m = best

    print(f"\n  BEST VIABLE: {best_label}")
    print(f"  R/yr={best_m['total_r']/DATA_YEARS:.1f}, DD={best_m['max_drawdown_r']:.1f}R, "
          f"Calmar={best_m['calmar_ratio']:.2f}, Trades={best_m['total_trades']}")

    # ══════════════════════════════════════════════════════════════════
    # PHASE B: VARIABLE SWEEP AGAINST BEST STACKED BASE
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'='*110}")
    print(f"  PHASE B: VARIABLE SWEEP vs BEST STACKED BASE")
    print(f"  Base: {best_label}")
    print(f"{'='*110}")

    def make_best(**overrides):
        kw = dict(entry_start=best_es, entry_end=best_ee, gap=best_gap,
                  rr=best_rr, tp1=best_tp1)
        kw.update(overrides)
        return make_config(**kw)

    best_base = make_best()

    # ── B1. RR ────────────────────────────────────────────────────────
    rr_values = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5]
    print_header("B1. R:R RATIO")
    for i, rr in enumerate(rr_values, 1):
        config = make_best(rr=rr)
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"rr={rr:.2f}", m, is_base=(rr == best_rr))

    # ── B2. TP1 ───────────────────────────────────────────────────────
    tp1_values = [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7]
    print_header("B2. TP1 RATIO")
    for i, tp1 in enumerate(tp1_values, 1):
        config = make_best(tp1=tp1)
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"tp1={tp1:.2f}", m, is_base=(tp1 == best_tp1))

    # ── B3. STOP ATR ─────────────────────────────────────────────────
    stop_values = [5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0]
    print_header("B3. STOP ATR %")
    for i, stop in enumerate(stop_values, 1):
        config = make_best(stop=stop)
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"stop={stop}%", m, is_base=(stop == 10.0))

    # ── B4. MIN GAP ATR ──────────────────────────────────────────────
    gap_values = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    print_header("B4. MIN GAP ATR %")
    for i, gap in enumerate(gap_values, 1):
        config = make_best(gap=gap)
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"gap={gap}%", m, is_base=(gap == best_gap))

    # ── B5. ENTRY END (fine-tune) ─────────────────────────────────────
    end_values = ["12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]
    print_header("B5. ENTRY END TIME")
    for i, ee in enumerate(end_values, 1):
        config = make_best(entry_end=ee)
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"end={ee}", m, is_base=(ee == best_ee))

    # ── B6. ENTRY START (fine-tune) ───────────────────────────────────
    start_values = ["09:50", "10:00", "10:15", "10:30", "10:45", "11:00"]
    print_header("B6. ENTRY START")
    for i, es in enumerate(start_values, 1):
        config = make_best(entry_start=es)
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"start={es}", m, is_base=(es == best_es))

    # ── B7. ORB WINDOW ────────────────────────────────────────────────
    orb_windows = [
        ("15m", "09:30", "09:45"),
        ("20m", "09:30", "09:50"),
        ("25m", "09:30", "09:55"),
        ("30m", "09:30", "10:00"),
    ]
    print_header("B7. ORB WINDOW")
    for i, (label, orb_s, orb_e) in enumerate(orb_windows, 1):
        sess = replace(make_best().sessions[0], orb_start=orb_s, orb_end=orb_e)
        config = replace(make_best(), sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"orb={label}", m, is_base=(label == "20m"))

    # ── B8. ATR LENGTH ────────────────────────────────────────────────
    atr_values = [7, 10, 14, 20, 30, 50]
    print_header("B8. ATR LENGTH")
    for i, atr in enumerate(atr_values, 1):
        config = replace(make_best(), atr_length=atr)
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"atr={atr}", m, is_base=(atr == 14))

    # ── B9. MAX GAP POINTS ────────────────────────────────────────────
    mgp_values = [20, 30, 50, 75, 100, 150, 0]
    print_header("B9. MAX GAP POINTS (0=no limit)")
    for i, mg in enumerate(mgp_values, 1):
        sess = replace(make_best().sessions[0], max_gap_points=float(mg))
        config = replace(make_best(), sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        label = f"maxgap={mg}" if mg > 0 else "maxgap=OFF"
        print_row(i, label, m, is_base=(mg == 100))

    # ── B10. DAY EXCLUSIONS ───────────────────────────────────────────
    DOW = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    dow_combos = [
        ("gate only",     best_gate),
        ("+excl-Mon",     lambda t: [x for x in (best_gate(t) if best_gate else t)
                                     if pd.Timestamp(x.date).dayofweek != 0]),
        ("+excl-Thu",     lambda t: [x for x in (best_gate(t) if best_gate else t)
                                     if pd.Timestamp(x.date).dayofweek != 3]),
        ("+excl-Wed",     lambda t: [x for x in (best_gate(t) if best_gate else t)
                                     if pd.Timestamp(x.date).dayofweek != 2]),
    ]

    # Only add these if best_gate doesn't already exclude Fri
    if best_gate is not excl_fri_gate:
        dow_combos.append(
            ("+excl-Fri", lambda t: [x for x in (best_gate(t) if best_gate else t)
                                     if pd.Timestamp(x.date).dayofweek != 4])
        )

    print_header("B10. ADDITIONAL DAY EXCLUSIONS (on top of best gate)")
    for i, (label, gate) in enumerate(dow_combos, 1):
        m = run_and_metric(df_5m, df_1m, make_best(), gate_fn=gate)
        print_row(i, label, m, is_base=(label == "gate only"))
        print_year_breakdown(m)

    # ── B11. FLAT TIME ────────────────────────────────────────────────
    flat_times = [
        ("14:00", "14:00", "14:05"),
        ("14:30", "14:30", "14:35"),
        ("15:00", "15:00", "15:05"),
        ("15:30", "15:30", "15:35"),
        ("15:50", "15:50", "16:00"),
    ]
    print_header("B11. FLAT TIME")
    for i, (label, flat_s, flat_e) in enumerate(flat_times, 1):
        sess = replace(make_best().sessions[0], flat_start=flat_s, flat_end=flat_e)
        config = replace(make_best(), sessions=(sess,))
        m = run_and_metric(df_5m, df_1m, config, gate_fn=best_gate)
        print_row(i, f"flat={label}", m, is_base=(label == "15:50"))

    # ── FINAL SUMMARY ─────────────────────────────────────────────────
    elapsed = time.time() - t_start
    print(f"\n{'='*110}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*110}")


if __name__ == "__main__":
    main()
