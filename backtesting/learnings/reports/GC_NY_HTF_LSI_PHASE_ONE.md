# GC NY HTF-LSI Phase One

- Frozen shortlist source: [GC_NY_HTF_LSI_STITCHED_FOLLOWUP.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/GC_NY_HTF_LSI_STITCHED_FOLLOWUP.md)
- Holdout opened once for phase one: `2025-04-01` to `2026-03-30`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2025-03-31`).
- Bailey-style PSR / DSR was not rerun on this GC packet; phase-one verdicts here are downstream scorecard reads on a frozen pre-holdout shortlist.

## Summary

- `GC NY HTF_LSI stageE lag30 GC NY HTF_LSI stageD 3m end11:00 atr14 gap3.0 rr3.5 tp0.5 n5 L60 R15`: verdict `NO-GO`, OOS prop payout `59.4%`, OOS funded payout `45.1%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `GC NY HTF_LSI stageE lag0 GC NY HTF_LSI stageD 3m end10:30 atr14 gap3.0 rr3.5 tp0.5 n5 L60 R15`: verdict `NO-GO`, OOS prop payout `52.8%`, OOS funded payout `43.8%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `GC NY HTF_LSI stageE lag0 GC NY HTF_LSI stageD 3m end10:30 atr14 gap3.0 rr3.5 tp0.5 n5 L60 R9`: verdict `NO-GO`, OOS prop payout `58.9%`, OOS funded payout `41.0%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `GC NY HTF_LSI stageB 3m cap2 GC NY HTF_LSI stageA 3m htf60 n5 short fvg_limit 08:30-10:30`: verdict `NO-GO`, OOS prop payout `57.0%`, OOS funded payout `39.2%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `GC NY HTF_LSI stageE lag24 GC NY HTF_LSI stageD 3m end11:00 atr14 gap3.0 rr3.5 tp0.5 n5 L60 R15`: verdict `NO-GO`, OOS prop payout `58.6%`, OOS funded payout `43.9%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`

## Candidate Details

### GC NY HTF_LSI stageE lag30 GC NY HTF_LSI stageD 3m end11:00 atr14 gap3.0 rr3.5 tp0.5 n5 L60 R15

- verdict: `NO-GO`
- candidate_id: `late_lag30_1100_r15`
- config: `short fvg_limit 08:30-11:00 rr3.5 tp0.5 gap3.0 htf60 n5 cap2 fvgL20 fvgR5 lag30`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `324.0`, PF `1.2353`, avgR `0.1302`, totalR `42.1737`
- stitched OOS metrics: trades `220.0`, PF `1.2656`, avgR `0.1493`, totalR `32.8535`
- OOS prop scorecard: payout `59.4%`, breach `32.5%`, open `8.1%`, EV `$11808.11`, avg days `134.84`
- OOS funded scorecard: payout `45.1%`, breach `46.8%`, open `8.1%`, EV `$88.32`, avg days `91.17`
- holdout metrics: trades `31.0`, PF `0.2344`, avgR `-0.573`, totalR `-17.7635`
- holdout prop scorecard: payout `0.0%`, breach `78.1%`, open `21.9%`, EV `$-89.07`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `87.8%`, open `12.2%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $118081.1 / $295202.75 / $590405.5`, funded `10/25/50 = $883.2 / $2208.0 / $4416.0`
- holdout cohort EV: prop `10/25/50 = $-890.7 / $-2226.75 / $-4453.5`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### GC NY HTF_LSI stageE lag0 GC NY HTF_LSI stageD 3m end10:30 atr14 gap3.0 rr3.5 tp0.5 n5 L60 R15

- verdict: `NO-GO`
- candidate_id: `quality_lag0_1030_r15`
- config: `short fvg_limit 08:30-10:30 rr3.5 tp0.5 gap3.0 htf60 n5 cap2 fvgL20 fvgR5 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `301.0`, PF `1.2489`, avgR `0.133`, totalR `40.0322`
- stitched OOS metrics: trades `208.0`, PF `1.2382`, avgR `0.1289`, totalR `26.8121`
- OOS prop scorecard: payout `52.8%`, breach `39.1%`, open `8.1%`, EV `$10486.59`, avg days `154.1`
- OOS funded scorecard: payout `43.8%`, breach `48.7%`, open `7.5%`, EV `$74.53`, avg days `115.1`
- holdout metrics: trades `28.0`, PF `0.2914`, avgR `-0.5046`, totalR `-14.1301`
- holdout prop scorecard: payout `0.0%`, breach `70.4%`, open `29.6%`, EV `$-85.21`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `72.0%`, open `28.0%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $104865.9 / $262164.75 / $524329.5`, funded `10/25/50 = $745.3 / $1863.25 / $3726.5`
- holdout cohort EV: prop `10/25/50 = $-852.1 / $-2130.25 / $-4260.5`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### GC NY HTF_LSI stageE lag0 GC NY HTF_LSI stageD 3m end10:30 atr14 gap3.0 rr3.5 tp0.5 n5 L60 R9

