# ALPHA_V1 ES NY ATH Exact Replay - 2026-05-05

## Scope

Exact replay of ES NY only from 2016-04-17 through 2026-03-24, using `ALPHA_V1-A` ES NY settings and an in-memory ATH gate profile.

Gate tested: block new ES NY ORB entries when the closed signal bar is 0.5-1.0% below the expanding ES futures ATH.

Deployability fields:
- `deployability`: post_filter_only
- `live_support_notes`: ORBEngine supports causal `ath_block_min_pct/max_pct`; production live still needs a trusted historical ATH seed source before this becomes `live_native`.
- `exact_replay_required`: complete for this ES NY exact replay pass

## Exact Replay Summary

| window | baseline_trades | gated_trades | trade_delta | baseline_total_r | gated_total_r | delta_r | baseline_pnl_usd | gated_pnl_usd | delta_pnl_usd | baseline_max_dd_r | gated_max_dd_r | baseline_win_rate_pct | gated_win_rate_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | 849 | 774 | -75 | 145.803 | 155.011 | 9.208 | 47534.68 | 50703.38 | 3168.7 | -12.0 | -12.0 | 55.8 | 56.7 |
| 2024+ | 201 | 172 | -29 | 34.424 | 42.924 | 8.5 | 12306.4 | 15287.98 | 2981.58 | -9.0 | -7.5 | 53.2 | 55.2 |
| 2025+ | 111 | 98 | -13 | 18.041 | 27.541 | 9.5 | 7136.38 | 10417.96 | 3281.58 | -9.0 | -7.5 | 54.1 | 57.1 |

## Funded First-Payout Simulation

| profile | window | accounts | payouts | breaches | open | payout_rate_pct | breach_rate_pct | ev_per_account_usd | median_days_to_payout | median_trades_to_payout | max_consecutive_breaches |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1_ES_NY_BASELINE_EXACT | full | 260 | 169 | 85 | 6 | 65.0 | 32.69230769230769 | 175.0 | 103.0 | 25.0 | 25 |
| ALPHA_V1_ES_NY_BASELINE_EXACT | 2024+ | 59 | 44 | 9 | 6 | 74.57627118644068 | 15.254237288135593 | 222.88135593220338 | 101.0 | 25.0 | 5 |
| ALPHA_V1_ES_NY_BASELINE_EXACT | 2025+ | 32 | 19 | 8 | 5 | 59.375 | 25.0 | 146.875 | 96.0 | 25.0 | 4 |
| ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | full | 260 | 157 | 97 | 6 | 60.38461538461538 | 37.30769230769231 | 151.92307692307693 | 96.0 | 19.0 | 25 |
| ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | 2024+ | 59 | 50 | 3 | 6 | 84.7457627118644 | 5.084745762711865 | 273.728813559322 | 109.0 | 21.0 | 3 |
| ALPHA_V1_ES_NY_ATH_0P5_1_EXACT | 2025+ | 32 | 24 | 3 | 5 | 75.0 | 9.375 | 225.0 | 93.0 | 17.0 | 3 |

## Trade Replacement Check

- Baseline trades removed by gate: 95
- New later trades admitted after skipped setups: 20

## Interpretation

This is the first causal execution-engine pass for the ES NY ATH dead-zone thesis. The gate is no longer just a post-hoc filter: it blocks before the order is armed and keeps scanning for later valid FVGs in the same entry window.

Decision read: exact replay confirms the trade-level edge and recent payout benefit, but not broad full-history account-flow promotion. Full-history net improves by +9.2R, while full-history first-payout quality worsens from 65.0% payout / 32.7% breach to 60.4% payout / 37.3% breach. The 2024+ and 2025+ cohorts improve materially, so this belongs in a recent-flow / separate-account research lane rather than the default ALPHA_V1 production sleeve.

Next research step: run rolling split diagnostics and nearby band sensitivity (`0.25-0.75%`, `0.5-0.75%`, `0.75-1.0%`, `0.5-1.25%`) in exact replay before any dry-run proposal, then wire a production ATH seed source if the candidate survives.
