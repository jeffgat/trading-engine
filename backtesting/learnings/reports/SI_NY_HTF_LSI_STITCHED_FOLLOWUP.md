# SI NY HTF-LSI Stitched Follow-Up

- Fixed stitched OOS comparison over `2016-01-01` to `2025-04-01` using `36m IS / 12m OOS / 12m step` slices.
- Holdout remains unopened.

| Candidate | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| control_stage_b_end13_cap1 | 1.120 | 0.052 | 1.776 | 0.279 | 13.060 | 1.386 | 0.157 | 4.410 | 471 | -16.75 |
| balanced_lag0_end13 | 1.109 | 0.048 | 1.767 | 0.272 | 12.755 | 1.360 | 0.147 | 4.091 | 482 | -17.30 |
| late_lag30_end13 | 1.097 | 0.043 | 1.772 | 0.281 | 12.720 | 1.351 | 0.147 | 3.941 | 465 | -17.30 |
| control_stage_b_end14 | 1.064 | 0.028 | 1.719 | 0.258 | 13.087 | 1.323 | 0.133 | 3.487 | 512 | -19.51 |
| balanced_lag0_end14 | 1.074 | 0.032 | 1.751 | 0.264 | 13.254 | 1.333 | 0.136 | 3.455 | 511 | -20.07 |
| late_lag30_end14 | 1.062 | 0.027 | 1.766 | 0.281 | 13.409 | 1.319 | 0.134 | 3.423 | 483 | -18.95 |
