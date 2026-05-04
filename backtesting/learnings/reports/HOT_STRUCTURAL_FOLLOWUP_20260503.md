# Hot Structural Follow-Up

- Run slug: `hot_structural_followup_20260503`
- Last-1y window: `2025-03-24` to `2026-03-24`
- Last-2y/context window: `2024-03-24` to `2026-03-24`
- Scope: targeted second pass on the positive structural leads from `HOT_STRUCTURAL_SEQUENCE_20260503`.
- Legs: `NQ NY ORB`, `ES NY ORB`, `GC NY ORB`, `GC Asia ORB`.
- Tested refined news/event exclusions, day-of-month cuts, ORB-size thresholds, prior-day filters, Asia/NY context, and signal-shape thresholds.
- Still TESTING-only and optimized directly on the hot one-year window.

## Best Net Additions

| leg | pick | stage | surface | fills | net_r | delta_r | calmar | pf | dd | base_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ NY ORB | exclude_cpi | oat | n/a | 76 | 64.95 | 1 | 12.99 | 2.327 | -5 | 63.95 |
| ES NY ORB | exclude_fomc_cpi | oat | n/a | 174 | 125.97 | 10 | 10.497 | 2.017 | -12 | 115.97 |
| GC NY ORB | combo__cpi_nfp_plus_outside__exclude_fomc_nfp | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 56.99 |
| GC Asia ORB | cpi_nfp_plus_not_inside | oat | n/a | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 62.44 |

## Best Score / DD Tilt

| leg | pick | stage | surface | fills | net_r | delta_r | calmar | pf | dd | base_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ NY ORB | combo__cpi_nfp_plus_wick35__exclude_all_news__orb_pctile_le_75 | combo | soft_curve | 35 | 56.42 | -7.53 | 18.805 | 4.073 | -3 | 63.95 |
| ES NY ORB | exclude_fomc_cpi | oat | n/a | 174 | 125.97 | 10 | 10.497 | 2.017 | -12 | 115.97 |
| GC NY ORB | combo__signal_outside_orb__adverse_wick_le_50__exclude_dom_1_3 | combo | curve | 30 | 58.19 | 1.2 | 14.547 | 4.083 | -4 | 56.99 |
| GC Asia ORB | cpi_nfp_plus_not_inside | oat | n/a | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 62.44 |

## NQ NY ORB

Baseline after existing `gate_none` gate: 77 fills, `63.95R`, Calmar `12.79`, PF `2.281`, DD `-5.0R`.

### Top OAT

| gate_id | family | surface | last1_fills | last1_net_r | delta_last1_net_r | last1_calmar | last1_pf | last1_dd_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exclude_cpi | calendar_news | n/a | 76 | 64.95 | 1 | 12.99 | 2.327 | -5 | 59.7 | - | exclude_cpi |
| exclude_cpi_nfp | calendar_news | n/a | 76 | 64.95 | 1 | 12.99 | 2.327 | -5 | 59.7 | - | exclude_cpi_nfp |
| exclude_nfp | calendar_news | n/a | 77 | 63.95 | 0 | 12.79 | 2.281 | -5 | 56.7 | - | exclude_nfp |
| exclude_cpi_nfp_ppi | calendar_news | n/a | 74 | 63.74 | -0.21 | 12.747 | 2.331 | -5 | 61.08 | - | exclude_cpi_nfp_ppi |
| exclude_fomc_cpi | calendar_news | n/a | 74 | 63.73 | -0.22 | 12.747 | 2.327 | -5 | 57.08 | - | exclude_fomc_cpi |
| exclude_ppi | calendar_news | n/a | 75 | 62.74 | -1.21 | 12.547 | 2.283 | -5 | 58.08 | - | exclude_ppi |
| exclude_fomc | calendar_news | n/a | 75 | 62.73 | -1.22 | 12.547 | 2.279 | -5 | 54.08 | - | exclude_fomc |
| exclude_fomc_nfp | calendar_news | n/a | 75 | 62.73 | -1.22 | 12.547 | 2.279 | -5 | 54.08 | - | exclude_fomc_nfp |
| exclude_all_news | calendar_news | n/a | 72 | 62.52 | -1.43 | 12.504 | 2.331 | -5 | 58.47 | - | exclude_all_news |
| signal_outside_orb | signal_shape | n/a | 74 | 60.49 | -3.45 | 7.562 | 2.263 | -8 | 51.81 | - | signal_outside_orb |
| orb_pctile_le_75 | orb_size | n/a | 59 | 59.44 | -4.51 | 8.491 | 2.642 | -7 | 60.32 | - | orb_pctile_le_75 |
| orb_pctile_le_80 | orb_size | n/a | 59 | 59.44 | -4.51 | 8.491 | 2.642 | -7 | 59.32 | - | orb_pctile_le_80 |

