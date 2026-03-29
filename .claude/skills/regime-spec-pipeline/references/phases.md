# Regime-Specific Pipeline — Phase Guide

Run from `backtesting/` using `uv run`.

---

## Phase 0: Regime Definition Audit

**Goal**: Prove the regime label is usable in live trading before optimizing anything.

Use regime labels that are known before or at the decision point:

- Prior-session structure
- Prior-day trend and volatility features
- Rolling realized vol
- Pre-open or prior-close state variables

Good examples in this repo:

- `build_nq_ny_regime_calendar()` in `orb_backtest.analysis.prop_regime_specialist`
- `compute_session_regime()` in `orb_backtest.signals.structure_15m`

Bad examples:

- Labeling a day "bull" because it finished up strongly
- Tagging regimes from future returns
- Using a classifier fit on the whole sample and then pretending labels were known in real time

**Pass checks**:

- No lookahead in the regime definition
- Enough target-regime observations to support optimization
- Multiple target-regime episodes if possible, not one single contiguous run
- Low-confidence or ambiguous days are either excluded or flagged explicitly

**Required write-up**:

- Exact regime rule
- What data is known at the time of labeling
- How many total regime days and target-regime days exist by year
- Whether low-confidence days are included

---

## Before Phase 1: Reserve a Final Same-Regime Hold-Out

Reserve a final hold-out period before any screening.

- If possible, choose a later episode of the same regime
- Keep it out of Phase 1 and Phase 2 completely
- Check `holdout_log` before use

This is the final conditional test:

- Bull specialist -> later unseen bull period
- Bear specialist -> later unseen bear period
- Sideways specialist -> later unseen sideways period

Do not use an unrelated regime as the main hold-out test for the specialist logic.

---

## Phase 1: In-Regime Structural Check

**Goal**: Confirm the candidate is viable inside the target regime on pre-holdout data.

Run the backtest only on target-regime trading dates, or filter the resulting trades to target-regime days.

```python
from orb_backtest.analysis.prop_regime_specialist import (
    build_nq_ny_regime_calendar,
    filter_trades_by_regime,
)
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

regime_calendar = build_nq_ny_regime_calendar(df, start_date="2016-01-01", end_date="2024-12-31")
trades = run_backtest(df, config, start_date="2016-01-01")
target_trades = filter_trades_by_regime(trades, regime_calendar, target_regime="bull")
m = compute_metrics(target_trades)
```

**Pass criteria**:

- `total_trades >= 75-100`
- `profit_factor > 1.0`
- positive expectancy
- enough years or episodes that the target regime is not a one-off accident

This is only a viability check. Do not use it to keep retuning.

---

## Phase 2: Same-Regime Walk-Forward

**Goal**: Optimize and validate only on target-regime observations, but do so chronologically.

Use rolling WF on pre-holdout data. The optimizer should score configs using target-regime trades only.

Preferred setup on long histories:

- `12m IS / 3m OOS / 3m step`

Use larger windows only if the regime is sparse.

What matters:

- IS uses earlier target-regime observations
- OOS uses later unseen target-regime observations
- combined OOS trades are stitched chronologically

**Pass focus**:

- conditional OOS edge remains positive
- walk-forward efficiency is still reasonable
- parameter stability is acceptable
- there are enough OOS folds or enough distinct target-regime episodes

**Important**:

- It is fine if performance is poor outside the target regime in this phase
- It is not fine if the strategy only works in one tiny bull run and nowhere else

**Bailey note**:

Regime conditioning shrinks sample size, so the burden of proof rises. If you tried many regime definitions or variants, say so explicitly.

---

## Phase 3: Full-Calendar Gate Test

**Goal**: Validate the live system, not just the specialist logic.

Run the regime gate plus the strategy across all dates.

Questions to answer:

- Does the gate correctly turn the strategy on in the target regime?
- Does it mostly stay out when not in regime?
- Are out-of-regime trades rare, small, or at least controlled?
- Does the combined system produce acceptable account behavior?

Useful diagnostics:

- in-regime vs out-of-regime avg R
- specialization ratio
- regime attribution table
- confusion log for low-confidence days

This is where non-target regimes matter. Not because the strategy must win there, but because the gate must behave correctly there.

---

## Phase 4: Final Same-Regime Hold-Out

**Goal**: Final untouched confirmation on a later unseen slice of the target regime.

Use mode params or a stable representative config from Phase 2. Then run exactly once on the reserved same-regime hold-out.

Also check and log hold-out usage:

```python
from orb_backtest.analysis.holdout_log import check_holdout_period, log_holdout_test

check = check_holdout_period("2025-01-01", "2025-12-31")
print(check.warning or "Hold-out is clean")
log_holdout_test("2025-01-01", "2025-12-31", config=mode_params, experiment_name="regime-spec-pipeline")
```

**Pass criteria**:

- positive conditional PnL
- PF > 1.0
- enough target-regime trades to say something meaningful

If the later hold-out contains very few target-regime days, say the evidence is thin and downgrade confidence.

---

## Phase 5: Monte Carlo + Specialist Diagnostics

**Goal**: Stress the target-regime OOS trade distribution and verify the strategy is actually regime-specific.

Use the combined same-regime OOS trades from Phase 2 for path-risk testing.

Prefer:

- block bootstrap over simple bootstrap
- real breach threshold, not a dummy DD cap

Also report specialist diagnostics:

- in-regime avg R
- out-of-regime avg R
- specialization ratio
- yearly target-regime contribution

Interpretation:

- strong in-regime edge plus weak or inactive outside-regime behavior is good
- strong in-regime edge with catastrophic outside-regime leakage means the gate is not ready
- similar performance in all regimes means this is not really a specialist

---

## Final Decision

Use both conditional and system-level evidence:

- **GO**: target-regime WF passes, full-calendar gate behaves, same-regime hold-out is clean, and specialist diagnostics support the claim
- **CONDITIONAL**: target-regime results are promising but hold-out is thin, path risk is marginal, or the gate still needs tightening
- **NO-GO**: causal regime definition is weak, same-regime OOS fails, or the strategy does not materially separate target from non-target behavior

Always label the conclusion honestly:

- "bull specialist"
- "bear specialist"
- "bull-biased but mixed-regime"
- "not actually regime-specific"
