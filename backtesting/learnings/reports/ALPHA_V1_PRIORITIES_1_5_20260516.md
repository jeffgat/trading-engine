# ALPHA_V1 Priorities 1-5 Packet (2026-05-16)

- Generated: `2026-05-16T18:49:40`
- Results packet: `backtesting/data/results/alpha_v1_priorities_1_5_20260516`
- Repro script: `backtesting/scripts/run_alpha_v1_priorities_1_5_20260516.py`
- Runtime: `0.9s`
- Hunter exact latest NQ end: `2026-05-01`
- Updated ALPHA exact latest common NQ/ES end: `2026-03-24`

## 1. Hunter Live-Engine Parity

The live `hunter_orb` replay does not match the original research-selected Hunter stream closely enough to treat the prior downstream read as confirmed parity.

| Stream | Trades | Net | DD | PF | Net R | DD R | WR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| live_engine_exact_shadow_025 | 1651 | $5,431 | $-4,016 | 1.07 | 80.0 | -54.5 | 39.9% |
| research_selected_10y_safe | 1650 | $20,654 | $-3,360 | 1.15 | 236 | -38.4 | 39.9% |
| fuzzy_same_setup_match | 593 | $0 | $0 | 0.00 | 0.0 | 0.0 | 35.9% |

Fuzzy same-setup match: `593` matched, `1058` exact-only, `1057` research-only over `2016-04-25` to `2026-04-24`.

Deployability: `live_native` for the shadow engine profile, but `exact_replay_required=failed_parity_investigation` before sizing decisions should lean on the old research CSV.

## 2. Hunter Sidecar Sizing Around 0.25x

This uses actual current Hunter engine sizing behavior. The important artifact is the contract floor: `risk_usd=$87.50` can still trade 1 MNQ even when the stop risk is wider than the intended risk.

| Scale | Intended Risk | Max C | Net | DD | PF | Avg Eff Risk | P95 Eff Risk | Over Intended | Strict Drops |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.125x | $43.75 | 3 | $6,504 | $-1,523 | 1.11 | $60.12 | $144.02 | 49.2% | 49.2% |
| 0.25x | $87.50 | 5 | $4,726 | $-4,016 | 1.06 | $78.84 | $144.02 | 18.2% | 18.2% |
| 0.375x | $131.25 | 8 | $5,245 | $-6,031 | 1.05 | $109.11 | $144.02 | 6.3% | 6.3% |
| 0.5x | $175.00 | 10 | $9,145 | $-8,573 | 1.06 | $144.11 | $175.00 | 2.6% | 2.6% |

### Cached ALPHA_V1 Portfolio Fit

| Scenario | Net | Delta | DD | Worst Month | Sharpe |
| --- | --- | --- | --- | --- | --- |
| ALPHA_V1 cached fee-aware | $53,825 | $0 | $-4,037 | $-2,469 | 2.04 |
| ALPHA_V1 + Hunter 0.125x actual engine sizing | $59,302 | $5,477 | $-3,699 | $-2,915 | 2.18 |
| ALPHA_V1 + Hunter 0.25x actual engine sizing | $59,797 | $5,972 | $-3,699 | $-2,915 | 2.19 |
| ALPHA_V1 + Hunter 0.375x actual engine sizing | $61,448 | $7,623 | $-3,699 | $-2,915 | 2.21 |
| ALPHA_V1 + Hunter 0.5x actual engine sizing | $66,202 | $12,377 | $-3,672 | $-2,915 | 2.30 |

### 0.25x Account Outcomes

| Scenario | Year | Payout | Breach | Avg PayD | MCBch | EV/Start |
| --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1 cached fee-aware | 2024 | 82.6% | 17.4% | 40.6 | 2 | $202 |
| ALPHA_V1 cached fee-aware | 2025 | 73.1% | 26.9% | 20.5 | 7 | $202 |
| ALPHA_V1 cached fee-aware | 2026_YTD | 100.0% | 0.0% | 39.3 | 0 | $100 |
| ALPHA_V1 + Hunter 0.25x actual engine sizing | 2024 | 80.0% | 20.0% | 36.9 | 2 | $220 |
| ALPHA_V1 + Hunter 0.25x actual engine sizing | 2025 | 84.6% | 15.4% | 23.2 | 4 | $257 |
| ALPHA_V1 + Hunter 0.25x actual engine sizing | 2026_YTD | 100.0% | 0.0% | 30.3 | 0 | $100 |

## 3. Hunter + ES_NY ATH Gate Interaction

The ATH leg was revalued to current ALPHA_V1 ES_NY risk (`$300`) with current MES fees before replacing the baseline ES_NY stream.

| ES_NY Stream | Trades | Net | DD | PF | Net R | DD R |
| --- | --- | --- | --- | --- | --- | --- |
| current_es_ny | 173 | $5,721 | $-3,105 | 1.25 | 20.2 | -10.2 |
| ath_0p5_0p75_revalued | 276 | $11,500 | $-3,898 | 1.29 | 39.8 | -13.0 |

| Scenario | Net | Delta | DD | Worst Month | Sharpe |
| --- | --- | --- | --- | --- | --- |
| ALPHA_V1 cached fee-aware | $53,825 | $0 | $-4,037 | $-2,469 | 2.04 |
| ALPHA_V1 + Hunter 0.25x actual | $59,797 | $5,972 | $-3,699 | $-2,915 | 2.19 |
| ALPHA_V1 with ES_NY ATH 0.50-0.75 replacement | $59,604 | $5,779 | $-4,630 | $-3,003 | 2.07 |
| ALPHA_V1 ES_NY ATH replacement + Hunter 0.25x actual | $65,576 | $11,751 | $-4,572 | $-3,026 | 2.21 |

