# ALPHA_V1 ATH Fragility - 2026-06-08

## Scope

- Profile: `ALPHA_V1-A`
- Exact replay window: `2021-06-06` to `2026-06-05`
- Latest common ES/NQ local data timestamp: `2026-06-05T16:55:00-04:00`
- Inputs are local ES/NQ OHLCV files only. The latest DataBento pull warned that `2026-05-24` is degraded.
- ATH bucket labels use fill-time 5m-bar context as an attribution proxy. Native hard gates evaluate on the closed signal bar before order arming.
- Exact hard-gate variants are `live_native` for ORB sessions. Post-haircut variants are `research_only` until live ATH-conditioned risk sizing exists.
- First-payout proxy uses a simple `+5R` payout / `-4R` breach model with a new account every 14 calendar days.

## Fresh Baseline Exact Summary

- Trades: `1425`; net PnL: `$61521.02`; engine-native net R: `207.56`; PF: `1.36`; max DD: `$-4434.87`; max consecutive losses: `10`

## Baseline ATH Buckets

| window | ath_bucket | trades | configured_net_r | avg_configured_r | profit_factor | max_dd_configured_r | max_consecutive_losses | loss_after_loss_pct | three_loss_cluster_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | above_prior_ath | 2 | 2.034 | 1.017 | inf | 0.000 | 0 | 0.000 | 0 |
| full | 0-0.5% | 243 | 54.880 | 0.226 | 1.546 | -11.521 | 5 | 48.571 | 21 |
| full | 0.5-1% | 129 | 15.222 | 0.118 | 1.271 | -10.029 | 7 | 44.068 | 13 |
| full | 1-2% | 161 | 14.420 | 0.090 | 1.192 | -11.243 | 8 | 51.316 | 22 |
| full | 2-5% | 239 | 19.550 | 0.082 | 1.176 | -15.486 | 7 | 53.719 | 37 |
| full | 5-10% | 231 | 29.446 | 0.127 | 1.275 | -11.654 | 6 | 47.748 | 24 |
| full | >10% | 420 | 56.029 | 0.133 | 1.301 | -10.502 | 10 | 50.251 | 50 |
| 2025+ | above_prior_ath | 1 | 0.479 | 0.479 | inf | 0.000 | 0 | 0.000 | 0 |
| 2025+ | 0-0.5% | 94 | 32.156 | 0.342 | 1.856 | -11.521 | 5 | 44.737 | 6 |
| 2025+ | 0.5-1% | 54 | 2.642 | 0.049 | 1.101 | -10.029 | 7 | 55.556 | 7 |
| 2025+ | 1-2% | 69 | 20.640 | 0.299 | 1.794 | -3.176 | 3 | 40.000 | 3 |
| 2025+ | 2-5% | 109 | 32.675 | 0.300 | 1.791 | -5.911 | 4 | 42.222 | 9 |
| 2025+ | 5-10% | 55 | 4.997 | 0.091 | 1.186 | -7.127 | 4 | 48.148 | 4 |
| 2025+ | >10% | 30 | -5.470 | -0.182 | 0.677 | -10.502 | 10 | 68.421 | 9 |
| 2026_ytd | above_prior_ath | 1 | 0.479 | 0.479 | inf | 0.000 | 0 | 0.000 | 0 |
| 2026_ytd | 0-0.5% | 28 | -11.520 | -0.411 | 0.346 | -10.804 | 4 | 50.000 | 2 |
| 2026_ytd | 0.5-1% | 18 | 8.079 | 0.449 | 2.308 | -2.137 | 2 | 50.000 | 0 |
| 2026_ytd | 1-2% | 22 | 11.341 | 0.516 | 2.677 | -2.613 | 3 | 50.000 | 1 |
| 2026_ytd | 2-5% | 33 | 4.095 | 0.124 | 1.279 | -5.911 | 4 | 53.333 | 4 |
| 2026_ytd | 5-10% | 25 | -2.966 | -0.119 | 0.802 | -7.127 | 4 | 53.333 | 3 |
| 2026_ytd | >10% | 2 | -0.331 | -0.165 | 0.632 | 0.000 | 1 | 0.000 | 0 |
| 2026_05+ | 0-0.5% | 19 | -5.791 | -0.305 | 0.463 | -5.983 | 2 | 45.455 | 0 |
| 2026_05+ | 0.5-1% | 7 | 8.825 | 1.261 | inf | 0.000 | 0 | 0.000 | 0 |
| 2026_05+ | 1-2% | 6 | -0.016 | -0.003 | 0.996 | -2.613 | 3 | 66.667 | 1 |
| 2026_05+ | 2-5% | 1 | 0.492 | 0.492 | inf | 0.000 | 0 | 0.000 | 0 |

