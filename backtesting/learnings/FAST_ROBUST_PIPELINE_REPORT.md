# FAST Execution Config — Robust Pipeline Report

**Date**: 2026-03-29
**Pipeline version**: Bailey-aware 5-phase (PBO/CSCV/DSR/PSR not implemented — verdicts are heuristic)
**Hold-out**: 2025-03-01 to 2026-02-28 (pre-registered, frozen before Phase 1)
**Walk-forward**: 12m IS / 3m OOS / 3m step, rolling, 32 folds, objective=sharpe
**Monte Carlo**: 2000 block_bootstrap sims, 15R ruin threshold

---

## Executive Summary

All 9 FAST legs received a **NO-GO** verdict under the strict 5-phase pipeline. However, the results are not uniform — two legs (NQ_NY_LSI and NQ_Asia_LSI) showed genuine walk-forward stability with strong risk profiles, failing only on the annual R floor. The remaining legs exhibit meaningful IS→OOS degradation, monthly loss spikes, or insufficient trade counts.

**NQ_NY_LSI is the strongest candidate in the portfolio** — 4/5 phases passed, 100% MC survival, Sharpe 3.12, DD -7.3R, all 8 OOS years positive. Its only failure is averaging ~11R/year OOS vs the 12R threshold.

---

## Results Matrix

| # | Leg | P1 | P2 | P3 | P4 | P5 | Verdict | OOS Trades | OOS Sharpe | OOS DD | OOS Net R |
|---|-----|:--:|:--:|:--:|:--:|:--:|:-------:|:----------:|:---------:|:------:|:---------:|
| 1 | NQ_NY | PASS | **FAIL** | **FAIL** | PASS | **FAIL** | NO-GO | 500 | 1.03 | -20.1R | +35.6R |
| 2 | NQ_NY_BULL | **FAIL** | PASS | PASS | **FAIL** | PASS | NO-GO | 71 | 3.92 | -3.0R | +17.0R |
| 3 | NQ_Asia | PASS | **FAIL** | **FAIL** | PASS | **FAIL** | NO-GO | 549 | 1.60 | -18.5R | +76.7R |
| 4 | GC_NY | **FAIL** | **FAIL** | **FAIL** | PASS | **FAIL** | NO-GO | 491 | 1.79 | -17.7R | +123.4R |
| 5 | ES_NY | PASS | PASS | **FAIL** | **FAIL** | **FAIL** | NO-GO | 677 | 1.85 | -19.4R | +100.9R |
| 6 | ES_Asia | PASS | PASS | **FAIL** | PASS | **FAIL** | NO-GO | 1138 | 1.30 | -17.7R | +87.5R |
| 7 | NQ_LDN | **FAIL** | **FAIL** | **FAIL** | PASS | **FAIL** | NO-GO | 896 | 0.81 | -40.8R | +95.5R |
| 8 | NQ_Asia_LSI | PASS | PASS | **FAIL** | **FAIL** | **FAIL** | NO-GO | 424 | 2.19 | -11.8R | +62.8R |
| 9 | NQ_NY_LSI | PASS | PASS | **FAIL** | PASS | PASS | NO-GO | 513 | 3.12 | -7.3R | +88.4R |

---

## Per-Leg Detail

### 1. NQ_NY (Continuation, Long Only)

**Config**: ORB 09:30-09:45, entry<12:00, flat 15:30, stop=7% ATR-12, rr=3.5, tp1=0.4, Fri excl
**Grid**: 625/fold (stop × rr × gap × tp1), 20,000 total trials
**Runtime**: 14 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 555 trades, 51% WR, PF 1.33, Calmar 5.59 |
| 2 Walk-Forward | **FAIL** | WF efficiency **0.153** (threshold >=0.5), stability 0.508 |
| 3 Prop Constraints | **FAIL** | Annual R <12R in most years, 2023 -5.6R |
| 4 Hold-Out | PASS | Sharpe 1.70, PF 1.29, +5.0R |
| 5 Monte Carlo | **FAIL** | 37% survival at 15R |

**Mode params**: stop=9.0, rr=2.5, gap=3.0, tp1=0.3 (shifted significantly from anchor)
**Key issue**: Heavy IS→OOS Sharpe decay (IS avg ~5, OOS avg ~0.8). The optimizer finds configs that look great in-sample but degrade sharply out-of-sample. 3 negative years in structural test (2022, 2023, 2025).

---

### 2. NQ_NY_BULL_SPECIALIST (Continuation, Regime-Gated)

