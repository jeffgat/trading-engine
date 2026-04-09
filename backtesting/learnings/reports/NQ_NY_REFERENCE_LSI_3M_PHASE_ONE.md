# NQ NY Reference LSI 3m Phase One

- Frozen shortlist source: [NQ_NY_REFERENCE_LSI_DISCOVERY_3M.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/NQ_NY_REFERENCE_LSI_DISCOVERY_3M.md)
- Holdout opened once for phase one: `2025-01-01` to `2026-03-24`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2024-12-31`).

## Summary

- `NQ NY reference_lsi 3m both 13:00 far gap9 inv12 rr3.0 tp0.7` (LEADER): verdict `CONDITIONAL`, OOS prop payout `79.6%`, OOS funded payout `77.1%`, holdout prop payout `0.0%`, holdout funded payout `1.6%`
- `NQ NY reference_lsi 3m both 12:00 near gap6 inv12 rr3.0 tp0.8` (CHALLENGER): verdict `CONDITIONAL`, OOS prop payout `77.0%`, OOS funded payout `69.0%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `NQ NY reference_lsi 3m both 13:00 near gap6 inv12 rr2.5 tp0.8` (CHALLENGER): verdict `CONDITIONAL`, OOS prop payout `78.1%`, OOS funded payout `64.4%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`

## Candidate Details

### NQ NY reference_lsi 3m both 13:00 far gap9 inv12 rr3.0 tp0.7

- role: `LEADER`
- verdict: `CONDITIONAL`
- config: `both 13:00 far gap9 inv12 rr3.0 tp0.7`
- discovery PSR / DSR: `0.9891` / `0.7692`
- pre-holdout structural metrics: trades `107.0`, PF `1.6112`, avgR `0.2931`, totalR `31.3595`
- stitched OOS metrics: trades `67.0`, PF `1.8766`, avgR `0.3917`, totalR `26.2462`
- OOS prop scorecard: payout `79.6%`, breach `1.0%`, EV `$15870.29`
- OOS funded scorecard: payout `77.1%`, breach `3.5%`, EV `$282.76`
- holdout metrics: trades `18.0`, PF `1.3016`, avgR `0.1812`, totalR `3.2609`
- holdout prop scorecard: payout `0.0%`, breach `23.2%`, EV `$-61.62`
- holdout funded scorecard: payout `1.6%`, breach `81.2%`, EV `$-99.74`

### NQ NY reference_lsi 3m both 12:00 near gap6 inv12 rr3.0 tp0.8

- role: `CHALLENGER`
- verdict: `CONDITIONAL`
- config: `both 12:00 near gap6 inv12 rr3.0 tp0.8`
- discovery PSR / DSR: `0.9972` / `0.8855`
- pre-holdout structural metrics: trades `116.0`, PF `1.7998`, avgR `0.2957`, totalR `34.3069`
- stitched OOS metrics: trades `78.0`, PF `1.8373`, avgR `0.3003`, totalR `23.4197`
- OOS prop scorecard: payout `77.0%`, breach `7.7%`, EV `$15342.32`
- OOS funded scorecard: payout `69.0%`, breach `15.6%`, EV `$149.78`
- holdout metrics: trades `17.0`, PF `0.5372`, avgR `-0.2509`, totalR `-4.265`
- holdout prop scorecard: payout `0.0%`, breach `81.2%`, EV `$-90.6`
- holdout funded scorecard: payout `0.0%`, breach `81.2%`, EV `$-100.0`

### NQ NY reference_lsi 3m both 13:00 near gap6 inv12 rr2.5 tp0.8

- role: `CHALLENGER`
- verdict: `CONDITIONAL`
- config: `both 13:00 near gap6 inv12 rr2.5 tp0.8`
- discovery PSR / DSR: `0.9968` / `0.881`
- pre-holdout structural metrics: trades `130.0`, PF `1.7389`, avgR `0.2689`, totalR `34.9514`
- stitched OOS metrics: trades `87.0`, PF `1.8614`, avgR `0.2936`, totalR `25.5447`
- OOS prop scorecard: payout `78.1%`, breach `6.5%`, EV `$15567.72`
- OOS funded scorecard: payout `64.4%`, breach `20.2%`, EV `$121.5`
- holdout metrics: trades `17.0`, PF `0.497`, avgR `-0.2774`, totalR `-4.715`
- holdout prop scorecard: payout `0.0%`, breach `81.2%`, EV `$-90.6`
- holdout funded scorecard: payout `0.0%`, breach `81.2%`, EV `$-100.0`
