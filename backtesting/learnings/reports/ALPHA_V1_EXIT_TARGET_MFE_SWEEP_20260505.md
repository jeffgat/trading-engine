# ALPHA_V1 Exit Target MFE Sweep (2026-05-05)

- Run slug: `alpha_v1_exit_target_mfe_sweep_20260505`
- Full window: `2016-04-17` to `2026-03-24`; recent windows: `2024-03-24` and `2025-03-24` to `2026-03-24`.
- Scope: active `ALPHA_V1` legs plus `NQ NY ORB R11`.
- Pass 1: fixed-fill MFE/MAE diagnostic using the existing replay helper.
- Pass 2: true engine replay while holding entries, stops, sessions, DOW filters, ORB windows, and gap filters fixed; only `rr` and TP1 distance changed.
- Pass 3: Calmar/edge-first ranking against each leg's baseline. Full TP rate is treated as a diagnostic, not an objective.
- Deployability: all target rows are `live_native`; any selected change still requires exact execution replay before live modification.

## Pass 1 — MFE Diagnostic

| Leg | TP1_R | RR | WR | TP2% | TP1-BE% | TP1 hit% | TP2/TP1 | MFE>=2R | MFE>=3R | MFE>=RR | TP1-hit p75 MFE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HTF_LSI/NQ_NY-L24 | 1.40 | 3.50 | 52.8% | 6.2% | 12.1% | 35.8% | 17.4% | 21.8% | 9.4% | 6.9% | 3.03 |
| ORB/NQ_ASIA-RR6 | 1.80 | 6.00 | 45.7% | 5.1% | 14.7% | 41.4% | 12.4% | 37.4% | 22.6% | 5.3% | 4.47 |
| ORB/ES_ASIA-RR1.5 | 1.05 | 1.50 | 54.4% | 21.7% | 8.7% | 38.0% | 56.9% | 1.7% | 0.3% | 35.5% | 1.60 |
| ORB/ES_NY-RR5 | 1.00 | 5.00 | 61.0% | 6.4% | 46.9% | 59.8% | 10.7% | 21.5% | 15.0% | 8.9% | 2.92 |
| NQ NY ORB R11 | 1.40 | 3.50 | 53.3% | 18.1% | 33.0% | 52.4% | 34.6% | 36.0% | 24.8% | 21.4% | 3.62 |

## Pass 2/3 — Best Target Compression Rows

| Leg | Decision | Current | Selected | ΔR | ΔDD | TP2% | TP1-BE% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HTF_LSI/NQ_NY-L24 | test_closer_target | rr 3.5/TP1 1.4R 92.6R PF1.45 DD10.9 | rr 2/TP1 1.4R 90.0R PF1.43 DD10.0 | -2.62 | -0.91 | 21.0% | 8.1% |
| ORB/NQ_ASIA-RR6 | test_closer_target | rr 6/TP1 1.8R 213.5R PF1.55 DD10.2 | rr 3/TP1 2R 217.6R PF1.55 DD10.6 | 4.08 | 0.43 | 22.7% | 8.6% |
| ORB/ES_ASIA-RR1.5 | research_only_closer | rr 1.5/TP1 1.05R 145.8R PF1.28 DD12.3 | rr 1.25/TP1 1R 137.9R PF1.27 DD13.2 | -7.93 | 0.94 | 28.4% | 7.5% |
| ORB/ES_NY-RR5 | research_only_closer | rr 5/TP1 1R 126.6R PF1.39 DD10.9 | rr 4/TP1 1R 113.0R PF1.34 DD11.4 | -13.58 | 0.56 | 8.0% | 46.2% |
| NQ NY ORB R11 | research_only_closer | rr 3.5/TP1 1.4R 129.4R PF1.50 DD6.0 | rr 3/TP1 1.4R 118.8R PF1.46 DD6.1 | -10.64 | 0.08 | 20.6% | 31.3% |

## Top Ranked Rows

