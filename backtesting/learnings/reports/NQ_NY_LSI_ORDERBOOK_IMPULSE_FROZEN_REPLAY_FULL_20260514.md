# NQ LSI Order-Book Impulse Frozen Threshold Replay

- Method: select candidate-specific order-book gates on validation rows only, then replay the frozen threshold on holdout rows.
- Validation CSV: `data/results/nq_ny_lsi_orderbook_impulse_validation_full_20260514/trade_orderbook_impulse.csv`.
- Holdout CSV: `data/results/nq_ny_lsi_orderbook_impulse_20260513/trade_orderbook_impulse.csv`.
- Minimum validation trades per selected gate: `20`.
- Validation feature coverage: `537/544` rows.
- Holdout feature coverage: `253/255` rows.
- Data status: validation coverage is effectively complete; unmatched rows are tiny/no-data windows.

## Selected Validation Gates Replayed On Holdout

| Candidate | Status | Gate | Val Trades | Val PF | Val Avg R | Val R | Holdout Trades | Holdout PF | Holdout Avg R | Holdout R |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | selected | `aligned_depth_imbalance_3_mean_q80` @ 0.0188 | 21 | 2.302 | 0.434 | 9.12 | 21 | 1.014 | 0.005 | 0.09 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | selected | `mid_velocity_ticks_per_second_q70` @ 1.0000 | 26 | 2.831 | 0.493 | 12.81 | 27 | 1.300 | 0.111 | 3.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | selected | `aligned_depth_imbalance_3_mean_q80` @ 0.0213 | 28 | 2.905 | 0.544 | 15.24 | 14 | 1.225 | 0.090 | 1.26 |
| `htf_lsi_2m_anchor` | selected | `aligned_depth_imbalance_3_mean_q60` @ 0.0033 | 71 | 1.670 | 0.289 | 20.54 | 44 | 0.788 | -0.112 | -4.91 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | no_validation_gate_met_min_trades | n/a | 0 | 0.000 | 0.000 | 0.00 | 0 | 0.000 | 0.000 | 0.00 |

## Baseline Coverage

| Period | Candidate | Rows | Scored | Coverage | All PF | All Avg R | Scored PF | Scored Avg R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 58 | 57 | 98.3% | 1.734 | 0.253 | 1.655 | 0.230 |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 47 | 46 | 97.9% | 1.753 | 0.256 | 1.655 | 0.228 |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | 46 | 46 | 100.0% | 1.733 | 0.265 | 1.733 | 0.265 |
| holdout | `htf_lsi_2m_anchor` | 83 | 83 | 100.0% | 1.028 | 0.014 | 1.028 | 0.014 |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 21 | 21 | 100.0% | 1.692 | 0.231 | 1.692 | 0.231 |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 106 | 104 | 98.1% | 1.367 | 0.152 | 1.362 | 0.150 |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 85 | 83 | 97.6% | 1.615 | 0.239 | 1.616 | 0.238 |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | 140 | 139 | 99.3% | 1.153 | 0.071 | 1.145 | 0.068 |
| validation | `htf_lsi_2m_anchor` | 180 | 178 | 98.9% | 1.262 | 0.127 | 1.245 | 0.121 |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 33 | 33 | 100.0% | 2.055 | 0.320 | 2.055 | 0.320 |