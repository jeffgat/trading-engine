# ALPHA_V1 Final Target Exact Sweep

- Objective: rerun the active `ALPHA_V1` legs through the production backtest engine while varying only the final target (`rr`) and keeping the first scale distance fixed.
- Method: for each leg, preserve `tp1_distance_in_R = rr * tp1_ratio`, then set `tp1_ratio = fixed_tp1_r / new_rr` for each tested final target.
- Shared recent window: `2024-01-01` onward.

## HTF_LSI/NQ_NY-L24

| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Recent Win Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.5 | 75.9 | 10.8 | 7.01 | 32.0 | 5.2 | 6.11 | 58.1% |
| 2.0 | 87.7 | 10.0 | 8.74 | 30.5 | 5.2 | 5.82 | 57.1% |
| 2.5 | 81.5 | 11.1 | 7.34 | 30.7 | 5.2 | 5.86 | 57.1% |
| 3.0 | 88.0 | 10.9 | 8.04 | 33.7 | 5.2 | 6.43 | 57.1% |
| 3.5 | 89.3 | 10.9 | 8.16 | 34.8 | 5.2 | 6.64 | 57.1% |

## ORB/NQ_ASIA-RR6

| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Recent Win Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2.0 | 178.2 | 9.6 | 18.65 | 49.3 | 7.7 | 6.38 | 47.4% |
| 2.5 | 192.7 | 9.4 | 20.52 | 53.4 | 6.3 | 8.44 | 47.4% |
| 3.0 | 196.6 | 9.0 | 21.88 | 50.0 | 7.0 | 7.09 | 47.4% |
| 4.0 | 198.6 | 10.2 | 19.55 | 52.5 | 6.0 | 8.74 | 47.4% |
| 5.0 | 205.8 | 10.2 | 20.27 | 53.4 | 6.0 | 8.90 | 47.4% |
| 6.0 | 212.0 | 10.2 | 20.87 | 54.5 | 6.1 | 8.99 | 47.4% |

## ORB/ES_ASIA-RR1.5

| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Recent Win Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.5 | 146.6 | 12.3 | 11.95 | 47.0 | 5.8 | 8.08 | 56.9% |

## ORB/ES_NY-RR5

| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Recent Win Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.5 | 77.7 | 11.7 | 6.65 | 12.4 | 8.4 | 1.48 | 62.7% |
| 2.0 | 81.6 | 11.7 | 6.96 | 10.9 | 9.7 | 1.13 | 62.7% |
| 2.5 | 94.5 | 11.6 | 8.15 | 14.6 | 9.6 | 1.52 | 62.7% |
| 3.0 | 107.9 | 12.9 | 8.36 | 15.6 | 9.6 | 1.62 | 62.7% |
| 4.0 | 129.0 | 11.4 | 11.30 | 19.1 | 9.6 | 1.98 | 62.7% |
| 5.0 | 142.6 | 10.9 | 13.13 | 21.2 | 9.7 | 2.18 | 62.7% |
