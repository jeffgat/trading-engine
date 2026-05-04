# Hot One-Year Strategy Workflow

- Run slug: `hot_one_year_strategy_workflow_20260503`
- Optimization window: `2025-03-24` to `2026-03-24`
- Loaded warmup window starts: `2025-01-01`
- Objective: maximize last-year Calmar while looking for Hunter-like recent R.
- This intentionally skips Bailey-style deflation and holdout discipline.
- Cliff control: selected winners should be `curve` or `soft_curve` by one-step local-neighbor checks.
- `GC Asia LSI` has no prior promoted anchor; it uses validated GC NY LSI mechanics transplanted to Asia as the seed.

## Baselines

| leg | note | fills | net_r | calmar | pf | dd | y2025_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nq_ny_orb | NQ R11 NY continuation long | 49 | 6.33 | 1.054 | 1.244 | -6 | 7 |
| nq_asia_orb | NQ R9 Asia restart final | 78 | 9.75 | 1.063 | 1.195 | -9.17 | 6.78 |
| nq_ny_lsi | current ALPHA_V1 HTF-LSI lag24 operating row | 39 | 14.11 | 4.702 | 1.932 | -3 | 14.07 |
| es_ny_orb | ES NY ORB final | 93 | 18.20 | 1.894 | 1.571 | -9.61 | 16.42 |
| es_asia_orb | ES Asia ORB final | 143 | 21.75 | 3.735 | 1.421 | -5.82 | 20.67 |
| es_ny_lsi | ES 3m HTF-LSI balanced restart branch | 49 | -1.04 | -0.14 | 0.971 | -7.45 | 0.72 |
| gc_ny_orb | GC NY R3 high-RR continuation | 53 | 20.09 | 1.768 | 1.583 | -11.36 | 28.77 |
| gc_asia_orb | GC Asia-1 ORB continuation | 128 | 16.71 | 1.445 | 1.237 | -11.57 | 17.94 |
| gc_ny_lsi | GC NY fvg_limit LSI conditional GO | 3 | -1.99 | -0.993 | 0.007 | -2 | -1.99 |
| gc_asia_lsi | GC NY LSI mechanics transplanted to Asia; no prior GC Asia LSI winner | 14 | -1.45 | -0.27 | 0.831 | -5.37 | -1.27 |

## Best Candidates

### NQ NY ORB

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 49 | 6.33 | 1.054 | 1.244 | -6 | 7 | - | 0 |
| best_curve_calmar | combo__orb20m__entry_1300__flat_1430__rr4p0_tp0p3__stop_atr_9p0__gap_orb_10p0__atr12__dir_ | gate_skip_high_vol | curve | 33 | 16.07 | 8.034 | 2.802 | -2 | 9.98 | 0.673 | 3 |
| best_raw_calmar | combo__orb20m__entry_1300__flat_1430__rr4p0_tp0p3__stop_atr_9p0__gap_orb_10p0__atr12__dir_ | gate_skip_high_vol | curve | 33 | 16.07 | 8.034 | 2.802 | -2 | 9.98 | 0.673 | 3 |
| best_curve_net | combo__orb10m__entry_1300__flat_1530__rr3p5_tp0p4__stop_atr_7p0__gap_atr_2p5__atr20__dir_l | gate_none | curve | 89 | 25.65 | 2.75 | 1.602 | -9.33 | 27.75 | 0.918 | 8 |

**Selected option seeds**

```json
{
  "atr": [
    "atr12",
    "atr20"
  ],
  "direction": [
    "dir_long",
    "dir_short"
  ],
  "dow": [
    "dow_baseline",
    "dow_exThu"
  ],
  "entry_end": [
    "entry_1200",
    "entry_1300"
  ],
  "flat_start": [
    "flat_1530",
    "flat_1430"
  ],
  "fvg_selection": [
    "fvg_first",
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_2p5",
    "gap_orb_10p0"
  ],
  "icf": [
    "icf_off",
    "icf_on"
  ],
  "orb_window": [
    "orb20m",
    "orb10m"
  ],
  "reentry": [
    "cap1",
    "cap2_nonpos"
  ],
  "rr_tp1": [
    "rr3p5_tp0p4",
    "rr4p0_tp0p3"
  ],
  "stop": [
    "stop_atr_7p0",
    "stop_atr_9p0"
  ]
}
```

