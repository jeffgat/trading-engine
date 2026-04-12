# CL NY HTF-LSI Phase One

- Frozen shortlist source: [CL_NY_HTF_LSI_STITCHED_FOLLOWUP.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/CL_NY_HTF_LSI_STITCHED_FOLLOWUP.md)
- Holdout opened once for phase one: `2025-04-01` to `2026-03-31`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2025-03-31`).
- Bailey-style PSR / DSR was not rerun on this CL packet; phase-one verdicts here are downstream scorecard reads on a frozen pre-holdout shortlist.

## Summary

- `CL NY HTF_LSI stageB 1m cap2 CL NY HTF_LSI stageA 1m htf60 n3 long close 08:30-14:00`: verdict `CONDITIONAL`, OOS prop payout `58.2%`, OOS funded payout `45.1%`, holdout prop payout `29.5%`, holdout funded payout `24.7%`
- `CL NY HTF_LSI oat htf_n 7`: verdict `CONDITIONAL`, OOS prop payout `60.1%`, OOS funded payout `50.6%`, holdout prop payout `9.6%`, holdout funded payout `22.4%`
- `CL NY HTF_LSI oat entry_end 10:30`: verdict `NO-GO`, OOS prop payout `48.4%`, OOS funded payout `32.6%`, holdout prop payout `13.8%`, holdout funded payout `13.8%`
- `CL NY HTF_LSI stageB 1m cap2 CL NY HTF_LSI stageA 1m htf30 n5 long close 08:30-14:00`: verdict `NO-GO`, OOS prop payout `42.0%`, OOS funded payout `33.6%`, holdout prop payout `24.7%`, holdout funded payout `22.1%`
- `CL NY HTF_LSI stageB 1m cap2 CL NY HTF_LSI stageA 1m htf30 n5 long close 08:30-13:00`: verdict `NO-GO`, OOS prop payout `49.8%`, OOS funded payout `34.1%`, holdout prop payout `31.4%`, holdout funded payout `29.8%`

## Candidate Details

### CL NY HTF_LSI stageB 1m cap2 CL NY HTF_LSI stageA 1m htf60 n3 long close 08:30-14:00

- verdict: `CONDITIONAL`
- candidate_id: `structural_alt_htf60_end14`
- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `840.0`, PF `1.1467`, avgR `0.078`, totalR `65.4954`
- stitched OOS metrics: trades `573.0`, PF `1.2083`, avgR `0.1093`, totalR `62.6414`
- OOS prop scorecard: payout `58.2%`, breach `35.9%`, open `5.9%`, EV `$11569.54`, avg days `61.52`
- OOS funded scorecard: payout `45.1%`, breach `49.3%`, open `5.6%`, EV `$116.23`, avg days `47.1`
- holdout metrics: trades `95.0`, PF `1.1017`, avgR `0.0488`, totalR `4.6377`
- holdout prop scorecard: payout `29.5%`, breach `49.4%`, open `21.1%`, EV `$5822.76`, avg days `31.35`
- holdout funded scorecard: payout `24.7%`, breach `56.4%`, open `18.9%`, EV `$34.77`, avg days `24.26`
- OOS cohort EV: prop `10/25/50 = $115695.4 / $289238.5 / $578477.0`, funded `10/25/50 = $1162.3 / $2905.75 / $5811.5`
- holdout cohort EV: prop `10/25/50 = $58227.6 / $145569.0 / $291138.0`, funded `10/25/50 = $347.7 / $869.25 / $1738.5`

### CL NY HTF_LSI oat htf_n 7

- verdict: `CONDITIONAL`
- candidate_id: `htf_n7_end14`
- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf30 n7 cap2 fvgL100 fvgR10 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `826.0`, PF `1.1499`, avgR `0.0805`, totalR `66.4896`
- stitched OOS metrics: trades `558.0`, PF `1.2225`, avgR `0.1172`, totalR `65.3938`
- OOS prop scorecard: payout `60.1%`, breach `30.6%`, open `9.3%`, EV `$11953.24`, avg days `62.23`
- OOS funded scorecard: payout `50.6%`, breach `43.1%`, open `6.3%`, EV `$104.04`, avg days `53.65`
- holdout metrics: trades `98.0`, PF `0.9774`, avgR `-0.0159`, totalR `-1.5537`
- holdout prop scorecard: payout `9.6%`, breach `68.6%`, open `21.8%`, EV `$1838.78`, avg days `28.23`
- holdout funded scorecard: payout `22.4%`, breach `56.1%`, open `21.5%`, EV `$6.74`, avg days `46.14`
- OOS cohort EV: prop `10/25/50 = $119532.4 / $298831.0 / $597662.0`, funded `10/25/50 = $1040.4 / $2601.0 / $5202.0`
- holdout cohort EV: prop `10/25/50 = $18387.8 / $45969.5 / $91939.0`, funded `10/25/50 = $67.4 / $168.5 / $337.0`

### CL NY HTF_LSI oat entry_end 10:30

- verdict: `NO-GO`
- candidate_id: `early_end1030`
- config: `long close 08:30-10:30 rr3.0 tp0.6 gap3.0 htf30 n5 cap2 fvgL100 fvgR10 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `523.0`, PF `1.1676`, avgR `0.0939`, totalR `49.1293`
- stitched OOS metrics: trades `365.0`, PF `1.1571`, avgR `0.0891`, totalR `32.5219`
- OOS prop scorecard: payout `48.4%`, breach `43.4%`, open `8.2%`, EV `$9609.04`, avg days `84.91`
- OOS funded scorecard: payout `32.6%`, breach `61.4%`, open `6.0%`, EV `$37.45`, avg days `54.44`
- holdout metrics: trades `61.0`, PF `0.9377`, avgR `-0.0322`, totalR `-1.9663`
- holdout prop scorecard: payout `13.8%`, breach `45.8%`, open `40.4%`, EV `$2683.49`, avg days `31.72`
- holdout funded scorecard: payout `13.8%`, breach `65.7%`, open `20.5%`, EV `$-45.01`, avg days `30.49`
- OOS cohort EV: prop `10/25/50 = $96090.4 / $240226.0 / $480452.0`, funded `10/25/50 = $374.5 / $936.25 / $1872.5`
- holdout cohort EV: prop `10/25/50 = $26834.9 / $67087.25 / $134174.5`, funded `10/25/50 = $-450.1 / $-1125.25 / $-2250.5`

