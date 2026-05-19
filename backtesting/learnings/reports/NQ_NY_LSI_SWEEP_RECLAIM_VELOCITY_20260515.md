# NQ NY LSI Sweep-Reclaim Velocity Replay

- Objective: test no-extra-fetch price-action proxies for the discretionary idea that violent sweep/reclaim reversals are stronger.
- Data: existing frozen LSI candidate trade CSVs plus local `NQ_1s.parquet`; no DataBento fetch.
- Thresholds: validation-only terciles by candidate and feature, replayed unchanged on holdout.
- Primary sizing profile: low `0.5x`, mid `1.0x`, high `1.5x`.
- Deployability: `research_only` until implemented in the live/exact execution path, but the data requirement is 1s price bars rather than paid MBP-10 depth.

## Best Primary Holdout Reads

| Candidate | Feature | Timing | Val Base R | Val Tier R | Holdout Base R | Holdout Tier R | Holdout Per-1x Avg | Read |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `add_3m_hourly_atr12p5_b3_a7p5` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 9.93 | 21.68 | 12.17 | 17.34 | 0.343 | `supported_after_exposure_normalization` |
| `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 9.93 | 17.33 | 12.17 | 16.06 | 0.309 | `mild_after_exposure_normalization` |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `post_reclaim_60s_score` | `post_confirm_management_only` | 20.30 | 24.76 | 12.05 | 14.71 | 0.270 | `mild_after_exposure_normalization` |
| `htf_lsi_2m_anchor` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 22.92 | 14.60 | 1.17 | 1.97 | 0.022 | `mild_after_exposure_normalization` |
| `htf_lsi_2m_anchor` | `post_reclaim_30s_score` | `post_confirm_management_only` | 22.92 | 25.30 | 1.17 | 1.81 | 0.018 | `mild_after_exposure_normalization` |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 10.55 | 15.82 | 4.84 | 7.26 | 0.231 | `exposure_only_no_tier_discrimination` |
| `htf_lsi_2m_anchor` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 22.92 | 34.38 | 1.17 | 1.76 | 0.014 | `exposure_only_no_tier_discrimination` |
| `add_3m_hourly_atr12p5_b3_a7p5` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 9.93 | 14.90 | 12.17 | 18.26 | 0.265 | `exposure_only_no_tier_discrimination` |
| `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_score` | `causal_at_signal_close` | 9.93 | 15.34 | 12.17 | 14.74 | 0.263 | `failed_after_exposure_normalization` |
| `add_3m_hourly_atr12p5_b3_a7p5` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 9.93 | 12.35 | 12.17 | 14.33 | 0.261 | `failed_after_exposure_normalization` |
| `add_3m_hourly_atr12p5_b3_a7p5` | `post_reclaim_30s_score` | `post_confirm_management_only` | 9.93 | 17.83 | 12.17 | 14.08 | 0.258 | `failed_after_exposure_normalization` |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `post_reclaim_60s_score` | `post_confirm_management_only` | 16.14 | 19.80 | 14.67 | 16.63 | 0.246 | `failed_after_exposure_normalization` |

## Primary Summary

| Period | Candidate | Feature | Timing | Trades | Base R | Tier R | Delta R | Base Avg | Per-1x Avg | Tiers | Read |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `post_reclaim_60s_score` | `post_confirm_management_only` | 58 | 14.67 | 16.63 | 1.95 | 0.253 | 0.246 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 58 | 14.67 | 13.04 | -1.63 | 0.253 | 0.235 | 3 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 58 | 14.67 | 15.57 | 0.90 | 0.253 | 0.234 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `post_reclaim_30s_score` | `post_confirm_management_only` | 58 | 14.67 | 15.36 | 0.68 | 0.253 | 0.233 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `confirm_reclaim_score` | `causal_at_signal_close` | 58 | 14.67 | 15.05 | 0.38 | 0.253 | 0.226 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 58 | 14.67 | 13.56 | -1.11 | 0.253 | 0.226 | 3 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 58 | 14.67 | 11.29 | -3.38 | 0.253 | 0.226 | 3 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 58 | 14.67 | 12.75 | -1.92 | 0.253 | 0.226 | 3 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `post_reclaim_60s_score` | `post_confirm_management_only` | 47 | 12.05 | 14.71 | 2.66 | 0.256 | 0.270 | 2 | `mild_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `confirm_reclaim_score` | `causal_at_signal_close` | 47 | 12.05 | 12.94 | 0.89 | 0.256 | 0.244 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `post_reclaim_30s_score` | `post_confirm_management_only` | 47 | 12.05 | 13.23 | 1.18 | 0.256 | 0.243 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 47 | 12.05 | 11.67 | -0.38 | 0.256 | 0.238 | 3 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 47 | 12.05 | 12.66 | 0.61 | 0.256 | 0.232 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 47 | 12.05 | 9.11 | -2.94 | 0.256 | 0.219 | 3 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 47 | 12.05 | 9.61 | -2.44 | 0.256 | 0.211 | 3 | `failed_after_exposure_normalization` |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 47 | 12.05 | 9.06 | -2.99 | 0.256 | 0.199 | 3 | `failed_after_exposure_normalization` |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 46 | 12.17 | 17.34 | 5.17 | 0.265 | 0.343 | 3 | `supported_after_exposure_normalization` |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 46 | 12.17 | 16.06 | 3.89 | 0.265 | 0.309 | 3 | `mild_after_exposure_normalization` |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 46 | 12.17 | 18.26 | 6.09 | 0.265 | 0.265 | 1 | `exposure_only_no_tier_discrimination` |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_score` | `causal_at_signal_close` | 46 | 12.17 | 14.74 | 2.57 | 0.265 | 0.263 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 46 | 12.17 | 14.33 | 2.16 | 0.265 | 0.261 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | `post_reclaim_30s_score` | `post_confirm_management_only` | 46 | 12.17 | 14.08 | 1.91 | 0.265 | 0.258 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | `post_reclaim_60s_score` | `post_confirm_management_only` | 46 | 12.17 | 13.74 | 1.57 | 0.265 | 0.243 | 2 | `failed_after_exposure_normalization` |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 46 | 12.17 | 11.72 | -0.46 | 0.265 | 0.237 | 3 | `failed_after_exposure_normalization` |
| holdout | `htf_lsi_2m_anchor` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 83 | 1.17 | 1.97 | 0.79 | 0.014 | 0.022 | 3 | `mild_after_exposure_normalization` |
| holdout | `htf_lsi_2m_anchor` | `post_reclaim_30s_score` | `post_confirm_management_only` | 83 | 1.17 | 1.81 | 0.64 | 0.014 | 0.018 | 2 | `mild_after_exposure_normalization` |
| holdout | `htf_lsi_2m_anchor` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 83 | 1.17 | 1.76 | 0.59 | 0.014 | 0.014 | 1 | `exposure_only_no_tier_discrimination` |
| holdout | `htf_lsi_2m_anchor` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 83 | 1.17 | 0.23 | -0.95 | 0.014 | 0.003 | 3 | `failed_after_exposure_normalization` |
| holdout | `htf_lsi_2m_anchor` | `post_reclaim_60s_score` | `post_confirm_management_only` | 83 | 1.17 | 0.11 | -1.07 | 0.014 | 0.001 | 2 | `failed_after_exposure_normalization` |
| holdout | `htf_lsi_2m_anchor` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 83 | 1.17 | -0.70 | -1.87 | 0.014 | -0.007 | 2 | `failed_after_exposure_normalization` |
| holdout | `htf_lsi_2m_anchor` | `confirm_reclaim_score` | `causal_at_signal_close` | 83 | 1.17 | -0.98 | -2.15 | 0.014 | -0.010 | 2 | `failed_after_exposure_normalization` |
| holdout | `htf_lsi_2m_anchor` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 83 | 1.17 | -1.03 | -2.20 | 0.014 | -0.012 | 3 | `failed_after_exposure_normalization` |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 21 | 4.84 | 7.26 | 2.42 | 0.231 | 0.231 | 1 | `exposure_only_no_tier_discrimination` |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 21 | 4.84 | 4.89 | 0.05 | 0.231 | 0.200 | 2 | `failed_after_exposure_normalization` |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `post_reclaim_60s_score` | `post_confirm_management_only` | 21 | 4.84 | 5.03 | 0.19 | 0.231 | 0.197 | 2 | `failed_after_exposure_normalization` |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `post_reclaim_30s_score` | `post_confirm_management_only` | 21 | 4.84 | 4.01 | -0.83 | 0.231 | 0.167 | 2 | `failed_after_exposure_normalization` |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 21 | 4.84 | 3.76 | -1.08 | 0.231 | 0.160 | 2 | `failed_after_exposure_normalization` |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_reclaim_score` | `causal_at_signal_close` | 21 | 4.84 | 3.51 | -1.33 | 0.231 | 0.143 | 2 | `failed_after_exposure_normalization` |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 21 | 4.84 | 3.51 | -1.33 | 0.231 | 0.143 | 2 | `failed_after_exposure_normalization` |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 21 | 4.84 | 2.51 | -2.33 | 0.231 | 0.107 | 3 | `failed_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 106 | 16.14 | 22.81 | 6.67 | 0.152 | 0.214 | 3 | `supported_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 106 | 16.14 | 20.24 | 4.11 | 0.152 | 0.190 | 3 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 106 | 16.14 | 19.59 | 3.46 | 0.152 | 0.184 | 3 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 106 | 16.14 | 18.17 | 2.03 | 0.152 | 0.160 | 3 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `post_reclaim_60s_score` | `post_confirm_management_only` | 106 | 16.14 | 19.80 | 3.66 | 0.152 | 0.160 | 2 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 106 | 16.14 | 19.16 | 3.02 | 0.152 | 0.155 | 2 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `confirm_reclaim_score` | `causal_at_signal_close` | 106 | 16.14 | 18.36 | 2.22 | 0.152 | 0.148 | 2 | `failed_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `post_reclaim_30s_score` | `post_confirm_management_only` | 106 | 16.14 | 18.35 | 2.21 | 0.152 | 0.148 | 2 | `failed_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 85 | 20.30 | 24.97 | 4.68 | 0.239 | 0.270 | 3 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 85 | 20.30 | 22.94 | 2.65 | 0.239 | 0.268 | 3 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 85 | 20.30 | 22.07 | 1.78 | 0.239 | 0.258 | 3 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 85 | 20.30 | 21.72 | 1.43 | 0.239 | 0.254 | 3 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `post_reclaim_60s_score` | `post_confirm_management_only` | 85 | 20.30 | 24.76 | 4.46 | 0.239 | 0.249 | 2 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `confirm_reclaim_score` | `causal_at_signal_close` | 85 | 20.30 | 24.57 | 4.27 | 0.239 | 0.247 | 2 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 85 | 20.30 | 24.32 | 4.02 | 0.239 | 0.244 | 2 | `mild_after_exposure_normalization` |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `post_reclaim_30s_score` | `post_confirm_management_only` | 85 | 20.30 | 23.31 | 3.01 | 0.239 | 0.234 | 2 | `failed_after_exposure_normalization` |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 140 | 9.93 | 21.68 | 11.74 | 0.071 | 0.154 | 3 | `supported_after_exposure_normalization` |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 140 | 9.93 | 17.33 | 7.39 | 0.071 | 0.123 | 3 | `supported_after_exposure_normalization` |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | `post_reclaim_30s_score` | `post_confirm_management_only` | 140 | 9.93 | 17.83 | 7.89 | 0.071 | 0.109 | 2 | `mild_after_exposure_normalization` |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 140 | 9.93 | 14.51 | 4.57 | 0.071 | 0.102 | 3 | `mild_after_exposure_normalization` |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_score` | `causal_at_signal_close` | 140 | 9.93 | 15.34 | 5.40 | 0.071 | 0.094 | 2 | `mild_after_exposure_normalization` |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | `post_reclaim_60s_score` | `post_confirm_management_only` | 140 | 9.93 | 15.25 | 5.32 | 0.071 | 0.093 | 2 | `mild_after_exposure_normalization` |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 140 | 9.93 | 12.35 | 2.41 | 0.071 | 0.075 | 2 | `mild_after_exposure_normalization` |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 140 | 9.93 | 14.90 | 4.97 | 0.071 | 0.071 | 1 | `exposure_only_no_tier_discrimination` |
| validation | `htf_lsi_2m_anchor` | `post_reclaim_60s_score` | `post_confirm_management_only` | 180 | 22.92 | 27.25 | 4.33 | 0.127 | 0.129 | 2 | `mild_after_exposure_normalization` |
| validation | `htf_lsi_2m_anchor` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 180 | 22.92 | 34.38 | 11.46 | 0.127 | 0.127 | 1 | `exposure_only_no_tier_discrimination` |
| validation | `htf_lsi_2m_anchor` | `confirm_reclaim_score` | `causal_at_signal_close` | 180 | 22.92 | 26.29 | 3.37 | 0.127 | 0.125 | 2 | `failed_after_exposure_normalization` |
| validation | `htf_lsi_2m_anchor` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 180 | 22.92 | 22.10 | -0.81 | 0.127 | 0.122 | 3 | `failed_after_exposure_normalization` |
| validation | `htf_lsi_2m_anchor` | `post_reclaim_30s_score` | `post_confirm_management_only` | 180 | 22.92 | 25.30 | 2.38 | 0.127 | 0.120 | 2 | `failed_after_exposure_normalization` |
| validation | `htf_lsi_2m_anchor` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 180 | 22.92 | 24.86 | 1.94 | 0.127 | 0.118 | 2 | `failed_after_exposure_normalization` |
| validation | `htf_lsi_2m_anchor` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 180 | 22.92 | 16.78 | -6.14 | 0.127 | 0.092 | 3 | `failed_after_exposure_normalization` |
| validation | `htf_lsi_2m_anchor` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 180 | 22.92 | 14.60 | -8.32 | 0.127 | 0.081 | 3 | `failed_after_exposure_normalization` |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `pre_signal_reclaim_score` | `entry_safe_before_signal_bar` | 33 | 10.55 | 15.82 | 5.27 | 0.320 | 0.320 | 1 | `exposure_only_no_tier_discrimination` |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `compression_expansion_confirm_score` | `causal_at_signal_close` | 33 | 10.55 | 11.99 | 1.44 | 0.320 | 0.311 | 2 | `failed_after_exposure_normalization` |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `trapped_reversal_confirm_score` | `causal_at_signal_close` | 33 | 10.55 | 11.29 | 0.74 | 0.320 | 0.293 | 2 | `failed_after_exposure_normalization` |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `post_reclaim_30s_score` | `post_confirm_management_only` | 33 | 10.55 | 11.29 | 0.74 | 0.320 | 0.293 | 2 | `failed_after_exposure_normalization` |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_reclaim_velocity_ticks_per_second` | `causal_at_signal_close` | 33 | 10.55 | 11.27 | 0.72 | 0.320 | 0.293 | 2 | `failed_after_exposure_normalization` |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_reclaim_score` | `causal_at_signal_close` | 33 | 10.55 | 10.05 | -0.50 | 0.320 | 0.261 | 2 | `failed_after_exposure_normalization` |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `post_reclaim_60s_score` | `post_confirm_management_only` | 33 | 10.55 | 10.05 | -0.50 | 0.320 | 0.261 | 2 | `failed_after_exposure_normalization` |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `confirm_post_reclaim_move_ticks` | `causal_at_signal_close` | 33 | 10.55 | 8.65 | -1.90 | 0.320 | 0.240 | 3 | `failed_after_exposure_normalization` |

## Holdout Tier Breakdown For Best Reads

| Candidate | Feature | Tier | Trades | Feature Range | Base Avg R | Base R | Weight | Weighted R |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `post_reclaim_60s_score` | mid | 32 | 0.000-2.587 | 0.210 | 6.72 | 1.00 | 6.72 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `post_reclaim_60s_score` | high | 15 | 2.859-84.402 | 0.355 | 5.33 | 1.50 | 7.99 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_velocity_ticks_per_second` | low | 13 | 0.000-0.000 | 0.075 | 0.97 | 0.50 | 0.49 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_velocity_ticks_per_second` | mid | 8 | 0.103-0.362 | 0.306 | 2.44 | 1.00 | 2.44 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `confirm_reclaim_velocity_ticks_per_second` | high | 25 | 0.401-8.083 | 0.350 | 8.75 | 1.50 | 13.13 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `trapped_reversal_confirm_score` | low | 13 | 0.000-0.000 | 0.075 | 0.97 | 0.50 | 0.49 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `trapped_reversal_confirm_score` | mid | 11 | 0.238-3.057 | -0.010 | -0.11 | 1.00 | -0.11 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `trapped_reversal_confirm_score` | high | 22 | 4.190-192.702 | 0.514 | 11.31 | 1.50 | 16.96 |

## Orderbook Relationship Check

| Candidate | Orderbook Feature | Price Feature | N | Pearson | Spearman |
| --- | --- | --- | ---: | ---: | ---: |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `pre_confirm_30s_pressure_score` | `post_reclaim_60s_score` | 54 | 0.024 | 0.119 |
| `htf_lsi_2m_anchor` | `pre_confirm_30s_pressure_score` | `confirm_reclaim_velocity_ticks_per_second` | 261 | -0.055 | -0.111 |
| `htf_lsi_2m_anchor` | `pre_confirm_30s_pressure_score` | `trapped_reversal_confirm_score` | 261 | -0.053 | -0.079 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `pre_confirm_30s_pressure_score` | `post_reclaim_60s_score` | 161 | 0.003 | -0.053 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `pre_confirm_30s_pressure_score` | `trapped_reversal_confirm_score` | 129 | 0.030 | -0.052 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `pre_confirm_30s_pressure_score` | `trapped_reversal_confirm_score` | 161 | 0.028 | -0.047 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `pre_confirm_30s_pressure_score` | `trapped_reversal_confirm_score` | 54 | -0.070 | -0.043 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `pre_confirm_30s_pressure_score` | `post_reclaim_60s_score` | 185 | -0.051 | 0.042 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `pre_confirm_30s_pressure_score` | `confirm_reclaim_velocity_ticks_per_second` | 161 | 0.107 | 0.037 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `pre_confirm_30s_pressure_score` | `post_reclaim_60s_score` | 129 | 0.027 | -0.033 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `pre_confirm_30s_pressure_score` | `trapped_reversal_confirm_score` | 185 | -0.058 | 0.029 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `pre_confirm_30s_pressure_score` | `confirm_reclaim_velocity_ticks_per_second` | 129 | 0.048 | 0.027 |

## Feature Coverage

- Scored rows: `799` / `799`.
- Candidates: `5`.
- Threshold rows: `40`.

## Interpretation

- This replay is a price-action proxy, not an order-book replacement. If a feature works here, it suggests we can test more history before spending more MBP-10 budget.
- Entry-safe features use information up to `signal_start`; signal-close features use information through `signal_end`; post-confirm features are diagnostics for management only.
- Treat improvements that only appear in post-confirm diagnostics as hold/add/reduce ideas, not entry rules.
- Any promotion still needs exact execution replay with dynamic sizing.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_sweep_reclaim_velocity_20260515/trade_sweep_reclaim_features.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_sweep_reclaim_velocity_20260515/frozen_thresholds.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_sweep_reclaim_velocity_20260515/risk_tier_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_sweep_reclaim_velocity_20260515/tier_breakdown.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_sweep_reclaim_velocity_20260515/monthly_breakdown.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_sweep_reclaim_velocity_20260515/top_features.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_sweep_reclaim_velocity_20260515/orderbook_price_correlation.csv`