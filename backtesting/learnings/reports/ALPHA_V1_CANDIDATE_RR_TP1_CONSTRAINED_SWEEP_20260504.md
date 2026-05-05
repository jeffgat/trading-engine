# ALPHA_V1 Candidate RR/TP1 Constrained Sweep

- Run slug: `alpha_v1_candidate_rr_tp1_constrained_sweep_20260504`
- Window set: last 1y `2025-03-24` to `2026-03-24`, last 2y `2024-03-24` to `2026-03-24`, full `2016-04-17` to `2026-03-24`.
- Constraint: `rr <= 3.0` and `1.0 <= rr * tp1_ratio <= 1.5`.
- Target menu: `[(1.5, 0.666667, 1.0), (1.5, 0.833333, 1.25), (1.5, 1.0, 1.5), (2.0, 0.5, 1.0), (2.0, 0.625, 1.25), (2.0, 0.75, 1.5), (2.5, 0.4, 1.0), (2.5, 0.5, 1.25), (2.5, 0.6, 1.5), (3.0, 0.416667, 1.25), (3.0, 0.5, 1.5)]`.
- Method: broad research replay with 1s/1m magnifier data where the research configs require it. Execution configs were not edited.
- Exact replay posture: live-native rows are exact-replay candidates, but this packet is the research shortlist stage. Use the exact execution state machines before promoting any live config.

## Candidate Set

| Candidate | Key | Group | Deployability | Exact replay required | Inclusion notes |
| --- | --- | --- | --- | --- | --- |
| NQ NY HTF-LSI | nq_ny_htf_lsi | active_alpha_v1 | live_native | yes | Current ALPHA_V1 leg from ALPHA_V1.md. |
| NQ Asia ORB | nq_asia_orb | active_alpha_v1 | live_native | yes | Current ALPHA_V1 leg from ALPHA_V1.md. |
| ES Asia ORB | es_asia_orb | active_alpha_v1 | live_native | yes | Current ALPHA_V1 leg from ALPHA_V1.md. |
| ES NY ORB | es_ny_orb | active_alpha_v1 | live_native | yes | Current ALPHA_V1 leg from ALPHA_V1.md. |
| NQ NY ORB R11 conditional long | nq_ny_orb_r11 | conditional_candidate | live_native | yes | NQ detailed history marks R11 conditional with 4/5 pipeline phases passed. |
| NQ NY ORB short v2 conditional | nq_ny_short_v2 | conditional_candidate | live_native | yes | Included as a low-frequency diversifier; known annual-R bottleneck. |
| ES Asia-B ORB ungated | es_asia_b_ungated | conditional_candidate | live_native | yes | ES detailed history marks Asia-B STRONG and paper-trading consideration. |
| ES NY HTF-LSI balanced lag0 gap3 | es_ny_htf_lsi_balanced_lag0_gap3 | conditional_research | research_only | yes | Included because it is the best ES HTF-LSI restart branch, but it is not promotion-clean. |
| add_1m_classic_atr10_b3_a7p5 / both / no Thursday / entry cutoff 15:30 | nq_ny_cisd_additive_no_thu | conditional_research | live_native | yes | NQ CISD restricted finalist from 2026-05-03; target-only retest under stricter RR cap. |
| pure_1m_classic_atr15_b2_a7p5 / long / all weekdays / entry cutoff 12:00 | nq_ny_pure_cisd_long_noon | conditional_research | live_native | yes | NQ CISD restricted finalist from 2026-05-03; target-only retest under stricter RR cap. |

## Top Ranked Candidate Per Leg

