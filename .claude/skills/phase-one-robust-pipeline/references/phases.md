# Phase-One Robust Pipeline — Phase Guide

Run from `backtesting/` using `uv run` and reuse the same anti-overfitting posture as the existing robust pipeline.

---

## Phase 0: Hold-Out and Funded-Account Model Freeze

**Goal**: Freeze both the final OOS slice and the phase-one business model before screening.

Lock the following up front:

- Hold-out dates
- Account size and trailing DD model
- First-payout milestone
- Withdrawal at first payout
- Reset cost assumption
- Whether open accounts are counted as mark-to-market EV or excluded from ranking

Default model if the user does not override it:

- Start `50,000`
- Breach if end-of-day trailing floor falls below equity by more than `2,000`
- Trail stops rising above `50,000`
- First phase-one milestone at `52,500`
- Withdraw `500` at first payout
- Hand off surviving account to phase-two logic with `50,000` floor
- Use `$100` as the default reset-cost example

---

## Phase 1: Structural Viability

**Goal**: Confirm the candidate has enough edge to justify payout-sprint analysis.

Reuse the conservative structural checks from the current robust pipeline:

- enough trades
- positive edge
- no obviously broken distribution

Good defaults:

- `total_trades >= 100`
- `profit_factor > 1.0`
- positive expectancy

This phase is only a viability filter. Do not redesign the strategy here.

---

## Phase 2: Rolling Walk-Forward

**Goal**: Produce a chronologically valid OOS trade stream for payout economics.

Preferred setup:

- `12m IS / 3m OOS / 3m step`
- rolling, not anchored
- optimize on a risk-adjusted objective such as Sharpe

Carry over:

- combined OOS trades
- walk-forward efficiency
- parameter stability
- total trials tried across the broader research effort

Phase two should still fail obviously unstable candidates. The phase-one business model should not rescue a strategy that does not generalize.

---

## Phase 3: First-Payout Scorecard

**Goal**: Grade the combined Phase 2 OOS trades as first-payout account attempts.

Convert OOS trades into funded-account outcomes and report:

- first payout rate
- breach rate
- open-account rate
- EV per account attempt
- average and median days to first payout
- average and median trades to first payout
- average resets per first payout
- open-account average and median R
- breach clustering over time

Do **not** use annual R or worst month as the primary pass/fail gate here. Report them as diagnostics only if they help explain why payout economics are weak.

Primary ranking order:

1. EV per attempt
2. First payout rate
3. Median days to first payout
4. Resets per first payout
5. Failure clustering and open-account health

---

## Phase 4: First-Payout Hold-Out

**Goal**: Repeat the same payout-sprint conversion once on the untouched hold-out.

Use the representative config from walk-forward, then evaluate:

- hold-out first payout rate
- hold-out breach rate
- hold-out EV per attempt
- hold-out time to payout
- whether open hold-out accounts are trending positive enough to matter

If the hold-out has very few resolved accounts, downgrade confidence rather than pretending the result is conclusive.

---

## Phase 5: Cohort EV Simulation

**Goal**: Evaluate the candidate as an account-farming business, not as a single-account survival problem.

Model parallel attempts and report:

- cohort EV for `10 / 25 / 50` account attempts
- total payouts, breaches, and still-open accounts
- payout timing distribution
- resets required per cohort
- concentration of breaches in the same bad regime/month
- handoff rate into phase two after first payout

This phase is intentionally **not** framed as single-account breach avoidance. The central question is:

`Does the payout stream outweigh reset costs with acceptable speed and acceptable clustering?`

Interpretation:

- **Strong**: cohort EV is positive, payout timing is reasonable, and clustering is controlled
- **Conditional**: cohort EV is positive but slow, thin, or highly regime-sensitive
- **No-go**: cohort EV is non-positive or clustering breaks the business model
