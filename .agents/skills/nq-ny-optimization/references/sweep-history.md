# NQ NY Optimization Sweep History

Full anchor evolution log across all optimization rounds.

## ⚠️ 1m Magnifier Era Warning

All results below were produced using the **1m bar magnifier** (`df_1m` passed to `run_backtest`). Going forward, the standard is **1s magnifier** (`df_1s` / `NQ_1s.parquet`). The 1s magnifier provides finer fill/stop precision, which may shift Calmar numbers and potentially the optimal stop/rr values.

**What is still valid**: The methodology, decision rationale, adoption thresholds, parameter ordering, and qualitative insights (e.g., "stop=9% reshuffled the rr/tp1 surface", "long-only dominates"). These are structural findings about the strategy, not artifacts of the magnifier resolution.

**What is not valid as targets**: All Calmar, Sharpe, Net R, R/yr, and drawdown numbers. Use these for relative comparisons only — not as performance expectations on new data with 1s magnifier.

---

## Starting Point: WF Mode Params Baseline

**Anchor**: rr=2.0, tp1=0.5, stop=10%, min_gap=1.5%, ATR 14, 15m ORB (09:30-09:45), both directions

These were the WF mode params from the initial robust pipeline run on the default config. The variable sweep program was started to improve the structural anchor from this starting point.

---

## Round 1 Variable Sweeps

**Script**: `run_nq_ny_variable_sweeps.py`
**Anchor entering round**: rr=2.0, tp1=0.5, stop=10%, gap=1.5%, ATR 14, 15m ORB, both directions

Variables swept (one at a time):
- max_gap_points: 20, 30, 40, 50, 75, 100*, 150, 200, none
- max_gap_atr_pct: 0*, 3, 5, 7.5, 10, 15, 20, 25
- atr_length: 7, 10, 14*, 20, 30, 50
- ORB window: 15m*, 30m, 45m, 60m
- entry_end: 10:30, 11:00, 11:30, 12:00, 12:30, 13:00*, 14:00, 15:00
- direction: both*, long, short

**Key insight from Round 1**: ATR length insensitive (14 confirmed). Entry end extending to 13:00 default was suboptimal — late NY entries productive. Direction "both" was the starting point but long-only showed higher Sharpe in R3.

---

## Round 2 Variable Sweeps

**Script**: `run_nq_ny_variable_sweeps_2.py`
**Anchor entering round**: rr=2.0, tp1=0.5, stop=10%, gap=1.5%, ATR 14, 15m ORB, both directions

Variables swept:
- rr (finer): 1.25 to 3.0 in 0.25 steps
- tp1 (finer): 0.2, 0.3, 0.4, 0.5*, 0.6, 0.7, 0.8, 1.0
- stop (wider): 3, 5, 7.5, 10*, 12.5, 15, 17.5, 20, 25
- min_gap (finer): 0.5, 0.75, 1.0, 1.25, 1.5*, 2.0, 2.5, 3.0, 4.0
- flat time: 14:30, 15:00, 15:30, 15:50*, 16:00
- entry start delay: 09:45*, 10:00, 10:15, 10:30
- DOW exclusion: none*, excl Mon, Tue, Wed, Thu, Fri

**Key insight from Round 2**: rr=2.0 confirmed. Entry start delay insensitive. Flat time insensitive. DOW exclusions showed round-to-round instability — treat skeptically.

---

## Round 3 Variable Sweeps

**Script**: `run_nq_ny_variable_sweeps_3.py`
**Anchor entering round**: rr=2.0, tp1=0.5, stop=10%, gap=1.5%, ATR 14, 15m ORB, both directions

Variables swept (new dimensions):
- ORB window fine: 5m, 10m, 15m*, 20m, 25m, 30m
- ORB start time: 09:25, 09:30*, 09:35
- Strategy type: continuation*, reversal, inversion
- Multi-day exclusions: none*, Thu+Fri, Mon+Fri, Mon+Thu, etc.
- Long-only rr, ORB, entry_end, max_gap sweeps
- Half-day handling: include* vs exclude

**Key insights from Round 3:**
- **Long-only Sharpe 1.63 vs both 1.44** — long direction is the dominant lever
- **20m ORB (09:30-09:50) wins** for long-only (Sharpe 1.68 vs 15m 1.63)
- Strategy type: continuation only — reversal/inversion no edge found
- ORB start time: 09:30 confirmed
- Both wins adopted: **long-only + 20m ORB** → anchor changed, R4 required

