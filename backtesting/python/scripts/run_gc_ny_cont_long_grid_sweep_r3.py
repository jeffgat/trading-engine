#!/usr/bin/env python3
"""Step 3 — Grid Sweep R3: GC NY Continuation Longs.

Anchor (converged from R12 variable sweeps):
  stop=4.5%, rr=9.0, tp1=0.35, ATR 7, min_gap=3.0%, max_gap_atr=30%
  ICF=True, 8m ORB (09:30-09:38), entry→12:00, flat 13:30, long-only, FOMC excluded
  Friday excluded (post-backtest filter)
  Calmar 16.11, 622 trades, DD -12.4, 0 neg years

Grid: stop x rr x gap x tp1 = 5x5x5x5 = 625 combos
"""

import sys, time, datetime
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
CPY = "2026"
EXCL_DAYS = {4}

GC_NY = SessionConfig(name="NY", orb_start="09:30", orb_end="09:38", entry_start="09:38",
    entry_end="12:00", flat_start="13:30", flat_end="16:00",
    stop_atr_pct=4.5, min_gap_atr_pct=3.0, max_gap_points=25.0, max_gap_atr_pct=30.0)

ANCHOR = StrategyConfig(rr=9.0, tp1_ratio=0.35, risk_usd=5000.0, atr_length=7,
    min_qty=1.0, qty_step=1.0, sessions=(GC_NY,), instrument=GC,
    strategy="continuation", direction_filter="long", impulse_close_filter=True,
    use_bar_magnifier=True,
    half_days=("20250703","20251128","20251224","20250109","20260119"),
    excluded_dates=FOMC_DATES)

STOPS = [3.5, 4.0, 4.5, 5.0, 5.5]
RRS   = [7.0, 8.0, 9.0, 10.0, 11.0]
GAPS  = [2.0, 2.5, 3.0, 3.5, 4.0]
TP1S  = [0.25, 0.30, 0.35, 0.40, 0.45]

GRID = list(product(STOPS, RRS, GAPS, TP1S))
ANCHOR_STOP, ANCHOR_RR, ANCHOR_GAP, ANCHOR_TP1 = 4.5, 9.0, 3.0, 0.35

def dow_filter(trades):
    return [t for t in trades if t.exit_type == EXIT_NO_FILL or datetime.date.fromisoformat(t.date).weekday() not in EXCL_DAYS]

def median_stop_ticks(trades):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled: return 0.0
    return float(np.median([abs(t.entry_price - t.stop_price) / GC.min_tick for t in filled]))

