# Hot One-Year Squeeze

- Run slug: `hot_one_year_squeeze_20260503`
- Window: `2025-03-24` to `2026-03-24`
- Loaded warmup starts: `2025-01-01`
- Scope: the nine screenshot legs only; `GC Asia LSI` was not included.
- Objective: squeeze last-year Calmar and net/DD without Bailey-style deflation.
- Added: wider local grids, richer regime gates, ORB wide-stop compression, extra ORB reentry policies, split directions, finer windows, and extra LSI stop/target/entry modes.

## Cross-Leg Winners

| leg | best squeeze | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_ny_orb | rr=6, tp1=0.8, stop_atr_pct=3, up to two trades, min_gap_orb_pct=5, entry_end=11:30, ORB 8m, extreme/chasing FVG | gate_none | curve | 77 | 63.94 | 12.788 | 2.28 | -5 | 53.19 | 0.918 |
| nq_asia_orb | rr=5.5, tp1=0.8, entry_end=06:00, up to two trades, flat_start=06:00, stop_atr_pct=3, ORB 15m, exclude Fri | gate_skip_bear_medium_high | curve | 173 | 91.23 | 6.179 | 1.836 | -14.76 | 82.46 | 0.927 |
| nq_ny_lsi | rr=3, tp1=0.8, flat_start=15:00, htf_n_left=3, FVG 10/10, entry_end=15:00, atr_length=5, 08:30-14:30 | gate_none | curve | 93 | 42.71 | 10.678 | 2.107 | -4 | 38.89 | 0.94 |
| es_ny_orb | rr=7, tp1=0.8, include all weekdays, min_gap_atr_pct=1, if stop >= 12.5 pts, target rr=3, impulse close filter on, cancel pending limit after TP1 touch, flat_start=13:30 | gate_skip_medium_vol | curve | 222 | 111.94 | 4.146 | 1.671 | -27 | 91.15 | 0.98 |
| es_asia_orb | rr=2, tp1=0.7, stop_orb_pct=75, min_gap_atr_pct=0.375, exclude Mon, flat_start=06:00, atr_length=10, if stop >= 12.5 pts, target rr=1.5 | gate_skip_sideways_high_vol | curve | 216 | 61.61 | 9.91 | 1.641 | -6.22 | 47.87 | 0.817 |
| es_ny_lsi | exclude Wed, FVG 7/3, rr=5, tp1=0.25, lsi_stop_mode=struct_75pct, atr_length=14, max_fvg_to_inversion_bars=16, entry_end=14:00 | gate_skip_high_vol | curve | 32 | 28.64 | 20.832 | 4.58 | -1.38 | 22.27 | 0.665 |
| gc_ny_orb | rr=12, tp1=0.8, atr_length=5, entry_end=11:30, min_gap_orb_pct=20, stop_atr_pct=3, flat_start=15:50, include all weekdays | gate_skip_sideways_medium_vol | curve | 45 | 66.86 | 13.372 | 3.131 | -5 | 62.79 | 0.877 |
| gc_asia_orb | rr=3, tp1=0.8, cancel pending limit after TP2 touch, stop_atr_pct=3, min_gap_atr_pct=1, ORB 10m, if stop >= 15 pts, target rr=1, entry_end=23:00 | gate_skip_medium_vol | curve | 121 | 57.27 | 11.453 | 1.862 | -5 | 47.35 | 0.603 |
| gc_ny_lsi | include all weekdays, lsi_n_left=10, timed hybrid <=60m close, rr=3.5, tp1=0.3, lsi_stop_mode=struct_75pct, entry_end=15:30, atr_length=5 | gate_skip_high_vol | curve | 9 | 6.18 | 60.284 | 60.351 | -0.1 | 6.18 | 0.915 |

