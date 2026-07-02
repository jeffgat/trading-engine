# NQ NY VWAP 3m BOS Challenger

- Run slug: `nq_ny_vwap_3m_bos_challenger_20260630`
- Data: `2021-06-05` to `<2026-06-06` from raw NQ 1m bars resampled to native 3m.
- Direction: long-only, because the prior direction split showed the 3m long leg carried most of the edge.
- Exit: fixed static `1.5:1` reward-to-risk with stop priority on same-bar stop/target touches.
- Stop: `atr14_prev` `7.5%` rounded to even NQ ticks, matching the current best 3m leg.
- Context: no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full NY RTH window.
- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.

## Challenger Entry Criteria

Long setup:

1. Use NY RTH session VWAP as the mean.
2. Price must be below VWAP and extend at least `0.025 * prior 14-day RTH ATR` away from VWAP.
3. Wait for an `N`-minute consolidation below VWAP; tested `15`, `21`, `30`, `45`, and `60` minutes.
4. The consolidation range must be `<= 0.20 * ATR` and every consolidation bar high must stay below its same-bar VWAP.
5. Signal bar must close above `consolidation high + buffer * consolidation range`, while still closing below VWAP.
6. Enter long on the next 3m bar open. Maximum 3 sequential non-overlapping trades/day, about 10 minutes cooldown after exit.

The buffer grid was `0%`, `10%`, `25%`, and `50%` of the consolidation range above the consolidation high.

## Baseline Controls

| label                                    |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |
|:-----------------------------------------|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|
| baseline_sweep_reclaim_3m_all_directions |           1498 |               1.1585 |                0.7224 |   82.182  |  0.0549 |        16.0169 |   0.7039 |          1.097  |     0.4266 |         -22.7535 |                     1 |
| baseline_sweep_reclaim_3m_long_only      |            497 |               0.3844 |                0.2831 |   64.5394 |  0.1299 |        12.5784 |   0.7331 |          1.2411 |     0.4527 |         -17.1575 |                     1 |
| baseline_sweep_reclaim_3m_short_only     |           1001 |               0.7742 |                0.4811 |   17.6426 |  0.0176 |         3.4385 |   0.1326 |          1.0305 |     0.4136 |         -25.9257 |                     2 |

## Best By Consolidation Length

|   rank |   consolidation_minutes |   breakout_buffer_range_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   fixed_target_reaches_mean_pct |
|-------:|------------------------:|----------------------------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|--------------------------------:|
|      3 |                      15 |                        0.1  |           1038 |               0.8028 |                0.4934 |   38.1618 |  0.0368 |         7.4376 |   0.1386 |          1.0634 |     0.4171 |         -53.6613 |                     1 |                          0.5723 |
|      4 |                      21 |                        0.1  |            665 |               0.5143 |                0.3658 |   21.7512 |  0.0327 |         4.2392 |   0.1229 |          1.0562 |     0.415  |         -34.5    |                     1 |                          0.5308 |
|      9 |                      30 |                        0.25 |            134 |               0.1036 |                0.0959 |    1.0955 |  0.0082 |         0.2135 |   0.0133 |          1.0138 |     0.403  |         -16      |                     2 |                          0.4403 |
|     11 |                      45 |                        0.5  |              2 |               0.0015 |                0.0015 |    0.5    |  0.25   |         0.0974 |   0      |          1.5    |     0.5    |           0      |                     1 |                          0.5    |
|      1 |                      60 |                        0.1  |             45 |               0.0348 |                0.0348 |    6.4163 |  0.1426 |         1.2505 |   0.2501 |          1.2673 |     0.4667 |          -5      |                     2 |                          0.2889 |

## Daily-Cadence Challenger Rows

These are the rows that preserve the original minimum target of about one trade/day.

|   rank |   consolidation_minutes |   breakout_buffer_range_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   fixed_target_reaches_mean_pct |
|-------:|------------------------:|----------------------------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|--------------------------------:|
|      6 |                      15 |                           0 |           1329 |               1.0278 |                0.5553 |   34.1004 |  0.0257 |          6.646 |   0.1087 |          1.0438 |     0.4116 |         -61.1613 |                     1 |                          0.5719 |

