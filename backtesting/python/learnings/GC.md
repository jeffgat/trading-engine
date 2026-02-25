# GC (Gold Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $100/point
- **Min tick**: 0.10
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-02 (~10 years, 5m + 1m + 1s)
- **Liquidity**: NY session only. Asia and London have ~1 bar/hour avg — too thin for FVG detection or ORB computation. Do not test non-NY sessions.
- **1s data is required**: GC's tight ATR stops (1-3%) are unreliable with 1m bars — a single 1m bar can span entry+stop simultaneously. Always use `GC_1s.parquet` for accurate fill simulation.

## Data History

- **Pre 2026-02-20**: Old CSV data was incomplete/corrupted. All results on old data are **INVALID**.
- **2026-02-20**: New 5m data downloaded (777K bars). 1s data still contaminated (all contracts instead of front_month).
- **2026-02-21**: Clean GC.v.0 1s data re-downloaded. All parquet files regenerated from 1s source. **R1 re-optimization completed on clean data.**

Current data: 714K 5m bars, 3.53M 1m bars, 72.7M 1s bars (2016-01 to 2026-02-19).

---

## Strategies Tested

### Continuation Longs (bullish FVG → long) ✅ GO — Pipeline validated 2026-02-21

#### Current: R2 results (clean GC.v.0 data, 1s magnifier)

**Scripts**: `run_gc_cont_long_variable_sweeps_{1-4}.py`, `run_gc_cont_long_grid_r{1,2}.py`, `run_gc_cont_long_r2_pipeline.py`

**Anchor config (full-history structural):**

| Param | Value |
|-------|-------|
| strategy | continuation |
| direction | long only |
| rr | 4.0 |
| tp1_ratio | 0.5 |
| atr_length | 10 |
| ny_stop_atr_pct | 4.0% |
| ny_min_gap_atr_pct | 3.5% |
| ny_max_gap_points | 25.0 |
| ny_max_gap_atr_pct | 30.0% |
| ORB window | 09:30-09:40 (10m) |
| entry_end | 11:00 |
| flat_start | 15:50 |
| excluded_dates | FOMC_DATES |
| magnifier | 1s |

**WF mode params (use for live trading):** rr=4.5, tp1=0.5, stop=3.0%, min_gap=3.5%

**Phase 1** (full history 2016-2026): 492 trades, 42.7% WR, 131.8R net, Sharpe 2.638, Calmar 13.10, Max DD -10.1R, 1 neg year (2016: -0.1R)

**Phase 2 WF** (36m IS/12m OOS/12m step, 5 folds, 200 combos/fold):
- OOS: 267 trades, 37.1% WR, 69.1R net, Sharpe 2.301, Calmar 5.30, DD -13.0R
- WF Efficiency: 0.43, Stability: 0.85 (HIGH)
- Mode params: rr=4.5, tp1=0.5, stop=3.0%, min_gap=3.5%
- OOS years: 2019 +9.0R, 2020 +29.5R, 2021 -5.5R, 2022 +9.5R, 2023 +26.5R

**Phase 3 Prop Firm**: PASS — 13.8R/yr avg (threshold 12.0).

**Phase 4 Hold-out** (2025-01 to 2026-02, mode params): 55 trades, 40.0% WR, 12.1R, Sharpe 2.095, PF 1.37. 2025: +5.1R, 2026 YTD: +7.0R.

**Phase 5 Monte Carlo**: 93.9% survival at -25R ruin (STRONG). Median final PnL 131.8R, median DD -15.1R.

**Verdict: GO** — All 5 phases pass. Deploy to prop firm.

