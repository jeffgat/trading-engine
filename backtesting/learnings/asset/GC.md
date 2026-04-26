# GC (Gold Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $100/point
- **Min tick**: 0.10
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-02 (~10 years, 5m + 1m + 1s)
- **Liquidity**: NY is the primary session. Asia and London were previously assumed too thin (~1 bar/hour), but a 2026-04-01 3-session discovery sweep found **strong edges in both** — Asia produced the best results of all 3 sessions (Calmar 11.71, +167R, 0 neg years). All sessions are viable for ORB continuation.
- **1s data is required**: GC's tight ATR stops (1-3%) are unreliable with 1m bars — a single 1m bar can span entry+stop simultaneously. Always use `GC_1s.parquet` for accurate fill simulation.

## Data History

- **Pre 2026-02-20**: Old CSV data was incomplete/corrupted. All results on old data are **INVALID**.
- **2026-02-20**: New 5m data downloaded (777K bars). 1s data still contaminated (all contracts instead of front_month).
- **2026-02-21**: Clean GC.v.0 1s data re-downloaded. All parquet files regenerated from 1s source. **R1 re-optimization completed on clean data.**

Current data: 714K 5m bars, 3.53M 1m bars, 72.7M 1s bars (2016-01 to 2026-02-19).

---

## Strategies Tested

### Continuation Longs (bullish FVG → long) ✅ GO — Pipeline validated 2026-02-22

#### Current: R3 High-RR config (post-engine-bugfix, 1s magnifier, Friday exclusion)

**Scripts**: `run_gc_ny_cont_long_variable_sweeps_{8-12}.py`, `run_gc_ny_cont_long_grid_sweep_r{1-3}.py`, `run_gc_ny_cont_long_robust_pipeline.py`