## Near-Daily Challenger Rows

These are included because the strongest higher-cadence BOS row landed just below one trade/day.

|   rank |   consolidation_minutes |   breakout_buffer_range_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   fixed_target_reaches_mean_pct |
|-------:|------------------------:|----------------------------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|--------------------------------:|
|      3 |                      15 |                         0.1 |           1038 |               0.8028 |                0.4934 |   38.1618 |  0.0368 |         7.4376 |   0.1386 |          1.0634 |     0.4171 |         -53.6613 |                     1 |                          0.5723 |
|      6 |                      15 |                         0   |           1329 |               1.0278 |                0.5553 |   34.1004 |  0.0257 |         6.646  |   0.1087 |          1.0438 |     0.4116 |         -61.1613 |                     1 |                          0.5719 |

## Top Challenger Rows

|   rank |   consolidation_minutes |   breakout_buffer_range_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   fixed_target_reaches_mean_pct |
|-------:|------------------------:|----------------------------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|--------------------------------:|
|      1 |                      60 |                        0.1  |             45 |               0.0348 |                0.0348 |    6.4163 |  0.1426 |         1.2505 |   0.2501 |          1.2673 |     0.4667 |          -5      |                     2 |                          0.2889 |
|      2 |                      60 |                        0.25 |             13 |               0.0101 |                0.0101 |    1.6622 |  0.1279 |         0.324  |   0.162  |          1.2375 |     0.4615 |          -2      |                     1 |                          0.1538 |
|      3 |                      15 |                        0.1  |           1038 |               0.8028 |                0.4934 |   38.1618 |  0.0368 |         7.4376 |   0.1386 |          1.0634 |     0.4171 |         -53.6613 |                     1 |                          0.5723 |
|      4 |                      21 |                        0.1  |            665 |               0.5143 |                0.3658 |   21.7512 |  0.0327 |         4.2392 |   0.1229 |          1.0562 |     0.415  |         -34.5    |                     1 |                          0.5308 |
|      5 |                      15 |                        0.5  |            167 |               0.1292 |                0.1183 |   12.6622 |  0.0758 |         2.4678 |   0.1204 |          1.1333 |     0.4311 |         -20.5    |                     1 |                          0.479  |
|      6 |                      15 |                        0    |           1329 |               1.0278 |                0.5553 |   34.1004 |  0.0257 |         6.646  |   0.1087 |          1.0438 |     0.4116 |         -61.1613 |                     1 |                          0.5719 |
|      7 |                      21 |                        0.5  |             78 |               0.0603 |                0.0572 |    4.1622 |  0.0534 |         0.8112 |   0.0579 |          1.0925 |     0.4231 |         -14      |                     2 |                          0.4615 |
|      8 |                      21 |                        0    |            906 |               0.7007 |                0.4439 |   13.7322 |  0.0152 |         2.6763 |   0.0546 |          1.0257 |     0.4073 |         -49      |                     1 |                          0.5585 |
|      9 |                      30 |                        0.25 |            134 |               0.1036 |                0.0959 |    1.0955 |  0.0082 |         0.2135 |   0.0133 |          1.0138 |     0.403  |         -16      |                     2 |                          0.4403 |
|     10 |                      60 |                        0.5  |              0 |               0      |                0      |    0      |  0      |         0      |   0      |          0      |     0      |           0      |                     0 |                          0      |
|     11 |                      45 |                        0.5  |              2 |               0.0015 |                0.0015 |    0.5    |  0.25   |         0.0974 |   0      |          1.5    |     0.5    |           0      |                     1 |                          0.5    |
|     12 |                      15 |                        0.25 |            609 |               0.471  |                0.3534 |   -4.4583 | -0.0073 |        -0.8689 |  -0.0141 |          0.9878 |     0.3974 |         -61.6613 |                     1 |                          0.555  |
|     13 |                      30 |                        0.5  |             23 |               0.0178 |                0.017  |   -0.5    | -0.0217 |        -0.0974 |  -0.0195 |          0.9643 |     0.3913 |          -5      |                     2 |                          0.4783 |
|     14 |                      21 |                        0.25 |            325 |               0.2514 |                0.2096 |   -3.3031 | -0.0102 |        -0.6438 |  -0.0271 |          0.9831 |     0.3938 |         -23.7122 |                     2 |                          0.4985 |
|     15 |                      45 |                        0.1  |            132 |               0.1021 |                0.0951 |   -9.0858 | -0.0688 |        -1.7708 |  -0.0787 |          0.8886 |     0.3788 |         -22.5    |                     1 |                          0.4318 |
|     16 |                      30 |                        0    |            522 |               0.4037 |                0.3001 |  -22.8078 | -0.0437 |        -4.4451 |  -0.098  |          0.9284 |     0.3851 |         -45.3601 |                     3 |                          0.4981 |
|     17 |                      45 |                        0    |            205 |               0.1585 |                0.1423 |  -18.0929 | -0.0883 |        -3.5262 |  -0.1217 |          0.8581 |     0.3707 |         -28.9833 |                     2 |                          0.4195 |
|     18 |                      30 |                        0.1  |            340 |               0.263  |                0.2181 |  -21.4161 | -0.063  |        -4.1739 |  -0.139  |          0.8978 |     0.3765 |         -30.0286 |                     3 |                          0.4882 |
|     19 |                      45 |                        0.25 |             33 |               0.0255 |                0.0232 |   -7.9045 | -0.2395 |        -1.5406 |  -0.1638 |          0.6497 |     0.303  |          -9.4045 |                     2 |                          0.3939 |
|     20 |                      60 |                        0    |             90 |               0.0696 |                0.0681 |   -9.1451 | -0.1016 |        -1.7823 |  -0.1782 |          0.8379 |     0.3667 |         -10      |                     1 |                          0.2889 |

