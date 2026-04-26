# ALPHA_V1 ORB Cap=2 Frontier

- Window: `2024-04-17` to `2026-04-17`
- Scope: the three ORB legs in `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`)
- Baseline reference: cap=1 on all ORB legs
- Frontier tested: leg-selective cap=2 plus simple trade-1 outcome policies for trade 2

## Baseline ORB Sleeve

| fills | total_r | sharpe_ratio | max_drawdown_r | calmar_ratio | negative_days |
| --- | --- | --- | --- | --- | --- |
| 579 | 91.04 | 2.24 | -9.88 | 4.65 | 143 |

## Trade 2 By First Exit Type

| leg | first_exit | count | avg_r_trade2 | total_r_trade2 | win_rate_pct_trade2 |
| --- | --- | --- | --- | --- | --- |
| NQ Asia ORB | sl | 6 | 1.16 | 6.96 | 66.67 |
| ES Asia ORB | sl | 18 | 0.21 | 3.79 | 61.11 |
| ES Asia ORB | tp1_be | 17 | 0.08 | 1.32 | 52.94 |
| ES Asia ORB | tp1_tp2 | 49 | 0.02 | 1.07 | 51.02 |
| ES NY ORB | sl | 30 | 0.29 | 8.55 | 63.33 |
| ES NY ORB | tp1_be | 42 | 0.05 | 2.01 | 50 |
| ES NY ORB | tp1_tp2 | 7 | 0.48 | 3.39 | 100 |

## Trade 2 By First Outcome Sign

| leg | first_bucket | count | avg_r_trade2 | total_r_trade2 | win_rate_pct_trade2 |
| --- | --- | --- | --- | --- | --- |
| NQ Asia ORB | nonpositive_first | 6 | 1.16 | 6.96 | 66.67 |
| ES Asia ORB | nonpositive_first | 18 | 0.21 | 3.79 | 61.11 |
| ES Asia ORB | positive_first | 66 | 0.04 | 2.40 | 51.52 |
| ES NY ORB | nonpositive_first | 30 | 0.29 | 8.55 | 63.33 |
| ES NY ORB | positive_first | 49 | 0.11 | 5.40 | 57.14 |

## Trade 2 By Fill Hour

| leg | fill_hour | count | avg_r_trade2 | total_r_trade2 |
| --- | --- | --- | --- | --- |
| NQ Asia ORB | 21 | 3 | 0.46 | 1.38 |
| NQ Asia ORB | 22 | 3 | 1.86 | 5.58 |
| ES Asia ORB | 00 | 19 | 0.10 | 1.87 |
| ES Asia ORB | 01 | 15 | 0.23 | 3.46 |
| ES Asia ORB | 02 | 20 | 0.09 | 1.75 |
| ES Asia ORB | 21 | 7 | -0.35 | -2.44 |
| ES Asia ORB | 22 | 11 | 0.10 | 1.15 |
| ES Asia ORB | 23 | 12 | 0.03 | 0.40 |
| ES NY ORB | 10 | 15 | -0.13 | -1.97 |
| ES NY ORB | 11 | 40 | 0.21 | 8.52 |
| ES NY ORB | 12 | 24 | 0.31 | 7.40 |

## Top Frontier Variants By Total R

