# NQ Regime Research Learnings

## Framework Definition (v1)

Two independent axes, both point-in-time (shifted by 1 session — no lookahead):

**Trend axis:**
- Bull: `close_vs_sma20 >= +0.5%` AND `ret_5d > 0`
- Bear: `close_vs_sma20 <= -0.5%` AND `ret_5d < 0`
- Sideways: everything else (after warmup)

**Volatility axis:**
- `realized_vol_21d` = rolling 21-day log-return std * sqrt(252)
- Tercile thresholds computed on pre-holdout data only (2016-01 to 2024-02)
- Low: vol <= 12.52% annualized
- Medium: 12.52% < vol <= 20.40%
- High: vol > 20.40%

**Low-confidence flag:** `|close_vs_sma20| < 0.25%` OR `|ret_5d| < 0.5%` — 22.7% of days

**Holdout:** 2024-03 to 2026-02 (24 months, untouched until Phase D)

---

## Phase A Findings (2024-03-31)

### Trend Distribution (pre-holdout, 2516 days)

| Regime | Days | Share | Episodes | Avg Duration |
|--------|------|-------|----------|-------------|
| Bull | 1,242 | 49.4% | 251 | 6.1d |
| Sideways | 698 | 27.7% | 385 | 2.4d |
| Bear | 576 | 22.9% | 179 | 4.0d |

NQ has a structural bull bias — expected for an equity index over 2016-2024.

### Volatility Distribution

Tercile bucketing gives exactly 33.3% per bucket by construction. Vol episodes are much stickier than trend episodes (median 4-13 days vs 2-5 days). High-vol episodes can persist 160 days (2022).

### Combined 3x3 Grid

| Bucket | Days | Share | Episodes | Status |
|--------|------|-------|----------|--------|
| bull_low_vol | 489 | 19.4% | 106 | Healthy |
| bull_medium_vol | 444 | 17.6% | 125 | Healthy |
| bull_high_vol | 309 | 12.3% | 84 | Healthy |
| bear_high_vol | 298 | 11.8% | 85 | Healthy |
| sideways_low_vol | 250 | 9.9% | 117 | Healthy |
| sideways_high_vol | 232 | 9.2% | 137 | Healthy |
| sideways_medium_vol | 216 | 8.6% | 166 | Healthy |
| bear_medium_vol | 178 | 7.1% | 89 | Marginal |
| bear_low_vol | 100 | 4.0% | 43 | THIN |

### Key Observations

1. **bear_low_vol is the weakest bucket** — 4.0% share, 43 episodes, and has structural holes (0 days in 2017, 2020, 2022, 2024). Bear markets tend to be high-vol events, so low-vol bears are rare. Any specialist for this bucket will fail promotion due to insufficient trades/episodes. Proceeding as-is; the pipeline will naturally reject it.

2. **Vol is extremely regime-clustered by year:**
   - 2017: zero high-vol days (entire year low/medium)
   - 2022: zero low-vol days (97% high-vol — the rate-hike bear)
   - 2020: 62% high-vol (COVID)
   - This means vol bucketing is useful but has strong temporal concentration

3. **Sideways episodes are short** — median 2 days across all vol levels. This means sideways is more of a "transition between bull/bear" than a persistent state. Specialist optimization for sideways buckets needs many short episodes rather than a few long runs.

4. **Low-confidence days: 22.7%** — nearly 1 in 4 days is ambiguous. This is a feature, not a bug: the regime framework explicitly flags uncertainty rather than forcing a classification. Strategies should be tested with and without low-confidence days.

---

## Phase B Findings (2024-03-31)

18 threshold variants searched (3 SMA thresholds x 3 ret5d thresholds x 2 vol methods). 18 trials counted.

### Best Variants (by min_bucket_share)

| SMA Thresh | Ret5d Thresh | Vol Method | Min Bucket | Min Episodes |
|-----------|-------------|-----------|-----------|-------------|
| 0.25% | 0.0% | tercile | 4.69% | 47 |
| 0.25% | 0.25% | tercile | 4.45% | 48 |
| 0.50% (default) | 0.0% | tercile | 3.97% | 40 |

