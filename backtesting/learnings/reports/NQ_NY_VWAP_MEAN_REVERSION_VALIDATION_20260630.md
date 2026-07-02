# NQ NY VWAP Mean-Reversion Validation Packet

- Run slug: `nq_ny_vwap_mean_reversion_validation_20260630`
- Candidate: `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2` + `reject_vwap_side_slope` + `efficiency_max=0.65` + `session_range_atr_max=2.0` + `10:00-14:00`
- Recent validation window: `2021-06-05` to `<2026-06-06`
- Cold older stress window: `2016-01-01` to `<2021-06-05`
- Deployability: `research_only`; exact replay and live execution support are still required before any deployment discussion.

## Step 0: Current Candidate Replay

| label   |   trades |   trading_days |   avg_trades_per_day |   days_with_trade |   pct_days_with_trade |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |
|:--------|---------:|---------------:|---------------------:|------------------:|----------------------:|----------:|--------:|----------------:|-----------:|-----------------:|
| best_5m |      370 |           1293 |               0.2862 |               339 |                0.2622 |   127.777 |  0.3453 |          1.5563 |     0.3703 |         -12.1977 |

## Step 1: Validation

### Recent split and annual/rolling windows

| label                              |   trades |   trading_days |   avg_trades_per_day |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |
|:-----------------------------------|---------:|---------------:|---------------------:|----------:|--------:|----------------:|-----------:|-----------------:|
| recent_full                        |      370 |           1293 |               0.2862 |  127.777  |  0.3453 |          1.5563 |     0.3703 |         -12.1977 |
| retrospective_dev_2021_2023        |      177 |            665 |               0.2662 |   68.0535 |  0.3845 |          1.6207 |     0.3672 |         -12.1977 |
| retrospective_validation_2024_2026 |      193 |            628 |               0.3073 |   59.7232 |  0.3094 |          1.4974 |     0.3731 |          -9.2293 |
| year_2021                          |       39 |            149 |               0.2617 |    8.8887 |  0.2279 |          1.3648 |     0.359  |         -12.1977 |
| year_2022                          |       60 |            258 |               0.2326 |   16.486  |  0.2748 |          1.4122 |     0.3167 |         -10.4494 |
| year_2023                          |       78 |            258 |               0.3023 |   42.6788 |  0.5472 |          1.9427 |     0.4103 |          -7.7523 |
| year_2024                          |       95 |            259 |               0.3668 |   43.032  |  0.453  |          1.7549 |     0.4    |          -8.281  |
| year_2025                          |       72 |            258 |               0.2791 |    6.5258 |  0.0906 |          1.1387 |     0.3333 |          -9.2293 |
| year_2026                          |       26 |            111 |               0.2342 |   10.1654 |  0.391  |          1.6353 |     0.3846 |          -3.3205 |
| rolling_6m_2021-07-01_2021-12-31   |       33 |            131 |               0.2519 |    6.347  |  0.1923 |          1.2971 |     0.3333 |         -12.1977 |
| rolling_6m_2022-01-01_2022-06-30   |       29 |            128 |               0.2266 |   -5.5508 | -0.1914 |          0.7477 |     0.2414 |         -10.4494 |
| rolling_6m_2022-07-01_2022-12-31   |       31 |            130 |               0.2385 |   22.0368 |  0.7109 |          2.2243 |     0.3871 |          -6      |
| rolling_6m_2023-01-01_2023-06-30   |       38 |            129 |               0.2946 |   33.8681 |  0.8913 |          2.6934 |     0.4737 |          -6      |
| rolling_6m_2023-07-01_2023-12-31   |       40 |            129 |               0.3101 |    8.8107 |  0.2203 |          1.3486 |     0.35   |          -7.7523 |
| rolling_6m_2024-01-01_2024-06-30   |       50 |            128 |               0.3906 |   16.3474 |  0.3269 |          1.5109 |     0.36   |          -8.281  |
| rolling_6m_2024-07-01_2024-12-31   |       45 |            131 |               0.3435 |   26.6846 |  0.593  |          2.0674 |     0.4444 |          -5      |
| rolling_6m_2025-01-01_2025-06-30   |       36 |            127 |               0.2835 |    3.4087 |  0.0947 |          1.1545 |     0.3611 |          -6.6336 |
| rolling_6m_2025-07-01_2025-12-31   |       36 |            131 |               0.2748 |    3.1171 |  0.0866 |          1.1247 |     0.3056 |          -6.793  |
| rolling_6m_2026-01-01_2026-06-30   |       26 |            111 |               0.2342 |   10.1654 |  0.391  |          1.6353 |     0.3846 |          -3.3205 |

