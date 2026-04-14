# NQ NY HTF-LSI 2m Data Macro-Window Compare

- Objective: continue the `data_high/data_low` idea with the cleaner scheduled macro-release thesis.
- Data level definition: completed `1m` candle with range >= `15%` of previous-day ATR; keep only candles that also print a new running NY-session extreme and occur within the configured post-release window for `NFP`, `CPI`, `PPI`, or `FOMC`.
- Anchor: `long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, `lag0`.
- Data-level basket: `data_high, data_low` at `data_sweep_min_daily_atr_pct=15.0`, `data_sweep_require_session_extreme=True`, event types `NFP, CPI, PPI, FOMC`.
- Screening packet: windows `0, 1, 2, 5` minutes after the scheduled release (`0` = release-minute candle only).
- Shortlist policy: always keep `htf_only`, then stitch only the top `3` challengers by validation Calmar / PF / avg R.

## Screening

| Variant | Mode | Window | Val PF | Val Avg R | Val Calmar | Val Trades | Disc PF | Disc Avg R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | htf_only | 0 | 1.275 | 0.127 | 2.057 | 180 | 1.186 | 0.094 |
| htf_plus_data_w0 | htf_plus_data | 0 | 1.164 | 0.079 | 1.366 | 189 | 1.146 | 0.075 |
| htf_plus_data_w5 | htf_plus_data | 5 | 1.166 | 0.078 | 1.354 | 190 | 1.155 | 0.080 |
| htf_plus_data_w1 | htf_plus_data | 1 | 1.156 | 0.073 | 1.260 | 188 | 1.151 | 0.078 |
| htf_plus_data_w2 | htf_plus_data | 2 | 1.156 | 0.073 | 1.260 | 188 | 1.155 | 0.080 |
| data_only_w5 | data_only | 5 | 0.605 | -0.216 | -0.898 | 30 | 0.797 | -0.113 |
| data_only_w0 | data_only | 0 | 0.641 | -0.179 | -0.913 | 29 | 0.692 | -0.183 |
| data_only_w1 | data_only | 1 | 0.538 | -0.268 | -0.938 | 28 | 0.728 | -0.162 |
| data_only_w2 | data_only | 2 | 0.538 | -0.268 | -0.938 | 28 | 0.771 | -0.131 |

## Finalists

| Variant | Mode | Window | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD | Val PF | Val Avg R | Val Calmar |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | htf_only | 0 | 1.212 | 0.104 | 3.763 | 486 | -13.41 | 1.275 | 0.127 | 2.057 |
| htf_plus_data_w5 | htf_plus_data | 5 | 1.156 | 0.078 | 2.808 | 507 | -14.05 | 1.166 | 0.078 | 1.354 |
| htf_plus_data_w1 | htf_plus_data | 1 | 1.151 | 0.075 | 2.711 | 506 | -14.05 | 1.156 | 0.073 | 1.260 |
| htf_plus_data_w0 | htf_plus_data | 0 | 1.149 | 0.075 | 2.269 | 505 | -16.63 | 1.164 | 0.079 | 1.366 |

## Finalist Source Use

| Variant | Pre-Holdout Filled | Pre HTF | Pre Data | Validation Filled | Val HTF | Val Data |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | 747 | 747 | 0 | 180 | 180 | 0 |
| htf_plus_data_w5 | 772 | 705 | 67 | 190 | 166 | 24 |
| htf_plus_data_w1 | 768 | 706 | 62 | 188 | 166 | 22 |
| htf_plus_data_w0 | 767 | 706 | 61 | 189 | 166 | 23 |

## Finalist Data-Level Breakdown

### htf_only

No data-driven filled trades.

### htf_plus_data_w5

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| data_high | 0 | 0 |
| data_low | 67 | 24 |

### htf_plus_data_w1

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| data_high | 0 | 0 |
| data_low | 62 | 22 |

### htf_plus_data_w0

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| data_high | 0 | 0 |
| data_low | 61 | 23 |