## NQ NY ORB

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_none | curve | 77 | 63.94 | 12.788 | 2.28 | -5 | 89.5023 | 53.19 | 0.918 | rr=6, tp1=0.8, stop_atr_pct=3, up to two trades, min_gap_orb_pct=5, entry_end=11:30, ORB 8m, extreme/chasing FVG |
| best_curve_calmar | gate_none | curve | 77 | 63.94 | 12.788 | 2.28 | -5 | 89.5023 | 53.19 | 0.918 | rr=6, tp1=0.8, stop_atr_pct=3, up to two trades, min_gap_orb_pct=5, entry_end=11:30, ORB 8m, extreme/chasing FVG |
| best_curve_net | gate_none | curve | 109 | 70 | 8.139 | 1.922 | -8.6 | 85.108 | 67.09 | 0.905 | rr=6, tp1=0.8, stop_atr_pct=3, up to three trades, min_gap_orb_pct=5, entry_end=12:30, ORB 8m, extreme/chasing FVG |
| best_raw_calmar | gate_none | curve | 77 | 63.94 | 12.788 | 2.28 | -5 | 89.5023 | 53.19 | 0.918 | rr=6, tp1=0.8, stop_atr_pct=3, up to two trades, min_gap_orb_pct=5, entry_end=11:30, ORB 8m, extreme/chasing FVG |
| best_raw_net | gate_none | n/a | 104 | 79.25 | 6.096 | 2.122 | -13 | 89.3205 | 81.34 | - | rr=6, tp1=0.8, stop_atr_pct=3, up to two trades, min_gap_orb_pct=5, entry_end=12:30, ORB 8m, extreme/chasing FVG |

Combo categories searched: `rr_tp1, stop, reentry, gap, entry_end, orb_window, fvg_selection`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr7",
    "atr5",
    "atr10"
  ],
  "direction": [
    "dir_both",
    "dir_short"
  ],
  "dow": [
    "dow_none",
    "dow_exTue",
    "dow_exThu"
  ],
  "entry_end": [
    "entry_end_1230",
    "entry_end_1130",
    "entry_end_1200"
  ],
  "flat_start": [
    "flat_1500",
    "flat_1430",
    "flat_1550"
  ],
  "fvg_selection": [
    "fvg_extreme"
  ],
  "gap": [
    "gap_orb_7p5",
    "gap_orb_5p0",
    "gap_atr_1p5"
  ],
  "icf": [
    "icf_off"
  ],
  "orb_window": [
    "orb8m",
    "orb10m",
    "orb30m"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp2",
    "pre_cancel_tp1"
  ],
  "reentry": [
    "cap3_any",
    "uncapped_any",
    "cap2_any"
  ],
  "rr_tp1": [
    "rr6p0_tp0p8",
    "rr4p5_tp0p8",
    "rr5p0_tp0p8"
  ],
  "stop": [
    "stop_orb_25p0",
    "stop_atr_3p0",
    "stop_atr_4p0"
  ],
  "wide_stop": [
    "wide_t75_rr1",
    "wide_t75_rr1p25",
    "wide_t75_rr1p5"
  ]
}
```

</details>

## NQ Asia ORB

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_skip_bear_medium_high | curve | 173 | 91.23 | 6.179 | 1.836 | -14.76 | 100.809 | 82.46 | 0.927 | rr=5.5, tp1=0.8, entry_end=06:00, up to two trades, flat_start=06:00, stop_atr_pct=3, ORB 15m, exclude Fri |
| best_curve_calmar | gate_only_sideways | curve | 55 | 26.13 | 15.07 | 3.608 | -1.73 | 57.7622 | 19.37 | 0.694 | rr=6, tp1=0.8, entry_end=06:00, up to two trades, flat_start=03:00, stop_orb_pct=150, ORB 10m, exclude Fri |
| best_curve_net | gate_skip_bear_medium_high | curve | 173 | 91.23 | 6.179 | 1.836 | -14.76 | 100.809 | 82.46 | 0.927 | rr=5.5, tp1=0.8, entry_end=06:00, up to two trades, flat_start=06:00, stop_atr_pct=3, ORB 15m, exclude Fri |
| best_raw_calmar | gate_only_sideways | curve | 55 | 26.13 | 15.07 | 3.608 | -1.73 | 57.7622 | 19.37 | 0.694 | rr=6, tp1=0.8, entry_end=06:00, up to two trades, flat_start=03:00, stop_orb_pct=150, ORB 10m, exclude Fri |
| best_raw_net | gate_skip_bear_medium_high | curve | 173 | 91.23 | 6.179 | 1.836 | -14.76 | 100.809 | 82.46 | 0.927 | rr=5.5, tp1=0.8, entry_end=06:00, up to two trades, flat_start=06:00, stop_atr_pct=3, ORB 15m, exclude Fri |

Combo categories searched: `rr_tp1, entry_end, reentry, flat_start, stop, orb_window, dow`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr7",
    "atr10",
    "atr12"
  ],
  "direction": [
    "dir_both"
  ],
  "dow": [
    "dow_exFri",
    "dow_exMon",
    "dow_exTue"
  ],
  "entry_end": [
    "entry_end_0300",
    "entry_end_0400",
    "entry_end_0600"
  ],
  "flat_start": [
    "flat_0600",
    "flat_0500",
    "flat_0300"
  ],
  "fvg_selection": [
    "fvg_extreme"
  ],
  "gap": [
    "gap_orb_11p25",
    "gap_orb_10p0",
    "gap_atr_1p0"
  ],
  "icf": [
    "icf_on"
  ],
  "orb_window": [
    "orb15m",
    "orb10m",
    "orb20m"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp2",
    "pre_cancel_tp1"
  ],
  "reentry": [
    "cap2_any",
    "cap3_any",
    "uncapped_any"
  ],
  "rr_tp1": [
    "rr6p0_tp0p8",
    "rr5p5_tp0p8",
    "rr6p0_tp0p7"
  ],
  "stop": [
    "stop_orb_150p0",
    "stop_atr_3p0",
    "stop_atr_3p2"
  ],
  "wide_stop": [
    "wide_t75_rr1",
    "wide_t75_rr1p25",
    "wide_t75_rr1p5"
  ]
}
```

