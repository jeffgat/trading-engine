# NQ NY LSI Pure 1m Order-Book Velocity Live Scope

Date: 2026-05-15

## Objective

Scope the first live implementation path for the cleaner order-book survivor:

- Candidate: `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`
- Feature: `confirm_last_10s_mid_velocity_ticks_per_second`
- Sizing profile: `tier_0p5_1_1p5`
- Validation thresholds: low `< -0.322`, mid `[-0.322, 0.912)`, high `>= 0.912` ticks/sec
- Weights: low `0.5x`, mid `1.0x`, high `1.5x`

This scope is implementation-first, not another threshold-mining pass. The research result stays `research_only` until live MBP-10 streaming, dynamic sizing, and exact replay/paper parity are implemented.

## Current Evidence

The stricter stress run kept the primary `0.5/1/1.5` overlay breach-clean after 1 tick/side slippage:

| Period | Trades | Weighted R | Avg R | PF | Max DD | Account EV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Holdout | 21 | `+8.07R` | `0.384R` | `2.23` | `-1.53R` | `+3.83R` |
| Post-2023 | 54 | `+19.23R` | `0.356R` | `2.22` | `-2.84R` | `+4.64R` |

The holdout high tier carried the edge: `11` trades, `+9.45R`, `0.859R` avg, PF `4.13`. Low and mid tiers were negative on holdout, so the first deployment should expose both the primary risk-tier profile and a shadow `0/1/1.5` skip-weak profile, while only considering `0.5/1/1.5` for actual promotion until exact replay confirms otherwise.

## DataBento Live Requirements

The current live feed subscribes to `ohlcv-1m` and `ohlcv-1s` in a single `DataBentoFeed` session. DataBento's live API supports multiple subscriptions for different schemas in the same session, and MBP-10 provides top-ten market-by-price events with trade and depth updates. In Python, bid/ask depth is exposed as `record.levels`, with top-of-book at index `0`.

Implementation implications:

- Add an optional `mbp-10` subscription only when an enabled execution profile requires order-book features.
- Route `db.MBP10Msg` records where `record.rtype == RType.MBP_10`.
- Use existing `SymbolMappingMsg` and front-month election so MBP records are attributed to the same parent symbol as OHLCV bars.
- Fallback to neutral `1.0x` when front-month is unknown or the last-10s window lacks coverage.

References:

- Databento Live client: https://databento.com/docs/api-reference-live/client/live
- Databento schemas/MBP-10: https://databento.com/docs/schemas-and-data-formats
- Databento live recovery note for stateless MBP-10: https://databento.com/docs/api-reference-live/basics/schemas-and-conventions

## Execution Code Insertion Points

1. Feed layer: `execution/src/trader/feed.py`
   - Add `OnSymbolOrderbookCallback`.
   - Extend `DataBentoFeed.__init__` with `on_orderbook` and `enable_mbp10`.
   - In `_connect()`, subscribe to `schema="mbp-10"` when enabled.
   - In the async loop, handle `db.MBP10Msg` separately from `db.OHLCVMsg`.

2. Feature layer: new `execution/src/trader/orderbook_features.py`
   - `MBP10TopOfBookSample`: parent symbol, raw contract, instrument id, event timestamp, bid, ask, mid.
   - `OrderbookFeatureCache`: rolling per-symbol top-of-book samples, default retention `90s`.
   - `OrderbookVelocitySizer`: computes `direction * (last_mid - first_mid) / min_tick / seconds` over `[signal_end - 10s, signal_end)`.
   - `DynamicSizingDecision`: feature value, tier, risk weight, coverage, sample count, reason.

3. Main wiring: `execution/src/trader/main.py`
   - Detect any enabled LSI session with `orderbook_dynamic_sizing.enabled = true`.
   - Construct the shared feature cache/sizer.
   - Pass `on_orderbook` into `DataBentoFeed`.
   - Inject a `dynamic_sizing_provider` into target `LSIEngine` instances only.

4. Engine sizing: `execution/src/trader/lsi_engine.py`
   - Add optional `dynamic_sizing_provider`.
   - At `_build_and_enter()`, request a decision before quantity is finalized.
   - Apply final quantity multiplier as `qty_multiplier * decision.risk_weight`.
   - Do not let a missing feature increase risk; fallback is `1.0x`.
   - For future skip-weak tests, allow `risk_weight=0.0` to reject the entry with a specific `ENTRY_REJECTED_DYNAMIC_SIZING` log reason.