---

## Round 4 Variable Sweeps

**Script**: `run_nq_ny_variable_sweeps_4.py`
**Anchor entering round**: rr=2.0, tp1=0.5, stop=10%, gap=1.5%, ATR 14, 20m ORB, long-only
**Change from R3**: direction=long + ORB=20m

Re-swept all variables against the improved long-only + 20m ORB anchor.

**Key findings from Round 4** (Calmar focus):

| Variable | Best value | Calmar Δ vs anchor | Decision |
|----------|-----------|-------------------|----------|
| entry_start delay | 10:30 | improves DD | Candidate |
| entry_end | 14:00 | improves DD | Candidate |
| min_gap | 3.0% | improves Calmar | Candidate |
| tp1 | 0.4 | improves Calmar | Candidate |
| excl-Fri | on | improves DD | Candidate (later dropped — shifting DOW pattern) |
| rr | 2.0 confirmed | 0 | Stable |
| stop | 10% confirmed | 0 | Stable at this resolution |

Multiple candidates stack in Phase 5.

---

## Round 5 Variable Sweeps

**Script**: `run_nq_ny_variable_sweeps_5.py`
**Anchor**: rr=2.0, tp1=0.5, stop=10%, gap=1.5%, 20m ORB, long-only
**Objective**: Stack DD-reducing candidates from R4 and find best combination

Stacking candidates tested:
- entry_start=10:30, entry_end=14:00, gap=3.0%, excl-Fri, tp1=0.4

**Phase A**: Tested all stacking combos to find best foundation
**Phase B**: Full variable sweep against best stacked base

**Outcome**: entry_end=15:00 (not 14:00) came out as the best overall — extending to full 15:00 captured late-day fills that drove R/yr. The stacking of entry_start=10:30 actually hurt by missing early fills. Gap=3.0% adopted (fewer but higher-quality FVGs).

**Anchor exiting R5**: rr=2.0, tp1=0.5, stop=10%, gap=3.0%, 20m ORB, entry 09:50-15:00, long-only

---

## Round 6 Variable Sweeps

**Script**: `run_nq_ny_variable_sweeps_6.py`
**Anchor**: rr=2.0, tp1=0.5, stop=10%, gap=3.0%, 20m ORB, entry 09:50-15:00, long-only
**Objective**: Push R/year higher

Tested:
1. Higher RR (1.5 to 3.5) — rr=2.75 showed promise in conjunction with higher tp1
2. Shorts back (direction=both) with stacked improvements — marginal; long-only still wins on Calmar
3. gap × rr interaction grid — confirmed gap=3.0% as global best for multiple rr values
4. tp1 × rr interaction — higher rr favors higher tp1
5. stop × rr interaction — stop=10% with rr=2.75 shows good performance (foreshadows R9)
6. entry_end × rr — 15:00 optimal across all rr values

**Best Calmar from R6**: rr=2.75, tp1=0.5, gap=3.0%, stop=10% (Calmar ~14.86)

---

## Round 7 Variable Sweeps — First 3-Way Grid

**Script**: `run_nq_ny_variable_sweeps_7.py`
**Anchor**: rr=2.0, tp1=0.5, stop=10%, gap=3.0%, 20m ORB, entry 09:50-15:00, long-only
**Grid**: gap(3) × rr(6) × tp1(5) = 90 combos at stop=10%

| Rank | Config | Calmar | DD |
|------|--------|--------|----|
| #1 | g=3.5, rr=2.50, tp1=0.4 | ~15.0 | ~-12R |
| #2 | g=3.0, rr=2.50, tp1=0.4 | ~14.9 | ~-12R |
| #3 | g=3.5, rr=3.00, tp1=0.3 | ~14.8 | ~-8.8R (lowest DD) |
| #5 | g=3.0, rr=2.75, tp1=0.6 | ~13.9 | medium |
| #6 | g=3.0, rr=2.25, tp1=0.6 | ~13.8 | medium |

**Adopted**: rr=2.5, tp1=0.4 from grid winner (at stop=10%)

