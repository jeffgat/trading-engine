# Council Transcript: Regime Gate Implementation Review

**Date:** April 3, 2026
**Question:** Review the regime gate implementation ported from backtesting to live execution for bugs, lookahead bias, and live/backtest parity.

---

## Framed Question

The user ported regime-gate logic from a Python backtesting research engine to a live execution engine for futures trading. The gates classify each trading day as bull/bear/sideways + low/medium/high volatility using NQ daily price data, then block trading on certain regime combinations.

Key files: `gates.py`, `engine.py`, `lsi_engine.py`, `main.py`, `api.py`, `historical_backtest.py`, `ConfigView.tsx`, `types.ts`.

Focus areas: (1) Lookahead bias, (2) Gate evaluation timing, (3) Normalization correctness, (4) Live vs backtest parity, (5) Placeholder day edge cases, (6) Bugs or logic errors.

---

## Advisor Responses

### 1. The Contrarian

Fatal Flaws Found:

1. **Placeholder day creates a ghost bar that corrupts rolling calculations.** The fake bar contaminates log_returns, realized_vol_21d, and ret_5d -- vol drops artificially (a zero-range bar), and the 5-day return gets a phantom close. The regime for today is computed using a fabricated price. This is silent: no error, wrong regime.

2. **The .shift(1) is applied to already-indexed daily data, but the index after reset_index(drop=True) is positional integers, not dates.** The calendar is returned with integer index. If anything upstream reindexes or merges on date, the shift relationship breaks silently. The backtest engine shifts on a date-indexed frame -- alignment is guaranteed. Here it's positional, which only works if rows are perfectly contiguous trading days.

3. **Frozen vol thresholds are a category error.** The backtesting engine computes 33rd/67th percentiles of pre-holdout vol. The execution engine hardcodes 0.1252 / 0.2040. If market vol regime shifts, the frozen thresholds misclassify persistently. There's no recalibration mechanism.

4. **No warmup guard on the live day's regime.** If the provider returns fewer than 21 bars, warmup_ok=False silently assigns "warmup" regime, and the gate behavior depends entirely on whether "warmup" is in the blocked list.

### 2. The First Principles Thinker

The implementation has one real flaw and a few non-issues.

**The real bug: min_periods mismatch.** The backtester requires 20 bars before emitting a SMA value, so early dates get NaN and are excluded from classification. The execution engine's rolling(20) with no min_periods defaults to min_periods=1, meaning it produces a SMA from the first available bar. Silent parity break. Fix: set min_periods=20.

**The placeholder day is correct.** After .shift(1), the classification used for today's trades is built from yesterday's actual data. The placeholder's own row gets shifted away and never drives a decision.

**The frozen vol thresholds are acceptable.** Tercile thresholds frozen from training data are standard practice for live deployment.

**The shift alignment is correct** in both engines.

**Net verdict:** One concrete fix needed. Change rolling(20).mean() to rolling(20, min_periods=20).mean().

### 3. The Expansionist

The frozen threshold architecture is the most undervalued part of this build. Those hardcoded vol boundaries aren't a limitation -- they're a deployment superpower.

Next moves: derive asset-specific thresholds for ES, CL, GC, RTY. Flip AND logic to select high-conviction windows. Stress-test NQ-as-universal-regime-proxy. Add OR logic. Build gate hit-rate telemetry for self-improving filter.

### 4. The Outsider

Six real problems, ranked by severity:

1. **Silent logic error in _blocking_regime_gate_name (Critical)** -- fallback branch can never be reached after initialization normalization. Dead code that looks like a safety net.

2. **Rolling windows produce silent NaN propagation (High)** -- no min_periods means first 19+ days produce wrong decisions with no warning.

3. **Initialization normalization is stateful mutation disguised as setup (High)** -- mutates self.regime_gate, self.regime_gates, and self.regime_gate_checks conditionally across three branches with overlapping logic. Silent None-setting.

