# NQ NY LSI Broad Discretionary Challenger Matrix - 2026-05-17

## Objective

Extend the three discretionary momentum challenger families beyond the pure 1m survivor and include the current 5m HTF-LSI path where no-extra-fetch data exists.

- DataBento fetches: `0`.
- Thresholds: validation terciles frozen per candidate/feature and replayed on holdout.
- Primary sizing: `0.5x / 1.0x / 1.5x`.
- 5m caveat: no local MBP-10 windows exist for the current 5m path, so 5m is price-action only in this pass.

## Coverage

| Candidate | TF | Validation | Holdout | OB Rows | Tested Features | OB Features | Price Features |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `1m` | 104 | 57 | 161 | 14 | 8 | 6 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `1m` | 83 | 46 | 129 | 14 | 8 | 6 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `3m` | 139 | 46 | 185 | 14 | 8 | 6 |
| `htf_lsi_2m_anchor` | `2m` | 178 | 83 | 261 | 14 | 8 | 6 |
| `htf_lsi_5m_lag24_current` | `5m` | 91 | 32 | 0 | 6 | 0 | 6 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `1m` | 33 | 21 | 54 | 14 | 8 | 6 |

## Best Holdout Read By Candidate

| Candidate | Branch | Feature | Holdout Weighted R | Holdout Avg | PF | Max DD | Holdout Read | Validation Read |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `current_orderbook_survivor` | `pre_confirm_30s_pressure_score` | 20.05 | 0.352 | 1.95 | -5.57 | `supported_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `current_orderbook_survivor` | `pre_confirm_30s_pressure_score` | 15.84 | 0.344 | 1.93 | -4.63 | `supported_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `add_3m_hourly_atr12p5_b3_a7p5` | `absorption_then_release` | `trapped_reversal_confirm_score` | 17.34 | 0.377 | 2.00 | -5.67 | `supported_after_exposure_normalization` | `supported_after_exposure_normalization` |
| `htf_lsi_2m_anchor` | `current_orderbook_survivor` | `confirm_last_10s_mid_velocity_ticks_per_second` | 4.93 | 0.059 | 1.11 | -14.58 | `mild_after_exposure_normalization` | `supported_after_exposure_normalization` |
| `htf_lsi_5m_lag24_current` | `reversal_violence_relative_to_day` | `price_violence_signal_bar_score` | 13.08 | 0.409 | 2.07 | -4.00 | `mild_after_exposure_normalization` | `failed_after_exposure_normalization` |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `liquidity_vacuum_book_pull` | `ob_vacuum_confirm_last_10s_score` | 7.02 | 0.334 | 2.17 | -2.25 | `supported_after_exposure_normalization` | `supported_after_exposure_normalization` |

## Current Order-Book Path Rows

| Candidate | Feature | Holdout Baseline R | Holdout Weighted R | Holdout Read | Validation Read |
| --- | --- | ---: | ---: | --- | --- |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `pre_confirm_30s_pressure_score` | 13.10 | 20.05 | `supported_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `confirm_last_10s_mid_velocity_ticks_per_second` | 13.10 | 14.23 | `mild_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `pre_confirm_30s_pressure_score` | 10.48 | 15.84 | `supported_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `confirm_last_10s_mid_velocity_ticks_per_second` | 10.48 | 12.33 | `mild_after_exposure_normalization` | `failed_after_exposure_normalization` |
| `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_last_10s_mid_velocity_ticks_per_second` | 12.17 | 13.18 | `mild_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `add_3m_hourly_atr12p5_b3_a7p5` | `pre_confirm_30s_pressure_score` | 12.17 | 12.01 | `failed_after_exposure_normalization` | `failed_after_exposure_normalization` |
| `htf_lsi_2m_anchor` | `confirm_last_10s_mid_velocity_ticks_per_second` | 1.17 | 4.93 | `mild_after_exposure_normalization` | `supported_after_exposure_normalization` |
| `htf_lsi_2m_anchor` | `pre_confirm_30s_pressure_score` | 1.17 | -1.51 | `failed_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_last_10s_mid_velocity_ticks_per_second` | 4.84 | 8.33 | `supported_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `pre_confirm_30s_pressure_score` | 4.84 | 6.05 | `supported_after_exposure_normalization` | `failed_after_exposure_normalization` |

## Stable Supported Rows

| Candidate | Branch | Feature | Holdout Weighted R | Holdout Per-1x Avg Delta | Validation Weighted R |
| --- | --- | --- | ---: | ---: | ---: |
| `add_3m_hourly_atr12p5_b3_a7p5` | `absorption_then_release` | `trapped_reversal_confirm_score` | 17.34 | 0.079 | 20.93 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `liquidity_vacuum_book_pull` | `ob_vacuum_confirm_last_10s_score` | 7.02 | 0.120 | 12.31 |

## Interpretation

The strict stable-survivor view is intentionally conservative: it requires exposure-normalized support on both validation and holdout. Under that rule only 3m trapped reversal and pure 1m liquidity-vacuum survive. The incumbent 1m additive pressure and pure 1m velocity rows still matter because they win or nearly win absolute holdout R, but their validation improvement is milder under this particular per-1x normalization.

The current 5m HTF-LSI path did not produce a stable no-fetch price-action overlay. Signal-bar price violence was mildly positive on holdout, but failed validation, and the sweep/reclaim scores were exposure-only because the validation thresholds were zero-inflated. Order-book absorption/vacuum on 5m remains untested until MBP-10 windows are fetched for that branch.

This is still a research-only matrix. Rows that require MBP-10 features are not live-native until the execution path supports the exact feature and passes exact replay / shadow validation. The 5m branch needs a separate MBP-10 fetch before order-book absorption or liquidity-vacuum can be tested on it.
