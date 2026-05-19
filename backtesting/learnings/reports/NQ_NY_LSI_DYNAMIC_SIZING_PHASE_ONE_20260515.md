# NQ NY LSI Dynamic Sizing Phase-One Replay

- Objective: no-fetch account-objective replay for the orderbook and sweep-reclaim dynamic sizing overlays.
- Model: stagger a new account every 14 calendar days; payout at `+5R`; breach at `-4R`.
- Inputs: existing trade-level baseline R and weighted R from prior overlay replay CSVs; no new market data fetch.
- Caveat: this is not yet exact engine execution. It is a trade-level account replay to rank which overlays deserve exact replay.

## Post-2023 Tiered Results

| Source | Overlay | Profile | Trades | Total R | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sweep_reclaim | `3m_trapped_reversal_confirm` | `tier_0_1_1p5` | 186 | 41.75 | 87.4% | 4.6% | 4.08R | +2.05R | +24.1% | -24.1% |
| sweep_reclaim | `3m_trapped_reversal_confirm` | `tier_0p5_1_1p5` | 186 | 39.02 | 83.9% | 10.3% | 3.77R | +1.74R | +20.7% | -18.4% |
| sweep_reclaim | `3m_confirm_reclaim_velocity` | `tier_0_1_1p5` | 186 | 36.12 | 83.9% | 9.2% | 3.73R | +1.70R | +20.7% | -19.5% |
| sweep_reclaim | `3m_trapped_reversal_confirm` | `tier_0p75_1_1p25` | 186 | 30.56 | 78.2% | 14.9% | 3.33R | +1.30R | +14.9% | -13.8% |
| sweep_reclaim | `3m_confirm_reclaim_velocity` | `tier_0p5_1_1p5` | 186 | 33.39 | 75.9% | 18.4% | 3.02R | +0.99R | +12.6% | -10.3% |
| sweep_reclaim | `3m_confirm_reclaim_velocity` | `tier_0p75_1_1p25` | 186 | 27.75 | 73.6% | 19.5% | 2.89R | +0.87R | +10.3% | -9.2% |
| orderbook | `pure_1m_long_confirm_last_velocity` | `tier_0p5_1_1p5` | 54 | 19.97 | 86.2% | 0.0% | 4.65R | +0.21R | +8.0% | +0.0% |
| orderbook | `pure_1m_long_confirm_last_velocity` | `tier_0_1_1p5` | 54 | 18.54 | 86.2% | 0.0% | 4.62R | +0.18R | +8.0% | +0.0% |
| orderbook | `pure_1m_long_confirm_last_velocity` | `tier_0p75_1_1p25` | 54 | 17.68 | 85.1% | 0.0% | 4.58R | +0.14R | +6.9% | +0.0% |
| orderbook | `noThu_additive_pre_confirm_pressure` | `tier_0p75_1_1p25` | 129 | 34.91 | 77.0% | 12.6% | 3.72R | -0.38R | +2.3% | +4.6% |
| orderbook | `allDOW_additive_pre_confirm_pressure` | `tier_0p75_1_1p25` | 161 | 33.89 | 74.7% | 20.7% | 3.08R | -0.41R | -2.3% | +4.6% |
| orderbook | `allDOW_additive_pre_confirm_pressure` | `tier_0_1_1p5` | 161 | 39.12 | 72.4% | 23.0% | 2.87R | -0.62R | -4.6% | +6.9% |
| orderbook | `allDOW_additive_pre_confirm_pressure` | `tier_0p5_1_1p5` | 161 | 39.12 | 72.4% | 23.0% | 2.87R | -0.62R | -4.6% | +6.9% |
| orderbook | `noThu_additive_pre_confirm_pressure` | `tier_0_1_1p5` | 129 | 39.62 | 72.4% | 17.2% | 3.32R | -0.78R | -2.3% | +9.2% |
| orderbook | `noThu_additive_pre_confirm_pressure` | `tier_0p5_1_1p5` | 129 | 39.62 | 72.4% | 17.2% | 3.32R | -0.78R | -2.3% | +9.2% |

