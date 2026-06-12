# ALPHA_V2 Portfolio

ALPHA_V2 is the challenger portfolio to ALPHA_V1. The design thesis is lower trade frequency, higher selectivity, and cleaner portfolio-level complementarity: each leg should earn its place as a specialist rather than adding another high-count continuation stream.

Current status: first live-dry candidate added on 2026-06-09. The execution profile is `ALPHA_V2`, enabled with no webhooks, so it can observe and log in dry-run mode without routing orders.

## Portfolio Intent

| Principle | ALPHA_V2 Target |
|---|---|
| Role vs ALPHA_V1 | Challenger portfolio, not a clone |
| Trade count | Lower frequency by design |
| Trade quality | Prefer structurally gated, exact-replayed, cost-stressed legs |
| Leg overlap | Prefer different session logic, filters, payoffs, or market states from ALPHA_V1 |
| Promotion path | Live-dry monitoring before any webhook or scaled risk |

## Active Dry-Run Legs

### Leg 1: ORB/NQ_NY-RR2

**Live-dry challenger, native rolling ATR/ORB gated NY ORB**

| Field | Value |
|---|---|
| execution_config | `ALPHA_V2` |
| execution_session | `NQ_NY-RR2` |
| base_session | `NQ_NY` |
| deployability | `live_native` |
| strategy | ORB continuation with first 5m FVG outside range |
| session | New York |
| direction | Long only |
| ORB window | 09:30-09:45 ET |
| entry window | 09:45-13:00 ET |
| flat window | 15:50-16:00 ET |
| stop | 10.0% ATR14 |
| gap filter | 2.0% ATR14 |
| target | 1:2R |
| exit mode | Single target |
| DOW exclusion | None |
| pre-trade ATR gate | prior rolling ATR14% <= `1.6228084238855573` |
| pre-trade ORB gate | ORB range% <= `0.4657663656763981` |
| dry-run sizing | `risk_usd=250`, `max_single_risk_usd=375`, no webhooks |

### Validation Snapshot

| Window | Trades | Gross R | Net R | PF | Max DD | Win Rate | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| 2021-2024 pre-holdout exact | 151 | +31.74 | +27.41 | 1.31 | -10.03R | 41.06% | 2022 had no fills under the gates |
| 2025 holdout exact | 32 | +10.38 | +9.74 | 1.60 | -3.00R | 50.00% | Holdout opened 2026-06-09 |
| 2026 YTD exact | 14 | +4.00 | +3.78 | 1.47 | -3.00R | 42.86% | Through latest local data, 2026-06-05 |

MFE read: pre-holdout median MFE was `1.37R`, 38.41% reached `2R`; 2025 holdout median MFE was `1.34R`, 37.5% reached `2R`. This supports keeping the single `2R` target for dry-run observation instead of immediately changing the exit.

### Cost Stress

| Stress | Combined 2021-2025 Net R | PF | Max DD | Read |
|---|---:|---:|---:|---|
| 0 ticks/side extra | +37.15 | 1.36 | -10.77R | Baseline exact, commission-adjusted |
| 2 ticks/side extra | +28.50 | 1.26 | -12.11R | Dry-run pass envelope |
| 4 ticks/side extra | +19.85 | 1.17 | -14.07R | Still positive but thinner |
| 8 ticks/side extra | +2.54 | 1.02 | -19.78R | Edge boundary |

Operating rule: dry-run fill monitoring must show observed slippage comfortably inside the 2 ticks/side envelope before any live webhook or risk increase.

### MBP1 Order Book Feature Read

First order-book pass scored all 197 exact NQ_NY-RR2 trades against MBP1 windows around gap creation, gap revisit/pre-entry, and post-entry follow-through. The screen froze quartile thresholds on 2021-2024 and applied those unchanged to 2025 and 2026 inspection slices.

Baseline for the scored sample matched the exact replay: 2021-2024 produced 151 trades, +31.74R gross, 41.06% win rate, 1.37 PF, and -10.03R max DD; 2025 produced 32 trades, +10.38R gross, 50.00% win rate, 1.65 PF, and -3.00R max DD; 2026 YTD produced 14 trades, +4.00R gross, 42.86% win rate, 1.50 PF, and -3.00R max DD.

