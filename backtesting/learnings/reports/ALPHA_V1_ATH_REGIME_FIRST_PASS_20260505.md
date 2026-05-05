# ALPHA_V1 ATH Regime First Pass

Date: 2026-05-05

## Scope

- Source trades: `data/results/alpha_v1_orb_reentry_promotion_20260502/baseline_trades.csv`
- Trade set: active ALPHA_V1 baseline from the reentry promotion packet, `3,470` filled trades.
- Instruments: local continuous futures data only (`NQ_5m.parquet`, `ES_5m.parquet`).
- ATH definition: expanding all-time high of the available continuous futures 5-minute high, with history starting at each file's first bar.
- Decision-safe context: `signal` includes the closed setup bar; `fill` uses only prior completed 5-minute data before the fill timestamp.

This is attribution, not a promoted filter. Buckets with fewer than 30 trades should be treated as color only.

## Baseline Check

| Leg | Trades | Net R | Avg R | WR | PF | DD R |
| --- | --- | --- | --- | --- | --- | --- |
| es_asia_orb | 1422 | 145.90 | 0.10 | 54.4% | 1.29 | -12.30 |
| es_ny_orb | 845 | 127.60 | 0.15 | 61.1% | 1.39 | -10.90 |
| nq_asia_orb | 722 | 213.50 | 0.30 | 45.7% | 1.56 | -10.20 |
| nq_ny_htf_lsi | 481 | 92.60 | 0.19 | 52.8% | 1.45 | -10.90 |
| portfolio | 3470 | 579.50 | 0.17 | 54.0% | 1.41 | -15.40 |

## Portfolio By Signal-Time ATH Distance

| Bucket | Trades | Net R | Avg R | WR | TP2 | SL |
| --- | --- | --- | --- | --- | --- | --- |
| 0-0.5% | 756 | 162.40 | 0.21 | 56.3% | 11.2% | 32.9% |
| 0.5-1% | 381 | 2.60 | 0.01 | 46.7% | 10.8% | 42.8% |
| 1-2% | 463 | 94.80 | 0.20 | 55.5% | 11.2% | 38.2% |
| 2-5% | 650 | 90.10 | 0.14 | 51.5% | 12.2% | 41.4% |
| 5-10% | 562 | 78.10 | 0.14 | 53.7% | 12.6% | 40.7% |
| >10% | 658 | 151.50 | 0.23 | 57.1% | 15.3% | 39.5% |

## Per-Leg Near/Far Split

Near ATH = above prior ATH through 2% below prior ATH. Far = more than 2% below prior ATH.

| Leg | Trades | Near ATH R | Near Avg | Far R | Far Avg | Best >=30 | Worst >=30 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| es_asia_orb | 1422 | 75.80 | 0.11 | 70.00 | 0.09 | 0-0.5% (0.188R) | 0.5-1% (0.023R) |
| es_ny_orb | 845 | 57.10 | 0.14 | 70.50 | 0.16 | >10% (0.209R) | 0.5-1% (-0.055R) |
| nq_asia_orb | 722 | 98.00 | 0.30 | 115.50 | 0.29 | >10% (0.465R) | 0.5-1% (0.071R) |
| nq_ny_htf_lsi | 481 | 28.90 | 0.15 | 63.70 | 0.22 | 2-5% (0.412R) | 0.5-1% (-0.015R) |

## Recent 2024+ Near/Far Split

| Leg | Trades | Near ATH R | Near Avg | Far R | Far Avg | Best >=30 | Worst >=30 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| es_asia_orb | 320 | 33.20 | 0.16 | 13.90 | 0.12 | 0-0.5% (0.354R) | 0.5-1% (-0.060R) |
| es_ny_orb | 200 | 10.30 | 0.07 | 11.90 | 0.19 | 0-0.5% (0.312R) | 0.5-1% (-0.162R) |
| nq_asia_orb | 156 | 27.00 | 0.35 | 27.50 | 0.35 | 0-0.5% (0.591R) | 2-5% (0.575R) |
| nq_ny_htf_lsi | 105 | 15.30 | 0.37 | 19.50 | 0.30 | 2-5% (0.479R) | 2-5% (0.479R) |

## Strongest Full-History Percent Buckets

| Leg | Bucket | Trades | Net R | Avg R | Base Avg R | Delta | WR | TP2 | SL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_ny_htf_lsi | 2-5% | 102 | 42.10 | 0.41 | 0.19 | 0.22 | 59.8% | 9.8% | 38.2% |
| nq_asia_orb | >10% | 139 | 64.70 | 0.47 | 0.30 | 0.17 | 50.4% | 7.9% | 48.2% |
| nq_asia_orb | 1-2% | 95 | 43.30 | 0.46 | 0.30 | 0.16 | 46.3% | 7.4% | 53.7% |
| nq_ny_htf_lsi | 1-2% | 64 | 20.10 | 0.31 | 0.19 | 0.12 | 62.5% | 4.7% | 31.2% |
| es_asia_orb | 0-0.5% | 325 | 61.10 | 0.19 | 0.10 | 0.09 | 59.4% | 18.8% | 21.2% |
| es_ny_orb | >10% | 155 | 32.40 | 0.21 | 0.15 | 0.06 | 64.5% | 9.7% | 35.5% |
| es_ny_orb | 0-0.5% | 202 | 41.90 | 0.21 | 0.15 | 0.06 | 60.4% | 5.9% | 36.1% |
| es_ny_orb | 5-10% | 137 | 27.60 | 0.20 | 0.15 | 0.05 | 65.0% | 8.0% | 35.0% |
| es_asia_orb | >10% | 250 | 33.30 | 0.13 | 0.10 | 0.03 | 57.2% | 27.2% | 37.2% |
| es_ny_orb | 1-2% | 115 | 20.50 | 0.18 | 0.15 | 0.03 | 62.6% | 4.3% | 37.4% |

