# NQ NY LSI 3m Trapped-Reversal Stress

- Objective: push the no-extra-fetch `3m` trapped-reversal survivor through stricter execution-cost, account-rule, tier, monthly, and bootstrap tests.
- Candidate: `add_3m_hourly_atr12p5_b3_a7p5`
- Feature: `trapped_reversal_confirm_score`
- Scope: research-engine trade replay using already-created local CSVs. No DataBento fetch. This is not full live-engine parity because the live LSI engine does not yet model this candidate's `inversion_or_cisd` confirmation plus `atr_pct` stop exactly.

## Account Stress, 1 Tick/Side Slippage

Account rules here: stagger every `14` calendar days, payout `+5R`, breach `-4R`, daily stop `-2R`, minimum `5` trading days before payout.

| Window | Profile | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `0.5/1/1.5` | 62.1% | 13.8% | 2.36R | -0.02R | +6.9% | +6.9% |
| holdout | `0.75/1/1.25` | 58.6% | 10.3% | 2.34R | -0.05R | +3.4% | +3.4% |
| holdout | `0/1/1.5` | 58.6% | 10.3% | 2.02R | -0.36R | +3.4% | +3.4% |
| post_2023 | `0/1/1.5` | 87.4% | 4.6% | 4.07R | +2.57R | +29.9% | -29.9% |
| post_2023 | `0.5/1/1.5` | 81.6% | 12.6% | 3.56R | +2.06R | +24.1% | -21.8% |
| post_2023 | `0.75/1/1.25` | 71.3% | 21.8% | 2.70R | +1.20R | +13.8% | -12.6% |

## R-Multiple Stress

| Window | Slip | Profile | Trades | Total R | Avg R | PF | Max DD | Delta Total R |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | 0.0 | `0.5/1/1.5` | 46 | 17.34 | 0.377 | 2.00 | -5.67R | +5.17R |
| holdout | 0.0 | `0/1/1.5` | 33 | 16.85 | 0.511 | 2.13 | -5.17R | +4.68R |
| holdout | 0.0 | `0.75/1/1.25` | 46 | 14.76 | 0.321 | 1.87 | -5.39R | +2.58R |
| holdout | 1.0 | `0.5/1/1.5` | 46 | 16.75 | 0.364 | 1.95 | -5.75R | +5.13R |
| holdout | 1.0 | `0/1/1.5` | 33 | 16.35 | 0.495 | 2.08 | -5.25R | +4.73R |
| holdout | 1.0 | `0.75/1/1.25` | 46 | 14.18 | 0.308 | 1.82 | -5.47R | +2.56R |
| post_2023 | 0.0 | `0/1/1.5` | 127 | 41.75 | 0.329 | 1.68 | -5.17R | +19.65R |
| post_2023 | 0.0 | `0.5/1/1.5` | 186 | 39.02 | 0.210 | 1.51 | -5.67R | +16.91R |
| post_2023 | 0.0 | `0.75/1/1.25` | 186 | 30.56 | 0.164 | 1.39 | -5.88R | +8.45R |
| post_2023 | 1.0 | `0/1/1.5` | 127 | 39.27 | 0.309 | 1.63 | -5.25R | +20.03R |
| post_2023 | 1.0 | `0.5/1/1.5` | 186 | 36.09 | 0.194 | 1.46 | -5.75R | +16.85R |
| post_2023 | 1.0 | `0.75/1/1.25` | 186 | 27.66 | 0.149 | 1.34 | -6.27R | +8.42R |
| validation | 0.0 | `0/1/1.5` | 94 | 24.90 | 0.265 | 1.54 | -4.50R | +14.96R |
| validation | 0.0 | `0.5/1/1.5` | 140 | 21.68 | 0.155 | 1.36 | -5.00R | +11.74R |
| validation | 0.0 | `0.75/1/1.25` | 140 | 15.80 | 0.113 | 1.25 | -5.88R | +5.87R |
| validation | 1.0 | `0/1/1.5` | 94 | 22.92 | 0.244 | 1.48 | -4.58R | +15.31R |
| validation | 1.0 | `0.5/1/1.5` | 140 | 19.34 | 0.138 | 1.32 | -5.09R | +11.72R |
| validation | 1.0 | `0.75/1/1.25` | 140 | 13.48 | 0.096 | 1.21 | -6.27R | +5.86R |

## Conservative Tier Quality

| Window | Tier | Trades | Avg Weight | Total R | Avg R | PF |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| holdout | `high` | 22 | 1.25 | 13.83 | 0.629 | 2.66 |
| holdout | `low` | 13 | 0.75 | 0.60 | 0.046 | 1.16 |
| holdout | `mid` | 11 | 1.00 | -0.25 | -0.023 | 0.95 |
| validation | `high` | 48 | 1.25 | 20.33 | 0.424 | 2.07 |
| validation | `low` | 46 | 0.75 | -5.38 | -0.117 | 0.73 |
| validation | `mid` | 46 | 1.00 | -1.47 | -0.032 | 0.94 |

## Bootstrap Fragility, 1 Tick/Side Slippage

| Window | Profile | Trades | P05 Total R | P50 Total R | P95 Total R | Prob Positive | Prob DD <= -4R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `0/1/1.5` | 33 | 2.41 | 16.63 | 30.22 | 97.2% | 58.1% |
| holdout | `0.5/1/1.5` | 46 | 1.84 | 16.73 | 31.00 | 96.9% | 62.1% |
| holdout | `0.75/1/1.25` | 46 | 1.01 | 13.89 | 26.72 | 96.5% | 56.2% |
| post_2023 | `0/1/1.5` | 127 | 13.94 | 39.63 | 65.75 | 99.6% | 99.3% |
| post_2023 | `0.5/1/1.5` | 186 | 9.55 | 36.14 | 63.46 | 98.8% | 99.8% |
| post_2023 | `0.75/1/1.25` | 186 | 2.38 | 27.57 | 53.12 | 96.5% | 99.8% |

## Interpretation

- The live execution engine needs a separate parity task before this can be called production-exact.
- For current no-fetch research, prefer the conservative `0.75/1/1.25` profile unless the account stress clearly rewards a more aggressive profile after slippage.
- The `0/1/1.5` skip-weak profile is useful as a fragility test; it should not be promoted unless it survives holdout account behavior after slippage.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/stress_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/stress_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/tier_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/monthly_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/account_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/account_outcomes.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/bootstrap_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/summary.json`