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

## Yearly Dead-Zone Stability

Dead zone = signal-time `0.5-1%` below futures ATH, removed from all legs.

| Year | Base R | Dead Trades | Dead R | Dead Avg | Gated R | Delta R | DD Delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2016 | 30.40 | 42 | -6.80 | -0.16 | 37.30 | 6.80 | 3.10 |
| 2017 | 59.30 | 63 | 3.90 | 0.06 | 55.40 | -3.90 | 1.40 |
| 2018 | 44.90 | 29 | -0.60 | -0.02 | 45.50 | 0.60 | 0.00 |
| 2019 | 39.50 | 41 | -0.20 | -0.01 | 39.70 | 0.20 | -0.30 |
| 2020 | 60.20 | 30 | 4.60 | 0.15 | 55.60 | -4.60 | 2.00 |
| 2021 | 41.70 | 50 | 0.40 | 0.01 | 41.30 | -0.40 | -1.90 |
| 2022 | 70.40 | 1 | 0.30 | 0.27 | 70.10 | -0.30 | 0.00 |
| 2023 | 74.50 | 6 | 4.50 | 0.74 | 70.00 | -4.50 | 0.00 |
| 2024 | 52.30 | 62 | 1.90 | 0.03 | 50.40 | -1.90 | 0.00 |
| 2025 | 97.50 | 48 | -6.60 | -0.14 | 104.10 | 6.60 | 2.70 |
| 2026 | 8.70 | 9 | 1.40 | 0.16 | 7.30 | -1.40 | 0.00 |

## Rolling Two-Year Check

| Window | Base R | Dead Trades | Dead R | Dead Avg | Gated R | Delta R | DD Delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2016-2017 | 89.70 | 105 | -3.00 | -0.03 | 92.70 | 3.00 | 1.80 |
| 2017-2018 | 104.20 | 92 | 3.20 | 0.04 | 101.00 | -3.20 | 0.00 |
| 2018-2019 | 84.40 | 70 | -0.80 | -0.01 | 85.20 | 0.80 | 0.00 |
| 2019-2020 | 99.70 | 71 | 4.40 | 0.06 | 95.30 | -4.40 | 2.00 |
| 2020-2021 | 101.90 | 80 | 5.00 | 0.06 | 96.90 | -5.00 | 2.00 |
| 2021-2022 | 112.10 | 51 | 0.60 | 0.01 | 111.50 | -0.60 | -2.70 |
| 2022-2023 | 144.90 | 7 | 4.70 | 0.68 | 140.20 | -4.70 | 0.00 |
| 2023-2024 | 126.80 | 68 | 6.40 | 0.09 | 120.40 | -6.40 | 0.00 |
| 2024-2025 | 149.80 | 110 | -4.70 | -0.04 | 154.50 | 4.70 | 0.00 |
| 2025-2026 | 106.30 | 57 | -5.20 | -0.09 | 111.50 | 5.20 | 2.70 |

## Daily-R Gate Comparison

| Window | Profile | Trades | Removed | Net R | Delta R | Sharpe | DD R | DD Delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | baseline | 3470 | 0 | 579.50 | 0.00 | 2.04 | -14.50 | 0.00 |
| full | skip_pct_0p5_1_all | 3089 | 381 | 576.90 | -2.60 | 2.14 | -14.50 | -0.00 |
| 2024+ | baseline | 781 | 0 | 158.60 | 0.00 | 2.50 | -14.40 | 0.00 |
| 2024+ | skip_pct_0p5_1_all | 662 | 119 | 161.90 | 3.30 | 2.77 | -14.40 | 0.00 |
| 2025+ | baseline | 423 | 0 | 106.30 | 0.00 | 3.11 | -10.90 | 0.00 |
| 2025+ | skip_pct_0p5_1_all | 366 | 57 | 111.50 | 5.20 | 3.50 | -8.20 | 2.70 |

## Worst 90-Day Windows

| Profile | Start | End | Net R | DD R | Net $ | DD $ |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 2023-02-01 | 2023-05-01 | 3.30 | -14.50 | 610.00 | -3795.00 |
| baseline | 2022-12-22 | 2023-03-21 | 5.70 | -14.50 | 822.00 | -3883.00 |
| baseline | 2023-01-18 | 2023-04-17 | 6.20 | -14.50 | 1325.00 | -3883.00 |
| baseline | 2022-12-28 | 2023-03-27 | 9.40 | -14.50 | 1760.00 | -3883.00 |
| baseline | 2022-12-05 | 2023-03-04 | -6.40 | -14.50 | -1612.00 | -3883.00 |
| skip_pct_0p5_1_all | 2021-12-01 | 2022-02-28 | -10.00 | -14.50 | -2990.00 | -4099.00 |
| skip_pct_0p5_1_all | 2021-12-02 | 2022-03-01 | -9.00 | -14.50 | -2595.00 | -4099.00 |
| skip_pct_0p5_1_all | 2021-12-03 | 2022-03-02 | -7.40 | -14.50 | -2114.00 | -4099.00 |
| skip_pct_0p5_1_all | 2021-12-04 | 2022-03-03 | -6.80 | -14.50 | -1994.00 | -4099.00 |
| skip_pct_0p5_1_all | 2021-12-05 | 2022-03-04 | -6.20 | -14.50 | -1860.00 | -4099.00 |

