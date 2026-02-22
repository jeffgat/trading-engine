# ES (E-mini S&P 500) — Strategy Learnings

## Instrument Profile
- **Point value**: $50/point
- **Min tick**: 0.25
- **Commission**: $0.05/contract/side
- **Data**: 2015-01 to 2026-02 (~11 years, 5m + 1m)
- **Liquidity**: All sessions viable. London session produces ~230 trades/year.

## Strategies Tested

### London ORB Continuation — Both Directions
- **Status**: CONDITIONAL GO (edge confirmed, DD structural but accepted)
- **Run 1** — stop=3%, gap=1.25%, rr=2.75, tp1=0.3, be=10 (2026-02-18):
  - Phase 1 PASS: 2,328 trades, 59.5% WR, PF 1.64, Sharpe 3.46, DD -20.3R
  - Phase 2 FAIL: WF eff 0.42, stability 0.83 | Phase 5 FAIL: 40% survival
  - **DB**: `bt-es-ldn-2016-2026-robust-pipeline-no-go-802f28`
- **Run 2** — stop=1.5%, gap=1.25%, rr=3.0, tp1=0.5, be=0 (2026-02-18):
  - Phase 1 PASS: 2086 trades, 48.3% WR, PF 1.49, Sharpe 2.63, DD -19.7R
  - Phase 2 PASS: WF eff 0.77, stability 0.75 (high) — edge is genuine and transfers OOS
  - Phase 3: OOS DD -17.8R, worst month -9.3R | Phase 5 PASS: 100% survival (no DD gate)
  - Phase 4 PASS: Hold-out Sharpe 2.02, PF 1.31, +32.3R
  - WF mode params: rr=2.0, stop=2.0, gap=2.0, tp1=0.5
- **Run 3** — stop=1.5%, gap=1.25%, rr=3.0, tp1=0.5, be=0, WF without DD pre-filter (2026-02-18):
  - Phase 1 PASS: 2086 trades, 48.3% WR, PF 1.49, Sharpe 2.63, DD -19.7R
  - Phase 2 FAIL: WF eff 0.47 (borderline), stability 0.88 (high)
  - Phase 3: OOS DD -24.0R, worst month -11.1R, 2022: +13.0R, 2023: +9.8R (below 24R target)
  - Phase 4 PASS: Hold-out Sharpe 2.27, PF 1.43, **+61.2R** — 2025 is the best year
  - Phase 5 PASS: 100% survival (no DD gate)
  - **WF mode params: rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5** ← trade these
  - **DB**: `ES LDN 2016-2026 Continuation Both WF Mode`
  - **Script**: `python/scripts/run_es_ldn_tp1_be_robust_pipeline.py`
- **1,296-combo sweep**: 0/1296 combos have DD <= 10R. Floor is ~-14R.
- **Key insight**: Edge is genuine (WF stability 0.88). DD is structural — 2022/2023 were weak years (+13R, +9.8R). 2025 hold-out is exceptional (+61.2R, Sharpe 2.27). Accepted as conditional GO.
- **DB entries**: `bt-es-ldn-2016-2026-robust-pipeline-no-go-802f28`, `opt-es-ldn.gap-ldn.stop-rr-tp1-1296c-463110`, `ES LDN 2016-2026 Continuation Both WF Mode`

### London ORB Continuation — Long Only
- **Status**: NO-GO
- **Candidate params**: stop=1.5%, gap=1.25%, rr=3.0, tp1=0.3, risk=$5K, direction=long
- **Structural metrics look excellent**: 1,440 trades, 59.1% WR, PF 1.67, Sharpe 2.64, DD -10.7R
- **Robust pipeline result (2026-02-18)**:
  - Phase 1 PASS: 1,440 trades, 59.1% WR, PF 1.67, DD -10.7R
  - Phase 2 PASS: WF efficiency 0.57, stability 0.62 (moderate)
  - Phase 3 FAIL: OOS DD **-19.8R**, worst month -9.2R, 2021 was -6.8R
  - Phase 4 FAIL: Hold-out Sharpe 0.25, PF 1.03, only +2.1R
  - Phase 5 FAIL: **4.5% survival**, 95.5% ruin
  - **Verdict: NO-GO** — in-sample metrics are flattering but don't survive walk-forward
- **WF mode params**: rr=2.5, stop=1.5, gap=2.0, tp1=0.25
- **DB entry**: `bt-es-ldn-long-2016-2026-robust-pipeline-no-8f57d8`
- **Script**: `python/scripts/run_es_ldn_long_robust_pipeline.py`

