# Hot Structural Sequence

- Run slug: `hot_structural_sequence_20260503`
- Last-1y window: `2025-03-24` to `2026-03-24`
- Last-2y/context window: `2024-03-24` to `2026-03-24`
- Baseline: current `HOT_ONE_YEAR_SQUEEZE` best curve-squeeze candidate per leg, including its existing regime gate.
- Tested structural families: ORB size regimes, prior-day range/trend context, Asia/NY session context, calendar/news filters, Hunter-inspired signal proxies, and custom day-type combinations.
- These are TESTING-only, hot-regime candidates; no Bailey-style deflation or holdout discipline is applied here.

## Best Structural Candidates

### Best Score / Calmar Tilt

| leg | pick | family | surface | fills | net_r | calmar | pf | dd | delta_r | base_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ NY ORB | combo__adverse_wick_le_35__exclude_cpi_nfp | combo | cliff | 48 | 56.3 | 18.768 | 3 | -3 | -7.65 | 63.95 |
| NQ Asia ORB | exclude_cpi_nfp | calendar_news | n/a | 162 | 77.24 | 5.231 | 1.76 | -14.76 | -6.17 | 83.41 |
| NQ NY LSI | prior_not_inside_day | prior_day | n/a | 81 | 42.54 | 13.863 | 2.386 | -3.07 | -0.17 | 42.71 |
| ES NY ORB | exclude_fomc | calendar_news | n/a | 179 | 120.97 | 8.641 | 1.938 | -14 | 5 | 115.97 |
| ES Asia ORB | combo__orb_not_extreme__exclude_fomc | combo | cliff | 143 | 55.34 | 14.636 | 1.947 | -3.78 | -5.73 | 61.07 |
| ES NY LSI | prior_not_inside_day | prior_day | n/a | 27 | 21.76 | 21.755 | 4.121 | -1 | 0.44 | 21.31 |
| GC NY ORB | combo__exclude_cpi_nfp__signal_outside_orb | combo | cliff | 36 | 63.99 | 14.967 | 3.71 | -4.28 | 7 | 56.99 |
| GC Asia ORB | combo__exclude_cpi_nfp__prior_not_inside_day | combo | cliff | 94 | 65.74 | 13.147 | 2.485 | -5 | 3.3 | 62.44 |
| GC NY LSI | exclude_fomc | calendar_news | n/a | 11 | 5.12 | 4.797 | 4.767 | -1.07 | 1 | 4.12 |

### Best Net Additions

| leg | pick | family | surface | fills | net_r | calmar | pf | dd | delta_r | base_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ NY ORB | exclude_cpi_nfp | calendar_news | n/a | 76 | 64.95 | 12.99 | 2.327 | -5 | 1 | 63.95 |
| NQ Asia ORB | none | - | - | - | - | - | - | - | - | 83.41 |
| NQ NY LSI | none | - | - | - | - | - | - | - | - | 42.71 |
| ES NY ORB | exclude_fomc | calendar_news | n/a | 179 | 120.97 | 8.641 | 1.938 | -14 | 5 | 115.97 |
| ES Asia ORB | none | - | - | - | - | - | - | - | - | 61.07 |
| ES NY LSI | prior_not_inside_day | prior_day | n/a | 27 | 21.76 | 21.755 | 4.121 | -1 | 0.44 | 21.31 |
| GC NY ORB | combo__exclude_cpi_nfp__signal_outside_orb | combo | cliff | 36 | 63.99 | 14.967 | 3.71 | -4.28 | 7 | 56.99 |
| GC Asia ORB | combo__exclude_cpi_nfp__prior_not_inside_day | combo | cliff | 94 | 65.74 | 13.147 | 2.485 | -5 | 3.3 | 62.44 |
| GC NY LSI | exclude_fomc | calendar_news | n/a | 11 | 5.12 | 4.797 | 4.767 | -1.07 | 1 | 4.12 |

## NQ NY ORB

