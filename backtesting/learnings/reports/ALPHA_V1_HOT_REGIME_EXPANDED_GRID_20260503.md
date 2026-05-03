# ALPHA_V1 Hot-Regime Expanded Grid

- Run slug: `alpha_v1_hot_regime_expanded_grid_20260503`
- Window: `2016-04-17` to `2026-03-24`
- Intent: larger top-3-per-category Cartesian expansion after the OAT attribution pass.
- This is TESTING-only hot-regime research, not a robust promotion packet.
- Score formula: `3*last1_net + 2*last2_net + full_net - 0.50*abs(last1_dd) - 0.25*abs(last2_dd) - 0.10*abs(full_dd) - 10*full_negative_years - 25*(last1_fills<12)`
- FVG extreme chasing, wide-stop target compression, and close-entry HTF-LSI were kept constrained because the OAT pass already showed they were destructive.

## Selected Combo Seeds

```json
{
  "es_asia_orb": {
    "atr": [
      "atr14",
      "atr20",
      "atr10"
    ],
    "dow": [
      "dow_baseline",
      "dow_exFri",
      "dow_exMon"
    ],
    "entry": [
      "entry_0300",
      "entry_0600",
      "entry_0400"
    ],
    "fvg_selection": [
      "fvg_first"
    ],
    "gap": [
      "min_gap_atr_pct_0p5",
      "min_gap_atr_pct_0p25",
      "min_gap_atr_pct_0p0"
    ],
    "reentry": [
      "cap1",
      "cap2_any",
      "uncapped_any"
    ],
    "rr_tp1": [
      "rr1p5_tp0p7",
      "rr4p0_tp0p25",
      "rr2p0_tp0p5"
    ],
    "stop": [
      "stop_orb_pct_125p0",
      "stop_orb_pct_100p0",
      "stop_orb_pct_75p0"
    ],
    "wide_stop": [
      "wide_none"
    ]
  },
  "es_ny_orb": {
    "atr": [
      "atr7",
      "atr10",
      "atr5"
    ],
    "dow": [
      "dow_baseline",
      "dow_none",
      "dow_exTue"
    ],
    "entry": [
      "entry_1300",
      "entry_1200",
      "entry_1400"
    ],
    "fvg_selection": [
      "fvg_first"
    ],
    "gap": [
      "min_gap_atr_pct_0p25",
      "min_gap_atr_pct_0p75",
      "min_gap_atr_pct_0p5"
    ],
    "reentry": [
      "cap1",
      "cap2_any",
      "uncapped_any"
    ],
    "rr_tp1": [
      "rr5p0_tp0p2",
      "rr7p0_tp0p2",
      "rr6p0_tp0p2"
    ],
    "stop": [
      "stop_atr_pct_5p0",
      "stop_atr_pct_3p0",
      "stop_atr_pct_4p0"
    ],
    "wide_stop": [
      "wide_none"
    ]
  },
  "nq_asia_orb": {
    "atr": [
      "atr5",
      "atr14",
      "atr7"
    ],
    "dow": [
      "dow_baseline",
      "dow_none",
      "dow_exFri"
    ],
    "entry": [
      "entry_2230",
      "entry_2315",
      "entry_0000"
    ],
    "fvg_selection": [
      "fvg_first"
    ],
    "gap": [
      "min_gap_orb_pct_10p0",
      "min_gap_orb_pct_5p0",
      "min_gap_orb_pct_0p0"
    ],
    "reentry": [
      "cap1",
      "uncapped_any",
      "cap2_after_nonpositive"
    ],
    "rr_tp1": [
      "rr6p0_tp0p3",
      "rr8p0_tp0p2",
      "rr7p0_tp0p2"
    ],
    "stop": [
      "stop_orb_pct_100p0",
      "stop_orb_pct_125p0",
      "stop_orb_pct_75p0"
    ],
    "wide_stop": [
      "wide_none"
    ]
  },
  "nq_ny_htf_lsi": {
    "dow": [
      "dow_none",
      "dow_exFri",
      "dow_exMon"
    ],
    "entry_mode": [
      "mode_fvg_limit"
    ],
    "entry_window": [
      "window_0830_1330",
      "window_0830_1430",
      "window_0830_1230"
    ],
    "fvg_window": [
      "fvgL20_R2",
      "fvgL30_R2",
      "fvgL10_R2"
    ],
    "htf_left": [
      "htfN3",
      "htfN2",
      "htfN4"
    ],
    "max_inv": [
      "lag24",
      "lag48",
      "lag36"
    ],
    "min_gap": [
      "gap3p0",
      "gap1p0",
      "gap2p0"
    ],
    "rr_tp1": [
      "rr3p5_tp0p4",
      "rr3p0_tp0p4",
      "rr4p0_tp0p3"
    ],
    "trade_cap": [
      "cap2",
      "cap3",
      "cap0"
    ]
  }
}
```

## Best Candidates

### nq_ny_htf_lsi

