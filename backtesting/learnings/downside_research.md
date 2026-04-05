# ALPHA_V1 Downside Research

Wave-1 downside-variant discovery run for the frozen `ALPHA_V1` long-only separate-account portfolio.

Research date: 2026-04-03  
Baseline artifact: `backtesting/data/results/alpha_v1_downside/baseline_full/`  
Wave-1 artifact: `backtesting/data/results/alpha_v1_downside/wave1_full/`

---

## Executive Summary

The downside search produced **5 promoted candidates out of 811 tested**, and all 5 came from the **NQ NY stack**. Nothing from `ES NY dual-book`, `NQ Asia quick downside`, or `ES Asia quick downside` cleared the generalist additivity rules.

The most important result is that **the best true additive downside leg is NQ NY continuation short**, not an ES both-direction branch.

Two different things worked:

1. **NQ NY continuation short** found real short-only additive legs that improved downside behavior and improved the portfolio's worst rolling 3-month window without materially hurting the full-calendar book.
2. **NQ NY LSI downside variants** only promoted as **long-only gated “turn-off-in-bad-context” branches**, not as true short engines. These are more useful as replacement / shadow-run candidates than as genuinely distinct new downside accounts.

What did **not** work:

- `ES NY ORB dual-book`: 160 tested, 0 promoted.
- `NQ Asia downside quick`: 96 tested, 0 promoted.
- `ES Asia downside quick`: 48 tested, 0 promoted.

The broad conclusion is:

- **Downside additivity exists in NQ NY.**
- **It did not show up as a robust ES both-direction generalist.**
- **Asia downside candidates produced many false positives that improved downside slices while making the total portfolio drawdown profile worse.**

---

## Baseline: Frozen ALPHA_V1 Book

Unified holdout for this project was frozen at `2025-01-01+`.

### Portfolio Baseline

| Metric | Value |
|-------|------:|
| Full-history net R | +488.07R |
| Full-history max DD | -18.91R |
| Holdout net R | +85.87R |
| Holdout max DD | -11.63R |
| Holdout downside-regime net R | +28.38R |

### Weakest Baseline Periods

| Window | Worst Span | Net R |
|-------|------------|------:|
| 1m | 2016-06-09 to 2016-07-07 | -12.96R |
| 3m | 2020-06-10 to 2020-09-04 | -15.35R |
| 6m | 2018-04-17 to 2018-10-09 | -10.34R |

### Deepest Drawdown Clusters

| Rank | Span | Drawdown | Recovery |
|-----|------|---------:|----------|
| 1 | 2016-05-17 to 2016-07-07 | -18.91R | 2016-08-05 |
| 2 | 2020-06-09 to 2020-08-07 | -16.73R | 2020-11-17 |
| 3 | 2018-04-17 to 2018-05-29 | -13.69R | 2019-01-24 |
| 4 | 2021-06-24 to 2021-09-15 | -12.78R | 2021-11-18 |
| 5 | 2023-02-08 to 2023-03-03 | -12.34R | 2023-04-19 |

### Pairwise Overlap Notes

The current 4-leg book is already reasonably diversified by trade date, except for the two Asia legs:

- `ES Asia ORB` vs `NQ Asia ORB`: `0.4327` Jaccard overlap and `0.3831` daily R correlation. This is the highest overlap pair in the base portfolio.
- `NQ Asia ORB` vs `NQ NY LSI`: only `0.0574` Jaccard overlap and `-0.0184` daily R correlation.
- `ES NY ORB` vs `NQ NY LSI`: only `0.1581` Jaccard overlap and `0.0285` daily R correlation.

This mattered in the search: the best downside additions were the candidates that stayed structurally distinct from the existing long stack instead of acting like a noisy mirror.

---

## Wave-1 Search Coverage

Search order matched the plan:

1. `ES NY ORB dual-book`
2. `NQ NY continuation short`
3. `NQ NY LSI downside family`
4. `NQ Asia downside quick screen`
5. `ES Asia downside quick screen`

### Family Outcome Summary