Baseline after existing `gate_none` gate: 77 fills, `63.95R`, Calmar `12.79`, PF `2.281`, DD `-5.0R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hunter_proxy | adverse_wick_le_35 | 49 | 55.3 | 18.434 | 2.896 | -3 | -8.65 | 48.57 | adverse wick <= 35% |
| calendar_news | exclude_cpi_nfp | 76 | 64.95 | 12.99 | 2.327 | -5 | 1 | 59.7 | exclude CPI and NFP dates |
| calendar_news | exclude_news | 72 | 62.52 | 12.504 | 2.331 | -5 | -1.43 | 58.47 | exclude FOMC/CPI/NFP/PPI dates |
| calendar_news | exclude_fomc | 75 | 62.73 | 12.547 | 2.279 | -5 | -1.22 | 54.08 | exclude FOMC dates |
| hunter_proxy | signal_body_50 | 32 | 50.69 | 16.897 | 4.106 | -3 | -13.26 | 41.87 | signal body >= 50% of candle |
| hunter_proxy | signal_close_strong_65 | 44 | 53.85 | 13.462 | 3.137 | -4 | -10.1 | 51.69 | signal closes in directional 65% of candle |
| orb_size | orb_not_high | 51 | 54.6 | 10.92 | 2.815 | -5 | -9.35 | 62.48 | exclude high ORB range pctile |
| orb_size | orb_not_extreme | 59 | 59.44 | 8.491 | 2.642 | -7 | -4.51 | 59.32 | exclude extreme ORB range pctile >= 80% |
| calendar_news | exclude_bom3 | 66 | 58.82 | 9.804 | 2.397 | -6 | -5.13 | 48.66 | exclude day-of-month 1-3 |
| hunter_proxy | signal_outside_orb | 74 | 60.49 | 7.562 | 2.263 | -8 | -3.45 | 51.81 | signal close outside ORB edge |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__adverse_wick_le_35__exclude_cpi_nfp | cliff | 48 | 56.3 | 18.768 | 3 | -3 | -7.65 | 51.57 | 0 | adverse_wick_le_35\|exclude_cpi_nfp |
| combo__adverse_wick_le_35__exclude_cpi_nfp__orb_not_high__prior_not_inside_day | curve | 31 | 48.06 | 16.02 | 3.954 | -3 | -15.89 | 56.64 | 0.799 | adverse_wick_le_35\|exclude_cpi_nfp\|orb_not_high\|prior_not_inside_day |
| combo__adverse_wick_le_35__exclude_cpi_nfp__orb_not_high | curve | 33 | 48.79 | 16.265 | 3.828 | -3 | -15.16 | 54.78 | 0.979 | adverse_wick_le_35\|exclude_cpi_nfp\|orb_not_high |
| combo__adverse_wick_le_35__exclude_cpi_nfp__prior_not_inside_day | curve | 43 | 55.3 | 13.824 | 3.194 | -4 | -8.65 | 54.16 | 0.982 | adverse_wick_le_35\|exclude_cpi_nfp\|prior_not_inside_day |
| combo__adverse_wick_le_35__orb_not_high | cliff | 34 | 47.79 | 15.931 | 3.617 | -3 | -16.16 | 51.78 | 0 | adverse_wick_le_35\|orb_not_high |
| combo__adverse_wick_le_35__prior_not_inside_day | cliff | 44 | 54.3 | 13.574 | 3.072 | -4 | -9.65 | 51.16 | 0 | adverse_wick_le_35\|prior_not_inside_day |
| combo__exclude_cpi_nfp__orb_not_high | cliff | 50 | 55.6 | 11.12 | 2.912 | -5 | -8.35 | 65.48 | 0 | exclude_cpi_nfp\|orb_not_high |
| combo__adverse_wick_le_35__orb_not_high__prior_not_inside_day | curve | 32 | 47.06 | 11.765 | 3.723 | -4 | -16.89 | 53.64 | 1.154 | adverse_wick_le_35\|orb_not_high\|prior_not_inside_day |
| combo__exclude_cpi_nfp__orb_not_high__prior_not_inside_day | curve | 45 | 51.47 | 8.578 | 2.981 | -6 | -12.48 | 62.55 | 1.071 | exclude_cpi_nfp\|orb_not_high\|prior_not_inside_day |
| combo__exclude_cpi_nfp__prior_not_inside_day | cliff | 67 | 55.14 | 9.19 | 2.255 | -6 | -8.81 | 54.09 | 0 | exclude_cpi_nfp\|prior_not_inside_day |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_none",
  "base_variant": "prev_curve_net__combo__rr6p0_tp0p8__stop_atr_3p0__cap2_any__gap_orb_5p0__entry_end_1130__orb8m__fvg_extreme",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": 1.0,
      "gate_id": "exclude_cpi_nfp",
      "label": "exclude CPI and NFP dates",
      "last1_calmar": 12.99,
      "last1_net_r": 64.95
    },
    "hunter_proxy": {
      "delta_last1_net_r": -8.65,
      "gate_id": "adverse_wick_le_35",
      "label": "adverse wick <= 35%",
      "last1_calmar": 18.434,
      "last1_net_r": 55.3
    },
    "orb_size": {
      "delta_last1_net_r": -9.35,
      "gate_id": "orb_not_high",
      "label": "exclude high ORB range pctile",
      "last1_calmar": 10.92,
      "last1_net_r": 54.6
    },
    "prior_day": {
      "delta_last1_net_r": -9.81,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 7.735,
      "last1_net_r": 54.14
    },
    "session_context": {
      "delta_last1_net_r": -13.92,
      "gate_id": "asia_trend_aligned",
      "label": "NY only: Asia trend aligns with trade",
      "last1_calmar": 8.339,
      "last1_net_r": 50.03
    }
  }
}
```

</details>

## NQ Asia ORB

Baseline after existing `gate_skip_bear_medium_high` gate: 165 fills, `83.41R`, Calmar `5.649`, PF `1.804`, DD `-14.76R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendar_news | exclude_cpi_nfp | 162 | 77.24 | 5.231 | 1.76 | -14.76 | -6.17 | 74.24 | exclude CPI and NFP dates |
| calendar_news | exclude_fomc | 156 | 76.45 | 5.178 | 1.775 | -14.76 | -6.95 | 75.45 | exclude FOMC dates |
| calendar_news | exclude_bom3 | 151 | 77.33 | 5.238 | 1.814 | -14.76 | -6.08 | 73.25 | exclude day-of-month 1-3 |
| calendar_news | exclude_news | 148 | 75.29 | 5.099 | 1.821 | -14.76 | -8.12 | 79.6 | exclude FOMC/CPI/NFP/PPI dates |
| prior_day | prior_not_inside_day | 158 | 72.98 | 5.717 | 1.729 | -12.76 | -10.43 | 65.01 | exclude inside day |
| calendar_news | exclude_eom5 | 127 | 71.42 | 6.038 | 1.889 | -11.83 | -11.99 | 59.84 | exclude day-of-month >= 25 |
| prior_day | prior_trend_aligned | 91 | 48.62 | 6.751 | 1.93 | -7.2 | -34.79 | 63.38 | prior RTH trend aligns with trade direction |
| session_context | asia_prior_rth_trend_aligned | 91 | 48.62 | 6.751 | 1.93 | -7.2 | -34.79 | 63.38 | Asia: prior RTH trend aligns |
| custom_day_type | momentum_carry | 74 | 47.06 | 6.012 | 2.139 | -7.83 | -36.35 | 66.05 | prior trend and prior close extreme align |
| prior_day | prior_close_aligned_extreme | 74 | 47.06 | 6.012 | 2.139 | -7.83 | -36.35 | 58.3 | prior close near directional extreme |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__exclude_cpi_nfp__prior_not_inside_day | cliff | 155 | 66.81 | 5.234 | 1.683 | -12.76 | -16.6 | 61.64 | 0 | exclude_cpi_nfp\|prior_not_inside_day |
| combo__asia_prior_rth_trend_aligned__momentum_carry | cliff | 74 | 47.06 | 6.012 | 2.139 | -7.83 | -36.35 | 66.05 | 0 | asia_prior_rth_trend_aligned\|momentum_carry |
| combo__prior_not_inside_day__orb_not_high | cliff | 122 | 54.2 | 5.428 | 1.714 | -9.98 | -29.21 | 45.33 | 0 | prior_not_inside_day\|orb_not_high |
| combo__exclude_cpi_nfp__asia_prior_rth_trend_aligned | cliff | 89 | 44.49 | 6.177 | 1.881 | -7.2 | -38.92 | 61.04 | 0 | exclude_cpi_nfp\|asia_prior_rth_trend_aligned |
| combo__exclude_cpi_nfp__prior_not_inside_day__orb_not_high | curve | 121 | 52.16 | 5.224 | 1.689 | -9.98 | -31.25 | 45.09 | 1.002 | exclude_cpi_nfp\|prior_not_inside_day\|orb_not_high |
| combo__exclude_cpi_nfp__momentum_carry | cliff | 72 | 42.92 | 5.484 | 2.081 | -7.83 | -40.48 | 61.72 | 0 | exclude_cpi_nfp\|momentum_carry |
| combo__exclude_cpi_nfp__asia_prior_rth_trend_aligned__momentum_carry | curve | 72 | 42.92 | 5.484 | 2.081 | -7.83 | -40.48 | 61.72 | 1.096 | exclude_cpi_nfp\|asia_prior_rth_trend_aligned\|momentum_carry |
| combo__exclude_cpi_nfp__orb_not_high | cliff | 125 | 50.04 | 4.175 | 1.637 | -11.98 | -33.37 | 48.47 | 0 | exclude_cpi_nfp\|orb_not_high |
| combo__prior_not_inside_day__momentum_carry | cliff | 71 | 40.49 | 5.174 | 2.012 | -7.83 | -42.91 | 51.45 | 0 | prior_not_inside_day\|momentum_carry |
| combo__prior_not_inside_day__asia_prior_rth_trend_aligned__momentum_carry | curve | 71 | 40.49 | 5.174 | 2.012 | -7.83 | -42.91 | 51.45 | 1 | prior_not_inside_day\|asia_prior_rth_trend_aligned\|momentum_carry |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_skip_bear_medium_high",
  "base_variant": "prev_curve_calmar__combo__rr5p5_tp0p8__entry_end_0600__cap2_any__flat_0600__stop_atr_3p0__orb15m__dow_exFri",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": -6.17,
      "gate_id": "exclude_cpi_nfp",
      "label": "exclude CPI and NFP dates",
      "last1_calmar": 5.231,
      "last1_net_r": 77.24
    },
    "custom_day_type": {
      "delta_last1_net_r": -36.35,
      "gate_id": "momentum_carry",
      "label": "prior trend and prior close extreme align",
      "last1_calmar": 6.012,
      "last1_net_r": 47.06
    },
    "orb_size": {
      "delta_last1_net_r": -31.34,
      "gate_id": "orb_not_high",
      "label": "exclude high ORB range pctile",
      "last1_calmar": 4.345,
      "last1_net_r": 52.07
    },
    "prior_day": {
      "delta_last1_net_r": -10.43,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 5.717,
      "last1_net_r": 72.98
    },
    "session_context": {
      "delta_last1_net_r": -34.79,
      "gate_id": "asia_prior_rth_trend_aligned",
      "label": "Asia: prior RTH trend aligns",
      "last1_calmar": 6.751,
      "last1_net_r": 48.62
    }
  }
}
```

