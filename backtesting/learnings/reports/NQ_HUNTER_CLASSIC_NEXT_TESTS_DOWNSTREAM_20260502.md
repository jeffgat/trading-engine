# NQ Hunter Classic Next-Tests Downstream Validation (2026-05-02)

## Scope

This packet validates the three frozen branches selected after `NQ_HUNTER_CLASSIC_NEXT_TESTS_20260502`. No new parameters are searched. All three keep the stress gate: skip `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`.

## Candidates

| Label | Candidate | Role | Params |
| --- | --- | --- | --- |
| Neutral Reference | `ema14_tol2_distnone__noTue__1055__rej20__stress` | balanced stress-gated baseline | EMA14, 2pt tolerance, no distance cap, no Tuesday, 10:55 cutoff, rejection <=20 |
| 10y-Safe Branch | `ema14_tol0_distnone__withTue__1055__rej100__stress` | workflow-clean pre-holdout leader | EMA14, 0pt tolerance, no distance cap, Tuesday included, 10:55 cutoff, rejection disabled |
| Recent-Strength Branch | `ema14_tol5_distnone__noTue__1055__rej100__stress` | best current-regime branch with better long-history twin than rej40 | EMA14, 5pt tolerance, no distance cap, no Tuesday, 10:55 cutoff, rejection disabled |

## Core Performance

| Label | Candidate | Full Net | Full DD | 2025+ Net | Last 1y Net | Last 1y WR | Full PF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Neutral Reference | `ema14_tol2_distnone__noTue__1055__rej20__stress` | +164.7R | -41.8R | +108.5R | +92.8R | 57.4% | 1.17 |
| 10y-Safe Branch | `ema14_tol0_distnone__withTue__1055__rej100__stress` | +236.0R | -38.4R | +106.9R | +78.3R | 51.6% | 1.15 |
| Recent-Strength Branch | `ema14_tol5_distnone__noTue__1055__rej100__stress` | +178.0R | -47.7R | +131.4R | +108.7R | 56.1% | 1.15 |

## Rolling Stress

| Label | Worst Month | Worst 3m DD | Worst 6m DD | Worst 6m Sum | Negative Months |
| --- | --- | --- | --- | --- | --- |
| Neutral Reference | -20.4R | -29.9R | -29.9R | -26.9R | 45 |
| 10y-Safe Branch | -13.3R | -27.2R | -31.9R | -29.8R | 49 |
| Recent-Strength Branch | -20.5R | -29.6R | -30.6R | -30.6R | 52 |

## Annual Net R

| Year | Neutral Reference | 10y-Safe Branch | Recent-Strength Branch |
| --- | --- | --- | --- |
| 2016 | +0.5R | +5.4R | +5.4R |
| 2017 | +1.3R | -12.0R | -4.3R |
| 2018 | -5.8R | -10.7R | -2.4R |
| 2019 | -16.6R | +2.2R | -13.3R |
| 2020 | +52.9R | +56.4R | +49.2R |
| 2021 | +7.0R | +10.3R | +0.6R |
| 2022 | -6.9R | +8.3R | -4.3R |
| 2023 | +8.6R | +2.0R | -7.2R |
| 2024 | +15.3R | +67.1R | +22.9R |
| 2025 | +52.9R | +57.8R | +86.8R |
| 2026 | +55.7R | +49.1R | +44.6R |

## Worst Monthly Pain

| Label | Five Worst Months |
| --- | --- |
| Neutral Reference | 2021-07-31: -20.4R, 2022-03-31: -10.8R, 2025-04-30: -10.3R, 2024-01-31: -8.9R, 2021-06-30: -8.6R |
| 10y-Safe Branch | 2023-01-31: -13.3R, 2018-10-31: -13.3R, 2022-06-30: -13.2R, 2025-04-30: -12.6R, 2025-11-30: -11.7R |
| Recent-Strength Branch | 2021-07-31: -20.5R, 2025-04-30: -12.6R, 2024-02-29: -12.4R, 2024-08-31: -11.9R, 2022-03-31: -10.8R |

## Monte Carlo Bootstrap at 0.25x Risk

| Label | Median Net | p05 Net | Median DD | p05 DD | Prob DD <= -20R |
| --- | --- | --- | --- | --- | --- |
| Neutral Reference | +40.7R | +8.2R | -12.2R | -22.1R | 9.0% |
| 10y-Safe Branch | +59.1R | +19.0R | -14.4R | -25.3R | 16.2% |
| Recent-Strength Branch | +44.3R | +8.3R | -13.6R | -24.7R | 13.9% |

## Phase-One Scorecard, 14-Day Staggered Starts at 0.25x Risk

| Label | Window | Accounts | Payout | Breach | Open | Median Days to Payout | EV/Attempt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Neutral Reference | full_10y | 261 | 41.0% | 57.5% | 1.5% | 204 | $105 |
| Neutral Reference | holdout_2025_plus | 34 | 88.2% | 0.0% | 11.8% | 116 | $341 |
| Neutral Reference | last_1y | 26 | 80.8% | 0.0% | 19.2% | 109 | $304 |
| 10y-Safe Branch | full_10y | 261 | 57.1% | 41.4% | 1.5% | 193 | $185 |
| 10y-Safe Branch | holdout_2025_plus | 34 | 88.2% | 0.0% | 11.8% | 94 | $341 |
| 10y-Safe Branch | last_1y | 26 | 80.8% | 0.0% | 19.2% | 90 | $304 |
| Recent-Strength Branch | full_10y | 261 | 29.5% | 68.6% | 1.9% | 120 | $48 |
| Recent-Strength Branch | holdout_2025_plus | 34 | 85.3% | 0.0% | 14.7% | 87 | $326 |
| Recent-Strength Branch | last_1y | 26 | 76.9% | 0.0% | 23.1% | 87 | $285 |