| Rank | Candidate | Group | rr | tp1_ratio | TP1_R | 1y R/tr/PF/DD | 2y R/tr/PF/DD | full R/tr/PF/DD | WR 1y/full | Deployability | Exact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | NQ Asia ORB | active_alpha_v1 | 3.00 | 0.50 | 1.50 | 26.9/73/1.78/-6.0 | 42.6/138/1.65/-6.0 | 173.6/722/1.48/-10.7 | 53.4%/49.0% | live_native | yes |
| 2 | ES Asia ORB | active_alpha_v1 | 1.50 | 0.83 | 1.25 | 22.9/143/1.41/-5.6 | 43.6/284/1.39/-6.1 | 160.7/1422/1.30/-14.2 | 54.5%/52.7% | live_native | yes |
| 3 | ES Asia-B ORB ungated | conditional_candidate | 2.00 | 0.75 | 1.50 | 22.9/83/1.67/-4.8 | 40.9/172/1.58/-5.2 | 107.9/906/1.26/-12.6 | 57.8%/48.5% | live_native | yes |
| 4 | NQ NY HTF-LSI | active_alpha_v1 | 3.00 | 0.50 | 1.50 | 13.7/39/1.82/-4.0 | 25.2/89/1.64/-6.9 | 85.8/481/1.40/-10.7 | 59.0%/51.1% | live_native | yes |
| 5 | NQ NY ORB R11 conditional long | conditional_candidate | 3.00 | 0.50 | 1.50 | 6.0/49/1.22/-6.0 | 21.0/110/1.36/-6.0 | 114.7/552/1.42/-8.5 | 44.9%/50.7% | live_native | yes |
| 6 | add_1m_classic_atr10_b3_a7p5 / both / no Thursday / entry cutoff 15:30 | conditional_research | 2.50 | 0.40 | 1.00 | 8.5/43/1.52/-4.6 | 18.5/85/1.59/-4.6 | 87.9/462/1.46/-8.9 | 62.8%/58.9% | live_native | yes |
| 7 | ES NY ORB | active_alpha_v1 | 2.50 | 0.50 | 1.25 | 16.2/93/1.38/-10.1 | 20.2/183/1.23/-10.1 | 69.8/846/1.17/-19.9 | 54.8%/51.6% | live_native | yes |
| 8 | pure_1m_classic_atr15_b2_a7p5 / long / all weekdays / entry cutoff 12:00 | conditional_research | 2.50 | 0.40 | 1.00 | 3.0/17/1.47/-1.7 | 10.9/38/1.99/-2.5 | 40.9/185/1.57/-10.1 | 64.7%/62.2% | live_native | yes |
| 9 | NQ NY ORB short v2 conditional | conditional_candidate | 1.50 | 0.67 | 1.00 | 6.7/16/3.15/-1.5 | 10.6/38/2.09/-2.1 | 19.8/198/1.28/-5.8 | 81.2%/61.1% | live_native | yes |
| 10 | ES NY HTF-LSI balanced lag0 gap3 | conditional_research | 1.50 | 0.83 | 1.25 | 1.2/49/1.08/-7.0 | -0.6/101/0.99/-9.3 | 37.7/545/1.17/-19.8 | 49.0%/50.3% | research_only | yes |

## Active ALPHA_V1 Read

- **NQ Asia ORB**: best constrained row is `rr=3.00`, `tp1_ratio=0.5000` (`TP1_R=1.50`), versus current `rr=6.0`, `tp1_ratio=0.3`. Last-1y `26.9R`, last-2y `42.6R`, full `173.6R`.
- **ES Asia ORB**: best constrained row is `rr=1.50`, `tp1_ratio=0.8333` (`TP1_R=1.25`), versus current `rr=1.5`, `tp1_ratio=0.7`. Last-1y `22.9R`, last-2y `43.6R`, full `160.7R`.
- **NQ NY HTF-LSI**: best constrained row is `rr=3.00`, `tp1_ratio=0.5000` (`TP1_R=1.50`), versus current `rr=3.5`, `tp1_ratio=0.4`. Last-1y `13.7R`, last-2y `25.2R`, full `85.8R`.
- **ES NY ORB**: best constrained row is `rr=2.50`, `tp1_ratio=0.5000` (`TP1_R=1.25`), versus current `rr=5.0`, `tp1_ratio=0.2`. Last-1y `16.2R`, last-2y `20.2R`, full `69.8R`.

## Exact Active Shortlist Replay

Follow-up exact replay: `backtesting/learnings/reports/ALPHA_V1_CONSTRAINED_TOP_EXACT_REPLAY_20260504.md`

The production execution engine replayed the top constrained active profile in memory, without editing `execution/config/exec_configs.json`:

```json
{
  "NQ_NY_LSI": {"rr": 3.0, "tp1_ratio": 0.5},
  "NQ_Asia": {"rr": 3.0, "tp1_ratio": 0.5},
  "ES_Asia": {"rr": 1.5, "tp1_ratio": 0.8333333333333334},
  "ES_NY": {"rr": 2.5, "tp1_ratio": 0.5}
}
```

| Scope | Last 1y R/tr/PF/DD | Last 2y R/tr/PF/DD | Full R/tr/PF/DD |
| --- | ---: | ---: | ---: |
| Combined exact constrained top | 71.1 / 269 / 1.65 / -12.6 | 119.0 / 529 / 1.47 / -12.6 | 393.5 / 2605 / 1.32 / -20.5 |
| NQ NY HTF-LSI | 16.6 / 28 / 2.99 / -3.0 | 22.1 / 67 / 1.85 / -6.3 | 62.7 / 355 / 1.43 / -10.1 |
| NQ Asia ORB | 23.3 / 66 / 1.74 / -6.0 | 43.6 / 120 / 1.68 / -6.0 | 117.1 / 632 / 1.38 / -10.5 |
| ES Asia ORB | 19.5 / 118 / 1.36 / -5.1 | 42.9 / 226 / 1.43 / -6.0 | 158.6 / 1112 / 1.31 / -15.5 |
| ES NY ORB | 11.8 / 57 / 1.53 / -4.5 | 10.5 / 116 / 1.22 / -9.9 | 55.0 / 506 / 1.20 / -14.1 |

Current exact ALPHA_V1-A reference from `alpha_v1_live_replay_compare_20260503`: combined last-1y `87.7R / -9.5R DD`; combined full `445.5R / -14.9R DD`. The exact constrained-all-active profile is therefore **not** a portfolio upgrade despite the research shortlist looking attractive on individual rows.

