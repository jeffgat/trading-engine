# ALPHA_V1 ORB One-Loss Reentry Promotion Packet

- Verdict: **RESEARCH PASS, EXECUTION BUILD REQUIRED BEFORE DRY-RUN**.
- Candidate: add `cap=2 after_nonpositive_first` to `NQ Asia ORB` and `ES Asia ORB`; leave `ES NY ORB` and `NQ NY HTF-LSI` unchanged.
- Test window: `2016-04-17` through `2026-03-24`.
- Current risk sizing: HTF-LSI $300, NQ Asia ORB $300, ES Asia ORB $200, ES NY ORB $300.
- Runtime: 86.8s.

## 1. Combined ALPHA_V1 Portfolio

| window | profile | fills | net_r | delta_net_r | net_usd_current | delta_net_usd_current | profit_factor | sharpe | max_dd | delta_max_dd | max_dd_usd_current | delta_max_dd_usd_current |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | baseline | 3470 | 580 | 0 | 159269 | 0 | 1.41 | 2.72 | -14.47 | 0 | -3934 | 0 |
| full | candidate | 3604 | 626 | 46.11 | 170868 | 11599 | 1.43 | 2.85 | -15.39 | -0.92 | -3952 | -17.82 |
| 2024+ | baseline | 781 | 159 | 0 | 42866 | 0 | 1.51 | 3.29 | -14.38 | 0 | -3934 | 0 |
| 2024+ | candidate | 808 | 174 | 15.03 | 46819 | 3953 | 1.55 | 3.46 | -13.92 | 0.46 | -3837 | 97.52 |
| 2025+ | baseline | 423 | 106 | 0 | 29037 | 0 | 1.67 | 4.12 | -10.93 | 0 | -2991 | 0 |
| 2025+ | candidate | 438 | 113 | 6.56 | 30652 | 1615 | 1.69 | 4.22 | -9.64 | 1.29 | -2733 | 257 |
| last_1y | baseline | 347 | 91.38 | 0 | 25238 | 0 | 1.69 | 4.13 | -10.93 | 0 | -2991 | 0 |
| last_1y | candidate | 357 | 98.08 | 6.70 | 26824 | 1585 | 1.73 | 4.34 | -9.64 | 1.29 | -2733 | 257 |
| calendar_2025 | baseline | 344 | 97.54 | 0 | 26520 | 0 | 1.78 | 4.64 | -10.93 | 0 | -2991 | 0 |
| calendar_2025 | candidate | 355 | 103 | 5.57 | 27936 | 1416 | 1.80 | 4.72 | -9.64 | 1.29 | -2733 | 257 |

## 2. Per-Leg Impact

| window | scope | fills | net_r | delta_net_r | net_usd_current | delta_net_usd_current | profit_factor | sharpe | max_dd | delta_max_dd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | nq_ny_htf_lsi | 481 | 92.58 | 0 | 27773 | 0 | 1.45 | 2.61 | -10.94 | 0 |
| full | nq_asia_orb | 759 | 237 | 23.78 | 71183 | 7132 | 1.59 | 3.26 | -10.28 | -0.12 |
| full | es_asia_orb | 1519 | 168 | 22.34 | 33638 | 4468 | 1.31 | 2.12 | -11.67 | 0.61 |
| full | es_ny_orb | 845 | 128 | 0 | 38275 | 0 | 1.39 | 2.13 | -10.86 | 0 |
| 2025+ | nq_ny_htf_lsi | 47 | 15.39 | 0 | 4617 | 0 | 1.87 | 4.30 | -5.24 | 0 |
| 2025+ | nq_asia_orb | 91 | 44.94 | 3.03 | 13481 | 908 | 2.05 | 5.05 | -6 | 0 |
| 2025+ | es_asia_orb | 190 | 32.04 | 3.54 | 6408 | 707 | 1.47 | 3 | -4.75 | 1.07 |
| 2025+ | es_ny_orb | 110 | 20.49 | 0 | 6146 | 0 | 1.59 | 2.88 | -9.61 | 0 |
| last_1y | nq_ny_htf_lsi | 39 | 14.11 | 0 | 4232 | 0 | 1.96 | 4.64 | -3 | 0 |
| last_1y | nq_asia_orb | 74 | 38.76 | 2.45 | 11627 | 733 | 2.10 | 5.16 | -6 | 0 |
| last_1y | es_asia_orb | 152 | 26.01 | 4.26 | 5203 | 852 | 1.48 | 3.05 | -4.36 | 1.46 |
| last_1y | es_ny_orb | 92 | 19.20 | 0 | 5761 | 0 | 1.64 | 3.06 | -9.61 | 0 |
| calendar_2025 | nq_ny_htf_lsi | 39 | 15.35 | 0 | 4606 | 0 | 2.11 | 5.26 | -5.24 | 0 |
| calendar_2025 | nq_asia_orb | 76 | 40.10 | 3.03 | 12029 | 908 | 2.19 | 5.54 | -6 | 0 |
| calendar_2025 | es_asia_orb | 152 | 29.96 | 2.54 | 5991 | 507 | 1.55 | 3.43 | -4.75 | -0.06 |
| calendar_2025 | es_ny_orb | 88 | 17.70 | 0 | 5310 | 0 | 1.63 | 3.04 | -9.61 | 0 |

