# ORB Autoresearch Flow Plan

## Purpose

This is a guarded autoresearch flow for ORB continuation parameters across `['NQ', 'ES', 'GC', 'SI', 'RTY', 'YM']` and `['NY', 'Asia', 'LDN']`. It is designed as a rejection engine: broad search is allowed, but promotion requires validation, deflated metrics, deployability labels, and exact replay.

## Frozen Spec

- Train: `2021-01-01` to `2023-12-31`
- Validation: `2024-01-01` to `2024-12-31`
- Holdout: `2025-01-01` onward; opened in this run: `False`
- Search streams per sleeve: `360`
- Post-filter variants per stream: `54`
- Raw candidates per sleeve: `19440`
- Total raw candidates: `349920`

## Search Space

- ORB minutes: `[15, 30]`
- Stop ATR%: `[5.0, 7.5, 10.0, 12.5]`
- Min gap ATR%: `[1.0, 2.0, 3.0]`
- RR: `[1.0, 1.25, 1.5, 2.0, 2.5]`
- Directions: `['long', 'short', 'both']`
- DOW exclusions: `['none', 'no_mon', 'no_tue', 'no_wed', 'no_thu', 'no_fri']`
- ATR gates: `['none', 'low_or_mid_atr', 'low_atr_only']`
- ORB gates: `['none', 'small_or_mid_orb', 'small_orb_only']`

## Guardrails

- Holdout is never opened unless --open-holdout is passed.
- Search space is fixed before run artifacts are written.
- Trial counts are reported per sleeve and globally.
- Candidates with large_orb_only are post_filter_only unless live min-ORB support exists.
- Promotion output is exact-replay queue only, not live deployment.

## Sleeve Trial Budget

| Asset | Session | Streams | Post Filters | Raw Candidates |
| --- | --- | --- | --- | --- |
| NQ | NY | 360 | 54 | 19440 |
| NQ | Asia | 360 | 54 | 19440 |
| NQ | LDN | 360 | 54 | 19440 |
| ES | NY | 360 | 54 | 19440 |
| ES | Asia | 360 | 54 | 19440 |
| ES | LDN | 360 | 54 | 19440 |
| GC | NY | 360 | 54 | 19440 |
| GC | Asia | 360 | 54 | 19440 |
| GC | LDN | 360 | 54 | 19440 |
| SI | NY | 360 | 54 | 19440 |
| SI | Asia | 360 | 54 | 19440 |
| SI | LDN | 360 | 54 | 19440 |
| RTY | NY | 360 | 54 | 19440 |
| RTY | Asia | 360 | 54 | 19440 |
| RTY | LDN | 360 | 54 | 19440 |
| YM | NY | 360 | 54 | 19440 |
| YM | Asia | 360 | 54 | 19440 |
| YM | LDN | 360 | 54 | 19440 |

## Commands

```bash
cd backtesting
uv run python scripts/run_orb_autoresearch_flow.py --mode plan --preset broad
uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset seed --assets NQ --sessions NY
uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset broad --allow-large-run
```

