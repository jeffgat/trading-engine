#!/usr/bin/env python3
"""Step 3 — Grid Sweep R1: GC NY Continuation Longs.

Anchor (from variable sweeps R6 — best Calmar 4.37):
  stop=4.0%, rr=7.0, tp1=0.5, ATR 7, min_gap=2.5%, max_gap_atr=25%
  ICF=True, 8m ORB (09:30-09:38), entry→12:00, flat 15:50, long-only, FOMC excluded

Grid: stop x rr x gap x tp1 = 5x5x5x5 = 625 combos
If winner differs from anchor (Calmar delta > 0.5) -> re-run variable sweeps.
"""

import sys
import time
from collections import defaultdict
from dataclasses import replace
from itertools import product
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10.15
CPY = "2026"  # current partial year — exclude from neg-year count

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:38",
    entry_start="09:38",
    entry_end="12:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=4.0,
    min_gap_atr_pct=2.5,
    max_gap_points=25.0,
    max_gap_atr_pct=25.0,
)

ANCHOR = StrategyConfig(
    rr=7.0,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=7,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    impulse_close_filter=True,
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=FOMC_DATES,
)

# Grid dimensions — narrow range centered on R6 anchor
STOPS = [3.0, 3.5, 4.0, 4.5, 5.0]
RRS   = [5.0, 6.0, 7.0, 8.0, 9.0]
GAPS  = [1.5, 2.0, 2.5, 3.0, 3.5]
TP1S  = [0.4, 0.45, 0.5, 0.55, 0.6]

GRID = list(product(STOPS, RRS, GAPS, TP1S))
ANCHOR_STOP, ANCHOR_RR, ANCHOR_GAP, ANCHOR_TP1 = 4.0, 7.0, 2.5, 0.5


def median_stop_ticks(trades):
    """Median stop distance in ticks for filled trades."""
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return 0.0
    ticks = [abs(t.entry_price - t.stop_price) / GC.min_tick for t in filled]
    return float(np.median(ticks))


