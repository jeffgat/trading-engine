# ALPHA_V1 ORB Gap-Candle Stop Compare (2026-05-03)

- Window: `2016-04-17` to `2026-03-24`
- Scope: NQ Asia ORB, ES Asia ORB, ES NY ORB from `ALPHA_V1_ORB_REENTRY_2Y.md`.
- Variant: current stop logic versus FVG impulse-candle structural stop.
- Structural stop: long `low[signal_bar - 1] - 1`; short `high[signal_bar - 1] + 1`. Existing engine hard floors remain active: at least 5% daily ATR and each leg's configured point floor.

## Combined ORB Sleeve

| window | profile | fills | net_r | delta_net_r | dd_r | delta_dd_r | wr_pct | pf | avg_r | sharpe | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10yr | current_stop | 2989 | 487 | 0 | -21.18 | 0 | 54.20 | 1.40 | 0.16 | 1.73 | 0 |
| 10yr | gap_impulse_stop | 2990 | 376 | -111 | -28.81 | -7.63 | 51.44 | 1.28 | 0.13 | 1.37 | 0 |
| 2024 | current_stop | 300 | 32.85 | 0 | -9.52 | 0 | 53 | 1.25 | 0.11 | 1.38 | 0 |
| 2024 | gap_impulse_stop | 300 | 24.59 | -8.26 | -13.77 | -4.25 | 52.33 | 1.18 | 0.08 | 1.19 | 0 |
| 2025 | current_stop | 305 | 82.19 | 0 | -9.88 | 0 | 60.66 | 1.71 | 0.27 | 2.80 | 0 |
| 2025 | gap_impulse_stop | 306 | 54.40 | -27.79 | -12.34 | -2.46 | 54.25 | 1.39 | 0.18 | 1.80 | 0 |
| 2026 | current_stop | 71 | 8.71 | 0 | -8.06 | 0 | 53.52 | 1.30 | 0.12 | 1.92 | 0 |
| 2026 | gap_impulse_stop | 71 | 10.29 | 1.58 | -7.20 | 0.86 | 52.11 | 1.33 | 0.14 | 2.68 | 0 |

## Funded First-Payout Model

- Model: $50k account, $2k trailing drawdown capped at $50k, first payout at $52.5k, $500 first withdrawal, $150 challenge fee, new cohort every 14 calendar days.

| window | profile | accounts | payouts | delta_payouts | breaches | delta_breaches | open | payout_rate_pct | breach_rate_pct | ev_per_account_usd | delta_ev_per_account_usd | median_days_to_payout | max_consecutive_breaches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10yr | current_stop | 260 | 186 | 0 | 70 | 0 | 4 | 71.54 | 26.92 | 208 | 0 | 40 | 9 |
| 10yr | gap_impulse_stop | 260 | 170 | -16 | 85 | 15 | 5 | 65.38 | 32.69 | 177 | -30.77 | 44 | 22 |
| 2024 | current_stop | 27 | 15 | 0 | 7 | 0 | 5 | 55.56 | 25.93 | 128 | 0 | 81 | 7 |
| 2024 | gap_impulse_stop | 27 | 14 | -1 | 5 | -2 | 8 | 51.85 | 18.52 | 109 | -18.52 | 76.50 | 5 |
| 2025 | current_stop | 27 | 24 | 0 | 2 | 0 | 1 | 88.89 | 7.41 | 294 | 0 | 32 | 2 |
| 2025 | gap_impulse_stop | 27 | 19 | -5 | 7 | 5 | 1 | 70.37 | 25.93 | 202 | -92.59 | 34 | 4 |
| 2026 | current_stop | 6 | 2 | 0 | 0 | 0 | 4 | 33.33 | 0 | 16.67 | 0 | 35.50 | 0 |
| 2026 | gap_impulse_stop | 6 | 2 | 0 | 0 | 0 | 4 | 33.33 | 0 | 16.67 | 0 | 30.50 | 0 |

