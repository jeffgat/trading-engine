#!/usr/bin/env python3
"""GC NY Continuation Longs — 5-Phase Robust Pipeline (R12 anchor).

Anchor from R12 variable sweep convergence (with Friday exclusion):
  stop=4.5%, rr=9.0, tp1=0.35, ATR=7, gap=3.0%, max_gap_atr=30%
  ICF=True, 8m ORB (09:30-09:38), entry→12:00, flat 13:30
  Long-only, FOMC excluded, Friday excluded (post-backtest filter)

In-sample: Calmar 16.11, 622 trades, DD -12.4R, 0 neg years.

Pipeline phases:
  1. Structural validation — full-history metrics check
  2. Walk-forward (36m IS / 12m OOS / 12m step) + param stability
  3. Prop constraint filter on WF OOS trades (DD is INFO only)
  4. Hold-out OOS — 2025+ data never used in optimization
  5. Monte Carlo survival — 1000 bootstrap sims, ruin at -25R
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import GC
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.prop_constraints import (
    PropFirmConstraints,
    evaluate_constraints,
    evaluate_constraints_mc,
)
from orb_backtest.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig
from orb_backtest.analysis.gates import apply_dow_filter, FRI

# -- Config ----------------------------------------------------------------

START_DATE = "2016-01-01"
HOLDOUT_START = "2025-01-01"  # Never optimized on this data
FULL_YEARS = [str(y) for y in range(2016, 2026)]
DOW_EXCLUDED = {FRI}

GC_NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:38",       # 8m ORB
    entry_start="09:38",
    entry_end="12:00",
    flat_start="13:30",
    flat_end="16:00",
    stop_atr_pct=4.5,
    min_gap_atr_pct=3.0,
)

ANCHOR = StrategyConfig(
    rr=9.0,
    tp1_ratio=0.35,
    risk_usd=5000.0,
    atr_length=7,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY_SESSION,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    impulse_close_filter=True,
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=FOMC_DATES,
)

# -- Walk-forward param ranges (tight grid around anchor) ----------------------

PARAM_RANGES = {
    "ny_stop_atr_pct": [4.0, 4.5, 5.0],
    "rr": [8.0, 9.0, 10.0],
    "ny_min_gap_atr_pct": [2.5, 3.0, 3.5],
    "tp1_ratio": [0.30, 0.35, 0.40],
}
# 3 x 3 x 3 x 3 = 81 combos per fold

# -- Helpers -------------------------------------------------------------------


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def section(title):
    print(flush=True)
    print("=" * 70, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 70, flush=True)


def print_metrics(m, label=""):
    if label:
        print(f"\n  {label}", flush=True)
    print(f"  {'Trades':<24s} {m['total_trades']:>10d}", flush=True)
    print(f"  {'Win Rate':<24s} {m['win_rate']:>9.1%}", flush=True)
    print(f"  {'Profit Factor':<24s} {m['profit_factor']:>10.2f}", flush=True)
    print(f"  {'Net R':<24s} {m['total_r']:>9.1f}R", flush=True)
    print(f"  {'R/yr':<24s} {r_per_year(m):>9.1f}R", flush=True)
    print(f"  {'Max DD':<24s} {m['max_drawdown_r']:>9.1f}R", flush=True)
    print(f"  {'Calmar':<24s} {m['calmar_ratio']:>10.2f}", flush=True)
    print(f"  {'Sharpe':<24s} {m['sharpe_ratio']:>10.3f}", flush=True)
    print(f"  {'Neg full years':<24s} {neg_years(m):>10d}", flush=True)
    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:", flush=True)
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}", flush=True)


def wf_progress(fold_idx, total, status):
    print(f"  [Fold {fold_idx + 1}/{total}] {status}", flush=True)


# -- Phase 1: Structural Validation -------------------------------------------

def phase_1(df, df_1m, df_1s):
    section("PHASE 1: STRUCTURAL VALIDATION")
    print("  Running full-history backtest on anchor config...", flush=True)
    print("  DOW filter: exclude Friday (applied post-backtest)", flush=True)

    t0 = time.time()
    trades = run_backtest(df, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCLUDED)
    m = compute_metrics(trades)
    elapsed = time.time() - t0

    print_metrics(m, f"Full-history metrics ({elapsed:.1f}s)")

    # Checks
    checks = {
        "Trades > 100": m["total_trades"] > 100,
        "Win rate > 30%": m["win_rate"] > 0.30,
        "PF > 1.0": m["profit_factor"] > 1.0,
        "Sharpe > 0.5": m["sharpe_ratio"] > 0.5,
        "Calmar > 1.0": m["calmar_ratio"] > 1.0,
    }

    print(f"\n  Structural checks:", flush=True)
    all_pass = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] {name}", flush=True)
        if not passed:
            all_pass = False

    verdict = "PASS" if all_pass else "FAIL"
    print(f"\n  Phase 1 verdict: {verdict}", flush=True)
    return all_pass, trades, m


# -- Phase 2: Walk-Forward + Stability ----------------------------------------

def phase_2(df, df_1m, df_1s):
    section("PHASE 2: WALK-FORWARD + PARAMETER STABILITY")
    # NOTE: WF uses 1m magnifier only (not 1s). The 1s maps are too large
    # and serializing them for multiprocessing workers is prohibitively slow.
    # 1m fill precision is sufficient for parameter stability analysis.

    n_combos = 1
    for v in PARAM_RANGES.values():
        n_combos *= len(v)
    print(f"  Config: 36m IS / 12m OOS / 12m step", flush=True)
    print(f"  Grid: {n_combos} combos per fold", flush=True)
    print(f"  Objective: sharpe", flush=True)
    print(f"  Magnifier: 1m (1s too large for multiprocessing serialization)", flush=True)
    print(f"  DOW filter: exclude Friday (applied post-backtest in WF)", flush=True)
    print(f"  Params: {list(PARAM_RANGES.keys())}", flush=True)
    print(flush=True)

    dow_gate = lambda trades: apply_dow_filter(trades, DOW_EXCLUDED)

    t0 = time.time()
    wf_result = run_walkforward(
        df,
        ANCHOR,
        param_ranges=PARAM_RANGES,
        is_months=36,
        oos_months=12,
        step_months=12,
        anchored=False,
        objective="sharpe",
        start_date=START_DATE,
        progress_fn=wf_progress,
        df_1m=df_1m,
        gate_fn=dow_gate,
    )
    elapsed = time.time() - t0
    print(f"\n  Walk-forward completed in {elapsed:.0f}s", flush=True)

    # Per-fold summary
    print(f"\n  {'Fold':<6s} {'IS Period':<24s} {'OOS Period':<24s} {'IS Shrp':>8s} {'OOS Shrp':>9s} {'Best Params'}", flush=True)
    print(f"  {'-' * 110}", flush=True)
    for f in wf_result.folds:
        params_str = ", ".join(f"{k}={v}" for k, v in f.best_params.items())
        print(
            f"  {f.fold_index + 1:<6d}"
            f" {f.is_start} -> {f.is_end:<10s}"
            f" {f.oos_start} -> {f.oos_end:<10s}"
            f" {f.is_objective_value:>8.3f}"
            f" {f.oos_objective_value:>9.3f}"
            f"  {params_str}",
            flush=True,
        )

    # Combined OOS metrics
    oos_m = wf_result.combined_oos_metrics
    print_metrics(oos_m, "Combined OOS metrics")

    # WF efficiency
    print(f"\n  WF Efficiency: {wf_result.walk_forward_efficiency:.3f}", flush=True)
    wfe_pass = wf_result.walk_forward_efficiency > 0.5
    print(f"    [{'PASS' if wfe_pass else 'FAIL'}] WF efficiency > 0.5", flush=True)

    # Parameter stability
    stability = analyze_parameter_stability(wf_result, param_ranges=PARAM_RANGES)
    print(f"\n  Parameter Stability:", flush=True)
    print(f"    Overall: {stability.overall_score:.3f} ({stability.interpretation})", flush=True)
    for p in stability.params:
        print(
            f"    {p.name:<24s}  mode={p.mode:<6}  freq={p.mode_frequency}/{stability.n_folds}"
            f"  score={p.stability_score:.3f}  range=[{p.value_range[0]}, {p.value_range[1]}]",
            flush=True,
        )

    stab_pass = stability.overall_score >= 0.4
    print(f"    [{'PASS' if stab_pass else 'FAIL'}] Stability >= 0.4", flush=True)

    verdict = "PASS" if (wfe_pass and stab_pass) else "FAIL"
    print(f"\n  Phase 2 verdict: {verdict}", flush=True)
    return wfe_pass and stab_pass, wf_result, stability


# -- Phase 3: Prop Constraint Filter -------------------------------------------

def phase_3(wf_result):
    section("PHASE 3: PROP FIRM CONSTRAINTS (on WF OOS trades)")

    constraints = PropFirmConstraints(
        max_drawdown_r=999.0,    # DD is NOT a hard filter (user preference)
        min_annual_r=12.0,
        max_monthly_loss_r=5.0,
        min_positive_expectancy=True,
    )
    print(f"  Constraints:", flush=True)
    print(f"    max_drawdown_r:  {constraints.max_drawdown_r} (INFO only — disabled as gate)", flush=True)
    print(f"    min_annual_r:    {constraints.min_annual_r}R", flush=True)
    print(f"    max_monthly_loss_r: {constraints.max_monthly_loss_r}R", flush=True)
    print(f"    min_positive_expectancy: {constraints.min_positive_expectancy}", flush=True)

    cr = evaluate_constraints(wf_result.combined_oos_trades, constraints)

    print(f"\n  Results:", flush=True)
    print(f"    Total trades:    {cr.total_trades}", flush=True)
    print(f"    Total R:         {cr.total_r:.1f}R", flush=True)
    print(f"    Win Rate:        {cr.win_rate:.1%}", flush=True)
    print(f"    Expectancy:      {cr.expectancy:.3f}R", flush=True)
    print(f"    Max DD:          {cr.max_drawdown_r:.1f}R", flush=True)
    print(f"    Worst month:     {cr.worst_month_r:.1f}R", flush=True)
    print(f"    Max consec loss: {cr.max_consecutive_losses}", flush=True)

    print(f"\n  Constraint checks:", flush=True)
    print(f"    [INFO ] Max DD: {cr.max_drawdown_r:.1f}R (not gated)", flush=True)

    if cr.annual_r_values:
        print(f"\n    Annual R by year (OOS):", flush=True)
        for y, r in sorted(cr.annual_r_values.items()):
            flag = " <--" if r < 0 else ""
            print(f"      {y}: {r:>8.1f}R{flag}", flush=True)

    print(f"    [{'PASS' if cr.annual_r_passed else 'FAIL'}] Avg annual R >= {constraints.min_annual_r}R", flush=True)
    print(f"    [{'PASS' if cr.monthly_loss_passed else 'FAIL'}] Worst month <= {constraints.max_monthly_loss_r}R", flush=True)
    print(f"    [{'PASS' if cr.expectancy_passed else 'FAIL'}] Positive expectancy", flush=True)

    # Overall (ignoring DD since it's info-only)
    non_dd_passed = cr.annual_r_passed and cr.monthly_loss_passed and cr.expectancy_passed
    verdict = "PASS" if non_dd_passed else "FAIL"
    print(f"\n  Phase 3 verdict: {verdict}", flush=True)
    return non_dd_passed, cr


# -- Phase 4: Hold-Out OOS Test ------------------------------------------------

def phase_4(df, df_1m, df_1s):
    section("PHASE 4: HOLD-OUT OOS TEST (2025+)")
    print(f"  Hold-out start: {HOLDOUT_START}", flush=True)
    print(f"  This data was NEVER used during optimization.", flush=True)
    print(f"  DOW filter: exclude Friday", flush=True)

    t0 = time.time()
    trades = run_backtest(df, ANCHOR, start_date=HOLDOUT_START, df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCLUDED)
    m = compute_metrics(trades)
    elapsed = time.time() - t0

    print_metrics(m, f"Hold-out OOS metrics ({elapsed:.1f}s)")

    checks = {
        "Sharpe > 0.5": m["sharpe_ratio"] > 0.5,
        "PF > 1.0": m["profit_factor"] > 1.0,
        "Total R > 0": m["total_r"] > 0,
    }

    print(f"\n  Hold-out checks:", flush=True)
    all_pass = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] {name}", flush=True)
        if not passed:
            all_pass = False

    verdict = "PASS" if all_pass else "FAIL"
    print(f"\n  Phase 4 verdict: {verdict}", flush=True)
    return all_pass, trades, m


# -- Phase 5: Monte Carlo Survival --------------------------------------------

def phase_5(full_trades):
    section("PHASE 5: MONTE CARLO SURVIVAL")

    mc_config = MonteCarloConfig(
        n_simulations=1000,
        method="bootstrap",
        seed=42,
    )
    ruin_threshold = -25.0

    print(f"  Method:      {mc_config.method}", flush=True)
    print(f"  Simulations: {mc_config.n_simulations}", flush=True)
    print(f"  Ruin at:     {ruin_threshold}R", flush=True)
    print(f"  Trades in:   {len(full_trades)}", flush=True)

    t0 = time.time()
    mc_result = run_monte_carlo(full_trades, mc_config, ruin_threshold=ruin_threshold)
    elapsed = time.time() - t0

    print(f"\n  Monte Carlo completed in {elapsed:.1f}s", flush=True)

    print(f"\n  Actual performance:", flush=True)
    print(f"    Final PnL:    {mc_result.actual_final_pnl:.1f}R", flush=True)
    print(f"    Max DD:       {mc_result.actual_max_drawdown:.1f}R", flush=True)
    print(f"    Sharpe:       {mc_result.actual_sharpe:.3f}", flush=True)

    print(f"\n  MC percentiles — Final PnL (R):", flush=True)
    for k, v in mc_result.final_pnl_percentiles.items():
        print(f"    {k}: {v:>8.1f}R", flush=True)

    print(f"\n  MC percentiles — Max DD (R):", flush=True)
    for k, v in mc_result.max_dd_percentiles.items():
        print(f"    {k}: {v:>8.1f}R", flush=True)

    print(f"\n  MC percentiles — Sharpe:", flush=True)
    for k, v in mc_result.sharpe_percentiles.items():
        print(f"    {k}: {v:>8.3f}", flush=True)

    ruin_prob = mc_result.ruin_probability
    survival = 1.0 - ruin_prob
    print(f"\n  Ruin probability: {ruin_prob:.1%} (threshold: {ruin_threshold}R)", flush=True)
    print(f"  Survival rate:    {survival:.1%}", flush=True)

    # Also run prop-constraint MC evaluation
    constraints = PropFirmConstraints(max_drawdown_r=999.0, min_annual_r=12.0, max_monthly_loss_r=5.0)
    trade_dates = [t.date for t in full_trades if t.exit_type != EXIT_NO_FILL]
    mc_eval = evaluate_constraints_mc(mc_result, constraints, trade_dates=trade_dates)
    print(f"\n  MC prop constraint eval:", flush=True)
    print(f"    DD survival:         {mc_eval['survival_rate']:.1%} (threshold: {mc_eval['dd_threshold']}R — INFO)", flush=True)
    print(f"    DD p50:              {mc_eval['dd_percentiles']['p50']:.1f}R", flush=True)
    print(f"    DD p95:              {mc_eval['dd_percentiles']['p95']:.1f}R", flush=True)
    if "monthly_loss_pass_rate" in mc_eval:
        print(f"    Monthly loss pass:   {mc_eval['monthly_loss_pass_rate']:.1%}", flush=True)
    if "annual_r_pass_rate" in mc_eval:
        print(f"    Annual R pass:       {mc_eval['annual_r_pass_rate']:.1%}", flush=True)

    surv_pass = survival >= 0.70
    print(f"\n    [{'PASS' if surv_pass else 'FAIL'}] Survival >= 70% at {ruin_threshold}R ruin", flush=True)

    verdict = "PASS" if surv_pass else "FAIL"
    print(f"\n  Phase 5 verdict: {verdict}", flush=True)
    return surv_pass, mc_result


# -- Main ----------------------------------------------------------------------

if __name__ == "__main__":
    print(flush=True)
    print("=" * 70, flush=True)
    print("  GC NY CONTINUATION LONGS — 5-PHASE ROBUST PIPELINE (R12)", flush=True)
    print("  Anchor: stop=4.5% | rr=9.0 | gap=3.0% | tp1=0.35 | ATR=7", flush=True)
    print("  Structural: ORB 8m | flat 13:30 | max_gap=30%ATR", flush=True)
    print("  Long only | DOW excl Fri | ICF on | FOMC excl | 1s mag", flush=True)
    print("=" * 70, flush=True)

    # Load data
    print("\nLoading data...", flush=True)
    t_load = time.time()
    df = load_5m_data(GC.data_file)
    df_1m = load_1m_for_5m(GC.data_file)
    df_1s = load_1s_for_5m(GC.data_file)
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})", flush=True)
    if df_1m is not None:
        print(f"  1m: {len(df_1m):,} bars", flush=True)
    if df_1s is not None:
        print(f"  1s: {len(df_1s):,} bars", flush=True)
    else:
        print("  1s: NOT FOUND", flush=True)
    print(f"  Loaded in {time.time() - t_load:.1f}s", flush=True)

    t_start = time.time()
    results = {}

    # Phase 1
    p1_pass, full_trades, full_metrics = phase_1(df, df_1m, df_1s)
    results["Phase 1: Structural"] = p1_pass

    if not p1_pass:
        print("\n  WARNING: Phase 1 failed. Continuing pipeline anyway.", flush=True)

    # Phase 2
    p2_pass, wf_result, stability = phase_2(df, df_1m, df_1s)
    results["Phase 2: Walk-Forward"] = p2_pass

    # Phase 3
    p3_pass, constraint_result = phase_3(wf_result)
    results["Phase 3: Prop Constraints"] = p3_pass

    # Phase 4
    p4_pass, holdout_trades, holdout_metrics = phase_4(df, df_1m, df_1s)
    results["Phase 4: Hold-Out OOS"] = p4_pass

    # Phase 5
    p5_pass, mc_result = phase_5(full_trades)
    results["Phase 5: Monte Carlo"] = p5_pass

    total_elapsed = time.time() - t_start

    # -- Final Summary --
    section("FINAL PIPELINE SUMMARY")
    print(f"  Anchor: stop=4.5% | rr=9.0 | gap=3.0% | tp1=0.35 | ATR=7", flush=True)
    print(f"  Structural: ORB 8m | flat 13:30 | max_gap=30%ATR", flush=True)
    print(f"  Long only | DOW excl Fri | ICF on | FOMC excl | 1s mag", flush=True)
    print(flush=True)

    all_pass = True
    for phase, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {phase}", flush=True)
        if not passed:
            all_pass = False

    print(flush=True)
    if all_pass:
        print("  VERDICT: GO — All phases passed. Strategy is prop-firm ready.", flush=True)
    else:
        failed = [p for p, v in results.items() if not v]
        n_passed = sum(1 for v in results.values() if v)
        if n_passed >= 4:
            print(f"  VERDICT: CONDITIONAL — {n_passed}/5 passed. Failed: {', '.join(failed)}", flush=True)
        else:
            print(f"  VERDICT: NO-GO — {n_passed}/5 passed. Failed: {', '.join(failed)}", flush=True)

    print(f"\n  Total pipeline time: {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)", flush=True)
    print(flush=True)
