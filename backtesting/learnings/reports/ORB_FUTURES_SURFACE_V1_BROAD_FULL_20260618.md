# ORB Futures Surface v1 Results

## Executive Read

Ran `orb_futures_surface_v1_broad_full_20260618` with train `2021-01-01`-`2023-12-31` and validation `2024-01-01`-`2024-12-31`. Strategy `orb_breakout`. Holdout opened: `False`.

- Sleeves evaluated: `21`
- Raw candidates evaluated: `204120`
- Top candidates emitted: `63`

## Top Candidates

| Asset | Sess | Rank | Verdict | Rule | Val R | Val PF | Pre R | Pre DD | Cal | Cluster | Stress | No1Yr | DSR | Dep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ | NY | 1 | REJECT | nq__ny__orb30__stop12p5__gap0__rr2p5__long__no_thu__low_atr_only__small_orb_only | 3.64 | 1.10 | 7.85 | -13.14 | 0.60 | 0.33 | False | True | 0.05 | live_native |
| NQ | NY | 2 | REJECT | nq__ny__orb30__stop12p5__gap0__rr2__long__no_thu__low_atr_only__small_orb_only | 0.64 | 1.03 | 2.40 | -10.51 | 0.23 | 0.25 | False | False | 0.03 | live_native |
| NQ | NY | 3 | REJECT | nq__ny__orb30__stop12p5__gap0__rr2p5__both__no_thu__low_atr_only__small_orb_only | -1.34 | 0.99 | -1.04 | -23.01 | -0.05 | 0.00 | False | False | 0.02 | live_native |
| NQ | Asia | 1 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__asia__orb5__stop7p5__gap0__rr1p25__long__no_mon__small_or_mid_orb | 34.25 | 1.52 | 68.91 | -11.50 | 5.99 | 1.00 | True | True | 0.84 | live_native |
| NQ | Asia | 2 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__asia__orb5__stop7p5__gap0__rr1p25__long__no_mon__low_or_mid_atr | 32.75 | 1.43 | 70.16 | -12.11 | 5.79 | 1.00 | True | True | 0.82 | live_native |
| NQ | Asia | 3 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__asia__orb15__stop7p5__gap0__rr2p5__long__no_tue__small_or_mid_orb | 26.37 | 1.33 | 74.98 | -15.50 | 4.84 | 1.00 | True | True | 0.68 | live_native |
| NQ | LDN | 1 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__ldn__orb30__stop12p5__gap0__rr2p5__long__no_tue__small_orb_only | 22.21 | 1.62 | 39.78 | -11.04 | 3.60 | 1.00 | True | True | 0.73 | live_native |
| NQ | LDN | 2 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__ldn__orb30__stop10__gap0__rr2p5__both__no_mon__small_orb_only | 18.04 | 1.30 | 51.98 | -14.47 | 3.59 | 1.00 | True | True | 0.71 | live_native |
| NQ | LDN | 3 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__ldn__orb30__stop12p5__gap0__rr2p5__both__no_mon__small_orb_only | 16.60 | 1.31 | 36.79 | -14.53 | 2.53 | 1.00 | True | True | 0.55 | live_native |
| ES | NY | 1 | REJECT | es__ny__orb15__stop12p5__gap0__rr2p5__both__no_thu__low_or_mid_atr__small_orb_only | 15.33 | 1.17 | 35.36 | -16.77 | 2.11 | 0.75 | False | True | 0.21 | live_native |
| ES | NY | 2 | REJECT | es__ny__orb5__stop12p5__gap0__rr2p5__both__no_thu__small_orb_only | 16.04 | 1.18 | 50.05 | -14.16 | 3.53 | 0.67 | False | True | 0.36 | live_native |
| ES | NY | 3 | REJECT | es__ny__orb30__stop12p5__gap0__rr2p5__both__no_thu__low_or_mid_atr__small_orb_only | 20.24 | 1.24 | 44.72 | -18.52 | 2.42 | 0.67 | False | True | 0.31 | live_native |
| ES | Asia | 1 | REJECT | es__asia__orb15__stop12p5__gap0__rr2__long__no_mon__low_or_mid_atr__small_orb_only | 15.03 | 1.30 | 35.46 | -8.46 | 4.19 | 1.00 | False | True | 0.54 | live_native |
| ES | Asia | 2 | REJECT | es__asia__orb15__stop12p5__gap0__rr2__long__no_mon__small_orb_only | 15.03 | 1.30 | 34.73 | -8.46 | 4.10 | 1.00 | False | True | 0.51 | live_native |
| ES | Asia | 3 | REJECT | es__asia__orb15__stop12p5__gap0__rr1__long__no_tue__low_or_mid_atr__small_or_mid_orb | 14.01 | 1.24 | 42.01 | -7.39 | 5.69 | 1.00 | False | True | 0.64 | live_native |
| ES | LDN | 1 | REJECT | es__ldn__orb30__stop12p5__gap0__rr2__long__no_tue__low_or_mid_atr__small_orb_only | 26.55 | 1.58 | 39.76 | -10.21 | 3.90 | 1.00 | False | True | 0.75 | live_native |
| ES | LDN | 2 | REJECT | es__ldn__orb30__stop12p5__gap0__rr2__long__no_tue__small_orb_only | 24.41 | 1.51 | 42.49 | -10.21 | 4.16 | 1.00 | False | True | 0.77 | live_native |
| ES | LDN | 3 | REJECT | es__ldn__orb30__stop12p5__gap0__rr2p5__long__no_tue__small_orb_only | 23.67 | 1.48 | 40.44 | -10.21 | 3.96 | 1.00 | False | True | 0.72 | live_native |
| CL | NY | 1 | REJECT | cl__ny__orb30__stop12p5__gap0__rr1p5__both__none__low_atr_only__small_orb_only | 0.64 | 1.01 | 16.08 | -16.87 | 0.95 | 0.75 | False | True | 0.12 | live_native |
| CL | NY | 2 | REJECT | cl__ny__orb30__stop12p5__gap0__rr1p25__both__no_wed__low_atr_only__small_orb_only | 4.63 | 1.10 | 14.32 | -19.12 | 0.75 | 0.75 | False | True | 0.13 | live_native |
| CL | NY | 3 | REJECT | cl__ny__orb30__stop12p5__gap0__rr1p5__both__no_wed__low_atr_only__small_orb_only | 2.14 | 1.05 | 20.08 | -20.37 | 0.99 | 0.75 | False | True | 0.20 | live_native |
| CL | Asia | 1 | REJECT | cl__asia__orb5__stop12p5__gap0__rr2__long__none__low_atr_only__small_or_mid_orb | 16.99 | 1.22 | 42.75 | -17.94 | 2.38 | 1.00 | False | True | 0.56 | live_native |
| CL | Asia | 2 | REJECT | cl__asia__orb5__stop12p5__gap0__rr2__long__no_fri__low_atr_only__small_or_mid_orb | 16.99 | 1.22 | 42.75 | -17.94 | 2.38 | 1.00 | False | True | 0.56 | live_native |
| CL | Asia | 3 | REJECT | cl__asia__orb5__stop12p5__gap0__rr1__long__no_tue__low_atr_only__small_or_mid_orb | 10.94 | 1.24 | 30.93 | -9.06 | 3.41 | 1.00 | False | True | 0.67 | live_native |
| CL | LDN | 1 | PROMOTE_TO_EXACT_REPLAY_QUEUE | cl__ldn__orb30__stop12p5__gap0__rr1p5__short__no_thu__low_atr_only__small_orb_only | 16.18 | 1.40 | 35.13 | -12.50 | 2.81 | 1.00 | True | True | 0.77 | live_native |
| CL | LDN | 2 | REJECT | cl__ldn__orb5__stop10__gap0__rr2p5__short__no_thu__low_or_mid_atr__small_orb_only | 31.24 | 1.46 | 41.20 | -11.01 | 3.74 | 1.00 | False | True | 0.50 | live_native |
| CL | LDN | 3 | REJECT | cl__ldn__orb15__stop12p5__gap0__rr1p25__short__no_thu__small_or_mid_orb | 30.26 | 1.46 | 58.60 | -16.08 | 3.64 | 1.00 | False | True | 0.81 | live_native |
| GC | NY | 1 | REJECT | gc__ny__orb5__stop10__gap0__rr1__both__no_mon__small_orb_only | 14.00 | 1.50 | 17.00 | -10.00 | 1.70 | 0.00 | False | True | 0.17 | live_native |
| GC | NY | 2 | REJECT | gc__ny__orb5__stop12p5__gap0__rr2p5__both__no_mon__small_or_mid_orb | 4.59 | 1.06 | 15.41 | -26.50 | 0.58 | 0.00 | False | False | 0.05 | live_native |
| GC | NY | 3 | REJECT | gc__ny__orb5__stop12p5__gap0__rr1p5__both__no_fri__small_or_mid_orb | 2.85 | 1.04 | 3.75 | -23.04 | 0.16 | 0.00 | False | False | 0.03 | live_native |
| GC | Asia | 1 | PROMOTE_TO_EXACT_REPLAY_QUEUE | gc__asia__orb5__stop12p5__gap0__rr2p5__long__no_tue__low_atr_only | 25.92 | 1.71 | 75.24 | -11.48 | 6.55 | 1.00 | True | True | 0.94 | live_native |
| GC | Asia | 2 | PROMOTE_TO_EXACT_REPLAY_QUEUE | gc__asia__orb15__stop10__gap0__rr2p5__long__no_fri__low_atr_only__small_orb_only | 25.46 | 2.47 | 61.75 | -6.00 | 10.29 | 1.00 | True | True | 0.98 | live_native |
| GC | Asia | 3 | PROMOTE_TO_EXACT_REPLAY_QUEUE | gc__asia__orb5__stop12p5__gap0__rr2p5__long__no_fri__low_atr_only | 24.99 | 1.46 | 94.56 | -13.92 | 6.79 | 1.00 | True | True | 0.97 | live_native |
| GC | LDN | 1 | REJECT | gc__ldn__orb15__stop12p5__gap0__rr1p25__long__no_thu__small_orb_only | 12.84 | 1.35 | 30.79 | -12.35 | 2.49 | 1.00 | False | True | 0.59 | live_native |
| GC | LDN | 2 | REJECT | gc__ldn__orb5__stop10__gap0__rr1p5__short__no_thu__low_atr_only__small_orb_only | 15.93 | 1.72 | 28.42 | -7.50 | 3.79 | 0.80 | False | True | 0.67 | live_native |
| GC | LDN | 3 | REJECT | gc__ldn__orb15__stop12p5__gap0__rr1p25__long__no_thu__low_or_mid_atr__small_orb_only | 6.87 | 1.27 | 26.56 | -11.81 | 2.25 | 0.80 | False | True | 0.57 | live_native |
| SI | NY | 1 | REJECT | si__ny__orb5__stop12p5__gap0__rr2p5__both__no_fri__low_or_mid_atr__small_orb_only | 5.18 | 1.16 | 13.95 | -20.02 | 0.70 | 0.67 | False | True | 0.07 | live_native |
| SI | NY | 2 | REJECT | si__ny__orb15__stop12p5__gap0__rr1__both__no_fri__low_atr_only__small_orb_only | 4.00 | 1.30 | 15.23 | -4.00 | 3.81 | 0.50 | False | True | 0.27 | live_native |
| SI | NY | 3 | REJECT | si__ny__orb15__stop12p5__gap0__rr1__both__none__low_atr_only__small_orb_only | 4.00 | 1.28 | 12.23 | -4.00 | 3.06 | 0.50 | False | True | 0.16 | live_native |
| SI | Asia | 1 | REJECT | si__asia__orb5__stop10__gap0__rr1p25__long__no_tue__low_or_mid_atr__small_orb_only | 9.50 | 1.53 | 28.25 | -14.25 | 1.98 | 0.80 | False | True | 0.60 | live_native |
| SI | Asia | 2 | REJECT | si__asia__orb5__stop10__gap0__rr1p25__long__no_tue__low_atr_only__small_orb_only | 4.50 | 1.55 | 18.75 | -5.75 | 3.26 | 0.80 | False | True | 0.54 | live_native |
| SI | Asia | 3 | REJECT | si__asia__orb5__stop10__gap0__rr1__long__no_tue__small_orb_only | 12.00 | 1.37 | 25.00 | -21.00 | 1.19 | 0.75 | False | True | 0.50 | live_native |
| SI | LDN | 1 | REJECT | si__ldn__orb5__stop12p5__gap0__rr1p25__both__no_fri__small_or_mid_orb | 15.91 | 1.21 | 57.55 | -16.60 | 3.47 | 1.00 | False | True | 0.75 | live_native |
| SI | LDN | 2 | REJECT | si__ldn__orb15__stop7p5__gap0__rr2p5__both__no_fri__small_orb_only | 12.71 | 1.26 | 42.71 | -10.54 | 4.05 | 1.00 | False | True | 0.51 | live_native |
| SI | LDN | 3 | REJECT | si__ldn__orb30__stop10__gap0__rr1p5__both__no_fri__small_orb_only | 12.45 | 1.32 | 44.14 | -10.50 | 4.20 | 1.00 | False | True | 0.73 | live_native |
| RTY | NY | 1 | REJECT | rty__ny__orb30__stop12p5__gap0__rr2p5__long__no_tue__low_atr_only__small_orb_only | 14.32 | 1.64 | 21.25 | -13.24 | 1.61 | 0.67 | False | True | 0.23 | live_native |
| RTY | NY | 2 | REJECT | rty__ny__orb30__stop12p5__gap0__rr2__long__no_tue__low_atr_only__small_orb_only | 7.95 | 1.36 | 15.39 | -11.56 | 1.33 | 0.25 | False | True | 0.17 | live_native |
| RTY | NY | 3 | REJECT | rty__ny__orb30__stop10__gap0__rr2p5__long__no_tue__low_atr_only__small_orb_only | 8.44 | 1.34 | 15.49 | -11.55 | 1.34 | 0.25 | False | False | 0.14 | live_native |
| RTY | Asia | 1 | REJECT | rty__asia__orb15__stop7p5__gap0__rr1p25__short__no_wed__low_or_mid_atr__small_or_mid_orb | 15.21 | 1.23 | 42.25 | -14.29 | 2.96 | 0.83 | False | True | 0.54 | live_native |
| RTY | Asia | 2 | REJECT | rty__asia__orb15__stop7p5__gap0__rr1p25__short__no_wed__small_or_mid_orb | 10.71 | 1.15 | 50.25 | -18.54 | 2.71 | 0.83 | False | True | 0.61 | live_native |
| RTY | Asia | 3 | REJECT | rty__asia__orb5__stop10__gap0__rr1p25__both__no_wed__low_atr_only__small_orb_only | 15.65 | 1.52 | 30.16 | -9.75 | 3.09 | 0.80 | False | True | 0.61 | live_native |
| RTY | LDN | 1 | PROMOTE_TO_EXACT_REPLAY_QUEUE | rty__ldn__orb15__stop12p5__gap0__rr2__long__no_tue__small_orb_only | 22.03 | 1.53 | 47.89 | -9.50 | 5.04 | 1.00 | True | True | 0.82 | live_native |
| RTY | LDN | 2 | PROMOTE_TO_EXACT_REPLAY_QUEUE | rty__ldn__orb30__stop12p5__gap0__rr2p5__short__no_fri__low_or_mid_atr__small_orb_only | 21.31 | 1.50 | 44.54 | -6.91 | 6.44 | 1.00 | True | True | 0.77 | live_native |
| RTY | LDN | 3 | PROMOTE_TO_EXACT_REPLAY_QUEUE | rty__ldn__orb30__stop12p5__gap0__rr2p5__short__no_thu__low_or_mid_atr__small_orb_only | 19.43 | 1.50 | 43.08 | -8.28 | 5.20 | 1.00 | True | True | 0.78 | live_native |
| YM | NY | 1 | REJECT | ym__ny__orb15__stop12p5__gap0__rr2p5__long__no_mon__low_atr_only__small_or_mid_orb | 31.95 | 1.81 | 41.57 | -23.49 | 1.77 | 0.25 | False | True | 0.43 | live_native |
| YM | NY | 2 | REJECT | ym__ny__orb15__stop12p5__gap0__rr2__long__no_mon__low_atr_only__small_or_mid_orb | 20.77 | 1.54 | 22.39 | -22.49 | 1.00 | 0.20 | False | True | 0.18 | live_native |
| YM | NY | 3 | REJECT | ym__ny__orb30__stop12p5__gap0__rr2p5__long__no_thu__low_or_mid_atr__small_orb_only | 26.83 | 1.81 | 29.53 | -16.44 | 1.80 | 0.00 | False | True | 0.26 | live_native |
| YM | Asia | 1 | REJECT | ym__asia__orb5__stop7p5__gap0__rr2__long__no_mon__small_or_mid_orb | 17.39 | 1.17 | 62.58 | -21.74 | 2.88 | 1.00 | False | True | 0.52 | live_native |
| YM | Asia | 2 | REJECT | ym__asia__orb15__stop7p5__gap0__rr1p25__short__no_mon__low_atr_only | 17.50 | 1.35 | 40.75 | -14.00 | 2.91 | 0.83 | False | True | 0.66 | live_native |
| YM | Asia | 3 | REJECT | ym__asia__orb15__stop7p5__gap0__rr1p25__short__no_mon__low_atr_only__small_or_mid_orb | 17.50 | 1.35 | 32.50 | -14.00 | 2.32 | 0.83 | False | True | 0.51 | live_native |
| YM | LDN | 1 | REJECT | ym__ldn__orb30__stop10__gap0__rr1p25__long__no_tue__low_or_mid_atr__small_orb_only | 6.70 | 1.11 | 27.52 | -11.51 | 2.39 | 0.80 | False | True | 0.51 | live_native |
| YM | LDN | 2 | REJECT | ym__ldn__orb30__stop10__gap0__rr1p25__long__no_tue__small_orb_only | 4.70 | 1.07 | 28.91 | -11.51 | 2.51 | 0.80 | False | True | 0.52 | live_native |
| YM | LDN | 3 | REJECT | ym__ldn__orb30__stop10__gap0__rr2__long__no_tue__small_orb_only | 4.38 | 1.07 | 35.12 | -16.33 | 2.15 | 0.80 | False | True | 0.54 | live_native |

## Method Notes

- Ranking uses validation transfer first, neighboring-parameter cluster support, deflated metrics, annual consistency, drawdown, Calmar, and deployability.
- Plain `orb_breakout` uses completed OR levels directly; `continuation` keeps the older ORB+FVG confirmation lineage.
- Stress gate revalues preholdout trades with doubled commission plus `2` adverse ticks per side.
- No-single-year gate requires positive preholdout R after removing the best year.
- `PROMOTE_TO_EXACT_REPLAY_QUEUE` is a queue label, not a live/dry-run recommendation.
- The default gate set is live-native only. Use `--include-post-filter-only` to allow research-only large-ORB lower-bound ideas.
- Large sleeves use bounded deterministic effective-trial estimation; see each sleeve's `trial_counts.effective_trial_estimation` in `summary.json`.
- PBO/CSCV is not implemented here; PSR/DSR/effective trial counts are used as the available Bailey-style guardrail.

## Artifacts

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_broad_full_20260618/spec.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_broad_full_20260618/all_candidates.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_broad_full_20260618/top_candidates.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_broad_full_20260618/summary.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_broad_full_20260618/report.md`

