# NQ Entry Mode Inversion Timing Read

- Objective: test whether faster sweep-to-inversion reactions should use `close` instead of `fvg_limit` on frozen NQ winners before reopening the discovery loop.
- Period: `2016-01-01` to `2025-03-31` (pre-holdout only).
- Hybrid rows are exact engine runs using `lsi_entry_mode='timed_hybrid'` with explicit minute thresholds. They are still diagnostic, not promotion-grade holdout evidence.

## Branch Verdicts
### classic_lsi_rr2_gated
- Timeframe: `5m`
- `close`: avg R/all `0.173`, Calmar `4.80`, DD `-4.9R`
- `fvg_limit`: avg R/all `0.190`, Calmar `6.97`, DD `-3.8R`
- `timed_hybrid <=5m`: avg R/all `0.184`, Calmar `6.72`, DD `-3.8R`
- `timed_hybrid <=15m`: avg R/all `0.166`, Calmar `6.10`, DD `-3.8R`

### htf_lsi_5m_lag24
- Timeframe: `5m`
- `close`: avg R/all `0.054`, Calmar `1.55`, DD `-17.7R`
- `fvg_limit`: avg R/all `0.147`, Calmar `6.78`, DD `-10.9R`
- `timed_hybrid <=5m`: avg R/all `0.129`, Calmar `5.92`, DD `-10.9R`
- `timed_hybrid <=15m`: avg R/all `0.108`, Calmar `4.03`, DD `-13.5R`

### htf_lsi_2m_anchor
- Timeframe: `2m`
- `close`: avg R/all `0.052`, Calmar `2.00`, DD `-21.2R`
- `fvg_limit`: avg R/all `0.093`, Calmar `5.67`, DD `-13.4R`
- `timed_hybrid <=5m`: avg R/all `0.087`, Calmar `5.33`, DD `-13.4R`
- `timed_hybrid <=15m`: avg R/all `0.078`, Calmar `3.98`, DD `-15.9R`

## Detailed Matrix

| Branch | Variant | Signals | Filled | Fill Rate | Avg R / Signal | Avg R / Filled | Net R | Max DD | Calmar |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| classic_lsi_rr2_gated | close | 137 | 137 | 1.000 | 0.173 | 0.173 | 23.7 | -4.9 | 4.80 |
| classic_lsi_rr2_gated | fvg_limit | 140 | 123 | 0.879 | 0.190 | 0.217 | 26.6 | -3.8 | 6.97 |
| classic_lsi_rr2_gated | timed_hybrid<=5m | 140 | 123 | 0.879 | 0.184 | 0.209 | 25.7 | -3.8 | 6.72 |
| classic_lsi_rr2_gated | timed_hybrid<=15m | 140 | 123 | 0.879 | 0.166 | 0.190 | 23.3 | -3.8 | 6.10 |
| htf_lsi_5m_lag24 | close | 506 | 506 | 1.000 | 0.054 | 0.054 | 27.4 | -17.7 | 1.55 |
| htf_lsi_5m_lag24 | fvg_limit | 503 | 456 | 0.907 | 0.147 | 0.163 | 74.2 | -10.9 | 6.78 |
| htf_lsi_5m_lag24 | timed_hybrid<=5m | 503 | 458 | 0.911 | 0.129 | 0.141 | 64.8 | -10.9 | 5.92 |
| htf_lsi_5m_lag24 | timed_hybrid<=15m | 503 | 464 | 0.922 | 0.108 | 0.118 | 54.6 | -13.5 | 4.03 |
| htf_lsi_2m_anchor | close | 819 | 793 | 0.968 | 0.052 | 0.053 | 42.4 | -21.2 | 2.00 |
| htf_lsi_2m_anchor | fvg_limit | 818 | 747 | 0.913 | 0.093 | 0.102 | 76.0 | -13.4 | 5.67 |
| htf_lsi_2m_anchor | timed_hybrid<=5m | 818 | 750 | 0.917 | 0.087 | 0.095 | 71.5 | -13.4 | 5.33 |
| htf_lsi_2m_anchor | timed_hybrid<=15m | 818 | 758 | 0.927 | 0.078 | 0.084 | 63.4 | -15.9 | 3.98 |

## Inversion-Time Buckets

### classic_lsi_rr2_gated

| Variant | Bucket | Signals | Filled | Fill Rate | Avg R / Signal | Avg R / Filled | WR Filled |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| close | <=5m | 137 | 137 | 1.000 | 0.173 | 0.173 | 0.591 |
| close | 6-15m | 0 | 0 | NA | NA | NA | NA |
| close | >15m | 0 | 0 | NA | NA | NA | NA |
| fvg_limit | <=5m | 140 | 123 | 0.879 | 0.190 | 0.217 | 0.593 |
| fvg_limit | 6-15m | 0 | 0 | NA | NA | NA | NA |
| fvg_limit | >15m | 0 | 0 | NA | NA | NA | NA |

### htf_lsi_5m_lag24

| Variant | Bucket | Signals | Filled | Fill Rate | Avg R / Signal | Avg R / Filled | WR Filled |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| close | <=5m | 22 | 22 | 1.000 | -0.297 | -0.297 | 0.318 |
| close | 6-15m | 91 | 91 | 1.000 | 0.110 | 0.110 | 0.451 |
| close | >15m | 393 | 393 | 1.000 | 0.061 | 0.061 | 0.504 |
| fvg_limit | <=5m | 22 | 20 | 0.909 | 0.131 | 0.144 | 0.450 |
| fvg_limit | 6-15m | 91 | 85 | 0.934 | 0.222 | 0.238 | 0.494 |
| fvg_limit | >15m | 390 | 351 | 0.900 | 0.131 | 0.145 | 0.527 |

### htf_lsi_2m_anchor

| Variant | Bucket | Signals | Filled | Fill Rate | Avg R / Signal | Avg R / Filled | WR Filled |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| close | <=5m | 48 | 48 | 1.000 | 0.199 | 0.199 | 0.438 |
| close | 6-15m | 240 | 235 | 0.979 | -0.009 | -0.009 | 0.387 |
| close | >15m | 531 | 510 | 0.960 | 0.066 | 0.069 | 0.482 |
| fvg_limit | <=5m | 48 | 45 | 0.938 | 0.295 | 0.314 | 0.422 |
| fvg_limit | 6-15m | 240 | 227 | 0.946 | 0.025 | 0.026 | 0.383 |
| fvg_limit | >15m | 530 | 475 | 0.896 | 0.106 | 0.118 | 0.480 |

