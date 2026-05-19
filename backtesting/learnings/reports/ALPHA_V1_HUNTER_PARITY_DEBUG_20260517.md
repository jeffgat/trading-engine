# ALPHA_V1 Hunter Parity Debug (2026-05-17)

- Generated: `2026-05-18T06:20:51`
- Results packet: `backtesting/data/results/alpha_v1_hunter_parity_debug_20260517`
- Repro script: `backtesting/scripts/run_alpha_v1_hunter_parity_debug_20260517.py`
- Runtime: `2.0s`
- Hunter exact latest NQ end: `2026-05-01`

## Exact Variant Summary

| Variant | Trades | Net | DD | PF | Net R | DD R | WR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| signal_close_cap_fixed | 1384 | $2,971 | $-4,078 | 1.05 | 51.0 | -54.9 | 37.4% |
| next_open_cap_fixed | 1385 | $3,085 | $-4,075 | 1.05 | 47.2 | -57.1 | 37.3% |
| next_open_signal_only | 1661 | $28,024 | $-6,176 | 1.14 | 67.9 | -56.5 | 39.7% |
| next_open_no_tuesday_signal_only | 1301 | $23,038 | $-5,223 | 1.15 | 64.1 | -41.8 | 40.0% |
| next_open_after_each_loss_signal_only | 1683 | $27,091 | $-6,889 | 1.14 | 59.8 | -64.1 | 39.5% |
| next_open_all_nonoverlap_signal_only | 1692 | $27,347 | $-6,945 | 1.14 | 61.5 | -63.3 | 39.5% |
| next_open_samebar_win_signal_only | 1662 | $27,707 | $-6,176 | 1.14 | 66.9 | -56.5 | 39.7% |
| next_open_fast_exhaustion_signal_only | 1654 | $28,557 | $-6,176 | 1.15 | 69.0 | -56.5 | 39.7% |

## Research Parity Counts

| Variant | Exact | Research | Matched | Match vs Research | Exact Only | Research Only |
| --- | --- | --- | --- | --- | --- | --- |
| signal_close_cap_fixed | 1378 | 1650 | 529 | 32.1% | 849 | 1121 |
| next_open_cap_fixed | 1379 | 1650 | 1349 | 81.8% | 30 | 301 |
| next_open_signal_only | 1652 | 1650 | 1650 | 100.0% | 2 | 0 |
| next_open_no_tuesday_signal_only | 1294 | 1650 | 1294 | 78.4% | 0 | 356 |
| next_open_after_each_loss_signal_only | 1674 | 1650 | 1650 | 100.0% | 24 | 0 |
| next_open_all_nonoverlap_signal_only | 1683 | 1650 | 1650 | 100.0% | 33 | 0 |
| next_open_samebar_win_signal_only | 1653 | 1650 | 1650 | 100.0% | 3 | 0 |
| next_open_fast_exhaustion_signal_only | 1645 | 1650 | 1642 | 99.5% | 3 | 8 |

## Match Ladder

| Variant | Match Level | Matches | Match vs Research |
| --- | --- | --- | --- |
| signal_close_cap_fixed | date_direction_minute | 1349 | 81.8% |
| signal_close_cap_fixed | plus_entry | 529 | 32.1% |
| signal_close_cap_fixed | plus_target | 529 | 32.1% |
| next_open_cap_fixed | date_direction_minute | 1349 | 81.8% |
| next_open_cap_fixed | plus_entry | 1349 | 81.8% |
| next_open_cap_fixed | plus_target | 1349 | 81.8% |
| next_open_signal_only | date_direction_minute | 1650 | 100.0% |
| next_open_signal_only | plus_entry | 1650 | 100.0% |
| next_open_signal_only | plus_target | 1650 | 100.0% |
| next_open_no_tuesday_signal_only | date_direction_minute | 1294 | 78.4% |
| next_open_no_tuesday_signal_only | plus_entry | 1294 | 78.4% |
| next_open_no_tuesday_signal_only | plus_target | 1294 | 78.4% |
| next_open_after_each_loss_signal_only | date_direction_minute | 1650 | 100.0% |
| next_open_after_each_loss_signal_only | plus_entry | 1650 | 100.0% |
| next_open_after_each_loss_signal_only | plus_target | 1650 | 100.0% |
| next_open_all_nonoverlap_signal_only | date_direction_minute | 1650 | 100.0% |
| next_open_all_nonoverlap_signal_only | plus_entry | 1650 | 100.0% |
| next_open_all_nonoverlap_signal_only | plus_target | 1650 | 100.0% |
| next_open_samebar_win_signal_only | date_direction_minute | 1650 | 100.0% |
| next_open_samebar_win_signal_only | plus_entry | 1650 | 100.0% |
| next_open_samebar_win_signal_only | plus_target | 1650 | 100.0% |
| next_open_fast_exhaustion_signal_only | date_direction_minute | 1642 | 99.5% |
| next_open_fast_exhaustion_signal_only | plus_entry | 1642 | 99.5% |
| next_open_fast_exhaustion_signal_only | plus_target | 1642 | 99.5% |

