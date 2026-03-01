#!/usr/bin/env python3
"""Walk-forward for 6B LDN Inversion ORB30 with magnifier.

Pipeline: Phase 2 (walk-forward + stability) for the robust pipeline.
Config: Inversion strategy, 30-min ORB, LDN session, bar magnifier.
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, with_overrides, LDN_SESSION
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import linspace_range, describe_grid
from orb_backtest.optimize.walkforward import run_walkforward, generate_windows, recency_analysis
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.results.metrics import compute_metrics

# --- Config ---
INSTRUMENT = "6B"
DATA_FILE = "6B_5m.csv"
IS_MONTHS = 36
OOS_MONTHS = 12
STEP_MONTHS = 12
OBJECTIVE = "sharpe"

# ORB30 LDN session (03:00-03:30 ORB window)
LDN_ORB30 = replace(LDN_SESSION, orb_end="03:30", entry_start="03:30")

# Parameters to sweep
PARAM_RANGES = {
    "tp1_ratio": linspace_range(0.10, 0.20, 0.05),
    "ldn_stop_atr_pct": linspace_range(8.0, 15.0, 1.0),
}


def main():
    instrument = get_instrument(INSTRUMENT)

    # Build base config: inversion, ORB30, LDN, magnifier, short-only
    base_config = default_config(instrument)
    base_config = with_overrides(base_config, sessions=(LDN_ORB30,),
        strategy="inversion", use_bar_magnifier=True,
        direction_filter="short", rr=4.0, atr_length=50)

    print("6B LDN Inversion ORB30 Walk-Forward")
    print(f"  IS: {IS_MONTHS}m | OOS: {OOS_MONTHS}m | Step: {STEP_MONTHS}m")
    print(f"  Objective: {OBJECTIVE}")
    print(f"  Bar Magnifier: enabled")
    print()
    print(describe_grid(PARAM_RANGES))
    print()

    # Load data
    print(f"Loading data: {DATA_FILE}")
    t0 = time.time()
    df = load_5m_data(DATA_FILE)
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    t1m = time.time()
    df_1m = load_1m_for_5m(DATA_FILE)
    print(f"  {len(df_1m):,} 1m bars loaded [{time.time() - t1m:.1f}s]")
    print()

    # Preview folds
    data_start = df.index[0].strftime("%Y-%m-%d")
    data_end = df.index[-1].strftime("%Y-%m-%d")
    windows = generate_windows(data_start, data_end, IS_MONTHS, OOS_MONTHS, STEP_MONTHS, anchored=False)
    print(f"Generated {len(windows)} walk-forward folds")
    for i, w in enumerate(windows):
        print(f"  Fold {i+1}: IS {w.is_start[:7]}→{w.is_end[:7]} | OOS {w.oos_start[:7]}→{w.oos_end[:7]}")
    print()

    # Run walk-forward
    t0 = time.time()
    grid_size = 1
    for v in PARAM_RANGES.values():
        grid_size *= len(v)

    def progress_fn(fold_idx, total_folds, status):
        elapsed = time.time() - t0
        if status == "done":
            print(f"\r  Fold {fold_idx + 1}/{total_folds}: done [{elapsed:.0f}s elapsed]", flush=True)
        else:
            print(f"\r  Fold {fold_idx + 1}/{total_folds}: {status} ({grid_size} combos)", end="", flush=True)

    result = run_walkforward(
        df, base_config, PARAM_RANGES,
        is_months=IS_MONTHS, oos_months=OOS_MONTHS, step_months=STEP_MONTHS,
        anchored=False, objective=OBJECTIVE,
        progress_fn=progress_fn, df_1m=df_1m,
    )
    print(f"\n  Completed in {time.time() - t0:.1f}s\n")

    # --- Per-fold results ---
    print("=" * 100)
    print("WALK-FORWARD RESULTS")
    print("=" * 100)
    param_cols = list(PARAM_RANGES.keys())
    param_hdr = " | ".join(f"{p:>15s}" for p in param_cols)
    print(f"  {'Fold':>4s} | {'IS Period':<23s} | {'OOS Period':<23s} | {'IS Sharpe':>10s} | {'OOS Sharpe':>10s} | {'OOS Trades':>10s} | {'Eff':>6s} | {param_hdr}")
    print("  " + "-" * (95 + 18 * len(param_cols)))

    for fold in result.folds:
        is_p = f"{fold.is_start[:7]} → {fold.is_end[:7]}"
        oos_p = f"{fold.oos_start[:7]} → {fold.oos_end[:7]}"
        eff = fold.oos_objective_value / fold.is_objective_value if fold.is_objective_value != 0 else 0
        oos_trades = fold.oos_metrics["total_trades"]
        pvals = " | ".join(f"{fold.best_params.get(p, 0):>15.2f}" for p in param_cols)
        print(f"  {fold.fold_index + 1:>4d} | {is_p:<23s} | {oos_p:<23s} | {fold.is_objective_value:>10.3f} | {fold.oos_objective_value:>10.3f} | {oos_trades:>10d} | {eff:>6.2f} | {pvals}")

    print()

    # --- Combined OOS ---
    m = result.combined_oos_metrics
    risk_usd = base_config.risk_usd
    import datetime
    total_oos_days = sum(
        (datetime.datetime.strptime(f.oos_end, "%Y-%m-%d") - datetime.datetime.strptime(f.oos_start, "%Y-%m-%d")).days
        for f in result.folds
    )
    oos_years = total_oos_days / 365.25
    r_per_year = (m["total_pnl_usd"] / risk_usd) / oos_years if oos_years > 0 else 0

    print(f"  Combined OOS Performance:")
    print(f"    Folds:          {len(result.folds)}")
    print(f"    OOS trades:     {m['total_trades']}")
    print(f"    OOS span:       {oos_years:.1f} years")
    print(f"    Win rate:       {m['win_rate']:.1%}")
    print(f"    Total R:        {m['total_pnl_usd'] / risk_usd:.1f}R")
    print(f"    R/year:         {r_per_year:.1f}")
    print(f"    Profit factor:  {m['profit_factor']:.2f}")
    print(f"    Sharpe:         {m['sharpe_ratio']:.3f}")
    print(f"    Sortino:        {m['sortino_ratio']:.3f}")
    print(f"    Calmar:         {m['calmar_ratio']:.2f}")
    print(f"    Max DD (R):     {m['max_drawdown_usd'] / risk_usd:.1f}R")
    print(f"    Avg R:          {m['avg_r']:.3f}")
    print()
    print(f"  Walk-Forward Efficiency: {result.walk_forward_efficiency:.2f}")
    print()

    # --- Stability analysis ---
    print("=" * 60)
    print("PARAMETER STABILITY ANALYSIS")
    print("=" * 60)
    stability = analyze_parameter_stability(result, PARAM_RANGES)
    print(f"  Overall stability score: {stability.overall_score:.2f}")
    print(f"  Interpretation: {stability.interpretation}")
    print()
    for ps in stability.params:
        print(f"  {ps.name}:")
        print(f"    Values across folds: {[f'{v:.2f}' for v in ps.values]}")
        print(f"    Mode: {ps.mode:.2f} (selected {ps.mode_frequency}/{len(result.folds)} folds)")
        print(f"    Stability score: {ps.stability_score:.2f}")
    print()

    # --- Recency analysis ---
    if len(result.folds) >= 4:
        print("=" * 60)
        print("RECENCY ANALYSIS")
        print("=" * 60)
        ra = recency_analysis(result)
        recent_m = ra["recent_metrics"]
        hist_m = ra["historical_metrics"]
        print(f"  Recent folds: {ra['recent_folds_used']} | Historical: {ra['historical_folds_used']}")
        if hist_m and hist_m["total_trades"] > 0:
            print(f"    {'Metric':<20s} {'Historical':>12s} {'Recent':>12s}")
            print(f"    {'-'*44}")
            print(f"    {'Sharpe':<20s} {hist_m['sharpe_ratio']:>12.3f} {recent_m['sharpe_ratio']:>12.3f}")
            print(f"    {'Win Rate':<20s} {hist_m['win_rate']:>11.1%} {recent_m['win_rate']:>11.1%}")
            print(f"    {'Avg R':<20s} {hist_m['avg_r']:>12.3f} {recent_m['avg_r']:>12.3f}")
            print(f"    {'Max DD (R)':<20s} {hist_m['max_drawdown_r']:>12.1f} {recent_m['max_drawdown_r']:>12.1f}")
        if ra["degradation_flag"]:
            print(f"\n    ** DEGRADATION WARNING **")
        print()

    # --- Monte Carlo ---
    from orb_backtest.engine.simulator import EXIT_NO_FILL
    filled = [t for t in result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    if len(filled) >= 10:
        r_multiples = np.array([t.r_multiple for t in filled])
        n_trades = len(r_multiples)
        n_sims = 2000
        rng = np.random.default_rng(42)

        print("=" * 60)
        print(f"MONTE CARLO ({n_sims:,} bootstrap sims, {n_trades} trades)")
        print("=" * 60)

        indices = rng.integers(0, n_trades, size=(n_sims, n_trades))
        paths = r_multiples[indices]
        equity = np.cumsum(paths, axis=1)
        final_pnl = equity[:, -1]
        running_max = np.maximum.accumulate(equity, axis=1)
        max_dd = np.min(equity - running_max, axis=1)

        def pct(arr, p): return float(np.percentile(arr, p))

        print(f"  Final PnL: p5={pct(final_pnl,5):.1f}R  p50={pct(final_pnl,50):.1f}R  p95={pct(final_pnl,95):.1f}R")
        print(f"  Max DD:    p5={pct(max_dd,5):.1f}R  p50={pct(max_dd,50):.1f}R  p95={pct(max_dd,95):.1f}R")

        # Survival at various thresholds
        for threshold in [-8.0, -10.0, -12.0]:
            survival = float(np.mean(max_dd >= threshold))
            print(f"  Survival at {threshold}R DD: {survival:.1%}")

        print()

    print("=" * 60)
    print("PHASE 2 PASS/FAIL")
    print("=" * 60)
    wf_pass = result.walk_forward_efficiency >= 0.5
    stab_pass = stability.overall_score >= 0.4
    folds_pass = len(result.folds) >= 4
    print(f"  WF Efficiency >= 0.5: {'PASS' if wf_pass else 'FAIL'} ({result.walk_forward_efficiency:.2f})")
    print(f"  Stability >= 0.4:     {'PASS' if stab_pass else 'FAIL'} ({stability.overall_score:.2f})")
    print(f"  Folds >= 4:           {'PASS' if folds_pass else 'FAIL'} ({len(result.folds)})")
    all_pass = wf_pass and stab_pass and folds_pass
    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")
    print()


if __name__ == "__main__":
    main()
