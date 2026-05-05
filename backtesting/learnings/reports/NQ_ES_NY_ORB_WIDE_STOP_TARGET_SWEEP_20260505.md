# NQ/ES NY ORB Wide-Stop Target Sweep

- Run slug: `nq_es_ny_orb_wide_stop_target_sweep_20260505`
- Window set: last 1y `2025-03-24` to `2026-03-24`, last 2y `2024-03-24` to `2026-03-24`, full `2016-04-17` to `2026-03-24`.
- Scope: NQ NY ORB R11 and ES NY ORB only. Signal/session structure, direction filters, ATR length, DOW exclusions, gap filters, and magnifier settings were held fixed.
- Swept TP1 as target distance in R: `(1.0, 1.25, 1.4, 1.5, 2.0, 2.5, 3.0)`; accepted ratios were `0.2` to `0.75` and still obeyed the hard `rr * tp1_ratio >= 1.0` rule.
- `near_intact` means median stop widened at least 20%, full R retained at least 90%, last-1y and last-2y R retained at least 80%, full DD worsened no more than 25%, PF stayed within 0.10, and negative full years did not increase.
- This is a research sweep, not an execution change. Any selected row still needs exact execution replay before promotion.

## Read

- **Result: NO-GO for replacing either NY ORB with a wider-stop variant.** Across `794` valid configs, zero rows widened the actual median stop by at least `20%` while preserving the current result quality.
- **NQ NY ORB R11** baseline was `54.9` median stop ticks, `+122.4R`, `PF 1.55`, `-10.6R` DD, last-1y `+9.4R`, and last-2y `+19.9R`. The least-bad actual widening was around `ATR 9%` (`70.6` ticks, `1.29x` wider), but the best full-history rows gave up roughly `26R-30R` and dropped PF into the `1.34-1.42` zone. Example: `ATR 9% / rr 3.0 / TP1_R 1.25` printed `+96.2R`, `PF 1.42`, `-10.4R` DD, last-1y `+10.6R`, and last-2y `+19.8R`. That is smoother in places, but it is a real full-history haircut, not a free stop-width upgrade.
- **ES NY ORB** baseline was `12.0` median stop ticks, `+126.6R`, `PF 1.39`, `-10.9R` DD, last-1y `+18.2R`, and last-2y `+21.4R`. `ATR 6%` and `ORB 25%` still resolved to the same `12`-tick median stop because the `3pt` minimum stop floor dominated. The first meaningful wider rows were `ATR 10%+`, `ATR 12%+`, and `ORB 50%+`; they either damaged recent performance or doubled drawdown pressure. Example: `ATR 12% / rr 6.0 / TP1_R 1.5` nearly retained full R (`+124.5R`) but collapsed last-1y to `+5.3R`, dropped last-1y PF to `1.08`, and worsened DD to about `-20.4R` full / `-17.1R` last-1y. `ORB 50% / rr 5.0 / TP1_R 2.5` was less bad recently (`+14.6R` last-1y) but still cut full R to `+114.9R` and widened DD to `-17.2R`.
- Practical conclusion: if the live issue is discomfort with NY stopouts, **risk down or pause ES_NY rather than widening the stop**. For NQ R11, a modest `ATR 9%` family can be treated as a lower-return research branch, but it is not an upgrade over R11.

## Candidate Deployability

| Candidate | deployability | live_support_notes | exact_replay_required |
| --- | --- | --- | --- |
| NQ NY ORB R11 conditional long | live_native | Standard ORB continuation fields; NQ R11 is not active ALPHA_V1-A but all swept knobs are execution-supported. | yes_before_live_promotion |
| ES NY ORB ALPHA_V1 | live_native | Active ALPHA_V1 ORB leg; all swept stop/target knobs are execution-supported. | yes_before_live_promotion |

## Baselines

