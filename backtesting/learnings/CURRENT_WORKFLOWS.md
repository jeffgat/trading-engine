# New Strategy Workflow

1. **Start with the thesis**

   Define the strategy family, instrument, session, direction bias, and read the relevant `backtesting/learnings/asset/{ASSET}.md` first.

2. **Build a baseline**

   Create a simple baseline config or script and run a full-history pre-holdout backtest just to see if the idea is structurally alive.

3. **Freeze the final hold-out early**

   Reserve the most recent `12-24` months and do not touch it during discovery.

4. **Explore on pre-holdout data only**

   Run coarse variable sweeps or small grid searches with `2-3` parameters at a time. Start broad, then narrow.

5. **Use `discovery-pipeline`**

   Once the anchor stabilizes, use it to rank candidates by combined OOS behavior, walk-forward retention, and local plateau stability. Promote only a tiny frozen shortlist.

6. **Validate with PSR/DSR (overfitting gate)**

   Run PSR and DSR on every promoted candidate before phase-one.
   - **PSR** (Probabilistic Sharpe Ratio): confirms the observed Sharpe is real given sample size, skewness, and kurtosis. Threshold: PSR >= `0.95` = strong, >= `0.85` = moderate.
   - **DSR** (Deflated Sharpe Ratio): adjusts Sharpe for the number of strategies tested. Use effective independent trial count (cluster configs by trade-date overlap), not raw config count. Threshold: DSR >= `0.50` at effective trials = survives deflation.
   - If PSR is strong but DSR is weak, the edge is real but may not survive selection bias — proceed with caution and flag in the promotion memo.
   - Module: `backtesting/src/orb_backtest/validate/deflated_sharpe.py`

7. **Run `phase-one-robust-pipeline`**

   Feed only the frozen promoted candidates into phase one and evaluate payout rate, EV per attempt, and time to payout. Do not use phase one as the main search loop.

8. **Save and document the winner**

   After downstream validation, save the final config and update the asset learnings file with the conclusion and DB references.


# Regime Identification Workflow

1. **Define the regime question before labeling**

   Separate the dimensions on purpose:
   trend = `up`, `down`, `sideways`
   volatility = `low`, `medium`, `high`

   The combined live state can then be things like `up + high vol` or `sideways + low vol`.

2. **Use only causal inputs**

   Build regime labels only from information known before the session you want to trade.
   Good defaults:
   prior-day / rolling return measures
   close vs moving average shifted by `1` day
   rolling realized vol shifted by `1` day
   prior-session structure

   Do not label with same-day close or future returns.

3. **Start with simple hand-built rules**

   Prefer a small transparent rule set before trying ML clustering.
   Example:
   trend from shifted `close_vs_sma20` + shifted `5d return`
   vol bucket from shifted realized vol percentile or ATR percentile

4. **Freeze the final regime hold-out early**

   Reserve the most recent `12-24` months as the final untouched period for the regime framework too, not just the strategy.

5. **Tune regime thresholds on pre-holdout only**

   If you test multiple thresholds, moving average lengths, vol lengths, or bucket definitions, that is multiple testing.
   Count it honestly just like strategy parameter search.

6. **Audit sample size and episode balance**

   Before trusting any regime:
   check yearly counts
   check number of distinct episodes
   check trade counts inside each bucket

   Sparse buckets need simpler rules and higher skepticism.

7. **Validate the regime map out of sample**

   Yes, regime identification itself should be validated OOS.
   Treat the regime gate like its own model and test it with rolling / walk-forward splits on pre-holdout data.

   What to look for:
   stable bucket frequencies
   stable threshold behavior
   no dependence on one short calendar period
   no obvious drift that breaks the labeling logic

8. **Use regimes for attribution before optimization**

   First run robust candidate strategies on the full calendar and only attribute results by regime.
   This answers:
   where the strategy naturally works
   where it leaks
   whether the regime split is actually informative

9. **Promote regime specialists only when separation is real**

   Only create a specialist when in-regime behavior is materially better than out-of-regime behavior, not just slightly better.

10. **Optimize specialist variants inside the target regime only**

   If a strategy is promoted as, for example, `up + high vol`, optimize that specialist on pre-holdout observations from that target regime only.

11. **Validate the full gated system on all dates**

   A specialist does not need to win outside its target regime, but the live system must still be tested across the full calendar to verify the gate behaves correctly and mostly stays out when it should.

12. **Use the final hold-out once**

   Final evaluation should include:
   same-regime hold-out performance for the specialist logic
   full-calendar hold-out behavior for the gate + strategy combined


# Regime Rules Of Thumb

- Regime identification can absolutely be overfit and tainted.
- Regime definitions, thresholds, filters, and confidence rules all count as trials under Bailey-style multiple testing.
- Keep trend and volatility as separate axes first; combine them later only if the interaction clearly matters.
- Start with coarse buckets and only increase complexity if simpler labels already show stable value.
- Full-sample HMM / clustering can be useful for diagnosis, but not as a live trading gate unless it is rebuilt in a causal walk-forward way.