## Leg Focus: Moderate and Deeper Dip Buckets

| window | scope | ath_bucket | trades | configured_net_r | avg_configured_r | profit_factor | max_dd_configured_r | max_consecutive_losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025+ | ES_Asia | 0.5-1% | 26 | -0.433 | -0.017 | 0.967 | -6.817 | 5 |
| 2025+ | ES_Asia | 5-10% | 19 | 1.411 | 0.074 | 1.158 | -3.755 | 3 |
| 2025+ | ES_NY | 0.5-1% | 7 | -4.312 | -0.616 | 0.163 | -3.397 | 2 |
| 2025+ | ES_NY | 5-10% | 13 | -2.137 | -0.164 | 0.649 | -3.033 | 3 |
| 2025+ | NQ_Asia | 0.5-1% | 10 | 6.642 | 0.664 | 2.676 | -2.958 | 3 |
| 2025+ | NQ_Asia | 5-10% | 13 | 0.658 | 0.051 | 1.083 | -5.910 | 6 |
| 2025+ | NQ_NY | 0.5-1% | 6 | 0.726 | 0.121 | 1.378 | -0.951 | 2 |
| 2025+ | NQ_NY | 5-10% | 7 | 0.688 | 0.098 | 1.176 | -1.957 | 2 |
| 2025+ | NQ_NY_LSI | 0.5-1% | 5 | 0.019 | 0.004 | 1.010 | -0.966 | 2 |
| 2025+ | NQ_NY_LSI | 5-10% | 3 | 4.377 | 1.459 | inf | 0.000 | 0 |
| 2026_ytd | ES_Asia | 0.5-1% | 8 | 2.985 | 0.373 | 1.991 | -1.046 | 1 |
| 2026_ytd | ES_Asia | 5-10% | 9 | -1.549 | -0.172 | 0.693 | -3.004 | 3 |
| 2026_ytd | ES_NY | 0.5-1% | 4 | -2.744 | -0.686 | 0.132 | -2.086 | 2 |
| 2026_ytd | ES_NY | 5-10% | 2 | -0.616 | -0.308 | 0.420 | 0.000 | 1 |
| 2026_ytd | NQ_Asia | 0.5-1% | 3 | 5.407 | 1.802 | inf | 0.000 | 0 |
| 2026_ytd | NQ_Asia | 5-10% | 9 | -3.096 | -0.344 | 0.553 | -5.910 | 6 |
| 2026_ytd | NQ_NY | 0.5-1% | 2 | 1.360 | 0.680 | inf | 0.000 | 0 |
| 2026_ytd | NQ_NY | 5-10% | 3 | -1.254 | -0.418 | 0.355 | -0.942 | 2 |
| 2026_ytd | NQ_NY_LSI | 0.5-1% | 1 | 1.070 | 1.070 | inf | 0.000 | 0 |
| 2026_ytd | NQ_NY_LSI | 5-10% | 2 | 3.549 | 1.775 | inf | 0.000 | 0 |
| 2026_05+ | ES_Asia | 0.5-1% | 3 | 3.636 | 1.212 | inf | 0.000 | 0 |
| 2026_05+ | NQ_Asia | 0.5-1% | 2 | 3.488 | 1.744 | inf | 0.000 | 0 |
| 2026_05+ | NQ_NY | 0.5-1% | 1 | 0.631 | 0.631 | inf | 0.000 | 0 |
| 2026_05+ | NQ_NY_LSI | 0.5-1% | 1 | 1.070 | 1.070 | inf | 0.000 | 0 |

## Continuous Correlation Check

| scope | trades | pearson_gap | spearman_gap | pearson_days_since_ath | spearman_days_since_ath |
| --- | --- | --- | --- | --- | --- |
| portfolio | 1425 | 0.001 | 0.004 | -0.012 | -0.010 |
| ES_Asia | 586 | 0.019 | 0.013 | -0.018 | -0.015 |
| ES_NY | 246 | 0.000 | 0.111 | 0.028 | 0.100 |
| NQ_Asia | 256 | -0.040 | -0.078 | -0.058 | -0.070 |
| NQ_NY | 202 | -0.003 | 0.015 | -0.005 | -0.016 |
| NQ_NY_LSI | 135 | -0.025 | -0.036 | 0.003 | -0.029 |

