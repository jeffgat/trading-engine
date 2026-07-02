# NQ NY VWAP Static 1:1.5R Stop Sweep

- Run slug: `nq_ny_vwap_static_rr_stop_sweep_20260630`
- Data: `2021-06-05` to `<2026-06-06` using NQ 5m RTH bars
- Trading days: `1293`
- Base setup: `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2` high-cadence VWAP state-machine anchor
- Context: no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full window
- Exit: static fixed `1.5:1` reward-to-risk, conservative 5m path with stop priority on same-bar stop/target touches
- Stop basis is known at signal time: previous daily ATR, prior RTH session range, or current session range-so-far.
- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.

## Top Rows By Calmar

|   rank | stop_basis           |   stop_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   avg_stop_points |   fixed_target_reaches_mean_pct | deployability   |
|-------:|:---------------------|-----------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|------------------:|--------------------------------:|:----------------|
|      1 | prior_session_range  |      0.1   |           1347 |               1.0418 |                0.7053 |   43.2007 |  0.0321 |         8.4196 |   0.2691 |          1.0571 |     0.4224 |         -31.2837 |                     1 |             25.21 |                          0.7988 | research_only   |
|      2 | prior_session_range  |      0.15  |           1239 |               0.9582 |                0.7053 |   28.4849 |  0.023  |         5.5516 |   0.2366 |          1.0436 |     0.431  |         -23.4671 |                     0 |             37.66 |                          0.5682 | research_only   |
|      3 | session_range_so_far |      0.15  |           1314 |               1.0162 |                0.7053 |   26.7018 |  0.0203 |         5.2041 |   0.1723 |          1.0368 |     0.4224 |         -30.1952 |                     1 |             30.13 |                          0.7831 | research_only   |
|      4 | atr14_prev           |      0.075 |           1411 |               1.0913 |                0.7053 |   25.1823 |  0.0178 |         4.9079 |   0.1423 |          1.0306 |     0.4103 |         -34.5015 |                     2 |             20.51 |                          0.9036 | research_only   |
|      5 | atr14_prev           |      0.05  |           1485 |               1.1485 |                0.7053 |   33.6912 |  0.0227 |         6.5663 |   0.1415 |          1.0386 |     0.4088 |         -46.3884 |                     1 |             13.83 |                          0.9663 | research_only   |
|      6 | prior_session_range  |      0.075 |           1424 |               1.1013 |                0.7053 |   37.776  |  0.0265 |         7.3624 |   0.1302 |          1.0458 |     0.415  |         -56.5613 |                     1 |             19.15 |                          0.9024 | research_only   |
|      7 | session_range_so_far |      0.1   |           1433 |               1.1083 |                0.7053 |   21.9226 |  0.0153 |         4.2726 |   0.1175 |          1.0263 |     0.4117 |         -36.3608 |                     2 |             20.3  |                          0.9421 | research_only   |
|      8 | session_range_so_far |      0.2   |           1224 |               0.9466 |                0.7053 |   15.5744 |  0.0127 |         3.0354 |   0.105  |          1.0242 |     0.4314 |         -28.9154 |                     0 |             39.91 |                          0.6127 | research_only   |
|      9 | prior_session_range  |      0.2   |           1139 |               0.8809 |                0.7053 |    9.4744 |  0.0083 |         1.8465 |   0.0816 |          1.0171 |     0.4363 |         -22.6339 |                     1 |             49.95 |                          0.3802 | research_only   |
|     10 | session_range_so_far |      0.075 |           1478 |               1.1431 |                0.7053 |   18.8427 |  0.0127 |         3.6724 |   0.0597 |          1.0215 |     0.4053 |         -61.5398 |                     2 |             15.33 |                          0.9804 | research_only   |
|     11 | session_range_so_far |      0.25  |           1152 |               0.891  |                0.7053 |    9.4622 |  0.0082 |         1.8441 |   0.0572 |          1.0167 |     0.4366 |         -32.2375 |                     1 |             49.94 |                          0.3533 | research_only   |
|     12 | prior_session_range  |      0.05  |           1494 |               1.1555 |                0.7053 |    7.0879 |  0.0047 |         1.3814 |   0.0161 |          1.008  |     0.4023 |         -85.6825 |                     3 |             12.95 |                          0.9659 | research_only   |
|     13 | session_range_so_far |      0.3   |           1094 |               0.8461 |                0.7053 |   -9.5924 | -0.0088 |        -1.8695 |  -0.0421 |          0.9808 |     0.4369 |         -44.4541 |                     1 |             59.7  |                          0.1362 | research_only   |
|     14 | atr14_prev           |      0.1   |           1324 |               1.024  |                0.7053 |  -11.7987 | -0.0089 |        -2.2995 |  -0.0455 |          0.9846 |     0.4048 |         -50.543  |                     1 |             27.19 |                          0.7598 | research_only   |
|     15 | atr14_prev           |      0.125 |           1259 |               0.9737 |                0.7053 |   -8.5286 | -0.0068 |        -1.6622 |  -0.0496 |          0.9878 |     0.4138 |         -33.5158 |                     1 |             33.89 |                          0.5925 | research_only   |

