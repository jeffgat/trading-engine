# ALPHA_V1 ORB Payout-Optimized Risk Compare

- Scope: the three ORB legs from `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`).
- Comparison:
  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.
  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.
- Important: the earlier R-based prop table cannot respond to dollar risk changes. This rerun uses the funded first-payout USD model instead.
- Funded model: `$50k` start, `$2k` trailing EOD DD capped at `$50k`, first payout floor `$52.5k`, challenge fee `$100`.
- Risk sweep: `risk_pre_payout_usd` in `200..600` by `50`, with `risk_post_payout_usd = max(100, risk_pre / 2)`.
- Best-risk selection rule copied from the existing portfolio first-payout sweep: maximize payout-heavy rank score with breach and time-to-payout penalties.

## Chosen Risk Settings

| rules | risk_pre_usd | risk_post_usd | payout_rate | breach_rate | avg_days_to_payout | ev_per_start_usd | rank_score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Current single-trade legs | 200 | 100 | 82.64 | 14.97 | 78.16 | 98.59 | 39.69 |
| Optimized rules | 200 | 100 | 86.49 | 12.67 | 70.71 | 96.46 | 47.86 |

## Comparison Table

| period | window | rules | max_dd_r | net_r | payouts | breaches | payout_rate | breach_rate | resolved_payout_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Last 10y available | 2016-04-17 to 2026-03-24 | Current single-trade legs | -21.18 | 360 | 2556 | 463 | 82.64 | 14.97 | 84.66 |
| Last 10y available | 2016-04-17 to 2026-03-24 | Optimized rules | -21.38 | 440 | 2675 | 392 | 86.49 | 12.67 | 87.22 |
| 2024 | 2024-01-01 to 2024-12-31 | Current single-trade legs | -9.52 | 27.57 | 213 | 0 | 68.05 | 0 | 100 |
| 2024 | 2024-01-01 to 2024-12-31 | Optimized rules | -10.54 | 48.41 | 226 | 0 | 72.20 | 0 | 100 |
| 2025 | 2025-01-01 to 2025-12-31 | Current single-trade legs | -9.88 | 58.10 | 245 | 52 | 78.53 | 16.67 | 82.49 |
| 2025 | 2025-01-01 to 2025-12-31 | Optimized rules | -11.31 | 62.15 | 242 | 53 | 77.56 | 16.99 | 82.03 |
| 2026 YTD | 2026-01-01 to 2026-03-24 | Current single-trade legs | -8.06 | 10.40 | 1 | 0 | 1.41 | 0 | 100 |
| 2026 YTD | 2026-01-01 to 2026-03-24 | Optimized rules | -11.94 | 14.53 | 13 | 32 | 18.31 | 45.07 | 28.89 |

## Notes

- `max_dd_r` and `net_r` stay in R-space, so they are unchanged from the earlier comparison.
- The funded-account payout/breach counts and rates are the fields that actually change when risk sizing changes.