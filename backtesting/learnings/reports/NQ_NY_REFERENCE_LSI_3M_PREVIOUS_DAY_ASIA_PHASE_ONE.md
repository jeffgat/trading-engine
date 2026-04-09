# NQ NY Reference LSI 3m Previous Day + Asia Phase One

- Frozen shortlist source: [NQ_NY_REFERENCE_LSI_DISCOVERY_3M_PREVIOUS_DAY_ASIA.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/NQ_NY_REFERENCE_LSI_DISCOVERY_3M_PREVIOUS_DAY_ASIA.md)
- Active reference levels: `previous_day_high, previous_day_low, asia_high, asia_low`
- Holdout opened once for phase one: `2025-01-01` to `2026-03-24`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2024-12-31`).

## Summary

- `NQ NY reference_lsi 3m previous_day_asia both 12:00 near gap9 inv12 rr3.0 tp0.8` (LEADER): verdict `CONDITIONAL`, OOS prop payout `82.9%`, OOS funded payout `77.1%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `NQ NY reference_lsi 3m previous_day_asia both 13:00 near gap9 inv12 rr2.5 tp0.8` (CHALLENGER): verdict `CONDITIONAL`, OOS prop payout `81.8%`, OOS funded payout `75.0%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `NQ NY reference_lsi 3m previous_day_asia both 14:00 near gap6 inv12 rr2.5 tp0.8` (CHALLENGER): verdict `CONDITIONAL`, OOS prop payout `78.5%`, OOS funded payout `64.7%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`

## Candidate Details

### NQ NY reference_lsi 3m previous_day_asia both 12:00 near gap9 inv12 rr3.0 tp0.8

- role: `LEADER`
- verdict: `CONDITIONAL`
- config: `both 12:00 near gap9 inv12 rr3.0 tp0.8`
- discovery PSR / DSR: `0.9961` / `0.8198`
- pre-holdout structural metrics: trades `101.0`, PF `1.8329`, avgR `0.3016`, totalR `30.4606`
- stitched OOS metrics: trades `68.0`, PF `1.9874`, avgR `0.3248`, totalR `22.0873`
- OOS prop scorecard: payout `82.9%`, breach `1.1%`, EV `$16534.05`
- OOS funded scorecard: payout `77.1%`, breach `6.9%`, EV `$270.0`
- holdout metrics: trades `15.0`, PF `0.7802`, avgR `-0.0865`, totalR `-1.2981`
- holdout prop scorecard: payout `0.0%`, breach `64.2%`, EV `$-82.11`
- holdout funded scorecard: payout `0.0%`, breach `79.6%`, EV `$-100.0`

### NQ NY reference_lsi 3m previous_day_asia both 13:00 near gap9 inv12 rr2.5 tp0.8

- role: `CHALLENGER`
- verdict: `CONDITIONAL`
- config: `both 13:00 near gap9 inv12 rr2.5 tp0.8`
- discovery PSR / DSR: `0.9961` / `0.828`
- pre-holdout structural metrics: trades `113.0`, PF `1.8014`, avgR `0.2747`, totalR `31.0373`
- stitched OOS metrics: trades `75.0`, PF `2.0386`, avgR `0.3189`, totalR `23.9207`
- OOS prop scorecard: payout `81.8%`, breach `2.1%`, EV `$16319.38`
- OOS funded scorecard: payout `75.0%`, breach `8.9%`, EV `$215.9`
- holdout metrics: trades `15.0`, PF `0.7241`, avgR `-0.1197`, totalR `-1.7958`
- holdout prop scorecard: payout `0.0%`, breach `64.2%`, EV `$-82.11`
- holdout funded scorecard: payout `0.0%`, breach `79.6%`, EV `$-100.0`

### NQ NY reference_lsi 3m previous_day_asia both 14:00 near gap6 inv12 rr2.5 tp0.8

- role: `CHALLENGER`
- verdict: `CONDITIONAL`
- config: `both 14:00 near gap6 inv12 rr2.5 tp0.8`
- discovery PSR / DSR: `0.9935` / `0.7771`
- pre-holdout structural metrics: trades `101.0`, PF `1.7967`, avgR `0.2742`, totalR `27.697`
- stitched OOS metrics: trades `69.0`, PF `1.9382`, avgR `0.3007`, totalR `20.7515`
- OOS prop scorecard: payout `78.5%`, breach `5.5%`, EV `$15653.91`
- OOS funded scorecard: payout `64.7%`, breach `19.3%`, EV `$190.54`
- holdout metrics: trades `13.0`, PF `0.3814`, avgR `-0.3564`, totalR `-4.633`
- holdout prop scorecard: payout `0.0%`, breach `64.2%`, EV `$-82.11`
- holdout funded scorecard: payout `0.0%`, breach `79.6%`, EV `$-100.0`
