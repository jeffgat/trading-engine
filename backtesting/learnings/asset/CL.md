# CL (Crude Oil Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $1,000/point
- **Min tick**: 0.01 ($0.01/tick)
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-02 (~10 years, 5m: 694K bars, 1m: 3.4M bars, 1s: 74.3M bars)
- **Liquidity**: NY session primary. Asia and LDN sessions not yet tested.
- **Stop distance warning**: CL's small min_tick ($0.01) relative to ATR (~$1.50) means low stop_atr_pct values produce sub-tick stops. Minimum viable stop is 10 ticks ($0.10), requiring stop_atr_pct ≥ ~7% at typical ATR. See "Simulator Artifact" below.

## Data History

- **Pre 2026-02-22**: Prior learnings invalidated due to corrupted data. All old results purged.
- **2026-02-22**: Fresh optimization from scratch on clean data. R1-R4 variable sweeps + robust pipeline completed.
- **2026-02-22**: **ALL R1-R4 results INVALIDATED** — simulator had no minimum stop distance, allowing sub-tick stops. 10-tick floor added to engine. Re-test with floor shows NO EDGE.

---

## Strategies Tested

### Plain NY ORB Breakout Seed Surface (2026-06-18) — NO-GO
- **Status**: NO-GO — crude-oil plain ORB seed had some positive preholdout cells, but validation and stress rejected them.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_SEED_CORE_NQ_ES_CL_NY_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_seed_core_nq_es_cl_ny_20260618/`.
- **Scope**: Canonical `strategy="orb_breakout"` seed grid, CL NY only, ORB windows `5/15/30`, train `2021-2023`, validation `2024`, holdout closed from `2025` onward.
- **Best rejected cell**: `cl__ny__orb5__stop10__gap0__rr2__both__no_thu__low_atr_only__small_orb_only` had 2021-2024 preholdout `+15.00R`, PF `1.13`, DD `-10.00R`, but 2024 validation `-5.00R`, PF `0.91`, cluster score `0.00`, DSR `0.0670`, cost/slippage stress `FAIL`. It passed the no-single-year dependency check only because the weak validation year was included, not because it was promotable.
- **Conclusion**: Plain CL NY ORB breakout should not advance from seed. Wider stop/threshold-adjusted CL work would need a separate frozen run, not parameter rescue from this failed seed surface.

### Plain LDN ORB Breakout Broad Surface (2026-06-18) — EXACT-REPLAY QUEUE
- **Status**: EXACT-REPLAY QUEUE ONLY — one CL LDN short plain ORB cluster passed broad-surface promotion gates; CL NY and CL Asia remained rejected.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_BROAD_FULL_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_broad_full_20260618/`.
- **Top row**: `cl__ldn__orb30__stop12p5__gap0__rr1p5__short__no_thu__low_atr_only__small_orb_only` had 2024 validation `+16.18R`, 2021-2024 preholdout `+35.13R`, stress `+4.13R`, cluster score `1.00`, DSR `0.7695`.
- **Conclusion**: The LDN short row is a narrow exact-replay candidate, not a live approval. The stress margin is thin compared with NQ/GC/RTY candidates, so exact replay and slippage audit should be especially strict.

### Plain LDN ORB Breakout Exact Replay (2026-06-18) — EXACT-REPLAY PASS
- **Status**: Exact-replay PASS on pre-holdout/discovery only. Holdout stayed closed.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_EXACT_REPLAY_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_exact_replay_20260618/`.
- **Scope**: execution-engine exact replay of `cl__ldn__orb30__stop12p5__gap0__rr1p5__short__no_thu__low_atr_only__small_orb_only` over `2021-01-01` to `2024-12-31`, with 5m signal bars and 1s fill/exit sequencing.
- **Result**: `177` exact trades, `+33.68` net R, PF `1.38`, max DD `-13.50R`, and `96%` retention versus research preholdout R. Exact year R stayed positive across 2021-2024: `+14.98R`, `+0.50R`, `+13.20R`, `+18.14R`.
- **Caveat**: The broad-surface stress margin was thin (`+4.13R`), so this should advance only to strict exact stress/replay diagnostics, not holdout or paper. CL stop/order handling must remain conservative because this asset has a long history of stop-distance artifacts.
- **Conclusion**: CL LDN 30m short is a real pre-holdout survivor after exact replay, but lower priority than GC/NQ/RTY because of stress-margin fragility and drawdown.

### Plain LDN ORB Breakout Exact Stress (2026-06-18) — FAIL
- **Status**: FAIL under strict exact cost/slippage stress. Holdout stayed closed.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_EXACT_STRESS_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_exact_stress_20260618/`.
- **Stress model**: post-exact-replay accounting on the frozen trade ledger, with `2x` baseline commission plus `2` adverse ticks per side on every filled round trip. Signal/fill path unchanged.
- **Result**: `cl__ldn__orb30__stop12p5__gap0__rr1p5__short__no_thu__low_atr_only__small_orb_only` fell from exact `+33.68R` to stressed `-13.39R`, PF `0.88`, DD `-19.58R`. Even the slippage-only `2` ticks/side scenario was roughly flat/negative at `-0.25R`.
- **Conclusion**: Reject the CL plain LDN breakout row for this workflow. The exact replay pass was too dependent on low friction, which matches the earlier broad-stress warning.

