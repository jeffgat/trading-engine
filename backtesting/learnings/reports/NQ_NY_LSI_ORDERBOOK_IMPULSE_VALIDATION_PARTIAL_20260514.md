# NQ NY LSI Order-Book Impulse Diagnostic

- Objective: test the discretionary reversal-momentum idea using true DataBento MBP-10 order-book data around 1m/2m/3m LSI candidate fills.
- Feature: aligned aggressive trade volume, abnormal volume rate, aligned midpoint velocity, and top-of-book/depth imbalance during the signal confirmation bar.
- Scored trade window: `2023-01-01` through `2025-04-01`.
- Data files used: `186` MBP-10 windows from `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/raw/orderbook/NQ/mbp-10`.
- Missing order-book matches: `512` candidate fills.
- Warning: thresholds below are same-period diagnostics on sparse windows. They are evidence for feature design, not deployable gates until frozen on pre-holdout data.

## Best Diagnostic Gates

| Candidate | Gate | Threshold | Trades | PF | Avg R | Total R | DD | Calmar |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| n/a | n/a | n/a | 0 | 0.000 | 0.000 | 0.00 | 0.00 | 0.00 |

## Baselines

| Candidate | Trades | PF | Avg R | Total R | DD | Calmar | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 106 | 1.367 | 0.152 | 16.14 | -6.63 | 2.43 | 6.6% |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 85 | 1.615 | 0.239 | 20.30 | -7.08 | 2.87 | 7.1% |
| `add_3m_hourly_atr12p5_b3_a7p5` | 140 | 1.153 | 0.071 | 9.93 | -7.50 | 1.32 | 6.4% |
| `htf_lsi_2m_anchor` | 180 | 1.262 | 0.127 | 22.92 | -11.14 | 2.06 | 5.0% |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 33 | 2.055 | 0.320 | 10.55 | -2.94 | 3.58 | 3.0% |

## Impulse Score Quartiles

| Candidate | Bucket | Trades | Score Range | PF | Avg R | Total R | DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_3m_hourly_atr12p5_b3_a7p5` | q1_low | 3 | 0.000-0.000 | 0.000 | 1.185 | 3.56 | 0.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q2 | 2 | 0.001-0.001 | 1.500 | 0.250 | 0.50 | 0.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q3 | 2 | 0.002-0.002 | 0.429 | -0.286 | -0.57 | 0.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q4_high | 2 | 0.003-0.005 | 1.571 | 0.286 | 0.57 | 0.00 |
| `htf_lsi_2m_anchor` | q1_low | 3 | 0.000-0.002 | 1.200 | 0.133 | 0.40 | -1.00 |
| `htf_lsi_2m_anchor` | q2 | 2 | 0.002-0.002 | 1.881 | 0.440 | 0.88 | 0.00 |
| `htf_lsi_2m_anchor` | q3 | 2 | 0.005-0.006 | 0.000 | 0.616 | 1.23 | 0.00 |
| `htf_lsi_2m_anchor` | q4_high | 2 | 0.007-0.008 | 0.000 | 0.464 | 0.93 | 0.00 |

## Feature Distribution

| Candidate | Trades | Impulse p50 | Impulse p75 | Pressure p50 | Mid Move p50 | Agg Imb p50 | Depth3 p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 106 | 0.002 | 0.007 | 0.054 | 60.000 | 0.123 | -0.015 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 85 | 0.004 | 0.007 | 0.078 | 62.500 | 0.140 | -0.005 |
| `add_3m_hourly_atr12p5_b3_a7p5` | 140 | 0.001 | 0.002 | 0.024 | 94.000 | 0.083 | -0.003 |
| `htf_lsi_2m_anchor` | 180 | 0.002 | 0.006 | 0.039 | 86.000 | 0.112 | -0.011 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 33 | 0.002 | 0.002 | 0.027 | 103.500 | 0.076 | -0.015 |

## Interpretation

- `impulse_score` is strict: it needs aligned aggression, abnormal volume, and aligned midpoint displacement.
- `pressure_score` is looser: it rewards one-way aggression and book support even when price displacement is smaller.
- A production rule should be selected from pre-holdout validation, then replayed on untouched holdout windows and exact execution data.