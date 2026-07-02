# NQ NY VWAP Static 1:1.5R Native Timeframe Sweep

- Run slug: `nq_ny_vwap_static_rr_timeframe_sweep_20260630`
- Data: `2021-06-05` to `<2026-06-06` from raw NQ 1m bars; 2m/3m/5m were resampled from 1m for alignment.
- Timeframes: `1m, 2m, 3m, 5m`
- Setup was time-normalized: 30-minute consolidation, 60-minute setup timeout, and about 10-minute post-exit cooldown.
- Context: no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full window.
- Exit: static fixed `1.5:1` reward-to-risk, conservative OHLC path with stop priority on same-bar stop/target touches.
- Stop basis is known at signal time: previous daily ATR, prior RTH session range, or current session range-so-far.
- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.

## Entry Criteria

Long setup:

1. During NY RTH, use session VWAP as the mean.
2. Price must be below VWAP and extend at least `0.025 * prior 14-day RTH ATR` away from VWAP.
3. After the extension, wait for a 30-minute consolidation below VWAP whose high-low range is no more than `0.20 * ATR`.
4. The consolidation must remain below VWAP, and the consolidation low must still be at least `0.025 * ATR` below VWAP.
5. Signal bar must sweep below the consolidation low, then close back above that consolidation low while still closing below VWAP.
6. Enter long on the next bar open. Maximum 3 trades/day, non-overlapping, with about 10 minutes cooldown after exit.

Short setup is the mirror image above VWAP: extension above VWAP, tight consolidation above VWAP, sweep above consolidation high, close back below that high while still above VWAP, then short next bar open.

Static exit used in this sweep: stop from selected volatility basis, target fixed at `1.5R`, flat by `15:55` if neither stop nor target hits.

## Best By Timeframe

| timeframe   |   consolidation_bars |   setup_timeout_bars |   cooldown_bars | stop_basis           |   stop_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |
|:------------|---------------------:|---------------------:|----------------:|:---------------------|-----------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|
| 1m          |                   30 |                   60 |              10 | session_range_so_far |      0.1   |           1707 |               1.3202 |                0.7602 |   22.931  |  0.0134 |         4.4692 |   0.0605 |          1.0229 |     0.4107 |         -73.8769 |                     2 |
| 2m          |                   15 |                   30 |               5 | prior_session_range  |      0.075 |           1643 |               1.2707 |                0.7479 |   78.8366 |  0.048  |        15.3649 |   0.3123 |          1.0842 |     0.4254 |         -49.1961 |                     2 |
| 3m          |                   10 |                   20 |               4 | atr14_prev           |      0.075 |           1498 |               1.1585 |                0.7224 |   82.182  |  0.0549 |        16.0169 |   0.7039 |          1.097  |     0.4266 |         -22.7535 |                     1 |
| 5m          |                    6 |                   12 |               2 | prior_session_range  |      0.1   |           1347 |               1.0418 |                0.7053 |   43.2007 |  0.0321 |         8.4196 |   0.2691 |          1.0571 |     0.4224 |         -31.2837 |                     1 |

## Direct Carry-Forward: Prior Session Range 10% Stop

| timeframe   |   consolidation_bars |   setup_timeout_bars |   cooldown_bars | stop_basis          |   stop_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |
|:------------|---------------------:|---------------------:|----------------:|:--------------------|-----------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|
| 1m          |                   30 |                   60 |              10 | prior_session_range |        0.1 |           1591 |               1.2305 |                0.7602 |  -19.2872 | -0.0121 |        -3.759  |  -0.0372 |          0.9791 |     0.4054 |        -101.052  |                     2 |
| 2m          |                   15 |                   30 |               5 | prior_session_range |        0.1 |           1540 |               1.191  |                0.7479 |   33.709  |  0.0219 |         6.5697 |   0.1598 |          1.0387 |     0.4201 |         -41.1149 |                     2 |
| 3m          |                   10 |                   20 |               4 | prior_session_range |        0.1 |           1424 |               1.1013 |                0.7224 |   73.8797 |  0.0519 |        14.3988 |   0.3369 |          1.0935 |     0.4277 |         -42.7356 |                     2 |
| 5m          |                    6 |                   12 |               2 | prior_session_range |        0.1 |           1347 |               1.0418 |                0.7053 |   43.2007 |  0.0321 |         8.4196 |   0.2691 |          1.0571 |     0.4224 |         -31.2837 |                     1 |