### Continuation Both (bullish FVG → long, bearish FVG → short) — NO-GO (INVALIDATED)

**Scripts**: `run_cl_ny_sweep_r1.py`, `run_cl_ny_variable_sweeps_{2,3,4}.py`, `run_cl_ny_robust_pipeline.py`, `run_cl_ny_low_rr_pipeline.py`

#### Simulator Artifact Discovery

The R1→R4 optimization converged on stop=0.75-1.0% ATR, which on CL (ATR ~$1.50) computes to $0.01-$0.015 — approximately **1 tick**. The simulator never checks the fill bar for stop hits, so a 1-tick stop gets a free pass on every trade. This inflated win rate and Calmar dramatically.

After adding a 10-tick minimum stop floor to the engine (`simulator.py`), the results collapsed:

| Metric | Before (no floor) | After (10-tick floor) |
|--------|-------------------|----------------------|
| Phase 1 Calmar | 38.01 | **6.57** |
| Phase 1 Net R | 905.7R | **264.1R** |
| Phase 1 WR | 31.5% | **25.0%** |
| Phase 1 Max DD | -23.8R | **-40.2R** |
| Phase 1 Neg years | 0 | **2** |
| WF OOS Net R | 825.9R | **175.5R** |
| WF OOS Neg years | 0 | **2** (2020: -29.8R, 2022: -12.3R) |
| Phase 4 holdout R | +119.2R | **-1.0R** |
| Phase 4 Sharpe | 3.319 | **-0.032** |
| MC survival | 43.3% | **0.1%** |

**Critical insight**: Every stop_atr_pct value in the sweep range (0.75-3.0%) computes to less than $0.10 on CL and gets clamped to 10 ticks. To get a natural stop above 10 ticks, CL needs stop_atr_pct ≥ ~7%. The entire R1→R4 optimization was chasing an artifact — the grid kept rewarding tighter stops because the simulator gave each trade a free pass on the fill bar.

**Verdict: HARD NO-GO** — No viable edge at realistic stop distances. Do not revisit continuation on CL without fundamentally different stop logic or much wider stop_atr_pct ranges (7%+).

#### Pre-floor results (INVALID — kept for reference only)

**Anchor config**: stop=1.0%, rr=6.0, gap=1.0%, tp1=0.60, ORB 10m, ATR 10, entry→14:00, both directions, 1s magnifier

Phase 1: 2131 trades, 31.5% WR, 905.7R, Calmar 38.01, 0 neg years — **INFLATED by sub-tick stops**
Phase 2 WF: 825.9R OOS, WF eff 0.952, stability 1.000 — **INFLATED**
Phase 3: FAIL (worst month -12.8R)
Phase 4: +119.2R holdout — **INFLATED**
Phase 5: 43.3% MC survival — **INFLATED**

Low-RR variant (rr=4.0, stop=2.0%): Also inflated. Calmar 9.58, MC survival 11.5%.

### VWAP Reversion Shorts — NO-GO

**Scripts**: `run_cl_ny_vwap_diagnostic.py`, `run_cl_ny_vwap_focused_sweep.py`

**Approach**: Session-anchored VWAP deviation + rejection candle entry, short only. Tested deviation_atr_pct 10-100%, stop_atr_pct 0-25%, deviation_std 1.0-3.0, rejection modes (close/pinbar), TP2 modes (fixed_rr/vwap), ATR lengths 5-30, entry windows, flat times. Full 2D dev×stop grid + focused high-leverage sweeps.

**Diagnostic sweep (82 configs)**: CL shorts showed initial promise at dev=20%, stop=15%, rr=8.0, tp1=0.7, atr=10, entry→11:00 → 895 trades, PF 1.16, +89.1R, Calmar 0.35, 2 neg years.

**Focused sweep (7 dimensions)**: Flat time, dev×stop 2D grid, min_stop_points, RR, TP1, entry end, ATR length. Only RR (8→12) and TP1 (0.7→0.8) adopted with minimal impact.

