#!/usr/bin/env python3
"""ES NY Fine-Tune Grid — High-resolution 5D sweep with 1s magnifier.

Centered on R6 converged anchor: stop=3.0%, rr=5.0, gap=1.5%, tp1=0.4, ATR=3
All continuous dims at 0.25 step, ATR at structural values.

Grid: stop(5) × rr(5) × gap(5) × tp1(5) × atr(3) = 1,875 combos
1s bar magnifier for maximum fill accuracy.

Structural (locked from R1-R6 variable sweeps):
  ORB: 09:30-09:55 (25m), entry≤13:00, flat=15:50
  direction=long, ICF=ON, DOW excl Thu+Fri
  max_gap_points=10, continuation strategy
"""

import sys
import time
from collections import defaultdict
from dataclasses import replace
from itertools import product

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DOW_EXCL = {3, 4}  # Thu+Fri

ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:55",
    entry_start="09:55",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,
    min_gap_atr_pct=1.5,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=ES,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=5.0,
    tp1_ratio=0.4,
    atr_length=3,
    impulse_close_filter=True,
    name="ES NY Fine Tune",
)

# ── Fine-tune grid dimensions ────────────────────────────────────────────────

STOPS = [2.5, 2.75, 3.0, 3.25, 3.5]                  # 5
RRS   = [4.0, 4.5, 5.0, 5.5, 6.0]                    # 5
GAPS  = [1.0, 1.25, 1.5, 1.75, 2.0]                   # 5
TP1S  = [0.3, 0.35, 0.4, 0.45, 0.5]                   # 5
ATRS  = [3, 5, 7]                                      # 3

GRID = list(product(STOPS, RRS, GAPS, TP1S, ATRS))
TOTAL = len(GRID)


