# NQ Hunter Classic Original Combo Grid, 2025+ (2026-05-02)

This is an intentionally in-sample combo grid over the same 2025+ window as the original ungated ablation. It combines the strongest one-at-a-time looseners and checks whether they stack.

- Window: `2025-01-01` through `2026-04-24`
- Grid size: `768` configs
- Baseline original ungated: 195 trades, +157.3R, PF 1.55, DD -26.8R

## Best By Net R

| Rank | Config | Trades | Net | WR | PF | DD | Net/DD |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `no_ema__noTue__1300__body0_rej20__allNonOverlap__always2R__ungated` | 362 | +372.9R | 46.4% | 1.65 | -26.8R | 13.92 |
| 2 | `ema14_tol5__noTue__1300__body0_rej20__allNonOverlap__always2R__ungated` | 348 | +365.9R | 46.6% | 1.67 | -25.8R | 14.18 |
| 3 | `no_ema__noTue__1300__body0_rej100__allNonOverlap__always2R__ungated` | 532 | +360.5R | 41.5% | 1.45 | -37.3R | 9.67 |
| 4 | `ema14_tol5__noTue__1300__body0_rej100__allNonOverlap__always2R__ungated` | 511 | +350.6R | 41.3% | 1.46 | -37.9R | 9.26 |
| 5 | `ema14_tol2__noTue__1300__body0_rej20__allNonOverlap__always2R__ungated` | 344 | +349.1R | 46.2% | 1.64 | -25.8R | 13.53 |
| 6 | `no_ema__noTue__1300__body0_rej20__afterLoss__always2R__ungated` | 341 | +342.7R | 46.9% | 1.64 | -32.6R | 10.50 |
| 7 | `no_ema__withTue__1300__body0_rej20__allNonOverlap__always2R__ungated` | 454 | +338.1R | 43.4% | 1.44 | -35.9R | 9.41 |
| 8 | `ema14_tol5__withTue__1300__body0_rej20__allNonOverlap__always2R__ungated` | 436 | +338.0R | 43.8% | 1.46 | -35.9R | 9.40 |
| 9 | `no_ema__withTue__1300__body0_rej100__allNonOverlap__always2R__ungated` | 682 | +332.3R | 40.0% | 1.31 | -42.0R | 7.91 |
| 10 | `ema14_tol2__noTue__1300__body0_rej100__allNonOverlap__always2R__ungated` | 504 | +331.0R | 41.1% | 1.43 | -37.1R | 8.91 |

## Best Net-R Params

- EMA: off
- Weekdays: Mon/Wed/Thu/Fri
- Signal end: 13:00
- Body min: 0%
- Rejection max: 20%
- Reentry: all_nonoverlap
- Wide stop target: always 2R
- Stress gate: off

Best net result: `no_ema__noTue__1300__body0_rej20__allNonOverlap__always2R__ungated` -> 362 trades, +372.9R, 46.4% WR, PF 1.65, DD -26.8R.
Delta vs original baseline: +215.6R net, +0.0R DD.

## Risk-Aware Check

Best balanced (`net - 0.5*abs(DD)`) is `no_ema__noTue__1300__body0_rej20__allNonOverlap__always2R__ungated` -> +372.9R, DD -26.8R, PF 1.65.
Best Net/DD is `ema14_tol5__noTue__1300__body0_rej20__allNonOverlap__always2R__ungated` -> +365.9R, DD -25.8R, Net/DD 14.18.

## Read

- For pure 2025+ in-sample net R, the optimized shape is aggressive: no stress gate, no Tuesday, signal window extended to `13:00`, body filter removed, rejection-wick filter retained, looser same-day reentry, and always target 2R even on wide stops.
- The combo confirms that the recent hot window wants flow, not protection. Almost every protective gate that helped the 10-year profile trims recent net R.
- This should not be promoted directly. It is a hot-regime research branch and needs the same 10-year/workflow check before it can compete with the stress-gated baseline.

## Artifacts

- Results: `data/results/hunter_classic_original_combo_grid_2025plus_20260502`
- `combo_grid_2025plus.csv`
- `top_net.csv`, `top_balanced.csv`, `top_net_to_dd.csv`
- `selected_trades/*.csv`
