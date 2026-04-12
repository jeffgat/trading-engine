# NQ NY HTF-LSI Count Expansion

- Objective: move the 5m HTF-LSI branch closer to `60-80` filled trades per year without reopening the full discovery tree.
- Holdout remains frozen at `2025-04-01+`; this report only uses `2016-01-01` to `2025-03-31`.
- Anchor: `long fvg_limit gap3.0 right2 lag24 cap2` with `54.7` pre-holdout trades/year and `56.5` validation trades/year.

## Top Target-Band Candidates

| Config | Pre/Yr | Val/Yr | Val PF | Val Avg R | Val Calmar | 2024 Trades | 2025 Q1 Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `long fvg_limit gap2.5 right2 lag0 cap2` | 66.4 | 69.0 | 1.668 | 0.265 | 7.328 | 78 | 11 |
| `long fvg_limit gap2.5 right2 lag0 cap3` | 66.4 | 69.0 | 1.668 | 0.265 | 7.328 | 78 | 11 |
| `long fvg_limit gap2.5 right2 lag30 cap2` | 60.8 | 61.8 | 1.683 | 0.294 | 6.592 | 72 | 11 |
| `long fvg_limit gap2.5 right2 lag30 cap3` | 60.8 | 61.8 | 1.683 | 0.294 | 6.592 | 72 | 11 |
| `long fvg_limit gap2.5 right3 lag0 cap2` | 70.2 | 71.2 | 1.569 | 0.243 | 6.457 | 81 | 11 |
| `long fvg_limit gap2.5 right3 lag0 cap3` | 70.2 | 71.2 | 1.569 | 0.243 | 6.457 | 81 | 11 |
| `long fvg_limit gap3.0 right2 lag0 cap2` | 62.2 | 67.2 | 1.556 | 0.224 | 6.208 | 75 | 11 |
| `long fvg_limit gap3.0 right2 lag0 cap3` | 62.2 | 67.2 | 1.556 | 0.224 | 6.208 | 75 | 11 |
| `long fvg_limit gap2.5 right3 lag24 cap2` | 62.8 | 62.3 | 1.600 | 0.280 | 6.198 | 73 | 11 |
| `long fvg_limit gap2.5 right3 lag24 cap3` | 62.8 | 62.3 | 1.600 | 0.280 | 6.198 | 73 | 11 |
| `long fvg_limit gap3.0 right3 lag0 cap2` | 66.1 | 69.4 | 1.460 | 0.201 | 6.119 | 78 | 11 |
| `long fvg_limit gap3.0 right3 lag0 cap3` | 66.1 | 69.4 | 1.460 | 0.201 | 6.119 | 78 | 11 |
| `long fvg_limit gap2.5 right3 lag30 cap2` | 64.7 | 64.5 | 1.569 | 0.263 | 5.767 | 75 | 11 |
| `long fvg_limit gap2.5 right3 lag30 cap3` | 64.7 | 64.5 | 1.569 | 0.263 | 5.767 | 75 | 11 |
| `long fvg_limit gap3.0 right3 lag30 cap2` | 60.4 | 62.3 | 1.460 | 0.219 | 5.175 | 71 | 11 |

## Best Overall Compromises

