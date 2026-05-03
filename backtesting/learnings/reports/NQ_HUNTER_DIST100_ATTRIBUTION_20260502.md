# NQ Hunter ORB Dist100 Attribution (2026-05-02)

## Question

How much work is `ema15_max_distance=100` doing inside Hunter ORB, and is the idea worth testing on the current `ALPHA_V1` legs?

## Mechanic

Hunter's EMA distance value is directional:

- Long signal: `signal_close - confirmed_previous_15m_EMA`
- Short signal: `confirmed_previous_15m_EMA - signal_close`

The normal EMA gate allows a small wrong-side tolerance. A max-distance cap adds the other side of the band: reject the trade if the signal is already more than `N` points stretched beyond the EMA in the trade direction.

So `dist100` is a chase/exhaustion cap, not a regime gate.

## Stress-Gated Grid Read

Source: `backtesting/data/results/hunter_classic_stress_gate_strategy_workflow_20260502/candidate_grid_metrics.csv`

The table below compares `dist100` against no-cap with all other knobs paired: EMA length, tolerance, re-entry policy, and same-bar-win setting.

| Window | Median Trade Delta | Median Net Delta | Net Improved? | Median DD Delta | Median PF Delta |
|---|---:|---:|---:|---:|---:|
| Pre-holdout | -42 trades | -30.3R | 0% | -1.6R | -0.035 |
| Full 10y | -75 trades | -45.5R | 0% | -1.6R | -0.032 |
| 2025+ holdout | -33 trades | -21.8R | 0% | +0.0R | +0.178 |
| Last 1y | -24 trades | -15.6R | 20% | +0.0R | +0.143 |

Interpretation: `dist100` raises PF in the recent windows, but it does that by throwing away too much net R. It does not improve the long-history drawdown shape.

## Candidate-Level Comparisons

| Candidate Pair | Full 10y | 2025+ | Last 1y | Read |
|---|---:|---:|---:|---|
| Workflow leader no-cap | +162.9R / -40.5R DD | +104.2R | +88.4R | Best workflow-clean branch |
| Workflow leader with dist100 | +110.8R / -40.8R DD | +82.3R | +72.8R | Loses ~52R with no DD benefit |
| Balanced no-cap | +164.7R / -41.8R DD | +108.5R | +92.8R | Best pilot balance |
| Balanced with dist100 | +112.5R / -42.2R DD | +86.7R | +77.1R | Same problem: less R, no DD repair |
| Recent all-nonoverlap no-cap | +159.0R / -41.8R DD | +116.1R | +95.4R | Good recent but weaker pre-HO |
| Recent all-nonoverlap dist100 | +111.9R / -42.7R DD | +104.8R | +95.5R | Recent quality up, history broken |
| Recent all-nonoverlap dist150 | +163.2R / -41.8R DD | +132.9R | +107.6R | If using a cap, 150 beats 100 here |

## Leaderboard Signal

Distance distribution inside the Hunter workflow:

| Ranking | Top 10 | Top 25 | Top 50 |
|---|---|---|---|
| Pre-holdout | 10 no-cap | 25 no-cap | 50 no-cap |
| Full 10y | 7 dist150 / 3 no-cap | 13 dist150 / 12 no-cap | 33 no-cap / 17 dist150 |
| Last 1y | 10 dist150 | 24 dist150 / 1 dist100 | 40 dist150 / 6 dist100 / 4 dist125 |

`dist100` is not a robust leaderboard winner. The pre-holdout search wants no cap. The recent hot-regime board wants a looser `dist150`, not `dist100`.

## Raw Regime-Gate Context

From the regime-gate report:

- No cap, no regime gate: `+46.9R / -161.9R DD`
- `dist100`, no regime gate: about `0R / -122.6R DD`
- No cap + stress gate: `+150.9R / -41.8R DD`
- `dist100` + stress gate: `+110.0R / -42.2R DD`

The stress gate is doing the real repair. `dist100` reduces raw disaster risk but does not create a robust standalone edge, and once the stress gate is present it becomes mostly redundant and costly.

## ALPHA_V1 Transfer Read

Do not directly port `dist100` as a points-based rule. ALPHA_V1 spans NQ and ES, NY and Asia, and different stop/target structures. If tested, it should be normalized as an ATR-based entry-context cap, for example:

- `ema50_aligned`, `entry_context_min_atr=0.0`, `entry_context_max_atr=0.20-0.30`
- possibly `ema20_aligned` for a faster anchor

Existing adjacent evidence is not encouraging:

- `ORB_INDICATOR_CONFLUENCE_HOLDOUT_READ.md` tested similar MA/VWAP aligned-distance overlays on ALPHA ORB anchors. On the three ALPHA ORB legs, the promoted overlays reduced total holdout R on every leg.
- `ALPHA_V1_ORB_HTF_HIGH_FILTERS.md` tested another "headroom/chase quality" idea and rejected it as too destructive.

## Recommendation

Do not prioritize `dist100` for the active ALPHA_V1 legs.

If we still want to test the family, test it as a small pre-holdout-only research branch on the three ORB legs only, not the HTF-LSI leg:

1. Use ATR-normalized `entry_context_gate`, not raw point caps.
2. Test broader caps first: `0.20`, `0.25`, `0.30` ATR.
3. Require it to improve pre-holdout and holdout total R, not just PF or average R.
4. Treat `0.25-0.30 ATR` as the analog of Hunter's looser `dist150`, because `dist100` was too tight in the Hunter workflow.

