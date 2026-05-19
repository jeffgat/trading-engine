# NQ NY LSI Corrected Candidate Retest - 2026-05-16

- Objective: retest serious NQ NY LSI / HTF-LSI challengers after the stale HTF-level invalidation correction.
- Scope: research-engine comparison through `2026-05-01`; exact live replay is still required before promoting any new live slot.
- Baseline: `current_active_htf_lag24`, matching the current `ALPHA_V1` HTF-LSI slot.

## Verdict

- No challenger cleanly dethrones the current `ALPHA_V1` HTF-LSI slot on all-weather evidence.
- Best practical tweak: add the live-supported `block_bear_high_vol` regime gate to the current slot. Exact replay improves the recent windows and holdout, but gives up full-history R.
- Best research-only upgrade: `current + 15m EQHL tol1`. It slightly improves full-history research Calmar and drawdown, but execution does not support additive EQHL yet and holdout is effectively unchanged.
- Do not promote the `2m` anchor, standalone EQHL, or wide `60m EQHL 15pt` branches. They fail recent quality, live support, or both.

## Exact Live-Native Challenger Replay

These rows were replayed through the live execution engine after the research screen. Baseline is the corrected exact `ALPHA_V1` HTF-LSI slot from `NQ_NY_HTF_LSI_LAG24_EXACT_REPLAY.md`.

| Exact Candidate | Full Trades | Full PF | Full R | Full DD | Full Calmar | Holdout Trades | Holdout PF | Holdout R | Holdout DD | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Current slot | 394 | 1.470 | +82.34 | -8.00R | 10.29 | 29 | 2.096 | +11.75 | -3.00R | Keep as default |
| Current + block_bear_high_vol | 340 | 1.532 | +78.73 | -8.00R | 9.84 | 28 | 2.285 | +12.75 | -3.00R | Conditional risk-quality tweak |
| Old exit/window lag24 | 447 | 1.321 | +71.72 | -9.75R | 7.36 | 33 | 2.282 | +14.02 | -3.00R | Better recent R, worse all-weather |
| gap2.5 / lag30 / current exit | 431 | 1.454 | +83.76 | -10.00R | 8.38 | 35 | 2.009 | +11.82 | -4.00R | More flow, worse DD/Calmar |

Exact output: `backtesting/data/results/nq_ny_lsi_corrected_candidate_retest_20260516/exact_live_native_challengers.json`.

## Holdout Ranking

| Candidate | Deployability | Holdout Trades | Holdout PF | Holdout R | Holdout DD | Full R | Full DD | Full Calmar | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| gap25_right3_lag0_skip_bear_old_exit | post_filter_only | 43 | 1.932 | +14.07 | -3.75R | +69.36 | -10.79R | 6.43 | Higher-count sibling as originally studied. |
| old_exit_lag24_htf_only | live_native | 33 | 2.121 | +13.66 | -3.00R | +67.25 | -10.14R | 6.63 | Prior frozen lag24 exit/window shape. |
| gap25_right3_lag0_skip_bear_current_exit | post_filter_only | 37 | 2.176 | +13.60 | -4.05R | +75.29 | -10.00R | 7.53 | Higher-count sibling normalized to current exit/window. |
| gap25_right2_lag0_skip_bear_old_exit | post_filter_only | 37 | 1.945 | +12.87 | -3.12R | +70.96 | -10.79R | 6.58 | Count challenger as originally studied. |
| current_plus_5m_eqhl_tol1 | research_only | 31 | 1.986 | +12.04 | -3.00R | +93.44 | -11.18R | 8.36 | Additive EQHL lower-DD alternate; execution unsupported. |
| current_active_htf_lag24_skip_bear | post_filter_only | 28 | 2.224 | +11.93 | -3.00R | +77.60 | -8.00R | 9.70 | Same current slot, post-filtered to skip bear_high_vol. |
| gap25_right2_lag0_skip_bear_current_exit | post_filter_only | 33 | 2.083 | +11.92 | -3.12R | +75.66 | -10.00R | 7.57 | Count challenger normalized to current exit/window. |
| current_plus_15m_eqhl_tol1 | research_only | 29 | 1.995 | +10.93 | -3.00R | +83.05 | -7.93R | 10.47 | Additive EQHL preferred research upgrade; execution unsupported. |
| current_active_htf_lag24 | live_native | 29 | 1.995 | +10.93 | -3.00R | +80.50 | -8.26R | 9.75 | Current ALPHA_V1 slot. |
| gap25_right2_lag30_current_exit | live_native | 35 | 1.788 | +10.85 | -4.00R | +81.99 | -10.00R | 8.20 | Higher-flow late-lag variant normalized to current exit/window. |
| current_plus_60m_eqhl_15pt | research_only | 38 | 1.332 | +5.38 | -3.00R | +89.80 | -9.39R | 9.56 | Wide additive challenger; execution unsupported. |
| standalone_5m_eqhl_lsi | research_only | 9 | 1.655 | +4.39 | -2.00R | +40.27 | -11.26R | 3.58 | Standalone EQHL-LSI phase-one challenger; execution unsupported. |
| secondary_2m_anchor | research_only | 63 | 0.811 | -6.89 | -12.79R | +62.90 | -16.92R | 3.72 | 2m secondary anchor; exact/live plumbing not validated in ALPHA. |

## Full / 10Y / 2Y / 1Y Snapshot

| Candidate | Full R | 10Y R | 2Y R | 1Y R | Full PF | 10Y PF | 2Y PF | 1Y PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gap25_right3_lag0_skip_bear_old_exit | +69.36 | +71.14 | +25.39 | +18.07 | 1.328 | 1.350 | 1.786 | 2.553 |
| old_exit_lag24_htf_only | +67.25 | +67.74 | +21.82 | +17.66 | 1.326 | 1.338 | 1.795 | 3.048 |
| gap25_right3_lag0_skip_bear_current_exit | +75.29 | +77.53 | +25.17 | +15.90 | 1.433 | 1.467 | 1.948 | 2.679 |
| gap25_right2_lag0_skip_bear_old_exit | +70.96 | +73.64 | +23.63 | +16.87 | 1.358 | 1.387 | 1.787 | 2.684 |
| current_plus_5m_eqhl_tol1 | +93.44 | +96.35 | +22.09 | +14.34 | 1.437 | 1.471 | 1.731 | 2.427 |
| current_active_htf_lag24_skip_bear | +77.60 | +79.26 | +21.57 | +14.23 | 1.554 | 1.586 | 1.988 | 2.885 |
| gap25_right2_lag0_skip_bear_current_exit | +75.66 | +77.60 | +23.19 | +14.22 | 1.466 | 1.498 | 1.930 | 2.604 |
| current_plus_15m_eqhl_tol1 | +83.05 | +85.00 | +20.30 | +13.23 | 1.457 | 1.487 | 1.803 | 2.498 |
| current_active_htf_lag24 | +80.50 | +81.47 | +20.07 | +13.23 | 1.490 | 1.510 | 1.832 | 2.498 |
| gap25_right2_lag30_current_exit | +81.99 | +83.22 | +21.63 | +14.15 | 1.443 | 1.466 | 1.750 | 2.384 |
| current_plus_60m_eqhl_15pt | +89.80 | +92.46 | +17.52 | +7.68 | 1.385 | 1.414 | 1.482 | 1.515 |
| standalone_5m_eqhl_lsi | +40.27 | +42.52 | +8.80 | +5.39 | 1.340 | 1.383 | 1.678 | 2.186 |
| secondary_2m_anchor | +62.90 | +64.69 | -4.49 | -2.89 | 1.194 | 1.207 | 0.984 | 0.905 |
