# NQ NY VWAP 3m Sweep + BOS Confirmation

- Run slug: `nq_ny_vwap_3m_sweep_bos_confirm_20260630`
- Data: `2021-06-05` to `<2026-06-06` from raw NQ 1m bars resampled to native 3m.
- Exit: fixed static `1.5:1` reward-to-risk with stop priority on same-bar stop/target touches.
- Stop: `atr14_prev` `7.5%` rounded to even NQ ticks, matching the current best 3m leg.
- Context: no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full NY RTH window.
- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.

## Confirmation Entry Criteria

1. Use the current 3m sweep/reclaim VWAP setup: extension from VWAP, 30-minute consolidation, sweep of the consolidation edge, reclaim close still on the VWAP side, and fixed 1.5R target.
2. Do not enter immediately on the sweep/reclaim bar.
3. Wait up to `N` minutes for a BOS close beyond `consolidation edge + buffer * consolidation range` while still on the VWAP side.
4. Enter on the next 3m bar open after the BOS confirmation. Maximum 3 sequential non-overlapping trades/day, about 10 minutes cooldown after exit.

The confirmation-window grid was `0`, `15`, `30`, `45`, and `60` minutes. The buffer grid was `0%`, `10%`, `25%`, and `50%` of the consolidation range.

## Baseline Controls

| label                                    |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |
|:-----------------------------------------|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|
| baseline_sweep_reclaim_3m_all_directions |           1498 |               1.1585 |                0.7224 |   82.182  |  0.0549 |        16.0169 |   0.7039 |          1.097  |     0.4266 |         -22.7535 |                     1 |
| baseline_sweep_reclaim_3m_long_only      |            497 |               0.3844 |                0.2831 |   64.5394 |  0.1299 |        12.5784 |   0.7331 |          1.2411 |     0.4527 |         -17.1575 |                     1 |
| baseline_sweep_reclaim_3m_short_only     |           1001 |               0.7742 |                0.4811 |   17.6426 |  0.0176 |         3.4385 |   0.1326 |          1.0305 |     0.4136 |         -25.9257 |                     2 |

## Best By Direction Scope

|   rank | direction_scope   |   confirmation_window_minutes |   breakout_buffer_range_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   fixed_target_reaches_mean_pct |
|-------:|:------------------|------------------------------:|----------------------------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|--------------------------------:|
|      7 | both              |                             0 |                         0.1 |              7 |               0.0054 |                0.0054 |    0.7222 |  0.1032 |         0.1408 |   0.0704 |          1.1912 |     0.4286 |             -2   |                     1 |                          0.1429 |
|      1 | long_only         |                            60 |                         0.5 |             50 |               0.0387 |                0.0387 |    9.6622 |  0.1932 |         1.8831 |   0.538  |          1.3716 |     0.48   |             -3.5 |                     0 |                          0.4    |

## Daily-Cadence Confirmation Rows

_None._

## Near-Daily Confirmation Rows

_None._

## Top Confirmation Rows

