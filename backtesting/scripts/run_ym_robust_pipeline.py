#!/usr/bin/env python3
"""YM Robust Pipeline — 5-phase prop firm validation.

Instrument: YM (Dow Jones), continuation strategy, bar magnifier enabled.
Data range: ~2016-01-01 to 2026-02-16 (~10 years).
Sessions: NY only.

Phases:
  1. Structural validation (full history, default params)
  2. Walk-forward + parameter stability (36m IS / 12m OOS / 12m step)
  3. Prop firm constraint filter (on combined WF OOS trades)
  4. Hold-out OOS test (2025-01-01 onward, mode params from WF)
  5. Monte Carlo survival (2000 bootstrap sims on WF OOS trades)
"""

import sys
import time

sys.path.insert(0, "src")

import numpy as np

from orb_backtest.config import (
    NY_SESSION,
    StrategyConfig,
    with_overrides,
)
from orb_backtest.data.instruments import YM
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
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

# ── Configuration ──────────────────────────────────────────────────────────
WF_START = "2016-01-01"
WF_END_SLICE = "2025-01-31"   # slice df for WF so OOS doesn't bleed into hold-out
HOLDOUT_START = "2025-01-01"
N_WORKERS = 8

PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=999.0,    # DD is NOT a hard filter (user preference)
    min_annual_r=24.0,
    max_monthly_loss_r=5.0,
    min_positive_expectancy=True,
)

# Walk-forward sweep ranges
PARAM_RANGES = {
    "rr": [2.0, 2.5, 3.0, 3.5],
    "ny_stop_atr_pct": [5.0, 7.5, 10.0, 12.5, 15.0],
    "ny_min_gap_atr_pct": [1.0, 1.5, 2.0, 2.5],
    "tp1_ratio": [0.4, 0.5, 0.6],
}

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)