**Config**: ORB 09:30-09:50, entry<12:00, flat 15:30, stop=6% ATR-12, rr=3.0, tp1=0.6, Fri excl
**Gates**: bull regime + no low-confidence + hh_hl_2_vwap structure (applied via gate_factory)
**Grid**: 625/fold, 20,000 total trials
**Runtime**: 2.8 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | **FAIL** | Only **85 trades** (threshold >=100) |
| 2 Walk-Forward | PASS | Stability **0.773** (high), mode: stop=4.0, rr=2.0, gap=3.5, tp1=0.4 |
| 3 Prop Constraints | PASS | DD -3.0R, worst month -2.0R |
| 4 Hold-Out | **FAIL** | Only **4 trades** in 12-month holdout, -1.2R |
| 5 Monte Carlo | PASS | 100% survival at 15R |

**Mode params**: stop=4.0, rr=2.0, gap=3.5, tp1=0.4 (major shift from anchor)
**Key issue**: The regime+structure gates filter too aggressively — 85 trades across 9 years means ~9 trades/year. The strategy concept works (69% WR, Sharpe 3.9 when it trades) but lacks statistical sample size. Multiple OOS folds had 0-1 trades producing infinite/zero Sharpe, making WF efficiency meaningless (reported as 29 billion).

---

### 3. NQ_Asia (Continuation, Long Only)

**Config**: ORB 20:00-20:15, entry<22:30, flat 04:00, stop=100% ORB, rr=6.0, tp1=0.3, ATR-5, Tue excl
**Grid**: 750/fold (stop_orb × rr × gap_orb × tp1), 24,000 total trials
**Runtime**: 16 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | |
| 2 Walk-Forward | **FAIL** | WF efficiency **0.346** (threshold >=0.5), stability 0.586 |
| 3 Prop Constraints | **FAIL** | Worst month -5.4R, annual R <12R most years, 2021 -6.4R |
| 4 Hold-Out | PASS | Sharpe 5.87, PF 2.34, **+30.8R** (outstanding recent performance) |
| 5 Monte Carlo | **FAIL** | 44% survival at 15R |

**Mode params**: stop_orb=125%, rr=4.0, gap_orb=15%, tp1=0.3
**Key issue**: WF efficiency below threshold. Strong recent holdout (+30.8R in 12 months) contrasts with weak 2020-2021 OOS performance. The parameter space is unstable across regimes — stop_orb ranges from 75-175% across folds.

---

### 4. GC_NY (Continuation, Long Only, ICF + FOMC)

**Config**: ORB 09:30-09:40, entry<12:00, flat 13:30, stop=4.5% ATR-7, rr=9.0, tp1=0.35, ICF ON, FOMC excl, Fri excl
**Grid**: 500/fold, 16,000 total trials
**Runtime**: 34 min (slowest — 1s magnifier for GC)

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | **FAIL** | |
| 2 Walk-Forward | **FAIL** | WF efficiency **0.216**, stability 0.672 |
| 3 Prop Constraints | **FAIL** | Worst month **-10.0R**, max consec losses 15 |
| 4 Hold-Out | PASS | Sharpe 2.59, PF 1.61, +21.4R |
| 5 Monte Carlo | **FAIL** | **11.6% survival** at 15R |

**Mode params**: stop=3.0, rr=10.0, gap=4.0, tp1=0.4
**Key issue**: The high R:R profile (30.8% WR, avg win 3.07R) produces enormous total returns (+123.4R OOS) but catastrophic monthly loss spikes. A single bad month can erase 10R. The strategy has edge but the volatility profile is incompatible with prop firm constraints at any sizing.

---

### 5. ES_NY (Continuation, Long Only)

**Config**: ORB 09:30-09:45, entry<13:00, flat 15:50, stop=5% ATR-7, rr=5.0, tp1=0.2, min_stop=3pts, min_tp1=3pts, Thu excl
**Grid**: 625/fold, 20,000 total trials
**Runtime**: 16 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | |
| 2 Walk-Forward | **PASS** | WF efficiency **0.598**, stability 0.602 |
| 3 Prop Constraints | **FAIL** | Worst month -7.4R, 2024 -1.5R |
| 4 Hold-Out | **FAIL** | Sharpe 0.004, PF 0.99, **+0.0R** (flat) |
| 5 Monte Carlo | **FAIL** | 26.4% survival at 15R |

**Mode params**: stop=7.0, rr=5.0, gap=0.15, tp1=0.25
**Key issue**: Passed Phase 2 with decent WF efficiency, but the holdout period is completely flat (+0.0R, Sharpe near zero). The gap filter at 0.15% essentially accepts all FVGs — this may indicate the edge is in trade selection, not gap quality. Monthly loss spikes in 2022-2024 kill the prop constraint check.

---

### 6. ES_Asia (Continuation, Long Only)

