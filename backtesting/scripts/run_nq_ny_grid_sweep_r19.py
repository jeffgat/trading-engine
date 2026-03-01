#!/usr/bin/env python3
"""NQ NY ORB — Grid sweep: stop × rr × tp1 × gap (R9-R11 rule).

Triggered by stop change (11% → 9% winner in R19). Per R9-R11 rule,
the entire rr × tp1 × gap surface must be re-run when stop changes.

Structural params (frozen from R19 variable sweeps):
  ORB: 09:30-09:50 (20m), entry until 15:30, flat 15:50
  ATR=12, direction=both, continuation, 1s magnifier

Grid:
  stop:  [8.0, 8.5, 9.0, 9.5, 10.0]
  rr:    [1.5, 1.75, 2.0, 2.25, 2.5, 2.75]
  gap:   [1.0, 1.5, 2.0, 2.5, 3.0]
  tp1:   [0.3, 0.4, 0.5, 0.6, 0.7]
  Total: 5 × 6 × 5 × 5 = 750 combos

Uses parallel sweep infrastructure for speed.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

# Structural params (frozen)
BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,       # Placeholder — overridden in grid
    min_gap_atr_pct=1.5,     # Placeholder — overridden in grid
)

BASE_CONFIG = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=2.0,                  # Placeholder — overridden in grid
    tp1_ratio=0.5,           # Placeholder — overridden in grid
    atr_length=12,
    name="NQ NY Grid",
)

# Grid dimensions
STOPS = [8.0, 8.5, 9.0, 9.5, 10.0]
RRS = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75]
GAPS = [1.0, 1.5, 2.0, 2.5, 3.0]
TP1S = [0.3, 0.4, 0.5, 0.6, 0.7]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    total = len(STOPS) * len(RRS) * len(GAPS) * len(TP1S)
    print(f"NQ NY ORB — Grid Sweep: {total} combos")
    print(f"  stop: {STOPS}")
    print(f"  rr:   {RRS}")
    print(f"  gap:  {GAPS}")
    print(f"  tp1:  {TP1S}")
    print("=" * 100)

    # Load data
    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t_start:.1f}s]")

    # Build all configs
    configs = []
    for stop in STOPS:
        for rr in RRS:
            for gap in GAPS:
                for tp1 in TP1S:
                    sess = replace(BASE_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
                    config = replace(BASE_CONFIG, sessions=(sess,), rr=rr, tp1_ratio=tp1)
                    configs.append(config)

    print(f"\nRunning {len(configs)} configs...", flush=True)
    t_sweep = time.time()
    results = run_sweep(df_5m, configs, n_workers=1, start_date=START_DATE,
                        df_1m=df_1m, df_1s=df_1s)
    t_sweep_elapsed = time.time() - t_sweep
    print(f"  Sweep done [{t_sweep_elapsed:.0f}s]")

    # Compute metrics for all
    scored = []
    for config, trades in results:
        m = compute_metrics(trades)
        sess = config.sessions[0]
        scored.append({
            "stop": sess.stop_atr_pct,
            "rr": config.rr,
            "gap": sess.min_gap_atr_pct,
            "tp1": config.tp1_ratio,
            "metrics": m,
        })

    # Sort by Calmar
    scored.sort(key=lambda x: x["metrics"]["calmar_ratio"], reverse=True)

    # Print top 30
    print(f"\n{'='*100}")
    print(f"  TOP 30 BY CALMAR")
    print(f"{'='*100}")
    print(f"  {'#':>3} {'stop':>5} {'rr':>5} {'gap':>5} {'tp1':>5} "
          f"{'N':>5} {'WR':>5} {'PF':>5} {'Sharpe':>7} {'Net R':>7} "
          f"{'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'NegYr':>5}")
    print(f"  {'─'*95}")

    for i, row in enumerate(scored[:30], 1):
        m = row["metrics"]
        r_yr = m["total_r"] / DATA_YEARS
        ny = len(neg_year_set(m))
        print(f"  {i:>3} {row['stop']:>5.1f} {row['rr']:>5.2f} {row['gap']:>5.1f} {row['tp1']:>5.1f} "
              f"{m['total_trades']:>5} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
              f"{m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} {ny:>5}")

    # Top 5 detailed year breakdown
    print(f"\n{'='*100}")
    print(f"  TOP 5 — Year-by-year")
    print(f"{'='*100}")
    for i, row in enumerate(scored[:5], 1):
        m = row["metrics"]
        r_yr = m["total_r"] / DATA_YEARS
        print(f"\n  #{i}: stop={row['stop']}% rr={row['rr']} gap={row['gap']}% tp1={row['tp1']}")
        print(f"      N={m['total_trades']} WR={m['win_rate']:.1%} PF={m['profit_factor']:.2f} "
              f"Sharpe={m['sharpe_ratio']:.2f} Net R={m['total_r']:.1f} R/yr={r_yr:.1f} "
              f"DD={m['max_drawdown_r']:.1f} Calmar={m['calmar_ratio']:.2f}")
        if "r_by_year" in m:
            years = sorted(m["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
            print(f"      R by year: {yr_str}")

    # Best per stop level
    print(f"\n{'='*100}")
    print(f"  BEST PER STOP LEVEL")
    print(f"{'='*100}")
    for stop in STOPS:
        stop_results = [s for s in scored if s["stop"] == stop]
        if not stop_results:
            continue
        best = stop_results[0]  # Already sorted by Calmar
        m = best["metrics"]
        r_yr = m["total_r"] / DATA_YEARS
        ny = len(neg_year_set(m))
        print(f"  stop={stop:>5.1f}%: rr={best['rr']:.2f} gap={best['gap']:.1f}% tp1={best['tp1']:.1f} → "
              f"Calmar={m['calmar_ratio']:.2f} R/yr={r_yr:.1f} DD={m['max_drawdown_r']:.1f} "
              f"N={m['total_trades']} NegYr={ny}")

    # R19 anchor reference point
    r19_results = [s for s in scored
                   if s["stop"] == 9.0 and s["rr"] == 2.0 and s["gap"] == 1.5 and s["tp1"] == 0.5]
    if r19_results:
        m = r19_results[0]["metrics"]
        print(f"\n  R19 anchor (stop=9 rr=2.0 gap=1.5 tp1=0.5): Calmar={m['calmar_ratio']:.2f} "
              f"R/yr={m['total_r']/DATA_YEARS:.1f} DD={m['max_drawdown_r']:.1f}")

    winner = scored[0]
    m_win = winner["metrics"]
    print(f"\n  GRID WINNER: stop={winner['stop']}% rr={winner['rr']} gap={winner['gap']}% tp1={winner['tp1']}")
    print(f"  Calmar={m_win['calmar_ratio']:.2f} R/yr={m_win['total_r']/DATA_YEARS:.1f} "
          f"DD={m_win['max_drawdown_r']:.1f}")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
