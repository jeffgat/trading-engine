# ALPHA_V1 Stop/Target Candidate Live-Engine Replay

- Run slug: `alpha_v1_stop_target_live_engine_replay_20260504`
- Result directory: `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/alpha_v1_stop_target_live_engine_replay_20260504`
- Window: `2016-04-17` to `2026-03-24`
- Engine path: `execution/src/trader/historical_backtest.py` using live `ORBEngine` profiles created in memory.
- Base profile for active ALPHA legs: `ALPHA_V1-A`. No live execution config file was edited.
- Ranking lens: last 1y first, then last 2y, then full available history.

## Ranked Exact Replay Results

| Rank | Candidate | Stop | rr | tp1 | TP1_R | Last 1y Trades | Last 1y R | Last 1y WR | Last 2y R | Full Trades | Full R | Full WR | Full PF | Full DD | Deployability |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | ES Asia ORB | ORB 50% | 2.00 | 0.75 | 1.50 | 143 | 37.25 | 49.65% | 53.04 | 1429 | 209.88 | 47.17% | 1.288 | -16.25 | live_native |
| 2 | NQ Asia ORB | ORB 125% | 2.50 | 0.60 | 1.50 | 73 | 32.39 | 56.16% | 50.13 | 725 | 166.57 | 49.66% | 1.495 | -13.34 | live_native |
| 3 | ES Asia-B ungated | ATR 12% | 2.00 | 0.75 | 1.50 | 83 | 21.55 | 54.22% | 40.57 | 911 | 112.39 | 48.30% | 1.280 | -11.95 | live_native |
| 4 | NQ NY ORB R11 | ATR 7% | 3.00 | 0.50 | 1.50 | 49 | 7.50 | 44.90% | 25.83 | 554 | 139.21 | 49.64% | 1.495 | -8.25 | live_native |
| 5 | ES NY ORB | ORB 50% | 3.00 | 0.50 | 1.50 | 93 | 8.40 | 43.01% | 19.17 | 849 | 89.41 | 43.70% | 1.192 | -14.75 | live_native |

## Blocked / Not Replayed

| Candidate | Requested Structure | Reason | Exact Replay Required |
| --- | --- | --- | --- |
| NQ CISD additive noThu | ATR 10%, rr=2.5, tp1=0.4, TP1_R=1.0 | Blocked for exact live replay: the current execution engine does not expose the research CISD/additive confirmation fields required by this branch. It should not be approximated with legacy LSI or plain ORB replay. | yes_after_live_engine_parity |

## Notes

- Rows are single-candidate exact replays. They are not a combined portfolio because `ES Asia ORB` and `ES Asia-B ungated` both occupy the `ES_Asia` execution session key and are alternative definitions.
- The live engine path can replay standard ORB continuation stop/target variants directly. The CISD additive branch needs execution-engine parity before it can be exact-replayed or deployed.
