# NQ Hunter Classic Three-Candidate Downstream Validation (2026-05-02)

## Scope

This packet moves the three frozen stress-gated Hunter candidates from the strategy workflow into downstream validation. No new parameters were searched here. The stress gate remains: skip `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`.

## Candidates

| Label | Candidate | Role | Params |
| --- | --- | --- | --- |
| Workflow Leader | `ema14_tol0_distnone_relegacy_samewin0` | workflow/pre-HO leader | EMA14, 0pt tolerance, no distance cap, legacy one reentry after loss |
| Balanced Challenger | `ema14_tol2_distnone_relegacy_samewin0` | balanced 10y/workflow challenger | EMA14, 2pt tolerance, no distance cap, legacy one reentry after loss |
| Recent Challenger | `ema10_tol0_dist150_reall_samewin0` | recent hot-regime challenger | EMA10, 0pt tolerance, 150pt distance cap, all non-overlap reentries |

## Core Performance

| Label | Candidate | Full Net | Full DD | 2025+ Net | Last 1y Net | Last 1y WR | Full PF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Workflow Leader | `ema14_tol0_distnone_relegacy_samewin0` | +162.9R | -40.5R | +104.2R | +88.4R | 57.0% | 1.17 |
| Balanced Challenger | `ema14_tol2_distnone_relegacy_samewin0` | +164.7R | -41.8R | +108.5R | +92.8R | 57.4% | 1.17 |
| Recent Challenger | `ema10_tol0_dist150_reall_samewin0` | +163.2R | -41.8R | +132.9R | +107.6R | 60.4% | 1.17 |

## Rolling Stress

| Label | Worst Month | Worst 3m DD | Worst 6m DD | Worst 6m Sum | Negative Months |
| --- | --- | --- | --- | --- | --- |
| Workflow Leader | -20.4R | -29.9R | -29.9R | -26.1R | 45 |
| Balanced Challenger | -20.4R | -29.9R | -29.9R | -26.9R | 45 |
| Recent Challenger | -20.4R | -29.9R | -29.9R | -29.2R | 48 |

## Monte Carlo Bootstrap at 0.25x Risk

| Label | Median Net | p05 Net | Median DD | p05 DD | Prob DD <= -20R |
| --- | --- | --- | --- | --- | --- |
| Workflow Leader | +40.4R | +8.2R | -12.2R | -22.3R | 8.4% |
| Balanced Challenger | +41.0R | +8.9R | -12.3R | -22.0R | 8.2% |
| Recent Challenger | +41.2R | +8.9R | -11.9R | -21.8R | 7.8% |

## Phase-One Scorecard, 14-Day Staggered Starts at 0.25x Risk

| Label | Window | Accounts | Payout | Breach | Open | Median Days to Payout | EV/Attempt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Workflow Leader | full_10y | 261 | 40.6% | 57.5% | 1.9% | 206 | $103 |
| Workflow Leader | holdout_2025_plus | 34 | 85.3% | 0.0% | 14.7% | 117 | $326 |
| Workflow Leader | last_1y | 26 | 76.9% | 0.0% | 23.1% | 110 | $285 |
| Balanced Challenger | full_10y | 261 | 41.0% | 57.5% | 1.5% | 204 | $105 |
| Balanced Challenger | holdout_2025_plus | 34 | 88.2% | 0.0% | 11.8% | 116 | $341 |
| Balanced Challenger | last_1y | 26 | 80.8% | 0.0% | 19.2% | 109 | $304 |
| Recent Challenger | full_10y | 261 | 36.8% | 61.3% | 1.9% | 174 | $84 |
| Recent Challenger | holdout_2025_plus | 34 | 85.3% | 0.0% | 14.7% | 110 | $326 |
| Recent Challenger | last_1y | 26 | 76.9% | 0.0% | 23.1% | 98 | $285 |

## ALPHA_V1 Portfolio Fit

| Label | Scenario | Net | DD | Worst Month | Corr |
| --- | --- | --- | --- | --- | --- |
| Workflow Leader | ALPHA_V1 baseline | +597.1R | -15.6R | -12.2R | -0.01 |
| Workflow Leader | + Hunter 0.25x | +620.9R | -16.7R | -11.1R | -0.01 |
| Workflow Leader | ES_NY 0.75x + Hunter 0.25x | +589.3R | -16.1R | -10.3R | -0.01 |
| Balanced Challenger | ALPHA_V1 baseline | +597.1R | -15.6R | -12.2R | -0.02 |
| Balanced Challenger | + Hunter 0.25x | +621.4R | -16.7R | -11.1R | -0.02 |
| Balanced Challenger | ES_NY 0.75x + Hunter 0.25x | +589.7R | -16.1R | -10.3R | -0.02 |
| Recent Challenger | ALPHA_V1 baseline | +597.1R | -15.6R | -12.2R | -0.01 |
| Recent Challenger | + Hunter 0.25x | +619.7R | -16.7R | -11.1R | -0.01 |
| Recent Challenger | ES_NY 0.75x + Hunter 0.25x | +588.0R | -16.1R | -10.3R | -0.01 |

## Read

- The balanced challenger is the slight pilot preference: it is nearly tied with the workflow leader pre-holdout, but improves full history, 2025+, last 1y, and the 0.25x phase-one scorecard.
- The workflow leader remains the cleanest search-discipline fallback because it won pre-holdout without seeing 2025+.
- The recent challenger keeps the best last-year profile, but it is still the most hindsight-sensitive branch because its pre-holdout score is much weaker.
- At 0.25x risk, all three are viable as paper/live pilot legs beside ALPHA_V1; larger sizing should wait for more forward data because full-risk Monte Carlo and historical drawdowns remain too large for a single funded account.

## Artifacts

- Results packet: `backtesting/data/results/hunter_classic_three_candidate_downstream_20260502`
- Repro script: `backtesting/scripts/run_hunter_classic_three_candidate_downstream.py`