| Candidate | Stop | rr | tp1 | TP1_R | Med Stop Ticks | Full R/PF/DD | 1y R/PF/DD | 2y R/PF/DD | TP2% | TP1_BE% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ NY ORB R11 conditional long | atr_pct 7 | 3.50 | 0.40 | 1.40 | 54.90 | 122.4/1.55/-10.6 | 9.4/1.42/-4.5 | 19.9/1.45/-6.4 | 11.78 | 45.65 |
| ES NY ORB ALPHA_V1 | atr_pct 5 | 5.00 | 0.20 | 1.00 | 12.00 | 126.6/1.39/-10.9 | 18.2/1.57/-9.6 | 21.4/1.30/-9.7 | 6.38 | 46.93 |

## Best Near-Intact Wide Stops Per Candidate

| Candidate | Stop | Stop x | rr | tp1 | TP1_R | Full R/delta/PF/DD | 1y R/delta/PF/DD | 2y R/delta/PF/DD | TP2% | TP1_BE% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Top Near-Intact Wide Stops

| Candidate | Stop | Stop x | rr | tp1 | TP1_R | Full R/delta/PF/DD | 1y R/delta/PF/DD | 2y R/delta/PF/DD | TP2% | TP1_BE% | Near |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Top Score Rows Including Degraded

