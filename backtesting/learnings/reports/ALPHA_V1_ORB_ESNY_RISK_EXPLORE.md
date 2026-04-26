# ALPHA_V1 ORB ES NY Risk Explore

- Scope: combined ORB sleeve only (`NQ Asia`, `ES Asia`, `ES NY`).
- Profile basis:
  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.
  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.
- Dollar sizing basis: `NQ Asia=$250`, `ES Asia=$250`, `ES NY=$400` from `execution/config/exec_configs.json`.
- Fresh-account model: one fresh account max per day, next-day trigger every `$1,000` move in the combined master daily USD stream.
- Resolution model: `+$2,500` payout / `$-2,000` breach.

## ES NY Trade-2 Frequency

| period | trade_days | days_with_2_trades | days_with_2_trades_pct | first_trade_avg_r | first_trade_total_r | second_trade_avg_r | second_trade_total_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | 845 | 295 | 34.91 | 0.15 | 128 | 0.13 | 38.55 |
| 2024 | 90 | 41 | 45.56 | 0.02 | 1.73 | 0.30 | 12.37 |
| 2025 | 88 | 32 | 36.36 | 0.20 | 17.70 | 0.03 | 0.93 |
| 2026 YTD | 22 | 15 | 68.18 | 0.13 | 2.79 | 0.21 | 3.14 |

## Portfolio Variants

| period | variant | starts | payouts | breaches | open | resolved_payout_rate | avg_start_gap_days | net_usd | max_dd_usd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | Current baseline | 264 | 222 | 39 | 3 | 85.06 | 13.78 | 140872 | -5893 |
| Last 10y available | Optimized baseline | 317 | 264 | 49 | 4 | 84.35 | 11.48 | 167820 | -7214 |
| Last 10y available | Optimized ES_NY trade2 $0 | 276 | 233 | 40 | 3 | 85.35 | 13.15 | 152400 | -5874 |
| Last 10y available | Optimized ES_NY trade2 $100 | 278 | 237 | 39 | 2 | 85.87 | 13.06 | 156255 | -6189 |
| Last 10y available | Optimized ES_NY trade2 $200 | 306 | 258 | 46 | 2 | 84.87 | 11.84 | 160110 | -6531 |
| Last 10y available | Optimized ES_NY trade2 $250 | 296 | 251 | 42 | 3 | 85.67 | 12.24 | 162037 | -6702 |
| Last 10y available | Optimized ES_NY trade2 $300 | 301 | 252 | 45 | 4 | 84.85 | 12.09 | 163965 | -6873 |
| Last 10y available | Optimized ES_NY all $300 | 263 | 227 | 32 | 4 | 87.64 | 13.81 | 151207 | -6416 |
| Last 10y available | Optimized ES_NY all $250 | 240 | 208 | 28 | 4 | 88.14 | 15.18 | 142900 | -6017 |
| 2024 | Current baseline | 25 | 17 | 5 | 3 | 77.27 | 14.42 | 8472 | -3244 |
| 2024 | Optimized baseline | 30 | 24 | 2 | 4 | 92.31 | 12.34 | 15539 | -2599 |
| 2024 | Optimized ES_NY trade2 $0 | 28 | 21 | 3 | 4 | 87.50 | 12.81 | 10590 | -2577 |
| 2024 | Optimized ES_NY trade2 $100 | 25 | 19 | 3 | 3 | 86.36 | 14.42 | 11827 | -2529 |
| 2024 | Optimized ES_NY trade2 $200 | 26 | 21 | 3 | 2 | 87.50 | 13.84 | 13064 | -2481 |
| 2024 | Optimized ES_NY trade2 $250 | 27 | 23 | 1 | 3 | 95.83 | 13.31 | 13683 | -2457 |
| 2024 | Optimized ES_NY trade2 $300 | 29 | 23 | 3 | 3 | 88.46 | 12.36 | 14301 | -2432 |
| 2024 | Optimized ES_NY all $300 | 25 | 18 | 2 | 5 | 90 | 14.42 | 14129 | -2291 |
| 2024 | Optimized ES_NY all $250 | 22 | 19 | 0 | 3 | 100 | 16.48 | 13424 | -2137 |
| 2025 | Current baseline | 35 | 29 | 3 | 3 | 90.62 | 10.56 | 23202 | -3104 |
| 2025 | Optimized baseline | 38 | 30 | 4 | 4 | 88.24 | 9.84 | 24964 | -3982 |
| 2025 | Optimized ES_NY trade2 $0 | 32 | 29 | 1 | 2 | 96.67 | 11.55 | 24593 | -2782 |
| 2025 | Optimized ES_NY trade2 $100 | 34 | 30 | 2 | 2 | 93.75 | 10.85 | 24686 | -3082 |
| 2025 | Optimized ES_NY trade2 $200 | 36 | 32 | 2 | 2 | 94.12 | 10.23 | 24779 | -3382 |
| 2025 | Optimized ES_NY trade2 $250 | 34 | 29 | 3 | 2 | 90.62 | 10.85 | 24825 | -3532 |
| 2025 | Optimized ES_NY trade2 $300 | 34 | 28 | 2 | 4 | 93.33 | 11.03 | 24871 | -3682 |
| 2025 | Optimized ES_NY all $300 | 31 | 26 | 2 | 3 | 92.86 | 11.93 | 23101 | -3379 |
| 2025 | Optimized ES_NY all $250 | 30 | 26 | 1 | 3 | 96.30 | 12.34 | 22170 | -3078 |
| 2026 YTD | Current baseline | 6 | 2 | 1 | 3 | 66.67 | 14.20 | 2596 | -2166 |
| 2026 YTD | Optimized baseline | 12 | 8 | 2 | 2 | 80 | 6.45 | 4101 | -3736 |
| 2026 YTD | Optimized ES_NY trade2 $0 | 6 | 2 | 0 | 4 | 100 | 14.20 | 2846 | -2136 |
| 2026 YTD | Optimized ES_NY trade2 $100 | 7 | 3 | 1 | 3 | 75 | 11 | 3159 | -2486 |
| 2026 YTD | Optimized ES_NY trade2 $200 | 9 | 4 | 2 | 3 | 66.67 | 8.88 | 3473 | -2836 |
| 2026 YTD | Optimized ES_NY trade2 $250 | 9 | 5 | 1 | 3 | 83.33 | 9.75 | 3630 | -3061 |
| 2026 YTD | Optimized ES_NY trade2 $300 | 13 | 7 | 3 | 3 | 70 | 6.50 | 3787 | -3286 |
| 2026 YTD | Optimized ES_NY all $300 | 11 | 5 | 1 | 5 | 83.33 | 7.80 | 3508 | -3183 |
| 2026 YTD | Optimized ES_NY all $250 | 9 | 4 | 1 | 4 | 80 | 8.88 | 3212 | -2907 |
