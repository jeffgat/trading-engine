# NQ NY HTF-LSI Window + Exit Local Sweep

- Objective: answer whether the promoted `5m lag24` lead has a better sub-window inside `08:30-15:00`, and whether `rr / tp1` should move when that branch is compared gated vs ungated.
- Scope: structure held fixed to the promoted lead (`long`, `fvg_limit`, `gap3.0`, `htf60`, `n3`, `cap2`, `fvgL20`, `fvgR2`, `lag24`).
- Selection discipline: all ranking uses pre-holdout discovery/validation only. Stitched OOS and opened holdout are reported only as secondary reads for the finalists.

## Current Window Gate Check

| Gate | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `skip_bear_high_vol` | 316 | 1.247 | 122 | 1.644 | 0.289 | 8.138 |
| `skip_medium_vol` | 296 | 1.213 | 66 | 1.500 | 0.218 | 3.504 |
| `ungated` | 379 | 1.188 | 127 | 1.597 | 0.268 | 6.382 |

## Best Windows By Gate

### skip_medium_vol

| Window | Minutes | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |

### ungated

| Window | Minutes | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `08:30-13:30` | 300 | 339 | 1.230 | 117 | 1.668 | 0.300 | 6.602 |
| `08:30-14:00` | 330 | 355 | 1.226 | 120 | 1.644 | 0.289 | 6.505 |
| `08:30-14:30` | 360 | 365 | 1.208 | 123 | 1.627 | 0.281 | 6.492 |
| `08:30-15:00` | 390 | 379 | 1.188 | 127 | 1.597 | 0.268 | 6.382 |
| `08:30-13:00` | 270 | 322 | 1.237 | 115 | 1.635 | 0.290 | 6.259 |

### skip_bear_high_vol

| Window | Minutes | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `08:30-13:30` | 300 | 284 | 1.279 | 113 | 1.705 | 0.316 | 8.265 |
| `08:30-14:00` | 330 | 297 | 1.283 | 116 | 1.679 | 0.304 | 8.147 |
| `08:30-15:00` | 390 | 316 | 1.247 | 122 | 1.644 | 0.289 | 8.138 |
| `08:30-14:30` | 360 | 305 | 1.262 | 119 | 1.661 | 0.295 | 8.130 |
| `08:30-13:00` | 270 | 271 | 1.290 | 111 | 1.670 | 0.306 | 7.843 |

## Local Exit Sweep

### ungated on `08:30-13:30`

| RR | TP1 | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3.50 | 0.40 | 339 | 1.270 | 117 | 1.717 | 0.292 | 6.831 |
| 3.00 | 0.60 | 339 | 1.230 | 117 | 1.668 | 0.300 | 6.602 |
| 3.50 | 0.50 | 339 | 1.229 | 117 | 1.658 | 0.298 | 6.540 |
| 2.75 | 0.50 | 339 | 1.247 | 117 | 1.682 | 0.277 | 6.475 |
| 3.25 | 0.40 | 339 | 1.260 | 117 | 1.645 | 0.265 | 6.209 |

### skip_bear_high_vol on `08:30-13:30`

| RR | TP1 | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3.50 | 0.40 | 284 | 1.326 | 113 | 1.764 | 0.309 | 8.524 |
| 3.00 | 0.60 | 284 | 1.279 | 113 | 1.705 | 0.316 | 8.265 |
| 3.50 | 0.50 | 284 | 1.287 | 113 | 1.695 | 0.314 | 8.195 |
| 2.75 | 0.50 | 284 | 1.298 | 113 | 1.727 | 0.294 | 8.093 |
| 2.75 | 0.60 | 284 | 1.285 | 113 | 1.667 | 0.298 | 7.785 |

## Finalist Secondary Read

| Label | Gate | Window | RR | TP1 | OOS PF | OOS Avg R | OOS Calmar | Holdout PF | Holdout Avg R | Holdout Calmar |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `best_skip_bear_high_vol` | `skip_bear_high_vol` | `08:30-13:30` | 3.50 | 0.40 | 1.590 | 0.246 | 9.942 | 2.264 | 0.445 | 5.338 |
| `baseline_skip_bear_high_vol` | `skip_bear_high_vol` | `08:30-15:00` | 3.00 | 0.60 | 1.473 | 0.217 | 8.537 | 2.290 | 0.462 | 6.003 |
| `best_ungated` | `ungated` | `08:30-13:30` | 3.50 | 0.40 | 1.467 | 0.199 | 5.432 | 2.089 | 0.398 | 5.036 |
| `baseline_ungated` | `ungated` | `08:30-15:00` | 3.00 | 0.60 | 1.347 | 0.162 | 4.849 | 2.200 | 0.430 | 6.024 |