</details>

## NQ NY LSI

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_none | curve | 93 | 42.71 | 10.678 | 2.107 | -4 | 64.1839 | 38.89 | 0.94 | rr=3, tp1=0.8, flat_start=15:00, htf_n_left=3, FVG 10/10, entry_end=15:00, atr_length=5, 08:30-14:30 |
| best_curve_calmar | gate_only_bull | curve | 34 | 16.88 | 14.889 | 3.082 | -1.13 | 48.0639 | 14.25 | 0.616 | rr=2.5, tp1=0.6, flat_start=15:00, htf_n_left=6, FVG 20/3, entry_end=15:00, atr_length=10, 08:30-14:30 |
| best_curve_net | gate_none | curve | 93 | 42.71 | 10.678 | 2.107 | -4 | 64.1839 | 38.89 | 0.94 | rr=3, tp1=0.8, flat_start=15:00, htf_n_left=3, FVG 10/10, entry_end=15:00, atr_length=5, 08:30-14:30 |
| best_raw_calmar | gate_skip_sideways_high_vol | n/a | 32 | 23.54 | 23.539 | 4.851 | -1 | 72.7368 | 21.04 | - | rr=3, tp1=0.8, flat_start=14:30, htf_n_left=6, FVG 20/3, entry_end=15:00, atr_length=5, 08:30-14:30 |
| best_raw_net | gate_none | curve | 93 | 42.71 | 10.678 | 2.107 | -4 | 64.1839 | 38.89 | 0.94 | rr=3, tp1=0.8, flat_start=15:00, htf_n_left=3, FVG 10/10, entry_end=15:00, atr_length=5, 08:30-14:30 |

