---
name: phase-one-robust-pipeline
description: >
  Phase-one robust pipeline for first-payout optimization on all-weather prop-firm strategies.
  Use when the user wants a phase one robust pipeline, first payout pipeline, funded sprint,
  account farming EV, first payout rate, or time to payout analysis for a non-regime-specific
  strategy. Focuses on pre-registered hold-out handling, rolling walk-forward validation,
  structural viability, first-payout scorecards, and cohort EV rather than strict breach
  avoidance. Best for evaluating whether a strategy can reach first payout fast enough to justify
  reset costs under a default 50k funded-account model.
---

# Phase-One Robust Pipeline

Payout-sprint pipeline that answers: **"Can this all-weather strategy reach first payout quickly enough, often enough, and profitably enough to justify running many funded-account attempts?"**

## When to Use

- Evaluating a strategy for the sprint from funded-account start to first payout
- Comparing candidates by first payout rate, EV per attempt, and time to payout
- Reworking a current discovery-pipeline idea so it is judged as an account-farming business, not a breach-avoidance exercise
- Converting walk-forward OOS trades into funded-account outcomes

## Do NOT Use When

- The user wants a post-first-payout preservation framework
- The strategy is explicitly regime-gated
- The task is a generic one-off backtest or parameter sweep without payout economics

## Default Funded-Account Model

Use this default when the user does not specify a different prop setup:

- Account size `50,000`
- Starting balance `50,000`
- Max trailing drawdown `2,000`
- Initial breach floor `48,000`
- Trailing floor updates on end-of-day balance only
- Trailing floor stops rising once the account reaches `52,000`
- Phase-one sprint target is `52,500`
- First payout is modeled as a `500` withdrawal to recoup costs and ROI
- Phase-two handoff starts from a `50,000` floor after that first payout
- Default reset/account cost for EV examples is `$100`, but treat it as configurable

## Required Posture

- Reserve the hold-out period before Phase 1 and do not let screening touch it.
- Keep Bailey-style multiple-testing discipline from the existing `discovery-pipeline`.
- Reuse structural and walk-forward rigor from the existing robust pipeline.
- Do **not** treat worst month, annual R, or pure survival as the primary objective in phase one.
- Judge phase one with a scorecard first: payout rate, EV per attempt, time to payout, open-account trajectory, and failure clustering.
- Use monthly loss and drawdown as diagnostics that explain the payout business, not as automatic vetoes.

## Key Inputs and References

| Resource | Path | Purpose |
|---------|------|---------|
| Existing discovery validator | `.agents/skills/discovery-pipeline/SKILL.md` | Hold-out, walk-forward, and Bailey posture to preserve |
| Prop EV simulation reference | `backtesting/scripts/run_nq_lsi_propfirm_sweep.py` | Account-level payout/breach simulation patterns |
| Prop EV framework notes | `backtesting/learnings/prop_regime_specialist_framework.md` | EV vocabulary, payout metrics, and clustering questions |
| Phase guide | `references/phases.md` | Detailed execution flow for this skill |

## Pipeline Summary

| # | Phase | Purpose | Primary Output |
|---|-------|---------|----------------|
| 0 | Hold-Out + Model Freeze | Freeze the final OOS period and the funded-account economics | Clean hold-out, locked account model |
| 1 | Structural Viability | Confirm the strategy has enough pre-holdout signal to justify sprint analysis | Basic viability metrics |
| 2 | Rolling Walk-Forward | Test whether the strategy generalizes over time before payout modeling | Combined OOS trades, stability |
| 3 | First-Payout Scorecard | Convert combined OOS trades into first-payout outcomes | Payout rate, breach rate, EV, speed |
| 4 | First-Payout Hold-Out | Re-run the same sprint logic on untouched hold-out data | Final payout-sprint evidence |
| 5 | Cohort EV Simulation | Evaluate many parallel attempts as an account-farming business | Cohort EV, clustering, phase-two handoff rate |

See `references/phases.md` for the detailed workflow.

## Decision Framework

Classify the candidate with scorecard language instead of hard breach-avoidance language:

| Outcome | Criteria | Action |
|---------|----------|--------|
| **STRONG** | EV is positive, first payout is reached often enough and fast enough, and failures are not pathologically clustered | Candidate is worth ranking near the top for live/paper sprint testing |
| **CONDITIONAL** | EV is positive but payout is slow, sample is thin, or clustering risk is meaningful | Keep as a challenger, tighten the model, or lower its capital priority |
| **NO-GO** | EV is non-positive, payout path is too slow, or failures cluster badly enough to break the business model | Do not fund broadly; revisit params or strategy family |
