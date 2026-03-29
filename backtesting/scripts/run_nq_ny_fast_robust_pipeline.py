#!/usr/bin/env python3
"""NQ NY FAST — 5-Phase Robust Pipeline (Bailey-aware).

FAST execution config NQ_NY leg:
  ORB: 09:30-09:45, entry until 12:00, flat 15:30-16:00
  stop=7.0% ATR-12, min_gap=2.5%, rr=3.5, tp1=0.4
  Long only, Friday excluded

Phases:
  0. Hold-out pre-registration
  1. Structural validation (full pre-holdout history)
  2. Walk-forward (12m IS / 3m OOS / 3m step) + param stability
  3. Prop firm constraint filter (on combined WF OOS trades)
  4. Hold-out OOS (2025-03-01 onward, mode params from WF)
  5. Monte Carlo survival (2000 block_bootstrap sims)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import FRI, apply_dow_filter
from orb_backtest.analysis.holdout_log import check_holdout_period, log_holdout_test
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.optimize.prop_constraints import (
    PropFirmConstraints,
    evaluate_constraints,
    evaluate_constraints_mc,
)
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.simulate.monte_carlo import MonteCarloConfig, run_monte_carlo

# ── Configuration ─────────────────────────────────────────────────────────
WF_START = "2016-01-01"
WF_END_SLICE = "2025-02-28"
HOLDOUT_START = "2025-03-01"
HOLDOUT_END = "2026-02-28"
N_WORKERS = 8
MC_RUIN_THRESHOLD_R = 15.0
MC_SURVIVAL_DD = 15.0
DOW_EXCLUDED = {FRI}

PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=999.0,
    min_annual_r=12.0,
    max_monthly_loss_r=5.0,
    min_positive_expectancy=True,
)

# ── Candidate config (FAST execution NQ_NY) ──────────────────────────────
CANDIDATE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="12:00",
    flat_start="15:30",
    flat_end="16:00",
    stop_atr_pct=7.0,
    min_gap_atr_pct=2.5,
)

CANDIDATE = StrategyConfig(
    sessions=(CANDIDATE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=3.5,
    tp1_ratio=0.4,
    atr_length=12,
    excluded_dates=("20241218",),
    name="NQ NY FAST Robust Pipeline",
)

# ── Walk-forward param ranges (centered on candidate) ────────────────────
PARAM_RANGES = {
    "ny_stop_atr_pct": [5.0, 6.0, 7.0, 8.0, 9.0],
    "rr": [2.5, 3.0, 3.5, 4.0, 4.5],
    "ny_min_gap_atr_pct": [1.5, 2.0, 2.5, 3.0, 3.5],
    "tp1_ratio": [0.3, 0.35, 0.4, 0.45, 0.5],
}

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)


# ── Helpers ───────────────────────────────────────────────────────────────

def fmt(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def section(title: str):
    print(f"\n{'='*70}\n  {title}\n{'='*70}\n", flush=True)


def print_metrics(m, label=""):
    if label:
        print(f"\n  {label}", flush=True)
    print(f"  {'Trades':<24s} {m['total_trades']:>10d}", flush=True)
    print(f"  {'Win Rate':<24s} {m['win_rate']:>9.1%}", flush=True)
    print(f"  {'Profit Factor':<24s} {m['profit_factor']:>10.2f}", flush=True)
    print(f"  {'Net R':<24s} {m['total_r']:>9.1f}R", flush=True)
    print(f"  {'Max DD':<24s} {m['max_drawdown_r']:>9.1f}R", flush=True)
    print(f"  {'Calmar':<24s} {m['calmar_ratio']:>10.2f}", flush=True)
    print(f"  {'Sharpe':<24s} {m['sharpe_ratio']:>10.3f}", flush=True)
    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:", flush=True)
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}", flush=True)


def dow_gate(trades):
    return apply_dow_filter(trades, DOW_EXCLUDED)


def wf_progress(fold_idx, total, status):
    print(f"  [Fold {fold_idx + 1}/{total}] {status}", flush=True)


# ── Phase 0: Hold-Out Pre-Registration ───────────────────────────────────

def phase_0():
    section("PHASE 0: HOLD-OUT PRE-REGISTRATION")
    check = check_holdout_period(HOLDOUT_START, HOLDOUT_END)
    if check.is_clean:
        print(f"  Hold-out {HOLDOUT_START} -> {HOLDOUT_END} is CLEAN (never tested).")
    else:
        print(f"  WARNING: {check.warning}")
        print(f"  Previous tests: {check.previous_test_count}")
    print(f"  Hold-out frozen. Phases 1-2 will NOT touch this period.")
    return check


# ── Phase 1: Structural Validation ───────────────────────────────────────

def phase_1(df, df_1m, df_1s):
    section("PHASE 1: STRUCTURAL VALIDATION")
    print(f"  Running full pre-holdout backtest with 1s magnifier...")
    print(f"  DOW filter: exclude Friday")

    t0 = time.time()
    trades = run_backtest(df, CANDIDATE, start_date=WF_START,
                          df_1m=df_1m, df_1s=df_1s)
    trades = dow_gate(trades)
    m = compute_metrics(trades)
    print(f"  Completed in {time.time() - t0:.1f}s")
    print_metrics(m, "Full pre-holdout metrics")

    checks = {
        "Trades >= 100": (m["total_trades"] >= 100, m["total_trades"], ">=100"),
        "Win rate >= 35%": (m["win_rate"] >= 0.35, f"{m['win_rate']:.1%}", ">=35%"),
        "PF >= 1.0": (m["profit_factor"] >= 1.0, f"{m['profit_factor']:.2f}", ">=1.0"),
        "Max consec losses <= 15": (m["max_consecutive_losses"] <= 15, m["max_consecutive_losses"], "<=15"),
    }

    print(f"\n  {'Check':<28} {'Value':>10}  {'Threshold':>10}  {'Result':>8}")
    print(f"  {'-'*62}")
    all_pass = True
    for name, (passed, val, thresh) in checks.items():
        print(f"  {name:<28} {str(val):>10}  {thresh:>10}  {fmt(passed):>8}")
        if not passed:
            all_pass = False

    print(f"\n  >> PHASE 1: {fmt(all_pass)}")
    return all_pass, trades, m


# ── Phase 2: Walk-Forward + Parameter Stability ─────────────────────────

def phase_2(df, df_1m):
    section("PHASE 2: WALK-FORWARD OPTIMIZATION + STABILITY")
    print(f"  Config: 12m IS / 3m OOS / 3m step (rolling)")
    print(f"  Grid: {GRID_SIZE} combos per fold")
    print(f"  Objective: sharpe")
    print(f"  Magnifier: 1m only (1s too large for multiprocessing)")
    print(f"  DOW filter: exclude Friday")
    print(f"  Params: {list(PARAM_RANGES.keys())}")

    # Slice data to prevent OOS from bleeding into hold-out
    df_wf = df.loc[:WF_END_SLICE]
    df_wf_1m = df_1m.loc[:WF_END_SLICE] if df_1m is not None else None
    print(f"  WF data: {df_wf.index[0].date()} -> {df_wf.index[-1].date()}")

    t0 = time.time()
    wf_result = run_walkforward(
        df_wf, CANDIDATE, PARAM_RANGES,
        is_months=12, oos_months=3, step_months=3,
        anchored=False, objective="sharpe",
        n_workers=N_WORKERS, start_date=WF_START,
        progress_fn=wf_progress,
        df_1m=df_wf_1m,
        gate_fn=dow_gate,
    )
    elapsed = time.time() - t0
    print(f"\n  Walk-forward completed in {elapsed:.0f}s ({len(wf_result.folds)} folds)")

    # Per-fold summary
    print(f"\n  {'Fold':<6} {'IS Period':<24} {'OOS Period':<24} {'IS Shrp':>8} {'OOS Shrp':>9} {'Best Params'}")
    print(f"  {'-'*110}")
    for f in wf_result.folds:
        params_str = ", ".join(f"{k}={v}" for k, v in f.best_params.items())
        print(f"  {f.fold_index + 1:<6}"
              f" {f.is_start} -> {f.is_end:<10}"
              f" {f.oos_start} -> {f.oos_end:<10}"
              f" {f.is_objective_value:>8.3f}"
              f" {f.oos_objective_value:>9.3f}"
              f"  {params_str}")

    # Combined OOS metrics
    oos_m = wf_result.combined_oos_metrics
    print_metrics(oos_m, "Combined OOS metrics")

    # WF efficiency
    wfe_pass = wf_result.walk_forward_efficiency >= 0.5
    folds_pass = len(wf_result.folds) >= 4

    # Stability
    stability = analyze_parameter_stability(wf_result, param_ranges=PARAM_RANGES)
    stab_pass = stability.overall_score >= 0.4

    print(f"\n  Parameter Stability (overall: {stability.overall_score:.3f} — {stability.interpretation}):")
    for p in stability.params:
        print(f"    {p.name:<24}  mode={p.mode:<6}  freq={p.mode_frequency}/{stability.n_folds}"
              f"  score={p.stability_score:.3f}  range=[{p.value_range[0]}, {p.value_range[1]}]")

    print(f"\n  {'Check':<28} {'Value':>10}  {'Threshold':>10}  {'Result':>8}")
    print(f"  {'-'*62}")
    print(f"  {'WF efficiency':<28} {wf_result.walk_forward_efficiency:>10.3f}  {'>=0.50':>10}  {fmt(wfe_pass):>8}")
    print(f"  {'Stability score':<28} {stability.overall_score:>10.3f}  {'>=0.40':>10}  {fmt(stab_pass):>8}")
    print(f"  {'Folds completed':<28} {len(wf_result.folds):>10}  {'>=4':>10}  {fmt(folds_pass):>8}")

    passed = wfe_pass and stab_pass and folds_pass
    print(f"\n  >> PHASE 2: {fmt(passed)}")
    return passed, wf_result, stability


# ── Phase 3: Prop Firm Constraint Filter ─────────────────────────────────

def phase_3(wf_result):
    section("PHASE 3: PROP FIRM CONSTRAINTS (on WF OOS trades)")
    print(f"  Constraints: Annual>={PROP_CONSTRAINTS.min_annual_r}R, "
          f"Monthly<={PROP_CONSTRAINTS.max_monthly_loss_r}R, Expectancy>0")
    print(f"  Note: Max DD is informational only (not gated)")

    cr = evaluate_constraints(wf_result.combined_oos_trades, PROP_CONSTRAINTS)

    print(f"\n  {'Constraint':<28} {'Value':>12}  {'Threshold':>12}  {'Result':>8}")
    print(f"  {'-'*66}")
    print(f"  {'Max drawdown':<28} {cr.max_drawdown_r:>12.1f}R {'(INFO)':>12}  {'INFO':>8}")
    print(f"  {'Worst monthly loss':<28} {cr.worst_month_r:>12.1f}R {'<=' + str(PROP_CONSTRAINTS.max_monthly_loss_r) + 'R':>12}  {fmt(cr.monthly_loss_passed):>8}")
    print(f"  {'Expectancy':<28} {cr.expectancy:>12.3f}R {'> 0':>12}  {fmt(cr.expectancy_passed):>8}")
    print(f"  {'Annual R (full years)':<28} {'':>12}  {'>=' + str(PROP_CONSTRAINTS.min_annual_r) + 'R':>12}  {fmt(cr.annual_r_passed):>8}")

    if cr.annual_r_values:
        print(f"\n  Annual R by year (OOS):")
        for y, r in sorted(cr.annual_r_values.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")

    print(f"\n  Stats: {cr.total_trades} trades, {cr.win_rate:.1%} WR, "
          f"avg win {cr.avg_win_r:.2f}R, avg loss {cr.avg_loss_r:.2f}R, "
          f"max consec losses {cr.max_consecutive_losses}")

    worst_months = sorted(cr.monthly_r_values.items(), key=lambda x: x[1])[:5]
    print(f"  Worst 5 months:")
    for m_key, r in worst_months:
        print(f"    {m_key}: {r:>8.1f}R")

    passed = cr.monthly_loss_passed and cr.expectancy_passed and cr.annual_r_passed
    print(f"\n  >> PHASE 3: {fmt(passed)}")
    return passed, cr


# ── Phase 4: Hold-Out OOS Test ───────────────────────────────────────────

def phase_4(df, df_1m, df_1s, stability):
    section("PHASE 4: HOLD-OUT OOS TEST")

    # Use mode params from stability analysis
    mode_params = {p.name: p.mode for p in stability.params}
    holdout_config = with_overrides(CANDIDATE, **mode_params)

    print(f"  Hold-out: {HOLDOUT_START} -> present")
    print(f"  Mode params from WF: {mode_params}")

    t0 = time.time()
    trades = run_backtest(df, holdout_config, start_date=HOLDOUT_START,
                          df_1m=df_1m, df_1s=df_1s)
    trades = dow_gate(trades)
    m = compute_metrics(trades)
    print(f"  Completed in {time.time() - t0:.1f}s")
    print_metrics(m, "Hold-out OOS metrics")

    # Log hold-out usage
    entry = log_holdout_test(
        HOLDOUT_START, HOLDOUT_END,
        config=mode_params,
        experiment_name="FAST NQ_NY robust pipeline",
    )
    if entry.warning:
        print(f"\n  HOLDOUT WARNING: {entry.warning}")
    print(f"  Hold-out test #{entry.test_count} logged.")

    p4_sharpe = m["sharpe_ratio"] > 0.5
    p4_pf = m["profit_factor"] > 1.0
    p4_r = m["total_r"] > 0
    passed = p4_sharpe and p4_pf and p4_r

    print(f"\n  {'Check':<28} {'Value':>10}  {'Threshold':>10}  {'Result':>8}")
    print(f"  {'-'*62}")
    print(f"  {'Sharpe ratio':<28} {m['sharpe_ratio']:>10.2f}  {'>0.50':>10}  {fmt(p4_sharpe):>8}")
    print(f"  {'Profit factor':<28} {m['profit_factor']:>10.2f}  {'>1.0':>10}  {fmt(p4_pf):>8}")
    print(f"  {'Total R':<28} {m['total_r']:>10.1f}  {'>0':>10}  {fmt(p4_r):>8}")

    print(f"\n  >> PHASE 4: {fmt(passed)}")
    return passed, trades, m


# ── Phase 5: Monte Carlo Survival ────────────────────────────────────────

def phase_5(wf_result):
    section("PHASE 5: MONTE CARLO SURVIVAL")
    print(f"  Method: block_bootstrap (preserves serial correlation)")
    print(f"  Simulations: 2000")
    print(f"  Ruin threshold: {MC_RUIN_THRESHOLD_R}R")

    mc_config = MonteCarloConfig(
        n_simulations=2000,
        method="block_bootstrap",
        seed=42,
    )

    t0 = time.time()
    mc_result = run_monte_carlo(
        wf_result.combined_oos_trades,
        mc_config,
        ruin_threshold=-MC_RUIN_THRESHOLD_R,
    )
    print(f"  Completed in {time.time() - t0:.1f}s")

    # Prop constraint survival
    trade_dates = [t.date for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_constraints = PropFirmConstraints(
        max_drawdown_r=MC_SURVIVAL_DD,
        min_annual_r=12.0,
        max_monthly_loss_r=5.0,
    )
    mc_surv = evaluate_constraints_mc(mc_result, mc_constraints, trade_dates=trade_dates)

    survival_ok = mc_surv["survival_rate"] >= 0.70
    ruin_ok = mc_result.ruin_probability < 0.05

    print(f"\n  Actual: PnL={mc_result.actual_final_pnl:.1f}R, "
          f"DD={mc_result.actual_max_drawdown:.1f}R, Sharpe={mc_result.actual_sharpe:.3f}")
    print(f"\n  PnL percentiles:   {mc_result.final_pnl_percentiles}")
    print(f"  DD percentiles:    {mc_surv['dd_percentiles']}")
    print(f"  Sharpe percentiles: {mc_result.sharpe_percentiles}")

    if "monthly_loss_pass_rate" in mc_surv:
        print(f"  Monthly loss pass rate: {mc_surv['monthly_loss_pass_rate']:.1%}")
    if "annual_r_pass_rate" in mc_surv:
        print(f"  Annual R pass rate: {mc_surv['annual_r_pass_rate']:.1%}")

    print(f"\n  {'Check':<28} {'Value':>12}  {'Threshold':>12}  {'Result':>8}")
    print(f"  {'-'*66}")
    print(f"  {'Survival at ' + str(MC_SURVIVAL_DD) + 'R':<28} {mc_surv['survival_rate']:>12.1%}  {'>=70%':>12}  {fmt(survival_ok):>8}")
    print(f"  {'Ruin at ' + str(MC_RUIN_THRESHOLD_R) + 'R':<28} {mc_result.ruin_probability:>12.1%}  {'<5%':>12}  {fmt(ruin_ok):>8}")

    sr = mc_surv["survival_rate"]
    if sr >= 0.80:
        interp = "Strong -- deploy with full size"
    elif sr >= 0.70:
        interp = "Acceptable -- deploy, monitor closely"
    elif sr >= 0.50:
        interp = "Conditional -- reduce size or tighten stops"
    else:
        interp = "No-go -- strategy will likely breach"
    print(f"\n  Interpretation: {interp}")

    passed = survival_ok and ruin_ok
    print(f"\n  >> PHASE 5: {fmt(passed)}")
    return passed, mc_result, mc_surv


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    t_global = time.time()

    # Phase 0
    holdout_check = phase_0()

    # Load data
    section("LOADING DATA")
    t0 = time.time()
    df_5m = load_5m_data(NQ.data_file)
    df_1m = load_1m_for_5m(NQ.data_file)
    try:
        df_1s = load_1s_for_5m(NQ.data_file)
    except FileNotFoundError:
        df_1s = None
        print("  1s data not found — using 1m magnifier for Phase 1/4")
    print(f"  5m: {len(df_5m):,} bars, 1m: {len(df_1m):,} bars"
          f"{f', 1s: {len(df_1s):,} bars' if df_1s is not None else ''}")
    print(f"  Range: {df_5m.index[0].date()} -> {df_5m.index[-1].date()}")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    # Slice pre-holdout data for Phase 1
    df_pre = df_5m.loc[:WF_END_SLICE]
    df_pre_1m = df_1m.loc[:WF_END_SLICE] if df_1m is not None else None
    df_pre_1s = df_1s.loc[:WF_END_SLICE] if df_1s is not None else None

    print(f"\n  Candidate: stop={CANDIDATE_SESSION.stop_atr_pct}% rr={CANDIDATE.rr} "
          f"gap={CANDIDATE_SESSION.min_gap_atr_pct}% tp1={CANDIDATE.tp1_ratio}")
    print(f"  Structural: ORB 15m, entry<12:00, flat 15:30, ATR={CANDIDATE.atr_length}, "
          f"dir={CANDIDATE.direction_filter}, DOW excl Fri")

    results = {}

    # Phase 1
    p1_pass, p1_trades, p1_m = phase_1(df_pre, df_pre_1m, df_pre_1s)
    results["Phase 1: Structural"] = p1_pass
    if not p1_pass:
        print("\n  WARNING: Phase 1 failed. Continuing pipeline anyway.")

    # Phase 2
    p2_pass, wf_result, stability = phase_2(df_5m, df_1m)
    results["Phase 2: Walk-Forward"] = p2_pass

    # Phase 3
    p3_pass, cr = phase_3(wf_result)
    results["Phase 3: Prop Constraints"] = p3_pass

    # Phase 4
    p4_pass, p4_trades, p4_m = phase_4(df_5m, df_1m, df_1s, stability)
    results["Phase 4: Hold-Out OOS"] = p4_pass

    # Phase 5
    p5_pass, mc_result, mc_surv = phase_5(wf_result)
    results["Phase 5: Monte Carlo"] = p5_pass

    # ── Final Verdict ─────────────────────────────────────────────────
    section("FINAL VERDICT")

    n_folds = len(wf_result.folds)
    total_trials = GRID_SIZE * n_folds

    print(f"  Candidate: stop={CANDIDATE_SESSION.stop_atr_pct}% rr={CANDIDATE.rr} "
          f"gap={CANDIDATE_SESSION.min_gap_atr_pct}% tp1={CANDIDATE.tp1_ratio}")
    print(f"  Mode params: {', '.join(f'{p.name}={p.mode}' for p in stability.params)}")
    print()

    all_pass = True
    for phase, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {phase}")
        if not passed:
            all_pass = False

    # Determine verdict
    phases_1_4 = all(v for k, v in results.items() if "Monte Carlo" not in k)
    sr = mc_surv["survival_rate"]

    if phases_1_4 and p5_pass:
        verdict = "GO"
        detail = "All phases pass. Strategy is prop-firm ready (heuristic verdict)."
    elif phases_1_4 and sr >= 0.50:
        verdict = "CONDITIONAL"
        detail = "Phases 1-4 pass but MC survival is borderline. Trade reduced size."
    else:
        failed = [k for k, v in results.items() if not v]
        verdict = "NO-GO"
        detail = f"Failed: {', '.join(failed)}. Revisit parameters."

    print(f"\n  >> VERDICT: {verdict}")
    print(f"     {detail}")

    # Bailey posture
    print(f"\n  METHODOLOGY NOTE (Bailey-style posture):")
    print(f"  {'-'*50}")
    print(f"  Total trials: {total_trials:,} ({GRID_SIZE} combos x {n_folds} folds)")
    print(f"  PBO (Probability of Backtest Overfitting):           NOT IMPLEMENTED")
    print(f"  CSCV (Combinatorially Symmetric Cross-Validation):   NOT IMPLEMENTED")
    print(f"  DSR (Deflated Sharpe Ratio):                         NOT IMPLEMENTED")
    print(f"  PSR (Probabilistic Sharpe Ratio):                    NOT IMPLEMENTED")
    print()
    print(f"  Without these diagnostics, this pipeline reduces overfitting risk")
    print(f"  heuristically (via walk-forward, stability, and block bootstrap MC)")
    print(f"  but does NOT estimate it directly. The verdict is HEURISTIC, not")
    print(f"  statistically deflated.")
    print()
    print(f"  Phase 3 (Prop Filter) and Phase 5 (MC) operate on the same combined")
    print(f"  OOS trade set from Phase 2. They are stress tests, NOT independent")
    print(f"  evidence of out-of-sample robustness.")

    if not holdout_check.is_clean:
        print(f"\n  HOLD-OUT CONTAMINATION: {holdout_check.warning}")

    elapsed = time.time() - t_global
    print(f"\n  Total pipeline time: {elapsed:.0f}s ({elapsed / 60:.1f} min)")


if __name__ == "__main__":
    main()