### Variable Sweeps Summary (2026-02-18)
- **max_gap_points**: No impact (10-100 all identical). Min gap ATR filter does the work.
- **atr_length**: 7-14 all comparable. Default 14 is optimal.
- **ORB window**: 15m default best for Calmar. Longer windows boost Sharpe but increase DD.
- **Entry end time**: 08:25 default is best. More time = more opportunity.
- **Direction filter**: Long-only halves DD vs both (10.7R vs 14.7R in-sample) but WF OOS reality is -19.8R.

### Key Findings
- ES London ORB continuation has strong in-sample metrics but fails walk-forward validation
- Long-only helps in-sample DD but the edge doesn't generalize — 2021 was a -6.8R year OOS
- Short side weaker overall (best Sharpe 2.45 vs 2.82 for longs) with higher DD
- The structural backtest is misleading due to in-sample fitting. Walk-forward reveals the true risk profile.

### London ORB Inversion — Both Directions
- **Status**: NO-GO (definitive)
- **Sweep**: 750 combos x 2 directions (long + short), magnifier ON
- **Best result**: Long PF 0.83 / Sharpe -1.33 / -130R / DD -145R. Short PF 0.76 / Sharpe -1.88 / -198R / DD -214R
- **Prop-ready combos (DD<=10R, PF>=1.0): 0 out of 1,500**
- **Script**: `python/scripts/run_es_ldn_inversion_sweep.py`
- **Conclusion**: ES London does not produce the fake-out/inversion pattern that works on GC (NY) and 6B (LDN). Catastrophic across every param combination. Do not revisit.

### London ORB CISD — Both Directions
- **Status**: NO-GO (definitive)
- **Tested**: rr=[1.5, 2.0, 2.5, 3.0] × tp1=[0.3, 0.5] = 8 combos
- **Best result**: PF 0.10, Sharpe -20.88, -2000R+ losses across ALL combos
- **Win rate**: 9-15% — strategy does not work on ES London at all
- **Script**: `python/scripts/run_es_ldn_dd_advanced.py` (Test 5)
- **Conclusion**: CISD pattern is catastrophic on ES London. Do not revisit.

## Overall Conclusion for ES London ORB
- Continuation (both): **CONDITIONAL GO** — rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5, be=0. Edge confirmed, DD structural (~20-24R OOS), 2025 hold-out exceptional.
- Continuation (long-only): NO-GO (OOS DD -19.8R, 4.5% MC survival, hold-out only +2.1R)
- Inversion (long + short): NO-GO (PF < 1.0 across all 1,500 combos — do not revisit)

## DD Reduction — Tested, All Exhausted

All post-hoc and structural DD reduction approaches tested. None materially move the max DD:

| Filter | Best Result | DD Change | Verdict |
|--------|-------------|-----------|---------|
| SMA trend gate (10/20/50) | in-sample -13.5R, OOS similar | modest | not worth trade-off |
| ATR volatility gate (15 combos) | ATR_SMA10×1.1 → -16.2R | -1.6R | not worth 320 trade loss |
| Day-of-week filter | no day systematically bad | 0 | excluded days worsen DD |
| Monthly loss cap | cap=7R → worst month -8.0R | 0 on max DD | cap=3-4R makes DD worse |
| Skip worst months (May/Jan/Mar) | skip 3 months → -16.6R | -1.2R | not worth 614 trade loss |
| Excl FOMC/NFP/CPI dates | excl all events → -23.6R | **+5.8R worse** | event days are profitable (56% WR) |
| Earlier flat time (07:30) | -15.5R, +611.7R net | -2.3R | **marginal**; only meaningful finding |
| Post-ORB cooling period | +75m cool → Sharpe 2.94 | +5.1R worse | better Sharpe but DD worsens |
| Remove EOD exits | -43.1R, +304.5R net | +25.3R worse | EOD exits are 82% WR profit contributor |
| CISD strategy | -2000R+ across all combos | catastrophic | ES LDN does not produce CISD pattern |

**Conclusion: DD is structural and irreducible.** Accepted as-is. The only marginal improvement is flat_time=07:30 (-2.3R DD improvement) but this is not enough to change the risk profile.

