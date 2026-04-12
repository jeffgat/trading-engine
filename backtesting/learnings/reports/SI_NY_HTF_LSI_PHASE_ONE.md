# SI NY HTF-LSI Phase One

- Frozen shortlist source: [SI_NY_HTF_LSI_STITCHED_FOLLOWUP.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/SI_NY_HTF_LSI_STITCHED_FOLLOWUP.md)
- Holdout opened once for phase one: `2025-04-01` to `2026-03-31`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2025-03-31`).
- Bailey-style PSR / DSR was not rerun on this SI packet; phase-one verdicts here are downstream scorecard reads on a frozen pre-holdout shortlist.

## Summary

- `SI NY HTF_LSI stageB 5m cap1 SI NY HTF_LSI stageA 5m htf60 n5 both fvg_limit 08:30-13:00`: verdict `NO-GO`, OOS prop payout `72.0%`, OOS funded payout `56.3%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `SI NY HTF_LSI stageE lag0 SI NY HTF_LSI stageD 5m end14:00 atr14 gap3.0 rr3.5 tp0.5 n5 L140 R10`: verdict `NO-GO`, OOS prop payout `56.9%`, OOS funded payout `51.3%`, holdout prop payout `1.6%`, holdout funded payout `1.6%`
- `SI NY HTF_LSI stageE lag0 SI NY HTF_LSI stageD 5m end13:00 atr14 gap3.0 rr3.5 tp0.5 n5 L140 R10`: verdict `NO-GO`, OOS prop payout `57.0%`, OOS funded payout `51.6%`, holdout prop payout `1.6%`, holdout funded payout `1.6%`
- `SI NY HTF_LSI stageE lag30 SI NY HTF_LSI stageD 5m end13:00 atr14 gap3.0 rr3.5 tp0.5 n5 L140 R10`: verdict `NO-GO`, OOS prop payout `55.6%`, OOS funded payout `49.7%`, holdout prop payout `1.6%`, holdout funded payout `1.6%`
- `SI NY HTF_LSI stageB 5m cap2 SI NY HTF_LSI stageA 5m htf60 n5 both fvg_limit 08:30-14:00`: verdict `NO-GO`, OOS prop payout `55.2%`, OOS funded payout `48.2%`, holdout prop payout `0.0%`, holdout funded payout `0.0%`
- `SI NY HTF_LSI stageE lag30 SI NY HTF_LSI stageD 5m end14:00 atr14 gap3.0 rr3.5 tp0.5 n5 L140 R10`: verdict `NO-GO`, OOS prop payout `55.7%`, OOS funded payout `49.2%`, holdout prop payout `1.6%`, holdout funded payout `1.6%`

## Candidate Details

### SI NY HTF_LSI stageB 5m cap1 SI NY HTF_LSI stageA 5m htf60 n5 both fvg_limit 08:30-13:00

