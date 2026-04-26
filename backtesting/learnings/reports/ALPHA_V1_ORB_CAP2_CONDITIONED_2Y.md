# ALPHA_V1 ORB Cap=2 Conditioned Re-Entry

- Window: `2024-04-17` to `2026-04-17`
- Scope: the three ORB legs in `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`)
- Engine rule under test: `orb_trade_max_per_session=2` plus `orb_reentry_policy=after_nonpositive_first`
- Comparison set: `cap=1` baseline, `cap=2` any re-entry, and the conditioned `cap=2` engine variant
- Regime lens: causal combined trend x vol buckets, then conditioned-re-entry-only gates

## Combined ORB Sleeve

| variant | cap | reentry_policy | fills | total_r | delta_vs_cap1_r | delta_vs_cap2_any_r | sharpe_ratio | max_drawdown_r | calmar_ratio | negative_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cap1_baseline | 1 | any_reentry | 579 | 91.04 | 0 | - | 2.24 | -9.88 | 4.65 | 143 |
| cap2_any_reentry | 2 | any_reentry | 748 | 116 | 24.86 | 0 | 2.56 | -12.92 | 4.53 | 157 |
| cap2_after_nonpositive_first | 2 | after_nonpositive_first | 633 | 108 | 16.86 | -8 | 2.57 | -11.44 | 4.76 | 138 |

## nq_asia_orb_long

| variant | cap | reentry_policy | signals | fills | reentry_fills | reentry_days | max_trades_day | win_rate_pct | avg_r | total_r | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cap1_baseline | 1 | any_reentry | 168 | 134 | 0 | 0 | 1 | 50 | 0.40 | 53.76 | 4.13 | -6 |
| cap2_any_reentry | 2 | any_reentry | 332 | 140 | 6 | 6 | 2 | 50.71 | 0.43 | 60.72 | 4.40 | -6 |
| cap2_after_nonpositive_first | 2 | after_nonpositive_first | 332 | 140 | 6 | 6 | 2 | 50.71 | 0.43 | 60.72 | 4.40 | -6 |

### Conditioned First Trade vs Re-Entries

| bucket | fills | win_rate_pct | avg_r | total_r | profit_factor | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| first_trades | 134 | 50 | 0.40 | 53.76 | 1.81 | 4.13 | -6 |
| reentries_only | 6 | 66.67 | 1.16 | 6.96 | 4.29 | 9.18 | -1 |

- Re-entry days: `6`
- Max trades in one session-day: `2`
- Trades-per-day distribution: `{'1': 128, '2': 6}`

### Top Conditioned Re-Entry Regimes

| bucket | trades | avg_r | total_r | win_rate_pct | profit_factor | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- |
| sideways_high_vol | 2 | 1.57 | 3.13 | 50 | 4.13 | -1 |
| sideways_low_vol | 2 | 0.72 | 1.44 | 50 | 2.44 | 0 |

## es_asia_orb_long

| variant | cap | reentry_policy | signals | fills | reentry_fills | reentry_days | max_trades_day | win_rate_pct | avg_r | total_r | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cap1_baseline | 1 | any_reentry | 313 | 268 | 0 | 0 | 1 | 56.72 | 0.14 | 38.70 | 2.41 | -5.82 |
| cap2_any_reentry | 2 | any_reentry | 1451 | 352 | 84 | 84 | 2 | 55.97 | 0.13 | 44.88 | 2.16 | -5.84 |
| cap2_after_nonpositive_first | 2 | after_nonpositive_first | 1451 | 286 | 18 | 18 | 2 | 56.99 | 0.15 | 42.49 | 2.47 | -5 |

### Conditioned First Trade vs Re-Entries

| bucket | fills | win_rate_pct | avg_r | total_r | profit_factor | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| first_trades | 268 | 56.72 | 0.14 | 38.70 | 1.39 | 2.41 | -5.82 |
| reentries_only | 18 | 61.11 | 0.21 | 3.79 | 1.60 | 3.37 | -2.73 |

- Re-entry days: `18`
- Max trades in one session-day: `2`
- Trades-per-day distribution: `{'1': 250, '2': 18}`

### Top Conditioned Re-Entry Regimes

