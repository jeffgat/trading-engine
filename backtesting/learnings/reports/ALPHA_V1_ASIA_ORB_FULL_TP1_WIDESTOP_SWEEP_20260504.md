# ALPHA_V1 Asia ORB Full-TP1 Wide-Stop Sweep (2026-05-04)

- Window: `2016-04-17` to `2026-03-24`
- Scope: `NQ Asia ORB` and `ES Asia ORB` only.
- Test: if `risk_points >= large_sl_threshold_points`, exit the full trade at the normal TP1 level instead of taking a partial at TP1 and targeting TP2.
- Baseline behavior and all entries/stops/re-entry caps remain unchanged.
- Deployability: all rows are `research_only` until execution/exact replay support for `wide_stop_full_exit_at_tp1` is wired.

## Baseline Risk Distribution

| leg | fills | risk_min | risk_p50 | risk_p75 | risk_p90 | risk_max |
| --- | --- | --- | --- | --- | --- | --- |
| nq_asia_orb_long | 722 | 1.51 | 12.17 | 19.50 | 31.50 | 110 |
| es_asia_orb_long | 1422 | 3 | 4.06 | 6.56 | 10.62 | 73.75 |

## Two-Leg Baseline

| window | fills | net_r | profit_factor | sharpe_ratio | max_drawdown_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- |
| full | 2144 | 359 | 1.40 | 1.28 | -16.97 | 0 |
| 2024_plus | 476 | 102 | 1.51 | 1.79 | -10.25 | 0 |
| 2025_plus | 266 | 70.41 | 1.65 | 2.03 | -8.05 | 0 |
| last_1y | 216 | 58.07 | 1.65 | 2.10 | -8.05 | 0 |

## Best NQ Asia Rows

| large_sl_threshold_points | fills | net_r | delta_net_r | profit_factor | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | 722 | 217 | 3.82 | 1.56 | -10.16 | 0 | 0 |
| 40 | 722 | 217 | 3.51 | 1.56 | -10.16 | 0 | 0 |
| 25 | 722 | 216 | 2.80 | 1.56 | -10.16 | 0 | 0 |
| 30 | 722 | 215 | 1.57 | 1.55 | -10.16 | 0 | 0 |
| 50 | 722 | 214 | 0.79 | 1.55 | -10.16 | 0 | 0 |
| 17.50 | 722 | 214 | 0.78 | 1.55 | -10.16 | 0 | 0 |
| 20 | 722 | 211 | -2.02 | 1.54 | -10.16 | 0 | 0 |
| 15 | 722 | 210 | -3.99 | 1.54 | -10.16 | 0 | 0 |

## Best ES Asia Rows

| large_sl_threshold_points | fills | net_r | delta_net_r | profit_factor | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 15 | 1422 | 146 | -0.18 | 1.28 | -12.28 | 0 | 0 |
| 20 | 1422 | 145 | -0.70 | 1.28 | -12.28 | 0 | 0 |
| 12 | 1422 | 144 | -1.36 | 1.28 | -12.28 | 0 | 0 |
| 10 | 1422 | 141 | -4.56 | 1.27 | -12.50 | -0.22 | 0 |
| 9 | 1422 | 140 | -6.26 | 1.27 | -12.50 | -0.22 | 0 |
| 8 | 1422 | 138 | -8.25 | 1.27 | -12.75 | -0.47 | 0 |
| 7 | 1422 | 134 | -12.21 | 1.26 | -12.75 | -0.47 | 0 |
| 6 | 1422 | 131 | -15.03 | 1.25 | -13.21 | -0.93 | 0 |

## Best Combined NQ+ES Asia Rows

| variant | fills | net_r | delta_net_r | profit_factor | sharpe_ratio | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_sl35p0__es_baseline | 2144 | 363 | 3.82 | 1.40 | 1.30 | -16.97 | 0 | 0 |
| nq_sl35p0__es_sl15p0 | 2144 | 363 | 3.63 | 1.40 | 1.30 | -16.97 | 0 | 0 |
| nq_sl40p0__es_baseline | 2144 | 363 | 3.51 | 1.40 | 1.30 | -16.97 | 0 | 0 |
| nq_sl40p0__es_sl15p0 | 2144 | 363 | 3.33 | 1.40 | 1.30 | -16.97 | 0 | 0 |
| nq_sl35p0__es_sl20p0 | 2144 | 362 | 3.12 | 1.40 | 1.30 | -16.97 | 0 | 0 |
| nq_sl40p0__es_sl20p0 | 2144 | 362 | 2.81 | 1.40 | 1.30 | -16.97 | 0 | 0 |
| nq_sl25p0__es_baseline | 2144 | 362 | 2.80 | 1.40 | 1.31 | -17.21 | -0.24 | 0 |
| nq_sl25p0__es_sl15p0 | 2144 | 362 | 2.61 | 1.40 | 1.31 | -17.21 | -0.24 | 0 |
| nq_sl35p0__es_sl12p0 | 2144 | 362 | 2.46 | 1.40 | 1.30 | -16.97 | 0 | 0 |
| nq_sl40p0__es_sl12p0 | 2144 | 362 | 2.15 | 1.40 | 1.29 | -16.97 | 0 | 0 |

## Recent Combined Check

| variant | fills | net_r | delta_net_r | profit_factor | sharpe_ratio | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_sl35p0__es_sl12p0 | 266 | 71.83 | 1.42 | 1.66 | 2.04 | -8.05 | 0 | 0 |
| nq_sl35p0__es_baseline | 266 | 71.39 | 0.98 | 1.65 | 2.06 | -8.05 | 0 | 0 |
| nq_sl35p0__es_sl15p0 | 266 | 71.28 | 0.87 | 1.65 | 2.06 | -8.05 | 0 | 0 |
| nq_sl35p0__es_sl20p0 | 266 | 71.21 | 0.80 | 1.65 | 2.06 | -8.05 | 0 | 0 |
| nq_sl40p0__es_sl12p0 | 266 | 70.93 | 0.52 | 1.65 | 2.02 | -8.05 | 0 | 0 |
| nq_baseline__es_sl12p0 | 266 | 70.85 | 0.44 | 1.65 | 2.01 | -8.05 | 0 | 0 |
| nq_sl30p0__es_sl12p0 | 266 | 70.80 | 0.39 | 1.65 | 2.01 | -8.05 | 0 | 0 |
| nq_sl40p0__es_baseline | 266 | 70.49 | 0.08 | 1.65 | 2.03 | -8.05 | 0 | 0 |
| nq_sl50p0__es_sl12p0 | 266 | 70.44 | 0.03 | 1.65 | 2 | -8.05 | 0 | 0 |
| nq_sl40p0__es_sl15p0 | 266 | 70.38 | -0.03 | 1.65 | 2.03 | -8.05 | 0 | 0 |

## Read

- NQ Asia best full-history threshold is `35.0` points, but its full-history delta is `3.82R`.
- ES Asia best full-history threshold is `15.0` points, with full-history delta `-0.18R`.
- Combined best full-history pair is `nq_sl35p0__es_baseline` with delta `3.82R` and DD change `0.0R`.
- Treat this as a research-only exit-management probe, not a deployable config, until live sizing/order handling can close the entire remaining position at TP1 conditionally by stop size.

## Artifacts

- Result directory: `data/results/alpha_v1_asia_orb_full_tp1_widestop_sweep_20260504`
- `leg_metrics_by_window.csv`
- `combined_metrics_by_window.csv`
- `risk_distribution.csv`
- `summary.json`
