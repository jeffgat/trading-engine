# NQ NY LSI CISD Candidate Validation

- Latest data date: `2026-05-01`.
- Candidates are frozen from the CISD survivor-refinement sequence.
- Targets remain fixed at `rr=2.0`, `tp1_ratio=0.5`.
- Search-trial count used for DSR: `242`.

## Frozen Candidates

- `add_1m_classic_atr10_b3_a7p5`: 1m additive classic swing, limit, ATR10 stop, CISD 3 bars / 7.5% ATR
- `pure_1m_classic_atr15_b2_a7p5`: 1m pure CISD classic swing, limit, ATR15 stop, CISD 2 bars / 7.5% ATR
- `add_3m_hourly_atr12p5_b3_a7p5`: 3m additive hourly sweep, limit, ATR12.5 stop, CISD 3 bars / 7.5% ATR

## Period Scorecard

### add_1m_classic_atr10_b3_a7p5
- `discovery`: 433 tr, PF 1.18, R 36.3, DD -18.1, Calmar 2.01
- `validation`: 106 tr, PF 1.37, R 16.1, DD -6.6, Calmar 2.43
- `holdout`: 58 tr, PF 1.73, R 14.7, DD -5.1, Calmar 2.89
- `post_2023`: 164 tr, PF 1.48, R 30.8, DD -6.6, Calmar 4.64
- `full`: 597 tr, PF 1.25, R 67.1, DD -18.1, Calmar 3.71

### pure_1m_classic_atr15_b2_a7p5
- `discovery`: 223 tr, PF 1.09, R 9.1, DD -11.2, Calmar 0.82
- `validation`: 52 tr, PF 1.50, R 10.0, DD -7.5, Calmar 1.33
- `holdout`: 41 tr, PF 1.66, R 10.0, DD -4.0, Calmar 2.49
- `post_2023`: 93 tr, PF 1.57, R 19.9, DD -7.5, Calmar 2.66
- `full`: 316 tr, PF 1.21, R 29.1, DD -14.0, Calmar 2.08

### add_3m_hourly_atr12p5_b3_a7p5
- `discovery`: 416 tr, PF 1.14, R 25.7, DD -16.2, Calmar 1.59
- `validation`: 140 tr, PF 1.15, R 9.9, DD -7.5, Calmar 1.32
- `holdout`: 46 tr, PF 1.73, R 12.2, DD -5.1, Calmar 2.38
- `post_2023`: 186 tr, PF 1.27, R 22.1, DD -7.5, Calmar 2.95
- `full`: 602 tr, PF 1.18, R 47.8, DD -16.2, Calmar 2.96

## Walk-Forward

- `add_1m_classic_atr10_b3_a7p5`: 8/8 OOS folds passed, median OOS PF `1.51`, median OOS Calmar `1.15`.
- `pure_1m_classic_atr15_b2_a7p5`: 7/8 OOS folds passed, median OOS PF `1.72`, median OOS Calmar `1.73`.
- `add_3m_hourly_atr12p5_b3_a7p5`: 5/8 OOS folds passed, median OOS PF `1.12`, median OOS Calmar `0.46`.

## Execution Stress

### add_1m_classic_atr10_b3_a7p5 Holdout
- `baseline`: 58 tr, PF 1.73, R 14.7, DD -5.1, Calmar 2.89
- `slip_1t_per_side`: 58 tr, PF 1.68, R 13.8, DD -5.2, Calmar 2.65
- `slip_2t_per_side`: 58 tr, PF 1.63, R 12.9, DD -5.3, Calmar 2.42
- `require_1tick_penetration`: 53 tr, PF 1.47, R 9.3, DD -5.6, Calmar 1.68
- `skip_first_eligible_parent_bar`: 18 tr, PF 2.26, R 6.3, DD -2.0, Calmar 3.14
- `penetration_plus_1t_slip`: 53 tr, PF 1.42, R 8.5, DD -5.9, Calmar 1.45