### Cold older-window stress

| label                |   trades |   trading_days |   avg_trades_per_day |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |
|:---------------------|---------:|---------------:|---------------------:|----------:|--------:|----------------:|-----------:|-----------------:|
| cold_2016_to_2021_06 |      441 |           1400 |                0.315 |    7.5234 |  0.0171 |          1.0248 |     0.3061 |         -45.1152 |

## Step 2: Sensitivity

|   rank |   slope_threshold |   efficiency_max |   session_range_atr_max | time_bucket   |   trades |   avg_trades_per_day |   total_r |   avg_r |   profit_factor |   max_drawdown_r |
|-------:|------------------:|-----------------:|------------------------:|:--------------|---------:|---------------------:|----------:|--------:|----------------:|-----------------:|
|      1 |              0.02 |             0.7  |                    2    | 10:00-15:00   |      619 |               0.4787 |   134.715 |  0.2176 |          1.3349 |         -28.9848 |
|      2 |              0.02 |             0.7  |                    2    | full          |      619 |               0.4787 |   134.715 |  0.2176 |          1.3349 |         -28.9848 |
|      3 |              0.02 |             0.7  |                    2    | 11:00-15:00   |      618 |               0.478  |   133.873 |  0.2166 |          1.3328 |         -28.9848 |
|      4 |              0.02 |             0.7  |                    2.25 | 10:00-15:00   |      620 |               0.4795 |   133.715 |  0.2157 |          1.3316 |         -28.9848 |
|      5 |              0.02 |             0.7  |                    2.25 | full          |      620 |               0.4795 |   133.715 |  0.2157 |          1.3316 |         -28.9848 |
|      6 |              0.02 |             0.7  |                  nan    | 10:00-15:00   |      620 |               0.4795 |   133.715 |  0.2157 |          1.3316 |         -28.9848 |
|      7 |              0.02 |             0.7  |                  nan    | full          |      620 |               0.4795 |   133.715 |  0.2157 |          1.3316 |         -28.9848 |
|      8 |              0.02 |             0.7  |                    2.25 | 11:00-15:00   |      619 |               0.4787 |   132.873 |  0.2147 |          1.3295 |         -28.9848 |
|      9 |              0.02 |             0.7  |                  nan    | 11:00-15:00   |      619 |               0.4787 |   132.873 |  0.2147 |          1.3295 |         -28.9848 |
|     10 |              0.02 |             0.7  |                    1.5  | 10:00-15:00   |      613 |               0.4741 |   131.668 |  0.2148 |          1.3306 |         -28.9848 |
|     11 |              0.02 |             0.7  |                    1.5  | full          |      613 |               0.4741 |   131.668 |  0.2148 |          1.3306 |         -28.9848 |
|     12 |              0.02 |             0.7  |                    2    | 10:00-14:00   |      408 |               0.3155 |   131.018 |  0.3211 |          1.5164 |         -12.6167 |
|     13 |              0.02 |             0.7  |                    1.5  | 11:00-15:00   |      612 |               0.4733 |   130.826 |  0.2138 |          1.3285 |         -28.9848 |
|     14 |              0.02 |             0.7  |                    1.75 | 10:00-15:00   |      616 |               0.4764 |   130.211 |  0.2114 |          1.3253 |         -28.9848 |
|     15 |              0.02 |             0.7  |                    1.75 | full          |      616 |               0.4764 |   130.211 |  0.2114 |          1.3253 |         -28.9848 |
|     16 |              0.02 |             0.7  |                    2.25 | 10:00-14:00   |      409 |               0.3163 |   130.018 |  0.3179 |          1.5105 |         -12.6167 |
|     17 |              0.02 |             0.7  |                  nan    | 10:00-14:00   |      409 |               0.3163 |   130.018 |  0.3179 |          1.5105 |         -12.6167 |
|     18 |              0.02 |             0.7  |                    1.75 | 11:00-15:00   |      615 |               0.4756 |   129.369 |  0.2104 |          1.3232 |         -28.9848 |
|     19 |              0.02 |             0.65 |                    2    | 10:00-14:00   |      370 |               0.2862 |   127.777 |  0.3453 |          1.5563 |         -12.1977 |
|     20 |              0.02 |             0.65 |                    2.25 | 10:00-14:00   |      371 |               0.2869 |   126.777 |  0.3417 |          1.5495 |         -12.1977 |

