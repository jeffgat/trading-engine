# ALPHA_V1 Hot-Regime Ablation

- Run slug: `alpha_v1_hot_regime_ablation_20260503`
- Window: `2016-04-17` to `2026-03-24`
- Intent: deliberately search for TESTING-only high-R hot-regime candidates, inspired by `H_ORB_ABLATED`.
- This is not a robust promotion packet. Full-history stats are shown as warning context.
- Hot score: `3*last1_net + 2*last2_net + full_net - 0.50*abs(last1_dd) - 0.25*abs(last2_dd) - 0.10*abs(full_dd) - 10*full_negative_years - 25*(last1_fills<12)`

## Execution Context

- `TESTING.H_ORB_ABLATED` is dry-mode only (`webhooks: []`).
- Its style: no stress gate, no Tuesday, later signal window, EMA disabled, body filter removed, all non-overlap reentries, and no wide-stop target reduction (`reduced_target_rr=2R`).
- This pass borrows the *research posture*, not the Hunter-specific rules.

```json
{
  "allow_same_bar_win_reentry": false,
  "body_min_pct": 0.0,
  "ema15_enabled": false,
  "ema15_max_distance": null,
  "enable_fast_reentry_exhaustion_filter": false,
  "entry_end": "13:05",
  "excluded_dow": [
    1
  ],
  "max_contracts": 20,
  "max_single_risk_usd": 350,
  "reduced_target_rr": 2.0,
  "reentry_max_extension_pct": null,
  "reentry_policy": "all_nonoverlap",
  "rejection_wick_max_pct": 20.0,
  "risk_usd": 350
}
```

## Baselines

| leg | full_net | full_dd | full_pf | last2_net | last1_net | last1_pf | last1_fills | hot_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_ny_htf_lsi | 92.58 | -10.94 | 1.446 | 26.01 | 14.11 | 1.932 | 39 | 183.0 |
| nq_asia_orb | 213.5 | -10.16 | 1.55 | 53.16 | 36.31 | 1.989 | 73 | 423.2 |
| es_asia_orb | 145.8 | -12.28 | 1.283 | 39.89 | 21.75 | 1.421 | 143 | 285.3 |
| es_ny_orb | 126.6 | -10.86 | 1.386 | 21.40 | 18.20 | 1.571 | 93 | 205.7 |

## Hot Candidates By Leg

### nq_ny_htf_lsi

| pick | variant | stage | full_net | full_dd | full_pf | neg_y | last2_net | last1_net | last1_dd | last1_pf | fills1y | hot_score | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | baseline | 92.58 | -10.94 | 1.446 | 0 | 26.01 | 14.11 | -3 | 1.932 | 39 | 183.0 | warning layer acceptable for TESTING |
| best_last1 | combo__window_0830_1430__dow_exFri__rr3p5_tp0p4__gap1p0__fvgL20_R2__lag24__cap2_ | combo | 91.59 | -15.12 | 1.31 | 2 | 32.65 | 17.82 | -5 | 1.729 | 60 | 184.5 | 2 negative years |
| best_last2 | combo__window_0830_1430__dow_exFri__rr3p5_tp0p4__gap1p0__fvgL20_R2__lag24__cap2_ | combo | 91.59 | -15.12 | 1.31 | 2 | 32.65 | 17.82 | -5 | 1.729 | 60 | 184.5 | 2 negative years |
| best_score | combo__window_0830_1430__dow_none__rr3p5_tp0p4__gap1p0__fvgL20_R2__lag24__cap2__ | combo | 113.2 | -17.91 | 1.302 | 1 | 29.90 | 16.61 | -5.62 | 1.486 | 76 | 206.2 | 1 negative years |

**Top OAT contributors**

