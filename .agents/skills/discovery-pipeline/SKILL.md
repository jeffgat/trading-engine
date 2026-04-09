---
name: discovery-pipeline
description: >
  Discovery-first robustness pipeline for candidate selection with explicit anti-overfitting
  safeguards. Finds and stress-tests a small shortlist on pre-holdout data using structural
  screening, walk-forward optimization, and parameter-stability checks, then prepares frozen
  candidates for downstream validation in phase-one-robust-pipeline. Use when the user says
  "discovery pipeline", "robust pipeline", "candidate discovery", "pre-holdout robustness", "shortlist candidates",
  "walk-forward + stability", "Bailey-aware discovery", or asks which parameter sets deserve
  promotion before payout-sprint testing. Differentiates from strategy-optimizer by adding
  promotion discipline and from phase-one-robust-pipeline by avoiding final payout evaluation.
---

# Discovery Pipeline

Discovery-first pipeline that answers: **"Which small set of parameter candidates is robust enough to deserve promotion into the phase-one payout pipeline without fooling us with backtest overfitting?"**

## When to Use

- Running pre-holdout candidate discovery with Bailey-aware discipline
- Turning a broad search space into a frozen shortlist of 1-3 candidates
- Stress-testing candidate families with walk-forward optimization and stability checks
- Comparing candidate configs through a standardized promotion workflow
- Preparing a strategy for downstream evaluation in `phase-one-robust-pipeline`

## Do NOT Use When

- Running a single backtest (use `orb-backtester`)
- Doing unconstrained exploratory sweeps with no promotion rules at all (use `strategy-optimizer`)
- Running final payout-sprint evaluation or funded-account EV ranking (use `phase-one-robust-pipeline`)
- Claiming final live-readiness from this skill alone

## Required Posture

- Reserve the final hold-out period before any discovery work. This skill must not touch it.
- Do all search, ranking, and robustness work on pre-holdout data only.
- Track trial count mentally and in the writeup. Bailey's core warning is multiple testing, not just weak OOS metrics.
- Prefer stable neighborhoods and plateaus over single-point maxima.
- Promote a very small frozen shortlist, ideally 1 main candidate plus at most 1-2 challengers.
- Treat parameter stability as a heuristic, not proof against overfitting.
- If PSR and DSR are implemented in the codebase, run them on every promoted candidate before handing anything to `phase-one-robust-pipeline`.
- If PBO or CSCV are implemented, include them as stronger Bailey-style diagnostics; if they are not implemented, say so explicitly.
- If PSR or DSR are not implemented, say so explicitly and cap the verdict at **heuristic** rather than statistically strong.
- Do not call this skill's output a final deployment verdict. Its job is candidate promotion, not final approval.

## Key Files

| Module | Path | Purpose |
|--------|------|---------|
| Prop constraints | `backtesting/src/orb_backtest/optimize/prop_constraints.py` | R-based constraint evaluation |
| Stability analysis | `backtesting/src/orb_backtest/optimize/stability.py` | Walk-forward parameter stability |
| Walk-forward engine | `backtesting/src/orb_backtest/optimize/walkforward.py` | Rolling IS/OOS optimization |
| Monte Carlo | `backtesting/src/orb_backtest/simulate/monte_carlo.py` | Bootstrap, shuffle, block bootstrap |
| Hold-out hygiene | `backtesting/src/orb_backtest/analysis/holdout_log.py` | Detect repeated hold-out use and preserve untouched final OOS |
| Metrics | `backtesting/src/orb_backtest/results/metrics.py` | R-based performance metrics |

## Pipeline Phases

| # | Phase | Purpose | Primary Output |
|---|-------|---------|----------------|
| 0 | Hold-Out Freeze | Reserve untouched final OOS before any search | Clean final hold-out declaration |
| 1 | Structural Family Screen | Reject obviously broken regions on pre-holdout data | Viable families / anchors |
| 2 | Discovery Search | Coarse search over pre-holdout data with explicit trial tracking | Candidate pool |
| 3 | Rolling Walk-Forward | Rank candidates by combined OOS behavior, not IS peaks | OOS-ranked shortlist |
| 4 | Local Stability / Plateau Check | Prefer robust neighborhoods over fragile maxima | Frozen promoted candidates |
| 5 | Promotion Packet | Prepare 1-3 candidates for `phase-one-robust-pipeline` with raw/effective trial counts and PSR/DSR when implemented | Promotion memo + frozen params |

See `references/phases.md` for the detailed execution guide with promotion rules.
See `references/prop-constraints.md` for constraint thresholds and interpretation.

## Bailey Add-On

- Prefer PBO via CSCV when available. Bailey treats that as the direct estimate of backtest overfitting.
- Run DSR and PSR on every promoted candidate when available. Raw Sharpe thresholds are not enough after multiple testing.
- If those diagnostics are missing in the codebase, say: `Bailey-style PBO/DSR not implemented; verdict is heuristic, not statistically deflated.`

## Decision Framework

After all phases, classify candidates conservatively:

| Outcome | Criteria | Action |
|---------|----------|--------|
| **PROMOTE** | Candidate is strong on pre-holdout discovery, combined OOS, and local stability; raw/effective trial counts are honest; PSR/DSR posture is acceptable | Freeze params and pass into `phase-one-robust-pipeline` |
| **CHALLENGER** | Candidate is viable but slower, thinner, or less stable than the leader, or its Bailey posture is acceptable but clearly weaker | Keep as backup and optionally pass alongside the leader |
| **REJECT** | Candidate relies on sharp peaks, weak OOS retention, missing deflation evidence, or excessive search inflation | Do not pass forward; revise the search space |