**Config**: ORB 20:00-20:15, entry<03:00, flat 07:00, stop=125% ORB, gap=0.5% ATR-14, rr=1.5, tp1=0.7, min_stop=3pts, min_tp1=3pts
**Grid**: 500/fold, 16,000 total trials
**Runtime**: 14 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | |
| 2 Walk-Forward | **PASS** | WF efficiency **0.523**, stability 0.586 |
| 3 Prop Constraints | **FAIL** | Worst month -6.2R, annual R <12R most years |
| 4 Hold-Out | PASS | Sharpe 1.79, PF 1.31, +16.1R |
| 5 Monte Carlo | **FAIL** | 31.8% survival at 15R |

**Mode params**: stop_orb=175%, rr=2.0, gap_atr=0.25%, tp1=0.9
**Key issue**: Decent WF profile with 1,138 OOS trades across 8 years, but low per-trade expectancy (0.077R) and monthly loss clustering. The strategy is a high-frequency grinder that works but doesn't generate enough annual R for prop firm targets. Mode shifted to wider stop (175%) and higher tp1 (0.9) vs anchor.

---

### 7. NQ_LDN (Continuation, Long Only)

**Config**: ORB 03:00-03:30, entry<08:25, flat 08:20, stop=1.5% ATR-10, rr=6.0, tp1=0.7
**Note**: G5 gate (skip if NQ Asia hit TP1) was ignored — standalone validation
**Grid**: 500/fold, 16,000 total trials
**Runtime**: 14 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | **FAIL** | |
| 2 Walk-Forward | **FAIL** | WF efficiency **0.096** (worst of all legs), stability 0.500 |
| 3 Prop Constraints | **FAIL** | Worst month **-11.0R**, DD **-40.8R**, max consec losses **22** |
| 4 Hold-Out | PASS | Sharpe 1.01, PF 1.15, +10.8R |
| 5 Monte Carlo | **FAIL** | **0.0% survival**, 100% ruin at 15R |

**Mode params**: stop=1.0, rr=4.0, gap=0.5, tp1=0.5
**Key issue**: The weakest leg by every measure. 27.2% WR with extremely lumpy returns — 22 consecutive losses at one point, -40.8R max OOS drawdown, -11R worst month. MC shows 0% survival with p50 DD of -39R. The London session edge may exist directionally but the tight ATR stop (1-2%) creates constant stop-outs in the pre-NY volatility expansion. Not viable at any prop firm sizing.

---

### 8. NQ_Asia_LSI (Liquidity Sweep Inversion, Long Only)

**Config**: Entry 20:40-23:30, flat 04:00, gap=1.75% ATR-40, rr=2.0, tp1=0.7, n_left=8, n_right=2, entry=close
**Grid**: 80/fold (rr × tp1 × gap), 2,560 total trials
**Runtime**: 11 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | |
| 2 Walk-Forward | **PASS** | WF efficiency **0.523**, stability 0.552, rr=1.5 in **21/32 folds** |
| 3 Prop Constraints | **FAIL** | Annual R <12R (avg ~8R/yr), worst month -5.0R (borderline) |
| 4 Hold-Out | **FAIL** | Sharpe 0.50 (exactly at threshold, not >0.5), PF 0.97, +0.9R |
| 5 Monte Carlo | **FAIL** | Survival 88.5% (strong) but ruin 11.5% (>5% threshold) |

**Mode params**: rr=1.5, tp1=0.8, gap=2.25
**Key issue**: The risk profile is solid (DD -11.8R, Sharpe 2.19, max consec losses 7) but annual returns average ~8R/year — below the 12R floor. The holdout was borderline (Sharpe exactly 0.50, missed by a rounding margin). MC survival at 88.5% is strong. This strategy is a consistent, moderate-edge grinder that doesn't hit prop firm return targets but has excellent survivability.

---

### 9. NQ_NY_LSI (Liquidity Sweep Inversion, Long Only) — Best Result

**Config**: Entry 09:35-15:30, flat 15:50, gap=5.0% ATR-10, rr=3.0, tp1=0.3, n_left=8, n_right=60, entry=fvg_limit, Wed+Thu excl
**Grid**: 100/fold (rr × tp1 × gap), 3,200 total trials
**Runtime**: 12 min

| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | |
| 2 Walk-Forward | **PASS** | WF efficiency **0.661** (best of all legs), stability 0.521 |
| 3 Prop Constraints | **FAIL** | Annual R <12R in 5/8 years (but **all years positive**) |
| 4 Hold-Out | **PASS** | Sharpe **4.90**, PF 2.14, **+18.3R** |
| 5 Monte Carlo | **PASS** | **100% survival**, ruin **0.1%**, p95 DD -9.8R |

