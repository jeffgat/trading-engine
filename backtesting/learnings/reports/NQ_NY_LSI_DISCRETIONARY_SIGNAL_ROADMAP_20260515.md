# NQ NY LSI Discretionary Signal Roadmap

- Date: 2026-05-15
- Scope: roadmap after the NQ NY LSI order-book risk-tier replay.
- Current stance: DataBento cost should not cap the research program, but the next branch should first exhaust no-extra-fetch tests that can run on existing 1s, 1m, 5m, trade logs, and already-scored MBP-10 windows.
- Related reports:
  - `backtesting/learnings/reports/NQ_NY_LSI_ORDERBOOK_FEATURE_LAB_20260514.md`
  - `backtesting/learnings/reports/NQ_NY_LSI_ORDERBOOK_RISK_TIERS_20260515.md`

## Decision

Keep the order-book path alive, but do not broaden DataBento fetching yet. After the stricter account stress, the cleanest promotion lead is the pure 1m long `confirm_last_10s_mid_velocity_ticks_per_second` overlay because it had the best breach behavior. The 1m additive `pre_confirm_30s_pressure_score` overlay remains important but needs exact replay/conservative account-aware sizing before promotion. The 3m absorption-release family should remain chart-review only until a nondegenerate formulation appears.

Near-term research should prioritize price/structure proxies for the same discretionary idea:

> A watched level gets swept, rejected, reclaimed, and then price moves away quickly enough that the reversal feels violent rather than passive.

These paths are cheaper to iterate because they use existing bar/magnifier data and can be tested over wider history before deciding what deserves more MBP-10 coverage.

## No-Extra-Fetch Test Backlog

| Priority | Idea | Data Needed | Candidate Use | Initial Test |
| --- | --- | --- | --- | --- |
| 1 | Exact dynamic-sizing replay for 1m pressure survivor | Existing candidate trades plus existing MBP-10 scored windows | Risk tier, not skip filter | Replay `0.75x/1.0x/1.25x` and `0.5x/1.0x/1.5x` inside the execution-grade trade path; compare phase-one payout, breach, DD, and slippage stress. |
| 2 | Sweep-reclaim velocity | Existing 1s/1m NQ parquet plus LSI levels | Entry quality and risk tier | Measure sweep depth, seconds-to-reclaim, reclaim close strength, and 10s/30s/60s post-reclaim displacement. |
| 3 | Compression-then-expansion | Existing 1s/1m/5m NQ parquet | Entry quality and risk tier | Require pre-signal realized range/vol compression, then aligned displacement after reclaim/confirmation. |
| 4 | Failed continuation / trapped-trader proxy | Existing 1s/1m bars and volume | Reversal quality tier | Detect large push into the level with poor progress, wick/reclaim, then inverse displacement. |
| 5 | Clean-air / target-room score | Existing swing, session, HTF, FVG, and reference levels | Trade selection or target sizing | Score distance to nearest opposing level and whether the first target path is obstructed. |
| 6 | Manual label audit | Existing trade chart windows and scored feature CSVs | Feature validation | Label 30-50 examples as strong/violent versus weak/passive, then compare labels to pressure, reclaim, compression, and velocity features. |

### Completed First No-Fetch Pass

- `2026-05-15`: `backtesting/learnings/reports/NQ_NY_LSI_SWEEP_RECLAIM_VELOCITY_20260515.md` tested priority 2 using existing `NQ_1s.parquet` and frozen LSI candidate rows.
- Cleanest result: 3m hourly `add_3m_hourly_atr12p5_b3_a7p5` with `trapped_reversal_confirm_score` as a signal-close risk tier. Primary `0.5x/1.0x/1.5x` sizing improved holdout from `+12.17R` to `+17.34R`; conservative `0.75x/1.0x/1.25x` improved holdout to `+14.76R`.
- 1m result: sweep-reclaim price proxies did not replace the 1m MBP-10 pressure edge. Keep `pre_confirm_30s_pressure_score` alive as a separate order-book path.
- Correlation check: price-action trapped/reclaim features are near-zero correlated with `pre_confirm_30s_pressure_score`, so treat them as an orthogonal branch rather than a lower-cost duplicate.
- `2026-05-15`: `backtesting/learnings/reports/NQ_NY_LSI_DYNAMIC_SIZING_PHASE_ONE_20260515.md` tested priority 1/account-objective behavior using existing weighted trade replays. The 3m trapped-reversal branch looked excellent post-2023 but did not improve holdout-only EV; pure 1m long MBP velocity was lower capacity but had the cleanest breach behavior. Additive 1m MBP pressure improved holdout but worsened post-2023 account EV, so it needs exact replay/conservative account-aware sizing before any promotion.
- `2026-05-15`: `backtesting/learnings/reports/NQ_NY_LSI_3M_TRAPPED_REVERSAL_STRESS_20260515.md` pushed the 3m trapped-reversal survivor through no-fetch slippage, account-rule, tier, monthly, and bootstrap stress. Aggregate R still survived 1 tick/side slippage, but holdout account EV was flat-to-worse after daily stop and minimum trading-day rules. The live execution engine also cannot yet express the exact research shape (`3m`, `inversion_or_cisd`, `atr_pct` stop, 1s trapped-reversal feature), so this branch stays `research_only`.
- `2026-05-15`: `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_ORDERBOOK_VELOCITY_STRESS_20260515.md` applied the same stricter stress to the pure 1m long order-book velocity survivor. Primary `0.5/1/1.5` stayed breach-clean with 1 tick/side slippage and stricter account rules: post-2023 payout `86.2%`, breach `0.0%`, EV `+4.64R`; holdout payout `58.6%`, breach `0.0%`, EV `+3.83R` (`+0.57R` vs baseline). This becomes the cleaner promotion candidate, but it still requires live MBP-10 streaming and dynamic sizing implementation.
- `2026-05-15`: `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_ORDERBOOK_VELOCITY_LIVE_SCOPE_20260515.md` scoped live MBP-10 feature streaming plus dynamic sizing for the pure 1m survivor first. The implementation path is: optional `mbp-10` feed subscription, rolling top-of-book feature cache, `dynamic_sizing_provider` injection into `LSIEngine`, trade metadata persistence, then exact replay/paper parity before promotion.
- `2026-05-16`: `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_ORDERBOOK_VELOCITY_MIN_IMPL_VALIDATION_20260516.md` completed the minimum no-fetch implementation validation. The new execution-facing sizing decision module reproduced all `54` frozen pure 1m replay rows with `0` tier/weight/weighted-R mismatches and required `0` new historical DataBento days.

