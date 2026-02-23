#!/usr/bin/env python3
"""NQ Asia ORB — ICF=ON grid sweep: stop × rr × gap on R4 anchor.

R4 anchor (converged, GO):
  ORB 10m (20:00-20:10), entry≤01:00, flat=00:00, ATR=5, dir=both, no-Thu
  stop=3.7%, gap=0.90%, max_gap_atr=5.0%, rr=1.75, tp1=0.35, ICF=OFF
  Calmar 23.85, 21.1 R/yr, DD -8.9R, 0 neg years

v3+ICF optimization (entry_end=23:00, 1m mag) shifted: stop 3.7→3.3, rr 1.75→2.15.
This sweep tests whether ICF is viable at the R4 anchor (entry_end=01:00, 1s mag).

Grid:
  stop_atr_pct : 2.0 – 6.0 in 0.5 steps  (9 values)
  rr           : 1.0 – 3.5 in 0.5 steps   (6 values)
  min_gap_atr  : 0.50 – 2.00 in 0.25 steps (7 values)
  Total: 378 combos with ICF=ON, tp1=0.35 held fixed
  + no-Thursday DOW filter applied to all
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from itertools import product

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10
DOW_EXCL = {3}  # no-Thursday

BASE_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:10",
    entry_start="20:10",
    entry_end="01:00",
    flat_start="00:00",
    flat_end="07:00",
    stop_atr_pct=3.7,
    min_gap_atr_pct=0.90,
)

BASE = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=1.75,
    tp1_ratio=0.35,
    atr_length=5,
    impulse_close_filter=True,   # ICF ON for entire grid
    name="NQ Asia ICF grid",
)

# Grid ranges
STOPS = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
RRS   = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
GAPS  = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    n_combos = len(STOPS) * len(RRS) * len(GAPS)
    print(f"NQ Asia ORB — ICF=ON grid sweep: stop × rr × gap ({n_combos} combos)")
    print("=" * 100)
    print(f"Fixed: orb=10m, tp1=0.35, ATR=5, dir=both, max_gap_atr=5.0%, no-Thu, ICF=ON")
    print(f"Swept: stop=[{STOPS[0]}-{STOPS[-1]}], rr=[{RRS[0]}-{RRS[-1]}], gap=[{GAPS[0]}-{GAPS[-1]}]")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t0:.1f}s]")

    # ── Run R4 ICF=OFF anchor baseline ────────────────────────────────
    print("\nRunning R4 ICF=OFF baseline (no-Thu)...", flush=True)
    anchor_off = replace(BASE, impulse_close_filter=False, name="R4 ICF OFF baseline")
    trades_base = run_backtest(df_5m, anchor_off, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades_base = apply_dow_filter(trades_base, DOW_EXCL)
    m_base = compute_metrics(trades_base)
    base_calmar = m_base["calmar_ratio"]
    base_neg = neg_year_set(m_base)
    r_yr_base = m_base["total_r"] / DATA_YEARS
    print(f"  R4 ICF=OFF: {m_base['total_trades']} trades, Calmar {base_calmar:.2f}, "
          f"{r_yr_base:.1f} R/yr, DD {m_base['max_drawdown_r']:.1f}, neg years: {sorted(base_neg) if base_neg else 'none'}")

    # ── Grid sweep ────────────────────────────────────────────────────
    print(f"\nRunning {n_combos} ICF=ON combos...", flush=True)
    results = []
    done = 0

    for stop, rr, gap in product(STOPS, RRS, GAPS):
        sess = replace(BASE_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
        config = replace(BASE, sessions=(sess,), rr=rr)
        trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        trades = apply_dow_filter(trades, DOW_EXCL)
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
    print(f"  TOP 20 BY CALMAR (ICF=ON) — R4 ICF=OFF baseline: Calmar {base_calmar:.2f}")
    print(f"{'='*100}")
    hdr = (f"  {'#':>3} {'stop':>5} {'rr':>5} {'gap':>5} {'Trades':>6} {'WR':>5} {'PF':>5} "
           f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>12}")
    print(hdr)
    print(f"  {'─'*98}")

    for i, (stop, rr, gap, m, neg) in enumerate(results[:20], 1):
        r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
        neg_str = ",".join(str(y) for y in sorted(neg)) if neg else "none"
        print(f"  {i:>3} {stop:>5.1f} {rr:>5.2f} {gap:>5.2f} {m['total_trades']:>6} "
              f"{m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} "
              f"{m['total_r']:>7.1f} {r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} "
              f"{m['calmar_ratio']:>7.2f} {neg_str:>12}")

    # ── Top 20 with 0 negative full years ─────────────────────────────
    clean = [(s, rr, g, m, n) for s, rr, g, m, n in results if len(n) == 0]
    print(f"\n{'='*100}")
    print(f"  TOP 20 BY CALMAR — 0 NEGATIVE FULL YEARS ({len(clean)}/{n_combos} configs)")
    print(f"  R4 ICF=OFF baseline: Calmar {base_calmar:.2f}, 0 neg years")
    print(f"{'='*100}")
    print(hdr)
    print(f"  {'─'*98}")

    for i, (stop, rr, gap, m, neg) in enumerate(clean[:20], 1):
        r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
        marker = " <-- BEATS R4" if m["calmar_ratio"] > base_calmar else ""
        print(f"  {i:>3} {stop:>5.1f} {rr:>5.2f} {gap:>5.2f} {m['total_trades']:>6} "
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

    by_stop = defaultdict(list)
    for s, rr, g, m, n in results:
        by_stop[s].append(m["calmar_ratio"])
    print(f"\n  stop_atr_pct:")
    for s in STOPS:
        vals = by_stop[s]
        avg = sum(vals) / len(vals)
        clean_n = sum(1 for s2, rr, g, m, n in results if s2 == s and len(n) == 0)
        print(f"    {s:>5.1f}%: avg Calmar {avg:>6.2f}, {clean_n:>3}/{len(vals)} clean")

    by_rr = defaultdict(list)
    for s, rr, g, m, n in results:
        by_rr[rr].append(m["calmar_ratio"])
    print(f"\n  rr:")
    for rr in RRS:
        vals = by_rr[rr]
        avg = sum(vals) / len(vals)
        clean_n = sum(1 for s2, rr2, g, m, n in results if rr2 == rr and len(n) == 0)
        print(f"    {rr:>5.2f}: avg Calmar {avg:>6.2f}, {clean_n:>3}/{len(vals)} clean")

    by_gap = defaultdict(list)
    for s, rr, g, m, n in results:
        by_gap[g].append(m["calmar_ratio"])
    print(f"\n  min_gap_atr_pct:")
    for g in GAPS:
        vals = by_gap[g]
        avg = sum(vals) / len(vals)
        clean_n = sum(1 for s2, rr, g2, m, n in results if g2 == g and len(n) == 0)
        print(f"    {g:>5.2f}%: avg Calmar {avg:>6.2f}, {clean_n:>3}/{len(vals)} clean")

    # ── Verdict ───────────────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  VERDICT")
    print(f"{'='*100}")
    best_clean_calmar = clean[0][3]["calmar_ratio"] if clean else 0
    best_overall_calmar = results[0][3]["calmar_ratio"]
    print(f"  R4 ICF=OFF anchor Calmar:       {base_calmar:.2f} (0 neg years)")
    print(f"  Best ICF=ON overall Calmar:      {best_overall_calmar:.2f}")
    print(f"  Best ICF=ON clean Calmar:        {best_clean_calmar:.2f}")
    delta = best_clean_calmar - base_calmar
    print(f"  Delta (best clean vs R4):        {delta:+.2f}")

    if delta > 0:
        s, rr, g, m, _ = clean[0]
        print(f"\n  ICF=ON CAN beat R4 at: stop={s}%, rr={rr}, gap={g}%")
        print(f"  Consider adopting ICF + new params and re-sweeping")
    else:
        print(f"\n  ICF=ON cannot match R4 ICF=OFF at any point in the swept grid.")
        print(f"  R4 anchor (ICF=OFF) confirmed.")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
