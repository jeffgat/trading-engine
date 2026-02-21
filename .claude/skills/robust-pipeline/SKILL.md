---
name: robust-pipeline
description: >
  Five-phase validation pipeline for prop firm readiness. Evaluates strategy robustness through
  structural validation, rolling walk-forward with parameter stability analysis, prop firm constraint
  filtering, hold-out OOS testing, and Monte Carlo survival simulation. Use when the user says
  "robust pipeline", "prop firm validation", "validate strategy", "is this strategy ready",
  "prop firm readiness", "survival analysis", "stability check", "hold-out test", or asks whether
  a parameter set is robust enough to trade live. Differentiates from strategy-optimizer (single
  optimization tasks) and multi-phase-backtest (optimization rounds) by focusing on validation
  and go/no-go decisions.
---

# Robust Pipeline

Five-phase validation pipeline that answers: **"Is this parameter set robust enough to trade on a prop firm account?"**

## When to Use

- Validating a parameter set before going live
- Running a full prop firm readiness check
- Testing if optimized params survive walk-forward + Monte Carlo
- Comparing multiple candidate configs through a standardized pipeline
- After multi-phase-backtest produces candidates — this skill filters them

## Do NOT Use When

- Running a single backtest (use `orb-backtester`)
- Optimizing parameters (use `strategy-optimizer` or `multi-phase-backtest`)
- Doing exploratory sweeps without a specific candidate to validate

## Key Files

| Module | Path | Purpose |
|--------|------|---------|
| Prop constraints | `python/src/orb_backtest/optimize/prop_constraints.py` | R-based constraint evaluation |
| Stability analysis | `python/src/orb_backtest/optimize/stability.py` | Walk-forward parameter stability |
| Walk-forward engine | `python/src/orb_backtest/optimize/walkforward.py` | Rolling IS/OOS optimization |
| Monte Carlo | `python/src/orb_backtest/simulate/monte_carlo.py` | Bootstrap/shuffle simulation |
| Metrics | `python/src/orb_backtest/results/metrics.py` | R-based performance metrics |
| Config | `python/src/orb_backtest/config.py` | StrategyConfig / SessionConfig |

## Pipeline Phases

| # | Phase | Purpose | Pass Criteria |
|---|-------|---------|---------------|
| 1 | Structural | Full-history backtest, basic metric check | Trades > 100, win rate > 35%, PF > 1.0 |
| 2 | Walk-Forward + Stability | Rolling 36m IS / 12m OOS, param stability | WF efficiency > 0.5, stability score >= 0.4 |
| 3 | Prop Constraint Filter | Evaluate R-based DD, annual R, monthly loss | All constraints pass on WF OOS trades |
| 4 | Hold-Out OOS | Test on reserved data never seen during optimization | Sharpe > 0.5, PF > 1.0, total R > 0 |
| 5 | Monte Carlo Survival | Bootstrap 1000+ sims, compute survival rate | Survival >= 70% at DD threshold |

See `references/phases.md` for detailed execution guide with code examples.
See `references/prop-constraints.md` for constraint thresholds and interpretation.

## Quick Start

```python
# Phase 1: Structural check
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics
trades = run_backtest(df, config, start_date="2016-01-01")
m = compute_metrics(trades)
assert m["total_trades"] > 100 and m["win_rate"] > 0.35 and m["profit_factor"] > 1.0

# Phase 3: Prop constraints on WF OOS trades
from orb_backtest.optimize.prop_constraints import evaluate_constraints, PropFirmConstraints
cr = evaluate_constraints(wf_result.combined_oos_trades, PropFirmConstraints(max_drawdown_r=10.0))
print(f"Passed: {cr.passed}, DD: {cr.max_drawdown_r:.1f}R, Expectancy: {cr.expectancy:.3f}R")

# Phase 2b: Stability
from orb_backtest.optimize.stability import analyze_parameter_stability
sr = analyze_parameter_stability(wf_result, param_ranges=swept_params)
print(f"Stability: {sr.overall_score:.2f} ({sr.interpretation})")

# Phase 5: MC survival
from orb_backtest.optimize.prop_constraints import evaluate_constraints_mc
mc_surv = evaluate_constraints_mc(mc_result, PropFirmConstraints(max_drawdown_r=10.0))
print(f"Survival: {mc_surv['survival_rate']:.1%}")
```

## Decision Framework

After all 5 phases, classify the candidate:

| Outcome | Criteria | Action |
|---------|----------|--------|
| **GO** | All phases pass | Deploy to prop firm |
| **CONDITIONAL** | Phase 5 survival 50-70% | Trade with reduced size or tighter DD |
| **NO-GO** | Any phase 1-4 fails or survival < 50% | Do not trade; revisit params |
