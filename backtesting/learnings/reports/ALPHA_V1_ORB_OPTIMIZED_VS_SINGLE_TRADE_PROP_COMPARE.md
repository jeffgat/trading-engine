# ALPHA_V1 ORB Optimized Rules Vs Single-Trade Legs

- Scope: the three ORB legs from `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`).
- Comparison:
  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.
  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.
- Prop scorecard model: `+5R` payout, `-4R` breach, `-2R` daily loss limit, `5` minimum trading days, `$50` fee + `$50` reset, `80%` payout split.
- Last 10 years available in repo: `2016-04-17` to `2026-03-24`.
- `2026` is partial in this repo: `2026-01-01` to `2026-03-24`.

## Comparison Table

| period | window | rules | max_dd_r | net_r | payouts | breaches | payout_rate | breach_rate | resolved_payout_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | 2016-04-17 to 2026-03-24 | Current single-trade legs | -21.18 | 360 | 1060 | 2029 | 34.27 | 65.60 | 34.32 |
| Last 10y available | 2016-04-17 to 2026-03-24 | Optimized rules | -21.38 | 440 | 1075 | 2014 | 34.76 | 65.11 | 34.80 |
| 2024 | 2024-01-01 to 2024-12-31 | Current single-trade legs | -9.52 | 27.57 | 70 | 230 | 22.36 | 73.48 | 23.33 |
| 2024 | 2024-01-01 to 2024-12-31 | Optimized rules | -10.54 | 48.41 | 84 | 208 | 26.84 | 66.45 | 28.77 |
| 2025 | 2025-01-01 to 2025-12-31 | Current single-trade legs | -9.88 | 58.10 | 178 | 133 | 57.05 | 42.63 | 57.23 |
| 2025 | 2025-01-01 to 2025-12-31 | Optimized rules | -11.31 | 62.15 | 150 | 161 | 48.08 | 51.60 | 48.23 |
| 2026 YTD | 2026-01-01 to 2026-03-24 | Current single-trade legs | -8.06 | 10.40 | 13 | 54 | 18.31 | 76.06 | 19.40 |
| 2026 YTD | 2026-01-01 to 2026-03-24 | Optimized rules | -11.94 | 14.53 | 14 | 53 | 19.72 | 74.65 | 20.90 |

