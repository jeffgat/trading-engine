# ORB Autoresearch Flow Results

## Executive Read

Ran `orb_autoresearch_flow_seed_smoke_20260617` with train `2021-01-01`-`2023-12-31` and validation `2024-01-01`-`2024-12-31`. Holdout opened: `False`.

- Sleeves evaluated: `1`
- Raw candidates evaluated: `648`
- Top candidates emitted: `3`

## Top Candidates

| Asset | Sess | Rank | Verdict | Rule | Val R | Val PF | Pre R | Pre DD | Cal | DSR | Dep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ | NY | 1 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__ny__orb15__stop10__gap2__rr1__long__none | 28.21 | 1.81 | 35.01 | -14.48 | 2.42 | 0.56 | live_native |
| NQ | NY | 2 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__ny__orb15__stop10__gap2__rr1__long__no_wed | 25.21 | 1.95 | 31.01 | -10.48 | 2.96 | 0.55 | live_native |
| NQ | NY | 3 | PROMOTE_TO_EXACT_REPLAY_QUEUE | nq__ny__orb15__stop10__gap2__rr2__both__no_thu__small_orb_only | 21.06 | 1.57 | 40.81 | -6.00 | 6.80 | 0.73 | live_native |

## Method Notes

- Ranking uses validation transfer first, then deflated metrics, annual consistency, drawdown, Calmar, and deployability.
- `PROMOTE_TO_EXACT_REPLAY_QUEUE` is a queue label, not a live/dry-run recommendation.
- The default gate set is live-native only. Use `--include-post-filter-only` to allow research-only large-ORB lower-bound ideas.
- PBO/CSCV is not implemented here; PSR/DSR/effective trial counts are used as the available Bailey-style guardrail.

## Artifacts

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_autoresearch_flow_seed_smoke_20260617/spec.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_autoresearch_flow_seed_smoke_20260617/all_candidates.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_autoresearch_flow_seed_smoke_20260617/top_candidates.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_autoresearch_flow_seed_smoke_20260617/summary.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/orb_autoresearch_flow_seed_smoke_20260617/report.md`

