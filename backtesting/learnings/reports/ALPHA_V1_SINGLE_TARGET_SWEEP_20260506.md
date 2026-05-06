# ALPHA_V1 Native Single-Target Sweep (2026-05-06)

- Run slug: `alpha_v1_single_target_sweep_20260506`
- Full window: `2016-04-17` to `2026-03-24`; recent windows start `2024-03-24` and `2025-03-24`.
- Scope: active ALPHA_V1 legs plus NQ NY ORB R11.
- Structure: current split ladders compared against native `exit_mode=single_target` with `tp1_ratio=1.0` and RR as the only target.
- Ranking: Calmar-first composite, with R/PF/DD penalties versus each leg's current split baseline.
- Deployability: all single-target rows are `live_native`; exact replay is still required before changing live config.

## Leg Comparison

| Leg | Current Split | Single @ TP1 | Best Single | Best Target | ΔR | ΔPF | ΔDD | Read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORB/ES_ASIA-RR1.5 | 1.5R +145.9R PF 1.28 DD -12.3R Target 21.7% | 1.05R +149.5R PF 1.29 DD -13.1R Target 38.0% | 1.25R +173.7R PF 1.32 DD -13.6R Target 32.2% | 1.25R | 27.86 | 0.04 | 1.35 | mixed |
| ORB/ES_NY-RR5 | 5R +126.6R PF 1.39 DD -10.9R Target 6.4% | 1R +186.4R PF 1.57 DD -8.0R Target 59.8% | 1R +186.4R PF 1.57 DD -8.0R Target 59.8% | 1R | 59.82 | 0.18 | -2.86 | material_upgrade |
| HTF_LSI/NQ_NY-L24 | 3.5R +92.6R PF 1.45 DD -10.9R Target 6.2% | 1.4R +87.2R PF 1.42 DD -10.1R Target 35.8% | 1.5R +83.6R PF 1.39 DD -9.3R Target 33.3% | 1.5R | -8.97 | -0.06 | -1.68 | inferior |
| ORB/NQ_ASIA-RR6 | 6R +213.5R PF 1.55 DD -10.2R Target 5.1% | 1.8R +180.0R PF 1.46 DD -9.9R Target 41.4% | 2R +203.1R PF 1.51 DD -11.0R Target 38.4% | 2R | -10.41 | -0.04 | 0.84 | inferior |
| NQ NY ORB R11 | 3.5R +129.4R PF 1.50 DD -6.0R Target 18.1% | 1.4R +149.2R PF 1.58 DD -6.4R Target 52.4% | 1.4R +149.2R PF 1.58 DD -6.4R Target 52.4% | 1.4R | 19.79 | 0.08 | 0.40 | material_upgrade |

## Top Single-Target Rows

| Leg | Target | Net R | PF | DD | WR | Target% | 2Y R | Read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORB/ES_NY-RR5 | 1R | 186.40 | 1.57 | 8.00 | 61.0% | 59.8% | 44.33 | material_upgrade |
| NQ NY ORB R11 | 1.4R | 149.20 | 1.58 | 6.40 | 53.3% | 52.4% | 20.84 | material_upgrade |
| NQ NY ORB R11 | 1R | 126.22 | 1.59 | 6.00 | 61.6% | 60.9% | 27.24 | mixed |
| NQ NY ORB R11 | 1.25R | 141.85 | 1.59 | 7.00 | 56.2% | 55.2% | 26.24 | material_upgrade |
| NQ NY ORB R11 | 1.5R | 142.21 | 1.52 | 7.50 | 50.7% | 49.6% | 21.24 | mixed |
| ORB/NQ_ASIA-RR6 | 2R | 203.09 | 1.51 | 11.00 | 44.5% | 38.4% | 55.43 | inferior |
| ORB/NQ_ASIA-RR6 | 1.8R | 180.00 | 1.46 | 9.87 | 45.7% | 41.4% | 50.56 | inferior |
| ORB/NQ_ASIA-RR6 | 6R | 274.02 | 1.61 | 15.62 | 36.3% | 6.0% | 56.49 | mixed |
| ORB/NQ_ASIA-RR6 | 5R | 259.04 | 1.57 | 14.75 | 36.3% | 8.9% | 55.47 | mixed |
| ORB/NQ_ASIA-RR6 | 1.75R | 177.65 | 1.46 | 10.02 | 46.4% | 42.5% | 49.59 | inferior |
| ORB/NQ_ASIA-RR6 | 2.25R | 224.91 | 1.55 | 13.00 | 43.1% | 34.8% | 60.22 | mixed |
| ORB/NQ_ASIA-RR6 | 4.5R | 257.63 | 1.57 | 15.25 | 36.6% | 11.5% | 53.82 | mixed |
| ORB/NQ_ASIA-RR6 | 5.5R | 260.99 | 1.58 | 15.62 | 36.3% | 7.1% | 53.49 | mixed |
| ORB/NQ_ASIA-RR6 | 2.5R | 228.59 | 1.55 | 14.30 | 41.3% | 30.8% | 60.12 | mixed |
| ORB/NQ_ASIA-RR6 | 3.25R | 239.30 | 1.54 | 15.29 | 38.0% | 21.6% | 55.11 | mixed |
| ORB/NQ_ASIA-RR6 | 1.25R | 131.02 | 1.38 | 8.06 | 52.8% | 51.1% | 28.32 | inferior |
| ORB/NQ_ASIA-RR6 | 3R | 240.32 | 1.55 | 15.69 | 38.9% | 24.4% | 55.17 | mixed |
| ORB/NQ_ASIA-RR6 | 4R | 240.68 | 1.53 | 15.75 | 36.7% | 14.3% | 54.78 | mixed |
| ORB/NQ_ASIA-RR6 | 2.75R | 227.78 | 1.53 | 14.94 | 39.9% | 27.3% | 50.78 | mixed |
| ORB/NQ_ASIA-RR6 | 3.5R | 240.25 | 1.54 | 16.25 | 37.7% | 18.6% | 51.54 | mixed |
| ORB/ES_ASIA-RR1.5 | 1.25R | 173.72 | 1.32 | 13.62 | 52.7% | 32.2% | 43.71 | mixed |
| NQ NY ORB R11 | 1.75R | 118.06 | 1.39 | 9.00 | 44.6% | 43.5% | 23.24 | inferior |
| ORB/NQ_ASIA-RR6 | 1.5R | 152.20 | 1.41 | 11.62 | 49.0% | 46.5% | 42.05 | inferior |
| ORB/ES_ASIA-RR1.5 | 1.5R | 175.63 | 1.31 | 14.71 | 50.8% | 24.6% | 45.68 | mixed |
| ORB/ES_ASIA-RR1.5 | 1.75R | 178.19 | 1.31 | 14.96 | 49.4% | 19.5% | 38.39 | mixed |