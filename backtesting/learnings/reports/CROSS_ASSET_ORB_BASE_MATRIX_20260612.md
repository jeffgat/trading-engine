# Cross-Asset Neutral ORB Base Matrix

## Executive Read

This scan reused the ALPHA_V2 NQ_NY-RR2 neutral ORB anchor across NQ, ES, GC, SI, RTY, and YM for NY, Asia, and London sessions. Discovery used 2021-2024 only; 2025+ was evaluated after each sleeve shortlist was frozen.

The ranking is deliberately multi-factor: enough trades, positive edge, annual consistency, 2022-2023 survivability, PSR/DSR, first-payout EV, drawdown, Calmar, and holdout behavior. Calmar is reported but is not the sole optimizer.

**Best promotion candidate:** `rty__ny__rr1p0__both__no_thu__low_or_mid_atr`

- Verdict: `PROMOTE_TO_EXACT_REPLAY`; deployability `live_native`; exact execution replay required.
- Discovery: 246 trades, 50.00R, PF 1.51, DD -9.00R, Calmar 5.56, PSR 0.9991, DSR 0.8943.
- Discovery payout model: payout 64.8%, breach 29.5%, EV/start $223.81.
- Holdout: 106 trades, 3.36R, PF 1.06, DD -11.64R.

## Overall Top Candidates

| Rank | Asset | Sess | Rule | Verdict | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R | HO PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | RTY | NY | rty__ny__rr1p0__both__no_thu__low_or_mid_atr | PROMOTE_TO_EXACT_REPLAY | 246 | 50.00 | 1.51 | -9.00 | 5.56 | 0.89 | 0.65 | 223.81 | 3.36 | 1.06 |
| 2 | SI | NY | si__ny__rr1p0__both__no_tue__small_or_mid_orb | PROMOTE_TO_EXACT_REPLAY | 268 | 33.04 | 1.29 | -5.00 | 6.61 | 0.51 | 0.61 | 204.76 | 5.66 | 1.18 |
| 3 | ES | NY | es__ny__rr1p0__both__no_wed | PROMOTE_TO_EXACT_REPLAY | 400 | 47.75 | 1.28 | -10.00 | 4.77 | 0.68 | 0.52 | 161.90 | 4.82 | 1.07 |
| 4 | SI | NY | si__ny__rr1p0__both__no_tue__low_or_mid_atr | PROMOTE_TO_EXACT_REPLAY | 261 | 36.81 | 1.33 | -5.00 | 7.36 | 0.62 | 0.77 | 285.71 | 4.44 | 1.14 |
| 5 | SI | NY | si__ny__rr1p0__long__no_tue | PROMOTE_TO_EXACT_REPLAY | 267 | 33.74 | 1.30 | -7.00 | 4.82 | 0.53 | 0.58 | 190.48 | 7.66 | 1.18 |
| 6 | NQ | NY | nq__ny__rr1p5__long__no_fri__small_orb_only | PROMOTE_TO_EXACT_REPLAY | 98 | 29.79 | 1.69 | -6.01 | 4.96 | 0.71 | 0.68 | 238.10 | 6.06 | 1.24 |
| 7 | NQ | NY | nq__ny__rr1p5__long__none__small_orb_only | PROMOTE_TO_EXACT_REPLAY | 128 | 29.79 | 1.48 | -8.91 | 3.34 | 0.59 | 0.71 | 257.14 | 6.56 | 1.23 |
| 8 | ES | NY | es__ny__rr1p0__short__no_wed | PROMOTE_TO_EXACT_REPLAY | 140 | 23.67 | 1.42 | -6.00 | 3.94 | 0.53 | 0.56 | 180.95 | 9.00 | 1.46 |
| 9 | ES | NY | es__ny__rr1p25__short__no_wed | PROMOTE_TO_EXACT_REPLAY | 140 | 25.92 | 1.40 | -7.75 | 3.34 | 0.50 | 0.50 | 147.62 | 7.25 | 1.33 |
| 10 | ES | Asia | es__asia__rr2p0__long__no_mon__small_or_mid_orb | PROMOTE_TO_EXACT_REPLAY | 96 | 31.75 | 1.66 | -10.00 | 3.18 | 0.60 | 0.86 | 328.57 | 7.79 | 1.45 |
| 11 | ES | Asia | es__asia__rr2p0__long__no_mon__low_or_mid_atr__small_or_mid_orb | PROMOTE_TO_EXACT_REPLAY | 79 | 27.46 | 1.68 | -10.00 | 2.75 | 0.54 | 0.86 | 328.57 | 9.24 | 1.67 |
| 12 | GC | Asia | gc__asia__rr2p0__long__no_wed__low_atr_only | PROMOTE_TO_EXACT_REPLAY | 99 | 30.01 | 1.54 | -5.00 | 6.00 | 0.53 | 0.74 | 271.43 | 1.00 | 1.38 |

