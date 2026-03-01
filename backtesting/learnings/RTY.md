# RTY (Russell 2000 E-mini) — Strategy Learnings

## Instrument Profile
- **Point value**: $50/point
- **Min tick**: 0.10 ($5/tick)
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-02 (~10 years, 5m + 1m + 1s)
- **Roll**: Calendar roll `.c.0` (index future — standard)
- **Liquidity**: Asia session has sufficient bar density for 15m ORB

---

## Strategies Tested

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

### Direction
- **Shorts are destructive**: Asia -59.1R, NY -19.3R over 10 years. Long-only is the only viable direction.

### DOW Exclusion
- **Tuesday exclusion** consistently improved Calmar across all anchor configs (+0.5 to +0.8 Calmar).

### Parameter Interactions
- Entry_end=21:00 + gap=2.5% + tp1=0.6 caused destructive interaction when compounded (715→143 trades, Calmar 5.77→3.64). Individual adoptions looked strong but collapsed when combined.

### Optimization History
- R1: Default → long adopted (Calmar -0.52 → 2.55)
- R2: Excl Tue adopted (2.55 → 3.32)
- R3: stop=4.0% + tp1=0.4 adopted (3.32 → 5.77)
- R4: entry_end=21:00 + tp1=0.6 + gap=2.5% adopted (5.77 maintained)
- R5: Compound R4 adoptions FAILED (trades collapsed). Reverted to R4 anchor.
- Grid sweep: 320 combos, winner stop=4.0%/rr=2.5/gap=0.9%/tp1=0.3 (Calmar 6.26)
- Pipeline: NO-GO (WF eff 0.28, avg annual R 7.6)

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

## Overall Assessment
RTY ORB+FVG continuation longs fail walk-forward validation in both sessions. The instrument shows strong in-sample curves but poor OOS generalization. Both Asia and NY exhibit WF efficiency well below 0.3, indicating the strategy's edge on RTY is likely curve-fitted. Not recommended for further ORB+FVG exploration without a fundamentally different approach (e.g., reversal, different entry logic).
