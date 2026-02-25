#!/usr/bin/env python3
"""YM Robust Pipeline — directional variants.

Usage:
  uv run python scripts/run_ym_robust_directional.py --session NY --direction short
  uv run python scripts/run_ym_robust_directional.py --session Asia --direction long
"""

import argparse
import sys
import time

sys.path.insert(0, "src")

import numpy as np

from orb_backtest.config import (
    ASIA_SESSION,
    LDN_SESSION,
    NY_SESSION,
    StrategyConfig,
    with_overrides,
)
from orb_backtest.data.instruments import YM
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.optimize.prop_constraints import (
    PropFirmConstraints,
    evaluate_constraints,
    evaluate_constraints_mc,
)
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.simulate.monte_carlo import MonteCarloConfig, run_monte_carlo

SESSION_MAP = {
    "NY": (NY_SESSION,),
    "Asia": (ASIA_SESSION,),
    "LDN": (LDN_SESSION,),
}

# Session-prefixed param names
SESSION_PARAM_PREFIX = {
    "NY": "ny",
    "Asia": "asia",
    "LDN": "ldn",
}

WF_START = "2016-01-01"
WF_END_SLICE = "2025-01-31"
HOLDOUT_START = "2025-01-01"
N_WORKERS = 8

PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=999.0,    # DD is NOT a hard filter (user preference)
    min_annual_r=24.0,
    max_monthly_loss_r=5.0,
    min_positive_expectancy=True,
)