Combo categories searched: `rr_tp1, flat_start, htf_left, fvg_window, entry_end, atr, entry_window`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr5",
    "atr7",
    "atr10"
  ],
  "direction": [
    "dir_long",
    "dir_both",
    "dir_short"
  ],
  "dow": [
    "dow_exTue",
    "dow_exMon",
    "dow_none"
  ],
  "entry_end": [
    "entry_1500",
    "entry_1530",
    "entry_1300"
  ],
  "entry_mode": [
    "mode_level_limit",
    "mode_timed_hybrid_30",
    "mode_timed_hybrid_60"
  ],
  "entry_window": [
    "window_0830_1430",
    "window_0830_1330",
    "window_0800_1300"
  ],
  "flat_start": [
    "flat_1430",
    "flat_1330",
    "flat_1500"
  ],
  "fvg_window": [
    "fvgL20_R3",
    "fvgL33_R3",
    "fvgL10_R10"
  ],
  "gap": [
    "gap1",
    "gap5",
    "gap4"
  ],
  "htf_left": [
    "htfN2",
    "htfN6",
    "htfN3"
  ],
  "htf_sweep_source": [
    "src_htf_eqhl"
  ],
  "htf_tf": [
    "htf90",
    "htf30"
  ],
  "lsi_clean_path": [
    "clean_on"
  ],
  "lsi_first_fvg": [
    "first_fvg_on"
  ],
  "lsi_stale_pivot": [
    "stale_consumes_off"
  ],
  "lsi_stop_mode": [
    "stop_struct_75pct",
    "stop_gap_2x",
    "stop_struct_50pct"
  ],
  "lsi_sweep_gate": [
    "sweep_gate_entry",
    "sweep_gate_rth"
  ],
  "lsi_target_mode": [
    "target_structural",
    "target_left_structure"
  ],
  "max_inv": [
    "lag0",
    "lag36",
    "lag48"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp2",
    "pre_cancel_tp1_after_htf_sweep",
    "pre_cancel_tp1"
  ],
  "rr_tp1": [
    "rr2p5_tp0p8",
    "rr2p5_tp0p6",
    "rr3p0_tp0p8"
  ],
  "trade_cap": [
    "cap1",
    "cap3",
    "cap0"
  ]
}
```

</details>

## ES NY ORB

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_skip_medium_vol | curve | 222 | 111.94 | 4.146 | 1.671 | -27 | 114.252 | 91.15 | 0.98 | rr=7, tp1=0.8, include all weekdays, min_gap_atr_pct=1, if stop >= 12.5 pts, target rr=3, impulse close filter on, cancel pending limit after TP1 touch, flat_start=13:30 |
| best_curve_calmar | gate_only_high_vol | curve | 94 | 76.57 | 10.938 | 2.143 | -7 | 97.8393 | 47.84 | 0.829 | rr=7, tp1=0.8, include all weekdays, min_gap_atr_pct=1, if stop >= 12.5 pts, target rr=3, impulse close filter on, cancel pending limit after TP1 touch, flat_start=15:50 |
| best_curve_net | gate_skip_medium_vol | curve | 222 | 111.94 | 4.146 | 1.671 | -27 | 114.252 | 91.15 | 0.98 | rr=7, tp1=0.8, include all weekdays, min_gap_atr_pct=1, if stop >= 12.5 pts, target rr=3, impulse close filter on, cancel pending limit after TP1 touch, flat_start=13:30 |
| best_raw_calmar | gate_only_high_vol | curve | 94 | 76.57 | 10.938 | 2.143 | -7 | 97.8393 | 47.84 | 0.829 | rr=7, tp1=0.8, include all weekdays, min_gap_atr_pct=1, if stop >= 12.5 pts, target rr=3, impulse close filter on, cancel pending limit after TP1 touch, flat_start=15:50 |
| best_raw_net | gate_skip_medium_vol | curve | 222 | 111.94 | 4.146 | 1.671 | -27 | 114.252 | 91.15 | 0.98 | rr=7, tp1=0.8, include all weekdays, min_gap_atr_pct=1, if stop >= 12.5 pts, target rr=3, impulse close filter on, cancel pending limit after TP1 touch, flat_start=13:30 |

Combo categories searched: `rr_tp1, dow, gap, wide_stop, icf, pre_entry_cancel, flat_start`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr5",
    "atr10",
    "atr14"
  ],
  "direction": [
    "dir_short",
    "dir_long"
  ],
  "dow": [
    "dow_none",
    "dow_exFri",
    "dow_exTue"
  ],
  "entry_end": [
    "entry_end_1300",
    "entry_end_1530",
    "entry_end_1400"
  ],
  "flat_start": [
    "flat_1530",
    "flat_1330",
    "flat_1550"
  ],
  "fvg_selection": [
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_1p0",
    "gap_atr_0p5",
    "gap_orb_5p0"
  ],
  "icf": [
    "icf_off",
    "icf_on"
  ],
  "orb_window": [
    "orb8m",
    "orb10m",
    "orb15m"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp1",
    "pre_cancel_tp2"
  ],
  "reentry": [
    "cap3_any",
    "uncapped_any",
    "cap2_full"
  ],
  "rr_tp1": [
    "rr7p0_tp0p8",
    "rr7p0_tp0p7",
    "rr7p0_tp0p6"
  ],
  "stop": [
    "stop_atr_3p0",
    "stop_atr_4p0",
    "stop_atr_6p0"
  ],
  "wide_stop": [
    "wide_t12p5_rr3",
    "wide_t12p5_rr2",
    "wide_t12p5_rr1p5"
  ]
}
```

</details>

