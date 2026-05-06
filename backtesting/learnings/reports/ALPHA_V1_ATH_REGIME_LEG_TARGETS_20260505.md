# ALPHA_V1 ATH Regime Leg Targets

Date: 2026-05-05

## Scope

- Source: `data/results/alpha_v1_ath_regime_first_pass_20260505/annotated_trades.csv`
- Trade set: active ALPHA_V1 baseline, signal-time ATH features only, futures data only.
- Purpose: test the leg-specific ATH targets suggested by the first pass.
- Status: post-filter research. Any promising row needs a live pre-trade ATH gate and exact replay before promotion.

## Profile Definitions

| Profile | Target | Thesis | Deploy |
| --- | --- | --- | --- |
| baseline | Portfolio | Current active ALPHA_V1 baseline. | live_native |
| es_asia_near_0_0p5_only | ES Asia ORB | Test whether ES Asia should become a closest-to-ATH specialist. | post_filter_only |
| es_asia_skip_mid_0p5_5 | ES Asia ORB | Keep ES Asia flow near ATH and far below ATH, skip the low-quality middle bands. | post_filter_only |
| nq_lsi_2_5_only | NQ NY HTF-LSI | Test the cleanest HTF-LSI sweet spot from the first pass. | post_filter_only |
| nq_lsi_1_5_only | NQ NY HTF-LSI | Test whether broadening HTF-LSI to the adjacent strong bucket preserves quality and flow. | post_filter_only |
| nq_lsi_skip_weak_0p5_1_5_10 | NQ NY HTF-LSI | Test a surgical HTF-LSI weak-bucket removal without starving the leg. | post_filter_only |
| nq_asia_top3_only | NQ Asia ORB | Test NQ Asia's strongest bands while avoiding its soft middle. | post_filter_only |
| nq_asia_skip_soft_0p5_1_2_5 | NQ Asia ORB | Test a less restrictive NQ Asia weak-bucket removal. | post_filter_only |
| es_ny_skip_0p5_1 | ES NY ORB | Check the other ALPHA_V1 leg's clearly negative ATH dead zone. | post_filter_only |
| combo_negative_only_skip | Portfolio | Remove only the buckets that are negative full-history in their own leg. | post_filter_only |
| combo_surgical_weak_skip | Portfolio | Combine the most plausible weak-bucket removals while preserving broad portfolio structure. | post_filter_only |

## Target-Leg Thesis Fit, Full History

This isolates the target leg only. Target = trades that pass that profile's ATH rule; outside = the same leg's removed trades.

| Profile | Leg | Base T | Base R | Base Avg | Target T | Target R | Target Avg | Target PF | Outside R | Outside Avg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_lsi_2_5_only | NQ NY HTF-LSI | 481 | 92.60 | 0.19 | 102 | 42.10 | 0.41 | 2.05 | 50.50 | 0.13 |
| nq_lsi_1_5_only | NQ NY HTF-LSI | 481 | 92.60 | 0.19 | 166 | 62.10 | 0.37 | 2.01 | 30.50 | 0.10 |
| nq_asia_top3_only | NQ Asia ORB | 722 | 213.50 | 0.30 | 390 | 157.70 | 0.40 | 1.80 | 55.80 | 0.17 |
| es_asia_near_0_0p5_only | ES Asia ORB | 1422 | 145.90 | 0.10 | 325 | 61.10 | 0.19 | 1.69 | 84.80 | 0.08 |
| nq_asia_skip_soft_0p5_1_2_5 | NQ Asia ORB | 722 | 213.50 | 0.30 | 506 | 187.20 | 0.37 | 1.72 | 26.30 | 0.12 |
| nq_lsi_skip_weak_0p5_1_5_10 | NQ NY HTF-LSI | 481 | 92.60 | 0.19 | 353 | 92.90 | 0.26 | 1.67 | -0.30 | -0.00 |
| es_asia_skip_mid_0p5_5 | ES Asia ORB | 1422 | 145.90 | 0.10 | 813 | 115.00 | 0.14 | 1.41 | 30.90 | 0.05 |
| es_ny_skip_0p5_1 | ES NY ORB | 845 | 127.60 | 0.15 | 750 | 132.80 | 0.18 | 1.47 | -5.20 | -0.06 |

## Target-Leg Thesis Fit, 2024+

