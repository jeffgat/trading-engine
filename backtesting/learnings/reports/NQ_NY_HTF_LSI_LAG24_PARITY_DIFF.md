# NQ NY HTF-LSI Lag24 Parity Diff

- Objective: decompose the gap between the frozen research branch and the exact live-engine replay at the trade level.
- Profile: `HTF_LSI_5M_LAG24`
- Exact replay window: `2016-01-01` to `2026-03-24`

## Key Findings

- The current direct research export printed `602` trades, but `54` of those were `no_fill` setups. Removing those restores the frozen filled-trade count of `548` (`506` pre-holdout, `42` holdout).
- Holdout parity is materially tighter than the raw count suggests. Exact replay filled `42` trades, and all `42` map to research filled trades under a same-trade key of `(date, entry_price, htf_level_price, fvg_to_inversion_bars)`.
- Half of the apparent holdout mismatch is timestamping only: strict minute matching found `24` overlaps, but fuzzy same-trade matching found `42` overlaps. Exact fill timestamps were usually `+1` to `+4` minutes later than the research bar timestamp.
- The true remaining holdout gap is `0` research trades across `0` days, with `0` exact-only holdout trades.
- Those missing holdout trades were all slot-1 trades (`{}`), so the residual gap does not look like a trade-cap or second-trade-per-session problem.

## Window Summary

| Window | Research Filled | Exact | Strict Minute Match | Fuzzy Same-Trade Match | Research Only | Exact Only |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pre-Holdout | 506 | 498 | 265 | 490 | 16 | 8 |
| Holdout | 42 | 42 | 24 | 42 | 0 | 0 |

## Holdout Shape

- Minute-shift distribution on matched holdout trades: `{0: 24, 1: 8, 2: 4, 3: 4, 4: 2}`
- Missing holdout trade days: ``
- Missing holdout FVG-to-inversion bars: `[]`
- Missing holdout entry times: `[]`
- Missing holdout exit types: `[]`

## Pre-Holdout Shape

- Minute-shift distribution on matched pre-holdout trades: `{0: 264, 1: 74, 2: 50, 3: 57, 4: 45}`
- Pre-holdout research-only day count: `15`
- Pre-holdout missing trade slots: `{1: 7, 2: 9}`
- Pre-holdout missing FVG-to-inversion bars: `[(3, 3), (1, 2), (2, 2), (6, 2), (4, 2), (12, 1), (7, 1), (5, 1), (11, 1), (14, 1)]`

## Interpretation

- The scary raw count gap had three separate causes:
  1. research exports included `no_fill` setups,
  2. exact replay timestamps real intraday limit fills a few minutes later than the research bar timestamp,
  3. there is still a real subset of missing research trades.
- On holdout, that real subset is now much smaller than the headline `42 vs 28` made it look: the unresolved difference is `14` truly missing research fills.
- Because those unresolved holdout misses are all first-trade days, the next debug step should focus on day-level setup arming and limit-fill lifecycle on those dates, not on trade-cap sequencing.
