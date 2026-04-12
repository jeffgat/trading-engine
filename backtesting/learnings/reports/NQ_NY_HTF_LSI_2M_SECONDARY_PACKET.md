# NQ NY HTF-LSI 2m Secondary Packet

- Narrow pre-holdout packet around the honest `2m lag=0` branch.
- Fixed branch shape: `long`, `fvg_limit`, `cap1`, `lag=0`, `08:30-15:00`.
- Search window: `2016-01-01` to `2025-04-01` with holdout still closed.

## Grid

| Param | Values |
| --- | --- |
| min_gap_atr_pct | 3.0, 4.0 |
| htf_n_left | 3, 5 |
| lsi_fvg_window_left | 40, 50, 60 |
| lsi_fvg_window_right | 3, 5, 8 |
| rr | 2.5, 3.0, 3.5 |
| tp1_ratio | 0.5, 0.6, 0.7 |

- Total configs: `324`
- Survivors by discovery filters: `306`

## Top Pre-Holdout Rows

| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left50 right8 rr3.0 tp0.6 | 1.135 | 0.070 | 1.310 | 0.148 | 3.302 | 193 |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left40 right8 rr3.0 tp0.6 | 1.135 | 0.070 | 1.306 | 0.146 | 3.245 | 192 |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left50 right8 rr2.5 tp0.5 | 1.078 | 0.039 | 1.323 | 0.136 | 3.172 | 193 |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left60 right8 rr2.5 tp0.5 | 1.074 | 0.037 | 1.321 | 0.135 | 3.165 | 194 |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left50 right5 rr3.0 tp0.6 | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 180 |

## Stitched OOS Follow-Up

| Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left50 right5 rr3.0 tp0.6 | 1.212 | 0.104 | 3.763 | 486 | -13.41 |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left50 right8 rr3.0 tp0.6 | 1.177 | 0.088 | 2.760 | 529 | -16.94 |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left40 right8 rr3.0 tp0.6 | 1.172 | 0.086 | 2.591 | 526 | -17.50 |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left50 right8 rr2.5 tp0.5 | 1.124 | 0.059 | 1.648 | 529 | -18.82 |
| NQ NY HTF_LSI 2m packet gap3.0 n3 left60 right8 rr2.5 tp0.5 | 1.118 | 0.056 | 1.464 | 530 | -20.20 |