## Exact Native Hard-Gate Scorecard

| scenario | window | trades | trade_delta | delta_pnl_usd | delta_configured_net_r | configured_net_r | profit_factor | max_dd_configured_r | max_consecutive_losses | delta_max_consecutive_losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BASELINE | full | 1425 | 0 | 0.000 | 0.000 | 191.581 | 1.301 | -16.125 | 10 | 0 |
| BASELINE | 2025+ | 412 | 0 | 0.000 | 0.000 | 88.119 | 1.504 | -12.776 | 10 | 0 |
| BASELINE | 2026_ytd | 129 | 0 | 0.000 | 0.000 | 9.178 | 1.150 | -9.447 | 6 | 0 |
| BASELINE | 2026_05+ | 33 | 0 | 0.000 | 0.000 | 3.511 | 1.243 | -4.981 | 3 | 0 |
| ES_NY_BLOCK_0P5_0P75 | full | 1422 | -3 | 4146.610 | 11.779 | 203.360 | 1.321 | -18.290 | 10 | 0 |
| ES_NY_BLOCK_0P5_0P75 | 2025+ | 409 | -3 | 2029.820 | 6.690 | 94.810 | 1.549 | -11.774 | 10 | 0 |
| ES_NY_BLOCK_0P5_0P75 | 2026_ytd | 127 | -2 | 98.120 | 0.397 | 9.575 | 1.159 | -9.447 | 6 | 0 |
| ES_NY_BLOCK_0P5_0P75 | 2026_05+ | 33 | 0 | 0.000 | 0.000 | 3.511 | 1.243 | -4.981 | 3 | 0 |
| ES_NY_BLOCK_0P5_1P0 | full | 1421 | -4 | 3236.410 | 6.274 | 197.855 | 1.312 | -16.621 | 10 | 0 |
| ES_NY_BLOCK_0P5_1P0 | 2025+ | 409 | -3 | 1286.690 | 2.947 | 91.067 | 1.527 | -11.774 | 10 | 0 |
| ES_NY_BLOCK_0P5_1P0 | 2026_ytd | 130 | 1 | -175.830 | -0.978 | 8.200 | 1.134 | -9.447 | 6 | 0 |
| ES_NY_BLOCK_0P5_1P0 | 2026_05+ | 33 | 0 | -939.790 | -3.230 | 0.280 | 1.018 | -4.981 | 5 | 2 |
| ES_ASIA_BLOCK_0P5_1P0 | full | 1380 | -45 | -618.560 | -6.244 | 185.337 | 1.301 | -19.084 | 10 | 0 |
| ES_ASIA_BLOCK_0P5_1P0 | 2025+ | 398 | -14 | -2580.240 | -7.240 | 80.879 | 1.482 | -11.774 | 10 | 0 |
| ES_ASIA_BLOCK_0P5_1P0 | 2026_ytd | 127 | -2 | -183.900 | -1.236 | 7.942 | 1.132 | -10.830 | 6 | 0 |
| ES_ASIA_BLOCK_0P5_1P0 | 2026_05+ | 33 | 0 | 46.640 | -1.185 | 2.326 | 1.151 | -4.874 | 3 | 0 |
| ES_ALL_BLOCK_0P5_1P0 | full | 1365 | -60 | 4871.980 | 13.039 | 204.620 | 1.336 | -18.344 | 10 | 0 |
| ES_ALL_BLOCK_0P5_1P0 | 2025+ | 391 | -21 | 2501.890 | 9.951 | 98.070 | 1.607 | -11.774 | 10 | 0 |
| ES_ALL_BLOCK_0P5_1P0 | 2026_ytd | 125 | -4 | 493.700 | 1.028 | 10.206 | 1.172 | -10.014 | 6 | 0 |
| ES_ALL_BLOCK_0P5_1P0 | 2026_05+ | 32 | -1 | 283.300 | -0.238 | 3.273 | 1.227 | -3.928 | 3 | 0 |
| ES_ALL_BLOCK_5P0_10P0 | full | 1301 | -124 | 845.550 | -2.073 | 189.508 | 1.328 | -12.897 | 10 | 0 |
| ES_ALL_BLOCK_5P0_10P0 | 2025+ | 380 | -32 | 1209.860 | 3.425 | 91.545 | 1.583 | -10.425 | 10 | 0 |
| ES_ALL_BLOCK_5P0_10P0 | 2026_ytd | 118 | -11 | 725.950 | 3.581 | 12.759 | 1.239 | -9.915 | 8 | 2 |
| ES_ALL_BLOCK_5P0_10P0 | 2026_05+ | 33 | 0 | 553.220 | 2.194 | 5.705 | 1.421 | -4.981 | 3 | 0 |
| ORB_ALL_BLOCK_0P5_1P0 | full | 1336 | -89 | -3532.470 | -9.176 | 182.405 | 1.304 | -19.064 | 10 | 0 |
| ORB_ALL_BLOCK_0P5_1P0 | 2025+ | 380 | -32 | -980.390 | -0.359 | 87.761 | 1.553 | -15.454 | 10 | 0 |
| ORB_ALL_BLOCK_0P5_1P0 | 2026_ytd | 121 | -8 | -3391.530 | -10.956 | -1.778 | 0.971 | -15.454 | 6 | 0 |
| ORB_ALL_BLOCK_0P5_1P0 | 2026_05+ | 29 | -4 | -3154.400 | -10.830 | -7.319 | 0.548 | -7.509 | 5 | 2 |

