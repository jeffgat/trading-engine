# ALPHA_V1 ORB Wide-Stop + Re-Entry Transfer Test

- Window: `2016-04-17` to `2026-03-24`
- Scope: current active ALPHA_V1 ORB legs only: `NQ Asia ORB`, `ES Asia ORB`, `ES NY ORB`
- Excluded: HTF-LSI leg, because this pass is testing ORB mechanic transfer only
- Wide-stop rule: if realized stop/risk points are above a leg-specific baseline-risk quantile, use a lower effective RR target ladder for that trade
- Re-entry rule: engine-backed `orb_trade_max_per_session=2` with `any_reentry`, `after_nonpositive_first`, `after_sl_first`, and diagnostic positive/full-target policies
- Note: lowered RR also lowers the TP1 ladder through the existing engine rule, while still enforcing the hard minimum TP1 distance of at least `1R`.

## Baseline Combined ORB Sleeve

| window | signals | fills | net_r | win_rate_pct | profit_factor | sharpe_ratio | max_drawdown_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | 3550 | 2989 | 487 | 54.20 | 1.40 | 1.73 | -21.18 | 0 |
| 2024_plus | 822 | 676 | 124 | 56.51 | 1.45 | 2.08 | -9.88 | 0 |
| 2025_plus | 456 | 376 | 90.90 | 59.31 | 1.63 | 2.62 | -9.88 | 0 |
| last_1y | 376 | 308 | 77.27 | 58.77 | 1.64 | 2.75 | -9.88 | 0 |

## Risk Thresholds By Leg

| leg | fills | risk_p50 | risk_p65 | risk_p75 | risk_p85 | risk_p90 | risk_min | risk_median | risk_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_asia_orb_long | 722 | 12.25 | 16.25 | 19.50 | 25.25 | 31.50 | 1.51 | 12.17 | 110 |
| es_asia_orb_long | 1422 | 4.25 | 5.50 | 6.75 | 8.75 | 10.75 | 3 | 4.06 | 73.75 |
| es_ny_orb_long | 845 | 3 | 3 | 3.25 | 3.75 | 4.25 | 3 | 3 | 10.87 |

## Combined Sleeve: Re-Entry Only

| window | variant | fills | net_r | delta_net_r | win_rate_pct | profit_factor | sharpe_ratio | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| last_1y | cap2_any | 389 | 88.97 | 11.70 | 57.84 | 1.58 | 2.78 | -12.60 | -2.72 | 0 |
| last_1y | cap2_after_positive | 365 | 87.32 | 10.05 | 57.81 | 1.61 | 2.90 | -12.17 | -2.29 | 0 |
| last_1y | cap2_after_full_target | 334 | 80.84 | 3.57 | 58.38 | 1.63 | 2.74 | -11.17 | -1.29 | 0 |
| last_1y | cap2_after_nonpositive | 332 | 78.92 | 1.65 | 58.73 | 1.60 | 2.62 | -10.94 | -1.06 | 0 |
| last_1y | cap2_after_sl | 332 | 78.92 | 1.65 | 58.73 | 1.60 | 2.62 | -10.94 | -1.06 | 0 |
| full | cap2_any | 3698 | 568 | 81.56 | 54.19 | 1.37 | 1.92 | -23.21 | -2.03 | 0 |
| full | cap2_after_nonpositive | 3224 | 546 | 58.67 | 54.47 | 1.41 | 1.93 | -21.96 | -0.78 | 0 |
| full | cap2_after_sl | 3224 | 546 | 58.67 | 54.47 | 1.41 | 1.93 | -21.96 | -0.78 | 0 |
| full | cap2_after_positive | 3463 | 510 | 22.88 | 53.94 | 1.36 | 1.73 | -19.41 | 1.77 | 0 |
| full | cap2_after_full_target | 3218 | 489 | 2.15 | 53.98 | 1.37 | 1.71 | -21.47 | -0.29 | 0 |
| 2025_plus | cap2_any | 481 | 104 | 13.60 | 57.80 | 1.55 | 2.70 | -12.60 | -2.72 | 0 |
| 2025_plus | cap2_after_positive | 449 | 97.87 | 6.97 | 57.91 | 1.56 | 2.65 | -12.17 | -2.29 | 0 |
| 2025_plus | cap2_after_nonpositive | 408 | 97.52 | 6.62 | 59.07 | 1.61 | 2.67 | -10.94 | -1.06 | 0 |
| 2025_plus | cap2_after_sl | 408 | 97.52 | 6.62 | 59.07 | 1.61 | 2.67 | -10.94 | -1.06 | 0 |
| 2025_plus | cap2_after_full_target | 409 | 93.73 | 2.83 | 58.44 | 1.60 | 2.58 | -11.17 | -1.29 | 0 |

