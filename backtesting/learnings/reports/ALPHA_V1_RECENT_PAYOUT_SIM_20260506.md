# ALPHA_V1 Recent Payout Simulation

- Run slug: `alpha_v1_recent_payout_sim_20260506`
- Windows: `2024`, `2025`, and partial `2026_YTD` through `2026-03-24`.
- Account model: `$50k` account, `$2k` EOD trailing DD capped at `$50k`, payout trigger `$52.5k`, first payout `$500`, account cost `$150`, starts every `14` calendar days.
- Payout and breach percentages below are **resolved-account rates** (`payouts / payouts+breaches`) so open year-end accounts do not distort partial 2026. Open rate is shown separately.

## Trade Stream

| Leg | Trades | Net R | 2024 R | 2025 R | 2026 R | Source |
| --- | --- | --- | --- | --- | --- | --- |
| NQ NY HTF-LSI | 374 | 70.2 | 8.90 | 16.5 | 0.60 | alpha_v1_live_exact_4leg |
| NQ Asia ORB | 640 | 167 | 19.4 | 35.4 | 6.80 | alpha_v1_live_exact_4leg |
| ES Asia ORB | 1116 | 137 | 15.3 | 23.5 | 3.10 | alpha_v1_live_exact_4leg |
| NQ NY ORB R11 | 554 | 148 | 9.30 | 11.6 | -0.80 | nq_r11_exact_split |
| ES NY ORB | 506 | 71.1 | 2.90 | 16.4 | -1.00 | alpha_v1_live_exact_4leg |

## Proposed ALPHA Menus

| Profile | Year | Accts | Pay | Breach | Open | Res Pay% | Res Br% | Open% | Avg PayD | Med PayD | EV/start | MCBch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Probation / lowest breach | 2024 | 27 | 21 | 2 | 4 | 91.3 | 8.70 | 14.8 | 54.9 | 59.0 | 239 | 2 |
| Probation / lowest breach | 2025 | 27 | 22 | 3 | 2 | 88.0 | 12.0 | 7.40 | 44.8 | 31.0 | 257 | 3 |
| Probation / lowest breach | 2026_YTD | 6 | 2 | 0 | 4 | 100 | 0.00 | 66.7 | 32.0 | 32.0 | 17.0 | 0 |
| Balanced default | 2024 | 27 | 19 | 4 | 4 | 82.6 | 17.4 | 14.8 | 47.2 | 47.0 | 202 | 2 |
| Balanced default | 2025 | 27 | 22 | 4 | 1 | 84.6 | 15.4 | 3.70 | 27.7 | 23.0 | 257 | 4 |
| Balanced default | 2026_YTD | 6 | 2 | 3 | 1 | 40.0 | 60.0 | 16.7 | 27.5 | 27.5 | 17.0 | 3 |
| NQ-led sprint | 2024 | 27 | 17 | 6 | 4 | 73.9 | 26.1 | 14.8 | 39.3 | 43.0 | 165 | 3 |
| NQ-led sprint | 2025 | 27 | 23 | 3 | 1 | 88.5 | 11.5 | 3.70 | 24.1 | 21.0 | 276 | 3 |
| NQ-led sprint | 2026_YTD | 6 | 2 | 3 | 1 | 40.0 | 60.0 | 16.7 | 27.5 | 27.5 | 17.0 | 3 |

## Top Fast-Enough Grid Rows

Rows are ranked on 2024-2025 because 2026 is partial. `Avg PayD` and `Max PayD` must stay under `90d` to be considered fast enough.

| HTF | NQ Asia | ES Asia | R11 | ES NY | Avg PayD | Max PayD | Avg Res Pay% | Avg Res Br% | MCBch | EV/start |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 300 | 300 | 150 | 150 | 100 | 52.0 | 56.7 | 95.7 | 4.30 | 2 | 276 |
| 300 | 250 | 200 | 150 | 100 | 53.3 | 57.8 | 95.7 | 4.30 | 2 | 276 |
| 300 | 250 | 150 | 150 | 100 | 57.9 | 59.9 | 95.7 | 4.30 | 2 | 276 |
| 300 | 250 | 150 | 150 | 150 | 57.8 | 60.4 | 95.5 | 4.50 | 2 | 267 |
| 300 | 250 | 150 | 350 | 150 | 41.8 | 48.7 | 89.5 | 10.5 | 2 | 248 |
| 300 | 300 | 150 | 300 | 200 | 40.7 | 49.8 | 89.9 | 10.1 | 3 | 257 |
| 300 | 300 | 150 | 250 | 200 | 41.3 | 50.4 | 89.9 | 10.1 | 3 | 257 |
| 300 | 300 | 150 | 200 | 200 | 44.2 | 51.6 | 89.9 | 10.1 | 3 | 257 |
| 300 | 250 | 200 | 200 | 200 | 45.5 | 51.4 | 89.9 | 10.1 | 3 | 257 |
| 300 | 250 | 150 | 250 | 200 | 46.6 | 53.0 | 89.9 | 10.1 | 3 | 257 |
| 300 | 300 | 150 | 250 | 150 | 42.5 | 51.5 | 89.7 | 10.3 | 3 | 248 |
| 300 | 300 | 150 | 200 | 150 | 43.2 | 54.4 | 89.7 | 10.3 | 3 | 248 |

## Read

- Payout speed is **not** the blocker. All three proposed menus are under the desired `2-3 month` average on resolved 2024-2025 payouts.
- The blocker is breach clustering when NY ORB risk is raised. The `Balanced default` is fast (`47d` in 2024, `28d` in 2025), but partial `2026_YTD` resolved at only `2` payouts / `3` breaches / `1` open.
- The safest fast row is `HTF $300 / NQ Asia $300 / ES Asia $150 / R11 $150 / ES NY $100`: average 2024-2025 payout time `52d`, resolved payout `95.7%`, resolved breach `4.3%`, max consecutive breaches `2`, and `2026_YTD` had `2` payouts / `0` breaches / `4` open.
- A more aggressive but still reasonable sprint row is `HTF $300 / NQ Asia $300 / ES Asia $150 / R11 $250 / ES NY $200`: average 2024-2025 payout time `41d`, resolved payout `89.9%`, resolved breach `10.1%`, max consecutive breaches `3`, but partial `2026_YTD` already shows NY-sleeve stress.
- 2026 is too short to finalize sizing; many accounts are still open. Use it as a live-flow sanity check, not a full-year verdict.

## Artifacts

- `trade_stream.csv`
- `trade_summary.csv`
- `static_profile_year_summary.csv`
- `static_profile_account_outcomes.csv`
- `risk_sweep_ranked.csv`
- `summary.json`
