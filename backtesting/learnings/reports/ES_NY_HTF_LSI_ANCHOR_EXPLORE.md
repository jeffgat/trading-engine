# ES NY HTF-LSI Anchor Explore

- Instrument: `ES`
- Packet: NQ-derived HTF-LSI transfer anchors (`1m lag0`, `3m lag0`, `5m lag0`, `5m lag24`)
- Date windows: discovery `2016-01-01` to `2023-01-01`, validation `2023-01-01` to `2025-04-01`
- Holdout policy: `2025-04-01+` remains closed in this packet
- Session floors applied: `min_stop_points=3.0`, `min_tp1_points=3.0`

## 5m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m_lag0_control | diagnostic_only | 0.964 | -0.019 | 445 | 1.240 | 0.102 | 1.805 | 163 | 1.032 | 0.296 | 6 |
| 5m_lag24_promoted | diagnostic_only | 0.979 | -0.014 | 374 | 1.200 | 0.094 | 1.362 | 133 | 1.032 | 0.292 | 6 |

## 3m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3m_lag0_diagnostic | diagnostic_only | 0.953 | -0.025 | 499 | 1.318 | 0.141 | 2.527 | 170 | 1.036 | 0.324 | 5 |

## 1m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m_lag0_honest | diagnostic_only | 0.969 | -0.014 | 636 | 1.027 | 0.017 | 0.257 | 210 | 0.982 | -0.161 | 6 |

## Notes

- `3m_lag0_diagnostic`: Diagnostic 3m transfer from NQ. Validation-strong there, but discovery-negative.
- `5m_lag0_control`: 5m control row from NQ before the late-lag promotion.
- `5m_lag24_promoted`: Promoted 5m lead from NQ. The only lag-cap improvement that survived stitched OOS.
- `1m_lag0_honest`: Honest lower-timeframe baseline from NQ. Kept uncapped because lag10 failed stitched OOS.
