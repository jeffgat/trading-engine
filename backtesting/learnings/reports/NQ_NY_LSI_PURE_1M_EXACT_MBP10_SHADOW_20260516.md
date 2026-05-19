# NQ NY LSI Pure 1m Exact MBP-10 Shadow Replay - 2026-05-16

## Objective

Validate the next no-new-cost promotion gate for the pure 1m order-book velocity survivor: inject locally replayed MBP-10 feature decisions into the exact live execution engine in shadow mode.

This is still not a live/paper run. It verifies that the exact replay path can consume the same decision interface that live MBP-10 streaming will use, persist the metadata, and report the quantity-sizing effect without changing executed quantities.

## Inputs

- Candidate: `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`
- Execution profile: `NQ_LSI_PURE_1M_OBV_SHADOW`
- Execution session: `NQ_NY_LSI_PURE_1M`
- Feature: `confirm_last_10s_mid_velocity_ticks_per_second`
- Sizing ladder: `0.5x / 1.0x / 1.5x`
- Frozen thresholds: low `< -0.322`, mid `[-0.322, 0.912)`, high `>= 0.912`
- Source decisions: `backtesting/data/results/nq_ny_lsi_pure_1m_velocity_mbp10_replay_validation_20260516/replay_validation.csv`
- Output: `backtesting/data/results/nq_ny_lsi_pure_1m_exact_mbp10_shadow_20260516/`
- DataBento fetches: `0`

## Result

Exact live-engine replay with shadow MBP-10 decisions:

- Trades: `21`
- Date match versus MBP-10 replay rows: `true`
- Active dynamic-sizing decisions: `21`
- Fallback decisions: `0`
- Tier counts: high `11`, low `6`, mid `4`

Exact baseline:

- Total R: `+5.50R`
- Avg R: `0.262R`
- PF: `1.79`
- Max DD: `-1.50R`

Shadow weighted read:

- Weighted R: `+9.25R`
- Weighted avg R: `0.440R`
- Weighted PF: `2.42`
- Weighted max DD: `-1.50R`
- Delta versus exact baseline: `+3.75R`

## Implementation Notes

- `run_profile_backtest_sync` now accepts session-scoped `dynamic_sizing_providers` and a `dynamic_sizing_shadow` flag.
- `ScoredFeatureLookupProvider` can now replay MBP-10 validation CSVs that contain `actual_feature_value` rather than only research `feature_value`.
- `ReplayRecorder` includes `entry_context` in exact replay trade exports, so shadow sizing metadata is auditable per trade.
- New script: `backtesting/scripts/replay_nq_lsi_pure_1m_exact_mbp10_shadow.py`

## Interpretation

This is a stronger promotion checkpoint than the earlier CSV replay because the sizing decision now passes through the exact live `LSIEngine` trade lifecycle. The result preserves the same 21-trade exact execution set and shows the MBP-10 sizing ladder would have improved the live-style exact replay from `+5.50R` to `+9.25R`.

Status: still shadow-only. The next blocker is a live/paper shadow run with real-time MBP-10 enabled intentionally, then comparison of live feature values against offline replay windows before any quantity-changing deployment.