## Post-Trade Risk Haircut Scorecard

| scenario | window | trade_delta | delta_pnl_usd | delta_configured_net_r | configured_net_r | profit_factor | max_dd_configured_r | max_consecutive_losses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| POST_ES_NY_HALF_RISK_0P5_1P0 | full | 0 | 1372.160 | 4.574 | 196.155 | 1.311 | -16.125 | 10 |
| POST_ES_NY_HALF_RISK_0P5_1P0 | 2025+ | 0 | 646.810 | 2.156 | 90.275 | 1.524 | -12.776 | 10 |
| POST_ES_NY_HALF_RISK_0P5_1P0 | 2026_ytd | 0 | 411.535 | 1.372 | 10.550 | 1.177 | -9.447 | 6 |
| POST_ES_NY_HALF_RISK_0P5_1P0 | 2026_05+ | 0 | 0.000 | 0.000 | 3.511 | 1.243 | -4.981 | 3 |
| POST_ES_ASIA_HALF_RISK_0P5_1P0 | full | 0 | -696.825 | -4.645 | 186.936 | 1.301 | -16.204 | 10 |
| POST_ES_ASIA_HALF_RISK_0P5_1P0 | 2025+ | 0 | 32.490 | 0.217 | 88.336 | 1.525 | -12.776 | 10 |
| POST_ES_ASIA_HALF_RISK_0P5_1P0 | 2026_ytd | 0 | -223.870 | -1.492 | 7.686 | 1.129 | -9.447 | 6 |
| POST_ES_ASIA_HALF_RISK_0P5_1P0 | 2026_05+ | 0 | -272.735 | -1.818 | 1.692 | 1.117 | -4.981 | 3 |
| POST_ES_ALL_HALF_RISK_0P5_1P0 | full | 0 | 675.335 | -0.072 | 191.509 | 1.311 | -16.204 | 10 |
| POST_ES_ALL_HALF_RISK_0P5_1P0 | 2025+ | 0 | 679.300 | 2.373 | 90.492 | 1.546 | -12.776 | 10 |
| POST_ES_ALL_HALF_RISK_0P5_1P0 | 2026_ytd | 0 | 187.665 | -0.121 | 9.057 | 1.156 | -9.447 | 6 |
| POST_ES_ALL_HALF_RISK_0P5_1P0 | 2026_05+ | 0 | -272.735 | -1.818 | 1.692 | 1.117 | -4.981 | 3 |
| POST_ES_ALL_HALF_RISK_5P0_10P0 | full | 0 | -803.825 | -3.586 | 187.995 | 1.310 | -13.271 | 10 |
| POST_ES_ALL_HALF_RISK_5P0_10P0 | 2025+ | 0 | 214.700 | 0.363 | 88.482 | 1.529 | -12.101 | 10 |
| POST_ES_ALL_HALF_RISK_5P0_10P0 | 2026_ytd | 0 | 208.550 | 1.083 | 10.261 | 1.177 | -8.012 | 6 |
| POST_ES_ALL_HALF_RISK_5P0_10P0 | 2026_05+ | 0 | 0.000 | 0.000 | 3.511 | 1.243 | -4.981 | 3 |
| POST_ORB_ALL_HALF_RISK_0P5_1P0 | full | 0 | -2175.090 | -7.761 | 183.820 | 1.301 | -17.062 | 10 |
| POST_ORB_ALL_HALF_RISK_0P5_1P0 | 2025+ | 0 | -739.845 | -1.311 | 86.808 | 1.533 | -12.776 | 10 |
| POST_ORB_ALL_HALF_RISK_0P5_1P0 | 2026_ytd | 0 | -1063.815 | -3.504 | 5.674 | 1.098 | -9.447 | 6 |
| POST_ORB_ALL_HALF_RISK_0P5_1P0 | 2026_05+ | 0 | -1049.150 | -3.878 | -0.367 | 0.975 | -4.981 | 3 |

