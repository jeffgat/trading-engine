# ALPHA_V1 ORB Range Gate Sweep

- Run slug: `alpha_v1_orb_range_gate_sweep_20260529`
- Purpose: broad post-filter search for ORB range percentile sweet spots, especially `orb_mid`-style bands that skip tiny and extreme-large opening ranges.
- Primary stream: `alpha_v1_recent_payout_sim_20260506/trade_stream.csv` active exact ORB legs, `2016-04-17` through `2026-03-24`.
- Secondary streams: exact split counterparts for ES Asia / ES NY / NQ R11, plus current fee-aware aggressive sprint trades from `2023-01-01` through `2026-03-24`.
- ORB range percentile: rolling 60 completed session ranges, current session included after ORB completion; minimum 10 prior/current observations.
- Status: `post_filter_only` / `research_only`; no live pre-arm ORB-size gate exists yet.

## Primary Baseline

| stream_label | leg_label | base_trades | base_total_r | base_avg_r | base_wr_pct | base_pf | base_dd_r | base_calmar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1 active exact stream | ES Asia ORB | 1116 | 137 | 0.12 | 54.9 | 1.28 | -12.2 | 11.2 |
| ALPHA_V1 active exact stream | ES NY ORB | 506 | 71.1 | 0.14 | 55.3 | 1.32 | -12.0 | 5.93 |
| ALPHA_V1 active exact stream | NQ Asia ORB | 640 | 167 | 0.26 | 44.4 | 1.48 | -8.32 | 20.1 |
| ALPHA_V1 active exact stream | NQ NY ORB R11 | 554 | 148 | 0.27 | 52.2 | 1.56 | -6.45 | 23.0 |

## Operating Read

- The active ORB sleeve has a real quality-concentration effect, but the evidence does not support a simple hard rule that skips both tiny and very large ORBs across all legs.
- Sleeve-wide `40%-67%` ORB percentile kept only `27%` of trades but improved average R/trade (`0.186R -> 0.232R`), PF (`1.397 -> 1.503`), and max DD (`-19.87R -> -10.78R`). It also gave up `-347.2R` of total edge, so this is more promising as a risk throttle or specialist sleeve than a full replacement.
- Do not blindly skip all high ORBs: the `80%-100%` sleeve bucket remained strong, and ES NY, NQ Asia, and NQ R11 each had profitable very-large ORB buckets. The weak high-range pocket is mostly `67%-80%`, not the full high tail.
- ES Asia is the cleanest true-gate follow-up: `0%-20%` and `67%-100%` underperformed, while `20%-67%` improved PF/DD versus baseline. This deserves a causal engine replay before any promotion.
- ES NY, NQ Asia, and NQ R11 are not clean `orb_mid` candidates because each has at least one strong non-mid bucket. For those legs, treat ORB size as context or sizing input, not an outright skip rule.

## Best Primary Percentile Bands

| leg_label | band | kept_trades | keep_pct | kept_total_r | delta_total_r | kept_avg_r | delta_avg_r | kept_pf | delta_pf | kept_dd_r | delta_dd_r | quality_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES Asia ORB | 20%-50% | 338 | 30.3 | 62.9 | -73.8 | 0.19 | 0.06 | 1.45 | 0.17 | -8.20 | 4.03 | 9.04 |
| ES Asia ORB | 20%-67% | 528 | 47.3 | 82.9 | -53.8 | 0.16 | 0.03 | 1.36 | 0.08 | -7.20 | 5.03 | 8.47 |
| ES Asia ORB | 33%-67% | 394 | 35.3 | 66.5 | -70.2 | 0.17 | 0.05 | 1.40 | 0.11 | -8.00 | 4.23 | 7.68 |
| ES NY ORB | 30%-60% | 144 | 28.5 | 38.7 | -32.5 | 0.27 | 0.13 | 1.74 | 0.42 | -8.00 | 4.00 | 18.0 |
| ES NY ORB | 33%-60% | 130 | 25.7 | 31.3 | -39.9 | 0.24 | 0.10 | 1.68 | 0.36 | -7.50 | 4.50 | 15.5 |
| ES NY ORB | 30%-67% | 173 | 34.2 | 39.7 | -31.4 | 0.23 | 0.09 | 1.61 | 0.29 | -8.00 | 4.00 | 13.9 |
| NQ Asia ORB | 40%-67% | 174 | 27.2 | 63.8 | -104 | 0.37 | 0.11 | 1.67 | 0.19 | -6.78 | 1.54 | 8.04 |
| NQ Asia ORB | 0%-30% | 187 | 29.2 | 70.8 | -96.7 | 0.38 | 0.12 | 1.70 | 0.22 | -9.40 | -1.08 | 7.29 |
| NQ Asia ORB | 40%-70% | 199 | 31.1 | 69.8 | -97.7 | 0.35 | 0.09 | 1.64 | 0.16 | -7.78 | 0.54 | 5.14 |
| NQ NY ORB R11 | 75%-100% | 155 | 28.0 | 55.9 | -92.5 | 0.36 | 0.09 | 1.75 | 0.19 | -7.90 | -1.45 | 5.04 |
| NQ NY ORB R11 | 40%-67% | 151 | 27.3 | 52.6 | -95.7 | 0.35 | 0.08 | 1.80 | 0.24 | -6.65 | -0.20 | 3.76 |
| NQ NY ORB R11 | 40%-100% | 348 | 62.8 | 109 | -39.0 | 0.31 | 0.05 | 1.67 | 0.11 | -10.4 | -3.95 | 2.90 |
| ORB sleeve portfolio | 40%-67% | 759 | 26.9 | 176 | -347 | 0.23 | 0.05 | 1.50 | 0.11 | -10.8 | 9.09 | 1.13 |
| ORB sleeve portfolio | 0%-60% | 1682 | 59.7 | 313 | -210 | 0.19 | 0.00 | 1.39 | -0.01 | -12.8 | 7.04 | 0.06 |
| ORB sleeve portfolio | 0%-67% | 1843 | 65.5 | 362 | -161 | 0.20 | 0.01 | 1.42 | 0.02 | -15.4 | 4.50 | -0.21 |