### Top Combos

| gate_id | family | surface | last1_fills | last1_net_r | delta_last1_net_r | last1_calmar | last1_pf | last1_dd_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__adverse_wick_le_50__exclude_fomc_cpi | combo | cliff | 56 | 61.1 | -2.85 | 15.276 | 2.785 | -4 | 58.2 | 0 | adverse_wick_le_50\|exclude_fomc_cpi |
| combo__exclude_cpi__orb_pctile_le_75 | combo | cliff | 58 | 60.44 | -3.51 | 8.634 | 2.717 | -7 | 63.32 | 0 | exclude_cpi\|orb_pctile_le_75 |
| combo__exclude_cpi_nfp__orb_pctile_le_75 | combo | cliff | 58 | 60.44 | -3.51 | 8.634 | 2.717 | -7 | 63.32 | 0 | exclude_cpi_nfp\|orb_pctile_le_75 |
| combo__exclude_cpi__adverse_wick_le_50 | combo | cliff | 57 | 60.1 | -3.85 | 15.026 | 2.711 | -4 | 59.6 | 0 | exclude_cpi\|adverse_wick_le_50 |
| combo__exclude_cpi_nfp__adverse_wick_le_50 | combo | cliff | 57 | 60.1 | -3.85 | 15.026 | 2.711 | -4 | 59.6 | 0 | exclude_cpi_nfp\|adverse_wick_le_50 |
| combo__adverse_wick_le_50__exclude_fomc | combo | cliff | 57 | 60.1 | -3.85 | 15.026 | 2.705 | -4 | 55.2 | 0 | adverse_wick_le_50\|exclude_fomc |
| combo__adverse_wick_le_50__exclude_fomc_nfp | combo | cliff | 57 | 60.1 | -3.85 | 15.026 | 2.705 | -4 | 55.2 | 0 | adverse_wick_le_50\|exclude_fomc_nfp |
| combo__adverse_wick_le_50__exclude_all_news | combo | cliff | 54 | 59.89 | -4.06 | 14.972 | 2.805 | -4 | 58.58 | 0 | adverse_wick_le_50\|exclude_all_news |
| combo__exclude_nfp__orb_pctile_le_75 | combo | cliff | 59 | 59.44 | -4.51 | 8.491 | 2.642 | -7 | 60.32 | 0 | exclude_nfp\|orb_pctile_le_75 |
| combo__exclude_cpi_nfp_ppi__orb_pctile_le_75 | combo | cliff | 56 | 59.22 | -4.73 | 9.87 | 2.734 | -6 | 67.1 | 0 | exclude_cpi_nfp_ppi\|orb_pctile_le_75 |
| combo__exclude_fomc_cpi__orb_pctile_le_75 | combo | cliff | 56 | 59.22 | -4.73 | 8.46 | 2.727 | -7 | 58.7 | 0 | exclude_fomc_cpi\|orb_pctile_le_75 |
| combo__adverse_wick_le_50__exclude_nfp | combo | cliff | 58 | 59.1 | -4.85 | 14.776 | 2.636 | -4 | 56.6 | 0 | adverse_wick_le_50\|exclude_nfp |