## ES Asia ORB

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_skip_sideways_high_vol | curve | 216 | 61.61 | 9.91 | 1.641 | -6.22 | 80.618 | 47.87 | 0.817 | rr=2, tp1=0.7, stop_orb_pct=75, min_gap_atr_pct=0.375, exclude Mon, flat_start=06:00, atr_length=10, if stop >= 12.5 pts, target rr=1.5 |
| best_curve_calmar | gate_skip_sideways_high_vol | curve | 216 | 61.61 | 9.91 | 1.641 | -6.22 | 80.618 | 47.87 | 0.817 | rr=2, tp1=0.7, stop_orb_pct=75, min_gap_atr_pct=0.375, exclude Mon, flat_start=06:00, atr_length=10, if stop >= 12.5 pts, target rr=1.5 |
| best_curve_net | gate_skip_bull_medium_vol | curve | 246 | 61.93 | 7.307 | 1.531 | -8.48 | 75.0629 | 55.96 | 0.771 | rr=2, tp1=0.7, stop_orb_pct=50, min_gap_atr_pct=0.375, exclude Mon, flat_start=06:00, atr_length=10, if stop >= 15 pts, target rr=1.25 |
| best_raw_calmar | gate_skip_bull_medium_vol | n/a | 192 | 84.79 | 19.019 | 2.101 | -4.46 | 122.827 | 71.05 | - | rr=2, tp1=0.7, stop_orb_pct=50, min_gap_atr_pct=0.375, exclude Mon, flat_start=06:00, atr_length=7, if stop >= 15 pts, target rr=1.25 |
| best_raw_net | gate_skip_bull_medium_vol | n/a | 192 | 84.79 | 19.019 | 2.101 | -4.46 | 122.827 | 71.05 | - | rr=2, tp1=0.7, stop_orb_pct=50, min_gap_atr_pct=0.375, exclude Mon, flat_start=06:00, atr_length=7, if stop >= 15 pts, target rr=1.25 |

Combo categories searched: `rr_tp1, stop, gap, dow, flat_start, atr, wide_stop`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr30",
    "atr7",
    "atr10"
  ],
  "direction": [
    "dir_long",
    "dir_both",
    "dir_short"
  ],
  "dow": [
    "dow_exFri",
    "dow_exMon",
    "dow_exThu"
  ],
  "entry_end": [
    "entry_end_0400",
    "entry_end_0300",
    "entry_end_0100"
  ],
  "flat_start": [
    "flat_0600",
    "flat_0400",
    "flat_0300"
  ],
  "fvg_selection": [
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_0p25",
    "gap_atr_0p375",
    "gap_atr_0p0"
  ],
  "icf": [
    "icf_on"
  ],
  "orb_window": [
    "orb10m",
    "orb5m",
    "orb15m"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp2",
    "pre_cancel_tp1"
  ],
  "reentry": [
    "cap2_sl",
    "cap3_nonpos",
    "uncapped_any"
  ],
  "rr_tp1": [
    "rr1p75_tp0p8",
    "rr2p0_tp0p7",
    "rr4p0_tp0p35"
  ],
  "stop": [
    "stop_orb_50p0",
    "stop_orb_75p0",
    "stop_orb_156p25"
  ],
  "wide_stop": [
    "wide_t15_rr1p25",
    "wide_t12p5_rr1p5",
    "wide_t15_rr1p5"
  ]
}
```

</details>

## ES NY LSI

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_skip_high_vol | curve | 32 | 28.64 | 20.832 | 4.58 | -1.38 | 72.2415 | 22.27 | 0.665 | exclude Wed, FVG 7/3, rr=5, tp1=0.25, lsi_stop_mode=struct_75pct, atr_length=14, max_fvg_to_inversion_bars=16, entry_end=14:00 |
| best_curve_calmar | gate_skip_high_vol | curve | 32 | 28.64 | 20.832 | 4.58 | -1.38 | 72.2415 | 22.27 | 0.665 | exclude Wed, FVG 7/3, rr=5, tp1=0.25, lsi_stop_mode=struct_75pct, atr_length=14, max_fvg_to_inversion_bars=16, entry_end=14:00 |
| best_curve_net | gate_none | curve | 67 | 41.26 | 10.521 | 3.041 | -3.92 | 62.9903 | 28.44 | 0.918 | exclude Thu, FVG 7/3, rr=6, tp1=0.2, lsi_stop_mode=struct_75pct, atr_length=14, max_fvg_to_inversion_bars=48, entry_end=15:00 |
| best_raw_calmar | gate_skip_sideways_high_vol | n/a | 31 | 24.31 | 24.312 | 3.727 | -1 | 74.6574 | 17.83 | - | exclude Wed, FVG 10/2, rr=5, tp1=0.25, lsi_stop_mode=struct_75pct, atr_length=14, max_fvg_to_inversion_bars=16, entry_end=15:00 |
| best_raw_net | gate_none | curve | 67 | 41.26 | 10.521 | 3.041 | -3.92 | 62.9903 | 28.44 | 0.918 | exclude Thu, FVG 7/3, rr=6, tp1=0.2, lsi_stop_mode=struct_75pct, atr_length=14, max_fvg_to_inversion_bars=48, entry_end=15:00 |

Combo categories searched: `dow, fvg_window, rr_tp1, lsi_stop_mode, atr, max_inv, entry_end`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr14",
    "atr7",
    "atr10"
  ],
  "direction": [
    "dir_both",
    "dir_long",
    "dir_short"
  ],
  "dow": [
    "dow_exWed",
    "dow_exThu",
    "dow_none"
  ],
  "entry_end": [
    "entry_1500",
    "entry_1300",
    "entry_1400"
  ],
  "entry_mode": [
    "mode_level_limit",
    "mode_timed_hybrid_60",
    "mode_close"
  ],
  "entry_window": [
    "window_0830_1330",
    "window_0830_1430",
    "window_0800_1500"
  ],
  "flat_start": [
    "flat_1530",
    "flat_1500",
    "flat_1430"
  ],
  "fvg_window": [
    "fvgL7_R3",
    "fvgL10_R2",
    "fvgL20_R2"
  ],
  "gap": [
    "gap1",
    "gap2",
    "gap4"
  ],
  "htf_left": [
    "htfN2",
    "htfN4",
    "htfN6"
  ],
  "htf_sweep_source": [
    "src_htf_eqhl",
    "src_eqhl"
  ],
  "htf_tf": [
    "htf60",
    "htf30",
    "htf90"
  ],
  "lsi_clean_path": [
    "clean_on"
  ],
  "lsi_first_fvg": [
    "first_fvg_on"
  ],
  "lsi_stale_pivot": [
    "stale_consumes_off"
  ],
  "lsi_stop_mode": [
    "stop_struct_75pct",
    "stop_gap_2x",
    "stop_struct_50pct"
  ],
  "lsi_sweep_gate": [
    "sweep_gate_entry",
    "sweep_gate_rth"
  ],
  "lsi_target_mode": [
    "target_structural",
    "target_left_structure"
  ],
  "max_inv": [
    "lag48",
    "lag16",
    "lag36"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp1_after_htf_sweep",
    "pre_cancel_tp2",
    "pre_cancel_tp1"
  ],
  "rr_tp1": [
    "rr5p0_tp0p25",
    "rr6p0_tp0p2",
    "rr4p5_tp0p3"
  ],
  "trade_cap": [
    "cap1",
    "cap3",
    "cap0"
  ]
}
```

