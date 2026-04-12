# NQ NY HTF-LSI Lag24 Exact Replay

- Objective: replay the current `5m lag=24` branch through the live execution engine and compare it with the current research definition.
- Profile: `HTF_LSI_5M_LAG24`
- Research config: `long fvg_limit 08:30-13:30 rr3.5 tp0.4 gap3.0 htf60 n3 cap2 fvgL20 fvgR2 lag24`
- Full replay window: `2016-01-01` to `2026-03-24`

## Windows

| Window | Exact Trades | Exact PF | Exact Avg R | Exact Calmar | Research Trades | Research PF | Research Avg R | Research Calmar | Delta Trades | Delta PF | Delta Avg R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pre-Holdout | 455 | 1.394 | 0.162 | 7.339 | 456 | 1.368 | 0.163 | 6.783 | -1 | 0.026 | -0.001 |
| Holdout | 38 | 1.963 | 0.342 | 4.330 | 38 | 2.089 | 0.398 | 5.036 | 0 | -0.125 | -0.056 |

## Exact Replay Full-Window Snapshot

- Trades: `493`
- PF: `1.433`
- Avg R: `0.176`
- Total R: `86.603`
- Max DD: `-10.030R`
- Calmar: `8.634`
