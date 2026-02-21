# GC Optimization Sweep History

Full anchor evolution log across all optimization rounds.

## Data Timeline

- **Pre-2026-02-20**: All results produced on contaminated 1s data (included all GC contracts, not front-month only). These are preserved below as "Historical Rounds" for methodology reference but all numbers are invalid.
- **2026-02-20**: Re-downloaded GC data using `.v.0` (volume roll). Clean data validated: 72.7M 1s bars, 714K 5m bars, no duplicates, correct price levels.
- **2026-02-21**: R1 optimization completed on clean data.

---

## R1 — Clean Data Re-Optimization (2026-02-21)

### R1 Variable Sweeps

**Script**: `run_gc_cont_long_variable_sweeps_1.py`
**Anchor entering round**: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 16, 10m ORB, entry→11:00, FOMC excluded
**Anchor Calmar**: 9.71 (559 trades, 39.4% WR, 151.2R net, Sharpe 2.479)

| Variable | Anchor Calmar | Best | Calmar Δ | Decision |
|----------|--------------|------|----------|----------|
| ORB window | 9.71 | 10m (anchor) | 0 | Confirmed |
| ATR length | 9.71 | ATR 16 (anchor) | 0 | Confirmed |
| Entry end | 9.71 | 11:00 (anchor) | 0 | Confirmed |
| Flat start | 9.71 | all identical | 0 | Completely insensitive |
| Direction | 9.71 | long (anchor) | — | Confirmed long-only |
| DOW excl | 9.71 | excl Fri (+3.10) | +3.10 | Skip — decomposed below |
| Max gap pts | 9.71 | insensitive | ~0 | Confirmed |
| Max gap ATR% | 9.71 | anchor is best | 0 | Keep disabled |

**All 8 dimensions confirmed anchor — no changes.** Convergence in 1 round.

### Friday Decomposition Diagnostic

Friday exclusion showed +3.10 Calmar. Decomposed by NFP status:
- **NFP Fridays**: avg R = +0.257 (profitable, do NOT exclude)
- **Non-NFP Fridays**: avg R = -0.103 (weak, but no mechanical explanation)
- **Decision**: Do NOT adopt Friday exclusion — data-mining risk with no structural basis. The prior contaminated-data rounds showed DOW exclusion shifting every round (Mon+Fri → Wed → Wed → Fri), confirming it's unstable.

### R1 Grid Sweep

**Script**: `run_gc_cont_long_grid_r1.py`
**Grid**: stop(6) × rr(5) × min_gap(5) × tp1(3) = 450 combos
**Ranges**: stop=[3.0-5.5], rr=[3.0-5.0], min_gap=[1.5-3.5], tp1=[0.3-0.5]

**Top 5 by Calmar**:

| stop | rr | gap | tp1 | Trd | WR | PF | Net R | R/yr | MaxDD | Calmar | Sharpe | NegYr |
|------|-----|-----|-----|-----|------|------|-------|------|-------|--------|--------|-------|
| 4.0 | 4.0 | 3.5 | 0.5 | 498 | 41.0% | 1.39 | 115.9 | 11.1 | -11.0 | 10.49 | 2.286 | 1 |
| 4.0 | 4.5 | 1.5 | 0.5 | 635 | 37.0% | 1.33 | 134.1 | 12.9 | -12.9 | 10.40 | 1.943 | 1 |
| 4.5 | 3.5 | 3.5 | 0.5 | 498 | 43.8% | 1.38 | 106.9 | 10.3 | -10.4 | 10.28 | 2.276 | 1 |
| 4.0 | 3.5 | 3.0 | 0.5 | 529 | 43.3% | 1.34 | 103.2 | 9.9 | -10.1 | 10.19 | 2.082 | 1 |
| **4.0** | **4.5** | **2.5** | **0.5** | **559** | **39.4%** | **1.44** | **151.2** | **14.9** | **-15.6** | **9.71** | **2.479** | **1** |

- **Grid winner**: stop=4.0, rr=4.0, gap=3.5, tp1=0.5 (Calmar 10.49)
- **Anchor rank**: #5 of 450 (Calmar 9.71)
- Top 20 dominated by stop=4.0% — confirms variable sweep finding

### R1 Robust Pipeline

**Script**: `run_gc_cont_long_r1_pipeline.py`
**WF**: 36m IS / 12m OOS / 12m step, 5 folds, 160 combos/fold

