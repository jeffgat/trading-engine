# CL NY HTF-LSI Local Refinement

- This packet stayed inside the promoted CL HTF-LSI lead family and did not reopen broad discovery.
- Primary ranking is still pre-holdout + stitched OOS. The already-opened `2025-04-01+` holdout is only a secondary read.
- Base lead entering this packet: `base_lead` (`long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`).

## Recommendation

- Best restart point after local refinement: `oat_entry_end_1430` (`long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`).
- Stitched OOS funded EV/start moved `152.78` → `173.12`.
- Secondary holdout funded EV/start moved `137.56` → `151.99`.

## OAT Leaders

- `entry_end`: `oat_entry_end_1430` | `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20` | validation PF/avgR/calmar `1.261817384481324` / `0.14509751371798413` / `2.1510936395220535`
- `atr_length`: `oat_atr_length_22` | `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr22` | validation PF/avgR/calmar `1.3036282257595628` / `0.17340650737545266` / `2.7408395422616048`
- `htf_n_left`: `oat_htf_n_left_2` | `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n2 cap2 fvgL100 fvgR10 lag15 atr20` | validation PF/avgR/calmar `1.3267188571875712` / `0.18210276683053958` / `2.356203066345752`
- `left_minutes`: `oat_left_minutes_80` | `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL80 fvgR10 lag15 atr20` | validation PF/avgR/calmar `1.3034837526075937` / `0.17346814809657243` / `2.741813827070252`
- `right_minutes`: `oat_right_minutes_8` | `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR8 lag15 atr20` | validation PF/avgR/calmar `1.3249449982328076` / `0.1823128962792889` / `3.2047805908885425`
- `max_fvg_to_inversion_bars`: `oat_max_fvg_to_inversion_bars_16` | `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag16 atr20` | validation PF/avgR/calmar `1.321610106832299` / `0.183357515581861` / `2.950816977485388`

## Finalists

### oat_entry_end_1430

- config: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`
- pre-holdout: discovery PF/avgR `1.1883689793706862` / `0.11050439180411535`, validation PF/avgR/calmar `1.261817384481324` / `0.14509751371798413` / `2.1510936395220535`
- stitched OOS: trades `306.0`, PF `1.2754`, avgR `0.1555`, funded payout `55.5%`, funded EV/start `$173.12`
- secondary holdout: trades `45.0`, PF `1.6091`, avgR `0.3142`, funded payout `35.9%`, funded EV/start `$151.99`

### base_lead

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`
- pre-holdout: discovery PF/avgR `1.1968487936800467` / `0.11502008302576318`, validation PF/avgR/calmar `1.3034837526075937` / `0.17346814809657243` / `2.741813827070252`
- stitched OOS: trades `292.0`, PF `1.2808`, avgR `0.1603`, funded payout `53.7%`, funded EV/start `$152.78`
- secondary holdout: trades `44.0`, PF `1.5632`, avgR `0.2976`, funded payout `35.9%`, funded EV/start `$137.56`

### oat_left_minutes_80

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL80 fvgR10 lag15 atr20`
- pre-holdout: discovery PF/avgR `1.1968487936800467` / `0.11502008302576318`, validation PF/avgR/calmar `1.3034837526075937` / `0.17346814809657243` / `2.741813827070252`
- stitched OOS: trades `292.0`, PF `1.2808`, avgR `0.1603`, funded payout `53.7%`, funded EV/start `$152.78`
- secondary holdout: trades `44.0`, PF `1.5632`, avgR `0.2976`, funded payout `35.9%`, funded EV/start `$137.56`

### oat_atr_length_22

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr22`
- pre-holdout: discovery PF/avgR `1.218629252479268` / `0.12646762806285258`, validation PF/avgR/calmar `1.3036282257595628` / `0.17340650737545266` / `2.7408395422616048`
- stitched OOS: trades `293.0`, PF `1.2958`, avgR `0.168`, funded payout `53.7%`, funded EV/start `$151.95`
- secondary holdout: trades `44.0`, PF `1.5632`, avgR `0.2976`, funded payout `35.9%`, funded EV/start `$137.56`

### int_end1400_atr22_n3_lag16_l100_r10

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag16 atr22`
- pre-holdout: discovery PF/avgR `1.2411591053723208` / `0.13762802295157414`, validation PF/avgR/calmar `1.3217522310083587` / `0.183296975587904` / `2.9498426926767416`
- stitched OOS: trades `305.0`, PF `1.3253`, avgR `0.1816`, funded payout `55.2%`, funded EV/start `$133.73`
- secondary holdout: trades `46.0`, PF `1.4518`, avgR `0.2459`, funded payout `35.9%`, funded EV/start `$104.78`

### oat_max_fvg_to_inversion_bars_16

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag16 atr20`
- pre-holdout: discovery PF/avgR `1.2198654125991413` / `0.12665899265880037`, validation PF/avgR/calmar `1.321610106832299` / `0.183357515581861` / `2.950816977485388`
- stitched OOS: trades `304.0`, PF `1.3106`, avgR `0.1743`, funded payout `55.2%`, funded EV/start `$132.54`
- secondary holdout: trades `45.0`, PF `1.513`, avgR `0.2736`, funded payout `35.9%`, funded EV/start `$104.78`