</details>

## GC NY ORB

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_skip_sideways_medium_vol | curve | 45 | 66.86 | 13.372 | 3.131 | -5 | 94.066 | 62.79 | 0.877 | rr=12, tp1=0.8, atr_length=5, entry_end=11:30, min_gap_orb_pct=20, stop_atr_pct=3, flat_start=15:50, include all weekdays |
| best_curve_calmar | gate_skip_sideways_medium_vol | curve | 39 | 61.06 | 15.265 | 3.282 | -4 | 92.3727 | 55.99 | 0.86 | rr=12, tp1=0.8, atr_length=5, entry_end=11:30, min_gap_orb_pct=20, stop_atr_pct=3, flat_start=15:50, exclude Tue |
| best_curve_net | gate_skip_medium_vol | curve | 56 | 67.33 | 8.416 | 2.709 | -8 | 83.6569 | 53.52 | 0.922 | rr=12, tp1=0.8, atr_length=5, entry_end=12:30, min_gap_orb_pct=20, stop_atr_pct=3, flat_start=15:50, include all weekdays |
| best_raw_calmar | gate_skip_sideways_medium_vol | n/a | 37 | 62.11 | 15.527 | 3.524 | -4 | 94.0534 | 55.04 | - | rr=12, tp1=0.8, atr_length=5, entry_end=11:00, min_gap_orb_pct=15, stop_atr_pct=3, flat_start=15:50, exclude Tue |
| best_raw_net | gate_skip_sideways_medium_vol | n/a | 42 | 68.91 | 13.781 | 3.444 | -5 | 97.077 | 62.84 | - | rr=12, tp1=0.8, atr_length=5, entry_end=11:00, min_gap_orb_pct=15, stop_atr_pct=3, flat_start=15:50, include all weekdays |

