# NQ HTF-LSI ATR / ORB Stop Sweep

- Date: `2026-04-13`
- Scope: current NQ NY HTF-LSI operating lead only (`5m lag24`, `long`, `fvg_limit`, `08:30-13:30`, `rr=3.5`, `tp1=0.4`, skip `bear_high_vol`).
- Objective: broad stop-source probe using ORB-style and ATR-style distances while keeping targets on the current `risk` basis.
- ORB assumption: use a minimal NY opening range of `08:30-08:35` so ORB stop rows are available from the first eligible entry bar.
- Rule: ATR% and ORB% stop distances are capped at the structural invalidation point.
- Holdout split: pre-holdout `< 2025-04-01`, holdout `>= 2025-04-01`.

## Stop Menu

- `absolute`
- `atr_pct`: `5%`, `10%`, `15%`, `20%` of daily ATR
- `orb_pct`: `50%`, `75%`, `100%` of the `08:30-08:35` opening range

| Rank | Stop Label | Mode | Stop Value | Pre PF | Pre AvgR | Pre Calmar | Pre DD | Hold PF | Hold AvgR | Hold Calmar | Med Stop (ticks) | Med TP1 R | Med TP2 R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `absolute` | `absolute` | `structural` | 1.435 | 0.191 | 8.424 | -9.00 | 2.264 | 0.445 | 5.338 | 149.0 | 1.40 | 3.50 |
| 2 | `atr_20pct` | `atr_pct` | `20% ATR` | 1.230 | 0.121 | 4.874 | -9.86 | 2.044 | 0.416 | 4.988 | 118.0 | 1.40 | 3.50 |
| 3 | `orb_100pct` | `orb_pct` | `100% ORB` | 1.226 | 0.112 | 2.362 | -18.86 | 1.816 | 0.360 | 3.816 | 47.0 | 1.40 | 3.50 |
| 4 | `atr_15pct` | `atr_pct` | `15% ATR` | 1.155 | 0.083 | 2.335 | -14.10 | 2.064 | 0.425 | 5.105 | 96.5 | 1.40 | 3.50 |
| 5 | `atr_10pct` | `atr_pct` | `10% ATR` | 1.171 | 0.087 | 1.676 | -20.63 | 1.771 | 0.324 | 2.144 | 68.6 | 1.40 | 3.50 |
| 6 | `orb_75pct` | `orb_pct` | `75% ORB` | 1.097 | 0.048 | 1.134 | -16.69 | 1.401 | 0.184 | 1.479 | 41.2 | 1.40 | 3.50 |
| 7 | `orb_50pct` | `orb_pct` | `50% ORB` | 1.057 | 0.028 | 0.514 | -21.77 | 1.203 | 0.085 | 0.499 | 38.1 | 1.40 | 3.50 |
| 8 | `atr_5pct` | `atr_pct` | `5% ATR` | 0.975 | -0.014 | -0.223 | -24.21 | 1.120 | 0.051 | 0.309 | 34.3 | 1.40 | 3.50 |

## Quick Read

- Baseline: `absolute` -> pre PF `1.435`, pre avg R `0.191`, pre Calmar `8.424`, holdout PF `2.264`.
- Best pre-holdout row: `absolute` -> pre PF `1.435`, pre avg R `0.191`, pre Calmar `8.424`, holdout PF `2.264`.