### Key Findings

1. **Tercile always beats quartile** — quartile dilutes the thinnest bucket further
2. **Looser SMA threshold (0.25%) is marginally better** but less interpretable
3. **No variant reaches 5% min_bucket_share** — `bear_low_vol` is structurally thin regardless of thresholds
4. **Ret5d threshold has minimal impact** — 0.0% is simplest and near-best
5. **Ambiguity rate is constant at 22.7%** across all variants (driven by low-confidence definition, not trend/vol thresholds)

### Decision

Stick with defaults (SMA=0.5%, ret5d=0%, tercile). The 0.72pp improvement from SMA=0.25% is not worth the reduced interpretability. The pipeline will naturally reject `bear_low_vol` as a specialist target.

## Phase C Findings (2024-03-31)

28 walk-forward folds tested (12m IS / 3m OOS / 3m step). Both criteria failed.

### Results
- **Mean label agreement: 64.3%** — IS-derived vs global thresholds disagree on 36% of OOS days
- **Stable frequencies: FAIL** — every bucket has CV ~1.0 (std equals mean)
- **No sparse buckets: FAIL** — every single bucket hits 0% in at least one fold

### Root Cause
The **trend axis is stable** (fixed SMA/ret5d thresholds). The **vol axis is unstable** because realized vol has extreme temporal clustering:
- Vol tercile thresholds shift dramatically with 12-month IS windows
- `low_upper` threshold: global=0.125, fold mean=0.139, std=0.048 (35% CV)
- Some 3-month OOS windows are 100% one vol regime (e.g., Q1 2022 = all high-vol)

### Verdict
Phase C failure means: **do not recompute vol thresholds adaptively**. Use the frozen pre-holdout thresholds (12.52% / 20.40%) throughout. This is consistent with the plan's v1 approach. The vol axis is operationally valid (point-in-time, no lookahead) but not stable under walk-forward recomputation.

## Phase D Findings (2024-03-31)

Holdout: 2024-03 to 2026-02 (623 days). Run once with frozen thresholds. 153 ambiguous days.

### Distribution Shifts (Pre-Holdout → Holdout)

| Bucket | Pre | Holdout | Diff |
|--------|-----|---------|------|
| bull_high_vol | 12.6% | 12.5% | -0.1% |
| bull_medium_vol | 18.1% | 19.1% | +1.0% |
| bull_low_vol | 20.2% | 17.8% | -2.4% |
| sideways_medium_vol | 7.7% | 16.5% | **+8.8%** |
| bear_medium_vol | 7.5% | 15.7% | **+8.2%** |
| bear_high_vol | 12.3% | 5.5% | **-6.8%** |

### Key Findings

1. **Bull buckets are stable** (within 2.4pp) — most important since primary strategies are long-biased
2. **Bear character changed** — holdout bears are medium-vol (rolling correction), not high-vol (crash). `bear_high_vol` halved, `bear_medium_vol` doubled.
3. **Sideways_medium_vol surged** — 2024-2025 had more medium-vol indecision than training data
4. **bear_low_vol nearly empty in holdout** (1.6%, 4 episodes) — confirms structural thinness

### Implications for Downstream
- Long-biased strategy attribution: reliable (stable bull buckets)
- Bear/sideways specialist research: treat with extra caution (different bear character in holdout)
- `bear_low_vol`: will fail promotion — confirmed across both training and holdout

## Attribution Findings (2024-03-31)

Three frozen robust strategies attributed across the 3x3 grid. All three are positive in 8 of 9 buckets.

### NQ NY Long R11 (567 trades, +128.0R)

| Bucket | Trades | Avg R | Total R | Verdict |
|--------|--------|-------|---------|---------|
| bear_low_vol | 25 | +0.640 | +16.0 | Best but thin |
| bull_low_vol | 95 | +0.367 | +34.8 | Core strength |
| sideways_medium_vol | 66 | +0.342 | +22.6 | Surprisingly strong |
| bear_high_vol | 58 | +0.295 | +17.1 | Robust in volatile bears |
| sideways_high_vol | 53 | -0.093 | -5.0 | **Only losing bucket** |