def fmt(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def sep(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, choices=["NY", "Asia", "LDN"])
    parser.add_argument("--direction", required=True, choices=["long", "short", "both"])
    args = parser.parse_args()

    sess_name = args.session
    direction = args.direction
    prefix = SESSION_PARAM_PREFIX[sess_name]

    label = f"YM {sess_name} {direction}-only continuation (magnifier)"
    sep(f"ROBUST PIPELINE: {label}")

    # Build param ranges with session prefix
    param_ranges = {
        "rr": [2.0, 2.5, 3.0, 3.5],
        f"{prefix}_stop_atr_pct": [5.0, 7.5, 10.0, 12.5, 15.0],
        f"{prefix}_min_gap_atr_pct": [1.0, 1.5, 2.0, 2.5],
        "tp1_ratio": [0.4, 0.5, 0.6],
    }
    grid_size = 1
    for v in param_ranges.values():
        grid_size *= len(v)

    # Load data
    sep("Loading data")
    t0 = time.time()
    df_5m = load_5m_data("YM_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("YM_5m.csv", start=None, end=None)
    df_1s = load_1s_for_5m("YM_5m.csv", start=None, end=None)
    print(f"5m: {len(df_5m):,} bars  |  1m: {len(df_1m):,} bars  |  {time.time()-t0:.1f}s")
    if df_1s is not None:
        print(f"1s: {len(df_1s):,} bars")
    else:
        print("1s: NOT FOUND")

    base_config = StrategyConfig(
        sessions=SESSION_MAP[sess_name],
        instrument=YM,
        strategy="continuation",
        direction_filter=direction,
        use_bar_magnifier=True,
        name=f"YM {sess_name} {direction} Robust Pipeline",
    )

    # ── PHASE 1 ──────────────────────────────────────────────────────
    sep("PHASE 1: Structural Validation")
    t0 = time.time()
    p1_trades = run_backtest(df_5m, base_config, start_date=WF_START, df_1m=df_1m, df_1s=df_1s)
    p1_m = compute_metrics(p1_trades)
    print(f"Completed in {time.time()-t0:.1f}s")

    checks = [
        ("Total trades", p1_m["total_trades"], ">=100", p1_m["total_trades"] >= 100),
        ("Win rate", f"{p1_m['win_rate']:.1%}", ">=35%", p1_m["win_rate"] >= 0.35),
        ("Profit factor", f"{p1_m['profit_factor']:.2f}", ">=1.0", p1_m["profit_factor"] >= 1.0),
        ("Max consec losses", p1_m["max_consecutive_losses"], "<=15", p1_m["max_consecutive_losses"] <= 15),
    ]
    print(f"\n{'Metric':<25} {'Value':>10}  {'Threshold':>10}  {'Result':>6}")
    print("-" * 57)
    for name, val, thresh, ok in checks:
        print(f"{name:<25} {str(val):>10}  {thresh:>10}  {fmt(ok):>6}")

    p1_passed = all(ok for _, _, _, ok in checks)
    print(f"\n  Sharpe={p1_m['sharpe_ratio']:.2f}, Total R={p1_m['total_r']:.1f}, "
          f"Max DD={p1_m['max_drawdown_r']:.1f}R, Calmar={p1_m['calmar_ratio']:.2f}")
    print(f"  Exit breakdown: {dict(sorted(p1_m['exit_breakdown'].items()))}")
    print(f"\n  >> PHASE 1: {fmt(p1_passed)}")

    if not p1_passed:
        print("  Structural validation failed. Continuing for diagnostics...\n")

    # ── PHASE 2 ──────────────────────────────────────────────────────
    sep("PHASE 2: Walk-Forward + Stability")
    # NOTE: WF uses 1m magnifier only (not 1s). The 1s maps are too large
    # and serializing them for multiprocessing workers is prohibitively slow.
    # 1m fill precision is sufficient for parameter stability analysis.
    print(f"36m IS / 12m OOS / 12m step | {grid_size} combos x {N_WORKERS} workers")
    print(f"Magnifier: 1m (1s too large for multiprocessing serialization)")

    df_wf = df_5m.loc[:WF_END_SLICE]
    df_wf_1m = df_1m.loc[:WF_END_SLICE] if df_1m is not None else None

    def progress(fi, total, status):
        print(f"  Fold {fi+1}/{total}: {status}")

    t0 = time.time()
    wf = run_walkforward(
        df_wf, base_config, param_ranges,
        is_months=36, oos_months=12, step_months=12,
        anchored=False, objective="sharpe", n_workers=N_WORKERS,
        start_date=WF_START, progress_fn=progress, df_1m=df_wf_1m,
    )
    print(f"\nCompleted in {time.time()-t0:.0f}s ({len(wf.folds)} folds)")

    # Per-fold table
    print(f"\n{'Fold':<5} {'IS Period':<24} {'OOS Period':<24} {'IS Obj':>7} {'OOS Obj':>8} {'Params'}")
    print("-" * 110)
    for f in wf.folds:
        ps = ", ".join(f"{k}={v}" for k, v in f.best_params.items())
        print(f"{f.fold_index+1:<5} {f.is_start}->{f.is_end:<13} "
              f"{f.oos_start}->{f.oos_end:<13} "
              f"{f.is_objective_value:>7.2f} {f.oos_objective_value:>8.2f} {ps}")

    stability = analyze_parameter_stability(wf, param_ranges)

    print(f"\nStability (overall={stability.overall_score:.2f}, {stability.interpretation}):")
    for p in stability.params:
        print(f"  {p.name:<25} mode={p.mode:<8.2f} score={p.stability_score:.2f}  range={p.value_range}")

    cm = wf.combined_oos_metrics
    print(f"\nCombined OOS: {cm['total_trades']} trades, WR={cm['win_rate']:.1%}, "
          f"PF={cm['profit_factor']:.2f}, Sharpe={cm['sharpe_ratio']:.2f}, "
          f"R={cm['total_r']:.1f}, DD={cm['max_drawdown_r']:.1f}R")

    p2_wfe = wf.walk_forward_efficiency >= 0.5
    p2_stab = stability.overall_score >= 0.4
    p2_folds = len(wf.folds) >= 4
    p2_passed = p2_wfe and p2_stab and p2_folds

    print(f"\n  WF efficiency: {wf.walk_forward_efficiency:.2f} ({fmt(p2_wfe)})")
    print(f"  Stability: {stability.overall_score:.2f} ({fmt(p2_stab)})")
    print(f"  Folds: {len(wf.folds)} ({fmt(p2_folds)})")
    print(f"\n  >> PHASE 2: {fmt(p2_passed)}")

    # ── PHASE 3 ──────────────────────────────────────────────────────
    sep("PHASE 3: Prop Firm Constraint Filter")
    cr = evaluate_constraints(wf.combined_oos_trades, PROP_CONSTRAINTS)

    print(f"  Max DD: {cr.max_drawdown_r:.1f}R ({fmt(cr.max_drawdown_passed)})")
    print(f"  Worst month: {cr.worst_month_r:.1f}R ({fmt(cr.monthly_loss_passed)})")
    print(f"  Expectancy: {cr.expectancy:.3f}R ({fmt(cr.expectancy_passed)})")
    print(f"  Annual R: {fmt(cr.annual_r_passed)}")
    if cr.annual_r_values:
        for yr, rv in sorted(cr.annual_r_values.items()):
            print(f"    {yr}: {rv:+.1f}R")
    print(f"  Stats: {cr.total_trades} trades, {cr.win_rate:.1%} WR, "
          f"avg win {cr.avg_win_r:.2f}R, avg loss {cr.avg_loss_r:.2f}R")

    p3_passed = cr.passed
    print(f"\n  >> PHASE 3: {fmt(p3_passed)}")

    # ── PHASE 4 ──────────────────────────────────────────────────────
    sep("PHASE 4: Hold-Out OOS")
    mode_params = {p.name: p.mode for p in stability.params}
    holdout_cfg = with_overrides(base_config, **mode_params)
    print(f"Period: {HOLDOUT_START} -> present | Mode params: {mode_params}")

    t0 = time.time()
    ho_trades = run_backtest(df_5m, holdout_cfg, start_date=HOLDOUT_START, df_1m=df_1m, df_1s=df_1s)
    ho_m = compute_metrics(ho_trades)
    print(f"Completed in {time.time()-t0:.1f}s")

    p4_sharpe = ho_m["sharpe_ratio"] > 0.5
    p4_pf = ho_m["profit_factor"] > 1.0
    p4_r = ho_m["total_r"] > 0
    p4_passed = p4_sharpe and p4_pf and p4_r

    print(f"\n  {ho_m['total_trades']} trades, WR={ho_m['win_rate']:.1%}")
    print(f"  Sharpe={ho_m['sharpe_ratio']:.2f} ({fmt(p4_sharpe)}), "
          f"PF={ho_m['profit_factor']:.2f} ({fmt(p4_pf)}), "
          f"R={ho_m['total_r']:+.1f} ({fmt(p4_r)})")
    print(f"  Max DD={ho_m['max_drawdown_r']:.1f}R, Calmar={ho_m['calmar_ratio']:.2f}")
    print(f"\n  >> PHASE 4: {fmt(p4_passed)}")

    # ── PHASE 5 ──────────────────────────────────────────────────────
    sep("PHASE 5: Monte Carlo Survival")
    mc_cfg = MonteCarloConfig(n_simulations=2000, method="bootstrap", seed=42)
    t0 = time.time()
    MC_RUIN_THRESHOLD = -25.0  # standalone ruin threshold, not tied to prop DD
    mc = run_monte_carlo(wf.combined_oos_trades, mc_cfg,
                         ruin_threshold=MC_RUIN_THRESHOLD)
    print(f"2000 bootstrap sims in {time.time()-t0:.1f}s")

    dates = [t.date for t in wf.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_surv = evaluate_constraints_mc(mc, PROP_CONSTRAINTS, trade_dates=dates)

    p5_surv = mc_surv["survival_rate"] >= 0.70
    p5_dd95 = mc_surv["dd_percentiles"]["p95"] <= abs(MC_RUIN_THRESHOLD) * 1.2
    p5_passed = p5_surv and p5_dd95

    print(f"\n  Survival: {mc_surv['survival_rate']:.1%} ({fmt(p5_surv)})")
    print(f"  DD p95: {mc_surv['dd_percentiles']['p95']:.1f}R ({fmt(p5_dd95)})")
    print(f"  DD percentiles: {mc_surv['dd_percentiles']}")
    print(f"  Ruin prob: {mc.ruin_probability:.1%}")
    print(f"  Actual PnL: {mc.actual_final_pnl:.1f}R, Actual DD: {mc.actual_max_drawdown:.1f}R")
    if "monthly_loss_pass_rate" in mc_surv:
        print(f"  Monthly loss pass rate: {mc_surv['monthly_loss_pass_rate']:.1%}")
    if "annual_r_pass_rate" in mc_surv:
        print(f"  Annual R pass rate: {mc_surv['annual_r_pass_rate']:.1%}")

    if mc_surv["survival_rate"] >= 0.80:
        interp = "Strong -- deploy with full size"
    elif mc_surv["survival_rate"] >= 0.70:
        interp = "Acceptable -- deploy, monitor closely"
    elif mc_surv["survival_rate"] >= 0.50:
        interp = "Conditional -- reduce size or tighten stops"
    else:
        interp = "No-go -- strategy will likely breach"
    print(f"  Interpretation: {interp}")
    print(f"\n  >> PHASE 5: {fmt(p5_passed)}")

    # ── VERDICT ──────────────────────────────────────────────────────
    sep(f"VERDICT: {label}")

    phases = [
        ("Phase 1 (Structural)", p1_passed),
        ("Phase 2 (Walk-Forward)", p2_passed),
        ("Phase 3 (Prop Filter)", p3_passed),
        ("Phase 4 (Hold-Out)", p4_passed),
        ("Phase 5 (MC Survival)", p5_passed),
    ]
    for name, passed in phases:
        print(f"  {name + ':':<28} {fmt(passed)}")

    all_14 = all(p for _, p in phases[:4])
    if all_14 and p5_passed:
        print(f"\n  >> VERDICT: GO")
    elif all_14 and mc_surv["survival_rate"] >= 0.50:
        print(f"\n  >> VERDICT: CONDITIONAL")
    else:
        failed = [n for n, p in phases if not p]
        print(f"\n  >> VERDICT: NO-GO")
        print(f"     Failed: {', '.join(failed)}")

    print(f"\n  Mode params: {mode_params}")


if __name__ == "__main__":
    main()
