# NQ NY Reference LSI Follow-Up Spec

- Holdout `2025-01-01+` remains frozen.
- This follow-up reopens only the winning family from the first discovery pass.

## Fixed Choices

- `direction_filter = both`
- `entry_end = 11:00`
- `ref_lsi_gap_entry_edge = near`
- `atr_length = 10`
- `min_gap_atr_pct = 5.0`

## Structural Neighborhoods

- `gap4 / inv15`
- `gap6 / inv15`
- `gap6 / inv18`
- `gap8 / inv18`
- `gap8 / inv21`
- `gap10 / inv12`
- `gap12 / inv9`
- `gap12 / inv12`
- `gap12 / inv15`
- `gap14 / inv12`

## Reward Neighborhood

- `rr`: [2.75, 3.0, 3.25]
- `tp1_ratio`: [0.7, 0.8, 0.9]

- Total raw trials: `90`