## Step 3: 1m/1s Path Replay

### Original VWAP-target candidate

| path_label   | available   |   trades |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   exit_type_changes |   total_r_delta_vs_5m |
|:-------------|:------------|---------:|----------:|--------:|----------------:|-----------:|-----------------:|--------------------:|----------------------:|
| 1m           | True        |      370 |   127.256 |  0.3439 |          1.5545 |     0.3703 |         -12.0113 |                   1 |               -0.5205 |
| 1s           | True        |      370 |   127.72  |  0.3452 |          1.5564 |     0.3703 |         -12.0535 |                   1 |               -0.0571 |

### Exit-refined candidate

| path_label   | available   |   trades |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   exit_type_changes |   total_r_delta_vs_5m |
|:-------------|:------------|---------:|----------:|--------:|----------------:|-----------:|-----------------:|--------------------:|----------------------:|
| 1m           | True        |      368 |   144.823 |  0.3935 |           1.637 |     0.375  |         -11.4561 |                   1 |               -0.4888 |
| 1s           | True        |      368 |   152.999 |  0.4158 |           1.679 |     0.3804 |          -9.153  |                   4 |                7.687  |

## Step 4: Exit/Stop Refinement

|   rank | exit_model                         |   trades |   avg_trades_per_day |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |
|-------:|:-----------------------------------|---------:|---------------------:|----------:|--------:|----------------:|-----------:|-----------------:|
|      1 | signal_1x_to_day_mid               |      368 |               0.2846 |  145.312  |  0.3949 |          1.6392 |     0.375  |         -11.5293 |
|      2 | signal_1x_to_partial_75_to_vwap    |      374 |               0.2892 |  134.699  |  0.3602 |          1.6528 |     0.4412 |         -11.5773 |
|      3 | signal_1x_to_vwap                  |      370 |               0.2862 |  127.777  |  0.3453 |          1.5563 |     0.3703 |         -12.1977 |
|      4 | signal_1.5x_to_day_mid             |      365 |               0.2823 |  117.943  |  0.3231 |          1.5542 |     0.4082 |         -11.3418 |
|      5 | signal_0.5x_to_partial_75_to_vwap  |      380 |               0.2939 |  116.141  |  0.3056 |          1.4901 |     0.3684 |         -19.8307 |
|      6 | signal_0x_to_day_mid               |      378 |               0.2923 |  100.942  |  0.267  |          1.3611 |     0.2566 |         -29.0038 |
|      7 | cons_edge_1x_to_partial_75_to_vwap |      381 |               0.2947 |   97.6535 |  0.2563 |          1.3965 |     0.3491 |         -23.836  |
|      8 | signal_1.5x_to_vwap                |      367 |               0.2838 |   95.8409 |  0.2611 |          1.4413 |     0.3978 |         -11.3517 |
|      9 | signal_1.5x_to_partial_75_to_vwap  |      372 |               0.2877 |   94.9486 |  0.2552 |          1.4824 |     0.4624 |         -11.1719 |
|     10 | signal_0x_to_partial_75_to_vwap    |      384 |               0.297  |   93.8963 |  0.2445 |          1.3576 |     0.3125 |         -24.6955 |
|     11 | signal_0.5x_to_day_mid             |      374 |               0.2892 |   92.5124 |  0.2474 |          1.3614 |     0.3075 |         -17.1856 |
|     12 | signal_0x_to_vwap                  |      378 |               0.2923 |   85.5281 |  0.2263 |          1.3055 |     0.254  |         -31.0199 |
|     13 | signal_0.5x_to_vwap                |      376 |               0.2908 |   84.8824 |  0.2258 |          1.3298 |     0.3059 |         -16.9797 |
|     14 | signal_1x_to_fixed_1.5r            |      379 |               0.2931 |   74.2218 |  0.1958 |          1.383  |     0.4776 |         -14.4638 |
|     15 | cons_edge_1x_to_day_mid            |      374 |               0.2892 |   73.5172 |  0.1966 |          1.2761 |     0.2834 |         -22.0671 |
|     16 | signal_1.5x_to_fixed_1.5r          |      374 |               0.2892 |   64.3242 |  0.172  |          1.3321 |     0.4706 |         -12.8044 |
|     17 | cons_edge_1x_to_vwap               |      375 |               0.29   |   53.1829 |  0.1418 |          1.1968 |     0.2747 |         -23.6982 |
|     18 | signal_1x_to_fixed_1r              |      382 |               0.2954 |   47.8504 |  0.1253 |          1.2905 |     0.5602 |         -13      |
|     19 | signal_0.5x_to_fixed_1.5r          |      384 |               0.297  |   44.6444 |  0.1163 |          1.2132 |     0.4453 |         -12.3813 |
|     20 | cons_edge_1x_to_fixed_1.5r         |      385 |               0.2978 |   40.259  |  0.1046 |          1.1888 |     0.4416 |         -16.5    |