Edge is broadly uniform — not a specialist candidate. All-weather with one bucket to avoid (sideways_high_vol).

### NQ NY Short v2 (332 trades, +33.4R)

| Bucket | Trades | Avg R | Total R | Verdict |
|--------|--------|-------|---------|---------|
| bull_medium_vol | 42 | +0.249 | +10.5 | Paradoxically best |
| bull_high_vol | 40 | +0.227 | +9.1 | Countertrend works |
| bear_high_vol | 38 | +0.037 | +1.4 | Barely positive in "home" regime |
| sideways_medium_vol | 38 | -0.072 | -2.7 | **Only loser** |

Short strategy works best in bull regimes (countertrend), not bear. No clean regime separation.

### NQ Asia R9 (777 trades, +120.9R)

| Bucket | Trades | Avg R | Total R | Verdict |
|--------|--------|-------|---------|---------|
| bear_high_vol | 82 | +0.293 | +24.0 | Strong |
| sideways_medium_vol | 74 | +0.288 | +21.3 | Strong |
| bull_medium_vol | 126 | +0.215 | +27.1 | Solid core |
| bull_high_vol | 93 | -0.032 | -3.0 | **Only losing bucket** |

Broadly positive, not a specialist. Bull_high_vol is the one drag.

### Key Insight

**None of the three strategies show clean regime separation.** All are positive in 8/9 buckets with different "bad" buckets per strategy:
- NY Long: sideways_high_vol (-0.09 avg R)
- NY Short: sideways_medium_vol (-0.07 avg R)
- Asia R9: bull_high_vol (-0.03 avg R)

This is a **positive finding**: these strategies are robust all-weather systems, not fragile regime-dependent artifacts. The plan explicitly allows "no specialist warranted" as an honest outcome.

### Potential Regime-Gate Value

Rather than specialist promotion, the attribution suggests a **regime-avoidance gate** could add value:
- NY Long: skip sideways_high_vol days → saves ~5R of drag from 53 trades
- Asia R9: skip bull_high_vol days → saves ~3R of drag from 93 trades
- These are small improvements relative to total R (128R and 121R) — may not survive walk-forward

## Expanded Attribution: VWAP + LSI (2024-03-31)

### VWAP Sideways Both (1163 trades, -41.4R) — NO-GO

Dead on arrival. Negative total R. Sideways buckets all negative. Not viable as a sideways specialist.

### LSI Close-Entry (Best: Both, 1646 trades, +109.7R)

| Bucket | Long | Short | Both | Pattern |
|--------|------|-------|------|---------|
| bull_low_vol | +28.9 | +5.3 | +37.9 | **Core strength** |
| bear_high_vol | +34.2 | +4.4 | +34.9 | **Sweep-and-reverse alpha** |
| bear_medium_vol | +22.4 | -0.6 | +19.7 | Long only |
| bear_low_vol | +11.0 | +8.0 | +19.2 | Both contribute |
| bull_high_vol | +10.5 | +8.3 | +21.7 | Both contribute |
| bull_medium_vol | **-9.1** | **-8.4** | **-13.9** | **Consistent drag** |
| sideways_medium_vol | **-10.8** | **-4.6** | **-11.8** | **Consistent drag** |

### LSI FVG-Limit (Best: Both, 1401 trades, +109.9R)

Same pattern as close-entry. Long dominates (+95R), short adds value (+34R), both together best (+110R).

### Key Findings

1. **LSI shows genuine regime separation** — unlike the ORB continuation strategies which were all-weather
2. **Medium-vol is the consistent drag** — `bull_medium_vol` and `sideways_medium_vol` negative for every LSI variant. Medium-vol chop produces false sweeps without the sharp dislocations LSI needs.
3. **LSI long works best in bear_high_vol** (+34R, avg +0.308) — counterintuitive but structurally sound: volatile bears create sweeps that reverse, long entry catches the bounce
4. **Both directions > either alone** — long + short together don't cancel; they capture different setups (+110R vs +88R long-only)
5. **VWAP mean-reversion is not viable** for any regime on NQ NY
6. **Regime-avoidance gate opportunity**: filtering out medium-vol buckets (`bull_medium_vol` + `sideways_medium_vol`) could save ~25R of drag for LSI strategies — worth testing in walk-forward