## ALPHA_V1 Portfolio Fit

| Label | Scenario | Net | DD | Delta Net | Delta DD | Worst Month | Corr |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Neutral Reference | ALPHA_V1 baseline | +597.1R | -15.6R | +0.0R | +0.0R | -12.2R | -0.02 |
| Neutral Reference | + Hunter 0.25x | +621.4R | -16.7R | +24.2R | -1.1R | -11.1R | -0.02 |
| Neutral Reference | ES_NY 0.75x + Hunter 0.25x | +589.7R | -16.1R | -7.4R | -0.5R | -10.3R | -0.02 |
| 10y-Safe Branch | ALPHA_V1 baseline | +597.1R | -15.6R | +0.0R | +0.0R | -12.2R | -0.04 |
| 10y-Safe Branch | + Hunter 0.25x | +636.5R | -15.3R | +39.3R | +0.3R | -12.1R | -0.04 |
| 10y-Safe Branch | ES_NY 0.75x + Hunter 0.25x | +604.8R | -14.2R | +7.7R | +1.4R | -11.3R | -0.04 |
| Recent-Strength Branch | ALPHA_V1 baseline | +597.1R | -15.6R | +0.0R | +0.0R | -12.2R | -0.04 |
| Recent-Strength Branch | + Hunter 0.25x | +627.0R | -15.7R | +29.9R | -0.1R | -13.3R | -0.04 |
| Recent-Strength Branch | ES_NY 0.75x + Hunter 0.25x | +595.4R | -14.8R | -1.7R | +0.8R | -12.6R | -0.04 |

## ALPHA_V1 Leg Overlap

| Label | Leg | Corr | Overlap Days | Both Losing | Offset Days | Worst Combined |
| --- | --- | --- | --- | --- | --- | --- |
| Neutral Reference | nq_ny_lsi_long | -0.04 | 147 | 25 | 88 | -10.4R |
| Neutral Reference | nq_asia_orb_long | -0.04 | 248 | 77 | 134 | -7.5R |
| Neutral Reference | es_asia_orb_long | -0.03 | 350 | 85 | 191 | -9.9R |
| Neutral Reference | es_ny_orb_long | 0.07 | 275 | 64 | 126 | -6.9R |
| Neutral Reference | alpha_v1_total | -0.02 | 625 | 153 | 328 | -10.4R |
| 10y-Safe Branch | nq_ny_lsi_long | -0.06 | 321 | 61 | 185 | -12.2R |
| 10y-Safe Branch | nq_asia_orb_long | -0.04 | 306 | 90 | 172 | -7.5R |
| 10y-Safe Branch | es_asia_orb_long | -0.04 | 580 | 140 | 316 | -11.3R |
| 10y-Safe Branch | es_ny_orb_long | 0.05 | 455 | 119 | 203 | -10.3R |
| 10y-Safe Branch | alpha_v1_total | -0.04 | 1015 | 255 | 526 | -10.9R |
| Recent-Strength Branch | nq_ny_lsi_long | -0.05 | 180 | 31 | 106 | -10.4R |
| Recent-Strength Branch | nq_asia_orb_long | -0.05 | 310 | 91 | 175 | -7.5R |
| Recent-Strength Branch | es_asia_orb_long | -0.04 | 441 | 105 | 245 | -11.3R |
| Recent-Strength Branch | es_ny_orb_long | 0.07 | 345 | 79 | 159 | -9.9R |
| Recent-Strength Branch | alpha_v1_total | -0.04 | 780 | 189 | 415 | -10.9R |

## Read

- The **10y-safe branch** is the best if the priority is long-history durability. It roughly adds `+71R` over the neutral reference full-history, improves DD, and has the best 0.25x full-history payout scorecard, but it gives up recent/current-regime heat.
- The **recent-strength branch** is the best if the priority is the current Hunter behavior: strongest 2025+ and last-1y, best recent payout speed, and still improves full-history net versus neutral. Its DD and negative-year profile are weaker, so it should stay a challenger rather than replace the neutral branch outright.
- The **neutral reference** remains the best control leg. It has the cleanest interpretation and avoids the Tuesday long-history/current-regime fork.
- In ALPHA_V1 portfolio context, adding Hunter at `0.25x` beats risk-down ES NY + Hunter on total R for all three branches. Risking down ES NY improves worst month/DD slightly but gives up too much net.
- Correlation remains low to ALPHA_V1 legs. Overlap risk is not zero, but it is not concentrated enough to block a small pilot.

## Artifacts

- Results packet: `backtesting/data/results/hunter_classic_next_tests_downstream_20260502`
- Repro script: `backtesting/scripts/run_hunter_classic_next_tests_downstream.py`

