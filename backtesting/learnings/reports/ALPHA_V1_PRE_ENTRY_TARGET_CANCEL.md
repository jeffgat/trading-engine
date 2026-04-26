# ALPHA_V1 Pre-Entry Target-Touch Cancel

Date: 2026-04-17

## Question

For each active `ALPHA_V1` leg, does cancelling a still-open limit order help if price touches:

1. `TP1` before entry
2. `TP2` before entry

## Method

- Active lineup from `backtesting/learnings/ALPHA_V1.md`
  - `HTF_LSI/NQ_NY-L24`
  - `ORB/NQ_ASIA-RR6`
  - `ORB/ES_ASIA-RR1.5`
  - `ORB/ES_NY-RR5`
- Engine change: `StrategyConfig.limit_cancel_on_pre_entry_target_touch = "", "tp1", "tp2"`
- Comparison windows:
  - Full history
  - Recent: `2024-01-01+`
- Important implementation note:
  - If a shared bar touches both the entry and the pre-entry target, fill still wins. The cancel only fires on bars where the order is still unfilled.

Raw summary JSON:
- `backtesting/data/results/alpha_v1_pre_entry_target_cancel_20260417/summary.json`

Script:
- `backtesting/scripts/run_alpha_v1_pre_entry_target_cancel.py`

## Main Result

This was a **pure trade-removal filter** in practice. No leg produced variant-only fills; the cancel rules only removed baseline trades.

There is **no portfolio-wide case** for turning this on broadly.

- `TP1` cancel is generally too destructive.
- `TP2` cancel is neutral-to-harmful on three legs, but looks constructive on `ES_NY`.

## Full-History Read

Positive `delta DD` means shallower drawdown. Negative `delta DD` means worse drawdown.

| Leg | TP1 delta R | TP1 delta DD | TP2 delta R | TP2 delta DD | Verdict |
|---|---:|---:|---:|---:|---|
| `HTF_LSI/NQ_NY-L24` | -2.5R | +0.8R | -1.1R | +0.0R | Keep baseline |
| `ORB/NQ_ASIA-RR6` | -5.8R | +1.4R | +0.0R | +0.0R | `TP1` not worth it; `TP2` irrelevant |
| `ORB/ES_ASIA-RR1.5` | -14.6R | +0.7R | -7.3R | +0.7R | Reject both |
| `ORB/ES_NY-RR5` | -54.6R | -5.5R | +2.8R | +1.5R | Reject `TP1`; **promising `TP2`** |

## Recent Read (`2024-01-01+`)

| Leg | TP1 delta R | TP1 delta DD | TP2 delta R | TP2 delta DD | Verdict |
|---|---:|---:|---:|---:|---|
| `HTF_LSI/NQ_NY-L24` | -3.5R | +0.0R | -0.7R | +0.0R | Keep baseline |
| `ORB/NQ_ASIA-RR6` | +2.1R | +0.0R | +0.0R | +0.0R | Small recent-only `TP1` improvement, but not enough to override full-history damage |
| `ORB/ES_ASIA-RR1.5` | -8.1R | -1.6R | -5.1R | -0.7R | Reject both |
| `ORB/ES_NY-RR5` | +1.0R | +2.2R | +2.6R | +0.6R | `TP2` still best; `TP1` only improved recent sample, not full history |

## Leg-Level Notes

### `HTF_LSI/NQ_NY-L24`

- `TP1` cancel removes 30 trades on full history and costs `2.5R`.
- `TP2` cancel barely changes behaviour and still loses `1.1R`.
- Conclusion: the current HTF-LSI leg does not benefit from pre-entry target-touch invalidation.

### `ORB/NQ_ASIA-RR6`

- `TP1` cancel trims trades and does make full-history DD slightly shallower, but the cost is `-5.8R`.
- `TP2` cancel did nothing meaningful in this sample.
- Conclusion: not a robust adoption candidate. If revisited, it should be framed as a recency-sensitive filter, not a default rule.

### `ORB/ES_ASIA-RR1.5`

- Both variants reduce expectancy materially.
- Recent window gets worse on both R and DD.
- Conclusion: hard reject.

### `ORB/ES_NY-RR5`

- `TP1` cancel is dangerous on full history despite a better recent sample.
- `TP2` cancel is the standout result:
  - Full history: `+2.8R`, DD improves by `1.5R`
  - Recent: `+2.6R`, DD improves by `0.6R`
- Conclusion: if we want to promote one version of this idea, it should be **ES NY with pre-entry `TP2` cancel only**.

## Decision

Do **not** add a universal pre-entry target-touch cancel rule to `ALPHA_V1`.

Current recommendation:

- `HTF_LSI/NQ_NY-L24`: baseline
- `ORB/NQ_ASIA-RR6`: baseline
- `ORB/ES_ASIA-RR1.5`: baseline
- `ORB/ES_NY-RR5`: worthy of a follow-up branch with `limit_cancel_on_pre_entry_target_touch="tp2"`

## HTF-LSI Follow-Up

A targeted NQ HTF-LSI follow-up also tested a stricter conjunction:

- cancel only when pre-entry `TP2` is touched **and** a fresh post-signal HTF-LSI sweep appears before fill

Result:

- `tp2_plus_sweep` matched baseline exactly on both full history and the recent `2024-01-01+` window
- practical conclusion: the extra HTF-LSI sweep requirement filtered nothing in this sample, so the NQ HTF-LSI leg still stays on baseline

Reference report:

- `backtesting/learnings/reports/NQ_NY_HTF_LSI_PRE_ENTRY_TP2_SWEEP_CANCEL.md`

## ORB HTF-High Follow-Up

A separate ORB-only follow-up tested two ideas on the active `ALPHA_V1` ORB legs, using instrument-native published unswept HTF highs (`NQ=60m/n_left3`, `ES=90m/n_left3`):

- cancel a pending ORB limit only when pre-entry `TP2` is touched **and** a fresh HTF high is swept before fill
- keep only ORB signals where the active HTF high is already at `TP1` or greater when the order arms

Result:

- the `TP2 + fresh HTF-high sweep` cancel was a no-op on `NQ_ASIA` and mildly harmful on both ES ORB legs
- the `HTF high >= TP1` gate was too destructive everywhere and did not show a robust recent-window quality edge

Reference report:

- `backtesting/learnings/reports/ALPHA_V1_ORB_HTF_HIGH_FILTERS.md`
