# Phase-One Regime-Specific Pipeline — Phase Guide

This is the payout-sprint version of the regime-specific pipeline. Keep the causal-label and same-regime discipline from the existing regime skill, but judge the strategy as a funded-account business.

---

## Phase 0: Regime Audit and Model Freeze

Before any screening:

- define the regime rule
- prove labels are point-in-time
- reserve the same-regime hold-out
- freeze the funded-account model

Use the same default funded-account economics as `phase-one-robust-pipeline` unless the user overrides them.

---

## Phase 1: In-Regime Structural Viability

Run the candidate only on target-regime days, or filter trades to target-regime days.

Goal:

- confirm there is real specialist edge worth modeling
- reject one-off or tiny-sample specialists early

Good defaults:

- `total_trades >= 75-100`
- positive expectancy
- `profit_factor > 1.0`

---

## Phase 2: Same-Regime Walk-Forward

Optimize and validate chronologically inside the target regime only.

Carry forward:

- combined same-regime OOS trades
- walk-forward efficiency
- parameter stability
- number of regime episodes represented

If the candidate only works in one narrow episode, phase one business modeling should not rescue it.

---

## Phase 3: Full-Calendar First-Payout Scorecard

**Goal**: Evaluate the live gated system, not just specialist logic in isolation.

Run the gate plus strategy across all dates and report:

- first payout rate
- breach rate
- EV per attempt
- payout speed
- open-account rate
- first payout rate by regime
- breach clustering by regime shift
- in-regime versus out-of-regime contribution

This is where the gate earns its keep. The question is:

`Does the gate improve payout economics enough to justify specialist deployment?`

Use specialization ratio, attribution tables, and regime-shift failure notes to explain results.

---

## Phase 4: Final Same-Regime Hold-Out

Run one untouched same-regime hold-out test and convert those results into the same first-payout scorecard.

If there are too few target-regime observations, say the evidence is thin and downgrade confidence.

---

## Phase 5: Cohort EV and Specialist Diagnostics

Evaluate the strategy as a specialist account-farming business:

- cohort EV for parallel attempts
- payout/breach mix by regime
- clustering of breaches around regime transitions
- specialization ratio plus payout EV
- handoff rate into phase two

Preferred interpretation:

- **Strong**: gate improves EV, payout speed is acceptable, and failures are not badly clustered
- **Conditional**: EV is positive but depends too much on a narrow regime window
- **No-go**: gate does not improve the business enough or clustered failures are unacceptable
