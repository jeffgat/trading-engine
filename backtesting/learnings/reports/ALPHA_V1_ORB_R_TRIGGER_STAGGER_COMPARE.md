# ALPHA_V1 ORB R-Trigger Stagger Compare

- Scope: the three ORB legs from `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`) plus the combined portfolio.
- Rules compared:
  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.
  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.
- Stagger model: seed one account on the first trading day of each window, then add a new account each time the master daily stream moves another `+/-2R` from the last launch anchor.
- Resolution model: `+5R` payout / `-4R` breach on the same daily R stream, no per-start minimum-day gate.
- `2026 YTD` is partial in this repo: `2026-01-01` to `2026-03-24`.

## Portfolio

| period | rules | trades | starts | payouts | breaches | open | payout_rate_starts | breach_rate_starts | resolved_payout_rate | max_dd_r | net_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | Current single-trade legs | 2989 | 631 | 434 | 195 | 2 | 68.78 | 30.90 | 69 | -21.18 | 360 |
| Last 10y available | Optimized rules | 3418 | 733 | 515 | 215 | 3 | 70.26 | 29.33 | 70.55 | -21.38 | 440 |
| 2024 | Current single-trade legs | 300 | 57 | 37 | 18 | 2 | 64.91 | 31.58 | 67.27 | -9.52 | 27.57 |
| 2024 | Optimized rules | 353 | 61 | 42 | 15 | 4 | 68.85 | 24.59 | 73.68 | -10.54 | 48.41 |
| 2025 | Current single-trade legs | 305 | 75 | 57 | 16 | 2 | 76 | 21.33 | 78.08 | -9.88 | 58.10 |
| 2025 | Optimized rules | 348 | 80 | 63 | 15 | 2 | 78.75 | 18.75 | 80.77 | -11.31 | 62.15 |
| 2026 YTD | Current single-trade legs | 71 | 14 | 8 | 3 | 3 | 57.14 | 21.43 | 72.73 | -8.06 | 10.40 |
| 2026 YTD | Optimized rules | 90 | 20 | 11 | 7 | 2 | 55 | 35 | 61.11 | -11.94 | 14.53 |

## Per-Leg Deltas

| period | subject | trade_delta | start_delta | payout_delta | breach_delta | open_delta | resolved_payout_rate_delta | net_r_delta | max_dd_r_delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | Portfolio | 429 | 102 | 81 | 20 | 1 | 1.55 | 80.47 | -0.20 |
| Last 10y available | NQ Asia | 37 | 2 | 7 | -5 | 0 | 2.45 | 22.61 | 1.25 |
| Last 10y available | ES Asia | 97 | 9 | 9 | -1 | 1 | 1.23 | 19.30 | 0.50 |
| Last 10y available | ES NY | 295 | 44 | 26 | 18 | 0 | -2.71 | 38.55 | -2.26 |
| 2024 | Portfolio | 53 | 4 | 5 | -3 | 2 | 6.41 | 20.84 | -1.02 |
| 2024 | NQ Asia | 4 | -2 | -2 | 0 | 0 | -2.02 | 6.43 | 1.29 |
| 2024 | ES Asia | 8 | 1 | 0 | -2 | 3 | 8.89 | 2.05 | 0 |
| 2024 | ES NY | 41 | 10 | 9 | 2 | -1 | 26.67 | 12.37 | 0.39 |
| 2025 | Portfolio | 43 | 5 | 6 | -1 | 0 | 2.69 | 4.05 | -1.43 |
| 2025 | NQ Asia | 3 | -3 | -3 | 0 | 0 | -0.92 | 0.58 | 0 |
| 2025 | ES Asia | 8 | 3 | 4 | -1 | 0 | 5.65 | 2.54 | -1.02 |
| 2025 | ES NY | 32 | 4 | 1 | 4 | -1 | -12.28 | 0.93 | -3.51 |
| 2026 YTD | Portfolio | 19 | 6 | 3 | 4 | -1 | -11.62 | 4.13 | -3.88 |
| 2026 YTD | NQ Asia | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026 YTD | ES Asia | 4 | -2 | 0 | -2 | 0 | 66.67 | 1 | 0.46 |
| 2026 YTD | ES NY | 15 | 8 | 5 | 1 | 2 | 83.33 | 3.14 | -3.53 |

