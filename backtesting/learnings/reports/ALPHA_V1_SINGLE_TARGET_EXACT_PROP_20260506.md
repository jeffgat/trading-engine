# ALPHA_V1 Single-Target Exact Replay + Phase-One Sizing

- Run slug: `alpha_v1_single_target_exact_prop_20260506`
- Exact/live-engine window: `2016-04-17` to `2026-03-24`
- Engine path: `execution/src/trader/historical_backtest.py` using temporary in-memory execution profiles.
- Base profile cloned where applicable: `ALPHA_V1-A`. No live execution config file was edited.
- Account model: 50k account, 2k EOD trailing drawdown, trail cap at 50k, first payout at 52.5k, $500 first payout, $100 account/reset cost, starts every 14 calendar days.
- Deployability: all three candidates are `live_native`; exact replay status is `complete`.

## Exact Replay Stats

| label | trades | net_r | profit_factor | win_rate_pct | max_dd_r | target_rate_pct | sl_rate_pct | eod_rate_pct | result_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB single 1.0R | 849 | 102 | 1.28 | 55.8 | 12.2 | 55.0 | 43.0 | 2.00 | bt-alpha-v1-exact-singletarget-es-ny-orb-single-1-0-89f860 |
| NQ NY ORB R11 single 1.4R | 554 | 137 | 1.47 | 52.2 | 6.40 | 51.6 | 47.6 | 0.72 | bt-alpha-v1-exact-singletarget-nq-ny-orb-r11-single-842410 |
| ES Asia ORB single 1.25R | 1428 | 220 | 1.34 | 52.0 | 15.0 | 47.6 | 45.2 | 7.14 | bt-alpha-v1-exact-singletarget-es-asia-orb-single-1-dee938 |

## Research Vs Exact Replay

| label | research_net_r | exact_net_r | delta_r | research_pf | exact_pf | research_dd_r | exact_dd_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB single 1.0R | 186 | 102 | -84.8 | 1.57 | 1.28 | 8.00 | 12.2 |
| NQ NY ORB R11 single 1.4R | 149 | 137 | -12.5 | 1.58 | 1.47 | 6.40 | 6.40 |
| ES Asia ORB single 1.25R | 174 | 220 | 45.9 | 1.32 | 1.34 | 13.6 | 15.0 |

## Preferred Phase-One Sizing

_Preferred means the fastest row that still clears at least 75% payout and at most 10% breach. If no row clears that guard, it falls back to the guarded positive-EV row._

| label | risk_usd | payouts | breaches | open | payout_rate_pct | breach_rate_pct | ev_per_account_usd | avg_days_to_payout | max_consecutive_breaches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB single 1.0R | 175 | 206 | 24 | 30 | 79.2 | 9.23 | 296 | 403 | 12 |
| NQ NY ORB R11 single 1.4R | 325 | 230 | 17 | 13 | 88.5 | 6.54 | 342 | 187 | 6 |
| ES Asia ORB single 1.25R | 200 | 236 | 14 | 10 | 90.8 | 5.38 | 354 | 189 | 6 |

## Conservative Low-Breach Sizing

_This is the highest-EV row with no more than 10% breaches. It is safer but can be materially slower._

| label | risk_usd | payouts | breaches | open | payout_rate_pct | breach_rate_pct | ev_per_account_usd | avg_days_to_payout | max_consecutive_breaches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB single 1.0R | 150 | 218 | 0 | 42 | 83.8 | 0.00 | 319 | 496 | 0 |
| NQ NY ORB R11 single 1.4R | 300 | 241 | 0 | 19 | 92.7 | 0.00 | 363 | 209 | 0 |
| ES Asia ORB single 1.25R | 125 | 246 | 0 | 14 | 94.6 | 0.00 | 373 | 294 | 0 |

## Risk Buckets

| label | bucket | risk_usd | payouts | breaches | payout_rate_pct | breach_rate_pct | ev_per_account_usd | avg_days_to_payout | max_consecutive_breaches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB single 1.0R | best_balanced | 150 | 218 | 0 | 83.8 | 0.00 | 319 | 496 | 0 |
| ES NY ORB single 1.0R | best_ev | 150 | 218 | 0 | 83.8 | 0.00 | 319 | 496 | 0 |
| ES NY ORB single 1.0R | best_guarded | 150 | 218 | 0 | 83.8 | 0.00 | 319 | 496 | 0 |
| ES NY ORB single 1.0R | best_low_breach | 150 | 218 | 0 | 83.8 | 0.00 | 319 | 496 | 0 |
| ES NY ORB single 1.0R | best_sprint | 175 | 206 | 24 | 79.2 | 9.23 | 296 | 403 | 12 |
| ES NY ORB single 1.0R | best_low_breach_ev | 150 | 218 | 0 | 83.8 | 0.00 | 319 | 496 | 0 |
| NQ NY ORB R11 single 1.4R | best_balanced | 300 | 241 | 0 | 92.7 | 0.00 | 363 | 209 | 0 |
| NQ NY ORB R11 single 1.4R | best_ev | 300 | 241 | 0 | 92.7 | 0.00 | 363 | 209 | 0 |
| NQ NY ORB R11 single 1.4R | best_guarded | 300 | 241 | 0 | 92.7 | 0.00 | 363 | 209 | 0 |
| NQ NY ORB R11 single 1.4R | best_low_breach | 300 | 241 | 0 | 92.7 | 0.00 | 363 | 209 | 0 |
| NQ NY ORB R11 single 1.4R | best_sprint | 325 | 230 | 17 | 88.5 | 6.54 | 342 | 187 | 6 |
| NQ NY ORB R11 single 1.4R | best_low_breach_ev | 300 | 241 | 0 | 92.7 | 0.00 | 363 | 209 | 0 |
| ES Asia ORB single 1.25R | best_balanced | 125 | 246 | 0 | 94.6 | 0.00 | 373 | 294 | 0 |
| ES Asia ORB single 1.25R | best_ev | 125 | 246 | 0 | 94.6 | 0.00 | 373 | 294 | 0 |
| ES Asia ORB single 1.25R | best_guarded | 125 | 246 | 0 | 94.6 | 0.00 | 373 | 294 | 0 |
| ES Asia ORB single 1.25R | best_low_breach | 125 | 246 | 0 | 94.6 | 0.00 | 373 | 294 | 0 |
| ES Asia ORB single 1.25R | best_sprint | 200 | 236 | 14 | 90.8 | 5.38 | 354 | 189 | 6 |
| ES Asia ORB single 1.25R | best_low_breach_ev | 125 | 246 | 0 | 94.6 | 0.00 | 373 | 294 | 0 |

## Read

- `best_sprint` is the practical phase-one default: it prioritizes time to payout inside a 75% payout / 10% breach guard.
- `best_low_breach_ev` is the conservative standalone default when speed matters less than avoiding resets.
- `best_guarded` is a broad positive-EV fallback: at least 35% payout rate when possible and no more than 45% breaches.
- `best_ev` is included as an aggressive ceiling; it can over-size a choppy leg if the EV comes with poor breach clustering.
- The exact replay materially haircut ES NY versus the research sweep, so exact replay should supersede the earlier optimistic ES NY single-target read.
