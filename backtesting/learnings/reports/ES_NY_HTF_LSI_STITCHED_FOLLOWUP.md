# ES NY HTF-LSI Stitched Follow-Up

- Fixed stitched OOS comparison over `2016-01-01` to `2025-04-01` using `36m IS / 12m OOS / 12m step` slices.
- Holdout remains unopened.

| Candidate | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| control_stage_b | 1.055 | 0.025 | 1.434 | 0.191 | 2.445 | 1.253 | 0.115 | 3.661 | 350 | -11.00 |
| balanced_lag0_gap3 | 1.074 | 0.030 | 1.449 | 0.175 | 2.358 | 1.243 | 0.097 | 3.556 | 348 | -9.52 |
| count_lag0_gap2_r15 | 1.056 | 0.024 | 1.396 | 0.168 | 2.514 | 1.220 | 0.095 | 2.995 | 478 | -15.11 |
| discovery_lag0_gap2_r9 | 1.085 | 0.036 | 1.339 | 0.138 | 2.213 | 1.214 | 0.088 | 2.929 | 440 | -13.26 |
| late_lag24_gap3 | 1.057 | 0.027 | 1.407 | 0.179 | 2.165 | 1.220 | 0.102 | 2.883 | 257 | -9.07 |
| quality_lag16_gap2 | 1.055 | 0.028 | 1.421 | 0.188 | 2.525 | 1.191 | 0.093 | 2.474 | 271 | -10.15 |
