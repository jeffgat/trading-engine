# Robust Pipeline — Phase Execution Guide

Detailed instructions for each phase. Run from `backtesting/` using `uv run`.

---

## Before Phase 1: Freeze the Hold-Out

**Goal**: Preserve one truly untouched final OOS test.

- Reserve the most recent 12-24 months before any screening or sanity check.
- Exclude this period from Phase 1 and Phase 2 entirely.
- Check `orb_backtest.analysis.holdout_log` before using the hold-out.
- If the period has already been tested multiple times, say the hold-out is contaminated and downgrade the verdict.

This is mandatory. Bailey explicitly warns that repeated hold-out probing turns the hold-out into another in-sample dataset.

---

## Phase 1: Structural Validation

**Goal**: Confirm the candidate config produces a viable trade distribution over the pre-holdout history.

**Data**: Longest available dataset **excluding the reserved hold-out**.

```python
from orb_backtest.data.loader import load_data
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

df = load_data("NQ_5m.csv")
train_df = df.loc[:holdout_start]
trades = run_backtest(train_df, config, start_date="2015-01-01")
m = compute_metrics(trades)
```

**Pass criteria** (all must hold):
- `total_trades >= 100` — enough sample size
- `win_rate >= 0.35` — not catastrophically wrong
- `profit_factor >= 1.0` — positive edge exists

**Important**: This is a viability filter only. Do not tune the strategy from Phase 1 results.

**If fails**: The parameter set is fundamentally broken. Go back to optimization.

---

## Phase 2: Walk-Forward + Parameter Stability

**Goal**: Test if the strategy generalizes across time and if optimal params are stable across rolling regimes.

**Preferred setup**: `12m IS / 3m OOS / 3m step`, rolling, not anchored.

Use `24m / 6m / 3m` or `36m / 12m / 12m` only if the strategy is too sparse for the default. More folds are better evidence.

```python
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability

# Define the params to sweep within each WF fold
param_ranges = {
    "ny_stop_atr_pct": [5, 6, 7, 8, 9, 10],
    "rr": [2.0, 2.5, 3.0, 3.5],
    # ... other params
}

wf_result = run_walkforward(
    df, base_config, param_ranges,
    is_months=12, oos_months=3, step_months=3,
    objective="sharpe", n_workers=8,
    start_date="2015-01-01",
)

# WF efficiency: avg OOS objective / avg IS objective
print(f"WF Efficiency: {wf_result.walk_forward_efficiency:.2f}")

# Parameter stability
stability = analyze_parameter_stability(wf_result, param_ranges)
print(f"Stability: {stability.overall_score:.2f} ({stability.interpretation})")
for p in stability.params:
    print(f"  {p.name}: mode={p.mode}, score={p.stability_score:.2f}, "
          f"range={p.value_range}, unique={p.unique_values}")
```

**Pass criteria**:
- `walk_forward_efficiency >= 0.3-0.5` — OOS retains a meaningful fraction of IS performance
- `stability.overall_score >= 0.4` — params don't wildly shift between folds
- Prefer 20+ folds on long histories; minimum 8 before trusting the result

**Bailey note**: Stability is helpful, but it is not a substitute for PBO or DSR. A stable parameter can still be a false discovery.

**Interpreting stability scores**:
- `>= 0.7` (high): Params converge consistently — strong signal
- `0.4 - 0.7` (moderate): Some drift but core params stable — acceptable
- `< 0.4` (low): Params are regime-dependent — unreliable optimization

**Required write-up**:
- Report combined OOS metrics, not just best-fold metrics
- Report recent-vs-historical fold degradation when available
- State how many parameter combinations were tried per fold and across the whole research effort

### Bailey Diagnostics

If the codebase supports them, compute:

- **PBO / CSCV**: Prefer `PBO <= 0.05`
- **DSR or PSR**: Require the selected Sharpe to remain significant after multiple-testing adjustment

If these diagnostics are unavailable, explicitly say the pipeline is reducing overfitting risk heuristically, but not estimating it directly.

---

## Phase 3: Prop Firm Constraint Filter

**Goal**: Verify the combined WF OOS trade sequence meets prop firm account requirements.

```python
from orb_backtest.optimize.prop_constraints import (
    evaluate_constraints, PropFirmConstraints,
)

constraints = PropFirmConstraints(
    max_drawdown_r=10.0,    # prop firm breach level
    min_annual_r=24.0,      # 2R/month target
    max_monthly_loss_r=5.0, # worst month cap
    min_positive_expectancy=True,
)

cr = evaluate_constraints(wf_result.combined_oos_trades, constraints)

print(f"Overall: {'PASS' if cr.passed else 'FAIL'}")
print(f"  Max DD: {cr.max_drawdown_r:.1f}R  {'PASS' if cr.max_drawdown_passed else 'FAIL'}")
print(f"  Annual R: {cr.annual_r_passed}  values={cr.annual_r_values}")
print(f"  Monthly: worst={cr.worst_month_r:.1f}R  {'PASS' if cr.monthly_loss_passed else 'FAIL'}")
print(f"  Expectancy: {cr.expectancy:.3f}R  {'PASS' if cr.expectancy_passed else 'FAIL'}")
print(f"  Stats: {cr.total_trades} trades, {cr.win_rate:.1%} WR, "
      f"avg win {cr.avg_win_r:.2f}R, avg loss {cr.avg_loss_r:.2f}R")
```

