# Robust Pipeline — Phase Execution Guide

Detailed instructions for each phase. All code runs from `python/` using `uv run`.

---

## Phase 1: Structural Validation

**Goal**: Confirm the candidate config produces a viable trade distribution over the full available history.

**Data**: Longest available dataset (e.g., NQ 2015-2026).

```python
from orb_backtest.data.loader import load_data
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

df = load_data("NQ_5m.csv")
trades = run_backtest(df, config, start_date="2015-01-01")
m = compute_metrics(trades)
```

**Pass criteria** (all must hold):
- `total_trades >= 100` — enough sample size
- `win_rate >= 0.35` — not catastrophically wrong
- `profit_factor >= 1.0` — positive edge exists
- `max_consecutive_losses <= 15` — no extreme loss streaks

**If fails**: The parameter set is fundamentally broken. Go back to optimization.

---

## Phase 2: Walk-Forward + Parameter Stability

**Goal**: Test if the strategy generalizes across time and if optimal params are stable.

**Setup**: 36-month IS, 12-month OOS, 12-month step (rolling, not anchored).

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
    is_months=36, oos_months=12, step_months=12,
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
- `walk_forward_efficiency >= 0.5` — OOS retains at least half of IS performance
- `stability.overall_score >= 0.4` — params don't wildly shift between folds
- At least 4 folds completed (enough data coverage)

**Interpreting stability scores**:
- `>= 0.7` (high): Params converge consistently — strong signal
- `0.4 - 0.7` (moderate): Some drift but core params stable — acceptable
- `< 0.4` (low): Params are regime-dependent — unreliable optimization

---

## Phase 3: Prop Firm Constraint Filter

**Goal**: Verify the WF OOS trade sequence meets prop firm account requirements.

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

**Adjusting thresholds**:
- If DD is 10.5R but everything else passes, consider `max_drawdown_r=11.0` with a note
- Annual R threshold can be lowered for commodities with fewer trading days
- Monthly loss is the strictest — a single -6R month fails the check

---

## Phase 4: Hold-Out OOS Test

**Goal**: Test on data that was never part of any optimization or walk-forward window.

**Data split**: Reserve the most recent 12-24 months as hold-out. The WF in Phase 2 should NOT extend into this period.

```python
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
```

**Pass criteria**:
- `sharpe_ratio > 0.5` — degraded but still positive
- `profit_factor > 1.0` — still profitable
- `total_r > 0` — net positive over hold-out

**Important**: The hold-out period should be at least 6 months with 30+ trades. Short hold-outs are noisy.

---

## Phase 5: Monte Carlo Survival

**Goal**: Estimate the probability of surviving prop firm DD limits under resampled trade sequences.

```python
from orb_backtest.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig
from orb_backtest.optimize.prop_constraints import evaluate_constraints_mc

# Use WF OOS trades (Phase 2) or hold-out trades (Phase 4)
mc_config = MonteCarloConfig(n_simulations=2000, method="bootstrap", seed=42)
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
- `survival_rate >= 0.70` — 70%+ of simulated paths survive the DD limit
- `dd_percentiles.p95 <= max_drawdown_r * 1.2` — 95th percentile DD isn't catastrophic

**Interpreting results**:
- `>= 80%` survival: Strong — deploy with full size
- `70-80%`: Acceptable — deploy, monitor closely
- `50-70%`: Conditional — reduce size or tighten stops
- `< 50%`: No-go — strategy will likely breach

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

If any phase fails, the verdict is NO-GO unless it's a borderline Phase 5 (50-70%), which earns CONDITIONAL.