## Frequency-Fit Rows

|   rank | stop_basis           |   stop_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   avg_stop_points |   fixed_target_reaches_mean_pct | deployability   |
|-------:|:---------------------|-----------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|------------------:|--------------------------------:|:----------------|
|      1 | prior_session_range  |      0.1   |           1347 |               1.0418 |                0.7053 |   43.2007 |  0.0321 |         8.4196 |   0.2691 |          1.0571 |     0.4224 |         -31.2837 |                     1 |             25.21 |                          0.7988 | research_only   |
|      3 | session_range_so_far |      0.15  |           1314 |               1.0162 |                0.7053 |   26.7018 |  0.0203 |         5.2041 |   0.1723 |          1.0368 |     0.4224 |         -30.1952 |                     1 |             30.13 |                          0.7831 | research_only   |
|      4 | atr14_prev           |      0.075 |           1411 |               1.0913 |                0.7053 |   25.1823 |  0.0178 |         4.9079 |   0.1423 |          1.0306 |     0.4103 |         -34.5015 |                     2 |             20.51 |                          0.9036 | research_only   |
|      5 | atr14_prev           |      0.05  |           1485 |               1.1485 |                0.7053 |   33.6912 |  0.0227 |         6.5663 |   0.1415 |          1.0386 |     0.4088 |         -46.3884 |                     1 |             13.83 |                          0.9663 | research_only   |
|      6 | prior_session_range  |      0.075 |           1424 |               1.1013 |                0.7053 |   37.776  |  0.0265 |         7.3624 |   0.1302 |          1.0458 |     0.415  |         -56.5613 |                     1 |             19.15 |                          0.9024 | research_only   |
|      7 | session_range_so_far |      0.1   |           1433 |               1.1083 |                0.7053 |   21.9226 |  0.0153 |         4.2726 |   0.1175 |          1.0263 |     0.4117 |         -36.3608 |                     2 |             20.3  |                          0.9421 | research_only   |
|     10 | session_range_so_far |      0.075 |           1478 |               1.1431 |                0.7053 |   18.8427 |  0.0127 |         3.6724 |   0.0597 |          1.0215 |     0.4053 |         -61.5398 |                     2 |             15.33 |                          0.9804 | research_only   |
|     12 | prior_session_range  |      0.05  |           1494 |               1.1555 |                0.7053 |    7.0879 |  0.0047 |         1.3814 |   0.0161 |          1.008  |     0.4023 |         -85.6825 |                     3 |             12.95 |                          0.9659 | research_only   |
|     14 | atr14_prev           |      0.1   |           1324 |               1.024  |                0.7053 |  -11.7987 | -0.0089 |        -2.2995 |  -0.0455 |          0.9846 |     0.4048 |         -50.543  |                     1 |             27.19 |                          0.7598 | research_only   |
|     16 | atr14_prev           |      0.03  |           1540 |               1.191  |                0.7053 |  -37.6488 | -0.0244 |        -7.3376 |  -0.0862 |          0.9598 |     0.3896 |         -85.1488 |                     3 |              8.43 |                          0.9922 | research_only   |
|     17 | session_range_so_far |      0.05  |           1525 |               1.1794 |                0.7053 |  -44      | -0.0289 |        -8.5754 |  -0.088  |          0.9528 |     0.3882 |         -97.5    |                     4 |             10.35 |                          0.9961 | research_only   |