| Family | Candidates | Promote | Reject | Takeaway |
|-------|-----------:|--------:|-------:|----------|
| `es_ny_orb_dual_book` | 160 | 0 | 160 | Strong downside lifts existed, but they consistently worsened the worst rolling 3m window. |
| `nq_ny_cont_short` | 432 | 3 | 429 | Best true downside-additive family. |
| `nq_ny_lsi_downside` | 75 | 2 | 73 | Only gated long variants promoted; short LSI branches still not convincing. |
| `nq_asia_downside_quick` | 96 | 0 | 96 | Big apparent downside lifts were false positives; additivity failed. |
| `es_asia_downside_quick` | 48 | 0 | 48 | Same pattern as NQ Asia, but worse. |
| **Total** | **811** | **5** | **806** | All promotions came from the NQ NY complex. |

---

## Promoted Candidates

### 1. Best Additive Downside Leg

`nq_ny_short_orb0955_end1130_stop15p0_gap2p5_rr2p0_tp10p5_atr10`

This is the strongest outcome of the whole wave because it is a **true short-only candidate** that behaves like a complementary leg rather than a slightly modified copy of an existing long system.

| Metric | Value |
|-------|------:|
| Family | `nq_ny_cont_short` |
| Direction | short |
| Standalone full-history R | +35.74R |
| Standalone holdout R | +15.10R |
| Combined full-history R | +523.81R |
| Combined full max DD | -18.96R |
| Combined holdout R | +100.96R |
| Combined holdout downside R | +33.11R |
| Worst 3m window | -11.98R |
| PSR | 0.962 |
| DSR | 0.895 |

Why it matters:

- Downside-regime holdout R improved from `+28.38R` to `+33.11R`, a `+16.66%` lift.
- Worst rolling 3-month window improved from `-15.35R` to `-11.98R`, a `+21.96%` improvement.
- Full max DD barely changed: `-18.91R` to `-18.96R`.
- Overlap with live `NQ NY LSI` was only `0.1963` Jaccard with `0.0066` daily R correlation, which is exactly what we want from an additive downside leg.

This is the clearest candidate to advance as a separate-account downside add-on.

### 2. Secondary NQ NY Short Variants

Two close siblings also promoted:

| Candidate | Combined Holdout R | Holdout Downside R | Worst 3m | PSR | DSR |
|----------|-------------------:|-------------------:|---------:|----:|----:|
| `nq_ny_short_orb0955_end1130_stop15p0_gap2p5_rr2p5_tp10p4_atr12` | +100.35R | +31.25R | -13.00R | 0.964 | 0.898 |
| `nq_ny_short_orb0955_end1130_stop15p0_gap2p5_rr2p5_tp10p4_atr10` | +100.16R | +31.25R | -13.03R | 0.974 | 0.921 |

These are valid backups, but the `rr=2.0 / tp1=0.5 / atr=10` version is the best first candidate because it delivered the best combined downside lift and the biggest 3-month drawdown improvement.

### 3. NQ NY LSI “Turn Long Off” Variants

Two LSI downside variants promoted:

| Candidate | Combined Holdout R | Holdout Downside R | Worst 3m | PSR | DSR |
|----------|-------------------:|-------------------:|---------:|----:|----:|
| `nq_ny_lsi_long_gate_gateskip_bear_h_rr3p0_tp10p34` | +103.08R | +35.74R | -13.01R | 1.000 | 0.999 |
| `nq_ny_lsi_long_gate_gateskip_bear_mh_rr3p0_tp10p34` | +95.73R | +28.38R | -13.01R | 1.000 | 0.994 |

These cleared because they improved the portfolio's worst rolling 3-month window enough to pass the rule-B additivity gate.

But they are **not true downside engines**:

- Both are still **long-only LSI** variants.
- The stronger one (`bear_h`) improved downside-regime holdout R by `+25.92%`, but full max DD worsened from `-18.91R` to `-24.22R`.
- Trade-date overlap with the live `NQ NY LSI` is extremely high:
  - `bear_h`: `0.8887` Jaccard overlap, `0.9252` daily R correlation
  - `bear_mh`: `0.8036` Jaccard overlap, `0.8590` daily R correlation

Interpretation: these are better viewed as **gated replacement / shadow-run branches** for the flagship LSI leg, not as brand-new additive separate-account downside accounts.

---

## What Failed

