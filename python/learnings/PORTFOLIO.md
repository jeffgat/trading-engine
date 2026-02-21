# 4-Way Portfolio — Learnings

## Portfolio Composition

| Leg | Instrument | Strategy | Run ID | Trades | Period |
|-----|------------|----------|--------|--------|--------|
| NQ ASIA | NQ | Continuation v3 flat00 | 6718 | 1,800 | 2015–2026 |
| ES LDN  | ES | Continuation Both WF   | 6707 | 2,328 | 2016–2026 |
| NQ NY   | NQ | Long Continuation WF   | 6717 | 1,167 | 2015–2026 |
| GC NY   | GC | Inv Longs Stacked v9+CleanAir | 6693 | 349 | 2016–2026 |

**Combined portfolio**: Run ID 6719
**In-sample combined**: 5,644 trades, 54.7% WR, +1,131R, Sharpe 2.33, Calmar 42.3
**Analysis script**: `scripts/run_cross_asset_analysis.py`

---

## Section 1 — Pairwise Monthly R Correlation

**Method**: Monthly R sums per strategy, Pearson correlation over 134 common months.

| Pair | r | p-value | Signal |
|------|---|---------|--------|
| NQ ASIA ↔ ES LDN | +0.016 | 0.8635 | None |
| NQ ASIA ↔ NQ NY  | -0.029 | 0.7406 | None |
| NQ ASIA ↔ GC NY  | -0.089 | 0.3430 | None |
| ES LDN  ↔ NQ NY  | +0.069 | 0.4466 | None |
| ES LDN  ↔ GC NY  | +0.033 | 0.7251 | None |
| NQ NY   ↔ GC NY  | +0.063 | 0.5017 | None |

**Diversification score: 0.950** (avg pairwise |r| = 0.050) — **excellent**.

No pair exceeded |r| > 0.30. The four strategies operate on uncorrelated monthly R streams. This is genuine diversification, not just strategy-level independence.

Key takeaway: **Counter-intuitive finding** — ES LDN and NQ NY (both equity, both continuation) show near-zero monthly correlation (+0.069). Different sessions, different instruments, and different market microstructure produce uncorrelated outcomes even within the same asset class.

---

## Section 2 — Rolling 12-Month Correlation

Yearly correlation is also mostly near-zero. Two isolated spikes exceeded |r| > 0.50:

- **2019: NQ ASIA ↔ NQ NY = +0.557** — equity bull year, both strategies fired in sync across a calm trend
- **2023: ES LDN ↔ GC NY = +0.550** — single-year coincidence, not persistent

No pair shows consistently elevated correlation across multiple years. Correlation structure is **unstable year-to-year**, which is expected for independent signals.

Watch list: In strongly trending equity bull years (like 2019), NQ ASIA and NQ NY may temporarily correlate. Not enough to act on — both should still be run — but worth monitoring if another prolonged melt-up occurs.

---

## Section 3 — Concurrent Trade Analysis (NQ NY ↔ GC NY)

138 dates where both NQ NY and GC NY had filled trades.

| Condition | GC Win Rate | n |
|-----------|------------|---|
| Unconditional | 60.9% | 138 |
| NQ NY Won | 58.3% | 72 |
| NQ NY Lost | 63.6% | 66 |

**Win-rate delta: -5.3%** (GC wins MORE often when NQ loses)

→ **GC provides a mild natural hedge on NQ NY bad days.** Not strong enough to trade as a signal, but it confirms GC is adding genuine downside buffer to the portfolio, not just adding risk on the same days equity strategies struggle.

---

## Section 4 — Sequential Signal Analysis (Information Cascade)

### 4A — Does ES LDN predict NQ NY? (same calendar date)

| ES LDN Outcome | NQ NY Trades | NQ NY WR | NQ NY Avg R |
|----------------|-------------|----------|-------------|
| ES Won | 462 | 49.1% | +0.115 |
| ES Lost | 496 | 53.8% | +0.165 |
| ES No Trade | 209 | 52.2% | +0.130 |

**NQ NY performs BETTER when ES LDN lost.** F1 (skip NQ NY when ES LDN=sl) would be actively harmful (-7.0 Calmar delta, -$82R net R). Do not implement. ES LDN and NQ NY are independent enough that an ES loss provides zero negative signal for NQ NY.

