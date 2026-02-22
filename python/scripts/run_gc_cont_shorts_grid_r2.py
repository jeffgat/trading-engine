#!/usr/bin/env python3
"""GC NY Continuation Shorts — Grid Sweep R2 (extended rr/tp1).

Grid R1 winner: stop=3.0%, rr=6.0, gap=5.5%, tp1=0.6
  → Calmar 10.94, Sharpe 2.149, 190.4R, -17.4R DD, 1 neg year

R3 variable sweeps showed rr and tp1 improve beyond grid R1 range:
  - rr=8.0: Calmar 11.88 (+0.94)  → grid R1 topped at rr=6.0
  - tp1=0.8: Calmar 11.99 (+1.05) → grid R1 topped at tp1=0.6
  - max_gap_atr=25%: Calmar 11.62 (+0.68) → adopt for grid R2

These interact, so test jointly in expanded grid.

Grid R2: stop × rr × min_gap × tp1 = 504 combos
  stop:    [2.5, 3.0, 3.5]                      (3)
  rr:      [5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0] (7)
  min_gap: [5.0, 5.5, 6.0]                      (3)
  tp1:     [0.5, 0.6, 0.65, 0.7, 0.75, 0.8]    (6) — skipping lower; R3 showed monotonic
  Total:   3 × 7 × 3 × 8 = 504

Change from R1: max_gap_atr=25% (was 30%).
Structural params fixed: ATR 10, 15m ORB, entry→15:00, FOMC excl.
"""

import sys
import time
import itertools
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]


def make_session(stop, min_gap):
    return SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=stop,
        min_gap_atr_pct=min_gap,
        max_gap_points=25.0,
        max_gap_atr_pct=25.0,  # adopted from R3 (was 30%)
    )


BASE = StrategyConfig(
    rr=6.0, tp1_ratio=0.6, risk_usd=5000.0, atr_length=10,
    min_qty=1.0, qty_step=1.0,
    sessions=(make_session(3.0, 5.5),),
    instrument=GC,
    strategy="continuation",
    direction_filter="short",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=FOMC_DATES,
)

