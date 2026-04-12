# RTY NY HTF-LSI Anchor Explore

- Instrument: `RTY`
- Packet: NQ-derived HTF-LSI transfer anchors (`1m lag0`, `3m lag0`, `5m lag0`, `5m lag24`)
- Date windows: discovery `2016-01-01` to `2023-01-01`, validation `2023-01-01` to `2025-04-01`
- Holdout policy: `2025-04-01+` remains closed in this packet
- Session floors applied: `min_stop_points=0.0`, `min_tp1_points=0.0`

## 5m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m_lag24_promoted | dead | 0.930 | -0.037 | 316 | 0.835 | -0.095 | -0.755 | 120 | 0.901 | -0.650 | 6 |
| 5m_lag0_control | dead | 0.933 | -0.033 | 356 | 0.802 | -0.104 | -0.907 | 138 | 0.893 | -0.731 | 6 |

## 3m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3m_lag0_diagnostic | dead | 0.989 | -0.009 | 425 | 0.797 | -0.108 | -0.712 | 172 | 0.929 | -0.708 | 7 |

## 1m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m_lag0_honest | dead | 0.988 | -0.009 | 584 | 0.855 | -0.086 | -0.623 | 239 | 0.947 | -0.538 | 7 |

## Notes

- `1m_lag0_honest`: Honest lower-timeframe baseline from NQ. Kept uncapped because lag10 failed stitched OOS.
- `3m_lag0_diagnostic`: Diagnostic 3m transfer from NQ. Validation-strong there, but discovery-negative.
- `5m_lag24_promoted`: Promoted 5m lead from NQ. The only lag-cap improvement that survived stitched OOS.
- `5m_lag0_control`: 5m control row from NQ before the late-lag promotion.