5. Trade metadata: `execution/src/trader/engine.py`, `execution/src/trader/api.py`, `execution/src/trader/checkpoint.py`
   - Add a compact metadata field to `TradeRecord`, such as `entry_context: dict[str, Any] = field(default_factory=dict)`.
   - Persist order-book sizing metadata in checkpoint JSON and live DB payload:
     - feature name/value
     - tier
     - requested risk weight
     - actual quantity multiplier after contract rounding/caps
     - coverage/sample count/fallback reason

## Proposed Config Shape

Use session-level config so this can be scoped to the pure 1m long leg without changing every LSI profile:

```json
"orderbook_dynamic_sizing": {
  "enabled": true,
  "schema": "mbp-10",
  "feature": "confirm_last_10s_mid_velocity_ticks_per_second",
  "window_seconds": 10,
  "min_coverage": 0.8,
  "fallback_weight": 1.0,
  "low_threshold": -0.322,
  "high_threshold": 0.912,
  "weights": {
    "low": 0.5,
    "mid": 1.0,
    "high": 1.5
  },
  "directions": ["long"]
}
```

## Causality Rules

- Score only after the signal bar is closed.
- Use `signal_end` as the right edge of the feature window.
- For the 1m survivor, `signal_end = signal_start + 1 minute`; the feature window is the final 10 seconds before that close.
- Do not use `post_confirm_*` features for entry sizing.
- If timestamp semantics differ between the research candidate and the live engine, block promotion until exact replay proves parity.

## Candidate-Parity Gap

This survivor is a pure 1m CISD-style research candidate. The current live `LSIEngine` is already LSI-capable, but the active live profiles inspected today are mostly legacy/HTF 5m shapes. Dynamic sizing infrastructure can be implemented generically first, but the candidate is not live-native until we also verify or implement:

- 1m bar signal cadence for this profile.
- CISD timing parity.
- ATR15 and stop/target parity.
- `long_only`, all-DOW behavior, and `cut1200` style trade cutoff.
- Exact backtest replay through the live execution engine, not just research CSV weighting.

## Implementation Phases

1. Offline/live-neutral feature module
   - Build `orderbook_features.py` with synthetic-unit tests.
   - No DataBento live subscription required.
   - Prove threshold/tier mapping and fallback behavior.

2. Live MBP-10 stream, disabled by default
   - Add optional feed subscription and callback.
   - Paper log top-of-book samples for NQ only.
   - Validate sample timestamps, front-month mapping, and mid calculation.

3. Engine dynamic sizing, dry-run only
   - Inject the provider into `LSIEngine`.
   - Log sizing decisions at entry time.
   - Persist decision metadata to checkpoints and trade history.

4. Exact replay bridge
   - First pass: deterministic lookup provider from existing scored feature CSVs to validate quantity/sizing behavior with no new fetch.
   - Second pass: DBN/MBP replay provider once broader local MBP-10 files exist.

5. Paper/live shadow
   - Run with webhooks paused or dry-run profile.
   - Compare live feature values against offline scorer on the same windows.
   - Track requested weight versus actual risk after quantity rounding and position caps.

6. Promotion review
   - Rerun account stress with engine-level quantities.
   - Review missed/fallback entries.
   - Only then decide between `0.5/1/1.5`, `0/1/1.5`, or conservative `0.75/1/1.25`.

## Test Plan

- Unit: long rising mids create positive velocity; long falling mids create negative velocity; short direction reverses the sign.
- Unit: tier thresholds exactly match `-0.322` and `0.912`.
- Unit: insufficient coverage returns fallback `1.0x`.
- Unit: `risk_weight=0.0` rejects before broker order creation.
- Integration: mocked `db.MBP10Msg` records update the feature cache through `DataBentoFeed`.
- Integration: dynamic sizing metadata survives checkpoint save/load.
- Replay: the CSV lookup provider reproduces the risk-tier weighted trade counts from the frozen replay.

## Open Risks

- Live MBP-10 volume/cost is not bounded by our sparse historical windows; enable it only for the profiles that need it.
- Parent-symbol front-month election currently depends on 1m volume. The MBP feature should ignore records until the elected front-month is known.
- Contract rounding can erase `0.5x` on small risk/large stop trades. Persist both requested and actual risk weights.
- Candidate parity is the main blocker. Infrastructure can land before exact pure-1m promotion, but promotion cannot.

## Recommendation

Implement phases 1-3 first behind disabled-by-default config flags. This is the highest-leverage next step because it turns the survivor from a CSV overlay into a live-measurable feature without committing capital or fetching new historical DataBento files. The first exact replay should use the existing scored feature CSVs; broaden MBP-10 historical replay only after the live feature path is mechanically sound.
