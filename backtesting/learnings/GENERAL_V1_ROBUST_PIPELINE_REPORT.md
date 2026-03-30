# general_v1 Execution Config — Robust Pipeline Report

**Date**: 2026-03-29
**Pipeline version**: Bailey-aware 5-phase (PBO/CSCV/DSR/PSR not implemented — verdicts are heuristic)
**Hold-out**: 2025-03-01 to 2026-02-28 (pre-registered, frozen before Phase 1)
**Walk-forward**: 12m IS / 3m OOS / 3m step, rolling, 32 folds, objective=sharpe
**Monte Carlo**: 2000 block_bootstrap sims, 15R ruin threshold

**Note**: general_v1 is a dry-run config (no webhooks). It uses the same main.py session defaults as FAST but with different risk sizing and two param overrides: NQ_Asia_LSI entry_end extended to 23:00, and NQ_NY_LSI gap lowered to 3.75%.

---

## Executive Summary

No legs received a GO verdict. However, **NQ_NY_LSI** continued its strong showing (4/5 phases passed, 100% MC survival, Sharpe 2.80) — the same pattern seen in both FAST and FAST_V2. The lowered gap filter (3.75% vs FAST's 5.0%) produces more trades (555 OOS vs FAST's 513) with nearly identical risk metrics.

The two ORB continuation legs (NQ_Asia, Bull Specialist) produced identical results to their FAST counterparts since they share the same main.py configs. The NQ_Asia_LSI with extended entry window (23:00) performed worse than FAST's version (WF eff 0.26 vs 0.52).

---

## Results Matrix

| # | Leg | P1 | P2 | P3 | P4 | P5 | Verdict | OOS Trades | OOS Sharpe | OOS DD | OOS Net R |
|---|-----|:--:|:--:|:--:|:--:|:--:|:-------:|:----------:|:---------:|:------:|:---------:|
| 1 | NQ_Asia | PASS | **FAIL** | **FAIL** | PASS | **FAIL** | NO-GO | 549 | 1.60 | -18.5R | +76.7R |
| 2 | NQ_NY_BULL | **FAIL** | PASS | PASS | **FAIL** | PASS | NO-GO | 71 | 3.92 | -3.0R | +17.0R |
| 3 | NQ_Asia_LSI | PASS | **FAIL** | **FAIL** | **FAIL** | **FAIL** | NO-GO | 317 | 2.00 | -11.5R | +43.3R |
| 4 | NQ_NY_LSI | PASS | PASS | **FAIL** | PASS | PASS | NO-GO | 555 | 2.80 | -7.3R | +85.0R |

---

## Per-Leg Detail

### 1. NQ_Asia (Continuation, Long Only)

**Config**: Identical to FAST NQ_Asia — ORB 20:00-20:15, stop=100% ORB, rr=6.0, tp1=0.3, Tue excl
**Grid**: 750/fold, 24,000 total trials
**Runtime**: 22 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 675 trades, 43.9% WR, Calmar 18.12 |
| 2 Walk-Forward | **FAIL** | WF efficiency **0.346**, stability 0.586 |
| 3 Prop Constraints | **FAIL** | Worst month -5.4R, annual R <12R, 2021 -6.4R |
| 4 Hold-Out | PASS | Sharpe 5.87, +30.8R |
| 5 Monte Carlo | **FAIL** | 44% survival at 15R |

**Mode params**: stop_orb=125%, rr=4.0, gap_orb=15%, tp1=0.3
**Identical to FAST NQ_Asia** — same config, same results. The WF optimizer selects the same mode params. The long-only NQ Asia ORB continuation with high R:R doesn't generalize well across the full 32-fold walk-forward.

---

### 2. NQ_NY_BULL_SPECIALIST (Continuation, Regime-Gated)

**Config**: Identical to FAST Bull Specialist — ORB 09:30-09:50, stop=6% ATR-12, rr=3.0, tp1=0.6, regime+structure gates, Fri excl
**Grid**: 625/fold, 20,000 total trials
**Runtime**: 3 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | **FAIL** | Only **85 trades** (threshold >=100) |
| 2 Walk-Forward | PASS | Stability **0.773** (high), mode: stop=4.0, rr=2.0, gap=3.5, tp1=0.4 |
| 3 Prop Constraints | PASS | DD -3.0R, worst month -2.0R |
| 4 Hold-Out | **FAIL** | Only **4 trades** in holdout, -1.2R |
| 5 Monte Carlo | PASS | 100% survival at 15R |

**Mode params**: stop=4.0, rr=2.0, gap=3.5, tp1=0.4
**Identical to FAST Bull Specialist** — same config, same results. The regime+structure gates remain too aggressive, leaving only ~9 trades/year. The strategy has an excellent risk profile when it trades but lacks statistical sample size.

---

### 3. NQ_Asia_LSI (Liquidity Sweep Inversion, Long Only) — Extended Entry Window