## Full Per-Leg Comparison

| period | subject | rules | trades | starts | payouts | breaches | open | resolved_payout_rate | max_dd_r | net_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | NQ Asia | Current single-trade legs | 722 | 224 | 171 | 49 | 4 | 77.73 | -10.60 | 130 |
| Last 10y available | ES Asia | Current single-trade legs | 1422 | 210 | 164 | 42 | 4 | 79.61 | -14.18 | 102 |
| Last 10y available | ES NY | Current single-trade legs | 845 | 161 | 113 | 45 | 3 | 71.52 | -10.86 | 128 |
| Last 10y available | NQ Asia | Optimized rules | 759 | 226 | 178 | 44 | 4 | 80.18 | -9.35 | 152 |
| Last 10y available | ES Asia | Optimized rules | 1519 | 219 | 173 | 41 | 5 | 80.84 | -13.68 | 121 |
| Last 10y available | ES NY | Optimized rules | 1140 | 205 | 139 | 63 | 3 | 68.81 | -13.12 | 166 |
| 2024 | NQ Asia | Current single-trade legs | 68 | 15 | 10 | 1 | 4 | 90.91 | -9.89 | 7.60 |
| 2024 | ES Asia | Current single-trade legs | 142 | 24 | 16 | 4 | 4 | 80 | -5 | 18.24 |
| 2024 | ES NY | Current single-trade legs | 90 | 14 | 3 | 6 | 5 | 33.33 | -9.74 | 1.73 |
| 2024 | NQ Asia | Optimized rules | 72 | 13 | 8 | 1 | 4 | 88.89 | -8.60 | 14.03 |
| 2024 | ES Asia | Optimized rules | 150 | 25 | 16 | 2 | 7 | 88.89 | -5 | 20.29 |
| 2024 | ES NY | Optimized rules | 131 | 24 | 12 | 8 | 4 | 60 | -9.35 | 14.10 |
| 2025 | NQ Asia | Current single-trade legs | 73 | 30 | 25 | 2 | 3 | 92.59 | -5 | 22.25 |
| 2025 | ES Asia | Current single-trade legs | 144 | 23 | 18 | 2 | 3 | 90 | -4.69 | 18.15 |
| 2025 | ES NY | Current single-trade legs | 88 | 22 | 15 | 4 | 3 | 78.95 | -9.61 | 17.70 |
| 2025 | NQ Asia | Optimized rules | 76 | 27 | 22 | 2 | 3 | 91.67 | -5 | 22.83 |
| 2025 | ES Asia | Optimized rules | 152 | 26 | 22 | 1 | 3 | 95.65 | -5.71 | 20.69 |
| 2025 | ES NY | Optimized rules | 120 | 26 | 16 | 8 | 2 | 66.67 | -13.12 | 18.63 |
| 2026 YTD | NQ Asia | Current single-trade legs | 15 | 6 | 1 | 1 | 4 | 50 | -4 | 5.84 |
| 2026 YTD | ES Asia | Current single-trade legs | 34 | 6 | 1 | 2 | 3 | 33.33 | -4.82 | 1.77 |
| 2026 YTD | ES NY | Current single-trade legs | 22 | 2 | 0 | 0 | 2 | 0 | -2 | 2.79 |
| 2026 YTD | NQ Asia | Optimized rules | 15 | 6 | 1 | 1 | 4 | 50 | -4 | 5.84 |
| 2026 YTD | ES Asia | Optimized rules | 38 | 4 | 1 | 0 | 3 | 100 | -4.36 | 2.77 |
| 2026 YTD | ES NY | Optimized rules | 37 | 10 | 5 | 1 | 4 | 83.33 | -5.53 | 5.93 |