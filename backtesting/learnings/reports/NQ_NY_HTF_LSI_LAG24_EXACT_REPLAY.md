# NQ NY HTF-LSI Lag24 Exact Replay

- Objective: replay the current `5m lag=24` branch through the live execution engine and compare it with the current research definition.
- Profile: `HTF_LSI_5M_LAG24`
- Research config: `long fvg_limit 08:30-13:30 rr3.5 tp0.4 gap3.0 htf60 n3 cap2 fvgL20 fvgR2 lag24`
- Full replay window: `2016-01-01` to `2026-05-01`

## Windows

| Window | Exact Trades | Exact PF | Exact Avg R | Exact Calmar | Research Trades | Research PF | Research Avg R | Research Calmar | Delta Trades | Delta PF | Delta Avg R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pre-Holdout | 365 | 1.427 | 0.193 | 8.824 | 364 | 1.456 | 0.191 | 8.425 | 1 | -0.029 | 0.002 |
| Holdout | 29 | 2.096 | 0.405 | 3.916 | 29 | 1.995 | 0.377 | 3.645 | 0 | 0.101 | 0.028 |

## Exact Replay Full-Window Snapshot

- Trades: `394`
- PF: `1.470`
- Avg R: `0.209`
- Total R: `82.336`
- Max DD: `-8.000R`
- Calmar: `10.292`
