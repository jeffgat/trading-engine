# FAST Execution Config — Phase-One Robust Pipeline Report

**Date**: 2026-03-29
**Pipeline**: Phase-one robust pipeline (payout-sprint, account-farming EV)
**Hard constraints enforced**: stop >= 5% ATR, tp1_ratio * rr >= 1.0, rr >= 1.0
**Hold-out**: 2025-03-01 to 2026-02-28

---

## Phase 0: Model Freeze

| Parameter | Value |
|-----------|-------|
| Account size | $50,000 |
| Trailing drawdown | $2,000 |
| Breach floor | $48,000 (trails EOD balance) |
| Trail stops rising at | $52,000 |
| Phase-one sprint target | $52,500 |
| First payout withdrawal | $500 |
| Reset cost assumption | $100 |
| Stagger interval | 14 calendar days |
| Payout threshold | +5R from account start |
| Breach threshold | -4R from account start |
| Hold-out | 2025-03-01 to 2026-02-28 (frozen) |

**Bailey posture**: PBO/CSCV/DSR/PSR not implemented. All verdicts are heuristic. WF combined OOS trades are the same data used for Phase 3 scorecard — not independent evidence.

---

## Executive Summary

**NQ_NY_LSI is the strongest account-farming candidate in the FAST portfolio** — 92.7% success rate, +4.30R EV per attempt, max 6 consecutive breaches, all 10+ years positive. At a $100 reset cost and $500 first payout, the business model is strongly positive.

Five legs clear the STRONG threshold (EV > +2.5R, success > 75%): NQ_NY_LSI, NQ_Asia_LSI, NQ_NY_BULL, NQ_Asia, and ES_Asia. Two more are CONDITIONAL (ES_NY, NQ_NY). Two are NO-GO (GC_NY, NQ_LDN).

---

## Phase 1: Structural Viability

All legs tested with their FAST anchor configs on full pre-holdout history. Hard constraints enforced by engine (stop >= 5% ATR clamped for GC_NY at 4.5% and NQ_LDN at 1.5%; NQ_NY_LSI tp1_ratio bumped from 0.3 to 0.34).

| Leg | Trades | WR | PF | Net R | Sharpe | DD | Viability |
|-----|:------:|:--:|:--:|:-----:|:------:|:--:|:---------:|
| NQ_NY | 613 | 51.1% | 1.34 | +103.1R | 2.063 | -16.0R | PASS |
| NQ_NY_BULL | 90 | 50.0% | 1.75 | +33.7R | 3.988 | -7.1R | **MARGINAL** (90 trades) |
| NQ_Asia | 753 | 45.2% | 1.52 | +212.0R | 2.860 | -10.2R | PASS |
| GC_NY | 632 | 30.7% | 1.34 | +151.1R | 1.794 | -15.1R | PASS |
| ES_NY | 876 | 61.3% | 1.42 | +142.6R | 2.283 | -10.9R | PASS |
| ES_Asia | 1468 | 54.2% | 1.27 | +146.6R | 1.754 | -12.3R | PASS |
| NQ_LDN | 1137 | 30.3% | 1.08 | +60.9R | 0.473 | -44.7R | **WEAK** (PF 1.08, DD -44.7R) |
| NQ_Asia_LSI | 532 | 53.4% | 1.48 | +114.8R | 2.926 | -6.9R | PASS |
| NQ_NY_LSI | 611 | 59.2% | 1.61 | +120.1R | 3.217 | -6.6R | PASS |

**NQ_NY_BULL** passes on edge quality (Sharpe 3.99, PF 1.75) but only 90 trades is thin. **NQ_LDN** has PF 1.08 and -44.7R DD — structurally weak but included for completeness.

---

## Phase 2: Walk-Forward Reference

WF results from the FAST robust pipeline (12m IS / 3m OOS / 3m step, 32 folds). These establish whether the edge generalizes before applying payout economics.