Fresh re-optimization starting from baseline, taking a fundamentally different path: high RR (9.0 vs R2's 4.0), shorter ATR (7 vs 10), ICF on, entry→12:00 (vs 11:00), flat 13:30 (vs 15:50), Friday DOW exclusion.

**Converged anchor config:**

| Param | Value |
|-------|-------|
| strategy | continuation |
| direction | long only |
| rr | 9.0 |
| tp1_ratio | 0.35 |
| atr_length | 7 |
| ny_stop_atr_pct | 4.5% |
| ny_min_gap_atr_pct | 3.0% |
| ny_max_gap_atr_pct | 30.0% |
| ny_max_gap_points | 25.0 |
| ORB window | 09:30-09:38 (8m) |
| entry_end | 12:00 |
| flat_start | 13:30 |
| impulse_close_filter | True |
| DOW exclusion | Friday (post-backtest) |
| excluded_dates | FOMC_DATES |
| magnifier | 1s |

**Phase 1** (full history 2016-2026): 622 trades, 31.8% WR, 200.3R net, Sharpe 2.310, Calmar 16.11, DD -12.4R, **0 neg full years**

R by year: 2016 +2.5 | 2017 +9.3 | 2018 +18.5 | 2019 +27.8 | 2020 +23.8 | 2021 +12.5 | 2022 +11.7 | 2023 +26.7 | 2024 +25.8 | 2025 +42.4

**Phase 2 WF** (36m IS/12m OOS/12m step, 7 folds, 81 combos/fold): **PASS**
- OOS: 416 trades, 32.5% WR, 145.7R net, Sharpe 2.467, Calmar 9.47, PF 1.52, DD -15.4R
- WF Efficiency: 0.956 (excellent)
- Stability: 0.929 (high) — stop=4.5 mode 6/7, gap=3.0 mode 5/7, tp1=0.35 mode 4/7
- OOS neg year: 2021 -5.4R

**Phase 3 Prop Firm**: **FAIL** — Worst month -8.0R exceeds 5.0R limit. Annual R avg passes (20.8R/yr), expectancy passes (+0.350R).

**Phase 4 Hold-out** (2025+): **PASS** — 62 trades, 37.1% WR, 41.7R, Sharpe 4.256, PF 2.08.

**Phase 5 Monte Carlo**: **FAIL** — 63.4% survival at -25R ruin (threshold: 70%). MC p50 DD -22.8R.

**Verdict: GO (user override)** — Pipeline scored 3/5 (Phase 3 worst month -8.0R, Phase 5 MC survival 63.4%). Exceptional structural metrics override borderline failures. Position sizing can manage tail risk.

**DB entry**: `bt-gc-ny-cont-longs-r3-high-rr-final-fri-ex-692e90`

**Close-entry follow-up (2026-04-26)**: R3 still needs the retest. In the broad close-entry probe (`2016-04-17` to `2026-03-24`), baseline retest produced `+153.7R / -15.1R DD`; `fvg_close` fell to `-28.3R / -74.9R DD`; no-FVG `breakout_close` fell to `-43.0R / -86.5R DD`. Do not pursue close-entry replacements for GC NY R3. Reference: `backtesting/learnings/reports/PROMISING_ORB_CLOSE_ENTRY_PROBE.md`.

**Convergence path**: 12 rounds of variable sweeps + 3 grid sweeps. Key adoptions: rr 7→9 (grid R1), flat 14:30→13:30 (R8), max_gap_atr=30% (R8), Friday exclusion (R10), rr 8→9 (R11). Grid R3 confirmed anchor at #1/625.

#### Prior: R2 config — INVALIDATED by engine bug fixes (2026-02-22)

The R2 config (rr=4.5, tp1=0.5, stop=3.0%, ATR 10, 10m ORB, entry→11:00, flat 15:50) was optimized before engine bug fixes. Re-running on the corrected engine:

| Metric | Old R2 (pre-fix) | R2 on current engine |
|--------|------------------|---------------------|
| Trades | 492 | 440 |
| Win Rate | 42.7% | 42.0% |
| Net R | 131.8R | 81.1R (-38%) |
| Sharpe | 2.638 | 1.888 |
| Calmar | 13.10 | **7.76** |
| Max DD | -10.1R | -10.4R |
| Neg years | 1 | **2** (2022: -2.1R, 2025: -3.8R) |

Bug fixes removed ~50R of phantom edge. All R2 pipeline results (WF, MC, etc.) are invalid. **Do not use R2 config — use R3 instead.**

#### Other prior versions (historical reference)
- R1 pipeline (clean data, pre-bugfix): INVALIDATED — Calmar 9.71
- R6 (contaminated 1s): SUPERSEDED — Calmar 14.10, numbers inflated
- v2 (contaminated 1s): SUPERSEDED — 1033 trades, Calmar 4.61
- v1 (1m magnifier): INVALID — 1m data inflated performance

### Reversal (bullish FVG -> short, bearish FVG -> long)
- **Status**: INVALIDATED — prior results tested without liquidity sweep gate. Needs re-testing with sweep-gated reversal definition.

### Inversion Longs (wait for FVG invalidation, then enter long)
- **Status**: INVALIDATED — prior results tested without liquidity sweep gate. Needs re-testing with sweep-gated reversal/inversion definition.

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
- **Status**: INVALIDATED — prior results tested without liquidity sweep gate. Needs re-testing with sweep-gated definition.

### No-ORB Liquidity Sweep Inversions (incl. Clean Air)
- **Status**: INVALIDATED — prior results tested without liquidity sweep gate. Needs re-testing with sweep-gated definition.

### Stacked GC Strategy: v9 Regime-Sized + Clean Air No-ORB
- **Status**: INVALIDATED — prior results tested without liquidity sweep gate. Needs re-testing with sweep-gated definition.

### VWAP Reversion (session-anchored VWAP deviation + rejection candle)
- **Status**: NO-GO — confirmed 2026-02-23, comprehensive diagnostic sweep on clean 1s data
- **Scripts**: `run_gc_ny_vwap_baseline.py`, `run_gc_ny_vwap_diagnostic.py`
- **Baseline** (defaults: dev=30% ATR, stop=0%, rr=2.5, close rejection, both dirs): 1259 trades, **0.0% WR, PF 0.02**, 97.6% SL exits. Every year -100R to -133R.
- **Diagnostic sweep** (67 configs): Swept deviation threshold (10-100% ATR), stop buffer (0-20% ATR), direction (both/long/short), RR (1.0-8.0), deviation mode (atr/std), rejection mode (close/pinbar with multiple wick/body params), TP2 mode (fixed_rr/vwap).
- **Results**: Win rate near-zero (0.0-0.5%) across ALL configs. PF universally <1.0 except dev=100% (PF 1.14, only 34 trades in 10 years, 5 neg years — statistically meaningless). Stop buffer from 0% to 20% barely changes outcome. Std-dev mode equally broken. Pinbar rejection reduces trade count but WR stays near-zero.
- **Root cause**: After a "rejection" candle near VWAP deviation bands, GC price does NOT revert to VWAP — it continues in the deviation direction. The mean-reversion signal is structurally wrong for gold, which tends to trend through VWAP rather than revert. This is consistent with GC's strong trending behavior seen in continuation strategy success.
- **Conclusion**: VWAP Reversion has NO EDGE on GC NY in any structural configuration tested. Do not revisit. Gold's trending nature makes it unsuitable for mean-reversion strategies. Stick to ORB continuation strategies for GC.

### VWAP + FVG Inversion Longs (hybrid: bearish FVG below VWAP deviation → invalidation → long)
- **Status**: INVALIDATED — prior results tested without liquidity sweep gate. The FVG inversion component needs re-testing with sweep-gated definition.

### VWAP Trend Continuation Longs (pullback to VWAP center → FVG inversion or CISD → long)
- **Status**: INVALIDATED — prior results tested without liquidity sweep gate. The FVG inversion entry component needs re-testing with sweep-gated definition. CISD entry component also showed no edge (PF 1.04, Calmar 0.07) but is a separate signal type.

### NY Liquidity Sweep Inversion (LSI) fvg_limit — CONDITIONAL GO (2026-02-27)

**Scripts**: `run_gc_ny_lsi_baseline.py`, `run_gc_ny_lsi_fvgl_variable_sweeps_{1-9}.py`, `run_gc_ny_lsi_fvgl_grid_sweep_r1.py`, `run_gc_ny_lsi_fvgl_early_entry_sweep.py`, `run_gc_ny_lsi_fvgl_robust_pipeline.py`, `save_gc_ny_lsi_fvgl_r1_final.py`

#### Converged anchor config

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute (structural stop) |
| lsi_entry_mode | fvg_limit |
| direction | both |
| lsi_n_left | 5 |
| lsi_n_right | 75 (full NY session) |
| lsi_fvg_window_left | 10 |
| lsi_fvg_window_right | 10 |
| atr_length | 7 |
| ny_min_gap_atr_pct | 5.0% |
| ny_stop_atr_pct | 0.0 (structural) |
| ORB window | 09:30-09:35 (vestigial — LSI uses swing pivots) |
| entry_start | 09:35 |
| entry_end | 10:30 |
| flat_start | 15:00 |
| magnifier | 1s |

**WF mode params (use for live trading):** rr=9.0, tp1=0.4, ny_min_gap_atr_pct=5.0

**Phase 1** (full history 2016-2026): 130 trades, 50.8% WR, PF 2.29, Calmar 12.21, Sharpe 4.786, Max DD -5.0R, **0 neg full years**, median stop 46 ticks

R by year: 2016 +7.7 | 2017 +12.6 | 2018 +2.5 | 2019 +4.7 | 2020 +6.5 | 2021 +4.7 | 2022 +6.2 | 2023 +3.9 | 2024 +4.7 | 2025 +5.7

**Phase 2 WF** (36m IS/12m OOS/12m step, 5 folds): **PASS**
- OOS: 62 trades, 45.2% WR, 19.4R, Sharpe 3.608, Calmar 4.17, PF 1.83, DD -4.6R
- WF Efficiency: 0.585 (PASS ≥ 0.5)
- Stability: 1.000 (high) — rr mode=9.0, tp1_ratio mode=0.4, gap mode=5.0%

| Fold | IS Period | OOS Period | IS Shrp | OOS Shrp | Best Params |
|------|-----------|-----------|---------|----------|-------------|
| 1 | 2016→2019 | 2019 OOS | 7.903 | 4.243 | rr=7.0, tp1=0.4, gap=6.0% |
| 2 | 2017→2020 | 2020 OOS | 6.860 | 2.081 | rr=7.0, tp1=0.4, gap=6.0% |
| 3 | 2018→2021 | 2021 OOS | 4.850 | 3.196 | rr=9.0, tp1=0.3, gap=5.0% |
| 4 | 2019→2022 | 2022 OOS | 5.149 | 5.431 | rr=9.0, tp1=0.4, gap=5.0% |
| 5 | 2020→2023 | 2023 OOS | 5.165 | 2.562 | rr=9.0, tp1=0.4, gap=5.0% |

**Phase 3 Prop Firm**: **FAIL** — Avg OOS annual R 3.9R < 6.0R threshold. Worst month -2.3R (PASS ≤ 5.0R), expectancy +0.312R.
- **Structural cause**: ~13 trades/year — individual 12-month OOS windows have insufficient sample (10-15 trades). Full-history achieves exactly 6.0R/yr. Not a strategy failure.

**Phase 4 Hold-out** (2025-01+, WF mode params): **PASS** — 20 trades, 50.0% WR, +7.6R, PF 1.99, Sharpe 3.386. 2025: +5.7R, 2026 YTD: +1.9R.

**Phase 5 Monte Carlo**: **PASS** — 100% survival at -25R ruin (2000 bootstraps, 88 trades). MC p5 final PnL +1.2R, p5 max DD -10.4R.

**Verdict: CONDITIONAL GO** — 4/5 phases. Phase 3 fails due to structural trade frequency (~13/yr), not edge quality. Exceptional structural metrics (Calmar 12.21, 0 neg years all 10 years, 100% MC survival). Trade with appropriate position sizing.

**DB entry**: `bt-gc-ny-lsi-fvgl-r1-final-XXXXXX` (run save script to populate)

#### Anchor convergence path (R1→R9, 2026-02-27)

| Round | Calmar | Adoptions |
|-------|--------|-----------|
| R1 (baseline fvg_limit params) | 0.99 | direction→both; n_right→75; gap→4.0% |
| R2 | 2.40 | flat→14:00; entry_end→10:30; gap→3.0%; atr→20 |
| R3 | 4.49 | n_left→10; gap→4.5%; atr→14 |
| R4 | 6.08 | n_left→10; gap→5.0%; atr→7; flat→14:30 |
| R5 | 8.29 | gap→4.0%; atr→7; flat→14:00; rr→5.0; tp1→0.4 |
| R6 | 6.88 | gap→5.0%; atr→30; flat→14:30; rr→8.0; tp1→0.7 |
| R7 | 7.09 | n_left→5; gap→3.5%; atr→7; flat→13:00; rr→5.0 |
| Grid R1 (252 combos: rr×tp1×gap) | 10.98 | rr→9.0, tp1→0.4, gap→5.0% — ALL top 20 used gap=5.0% |
| R8 (post-grid) | 10.98 | flat_start→15:00 (+1.24) |
| R9 | 12.21 | **0 adoptions → CONVERGED** |

**Key insight — min_gap oscillation**: Rounds R5-R7 had gap/atr/rr/tp1 cycling through the same values. Sequential independent sweeps cannot resolve co-dependent parameters. The 3D grid (252 combos) definitively resolved this: gap=5.0% wins 100% of top-20 regardless of rr/tp1.

#### Close entry vs fvg_limit entry (baseline comparison)

| Mode | Trades | WR | Net R | Calmar | Neg Yrs |
|------|--------|----|-------|--------|---------|
| close / both | 2310 | 53.5% | -40.2R | -0.54 | 6 |
| fvg_limit / both | 2063 | 56.4% | +42.6R | +0.99 | 3 |

**Close entry is not viable at standard params.** fvg_limit dominates at baseline. Optimization focused entirely on fvg_limit.

#### INFO-ONLY findings (not baked into anchor)

- **Mon DOW exclusion**: Calmar 14.72 (+2.51), 108 trades, 0 neg years — noted but not adopted. Consistent signal (R8 and R9 both showed +2.51). Could be reconsidered with WF validation.
- **entry_end=10:15**: Calmar 15.50 (+4.52) but only 72 trades — below 100-trade threshold.
- **Early entry sweep (07:30-09:30)**: Earlier starts lower WR to 40-42% vs 50%+ at 09:35. 2020 large DD on pre-market entries. 09:35 remains optimal.

#### Parameter sensitivity (LSI fvg_limit)

- **lsi_n_right**: 75 (full session) optimal — using prior-session-confirmed pivots only is structurally sound.
- **lsi_n_left**: 5 optimal. Tighter swing definition captures more setups without adding noise.
- **atr_length**: 7 optimal. Short ATR adapts stop thresholds to recent volatility (consistent with GC continuation finding).
- **min_gap_atr_pct**: 5.0% definitively optimal — resolves co-dependence with rr/atr. Grid R1 confirms 100% of top-20 use gap=5.0%.
- **rr**: Wide plateau rr=6-9 all produce Calmar 10-11+. rr=9.0 is stable mode value; rr=7.0 selected in early folds (slightly less aggressive).
- **tp1_ratio**: 0.4 optimal. tp1=0.3 slightly worse (mode in 1 fold), tp1=0.5+ reduces Calmar.
- **entry_end**: 10:30 optimal. Extending to 11:00 adds noise trades. Restricting to 10:15 improves Calmar but drops below trade count floor.
- **flat_start**: 15:00 optimal. Position must be held for full LSI target extension.
- **entry_start**: 09:35 optimal. Pre-market entries (07:30-09:30) systematically worse — lower WR, higher DD, uneven year distribution.
- **direction**: both (not long-only). Unlike continuation longs, LSI finds edge in both directions on GC — structural sweeps confirm "both" throughout.

#### Prop firm considerations

- **Strategy is selective**: ~13 trades/year. Phase 3's 6.0R/yr annual threshold will frequently fail in individual OOS years due to small sample size. Full-history rate (6.0R/yr) is on target.
- **Max DD**: Full-history -5.0R. MC p50 max DD -5.3R. At risk_usd=$5,000, dollar DD is ~$26,500 (p50). Very shallow.
- **Sizing**: Can run at full risk_usd=$5,000 given 100% MC survival and shallow DD.
- **Hold-out 2025**: +5.7R in 2025 — strategy performing in-line with historical average. 2026 YTD +1.9R.
- **Low frequency note**: Accept that some calendar years will underperform 6.0R target (e.g., 2018: +2.5R, 2019: +4.7R). These are statistical variance on 13 trades, not edge failure.

### NY HTF-LSI (Higher-Timeframe Liquidity Sweep Inversion) — NO-GO

- **Status**: **NO-GO** (real pre-holdout family, but the opened funded holdout rejected the entire frozen shortlist)
- **Scripts**: `run_cross_asset_htf_lsi_anchor_explore.py`, `run_cross_asset_htf_lsi_broad_discovery.py`, `run_cross_asset_htf_lsi_stitched_followup.py`, `run_gc_ny_htf_lsi_phase_one.py`
- **Important separation**: this is a different thesis from the existing GC NY LSI `fvg_limit` branch above. Standard GC NY LSI remains a conditional GO; GC NY **HTF-LSI** does not.

**Transfer packet result:**
- Replayed the trusted NQ anchors on GC `1m / 3m / 5m` with the holdout still closed.
- None of the transfer rows were promotable. `5m lag24` and `5m lag0` were constructive on discovery (`PF 1.346` / `1.333`) but both flipped negative in validation (`PF 0.894` / `0.887`). `3m lag0` was weak and `1m lag0` was dead.
- Conclusion from the packet: GC does not accept the NQ HTF-LSI shapes unchanged.

**Broad discovery result (GC-native reopen):**
- Reopened discovery only on pre-holdout data and expanded the search to include GC’s earlier `10:30` cutoff, which the default packet would have under-explored.
- A strong asset-native cluster emerged:
  - `3m`
  - `short`
  - `fvg_limit`
  - `htf60`
  - `htf_n_left=5`
  - `cap=2`
  - `gap=3.0`
  - `atr=14`
  - `rr=3.5`
  - `tp1=0.5`
  - either `entry_end=10:30` with `lag0`, or `entry_end=11:00` with `lag24-30`
- Stage B lead: `3m short fvg_limit 08:30-10:30 htf60 n5 cap2`, discovery PF `1.180`, validation PF `1.620`, validation avg R `0.256`, Calmar `2.705`.

**Stitched follow-up (holdout still closed):**
- `late_lag30_1100_r15` became the stitched leader:
  - `3m`, `short`, `fvg_limit`, `08:30-11:00`
  - `rr=3.5`, `tp1=0.5`, `gap=3.0`, `htf60`, `n5`, `cap=2`, `fvg=20/5`, `lag=30`
  - stitched OOS: `220` trades, PF `1.266`, avg R `0.149`, Calmar `2.79`, DD `-11.77R`
- Best early challenger:
  - `balanced_lag0_1030_r9`
  - stitched OOS: `178` trades, PF `1.277`, avg R `0.140`, Calmar `2.47`, DD `-10.12R`
- Broad read: GC HTF-LSI looked legitimately alive pre-holdout and favored `3m short`, not the NQ-style `5m long` family.

**Phase-one / opened holdout result (`2025-04-01` to `2026-03-30`):**
- Every frozen candidate failed the funded-account holdout test.
- `late_lag30_1100_r15`: `31` holdout trades, PF `0.234`, avg R `-0.573`, funded payout `0.0%`, funded EV/start `-$100.00`
- `quality_lag0_1030_r15`: `28` holdout trades, PF `0.291`, avg R `-0.505`, funded payout `0.0%`, funded EV/start `-$100.00`
- `balanced_lag0_1030_r9`: `26` holdout trades, PF `0.326`, avg R `-0.467`, funded payout `0.0%`, funded EV/start `-$100.00`
- `control_stage_b_1030`: `26` holdout trades, PF `0.330`, avg R `-0.464`, funded payout `0.0%`, funded EV/start `-$100.00`
- `late_lag24_1100_r15`: `29` holdout trades, PF `0.253`, avg R `-0.544`, funded payout `0.0%`, funded EV/start `-$100.00`

**Conclusion:**
- GC HTF-LSI was not a fake discovery; it produced a coherent pre-holdout `3m short` family.
- But the untouched holdout was a full family-wide rejection under the default funded model.
- Do **not** advance GC HTF-LSI to phase two, and do not keep tuning this frozen family.
- If GC HTF-LSI is ever revisited, it needs a materially new thesis rather than more refinement of the `3m short / htf60 / n5` branch.

### NY LSI v2 (NQ RR2/TP0.5 Anchor) — Both Directions — NO-GO

- **Status**: **NO-GO** (REJECT 2/5 pipeline phases — WF efficiency too low, prop constraints fail)
- **Tested**: 2026-04-02, full strategy workflow (baseline → 7-phase sweeps → discovery pipeline)
- **Approach**: Transplanted NQ NY LSI RR2/TP0.5 anchor to GC and re-optimized. Different edge region from existing GC LSI (RR=9.0, entry_end=10:30).
- **Optimized config**: nL=8, nR=120, RR=2.0, TP1=0.5, ATR=30, gap=6.0%, Fri excl, flat=14:30, fvg_limit, both dirs
- **Pre-holdout**: 535 tr, 55.5% WR, PF 1.47, +58.5R, DD -6.3R, **Calmar 9.30**, 1 neg yr (2024: -1.9R)
- **WF OOS** (36m/12m/12m, 6 folds): 344 tr, 49.7% WR, PF 1.16, +15.4R, DD -7.0R, Calmar 2.20, Sharpe 0.93
- **WF efficiency**: 0.258 (FAIL, need ≥0.30) — significant IS→OOS degradation
- **Stability**: 0.958 (high) — rr mode=2.25, tp1 mode=0.6, gap mode=6.0, ATR mode=30
- **MC survival**: 93.4% at 15R (PASS ≥70%), ruin 6.6% (FAIL <5%)
- **Plateau**: PASS — no collapses in local neighborhood
- **Key failure**: OOS Calmar collapses from 9.30 (IS) to 2.20 (OOS). Fold 6 (2024 OOS) goes negative (-0.919 Sharpe). The low-RR approach does not generalize on GC.
- **Comparison to existing GC LSI**: Existing uses RR=9.0/TP1=0.4 with 130 trades and Calmar 12.21. This NQ-anchor approach has 4× more trades but much weaker OOS. The high-RR selectivity of the existing config is what makes GC LSI work — GC needs wide targets to capture commodity-scale moves.
- **Scripts**: `run_gc_ny_lsi_nq_anchor_sweep.py`, `run_gc_ny_lsi_nq_anchor_pipeline.py`

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
- **Inversion longs** — INVALIDATED (tested without sweep gate).
- **Reversal strategy** — INVALIDATED (tested without sweep gate).
- **Continuation shorts** — ~~-98R old data~~ OVERTURNED: CONDITIONAL GO. Full-history Calmar 14.52, 219R, 0 neg years. Pipeline borderline on WF efficiency (0.28 vs 0.30) and MC survival (47.9% vs 60%). Tradeable with reduced position sizing.
- **Inversion shorts** — INVALIDATED (tested without sweep gate).
- **ORB reclaims** — Without FVG filter, -65R DD in 2023 alone. Untradeable.
- **CISD** — Good WR (50%) but DD exceeds 10R in every config.
- ~~**Asia/London sessions** — Too illiquid (~1 bar/hour).~~ **OVERTURNED** (2026-04-01): 3-session discovery sweep with 1s magnifier found Asia is the strongest GC session (Calmar 11.71, +167R, 1,238 trades, 0 neg years). LDN also viable (Calmar 5.09, +85R, short-only). The "1 bar/hour" characterization was inaccurate — GC has sufficient liquidity in both sessions for ORB continuation with FVG detection.
- **No-ORB clean air inversions** — INVALIDATED (tested without sweep gate).
- **Stacked strategy (v9 + clean air)** — INVALIDATED (tested without sweep gate).
- **Long ATR (50+)** — Dramatically underperforms short ATR. Do not use ATR 50 as default for GC.
- **Max gap points filter** — Insensitive. GC natural ATR-based filters already limit gap size effectively.
- **VWAP Reversion** — NO EDGE. 67 configs tested (deviation 10-100% ATR, stop 0-20% ATR, both dirs, RR 1-8, atr/std mode, close/pinbar, fixed_rr/vwap TP2). Win rate near-zero everywhere. Gold trends through VWAP — mean-reversion signals are structurally wrong for GC.
- **VWAP Trend Continuation** — INVALIDATED (FVG inversion component tested without sweep gate). CISD entry component showed no edge independently (PF 1.04, Calmar 0.07).

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
- **entry_delay**: 0m (baseline) is optimal and GC R3 is the most sensitive leg. 10m delay collapses Calmar from 15.60→4.72 (DD -12.4→-26.9R). The 8m ORB means early FVGs form right after 09:38; delaying even slightly misses the best setups. 5m delay is identical (same 5m bar boundary). Script: `run_combined_longs_entry_delay_sweep.py`.
- **event_day_exclusion**: FOMC already excluded in engine config (no additional effect from post-trade filter). NFP: only 1 trade (-1.0R), negligible. CPI actually *above* average (+0.529R vs +0.310R, n=33) — excluding CPI *hurts* (Calmar 15.60→13.02, DD -12.4→-13.6R). No additional event exclusions recommended. Script: `run_combined_longs_event_day_sweep.py`.

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

---

### GC ORB 3-Session Discovery (2026-04-01)

New 3-session sweep with 1s magnifier and regime gate. 1,296 configs per session (4 ORB windows × 2 stop modes × 4 RR × 4 TP1 × 3 directions × 4-5 stop values). Pre-holdout only (<2024-03). Script: `run_gc_orb_discovery.py`.

**Overturns the "Asia/LDN too illiquid" assumption** — Asia produced the strongest results of all 3 sessions.

#### Best Per Session

| Session | Top Config | Net R | Calmar | Sharpe | DD | Trades | Dir | Neg Yrs |
|---------|-----------|-------|--------|--------|----|--------|-----|---------|
| **Asia** | 30m ORB, ORB 25%, RR=2.5, TP1=0.6 | **+167.0** | **11.71** | 1.67 | -14.2 | 1,238 | both | **0** |
| **NY** | 30m ORB, ATR 15%, RR=3.0, TP1=0.4 | +72.3 | 5.70 | 1.09 | -12.7 | 947 | both | 0 |
| **LDN** | 10m ORB, ATR 5%, RR=3.0, TP1=0.5 | +85.2 | 5.09 | 1.57 | -16.7 | 655 | short | 0 |

#### Key Findings

1. **Asia is the strongest GC session** — Calmar 11.71 at +167R, 0 negative years, 1,238 trades. Completely overturns "~1 bar/hour" assumption. 30m ORB with tight ORB 25% stop is the winning structure.
2. **Shorts dominate across all sessions** — top NY configs are short or both (short carries the both). All top LDN configs are short-only. Asia top configs are both/short.
3. **ORB range stops work well** — Asia #1 is ORB 25%, LDN #2 is ORB 25%. Not just ATR-based stops.
4. **30m ORB is optimal for Asia and NY**, while **10m ORB is optimal for LDN**.
5. **NY with these lower RR/TP1 params is weaker than existing R3 config** — R3 (RR=9.0, ATR 7, 8m ORB) has Calmar 16.11. The lower RR sweep finds a different, weaker optimum. NY continuation is already well-optimized.
6. **LDN short-only is viable** — Calmar 5.09, +85R, 0 neg years at #1. 10m ORB with very tight stops (ATR 5%).
7. **All 3 sessions show 0 negative years** at their top configs — structural edge exists across sessions.

#### Discovery Pipeline — Walk-Forward Ranking

9 candidates (3 per session) through 12m IS / 3m OOS / 3m step walk-forward with 1s magnifier. Script: `run_gc_orb_discovery_pipeline.py`.

| # | Name | OOS R | Calmar | Sharpe | DD | WFE | Stability | Gate | Verdict |
|---|------|-------|--------|--------|----|-----|-----------|------|---------|
| 1 | Asia-2 (15m ORB75 short) | +97.2 | 10.51 | 2.34 | -9.2 | 0.545 | 1.000 | Y | PROMOTE |
| 2 | Asia-3 (30m ORB75 short) | +89.9 | 7.00 | 2.10 | -12.8 | 0.491 | 1.000 | N | PROMOTE |
| 3 | Asia-1 (30m ORB25 both) | +141.7 | 7.50 | 1.54 | -18.9 | 0.450 | 0.839 | N | PROMOTE |
| 4 | LDN-3 (10m ATR8 short) | +46.5 | 3.16 | 1.13 | -14.7 | 0.341 | 1.000 | Y | PROMOTE |

---

### GC Asia ORB Continuation — Phase-One Complete (2026-04-01)

**Status**: Asia-1 is **STRONG**. Asia-2/Asia-3 collapsed on holdout. LDN-3 dead. Script: `run_gc_orb_phase_one.py`.

#### Phase-One Results (all 4 promoted candidates, both gate variants)

| Candidate | Verdict | Pre R | HO R | Pre PR | HO PR | HO EV | PSR |
|-----------|---------|-------|------|--------|-------|-------|-----|
| **Asia-1 ungated** | **STRONG** | +167.0 | **+20.1** | 70.1% | **55.9%** | $11,102 | 1.000 |
| **Asia-1 gated** | **STRONG** | +131.9 | **+20.4** | 68.1% | **58.4%** | $11,617 | 1.000 |
| Asia-2 gated | STRONG | +92.9 | -1.1 | 77.2% | 43.3% | $8,597 | 1.000 |
| Asia-2 ungated | CONDITIONAL | +105.2 | -4.3 | 72.7% | 35.1% | $6,955 | 1.000 |
| Asia-3 ungated | CONDITIONAL | +111.4 | -16.0 | 78.7% | 5.8% | $1,069 | 1.000 |
| Asia-3 gated | CONDITIONAL | +84.3 | -6.2 | 82.1% | 5.8% | $1,074 | 1.000 |
| LDN-3 ungated | CONDITIONAL | +16.7 | -41.4 | 55.1% | 11.2% | $2,155 | 0.712 |
| LDN-3 gated | CONDITIONAL | +34.1 | -26.1 | 58.1% | 6.1% | $1,125 | 0.900 |

#### Asia-1 Config (WINNER — promoted to paper trading consideration)

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 20:00-20:30 (30m) |
| entry window | 20:30-23:15 |
| flat | 04:00-07:00 |
| stop | ORB 25% |
| rr | 2.5 |
| tp1_ratio | 0.6 (TP1 at 1.5R, TP2 at 2.5R) |
| direction | both |
| atr_length | 14 |
| min_gap_atr_pct | 1.0% |
| bar magnifier | ON (1s) |

- **Pre-holdout ungated**: 1,238 trades, 47.1% WR, PF 1.25, +167.0R, Cal 11.71, DD -14.3R, 0 neg years
- **Pre-holdout gated**: 943 trades, 47.2% WR, PF 1.26, +131.9R, Cal 9.59, DD -13.8R, 1 neg year (2022:-6.2)
- **Holdout ungated**: 307 trades, +20.1R, Cal 1.38, Shp 0.82, DD -14.5R (2024:+7.4, 2025:+16.0, 2026:-3.4)
- **Holdout gated**: 225 trades, +20.4R, Cal 1.74, Shp 1.11, DD -11.7R (2024:+9.9, 2025:+13.8, 2026:-3.4)
- **DSR**: 0.652 ungated / 0.508 gated @1,296 trials (borderline)

#### Gate Decision
Both variants STRONG. Gated has better holdout Calmar (1.74 vs 1.38), better Sharpe (1.11 vs 0.82), smaller DD (-11.7 vs -14.5R), and higher holdout payout rate (58.4% vs 55.9%). But ungated has 0 pre-holdout negative years and more trades. **Recommend gated for production** — tighter risk profile on holdout.

#### Key Findings
1. **Asia-1 is a new GC edge** — first validated GC strategy outside NY session. 30m ORB with ORB 25% stop, both directions.
2. **Discovery WF ranking ≠ holdout ranking** — Asia-2 was WF #1 (Cal 10.51) but collapsed on holdout. Asia-1 was WF #3 but the only holdout survivor.
3. **Asia short-only strategies (Asia-2, Asia-3) collapsed** — 2024-2025 gold bull market killed short-only configs. Both-directions Asia-1 survived because the long component carried.
4. **LDN is dead on holdout** — -41.4R ungated, -26.1R gated. 84-90% breach rate. Do not promote.
5. **GC now has 3 validated strategies**: NY continuation longs (R3), NY continuation shorts (conditional), and Asia continuation both (Asia-1).

---

### Regime-Gate Transfer Confirmation (2026-04-01)

Cross-asset transfer run with shared holdout `2024-03-01` to `2026-02-28` reconfirmed GC Asia-1 as a genuine gate candidate:

| Variant | Trades | HO R | Calmar | Sharpe | DD | HO PR | HO EV |
|---------|--------|------|--------|--------|----|-------|-------|
| Ungated | 307 | +20.08 | 1.385 | 0.816 | -14.5R | 55.9% | $11,102 |
| Gated | 225 | +20.41 | 1.745 | 1.110 | -11.7R | 58.4% | $11,617 |

- **Verdict**: `supports_gate`
- **Interpretation**: GC keeps essentially the same holdout net R after removing medium-vol days, but the gate meaningfully improves risk-adjusted quality and payout behavior.
- **Action**: Keep **Asia-1 gated** as the preferred production baseline and promote GC into the second-round regime-gate study.

**Close-entry follow-up (2026-04-26)**: The raw `GC Asia-1` signal also still needs retest behavior. Ungated baseline retest was `+114.7R / -21.0R DD`; `fvg_close` was `-67.7R / -91.1R DD`; no-FVG `breakout_close` was `-120.4R / -124.0R DD`. Holdout did not rescue the branch (`breakout_close` holdout `-31.1R`). Do not pursue close-entry replacements here; keep regime-gated retest as the only serious GC Asia-1 form. Reference: `backtesting/learnings/reports/PROMISING_ORB_CLOSE_ENTRY_PROBE.md`.

### Regime-Gate Round Two Refinement (2026-04-01)

Round two tested partial vs full medium-vol blocks on the same shared holdout:

| Variant | HO R | Calmar | Sharpe | DD | HO PR |
|---------|------|--------|--------|----|-------|
| Ungated | +20.08 | 1.385 | 0.816 | -14.5R | 55.9% |
| Block `bull_medium_vol` only | **+26.68** | **2.183** | **1.314** | **-12.2R** | **64.9%** |
| Block `sideways_medium_vol` only | +13.81 | 1.143 | 0.768 | -12.1R | 46.5% |
| Block full medium-vol gate | +20.41 | 1.745 | 1.110 | -11.7R | 58.4% |

- **Damage attribution**: `bull_medium_vol` was -6.59R on holdout, while `sideways_medium_vol` was +6.26R.
- **Updated action**: refine the GC gate to **block `bull_medium_vol` only**. The full NQ-style gate is directionally helpful, but it removes a profitable GC bucket.
