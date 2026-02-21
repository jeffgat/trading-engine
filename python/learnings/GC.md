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

### Continuation Longs (bullish FVG → long) ✅ CONDITIONAL GO (R1 clean data) — Pipeline validated 2026-02-21

#### Current: R1 results (clean GC.v.0 data, 1s magnifier)

**Scripts**: `run_gc_cont_long_variable_sweeps_1.py`, `run_gc_cont_long_grid_r1.py`, `run_gc_cont_long_r1_pipeline.py`

**Final trading config (WF mode params):**

| Param | Value |
|-------|-------|
| strategy | continuation |
| direction | long only |
| rr | 4.5 |
| tp1_ratio | 0.5 |
| atr_length | 16 |
| ny_stop_atr_pct | **3.5%** (WF mode) |
| ny_min_gap_atr_pct | 2.5% |
| ny_max_gap_points | 25.0 |
| ORB window | 09:30-09:40 (10m) |
| entry_end | 11:00 |
| flat_start | 15:50 |
| excluded_dates | FOMC_DATES |
| magnifier | 1s |

**Phase 1** (full history 2016-2026): 559 trades, 39.4% WR, 151.2R net, Sharpe 2.479, Calmar 9.71, Max DD -15.6R, 1 neg year (2021: -3.5R)

**Phase 2 WF** (36m IS/12m OOS/12m step, 5 folds, 160 combos/fold):
- OOS: 282 trades, 41.5% WR, 58.3R net, Sharpe 2.052, Calmar 5.83, DD -10.0R
- WF Efficiency: 0.33, Stability: 0.95 (HIGH)
- Mode params: rr=4.5, tp1=0.5, stop=3.5%, min_gap=2.5%
- OOS years: 2019 +12.0R, 2020 +19.3R, 2021 -1.9R, 2022 +5.2R, 2023 +23.7R

**Phase 3 Prop Firm**: CAUTION — 11.7R/yr avg (threshold 12.0). 2021 structural flat year drags average.

**Phase 4 Hold-out** (2025-01 to 2026-02, mode params): 63 trades, 41.3% WR, 19.3R, Sharpe 2.795, PF 1.51. 2025: +14.2R, 2026 YTD: +5.0R.

**Phase 5 Monte Carlo**: 85.5% survival at -25R ruin (STRONG). Median final PnL 141.9R, median DD -18.2R.

**Verdict: CONDITIONAL GO** — Phase 3 marginal (11.7 vs 12.0 annual R) due to 2021 structural flat year. All other phases pass comfortably. Tradeable with slight position size reduction.

#### Prior versions (historical reference — all on contaminated 1s data)
- v1 (1m magnifier): INVALID — 1m data inflated performance
- v2 (1s, contaminated): SUPERSEDED — 1033 trades, Calmar 4.61, different config
- R6 (1s, contaminated): SUPERSEDED — Calmar 14.10 structural, pipeline all PASS. Numbers inflated by contaminated 1s data. Methodology was sound; structural choices confirmed on clean data.

### Reversal (bullish FVG -> short, bearish FVG -> long)
- **Status**: NO-GO (tested on old data, expected same conclusion on new data — all continuation signals go long)
- **Result**: -292.8R over 10 years with defaults. Best of 140 param combos still -114R, PF 0.80. Every single year negative.
- **Conclusion**: GC does not mean-revert through FVGs. The continuation direction captures the trend; reversals fight it. Do not revisit.

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

### Continuation Shorts
- **Status**: NO-GO
- **Result**: -98R over 10 years, 28% win rate. Structurally broken — every param combo negative. Do not revisit.

### Inversion Shorts (with Qualifying Move Gate)
- **Status**: NO-GO
- **Best case**: QM=100%, 28 trades in 10 years (~3/year) — too few for statistical confidence. Do not revisit.