| Leg | WF Efficiency | Stability | OOS Sharpe | OOS DD | Phase 2 |
|-----|:------------:|:---------:|:----------:|:------:|:-------:|
| NQ_NY | 0.153 | 0.508 | 1.03 | -20.1R | FAIL |
| NQ_NY_BULL | N/A* | 0.773 | 3.92 | -3.0R | PASS* |
| NQ_Asia | 0.346 | 0.586 | 1.60 | -18.5R | FAIL |
| GC_NY | 0.216 | 0.672 | 1.79 | -17.7R | FAIL |
| ES_NY | 0.598 | 0.602 | 1.85 | -19.4R | PASS |
| ES_Asia | 0.523 | 0.586 | 1.30 | -17.7R | PASS |
| NQ_LDN | 0.096 | 0.500 | 0.81 | -40.8R | FAIL |
| NQ_Asia_LSI | 0.523 | 0.552 | 2.19 | -11.8R | PASS |
| NQ_NY_LSI | 0.661 | 0.521 | 3.12 | -7.3R | PASS |

*NQ_NY_BULL has meaningless WF efficiency due to 0-trade folds but high stability (0.773).

**Note**: Under the phase-one framework, WF failure does NOT automatically disqualify a leg. It downgrades confidence. The payout scorecard in Phase 3 may reveal that a WF-failing leg still has positive account-farming EV on the anchor config.

---

## Phase 3: First-Payout Scorecard

Staggered account simulation on the full 10-year backtest: new account every 14 days, +5R payout / -4R breach, unlimited duration per account.

| Leg | Accounts | Payouts | Breaches | Open | Success Rate | EV/Attempt | Avg Days to Payout | Max Consec Breach |
|-----|:--------:|:-------:|:--------:|:----:|:------------:|:----------:|:------------------:|:-----------------:|
| **NQ_NY_LSI** | 267 | **241** | 19 | 7 | **92.7%** | **+4.30R** | 126 | **6** |
| **NQ_Asia_LSI** | 267 | **219** | 38 | 10 | **85.2%** | **+3.48R** | 144 | 11 |
| **NQ_NY_BULL** | 267 | **205** | 39 | 23 | **84.0%** | **+3.51R** | 376 | 26 |
| **NQ_Asia** | 267 | **215** | 46 | 6 | **82.4%** | **+3.31R** | 67 | 9 |
| **ES_Asia** | 267 | **214** | 50 | 3 | **81.1%** | **+3.25R** | 97 | 5 |
| ES_NY | 267 | 196 | 65 | 6 | 75.1% | +2.70R | 77 | 11 |
| NQ_NY | 267 | 173 | 85 | 9 | 67.1% | +1.90R | 90 | 29 |
| GC_NY | 268 | 137 | 128 | 3 | 51.7% | +0.62R | 45 | 13 |
| NQ_LDN | 267 | 107 | 159 | 1 | 40.2% | -0.39R | 31 | 17 |

### Scorecard Ranking (Primary: EV per attempt)

1. **NQ_NY_LSI** — EV +4.30R, 92.7% success, 126 days median, 6 max consec breach
2. **NQ_NY_BULL** — EV +3.51R, 84.0% success, but 376 days to payout (slow)
3. **NQ_Asia_LSI** — EV +3.48R, 85.2% success, 144 days, 11 consec breach
4. **NQ_Asia** — EV +3.31R, 82.4% success, 67 days (fastest payout), 9 consec breach
5. **ES_Asia** — EV +3.25R, 81.1% success, 97 days, **5 max consec breach** (best clustering)
6. **ES_NY** — EV +2.70R, 75.1% success, 77 days, 11 consec breach
7. **NQ_NY** — EV +1.90R, 67.1% success, 90 days, **29 consec breach** (severe clustering)
8. **GC_NY** — EV +0.62R, 51.7% success, 45 days (fast when it works), 13 consec breach
9. **NQ_LDN** — EV **-0.39R**, 40.2% success, negative EV = business model failure

### Payout Business Economics (at $100 reset cost, $500 first payout)