**Best config found**:

| Param | Value |
|-------|-------|
| direction | short |
| deviation_atr_pct | 20% |
| stop_atr_pct | 15% |
| rr | 12.0 |
| tp1_ratio | 0.8 |
| atr_length | 10 |
| entry_end | 11:00 |
| flat_start | 15:50 |
| rejection_mode | close |
| tp2_mode | fixed_rr |

| Metric | Value |
|--------|-------|
| Trades | 895 |
| WR | 0.4% |
| PF | 1.18 |
| Net R | +96.8 |
| R/yr | 9.5 |
| Max DD | -25.6R |
| Calmar | 0.37 |
| Neg years | 2 (2020, 2025) |
| Median stop | 36 ticks |

**Why NO-GO**:
- Calmar 0.37 is below the 0.5 pipeline threshold (would fail Phase 1 structural validation)
- Extreme concentration: 2022 (+38.3R) and 2024 (+50.9R) = 92% of total R
- Poor recency: 2025 is -10.0R
- Flat optimization surface: no dimension meaningfully improves Calmar beyond 0.37
- Edge is thin and fragile — not suitable for prop firm deployment

**Key finding**: VWAP longs on CL are definitively bad (all configs negative). Shorts show a marginal statistical edge but insufficient for trading.

### LSI (Liquidity Sweep Inversion) Both — NO-GO

**Scripts**: `run_cl_ny_lsi_baseline.py`, `run_cl_ny_lsi_variable_sweeps_1.py`

**Approach**: `strategy="lsi"` — swing level swept → FVG forms within 10 bars → FVG inverted → entry at inversion bar close. Structural stop (`lsi_stop_mode="absolute"`). Entry 09:35-15:30, flat 15:50.

**Step 1 — Baseline** (n_left=3, n_right=3, 2016-2026):

| Metric | Both | Longs | Shorts |
|--------|------|-------|--------|
| Trades | 2421 | 1223 | 1198 |
| WR | 53.9% | 54.7% | 53.1% |
| PF | 0.88 | 0.94 | 0.82 |
| Net R | -120.0 | -31.4 | -88.6 |
| R/yr | -11.7 | -2.9 | -8.8 |
| Calmar | -0.95 | -0.58 | -0.92 |
| Max DD | -126.9R | -54.1R | -96.6R |
| Neg years | 9/10 | 5/10 | 9/10 |
| Median stop | 37t | 39t | 36t |

**Step 2 — Wide Pivot Sweep** (n_left × n_right 2D grid, 64 combos):

Tested whether wider pivots (requiring more significant swing levels) improve the signal. Grid: n_left=[3,6,12,24,48,96,144,288] × n_right=[3,6,12,24,48,96,144,288]. All other params held at baseline.

| Metric | Best combo (48×12) | Range across grid |
|--------|-------------------|-------------------|
| PF | 0.94 | 0.77 – 0.94 |
| Calmar | -0.78 | -1.02 – -0.78 |
| Net R | -43.1 | -165.0 – -43.1 |
| Trades | 1968 | 1196 – 2421 |
| Neg years | 7/10 | 5 – 10 |

**Every single combo in the 64-cell grid is negative** — PF < 1.0 and Calmar < 0 for all. The best combo (n_left=48, n_right=12) merely loses less (-43.1R vs -120.0R baseline) with PF 0.94 and 7 negative years. No combo meets viability thresholds (PF ≥ 1.0, Calmar ≥ 0.5).

**Why NO-GO (strengthened)**:
- Baseline failed: PF 0.88, Net R -120R, 9/10 negative years
- Wide pivot sweep (64 combos up to 288 bars / ~24 hours) — zero viable combos
- PF never reaches 1.0 at any pivot width, Calmar never reaches 0.0
- Wider pivots reduce trade count but do not flip the edge — losses shrink proportionally
- The LSI signal is structurally broken on CL regardless of pivot significance
- Structural stops are healthy (37-39 ticks median) — not a stop-distance artifact
- FVG stop mode even worse: 23.5% WR, -1490.7R
- **DEFINITIVE NO-GO** — do not revisit LSI on CL

### Reversal with Liquidity Sweep Gate — NO-GO

**Script**: `run_cl_ny_reversal_sweep_test.py`

**Concept**: `strategy="reversal"` (bullish FVG → SHORT, bearish FVG → LONG). Sweep gate keeps only trades where a liquidity sweep occurred between signal and fill: buy-side sweep for shorts (price took out swing high), sell-side sweep for longs (price took out swing low).