### CL NY HTF_LSI stageB 1m cap2 CL NY HTF_LSI stageA 1m htf30 n5 long close 08:30-14:00

- verdict: `NO-GO`
- candidate_id: `control_stage_b_end14`
- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf30 n5 cap2 fvgL100 fvgR10 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `943.0`, PF `1.1261`, avgR `0.0671`, totalR `63.312`
- stitched OOS metrics: trades `633.0`, PF `1.1049`, avgR `0.0574`, totalR `36.3173`
- OOS prop scorecard: payout `42.0%`, breach `51.3%`, open `6.7%`, EV `$8317.74`, avg days `59.6`
- OOS funded scorecard: payout `33.6%`, breach `60.6%`, open `5.8%`, EV `$26.87`, avg days `46.15`
- holdout metrics: trades `108.0`, PF `0.9829`, avgR `-0.0139`, totalR `-1.5021`
- holdout prop scorecard: payout `24.7%`, breach `61.2%`, open `14.1%`, EV `$4855.29`, avg days `51.32`
- holdout funded scorecard: payout `22.1%`, breach `68.9%`, open `9.0%`, EV `$4.63`, avg days `43.87`
- OOS cohort EV: prop `10/25/50 = $83177.4 / $207943.5 / $415887.0`, funded `10/25/50 = $268.7 / $671.75 / $1343.5`
- holdout cohort EV: prop `10/25/50 = $48552.9 / $121382.25 / $242764.5`, funded `10/25/50 = $46.3 / $115.75 / $231.5`

### CL NY HTF_LSI stageB 1m cap2 CL NY HTF_LSI stageA 1m htf30 n5 long close 08:30-13:00

- verdict: `NO-GO`
- candidate_id: `control_stage_b_end13`
- config: `long close 08:30-13:00 rr3.0 tp0.6 gap3.0 htf30 n5 cap2 fvgL100 fvgR10 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `863.0`, PF `1.1559`, avgR `0.0832`, totalR `71.7913`
- stitched OOS metrics: trades `579.0`, PF `1.1241`, avgR `0.0682`, totalR `39.463`
- OOS prop scorecard: payout `49.8%`, breach `43.6%`, open `6.6%`, EV `$9887.02`, avg days `69.83`
- OOS funded scorecard: payout `34.1%`, breach `60.1%`, open `5.8%`, EV `$11.92`, avg days `44.85`
- holdout metrics: trades `96.0`, PF `1.1188`, avgR `0.0575`, totalR `5.5163`
- holdout prop scorecard: payout `31.4%`, breach `40.4%`, open `28.2%`, EV `$6211.86`, avg days `42.91`
- holdout funded scorecard: payout `29.8%`, breach `60.6%`, open `9.6%`, EV `$-2.56`, avg days `40.19`
- OOS cohort EV: prop `10/25/50 = $98870.2 / $247175.5 / $494351.0`, funded `10/25/50 = $119.2 / $298.0 / $596.0`
- holdout cohort EV: prop `10/25/50 = $62118.6 / $155296.5 / $310593.0`, funded `10/25/50 = $-25.6 / $-64.0 / $-128.0`
