# NQ NY EQHL-LSI Promotion Packet

- Objective: local promotion sweep around the two surviving EQHL-LSI families.
- Scope: only `rr`, `tp1_ratio`, `lsi_fvg_window_left`, and `lsi_fvg_window_right` move. All EQHL source settings stay frozen to the broad-discovery winners.
- Pre-holdout window: `2016-01-01` to `2025-04-01`. Opened holdout remains closed.

## 5m_eqhl5m

- Base entry TF: `5m`
- EQHL source TF: `5m`
- Frozen sweep semantics: `tol=2 ticks`, `touches=2`, `long`, `fvg_limit`, `entry_end=13:00`
- Configs tested: `135`
- Survivors: `99`

| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 5m_eqhl5m left20 right1 rr3.5 tp0.6 | 1.063 | 0.026 | 1.876 | 0.347 | 8.368 | 85 |
| NQ NY EQHL_LSI promote 5m_eqhl5m left24 right1 rr3.5 tp0.6 | 1.054 | 0.023 | 1.876 | 0.347 | 8.368 | 85 |
| NQ NY EQHL_LSI promote 5m_eqhl5m left20 right3 rr3.25 tp0.6 | 1.108 | 0.050 | 1.885 | 0.353 | 8.260 | 106 |
| NQ NY EQHL_LSI promote 5m_eqhl5m left24 right3 rr3.25 tp0.6 | 1.108 | 0.050 | 1.885 | 0.353 | 8.260 | 106 |
| NQ NY EQHL_LSI promote 5m_eqhl5m left16 right3 rr3.25 tp0.6 | 1.111 | 0.051 | 1.826 | 0.333 | 7.715 | 105 |

| WF Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 5m_eqhl5m left20 right3 rr3.25 tp0.6 | 1.248 | 0.124 | 2.233 | 257 | -14.24 |
| NQ NY EQHL_LSI promote 5m_eqhl5m left24 right3 rr3.25 tp0.6 | 1.248 | 0.124 | 2.233 | 257 | -14.24 |
| NQ NY EQHL_LSI promote 5m_eqhl5m left16 right3 rr3.25 tp0.6 | 1.230 | 0.115 | 2.060 | 256 | -14.24 |
| NQ NY EQHL_LSI promote 5m_eqhl5m left20 right1 rr3.5 tp0.6 | 1.242 | 0.117 | 1.423 | 207 | -16.99 |
| NQ NY EQHL_LSI promote 5m_eqhl5m left24 right1 rr3.5 tp0.6 | 1.242 | 0.117 | 1.423 | 207 | -16.99 |

## 2m_eqhl15m

- Base entry TF: `2m`
- EQHL source TF: `15m`
- Frozen sweep semantics: `tol=2 ticks`, `touches=2`, `long`, `fvg_limit`, `entry_end=15:00`
- Configs tested: `135`
- Survivors: `135`

| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 2m_eqhl15m left40 right5 rr2.5 tp0.5 | 1.240 | 0.099 | 1.528 | 0.200 | 3.074 | 57 |
| NQ NY EQHL_LSI promote 2m_eqhl15m left50 right5 rr2.5 tp0.5 | 1.228 | 0.094 | 1.528 | 0.200 | 3.074 | 57 |
| NQ NY EQHL_LSI promote 2m_eqhl15m left60 right5 rr2.5 tp0.5 | 1.228 | 0.094 | 1.528 | 0.200 | 3.074 | 57 |
| NQ NY EQHL_LSI promote 2m_eqhl15m left40 right5 rr2.75 tp0.5 | 1.249 | 0.103 | 1.566 | 0.237 | 2.908 | 57 |
| NQ NY EQHL_LSI promote 2m_eqhl15m left50 right5 rr2.75 tp0.5 | 1.238 | 0.099 | 1.566 | 0.237 | 2.908 | 57 |

| WF Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI promote 2m_eqhl15m left40 right5 rr2.75 tp0.5 | 1.133 | 0.059 | 0.609 | 142 | -13.73 |
| NQ NY EQHL_LSI promote 2m_eqhl15m left50 right5 rr2.75 tp0.5 | 1.115 | 0.051 | 0.536 | 143 | -13.73 |
| NQ NY EQHL_LSI promote 2m_eqhl15m left40 right5 rr2.5 tp0.5 | 1.099 | 0.043 | 0.476 | 142 | -12.86 |
| NQ NY EQHL_LSI promote 2m_eqhl15m left50 right5 rr2.5 tp0.5 | 1.081 | 0.036 | 0.398 | 143 | -12.86 |
| NQ NY EQHL_LSI promote 2m_eqhl15m left60 right5 rr2.5 tp0.5 | 1.081 | 0.036 | 0.398 | 143 | -12.86 |