## Step 5: Prop-Firm Lifecycle

- Account model: `$2,000` EOD trailing drawdown capped at starting balance, `$3,000` pass target, `$1,500` first payout, `$0` fee, account starts every `14` days.
- Prop scores use the `1s` path replay trade stream when available.

|   rank |   risk_usd_per_r |   total_starts |   first_payout_rate |   pre_payout_bust_rate |   post_payout_bust_rate |   open_rate |   ev_per_start_usd |   marked_ev_per_start_usd |   avg_days_to_first_payout |   worst_min_cushion_usd |
|-------:|-----------------:|---------------:|--------------------:|-----------------------:|------------------------:|------------:|-------------------:|--------------------------:|---------------------------:|------------------------:|
|      1 |              175 |            131 |              0.7634 |                 0.0382 |                  0      |      0.9618 |            1145.04 |                  10241.6  |                     220.03 |                 -109.36 |
|      2 |              200 |            131 |              0.7557 |                 0.1069 |                  0.0076 |      0.8855 |            1133.59 |                   9935.68 |                     194.51 |                  -96.42 |
|      3 |              150 |            131 |              0.7023 |                 0      |                  0      |      1      |            1053.44 |                   9492    |                     233.05 |                  191.97 |
|      4 |              125 |            131 |              0.6641 |                 0      |                  0      |      1      |             996.18 |                   7910    |                     251.89 |                  493.31 |
|      5 |              100 |            131 |              0.6565 |                 0      |                  0      |      1      |             984.73 |                   6328    |                     300.06 |                  711.62 |
|      6 |               75 |            131 |              0.6412 |                 0      |                  0      |      1      |             961.83 |                   4746    |                     408.7  |                  896.52 |
|      7 |              250 |            131 |              0.6183 |                 0.2824 |                  0.084  |      0.6336 |             927.48 |                   9926.46 |                     109.8  |                 -226.45 |
|      8 |              300 |            131 |              0.5802 |                 0.3511 |                  0.0534 |      0.5954 |             870.23 |                  11887.4  |                      81.47 |                 -271.71 |
|      9 |              400 |            131 |              0.5649 |                 0.3893 |                  0.1221 |      0.4885 |             847.33 |                  12443.5  |                      53.38 |                 -399.92 |
|     10 |               50 |            131 |              0.5115 |                 0      |                  0      |      1      |             767.18 |                   3164    |                     603.84 |                 1052.32 |

### Exit-refined prop lifecycle

|   rank |   risk_usd_per_r |   total_starts |   first_payout_rate |   pre_payout_bust_rate |   post_payout_bust_rate |   open_rate |   ev_per_start_usd |   marked_ev_per_start_usd |   avg_days_to_first_payout |   worst_min_cushion_usd |
|-------:|-----------------:|---------------:|--------------------:|-----------------------:|------------------------:|------------:|-------------------:|--------------------------:|---------------------------:|------------------------:|
|      1 |              200 |            131 |              0.8702 |                 0      |                  0.0382 |      0.9618 |            1305.34 |                  13589.6  |                     177.25 |                  -90.7  |
|      2 |              175 |            131 |              0.855  |                 0      |                  0      |      1      |            1282.44 |                  12559.5  |                     216.69 |                   41.07 |
|      3 |              150 |            131 |              0.8244 |                 0      |                  0      |      1      |            1236.64 |                  10765.2  |                     244.12 |                  444.76 |
|      4 |              125 |            131 |              0.7863 |                 0      |                  0      |      1      |            1179.39 |                   8971.04 |                     270.64 |                  601.83 |
|      5 |              250 |            131 |              0.7405 |                 0.1603 |                  0.0534 |      0.7863 |            1110.69 |                  14107    |                     125.57 |                 -232.08 |
|      6 |              300 |            131 |              0.687  |                 0.2672 |                  0.1298 |      0.6031 |            1030.53 |                  13873.5  |                      86.62 |                 -273.87 |
|      7 |              100 |            131 |              0.6718 |                 0      |                  0      |      1      |            1007.63 |                   7176.83 |                     288.56 |                  776.98 |
|      8 |               75 |            131 |              0.6565 |                 0      |                  0      |      1      |             984.73 |                   5382.62 |                     365.86 |                  875.32 |
|      9 |              400 |            131 |              0.6336 |                 0.3282 |                  0.145  |      0.5267 |             950.38 |                  16130.7  |                      59.28 |                 -400.24 |
|     10 |               50 |            131 |              0.5802 |                 0      |                  0      |      1      |             870.23 |                   3588.42 |                     571.26 |                 1043.75 |

