# NQ NY LSI CISD Target Sweep

- Latest data date: `2026-05-01`.
- Scope: target-only sweep on 3 frozen finalists; signal, entry, stop, sweep source, timeframe, DOW, and session cutoffs are unchanged.
- RR values: `[1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0]`.
- TP1 ratio values: `[0.4, 0.5, 0.6, 0.7, 0.8]`; rows with `rr * tp1_ratio < 1.0` skipped.
- Deployability for swept rows: `live_native`; exact replay still required before execution-config promotion.

## Top Rows

| Rank | Candidate | Robust | Full R/PF/DD | V R/PF | H R/PF | Post-2023 R/PF/DD | 2025 R | Neg Years |
| ---: | --- | --- | --- | --- | --- | --- | ---: | ---: |
| 1 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p5__tp1_0p4` | `True` | 66.2 / 1.25 / -18.6 | 16.3 / 1.37 | 16.2 / 1.81 | 32.6 / 1.51 / -6.7 | 5.6 | 1 |
| 2 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p0__tp1_0p5` | `True` | 67.1 / 1.25 / -18.1 | 16.1 / 1.37 | 14.7 / 1.73 | 30.8 / 1.48 / -6.6 | 6.2 | 1 |
| 3 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p75__tp1_0p4` | `True` | 66.3 / 1.24 / -18.2 | 19.2 / 1.41 | 15.3 / 1.69 | 34.5 / 1.50 / -7.0 | 6.8 | 1 |
| 4 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr1p75__tp1_0p6` | `True` | 65.3 / 1.24 / -16.7 | 16.7 / 1.36 | 14.4 / 1.72 | 31.1 / 1.47 / -7.3 | 7.2 | 1 |
| 5 | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p5__tp1_0p4` | `True` | 86.1 / 1.44 / -9.8 | 20.0 / 1.61 | 12.7 / 1.80 | 32.7 / 1.67 / -6.6 | 7.0 | 1 |
| 6 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p5__tp1_0p5` | `True` | 60.9 / 1.20 / -17.6 | 17.0 / 1.34 | 11.1 / 1.43 | 28.1 / 1.37 / -8.5 | 4.2 | 1 |
| 7 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr1p5__tp1_0p7` | `True` | 61.2 / 1.23 / -14.9 | 15.9 / 1.35 | 12.8 / 1.64 | 28.7 / 1.44 / -6.8 | 6.1 | 2 |
| 8 | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p0__tp1_0p5` | `True` | 88.6 / 1.45 / -9.0 | 20.3 / 1.62 | 12.0 / 1.75 | 32.3 / 1.66 / -7.1 | 7.9 | 1 |
| 9 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p25__tp1_0p5` | `True` | 69.1 / 1.24 / -17.1 | 19.2 / 1.41 | 10.5 / 1.44 | 29.7 / 1.42 / -7.5 | 2.8 | 1 |
| 10 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p0__tp1_0p6` | `True` | 59.6 / 1.20 / -18.9 | 15.9 / 1.32 | 12.4 / 1.50 | 28.3 / 1.38 / -9.1 | 8.5 | 1 |
| 11 | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr1p75__tp1_0p6` | `True` | 84.2 / 1.42 / -8.4 | 20.4 / 1.60 | 12.1 / 1.75 | 32.5 / 1.65 / -6.3 | 7.9 | 1 |
| 12 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr3p0__tp1_0p4` | `True` | 47.7 / 1.16 / -17.9 | 15.5 / 1.31 | 10.7 / 1.43 | 26.2 / 1.35 / -9.7 | 3.5 | 1 |
| 13 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr1p75__tp1_0p7` | `True` | 58.9 / 1.20 / -17.0 | 17.1 / 1.34 | 10.5 / 1.42 | 27.6 / 1.37 / -8.4 | 6.7 | 1 |
| 14 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p25__tp1_0p6` | `True` | 65.2 / 1.21 / -16.8 | 22.7 / 1.45 | 8.8 / 1.32 | 31.5 / 1.40 / -8.5 | 4.7 | 1 |
| 15 | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr1p5__tp1_0p7` | `True` | 80.6 / 1.40 / -7.1 | 19.4 / 1.57 | 10.1 / 1.63 | 29.5 / 1.59 / -5.8 | 6.3 | 1 |
| 16 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr1p5__tp1_0p8` | `True` | 49.7 / 1.17 / -17.9 | 16.3 / 1.33 | 8.4 / 1.34 | 24.7 / 1.33 / -8.0 | 5.0 | 1 |
| 17 | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr1p5__tp1_0p8` | `True` | 39.1 / 1.45 / -10.4 | 11.6 / 1.96 | 6.5 / 1.81 | 18.1 / 1.90 / -2.6 | 4.1 | 4 |
| 18 | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p75__tp1_0p4` | `True` | 83.4 / 1.40 / -9.4 | 22.0 / 1.63 | 11.0 / 1.61 | 33.1 / 1.62 / -8.5 | 6.1 | 1 |
| 19 | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr2p25__tp1_0p5` | `True` | 32.3 / 1.39 / -11.4 | 11.0 / 1.91 | 6.1 / 1.87 | 17.0 / 1.90 / -2.7 | 2.4 | 3 |
| 20 | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p0__tp1_0p6` | `True` | 78.0 / 1.35 / -9.0 | 18.4 / 1.48 | 9.7 / 1.48 | 28.1 / 1.48 / -8.1 | 7.3 | 1 |

