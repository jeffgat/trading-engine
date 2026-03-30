---
name: phase-two-robust-pipeline
description: >
  Phase-two robust pipeline for post-first-payout validation on all-weather prop-firm strategies.
  Use when the user wants a phase two robust pipeline, post payout pipeline, withdrawal
  preservation, protect funded account, or post-first-payout review for a non-regime-specific
  strategy. Focuses on the same anti-overfitting discipline as the existing robust pipeline, but
  frames Phase 3 and Phase 5 around post-payout account longevity, steady withdrawals, and
  controlled giveback after ROI is already secured.
---

# Phase-Two Robust Pipeline

Post-first-payout pipeline that answers: **"Now that the account has already paid for itself, can this all-weather strategy keep producing withdrawals without giving the account back too recklessly?"**

## When to Use

- Validating a strategy after first payout has already been secured
- Ranking candidates by post-payout longevity and withdrawal continuity
- Reframing a generic robust-pipeline review as a post-first-payout preservation workflow
- Deciding whether a candidate should be trusted on accounts that have already reached the lock-in floor

## Do NOT Use When

- The real objective is to sprint to first payout
- The strategy is explicitly regime-gated
- The task is a generic optimization sweep instead of post-payout validation

## Required Posture

- Keep the hold-out and Bailey posture from the existing `robust-pipeline`.
- Phase two is conservative by default: survival still matters because the account is already monetizable.
- Reframe the goal from "never breach" to "maximize extracted post-payout withdrawals while preserving account longevity."
- Keep monthly loss, drawdown, and Monte Carlo path-risk as meaningful controls.
- Report how long the account keeps producing after first payout, not just whether it survives.

## Key Inputs and References

| Resource | Path | Purpose |
|---------|------|---------|
| Existing robust validator | `.agents/skills/robust-pipeline/SKILL.md` | Canonical conservative validation posture |
| Robust phase reference | `.agents/skills/robust-pipeline/references/phases.md` | Current structural/WF/hold-out flow |
| Prop constraints reference | `.agents/skills/robust-pipeline/references/prop-constraints.md` | DD, monthly loss, and MC diagnostics |
| Phase guide | `references/phases.md` | Post-first-payout framing for this skill |

## Pipeline Summary

| # | Phase | Purpose | Primary Output |
|---|-------|---------|----------------|
| 1 | Structural | Confirm the config still has viable pre-holdout behavior | Basic viability metrics |
| 2 | Rolling Walk-Forward | Produce a valid OOS trade stream and stable representative params | Combined OOS trades, stability |
| 3 | Post-Payout Continuity Filter | Judge whether OOS trade behavior supports ongoing withdrawals | Monthly loss, DD, continuity diagnostics |
| 4 | Final Hold-Out OOS | Test the representative config on untouched hold-out data | Final post-payout evidence |
| 5 | Post-Payout Path-Risk | Stress the OOS trade stream for giveback risk and withdrawal continuity | MC survival and continuity diagnostics |

See `references/phases.md` for the detailed workflow.

## Decision Framework

| Outcome | Criteria | Action |
|---------|----------|--------|
| **GO** | Structural, WF, hold-out, and post-payout continuity are all acceptable; path risk is controlled | Suitable for post-first-payout funded accounts |
| **CONDITIONAL** | Core edge is intact but continuity or path risk is only marginal | Trade smaller, withdraw more aggressively, or tighten operating rules |
| **NO-GO** | The strategy gives back too much too quickly or fails conservative validation outright | Do not use on monetized accounts without rework |