## Top Rows Overall

|   rank | timeframe   | stop_basis           |   stop_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   avg_stop_points | deployability   |
|-------:|:------------|:---------------------|-----------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|------------------:|:----------------|
|      1 | 3m          | atr14_prev           |      0.075 |           1498 |               1.1585 |                0.7224 |   82.182  |  0.0549 |        16.0169 |   0.7039 |          1.097  |     0.4266 |         -22.7535 |                     1 |             20.52 | research_only   |
|      2 | 3m          | session_range_so_far |      0.075 |           1580 |               1.222  |                0.7224 |   98.4436 |  0.0623 |        19.1862 |   0.7009 |          1.1089 |     0.4272 |         -27.375  |                     1 |             15.25 | research_only   |
|      3 | 3m          | prior_session_range  |      0.075 |           1517 |               1.1732 |                0.7224 |  117.382  |  0.0774 |        22.8772 |   0.5813 |          1.1386 |     0.4324 |         -39.3538 |                     1 |             18.9  | research_only   |
|      4 | 3m          | prior_session_range  |      0.05  |           1599 |               1.2367 |                0.7224 |   61.4945 |  0.0385 |        11.985  |   0.5424 |          1.066  |     0.4165 |         -22.0971 |                     1 |             12.81 | research_only   |
|      5 | 3m          | atr14_prev           |      0.05  |           1590 |               1.2297 |                0.7224 |   75.4035 |  0.0474 |        14.6958 |   0.5413 |          1.0819 |     0.4189 |         -27.1471 |                     1 |             13.86 | research_only   |
|      6 | 3m          | session_range_so_far |      0.15  |           1391 |               1.0758 |                0.7224 |   43.2222 |  0.0311 |         8.4238 |   0.3865 |          1.0566 |     0.4277 |         -21.7964 |                     1 |             29.84 | research_only   |
|      7 | 3m          | prior_session_range  |      0.1   |           1424 |               1.1013 |                0.7224 |   73.8797 |  0.0519 |        14.3988 |   0.3369 |          1.0935 |     0.4277 |         -42.7356 |                     2 |             24.96 | research_only   |
|      8 | 2m          | prior_session_range  |      0.075 |           1643 |               1.2707 |                0.7479 |   78.8366 |  0.048  |        15.3649 |   0.3123 |          1.0842 |     0.4254 |         -49.1961 |                     2 |             19.15 | research_only   |
|      9 | 3m          | session_range_so_far |      0.1   |           1520 |               1.1756 |                0.7224 |   51.8901 |  0.0341 |        10.1132 |   0.2716 |          1.0592 |     0.4178 |         -37.2311 |                     2 |             20.15 | research_only   |
|     10 | 5m          | prior_session_range  |      0.1   |           1347 |               1.0418 |                0.7053 |   43.2007 |  0.0321 |         8.4196 |   0.2691 |          1.0571 |     0.4224 |         -31.2837 |                     1 |             25.21 | research_only   |
|     11 | 2m          | session_range_so_far |      0.075 |           1708 |               1.321  |                0.7479 |   44.9378 |  0.0263 |         8.7582 |   0.2468 |          1.0449 |     0.4128 |         -35.4807 |                     2 |             15.29 | research_only   |
|     12 | 5m          | prior_session_range  |      0.15  |           1239 |               0.9582 |                0.7053 |   28.4849 |  0.023  |         5.5516 |   0.2366 |          1.0436 |     0.431  |         -23.4671 |                     0 |             37.66 | research_only   |
|     13 | 3m          | prior_session_range  |      0.15  |           1292 |               0.9992 |                0.7224 |   27.8035 |  0.0215 |         5.4188 |   0.2036 |          1.0405 |     0.4272 |         -26.6204 |                     2 |             36.94 | research_only   |
|     14 | 5m          | session_range_so_far |      0.15  |           1314 |               1.0162 |                0.7053 |   26.7018 |  0.0203 |         5.2041 |   0.1723 |          1.0368 |     0.4224 |         -30.1952 |                     1 |             30.13 | research_only   |
|     15 | 2m          | prior_session_range  |      0.1   |           1540 |               1.191  |                0.7479 |   33.709  |  0.0219 |         6.5697 |   0.1598 |          1.0387 |     0.4201 |         -41.1149 |                     2 |             25.11 | research_only   |
|     16 | 2m          | atr14_prev           |      0.05  |           1726 |               1.3349 |                0.7479 |   25.8755 |  0.015  |         5.043  |   0.154  |          1.0253 |     0.4073 |         -32.7528 |                     2 |             13.83 | research_only   |
|     17 | 5m          | atr14_prev           |      0.075 |           1411 |               1.0913 |                0.7053 |   25.1823 |  0.0178 |         4.9079 |   0.1423 |          1.0306 |     0.4103 |         -34.5015 |                     2 |             20.51 | research_only   |
|     18 | 5m          | atr14_prev           |      0.05  |           1485 |               1.1485 |                0.7053 |   33.6912 |  0.0227 |         6.5663 |   0.1415 |          1.0386 |     0.4088 |         -46.3884 |                     1 |             13.83 | research_only   |
|     19 | 5m          | prior_session_range  |      0.075 |           1424 |               1.1013 |                0.7053 |   37.776  |  0.0265 |         7.3624 |   0.1302 |          1.0458 |     0.415  |         -56.5613 |                     1 |             19.15 | research_only   |
|     20 | 5m          | session_range_so_far |      0.1   |           1433 |               1.1083 |                0.7053 |   21.9226 |  0.0153 |         4.2726 |   0.1175 |          1.0263 |     0.4117 |         -36.3608 |                     2 |             20.3  | research_only   |