## Frequency-Fit Rows With PF >= 1.05

|   rank | stop_basis          |   stop_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   avg_stop_points |   fixed_target_reaches_mean_pct | deployability   |
|-------:|:--------------------|-----------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|------------------:|--------------------------------:|:----------------|
|      1 | prior_session_range |        0.1 |           1347 |               1.0418 |                0.7053 |   43.2007 |  0.0321 |         8.4196 |   0.2691 |          1.0571 |     0.4224 |         -31.2837 |                     1 |             25.21 |                          0.7988 | research_only   |

## Best By Stop Basis

| stop_basis           |   rank |   stop_pct |   total_trades |   avg_trades_per_day |   total_r |   calmar |   profit_factor |   max_drawdown_r |   avg_stop_points |
|:---------------------|-------:|-----------:|---------------:|---------------------:|----------:|---------:|----------------:|-----------------:|------------------:|
| atr14_prev           |      4 |      0.075 |           1411 |               1.0913 |   25.1823 |   0.1423 |          1.0306 |         -34.5015 |             20.51 |
| prior_session_range  |      1 |      0.1   |           1347 |               1.0418 |   43.2007 |   0.2691 |          1.0571 |         -31.2837 |             25.21 |
| session_range_so_far |      3 |      0.15  |           1314 |               1.0162 |   26.7018 |   0.1723 |          1.0368 |         -30.1952 |             30.13 |

## Best Row Year Split

|   year | period                   |   trades |   win_rate |   total_r |   avg_r |   profit_factor |   max_drawdown_r |
|-------:|:-------------------------|---------:|-----------:|----------:|--------:|----------------:|-----------------:|
|   2021 | 2021-06-07 to 2021-12-31 |      157 |     0.4013 |   -3.2804 | -0.0209 |          0.9647 |         -18.7879 |
|   2022 | 2022-01-03 to 2022-12-30 |      276 |     0.4203 |   10.553  |  0.0382 |          1.068  |         -17.6549 |
|   2023 | 2023-01-03 to 2023-12-27 |      288 |     0.3854 |  -16.1322 | -0.056  |          0.9063 |         -25.1322 |
|   2024 | 2024-01-02 to 2024-12-31 |      254 |     0.4528 |   23.8691 |  0.094  |          1.1738 |         -13.8208 |
|   2025 | 2025-01-03 to 2025-12-29 |      263 |     0.4411 |   17.1475 |  0.0652 |          1.1221 |         -22.5294 |
|   2026 | 2026-01-05 to 2026-06-04 |      109 |     0.4404 |   11.0437 |  0.1013 |          1.1872 |         -10      |

## Summary Read

- Best static-RR row: `prior_session_range_pct10_rr1.5` with `1347` trades, `1.0418` trades/day, `+43.20R`, PF `1.057`, Calmar `0.269`, max DD `-31.28R`.
- Frequency-fit rows (`1-3` trades/day and >=70% day coverage): `11`.
- Frequency-fit rows with PF `>=1.05`: `1`.
- Treat this as a 5m research screen. Any survivor still needs 1m/1s path replay and prop-firm lifecycle scoring before promotion.

## Artifacts

- Sweep results: `backtesting/data/results/nq_ny_vwap_static_rr_stop_sweep_20260630/sweep_results.csv`
- Top trades: `backtesting/data/results/nq_ny_vwap_static_rr_stop_sweep_20260630/top_static_rr_trades.csv`
- Top yearly: `backtesting/data/results/nq_ny_vwap_static_rr_stop_sweep_20260630/top_static_rr_yearly.csv`
- Summary JSON: `backtesting/data/results/nq_ny_vwap_static_rr_stop_sweep_20260630/summary.json`