- verdict: `NO-GO`
- candidate_id: `control_stage_b_end13_cap1`
- config: `both fvg_limit 08:30-13:00 rr3.0 tp0.6 gap3.0 htf60 n5 cap1 fvgL20 fvgR2 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `682.0`, PF `1.2741`, avgR `0.1147`, totalR `78.2351`
- stitched OOS metrics: trades `471.0`, PF `1.3858`, avgR `0.1568`, totalR `73.8671`
- OOS prop scorecard: payout `72.0%`, breach `17.9%`, open `10.1%`, EV `$14348.89`, avg days `94.85`
- OOS funded scorecard: payout `56.3%`, breach `33.6%`, open `10.1%`, EV `$107.31`, avg days `73.98`
- holdout metrics: trades `57.0`, PF `0.7593`, avgR `-0.1532`, totalR `-8.7307`
- holdout prop scorecard: payout `0.0%`, breach `27.2%`, open `72.8%`, EV `$-63.62`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `76.0%`, open `24.0%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $143488.9 / $358722.25 / $717444.5`, funded `10/25/50 = $1073.1 / $2682.75 / $5365.5`
- holdout cohort EV: prop `10/25/50 = $-636.2 / $-1590.5 / $-3181.0`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### SI NY HTF_LSI stageE lag0 SI NY HTF_LSI stageD 5m end14:00 atr14 gap3.0 rr3.5 tp0.5 n5 L140 R10

- verdict: `NO-GO`
- candidate_id: `balanced_lag0_end14`
- config: `both fvg_limit 08:30-14:00 rr3.5 tp0.5 gap3.0 htf60 n5 cap2 fvgL28 fvgR2 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `750.0`, PF `1.2261`, avgR `0.0946`, totalR `70.9333`
- stitched OOS metrics: trades `511.0`, PF `1.3329`, avgR `0.1357`, totalR `69.3481`
- OOS prop scorecard: payout `56.9%`, breach `33.5%`, open `9.7%`, EV `$11302.99`, avg days `76.9`
- OOS funded scorecard: payout `51.3%`, breach `39.0%`, open `9.7%`, EV `$92.17`, avg days `62.65`
- holdout metrics: trades `66.0`, PF `0.7688`, avgR `-0.1341`, totalR `-8.8481`
- holdout prop scorecard: payout `1.6%`, breach `47.4%`, open `51.0%`, EV `$246.79`, avg days `13.6`
- holdout funded scorecard: payout `1.6%`, breach `76.0%`, open `22.4%`, EV `$-99.84`, avg days `13.6`
- OOS cohort EV: prop `10/25/50 = $113029.9 / $282574.75 / $565149.5`, funded `10/25/50 = $921.7 / $2304.25 / $4608.5`
- holdout cohort EV: prop `10/25/50 = $2467.9 / $6169.75 / $12339.5`, funded `10/25/50 = $-998.4 / $-2496.0 / $-4992.0`

### SI NY HTF_LSI stageE lag0 SI NY HTF_LSI stageD 5m end13:00 atr14 gap3.0 rr3.5 tp0.5 n5 L140 R10