## Best By Base

### add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530
- `rr=2.50`, `tp1=0.40`: post-2023 `32.6R` PF `1.51` DD `-6.7`; 2025 `5.6R`; delta post-2023 `+1.7R`, delta 2025 `-0.6R`; phase-one post-2023 payout `80.5%`, breach `14.9%`, EV `3.61R`.
- `rr=2.00`, `tp1=0.50`: post-2023 `30.8R` PF `1.48` DD `-6.6`; 2025 `6.2R`; delta post-2023 `+0.0R`, delta 2025 `+0.0R`; phase-one post-2023 payout `77.0%`, breach `16.1%`, EV `3.49R`.
- `rr=2.75`, `tp1=0.40`: post-2023 `34.5R` PF `1.50` DD `-7.0`; 2025 `6.8R`; delta post-2023 `+3.7R`, delta 2025 `+0.6R`; phase-one post-2023 payout `82.8%`, breach `13.8%`, EV `3.73R`.
- `rr=1.75`, `tp1=0.60`: post-2023 `31.1R` PF `1.47` DD `-7.3`; 2025 `7.2R`; delta post-2023 `+0.3R`, delta 2025 `+1.0R`; phase-one post-2023 payout `80.5%`, breach `12.6%`, EV `3.79R`.
- `rr=2.50`, `tp1=0.50`: post-2023 `28.1R` PF `1.37` DD `-8.5`; 2025 `4.2R`; delta post-2023 `-2.7R`, delta 2025 `-2.0R`; phase-one post-2023 payout `81.6%`, breach `12.6%`, EV `3.75R`.

### add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530
- `rr=2.50`, `tp1=0.40`: post-2023 `32.7R` PF `1.67` DD `-6.6`; 2025 `7.0R`; delta post-2023 `+0.4R`, delta 2025 `-0.9R`; phase-one post-2023 payout `82.8%`, breach `8.0%`, EV `4.18R`.
- `rr=2.00`, `tp1=0.50`: post-2023 `32.3R` PF `1.66` DD `-7.1`; 2025 `7.9R`; delta post-2023 `+0.0R`, delta 2025 `+0.0R`; phase-one post-2023 payout `71.3%`, breach `11.5%`, EV `3.79R`.
- `rr=1.75`, `tp1=0.60`: post-2023 `32.5R` PF `1.65` DD `-6.3`; 2025 `7.9R`; delta post-2023 `+0.1R`, delta 2025 `-0.0R`; phase-one post-2023 payout `74.7%`, breach `6.9%`, EV `4.16R`.
- `rr=1.50`, `tp1=0.70`: post-2023 `29.5R` PF `1.59` DD `-5.8`; 2025 `6.3R`; delta post-2023 `-2.8R`, delta 2025 `-1.6R`; phase-one post-2023 payout `73.6%`, breach `5.7%`, EV `4.18R`.
- `rr=2.75`, `tp1=0.40`: post-2023 `33.1R` PF `1.62` DD `-8.5`; 2025 `6.1R`; delta post-2023 `+0.7R`, delta 2025 `-1.8R`; phase-one post-2023 payout `77.0%`, breach `10.3%`, EV `3.94R`.

### pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200
- `rr=1.50`, `tp1=0.80`: post-2023 `18.1R` PF `1.90` DD `-2.6`; 2025 `4.1R`; delta post-2023 `+2.7R`, delta 2025 `+1.7R`; phase-one post-2023 payout `88.5%`, breach `0.0%`, EV `4.67R`.
- `rr=2.25`, `tp1=0.50`: post-2023 `17.0R` PF `1.90` DD `-2.7`; 2025 `2.4R`; delta post-2023 `+1.7R`, delta 2025 `-0.1R`; phase-one post-2023 payout `86.2%`, breach `0.0%`, EV `4.68R`.
- `rr=2.75`, `tp1=0.40`: post-2023 `15.2R` PF `1.80` DD `-2.5`; 2025 `2.8R`; delta post-2023 `-0.2R`, delta 2025 `+0.3R`; phase-one post-2023 payout `86.2%`, breach `0.0%`, EV `4.65R`.
- `rr=2.50`, `tp1=0.40`: post-2023 `16.3R` PF `1.96` DD `-2.7`; 2025 `2.0R`; delta post-2023 `+0.9R`, delta 2025 `-0.5R`; phase-one post-2023 payout `75.9%`, breach `0.0%`, EV `4.39R`.
- `rr=2.00`, `tp1=0.60`: post-2023 `19.9R` PF `2.00` DD `-2.4`; 2025 `2.9R`; delta post-2023 `+4.5R`, delta 2025 `+0.4R`; phase-one post-2023 payout `90.8%`, breach `0.0%`, EV `4.74R`.