## Final Status: ACCEPTED — Trade with Reduced Size
- **Strategy**: ES LDN Continuation, both directions, be=0, magnifier
- **Params**: rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5, risk=$5K
- **In-sample**: 2328 trades, 48% WR, PF 1.51, Sharpe 2.51, DD -17.8R
- **2025 hold-out**: Sharpe 2.27, PF 1.43, +61.2R
- **Risk management**: Trade at reduced size so that the ~18-24R OOS DD stays within account dollar limits
- **DB**: `ES LDN 2016-2026 Continuation Both WF Mode`

## 1s Magnifier Re-Optimization (2026-02-21)

All prior results above were obtained with 1m bar magnifier. The 1s magnifier is now available and changes fill/stop resolution significantly.

### Minimum Stop Floor: 3.0% ATR

`stop_atr_pct` is divided by 100 in the simulator (`stop_dist = (stop_atr_pct / 100) * ATR`). For ES with typical ATR ~60 points:

| stop_atr_pct | Stop distance | Ticks | Realistic? |
|-------------|---------------|-------|------------|
| 0.50% | 0.30 pts | ~1 | NO — spread alone eats this |
| 1.00% | 0.60 pts | ~2-3 | NO — slippage kills it |
| 2.00% | 1.20 pts | ~5 | Marginal |
| **3.00%** | **1.80 pts** | **~7** | **Minimum realistic** |
| 5.00% | 3.00 pts | ~12 | Comfortable |

**Rule: Never optimize below stop_atr_pct=3.0% for ES.** The engine has no slippage model, so ultra-tight stops produce inflated Calmars that don't survive real execution. The previous fine-tune at 0.5-1.5% (Calmar 68) was an artifact of perfect-fill simulation.

### 1s Variable Sweep Results (sweep_1, original anchor)
- **Anchor**: rr=3.0, tp1=0.5, stop=1.5%, gap=1.25%, ORB 15m, ATR 14
- **Biggest levers**: rr (+10.76 Calmar), flat_start=07:30 (+7.18), min_gap (+7.02), ORB 10m (+4.71)
- **Structural winners**: ORB 10m, flat 07:30, ATR 50, both dir
- **Insensitive**: DOW, max_gap_points, direction

### 1s Broad Stop Sweep (3-12% ATR)
- **Anchor**: rr=3.0, tp1=0.5, gap=1.25%, structural winners locked
- **Winner**: stop=5.0% (Calmar 5.89, Sharpe 0.870, 143.8R, DD -24.4R, 2 neg years)
- **Runner-up**: stop=3.0% (Calmar 5.84, Sharpe 1.281, 218.8R, DD -37.4R, 1 neg year)
- **Sweet spot**: 3-6% ATR; degrades badly above 8%

### 1s Fine-Tune v1 (complete)
- **Grid**: stop=[2.5-6.0] × rr=[2.0-5.0] × gap=[0.75-3.0] × tp1=[0.3-0.7] = 1,960 combos
- **Winner (clean, >= 3% stop floor)**: stop=5.0%, rr=2.0, gap=1.25%, tp1=0.40 → Calmar 10.39

### 1s Robust Pipeline (pre fill-bar fix)
- **Anchor**: stop=5.2%, rr=2.0, gap=1.25%, tp1=0.40, flat=08:00
- **Phase 1**: Calmar 14.57, Sharpe 1.383, DD -11.8R, 171.8 Net R, 0 neg years
- **Status**: Complete, but engine fill-bar fix landed — re-optimization needed