## Top 3 By Asset And Session

### NQ NY

- Trials: raw `864`, effective `22`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.2932`, ATR p66 `1.9312`, ORB p33 `0.3718`, ORB p66 `0.5853`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | nq__ny__rr1p5__long__no_fri__small_orb_only | PROMOTE_TO_EXACT_REPLAY | long | 1.50 | Friday | none | small_orb_only | 98 | 29.79 | 1.69 | -6.01 | 4.96 | 0.71 | 0.68 | 238.10 | 6.06 |
| 2 | nq__ny__rr1p5__long__none__small_orb_only | PROMOTE_TO_EXACT_REPLAY | long | 1.50 | None | none | small_orb_only | 128 | 29.79 | 1.48 | -8.91 | 3.34 | 0.59 | 0.71 | 257.14 | 6.56 |
| 3 | nq__ny__rr1p25__long__no_fri__small_orb_only | PROMOTE_TO_EXACT_REPLAY | long | 1.25 | Friday | none | small_orb_only | 98 | 30.51 | 1.80 | -6.26 | 4.88 | 0.81 | 0.86 | 328.57 | 5.53 |

### NQ Asia

- Trials: raw `864`, effective `24`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.2932`, ATR p66 `1.9312`, ORB p33 `0.0639`, ORB p66 `0.1280`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | nq__asia__rr2p0__long__no_tue | REJECT | long | 2.00 | Tuesday | none | none | 163 | 13.93 | 1.13 | -15.31 | 0.91 | 0.11 | 0.40 | 100.00 | -0.71 |
| 2 | nq__asia__rr1p0__both__no_tue | REJECT | both | 1.00 | Tuesday | none | none | 256 | 7.10 | 1.06 | -13.00 | 0.55 | 0.06 | 0.30 | 52.38 | -8.00 |
| 3 | nq__asia__rr2p0__both__no_tue__low_atr_only | REJECT | both | 2.00 | Tuesday | low_atr_only | none | 75 | 5.50 | 1.12 | -9.82 | 0.56 | 0.06 | 0.27 | 33.33 | -0.93 |

### NQ LDN