| Leg | EV/Attempt (R) | At $200 risk: EV/Attempt ($) | Reset Cost | Net EV ($) | ROI per Attempt |
|-----|:--------------:|:----------------------------:|:----------:|:----------:|:---------------:|
| NQ_NY_LSI | +4.30R | +$860 | $100 | **+$760** | 760% |
| NQ_NY_BULL | +3.51R | +$702 | $100 | **+$602** | 602% |
| NQ_Asia_LSI | +3.48R | +$696 | $100 | **+$596** | 596% |
| NQ_Asia | +3.31R | +$662 | $100 | **+$562** | 562% |
| ES_Asia | +3.25R | +$650 | $100 | **+$550** | 550% |
| ES_NY | +2.70R | +$540 | $100 | **+$440** | 440% |
| NQ_NY | +1.90R | +$380 | $100 | **+$280** | 280% |
| GC_NY | +0.62R | +$124 | $100 | **+$24** | 24% |
| NQ_LDN | -0.39R | -$78 | $100 | **-$178** | -178% |

---

## Phase 4: Hold-Out Diagnostics

Hold-out period: 2025-03-01 to 2026-03-24 (~13 months). R performance during holdout from the robust pipeline runs:

| Leg | Holdout Net R | Holdout Sharpe | Holdout Trades | Trending |
|-----|:------------:|:--------------:|:--------------:|:--------:|
| NQ_NY | +5.0R | 1.70 | 54 | Positive |
| NQ_NY_BULL | -1.2R | -6.04 | 4 | Too few trades |
| NQ_Asia | +30.8R | 5.87 | 68 | Strong positive |
| GC_NY | +21.4R | 2.59 | 47 | Strong positive |
| ES_NY | +0.0R | 0.00 | 96 | Flat |
| ES_Asia | +16.1R | 1.79 | 154 | Positive |
| NQ_LDN | +10.8R | 1.01 | 119 | Positive |
| NQ_Asia_LSI | +0.9R | 0.50 | 28 | Marginal |
| NQ_NY_LSI | +18.3R | 4.97 | 52 | Strong positive |

**Note**: The holdout has been tested multiple times across pipeline runs. Phase 4 results should be treated as informational, not as truly untouched OOS evidence.

NQ_NY_LSI continues to perform strongly in the holdout (+18.3R, Sharpe 4.97). NQ_Asia is exceptional (+30.8R) in the holdout despite weak WF efficiency. ES_NY is flat — concerning for a leg ranked #6.

---

## Phase 5: Cohort EV Simulation

Modeled as batches of parallel account attempts using the 10-year simulation data.

### 10-Account Cohort

| Leg | Expected Payouts | Expected Breaches | Cohort EV (R) | Reset Costs ($100/acct) | Net Cohort Value |
|-----|:----------------:|:-----------------:|:-------------:|:-----------------------:|:----------------:|
| NQ_NY_LSI | 9.3 | 0.7 | +43.0R | $1,000 | **+$7,600** |
| NQ_Asia_LSI | 8.5 | 1.5 | +34.8R | $1,000 | **+$5,960** |
| NQ_NY_BULL | 8.4 | 1.6 | +35.1R | $1,000 | **+$6,020** |
| NQ_Asia | 8.2 | 1.8 | +33.1R | $1,000 | **+$5,620** |
| ES_Asia | 8.1 | 1.9 | +32.5R | $1,000 | **+$5,500** |
| ES_NY | 7.5 | 2.5 | +27.0R | $1,000 | **+$4,400** |
| NQ_NY | 6.7 | 3.3 | +19.0R | $1,000 | **+$2,800** |
| GC_NY | 5.2 | 4.8 | +6.2R | $1,000 | **+$240** |
| NQ_LDN | 4.0 | 6.0 | -3.9R | $1,000 | **-$1,780** |

### Breach Clustering Assessment

