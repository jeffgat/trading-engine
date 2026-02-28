#!/usr/bin/env python3
"""NQ NY Short — Diagnostic: min_stop_points=10 floor.

Tests configs with the new min_stop_points field which enforces
stop_dist = max(computed_stop, 10 points) at the engine level.
No more post-filtering — all trades have stops >= 10 pts.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from statistics import median

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

# Base session with ORB-based stop + 10pt floor
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


def median_stop_ticks(trades):
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / NQ.min_tick for t in filled)


def print_row(label, m, trades):
    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
    neg = neg_year_set(m)
    med_pts = median_stop_pts(trades)
    med_ticks = median_stop_ticks(trades)
    rby = m.get("r_by_year", {})
    yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(rby.items()))

    # Exit type breakdown
    exit_counts = {}
    for t in trades:
        exit_counts[t.exit_type] = exit_counts.get(t.exit_type, 0) + 1

    print(f"\n  {label}")
    print(f"    Trades: {m['total_trades']:<6}  WR: {m['win_rate']:.1%}  PF: {m['profit_factor']:.2f}  "
          f"Sharpe: {m['sharpe_ratio']:.2f}  Calmar: {m['calmar_ratio']:.2f}")
    print(f"    Net R: {m['total_r']:.1f}  R/yr: {r_yr:.1f}  MaxDD: {m['max_drawdown_r']:.1f}R  "
          f"Neg years: {sorted(neg) if neg else 'none'}")
    print(f"    Median stop: {med_pts:.1f} pts ({med_ticks:.0f} ticks)")
    print(f"    R by year: {yr_str}")
    # Show exit types
    et_strs = []
    for et, cnt in sorted(exit_counts.items(), key=lambda x: -x[1]):
        et_strs.append(f"{et}:{cnt}")
    print(f"    Exits: {', '.join(et_strs)}")


def main():
    print("NQ NY SHORT — min_stop_points=10 Floor Diagnostic")
    print("=" * 80)
    print("All trades now have stops >= 10 points enforced at the engine level.")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    # ── PART 1: Compare with and without floor ──
    print("\n" + "=" * 80)
    print("  PART 1: With vs Without min_stop_points=10 floor")
    print("=" * 80)

    # Without floor
    sess_no_floor = replace(BASE_SESSION, min_stop_points=0.0)
    cfg_no_floor = replace(BASE_CONFIG, sessions=(sess_no_floor,), tp1_ratio=0.5, rr=2.0)
    trades_nf = run_backtest(df_5m, cfg_no_floor, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades_nf = apply_dow_filter(trades_nf, {0, 4})
    m_nf = compute_metrics(trades_nf)
    print_row("orbstop=15%, tp1=0.5, rr=2.0 — NO floor", m_nf, trades_nf)

    # With floor
    cfg_floor = replace(BASE_CONFIG, tp1_ratio=0.5, rr=2.0)
    trades_f = run_backtest(df_5m, cfg_floor, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades_f = apply_dow_filter(trades_f, {0, 4})
    m_f = compute_metrics(trades_f)
    print_row("orbstop=15%, tp1=0.5, rr=2.0 — WITH 10pt floor", m_f, trades_f)

    # ── PART 2: Sweep rr × tp1 with 10pt floor ──
    print("\n" + "=" * 80)
    print("  PART 2: rr × tp1 sweep with min_stop_points=10")
    print("=" * 80)

    print(f"\n  {'rr':>4} {'tp1':>5} {'Trades':>6} {'WR':>6} {'PF':>5} {'Sharpe':>7} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedStop':>8} {'NegYrs':>8}")
    print(f"  {'─' * 90}")

    for rr in [1.5, 2.0, 2.5, 3.0, 3.5]:
        for tp1 in [0.3, 0.4, 0.5, 0.6]:
            cfg = replace(BASE_CONFIG, rr=rr, tp1_ratio=tp1)
            trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
            trades = apply_dow_filter(trades, {0, 4})
            m = compute_metrics(trades)
            med = median_stop_pts(trades)
            r_yr = m["total_r"] / DATA_YEARS
            neg = neg_year_set(m)
            marker = " *" if m["calmar_ratio"] > 0.5 and m["profit_factor"] > 1.0 else ""
            print(f"  {rr:>4} {tp1:>5} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
                  f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
                  f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} "
                  f"{med:>7.1f}pt {len(neg):>5}{marker}")

    # ── PART 3: Sweep stop_orb_pct with floor ──
    print("\n" + "=" * 80)
    print("  PART 3: stop_orb_pct sweep with min_stop_points=10, tp1=0.5, rr=2.0")
    print("=" * 80)

    print(f"\n  {'orbstop':>8} {'Trades':>6} {'WR':>6} {'PF':>5} {'Sharpe':>7} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedStop':>8}")
    print(f"  {'─' * 80}")

    for stop_orb in [10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0]:
        sess = replace(BASE_SESSION, stop_orb_pct=stop_orb)
        cfg = replace(BASE_CONFIG, sessions=(sess,), tp1_ratio=0.5, rr=2.0)
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        trades = apply_dow_filter(trades, {0, 4})
        m = compute_metrics(trades)
        med = median_stop_pts(trades)
        r_yr = m["total_r"] / DATA_YEARS
        print(f"  {stop_orb:>7.0f}% {m['total_trades']:>6} {m['win_rate']:>5.1%} "
              f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
              f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} "
              f"{med:>7.1f}pt")

    # ── PART 4: No DOW filter, sweep rr × tp1 ──
    print("\n" + "=" * 80)
    print("  PART 4: No DOW filter, rr × tp1 sweep with min_stop_points=10")
    print("=" * 80)

    print(f"\n  {'rr':>4} {'tp1':>5} {'Trades':>6} {'WR':>6} {'PF':>5} {'Sharpe':>7} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedStop':>8} {'NegYrs':>8}")
    print(f"  {'─' * 90}")

    for rr in [1.5, 2.0, 2.5, 3.0, 3.5]:
        for tp1 in [0.3, 0.4, 0.5, 0.6]:
            cfg = replace(BASE_CONFIG, rr=rr, tp1_ratio=tp1)
            trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
            # No DOW filter
            m = compute_metrics(trades)
            med = median_stop_pts(trades)
            r_yr = m["total_r"] / DATA_YEARS
            neg = neg_year_set(m)
            marker = " *" if m["calmar_ratio"] > 0.5 and m["profit_factor"] > 1.0 else ""
            print(f"  {rr:>4} {tp1:>5} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
                  f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
                  f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} "
                  f"{med:>7.1f}pt {len(neg):>5}{marker}")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    main()
