# NQ NY HTF-LSI 2m Inversion-Ordinal Compare

- Objective: test whether waiting for inversion `#2` or `#3` after the sweep improves the frozen `2m` HTF-LSI anchor versus the base `#1` inversion.
- Holdout stays closed. This is a pre-holdout stitched-OOS packet only.
- Fixed anchor: `2m`, `long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, `max_fvg_to_inversion_bars=0`.
- Tested inversion ordinals: `1`, `2`, `3`.

## Liquidity Families

| Family | Description |
| --- | --- |
| htf_only | HTF 1h unswept highs/lows only |
| session_only | NY / Asia / London session highs/lows only |
| htf_plus_session | HTF 1h levels plus session highs/lows |
| data_only | Same-day data_high/data_low only |
| htf_plus_data | HTF 1h levels plus data_high/data_low |
| all_sources | HTF 1h levels plus session highs/lows plus data_high/data_low |

## Best Row By Family

| Family | Best Ordinal | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | 1 | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 1.212 | 0.104 | 3.763 | 486 | -13.41 |
| htf_plus_session | 1 | 1.187 | 0.092 | 1.256 | 0.126 | 2.716 | 1.211 | 0.103 | 3.571 | 737 | -21.19 |
| session_only | 1 | 1.171 | 0.083 | 1.286 | 0.140 | 2.821 | 1.210 | 0.100 | 3.010 | 641 | -21.32 |
| all_sources | 1 | 1.093 | 0.048 | 1.031 | 0.021 | 0.520 | 1.105 | 0.053 | 2.911 | 930 | -16.89 |
| htf_plus_data | 1 | 1.095 | 0.049 | 0.994 | -0.003 | -0.055 | 1.087 | 0.043 | 1.517 | 797 | -22.74 |
| data_only | 1 | 1.042 | 0.022 | 0.941 | -0.038 | -0.418 | 0.984 | -0.010 | -0.214 | 585 | -25.98 |

## Full Matrix

| Family | Ordinal | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all_sources | 1 | 1.093 | 0.048 | 1.031 | 0.021 | 0.520 | 364 | 1.105 | 0.053 | 2.911 | 930 | -16.89 |
| all_sources | 2 | 0.981 | -0.014 | 1.160 | 0.070 | 1.190 | 134 | 1.062 | 0.015 | 0.348 | 351 | -15.24 |
| all_sources | 3 | 1.448 | 0.128 | 1.318 | 0.077 | 0.892 | 37 | 1.189 | 0.061 | 1.440 | 104 | -4.41 |
| data_only | 1 | 1.042 | 0.022 | 0.941 | -0.038 | -0.418 | 248 | 0.984 | -0.010 | -0.214 | 585 | -25.98 |
| data_only | 2 | 1.101 | 0.035 | 0.793 | -0.083 | -0.538 | 112 | 0.953 | -0.024 | -0.396 | 253 | -15.62 |
| data_only | 3 | 1.109 | 0.040 | 1.542 | 0.131 | 1.039 | 30 | 0.929 | -0.031 | -0.360 | 93 | -7.89 |
| htf_only | 1 | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 180 | 1.212 | 0.104 | 3.763 | 486 | -13.41 |
| htf_only | 2 | 1.242 | 0.071 | 1.340 | 0.116 | 0.808 | 55 | 1.184 | 0.053 | 0.511 | 158 | -16.41 |
| htf_only | 3 | 1.018 | -0.010 | 2.188 | 0.354 | 1.830 | 13 | 1.129 | 0.039 | 0.385 | 57 | -5.82 |
| htf_plus_data | 1 | 1.095 | 0.049 | 0.994 | -0.003 | -0.055 | 314 | 1.087 | 0.043 | 1.517 | 797 | -22.74 |
| htf_plus_data | 2 | 1.069 | 0.020 | 1.021 | 0.009 | 0.079 | 115 | 1.076 | 0.021 | 0.283 | 304 | -22.63 |
| htf_plus_data | 3 | 1.047 | 0.008 | 1.837 | 0.188 | 1.382 | 29 | 1.010 | -0.007 | -0.103 | 101 | -6.41 |
| htf_plus_session | 1 | 1.187 | 0.092 | 1.256 | 0.126 | 2.716 | 272 | 1.211 | 0.103 | 3.571 | 737 | -21.19 |
| htf_plus_session | 2 | 1.102 | 0.023 | 1.348 | 0.113 | 1.126 | 94 | 1.042 | -0.002 | -0.027 | 267 | -17.39 |
| htf_plus_session | 3 | 1.370 | 0.097 | 1.041 | 0.024 | 0.140 | 28 | 1.203 | 0.068 | 0.802 | 84 | -7.15 |
| session_only | 1 | 1.171 | 0.083 | 1.286 | 0.140 | 2.821 | 236 | 1.210 | 0.100 | 3.010 | 641 | -21.32 |
| session_only | 2 | 1.163 | 0.049 | 1.177 | 0.062 | 0.543 | 90 | 1.030 | -0.000 | -0.008 | 243 | -12.80 |
| session_only | 3 | 1.517 | 0.118 | 1.136 | 0.033 | 0.213 | 20 | 1.252 | 0.072 | 0.802 | 80 | -7.19 |

## Reference-Level Flow

### htf_only (best ordinal = 1)

- Pre-holdout filled `747`, HTF `747`, reference/data `0`
- Validation filled `180`, HTF `180`, reference/data `0`
- No reference/data-driven filled trades.

### htf_plus_session (best ordinal = 1)

- Pre-holdout filled `1128`, HTF `427`, reference/data `701`
- Validation filled `272`, HTF `99`, reference/data `173`

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| new_york_high | 0 | 0 |
| new_york_low | 215 | 58 |
| asia_high | 0 | 0 |
| asia_low | 275 | 69 |
| london_high | 0 | 0 |
| london_low | 211 | 46 |
| data_high | 0 | 0 |
| data_low | 0 | 0 |

### session_only (best ordinal = 1)

- Pre-holdout filled `978`, HTF `0`, reference/data `978`
- Validation filled `236`, HTF `0`, reference/data `236`

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| new_york_high | 0 | 0 |
| new_york_low | 234 | 64 |
| asia_high | 0 | 0 |
| asia_low | 422 | 108 |
| london_high | 0 | 0 |
| london_low | 322 | 64 |
| data_high | 0 | 0 |
| data_low | 0 | 0 |

### all_sources (best ordinal = 1)

- Pre-holdout filled `1409`, HTF `320`, reference/data `1089`
- Validation filled `364`, HTF `73`, reference/data `291`

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| new_york_high | 0 | 0 |
| new_york_low | 154 | 41 |
| asia_high | 0 | 0 |
| asia_low | 207 | 52 |
| london_high | 0 | 0 |
| london_low | 170 | 33 |
| data_high | 0 | 0 |
| data_low | 558 | 165 |

### htf_plus_data (best ordinal = 1)

- Pre-holdout filled `1222`, HTF `520`, reference/data `702`
- Validation filled `314`, HTF `115`, reference/data `199`

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| new_york_high | 0 | 0 |
| new_york_low | 0 | 0 |
| asia_high | 0 | 0 |
| asia_low | 0 | 0 |
| london_high | 0 | 0 |
| london_low | 0 | 0 |
| data_high | 0 | 0 |
| data_low | 702 | 199 |

### data_only (best ordinal = 1)

- Pre-holdout filled `893`, HTF `0`, reference/data `893`
- Validation filled `248`, HTF `0`, reference/data `248`

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| new_york_high | 0 | 0 |
| new_york_low | 0 | 0 |
| asia_high | 0 | 0 |
| asia_low | 0 | 0 |
| london_high | 0 | 0 |
| london_low | 0 | 0 |
| data_high | 0 | 0 |
| data_low | 893 | 248 |
