# NQ NY LSI Orderflow Side-Branch Provider Validation

- Date: 2026-05-17
- Scope: no-fetch execution-facing provider validation for the champion and two side branches.
- DataBento fetches: `0`
- Profile: `tier_0p5_1_1p5`
- Status: `pass`

## Provider Match

- Rows checked: `293`
- Tier mismatches: `0`
- Weight mismatches: `0`
- Weighted-R mismatches: `0`

## Period Read

| Track | Period | Trades | Baseline R | Weighted R | Delta R | Weighted Avg | PF | Max DD | Exact Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `pure_1m_velocity_champion` | `validation` | 33 | 10.55R | 11.63R | +1.08R | 0.353R | 2.29 | -2.75R | exact shadow pass: +9.25R vs +5.50R baseline, 0 fallbacks |
| `pure_1m_velocity_champion` | `holdout` | 21 | 4.84R | 8.33R | +3.49R | 0.397R | 2.28 | -1.50R | exact shadow pass: +9.25R vs +5.50R baseline, 0 fallbacks |
| `pure_1m_liquidity_vacuum_side_branch` | `validation` | 33 | 10.55R | 12.31R | +1.76R | 0.373R | 2.30 | -2.72R | scored exact shadow pass: +7.25R vs +5.50R baseline, 0 fallbacks |
| `pure_1m_liquidity_vacuum_side_branch` | `holdout` | 21 | 4.84R | 7.02R | +2.18R | 0.334R | 2.17 | -2.25R | scored exact shadow pass: +7.25R vs +5.50R baseline, 0 fallbacks |
| `three_minute_trapped_reversal_side_branch` | `validation` | 139 | 9.43R | 20.93R | +11.49R | 0.151R | 1.35 | -5.00R | research/stress pass only; execution-engine parity not implemented |
| `three_minute_trapped_reversal_side_branch` | `holdout` | 46 | 12.17R | 17.34R | +5.17R | 0.377R | 2.00 | -5.67R | research/stress pass only; execution-engine parity not implemented |

## Interpretation

- Pure 1m velocity remains the shadow champion because it has live-engine exact shadow support and the best exact weighted R.
- Pure 1m liquidity-vacuum has now cleared scored exact-shadow replay, but still needs a live-native MBP-10 depth/microprice calculator before it can shadow from streaming data.
- 3m trapped-reversal remains research-only. The provider bridge can reproduce its frozen tiers, but execution parity for the 3m candidate and a live/replay feature calculator are still required.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_lsi_orderflow_side_branch_provider_validation_20260517/validated_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_lsi_orderflow_side_branch_provider_validation_20260517/period_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_lsi_orderflow_side_branch_provider_validation_20260517/summary.json`