- Trials: raw `864`, effective `19`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.2932`, ATR p66 `1.9312`, ORB p33 `0.1237`, ORB p66 `0.2087`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | nq__ldn__rr1p0__long__no_wed | REJECT | long | 1.00 | Wednesday | none | none | 341 | 30.24 | 1.23 | -8.49 | 3.56 | 0.47 | 0.53 | 166.67 | 3.49 |
| 2 | nq__ldn__rr1p25__long__no_mon__low_atr_only | REJECT | long | 1.25 | Monday | low_atr_only | none | 114 | 9.50 | 1.20 | -6.03 | 1.58 | 0.16 | 0.71 | 257.14 | 0.01 |
| 3 | nq__ldn__rr2p0__long__no_mon__low_atr_only | REJECT | long | 2.00 | Monday | low_atr_only | none | 114 | 13.67 | 1.26 | -6.26 | 2.18 | 0.20 | 0.80 | 300.00 | -4.62 |

### ES NY

- Trials: raw `864`, effective `22`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `0.9150`, ATR p66 `1.3970`, ORB p33 `0.2140`, ORB p66 `0.3489`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | es__ny__rr1p0__both__no_wed | PROMOTE_TO_EXACT_REPLAY | both | 1.00 | Wednesday | none | none | 400 | 47.75 | 1.28 | -10.00 | 4.77 | 0.68 | 0.52 | 161.90 | 4.82 |
| 2 | es__ny__rr1p0__short__no_wed | PROMOTE_TO_EXACT_REPLAY | short | 1.00 | Wednesday | none | none | 140 | 23.67 | 1.42 | -6.00 | 3.94 | 0.53 | 0.56 | 180.95 | 9.00 |
| 3 | es__ny__rr1p25__short__no_wed | PROMOTE_TO_EXACT_REPLAY | short | 1.25 | Wednesday | none | none | 140 | 25.92 | 1.40 | -7.75 | 3.34 | 0.50 | 0.50 | 147.62 | 7.25 |

### ES Asia

- Trials: raw `864`, effective `27`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `0.9150`, ATR p66 `1.3970`, ORB p33 `0.0498`, ORB p66 `0.0987`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | es__asia__rr2p0__long__no_mon__small_or_mid_orb | PROMOTE_TO_EXACT_REPLAY | long | 2.00 | Monday | none | small_or_mid_orb | 96 | 31.75 | 1.66 | -10.00 | 3.18 | 0.60 | 0.86 | 328.57 | 7.79 |
| 2 | es__asia__rr2p0__long__no_mon__low_or_mid_atr__small_or_mid_orb | PROMOTE_TO_EXACT_REPLAY | long | 2.00 | Monday | low_or_mid_atr | small_or_mid_orb | 79 | 27.46 | 1.68 | -10.00 | 2.75 | 0.54 | 0.86 | 328.57 | 9.24 |
| 3 | es__asia__rr1p5__long__no_mon | REJECT | long | 1.50 | Monday | none | none | 176 | 25.46 | 1.27 | -11.00 | 2.31 | 0.31 | 0.54 | 171.43 | 18.36 |

### ES LDN

- Trials: raw `864`, effective `25`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `0.9150`, ATR p66 `1.3970`, ORB p33 `0.0935`, ORB p66 `0.1654`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | es__ldn__rr1p0__both__no_thu__low_atr_only__small_orb_only | CHALLENGER | both | 1.00 | Thursday | low_atr_only | small_orb_only | 98 | 18.51 | 1.53 | -5.30 | 3.49 | 0.50 | 0.90 | 352.38 | -4.38 |
| 2 | es__ldn__rr1p25__both__no_mon__low_atr_only__small_orb_only | REJECT | both | 1.25 | Monday | low_atr_only | small_orb_only | 86 | 18.17 | 1.55 | -4.29 | 4.23 | 0.45 | 0.74 | 271.43 | -4.81 |
| 3 | es__ldn__rr1p5__both__no_mon__low_atr_only__small_orb_only | REJECT | both | 1.50 | Monday | low_atr_only | small_orb_only | 86 | 19.54 | 1.57 | -4.12 | 4.74 | 0.45 | 0.83 | 314.29 | -12.07 |

### GC NY

- Trials: raw `864`, effective `28`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.0838`, ATR p66 `1.3308`, ORB p33 `0.2188`, ORB p66 `0.3051`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | gc__ny__rr1p25__long__no_mon__low_atr_only__small_orb_only | CHALLENGER | long | 1.25 | Monday | low_atr_only | small_orb_only | 45 | 25.97 | 2.97 | -2.00 | 12.99 | 0.92 | 0.70 | 247.62 | 1.25 |
| 2 | gc__ny__rr1p25__long__no_thu__low_atr_only__small_orb_only | CHALLENGER | long | 1.25 | Thursday | low_atr_only | small_orb_only | 52 | 19.72 | 2.02 | -3.00 | 6.57 | 0.67 | 0.68 | 238.10 | 1.25 |
| 3 | gc__ny__rr1p25__long__none__low_atr_only__small_orb_only | CHALLENGER | long | 1.25 | None | low_atr_only | small_orb_only | 60 | 20.72 | 1.89 | -3.00 | 6.91 | 0.65 | 0.69 | 242.86 | 2.50 |

### GC Asia

