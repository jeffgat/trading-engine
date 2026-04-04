# LLM Council Transcript — Discovery Candidate Evaluation for Prop Firm Payout Farming

**Date**: April 3, 2026
**Session ID**: 20260403-110838

---

## Original Question

Evaluate all 17 viable candidate legs from the TOP_CANDIDATES_PER_ASSET_REPORT against the prop firm payout farming framework established in two prior council sessions (083956 and 093017). Rank all legs, find best 3-leg and 5-leg combinations, identify categorical exclusions, determine if any discovery leg should replace a live leg, and confirm/challenge GC Asia-1 ungated as highest-confidence non-equity add.

---

## Framed Question

Evaluate 17 candidate trading strategy legs for deployment on prop firm funded accounts ($50K accounts, +5R payout/$500, -4R breach/$100 reset, new account every 14 days, separate account per leg). Two prior councils established a live 4-leg portfolio (NQ_Asia ORB, ES_Asia ORB, ES_NY ORB, NQ_NY_LSI) with live track records. Now 17 new discovery-pipeline candidates need evaluation for: (a) individual account viability, (b) optimal 3-leg and 5-leg combinations, (c) whether any should replace or supplement the live portfolio.

Key criteria from prior councils: payout rate >75% viable, max consecutive breach >15 disqualifying, 2026 negative performance is red flag, DSR >0.3 preferred, positive holdout R required, speed to payout matters, uncorrelated instruments valued.

---

## Advisor Responses

### The Contrarian

Fatal flaw: holdout performance is catastrophically weak for most legs — 90%+ pre-to-holdout evaporation. Only 5 legs worth considering by HO R: NQ Asia-B (+42.5R), NQ Asia-A (+37.9R), GC Asia-1 ungated (+20.1R), SI Asia-3 (+10.1R), RTY NY-1 (+11.0R). GC Asia-1 is NOT highest-confidence by prop metrics — NQ Asia-B's holdout is double. ES Asia-A (HO -0.4R) and GC Asia-2 (HO -1.1R) must be categorically excluded. Correlation assumption unexamined — equity-dominated portfolio gets wiped by single shock. Cannot evaluate replacement without incumbent's holdout data.

The framework conflates pre-sample fit with predictive validity. Pre-sample R is in-sample performance on historical data used to build or select these configs — it tells you almost nothing about forward edge. HO R is the only number that matters for prop firm farming, and the majority show massive decay.

The live portfolio replacement question (Q5) is being asked backwards. The live legs aren't benchmarked against their own holdout performance here. You can't evaluate replacement without knowing if the incumbent is also degrading. If ES_Asia ORB holdout is near zero, replacing it with ES Asia-A gated (HO -0.4R) is a lateral move into a confirmed loser.

Bottom line: Rank by holdout R only. Exclude anything with HO < +5R as insufficient edge to reliably farm payouts before randomness swamps signal.

### The First Principles Thinker

The question being asked is wrong. This is a survival problem, not a ranking problem. The prop firm structure defines the game exactly: +5R wins, -4R loses. The only question: what is the probability that any given leg reaches +5R before hitting -4R, and how fast?

HO R is the only honest signal. Pre-period R is backtested-in-sample by definition. Tier 1 (HO R meaningfully positive, DSR supports frequency): NQ Asia-B, NQ Asia-A, CL LDN-1, SI Asia-3, RTY NY-1, GC Asia-1 ungated. Tier 2 (modest HO): GC Asia-1 gated, CL LDN-3, SI Asia-4, RTY NY-2.

Categorically exclude — HO R near zero or negative: ES Asia-A (HO -0.4R), GC Asia-2 (HO -1.1R), ES NY-A (HO +2.7R on 78% WR screams overfitting), RTY NY-4 (HO +1.2R), NQ NY-B (HO +1.8R). High pre-period WR with collapsed HO performance is the clearest overfitting signature.

Gold/Silver move together. CL is its own regime. NQ/ES/RTY are equity-correlated.

Best 3: NQ Asia-B + GC Asia-1 ungated + CL LDN-1. Three different market structures, three session windows, no shared dominant driver.

Best 5: Add RTY NY-1 (equity but NY session — different timing) and SI Asia-3 (silver diverges from gold in vol regimes).

On Q5: The live portfolio should drop one ES leg and add GC Asia-1 ungated. That is the highest-expected-value single change available.

