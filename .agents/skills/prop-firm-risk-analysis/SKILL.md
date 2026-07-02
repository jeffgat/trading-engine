---
name: prop-firm-risk-analysis
description: Prop-firm payout and risk analysis for trading strategies. Use when the user asks to model or optimize funded/prop account risk, EOD trailing drawdown, pass targets, first payout, account farming EV, staggered account starts, risk-per-trade sweeps, or post-first-payout survival-to-bust behavior. Covers custom models such as $2,000 EOD trailing drawdown, $3,000 pass target, $1,500 first payout, then continuing until bust.
---

# Prop Firm Risk Analysis

## Overview

Convert a filled trade stream into prop-account lifecycle outcomes. This skill isolates the account-risk layer from strategy research: given trades and a frozen account model, simulate staggered starts, first payout, post-payout survival, busts, open-account censoring, and EV.

Use this alongside strategy-specific skills such as `vwap-optimization`, `strategy-optimizer`, or `phase-one-robust-pipeline`. This skill does not prove strategy edge by itself; it answers whether a trade stream is economically useful under a prop-firm account path.

## Account Model

Default to the user-specified model unless they override it:

- EOD trailing drawdown: `$2,000`
- Pass target: `+$3,000`
- First payout: `$1,500`
- Trailing floor cap: starting balance, represented as `0` delta
- After payout: balance delta is reduced by `$1,500`, floor remains capped at start, so payout at `+$3,000` leaves `$1,500` drawdown cushion
- Continue trading until bust or data end
- Challenge/account fee: `$0` if unspecified
- Account starts: every `14` calendar days unless the user specifies another cadence

Do not model repeated payouts after the first payout unless the user explicitly asks for recurring withdrawals.

## Workflow

1. **Freeze the model and holdout**
   - State the account rules in dollars before ranking candidates.
   - Reserve holdout before screening. Do not use holdout rows for optimization.
   - Report exact data years and whether holdout was used.

2. **Generate filled trades**
   - Run the candidate strategy over the intended in-sample/pre-holdout window.
   - Filter no-fill trades.
   - Prefer micro contracts for small prop cushions when full-size futures make risk sizing too coarse. State the sizing assumption clearly, such as `MNQ sizing on NQ price data`.

3. **Simulate account starts**
   - Import the bundled helper:

```python
from pathlib import Path
import sys

SKILL_DIR = Path(".agents/skills/prop-firm-risk-analysis")
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from prop_firm_risk import (
    PropFirmRiskProfile,
    make_account_starts,
    score_prop_firm_outcomes,
    simulate_prop_firm_risk,
)

profile = PropFirmRiskProfile(
    trailing_drawdown_usd=2000.0,
    pass_target_usd=3000.0,
    first_payout_usd=1500.0,
    floor_cap_delta_usd=0.0,
    challenge_fee_usd=0.0,
    account_start_spacing_days=14,
)

starts = make_account_starts("2016-01-01", "2025-01-01", profile.account_start_spacing_days)
outcomes = simulate_prop_firm_risk(
    variant_id="candidate_name",
    trades=filled_trades,
    account_starts=starts,
    profile=profile,
    end_exclusive="2025-01-01",
)
score = score_prop_firm_outcomes(outcomes)
```

4. **Rank candidates**
   - Primary: realized first-payout EV per start and first-payout rate.
   - Secondary: recent-period first-payout rate, average days to first payout, open rate, and marked terminal EV.
   - Diagnostics: pre-payout bust rate, post-payout bust rate, minimum cushion distribution, max clustering of busts.
   - Penalize high open-account censoring when comparing recent windows.

5. **Report the prop read**
   - Include data years, trade count, account-start count, holdout status, sizing instrument, challenge fee, and exact account model.
   - Separate all-period score from recent-period score.
   - Label the outcome as account-farming economics, not standalone strategy quality, when bust rates are high.
   - Save ranked candidates, top account paths, summary JSON, and a learnings report when the result is meaningful.

## Interpretation

Use precise language:

- **Strong prop path**: positive realized EV, high payout rate, acceptable time to payout, and low open-account censoring.
- **Conditional prop path**: positive EV but high bust rate, slow payout, thin trades, or stale all-period strength.
- **No-go**: non-positive EV, excessive pre-payout busts, or results driven by open accounts rather than realized payouts.

Realized EV counts completed withdrawals minus fees. Marked EV can include open account equity, but it is secondary because that equity is not withdrawn.

## Common Gotchas

- EOD trailing floors ratchet after the trading day, not after every intraday mark.
- The floor caps at starting balance for this model; that is what makes `+$3,000` minus `$1,500` leave `$1,500` cushion.
- If a candidate only works at the top edge of the risk grid, run a targeted risk/RR refinement before calling it optimized.
- If the strategy has no live execution support or exact replay parity, keep status `research_only` regardless of prop EV.
- Always update research memory and rebuild the learnings registry after a meaningful new result.
