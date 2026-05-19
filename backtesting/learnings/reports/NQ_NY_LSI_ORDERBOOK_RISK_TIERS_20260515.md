# NQ NY LSI Order-Book Risk-Tier Replay

- Objective: continue the promising order-book momentum signals as frozen risk-tier overlays, not hard filters.
- Input feature-lab directory: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_orderbook_feature_lab_20260514`.
- Output directory: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_orderbook_risk_tiers_20260515`.
- Thresholds: validation-only terciles for each selected candidate/feature pair.
- Primary sizing: low tercile `0.5x`, middle tercile `1.0x`, high tercile `1.5x`.
- DataBento: no fetch; this consumes existing local feature CSVs.
- Deployability: `research_only` until live MBP-10 feature streaming and execution-engine sizing support exist.

## Primary Frozen Replay

| Overlay | Feature | Val Base R | Val Tier R | Holdout Base R | Holdout Tier R | Holdout Avg R | Per-1x Avg R | Tiers | Read |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `allDOW_additive_pre_confirm_pressure` | `pre_confirm_30s_pressure_score` | 15.57 | 19.07 | 13.10 | 20.05 | 0.352 | 0.311 | 2 | supported_after_exposure_normalization |
| `hourly_3m_absorption_release_first10` | `absorption_release_confirm_first_10s_score` | 9.43 | 14.15 | 12.17 | 18.26 | 0.397 | 0.265 | 1 | exposure_only_no_tier_discrimination |
| `hourly_3m_absorption_release_last10` | `absorption_release_confirm_last_10s_score` | 9.43 | 14.15 | 12.17 | 18.26 | 0.397 | 0.265 | 1 | exposure_only_no_tier_discrimination |
| `noThu_additive_pre_confirm_pressure` | `pre_confirm_30s_pressure_score` | 19.72 | 23.78 | 10.48 | 15.84 | 0.344 | 0.302 | 2 | supported_after_exposure_normalization |
| `pure_1m_long_confirm_last_velocity` | `confirm_last_10s_mid_velocity_ticks_per_second` | 10.55 | 11.63 | 4.84 | 8.33 | 0.397 | 0.355 | 3 | supported_after_exposure_normalization |

## Holdout Stress Profiles

| Overlay | Profile | Base R | Tier R | Delta R | Avg R | Per-1x Avg R | DD | PF |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `allDOW_additive_pre_confirm_pressure` | `tier_0_1_1p5` | 13.10 | 20.05 | 6.94 | 0.352 | 0.311 | -5.57 | 1.955 |
| `allDOW_additive_pre_confirm_pressure` | `tier_0p5_1_1p5` | 13.10 | 20.05 | 6.94 | 0.352 | 0.311 | -5.57 | 1.955 |
| `allDOW_additive_pre_confirm_pressure` | `tier_0p5_1_2` | 13.10 | 26.99 | 13.89 | 0.473 | 0.375 | -6.07 | 2.227 |
| `allDOW_additive_pre_confirm_pressure` | `tier_0p75_1_1p25` | 13.10 | 16.57 | 3.47 | 0.291 | 0.273 | -5.32 | 1.809 |
| `hourly_3m_absorption_release_first10` | `tier_0_1_1p5` | 12.17 | 18.26 | 6.09 | 0.397 | 0.265 | -7.67 | 1.733 |
| `hourly_3m_absorption_release_first10` | `tier_0p5_1_1p5` | 12.17 | 18.26 | 6.09 | 0.397 | 0.265 | -7.67 | 1.733 |
| `hourly_3m_absorption_release_first10` | `tier_0p5_1_2` | 12.17 | 24.34 | 12.17 | 0.529 | 0.265 | -10.22 | 1.733 |
| `hourly_3m_absorption_release_first10` | `tier_0p75_1_1p25` | 12.17 | 15.21 | 3.04 | 0.331 | 0.265 | -6.39 | 1.733 |
| `hourly_3m_absorption_release_last10` | `tier_0_1_1p5` | 12.17 | 18.26 | 6.09 | 0.397 | 0.265 | -7.67 | 1.733 |
| `hourly_3m_absorption_release_last10` | `tier_0p5_1_1p5` | 12.17 | 18.26 | 6.09 | 0.397 | 0.265 | -7.67 | 1.733 |
| `hourly_3m_absorption_release_last10` | `tier_0p5_1_2` | 12.17 | 24.34 | 12.17 | 0.529 | 0.265 | -10.22 | 1.733 |
| `hourly_3m_absorption_release_last10` | `tier_0p75_1_1p25` | 12.17 | 15.21 | 3.04 | 0.331 | 0.265 | -6.39 | 1.733 |
| `noThu_additive_pre_confirm_pressure` | `tier_0_1_1p5` | 10.48 | 15.84 | 5.36 | 0.344 | 0.302 | -4.63 | 1.932 |
| `noThu_additive_pre_confirm_pressure` | `tier_0p5_1_1p5` | 10.48 | 15.84 | 5.36 | 0.344 | 0.302 | -4.63 | 1.932 |
| `noThu_additive_pre_confirm_pressure` | `tier_0p5_1_2` | 10.48 | 21.21 | 10.73 | 0.461 | 0.359 | -5.07 | 2.178 |
| `noThu_additive_pre_confirm_pressure` | `tier_0p75_1_1p25` | 10.48 | 13.16 | 2.68 | 0.286 | 0.267 | -4.88 | 1.798 |
| `pure_1m_long_confirm_last_velocity` | `tier_0_1_1p5` | 4.84 | 8.62 | 3.78 | 0.575 | 0.420 | -1.50 | 2.724 |
| `pure_1m_long_confirm_last_velocity` | `tier_0p5_1_1p5` | 4.84 | 8.33 | 3.49 | 0.397 | 0.355 | -1.50 | 2.282 |
| `pure_1m_long_confirm_last_velocity` | `tier_0p5_1_2` | 4.84 | 11.54 | 6.70 | 0.549 | 0.398 | -2.00 | 2.538 |
| `pure_1m_long_confirm_last_velocity` | `tier_0p75_1_1p25` | 4.84 | 6.59 | 1.75 | 0.314 | 0.296 | -1.58 | 1.976 |