| category | primary_option | label | delta_hot_score | delta_last1_net_r | delta_last2_net_r | delta_full_net_r | delta_last1_dd_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| entry_window | window_0830_1430 | 08:30-14:30 | 11.19 | 1.17 | 3.15 | 1.54 | 0 |
| min_gap | gap1p0 | min_gap_atr_pct=1 | 4.83 | 0.81 | 0.22 | 14.59 | -2.62 |
| entry_window | window_0830_1330 | 08:30-13:30 | 0 | 0 | 0 | 0 | 0 |
| fvg_window | fvgL30_R2 | lsi_fvg_window_left=30, right=2 | 0 | 0 | 0 | 0 | 0 |
| trade_cap | cap3 | htf_trade_max_per_session=3 | 0 | 0 | 0 | 0 | 0 |
| trade_cap | cap0 | htf_trade_max_per_session=0 | 0 | 0 | 0 | 0 | 0 |
| trade_cap | cap1 | htf_trade_max_per_session=1 | -2.02 | 0 | 0 | -2.02 | 0 |
| entry_window | window_0830_1230 | 08:30-12:30 | -8.59 | 1.8 | 0.13 | -4.9 | 1 |

**Worst OAT removals/changes**

| category | primary_option | label | delta_hot_score | delta_last1_net_r | delta_last2_net_r | delta_full_net_r |
| --- | --- | --- | --- | --- | --- | --- |
| entry_mode | mode_close | close entry | -108.0 | -4.26 | -5.25 | -53.13 |
| dow | dow_exTue | exclude Tue | -96.07 | -6.15 | -13.34 | -30.54 |
| entry_window | window_0930_1330 | 09:30-13:30 | -85.64 | -6.56 | -14.95 | -36.64 |
| htf_left | htfN5 | htf_n_left=5 | -81.96 | -0.09 | -9.87 | -21.41 |
| min_gap | gap4p0 | min_gap_atr_pct=4 | -75.63 | -8.13 | -14.00 | -13.33 |

### nq_asia_orb

| pick | variant | stage | full_net | full_dd | full_pf | neg_y | last2_net | last1_net | last1_dd | last1_pf | fills1y | hot_score | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | baseline | 213.5 | -10.16 | 1.55 | 0 | 53.16 | 36.31 | -6 | 1.989 | 73 | 423.2 | warning layer acceptable for TESTING |
| best_last1 | combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_5p | combo | 223.4 | -15.17 | 1.426 | 0 | 57.18 | 43.42 | -9 | 1.895 | 98 | 459.8 | warning layer acceptable for TESTING |
| best_last2 | combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_125p0__min_gap_orb_pct_10 | combo | 220.1 | -19.47 | 1.449 | 0 | 61.51 | 36.88 | -7 | 1.901 | 89 | 446.6 | warning layer acceptable for TESTING |
| best_score | combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_10 | combo | 242.8 | -14.22 | 1.467 | 0 | 61.07 | 41.40 | -7 | 1.91 | 90 | 482.5 | warning layer acceptable for TESTING |

**Top OAT contributors**

| category | primary_option | label | delta_hot_score | delta_last1_net_r | delta_last2_net_r | delta_full_net_r | delta_last1_dd_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| reentry | uncapped_any | uncapped non-overlapping trades | 45.26 | 2.45 | 6.96 | 24.00 | 0 |
| reentry | cap2_after_nonpositive | second trade only after <=0R first trade | 45.04 | 2.45 | 6.96 | 23.78 | 0 |
| reentry | cap2_any | up to two non-overlapping trades | 44.36 | 2.45 | 6.96 | 23.10 | 0 |
| dow | dow_none | include all weekdays | 23.80 | 3.65 | 2.95 | 8.09 | -1 |
| dow | dow_exFri | exclude Fri | 23.80 | 3.65 | 2.95 | 8.09 | -1 |
| gap | min_gap_orb_pct_5p0 | min_gap_orb_pct=5 | 11.18 | 4.67 | 1.23 | -3.55 | -2 |
| entry | entry_2315 | entry_end=23:15 | 4.01 | 1.49 | -7.51 | 14.57 | 0 |
| atr | atr14 | atr_length=14 | 1.3 | 0.38 | 0.67 | -0.92 | 0 |

**Worst OAT removals/changes**