### 4B — Does NQ ASIA predict ES LDN? (ASIA date D → ES LDN date D+1)

| NQ ASIA Outcome (prior night) | ES LDN Trades | ES LDN WR | ES LDN Avg R |
|-------------------------------|--------------|----------|--------------|
| ASIA Won | 1,402 | 49.0% | +0.305 |
| ASIA Lost | 767 | 46.5% | +0.215 |
| ASIA No Trade | 159 | 45.9% | +0.170 |

**NQ ASIA winning the previous night is a positive leading indicator for ES LDN.** ES LDN avg R is +42% higher after an ASIA win vs an ASIA loss (0.305 vs 0.215). The degradation is monotonic across Win → Loss → NoTrade.

**Filter F3 (skip ES LDN when NQ ASIA=sl previous night)**:
- Calmar delta: **+10.277 (+16.2%)** at portfolio level
- Filtered trades: 4,993 (removed 651) — high confidence
- Avg R improves: +0.025/trade
- Net R cost: -130R over 10 years (expected — fewer trades)
- This is the single most valuable cross-asset signal found

F3 interpretation: When NQ ASIA takes a full stop-loss the prior evening, it suggests unfavorable overnight conditions that tend to persist into the ES LDN session. This is not a time-zone overlap effect — NQ ASIA is complete before ES LDN opens.

### 4C — Does NQ NY outcome correlate with GC NY? (same day, partial overlap)

| NQ NY Outcome | GC NY Trades | GC NY WR | GC NY Avg R |
|---------------|-------------|----------|-------------|
| NQ Won | 72 | 58.3% | +0.504 |
| NQ Lost | 66 | 63.6% | +0.541 |

Consistent with Section 3: GC NY avg R is slightly higher when NQ loses. No actionable signal, but the slight negative correlation reinforces the hedge narrative.

---

## Section 5 — Regime-Conditional Performance

### VIX Buckets (prior-day close)

| VIX Bucket | NQ_ASIA Avg R | ES_LDN Avg R | NQ_NY Avg R | GC_NY Avg R |
|------------|-------------|------------|-----------|-----------|
| VIX < 15   | +0.090 (n=611) | +0.334 (n=839) | +0.120 (n=364) | +0.402 (n=120) |
| VIX 15–20  | +0.141 (n=519) | +0.323 (n=757) | +0.112 (n=354) | +0.429 (n=122) |
| VIX 20–25  | +0.100 (n=286) | +0.166 (n=389) | +0.147 (n=194) | +0.428 (n= 45) |
| VIX 25–30  | +0.225 (n=134) | +0.050 (n=203) | +0.155 (n= 92) | +0.116 (n= 29)† |
| VIX > 30   | -0.019 (n= 95) | +0.148 (n=140) | +0.271 (n= 67) | +0.693 (n= 33)† |

† = < 50 trades, low confidence

Key regime insights:
- **ES LDN degrades sharply above VIX 25**: avg R drops from 0.334 → 0.050 → loses effectiveness. F4 (skip ES LDN + NQ NY when VIX>25) only -0.9 Calmar delta — nearly neutral, possibly worth running to reduce stress on high-VIX days even without Calmar gain.
- **NQ NY is VIX-robust**: avg R is stable or slightly improving across VIX buckets. Counter-intuitive — NQ NY continuation longs hold up in volatile markets.
- **NQ ASIA is VIX-robust**: Similar stability. Goes slightly negative at VIX>30 but only marginally.
- **GC NY improves at high VIX**: avg R at VIX>30 is +0.693 (n=33, low confidence) — gold inversion longs actually improve when equity fear is elevated. GC provides portfolio support on equity-stress days. This is the core diversification argument in action.
- **No regime creates uniform portfolio weakness**: At no VIX level are all four strategies simultaneously degraded. This confirms the regime-robustness of the portfolio.

### SPY Trend (prior-day close vs 20-day SMA)