</details>

## NQ NY LSI

Baseline after existing `gate_none` gate: 93 fills, `42.71R`, Calmar `10.678`, PF `2.107`, DD `-4.0R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prior_day | prior_not_inside_day | 81 | 42.54 | 13.863 | 2.386 | -3.07 | -0.17 | 49.59 | exclude inside day |
| prior_day | prior_trend_aligned | 50 | 37.58 | 12.526 | 3.257 | -3 | -5.13 | 54.11 | prior RTH trend aligns with trade direction |
| calendar_news | exclude_fomc | 92 | 41.51 | 10.378 | 2.073 | -4 | -1.2 | 57.08 | exclude FOMC dates |
| custom_day_type | momentum_carry | 33 | 30.47 | 15.234 | 3.643 | -2 | -12.24 | 41.03 | prior trend and prior close extreme align |
| calendar_news | exclude_cpi_nfp | 82 | 38.4 | 11.724 | 2.164 | -3.28 | -4.31 | 50.15 | exclude CPI and NFP dates |
| hunter_proxy | signal_close_strong_65 | 79 | 37.48 | 9.371 | 2.156 | -4 | -5.23 | 60.57 | signal closes in directional 65% of candle |
| hunter_proxy | adverse_wick_le_35 | 79 | 37.48 | 9.371 | 2.156 | -4 | -5.23 | 60.57 | adverse wick <= 35% |
| calendar_news | exclude_bom3 | 87 | 36.5 | 11.144 | 1.974 | -3.28 | -6.21 | 52.35 | exclude day-of-month 1-3 |
| calendar_news | exclude_eom5 | 69 | 33.56 | 10.247 | 2.206 | -3.28 | -9.15 | 54.62 | exclude day-of-month >= 25 |
| calendar_news | exclude_news | 76 | 35.77 | 10.351 | 2.146 | -3.46 | -6.94 | 44.37 | exclude FOMC/CPI/NFP/PPI dates |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__prior_not_inside_day__exclude_fomc | cliff | 80 | 41.34 | 13.193 | 2.343 | -3.13 | -1.37 | 45.27 | 0 | prior_not_inside_day\|exclude_fomc |
| combo__exclude_fomc__momentum_carry | cliff | 33 | 30.47 | 15.234 | 3.643 | -2 | -12.24 | 40.62 | 0 | exclude_fomc\|momentum_carry |
| combo__momentum_carry__orb_not_extreme | cliff | 24 | 27.64 | 13.818 | 5.109 | -2 | -15.07 | 38.94 | 0 | momentum_carry\|orb_not_extreme |
| combo__exclude_fomc__momentum_carry__orb_not_extreme | curve | 24 | 27.64 | 13.818 | 5.109 | -2 | -15.07 | 38.94 | 1 | exclude_fomc\|momentum_carry\|orb_not_extreme |
| combo__exclude_fomc__signal_close_strong_65 | cliff | 79 | 37.48 | 9.371 | 2.156 | -4 | -5.23 | 58.46 | 0 | exclude_fomc\|signal_close_strong_65 |
| combo__momentum_carry__signal_close_strong_65 | cliff | 32 | 27.77 | 13.884 | 3.402 | -2 | -14.94 | 40.23 | 0 | momentum_carry\|signal_close_strong_65 |
| combo__exclude_fomc__momentum_carry__signal_close_strong_65 | curve | 32 | 27.77 | 13.884 | 3.402 | -2 | -14.94 | 39.82 | 1 | exclude_fomc\|momentum_carry\|signal_close_strong_65 |
| combo__prior_not_inside_day__signal_close_strong_65 | cliff | 68 | 36.32 | 10.206 | 2.415 | -3.56 | -6.4 | 46.61 | 0 | prior_not_inside_day\|signal_close_strong_65 |
| combo__momentum_carry__signal_close_strong_65__orb_not_extreme | curve | 23 | 24.94 | 12.468 | 4.697 | -2 | -17.77 | 38.14 | 1.108 | momentum_carry\|signal_close_strong_65\|orb_not_extreme |
| combo__exclude_fomc__momentum_carry__signal_close_strong_65__orb_not_extreme | curve | 23 | 24.94 | 12.468 | 4.697 | -2 | -17.77 | 38.14 | 1.054 | exclude_fomc\|momentum_carry\|signal_close_strong_65\|orb_not_extreme |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_none",
  "base_variant": "prev_curve_net__combo__rr3p0_tp0p8__flat_1500__htfN3__fvgL10_R10__entry_1500__atr5__window_0830_1430",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": -1.2,
      "gate_id": "exclude_fomc",
      "label": "exclude FOMC dates",
      "last1_calmar": 10.378,
      "last1_net_r": 41.51
    },
    "custom_day_type": {
      "delta_last1_net_r": -12.24,
      "gate_id": "momentum_carry",
      "label": "prior trend and prior close extreme align",
      "last1_calmar": 15.234,
      "last1_net_r": 30.47
    },
    "hunter_proxy": {
      "delta_last1_net_r": -5.23,
      "gate_id": "signal_close_strong_65",
      "label": "signal closes in directional 65% of candle",
      "last1_calmar": 9.371,
      "last1_net_r": 37.48
    },
    "orb_size": {
      "delta_last1_net_r": -12.09,
      "gate_id": "orb_not_extreme",
      "label": "exclude extreme ORB range pctile >= 80%",
      "last1_calmar": 7.371,
      "last1_net_r": 30.62
    },
    "prior_day": {
      "delta_last1_net_r": -0.17,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 13.863,
      "last1_net_r": 42.54
    }
  }
}
```