## 3. Funded First-Payout Simulation

- Model: $50k account, $2k trailing drawdown capped at $50k, first payout trigger at $52.5k, $500 first withdrawal, $150 challenge fee, new cohort every 14 calendar days.
- PnL uses current live/pilot risk dollars by leg, not uniform research R.

| window | profile | accounts | payouts | breaches | open | payout_rate_pct | breach_rate_pct | ev_per_account_usd | median_days_to_payout | median_trades_to_payout | max_consecutive_breaches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | baseline | 259 | 200 | 55 | 4 | 77.22 | 21.24 | 236 | 35 | 34.50 | 10 |
| full | candidate | 259 | 192 | 64 | 3 | 74.13 | 24.71 | 221 | 31 | 31.50 | 10 |
| 2024+ | baseline | 59 | 48 | 7 | 4 | 81.36 | 11.86 | 257 | 32 | 32.50 | 4 |
| 2024+ | candidate | 59 | 47 | 8 | 4 | 79.66 | 13.56 | 248 | 32 | 31 | 5 |
| 2025+ | baseline | 32 | 27 | 2 | 3 | 84.38 | 6.25 | 272 | 34 | 32 | 2 |
| 2025+ | candidate | 32 | 27 | 2 | 3 | 84.38 | 6.25 | 272 | 30 | 28 | 2 |
| last_1y | baseline | 27 | 20 | 3 | 4 | 74.07 | 11.11 | 220 | 28 | 23 | 3 |
| last_1y | candidate | 27 | 21 | 2 | 4 | 77.78 | 7.41 | 239 | 28 | 24 | 2 |

## 4. Monthly DD And Worst 90-Day Windows

Worst calendar months by current-dollar drawdown:

| profile | month | net_r | max_dd_r | net_usd_current | max_dd_usd_current |
| --- | --- | --- | --- | --- | --- |
| baseline | 2023-02 | -12.29 | -12.47 | -3283 | -3195 |
| baseline | 2024-07 | -0.33 | -12.20 | 86.75 | -3192 |
| candidate | 2024-07 | -0.33 | -12.20 | 86.75 | -3192 |
| candidate | 2023-02 | -11.57 | -11.74 | -3138 | -3050 |
| baseline | 2018-05 | -1.64 | -9.93 | -392 | -2725 |
| baseline | 2025-07 | -0.80 | -10.21 | -292 | -2691 |
| candidate | 2018-05 | -2.76 | -10.06 | -530 | -2663 |
| candidate | 2025-07 | 0.49 | -8.93 | -34.55 | -2433 |
| baseline | 2022-02 | -7.84 | -8.36 | -2318 | -2423 |
| candidate | 2022-02 | -7.84 | -8.36 | -2318 | -2423 |
| baseline | 2016-12 | -4.12 | -8.42 | -989 | -2383 |
| baseline | 2024-09 | 0.04 | -8.43 | -202 | -2374 |

Worst rolling 90-calendar-day windows:

| profile | start | end | net_r | max_dd_r | net_usd_current | max_dd_usd_current |
| --- | --- | --- | --- | --- | --- | --- |
| candidate | 2018-03-20 | 2018-06-17 | -4.52 | -15.39 | -1267 | -3952 |
| candidate | 2018-03-22 | 2018-06-19 | -4.63 | -15.39 | -1155 | -3952 |
| candidate | 2018-03-23 | 2018-06-20 | -3.63 | -15.39 | -855 | -3952 |
| candidate | 2018-03-01 | 2018-05-29 | -3.32 | -15.39 | -829 | -3952 |
| candidate | 2018-03-16 | 2018-06-13 | -2.34 | -15.39 | -741 | -3952 |
| candidate | 2018-03-17 | 2018-06-14 | -2.34 | -15.39 | -741 | -3952 |
| candidate | 2018-03-18 | 2018-06-15 | -2.34 | -15.39 | -741 | -3952 |
| candidate | 2018-03-19 | 2018-06-16 | -2.34 | -15.39 | -741 | -3952 |
| candidate | 2018-03-24 | 2018-06-21 | -2.80 | -15.39 | -589 | -3952 |
| candidate | 2018-03-21 | 2018-06-18 | -1.59 | -15.39 | -389 | -3952 |
| baseline | 2024-07-13 | 2024-10-10 | 2.66 | -14.38 | 325 | -3934 |
| baseline | 2024-06-23 | 2024-09-20 | 3.47 | -14.38 | 443 | -3934 |

## 5. Trade Timing Overlap

| reentry_count | reentry_net_r | reentry_net_usd_current | reentry_wr_pct | avg_other_legs_usd | share_other_legs_negative_pct | share_total_day_negative_pct | all_candidate_days_negative_pct |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 134 | 46.11 | 11599 | 59.70 | 34.33 | 31.34 | 51.49 | 46.19 |

Worst reentry overlap days:

| date | leg | reentry_r | reentry_usd | other_legs_r | other_legs_usd | total_day_r | total_day_usd | other_legs_negative | total_day_negative |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2021-10-18 | NQ Asia ORB | -1 | -300 | -3 | -600 | -6 | -1500 | True | True |
| 2021-10-18 | ES Asia ORB | -1 | -200 | -3 | -900 | -6 | -1500 | True | True |
| 2018-12-10 | NQ Asia ORB | -1 | -300 | -3 | -700 | -5 | -1300 | True | True |
| 2018-12-10 | ES Asia ORB | -1 | -200 | -3 | -900 | -5 | -1300 | True | True |
| 2022-10-26 | NQ Asia ORB | -1 | -300 | -2.37 | -575 | -4.37 | -1175 | True | True |
| 2024-06-03 | NQ Asia ORB | -1 | -300 | -1.97 | -494 | -3.97 | -1094 | True | True |
| 2026-01-19 | ES Asia ORB | -1 | -200 | -2 | -600 | -4 | -1000 | True | True |
| 2018-04-25 | NQ Asia ORB | -1 | -300 | -1.05 | -214 | -3.05 | -814 | True | True |
| 2020-08-06 | NQ Asia ORB | -1 | -300 | -0.67 | -133 | -2.67 | -733 | True | True |
| 2020-08-06 | ES Asia ORB | 0.33 | 66.67 | -2 | -600 | -2.67 | -733 | True | True |
| 2025-02-13 | NQ Asia ORB | -1 | -300 | -2 | -400 | -3 | -700 | True | True |
| 2025-02-13 | ES Asia ORB | -1 | -200 | -1 | -300 | -3 | -700 | True | True |

## 6. Execution Compatibility

| check | value |
| --- | --- |
| research_backtester_supports_candidate | True |
| execution_generic_orb_engine_supports_candidate | False |
| runtime_overrides_support_candidate | False |
| historical_exact_replay_records_candidate_fields | False |
| hunter_orb_engine_has_its_own_reentry | True |
| promotion_status | research_promotable_but_execution_blocked |

- The research backtester supports orb_trade_max_per_session and orb_reentry_policy.
- The execution HunterORBEngine has separate reentry support, but ALPHA_V1 Asia ORB legs use the generic ORBEngine.
- Generic execution ORBEngine currently scans one FVG, arms one order, then goes flat after completion; no equivalent cap=2 after_nonpositive_first promotion knob was found.

## Readout

- Full combined R moves from 579.51R to 625.62R, a 46.11R change.
- Calendar 2025 current-dollar PnL moves from $26520.48 to $27936.1, a $1415.62 change.
- The packet is intentionally stricter than the earlier sleeve-only test because it includes the active HTF-LSI leg and current risk sizing.
- Artifacts: `backtesting/data/results/alpha_v1_orb_reentry_promotion_20260502`.