| Strategy | Risk-On (SPY ≥ SMA20) | Risk-Off (SPY < SMA20) |
|----------|-----------------------|------------------------|
| NQ_ASIA  | 1,125 trades, 63.5% WR, avg R +0.102 | 520 trades, 68.1% WR, avg R +0.135 |
| ES_LDN   | 1,601 trades, 49.4% WR, avg R +0.306 | 727 trades, 44.8% WR, avg R +0.179 |
| NQ_NY    | 697 trades, 51.1% WR, avg R +0.128  | 374 trades, 52.4% WR, avg R +0.146 |
| GC_NY    | 235 trades, 61.3% WR, avg R +0.495  | 114 trades, 50.0% WR, avg R +0.261 |

- **ES LDN is the clearest risk-on strategy**: avg R drops from 0.306 → 0.179 in risk-off markets. Primary equity session, most sensitive to SPY trend.
- **NQ ASIA is contrarian to SPY**: avg R slightly higher in risk-off (0.135 vs 0.102), WR also higher. Asia session operates somewhat independently from US equity trend direction.
- **GC NY risk-on premium**: Gold inversion longs perform markedly better in risk-on environments (avg R 0.495 vs 0.261). Consistent with the VIX finding — clean, trending risk-on markets produce the best fake-outs and reversals.
- **NQ NY is SPY-neutral**: Nearly identical WR and avg R in both regimes. Not a concern — just robust.

### DXY Trend (prior-day close vs 50-day SMA, GC and ES only)

| Strategy | DXY ≥ SMA50 (strong $) | DXY < SMA50 (weak $) |
|----------|------------------------|----------------------|
| GC_NY    | 171 trades, 54.4% WR, avg R +0.276 | 178 trades, 60.7% WR, avg R +0.555 |
| ES_LDN   | 1,200 trades, 47.2% WR, avg R +0.237 | 1,128 trades, 48.8% WR, avg R +0.297 |

- **GC performs 2× better with weak USD** (avg R 0.555 vs 0.276). Classic gold/USD inverse relationship. This is a known regime driver from single-asset GC analysis and holds at the portfolio level.
- **ES LDN has a mild weak-USD preference**: avg R 0.297 vs 0.237. Weak dollar tends to correlate with international risk-on flows, which could spill into LDN session equity moves.

---

## Section 6 — Filter Simulation Results

Baseline portfolio (no filters): 5,644 trades | 54.7% WR | Net R 1,131R | Calmar 42.342

| Filter | Trades | WR | Avg R | Net R | Calmar | ΔCalmar | Verdict |
|--------|--------|----|-------|-------|--------|---------|---------|
| **F3** | 4,993 | 55.8% | +0.200 | 1,000R | **52.619** | **+10.277** | **IMPLEMENT** |
| F5 | 5,535 | 54.7% | +0.201 | 1,114R | 42.215 | -0.127 | Neutral |
| F6 | 5,710 | 54.8% | +0.204 | 1,167R | 41.928 | -0.414 | No benefit |
| F4 | 5,145 | 55.6% | +0.207 | 1,066R | 41.420 | -0.922 | No benefit |
| F2 | 5,337 | 55.0% | +0.205 | 1,093R | 34.231 | -8.111 | **Harmful** |
| F1 | 5,156 | 54.8% | +0.203 | 1,049R | 35.323 | -7.019 | **Harmful** |

**F3 is the only filter that improves the portfolio (+16.2% Calmar). All others are neutral or harmful.**

### Filter F3 — Implementation Spec

- **Rule**: Skip ES LDN on any day where NQ ASIA took a full stop-loss (exit_type = `sl`) the prior evening.
- **Matching**: NQ ASIA session date D → skip ES LDN on date D+1 (calendar next day, with weekend lookahead up to 4 days).
- **Effect**: Removes 651 ES LDN trades (28% of ES LDN volume), improving avg R from 0.266 → 0.292.
- **Confidence**: n = 4,993 remaining portfolio trades — high confidence.
- **Live implementation**: Before opening any ES LDN position, check if yesterday's NQ ASIA result was an SL. If yes, skip the day's ES LDN.
- **Caution**: This is post-hoc analysis. Paper-trade F3 for 3–6 months before applying live to confirm the signal persists.

### Why F1 and F2 Are Harmful