</details>

## ES NY ORB

Baseline after existing `gate_skip_medium_vol` gate: 184 fills, `115.97R`, Calmar `8.283`, PF `1.865`, DD `-14.0R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendar_news | exclude_fomc | 179 | 120.97 | 8.641 | 1.938 | -14 | 5 | 142.11 | exclude FOMC dates |
| hunter_proxy | signal_outside_orb | 175 | 112.59 | 8.523 | 1.879 | -13.21 | -3.38 | 130.73 | signal close outside ORB edge |
| calendar_news | exclude_news | 161 | 114.13 | 7.916 | 1.986 | -14.42 | -1.84 | 126.03 | exclude FOMC/CPI/NFP/PPI dates |
| prior_day | prior_not_inside_day | 168 | 109.98 | 9.165 | 1.903 | -12 | -5.99 | 120.29 | exclude inside day |
| calendar_news | exclude_cpi_nfp | 174 | 116.76 | 7.112 | 1.927 | -16.42 | 0.79 | 115.38 | exclude CPI and NFP dates |
| calendar_news | exclude_bom3 | 161 | 99.84 | 7.68 | 1.85 | -13 | -16.12 | 121.91 | exclude day-of-month 1-3 |
| hunter_proxy | dist_orb_near | 94 | 92.85 | 11.606 | 2.493 | -8 | -23.12 | 84.1 | signal distance 0-50% of ORB |
| prior_day | prior_trend_aligned | 97 | 79.13 | 13.188 | 2.169 | -6 | -36.84 | 94.08 | prior RTH trend aligns with trade direction |
| prior_day | prior_range_high | 63 | 65.71 | 9.387 | 2.518 | -7 | -50.26 | 84.44 | only high prior-day range pctile >= 67% |
| calendar_news | exclude_eom5 | 138 | 83.76 | 5.235 | 1.819 | -16 | -32.21 | 70.56 | exclude day-of-month >= 25 |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__exclude_fomc__signal_outside_orb | cliff | 171 | 116.59 | 8.968 | 1.94 | -13 | 0.62 | 140.73 | 0 | exclude_fomc\|signal_outside_orb |
| combo__exclude_fomc__prior_not_inside_day | cliff | 164 | 113.98 | 9.498 | 1.968 | -12 | -1.99 | 130.29 | 0 | exclude_fomc\|prior_not_inside_day |
| combo__exclude_fomc__signal_outside_orb__prior_not_inside_day | curve | 157 | 111.07 | 9.844 | 1.986 | -11.28 | -4.9 | 129.38 | 0.965 | exclude_fomc\|signal_outside_orb\|prior_not_inside_day |
| combo__signal_outside_orb__prior_not_inside_day | cliff | 160 | 108.07 | 9.578 | 1.934 | -11.28 | -7.9 | 120.38 | 0 | signal_outside_orb\|prior_not_inside_day |
| combo__exclude_fomc__contained_asia_breakout | cliff | 111 | 80.64 | 5.193 | 1.998 | -15.53 | -35.33 | 80.61 | 0 | exclude_fomc\|contained_asia_breakout |
| combo__exclude_fomc__signal_outside_orb__contained_asia_breakout | curve | 111 | 80.64 | 5.193 | 1.998 | -15.53 | -35.33 | 80.61 | 1 | exclude_fomc\|signal_outside_orb\|contained_asia_breakout |
| combo__exclude_fomc__prior_not_inside_day__contained_asia_breakout | curve | 99 | 73.13 | 5.837 | 2.022 | -12.53 | -42.84 | 73.88 | 0.901 | exclude_fomc\|prior_not_inside_day\|contained_asia_breakout |
| combo__exclude_fomc__signal_outside_orb__prior_not_inside_day__contained_asia_breakout | curve | 99 | 73.13 | 5.837 | 2.022 | -12.53 | -42.84 | 73.88 | 0.95 | exclude_fomc\|signal_outside_orb\|prior_not_inside_day\|contained_asia_breakout |
| combo__signal_outside_orb__contained_asia_breakout | cliff | 114 | 77.64 | 4.429 | 1.926 | -17.53 | -38.33 | 73.61 | 0 | signal_outside_orb\|contained_asia_breakout |
| combo__signal_outside_orb__orb_high | cliff | 64 | 65.85 | 5.85 | 2.485 | -11.26 | -50.12 | 81.43 | 0 | signal_outside_orb\|orb_high |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_skip_medium_vol",
  "base_variant": "prev_curve_net__combo__rr7p0_tp0p8__dow_none__gap_atr_1p0__wide_t12p5_rr3__icf_on__pre_cancel_tp1__flat_1330",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": 5.0,
      "gate_id": "exclude_fomc",
      "label": "exclude FOMC dates",
      "last1_calmar": 8.641,
      "last1_net_r": 120.97
    },
    "custom_day_type": {
      "delta_last1_net_r": -38.33,
      "gate_id": "contained_asia_breakout",
      "label": "NY opens inside Asia range and signal closes outside ORB",
      "last1_calmar": 4.429,
      "last1_net_r": 77.64
    },
    "hunter_proxy": {
      "delta_last1_net_r": -3.38,
      "gate_id": "signal_outside_orb",
      "label": "signal close outside ORB edge",
      "last1_calmar": 8.523,
      "last1_net_r": 112.59
    },
    "orb_size": {
      "delta_last1_net_r": -51.12,
      "gate_id": "orb_high",
      "label": "only high ORB range pctile >= 67%",
      "last1_calmar": 5.291,
      "last1_net_r": 64.85
    },
    "prior_day": {
      "delta_last1_net_r": -5.99,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 9.165,
      "last1_net_r": 109.98
    }
  }
}
```

</details>

## ES Asia ORB

