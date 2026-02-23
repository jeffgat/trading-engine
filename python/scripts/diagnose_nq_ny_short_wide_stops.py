#!/usr/bin/env python3
"""NQ NY Short — Diagnostic: force tp1 >= 0.4 and min stop 10 points.

Tests whether a real edge exists when we eliminate the ultra-scalp artifact.
Post-filters trades to only include those with risk_points >= 10.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from statistics import median

import numpy as np

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10
MIN_STOP_PTS = 10.0

# Base session — try multiple ORB/stop combos
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


def median_stop_ticks(trades):
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / NQ.min_tick for t in filled)


def median_stop_pts(trades):
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points for t in filled)


def filter_min_stop(trades, min_pts):
    """Keep only trades with risk_points >= min_pts."""
    return [t for t in trades if t.risk_points >= min_pts]


def print_metrics(label, trades, m):
    n_years = max(DATA_YEARS, 1)
    r_yr = m["total_r"] / n_years if m["total_trades"] > 0 else 0
    neg = neg_year_set(m)
    rby = m.get("r_by_year", {})
    yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(rby.items()))

    filled = [t for t in trades if t.risk_points > 0]
    med_stop = median(t.risk_points for t in filled) if filled else 0
    med_ticks = median(t.risk_points / NQ.min_tick for t in filled) if filled else 0

    # Exit type breakdown
    exit_counts = {}
    exit_r = {}
    for t in trades:
        et = t.exit_type
        exit_counts[et] = exit_counts.get(et, 0) + 1
        exit_r.setdefault(et, []).append(t.r_multiple)

    print(f"\n  {label}")
    print(f"  {'─' * 70}")
    print(f"    Trades: {m['total_trades']:<6}  WR: {m['win_rate']:.1%}  PF: {m['profit_factor']:.2f}  "
          f"Sharpe: {m['sharpe_ratio']:.2f}  Calmar: {m['calmar_ratio']:.2f}")
    print(f"    Net R: {m['total_r']:.1f}  R/yr: {r_yr:.1f}  MaxDD: {m['max_drawdown_r']:.1f}R  "
          f"Neg years: {sorted(neg) if neg else 'none'}")
    print(f"    Median stop: {med_stop:.1f} pts ({med_ticks:.0f} ticks)")
    print(f"    R by year: {yr_str}")

    # TP1 distance
    if filled:
        tp1_dists = [t.risk_points * BASE_CONFIG.rr * 0.5 for t in filled]  # TP1 = halfway to full target...
        # Actually TP1 is at tp1_ratio of the full R:R distance
        # For the current config being tested, we need to use the actual tp1_ratio
        pass

    # Exit breakdown
    print(f"    Exit breakdown:")
    for et, cnt in sorted(exit_counts.items(), key=lambda x: -x[1]):
        avg_r = np.mean(exit_r[et]) if exit_r[et] else 0
        print(f"      {str(et):>12}: {cnt:>4} ({cnt/len(trades)*100:5.1f}%)  avg R: {avg_r:+.3f}")


def main():
    print("NQ NY SHORT — Wide Stop Diagnostic")
    print("=" * 80)
    print(f"Post-filtering trades with risk_points >= {MIN_STOP_PTS} pts ({MIN_STOP_PTS/NQ.min_tick:.0f} ticks)")
    print(f"Testing tp1 = 0.4, 0.5, 0.6 with rr = 1.5, 2.0, 2.5, 3.0")

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

    # First: show what happens to the R9 anchor with min stop filter
    print("\n" + "=" * 80)
    print("  PART 1: Current R10 anchor (orbstop=15%, orbgap=7%) with min stop filter")
    print("=" * 80)

    # R10 anchor config with DOW excl M+F
    for tp1 in [0.2, 0.4, 0.5]:
        cfg = replace(BASE_CONFIG, tp1_ratio=tp1)
        all_trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        all_trades = apply_dow_filter(all_trades, {0, 4})

        # Unfiltered
        m_all = compute_metrics(all_trades)
        filled_all = [t for t in all_trades if t.risk_points > 0]
        print(f"\n  tp1={tp1} — ALL trades (no stop filter)")
        print(f"    Trades: {m_all['total_trades']}, Med stop: {median_stop_pts(all_trades):.1f} pts, "
              f"WR: {m_all['win_rate']:.1%}, PF: {m_all['profit_factor']:.2f}, "
              f"Calmar: {m_all['calmar_ratio']:.2f}, Net R: {m_all['total_r']:.1f}")

        # Filtered >= 10 pts
        filtered = filter_min_stop(all_trades, MIN_STOP_PTS)
        if len(filtered) > 10:
            m_filt = compute_metrics(filtered)
            print_metrics(f"tp1={tp1} — stops >= {MIN_STOP_PTS} pts only", filtered, m_filt)
        else:
            print(f"    Only {len(filtered)} trades with stop >= {MIN_STOP_PTS} pts — too few")

    # PART 2: Try different stop sizes to naturally produce wider stops
    print("\n" + "=" * 80)
    print("  PART 2: Wider stops via higher stop_orb_pct")
    print("=" * 80)

    for stop_orb in [20.0, 25.0, 30.0, 40.0, 50.0]:
        for tp1 in [0.4, 0.5]:
            sess = replace(BASE_SESSION, stop_orb_pct=stop_orb)
            cfg = replace(BASE_CONFIG, sessions=(sess,), tp1_ratio=tp1)
            trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
            trades = apply_dow_filter(trades, {0, 4})

            filled = [t for t in trades if t.risk_points > 0]
            if not filled:
                print(f"\n  orbstop={stop_orb}%, tp1={tp1}: No filled trades")
                continue
            med = median(t.risk_points for t in filled)
            m = compute_metrics(trades)
            neg = neg_year_set(m)
            rby = m.get("r_by_year", {})
            yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(rby.items()))
            r_yr = m["total_r"] / DATA_YEARS
            print(f"\n  orbstop={stop_orb}%, tp1={tp1}: {m['total_trades']} trades, "
                  f"med stop={med:.1f} pts ({med/NQ.min_tick:.0f} ticks), "
                  f"WR={m['win_rate']:.1%}, PF={m['profit_factor']:.2f}, "
                  f"Calmar={m['calmar_ratio']:.2f}, Net R={m['total_r']:.1f}, "
                  f"MaxDD={m['max_drawdown_r']:.1f}")
            print(f"    R/yr: {r_yr:.1f} | Neg: {sorted(neg) if neg else 'none'}")
            print(f"    R by year: {yr_str}")

    # PART 3: ATR-based stops (disable ORB-based) with wider values
    print("\n" + "=" * 80)
    print("  PART 3: ATR-based stops (ORB stop disabled), wider ATR %")
    print("=" * 80)

    for stop_atr in [7.5, 10.0, 12.5, 15.0, 20.0]:
        for tp1 in [0.4, 0.5]:
            sess = replace(BASE_SESSION, stop_atr_pct=stop_atr, stop_orb_pct=0.0, min_gap_orb_pct=0.0,
                           min_gap_atr_pct=2.0)
            cfg = replace(BASE_CONFIG, sessions=(sess,), tp1_ratio=tp1)
            trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
            trades = apply_dow_filter(trades, {0, 4})

            filled = [t for t in trades if t.risk_points > 0]
            if not filled:
                print(f"\n  atr_stop={stop_atr}%, tp1={tp1}: No filled trades")
                continue
            med = median(t.risk_points for t in filled)
            m = compute_metrics(trades)
            neg = neg_year_set(m)
            rby = m.get("r_by_year", {})
            yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(rby.items()))
            r_yr = m["total_r"] / DATA_YEARS
            print(f"\n  atr_stop={stop_atr}%, tp1={tp1}: {m['total_trades']} trades, "
                  f"med stop={med:.1f} pts ({med/NQ.min_tick:.0f} ticks), "
                  f"WR={m['win_rate']:.1%}, PF={m['profit_factor']:.2f}, "
                  f"Calmar={m['calmar_ratio']:.2f}, Net R={m['total_r']:.1f}, "
                  f"MaxDD={m['max_drawdown_r']:.1f}")
            print(f"    R/yr: {r_yr:.1f} | Neg: {sorted(neg) if neg else 'none'}")
            print(f"    R by year: {yr_str}")

    # PART 4: Post-filter all trades to >= 10 pts, sweep rr x tp1
    print("\n" + "=" * 80)
    print("  PART 4: Post-filter >= 10pt stops, sweep rr x tp1 (ORB-based)")
    print("=" * 80)

    # Run once with orbstop=15% (produces range of stop sizes), filter to >= 10pts
    sess = replace(BASE_SESSION, stop_orb_pct=15.0, min_gap_orb_pct=7.0)
    base_cfg = replace(BASE_CONFIG, sessions=(sess,), tp1_ratio=0.5, rr=2.0)

    print(f"\n  {'rr':>4} {'tp1':>5} {'Trades':>6} {'WR':>6} {'PF':>5} {'Sharpe':>7} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedStop':>8}")
    print(f"  {'─' * 85}")

    for rr in [1.5, 2.0, 2.5, 3.0, 3.5]:
        for tp1 in [0.4, 0.5, 0.6]:
            cfg = replace(base_cfg, rr=rr, tp1_ratio=tp1)
            trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
            trades = apply_dow_filter(trades, {0, 4})
            trades = filter_min_stop(trades, MIN_STOP_PTS)

            if len(trades) < 50:
                print(f"  {rr:>4} {tp1:>5} {len(trades):>6}  (too few)")
                continue

            m = compute_metrics(trades)
            filled = [t for t in trades if t.risk_points > 0]
            med = median(t.risk_points for t in filled) if filled else 0
            r_yr = m["total_r"] / DATA_YEARS
            neg = neg_year_set(m)
            marker = " *" if m["calmar_ratio"] > 0.5 and m["profit_factor"] > 1.0 and not neg else ""
            print(f"  {rr:>4} {tp1:>5} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
                  f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} "
                  f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} "
                  f"{med:>7.1f}pt{marker}")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    main()
