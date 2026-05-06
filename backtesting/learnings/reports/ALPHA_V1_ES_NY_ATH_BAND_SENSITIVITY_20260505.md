# ALPHA_V1 ES NY ATH Band Sensitivity - 2026-05-05

## Scope

Exact-engine sensitivity pass for ES NY only from 2016-04-17 through 2026-03-24. Each profile uses the live ORBEngine ATH gate before arming the order; no post-trade filter is used.

Bands tested: `0.25-0.75%`, `0.50-0.75%`, `0.75-1.00%`, `0.50-1.00%`, and `0.50-1.25%` below expanding ES futures ATH.

Deployability fields:
- `deployability`: post_filter_only
- `live_support_notes`: exact replay uses causal `ath_block_min_pct/max_pct`; production live still needs a trusted historical ATH seed source before this becomes `live_native`.
- `exact_replay_required`: complete for this sensitivity pass

## Ranking

| band | profile | deployability | exact_replay_required | full_delta_r | full_payout_delta_pct | 2024_delta_r | 2024_payout_delta_pct | 2025_delta_r | 2025_payout_delta_pct | rolling_positive | rolling_median_delta_r | rolling_worst_delta_r | live_support_notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.50-0.75% | ALPHA_V1_ES_NY_ATH_0P5_0P75_EXACT | post_filter_only | complete_for_sensitivity | 11.5 | 2.3 | 5.0 | 10.2 | 10.0 | 15.6 | 7/10 | 1.75 | -6.917 | Exact replay uses causal ORBEngine ATH block config; production live still needs a trusted historical ATH seed before this becomes live_native. |
| 0.50-1.00% | ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | post_filter_only | complete_for_sensitivity | 9.208 | -4.6 | 8.5 | 10.2 | 9.5 | 15.6 | 6/10 | 1.5 | -11.209 | Exact replay uses causal ORBEngine ATH block config; production live still needs a trusted historical ATH seed before this becomes live_native. |
| 0.25-0.75% | ALPHA_V1_ES_NY_ATH_0P25_0P75_EXACT | post_filter_only | complete_for_sensitivity | 5.041 | 5.0 | 7.5 | 8.5 | 13.0 | 21.9 | 4/10 | -1.855 | -4.5 | Exact replay uses causal ORBEngine ATH block config; production live still needs a trusted historical ATH seed before this becomes live_native. |
| 0.75-1.00% | ALPHA_V1_ES_NY_ATH_0P75_1_EXACT | post_filter_only | complete_for_sensitivity | 7.958 | 3.1 | 6.5 | 10.2 | 1.5 | 15.6 | 6/10 | 1.083 | -2.125 | Exact replay uses causal ORBEngine ATH block config; production live still needs a trusted historical ATH seed before this becomes live_native. |
| 0.50-1.25% | ALPHA_V1_ES_NY_ATH_0P5_1P25_EXACT | post_filter_only | complete_for_sensitivity | 0.916 | -4.6 | 4.5 | 10.2 | 4.5 | 15.6 | 6/10 | 1.0 | -11.209 | Exact replay uses causal ORBEngine ATH block config; production live still needs a trusted historical ATH seed before this becomes live_native. |

## Full-History Exact Comparison

| band | profile | window | baseline_trades | gated_trades | trade_delta | baseline_r | gated_r | delta_r | baseline_dd_r | gated_dd_r | dd_delta_r | baseline_wr_pct | gated_wr_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.25-0.75% | ALPHA_V1_ES_NY_ATH_0P25_0P75_EXACT | full | 849 | 740 | -109 | 145.803 | 150.844 | 5.041 | -12.0 | -12.0 | 0.0 | 55.8 | 56.6 |
| 0.50-0.75% | ALPHA_V1_ES_NY_ATH_0P5_0P75_EXACT | full | 849 | 808 | -41 | 145.803 | 157.303 | 11.5 | -12.0 | -12.0 | 0.0 | 55.8 | 56.1 |
| 0.75-1.00% | ALPHA_V1_ES_NY_ATH_0P75_1_EXACT | full | 849 | 828 | -21 | 145.803 | 153.761 | 7.958 | -12.0 | -12.0 | 0.0 | 55.8 | 56.5 |
| 0.50-1.00% | ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | full | 849 | 774 | -75 | 145.803 | 155.011 | 9.208 | -12.0 | -12.0 | 0.0 | 55.8 | 56.7 |
| 0.50-1.25% | ALPHA_V1_ES_NY_ATH_0P5_1P25_EXACT | full | 849 | 750 | -99 | 145.803 | 146.719 | 0.916 | -12.0 | -12.0 | 0.0 | 55.8 | 56.4 |