Baseline after existing `gate_skip_sideways_high_vol` gate: 205 fills, `61.07R`, Calmar `8.274`, PF `1.683`, DD `-7.38R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| orb_size | orb_not_extreme | 150 | 56.87 | 11.567 | 1.925 | -4.92 | -4.2 | 39.63 | exclude extreme ORB range pctile >= 80% |
| calendar_news | exclude_fomc | 196 | 58.84 | 7.973 | 1.689 | -7.38 | -2.23 | 40.3 | exclude FOMC dates |
| orb_size | orb_not_high | 130 | 48.11 | 10.552 | 1.9 | -4.56 | -12.96 | 48.99 | exclude high ORB range pctile |
| prior_day | prior_not_inside_day | 194 | 56.87 | 8.412 | 1.673 | -6.76 | -4.2 | 37.31 | exclude inside day |
| calendar_news | exclude_cpi_nfp | 186 | 56.71 | 7.308 | 1.715 | -7.76 | -4.36 | 39.43 | exclude CPI and NFP dates |
| calendar_news | exclude_bom3 | 188 | 54.02 | 6.086 | 1.659 | -8.88 | -7.05 | 44.89 | exclude day-of-month 1-3 |
| calendar_news | exclude_news | 174 | 53.45 | 6.889 | 1.72 | -7.76 | -7.62 | 36.04 | exclude FOMC/CPI/NFP/PPI dates |
| calendar_news | exclude_eom5 | 164 | 48.43 | 6.828 | 1.664 | -7.09 | -12.64 | 20.84 | exclude day-of-month >= 25 |
| hunter_proxy | signal_outside_orb | 148 | 39.37 | 7.065 | 1.591 | -5.57 | -21.7 | 33.19 | signal close outside ORB edge |
| orb_size | orb_mid | 70 | 30.95 | 7.197 | 2.177 | -4.3 | -30.12 | 41.03 | only mid ORB range pctile 33-67% |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__orb_not_extreme__exclude_fomc | cliff | 143 | 55.34 | 14.636 | 1.947 | -3.78 | -5.73 | 37.68 | 0 | orb_not_extreme\|exclude_fomc |
| combo__orb_not_extreme__exclude_fomc__prior_not_inside_day | soft_curve | 134 | 50.81 | 14.768 | 1.934 | -3.44 | -10.26 | 33.63 | 0.721 | orb_not_extreme\|exclude_fomc\|prior_not_inside_day |
| combo__orb_not_extreme__prior_not_inside_day | cliff | 141 | 52.34 | 10.645 | 1.911 | -4.92 | -8.73 | 35.57 | 0 | orb_not_extreme\|prior_not_inside_day |
| combo__exclude_fomc__prior_not_inside_day | cliff | 185 | 54.65 | 8.083 | 1.679 | -6.76 | -6.42 | 34.93 | 0 | exclude_fomc\|prior_not_inside_day |
| combo__orb_not_extreme__signal_outside_orb | cliff | 114 | 38.67 | 7.733 | 1.784 | -5 | -22.4 | 29.97 | 0 | orb_not_extreme\|signal_outside_orb |
| combo__orb_not_extreme__exclude_fomc__signal_outside_orb | curve | 108 | 37.57 | 7.514 | 1.81 | -5 | -23.5 | 28.45 | 1.029 | orb_not_extreme\|exclude_fomc\|signal_outside_orb |
| combo__orb_not_extreme__prior_not_inside_day__signal_outside_orb | curve | 107 | 37.54 | 7.508 | 1.829 | -5 | -23.53 | 27.37 | 1.03 | orb_not_extreme\|prior_not_inside_day\|signal_outside_orb |
| combo__exclude_fomc__signal_outside_orb | cliff | 140 | 37.58 | 6.743 | 1.6 | -5.57 | -23.49 | 30.24 | 0 | exclude_fomc\|signal_outside_orb |
| combo__orb_not_extreme__exclude_fomc__prior_not_inside_day__signal_outside_orb | curve | 101 | 36.44 | 7.289 | 1.862 | -5 | -24.63 | 25.85 | 1.03 | orb_not_extreme\|exclude_fomc\|prior_not_inside_day\|signal_outside_orb |
| combo__prior_not_inside_day__signal_outside_orb | cliff | 139 | 38.58 | 5.154 | 1.625 | -7.49 | -22.49 | 30.22 | 0 | prior_not_inside_day\|signal_outside_orb |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_skip_sideways_high_vol",
  "base_variant": "prev_curve_net__combo__rr2p0_tp0p7__stop_orb_75p0__gap_atr_0p375__dow_exMon__flat_0600__atr10__wide_t12p5_rr1p5",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": -2.23,
      "gate_id": "exclude_fomc",
      "label": "exclude FOMC dates",
      "last1_calmar": 7.973,
      "last1_net_r": 58.84
    },
    "custom_day_type": {
      "delta_last1_net_r": -33.96,
      "gate_id": "momentum_carry",
      "label": "prior trend and prior close extreme align",
      "last1_calmar": 9.038,
      "last1_net_r": 27.11
    },
    "hunter_proxy": {
      "delta_last1_net_r": -21.7,
      "gate_id": "signal_outside_orb",
      "label": "signal close outside ORB edge",
      "last1_calmar": 7.065,
      "last1_net_r": 39.37
    },
    "orb_size": {
      "delta_last1_net_r": -4.2,
      "gate_id": "orb_not_extreme",
      "label": "exclude extreme ORB range pctile >= 80%",
      "last1_calmar": 11.567,
      "last1_net_r": 56.87
    },
    "prior_day": {
      "delta_last1_net_r": -4.2,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 8.412,
      "last1_net_r": 56.87
    }
  }
}
```

</details>

## ES NY LSI