| category | primary_option | label | delta_hot_score | delta_last1_net_r | delta_last2_net_r | delta_full_net_r |
| --- | --- | --- | --- | --- | --- | --- |
| fvg_selection | fvg_extreme | chase more extreme same-day FVG | -686.6 | -33.83 | -60.67 | -345.7 |
| wide_stop | wide_q75_rr1p0 | if risk>=19.5 pts, target rr=1 | -136.7 | -14.64 | -15.90 | -40.95 |
| rr_tp1 | rr4p0_tp0p3 | rr=4, tp1=0.3 | -125.1 | -10.85 | -16.67 | -59.26 |
| wide_stop | wide_q75_rr1p5 | if risk>=19.5 pts, target rr=1.5 | -112.7 | -11.62 | -12.20 | -33.40 |
| rr_tp1 | rr5p0_tp0p25 | rr=5, tp1=0.25 | -109.2 | -10.78 | -14.42 | -48.06 |

### es_asia_orb

| pick | variant | stage | full_net | full_dd | full_pf | neg_y | last2_net | last1_net | last1_dd | last1_pf | fills1y | hot_score | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | baseline | 145.8 | -12.28 | 1.283 | 0 | 39.89 | 21.75 | -5.82 | 1.421 | 143 | 285.3 | warning layer acceptable for TESTING |
| best_last1 | combo__entry_0600__dow_exFri__rr1p5_tp0p7__stop_orb_pct_100p0__min_gap_atr_pct_0 | combo | 154.5 | -20.48 | 1.148 | 2 | 44.46 | 41.98 | -4.85 | 1.458 | 240 | 341.4 | 2 negative years; low full PF 1.148 |
| best_last2 | combo__entry_0600__dow_exFri__rr1p5_tp0p7__stop_orb_pct_125p0__min_gap_atr_pct_0 | combo | 180.8 | -19.61 | 1.184 | 2 | 53.95 | 40.18 | -4.65 | 1.48 | 223 | 382.0 | 2 negative years |
| best_score | combo__entry_0600__dow_baseline__rr4p0_tp0p25__stop_orb_pct_125p0__min_gap_atr_p | combo | 203.3 | -17.05 | 1.217 | 0 | 44.80 | 38.33 | -4.61 | 1.456 | 237 | 400.5 | warning layer acceptable for TESTING |

**Top OAT contributors**

| category | primary_option | label | delta_hot_score | delta_last1_net_r | delta_last2_net_r | delta_full_net_r | delta_last1_dd_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| reentry | cap2_any | up to two non-overlapping trades | 61.16 | 8.79 | 7.2 | 19.92 | 0.71 |
| reentry | uncapped_any | uncapped non-overlapping trades | 53.01 | 7.89 | 8.71 | 21.53 | 0.54 |
| reentry | cap2_after_nonpositive | second trade only after <=0R first trade | 44.72 | 4.26 | 4.3 | 22.34 | 1.46 |
| entry | entry_0600 | entry_end=06:00 | 42.43 | 5.16 | 0.07 | 27.74 | 0.74 |
| atr | atr20 | atr_length=20 | 18.79 | 2.86 | 3.86 | 1.99 | 0.71 |
| entry | entry_0400 | entry_end=04:00 | 4.5 | 3.11 | -0.01 | 5.45 | 0.49 |
| entry | entry_0300 | entry_end=03:00 | 0 | 0 | 0 | 0 | 0 |
| wide_stop | wide_q75_rr1p5 | if risk>=6.75 pts, target rr=1.5 | 0 | 0 | 0 | 0 | 0 |

**Worst OAT removals/changes**

| category | primary_option | label | delta_hot_score | delta_last1_net_r | delta_last2_net_r | delta_full_net_r |
| --- | --- | --- | --- | --- | --- | --- |
| fvg_selection | fvg_extreme | chase more extreme same-day FVG | -1870.1 | -103.8 | -209.8 | -878.7 |
| gap | min_gap_atr_pct_1p0 | min_gap_atr_pct=1 | -174.5 | -15.88 | -25.84 | -52.11 |
| dow | dow_exWed | exclude Wed | -120.6 | -10.48 | -21.95 | -32.13 |
| dow | dow_exThu | exclude Thu | -96.36 | -7.01 | -17.50 | -29.50 |
| entry | entry_0200 | entry_end=02:00 | -71.55 | -4.06 | -10.51 | -29.29 |

### es_ny_orb

