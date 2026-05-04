# NQ NY LSI CISD Survivor Refinement

- Purpose: refine validation/holdout survivors from the staged NQ NY LSI/CISD sequence.
- Discovery: `2016-01-01` to `2023-01-01`.
- Validation: `2023-01-01` to `2025-04-01`.
- Holdout: `2025-04-01` onward.
- Targets fixed at `rr=2.0`, `tp1_ratio=0.5`.

## Stage Counts

- `survivor_stop`: 77 configs
- `survivor_source`: 16 configs

## Top Robust Rows

| Rank | Label | D Tr | D PF | D Calmar | V Tr | V PF | V Calmar | H Tr | H PF | H Calmar | CISD | Inversion |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `1m|survivor_stop|additive|classic_swing|level_limit|atr_pct10|bars3|atr7.5` | 433 | 1.18 | 2.01 | 106 | 1.37 | 2.43 | 58 | 1.75 | 2.89 | 186 | 411 |
| 2 | `1m|survivor_source|classic_swing|inversion_or_cisd|level_limit|atr_pct10|bars3|atr7.5` | 433 | 1.18 | 2.01 | 106 | 1.37 | 2.43 | 58 | 1.75 | 2.89 | 186 | 411 |
| 3 | `1m|survivor_stop|pure_cisd|classic_swing|level_limit|atr_pct15|bars2|atr7.5` | 223 | 1.09 | 0.82 | 52 | 1.52 | 1.33 | 41 | 1.69 | 2.49 | 316 | 0 |
| 4 | `1m|survivor_source|classic_swing|cisd|level_limit|atr_pct15|bars2|atr7.5` | 223 | 1.09 | 0.82 | 52 | 1.52 | 1.33 | 41 | 1.69 | 2.49 | 316 | 0 |
| 5 | `1m|survivor_stop|pure_cisd|classic_swing|level_limit|fvg|bars2|atr7.5` | 223 | 0.91 | -0.43 | 51 | 1.43 | 1.50 | 41 | 1.35 | 1.34 | 315 | 0 |
| 6 | `1m|survivor_source|classic_swing|cisd|level_limit|fvg|bars2|atr7.5` | 223 | 0.91 | -0.43 | 51 | 1.43 | 1.50 | 41 | 1.35 | 1.34 | 315 | 0 |
| 7 | `3m|survivor_source|hourly_htf|inversion_or_cisd|level_limit|atr_pct12.5|bars3|atr7.5` | 416 | 1.13 | 1.59 | 140 | 1.14 | 1.32 | 46 | 1.80 | 2.38 | 89 | 513 |
| 8 | `3m|survivor_stop|additive|classic_swing|level_limit|atr_pct12.5|bars3|atr7.5` | 363 | 1.03 | 0.36 | 114 | 1.18 | 1.27 | 45 | 1.67 | 2.62 | 90 | 432 |
| 9 | `3m|survivor_source|classic_swing|inversion_or_cisd|level_limit|atr_pct12.5|bars3|atr7.5` | 363 | 1.03 | 0.36 | 114 | 1.18 | 1.27 | 45 | 1.67 | 2.62 | 90 | 432 |
| 10 | `1m|survivor_stop|pure_cisd|classic_swing|level_limit|absolute|bars2|atr5` | 328 | 1.05 | 0.87 | 92 | 1.47 | 3.38 | 52 | 1.21 | 1.27 | 472 | 0 |
| 11 | `1m|survivor_stop|additive|classic_swing|level_limit|atr_pct10|bars2|atr5` | 531 | 1.16 | 1.93 | 146 | 1.23 | 1.25 | 73 | 1.23 | 1.10 | 418 | 332 |
| 12 | `3m|survivor_stop|additive|classic_swing|level_limit|absolute|bars3|atr7.5` | 361 | 1.08 | 0.84 | 114 | 1.19 | 1.12 | 44 | 1.66 | 2.89 | 90 | 429 |
| 13 | `1m|survivor_stop|pure_cisd|classic_swing|level_limit|absolute|bars2|atr7.5` | 223 | 1.05 | 0.53 | 52 | 1.29 | 1.11 | 41 | 1.57 | 2.15 | 316 | 0 |
| 14 | `3m|survivor_stop|additive|classic_swing|level_limit|atr_pct12.5|bars4|atr10` | 338 | 1.01 | 0.11 | 109 | 1.16 | 1.09 | 43 | 1.62 | 2.61 | 35 | 455 |
| 15 | `3m|survivor_stop|additive|classic_swing|level_limit|absolute|bars4|atr10` | 336 | 1.07 | 0.81 | 109 | 1.18 | 1.01 | 42 | 1.26 | 1.18 | 35 | 452 |
| 16 | `3m|survivor_stop|additive|classic_swing|level_limit|atr_pct12.5|bars4|atr12.5` | 337 | 1.02 | 0.16 | 107 | 1.16 | 0.97 | 42 | 1.74 | 2.94 | 31 | 455 |
| 17 | `1m|survivor_stop|additive|classic_swing|level_limit|atr_pct12.5|bars3|atr7.5` | 433 | 1.11 | 1.56 | 106 | 1.30 | 1.76 | 58 | 1.21 | 0.82 | 186 | 411 |
| 18 | `1m|survivor_stop|additive|classic_swing|level_limit|atr_pct7.5|bars3|atr7.5` | 433 | 1.08 | 0.81 | 106 | 1.39 | 1.93 | 58 | 1.24 | 0.79 | 186 | 411 |
| 19 | `1m|survivor_stop|pure_cisd|classic_swing|level_limit|atr_pct7.5|bars2|atr7.5` | 223 | 1.20 | 1.66 | 52 | 1.32 | 1.42 | 41 | 1.27 | 0.81 | 316 | 0 |
| 20 | `3m|survivor_stop|additive|classic_swing|level_limit|absolute|bars4|atr12.5` | 335 | 1.08 | 0.88 | 107 | 1.17 | 0.78 | 41 | 1.36 | 1.40 | 31 | 452 |
