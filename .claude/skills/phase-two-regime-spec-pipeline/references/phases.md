# Phase-Two Regime-Specific Pipeline — Phase Guide

This is the explicit post-first-payout version of the regime-specific pipeline. Keep the same-regime and causal-label discipline, but interpret the live system through monetized-account continuity.

---

## Phase 0: Regime Definition Audit

Keep the current regime rules:

- no hindsight labels
- enough target-regime observations
- explicit low-confidence handling
- same-regime hold-out reserved in advance

---

## Phase 1: In-Regime Structural Check

Confirm the specialist still has enough in-regime viability to justify post-payout handling:

- enough target-regime trades
- positive expectancy
- acceptable PF

This remains a viability gate, not a place to rationalize weak specialists.

---

## Phase 2: Same-Regime Walk-Forward

Use the same-regime walk-forward setup from the existing regime skill:

- optimize on earlier target-regime episodes
- test on later unseen target-regime episodes
- stitch combined OOS trades chronologically
- analyze parameter stability

Only candidates with real conditional edge should advance.

---

## Phase 3: Full-Calendar Post-Payout Gate Test

**Goal**: Ask whether the full gated live system behaves well on already-monetized accounts.

Report:

- in-regime and out-of-regime behavior
- gate leakage
- worst giveback periods after profitable runs
- whether the account would likely stay in withdrawal mode or recovery mode
- how much the gate helps continuity relative to ungated trading

The strategy does not need to win outside the target regime, but the gate must keep the full system controlled enough to remain monetizable.

---

## Phase 4: Final Same-Regime Hold-Out

Run the representative config once on the untouched same-regime hold-out and report:

- conditional hold-out performance
- whether the hold-out would likely have sustained withdrawals after payout
- whether the gate still looked trustworthy in that later period

If the hold-out is thin, downgrade confidence explicitly.

---

## Phase 5: Post-Payout Path-Risk and Specialist Diagnostics

Use Monte Carlo and specialist diagnostics together:

- survival and drawdown percentiles
- monthly loss pass rate
- annual production pass rate
- specialization ratio
- regime attribution
- whether post-payout continuity is materially better with the gate than without it

Interpretation:

- **GO**: specialist edge survives, gate behaves, and post-payout continuity is acceptable
- **Conditional**: the specialist works but post-payout continuity is too jagged for standard handling
- **No-go**: gate leakage or giveback makes the monetized-account profile too weak