- Trials: raw `864`, effective `23`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.0838`, ATR p66 `1.3308`, ORB p33 `0.0639`, ORB p66 `0.1100`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | gc__asia__rr2p0__long__no_wed__low_atr_only | PROMOTE_TO_EXACT_REPLAY | long | 2.00 | Wednesday | low_atr_only | none | 99 | 30.01 | 1.54 | -5.00 | 6.00 | 0.53 | 0.74 | 271.43 | 1.00 |
| 2 | gc__asia__rr2p0__long__no_wed__low_atr_only__small_or_mid_orb | CHALLENGER | long | 2.00 | Wednesday | low_atr_only | small_or_mid_orb | 86 | 28.01 | 1.59 | -4.00 | 7.00 | 0.53 | 0.77 | 285.71 | -1.00 |
| 3 | gc__asia__rr2p0__long__no_mon__low_or_mid_atr__small_orb_only | CHALLENGER | long | 2.00 | Monday | low_or_mid_atr | small_orb_only | 48 | 20.45 | 1.84 | -2.00 | 10.23 | 0.51 | 0.92 | 361.90 | -1.00 |

### GC LDN

- Trials: raw `864`, effective `18`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.0838`, ATR p66 `1.3308`, ORB p33 `0.1106`, ORB p66 `0.1612`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | gc__ldn__rr2p0__short__no_fri__small_or_mid_orb | REJECT | short | 2.00 | Friday | none | small_or_mid_orb | 105 | 24.69 | 1.47 | -9.00 | 2.74 | 0.46 | 0.72 | 261.90 | -7.33 |
| 2 | gc__ldn__rr1p25__short__no_fri__small_or_mid_orb | REJECT | short | 1.25 | Friday | none | small_or_mid_orb | 105 | 20.64 | 1.46 | -6.00 | 3.44 | 0.50 | 0.56 | 180.95 | -5.08 |
| 3 | gc__ldn__rr1p5__short__no_fri__small_or_mid_orb | REJECT | short | 1.50 | Friday | none | small_or_mid_orb | 105 | 22.67 | 1.47 | -7.00 | 3.24 | 0.50 | 0.71 | 257.14 | -7.83 |

### SI NY

- Trials: raw `864`, effective `26`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `2.2086`, ATR p66 `2.6496`, ORB p33 `0.4691`, ORB p66 `0.6624`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | si__ny__rr1p0__both__no_tue__small_or_mid_orb | PROMOTE_TO_EXACT_REPLAY | both | 1.00 | Tuesday | none | small_or_mid_orb | 268 | 33.04 | 1.29 | -5.00 | 6.61 | 0.51 | 0.61 | 204.76 | 5.66 |
| 2 | si__ny__rr1p0__both__no_tue__low_or_mid_atr | PROMOTE_TO_EXACT_REPLAY | both | 1.00 | Tuesday | low_or_mid_atr | none | 261 | 36.81 | 1.33 | -5.00 | 7.36 | 0.62 | 0.77 | 285.71 | 4.44 |
| 3 | si__ny__rr1p0__long__no_tue | PROMOTE_TO_EXACT_REPLAY | long | 1.00 | Tuesday | none | none | 267 | 33.74 | 1.30 | -7.00 | 4.82 | 0.53 | 0.58 | 190.48 | 7.66 |

### SI Asia

- Trials: raw `864`, effective `20`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `2.2086`, ATR p66 `2.6496`, ORB p33 `0.1518`, ORB p66 `0.2511`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | si__asia__rr2p0__long__none__small_or_mid_orb | REJECT | long | 2.00 | None | none | small_or_mid_orb | 280 | 11.51 | 1.06 | -21.00 | 0.55 | 0.08 | 0.30 | 52.38 | -26.59 |
| 2 | si__asia__rr2p0__long__no_fri__small_or_mid_orb | REJECT | long | 2.00 | Friday | none | small_or_mid_orb | 280 | 11.51 | 1.06 | -21.00 | 0.55 | 0.08 | 0.30 | 52.38 | -26.59 |
| 3 | si__asia__rr1p0__long__no_tue__small_or_mid_orb | REJECT | long | 1.00 | Tuesday | none | small_or_mid_orb | 233 | 9.00 | 1.08 | -14.00 | 0.64 | 0.09 | 0.34 | 71.43 | -14.00 |

### SI LDN