def fmt_pass(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def separator(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def main():
    # ── Load data ──────────────────────────────────────────────────────
    separator("Loading YM data (5m + 1m for magnifier)")

    t0 = time.time()
    df_5m = load_5m_data("YM_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("YM_5m.csv", start=None, end=None)
    print(f"5m bars: {len(df_5m):,}  |  1m bars: {len(df_1m):,}")
    print(f"Date range: {df_5m.index[0]} -> {df_5m.index[-1]}")
    print(f"Loaded in {time.time() - t0:.1f}s")

    # Base config: YM NY continuation with magnifier
    base_config = StrategyConfig(
        sessions=(NY_SESSION,),
        instrument=YM,
        strategy="continuation",
        use_bar_magnifier=True,
        name="YM NY Robust Pipeline",
    )

    # ==================================================================
    # PHASE 1: Structural Validation
    # ==================================================================
    separator("PHASE 1: Structural Validation")
    print("Running full-history backtest with default params + magnifier...")

    t0 = time.time()
    p1_trades = run_backtest(df_5m, base_config, start_date=WF_START, df_1m=df_1m)
    p1_metrics = compute_metrics(p1_trades)
    print(f"Completed in {time.time() - t0:.1f}s")

    # Check criteria
    p1_trades_ok = p1_metrics["total_trades"] >= 100
    p1_wr_ok = p1_metrics["win_rate"] >= 0.35
    p1_pf_ok = p1_metrics["profit_factor"] >= 1.0
    p1_consec_ok = p1_metrics["max_consecutive_losses"] <= 15
    p1_passed = p1_trades_ok and p1_wr_ok and p1_pf_ok and p1_consec_ok

    print(f"\n{'Metric':<28} {'Value':>10}  {'Threshold':>10}  {'Result':>8}")
    print("-" * 62)
    print(f"{'Total trades':<28} {p1_metrics['total_trades']:>10}  {'>=100':>10}  {fmt_pass(p1_trades_ok):>8}")
    print(f"{'Win rate':<28} {p1_metrics['win_rate']:>10.1%}  {'>=35%':>10}  {fmt_pass(p1_wr_ok):>8}")
    print(f"{'Profit factor':<28} {p1_metrics['profit_factor']:>10.2f}  {'>=1.0':>10}  {fmt_pass(p1_pf_ok):>8}")
    print(f"{'Max consecutive losses':<28} {p1_metrics['max_consecutive_losses']:>10}  {'<=15':>10}  {fmt_pass(p1_consec_ok):>8}")
    print(f"\n  Additional: Sharpe={p1_metrics['sharpe_ratio']:.2f}, "
          f"Total R={p1_metrics['total_r']:.1f}, "
          f"Max DD={p1_metrics['max_drawdown_r']:.1f}R, "
          f"Calmar={p1_metrics['calmar_ratio']:.2f}")

    print(f"\n  Exit breakdown:")
    for exit_name, count in sorted(p1_metrics["exit_breakdown"].items()):
        print(f"    {exit_name}: {count}")

    print(f"\n  >> PHASE 1: {fmt_pass(p1_passed)}")

    if not p1_passed:
        print("\n  Strategy fails structural validation. Pipeline stops here.")
        sys.exit(1)

    # ==================================================================
    # PHASE 2: Walk-Forward + Parameter Stability
    # ==================================================================
    separator("PHASE 2: Walk-Forward Optimization + Stability")
    print(f"Config: 36m IS / 12m OOS / 12m step (rolling)")
    print(f"Sweep: {GRID_SIZE} combos per fold x {N_WORKERS} workers")
    print(f"Params: {', '.join(f'{k}={v}' for k, v in PARAM_RANGES.items())}")

    # Slice data to prevent OOS from bleeding into hold-out
    df_wf = df_5m.loc[:WF_END_SLICE]
    df_wf_1m = df_1m.loc[:WF_END_SLICE]
    print(f"WF data range: {df_wf.index[0]} -> {df_wf.index[-1]}")

    def wf_progress(fold_idx, total_folds, status):
        print(f"  Fold {fold_idx + 1}/{total_folds}: {status}")

    t0 = time.time()
    wf_result = run_walkforward(
        df_wf,
        base_config,
        PARAM_RANGES,
        is_months=36,
        oos_months=12,
        step_months=12,
        anchored=False,
        objective="sharpe",
        n_workers=N_WORKERS,
        start_date=WF_START,
        progress_fn=wf_progress,
        df_1m=df_wf_1m,
    )
    wf_elapsed = time.time() - t0
    print(f"\nWalk-forward completed in {wf_elapsed:.0f}s ({len(wf_result.folds)} folds)")

    # Per-fold summary
    print(f"\n{'Fold':<6} {'IS Period':<25} {'OOS Period':<25} {'IS Sharpe':>10} {'OOS Sharpe':>11} {'Best Params'}")
    print("-" * 120)
    for f in wf_result.folds:
        params_str = ", ".join(f"{k}={v}" for k, v in f.best_params.items())
        print(f"{f.fold_index + 1:<6} "
              f"{f.is_start}->{f.is_end:<14} "
              f"{f.oos_start}->{f.oos_end:<14} "
              f"{f.is_objective_value:>10.2f} "
              f"{f.oos_objective_value:>11.2f} "
              f"{params_str}")

    # WF efficiency
    p2_wfe_ok = wf_result.walk_forward_efficiency >= 0.5
    p2_folds_ok = len(wf_result.folds) >= 4

    # Stability
    stability = analyze_parameter_stability(wf_result, PARAM_RANGES)
    p2_stability_ok = stability.overall_score >= 0.4

    print(f"\nParameter Stability:")
    print(f"  {'Param':<25} {'Mode':>8} {'Score':>8} {'Range':<20} {'Unique':>8}")
    print(f"  {'-'*73}")
    for p in stability.params:
        print(f"  {p.name:<25} {p.mode:>8.2f} {p.stability_score:>8.2f} "
              f"{str(p.value_range):<20} {p.unique_values:>8}")

    # Combined OOS metrics
    cm = wf_result.combined_oos_metrics
    print(f"\nCombined OOS Metrics:")
    print(f"  Trades: {cm['total_trades']}, Win Rate: {cm['win_rate']:.1%}, "
          f"PF: {cm['profit_factor']:.2f}")
    print(f"  Total R: {cm['total_r']:.1f}, Sharpe: {cm['sharpe_ratio']:.2f}, "
          f"Max DD: {cm['max_drawdown_r']:.1f}R")

    p2_passed = p2_wfe_ok and p2_stability_ok and p2_folds_ok

    print(f"\n{'Check':<28} {'Value':>10}  {'Threshold':>10}  {'Result':>8}")
    print("-" * 62)
    print(f"{'WF efficiency':<28} {wf_result.walk_forward_efficiency:>10.2f}  {'>=0.50':>10}  {fmt_pass(p2_wfe_ok):>8}")
    print(f"{'Stability score':<28} {stability.overall_score:>10.2f}  {'>=0.40':>10}  {fmt_pass(p2_stability_ok):>8}")
    print(f"{'Folds completed':<28} {len(wf_result.folds):>10}  {'>=4':>10}  {fmt_pass(p2_folds_ok):>8}")
    print(f"{'Stability interpretation':<28} {stability.interpretation:>10}")

    print(f"\n  >> PHASE 2: {fmt_pass(p2_passed)}")

    if not p2_passed:
        print("\n  Walk-forward validation failed. Continuing pipeline for diagnostics...")

    # ==================================================================
    # PHASE 3: Prop Firm Constraint Filter
    # ==================================================================
    separator("PHASE 3: Prop Firm Constraint Filter")
    print(f"Evaluating {len(wf_result.combined_oos_trades)} combined OOS trades against prop constraints...")
    print(f"Constraints: DD<={PROP_CONSTRAINTS.max_drawdown_r}R, "
          f"Annual>={PROP_CONSTRAINTS.min_annual_r}R, "
          f"Monthly Loss<={PROP_CONSTRAINTS.max_monthly_loss_r}R")

    cr = evaluate_constraints(wf_result.combined_oos_trades, PROP_CONSTRAINTS)

    print(f"\n{'Constraint':<28} {'Value':>12}  {'Threshold':>12}  {'Result':>8}")
    print("-" * 66)
    print(f"{'Max drawdown':<28} {cr.max_drawdown_r:>12.1f}R {'<=' + str(PROP_CONSTRAINTS.max_drawdown_r) + 'R':>12}  {fmt_pass(cr.max_drawdown_passed):>8}")
    print(f"{'Worst monthly loss':<28} {cr.worst_month_r:>12.1f}R {'<=' + str(PROP_CONSTRAINTS.max_monthly_loss_r) + 'R':>12}  {fmt_pass(cr.monthly_loss_passed):>8}")
    print(f"{'Expectancy':<28} {cr.expectancy:>12.3f}R {'> 0':>12}  {fmt_pass(cr.expectancy_passed):>8}")
    print(f"{'Annual R (full years)':<28} {'':>12}  {'>=' + str(PROP_CONSTRAINTS.min_annual_r) + 'R':>12}  {fmt_pass(cr.annual_r_passed):>8}")

    if cr.annual_r_values:
        print(f"\n  Annual R by year:")
        for year, r_val in sorted(cr.annual_r_values.items()):
            print(f"    {year}: {r_val:+.1f}R")

    print(f"\n  Supporting stats: {cr.total_trades} trades, {cr.win_rate:.1%} WR, "
          f"avg win {cr.avg_win_r:.2f}R, avg loss {cr.avg_loss_r:.2f}R, "
          f"max consec losses {cr.max_consecutive_losses}")

    p3_passed = cr.passed
    print(f"\n  >> PHASE 3: {fmt_pass(p3_passed)}")

    if not p3_passed:
        print("\n  Prop constraint filter failed. Continuing for diagnostics...")

    # ==================================================================
    # PHASE 4: Hold-Out OOS Test
    # ==================================================================
    separator("PHASE 4: Hold-Out OOS Test")

    # Use mode params from stability analysis
    mode_params = {p.name: p.mode for p in stability.params}
    holdout_config = with_overrides(base_config, **mode_params)

    print(f"Hold-out period: {HOLDOUT_START} -> present")
    print(f"Mode params from WF: {mode_params}")

    t0 = time.time()
    holdout_trades = run_backtest(df_5m, holdout_config, start_date=HOLDOUT_START, df_1m=df_1m)
    holdout_m = compute_metrics(holdout_trades)
    print(f"Completed in {time.time() - t0:.1f}s")

    p4_sharpe_ok = holdout_m["sharpe_ratio"] > 0.5
    p4_pf_ok = holdout_m["profit_factor"] > 1.0
    p4_r_ok = holdout_m["total_r"] > 0
    p4_passed = p4_sharpe_ok and p4_pf_ok and p4_r_ok

    print(f"\n{'Metric':<28} {'Value':>10}  {'Threshold':>10}  {'Result':>8}")
    print("-" * 62)
    print(f"{'Sharpe ratio':<28} {holdout_m['sharpe_ratio']:>10.2f}  {'>0.50':>10}  {fmt_pass(p4_sharpe_ok):>8}")
    print(f"{'Profit factor':<28} {holdout_m['profit_factor']:>10.2f}  {'>1.0':>10}  {fmt_pass(p4_pf_ok):>8}")
    print(f"{'Total R':<28} {holdout_m['total_r']:>10.1f}  {'>0':>10}  {fmt_pass(p4_r_ok):>8}")
    print(f"\n  Additional: {holdout_m['total_trades']} trades, "
          f"WR={holdout_m['win_rate']:.1%}, "
          f"Max DD={holdout_m['max_drawdown_r']:.1f}R, "
          f"Calmar={holdout_m['calmar_ratio']:.2f}")

    print(f"\n  Exit breakdown:")
    for exit_name, count in sorted(holdout_m["exit_breakdown"].items()):
        print(f"    {exit_name}: {count}")

    print(f"\n  >> PHASE 4: {fmt_pass(p4_passed)}")

    if not p4_passed:
        print("\n  Hold-out test failed. Continuing for diagnostics...")

    # ==================================================================
    # PHASE 5: Monte Carlo Survival
    # ==================================================================
    separator("PHASE 5: Monte Carlo Survival")
    print("Running 2000 bootstrap simulations on WF OOS trades...")

    mc_config = MonteCarloConfig(n_simulations=2000, method="bootstrap", seed=42)
    t0 = time.time()
    mc_result = run_monte_carlo(
        wf_result.combined_oos_trades,
        mc_config,
        ruin_threshold=-PROP_CONSTRAINTS.max_drawdown_r,
    )
    print(f"MC completed in {time.time() - t0:.1f}s")

    # Prop constraint survival
    trade_dates = [t.date for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_surv = evaluate_constraints_mc(mc_result, PROP_CONSTRAINTS, trade_dates=trade_dates)

    p5_survival_ok = mc_surv["survival_rate"] >= 0.70
    p5_dd95_ok = mc_surv["dd_percentiles"]["p95"] <= PROP_CONSTRAINTS.max_drawdown_r * 1.2

    print(f"\n{'Metric':<28} {'Value':>12}  {'Threshold':>12}  {'Result':>8}")
    print("-" * 66)
    print(f"{'Survival rate':<28} {mc_surv['survival_rate']:>12.1%}  {'>=70%':>12}  {fmt_pass(p5_survival_ok):>8}")
    print(f"{'DD p95':<28} {mc_surv['dd_percentiles']['p95']:>12.1f}R {'<=' + str(PROP_CONSTRAINTS.max_drawdown_r * 1.2) + 'R':>12}  {fmt_pass(p5_dd95_ok):>8}")

    print(f"\n  DD Percentiles: {mc_surv['dd_percentiles']}")
    print(f"  Ruin probability: {mc_result.ruin_probability:.1%}")
    print(f"  Actual final PnL: {mc_result.actual_final_pnl:.1f}R")
    print(f"  Actual max DD: {mc_result.actual_max_drawdown:.1f}R")
    print(f"  Final PnL percentiles: {mc_result.final_pnl_percentiles}")

    if "monthly_loss_pass_rate" in mc_surv:
        print(f"  Monthly loss pass rate: {mc_surv['monthly_loss_pass_rate']:.1%}")
    if "annual_r_pass_rate" in mc_surv:
        print(f"  Annual R pass rate: {mc_surv['annual_r_pass_rate']:.1%}")

    p5_passed = p5_survival_ok and p5_dd95_ok

    # Interpret survival rate
    if mc_surv["survival_rate"] >= 0.80:
        survival_interp = "Strong -- deploy with full size"
    elif mc_surv["survival_rate"] >= 0.70:
        survival_interp = "Acceptable -- deploy, monitor closely"
    elif mc_surv["survival_rate"] >= 0.50:
        survival_interp = "Conditional -- reduce size or tighten stops"
    else:
        survival_interp = "No-go -- strategy will likely breach"

    print(f"\n  Interpretation: {survival_interp}")
    print(f"\n  >> PHASE 5: {fmt_pass(p5_passed)}")

    # ==================================================================
    # FINAL VERDICT
    # ==================================================================
    separator("FINAL VERDICT")

    phases = [
        ("Phase 1 (Structural)", p1_passed,
         f"{p1_metrics['total_trades']} trades, {p1_metrics['win_rate']:.1%} WR, PF {p1_metrics['profit_factor']:.2f}"),
        ("Phase 2 (Walk-Forward)", p2_passed,
         f"WF eff {wf_result.walk_forward_efficiency:.2f}, stability {stability.overall_score:.2f} ({stability.interpretation})"),
        ("Phase 3 (Prop Filter)", p3_passed,
         f"DD {cr.max_drawdown_r:.1f}R, worst month {cr.worst_month_r:.1f}R, expectancy {cr.expectancy:.3f}R"),
        ("Phase 4 (Hold-Out)", p4_passed,
         f"Sharpe {holdout_m['sharpe_ratio']:.2f}, PF {holdout_m['profit_factor']:.2f}, {holdout_m['total_r']:+.1f}R"),
        ("Phase 5 (MC Survival)", p5_passed,
         f"{mc_surv['survival_rate']:.0%} survival at {PROP_CONSTRAINTS.max_drawdown_r}R DD"),
    ]

    for name, passed, detail in phases:
        status = "PASS" if passed else "FAIL"
        print(f"  {name + ':':<28} {status:<6} -- {detail}")

    # Determine verdict
    all_phase_1_4 = all(p for _, p, _ in phases[:4])
    phase_5_ok = p5_passed

    if all_phase_1_4 and phase_5_ok:
        verdict = "GO"
        verdict_detail = "All phases pass. Strategy is prop-firm ready."
    elif all_phase_1_4 and mc_surv["survival_rate"] >= 0.50:
        verdict = "CONDITIONAL"
        verdict_detail = "Phases 1-4 pass but MC survival is borderline. Trade with reduced size."
    else:
        verdict = "NO-GO"
        failed = [name for name, passed, _ in phases if not passed]
        verdict_detail = f"Failed: {', '.join(failed)}. Revisit parameters."

    print(f"\n  >> VERDICT: {verdict}")
    print(f"     {verdict_detail}")

    # Mode params summary
    print(f"\n  Recommended params (WF mode): {mode_params}")


if __name__ == "__main__":
    main()