| Candidate | Stop | Stop x | rr | tp1 | TP1_R | Full R/delta/PF/DD | 1y R/delta/PF/DD | 2y R/delta/PF/DD | TP2% | TP1_BE% | Near |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB ALPHA_V1 | atr_pct 5 | 1.00 | 5.00 | 0.60 | 3.00 | 151.1/+24.5/1.26/-19.9 | 23.7/+5.5/1.35/-15.1 | 43.2/+21.8/1.33/-15.1 | 13.48 | 7.21 | False |
| ES NY ORB ALPHA_V1 | atr_pct 5 | 1.00 | 4.00 | 0.75 | 3.00 | 149.0/+22.4/1.26/-21.0 | 22.5/+4.3/1.33/-15.4 | 49.5/+28.1/1.38/-15.4 | 17.73 | 4.14 | False |
| ES NY ORB ALPHA_V1 | orb_pct 25 | 1.00 | 5.00 | 0.60 | 3.00 | 137.9/+11.4/1.24/-19.9 | 23.3/+5.1/1.34/-15.4 | 35.2/+13.8/1.27/-17.1 | 12.41 | 6.03 | False |
| ES NY ORB ALPHA_V1 | atr_pct 5 | 1.00 | 4.00 | 0.62 | 2.50 | 125.5/-1.0/1.23/-20.9 | 18.6/+0.4/1.29/-14.0 | 45.8/+24.4/1.38/-14.0 | 16.78 | 7.45 | False |
| NQ NY ORB R11 conditional long | atr_pct 7 | 1.00 | 4.00 | 0.38 | 1.50 | 120.9/-1.5/1.50/-9.8 | 11.6/+2.2/1.51/-4.2 | 23.6/+3.7/1.50/-7.3 | 10.69 | 42.21 | False |
| ES NY ORB ALPHA_V1 | atr_pct 5 | 1.00 | 6.00 | 0.50 | 3.00 | 141.7/+15.1/1.25/-23.7 | 21.1/+2.9/1.31/-14.1 | 34.5/+13.1/1.26/-14.1 | 9.81 | 9.10 | False |
| NQ NY ORB R11 conditional long | atr_pct 7 | 1.00 | 3.50 | 0.43 | 1.50 | 119.9/-2.4/1.50/-10.7 | 10.6/+1.2/1.47/-4.3 | 24.9/+5.0/1.53/-7.3 | 12.86 | 41.12 | False |
| ES NY ORB ALPHA_V1 | orb_pct 25 | 1.00 | 5.00 | 0.50 | 2.50 | 130.6/+4.0/1.24/-20.4 | 23.4/+5.2/1.36/-14.0 | 40.0/+18.6/1.32/-14.0 | 11.94 | 9.57 | False |
| NQ NY ORB R11 conditional long | atr_pct 7 | 1.00 | 5.00 | 0.30 | 1.50 | 121.7/-0.7/1.50/-9.8 | 10.4/+1.0/1.46/-4.2 | 22.4/+2.5/1.47/-7.3 | 7.43 | 43.48 | False |
| NQ NY ORB R11 conditional long | atr_pct 7 | 1.00 | 3.50 | 0.40 | 1.40 | 122.4/+0.0/1.55/-10.6 | 9.4/+0.0/1.42/-4.5 | 19.9/+0.0/1.45/-6.4 | 11.78 | 45.65 | False |
| ES NY ORB ALPHA_V1 | atr_pct 5 | 1.00 | 5.00 | 0.20 | 1.00 | 126.6/+0.0/1.39/-10.9 | 18.2/+0.0/1.57/-9.6 | 21.4/+0.0/1.30/-9.7 | 6.38 | 46.93 | False |
| ES NY ORB ALPHA_V1 | orb_pct 25 | 1.00 | 4.00 | 0.62 | 2.50 | 122.6/-4.0/1.22/-21.4 | 22.8/+4.5/1.35/-15.0 | 41.7/+20.3/1.34/-15.0 | 16.19 | 7.33 | False |
| ES NY ORB ALPHA_V1 | orb_pct 25 | 1.00 | 6.00 | 0.50 | 3.00 | 128.5/+1.9/1.23/-23.6 | 27.0/+8.8/1.40/-14.4 | 35.3/+13.9/1.27/-17.1 | 8.51 | 7.57 | False |
| NQ NY ORB R11 conditional long | atr_pct 7 | 1.00 | 4.00 | 0.35 | 1.40 | 121.8/-0.6/1.54/-11.7 | 10.4/+1.0/1.46/-4.3 | 17.9/-2.0/1.40/-7.3 | 9.60 | 46.74 | False |
| ES NY ORB ALPHA_V1 | orb_pct 25 | 1.00 | 6.00 | 0.42 | 2.50 | 123.5/-3.1/1.23/-23.9 | 27.2/+9.0/1.42/-12.9 | 41.0/+19.6/1.33/-13.1 | 8.27 | 10.99 | False |
| ES NY ORB ALPHA_V1 | orb_pct 25 | 1.00 | 4.00 | 0.75 | 3.00 | 129.9/+3.4/1.23/-21.0 | 22.6/+4.4/1.33/-16.5 | 36.5/+15.1/1.27/-17.1 | 16.78 | 3.66 | False |
| ES NY ORB ALPHA_V1 | atr_pct 5 | 1.00 | 5.00 | 0.50 | 2.50 | 126.1/-0.5/1.23/-19.2 | 18.7/+0.5/1.29/-13.7 | 37.9/+16.5/1.31/-13.7 | 12.65 | 10.40 | False |
| NQ NY ORB R11 conditional long | atr_pct 7 | 1.00 | 3.00 | 0.50 | 1.50 | 112.0/-10.3/1.46/-12.2 | 11.3/+1.9/1.49/-4.3 | 25.4/+5.5/1.53/-7.3 | 14.86 | 40.04 | False |
| ES NY ORB ALPHA_V1 | atr_pct 5 | 1.00 | 6.00 | 0.21 | 1.25 | 125.2/-1.4/1.31/-15.1 | 23.5/+5.3/1.55/-11.4 | 27.3/+5.9/1.31/-12.8 | 6.74 | 34.52 | False |
| NQ NY ORB R11 conditional long | atr_pct 7 | 1.00 | 3.00 | 0.47 | 1.40 | 114.5/-7.9/1.51/-10.6 | 10.0/+0.6/1.44/-4.6 | 21.2/+1.3/1.47/-6.4 | 13.59 | 44.75 | False |

## Artifacts

- Summary JSON: `backtesting/data/results/nq_es_ny_orb_wide_stop_target_sweep_20260505/summary.json`
- Ranked CSV: `backtesting/data/results/nq_es_ny_orb_wide_stop_target_sweep_20260505/ranked_candidates.csv`
- Window metrics CSV: `backtesting/data/results/nq_es_ny_orb_wide_stop_target_sweep_20260505/window_metrics.csv`
- Variant manifest CSV: `backtesting/data/results/nq_es_ny_orb_wide_stop_target_sweep_20260505/variant_manifest.csv`
- Script: `backtesting/scripts/run_nq_es_ny_orb_wide_stop_target_sweep_20260505.py`
