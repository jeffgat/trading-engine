# ORB Futures Surface v1 Results

## Executive Read

Ran `orb_futures_surface_v1_seed_core_nq_es_cl_ny_20260618` with train `2021-01-01`-`2023-12-31` and validation `2024-01-01`-`2024-12-31`. Strategy `orb_breakout`. Holdout opened: `False`.

- Sleeves evaluated: `3`
- Raw candidates evaluated: `4374`
- Top candidates emitted: `9`

## Top Candidates

| Asset | Sess | Rank | Verdict | Rule | Val R | Val PF | Pre R | Pre DD | Cal | Cluster | Stress | No1Yr | DSR | Dep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ | NY | 1 | REJECT | nq__ny__orb15__stop10__gap0__rr2__long__no_thu__low_atr_only__small_orb_only | 14.20 | 1.32 | -19.67 | -37.86 | -0.52 | 0.00 | False | False | 0.00 | live_native |
| NQ | NY | 2 | REJECT | nq__ny__orb15__stop10__gap0__rr2__long__no_thu__low_atr_only | 10.20 | 1.17 | -43.67 | -54.86 | -0.80 | 0.00 | False | False | 0.00 | live_native |
| NQ | NY | 3 | REJECT | nq__ny__orb15__stop10__gap0__rr2__long__no_tue__low_atr_only | 10.12 | 1.18 | -28.82 | -38.95 | -0.74 | 0.00 | False | False | 0.00 | live_native |
| ES | NY | 1 | REJECT | es__ny__orb5__stop10__gap0__rr2__both__no_fri__low_atr_only__small_orb_only | -31.26 | 0.62 | -28.52 | -34.26 | -0.83 | 0.00 | False | False | 0.00 | live_native |
| ES | NY | 2 | REJECT | es__ny__orb5__stop10__gap0__rr2__both__no_thu__low_or_mid_atr__small_orb_only | -22.25 | 0.77 | -21.03 | -37.60 | -0.56 | 0.00 | False | False | 0.00 | live_native |
| ES | NY | 3 | REJECT | es__ny__orb5__stop10__gap0__rr2__both__no_mon__low_or_mid_atr__small_orb_only | -23.40 | 0.74 | -21.98 | -45.29 | -0.49 | 0.00 | False | False | 0.00 | live_native |
| CL | NY | 1 | REJECT | cl__ny__orb5__stop10__gap0__rr2__both__no_thu__low_atr_only__small_orb_only | -5.00 | 0.91 | 15.00 | -10.00 | 1.50 | 0.00 | False | True | 0.07 | live_native |
| CL | NY | 2 | REJECT | cl__ny__orb5__stop10__gap0__rr2__both__no_wed__small_orb_only | -11.00 | 0.86 | 36.10 | -18.00 | 2.01 | 0.00 | False | True | 0.20 | live_native |
| CL | NY | 3 | REJECT | cl__ny__orb5__stop10__gap0__rr2__both__no_thu__low_or_mid_atr__small_orb_only | -12.00 | 0.85 | 28.10 | -15.00 | 1.87 | 0.00 | False | True | 0.13 | live_native |

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

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_seed_core_nq_es_cl_ny_20260618/spec.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_seed_core_nq_es_cl_ny_20260618/all_candidates.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_seed_core_nq_es_cl_ny_20260618/top_candidates.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_seed_core_nq_es_cl_ny_20260618/summary.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_futures_surface_v1_seed_core_nq_es_cl_ny_20260618/report.md`

