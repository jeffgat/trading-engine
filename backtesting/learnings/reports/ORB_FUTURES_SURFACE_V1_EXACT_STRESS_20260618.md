# ORB Futures Surface v1 Exact Stress

## Summary

Stress-tested the four exact-replay pass rows from `ORB_FUTURES_SURFACE_V1_EXACT_REPLAY` over `2021-01-01`-`2024-12-31`. Holdout remained closed.

- Full stress: `2x` baseline commission plus `2` adverse ticks per side on every filled round trip.
- This is post-exact-replay cost/slippage accounting; it preserves the exact replay signal/fill path.
- Full-stress pass: `0`
- Full-stress watch: `2`
- Full-stress fail: `2`

## Full Stress Pass

_No rows._

## Full Stress Watch

| Cand | Status | Deploy | Replay | Stress R | Ret Exact | PF | DD R | Min Year | Trades |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORBFX_GC_ASIA_R1 | EXACT_STRESS_WATCH | live_native | complete | 15.45 | 0.23 | 1.09 | -15.58 | -4.81 | 230 |
| ORBFX_NQ_ASIA_R1 | EXACT_STRESS_WATCH | live_native | complete | 33.76 | 0.44 | 1.15 | -17.21 | -3.89 | 450 |

## Full Stress Fail

| Cand | Status | Deploy | Replay | Stress R | Ret Exact | PF | DD R | Min Year | Trades |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ORBFX_CL_LDN_R1 | EXACT_STRESS_FAIL | live_native | complete | -13.39 | -0.40 | 0.88 | -19.58 | -12.43 | 177 |
| ORBFX_RTY_LDN_R1 | EXACT_STRESS_FAIL | live_native | complete | -0.14 | -0.00 | 1.00 | -20.50 | -4.06 | 278 |

## Stress Ladder

| Cand | Scenario | Deploy | Net R | PF | DD R | Min Year |
| --- | --- | --- | --- | --- | --- | --- |
| ORBFX_CL_LDN_R1 | baseline_recomputed | live_native | 33.68 | 1.38 | -14.78 | 0.39 |
| ORBFX_GC_ASIA_R1 | baseline_recomputed | live_native | 68.31 | 1.48 | -9.37 | 5.54 |
| ORBFX_NQ_ASIA_R1 | baseline_recomputed | live_native | 76.46 | 1.36 | -12.10 | 6.62 |
| ORBFX_RTY_LDN_R1 | baseline_recomputed | live_native | 41.65 | 1.33 | -8.89 | 1.96 |
| ORBFX_CL_LDN_R1 | double_commission_only | live_native | 20.53 | 1.21 | -16.06 | 0.28 |
| ORBFX_GC_ASIA_R1 | double_commission_only | live_native | 52.87 | 1.35 | -10.90 | 3.08 |
| ORBFX_NQ_ASIA_R1 | double_commission_only | live_native | 60.87 | 1.28 | -13.88 | 5.03 |
| ORBFX_RTY_LDN_R1 | double_commission_only | live_native | 26.39 | 1.20 | -10.89 | 0.42 |
| ORBFX_CL_LDN_R1 | two_ticks_slippage_only | live_native | -0.25 | 1.00 | -18.09 | -5.75 |
| ORBFX_GC_ASIA_R1 | two_ticks_slippage_only | live_native | 30.88 | 1.19 | -13.51 | -1.43 |
| ORBFX_NQ_ASIA_R1 | two_ticks_slippage_only | live_native | 49.35 | 1.22 | -15.19 | 1.24 |
| ORBFX_RTY_LDN_R1 | two_ticks_slippage_only | live_native | 15.12 | 1.11 | -12.88 | -0.72 |
| ORBFX_CL_LDN_R1 | full_stress_2x_commission_2ticks | live_native | -13.39 | 0.88 | -19.58 | -12.43 |
| ORBFX_GC_ASIA_R1 | full_stress_2x_commission_2ticks | live_native | 15.45 | 1.09 | -15.58 | -4.81 |
| ORBFX_NQ_ASIA_R1 | full_stress_2x_commission_2ticks | live_native | 33.76 | 1.15 | -17.21 | -3.89 |
| ORBFX_RTY_LDN_R1 | full_stress_2x_commission_2ticks | live_native | -0.14 | 1.00 | -20.50 | -4.06 |
| ORBFX_CL_LDN_R1 | boundary_2x_commission_4ticks | live_native | -47.32 | 0.64 | -50.64 | -29.65 |
| ORBFX_GC_ASIA_R1 | boundary_2x_commission_4ticks | live_native | -21.98 | 0.89 | -39.82 | -13.00 |
| ORBFX_NQ_ASIA_R1 | boundary_2x_commission_4ticks | live_native | 6.64 | 1.03 | -25.98 | -12.80 |
| ORBFX_RTY_LDN_R1 | boundary_2x_commission_4ticks | live_native | -26.67 | 0.84 | -38.50 | -14.01 |

## Artifacts

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_exact_stress_20260618/exact_stress_summary.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_exact_stress_20260618/exact_stress_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_exact_stress_20260618/exact_stress_payload.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_exact_stress_20260618/exact_stress_report.md`