| Profile | Leg | Base T | Base R | Base Avg | Target T | Target R | Target Avg | Target PF | Outside R | Outside Avg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| es_asia_near_0_0p5_only | ES Asia ORB | 320 | 47.00 | 0.15 | 80 | 28.40 | 0.35 | 2.28 | 18.70 | 0.08 |
| nq_lsi_2_5_only | NQ NY HTF-LSI | 105 | 34.80 | 0.33 | 40 | 19.20 | 0.48 | 2.22 | 15.70 | 0.24 |
| es_asia_skip_mid_0p5_5 | ES Asia ORB | 320 | 47.00 | 0.15 | 118 | 31.30 | 0.27 | 1.84 | 15.80 | 0.08 |
| nq_lsi_1_5_only | NQ NY HTF-LSI | 105 | 34.80 | 0.33 | 57 | 25.10 | 0.44 | 2.25 | 9.70 | 0.20 |
| nq_lsi_skip_weak_0p5_1_5_10 | NQ NY HTF-LSI | 105 | 34.80 | 0.33 | 79 | 30.80 | 0.39 | 2.06 | 4.00 | 0.15 |
| es_ny_skip_0p5_1 | ES NY ORB | 200 | 22.20 | 0.11 | 165 | 27.90 | 0.17 | 1.49 | -5.70 | -0.16 |
| nq_asia_top3_only | NQ Asia ORB | 156 | 54.50 | 0.35 | 77 | 22.30 | 0.29 | 1.56 | 32.20 | 0.41 |
| nq_asia_skip_soft_0p5_1_2_5 | NQ Asia ORB | 156 | 54.50 | 0.35 | 100 | 23.70 | 0.24 | 1.44 | 30.80 | 0.55 |

## Portfolio Overlay Comparison, Full History

| Profile | Removed | Net R | Delta R | Avg R | PF | Trade DD | Daily Sh | Daily DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo_negative_only_skip | 152 | 585.60 | 6.10 | 0.18 | 1.43 | -15.40 | 2.09 | -14.50 |
| es_ny_skip_0p5_1 | 95 | 584.80 | 5.20 | 0.17 | 1.42 | -15.40 | 2.08 | -14.50 |
| nq_lsi_skip_weak_0p5_1_5_10 | 128 | 579.80 | 0.30 | 0.17 | 1.43 | -15.80 | 2.07 | -15.70 |
| baseline | 0 | 579.50 | 0.00 | 0.17 | 1.41 | -15.40 | 2.04 | -14.50 |
| combo_surgical_weak_skip | 598 | 555.10 | -24.50 | 0.19 | 1.49 | -15.40 | 2.17 | -14.60 |
| nq_asia_skip_soft_0p5_1_2_5 | 216 | 553.20 | -26.30 | 0.17 | 1.43 | -15.40 | 2.06 | -14.50 |
| nq_lsi_1_5_only | 315 | 549.10 | -30.50 | 0.17 | 1.43 | -15.80 | 2.02 | -15.70 |
| es_asia_skip_mid_0p5_5 | 609 | 548.60 | -30.90 | 0.19 | 1.46 | -15.40 | 2.09 | -14.70 |
| nq_lsi_2_5_only | 379 | 529.00 | -50.50 | 0.17 | 1.42 | -16.10 | 1.97 | -16.00 |
| nq_asia_top3_only | 332 | 523.70 | -55.80 | 0.17 | 1.42 | -15.40 | 2.04 | -14.50 |
| es_asia_near_0_0p5_only | 1097 | 494.80 | -84.80 | 0.21 | 1.49 | -15.00 | 2.04 | -15.00 |

## Portfolio Overlay Comparison, 2025+

| Profile | Removed | Net R | Delta R | Avg R | PF | Trade DD | Daily Sh | Daily DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| combo_negative_only_skip | 22 | 111.90 | 5.60 | 0.28 | 1.76 | -8.40 | 3.33 | -8.40 |
| es_ny_skip_0p5_1 | 16 | 111.90 | 5.60 | 0.28 | 1.75 | -10.40 | 3.32 | -9.90 |
| baseline | 0 | 106.30 | 0.00 | 0.25 | 1.67 | -11.20 | 3.12 | -10.90 |
| nq_lsi_1_5_only | 23 | 105.80 | -0.40 | 0.27 | 1.71 | -10.90 | 3.18 | -10.60 |
| nq_lsi_skip_weak_0p5_1_5_10 | 11 | 104.10 | -2.20 | 0.25 | 1.68 | -9.20 | 3.08 | -8.90 |
| nq_lsi_2_5_only | 26 | 102.80 | -3.50 | 0.26 | 1.69 | -10.90 | 3.10 | -10.60 |
| es_asia_near_0_0p5_only | 143 | 94.90 | -11.40 | 0.34 | 1.92 | -9.20 | 3.28 | -8.90 |
| es_asia_skip_mid_0p5_5 | 112 | 94.50 | -11.80 | 0.30 | 1.81 | -9.20 | 3.15 | -8.90 |
| combo_surgical_weak_skip | 85 | 90.00 | -16.30 | 0.27 | 1.76 | -8.50 | 3.14 | -8.20 |
| nq_asia_skip_soft_0p5_1_2_5 | 33 | 83.10 | -23.20 | 0.21 | 1.57 | -12.50 | 2.71 | -12.20 |
| nq_asia_top3_only | 45 | 80.80 | -25.50 | 0.21 | 1.58 | -12.50 | 2.72 | -12.20 |

