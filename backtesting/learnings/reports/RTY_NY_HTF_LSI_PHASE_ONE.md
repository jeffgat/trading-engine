# RTY NY HTF-LSI Phase One

- Frozen shortlist source: [RTY_NY_HTF_LSI_STITCHED_FOLLOWUP.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/RTY_NY_HTF_LSI_STITCHED_FOLLOWUP.md)
- Holdout opened once for phase one: `2025-04-01` to `2026-03-31`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2025-03-31`).
- Bailey-style PSR / DSR was not rerun on this RTY packet; phase-one verdicts here are downstream scorecard reads on a frozen pre-holdout shortlist.

## Summary

- `RTY NY HTF_LSI stageE lag30 RTY NY HTF_LSI stageD 5m end14:00 atr10 gap2.0 rr4.0 tp0.5 n3 L60 R10`: verdict `NO-GO`, OOS prop payout `49.2%`, OOS funded payout `42.6%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `RTY NY HTF_LSI stageE lag20 RTY NY HTF_LSI stageD 5m end14:00 atr14 gap2.0 rr4.0 tp0.5 n3 L100 R10`: verdict `NO-GO`, OOS prop payout `47.8%`, OOS funded payout `42.3%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `RTY NY HTF_LSI stageB 5m cap2 RTY NY HTF_LSI stageA 5m htf90 n3 short fvg_limit 08:30-15:00`: verdict `NO-GO`, OOS prop payout `56.4%`, OOS funded payout `47.9%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `RTY NY HTF_LSI stageE lag12 RTY NY HTF_LSI stageD 5m end15:00 atr14 gap2.0 rr3.0 tp0.4 n5 L60 R5`: verdict `NO-GO`, OOS prop payout `66.3%`, OOS funded payout `35.0%`, holdout prop payout `1.9%`, holdout funded payout `1.9%`

## Candidate Details

### RTY NY HTF_LSI stageE lag30 RTY NY HTF_LSI stageD 5m end14:00 atr10 gap2.0 rr4.0 tp0.5 n3 L60 R10

- verdict: `NO-GO`
- candidate_id: `rr4_lag30_atr10_l60`
- config: `short fvg_limit 08:30-14:00 rr4.0 tp0.5 gap2.0 htf90 n3 cap2 fvgL12 fvgR2 lag30`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `449.0`, PF `1.1557`, avgR `0.0817`, totalR `36.6664`
- stitched OOS metrics: trades `343.0`, PF `1.2206`, avgR `0.1114`, totalR `38.2212`
- OOS prop scorecard: payout `49.2%`, breach `40.4%`, open `10.4%`, EV `$9770.41`, avg days `90.1`
- OOS funded scorecard: payout `42.6%`, breach `47.7%`, open `9.8%`, EV `$107.82`, avg days `68.0`
- holdout metrics: trades `55.0`, PF `0.5074`, avgR `-0.29`, totalR `-15.9504`
- holdout prop scorecard: payout `0.0%`, breach `79.8%`, open `20.2%`, EV `$-89.9`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `79.8%`, open `20.2%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $97704.1 / $244260.25 / $488520.5`, funded `10/25/50 = $1078.2 / $2695.5 / $5391.0`
- holdout cohort EV: prop `10/25/50 = $-899.0 / $-2247.5 / $-4495.0`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### RTY NY HTF_LSI stageE lag20 RTY NY HTF_LSI stageD 5m end14:00 atr14 gap2.0 rr4.0 tp0.5 n3 L100 R10