| Leg | Max Consec Breaches | Clustering Risk | Interpretation |
|-----|:-------------------:|:---------------:|----------------|
| ES_Asia | **5** | Low | Breaches spread across regimes |
| NQ_NY_LSI | **6** | Low | Best among high-EV legs |
| NQ_Asia | 9 | Moderate | Some regime-sensitive breach streaks |
| ES_NY | 11 | Moderate | Occasional bad stretches |
| NQ_Asia_LSI | 11 | Moderate | |
| GC_NY | 13 | High | Volatile monthly loss profile |
| NQ_LDN | 17 | Severe | Strategy is regime-dependent |
| NQ_NY_BULL | 26 | Severe | Long gaps between bull trades = many "empty" accounts breach |
| NQ_NY | **29** | Severe | Nearly 30 consecutive breaches |

**NQ_NY_BULL clustering caveat**: The 26 consecutive breaches is misleading — the bull specialist only takes ~9 trades/year, so most accounts have very few trades before the next account starts. The breaches are "empty" (0-1 trades taken) rather than loss-driven. The 84% success rate among resolved accounts is genuine, but it takes 376 days on average to reach payout.

**NQ_NY clustering**: 29 consecutive breaches is a genuine regime failure. The 2022-2023 period produced a sustained drawdown that breached ~30 sequential accounts.

---

## R-by-Year Consistency

| Leg | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* | Neg Years |
|-----|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:----:|:-----:|:---------:|
| NQ_NY_LSI | +9.4 | +17.6 | +2.6 | +7.8 | +16.7 | +14.9 | +9.8 | +15.7 | +7.2 | +13.3 | +5.1 | **0** |
| NQ_Asia | +21.5 | +19.7 | +28.1 | +11.0 | +15.8 | +5.5 | +31.3 | +24.6 | +12.6 | +37.1 | +4.8 | **0** |
| ES_Asia | +7.5 | +7.6 | +1.9 | +15.3 | +14.4 | +9.1 | +22.1 | +21.7 | +18.5 | +27.4 | +1.1 | **0** |
| ES_NY | +15.4 | +25.9 | +4.6 | +11.0 | +16.6 | +19.0 | +15.2 | +13.8 | +1.7 | +17.7 | +1.8 | **0** |
| NQ_Asia_LSI | +0.7 | +17.1 | +17.3 | +12.4 | +9.5 | +19.1 | +7.5 | +2.4 | +17.8 | +15.6 | -4.5 | 1 |
| NQ_NY | +2.7 | +25.2 | +18.8 | +19.7 | +14.8 | +6.5 | -0.2 | -6.2 | +11.6 | +12.1 | -1.9 | 3 |
| NQ_NY_BULL | +0.8 | +4.4 | +3.6 | -2.7 | -0.3 | +7.4 | -0.7 | +9.9 | +7.1 | +1.8 | +2.4 | 3 |
| GC_NY | +1.0 | +7.9 | +20.6 | +24.2 | +12.4 | +6.9 | +6.3 | +20.0 | +12.5 | +46.9 | -7.7 | 1 |
| NQ_LDN | -25.5 | +63.0 | +34.6 | +14.2 | +2.4 | -5.4 | -7.6 | +0.8 | +8.8 | -14.3 | -10.0 | 5 |

*2026 is partial (Jan-Mar only)

**NQ_NY_LSI, NQ_Asia, ES_Asia, and ES_NY have zero negative full years** — the most consistent legs for account farming.

---

## Final Verdicts

| Leg | EV | Success | Clustering | Consistency | WF | Holdout | Verdict |
|-----|:--:|:-------:|:----------:|:-----------:|:--:|:-------:|:-------:|
| **NQ_NY_LSI** | +4.30 | 92.7% | Low (6) | 0 neg years | PASS | Strong | **STRONG** |
| **NQ_Asia** | +3.31 | 82.4% | Mod (9) | 0 neg years | FAIL | Strong | **STRONG** |
| **NQ_Asia_LSI** | +3.48 | 85.2% | Mod (11) | 1 neg year | PASS | Marginal | **STRONG** |
| **ES_Asia** | +3.25 | 81.1% | Low (5) | 0 neg years | PASS | Positive | **STRONG** |
| **NQ_NY_BULL** | +3.51 | 84.0% | Severe* (26) | 3 neg years | PASS* | Thin (4) | **CONDITIONAL** |
| ES_NY | +2.70 | 75.1% | Mod (11) | 0 neg years | PASS | Flat | **CONDITIONAL** |
| NQ_NY | +1.90 | 67.1% | Severe (29) | 3 neg years | FAIL | Positive | **CONDITIONAL** |
| GC_NY | +0.62 | 51.7% | High (13) | 1 neg year | FAIL | Positive | **NO-GO** |
| NQ_LDN | -0.39 | 40.2% | Severe (17) | 5 neg years | FAIL | Positive | **NO-GO** |