## Portfolio Funded First-Payout Comparison

Full-history combined-account style comparison, matching the first-pass payout model.

| Profile | Leg | Accounts | Pay% | Breach% | Payouts | Breaches | Open | EV/acct | Med PayD | MCBch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | Portfolio | 260 | 73.80 | 24.60 | 192 | 64 | 4 | 219.00 | 37.00 | 10 |
| es_asia_near_0_0p5_only | Portfolio | 260 | 76.90 | 21.50 | 200 | 56 | 4 | 235.00 | 43.00 | 9 |
| es_asia_skip_mid_0p5_5 | Portfolio | 260 | 75.80 | 22.30 | 197 | 58 | 5 | 229.00 | 39.00 | 8 |
| nq_lsi_2_5_only | Portfolio | 260 | 70.80 | 27.70 | 184 | 72 | 4 | 204.00 | 36.50 | 8 |
| nq_lsi_1_5_only | Portfolio | 260 | 71.90 | 26.50 | 187 | 69 | 4 | 210.00 | 36.00 | 7 |
| nq_lsi_skip_weak_0p5_1_5_10 | Portfolio | 260 | 75.00 | 23.50 | 195 | 61 | 4 | 225.00 | 36.00 | 7 |
| nq_asia_top3_only | Portfolio | 260 | 74.60 | 22.70 | 194 | 59 | 7 | 223.00 | 40.00 | 7 |
| nq_asia_skip_soft_0p5_1_2_5 | Portfolio | 260 | 73.50 | 24.20 | 191 | 63 | 6 | 217.00 | 39.00 | 8 |
| es_ny_skip_0p5_1 | Portfolio | 260 | 70.80 | 27.70 | 184 | 72 | 4 | 204.00 | 33.00 | 10 |
| combo_negative_only_skip | Portfolio | 260 | 71.90 | 26.50 | 187 | 69 | 4 | 210.00 | 36.00 | 9 |
| combo_surgical_weak_skip | Portfolio | 260 | 73.80 | 23.50 | 192 | 61 | 7 | 219.00 | 40.00 | 11 |

## Target-Leg Standalone Funded Comparison, Full History

Because ALPHA_V1 is operated as separate accounts, this compares target-leg baseline accounts against target-leg gated accounts.

| Profile | Leg | Accounts | Pay% | Breach% | Payouts | Breaches | Open | EV/acct | Med PayD | MCBch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | ES Asia ORB | 260 | 83.10 | 12.70 | 216 | 33 | 11 | 265.00 | 227.00 | 17 |
| baseline | NQ NY HTF-LSI | 260 | 74.20 | 21.50 | 193 | 56 | 11 | 221.00 | 165.00 | 28 |
| baseline | NQ Asia ORB | 260 | 80.40 | 16.90 | 209 | 44 | 7 | 252.00 | 95.00 | 12 |
| baseline | ES NY ORB | 260 | 64.20 | 33.10 | 167 | 86 | 7 | 171.00 | 134.00 | 27 |
| es_asia_near_0_0p5_only | ES Asia ORB | 260 | 93.50 | 0.00 | 243 | 0 | 17 | 317.00 | 655.00 | 0 |
| es_asia_skip_mid_0p5_5 | ES Asia ORB | 260 | 78.50 | 14.60 | 204 | 38 | 18 | 242.00 | 295.50 | 18 |
| nq_lsi_2_5_only | NQ NY HTF-LSI | 260 | 91.50 | 0.00 | 238 | 0 | 22 | 308.00 | 675.50 | 0 |
| nq_lsi_1_5_only | NQ NY HTF-LSI | 260 | 95.00 | 0.00 | 247 | 0 | 13 | 325.00 | 383.00 | 0 |
| nq_lsi_skip_weak_0p5_1_5_10 | NQ NY HTF-LSI | 260 | 76.50 | 18.50 | 199 | 48 | 13 | 233.00 | 201.00 | 28 |
| nq_asia_top3_only | NQ Asia ORB | 260 | 88.10 | 6.90 | 229 | 18 | 13 | 290.00 | 166.00 | 18 |
| nq_asia_skip_soft_0p5_1_2_5 | NQ Asia ORB | 260 | 92.70 | 3.10 | 241 | 8 | 11 | 313.00 | 148.00 | 5 |
| es_ny_skip_0p5_1 | ES NY ORB | 260 | 68.50 | 28.80 | 178 | 75 | 7 | 192.00 | 144.00 | 26 |

