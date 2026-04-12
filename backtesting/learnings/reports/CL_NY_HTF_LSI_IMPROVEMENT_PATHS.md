# CL NY HTF-LSI Improvement Paths

- This packet stayed inside the existing CL HTF-LSI family instead of reopening broad discovery.
- Holdout had already been opened previously on `2025-04-01` and remains a secondary read only in this report.
- Fixed family: `1m`, `long`, `close`, `cap=2`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `fvg=100/10`.
- Improvement paths tested: structure `lead_htf60_n3, alt_htf60_n5, challenger_htf30_n7`, entry end `13:30, 14:00, 14:30`, ATR `14, 20`, lag `0, 5, 8, 10, 12, 15`.
- Current phase-one lead entering this packet: `lead_htf60_n3_end1400_atr14_lag0` (`long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag0 atr14`).

## Recommendation

- Best restart point after the micro-packet: `lead_htf60_n3_end1400_atr20_lag15` (`long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`).
- Stitched OOS: `292.0` trades, PF `1.2808`, avgR `0.1603`, funded payout `53.7%`, funded EV/start `$152.78`.
- Secondary holdout read (`2025-04-01` to `2026-03-31`): `44.0` trades, PF `1.5632`, avgR `0.2976`, funded payout `35.9%`, funded EV/start `$137.56`.
- Compared with the old lead, the stitched funded EV/start moved `116.23` → `152.78` and the secondary holdout funded EV/start moved `34.77` → `137.56`.

## Path Leaders

### Structure

- `challenger_htf30_n7`: `challenger_htf30_n7_end1400_atr20_lag0` | pre rank PF/avgR/calmar `1.3109676788160147` / `0.15856727187455985` / `4.662625344316641`; secondary holdout PF `0.984`, avgR `-0.0128`, funded EV/start `$-1.02`
- `lead_htf60_n3`: `lead_htf60_n3_end1400_atr20_lag8` | pre rank PF/avgR/calmar `1.4615293575843018` / `0.2522147811482619` / `2.7949049729959`; secondary holdout PF `2.1163`, avgR `0.5078`, funded EV/start `$210.11`
- `alt_htf60_n5`: `alt_htf60_n5_end1430_atr20_lag12` | pre rank PF/avgR/calmar `1.0514041397829907` / `0.031143059742508625` / `0.21425521145767218`; secondary holdout PF `1.6748`, avgR `0.3487`, funded EV/start `$82.54`

### Entry End

- `14:00`: `challenger_htf30_n7_end1400_atr20_lag0` | pre rank PF/avgR/calmar `1.3109676788160147` / `0.15856727187455985` / `4.662625344316641`; secondary holdout PF `0.984`, avgR `-0.0128`, funded EV/start `$-1.02`
- `14:30`: `challenger_htf30_n7_end1430_atr20_lag0` | pre rank PF/avgR/calmar `1.259783132379507` / `0.13071131045575035` / `3.653872704168785`; secondary holdout PF `1.0313`, avgR `0.0117`, funded EV/start `$0.71`
- `13:30`: `challenger_htf30_n7_end1330_atr20_lag0` | pre rank PF/avgR/calmar `1.2482677198367575` / `0.12911742470230872` / `2.831997661338448`; secondary holdout PF `1.0145`, avgR `0.005`, funded EV/start `$35.78`

### ATR

- `20`: `challenger_htf30_n7_end1400_atr20_lag0` | pre rank PF/avgR/calmar `1.3109676788160147` / `0.15856727187455985` / `4.662625344316641`; secondary holdout PF `0.984`, avgR `-0.0128`, funded EV/start `$-1.02`
- `14`: `challenger_htf30_n7_end1400_atr14_lag0` | pre rank PF/avgR/calmar `1.2910795078757555` / `0.15090107467954975` / `4.019129341146583`; secondary holdout PF `0.9774`, avgR `-0.0159`, funded EV/start `$6.74`

### Lag

