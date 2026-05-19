# NQ NY LSI Pure 1m Order-Book Velocity Stress

- Objective: apply the same no-extra-fetch promotion stress used on the 3m trapped-reversal branch to the pure 1m long MBP-10 velocity survivor.
- Candidate: `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`
- Feature: `confirm_last_10s_mid_velocity_ticks_per_second`
- Scope: existing order-book risk-tier replay CSV only; no DataBento fetch. This is still `research_only` because live MBP-10 feature streaming and dynamic sizing are not implemented in the execution path.

## Account Stress, 1 Tick/Side Slippage

Account rules: stagger every `14` calendar days, payout `+5R`, breach `-4R`, daily stop `-2R`, minimum `5` trading days before payout.

| Window | Profile | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `0.5/1/1.5` | 58.6% | 0.0% | 3.83R | +0.57R | +20.7% | +0.0% |
| holdout | `0/1/1.5` | 58.6% | 0.0% | 3.73R | +0.46R | +20.7% | +0.0% |
| holdout | `0.75/1/1.25` | 58.6% | 0.0% | 3.68R | +0.41R | +20.7% | +0.0% |
| post_2023 | `0.5/1/1.5` | 86.2% | 0.0% | 4.64R | +0.22R | +8.0% | +0.0% |
| post_2023 | `0/1/1.5` | 85.1% | 0.0% | 4.60R | +0.18R | +6.9% | +0.0% |
| post_2023 | `0.75/1/1.25` | 85.1% | 0.0% | 4.57R | +0.15R | +6.9% | +0.0% |

## R-Multiple Stress

| Window | Slip | Profile | Trades | Total R | Avg R | PF | Max DD | Delta Total R |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | 0.0 | `0/1/1.5` | 15 | 8.62 | 0.575 | 2.72 | -1.50R | +3.78R |
| holdout | 0.0 | `0.5/1/1.5` | 21 | 8.33 | 0.397 | 2.28 | -1.50R | +3.49R |
| holdout | 0.0 | `0.75/1/1.25` | 21 | 6.59 | 0.314 | 1.98 | -1.58R | +1.75R |
| holdout | 1.0 | `0/1/1.5` | 15 | 8.39 | 0.560 | 2.66 | -1.51R | +3.79R |
| holdout | 1.0 | `0.5/1/1.5` | 21 | 8.07 | 0.384 | 2.23 | -1.53R | +3.47R |
| holdout | 1.0 | `0.75/1/1.25` | 21 | 6.34 | 0.302 | 1.93 | -1.61R | +1.73R |
| post_2023 | 0.0 | `0.5/1/1.5` | 54 | 19.97 | 0.370 | 2.29 | -2.75R | +4.58R |
| post_2023 | 0.0 | `0/1/1.5` | 37 | 18.54 | 0.501 | 2.54 | -2.75R | +3.15R |
| post_2023 | 0.0 | `0.75/1/1.25` | 54 | 17.68 | 0.327 | 2.09 | -2.68R | +2.29R |
| post_2023 | 1.0 | `0.5/1/1.5` | 54 | 19.23 | 0.356 | 2.22 | -2.84R | +4.55R |
| post_2023 | 1.0 | `0/1/1.5` | 37 | 17.90 | 0.484 | 2.47 | -2.84R | +3.23R |
| post_2023 | 1.0 | `0.75/1/1.25` | 54 | 16.95 | 0.314 | 2.03 | -2.83R | +2.28R |
| validation | 0.0 | `0.5/1/1.5` | 33 | 11.63 | 0.353 | 2.29 | -2.75R | +1.08R |
| validation | 0.0 | `0.75/1/1.25` | 33 | 11.09 | 0.336 | 2.17 | -2.68R | +0.54R |
| validation | 0.0 | `0/1/1.5` | 22 | 9.92 | 0.451 | 2.42 | -2.75R | -0.63R |
| validation | 1.0 | `0.5/1/1.5` | 33 | 11.15 | 0.338 | 2.22 | -2.84R | +1.08R |
| validation | 1.0 | `0.75/1/1.25` | 33 | 10.61 | 0.321 | 2.10 | -2.83R | +0.54R |
| validation | 1.0 | `0/1/1.5` | 22 | 9.51 | 0.432 | 2.34 | -2.84R | -0.56R |

## Primary Tier Quality

| Window | Tier | Trades | Avg Weight | Total R | Avg R | PF |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| holdout | `high` | 11 | 1.50 | 9.45 | 0.859 | 4.13 |
| holdout | `low` | 6 | 0.50 | -0.32 | -0.053 | 0.79 |
| holdout | `mid` | 4 | 1.00 | -1.05 | -0.264 | 0.48 |
| validation | `high` | 11 | 1.50 | 8.18 | 0.744 | 3.69 |
| validation | `low` | 11 | 0.50 | 1.64 | 0.149 | 1.81 |
| validation | `mid` | 11 | 1.00 | 1.32 | 0.120 | 1.32 |

## Bootstrap Fragility, 1 Tick/Side Slippage

| Window | Profile | Trades | P05 Total R | P50 Total R | P95 Total R | Prob Positive | Prob DD <= -4R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `0/1/1.5` | 15 | 0.02 | 8.46 | 16.94 | 95.0% | 15.1% |
| holdout | `0.5/1/1.5` | 21 | -0.66 | 8.05 | 17.21 | 93.4% | 19.7% |
| holdout | `0.75/1/1.25` | 21 | -1.67 | 6.17 | 14.35 | 90.4% | 18.7% |
| post_2023 | `0.5/1/1.5` | 54 | 6.59 | 19.29 | 32.51 | 99.3% | 41.2% |
| post_2023 | `0/1/1.5` | 37 | 5.33 | 17.90 | 30.41 | 99.0% | 36.5% |
| post_2023 | `0.75/1/1.25` | 54 | 5.21 | 16.82 | 28.97 | 99.0% | 40.5% |

## Interpretation

- This branch remains the cleanest capital-protection survivor because breach stayed at `0.0%` in the prior account replay and remains low under stricter rules.
- Capacity is the tradeoff: holdout has only `21` baseline trades, so the signal is useful as a sizing overlay but not enough as a standalone engine.
- The next implementation question is not more threshold mining; it is live MBP-10 feature streaming plus dynamic sizing support.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/stress_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/stress_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/tier_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/monthly_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/account_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/account_outcomes.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/bootstrap_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/summary.json`