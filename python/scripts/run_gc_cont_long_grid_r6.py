#!/usr/bin/env python3
"""GC NY Continuation Longs — Grid Sweep R6 (1s magnifier).

Anchor (stabilized after 5 rounds of variable sweeps + FOMC diagnostic):
  stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5
  ATR 16, 10m ORB (09:30-09:40), entry→11:00, flat_start=15:50
  long-only, FOMC dates excluded

Grid sweep: stop × rr × min_gap × tp1 — 450 combos
  stop:    [3.0, 3.5, 4.0, 4.5, 5.0, 5.5]     (6)
  rr:      [3.0, 3.5, 4.0, 4.5, 5.0]            (5)
  min_gap: [1.5, 2.0, 2.5, 3.0, 3.5]            (5)
  tp1:     [0.3, 0.4, 0.5]                       (3)
  Total:   6 × 5 × 5 × 3 = 450

Structural params fixed: ATR 16, 10m ORB, entry→11:00, FOMC excl.
Results saved to experiment DB.
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
from orb_backtest.results.export import grid_results_to_dict, save_optimization_result

GC = get_instrument("GC")
START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]

# ── Structural anchor (fixed for all combos) ──────────────────────────────────

def make_session(stop, min_gap):
    return SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:40",
        entry_start="09:40", entry_end="11:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=stop,
        min_gap_atr_pct=min_gap,
    )


BASE = StrategyConfig(
    rr=4.5, tp1_ratio=0.5, risk_usd=5000.0, atr_length=16,
    min_qty=1.0, qty_step=1.0,
    sessions=(make_session(4.0, 2.5),),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",) + FOMC_DATES,
)

# ── Grid params ───────────────────────────────────────────────────────────────

STOPS    = [3.0, 3.5, 4.0, 4.5, 5.0, 5.5]
RRS      = [3.0, 3.5, 4.0, 4.5, 5.0]
MIN_GAPS = [1.5, 2.0, 2.5, 3.0, 3.5]
TP1S     = [0.3, 0.4, 0.5]

df = df_1m = df_1s = None


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
    print("  GC NY CONT LONGS — GRID SWEEP R6 (1s magnifier)")
    print("  Fixed: ATR 16 | 10m ORB | entry→11:00 | FOMC excluded")
    print("  Grid: stop × rr × min_gap × tp1 = 450 combos")
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
    print(f"\nRunning {total} combos (single worker — 1s data)...")

    results = []
    t0 = time.time()
    for i, (stop, rr, min_gap, tp1) in enumerate(combos, 1):
        cfg = with_overrides(
            BASE,
            rr=rr,
            tp1_ratio=tp1,
            sessions=(make_session(stop, min_gap),),
        )
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        results.append((cfg, trades))

        if i % 50 == 0 or i == total:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (total - i) / rate if rate > 0 else 0
            print(f"  {i}/{total}  ({elapsed:.0f}s elapsed, ETA {eta:.0f}s)")

    print(f"\nDone in {time.time() - t0:.1f}s. Ranking results...")

    # ── Rank by Calmar ────────────────────────────────────────────────────────

    scored = []
    for cfg, trades in results:
        m = compute_metrics(trades)
        sess = cfg.sessions[0]
        scored.append({
            "stop":     sess.stop_atr_pct,
            "rr":       cfg.rr,
            "min_gap":  sess.min_gap_atr_pct,
            "tp1":      cfg.tp1_ratio,
            "trades":   m["total_trades"],
            "wr":       m["win_rate"],
            "pf":       m["profit_factor"],
            "total_r":  m["total_r"],
            "r_yr":     r_per_year(m),
            "max_dd":   m["max_drawdown_r"],
            "calmar":   m["calmar_ratio"],
            "sharpe":   m["sharpe_ratio"],
            "neg_yr":   neg_years(m),
            "cfg":      cfg,
            "trades_list": trades,
        })

    scored.sort(key=lambda x: x["calmar"], reverse=True)

    # ── Print top 20 ──────────────────────────────────────────────────────────

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
        anchor = "  ← anchor" if (r["stop"] == 4.0 and r["rr"] == 4.5 and r["min_gap"] == 2.5 and r["tp1"] == 0.5) else ""
        print(
            f"  {r['stop']:>5.1f}  {r['rr']:>5.1f}  {r['min_gap']:>5.1f}  {r['tp1']:>4.1f}"
            f"  {r['trades']:>5d}  {r['wr']:>6.1%}  {r['pf']:>5.2f}"
            f"  {r['total_r']:>7.1f}  {r['r_yr']:>6.1f}  {r['max_dd']:>7.1f}"
            f"  {r['calmar']:>7.2f}  {r['sharpe']:>7.3f}  {r['neg_yr']:>5d}{anchor}"
        )

    winner = scored[0]
    print()
    print("=" * 70)
    print("  WINNER (best Calmar)")
    print("=" * 70)
    print(f"  stop={winner['stop']}%  rr={winner['rr']}  min_gap={winner['min_gap']}%  tp1={winner['tp1']}")
    print(f"  Trades:  {winner['trades']}")
    print(f"  Win Rate:{winner['wr']:.1%}")
    print(f"  PF:      {winner['pf']:.2f}")
    print(f"  Net R:   {winner['total_r']:.1f}R")
    print(f"  R/yr:    {winner['r_yr']:.1f}R")
    print(f"  Max DD:  {winner['max_dd']:.1f}R")
    print(f"  Calmar:  {winner['calmar']:.2f}")
    print(f"  Sharpe:  {winner['sharpe']:.3f}")
    print(f"  Neg Yrs: {winner['neg_yr']}")

    # R by year for winner
    winner_m = compute_metrics(winner["trades_list"])
    rby = winner_m.get("r_by_year", {})
    print(f"\n  R by year:")
    for y in sorted(rby):
        flag = " <--" if rby[y] < 0 else ""
        print(f"    {y}: {rby[y]:>8.1f}R{flag}")

    # ── Save to DB ────────────────────────────────────────────────────────────

    print("\nSaving to experiment DB...")
    grid_result = grid_results_to_dict(
        [(r["cfg"], r["trades_list"]) for r in scored],
        swept_params={
            "ny_stop_atr_pct": STOPS,
            "rr": RRS,
            "ny_min_gap_atr_pct": MIN_GAPS,
            "tp1_ratio": TP1S,
        },
    )
    result_id = save_optimization_result(grid_result)
    print(f"  Saved: {result_id}")
    print()