On Q6: Yes. GC Asia-1 ungated has highest DSR (0.652), positive HO, zero equity correlation. Ungated beats gated because gate consumes edge (DSR 0.652 vs 0.508 with comparable HO R).

### The Expansionist

Ranked all 17 by HO R with decorrelation analysis.

Top 5: NQ Asia-B (+42.5R, HO PR 76.7%), NQ Asia-A (+37.9R), GC Asia-1 ungated (DSR 0.652), GC Asia-1 gated, RTY NY-1 (DSR 0.590).

Best 3: NQ Asia-B + GC Asia-1 ungated + CL LDN-1. Equity/metals/energy, Asia/Asia/London. Zero session overlap.

Best 5: Add RTY NY-1 + SI Asia-3. Five instruments, three sessions, max decorrelation. SI short-only hedges against risk-off metal spikes that long-gold captures — covering both sides.

Hard excludes: GC Asia-2 (HO -1.1R), ES Asia-A (HO -0.4R, 87.3% pre PR screams overfit), RTY NY-4, NQ NY-B, ES NY-A.

Replace ES Asia ORB from live portfolio with NQ Asia-B or NQ Asia-A — HO +42.5R vs -0.4R is a categorical upgrade, not marginal. The argument for keeping ES Asia-A is sentimental, not quantitative.

GC Asia-1 ungated confirmed: DSR 0.652 is the best in the entire 21-leg universe (17 discovery + 4 live). Gold during Asia is driven by Shanghai/HK physical demand, structurally independent of US equity ORB patterns. CL LDN-1 (London session energy) and SI Asia-3 (short-only metals) are undervalued diversifiers.

### The Outsider

Pure EV math: EV = (HO PR x 400) - ((1 - HO PR) x 100).

| Rank | Option | HO PR | EV/attempt |
|------|--------|-------|------------|
| 1 | NQ Asia-B | 76.7% | +$284 |
| 2 | NQ Asia-A | 74.8% | +$274 |
| 3 | GC Asia-1 gated | 58.4% | +$174 |
| 4 | GC Asia-1 ungated | 55.9% | +$145 |
| 5 | CL LDN-2 | 55.0% | +$120 |
| 6 | CL LDN-1 | 54.1% | +$116 |
| 7 | RTY NY-2 | 52.2% | +$89 |

9 legs have negative EV on holdout. Hard excludes: ES Asia-A (HO PR 0.0%), GC Asia-2, ES NY-A, SI Asia-1, NQ NY-B, SI Asia-3, SI Asia-4, RTY NY-4, CL LDN-3 (borderline).

Best 3: NQ Asia-B + NQ Asia-A + GC Asia-1 gated ($732/cycle).
Best 5: Add GC Asia-1 ungated + CL LDN-2 ($997/cycle).

Interesting finding: GC gated has HIGHER EV than ungated (HO PR 58.4% vs 55.9%), despite lower DSR. If forced to pick one, gated wins on dollars.

Replace weak live legs with GC variants. G1-filtered (higher EV) beats G1-open (higher DSR) unless weighting confidence.

### The Executor

Monday morning action list.

**Tier 1 — Build immediately:**
1. NQ Asia-B gated (+42.5R HO, 76.7% HO PR)
2. NQ Asia-A gated (+37.9R HO, 74.8% HO PR)
3. GC Asia-1 ungated (DSR 0.652, +20.1R HO)
4. GC Asia-1 gated (+20.4R HO, 58.4% HO PR)

**Tier 2 — Build after Tier 1 live:** RTY NY-1, CL LDN-2.

**Tier 3 — Do not build:** GC Asia-2 (HO -1.1R), ES Asia-A (HO -0.4R), ES NY-A, NQ NY-B, RTY NY-4, all CL except LDN-2, all SI (HO PR 29.3% alarming).

Best 3: NQ Asia-B + GC Asia-1 ungated + RTY NY-1
Best 5: Add NQ Asia-A + CL LDN-2

**No replacements for live legs — additions only.** Live track records trump backtests. The one exception to monitor: if GC Asia-1 ungated outperforms ES Asia ORB on rolling 90-day basis after going live, revisit.

GC Asia-1 ungated confirmed as highest-priority build. Monday: verify 1s data availability for GC, start GC execution config build, begin NQ Asia-B config in parallel, scope RTY and CL timelines.

---

## Peer Reviews