Combo categories searched: `rr_tp1, atr, entry_end, gap, stop, flat_start, dow`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr5",
    "atr10",
    "atr14"
  ],
  "direction": [
    "dir_both"
  ],
  "dow": [
    "dow_exWed",
    "dow_none",
    "dow_exTue"
  ],
  "entry_end": [
    "entry_end_1100",
    "entry_end_1130",
    "entry_end_1230"
  ],
  "flat_start": [
    "flat_1550",
    "flat_1430",
    "flat_1500"
  ],
  "fvg_selection": [
    "fvg_extreme"
  ],
  "gap": [
    "gap_orb_15p0",
    "gap_orb_20p0",
    "gap_atr_2p25"
  ],
  "icf": [
    "icf_on",
    "icf_off"
  ],
  "orb_window": [
    "orb15m",
    "orb20m",
    "orb30m"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp2",
    "pre_cancel_tp1"
  ],
  "reentry": [
    "cap2_any",
    "cap2_nonpos",
    "cap2_sl"
  ],
  "rr_tp1": [
    "rr12p0_tp0p8",
    "rr12p0_tp0p7",
    "rr11p0_tp0p8"
  ],
  "stop": [
    "stop_orb_25p0",
    "stop_atr_3p0",
    "stop_atr_3p6"
  ],
  "wide_stop": [
    "wide_t15_rr1",
    "wide_t15_rr1p25",
    "wide_t15_rr1p5"
  ]
}
```

</details>

## GC Asia ORB

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_skip_medium_vol | curve | 121 | 57.27 | 11.453 | 1.862 | -5 | 79.8585 | 47.35 | 0.603 | rr=3, tp1=0.8, cancel pending limit after TP2 touch, stop_atr_pct=3, min_gap_atr_pct=1, ORB 10m, if stop >= 15 pts, target rr=1, entry_end=23:00 |
| best_curve_calmar | gate_skip_medium_vol | curve | 121 | 57.27 | 11.453 | 1.862 | -5 | 79.8585 | 47.35 | 0.603 | rr=3, tp1=0.8, cancel pending limit after TP2 touch, stop_atr_pct=3, min_gap_atr_pct=1, ORB 10m, if stop >= 15 pts, target rr=1, entry_end=23:00 |
| best_curve_net | gate_skip_sideways_medium_vol | curve | 147 | 61.2 | 4.007 | 1.797 | -15.27 | 66.2757 | 46.53 | 0.967 | rr=3.5, tp1=0.6, cancel pending limit after TP2 touch, stop_orb_pct=50, min_gap_orb_pct=18.75, ORB 5m, if stop >= 15 pts, target rr=1, entry_end=01:00 |
| best_raw_calmar | gate_skip_bear_medium_high | n/a | 47 | 28.34 | 12.417 | 2.639 | -2.28 | 54.0596 | 22.38 | - | entry_end=01:00 |
| best_raw_net | gate_skip_sideways_medium_vol | curve | 147 | 61.2 | 4.007 | 1.797 | -15.27 | 66.2757 | 46.53 | 0.967 | rr=3.5, tp1=0.6, cancel pending limit after TP2 touch, stop_orb_pct=50, min_gap_orb_pct=18.75, ORB 5m, if stop >= 15 pts, target rr=1, entry_end=01:00 |

Combo categories searched: `rr_tp1, pre_entry_cancel, stop, gap, orb_window, wide_stop, entry_end`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr12",
    "atr10",
    "atr14"
  ],
  "direction": [
    "dir_both",
    "dir_long"
  ],
  "dow": [
    "dow_exThu",
    "dow_exFri",
    "dow_none"
  ],
  "entry_end": [
    "entry_end_0100",
    "entry_end_2300",
    "entry_end_2330"
  ],
  "flat_start": [
    "flat_0500",
    "flat_0300",
    "flat_0400"
  ],
  "fvg_selection": [
    "fvg_extreme"
  ],
  "gap": [
    "gap_atr_1p5",
    "gap_orb_18p75",
    "gap_atr_1p0"
  ],
  "icf": [
    "icf_on"
  ],
  "orb_window": [
    "orb10m",
    "orb5m",
    "orb20m"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp2",
    "pre_cancel_tp1"
  ],
  "reentry": [
    "cap2_nonpos",
    "cap2_sl",
    "cap3_nonpos"
  ],
  "rr_tp1": [
    "rr3p5_tp0p6",
    "rr3p0_tp0p7",
    "rr3p0_tp0p8"
  ],
  "stop": [
    "stop_orb_50p0",
    "stop_atr_3p0",
    "stop_atr_4p0"
  ],
  "wide_stop": [
    "wide_t15_rr1",
    "wide_t15_rr1p25",
    "wide_t15_rr1p5"
  ]
}
```