## Decision Table

| Profile | Target | Full Delta R | 2025+ Delta R | Full Pay% | 2025+ Pay% | Decision | deployability | exact_replay_required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| es_asia_near_0_0p5_only | ES Asia ORB | -84.80 | -11.40 | 76.90 | 84.40 | NO-GO as broad overlay | post_filter_only | yes |
| es_asia_skip_mid_0p5_5 | ES Asia ORB | -30.90 | -11.80 | 75.80 | 78.10 | NO-GO as broad overlay | post_filter_only | yes |
| nq_lsi_2_5_only | NQ NY HTF-LSI | -50.50 | -3.50 | 70.80 | 81.20 | NO-GO as broad overlay | post_filter_only | yes |
| nq_lsi_1_5_only | NQ NY HTF-LSI | -30.50 | -0.40 | 71.90 | 81.20 | NO-GO as broad overlay | post_filter_only | yes |
| nq_lsi_skip_weak_0p5_1_5_10 | NQ NY HTF-LSI | 0.30 | -2.20 | 75.00 | 81.20 | CONDITIONAL research | post_filter_only | yes |
| nq_asia_top3_only | NQ Asia ORB | -55.80 | -25.50 | 74.60 | 75.00 | NO-GO as broad overlay | post_filter_only | yes |
| nq_asia_skip_soft_0p5_1_2_5 | NQ Asia ORB | -26.30 | -23.20 | 73.50 | 78.10 | NO-GO as broad overlay | post_filter_only | yes |
| es_ny_skip_0p5_1 | ES NY ORB | 5.20 | 5.60 | 70.80 | 84.40 | Recent-only watchlist | post_filter_only | yes |
| combo_negative_only_skip | Portfolio | 6.10 | 5.60 | 71.90 | 87.50 | Recent-only watchlist | post_filter_only | yes |
| combo_surgical_weak_skip | Portfolio | -24.50 | -16.30 | 73.80 | 81.20 | NO-GO as broad overlay | post_filter_only | yes |

## Yearly Stability Snapshot