### pure_1m_classic_atr15_b2_a7p5 Holdout
- `baseline`: 41 tr, PF 1.66, R 10.0, DD -4.0, Calmar 2.49
- `slip_1t_per_side`: 41 tr, PF 1.63, R 9.5, DD -4.1, Calmar 2.33
- `slip_2t_per_side`: 41 tr, PF 1.59, R 9.1, DD -4.2, Calmar 2.17
- `require_1tick_penetration`: 37 tr, PF 1.43, R 6.5, DD -3.7, Calmar 1.77
- `skip_first_eligible_parent_bar`: 16 tr, PF 1.01, R 0.1, DD -2.7, Calmar 0.02
- `penetration_plus_1t_slip`: 37 tr, PF 1.40, R 6.1, DD -3.7, Calmar 1.63

### add_3m_hourly_atr12p5_b3_a7p5 Holdout
- `baseline`: 46 tr, PF 1.73, R 12.2, DD -5.1, Calmar 2.38
- `slip_1t_per_side`: 46 tr, PF 1.69, R 11.6, DD -5.2, Calmar 2.24
- `slip_2t_per_side`: 46 tr, PF 1.65, R 11.1, DD -5.3, Calmar 2.11
- `require_1tick_penetration`: 44 tr, PF 1.97, R 14.2, DD -4.1, Calmar 3.45
- `skip_first_eligible_parent_bar`: 9 tr, PF 1.52, R 1.9, DD -1.6, Calmar 1.16
- `penetration_plus_1t_slip`: 44 tr, PF 1.92, R 13.6, DD -4.2, Calmar 3.27

## Fragility

- `add_1m_classic_atr10_b3_a7p5`: `27/27` neighbors robust (`100.0%`); median validation PF `1.31`, median holdout PF `1.21`.
- `pure_1m_classic_atr15_b2_a7p5`: `12/18` promotable neighbors robust (`66.7%`), excluding diagnostic `bars=1` rows because CISD leg bars must be at least `2`; median validation PF `1.31`, median holdout PF `1.47`.
- `add_3m_hourly_atr12p5_b3_a7p5`: `19/27` neighbors robust (`70.4%`); median validation PF `1.04`, median holdout PF `1.30`.

## Monte Carlo

- `add_1m_classic_atr10_b3_a7p5` post-2023 block bootstrap: final R p5 `9.7897`, max DD p5 `-12.1429`, ruin(-10R) `15.9%`.
- `pure_1m_classic_atr15_b2_a7p5` post-2023 block bootstrap: final R p5 `0.9525`, max DD p5 `-13.4225`, ruin(-10R) `18.4%`.
- `add_3m_hourly_atr12p5_b3_a7p5` post-2023 block bootstrap: final R p5 `1.5373`, max DD p5 `-13.9619`, ruin(-10R) `26.2%`.

## PSR / DSR

- `add_1m_classic_atr10_b3_a7p5` post-2023: PSR `0.9900` (strong), DSR `0.2998` (overfit).
- `pure_1m_classic_atr15_b2_a7p5` post-2023: PSR `0.9769` (strong), DSR `0.1977` (overfit).
- `add_3m_hourly_atr12p5_b3_a7p5` post-2023: PSR `0.9367` (moderate), DSR `0.0916` (overfit).

## Phase-One Style Accounts

- `add_1m_classic_atr10_b3_a7p5` post-2023 normal profile: payout `77.0%`, breach `16.1%`, EV `3.49R` per 14-day staggered account.
- `pure_1m_classic_atr15_b2_a7p5` post-2023 normal profile: payout `80.5%`, breach `14.9%`, EV `3.48R` per 14-day staggered account.
- `add_3m_hourly_atr12p5_b3_a7p5` post-2023 normal profile: payout `63.2%`, breach `28.7%`, EV `2.03R` per 14-day staggered account.
