---
name: phase-one-regime-spec-pipeline
description: >
  Phase-one regime-specific pipeline for first-payout optimization on specialist strategies.
  Use when the user wants a phase one regime spec pipeline, regime phase one, same-regime payout,
  bull specialist, bear specialist, regime specialist payout, first payout rate, or account
  farming EV for a strategy that only trades in a target regime. Focuses on causal regime labels,
  same-regime walk-forward validation, full-calendar gate behavior, first-payout scorecards, and
  cohort EV rather than strict breach avoidance.
---

# Phase-One Regime-Specific Pipeline

Payout-sprint specialist pipeline that answers: **"Can this regime-gated strategy reach first payout efficiently enough to justify many funded-account attempts, and does the gate actually improve that payout business?"**

## When to Use

- Evaluating bull, bear, sideways, high-vol, or other regime specialists for first payout
- Testing whether a regime gate improves first payout rate or EV versus ungated trading
- Judging same-regime OOS edge through a funded-account business lens
- Comparing specialists by payout speed, payout frequency, and breach clustering by regime shift

## Do NOT Use When

- The strategy is intended to trade all environments
- The user wants a post-first-payout preservation framework
- The regime label is not causal or cannot be known point-in-time

## Default Funded-Account Model

Unless the user specifies otherwise, use the same default phase-one funded-account model as `phase-one-robust-pipeline`:

- `50k` funded account
- `2k` trailing drawdown
- end-of-day trail updates only
- trail locks at `50k`
- sprint to `52.5k`
- withdraw `500` at first payout
- default reset-cost example of `$100`

## Required Posture

- Regime labels must be causal and point-in-time.
- Same-regime OOS is still the right conditional test, but the final business question is payout EV.
- Validate the full gated system across all dates because the gate itself must survive live use.
- Reuse Bailey discipline from the current `regime-spec-pipeline`.
- Do **not** judge a specialist primarily by worst month or generic survival if the true phase-one question is first-payout economics.

## Key Inputs and References

| Resource | Path | Purpose |
|---------|------|---------|
| Existing regime specialist skill | `.agents/skills/regime-spec-pipeline/SKILL.md` | Causal-label and gate-discipline baseline |
| Existing regime rules | `.agents/skills/regime-spec-pipeline/references/regime-rules.md` | Label integrity and same-regime testing rules |
| Prop-firm phase-one workflow | `.agents/skills/prop-firm-phase1/SKILL.md` | Account-level payout/breach simulation patterns |
| Prop EV framework notes | `backtesting/learnings/prop_regime_specialist_framework.md` | EV metrics, failure clustering, and specialist business logic |
| Phase guide | `references/phases.md` | Detailed workflow for this skill |

## Pipeline Summary

| # | Phase | Purpose | Primary Output |
|---|-------|---------|----------------|
| 0 | Regime Audit + Model Freeze | Lock the regime label, hold-out, and funded-account economics | Clean label, clean model |
| 1 | In-Regime Structural Check | Confirm target-regime viability on pre-holdout data | Basic specialist viability |
| 2 | Same-Regime Walk-Forward | Test chronological generalization inside the target regime | Conditional OOS trades, stability |
| 3 | Full-Calendar First-Payout Scorecard | Judge the gated live system as a payout-sprint business | Payout rate, breach rate, gate value |
| 4 | Final Same-Regime Hold-Out | Run one untouched first-payout test on later target-regime data | Final specialist payout evidence |
| 5 | Cohort EV + Specialist Diagnostics | Measure account-farming EV and whether the gate truly helps | Cohort EV, specialization, clustering |

See `references/phases.md` for the detailed workflow.

## Decision Framework

| Outcome | Criteria | Action |
|---------|----------|--------|
| **STRONG** | First-payout EV is positive, payout timing is acceptable, clustering is controlled, and the gate clearly helps | Worth prioritizing for specialist paper/live sprint testing |
| **CONDITIONAL** | EV is positive but thin, slow, or highly regime-sensitive | Keep as a challenger or tighten the regime gate |
| **NO-GO** | EV is non-positive, the gate does not add value, or failures cluster badly enough to break the business model | Do not fund this specialist broadly |
