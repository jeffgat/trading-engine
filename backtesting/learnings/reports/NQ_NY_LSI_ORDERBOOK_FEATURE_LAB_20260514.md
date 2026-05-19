# NQ NY LSI Order-Book Feature Lab

- Objective: retest the discretionary momentum idea with smaller order-book windows instead of one blunt confirmation-bar aggregate.
- Data source: existing DataBento MBP-10 DBN files only; this run does not refetch data.
- Validation CSV: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_orderbook_impulse_validation_full_20260514/trade_orderbook_impulse.csv`.
- Holdout CSV: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_orderbook_impulse_20260513/trade_orderbook_impulse.csv`.
- Output directory: `data/results/nq_ny_lsi_orderbook_feature_lab_20260514`.
- Minimum validation trades per tested rule: `20`.
- Validation feature coverage: `537/544` rows.
- Holdout feature coverage: `253/255` rows.
- Entry-safe features end no later than the signal/confirmation close. Post-confirm features are diagnostics only.

## Validation-Selected Entry-Safe Rules

| Candidate | Rule | Feature | Val Trades | Val Avg R | Val R | Holdout Trades | Holdout Avg R | Holdout R | Holdout Delta Avg R |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `confirm_first_10s_aligned_run_volume_ratio` | 32 | 0.468 | 14.99 | 16 | 0.160 | 2.57 | -0.069 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `confirm_first_10s_aligned_run_volume_ratio` | 25 | 0.454 | 11.36 | 12 | 0.339 | 4.07 | 0.111 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `threshold` | `confirm_full_aligned_depth_imbalance_3_mean` | 28 | 0.544 | 15.24 | 14 | 0.090 | 1.26 | -0.174 |
| `htf_lsi_2m_anchor` | `threshold` | `pre_confirm_30s_mid_velocity_ratio` | 36 | 0.524 | 18.88 | 13 | -0.458 | -5.96 | -0.472 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `threshold` | `pre_confirm_10s_aligned_depth_imbalance_3_mean` | 26 | 0.406 | 10.55 | 13 | 0.330 | 4.30 | 0.100 |

## Entry-Safe Holdout Survivors

These rows are diagnostic because they are sorted after seeing holdout, but they tell us which feature families deserve the next frozen test.

| Candidate | Rule | Feature | Val Avg R | Holdout Trades | Holdout Avg R | Holdout Delta Avg R | Holdout PF |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `pre_confirm_30s_aligned_burst_5s_ratio` | 0.440 | 8 | 1.019 | 0.789 | inf |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `pre_confirm_10s_aligned_depth_imbalance_3_delta` | 0.467 | 8 | 0.957 | 0.727 | 8.656 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `pre_confirm_30s_pressure_score` | 0.363 | 8 | 0.836 | 0.606 | 7.684 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `confirm_last_10s_counter_suppression_score` | 0.211 | 8 | 0.807 | 0.577 | 7.452 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `pre_confirm_30s_aligned_burst_5s_ratio` | 0.243 | 16 | 0.756 | 0.526 | 7.047 |
| `htf_lsi_2m_anchor` | `threshold` | `pre_confirm_10s_aligned_depth_imbalance_3_delta` | 0.250 | 15 | 0.539 | 0.525 | 2.470 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `threshold` | `pre_confirm_10s_aligned_burst_5s_ratio` | 0.315 | 9 | 0.770 | 0.505 | 7.929 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `pre_confirm_30s_pressure_score` | 0.245 | 11 | 0.699 | 0.471 | 4.842 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `confirm_first_10s_aligned_micro_skew_ticks_end` | 0.221 | 15 | 0.669 | 0.439 | 4.346 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `pre_confirm_30s_counter_suppression_score` | 0.297 | 8 | 0.647 | 0.417 | 3.587 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `confirm_last_10s_counter_suppression_score` | 0.334 | 9 | 0.606 | 0.378 | 3.726 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `confirm_first_10s_aligned_micro_skew_ticks_end` | 0.185 | 19 | 0.606 | 0.376 | 3.878 |

## Entry-Safe Risk-Tier Survivors

These apply 0.5x / 1.0x / 1.5x risk by validation terciles, so they keep trade count instead of hard-filtering entries.

