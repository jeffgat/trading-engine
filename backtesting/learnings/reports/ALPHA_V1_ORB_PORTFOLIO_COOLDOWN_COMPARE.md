# ALPHA_V1 ORB Portfolio Cooldown Compare

- Scope: combined ALPHA_V1 ORB portfolio only (`NQ Asia`, `ES Asia`, `ES NY`).
- Rules compared:
  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.
  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.
- Trigger model: seed one account on the first trading day of each window, then add a new account when the master daily stream moves another `+/-2R` away from the last launch anchor.
- Cooldown model: only one fresh account can be launched per start date, with a minimum cooldown of `1`, `7`, or `14` calendar days between launches.
- Resolution model: `+5R` payout / `-4R` breach on the same daily R stream.
- `2026 YTD` is partial in this repo: `2026-01-01` to `2026-03-24`.

## Portfolio

| period | rules | cooldown_label | trades | starts | payouts | breaches | open | resolved_payout_rate | avg_start_gap_days | net_r | max_dd_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | Current single-trade legs | 1 day | 2989 | 611 | 430 | 179 | 2 | 70.61 | 5.93 | 360 | -21.18 |
| Last 10y available | Current single-trade legs | 7 days | 2989 | 405 | 278 | 123 | 4 | 69.33 | 8.97 | 360 | -21.18 |
| Last 10y available | Current single-trade legs | 14 days | 2989 | 251 | 173 | 76 | 2 | 69.48 | 14.51 | 360 | -21.18 |
| Last 10y available | Optimized rules | 1 day | 3418 | 711 | 497 | 211 | 3 | 70.20 | 5.11 | 440 | -21.38 |
| Last 10y available | Optimized rules | 7 days | 3418 | 418 | 297 | 119 | 2 | 71.39 | 8.70 | 440 | -21.38 |
| Last 10y available | Optimized rules | 14 days | 3418 | 258 | 187 | 70 | 1 | 72.76 | 14.09 | 440 | -21.38 |
| 2024 | Current single-trade legs | 1 day | 300 | 57 | 37 | 18 | 2 | 67.27 | 6.18 | 27.57 | -9.52 |
| 2024 | Current single-trade legs | 7 days | 300 | 31 | 19 | 9 | 3 | 67.86 | 11.67 | 27.57 | -9.52 |
| 2024 | Current single-trade legs | 14 days | 300 | 22 | 12 | 8 | 2 | 60 | 16.86 | 27.57 | -9.52 |
| 2024 | Optimized rules | 1 day | 353 | 59 | 41 | 14 | 4 | 74.55 | 6.07 | 48.41 | -10.54 |
| 2024 | Optimized rules | 7 days | 353 | 41 | 31 | 8 | 2 | 79.49 | 8.75 | 48.41 | -10.54 |
| 2024 | Optimized rules | 14 days | 353 | 25 | 19 | 5 | 1 | 79.17 | 14.67 | 48.41 | -10.54 |
| 2025 | Current single-trade legs | 1 day | 305 | 75 | 57 | 16 | 2 | 78.08 | 4.92 | 58.10 | -9.88 |
| 2025 | Current single-trade legs | 7 days | 305 | 47 | 36 | 11 | 0 | 76.60 | 7.78 | 58.10 | -9.88 |
| 2025 | Current single-trade legs | 14 days | 305 | 26 | 20 | 6 | 0 | 76.92 | 14.32 | 58.10 | -9.88 |
| 2025 | Optimized rules | 1 day | 348 | 78 | 61 | 15 | 2 | 80.26 | 4.73 | 62.15 | -11.31 |
| 2025 | Optimized rules | 7 days | 348 | 45 | 38 | 6 | 1 | 86.36 | 8.25 | 62.15 | -11.31 |
| 2025 | Optimized rules | 14 days | 348 | 27 | 23 | 3 | 1 | 88.46 | 14 | 62.15 | -11.31 |
| 2026 YTD | Current single-trade legs | 1 day | 71 | 14 | 8 | 3 | 3 | 72.73 | 5.46 | 10.40 | -8.06 |
| 2026 YTD | Current single-trade legs | 7 days | 71 | 10 | 5 | 3 | 2 | 62.50 | 8.11 | 10.40 | -8.06 |
| 2026 YTD | Current single-trade legs | 14 days | 71 | 6 | 3 | 2 | 1 | 60 | 14 | 10.40 | -8.06 |
| 2026 YTD | Optimized rules | 1 day | 90 | 18 | 11 | 5 | 2 | 68.75 | 4.59 | 14.53 | -11.94 |
| 2026 YTD | Optimized rules | 7 days | 90 | 12 | 7 | 3 | 2 | 70 | 7.09 | 14.53 | -11.94 |
| 2026 YTD | Optimized rules | 14 days | 90 | 6 | 3 | 2 | 1 | 60 | 14 | 14.53 | -11.94 |

## Optimized Minus Current

| period | cooldown_label | trade_delta | start_delta | payout_delta | breach_delta | open_delta | resolved_payout_rate_delta | avg_start_gap_days_delta | net_r_delta | max_dd_r_delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | 1 day | 429 | 100 | 67 | 32 | 1 | -0.41 | -0.82 | 80.47 | -0.20 |
| Last 10y available | 7 days | 429 | 13 | 19 | -4 | -2 | 2.06 | -0.27 | 80.47 | -0.20 |
| Last 10y available | 14 days | 429 | 7 | 14 | -6 | -1 | 3.28 | -0.42 | 80.47 | -0.20 |
| 2024 | 1 day | 53 | 2 | 4 | -4 | 2 | 7.28 | -0.11 | 20.84 | -1.02 |
| 2024 | 7 days | 53 | 10 | 12 | -1 | -1 | 11.63 | -2.92 | 20.84 | -1.02 |
| 2024 | 14 days | 53 | 3 | 7 | -3 | -1 | 19.17 | -2.19 | 20.84 | -1.02 |
| 2025 | 1 day | 43 | 3 | 4 | -1 | 0 | 2.18 | -0.19 | 4.05 | -1.43 |
| 2025 | 7 days | 43 | -2 | 2 | -5 | 1 | 9.76 | 0.47 | 4.05 | -1.43 |
| 2025 | 14 days | 43 | 1 | 3 | -3 | 1 | 11.54 | -0.32 | 4.05 | -1.43 |
| 2026 YTD | 1 day | 19 | 4 | 3 | 2 | -1 | -3.98 | -0.87 | 4.13 | -3.88 |
| 2026 YTD | 7 days | 19 | 2 | 2 | 0 | 0 | 7.50 | -1.02 | 4.13 | -3.88 |
| 2026 YTD | 14 days | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 4.13 | -3.88 |