**Grid**: stop_atr_pct=[7,10,15] × rr=[2.0,3.5,5.0] × direction=[both,long,short] = 27 configs. Post-filtered at swing lookback N=[6,12,24,48].

**Baseline results** (all 27 configs deeply negative):
- Win rate: 10-29% depending on stop/rr
- PF: 0.16-0.54
- Net R: -470R to -1560R over 10 years
- Every config negative every year

**Sweep gate results**:
- Gate passes only 3-8 trades out of 1200+ filled (0.2-0.5% pass rate)
- Top 10 table EMPTY — no gated config reaches 20-trade minimum
- "Positive" N=48 long-only results (+2.5 to +4.8R) are noise on 6-trade samples
- Short-side gated trades: universally 0% WR across all lookback values

**Verdict: NO-GO** — Reversal signal is structurally broken on CL. After ORB breakout, counter-directional FVGs do not produce reversals even when preceded by a liquidity sweep. The sweep gate is too selective (99.5%+ rejection) to produce a tradeable sample. Do not revisit.

---

## What Works on CL

- **10-minute ORB** (09:30-09:40) — ORB 10m was +218% vs ORB 15m in R1. This structural finding may still hold at wider stops.
- **ATR 10** — Short ATR adapts to CL's volatile sessions. Likely still valid.
- **entry_end 14:00** — CL has afternoon continuation. Likely still valid.

## What Doesn't Work on CL

- **Continuation at stop_atr_pct < 7%** — Sub-tick stops, invalidated by 10-tick floor. The optimizer consistently pushed toward impossibly tight stops, masking the lack of edge at realistic distances.
- **VWAP Reversion** — Shorts marginal (Calmar 0.37, PF 1.18, concentrated in 2 years). Longs definitively bad (all configs negative). Flat optimization surface — no lever moves Calmar above 0.37. Not viable for prop firm.
- **Reversal with sweep gate** — NO-GO. 27 configs (stop=[7,10,15]% × rr=[2.0,3.5,5.0] × dir=[both,long,short]) all catastrophically negative. Baseline: -470R to -1560R, WR 10-29%, PF 0.16-0.54. Sweep gate (N=[6,12,24,48]) filters to 3-8 trades in 10 years (0.2-0.5% pass rate) — statistically meaningless. "Positive" gated results are noise on 6-trade samples. Script: `run_cl_ny_reversal_sweep_test.py`.
- **LSI (Liquidity Sweep Inversion)** — DEFINITIVE NO-GO. Baseline (n_left=3, n_right=3): PF 0.88, Net R -120R, 9/10 neg years. Wide pivot sweep (64 combos, n_left/n_right up to 288 bars): every combo negative, best PF=0.94, best Calmar=-0.78. Signal structurally broken on CL regardless of pivot width. Scripts: `run_cl_ny_lsi_baseline.py`, `run_cl_ny_lsi_variable_sweeps_1.py`.
- **Asia / LDN sessions** — Tested in 3-session discovery (see Strategy 5 below). LDN longs are viable. Asia longs marginal.

### 5. 3-Session ORB Continuation Discovery (NY + Asia + LDN) — CONDITIONAL GO (LDN longs)
- **Status**: **CONDITIONAL GO** — LDN longs survive holdout with 49-55% holdout PR; DSR marginal (0.19-0.29)
- **Scripts**: `run_cl_orb_discovery.py`, `run_cl_orb_discovery_pipeline.py`, `run_cl_orb_phase_one.py`
- **Sweep**: 1,296 configs per session, 3,888 total. Pre-holdout <2025-01. 1m magnifier. ATR stops at 5% hit 10-tick floor (noted in output).

**Discovery sweep results:**
- **LDN**: Outstanding longs — Calmar 8.9-9.3, 0 neg years, scores 2.9-5.7. 30m ORB ATR 8% and 10m ORB 25% both strong.
- **Asia**: Strong longs — Calmar 4.3-6.4, 1 neg year, scores 0.1-2.6. 5m ORB dominates.
- **NY**: Moderate — 2-3 neg years, scores <0.6.

**Discovery pipeline (WF 12m IS / 3m OOS / 3m step, Calmar objective):**
| Candidate | OOS R | Calmar | Sharpe | DD | WFE | Stability | Verdict |
|-----------|-------|--------|--------|------|-----|-----------|---------|
| LDN-4 (10m ORB 25%, RR 3.5, TP1 0.6, long) | +152.5 | 7.62 | 1.21 | -20.0 | 0.416 | 0.875 | PROMOTE |
| LDN-1 (30m ATR 8%, RR 3.5, TP1 0.6, long) | +103.4 | 5.32 | 1.15 | -19.4 | 0.463 | 0.903 | PROMOTE |
| Asia-2 (5m ORB 75%, RR 2.5, TP1 0.4, long) | +97.2 | 3.65 | 1.36 | -26.6 | 0.469 | 0.833 | PROMOTE |

