#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 12: fine-tune the R11 winner.

Winner: g=3.0 rr=2.25 tp1=0.7 stop=9.0% (Calmar 17.17, 16.5 R/yr, DD -10.6R)

Fine-tune each variable individually around the optimum:
  1. rr:        2.0 to 2.5 in 0.05 steps (11 values)
  2. tp1:       0.55 to 0.80 in 0.05 steps (6 values)
  3. gap:       2.5 to 3.5 in 0.1 steps (11 values)
  4. entry_end: 14:00 to 15:30 in 15min steps (7 values)
  5. stop:      8.5 to 9.5 in 0.1 steps (11 values) — reconfirm with new rr/tp1
  6. Best combo: stack any improvements and run final comparison

Base: long-only, 20m ORB, entry 09:50-15:00, stop=9%, magnifier
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import NY_SESSION, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
DATA_YEARS = 11

NY_20M = replace(
    NY_SESSION,
    orb_end="09:50",
    entry_start="09:50",
)

# R11 winner defaults
BASE = dict(gap=3.0, rr=2.25, tp1=0.7, stop=9.0, entry_end="15:00")


def make_config(gap=3.0, rr=2.25, tp1=0.7, stop=9.0, entry_end="15:00"):
    sess = replace(NY_20M,
                   entry_start="09:50",
                   entry_end=entry_end,
                   min_gap_atr_pct=gap,
                   stop_atr_pct=stop)
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=rr,
        tp1_ratio=tp1,
        name="NQ NY Fine-Tune R11",
    )


