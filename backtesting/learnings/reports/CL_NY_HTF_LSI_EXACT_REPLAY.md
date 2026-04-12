# CL NY HTF-LSI Exact Replay

- Objective: replay the frozen `1m` CL HTF-LSI lead through the live `LSIEngine` state machine using `1m + 1s` local parquet data.
- Scope note: this is an execution-side replay prototype for the 1m branch. The normal live feed still aggregates signals to 5m, so this is not full production-feed parity yet.
- Candidate: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`
- Replay window: `2016-01-01` to `2026-03-31`

## Candidate

- Direction / entry: `long / close`
- Windows: `sweep 08:30-15:00`, `entry 08:30-14:30`, `flat 15:50-16:00`
- Structure: `htf60 n3 cap2`
- Risk shape: `rr 3.0`, `tp1 0.6`, `gap 3.0`, `atr 20`
- FVG / lag: `left 100`, `right 10`, `lag 15`

## Raw Metrics

| Window | Exact Trades | Exact PF | Exact Avg R | Exact Total R | Exact Max DD | Exact Calmar | Research Trades | Research PF | Research Avg R | Delta Trades | Delta PF | Delta Avg R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pre-Holdout | 425 | 1.233 | 0.131 | 55.697 | -21.485R | 2.592 | 425 | 1.208 | 0.120 | 0 | 0.025 | 0.011 |
| Holdout | 45 | 1.603 | 0.313 | 14.100 | -8.063R | 1.749 | 45 | 1.609 | 0.314 | 0 | -0.007 | -0.001 |

## Exact Replay Scorecards

- Pre-holdout prop payout: `60.2%` | funded payout: `50.0%` | funded EV/start: `$154.5`
- Holdout prop payout: `36.2%` | funded payout: `34.6%` | funded EV/start: `$155.67`

## Full Replay Snapshot

- Trades: `470`
- PF: `1.266`
- Avg R: `0.149`
- Total R: `69.797`
- Max DD: `-21.485R`
- Calmar: `3.249`