**Pass criteria**: `cr.passed == True` (all constraints met).

**Important**: Phase 3 is a filter on Phase 2 OOS trades. It is not new out-of-sample evidence.

---

## Phase 4: Hold-Out OOS Test

**Goal**: Test on data that was never part of any optimization or walk-forward window.

**Data split**: Reserve the most recent 12-24 months as hold-out. The WF in Phase 2 should NOT extend into this period.

```python
from orb_backtest.analysis.holdout_log import check_holdout_period, log_holdout_test

# Check cleanliness before running
check = check_holdout_period("2025-01-01", "2025-12-31")
print(check.warning or "Hold-out is clean")

# Use the mode params from stability analysis (most frequently selected)
mode_params = {p.name: p.mode for p in stability.params}
holdout_config = base_config.with_overrides(**mode_params)

# Run on hold-out period only
holdout_trades = run_backtest(df, holdout_config, start_date="2025-01-01")
holdout_m = compute_metrics(holdout_trades)

print(f"Hold-out: {holdout_m['total_trades']} trades, "
      f"Sharpe={holdout_m['sharpe_ratio']:.2f}, "
      f"PF={holdout_m['profit_factor']:.2f}, "
      f"Total R={holdout_m['total_r']:.1f}")

log_holdout_test("2025-01-01", "2025-12-31", config=mode_params, experiment_name="robust-pipeline")
```

**Pass criteria**:
- `sharpe_ratio > 0.5` — degraded but still positive
- `profit_factor > 1.0` — still profitable
- `total_r > 0` — net positive over hold-out

**Important**:
- The hold-out period should be at least 6 months with 30+ trades
- If the hold-out was previously tested, say it is no longer truly final OOS
- Do not retune after seeing hold-out results unless you also retire that hold-out

---

## Phase 5: Monte Carlo Survival

**Goal**: Estimate the probability of surviving prop firm DD limits under resampled trade sequences.

```python
from orb_backtest.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig
from orb_backtest.optimize.prop_constraints import evaluate_constraints_mc

# Use WF OOS trades. Prefer block bootstrap to preserve serial dependence.
mc_config = MonteCarloConfig(n_simulations=2000, method="block_bootstrap", seed=42)
mc_result = run_monte_carlo(wf_result.combined_oos_trades, mc_config, ruin_threshold=-10.0)

# Prop constraint survival across MC sims
trade_dates = [t.date for t in wf_result.combined_oos_trades
               if t.exit_type != 0]  # filter no-fills
mc_surv = evaluate_constraints_mc(
    mc_result,
    PropFirmConstraints(max_drawdown_r=10.0),
    trade_dates=trade_dates,
)

print(f"Survival rate: {mc_surv['survival_rate']:.1%}")
print(f"DD percentiles: {mc_surv['dd_percentiles']}")
if 'monthly_loss_pass_rate' in mc_surv:
    print(f"Monthly loss pass rate: {mc_surv['monthly_loss_pass_rate']:.1%}")
if 'annual_r_pass_rate' in mc_surv:
    print(f"Annual R pass rate: {mc_surv['annual_r_pass_rate']:.1%}")
```

**Pass criteria**:
- `survival_rate >= 0.70` — 70%+ of simulated paths survive the real DD limit
- `dd_percentiles.p95 <= max_drawdown_r * 1.2` — 95th percentile DD isn't catastrophic

**Interpreting results**:
- `>= 80%` survival: Strong — deploy with full size
- `70-80%`: Acceptable — deploy, monitor closely
- `50-70%`: Conditional — reduce size or tighten stops
- `< 50%`: No-go — strategy will likely breach

**Important**:
- Use the real prop-firm breach threshold, typically `8R` to `10R`
- Do not set `max_drawdown_r` to a dummy value like `999R` and then call the result "survival"
- Bootstrap and shuffle are sensitivity checks; block bootstrap is the preferred default
- Phase 5 stresses path risk. It does not rescue a weak edge

---

## Final Decision

Collect results from all 5 phases into a summary table:

```
Phase 1 (Structural):    PASS  — 2362 trades, 47.1% WR, PF 1.25
Phase 2 (Walk-Forward):  PASS  — WF eff 0.68, stability 0.62 (moderate)
Phase 3 (Prop Filter):   PASS  — DD -7.2R, annual 28R+, monthly -3.1R worst
Phase 4 (Hold-Out):      PASS  — Sharpe 0.89, PF 1.18, +14.2R
Phase 5 (MC Survival):   PASS  — 78% survival at 10R DD
→ VERDICT: GO
```

Use this decision hierarchy:

- **GO**: All 5 phases pass, hold-out is clean, and Bailey diagnostics support the result
- **CONDITIONAL**: Five phases pass but PBO/DSR are unavailable, or Monte Carlo is borderline
- **NO-GO**: Hold-out contaminated, Phase 1-4 fails, or Bailey diagnostics reject the edge
