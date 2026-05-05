# HOT_REGIME_V1 Exact Candidate Compare

- Run slug: `hot_regime_v1_exact_candidate_compare_20260503`
- Window: `2025-03-24` to `2026-03-24`
- Baseline current HOT full replay source: existing exact result from `hot_regime_v1_exact_compare_20260503`.
- Candidate exact replay source: temporary in-memory execution profiles; `execution/config/exec_configs.json` was not edited.
- Post-filter rows are explicitly not live-native exact replays; they remove exact fills after the lifecycle has already happened.

## Gate Support

| candidate | status | method |
| --- | --- | --- |
| NQ NY ORB exclude CPI | exact-native | temporary excluded_dates on NQ_NY |
| ES NY ORB exclude FOMC+CPI | exact-native | temporary excluded_dates on ES_NY |
| GC NY ORB exclude CPI/NFP | exact-native | temporary excluded_dates on GC_NY |
| GC NY ORB cpi_nfp_plus_outside | skipped | signal-outside-ORB is not a live-native gate and exact fill records do not preserve signal-bar close/ORB context |
| GC Asia ORB CPI/NFP + prior-not-inside | mixed | CPI/NFP exact-native; prior-not-inside is post-filter-only |

## Full Portfolio Exact-Native Deltas

| session | gate | current_fills | candidate_fills | delta_fills | current_net_r | candidate_net_r | delta_net_r | current_dd_r | candidate_dd_r | current_calmar | candidate_calmar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ_NY | exclude_cpi | 68 | 66 | -2 | -3.0 | 5.4 | 8.4 | -25.4 | -21.8 | -0.118 | 0.248 |
| ES_NY | exclude_fomc_cpi | 92 | 80 | -12 | 16.4 | 15.46 | -0.94 | -12.69 | -10.5 | 1.292 | 1.473 |
| GC_NY | exclude_cpi_nfp | 22 | 17 | -5 | 13.4 | 18.4 | 5.0 | -10.0 | -8.0 | 1.34 | 2.3 |
| GC_Asia | exclude_cpi_nfp native; cpi_nfp_plus_not_inside post-filter | 60 | 59 | -1 | 31.7 | 36.4 | 4.7 | -6.0 | -5.0 | 5.283 | 7.28 |

## Single-Leg Exact-Native Deltas

| session | gate | current_fills | candidate_fills | delta_fills | current_net_r | candidate_net_r | delta_net_r | current_dd_r | candidate_dd_r | current_calmar | candidate_calmar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ_NY | exclude_cpi | 116 | 113 | -3 | 22.2 | 18.8 | -3.4 | -19.4 | -19.4 | 1.144 | 0.969 |
| ES_NY | exclude_fomc_cpi | 153 | 145 | -8 | 81.07 | 84.82 | 3.75 | -11.57 | -13.0 | 7.004 | 6.524 |
| GC_NY | exclude_cpi_nfp | 40 | 34 | -6 | 40.4 | 46.4 | 6.0 | -7.0 | -5.0 | 5.771 | 9.279 |
| GC_Asia | exclude_cpi_nfp native; cpi_nfp_plus_not_inside post-filter | 72 | 69 | -3 | 36.7 | 36.0 | -0.7 | -6.0 | -5.0 | 6.117 | 7.2 |

## Post-Filter-Only Deltas

| session | gate | current_fills | candidate_fills | delta_fills | current_net_r | candidate_net_r | delta_net_r | current_dd_r | candidate_dd_r | current_calmar | candidate_calmar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GC_Asia | prior_not_inside_day post-filter after native CPI/NFP exclusion | 59 | 56 | -3 | 36.4 | 33.5 | -2.9 | -5.0 | -5.0 | 7.28 | 6.7 |

## Decision

- Encode candidate: `GC_NY exclude_cpi_nfp`. It survives exact single-leg and full-portfolio replay with positive net-R and lower drawdown.
- Conditional candidate: `GC_Asia exclude_cpi_nfp`. It helps full-portfolio exact replay, but single-leg net-R is slightly worse; do not include the prior-inside component without live-native implementation.
- Conditional/portfolio-only candidate: `NQ_NY exclude_cpi`. It helps the full portfolio but fails single-leg exact replay, so the edge is interaction-dependent.
- Do not encode for net-R: `ES_NY exclude_fomc_cpi`. It improves exact single-leg net-R but worsens single-leg DD/Calmar and is slightly negative in the full portfolio.
- Research-only/skip: `signal_outside_orb` variants and `prior_not_inside_day` until the live ORB engine records/evaluates those gates before order arming.

## Read

Exact-native date exclusions did not recreate the research squeeze. The comparison isolates whether the structural event-date cuts survive the live engine; signal-shape and prior-day gates remain research-only unless they are encoded into the live ORB state machine.

## Artifacts

- Results: `backtesting/data/results/hot_regime_v1_exact_candidate_compare_20260503/`
- Script: `backtesting/scripts/run_hot_regime_v1_exact_candidate_compare.py`
