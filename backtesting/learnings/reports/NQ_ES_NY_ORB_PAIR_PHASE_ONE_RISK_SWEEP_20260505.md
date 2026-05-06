# NQ/ES NY ORB Pair Phase-One Risk Sweep

- Run slug: `nq_es_ny_orb_pair_phase_one_risk_sweep_20260505`
- Date range: `2016-04-17` to `2026-03-24`; holdout opened once at `2025-01-01`.
- Candidates are frozen: no signal, stop, target, DOW, or session changes were optimized.
- Funded model: `$50k` account, `$2k` EOD trailing DD capped at `$50k`, first payout trigger `$52.5k`, first withdrawal `$500`, challenge/reset fee `$100`, starts every `14` calendar days.
- Risk grid: independent NQ and ES risk from `$100` to `$650` in `$50` steps.

## Candidate Deployability

| Candidate | deployability | live_support_notes | exact_replay_required |
| --- | --- | --- | --- |
| NQ NY ORB R11 | live_native | Standard ORB continuation fields; not active ALPHA_V1-A yet, but supported by execution knobs. | yes_before_live_promotion |
| ES NY ORB | live_native | Active ALPHA_V1 ES_NY ORB leg; standard execution-supported ORB fields. | yes_before_live_promotion |

## Frozen Candidate Stats

| leg | trades | net_r | profit_factor | max_dd_r | win_rate_pct | avg_r | median_stop_ticks | full_tp_rate_pct | tp1_be_rate_pct | sl_rate_pct | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_ny_orb_r11 | 552 | 129 | 1.50 | -6.00 | 53.3 | 0.23 | 54.9 | 18.1 | 33.0 | 46.4 | 1 |
| es_ny_orb | 846 | 127 | 1.39 | -10.9 | 61.0 | 0.15 | 12.0 | 6.38 | 46.9 | 38.2 | 1 |

## Recent Windows

| leg | window | trades | net_r | profit_factor | max_dd_r | win_rate_pct | full_tp_rate_pct | tp1_be_rate_pct | sl_rate_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_ny_orb_r11 | last_2y | 110 | 18.2 | 1.33 | -6.00 | 50.0 | 17.3 | 30.0 | 50.0 |
| nq_ny_orb_r11 | last_1y | 49 | 6.33 | 1.24 | -6.00 | 46.9 | 16.3 | 26.5 | 53.1 |
| es_ny_orb | last_2y | 183 | 21.4 | 1.30 | -9.74 | 62.3 | 6.01 | 53.5 | 37.7 |
| es_ny_orb | last_1y | 93 | 18.2 | 1.57 | -9.61 | 66.7 | 6.45 | 58.1 | 33.3 |

## Risk Sizing Result

- Pre-holdout best score: NQ `$200` / ES `$100` (pre payout `86.84%`, breach `0.0%`, EV `$334.21`; holdout payout `71.88%`, breach `0.0%`, EV `$259.38`).
- Holdout-confirmed robust pick: NQ `$150` / ES `$150` (pre payout `83.33%`, breach `0.0%`, EV `$316.67`; holdout payout `75.0%`, breach `0.0%`, EV `$275.0`).

## Operating Recommendation

- **Conservative / lowest-breach sizing**: `NQ $150 / ES $150`. This is the best holdout-confirmed no-breach row, but it is slow: holdout average payout time is about `186` calendar days.
- **Phase-one sprint sizing**: `NQ $250 / ES $350` is the preferred speed/EV compromise if the goal is first-payout velocity. It cuts average payout time to about `70` holdout days while keeping the holdout breach rate at `21.9%` and max consecutive holdout breaches at `7`.
- `NQ $300 / ES $350` is a slightly faster alternative with nearly identical payout/EV, but the extra NQ risk does not materially improve the account outcome.
- `NQ $400 / ES $400` is not the preferred default: it is faster, but it pushes the pre-holdout breach rate above `34%` and the holdout breach rate above `34%`, which is too hot for a clustered NY ORB sleeve.

| mode | nq_risk_usd | es_risk_usd | total_risk_usd | pre_payout_rate_pct | pre_breach_rate_pct | pre_ev_per_account_usd | pre_avg_days_to_payout | holdout_payout_rate_pct | holdout_breach_rate_pct | holdout_ev_per_account_usd | holdout_avg_days_to_payout | holdout_max_consecutive_breaches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| conservative_no_breach | 150 | 150 | 300 | 83.3 | 0.00 | 317 | 198 | 75.0 | 0.00 | 275 | 186 | 0 |
| pre_holdout_no_breach_best | 200 | 100 | 300 | 86.8 | 0.00 | 334 | 217 | 71.9 | 0.00 | 259 | 188 | 0 |
| phase_one_sprint_compromise | 250 | 350 | 600 | 74.1 | 23.7 | 271 | 79.1 | 59.4 | 21.9 | 197 | 69.9 | 7 |
| phase_one_sprint_faster | 300 | 350 | 650 | 73.7 | 24.6 | 268 | 72.9 | 59.4 | 21.9 | 197 | 67.9 | 7 |
| too_hot_reference | 400 | 400 | 800 | 64.9 | 34.2 | 225 | 48.5 | 62.5 | 34.4 | 212 | 58.2 | 7 |

## Top Robust Rows

