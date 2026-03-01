#!/usr/bin/env python3
"""NQ Asia ORB — Grid sweep on R4 anchor (fully converged).

R4 anchor (all structural vars converged):
  ORB: 20:00-20:10 (10m), entry until 01:00, flat 00:00
  ATR=5, direction=both, continuation, 1s magnifier, no-Thursday, ICF=OFF

Current continuous params: stop=3.7% rr=1.75 gap=0.90% tp1=0.35

Grid (broad, centered on R4 anchor):
  stop:  [2.5, 3.0, 3.5, 3.7, 4.0, 4.5, 5.0, 6.0]
  rr:    [1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
  gap:   [0.50, 0.75, 0.90, 1.10, 1.25, 1.50]
  tp1:   [0.2, 0.25, 0.3, 0.35, 0.4, 0.5]
  Total: 8 × 7 × 6 × 6 = 2,016 combos
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

# Structural params (frozen from R4)
BASE_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:10",
    entry_start="20:10",
    entry_end="01:00",
    flat_start="00:00",
    flat_end="07:00",
    stop_atr_pct=3.7,       # placeholder — overridden
    min_gap_atr_pct=0.90,   # placeholder — overridden
)

BASE_CONFIG = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=1.75,                 # placeholder — overridden
    tp1_ratio=0.35,          # placeholder — overridden
    atr_length=5,
    name="NQ Asia Grid R4",
)

# Grid dimensions
STOPS = [2.5, 3.0, 3.5, 3.7, 4.0, 4.5, 5.0, 6.0]
RRS = [1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
GAPS = [0.50, 0.75, 0.90, 1.10, 1.25, 1.50]
TP1S = [0.2, 0.25, 0.3, 0.35, 0.4, 0.5]

DOW_EXCL = {3}  # no-Thursday


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    total = len(STOPS) * len(RRS) * len(GAPS) * len(TP1S)
    print(f"NQ Asia ORB — Grid Sweep R4: {total} combos")
    print(f"  stop: {STOPS}")
    print(f"  rr:   {RRS}")
    print(f"  gap:  {GAPS}")
    print(f"  tp1:  {TP1S}")
    print("=" * 110)

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

    # Compute metrics for all (with no-Thursday gate)
    scored = []
    for config, trades in results:
        gated = apply_dow_filter(trades, DOW_EXCL)
        m = compute_metrics(gated)
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
        marker = " <--" if (abs(row["stop"] - 3.7) < 0.01 and abs(row["rr"] - 1.75) < 0.01 and
                            abs(row["gap"] - 0.90) < 0.01 and abs(row["tp1"] - 0.35) < 0.01) else ""
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
        marker = " <--" if (abs(row["stop"] - 3.7) < 0.01 and abs(row["rr"] - 1.75) < 0.01 and
                            abs(row["gap"] - 0.90) < 0.01 and abs(row["tp1"] - 0.35) < 0.01) else ""
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
        stop_zero = [s for s in zero_neg if abs(s["stop"] - stop) < 0.01]
        if not stop_zero:
            print(f"  stop={stop:>5.2f}%: no configs with 0 neg years")
            continue
        best = stop_zero[0]
        m = best["metrics"]
        r_yr = m["total_r"] / DATA_YEARS
        print(f"  stop={stop:>5.2f}%: rr={best['rr']:.3f} gap={best['gap']:.2f}% tp1={best['tp1']:.2f} → "
              f"Calmar={m['calmar_ratio']:.2f} R/yr={r_yr:.1f} DD={m['max_drawdown_r']:.1f} "
              f"N={m['total_trades']}")

    # ── R4 ANCHOR REFERENCE ──────────────────────────────────────────
    ref = [s for s in scored if abs(s["stop"] - 3.7) < 0.01 and abs(s["rr"] - 1.75) < 0.01 and
           abs(s["gap"] - 0.90) < 0.01 and abs(s["tp1"] - 0.35) < 0.01]
    if ref:
        m = ref[0]["metrics"]
        rank_all = next(i for i, s in enumerate(scored, 1)
                        if abs(s["stop"] - 3.7) < 0.01 and abs(s["rr"] - 1.75) < 0.01 and
                        abs(s["gap"] - 0.90) < 0.01 and abs(s["tp1"] - 0.35) < 0.01)
        rank_zero = next((i for i, s in enumerate(zero_neg, 1)
                          if abs(s["stop"] - 3.7) < 0.01 and abs(s["rr"] - 1.75) < 0.01 and
                          abs(s["gap"] - 0.90) < 0.01 and abs(s["tp1"] - 0.35) < 0.01), None)
        print(f"\n  R4 anchor (stop=3.7 rr=1.75 gap=0.90 tp1=0.35): "
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
    anchor_changed = not (abs(winner["stop"] - 3.7) < 0.01 and abs(winner["rr"] - 1.75) < 0.01 and
                          abs(winner["gap"] - 0.90) < 0.01 and abs(winner["tp1"] - 0.35) < 0.01)
    if anchor_changed:
        print(f"\n  ** ANCHOR MOVED — need fine-tune around new winner **")
    else:
        print(f"\n  ** ANCHOR STABLE — ready for pipeline **")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
