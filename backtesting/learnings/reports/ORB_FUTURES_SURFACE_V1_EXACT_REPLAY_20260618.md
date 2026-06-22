# ORB Futures Surface v1 Exact Replay

## Summary

Ran `ORB_FUTURES_SURFACE_V1_EXACT_REPLAY` through execution-engine exact replay for `2021-01-01`-`2024-12-31`. Holdout remained closed.

- Candidates replayed: `11`
- Exact replay pass: `4`
- Exact replay watch: `5`
- Exact replay fail: `2`
- Promoted rows skipped: `2` unsupported `both`-direction rows
- Source candidates: promoted one-sided rows from ORB Futures Surface v1 broad run.

## Pass

| Cand | Rule | Status | Research R | Exact Net R | Ret | Exact PF | Exact DD | Trades | Delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORBFX_CL_LDN_R1 | cl__ldn__orb30__stop12p5__gap0__rr1p5__short__no_thu__low_atr_only__small_orb_only | EXACT_REPLAY_PASS | 35.13 | 33.68 | 0.96 | 1.38 | -13.50 | 177 | 15 |
| ORBFX_GC_ASIA_R1 | gc__asia__orb5__stop12p5__gap0__rr2p5__long__no_tue__low_atr_only | EXACT_REPLAY_PASS | 75.24 | 68.31 | 0.91 | 1.48 | -7.57 | 230 | -62 |
| ORBFX_NQ_ASIA_R1 | nq__asia__orb5__stop7p5__gap0__rr1p25__long__no_mon__small_or_mid_orb | EXACT_REPLAY_PASS | 68.91 | 76.47 | 1.11 | 1.36 | -10.32 | 450 | -212 |
| ORBFX_RTY_LDN_R1 | rty__ldn__orb15__stop12p5__gap0__rr2__long__no_tue__small_orb_only | EXACT_REPLAY_PASS | 47.89 | 41.66 | 0.87 | 1.33 | -6.95 | 278 | 4 |

## Watch

| Cand | Rule | Status | Research R | Exact Net R | Ret | Exact PF | Exact DD | Trades | Delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORBFX_GC_ASIA_R3 | gc__asia__orb5__stop12p5__gap0__rr2p5__long__no_fri__low_atr_only | EXACT_REPLAY_WATCH | 94.56 | 23.53 | 0.25 | 1.47 | -6.00 | 80 | -233 |
| ORBFX_NQ_ASIA_R2 | nq__asia__orb5__stop7p5__gap0__rr1p25__long__no_mon__low_or_mid_atr | EXACT_REPLAY_WATCH | 70.16 | 8.72 | 0.12 | 1.13 | -11.03 | 125 | -535 |
| ORBFX_NQ_ASIA_R3 | nq__asia__orb15__stop7p5__gap0__rr2p5__long__no_tue__small_or_mid_orb | EXACT_REPLAY_WATCH | 74.98 | 11.66 | 0.16 | 1.14 | -12.50 | 118 | -493 |
| ORBFX_NQ_LDN_R1 | nq__ldn__orb30__stop12p5__gap0__rr2p5__long__no_tue__small_orb_only | EXACT_REPLAY_WATCH | 39.78 | 8.53 | 0.21 | 1.36 | -6.01 | 54 | -207 |
| ORBFX_RTY_LDN_R2 | rty__ldn__orb30__stop12p5__gap0__rr2p5__short__no_fri__low_or_mid_atr__small_orb_only | EXACT_REPLAY_WATCH | 44.54 | 23.98 | 0.54 | 1.48 | -5.24 | 107 | -115 |

## Fail

| Cand | Rule | Status | Research R | Exact Net R | Ret | Exact PF | Exact DD | Trades | Delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORBFX_GC_ASIA_R2 | gc__asia__orb15__stop10__gap0__rr2p5__long__no_fri__low_atr_only__small_orb_only | EXACT_REPLAY_FAIL | 61.75 | -1.09 | -0.02 | 0.00 | 0.00 | 1 | -107 |
| ORBFX_RTY_LDN_R3 | rty__ldn__orb30__stop12p5__gap0__rr2p5__short__no_thu__low_or_mid_atr__small_orb_only | EXACT_REPLAY_FAIL | 43.08 | -0.97 | -0.02 | 0.87 | -5.00 | 13 | -192 |

## Artifacts

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_exact_replay_20260618/exact_replay_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_exact_replay_20260618/exact_replay_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_exact_replay_20260618/exact_replay_payload.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_exact_replay_20260618/exact_replay_report.md`