def main():
    print(f"\n{'='*110}")
    print(f"  GC NY CONT LONGS — GRID SWEEP R1 ({len(GRID)} combos)")
    print(f"  Anchor: stop=4.0%, rr=7.0, tp1=0.5, ATR 7, gap=2.5%, max_gap_atr=25%")
    print(f"          ICF=True, 8m ORB, entry→12:00, flat 15:50, long-only, FOMC excl")
    print(f"  Grid: stop={STOPS} x rr={RRS} x gap={GAPS} x tp1={TP1S}")
    print(f"{'='*110}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data(GC.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(GC.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(GC.data_file, start=START_DATE)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    results = []
    skipped = 0
    t_start = time.time()

    for i, (stop, rr, gap, tp1) in enumerate(GRID):
        sess = replace(GC_NY, stop_atr_pct=stop, min_gap_atr_pct=gap)
        cfg = replace(ANCHOR, sessions=(sess,), rr=rr, tp1_ratio=tp1)
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)

        rby = m.get("r_by_year", {})
        neg_yrs = sum(1 for y, r in rby.items() if r < 0 and y != CPY)

        results.append({
            "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
            "net_r": m["total_r"], "r_per_yr": m["total_r"] / DATA_YEARS,
            "max_dd": m["max_drawdown_r"], "calmar": m.get("calmar_ratio", 0),
            "neg_yrs": neg_yrs,
            "neg_list": ",".join(y for y, r in sorted(rby.items()) if r < 0 and y != CPY),
            "r_by_year": rby,
            "med_ticks": median_stop_ticks(trades),
        })

        if (i + 1) % 50 == 0 or i == len(GRID) - 1:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed
            eta = (len(GRID) - i - 1) / rate
            print(f"  {i+1}/{len(GRID)} done [{elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s]")

    total_time = time.time() - t_start
    print(f"\n  Grid complete in {total_time:.1f}s ({total_time/60:.1f}m)")

    # Sort by Calmar
    results.sort(key=lambda x: x["calmar"], reverse=True)

    HDR = (f"  {'#':>4} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>5} "
           f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
           f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYr':>6} {'Ticks':>6}")

    # -- Top 20 overall --
    print(f"\n{'='*110}")
    print(f"  TOP 20 BY CALMAR (all combos)")
    print(f"{'='*110}")
    print(HDR)
    print(f"  {'-'*108}")

    for rank, r in enumerate(results[:20], 1):
        is_anchor = (abs(r["stop"]-ANCHOR_STOP)<0.01 and abs(r["rr"]-ANCHOR_RR)<0.01
                     and abs(r["gap"]-ANCHOR_GAP)<0.01 and abs(r["tp1"]-ANCHOR_TP1)<0.01)
        marker = " <<< ANCHOR" if is_anchor else ""
        print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>5.1f} {r['tp1']:>5.2f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
              f"{r['net_r']:>7.1f} {r['r_per_yr']:>6.1f} {r['max_dd']:>6.1f} "
              f"{r['calmar']:>7.2f} {r['neg_yrs']:>3}    {r['med_ticks']:>5.0f}{marker}")
        if rank <= 5:
            years = sorted(r["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{v:+.0f}" for yr, v in years)
            print(f"        R by year: {yr_str}")

    # Warn if winner is at grid boundary
    winner = results[0]
    edge_warnings = []
    if winner["stop"] in (STOPS[0], STOPS[-1]):
        edge_warnings.append(f"stop={winner['stop']}")
    if winner["rr"] in (RRS[0], RRS[-1]):
        edge_warnings.append(f"rr={winner['rr']}")
    if winner["gap"] in (GAPS[0], GAPS[-1]):
        edge_warnings.append(f"gap={winner['gap']}")
    if winner["tp1"] in (TP1S[0], TP1S[-1]):
        edge_warnings.append(f"tp1={winner['tp1']}")
    if edge_warnings:
        print(f"\n  WARNING: Winner at grid boundary on: {', '.join(edge_warnings)}")
        print("  Consider expanding the grid in those dimensions.")

    # -- Top 20 with 0 negative years --
    zero_neg = [r for r in results if r["neg_yrs"] == 0]
    print(f"\n  Combos with 0 negative years: {len(zero_neg)}/{len(results)}")
    if zero_neg:
        print(f"\n{'='*110}")
        print(f"  TOP 20 WITH 0 NEGATIVE YEARS (by Calmar)")
        print(f"{'='*110}")
        print(HDR)
        print(f"  {'-'*108}")
        for rank, r in enumerate(zero_neg[:20], 1):
            is_anchor = (abs(r["stop"]-ANCHOR_STOP)<0.01 and abs(r["rr"]-ANCHOR_RR)<0.01
                         and abs(r["gap"]-ANCHOR_GAP)<0.01 and abs(r["tp1"]-ANCHOR_TP1)<0.01)
            marker = " <<< ANCHOR" if is_anchor else ""
            print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>5.1f} {r['tp1']:>5.2f} "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
                  f"{r['net_r']:>7.1f} {r['r_per_yr']:>6.1f} {r['max_dd']:>6.1f} "
                  f"{r['calmar']:>7.2f} {r['neg_yrs']:>3}    {r['med_ticks']:>5.0f}{marker}")
            if rank <= 5:
                years = sorted(r["r_by_year"].items())
                yr_str = "  ".join(f"{yr}:{v:+.0f}" for yr, v in years)
                print(f"        R by year: {yr_str}")

    # -- Anchor rank --
    anchor_rank = None
    anchor_calmar = 0
    for rank, r in enumerate(results, 1):
        if (abs(r["stop"]-ANCHOR_STOP)<0.01 and abs(r["rr"]-ANCHOR_RR)<0.01
                and abs(r["gap"]-ANCHOR_GAP)<0.01 and abs(r["tp1"]-ANCHOR_TP1)<0.01):
            anchor_rank = rank
            anchor_calmar = r["calmar"]
            break
    if anchor_rank:
        print(f"\n  Anchor rank: #{anchor_rank}/{len(results)} (Calmar {anchor_calmar:.2f})")

    # -- Dimension dominance (top 20) --
    print(f"\n{'='*110}")
    print(f"  DIMENSION DOMINANCE (top 20)")
    print(f"{'='*110}")
    for dim_name, dim_values, dim_key in [
        ("stop", STOPS, "stop"), ("rr", RRS, "rr"),
        ("gap", GAPS, "gap"), ("tp1", TP1S, "tp1"),
    ]:
        counts = defaultdict(int)
        for r in results[:20]:
            counts[r[dim_key]] += 1
        parts = "  ".join(f"{v}={counts.get(v, 0)}" for v in dim_values)
        print(f"  {dim_name}: {parts}")

    # -- Grid summary --
    profitable = sum(1 for r in results if r["net_r"] > 0)
    print(f"\n  Grid summary:")
    print(f"    Total combos: {len(results)}")
    print(f"    Profitable: {profitable}/{len(results)} ({profitable/len(results)*100:.0f}%)")
    print(f"    0 neg years: {len(zero_neg)}/{len(results)} ({len(zero_neg)/len(results)*100:.0f}%)")

    # -- Decision --
    if results and anchor_rank:
        winner_calmar = results[0]["calmar"]
        delta = winner_calmar - anchor_calmar
        if abs(delta) > 0.5:
            print(f"\n  *** GRID WINNER DIFFERS FROM ANCHOR (Calmar delta = {delta:+.2f}) ***")
            print(f"  Winner: stop={results[0]['stop']}, rr={results[0]['rr']}, gap={results[0]['gap']}, tp1={results[0]['tp1']}")
            print(f"  --> Update anchor to grid winner and re-run variable sweeps")
        else:
            print(f"\n  Grid confirms anchor (Calmar delta = {delta:+.2f}, <= 0.5). Proceed to robust pipeline.")

    print(f"\n  Total runtime: {total_time:.0f}s ({total_time/60:.1f}m)")


if __name__ == "__main__":
    main()