### NQ Asia ORB

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 78 | 9.75 | 1.063 | 1.195 | -9.17 | 6.78 | - | 0 |
| best_curve_calmar | combo__orb15m__entry_2230__flat_0400__rr5p0_tp0p25__stop_atr_4p0__gap_orb_15p0__atr5__dir_ | gate_skip_bear_high_vol | soft_curve | 67 | 32.45 | 8.113 | 2.157 | -4 | 28.75 | 0.478 | 3 |
| best_raw_calmar | combo__orb15m__entry_2230__flat_0400__rr5p0_tp0p25__stop_atr_4p0__gap_orb_15p0__atr5__dir_ | gate_skip_bear_high_vol | soft_curve | 67 | 32.45 | 8.113 | 2.157 | -4 | 28.75 | 0.478 | 3 |
| best_curve_net | combo__orb15m__entry_2315__flat_0400__rr5p0_tp0p25__stop_atr_4p0__gap_orb_15p0__atr5__dir_ | gate_skip_bear_high_vol | curve | 84 | 42.55 | 5.441 | 2.211 | -7.82 | 40.29 | 0.776 | 6 |

**Selected option seeds**

```json
{
  "atr": [
    "atr5",
    "atr14"
  ],
  "direction": [
    "dir_long",
    "dir_both"
  ],
  "dow": [
    "dow_baseline",
    "dow_none"
  ],
  "entry_end": [
    "entry_2230",
    "entry_2315"
  ],
  "flat_start": [
    "flat_0400",
    "flat_0700"
  ],
  "fvg_selection": [
    "fvg_first",
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_0p9",
    "gap_orb_15p0"
  ],
  "icf": [
    "icf_on",
    "icf_off"
  ],
  "orb_window": [
    "orb15m",
    "orb30m"
  ],
  "reentry": [
    "cap1",
    "cap2_nonpos"
  ],
  "rr_tp1": [
    "rr3p0_tp0p6",
    "rr5p0_tp0p25"
  ],
  "stop": [
    "stop_atr_4p0",
    "stop_orb_125p0"
  ]
}
```

### NQ NY LSI

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 39 | 14.11 | 4.702 | 1.932 | -3 | 14.07 | - | 0 |
| best_curve_calmar | combo__window_0830_1230__rr3p5_tp0p4__gap3p0__atr10__fvgL20_R2__lag24__cap2__htfN5__htf60_ | gate_none | soft_curve | 31 | 15.63 | 15.63 | 3.158 | -1 | 15.46 | 0.528 | 3 |
| best_raw_calmar | combo__window_0830_1230__rr3p5_tp0p4__gap3p0__atr10__fvgL20_R2__lag24__cap2__htfN5__htf60_ | gate_none | soft_curve | 31 | 15.63 | 15.63 | 3.158 | -1 | 15.46 | 0.528 | 3 |
| best_curve_net | combo__window_0830_1230__rr3p5_tp0p4__gap3p0__atr14__fvgL20_R2__lag24__cap2__htfN3__htf60_ | gate_skip_bear_high_vol | curve | 50 | 20.59 | 6.864 | 2.225 | -3 | 19.65 | 0.869 | 7 |

**Selected option seeds**

```json
{
  "atr": [
    "atr14",
    "atr10"
  ],
  "direction": [
    "dir_long",
    "dir_both"
  ],
  "dow": [
    "dow_baseline",
    "dow_exFri"
  ],
  "entry_mode": [
    "mode_fvg_limit",
    "mode_close"
  ],
  "entry_window": [
    "window_0830_1230",
    "window_0830_1430"
  ],
  "fvg_window": [
    "fvgL20_R2",
    "fvgL10_R2"
  ],
  "gap": [
    "gap3p0",
    "gap2p5"
  ],
  "htf_left": [
    "htfN3",
    "htfN5"
  ],
  "htf_tf": [
    "htf60"
  ],
  "max_inv": [
    "lag24",
    "lag0"
  ],
  "rr_tp1": [
    "rr3p5_tp0p4",
    "rr3p0_tp0p4"
  ],
  "trade_cap": [
    "cap2",
    "cap1"
  ]
}
```