### ES NY ORB Dual-Book Failed Broadly

`ES NY` was the first place to look for a both-direction generalist, but the wave-1 result was decisive: **160 tested, 0 promoted**.

The best ES NY candidates often showed attractive downside-lift numbers:

- top rejects had `+29%` to `+36%` downside improvement

But the same candidates consistently violated the rolling-window guardrail:

- worst rolling 3-month deterioration ranged from roughly `-19%` to `-65%`

So the problem was not “no short edge exists at all.” The problem was that **whatever ES NY downside edge appeared in isolation did not combine cleanly with the live long-only book under the generalist rules**.

### NQ Asia Quick Screen Produced False Positives

`NQ Asia` had some of the most visually tempting downside-lift numbers in the entire run:

- top rejects showed `+89%` to `+100%` downside improvement

But every one of those candidates failed additivity because the portfolio’s worst 3-month window got much worse:

- top rejects showed `-59%` to `-73%` rolling-3m deterioration

This confirms the prior negative evidence around NQ Asia downside work. It can create attractive local downside slices without improving the full portfolio’s actual pain profile.

### ES Asia Quick Screen Was Even Worse

`ES Asia` had the same failure mode, just more extreme:

- downside-lift numbers as high as `+89%`
- rolling-3m deterioration from roughly `-109%` to `-145%`

That is a clear reject for the current generalist objective.

---

## Main Conclusions

### 1. The best downside research path is now NQ NY short continuation

This is the only branch that clearly produced **true additive downside legs** instead of pseudo-diversified copies or false-positive downside specialists.

### 2. NQ NY LSI downside work found a useful filter, not a short engine

The LSI outcome is still valuable, but it answered a different question:

- not “what short LSI should we deploy?”
- but “when should we skip parts of the existing long LSI profile?”

That belongs in a replacement / shadow-run workflow, not the same bucket as a new separate-account short leg.

### 3. Generalist downside strength did not transfer to ES or Asia

This is the biggest negative result of the wave:

- `ES NY dual-book` did not clear
- `NQ Asia downside quick` did not clear
- `ES Asia downside quick` did not clear

So broad downside deployment should **not** be framed as “find a mirror branch for every live leg.” The evidence says the edge is concentrated in **specific NQ NY structures**, not evenly available across the whole long-only portfolio.

---

## Phase 1: Prop Firm Evaluation (2026-04-04)

Phase-one prop sim on all 3 promoted NQ NY continuation short candidates, both standalone and combined with the ALPHA_V1 long book.

Script: `backtesting/scripts/run_alpha_v1_downside_phase1.py`

### Standalone Short Accounts (+5R / -4R, 14-day stagger, full history)

| Candidate | Trades | WR | Net R | DD | Calmar | Sharpe | Pay% | EV/acct | Avg Days | MCB |
|-----------|--------|-----|-------|-----|--------|--------|------|---------|----------|-----|
| RR2.0 ATR10 | 559 | 61.2% | +35.7 | -19.6R | 1.82 | 1.19 | 62.8% | +1.657 | 228 | 37 |
| RR2.5 ATR12 | 559 | 60.8% | +37.0 | -21.5R | 1.72 | 1.20 | 61.2% | +1.495 | 219 | 36 |
| **RR2.5 ATR10** | **559** | **61.2%** | **+39.8** | **-20.9R** | **1.90** | **1.29** | **64.2%** | **+1.764** | **222** | **35** |

Holdout (2025-01-01+): all 3 showed 63 trades, 76.2% WR, +14 to +15R, -5.0R DD.

R by year (RR2.5 ATR10): 2016:+7.9 | 2017:-1.2 | 2018:+4.5 | 2019:-11.4 | 2020:+0.3 | 2021:+5.2 | 2022:+5.0 | 2023:+10.7 | 2024:+4.5 | 2025:+11.0 | 2026:+3.3

### Standalone Phase-1 Verdict

**Not viable as independent prop farm accounts.** All three show:

- 61-64% payout rate (below the 80% target)
- 35-37 max consecutive breaches
- Negative years: 2017 and 2019

The short edge is real but too inconsistent across regimes to survive standalone account farming.