<details><summary>Selected combo gates</summary>

```json
{
  "base_gate": "gate_none",
  "base_variant": "prev_curve_net__combo__rr6p0_tp0p8__stop_atr_3p0__cap2_any__gap_orb_5p0__entry_end_1130__orb8m__fvg_extreme",
  "combo_gate_ids": [
    "exclude_cpi",
    "exclude_cpi_nfp",
    "cpi_nfp_plus_wick35",
    "adverse_wick_le_35",
    "exclude_cpi_nfp_ppi",
    "adverse_wick_le_50",
    "exclude_nfp",
    "exclude_fomc_cpi",
    "exclude_ppi",
    "exclude_all_news",
    "exclude_fomc",
    "exclude_fomc_nfp",
    "body_ge_50",
    "dist_orb_ge_25",
    "orb_pctile_le_67",
    "orb_pctile_le_75"
  ]
}
```

</details>

## ES NY ORB

Baseline after existing `gate_skip_medium_vol` gate: 184 fills, `115.97R`, Calmar `8.283`, PF `1.865`, DD `-14.0R`.

### Top OAT

| gate_id | family | surface | last1_fills | last1_net_r | delta_last1_net_r | last1_calmar | last1_pf | last1_dd_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exclude_fomc_cpi | calendar_news | n/a | 174 | 125.97 | 10 | 10.497 | 2.017 | -12 | 135.21 | - | exclude_fomc_cpi |
| exclude_cpi | calendar_news | n/a | 179 | 120.97 | 5 | 10.081 | 1.938 | -12 | 125.21 | - | exclude_cpi |
| exclude_fomc | calendar_news | n/a | 179 | 120.97 | 5 | 8.641 | 1.938 | -14 | 142.11 | - | exclude_fomc |
| exclude_fomc_nfp | calendar_news | n/a | 174 | 116.76 | 0.79 | 7.112 | 1.927 | -16.42 | 132.28 | - | exclude_fomc_nfp |
| exclude_cpi_nfp | calendar_news | n/a | 174 | 116.76 | 0.79 | 7.112 | 1.927 | -16.42 | 115.38 | - | exclude_cpi_nfp |
| fomc_plus_outside | seed_combo | n/a | 171 | 116.59 | 0.62 | 8.968 | 1.94 | -13 | 140.73 | - | fomc_plus_outside |
| exclude_all_news | calendar_news | n/a | 161 | 114.13 | -1.84 | 7.916 | 1.986 | -14.42 | 126.03 | - | exclude_all_news |
| signal_outside_orb | signal_shape | n/a | 175 | 112.59 | -3.38 | 8.523 | 1.879 | -13.21 | 130.73 | - | signal_outside_orb |
| exclude_nfp | calendar_news | n/a | 179 | 111.76 | -4.21 | 6.808 | 1.853 | -16.42 | 121.28 | - | exclude_nfp |
| dist_orb_0_100 | signal_shape | n/a | 144 | 111.12 | -4.85 | 7.408 | 2.091 | -15 | 111.63 | - | dist_orb_0_100 |
| exclude_ppi | calendar_news | n/a | 174 | 110.33 | -5.64 | 9.194 | 1.87 | -12 | 133.76 | - | exclude_ppi |
| prior_not_inside_day | prior_day | n/a | 168 | 109.98 | -5.99 | 9.165 | 1.903 | -12 | 120.29 | - | prior_not_inside_day |

### Top Combos