# Grid params — extended ranges for rr and tp1
STOPS    = [2.5, 3.0, 3.5]
RRS      = [5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 9.0]
MIN_GAPS = [5.0, 5.5, 6.0]
TP1S     = [0.5, 0.6, 0.65, 0.7, 0.75, 0.8]


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY CONT SHORTS — GRID SWEEP R2 (extended rr/tp1)")
    print("  Fixed: ATR 10 | 15m ORB | entry→15:00 | max_gap_atr=25% | FOMC excl")
    total_combos = len(STOPS) * len(RRS) * len(MIN_GAPS) * len(TP1S)
    print(f"  Grid: stop × rr × min_gap × tp1 = {total_combos} combos")
    print("=" * 70)

    print("\nLoading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars | 1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    combos = list(itertools.product(STOPS, RRS, MIN_GAPS, TP1S))
    total = len(combos)
    print(f"\nRunning {total} combos...")

    scored = []
    t0 = time.time()
    for i, (stop, rr, min_gap, tp1) in enumerate(combos, 1):
        cfg = with_overrides(
            BASE,
            rr=rr,
            tp1_ratio=tp1,
            sessions=(make_session(stop, min_gap),),
        )
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)
        scored.append({
            "stop": stop, "rr": rr, "min_gap": min_gap, "tp1": tp1,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "total_r": m["total_r"],
            "r_yr": r_per_year(m), "max_dd": m["max_drawdown_r"],
            "calmar": m["calmar_ratio"], "sharpe": m["sharpe_ratio"],
            "neg_yr": neg_years(m),
        })

        if i % 50 == 0 or i == total:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (total - i) / rate if rate > 0 else 0
            print(f"  {i}/{total}  ({elapsed:.0f}s elapsed, ETA {eta:.0f}s)")

    print(f"\nDone in {time.time() - t0:.1f}s. Ranking...")

    scored.sort(key=lambda x: x["calmar"], reverse=True)

    # Top 20
    print()
    print("=" * 70)
    print("  TOP 20 BY CALMAR")
    print("=" * 70)
    print(
        f"  {'stop':>5s}  {'rr':>5s}  {'gap':>5s}  {'tp1':>4s}"
        f"  {'Trd':>5s}  {'WR':>6s}  {'PF':>5s}"
        f"  {'Net R':>7s}  {'R/yr':>6s}  {'MaxDD':>7s}"
        f"  {'Calmar':>7s}  {'Sharpe':>7s}  {'NegYr':>5s}"
    )
    print("  " + "-" * 100)
    for r in scored[:20]:
        r1_winner = "  <- R1 winner" if (r["stop"] == 3.0 and r["rr"] == 6.0 and r["min_gap"] == 5.5 and r["tp1"] == 0.6) else ""
        print(
            f"  {r['stop']:>5.1f}  {r['rr']:>5.1f}  {r['min_gap']:>5.1f}  {r['tp1']:>4.2f}"
            f"  {r['trades']:>5d}  {r['wr']:>6.1%}  {r['pf']:>5.2f}"
            f"  {r['total_r']:>7.1f}  {r['r_yr']:>6.1f}  {r['max_dd']:>7.1f}"
            f"  {r['calmar']:>7.2f}  {r['sharpe']:>7.3f}  {r['neg_yr']:>5d}{r1_winner}"
        )

    # Bottom 5 (sanity check)
    print()
    print("  BOTTOM 5 (worst Calmar)")
    print("  " + "-" * 100)
    for r in scored[-5:]:
        print(
            f"  {r['stop']:>5.1f}  {r['rr']:>5.1f}  {r['min_gap']:>5.1f}  {r['tp1']:>4.2f}"
            f"  {r['trades']:>5d}  {r['wr']:>6.1%}  {r['pf']:>5.2f}"
            f"  {r['total_r']:>7.1f}  {r['r_yr']:>6.1f}  {r['max_dd']:>7.1f}"
            f"  {r['calmar']:>7.2f}  {r['sharpe']:>7.3f}  {r['neg_yr']:>5d}"
        )

    winner = scored[0]
    print()
    print("=" * 70)
    print("  GRID R2 WINNER")
    print("=" * 70)
    print(f"  stop={winner['stop']}% | rr={winner['rr']} | min_gap={winner['min_gap']}% | tp1={winner['tp1']}")
    print(f"  Trades:   {winner['trades']}")
    print(f"  Win Rate: {winner['wr']:.1%}")
    print(f"  PF:       {winner['pf']:.2f}")
    print(f"  Net R:    {winner['total_r']:.1f}R")
    print(f"  R/yr:     {winner['r_yr']:.1f}R")
    print(f"  Max DD:   {winner['max_dd']:.1f}R")
    print(f"  Calmar:   {winner['calmar']:.2f}")
    print(f"  Sharpe:   {winner['sharpe']:.3f}")
    print(f"  Neg Yrs:  {winner['neg_yr']}")

    # Check R1 winner rank in R2 grid
    r1_rank = next(
        (i for i, r in enumerate(scored)
         if r["stop"] == 3.0 and r["rr"] == 6.0 and r["min_gap"] == 5.5 and r["tp1"] == 0.6),
        -1,
    )
    print(f"\n  R1 winner rank in R2: #{r1_rank + 1} of {total}")

    # How many combos are positive?
    pos = sum(1 for r in scored if r["total_r"] > 0)
    print(f"  Positive combos: {pos}/{total} ({pos/total:.0%})")

    # Check if winner moved significantly from R1 winner
    if r1_rank == 0:
        print("\n  CONVERGED: R1 winner remains top — anchor stable.")
    elif r1_rank < 5:
        print("\n  CLOSE: R1 winner in top 5 — minor shift, may be noise.")
    else:
        print("\n  SHIFTED: Winner moved — re-sweep structural params (R4).")
    print()