## Portfolio-Level Bands

| stream_label | band | kept_trades | keep_pct | kept_total_r | delta_total_r | kept_avg_r | delta_avg_r | kept_pf | delta_pf | kept_dd_r | delta_dd_r | quality_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1 active exact stream | 40%-67% | 759 | 26.9 | 176 | -347 | 0.23 | 0.05 | 1.50 | 0.11 | -10.8 | 9.09 | 1.13 |
| ALPHA_V1 active exact stream | 0%-60% | 1682 | 59.7 | 313 | -210 | 0.19 | 0.00 | 1.39 | -0.01 | -12.8 | 7.04 | 0.06 |
| ALPHA_V1 active exact stream | 0%-67% | 1843 | 65.5 | 362 | -161 | 0.20 | 0.01 | 1.42 | 0.02 | -15.4 | 4.50 | -0.21 |
| ALPHA_V1 active exact stream | 0%-90% | 2504 | 88.9 | 468 | -55.6 | 0.19 | 0.00 | 1.40 | 0.00 | -18.4 | 1.48 | -0.47 |
| ALPHA_V1 active exact stream | 0%-70% | 1933 | 68.6 | 363 | -161 | 0.19 | 0.00 | 1.40 | -0.00 | -15.4 | 4.50 | -1.10 |
| ALPHA_V1 fee-aware aggressive sprint 2023+ | 0%-30% | 228 | 27.5 | 53.6 | -77.3 | 0.24 | 0.08 | 1.49 | 0.17 | -12.0 | 7.46 | 15.4 |
| ALPHA_V1 fee-aware aggressive sprint 2023+ | 67%-100% | 302 | 36.5 | 50.6 | -80.3 | 0.17 | 0.01 | 1.36 | 0.04 | -8.35 | 11.1 | 13.7 |
| ALPHA_V1 fee-aware aggressive sprint 2023+ | 0%-40% | 319 | 38.5 | 67.2 | -63.7 | 0.21 | 0.05 | 1.43 | 0.11 | -12.3 | 7.19 | 13.1 |
| ALPHA_V1 fee-aware aggressive sprint 2023+ | 70%-100% | 282 | 34.1 | 49.2 | -81.7 | 0.17 | 0.02 | 1.38 | 0.06 | -9.42 | 10.0 | 12.7 |
| ALPHA_V1 fee-aware aggressive sprint 2023+ | 75%-100% | 232 | 28.0 | 38.8 | -92.1 | 0.17 | 0.01 | 1.35 | 0.03 | -8.74 | 10.7 | 12.4 |
| Exact split counterpart streams | 25%-100% | 2182 | 77.1 | 404 | -71.9 | 0.18 | 0.02 | 1.42 | 0.04 | -14.7 | 0.00 | -1.81 |
| Exact split counterpart streams | 33%-90% | 1619 | 57.2 | 309 | -167 | 0.19 | 0.02 | 1.44 | 0.06 | -12.2 | 2.47 | -2.24 |
| Exact split counterpart streams | 0%-90% | 2503 | 88.4 | 422 | -53.0 | 0.17 | 0.00 | 1.38 | 0.01 | -15.8 | -1.08 | -2.56 |
| Exact split counterpart streams | 10%-90% | 2267 | 80.1 | 401 | -74.9 | 0.18 | 0.01 | 1.40 | 0.02 | -19.0 | -4.30 | -2.82 |
| Exact split counterpart streams | 20%-100% | 2322 | 82.0 | 404 | -71.9 | 0.17 | 0.01 | 1.39 | 0.01 | -16.6 | -1.90 | -2.99 |