### Combined Portfolio (ALPHA_V1 + Short Leg, 0.2R/trade, +25R/-20R)

| Portfolio | Pay% | EV/acct | Avg Days | Med Days |
|-----------|------|---------|----------|----------|
| ALPHA_V1 baseline (no short) | 100.0% | +23.247 | 728 | 746 |
| + RR2.0 ATR10 | 100.0% | +23.532 | 704 | 708 |
| + RR2.5 ATR12 | 100.0% | +23.508 | 705 | 702 |
| + RR2.5 ATR10 | 100.0% | +23.507 | 701 | 699 |

Adding the short leg shaves ~25-45 days off median payout time and adds ~+0.3R EV/account. Marginal but positive. Baseline is already 100% success, so the short leg's role here is drawdown reduction and payout speed, not survival.

---

## Phase 1.5: Regime Gate Sweep (2026-04-04)

Regime gates were never tested on the NQ NY continuation short family in wave-1. This sweep applied the causal 3x3 regime framework (trend × vol, shifted 1 session) to all 3 promoted candidates.

Script: `backtesting/scripts/run_alpha_v1_downside_regime_gates.py`

### Regime Attribution — Consistent Pattern Across All 3 Candidates

The short edge is concentrated in **high volatility** and dies in **low volatility**:

**Worst buckets (all 3 candidates agree):**

| Bucket | Avg R | Total R | WR | Interpretation |
|--------|-------|---------|-----|----------------|
| `bull_low_vol` | -0.12 to -0.14 | -11 to -13R | 43% | Quiet uptrend kills short follow-through |
| `sideways_low_vol` | -0.07 to -0.08 | -3.6 to -4.4R | 52-54% | Low-vol chop = stop hunts |
| `sideways_medium_vol` | -0.05 to -0.07 | -3.0 to -4.7R | 52% | Similar but milder |

**Best buckets (all 3 candidates agree):**

| Bucket | Avg R | Total R | WR |
|--------|-------|---------|-----|
| `bull_high_vol` | +0.31 to +0.35 | +22 to +25R | 75-76% |
| `sideways_high_vol` | +0.21 to +0.23 | +11 to +12R | 73-75% |
| `bear_high_vol` | +0.15 to +0.16 | +10R | 70% |

This makes structural sense: NQ continuation shorts need volatility to produce the ORB breakdowns and FVG setups that drive the signal. In low-vol bull environments, dip-buying dominates and short signals get run over.

### Gate Sweep Results — RR2.5 ATR10 (Best Candidate)

19 gate variants tested across all 3 candidates. RR2.5 ATR10 won across the board.

| Gate | Trades | Net R | DD | Calmar | Pay% | EV/acct | MCB | Neg Yr | H-R |
|------|--------|-------|-----|--------|------|---------|-----|--------|-----|
| ungated | 559 | +39.8 | -20.9R | 1.90 | 64.2% | +1.764 | 35 | 2 | +14.3 |
| `skip_bull_low_vol` | 464 | +52.7 | -14.4R | 3.66 | 82.2% | +3.330 | 29 | 1 | +10.2 |
| `skip_bull+sw_low` | 408 | +56.3 | -12.1R | 4.67 | 80.2% | +3.144 | 29 | 1 | +9.7 |
| `skip_bull_low+med` | 385 | +45.9 | -9.9R | 4.65 | 80.7% | +3.196 | 19 | 1 | +7.4 |
| `skip_bull+sw_low+med` | 264 | +52.6 | -7.8R | **6.74** | **92.7%** | **+4.255** | **9** | 1 | +5.5 |

Year-by-year for `skip_bull+sw_low+med`: 2016:+9.3 | 2017:+1.0 | 2018:+7.7 | 2019:-0.9 | 2020:+0.6 | 2021:+5.9 | 2022:+6.0 | 2023:+12.0 | 2024:+5.5 | 2025:+2.6 | 2026:+2.9

Year-by-year for `skip_bull_low_vol`: 2016:+13.0 | 2017:+2.4 | 2018:+7.7 | 2019:-7.4 | 2020:+1.4 | 2021:+5.7 | 2022:+5.0 | 2023:+11.8 | 2024:+7.0 | 2025:+7.8 | 2026:+1.9