## Baseline Delta Summary

### add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p5__tp1_0p4`: dScore `+0.20`, dPost23 `+1.7R`, dPF `+0.03`, d2025 `-0.6R`, dFullDD `-0.5`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p0__tp1_0p5`: dScore `+0.00`, dPost23 `+0.0R`, dPF `+0.00`, d2025 `+0.0R`, dFullDD `+0.0`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p75__tp1_0p4`: dScore `-0.05`, dPost23 `+3.7R`, dPF `+0.02`, d2025 `+0.6R`, dFullDD `-0.1`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr1p75__tp1_0p6`: dScore `-0.14`, dPost23 `+0.3R`, dPF `-0.01`, d2025 `+1.0R`, dFullDD `+1.4`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p5__tp1_0p5`: dScore `-0.59`, dPost23 `-2.7R`, dPF `-0.11`, d2025 `-2.0R`, dFullDD `+0.5`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr1p5__tp1_0p7`: dScore `-0.61`, dPost23 `-2.1R`, dPF `-0.05`, d2025 `-0.1R`, dFullDD `+3.1`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p25__tp1_0p5`: dScore `-0.67`, dPost23 `-1.1R`, dPF `-0.06`, d2025 `-3.4R`, dFullDD `+0.9`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530__rr2p0__tp1_0p6`: dScore `-0.70`, dPost23 `-2.5R`, dPF `-0.10`, d2025 `+2.3R`, dFullDD `-0.8`.

### add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p5__tp1_0p4`: dScore `+0.41`, dPost23 `+0.4R`, dPF `+0.01`, d2025 `-0.9R`, dFullDD `-0.7`.
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p0__tp1_0p5`: dScore `+0.00`, dPost23 `+0.0R`, dPF `+0.00`, d2025 `+0.0R`, dFullDD `+0.0`.
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr1p75__tp1_0p6`: dScore `-0.06`, dPost23 `+0.1R`, dPF `-0.01`, d2025 `-0.0R`, dFullDD `+0.7`.
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr1p5__tp1_0p7`: dScore `-0.53`, dPost23 `-2.8R`, dPF `-0.07`, d2025 `-1.6R`, dFullDD `+1.9`.
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p75__tp1_0p4`: dScore `-1.05`, dPost23 `+0.7R`, dPF `-0.04`, d2025 `-1.8R`, dFullDD `-0.3`.
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p0__tp1_0p6`: dScore `-1.11`, dPost23 `-4.3R`, dPF `-0.18`, d2025 `-0.6R`, dFullDD `+0.0`.
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr2p5__tp1_0p5`: dScore `-1.19`, dPost23 `-5.7R`, dPF `-0.21`, d2025 `-4.6R`, dFullDD `-0.1`.
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530__rr1p75__tp1_0p7`: dScore `-1.35`, dPost23 `-4.9R`, dPF `-0.19`, d2025 `-2.1R`, dFullDD `+0.1`.

### pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr1p5__tp1_0p8`: dScore `+1.01`, dPost23 `+2.7R`, dPF `-0.00`, d2025 `+1.7R`, dFullDD `-1.4`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr2p25__tp1_0p5`: dScore `+0.89`, dPost23 `+1.7R`, dPF `-0.01`, d2025 `-0.1R`, dFullDD `-2.3`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr2p75__tp1_0p4`: dScore `+0.76`, dPost23 `-0.2R`, dPF `-0.11`, d2025 `+0.3R`, dFullDD `-2.3`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr2p5__tp1_0p4`: dScore `+0.46`, dPost23 `+0.9R`, dPF `+0.06`, d2025 `-0.5R`, dFullDD `-1.0`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr2p0__tp1_0p6`: dScore `+0.33`, dPost23 `+4.5R`, dPF `+0.09`, d2025 `+0.4R`, dFullDD `-1.4`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr2p5__tp1_0p5`: dScore `+0.15`, dPost23 `+3.7R`, dPF `+0.05`, d2025 `+0.4R`, dFullDD `-2.1`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr1p75__tp1_0p6`: dScore `+0.15`, dPost23 `-0.8R`, dPF `-0.10`, d2025 `-0.3R`, dFullDD `+0.1`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200__rr2p0__tp1_0p5`: dScore `+0.00`, dPost23 `+0.0R`, dPF `+0.00`, d2025 `+0.0R`, dFullDD `+0.0`.

