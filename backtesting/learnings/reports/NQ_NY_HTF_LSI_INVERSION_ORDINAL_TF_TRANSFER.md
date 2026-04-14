# NQ NY HTF-LSI Inversion-Ordinal TF Transfer

- Objective: test whether waiting for inversion `#2` or `#3` helps outside the original `2m` packet when we only keep the two live liquidity families: `htf_only` and `htf_plus_session`.
- Holdout stays closed. This is a pre-holdout stitched-OOS transfer packet only.
- Fixed-config stitched OOS is computed by slicing each full-period trade stream into the standard `36m IS / 12m OOS / 12m step` windows.
- Families tested: `htf_only`, `htf_plus_session`.
- Inversion ordinals tested: `1`, `2`, `3`.

## Anchors

| Timeframe | Anchor | Entry | Window | RR | TP1 | Cap | FVG Window | Note |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 1m | lag=0 | long / close | 08:30-15:00 | 3.0 | 0.6 | 2 | L100 / R10 | honest 1m lag-curve baseline; the later lag10 pop was never promoted beyond validation |
| 2m | lag=0 | long / fvg_limit | 08:30-15:00 | 3.0 | 0.6 | 1 | L50 / R5 | frozen 2m secondary anchor used in the session/data source experiments |
| 3m | lag=0 | long / fvg_limit | 08:30-15:00 | 3.0 | 0.6 | 2 | L33 / R3 | honest 3m baseline; 3m remains closed because discovery stayed too weak |
| 5m | lag=24 | long / fvg_limit | 08:30-15:00 | 3.0 | 0.6 | 2 | L20 / R2 | promoted frozen 5m lead from the late-lag follow-up |

## Best Row By Timeframe / Family

| Timeframe | Family | Best Ordinal | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m | htf_only | 1 | 1.082 | 0.041 | 1.263 | 0.126 | 1.711 | 1.147 | 0.073 | 2.168 | 577 | -19.35 |
| 1m | htf_plus_session | 3 | 1.488 | 0.118 | 0.939 | -0.020 | -0.230 | 1.342 | 0.083 | 1.892 | 165 | -7.20 |
| 2m | htf_only | 1 | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 1.212 | 0.104 | 3.763 | 486 | -13.41 |
| 2m | htf_plus_session | 1 | 1.187 | 0.092 | 1.256 | 0.126 | 2.716 | 1.211 | 0.103 | 3.571 | 737 | -21.19 |
| 3m | htf_only | 1 | 0.947 | -0.022 | 1.545 | 0.219 | 5.210 | 1.155 | 0.078 | 2.637 | 444 | -13.07 |
| 3m | htf_plus_session | 1 | 1.052 | 0.030 | 1.367 | 0.161 | 5.415 | 1.133 | 0.068 | 3.500 | 780 | -15.16 |
| 5m | htf_only | 1 | 1.188 | 0.088 | 1.597 | 0.268 | 6.382 | 1.347 | 0.162 | 4.849 | 330 | -11.01 |
| 5m | htf_plus_session | 1 | 1.112 | 0.054 | 1.244 | 0.125 | 3.022 | 1.117 | 0.062 | 1.517 | 579 | -23.84 |

## Full Matrix