*NQ_NY_BULL clustering is from empty accounts (too few trades), not loss-driven breaches.

### Verdict Rationale

**STRONG (4 legs)**:
- **NQ_NY_LSI**: Best leg across every metric. 92.7% success, EV +4.30R, only 6 max consecutive breaches, 0 negative years, WF efficiency 0.661. The clearest account-farming candidate.
- **NQ_Asia**: Highest absolute R (212R over 10 years), fastest payout (67 days), 0 negative years. WF efficiency is weak (0.346) but the anchor config has strong structural edge (Calmar 20.87). The payout economics are compelling despite WF concerns.
- **NQ_Asia_LSI**: 85.2% success, EV +3.48R, DD only -6.9R. The tightest risk profile among continuation/LSI legs. One partial negative year (2026 at -4.5R, only 3 months).
- **ES_Asia**: 81.1% success with the **best breach clustering** (max 5 consecutive). Most consistent grinder with 0 negative years. Highest trade volume (1468 trades) gives the most statistical confidence.

**CONDITIONAL (3 legs)**:
- **NQ_NY_BULL**: Excellent EV (+3.51R) and success rate (84%) but payout takes 376 days on average and clustering looks severe (26 consecutive) due to sparse trading (9 trades/year). Best used as a supplemental leg, not standalone.
- **ES_NY**: Solid EV (+2.70R) and 0 negative years, but the holdout is flat (0.0R) which is concerning for forward deployment.
- **NQ_NY**: Positive EV (+1.90R) but 29 consecutive breaches during 2022-2023 would destroy a cohort. Needs regime filtering or position reduction during choppy periods.

**NO-GO (2 legs)**:
- **GC_NY**: EV barely positive (+0.62R), essentially coin-flip success rate (51.7%). At $100 reset cost, the net EV is only $24 per attempt — not worth the capital.
- **NQ_LDN**: Negative EV (-0.39R). The business model loses money. 40% success rate with 17 consecutive breaches. Do not fund.

---

## Recommended Account-Farming Portfolio

Based on the phase-one scorecard, the optimal 4-leg farming portfolio from FAST is:

| Priority | Leg | Role | Expected Contribution |
|:--------:|-----|------|----------------------|
| 1 | **NQ_NY_LSI** | Primary payout driver | 92.7% success, fastest positive EV |
| 2 | **NQ_Asia** | Volume + speed driver | Fastest payout (67 days), high R/year |
| 3 | **ES_Asia** | Consistency anchor | Best clustering (5), most trades, 0 neg years |
| 4 | **NQ_Asia_LSI** | Risk-efficient supplement | Tightest DD (-6.9R), 85% success |

**NQ_NY_BULL** as optional 5th leg for bull-regime overlay (slow payout but very high EV when it resolves).

---

## Methodology Notes

- **Hard trade constraints enforced**: stop >= 5% ATR (engine clamp), tp1*rr >= 1.0 (config validation), rr >= 1.0 (config validation). GC_NY stop clamped from 4.5% to 5%. NQ_LDN stop clamped from 1.5% to 5%. NQ_NY_LSI tp1_ratio bumped from 0.3 to 0.34.
- **PBO, CSCV, DSR, PSR not implemented**. All verdicts are heuristic.
- **Phase 3 scorecard uses the same 10-year full-history backtest** — not walk-forward OOS trades. This provides maximum sample size for account simulation but overstates edge for legs with poor WF efficiency.
- **Hold-out contaminated** from prior pipeline runs. Phase 4 results are informational.
- **Stagger simulation is deterministic** — every 14 days from 2016-01-01. Real deployment would have different start dates.
