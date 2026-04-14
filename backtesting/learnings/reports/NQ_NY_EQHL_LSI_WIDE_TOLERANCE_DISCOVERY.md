# NQ NY EQHL-LSI Wide Tolerance Discovery

- Objective: test whether NQ equal-high/low matching should be widened well beyond the original `0-4 tick` packet, and locate where the trade-count gain starts to degrade quality.
- Method: focused long-side discovery packet using the existing EQHL-LSI runner with point-based tolerances and added `3m` support.
- Scope: `1m/2m/3m/5m` base entries, EQHL source TF `{5m,15m,60m}`, tolerance `{3,5,10,15,20}` points, `touches=2`, `direction=long`, `entry_mode=fvg_limit`, `entry_end={13:00,15:00}`.
- Non-tolerance parameters stayed on the broad-discovery anchor: `rr=3.0`, `tp1_ratio=0.5`, `min_gap_atr_pct=3.0`, `eqhl_n_left=2`, `eqhl_lookback_bars=48`, and real-minute FVG windows of `left=100`, `right=10`.

## Summary

- Widening the zone did **not** immediately kill EQHL on NQ.
- In this focused packet, the broad sweet spot was roughly `5-15` points.
- Aggregate quality improved from `3 -> 15` points, then fell back at `20`.
- `20` points increased count further, but the average validation edge softened enough to mark the first clean falloff.
- `3m` was successfully added and produced a real live row rather than noise.

## Aggregate Tolerance Read

| Tolerance | Mean Pre Trades | Mean Val PF | Mean Val Avg R | Alive Rows |
| ---: | ---: | ---: | ---: | ---: |
| `3pt` | 519.3 | 1.388 | 0.162 | 17 / 24 |
| `5pt` | 609.3 | 1.360 | 0.158 | 15 / 24 |
| `10pt` | 709.5 | 1.410 | 0.180 | 16 / 24 |
| `15pt` | 752.7 | 1.446 | 0.192 | 22 / 24 |
| `20pt` | 773.0 | 1.362 | 0.159 | 19 / 24 |

Practical read:

- Trade count rose steadily as expected.
- The broad quality hump peaked around `15pt`.
- `20pt` still produced many live rows, but the average validation PF / avg R rolled over.

## Best Row Per Entry Timeframe

| Entry TF | Best Row | Pre Trades | Val Trades | Val PF | Val Avg R | Val Calmar |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `1m` | `60m EQHL, 15pt, end13:00` | 347 | 79 | 1.908 | 0.348 | 7.53 |
| `2m` | `15m EQHL, 5pt, end13:00` | 604 | 152 | 1.583 | 0.263 | 5.10 |
| `3m` | `15m EQHL, 15pt, end13:00` | 671 | 169 | 1.656 | 0.266 | 8.61 |
| `5m` | `5m EQHL, 5pt, end13:00` | 645 | 165 | 1.684 | 0.270 | 7.99 |

## Structural Read

- `1m` behaved very differently from the earlier tight-tolerance packet. Once the zone widened, the best sampled `1m` rows came off `60m EQHL`, not local structure.
- `2m` and `5m` preferred moderate widening around `5pt`.
- `3m` became a legitimate transfer branch, and its best row wanted much wider `15pt` matching on `15m EQHL`.
- `15m EQHL` and `60m EQHL` both became materially more usable once the zone widened. In the tight-tolerance study, `60m` was mostly a tiny-sample curiosity; here it became a real family, especially for `1m`.

## Conclusion

- The old `0-4 tick` packet was almost certainly too tight for NQ if the goal is to explore broader discretionary-style near-equal liquidity shelves.
- For the current focused long-side packet, the honest falloff starts at **`20 points`**, not at `5` or `10`.
- The current best broad next-step operating ranges are:
  - `5pt` for `2m` and `5m`
  - `15pt` for `3m`
  - `10-15pt` for `1m` if we insist on sufficient validation sample
- `20pt` should be treated as the “too broad starts here” marker for the next round, not as the new default.

## Artifacts

- Raw results: `backtesting/data/results/nq_ny_eqhl_lsi_broad_discovery_wide_tolerance_points_long_all_tf/`
- Script used: `backtesting/scripts/run_cross_asset_eqhl_lsi_broad_discovery.py`