- verdict: `NO-GO`
- candidate_id: `balanced_lag0_end13`
- config: `both fvg_limit 08:30-13:00 rr3.5 tp0.5 gap3.0 htf60 n5 cap2 fvgL28 fvgR2 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `696.0`, PF `1.2581`, avgR `0.1084`, totalR `75.4508`
- stitched OOS metrics: trades `482.0`, PF `1.3598`, avgR `0.1468`, totalR `70.7651`
- OOS prop scorecard: payout `57.0%`, breach `33.3%`, open `9.7%`, EV `$11333.96`, avg days `78.69`
- OOS funded scorecard: payout `51.6%`, breach `38.7%`, open `9.7%`, EV `$90.07`, avg days `65.91`
- holdout metrics: trades `58.0`, PF `0.7529`, avgR `-0.1531`, totalR `-8.8806`
- holdout prop scorecard: payout `1.6%`, breach `31.4%`, open `67.0%`, EV `$254.81`, avg days `13.6`
- holdout funded scorecard: payout `1.6%`, breach `74.4%`, open `24.0%`, EV `$-99.84`, avg days `13.6`
- OOS cohort EV: prop `10/25/50 = $113339.6 / $283349.0 / $566698.0`, funded `10/25/50 = $900.7 / $2251.75 / $4503.5`
- holdout cohort EV: prop `10/25/50 = $2548.1 / $6370.25 / $12740.5`, funded `10/25/50 = $-998.4 / $-2496.0 / $-4992.0`

### SI NY HTF_LSI stageE lag30 SI NY HTF_LSI stageD 5m end13:00 atr14 gap3.0 rr3.5 tp0.5 n5 L140 R10

- verdict: `NO-GO`
- candidate_id: `late_lag30_end13`
- config: `both fvg_limit 08:30-13:00 rr3.5 tp0.5 gap3.0 htf60 n5 cap2 fvgL28 fvgR2 lag30`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `670.0`, PF `1.2499`, avgR `0.1077`, totalR `72.1448`
- stitched OOS metrics: trades `465.0`, PF `1.351`, avgR `0.1466`, totalR `68.1726`
- OOS prop scorecard: payout `55.6%`, breach `34.8%`, open `9.6%`, EV `$11044.85`, avg days `81.93`
- OOS funded scorecard: payout `49.7%`, breach `40.7%`, open `9.6%`, EV `$86.08`, avg days `66.89`
- holdout metrics: trades `55.0`, PF `0.739`, avgR `-0.1641`, totalR `-9.0258`
- holdout prop scorecard: payout `1.6%`, breach `34.9%`, open `63.5%`, EV `$253.04`, avg days `13.6`
- holdout funded scorecard: payout `1.6%`, breach `74.4%`, open `24.0%`, EV `$-99.84`, avg days `13.6`
- OOS cohort EV: prop `10/25/50 = $110448.5 / $276121.25 / $552242.5`, funded `10/25/50 = $860.8 / $2152.0 / $4304.0`
- holdout cohort EV: prop `10/25/50 = $2530.4 / $6326.0 / $12652.0`, funded `10/25/50 = $-998.4 / $-2496.0 / $-4992.0`

### SI NY HTF_LSI stageB 5m cap2 SI NY HTF_LSI stageA 5m htf60 n5 both fvg_limit 08:30-14:00

- verdict: `NO-GO`
- candidate_id: `control_stage_b_end14`
- config: `both fvg_limit 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n5 cap2 fvgL20 fvgR2 lag0`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `752.0`, PF `1.2146`, avgR `0.0903`, totalR `67.8764`
- stitched OOS metrics: trades `512.0`, PF `1.3234`, avgR `0.1329`, totalR `68.0314`
- OOS prop scorecard: payout `55.2%`, breach `34.6%`, open `10.1%`, EV `$10983.14`, avg days `76.52`
- OOS funded scorecard: payout `48.2%`, breach `41.7%`, open `10.1%`, EV `$82.54`, avg days `59.1`
- holdout metrics: trades `66.0`, PF `0.7747`, avgR `-0.1318`, totalR `-8.701`
- holdout prop scorecard: payout `0.0%`, breach `45.2%`, open `54.8%`, EV `$-72.6`, avg days `None`
- holdout funded scorecard: payout `0.0%`, breach `77.6%`, open `22.4%`, EV `$-100.0`, avg days `None`
- OOS cohort EV: prop `10/25/50 = $109831.4 / $274578.5 / $549157.0`, funded `10/25/50 = $825.4 / $2063.5 / $4127.0`
- holdout cohort EV: prop `10/25/50 = $-726.0 / $-1815.0 / $-3630.0`, funded `10/25/50 = $-1000.0 / $-2500.0 / $-5000.0`

### SI NY HTF_LSI stageE lag30 SI NY HTF_LSI stageD 5m end14:00 atr14 gap3.0 rr3.5 tp0.5 n5 L140 R10

- verdict: `NO-GO`
- candidate_id: `late_lag30_end14`
- config: `both fvg_limit 08:30-14:00 rr3.5 tp0.5 gap3.0 htf60 n5 cap2 fvgL28 fvgR2 lag30`
- discovery deflation: `not_run` / `not_run`
- pre-holdout structural metrics: trades `706.0`, PF `1.2217`, avgR `0.0962`, totalR `67.8929`
- stitched OOS metrics: trades `483.0`, PF `1.3191`, avgR `0.1343`, totalR `64.8671`
- OOS prop scorecard: payout `55.7%`, breach `34.6%`, open `9.6%`, EV `$11075.82`, avg days `82.71`
- OOS funded scorecard: payout `49.2%`, breach `41.1%`, open `9.6%`, EV `$80.76`, avg days `66.98`
- holdout metrics: trades `63.0`, PF `0.76`, avgR `-0.1402`, totalR `-8.8306`
- holdout prop scorecard: payout `1.6%`, breach `49.7%`, open `48.7%`, EV `$245.67`, avg days `13.6`
- holdout funded scorecard: payout `1.6%`, breach `76.0%`, open `22.4%`, EV `$-99.84`, avg days `13.6`
- OOS cohort EV: prop `10/25/50 = $110758.2 / $276895.5 / $553791.0`, funded `10/25/50 = $807.6 / $2019.0 / $4038.0`
- holdout cohort EV: prop `10/25/50 = $2456.7 / $6141.75 / $12283.5`, funded `10/25/50 = $-998.4 / $-2496.0 / $-4992.0`