### ES NY ORB

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 93 | 18.20 | 1.894 | 1.571 | -9.61 | 16.42 | - | 0 |
| best_curve_calmar | combo__orb15m__entry_1300__flat_1430__rr5p0_tp0p2__stop_atr_5p0__gap_orb_10p0__atr7__dir_b | gate_none | curve | 115 | 30.13 | 8.499 | 1.799 | -3.55 | 27.23 | 0.657 | 3 |
| best_raw_calmar | combo__orb15m__entry_1300__flat_1430__rr5p0_tp0p2__stop_atr_5p0__gap_orb_10p0__atr7__dir_b | gate_none | curve | 115 | 30.13 | 8.499 | 1.799 | -3.55 | 27.23 | 0.657 | 3 |
| best_curve_net | combo__orb10m__entry_1200__flat_1430__rr6p0_tp0p2__stop_atr_5p0__gap_atr_0p25__atr7__dir_b | gate_skip_medium_vol | curve | 172 | 52.47 | 4.14 | 1.725 | -12.67 | 32.27 | 0.929 | 8 |

**Selected option seeds**

```json
{
  "atr": [
    "atr7",
    "atr10"
  ],
  "direction": [
    "dir_long",
    "dir_both"
  ],
  "dow": [
    "dow_baseline",
    "dow_exWed"
  ],
  "entry_end": [
    "entry_1300",
    "entry_1200"
  ],
  "flat_start": [
    "flat_1550",
    "flat_1430"
  ],
  "fvg_selection": [
    "fvg_first",
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_0p25",
    "gap_orb_10p0"
  ],
  "icf": [
    "icf_off",
    "icf_on"
  ],
  "orb_window": [
    "orb15m",
    "orb10m"
  ],
  "reentry": [
    "cap1",
    "cap2_any"
  ],
  "rr_tp1": [
    "rr5p0_tp0p2",
    "rr6p0_tp0p2"
  ],
  "stop": [
    "stop_atr_5p0",
    "stop_atr_3p0"
  ]
}
```

### ES Asia ORB

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 143 | 21.75 | 3.735 | 1.421 | -5.82 | 20.67 | - | 0 |
| best_curve_calmar | combo__orb10m__entry_0600__flat_0700__rr1p5_tp0p7__stop_orb_125p0__gap_atr_0p5__atr20__dir | gate_skip_bear_high_vol | curve | 173 | 46.88 | 12.66 | 1.799 | -3.7 | 40.12 | 0.733 | 5 |
| best_raw_calmar | combo__orb10m__entry_0600__flat_0700__rr1p5_tp0p7__stop_orb_125p0__gap_atr_0p5__atr20__dir | gate_skip_bear_high_vol | curve | 173 | 46.88 | 12.66 | 1.799 | -3.7 | 40.12 | 0.733 | 5 |
| best_curve_net | combo__orb15m__entry_0600__flat_0400__rr1p5_tp0p7__stop_orb_125p0__gap_orb_10p0__atr20__di | gate_skip_bear_high_vol | curve | 205 | 49.44 | 5.432 | 1.764 | -9.1 | 42.51 | 0.958 | 10 |

**Selected option seeds**

```json
{
  "atr": [
    "atr14",
    "atr20"
  ],
  "direction": [
    "dir_long",
    "dir_both"
  ],
  "dow": [
    "dow_baseline",
    "dow_exMon"
  ],
  "entry_end": [
    "entry_0300",
    "entry_0600"
  ],
  "flat_start": [
    "flat_0700",
    "flat_0400"
  ],
  "fvg_selection": [
    "fvg_first",
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_0p5",
    "gap_orb_10p0"
  ],
  "icf": [
    "icf_off",
    "icf_on"
  ],
  "orb_window": [
    "orb15m",
    "orb10m"
  ],
  "reentry": [
    "cap1",
    "cap2_nonpos"
  ],
  "rr_tp1": [
    "rr1p5_tp0p7",
    "rr1p75_tp0p6"
  ],
  "stop": [
    "stop_orb_125p0",
    "stop_atr_15p0"
  ]
}
```

### ES NY LSI

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 49 | -1.04 | -0.14 | 0.971 | -7.45 | 0.72 | - | 0 |
| best_curve_calmar | combo__window_0830_1500__rr4p0_tp0p3__gap3p0__atr20__fvgL20_R3__lag16__cap1__htfN2__htf90_ | gate_skip_high_vol | soft_curve | 22 | 14.60 | 14.60 | 3.277 | -1 | 9.58 | 0.454 | 3 |
| best_raw_calmar | combo__window_0830_1500__rr2p5_tp0p5__gap4p0__atr14__fvgL20_R3__lag16__cap2__htfN2__htf60_ | gate_skip_medium_vol | cliff | 28 | 16.27 | 15.34 | 3.382 | -1.06 | 12.81 | 0.426 | 2 |
| best_curve_net | combo__window_0830_1500__rr4p0_tp0p3__gap3p0__atr14__fvgL20_R3__lag0__cap2__htfN3__htf60__ | gate_skip_bear_high_vol | curve | 82 | 27.38 | 8.651 | 2.002 | -3.17 | 23.65 | 0.617 | 5 |

