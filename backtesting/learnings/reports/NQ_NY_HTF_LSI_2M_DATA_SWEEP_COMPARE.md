# NQ NY HTF-LSI 2m Data-Sweep Compare

- Objective: compare HTF pivots versus new `data_high/data_low` sweep sources on the frozen `2m` anchor.
- Data level definition: completed `1m` candle with range >= `15%` of previous-day ATR; its high/low become valid on the first eligible base bar after the `1m` close and stay active for the rest of that day.
- Anchor: `long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, `lag0`.
- Data-level basket: `data_high, data_low` at `data_sweep_min_daily_atr_pct=15.0`.
- Stitched OOS: `36m IS / 12m OOS / 12m step` from `2016-01-01` to `2025-04-01`.

## Summary

| Variant | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 180 | 1.212 | 0.104 | 3.763 | 486 | -13.41 |
| htf_plus_data | 1.095 | 0.049 | 0.994 | -0.003 | -0.055 | 314 | 1.087 | 0.043 | 1.517 | 797 | -22.74 |
| data_only | 1.042 | 0.022 | 0.941 | -0.038 | -0.418 | 248 | 0.984 | -0.010 | -0.214 | 585 | -25.98 |

## Source Use

| Variant | Pre-Holdout Filled | Pre HTF | Pre Data | Validation Filled | Val HTF | Val Data |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | 747 | 747 | 0 | 180 | 180 | 0 |
| htf_plus_data | 1222 | 520 | 702 | 314 | 115 | 199 |
| data_only | 893 | 0 | 893 | 248 | 0 | 248 |

## Data-Level Breakdown

### htf_only

No data-driven filled trades.

### htf_plus_data

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| data_high | 0 | 0 |
| data_low | 702 | 199 |

### data_only

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| data_high | 0 | 0 |
| data_low | 893 | 248 |
