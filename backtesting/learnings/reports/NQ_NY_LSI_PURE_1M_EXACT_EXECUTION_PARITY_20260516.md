# NQ NY LSI Pure 1m Exact Execution Parity - 2026-05-16

## Objective

Move the pure 1m order-book velocity survivor from research-only rule replay toward live-native execution by validating that the live `LSIEngine` can reproduce the frozen holdout trade set.

Candidate:

- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`
- Feature overlay: `confirm_last_10s_mid_velocity_ticks_per_second`
- Confirmation: CISD
- Entry: level-limit
- Stop: `15%` daily ATR capped by structure
- Timeframe: `1m`
- Entry cutoff: `12:00 ET`

## Implementation

Execution-side additions:

- Added a causal `InternalCisdTracker` for bar-by-bar CISD events.
- Added `lsi_confirmation_mode="cisd"`, `lsi_stop_mode="atr_pct"`, `stop_atr_pct`, and `base_bar_minutes` to the live LSI path.
- Added the disabled profile `NQ_LSI_PURE_1M_OBV_SHADOW` targeting `NQ_NY_LSI_PURE_1M`.
- Updated exact replay to route `1m` and `5m` bars to matching engines instead of assuming every LSI engine is `5m`.
- Preserved zero-cost defaults: MBP-10 streaming and dynamic sizing remain disabled unless explicitly enabled with cost acknowledgement.

## Replay Result

Replay path:

- `execution/src/trader/historical_backtest.py`
- Profile: `NQ_LSI_PURE_1M_OBV_SHADOW`
- Window: `2025-04-10` to `2026-04-30`
- Data source: local parquet/cache only
- DataBento fetches: `0`

Research holdout from `validated_trades.csv`:

- Trades: `21`
- Unique trade dates: `21`
- Baseline total R: `+4.841R`

Exact execution replay:

- Trades: `21`
- Unique trade dates: `21`
- Date-set match: `21/21`
- Missing dates: `0`
- Extra dates: `0`
- Live-style total R: `+5.50R`
- Avg R: `0.262R`
- Profit factor: `1.84`
- Max DD: `-1.50R`

## Interpretation

Signal-date parity is now cleared for the pure 1m survivor. The execution engine can reproduce the same frozen holdout trade dates using its live state machines.

The R totals are not expected to be identical yet: the research survivor score is a 1m bar-level result, while exact execution replay exits through the live-style 1s tick path. Treat the `+5.50R` exact replay result as the more operationally realistic live-engine read for the no-orderbook baseline trade set.

## Status

`post_filter_only` moving toward `live_native`.

Cleared:

- Historical MBP-10 holdout data blocker
- Raw DBN-to-live-cache feature replay
- Pure 1m CISD/ATR-stop signal-date replay through the live execution engine

Remaining before quantity-changing live use:

- Paper/shadow run with `dynamic_sizing_shadow_enabled=true`
- Compare live MBP-10 feature values against offline replay on the same signal windows
- Decide whether production uses `0.5/1/1.5`, `0/1/1.5`, or a more conservative sizing ladder after engine-level quantity/account review