| gate_id | family | surface | last1_fills | last1_net_r | delta_last1_net_r | last1_calmar | last1_pf | last1_dd_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__exclude_fomc_cpi__fomc_plus_outside | combo | cliff | 166 | 121.59 | 5.62 | 9.958 | 2.023 | -12.21 | 133.83 | 0 | exclude_fomc_cpi\|fomc_plus_outside |
| combo__exclude_fomc_cpi__signal_outside_orb | combo | cliff | 166 | 121.59 | 5.62 | 9.958 | 2.023 | -12.21 | 133.83 | 0 | exclude_fomc_cpi\|signal_outside_orb |
| combo__exclude_cpi__fomc_plus_outside | combo | cliff | 166 | 121.59 | 5.62 | 9.958 | 2.023 | -12.21 | 133.83 | 0 | exclude_cpi\|fomc_plus_outside |
| combo__exclude_fomc_cpi__fomc_plus_outside__signal_outside_orb | combo | curve | 166 | 121.59 | 5.62 | 9.958 | 2.023 | -12.21 | 133.83 | 1 | exclude_fomc_cpi\|fomc_plus_outside\|signal_outside_orb |
| combo__exclude_cpi__fomc_plus_outside__signal_outside_orb | combo | curve | 166 | 121.59 | 5.62 | 9.958 | 2.023 | -12.21 | 133.83 | 0.901 | exclude_cpi\|fomc_plus_outside\|signal_outside_orb |
| combo__exclude_fomc_cpi__dist_orb_0_100 | combo | cliff | 135 | 120.12 | 4.15 | 10.01 | 2.296 | -12 | 111.73 | 0 | exclude_fomc_cpi\|dist_orb_0_100 |
| combo__exclude_fomc_cpi__fomc_plus_outside__dist_orb_0_100 | combo | curve | 135 | 120.12 | 4.15 | 10.01 | 2.296 | -12 | 111.73 | 0.995 | exclude_fomc_cpi\|fomc_plus_outside\|dist_orb_0_100 |
| combo__exclude_cpi__fomc_plus_outside__dist_orb_0_100 | combo | curve | 135 | 120.12 | 4.15 | 10.01 | 2.296 | -12 | 111.73 | 0.892 | exclude_cpi\|fomc_plus_outside\|dist_orb_0_100 |
| combo__exclude_fomc_cpi__prior_not_inside_day | combo | cliff | 159 | 118.98 | 3.01 | 10.816 | 2.056 | -11 | 123.39 | 0 | exclude_fomc_cpi\|prior_not_inside_day |
| combo__exclude_cpi__signal_outside_orb | combo | cliff | 170 | 117.59 | 1.62 | 8.901 | 1.956 | -13.21 | 124.83 | 0 | exclude_cpi\|signal_outside_orb |
| combo__fomc_plus_outside__exclude_cpi_nfp | combo | cliff | 161 | 117.38 | 1.41 | 7.06 | 2.013 | -16.63 | 124 | 0 | fomc_plus_outside\|exclude_cpi_nfp |
| combo__fomc_plus_outside__exclude_cpi_nfp__signal_outside_orb | combo | curve | 161 | 117.38 | 1.41 | 7.06 | 2.013 | -16.63 | 124 | 1 | fomc_plus_outside\|exclude_cpi_nfp\|signal_outside_orb |

<details><summary>Selected combo gates</summary>

```json
{
  "base_gate": "gate_skip_medium_vol",
  "base_variant": "prev_curve_net__combo__rr7p0_tp0p8__dow_none__gap_atr_1p0__wide_t12p5_rr3__icf_on__pre_cancel_tp1__flat_1330",
  "combo_gate_ids": [
    "exclude_fomc_cpi",
    "exclude_fomc",
    "exclude_cpi",
    "fomc_plus_outside",
    "exclude_fomc_nfp",
    "exclude_cpi_nfp",
    "exclude_ppi",
    "signal_outside_orb",
    "exclude_all_news",
    "prior_not_inside_day",
    "exclude_nfp",
    "dist_orb_0_100",
    "exclude_cpi_nfp_ppi",
    "exclude_dom_1_3",
    "orb_pctile_ge_33",
    "dist_orb_0_50"
  ]
}
```

</details>

## GC NY ORB

