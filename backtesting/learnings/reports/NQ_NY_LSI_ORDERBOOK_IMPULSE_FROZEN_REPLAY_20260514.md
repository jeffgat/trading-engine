# NQ LSI Order-Book Impulse Frozen Threshold Replay

- Method: select candidate-specific order-book gates on validation rows only, then replay the frozen threshold on holdout rows.
- Validation CSV: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_orderbook_impulse_validation_partial_20260514/trade_orderbook_impulse.csv`.
- Holdout CSV: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_orderbook_impulse_20260513/trade_orderbook_impulse.csv`.
- Minimum validation trades per selected gate: `8`.
- Validation feature coverage: `32/544` rows.
- Holdout feature coverage: `253/255` rows.
- Important limitation: this run is partial because DataBento returned `402 account_insufficient_funds` during validation download. Treat this as a pipeline check, not a final feature verdict.

## Selected Validation Gates Replayed On Holdout

| Candidate | Status | Gate | Val Trades | Val PF | Val Avg R | Val R | Holdout Trades | Holdout PF | Holdout Avg R | Holdout R |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | no_validation_gate_met_min_trades | n/a | 0 | 0.000 | 0.000 | 0.00 | 0 | 0.000 | 0.000 | 0.00 |
| `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | no_validation_gate_met_min_trades | n/a | 0 | 0.000 | 0.000 | 0.00 | 0 | 0.000 | 0.000 | 0.00 |
| `add_3m_hourly_atr12p5_b3_a7p5` | no_validation_gate_met_min_trades | n/a | 0 | 0.000 | 0.000 | 0.00 | 0 | 0.000 | 0.000 | 0.00 |
| `htf_lsi_2m_anchor` | selected | `volume_rate_ratio_ge_1` @ 1.0000 | 8 | 3.220 | 0.555 | 4.44 | 53 | 1.028 | 0.014 | 0.73 |
| `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | no_validation_gate_met_min_trades | n/a | 0 | 0.000 | 0.000 | 0.00 | 0 | 0.000 | 0.000 | 0.00 |

## Baseline Coverage

| Period | Candidate | Rows | Scored | Coverage | All PF | All Avg R | Scored PF | Scored Avg R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 58 | 57 | 98.3% | 1.734 | 0.253 | 1.655 | 0.230 |
| holdout | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 47 | 46 | 97.9% | 1.753 | 0.256 | 1.655 | 0.228 |
| holdout | `add_3m_hourly_atr12p5_b3_a7p5` | 46 | 46 | 100.0% | 1.733 | 0.265 | 1.733 | 0.265 |
| holdout | `htf_lsi_2m_anchor` | 83 | 83 | 100.0% | 1.028 | 0.014 | 1.028 | 0.014 |
| holdout | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 21 | 21 | 100.0% | 1.692 | 0.231 | 1.692 | 0.231 |
| validation | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | 106 | 7 | 6.6% | 1.367 | 0.152 | 2.227 | 0.351 |
| validation | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | 85 | 6 | 7.1% | 1.615 | 0.239 | 1.477 | 0.159 |
| validation | `add_3m_hourly_atr12p5_b3_a7p5` | 140 | 9 | 6.4% | 1.153 | 0.071 | 2.352 | 0.451 |
| validation | `htf_lsi_2m_anchor` | 180 | 9 | 5.0% | 1.262 | 0.127 | 2.147 | 0.382 |
| validation | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | 33 | 1 | 3.0% | 2.055 | 0.320 | 0.000 | 0.500 |