- `0`: `challenger_htf30_n7_end1400_atr20_lag0` | pre rank PF/avgR/calmar `1.3109676788160147` / `0.15856727187455985` / `4.662625344316641`; secondary holdout PF `0.984`, avgR `-0.0128`, funded EV/start `$-1.02`
- `8`: `lead_htf60_n3_end1400_atr20_lag8` | pre rank PF/avgR/calmar `1.4615293575843018` / `0.2522147811482619` / `2.7949049729959`; secondary holdout PF `2.1163`, avgR `0.5078`, funded EV/start `$210.11`
- `15`: `lead_htf60_n3_end1400_atr20_lag15` | pre rank PF/avgR/calmar `1.3034837526075937` / `0.17346814809657243` / `2.741813827070252`; secondary holdout PF `1.5632`, avgR `0.2976`, funded EV/start `$137.56`
- `12`: `lead_htf60_n3_end1400_atr20_lag12` | pre rank PF/avgR/calmar `1.2300007589377713` / `0.13325329959655377` / `1.9243728313291866`; secondary holdout PF `1.7839`, avgR `0.3822`, funded EV/start `$115.06`
- `10`: `lead_htf60_n3_end1400_atr20_lag10` | pre rank PF/avgR/calmar `1.218376048769816` / `0.12722301553572576` / `1.6815030365158066`; secondary holdout PF `2.1163`, avgR `0.5078`, funded EV/start `$210.11`
- `5`: `lead_htf60_n3_end1400_atr14_lag5` | pre rank PF/avgR/calmar `1.5448237827070825` / `0.2890448993312028` / `2.9643907117455965`; secondary holdout PF `2.1395`, avgR `0.5112`, funded EV/start `$213.17`

## Finalists

### lead_htf60_n3_end1400_atr20_lag15

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`
- pre-holdout: trades `408`, discovery PF/avgR `1.1968487936800467` / `0.11502008302576318`, validation PF/avgR/calmar `1.3034837526075937` / `0.17346814809657243` / `2.741813827070252`
- stitched OOS: trades `292.0`, PF `1.2808`, avgR `0.1603`, calmar `3.0337`, funded payout `53.7%`, funded EV/start `$152.78`
- secondary holdout: trades `44.0`, PF `1.5632`, avgR `0.2976`, funded payout `35.9%`, funded EV/start `$137.56`

### lead_htf60_n3_end1400_atr20_lag12

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag12 atr20`
- pre-holdout: trades `364`, discovery PF/avgR `1.194983377613959` / `0.11264865896751741`, validation PF/avgR/calmar `1.2300007589377713` / `0.13325329959655377` / `1.9243728313291866`
- stitched OOS: trades `261.0`, PF `1.2523`, avgR `0.143`, calmar `2.5989`, funded payout `45.5%`, funded EV/start `$128.0`
- secondary holdout: trades `36.0`, PF `1.7839`, avgR `0.3822`, funded payout `34.9%`, funded EV/start `$115.06`

### lead_htf60_n3_end1400_atr14_lag0

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag0 atr14`
- pre-holdout: trades `840`, discovery PF/avgR `1.123429001751626` / `0.06657448661432798`, validation PF/avgR/calmar `1.2107906556988222` / `0.10989039881883317` / `2.280730757345375`
- stitched OOS: trades `573.0`, PF `1.2083`, avgR `0.1093`, calmar `2.4064`, funded payout `45.1%`, funded EV/start `$116.23`
- secondary holdout: trades `95.0`, PF `1.1017`, avgR `0.0488`, funded payout `24.7%`, funded EV/start `$34.77`

### challenger_htf30_n7_end1430_atr14_lag0

- config: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf30 n7 cap2 fvgL100 fvgR10 lag0 atr14`
- pre-holdout: trades `872`, discovery PF/avgR `1.100282832867558` / `0.054687322124035306`, validation PF/avgR/calmar `1.2404193463291158` / `0.12359406341081813` / `3.1498516227076534`
- stitched OOS: trades `589.0`, PF `1.2111`, avgR `0.1099`, calmar `2.2926`, funded payout `48.5%`, funded EV/start `$105.14`
- secondary holdout: trades `103.0`, PF `1.0089`, avgR `0.001`, funded payout `22.4%`, funded EV/start `$8.47`

### challenger_htf30_n7_end1400_atr14_lag0

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf30 n7 cap2 fvgL100 fvgR10 lag0 atr14`
- pre-holdout: trades `826`, discovery PF/avgR `1.0977034927289893` / `0.054137909990386014`, validation PF/avgR/calmar `1.2910795078757555` / `0.15090107467954975` / `4.019129341146583`
- stitched OOS: trades `558.0`, PF `1.2225`, avgR `0.1172`, calmar `2.2541`, funded payout `50.6%`, funded EV/start `$104.04`
- secondary holdout: trades `98.0`, PF `0.9774`, avgR `-0.0159`, funded payout `22.4%`, funded EV/start `$6.74`

### challenger_htf30_n7_end1330_atr20_lag0

- config: `long close 08:30-13:30 rr3.0 tp0.6 gap3.0 htf30 n7 cap2 fvgL100 fvgR10 lag0 atr20`
- pre-holdout: trades `789`, discovery PF/avgR `1.1079017287559598` / `0.060710011793361024`, validation PF/avgR/calmar `1.2482677198367575` / `0.12911742470230872` / `2.831997661338448`
- stitched OOS: trades `533.0`, PF `1.2273`, avgR `0.1203`, calmar `2.4229`, funded payout `44.5%`, funded EV/start `$97.12`
- secondary holdout: trades `94.0`, PF `1.0145`, avgR `0.005`, funded payout `24.4%`, funded EV/start `$35.78`

### challenger_htf30_n7_end1430_atr20_lag0

- config: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf30 n7 cap2 fvgL100 fvgR10 lag0 atr20`
- pre-holdout: trades `860`, discovery PF/avgR `1.1058966593618749` / `0.05817465429418775`, validation PF/avgR/calmar `1.259783132379507` / `0.13071131045575035` / `3.653872704168785`
- stitched OOS: trades `582.0`, PF `1.2363`, avgR `0.1216`, calmar `2.439`, funded payout `43.7%`, funded EV/start `$96.19`
- secondary holdout: trades `106.0`, PF `1.0313`, avgR `0.0117`, funded payout `18.9%`, funded EV/start `$0.71`

