# NQ HTF-LSI Lower-TF Structural Stop / Target Sweep

- Date: `2026-04-13`
- Scope: honest `1m`, `2m`, and `3m` lag-0 HTF-LSI anchors only.
- Stop modes: `absolute`, `gap_1x`, `gap_2x`, `gap_3x`, `gap_4x`, `struct_50pct`, `struct_75pct`.
- Target modes: `risk`, `structural`, `left_structure`.
- Holdout hygiene: `2025-04-01+` stays closed for all three timeframes; stitched OOS is the honest secondary read.
- Ranking: stitched OOS first, then validation.

## 1m

- Anchor: `NQ NY HTF_LSI lagcurve 1m lag0 long close cap2`
- Shape: `long / close / cap2 / 08:30-15:00 / rr3.0 / tp0.6 / L100 / R10`
- Baseline stitched OOS: PF `1.147`, avg R `0.073`, Calmar `2.168`, DD `-19.35`, median stop `140.0` ticks
- Best `left_structure`: `absolute` -> stitched PF `1.166`, avg R `0.078`, Calmar `1.657`, DD `-27.24`

| Rank | Stop | Target | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF DD | Stop Ticks | TP1 R | TP2 R |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `absolute` | `risk` | 1.082 | 0.041 | 1.263 | 0.126 | 1.711 | 1.147 | 0.073 | 2.168 | -19.35 | 140.0 | 1.80 | 3.00 |
| 2 | `absolute` | `structural` | 1.082 | 0.041 | 1.263 | 0.126 | 1.711 | 1.147 | 0.073 | 2.168 | -19.35 | 140.0 | 1.80 | 3.00 |
| 3 | `absolute` | `left_structure` | 1.123 | 0.058 | 1.245 | 0.118 | 2.265 | 1.166 | 0.078 | 1.657 | -27.24 | 140.0 | 1.42 | 1.97 |
| 4 | `gap_4x` | `left_structure` | 1.089 | 0.048 | 1.160 | 0.089 | 1.536 | 1.090 | 0.051 | 0.906 | -32.62 | 108.0 | 1.58 | 2.27 |
| 5 | `struct_75pct` | `left_structure` | 1.065 | 0.037 | 1.175 | 0.088 | 1.509 | 1.070 | 0.041 | 0.790 | -30.22 | 105.0 | 1.60 | 2.31 |

## 2m

- Anchor: `NQ NY HTF_LSI lagcurve 2m lag0 long fvg_limit cap1`
- Shape: `long / fvg_limit / cap1 / 08:30-15:00 / rr3.0 / tp0.6 / L50 / R5`
- Baseline stitched OOS: PF `1.212`, avg R `0.104`, Calmar `3.763`, DD `-13.41`, median stop `137.0` ticks
- Best `left_structure`: `gap_4x` -> stitched PF `1.080`, avg R `0.045`, Calmar `1.355`, DD `-16.34`

| Rank | Stop | Target | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF DD | Stop Ticks | TP1 R | TP2 R |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `struct_75pct` | `risk` | 1.167 | 0.091 | 1.149 | 0.078 | 1.674 | 1.178 | 0.093 | 3.781 | -11.94 | 103.5 | 1.80 | 3.00 |
| 2 | `absolute` | `risk` | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 1.212 | 0.104 | 3.763 | -13.41 | 137.0 | 1.80 | 3.00 |
| 3 | `absolute` | `structural` | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 1.212 | 0.104 | 3.763 | -13.41 | 137.0 | 1.80 | 3.00 |
| 4 | `gap_4x` | `structural` | 1.245 | 0.139 | 1.231 | 0.124 | 1.960 | 1.229 | 0.129 | 3.745 | -16.75 | 116.0 | 1.80 | 3.00 |
| 5 | `gap_3x` | `structural` | 1.291 | 0.178 | 1.118 | 0.074 | 0.831 | 1.239 | 0.146 | 3.728 | -19.08 | 96.0 | 2.25 | 3.75 |

## 3m

- Anchor: `NQ NY HTF_LSI lagcurve 3m lag0 long fvg_limit cap2`
- Shape: `long / fvg_limit / cap2 / 08:30-15:00 / rr3.0 / tp0.6 / L33 / R3`
- Baseline stitched OOS: PF `1.155`, avg R `0.078`, Calmar `2.637`, DD `-13.07`, median stop `152.0` ticks
- Best `left_structure`: `gap_3x` -> stitched PF `1.167`, avg R `0.094`, Calmar `2.242`, DD `-18.73`

| Rank | Stop | Target | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF DD | Stop Ticks | TP1 R | TP2 R |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `gap_2x` | `risk` | 1.081 | 0.047 | 1.298 | 0.163 | 2.016 | 1.192 | 0.107 | 3.430 | -14.03 | 72.0 | 1.80 | 3.00 |
| 2 | `struct_75pct` | `risk` | 1.030 | 0.019 | 1.471 | 0.214 | 4.469 | 1.201 | 0.102 | 2.721 | -16.92 | 115.1 | 1.80 | 3.00 |
| 3 | `absolute` | `risk` | 0.947 | -0.022 | 1.545 | 0.219 | 5.210 | 1.155 | 0.078 | 2.637 | -13.07 | 152.0 | 1.80 | 3.00 |
| 4 | `absolute` | `structural` | 0.947 | -0.022 | 1.545 | 0.219 | 5.210 | 1.155 | 0.078 | 2.637 | -13.07 | 152.0 | 1.80 | 3.00 |
| 5 | `gap_3x` | `risk` | 0.963 | -0.016 | 1.373 | 0.180 | 3.750 | 1.147 | 0.083 | 2.366 | -15.67 | 101.5 | 1.80 | 3.00 |