- Trials: raw `864`, effective `21`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `2.2086`, ATR p66 `2.6496`, ORB p33 `0.2154`, ORB p66 `0.3143`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | si__ldn__rr1p0__long__no_thu__low_atr_only__small_orb_only | CHALLENGER | long | 1.00 | Thursday | low_atr_only | small_orb_only | 75 | 18.73 | 1.65 | -7.00 | 2.68 | 0.58 | 0.50 | 152.38 | -3.00 |
| 2 | si__ldn__rr1p0__long__no_thu__low_or_mid_atr__small_orb_only | REJECT | long | 1.00 | Thursday | low_or_mid_atr | small_orb_only | 115 | 20.31 | 1.42 | -7.70 | 2.64 | 0.49 | 0.58 | 190.48 | -2.00 |
| 3 | si__ldn__rr1p0__long__no_tue__low_atr_only__small_orb_only | REJECT | long | 1.00 | Tuesday | low_atr_only | small_orb_only | 70 | 15.12 | 1.55 | -5.00 | 3.02 | 0.44 | 0.55 | 176.19 | -6.00 |

### RTY NY

- Trials: raw `864`, effective `22`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.6008`, ATR p66 `2.0285`, ORB p33 `0.5466`, ORB p66 `0.7522`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | rty__ny__rr1p0__both__no_thu__low_or_mid_atr | PROMOTE_TO_EXACT_REPLAY | both | 1.00 | Thursday | low_or_mid_atr | none | 246 | 50.00 | 1.51 | -9.00 | 5.56 | 0.89 | 0.65 | 223.81 | 3.36 |
| 2 | rty__ny__rr2p0__both__none__small_or_mid_orb | CHALLENGER | both | 2.00 | None | none | small_or_mid_orb | 300 | 52.84 | 1.30 | -17.08 | 3.09 | 0.56 | 0.50 | 147.62 | -18.89 |
| 3 | rty__ny__rr1p5__long__no_thu__low_or_mid_atr | CHALLENGER | long | 1.50 | Thursday | low_or_mid_atr | none | 168 | 45.16 | 1.55 | -8.50 | 5.31 | 0.80 | 0.67 | 233.33 | -8.64 |

### RTY Asia

- Trials: raw `864`, effective `27`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.6008`, ATR p66 `2.0285`, ORB p33 `0.0908`, ORB p66 `0.1474`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | rty__asia__rr2p0__both__no_thu__low_atr_only__small_orb_only | REJECT | both | 2.00 | Thursday | low_atr_only | small_orb_only | 45 | 0.97 | 1.03 | -7.36 | 0.13 | 0.03 | 0.30 | 47.62 | 1.49 |
| 2 | rty__asia__rr1p0__long__none__large_orb_only | REJECT | long | 1.00 | None | none | large_orb_only | 91 | 2.44 | 1.06 | -11.00 | 0.22 | 0.04 | 0.10 | -52.38 | 2.00 |
| 3 | rty__asia__rr1p0__long__no_fri__large_orb_only | REJECT | long | 1.00 | Friday | none | large_orb_only | 91 | 2.44 | 1.06 | -11.00 | 0.22 | 0.04 | 0.10 | -52.38 | 2.00 |

### RTY LDN

- Trials: raw `864`, effective `21`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `1.6008`, ATR p66 `2.0285`, ORB p33 `0.1428`, ORB p66 `0.2302`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | rty__ldn__rr1p5__both__no_mon__low_atr_only__small_orb_only | REJECT | both | 1.50 | Monday | low_atr_only | small_orb_only | 88 | 11.88 | 1.28 | -4.30 | 2.77 | 0.20 | 0.70 | 252.38 | 14.54 |
| 2 | rty__ldn__rr2p0__both__no_mon__low_atr_only__small_orb_only | REJECT | both | 2.00 | Monday | low_atr_only | small_orb_only | 88 | 11.47 | 1.25 | -6.61 | 1.73 | 0.15 | 0.68 | 238.10 | 15.02 |
| 3 | rty__ldn__rr1p0__both__no_mon__low_atr_only__small_orb_only | REJECT | both | 1.00 | Monday | low_atr_only | small_orb_only | 88 | 7.51 | 1.21 | -4.30 | 1.75 | 0.14 | 0.68 | 238.10 | 11.04 |

### YM NY

