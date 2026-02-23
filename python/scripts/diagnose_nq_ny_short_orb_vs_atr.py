#!/usr/bin/env python3
"""NQ NY Short — ORB-based vs ATR-based stops with both 10pt floors.

Compares stop mechanisms head-to-head across rr × tp1 combos.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from statistics import median

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

# ORB-based session
ORB_SESSION = SessionConfig(
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
    sessions=(ORB_SESSION,),
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
    return median(t.risk_points for t in filled) if filled else 0.0


def run_grid(df_5m, df_1m, df_1s, session, label):
    print(f"\n  {'rr':>4} {'tp1':>5} {'Trades':>6} {'WR':>6} {'PF':>5} {'Sharpe':>7} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedStop':>8} {'MedTP1':>7} {'NegYrs':>6}")
    print(f"  {'─' * 100}")

    for rr in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        for tp1 in [0.3, 0.4, 0.5, 0.6]:
            cfg = replace(BASE_CONFIG, sessions=(session,), rr=rr, tp1_ratio=tp1)
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


def main():
    print("NQ NY SHORT — ORB-based vs ATR-based Stops (both 10pt floors)")
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

    # ── A: ORB-based (orbstop=15%, orbgap=7%) ──
    print("\n" + "=" * 80)
    print("  A. ORB-BASED (orbstop=15%, orbgap=7%, 20m ORB)")
    print("=" * 80)
    run_grid(df_5m, df_1m, df_1s, ORB_SESSION, "ORB")

    # ── B: ATR-based with various stop_atr_pct values ──
    for stop_atr, gap_atr in [(5.0, 2.0), (7.5, 2.25), (10.0, 2.25), (12.5, 2.25)]:
        atr_session = SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end="09:50",
            entry_start="09:50",
            entry_end="15:00",
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=stop_atr,
            min_gap_atr_pct=gap_atr,
            stop_orb_pct=0.0,
            min_gap_orb_pct=0.0,
            min_stop_points=10.0,
            min_tp1_points=10.0,
        )
        print(f"\n{'=' * 80}")
        print(f"  B. ATR-BASED (stop_atr={stop_atr}%, gap_atr={gap_atr}%, 20m ORB)")
        print(f"{'=' * 80}")
        run_grid(df_5m, df_1m, df_1s, atr_session, f"ATR{stop_atr}")

    # ── C: ORB-based with different orbstop values ──
    for stop_orb in [10.0, 20.0, 25.0, 30.0]:
        orb_session = replace(ORB_SESSION, stop_orb_pct=stop_orb)
        print(f"\n{'=' * 80}")
        print(f"  C. ORB-BASED (orbstop={stop_orb}%, orbgap=7%, 20m ORB)")
        print(f"{'=' * 80}")
        run_grid(df_5m, df_1m, df_1s, orb_session, f"ORB{stop_orb}")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    main()