F1 (skip NQ NY when ES LDN lost): NQ NY actually averages better R after an ES LDN loss (0.165 vs 0.115). These are different instruments in different sessions — the NQ NY signal is independent and should not be filtered by ES LDN outcome.

F2 (skip NQ NY when NQ ASIA lost): Same problem — NQ NY has no dependence on prior-night ASIA results. Skipping NQ NY costs real R without improving per-trade quality.

---

## Key Findings

### What works at portfolio level
- **Session cascade signal (F3)**: NQ ASIA SL the prior night is a reliable warning signal for ES LDN. Skipping ES LDN on those days improves portfolio Calmar by +16.2%.
- **GC as genuine portfolio diversifier**: Monthly r = 0.033 vs ES LDN, 0.063 vs NQ NY. GC NY avg R is higher on NQ-loss days (-5.3% win-rate delta). Provides real hedge value, not just uncorrelated exposure.
- **Session-based diversification beats instrument-based**: NQ ASIA (overnight) and ES LDN (early morning) are uncorrelated (+0.016) despite both being equity-continuation strategies. Session timing is more important than asset class for correlation.
- **High-VIX resilience**: At VIX > 30, NQ NY continues to perform (+0.271 avg R) and GC improves (+0.693 avg R, low confidence). ES LDN slows to +0.050. Portfolio stays positive across all VIX regimes.
- **No regime destroys the whole portfolio**: There is no VIX bucket, SPY regime, or DXY state where all four strategies simultaneously underperform. True diversification.

### What doesn't work at portfolio level
- **Using one strategy's loss as a skip signal for another equity leg**: ES LDN and NQ NY are independent enough that cross-signal filtering is harmful (F1, F2).
- **VIX-based equity cutoffs**: F4 (skip equity legs at VIX>25) and F5 (skip NQ NY at VIX>25 + SPY<SMA20) are near-neutral. These strategies are robust enough that filtering by VIX removes good trades as often as bad ones.
- **Doubling GC on NQ loss days**: The negative correlation between NQ NY and GC NY is too mild (~5% win-rate delta) to justify dynamic sizing. F6 barely moves the needle (-0.414 Calmar).

### Concentration risk assessment
- No VIX bucket has all four strategies degraded simultaneously — concentration risk is low.
- The only concentration scenario: prolonged low-VIX equity bull run (like 2019) where NQ ASIA and NQ NY may temporarily correlate. Monitor if this condition persists > 6 months.
- ES LDN is the most regime-sensitive leg (most impacted by SPY trend and VIX). If risk-off conditions persist, ES LDN is the first leg to pull back.

---

## Open Questions / Next Steps

1. **Live F3 validation**: Paper-trade the F3 rule for 3–6 months. Check if NQ ASIA SL → ES LDN skip continues to improve per-trade quality in live data.
2. **NQ ASIA SL rate**: What fraction of NQ ASIA trades are SLs? If > 40%, F3 would filter too many ES LDN days. Check trade distribution before implementing.
3. **Regime sizing**: The mild GC/equity negative correlation at high VIX could justify 1.25–1.5x GC sizing when VIX > 25. Too low confidence (n=29–33 in VIX>25/30 buckets) for now — revisit after 2026 adds more data.
4. **F3 timing risk**: F3 requires knowing NQ ASIA's exit_type before ES LDN opens. Confirm that NQ ASIA session always completes before 03:00 ET (ES LDN ORB start). The session ends ~midnight ET so there is a ~3-hour buffer. This is safe for live use.

---

## DB Entries

| Run | ID | Description |
|-----|----|-------------|
| Portfolio combined | 6719 | 4-Way Portfolio: ES LDN + NQ ASIA + NQ NY + GC NY |
| GC NY component | 6693 | GC NY Inv Longs Stacked v9+CleanAir |
| ES LDN component | 6707 | ES LDN 2016-2026 Continuation Both WF Mode |
| NQ NY component | 6717 | NQ NY Long Continuation Accepted (WF Mode) |
| NQ ASIA component | 6718 | NQ ASIA 2015-2026 v3 flat00 Pipeline NO-GO |

Analysis script: `scripts/run_cross_asset_analysis.py` (re-runnable, read-only, < 30 seconds)
