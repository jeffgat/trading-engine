# NQ Hunter Classic ORB Next Tests (2026-05-02)

## Scope

Follow-up around the stress-gated balanced Hunter candidate `ema14_tol2_distnone_relegacy_samewin0`.

- Stress gate remains ON for all promotion rankings: skip `bull_high_vol`, `bear_high_vol`, `bear_medium_vol`.
- Swept signal cutoff `10:55` vs `13:00`, rejection wick max `20/40/100`, and Tuesday excluded vs included.
- EMA controls included because they are cheap: `ema14 tol0/tol2/tol5`, `ema14 tol2 dist150`, and previous `ema10 tol0 dist150` challenger.
- Holdout view remains `2025-01-01+`; pre-holdout ranking is the workflow-clean read.

## Baseline

Stress-gated balanced baseline: `ema14_tol2_distnone__noTue__1055__rej20__stress`.

- Full 10y: 1,008 trades, +164.7R, 41.4% WR, PF 1.17, DD -41.8R
- pre +56.2R/-41.8R DD; full +164.7R/-41.8R DD; 2025+ +108.5R; last1 +92.8R

## Paired Effect Summary

| Effect | Pairs | Pre-HO Net | Full Net | 2024+ Net | 2025+ Net | Last 1y Net | Full DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Rejection 20 -> disabled | 20 | +7.4R | +17.8R | +22.5R | +12.0R | +6.1R | -5.9R |
| Rejection 20 -> 40 | 20 | +3.0R | +14.3R | +21.1R | +12.8R | +6.1R | -6.0R |
| Signal 10:55 -> 13:00 | 30 | +12.2R | +7.3R | -12.8R | -7.0R | -3.5R | -4.6R |
| Add Tuesday | 30 | +68.7R | +58.5R | +30.5R | -12.8R | -19.5R | +0.3R |

## Workflow-Clean Pre-Holdout Leaders

| Rank | Candidate | Trades | Net | WR | PF | DD | Neg Years | 2025+ | Last 1y |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `ema14_tol0_distnone__withTue__1055__rej100__stress` | 1,455 | +129.1R | 38.3% | 1.10 | -38.4R | 2 | +106.9R | +78.3R |
| 2 | `ema14_tol2_distnone__withTue__1055__rej100__stress` | 1,464 | +127.8R | 38.2% | 1.10 | -38.4R | 3 | +111.3R | +82.6R |
| 3 | `ema14_tol0_distnone__withTue__1055__rej40__stress` | 1,437 | +121.7R | 38.1% | 1.10 | -38.4R | 2 | +106.9R | +78.3R |
| 4 | `ema14_tol2_distnone__withTue__1300__rej100__stress` | 1,932 | +143.4R | 37.3% | 1.09 | -55.0R | 4 | +96.8R | +70.4R |
| 5 | `ema14_tol5_distnone__withTue__1055__rej100__stress` | 1,472 | +120.4R | 38.1% | 1.09 | -40.6R | 2 | +120.5R | +86.9R |

## Full 10-Year Leaders

| Rank | Candidate | Trades | Net | WR | PF | DD | Neg Years | 2025+ | Last 1y |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `ema14_tol5_distnone__withTue__1055__rej100__stress` | 1,670 | +240.9R | 39.9% | 1.15 | -40.6R | 2 | +120.5R | +86.9R |
| 2 | `ema14_tol0_distnone__withTue__1055__rej100__stress` | 1,650 | +236.0R | 39.9% | 1.15 | -38.4R | 2 | +106.9R | +78.3R |
| 3 | `ema14_tol2_distnone__withTue__1055__rej100__stress` | 1,660 | +239.1R | 39.9% | 1.15 | -38.4R | 3 | +111.3R | +82.6R |
| 4 | `ema14_tol0_distnone__withTue__1055__rej40__stress` | 1,632 | +228.6R | 39.8% | 1.15 | -38.4R | 2 | +106.9R | +78.3R |
| 5 | `ema14_tol5_distnone__withTue__1055__rej40__stress` | 1,652 | +233.4R | 39.8% | 1.15 | -40.6R | 3 | +120.5R | +86.9R |

## Recent Hot-Window Leaders

| Rank | Candidate | Trades | Net | WR | PF | DD | Neg Years | 2025+ | Last 1y |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `ema14_tol5_distnone__noTue__1055__rej40__stress` | 123 | +108.7R | 56.1% | 1.72 | -14.2R | 0 | +131.4R | +108.7R |
| 2 | `ema14_tol5_distnone__noTue__1055__rej100__stress` | 123 | +108.7R | 56.1% | 1.72 | -14.2R | 0 | +131.4R | +108.7R |
| 3 | `ema14_tol2_dist150__noTue__1055__rej40__stress` | 112 | +105.1R | 57.1% | 1.80 | -14.2R | 0 | +123.3R | +105.1R |
| 4 | `ema14_tol2_dist150__noTue__1055__rej100__stress` | 112 | +105.1R | 57.1% | 1.80 | -14.2R | 0 | +123.3R | +105.1R |
| 5 | `ema14_tol2_dist150__noTue__1300__rej20__stress` | 116 | +103.5R | 56.9% | 1.78 | -15.9R | 0 | +114.0R | +103.5R |

