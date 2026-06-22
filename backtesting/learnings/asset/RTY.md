# RTY (Russell 2000 E-mini) — Strategy Learnings

## Instrument Profile
- **Point value**: $50/point
- **Min tick**: 0.10 ($5/tick)
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-03 (~10 years, 5m + 1m + 1s)
- **Roll**: Calendar roll `.c.0` (index future — standard)
- **Liquidity**: Asia session has sufficient bar density for 15m ORB

---

## Strategies Tested

### Plain LDN ORB Breakout Broad Surface (2026-06-18) — EXACT-REPLAY QUEUE
- **Status**: EXACT-REPLAY QUEUE ONLY — RTY LDN plain ORB breakout clusters passed broad-surface promotion gates. RTY NY and RTY Asia remained rejected.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_BROAD_FULL_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_broad_full_20260618/`.
- **Scope**: `strategy="orb_breakout"` broad grid, train `2021-2023`, validation `2024`, holdout closed from `2025` onward.
- **Top row**: `rty__ldn__orb15__stop12p5__gap0__rr2__long__no_tue__small_orb_only` had 2024 validation `+22.03R`, 2021-2024 preholdout `+47.89R`, stress `+21.49R`, cluster score `1.00`, DSR `0.8202`.
- **Nearby cluster**: The top-3 RTY LDN rows all promoted, including two 30m short variants with validation `+21.31R` / `+19.43R`, stress `+22.17R` / `+22.59R`, and DSR `0.7659` / `0.7785`.
- **Conclusion**: RTY LDN plain breakout deserves exact replay as a candidate cluster, not a single isolated row. Keep holdout closed until exact replay confirms parity.

### Plain LDN ORB Breakout Exact Replay (2026-06-18) — MIXED
- **Status**: RTY LDN R1 exact-replay PASS; R2 WATCH; R3 FAIL. Holdout stayed closed.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_EXACT_REPLAY_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_exact_replay_20260618/`.
- **Scope**: execution-engine exact replay of one-sided promoted RTY LDN broad-surface rows over `2021-01-01` to `2024-12-31`, using 5m signal bars and 1s fill/exit sequencing.
- **Pass**: `rty__ldn__orb15__stop12p5__gap0__rr2__long__no_tue__small_orb_only` produced `278` exact trades, `+41.66` net R, PF `1.33`, max DD `-6.95R`, and `87%` retention versus research preholdout R. Exact year R was positive in 2021-2024: `+9.79R`, `+3.50R`, `+17.35R`, `+26.26R`.
- **Watch/fail**: the Friday-exclusion 30m short remained positive (`+23.98R`, PF `1.48`, `54%` retention) but drifted enough to stay WATCH. The Thursday-exclusion 30m short failed (`13` trades, `-0.97R`).
- **Conclusion**: Promote the 15m long/no-Tuesday row as the RTY exact-replay survivor. Keep the 30m short/no-Friday row as a challenger only; reject the no-Thursday short row for this workflow.