| pick | variant | stage | full_net | full_dd | full_pf | neg_y | last2_net | last1_net | last1_dd | last1_pf | fills1y | hot_score | warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | baseline | baseline | 126.6 | -10.86 | 1.386 | 1 | 21.40 | 18.20 | -9.61 | 1.571 | 93 | 205.7 | 1 negative years |
| best_last1 | combo__entry_1200__dow_none__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p75 | combo | 86.52 | -26.26 | 1.186 | 3 | 26.75 | 24.36 | -10.20 | 1.475 | 98 | 172.4 | 3 negative years; deep full DD -26.26R |
| best_last2 | combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_ | combo | 157.1 | -20.62 | 1.274 | 1 | 48.48 | 19.75 | -16.53 | 1.287 | 124 | 288.9 | 1 negative years |
| best_score | combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_ | combo | 157.1 | -20.62 | 1.274 | 1 | 48.48 | 19.75 | -16.53 | 1.287 | 124 | 288.9 | 1 negative years |

**Top OAT contributors**

| category | primary_option | label | delta_hot_score | delta_last1_net_r | delta_last2_net_r | delta_full_net_r | delta_last1_dd_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| reentry | cap2_any | up to two non-overlapping trades | 70.11 | 0.47 | 16.49 | 38.55 | -3.51 |
| reentry | uncapped_any | uncapped non-overlapping trades | 56.60 | -1.06 | 14.86 | 34.71 | -5.51 |
| reentry | cap2_after_nonpositive | second trade only after <=0R first trade | 8.58 | -5.05 | 11.61 | 12.57 | -2.51 |
| entry | entry_1300 | entry_end=13:00 | 0 | 0 | 0 | 0 | 0 |
| stop | stop_atr_pct_3p0 | stop_atr_pct=3 | 0 | 0 | 0 | 0 | 0 |
| stop | stop_atr_pct_4p0 | stop_atr_pct=4 | 0 | 0 | 0 | 0 | 0 |
| gap | min_gap_atr_pct_0p75 | min_gap_atr_pct=0.75 | -1.6 | -1.92 | 3.69 | -3.22 | 0 |
| gap | min_gap_atr_pct_0p5 | min_gap_atr_pct=0.5 | -2.06 | -0.9 | -0.39 | 1.42 | 0 |

**Worst OAT removals/changes**

| category | primary_option | label | delta_hot_score | delta_last1_net_r | delta_last2_net_r | delta_full_net_r |
| --- | --- | --- | --- | --- | --- | --- |
| fvg_selection | fvg_extreme | chase more extreme same-day FVG | -751.8 | -33.61 | -61.99 | -390.9 |
| stop | stop_atr_pct_7p0 | stop_atr_pct=7 | -118.5 | -12.06 | -7.78 | -44.65 |
| dow | dow_exMon | exclude Mon | -112.5 | -7.64 | -18.58 | -29.56 |
| dow | dow_exFri | exclude Fri | -106.7 | -4.66 | -8.76 | -64.08 |
| dow | dow_exWed | exclude Wed | -106.3 | -4.08 | -24.19 | -23.55 |

## Portfolio View

This is a simple separate-account R aggregation of replacing each leg with its per-leg best hot-score row. It is a sizing/read-through proxy, not a prop simulation.

| portfolio | full_fills | full_net_r | full_pf | full_dd_r | full_negative_years | last_2y_fills | last_2y_net_r | last_2y_pf | last_2y_dd_r | last_1y_fills | last_1y_net_r | last_1y_pf | last_1y_dd_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_current_alpha_v1 | 3471 | 578.5 | 1.401 | -15.40 | 0 | 694 | 140.5 | 1.487 | -13.38 | 348 | 90.38 | 1.658 | -11.21 |
| replace_each_leg_with_best_hot_score | 5159 | 716.5 | 1.298 | -23.27 | 0 | 1083 | 184.2 | 1.363 | -17.57 | 527 | 116.1 | 1.496 | -17.57 |

## Interpretation

- Treat any last-1y winner here as a TESTING-only branch. The point is forward observation, not portfolio promotion.
- A candidate is more interesting when it improves last 1y and last 2y together without exploding full-history DD or creating many negative full years.
- Candidates that win last 1y by removing protective filters but degrade full-history PF/DD are exactly the hot-regime archetype: potentially useful while conditions persist, fragile when they stop.