## Frequency-Fit Rows With PF >= 1.05

|   rank | timeframe   | stop_basis           |   stop_pct |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   avg_annual_r |   calmar |   profit_factor |   win_rate |   max_drawdown_r |   negative_full_years |   avg_stop_points | deployability   |
|-------:|:------------|:---------------------|-----------:|---------------:|---------------------:|----------------------:|----------:|--------:|---------------:|---------:|----------------:|-----------:|-----------------:|----------------------:|------------------:|:----------------|
|      1 | 3m          | atr14_prev           |      0.075 |           1498 |               1.1585 |                0.7224 |   82.182  |  0.0549 |        16.0169 |   0.7039 |          1.097  |     0.4266 |         -22.7535 |                     1 |             20.52 | research_only   |
|      2 | 3m          | session_range_so_far |      0.075 |           1580 |               1.222  |                0.7224 |   98.4436 |  0.0623 |        19.1862 |   0.7009 |          1.1089 |     0.4272 |         -27.375  |                     1 |             15.25 | research_only   |
|      3 | 3m          | prior_session_range  |      0.075 |           1517 |               1.1732 |                0.7224 |  117.382  |  0.0774 |        22.8772 |   0.5813 |          1.1386 |     0.4324 |         -39.3538 |                     1 |             18.9  | research_only   |
|      4 | 3m          | prior_session_range  |      0.05  |           1599 |               1.2367 |                0.7224 |   61.4945 |  0.0385 |        11.985  |   0.5424 |          1.066  |     0.4165 |         -22.0971 |                     1 |             12.81 | research_only   |
|      5 | 3m          | atr14_prev           |      0.05  |           1590 |               1.2297 |                0.7224 |   75.4035 |  0.0474 |        14.6958 |   0.5413 |          1.0819 |     0.4189 |         -27.1471 |                     1 |             13.86 | research_only   |
|      6 | 3m          | session_range_so_far |      0.15  |           1391 |               1.0758 |                0.7224 |   43.2222 |  0.0311 |         8.4238 |   0.3865 |          1.0566 |     0.4277 |         -21.7964 |                     1 |             29.84 | research_only   |
|      7 | 3m          | prior_session_range  |      0.1   |           1424 |               1.1013 |                0.7224 |   73.8797 |  0.0519 |        14.3988 |   0.3369 |          1.0935 |     0.4277 |         -42.7356 |                     2 |             24.96 | research_only   |
|      8 | 2m          | prior_session_range  |      0.075 |           1643 |               1.2707 |                0.7479 |   78.8366 |  0.048  |        15.3649 |   0.3123 |          1.0842 |     0.4254 |         -49.1961 |                     2 |             19.15 | research_only   |
|      9 | 3m          | session_range_so_far |      0.1   |           1520 |               1.1756 |                0.7224 |   51.8901 |  0.0341 |        10.1132 |   0.2716 |          1.0592 |     0.4178 |         -37.2311 |                     2 |             20.15 | research_only   |
|     10 | 5m          | prior_session_range  |      0.1   |           1347 |               1.0418 |                0.7053 |   43.2007 |  0.0321 |         8.4196 |   0.2691 |          1.0571 |     0.4224 |         -31.2837 |                     1 |             25.21 | research_only   |