## DataBento Fetch Backlog

These are worth testing later, and the current instruction is to not discard them just because they need additional paid data.

| Priority | Idea | DataBento Need | Why It Is Worth Fetching Later | Guardrail |
| --- | --- | --- | --- | --- |
| A | Expand MBP-10 pressure coverage across all frozen LSI finalists | More sparse MBP-10 windows around all candidate trades, especially validation/holdout misses | Confirms whether `pre_confirm_30s_pressure_score` generalizes beyond the currently fetched windows. | Freeze candidate list and thresholds before fetching; do not use the new data for broad threshold mining. |
| A | Broader no-Thursday/allDOW additive pressure replay | MBP-10 windows for full finalist history | Tests whether the best order-book sizing overlay survives account-level simulation with more complete coverage. | Evaluate as risk-tier only first; include conservative sizing before aggressive sizing. |
| B | Post-confirm continuation management | MBP-10 windows extending 30s-180s after confirmation | Discretionary read suggests fast follow-through may support add/hold/scale decisions even when not entry-safe. | Do not use post-confirm features as entry filters; label as trade-management only. |
| B | Absorption-release reformulation | More MBP-10 windows, possibly with longer pre-level and post-reclaim context | The first 3m version was degenerate because zeros dominated; a richer formulation may capture "aggression into level, no progress, release." | Require nonzero prevalence and validation-only thresholds before holdout. |
| B | Cross-market confirmation | MBP-10 windows for ES/MNQ or correlated NQ/ES windows | Tests whether NQ reversal quality improves when ES confirms pressure/reclaim. | Avoid same-symbol overfitting; score only causal cross-market state. |
| C | Aggressor-flow / trade-print pressure | DataBento trades or MBO where available | Manual "violent buy/sell" may be closer to aggressive executed flow than passive depth. | Compare against MBP-only pressure; promote only if it adds out-of-sample value. |
| C | Liquidity pull / book vacuum | Wider MBP-10 context around the watched level | A fast reversal may strengthen when opposing liquidity pulls and same-side liquidity reloads. | Must be measured before entry/management decision time. |

## Promotion Rules

- No-extra-fetch features can move fastest if they are live-native from existing bar data.
- Order-book features remain `research_only` until live MBP-10 feature streaming, exact execution replay, and dynamic sizing support exist.
- Post-confirm order-book features are not entry filters. They can only be tested as add/hold/reduce logic unless a separate causal entry timestamp is defined.
- Do not combine allDOW and no-Thursday additive overlays as independent edges; they are overlapping variants of the same 1m additive family.
- Keep the 3m absorption-release result demoted unless a future formulation avoids zero-inflated tiers and passes validation before holdout.

## Recommended Next Run

After the minimum implementation validation, the next step is live wiring behind disabled-by-default flags:

1. Add optional `mbp-10` streaming and paper logging in `execution/src/trader/feed.py`, enabled only by profiles with `orderbook_dynamic_sizing.enabled = true`.
2. Add `dynamic_sizing_provider` to `LSIEngine` and persist requested/actual risk weight metadata.
3. Add a dry-run/paper config path for the pure 1m velocity survivor once signal cadence/parity is confirmed.
4. Only after paper parity should we fetch broader MBP-10 history.