Baseline after existing `gate_skip_high_vol` gate: 29 fills, `21.31R`, Calmar `15.499`, PF `3.666`, DD `-1.38R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prior_day | prior_not_inside_day | 27 | 21.76 | 21.755 | 4.121 | -1 | 0.44 | 14.48 | exclude inside day |
| calendar_news | exclude_bom3 | 27 | 18.98 | 18.978 | 3.697 | -1 | -2.33 | 12.9 | exclude day-of-month 1-3 |
| prior_day | prior_trend_aligned | 13 | 15.37 | 15.367 | 9.071 | -1 | -5.94 | 10 | prior RTH trend aligns with trade direction |
| calendar_news | exclude_fomc | 29 | 21.31 | 15.499 | 3.666 | -1.38 | 0 | 13.24 | exclude FOMC dates |
| prior_day | prior_range_low | 13 | 14.29 | 14.29 | 7.781 | -1 | -7.02 | 12.58 | only low prior-day range pctile <= 33% |
| hunter_proxy | signal_close_strong_65 | 24 | 17.48 | 16.137 | 3.5 | -1.08 | -3.83 | 9.16 | signal closes in directional 65% of candle |
| hunter_proxy | adverse_wick_le_35 | 24 | 17.48 | 16.137 | 3.5 | -1.08 | -3.83 | 9.16 | adverse wick <= 35% |
| calendar_news | exclude_cpi_nfp | 25 | 16.39 | 16.394 | 3.357 | -1 | -4.92 | 11.32 | exclude CPI and NFP dates |
| session_context | asia_trend_aligned | 15 | 13.9 | 13.896 | 4.454 | -1 | -7.42 | 13.57 | NY only: Asia trend aligns with trade |
| hunter_proxy | signal_close_strong_80 | 20 | 13.97 | 13.97 | 3.269 | -1 | -7.34 | 8.02 | signal closes in directional 80% of candle |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__prior_not_inside_day__exclude_bom3 | cliff | 25 | 19.42 | 19.422 | 4.23 | -1 | -1.89 | 14.14 | 0 | prior_not_inside_day\|exclude_bom3 |
| combo__prior_not_inside_day__exclude_bom3__orb_not_high | curve | 21 | 17.03 | 17.033 | 3.82 | -1 | -4.28 | 11.28 | 1 | prior_not_inside_day\|exclude_bom3\|orb_not_high |
| combo__exclude_bom3__orb_not_high | cliff | 21 | 17.03 | 17.033 | 3.82 | -1 | -4.28 | 10.91 | 0 | exclude_bom3\|orb_not_high |
| combo__prior_not_inside_day__asia_trend_aligned | cliff | 14 | 13.34 | 13.34 | 4.316 | -1 | -7.97 | 11.81 | 0 | prior_not_inside_day\|asia_trend_aligned |
| combo__exclude_bom3__signal_close_strong_65 | cliff | 22 | 15.15 | 13.983 | 3.509 | -1.08 | -6.16 | 7.82 | 0 | exclude_bom3\|signal_close_strong_65 |
| combo__prior_not_inside_day__exclude_bom3__signal_close_strong_65 | curve | 21 | 14.59 | 13.471 | 3.417 | -1.08 | -6.72 | 8.69 | 1.038 | prior_not_inside_day\|exclude_bom3\|signal_close_strong_65 |
| combo__prior_not_inside_day__signal_close_strong_65 | cliff | 23 | 16.93 | 12.12 | 3.421 | -1.4 | -4.38 | 10.02 | 0 | prior_not_inside_day\|signal_close_strong_65 |
| combo__exclude_bom3__asia_trend_aligned | cliff | 13 | 11.56 | 11.563 | 4.774 | -1 | -9.75 | 11.24 | 0 | exclude_bom3\|asia_trend_aligned |
| combo__prior_not_inside_day__orb_not_high | cliff | 22 | 16.03 | 11.661 | 3.293 | -1.38 | -5.28 | 9.28 | 0 | prior_not_inside_day\|orb_not_high |
| combo__prior_not_inside_day__exclude_bom3__asia_trend_aligned | curve | 12 | 11.01 | 11.007 | 4.593 | -1 | -10.3 | 9.48 | 1.212 | prior_not_inside_day\|exclude_bom3\|asia_trend_aligned |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_skip_high_vol",
  "base_variant": "prev_curve_net__combo__dow_exWed__fvgL7_R3__rr5p0_tp0p25__stop_struct_75pct__atr14__lag16__entry_1400",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": -2.33,
      "gate_id": "exclude_bom3",
      "label": "exclude day-of-month 1-3",
      "last1_calmar": 18.978,
      "last1_net_r": 18.98
    },
    "hunter_proxy": {
      "delta_last1_net_r": -3.83,
      "gate_id": "signal_close_strong_65",
      "label": "signal closes in directional 65% of candle",
      "last1_calmar": 16.137,
      "last1_net_r": 17.48
    },
    "orb_size": {
      "delta_last1_net_r": -5.28,
      "gate_id": "orb_not_high",
      "label": "exclude high ORB range pctile",
      "last1_calmar": 11.661,
      "last1_net_r": 16.03
    },
    "prior_day": {
      "delta_last1_net_r": 0.44,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 21.755,
      "last1_net_r": 21.76
    },
    "session_context": {
      "delta_last1_net_r": -7.42,
      "gate_id": "asia_trend_aligned",
      "label": "NY only: Asia trend aligns with trade",
      "last1_calmar": 13.896,
      "last1_net_r": 13.9
    }
  }
}
```

</details>

## GC NY ORB

Baseline after existing `gate_skip_sideways_medium_vol` gate: 43 fills, `56.99R`, Calmar `11.398`, PF `2.884`, DD `-5.0R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendar_news | exclude_cpi_nfp | 36 | 63.99 | 14.967 | 3.71 | -4.28 | 7 | 55.57 | exclude CPI and NFP dates |
| orb_size | orb_not_extreme | 33 | 55.19 | 12.909 | 3.511 | -4.28 | -1.8 | 61.87 | exclude extreme ORB range pctile >= 80% |
| hunter_proxy | signal_outside_orb | 42 | 57.99 | 11.598 | 2.982 | -5 | 1 | 63.55 | signal close outside ORB edge |
| calendar_news | exclude_fomc | 43 | 56.99 | 11.398 | 2.884 | -5 | 0 | 62.55 | exclude FOMC dates |
| calendar_news | exclude_eom5 | 33 | 53.91 | 13.477 | 3.392 | -4 | -3.08 | 48.71 | exclude day-of-month >= 25 |
| calendar_news | exclude_news | 35 | 55.25 | 11.051 | 3.345 | -5 | -1.74 | 50.88 | exclude FOMC/CPI/NFP/PPI dates |
| calendar_news | exclude_bom3 | 39 | 49.19 | 11.505 | 2.773 | -4.28 | -7.8 | 51.91 | exclude day-of-month 1-3 |
| prior_day | prior_not_inside_day | 39 | 37.25 | 7.45 | 2.309 | -5 | -19.74 | 44.81 | exclude inside day |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__exclude_cpi_nfp__signal_outside_orb | cliff | 36 | 63.99 | 14.967 | 3.71 | -4.28 | 7 | 57.57 | 0 | exclude_cpi_nfp\|signal_outside_orb |
| combo__orb_not_extreme__signal_outside_orb | cliff | 32 | 56.19 | 13.143 | 3.678 | -4.28 | -0.8 | 63.87 | 0 | orb_not_extreme\|signal_outside_orb |
| combo__exclude_cpi_nfp__signal_outside_orb__prior_not_inside_day | curve | 32 | 44.25 | 11.062 | 3.032 | -4 | -12.74 | 41.83 | 1 | exclude_cpi_nfp\|signal_outside_orb\|prior_not_inside_day |
| combo__exclude_cpi_nfp__prior_not_inside_day | cliff | 32 | 44.25 | 11.062 | 3.032 | -4 | -12.74 | 39.83 | 0 | exclude_cpi_nfp\|prior_not_inside_day |
| combo__signal_outside_orb__prior_not_inside_day | cliff | 38 | 38.25 | 7.65 | 2.393 | -5 | -18.74 | 47.81 | 0 | signal_outside_orb\|prior_not_inside_day |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_skip_sideways_medium_vol",
  "base_variant": "prev_curve_net__combo__rr12p0_tp0p8__atr5__entry_end_1130__gap_orb_20p0__stop_atr_3p0__flat_1550__dow_none",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": 7.0,
      "gate_id": "exclude_cpi_nfp",
      "label": "exclude CPI and NFP dates",
      "last1_calmar": 14.967,
      "last1_net_r": 63.99
    },
    "hunter_proxy": {
      "delta_last1_net_r": 1.0,
      "gate_id": "signal_outside_orb",
      "label": "signal close outside ORB edge",
      "last1_calmar": 11.598,
      "last1_net_r": 57.99
    },
    "orb_size": {
      "delta_last1_net_r": -1.8,
      "gate_id": "orb_not_extreme",
      "label": "exclude extreme ORB range pctile >= 80%",
      "last1_calmar": 12.909,
      "last1_net_r": 55.19
    },
    "prior_day": {
      "delta_last1_net_r": -19.74,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 7.45,
      "last1_net_r": 37.25
    }
  }
}
```

