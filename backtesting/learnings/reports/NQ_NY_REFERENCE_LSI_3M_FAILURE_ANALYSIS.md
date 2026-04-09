# NQ NY Reference LSI 3m Failure Analysis

- Candidate: `NQ NY reference_lsi 3m both 13:00 far gap9 inv12 rr3.0 tp0.7`
- Phase 3 comparison stream: stitched OOS `2019-01-01` to `2024-12-31`.
- Holdout read: `2025-01-01` to `2026-03-24`.

## Overall

- pre-holdout: trades `107`, avgR `0.2931`, PF `1.6112`, totalR `31.36`
- stitched OOS: trades `67`, avgR `0.3917`, PF `1.8766`, totalR `26.25`
- holdout: trades `18`, avgR `0.1812`, PF `1.3016`, totalR `3.26`

## Payout Conversion

- OOS prop payout / breach / open: `79.6%` / `1.0%` / `19.4%`
- OOS funded payout / breach / open: `77.1%` / `3.5%` / `19.4%`
- holdout prop payout / breach / open: `0.0%` / `23.2%` / `76.8%`
- holdout funded payout / breach / open: `1.6%` / `81.2%` / `17.2%`

## By Level Family

- `previous_day`: OOS `28` / avgR `0.5672` / PF `2.2132` / totalR `15.88`; holdout `3` / avgR `-0.0321` / PF `1.0341` / totalR `-0.1`
- `asia`: OOS `24` / avgR `0.3355` / PF `1.8677` / totalR `8.05`; holdout `10` / avgR `0.0152` / PF `0.9309` / totalR `0.15`
- `london`: OOS `15` / avgR `0.1541` / PF `1.369` / totalR `2.31`; holdout `5` / avgR `0.6411` / PF `2.92` / totalR `3.21`

## By Side / Direction

### level_side

- `high_side`: OOS `30` / avgR `0.3255` / PF `1.7026` / totalR `9.77`; holdout `11` / avgR `-0.4615` / PF `0.2884` / totalR `-5.08`
- `low_side`: OOS `37` / avgR `0.4454` / PF `2.0411` / totalR `16.48`; holdout `7` / avgR `1.1911` / PF `5.7965` / totalR `8.34`

### direction

- `short`: OOS `30` / avgR `0.3255` / PF `1.7026` / totalR `9.77`; holdout `11` / avgR `-0.4615` / PF `0.2884` / totalR `-5.08`
- `long`: OOS `37` / avgR `0.4454` / PF `2.0411` / totalR `16.48`; holdout `7` / avgR `1.1911` / PF `5.7965` / totalR `8.34`

### time_bucket

- `08:30-09:00`: OOS `0` / avgR `0.0` / PF `0.0` / totalR `0.0`; holdout `1` / avgR `-1.0` / PF `0.0` / totalR `-1.0`
- `09:00-09:30`: OOS `2` / avgR `0.025` / PF `1.2722` / totalR `0.05`; holdout `0` / avgR `0.0` / PF `0.0` / totalR `0.0`
- `09:30-10:00`: OOS `8` / avgR `0.9679` / PF `4.1115` / totalR `7.74`; holdout `4` / avgR `-0.302` / PF `0.6239` / totalR `-1.21`
- `10:00-10:30`: OOS `20` / avgR `0.5217` / PF `2.1039` / totalR `10.43`; holdout `5` / avgR `-0.053` / PF `0.9417` / totalR `-0.27`
- `10:30-11:00`: OOS `17` / avgR `0.4431` / PF `2.0057` / totalR `7.53`; holdout `6` / avgR `0.805` / PF `2.9128` / totalR `4.83`
- `11:00-11:30`: OOS `10` / avgR `0.4281` / PF `2.1546` / totalR `4.28`; holdout `0` / avgR `0.0` / PF `0.0` / totalR `0.0`
- `11:30-12:00`: OOS `1` / avgR `-1.0` / PF `0.0` / totalR `-1.0`; holdout `2` / avgR `0.4519` / PF `2.0653` / totalR `0.9`
- `12:00-12:30`: OOS `3` / avgR `-0.5172` / PF `0.2165` / totalR `-1.55`; holdout `0` / avgR `0.0` / PF `0.0` / totalR `0.0`
- `12:30-13:00`: OOS `6` / avgR `-0.207` / PF `0.6555` / totalR `-1.24`; holdout `0` / avgR `0.0` / PF `0.0` / totalR `0.0`

## Holdout By Year

- `2025`: trades `12`, avgR `0.1023`, PF `1.2037`, totalR `1.23`
- `2026`: trades `6`, avgR `0.3389`, PF `1.5418`, totalR `2.03`

## Readout

- The key problem is speed and sample, not a total collapse of raw trade quality in the leader. The holdout leader still stayed positive on raw R (`+3.26R`) but only produced `18` trades, which is not enough to reliably reach a `+5R` prop payout target across rolling account starts.
- Most holdout starts remained open or breached before enough positive trades accumulated. That is why payout conversion degraded much more than the raw holdout trade metrics alone suggest.
- This means the next branch should focus on concentration and selectivity: either remove the draggiest level families in the `3m` leader or restart the thesis with `previous_day_* + asia_*` only.