# NQ LSI ATR / ORB Stop Sweep

- Date: `2026-04-13`
- Scope: saved NQ NY LSI final branch only (`long`, `fvg_limit`, Thu excluded, skip medium-vol gate).
- Objective: broad stop-source probe using ORB-style and ATR-style distances while keeping targets on the current `risk` basis.
- ORB assumption: use a minimal NY opening range of `09:30-09:35` so ORB stop rows are available from the first entry bar.
- Rule: ATR% and ORB% stop distances are capped at the structural invalidation point.
- Holdout split: pre-holdout `< 2025-04-01`, holdout `>= 2025-04-01`.

## Stop Menu

- `absolute`
- `atr_pct`: `5%`, `10%`, `15%`, `20%` of daily ATR
- `orb_pct`: `50%`, `75%`, `100%` of the `09:30-09:35` opening range

| Rank | Stop Label | Mode | Stop Value | Pre PF | Pre AvgR | Pre Calmar | Pre DD | Hold PF | Hold AvgR | Hold Calmar | Med Stop (ticks) | Med TP1 R | Med TP2 R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `orb_100pct` | `orb_pct` | `100% ORB` | 1.661 | 0.241 | 10.336 | -4.11 | 1.588 | 0.198 | 0.749 | 117.5 | 1.00 | 2.00 |
| 2 | `atr_20pct` | `atr_pct` | `20% ATR` | 1.617 | 0.220 | 8.672 | -4.50 | 1.130 | 0.079 | 0.295 | 122.2 | 1.00 | 2.00 |
| 3 | `absolute` | `absolute` | `structural` | 1.658 | 0.193 | 7.586 | -4.42 | 2.464 | 0.313 | 2.457 | 180.0 | 1.00 | 2.00 |
| 4 | `atr_15pct` | `atr_pct` | `15% ATR` | 1.578 | 0.217 | 6.766 | -5.67 | 0.609 | -0.187 | -0.650 | 93.4 | 1.00 | 2.00 |
| 5 | `orb_75pct` | `orb_pct` | `75% ORB` | 1.586 | 0.209 | 6.480 | -5.67 | 0.876 | -0.007 | -0.029 | 88.9 | 1.00 | 2.00 |
| 6 | `orb_50pct` | `orb_pct` | `50% ORB` | 1.597 | 0.211 | 4.952 | -7.50 | 0.739 | -0.131 | -0.491 | 59.8 | 1.00 | 2.00 |
| 7 | `atr_10pct` | `atr_pct` | `10% ATR` | 1.451 | 0.169 | 4.036 | -7.43 | 0.277 | -0.477 | -1.111 | 62.3 | 1.00 | 2.00 |
| 8 | `atr_5pct` | `atr_pct` | `5% ATR` | 0.942 | -0.025 | -0.229 | -19.27 | 0.668 | -0.135 | -0.793 | 31.1 | 1.00 | 2.00 |

## Quick Read

- Baseline: `absolute` -> pre PF `1.658`, pre avg R `0.193`, holdout PF `2.464`.
- Best pre-holdout row: `orb_100pct` -> pre PF `1.661`, pre avg R `0.241`, holdout PF `1.588`.