|   rank | direction_scope   |   confirmation_window_minutes |   breakout_buffer_range_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   fixed_target_reaches_mean_pct |
|-------:|:------------------|------------------------------:|----------------------------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|--------------------------------:|
|      1 | long_only         |                            60 |                        0.5  |             50 |               0.0387 |                0.0387 |    9.6622 |  0.1932 |         1.8831 |   0.538  |          1.3716 |     0.48   |          -3.5    |                     0 |                          0.4    |
|      2 | long_only         |                            30 |                        0.5  |             21 |               0.0162 |                0.0162 |    3.6622 |  0.1744 |         0.7137 |   0.2379 |          1.3329 |     0.4762 |          -3      |                     0 |                          0.4762 |
|      3 | long_only         |                            45 |                        0.5  |             38 |               0.0294 |                0.0294 |    4.1622 |  0.1095 |         0.8112 |   0.2318 |          1.1982 |     0.4474 |          -3.5    |                     1 |                          0.4474 |
|      4 | long_only         |                            15 |                        0    |             79 |               0.0611 |                0.0588 |    8.5    |  0.1076 |         1.6566 |   0.1578 |          1.1932 |     0.443  |         -10.5    |                     1 |                          0.4177 |
|      5 | long_only         |                            15 |                        0.1  |             56 |               0.0433 |                0.041  |    4      |  0.0714 |         0.7796 |   0.1299 |          1.125  |     0.4286 |          -6      |                     1 |                          0.3929 |
|      6 | long_only         |                            30 |                        0    |            125 |               0.0967 |                0.092  |    5      |  0.04   |         0.9745 |   0.075  |          1.0685 |     0.416  |         -13      |                     1 |                          0.384  |
|      7 | both              |                             0 |                        0.1  |              7 |               0.0054 |                0.0054 |    0.7222 |  0.1032 |         0.1408 |   0.0704 |          1.1912 |     0.4286 |          -2      |                     1 |                          0.1429 |
|      8 | both              |                            60 |                        0.5  |            171 |               0.1323 |                0.1315 |    5.5376 |  0.0324 |         1.0793 |   0.0617 |          1.0557 |     0.4152 |         -17.5    |                     1 |                          0.4795 |
|      9 | long_only         |                             0 |                        0.1  |              1 |               0.0008 |                0.0008 |    1.5    |  1.5    |         0.2923 |   0      |        inf      |     1      |           0      |                     0 |                          0      |
|     10 | long_only         |                             0 |                        0.25 |              1 |               0.0008 |                0.0008 |    1.5    |  1.5    |         0.2923 |   0      |        inf      |     1      |           0      |                     0 |                          0      |
|     11 | both              |                             0 |                        0.5  |              1 |               0.0008 |                0.0008 |    1.5    |  1.5    |         0.2923 |   0      |        inf      |     1      |           0      |                     0 |                          0      |
|     12 | both              |                             0 |                        0.25 |              3 |               0.0023 |                0.0023 |    2      |  0.6667 |         0.3898 |   0      |          3      |     0.6667 |           0      |                     0 |                          0      |
|     13 | long_only         |                             0 |                        0.5  |              0 |               0      |                0      |    0      |  0      |         0      |   0      |          0      |     0      |           0      |                     0 |                          0      |
|     14 | long_only         |                             0 |                        0    |              2 |               0.0015 |                0.0015 |    0.5    |  0.25   |         0.0974 |   0      |          1.5    |     0.5    |           0      |                     1 |                          0.5    |
|     15 | both              |                            30 |                        0    |            364 |               0.2815 |                0.2637 |   -0.4681 | -0.0013 |        -0.0912 |  -0.0031 |          0.9978 |     0.3984 |         -29.3264 |                     2 |                          0.4643 |
|     16 | both              |                            15 |                        0    |            219 |               0.1694 |                0.1616 |   -0.4931 | -0.0023 |        -0.0961 |  -0.005  |          0.9962 |     0.4018 |         -19.2778 |                     2 |                          0.4612 |
|     17 | both              |                            15 |                        0.1  |            162 |               0.1253 |                0.1199 |   -3.6681 | -0.0226 |        -0.7149 |  -0.0359 |          0.9626 |     0.3889 |         -19.8889 |                     2 |                          0.4815 |
|     18 | long_only         |                            60 |                        0    |            165 |               0.1276 |                0.1206 |   -2.5    | -0.0152 |        -0.4872 |  -0.0375 |          0.975  |     0.3939 |         -13      |                     2 |                          0.3939 |
|     19 | both              |                            30 |                        0.25 |            204 |               0.1578 |                0.1547 |   -5.4156 | -0.0265 |        -1.0555 |  -0.047  |          0.9562 |     0.3873 |         -22.4489 |                     2 |                          0.5049 |
|     20 | long_only         |                            30 |                        0.25 |             63 |               0.0487 |                0.048  |   -3.3378 | -0.053  |        -0.6505 |  -0.0566 |          0.9144 |     0.381  |         -11.5    |                     2 |                          0.4444 |

## Best Confirmation Year Split

|   year | period                   |   trades |   win_rate |   total_r |   avg_r |   profit_factor |   max_drawdown_r |
|-------:|:-------------------------|---------:|-----------:|----------:|--------:|----------------:|-----------------:|
|   2021 | 2021-08-11 to 2021-12-14 |        4 |     0.5    |    1      |  0.25   |          1.5    |               -1 |
|   2022 | 2022-01-07 to 2022-12-28 |       21 |     0.4762 |    4      |  0.1905 |          1.3636 |               -3 |
|   2023 | 2023-01-03 to 2023-11-06 |       10 |     0.6    |    4.6622 |  0.4662 |          2.1656 |               -1 |
|   2024 | 2024-01-26 to 2024-09-26 |        6 |     0.5    |    1.5    |  0.25   |          1.5    |               -1 |
|   2025 | 2025-01-07 to 2025-12-08 |        7 |     0.4286 |    0.5    |  0.0714 |          1.125  |               -2 |
|   2026 | 2026-02-23 to 2026-05-04 |        2 |     0      |   -2      | -1      |          0      |               -1 |

## Summary Read

- Best confirmation row: `long_only` with `60m` confirmation window and `50%` range buffer; `50` trades, `0.0387` trades/day, `+9.66R`, PF `1.372`, max DD `-3.50R`.
- This tests BOS as an extra confirmation after the sweep/reclaim, not as a replacement.
- Treat this as a challenger screen only. Promotion would require exact replay and train/validation before prop-firm lifecycle scoring.
