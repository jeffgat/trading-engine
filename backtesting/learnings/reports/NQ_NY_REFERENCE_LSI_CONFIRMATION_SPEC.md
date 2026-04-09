# NQ NY Reference LSI Confirmation Spec

- Holdout `2025-01-01+` remains frozen.
- This pass only retests the strongest post-follow-up neighborhood before any holdout decision.

## Fixed Choices

- `direction_filter = both`
- `entry_end = 11:00`
- `ref_lsi_gap_entry_edge = near`
- `atr_length = 10`
- `min_gap_atr_pct = 5.0`

## Structures

- `gap6 / inv15`
- `gap6 / inv18`
- `gap8 / inv18`
- `gap12 / inv12`

## Reward Choices

- `rr`: [3.0, 3.25]
- `tp1_ratio`: [0.7, 0.8]

- Total raw trials: `16`