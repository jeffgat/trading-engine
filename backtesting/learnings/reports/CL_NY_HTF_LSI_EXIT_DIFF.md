# CL NY HTF-LSI Exit Diff

- Objective: explain why the exact replay is still slightly softer than research after full trade-count parity was closed.
- Candidate: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`
- Window: `2016-01-01` to `2026-03-31`

## Key Findings

- Pre-holdout matched `425` trades and still gave back `4.654R` in exact replay.
- Holdout matched `45` trades and still gave back `-0.041R` in exact replay.
- Pre-holdout exit-type disagreements: `4` trades. Same-exit-type but different R: `117` trades.
- Holdout exit-type disagreements: `0` trades. Same-exit-type but different R: `16` trades.

## Window Summary

| Window | Matched Trades | Exit-Type Diff | Same-Type R Diff | Exact Worse | Exact Better | Net Delta R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pre-Holdout | 425 | 4 | 117 | 75 | 46 | 4.654 |
| Holdout | 45 | 0 | 16 | 10 | 6 | -0.041 |

## Pre-Holdout Transition Mix

- `sl->sl`: `234`
- `tp1_tp2->tp1_tp2`: `79`
- `eod->eod`: `44`
- `tp1_be->tp1_be`: `34`
- `tp1_eod->tp1_eod`: `30`
- `sl->tp1_be`: `3`
- `eod->tp1_be`: `1`

## Holdout Transition Mix

- `sl->sl`: `22`
- `tp1_tp2->tp1_tp2`: `12`
- `eod->eod`: `6`
- `tp1_be->tp1_be`: `3`
- `tp1_eod->tp1_eod`: `2`

## Pre-Holdout Worst Dates

- `2025-02-19`: `-0.379`
- `2022-05-11`: `-0.12`
- `2022-07-27`: `-0.12`
- `2022-06-09`: `-0.094`
- `2024-10-11`: `-0.083`
- `2023-04-14`: `-0.067`
- `2022-07-28`: `-0.065`
- `2019-03-12`: `-0.056`
- `2020-03-25`: `-0.055`
- `2021-02-17`: `-0.055`
- `2022-11-22`: `-0.049`
- `2021-12-06`: `-0.046`

## Holdout Worst Dates

- `2026-02-02`: `-0.083`
- `2025-10-07`: `-0.04`
- `2025-10-20`: `-0.035`
- `2025-06-27`: `-0.032`
- `2025-10-03`: `-0.019`
- `2025-12-03`: `-0.019`
- `2025-11-03`: `-0.018`
- `2025-10-21`: `-0.017`
- `2025-04-22`: `-0.015`
- `2025-09-22`: `-0.015`
- `2025-04-04`: `0.0`
- `2025-04-09`: `0.0`

## Holdout Exit-Type Diff Samples

- `none`

## Holdout Same-Type R Diff Samples

- `2026-02-02 2026-02-02T13:58:00` `tp1_eod` deltaR `-0.083` exitSec `0`
- `2025-10-28 2025-10-28T11:48:00` `eod` deltaR `0.080` exitSec `2`
- `2025-07-18 2025-07-18T11:25:00` `eod` deltaR `0.058` exitSec `21`
- `2025-10-07 2025-10-07T09:11:00` `tp1_tp2` deltaR `-0.040` exitSec `27`
- `2025-04-21 2025-04-21T10:01:00` `tp1_be` deltaR `0.039` exitSec `7`
- `2025-10-02 2025-10-02T09:07:00` `tp1_be` deltaR `0.036` exitSec `54`
- `2025-10-20 2025-10-20T09:17:00` `tp1_tp2` deltaR `-0.035` exitSec `11`
- `2025-06-27 2025-06-27T11:45:00` `eod` deltaR `-0.032` exitSec `0`
- `2025-10-01 2025-10-01T09:33:00` `tp1_be` deltaR `0.029` exitSec `51`
- `2025-12-03 2025-12-03T09:20:00` `tp1_tp2` deltaR `-0.019` exitSec `23`
- `2025-10-03 2025-10-03T08:38:00` `tp1_tp2` deltaR `-0.019` exitSec `14`
- `2025-11-03 2025-11-03T10:34:00` `tp1_tp2` deltaR `-0.018` exitSec `4`
- `2025-10-21 2025-10-21T10:07:00` `tp1_tp2` deltaR `-0.017` exitSec `31`
- `2025-09-22 2025-09-22T09:32:00` `tp1_tp2` deltaR `-0.015` exitSec `34`
- `2025-04-22 2025-04-22T09:21:00` `tp1_tp2` deltaR `-0.015` exitSec `5`
- `2026-03-11 2026-03-11T10:04:00` `eod` deltaR `0.010` exitSec `0`