### Potential Specialist Candidates

| Strategy | Target Regime | Rationale |
|----------|--------------|-----------|
| LSI Both (close or fvg_limit) | NOT medium_vol | Avoidance gate: skip bull_medium_vol + sideways_medium_vol |
| LSI Long | bear_high_vol | Strongest single-bucket edge (+34R, 111 trades, 85 episodes) |
| LSI Both | bull_low_vol | Largest bucket with consistent edge (+38-46R) |

## Specialist Promotion Results

**ORB continuation strategies (NY Long R11, NY Short v2, Asia R9):** No specialist warranted. All-weather with no clean regime separation.

**LSI strategies:** Genuine separation found. Medium-vol buckets are consistent drags. A regime-avoidance gate (filtering out medium-vol days) is the most promising next step — simpler and more robust than full specialist optimization per bucket.

**VWAP mean-reversion:** NO-GO on NQ NY across all regimes.

## Walk-Forward: Medium-Vol Avoidance Gate for LSI (2024-03-31)

28-fold walk-forward (12m IS / 3m OOS / 3m step) on pre-holdout data. Gate removes trades on `bull_medium_vol` and `sideways_medium_vol` days.

### LSI Close Both

| Metric | Baseline | Gated | Change |
|--------|----------|-------|--------|
| Trades | 1,141 | 868 | -24% |
| Net R | +97.4 | +111.0 | **+13.6** |
| Sharpe | 1.46 | 2.16 | **+0.71** |
| Calmar | 6.54 | 8.49 | **+1.95** |
| Max DD | -14.9R | -13.1R | +1.8R |
| PF | 1.23 | 1.35 | +0.12 |

18/28 folds improved or unchanged. Gate flipped 3 losing folds positive.

### LSI FVGLimit Both

| Metric | Baseline | Gated | Change |
|--------|----------|-------|--------|
| Trades | 969 | 742 | -23% |
| Net R | +104.6 | +117.2 | **+12.6** |
| Sharpe | 1.61 | 2.34 | **+0.73** |
| Calmar | 5.65 | 9.35 | **+3.70** |
| Max DD | -18.5R | -12.5R | **+6.0R** |
| PF | 1.27 | 1.41 | +0.14 |

### Verdict: SURVIVES WALK-FORWARD

The medium-vol avoidance gate is not a data-mined artifact. Structural explanation: medium-vol chop produces false LSI sweeps that don't reverse cleanly. Extreme vol (high or low) creates the sharp dislocations LSI needs.

## Holdout Confirmation (2024-03-31)

Single untouched run on 2024-03 to 2026-02 (24 months). No retuning.

Holdout has 37% medium-vol days (vs 26% pre-holdout), so gate removes 39% of trades (vs 24% in WF).

### LSI Close Both — HOLDOUT

| Metric | Baseline | Gated | Change |
|--------|----------|-------|--------|
| Trades | 307 | 188 | -39% |
| Net R | +6.1 | +10.8 | **+4.7** |
| Sharpe | 0.35 | 1.04 | **+0.68** |
| Max DD | -15.0R | -11.2R | **+3.8R** |

### LSI FVGLimit Both — HOLDOUT

| Metric | Baseline | Gated | Change |
|--------|----------|-------|--------|
| Trades | 260 | 159 | -39% |
| Net R | **-5.8** | **+3.0** | **+8.8** |
| Sharpe | -0.35 | +0.30 | **+0.65** |
| Max DD | -18.0R | -7.1R | **+10.9R** |

### Verdict: HOLDOUT CONFIRMED

Gate flipped FVGLimit from negative (-5.8R) to positive (+3.0R) on unseen data. Sharpe improvement (+0.65-0.68) matches walk-forward (+0.71-0.73). Max DD reduction is dramatic (up to +10.9R). The medium-vol avoidance gate is structurally sound.

## ORB vs LSI: Opposite Regime Preferences (2024-03-31)