| Phase | Result | Key Numbers |
|-------|--------|-------------|
| 1 — Structural | PASS | 559 trades, Calmar 9.71, Sharpe 2.479, 1 neg year |
| 2 — Walk-Forward | PASS | WF Eff 0.33, Stability 0.95 (HIGH) |
| 3 — Prop Constraints | CAUTION | 11.7 R/yr (vs 12.0 threshold) — 2021 flat year drags avg |
| 4 — Hold-Out OOS | PASS | 63 trades, 19.3R, Sharpe 2.795 (2025-01 → 2026-02) |
| 5 — Monte Carlo | PASS | 85.5% survival at -25R ruin (STRONG) |

**WF mode params** (use for live trading): rr=4.5, tp1=0.5, stop=3.5%, min_gap=2.5%

**Verdict: CONDITIONAL GO**
- Phase 3 marginal (11.7R/yr vs 12.0 threshold) due to 2021 structural flat year (-1.9R)
- All other phases strong, especially MC survival (85.5%) and WF stability (0.95)
- Tradeable with slight position size reduction

---

## Historical Rounds (Contaminated 1s Data — Numbers Invalid)

> **Warning**: All results below were produced with contaminated 1s data (included all GC contracts, not front-month only). The methodology and decision rationale are preserved for reference, but Calmar, Sharpe, Net R, and drawdown numbers should not be used as performance targets.

### Starting Point: v2 Pipeline Baseline

**Anchor**: stop=4.5%, rr=3.0, min_gap=1.0%, tp1=0.3, ATR 50, 5m ORB, entry→12:00

This was the `default_config()` starting point before any GC-specific tuning. The pipeline ran WF and produced a mode config that worked but was suboptimal. The variable sweep program was started to find a better structural anchor.

### Round 2 Variable Sweeps

**Script**: `run_gc_cont_long_variable_sweeps_2.py`
**Anchor entering round**: stop=4.5%, rr=4.0, min_gap=2.5%, tp1=0.5, ATR 50, 5m ORB, entry→12:00
**Anchor Calmar**: 2.26

| Variable | Anchor Calmar | Best | Calmar Δ | Decision |
|----------|--------------|------|----------|----------|
| ORB window | 2.26 | 10m (3.82) | +1.56 | **ADOPTED** — 10m cuts DD from -39→-25R |
| ATR length | 2.26 | ATR 10 (8.02) | **+5.76** | **ADOPTED** — dominant lever; fine-tuned to ATR 14 |
| Entry end | 2.26 | 11:00 (2.48) | +0.22 | Skip — below 0.3 threshold |
| Flat start | 2.26 | 14:30 (2.37) | +0.11 | Skip — insensitive |
| Direction | 2.26 | long (best) | — | Confirmed long-only |
| DOW excl | 2.26 | excl Mon+Fri (5.75) | +3.49 | Skip — needs WF validation |
| Max gap pts | 2.26 | no limit (2.26) | ~0 | Confirmed insensitive |
| Max gap ATR% | 2.26 | 25% (2.33) | +0.07 | Skip — marginal |

**Anchor exiting round**: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 14, 10m ORB, entry→12:00

**Key insight**: Short ATR (10-18) is the single largest lever in GC optimization. ATR 50 applies yesterday's volatility estimate to today's stops — GC's volatility clusters mean ATR 14/16 is far more responsive.

### Round 3 Variable Sweeps

**Script**: `run_gc_cont_long_variable_sweeps_3.py`
**Anchor Calmar**: 10.71

Key change: **entry_end=11:00 ADOPTED** (+1.84 Calmar) — hard cliff, late entries poor quality.

### Round 4 Variable Sweeps

**Script**: `run_gc_cont_long_variable_sweeps_4.py`
**Anchor Calmar**: 12.55

Key change: **ATR 16 ADOPTED** (+0.43 Calmar) — clean peak at 16, ATR 17 adds negative year.

**DOW pattern observation**: Best DOW exclusion shifted every round — R2: Mon+Fri, R3: Wed, R4: Wed again. Classic data-mining signature.

### Round 5 Variable Sweeps

**Script**: `run_gc_cont_long_variable_sweeps_5.py`
**Anchor Calmar**: 12.98

All dimensions confirmed anchor — 2 consecutive stable rounds. Triggered FOMC diagnostic.

### FOMC vs Wednesday Diagnostic

Decomposed Wednesday exclusion by FOMC status:
- FOMC fills: negative avg R (-0.046) — the problem trades
- Non-FOMC Wednesday: positive avg R (+0.219) — profitable, don't exclude
- **Decision**: FOMC exclusion only (mechanically sound)

### Grid Sweep R6

Anchor IS the grid winner (stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5). Clean convergence.

### Robust Pipeline R6

All 5 phases passed on contaminated data. WF mode params: stop=3.5%, rr=4.5, tp1=0.5, min_gap=2.5%.
**Results invalidated** — must use R1 clean-data pipeline results above.
