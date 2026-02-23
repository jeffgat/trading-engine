#!/usr/bin/env python3
"""YM NY Long Continuation — Grid Sweep R1.

Variable sweeps converged at R2. Structural params frozen:
  ORB: 09:30-09:45 (15m), entry until 12:00, flat 15:50-16:00
  ATR=14, direction=long, continuation, 1m magnifier
  DOW gate: excl Tuesday

Grid (centered on R2 anchor):
  stop:  [5.0, 6.0, 7.0, 7.5, 8.0, 9.0, 10.0]
  rr:    [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
  gap:   [0.5, 0.75, 1.0, 1.5, 2.0]
  tp1:   [0.3, 0.4, 0.5, 0.6]
  Total: 7 × 6 × 5 × 4 = 840 combos
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import YM
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 9  # 2017-2025 full years

DOW_EXCL = {1}  # Exclude Tuesday

# Structural params (frozen from R2)
BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="12:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=7.5,        # Placeholder — overridden in grid
    min_gap_atr_pct=1.0,     # Placeholder — overridden in grid
)

BASE_CONFIG = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=YM,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=3.0,                   # Placeholder — overridden in grid
    tp1_ratio=0.4,            # Placeholder — overridden in grid
    atr_length=14,
    impulse_close_filter=False,
    name="YM NY Grid R1",
)

# Grid dimensions
STOPS = [5.0, 6.0, 7.0, 7.5, 8.0, 9.0, 10.0]
RRS = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
GAPS = [0.5, 0.75, 1.0, 1.5, 2.0]
TP1S = [0.3, 0.4, 0.5, 0.6]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    return {yr for yr, r in m["r_by_year"].items()
            if r < 0 and str(yr) not in ("2016", "2026")}


def main():
    total = len(STOPS) * len(RRS) * len(GAPS) * len(TP1S)
    print(f"YM NY Long Continuation — Grid Sweep R1: {total} combos")
    print(f"  stop: {STOPS}")
    print(f"  rr:   {RRS}")
    print(f"  gap:  {GAPS}")
    print(f"  tp1:  {TP1S}")
    print(f"  DOW excl: Tue")
    print("=" * 110)

    # Load data
    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("YM_5m.csv")
    df_1m = load_1m_for_5m("YM_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

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
    results = run_sweep(df_5m, configs, n_workers=1, start_date=START_DATE, df_1m=df_1m)
    print(f"  Sweep done [{time.time() - t_sweep:.0f}s]")

    # Compute metrics with DOW filter
    scored = []
    for config, trades in results:
        filtered = apply_dow_filter(trades, DOW_EXCL)
        m = compute_metrics(filtered)
        sess = config.sessions[0]
        rby = m.get("r_by_year", {})
        full_years = {y: r for y, r in rby.items() if y not in ("2016", "2026")}
        n_years = max(len(full_years), 1)
        avg_annual = m["total_r"] / n_years
        calmar = avg_annual / abs(m["max_drawdown_r"]) if m["max_drawdown_r"] != 0 else 0
        scored.append({
            "stop": sess.stop_atr_pct,
            "rr": config.rr,
            "gap": sess.min_gap_atr_pct,
            "tp1": config.tp1_ratio,
            "metrics": m,
            "calmar": calmar,
            "avg_annual": avg_annual,
            "n_years": n_years,
        })

    # Sort by Calmar
    scored.sort(key=lambda x: x["calmar"], reverse=True)

    # ── TOP 30 BY CALMAR ─────────────────────────────────────────────
    print(f"\n{'='*110}")
    print(f"  TOP 30 BY CALMAR")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'stop':>5} {'rr':>5} {'gap':>5} {'tp1':>5} "
          f"{'N':>5} {'WR':>5} {'PF':>5} {'Sharpe':>7} {'Net R':>7} "
          f"{'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'NegYr':>5}")
    print(f"  {'─'*105}")

    for i, row in enumerate(scored[:30], 1):
        m = row["metrics"]
        ny = len(neg_year_set(m))
        marker = " <--" if (row["stop"] == 7.5 and row["rr"] == 3.0 and
                            row["gap"] == 1.0 and row["tp1"] == 0.4) else ""
        print(f"  {i:>3} {row['stop']:>5.1f} {row['rr']:>5.1f} {row['gap']:>5.2f} {row['tp1']:>5.2f} "
              f"{m['total_trades']:>5} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} {row['avg_annual']:>6.1f} "
              f"{m['max_drawdown_r']:>7.1f} {row['calmar']:>7.2f} {ny:>5}{marker}")

    # ── TOP 15 WITH 0 NEGATIVE YEARS ──────────────────────────────────
    zero_neg = [s for s in scored if len(neg_year_set(s["metrics"])) == 0]
    print(f"\n{'='*110}")
    print(f"  TOP 15 WITH 0 NEGATIVE YEARS ({len(zero_neg)} of {total} configs)")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'stop':>5} {'rr':>5} {'gap':>5} {'tp1':>5} "
          f"{'N':>5} {'WR':>5} {'PF':>5} {'Sharpe':>7} {'Net R':>7} "
          f"{'R/yr':>6} {'MaxDD':>7} {'Calmar':>7}")
    print(f"  {'─'*100}")

    for i, row in enumerate(zero_neg[:15], 1):
        m = row["metrics"]
        marker = " <--" if (row["stop"] == 7.5 and row["rr"] == 3.0 and
                            row["gap"] == 1.0 and row["tp1"] == 0.4) else ""
        print(f"  {i:>3} {row['stop']:>5.1f} {row['rr']:>5.1f} {row['gap']:>5.02f} {row['tp1']:>5.02f} "
              f"{m['total_trades']:>5} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>7.2f} {m['total_r']:>7.1f} {row['avg_annual']:>6.1f} "
              f"{m['max_drawdown_r']:>7.1f} {row['calmar']:>7.2f}{marker}")

    # ── TOP 5 (0 neg years) YEAR-BY-YEAR ──────────────────────────────
    print(f"\n{'='*110}")
    print(f"  TOP 5 (0 neg years) — Year-by-year")
    print(f"{'='*110}")
    for i, row in enumerate(zero_neg[:5], 1):
        m = row["metrics"]
        print(f"\n  #{i}: stop={row['stop']}% rr={row['rr']} gap={row['gap']}% tp1={row['tp1']}")
        print(f"      N={m['total_trades']} WR={m['win_rate']:.1%} PF={m['profit_factor']:.2f} "
              f"Sharpe={m['sharpe_ratio']:.2f} Net R={m['total_r']:.1f} R/yr={row['avg_annual']:.1f} "
              f"DD={m['max_drawdown_r']:.1f} Calmar={row['calmar']:.2f}")
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
            print(f"  stop={stop:>5.1f}%: no configs with 0 neg years")
            continue
        best = stop_zero[0]
        m = best["metrics"]
        print(f"  stop={stop:>5.1f}%: rr={best['rr']:.1f} gap={best['gap']:.2f}% tp1={best['tp1']:.2f} → "
              f"Calmar={best['calmar']:.2f} R/yr={best['avg_annual']:.1f} DD={m['max_drawdown_r']:.1f} "
              f"N={m['total_trades']}")

    # ── R2 ANCHOR REFERENCE ──────────────────────────────────────────
    ref = [s for s in scored if s["stop"] == 7.5 and s["rr"] == 3.0 and
           s["gap"] == 1.0 and s["tp1"] == 0.4]
    if ref:
        m = ref[0]["metrics"]
        rank_all = next(i for i, s in enumerate(scored, 1)
                        if s["stop"] == 7.5 and s["rr"] == 3.0 and
                        s["gap"] == 1.0 and s["tp1"] == 0.4)
        rank_zero = next((i for i, s in enumerate(zero_neg, 1)
                          if s["stop"] == 7.5 and s["rr"] == 3.0 and
                          s["gap"] == 1.0 and s["tp1"] == 0.4), None)
        print(f"\n  R2 anchor (stop=7.5 rr=3.0 gap=1.0 tp1=0.4): "
              f"Calmar={ref[0]['calmar']:.2f} R/yr={ref[0]['avg_annual']:.1f} "
              f"DD={m['max_drawdown_r']:.1f}")
        print(f"  Rank: #{rank_all} overall, #{rank_zero} among 0-neg-year configs")

    # ── GRID WINNER ───────────────────────────────────────────────────
    winner = zero_neg[0] if zero_neg else scored[0]
    m_w = winner["metrics"]
    print(f"\n  GRID WINNER (0 neg years): stop={winner['stop']}% rr={winner['rr']} "
          f"gap={winner['gap']}% tp1={winner['tp1']}")
    print(f"  Calmar={winner['calmar']:.2f} R/yr={winner['avg_annual']:.1f} "
          f"DD={m_w['max_drawdown_r']:.1f} N={m_w['total_trades']}")

    # Check if anchor changed
    anchor_changed = not (winner["stop"] == 7.5 and winner["rr"] == 3.0 and
                          winner["gap"] == 1.0 and winner["tp1"] == 0.4)
    if anchor_changed:
        print(f"\n  ** ANCHOR MOVED — need to re-sweep structural vars **")
    else:
        print(f"\n  ** ANCHOR STABLE — ready for pipeline **")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