4. **Code duplication across engine.py and lsi_engine.py (Medium)** -- any fix must be applied twice.

5. **Placeholder day edge case fails non-consecutively (Medium)** -- guard silently returns unmodified dataframe for date gaps > 1 day. No error, no log.

6. **API serialization arbitrarily drops multi-gate info (Low)** -- two-gate config serializes with regime_gate: null.

### 5. The Executor

Ship with two fixes, monitor one risk.

**Fix immediately:** (1) Add min_periods=20 to all rolling windows. (2) Standardize normalization and _blocking_regime_gate_name into shared module.

**Monitor actively:** Daily bar source discrepancy -- if DailyHistoryProvider uses exchange session boundaries instead of midnight ET, ATR-based regime thresholds drift 10-15%.

**What's genuinely solid:** .shift(1) discipline is correct. Fail-safe blocking is right default. Warmup-via-NaN equivalent to explicit warmup given sufficient history.

---

## Peer Reviews

### Anonymization Mapping
- Response A = The Contrarian
- Response B = The First Principles Thinker
- Response C = The Expansionist
- Response D = The Outsider
- Response E = The Executor

### Reviewer 1
- **Strongest: A** -- correctly identifies ghost bar contamination and warmup silence.
- **Biggest blind spot: C** -- zero diagnostic value.
- **All missed:** _calendar_row_for_date lookup uses .iloc[-1] with no assertion (duplicate date risk). _daily_history_provider is a module-level global with no thread safety.

### Reviewer 2
- **Strongest: A** -- diagnoses why things break, not just that they break.
- **Biggest blind spot: C** -- pure product opinion dressed as code review.
- **All missed:** Timezone boundary mismatch risk documented in project memory -- daily bar resampling midnight ET vs exchange session boundaries causing 10-15% ATR discrepancy.

### Reviewer 3
- **Strongest: A** -- real data integrity issues, subtle alignment bugs.
- **Biggest blind spot: C** -- pivots to strategy opinions.
- **All missed:** ATR boundary discrepancy documented in project memory.

### Reviewer 4
- **Strongest: A** -- ghost bar contamination and index-shift misalignment are correctness failures.
- **Biggest blind spot: C** -- ignores the question entirely.
- **All missed:** Live execution timing -- if daily data provider delivers a partial current-day bar, the shift lands on an incomplete bar.

### Reviewer 5
- **Strongest: A** -- ghost bar and index-shift are real.
- **Biggest blind spot: C** -- could actively mislead developers.
- **All missed:** ATR boundary mismatch documented in project memory.

---

## Chairman's Synthesis

### Where the Council Agrees

- **min_periods on rolling windows is a confirmed bug** (B, D, E unanimous).
- **The .shift(1) discipline is correct** -- no lookahead bias (B, E).
- **Frozen vol thresholds are acceptable** standard practice (B, E).

### Where the Council Clashes

The sharpest disagreement: is the placeholder day a ghost bar (Contrarian) or correct pattern (First Principles, Executor)? Chairman sides with First Principles: the placeholder's regime label is discarded. However, the placeholder's synthetic return value (0.0) does participate in realized_vol_21d's rolling window on that final row -- a narrow contamination that A correctly identified for the wrong reason.

### Blind Spots the Council Caught

1. **ATR boundary mismatch** (3/5 reviewers): Project memory documents 10-15% discrepancy between midnight ET vs exchange session daily bars.
2. **Partial current-day bar contamination**: If provider delivers incomplete bar before market close.
3. **Duplicate date risk in _calendar_row_for_date**: .iloc[-1] silently picks last match.
4. **Thread safety on _daily_history_provider**: Module-level global with no locking in async context.

### The Recommendation

Ship after fixing three things:
1. Add min_periods=20 to all rolling windows in gates.py.
2. Verify daily bar provider uses midnight ET boundaries, not exchange session boundaries.
3. Assert exactly one row in _calendar_row_for_date.

### The One Thing to Do First

Audit the daily bar provider's session boundary definition against midnight ET.