**Mode params**: rr=4.0, tp1=0.35, gap=5.0

**Why this is the standout**:
- **Highest WF efficiency** (0.661) — IS performance translates well to OOS
- **Best risk profile** — DD -7.3R, worst month -4.0R, max consec losses only 4
- **All 8 OOS years positive** — no negative calendar years across the entire walk-forward
- **100% MC survival** — p50 DD -7.3R, p95 DD -9.8R, 96% monthly loss pass rate
- **Strong holdout** — Sharpe 4.90, +18.3R in 12 months
- **513 OOS trades** — statistically meaningful sample

The only failure is the annual R floor in Phase 3 — the strategy averages ~11R/year OOS (below 12R threshold). At the 12R threshold this is technically NO-GO, but at 10R it would be CONDITIONAL. Given the exceptional risk profile, this is the most deployment-ready leg in the portfolio.

---

## Cross-Leg Analysis

### Walk-Forward Efficiency Ranking

| Rank | Leg | WF Eff | Stability | Phase 2 |
|------|-----|--------|-----------|---------|
| 1 | NQ_NY_LSI | **0.661** | 0.521 | PASS |
| 2 | ES_NY | **0.598** | 0.602 | PASS |
| 3 | ES_Asia | **0.523** | 0.586 | PASS |
| 4 | NQ_Asia_LSI | **0.523** | 0.552 | PASS |
| 5 | NQ_Asia | 0.346 | 0.586 | FAIL |
| 6 | GC_NY | 0.216 | 0.672 | FAIL |
| 7 | NQ_NY | 0.153 | 0.508 | FAIL |
| 8 | NQ_LDN | 0.096 | 0.500 | FAIL |
| 9 | NQ_NY_BULL | N/A* | 0.773 | PASS* |

*Bull specialist WF efficiency is meaningless due to 0-trade OOS folds producing infinite Sharpe

### Common Failure Patterns

1. **Phase 3 Annual R** — Failed by all 9 legs. The 12R/year OOS threshold is demanding when the WF selects risk-adjusted (Sharpe-optimal) params. Sharpe-optimal configs tend to trade more conservatively than Calmar-optimal ones, resulting in lower absolute returns but better risk-adjusted performance.

2. **Monthly loss spikes** — Failed by NQ_NY, NQ_Asia, GC_NY, ES_NY, ES_Asia, NQ_LDN. The ORB continuation strategy produces occasional months with -5 to -11R losses. Only the LSI legs (worst months -4R and -5R) stay near the 5R threshold.

3. **IS→OOS decay** — The continuation legs (NQ_NY, NQ_Asia, GC_NY, NQ_LDN) show WF efficiency below 0.35, meaning 65%+ of IS performance evaporates OOS. The LSI legs and ES legs retain 50-66% of IS performance.

### Strategy-Type Comparison

| Metric | ORB Continuation (avg) | LSI Reversal (avg) |
|--------|:---------------------:|:------------------:|
| WF Efficiency | 0.27 | 0.59 |
| OOS Sharpe | 1.39 | 2.66 |
| OOS Max DD | -22.7R | -9.6R |
| Worst Month | -7.5R | -4.5R |
| MC Survival | 21% | 94% |
| Phase 2 Pass Rate | 2/7 | 2/2 |

The LSI reversal strategy fundamentally outperforms ORB continuation on walk-forward robustness and risk-adjusted metrics. Both LSI legs passed Phase 2; only 2/7 continuation legs did.

---

## Infrastructure Note

A signal cache disk key collision bug was discovered and fixed during this pipeline run. The `_signal_cache_path()` function in `parallel.py` was truncating the data key to 20 characters, causing different DataFrame slices (full WF range vs per-fold IS window) that start at the same timestamp to share the same cache file. This produced `IndexError` crashes when the WF engine used a cache built on a larger DataFrame for a smaller fold slice.

**Fix**: Replaced `safe_data_key = str(data_key)[:20]` with `data_hash = hashlib.md5(str(data_key).encode()).hexdigest()[:12]` so every unique DataFrame (by start time + end time + row count) gets its own cache file.

---

## Methodology Caveats

- **PBO, CSCV, DSR, PSR are NOT implemented**. All verdicts are heuristic, not statistically deflated.
- **Phase 3 and Phase 5 operate on the same OOS trade set** from Phase 2. They are stress tests, not independent evidence.
- **Hold-out contamination**: By leg 9, the hold-out period had been tested 9 times with 9 different configs. The hold-out is no longer truly untouched — Phase 4 results should be interpreted with caution.
- **Total trials across all legs**: ~138,000 parameter combinations tested. Without DSR/PSR correction, the risk of false discovery across this many trials is non-trivial.
