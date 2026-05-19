# ALPHA_V1 Hunter Cap-Fix Rerun (2026-05-17)

- Generated: `2026-05-16T19:19:41`
- Results packet: `backtesting/data/results/alpha_v1_hunter_cap_fix_20260517`
- Repro script: `backtesting/scripts/run_alpha_v1_hunter_cap_fix_20260517.py`
- Runtime: `0.2s`
- Hunter exact latest NQ end: `2026-05-01`

## Scope

Patched `HunterORBEngine._hunter_qty_for_risk()` so the Hunter path now follows the same `max_single_risk_usd` rule as standard ORB sizing: if one MNQ would exceed the configured single-contract cap, the setup is skipped instead of forced to `1` MNQ.

## Exact Replay Before / After

| Stream | Trades | Net | DD | PF | Net R | DD R | WR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| old_floor_hunter_025 | 1660 | $4,726 | $-4,016 | 1.06 | 73.7 | -54.5 | 39.8% |
| cap_fixed_hunter_025 | 1384 | $2,971 | $-4,078 | 1.05 | 51.0 | -54.9 | 37.4% |

Old floor behavior had `303` trades with effective risk above `$87.50`. Cap-fixed replay has `0` such trades. Same-setup old/new match count: `1357`.

## Research Parity After Cap Fix

| Stream | Trades | Net | DD | PF | Net R | DD R | WR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| live_engine_exact_shadow_025 | 1378 | $3,195 | $-4,078 | 1.05 | 54.3 | -54.9 | 37.5% |
| research_selected_10y_safe | 1650 | $20,654 | $-3,360 | 1.15 | 236 | -38.4 | 39.9% |
| fuzzy_same_setup_match | 529 | $0 | $0 | 0.00 | 0.0 | 0.0 | 32.1% |

Research parity match after cap fix: `529` matched, `849` exact-only, `1121` research-only.

## Sidecar Portfolio Fit

| Scenario | Net | Delta | DD | Worst Month | Sharpe |
| --- | --- | --- | --- | --- | --- |
| ALPHA_V1 cached fee-aware | $53,825 | $0 | $-4,037 | $-2,469 | 2.04 |
| ALPHA_V1 + old floor Hunter 0.25x | $59,797 | $5,972 | $-3,699 | $-2,915 | 2.19 |
| ALPHA_V1 + cap-fixed Hunter 0.25x | $58,881 | $5,056 | $-3,889 | $-2,469 | 2.18 |

## Sidecar Account Outcomes

| Scenario | Year | Payout | Breach | Avg PayD | MCBch | EV/Start |
| --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1 cached fee-aware | 2024 | 82.6% | 17.4% | 40.6 | 2 | $202 |
| ALPHA_V1 cached fee-aware | 2025 | 73.1% | 26.9% | 20.5 | 7 | $202 |
| ALPHA_V1 cached fee-aware | 2026_YTD | 100.0% | 0.0% | 39.3 | 0 | $100 |
| ALPHA_V1 + old floor Hunter 0.25x | 2024 | 80.0% | 20.0% | 36.9 | 2 | $220 |
| ALPHA_V1 + old floor Hunter 0.25x | 2025 | 84.6% | 15.4% | 23.2 | 4 | $257 |
| ALPHA_V1 + old floor Hunter 0.25x | 2026_YTD | 100.0% | 0.0% | 30.3 | 0 | $100 |
| ALPHA_V1 + cap-fixed Hunter 0.25x | 2024 | 87.5% | 12.5% | 38.0 | 2 | $239 |
| ALPHA_V1 + cap-fixed Hunter 0.25x | 2025 | 84.6% | 15.4% | 23.0 | 4 | $257 |
| ALPHA_V1 + cap-fixed Hunter 0.25x | 2026_YTD | 100.0% | 0.0% | 33.0 | 0 | $100 |

## Read

- The sizing patch removes the silent over-risking from Hunter `0.25x`: over-cap trades dropped from `303` to `0`.
- Standalone Hunter got smaller (`+$4.7k` old floor replay to `+$3.0k` cap-fixed replay), but the sidecar stayed additive in the current fee-aware ALPHA context.
- Account fit is cleaner after the cap fix: 2024 improved from baseline `82.6% / 17.4%` payout/breach to `87.5% / 12.5%`, and 2025 improved from `73.1% / 26.9%` to `84.6% / 15.4%`.
- Actionable read: keep cap-fixed Hunter as the cleaner no-webhook shadow candidate, but do not promote webhooks until the research/live signal-stream mismatch is explained.

