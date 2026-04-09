# Current Strategy Workflow

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
