# NQ NY LSI noThu MBP-1 Pressure Stress - 2026-05-27

## Objective

Retest the higher-frequency `1m additive noThu pressure` branch with a pressure score that is compatible with DataBento MBP-1. The old pressure feature used a depth-3 boost; this version uses only best-bid/ask level-1 imbalance plus trade-print aggression/volume.

- Candidate: `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530`
- New feature: `pre_confirm_30s_l1_pressure_score`
- Original feature comparator: `pre_confirm_30s_pressure_score`
- DataBento fetches: `0`
- Stress harness: same slippage/account/bootstrap setup as the pure 1m velocity champion.

## Frozen Thresholds

- Validation rows: `83`
- Low threshold: `0.000000`
- High threshold: `0.088464`
- Feature median: `0.038922`

## Primary Replay

| Period | Trades | Tiered R | Base R | Delta R | Avg R | PF | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | 46 | 15.84 | 10.48 | +5.36 | 0.344 | 1.93 | -4.63R |
| validation | 83 | 23.78 | 19.72 | +4.06 | 0.287 | 1.63 | -8.31R |

## Feature Comparator, Primary Profile

| Period | Feature | Rows | Tiered R | Delta R | Avg R | PF | Max DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `pre_confirm_30s_l1_pressure_no_depth_score` | 46 | 15.84 | +5.36 | 0.344 | 1.93 | -4.63R |
| holdout | `pre_confirm_30s_l1_pressure_score` | 46 | 15.84 | +5.36 | 0.344 | 1.93 | -4.63R |
| holdout | `pre_confirm_30s_pressure_score` | 46 | 15.84 | +5.36 | 0.344 | 1.93 | -4.63R |
| validation | `pre_confirm_30s_l1_pressure_no_depth_score` | 83 | 23.78 | +4.06 | 0.287 | 1.63 | -8.31R |
| validation | `pre_confirm_30s_l1_pressure_score` | 83 | 23.78 | +4.06 | 0.287 | 1.63 | -8.31R |
| validation | `pre_confirm_30s_pressure_score` | 83 | 23.78 | +4.06 | 0.287 | 1.63 | -8.31R |

## Account Stress, 1 Tick/Side Slippage

| Window | Profile | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `0/1/1.5` | 62.1% | 6.9% | 3.80R | +0.34R | +41.4% | +0.0% |
| holdout | `0.5/1/1.5` | 62.1% | 6.9% | 3.80R | +0.34R | +41.4% | +0.0% |
| holdout | `0.75/1/1.25` | 41.4% | 6.9% | 3.71R | +0.25R | +20.7% | +0.0% |
| post_2023 | `0.75/1/1.25` | 69.0% | 14.9% | 3.49R | -0.37R | +2.3% | +4.6% |
| post_2023 | `0/1/1.5` | 71.3% | 18.4% | 3.20R | -0.66R | +4.6% | +8.0% |
| post_2023 | `0.5/1/1.5` | 71.3% | 18.4% | 3.20R | -0.66R | +4.6% | +8.0% |

## Slippage R Stress, Primary Profile

| Window | Slip | Trades | Total R | Avg R | PF | Max DD | Delta Total R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | 0.0 | 46 | 15.84 | 0.344 | 1.93 | -4.63R | +5.36R |
| holdout | 1.0 | 46 | 15.03 | 0.327 | 1.87 | -4.91R | +5.26R |
| post_2023 | 0.0 | 129 | 39.62 | 0.307 | 1.72 | -8.31R | +9.42R |
| post_2023 | 1.0 | 129 | 36.77 | 0.285 | 1.66 | -8.84R | +9.01R |
| validation | 0.0 | 83 | 23.78 | 0.287 | 1.63 | -8.31R | +4.06R |
| validation | 1.0 | 83 | 21.74 | 0.262 | 1.56 | -8.84R | +3.75R |

## Holdout Tier Breakdown

| Tier | Trades | Weight | Feature Range | Total R | Avg R | PF | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `mid` | 33 | 1.00 | 0.0000-0.0858 | -0.25 | -0.008 | 0.98 | -7.76R |
| `high` | 13 | 1.50 | 0.0900-0.2256 | 16.09 | 1.238 | 6.36 | -1.50R |

## Interpretation

- The MBP-1-compatible L1 pressure proxy preserved the old noThu pressure tier assignments on this replay: same `46` holdout trades, same `+15.84R`, and the same primary risk weights as the depth-3 pressure path.
- It improves aggregate R versus the noThu baseline and improves holdout account payout behavior, but post-2023 account EV worsens because breach rate rises under stricter daily-stop/min-days stress.
- This is a viable higher-frequency side branch for shadow research, but it should not replace the pure 1m velocity champion until the account-level degradation is solved.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/nq_ny_lsi_nothu_mbp1_pressure_stress_20260527/trade_risk_tier_replay.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/nq_ny_lsi_nothu_mbp1_pressure_stress_20260527/period_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/nq_ny_lsi_nothu_mbp1_pressure_stress_20260527/tier_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/nq_ny_lsi_nothu_mbp1_pressure_stress_20260527/feature_comparison.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/nq_ny_lsi_nothu_mbp1_pressure_stress_20260527/stress_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/nq_ny_lsi_nothu_mbp1_pressure_stress_20260527/account_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/nq_ny_lsi_nothu_mbp1_pressure_stress_20260527/bootstrap_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/nq_ny_lsi_nothu_mbp1_pressure_stress_20260527/summary.json`
