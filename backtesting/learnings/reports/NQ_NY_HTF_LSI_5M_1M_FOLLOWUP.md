# NQ NY HTF-LSI 5m / 1m Follow-Up

- Scope:
  - promote the new `5m` late-lag path with stitched OOS checks
  - compare `5m` and `1m` on a minute-normalized lag basis
- Holdout was not reopened for this follow-up.
- Artifact sources:
  - [five_minute_partial.json](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_htf_lsi_5m_1m_followup/five_minute_partial.json)
  - [5m.json](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_htf_lsi_lag_curve/5m.json)
  - [1m.json](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_htf_lsi_lag_curve/1m.json)

## 5m Late-Lag Follow-Up

| Lag | Discovery PF | Discovery Avg R | Validation PF | Validation Avg R | Validation Calmar | Validation Trades | WF PF | WF Avg R | WF Calmar | WF Trades |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1.164 | 0.072 | 1.556 | 0.224 | 6.208 | 151 | 1.298 | 0.130 | 4.117 | 376 |
| 20 | 1.193 | 0.093 | 1.584 | 0.262 | 4.207 | 121 | 1.368 | 0.174 | 4.755 | 311 |
| 24 | 1.188 | 0.088 | 1.597 | 0.268 | 6.382 | 127 | 1.347 | 0.162 | 4.848 | 330 |
| 30 | 1.182 | 0.083 | 1.567 | 0.249 | 5.920 | 134 | 1.328 | 0.149 | 4.220 | 340 |

Takeaways:

- `lag=24` is the new best `5m` candidate in this family.
- It beat the uncapped anchor on validation PF, validation avg R, validation Calmar, stitched OOS PF, stitched OOS avg R, and stitched OOS Calmar.
- `lag=20` was also strong on stitched OOS and actually had the highest stitched OOS PF of the tested late-lag rows, but `lag=24` was better balanced overall.
- `lag=30` kept most of the late-lag improvement, but it gave back some of the `lag=24` edge.

## Minute-Normalized 5m vs 1m

The `5m` lag curve maps cleanly into minute caps because `1` lag bar on `5m` equals `5` minutes. The `1m` branch uses the same minute count as the lag count.

| Timeframe | Minute Cap | Lag Bars | Discovery PF | Discovery Avg R | Validation PF | Validation Avg R | Validation Calmar | Validation Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m | 0 | 0 | 1.164 | 0.072 | 1.556 | 0.224 | 6.208 | 151 |
| 5m | 30 | 6 | 1.193 | 0.109 | 1.427 | 0.207 | 1.149 | 59 |
| 5m | 60 | 12 | 1.281 | 0.141 | 1.388 | 0.195 | 1.770 | 97 |
| 5m | 90 | 18 | 1.178 | 0.089 | 1.477 | 0.219 | 2.470 | 116 |
| 5m | 120 | 24 | 1.188 | 0.088 | 1.597 | 0.268 | 6.382 | 127 |
| 5m | 150 | 30 | 1.182 | 0.083 | 1.567 | 0.249 | 5.920 | 134 |
| 1m | 0 | 0 | 1.082 | 0.041 | 1.263 | 0.126 | 1.711 | 219 |
| 1m | 5 | 5 | 0.889 | -0.070 | 1.577 | 0.315 | 2.713 | 43 |
| 1m | 10 | 10 | 0.751 | -0.167 | 1.888 | 0.420 | 4.913 | 76 |
| 1m | 15 | 15 | 0.791 | -0.138 | 1.611 | 0.314 | 4.141 | 93 |
| 1m | 20 | 20 | 0.965 | -0.023 | 1.438 | 0.227 | 2.513 | 113 |
| 1m | 30 | 30 | 0.999 | -0.001 | 1.468 | 0.237 | 3.254 | 138 |

Interpretation:

- The `5m` branch wants slow reversals in real time. Its best region was around `120` minutes.
- The `1m` branch liked a much quicker region, around `10-15` minutes, but that came with worse discovery quality than the uncapped `1m` anchor.
- So the `5m` and `1m` paths are not expressing the same timing behavior. This is not just a bar-count artifact.

## Current Read

- `5m` path: promote the late-lag challenger, centered around `lag=24`, into the next robustness pass.
- `1m` path: keep `lag=10` as the most interesting local challenger, but do not promote it yet without a completed stitched OOS comparison. The fixed validation split alone is not enough because discovery degraded materially.