| variant | policy | added_reentries | fills | total_r | delta_vs_cap1_r | sharpe_ratio | max_drawdown_r | calmar_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cap2 on NQ Asia ORB + ES Asia ORB + ES NY ORB | any_reentry | 169 | 748 | 116 | 24.86 | 2.56 | -12.92 | 4.53 |
| Cap2 on ES Asia ORB + ES NY ORB | any_reentry | 163 | 742 | 111 | 20.34 | 2.49 | -12.92 | 4.35 |
| Cap2 on NQ Asia ORB + ES NY ORB | any_reentry | 85 | 664 | 110 | 18.47 | 2.52 | -13.06 | 4.23 |
| Cap2 on NQ Asia ORB + ES Asia ORB + ES NY ORB | after_nonpositive_first | 54 | 633 | 108 | 16.86 | 2.57 | -11.44 | 4.76 |
| Cap2 on NQ Asia ORB + ES Asia ORB + ES NY ORB | after_sl_first | 54 | 633 | 108 | 16.86 | 2.57 | -11.44 | 4.76 |
| Cap2 on ES NY ORB | any_reentry | 79 | 658 | 105 | 13.96 | 2.43 | -13.06 | 4.06 |
| Cap2 on NQ Asia ORB + ES NY ORB | after_nonpositive_first | 36 | 615 | 104 | 13.07 | 2.50 | -11.60 | 4.53 |
| Cap2 on NQ Asia ORB + ES NY ORB | after_sl_first | 36 | 615 | 104 | 13.07 | 2.50 | -11.60 | 4.53 |
| Cap2 on ES Asia ORB + ES NY ORB | after_nonpositive_first | 48 | 627 | 103 | 12.34 | 2.49 | -11.44 | 4.56 |
| Cap2 on ES Asia ORB + ES NY ORB | after_sl_first | 48 | 627 | 103 | 12.34 | 2.49 | -11.44 | 4.56 |
| Cap2 on NQ Asia ORB + ES Asia ORB | any_reentry | 90 | 669 | 102 | 10.90 | 2.37 | -9.89 | 5.21 |
| Cap2 on ES NY ORB | after_nonpositive_first | 30 | 609 | 99.59 | 8.55 | 2.41 | -11.60 | 4.34 |

## Top Frontier Variants By Sharpe

| variant | policy | added_reentries | fills | total_r | delta_vs_cap1_r | sharpe_ratio | max_drawdown_r | calmar_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cap2 on NQ Asia ORB + ES Asia ORB + ES NY ORB | after_nonpositive_first | 54 | 633 | 108 | 16.86 | 2.57 | -11.44 | 4.76 |
| Cap2 on NQ Asia ORB + ES Asia ORB + ES NY ORB | after_sl_first | 54 | 633 | 108 | 16.86 | 2.57 | -11.44 | 4.76 |
| Cap2 on NQ Asia ORB + ES Asia ORB + ES NY ORB | any_reentry | 169 | 748 | 116 | 24.86 | 2.56 | -12.92 | 4.53 |
| Cap2 on NQ Asia ORB + ES NY ORB | any_reentry | 85 | 664 | 110 | 18.47 | 2.52 | -13.06 | 4.23 |
| Cap2 on NQ Asia ORB + ES NY ORB | after_nonpositive_first | 36 | 615 | 104 | 13.07 | 2.50 | -11.60 | 4.53 |
| Cap2 on NQ Asia ORB + ES NY ORB | after_sl_first | 36 | 615 | 104 | 13.07 | 2.50 | -11.60 | 4.53 |
| Cap2 on ES Asia ORB + ES NY ORB | any_reentry | 163 | 742 | 111 | 20.34 | 2.49 | -12.92 | 4.35 |
| Cap2 on ES Asia ORB + ES NY ORB | after_nonpositive_first | 48 | 627 | 103 | 12.34 | 2.49 | -11.44 | 4.56 |
| Cap2 on ES Asia ORB + ES NY ORB | after_sl_first | 48 | 627 | 103 | 12.34 | 2.49 | -11.44 | 4.56 |
| Cap2 on ES NY ORB | any_reentry | 79 | 658 | 105 | 13.96 | 2.43 | -13.06 | 4.06 |
| Cap2 on ES NY ORB | after_nonpositive_first | 30 | 609 | 99.59 | 8.55 | 2.41 | -11.60 | 4.34 |
| Cap2 on ES NY ORB | after_sl_first | 30 | 609 | 99.59 | 8.55 | 2.41 | -11.60 | 4.34 |

