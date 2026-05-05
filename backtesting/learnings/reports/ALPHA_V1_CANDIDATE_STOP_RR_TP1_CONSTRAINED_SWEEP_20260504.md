# ALPHA_V1 Candidate Stop + RR/TP1 Constrained Sweep

- Run slug: `alpha_v1_candidate_stop_rr_tp1_constrained_sweep_20260504`
- Windows: last 1y `2025-03-24` to `2026-03-24`, last 2y `2024-03-24` to `2026-03-24`, full `2016-04-17` to `2026-03-24`.
- Target constraint preserved: `rr <= 3.0` and `1.0 <= rr * tp1_ratio <= 1.5`.
- RR/TP1 target menu: `[(1.5, 0.666667, 1.0), (1.5, 0.833333, 1.25), (1.5, 1.0, 1.5), (2.0, 0.5, 1.0), (2.0, 0.625, 1.25), (2.0, 0.75, 1.5), (2.5, 0.4, 1.0), (2.5, 0.5, 1.25), (2.5, 0.6, 1.5), (3.0, 0.416667, 1.25), (3.0, 0.5, 1.5)]`.
- ATR stop values: `(3.0, 5.0, 7.0, 8.0, 10.0, 12.0)`.
- ORB stop values: `(17.0, 50.0, 75.0, 100.0, 125.0, 150.0)`.
- ORB-style candidates swept both ATR% and ORB% stops.
- LSI/HTF-LSI/CISD candidates swept ATR% stop mode only; native LSI setups do not define an ORB range, so ORB% stop rows were skipped rather than treated as valid comparisons.

## Candidate Set

| Candidate | Key | Group | Strategy | Deployability | Exact |
| --- | --- | --- | --- | --- | --- |
| NQ NY HTF-LSI | nq_ny_htf_lsi | active_alpha_v1 | htf_lsi | live_native | yes |
| NQ Asia ORB | nq_asia_orb | active_alpha_v1 | continuation | live_native | yes |
| ES Asia ORB | es_asia_orb | active_alpha_v1 | continuation | live_native | yes |
| ES NY ORB | es_ny_orb | active_alpha_v1 | continuation | live_native | yes |
| NQ NY ORB R11 conditional long | nq_ny_orb_r11 | conditional_candidate | continuation | live_native | yes |
| NQ NY ORB short v2 conditional | nq_ny_short_v2 | conditional_candidate | continuation | live_native | yes |
| ES Asia-B ORB ungated | es_asia_b_ungated | conditional_candidate | continuation | live_native | yes |
| ES NY HTF-LSI balanced lag0 gap3 | es_ny_htf_lsi_balanced_lag0_gap3 | conditional_research | htf_lsi | research_only | yes |
| add_1m_classic_atr10_b3_a7p5 / both / no Thursday / entry cutoff 15:30 | nq_ny_cisd_additive_no_thu | conditional_research | lsi | live_native | yes |
| pure_1m_classic_atr15_b2_a7p5 / long / all weekdays / entry cutoff 12:00 | nq_ny_pure_cisd_long_noon | conditional_research | lsi | live_native | yes |

## Best Overall Per Candidate

| Rank | Candidate | Group | Stop | rr | tp1_ratio | TP1_R | 1y R/tr/WR/PF/DD | 2y R/tr/PF/DD | full R/tr/WR/PF/DD | Deployability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | NQ Asia ORB | active_alpha_v1 | orb_pct 125 | 2.50 | 0.60 | 1.50 | 32.2/73/56.2%/2.06/-6.0 | 49.3/138/1.82/-6.0 | 174.3/722/50.1%/1.50/-13.1 | live_native |
| 2 | ES Asia ORB | active_alpha_v1 | orb_pct 50 | 2.00 | 0.75 | 1.50 | 31.6/143/50.4%/1.48/-6.2 | 46.9/284/1.34/-7.1 | 186.1/1422/48.5%/1.29/-18.1 | live_native |
| 3 | ES Asia-B ORB ungated | conditional_candidate | atr_pct 12 | 2.00 | 0.75 | 1.50 | 22.9/83/57.8%/1.67/-4.8 | 40.9/172/1.58/-5.2 | 107.9/906/48.5%/1.26/-12.6 | live_native |
| 4 | NQ NY ORB R11 conditional long | conditional_candidate | atr_pct 7 | 3.00 | 0.50 | 1.50 | 6.0/49/44.9%/1.22/-6.0 | 21.0/110/1.36/-6.0 | 114.7/552/50.7%/1.42/-8.5 | live_native |
| 5 | add_1m_classic_atr10_b3_a7p5 / both / no Thursday / entry cutoff 15:30 | conditional_research | atr_pct 10 | 2.50 | 0.40 | 1.00 | 8.5/43/62.8%/1.52/-4.6 | 18.5/85/1.59/-4.6 | 87.9/462/58.9%/1.46/-8.9 | live_native |
| 6 | ES NY ORB | active_alpha_v1 | orb_pct 50 | 3.00 | 0.50 | 1.50 | 9.2/93/43.0%/1.16/-14.3 | 20.3/183/1.19/-14.3 | 84.2/846/43.7%/1.18/-14.7 | live_native |
| 7 | ES NY HTF-LSI balanced lag0 gap3 | conditional_research | atr_pct 10 | 2.00 | 0.75 | 1.50 | 6.3/49/46.9%/1.24/-5.8 | 16.4/101/1.31/-5.8 | 41.8/549/44.4%/1.14/-18.2 | research_only |
| 8 | pure_1m_classic_atr15_b2_a7p5 / long / all weekdays / entry cutoff 12:00 | conditional_research | atr_pct 12 | 2.50 | 0.50 | 1.25 | 4.2/17/58.8%/1.59/-3.0 | 9.0/38/1.61/-4.7 | 53.5/185/58.9%/1.70/-8.8 | live_native |
| 9 | NQ NY HTF-LSI | active_alpha_v1 | atr_pct 8 | 3.00 | 0.50 | 1.50 | 13.9/39/56.4%/1.81/-5.0 | 15.3/89/1.33/-12.6 | 37.8/484/44.8%/1.14/-30.0 | live_native |
| 10 | NQ NY ORB short v2 conditional | conditional_candidate | orb_pct 17 | 1.50 | 0.67 | 1.00 | 6.7/16/81.2%/3.15/-1.5 | 10.6/38/2.09/-2.1 | 19.8/198/61.1%/1.28/-5.8 | live_native |

