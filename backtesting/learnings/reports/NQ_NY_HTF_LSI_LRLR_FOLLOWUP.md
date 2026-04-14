# NQ NY HTF-LSI LRLR Follow-up

- Scope: pre-holdout only (`2016-01-01` to `2025-03-31`). Holdout remains closed.
- Anchor: `2m` NQ NY HTF-LSI long branch (`fvg_limit`, `cap1`, `rr=3.0`, `tp1=0.6`).
- Pass 1: LRLR-lite = `2` unswept pivots with `30m` or `40m` max pivot spacing.
- Pass 2: TP1-aware LRLR = LRLR-lite plus the nearest LRLR level must sit inside TP1, optionally with an ATR buffer.

- Baseline validation: PF `1.275` / Avg R `0.127` / Calmar `2.057` / trades `180`
- Best LRLR-lite gate: gap `30m` -> PF `1.375` / Avg R `0.180` / Calmar `2.561` / trades `111`
- Best TP1-aware gate: gap `30m`, buffer `0.2 ATR` -> PF `1.501` / Avg R `0.229` / Calmar `4.012` / trades `105`

## LRLR-lite

| Max Gap (m) | Segmented Val PF | Segmented Val Avg R | Segmented Share | Require Val PF | Require Val Avg R | Require Val Calmar | Require Trades | Exclude Val PF | Exclude Val Avg R |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 1.361 | 0.172 | 60.6% | 1.375 | 0.180 | 2.561 | 111 | 1.134 | 0.058 |
| 40 | 1.347 | 0.163 | 63.3% | 1.360 | 0.170 | 2.530 | 116 | 1.146 | 0.066 |

## TP1-aware LRLR

| Max Gap (m) | Buffer (ATR) | TP1-Qualified Val PF | TP1-Qualified Val Avg R | TP1 Share | Require Val PF | Require Val Avg R | Require Val Calmar | Require Trades | Exclude Val PF | Exclude Val Avg R |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 0.2 | 1.489 | 0.222 | 57.2% | 1.501 | 0.229 | 4.012 | 105 | 1.004 | 0.000 |
| 40 | 0.2 | 1.469 | 0.210 | 60.0% | 1.481 | 0.217 | 3.941 | 110 | 1.008 | 0.004 |
| 30 | 0.1 | 1.507 | 0.228 | 54.4% | 1.475 | 0.215 | 3.554 | 99 | 1.020 | 0.007 |
| 40 | 0.1 | 1.485 | 0.214 | 57.2% | 1.454 | 0.203 | 3.487 | 104 | 1.024 | 0.011 |
| 30 | 0.3 | 1.397 | 0.188 | 58.9% | 1.411 | 0.195 | 3.100 | 108 | 1.095 | 0.041 |
| 40 | 0.3 | 1.382 | 0.177 | 61.7% | 1.395 | 0.184 | 3.064 | 113 | 1.104 | 0.047 |
| 30 | 0.0 | 1.658 | 0.269 | 48.3% | 1.583 | 0.241 | 3.011 | 89 | 0.990 | -0.005 |
| 40 | 0.0 | 1.624 | 0.252 | 51.1% | 1.554 | 0.225 | 2.977 | 94 | 0.993 | -0.003 |