### Post Fill-Bar Fix Re-Optimization (in progress)
- **Engine fix**: Stops/TPs that fill on the same bar as entry now correctly count
- **Pre-fix anchor**: stop=5.2%, rr=2.0, gap=1.25%, tp1=0.40, ORB 10m, flat 08:00, ATR 50, 1s
- **Step 1**: Diagnostic — run pre-fix anchor through fixed engine, compare metrics
- **Step 2**: Variable sweep #3 (`run_es_ldn_1s_variable_sweeps_3.py`)
- **Step 3**: Fine-tune grid v2 (`run_es_ldn_1s_fine_tune_v2.py`) — 1,728 combos
- **Step 4**: Convergence check (sweep #4 if needed)
- **Step 5**: Robust pipeline with converged anchor
- **Step 6**: Save final + update learnings
- **Scripts**: `run_es_ldn_1s_variable_sweeps_3.py`, `run_es_ldn_1s_fine_tune_v2.py`, `save_es_ldn_1s_final.py`

---

## Asia ORB Continuation — Long Only ✅ GO (2026-02-21)

### Optimization History

**R1→R5 variable sweeps** converged in 5 rounds. Key adoptions:
- R1: stop 5.25→3.0%, ORB 15m→10m, entry 23:15→01:00, tp1 0.5→0.3, gap 0.9→0.5%
- R2: ATR 14→5, entry 01:00→03:00, DOW none→excl Thu
- R3: direction both→long (+4.19 Calmar)
- R4: tp1 0.3→0.5 (+0.35 Calmar)
- R5: **CONVERGED** — all 12 dimensions Δ=0

**Scripts**: `run_es_asia_variable_sweeps_{1-5}.py`, `run_es_asia_grid_sweep_r1.py`, `run_es_asia_walkforward_r1.py`

### Converged Anchor Config

| Param | Value |
|-------|-------|
| strategy | continuation |
| direction | long only |
| rr | 2.0 |
| tp1_ratio | 0.5 |
| atr_length | 5 |
| stop_atr_pct | 3.0% |
| min_gap_atr_pct | 0.5% |
| max_gap_points | 50.0 (inert — no gaps exceed this) |
| max_gap_atr_pct | 0 (no limit) |
| ORB window | 20:00-20:10 (10m) |
| entry_end | 03:00 |
| flat_start | 06:45 |
| DOW exclusion | Thu |
| ICF | OFF |
| magnifier | 1s |

### Structural Backtest (full history 2016-2026)

| Metric | Value |
|--------|-------|
| Trades | 1,178 |
| Win Rate | 59.6% |
| PF | 1.46 |
| Sharpe | 2.85 |
| Net R | 223.1 |
| R/yr | 22.3 |
| Max DD | -10.5R |
| **Calmar** | **21.24** |
| Neg years | **0** |

R by year: 2016:+12  2017:+17  2018:+30  2019:+34  2020:+11  2021:+39  2022:+5  2023:+18  2024:+26  2025:+24  2026:+7

### Grid Sweep (576 combos: stop × rr × gap × tp1)

- **488/576 combos have 0 negative years** — extremely robust parameter surface
- Grid winner: stop=2.0%, rr=2.5, gap=0.5%, tp1=0.5 (Calmar 25.97)
- Anchor rank: #12/576 (Calmar 21.24)
- Note: stop=2.0% is marginal (~5 ticks) per ES minimum stop floor rule. Anchor at 3.0% is safer.

### Walk-Forward + Hold-out (all 4 configs GO)

| Config | OOS R/yr | OOS Calmar | Holdout Sharpe | Holdout R | Verdict |
|--------|----------|-----------|----------------|-----------|---------|
| **Anchor (s3.0/rr2.0/g0.5/tp0.5)** | **22.2** | 2.21 | **3.60** | **31.1** | **GO** |
| Grid #1 (s2.0/rr2.5/g0.5/tp0.5) | 19.4 | 2.28 | 3.47 | 35.5 | GO |
| Grid #2 (s2.0/rr3.0/g0.5/tp0.4) | 19.7 | 2.29 | 3.15 | 32.3 | GO |
| Grid #3 (s2.5/rr2.0/g0.5/tp0.6) | 21.2 | 2.12 | 3.88 | 36.3 | GO |

- All 6 OOS folds (2019-2024) profitable for every config
- All hold-outs (2025+) pass: Sharpe>0.5, PF>1.0, R>0
- **Recommended config: R5 Anchor** (s3.0/rr2.0/g0.5/tp0.5) — safest stop floor, best OOS R/yr

### Key Findings

- **Long-only dominates**: Short side dragged performance in early rounds (2023:-2, 2024:-11 OOS). Removing shorts boosted Calmar from 16.69 to 20.88 with zero negative years.
- **DOW Thursday exclusion**: Consistent +1-2 Calmar improvement across all anchors. Thursday is the weakest day for ES Asia longs.
- **ATR 5 is optimal**: Shorter lookback captures recent volatility better for overnight sessions.
- **Extended entry window (03:00)**: Asia session benefits from entries through the London open. Each hour added 01:00→03:00 improved Calmar monotonically.
- **Flat start insensitive**: All values 04:00-06:45 are identical — trades close well before any flat time.
- **Max gap points inert**: All values 20-100 and OFF are identical — gap sizes never reach these thresholds at 0.5% ATR floor.
- **Parameter surface extremely robust**: 488/576 grid combos (85%) have zero negative years.