## Top Combined Sleeve Variants: Full History

| family | variant | fills | net_r | delta_net_r | profit_factor | sharpe_ratio | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reentry_only | cap2_any | 3698 | 568 | 81.56 | 1.37 | 1.92 | -23.21 | -2.03 | 0 |
| combined | combo_q90_rr5p0_cap2_any | 3699 | 565 | 78.03 | 1.37 | 1.91 | -23.21 | -2.03 | 0 |
| combined | combo_q90_rr4p0_cap2_any | 3699 | 565 | 77.84 | 1.37 | 1.92 | -23.21 | -2.03 | 0 |
| combined | combo_q85_rr5p0_cap2_any | 3699 | 561 | 73.91 | 1.37 | 1.89 | -23.21 | -2.03 | 0 |
| combined | combo_q85_rr4p0_cap2_any | 3699 | 561 | 73.79 | 1.37 | 1.90 | -23.21 | -2.03 | 0 |
| combined | combo_q90_rr3p0_cap2_any | 3705 | 555 | 67.75 | 1.37 | 1.89 | -23.21 | -2.03 | 0 |
| combined | combo_q90_rr2p0_cap2_any | 3710 | 551 | 64.31 | 1.36 | 1.87 | -23.21 | -2.03 | 0 |
| combined | combo_q75_rr5p0_cap2_any | 3699 | 551 | 63.65 | 1.36 | 1.87 | -23.21 | -2.03 | 0 |

## Top Combined Sleeve Variants: 2025+

| family | variant | fills | net_r | delta_net_r | profit_factor | sharpe_ratio | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reentry_only | cap2_any | 481 | 104 | 13.60 | 1.55 | 2.70 | -12.60 | -2.72 | 0 |
| combined | combo_q90_rr5p0_cap2_any | 481 | 103 | 12.41 | 1.55 | 2.65 | -14.09 | -4.21 | 0 |
| combined | combo_q90_rr4p0_cap2_any | 481 | 103 | 11.72 | 1.55 | 2.66 | -14.19 | -4.31 | 0 |
| combined | combo_q85_rr4p0_cap2_any | 481 | 101 | 10.55 | 1.54 | 2.65 | -14.19 | -4.31 | 0 |
| combined | combo_q85_rr5p0_cap2_any | 481 | 101 | 10.48 | 1.54 | 2.61 | -14.09 | -4.21 | 0 |
| combined | combo_q50_rr5p0_cap2_any | 481 | 99.15 | 8.25 | 1.54 | 2.66 | -14.09 | -4.21 | 0 |
| combined | combo_q75_rr5p0_cap2_any | 481 | 98.58 | 7.68 | 1.53 | 2.58 | -14.09 | -4.21 | 0 |
| combined | combo_q90_rr3p0_cap2_any | 485 | 98.52 | 7.62 | 1.53 | 2.61 | -12.66 | -2.78 | 0 |

## Top Combined Sleeve Variants: Last 1y

| family | variant | fills | net_r | delta_net_r | profit_factor | sharpe_ratio | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reentry_only | cap2_any | 389 | 88.97 | 11.70 | 1.58 | 2.78 | -12.60 | -2.72 | 0 |
| reentry_only | cap2_after_positive | 365 | 87.32 | 10.05 | 1.61 | 2.90 | -12.17 | -2.29 | 0 |
| combined | combo_q90_rr5p0_cap2_any | 389 | 87.12 | 9.85 | 1.58 | 2.72 | -14.09 | -4.21 | 0 |
| combined | combo_q90_rr4p0_cap2_any | 389 | 86.60 | 9.33 | 1.58 | 2.72 | -14.19 | -4.31 | 0 |
| combined | combo_q85_rr5p0_cap2_any | 389 | 85.20 | 7.93 | 1.56 | 2.67 | -14.09 | -4.21 | 0 |
| combined | combo_q90_rr3p0_cap2_any | 393 | 85.11 | 7.84 | 1.57 | 2.73 | -12.66 | -2.78 | 0 |
| combined | combo_q90_rr2p0_cap2_any | 394 | 83.91 | 6.64 | 1.56 | 2.69 | -14.19 | -4.31 | 0 |
| combined | combo_q85_rr4p0_cap2_any | 389 | 83.44 | 6.17 | 1.55 | 2.64 | -14.19 | -4.31 | 0 |

## Wide-Stop Only Leaders