| nq_risk_usd | es_risk_usd | total_risk_usd | pre_payout_rate_pct | pre_breach_rate_pct | pre_ev_per_account_usd | pre_avg_days_to_payout | holdout_payout_rate_pct | holdout_breach_rate_pct | holdout_ev_per_account_usd | holdout_avg_days_to_payout | holdout_confirmed | robust_rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 150 | 150 | 300 | 83.3 | 0.00 | 317 | 198 | 75.0 | 0.00 | 275 | 186 | True | 295 |
| 100 | 150 | 250 | 82.5 | 0.00 | 312 | 230 | 75.0 | 0.00 | 275 | 200 | True | 287 |
| 200 | 100 | 300 | 86.8 | 0.00 | 334 | 217 | 71.9 | 0.00 | 259 | 188 | True | 272 |
| 150 | 100 | 250 | 82.5 | 0.00 | 312 | 245 | 65.6 | 0.00 | 228 | 219 | True | 209 |
| 100 | 100 | 200 | 82.0 | 0.00 | 310 | 295 | 50.0 | 0.00 | 150 | 264 | True | 72.2 |
| 250 | 350 | 600 | 74.1 | 23.7 | 271 | 79.1 | 59.4 | 21.9 | 197 | 69.9 | True | 41.2 |
| 300 | 350 | 650 | 73.7 | 24.6 | 268 | 72.9 | 59.4 | 21.9 | 197 | 67.9 | True | 38.3 |
| 250 | 400 | 650 | 71.5 | 26.8 | 257 | 67.3 | 59.4 | 21.9 | 197 | 61.9 | True | 35.7 |
| 200 | 450 | 650 | 69.7 | 28.5 | 249 | 62.3 | 59.4 | 21.9 | 197 | 57.7 | True | 33.1 |
| 250 | 500 | 750 | 65.3 | 33.3 | 227 | 51.0 | 62.5 | 21.9 | 212 | 56.0 | True | 18.6 |
| 300 | 400 | 700 | 71.9 | 26.8 | 260 | 64.9 | 59.4 | 21.9 | 197 | 59.6 | True | 15.7 |
| 300 | 300 | 600 | 74.6 | 23.7 | 273 | 81.5 | 56.2 | 25.0 | 181 | 70.1 | True | 15.2 |

## Top Pre-Holdout Rows

| nq_risk_usd | es_risk_usd | total_risk_usd | pre_payout_rate_pct | pre_breach_rate_pct | pre_ev_per_account_usd | pre_avg_days_to_payout | holdout_payout_rate_pct | holdout_breach_rate_pct | holdout_ev_per_account_usd | holdout_avg_days_to_payout | holdout_confirmed | robust_rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 200 | 100 | 300 | 86.8 | 0.00 | 334 | 217 | 71.9 | 0.00 | 259 | 188 | True | 272 |
| 150 | 150 | 300 | 83.3 | 0.00 | 317 | 198 | 75.0 | 0.00 | 275 | 186 | True | 295 |
| 100 | 150 | 250 | 82.5 | 0.00 | 312 | 230 | 75.0 | 0.00 | 275 | 200 | True | 287 |
| 150 | 100 | 250 | 82.5 | 0.00 | 312 | 245 | 65.6 | 0.00 | 228 | 219 | True | 209 |
| 100 | 100 | 200 | 82.0 | 0.00 | 310 | 295 | 50.0 | 0.00 | 150 | 264 | True | 72.2 |
| 350 | 250 | 600 | 77.2 | 21.1 | 286 | 87.4 | 56.2 | 25.0 | 181 | 75.7 | True | 11.5 |
| 250 | 300 | 550 | 76.8 | 20.2 | 284 | 91.6 | 53.1 | 28.1 | 166 | 71.9 | True | -15.7 |
| 350 | 300 | 650 | 75.0 | 23.7 | 275 | 74.3 | 56.2 | 25.0 | 181 | 68.0 | True | 15.1 |
| 300 | 300 | 600 | 74.6 | 23.7 | 273 | 81.5 | 56.2 | 25.0 | 181 | 70.1 | True | 15.2 |
| 250 | 350 | 600 | 74.1 | 23.7 | 271 | 79.1 | 59.4 | 21.9 | 197 | 69.9 | True | 41.2 |
| 300 | 350 | 650 | 73.7 | 24.6 | 268 | 72.9 | 59.4 | 21.9 | 197 | 67.9 | True | 38.3 |
| 250 | 400 | 650 | 71.5 | 26.8 | 257 | 67.3 | 59.4 | 21.9 | 197 | 61.9 | True | 35.7 |

## Interpretation

- The risk sweep selects dollar sizing only. It does not rescue a weak strategy with target or stop optimization.
- Because this is a two-leg NY ORB sleeve with clustered NY exposure, the robust pick is preferred over the raw pre-holdout winner when the two disagree.
- Both candidates remain `live_native`, but the NQ leg still needs exact execution replay before promotion into a live execution config.

## Artifacts

- `leg_stats.csv`
- `risk_sweep.csv`
- `pre_best_full_outcomes.csv` / `pre_best_holdout_outcomes.csv`
- `robust_best_full_outcomes.csv` / `robust_best_holdout_outcomes.csv`
- Runtime: `34.7s`
