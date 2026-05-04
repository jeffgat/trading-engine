# NQ NY LSI CISD Sequence

- Discovery: `2016-01-01` to `2023-01-01`.
- Validation: `2023-01-01` to `2025-04-01`.
- Holdout: `2025-04-01` onward.
- Targets fixed at `rr=2.0`, `tp1_ratio=0.5`.
- Directions: both long and short.

## Stage Counts

- `phase1_classic`: 18 configs
- `phase2_body`: 64 configs
- `phase3_timeframe`: 12 configs
- `phase4_sources`: 20 configs
- `phase5_stops`: 35 configs

## Top Discovery Rows

| Rank | Label | D Tr | D PF | D Calmar | V Tr | V PF | V Calmar | H Tr | H PF | H Calmar |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `5m|classic|inversion_or_cisd|level_limit|absolute` | 408 | 1.25 | 6.08 | 115 | 0.90 | -0.59 | 41 | 0.68 | -0.57 |
| 2 | `5m|body|inversion_or_cisd|level_limit|absolute|bars2|atr5` | 408 | 1.25 | 6.08 | 115 | 0.90 | -0.59 | 41 | 0.68 | -0.57 |
| 3 | `5m|tf|inversion_or_cisd|level_limit|absolute|bars2|atr5` | 408 | 1.25 | 6.08 | 115 | 0.90 | -0.59 | 41 | 0.68 | -0.57 |
| 4 | `5m|source|classic_swing|inversion_or_cisd|level_limit|absolute` | 408 | 1.25 | 6.08 | 115 | 0.90 | -0.59 | 41 | 0.68 | -0.57 |
| 5 | `5m|stop|classic_swing|inversion_or_cisd|level_limit|absolute` | 408 | 1.25 | 6.08 | 115 | 0.90 | -0.59 | 41 | 0.68 | -0.57 |
| 6 | `5m|body|inversion_or_cisd|level_limit|absolute|bars4|atr12.5` | 340 | 1.30 | 5.99 | 100 | 0.86 | -0.64 | 33 | 0.51 | -0.79 |
| 7 | `5m|tf|inversion_or_cisd|level_limit|absolute|bars4|atr12.5` | 340 | 1.30 | 5.99 | 100 | 0.86 | -0.64 | 33 | 0.51 | -0.79 |
| 8 | `5m|source|classic_swing|inversion_or_cisd|level_limit|absolute` | 340 | 1.30 | 5.99 | 100 | 0.86 | -0.64 | 33 | 0.51 | -0.79 |
| 9 | `5m|stop|classic_swing|inversion_or_cisd|level_limit|absolute` | 340 | 1.30 | 5.99 | 100 | 0.86 | -0.64 | 33 | 0.51 | -0.79 |
| 10 | `5m|body|inversion_or_cisd|level_limit|absolute|bars4|atr10` | 341 | 1.29 | 5.90 | 100 | 0.86 | -0.64 | 33 | 0.51 | -0.79 |
| 11 | `5m|tf|inversion_or_cisd|level_limit|absolute|bars4|atr10` | 341 | 1.29 | 5.90 | 100 | 0.86 | -0.64 | 33 | 0.51 | -0.79 |
| 12 | `5m|source|classic_swing|inversion_or_cisd|level_limit|absolute` | 341 | 1.29 | 5.90 | 100 | 0.86 | -0.64 | 33 | 0.51 | -0.79 |

## Top Validation Rows

| Rank | Label | D Tr | D PF | D Calmar | V Tr | V PF | V Calmar | H Tr | H PF | H Calmar |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `1m|tf|inversion_or_cisd|level_limit|absolute|bars2|atr5` | 529 | 1.07 | 1.32 | 145 | 1.38 | 2.43 | 72 | 0.83 | -0.61 |
| 2 | `5m|stop|classic_swing|inversion_or_cisd|level_limit|atr_pct15` | 344 | 1.07 | 1.15 | 100 | 1.23 | 1.81 | 33 | 0.33 | -0.90 |
| 3 | `5m|stop|classic_swing|inversion_or_cisd|level_limit|atr_pct15` | 345 | 1.07 | 1.10 | 100 | 1.23 | 1.81 | 33 | 0.33 | -0.90 |
| 4 | `5m|stop|classic_swing|inversion_or_cisd|level_limit|atr_pct15` | 411 | 1.08 | 1.65 | 115 | 1.19 | 1.47 | 41 | 0.44 | -0.91 |
| 5 | `1m|source|hourly_htf|inversion_or_cisd|level_limit|absolute` | 507 | 1.08 | 0.97 | 159 | 1.16 | 1.23 | 63 | 0.72 | -0.69 |
| 6 | `5m|stop|classic_swing|inversion_or_cisd|level_limit|atr_pct15` | 366 | 1.09 | 1.62 | 103 | 1.17 | 1.22 | 33 | 0.33 | -0.90 |
| 7 | `5m|stop|classic_swing|inversion_or_cisd|level_limit|atr_pct12.5` | 411 | 1.10 | 1.91 | 115 | 1.17 | 1.16 | 41 | 0.35 | -0.93 |
| 8 | `3m|tf|inversion_or_cisd|level_limit|absolute|bars3|atr7.5` | 361 | 1.08 | 0.84 | 114 | 1.19 | 1.12 | 44 | 1.66 | 2.89 |
| 9 | `1m|tf|inversion_or_cisd|level_limit|absolute|bars3|atr7.5` | 430 | 1.15 | 2.67 | 105 | 1.22 | 1.09 | 57 | 0.87 | -0.43 |
| 10 | `1m|source|classic_swing|inversion_or_cisd|level_limit|absolute` | 430 | 1.15 | 2.67 | 105 | 1.22 | 1.09 | 57 | 0.87 | -0.43 |
| 11 | `3m|tf|inversion_or_cisd|level_limit|absolute|bars4|atr10` | 336 | 1.07 | 0.81 | 109 | 1.18 | 1.01 | 42 | 1.26 | 1.18 |
| 12 | `5m|stop|classic_swing|inversion_or_cisd|level_limit|atr_pct12.5` | 344 | 1.07 | 1.07 | 100 | 1.14 | 1.00 | 33 | 0.25 | -0.96 |