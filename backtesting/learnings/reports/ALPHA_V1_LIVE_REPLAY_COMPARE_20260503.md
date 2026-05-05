# ALPHA_V1 Research vs Live-Engine Exact Replay

- Profile replayed: `ALPHA_V1-A` from `execution/config/exec_configs.json`.
- Exact replay path: `execution/src/trader/historical_backtest.py` via `run_profile_backtest_sync`.
- Full window: `2016-04-17` to `2026-03-24`.
- Last-1y hot window: `2025-03-24` to `2026-03-24`.
- Research baseline source: `backtesting/data/results/alpha_v1_orb_reentry_promotion_20260502/*_window_metrics.csv`, which is linked from `backtesting/learnings/ALPHA_V1.md` as the active four-leg promotion packet baseline.
- Note: exact replay exports filled trades only; research rows include signal/fill counts, so this report compares research fills to exact filled trades.

## Side-by-Side

| Window | Leg | Research fills | Exact fills | d fills | Research R | Exact R | d R | Research WR | Exact WR | Research PF | Exact PF | Research DD | Exact DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full | NQ NY HTF-LSI | 481 | 374 | -107 | 92.58 | 70.23 | -22.35 | 52.81% | 52.94% | 1.450 | 1.458 | -10.94R | -10.77R |
| full | NQ Asia ORB | 722 | 640 | -82 | 213.50 | 167.42 | -46.08 | 45.71% | 44.38% | 1.560 | 1.528 | -10.16R | -8.32R |
| full | ES Asia ORB | 1422 | 1116 | -306 | 145.85 | 136.68 | -9.17 | 54.43% | 54.93% | 1.290 | 1.287 | -12.28R | -12.23R |
| full | ES NY ORB | 845 | 506 | -339 | 127.58 | 71.13 | -56.45 | 61.07% | 55.34% | 1.390 | 1.330 | -10.86R | -12.00R |
| full | Combined ALPHA_V1 | 3470 | 2636 | -834 | 579.51 | 445.45 | -134.06 | 54.01% | 52.16% | 1.410 | 1.376 | -14.47R | -14.89R |
| last_1y | NQ NY HTF-LSI | 39 | 34 | -5 | 14.11 | 16.53 | 2.42 | 61.54% | 64.71% | 1.960 | 2.567 | -3.00R | -3.00R |
| last_1y | NQ Asia ORB | 73 | 66 | -7 | 36.31 | 35.39 | -0.92 | 50.68% | 51.52% | 2.030 | 2.140 | -6.00R | -5.00R |
| last_1y | ES Asia ORB | 143 | 118 | -25 | 21.75 | 16.95 | -4.80 | 57.34% | 55.93% | 1.420 | 1.349 | -5.82R | -5.10R |
| last_1y | ES NY ORB | 92 | 57 | -35 | 19.20 | 18.88 | -0.32 | 67.39% | 61.40% | 1.640 | 1.996 | -9.61R | -6.00R |
| last_1y | Combined ALPHA_V1 | 347 | 275 | -72 | 91.38 | 87.74 | -3.64 | 59.08% | 57.09% | 1.690 | 1.852 | -10.93R | -9.45R |

## Config Parity

| Leg | Key | Research | Execution |
| --- | --- | --- | --- |
| NQ Asia ORB | `flat_end` | `04:00` | `04:10` |
| ES Asia ORB | `flat_end` | `07:00` | `07:10` |

## Risk Sizing Drift

| Leg | Research reference | Execution `ALPHA_V1-A` |
| --- | ---: | ---: |
| NQ NY HTF-LSI | $300 | $400 |
| NQ Asia ORB | $300 | $250 |
| ES Asia ORB | $200 | $250 |
| ES NY ORB | $300 | $400 |

R-level metrics are still compared, but contract sizing can matter if live portfolio caps bind.

## Interpretation

- Divergence is primarily live state-machine semantics and fill/order lifecycle: exact replay uses the production ORB/LSI engines, tick-order fills while armed/managing, real pending-order state, and portfolio contract caps.
- No ALPHA_V1 active leg currently has an NQ-anchored regime gate in `ALPHA_V1-A`; the NQ daily-history caveat remains important for gated non-NQ profiles, but it was not a driver in this pass.
- The current exact replay is a combined-profile replay, not separate-account isolation. That matches the available execution profile, but differs from the ALPHA portfolio thesis where legs are intended to run on separate funded accounts.
- The live replay can therefore diverge from research even when the visible knobs match, especially around limit-order retests, TP/SL ordering, cancellations, flat handling, and any position-cap interaction.

## ALPHA_V1 Active-Section Metric Drift

The top active-leg tables in `ALPHA_V1.md` use mixed historical windows/vintages. The same-document promotion packet baseline over `2016-04-17` to `2026-03-24` is the research source used above. For awareness, the active-section full-history metrics differ from that packet for several legs:

| Leg | Active-section fills/R | Packet baseline fills/R |
| --- | ---: | ---: |
| NQ NY HTF-LSI | 493 / 86.60R | 481 / 92.58R |
| NQ Asia ORB | 753 / 212.00R | 722 / 213.50R |
| ES Asia ORB | 1454 / 183.30R | 1422 / 145.85R |
| ES NY ORB | 866 / 142.80R | 845 / 127.58R |

## Artifacts

- JSON payload: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/alpha_v1_live_replay_compare_20260503/alpha_v1_live_replay_compare.json`
- Exact trades CSV: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/alpha_v1_live_replay_compare_20260503/exact_trades.csv`
- Metrics CSV: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/alpha_v1_live_replay_compare_20260503/comparison_metrics.csv`
