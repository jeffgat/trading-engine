# FAST_V2 Execution Config — Phase-One Robust Pipeline Report

**Date**: 2026-03-29
**Pipeline**: Phase-one robust pipeline (payout-sprint, account-farming EV)
**Hard constraints enforced**: stop >= 5% ATR, tp1_ratio * rr >= 1.0, rr >= 1.0
**Hold-out**: 2025-03-01 to 2026-02-28

**Note**: FAST_V2 is the only live portfolio (has TradersPost webhook). Three legs had tp1_ratio bumped to meet the new tp1*rr >= 1.0 constraint: NQ_NY (0.3→0.4), ES_Asia (0.3→0.58), NQ_NY_LSI (0.2→0.4).

---

## Phase 0: Model Freeze

| Parameter | Value |
|-----------|-------|
| Payout threshold | +5R |
| Breach threshold | -4R |
| Stagger interval | 14 calendar days |
| Data range | 2016-01-01 to 2026-03-24 |
| Reset cost assumption | $100 |

---

## Executive Summary

The tp1_ratio constraint significantly degraded two legs (NQ_NY and ES_Asia) that previously relied on close-to-entry TP1 scalping. **NQ_Asia_LSI emerged as the top leg** with 97.1% success rate and +4.19R EV — the highest success rate across all three portfolios. NQ_NY_LSI remains strong at 85.9% success.

However, the constrained FAST_V2 portfolio is weaker overall than FAST because the "both directions" ORB legs (NQ_NY, ES_Asia) lose their edge when forced to wider TP1 distances.

---

## Results

| Leg | Trades | WR | PF | Net R | Sharpe | DD | P/B/O | Success | EV | Max CB | Avg Days |
|-----|:------:|:--:|:--:|:-----:|:------:|:--:|:-----:|:-------:|:--:|:------:|:--------:|
| **NQ_Asia_LSI** | 234 | 61.1% | 1.64 | +48.1R | 3.53 | -5.9R | 237/7/23 | **97.1%** | **+4.19R** | **7** | 365 |
| **NQ_NY_LSI** | 519 | 59.5% | 1.43 | +81.6R | 2.56 | -9.3R | 226/37/4 | **85.9%** | **+3.71R** | 16 | 156 |
| NQ_Asia | 1205 | 48.1% | 1.19 | +117.8R | 1.25 | -17.9R | 170/91/6 | 65.1% | +1.80R | 13 | 62 |
| NQ_NY | 1337 | 56.8% | 1.06 | +31.3R | 0.38 | -43.5R | 141/121/5 | 53.8% | +0.84R | 25 | 83 |
| ES_Asia | 2207 | 53.9% | 1.03 | +28.2R | 0.20 | -47.2R | 124/142/1 | 46.6% | +0.18R | 15 | 44 |

### What the TP1 Constraint Did

| Leg | Old tp1 | New tp1 | Old tp1*rr | New tp1*rr | Impact |
|-----|:-------:|:-------:|:----------:|:----------:|--------|
| NQ_NY | 0.3 | **0.4** | 0.75 | 1.00 | DD went from -16R to **-43.5R**, success dropped from ~68% to 53.8% |
| ES_Asia | 0.3 | **0.58** | 0.525 | 1.015 | DD went from -12R to **-47.2R**, success dropped from ~81% to 46.6% |
| NQ_NY_LSI | 0.2 | **0.4** | 0.50 | 1.00 | Modest impact — success ~86%, DD -9.3R (was -7.9R) |

NQ_NY and ES_Asia were heavily dependent on close-to-entry TP1 scalping (high WR, tiny wins). Forcing TP1 to at least 1R away destroyed their win rates and DD profiles. NQ_NY_LSI adapted better because its edge comes from FVG quality, not scalp frequency.

### R by Year

| Leg | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* | Neg |
|-----|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:-----:|:---:|
| NQ_Asia_LSI | +5.7 | +4.9 | +8.4 | +8.0 | +4.3 | +4.0 | +2.0 | -1.5 | +5.1 | +9.6 | -2.2 | 1 |
| NQ_NY_LSI | +4.1 | +15.4 | +0.5 | +9.5 | +5.9 | +7.6 | -4.0 | +13.8 | +7.4 | +15.3 | +6.1 | 1 |
| NQ_Asia | +8.7 | +6.2 | +3.3 | +0.7 | +13.6 | +25.7 | +18.2 | +12.4 | +2.2 | +26.3 | +0.7 | 0 |
| NQ_NY | -15.5 | +29.3 | +12.0 | -0.7 | -0.2 | +13.3 | -18.1 | -19.4 | +18.3 | +7.0 | +5.4 | 5 |
| ES_Asia | +5.3 | +11.0 | +3.5 | +14.9 | -4.2 | +21.4 | -10.8 | -25.1 | +2.7 | +17.8 | -8.4 | 4 |

*2026 is partial

---

## Verdicts

| Leg | EV | Success | Clustering | Consistency | Verdict |
|-----|:--:|:-------:|:----------:|:-----------:|:-------:|
| **NQ_Asia_LSI** | +4.19 | 97.1% | Low (7) | 1 neg year | **STRONG** |
| **NQ_NY_LSI** | +3.71 | 85.9% | High (16) | 1 neg year | **STRONG** |
| NQ_Asia | +1.80 | 65.1% | Mod (13) | 0 neg years | **CONDITIONAL** |
| NQ_NY | +0.84 | 53.8% | Severe (25) | 5 neg years | **NO-GO** |
| ES_Asia | +0.18 | 46.6% | High (15) | 4 neg years | **NO-GO** |

**NQ_Asia_LSI is the standout** — 97.1% success rate is the highest of any leg across all three portfolios. Only 7 breaches out of 244 resolved accounts. The tradeoff: it's slow (365 avg days to payout, 23 open accounts still pending).

**ES_Asia collapsed** under the tp1 constraint. The unconstrained version (FAST robust pipeline) was the only GO across all portfolios — now it's the worst leg. The constraint forces it from a 91% WR grinder to a 54% WR swing strategy that loses money more than half the time.

---

## FAST_V2 vs FAST Comparison (Phase-One)

| Leg | FAST Success | FAST_V2 Success | FAST EV | FAST_V2 EV | Difference |
|-----|:-----------:|:---------------:|:-------:|:----------:|:----------:|
| NQ_NY | 67.1% | 53.8% | +1.90R | +0.84R | FAST_V2 worse (both-dirs + tp1 bump) |
| NQ_Asia | 82.4% | 65.1% | +3.31R | +1.80R | FAST worse (both-dirs hurts) |
| ES_Asia | 81.1% | 46.6% | +3.25R | +0.18R | FAST_V2 collapsed (tp1 bump) |
| NQ_Asia_LSI | 85.2% | **97.1%** | +3.48R | **+4.19R** | FAST_V2 better (tighter params) |
| NQ_NY_LSI | 92.7% | 85.9% | +4.30R | +3.71R | FAST slightly better (lower gap) |

FAST_V2's LSI legs outperform or match FAST's, but the ORB continuation legs are significantly worse under the new constraints.
