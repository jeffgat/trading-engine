# ALPHA_V1 ORB Cap=2 Conditioned 10-Year Validation

- Requested check: validate the engine-backed `cap=2 + after_nonpositive_first` rule against the full available history.
- Available data window used: `2016-04-17` to `2026-03-24`.
- Current repo data ends on `2026-03-24`, so this is the longest available history rather than a literal through-today 10-year span.
- Rolling windows: full 2-year windows stepped yearly; the most recent partial window is shown separately in the major-window table.

## Major Windows

| label | window | years | variant | fills | total_r | r_per_year | delta_vs_cap1_r | delta_vs_cap2_any_r | sharpe_ratio | max_drawdown_r | negative_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Historical pre-recent | 2016-04-17 to 2024-04-16 | 8 | cap1_baseline | 2402 | 262 | 32.71 | 0 | - | 1.57 | -21.18 | 638 |
| Historical pre-recent | 2016-04-17 to 2024-04-16 | 8 | cap2_any_reentry | 2939 | 312 | 39.02 | 50.48 | 0 | 1.72 | -23.21 | 688 |
| Historical pre-recent | 2016-04-17 to 2024-04-16 | 8 | cap2_after_nonpositive_first | 2582 | 299 | 37.35 | 37.11 | -13.37 | 1.73 | -21.96 | 627 |
| Recent available | 2024-04-17 to 2026-03-24 | 1.94 | cap1_baseline | 587 | 97.80 | 50.41 | 0 | - | 2.37 | -9.88 | 144 |
| Recent available | 2024-04-17 to 2026-03-24 | 1.94 | cap2_any_reentry | 759 | 124 | 63.99 | 26.35 | 0 | 2.71 | -12.60 | 158 |
| Recent available | 2024-04-17 to 2026-03-24 | 1.94 | cap2_after_nonpositive_first | 642 | 115 | 59.36 | 17.36 | -8.99 | 2.70 | -10.94 | 139 |
| Full available history | 2016-04-17 to 2026-03-24 | 9.94 | cap1_baseline | 2989 | 360 | 36.17 | 0 | - | 1.73 | -21.18 | 782 |
| Full available history | 2016-04-17 to 2026-03-24 | 9.94 | cap2_any_reentry | 3698 | 436 | 43.90 | 76.84 | 0 | 1.92 | -23.21 | 846 |
| Full available history | 2016-04-17 to 2026-03-24 | 9.94 | cap2_after_nonpositive_first | 3224 | 414 | 41.65 | 54.48 | -22.36 | 1.93 | -21.96 | 766 |

## Rolling 2-Year Scorecard

| rolling_windows | conditioned_beats_cap1_total_r_windows | conditioned_beats_cap1_sharpe_windows | conditioned_beats_cap2_any_sharpe_windows | conditioned_has_better_drawdown_than_cap2_any_windows | conditioned_median_delta_vs_cap1_r | conditioned_mean_delta_vs_cap1_r |
| --- | --- | --- | --- | --- | --- | --- |
| 8 | 7 | 7 | 5 | 4 | 9.41 | 10.70 |

## Rolling 2-Year Detail

| window | baseline_total_r | cap2_any_total_r | conditioned_total_r | conditioned_delta_vs_cap1_r | conditioned_delta_vs_cap2_any_r | baseline_sharpe | cap2_any_sharpe | conditioned_sharpe | conditioned_max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2016-04-17 to 2018-04-16 | 75.85 | 93.49 | 85.66 | 9.81 | -7.83 | 1.82 | 2.11 | 2 | -15.37 |
| 2017-04-17 to 2019-04-16 | 58.21 | 59.71 | 61.85 | 3.64 | 2.14 | 1.35 | 1.30 | 1.40 | -21.96 |
| 2018-04-17 to 2020-04-16 | 39.84 | 47.46 | 47.92 | 8.08 | 0.46 | 0.95 | 1.04 | 1.10 | -20.81 |
| 2019-04-17 to 2021-04-16 | 69.07 | 90.12 | 82.21 | 13.14 | -7.91 | 1.70 | 2.02 | 1.93 | -17.94 |
| 2020-04-17 to 2022-04-16 | 45.33 | 59.21 | 56.41 | 11.08 | -2.80 | 1.15 | 1.39 | 1.39 | -17.94 |
| 2021-04-17 to 2023-04-16 | 65.06 | 66.39 | 64.59 | -0.47 | -1.80 | 1.68 | 1.55 | 1.62 | -12.90 |
| 2022-04-17 to 2024-04-16 | 96.74 | 109 | 106 | 9.02 | -3.11 | 2.23 | 2.26 | 2.37 | -12.90 |
| 2023-04-17 to 2025-04-16 | 92.83 | 125 | 124 | 31.31 | -1.09 | 2.17 | 2.66 | 2.82 | -12.49 |

## Full Available Per-Leg Read

| leg | variant | fills | win_rate_pct | avg_r | total_r | r_per_year | delta_vs_cap1_r | delta_vs_cap2_any_r | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ Asia ORB | cap1_baseline | 722 | 45.71 | 0.30 | 214 | 21.48 | 0 | - | 3 | -10.16 |
| NQ Asia ORB | cap2_any_reentry | 765 | 45.62 | 0.31 | 237 | 23.80 | 23.09 | 0 | 3.09 | -10.28 |
| NQ Asia ORB | cap2_after_nonpositive_first | 759 | 45.85 | 0.31 | 237 | 23.87 | 23.77 | 0.68 | 3.13 | -10.28 |
| ES Asia ORB | cap1_baseline | 1422 | 54.43 | 0.10 | 146 | 14.67 | 0 | - | 1.80 | -12.28 |
| ES Asia ORB | cap2_any_reentry | 1793 | 54.04 | 0.09 | 166 | 16.68 | 19.91 | 0 | 1.64 | -11.11 |
| ES Asia ORB | cap2_after_nonpositive_first | 1519 | 55.04 | 0.11 | 168 | 16.92 | 22.34 | 2.42 | 1.95 | -11.67 |
| ES NY ORB | cap1_baseline | 845 | 61.07 | 0.15 | 128 | 12.84 | 0 | - | 2.13 | -10.86 |
| ES NY ORB | cap2_any_reentry | 1140 | 60.18 | 0.15 | 166 | 16.71 | 38.55 | 0 | 2.02 | -13.12 |
| ES NY ORB | cap2_after_nonpositive_first | 946 | 60.47 | 0.15 | 140 | 14.10 | 12.57 | -25.99 | 2.07 | -12.99 |