## Recent Exact Comparison

| band | profile | window | baseline_trades | gated_trades | trade_delta | baseline_r | gated_r | delta_r | baseline_dd_r | gated_dd_r | dd_delta_r | baseline_wr_pct | gated_wr_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.25-0.75% | ALPHA_V1_ES_NY_ATH_0P25_0P75_EXACT | 2024+ | 201 | 169 | -32 | 34.424 | 41.924 | 7.5 | -9.0 | -6.5 | 2.5 | 53.2 | 55.0 |
| 0.25-0.75% | ALPHA_V1_ES_NY_ATH_0P25_0P75_EXACT | 2025+ | 111 | 93 | -18 | 18.041 | 31.041 | 13.0 | -9.0 | -5.0 | 4.0 | 54.1 | 58.1 |
| 0.50-0.75% | ALPHA_V1_ES_NY_ATH_0P5_0P75_EXACT | 2024+ | 201 | 188 | -13 | 34.424 | 39.424 | 5.0 | -9.0 | -8.5 | 0.5 | 53.2 | 53.2 |
| 0.50-0.75% | ALPHA_V1_ES_NY_ATH_0P5_0P75_EXACT | 2025+ | 111 | 103 | -8 | 18.041 | 28.041 | 10.0 | -9.0 | -8.5 | 0.5 | 54.1 | 56.3 |
| 0.75-1.00% | ALPHA_V1_ES_NY_ATH_0P75_1_EXACT | 2024+ | 201 | 192 | -9 | 34.424 | 40.924 | 6.5 | -9.0 | -8.5 | 0.5 | 53.2 | 54.7 |
| 0.75-1.00% | ALPHA_V1_ES_NY_ATH_0P75_1_EXACT | 2025+ | 111 | 108 | -3 | 18.041 | 19.541 | 1.5 | -9.0 | -8.5 | 0.5 | 54.1 | 54.6 |
| 0.50-1.00% | ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | 2024+ | 201 | 172 | -29 | 34.424 | 42.924 | 8.5 | -9.0 | -7.5 | 1.5 | 53.2 | 55.2 |
| 0.50-1.00% | ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | 2025+ | 111 | 98 | -13 | 18.041 | 27.541 | 9.5 | -9.0 | -7.5 | 1.5 | 54.1 | 57.1 |
| 0.50-1.25% | ALPHA_V1_ES_NY_ATH_0P5_1P25_EXACT | 2024+ | 201 | 165 | -36 | 34.424 | 38.924 | 4.5 | -9.0 | -9.5 | -0.5 | 53.2 | 55.2 |
| 0.50-1.25% | ALPHA_V1_ES_NY_ATH_0P5_1P25_EXACT | 2025+ | 111 | 95 | -16 | 18.041 | 22.541 | 4.5 | -9.0 | -9.5 | -0.5 | 54.1 | 56.8 |

## Funded First-Payout Summary