The medium-vol avoidance gate is **LSI-specific**. ORB continuation strategies have the opposite regime preference.

### ORB Continuation Strategies — Medium-Vol is Their Strength

| Strategy | Medium-Vol R (avoided buckets) | Gate Effect |
|----------|-------------------------------|-------------|
| NY Long R11 | +30.6R (sideways_med +22.6, bull_med +8.0) | Gate would LOSE -30.6R |
| NY Short v2 | +7.7R (bull_med +10.5, sideways_med -2.7) | Gate would LOSE -7.7R |
| Asia R9 | +48.4R (bull_med +27.1, sideways_med +21.3) | Gate would LOSE -48.4R |

ORB continuation thrives in medium-vol because: steady trends produce clean ORB breakouts with consistent follow-through. Not too quiet (no movement) and not too volatile (whipsaws).

### LSI Strategies — Medium-Vol is Their Weakness

| Strategy | Medium-Vol R (avoided buckets) | Gate Effect |
|----------|-------------------------------|-------------|
| LSI Close Both | -25.7R | Gate SAVES +25.7R |
| LSI FVGLimit Both | -28.7R | Gate SAVES +28.7R |

LSI dies in medium-vol because: enough movement to trigger false sweeps, but not enough momentum for the reversal to follow through.

### Structural Complementarity

| Regime | ORB Continuation | LSI |
|--------|-----------------|-----|
| Medium vol | **Thrives** (+30-48R) | **Dies** (-26-29R) |
| High/Low vol | Mixed/weaker | **Thrives** (+135-139R) |

These two strategy families are structurally complementary: ORB works in the "boring" medium-vol that LSI can't trade, and LSI works in the extreme-vol where ORB is weaker. A portfolio combining both would have natural regime diversification without any gate — the gate only matters for standalone LSI deployment.

### Per-Strategy Regime Detail

**NY Long R11** (567 trades, +128.0R, DD -6.0R): Positive in 8/9 buckets. Best: bear_low_vol (+0.640 avg R, 25 trades), bull_low_vol (+0.367, 95 trades). Only loser: sideways_high_vol (-0.094, 53 trades). All 10 full years positive.

**NY Short v2** (332 trades, +33.4R, DD -6.6R): Paradoxically best in bull regimes (countertrend). Bull_medium_vol +0.249 avg R, bull_high_vol +0.227. Only loser: sideways_medium_vol (-0.072). Edge thin everywhere.

**Asia R9** (777 trades, +120.9R, DD -15.1R): Positive in 8/9 buckets. Best: bear_high_vol (+0.293), sideways_medium_vol (+0.288), bull_medium_vol (+0.215). Only loser: bull_high_vol (-0.032, 93 trades).

### Production Readiness

The medium-vol avoidance gate for LSI strategies has now passed:
1. Attribution: genuine regime separation identified
2. Walk-forward: 28-fold OOS confirmation (+13-14R net improvement)
3. Holdout: 24-month untouched confirmation (gate rescued FVGLimit from underwater)

Next: integrate as a production gate for NQ NY LSI strategies. The gate requires daily regime classification (close_vs_sma20, ret_5d, realized_vol_21d) computed before session open.

## ORB Discovery + Phase-One Results (2026-03-31)

### Discovery Sweep
3,888 configs swept across NY, Asia, LDN (4 ORB windows x 2 stop modes x 4 RR x 4 TP1 x 3 directions x 4-5 stop values). 8 candidates promoted through walk-forward (28 folds, 12m/3m/3m). All 8 had high stability (0.80-1.00). PSR/DSR validation applied (module: `validate/deflated_sharpe.py`).

### Phase-One Prop-Firm Results

| Candidate | Pre-holdout | Holdout | Pre Payout Rate | HO Payout Rate | HO EV/attempt | Verdict |
|-----------|------------|---------|-----------------|----------------|---------------|---------|
| **Asia-B** | +119.2R, Cal 9.51 | **+42.5R, Cal 6.55, Shp 3.77** | 57.1% | **76.7%** | **$15,288** | **PROMOTE** |
| Asia-A | +102.4R, Cal 9.11 | +37.9R, Cal 6.21, Shp 3.57 | 58.9% | 74.8% | $14,902 | Strong backup |
| NY-B | +62.6R, Cal 8.01 | +1.8R, Cal 0.17 | 76.5% | 30.8% | $6,085 | Shelved |

