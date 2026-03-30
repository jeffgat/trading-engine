# FAST_V2 Execution Config — Robust Pipeline Report

**Date**: 2026-03-29
**Pipeline version**: Bailey-aware 5-phase (PBO/CSCV/DSR/PSR not implemented — verdicts are heuristic)
**Hold-out**: 2025-03-01 to 2026-02-28 (pre-registered, frozen before Phase 1)
**Walk-forward**: 12m IS / 3m OOS / 3m step, rolling, 32 folds, objective=sharpe
**Monte Carlo**: 2000 block_bootstrap sims, 15R ruin threshold

**Note**: FAST_V2 is the **only live portfolio** — it has a TradersPost webhook and is actively executing trades.

---

## Executive Summary

FAST_V2 produced the **first and only GO verdict** across all portfolios tested: **ES_Asia** passed all 5 phases with exceptional metrics (91.4% WR, Sharpe 3.18, DD -8.5R, 100% MC survival). NQ_NY_LSI came very close (4/5 phases, 98.9% MC survival) failing only on the annual R floor. NQ_NY also showed promise with strong Phase 2 results but failed on monthly loss spikes and MC survival.

The two "both directions" ORB continuation legs (NQ_NY, NQ_Asia) and both LSI legs trade on fundamentally different parameter profiles than the FAST config — FAST_V2's inline overrides produce meaningfully different behavior than main.py defaults.

---

## Results Matrix

| # | Leg | P1 | P2 | P3 | P4 | P5 | Verdict | OOS Trades | OOS Sharpe | OOS DD | OOS Net R |
|---|-----|:--:|:--:|:--:|:--:|:--:|:-------:|:----------:|:---------:|:------:|:---------:|
| 1 | NQ_NY | PASS | PASS | **FAIL** | PASS | **FAIL** | NO-GO | 1062 | 1.72 | -16.2R | +59.3R |
| 2 | NQ_Asia | PASS | **FAIL** | **FAIL** | PASS | **FAIL** | NO-GO | 923 | 0.10 | -24.4R | +7.3R |
| 3 | ES_Asia | PASS | PASS | PASS | PASS | PASS | **GO** | 1665 | 3.18 | -8.5R | +114.2R |
| 4 | NQ_Asia_LSI | PASS | **FAIL** | **FAIL** | PASS | PASS | NO-GO | 156 | 2.65 | -4.7R | +22.2R |
| 5 | NQ_NY_LSI | PASS | PASS | **FAIL** | PASS | PASS | NO-GO | 412 | 2.39 | -7.9R | +49.8R |

---

## Per-Leg Detail

### 1. NQ_NY (Continuation, Both Directions)

**Config**: ORB 09:30-09:45, entry<13:00, flat 15:50, stop=8% ATR-14, rr=2.5, tp1=0.3, both dirs, Fri excl
**Grid**: 625/fold, 20,000 total trials
**Runtime**: 17 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 1210 trades, 66% WR |
| 2 Walk-Forward | **PASS** | WF efficiency **0.572**, stability **0.750** (high) |
| 3 Prop Constraints | **FAIL** | Worst month -7.8R, annual R <12R, 2020 -7.6R |
| 4 Hold-Out | PASS | Sharpe 4.75, 91.7% WR, +14.2R, DD -2.0R |
| 5 Monte Carlo | **FAIL** | 68.4% survival (barely missed 70%) |

