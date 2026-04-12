# ES NY HTF-LSI Phase One

- Frozen shortlist source: [ES_NY_HTF_LSI_STITCHED_FOLLOWUP.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/ES_NY_HTF_LSI_STITCHED_FOLLOWUP.md)
- Holdout opened once for phase one: `2025-04-01` to `2026-03-24`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2025-03-31`).
- Bailey-style PSR / DSR was not rerun on this ES packet; phase-one verdicts here are downstream scorecard reads on a frozen pre-holdout shortlist.

## Summary

- `ES NY HTF_LSI stageE lag0 ES NY HTF_LSI stageD 3m end14:00 atr14 gap3.0 rr2.5 tp0.5 n3 L60 R9`: verdict `CONDITIONAL`, OOS prop payout `63.7%`, OOS funded payout `42.8%`, holdout prop payout `21.9%`, holdout funded payout `21.9%`
- `ES NY HTF_LSI stageE lag24 ES NY HTF_LSI stageD 3m end14:00 atr14 gap3.0 rr2.5 tp0.5 n3 L60 R9`: verdict `CONDITIONAL`, OOS prop payout `60.0%`, OOS funded payout `47.9%`, holdout prop payout `5.2%`, holdout funded payout `5.2%`
- `ES NY HTF_LSI stageB 3m cap2 ES NY HTF_LSI stageA 3m htf90 n3 long fvg_limit 08:30-14:00`: verdict `CONDITIONAL`, OOS prop payout `48.2%`, OOS funded payout `39.0%`, holdout prop payout `12.4%`, holdout funded payout `12.4%`

## Candidate Details

### ES NY HTF_LSI stageE lag0 ES NY HTF_LSI stageD 3m end14:00 atr14 gap3.0 rr2.5 tp0.5 n3 L60 R9

- verdict: `CONDITIONAL`
- candidate_id: `balanced_lag0_gap3`
- config: `long fvg_limit 08:30-14:00 rr2.5 tp0.5 gap3.0 htf90 n3 cap2 fvgL20 fvgR3 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `507.0`, PF `1.1598`, avgR `0.0664`, totalR `33.6595`
- stitched OOS metrics: trades `348.0`, PF `1.2429`, avgR `0.0973`, totalR `33.8587`
- OOS prop scorecard: payout `63.7%`, breach `29.8%`, open `6.5%`, EV `$12685.76`, avg days `167.72`
- OOS funded scorecard: payout `42.8%`, breach `52.1%`, open `5.1%`, EV `$62.67`, avg days `89.47`
- holdout metrics: trades `47.0`, PF `0.9176`, avgR `-0.0461`, totalR `-2.1677`
- holdout prop scorecard: payout `21.9%`, breach `26.5%`, open `51.6%`, EV `$4315.85`, avg days `100.79`
- holdout funded scorecard: payout `21.9%`, breach `32.0%`, open `46.1%`, EV `$-38.76`, avg days `100.79`
- OOS cohort EV: prop `10/25/50 = $126857.6 / $317144.0 / $634288.0`, funded `10/25/50 = $626.7 / $1566.75 / $3133.5`
- holdout cohort EV: prop `10/25/50 = $43158.5 / $107896.25 / $215792.5`, funded `10/25/50 = $-387.6 / $-969.0 / $-1938.0`

### ES NY HTF_LSI stageE lag24 ES NY HTF_LSI stageD 3m end14:00 atr14 gap3.0 rr2.5 tp0.5 n3 L60 R9

- verdict: `CONDITIONAL`
- candidate_id: `late_lag24_gap3`
- config: `long fvg_limit 08:30-14:00 rr2.5 tp0.5 gap3.0 htf90 n3 cap2 fvgL20 fvgR3 lag24`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `374.0`, PF `1.1337`, avgR `0.0634`, totalR `23.6937`
- stitched OOS metrics: trades `257.0`, PF `1.2203`, avgR `0.1017`, totalR `26.1339`
- OOS prop scorecard: payout `60.0%`, breach `28.4%`, open `11.6%`, EV `$11935.81`, avg days `180.72`
- OOS funded scorecard: payout `47.9%`, breach `46.5%`, open `5.5%`, EV `$46.48`, avg days `124.65`
- holdout metrics: trades `42.0`, PF `0.8308`, avgR `-0.0978`, totalR `-4.1059`
- holdout prop scorecard: payout `5.2%`, breach `35.3%`, open `59.5%`, EV `$978.1`, avg days `83.31`
- holdout funded scorecard: payout `5.2%`, breach `48.7%`, open `46.1%`, EV `$-96.0`, avg days `83.31`
- OOS cohort EV: prop `10/25/50 = $119358.1 / $298395.25 / $596790.5`, funded `10/25/50 = $464.8 / $1162.0 / $2324.0`
- holdout cohort EV: prop `10/25/50 = $9781.0 / $24452.5 / $48905.0`, funded `10/25/50 = $-960.0 / $-2400.0 / $-4800.0`

### ES NY HTF_LSI stageB 3m cap2 ES NY HTF_LSI stageA 3m htf90 n3 long fvg_limit 08:30-14:00

- verdict: `CONDITIONAL`
- candidate_id: `control_stage_b`
- config: `long fvg_limit 08:30-14:00 rr3.0 tp0.6 gap3.0 htf90 n3 cap2 fvgL33 fvgR3 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `509.0`, PF `1.1432`, avgR `0.067`, totalR `34.127`
- stitched OOS metrics: trades `350.0`, PF `1.2532`, avgR `0.115`, totalR `40.2635`
- OOS prop scorecard: payout `48.2%`, breach `45.6%`, open `6.2%`, EV `$9572.44`, avg days `84.13`
- OOS funded scorecard: payout `39.0%`, breach `55.9%`, open `5.1%`, EV `$72.96`, avg days `60.15`
- holdout metrics: trades `46.0`, PF `0.8274`, avgR `-0.0971`, totalR `-4.4682`
- holdout prop scorecard: payout `12.4%`, breach `38.2%`, open `49.4%`, EV `$2414.54`, avg days `88.84`
- holdout funded scorecard: payout `12.4%`, breach `60.1%`, open `27.5%`, EV `$-58.29`, avg days `88.84`
- OOS cohort EV: prop `10/25/50 = $95724.4 / $239311.0 / $478622.0`, funded `10/25/50 = $729.6 / $1824.0 / $3648.0`
- holdout cohort EV: prop `10/25/50 = $24145.4 / $60363.5 / $120727.0`, funded `10/25/50 = $-582.9 / $-1457.25 / $-2914.5`
