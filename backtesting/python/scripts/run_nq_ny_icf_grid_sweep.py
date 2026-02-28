#!/usr/bin/env python3
"""NQ NY ORB — ICF=ON grid sweep: stop × rr × min_gap.

ICF at the R20 anchor (stop=8.75, rr=2.625, gap=2.25) was catastrophic (Calmar 16.36→7.13).
But NQ Asia showed ICF reshuffles the optimal surface (stop 3.7→3.3, rr 1.75→2.15).
This sweep tests whether ICF is viable at a *different* point in param space.

Grid:
  stop_atr_pct : 5.0 – 12.0 in 1.0 steps  (8 values)
  rr           : 1.5 – 4.0  in 0.5 steps   (6 values)
  min_gap_atr  : 1.0 – 3.5  in 0.5 steps   (6 values)
  Total: 288 combos with ICF=ON, tp1=0.3 held fixed

All other params held at R20 anchor values.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from itertools import product

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

# R20 structural anchor (everything except swept params)
BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=8.75,
    min_gap_atr_pct=2.25,
)

BASE = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=2.625,
    tp1_ratio=0.3,
    atr_length=12,
    impulse_close_filter=True,   # ICF ON for entire grid
    name="NQ NY ICF grid",
)

# Grid ranges
STOPS = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
RRS   = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
GAPS  = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    n_combos = len(STOPS) * len(RRS) * len(GAPS)
    print(f"NQ NY ORB — ICF=ON grid sweep: stop × rr × gap ({n_combos} combos)")
    print("=" * 100)
    print(f"Fixed: orb=20m, tp1=0.3, ATR=12, dir=both, max_gap=100pt, ICF=ON")
    print(f"Swept: stop=[{STOPS[0]}-{STOPS[-1]}], rr=[{RRS[0]}-{RRS[-1]}], gap=[{GAPS[0]}-{GAPS[-1]}]")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t0:.1f}s]")

    # ── Run R20 ICF=OFF anchor baseline for comparison ────────────────
    print("\nRunning R20 ICF=OFF baseline...", flush=True)
    anchor_off = replace(BASE, impulse_close_filter=False, name="R20 ICF OFF baseline")
    anchor_off_sess = replace(BASE_SESSION, stop_atr_pct=8.75, min_gap_atr_pct=2.25)
    anchor_off = replace(anchor_off, sessions=(anchor_off_sess,), rr=2.625)
    trades_base = run_backtest(df_5m, anchor_off, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m_base = compute_metrics(trades_base)
    base_calmar = m_base["calmar_ratio"]
    base_neg = neg_year_set(m_base)
    r_yr_base = m_base["total_r"] / DATA_YEARS
    print(f"  R20 ICF=OFF: {m_base['total_trades']} trades, Calmar {base_calmar:.2f}, "
          f"{r_yr_base:.1f} R/yr, DD {m_base['max_drawdown_r']:.1f}, neg years: {sorted(base_neg) if base_neg else 'none'}")

    # ── Grid sweep ────────────────────────────────────────────────────
    print(f"\nRunning {n_combos} ICF=ON combos...", flush=True)
    results = []
    done = 0

    for stop, rr, gap in product(STOPS, RRS, GAPS):
        sess = replace(BASE_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
        config = replace(BASE, sessions=(sess,), rr=rr)
        trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)
        neg = neg_year_set(m)
        results.append((stop, rr, gap, m, neg))
        done += 1
        if done % 50 == 0:
            print(f"  {done}/{n_combos} done [{time.time() - t0:.0f}s]", flush=True)

    print(f"  Grid complete [{time.time() - t0:.0f}s]")

    # ── Sort by Calmar ────────────────────────────────────────────────
    results.sort(key=lambda x: x[3]["calmar_ratio"], reverse=True)

    # ── Top 20 overall ────────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  TOP 20 BY CALMAR (ICF=ON) — R20 ICF=OFF baseline: Calmar {base_calmar:.2f}")
    print(f"{'='*100}")
    hdr = (f"  {'#':>3} {'stop':>5} {'rr':>5} {'gap':>5} {'Trades':>6} {'WR':>5} {'PF':>5} "
           f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>8}")
    print(hdr)
    print(f"  {'─'*95}")

    for i, (stop, rr, gap, m, neg) in enumerate(results[:20], 1):
        r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
        neg_str = ",".join(str(y) for y in sorted(neg)) if neg else "none"
        print(f"  {i:>3} {stop:>5.1f} {rr:>5.2f} {gap:>5.1f} {m['total_trades']:>6} "
              f"{m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} "
              f"{m['total_r']:>7.1f} {r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} "
              f"{m['calmar_ratio']:>7.2f} {neg_str:>8}")

    # ── Top 20 with 0 negative full years ─────────────────────────────
    clean = [(s, rr, g, m, n) for s, rr, g, m, n in results if len(n) == 0]
    print(f"\n{'='*100}")
    print(f"  TOP 20 BY CALMAR — 0 NEGATIVE FULL YEARS ({len(clean)}/{n_combos} configs)")
    print(f"  R20 ICF=OFF baseline: Calmar {base_calmar:.2f}, 0 neg years")
    print(f"{'='*100}")
    print(hdr)
    print(f"  {'─'*95}")

    for i, (stop, rr, gap, m, neg) in enumerate(clean[:20], 1):
        r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
        marker = " <-- BEATS R20" if m["calmar_ratio"] > base_calmar else ""
        print(f"  {i:>3} {stop:>5.1f} {rr:>5.2f} {gap:>5.1f} {m['total_trades']:>6} "
              f"{m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} "
              f"{m['total_r']:>7.1f} {r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} "
              f"{m['calmar_ratio']:>7.2f} none{marker}")

    # Print year breakdown for top 5 clean
    if clean:
        print(f"\n  Year breakdown (top 5 clean):")
        for i, (stop, rr, gap, m, _) in enumerate(clean[:5], 1):
            if "r_by_year" in m:
                years = sorted(m["r_by_year"].items())
                yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
                print(f"    #{i} (s={stop} rr={rr} g={gap}): {yr_str}")

    # ── Marginal analysis ─────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  MARGINAL ANALYSIS (avg Calmar across grid)")
    print(f"{'='*100}")

    from collections import defaultdict

    # By stop
    by_stop = defaultdict(list)
    for s, rr, g, m, n in results:
        by_stop[s].append(m["calmar_ratio"])
    print(f"\n  stop_atr_pct:")
    for s in STOPS:
        vals = by_stop[s]
        avg = sum(vals) / len(vals)
        clean_n = sum(1 for s2, rr, g, m, n in results if s2 == s and len(n) == 0)
        print(f"    {s:>5.1f}%: avg Calmar {avg:>6.2f}, {clean_n:>3}/{len(vals)} clean")

    # By rr
    by_rr = defaultdict(list)
    for s, rr, g, m, n in results:
        by_rr[rr].append(m["calmar_ratio"])
    print(f"\n  rr:")
    for rr in RRS:
        vals = by_rr[rr]
        avg = sum(vals) / len(vals)
        clean_n = sum(1 for s2, rr2, g, m, n in results if rr2 == rr and len(n) == 0)
        print(f"    {rr:>5.2f}: avg Calmar {avg:>6.2f}, {clean_n:>3}/{len(vals)} clean")

    # By gap
    by_gap = defaultdict(list)
    for s, rr, g, m, n in results:
        by_gap[g].append(m["calmar_ratio"])
    print(f"\n  min_gap_atr_pct:")
    for g in GAPS:
        vals = by_gap[g]
        avg = sum(vals) / len(vals)
        clean_n = sum(1 for s2, rr, g2, m, n in results if g2 == g and len(n) == 0)
        print(f"    {g:>5.1f}%: avg Calmar {avg:>6.2f}, {clean_n:>3}/{len(vals)} clean")

    # ── Verdict ───────────────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  VERDICT")
    print(f"{'='*100}")
    best_clean_calmar = clean[0][3]["calmar_ratio"] if clean else 0
    best_overall_calmar = results[0][3]["calmar_ratio"]
    print(f"  R20 ICF=OFF anchor Calmar:     {base_calmar:.2f} (0 neg years)")
    print(f"  Best ICF=ON overall Calmar:     {best_overall_calmar:.2f}")
    print(f"  Best ICF=ON clean Calmar:       {best_clean_calmar:.2f}")
    delta = best_clean_calmar - base_calmar
    print(f"  Delta (best clean vs R20):      {delta:+.2f}")

    if delta > 0:
        s, rr, g, m, _ = clean[0]
        print(f"\n  ICF=ON CAN beat R20 at: stop={s}%, rr={rr}, gap={g}%")
        print(f"  Consider adopting ICF + new params and re-sweeping as R21")
    else:
        print(f"\n  ICF=ON cannot match R20 ICF=OFF at any point in the swept grid.")
        print(f"  Proceed to robust pipeline with R20 anchor (ICF=OFF).")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
