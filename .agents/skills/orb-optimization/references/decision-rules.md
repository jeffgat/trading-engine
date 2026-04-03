# Decision Rules Reference

Single source of truth for all thresholds, criteria, and decision logic used in the optimization workflow.

---

## Variable Sweep Adoption

- **Primary metric**: Calmar ratio
- **Adoption threshold**: Calmar delta > +0.3 vs anchor
- **Guard rails**: No new negative full years; trade count stays > 100; median stop >= 10 ticks
- **If adopted**: Update anchor, increment sweep round N, re-sweep all dimensions
- **Convergence**: 0 adoptions in a complete pass through all dimensions
- **Max changes per round**: Adopt 2-3 changes at most -- never 5+ simultaneously (destructive parameter interaction risk, see NQ Asia R3 crash in `backtesting/learnings/asset/NQ.md`)

## Grid Sweep Selection

- **Filter**: 0 negative full years required (preferred), or <= 1 neg year if no clean configs exist
- **Rank by**: Calmar ratio (descending)
- **If grid winner Calmar delta > +0.5 vs sweep anchor**: Adopt grid winner, return to variable sweeps
- **If grid winner approx equals anchor (delta < 0.5)**: Anchor confirmed, proceed to pipeline
- **Edge-of-grid winners**: Reject configs at grid boundary -- interior configs are more robust

## Baseline Pass/Fail

- **Pass**: > 100 trades AND PF > 1.0
- **Fail**: Record NO-GO in learnings, stop

## Pipeline Phase Thresholds

| Phase | Criterion | Threshold | Notes |
|-------|-----------|-----------|-------|
| 1 - Structural | Trades | > 100 | Statistical significance |
| 1 - Structural | Profit Factor | > 1.2 | |
| 1 - Structural | Win Rate | > 35% | Lowered from 45% for high-RR strategies |
| 1 - Structural | Calmar | > 0.5 | |
| 1 - Structural | Neg full years | 0 preferred | 1 acceptable if marginal |
| 2 - Walk-Forward | WF Efficiency | > 0.50 (strict), > 0.30 (marginal pass) | |
| 2 - Walk-Forward | Stability Score | >= 0.40 | Mode param consistency across folds |
| 2 - Walk-Forward | Total Folds | >= 4 | |
| 2 - Walk-Forward | OOS Folds Positive | Majority (> 50%) | |
| 3 - Prop Constraints | Max DD | NOT a filter (999.0) | INFO only -- see DD Policy |
| 3 - Prop Constraints | Daily Loss | INFO only | |
| 3 - Prop Constraints | Consistency | INFO only | |
| 3 - Prop Constraints | Annual R vs target | >= 12.0 R/yr | Prop firm viability |
| 3 - Prop Constraints | Expectancy | > 0 | Per-trade edge |
| 4 - Hold-Out | Sharpe | > 0.5 | |
| 4 - Hold-Out | PF | > 0.9 | Relaxed vs structural (unseen data) |
| 4 - Hold-Out | Net R | > 0 | |
| 5 - Monte Carlo | Survival Rate | > 85% (strong), > 60% (pass) | |
| 5 - Monte Carlo | Ruin Threshold | -25R | Standalone value, not tied to DD |
| 5 - Monte Carlo | Simulations | 2000 | |

## Final Verdict

| Outcome | Criteria | Action |
|---------|----------|--------|
| **GO** | All 5 phases pass | Deploy to prop firm |
| **CONDITIONAL** | 4 of 5 pass, or borderline failures | Trade with reduced size; note which failed |
| **NO-GO** | 3 or fewer pass | Do not trade; record in learnings |

## Minimum Stop Size (10-Tick Rule)

- **Never test or adopt a config where the median stop is less than 10 ticks**
- Computed as: `median(t.risk_points for t in filled_trades) / instrument.tick_size`
- Stops below 10 ticks are unrealistic (slippage eats the edge) and produce misleading backtests
- This applies to: variable sweep stop dimension, grid sweep results, baseline pass/fail, pipeline Phase 1
- In sweep scripts, skip the variant and print `SKIP (median stop < 10 ticks)` instead of metrics
- In grid sweeps, filter out combos with median stop < 10 ticks before ranking

## Minimum TP1 Ratio (0.2 Rule)

- **Never test or adopt a config with `tp1_ratio < 0.2`**
- A TP1 ratio below 0.2 takes too little off the table at the first target, leaving nearly all risk on for the full R:R move
- This applies to: variable sweep TP1 dimension, grid sweep TP1 axis
- In sweep scripts, skip the variant and print `SKIP (tp1_ratio < 0.2)` instead of metrics
- In grid sweeps, skip combos with tp1 < 0.2 before running the backtest (saves compute)

## DOW Filter Rules

- DOW exclusion is tested as a variable sweep dimension (excluded_days)
- Common patterns: exclude Monday (0), Thursday (3), Friday (4), or combinations
- **Data-mining warning**: If the "best" excluded day shifts every sweep round (e.g., Mon+Fri in R1, Wed in R2, Thu in R3), this is a classic data-mining signature -- do not adopt
- Adoption requires the same day(s) to be consistently beneficial across 2+ sweep rounds
- Trade count impact must be assessed -- excluding 2+ days can cut 30-40% of trades

## DD Policy (CRITICAL -- User Preference)

- Max drawdown is **NEVER** a hard filter
- Always set `max_drawdown_r = 999.0` in PropFirmConstraints
- Report DD as informational (INFO), never PASS/FAIL
- Remove `max_dd_r` from `run_walkforward()` calls -- do not pre-filter WF combos by DD
- MC ruin threshold (-25R) is a separate standalone value, not tied to DD constraints
- Position sizing handles dollar DD: a strategy with Calmar 1.0 at -15R DD is identical to one at -10R DD -- just trade at 2/3 size

## Walk-Forward Configuration

| Setting | Default | Notes |
|---------|---------|-------|
| IS window | 36 months | Training period |
| OOS window | 12 months | Test period |
| Step | 12 months | Non-overlapping OOS |
| Folds | 5-6 typical | Depends on data length |
| Objective | Sharpe or Calmar | Sharpe is more stable for WF |
| Combos per fold | 90-450 | Grid of swept params |

## Fixed-Param vs Adaptive Walk-Forward

- **Adaptive WF**: Re-optimizes params each fold. Tests if edge exists across the parameter surface.
- **Fixed-param WF**: Tests the specific candidate config across all folds. Tests if this exact point is robust.
- **If adaptive fails but fixed-param passes**: The parameter surface is noisy but the specific config is robust. Verdict can still be GO (see NQ NY R20).
- **If both fail**: NO-GO.
