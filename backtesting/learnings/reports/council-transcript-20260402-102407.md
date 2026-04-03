# LLM Council Transcript — Regime Gate Lookahead Analysis

**Date:** April 2, 2026
**Question:** Does the medium-vol regime avoidance gate for NQ LSI suffer from lookahead bias, and is it implementable in a live execution engine?

---

## Framed Question

The gate skips LSI trades on days classified as "bull_medium_vol" or "sideways_medium_vol" using:
- **Trend axis:** close_vs_sma20, ret_5d (both .shift(1) = yesterday's close)
- **Vol axis:** realized_vol_21d (.shift(1) = yesterday's close), frozen tercile thresholds (12.52% / 20.40%)
- **Strategy session:** NY 09:30-15:50 ET

Verified from source: `_apply_feature_shifts()` shifts all three features by 1 day before classification.

---

## Advisor Responses

### Advisor 1: The Contrarian

Gate is clean on lookahead but has 3 fatal flaws: (1) midnight-ET daily boundary bug — resample("1D") groups by midnight not CME session boundaries (6PM-5PM ET), so "yesterday's close" may not match what a live trader sees; (2) live implementation requires knowing which close to use, and the boundary is ambiguous across vendors; (3) frozen vol thresholds will drift over time with no recalibration mechanism.

**Verdict:** Lookahead is not the problem. Live execution will differ from backtest.

### Advisor 2: The First Principles Thinker

No lookahead, fully implementable. The .shift(1) means yesterday's close, available before 09:30. Four arithmetic operations on a rolling close series. Only caveat: ensure backtest resample("1D").last() matches live feed's close.

**Verdict:** Clean. Directly implementable.

### Advisor 3: The Expansionist

Clean and trivially live-implementable. The structural explanation (medium-vol = false sweeps without sharp dislocations) means this is not curve-fitting but a mechanistic edge.

**Verdict:** Ship it.

### Advisor 4: The Outsider

Daily computation is fine but the vol tercile thresholds (12.52%/20.40%) ARE a form of lookahead — computed on the full 8-year pre-holdout period, so any backtest within that window has thresholds that "saw" the whole distribution. Needs true OOS validation.

**Verdict:** Thresholds are the risk. Validate on unseen data.

### Advisor 5: The Executor

No lookahead. Morning batch job at ~09:25 ET: pull yesterday's close, compute 3 features, classify, set flag. Need 25-bar daily close history. Frozen thresholds mean no live re-estimation.

**Verdict:** Build it. Low complexity, clean bias argument.

---

## Peer Review

**Anonymization:** A=Contrarian, B=First Principles, C=Expansionist, D=Outsider, E=Executor

### Reviewer 1
- Strongest: D — correctly identifies distributional lookahead in threshold computation
- Biggest blind spot: C — conflates structural narrative with implementation validity
- All missed: midnight-ET resampling boundary mismatch (documented in MEMORY.md for ATR)

### Reviewer 2
- Strongest: D — the one genuine methodological issue
- Biggest blind spot: A — invents flaws that don't match the code
- All missed: post-hoc filtering vs. pre-trade gate creates trade-sequencing discrepancy

### Reviewer 3
- Strongest: D — identifies threshold contamination in WF folds
- Biggest blind spot: C — no mechanism for threshold recomputation in live
- All missed: holiday edge case for .shift(1) landing on non-trading day NaN

### Reviewer 4
- Strongest: D — names threshold leakage with precision
- Biggest blind spot: C — dangerously underspecified "ship it"
- All missed: live system must use prior session close, not intraday data

### Reviewer 5
- Strongest: A — identifies concrete implementation risks including midnight-ET boundary
- Biggest blind spot: C — no guidance on live implementation
- All missed: WF builds regime calendar from full dataset, thresholds globally frozen not fold-by-fold

---

## Chairman Synthesis

### Where the Council Agrees
All five agree .shift(1) is not lookahead. Yesterday's close is known before 09:30. Mechanically implementable as morning batch job.

### Where the Council Clashes
Whether vol thresholds (12.52%/20.40%) constitute distributional leakage. Outsider (4/5 peer support) says yes. Three advisors treat as non-issue. Contrarian's midnight-ET boundary concern is legitimate but engine-wide, not gate-specific.

### Blind Spots the Council Caught
1. Post-hoc vs. pre-trade filtering — trade sequencing differs
2. Holiday NaN edge case — behavior unspecified
3. WF threshold shortcut — globally frozen, not fold-by-fold
4. Threshold drift — no recalibration mechanism

### The Recommendation
Gate is NOT lookahead-contaminated in bar-signal sense and IS implementable. Three graded risks: (1) Medium — distributional threshold leakage, (2) Low-Med — post-hoc vs pre-trade filtering, (3) Low — operational hygiene. Sound design with fixable risks.

### The One Thing to Do First
Run holdout OOS test with fold-by-fold threshold recomputation. If performance difference is small, global shortcut is validated. If materially worse, gate's edge is partially illusory.