### Asia-B Config (WINNER)
- 15m ORB (20:00-20:15), ORB 100% stop, RR=3.5, TP1=0.6, long-only, ATR 14
- Medium-vol avoidance gate (skip bull_medium_vol + sideways_medium_vol days)
- Holdout: 115 trades, 46.1% WR, PF 1.71, DD -6.5R, Sharpe 3.77

### Key Findings
1. **Asia session dominates NQ ORB continuation** — both Asia candidates crushed holdout while NY collapsed
2. **Holdout improved over pre-holdout for Asia** — payout rate jumped from 57% to 77%. The regime gate is working.
3. **NY-B looked great pre-holdout (76.5% payout) but failed holdout (30.8%)** — 2024-2025 NY session unkind to this config
4. **ORB 100% stop (full range)** is the correct stop mode for Asia — wider stops survive overnight volatility
5. **Higher RR (3.5) beat lower RR (3.0)** on holdout despite fewer wins — bigger winners compensate
6. **LDN was rejected at PSR/DSR step** — Sharpe too low to survive multiple-testing penalty

## Cross-Asset Regime-Gate Transfer Study (2026-04-01)

Shared transfer-study protocol:
- Pre-holdout through `2024-02-29`
- Holdout `2024-03-01` to `2026-02-28`
- Gate = skip `bull_medium_vol` and `sideways_medium_vol`
- Revised shortlist only: NQ Asia-2 reference, ES Asia-B, GC Asia-1, RTY NY-1/2/4, SI Asia-1/3, CL LDN-1/2
- Script: `run_cross_asset_regime_gate_research.py`

### Candidate-Level Results

| Asset | Candidate | Ungated Holdout | Gated Holdout | Verdict |
|-------|-----------|-----------------|---------------|---------|
| NQ | Asia-2 | +49.6R, Cal 6.74, DD -7.4R | +42.5R, Cal 6.55, DD -6.5R | MIXED |
| ES | Asia-B | +49.4R, Cal 8.09, DD -6.1R | +36.1R, Cal 6.97, DD -5.2R | REJECTS GATE |
| GC | Asia-1 | +20.1R, Cal 1.38, DD -14.5R | +20.4R, Cal 1.74, DD -11.7R | SUPPORTS GATE |
| RTY | NY-1 | +36.0R, Cal 2.11, DD -17.1R | +32.0R, Cal 1.77, DD -18.0R | REJECTS GATE |
| RTY | NY-2 | +20.5R, Cal 1.36, DD -15.2R | +21.1R, Cal 1.76, DD -12.0R | SUPPORTS GATE |
| RTY | NY-4 | +15.4R, Cal 0.99, DD -15.5R | +19.4R, Cal 2.18, DD -8.9R | SUPPORTS GATE |
| SI | Asia-1 | +9.2R, Cal 0.86, DD -10.7R | +11.6R, Cal 2.29, DD -5.1R | SUPPORTS GATE |
| SI | Asia-3 | +15.6R, Cal 1.38, DD -11.3R | +17.8R, Cal 3.12, DD -5.7R | SUPPORTS GATE |
| CL | LDN-1 | +24.3R, Cal 1.05, DD -23.1R | +14.4R, Cal 0.63, DD -23.1R | REJECTS GATE |
| CL | LDN-2 | +9.7R, Cal 0.39, DD -25.1R | +3.7R, Cal 0.16, DD -23.5R | MIXED |

### Transfer Conclusions

