# NQ NY HTF-LSI 2m Data Session-Extreme Compare

- Objective: keep the `data_high/data_low` concept but only allow spike candles that also print a new running NY-session extreme.
- Data level definition: completed `1m` candle with range >= `15%` of previous-day ATR. `data_high` only updates when that candle also sets a new running session high; `data_low` only updates when it also sets a new running session low. Levels publish on the first eligible base bar after the `1m` close and stay active for the rest of that day.
- Anchor: `long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, `lag0`.
- Data-level basket: `data_high, data_low` at `data_sweep_min_daily_atr_pct=15.0` with `data_sweep_require_session_extreme=True`.
- Stitched OOS: `36m IS / 12m OOS / 12m step` from `2016-01-01` to `2025-04-01`.

## Summary

| Variant | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 180 | 1.212 | 0.104 | 3.763 | 486 | -13.41 |
| htf_plus_data_session_extreme | 1.153 | 0.076 | 1.186 | 0.088 | 2.005 | 237 | 1.154 | 0.074 | 2.453 | 642 | -19.30 |
| data_only_session_extreme | 1.109 | 0.052 | 0.988 | -0.019 | -0.171 | 124 | 0.998 | -0.007 | -0.098 | 323 | -22.42 |

## Source Use

| Variant | Pre-Holdout Filled | Pre HTF | Pre Data | Validation Filled | Val HTF | Val Data |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | 747 | 747 | 0 | 180 | 180 | 0 |
| htf_plus_data_session_extreme | 1000 | 603 | 397 | 237 | 136 | 101 |
| data_only_session_extreme | 519 | 0 | 519 | 124 | 0 | 124 |

## Data-Level Breakdown

### htf_only

No data-driven filled trades.

### htf_plus_data_session_extreme

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| data_high | 0 | 0 |
| data_low | 397 | 101 |

### data_only_session_extreme

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| data_high | 0 | 0 |
| data_low | 519 | 124 |