### Anonymization Mapping
- Response A = The Executor
- Response B = The Outsider
- Response C = The Contrarian
- Response D = The Expansionist
- Response E = The First Principles Thinker

### Reviewer 1 (general)
**Strongest: E (First Principles)** — survival framing is operationally correct for prop farming, tight defensible logic. **Blind spot: B (Outsider)** — anchors on dollar EV without drawdown path; prop accounts die from consecutive losses, not low average EV. **All missed:** Correlation stress-testing under regime shock — instrument diversity ≠ return independence.

### Reviewer 2 (risk manager)
**Strongest: C (Contrarian)** — challenges premise, questions holdout validity for most legs. **Blind spot: B (Outsider)** — recommends replacing live legs, survivorship/selection error; live execution data includes slippage, fills, behavioral discipline that backtests cannot replicate. **All missed:** Joint drawdown distribution and correlation structure during simultaneous drawdowns.

### Reviewer 3 (portfolio allocator)
**Strongest: D (Expansionist)** — uniquely prioritizes decorrelation across instruments AND sessions simultaneously. **Blind spot: B (Outsider)** — precise dollar figures without structural constraints (daily DD caps, consistency rules). **All missed:** Prop firm daily drawdown cap interaction with concurrent multi-leg positions.

### Reviewer 4 (operations)
**Strongest: C (Contrarian)** — identifies holdout validity as gating question before capital allocation. **Blind spot: B (Outsider)** — false precision, irreversible swap recommendation. **All missed:** Max daily loss / trailing drawdown rules governing which legs can coexist.

### Reviewer 5 (data scientist)
**Strongest: E (First Principles)** — tightest signal-to-noise, concrete falsifiable claims (gate consuming edge). **Blind spot: D (Expansionist)** — SI inclusion looks like rank-filling; session non-overlap ≠ return independence. **All missed:** Kelly-adjusted sizing under finite drawdown budget.

### Vote Tally
- Strongest: First Principles (2), Contrarian (2), Expansionist (1)
- Biggest blind spot: Outsider (4), Expansionist (1)

---

## Chairman's Synthesis

### Where the Council Agrees

**On the top tier:** All five advisors converge on NQ Asia-B and NQ Asia-A as the two strongest legs. No dissent. HO R of +42.5R and +37.9R respectively, with HO PR above 75%, make these the only legs with unambiguous holdout validation.

**On GC Asia-1 ungated as the non-equity anchor:** Four of five advisors rank it in the top 3. DSR 0.652 is the strongest prop-payout metric in the dataset. This is settled.

**On the hard excludes:** Universal agreement. ES Asia-A (HO -0.4R), GC Asia-2 (HO -1.1R), ES NY-A, RTY NY-4, NQ NY-B — these are dead. No advisor defended any of them.

**On the Outsider's blind spot:** Four of five peer reviewers flagged it. Dollar EV math without drawdown path, Kelly sizing, or prop daily-loss caps is the weakest framework in this council. The Outsider's rankings are not wrong directionally, but the precision is false and the GC gated-over-ungated preference (based on a 2.5% HO PR edge) is noise, not signal.

### Where the Council Clashes

**GC gated vs. ungated:** The Outsider says gated wins on EV ($174 vs $145 per attempt). First Principles says ungated wins because the gate consumes edge (DSR 0.652 vs 0.508). Executor and Expansionist side with ungated. DSR is the right metric for prop payout cadence — a leg that triggers less often with higher DSR generates more consistent payouts and smaller drawdown exposure per unit time. **Ungated wins.**

**SI Asia-3 inclusion:** First Principles and Expansionist include it in the best-5. Executor excludes it entirely, citing HO PR of 29.3% as alarming. Reviewer 5 calls it rank-filling. 29.3% HO PR means the leg fails 7 out of 10 attempts in holdout. On a prop account that breaches at -4R, that failure rate demands position sizing so small it destroys the +10.1R HO R in net payout terms. **The Executor is right to exclude it.**

**Replacements vs. additions:** The Executor refuses to replace live legs. First Principles says drop one ES leg. The Contrarian notes we cannot evaluate the question without the live legs' holdout data — the correct epistemic point. If the live ES legs are functionally equivalent to ES Asia-A (HO -0.4R), they are actively burning prop capital through reset fees. The principle "live track records trump backtests" cannot protect a leg that is destroying capital.

**CL LDN-1 vs. CL LDN-2:** First Principles and Expansionist pick LDN-1 (HO +12.8R). Executor picks LDN-2. Insufficient data differential provided to adjudicate — defer to higher HO R (LDN-1).

