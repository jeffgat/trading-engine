# NQ NY LSI Pure 1m Order-Book Velocity Minimum Implementation Validation

- Date: 2026-05-16
- Scope: no-fetch implementation validation using the existing frozen replay CSV.
- Candidate: `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`
- Feature: `confirm_last_10s_mid_velocity_ticks_per_second`
- Profile: `tier_0p5_1_1p5`
- DataBento fetches: `0`
- Historical days required: `0`
- Status: `pass`

## What Was Validated

The execution-facing `ScoredFeatureLookupProvider` was run against the existing scored replay rows and routed through the same `DynamicSizingContext` / `DynamicSizingDecision` interface that the live LSI engine now accepts. This proves the frozen thresholds and risk weights are reproducible in implementation code without a new historical MBP-10 fetch.

Frozen rule:

- Low: feature `< -0.322`, weight `0.5x`
- Mid: feature `[-0.322, 0.912)`, weight `1.0x`
- High: feature `>= 0.912`, weight `1.5x`

## Replay Match

- Rows checked: `54`
- Unique trade dates: `54`
- Unique trade IDs: `54`
- Tier mismatches: `0`
- Weight mismatches: `0`
- Weighted-R mismatches: `0`

## Period Metrics

| Period | Trades | Dates | Baseline R | Weighted R | Delta R | Weighted Avg R | Weighted PF | Weighted Max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| holdout | 21 | 21 | 4.84R | 8.33R | +3.49R | 0.397R | 2.28 | -1.50R |
| validation | 33 | 33 | 10.55R | 11.63R | +1.08R | 0.353R | 2.29 | -2.75R |

## Tier Metrics

| Period | Tier | Weight | Trades | Feature Range | Weighted R | Avg R | PF |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| holdout | `high` | 1.5 | 11 | 0.950 to 3.000 | 9.62R | 0.874R | 4.21 |
| holdout | `low` | 0.5 | 6 | -2.950 to -0.700 | -0.29R | -0.048R | 0.81 |
| holdout | `mid` | 1.0 | 4 | -0.250 to 0.900 | -1.00R | -0.250R | 0.50 |
| validation | `high` | 1.5 | 11 | 1.000 to 8.700 | 8.40R | 0.763R | 3.80 |
| validation | `low` | 0.5 | 11 | -3.750 to -0.350 | 1.71R | 0.156R | 1.86 |
| validation | `mid` | 1.0 | 11 | -0.300 to 0.900 | 1.52R | 0.138R | 1.38 |

## Interpretation

- This is the minimum implementation validation: no historical MBP-10 fetch and no broker order placement.
- The sizing provider bridge exactly reproduces the frozen replay tiers and weighted R, so the live engine can consume the same decision interface behind disabled-by-default config flags.
- The live MBP-10 path now has a cost acknowledgement guard and shadow mode available for paper validation before any quantity changes are applied.
- Promotion is still blocked until MBP-10 is enabled in a paper/live validation run and exact execution-engine replay/paper parity exists.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_min_impl_validation_20260516/validated_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_min_impl_validation_20260516/period_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_min_impl_validation_20260516/tier_metrics.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_min_impl_validation_20260516/summary.json`