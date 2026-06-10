# ALPHA_V1 ATH Refresh - 2026-06-08

## Scope

- Profile: `ALPHA_V1-A`
- Exact replay window: `2021-04-25` to `2026-04-24`
- Latest common local data timestamp: `2026-04-24T16:55:00-04:00`
- Note: this packet uses fill-time 5m-bar ATH context as a quick attribution proxy; live ORB ATH gates evaluate on the closed signal bar before order arming.
- Bucket and shadow-comparison R values are configured-risk R: trade PnL divided by the current profile risk for that session. Exact summaries use engine-native net R.

## Baseline Exact Summary

- Trades: `1434`; net PnL: `$61542.31`; net R: `216.11`; PF: `1.36`; max DD: `$-4817.10`

## Baseline ATH Buckets

| window | ath_bucket | trades | configured_net_r | avg_configured_r | win_rate_pct | profit_factor | sl_pct | max_dd_configured_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | above_prior_ath | 2 | 2.034 | 1.017 | 100.000 | inf | 0.000 | 0.000 |
| full | 0-0.5% | 228 | 62.996 | 0.276 | 58.772 | 1.693 | 40.351 | -7.709 |
| full | 0.5-1% | 135 | -0.013 | -0.000 | 49.630 | 1.000 | 48.148 | -11.704 |
| full | 1-2% | 158 | 20.842 | 0.132 | 55.063 | 1.300 | 44.937 | -12.196 |
| full | 2-5% | 247 | 15.184 | 0.061 | 48.178 | 1.128 | 50.202 | -17.181 |
| full | 5-10% | 234 | 27.043 | 0.116 | 52.137 | 1.249 | 47.436 | -13.590 |
| full | >10% | 430 | 65.213 | 0.152 | 53.256 | 1.346 | 45.116 | -9.590 |
| 2025+ | above_prior_ath | 1 | 0.479 | 0.479 | 100.000 | inf | 0.000 | 0.000 |
| 2025+ | 0-0.5% | 75 | 40.551 | 0.541 | 65.333 | 2.561 | 34.667 | -5.683 |
| 2025+ | 0.5-1% | 46 | -5.159 | -0.112 | 43.478 | 0.794 | 54.348 | -10.029 |
| 2025+ | 1-2% | 63 | 20.407 | 0.324 | 65.079 | 1.914 | 34.921 | -3.176 |
| 2025+ | 2-5% | 107 | 33.155 | 0.310 | 58.879 | 1.822 | 39.252 | -5.911 |
| 2025+ | 5-10% | 55 | 4.997 | 0.091 | 50.909 | 1.186 | 49.091 | -7.127 |
| 2025+ | >10% | 29 | -4.468 | -0.154 | 37.931 | 0.720 | 55.172 | -9.590 |
| 2026_ytd | above_prior_ath | 1 | 0.479 | 0.479 | 100.000 | inf | 0.000 | 0.000 |
| 2026_ytd | 0-0.5% | 8 | -4.888 | -0.611 | 25.000 | 0.192 | 75.000 | -4.235 |
| 2026_ytd | 0.5-1% | 10 | 0.278 | 0.028 | 50.000 | 1.054 | 50.000 | -2.107 |
| 2026_ytd | 1-2% | 16 | 11.357 | 0.710 | 81.250 | 4.652 | 18.750 | -2.033 |
| 2026_ytd | 2-5% | 32 | 4.336 | 0.135 | 53.125 | 1.311 | 46.875 | -5.911 |
| 2026_ytd | 5-10% | 25 | -2.966 | -0.119 | 40.000 | 0.802 | 60.000 | -7.127 |
| 2026_ytd | >10% | 2 | -0.331 | -0.165 | 50.000 | 0.632 | 50.000 | 0.000 |

## Continuous Correlation Check

| scope | trades | pearson_gap | spearman_gap | pearson_days_since_ath | spearman_days_since_ath |
| --- | --- | --- | --- | --- | --- |
| portfolio | 1434 | 0.007 | 0.011 | -0.012 | -0.007 |
| ES_Asia | 593 | 0.023 | 0.018 | -0.015 | -0.013 |
| ES_NY | 251 | 0.020 | 0.109 | 0.050 | 0.108 |
| NQ_Asia | 251 | -0.046 | -0.071 | -0.078 | -0.083 |
| NQ_NY | 204 | 0.018 | 0.057 | -0.013 | 0.006 |
| NQ_NY_LSI | 135 | -0.004 | -0.014 | 0.021 | -0.011 |

## ES NY ATH Shadow Comparison

Shadow applies only `ES_NY ath_block_min_pct=0.5` and `ath_block_max_pct=0.75` to `ALPHA_V1-A`.
Full-window deltas: `$1286.20` net PnL; `-1.71` engine-native net R; `2.25` configured-risk net R.

| window | baseline_trades | shadow_trades | trade_delta | baseline_configured_net_r | shadow_configured_net_r | delta_configured_net_r | baseline_pf | shadow_pf | baseline_dd_configured_r | shadow_dd_configured_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | 1434 | 1422 | -12 | 193.300 | 195.547 | 2.247 | 1.302 | 1.306 | -20.173 | -17.698 |
| 2024+ | 661 | 659 | -2 | 115.161 | 117.688 | 2.526 | 1.398 | 1.404 | -13.271 | -11.999 |
| 2025+ | 376 | 375 | -1 | 89.962 | 93.046 | 3.084 | 1.575 | 1.591 | -11.774 | -11.774 |
| 2026_ytd | 94 | 92 | -2 | 8.265 | 8.070 | -0.194 | 1.187 | 1.184 | -9.447 | -9.447 |

## Shadow Exact Summary

- Trades: `1422`; net PnL: `$62828.51`; net R: `214.41`; PF: `1.37`; max DD: `$-4288.23`

## Artifacts

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_refresh_20260608/ALPHA_V1-A_raw_result.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_refresh_20260608/ALPHA_V1-A_trades_ath_annotated.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_refresh_20260608/ALPHA_V1-A_ath_bucket_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_refresh_20260608/ALPHA_V1-A_ath_correlations.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_refresh_20260608/ALPHA_V1-A_ES_NY_ATH_0P5_0P75_raw_result.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_refresh_20260608/ALPHA_V1-A_ES_NY_ATH_0P5_0P75_trades_ath_annotated.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_refresh_20260608/shadow_comparison.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_refresh_20260608/summary.json`