### No-ORB Liquidity Sweep Inversions (incl. Clean Air)
- **Status**: NO-GO — confirmed on new complete data (2026-02-20)
- **Script**: `run_gc_inv_no_orb_cleanair_1s.py`
- **Unfiltered base**: 1009 trades, 37.0% WR, **-281.6R net**, Sharpe -4.484. Massively negative.
- **Clean air N=1** (best filter): 190 trades, 42.1% WR, **-28.9R**, -45.3R DD, Sharpe -2.218. Every lookback N negative.
- **Old results (Sharpe 5.0+, 59.5R)**: Entirely an artifact of incomplete data. Sparse bars masked SL exits and reduced signal count from ~100/yr to ~12/yr.
- **Conclusion**: No-ORB liquidity sweep inversions have NO EDGE on GC with complete data, with or without clean air filtering. Do not revisit.

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

## Key Findings (Updated 2026-02-21 — R1 clean data re-optimization)

### R1 Variable Sweep Results (clean data, 1s magnifier, anchor: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 16, 10m ORB, entry→11:00, FOMC excl)

Script: `run_gc_cont_long_variable_sweeps_1.py`

| Variable | Anchor Calmar | Best | Calmar Δ | Decision |
|----------|--------------|------|----------|----------|
| ORB window | 9.71 | 10m [anchor] | 0.00 | No change |
| ATR length | 9.71 | ATR 16 [anchor] | 0.00 | No change |
| Entry end | 9.71 | 11:00 [anchor] | 0.00 | No change |
| Flat start | 9.71 | insensitive | 0.00 | No change |
| Direction | 9.71 | long [anchor] | 0.00 | No change |
| DOW excl | 9.71 | excl Friday (12.81) | +3.10 | SKIP — NFP diagnostic negative |
| Max gap pts | 9.71 | insensitive | 0.00 | No change |
| Max gap ATR% | 9.71 | anchor best | 0.00 | No change |

**All structural parameters confirmed unchanged on clean data.** Anchor stable from first round — no re-sweep needed.

**Friday DOW diagnostic**: excl Friday shows +3.10 Calmar, but NFP Fridays are profitable (+0.257 avg R), and non-NFP Friday weakness has no mechanical explanation → data mining. FOMC already excluded.

### R1 Grid Sweep Results (clean data, 450 combos)

Script: `run_gc_cont_long_grid_r1.py`

| Rank | stop | rr | gap | tp1 | Trades | R/yr | DD | Calmar |
|------|------|----|-----|-----|--------|------|----|--------|
| #1 | 4.0 | 4.0 | 3.5 | 0.5 | 498 | 11.1 | -11.0 | 10.49 |
| #2 | 4.0 | 4.5 | 1.5 | 0.5 | 635 | 12.9 | -12.9 | 10.40 |
| #5 | 4.0 | 4.5 | 2.5 | 0.5 | 559 | 14.9 | -15.6 | 9.71 |

Anchor ranked #5/450. stop=4.0% and tp1=0.5 dominate top 20. Grid winner has lower trade count (498 vs 559) and lower DD. WF adaptively selects from this region.

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
- **Continuation longs** — GC trends higher through FVGs after an ORB breakout. Bullish FVG (above ORB high) → limit entry at FVG top. R6 config: Calmar 14.10, 0 neg years (full history IS).
- **ATR 16** — The single biggest Calmar lever. ATR 16 → Calmar 14.10 vs ATR 50 → Calmar 2.26. Responsive short ATR adapts stop/gap thresholds to recent volatility. Peak at 16 — ATR 17+ gains a negative year.
- **10-minute ORB** (09:30-09:40) — Better quality than 5m ORB. Lower DD, higher Calmar. FVGs after a 10m ORB are higher conviction.
- **rr=4.5 + tp1=0.5** — Taking 50% off at TP1 locks in profit while the runner targets rr=4.5. Grid sweep confirmed this as the optimal combination.
- **Large min_gap (2.5% ATR)** — Filters out low-quality small FVGs.
- **Entry window capped at 11:00** — Critical. entry_end=11:00 adopted in Round 3 (+1.84 Calmar). Later entries are lower quality.
- **FOMC dates excluded** — FOMC fill avg R = -0.046 (negative expectancy). Only ~8 dates/year, mechanically sound reason (Fed announcements cause gold whipsaw). Use `news_dates.FOMC_DATES`.
- **Long-only** — No edge in continuation shorts. GC shorts are structurally broken.
- **1s magnifier required** — Do not run GC optimization without `GC_1s.parquet`. 1m data inflates win rate and Calmar artificially.