### int_end1400_atr20_n3_lag16_l100_r10

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag16 atr20`
- pre-holdout: discovery PF/avgR `1.2198654125991413` / `0.12665899265880037`, validation PF/avgR/calmar `1.321610106832299` / `0.183357515581861` / `2.950816977485388`
- stitched OOS: trades `304.0`, PF `1.3106`, avgR `0.1743`, funded payout `55.2%`, funded EV/start `$132.54`
- secondary holdout: trades `45.0`, PF `1.513`, avgR `0.2736`, funded payout `35.9%`, funded EV/start `$104.78`

### oat_max_fvg_to_inversion_bars_14

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag14 atr20`
- pre-holdout: discovery PF/avgR `1.19918591390067` / `0.11416452514493941`, validation PF/avgR/calmar `1.3163324481817678` / `0.1801316718057529` / `2.7694873923567003`
- stitched OOS: trades `285.0`, PF `1.2951`, avgR `0.1648`, funded payout `52.9%`, funded EV/start `$121.29`
- secondary holdout: trades `43.0`, PF `1.6332`, avgR `0.3277`, funded payout `42.3%`, funded EV/start `$148.88`

### int_end1400_atr20_n3_lag14_l100_r10

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag14 atr20`
- pre-holdout: discovery PF/avgR `1.19918591390067` / `0.11416452514493941`, validation PF/avgR/calmar `1.3163324481817678` / `0.1801316718057529` / `2.7694873923567003`
- stitched OOS: trades `285.0`, PF `1.2951`, avgR `0.1648`, funded payout `52.9%`, funded EV/start `$121.29`
- secondary holdout: trades `43.0`, PF `1.6332`, avgR `0.3277`, funded payout `42.3%`, funded EV/start `$148.88`

### oat_right_minutes_8

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR8 lag15 atr20`
- pre-holdout: discovery PF/avgR `1.1827884367270645` / `0.10633740541468271`, validation PF/avgR/calmar `1.3249449982328076` / `0.1823128962792889` / `3.2047805908885425`
- stitched OOS: trades `269.0`, PF `1.2424`, avgR `0.1391`, funded payout `48.5%`, funded EV/start `$107.54`
- secondary holdout: trades `40.0`, PF `1.8172`, avgR `0.4093`, funded payout `52.9%`, funded EV/start `$193.29`

### int_end1400_atr22_n2_lag14_l100_r10

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n2 cap2 fvgL100 fvgR10 lag14 atr22`
- pre-holdout: discovery PF/avgR `1.2291130951679075` / `0.12644204273082768`, validation PF/avgR/calmar `1.3364031718230474` / `0.1873698201669497` / `2.9019845343359325`
- stitched OOS: trades `328.0`, PF `1.2356`, avgR `0.1319`, funded payout `50.0%`, funded EV/start `$106.65`
- secondary holdout: trades `46.0`, PF `1.3569`, avgR `0.2012`, funded payout `59.3%`, funded EV/start `$208.69`

### int_end1400_atr20_n2_lag14_l100_r10

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n2 cap2 fvgL100 fvgR10 lag14 atr20`
- pre-holdout: discovery PF/avgR `1.2154900746847987` / `0.11947580377252952`, validation PF/avgR/calmar `1.3364118569915002` / `0.18741860059373538` / `2.902740045783743`
- stitched OOS: trades `326.0`, PF `1.229`, avgR `0.1284`, funded payout `49.4%`, funded EV/start `$99.59`
- secondary holdout: trades `46.0`, PF `1.3569`, avgR `0.2012`, funded payout `59.3%`, funded EV/start `$208.69`

### oat_htf_n_left_2

- config: `long close 08:30-14:00 rr3.0 tp0.6 gap3.0 htf60 n2 cap2 fvgL100 fvgR10 lag15 atr20`
- pre-holdout: discovery PF/avgR `1.1922690065954866` / `0.10920735474170477`, validation PF/avgR/calmar `1.3267188571875712` / `0.18210276683053958` / `2.356203066345752`
- stitched OOS: trades `335.0`, PF `1.2062`, avgR `0.1185`, funded payout `45.0%`, funded EV/start `$81.06`
- secondary holdout: trades `47.0`, PF `1.3062`, avgR `0.1757`, funded payout `59.3%`, funded EV/start `$208.69`

## Search Space

- OAT dimensions: `entry_end, atr_length, htf_n_left, left_minutes, right_minutes, max_fvg_to_inversion_bars`
- Interaction values used: `{'entry_end': ['14:00', '14:30'], 'atr_length': [20, 22], 'htf_n_left': [3, 2], 'max_fvg_to_inversion_bars': [15, 16, 14], 'left_minutes': [100], 'right_minutes': [10]}`