## Monte Carlo Bootstrap

### Original VWAP-target candidate

|   iterations |   sample_trades |   total_r_p05 |   total_r_median |   total_r_p95 |   max_dd_r_p05 |   max_dd_r_median |   max_dd_r_p95 |   prob_total_r_positive |   prob_dd_worse_than_20r |
|-------------:|----------------:|--------------:|-----------------:|--------------:|---------------:|------------------:|---------------:|------------------------:|-------------------------:|
|         2000 |             370 |          62.1 |           126.26 |        193.82 |         -27.48 |            -16.32 |            -11 |                  0.9995 |                    0.261 |

### Exit-refined candidate

|   iterations |   sample_trades |   total_r_p05 |   total_r_median |   total_r_p95 |   max_dd_r_p05 |   max_dd_r_median |   max_dd_r_p95 |   prob_total_r_positive |   prob_dd_worse_than_20r |
|-------------:|----------------:|--------------:|-----------------:|--------------:|---------------:|------------------:|---------------:|------------------------:|-------------------------:|
|         2000 |             368 |         83.88 |           151.35 |        228.98 |         -26.19 |            -15.55 |         -10.31 |                       1 |                   0.2045 |

## Summary Read

- The screenshot row is now confirmed as the current best **pure VWAP-target** mean-reversion research candidate: recent 5m `370` trades, `+127.78R`, PF `1.556`, max DD `-12.20R`.
- 1s path replay did **not** degrade the pure VWAP-target row: `+127.72R`, PF `1.556`, max DD `-12.05R`, only `1` exit-type change.
- Exit refinement improved the candidate materially. Keeping the same VWAP setup/context but targeting `day_mid` produced `+145.31R`, PF `1.639`, DD `-11.53R` on 5m and `+153.00R`, PF `1.679`, DD `-9.15R` on 1s.
- The biggest caution is regime history. The same fixed candidate on the older cold window (`2016-01-01` to `<2021-06-05`) was only `+7.52R`, PF `1.025`, with `-45.12R` max DD. This is not a universal all-regime edge; it is a recent-regime sleeve.
- Sensitivity is mixed: looser `efficiency_max=0.70` and wider time windows can raise total R (`+134.72R`) but with much worse drawdown (`-28.98R`) and lower PF (`1.335`). The tighter screenshot row remains the cleaner risk-adjusted anchor.
- Prop lifecycle is positive but should be treated as account-farming economics, not deployability. On 1s path trades, the pure VWAP-target row was best at `$175/R` (`76.34%` first-payout rate, `$1,145` EV/start, `3.82%` pre-payout bust). The exit-refined row was best at `$200/R` (`87.02%` first-payout rate, `$1,305` EV/start, `0%` pre-payout bust, `3.82%` post-payout bust).
- Any positive result remains `research_only` until the strategy is implemented as a live-native pre-trade gate and exact replay parity exists.

## Artifacts

- best_5m_trades: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/best_candidate_5m_trades.csv`
- best_exit_5m_trades: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/best_exit_refined_5m_trades.csv`
- validation: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/validation_windows.csv`
- cold_score: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/cold_window_score.csv`
- cold_trades: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/cold_window_trades.csv`
- sensitivity: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/sensitivity_grid.csv`
- exit_refinement: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/exit_stop_refinement.csv`
- path_replays: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/path_replay_trades.csv`
- path_summary: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/path_replay_summary.csv`
- exit_path_replays: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/exit_refined_path_replay_trades.csv`
- exit_path_summary: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/exit_refined_path_replay_summary.csv`
- prop_grid: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/prop_risk_grid.csv`
- best_prop_outcomes: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/best_prop_account_paths.csv`
- exit_prop_grid: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/exit_refined_prop_risk_grid.csv`
- exit_best_prop_outcomes: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/exit_refined_best_prop_account_paths.csv`
- summary: `data/results/nq_ny_vwap_mean_reversion_validation_20260630/summary.json`
