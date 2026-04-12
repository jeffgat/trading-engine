# NQ NY HTF-LSI Phase One

- Frozen shortlist source: [NQ_NY_HTF_LSI_DISCOVERY.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/NQ_NY_HTF_LSI_DISCOVERY.md)
- Holdout opened once for phase one: `2025-04-01` to `2026-03-24`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2025-03-31`).

## Summary

- `NQ NY HTF_LSI 5m frozen balanced anchor`: verdict `STRONG`, OOS prop payout `70.9%`, OOS funded payout `52.2%`, holdout prop payout `71.2%`, holdout funded payout `71.2%`

## Candidate Details

### NQ NY HTF_LSI 5m frozen balanced anchor

- verdict: `STRONG`
- config: `long fvg_limit 08:30-15:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL20 fvgR2`
- discovery PSR / DSR: `0.9914` / `0.8092` (raw trials `144`, effective `8`)
- pre-holdout structural metrics: trades `575.0`, PF `1.2499`, avgR `0.112`, totalR `64.3713`
- stitched OOS metrics: trades `376.0`, PF `1.298`, avgR `0.1295`, totalR `48.6964`
- OOS prop scorecard: payout `70.9%`, breach `22.7%`, open `6.4%`, EV `$14108.3`, avg days `118.82`
- OOS funded scorecard: payout `52.2%`, breach `41.3%`, open `6.4%`, EV `$158.58`, avg days `81.7`
- holdout metrics: trades `46.0`, PF `1.9874`, avgR `0.3611`, totalR `16.6099`
- holdout prop scorecard: payout `71.2%`, breach `3.3%`, open `25.5%`, EV `$14196.73`, avg days `78.91`
- holdout funded scorecard: payout `71.2%`, breach `3.3%`, open `25.5%`, EV `$78.68`, avg days `77.72`
- OOS cohort EV: prop `10/25/50 = $141083.0 / $352707.5 / $705415.0`, funded `10/25/50 = $1585.8 / $3964.5 / $7929.0`
- holdout cohort EV: prop `10/25/50 = $141967.3 / $354918.25 / $709836.5`, funded `10/25/50 = $786.8 / $1967.0 / $3934.0`