- verdict: `NO-GO`
- candidate_id: `rr4_lag20_atr14_l100`
- config: `short fvg_limit 08:30-14:00 rr4.0 tp0.5 gap2.0 htf90 n3 cap2 fvgL20 fvgR2 lag20`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `406.0`, PF `1.1675`, avgR `0.0904`, totalR `36.7096`
- stitched OOS metrics: trades `316.0`, PF `1.2513`, avgR `0.1307`, totalR `41.3026`
- OOS prop scorecard: payout `47.8%`, breach `41.9%`, open `10.4%`, EV `$9481.77`, avg days `100.59`
- OOS funded scorecard: payout `42.3%`, breach `47.9%`, open `9.8%`, EV `$105.12`, avg days `65.5`
- holdout metrics: trades `54.0`, PF `0.4821`, avgR `-0.3182`, totalR `-17.1825`
- holdout prop scorecard: payout `0.0%`, breach `84.9%`, open `15.1%`, EV `$-92.47`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `94.2%`, open `5.8%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $94817.7 / $237044.25 / $474088.5`, funded `10/25/50 = $1051.2 / $2628.0 / $5256.0`
- holdout cohort EV: prop `10/25/50 = $-924.7 / $-2311.75 / $-4623.5`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### RTY NY HTF_LSI stageB 5m cap2 RTY NY HTF_LSI stageA 5m htf90 n3 short fvg_limit 08:30-15:00

- verdict: `NO-GO`
- candidate_id: `control_stage_b_end15`
- config: `short fvg_limit 08:30-15:00 rr3.0 tp0.6 gap3.0 htf90 n3 cap2 fvgL20 fvgR2 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `414.0`, PF `1.1791`, avgR `0.086`, totalR `35.5982`
- stitched OOS metrics: trades `318.0`, PF `1.2563`, avgR `0.116`, totalR `36.8783`
- OOS prop scorecard: payout `56.4%`, breach `35.5%`, open `8.1%`, EV `$11212.47`, avg days `125.04`
- OOS funded scorecard: payout `47.9%`, breach `44.0%`, open `8.1%`, EV `$100.37`, avg days `100.81`
- holdout metrics: trades `48.0`, PF `0.4716`, avgR `-0.2675`, totalR `-12.8417`
- holdout prop scorecard: payout `0.0%`, breach `77.9%`, open `22.1%`, EV `$-88.94`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `77.9%`, open `22.1%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $112124.7 / $280311.75 / $560623.5`, funded `10/25/50 = $1003.7 / $2509.25 / $5018.5`
- holdout cohort EV: prop `10/25/50 = $-889.4 / $-2223.5 / $-4447.0`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### RTY NY HTF_LSI stageE lag12 RTY NY HTF_LSI stageD 5m end15:00 atr14 gap2.0 rr3.0 tp0.4 n5 L60 R5

- verdict: `NO-GO`
- candidate_id: `quality_lag12_n5`
- config: `short fvg_limit 08:30-15:00 rr3.0 tp0.4 gap2.0 htf90 n5 cap2 fvgL12 fvgR1 lag12`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `278.0`, PF `1.223`, avgR `0.1083`, totalR `30.1116`
- stitched OOS metrics: trades `216.0`, PF `1.2279`, avgR `0.1077`, totalR `23.2658`
- OOS prop scorecard: payout `66.3%`, breach `22.8%`, open `10.8%`, EV `$13203.37`, avg days `191.78`
- OOS funded scorecard: payout `35.0%`, breach `54.1%`, open `10.8%`, EV `$50.16`, avg days `98.15`
- holdout metrics: trades `38.0`, PF `0.5838`, avgR `-0.2289`, totalR `-8.6981`
- holdout prop scorecard: payout `1.9%`, breach `76.0%`, open `22.1%`, EV `$296.63`, avg days `115.83`
- holdout funded scorecard: payout `1.9%`, breach `76.0%`, open `22.1%`, EV `$-97.82`, avg days `115.83`
- OOS cohort EV: prop `10/25/50 = $132033.7 / $330084.25 / $660168.5`, funded `10/25/50 = $501.6 / $1254.0 / $2508.0`
- holdout cohort EV: prop `10/25/50 = $2966.3 / $7415.75 / $14831.5`, funded `10/25/50 = $-978.2 / $-2445.5 / $-4891.0`
