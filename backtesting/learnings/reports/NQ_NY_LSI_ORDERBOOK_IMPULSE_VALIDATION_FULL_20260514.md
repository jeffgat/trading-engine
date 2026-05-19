# NQ NY LSI Order-Book Impulse Diagnostic

- Objective: test the discretionary reversal-momentum idea using true DataBento MBP-10 order-book data around 1m/2m/3m LSI candidate fills.
- Feature: aligned aggressive trade volume, abnormal volume rate, aligned midpoint velocity, and top-of-book/depth imbalance during the signal confirmation bar.
- Scored trade window: `2023-01-01` through `2025-04-01`.
- Data files used: `541` MBP-10 windows from `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/raw/orderbook/NQ/mbp-10`.
- Missing order-book matches: `7` candidate fills.
- Warning: thresholds below are same-period diagnostics on sparse windows. They are evidence for feature design, not deployable gates until frozen on pre-holdout data.

## Best Diagnostic Gates

| Candidate | Gate | Threshold | Trades | PF | Avg R | Total R | DD | Calmar |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `aligned_depth_imbalance_3_mean_q80` | 0.019 | 21 | 2.302 | 0.434 | 9.12 | -4.00 | 2.28 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `aggression_imbalance_q60` | 0.143 | 33 | 1.733 | 0.289 | 9.53 | -2.00 | 4.76 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `aligned_depth_imbalance_3_mean_q80` | 0.021 | 28 | 2.905 | 0.544 | 15.24 | -2.00 | 7.62 |
| `htf_lsi_2m_anchor` | `aligned_depth_imbalance_3_mean_q60` | 0.003 | 71 | 1.670 | 0.289 | 20.54 | -8.48 | 2.42 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `pressure_score_q60` | 0.038 | 13 | 3.383 | 0.550 | 7.15 | -1.00 | 7.15 |

## Baselines

| Candidate | Trades | PF | Avg R | Total R | DD | Calmar | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 106 | 1.367 | 0.152 | 16.14 | -6.63 | 2.43 | 98.1% |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 85 | 1.615 | 0.239 | 20.30 | -7.08 | 2.87 | 97.6% |
| `add_3m_hourly_atr12p5_b3_a7p5` | 140 | 1.153 | 0.071 | 9.93 | -7.50 | 1.32 | 99.3% |
| `htf_lsi_2m_anchor` | 180 | 1.262 | 0.127 | 22.92 | -11.14 | 2.06 | 98.9% |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 33 | 2.055 | 0.320 | 10.55 | -2.94 | 3.58 | 100.0% |

## Impulse Score Quartiles

| Candidate | Bucket | Trades | Score Range | PF | Avg R | Total R | DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | q1_low | 26 | 0.000-0.001 | 1.312 | 0.132 | 3.43 | -3.07 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | q2 | 26 | 0.001-0.002 | 1.958 | 0.295 | 7.66 | -3.50 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | q3 | 26 | 0.002-0.006 | 1.585 | 0.247 | 6.43 | -2.50 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | q4_high | 26 | 0.006-0.050 | 0.849 | -0.075 | -1.96 | -5.02 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | q1_low | 21 | 0.000-0.001 | 1.442 | 0.189 | 3.98 | -3.57 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | q2 | 21 | 0.001-0.002 | 1.689 | 0.230 | 4.82 | -3.00 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | q3 | 20 | 0.002-0.005 | 2.838 | 0.551 | 11.03 | -1.00 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | q4_high | 21 | 0.006-0.025 | 0.990 | -0.005 | -0.10 | -4.60 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q1_low | 35 | 0.000-0.000 | 0.832 | -0.091 | -3.18 | -8.13 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q2 | 35 | 0.000-0.001 | 1.194 | 0.089 | 3.10 | -6.02 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q3 | 34 | 0.001-0.003 | 1.366 | 0.161 | 5.48 | -5.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q4_high | 35 | 0.003-0.024 | 1.269 | 0.115 | 4.03 | -4.71 |
| `htf_lsi_2m_anchor` | q1_low | 45 | 0.000-0.000 | 1.761 | 0.302 | 13.59 | -5.03 |
| `htf_lsi_2m_anchor` | q2 | 44 | 0.000-0.002 | 1.101 | 0.057 | 2.52 | -6.31 |
| `htf_lsi_2m_anchor` | q3 | 44 | 0.002-0.004 | 1.256 | 0.133 | 5.85 | -5.87 |
| `htf_lsi_2m_anchor` | q4_high | 45 | 0.004-0.057 | 0.979 | -0.010 | -0.47 | -5.48 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | q1_low | 9 | 0.000-0.000 | 1.990 | 0.330 | 2.97 | -1.00 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | q2 | 8 | 0.000-0.001 | 2.464 | 0.366 | 2.93 | -1.00 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | q3 | 8 | 0.001-0.003 | 1.904 | 0.339 | 2.71 | -1.00 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | q4_high | 8 | 0.003-0.008 | 1.969 | 0.242 | 1.94 | -1.00 |

## Feature Distribution

| Candidate | Trades | Impulse p50 | Impulse p75 | Pressure p50 | Mid Move p50 | Agg Imb p50 | Depth3 p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 106 | 0.002 | 0.006 | 0.042 | 49.750 | 0.113 | -0.002 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 85 | 0.002 | 0.006 | 0.042 | 42.500 | 0.116 | -0.003 |
| `add_3m_hourly_atr12p5_b3_a7p5` | 140 | 0.001 | 0.003 | 0.026 | 77.500 | 0.079 | -0.002 |
| `htf_lsi_2m_anchor` | 180 | 0.002 | 0.004 | 0.037 | 54.500 | 0.091 | -0.007 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 33 | 0.001 | 0.003 | 0.033 | 37.500 | 0.090 | -0.008 |

## Interpretation

- `impulse_score` is strict: it needs aligned aggression, abnormal volume, and aligned midpoint displacement.
- `pressure_score` is looser: it rewards one-way aggression and book support even when price displacement is smaller.
- A production rule should be selected from pre-holdout validation, then replayed on untouched holdout windows and exact execution data.