| profile | window | accounts | payouts | breaches | open | payout_rate_pct | breach_rate_pct | ev_per_account_usd | median_days_to_payout | median_trades_to_payout | max_consecutive_breaches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1_ES_NY_BASELINE_EXACT | full | 260 | 169 | 85 | 6 | 65.0 | 32.69230769230769 | 175.0 | 103.0 | 25.0 | 25 |
| ALPHA_V1_ES_NY_BASELINE_EXACT | 2024+ | 59 | 44 | 9 | 6 | 74.57627118644068 | 15.254237288135593 | 222.88135593220338 | 101.0 | 25.0 | 5 |
| ALPHA_V1_ES_NY_BASELINE_EXACT | 2025+ | 32 | 19 | 8 | 5 | 59.375 | 25.0 | 146.875 | 96.0 | 25.0 | 4 |
| ALPHA_V1_ES_NY_ATH_0P25_0P75_EXACT | full | 260 | 182 | 71 | 7 | 70.0 | 27.307692307692307 | 200.0 | 120.0 | 21.5 | 25 |
| ALPHA_V1_ES_NY_ATH_0P25_0P75_EXACT | 2024+ | 59 | 49 | 3 | 7 | 83.05084745762711 | 5.084745762711865 | 265.2542372881356 | 133.0 | 26.0 | 3 |
| ALPHA_V1_ES_NY_ATH_0P25_0P75_EXACT | 2025+ | 32 | 26 | 0 | 6 | 81.25 | 0.0 | 256.25 | 103.0 | 18.0 | 0 |
| ALPHA_V1_ES_NY_ATH_0P5_0P75_EXACT | full | 260 | 175 | 79 | 6 | 67.3076923076923 | 30.384615384615383 | 186.53846153846155 | 103.0 | 21.0 | 25 |
| ALPHA_V1_ES_NY_ATH_0P5_0P75_EXACT | 2024+ | 59 | 50 | 3 | 6 | 84.7457627118644 | 5.084745762711865 | 273.728813559322 | 109.5 | 23.5 | 3 |
| ALPHA_V1_ES_NY_ATH_0P5_0P75_EXACT | 2025+ | 32 | 24 | 3 | 5 | 75.0 | 9.375 | 225.0 | 90.0 | 18.5 | 3 |
| ALPHA_V1_ES_NY_ATH_0P75_1_EXACT | full | 260 | 177 | 77 | 6 | 68.07692307692308 | 29.615384615384617 | 190.3846153846154 | 106.0 | 24.0 | 25 |
| ALPHA_V1_ES_NY_ATH_0P75_1_EXACT | 2024+ | 59 | 50 | 3 | 6 | 84.7457627118644 | 5.084745762711865 | 273.728813559322 | 112.0 | 24.0 | 3 |
| ALPHA_V1_ES_NY_ATH_0P75_1_EXACT | 2025+ | 32 | 24 | 3 | 5 | 75.0 | 9.375 | 225.0 | 120.5 | 29.0 | 3 |
| ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | full | 260 | 157 | 97 | 6 | 60.38461538461538 | 37.30769230769231 | 151.92307692307693 | 96.0 | 19.0 | 25 |
| ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | 2024+ | 59 | 50 | 3 | 6 | 84.7457627118644 | 5.084745762711865 | 273.728813559322 | 109.0 | 21.0 | 3 |
| ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | 2025+ | 32 | 24 | 3 | 5 | 75.0 | 9.375 | 225.0 | 93.0 | 17.0 | 3 |
| ALPHA_V1_ES_NY_ATH_0P5_1P25_EXACT | full | 260 | 157 | 98 | 5 | 60.38461538461538 | 37.69230769230769 | 151.92307692307693 | 99.0 | 20.0 | 25 |
| ALPHA_V1_ES_NY_ATH_0P5_1P25_EXACT | 2024+ | 59 | 50 | 4 | 5 | 84.7457627118644 | 6.779661016949152 | 273.728813559322 | 115.5 | 22.0 | 4 |
| ALPHA_V1_ES_NY_ATH_0P5_1P25_EXACT | 2025+ | 32 | 24 | 4 | 4 | 75.0 | 12.5 | 225.0 | 107.0 | 20.5 | 4 |

## Rolling 2-Year Stability

| band | windows | positive_delta_windows | nonnegative_delta_windows | median_delta_r | worst_delta_r | best_delta_r | dd_improved_windows | worst_dd_delta_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.25-0.75% | 10 | 4 | 4 | -1.855 | -4.5 | 13.0 | 5 | -1.0 |
| 0.50-0.75% | 10 | 7 | 7 | 1.75 | -6.917 | 10.0 | 4 | -1.083 |
| 0.75-1.00% | 10 | 6 | 7 | 1.083 | -2.125 | 5.5 | 3 | -0.5 |
| 0.50-1.00% | 10 | 6 | 7 | 1.5 | -11.209 | 9.5 | 6 | -2.083 |
| 0.50-1.25% | 10 | 6 | 6 | 1.0 | -11.209 | 7.0 | 6 | -2.083 |

## Decision Read

Best all-around band is `0.50-0.75%`. It has the highest exact R lift (`+11.5R` full history), improves full-history first-payout rate instead of hurting it (`65.0%` to `67.3%`), and keeps the recent-flow benefit (`2024+` payout `84.7%`, `2025+` payout `75.0%`). Rolling stability is acceptable but not perfect: `7/10` rolling 2-year windows improve, median delta is `+1.75R`, and the worst window is `-6.92R` in `2019-2020`.

`0.25-0.75%` is the payout-safety alternative (`70.0%` full payout and no `2025+` breaches), but it only improves `4/10` rolling windows and has a negative rolling median, so it looks more like a recent-flow specialist than a stable default. `0.75-1.00%` is steadier but gives up too much `2025+` R. Reject the wider `0.50-1.25%`; it removes too many trades and reintroduces the full-history payout damage seen in the original wider band.

Next action: freeze `0.50-0.75%` as the candidate for seed-source implementation and forward shadow/dry-run evaluation. Do not enable it in production until live startup can seed the same ES futures ATH used by exact replay.