**Phase-One Results:**
| Candidate | Pre R | HO R | Pre PR | HO PR | EV | PSR | DSR | Verdict |
|-----------|-------|------|--------|-------|------|-----|-----|---------|
| LDN-1 | +123.1 | **+12.8** | 58.6% | **54.1%** | $11,639 | 0.995 | 0.186 | CONDITIONAL |
| LDN-2 | +129.1 | **+7.3** | 58.0% | **55.0%** | $11,522 | 0.998 | **0.294** | CONDITIONAL |
| LDN-3 | +122.6 | **+8.6** | 57.1% | **48.9%** | $11,348 | 0.997 | 0.243 | CONDITIONAL |
| LDN-4 | +133.3 | -11.1 | 55.6% | 28.2% | $11,058 | 0.993 | 0.166 | CONDITIONAL |
| Asia-2 | +68.3 | -5.0 | 61.9% | 30.9% | $12,304 | 0.980 | 0.094 | CONDITIONAL |
| Asia-1 | +71.0 | -14.0 | 55.9% | 9.4% | $11,110 | 0.975 | 0.076 | CONDITIONAL |

**Key findings:**
- **LDN 30m ORB ATR 8% longs** are the winning family — LDN-1/LDN-2/LDN-3 all survived holdout (+7 to +13R) with holdout PR 49-55%
- **LDN-4 (10m ORB 25%)** had the best WF Calmar (7.62) but failed holdout (-11.1R) — 2025 was -13.3R
- **Both Asia configs failed holdout** — not recommended
- **All PSR >= 0.975** — Sharpe ratios are statistically real
- **DSR 0.19-0.29** — marginal, below the 0.50 threshold for surviving deflation. Edge is real but selection-bias-sensitive.

### 6. NY HTF-LSI (Higher-Timeframe Liquidity Sweep Inversion) — CONDITIONAL

- **Status**: **CONDITIONAL** — unlike regular CL LSI, the HTF-LSI branch produced a real `1m` pre-holdout family and two downstream candidates with positive funded holdout EV/start, but holdout payout rates are still only moderate.
- **Scripts**: `run_cross_asset_htf_lsi_anchor_explore.py`, `run_cross_asset_htf_lsi_broad_discovery.py`, `run_cl_ny_htf_lsi_stitched_followup.py`, `run_cl_ny_htf_lsi_phase_one.py`, `run_cl_ny_htf_lsi_improvement_paths.py`, `run_cl_ny_htf_lsi_local_refinement.py`, `execution/scripts/run_cl_ny_htf_lsi_exact_replay.py`
- **Reports**: `CL_NY_HTF_LSI_ANCHOR_EXPLORE.md`, `CL_NY_HTF_LSI_BROAD_DISCOVERY.md`, `CL_NY_HTF_LSI_STITCHED_FOLLOWUP.md`, `CL_NY_HTF_LSI_PHASE_ONE.md`, `CL_NY_HTF_LSI_IMPROVEMENT_PATHS.md`, `CL_NY_HTF_LSI_LOCAL_REFINEMENT.md`, `CL_NY_HTF_LSI_EXACT_REPLAY.md`

**Important workflow note**:
- Discovery was intentionally frozen after **Stage C** on the `1m` branch. The generic full `1m` Stage D/E packet was too expensive on CL’s full history, so the shortlist was taken from saved Stage B/C rows and then judged by stitched OOS and phase one.

**Transfer / discovery path:**
- The narrow NQ anchor packet already showed that HTF-LSI is not the same thesis as CL’s regular LSI failure:
  - `1m lag0 honest`: `900` pre-holdout trades, PF `1.142`, avg R `0.073`; validation PF `1.199`, avg R `0.099` — `alive`
  - `3m lag0 diagnostic`: PF `1.014`, avg R `0.009` pre-holdout; validation PF `1.049`, avg R `0.023` — `diagnostic_only`
  - both `5m` rows were dead
- Partial broad discovery then shifted CL into a clearly native family:
  - `1m`
  - `long`
  - `close`
  - later NY cutoffs (`13:00-15:00`)
  - either `htf30 n5` or the alternate `htf60 n3`
  - `rr=3.0`, `tp1=0.6`, `gap=3.0`, large FVG window (`100/10`)
