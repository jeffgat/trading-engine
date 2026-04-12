# CL NY HTF-LSI Parity Diff

- Objective: decompose the trade-count gap between the frozen `1m` CL HTF-LSI research branch and the execution-side exact replay prototype.
- Candidate: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`
- Exact replay window: `2016-01-01` to `2026-03-31`

## Key Findings

- Pre-holdout gap: research filled `425` trades vs exact `425`. Fuzzy same-trade matching recovered `425` overlaps, leaving `0` research-only trades and `0` exact-only trades.
- Holdout gap: research filled `45` trades vs exact `45`. Fuzzy same-trade matching recovered `45` overlaps, leaving `0` research-only trades and `0` exact-only trades.
- Pre-holdout missing-trade slots: `{}`
- Holdout missing-trade slots: `{}`

## Window Summary

| Window | Research Filled | Exact | Strict Minute Match | Fuzzy Same-Trade Match | Research Only | Exact Only |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pre-Holdout | 425 | 425 | 425 | 425 | 0 | 0 |
| Holdout | 45 | 45 | 45 | 45 | 0 | 0 |

## Holdout Shape

- Minute-shift distribution on matched holdout trades: `{0: 45}`
- Missing holdout trade days: `-`
- Missing holdout FVG-to-inversion bars: `[]`
- Missing holdout HTF level times: `[]`
- Missing holdout entry times: `[]`

## Pre-Holdout Shape

- Minute-shift distribution on matched pre-holdout trades: `{0: 425}`
- Pre-holdout research-only day count: `0`
- Pre-holdout missing trade slots: `{}`
- Pre-holdout missing FVG-to-inversion bars: `[]`
- Pre-holdout missing HTF level times: `[]`

## Interpretation


- Trade-level parity is closed. Exact replay now matches research on every filled trade across pre-holdout and holdout.
- The honest next step is no longer trade-gap debugging. It is downstream operational work: keep the frozen CL candidate as the execution-aligned restart point and validate live-feed behavior separately from this historical exact replay path.
