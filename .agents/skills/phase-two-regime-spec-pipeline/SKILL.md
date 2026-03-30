---
name: phase-two-regime-spec-pipeline
description: >
  Phase-two regime-specific pipeline for post-first-payout validation on specialist strategies.
  Use when the user wants a phase two regime spec pipeline, regime phase two, post payout
  specialist review, bull specialist, bear specialist, regime specialist, withdrawal preservation,
  or post-first-payout validation for a strategy that trades only in a target regime. Focuses on
  causal regime labels, same-regime walk-forward validation, full-calendar gate behavior, and
  conservative post-payout account preservation after ROI has already been secured.
---

# Phase-Two Regime-Specific Pipeline

Post-first-payout specialist pipeline that answers: **"After first payout has been secured, can this regime-gated strategy keep producing withdrawals without the gate leaking badly or giving back the account too quickly?"**

## When to Use

- Validating a bull, bear, sideways, or other specialist after first payout
- Measuring whether the gate supports post-payout longevity and controlled withdrawals
- Reframing the current regime-spec pipeline as an explicit post-first-payout workflow
- Comparing specialists by continuity after payout rather than by initial sprint speed

## Do NOT Use When

- The real objective is first payout
- The strategy is not regime-gated
- The regime label is hindsight-based or point-in-time invalid

## Required Posture

- Keep the causal-label discipline from the existing `regime-spec-pipeline`.
- Keep the conservative survival-first default because the account is already monetizable.
- Use same-regime OOS for specialist validation, but still test the full gated system across all dates.
- Judge the system by post-payout continuity, gate behavior, and giveback control.
- Keep Bailey-style multiple-testing discipline explicit in the write-up.

## Key Inputs and References

| Resource | Path | Purpose |
|---------|------|---------|
| Existing regime specialist skill | `.agents/skills/regime-spec-pipeline/SKILL.md` | Canonical specialist validation posture |
| Existing regime rules | `.agents/skills/regime-spec-pipeline/references/regime-rules.md` | Label integrity and gate rules |
| Existing discovery validator | `.agents/skills/discovery-pipeline/SKILL.md` | Conservative hold-out and Monte Carlo posture |
| Phase guide | `references/phases.md` | Post-first-payout specialist framing |

## Pipeline Summary

| # | Phase | Purpose | Primary Output |
|---|-------|---------|----------------|
| 0 | Regime Definition Audit | Verify a causal, live-usable regime label | Clean regime definition |
| 1 | In-Regime Structural Check | Confirm target-regime viability | Basic specialist metrics |
| 2 | Same-Regime Walk-Forward | Produce stable same-regime OOS evidence | Conditional OOS and stability |
| 3 | Full-Calendar Post-Payout Gate Test | Judge the gated live system on monetized accounts | Gate behavior and continuity |
| 4 | Final Same-Regime Hold-Out | Run one untouched later same-regime test | Final specialist post-payout evidence |
| 5 | Post-Payout Path-Risk + Specialist Diagnostics | Stress path risk and verify specialist behavior still helps | Continuity risk and specialist quality |

See `references/phases.md` for the detailed workflow.

## Decision Framework

| Outcome | Criteria | Action |
|---------|----------|--------|
| **GO** | Same-regime WF, gated-system behavior, hold-out, and post-payout continuity are all acceptable | Suitable for monetized specialist accounts |
| **CONDITIONAL** | Specialist edge is real but continuity or gate leakage is only marginal | Trade smaller, withdraw more aggressively, or tighten gating |
| **NO-GO** | The gate leaks badly, post-payout continuity is weak, or specialist evidence fails conservative review | Do not use this specialist post-payout |