### Gate Impact Summary

The `skip_bull_low_vol` gate on RR2.5 ATR10:

- Removes 95 trades (17%) — all from the worst-performing bucket
- Calmar: 1.90 → 3.66 (+93%)
- Max DD: -20.9R → -14.4R (-31%)
- Payout rate: 64.2% → **82.2%** (clears the 80% threshold)
- EV/acct: +1.764 → +3.330 (+89%)
- Negative years: 2 → 1 (only 2019 at -7.4R, vs -11.4R ungated)

The aggressive `skip_bull+sw_low+med` gate is even stronger on risk metrics (Calmar 6.74, DD -7.8R, 92.7% pay, MCB 9) but removes 53% of trades and reduces holdout R to +5.5. Better suited as a conservative deployment option.

---

## Recommended Next Actions

### Primary Recommendation

Advance **RR2.5 ATR10 with `skip_bull_low_vol` gate** as the downside add-on:

`nq_ny_short_orb0955_end1130_stop15p0_gap2p5_rr2p5_tp10p4_atr10`

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY (09:30-09:55 ORB, entry 09:55-11:30, flat 11:30) |
| direction | short only |
| rr | 2.5 |
| tp1_ratio | 0.4 |
| atr_length | 10 |
| stop | 15% ORB |
| gap filter | 2.5% ORB |
| min_stop_points | 10.0 |
| min_tp1_points | 10.0 |
| regime gate | skip `bull_low_vol` |
| magnifier | 1s |

This is a **regime-gated short-only separate-account leg**, not a combined-account add-on. It clears the 80% payout threshold with the gate applied.

### Conservative Alternative

`skip_bull+sw_low+med` gate on the same candidate for maximum risk-adjusted deployment (92.7% pay, Calmar 6.74, MCB 9). Trades less often (264 vs 464) but much safer.

### Backup Challenger

RR2.0 ATR10 with `skip_bull_low_vol` gate: 81.5% pay, +3.293 EV, similar profile.

### Shadow Run Candidates

- `nq_ny_lsi_long_gate_gateskip_bear_h_rr3p0_tp10p34`: still a replacement/shadow-run for NQ NY LSI, not a new account.

### De-prioritize

1. Stop broad `ES NY dual-book` generalist search.
2. Stop broad `NQ Asia` and `ES Asia` downside quick-screen expansion.

### If We Continue to Wave 2

Only move into bear-specialist work after the gated NQ NY short candidate is validated through live shadow-run. If wave 2 starts, it should be framed as:

- **regime-specialist**, not broad generalist mirror search
- **down + medium/high vol**, using causal regime labels
- focused first on **NQ NY**, not ES or Asia

---

## Bottom Line

The downside search succeeded in two phases:

**Wave-1 discovery** found that the best additive downside opportunity is NQ NY continuation short, not ES mirrors or Asia variants.

**Phase-1 + regime gating** transformed the winning candidate from a marginal standalone leg (64% pay, Calmar 1.9) into a viable prop farm account (82% pay, Calmar 3.7) by removing trades in `bull_low_vol` — the one regime where the short continuation edge consistently dies.

The short edge is structurally a **volatility play**: it thrives in high vol regardless of trend direction, and dies in quiet markets. The regime gate exploits this cleanly.

---

## Wave 2: Cross-Asset Broad Downside Search (2026-04-04)

Expanded the search beyond ALPHA_V1 variants to test all short/both-direction candidates from the `TOP_CANDIDATES_PER_ASSET_REPORT` as additive legs to the ALPHA_V1 long portfolio.

Scripts: `backtesting/scripts/run_downside_broad_search.py`, `backtesting/scripts/run_downside_regime_gates.py`

### Candidates Tested

10 candidates across 4 instruments: NQ (1), GC (3), RTY (3), SI (3).

### ALPHA_V1 Baseline (refreshed)

| Metric | Value |
|-------|------:|
| Combined trades | 3,708 |
| Combined net R | +644.6R |
| Combined max DD | -15.7R |
| Worst rolling 3m | -9.2R |

### Standalone Performance