## Primary Percentile Bucket Attribution

| leg_label | pctile_bucket | bucket_trades | bucket_total_r | bucket_avg_r | bucket_pf | bucket_dd_r |
| --- | --- | --- | --- | --- | --- | --- |
| ES Asia ORB | 0-20 | 199 | 11.9 | 0.06 | 1.13 | -7.40 |
| ES Asia ORB | 20-33 | 128 | 21.0 | 0.16 | 1.39 | -5.22 |
| ES Asia ORB | 33-50 | 189 | 44.0 | 0.23 | 1.58 | -9.68 |
| ES Asia ORB | 50-67 | 190 | 20.0 | 0.11 | 1.23 | -11.2 |
| ES Asia ORB | 67-80 | 150 | 14.8 | 0.10 | 1.23 | -9.16 |
| ES Asia ORB | 80-100 | 260 | 24.9 | 0.10 | 1.21 | -8.79 |
| ES NY ORB | 0-20 | 115 | 16.3 | 0.14 | 1.31 | -6.25 |
| ES NY ORB | 20-33 | 76 | 0.92 | 0.01 | 1.02 | -9.00 |
| ES NY ORB | 33-50 | 80 | 17.5 | 0.22 | 1.60 | -7.00 |
| ES NY ORB | 50-67 | 70 | 9.22 | 0.13 | 1.32 | -5.00 |
| ES NY ORB | 67-80 | 59 | -5.46 | -0.09 | 0.83 | -11.5 |
| ES NY ORB | 80-100 | 106 | 32.6 | 0.31 | 1.80 | -7.00 |
| NQ Asia ORB | 0-20 | 131 | 38.8 | 0.30 | 1.54 | -14.2 |
| NQ Asia ORB | 20-33 | 87 | 26.4 | 0.30 | 1.55 | -9.65 |
| NQ Asia ORB | 33-50 | 123 | 30.7 | 0.25 | 1.45 | -13.8 |
| NQ Asia ORB | 50-67 | 98 | 33.8 | 0.35 | 1.59 | -11.0 |
| NQ Asia ORB | 67-80 | 84 | 4.25 | 0.05 | 1.09 | -9.00 |
| NQ Asia ORB | 80-100 | 117 | 33.5 | 0.29 | 1.61 | -8.01 |
| NQ NY ORB R11 | 0-20 | 108 | 21.6 | 0.20 | 1.41 | -12.9 |
| NQ NY ORB R11 | 20-33 | 70 | 16.3 | 0.23 | 1.50 | -6.60 |
| NQ NY ORB R11 | 33-50 | 97 | 22.9 | 0.24 | 1.50 | -4.45 |
| NQ NY ORB R11 | 50-67 | 82 | 30.8 | 0.38 | 1.86 | -5.90 |
| NQ NY ORB R11 | 67-80 | 79 | 21.3 | 0.27 | 1.58 | -9.50 |
| NQ NY ORB R11 | 80-100 | 118 | 35.3 | 0.30 | 1.59 | -7.30 |

## Files

- Annotated trades: `backtesting/data/results/alpha_v1_orb_range_gate_sweep_20260529/annotated_trades.csv`
- Band sweep: `backtesting/data/results/alpha_v1_orb_range_gate_sweep_20260529/band_sweep.csv`
- Top candidates: `backtesting/data/results/alpha_v1_orb_range_gate_sweep_20260529/top_candidates.csv`
- Bucket summary: `backtesting/data/results/alpha_v1_orb_range_gate_sweep_20260529/bucket_summary.csv`
- Baseline summary: `backtesting/data/results/alpha_v1_orb_range_gate_sweep_20260529/baseline_summary.csv`

## Interpretation Notes

- A positive `delta_avg_r` with large negative `delta_total_r` means the band concentrates quality but gives up too much flow for a sleeve-wide replacement.
- A positive `delta_dd_r` means drawdown improved because max DD became less negative.
- These bands are searched directly on the evaluation stream; promotion would need causal engine support, exact replay, and out-of-sample validation.