| Profile | Year | Net R | Delta R | DD Delta |
| --- | --- | --- | --- | --- |
| combo_negative_only_skip | 2016 | 31.20 | 0.80 | 0.60 |
| combo_negative_only_skip | 2017 | 58.50 | -0.70 | 0.40 |
| combo_negative_only_skip | 2018 | 48.10 | 3.10 | 0.00 |
| combo_negative_only_skip | 2019 | 37.90 | -1.60 | -2.30 |
| combo_negative_only_skip | 2020 | 54.10 | -6.20 | -0.00 |
| combo_negative_only_skip | 2021 | 44.80 | 3.10 | -0.50 |
| combo_negative_only_skip | 2022 | 70.40 | 0.00 | 0.00 |
| combo_negative_only_skip | 2023 | 74.80 | 0.30 | 0.00 |
| combo_negative_only_skip | 2024 | 53.90 | 1.60 | 0.00 |
| combo_negative_only_skip | 2025 | 103.10 | 5.60 | 2.80 |
| combo_negative_only_skip | 2026 | 8.70 | -0.00 | 0.00 |
| combo_surgical_weak_skip | 2016 | 28.70 | -1.70 | 3.60 |
| combo_surgical_weak_skip | 2017 | 51.90 | -7.40 | 2.40 |
| combo_surgical_weak_skip | 2018 | 53.50 | 8.60 | -0.30 |
| combo_surgical_weak_skip | 2019 | 36.90 | -2.60 | 2.10 |
| combo_surgical_weak_skip | 2020 | 57.60 | -2.60 | 1.30 |
| combo_surgical_weak_skip | 2021 | 50.00 | 8.30 | -1.80 |
| combo_surgical_weak_skip | 2022 | 71.30 | 0.90 | 0.00 |
| combo_surgical_weak_skip | 2023 | 72.50 | -2.00 | 0.00 |
| combo_surgical_weak_skip | 2024 | 42.70 | -9.60 | 2.00 |
| combo_surgical_weak_skip | 2025 | 87.70 | -9.80 | 2.70 |
| combo_surgical_weak_skip | 2026 | 2.30 | -6.50 | 1.50 |
| es_ny_skip_0p5_1 | 2016 | 35.50 | 5.00 | 1.00 |
| es_ny_skip_0p5_1 | 2017 | 58.40 | -0.90 | 0.00 |
| es_ny_skip_0p5_1 | 2018 | 46.50 | 1.50 | 0.00 |
| es_ny_skip_0p5_1 | 2019 | 36.60 | -2.90 | -2.00 |
| es_ny_skip_0p5_1 | 2020 | 55.40 | -4.80 | 0.50 |
| es_ny_skip_0p5_1 | 2021 | 42.30 | 0.60 | -0.50 |
| es_ny_skip_0p5_1 | 2022 | 70.40 | 0.00 | 0.00 |
| es_ny_skip_0p5_1 | 2023 | 75.50 | 1.00 | 0.00 |
| es_ny_skip_0p5_1 | 2024 | 52.40 | 0.10 | 0.00 |
| es_ny_skip_0p5_1 | 2025 | 103.10 | 5.60 | 0.80 |
| es_ny_skip_0p5_1 | 2026 | 8.70 | -0.00 | 0.00 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2016 | 25.80 | -4.60 | 1.00 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2017 | 59.40 | 0.20 | 0.40 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2018 | 49.90 | 5.00 | -1.40 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2019 | 36.90 | -2.60 | -0.10 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2020 | 65.10 | 4.90 | -1.70 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2021 | 38.60 | -3.10 | -1.00 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2022 | 71.60 | 1.20 | 0.00 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2023 | 77.90 | 3.40 | 0.00 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2024 | 50.40 | -1.90 | 2.00 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2025 | 96.30 | -1.30 | 2.00 |
| nq_lsi_skip_weak_0p5_1_5_10 | 2026 | 7.90 | -0.90 | 0.50 |

## First Read

1. The cleanest next exact-replay candidate is `es_ny_skip_0p5_1`: it removes only `95` ES NY trades, lifts full-history R by `+5.2R`, lifts `2025+` by `+5.6R`, and improves ES NY standalone full-history payouts from `64.2%` to `68.5%`. The recent standalone read is much stronger (`2025+` ES NY baseline `43.8%` payout / `37.5%` breach vs gated `81.2%` payout / `0.0%` breach), but this is still post-filter evidence.
2. `combo_negative_only_skip` is the best portfolio-R overlay (`+6.1R` full history, `+5.6R` in `2025+`), but its full-history combined-account payout rate falls from `73.8%` to `71.9%`. Treat it as a recent-flow watchlist, not a broad promotion.
3. HTF-LSI's `1-5%` and `2-5%` whitelists have excellent trade quality and no standalone first-payout breaches, but they slow payout cadence and reduce portfolio R by `-30.5R` to `-50.5R`. The surgical HTF-LSI skip is safer, but the lift is only `+0.3R` full history and `-2.2R` in `2025+`.
4. ES Asia near-ATH is real as a quality pocket, but not as a replacement gate: `0-0.5%` below ATH produces `0.188R` avg versus `0.103R` baseline, yet removing the rest cuts `-84.8R` from the portfolio and stretches standalone median payout time to `655` days.
5. NQ Asia's top-bucket whitelists improve full-history standalone quality, but fail the recent test (`2025+` loses `-23R` to `-26R`). Do not prioritize NQ Asia ATH gating yet.
6. Treat every non-baseline row as `post_filter_only`; the research gate is causal in principle, but the live/exact engine does not yet compute futures ATH state before arming the order.

## Artifacts

- Profile metrics: `data/results/alpha_v1_ath_regime_leg_targets_20260505/profile_metrics.csv`
- Leg impact: `data/results/alpha_v1_ath_regime_leg_targets_20260505/leg_impact.csv`
- Target thesis table: `data/results/alpha_v1_ath_regime_leg_targets_20260505/target_thesis.csv`
- Yearly profiles: `data/results/alpha_v1_ath_regime_leg_targets_20260505/yearly_profiles.csv`
- Funded payout summary: `data/results/alpha_v1_ath_regime_leg_targets_20260505/funded_first_payout_summary.csv`
- Machine summary: `data/results/alpha_v1_ath_regime_leg_targets_20260505/summary.json`