| Config | In Band | Pre/Yr | Val/Yr | Val PF | Val Avg R | Val Calmar | 2024 Trades |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `long fvg_limit gap2.5 right2 lag0 cap2` | yes | 66.4 | 69.0 | 1.668 | 0.265 | 7.328 | 78 |
| `long fvg_limit gap2.5 right2 lag0 cap3` | yes | 66.4 | 69.0 | 1.668 | 0.265 | 7.328 | 78 |
| `long fvg_limit gap2.5 right2 lag30 cap2` | yes | 60.8 | 61.8 | 1.683 | 0.294 | 6.592 | 72 |
| `long fvg_limit gap2.5 right2 lag30 cap3` | yes | 60.8 | 61.8 | 1.683 | 0.294 | 6.592 | 72 |
| `long fvg_limit gap2.5 right3 lag0 cap2` | yes | 70.2 | 71.2 | 1.569 | 0.243 | 6.457 | 81 |
| `long fvg_limit gap2.5 right3 lag0 cap3` | yes | 70.2 | 71.2 | 1.569 | 0.243 | 6.457 | 81 |
| `long fvg_limit gap3.0 right2 lag0 cap2` | yes | 62.2 | 67.2 | 1.556 | 0.224 | 6.208 | 75 |
| `long fvg_limit gap3.0 right2 lag0 cap3` | yes | 62.2 | 67.2 | 1.556 | 0.224 | 6.208 | 75 |
| `long fvg_limit gap2.5 right3 lag24 cap2` | yes | 62.8 | 62.3 | 1.600 | 0.280 | 6.198 | 73 |
| `long fvg_limit gap2.5 right3 lag24 cap3` | yes | 62.8 | 62.3 | 1.600 | 0.280 | 6.198 | 73 |
| `long fvg_limit gap3.0 right3 lag0 cap2` | yes | 66.1 | 69.4 | 1.460 | 0.201 | 6.119 | 78 |
| `long fvg_limit gap3.0 right3 lag0 cap3` | yes | 66.1 | 69.4 | 1.460 | 0.201 | 6.119 | 78 |
| `long fvg_limit gap2.5 right3 lag30 cap2` | yes | 64.7 | 64.5 | 1.569 | 0.263 | 5.767 | 75 |
| `long fvg_limit gap2.5 right3 lag30 cap3` | yes | 64.7 | 64.5 | 1.569 | 0.263 | 5.767 | 75 |
| `long fvg_limit gap3.0 right3 lag30 cap2` | yes | 60.4 | 62.3 | 1.460 | 0.219 | 5.175 | 71 |

## Effect: `direction_filter`

| Value | Avg Pre/Yr | Avg Val/Yr | Avg Val PF | Avg Val Calmar | Best Val PF | Best Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `both` | 122.3 | 121.8 | 1.158 | 1.603 | 1.345 | 4.171 |
| `long` | 72.6 | 73.4 | 1.360 | 3.165 | 1.718 | 7.507 |

## Effect: `entry_mode`

| Value | Avg Pre/Yr | Avg Val/Yr | Avg Val PF | Avg Val Calmar | Best Val PF | Best Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `close` | 102.2 | 101.6 | 1.149 | 1.119 | 1.338 | 2.330 |
| `fvg_limit` | 92.8 | 93.6 | 1.369 | 3.650 | 1.718 | 7.507 |

## Effect: `min_gap_atr_pct`

| Value | Avg Pre/Yr | Avg Val/Yr | Avg Val PF | Avg Val Calmar | Best Val PF | Best Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `2.0` | 107.8 | 107.1 | 1.241 | 2.051 | 1.577 | 4.080 |
| `2.5` | 96.3 | 95.8 | 1.295 | 2.581 | 1.718 | 7.507 |
| `3.0` | 88.4 | 89.8 | 1.242 | 2.522 | 1.597 | 6.382 |

## Effect: `lsi_fvg_window_right`

| Value | Avg Pre/Yr | Avg Val/Yr | Avg Val PF | Avg Val Calmar | Best Val PF | Best Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `2` | 89.3 | 90.5 | 1.325 | 2.929 | 1.718 | 7.507 |
| `3` | 95.4 | 96.1 | 1.262 | 2.500 | 1.600 | 6.457 |
| `5` | 107.8 | 106.2 | 1.190 | 1.725 | 1.416 | 3.624 |

## Effect: `max_fvg_to_inversion_bars`

| Value | Avg Pre/Yr | Avg Val/Yr | Avg Val PF | Avg Val Calmar | Best Val PF | Best Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `0` | 103.5 | 105.2 | 1.261 | 2.541 | 1.668 | 7.328 |
| `24` | 93.0 | 92.1 | 1.265 | 2.336 | 1.718 | 7.507 |
| `30` | 96.0 | 95.5 | 1.251 | 2.276 | 1.683 | 6.592 |

## Effect: `htf_trade_max_per_session`

| Value | Avg Pre/Yr | Avg Val/Yr | Avg Val PF | Avg Val Calmar | Best Val PF | Best Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `2` | 97.5 | 97.6 | 1.259 | 2.384 | 1.718 | 7.507 |
| `3` | 97.5 | 97.6 | 1.259 | 2.385 | 1.718 | 7.507 |