**Config**: Same as FAST NQ_Asia_LSI BUT with **entry_end="23:00"** (general_v1 override, vs FAST's 23:30)
- Entry 20:40-23:00, flat 04:00-07:00, gap=1.75% ATR-40, rr=2.0, tp1=0.7, n_left=8, n_right=2, close entry
**Grid**: 80/fold, 2,560 total trials
**Runtime**: 14 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 389 trades, 53.0% WR, Calmar 10.06 |
| 2 Walk-Forward | **FAIL** | WF efficiency **0.261** (vs FAST's 0.523), stability 0.531 |
| 3 Prop Constraints | **FAIL** | Annual R <12R |
| 4 Hold-Out | **FAIL** | Sharpe 0.66, PF near break-even |
| 5 Monte Carlo | **FAIL** | Survival 90.6% but ruin 9.3% (>5%) |

**Mode params**: rr=1.5, tp1=0.5, gap=2.25

**Key difference from FAST**: The general_v1 override shortens the entry window to 23:00 (vs FAST's 23:30), but this is paired with the wider FAST-style LSI pivots (n_left=8, n_right=2). The result is worse than FAST's version:

| Metric | FAST NQ_Asia_LSI | general_v1 NQ_Asia_LSI |
|--------|:----------------:|:---------------------:|
| WF Efficiency | 0.523 | 0.261 |
| OOS Trades | 424 | 317 |
| OOS Sharpe | 2.19 | 2.00 |
| OOS DD | -11.8R | -11.5R |
| MC Survival | 88.5% | 90.6% |

The shorter entry window reduces trade count and the wider pivot detection (8/2) may be capturing lower-quality sweeps. Overall, the general_v1 override degrades the Asia LSI leg.

---

### 4. NQ_NY_LSI (Liquidity Sweep Inversion, Long Only) — Lowered Gap Filter

**Config**: Same as FAST NQ_NY_LSI BUT with **min_gap_atr_pct=3.75%** (general_v1 override, vs FAST's 5.0%)
- Entry 09:35-15:30, flat 15:50, rr=3.0, tp1=0.3, ATR-10, n_left=8, n_right=60, fvg_limit, Wed+Thu excl
**Grid**: 100/fold, 3,200 total trials
**Runtime**: 13 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 646 trades, 61.1% WR, Calmar 13.28 |
| 2 Walk-Forward | **PASS** | WF efficiency **0.644**, stability 0.500 |
| 3 Prop Constraints | **FAIL** | Annual R <12R (only failure) |
| 4 Hold-Out | **PASS** | Sharpe 2.51, 68.4% WR, +7.9R |
| 5 Monte Carlo | **PASS** | **100% survival**, 0.1% ruin |

**Mode params**: rr=2.0, tp1=0.35, gap=4.0

**Key difference from FAST**: The lowered gap filter (3.75% anchor → mode converges to 4.0%) admits more FVGs, producing more trades:

| Metric | FAST NQ_NY_LSI | general_v1 NQ_NY_LSI |
|--------|:--------------:|:--------------------:|
| WF Efficiency | 0.661 | 0.644 |
| OOS Trades | 513 | 555 |
| OOS Sharpe | 3.12 | 2.80 |
| OOS DD | -7.3R | -7.3R |
| OOS Calmar | 12.04 | 11.64 |
| MC Survival | 100% | 100% |
| Worst Month | -4.0R | -4.0R |

Nearly identical risk profiles. The lower gap filter adds ~40 trades over 8 years with no degradation in DD or monthly loss. The Sharpe is slightly lower (2.80 vs 3.12) — the additional FVGs are marginally lower quality but don't hurt the risk profile. Mode rr converged to 2.0 (vs FAST's 4.0), suggesting the lower gap filter works better with a more conservative R:R.

**This is the third instance of NQ_NY_LSI reaching 4/5 phases across three portfolios** (FAST, FAST_V2, general_v1). The consistent pattern: excellent WF efficiency (0.64-0.72), 100% MC survival, DD -7 to -8R, but annual R averaging 10-11R/year — below the 12R threshold.

---

## Cross-Portfolio NQ_NY_LSI Comparison

The NQ_NY_LSI leg is the most robust strategy across all three portfolios tested. Here's how the three variants compare:

| Metric | FAST | FAST_V2 | general_v1 |
|--------|:----:|:-------:|:----------:|
| **Config Diff** | gap=5.0%, n_left=8 | gap=3.75%, n_left=5 | gap=3.75%, n_left=8 |
| WF Efficiency | 0.661 | **0.718** | 0.644 |
| OOS Trades | 513 | 412 | **555** |
| OOS Sharpe | **3.12** | 2.39 | 2.80 |
| OOS DD | -7.3R | -7.9R | **-7.3R** |
| OOS Calmar | **12.04** | 6.30 | 11.64 |
| MC Survival | 100% | 98.9% | 100% |
| Mode RR | 4.0 | 2.75 | 2.0 |
| Mode Gap | 5.0 | 4.0 | 4.0 |
| Phases Passed | 4/5 | 4/5 | 4/5 |

All three variants produce GO-quality risk profiles. The FAST version has the best Sharpe and Calmar, FAST_V2 has the best WF efficiency, and general_v1 has the most trades. The consistent failure is the annual R threshold — all three average 6-11R/year OOS.

---

## Methodology Caveats

- **PBO, CSCV, DSR, PSR are NOT implemented**. All verdicts are heuristic, not statistically deflated.
- **Phase 3 and Phase 5 operate on the same OOS trade set** from Phase 2. They are stress tests, not independent evidence.
- **Hold-out severely contaminated**: By this point the hold-out period has been tested 15+ times across portfolios. Phase 4 results for all legs should be treated as informational, not as true out-of-sample evidence.
- **NQ_Asia and Bull Specialist are identical to FAST**: Since general_v1 uses the same main.py defaults without overrides for these legs, their results are duplicates of the FAST pipeline.
- **Total trials across all general_v1 legs**: ~53,760 parameter combinations. Combined with FAST (~138,000) and FAST_V2 (~69,000), over 260,000 total trials have been run without DSR/PSR correction.