- Best Stage B row: `1m / long / close / 14:00 / htf30 n5 / cap2`
  - discovery PF `1.084`, avg R `0.046`
  - validation PF `1.230`, avg R `0.121`, Calmar `3.94`
- Best Stage C challengers:
  - `entry_end=10:30` had the strongest fixed validation (`PF 1.420`, avg R `0.223`) but much thinner sample
  - `htf_n_left=7` and `atr=10/20` were the strongest same-family challengers

**Stitched OOS result:**
- The stitched leader was **not** the Stage B control. Best rows were:
  - `structural_alt_htf60_end14`: `573` stitched trades, PF `1.208`, avg R `0.109`, Calmar `2.41`
  - `htf_n7_end14`: `558` stitched trades, PF `1.222`, avg R `0.117`, Calmar `2.25`
  - `early_end1030`: higher fixed validation quality, but only `365` stitched trades and weaker Calmar `1.77`

**Phase-one result (holdout opened once on `2025-04-01` to `2026-03-31`):**
- **Lead conditional branch**: `structural_alt_htf60_end14`
  - config: `1m`, `long`, `close`, `08:30-14:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `htf60`, `n3`, `cap2`, `fvg=100/10`, `lag=0`
  - stitched OOS: `573` trades, PF `1.208`, avg R `0.109`, funded payout `45.1%`, funded EV/start `$116.23`
  - holdout: `95` trades, PF `1.102`, avg R `0.049`, total R `+4.64`
  - holdout funded payout `24.7%`, funded EV/start `$34.77`
  - verdict: **CONDITIONAL**
- **Secondary conditional challenger**: `htf_n7_end14`
  - stitched OOS: `558` trades, PF `1.222`, avg R `0.117`, funded payout `50.6%`, funded EV/start `$104.04`
  - holdout: `98` trades, PF `0.977`, avg R `-0.016`, total R `-1.55`
  - holdout funded payout `22.4%`, funded EV/start `$6.74`
  - verdict: **CONDITIONAL**
- **Rows to keep closed**:
  - `early_end1030`: holdout funded EV/start `-$45.01`
  - `control_stage_b_end14`: holdout funded EV/start `$4.63`, but raw holdout negative and OOS weaker than the leader
  - `control_stage_b_end13`: holdout raw was positive (`+5.52R`, PF `1.119`), but funded EV/start was still slightly negative at `-$2.56`

**Improvement-path follow-up (same family, pre-holdout primary / holdout secondary):**
- A dedicated micro-packet tested every narrow improvement path around the live family while keeping the thesis fixed:
  - structure: `htf60 n3`, `htf60 n5`, `htf30 n7`
  - entry end: `13:30`, `14:00`, `14:30`
  - ATR: `14`, `20`
  - lag: `0`, `5`, `8`, `10`, `12`, `15`
- The prettiest fixed validation rows were **not** the true downstream winners:
  - `htf30 n7 / 14:00 / atr20 / lag0` led the validation surface (`PF 1.311`, avg R `0.159`, Calmar `4.66`) but the already-seen holdout was flat-to-negative (`101` trades, PF `0.984`, avg R `-0.013`, funded EV/start `-$1.02`)
  - `htf60 n3 / 14:00 / atr14 / lag5` and `atr20 / lag8` had flashy secondary holdout reads, but they were much thinner on stitched OOS
- **New best restart point**: `htf60 n3 / 14:00 / atr20 / lag15`
  - config: `1m`, `long`, `close`, `08:30-14:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `htf60`, `n3`, `cap2`, `fvg=100/10`, `lag=15`, `atr=20`
  - stitched OOS: `292` trades, PF `1.281`, avg R `0.160`, funded payout `53.7%`, funded EV/start `$152.78`
  - secondary holdout read: `44` trades, PF `1.563`, avg R `0.298`, funded payout `35.9%`, funded EV/start `$137.56`
- **Secondary bench**: `htf60 n3 / 14:00 / atr20 / lag12`
  - stitched OOS: `261` trades, PF `1.252`, avg R `0.143`, funded EV/start `$128.00`
  - secondary holdout: `36` trades, PF `1.784`, avg R `0.382`, funded EV/start `$115.06`
- `htf60 n5` remains closed. One `14:30 / atr20 / lag12` row had a friendly secondary holdout, but pre-holdout quality stayed weak (`validation PF 1.051`, avg R `0.031`, Calmar `0.21`) and stitched OOS was only `PF 1.046`, avg R `0.028`.

**Local refinement around the promoted lead:**
- A second, smaller packet then refined only the promoted branch:
  - base: `htf60 n3 / 14:00 / atr20 / lag15 / fvg100/10`
  - OAT sweeps: `entry_end`, `atr_length`, `htf_n_left`, `left_minutes`, `right_minutes`, `lag`
  - interaction grid only on the remaining meaningful dimensions