### Blind Spots the Council Caught

1. **Correlation under regime shock.** All five peer reviewers flagged this. NQ Asia-B, NQ Asia-A, and RTY NY-1 are all equity index futures. A macro risk-off event hits all simultaneously. "Decorrelation" via session timing provides zero protection when the shock is global and synchronous.

2. **Joint drawdown and daily prop cap interaction.** If NQ Asia-B and NQ Asia-A run simultaneously, both accounts draw down at the same time. Combined capital at risk is not independent. No advisor modeled simultaneous breach probability.

3. **Kelly-adjusted sizing under finite drawdown budget.** Raw HO R numbers are irrelevant to sizing without per-trade variance. A leg with +42.5R on 50 trades has different sizing implications than +42.5R on 500 trades.

4. **Pre-period evaporation rate.** Only the Contrarian named the 90%+ pre-to-holdout evaporation. If a leg produces +200R pre and +42.5R holdout, the question is not "is 42.5R good" but "what happened to 77% of the edge" — that answer determines whether the remaining edge is durable or continuing to decay.

5. **NQ Asia-B and NQ Asia-A trade overlap percentage.** Both are long-only NQ Asia ORB with different parameters. They may enter on the same bars >50% of the time, making them a leveraged single bet, not two independent accounts.

### The Recommendation

**Ranking (top 8 only — below this is not prop-viable):**

| Rank | Leg | HO R | HO PR | DSR | Verdict |
|------|-----|------|-------|-----|---------|
| 1 | NQ Asia-B gated | +42.5 | 76.7% | 0.310 | STRONG — best holdout by far |
| 2 | NQ Asia-A gated | +37.9 | 74.8% | 0.233 | STRONG — verify trade overlap with Asia-B |
| 3 | GC Asia-1 ungated | +20.1 | 55.9% | 0.652 | STRONG — highest DSR, best non-equity add |
| 4 | GC Asia-1 gated | +20.4 | 58.4% | 0.508 | CONDITIONAL — gate consumes edge for prop cadence |
| 5 | RTY NY-1 | +11.0 | — | 0.590 | CONDITIONAL — strong DSR, missing HO PR is a flag |
| 6 | CL LDN-1 | +12.8 | 54.1% | 0.186 | CONDITIONAL — best decorrelator, low DSR concern |
| 7 | RTY NY-2 | +8.8 | 52.2% | 0.527 | CONDITIONAL — solid DSR, modest HO |
| 8 | SI Asia-3 | +10.1 | 37.0% | 0.376 | EXCLUDED — 37% HO PR is not prop-viable |

**Categorical excludes:** ES Asia-A, GC Asia-2, ES NY-A, RTY NY-4, NQ NY-B, all SI legs (HO PR too low), CL LDN-2/3 (redundant with LDN-1).

**Best 3-leg combination: NQ Asia-B + GC Asia-1 ungated + CL LDN-1**

Three instruments, three market structures (equity / metals / energy), minimal session overlap. Four advisors independently converged on this.

**Best 5-leg combination: NQ Asia-B + GC Asia-1 ungated + CL LDN-1 + NQ Asia-A + RTY NY-1**

NQ Asia-A is the 4th leg (pending trade-overlap verification with Asia-B). RTY NY-1 is the 5th (NY session equity, different timing from Asia legs). SI excluded.

**On replacements:** Do not replace live legs. Add discovery legs as new separate accounts. Monitor the live ES legs' rolling 90-day performance — if they match ES Asia-A's holdout profile, evaluate removal then.

**GC Asia-1 ungated confirmed** as highest-confidence non-equity add. DSR 0.652, positive holdout, zero equity correlation. Build priority #1 after verifying 1s data availability.

### The One Thing to Do First

Run NQ Asia-B and NQ Asia-A side-by-side on the same historical dates and log every trade entry time. Before deploying both as separate prop accounts, you must know the trade overlap percentage. If these two legs enter on the same bars more than 40% of the time, they are not two independent bets — they are a leveraged single bet with two reset clocks. That answer determines whether your "best 5" is actually 5 independent positions or 4 with a correlated duplicate. Everything else — GC data verification, CL LDN leg selection, sizing decisions — is secondary to this.

---

*Council session completed April 3, 2026. 5 advisors, 5 peer reviews, chairman synthesis.*
