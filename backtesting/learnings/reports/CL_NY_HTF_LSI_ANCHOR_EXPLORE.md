# CL NY HTF-LSI Anchor Explore

- Instrument: `CL`
- Packet: NQ-derived HTF-LSI transfer anchors (`1m lag0`, `3m lag0`, `5m lag0`, `5m lag24`)
- Date windows: discovery `2016-01-01` to `2023-01-01`, validation `2023-01-01` to `2025-04-01`
- Holdout policy: `2025-04-01+` remains closed in this packet
- Session floors applied: `min_stop_points=0.0`, `min_tp1_points=0.0`

## 5m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m_lag0_control | dead | 0.920 | -0.032 | 388 | 0.950 | -0.028 | -0.329 | 139 | 0.929 | -0.499 | 5 |
| 5m_lag24_promoted | dead | 0.916 | -0.037 | 343 | 0.941 | -0.037 | -0.402 | 126 | 0.923 | -0.573 | 5 |

## 3m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3m_lag0_diagnostic | diagnostic_only | 1.002 | 0.005 | 462 | 1.049 | 0.023 | 0.540 | 156 | 1.014 | 0.212 | 5 |

## 1m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m_lag0_honest | alive | 1.122 | 0.064 | 662 | 1.199 | 0.099 | 2.104 | 238 | 1.142 | 1.712 | 3 |

## Notes

- `1m_lag0_honest`: Honest lower-timeframe baseline from NQ. Kept uncapped because lag10 failed stitched OOS.
- `3m_lag0_diagnostic`: Diagnostic 3m transfer from NQ. Validation-strong there, but discovery-negative.
- `5m_lag0_control`: 5m control row from NQ before the late-lag promotion.
- `5m_lag24_promoted`: Promoted 5m lead from NQ. The only lag-cap improvement that survived stitched OOS.