## Per-Leg Metrics

| scope | window | profile | fills | net_r | delta_net_r | dd_r | delta_dd_r | pf |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_asia_orb_long | 10yr | current_stop | 722 | 214 | 0 | -10.16 | 0 | 1.55 |
| es_asia_orb_long | 10yr | current_stop | 1422 | 146 | 0 | -12.28 | 0 | 1.28 |
| es_ny_orb_long | 10yr | current_stop | 845 | 128 | 0 | -10.86 | 0 | 1.39 |
| nq_asia_orb_long | 10yr | gap_impulse_stop | 723 | 179 | -34.97 | -18.01 | -7.85 | 1.43 |
| es_asia_orb_long | 10yr | gap_impulse_stop | 1422 | 132 | -13.87 | -19.36 | -7.08 | 1.23 |
| es_ny_orb_long | 10yr | gap_impulse_stop | 845 | 65.03 | -62.55 | -19.98 | -9.12 | 1.17 |
| nq_asia_orb_long | 2024 | current_stop | 68 | 12.59 | 0 | -6.06 | 0 | 1.33 |
| es_asia_orb_long | 2024 | current_stop | 142 | 18.53 | 0 | -5.26 | 0 | 1.35 |
| es_ny_orb_long | 2024 | current_stop | 90 | 1.73 | 0 | -9.74 | 0 | 1.04 |
| nq_asia_orb_long | 2024 | gap_impulse_stop | 68 | 9.27 | -3.32 | -4.84 | 1.22 | 1.23 |
| es_asia_orb_long | 2024 | gap_impulse_stop | 142 | 19.49 | 0.96 | -6.79 | -1.53 | 1.35 |
| es_ny_orb_long | 2024 | gap_impulse_stop | 90 | -4.17 | -5.90 | -11.44 | -1.70 | 0.90 |
| nq_asia_orb_long | 2025 | current_stop | 73 | 37.07 | 0 | -6 | 0 | 2.07 |
| es_asia_orb_long | 2025 | current_stop | 144 | 27.42 | 0 | -4.69 | 0 | 1.53 |
| es_ny_orb_long | 2025 | current_stop | 88 | 17.70 | 0 | -9.61 | 0 | 1.61 |
| nq_asia_orb_long | 2025 | gap_impulse_stop | 74 | 24.18 | -12.89 | -7.15 | -1.15 | 1.57 |
| es_asia_orb_long | 2025 | gap_impulse_stop | 144 | 29.47 | 2.05 | -7.14 | -2.45 | 1.52 |
| es_ny_orb_long | 2025 | gap_impulse_stop | 88 | 0.75 | -16.95 | -10.72 | -1.11 | 1.01 |
| nq_asia_orb_long | 2026 | current_stop | 15 | 4.84 | 0 | -4 | 0 | 1.54 |
| es_asia_orb_long | 2026 | current_stop | 34 | 1.09 | 0 | -5.82 | 0 | 1.10 |
| es_ny_orb_long | 2026 | current_stop | 22 | 2.79 | 0 | -2 | 0 | 1.40 |
| nq_asia_orb_long | 2026 | gap_impulse_stop | 15 | 4.91 | 0.07 | -2.50 | 1.50 | 1.64 |
| es_asia_orb_long | 2026 | gap_impulse_stop | 34 | 1.07 | -0.02 | -6 | -0.18 | 1.08 |
| es_ny_orb_long | 2026 | gap_impulse_stop | 22 | 4.32 | 1.53 | -3.55 | -1.55 | 1.48 |

## Artifacts

- Result directory: `data/results/alpha_v1_orb_gap_candle_stop_compare_20260503`
- `metrics_by_scope_window.csv`
- `funded_first_payout_summary.csv`
- `current_stop_filled_trades.csv`
- `gap_impulse_stop_filled_trades.csv`
