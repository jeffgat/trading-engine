# NQ LSI Structural Stop / Target Sweep

- Date: `2026-04-13`
- Objective: test tighter LSI stops plus two structural target constructions: structural-risk-basis targets and left-side unswept-pivot targets.
- Scope: regular NQ NY LSI final branch plus the current NQ NY HTF-LSI operating lead.
- Holdout split: pre-holdout `< 2025-04-01`, holdout `>= 2025-04-01`.

## Stop / Target Menu

- Stops: `absolute`, `gap_1x`, `gap_2x`, `gap_3x`, `gap_4x`, `struct_50pct`, `struct_75pct`.
- Targets:
  - `risk`: TP1/TP2 from actual stop distance.
  - `structural`: TP1/TP2 from full structural distance, with `TP1 >= 1R` and `TP2 >= 1.5R` on actual risk.
  - `left_structure`: TP1/TP2 from unswept swing pivots to the left of the setup; longs target left-side highs, shorts target left-side lows, while still enforcing the minimum 1R / 1.5R floors.

## NQ NY LSI Final

- Gate: `skip_medium_vol`
- Notes: Long-only regular LSI final branch with Thu exclusion and medium-vol avoidance.

| Rank | Stop | Target | Pre PF | Pre AvgR | Pre Calmar | Pre DD | Hold PF | Hold AvgR | Hold Calmar | Med Stop (ticks) | Med TP1 R | Med TP2 R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `struct_50pct` | `structural` | 1.997 | 0.436 | 18.318 | -4.21 | 1.364 | 0.153 | 0.549 | 92.5 | 2.00 | 4.00 |
| 2 | `gap_1x` | `structural` | 1.952 | 0.562 | 15.094 | -6.59 | 0.921 | -0.024 | -0.052 | 53.0 | 3.06 | 6.12 |
| 3 | `struct_50pct` | `left_structure` | 1.875 | 0.399 | 14.110 | -5.00 | 0.726 | -0.166 | -0.372 | 92.5 | 2.56 | 3.52 |
| 4 | `gap_3x` | `structural` | 1.679 | 0.242 | 9.632 | -4.43 | 2.529 | 0.344 | 4.098 | 142.5 | 1.02 | 2.05 |
| 5 | `struct_50pct` | `risk` | 1.745 | 0.251 | 9.568 | -4.64 | 0.629 | -0.194 | -0.597 | 92.5 | 1.00 | 2.00 |
| 6 | `gap_1x` | `left_structure` | 1.715 | 0.438 | 9.296 | -8.34 | 0.974 | 0.013 | 0.028 | 53.0 | 4.30 | 6.07 |
| 7 | `struct_75pct` | `structural` | 1.684 | 0.254 | 9.252 | -4.86 | 2.048 | 0.281 | 1.775 | 138.8 | 1.33 | 2.67 |
| 8 | `gap_2x` | `risk` | 1.611 | 0.209 | 9.200 | -4.00 | 0.954 | -0.008 | -0.038 | 106.0 | 1.00 | 2.00 |

### Quick Read

- Baseline: `absolute` + `risk` -> pre PF `1.658`, pre avg R `0.193`, holdout PF `2.464`.
- Best pre-holdout row: `struct_50pct` + `structural` -> pre PF `1.997`, pre avg R `0.436`, holdout PF `1.364`.
- Best `left_structure` row: `struct_50pct` + `left_structure` -> pre PF `1.875`, pre avg R `0.399`, holdout PF `0.726`.

## NQ NY HTF-LSI Current

- Gate: `skip_bear_high_vol`
- Notes: Current operating HTF-LSI lead (`5m lag24`, `08:30-13:30`, `rr=3.5`, `tp1=0.4`).

| Rank | Stop | Target | Pre PF | Pre AvgR | Pre Calmar | Pre DD | Hold PF | Hold AvgR | Hold Calmar | Med Stop (ticks) | Med TP1 R | Med TP2 R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `absolute` | `risk` | 1.435 | 0.191 | 8.424 | -9.00 | 2.264 | 0.445 | 5.338 | 149.0 | 1.40 | 3.50 |
| 2 | `absolute` | `structural` | 1.435 | 0.191 | 8.424 | -9.00 | 2.264 | 0.445 | 5.338 | 149.0 | 1.40 | 3.50 |
| 3 | `absolute` | `left_structure` | 1.453 | 0.202 | 8.005 | -10.00 | 1.799 | 0.353 | 2.954 | 149.0 | 1.57 | 2.32 |
| 4 | `struct_75pct` | `structural` | 1.327 | 0.180 | 7.358 | -9.69 | 2.658 | 0.626 | 7.517 | 111.8 | 1.87 | 4.67 |
| 5 | `struct_75pct` | `left_structure` | 1.321 | 0.172 | 6.755 | -10.11 | 2.351 | 0.547 | 5.777 | 111.8 | 1.83 | 2.76 |
| 6 | `struct_50pct` | `risk` | 1.317 | 0.161 | 6.656 | -9.62 | 1.841 | 0.345 | 3.223 | 74.5 | 1.40 | 3.50 |
| 7 | `struct_50pct` | `structural` | 1.315 | 0.207 | 6.324 | -13.00 | 2.050 | 0.521 | 3.262 | 74.5 | 2.80 | 7.00 |
| 8 | `struct_75pct` | `risk` | 1.249 | 0.130 | 5.698 | -9.06 | 2.270 | 0.477 | 5.724 | 111.8 | 1.40 | 3.50 |

### Quick Read

- Baseline: `absolute` + `risk` -> pre PF `1.435`, pre avg R `0.191`, holdout PF `2.264`.
- Best pre-holdout row: `absolute` + `risk` -> pre PF `1.435`, pre avg R `0.191`, holdout PF `2.264`.
- Best `left_structure` row: `absolute` + `left_structure` -> pre PF `1.453`, pre avg R `0.202`, holdout PF `1.799`.