## Funded First-Payout Comparison

This uses the same simple 14-day staggered first-payout model as the reentry promotion packet and current ALPHA leg risk sizing from the source trade export.

| Window | Profile | Accounts | Pay% | Breach% | Payouts | Breaches | Open | EV/acct | Med PayD | MCBch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | baseline | 260 | 73.80 | 24.60 | 192 | 64 | 4 | 219.00 | 37.00 | 10 |
| full | skip_pct_0p5_1_all | 260 | 70.00 | 27.70 | 182 | 72 | 6 | 200.00 | 33.00 | 9 |
| 2024+ | baseline | 59 | 81.40 | 11.90 | 48 | 7 | 4 | 257.00 | 32.00 | 4 |
| 2024+ | skip_pct_0p5_1_all | 59 | 64.40 | 25.40 | 38 | 15 | 6 | 172.00 | 28.50 | 9 |
| 2025+ | baseline | 32 | 84.40 | 6.20 | 27 | 2 | 3 | 272.00 | 34.00 | 2 |
| 2025+ | skip_pct_0p5_1_all | 32 | 84.40 | 0.00 | 27 | 0 | 5 | 272.00 | 30.00 | 0 |

## First-Pass Read

1. The clearest broad weak zone is `0.5-1%` below futures ATH at signal time. Full history is basically flat (`381` trades for `+2.6R`), and skipping it raises average R and PF while preserving almost all full-history net R.
2. The recent read is stronger: skipping `0.5-1%` improves `2024+` from `+158.6R` to `+161.9R`, and `2025+` from `+106.3R / -11.2R DD` to `+111.5R / -8.5R DD`.
3. Funded-account behavior is the blocker: the broad skip worsens full-history payout rate (`73.8%` to `70.0%`) and 2024+ payout rate (`81.4%` to `64.4%`). It only clearly helps the opened 2025+ cohort by removing breaches while preserving payout count.
4. Yearly attribution is mixed: the dead zone was harmful in 2016 and 2025, mildly harmful in 2018-2019, but helpful in 2017, 2020, 2023, 2024, and 2026 YTD. Treat this as a risk-shaping diagnostic, not a broad gate.
5. This is not a universal "near ATH is good" result. ES Asia likes the closest ATH band, NQ Asia is strongest in deeper ATH drawdowns or 1-2% below ATH, and NQ NY HTF-LSI is best around 2-5% below ATH.
6. The broad `skip_pct_0p5_1_all` gate is **NO-GO for immediate promotion** from this post-filter evidence. Better next steps are leg-specific ATH theses and exact engine replay only after a gate is narrowed enough to preserve account-flow quality.
7. The gate remains `post_filter_only` / research-only until engine support can skip the setup before arming an order and exact replay can account for missed/alternate same-session opportunities.

## Artifacts

- Annotated trades: `data/results/alpha_v1_ath_regime_first_pass_20260505/annotated_trades.csv`
- Bucket summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/bucket_summary.csv`
- Baseline summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/baseline_summary.csv`
- Filter probes: `data/results/alpha_v1_ath_regime_first_pass_20260505/filter_evaluation.csv`
- Yearly dead-zone attribution: `data/results/alpha_v1_ath_regime_first_pass_20260505/yearly_dead_zone_attribution.csv`
- Rolling two-year attribution: `data/results/alpha_v1_ath_regime_first_pass_20260505/rolling_2y_dead_zone_attribution.csv`
- Daily-R comparison: `data/results/alpha_v1_ath_regime_first_pass_20260505/daily_r_comparison.csv`
- Daily summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/daily_summary.csv`
- Worst 90-day windows: `data/results/alpha_v1_ath_regime_first_pass_20260505/worst_90d_windows.csv`
- Funded payout summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/funded_first_payout_summary.csv`
- Funded account outcomes: `data/results/alpha_v1_ath_regime_first_pass_20260505/funded_first_payout_accounts.csv`
- Machine summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/summary.json`