def run_and_metric(df_5m, df_1m, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
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


def print_row(i, label, m, marker=""):
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
    print("NQ NY ORB — Round 12: Fine-Tune R11 Winner (g3.0 rr2.25 tp0.7 stop=9%)")
    print("=" * 105)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    best_per_sweep = {}  # sweep_name -> (value, metrics)

    # ── 1. RR FINE SWEEP ────────────────────────────────────────────────
    rr_values = [2.0 + i * 0.05 for i in range(11)]  # 2.0 to 2.5
    print_header("1. RR FINE SWEEP (2.0-2.5 in 0.05 steps)")
    best_calmar = -999
    for i, rr in enumerate(rr_values, 1):
        config = make_config(rr=rr)
        m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if abs(rr - 2.25) < 0.001 else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['rr'] = (rr, m)
        print_row(i, f"rr={rr:.2f}", m, marker)
        if abs(rr - 2.25) < 0.001 or m['calmar_ratio'] == best_calmar:
            print_year_breakdown(m)
    br = best_per_sweep['rr']
    print(f"\n  >> Best rr: {br[0]:.2f} (Calmar {br[1]['calmar_ratio']:.2f})")

    # ── 2. TP1 FINE SWEEP ───────────────────────────────────────────────
    tp1_values = [0.55 + i * 0.05 for i in range(6)]  # 0.55 to 0.80
    print_header("2. TP1 FINE SWEEP (0.55-0.80 in 0.05 steps)")
    best_calmar = -999
    for i, tp1 in enumerate(tp1_values, 1):
        config = make_config(tp1=tp1)
        m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if abs(tp1 - 0.7) < 0.001 else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['tp1'] = (tp1, m)
        print_row(i, f"tp1={tp1:.2f}", m, marker)
        if abs(tp1 - 0.7) < 0.001 or m['calmar_ratio'] == best_calmar:
            print_year_breakdown(m)
    bt = best_per_sweep['tp1']
    print(f"\n  >> Best tp1: {bt[0]:.2f} (Calmar {bt[1]['calmar_ratio']:.2f})")

    # ── 3. GAP FINE SWEEP ───────────────────────────────────────────────
    gap_values = [2.5 + i * 0.1 for i in range(11)]  # 2.5 to 3.5
    print_header("3. GAP FINE SWEEP (2.5-3.5 in 0.1 steps)")
    best_calmar = -999
    for i, gap in enumerate(gap_values, 1):
        config = make_config(gap=gap)
        m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if abs(gap - 3.0) < 0.001 else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['gap'] = (gap, m)
        print_row(i, f"gap={gap:.1f}%", m, marker)
        if abs(gap - 3.0) < 0.001 or m['calmar_ratio'] == best_calmar:
            print_year_breakdown(m)
    bg = best_per_sweep['gap']
    print(f"\n  >> Best gap: {bg[0]:.1f}% (Calmar {bg[1]['calmar_ratio']:.2f})")

    # ── 4. ENTRY END FINE SWEEP ─────────────────────────────────────────
    entry_ends = ["14:00", "14:15", "14:30", "14:45", "15:00", "15:15", "15:30"]
    print_header("4. ENTRY END FINE SWEEP (14:00-15:30 in 15min steps)")
    best_calmar = -999
    for i, ee in enumerate(entry_ends, 1):
        config = make_config(entry_end=ee)
        m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if ee == "15:00" else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['entry_end'] = (ee, m)
        print_row(i, f"end={ee}", m, marker)
        if ee == "15:00" or m['calmar_ratio'] == best_calmar:
            print_year_breakdown(m)
    be = best_per_sweep['entry_end']
    print(f"\n  >> Best entry_end: {be[0]} (Calmar {be[1]['calmar_ratio']:.2f})")

    # ── 5. STOP RE-CONFIRM ──────────────────────────────────────────────
    stop_values = [8.5 + i * 0.1 for i in range(11)]  # 8.5 to 9.5
    print_header("5. STOP RE-CONFIRM (8.5-9.5 in 0.1 steps)")
    best_calmar = -999
    for i, stop in enumerate(stop_values, 1):
        config = make_config(stop=stop)
        m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if abs(stop - 9.0) < 0.001 else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['stop'] = (stop, m)
        print_row(i, f"stop={stop:.1f}%", m, marker)
        if abs(stop - 9.0) < 0.001 or m['calmar_ratio'] == best_calmar:
            print_year_breakdown(m)
    bs = best_per_sweep['stop']
    print(f"\n  >> Best stop: {bs[0]:.1f}% (Calmar {bs[1]['calmar_ratio']:.2f})")

    # ── 6. STACKED IMPROVEMENTS ─────────────────────────────────────────
    # Collect best values from each sweep
    best_rr = best_per_sweep['rr'][0]
    best_tp1 = best_per_sweep['tp1'][0]
    best_gap = best_per_sweep['gap'][0]
    best_ee = best_per_sweep['entry_end'][0]
    best_stop = best_per_sweep['stop'][0]

    print_header("6. STACKED IMPROVEMENTS")

    combos = [
        ("R11 base",
         dict(gap=3.0, rr=2.25, tp1=0.7, stop=9.0, entry_end="15:00")),
        (f"best rr={best_rr:.2f}",
         dict(gap=3.0, rr=best_rr, tp1=0.7, stop=9.0, entry_end="15:00")),
        (f"best tp1={best_tp1:.2f}",
         dict(gap=3.0, rr=2.25, tp1=best_tp1, stop=9.0, entry_end="15:00")),
        (f"best gap={best_gap:.1f}%",
         dict(gap=best_gap, rr=2.25, tp1=0.7, stop=9.0, entry_end="15:00")),
        (f"best end={best_ee}",
         dict(gap=3.0, rr=2.25, tp1=0.7, stop=9.0, entry_end=best_ee)),
        (f"best stop={best_stop:.1f}%",
         dict(gap=3.0, rr=2.25, tp1=0.7, stop=best_stop, entry_end="15:00")),
        ("all best (stacked)",
         dict(gap=best_gap, rr=best_rr, tp1=best_tp1, stop=best_stop, entry_end=best_ee)),
        ("all best except entry_end",
         dict(gap=best_gap, rr=best_rr, tp1=best_tp1, stop=best_stop, entry_end="15:00")),
    ]

    # Also add the R11 #2 and #3 for reference
    combos.extend([
        ("R11 #2: rr3.0 tp0.6",
         dict(gap=3.0, rr=3.0, tp1=0.6, stop=9.0, entry_end="15:00")),
        ("R11 #3: rr2.75 tp0.7",
         dict(gap=3.0, rr=2.75, tp1=0.7, stop=9.0, entry_end="15:00")),
    ])

    for i, (label, params) in enumerate(combos, 1):
        config = make_config(**params)
        m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- base" if label == "R11 base" else ""
        print_row(i, label, m, marker)
        print_year_breakdown(m)

    # ── SUMMARY ──────────────────────────────────────────────────────────
    print(f"\n{'='*105}")
    print(f"  SUMMARY — Best per variable")
    print(f"{'='*105}")
    print(f"  {'Variable':<15} {'Current':>10} {'Best':>10} {'Calmar delta':>14}")
    print(f"  {'-'*50}")

    base_calmar = 17.17  # R11 base
    for var in ['rr', 'tp1', 'gap', 'entry_end', 'stop']:
        val, m = best_per_sweep[var]
        current = BASE[var] if var != 'entry_end' else BASE['entry_end']
        delta = m['calmar_ratio'] - base_calmar
        changed = "" if str(val) == str(current) else " *"
        print(f"  {var:<15} {str(current):>10} {str(val):>10} {delta:>+13.2f}{changed}")

    elapsed = time.time() - t_start
    print(f"\n{'='*105}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*105}")


if __name__ == "__main__":
    main()