### lead_htf60_n3_end1400_atr14_lag8

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag8 atr14`
- pre-holdout: trades `288`, discovery PF/avgR `1.1177690484994858` / `0.07119036802742384`, validation PF/avgR/calmar `1.452019647108491` / `0.24725011538878114` / `2.73988928772455`
- stitched OOS: trades `206.0`, PF `1.2045`, avgR `0.1202`, calmar `1.1251`, funded payout `45.4%`, funded EV/start `$91.52`
- secondary holdout: trades `33.0`, PF `2.1163`, avgR `0.5078`, funded payout `56.1%`, funded EV/start `$210.11`

### lead_htf60_n3_end1400_atr20_lag8

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag8 atr20`
- pre-holdout: trades `285`, discovery PF/avgR `1.1169733938482944` / `0.0703765849637429`, validation PF/avgR/calmar `1.4615293575843018` / `0.2522147811482619` / `2.7949049729959`
- stitched OOS: trades `206.0`, PF `1.2052`, avgR `0.1204`, calmar `1.1281`, funded payout `44.5%`, funded EV/start `$78.78`
- secondary holdout: trades `33.0`, PF `2.1163`, avgR `0.5078`, funded payout `56.1%`, funded EV/start `$210.11`

### lead_htf60_n3_end1400_atr20_lag10

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag10 atr20`
- pre-holdout: trades `326`, discovery PF/avgR `1.179731034805982` / `0.10664885435877396`, validation PF/avgR/calmar `1.218376048769816` / `0.12722301553572576` / `1.6815030365158066`
- stitched OOS: trades `236.0`, PF `1.1909`, avgR `0.1129`, calmar `1.3812`, funded payout `40.0%`, funded EV/start `$77.49`
- secondary holdout: trades `33.0`, PF `2.1163`, avgR `0.5078`, funded payout `56.1%`, funded EV/start `$210.11`

### lead_htf60_n3_end1400_atr14_lag5

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag5 atr14`
- pre-holdout: trades `205`, discovery PF/avgR `1.1158309574302157` / `0.07304593575376482`, validation PF/avgR/calmar `1.5448237827070825` / `0.2890448993312028` / `2.9643907117455965`
- stitched OOS: trades `154.0`, PF `1.2991`, avgR `0.1731`, calmar `1.9215`, funded payout `45.7%`, funded EV/start `$67.66`
- secondary holdout: trades `25.0`, PF `2.1395`, avgR `0.5112`, funded payout `51.9%`, funded EV/start `$213.17`

### alt_htf60_n5_end1430_atr20_lag12

- config: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n5 cap2 fvgL100 fvgR10 lag12 atr20`
- pre-holdout: trades `327`, discovery PF/avgR `1.0606997193995398` / `0.0365336610836398`, validation PF/avgR/calmar `1.0514041397829907` / `0.031143059742508625` / `0.21425521145767218`
- stitched OOS: trades `230.0`, PF `1.0456`, avgR `0.0277`, calmar `0.3186`, funded payout `31.0%`, funded EV/start `$50.61`
- secondary holdout: trades `33.0`, PF `1.6748`, avgR `0.3487`, funded payout `50.6%`, funded EV/start `$82.54`

### challenger_htf30_n7_end1400_atr20_lag0

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf30 n7 cap2 fvgL100 fvgR10 lag0 atr20`
- pre-holdout: trades `813`, discovery PF/avgR `1.1047704501873454` / `0.05847775070517873`, validation PF/avgR/calmar `1.3109676788160147` / `0.15856727187455985` / `4.662625344316641`
- stitched OOS: trades `550.0`, PF `1.2497`, avgR `0.1302`, calmar `2.5442`, funded payout `45.9%`, funded EV/start `$114.21`
- secondary holdout: trades `101.0`, PF `0.984`, avgR `-0.0128`, funded payout `18.9%`, funded EV/start `$-1.02`