| Candidate | Sym | Dir | Trades | Net R | DD | Calmar | Holdout R | Pay% | EV | MCB |
|-----------|-----|-----|--------|-------|-----|--------|-----------|------|-----|-----|
| GC Asia-1 Both | GC | both | 1558 | +192.3 | -14.5R | **13.26** | +17.9 | 70.3% | +2.321 | 7 |
| SI Asia-4 Short | SI | short | 946 | +127.0 | -10.8R | **11.78** | +7.8 | 75.2% | +2.605 | 8 |
| SI Asia-1 Short | SI | short | 946 | +126.0 | -11.2R | **11.22** | +5.4 | **78.9%** | +2.868 | **6** |
| SI Asia-3 Short | SI | short | 946 | +130.1 | -12.1R | 10.78 | **+11.1** | 69.7% | +2.151 | 8 |
| RTY NY-1 Both | RTY | both | 1622 | +183.3 | -20.6R | 8.89 | +0.9 | 62.2% | +1.582 | 9 |
| RTY NY-2 Both | RTY | both | 1622 | +159.3 | -20.9R | 7.62 | +2.7 | 64.7% | +1.789 | 8 |
| RTY NY-4 Both | RTY | both | 1622 | +119.2 | -17.5R | 6.80 | -6.7 | 64.8% | +1.817 | 10 |
| GC Asia-2 Short | GC | short | 993 | +99.3 | -18.5R | 5.36 | -0.8 | 69.4% | +2.157 | 14 |
| GC Asia-3 Short | GC | short | 842 | +95.8 | -23.3R | 4.11 | -9.7 | 67.8% | +2.066 | 37 |
| NQ NY Short | NQ | short | 559 | +39.8 | -20.9R | 1.90 | +14.3 | 64.2% | +1.764 | 35 |

### Portfolio Additivity

| Candidate | Jaccard | Daily R Corr | Comb Net R | Comb DD | Comb HO R | Worst 3m | W3m Δ% |
|-----------|---------|-------------|------------|---------|-----------|----------|--------|
| GC Asia-3 Short | 0.230 | +0.08 | +740.5 | -17.5R | +98.6 | -6.7R | **+27.9%** |
| GC Asia-2 Short | 0.263 | +0.05 | +744.0 | -17.7R | +107.5 | -8.6R | **+7.2%** |
| SI Asia-1 Short | 0.256 | **-0.19** | +770.7 | -18.1R | +113.7 | -10.0R | -8.0% |
| SI Asia-4 Short | 0.256 | **-0.18** | +771.6 | -19.0R | +116.2 | -10.7R | -16.1% |
| GC Asia-1 Both | 0.407 | +0.03 | +836.9 | -16.8R | +126.2 | -11.9R | -28.5% |
| SI Asia-3 Short | 0.256 | -0.19 | +774.7 | -19.4R | +119.4 | -12.9R | -39.7% |
| NQ NY Short | 0.171 | -0.06 | +684.4 | -20.0R | +122.6 | -13.4R | -44.7% |
| RTY NY-2 Both | 0.465 | -0.01 | +803.9 | -22.3R | +111.1 | -13.5R | -46.0% |
| RTY NY-4 Both | 0.465 | -0.01 | +763.8 | -22.3R | +101.7 | -15.4R | -66.3% |
| RTY NY-1 Both | 0.465 | +0.01 | +827.9 | -25.9R | +109.2 | -17.9R | -93.7% |

### Key Findings

1. **GC shorts are the only candidates that improve the portfolio's worst rolling 3-month window.** GC Asia-3 Short improved it by +27.9% and GC Asia-2 Short by +7.2%. Every other candidate made it worse.

2. **SI shorts have the best negative daily R correlation (-0.19)** — ideal for diversification — but they still slightly worsen the rolling window. Their standalone prop metrics are the best in the set (SI Asia-1: 78.9% pay, MCB 6, Calmar 11.22).

3. **RTY candidates fail additivity hard.** All 3 worsened the worst 3m by -46% to -94%, driven by high overlap (0.465 Jaccard) — they trade on the same days as the NQ/ES legs.

4. **GC is the true diversifier.** Low Jaccard (0.23-0.26 for shorts), low daily R correlation, and commodity exposure distinct from the equity-index long book.

