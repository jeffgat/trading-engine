# NQ NY HTF-LSI Pre-Entry TP2 + Fresh Sweep Cancel

Date: 2026-04-17

## Question

For the current `NQ NY HTF_LSI 5m lag24` lead, does it help to cancel a still-open limit order only when:

1. price touches `TP2` before entry, and
2. a fresh post-signal HTF-LSI sweep also occurs before the order fills

This is a follow-up to the broader `ALPHA_V1` pre-entry target-touch cancel read.

## Method

- Frozen branch: current `NQ NY HTF_LSI 5m lag24` operating lead from `backtesting/scripts/htf_lsi_common.py`
- Variants compared:
  - `baseline`
  - `tp2_only`: cancel if pre-entry `TP2` is touched
  - `tp2_plus_sweep`: cancel only after both pre-entry `TP2` touch and a fresh HTF-LSI sweep are seen
- Fresh sweep detection reuses the branch's configured HTF-LSI sweep sources during the pending-order window.
- Comparison windows:
  - Full history
  - Recent: `2024-01-01+`
- Important implementation note:
  - If a shared bar touches both the entry and the cancel condition, fill still wins. The cancel only fires while the limit is still unfilled.

Artifacts:
- Script: `backtesting/scripts/run_nq_htf_lsi_pre_entry_tp2_sweep_cancel.py`
- Raw summary: `backtesting/data/results/nq_htf_lsi_pre_entry_tp2_sweep_cancel_20260417/summary.json`

## Result

The sweep-gated version added **no value** on this sample. In fact, it matched baseline exactly.

| Variant | Filled trades | No-fills | Net R | Max DD |
|---|---:|---:|---:|---:|
| `baseline` | 494 | 52 | 89.3R | -10.9R |
| `tp2_only` | 490 | 56 | 88.2R | -10.9R |
| `tp2_plus_sweep` | 494 | 52 | 89.3R | -10.9R |

Recent `2024-01-01+`:

| Variant | Filled trades | No-fills | Net R | Max DD |
|---|---:|---:|---:|---:|
| `baseline` | 105 | 12 | 34.8R | -5.2R |
| `tp2_only` | 104 | 13 | 34.1R | -5.2R |
| `tp2_plus_sweep` | 105 | 12 | 34.8R | -5.2R |

## Interpretation

- Plain pre-entry `TP2` cancel remained mildly harmful:
  - Full history: `-1.1R`
  - Recent: `-0.7R`
- The `TP2 + fresh sweep` conjunction produced the **exact same fill set and PnL** as baseline.
- That means the conjunction never actually canceled a trade in this sample.
- Inference: the pending orders that reached pre-entry `TP2` did **not** also see a qualifying fresh post-signal HTF-LSI sweep before fill.

## Decision

Keep the current `NQ NY HTF_LSI 5m lag24` branch unchanged.

- Do **not** adopt plain pre-entry `TP2` cancel on this leg.
- Do **not** adopt the sweep-gated version either; it is functionally a no-op on the observed sample.
- If we revisit pre-entry invalidation on this branch, it should use a different causal gate than "another HTF-LSI sweep happened."