## Strongest Full-History ATR-Normalized Buckets

| Leg | Bucket | Trades | Net R | Avg R | Base Avg R | Delta | WR | TP2 | SL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_asia_orb | >5 ATR | 158 | 75.70 | 0.48 | 0.30 | 0.18 | 50.6% | 7.6% | 48.7% |
| nq_ny_htf_lsi | 2-5 ATR | 140 | 41.00 | 0.29 | 0.19 | 0.10 | 55.0% | 9.3% | 40.7% |
| es_asia_orb | 0-0.5 ATR | 262 | 51.70 | 0.20 | 0.10 | 0.10 | 59.5% | 21.0% | 22.1% |
| nq_asia_orb | 0.5-1 ATR | 88 | 34.20 | 0.39 | 0.30 | 0.09 | 46.6% | 3.4% | 52.3% |
| es_ny_orb | 0-0.5 ATR | 169 | 34.80 | 0.21 | 0.15 | 0.06 | 60.9% | 5.9% | 35.5% |
| es_ny_orb | 1-2 ATR | 130 | 25.80 | 0.20 | 0.15 | 0.05 | 65.4% | 4.6% | 34.6% |
| nq_ny_htf_lsi | 1-2 ATR | 81 | 17.00 | 0.21 | 0.19 | 0.02 | 56.8% | 3.7% | 37.0% |
| es_asia_orb | >5 ATR | 382 | 44.70 | 0.12 | 0.10 | 0.01 | 57.3% | 23.8% | 35.6% |
| nq_ny_htf_lsi | >5 ATR | 122 | 24.30 | 0.20 | 0.19 | 0.01 | 52.5% | 7.4% | 40.2% |
| es_ny_orb | >5 ATR | 229 | 32.70 | 0.14 | 0.15 | -0.01 | 61.1% | 8.3% | 38.9% |

## Simple Filter Probe

This is not optimization. It only tests the most obvious weak bucket from the first pass.

| Window | Filter | Removed | Trades | Net R | Delta R | Avg R | PF | DD R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | baseline | 0 | 3470 | 579.50 | 0.00 | 0.17 | 1.41 | -15.40 |
| full | skip_pct_0p5_1_all | 381 | 3089 | 576.90 | -2.60 | 0.19 | 1.46 | -15.40 |
| full | skip_lsi_atr_0p5_1 | 60 | 3410 | 582.20 | 2.60 | 0.17 | 1.42 | -15.40 |
| 2024+ | baseline | 0 | 781 | 158.60 | 0.00 | 0.20 | 1.51 | -14.40 |
| 2024+ | skip_pct_0p5_1_all | 119 | 662 | 161.90 | 3.30 | 0.24 | 1.64 | -14.40 |
| 2024+ | skip_lsi_atr_0p5_1 | 15 | 766 | 157.50 | -1.10 | 0.21 | 1.52 | -14.40 |
| 2025+ | baseline | 0 | 423 | 106.30 | 0.00 | 0.25 | 1.67 | -11.20 |
| 2025+ | skip_pct_0p5_1_all | 57 | 366 | 111.50 | 5.20 | 0.30 | 1.87 | -8.50 |
| 2025+ | skip_lsi_atr_0p5_1 | 4 | 419 | 105.40 | -0.90 | 0.25 | 1.67 | -10.20 |

## First-Pass Read

1. The clearest broad weak zone is `0.5-1%` below futures ATH at signal time. Full history is basically flat (`381` trades for `+2.6R`), and skipping it raises average R and PF while preserving almost all full-history net R.
2. The recent read is stronger: skipping `0.5-1%` improves `2024+` from `+158.6R` to `+161.9R`, and `2025+` from `+106.3R / -11.2R DD` to `+111.5R / -8.5R DD`.
3. This is not a universal "near ATH is good" result. ES Asia likes the closest ATH band, NQ Asia is strongest in deeper ATH drawdowns or 1-2% below ATH, and NQ NY HTF-LSI is best around 2-5% below ATH.
4. The next honest step is a pre-registered same-regime OOS check for `skip_pct_0p5_1_all`, plus leg-specific diagnostics for ES-near-ATH and HTF-LSI 2-5% behavior. Do not promote any threshold from this report directly.

## Artifacts

- Annotated trades: `data/results/alpha_v1_ath_regime_first_pass_20260505/annotated_trades.csv`
- Bucket summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/bucket_summary.csv`
- Baseline summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/baseline_summary.csv`
- Filter probes: `data/results/alpha_v1_ath_regime_first_pass_20260505/filter_evaluation.csv`
- Machine summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/summary.json`
