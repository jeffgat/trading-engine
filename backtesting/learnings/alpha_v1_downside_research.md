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

## Recommended Next Actions

### Immediate

1. Advance `nq_ny_short_orb0955_end1130_stop15p0_gap2p5_rr2p0_tp10p5_atr10` as the primary downside add-on candidate.
2. Keep the two sibling `NQ NY continuation short` promotions as backup challengers.
3. Treat `nq_ny_lsi_long_gate_gateskip_bear_h_rr3p0_tp10p34` as a shadow-run replacement candidate for `NQ NY LSI`, not as a new additive account.

### De-prioritize

1. Stop broad `ES NY dual-book` generalist search for now.
2. Stop broad `NQ Asia` and `ES Asia` downside quick-screen expansion for now.

### If We Continue to Wave 2

Only move into bear-specialist work after the promoted NQ NY short candidate is evaluated through the next downstream pipeline. If wave 2 starts, it should be framed as:

- **regime-specialist**, not broad generalist mirror search
- **down + medium/high vol**, using causal regime labels
- focused first on **NQ NY**, not ES or Asia

---

## Bottom Line

The downside search succeeded, but **narrowly**.

It did **not** discover a broad mirror portfolio for `ALPHA_V1`. It discovered that:

- the best additive downside opportunity is **NQ NY continuation short**
- the most useful LSI downside result is a **gated long variant**
- the apparent downside opportunity in `ES NY`, `NQ Asia`, and `ES Asia` mostly collapses once you demand true portfolio additivity instead of isolated regime beauty

That is a good outcome. It narrows the next research round to the part of the book that actually showed real incremental downside value.