**Selected option seeds**

```json
{
  "atr": [
    "atr14",
    "atr20"
  ],
  "direction": [
    "dir_long",
    "dir_both"
  ],
  "dow": [
    "dow_baseline",
    "dow_exTue"
  ],
  "entry_mode": [
    "mode_fvg_limit",
    "mode_close"
  ],
  "entry_window": [
    "window_0830_1400",
    "window_0830_1500"
  ],
  "fvg_window": [
    "fvgL20_R3",
    "fvgL33_R3"
  ],
  "gap": [
    "gap3p0",
    "gap4p0"
  ],
  "htf_left": [
    "htfN3",
    "htfN2"
  ],
  "htf_tf": [
    "htf90",
    "htf60"
  ],
  "max_inv": [
    "lag0",
    "lag16"
  ],
  "rr_tp1": [
    "rr2p5_tp0p5",
    "rr4p0_tp0p3"
  ],
  "trade_cap": [
    "cap2",
    "cap1"
  ]
}
```

### GC NY ORB

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 53 | 20.09 | 1.768 | 1.583 | -11.36 | 28.77 | - | 0 |
| best_curve_calmar | combo__orb15m__entry_1100__flat_1530__rr10p0_tp0p2__stop_orb_50p0__gap_atr_3p0__atr7__dir_ | gate_none | soft_curve | 30 | 25.73 | 12.86 | 2.749 | -2 | 24.15 | 0.475 | 3 |
| best_raw_calmar | combo__orb15m__entry_1100__flat_1530__rr10p0_tp0p2__stop_orb_50p0__gap_atr_3p0__atr7__dir_ | gate_none | cliff | 30 | 25.73 | 12.86 | 2.749 | -2 | 24.15 | 0.42 | 2 |
| best_curve_net | combo__orb15m__entry_1200__flat_1530__rr9p0_tp0p35__stop_atr_4p5__gap_atr_3p0__atr7__dir_l | gate_none | curve | 47 | 41.98 | 5.556 | 2.547 | -7.56 | 43.69 | 0.794 | 6 |

**Selected option seeds**

```json
{
  "atr": [
    "atr7",
    "atr10"
  ],
  "direction": [
    "dir_long",
    "dir_both"
  ],
  "dow": [
    "dow_baseline",
    "dow_exThu"
  ],
  "entry_end": [
    "entry_1200",
    "entry_1100"
  ],
  "flat_start": [
    "flat_1330",
    "flat_1530"
  ],
  "fvg_selection": [
    "fvg_first",
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_3p0",
    "gap_orb_5p0"
  ],
  "icf": [
    "icf_on",
    "icf_off"
  ],
  "orb_window": [
    "orb8m",
    "orb15m"
  ],
  "reentry": [
    "cap1",
    "cap2_any"
  ],
  "rr_tp1": [
    "rr9p0_tp0p35",
    "rr10p0_tp0p2"
  ],
  "stop": [
    "stop_atr_4p5",
    "stop_orb_50p0"
  ]
}
```

### GC Asia ORB

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 128 | 16.71 | 1.445 | 1.237 | -11.57 | 17.94 | - | 0 |
| best_curve_calmar | combo__orb10m__entry_2315__flat_0400__rr2p5_tp0p6__stop_atr_5p0__gap_atr_1p0__atr7__dir_sh | gate_skip_bear_high_vol | soft_curve | 45 | 22.99 | 11.50 | 2.339 | -2 | 19.03 | 0.57 | 4 |
| best_raw_calmar | combo__orb10m__entry_2315__flat_0400__rr2p5_tp0p6__stop_atr_5p0__gap_atr_1p0__atr7__dir_sh | gate_skip_bear_high_vol | soft_curve | 45 | 22.99 | 11.50 | 2.339 | -2 | 19.03 | 0.57 | 4 |
| best_curve_net | combo__orb10m__entry_2315__flat_0600__rr2p5_tp0p6__stop_orb_25p0__gap_orb_15p0__atr7__dir_ | gate_skip_medium_vol | curve | 105 | 39.35 | 6.246 | 1.857 | -6.3 | 38.68 | 0.851 | 7 |