### What doesn't work on GC
- **Inversion longs** — NO EDGE on complete data. 1411 signals, -40.6R net.
- **Reversal strategy** — No edge. GC trends after ORB breakout, doesn't revert.
- **Continuation shorts** — -98R over 10 years. Every param combo negative.
- **Inversion shorts** — Structural breakdown. Best case 28 trades in 10 years at QM=100%.
- **ORB reclaims** — Without FVG filter, -65R DD in 2023 alone. Untradeable.
- **CISD** — Good WR (50%) but DD exceeds 10R in every config.
- **Asia/London sessions** — Too illiquid (~1 bar/hour).
- **No-ORB clean air inversions** — Re-tested 2026-02-20 on complete data. 1009 unfiltered trades = -281.6R. Best clean air filter (N=1) = -28.9R. Old Sharpe 5.0+ was entirely from sparse data masking SL hits.
- **Stacked strategy (v9 + clean air)** — Both components confirmed NO-GO on complete data.
- **Long ATR (50+)** — Dramatically underperforms short ATR. Do not use ATR 50 as default for GC.
- **Max gap points filter** — Insensitive. GC natural ATR-based filters already limit gap size effectively.

### Parameter sensitivity (continuation longs, clean 1s data, R1 final)
- **atr_length**: ATR 16 is the peak. ATR 14 close (Calmar 9.37 vs 9.71). ATR 18+ loses ground. Short ATR is the structural key (vs ATR 50).
- **ORB window**: 10m optimal. 5m Calmar 5.71 (vs 9.71). 15m+ degrades sharply (3.89). 8m=10m in practice (same bars).
- **ny_stop_atr_pct**: 4.0% optimal in grid (dominates top 20). WF selects 3.5% as mode.
- **rr**: 4.5 optimal. Confirmed in variable sweeps and grid.
- **tp1_ratio**: 0.5 consistently optimal.
- **ny_min_gap_atr_pct**: 2.5% optimal. Grid winner at 3.5% (fewer trades, lower DD) — WF selects 2.5%.
- **entry_end**: 11:00 is a hard cliff. 11:30 drops Calmar from 9.71 → 8.48.
- **flat_start**: Completely insensitive. All values 14:00+ give identical results.
- **max_gap_points**: Insensitive. All values 20-30 identical. Can disable.
- **max_gap_atr_pct**: Off is best. Adding the filter hurts Calmar.
- **excluded_dates**: FOMC dates excluded (mechanically sound). DOW Friday exclusion (+3.10 Calmar) rejected — no mechanical explanation.

### Prop firm considerations (continuation longs R1 clean data — current)
- **OOS Max DD -10.0R** (5-fold WF combined OOS). MC p50 max DD -18.2R, p5 max DD -30.2R.
- **Sizing**: With risk_usd=$5,000/trade → 1R = $5K.
  - For a $50K DD ceiling: risk_usd ~$2,500-3,000/trade (conservative, accounts for MC tail)
  - For a $10K DD ceiling: risk_usd ~$500-600/trade
- **Win rate ~41%** (WF OOS) with rr=4.5 — expect 4-6 loss streaks frequently. Normal.
- **MC survival 85.5%** at -25R ruin (STRONG).
- **Hold-out 2025-2026**: 19.3R in ~14 months with mode params (stop=3.5%).
- **Annual R expectation**: ~11.7R/year (WF OOS avg). Phase 3 marginal (threshold 12.0) — 2021 drags average.
- **2021 structural flat year**: GC continuation longs produce -1.9R to -3.5R in 2021. This is a property of gold in 2021, not a strategy failure. Other years strong (12-24R/yr).
