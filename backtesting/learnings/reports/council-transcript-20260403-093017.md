# LLM Council Transcript #2 — Full Research Candidate Re-Evaluation

**Date**: April 3, 2026
**Session ID**: 20260403-093017

---

## Original Question

Re-evaluation of prop firm portfolio with ALL 16 research candidates across NQ, ES, GC, SI, CL, RTY. Key finding from lifecycle simulation: separate accounts per leg = 3-4x more profitable than combined ($1.66M vs $478K). The extraction phase (post-first-payout weekly withdrawals at $200 risk) is where most money is made.

Questions: (1) Best individual legs for separate accounts? (2) Best 3-5 for combined? (3) Should RR2/TP0.5 gated replace FAST NQ_NY_LSI? (4) Include GC/SI/CL/RTY?

---

## Advisor Responses

### The Contrarian
The $1.66M lifecycle projection is a backtest-on-backtest artifact — compounded overfitting. GC NY LSI's 13 trades/year is noise, not signal. SI DSR 0.507 barely above random. The separate accounts comparison is unfair (unequal capital). Need genuinely locked OOS test set first.

### The First Principles Thinker
Tier 1: NQ NY LSI FAST ($1.66M, 1,135d extraction), NQ Asia FAST (fastest payout), GC NY R3 (WFE 0.956). Tier 2: ES Asia, ES NY, GC NY LSI. Combined: NQ NY LSI + ES Asia + GC NY R3. Don't replace FAST with RR2 — run both as separate accounts. Key insight: shallow DD drives extraction duration.

### The Expansionist
Run 6-8 separate accounts. NQ NY LSI gated as flagship, GC NY R3 on its own. GC is mandatory. Combined: gated + GC R3 + ES Asia + NQ Asia Discovery + GC NY LSI. $10M+ ceiling.

### The Outsider
A-improved (RR2 gated) beats A-current on every metric — swap it. GC NY LSI deserves own account. Include GC Asia-1 + SI as insurance. Five combined: A-improved + GC NY LSI + SI + ES NY + NQ Asia.

### The Executor
Monday: swap NQ_NY_LSI to RR2 gated (ship Wed). Swap NQ Asia config. Start separate-account applications. GC build next sprint. Skip SI.

---

## Peer Reviews

### Anonymization: A=Contrarian, B=First Principles, C=Expansionist, D=Outsider, E=Executor

**Reviewer 1 (skeptical academic):** Strongest: A (identifies methodological flaw). Blind spot: B (treats WFE as stable estimate). All missed: OOS trade counts unverified.

**Reviewer 2 (risk manager):** Strongest: B (shallow DD = extraction duration is correct framing). Blind spot: C (6-8 accounts with no sizing analysis). All missed: stress-period correlation.

**Reviewer 3 (portfolio allocator):** Strongest: B (actionable tiered framework). Blind spot: D (SI recommendation without sizing). All missed: capital efficiency per dollar deployed.

**Reviewer 4 (operations):** Strongest: E (sequenced execution plan). Blind spot: E (defers GC despite Tier 1 ranking). All missed: account application lead time.

**Reviewer 5 (data scientist):** Strongest: A (DSR 0.507 correctly flagged). Blind spot: B (WFE 0.956 window count unknown). All missed: multiple comparison correction.

---

## Chairman's Synthesis

### Where the Council Agrees
- NQ NY LSI is the flagship — unanimous
- GC NY R3 is real — 4/5 Tier 1 or mandatory
- Separate accounts dominate combined — unchallenged
- SI is low-conviction — DSR barely above noise
- Don't combine more than 3-4 legs per account

### Where the Council Clashes
- RR2 Gated vs FAST: verify OOS first, then decide
- Account count: expand sequentially (2-3 first, then 4-5)
- GC NY LSI: wait for 30+ OOS trades
- $1.66M lifecycle: direction correct, magnitude likely inflated

### Blind Spots
1. OOS trade counts unverified
2. Stress-period correlation unmeasured
3. Capital efficiency not computed
4. Account application lead time (2-4 weeks each)
5. Multiple comparison correction needed

### The Recommendation

**Individual legs (ranked):**
- Tier 1: NQ NY LSI, GC NY R3, NQ Asia FAST
- Tier 2: ES Asia, ES NY, GC NY LSI (pending 30+ OOS trades)
- Skip: SI, RTY, CL

**Combined (if forced):** NQ NY LSI + GC NY R3 + ES Asia

**RR2 Gated:** Build gate, shadow-run 60 days, then decide. Or run both as separate accounts.

**Expansion sequence:** NQ NY LSI now → NQ Asia week 2 → GC NY R3 week 3-4 → ES Asia month 2 → ES NY month 3

### The One Thing to Do First
Pull the OOS-only trade log for NQ NY LSI RR2 Gated. Verify 30+ holdout trades with metrics matching summary. This single verification either confirms the flagship upgrade or protects from deploying to an overfit variant.

---

*Council session completed April 3, 2026. 5 advisors, 5 peer reviews, chairman synthesis.*