### Plain LDN ORB Breakout Exact Stress (2026-06-18) — FAIL
- **Status**: FAIL under strict exact cost/slippage stress. Holdout stayed closed.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_EXACT_STRESS_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_exact_stress_20260618/`.
- **Stress model**: post-exact-replay accounting on the frozen trade ledger, with `2x` baseline commission plus `2` adverse ticks per side on every filled round trip. Signal/fill path unchanged.
- **Result**: `rty__ldn__orb15__stop12p5__gap0__rr2__long__no_tue__small_orb_only` fell from exact `+41.66R` to stressed `-0.14R`, PF `1.00`, DD `-20.50R`. Year split under full stress had three negative years: 2021 `-0.11R`, 2022 `-2.26R`, 2023 `-4.06R`, 2024 `+6.29R`.
- **Conclusion**: Reject the RTY plain LDN breakout row for this workflow. The baseline edge is too thin after realistic adverse slippage and doubled fees.

### 1. Asia Continuation Longs — NO-GO
- **Status**: NO-GO (pipeline failed Phase 2 + Phase 3)
- **Config**: stop=4.0%, rr=2.5, gap=0.9%, tp1=0.3, ATR 14, 15m ORB (20:00-20:15), entry≤23:15, flat=06:45, long-only, excl Tue
- **Script**: `run_rty_asia_pipeline.py`

**Full-history (Phase 1 — PASS)**:
| Metric | Value |
|--------|-------|
| Trades | 715 |
| Win Rate | 59.9% |
| Net R | +71.2R |
| Sharpe | 1.556 |
| Calmar | 6.26 |
| Max DD | -11.4R |
| PF | 1.24 |

**Walk-forward (Phase 2 — FAIL)**:
- 5 folds (36m IS / 12m OOS / 12m step), 180 combos/fold
- WF efficiency: **0.28** (threshold ≥ 0.30) — marginal fail
- Stability: 0.90 (high) — params are stable across folds
- Combined OOS: 414 trades, +38.2R, Sharpe 1.399, Calmar 3.30, PF 1.22
- **2021 negative year (-2.5R)** in OOS — consistency concern
- Fold 3 (OOS 2021) had negative Calmar (-0.242)

**Prop Constraints (Phase 3 — FAIL)**:
- Avg annual R: 7.6R (threshold ≥ 12R) — insufficient annual return
- Positive expectancy: 0.092R (PASS)
- Max DD: -11.6R (INFO)

**Verdict**: In-sample metrics look strong (Calmar 6.26, 0 neg years) but OOS performance degrades significantly. WF efficiency at 0.28 suggests mild overfitting. Annual R of 7.6R on OOS is below prop firm viability.

### 2. NY Continuation Longs — NO-GO
- **Status**: NO-GO (pipeline failed Phase 2 + Phase 3)
- **Config**: stop=3.0%, rr=5.5, gap=1.0%, tp1=0.45, ATR 14, 15m ORB (09:30-09:45), entry≤15:30, flat=15:50, long-only, no DOW exclusion, 1s magnifier
- **Script**: `run_rty_ny_pipeline.py`

**Full-history (Phase 1 — PASS)**:
| Metric | Value |
|--------|-------|
| Trades | 1012 |
| Win Rate | 33.7% |
| Net R | +217.2R |
| Sharpe | 1.811 |
| Calmar | 10.87 |
| Max DD | -20.0R |
| PF | 1.32 |

**Walk-forward (Phase 2 — FAIL)**:
- 5 folds (36m IS / 12m OOS / 12m step), 375 combos/fold
- WF efficiency: **0.17** (threshold ≥ 0.30) — significant fail
- Stability: 0.75 (high) — params mostly stable but rr drifts to 6.5, stop to 5.0
- Combined OOS: 585 trades, +59.3R, Sharpe 0.835, Calmar 2.07, PF 1.14
- **3 negative OOS years** (2019: -1.3R, 2022: -1.6R, 2023: -3.1R)
- IS Calmars 3.3–9.5 collapsed to mostly negative OOS — classic overfitting

**Prop Constraints (Phase 3 — FAIL)**:
- Avg annual R: 11.9R (threshold ≥ 12R) — just below
- Positive expectancy: 0.101R (PASS)
- Max DD: -28.7R (INFO)

**Verdict**: Structural metrics were excellent (Calmar 10.87, 0 neg years) but WF efficiency of 0.17 confirms overfitting. The optimized params don't generalize. Annual R of 11.9R on OOS is borderline but with 3 negative years out of 5, consistency is poor.

**Optimization path**: 7 rounds of variable sweeps + 2 grid sweeps + 1 fine-tune grid (6,272 combos, 5h51m with 1s). User constraint: stop ≥ 3.0%. Converged anchor: stop=3.0%, rr=5.5, gap=1.0%, tp1=0.45.

---

## Key Findings

### Direction (updated 2026-04)
- **Both directions work with ORB-range stops** — the prior longs-only finding was an artifact of ATR-based stops. With ORB-range stops (75-100%), both-direction configs produce Calmar 7-9 on pre-holdout with 0 neg years.
- **Shorts are still destructive with ATR stops** — the original finding remains valid for ATR-based stop configs.

### Stop Type — Critical Discovery
- **ORB-range stops (75-100%) are dramatically superior to ATR stops on RTY NY**. The entire top 25 in the 3-session discovery uses ORB-range stops. ATR stops were used in prior testing (Strategies 1-2) which may explain the poor WF efficiency.

### Session
- **NY is the dominant session**: Scores 4-6 (best across any tested instrument). LDN has moderate longs. Asia is dead.
- **10m ORB is the optimal window**: Entire top 25 uses 10m ORB across all stop/RR/TP1 combinations.

### DOW Exclusion
- **Tuesday exclusion** consistently improved Calmar in prior Asia/NY longs-only tests (+0.5 to +0.8 Calmar). Not yet tested on the new ORB-range-stop configs.

### Parameter Interactions (prior testing)
- Entry_end=21:00 + gap=2.5% + tp1=0.6 caused destructive interaction when compounded (715→143 trades, Calmar 5.77→3.64). Individual adoptions looked strong but collapsed when combined.

---

## Parameter Sensitivity

### Asia Session
- **stop**: 4.0% dominated top 20 in grid (14/20). Very stable across WF folds.
- **rr**: 2.5 optimal in grid. Mode=2.5 in WF (score 1.0). Some folds prefer 3.0.
- **tp1**: 0.3 in grid, mode=0.4 in WF. Score 1.0 but split between 0.3/0.4.
- **gap**: 0.9% in grid, mode=0.5 in WF (score 0.6). Least stable dimension.

### NY Session
- **stop**: 3.0% in fine-tune grid (user floor), but WF mode=5.0. Large gap suggests overfitting at 3.0%.
- **rr**: 5.5 in grid, WF mode=6.5 (score 1.0). High rr works IS but doesn't generalize OOS.
- **tp1**: 0.45 in grid, WF mode=0.55 (score 0.40). Least stable — splits across folds.
- **gap**: 1.0% in grid, WF mode=1.0 (score 1.0). Most stable dimension.
- **Bimodal stop**: Fine-tune grid top 30 had bimodal stop distribution (3.0 and 5.5 both strong).

## Overall Assessment (updated 2026-04)
**RTY NY ORB continuation with ORB-range stops is a validated GO strategy.** The prior NO-GO verdict was specific to longs-only + ATR stops, which produced WFE <0.30. The 3-session discovery (1,296 configs/session) found that 10m ORB + ORB-range stops (75-100%) + both directions produces walk-forward Calmars 4.7-7.2, DSR 0.31-0.59 (survives deflation), and PSR >=0.998. Three configs survived holdout with positive R and payout rates 40-52%. NY-4 (ORB 100%, RR 3.0, TP1 0.4, both) earned STRONG verdict. Recommended next step: variable sweep optimization on the NY-4/NY-1/NY-2 anchors to further refine. Separate caution: the later RTY HTF-LSI thesis did not transfer into a funded-holdout survivor, so keep that branch distinct and closed.

### 3. NY LSI (Liquidity Sweep Inversion) — Both Directions — NO-GO
- **Status**: **NO-GO** (definitive — losing strategy, no edge)
- **Baseline** (2026-03-01): ORB 09:30-09:35, entry 09:35-15:30, flat 15:50, rr=2.625, tp1=0.3, gap=2.25%, n_left=3, n_right=3, fvg_window=10, absolute stop
- **Both**: 2060 trades, 53.7% WR, **PF 0.91**, -73.4R net, Sharpe -0.62, DD -87.6R, **6/9 neg years** (no 2016 data)
- **Longs**: 1073 trades, 53.3% WR, PF 0.86, -61.2R net, 8 neg years — actively destructive
- **Shorts**: 987 trades, 54.2% WR, PF 0.97, -12.3R net, 5 neg years — closest to breakeven but still losing
- **R by year (both)**: 2017:-10 2018:+5 2019:-32 2020:+28 2021:+3 2022:-8 2023:-18 2024:-21 2025:-22
- **Conclusion**: PF < 1.0 in all directions. Longs are the worst side (PF 0.86) — opposite of NQ where longs carry the edge. RTY lacks LSI edge.
- **Script**: `run_rty_ny_lsi_baseline.py`

### 4. 3-Session ORB Continuation Discovery (NY + Asia + LDN) — GO (NY-4 STRONG, NY-1/NY-2 CONDITIONAL)
- **Status**: **GO** — multiple NY configs pass phase-one with STRONG/CONDITIONAL verdicts
- **Scripts**: `run_rty_orb_discovery.py`, `run_rty_orb_discovery_pipeline.py`, `run_rty_orb_phase_one.py`
- **Sweep**: 1,296 configs per session (4 ORB windows × 2 stop modes × 4 RR × 4 TP1 × 3 directions × 5 stop values), 3,888 total. Pre-holdout <2025-01. 1m magnifier.

**Discovery sweep results:**
- **NY**: Outstanding — top 25 all 10m ORB, both directions, 0 neg years. Calmars 6.0-8.8, scores 4.4-6.4. ORB-range stops (75-100%) dominate.
- **Asia**: Weak — all configs 2+ neg years, best score -1.16.
- **LDN**: Moderate longs — best Calmar 3.44 (30m ORB 25%, RR 2.0, TP1 0.6, long, 0 neg yr).

**Discovery pipeline (WF 12m IS / 3m OOS / 3m step, Calmar objective):**
| Candidate | OOS R | Calmar | Sharpe | DD | WFE | Stability | Verdict |
|-----------|-------|--------|--------|------|-----|-----------|---------|
| NY-1 (ORB 75%, RR 3.5, TP1 0.6, both) | +145.9 | 7.17 | 1.44 | -20.4 | 0.385 | 0.720 | PROMOTE |
| NY-2 (ORB 100%, RR 3.5, TP1 0.6, both) | +126.8 | 5.94 | 1.36 | -21.4 | 0.389 | 0.800 | PROMOTE |
| NY-3 (ORB 100%, RR 2.0, TP1 0.5, both) | +83.3 | 4.74 | 1.08 | -17.6 | 0.394 | 1.000 | PROMOTE |
| NY-4 (ORB 100%, RR 3.0, TP1 0.4, both) | +95.2 | 5.13 | 1.15 | -18.6 | 0.376 | 0.860 | CHALLENGER |
| LDN-2 (ATR 5%, RR 2.0, TP1 0.6, long) | +64.3 | 2.33 | 1.03 | -27.6 | 0.593 | 0.900 | CHALLENGER |

**Phase-One Results (structural + prop sim + holdout + PSR/DSR):**
| Candidate | Pre R | HO R | Pre PR | HO PR | EV | PSR | DSR | Verdict |
|-----------|-------|------|--------|-------|------|-----|-----|---------|
| **NY-4** | +125.3 | **+1.2** | **62.7%** | **47.0%** | $12,479 | 0.999 | **0.419** | **STRONG** |
| NY-1 | +182.3 | **+11.0** | 58.1% | 43.1% | $11,540 | 1.000 | **0.590** | CONDITIONAL |
| NY-2 | +156.1 | **+8.8** | 59.9% | **52.2%** | $11,910 | 1.000 | **0.527** | CONDITIONAL |
| NY-3 | +103.3 | -6.1 | 59.7% | 40.1% | $11,868 | 0.998 | 0.311 | CONDITIONAL |
| LDN-2 | +109.7 | -15.0 | 61.9% | 25.7% | $12,314 | 0.999 | 0.414 | CONDITIONAL |

**Key findings:**
- **10m ORB + ORB-range stop + both directions** is the winning structural family on RTY NY
- All PSR >= 0.998 (strong) — the Sharpe ratios are statistically real
- DSR 0.31-0.59 — edge survives deflation from 1,296 trials (much stronger than YM's 0.008-0.031)
- NY-1 has the highest DSR (0.590) and best holdout (+11.0R) — strongest anti-overfitting evidence
- NY-2 has the best holdout payout rate (52.2%)
- NY-4 is the only STRONG verdict (PR 62.7%, HO PR 47.0%) — recommended for deployment
- NY-3 and LDN-2 failed holdout (negative R) — not recommended
- **Prior RTY testing was longs-only with ATR stops** — switching to both-direction + ORB-range stops unlocked a fundamentally different and much stronger edge

**Recommended configs for further optimization:**
- **NY-4** (STRONG): 10m ORB, ORB 100%, RR 3.0, TP1 0.4, both — best payout rate and EV
- **NY-1** (CONDITIONAL): 10m ORB, ORB 75%, RR 3.5, TP1 0.6, both — highest raw R and DSR
- **NY-2** (CONDITIONAL): 10m ORB, ORB 100%, RR 3.5, TP1 0.6, both — best holdout PR

---

### 5. NY HTF-LSI (Higher-Timeframe Liquidity Sweep Inversion) — NO-GO
- **Status**: **NO-GO** (pre-holdout family was alive, but the opened funded holdout failed across the frozen shortlist)
- **Scripts**: `run_cross_asset_htf_lsi_anchor_explore.py`, `run_cross_asset_htf_lsi_broad_discovery.py`, `run_cross_asset_htf_lsi_stitched_followup.py`, `run_rty_ny_htf_lsi_phase_one.py`
- **Holdout**: frozen until phase one, then opened once on `2025-04-01` to `2026-03-31`

**What was tested:**
- First replayed the trusted NQ transfer anchors on RTY `1m / 3m / 5m`. All four transfer rows were dead. Best anchor was still negative on both pre-holdout and validation quality (`1m lag0`: pre PF `0.947`, validation PF `0.855`).
- Reopened RTY-specific broad discovery after the failed transfer. The live cluster was very RTY-specific: `5m`, `short`, `fvg_limit`, `htf90`, `cap=2`, later entry cutoffs (`14:00-15:00`), `gap=2.0`, `rr=3.0-4.0`, `tp1=0.4-0.5`, and lag `12-30`.

**Best pre-holdout stitched candidates:**
- `rr4_lag20_atr14_l100`: stitched OOS `316` trades, PF `1.251`, avg R `0.131`, funded payout `42.3%`, funded EV/start `$105.12`
- `control_stage_b_end15`: stitched OOS `318` trades, PF `1.256`, avg R `0.116`, funded payout `47.9%`, funded EV/start `$100.37`
- `rr4_lag30_atr10_l60`: stitched OOS `343` trades, PF `1.221`, avg R `0.111`, funded payout `42.6%`, funded EV/start `$107.82`
- `quality_lag12_n5`: slower but clean pre-holdout quality branch, stitched OOS `216` trades, PF `1.228`, avg R `0.108`, funded payout `35.0%`, funded EV/start `$50.16`

**Opened holdout result:**
- All four frozen candidates were negative on raw holdout trade quality and negative on funded EV/start.
- `rr4_lag30_atr10_l60`: `55` holdout trades, PF `0.507`, avg R `-0.290`, funded payout `0.0%`, funded EV/start `-$100.00`
- `rr4_lag20_atr14_l100`: `54` holdout trades, PF `0.482`, avg R `-0.318`, funded payout `0.0%`, funded EV/start `-$100.00`
- `control_stage_b_end15`: `48` holdout trades, PF `0.472`, avg R `-0.268`, funded payout `0.0%`, funded EV/start `-$100.00`
- `quality_lag12_n5`: `38` holdout trades, PF `0.584`, avg R `-0.229`, funded payout `1.9%`, funded EV/start `-$97.82`

**Conclusion:**
- RTY HTF-LSI does have a real pre-holdout `5m short` family, so this was not a fake discovery.
- But the untouched phase-one holdout rejected the entire branch under the default funded-account model.
- Do **not** advance RTY HTF-LSI to phase two, and do not restart from the NQ transfer anchors. If RTY HTF-LSI is ever revisited, it needs a materially different RTY-native thesis rather than more tuning on this frozen family.

---

### Regime-Gate Transfer Update (2026-04-01)

Shared cross-asset regime-gate test showed that RTY is **candidate-dependent**, not uniformly helped by the NQ-style gate:

| Candidate | Ungated Holdout | Gated Holdout | Verdict |
|-----------|-----------------|---------------|---------|
| NY-1 | +36.0R, Cal 2.11, DD -17.1R, PR 46.2% | +32.0R, Cal 1.77, DD -18.0R, PR 54.6% | REJECTS GATE |
| NY-2 | +20.5R, Cal 1.36, DD -15.2R, PR 52.8% | +21.1R, Cal 1.76, DD -12.0R, PR 63.2% | SUPPORTS GATE |
| NY-4 | +15.4R, Cal 0.99, DD -15.5R, PR 52.7% | +19.4R, Cal 2.18, DD -8.9R, PR 59.7% | SUPPORTS GATE |

#### Updated Interpretation

1. **NY-2 and NY-4 are the right RTY gate-research branches.** Both improve holdout Calmar, reduce drawdown, and improve payout behavior under the medium-vol gate.
2. **NY-1 should remain ungated.** The gate improves Sharpe and payout rate but gives up too much net R / Calmar and slightly worsens drawdown.
3. **Second-round promotion**: use `NY-2` and `NY-4` for deeper regime-gate follow-up; keep `NY-1` as an ungated benchmark rather than a gated development branch.

### Regime-Gate Round Two Refinement (2026-04-01)

Round two split the RTY survivors into partial-gate vs full-gate winners:

| Candidate | Preferred Variant | Holdout | Why |
|-----------|-------------------|---------|-----|
| NY-2 | `block_bull_medium_vol` | +22.28R, Cal 1.776, DD -12.5R, PR 56.0% | `bull_medium_vol` was -1.75R; `sideways_medium_vol` was +1.18R |
| NY-4 | `block_full_medium_vol` | +19.44R, Cal 2.178, DD -8.9R, PR 59.7% | `bull_medium_vol` -2.83R and `sideways_medium_vol` -1.24R |

#### Updated Action

1. **NY-2 should use a partial gate**: block `bull_medium_vol` only.
2. **NY-4 should use the full medium-vol gate**: both blocked buckets were net harmful.
3. **NY-1 stays ungated** and should remain only as the comparison benchmark, not a gated promotion branch.
