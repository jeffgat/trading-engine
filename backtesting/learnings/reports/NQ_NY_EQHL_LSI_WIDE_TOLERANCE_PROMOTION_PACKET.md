# NQ NY EQHL-LSI Wide Tolerance Promotion Packet

- Objective: local promotion sweep around the widened-tolerance EQHL-LSI winners.
- Scope: only `rr`, `tp1_ratio`, `lsi_fvg_window_left`, and `lsi_fvg_window_right` move. All EQHL source settings stay frozen to the wide-tolerance discovery winners.
- Pre-holdout window: `2016-01-01` to `2025-04-01`. Opened holdout remains closed.

## 1m_eqhl60m_tol10p

- Base entry TF: `1m`
- EQHL source TF: `60m`
- Frozen sweep semantics: `tol=10.0 points`, `touches=2`, `long`, `fvg_limit`, `entry_end=13:00`
- Configs tested: `108`
- Survivors: `108`

| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left100 right12 rr2.75 tp0.4 | 1.132 | 0.065 | 2.371 | 0.388 | 5.968 | 60 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left120 right12 rr2.75 tp0.4 | 1.132 | 0.065 | 2.371 | 0.388 | 5.968 | 60 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left80 right12 rr2.75 tp0.4 | 1.132 | 0.065 | 2.316 | 0.376 | 5.791 | 60 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left100 right10 rr2.75 tp0.4 | 1.161 | 0.077 | 2.239 | 0.368 | 5.664 | 60 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left120 right10 rr2.75 tp0.4 | 1.161 | 0.077 | 2.239 | 0.368 | 5.664 | 60 |

| WF Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left100 right12 rr2.75 tp0.4 | 1.364 | 0.160 | 2.375 | 184 | -12.39 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left120 right12 rr2.75 tp0.4 | 1.364 | 0.160 | 2.375 | 184 | -12.39 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left100 right10 rr2.75 tp0.4 | 1.378 | 0.163 | 2.368 | 180 | -12.39 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left120 right10 rr2.75 tp0.4 | 1.378 | 0.163 | 2.368 | 180 | -12.39 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol10p left80 right12 rr2.75 tp0.4 | 1.352 | 0.156 | 2.320 | 184 | -12.39 |

## 1m_eqhl60m_tol15p

- Base entry TF: `1m`
- EQHL source TF: `60m`
- Frozen sweep semantics: `tol=15.0 points`, `touches=2`, `long`, `fvg_limit`, `entry_end=15:00`
- Configs tested: `108`
- Survivors: `108`

| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left100 right12 rr3.0 tp0.5 | 1.214 | 0.103 | 2.001 | 0.370 | 10.041 | 99 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left120 right12 rr3.0 tp0.5 | 1.214 | 0.103 | 2.001 | 0.370 | 10.041 | 99 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left80 right12 rr3.0 tp0.5 | 1.215 | 0.103 | 1.970 | 0.361 | 9.804 | 99 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left100 right12 rr2.75 tp0.5 | 1.171 | 0.082 | 1.954 | 0.351 | 9.247 | 99 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left120 right12 rr2.75 tp0.5 | 1.171 | 0.082 | 1.954 | 0.351 | 9.247 | 99 |

| WF Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left100 right12 rr3.0 tp0.5 | 1.350 | 0.164 | 3.007 | 268 | -14.63 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left120 right12 rr3.0 tp0.5 | 1.350 | 0.164 | 3.007 | 268 | -14.63 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left80 right12 rr3.0 tp0.5 | 1.344 | 0.161 | 2.857 | 268 | -15.09 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left100 right12 rr2.75 tp0.5 | 1.304 | 0.142 | 2.459 | 268 | -15.50 |
| NQ NY EQHL_LSI promote 1m_eqhl60m_tol15p left120 right12 rr2.75 tp0.5 | 1.304 | 0.142 | 2.459 | 268 | -15.50 |

## 2m_eqhl15m_tol5p

- Base entry TF: `2m`
- EQHL source TF: `15m`
- Frozen sweep semantics: `tol=5.0 points`, `touches=2`, `long`, `fvg_limit`, `entry_end=13:00`
- Configs tested: `108`
- Survivors: `61`

| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left40 right5 rr3.0 tp0.6 | 1.078 | 0.042 | 1.602 | 0.282 | 5.458 | 152 |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left50 right5 rr3.0 tp0.6 | 1.073 | 0.039 | 1.602 | 0.282 | 5.458 | 152 |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left60 right5 rr3.0 tp0.6 | 1.073 | 0.039 | 1.602 | 0.282 | 5.458 | 152 |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left40 right5 rr3.5 tp0.5 | 1.079 | 0.042 | 1.567 | 0.265 | 5.127 | 152 |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left50 right5 rr3.5 tp0.5 | 1.074 | 0.039 | 1.567 | 0.265 | 5.127 | 152 |

| WF Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left40 right5 rr3.0 tp0.6 | 1.172 | 0.098 | 1.710 | 380 | -21.70 |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left60 right5 rr3.0 tp0.6 | 1.160 | 0.092 | 1.619 | 382 | -21.69 |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left50 right5 rr3.0 tp0.6 | 1.160 | 0.092 | 1.618 | 382 | -21.70 |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left40 right5 rr3.5 tp0.5 | 1.140 | 0.081 | 1.403 | 380 | -21.92 |
| NQ NY EQHL_LSI promote 2m_eqhl15m_tol5p left50 right5 rr3.5 tp0.5 | 1.129 | 0.075 | 1.312 | 382 | -21.92 |

## 3m_eqhl15m_tol15p

- Base entry TF: `3m`
- EQHL source TF: `15m`
- Frozen sweep semantics: `tol=15.0 points`, `touches=2`, `long`, `fvg_limit`, `entry_end=13:00`
- Configs tested: `108`
- Survivors: `108`

| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left27 right4 rr2.75 tp0.6 | 1.093 | 0.048 | 1.668 | 0.291 | 9.633 | 173 |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left33 right4 rr2.75 tp0.6 | 1.091 | 0.047 | 1.672 | 0.291 | 9.627 | 173 |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left39 right4 rr2.75 tp0.6 | 1.084 | 0.043 | 1.672 | 0.291 | 9.627 | 173 |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left27 right4 rr2.75 tp0.5 | 1.125 | 0.060 | 1.702 | 0.287 | 9.499 | 173 |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left33 right4 rr2.75 tp0.5 | 1.124 | 0.059 | 1.705 | 0.287 | 9.492 | 173 |

| WF Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left27 right4 rr2.75 tp0.5 | 1.225 | 0.110 | 2.501 | 458 | -20.06 |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left33 right4 rr2.75 tp0.5 | 1.221 | 0.107 | 2.449 | 459 | -20.06 |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left27 right4 rr2.75 tp0.6 | 1.191 | 0.101 | 1.981 | 458 | -23.33 |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left33 right4 rr2.75 tp0.6 | 1.187 | 0.098 | 1.937 | 459 | -23.33 |
| NQ NY EQHL_LSI promote 3m_eqhl15m_tol15p left39 right4 rr2.75 tp0.6 | 1.177 | 0.093 | 1.690 | 461 | -25.33 |

## 5m_eqhl5m_tol5p

- Base entry TF: `5m`
- EQHL source TF: `5m`
- Frozen sweep semantics: `tol=5.0 points`, `touches=2`, `long`, `fvg_limit`, `entry_end=13:00`
- Configs tested: `108`
- Survivors: `91`

| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left20 right1 rr2.75 tp0.6 | 1.055 | 0.027 | 1.663 | 0.259 | 9.419 | 149 |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left24 right1 rr2.75 tp0.6 | 1.053 | 0.025 | 1.642 | 0.253 | 9.255 | 150 |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left24 right2 rr2.75 tp0.4 | 1.103 | 0.042 | 1.503 | 0.192 | 9.087 | 166 |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left24 right2 rr2.75 tp0.6 | 1.054 | 0.026 | 1.675 | 0.274 | 8.802 | 166 |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left16 right2 rr2.75 tp0.6 | 1.052 | 0.025 | 1.722 | 0.287 | 8.577 | 164 |

| WF Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left16 right2 rr2.75 tp0.6 | 1.372 | 0.169 | 4.073 | 380 | -15.74 |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left24 right2 rr2.75 tp0.4 | 1.354 | 0.140 | 3.922 | 386 | -13.74 |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left20 right1 rr2.75 tp0.6 | 1.361 | 0.161 | 3.832 | 352 | -14.74 |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left24 right2 rr2.75 tp0.6 | 1.367 | 0.166 | 3.608 | 386 | -17.74 |
| NQ NY EQHL_LSI promote 5m_eqhl5m_tol5p left24 right1 rr2.75 tp0.6 | 1.357 | 0.157 | 3.328 | 355 | -16.74 |