</details>

## GC Asia ORB

Baseline after existing `gate_skip_medium_vol` gate: 101 fills, `62.44R`, Calmar `12.487`, PF `2.253`, DD `-5.0R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendar_news | exclude_cpi_nfp | 99 | 64.44 | 12.887 | 2.34 | -5 | 2 | 49.1 | exclude CPI and NFP dates |
| prior_day | prior_not_inside_day | 96 | 63.74 | 12.747 | 2.385 | -5 | 1.3 | 47.7 | exclude inside day |
| hunter_proxy | signal_outside_orb | 101 | 62.44 | 12.487 | 2.253 | -5 | 0 | 45.3 | signal close outside ORB edge |
| calendar_news | exclude_bom3 | 92 | 60.32 | 12.064 | 2.358 | -5 | -2.12 | 44.49 | exclude day-of-month 1-3 |
| calendar_news | exclude_news | 92 | 56.61 | 9.435 | 2.256 | -6 | -5.83 | 41.38 | exclude FOMC/CPI/NFP/PPI dates |
| calendar_news | exclude_fomc | 96 | 56.34 | 9.389 | 2.177 | -6 | -6.1 | 38.5 | exclude FOMC dates |
| orb_size | orb_not_extreme | 66 | 45.7 | 11.426 | 2.408 | -4 | -16.73 | 34.66 | exclude extreme ORB range pctile >= 80% |
| calendar_news | exclude_eom5 | 82 | 48.29 | 9.658 | 2.155 | -5 | -14.15 | 22.23 | exclude day-of-month >= 25 |
| prior_day | prior_trend_fade | 66 | 39.03 | 9.758 | 2.198 | -4 | -23.4 | 26.27 | prior RTH trend opposes trade direction |
| session_context | asia_prior_rth_fade | 66 | 39.03 | 9.758 | 2.198 | -4 | -23.4 | 26.27 | Asia: fade prior RTH trend |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__exclude_cpi_nfp__prior_not_inside_day | cliff | 94 | 65.74 | 13.147 | 2.485 | -5 | 3.3 | 52.5 | 0 | exclude_cpi_nfp\|prior_not_inside_day |
| combo__exclude_cpi_nfp__prior_not_inside_day__signal_outside_orb | curve | 94 | 65.74 | 13.147 | 2.485 | -5 | 3.3 | 52.5 | 0.98 | exclude_cpi_nfp\|prior_not_inside_day\|signal_outside_orb |
| combo__exclude_cpi_nfp__signal_outside_orb | cliff | 99 | 64.44 | 12.887 | 2.34 | -5 | 2 | 50.1 | 0 | exclude_cpi_nfp\|signal_outside_orb |
| combo__prior_not_inside_day__signal_outside_orb | cliff | 96 | 63.74 | 12.747 | 2.385 | -5 | 1.3 | 47.7 | 0 | prior_not_inside_day\|signal_outside_orb |
| combo__exclude_cpi_nfp__prior_not_inside_day__orb_not_extreme | curve | 62 | 49.7 | 12.426 | 2.737 | -4 | -12.73 | 41.76 | 0.96 | exclude_cpi_nfp\|prior_not_inside_day\|orb_not_extreme |
| combo__exclude_cpi_nfp__prior_not_inside_day__signal_outside_orb__orb_not_extreme | curve | 62 | 49.7 | 12.426 | 2.737 | -4 | -12.73 | 41.76 | 0.98 | exclude_cpi_nfp\|prior_not_inside_day\|signal_outside_orb\|orb_not_extreme |
| combo__exclude_cpi_nfp__orb_not_extreme | cliff | 64 | 47.7 | 11.926 | 2.555 | -4 | -14.73 | 39.66 | 0 | exclude_cpi_nfp\|orb_not_extreme |
| combo__exclude_cpi_nfp__signal_outside_orb__orb_not_extreme | curve | 64 | 47.7 | 11.926 | 2.555 | -4 | -14.73 | 39.66 | 1 | exclude_cpi_nfp\|signal_outside_orb\|orb_not_extreme |
| combo__prior_not_inside_day__orb_not_extreme | cliff | 64 | 47.7 | 11.926 | 2.569 | -4 | -14.73 | 36.76 | 0 | prior_not_inside_day\|orb_not_extreme |
| combo__prior_not_inside_day__signal_outside_orb__orb_not_extreme | curve | 64 | 47.7 | 11.926 | 2.569 | -4 | -14.73 | 36.76 | 1 | prior_not_inside_day\|signal_outside_orb\|orb_not_extreme |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_skip_medium_vol",
  "base_variant": "prev_curve_net__combo__rr3p0_tp0p8__pre_cancel_tp2__stop_atr_3p0__gap_atr_1p0__orb10m__wide_t15_rr1__entry_end_2300",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": 2.0,
      "gate_id": "exclude_cpi_nfp",
      "label": "exclude CPI and NFP dates",
      "last1_calmar": 12.887,
      "last1_net_r": 64.44
    },
    "hunter_proxy": {
      "delta_last1_net_r": 0.0,
      "gate_id": "signal_outside_orb",
      "label": "signal close outside ORB edge",
      "last1_calmar": 12.487,
      "last1_net_r": 62.44
    },
    "orb_size": {
      "delta_last1_net_r": -16.73,
      "gate_id": "orb_not_extreme",
      "label": "exclude extreme ORB range pctile >= 80%",
      "last1_calmar": 11.426,
      "last1_net_r": 45.7
    },
    "prior_day": {
      "delta_last1_net_r": 1.3,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 12.747,
      "last1_net_r": 63.74
    },
    "session_context": {
      "delta_last1_net_r": -23.4,
      "gate_id": "asia_prior_rth_fade",
      "label": "Asia: fade prior RTH trend",
      "last1_calmar": 9.758,
      "last1_net_r": 39.03
    }
  }
}
```