| pick | variant | full_net | full_dd | full_pf | neg_y | last2_net | last1_net | last1_dd | last1_pf | fills1y | hot_score | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | 92.58 | -10.94 | 1.446 | 0 | 26.01 | 14.11 | -3 | 1.932 | 39 | 183.0 | warning layer acceptable for TESTING |
| best_last1 | combo__window_0830_1230__dow_exMon__rr3p5_tp0p4__gap1p0__fvgL10_R2__lag24__cap2__mode_fvg_ | 73.54 | -16.02 | 1.268 | 2 | 28.96 | 19.52 | -3.62 | 1.878 | 57 | 164.7 | 2 negative years |
| best_last2 | combo__window_0830_1430__dow_exFri__rr3p5_tp0p4__gap1p0__fvgL10_R2__lag24__cap2__mode_fvg_ | 91.06 | -13.58 | 1.322 | 2 | 32.97 | 19.27 | -5 | 1.82 | 60 | 189.1 | 2 negative years |
| best_score | combo__window_0830_1430__dow_none__rr3p5_tp0p4__gap1p0__fvgL10_R2__lag24__cap2__mode_fvg_l | 113.0 | -16.33 | 1.314 | 0 | 31.22 | 18.06 | -5.62 | 1.548 | 76 | 223.1 | warning layer acceptable for TESTING |

### nq_asia_orb

| pick | variant | full_net | full_dd | full_pf | neg_y | last2_net | last1_net | last1_dd | last1_pf | fills1y | hot_score | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | 213.5 | -10.16 | 1.55 | 0 | 53.16 | 36.31 | -6 | 1.989 | 73 | 423.2 | warning layer acceptable for TESTING |
| best_last1 | combo__entry_2315__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_0p0__cap1__f | 225.6 | -12.95 | 1.352 | 0 | 53.91 | 49.70 | -10.00 | 1.869 | 119 | 473.3 | warning layer acceptable for TESTING |
| best_last2 | combo__entry_2230__dow_none__rr8p0_tp0p2__stop_orb_pct_75p0__min_gap_orb_pct_10p0__uncappe | 217.7 | -20.60 | 1.409 | 1 | 64.45 | 36.55 | -8 | 1.754 | 94 | 438.2 | 1 negative years |
| best_score | combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_10p0__cap2_a | 243.6 | -14.22 | 1.474 | 0 | 61.07 | 41.40 | -7 | 1.91 | 90 | 483.3 | warning layer acceptable for TESTING |

### es_asia_orb

| pick | variant | full_net | full_dd | full_pf | neg_y | last2_net | last1_net | last1_dd | last1_pf | fills1y | hot_score | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | 145.8 | -12.28 | 1.283 | 0 | 39.89 | 21.75 | -5.82 | 1.421 | 143 | 285.3 | warning layer acceptable for TESTING |
| best_last1 | combo__entry_0400__dow_exMon__rr1p5_tp0p7__stop_orb_pct_75p0__min_gap_atr_pct_0p5__uncappe | 132.9 | -36.97 | 1.136 | 2 | 59.34 | 56.50 | -6.18 | 1.589 | 260 | 390.8 | 2 negative years; deep full DD -36.97R; low full PF 1.136 |
| best_last2 | combo__entry_0600__dow_exMon__rr1p5_tp0p7__stop_orb_pct_75p0__min_gap_atr_pct_0p5__uncappe | 171.8 | -27.40 | 1.135 | 1 | 62.79 | 55.58 | -8.22 | 1.428 | 330 | 443.7 | 1 negative years; deep full DD -27.4R; low full PF 1.135 |
| best_score | combo__entry_0600__dow_baseline__rr1p5_tp0p7__stop_orb_pct_125p0__min_gap_atr_pct_0p25__un | 252.6 | -21.65 | 1.2 | 1 | 61.17 | 38.52 | -6.38 | 1.321 | 312 | 471.1 | 1 negative years |

### es_ny_orb

| pick | variant | full_net | full_dd | full_pf | neg_y | last2_net | last1_net | last1_dd | last1_pf | fills1y | hot_score | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | 126.6 | -10.86 | 1.386 | 1 | 21.40 | 18.20 | -9.61 | 1.571 | 93 | 205.7 | 1 negative years |
| best_last1 | combo__entry_1300__dow_baseline__rr6p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p25__cap2 | 146.6 | -20.46 | 1.277 | 2 | 46.32 | 25.90 | -14.93 | 1.437 | 127 | 283.7 | 2 negative years |
| best_last2 | combo__entry_1400__dow_baseline__rr6p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p25__unca | 139.8 | -29.24 | 1.199 | 3 | 51.41 | 22.63 | -15.72 | 1.273 | 177 | 265.8 | 3 negative years; deep full DD -29.24R |
| best_score | combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p5__cap2_ | 165.1 | -22.30 | 1.295 | 0 | 50.06 | 20.03 | -13.25 | 1.283 | 124 | 313.2 | warning layer acceptable for TESTING |

## Portfolio Proxy

| portfolio | full_fills | full_net_r | full_pf | full_dd_r | full_negative_years | last_2y_fills | last_2y_net_r | last_2y_pf | last_2y_dd_r | last_1y_fills | last_1y_net_r | last_1y_pf | last_1y_dd_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_current_alpha_v1 | 3471 | 578.5 | 1.401 | -15.40 | 0 | 694 | 140.5 | 1.487 | -13.38 | 348 | 90.38 | 1.658 | -11.21 |
| replace_each_leg_with_best_expanded_hot_score | 5872 | 774.4 | 1.287 | -25.83 | 0 | 1230 | 203.5 | 1.361 | -18.20 | 602 | 118.0 | 1.433 | -18.20 |

## Read

- Prefer the best-score rows for TESTING candidates unless the explicit goal is maximum recent R regardless of 10-year warning damage.
- Any branch here should be dry-run forward tested first; this pass intentionally leans into recent-market overfit risk.