- Trials: raw `864`, effective `21`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `0.8697`, ATR p66 `1.2263`, ORB p33 `0.2774`, ORB p66 `0.4021`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ym__ny__rr1p5__short__no_tue | CHALLENGER | short | 1.50 | Tuesday | none | none | 133 | 28.04 | 1.41 | -5.50 | 5.10 | 0.50 | 0.74 | 271.43 | -11.00 |
| 2 | ym__ny__rr1p0__both__no_thu | REJECT | both | 1.00 | Thursday | none | none | 376 | 34.76 | 1.20 | -11.65 | 2.98 | 0.45 | 0.49 | 142.86 | 1.00 |
| 3 | ym__ny__rr1p5__short__none | REJECT | short | 1.50 | None | none | none | 164 | 29.54 | 1.34 | -7.00 | 4.22 | 0.47 | 0.56 | 180.95 | -9.50 |

### YM Asia

- Trials: raw `864`, effective `24`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `0.8697`, ATR p66 `1.2263`, ORB p33 `0.0551`, ORB p66 `0.0938`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ym__asia__rr1p25__long__no_tue | REJECT | long | 1.25 | Tuesday | none | none | 177 | 25.45 | 1.29 | -8.25 | 3.08 | 0.39 | 0.54 | 171.43 | -3.25 |
| 2 | ym__asia__rr2p0__long__no_wed__small_or_mid_orb | REJECT | long | 2.00 | Wednesday | none | small_or_mid_orb | 107 | 27.83 | 1.49 | -7.05 | 3.95 | 0.47 | 0.51 | 157.14 | -7.00 |
| 3 | ym__asia__rr1p25__long__no_mon | REJECT | long | 1.25 | Monday | none | none | 177 | 27.94 | 1.33 | -10.00 | 2.79 | 0.45 | 0.53 | 166.67 | -1.25 |

### YM LDN

- Trials: raw `864`, effective `21`.
- Gates calibrated on market-only 2021-2024 distributions: ATR p33 `0.8697`, ATR p66 `1.2263`, ORB p33 `0.0874`, ORB p66 `0.1526`.

| Rank | Rule | Verdict | Dir | RR | DOW | ATR | ORB | Trades | R | PF | DD | Cal | DSR | Pay% | EV | HO R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ym__ldn__rr1p0__both__no_mon__low_or_mid_atr__small_or_mid_orb | REJECT | both | 1.00 | Monday | low_or_mid_atr | small_or_mid_orb | 248 | 19.74 | 1.19 | -9.23 | 2.14 | 0.28 | 0.58 | 190.48 | 7.41 |
| 2 | ym__ldn__rr1p0__both__no_mon | REJECT | both | 1.00 | Monday | none | none | 471 | 20.66 | 1.10 | -13.27 | 1.56 | 0.18 | 0.50 | 152.38 | -5.94 |
| 3 | ym__ldn__rr1p0__long__no_mon | REJECT | long | 1.00 | Monday | none | none | 341 | 21.79 | 1.15 | -11.13 | 1.96 | 0.25 | 0.53 | 166.67 | -0.20 |

## Method Notes

- Data window: `2021-01-01` to `2026-06-05` loaded; discovery `2021-01-01`-`2024-12-31`; holdout `2025-01-01` onward.
- Anchor: 15m session ORB, first 5m continuation FVG outside range, ATR14, 10% ATR stop, 2% ATR gap, one trade per session day, single-target exits.
- RR/direction grid: RR `[1.0, 1.25, 1.5, 2.0]`, direction `['long', 'short', 'both']`.
- Causal filters: no single weekday, low/low-mid prior rolling ATR, small/small-mid/large ORB range.
- First-payout model: $50k start, $2k trailing DD capped at $50k, $52.5k payout trigger, $500 first withdrawal, $100 challenge fee, $500/R, 14-day staggered account starts.
- PBO/CSCV is not implemented in this scan. PSR/DSR/effective trials are reported for multiple-testing discipline.
- `PROMOTE_TO_EXACT_REPLAY` means promotion to exact execution replay / paper-candidate review, not live deployment.

## Artifacts

- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/cross_asset_orb_base_matrix_20260612/summary.json`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/cross_asset_orb_base_matrix_20260612/top3_candidates.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/cross_asset_orb_base_matrix_20260612/all_candidates.csv`
- `/Users/jeffreygatbonton/Desktop/Code/gat_capital/trading_engine/backtesting/data/results/cross_asset_orb_base_matrix_20260612/report.md`