## Best Overall Year Split

|   year | period                   |   trades |   win_rate |   total_r |   avg_r |   profit_factor |   max_drawdown_r |
|-------:|:-------------------------|---------:|-----------:|----------:|--------:|----------------:|-----------------:|
|   2021 | 2021-06-07 to 2021-12-31 |      178 |     0.4045 |   -0.3143 | -0.0018 |          0.997  |         -12.7714 |
|   2022 | 2022-01-03 to 2022-12-30 |      304 |     0.4342 |   20.3643 |  0.067  |          1.1191 |         -15.5    |
|   2023 | 2023-01-03 to 2023-12-27 |      316 |     0.4114 |   11.4019 |  0.0361 |          1.0628 |         -20.0121 |
|   2024 | 2024-01-03 to 2024-12-31 |      296 |     0.4392 |   25.0306 |  0.0846 |          1.1534 |         -11.2887 |
|   2025 | 2025-01-03 to 2025-12-31 |      278 |     0.4065 |   -1.1995 | -0.0043 |          0.9926 |         -17.0717 |
|   2026 | 2026-01-05 to 2026-06-04 |      126 |     0.4921 |   26.899  |  0.2135 |          1.4203 |          -6.5    |

## Summary Read

- Best overall native-timeframe row: `3m` `atr14_prev_pct7p5_rr1.5` with `1498` trades, `1.1585` trades/day, `+82.18R`, PF `1.097`, Calmar `0.704`, max DD `-22.75R`.
- Frequency-fit rows with PF `>=1.05`: `10` out of `120`.
- Treat this as a native-timeframe research screen. It still needs lower-timeframe exact replay, train/validation, and prop lifecycle scoring before promotion.

## Artifacts

- Sweep results: `backtesting/data/results/nq_ny_vwap_static_rr_timeframe_sweep_20260630/timeframe_sweep_results.csv`
- Best by timeframe: `backtesting/data/results/nq_ny_vwap_static_rr_timeframe_sweep_20260630/best_by_timeframe.csv`
- Prior-session-range 10% by timeframe: `backtesting/data/results/nq_ny_vwap_static_rr_timeframe_sweep_20260630/prior_session_range_pct10_by_timeframe.csv`
- Top trades: `backtesting/data/results/nq_ny_vwap_static_rr_timeframe_sweep_20260630/top_timeframe_static_rr_trades.csv`
- Top yearly: `backtesting/data/results/nq_ny_vwap_static_rr_timeframe_sweep_20260630/top_timeframe_static_rr_yearly.csv`
- Summary JSON: `backtesting/data/results/nq_ny_vwap_static_rr_timeframe_sweep_20260630/summary.json`