| Leg | Variant | Near | Loose | Full R/PF/DD | 2Y R/PF/DD | TP2% | TP1-BE% | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORB/NQ_ASIA-RR6 | rr 3/TP1 1.8R | False | True | 200.1/1.51/9.0 | 50.5/1.72/6.0 | 22.2% | 11.4% | 2361.79 |
| ORB/NQ_ASIA-RR6 | rr 3/TP1 1.75R | False | True | 199.7/1.52/9.1 | 50.1/1.72/6.0 | 22.2% | 12.2% | 2320.68 |
| ORB/NQ_ASIA-RR6 | rr 6/TP1 1.8R | True | True | 213.5/1.55/10.2 | 53.2/1.76/6.0 | 5.1% | 14.7% | 2235.05 |
| ORB/NQ_ASIA-RR6 | rr 2.5/TP1 1.8R | False | True | 196.2/1.50/9.4 | 53.7/1.77/6.0 | 28.8% | 7.9% | 2219.09 |
| NQ NY ORB R11 | rr 3.5/TP1 1.4R | True | True | 129.4/1.50/6.0 | 18.2/1.33/6.0 | 18.1% | 33.0% | 2218.89 |
| ORB/NQ_ASIA-RR6 | rr 3/TP1 2R | True | True | 217.6/1.55/10.6 | 54.8/1.76/6.0 | 22.7% | 8.6% | 2201.04 |
| ORB/NQ_ASIA-RR6 | rr 6/TP1 1.75R | True | True | 213.1/1.55/10.3 | 52.7/1.76/6.0 | 5.1% | 15.5% | 2199.95 |
| ORB/NQ_ASIA-RR6 | rr 2.5/TP1 1.75R | False | True | 195.8/1.51/9.5 | 53.3/1.76/6.0 | 28.8% | 8.7% | 2181.76 |
| ORB/NQ_ASIA-RR6 | rr 5/TP1 1.8R | True | True | 207.4/1.53/10.2 | 52.6/1.75/6.0 | 7.8% | 14.7% | 2176.48 |
| ORB/NQ_ASIA-RR6 | rr 5/TP1 1.75R | True | True | 207.0/1.54/10.3 | 52.1/1.75/6.0 | 7.8% | 15.5% | 2142.37 |
| ORB/NQ_ASIA-RR6 | rr 6/TP1 2R | False | True | 234.0/1.59/11.8 | 57.0/1.79/6.0 | 5.4% | 11.9% | 2134.48 |
| ORB/NQ_ASIA-RR6 | rr 3.5/TP1 1.8R | False | True | 201.6/1.52/10.2 | 49.9/1.71/6.0 | 16.9% | 12.9% | 2118.86 |
| ORB/NQ_ASIA-RR6 | rr 4/TP1 1.8R | False | True | 200.4/1.51/10.2 | 52.0/1.74/6.0 | 12.6% | 14.1% | 2107.91 |
| ORB/NQ_ASIA-RR6 | rr 2.5/TP1 2R | True | True | 214.0/1.54/11.0 | 57.8/1.80/6.0 | 29.6% | 5.0% | 2095.26 |
| ORB/NQ_ASIA-RR6 | rr 3.5/TP1 1.75R | False | True | 201.2/1.52/10.3 | 49.5/1.71/6.0 | 16.9% | 13.7% | 2085.85 |
| ORB/NQ_ASIA-RR6 | rr 5/TP1 2R | False | True | 226.9/1.57/11.8 | 56.4/1.78/6.0 | 8.0% | 11.9% | 2075.04 |
| ORB/NQ_ASIA-RR6 | rr 4/TP1 1.75R | False | True | 200.1/1.52/10.3 | 51.6/1.74/6.0 | 12.6% | 15.0% | 2074.99 |
| ORB/NQ_ASIA-RR6 | rr 3/TP1 2.25R | False | True | 234.4/1.58/12.2 | 58.5/1.80/6.0 | 23.6% | 6.0% | 2074.40 |
| NQ NY ORB R11 | rr 3/TP1 1.4R | False | True | 118.8/1.46/6.1 | 19.0/1.34/6.0 | 20.6% | 31.3% | 2017.64 |
| ORB/NQ_ASIA-RR6 | rr 4/TP1 2R | False | True | 218.9/1.55/11.8 | 55.9/1.78/6.0 | 13.0% | 11.4% | 2006.36 |

## Interpretation

- Low full-TP rate alone did not mean every TP2 was too far. The best rows had to preserve R production, PF, DD, and recent behavior.
- `test_closer_target` means a closer target preserved the baseline under the strict near-intact screen. `research_only_closer` means a closer target improved some behavior but gave up too much edge for direct promotion. `keep_baseline` means no closer target cleared even the loose screen.