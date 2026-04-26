# ALPHA_V1 NQ NY HTF-LSI Funded Target Compare

- Scope: the active `NQ NY HTF-LSI` leg only.
- Exact configs compared:
  - `Current 3.5R`: `long fvg_limit 08:30-13:30 rr3.5 tp0.4 gap3.0 htf60 n3 cap2 fvgL20 fvgR2 lag24`
  - `Reduced 2R`: `long fvg_limit 08:30-13:30 rr2.0 tp0.7 gap3.0 htf60 n3 cap2 fvgL20 fvgR2 lag24`
- First scale is held constant at `1.4R`, so the reduced target uses `tp1_ratio = 0.7`.
- Full data window: `2016-01-01` to `2026-03-24`.
- Fixed funded profile: `$50k` start, `$2k` trailing EOD DD, first payout floor `$52.5k`, challenge fee `$100`, risk `$500` pre-payout / `$250` post-payout`.
- Robustness step: risk is selected on pre-holdout only (`2016-01-01` to `2025-03-31`) and then frozen for the holdout replay.

## Summary

- Fixed-risk holdout payout rate winner: `Current 3.5R` (`3.5R=68.6%`, `2R=67.0%`).
- Fixed-risk holdout breach rate winner: `tie` (`3.5R=0.0%`, `2R=0.0%`).
- Frozen-risk holdout EV per start: `3.5R=$257.5` vs `2R=$129.36`.

## Exact Backtest Metrics

| target | window | trades | win_rate | profit_factor | avg_r | net_r | max_dd_r | calmar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Current 3.5R | 2016-01-01 to 2026-03-24 | 494 | 52.63 | 1.41 | 0.18 | 89.30 | -10.94 | 8.16 |
| Current 3.5R | 2016-01-01 to 2025-03-31 | 456 | 51.75 | 1.37 | 0.16 | 74.19 | -10.94 | 6.78 |
| Current 3.5R | 2024-01-01 to 2026-03-24 | 105 | 57.14 | 1.82 | 0.33 | 34.82 | -5.24 | 6.64 |
| Current 3.5R | 2025-04-01 to 2026-03-24 | 38 | 63.16 | 2.09 | 0.40 | 15.11 | -3 | 5.04 |
| Reduced 2R | 2016-01-01 to 2026-03-24 | 494 | 52.63 | 1.40 | 0.18 | 87.68 | -10.03 | 8.74 |
| Reduced 2R | 2016-01-01 to 2025-03-31 | 456 | 51.75 | 1.37 | 0.16 | 74.00 | -10.03 | 7.38 |
| Reduced 2R | 2024-01-01 to 2026-03-24 | 105 | 57.14 | 1.71 | 0.29 | 30.51 | -5.24 | 5.82 |
| Reduced 2R | 2025-04-01 to 2026-03-24 | 38 | 63.16 | 1.97 | 0.36 | 13.68 | -3 | 4.56 |

## Fixed Funded Profile

| target | window | risk_pre_usd | risk_post_usd | payout_rate | breach_rate | open_rate | avg_days_to_payout | median_days_to_payout | ev_per_start_usd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Current 3.5R | 2016-01-01 to 2026-03-24 | 500 | 250 | 62.57 | 34.41 | 3.02 | 90.55 | 85 | 162 |
| Current 3.5R | 2016-01-01 to 2025-03-31 | 500 | 250 | 61.40 | 34.28 | 4.31 | 90.70 | 85 | 161 |
| Current 3.5R | 2024-01-01 to 2026-03-24 | 500 | 250 | 61.93 | 24.28 | 13.79 | 82.99 | 84 | 119 |
| Current 3.5R | 2025-04-01 to 2026-03-24 | 500 | 250 | 68.63 | 0 | 31.37 | 83.16 | 79.50 | 152 |
| Reduced 2R | 2016-01-01 to 2026-03-24 | 500 | 250 | 60.69 | 36.14 | 3.17 | 104 | 90 | 108 |
| Reduced 2R | 2016-01-01 to 2025-03-31 | 500 | 250 | 59.49 | 36.20 | 4.31 | 105 | 90 | 111 |
| Reduced 2R | 2024-01-01 to 2026-03-24 | 500 | 250 | 53.88 | 31.61 | 14.51 | 90.76 | 86 | 62.07 |
| Reduced 2R | 2025-04-01 to 2026-03-24 | 500 | 250 | 66.99 | 0 | 33.01 | 91.27 | 91 | 75.55 |

## Pre-Holdout Best Risk

| target | risk_pre_usd | risk_post_usd | payout_rate | breach_rate | avg_days_to_payout | median_days_to_payout | ev_per_start_usd | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Current 3.5R | 600 | 300 | 61.54 | 34.53 | 74.67 | 71 | 220 | 12.67 |
| Reduced 2R | 600 | 300 | 59.87 | 35.99 | 79.95 | 71.50 | 154 | 8.57 |

## Holdout With Frozen Risk

| target | risk_pre_usd | risk_post_usd | payout_rate | breach_rate | open_rate | avg_days_to_payout | median_days_to_payout | ev_per_start_usd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Current 3.5R | 600 | 300 | 68.95 | 0 | 31.05 | 70.57 | 65 | 258 |
| Reduced 2R | 600 | 300 | 68.63 | 0 | 31.37 | 72.69 | 68.50 | 129 |

## Notes

- The fixed funded table answers the straightforward question: what happens if you trade each target with the current house risk profile.
- The frozen-risk holdout table is the cleaner operational read: each target gets one pre-holdout risk choice, then we see how that risk policy survives out of sample.