def main():
    print()
    print("=" * 110)
    print(f"  ES NY FINE-TUNE GRID: {TOTAL:,} combos "
          f"({len(STOPS)}x{len(RRS)}x{len(GAPS)}x{len(TP1S)}x{len(ATRS)})")
    print(f"  Anchor: stop=3.0% | rr=5.0 | gap=1.5% | tp1=0.4 | ATR=3")
    print(f"  Structural: 25m ORB | entry<=13:00 | long-only | ICF=ON | flat=15:50 | excl Thu+Fri")
    print("=" * 110)
    print()

    print("Loading data (including 1s)...")
    t0 = time.time()
    df = load_5m_data("ES_5m.csv")
    df_1m = load_1m_for_5m("ES_5m.csv")
    df_1s = load_1s_for_5m("ES_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars | 1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time()-t0:.1f}s")
    print()

    results = []
    t_start = time.time()

    for i, (stop, rr, gap, tp1, atr) in enumerate(GRID):
        sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
        cfg = replace(ANCHOR, sessions=(sess,), rr=rr, tp1_ratio=tp1, atr_length=atr)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        trades = apply_dow_filter(trades, DOW_EXCL)
        m = compute_metrics(trades)

        rby = m.get("r_by_year", {})
        full_years = {y: r for y, r in rby.items() if y not in ("2016", "2026")}
        neg_yrs = sum(1 for r in full_years.values() if r < 0)
        n_years = max(len(full_years), 1)
        avg_annual = m["total_r"] / n_years
        calmar = avg_annual / abs(m["max_drawdown_r"]) if m["max_drawdown_r"] != 0 else 0

        results.append({
            "stop": stop, "rr": rr, "gap": gap, "tp1": tp1, "atr": atr,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
            "net_r": m["total_r"], "avg_annual": avg_annual,
            "max_dd": m["max_drawdown_r"], "calmar": calmar,
            "neg_yrs": neg_yrs,
            "neg_list": ",".join(y for y, r in sorted(full_years.items()) if r < 0),
        })

        if (i + 1) % 100 == 0 or i == TOTAL - 1:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed
            eta = (TOTAL - i - 1) / rate
            hrs = int(eta // 3600)
            mins = int((eta % 3600) // 60)
            print(f"  {i+1:>5}/{TOTAL} done [{elapsed/60:.1f}min, {rate:.2f}/s, ETA {hrs}h{mins:02d}m]")

    total_time = time.time() - t_start
    hrs = int(total_time // 3600)
    mins = int((total_time % 3600) // 60)
    print(f"\n  Grid complete in {hrs}h{mins:02d}m ({total_time:.0f}s)")
    print()

    # Sort by Calmar
    results.sort(key=lambda x: x["calmar"], reverse=True)

    # ── Table header ──
    HDR = (f"  {'Rank':>4} {'stop':>5} {'rr':>5} {'gap':>5} {'tp1':>5} {'atr':>4} "
           f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} {'Net R':>7} "
           f"{'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")

    def print_row(rank, r, marker=""):
        print(f"  {rank:>4} {r['stop']:>5.2f} {r['rr']:>5.2f} {r['gap']:>5.2f} "
              f"{r['tp1']:>5.2f} {r['atr']:>4} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
              f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
              f"{r['calmar']:>7.2f} {r['neg_yrs']:>3} {r['neg_list']}{marker}")

    # ── Top 30 overall ──
    print("=" * 110)
    print("  TOP 30 BY CALMAR")
    print("=" * 110)
    print(HDR)
    for rank, r in enumerate(results[:30], 1):
        is_anchor = (abs(r["stop"] - 3.0) < 0.01 and abs(r["rr"] - 5.0) < 0.01
                     and abs(r["gap"] - 1.5) < 0.01 and abs(r["tp1"] - 0.4) < 0.01
                     and r["atr"] == 3)
        print_row(rank, r, " <<< ANCHOR" if is_anchor else "")
    print()

    # ── Top combos with 0 neg years ──
    zero_neg = [r for r in results if r["neg_yrs"] == 0]
    print(f"  Combos with 0 negative years: {len(zero_neg)}/{TOTAL} ({100*len(zero_neg)/TOTAL:.0f}%)")
    print()
    if zero_neg:
        print("=" * 110)
        print("  TOP 30 WITH 0 NEGATIVE YEARS (by Calmar)")
        print("=" * 110)
        print(HDR)
        for rank, r in enumerate(zero_neg[:30], 1):
            is_anchor = (abs(r["stop"] - 3.0) < 0.01 and abs(r["rr"] - 5.0) < 0.01
                         and abs(r["gap"] - 1.5) < 0.01 and abs(r["tp1"] - 0.4) < 0.01
                         and r["atr"] == 3)
            print_row(rank, r, " <<< ANCHOR" if is_anchor else "")
        print()

    # ── Anchor rank ──
    for rank, r in enumerate(results, 1):
        if (abs(r["stop"] - 3.0) < 0.01 and abs(r["rr"] - 5.0) < 0.01
                and abs(r["gap"] - 1.5) < 0.01 and abs(r["tp1"] - 0.4) < 0.01
                and r["atr"] == 3):
            print(f"  Anchor rank: #{rank}/{TOTAL}")
            break

    # ── Dimension dominance (top 30) ──
    print()
    print("=" * 110)
    print("  DIMENSION DOMINANCE (top 30)")
    print("=" * 110)
    for dim_name, dim_values, dim_key in [
        ("stop", STOPS, "stop"), ("rr", RRS, "rr"),
        ("gap", GAPS, "gap"), ("tp1", TP1S, "tp1"),
        ("atr", ATRS, "atr"),
    ]:
        counts = defaultdict(int)
        for r in results[:30]:
            counts[r[dim_key]] += 1
        parts = "  ".join(f"{v}={counts.get(v, 0)}" for v in dim_values)
        print(f"  {dim_name}: {parts}")

    # ── Plateau analysis ──
    best_calmar = results[0]["calmar"]
    plateau_90 = sum(1 for r in results if r["calmar"] >= 0.9 * best_calmar)
    plateau_80 = sum(1 for r in results if r["calmar"] >= 0.8 * best_calmar)
    print()
    print(f"  Plateau analysis:")
    print(f"    Best Calmar: {best_calmar:.2f}")
    print(f"    Within 90% ({0.9*best_calmar:.2f}): {plateau_90} combos ({100*plateau_90/TOTAL:.1f}%)")
    print(f"    Within 80% ({0.8*best_calmar:.2f}): {plateau_80} combos ({100*plateau_80/TOTAL:.1f}%)")
    print()

    # ── Best per ATR bucket ──
    print("=" * 110)
    print("  BEST PER ATR (0 neg years)")
    print("=" * 110)
    print(HDR)
    for atr in ATRS:
        bucket = [r for r in zero_neg if r["atr"] == atr]
        if bucket:
            best = bucket[0]  # already sorted by calmar
            print_row(0, best, f"  (best ATR={atr})")
    print()


if __name__ == "__main__":
    main()