## 3m Absorption-Release Positive-Only Check

The plain terciles are degenerate for 3m because most validation values are zero. This rescue check sizes zero/nonpositive values at 0.5x, then tiers only positive validation values.

| Feature | Val Base R | Val Tier R | Val Per-1x Avg R | Holdout Base R | Holdout Tier R | Holdout Per-1x Avg R | Avg Weight | Combined Read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `absorption_release_confirm_first_10s_score` | 9.43 | 3.00 | 0.035 | 12.17 | 7.65 | 0.266 | 0.62 | validation_failed |
| `absorption_release_confirm_full_score` | 9.43 | 16.37 | 0.139 | 12.17 | 9.90 | 0.296 | 0.73 | mild_after_exposure_normalization |
| `absorption_release_confirm_last_10s_score` | 9.43 | 8.83 | 0.098 | 12.17 | 8.02 | 0.279 | 0.62 | mild_after_exposure_normalization |

## Holdout Tier Breakdown

| Overlay | Tier | Trades | Weight | Feature Range | Base Avg R | Weighted R |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `allDOW_additive_pre_confirm_pressure` | mid | 42 | 1.00 | 0.0000-0.0880 | -0.019 | -0.78 |
| `allDOW_additive_pre_confirm_pressure` | high | 15 | 1.50 | 0.0904-0.2256 | 0.926 | 20.83 |
| `hourly_3m_absorption_release_first10` | high | 46 | 1.50 | 0.0000-0.0026 | 0.265 | 18.26 |
| `hourly_3m_absorption_release_last10` | high | 46 | 1.50 | -0.0000-0.0465 | 0.265 | 18.26 |
| `noThu_additive_pre_confirm_pressure` | mid | 33 | 1.00 | 0.0000-0.0880 | -0.008 | -0.25 |
| `noThu_additive_pre_confirm_pressure` | high | 13 | 1.50 | 0.0904-0.2256 | 0.825 | 16.09 |
| `pure_1m_long_confirm_last_velocity` | low | 6 | 0.50 | -2.9500--0.7000 | -0.095 | -0.29 |
| `pure_1m_long_confirm_last_velocity` | mid | 4 | 1.00 | -0.2500-0.9000 | -0.250 | -1.00 |
| `pure_1m_long_confirm_last_velocity` | high | 11 | 1.50 | 0.9500-3.0000 | 0.583 | 9.62 |

## Frozen Thresholds

| Overlay | Validation Rows | Low < q33 | High >= q66 | Feature Median |
| --- | ---: | ---: | ---: | ---: |
| `allDOW_additive_pre_confirm_pressure` | 104 | 0.000000 | 0.088511 | 0.039485 |
| `hourly_3m_absorption_release_first10` | 139 | 0.000000 | 0.000000 | 0.000000 |
| `hourly_3m_absorption_release_last10` | 139 | 0.000000 | 0.000000 | 0.000000 |
| `noThu_additive_pre_confirm_pressure` | 83 | 0.000000 | 0.089212 | 0.039111 |
| `pure_1m_long_confirm_last_velocity` | 33 | -0.322000 | 0.912000 | 0.100000 |

## Interpretation

- This packet is a fixed follow-up on selected risk-tier families, not a fresh feature search.
- The allDOW and noThursday overlays are overlapping variants of the same 1m additive family; do not combine them naively.
- The 3m absorption-release first-10s and last-10s plain tercile overlays are exposure-only. The positive-only rescue check demotes first-10s, leaves full/last-10s only mildly positive per 1x risk, and reduces absolute holdout R because average risk drops.
- Any deployment path requires implementing these features causally in the live engine before signal close and replaying exact execution with dynamic sizing.