| Timeframe | Family | Ordinal | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m | htf_only | 1 | 1.082 | 0.041 | 1.263 | 0.126 | 1.711 | 219 | 1.147 | 0.073 | 2.168 | 577 | -19.35 |
| 1m | htf_only | 2 | 1.182 | 0.056 | 1.154 | 0.053 | 0.752 | 85 | 1.164 | 0.046 | 0.806 | 236 | -13.60 |
| 1m | htf_only | 3 | 1.787 | 0.184 | 1.078 | 0.029 | 0.147 | 39 | 1.515 | 0.128 | 1.679 | 101 | -7.71 |
| 1m | htf_plus_session | 1 | 1.046 | 0.023 | 1.214 | 0.105 | 1.607 | 367 | 1.055 | 0.030 | 0.847 | 1012 | -36.10 |
| 1m | htf_plus_session | 2 | 1.217 | 0.071 | 0.982 | -0.017 | -0.216 | 151 | 1.147 | 0.041 | 0.733 | 409 | -22.97 |
| 1m | htf_plus_session | 3 | 1.488 | 0.118 | 0.939 | -0.020 | -0.230 | 69 | 1.342 | 0.083 | 1.892 | 165 | -7.20 |
| 2m | htf_only | 1 | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 180 | 1.212 | 0.104 | 3.763 | 486 | -13.41 |
| 2m | htf_only | 2 | 1.242 | 0.071 | 1.340 | 0.116 | 0.808 | 55 | 1.184 | 0.053 | 0.511 | 158 | -16.41 |
| 2m | htf_only | 3 | 1.018 | -0.010 | 2.188 | 0.354 | 1.830 | 13 | 1.129 | 0.039 | 0.385 | 57 | -5.82 |
| 2m | htf_plus_session | 1 | 1.187 | 0.092 | 1.256 | 0.126 | 2.716 | 272 | 1.211 | 0.103 | 3.571 | 737 | -21.19 |
| 2m | htf_plus_session | 2 | 1.102 | 0.023 | 1.348 | 0.113 | 1.126 | 94 | 1.042 | -0.002 | -0.027 | 267 | -17.39 |
| 2m | htf_plus_session | 3 | 1.370 | 0.097 | 1.041 | 0.024 | 0.140 | 28 | 1.203 | 0.068 | 0.802 | 84 | -7.15 |
| 3m | htf_only | 1 | 0.947 | -0.022 | 1.545 | 0.219 | 5.210 | 159 | 1.155 | 0.078 | 2.637 | 444 | -13.07 |
| 3m | htf_only | 2 | 1.283 | 0.075 | 0.864 | -0.041 | -0.212 | 42 | 1.054 | 0.013 | 0.117 | 130 | -14.77 |
| 3m | htf_only | 3 | 2.064 | 0.164 | 0.622 | -0.086 | -0.355 | 18 | 0.981 | -0.012 | -0.102 | 44 | -5.02 |
| 3m | htf_plus_session | 1 | 1.052 | 0.030 | 1.367 | 0.161 | 5.415 | 279 | 1.133 | 0.068 | 3.500 | 780 | -15.16 |
| 3m | htf_plus_session | 2 | 1.253 | 0.069 | 0.893 | -0.022 | -0.241 | 74 | 1.086 | 0.031 | 0.509 | 213 | -12.94 |
| 3m | htf_plus_session | 3 | 2.747 | 0.215 | 0.652 | -0.081 | -0.497 | 26 | 1.099 | 0.001 | 0.006 | 64 | -6.97 |
| 5m | htf_only | 1 | 1.188 | 0.088 | 1.597 | 0.268 | 6.382 | 127 | 1.347 | 0.162 | 4.849 | 330 | -11.01 |
| 5m | htf_only | 2 | 1.141 | 0.036 | 0.817 | -0.112 | -0.470 | 20 | 0.942 | -0.044 | -0.456 | 63 | -6.10 |
| 5m | htf_only | 3 | 1.608 | 0.109 | 1.475 | 0.225 | 0.000 | 4 | 1.116 | 0.114 | 0.544 | 5 | -1.05 |
| 5m | htf_plus_session | 1 | 1.112 | 0.054 | 1.244 | 0.125 | 3.022 | 214 | 1.117 | 0.062 | 1.517 | 579 | -23.84 |
| 5m | htf_plus_session | 2 | 1.302 | 0.086 | 0.708 | -0.155 | -0.696 | 34 | 0.895 | -0.060 | -0.515 | 100 | -11.62 |
| 5m | htf_plus_session | 3 | 51.935 | 0.502 | 0.583 | -0.188 | -0.470 | 6 | 0.537 | -0.181 | -0.528 | 7 | -2.41 |