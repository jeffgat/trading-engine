#!/usr/bin/env python3
"""NQ NY ORB — Grid sweep on R20 anchor (post fine-tune).

R20 anchor (structural vars converged):
  ORB: 09:30-09:50 (20m), entry until 15:30, flat 15:50
  ATR=12, direction=both, continuation, 1s magnifier

Current continuous params: stop=8.75% rr=2.625 gap=2.25% tp1=0.3

Grid (broad, centered on current anchor):
  stop:  [7.0, 7.5, 8.0, 8.5, 8.75, 9.0, 9.5, 10.0]
  rr:    [2.0, 2.25, 2.5, 2.625, 2.75, 3.0, 3.25, 3.5]
  gap:   [1.5, 2.0, 2.25, 2.5, 3.0]
  tp1:   [0.2, 0.25, 0.3, 0.35, 0.4, 0.5]
  Total: 8 × 8 × 5 × 6 = 1,920 combos
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

# Structural params (frozen from R20)
BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=8.75,       # Placeholder — overridden in grid
    min_gap_atr_pct=2.25,    # Placeholder — overridden in grid
)

BASE_CONFIG = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=2.625,                 # Placeholder — overridden in grid
    tp1_ratio=0.3,            # Placeholder — overridden in grid
    atr_length=12,
    name="NQ NY Grid R20",
)

# Grid dimensions (broad, centered on R20 anchor)
STOPS = [7.0, 7.5, 8.0, 8.5, 8.75, 9.0, 9.5, 10.0]
RRS = [2.0, 2.25, 2.5, 2.625, 2.75, 3.0, 3.25, 3.5]
GAPS = [1.5, 2.0, 2.25, 2.5, 3.0]
TP1S = [0.2, 0.25, 0.3, 0.35, 0.4, 0.5]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    total = len(STOPS) * len(RRS) * len(GAPS) * len(TP1S)
    print(f"NQ NY ORB — Grid Sweep R20: {total} combos")
    print(f"  stop: {STOPS}")
    print(f"  rr:   {RRS}")
    print(f"  gap:  {GAPS}")
    print(f"  tp1:  {TP1S}")
    print("=" * 110)

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
    print(f"  Sweep done [{time.time() - t_sweep:.0f}s]")

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

    # ── TOP 30 BY CALMAR ─────────────────────────────────────────────
    print(f"\n{'='*110}")
    print(f"  TOP 30 BY CALMAR")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'stop':>5} {'rr':>6} {'gap':>5} {'tp1':>5} "
          f"{'N':>5} {'WR':>5} {'PF':>5} {'Sharpe':>7} {'Net R':>7} "
          f"{'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'NegYr':>5}")
    print(f"  {'─'*105}")

    for i, row in enumerate(scored[:30], 1):
        m = row["metrics"]
        r_yr = m["total_r"] / DATA_YEARS
        ny = len(neg_year_set(m))
        marker = " <--" if (row["stop"] == 8.75 and row["rr"] == 2.625 and
                            row["gap"] == 2.25 and row["tp1"] == 0.3) else ""
        print(f"  {i:>3} {row['stop']:>5.2f} {row['rr']:>6.3f} {row['gap']:>5.2f} {row['tp1']:>5.2f} "
              f"{m['total_trades']:>5} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
              f"{m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} {ny:>5}{marker}")

    # ── TOP 15 WITH 0 NEGATIVE YEARS ──────────────────────────────────
    zero_neg = [s for s in scored if len(neg_year_set(s["metrics"])) == 0]
    print(f"\n{'='*110}")
    print(f"  TOP 15 WITH 0 NEGATIVE YEARS ({len(zero_neg)} configs total)")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'stop':>5} {'rr':>6} {'gap':>5} {'tp1':>5} "
          f"{'N':>5} {'WR':>5} {'PF':>5} {'Sharpe':>7} {'Net R':>7} "
          f"{'R/yr':>6} {'MaxDD':>7} {'Calmar':>7}")
    print(f"  {'─'*100}")

    for i, row in enumerate(zero_neg[:15], 1):
        m = row["metrics"]
        r_yr = m["total_r"] / DATA_YEARS
        marker = " <--" if (row["stop"] == 8.75 and row["rr"] == 2.625 and
                            row["gap"] == 2.25 and row["tp1"] == 0.3) else ""
        print(f"  {i:>3} {row['stop']:>5.2f} {row['rr']:>6.3f} {row['gap']:>5.2f} {row['tp1']:>5.2f} "
              f"{m['total_trades']:>5} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
              f"{m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f}{marker}")

    # ── TOP 5 (0 neg years) YEAR-BY-YEAR ──────────────────────────────
    print(f"\n{'='*110}")
    print(f"  TOP 5 (0 neg years) — Year-by-year")
    print(f"{'='*110}")
    for i, row in enumerate(zero_neg[:5], 1):
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

    # ── BEST PER STOP LEVEL ───────────────────────────────────────────
    print(f"\n{'='*110}")
    print(f"  BEST PER STOP LEVEL (0 neg years only)")
    print(f"{'='*110}")
    for stop in STOPS:
        stop_zero = [s for s in zero_neg if s["stop"] == stop]
        if not stop_zero:
            print(f"  stop={stop:>5.2f}%: no configs with 0 neg years")
            continue
        best = stop_zero[0]
        m = best["metrics"]
        r_yr = m["total_r"] / DATA_YEARS
        print(f"  stop={stop:>5.2f}%: rr={best['rr']:.3f} gap={best['gap']:.2f}% tp1={best['tp1']:.2f} → "
              f"Calmar={m['calmar_ratio']:.2f} R/yr={r_yr:.1f} DD={m['max_drawdown_r']:.1f} "
              f"N={m['total_trades']}")

    # ── R20 ANCHOR REFERENCE ──────────────────────────────────────────
    ref = [s for s in scored if s["stop"] == 8.75 and s["rr"] == 2.625 and
           s["gap"] == 2.25 and s["tp1"] == 0.3]
    if ref:
        m = ref[0]["metrics"]
        rank_all = next(i for i, s in enumerate(scored, 1)
                        if s["stop"] == 8.75 and s["rr"] == 2.625 and
                        s["gap"] == 2.25 and s["tp1"] == 0.3)
        rank_zero = next((i for i, s in enumerate(zero_neg, 1)
                          if s["stop"] == 8.75 and s["rr"] == 2.625 and
                          s["gap"] == 2.25 and s["tp1"] == 0.3), None)
        print(f"\n  R20 anchor (stop=8.75 rr=2.625 gap=2.25 tp1=0.3): "
              f"Calmar={m['calmar_ratio']:.2f} R/yr={m['total_r']/DATA_YEARS:.1f} "
              f"DD={m['max_drawdown_r']:.1f}")
        print(f"  Rank: #{rank_all} overall, #{rank_zero} among 0-neg-year configs")

    # ── GRID WINNER ───────────────────────────────────────────────────
    winner = zero_neg[0] if zero_neg else scored[0]
    m_w = winner["metrics"]
    print(f"\n  GRID WINNER (0 neg years): stop={winner['stop']}% rr={winner['rr']} "
          f"gap={winner['gap']}% tp1={winner['tp1']}")
    print(f"  Calmar={m_w['calmar_ratio']:.2f} R/yr={m_w['total_r']/DATA_YEARS:.1f} "
          f"DD={m_w['max_drawdown_r']:.1f} N={m_w['total_trades']}")

    # Check if anchor changed
    anchor_changed = not (winner["stop"] == 8.75 and winner["rr"] == 2.625 and
                          winner["gap"] == 2.25 and winner["tp1"] == 0.3)
    if anchor_changed:
        print(f"\n  ** ANCHOR MOVED — need to re-sweep structural vars **")
    else:
        print(f"\n  ** ANCHOR STABLE — ready for pipeline **")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
