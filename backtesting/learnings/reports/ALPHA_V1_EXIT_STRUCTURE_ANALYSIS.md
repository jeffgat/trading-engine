# ALPHA_V1 Exit Structure Analysis

- Objective: pressure-test whether the active `ALPHA_V1` exit structure benefits from the current TP1/TP2 ladder or whether simpler / more prop-friendly exits dominate.
- Method: keep the active `ALPHA_V1` fills fixed, then replay each filled trade with alternative exits on the same intraday path using 1-minute data and 1-second drill-down only when a minute touches a live threshold.
- Policies compared:
  - `Current TP1/TP2 replay`
  - `Full TP only`
  - `3-level TP (TP1 / midpoint / TP2)`
  - `Drawdown scale (50% at -0.5R, rest at -1R)`
- Common recent window for all legs: `2024-01-01` onward.
- Caveat: these are same-fill counterfactuals. That is exact for the cap=1 ORB legs and approximate for the cap=2 NQ NY HTF-LSI leg because alternative exits could affect same-session re-entry availability.

## HTF_LSI/NQ_NY-L24

- Backtest window: `2016-01-03` to `2026-03-24`

### Policy Comparison

| Policy | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Full Win Rate | p75 Winner MAE (R) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current TP1/TP2 replay | 96.0 | 10.6 | 9.05 | 35.4 | 5.5 | 6.39 | 52.8% | 0.62 |
| Full TP only | 98.7 | 12.3 | 8.03 | 33.9 | 7.2 | 4.68 | 45.1% | 0.64 |
| 3-level TP (TP1 / midpoint / TP2) | 93.4 | 10.8 | 8.67 | 34.1 | 5.8 | 5.91 | 53.0% | 0.62 |
| Drawdown scale (50% at -0.5R, rest at -1R) | 77.0 | 9.7 | 7.91 | 23.2 | 5.5 | 4.22 | 39.7% | 0.56 |

### Target Frontier

| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | p75 Winner MAE (R) | p90 Winner MAE (R) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.5 | 85.5 | 9.4 | 9.10 | 33.2 | 5.5 | 5.99 | 0.62 | 0.80 |
| 2.0 | 92.0 | 9.9 | 9.31 | 30.4 | 5.5 | 5.49 | 0.62 | 0.80 |
| 2.5 | 87.2 | 10.7 | 8.18 | 31.7 | 5.5 | 5.71 | 0.62 | 0.81 |
| 3.0 | 94.0 | 10.6 | 8.87 | 34.5 | 5.5 | 6.22 | 0.62 | 0.81 |
| 3.5 | 96.0 | 10.6 | 9.05 | 35.4 | 5.5 | 6.39 | 0.62 | 0.81 |

## ORB/NQ_ASIA-RR6

- Backtest window: `2016-01-03` to `2026-03-24`

### Policy Comparison

| Policy | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Full Win Rate | p75 Winner MAE (R) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current TP1/TP2 replay | 213.2 | 9.1 | 23.38 | 54.3 | 6.0 | 9.05 | 45.4% | 0.69 |
| Full TP only | 269.6 | 15.7 | 17.18 | 64.2 | 6.0 | 10.70 | 36.8% | 0.70 |
| 3-level TP (TP1 / midpoint / TP2) | 212.7 | 9.8 | 21.72 | 54.1 | 6.0 | 9.01 | 45.4% | 0.69 |
| Drawdown scale (50% at -0.5R, rest at -1R) | 194.7 | 14.4 | 13.52 | 49.2 | 4.8 | 10.23 | 34.1% | 0.68 |

### Target Frontier

| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | p75 Winner MAE (R) | p90 Winner MAE (R) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.0 | 184.0 | 9.7 | 19.00 | 52.8 | 6.7 | 7.92 | 0.68 | 0.83 |
| 2.5 | 196.1 | 9.2 | 21.27 | 53.7 | 6.3 | 8.50 | 0.69 | 0.83 |
| 3.0 | 197.8 | 8.9 | 22.12 | 50.5 | 7.0 | 7.24 | 0.69 | 0.84 |
| 4.0 | 199.2 | 9.6 | 20.77 | 52.9 | 6.0 | 8.82 | 0.69 | 0.84 |
| 5.0 | 206.5 | 9.1 | 22.64 | 52.7 | 6.0 | 8.78 | 0.69 | 0.84 |
| 6.0 | 213.2 | 9.1 | 23.38 | 54.3 | 6.0 | 9.05 | 0.69 | 0.84 |

## ORB/ES_ASIA-RR1.5

- Backtest window: `2016-01-03` to `2026-03-24`

### Policy Comparison

| Policy | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Full Win Rate | p75 Winner MAE (R) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current TP1/TP2 replay | 186.9 | 12.5 | 14.97 | 45.8 | 7.7 | 5.98 | 55.2% | 0.57 |
| Full TP only | 227.1 | 19.0 | 11.95 | 50.9 | 8.4 | 6.03 | 48.0% | 0.58 |
| 3-level TP (TP1 / midpoint / TP2) | 187.6 | 13.1 | 14.32 | 46.3 | 7.8 | 5.92 | 55.2% | 0.57 |
| Drawdown scale (50% at -0.5R, rest at -1R) | 179.8 | 14.0 | 12.85 | 44.6 | 5.6 | 7.96 | 46.5% | 0.58 |

### Target Frontier

| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | p75 Winner MAE (R) | p90 Winner MAE (R) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.5 | 186.9 | 12.5 | 14.97 | 45.8 | 7.7 | 5.98 | 0.57 | 0.77 |

## ORB/ES_NY-RR5

- Backtest window: `2016-01-03` to `2026-03-24`

### Policy Comparison

| Policy | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Full Win Rate | p75 Winner MAE (R) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current TP1/TP2 replay | 220.3 | 9.2 | 24.07 | 54.8 | 5.5 | 9.90 | 63.4% | 0.58 |
| Full TP only | 197.1 | 28.9 | 6.81 | 39.3 | 17.7 | 2.22 | 27.3% | 0.67 |
| 3-level TP (TP1 / midpoint / TP2) | 196.3 | 10.7 | 18.40 | 45.2 | 6.7 | 6.78 | 63.4% | 0.58 |
| Drawdown scale (50% at -0.5R, rest at -1R) | 160.7 | 22.2 | 7.25 | 40.8 | 12.5 | 3.26 | 25.9% | 0.67 |

### Target Frontier

| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | p75 Winner MAE (R) | p90 Winner MAE (R) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.5 | 188.2 | 9.1 | 20.65 | 48.1 | 5.0 | 9.57 | 0.58 | 0.83 |
| 2.0 | 166.6 | 9.0 | 18.45 | 40.8 | 6.1 | 6.64 | 0.58 | 0.83 |
| 2.5 | 178.3 | 9.2 | 19.48 | 44.2 | 6.8 | 6.47 | 0.58 | 0.83 |
| 3.0 | 190.2 | 9.2 | 20.78 | 44.4 | 6.6 | 6.76 | 0.58 | 0.83 |
| 4.0 | 212.2 | 9.2 | 23.19 | 54.0 | 6.1 | 8.93 | 0.58 | 0.83 |
| 5.0 | 220.3 | 9.2 | 24.07 | 54.8 | 5.5 | 9.90 | 0.58 | 0.84 |
