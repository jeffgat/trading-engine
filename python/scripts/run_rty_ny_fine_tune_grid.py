#!/usr/bin/env python3
"""RTY NY Fine-Tune Grid — High-resolution 5D sweep with 1s magnifier.

Centered on R2 grid winner: stop=1.5%, rr=6.0, gap=1.0%, tp1=0.6, entry≤15:30
All dimensions at 0.25 step (continuous) with fine TP1 resolution (0.05 step).

Grid: stop(7) × rr(8) × gap(4) × tp1(7) × entry(4) = 6,272 combos
1s bar magnifier for maximum fill accuracy.

Direction: long-only, ATR=14, 15m ORB (09:30-09:45), flat=15:50
"""

import sys
import time
from collections import defaultdict
from dataclasses import replace
from itertools import product

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import RTY
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"

ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="15:30",          # R2 grid winner
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,           # R6 (min allowed)
    min_gap_atr_pct=1.0,        # R2 grid winner
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=RTY,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=6.0,                     # R2 grid winner
    tp1_ratio=0.4,              # ADOPTED R6
    atr_length=14,
    impulse_close_filter=False,
    name="RTY NY Fine Tune",
)

# ── Fine-tune grid dimensions ────────────────────────────────────────────────
# Step 0.25 for stop/rr/gap, 0.05 for tp1, structural for entry_end

STOPS      = [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]              # 7
RRS        = [5.0, 5.25, 5.5, 5.75, 6.0, 6.25, 6.5, 7.0]      # 8
GAPS       = [0.5, 0.75, 1.0, 1.25]                              # 4
TP1S       = [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]            # 7
ENTRY_ENDS = ["12:00", "13:00", "14:00", "15:30"]                # 4

GRID = list(product(STOPS, RRS, GAPS, TP1S, ENTRY_ENDS))
TOTAL = len(GRID)


def main():
    print()
    print("=" * 110)
    print(f"  RTY NY FINE-TUNE GRID: {TOTAL:,} combos "
          f"({len(STOPS)}×{len(RRS)}×{len(GAPS)}×{len(TP1S)}×{len(ENTRY_ENDS)})")
    print(f"  Anchor: stop=3.0% | rr=6.0 | gap=1.0% | tp1=0.4 | entry≤15:30")
    print(f"  Structural: 15m ORB | ATR=14 | long-only | flat=15:50")
    print("=" * 110)
    print()

    print("Loading data (including 1s)...")
    t0 = time.time()
    df = load_5m_data("RTY_5m.csv")
    df_1m = load_1m_for_5m("RTY_5m.csv")
    df_1s = load_1s_for_5m("RTY_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars | 1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time()-t0:.1f}s")
    print()

    results = []
    t_start = time.time()

    for i, (stop, rr, gap, tp1, ee) in enumerate(GRID):
        sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap, entry_end=ee)
        cfg = replace(ANCHOR, sessions=(sess,), rr=rr, tp1_ratio=tp1)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)

        rby = m.get("r_by_year", {})
        full_years = {y: r for y, r in rby.items() if y not in ("2016", "2026")}
        neg_yrs = sum(1 for r in full_years.values() if r < 0)
        n_years = max(len(full_years), 1)
        avg_annual = m["total_r"] / n_years
        calmar = avg_annual / abs(m["max_drawdown_r"]) if m["max_drawdown_r"] != 0 else 0

        results.append({
            "stop": stop, "rr": rr, "gap": gap, "tp1": tp1, "ee": ee,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
            "net_r": m["total_r"], "avg_annual": avg_annual,
            "max_dd": m["max_drawdown_r"], "calmar": calmar,
            "neg_yrs": neg_yrs,
            "neg_list": ",".join(y for y, r in sorted(full_years.items()) if r < 0),
        })

        if (i + 1) % 200 == 0 or i == TOTAL - 1:
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
    HDR = (f"  {'Rank':>4} {'stop':>5} {'rr':>5} {'gap':>5} {'tp1':>5} {'entry':>6} "
           f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} {'Net R':>7} "
           f"{'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")

    def print_row(rank, r, marker=""):
        print(f"  {rank:>4} {r['stop']:>5.2f} {r['rr']:>5.2f} {r['gap']:>5.2f} "
              f"{r['tp1']:>5.2f} {r['ee']:>6s} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
              f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
              f"{r['calmar']:>7.2f} {r['neg_yrs']:>3} {r['neg_list']}{marker}")

    # ── Top 30 overall ──
    print("=" * 110)
    print("  TOP 30 BY CALMAR")
    print("=" * 110)
    print(HDR)
    for rank, r in enumerate(results[:30], 1):
        is_anchor = (r["stop"] == 3.0 and r["rr"] == 6.0 and r["gap"] == 1.0
                     and r["tp1"] == 0.4 and r["ee"] == "15:30")
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
            is_anchor = (r["stop"] == 1.5 and r["rr"] == 6.0 and r["gap"] == 1.0
                         and r["tp1"] == 0.6 and r["ee"] == "15:30")
            print_row(rank, r, " <<< ANCHOR" if is_anchor else "")
        print()

    # ── Anchor rank ──
    for rank, r in enumerate(results, 1):
        if (r["stop"] == 3.0 and r["rr"] == 6.0 and r["gap"] == 1.0
                and r["tp1"] == 0.4 and r["ee"] == "15:30"):
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
        ("entry", ENTRY_ENDS, "ee"),
    ]:
        counts = defaultdict(int)
        for r in results[:30]:
            counts[r[dim_key]] += 1
        parts = "  ".join(f"{v}={counts.get(v, 0)}" for v in dim_values)
        print(f"  {dim_name}: {parts}")

    # ── Plateau analysis: how many combos within 10% of best Calmar ──
    best_calmar = results[0]["calmar"]
    plateau_90 = sum(1 for r in results if r["calmar"] >= 0.9 * best_calmar)
    plateau_80 = sum(1 for r in results if r["calmar"] >= 0.8 * best_calmar)
    print()
    print(f"  Plateau analysis:")
    print(f"    Best Calmar: {best_calmar:.2f}")
    print(f"    Within 90% ({0.9*best_calmar:.2f}): {plateau_90} combos ({100*plateau_90/TOTAL:.1f}%)")
    print(f"    Within 80% ({0.8*best_calmar:.2f}): {plateau_80} combos ({100*plateau_80/TOTAL:.1f}%)")
    print()

    # ── Best per entry_end bucket ──
    print("=" * 110)
    print("  BEST PER ENTRY_END (0 neg years)")
    print("=" * 110)
    print(HDR)
    for ee in ENTRY_ENDS:
        bucket = [r for r in zero_neg if r["ee"] == ee]
        if bucket:
            best = bucket[0]  # already sorted by calmar
            print_row(0, best, f"  (best {ee})")
    print()


if __name__ == "__main__":
    main()