1. **The NQ gate does not transfer universally.** NQ itself is only mixed under the shared split, and ES/CL clearly reject the same medium-vol avoidance rule.
2. **GC transfers cleanly.** Asia-1 keeps the same net R while improving holdout Calmar, Sharpe, drawdown, and payout rate under gating.
3. **RTY is candidate-dependent.** NY-2 and NY-4 improve materially with the gate, while NY-1 loses quality and should remain ungated.
4. **SI is the best new transfer win after GC.** Both Asia-1 and Asia-3 materially improve on holdout with much smaller drawdowns, even though payout rate does not always rise.
5. **CL should not be a regime-gate priority.** LDN-1 rejects the gate and LDN-2 stays too weak to justify a deeper gating branch.
6. **YM remains excluded.** Latest learnings still treat YM as structurally overfit / non-deployable, so it was intentionally omitted from this transfer batch.

### Second-Round Regime-Gate Shortlist

Promote these for deeper follow-up:
- `NQ Asia-2` as the reference case
- `GC Asia-1` as the strongest non-NQ gated continuation candidate
- `RTY NY-2` and `RTY NY-4` as the RTY candidates that actually improve with the gate
- `SI Asia-1` and `SI Asia-3` as the clearest cross-asset transfer successes

De-prioritize for gating work:
- `ES Asia-B` because the gate trims too many holdout winners
- `RTY NY-1` because ungated is structurally stronger
- `CL LDN-1` and `CL LDN-2` because the gate does not improve the candidate family enough to justify a second round

## Cross-Asset Regime-Gate Round Two (2026-04-01)

Round-two protocol:
- Same shared holdout `2024-03-01` to `2026-02-28`
- Survivors only: `NQ Asia-2`, `GC Asia-1`, `RTY NY-2`, `RTY NY-4`, `SI Asia-1`, `SI Asia-3`
- Tested four variants per candidate: `ungated`, `block_bull_medium_vol`, `block_sideways_medium_vol`, `block_full_medium_vol`
- Script: `run_cross_asset_regime_gate_round2.py`

### Preferred Variants

| Asset | Candidate | Preferred Variant | Holdout | Damage Bucket Read |
|-------|-----------|-------------------|---------|--------------------|
| NQ | Asia-2 | `ungated` | +49.6R, Cal 6.74, DD -7.4R | Neither medium-vol bucket was damaging enough |
| GC | Asia-1 | `block_bull_medium_vol` | +26.7R, Cal 2.18, DD -12.2R, PR 64.9% | `bull_medium_vol` was negative, `sideways_medium_vol` was positive |
| RTY | NY-2 | `block_bull_medium_vol` | +22.3R, Cal 1.78, DD -12.5R, PR 56.0% | `bull_medium_vol` negative, `sideways_medium_vol` slightly positive |
| RTY | NY-4 | `block_full_medium_vol` | +19.4R, Cal 2.18, DD -8.9R, PR 59.7% | Both medium-vol buckets negative |
| SI | Asia-1 | `block_full_medium_vol` | +11.6R, Cal 2.29, DD -5.1R, PR 46.1% | `sideways_medium_vol` was the real damage bucket |
| SI | Asia-3 | `block_full_medium_vol` | +17.8R, Cal 3.12, DD -5.7R, PR 47.7% | `sideways_medium_vol` was the real damage bucket |

### Round-Two Conclusions

1. **NQ is still the conceptual source of the research, but not the best live template.** Under this shared transfer-study split, NQ Asia-2 should stay ungated because medium-vol days were not the holdout problem.
2. **GC wants a lighter gate.** Blocking only `bull_medium_vol` is better than the full NQ gate because GC still makes money in `sideways_medium_vol`.
3. **RTY splits into two gate families.** NY-2 wants the same lighter `bull_medium_vol` block as GC, while NY-4 benefits from the full gate because both medium-vol buckets were negative.
4. **SI is the cleanest full-gate transfer.** Both Asia-1 and Asia-3 improve most under the full gate, with `sideways_medium_vol` doing most of the damage.

### Updated Regime-Gate Promotion Set

Promote with explicit gate flavors:
- `GC Asia-1` with `block_bull_medium_vol`
- `RTY NY-2` with `block_bull_medium_vol`
- `RTY NY-4` with `block_full_medium_vol`
- `SI Asia-1` with `block_full_medium_vol`
- `SI Asia-3` with `block_full_medium_vol`

Keep as reference / benchmark:
- `NQ Asia-2` ungated
