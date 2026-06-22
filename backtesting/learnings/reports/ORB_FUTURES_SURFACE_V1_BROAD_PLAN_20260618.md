# ORB Futures Surface v1 Plan

## Purpose

This is a guarded autoresearch flow for ORB futures surface parameters across `['NQ', 'ES', 'CL', 'GC', 'SI', 'RTY', 'YM']` and `['NY', 'Asia', 'LDN']`. It is designed as a rejection engine: broad search is allowed, but promotion requires validation, deflated metrics, deployability labels, and exact replay.

## Frozen Spec

- Strategy: `orb_breakout`
- Train: `2021-01-01` to `2023-12-31`
- Validation: `2024-01-01` to `2024-12-31`
- Holdout: `2025-01-01` onward; opened in this run: `False`
- Search streams per sleeve: `180`
- Post-filter variants per stream: `54`
- Raw candidates per sleeve: `9720`
- Total raw candidates: `204120`

## Implementation Order

1. canonical_orb_engine
2. baseline_family_replication
3. broad_coarse_surface
4. module_ablations
5. robust_cluster_promotion
6. frozen_holdout_then_paper

## Baseline Families

- ES/NQ RTH 5/15/30 plain ORB
- TORB-style probe-time sweep via OR minute grid
- CL crude oil ORB
- threshold-adjusted ORB with protective ATR/OR stops

## Module Ablation Order

- stops
- exits
- confirmations
- filters
- sizing_overlays

## Promotion Rules

- Prefer neighboring parameter clusters over isolated maxima.
- Require train/validation transfer before any holdout read.
- Require PSR/DSR with explicit raw/effective trial counts.
- Promote only exact-replay queue candidates, not live approvals.
- Run 2x cost/slippage stress and no-single-year checks before paper trading.

## Search Space

- ORB minutes: `[5, 15, 30]`
- Stop ATR%: `[5.0, 7.5, 10.0, 12.5]`
- Min gap ATR%: `[0.0]`
- RR: `[1.0, 1.25, 1.5, 2.0, 2.5]`
- Directions: `['long', 'short', 'both']`
- DOW exclusions: `['none', 'no_mon', 'no_tue', 'no_wed', 'no_thu', 'no_fri']`
- ATR gates: `['none', 'low_or_mid_atr', 'low_atr_only']`
- ORB gates: `['none', 'small_or_mid_orb', 'small_orb_only']`

## Guardrails

- Holdout is never opened unless --open-holdout is passed.
- Search space is fixed before run artifacts are written.
- Trial counts are reported per sleeve and globally.
- Large sleeves use bounded deterministic effective-trial estimation and report the approximation metadata.
- Candidates with large_orb_only are post_filter_only unless live min-ORB support exists.
- Promotion output is exact-replay queue only, not live deployment.

## Sleeve Trial Budget

| Asset | Session | Streams | Post Filters | Raw Candidates |
| --- | --- | --- | --- | --- |
| NQ | NY | 180 | 54 | 9720 |
| NQ | Asia | 180 | 54 | 9720 |
| NQ | LDN | 180 | 54 | 9720 |
| ES | NY | 180 | 54 | 9720 |
| ES | Asia | 180 | 54 | 9720 |
| ES | LDN | 180 | 54 | 9720 |
| CL | NY | 180 | 54 | 9720 |
| CL | Asia | 180 | 54 | 9720 |
| CL | LDN | 180 | 54 | 9720 |
| GC | NY | 180 | 54 | 9720 |
| GC | Asia | 180 | 54 | 9720 |
| GC | LDN | 180 | 54 | 9720 |
| SI | NY | 180 | 54 | 9720 |
| SI | Asia | 180 | 54 | 9720 |
| SI | LDN | 180 | 54 | 9720 |
| RTY | NY | 180 | 54 | 9720 |
| RTY | Asia | 180 | 54 | 9720 |
| RTY | LDN | 180 | 54 | 9720 |
| YM | NY | 180 | 54 | 9720 |
| YM | Asia | 180 | 54 | 9720 |
| YM | LDN | 180 | 54 | 9720 |

## Commands

```bash
cd backtesting
uv run python scripts/run_orb_autoresearch_flow.py --mode plan --preset broad
uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset seed --assets NQ --sessions NY
uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset seed --strategy continuation --assets NQ --sessions NY
uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset broad --allow-large-run
```

