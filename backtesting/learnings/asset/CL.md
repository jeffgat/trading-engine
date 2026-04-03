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
- **2023 concentration**: LDN-1/2/3 all have +34-44R in 2023, which is ~30% of total R from one year
- **This completely overturns the prior CL NO-GO** — the issue was NY session + sub-tick ATR stops, not the instrument itself. LDN longs with realistic stops (ATR 8%) produce a genuine edge.

**Recommended configs for further optimization:**
- **LDN-2** (best holdout PR 55.0%, highest DSR 0.294): 30m ORB, ATR 8%, RR 3.0, TP1 0.6, long
- **LDN-1** (best holdout R +12.8): 30m ORB, ATR 8%, RR 3.5, TP1 0.6, long

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