## Debug Reason Counts

| Variant | Reason | Count |
| --- | --- | --- |
| next_open_after_each_loss_signal_only | signal_passed | 1693 |
| next_open_after_each_loss_signal_only | pending_next_open | 1683 |
| next_open_after_each_loss_signal_only | setup_activated | 1683 |
| next_open_after_each_loss_signal_only | reentry_blocked | 10 |
| next_open_all_nonoverlap_signal_only | pending_next_open | 1692 |
| next_open_all_nonoverlap_signal_only | setup_activated | 1692 |
| next_open_all_nonoverlap_signal_only | signal_passed | 1692 |
| next_open_cap_fixed | signal_passed | 1735 |
| next_open_cap_fixed | pending_next_open | 1705 |
| next_open_cap_fixed | setup_activated | 1385 |
| next_open_cap_fixed | qty_rejected | 320 |
| next_open_cap_fixed | reentry_blocked | 30 |
| next_open_fast_exhaustion_signal_only | signal_passed | 1695 |
| next_open_fast_exhaustion_signal_only | pending_next_open | 1654 |
| next_open_fast_exhaustion_signal_only | setup_activated | 1654 |
| next_open_fast_exhaustion_signal_only | reentry_blocked | 41 |
| next_open_no_tuesday_signal_only | signal_passed | 1330 |
| next_open_no_tuesday_signal_only | pending_next_open | 1301 |
| next_open_no_tuesday_signal_only | setup_activated | 1301 |
| next_open_no_tuesday_signal_only | reentry_blocked | 29 |
| next_open_samebar_win_signal_only | signal_passed | 1694 |
| next_open_samebar_win_signal_only | pending_next_open | 1662 |
| next_open_samebar_win_signal_only | setup_activated | 1662 |
| next_open_samebar_win_signal_only | reentry_blocked | 32 |
| next_open_signal_only | signal_passed | 1694 |
| next_open_signal_only | pending_next_open | 1661 |
| next_open_signal_only | setup_activated | 1661 |
| next_open_signal_only | reentry_blocked | 33 |
| signal_close_cap_fixed | signal_passed | 1735 |
| signal_close_cap_fixed | setup_activated | 1384 |

## Cap-Fixed Sidecar Portfolio

| Scenario | Net | Delta | DD | Worst Month | Sharpe |
| --- | --- | --- | --- | --- | --- |
| ALPHA_V1 cached fee-aware | $53,825 | $0 | $-4,037 | $-2,469 | 2.04 |
| ALPHA_V1 + next-open cap-fixed Hunter 0.25x | $58,917 | $5,092 | $-3,889 | $-2,469 | 2.18 |

## Cap-Fixed Sidecar Account Outcomes

| Scenario | Year | Payout | Breach | Avg PayD | MCBch | EV/Start |
| --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1 cached fee-aware | 2024 | 82.6% | 17.4% | 40.6 | 2 | $202 |
| ALPHA_V1 cached fee-aware | 2025 | 73.1% | 26.9% | 20.5 | 7 | $202 |
| ALPHA_V1 cached fee-aware | 2026_YTD | 100.0% | 0.0% | 39.3 | 0 | $100 |
| ALPHA_V1 + next-open cap-fixed Hunter 0.25x | 2024 | 87.5% | 12.5% | 38.0 | 2 | $239 |
| ALPHA_V1 + next-open cap-fixed Hunter 0.25x | 2025 | 80.8% | 19.2% | 20.7 | 4 | $239 |
| ALPHA_V1 + next-open cap-fixed Hunter 0.25x | 2026_YTD | 100.0% | 0.0% | 33.0 | 0 | $100 |

## Read

- Entry basis was the main parity bug. `signal_close_cap_fixed` matched only `529 / 1650` research setups once entry/target prices were included; `next_open_signal_only` matched `1650 / 1650`.
- The deployable `next_open_cap_fixed` row matched `1349 / 1650` research setups (`81.8%`). The remaining gap is mostly sizing integrity: `320` next-open candidates were rejected by the `$87.50` single-contract cap.
- Tuesday should stay enabled for this branch. Excluding Tuesday cut high-cap parity from `1650` matched research setups to `1294` and removed `356` research trades.
- Reentry is not the primary blocker after `next_open`: `after_each_loss`, `all_nonoverlap`, and same-bar-win variants all kept `100%` research coverage but added exact-only trades and did not improve standalone quality versus the frozen research-compatible baseline.
- Actionable gate: use `hunter_entry_basis=next_open` for Hunter shadow/parity work. Keep the branch no-webhook shadow only until live logs confirm next-open arming/fill behavior and the cap-fixed sidecar remains additive in forward data.