## Best By Stop Source

| Candidate | Stop Source | Stop Value | rr | tp1_ratio | TP1_R | 1y R | 2y R | full R | full PF | full DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ Asia ORB | orb_pct | 125.00 | 2.50 | 0.60 | 1.50 | 32.23 | 49.27 | 174.33 | 1.50 | -13.07 |
| ES Asia ORB | orb_pct | 50.00 | 2.00 | 0.75 | 1.50 | 31.63 | 46.86 | 186.11 | 1.29 | -18.09 |
| ES Asia ORB | atr_pct | 8.00 | 3.00 | 0.50 | 1.50 | 34.80 | 46.16 | 170.70 | 1.28 | -19.11 |
| NQ Asia ORB | atr_pct | 7.00 | 3.00 | 0.50 | 1.50 | 27.77 | 43.10 | 161.33 | 1.43 | -9.58 |
| ES Asia-B ORB ungated | atr_pct | 12.00 | 2.00 | 0.75 | 1.50 | 22.85 | 40.94 | 107.91 | 1.26 | -12.64 |
| ES Asia-B ORB ungated | orb_pct | 150.00 | 3.00 | 0.50 | 1.50 | 23.49 | 30.22 | 80.96 | 1.19 | -19.49 |
| NQ NY ORB R11 conditional long | atr_pct | 7.00 | 3.00 | 0.50 | 1.50 | 6.01 | 21.03 | 114.67 | 1.42 | -8.51 |
| NQ NY ORB R11 conditional long | orb_pct | 17.00 | 3.00 | 0.50 | 1.50 | 13.77 | 25.00 | 64.03 | 1.22 | -11.31 |
| add_1m_classic_atr10_b3_a7p5 / both / no Thursday / entry cutoff 15:30 | atr_pct | 10.00 | 2.50 | 0.40 | 1.00 | 8.52 | 18.48 | 87.87 | 1.46 | -8.86 |
| ES NY ORB | orb_pct | 50.00 | 3.00 | 0.50 | 1.50 | 9.17 | 20.28 | 84.20 | 1.18 | -14.71 |
| ES NY ORB | atr_pct | 3.00 | 2.50 | 0.50 | 1.25 | 16.19 | 20.17 | 69.83 | 1.17 | -19.93 |
| ES NY HTF-LSI balanced lag0 gap3 | atr_pct | 10.00 | 2.00 | 0.75 | 1.50 | 6.27 | 16.38 | 41.79 | 1.14 | -18.19 |
| pure_1m_classic_atr15_b2_a7p5 / long / all weekdays / entry cutoff 12:00 | atr_pct | 12.00 | 2.50 | 0.50 | 1.25 | 4.24 | 8.99 | 53.47 | 1.70 | -8.77 |
| NQ NY HTF-LSI | atr_pct | 8.00 | 3.00 | 0.50 | 1.50 | 13.90 | 15.28 | 37.80 | 1.14 | -30.03 |
| NQ NY ORB short v2 conditional | orb_pct | 17.00 | 1.50 | 0.67 | 1.00 | 6.67 | 10.61 | 19.82 | 1.28 | -5.82 |
| NQ NY ORB short v2 conditional | atr_pct | 3.00 | 2.00 | 0.50 | 1.00 | 3.88 | 7.89 | 26.54 | 1.44 | -4.99 |

## Read

- This is a research sweep, not an execution-config change.
- Any live-native winner still needs exact execution replay before promotion.
- ORB% stop rows are only valid for ORB-style candidates in this packet.

## Artifacts

- Summary JSON: `backtesting/data/results/alpha_v1_candidate_stop_rr_tp1_constrained_sweep_20260504/summary.json`
- Ranked rows CSV: `backtesting/data/results/alpha_v1_candidate_stop_rr_tp1_constrained_sweep_20260504/ranked_candidates.csv`
- Best by candidate CSV: `backtesting/data/results/alpha_v1_candidate_stop_rr_tp1_constrained_sweep_20260504/best_by_candidate.csv`
- Best by stop source CSV: `backtesting/data/results/alpha_v1_candidate_stop_rr_tp1_constrained_sweep_20260504/best_by_stop_source.csv`
- Window metrics CSV: `backtesting/data/results/alpha_v1_candidate_stop_rr_tp1_constrained_sweep_20260504/window_metrics.csv`
- Variant manifest CSV: `backtesting/data/results/alpha_v1_candidate_stop_rr_tp1_constrained_sweep_20260504/variant_manifest.csv`
- Script: `backtesting/scripts/run_alpha_v1_candidate_stop_rr_tp1_constrained_sweep.py`
