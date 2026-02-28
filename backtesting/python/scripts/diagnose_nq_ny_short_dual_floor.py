#!/usr/bin/env python3
"""NQ NY Short — Diagnostic with min_stop_points=10 AND min_tp1_points=10.

Both stop and TP1 now have 10pt floors at the engine level.
"""

import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime
from statistics import median, mean

import numpy as np

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

EXIT_NAMES = {
    0: "NO_FILL", 1: "SL", 2: "TP1_TP2", 3: "TP1_BE",
    4: "TP1_EOD", 5: "EOD", 6: "TP2_SINGLE",
}

START_DATE = "2016-01-01"
DATA_YEARS = 10

BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=5.0,
    min_gap_atr_pct=2.0,
    stop_orb_pct=15.0,
    min_gap_orb_pct=7.0,
    min_stop_points=10.0,
    min_tp1_points=10.0,
)

BASE_CONFIG = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="short",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=14,
    impulse_close_filter=False,
)


def neg_year_set(m):
    current_year = str(datetime.now().year)
    return {yr for yr, r in m.get("r_by_year", {}).items() if r < 0 and str(yr) != current_year}


def median_stop_pts(trades):
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points for t in filled)


def print_detail(label, m, trades, config):
    filled = [t for t in trades if t.exit_type != 0]
    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
    neg = neg_year_set(m)
    med_pts = median_stop_pts(trades)
    rby = m.get("r_by_year", {})
    yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(rby.items()))

    # Compute actual TP1 distances from trade data
    tp1_dists = []
    for t in filled:
        tp1_dist = abs(t.tp1_price - t.entry_price)
        if tp1_dist > 0:
            tp1_dists.append(tp1_dist)

    et_c = Counter(t.exit_type for t in filled)

    print(f"\n  {label}")
    print(f"  {'─' * 70}")
    print(f"    Trades: {m['total_trades']:<6}  WR: {m['win_rate']:.1%}  PF: {m['profit_factor']:.2f}  "
          f"Sharpe: {m['sharpe_ratio']:.2f}  Calmar: {m['calmar_ratio']:.2f}")
    print(f"    Net R: {m['total_r']:.1f}  R/yr: {r_yr:.1f}  MaxDD: {m['max_drawdown_r']:.1f}R  "
          f"Neg years: {sorted(neg) if neg else 'none'}")
    print(f"    Median stop: {med_pts:.1f} pts  |  Median TP1 dist: "
          f"{median(tp1_dists):.1f} pts" if tp1_dists else "    no TP1 data")
    print(f"    R by year: {yr_str}")
    print(f"    Exits: SL={et_c.get(1,0)}, TP1_BE={et_c.get(3,0)}, "
          f"TP1_TP2={et_c.get(2,0)}, TP1_EOD={et_c.get(4,0)}, EOD={et_c.get(5,0)}")

    # TP1_BE R values
    tp1be = [t for t in filled if t.exit_type == 3]
    if tp1be:
        avg_be_r = mean(t.r_multiple for t in tp1be)
        print(f"    TP1_BE avg R: {avg_be_r:+.4f} (vs theoretical 0.225 with old tiny stops)")


def main():
    print("NQ NY SHORT — Dual Floor Diagnostic (min_stop=10pt, min_tp1=10pt)")
    print("=" * 80)

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time()-t0:.1f}s]")

    # ── PART 1: Compare all three modes ──
    print("\n" + "=" * 80)
    print("  PART 1: Impact of floors (rr=2.0, tp1=0.5)")
    print("=" * 80)

    configs = [
        ("No floors", replace(BASE_SESSION, min_stop_points=0.0, min_tp1_points=0.0)),
        ("Stop floor only (10pt)", replace(BASE_SESSION, min_tp1_points=0.0)),
        ("Both floors (10pt each)", BASE_SESSION),
    ]
    for label, sess in configs:
        cfg = replace(BASE_CONFIG, sessions=(sess,))
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)
        print_detail(label, m, trades, cfg)

    # ── PART 2: rr × tp1 sweep with BOTH floors ──
    print("\n" + "=" * 80)
    print("  PART 2: rr × tp1 sweep — BOTH floors at 10pt (no DOW filter)")
    print("=" * 80)

    print(f"\n  {'rr':>4} {'tp1':>5} {'Trades':>6} {'WR':>6} {'PF':>5} {'Sharpe':>7} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedStop':>8} {'MedTP1':>7} {'NegYrs':>6}")
    print(f"  {'─' * 100}")

    for rr in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        for tp1 in [0.3, 0.4, 0.5, 0.6, 0.7]:
            cfg = replace(BASE_CONFIG, rr=rr, tp1_ratio=tp1)
            trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
            m = compute_metrics(trades)
            filled = [t for t in trades if t.exit_type != 0]
            med_stop = median_stop_pts(trades)
            tp1_dists = [abs(t.tp1_price - t.entry_price) for t in filled if abs(t.tp1_price - t.entry_price) > 0]
            med_tp1 = median(tp1_dists) if tp1_dists else 0
            r_yr = m["total_r"] / DATA_YEARS
            neg = neg_year_set(m)
            marker = " *" if m["calmar_ratio"] > 0.5 and m["profit_factor"] > 1.0 and len(neg) <= 2 else ""
            print(f"  {rr:>4} {tp1:>5} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
                  f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
                  f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} "
                  f"{med_stop:>7.1f}pt {med_tp1:>6.1f}pt {len(neg):>5}{marker}")

    # ── PART 3: Different TP1 floor values ──
    print("\n" + "=" * 80)
    print("  PART 3: TP1 floor sensitivity (rr=2.0, tp1=0.5, stop floor=10pt)")
    print("=" * 80)

    print(f"\n  {'tp1floor':>8} {'Trades':>6} {'WR':>6} {'PF':>5} {'Sharpe':>7} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedTP1':>7}")
    print(f"  {'─' * 80}")

    for tp1_floor in [0, 5, 7.5, 10, 12.5, 15, 20]:
        sess = replace(BASE_SESSION, min_tp1_points=float(tp1_floor))
        cfg = replace(BASE_CONFIG, sessions=(sess,), rr=2.0, tp1_ratio=0.5)
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)
        filled = [t for t in trades if t.exit_type != 0]
        tp1_dists = [abs(t.tp1_price - t.entry_price) for t in filled if abs(t.tp1_price - t.entry_price) > 0]
        med_tp1 = median(tp1_dists) if tp1_dists else 0
        r_yr = m["total_r"] / DATA_YEARS
        print(f"  {tp1_floor:>7.0f}pt {m['total_trades']:>6} {m['win_rate']:>5.1%} "
              f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
              f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} "
              f"{med_tp1:>6.1f}pt")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    main()
