# ALPHA_V1 R11 Structure Gate Engine Replay - 2026-05-16

Report path: `learnings/reports/ALPHA_V1_R11_STRUCTURE_GATE_ENGINE_REPLAY_20260516.md`
Results path: `data/results/alpha_v1_r11_structure_gate_engine_replay_20260516`

## Why this run exists

The prior R11 read used an entry-minus-one-5m proxy because the cached exact CSV
did not include the original signal bar. This run adds a narrow
`structure_vwap_gate` research field to the ORB engine and applies each gate at
the candidate signal bar before one-trade-per-day ORB selection.

Deployability label: baseline is `live_native`; structure-gated variants are
`post_filter_only`. The replay itself is candidate-level and causal inside the
research engine, but the production execution router does not yet have this
pre-trade structure/VWAP gate.

## R11 Config

| Parameter | Value |
| --- | --- |
| instrument | MNQ |
| session | NY (09:30-09:50 ORB, 09:50-12:00 entry, flat 15:30) |
| strategy | continuation |
| direction_filter | long |
| stop_atr_pct | 7.0 |
| min_gap_atr_pct | 2.5 |
| atr_length | 12 |
| rr | 3.5 |
| tp1_ratio | 0.4 |
| exit_mode | split |
| excluded_days | Friday |
| risk_usd | $250 |
| commission | $0.575/contract/side |
| magnifier | 5m -> 1m hierarchical |

## Full-Window Results

| Variant | Trades | Keep | Net R | Delta | PF | DD | WR | Full TP | Deployability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 552 | 75.1% | 90.0R | +0.0R | 1.33 | -8.4R | 52.9% | 18.1% | live_native |
| any2of3_vwap_d10 | 497 | 74.7% | 82.1R | -7.8R | 1.33 | -7.9R | 53.3% | 18.1% | post_filter_only |
| hh_or_hl_vwap_d10 | 518 | 75.0% | 85.4R | -4.6R | 1.33 | -9.8R | 52.9% | 18.3% | post_filter_only |
| score_gte2_vwap_d10 | 518 | 75.0% | 85.4R | -4.6R | 1.33 | -9.8R | 52.9% | 18.3% | post_filter_only |
| any2of3_vwap | 503 | 74.6% | 80.3R | -9.7R | 1.32 | -10.5R | 53.1% | 17.9% | post_filter_only |
| hh_hl_2_vwap | 246 | 75.5% | 21.3R | -68.6R | 1.16 | -14.6R | 50.0% | 15.9% | post_filter_only |

## Recent Windows

| Window | Variant | Trades | Net R | Delta | PF | DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2025_plus | baseline | 60 | 7.0R | +0.0R | 1.23 | -6.1R |
| 2025_plus | any2of3_vwap_d10 | 52 | 11.6R | +4.6R | 1.47 | -5.1R |
| 2025_plus | hh_or_hl_vwap_d10 | 58 | 11.9R | +5.0R | 1.45 | -6.1R |
| 2025_plus | score_gte2_vwap_d10 | 58 | 11.9R | +5.0R | 1.45 | -6.1R |
| 2025_plus | any2of3_vwap | 53 | 13.8R | +6.8R | 1.59 | -5.1R |
| 2025_plus | hh_hl_2_vwap | 24 | -1.1R | -8.1R | 0.92 | -5.4R |
| last_1y | baseline | 49 | 5.1R | +0.0R | 1.19 | -6.1R |
| last_1y | any2of3_vwap_d10 | 42 | 11.9R | +6.8R | 1.61 | -5.1R |
| last_1y | hh_or_hl_vwap_d10 | 47 | 13.3R | +8.2R | 1.65 | -6.1R |
| last_1y | score_gte2_vwap_d10 | 47 | 13.3R | +8.2R | 1.65 | -6.1R |
| last_1y | any2of3_vwap | 43 | 10.9R | +5.8R | 1.53 | -5.1R |
| last_1y | hh_hl_2_vwap | 19 | 2.3R | -2.8R | 1.25 | -3.1R |

## Deployability Details

| Variant | Deployability | Live support notes | Exact replay required |
| --- | --- | --- | --- |
| baseline | live_native | Baseline NQ NY ORB R11 parameters are already expressible in the live ORB execution profile. | completed_through_2026-03-24 |
| any2of3_vwap_d10 | post_filter_only | Causal research-engine gate, but production execution does not yet compute 15m structure/VWAP before arming. | yes_after_live_pretrade_gate_implementation |
| hh_or_hl_vwap_d10 | post_filter_only | Causal research-engine gate, but production execution does not yet compute 15m structure/VWAP before arming. | yes_after_live_pretrade_gate_implementation |
| score_gte2_vwap_d10 | post_filter_only | Causal research-engine gate, but production execution does not yet compute 15m structure/VWAP before arming. | yes_after_live_pretrade_gate_implementation |
| any2of3_vwap | post_filter_only | Causal research-engine gate, but production execution does not yet compute 15m structure/VWAP before arming. | yes_after_live_pretrade_gate_implementation |
| hh_hl_2_vwap | post_filter_only | Causal research-engine gate, but production execution does not yet compute 15m structure/VWAP before arming. | yes_after_live_pretrade_gate_implementation |

## Read

`any2of3_vwap_d10` did not survive the true candidate replay. The proxy improvement was mostly not enough once the engine could choose later same-day setups.

Strict `hh_hl_2_vwap` remains a high-selectivity diagnostic rather than an
ALPHA-grade replacement unless a separate lower-risk specialist sleeve is being
designed. The comparison that matters for candidate #7 is whether
`any2of3_vwap_d10` beats baseline without sacrificing the full-history R pool.

Artifacts:

- `variant_metrics.csv`
- `window_metrics.csv`
- `filled_trades.csv`

Runtime: 28.2s