Baseline after existing `gate_skip_sideways_medium_vol` gate: 43 fills, `56.99R`, Calmar `11.398`, PF `2.884`, DD `-5.0R`.

### Top OAT

| gate_id | family | surface | last1_fills | last1_net_r | delta_last1_net_r | last1_calmar | last1_pf | last1_dd_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cpi_nfp_plus_outside | seed_combo | n/a | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 57.57 | - | cpi_nfp_plus_outside |
| exclude_cpi_nfp | calendar_news | n/a | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 55.57 | - | exclude_cpi_nfp |
| exclude_fomc_nfp | calendar_news | n/a | 39 | 60.99 | 4 | 12.198 | 3.309 | -5 | 66.55 | - | exclude_fomc_nfp |
| exclude_nfp | calendar_news | n/a | 39 | 60.99 | 4 | 12.198 | 3.309 | -5 | 64.55 | - | exclude_nfp |
| exclude_fomc_cpi | calendar_news | n/a | 40 | 59.99 | 3 | 14.031 | 3.184 | -4.28 | 53.57 | - | exclude_fomc_cpi |
| exclude_cpi | calendar_news | n/a | 40 | 59.99 | 3 | 14.031 | 3.184 | -4.28 | 51.57 | - | exclude_cpi |
| signal_outside_orb | signal_shape | n/a | 42 | 57.99 | 1 | 11.598 | 2.982 | -5 | 63.55 | - | signal_outside_orb |
| exclude_fomc | calendar_news | n/a | 43 | 56.99 | 0 | 11.398 | 2.884 | -5 | 62.55 | - | exclude_fomc |
| exclude_all_news | calendar_news | n/a | 35 | 55.25 | -1.74 | 11.051 | 3.345 | -5 | 50.88 | - | exclude_all_news |
| exclude_cpi_nfp_ppi | calendar_news | n/a | 35 | 55.25 | -1.74 | 11.051 | 3.345 | -5 | 48.88 | - | exclude_cpi_nfp_ppi |
| orb_pctile_le_80 | orb_size | n/a | 33 | 55.19 | -1.8 | 12.909 | 3.511 | -4.28 | 61.87 | - | orb_pctile_le_80 |
| adverse_wick_le_50 | signal_shape | n/a | 33 | 55.19 | -1.8 | 11.038 | 3.53 | -5 | 73.79 | - | adverse_wick_le_50 |

### Top Combos

| gate_id | family | surface | last1_fills | last1_net_r | delta_last1_net_r | last1_calmar | last1_pf | last1_dd_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__cpi_nfp_plus_outside__exclude_fomc_nfp | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 59.57 | 0 | cpi_nfp_plus_outside\|exclude_fomc_nfp |
| combo__cpi_nfp_plus_outside__exclude_fomc_cpi | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 59.57 | 0 | cpi_nfp_plus_outside\|exclude_fomc_cpi |
| combo__cpi_nfp_plus_outside__exclude_fomc | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 59.57 | 0 | cpi_nfp_plus_outside\|exclude_fomc |
| combo__cpi_nfp_plus_outside__exclude_fomc_nfp__signal_outside_orb | combo | curve | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 59.57 | 1 | cpi_nfp_plus_outside\|exclude_fomc_nfp\|signal_outside_orb |
| combo__cpi_nfp_plus_outside__exclude_fomc_cpi__signal_outside_orb | combo | curve | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 59.57 | 1 | cpi_nfp_plus_outside\|exclude_fomc_cpi\|signal_outside_orb |
| combo__cpi_nfp_plus_outside__signal_outside_orb__exclude_fomc | combo | curve | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 59.57 | 1 | cpi_nfp_plus_outside\|signal_outside_orb\|exclude_fomc |
| combo__cpi_nfp_plus_outside__exclude_cpi_nfp | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 57.57 | 0 | cpi_nfp_plus_outside\|exclude_cpi_nfp |
| combo__cpi_nfp_plus_outside__exclude_nfp | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 57.57 | 0 | cpi_nfp_plus_outside\|exclude_nfp |
| combo__cpi_nfp_plus_outside__exclude_cpi | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 57.57 | 0 | cpi_nfp_plus_outside\|exclude_cpi |
| combo__cpi_nfp_plus_outside__signal_outside_orb | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 57.57 | 0 | cpi_nfp_plus_outside\|signal_outside_orb |
| combo__exclude_cpi_nfp__signal_outside_orb | combo | cliff | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 57.57 | 0 | exclude_cpi_nfp\|signal_outside_orb |
| combo__cpi_nfp_plus_outside__exclude_cpi_nfp__signal_outside_orb | combo | curve | 36 | 63.99 | 7 | 14.967 | 3.71 | -4.28 | 57.57 | 1 | cpi_nfp_plus_outside\|exclude_cpi_nfp\|signal_outside_orb |

