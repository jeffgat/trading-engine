# Phase-Two Robust Pipeline — Phase Guide

This is the explicit post-first-payout version of the current robust pipeline. Reuse the same anti-overfitting discipline, but interpret the account through a monetized-account lens.

---

## Phase 1: Structural Validation

Reuse the structural checks from the existing robust pipeline:

- enough trades
- positive expectancy
- profit factor above `1.0`
- no obviously broken loss distribution

The goal is still to reject fundamentally weak candidates before path-risk analysis.

---

## Phase 2: Rolling Walk-Forward

Reuse the standard walk-forward posture:

- `12m IS / 3m OOS / 3m step`
- combined OOS metrics
- parameter stability
- explicit trial-count discipline

Phase two should remain conservative. If the strategy is unstable here, it should not graduate to post-payout account management.

---

## Phase 3: Post-Payout Continuity Filter

**Goal**: Ask whether the OOS trade stream is suitable for keeping a monetized account alive and productive.

Use the same kinds of diagnostics as the current robust pipeline, but interpret them through post-payout behavior:

- max drawdown
- worst month
- expectancy
- annual production
- max consecutive losses

Required commentary should include:

- how often the account would likely be in withdrawal mode versus recovery mode
- how violent the givebacks are after a good run
- whether losses are clustered enough to erase several weeks of expected withdrawals

The account is already paid for, so the question is not pure breach avoidance. It is whether the candidate preserves a usable withdrawal stream long enough to matter.

---

## Phase 4: Final Hold-Out OOS

Run the representative config once on the untouched hold-out.

Report the usual hold-out metrics plus:

- whether the hold-out would likely have supported continued withdrawals
- whether the loss shape would have forced overly defensive management
- whether the account would have stayed monetizable long enough after payout

---

## Phase 5: Post-Payout Path-Risk

Use Monte Carlo on the combined OOS trade distribution, but interpret it as continuity risk:

- survival at the chosen drawdown threshold
- drawdown percentiles
- monthly loss pass rate
- annual production pass rate

Add explicit post-payout commentary:

- how likely long withdrawal streaks are to be interrupted by deep giveback
- whether the strategy behaves like a steady extractor or a violent boom-bust profile
- whether a more aggressive withdrawal cadence would make sense

Interpretation:

- **GO**: the strategy survives conservative stress and still looks monetizable
- **CONDITIONAL**: the edge survives but giveback is too jagged for standard handling
- **NO-GO**: the post-payout continuity profile is too fragile