</details>

## GC NY LSI

| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_curve_squeeze | gate_skip_high_vol | curve | 9 | 6.18 | 60.284 | 60.351 | -0.1 | 132.873 | 6.18 | 0.915 | include all weekdays, lsi_n_left=10, timed hybrid <=60m close, rr=3.5, tp1=0.3, lsi_stop_mode=struct_75pct, entry_end=15:30, atr_length=5 |
| best_curve_calmar | gate_skip_high_vol | curve | 9 | 6.18 | 60.284 | 60.351 | -0.1 | 132.873 | 6.18 | 0.915 | include all weekdays, lsi_n_left=10, timed hybrid <=60m close, rr=3.5, tp1=0.3, lsi_stop_mode=struct_75pct, entry_end=15:30, atr_length=5 |
| best_curve_net | gate_skip_high_vol | curve | 9 | 6.18 | 60.284 | 60.351 | -0.1 | 132.873 | 6.18 | 0.915 | include all weekdays, lsi_n_left=10, timed hybrid <=60m close, rr=3.5, tp1=0.3, lsi_stop_mode=struct_75pct, entry_end=15:30, atr_length=5 |
| best_raw_calmar | gate_skip_high_vol | curve | 9 | 6.18 | 60.284 | 60.351 | -0.1 | 132.873 | 6.18 | 0.915 | include all weekdays, lsi_n_left=10, timed hybrid <=60m close, rr=3.5, tp1=0.3, lsi_stop_mode=struct_75pct, entry_end=15:30, atr_length=5 |
| best_raw_net | gate_skip_high_vol | curve | 9 | 6.18 | 60.284 | 60.351 | -0.1 | 132.873 | 6.18 | 0.915 | include all weekdays, lsi_n_left=10, timed hybrid <=60m close, rr=3.5, tp1=0.3, lsi_stop_mode=struct_75pct, entry_end=15:30, atr_length=5 |

Combo categories searched: `dow, n_left, entry_mode, rr_tp1, lsi_stop_mode, entry_end, atr`

<details><summary>Selected local options</summary>

```json
{
  "atr": [
    "atr5",
    "atr10",
    "atr14"
  ],
  "direction": [
    "dir_long",
    "dir_short"
  ],
  "dow": [
    "dow_exWed",
    "dow_none",
    "dow_exTue"
  ],
  "entry_end": [
    "entry_1530",
    "entry_1400",
    "entry_1500"
  ],
  "entry_mode": [
    "mode_timed_hybrid_60",
    "mode_timed_hybrid_30",
    "mode_fvg_limit"
  ],
  "flat_start": [
    "flat_1530",
    "flat_1500",
    "flat_1330"
  ],
  "fvg_window": [
    "fvgL20_R5",
    "fvgL30_R5",
    "fvgL7_R3"
  ],
  "gap": [
    "gap4",
    "gap3",
    "gap6"
  ],
  "lsi_clean_path": [
    "clean_off",
    "clean_on"
  ],
  "lsi_first_fvg": [
    "first_fvg_off",
    "first_fvg_on"
  ],
  "lsi_stale_pivot": [
    "stale_consumes_off"
  ],
  "lsi_stop_mode": [
    "stop_struct_75pct",
    "stop_struct_50pct"
  ],
  "lsi_sweep_gate": [
    "sweep_gate_entry",
    "sweep_gate_rth"
  ],
  "lsi_target_mode": [
    "target_structural",
    "target_left_structure"
  ],
  "n_left": [
    "nL10",
    "nL12",
    "nL8"
  ],
  "n_right": [
    "nR90",
    "nR60",
    "nR120"
  ],
  "pre_entry_cancel": [
    "pre_cancel_tp1",
    "pre_cancel_tp2"
  ],
  "rr_tp1": [
    "rr3p0_tp0p35",
    "rr3p5_tp0p3",
    "rr2p0_tp0p5"
  ]
}
```

</details>

## Read

- These are TESTING-only hot-regime candidates optimized directly on the last year.
- `curve`/`soft_curve` rows passed a one-step local-neighbor check inside the final combo grid.
- `raw` rows are diagnostics; use them only if a follow-up local grid turns the area from cliff into curve.