<details><summary>Selected combo gates</summary>

```json
{
  "base_gate": "gate_skip_sideways_medium_vol",
  "base_variant": "prev_curve_net__combo__rr12p0_tp0p8__atr5__entry_end_1130__gap_orb_20p0__stop_atr_3p0__flat_1550__dow_none",
  "combo_gate_ids": [
    "cpi_nfp_plus_outside",
    "exclude_cpi_nfp",
    "exclude_fomc_nfp",
    "exclude_nfp",
    "exclude_fomc_cpi",
    "exclude_cpi",
    "signal_outside_orb",
    "adverse_wick_le_50",
    "orb_pctile_le_80",
    "exclude_fomc",
    "exclude_dom_25_31",
    "orb_pctile_le_75",
    "exclude_all_news",
    "exclude_cpi_nfp_ppi",
    "prior_range_le_67",
    "exclude_dom_1_3"
  ]
}
```

</details>

## GC Asia ORB

Baseline after existing `gate_skip_medium_vol` gate: 101 fills, `62.44R`, Calmar `12.487`, PF `2.253`, DD `-5.0R`.

### Top OAT

| gate_id | family | surface | last1_fills | last1_net_r | delta_last1_net_r | last1_calmar | last1_pf | last1_dd_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cpi_nfp_plus_not_inside | seed_combo | n/a | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | - | cpi_nfp_plus_not_inside |
| exclude_cpi_nfp | calendar_news | n/a | 99 | 64.44 | 2 | 12.887 | 2.34 | -5 | 49.1 | - | exclude_cpi_nfp |
| prior_not_inside_day | prior_day | n/a | 96 | 63.74 | 1.3 | 12.747 | 2.385 | -5 | 47.7 | - | prior_not_inside_day |
| exclude_cpi | calendar_news | n/a | 100 | 63.44 | 1 | 12.687 | 2.299 | -5 | 48.1 | - | exclude_cpi |
| exclude_nfp | calendar_news | n/a | 100 | 63.44 | 1 | 12.687 | 2.292 | -5 | 45.3 | - | exclude_nfp |
| exclude_cpi_nfp_ppi | calendar_news | n/a | 97 | 62.71 | 0.27 | 12.542 | 2.334 | -5 | 48.18 | - | exclude_cpi_nfp_ppi |
| signal_outside_orb | signal_shape | n/a | 101 | 62.44 | 0 | 12.487 | 2.253 | -5 | 45.3 | - | signal_outside_orb |
| exclude_ppi | calendar_news | n/a | 99 | 60.71 | -1.73 | 12.142 | 2.245 | -5 | 43.38 | - | exclude_ppi |
| exclude_dom_1_3 | calendar_news | n/a | 92 | 60.32 | -2.12 | 12.064 | 2.358 | -5 | 44.49 | - | exclude_dom_1_3 |
| orb_pctile_ge_33 | orb_size | n/a | 90 | 58.64 | -3.8 | 11.727 | 2.376 | -5 | 51.3 | - | orb_pctile_ge_33 |
| exclude_fomc_cpi | calendar_news | n/a | 95 | 57.34 | -5.1 | 9.556 | 2.224 | -6 | 41.3 | - | exclude_fomc_cpi |
| exclude_fomc_nfp | calendar_news | n/a | 95 | 57.34 | -5.1 | 9.556 | 2.216 | -6 | 39.5 | - | exclude_fomc_nfp |