## First-Payout Proxy Scorecard

| scenario | kind | window | accounts | payouts | breaches | resolved_payout_rate_pct | breach_rate_pct | median_days_to_payout | max_consecutive_breaches | ev_per_account_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BASELINE | exact | 2025+ | 38 | 29 | 8 | 78.378 | 21.053 | 12.000 | 3 | 2.927 |
| BASELINE | exact | 2026_ytd | 11 | 6 | 3 | 66.667 | 27.273 | 29.500 | 3 | 1.310 |
| BASELINE | exact | 2026_05+ | 3 | 1 | 0 | 100.000 | 0.000 | 17.000 | 0 | 0.334 |
| ES_NY_BLOCK_0P5_0P75 | exact | 2025+ | 38 | 29 | 7 | 80.556 | 18.421 | 12.000 | 3 | 3.024 |
| ES_NY_BLOCK_0P5_0P75 | exact | 2026_ytd | 11 | 7 | 3 | 70.000 | 27.273 | 29.000 | 3 | 1.790 |
| ES_NY_BLOCK_0P5_0P75 | exact | 2026_05+ | 3 | 1 | 0 | 100.000 | 0.000 | 17.000 | 0 | 0.334 |
| ES_NY_BLOCK_0P5_1P0 | exact | 2025+ | 38 | 27 | 8 | 77.143 | 21.053 | 12.000 | 3 | 2.596 |
| ES_NY_BLOCK_0P5_1P0 | exact | 2026_ytd | 11 | 5 | 3 | 62.500 | 27.273 | 34.000 | 3 | 0.582 |
| ES_NY_BLOCK_0P5_1P0 | exact | 2026_05+ | 3 | 0 | 0 | 0.000 | 0.000 | nan | 0 | -1.239 |
| ES_ASIA_BLOCK_0P5_1P0 | exact | 2025+ | 38 | 28 | 9 | 75.676 | 23.684 | 12.500 | 4 | 2.665 |
| ES_ASIA_BLOCK_0P5_1P0 | exact | 2026_ytd | 12 | 6 | 4 | 60.000 | 33.333 | 19.000 | 3 | 0.824 |
| ES_ASIA_BLOCK_0P5_1P0 | exact | 2026_05+ | 3 | 1 | 1 | 50.000 | 33.333 | 17.000 | 1 | 0.308 |
| ES_ALL_BLOCK_0P5_1P0 | exact | 2025+ | 38 | 28 | 9 | 75.676 | 23.684 | 12.000 | 4 | 2.690 |
| ES_ALL_BLOCK_0P5_1P0 | exact | 2026_ytd | 11 | 6 | 4 | 60.000 | 36.364 | 17.000 | 3 | 1.071 |
| ES_ALL_BLOCK_0P5_1P0 | exact | 2026_05+ | 3 | 1 | 0 | 100.000 | 0.000 | 17.000 | 0 | 0.699 |
| ES_ALL_BLOCK_5P0_10P0 | exact | 2025+ | 38 | 30 | 7 | 81.081 | 18.421 | 12.000 | 2 | 3.164 |
| ES_ALL_BLOCK_5P0_10P0 | exact | 2026_ytd | 11 | 7 | 3 | 70.000 | 27.273 | 27.000 | 3 | 1.790 |
| ES_ALL_BLOCK_5P0_10P0 | exact | 2026_05+ | 3 | 1 | 0 | 100.000 | 0.000 | 11.000 | 0 | 0.334 |
| ORB_ALL_BLOCK_0P5_1P0 | exact | 2025+ | 38 | 26 | 10 | 72.222 | 26.316 | 12.000 | 4 | 2.310 |
| ORB_ALL_BLOCK_0P5_1P0 | exact | 2026_ytd | 11 | 4 | 7 | 36.364 | 63.636 | 10.000 | 4 | -0.727 |
| ORB_ALL_BLOCK_0P5_1P0 | exact | 2026_05+ | 3 | 0 | 1 | 0.000 | 33.333 | nan | 1 | -3.083 |
| POST_ES_NY_HALF_RISK_0P5_1P0 | post_haircut | 2025+ | 38 | 29 | 8 | 78.378 | 21.053 | 12.000 | 3 | 2.927 |
| POST_ES_NY_HALF_RISK_0P5_1P0 | post_haircut | 2026_ytd | 11 | 6 | 3 | 66.667 | 27.273 | 29.000 | 3 | 1.357 |
| POST_ES_NY_HALF_RISK_0P5_1P0 | post_haircut | 2026_05+ | 3 | 1 | 0 | 100.000 | 0.000 | 17.000 | 0 | 0.334 |
| POST_ES_ASIA_HALF_RISK_0P5_1P0 | post_haircut | 2025+ | 38 | 27 | 8 | 77.143 | 21.053 | 12.000 | 3 | 2.641 |
| POST_ES_ASIA_HALF_RISK_0P5_1P0 | post_haircut | 2026_ytd | 11 | 6 | 3 | 66.667 | 27.273 | 29.000 | 3 | 1.088 |
| POST_ES_ASIA_HALF_RISK_0P5_1P0 | post_haircut | 2026_05+ | 3 | 1 | 0 | 100.000 | 0.000 | 17.000 | 0 | 0.125 |
| POST_ES_ALL_HALF_RISK_0P5_1P0 | post_haircut | 2025+ | 38 | 27 | 7 | 79.412 | 18.421 | 12.000 | 3 | 2.707 |
| POST_ES_ALL_HALF_RISK_0P5_1P0 | post_haircut | 2026_ytd | 11 | 6 | 3 | 66.667 | 27.273 | 19.000 | 3 | 1.134 |
| POST_ES_ALL_HALF_RISK_0P5_1P0 | post_haircut | 2026_05+ | 3 | 1 | 0 | 100.000 | 0.000 | 17.000 | 0 | 0.125 |
| POST_ES_ALL_HALF_RISK_5P0_10P0 | post_haircut | 2025+ | 38 | 30 | 7 | 81.081 | 18.421 | 13.000 | 2 | 3.164 |
| POST_ES_ALL_HALF_RISK_5P0_10P0 | post_haircut | 2026_ytd | 11 | 8 | 1 | 88.889 | 9.091 | 37.500 | 1 | 2.946 |
| POST_ES_ALL_HALF_RISK_5P0_10P0 | post_haircut | 2026_05+ | 3 | 1 | 0 | 100.000 | 0.000 | 17.000 | 0 | 0.334 |
| POST_ORB_ALL_HALF_RISK_0P5_1P0 | post_haircut | 2025+ | 38 | 25 | 8 | 75.758 | 21.053 | 12.000 | 3 | 2.317 |
| POST_ORB_ALL_HALF_RISK_0P5_1P0 | post_haircut | 2026_ytd | 11 | 3 | 3 | 50.000 | 27.273 | 13.000 | 3 | -0.491 |
| POST_ORB_ALL_HALF_RISK_0P5_1P0 | post_haircut | 2026_05+ | 3 | 0 | 0 | 0.000 | 0.000 | nan | 0 | -1.664 |

## Artifacts

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_fragility_20260608/baseline_raw_result.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_fragility_20260608/baseline_trades_ath_annotated.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_fragility_20260608/bucket_loss_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_fragility_20260608/ath_correlations.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_fragility_20260608/scenario_scorecard.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_fragility_20260608/payout_proxy_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_fragility_20260608/payout_proxy_accounts.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/alpha_v1_ath_fragility_20260608/summary.json`