## Conditional Promotion Read

- **ES Asia-B ORB ungated**: best constrained row `rr=2.00`, `tp1_ratio=0.7500` (`TP1_R=1.50`), last-1y `22.9R` on `83` trades, last-2y `40.9R`, full `107.9R`; deployability `live_native`. Standard ORB continuation fields; no regime gate required for the preferred branch.
- **NQ NY ORB R11 conditional long**: best constrained row `rr=3.00`, `tp1_ratio=0.5000` (`TP1_R=1.50`), last-1y `6.0R` on `49` trades, last-2y `21.0R`, full `114.7R`; deployability `live_native`. Standard ORB continuation fields; not currently in execution/config but supported by engine knobs.
- **add_1m_classic_atr10_b3_a7p5 / both / no Thursday / entry cutoff 15:30**: best constrained row `rr=2.50`, `tp1_ratio=0.4000` (`TP1_R=1.00`), last-1y `8.5R` on `43` trades, last-2y `18.5R`, full `87.9R`; deployability `live_native`. Simulator-native LSI/CISD fields; requires execution implementation/parity before deployment.
- **pure_1m_classic_atr15_b2_a7p5 / long / all weekdays / entry cutoff 12:00**: best constrained row `rr=2.50`, `tp1_ratio=0.4000` (`TP1_R=1.00`), last-1y `3.0R` on `17` trades, last-2y `10.9R`, full `40.9R`; deployability `live_native`. Simulator-native LSI/CISD fields; requires execution implementation/parity before deployment.
- **NQ NY ORB short v2 conditional**: best constrained row `rr=1.50`, `tp1_ratio=0.6667` (`TP1_R=1.00`), last-1y `6.7R` on `16` trades, last-2y `10.6R`, full `19.8R`; deployability `live_native`. Standard ORB continuation fields, short-only, ORB stop and dual floors.
- **ES NY HTF-LSI balanced lag0 gap3**: best constrained row `rr=1.50`, `tp1_ratio=0.8333` (`TP1_R=1.25`), last-1y `1.2R` on `49` trades, last-2y `-0.6R`, full `37.7R`; deployability `research_only`. Research HTF-LSI branch; execution support/parity not established and opened holdout was weak.

## Recommendation

- **Do not change the active ALPHA_V1 sleeve wholesale** to constrained targets. Exact replay rejected the all-active constrained-top profile: lower last-1y R, lower full R, and worse full drawdown than current exact ALPHA_V1-A.
- **Only ES Asia ORB has a live-native target-change case** from this pass: `rr=1.5`, `tp1_ratio=0.833333` improved exact per-leg R versus the current exact ES Asia row, but worsened full-history DD. It deserves isolated exact replay plus payout/risk sizing before any promotion.
- **Keep NQ Asia ORB current**. The constrained `rr=3/tp1=0.5` row is materially worse in exact replay than the current high-R target.
- **Keep ES NY ORB current**. The constrained `rr=2.5/tp1=0.5` row loses too much exact R and does not improve the combined profile.
- **Keep NQ NY HTF-LSI current for now**. `rr=3/tp1=0.5` is roughly flat in last-1y exact R but weaker full-history exact R; not enough reason to change the live profile.
- **Promote to exact-replay queue**: `ES Asia-B ORB ungated` (`rr=2.0`, `tp1_ratio=0.75`) is the best conditional live-native branch. It is not automatically an ALPHA replacement, but it is the cleanest next exact candidate.
- **Secondary research queue**: `NQ NY CISD additive no-Thursday` (`rr=2.5`, `tp1_ratio=0.4`) remains interesting, but execution implementation/parity is required before it can be considered live-native in practice.
- **Ignore for ALPHA_V1 promotion from this sweep**: `ES NY HTF-LSI balanced_lag0_gap3` remains research-only and weak recent/full; `NQ NY short v2` and pure-CISD noon are too low-throughput for portfolio priority.

## Artifacts

- Summary JSON: `backtesting/data/results/alpha_v1_candidate_rr_tp1_constrained_sweep_20260504/summary.json`
- Ranked rows CSV: `backtesting/data/results/alpha_v1_candidate_rr_tp1_constrained_sweep_20260504/ranked_candidates.csv`
- Window metrics CSV: `backtesting/data/results/alpha_v1_candidate_rr_tp1_constrained_sweep_20260504/window_metrics.csv`
- Variant manifest CSV: `backtesting/data/results/alpha_v1_candidate_rr_tp1_constrained_sweep_20260504/variant_manifest.csv`
- Script: `backtesting/scripts/run_alpha_v1_candidate_rr_tp1_constrained_sweep.py`
- Exact active shortlist: `backtesting/data/results/alpha_v1_constrained_top_exact_replay_20260504/summary.json`
- Exact active shortlist script: `backtesting/scripts/run_alpha_v1_constrained_top_exact_replay.py`
