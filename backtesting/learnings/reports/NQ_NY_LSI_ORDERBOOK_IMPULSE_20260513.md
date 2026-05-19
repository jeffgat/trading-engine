# NQ NY LSI Order-Book Impulse Diagnostic

- Objective: test the discretionary reversal-momentum idea using true DataBento MBP-10 order-book data around 1m/2m/3m LSI candidate fills.
- Feature: aligned aggressive trade volume, abnormal volume rate, aligned midpoint velocity, and top-of-book/depth imbalance during the signal confirmation bar.
- Scored trade window: `2025-04-01` through `2026-05-02`.
- Data files used: `164` MBP-10 windows from `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/raw/orderbook/NQ/mbp-10`.
- Missing order-book matches: `2` candidate fills.
- Warning: thresholds below are same-period diagnostics on sparse windows. They are evidence for feature design, not deployable gates until frozen on pre-holdout data.

## Best Diagnostic Gates

| Candidate | Gate | Threshold | Trades | PF | Avg R | Total R | DD | Calmar |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `mid_velocity_ratio_q60` | 0.019 | 23 | 2.526 | 0.398 | 9.16 | -2.00 | 4.58 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `mid_velocity_ratio_q70` | 0.022 | 14 | 3.038 | 0.437 | 6.11 | -1.00 | 6.11 |
| `add_3m_hourly_atr12p5_b3_a7p5` | `price_impulse_score_q60` | 0.012 | 19 | 2.813 | 0.440 | 8.36 | -1.50 | 5.57 |
| `htf_lsi_2m_anchor` | `pressure_score_q70` | 0.064 | 25 | 1.606 | 0.232 | 5.80 | -3.00 | 1.93 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `impulse_score_q50` | 0.001 | 11 | 4.267 | 0.594 | 6.53 | -1.50 | 4.36 |

## Baselines

| Candidate | Trades | PF | Avg R | Total R | DD | Calmar | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 58 | 1.734 | 0.253 | 14.67 | -5.07 | 2.89 | 98.3% |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 47 | 1.753 | 0.256 | 12.05 | -5.13 | 2.35 | 97.9% |
| `add_3m_hourly_atr12p5_b3_a7p5` | 46 | 1.733 | 0.265 | 12.17 | -5.11 | 2.38 | 100.0% |
| `htf_lsi_2m_anchor` | 83 | 1.028 | 0.014 | 1.17 | -10.78 | 0.11 | 100.0% |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 21 | 1.692 | 0.231 | 4.84 | -1.67 | 2.90 | 100.0% |

## Impulse Score Quartiles

| Candidate | Bucket | Trades | Score Range | PF | Avg R | Total R | DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | q1_low | 15 | 0.000-0.001 | 0.679 | -0.171 | -2.57 | -6.00 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | q2 | 14 | 0.001-0.002 | 3.867 | 0.614 | 8.60 | -1.00 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | q3 | 14 | 0.002-0.004 | 3.447 | 0.524 | 7.34 | -2.00 |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | q4_high | 14 | 0.004-0.017 | 0.956 | -0.019 | -0.26 | -3.55 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | q1_low | 12 | 0.000-0.001 | 0.829 | -0.085 | -1.03 | -4.50 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | q2 | 11 | 0.001-0.002 | 4.164 | 0.575 | 6.33 | -1.00 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | q3 | 11 | 0.002-0.004 | 2.647 | 0.449 | 4.94 | -2.00 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | q4_high | 12 | 0.004-0.017 | 1.047 | 0.020 | 0.24 | -2.55 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q1_low | 12 | 0.000-0.000 | 1.859 | 0.286 | 3.44 | -4.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q2 | 11 | 0.000-0.001 | 2.125 | 0.409 | 4.50 | -1.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q3 | 11 | 0.001-0.001 | 2.658 | 0.452 | 4.97 | -1.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | q4_high | 12 | 0.001-0.010 | 0.868 | -0.062 | -0.74 | -1.61 |
| `htf_lsi_2m_anchor` | q1_low | 21 | 0.000-0.000 | 0.892 | -0.061 | -1.29 | -5.59 |
| `htf_lsi_2m_anchor` | q2 | 21 | 0.000-0.001 | 0.931 | -0.040 | -0.84 | -3.39 |
| `htf_lsi_2m_anchor` | q3 | 20 | 0.001-0.003 | 0.653 | -0.172 | -3.43 | -8.66 |
| `htf_lsi_2m_anchor` | q4_high | 21 | 0.003-0.038 | 1.793 | 0.321 | 6.74 | -2.25 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | q1_low | 6 | 0.000-0.001 | 0.421 | -0.290 | -1.74 | -1.50 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | q2 | 5 | 0.001-0.001 | 1.773 | 0.309 | 1.55 | -1.00 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | q3 | 5 | 0.002-0.002 | 0.000 | 0.907 | 4.53 | 0.00 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | q4_high | 5 | 0.002-0.007 | 1.250 | 0.100 | 0.50 | -1.50 |

## Feature Distribution

| Candidate | Trades | Impulse p50 | Impulse p75 | Pressure p50 | Mid Move p50 | Agg Imb p50 | Depth3 p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 58 | 0.002 | 0.004 | 0.037 | 77.500 | 0.102 | 0.009 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 47 | 0.002 | 0.004 | 0.048 | 77.750 | 0.112 | 0.008 |
| `add_3m_hourly_atr12p5_b3_a7p5` | 46 | 0.001 | 0.001 | 0.015 | 101.250 | 0.054 | 0.011 |
| `htf_lsi_2m_anchor` | 83 | 0.001 | 0.003 | 0.030 | 72.000 | 0.085 | 0.005 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 21 | 0.001 | 0.002 | 0.028 | 77.500 | 0.090 | 0.004 |

## Interpretation

- `impulse_score` is strict: it needs aligned aggression, abnormal volume, and aligned midpoint displacement.
- `pressure_score` is looser: it rewards one-way aggression and book support even when price displacement is smaller.
- A production rule should be selected from pre-holdout validation, then replayed on untouched holdout windows and exact execution data.