## Holdout Tiered Results

| Source | Overlay | Profile | Trades | Total R | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| orderbook | `pure_1m_long_confirm_last_velocity` | `tier_0p5_1_1p5` | 21 | 8.33 | 58.6% | 0.0% | 3.86R | +0.54R | +20.7% | +0.0% |
| orderbook | `pure_1m_long_confirm_last_velocity` | `tier_0_1_1p5` | 21 | 8.62 | 58.6% | 0.0% | 3.76R | +0.44R | +20.7% | +0.0% |
| orderbook | `noThu_additive_pre_confirm_pressure` | `tier_0_1_1p5` | 46 | 15.84 | 62.1% | 3.4% | 4.09R | +0.44R | +20.7% | -3.4% |
| orderbook | `noThu_additive_pre_confirm_pressure` | `tier_0p5_1_1p5` | 46 | 15.84 | 62.1% | 3.4% | 4.09R | +0.44R | +20.7% | -3.4% |
| orderbook | `pure_1m_long_confirm_last_velocity` | `tier_0p75_1_1p25` | 21 | 6.59 | 58.6% | 0.0% | 3.71R | +0.39R | +20.7% | +0.0% |
| orderbook | `noThu_additive_pre_confirm_pressure` | `tier_0p75_1_1p25` | 46 | 13.16 | 62.1% | 3.4% | 4.02R | +0.37R | +20.7% | -3.4% |
| orderbook | `allDOW_additive_pre_confirm_pressure` | `tier_0_1_1p5` | 57 | 20.05 | 82.8% | 3.4% | 4.40R | +0.04R | +6.9% | +0.0% |
| orderbook | `allDOW_additive_pre_confirm_pressure` | `tier_0p5_1_1p5` | 57 | 20.05 | 82.8% | 3.4% | 4.40R | +0.04R | +6.9% | +0.0% |
| orderbook | `allDOW_additive_pre_confirm_pressure` | `tier_0p75_1_1p25` | 57 | 16.57 | 82.8% | 3.4% | 4.40R | +0.04R | +6.9% | +0.0% |
| sweep_reclaim | `3m_trapped_reversal_confirm` | `tier_0p75_1_1p25` | 46 | 14.76 | 58.6% | 6.9% | 2.40R | -0.02R | +3.4% | +0.0% |
| sweep_reclaim | `3m_trapped_reversal_confirm` | `tier_0p5_1_1p5` | 46 | 17.34 | 62.1% | 13.8% | 2.38R | -0.04R | +6.9% | +6.9% |
| sweep_reclaim | `3m_confirm_reclaim_velocity` | `tier_0p5_1_1p5` | 46 | 16.06 | 62.1% | 17.2% | 2.25R | -0.17R | +6.9% | +10.3% |
| sweep_reclaim | `3m_confirm_reclaim_velocity` | `tier_0p75_1_1p25` | 46 | 14.12 | 58.6% | 13.8% | 2.24R | -0.18R | +3.4% | +6.9% |
| sweep_reclaim | `3m_trapped_reversal_confirm` | `tier_0_1_1p5` | 46 | 16.85 | 58.6% | 10.3% | 2.05R | -0.37R | +3.4% | +3.4% |
| sweep_reclaim | `3m_confirm_reclaim_velocity` | `tier_0_1_1p5` | 46 | 15.58 | 58.6% | 13.8% | 1.89R | -0.54R | +3.4% | +6.9% |

## Interpretation

- Favor overlays that improve EV/account without raising breach rate materially.
- Aggregate R can improve while payout behavior worsens; this table is the account-objective check before exact replay.
- Use the conservative profile first when account EV is close, because it is less likely to overstate capacity.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_dynamic_sizing_phase_one_20260515/account_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_dynamic_sizing_phase_one_20260515/account_outcomes.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_dynamic_sizing_phase_one_20260515/summary.json`