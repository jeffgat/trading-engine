# GC NY HTF-LSI Anchor Explore

- Instrument: `GC`
- Packet: NQ-derived HTF-LSI transfer anchors (`1m lag0`, `3m lag0`, `5m lag0`, `5m lag24`)
- Date windows: discovery `2016-01-01` to `2023-01-01`, validation `2023-01-01` to `2025-04-01`
- Holdout policy: `2025-04-01+` remains closed in this packet
- Session floors applied: `min_stop_points=0.0`, `min_tp1_points=0.0`

## 5m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m_lag24_promoted | weak | 1.346 | 0.142 | 297 | 0.894 | -0.052 | -0.379 | 105 | 1.214 | 1.621 | 3 |
| 5m_lag0_control | weak | 1.333 | 0.126 | 341 | 0.887 | -0.053 | -0.480 | 125 | 1.201 | 1.724 | 2 |

## 3m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3m_lag0_diagnostic | weak | 1.119 | 0.054 | 400 | 0.947 | -0.030 | -0.309 | 147 | 1.072 | 0.580 | 4 |

## 1m

| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m_lag0_honest | dead | 1.092 | 0.048 | 615 | 0.673 | -0.174 | -0.823 | 208 | 0.978 | -0.085 | 4 |

## Notes

- `3m_lag0_diagnostic`: Diagnostic 3m transfer from NQ. Validation-strong there, but discovery-negative.
- `5m_lag24_promoted`: Promoted 5m lead from NQ. The only lag-cap improvement that survived stitched OOS.
- `5m_lag0_control`: 5m control row from NQ before the late-lag promotion.
- `1m_lag0_honest`: Honest lower-timeframe baseline from NQ. Kept uncapped because lag10 failed stitched OOS.