## Best Challenger Year Split

|   year | period                   |   trades |   win_rate |   total_r |   avg_r |   profit_factor |   max_drawdown_r |
|-------:|:-------------------------|---------:|-----------:|----------:|--------:|----------------:|-----------------:|
|   2021 | 2021-07-01 to 2021-12-29 |        6 |     0.5    |    1.5    |  0.25   |          1.5    |               -2 |
|   2022 | 2022-03-14 to 2022-12-19 |       17 |     0.4706 |    3      |  0.1765 |          1.3333 |               -4 |
|   2023 | 2023-01-16 to 2023-11-21 |       13 |     0.5385 |    4.1622 |  0.3202 |          1.6937 |               -2 |
|   2024 | 2024-02-06 to 2024-02-06 |        1 |     0      |   -1      | -1      |          0      |                0 |
|   2025 | 2025-03-28 to 2025-12-08 |        6 |     0.3333 |   -1      | -0.1667 |          0.75   |               -2 |
|   2026 | 2026-03-11 to 2026-05-25 |        2 |     0.5    |   -0.2459 | -0.123  |          0.7541 |                0 |

## Summary Read

- Best BOS row: `60m` consolidation with `10%` range buffer; `45` trades, `0.0348` trades/day, `+6.42R`, PF `1.267`, max DD `-5.00R`.
- Best daily-cadence BOS row is the `15m` consolidation with `0%` range buffer: it reaches `1.03` trades/day and is positive, but drawdown is much worse than the current sweep/reclaim 3m leg.
- Best near-daily BOS row is the `15m` consolidation with `10%` range buffer: better PF and total R than the daily-cadence BOS row, but only `0.80` trades/day and still worse drawdown than the sweep/reclaim long-only baseline.
- This tests whether a structure shift can replace the consolidation-low sweep/reclaim. It should be compared mainly against the long-only sweep/reclaim baseline, not the full long+short baseline.
- Treat this as a challenger screen only. Promotion would require exact replay and train/validation before prop-firm lifecycle scoring.
