---
name: robust-pipeline
description: >
  Five-phase validation pipeline for prop firm readiness with explicit anti-overfitting safeguards.
  Evaluates strategy robustness through pre-registered hold-out handling, rolling walk-forward
  validation, parameter stability, prop firm constraint filtering, final hold-out testing, and
  Monte Carlo survival analysis. Use when the user says "robust pipeline", "prop firm validation",
  "validate strategy", "is this strategy ready", "prop firm readiness", "survival analysis",
  "stability check", or "hold-out test", or asks whether a parameter set is robust enough to
  trade live while controlling overfitting risk. Differentiates from strategy-optimizer and
  multi-phase-backtest by focusing on validation, multiple-testing discipline, and go/no-go decisions.
---

# Robust Pipeline

Five-phase validation pipeline that answers: **"Is this parameter set robust enough to trade on a prop firm account without fooling us with backtest overfitting?"**

## When to Use

- Validating a parameter set before going live
- Running a full prop firm readiness check
- Testing if optimized params survive walk-forward, hold-out, and Monte Carlo
- Comparing multiple candidate configs through a standardized pipeline
- After multi-phase-backtest produces candidates - this skill filters them

## Do NOT Use When

- Running a single backtest (use `orb-backtester`)
- Optimizing parameters (use `strategy-optimizer` or `multi-phase-backtest`)
- Doing exploratory sweeps without a specific candidate to validate

## Required Posture

- Reserve the hold-out period before Phase 1. Do not let structural screening touch final hold-out data.
- Track trial count mentally and in the writeup. Bailey's core warning is multiple testing, not just weak OOS metrics.
- Treat parameter stability as a heuristic, not proof against overfitting.
- If PBO, CSCV, PSR, or DSR are not implemented, say so explicitly and cap the verdict at **heuristic** rather than statistically strong.
- Do not count Phase 3 or Phase 5 as independent new evidence. They stress the same OOS trade set from Phase 2.

## Key Files

| Module | Path | Purpose |
|--------|------|---------|
| Prop constraints | `backtesting/src/orb_backtest/optimize/prop_constraints.py` | R-based constraint evaluation |
| Stability analysis | `backtesting/src/orb_backtest/optimize/stability.py` | Walk-forward parameter stability |
| Walk-forward engine | `backtesting/src/orb_backtest/optimize/walkforward.py` | Rolling IS/OOS optimization |
| Monte Carlo | `backtesting/src/orb_backtest/simulate/monte_carlo.py` | Bootstrap, shuffle, block bootstrap |
| Hold-out hygiene | `backtesting/src/orb_backtest/analysis/holdout_log.py` | Detect repeated hold-out use |
| Metrics | `backtesting/src/orb_backtest/results/metrics.py` | R-based performance metrics |

## Pipeline Phases

| # | Phase | Purpose | Pass Criteria |
|---|-------|---------|---------------|
| 1 | Structural | Sanity check on pre-holdout history only | Trades >= 100, win rate >= 35%, PF > 1.0 |
| 2 | Rolling Walk-Forward | Default `12m IS / 3m OOS / 3m step`, combined OOS curve | WF efficiency >= 0.3-0.5, stability >= 0.4 |
| 3 | Prop Constraint Filter | Filter Phase 2 OOS trades against real account limits | Constraints pass on combined OOS trades |
| 4 | Final Hold-Out OOS | One untouched final test using mode params | Sharpe > 0.5, PF > 1.0, total R > 0 |
| 5 | Monte Carlo Survival | Stress the OOS trade distribution with real DD threshold | Survival >= 70% at actual breach threshold |

See `references/phases.md` for detailed execution guide with code examples.
See `references/prop-constraints.md` for constraint thresholds and interpretation.

## Bailey Add-On

- Prefer PBO via CSCV when available. Bailey treats that as the direct estimate of backtest overfitting.
- Prefer DSR or PSR when available. Raw Sharpe thresholds are not enough after multiple testing.
- If those diagnostics are missing in the codebase, say: `Bailey-style PBO/DSR not implemented; verdict is heuristic, not statistically deflated.`

## Decision Framework

After all 5 phases, classify the candidate conservatively:

| Outcome | Criteria | Action |
|---------|----------|--------|
| **GO** | All 5 phases pass, hold-out is clean, and Bailey diagnostics support the result | Deploy to prop firm |
| **CONDITIONAL** | 5 phases pass but PBO/DSR are unavailable, or Monte Carlo is only marginal | Trade reduced size or finish missing diagnostics first |
| **NO-GO** | Hold-out contaminated, Phase 1-4 fails, or Bailey diagnostics reject the edge | Do not trade; revisit parameters |