**Selected option seeds**

```json
{
  "atr": [
    "atr14",
    "atr7"
  ],
  "direction": [
    "dir_both",
    "dir_short"
  ],
  "dow": [
    "dow_baseline",
    "dow_exThu"
  ],
  "entry_end": [
    "entry_2315",
    "entry_0600"
  ],
  "flat_start": [
    "flat_0400",
    "flat_0600"
  ],
  "fvg_selection": [
    "fvg_first",
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_1p0",
    "gap_orb_15p0"
  ],
  "icf": [
    "icf_off",
    "icf_on"
  ],
  "orb_window": [
    "orb30m",
    "orb10m"
  ],
  "reentry": [
    "cap1",
    "uncapped_any"
  ],
  "rr_tp1": [
    "rr2p5_tp0p6",
    "rr2p0_tp0p5"
  ],
  "stop": [
    "stop_orb_25p0",
    "stop_atr_5p0"
  ]
}
```

### GC NY LSI

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 3 | -1.99 | -0.993 | 0.007 | -2 | -1.99 | - | 0 |
| best_curve_calmar | combo__entry_1530__flat_1550__rr3p0_tp0p4__gap5p0__atr7__nL5__nR75__fvgL10_R5__dir_both__m | gate_skip_high_vol | soft_curve | 9 | 2.91 | 23.97 | 16.36 | -0.12 | 2.91 | 0.568 | 5 |
| best_raw_calmar | combo__entry_1530__flat_1550__rr3p0_tp0p4__gap5p0__atr7__nL5__nR75__fvgL10_R5__dir_both__m | gate_skip_high_vol | cliff | 10 | 4.04 | 33.22 | 23.64 | -0.12 | 4.04 | 0.41 | 4 |
| best_curve_net | combo__entry_1530__flat_1550__rr3p0_tp0p4__gap5p0__atr7__nL5__nR75__fvgL10_R5__dir_both__m | gate_skip_high_vol | soft_curve | 9 | 2.91 | 23.97 | 16.36 | -0.12 | 2.91 | 0.568 | 5 |

**Selected option seeds**

```json
{
  "atr": [
    "atr7",
    "atr5"
  ],
  "direction": [
    "dir_both",
    "dir_short"
  ],
  "dow": [
    "dow_baseline",
    "dow_exMon"
  ],
  "entry_end": [
    "entry_1030",
    "entry_1530"
  ],
  "entry_mode": [
    "mode_fvg_limit",
    "mode_close"
  ],
  "flat_start": [
    "flat_1500",
    "flat_1550"
  ],
  "fvg_window": [
    "fvgL10_R10",
    "fvgL10_R5"
  ],
  "gap": [
    "gap5p0",
    "gap2p0"
  ],
  "n_left": [
    "nL5",
    "nL8"
  ],
  "n_right": [
    "nR75",
    "nR45"
  ],
  "rr_tp1": [
    "rr9p0_tp0p4",
    "rr3p0_tp0p4"
  ]
}
```

### GC Asia LSI

| pick | variant | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau | n_ge80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | gate_none | n/a | 14 | -1.45 | -0.27 | 0.831 | -5.37 | -1.27 | - | 0 |
| best_curve_calmar | combo__entry_2315__flat_0400__rr9p0_tp0p4__gap4p0__atr7__nL3__nR48__fvgL10_R10__dir_both__ | gate_skip_medium_vol | curve | 14 | 19.13 | 19.13 | 9.774 | -1 | 19.32 | 0.687 | 3 |
| best_raw_calmar | combo__entry_2315__flat_0400__rr9p0_tp0p4__gap4p0__atr7__nL3__nR48__fvgL10_R10__dir_both__ | gate_skip_medium_vol | curve | 14 | 19.13 | 19.13 | 9.774 | -1 | 19.32 | 0.687 | 3 |
| best_curve_net | combo__entry_2315__flat_0400__rr9p0_tp0p4__gap4p0__atr7__nL3__nR48__fvgL10_R10__dir_both__ | gate_skip_medium_vol | curve | 14 | 19.13 | 19.13 | 9.774 | -1 | 19.32 | 0.687 | 3 |