def main():
    print(f"\n{'='*110}")
    print(f"  GC NY CONT LONGS — GRID SWEEP R3 ({len(GRID)} combos)")
    print(f"  Anchor: stop=4.5%, rr=9.0, tp1=0.35, ATR 7, gap=3.0%, max_gap_atr=30%")
    print(f"          ICF=True, 8m ORB, entry→12:00, flat 13:30, long-only, FOMC excl, Fri excl")
    print(f"  Grid: stop={STOPS} x rr={RRS} x gap={GAPS} x tp1={TP1S}")
    print(f"{'='*110}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data(GC.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(GC.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(GC.data_file, start=START_DATE)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    results = []
    t_start = time.time()

    for i, (stop, rr, gap, tp1) in enumerate(GRID):
        sess = replace(GC_NY, stop_atr_pct=stop, min_gap_atr_pct=gap)
        cfg = replace(ANCHOR, sessions=(sess,), rr=rr, tp1_ratio=tp1)
        trades = dow_filter(run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s))
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
    results.sort(key=lambda x: x["calmar"], reverse=True)

    HDR = (f"  {'#':>4} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>5} "
           f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
           f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYr':>6} {'Ticks':>6}")

    print(f"\n{'='*110}\n  TOP 20 BY CALMAR\n{'='*110}")
    print(HDR); print(f"  {'-'*108}")
    for rank, r in enumerate(results[:20], 1):
        ia = (abs(r["stop"]-ANCHOR_STOP)<0.01 and abs(r["rr"]-ANCHOR_RR)<0.01
              and abs(r["gap"]-ANCHOR_GAP)<0.01 and abs(r["tp1"]-ANCHOR_TP1)<0.01)
        mk = " <<< ANCHOR" if ia else ""
        print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>5.1f} {r['tp1']:>5.2f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
              f"{r['net_r']:>7.1f} {r['r_per_yr']:>6.1f} {r['max_dd']:>6.1f} "
              f"{r['calmar']:>7.2f} {r['neg_yrs']:>3}    {r['med_ticks']:>5.0f}{mk}")
        if rank <= 5:
            years = sorted(r["r_by_year"].items())
            print(f"        R by year: {'  '.join(f'{yr}:{v:+.0f}' for yr, v in years)}")

    w = results[0]
    ew = []
    if w["stop"] in (STOPS[0], STOPS[-1]): ew.append(f"stop={w['stop']}")
    if w["rr"] in (RRS[0], RRS[-1]): ew.append(f"rr={w['rr']}")
    if w["gap"] in (GAPS[0], GAPS[-1]): ew.append(f"gap={w['gap']}")
    if w["tp1"] in (TP1S[0], TP1S[-1]): ew.append(f"tp1={w['tp1']}")
    if ew: print(f"\n  WARNING: Winner at grid boundary on: {', '.join(ew)}")

    zn = [r for r in results if r["neg_yrs"] == 0]
    print(f"\n  Combos with 0 negative years: {len(zn)}/{len(results)}")
    if zn:
        print(f"\n{'='*110}\n  TOP 20 WITH 0 NEGATIVE YEARS\n{'='*110}")
        print(HDR); print(f"  {'-'*108}")
        for rank, r in enumerate(zn[:20], 1):
            ia = (abs(r["stop"]-ANCHOR_STOP)<0.01 and abs(r["rr"]-ANCHOR_RR)<0.01
                  and abs(r["gap"]-ANCHOR_GAP)<0.01 and abs(r["tp1"]-ANCHOR_TP1)<0.01)
            mk = " <<< ANCHOR" if ia else ""
            print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>5.1f} {r['tp1']:>5.2f} "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
                  f"{r['net_r']:>7.1f} {r['r_per_yr']:>6.1f} {r['max_dd']:>6.1f} "
                  f"{r['calmar']:>7.2f} {r['neg_yrs']:>3}    {r['med_ticks']:>5.0f}{mk}")
            if rank <= 5:
                years = sorted(r["r_by_year"].items())
                print(f"        R by year: {'  '.join(f'{yr}:{v:+.0f}' for yr, v in years)}")

    ar, ac2 = None, 0
    for rank, r in enumerate(results, 1):
        if (abs(r["stop"]-ANCHOR_STOP)<0.01 and abs(r["rr"]-ANCHOR_RR)<0.01
                and abs(r["gap"]-ANCHOR_GAP)<0.01 and abs(r["tp1"]-ANCHOR_TP1)<0.01):
            ar, ac2 = rank, r["calmar"]; break
    if ar: print(f"\n  Anchor rank: #{ar}/{len(results)} (Calmar {ac2:.2f})")

    print(f"\n{'='*110}\n  DIMENSION DOMINANCE (top 20)\n{'='*110}")
    for dn, dv, dk in [("stop",STOPS,"stop"),("rr",RRS,"rr"),("gap",GAPS,"gap"),("tp1",TP1S,"tp1")]:
        c = defaultdict(int)
        for r in results[:20]: c[r[dk]] += 1
        print(f"  {dn}: {'  '.join(f'{v}={c.get(v,0)}' for v in dv)}")

    prof = sum(1 for r in results if r["net_r"] > 0)
    print(f"\n  Grid summary: {len(results)} combos | {prof} profitable ({prof/len(results)*100:.0f}%) | {len(zn)} with 0 neg years ({len(zn)/len(results)*100:.0f}%)")

    if results and ar:
        d = results[0]["calmar"] - ac2
        if abs(d) > 0.5:
            print(f"\n  *** GRID WINNER DIFFERS (Calmar delta = {d:+.2f}) ***")
            print(f"  Winner: stop={results[0]['stop']}, rr={results[0]['rr']}, gap={results[0]['gap']}, tp1={results[0]['tp1']}")
            print(f"  --> Update anchor and re-sweep")
        else:
            print(f"\n  Grid confirms anchor (delta = {d:+.2f}). Proceed to robust pipeline.")
    print(f"\n  Runtime: {total_time:.0f}s ({total_time/60:.1f}m)")

if __name__ == "__main__":
    main()