| Scenario | Year | Payout | Breach | Avg PayD | MCBch | EV/Start |
| --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1 cached fee-aware | 2024 | 82.6% | 17.4% | 40.6 | 2 | $202 |
| ALPHA_V1 cached fee-aware | 2025 | 73.1% | 26.9% | 20.5 | 7 | $202 |
| ALPHA_V1 with ES_NY ATH 0.50-0.75 replacement | 2024 | 76.0% | 24.0% | 36.9 | 3 | $202 |
| ALPHA_V1 with ES_NY ATH 0.50-0.75 replacement | 2025 | 80.8% | 19.2% | 19.5 | 4 | $239 |
| ALPHA_V1 ES_NY ATH replacement + Hunter 0.25x actual | 2024 | 96.0% | 4.0% | 33.9 | 1 | $294 |
| ALPHA_V1 ES_NY ATH replacement + Hunter 0.25x actual | 2025 | 84.6% | 15.4% | 20.2 | 4 | $257 |

## 4. Updated Post-2026-03-24 Exact Replay

Post-March replay is bounded by local ES data availability: `latest_common_end(['NQ', 'ES'])` returned `2026-03-24`. NQ has newer local data, but the combined ALPHA exact path cannot move past ES.

| Window | Source | Trades | Net | DD | PF | Net R |
| --- | --- | --- | --- | --- | --- | --- |
| cached_overlap | cached_fee_20260507 | 946 | $53,825 | $-4,338 | 1.48 | 171 |
| updated_overlap | updated_exact | 928 | $44,371 | $-4,707 | 1.41 | 149 |
| updated_post_2026_03_24 | updated_exact | 0 | $0 | $0 | 0.00 | 0.0 |
| updated_full | updated_exact | 928 | $44,371 | $-4,707 | 1.41 | 149 |

| Window | Leg | Trades | Net | PF | Net R |
| --- | --- | --- | --- | --- | --- |
| updated_full | es_asia_orb | 376 | $4,717 | 1.19 | 31.7 |
| updated_full | es_ny_orb | 173 | $4,241 | 1.18 | 12.1 |
| updated_full | nq_asia_orb | 167 | $19,847 | 1.66 | 60.3 |
| updated_full | nq_ny_htf_lsi | 86 | $10,926 | 1.68 | 22.4 |
| updated_full | nq_ny_orb_r11 | 126 | $4,640 | 1.30 | 22.8 |

| Year | Payout | Breach | Avg PayD | MCBch | EV/Start |
| --- | --- | --- | --- | --- | --- |
| 2024 | 76.2% | 23.8% | 40.6 | 2 | $146 |
| 2025 | 76.9% | 23.1% | 23.4 | 4 | $220 |
| 2026_updated | 100.0% | 0.0% | 37.3 | 0 | $100 |

## 5. Asia Sleeve Risk Balance

Grid varies only the Asia risks on the updated exact ALPHA stream. Other legs remain fixed. Ranking emphasizes 2024-2025 payout quality, breach control, and payout speed.

| Combo | NQ Asia | ES Asia | 24-25 Payout | Max Breach | Avg PayD | Net | DD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nq450_es150 | $450 | $150 | 78.9% | 23.1% | 30.3 | $48,966 | $-4,740 |
| nq450_es100 | $450 | $100 | 78.5% | 23.1% | 30.7 | $47,306 | $-4,219 |
| nq400_es150 | $400 | $150 | 78.5% | 23.1% | 30.4 | $46,696 | $-4,617 |
| nq300_es100 | $300 | $100 | 77.9% | 23.1% | 37.0 | $39,758 | $-3,876 |
| nq400_es200 | $400 | $200 | 76.6% | 23.8% | 29.8 | $48,637 | $-4,947 |
| nq350_es200 | $350 | $200 | 76.6% | 23.8% | 31.9 | $46,356 | $-4,697 |
| nq350_es100 | $350 | $100 | 77.9% | 25.0% | 36.4 | $42,754 | $-3,979 |
| nq400_es100 | $400 | $100 | 76.0% | 25.0% | 33.6 | $45,036 | $-4,101 |

Current combo (`NQ Asia $400 / ES Asia $150`) account read:

| Year | Payout | Breach | Avg PayD | MCBch | EV/Start |
| --- | --- | --- | --- | --- | --- |
| 2024 | 80.0% | 20.0% | 37.8 | 2 | $146 |
| 2025 | 76.9% | 23.1% | 23.1 | 4 | $220 |
| 2026_updated | 100.0% | 0.0% | 40.7 | 0 | $100 |

## Read

- Priority 1 is the gating result: Hunter is still interesting, but the prior research stream and live engine stream are not the same thing.
- Priority 2 says the `0.25x` label is not a clean proportional risk label under current Hunter sizing because of the 1-MNQ floor.
- Priority 3 should be judged on the revalued portfolio/account tables, not the old `$400` ATH file.
- Priority 4 gives the current exact ALPHA reference through the latest common local data.
- Priority 5 keeps the Asia-risk question bounded to risk balance only; no Asia parameter changes were searched.

