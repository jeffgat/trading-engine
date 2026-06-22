# Cross-Asset ORB Non-Reject Exact Replay

## Summary

Ran `ORB_NONREJECT_ADVANCEMENT_20260612` through the execution-engine exact replay for discovery `2021-01-01`-`2024-12-31` and holdout `2025-01-01`-`2026-03-27`.

- Exact replay pass: `4`
- Exact replay watch: `9`
- Exact replay fail: `10`

## Pass

| Rank | Cand | Rule | Status | Research R | Exact R | Exact PF | Exact DD | HO R | HO PF | Delta R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | ORB03_ES_NY | es__ny__rr1p0__both__no_wed | EXACT_REPLAY_PASS | 47.75 | 49.74 | 1.14 | -12.91 | 6.19 | 1.01 | 2.00 |
| 6 | ORB06_NQ_NY | nq__ny__rr1p5__long__no_fri__small_orb_only | EXACT_REPLAY_PASS | 29.79 | 31.90 | 1.66 | -6.01 | 4.00 | 1.18 | 2.11 |
| 10 | ORB10_ES_ASIA | es__asia__rr2p0__long__no_mon__small_or_mid_orb | EXACT_REPLAY_PASS | 31.75 | 18.13 | 1.59 | -4.04 | 1.11 | 1.05 | -13.62 |
| 12 | ORB12_GC_ASIA | gc__asia__rr2p0__long__no_wed__low_atr_only | EXACT_REPLAY_PASS | 30.01 | 28.01 | 1.40 | -5.00 | 1.00 | 1.24 | -2.00 |

## Watch

| Rank | Cand | Rule | Status | Research R | Exact R | Exact PF | Exact DD | HO R | HO PF | Delta R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ORB01_RTY_NY | rty__ny__rr1p0__both__no_thu__low_or_mid_atr | EXACT_REPLAY_WATCH | 50.00 | 37.00 | 1.09 | -12.00 | 2.92 | 0.92 | -13.00 |
| 2 | ORB02_SI_NY | si__ny__rr1p0__both__no_tue__small_or_mid_orb | EXACT_REPLAY_WATCH | 33.04 | 34.03 | 1.22 | -10.47 | -4.42 | 0.91 | 0.99 |
| 4 | ORB04_SI_NY | si__ny__rr1p0__both__no_tue__low_or_mid_atr | EXACT_REPLAY_WATCH | 36.81 | 8.00 | 1.19 | -6.00 | -1.00 | 0.89 | -28.81 |
| 14 | ORB14_YM_NY | ym__ny__rr1p5__short__no_tue | EXACT_REPLAY_WATCH | 28.04 | 14.27 | 1.09 | -10.00 | -6.91 | 0.87 | -13.77 |
| 15 | ORB15_RTY_NY | rty__ny__rr2p0__both__none__small_or_mid_orb | EXACT_REPLAY_WATCH | 52.84 | 38.45 | 1.26 | -7.17 | -10.13 | 0.72 | -14.39 |
| 17 | ORB17_GC_NY | gc__ny__rr1p25__long__no_mon__low_atr_only__small_orb_only | EXACT_REPLAY_WATCH | 25.97 | 22.89 | 2.81 | -2.00 | 1.25 | 0.00 | -3.08 |
| 21 | ORB21_SI_LDN | si__ldn__rr1p0__long__no_thu__low_atr_only__small_orb_only | EXACT_REPLAY_WATCH | 18.73 | 5.91 | 1.31 | -8.00 | -1.00 | 0.80 | -12.83 |
| 22 | ORB22_GC_ASIA | gc__asia__rr2p0__long__no_mon__low_or_mid_atr__small_orb_only | EXACT_REPLAY_WATCH | 20.45 | 7.35 | 1.60 | -4.00 | -1.00 | 0.63 | -13.10 |
| 23 | ORB23_ES_LDN | es__ldn__rr1p0__both__no_thu__low_atr_only__small_orb_only | EXACT_REPLAY_WATCH | 18.51 | 15.81 | 1.48 | -3.00 | -4.34 | 0.53 | -2.69 |

## Fail

| Rank | Cand | Rule | Status | Research R | Exact R | Exact PF | Exact DD | HO R | HO PF | Delta R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | ORB05_SI_NY | si__ny__rr1p0__long__no_tue | EXACT_REPLAY_FAIL | 33.74 | -5.94 | 0.72 | -7.00 | 7.00 | 1.65 | -39.68 |
| 7 | ORB07_NQ_NY | nq__ny__rr1p5__long__none__small_orb_only | EXACT_REPLAY_FAIL | 29.79 | -1.00 | 0.90 | -7.00 | 0.00 | 0.97 | -30.79 |
| 8 | ORB08_ES_NY | es__ny__rr1p0__short__no_wed | EXACT_REPLAY_FAIL | 23.67 | 4.00 | 1.65 | -2.00 | 2.00 | 2.84 | -19.67 |
| 9 | ORB09_ES_NY | es__ny__rr1p25__short__no_wed | EXACT_REPLAY_FAIL | 25.92 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | -25.92 |
| 11 | ORB11_ES_ASIA | es__asia__rr2p0__long__no_mon__low_or_mid_atr__small_or_mid_orb | EXACT_REPLAY_FAIL | 27.46 | -1.00 | 0.00 | 0.00 | 0.00 | 0.00 | -28.46 |
| 13 | ORB13_NQ_NY | nq__ny__rr1p25__long__no_fri__small_orb_only | EXACT_REPLAY_FAIL | 30.51 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | -30.51 |
| 16 | ORB16_RTY_NY | rty__ny__rr1p5__long__no_thu__low_or_mid_atr | EXACT_REPLAY_FAIL | 45.16 | -0.50 | 0.66 | -2.00 | 0.00 | 0.00 | -45.66 |
| 18 | ORB18_GC_NY | gc__ny__rr1p25__long__no_thu__low_atr_only__small_orb_only | EXACT_REPLAY_FAIL | 19.72 | -3.71 | 0.38 | -5.64 | 1.25 | 0.00 | -23.43 |
| 19 | ORB19_GC_ASIA | gc__asia__rr2p0__long__no_wed__low_atr_only__small_or_mid_orb | EXACT_REPLAY_FAIL | 28.01 | -2.00 | 0.00 | -1.00 | 0.00 | 0.00 | -30.01 |
| 20 | ORB20_GC_NY | gc__ny__rr1p25__long__none__low_atr_only__small_orb_only | EXACT_REPLAY_FAIL | 20.72 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | -20.72 |

## Artifacts

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/cross_asset_orb_nonreject_advancement_20260612/exact_replay_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/cross_asset_orb_nonreject_advancement_20260612/exact_replay_payload.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/cross_asset_orb_nonreject_advancement_20260612/exact_replay_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/cross_asset_orb_nonreject_advancement_20260612/exact_replay_report.md`