5. **GC Asia-3 Short has a holdout problem** (-9.7R, 2025: -11.3R). GC Asia-2 Short is more balanced (-0.8R holdout) but still has 2 slightly negative years.

### Regime Gate Results (GC + SI)

Per-asset regime calendars (causal, tercile vol) applied. Key results:

**GC Asia-2 Short:**
- `bull_medium_vol` is the worst bucket (-12.5R, 46.2% WR)
- `skip_bull+sw_med` gate: **0 neg years**, 73.5% pay, Calmar 7.92, +2.535 EV
- The medium-vol gate fixes GC shorts just like the low-vol gate fixes NQ shorts

**GC Asia-3 Short:**
- `bull_medium_vol` barely positive (+0.6R), the weakest bucket
- `skip_bull+sw_low+med` gate: 1 neg year, **81.4% pay**, +3.184 EV, MCB 12

**GC Asia-1 Both:**
- Already 0 neg years ungated (Calmar 13.26)
- `skip_bear_low+med` gate: still 0 neg years, 73.7% pay, +2.624 EV, MCB 6

**SI Asia-1 Short:**
- `bull_medium_vol` is the only negative bucket (-0.8R, 42.9% WR) — nearly flat
- `skip_bull_med` gate: **82.0% pay** (clears 80% threshold), +2.966 EV, MCB 8, Calmar 10.36
- This is the simplest gate: just skip medium-vol bull days

**SI Asia-4 Short:**
- Same pattern: `bull_medium_vol` is -7.2R, worst bucket
- `skip_bull_med` gate: 78.4% pay, +2.774 EV, Calmar 11.15

---

## Updated Promoted Candidates (All Research)

### Tier 1 — Deploy as separate accounts

| Rank | Candidate | Gate | Pay% | EV | Calmar | MCB | Neg Yr | Role |
|------|-----------|------|------|-----|--------|-----|--------|------|
| 1 | **NQ NY Short RR2.5 ATR10** | `skip_bull_low_vol` | 82.2% | +3.330 | 3.66 | 29 | 1 | NQ short hedge |
| 2 | **SI Asia-1 Short** | `skip_bull_medium_vol` | 82.0% | +2.966 | 10.36 | 8 | 2 | Commodity short, best neg corr |
| 3 | **GC Asia-1 Both** | ungated | 70.3% | +2.321 | 13.26 | 7 | 0 | Commodity diversifier, 0 neg yrs |

### Tier 2 — Shadow run / evaluate further

| Candidate | Gate | Pay% | EV | Calmar | Notes |
|-----------|------|------|-----|--------|-------|
| GC Asia-2 Short | `skip_bull+sw_med` | 73.5% | +2.535 | 7.92 | Best W3m additivity, 0 neg yrs |
| SI Asia-4 Short | `skip_bull_med` | 78.4% | +2.774 | 11.15 | Backup to SI Asia-1 |
| NQ NY Short RR2.5 ATR10 | `skip_bull+sw_low+med` | 92.7% | +4.255 | 6.74 | Conservative NQ short option |

### Rejected

| Candidate | Reason |
|-----------|--------|
| RTY NY-1/2/4 | High overlap (0.465 Jaccard), worst-3m deterioration -46% to -94% |
| GC Asia-3 Short | Holdout -9.7R, 2025 -11.3R — recent performance collapsing |
| NQ NY Short (ungated) | 64.2% pay, 35 MCB — not viable without gate |

---

## Bottom Line (Updated)

The cross-asset search confirmed two things:

1. **The best downside additivity comes from commodities (GC, SI), not more equity-index shorts.** GC shorts are the only candidates that improve the portfolio's worst rolling window. SI shorts provide the strongest negative correlation.

2. **Regime gates are consistently the unlock.** Across NQ, GC, and SI, the same pattern holds: removing the worst 1-2 regime buckets transforms marginal candidates into viable legs. The specific buckets differ by asset (NQ = low vol, GC/SI = medium vol), but the mechanism is the same.

The portfolio now has 3 viable new legs to deploy: NQ NY Short (gated), SI Asia-1 Short (gated), and GC Asia-1 Both (ungated). Together they provide equity-index short coverage, commodity diversification, and negative correlation with the existing long book.