### Top Combos

| gate_id | family | surface | last1_fills | last1_net_r | delta_last1_net_r | last1_calmar | last1_pf | last1_dd_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__cpi_nfp_plus_not_inside__exclude_cpi_nfp | combo | cliff | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 0 | cpi_nfp_plus_not_inside\|exclude_cpi_nfp |
| combo__cpi_nfp_plus_not_inside__prior_not_inside_day | combo | cliff | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 0 | cpi_nfp_plus_not_inside\|prior_not_inside_day |
| combo__cpi_nfp_plus_not_inside__exclude_cpi | combo | cliff | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 0 | cpi_nfp_plus_not_inside\|exclude_cpi |
| combo__cpi_nfp_plus_not_inside__exclude_nfp | combo | cliff | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 0 | cpi_nfp_plus_not_inside\|exclude_nfp |
| combo__cpi_nfp_plus_not_inside__signal_outside_orb | combo | cliff | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 0 | cpi_nfp_plus_not_inside\|signal_outside_orb |
| combo__exclude_cpi_nfp__prior_not_inside_day | combo | cliff | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 0 | exclude_cpi_nfp\|prior_not_inside_day |
| combo__cpi_nfp_plus_not_inside__exclude_cpi_nfp__prior_not_inside_day | combo | curve | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 1 | cpi_nfp_plus_not_inside\|exclude_cpi_nfp\|prior_not_inside_day |
| combo__cpi_nfp_plus_not_inside__exclude_cpi_nfp__signal_outside_orb | combo | curve | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 1 | cpi_nfp_plus_not_inside\|exclude_cpi_nfp\|signal_outside_orb |
| combo__cpi_nfp_plus_not_inside__prior_not_inside_day__exclude_cpi | combo | curve | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 1 | cpi_nfp_plus_not_inside\|prior_not_inside_day\|exclude_cpi |
| combo__cpi_nfp_plus_not_inside__prior_not_inside_day__exclude_nfp | combo | curve | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 1 | cpi_nfp_plus_not_inside\|prior_not_inside_day\|exclude_nfp |
| combo__cpi_nfp_plus_not_inside__prior_not_inside_day__signal_outside_orb | combo | curve | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 1 | cpi_nfp_plus_not_inside\|prior_not_inside_day\|signal_outside_orb |
| combo__cpi_nfp_plus_not_inside__exclude_cpi__signal_outside_orb | combo | curve | 94 | 65.74 | 3.3 | 13.147 | 2.485 | -5 | 52.5 | 1 | cpi_nfp_plus_not_inside\|exclude_cpi\|signal_outside_orb |

<details><summary>Selected combo gates</summary>

```json
{
  "base_gate": "gate_skip_medium_vol",
  "base_variant": "prev_curve_net__combo__rr3p0_tp0p8__pre_cancel_tp2__stop_atr_3p0__gap_atr_1p0__orb10m__wide_t15_rr1__entry_end_2300",
  "combo_gate_ids": [
    "cpi_nfp_plus_not_inside",
    "exclude_cpi_nfp",
    "prior_not_inside_day",
    "exclude_cpi",
    "exclude_nfp",
    "exclude_cpi_nfp_ppi",
    "signal_outside_orb",
    "exclude_dom_1_3",
    "exclude_ppi",
    "orb_pctile_ge_33",
    "adverse_wick_le_50",
    "body_ge_40",
    "exclude_fomc_cpi",
    "exclude_fomc_nfp",
    "exclude_all_news",
    "exclude_fomc"
  ]
}
```

</details>