| Candidate | Feature | Val Avg R | Holdout Trades | Holdout Avg R | Holdout Delta Avg R | Holdout R |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_last_10s_mid_velocity_ticks_per_second` | 0.353 | 21 | 0.397 | 0.166 | 8.33 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_last_10s_mid_move_ticks` | 0.353 | 21 | 0.397 | 0.166 | 8.33 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_last_10s_mid_velocity_ratio` | 0.420 | 21 | 0.375 | 0.145 | 7.88 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_last_10s_release_score` | 0.422 | 21 | 0.367 | 0.137 | 7.71 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_last_10s_burst_release_score` | 0.422 | 21 | 0.367 | 0.137 | 7.71 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_last_10s_monotonic_efficiency` | 0.404 | 21 | 0.363 | 0.133 | 7.63 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `absorption_release_confirm_first_10s_score` | 0.102 | 46 | 0.397 | 0.132 | 18.26 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `absorption_release_confirm_last_10s_score` | 0.102 | 46 | 0.397 | 0.132 | 18.26 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_last_10s_aligned_depth_imbalance_3_delta` | 0.391 | 21 | 0.360 | 0.130 | 7.57 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `pre_confirm_30s_pressure_score` | 0.183 | 57 | 0.352 | 0.122 | 20.05 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `pre_confirm_30s_pressure_score` | 0.287 | 46 | 0.344 | 0.117 | 15.84 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `absorption_release_confirm_first_10s_score` | 0.480 | 21 | 0.346 | 0.115 | 7.26 |

## Post-Confirm Diagnostics

These are not entry filters. They are included to check whether later follow-through matches the manual read of a strong reversal.

| Candidate | Rule | Feature | Val Avg R | Holdout Trades | Holdout Avg R | Holdout Delta Avg R |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_mid_velocity_ticks_per_second` | 0.449 | 19 | 0.810 | 0.582 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_mid_move_ticks` | 0.449 | 19 | 0.810 | 0.582 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_release_score` | 0.422 | 17 | 0.793 | 0.565 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_burst_release_score` | 0.422 | 17 | 0.793 | 0.565 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_monotonic_efficiency` | 0.431 | 17 | 0.782 | 0.554 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_mid_velocity_ticks_per_second` | 0.373 | 22 | 0.750 | 0.522 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_mid_move_ticks` | 0.373 | 22 | 0.750 | 0.522 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_mid_velocity_ratio` | 0.342 | 22 | 0.750 | 0.522 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_monotonic_efficiency` | 0.342 | 22 | 0.750 | 0.522 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `threshold` | `post_confirm_30s_mid_velocity_ratio` | 0.491 | 16 | 0.743 | 0.515 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `post_confirm_10s_aligned_depth_imbalance_3_mean` | 0.184 | 10 | 0.740 | 0.510 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `threshold` | `post_confirm_30s_mid_velocity_ratio` | 0.338 | 13 | 0.730 | 0.500 |

## Baselines

| Period | Candidate | Rows | Scored | Coverage | Scored PF | Scored Avg R | Scored R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 58 | 57 | 98.3% | 1.655 | 0.230 | 13.10 |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 47 | 46 | 97.9% | 1.655 | 0.228 | 10.48 |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | 46 | 46 | 100.0% | 1.733 | 0.265 | 12.17 |
| holdout | `htf_lsi_2m_anchor` | 83 | 83 | 100.0% | 1.028 | 0.014 | 1.17 |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 21 | 21 | 100.0% | 1.692 | 0.231 | 4.84 |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 106 | 104 | 98.1% | 1.362 | 0.150 | 15.57 |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 85 | 83 | 97.6% | 1.616 | 0.238 | 19.72 |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | 140 | 139 | 99.3% | 1.145 | 0.068 | 9.43 |
| validation | `htf_lsi_2m_anchor` | 180 | 178 | 98.9% | 1.245 | 0.121 | 21.49 |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 33 | 33 | 100.0% | 2.055 | 0.320 | 10.55 |

## Interpretation Guardrails

- Treat the validation-selected table as the honest replay read.
- Treat the holdout-survivor table as feature-family discovery only; it should seed a smaller frozen follow-up, not a production rule.
- Post-confirm rows can validate the discretionary intuition, but they are not causal entry gates unless converted into a later add/hold/scale rule.