- The important result was **not** another structural change. The same branch stayed best, and the only clean downstream improvement was a later cutoff:
  - **new best restart point**: `htf60 n3 / 14:30 / atr20 / lag15`
  - stitched OOS: `306` trades, PF `1.275`, avg R `0.156`, funded payout `55.5%`, funded EV/start `$173.12`
  - secondary holdout: `45` trades, PF `1.609`, avg R `0.314`, funded payout `35.9%`, funded EV/start `$151.99`
  - versus prior `14:00` lead: stitched funded EV/start `$152.78`, secondary holdout funded EV/start `$137.56`
- Useful but non-promoted temptations:
  - `right_minutes=8` was the prettiest OAT validation row (`PF 1.325`, avg R `0.182`, Calmar `3.20`) and had the strongest secondary holdout EV/start (`$193.29`), but stitched OOS dropped to funded EV/start `$107.54`
  - `lag16` improved fixed validation and kept healthy stitched OOS (`funded EV/start ~$132-134`) but did not beat the promoted `lag15 / 14:30` row
  - `htf_n_left=2` and `n2/lag14` combinations produced flashy secondary holdout reads (`funded EV/start ~$208.69`) but weaker stitched OOS (`$81.06-$106.65`), so they look more like holdout seduction than the next honest promotion
  - `left_minutes=80` was effectively identical to the base row; no real change

**Execution-side exact replay prototype (`1m + 1s`):**
- A bespoke replay was run through the live `LSIEngine` state machine using direct `1m` bars plus `1s` ticks, with `base_bar_minutes=1` added to the engine so the frozen `1m` branch could be tested honestly on the execution side.
- The branch stayed alive even before parity was fully closed. The first exact replay prototype underfilled relative to research (`368` vs `425` pre-holdout, `40` vs `45` holdout), but stayed positive on quality and funded economics, which justified debugging the exact engine instead of shelving the branch.
- A dedicated parity diff and day trace showed the missing trades came from two concrete bug families:
  - **HTF publication / retention** mismatch: research and exact replay were sometimes arming off different active HTF lows on the same day.
  - **Gap queue / lifecycle** mismatch: exact replay could keep an older pre-sweep gap alive while research preferred the new post-sweep gap.
- The first two execution-side fixes materially tightened parity:
  - `execution/src/trader/htf_levels.py` now publishes HTF levels on their fixed clock-time bucket boundary even when raw `1m` data is sparse, instead of delaying publication until the next observed bar.
  - `execution/src/trader/lsi_engine.py` now mirrors research gap ordering by putting the same-bar/post-sweep gap ahead of promoted pre-sweep gaps and deduping same-bar re-adds.
- After those fixes, the representative trace days `2016-08-22`, `2025-05-20`, and `2025-06-20` all matched on HTF level, entry minute, and chosen gap.
- The last residual then split into two smaller execution bugs:
  - **Sweep-retention bug**: if the sweep bar only promoted stale pre-sweep gaps that immediately failed `max_fvg_to_inversion_bars`, the live engine dropped the whole sweep instead of falling back to `WAITING_FOR_GAP` for a later post-sweep gap.
  - **HTF multi-trade rearm bug**: the `1s` exit path always went to `FLAT`, so same-day second HTF trades could not restart even when `htf_trade_max_per_session` still allowed them.
- Those two fixes were then applied in `execution/src/trader/lsi_engine.py`, and they closed the trade-gap side completely:
  - residual holdout dates `2025-06-23`, `2025-10-28`, `2026-02-13`, `2026-02-20`, and `2026-03-19` now all match on traced entry trade
  - full parity diff is now exact: `470` research filled trades vs `470` exact, with `425/425` pre-holdout and `45/45` holdout, `0` research-only, `0` exact-only, and `0` minute drift