- verdict: `NO-GO`
- candidate_id: `balanced_lag0_1030_r9`
- config: `short fvg_limit 08:30-10:30 rr3.5 tp0.5 gap3.0 htf60 n5 cap2 fvgL20 fvgR3 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `256.0`, PF `1.3116`, avgR `0.1573`, totalR `40.2565`
- stitched OOS metrics: trades `178.0`, PF `1.2766`, avgR `0.1404`, totalR `24.9997`
- OOS prop scorecard: payout `58.9%`, breach `30.4%`, open `10.8%`, EV `$11706.18`, avg days `193.8`
- OOS funded scorecard: payout `41.0%`, breach `51.5%`, open `7.5%`, EV `$66.74`, avg days `123.71`
- holdout metrics: trades `26.0`, PF `0.3262`, avgR `-0.4665`, totalR `-12.1301`
- holdout prop scorecard: payout `0.0%`, breach `70.4%`, open `29.6%`, EV `$-85.21`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `72.0%`, open `28.0%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $117061.8 / $292654.5 / $585309.0`, funded `10/25/50 = $667.4 / $1668.5 / $3337.0`
- holdout cohort EV: prop `10/25/50 = $-852.1 / $-2130.25 / $-4260.5`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### GC NY HTF_LSI stageB 3m cap2 GC NY HTF_LSI stageA 3m htf60 n5 short fvg_limit 08:30-10:30

- verdict: `NO-GO`
- candidate_id: `control_stage_b_1030`
- config: `short fvg_limit 08:30-10:30 rr3.0 tp0.6 gap3.0 htf60 n5 cap2 fvgL33 fvgR3 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `257.0`, PF `1.2821`, avgR `0.143`, totalR `36.7419`
- stitched OOS metrics: trades `179.0`, PF `1.2456`, avgR `0.1254`, totalR `22.4391`
- OOS prop scorecard: payout `57.0%`, breach `32.0%`, open `11.0%`, EV `$11344.93`, avg days `179.18`
- OOS funded scorecard: payout `39.2%`, breach `53.1%`, open `7.7%`, EV `$62.94`, avg days `114.03`
- holdout metrics: trades `26.0`, PF `0.3301`, avgR `-0.4639`, totalR `-12.0601`
- holdout prop scorecard: payout `0.0%`, breach `70.4%`, open `29.6%`, EV `$-85.21`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `72.0%`, open `28.0%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $113449.3 / $283623.25 / $567246.5`, funded `10/25/50 = $629.4 / $1573.5 / $3147.0`
- holdout cohort EV: prop `10/25/50 = $-852.1 / $-2130.25 / $-4260.5`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### GC NY HTF_LSI stageE lag24 GC NY HTF_LSI stageD 3m end11:00 atr14 gap3.0 rr3.5 tp0.5 n5 L60 R15

- verdict: `NO-GO`
- candidate_id: `late_lag24_1100_r15`
- config: `short fvg_limit 08:30-11:00 rr3.5 tp0.5 gap3.0 htf60 n5 cap2 fvgL20 fvgR5 lag24`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `309.0`, PF `1.2159`, avgR `0.1222`, totalR `37.7527`
- stitched OOS metrics: trades `214.0`, PF `1.235`, avgR `0.1349`, totalR `28.8792`
- OOS prop scorecard: payout `58.6%`, breach `33.3%`, open `8.1%`, EV `$11653.24`, avg days `132.3`
- OOS funded scorecard: payout `43.9%`, breach `47.9%`, open `8.1%`, EV `$51.21`, avg days `92.99`
- holdout metrics: trades `29.0`, PF `0.2528`, avgR `-0.5436`, totalR `-15.7635`
- holdout prop scorecard: payout `0.0%`, breach `78.1%`, open `21.9%`, EV `$-89.07`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `87.8%`, open `12.2%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $116532.4 / $291331.0 / $582662.0`, funded `10/25/50 = $512.1 / $1280.25 / $2560.5`
- holdout cohort EV: prop `10/25/50 = $-890.7 / $-2226.75 / $-4453.5`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`