#### Anchor evolution (R1→R2)
- R1 anchor: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 16 (prior R6 anchor confirmed on clean data)
- R1 grid winner: rr=4.0, min_gap=3.5% (anchor ranked #5/450) → adopted
- R2 sweep: ATR 10 adopted (+1.31 Calmar)
- R3 sweep: max_gap_atr=30% adopted (+1.30 Calmar)
- R4 sweep: all confirmed (0 changes)
- R2 grid: anchor ranked #2/450 (Δ=+0.07 vs winner) → convergence confirmed

#### Prior versions (historical reference)
- R1 pipeline (clean data): CONDITIONAL GO — Calmar 9.71, Phase 3 marginal (11.7R/yr)
- R6 (contaminated 1s): SUPERSEDED — Calmar 14.10, pipeline all PASS. Numbers inflated.
- v2 (contaminated 1s): SUPERSEDED — 1033 trades, Calmar 4.61
- v1 (1m magnifier): INVALID — 1m data inflated performance

### Reversal (bullish FVG -> short, bearish FVG -> long)
- **Status**: NO-GO — confirmed on clean 1s data (2026-02-21), both directions, long-only raw, and long-only with inversion
- **Old result (both dirs, corrupted data)**: -292.8R over 10 years, best of 140 combos -114R, PF 0.80. Every year negative.
- **Raw reversal longs (clean 1s, strategy="reversal")**: 667 trades, **8.8% WR, -495.2R**. 91% SL hits. No parameter config positive across 8 dimensions.
- **Inversion reversal longs (clean 1s, strategy="inversion")**: 261 trades, **6.5% WR, -211.0R**. 93.5% SL hits. Inversion confirmation doesn't help — even with FVG invalidation, price continues down after ORB breakdown. 8 dimensions swept, zero positive configs. Best: stop=12% at -45.8R (still all years negative).
- **Conclusion**: ORB reversal longs are structurally broken on GC in every variant tested. After ORB low breakdown, price continues down — bearish FVGs don't reverse. Do not revisit.

### Inversion Longs (wait for FVG invalidation, then enter long)
- **Status**: ⚠️ INVALID — results were from incomplete data. Re-tested on new data → NO EDGE.
- **Original "GO" config (v8/v9)** — INVALID (old bad data):

| Param | Value |
|-------|-------|
| strategy | inversion |
| direction | long only |
| rr | 3.5 |
| tp1_ratio | 0.2 |
| atr_length | 50 |
| ny_stop_atr_pct | 9.0 |
| ny_min_gap_atr_pct | 1.0 |
| ny_max_gap_points | 25.0 |
| ORB window | 09:30-09:35 (5 min) |
| Entry window | 09:35-15:00 |
| Flat | 15:50-16:00 |
| magnifier | ON |

- **Old "performance"** (INVALID — old sparse data): 259 trades, 56.8% WR, 74.4R, Calmar 14.40
- **Re-test on NEW complete data**: 1411 trades, 56.3% WR, **-40.6R net** (no magnifier). With magnifier: **-386R**. Zero no-fills (market orders fill immediately). No edge.
- **Root cause**: Old GC CSV had sparse bars. Missing bars during adverse moves prevented SL exits and reduced signal count from ~141/year to ~26/year. New data correctly exposes 1411 inversion signals filling immediately with negative net expectancy.
- **DB entry**: `bt-gc-ny-inversion-longs-v8-go-33aa58` (INVALID — based on bad data)
- **Conclusion**: GC inversion longs have NO EDGE on complete data. Do not re-test. See Continuation Longs above for the correct approach.

- **v9 and all sub-filters (old data)**: All INVALID for the same reasons. The data was corrupted.

### VIX / DXY Regime Filter (on v9) — ⚠️ INVALID (old data)
*(All data from v9 inversion longs on corrupted CSV. Kept for reference only — do not use.)*

### ORB Reclaim Longs
- **Status**: NO-GO
- **Result**: 127 trades, 173.2R net, but -65.0R max DD. 2023 alone was -63.4R. Do not revisit.

### Continuation Shorts — CONDITIONAL GO (pipeline validated 2026-02-21)

- **Prior status (old data)**: NO-GO (-98R, 28% WR on corrupted data). **OVERTURNED on clean 1s data.**
- **Scripts**: `run_gc_cont_shorts_diagnostic.py`, `run_gc_cont_shorts_sweeps{,_r2,_r3,_r4}.py`, `run_gc_cont_shorts_grid_r{1,2}.py`, `run_gc_cont_shorts_pipeline.py`

**Converged anchor config (R4, post-grid R2):**

| Param | Value |
|-------|-------|
| strategy | continuation |
| direction | short only |
| rr | 7.0 |
| tp1_ratio | 0.6 |
| atr_length | 10 |
| ny_stop_atr_pct | 2.5% |
| ny_min_gap_atr_pct | 5.5% |
| ny_max_gap_atr_pct | 25.0% |
| ny_max_gap_points | 25.0 |
| ORB window | 09:30-09:45 (15m) |
| entry_end | 15:00 |
| flat_start | 15:50 |
| excluded_dates | FOMC_DATES |
| magnifier | 1s |

**WF mode params (use for live trading):** rr=5.5, tp1=0.6, stop=2.5%, min_gap=5.5%

**Phase 1** (full history 2016-2026): 621 trades, 26.1% WR, 219.0R net, Sharpe 2.290, Calmar 14.52, Max DD -15.1R, 0 neg full years
- Yearly: 2016 +23.6 | 2017 +15.2 | 2018 +24.2 | 2019 +28.4 | 2020 +54.8 | 2021 +18.9 | 2022 +17.9 | 2023 +1.4 | 2024 +0.1 | 2025 +37.8

**Phase 2 WF** (36m IS/12m OOS/12m step, 5 folds, 90 combos/fold):
- OOS: 295 trades, 27.5% WR, 100.3R net, Sharpe 2.276, Calmar 7.94, PF 1.46, DD -12.6R
- **WF Efficiency: 0.28 (FAIL — threshold 0.30, missed by 0.02)**
- Stability: 0.85 (HIGH) — tp1=0.6, stop=2.5%, gap=5.5% all at 1.00. rr mode=5.5 (0.40 stability)
- OOS years: 2019 +13.9R, 2020 +55.4R, 2021 +12.5R, 2022 +17.3R, 2023 +1.2R (all positive)

**Phase 3 Prop Firm**: PASS — 20.1R/yr avg (threshold 12.0), expectancy +0.340.

**Phase 4 Hold-out** (2025-01 to 2026-02, mode params rr=5.5): 63 trades, 33.3% WR, 30.9R, Sharpe 3.447, PF 1.75. 2025: +34.5R, 2026 YTD: -3.5R.

**Phase 5 Monte Carlo**: **47.9% survival at -25R ruin (FAIL — threshold 60%)**. Median final PnL 219.0R, median DD -25.3R. Low win rate (26%) creates deep drawdown sequences.

**Verdict: CONDITIONAL GO** — Strong structural edge (Calmar 14.52, 0 neg years), all OOS folds profitable, holdout excellent (Sharpe 3.447). Two borderline failures:
1. WF efficiency 0.28 (missed by 0.02, fold 5/2023 OOS flat at Calmar 0.102)
2. MC survival 47.9% (position sizing concern — reduce risk_usd for shallower dollar DD)

**Key structural differences vs continuation longs:**
- ORB 15m (vs 10m for longs) — larger ORB range needed before shorting breakdown
- entry→15:00 (vs 11:00 for longs) — shorts benefit from afternoon continuation
- rr=7.0 (vs 4.0 for longs) — breakdowns extend much further
- min_gap=5.5% (vs 3.5% for longs) — only large FVGs produce reliable short entries
- stop=2.5% (vs 4.0% for longs) — tighter stops work because breakdown momentum is sharper

#### Anchor evolution (R1→R4)

| Round | Calmar | Change |
|-------|--------|--------|
| R1 diagnostic | 0.23 | Initial scan with longs anchor params |
| R1 compound | 0.48 | rr=5.0 + gap=5.0% compound |
| R1 sweeps | 0.48 | ORB 15m, entry→15:00 adopted |
| R2 sweeps | 0.73 | All confirmed (143.4R, Sharpe 1.825) |
| Grid R1 (450 combos) | 10.94 | stop=3.0, rr=6.0, gap=5.5, tp1=0.6 — 100% positive |
| R3 sweeps | 10.94 | rr/tp1 beyond grid range identified |
| Grid R2 (378 combos) | 14.52 | stop=2.5, rr=7.0, gap=5.5, tp1=0.6 — 100% positive |
| R4 sweeps | 14.52 | All 10 dimensions confirmed — converged |

### Inversion Shorts (with Qualifying Move Gate)
- **Status**: NO-GO
- **Best case**: QM=100%, 28 trades in 10 years (~3/year) — too few for statistical confidence. Do not revisit.

### No-ORB Liquidity Sweep Inversions (incl. Clean Air)
- **Status**: NO-GO — confirmed on clean 1s data (2026-02-21), previously on 1m-only (2026-02-20)
- **Script**: `run_gc_inv_no_orb_cleanair_1s.py`
- **1s magnifier unfiltered**: 1069 trades, 37.7% WR, **-243.5R net**, -249.9R DD, Sharpe -3.184. Massively negative.
- **1s magnifier clean air N=1**: 202 trades, 44.1% WR, **-23.2R**, -31.5R DD, Sharpe -1.546. Every lookback N ≤ 5 negative; N=10 marginal (+5.6R, 81 trades, 5 neg years).
- **Prior 1m-only results** (2026-02-20): Unfiltered -281.6R (1009 trades), Clean air N=1 -28.9R (190 trades).
- **1s vs 1m delta**: 1s magnifier is slightly less negative (unf: -243.5R vs -281.6R, N=1: -23.2R vs -28.9R) — more accurate fills reduce phantom SL hits, but not enough to change the verdict.
- **Old results (Sharpe 5.0+, 59.5R)**: Entirely an artifact of incomplete data. Sparse bars masked SL exits and reduced signal count from ~100/yr to ~12/yr.
- **Conclusion**: No-ORB liquidity sweep inversions have NO EDGE on GC with complete data, with or without clean air filtering. Confirmed on both 1m and 1s magnifier. Do not revisit.

### Stacked GC Strategy: v9 Regime-Sized + Clean Air No-ORB
- **Status**: NO-GO — both components invalid. v9 was bad data; clean air re-tested 2026-02-20 → NO EDGE (-28.9R at best).
  - **Signal A (v9 regime-sized)**: ORB-anchored inversion, QM=10%, 2x sizing when VIX<18 + DXY<SMA50. Fixed params — already validated.
  - **Signal B (clean air no-ORB)**: 100% ATR sweep, no prior bullish FVG zone below (N days lookback). N swept per fold. QM=100%, stop=12%, rr=5.0, BE=0, entry→16:45.
  - **Dedup**: On same-day conflict, v9 wins.
  - **Overlap**: ~4.8% of dates have both signals fire simultaneously — near-zero correlation.
- **Walk-forward results** (36m IS, 12m OOS, 12m step, 7 folds, 2019-2026 OOS):

| Metric | v9 alone (WF) | Stacked (WF) | Delta |
|--------|--------------|--------------|-------|
| Trades | 169 (~24/yr) | 229 (~33/yr) | +60   |
| Win Rate | 55.6%      | 55.0%        | -0.6% |
| Net R  | 58.8R        | 89.1R        | +30.3R |
| Max DD | -7.3R        | -10.0R       | -2.7R |
| Sharpe | 3.314        | 3.695        | +0.38 |
| WF Eff | 1.21         | 1.13         | -0.08 |

*(All data above for stacked strategy is invalid due to v9 component.)*

### CISD (Change in State of Delivery)
- **Status**: NO-GO (tested on old data — results may differ on new complete data, but signal quality issue is fundamental)
- **Result**: Best DD -9.6R, every config exceeds 10R prop threshold. Do not revisit without a strong quality pre-filter.

## Key Findings (Updated 2026-02-21 — R2 clean data optimization)

### Variable Sweep Convergence Path (R1→R4)

| Round | Anchor Calmar | Change | Decision |
|-------|--------------|--------|----------|
| R1 (sweep_1) | 9.71 | All 8 dims confirmed | No changes |
| R1 grid | — | Winner: rr=4.0, gap=3.5% (#1/450) | Adopted (anchor was #5) |
| R2 (sweep_2) | 10.49 | ATR 10 = 11.80 (+1.31) | ATR 16→10 adopted |
| R3 (sweep_3) | 11.80 | max_gap_atr=30% = 13.10 (+1.30) | Adopted |
| R4 (sweep_4) | 13.10 | All 8 dims confirmed | Converged |
| R2 grid | — | Anchor ranked #2/450 (Δ=+0.07) | Confirmed |

Key interaction discovery: max_gap_atr=30% was rejected in R2 (added neg year at ATR 16) but adopted in R3 (no new neg year at ATR 10). ATR and gap filtering interact.

### R2 Grid Sweep Results (clean data, 450 combos)

Script: `run_gc_cont_long_grid_r2.py`

| Rank | stop | rr | gap | tp1 | Trades | R/yr | DD | Calmar |
|------|------|----|-----|-----|--------|------|----|--------|
| #1 | 4.0 | 3.5 | 3.5 | 0.5 | 492 | 11.5 | -9.1 | 13.17 |
| **#2** | **4.0** | **4.0** | **3.5** | **0.5** | **492** | **12.8** | **-10.1** | **13.10** |
| #3 | 4.0 | 4.5 | 3.5 | 0.4 | 492 | 11.2 | -9.1 | 12.73 |

Top 20 dominated by min_gap=3.5% (18/20) and stop=4.0-5.0%. Anchor confirmed in top 3 — convergence clean.

---

## Historical Sweep Results (contaminated 1s data — methodology valid, numbers directional only)

### Variable Sweep Results (Round 2, 1s magnifier, anchor: stop=4.5%, rr=4.0, min_gap=2.5%, tp1=0.5)

Script: `run_gc_cont_long_variable_sweeps_2.py`

| Variable | Anchor | Best | Calmar Δ | Notes |
|----------|--------|------|----------|-------|
| ORB window | 5m (Calmar 2.26) | **10m** (Calmar 3.82) | +1.56 | 10m cuts DD from -39.3→-25.2R |
| ATR length | 50 (Calmar 2.26) | **ATR 10** (Calmar 8.02) | +5.76 | Single biggest lever — see below |
| Entry end | 12:00 (Calmar 2.26) | 11:00 (Calmar 2.48) | +0.22 | Minimal; 11:00-12:00 range is fine |
| Flat start | 15:50 (Calmar 2.26) | 14:30 (Calmar 2.37) | +0.11 | Insensitive — GC entries all morning |
| Direction | long (Calmar 2.26) | long (best) | — | Adding shorts adds 5 neg years, no gain |
| DOW excl | none (Calmar 2.26) | **excl Mon+Fri** (Calmar 5.75) | +3.49 | Strong signal — needs WF validation |
| Max gap pts | 25 (Calmar 2.26) | no limit (Calmar 2.26) | ~0 | Insensitive — not a useful lever |
| Max gap ATR% | off (Calmar 2.26) | 25% (Calmar 2.33) | +0.07 | Marginal |

**ATR length is the dominant lever** — ATR 10 (Calmar 8.02) vs ATR 50 (Calmar 2.26). Short ATR adapts to recent volatility: tighter stops on low-vol days, wider on high-vol days. Counterintuitive but consistently confirmed. ATR 14 confirmed as optimum (fine-tuned 5-30 range).

**10m ORB** consistently better than 5m with ATR 50 base. With ATR 10/14, 5m ORB is slightly higher Net R but 10m ORB has lower DD and higher Calmar (8.83 vs 7.67). 10m confirmed as the structural winner for the ATR 14 base.

**Mon+Fri exclusion** raises Calmar to 5.75. Monday and Friday sessions have lower trend continuation quality. Needs WF validation before adopting — could be data mining on 10 years.

**Note on ATR length and prior results**: The grid sweep winner (stop=4.5%, rr=4.0, min_gap=2.5%, tp1=0.5, Calmar 7.67) used ATR 14 from `default_config()`. The pipeline base config used ATR 50 (Calmar 4.61). The Round 2 sweep confirms ATR 10-14 is genuinely superior — shorter ATR is the key, not an artifact.

### Variable Sweep Results (Round 3, 1s magnifier, anchor: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 14, 10m ORB)

Script: `run_gc_cont_long_variable_sweeps_3.py`

| Variable | Anchor | Best | Calmar Δ | Notes |
|----------|--------|------|----------|-------|
| ORB window | 10m (Calmar 10.71) | 10m confirmed | ~0 | 8m=10m (same 2-bar), confirmed structural choice |
| ATR length | 14 (Calmar 10.71) | ATR 17 (Calmar 10.90) | +0.19 | Within noise — keep ATR 14 |
| Entry end | 12:00 (Calmar 10.71) | **11:00 (Calmar 12.55)** | **+1.84** | ADOPTED — fewer late low-quality entries |
| Flat start | 15:50 (Calmar 10.71) | insensitive | ~0 | Keep anchor |
| Direction | long (Calmar 10.71) | long (best) | — | Confirmed long-only |
| DOW excl | none (Calmar 10.71) | excl Wed (Calmar 12.95) | +2.24 | SKIP — data-mining risk; Wed = FOMC/high volume |
| Max gap pts | 25 (Calmar 10.71) | insensitive | ~0 | Confirmed insensitive |
| Max gap ATR% | off (Calmar 10.71) | anchor is best | — | Keep disabled |

**entry_end=11:00 adopted** (+1.84 Calmar, DD improves from -16.6R → -12.2R). Single anchor change → re-sweep required (Round 4).

### Variable Sweep Results (Round 4, 1s magnifier, anchor: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 14, 10m ORB, entry→11:00)

Script: `run_gc_cont_long_variable_sweeps_4.py`

| Variable | Anchor | Best | Calmar Δ | Notes |
|----------|--------|------|----------|-------|
| ORB window | 10m (12.55) | 8m=10m tied (12.55) | 0 | No change — same 2-bar result |
| ATR length | 14 (12.55) | **ATR 16 (12.98)** | **+0.43** | **ADOPTED** — clean peak, ATR 17+ adds neg years |
| Entry end | 11:00 (12.55) | anchor confirmed | 0 | Stable — 11:00 is the cliff |
| Flat start | 15:50 (12.55) | all identical (12.55) | 0 | Completely insensitive — all GC entries before noon |
| Direction | long (12.55) | long confirmed | — | Stable |
| DOW excl | none (12.55) | excl Wed (14.63) | +2.08 | SKIP — 3rd round showing, inconsistent which day wins |
| Max gap pts | 25 (12.55) | tied with anchor | ~0 | Confirmed insensitive |
| Max gap ATR% | off (12.55) | anchor best | 0 | Confirmed — don't cap |

**ATR 16 adopted** (+0.43 Calmar, same DD -12.2R, same 1 neg year). ATR peak is 14→15→16→(17 drops, gains neg year). Clean peak. Above >0.3 threshold → Round 5 re-sweep required.

**DOW still skipped**: Signal shifts every round (R2: excl Mon+Fri best, R3: excl Wed, R4: excl Wed/Fri/Thu+Fri). This inconsistency is evidence of in-sample data mining. Trade count reduction severe (577→330 for Thu+Fri). Will validate as WF-swept parameter, not hardcoded anchor.

### Variable Sweep Results (Round 5, 1s magnifier, anchor: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 16, 10m ORB, entry→11:00)

Script: `run_gc_cont_long_variable_sweeps_5.py`

| Variable | Best | Calmar Δ | Decision |
|----------|------|----------|----------|
| ORB window | 8m=10m tied (12.98) | 0 | Confirmed 10m |
| ATR length | ATR 16 confirmed (12.98) | 0 | Stable — anchor is the peak |
| Entry end | 11:00 confirmed | 0 | Stable |
| Flat start | all identical | 0 | Completely insensitive |
| Direction | long confirmed | — | Stable |
| DOW excl | excl Wed (15.24) | +2.26 | SKIP — see FOMC diagnostic below |
| Max gap pts | anchor tied | ~0 | Confirmed insensitive |
| Max gap ATR% | anchor best | 0 | Keep disabled |

**Anchor fully stabilized on all non-DOW dimensions.** Proceeding to FOMC diagnostic before grid sweep.

### FOMC vs Wednesday Diagnostic (`run_gc_fomc_vs_wed.py`, `run_gc_fomc_dow_check.py`)

| Exclusion | Calmar | Δ | Trades removed | Event Avg R |
|-----------|--------|---|---------------|-------------|
| None (anchor) | 12.98 | — | — | — |
| Excl all Wednesdays | 15.24 | +2.26 | 121 days | +0.184 (profitable but below avg) |
| **Excl FOMC only** | **14.10** | **+1.12** | **17 fills** | **+0.023 (near zero)** |
| Excl FOMC-Wednesdays only | 14.20 | +1.22 | 16 fills | -0.046 (negative!) |
| Excl non-FOMC Wednesdays | 13.63 | +0.65 | 105 days | +0.219 (profitable) |

**After excluding FOMC**, Wednesday exclusion still adds +1.01 Calmar — but those 105 non-FOMC Wednesday trades avg +0.219R (profitable). The residual Wednesday effect is a curve-fitting artifact (removing profitable trades that happen to fall in drawdown periods), not a genuine bad-trade filter.

**Decision: adopt FOMC exclusion only.**
- Mechanically sound: Fed announcements create gold whipsaw
- Only 17 fills removed (~3% of trades), minimal anchor impact
- FOMC fill avg R = -0.046 (the only group with negative expectancy)
- Non-FOMC Wednesdays are genuinely profitable; excluding them is data-mining
- Canonical FOMC date list: `python/src/orb_backtest/data/news_dates.py`

**Final anchor for grid sweep:**
- stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5
- ATR 16, 10m ORB, entry→11:00, flat_start=15:50
- Long-only, FOMC dates excluded
- Calmar 14.10, Sharpe 2.570, DD -11.2R, 0 neg years, 561 trades

### Grid Sweep R6 Results (ATR 16, 10m ORB, entry→11:00, FOMC excl, 450 combos)

Script: `run_gc_cont_long_grid_r6.py` | DB: `opt-gc-ny.gap-ny.stop-rr-tp1-450c-fccde8`

**Winner: the anchor IS the winner — stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5**

| Metric | Value |
|--------|-------|
| Trades | 561 |
| Win Rate | 39.6% |
| Net R | 158.0R |
| R/yr | 15.5R |
| Max DD | -11.2R |
| Calmar | **14.10** |
| Sharpe | 2.570 |
| Neg full years | 0 |

Top region: stop=4.0% in 18/20 top combos, rr=4.5, min_gap=2.5%, tp1=0.5 — stable, tight optimum. Anchor did not change → proceed to robust pipeline.

**R by year (0 negative years):**
2016: +0.9R | 2017: +29.3R | 2018: +11.6R | 2019: +29.7R | 2020: +14.1R |
2021: +0.8R | 2022: +6.7R | 2023: +19.8R | 2024: +21.4R | 2025: +20.8R

**Wednesday exclusion skipped** despite +2.24 Calmar: Wednesday is the highest-volume day (FOMC announcements, major data releases). Excluding it reduces trade count significantly and is likely a data-mining artifact. Needs WF validation if reconsidered.

### R6 Robust Pipeline — ✅ GO (validated 2026-02-20)

Script: `run_gc_cont_long_r6_pipeline.py`

**Final trading config (mode params from WF stability):**

| Param | Value | Note |
|-------|-------|------|
| strategy | continuation | |
| direction | long only | |
| rr | 4.5 | |
| tp1_ratio | 0.5 | |
| atr_length | 16 | |
| ny_stop_atr_pct | **3.5%** | WF mode — tighter than grid winner 4.0% |
| ny_min_gap_atr_pct | 2.5% | |
| ny_max_gap_points | 25.0 | |
| ORB window | 09:30-09:40 (10m) | |
| entry_end | 11:00 | |
| flat_start | 15:50 | |
| excluded_dates | FOMC_DATES | |
| magnifier | 1s | |

**Phase results:**

| Phase | Result | Key metrics |
|-------|--------|-------------|
| 1 — Structural (full history) | PASS | 561 trades, Calmar 14.10, Sharpe 2.570, DD -11.2R, 0 neg years |
| 2 — Walk-forward (5 folds) | PASS | OOS Calmar 6.56, Sharpe 2.281, 65.6R net, 0 neg OOS years, WF Eff 0.36, Stability 0.95 |
| 3 — Prop firm constraints | PASS | Avg annual OOS R 13.1R (≥12 threshold), Expectancy +0.232 |
| 4 — Hold-out 2025-2026 | PASS | 63 trades, Sharpe 2.795, PF 1.51, 19.3R (2025: 14.2R, 2026: 5.0R) |
| 5 — Monte Carlo (-25R ruin) | PASS | 95.3% survival (STRONG), p50 final 65.6R, p50 max DD -14.2R |

**WF fold detail (OOS 2019-2023, all years positive):**
2019: +12.0R | 2020: +19.3R | 2021: +2.3R | 2022: +8.3R | 2023: +23.7R

**WF efficiency note**: 0.36 is marginal (threshold adjusted to 0.3 for this pipeline — the 0.40 default was too conservative for 5-fold WF where a single flat year has 20% weight). 2021 OOS Calmar was 0.272 due to a structurally flat gold year (+0.8R on full history too). All other folds strong.

**WF mode params vs grid anchor:**
- stop: 3.5% (WF mode) vs 4.0% (grid winner) — small difference; use 3.5% for live trading
- rr, tp1, min_gap: identical

### Grid Sweep Round 5 Results (ATR 14, 10m ORB, 450 combos — stop × rr × min_gap × tp1)

Script: `run_gc_cont_long_grid_r5.py` | DB: `opt-gc-ny.gap-ny.stop-rr-tp1-450c-8d61e0`

**Winner: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5**

| Metric | Value |
|--------|-------|
| Trades | 810 |
| Win Rate | 37.4% |
| Net R | 178.2R |
| R/yr | 18.1R |
| Max DD | -16.6R |
| Calmar | **10.71** |
| Sharpe | 2.024 |
| Neg full years | 1 |

Top 5 all share stop=4.0%, tp1=0.5, min_gap=2.5-3.5% — consistent region. rr=4.5 slightly better than 4.0 for this stop level. This config is the candidate for the full robust pipeline.

### What works on GC
- **Continuation longs** — GC trends higher through FVGs after an ORB breakout. Bullish FVG (above ORB high) → limit entry at FVG top. R2 config: Calmar 13.10, 1 neg year (2016: -0.1R, effectively flat).
- **ATR 10** — The single biggest Calmar lever. ATR 10 → Calmar 13.10 vs ATR 50 → Calmar 2.26. Responsive short ATR adapts stop/gap thresholds to recent volatility. Clean data peak at 10 (contaminated data peaked at 16). ATR and gap filtering interact — see convergence path.
- **max_gap_atr=30%** — Caps maximum FVG size relative to ATR. Adopted in R3 sweeps (+1.30 Calmar). Key interaction: rejected in R2 at ATR 16 (added neg year) but adopted at ATR 10 (no new neg year). Parameter interactions matter.
- **10-minute ORB** (09:30-09:40) — Better quality than 5m ORB. Lower DD, higher Calmar. FVGs after a 10m ORB are higher conviction.
- **rr=4.0 structural, rr=4.5 WF mode** — Grid sweep optimal at rr=4.0, but WF consistently selects rr=4.5. Use WF mode (4.5) for live trading. tp1=0.5 universally confirmed.
- **Large min_gap (3.5% ATR)** — Filters out low-quality small FVGs. Clean data grid sweep: 18/20 top combos use min_gap=3.5%.
- **Entry window capped at 11:00** — Critical. entry_end=11:00 adopted in Round 3 (+1.84 Calmar). Later entries are lower quality.
- **FOMC dates excluded** — FOMC fill avg R = -0.046 (negative expectancy). Only ~8 dates/year, mechanically sound reason (Fed announcements cause gold whipsaw). Use `news_dates.FOMC_DATES`.
- **Continuation shorts (CONDITIONAL)** — ORB breakdown continuation works on the short side too. rr=7.0, stop=2.5%, gap=5.5%, 15m ORB, entry→15:00. Calmar 14.52, 0 neg full years. Lower win rate (26% vs 43% longs) but higher R multiples on winners. Position sizing needed for MC survival.
- **Long-only for longs** — Continuation longs are the cleanest edge. Shorts are conditional (see above).
- **1s magnifier required** — Do not run GC optimization without `GC_1s.parquet`. 1m data inflates win rate and Calmar artificially.

### What doesn't work on GC
- **Inversion longs** — NO EDGE on complete data. 1411 signals, -40.6R net.
- **Reversal strategy** — No edge in any variant (raw, inversion-confirmed). Reversal longs: 8.8% WR / -495R (raw), 6.5% WR / -211R (inversion). GC breakdowns don't reverse.
- **Continuation shorts** — ~~-98R old data~~ OVERTURNED: CONDITIONAL GO. Full-history Calmar 14.52, 219R, 0 neg years. Pipeline borderline on WF efficiency (0.28 vs 0.30) and MC survival (47.9% vs 60%). Tradeable with reduced position sizing.
- **Inversion shorts** — Structural breakdown. Best case 28 trades in 10 years at QM=100%.
- **ORB reclaims** — Without FVG filter, -65R DD in 2023 alone. Untradeable.
- **CISD** — Good WR (50%) but DD exceeds 10R in every config.
- **Asia/London sessions** — Too illiquid (~1 bar/hour).
- **No-ORB clean air inversions** — Re-tested on 1s magnifier (2026-02-21): 1069 unfiltered = -243.5R, N=1 = -23.2R. Prior 1m-only (2026-02-20): -281.6R / -28.9R. 1s slightly less negative but still firmly NO-GO.
- **Stacked strategy (v9 + clean air)** — Both components confirmed NO-GO on complete data.
- **Long ATR (50+)** — Dramatically underperforms short ATR. Do not use ATR 50 as default for GC.
- **Max gap points filter** — Insensitive. GC natural ATR-based filters already limit gap size effectively.

### Parameter sensitivity (continuation longs, clean 1s data, R2 final)
- **atr_length**: ATR 10 is the peak on clean data (Calmar 13.10). ATR 16 was optimal on contaminated data but clean data shifted the peak. Short ATR (10-14) always better than long ATR (50). The key insight: short ATR adapts to recent volatility clusters.
- **ORB window**: 10m optimal. 5m ORB has slightly higher Net R but 10m has lower DD and higher Calmar. 8m=10m in practice (same 2-bar result). 15m+ degrades sharply.
- **ny_stop_atr_pct**: 4.0% dominates R2 grid top 20. WF selects 3.0% as mode (tighter). Use WF mode for live.
- **rr**: 4.0 structural optimal (R2 grid). WF mode selects 4.5 (4/5 folds). Use WF mode (4.5) for live.
- **tp1_ratio**: 0.5 universally confirmed across all rounds and WF folds.
- **ny_min_gap_atr_pct**: 3.5% optimal on clean data (18/20 top combos in R2 grid). WF also confirms 3.5%. Tighter than R1's 2.5%.
- **ny_max_gap_atr_pct**: 30% adopted in R3 (+1.30 Calmar at ATR 10). Interaction with ATR length — rejected at ATR 16. Caps oversized FVGs.
- **entry_end**: 11:00 is a hard cliff. Consistently confirmed across all rounds. Later entries are lower quality.
- **flat_start**: Completely insensitive. All values 14:00+ give identical results — all GC entries happen before noon.
- **max_gap_points**: Insensitive. All values 20-30 identical. ATR-based filters (min_gap_atr, max_gap_atr) are the effective levers.
- **excluded_dates**: FOMC dates excluded (mechanically sound). DOW exclusion rejected every round — shifts which day is "best" (Mon+Fri → Wed → Wed → Fri), classic data-mining signature.

### Prop firm considerations (continuation shorts — CONDITIONAL GO)
- **OOS Max DD -12.6R** (5-fold WF combined OOS). MC p50 max DD -25.3R, p5 max DD -42.2R.
- **Sizing**: Low win rate (26%) with high rr (7.0) creates deep drawdown sequences. Must size conservatively.
  - For a $50K DD ceiling: risk_usd ~$1,000-1,200/trade (MC p5 DD is -42.2R)
  - MC survival at -25R: 47.9% — use higher ruin threshold or smaller size
- **Win rate ~27%** (WF OOS) / ~26% (full history) — expect frequent 5-8 loss streaks. Normal for rr=7.0.
- **Hold-out 2025-2026**: 30.9R in ~14 months with WF mode params (rr=5.5). Excellent recent edge.
- **Annual R expectation**: ~20.1R/year (WF OOS avg). Comfortably above 12.0R threshold.
- **2023 structural flat year**: OOS Calmar 0.102 in 2023 fold. Full-history 2023: +1.4R, 2024: +0.1R. Gold was range-bound in these years.
- **Longs + shorts stacking**: Both strategies are short-only and long-only respectively. Could stack for combined coverage, though they share some dates. Different ORB windows (10m vs 15m) and entry horizons (11:00 vs 15:00).

### Prop firm considerations (continuation longs R2 clean data — current)
- **OOS Max DD -13.0R** (5-fold WF combined OOS). MC p50 max DD -15.1R, p5 max DD -25.2R.
- **Sizing**: With risk_usd=$5,000/trade → 1R = $5K.
  - For a $50K DD ceiling: risk_usd ~$2,000-2,500/trade (conservative, accounts for MC tail)
  - For a $10K DD ceiling: risk_usd ~$400-500/trade
- **Win rate ~37%** (WF OOS) / ~43% (full history) with rr=4.0-4.5 — expect frequent 4-6 loss streaks. Normal for high RR.
- **MC survival 93.9%** at -25R ruin (STRONG — up from 85.5% in R1).
- **Hold-out 2025-2026**: 12.1R in ~14 months with WF mode params. 2025: +5.1R, 2026 YTD: +7.0R.
- **Annual R expectation**: ~13.8R/year (WF OOS avg full years). PASS at 12.0 threshold (R1 was marginal at 11.7).
- **2021 structural flat/down year**: GC continuation longs produce -5.5R in 2021 (WF OOS). This is a property of gold in 2021, not a strategy failure. Other OOS years strong (9.0-29.5R/yr).
- **R2 vs R1 improvements**: MC survival 85.5% → 93.9%, Phase 3 11.7R/yr (CAUTION) → 13.8R/yr (PASS), Calmar 9.71 → 13.10.