- Exit-side debugging then found one more real replay bug: on sparse CL days with no `1m/1s` events inside the configured `15:50-16:00` flat window, research fell back to the last observed intraday bar (for example the common `14:29` print) while exact replay carried the position into the evening reopen and sometimes degraded `eod` / `tp1_eod` into `sl` / `tp1_be`. A new session-gap flat fallback in `execution/src/trader/lsi_engine.py` now forces a synthetic EOD exit at the last observed pre-gap bar, and the new regression test in `execution/tests/test_lsi_engine.py` locks that behavior in.
- The refreshed exact replay report is therefore a materially different read now:
  - **entry parity is closed and the dominant exit-type mismatch is closed on holdout**
  - exact pre-holdout is now slightly **better** than research overall: `425` trades, PF `1.233`, avg R `0.131`, total R `+55.70`, max DD `-21.49R` vs research PF `1.208`, avg R `0.120`, total R `+51.05`, max DD `-21.48R`
  - exact holdout is now essentially on top of research: `45` trades, PF `1.603`, avg R `0.313`, total R `+14.10`, max DD `-8.06R` vs research PF `1.609`, avg R `0.314`, total R `+14.14`, max DD `-8.09R`
  - exact holdout funded payout remains alive at `34.6%`, but EV/start is now effectively matched and slightly higher at `$155.67` vs research `$151.99`
- A dedicated exit diff confirms what remains:
  - holdout exit-type mismatches are now `0`; holdout net delta is only `-0.041R`, entirely from same-exit-type price/seconds drift
  - pre-holdout exit-type mismatches are down to `4`, dominated by three `sl -> tp1_be` exact improvements and one `eod -> tp1_be` downgrade on `2025-02-19`
- Read: the honest next debug target is no longer generic exit microstructure. It is a much smaller question around same-bar ambiguity and realized-price precision on already-matched exits. References: `backtesting/learnings/reports/CL_NY_HTF_LSI_PARITY_DIFF.md`, `backtesting/learnings/reports/CL_NY_HTF_LSI_GAP_TRACE.md`, `backtesting/learnings/reports/CL_NY_HTF_LSI_GAP_TRACE_HOLDOUT_RESIDUAL_AFTER_FIX.md`, `backtesting/learnings/reports/CL_NY_HTF_LSI_EXACT_REPLAY.md`, and `backtesting/learnings/reports/CL_NY_HTF_LSI_EXIT_DIFF.md`.

**Interpretation:**
- This is the first non-NQ cross-asset HTF-LSI branch that stayed meaningfully alive after holdout, even if only conditionally.
- The important difference from standard CL LSI is structure: HTF-LSI wants `1m` and `close` entry, not the broader same-timeframe CL LSI logic that was a hard no-go.
- Best remembered restart point is now `htf60 n3 / 14:30 / cap2 / atr20 / lag15`.
- `htf60 n3 / 14:00 / cap2 / atr20 / lag15` remains the main control and `htf60 n3 / 14:00 / cap2 / atr20 / lag12` is the next honest same-family bench.
- `htf30 n7` should still be remembered as the best **pre-holdout validation surface**, not the promoted restart point.
- The execution-side replay is now **trade-parity complete** and effectively holdout-parity complete on exits. Treat the remaining difference as a small exit-pricing / ambiguity-resolution problem, not an arming or session-boundary problem.

## Parameter Sensitivity

All parameter sensitivity findings from R1-R4 are **INVALID** — they were measured at sub-tick stop distances. The dominant "finding" (tight stops + high RR = best Calmar) was a simulator artifact.

## Prop Firm Considerations

CL continuation has no viable edge at realistic stop distances. Not deployable.

## Outstanding Questions

- Re-test continuation with stop_atr_pct range starting at 7%+ (realistic 10+ tick stops)
- Test other instruments for similar sub-tick stop contamination (GC, ES, NQ have wider ATR-to-tick ratios and are likely unaffected)
- Continuation long-only vs short-only at realistic stops
- Reversal / inversion strategies — sweep-gated reversal confirmed NO-GO, LSI DEFINITIVE NO-GO (baseline + 64-combo wide pivot sweep, see above). CISD variant not tested.
- Asia / LDN sessions on CL

---

## Regime-Gate Transfer Update (2026-04-01)

Cross-asset regime-gate transfer testing does **not** justify a deeper CL gating branch:

| Candidate | Ungated Holdout | Gated Holdout | Verdict |
|-----------|-----------------|---------------|---------|
| LDN-1 | +24.32R, Cal 1.054, DD -23.1R, PR 52.0% | +14.45R, Cal 0.626, DD -23.1R, PR 40.6% | REJECTS GATE |
| LDN-2 | +9.68R, Cal 0.385, DD -25.1R, PR 48.5% | +3.70R, Cal 0.157, DD -23.5R, PR 37.4% | MIXED |

### Updated Interpretation

1. **CL LDN-1 should remain ungated.** The gate removes too much holdout edge without improving drawdown.
2. **CL LDN-2 is too weak to promote.** The small drawdown improvement is not enough to offset the loss in net R, Calmar, and payout rate.
3. **Second-round decision**: de-prioritize CL for regime-gate work. If CL gets more attention, it should come from fresh continuation refinement rather than the NQ medium-vol gate.