## Key Candidate Comparison

| Role | Candidate | Pre-HO | Full 10y | 2024+ | 2025+ | Last 1y | Full Neg Years |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline | `ema14_tol2_distnone__noTue__1055__rej20__stress` | +56.2R / -41.8R DD | +164.7R / -41.8R DD | +123.8R | +108.5R | +92.8R | 3 |
| Best workflow-clean | `ema14_tol0_distnone__withTue__1055__rej100__stress` | +129.1R / -38.4R DD | +236.0R / -38.4R DD | +174.0R | +106.9R | +78.3R | 2 |
| Best full 10y | `ema14_tol5_distnone__withTue__1055__rej100__stress` | +120.4R / -40.6R DD | +240.9R / -40.6R DD | +184.8R | +120.5R | +86.9R | 2 |
| Best 2025+ | `ema14_tol5_distnone__noTue__1055__rej40__stress` | +40.1R / -51.7R DD | +171.5R / -51.7R DD | +152.9R | +131.4R | +108.7R | 5 |

## Annual Net R For Shortlist

| Year | `ema14_tol2_distnone__noTue__1055__rej20__stress` | `ema14_tol0_distnone__withTue__1055__rej100__stress` | `ema14_tol5_distnone__withTue__1055__rej100__stress` | `ema14_tol5_distnone__noTue__1055__rej100__stress` | `ema14_tol5_distnone__noTue__1055__rej40__stress` |
|---:|---:|---:|---:|---:|---:|
| 2016 | +0.5R | +5.4R | +4.4R | +5.4R | +1.9R |
| 2017 | +1.3R | -12.0R | -11.1R | -4.3R | -4.6R |
| 2018 | -5.8R | -10.7R | -10.7R | -2.4R | -4.2R |
| 2019 | -16.6R | +2.2R | +0.7R | -13.3R | -11.6R |
| 2020 | +52.9R | +56.4R | +54.5R | +49.2R | +50.2R |
| 2021 | +7.0R | +10.3R | +8.1R | +0.6R | +1.2R |
| 2022 | -6.9R | +8.3R | +9.2R | -4.3R | -7.9R |
| 2023 | +8.6R | +2.0R | +0.9R | -7.2R | -6.2R |
| 2024 | +15.3R | +67.1R | +64.3R | +22.9R | +21.5R |
| 2025 | +52.9R | +57.8R | +67.0R | +86.8R | +86.8R |
| 2026 | +55.7R | +49.1R | +53.5R | +44.6R | +44.6R |

## No-Gate Context

| Variant | Full 10y | 2025+ | Last 1y |
|---|---:|---:|---:|
| `ema14_tol2_distnone__noTue__1055__rej20__nogate` | +68.4R / -138.8R DD | +157.3R | +130.6R |
| `ema14_tol2_distnone__noTue__1300__rej20__nogate` | +126.6R / -146.3R DD | +186.3R | +139.9R |
| `ema14_tol2_distnone__noTue__1300__rej100__nogate` | +107.0R / -171.8R DD | +184.8R | +145.7R |
| `ema14_tol2_distnone__withTue__1300__rej100__nogate` | +130.9R / -115.5R DD | +111.0R | +67.2R |

## Read

- **Signal extension to 13:00 is not broadly validated.** The original baseline-only ablation looked good, and the direct baseline row still improves, but the paired grid median gives up 2024+, 2025+, and last-1y R while slightly worsening full-history DD. Treat 13:00 as a narrow baseline-like side branch, not the new default.
- **Relaxing/removing the rejection wick filter is the cleanest robust improvement.** `rej40` and `rej100` both add median R across every window; the cost is worse full-history DD. The top workflow/full candidates use `rej100`, and the best recent candidate ties between `rej40` and `rej100` with `rej100` having the better long-history profile.
- **Tuesday is a 10y-vs-recent fork.** It helps every full/pre-history paired comparison and drives the best 10y candidates, but it hurts every 2025+ and last-1y paired comparison. Do not re-add Tuesday to the live/pilot expression unless the objective is explicitly 10y diversification over current-regime strength.
- **Best 10y-safe candidate:** `ema14_tol0_distnone__withTue__1055__rej100__stress` is the workflow-clean pre-holdout leader; `ema14_tol5_distnone__withTue__1055__rej100__stress` is the full-10y hindsight leader. Both disable rejection and re-add Tuesday, and both give up last-1y R versus the baseline.
- **Best hot candidate:** `ema14_tol5_distnone__noTue__1055__rej100__stress`/`rej40` wins the recent window. Prefer `rej100` if carrying it forward because it has identical recent performance with better pre/full/DD than `rej40`.
- **Supersede read:** no single row cleanly supersedes the balanced stress-gated baseline across all objectives. Carry forward two branches: a 10y-safe Tuesday/rej100 branch and a recent-strength no-Tuesday/tol5/rej100 branch. Keep the current balanced baseline as the neutral reference until downstream validation decides.

## Artifacts

- Results packet: `data/results/hunter_classic_next_tests_20260502`
- `next_test_metrics.csv`
- `paired_effects.csv`
- `paired_effect_summary.csv`
- `annual_metrics.csv`
- `selected_trades/*.csv`