**Selected option seeds**

```json
{
  "atr": [
    "atr7",
    "atr5"
  ],
  "direction": [
    "dir_both",
    "dir_short"
  ],
  "dow": [
    "dow_baseline",
    "dow_exWed"
  ],
  "entry_end": [
    "entry_2315",
    "entry_0000"
  ],
  "entry_mode": [
    "mode_fvg_limit",
    "mode_close"
  ],
  "flat_start": [
    "flat_0400",
    "flat_0000"
  ],
  "fvg_window": [
    "fvgL10_R10",
    "fvgL20_R3"
  ],
  "gap": [
    "gap5p0",
    "gap4p0"
  ],
  "n_left": [
    "nL5",
    "nL3"
  ],
  "n_right": [
    "nR36",
    "nR48"
  ],
  "rr_tp1": [
    "rr9p0_tp0p4",
    "rr3p0_tp0p4"
  ]
}
```

## Cross-Leg Summary

| leg | pick | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_ny_orb | combo__orb20m__entry_1300__flat_1430__rr4p0_tp0p3__stop_atr_9p0__gap_orb | gate_skip_high_vol | curve | 33 | 16.07 | 8.034 | 2.802 | -2 | 9.98 | 0.673 |
| nq_asia_orb | combo__orb15m__entry_2230__flat_0400__rr5p0_tp0p25__stop_atr_4p0__gap_or | gate_skip_bear_high_vol | soft_curve | 67 | 32.45 | 8.113 | 2.157 | -4 | 28.75 | 0.478 |
| nq_ny_lsi | combo__window_0830_1230__rr3p5_tp0p4__gap3p0__atr10__fvgL20_R2__lag24__c | gate_none | soft_curve | 31 | 15.63 | 15.63 | 3.158 | -1 | 15.46 | 0.528 |
| es_ny_orb | combo__orb15m__entry_1300__flat_1430__rr5p0_tp0p2__stop_atr_5p0__gap_orb | gate_none | curve | 115 | 30.13 | 8.499 | 1.799 | -3.55 | 27.23 | 0.657 |
| es_asia_orb | combo__orb10m__entry_0600__flat_0700__rr1p5_tp0p7__stop_orb_125p0__gap_a | gate_skip_bear_high_vol | curve | 173 | 46.88 | 12.66 | 1.799 | -3.7 | 40.12 | 0.733 |
| es_ny_lsi | combo__window_0830_1500__rr4p0_tp0p3__gap3p0__atr20__fvgL20_R3__lag16__c | gate_skip_high_vol | soft_curve | 22 | 14.60 | 14.60 | 3.277 | -1 | 9.58 | 0.454 |
| gc_ny_orb | combo__orb15m__entry_1100__flat_1530__rr10p0_tp0p2__stop_orb_50p0__gap_a | gate_none | soft_curve | 30 | 25.73 | 12.86 | 2.749 | -2 | 24.15 | 0.475 |
| gc_asia_orb | combo__orb10m__entry_2315__flat_0400__rr2p5_tp0p6__stop_atr_5p0__gap_atr | gate_skip_bear_high_vol | soft_curve | 45 | 22.99 | 11.50 | 2.339 | -2 | 19.03 | 0.57 |
| gc_ny_lsi | combo__entry_1530__flat_1550__rr3p0_tp0p4__gap5p0__atr7__nL5__nR75__fvgL | gate_skip_high_vol | soft_curve | 9 | 2.91 | 23.97 | 16.36 | -0.12 | 2.91 | 0.568 |
| gc_asia_lsi | combo__entry_2315__flat_0400__rr9p0_tp0p4__gap4p0__atr7__nL3__nR48__fvgL | gate_skip_medium_vol | curve | 14 | 19.13 | 19.13 | 9.774 | -1 | 19.32 | 0.687 |

## Read

- Treat these as TESTING-only hot-regime candidates. They are optimized directly on the last year.
- `curve` means the best row had nearby one-step neighbors retaining enough Calmar to look like a surface; `soft_curve` is usable but thinner.
- `cliff` rows can still be interesting diagnostics, but they should not be treated as optimized params without another local sweep.
- For comparison, the recent Hunter ORB branches remain the benchmark because they reached roughly triple-digit R in the hot window; the table above shows which candidates even enter that neighborhood.