The best causal signals did not confirm a simple "buying pressure at revisit" thesis. The strongest read was quieter, cleaner gap creation: low `gap_create_5m_mid_range_ticks` had 38 development trades, +0.78R/trade, 63.16% win rate, 3.58 PF, and -2.00R max DD, then stayed positive in 2025 but had no 2026 coverage. Low `gap_create_5m_update_rate_per_sec` had 38 development trades, +0.57R/trade, 55.26% win rate, 2.61 PF, and stayed positive in both inspection slices.

The revisit/pre-entry read currently looks more like an avoidance filter than a confirmation filter. Low `pre_entry_10s_l1_imbalance_mean` and low `pre_entry_10s_bid_dominance_pct` were strong in 2021-2024 and 2026, but 2025 was mixed enough that these should remain shadow gates until combined-gate testing proves they add value without overfitting.

Post-entry velocity and imbalance were useful diagnostics, not entry filters. Strong post-entry 30s/60s velocity separated winners from losers, but those features occur after entry and should only be considered for future management/scratch research.

Combined frozen shadow-gate pass (2026-06-10): the best practical forward-tagging candidate was `gap_any_top3_q1__AND__pre10_imbalance_not_q4`, using thresholds fit only on 2021-2024. Rule: pass when any of low gap-creation 5m mid range, low gap-creation 5m update rate, or low gap-creation 5m price volume is true, and pre-entry 10s L1 imbalance is not in the highest development quartile. It retained 34/151 development trades at +27.41R gross, +0.81R/trade, 61.76% win rate, 3.45 PF, and -3.01R max DD; 2025 retained 15/32 trades at +7.00R, +0.47R/trade, 2.17 PF, and -2.53R max DD; 2026 YTD retained 5/14 trades at +4.00R, +0.80R/trade, 3.00 PF, and -1.00R max DD. This is a shadow-tagging candidate only; it should be forward-observed before any live native gate is added.

Evidence artifacts:

- `backtesting/data/results/nq_ny_orb_gap_orderbook_feature_lab_20260610_scored/summary.md`
- `backtesting/data/results/nq_ny_orb_gap_orderbook_feature_lab_20260610_scored/trade_orderbook_gap_features.csv`
- `backtesting/data/results/nq_ny_orb_gap_orderbook_bucket_screen_20260610/report.md`
- `backtesting/data/results/nq_ny_orb_gap_orderbook_bucket_screen_20260610/candidate_bucket_filters.csv`
- `backtesting/data/results/nq_ny_orb_gap_orderbook_combined_shadow_gates_20260610/report.md`
- `backtesting/data/results/nq_ny_orb_gap_orderbook_combined_shadow_gates_20260610/ranked_shadow_gates.csv`

### Why This Belongs In ALPHA_V2

This leg is intentionally different from the high-frequency ALPHA_V1 stack. It is a selective NY-only ORB sleeve, long-only, single-exit, and gated by native pre-trade volatility/range context. The research search did not freely optimize the whole strategy; it fixed the neutral ORB recipe first, then selected only the causal gating layer and direction using survivability-first criteria.

Selection priorities were:

1. Survive 2022-2023 first.
2. Avoid negative years in the 2021-2024 discovery window.
3. Require enough trades for evidence, but allow low frequency.
4. Pass PSR/DSR robustness checks.
5. Use Calmar and total R as tie breakers.

### Required Next Checks

Before promotion beyond dry-run:

| Check | Status |
|---|---|
| Exact replay through live execution engine | Done |
| 2025 holdout opened and accepted | Done |
| Cost/slippage stress | Done |
| Dry-run profile with no webhooks | Done |
| Live-vs-exact slippage logging | Pending |
| Overlap/correlation vs ALPHA_V1 legs | Pending |
| Portfolio-level ALPHA_V2 sizing simulation | Pending |

Evidence artifacts:

- `backtesting/data/results/discovery_runs/nq_ny_orb_exec_native_rolling_gate_2021_20260609/artifacts/exact_replay_results.md`
- `backtesting/data/results/discovery_runs/nq_ny_orb_exec_native_rolling_gate_2025_holdout_20260609/artifacts/holdout_results.md`
- `backtesting/data/results/discovery_runs/nq_ny_orb_exec_native_rolling_gate_2026_ytd_20260609/artifacts/exact_replay_2026_ytd.json`
- `backtesting/data/results/discovery_runs/nq_ny_orb_rolling_gate_cost_stress_20260609/artifacts/cost_stress_results.md`
