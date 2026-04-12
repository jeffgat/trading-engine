# SI NY HTF-LSI Anchor Explore

- Instrument: `SI`
- Packet: NQ-derived HTF-LSI transfer anchors (`1m lag0`, `3m lag0`, `5m lag0`, `5m lag24`)
- Date windows: discovery `2016-01-01` to `2023-01-01`, validation `2023-01-01` to `2025-04-01`
- Holdout policy: `2025-04-01+` remains closed in this packet
- Session floors applied: `min_stop_points=0.0`, `min_tp1_points=0.0`

## 5m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m_lag24_promoted | alive | 1.077 | 0.030 | 304 | 1.791 | 0.280 | 4.096 | 116 | 1.237 | 2.075 | 4 |
| 5m_lag0_control | diagnostic_only | 1.047 | 0.015 | 359 | 1.640 | 0.222 | 3.128 | 133 | 1.183 | 1.658 | 4 |

## 3m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3m_lag0_diagnostic | alive | 1.199 | 0.086 | 425 | 1.135 | 0.067 | 0.947 | 168 | 1.180 | 1.815 | 2 |

## 1m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m_lag0_honest | diagnostic_only | 0.889 | -0.056 | 638 | 1.060 | 0.032 | 0.448 | 253 | 0.936 | -0.468 | 5 |

## Notes

- `5m_lag24_promoted`: Promoted 5m lead from NQ. The only lag-cap improvement that survived stitched OOS.
- `3m_lag0_diagnostic`: Diagnostic 3m transfer from NQ. Validation-strong there, but discovery-negative.
- `5m_lag0_control`: 5m control row from NQ before the late-lag promotion.
- `1m_lag0_honest`: Honest lower-timeframe baseline from NQ. Kept uncapped because lag10 failed stitched OOS.