| bucket | trades | avg_r | total_r | win_rate_pct | profit_factor | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- |
| bear_high_vol | 4 | 0.49 | 1.98 | 75 | 2.98 | -1 |
| sideways_medium_vol | 4 | 0.33 | 1.32 | 75 | 2.32 | -1 |
| bull_high_vol | 4 | 0.21 | 0.86 | 50 | 1.62 | -1 |
| sideways_high_vol | 3 | -0.24 | -0.71 | 33.33 | 0.64 | -2 |
| bear_low_vol | 2 | -0.47 | -0.93 | 50 | 0.07 | -1 |

## es_ny_orb_long

| variant | cap | reentry_policy | signals | fills | reentry_fills | reentry_days | max_trades_day | win_rate_pct | avg_r | total_r | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cap1_baseline | 1 | any_reentry | 228 | 177 | 0 | 0 | 1 | 62.15 | 0.12 | 21.44 | 1.76 | -9.74 |
| cap2_any_reentry | 2 | any_reentry | 839 | 256 | 79 | 79 | 2 | 61.33 | 0.14 | 35.39 | 1.92 | -13.12 |
| cap2_after_nonpositive_first | 2 | after_nonpositive_first | 839 | 207 | 30 | 30 | 2 | 62.32 | 0.14 | 29.99 | 2.04 | -12.12 |

### Conditioned First Trade vs Re-Entries

| bucket | fills | win_rate_pct | avg_r | total_r | profit_factor | sharpe_ratio | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- | --- |
| first_trades | 177 | 62.15 | 0.12 | 21.44 | 1.31 | 1.76 | -9.74 |
| reentries_only | 30 | 63.33 | 0.29 | 8.55 | 1.77 | 3.46 | -6.06 |

- Re-entry days: `30`
- Max trades in one session-day: `2`
- Trades-per-day distribution: `{'1': 147, '2': 30}`

### Top Conditioned Re-Entry Regimes

| bucket | trades | avg_r | total_r | win_rate_pct | profit_factor | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- |
| bear_high_vol | 3 | 0.87 | 2.62 | 66.67 | 3.62 | -1 |
| sideways_medium_vol | 2 | 1 | 2 | 50 | 3 | -1 |
| bull_low_vol | 7 | 0.22 | 1.52 | 57.14 | 1.51 | -2.52 |
| bull_high_vol | 6 | 0.24 | 1.44 | 83.33 | 2.44 | 0 |
| bear_medium_vol | 2 | 0.48 | 0.97 | 100 | - | 0 |

## Conditioned Re-Entry Regime Correlation

| bucket | trades | avg_r | total_r | win_rate_pct | profit_factor | max_drawdown_r |
| --- | --- | --- | --- | --- | --- | --- |
| bear_high_vol | 8 | 0.67 | 5.39 | 75 | 3.70 | -1 |
| sideways_medium_vol | 7 | 0.70 | 4.90 | 71.43 | 3.45 | -1 |
| bull_high_vol | 10 | 0.23 | 2.29 | 70 | 1.97 | -1 |
| sideways_low_vol | 8 | 0.27 | 2.18 | 62.50 | 1.73 | -2 |
| bull_low_vol | 7 | 0.22 | 1.52 | 57.14 | 1.51 | -2.52 |
| sideways_high_vol | 8 | 0.11 | 0.92 | 37.50 | 1.18 | -3.50 |
| bear_low_vol | 3 | -0.64 | -1.93 | 33.33 | 0.03 | -2 |

## Conditioned Re-Entry-Only Gate Tests

| gate | regimes | fills | total_r | delta_vs_cap1_r | delta_vs_conditioned_r | sharpe_ratio | max_drawdown_r | negative_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bull_high_vol | bull_high_vol | 589 | 93.34 | 2.30 | -14.56 | 2.30 | -9.88 | 143 |
| bull_medium_or_high_vol | bull_medium_vol, bull_high_vol | 590 | 96.40 | 5.36 | -11.50 | 2.37 | -9.88 | 142 |
| bull_expansion_plus_sideways_high_vol | bull_medium_vol, bull_high_vol, sideways_high_vol | 598 | 97.32 | 6.28 | -10.58 | 2.37 | -9.88 | 141 |
| all_high_vol | bear_high_vol, bull_high_vol, sideways_high_vol | 605 | 99.65 | 8.61 | -8.25 | 2.42 | -10.56 | 140 |

