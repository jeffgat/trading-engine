# NQ NY LSI/CISD Hot-Regime Sweep

- Run slug: `nq_ny_lsi_cisd_hot_regime_sweep_20260504`
- Data latest date: `2026-05-01`
- Optimization window: `2025-05-01` to `2026-05-01`
- Intent: in-sample trailing-one-year squeeze for the pure-CISD leg and the two additive finalist legs.
- Status: `research_only`; this is not a robust promotion packet.
- Stage 1 structure rows: `540`. Stage 2 target rows: `792`.

## Best Target Rows By Family

| leg | trades | win_rate | total_r | max_dd_r | profit_factor | long | short | cisd | inv | stop | bars | body_atr | cut | rr | tp1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Additive allDOW | 45 | 68.9% | 15.48 | -4.07 | 2.11 | 29 | 16 | 17 | 28 | 10.00 | 3 | 7.50 | 13:00 | 2.50 | 0.40 |
| Additive noThu | 38 | 65.8% | 10.95 | -3.07 | 1.84 | 23 | 15 | 14 | 24 | 10.00 | 2 | 7.50 | 13:00 | 2.50 | 0.40 |
| Pure CISD | 15 | 73.3% | 9.42 | -2.00 | 3.36 | 15 | 0 | 15 | 0 | 7.50 | 4 | 5.00 | 14:00 | 4.00 | 0.30 |

## Top 10 Overall By Net R

| family | trades | win_rate | total_r | max_dd_r | profit_factor | long | short | cisd | inv | stop | bars | body_atr | cut | rr | tp1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| add_allDOW | 45 | 68.9% | 15.48 | -4.07 | 2.11 | 29 | 16 | 17 | 28 | 10.00 | 3 | 7.50 | 13:00 | 2.50 | 0.40 |
| add_allDOW | 52 | 65.4% | 15.04 | -4.60 | 1.84 | 35 | 17 | 22 | 30 | 10.00 | 3 | 7.50 | 14:00 | 2.50 | 0.40 |
| add_allDOW | 55 | 65.5% | 14.96 | -5.07 | 1.79 | 38 | 17 | 22 | 33 | 10.00 | 3 | 7.50 | 15:30 | 2.50 | 0.40 |
| add_allDOW | 49 | 65.3% | 14.44 | -4.67 | 1.85 | 32 | 17 | 23 | 26 | 10.00 | 2 | 7.50 | 13:00 | 2.50 | 0.40 |
| add_allDOW | 45 | 62.2% | 13.66 | -5.00 | 1.80 | 29 | 16 | 17 | 28 | 10.00 | 3 | 7.50 | 13:00 | 2.00 | 0.60 |
| add_allDOW | 45 | 68.9% | 13.44 | -4.07 | 1.96 | 29 | 16 | 17 | 28 | 10.00 | 3 | 7.50 | 13:00 | 2.00 | 0.50 |
| add_allDOW | 45 | 66.7% | 13.42 | -3.60 | 1.89 | 30 | 15 | 13 | 32 | 10.00 | 3 | 10.00 | 14:00 | 2.50 | 0.40 |
| add_allDOW | 48 | 66.7% | 13.35 | -4.07 | 1.83 | 33 | 15 | 13 | 35 | 10.00 | 3 | 10.00 | 15:30 | 2.50 | 0.40 |
| add_allDOW | 62 | 62.9% | 13.32 | -5.60 | 1.58 | 42 | 20 | 33 | 29 | 10.00 | 2 | 7.50 | 15:30 | 2.50 | 0.40 |
| add_allDOW | 52 | 59.6% | 13.23 | -6.00 | 1.63 | 35 | 17 | 22 | 30 | 10.00 | 3 | 7.50 | 14:00 | 2.00 | 0.60 |

## Baseline Vs Best

| leg | baseline_r | best_r | delta_r | baseline_dd | best_dd | baseline_trades | best_trades |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Additive allDOW | 14.96 | 15.48 | 0.51 | -5.07 | -4.07 | 55 | 45 |
| Additive noThu | 10.47 | 10.95 | 0.47 | -4.60 | -3.07 | 45 | 38 |
| Pure CISD | 7.41 | 9.42 | 2.02 | -2.00 | -2.00 | 20 | 15 |

## Read

- Rows are intentionally optimized on the same trailing-year window they report, so treat them as hot-regime research candidates.
- The highest-net-R rows answer the squeeze question; prefer follow-up exact replay and forward testing before deployment sizing.