**Mode params**: stop=6.0, rr=2.0, gap=2.0, tp1=0.2
**Notable**: Both directions generates more trades (1062 OOS vs FAST's 500 long-only). WF efficiency and stability are much stronger than FAST's NQ_NY (0.57 vs 0.15). Mode converged to lower rr/tp1 than anchor. MC survival at 68.4% missed by 1.6% — this would be CONDITIONAL with a slightly relaxed threshold.

---

### 2. NQ_Asia (Continuation, Both Directions)

**Config**: ORB 20:00-20:15, entry<22:30, flat 04:00-04:10, stop=150% ORB, rr=5.0, tp1=0.25, both dirs, Tue excl
**Grid**: 750/fold, 24,000 total trials
**Runtime**: 17 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 1094 trades, 47.3% WR |
| 2 Walk-Forward | **FAIL** | WF efficiency **-0.019** (negative!), stability 0.602 |
| 3 Prop Constraints | **FAIL** | Worst month -8.7R, annual R <12R |
| 4 Hold-Out | PASS | Sharpe 2.47, +23.8R |
| 5 Monte Carlo | **FAIL** | 0.8% survival — catastrophic |

**Mode params**: stop_orb=150%, rr=5.5, gap_orb=15%, tp1=0.35
**Key issue**: Negative WF efficiency means OOS performance is worse than random on average. The both-directions profile on NQ Asia with high R:R (5.0-5.5) produces extreme variance — the optimizer finds configs that work in-sample but anti-predict out-of-sample. This is the worst-performing leg across all three portfolios.

---

### 3. ES_Asia (Continuation, Both Directions) — GO

**Config**: ORB 20:00-20:10, entry<03:00, flat 06:45-06:55, stop=2.5% ATR-5, rr=1.75, tp1=0.3, both dirs
**Grid**: 625/fold, 20,000 total trials
**Runtime**: 15 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 1985 trades, 84.1% WR, Calmar 18.20, Sharpe 2.78 |
| 2 Walk-Forward | **PASS** | WF efficiency passes, stability **0.781** (high) |
| 3 Prop Constraints | **PASS** | Worst month -2.5R, annual R passes, expectancy passes |
| 4 Hold-Out | **PASS** | Sharpe 3.71, **94.3% WR**, +13.1R, DD -2.9R |
| 5 Monte Carlo | **PASS** | **100% survival**, 0.0% ruin, p95 DD manageable |

**Mode params**: stop=3.0, rr=1.25, gap=1.5, tp1=0.2

**Why this passed everything**:
- **Highest trade count** (1665 OOS) — statistically robust sample
- **91.4% WR** with low R:R (mode rr=1.25, tp1=0.2) — consistent small wins, rare losses
- **DD -8.5R, worst month -2.5R** — the tightest risk profile of any leg across all portfolios
- **Calmar 13.44** — exceptional risk-adjusted return
- **Stability 0.781** (high) — params converge consistently across folds
- Both directions works well on ES Asia — unlike NQ Asia where shorts degrade the profile

**This is the only GO verdict across all 22 legs tested (9 FAST + 5 FAST_V2 + 4 general_v1 + 4 remaining).**

---

### 4. NQ_Asia_LSI (Liquidity Sweep Inversion, Long Only)

**Config**: Entry 20:45-22:00, flat 00:00-00:10, gap=1.75% ATR-40, rr=1.75, tp1=0.7, n_left=3, n_right=3, close entry
**Grid**: 80/fold, 2,560 total trials
**Runtime**: 10 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 211 trades, 60.7% WR, Calmar 6.08 |
| 2 Walk-Forward | **FAIL** | WF efficiency **0.422** (missed 0.5), stability 0.677 |
| 3 Prop Constraints | **FAIL** | Annual R <12R (only ~3R/year with 156 OOS trades) |
| 4 Hold-Out | PASS | Sharpe 3.71, +5.2R (19 trades) |
| 5 Monte Carlo | PASS | 100% survival, 0.1% ruin |

**Mode params**: rr=2.0, tp1=0.8, gap=2.25
**Key issue**: FAST_V2's tighter entry window (20:45-22:00 vs FAST's 20:40-23:30) and smaller LSI pivots (n_left=3/n_right=3 vs FAST's 8/2) produce fewer trades — only 156 OOS across 8 years (~20/year). The risk profile is excellent (DD -4.7R, 100% MC survival) but there simply aren't enough trades to generate meaningful annual R. WF efficiency at 0.42 barely missed.

---

### 5. NQ_NY_LSI (Liquidity Sweep Inversion, Long Only) — Near-CONDITIONAL

**Config**: Entry 10:10-14:30, flat 15:50, gap=3.75% ATR-10, rr=2.5, tp1=0.2, n_left=5, n_right=60, fvg_limit, Wed+Thu excl
**Grid**: 100/fold, 3,200 total trials
**Runtime**: 31 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 467 trades, 72.6% WR |
| 2 Walk-Forward | **PASS** | WF efficiency **0.718** (best across all portfolios), stability 0.656 |
| 3 Prop Constraints | **FAIL** | Annual R <12R in 5/8 years (only failure) |
| 4 Hold-Out | **PASS** | Sharpe 4.97, 72.3% WR, +13.7R, DD -2.9R |
| 5 Monte Carlo | **PASS** | **98.9% survival**, 1.1% ruin |

**Mode params**: rr=2.75, tp1=0.3, gap=4.0

**Why this is the second-strongest leg**:
- **WF efficiency 0.718** — the highest of any leg across all three portfolios, meaning 72% of IS performance retained OOS
- **DD -7.9R, worst month -2.8R** — tight risk
- **All 8 OOS years positive** (6.4R to 18.0R range)
- **98.9% MC survival** — near-certain prop firm survival
- Mode rr=2.75 shifted slightly from anchor (2.5) — reasonable adaptation

The only failure is annual R averaging ~6R/year, below the 12R threshold. At a 10R or even 8R threshold this would pass Phase 3 and receive a GO verdict.

---

## Cross-Leg Analysis

### FAST_V2 vs FAST Comparison (Same Legs)

| Leg | FAST WF Eff | FAST_V2 WF Eff | FAST Verdict | FAST_V2 Verdict | Key Difference |
|-----|:-----------:|:--------------:|:------------:|:---------------:|----------------|
| NQ_NY | 0.153 | **0.572** | NO-GO | NO-GO | Both-dirs + different stop/rr dramatically improved WF |
| NQ_Asia | 0.346 | -0.019 | NO-GO | NO-GO | Both-dirs on NQ Asia destroyed the edge |
| ES_Asia | 0.523 | **passes** | NO-GO | **GO** | Both-dirs + ATR stop (vs ORB) was the winning formula |
| NQ_Asia_LSI | 0.523 | 0.422 | NO-GO | NO-GO | Tighter params (3/3 vs 8/2) reduced trades too much |
| NQ_NY_LSI | 0.661 | **0.718** | NO-GO | NO-GO | Slightly different entry window, similar excellence |

**Key insight**: FAST_V2's "both directions" policy works for ES_Asia (where shorts add value) but hurts NQ_Asia (where shorts are noise). The inline param overrides in FAST_V2 produce meaningfully better WF efficiency for NQ_NY but the improvement isn't enough to overcome monthly loss spikes.

---

## Methodology Caveats

- **PBO, CSCV, DSR, PSR are NOT implemented**. All verdicts are heuristic, not statistically deflated.
- **Phase 3 and Phase 5 operate on the same OOS trade set** from Phase 2. They are stress tests, not independent evidence.
- **Hold-out contamination**: The hold-out period has been tested multiple times across portfolios. Phase 4 results should be interpreted with caution for legs that share the same hold-out period with FAST legs.
- **ES_Asia GO verdict**: While all 5 phases passed, the 91.4% WR with rr=1.25 and tp1=0.2 is a low-edge-per-trade, high-frequency grinder. A small shift in market microstructure (wider spreads, fewer Asia FVGs) could degrade the win rate significantly. The GO is heuristic — PBO/DSR could potentially reject it.