| variant | fills | net_r | delta_net_r | profit_factor | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wide_q90_rr4p0 | 2989 | 482 | -4.67 | 1.39 | -21.18 | 0 | 0 |
| wide_q90_rr5p0 | 2989 | 482 | -4.82 | 1.39 | -21.18 | 0 | 0 |
| wide_q85_rr4p0 | 2989 | 479 | -7.94 | 1.39 | -21.48 | -0.30 | 0 |
| wide_q85_rr5p0 | 2989 | 478 | -8.80 | 1.39 | -21.33 | -0.15 | 0 |
| wide_q90_rr2p0 | 2989 | 474 | -13.13 | 1.39 | -21.18 | 0 | 0 |
| wide_q90_rr3p0 | 2989 | 474 | -13.40 | 1.39 | -21.18 | 0 | 0 |
| wide_q90_rr1p5 | 2989 | 469 | -17.83 | 1.38 | -21.18 | 0 | 0 |
| wide_q75_rr5p0 | 2989 | 469 | -18.08 | 1.38 | -21.33 | -0.15 | 0 |

## Combined Mechanic Leaders

| variant | fills | net_r | delta_net_r | profit_factor | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- |
| combo_q90_rr5p0_cap2_any | 3699 | 565 | 78.03 | 1.37 | -23.21 | -2.03 | 0 |
| combo_q90_rr4p0_cap2_any | 3699 | 565 | 77.84 | 1.37 | -23.21 | -2.03 | 0 |
| combo_q85_rr5p0_cap2_any | 3699 | 561 | 73.91 | 1.37 | -23.21 | -2.03 | 0 |
| combo_q85_rr4p0_cap2_any | 3699 | 561 | 73.79 | 1.37 | -23.21 | -2.03 | 0 |
| combo_q90_rr3p0_cap2_any | 3705 | 555 | 67.75 | 1.37 | -23.21 | -2.03 | 0 |
| combo_q90_rr2p0_cap2_any | 3710 | 551 | 64.31 | 1.36 | -23.21 | -2.03 | 0 |
| combo_q75_rr5p0_cap2_any | 3699 | 551 | 63.65 | 1.36 | -23.21 | -2.03 | 0 |
| combo_q85_rr3p0_cap2_any | 3707 | 550 | 62.57 | 1.36 | -23.21 | -2.03 | 0 |

## Per-Leg Best Full-History Rows

| scope | family | variant | fills | net_r | delta_net_r | profit_factor | max_drawdown_r | delta_dd_r | negative_years |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_asia_orb_long | reentry_only | cap2_after_nonpositive | 759 | 237 | 23.78 | 1.58 | -10.28 | -0.12 | 0 |
| es_asia_orb_long | reentry_only | cap2_after_nonpositive | 1519 | 168 | 22.34 | 1.31 | -11.67 | 0.61 | 0 |
| es_ny_orb_long | combined | combo_q75_rr4p0_cap2_any | 1142 | 169 | 41.81 | 1.37 | -13.12 | -2.26 | 1 |

## Read

- **One-loss / nonpositive re-entry transfers; wide-stop target compression does not.** The cleanest Hunter-style transfer is `cap2_after_nonpositive` / `cap2_after_sl`: full-history combined sleeve improves by about `+58.7R`, keeps `0` negative years, improves Sharpe, and only worsens daily DD by about `-0.8R`.
- **`cap2_any` is the highest-R row, but it is less controlled.** It adds about `+81.6R` full history and `+13.6R` in 2025+, but daily DD worsens by about `-2.0R` full and `-2.7R` in the recent windows. That is attractive as a research branch, less clean as a direct live rule.
- **Wide-stop TP compression is a portfolio-level NO-GO for this sleeve.** Every wide-only combined variant loses net R versus baseline; the best full-history row is still `-4.7R`, the median wide-only row is about `-32.9R`, and recent windows are also negative. It does not buy meaningful drawdown relief.
- **Combined variants mostly inherit the re-entry edge.** The top combined rows are just `cap2_any` plus very light high-threshold target compression, and they underperform pure `cap2_any`. The wide-stop rule is not the source of the improvement.
- Per-leg: `NQ Asia` and `ES Asia` both favor the one-loss/nonpositive re-entry. `ES NY` likes extra flow most, but the best full-history ES NY combo introduces a negative year, so it needs prop/risk validation before any live promotion.
- The variant manifest records which wide-stop rows were active per leg; target RR values at or above a leg's normal RR map back to that leg's matching non-wide re-entry variant.

## Artifacts

- Result directory: `data/results/alpha_v1_orb_widestop_reentry_transfer_20260502`
- Active wide-rule config rows: `300`