</details>

## GC NY LSI

Baseline after existing `gate_skip_high_vol` gate: 12 fills, `4.12R`, Calmar `3.82`, PF `3.302`, DD `-1.08R`.

### Best OAT Gates

| family | gate_id | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| calendar_news | exclude_fomc | 11 | 5.12 | 4.797 | 4.767 | -1.07 | 1 | 7.65 | exclude FOMC dates |
| hunter_proxy | signal_close_strong_65 | 10 | 3.94 | 3.697 | 3.952 | -1.07 | -0.17 | 5.73 | signal closes in directional 65% of candle |
| hunter_proxy | adverse_wick_le_35 | 10 | 3.94 | 3.697 | 3.952 | -1.07 | -0.17 | 5.73 | adverse wick <= 35% |
| calendar_news | exclude_cpi_nfp | 12 | 4.12 | 3.82 | 3.302 | -1.08 | 0 | 6.55 | exclude CPI and NFP dates |
| prior_day | prior_not_inside_day | 11 | 4.05 | 3.758 | 3.269 | -1.08 | -0.07 | 5.29 | exclude inside day |
| calendar_news | exclude_eom5 | 10 | 3.17 | 2.943 | 2.776 | -1.08 | -0.94 | 6.7 | exclude day-of-month >= 25 |
| session_context | asia_trend_aligned | 10 | 3.66 | 3.395 | 3.114 | -1.08 | -0.46 | 2.52 | NY only: Asia trend aligns with trade |
| calendar_news | exclude_news | 10 | 2.84 | 2.664 | 2.827 | -1.07 | -1.28 | 5.27 | exclude FOMC/CPI/NFP/PPI dates |
| calendar_news | exclude_bom3 | 10 | 2.92 | 2.647 | 2.729 | -1.1 | -1.2 | 3.59 | exclude day-of-month 1-3 |
| orb_size | orb_not_extreme | 8 | 2.6 | 2.601 | 2.638 | -1 | -1.52 | 4.84 | exclude extreme ORB range pctile >= 80% |

### Best Combos

| gate_id | surface | last1_fills | last1_net_r | last1_calmar | last1_pf | last1_dd_r | delta_last1_net_r | last2_net_r | plateau_ratio | component_gates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo__exclude_fomc__prior_not_inside_day | cliff | 10 | 5.05 | 4.734 | 4.718 | -1.07 | 0.93 | 6.29 | 0 | exclude_fomc\|prior_not_inside_day |
| combo__exclude_fomc__asia_trend_aligned | cliff | 9 | 4.66 | 4.658 | 4.563 | -1 | 0.54 | 3.52 | 0 | exclude_fomc\|asia_trend_aligned |
| combo__exclude_fomc__prior_not_inside_day__asia_trend_aligned | curve | 8 | 4.59 | 4.591 | 4.512 | -1 | 0.47 | 3.45 | 1.015 | exclude_fomc\|prior_not_inside_day\|asia_trend_aligned |
| combo__exclude_fomc__signal_close_strong_65 | cliff | 10 | 3.94 | 3.697 | 3.952 | -1.07 | -0.17 | 5.73 | 0 | exclude_fomc\|signal_close_strong_65 |
| combo__signal_close_strong_65__prior_not_inside_day | cliff | 9 | 3.88 | 3.634 | 3.903 | -1.07 | -0.24 | 5.66 | 0 | signal_close_strong_65\|prior_not_inside_day |
| combo__exclude_fomc__signal_close_strong_65__prior_not_inside_day | curve | 9 | 3.88 | 3.634 | 3.903 | -1.07 | -0.24 | 5.66 | 1.017 | exclude_fomc\|signal_close_strong_65\|prior_not_inside_day |
| combo__signal_close_strong_65__asia_trend_aligned | cliff | 8 | 3.48 | 3.485 | 3.708 | -1 | -0.63 | 2.9 | 0 | signal_close_strong_65\|asia_trend_aligned |
| combo__exclude_fomc__signal_close_strong_65__asia_trend_aligned | curve | 8 | 3.48 | 3.485 | 3.708 | -1 | -0.63 | 2.9 | 1.061 | exclude_fomc\|signal_close_strong_65\|asia_trend_aligned |
| combo__prior_not_inside_day__asia_trend_aligned | cliff | 9 | 3.59 | 3.333 | 3.079 | -1.08 | -0.53 | 2.45 | 0 | prior_not_inside_day\|asia_trend_aligned |

<details><summary>Selected family gates for combo search</summary>

```json
{
  "base_gate": "gate_skip_high_vol",
  "base_variant": "prev_curve_calmar__combo__dow_none__nL10__mode_timed_hybrid_60__rr3p5_tp0p3__stop_struct_75pct__entry_1530__atr5",
  "families": {
    "calendar_news": {
      "delta_last1_net_r": 1.0,
      "gate_id": "exclude_fomc",
      "label": "exclude FOMC dates",
      "last1_calmar": 4.797,
      "last1_net_r": 5.12
    },
    "hunter_proxy": {
      "delta_last1_net_r": -0.17,
      "gate_id": "signal_close_strong_65",
      "label": "signal closes in directional 65% of candle",
      "last1_calmar": 3.697,
      "last1_net_r": 3.94
    },
    "orb_size": {
      "delta_last1_net_r": -1.52,
      "gate_id": "orb_not_extreme",
      "label": "exclude extreme ORB range pctile >= 80%",
      "last1_calmar": 2.601,
      "last1_net_r": 2.6
    },
    "prior_day": {
      "delta_last1_net_r": -0.07,
      "gate_id": "prior_not_inside_day",
      "label": "exclude inside day",
      "last1_calmar": 3.758,
      "last1_net_r": 4.05
    },
    "session_context": {
      "delta_last1_net_r": -0.46,
      "gate_id": "asia_trend_aligned",
      "label": "NY only: Asia trend aligns with trade",
      "last1_calmar": 3.395,
      "last1_net_r": 3.66
    }
  }
}
```

</details>

## Read

- A positive `delta_r` means the structural gate improved the already-gated hot baseline over the last-year window.
- Combo `surface` is a leave-one-gate stability check. `curve` means most drop-one variants retained the candidate Calmar; `cliff` means the combo depends heavily on all filters being stacked.
- The gates are post-trade structural filters, so they identify candidate context variables before we hard-code anything into the engine or live execution config.
