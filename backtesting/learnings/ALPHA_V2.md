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