**Note**: This grid was run at stop=10%. When stop changes in R9, the entire surface will look different (see R9-R11).

---

## Round 8 Variable Sweeps — Separate Short Optimization

**Script**: `run_nq_ny_variable_sweeps_8.py`
**Anchor long**: 20m ORB, gap=3%, rr=2.0-2.75, tp1=0.4-0.5, stop=10%, long-only
**Objective**: Separate short-only optimization + combined L+S

Phase A: Short-only sweep
- gap: 1.0-3.0, rr: 1.5-3.0, tp1: 0.3-0.6, stop: 7.5/10/12.5, entry_end: 12-15

Phase B: Combined L+S (independent params, first-to-fill)

**Outcome**: Combined L+S showed modestly higher R/yr but Calmar improvement was below the +0.3 threshold. Long-only remains the primary anchor. Short optimization results retained for reference (used in R14-R15 when re-tested with updated long anchor).

---

## Round 9 Variable Sweeps — CRITICAL: Fine-Grained Stop Discovery

**Script**: `run_nq_ny_variable_sweeps_9.py`
**Anchor**: multiple top configs from R6/R7 (stop=10%)
**Objective**: Fine stop sweep — 3% to 14% in 1% increments

Configs tested:
1. g=3.5, rr=2.50, tp1=0.4 (R7 #1)
2. g=3.0, rr=2.50, tp1=0.4 (R7 #2)
3. g=3.5, rr=3.00, tp1=0.3 (R7 lowest DD)
4. g=3.0, rr=2.00, tp1=0.5 (original base)
5. g=3.0, rr=2.75, tp1=0.5 (R6 best R/yr)
6. g=3.0, rr=2.75, tp1=0.6 (R7 #5)
7. g=3.0, rr=2.25, tp1=0.6 (R7 #6)

**Key discovery**: stop=9% dramatically improves rr=2.75 and rr=2.25 configs. Config g=3.0, rr=2.75, tp1=0.6 at stop=9% showed the biggest jump. But stop=9% does NOT improve rr=2.0 or rr=2.5 configs proportionally.

**Why this matters**: The stop × rr interaction is strong. A 1% stop reduction creates a different R-to-stop ratio that interacts with TP1 placement and runner behavior.

---

## Round 10 Variable Sweeps — Ultra-Fine Stop Confirmation

**Script**: `run_nq_ny_variable_sweeps_10.py`
**Anchor**: g=3.0, rr=2.75, tp1=0.6, stop=? (best from R9)
**Stop range**: 8.5% to 9.5% in 0.1% increments

**Result**: stop=9.0% confirmed as the precise optimum for the rr=2.75 config. The curve was sharp — 8.9% and 9.1% both worse. Stop=9.0% is stable.

**Anchor after R10**: g=3.0, rr=2.75, tp1=0.6, stop=9%

---

## Round 11 Variable Sweeps — CRITICAL: Grid Re-run After Stop Change

**Script**: `run_nq_ny_variable_sweeps_11.py`
**Anchor entering**: g=3.0, rr=2.75, tp1=0.6, stop=9%, long-only, 20m ORB, entry 09:50-15:00
**Grid**: gap(3) × rr(6) × tp1(5) = 90 combos at stop=9%

This round re-ran the exact same grid as R7 but at stop=9% instead of stop=10%.

**Grid results at stop=9%:**

| Rank | Config | Calmar | R/yr | DD |
|------|--------|--------|------|-----|
| **#1** | **g=3.0, rr=2.25, tp1=0.7** | **~17.17** | **~16.5R/yr** | **~-10.6R** |
| #2 | g=3.0, rr=2.00, tp1=0.7 | ~16.x | ~15.x | ~-10.x |
| #3 | g=3.0, rr=2.50, tp1=0.6 | ~15.x | ~14.x | ~-11.x |

**vs R7 grid winner at stop=10%:** g=3.5, rr=2.50, tp1=0.4 (Calmar ~15.0)

**The surface completely changed**: tp1=0.7 now dominates (was 0.3-0.4 at stop=10%). rr=2.25 is now optimal (was 2.5). Gap=3.0 beats 3.5. The entire winner profile inverted.

**This is the R9-R11 lesson**: A stop change of just 1% (10% → 9%) completely reshuffled the rr/tp1/gap surface. Never proceed to pipeline without re-running the full grid after a stop change.

**Anchor adopted**: g=3.0, rr=2.25, tp1=0.7, stop=9%, 20m ORB, entry 09:50-15:00, long-only

---

## Round 12 Variable Sweeps — Fine-Tune the R11 Winner

**Script**: `run_nq_ny_variable_sweeps_12.py`
**Anchor**: g=3.0, rr=2.25, tp1=0.7, stop=9.0%, 20m ORB, entry 09:50-15:00, long-only
**Objective**: Fine-tune each variable around the R11 winner

Variables fine-tuned:
1. rr: 2.0 to 2.5 in 0.05 steps — confirmed rr=2.25
2. tp1: 0.55 to 0.80 in 0.05 steps — confirmed tp1=0.70
3. gap: 2.5 to 3.5 in 0.1 steps — confirmed gap=3.0%
4. entry_end: 14:00 to 15:30 in 15min steps — confirmed 15:00
5. stop: 8.5 to 9.5 in 0.1 steps — confirmed stop=9.0%
6. Stacked best combo — no further improvement

**Anchor fully confirmed**: g=3.0, rr=2.25, tp1=0.7, stop=9.0%, 20m ORB, entry 09:50-15:00, long-only
**Calmar (1m era)**: ~17.17 | **R/yr**: ~16.5 | **DD**: ~-10.6R

All fine-tune tests showed Δ < 0.3. Anchor stable. Proceed to structural re-validation.

---

## Round 13a Variable Sweeps — Re-validate Structural Variables

**Script**: `run_nq_ny_variable_sweeps_13a.py`
**Anchor**: g=3.0, rr=2.25, tp1=0.7, stop=9.0%, ATR 14, 20m ORB, entry 09:50-15:00, long-only
**Objective**: Re-test dimensions not swept since the anchor changed (several rounds ago)

Variables tested:
1. ORB window (5m to 30m) — last tested R3 with different stop/rr
2. ATR length (5 to 30) — last tested R1 with different config
3. Flat window (flat_start) — NEVER tested
4. max_gap_atr_pct (upper FVG size filter) — NEVER tested
5. max_gap_points — NEVER tested at this anchor
6. DOW exclusion — last tested R2-R3 with old base

**Results:**
- ORB 20m confirmed (other windows worse by >0.3 Calmar)
- ATR 14 confirmed (stable across 10-20 range)
- Flat start completely insensitive (all values ≈ same Calmar)
- max_gap_atr_pct: adding an upper filter marginally helpful but below 0.3 threshold
- max_gap_points: insensitive with gap=3% already filtering large gaps
- DOW exclusion: shifting again (Thu showed weak pattern, but below adoption threshold)

**Anchor unchanged** after R13a. Proceed to environmental filter testing.

---

## Round 13b — Environmental & Regime Filters

**Script**: `run_nq_ny_variable_sweeps_13b.py`
**Anchor**: g=3.0, rr=2.25, tp1=0.7, stop=9.0%, 20m ORB, entry 09:50-15:00, long-only
**Objective**: Test post-hoc regime filters using external daily data

Filters tested:
1. **VIX** — level buckets + SMA20/50 trend
2. **SPY** — SMA20/50/200 trend gate
3. **TNX** — yield level buckets + SMA20/50 trend
4. **DXY** — SMA20/50/200 trend
5. **NQ own SMA trend gate** — price vs SMA10/20/50/100/200
6. **ATR volatility gate** — skip days ATR > 1.0×/1.1×/1.25×/1.5× rolling SMA
7. **Month-of-year seasonality** — 12 months individually + Q1-Q4
8. **Cross-env combos** — VIX<20+SPY>SMA50, etc.

**Summary of results (1m era, informational):**

| Filter | Calmar Δ | Verdict |
|--------|----------|---------|
| NQ SMA50 trend gate | +0.2 | Rejected — below threshold; also removes ~20% of trades |
| NQ SMA200 trend gate | +0.5 | Borderline — but only activates in 2022; likely curve-fit |
| VIX < 20 | -0.1 | Rejected — longs still profitable in high-VIX |
| VIX > SMA50 | +0.3 | Borderline — largely driven by 2022 bear market period |
| SPY > SMA50 | +0.2 | Rejected — below threshold |
| SPY < SMA200 (bear) | +1.2 | Rejected — only activates in 2022 (1 year), pure curve-fit |
| ATR < 1.25× SMA20 | +0.1 | Rejected — removes volatile days that are actually profitable |
| Monthly seasonality | varied | No month consistently negative across 11 years |

**Decision**: No environmental filter adopted. The gains were either:
- Below the +0.3 threshold
- Driven by a single year (2022 bear), making them data-mining artifacts
- Removing too many trades to be statistically reliable

**Caution note from R13b output**: "Post-hoc filtering has HIGH overfitting risk with ~1100 trades. Filters that cut >30% of trades should be viewed skeptically. Best use: regime SIZING (not hard filtering)."

---

## Round 14 Variable Sweeps — Re-optimize Shorts with New Anchor

**Script**: `run_nq_ny_variable_sweeps_14.py`
**Anchor long**: g=3.0, rr=2.25, tp1=0.7, stop=9.0%, entry 09:50-15:00
**Objective**: Short-only optimization at stop=9% + combined L+S comparison

Phase A: Short sweep (rr, tp1, gap, stop, entry_end)
Phase B: Combine best long + best short (first-to-fill, one per day)
Phase C: Decision — does combined Calmar justify the DD increase?

**Best short config found**: rr=1.25, tp1=0.5, gap=1.0%, stop=9%, entry_end=14:00 (approximate — exact values depend on run output)

**Comparison (1m era, informational):**

| Config | R/yr | DD | Calmar |
|--------|------|----|--------|
| Long only (anchor) | ~16.5 | ~-10.6 | ~17.17 |
| Short only (best) | ~5-7 | ~-12 | ~4-6 |
| Combined L+S | ~18-20 | ~-13 | ~14-15 |
| Both (same params) | ~14-15 | ~-14 | ~10-11 |

**Decision**: R/yr grew ~15-20% with shorts, but DD grew ~25%. Calmar dropped. Long-only is better risk-adjusted. Shorts may add value in specific regimes (explored in R15).

---

## Round 15 Variable Sweeps — Regime-Switched L+S

**Script**: `run_nq_ny_variable_sweeps_15.py`
**Anchor long**: g=3.0, rr=2.25, tp1=0.7, stop=9.0%
**Best short**: g=1.0, rr=1.25, tp1=0.5, stop=9%, entry_end=14:00
**Objective**: Long always + short only when environmental condition favors it

Environmental conditions tested for activating shorts:
- VIX > 20, VIX > 25, VIX > SMA20, VIX > SMA50
- SPY < SMA20, SPY < SMA50, SPY < SMA200
- TNX > SMA20, TNX > SMA50
- DXY > SMA20, DXY > SMA50
- Various combinations (VIX>SMA50 + SPY<SMA50, etc.)

**Key finding**: Most regime conditions for activating shorts were driven by 2022. When a regime switch condition only activates in 1-3 years, it is unreliable for forward trading.

**Decision**: No regime-switched configuration adopted. Long-only remains the anchor.

**Caution note from R15 output**: "Any signal that only activates in 2-3 years is unreliable. Prefer signals that activate in 5+ distinct years."

---

## Final Anchor (end of 1m magnifier era)

| Parameter | Value |
|-----------|-------|
| direction | long-only |
| ORB window | 20m (09:30-09:50) |
| entry_start | 09:50 |
| entry_end | 15:00 |
| flat_start | 15:50 |
| stop_atr_pct | 9.0% |
| min_gap_atr_pct | 3.0% |
| rr | 2.25 |
| tp1_ratio | 0.7 |
| atr_length | 14 |
| magnifier | 1m (superseded — use 1s) |

**Full history Calmar (1m era)**: ~17.17 | **R/yr**: ~16.5 | **Max DD**: ~-10.6R | **Trades**: ~1,100 over 11 years

---

## Next Run: 1s Magnifier Restart

When re-optimizing on fresh data with 1s magnifier:

1. Start at or near the final anchor above as Round 1 baseline
2. Confirm bar counts and 1s parquet presence
3. Run full variable sweep sequence per the SKILL.md protocol
4. The anchor may shift slightly (1s vs 1m fill timing differs)
5. Apply the R9-R11 rule if any stop change emerges
6. Document results in a new sweep-history section appended to this file
