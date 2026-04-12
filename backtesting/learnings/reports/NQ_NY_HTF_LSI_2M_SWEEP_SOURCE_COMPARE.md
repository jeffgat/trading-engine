# NQ NY HTF-LSI 2m Sweep-Source Compare

- Objective: compare three sweep-source variants on the frozen `2m` anchor without reopening the holdout.
- Anchor: `long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, `lag0`.
- Reference/session basket: `new_york_high, new_york_low, asia_high, london_high, asia_low, london_low, previous_day_high, previous_day_low, previous_week_high, previous_week_low`.
- Stitched OOS: `36m IS / 12m OOS / 12m step` from `2016-01-01` to `2025-04-01`.

## Summary

| Variant | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | 1.186 | 0.094 | 1.275 | 0.127 | 2.057 | 180 | 1.212 | 0.104 | 3.763 | 486 | -13.41 |
| htf_plus_reference | 1.186 | 0.094 | 1.168 | 0.086 | 1.950 | 285 | 1.199 | 0.100 | 3.563 | 768 | -21.46 |
| reference_only | 1.157 | 0.079 | 1.135 | 0.071 | 1.535 | 251 | 1.165 | 0.082 | 3.020 | 678 | -18.39 |

## Source Use

| Variant | Pre-Holdout Filled | Pre HTF | Pre Ref | Validation Filled | Val HTF | Val Ref |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| htf_only | 747 | 747 | 0 | 180 | 180 | 0 |
| htf_plus_reference | 1175 | 412 | 763 | 285 | 94 | 191 |
| reference_only | 1033 | 0 | 1033 | 251 | 0 | 251 |

## Reference-Level Breakdown

### htf_only

No reference-driven filled trades.

### htf_plus_reference

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| new_york_high | 0 | 0 |
| new_york_low | 179 | 48 |
| asia_high | 0 | 0 |
| london_high | 0 | 0 |
| asia_low | 254 | 66 |
| london_low | 209 | 46 |
| previous_day_high | 0 | 0 |
| previous_day_low | 91 | 22 |
| previous_week_high | 0 | 0 |
| previous_week_low | 30 | 9 |

### reference_only

| Level | Pre-Holdout Trades | Validation Trades |
| --- | ---: | ---: |
| new_york_high | 0 | 0 |
| new_york_low | 191 | 51 |
| asia_high | 0 | 0 |
| london_high | 0 | 0 |
| asia_low | 388 | 99 |
| london_low | 319 | 64 |
| previous_day_high | 0 | 0 |
| previous_day_low | 104 | 27 |
| previous_week_high | 0 | 0 |
| previous_week_low | 31 | 10 |
