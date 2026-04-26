# ALPHA_V1 ORB Re-Entry Exploration

- Window: `2024-04-17` to `2026-04-17`
- Scope: the three ORB legs in `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`)
- Variants: `cap=1` baseline, `cap=2` (one same-day re-entry), `cap=0` uncapped
- Regime lens: causal combined trend x vol buckets, then re-entry-only gates

## Combined ORB Sleeve

| variant | fills | total_r | delta_vs_cap1_r | sharpe_ratio | max_drawdown_r | calmar_ratio | negative_days |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cap1_baseline | 579 | 91.04 | 0 | 2.24 | -9.88 | 4.65 | 143 |
| cap2_one_reentry | 748 | 116 | 24.86 | 2.56 | -12.92 | 4.53 | 157 |
| cap0_uncapped | 796 | 115 | 24.26 | 2.45 | -15.17 | 3.84 | 162 |

## nq_asia_orb_long

| variant | cap | signals | fills | reentry_fills | reentry_days | max_trades_day | win_rate_pct | avg_r | total_r | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cap1_baseline | 1 | 168 | 134 | 0 | 0 | 1 | 50 | 0.40 | 53.76 | 4.13 | -6 |
| cap2_one_reentry | 2 | 332 | 140 | 6 | 6 | 2 | 50.71 | 0.43 | 60.72 | 4.40 | -6 |
| cap0_uncapped | 0 | 332 | 140 | 6 | 6 | 2 | 50.71 | 0.43 | 60.72 | 4.40 | -6 |

### Uncapped First Trade vs Re-Entries

| bucket | fills | win_rate_pct | avg_r | total_r | profit_factor | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| first_trades | 134 | 50 | 0.40 | 53.76 | 1.81 | 4.13 | -6 |
| reentries_only | 6 | 66.67 | 1.16 | 6.96 | 4.29 | 9.18 | -1 |

- Re-entry days: `6`
- Max trades in one session-day: `2`
- Trades-per-day distribution: `{'1': 128, '2': 6}`

### Top Re-Entry Regimes

| bucket | trades | avg_r | total_r | win_rate_pct | profit_factor | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- |

## es_asia_orb_long

| variant | cap | signals | fills | reentry_fills | reentry_days | max_trades_day | win_rate_pct | avg_r | total_r | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cap1_baseline | 1 | 313 | 268 | 0 | 0 | 1 | 56.72 | 0.14 | 38.70 | 2.41 | -5.82 |
| cap2_one_reentry | 2 | 1451 | 352 | 84 | 84 | 2 | 55.97 | 0.13 | 44.88 | 2.16 | -5.84 |
| cap0_uncapped | 0 | 1451 | 375 | 107 | 84 | 4 | 55.47 | 0.12 | 46.39 | 2.11 | -5.75 |

### Uncapped First Trade vs Re-Entries

| bucket | fills | win_rate_pct | avg_r | total_r | profit_factor | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| first_trades | 268 | 56.72 | 0.14 | 38.70 | 1.39 | 2.41 | -5.82 |
| reentries_only | 107 | 52.34 | 0.07 | 7.70 | 1.21 | 1.30 | -7.22 |

- Re-entry days: `84`
- Max trades in one session-day: `4`
- Trades-per-day distribution: `{'1': 184, '2': 64, '3': 17, '4': 3}`

### Top Re-Entry Regimes

| bucket | trades | avg_r | total_r | win_rate_pct | profit_factor | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- |
| sideways_medium_vol | 15 | 0.51 | 7.62 | 73.33 | 4.59 | -1.26 |
| bear_high_vol | 20 | 0.09 | 1.83 | 50 | 1.27 | -3.25 |
| bull_low_vol | 23 | 0.04 | 0.90 | 52.17 | 1.10 | -3.22 |
| bull_medium_vol | 7 | -0.01 | -0.09 | 57.14 | 0.97 | -2 |
| sideways_low_vol | 4 | -0.03 | -0.11 | 50 | 0.94 | -1 |

## es_ny_orb_long

| variant | cap | signals | fills | reentry_fills | reentry_days | max_trades_day | win_rate_pct | avg_r | total_r | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cap1_baseline | 1 | 228 | 177 | 0 | 0 | 1 | 62.15 | 0.12 | 21.44 | 1.76 | -9.74 |
| cap2_one_reentry | 2 | 839 | 256 | 79 | 79 | 2 | 61.33 | 0.14 | 35.39 | 1.92 | -13.12 |
| cap0_uncapped | 0 | 839 | 281 | 104 | 79 | 4 | 60.50 | 0.12 | 33.28 | 1.66 | -15.12 |

### Uncapped First Trade vs Re-Entries

| bucket | fills | win_rate_pct | avg_r | total_r | profit_factor | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| first_trades | 177 | 62.15 | 0.12 | 21.44 | 1.31 | 1.76 | -9.74 |
| reentries_only | 104 | 57.69 | 0.11 | 11.84 | 1.26 | 1.50 | -9.07 |

- Re-entry days: `79`
- Max trades in one session-day: `4`
- Trades-per-day distribution: `{'1': 98, '2': 58, '3': 17, '4': 4}`

### Top Re-Entry Regimes

| bucket | trades | avg_r | total_r | win_rate_pct | profit_factor | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- |
| sideways_low_vol | 17 | 0.42 | 7.06 | 64.71 | 2.18 | -3 |
| bull_low_vol | 23 | 0.18 | 4.03 | 56.52 | 1.40 | -6.03 |
| bull_high_vol | 20 | 0.06 | 1.23 | 60 | 1.15 | -2.50 |
| bear_medium_vol | 8 | 0.12 | 0.95 | 75 | 1.48 | -2 |
| sideways_medium_vol | 10 | 0 | 0 | 50 | 1 | -3 |

## Re-Entry Regime Correlation

| bucket | trades | avg_r | total_r | win_rate_pct | profit_factor | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- |
| sideways_medium_vol | 26 | 0.35 | 9.20 | 65.38 | 2.29 | -3 |
| sideways_low_vol | 23 | 0.36 | 8.39 | 60.87 | 1.93 | -3 |
| bull_low_vol | 46 | 0.11 | 4.93 | 54.35 | 1.26 | -6.03 |
| bull_medium_vol | 9 | 0.38 | 3.45 | 66.67 | 2.15 | -2 |
| bear_medium_vol | 10 | 0.27 | 2.73 | 80 | 2.37 | -2 |
| bear_high_vol | 35 | 0.05 | 1.70 | 51.43 | 1.12 | -3.25 |
| bull_high_vol | 36 | -0.02 | -0.55 | 50 | 0.96 | -3.09 |
| sideways_high_vol | 29 | -0.05 | -1.43 | 44.83 | 0.89 | -6.77 |

## Re-Entry-Only Gate Tests

| gate | regimes | fills | total_r | delta_vs_cap1_r | sharpe_ratio | max_drawdown_r | negative_days |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bull_high_vol | bull_high_vol | 615 | 91.50 | 0.46 | 2.23 | -10.04 | 148 |
| bull_medium_or_high_vol | bull_medium_vol, bull_high_vol | 624 | 95.95 | 4.91 | 2.32 | -11.04 | 147 |
| bull_expansion_plus_sideways_high_vol | bull_medium_vol, bull_high_vol, sideways_high_vol | 653 | 93.99 | 2.95 | 2.22 | -11.41 | 153 |
| all_high_vol | bear_high_vol, bull_high_vol, sideways_high_vol | 679 | 91.24 | 0.20 | 2.14 | -13.04 | 156 |

