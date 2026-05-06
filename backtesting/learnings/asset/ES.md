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

### London ORB Continuation — Both Directions (Fresh Full Optimization, 2026-02-22)
- **Status**: NO-GO (2/5 phases passed at best — overfit)
- **Workflow**: Full optimization skill — baseline → 12 rounds variable sweeps → 2 grid sweeps → robust pipeline
- **Converged anchor** (R11): stop=6.0%, rr=4.0, gap=1.0%, tp1=0.5, ATR=14, max_gap=20%ATR, ORB 10m, flat 08:20, entry 08:25, DOW excl Mon, ICF off, 1s mag
  - In-sample: Calmar 9.18, Sharpe 1.168, 191.5R net, -20.9R DD, 0 neg years
  - R by year: 2016:+4, 2017:+12, 2018:+34, 2019:+28, 2020:+30, 2021:+34, 2022:+0, 2023:+15, 2024:+29, 2025:+5
- **R11 Pipeline result (rr=4.0 anchor)**: NO-GO 1/5
  - Phase 1 PASS: Calmar 9.18, 0 neg years
  - Phase 2 FAIL: WFE 0.441, stability 0.928 (high). OOS negative in 2021 (-6R), 2022 (-1.8R), 2025 (-0.3R)
  - Phase 3 FAIL: Avg annual R 11.6R (need 12.0), worst month -11.9R
  - Phase 4 FAIL: 2025 holdout Sharpe 0.306, only 5.4R
  - Phase 5 FAIL: 81% ruin at -25R, 19% survival
- **R12 refinement**: DD reduction sweep → TP1 0.5→0.75, flat 08:20→08:00 improved Calmar 9.18→10.18
  - In-sample: Calmar 10.18, Sharpe 1.127, 206.7R net, -20.3R DD, 1 neg year (2016:-0.8R)
  - R by year: 2016:-1, 2017:+17, 2018:+31, 2019:+30, 2020:+40, 2021:+23, 2022:+0, 2023:+22, 2024:+39, 2025:+2
- **R12 Pipeline result**: NO-GO 2/5 (improved from 1/5)
  - Phase 1 PASS: Calmar 10.18, WR 33.9%, PF 1.19
  - Phase 2 PASS: WFE 0.591, stability 0.857 (high). WF mode: rr=3.5, tp1=0.6, stop=6.0, gap=1.0
  - Phase 3 FAIL: Worst month -8.9R (limit 5.0R). Avg annual R 16.4R passes.
  - Phase 4 FAIL: 2025 holdout Sharpe 0.214, only +4.1R
  - Phase 5 FAIL: 91.8% ruin at -25R, 8.2% survival. MC p50 DD -36.1R
- **Key findings**:
  - ATR oscillated (3↔20) across rounds, resolved by grid sweep (landed at 7→10→14)
  - Grid sweeps found high Calmars (8.47-9.18) but only 2-3% of combos had 0 neg years — fragile surface
  - Stop=6.0% is a very narrow peak — 0.1% change in either direction introduces negative years
  - DD is structural and irreducible: swept TP1, RR, flat, entry end, direction, DOW, gap — nothing materially moves DD
  - Strategy produces attractive in-sample metrics but does NOT generalize: MC p50 DD is -36R vs in-sample -20R
  - 2022 and 2025 are consistently weak in OOS across all anchors
  - Higher TP1 (0.75) improved WFE (0.441→0.591) and earned Phase 2 PASS, but MC survival worsened (19%→8%)
  - Min stop floor: 10 ticks (5.0% ATR) for ES, but optimal was 6% in this optimization
- **DB**: `bt-es-ldn-continuation-both-2016-2026-full-f75b08` (R11), `bt-es-ldn-continuation-both-2016-2026-full-bf6270` (R12)
- **Scripts**: `run_es_ldn_baseline.py`, `run_es_ldn_variable_sweeps_{1-12}.py`, `run_es_ldn_grid_sweep_r{1-2}.py`, `run_es_ldn_robust_pipeline.py`, `run_es_ldn_stop_sweep.py`, `run_es_ldn_dd_sweep.py`

### London ORB Continuation — Long Only (R12 config, direction split)
- **Status**: EXPLORATORY — long side carries 81% of R but ORB%-based sizing underperforms ATR%
- **R12 config long-only**: stop_atr=6.0%, gap_atr=1.0%, rr=4.0, tp1=0.75, ORB 10m, flat 08:00, ATR 14, 1s mag
  - 1,373 trades, 35.3% WR, 140.8R net, PF 1.17, Sharpe 1.033, Calmar 4.66, DD -30.2R
  - 2 neg years (2022:-11.6R, 2026:-0.4R)
  - R by year: 2016:+7 2017:+21 2018:+12 2019:+8 2020:+33 2021:+15 2022:-12 2023:+5 2024:+50 2025:+3 2026:-0.4
  - **DB**: `bt-es-ldn-continuation-long-2016-2026-full-410ed0`
- **R12 config short-only**: same params, direction=short
  - 1,246 trades, 30.0% WR, 41.0R net, PF 1.05, Sharpe 0.317, Calmar 0.87, DD -47.3R
  - 6 neg years — carried entirely by 2018 (+49.9R)
  - **DB**: `bt-es-ldn-continuation-short-2016-2026-full-f6b478`
- **ORB%-based sizing test** (long-only): swept stop_orb_pct=20-100, min_gap_orb_pct=5-30
  - Best: stop_orb=30%, gap_orb=20% → 1,185 trades, Calmar 3.11, Sharpe 0.943, DD -39.3R
  - ATR-based is better across all metrics (Calmar 4.66 vs 3.11, DD -30.2R vs -39.3R)
  - **TODO**: ORB% might perform better if optimized from scratch as anchor (not just swapped into ATR-optimized config). Worth a future full optimization with ORB% as the base sizing method.
  - **DB**: `opt-es-ldn.orbgap-ldn.orbstop-54c-c038d0`

### London ORB Continuation — Long Only (earlier test)
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
- **Status**: INVALIDATED — prior results tested without liquidity sweep gate. Needs re-testing with sweep-gated reversal/inversion definition.

### London ORB CISD — Both Directions
- **Status**: NO-GO (definitive)
- **Tested**: rr=[1.5, 2.0, 2.5, 3.0] × tp1=[0.3, 0.5] = 8 combos
- **Best result**: PF 0.10, Sharpe -20.88, -2000R+ losses across ALL combos
- **Win rate**: 9-15% — strategy does not work on ES London at all
- **Script**: `python/scripts/run_es_ldn_dd_advanced.py` (Test 5)
- **Conclusion**: CISD pattern is catastrophic on ES London. Do not revisit.

## Overall Conclusion for ES London ORB
- Continuation (both, 1m magnifier): **CONDITIONAL GO** — rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5, be=0. Edge confirmed, DD structural (~20-24R OOS), 2025 hold-out exceptional.
- Continuation (both, 1s magnifier full optimization): **NO-GO** — best in-sample Calmar 10.18 (R12) but 2/5 pipeline phases pass. MC ruin 92%, holdout Sharpe 0.21. Edge does not generalize.
- Continuation (long-only): NO-GO (OOS DD -19.8R, 4.5% MC survival, hold-out only +2.1R)
- Inversion (long + short): INVALIDATED — needs re-testing with sweep-gated definition

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

### Dual Floor: min_stop_points + min_tp1_points (CRITICAL)

The 10-tick median stop rule catches unrealistically tight stops, but it does NOT catch degenerate TP1 placement. With low rr × tp1_ratio, TP1 can land trivially close to entry, producing inflated win rates (90%+) that don't survive real execution.

**Example of the problem** (ES NY Long R3-R8 core convergence):
- stop_atr_pct=6.0%, rr=2.0, tp1_ratio=0.2 → TP1 = rr × risk × tp1 = 2.0 × 3.3 × 0.2 = **1.32 pts (~5 ticks)**
- TP1 at 40% of stop distance → 91.6% WR, Calmar 30.83 — completely unrealistic
- After TP1, stop moves to BE → worst case is +0.1R on half, 0R on half = noise wins
- The optimizer oscillated for 6 rounds chasing this degenerate pattern

**Fix**: Use `min_stop_points=3.0` and `min_tp1_points=3.0` in SessionConfig for ES (12 ticks each). This ensures:
- Stop is at least 3.0 points regardless of ATR% calculation
- TP1 is at least 3.0 points from entry — a genuine directional move, not noise

**Rule: Always set `min_stop_points=3.0` and `min_tp1_points=3.0` for ES in all sweeps, grids, and final configs.** Without these floors, the optimizer exploits degenerate rr×tp1 combos that produce inflated metrics.

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

## Asia ORB Continuation — Long Only ✅ CONDITIONAL GO (2026-02-23)

*Note: Previous Asia results (2026-02-21) were based on bad data and have been invalidated. This section reflects a complete re-optimization from scratch.*

### Optimization History

**Full optimization workflow**: Baseline → R1 stand-alone (13 dims) → R2-R3 core convergence → Grid R1 → R4 stand-alone re-sweep → R5-R6 core convergence → Grid R2 → Robust pipeline.

Key adoptions:
- R1 (stand-alone): stop ATR 5.25% → ORB 125% (+3.79 Calmar), entry 23:15 → 03:00 (+4.79), SMA OFF → 100 (+0.91)
- R2 (core): rr 2.5 → 1.5 (+0.77)
- R3 (core): **CONVERGED** — 0 adoptions (Calmar 7.65)
- Grid R1: Winner stop=125, rr=2.0, gap=0.5, tp1=0.7 (Calmar 11.82 vs anchor 7.65, Δ+4.16) → anchor changed
- R4 (stand-alone re-sweep): flat 06:45 → 07:00 (+0.54), SMA 100 → OFF (+0.53)
- R5 (core): rr 2.0 → 1.5 (+1.31)
- R6 (core): **CONVERGED** — 0 adoptions (Calmar 14.68)
- Grid R2: Anchor confirmed at #2/900 (Calmar 14.68, Δ=0.00). 672/900 combos have 0 neg years.

**Scripts**: `run_es_asia_long_baseline.py`, `run_es_asia_long_variable_sweeps_{1-6}.py`, `run_es_asia_long_grid_sweep_r{1-2}.py`, `run_es_asia_long_robust_pipeline.py`, `save_es_asia_long_r1_final.py`

### Final Config

| Param | Value |
|-------|-------|
| strategy | continuation |
| direction | long only |
| rr | 1.5 |
| tp1_ratio | 0.7 |
| atr_length | 14 |
| stop_orb_pct | 125.0% |
| stop_atr_pct | 0.0 (ORB% sizing) |
| min_gap_atr_pct | 0.5% |
| min_stop_points | 3.0 |
| min_tp1_points | 3.0 |
| ORB window | 20:00-20:15 (15m) |
| entry_end | 03:00 |
| flat_start | 07:00 |
| DOW exclusion | none |
| SMA trend gate | OFF |
| ICF | OFF |
| magnifier | 1s |

### Structural Backtest (full history 2016-2026)

| Metric | Value |
|--------|-------|
| Trades | 1,454 |
| Win Rate | 55.1% |
| PF | 1.28 |
| Sharpe | 1.90 |
| Net R | 183.3 |
| R/yr | 18.3 |
| Max DD | -12.5R |
| **Calmar** | **14.68** |
| Neg years | **0** |
| Median stop | 15.0 ticks |

R by year: 2016:+15  2017:+15  2018:+12  2019:+24  2020:+14  2021:+8  2022:+19  2023:+20  2024:+18  2025:+33  2026:+4

### Robust Pipeline Result

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | **PASS** | 1454 trades, 55.1% WR, PF 1.28, Calmar 14.68 |
| 2 — Walk-Forward | **PASS** | WF eff 0.834, stability 0.893 (high) |
| 3 — Prop Filter | **FAIL** | Worst month -8.7R > 5.0R cap in WF OOS |
| 4 — Hold-Out OOS | **PASS** | 164 trades, PF 1.56, Sharpe 3.47, +37.6R |
| 5 — Monte Carlo | **PASS** | 89.7% survival at -25R ruin |
| **Verdict** | **CONDITIONAL** | 4/5 passed |

### WF Fold Details

| Fold | IS Period | OOS Period | IS Sharpe | OOS Sharpe | Best Params |
|------|-----------|-----------|-----------|------------|-------------|
| 1 | 2016-2019 | 2019 | 1.653 | 2.421 | stop=125, rr=1.75, gap=0.75, tp1=0.7 |
| 2 | 2017-2020 | 2020 | 2.113 | 1.717 | stop=125, rr=1.75, gap=0.75, tp1=0.7 |
| 3 | 2018-2021 | 2021 | 2.168 | 1.113 | stop=150, rr=1.75, gap=0.5, tp1=0.8 |
| 4 | 2019-2022 | 2022 | 2.200 | 2.433 | stop=150, rr=1.75, gap=0.5, tp1=0.8 |
| 5 | 2020-2023 | 2023 | 2.546 | 0.533 | stop=150, rr=1.75, gap=0.25, tp1=0.8 |
| 6 | 2021-2024 | 2024 | 2.229 | 1.601 | stop=125, rr=1.75, gap=0.25, tp1=0.8 |
| 7 | 2022-2025 | 2025 | 2.280 | 2.852 | stop=125, rr=1.25, gap=0.25, tp1=0.8 |

- **rr=1.75 selected in 6/7 folds** — very stable, slightly above anchor's 1.5
- **tp1=0.8 selected in 5/7 folds** — stable, slightly above anchor's 0.7
- stop oscillates 125-150, gap oscillates 0.25-0.75 — all near anchor values
- All OOS folds positive, 2023 weakest (Sharpe 0.533)

### Key Findings

- **ORB%-based stops dominate ATR%**: stop_orb=125% (Calmar 11.82) vs best ATR stop=7.0% (Calmar 9.71). ORB% sizing naturally scales with the opening range.
- **SMA trend gate: dropped in R4**: At the post-grid anchor, SMA=OFF (Calmar 12.34) beats SMA=100 (Calmar 11.82). The gate was helpful at the earlier anchor but became suboptimal after gap/tp1 shifted.
- **No DOW exclusion**: Friday exclusion showed +1.44 Calmar but introduced 2018 as negative year. Thursday/Mon exclusions hurt. None adopted.
- **Flat 07:00 optimal**: Slight improvement over 06:45. Trades run to the NY open.
- **Extended entry window (03:00)**: Consistent finding — Asia session benefits from entries through the London open.
- **Phase 3 failure is borderline**: Worst month -8.7R in WF OOS slightly over 5.0R cap. Not a structural concern.
- **MC survival strong**: 89.7% at -25R. MC p50 DD -17.0R, p95 DD -27.9R.
- **Extremely robust parameter surface**: 672/900 grid combos (75%) have zero negative years.
- **WF stability exceptionally high**: 0.893. Parameters cluster tightly around anchor values across all folds.

### DB Entry
- **ID**: `bt-es-asia-cont-long-2016-2026-final-6f79d8`
- **Name**: `ES Asia Cont Long 2016-2026 Final`

---

## NY ORB Continuation — Long Only ✅ CONDITIONAL GO (2026-02-23)

### Optimization History

**R1-R2 stand-alone sweeps**, then **R3-R12 core convergence** (3 dims: stop, rr, tp1). R5-R7 invalidated due to degenerate TP1 (see Dual Floor section). Reset to R4 anchor with dual floor in R8. Converged at R12.

Key adoptions across rounds:
- R1: atr_length 14→7, rr 2.5→3.5, gap 2.25→0.5% (ATR% beats ORB% for both stop and gap sizing)
- R2: rr 3.5→5.0, tp1 0.5→0.2, DOW none→excl Thu
- R3-R4: stop 7.5→6.0, rr/tp1 oscillation began (degenerate TP1 issue)
- R5-R7: **INVALIDATED** — no dual floor, 91.6% WR artifacts
- R8 (reset to R4 + dual floor): rr 2.0→4.0
- R9: tp1 0.4→0.2
- R10: stop 6.0→5.0
- R11: rr 4.0→5.0
- R12: **CONVERGED** — 0 adoptions

**Grid R1** (600 combos): winner gap=0.25 (Δ+1.31 Calmar). Adopted, re-swept as R13.
**R13**: CONVERGED (0 adoptions with new gap). **Grid R2** confirmed: anchor is #1/600 (Δ+0.00).

**Scripts**: `run_es_ny_long_baseline.py`, `run_es_ny_long_variable_sweeps_{1-13}.py`, `run_es_ny_long_grid_sweep_r{1-2}.py`, `run_es_ny_long_robust_pipeline.py`, `save_es_ny_long_final.py`

### Final Config

| Param | Value |
|-------|-------|
| strategy | continuation |
| direction | long only |
| rr | 5.0 |
| tp1_ratio | 0.2 |
| atr_length | 7 |
| stop_atr_pct | 5.0% |
| min_gap_atr_pct | 0.25% |
| min_stop_points | 3.0 |
| min_tp1_points | 3.0 |
| ORB window | 09:30-09:45 (15m) |
| entry_end | 13:00 |
| flat_start | 15:50 |
| DOW exclusion | Thu |
| ICF | OFF |
| magnifier | 1s |

### Structural Backtest (full history 2016-2026)

| Metric | Value |
|--------|-------|
| Trades | 866 |
| Win Rate | 61.3% |
| PF | 1.42 |
| Sharpe | 2.28 |
| Net R | 142.8 |
| R/yr | 14.3 |
| Max DD | -10.4R |
| **Calmar** | **13.74** |
| Neg years | **0** |
| Median stop | 12 ticks |

R by year: 2016:+18  2017:+25  2018:+4  2019:+11  2020:+16  2021:+20  2022:+15  2023:+13  2024:+2  2025:+16

### Robust Pipeline Result

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | **PASS** | 866 trades, 61.3% WR, PF 1.42, Calmar 13.74 |
| 2 — Walk-Forward | **PASS** | WF eff 0.776, stability 0.893 (high), tp1=0.2 in 7/7 folds |
| 3 — Prop Filter | **FAIL** | Avg annual R < 12R (2024 only +2.0R in WF OOS), worst month -6.0R |
| 4 — Hold-Out OOS | **PASS** | 101 trades, PF 1.55, Sharpe 2.83, +18.2R |
| 5 — Monte Carlo | **PASS** | 97.3% survival at -25R ruin |
| **Verdict** | **CONDITIONAL** | 4/5 passed |

### WF Fold Details

| Fold | IS Period | OOS Period | IS Sharpe | OOS Sharpe | Best Params |
|------|-----------|-----------|-----------|------------|-------------|
| 1 | 2016-2019 | 2019 | 2.480 | 1.494 | stop=4.5, rr=4.5, gap=0.0, tp1=0.2 |
| 2 | 2017-2020 | 2020 | 2.180 | 1.532 | stop=5.5, rr=5.0, gap=0.0, tp1=0.2 |
| 3 | 2018-2021 | 2021 | 1.850 | 3.552 | stop=5.0, rr=4.5, gap=0.0, tp1=0.2 |
| 4 | 2019-2022 | 2022 | 2.837 | 2.485 | stop=4.5, rr=5.0, gap=0.0, tp1=0.2 |
| 5 | 2020-2023 | 2023 | 3.240 | 1.903 | stop=5.0, rr=4.5, gap=0.5, tp1=0.2 |
| 6 | 2021-2024 | 2024 | 3.116 | 0.341 | stop=5.5, rr=4.5, gap=0.5, tp1=0.2 |
| 7 | 2022-2025 | 2025 | 2.026 | 2.455 | stop=5.0, rr=5.0, gap=0.5, tp1=0.2 |

- **tp1=0.2 selected in 7/7 folds** — extremely stable
- stop oscillates tightly 4.5-5.5, rr oscillates 4.5-5.0 — all within grid range
- 2024 is the weak OOS year (Sharpe 0.341) — drives Phase 3 failure

### Key Findings

- **ATR% vs ORB%**: ATR% sizing wins for both stop (Calmar 1.70 vs 1.67) and gap (3.55 vs 2.35). Tested in R1.
- **Dual floor critical**: Without `min_stop_points=3.0` and `min_tp1_points=3.0`, the optimizer exploits degenerate rr×tp1 combos producing 91.6% WR artifacts. Rounds R5-R7 were invalidated by this issue.
- **DOW Thursday exclusion**: Consistent +1.6 Calmar improvement.
- **Gap insensitive**: Gap values 0.0-0.5% ATR produce nearly identical results. Anchor at 0.25%.
- **Phase 3 failure is borderline**: Only fails because 2024 WF OOS is weak (+2.0R) dragging avg annual R below 12R. Worst month -6.0R is 1R over 5.0R cap. Not a structural concern.
- **MC survival excellent**: 97.3% at -25R ruin. p50 DD -13.8R, p95 DD -23.0R.
- **Parameter surface robust**: Grid R2 top 20 all have Calmar 12.3-13.7 with identical tp1=0.2.

### DB Entry
- **ID**: `bt-es-ny-cont-long-2016-2026-final-650260`
- **Name**: `ES NY Cont Long 2016-2026 Final`

### ALPHA_V1-A Live Retention Note (2026-05-05)

- **Status**: CONDITIONAL — keep in research portfolio, demote or pause live risk at `$400`
- **Context**: Active `ALPHA_V1-A` execution config runs `ES_NY` at `$400` risk even though the ALPHA sizing table originally preferred `$300` and warned `$400` degraded first-payout behavior.
- **Exact production replay evidence** (`2016-04-17` to `2026-03-24`): `506` trades, `+71.13R`, `55.34%` WR, `PF 1.33`, `-12.00R` DD. Last 1y: `57` trades, `+18.88R`, `61.40%` WR, `PF 1.996`, `-6.00R` DD.
- **Portfolio contribution**: Removing ES_NY from the same exact replay reduces full-history ALPHA_V1 R from `+445.45R` to `+374.33R`, while improving DD only slightly (`-14.89R` to `-14.42R`). It adds R historically but is not essential to portfolio viability.
- **Live DB sample** (`2026-04-15` to `2026-05-05`): `7` closed trades, `-4.0R` / `-$1,600` at `$400`, with `5` stopouts, `2` TP1-to-BE partials, and `0` full TP2 exits. This confirms the uncomfortable payoff mode: if TP2s dry up, `+0.5R` partials cannot carry the leg.
- **Operating read**: Do not invalidate the ES NY ORB edge from 7 live trades, but do not keep the aggressive `$400` sizing while live behavior is failing. Prefer `$200-$300` risk or a temporary pause until post-`2026-03-24` data can be exact-replayed.

### ES_NY ORB Wide-Stop Target Sweep (2026-05-05)

- **Report**: `backtesting/learnings/reports/NQ_ES_NY_ORB_WIDE_STOP_TARGET_SWEEP_20260505.md`
- **Scope**: Held ES_NY ORB structure fixed (`09:30-09:45` ORB, long-only, ATR 7, gap 0.25% ATR, entry to 13:00, flat 15:50, excl-Thu, `min_stop_points=3`, `min_tp1_points=3`, 1s magnifier) and swept ATR/ORB stop width, `rr`, and TP1 distance.
- **Baseline in common ALPHA window (`2016-04-17` to `2026-03-24`)**: `ATR 5% / rr 5.0 / tp1 0.2` -> median stop `12.0` ticks, `+126.6R`, `PF 1.39`, `-10.9R` DD, last-1y `+18.2R`, last-2y `+21.4R`.
- **Conclusion**: NO-GO for replacing ES_NY with a wider-stop variant. Zero rows widened the actual median stop by at least `20%` while preserving full-history, recent-window, PF, and DD quality. `ATR 6%` and `ORB 25%` did not actually widen median stop because the `3pt` minimum stop floor dominated. The first meaningful wider rows were `ATR 10%+`, `ATR 12%+`, and `ORB 50%+`; they either damaged recent performance or pushed drawdown materially higher.
- **Least-bad wide examples**: `ATR 12% / rr 6.0 / TP1_R 1.5` widened to `21.3` median ticks and nearly retained full R (`+124.5R`), but last-1y collapsed to `+5.3R`, last-1y PF fell to `1.08`, and DD worsened to roughly `-20.4R` full / `-17.1R` last-1y. `ORB 50% / rr 5.0 / TP1_R 2.5` widened to `18.5` ticks with `+114.9R` full and `+14.6R` last-1y, but still worsened full DD to `-17.2R`.
- **Operating read**: The narrow ES_NY stop is uncomfortable but not an obvious optimization error. If live stopouts are the concern, risk down or pause ES_NY rather than widening its stop. `deployability=live_native`, `exact_replay_required=yes_before_live_promotion`.

### NQ/ES NY ORB Pair Phase-One Risk Sizing (2026-05-05)

- **Report**: `backtesting/learnings/reports/NQ_ES_NY_ORB_PAIR_PHASE_ONE_RISK_SWEEP_20260505.md`
- **Scope**: Paired current ES_NY ORB with frozen NQ NY ORB R11 and swept only per-leg dollar risk (`$100-$650` by `$50`) under the `$50k` funded-account first-payout model. No ES_NY parameters were optimized.
- **ES_NY standalone in the common ALPHA window (`2016-04-17` to `2026-03-24`)**: `846` fills, `+126.6R`, `PF 1.39`, `-10.9R` DD, `61.0%` WR, median stop `12.0` ticks, `6.4%` full TP, `46.9%` TP1-BE, `38.2%` SL.
- **Conservative pair sizing**: `NQ $150 / ES $150` had pre-holdout payout `83.3%`, breach `0.0%`, EV `$316.67`, avg payout `198d`; holdout payout `75.0%`, breach `0.0%`, EV `$275.00`, avg payout `186d`.
- **Sprint pair sizing**: `NQ $250 / ES $350` had pre-holdout payout `74.1%`, breach `23.7%`, EV `$270.61`, avg payout `79d`; holdout payout `59.4%`, breach `21.9%`, EV `$196.88`, avg payout `70d`.
- **Operating read**: The historical risk sweep likes ES risk in the sprint sleeve because ES_NY contributes more frequent partial wins and stronger recent-window stats, but this conflicts with the weak post-cutoff live sample at `$400`. Treat `ES $150` as conservative probation sizing and `ES $350` as research/sprint sizing only after fresh exact replay includes post-`2026-03-24` live-like data. Avoid defaulting to `ES $400+` while current live behavior remains poor. `deployability=live_native`; `exact_replay_required=yes_before_live_promotion`.

### ES_NY ORB Exit Deep-Dive (2026-05-05)

- **Report**: `backtesting/learnings/reports/ES_NQ_NY_ORB_EXIT_DEEPDIVE_20260505.md`
- **Scope**: Replayed ES_NY under true single-target/full-position TP1, no-BE, delayed-BE, and pre-trade bucket diagnostics before moving on to NQ Asia or NQ HTF-LSI exit optimization.
- **Baseline in common ALPHA window (`2016-04-17` to `2026-03-24`)**: `846` fills, `+126.6R`, `PF 1.39`, `-10.9R` DD, `61.0%` WR, `6.4%` full TP, `46.9%` TP1-BE.
- **Best research policies**: true full-position TP1 at `1R` improved to `+222.5R`, `PF 1.72`, `-8.0R` DD; delayed BE after `1.5R` improved to `+213.5R`, `PF 1.68`, `-9.3R` DD.
- **Operating read**: ES_NY's problem is not simply that TP2 is too far; the current partial-and-immediate-BE runner management is the uncomfortable part. `exit_mode=single_target` now makes the true full-position TP1 branch `deployability=live_native`, pending exact replay before deployment. Delayed-BE remains `research_only`. Pre-trade bucket gating is secondary because the weak buckets were positive, not toxic.

---

### NY LSI (Liquidity Sweep Inversion) — Long Only
- **Status**: **NO-GO** (thin edge, parameter instability, structural negative year)
- **Entry mode**: fvg_limit (limit at inverted FVG level)
- **Direction**: Long only (shorts dead — negative Calmar across all configs)

#### Optimization History

**Baseline** (NQ v2 anchor params transplanted to ES):
- fvg_limit/long: Calmar 2.77, 3 neg years (2018, 2021, 2025)
- close/long: Calmar 1.25 | both directions: Calmar 0.67–1.63
- Script: `run_es_ny_lsi_baseline.py`

**R1 Variable Sweeps** — 3 adoptions:
- rr: 3.0 → 4.5 (Δ+0.90) | tp1_ratio: 0.3 → 0.4 (Δ+1.22) | flat_start: 15:50 → 15:30 (Δ+0.53)
- New anchor Calmar: ~4.31
- Script: `run_es_ny_lsi_variable_sweeps_1.py`

**R2 Variable Sweeps** — 7 adoptions (WARNING: too many):
- rr=5.5, atr=7, gap=8.0%, n_left=20, flat=14:30, entry_end=13:00, DOW=excl Fri
- Script: `run_es_ny_lsi_variable_sweeps_2.py`

**R3 Variable Sweeps** — **DESTRUCTIVE INTERACTION**:
- Combined R2 anchor crashed Calmar from 4.31 → 2.64
- gap=8.0% was the main culprit (cut trades from 882 → 232)
- Most R2 adoptions reversed when combined — parameter instability confirmed
- Script: `run_es_ny_lsi_variable_sweeps_3.py`

#### Best Config Found

| Param | Value |
|-------|-------|
| entry_mode | fvg_limit |
| direction | long |
| n_left | 12 |
| n_right | 60 |
| fvg_window_left | 20 |
| fvg_window_right | 5 |
| rr | 5.5 |
| tp1_ratio | 0.4 |
| atr_length | 10 |
| min_gap_atr_pct | 5.0% |
| entry_end | 13:00 |
| flat_start | 14:30 |
| DOW | All days |

| Metric | Value |
|--------|-------|
| Trades | 544 |
| Win Rate | 47.4% |
| Profit Factor | 1.20 |
| Sharpe | 1.33 |
| Net R | 53.5 |
| R/yr | 5.4 |
| Max DD | -9.1R |
| Calmar | 5.87 |
| Neg Years | 2 (2018: -5.9R, 2025: -0.1R) |

#### R by Year
2016: +1.8 | 2017: +10.0 | **2018: -5.9** | 2019: +1.2 | 2020: +6.7 | 2021: +11.0 | 2022: +4.2 | 2023: +18.2 | 2024: +6.0 | **2025: -0.1** | 2026: +0.5

#### Reasons for NO-GO
1. **PF 1.20** — barely above breakeven; slippage/commissions erode edge in live trading
2. **Parameter instability** — 7 R2 adoptions caused destructive interaction, crashing Calmar by 40%. No stable parameter plateau found.
3. **Structural 2018 negative year** (-5.9R) — persists across all configs, cannot be optimized away
4. **R/yr = 5.4** — insufficient for prop firm viability (need ~12+ R/yr)
5. **Comparison**: NQ NY LSI achieves Calmar 20.37, PF 1.61, 0 neg years on similar params. ES simply lacks the LSI edge that NQ exhibits.

### London LSI (Liquidity Sweep Inversion) — Both Directions

- **Status**: **NO-GO** (2/5 pipeline phases — PF ceiling, no WF transferability)
- **Tested**: 2026-03-01, full lsi-optimization workflow (baseline → R1-R3 sweeps → grid R1 → robust pipeline)
- **Converged anchor** (after 3 variable sweep rounds + grid R1):
  - n_left=3, n_right=20, fvg_window=10/10, gap=4.5%, rr=2.625, tp1=0.5, atr=14, both directions
  - In-sample: 850 trades, 50.1% WR, PF 1.16, Calmar 2.40, R/yr 3.8R, DD -18.5R, **4 neg years**

#### Optimization History
- **Baseline**: rr=2.625, tp1=0.3, gap=2.25%, n_right=3 → PF 0.94, -45R net, 6 neg years (FAIL)
- **R1 stand-alone adoptions**: n_right=20 (+0.90 Calmar, 0.30 total), gap=5.0% (+0.54 Calmar)
- **R2 core convergence**: tp1=0.4 adopted (+0.48 Calmar → 1.41 total), 4 neg years
- **R3 core convergence**: CONVERGED (0 adoptions)
- **Grid R1** (270 combos, RR×TP1×GAP): winner rr=2.625, tp1=0.5, gap=4.5% (Calmar 2.40, Δ+0.99)
- **Key grid finding**: 0/270 combos with 0 negative years — negative years are structural

#### Pipeline Result (anchor: rr=2.625, tp1=0.5, gap=4.5%)

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | **FAIL** | PF 1.16 (need >1.2) — ceiling across ALL 270 grid combos |
| 2 — Walk-Forward | **FAIL** | WFE -0.151. OOS Sharpe: 2020:-2.71, 2022:-3.49 (catastrophic) |
| 3 — Prop Filter | **FAIL** | OOS expectancy -0.028R, avg annual -2.3R, OOS 2022:-21.8R |
| 4 — Hold-Out OOS | **PASS** | 50 trades, PF 1.16, +2.3R, Sharpe 0.995 |
| 5 — Monte Carlo | **PASS** | 100% survival (but OOS equity is -11.6R; MC p50 DD -24.3R) |
| **Verdict** | **NO-GO** | 2/5 passed |

#### Reasons for NO-GO
1. **PF ceiling at 1.16** — max PF across all 270 grid combinations is 1.16; Phase 1 requires >1.2. Structural limitation.
2. **WF edge does not transfer** — WFE -0.151, meaning in-sample optimization produces params that UNDERPERFORM OOS. 2020 and 2022 are catastrophic OOS years.
3. **0 negative-year-free combos** — 0/270 grid combos achieve 0 negative years. Negative years (2016, 2017, 2022, 2024) are structural.
4. **R/yr only 3.8R** in-sample (need 12R for prop firm), -2.3R OOS.
5. **Comparison to ES NY LSI**: Also NO-GO with best Calmar 5.87. ES lacks the LSI edge across ALL sessions.

#### Scripts Generated
- `run_es_ldn_lsi_baseline.py`, `run_es_ldn_lsi_variable_sweeps_{1-3}.py`
- `run_es_ldn_lsi_grid_sweep_r1.py`, `run_es_ldn_lsi_robust_pipeline.py`

---

### Asia LSI (Liquidity Sweep Inversion) — Both Directions
- **Status**: **NO-GO** (definitive — losing strategy, no edge)
- **Baseline** (2026-03-01): ORB 20:00-20:05, entry 20:05-23:30, flat 00:00, rr=2.625, tp1=0.3, gap=2.25%, n_left=3, n_right=3, fvg_window=10, absolute stop, min_stop/tp1=3.0pts
- **Both**: 1035 trades, 47.1% WR, **PF 0.80**, -71.1R net, Sharpe -1.49, DD -73.9R, **8/10 neg years**
- **Longs**: 542 trades, 49.1% WR, PF 0.86, -23.6R net, 6 neg years
- **Shorts**: 493 trades, 44.8% WR, PF 0.74, -47.5R net, 8 neg years
- **R by year (both)**: 2016:-6 2017:-6 2018:-18 2019:-5 2020:+6 2021:+1 2022:-1 2023:-7 2024:-20 2025:-11
- **Conclusion**: PF < 1.0 in all directions — strategy actively loses money. Only 2020 is positive across both directions. No optimization can rescue a losing baseline. Confirms ES lacks LSI edge across both NY and Asia sessions.
- **Script**: `run_es_asia_lsi_baseline.py`

### NY LSI v2 (NQ RR2/TP0.5 Anchor) — Both Directions — NO-GO

- **Status**: **NO-GO** (REJECT 2/5 pipeline phases — deep DD, MC ruin, gap fragility)
- **Tested**: 2026-04-02, full strategy workflow (baseline → 7-phase sweeps → discovery pipeline)
- **Approach**: Transplanted the proven NQ NY LSI RR2/TP0.5 anchor to ES and re-optimized.
- **Entry mode**: fvg_limit | **Direction**: both (longs + shorts combined)

#### Optimized Config (from sweeps)

| Param | Value |
|-------|-------|
| entry_mode | fvg_limit |
| direction | both |
| n_left | 12 |
| n_right | 78 |
| fvg_window_left | 20 |
| fvg_window_right | 5 |
| rr | 3.0 |
| tp1_ratio | 0.6 |
| atr_length | 12 |
| min_gap_atr_pct | 4.0% |
| entry_end | 15:30 |
| flat_start | 15:50 |
| DOW | All days |

#### Pre-holdout (2016-2025, pre-holdout)
- 1356 trades, 45.7% WR, PF 1.25, Sharpe 1.54, +158.8R, DD -16.7R, **Calmar 9.52**, 2 neg years (2023: -8.8R, 2025: -10.8R)

#### Walk-Forward OOS (36m IS / 12m OOS / 12m step, 6 folds)
- 845 trades, 45.7% WR, PF 1.27, Sharpe 1.61, +103.2R, DD -14.9R, **Calmar 6.94**, 1 neg year (2023: -3.4R)
- WF efficiency: **0.702** | Stability: **0.917 (high)**
- Parameter modes: rr=3.5, tp1=0.6, gap=5.0, ATR=12

#### Pipeline Results

| Phase | Result | Key Metric |
|-------|--------|-----------|
| Phase 1: Structural | PASS | 1356 tr, PF 1.25, Calmar 9.52 |
| Phase 2: WF + Stability | PASS | WFE 0.702, stability 0.917 |
| Phase 3: Prop Constraints | **FAIL** | Worst month -7.3R (threshold -5.0R) |
| Phase 4: Local Stability | **FAIL** | gap=3.0% collapses Calmar by -5.68 (SPIKE) |
| Phase 5: Monte Carlo | **FAIL** | 39% survival at 15R (need 70%), 61% ruin |

#### Reasons for NO-GO
1. **MC ruin 61%** — DD p50=-16.2R, p95=-26.7R. Does not survive stress testing.
2. **Gap parameter fragility** — gap 4.0% → 3.0% drops Calmar from 9.52 to 3.83 (cliff).
3. **Worst month -7.3R** — too deep for prop firm constraints.
4. **2023 structural weakness** — negative OOS year across multiple folds (Fold 5 Sharpe -0.37).
5. **Improved but still insufficient** — Calmar 9.52 is 63% better than prior ES LSI best (5.87), but still far below NQ (16.72) and fails Monte Carlo.

- **Scripts**: `run_es_ny_lsi_discovery_nq_anchor.py`, `run_es_ny_lsi_discovery_pipeline.py`
- **Results**: `data/results/es_ny_lsi_discovery_nq_anchor.json`

---

### NY HTF-LSI (NQ Anchor Transfer Packet) — EXPLORATORY / NOT ALIVE YET

- **Status**: EXPLORATORY — all anchors were diagnostic-only; none cleared the discovery gate
- **Tested**: 2026-04-11 with `run_cross_asset_htf_lsi_anchor_explore.py`
- **Policy**: Kept the `2025-04-01+` holdout closed; this was a pre-holdout transfer packet only
- **Session floors**: `min_stop_points=3.0`, `min_tp1_points=3.0` (same ES LSI safety rule as the earlier NY/LDN work)
- **Objective**: Test whether the NQ NY HTF-LSI anchor family transfers to ES before opening any ES-specific discovery sweep

#### Packet Results

| Anchor | Timeframe | Verdict | Pre-holdout | Discovery | Validation |
|--------|-----------|---------|-------------|-----------|------------|
| `3m lag0 diagnostic` | 3m | **diagnostic_only** | 669 trades, PF 1.04, Calmar 0.32 | PF 0.95, avg R -0.025 | **170 trades, PF 1.32, avg R 0.141, Calmar 2.53** |
| `5m lag0 control` | 5m | diagnostic_only | 608 trades, PF 1.03, Calmar 0.30 | PF 0.96, avg R -0.019 | 163 trades, PF 1.24, avg R 0.102, Calmar 1.81 |
| `5m lag24 promoted` | 5m | diagnostic_only | 507 trades, PF 1.03, Calmar 0.29 | PF 0.98, avg R -0.014 | 133 trades, PF 1.20, avg R 0.094, Calmar 1.36 |
| `1m lag0 honest` | 1m | diagnostic_only | 846 trades, PF 0.98, Calmar -0.16 | PF 0.97, avg R -0.014 | 210 trades, PF 1.03, avg R 0.017, Calmar 0.26 |

#### Read

1. **No anchor cleared discovery** — all four rows stayed below the repo’s alive bar because discovery PF / avg R were negative or near-flat. This is the important headline.
2. **`3m lag0` is the only shape worth remembering** — it had the cleanest validation (`PF 1.32`, `Calmar 2.53`, 0 negative validation years), but it still carried 5 negative pre-holdout years and discovery PF only `0.95`. Treat it as a diagnostic branch, not a promoted candidate.
3. **`5m lag24` did not port** — the promoted NQ lead was not better than the ES `5m lag0` control on this first transfer packet. ES did not reward the late-lag cap the way NQ did.
4. **HTF structure did not rescue ES on first contact** — these rows are materially weaker than the earlier ES NY LSI v2 branch (`Calmar 9.52`, PF 1.25, both directions). So HTF-LSI should not automatically replace prior ES LSI work.

#### Conclusion

The trusted NQ HTF-LSI anchors do **not** transfer cleanly to ES NY out of the box. That transfer conclusion was later **superseded** by a separate ES-specific broad discovery pass, which did uncover a viable `3m` family. The important lesson from this packet is narrower: **do not assume the NQ `5m lag24` lead is portable to ES without reopening ES discovery.**

- **Script**: `backtesting/scripts/run_cross_asset_htf_lsi_anchor_explore.py`
- **Report**: `backtesting/learnings/reports/ES_NY_HTF_LSI_ANCHOR_EXPLORE.md`
- **Results**: `backtesting/data/results/es_ny_htf_lsi_anchor_explore/summary.json`

---

### NY HTF-LSI (ES Broad Discovery + Stitched Follow-Up) — ALIVE / PRE-HOLDOUT LEAD

- **Status**: ALIVE pre-holdout; promoted to downstream phase-one evaluation
- **Tested**: 2026-04-11 with `run_cross_asset_htf_lsi_broad_discovery.py` followed by `run_cross_asset_htf_lsi_stitched_followup.py`
- **Policy**: Holdout remained closed from `2025-04-01` onward during both steps
- **Session floors**: `min_stop_points=3.0`, `min_tp1_points=3.0`
- **Objective**: Reopen ES discovery honestly after the failed NQ transfer packet and determine whether ES has its own viable HTF-LSI family

#### Broad Discovery Family Read

Broad discovery changed the ES read materially. The live family is not the transplanted NQ `5m lag24` branch. It clusters around:

- `3m`
- `long`
- `fvg_limit`
- `htf_level_tf_minutes=90`
- `htf_n_left=3`
- `entry_end=14:00`
- `htf_trade_max_per_session=2`

The strongest challengers all stayed inside that same family, with variation mainly in:

- `rr=2.5-3.0`
- `tp1_ratio=0.5-0.6`
- `min_gap_atr_pct=2.0-3.0`
- `lsi_fvg_window_left=20 or 33`
- `lsi_fvg_window_right=3 or 5`
- `max_fvg_to_inversion_bars=0, 16, or 24`

#### Fixed Stitched Follow-Up

The stitched tie-break used `36m IS / 12m OOS / 12m step` over `2016-01-01` to `2025-04-01` and ranked six curated `3m` candidates on combined OOS behavior.

| Candidate | Shape | Discovery | Validation | Stitched OOS |
|-----------|-------|-----------|------------|--------------|
| **Lead: `control_stage_b`** | `rr=3.0`, `tp1=0.6`, `gap=3.0`, `left/right=99/9`, `lag=0` | 380 trades, PF 1.055, avg R 0.025 | 129 trades, PF 1.434, avg R 0.191, Calmar 2.45 | **350 trades, PF 1.253, avg R 0.115, Calmar 3.66, DD -11.0R** |
| `balanced_lag0_gap3` | `rr=2.5`, `tp1=0.5`, `gap=3.0`, `left/right=60/9`, `lag=0` | 379 trades, PF 1.074, avg R 0.030 | 128 trades, PF 1.449, avg R 0.175, Calmar 2.36 | 348 trades, PF 1.243, avg R 0.097, Calmar 3.56, DD -9.5R |
| `count_lag0_gap2_r15` | `rr=2.5`, `tp1=0.5`, `gap=2.0`, `left/right=60/15`, `lag=0` | 535 trades, PF 1.056, avg R 0.024 | 165 trades, PF 1.396, avg R 0.168, Calmar 2.51 | 478 trades, PF 1.220, avg R 0.095, Calmar 3.00, DD -15.1R |
| `discovery_lag0_gap2_r9` | `rr=2.5`, `tp1=0.5`, `gap=2.0`, `left/right=60/9`, `lag=0` | **490 trades, PF 1.085, avg R 0.036** | 154 trades, PF 1.339, avg R 0.138, Calmar 2.21 | 440 trades, PF 1.214, avg R 0.088, Calmar 2.93, DD -13.3R |
| `late_lag24_gap3` | `rr=2.5`, `tp1=0.5`, `gap=3.0`, `left/right=60/9`, `lag=24` | 284 trades, PF 1.057, avg R 0.027 | 90 trades, PF 1.407, avg R 0.179, Calmar 2.17 | 257 trades, PF 1.220, avg R 0.102, Calmar 2.88, DD -9.1R |
| `quality_lag16_gap2` | `rr=2.5`, `tp1=0.5`, `gap=2.0`, `left/right=60/9`, `lag=16` | 320 trades, PF 1.055, avg R 0.028 | 86 trades, PF 1.421, avg R 0.188, Calmar 2.52 | 271 trades, PF 1.191, avg R 0.093, Calmar 2.47, DD -10.2R |

#### Read

1. **ES HTF-LSI is real, but it is an ES-shaped `3m` family** — reopening discovery was worth it. The alive cluster is `3m / long / fvg_limit / htf90 / n_left3 / cap2`, not the NQ `5m` lead.
2. **The original Stage B control won the stitched tie-break** — even though several lower-`RR` challengers looked slightly better on fixed validation, the `rr=3.0 / tp1=0.6 / gap=3.0 / lag=0` control held up best on combined rolling OOS (`PF 1.253`, `avg R 0.115`, `Calmar 3.66`).
3. **Lower-`RR` challengers are valid, but secondary** — `balanced_lag0_gap3` is the cleanest challenger and traded nearly the same stitched sample with slightly lower return quality but better OOS drawdown (`-9.5R` vs `-11.0R`).
4. **Late-lag variants did not beat lag0 once sample honesty mattered** — `lag=16` and `lag=24` produced attractive validation rows, but both lost the stitched comparison to the uncapped/lag0 control.
5. **`2022` is the persistent weak fold** — every candidate had a negative stitched OOS slice in `2022-01-01` to `2023-01-01`, so this family is alive but not regime-proof.
6. **Bailey-style deflation was not rerun on this ES packet yet** — this is a heuristic pre-holdout promotion result, not a final statistically-deflated approval.

#### Conclusion

ES NY HTF-LSI deserves to continue. Freeze the current lead as:

- `3m`
- `long`
- `fvg_limit`
- `08:30-14:00`
- `rr=3.0`
- `tp1_ratio=0.6`
- `min_gap_atr_pct=3.0`
- `atr_length=14`
- `htf_level_tf_minutes=90`
- `htf_n_left=3`
- `htf_trade_max_per_session=2`
- `lsi_fvg_window_left/right=33/3`
- `max_fvg_to_inversion_bars=0`

Carry `balanced_lag0_gap3` as the main challenger and optionally `late_lag24_gap3` as a thinner secondary challenger. The next clean step is downstream phase-one style evaluation on this frozen shortlist, with the `2025-04-01+` holdout still unopened until that workflow actually needs it.

- **Scripts**: `backtesting/scripts/run_cross_asset_htf_lsi_broad_discovery.py`, `backtesting/scripts/run_cross_asset_htf_lsi_stitched_followup.py`
- **Reports**: `backtesting/learnings/reports/ES_NY_HTF_LSI_BROAD_DISCOVERY.md`, `backtesting/learnings/reports/ES_NY_HTF_LSI_STITCHED_FOLLOWUP.md`
- **Results**: `backtesting/data/results/es_ny_htf_lsi_broad_discovery/summary.json`, `backtesting/data/results/es_ny_htf_lsi_stitched_followup/summary.json`

---

### NY HTF-LSI Phase One — CONDITIONAL / HOLDOUT WEAK

- **Status**: CONDITIONAL at best; not promoted to phase two
- **Tested**: 2026-04-11 with `run_es_ny_htf_lsi_phase_one.py`
- **Holdout**: Opened once on `2025-04-01` to `2026-03-24`
- **Packet**: `control_stage_b`, `balanced_lag0_gap3`, `late_lag24_gap3`
- **Note**: Bailey-style PSR / DSR was not rerun on this ES packet, so this is a downstream scorecard read on the frozen shortlist, not a deflated-statistics approval

#### Phase-One Summary

| Candidate | Verdict | OOS prop payout | OOS funded payout | OOS funded EV/start | Holdout PF | Holdout avg R | Holdout prop payout | Holdout funded payout | Holdout funded EV/start |
|-----------|---------|----------------:|------------------:|--------------------:|-----------:|--------------:|--------------------:|----------------------:|------------------------:|
| `balanced_lag0_gap3` | CONDITIONAL | 63.7% | 42.8% | $62.67 | 0.918 | -0.046 | 21.9% | 21.9% | -$38.76 |
| `late_lag24_gap3` | CONDITIONAL | 60.0% | 47.9% | $46.48 | 0.831 | -0.098 | 5.2% | 5.2% | -$96.00 |
| `control_stage_b` | CONDITIONAL | 48.2% | 39.0% | $72.96 | 0.827 | -0.097 | 12.4% | 12.4% | -$58.29 |

#### Read

1. **All three frozen candidates failed the raw holdout test** — every row was negative on `2025-04-01` to `2026-03-24`, with holdout PF only `0.83-0.92` and total R below zero on `42-47` trades. This is the key reason the branch stopped at conditional.
2. **The payout-sprint winner was not the stitched raw-quality winner** — the stitched-OOS control (`rr=3.0 / tp1=0.6`) kept the best raw OOS avg R / total R, but `balanced_lag0_gap3` converted better on phase-one payout scorecards because the lower-`RR` shape reached payout more often.
3. **`balanced_lag0_gap3` is the best conditional branch if ES HTF-LSI is kept open** — it led the packet on OOS prop payout (`63.7%`) and also had the least-damaging holdout (`PF 0.918`, avg R `-0.046`, funded payout `21.9%`).
4. **`lag24` did not survive downstream promotion on ES** — unlike NQ, the late-lag ES challenger was not the right branch once payout conversion and opened holdout mattered. It kept decent OOS payout rates, but holdout funded payout fell to only `5.2%`.
5. **None of these rows deserves phase-two work yet** — under the default funded-account model, all holdout funded EV/start values were negative. That is too weak for a confident first-payout business.

#### Conclusion

ES NY HTF-LSI stays alive only as a **conditional research branch**, not a promoted funded-account candidate. If it is revisited, the best restart point is now the **`balanced_lag0_gap3` phase-one branch**:

- `3m`
- `long`
- `fvg_limit`
- `08:30-14:00`
- `rr=2.5`
- `tp1_ratio=0.5`
- `min_gap_atr_pct=3.0`
- `atr_length=14`
- `htf_level_tf_minutes=90`
- `htf_n_left=3`
- `htf_trade_max_per_session=2`
- `lsi_fvg_window_left/right=20/3`
- `max_fvg_to_inversion_bars=0`

But the honest posture is cautious: the opened holdout was weak across the full shortlist, so ES HTF-LSI should **not** advance to phase two or live funding priority right now.

- **Script**: `backtesting/scripts/run_es_ny_htf_lsi_phase_one.py`
- **Report**: `backtesting/learnings/reports/ES_NY_HTF_LSI_PHASE_ONE.md`
- **Results**: `backtesting/data/results/es_ny_htf_lsi_phase_one/phase_one_results.json`

---

### ES ORB 3-Session Discovery (Regime-Gated) — Phase-One Complete (2026-04-01)

New discovery sweep with regime research framework (medium-vol avoidance gate). 3,888 configs swept across NY, Asia, LDN. 8 candidates through walk-forward. PSR/DSR validation. Phase-one prop simulation.

#### Sweep Results — Best Per Session

| Session | Top Config | Pre-holdout | Calmar | Direction |
|---------|-----------|-------------|--------|-----------|
| NY | 45m ORB, ATR 8%, RR=3.5, TP1=0.3 | +99.2R | 11.08 | **Both** |
| Asia | 60m ORB, ORB 100%, RR=2.5, TP1=0.4 | +65.6R | 9.04 | Long |
| LDN | 45m ORB, ATR 15%, RR=3.5, TP1=0.3 | +37.6R | 3.67 | **Short** |

Key ES vs NQ differences: ES NY works with both directions (short component strong). ES Asia needs 60m ORB (not 15m). ES LDN is short-only (NQ was long-only).

#### Phase-One Results

| Candidate | Pre R | HO R | Pre PR | HO PR | HO EV | PSR | Verdict |
|-----------|-------|------|--------|-------|-------|-----|---------|
| **ES NY-A** | +71.3 | **+2.7** | 78.1% | **43.3%** | $8,596 | 0.999 | **STRONG** |
| ES Asia-A | +65.6 | -0.4 | 87.3% | 0.0% | -$66 | 1.000 | CONDITIONAL |
| ES LDN-B | +40.0 | -16.2 | 60.4% | 0.8% | $67 | 0.966 | CONDITIONAL |

#### ES NY-A Config (WINNER — promoted with caution)

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| ORB window | 09:30-10:15 (45m) |
| entry window | 10:15-12:00 |
| flat | 15:50-16:00 |
| stop | ATR 8% |
| rr | 3.5 |
| tp1_ratio | 0.3 (TP1 at 1.05R, TP2 at 3.5R) |
| direction | **both** |
| atr_length | 14 |
| min_gap_atr_pct | 1.0% |
| regime gate | medium-vol avoidance |
| bar magnifier | OFF during discovery |

- **Pre-holdout**: 641 trades, WR 68%, PF 1.93, +71.3R, Cal 7.22, DD -9.9R
- **Holdout**: 121 trades, +2.7R, Cal 0.20, Shp 0.38, DD -13.8R
- **Holdout payout rate**: 43.3% (barely viable)

#### Post-Hoc Regime Gate Comparison (all 8 candidates, holdout)

All candidates re-run ungated vs gated (medium-vol avoidance: skip `bull_medium_vol` + `sideways_medium_vol`) on holdout (2024-03 → 2026-02). Script: `run_es_orb_regime_gate_comparison.py`.

| # | Name | Ungated R | Ungated Cal | Ungated DD | Gated R | Gated Cal | Gated DD | ΔCal | Gate helps? |
|---|------|-----------|-------------|------------|---------|-----------|----------|------|-------------|
| 1 | **Asia-B** | **+49.4** | **8.09** | -6.1 | +36.1 | 6.97 | -5.2 | -1.13 | **No — ungated is better** |
| 2 | Asia-C | +22.2 | 3.20 | -6.9 | +13.7 | **4.56** | **-3.0** | **+1.35** | **YES — Calmar ↑, DD halved** |
| 3 | Asia-A | +7.4 | 0.59 | -12.7 | -0.4 | -0.04 | -8.4 | -0.63 | No (went negative) |
| 4 | NY-A | +6.5 | 0.34 | -19.3 | +2.7 | 0.20 | -13.8 | -0.14 | No (both weak) |
| 5 | NY-B | +1.4 | 0.26 | -5.5 | -2.6 | -0.58 | -4.5 | -0.84 | No (went negative) |
| 6 | NY-C | -5.9 | -0.61 | -9.7 | -5.8 | -0.54 | -10.7 | +0.07 | Marginal (both negative) |
| 7 | LDN-A | -14.9 | -0.83 | -18.0 | -13.4 | -0.79 | -17.0 | +0.04 | No (still deeply negative) |
| 8 | LDN-B | -22.0 | -0.80 | -27.3 | -16.2 | -0.78 | -20.6 | +0.02 | No (still deeply negative) |

**Surprise finding — Asia-B was missed**: ES Asia-B (15m ORB, ATR 12%, RR=3.0, TP1=0.6, long) was **not promoted to phase-one** despite being the strongest holdout performer by far: +49.4R ungated (Cal 8.09) or +36.1R gated (Cal 6.97). This crushes the phase-one winner NY-A (+2.7R gated). Asia-A was promoted instead because it ranked higher on pre-holdout metrics, but Asia-B's holdout performance is dramatically better.

**Gate impact on ES is mixed**: unlike NQ where the gate universally compressed DD, on ES the gate hurt Asia-B (the best performer) by trimming profitable trades. The gate helped Asia-C and marginally helped LDN, but couldn't rescue the fundamentally weak candidates (NY, LDN).

#### Key Findings

1. **ES is structurally harder than NQ for ORB continuation** — all 3 sessions degraded on holdout
2. **ES NY-A is the only viable candidate** — both-directions approach gives resilience that pure long lacks
3. **ES Asia collapsed on holdout** (87% pre → 0% holdout) — same failure pattern as NQ NY-B
4. **ES LDN short collapsed** — the 2024-2025 bull market killed short-only LDN
5. **ES needs a 45-60m ORB window** (not 15m like NQ) — wider window needed to capture ES's slower breakout dynamics
6. **Regime gate helps but can't save weak holdout** — gate was essential for pre-holdout but didn't prevent holdout degradation
7. **ES NY holdout is marginal** — +2.7R over 24 months is barely positive. Promote with caution, consider ES as a portfolio diversifier rather than a standalone strategy
8. **Asia-B is the real ES winner** — +49.4R ungated on holdout (Cal 8.09, Shp 3.74, DD -6.1R). Phase-one promoted Asia-A instead based on pre-holdout ranking, missing the best candidate. Asia-B uses a 15m ORB (not 60m) with ATR 12% stop — structurally different from Asia-A
9. **ES regime gate is candidate-dependent** — helped Asia-C (+1.35 Calmar) but hurt Asia-B (-1.13 Calmar). No universal benefit like NQ. Best ES candidates should be tested both gated and ungated
10. **ES LDN is dead regardless of gating** — both short-only candidates deeply negative on holdout (-13R to -22R). Gate trimmed ~6R of losses but fundamentally no edge

---

### ES Asia-B Phase-One Pipeline — STRONG (2026-04-01)

**Status**: **STRONG** — both ungated and gated variants pass phase-one. Promoted to paper trading consideration.

#### ES Asia-B Config

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 20:00-20:15 (15m) |
| entry window | 20:15-23:15 |
| flat | 04:00-07:00 |
| stop | ATR 12% |
| rr | 3.0 |
| tp1_ratio | 0.6 (TP1 at 1.8R, TP2 at 3.0R) |
| direction | long only |
| atr_length | 14 |
| min_gap_atr_pct | 1.0% |

#### Phase-One Results (ungated vs gated)

| Metric | Ungated | Gated |
|--------|---------|-------|
| **Pre-holdout** | 766 trades, +82.2R, Cal 7.87, Shp 1.36, DD -10.4R, 1 neg yr (2024) | 574 trades, +82.6R, Cal 8.35, Shp 1.81, DD -9.9R, 0 neg yrs |
| **Walk-forward OOS** | +71.7R, Cal 6.04, Shp 1.37, WFE 0.563, Stab 0.750 | +57.9R, Cal 5.43, Shp 1.50, WFE 0.407, Stab 0.714 |
| **Holdout** | 171 trades, **+49.4R**, Cal 8.09, **Shp 3.74**, DD -6.1R | 97 trades, +36.1R, Cal 6.97, **Shp 4.97**, DD -5.2R |
| **Holdout yearly** | 2024:+13.7, 2025:+31.4, 2026:+4.2 | 2024:+11.9, 2025:+25.9, 2026:-1.7 |
| **Holdout payout rate** | **80.1%** | 78.8% |
| **Holdout EV** | $15,964/attempt | $15,708/attempt |
| **Pre-holdout payout rate** | 64.1% | **77.0%** |
| **Pre-holdout EV** | $12,748/attempt | **$15,339/attempt** |
| **PSR** | 0.992 (strong) | 0.998 (strong) |
| **DSR** @3888 trials | 0.098 (overfit flag) | 0.178 (overfit flag) |
| **Verdict** | **STRONG** | **STRONG** |

#### Gate Decision

Both variants are STRONG. Trade-offs:

- **Ungated** has higher holdout Net R (+49.4 vs +36.1), higher holdout payout rate (80.1% vs 78.8%), and better WFE (0.563 vs 0.407). All holdout years positive.
- **Gated** has 0 negative pre-holdout years (vs 1), higher pre-holdout payout rate (77.0% vs 64.1%), and higher pre-holdout EV ($15,339 vs $12,748). But 2026 is -1.7R on holdout.
- **Recommendation**: Run ungated in production — stronger holdout, no negative holdout years, higher WFE. Gate improves pre-holdout consistency but trims too many holdout winners.

#### Comparison to Original Phase-One Winner (NY-A)

| Metric | NY-A (original winner) | Asia-B ungated |
|--------|----------------------|----------------|
| Holdout R | +2.7 | **+49.4** |
| Holdout Cal | 0.20 | **8.09** |
| Holdout PR | 43.3% | **80.1%** |
| Holdout EV | $8,596 | **$15,964** |

Asia-B is dramatically stronger than NY-A across every metric. NY-A should be demoted; Asia-B is the clear ES leader.

#### Script
- `run_es_asia_b_phase_one.py`

---

### Regime-Gate Transfer Confirmation (2026-04-01)

Shared cross-asset transfer run reconfirmed that **ES Asia-B should stay ungated**:

| Variant | Trades | HO R | Calmar | Sharpe | DD | HO PR | HO EV |
|---------|--------|------|--------|--------|----|-------|-------|
| Ungated | 171 | +49.35 | 8.091 | 3.742 | -6.1R | 80.1% | $15,964 |
| Gated | 97 | +36.12 | 6.966 | 4.967 | -5.2R | 78.8% | $15,708 |

- **Verdict**: `rejects_gate`
- **Interpretation**: the medium-vol gate trims too many profitable Asia-B trades. It slightly improves drawdown and Sharpe, but the drop in net R and Calmar is too large.
- **Action**: keep **Asia-B ungated** as the ES production baseline and do **not** promote ES into the second-round gate shortlist.
- **ALPHA_V1 hot-regime ablation pass** (2026-05-03): `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_ABLATION_20260503.md`
  - Scope included ES Asia ORB and ES NY ORB from the active ALPHA_V1 sleeve. This is TESTING-only, overfit-aware research inspired by `H_ORB_ABLATED`, not a robust promotion packet.
  - Best ES Asia ORB hot-score branch: `combo__entry_0600__dow_baseline__rr4p0_tp0p25__stop_orb_pct_125p0__min_gap_atr_pct_0p25__cap2_any__fvg_first__wide_none` -> full `203.35R / -17.05R DD`, last 2y `44.8R`, last 1y `38.33R`; warning: warning layer acceptable for TESTING.
  - Best ES NY ORB hot-score branch: `combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p25__cap2_any__fvg_first__wide_none` -> full `157.1R / -20.62R DD`, last 2y `48.48R`, last 1y `19.75R`; warning: 1 negative year.
- **ALPHA_V1 expanded hot-regime grid** (2026-05-03): `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_EXPANDED_GRID_20260503.md`
  - Follow-up grid expanded the top OAT families into 4,378 scored variants. This is still TESTING-only and intentionally overfit-aware.
  - Best expanded ES Asia ORB hot-score branch: `combo__entry_0600__dow_baseline__rr1p5_tp0p7__stop_orb_pct_125p0__min_gap_atr_pct_0p25__uncapped_any__fvg_first__wide_none` -> full `252.59R / -21.65R DD`, last 2y `61.17R`, last 1y `38.52R`; warning: 1 negative year, lower PF, high trade count.
  - Pure last-1y ES Asia branch: `entry_0400 / exMon / rr1.5 / stop75 / gap0.5 / uncapped` reached `+56.50R` last-1y, but full history was much more fragile at `132.89R / -36.97R DD` with 2 negative years.
  - Best expanded ES NY ORB hot-score branch: `combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p5__cap2_any__fvg_first__wide_none` -> full `165.11R / -22.30R DD`, last 2y `50.06R`, last 1y `20.03R`; full and recent DD both worsen versus baseline.
- **Hot one-year strategy workflow** (2026-05-03): `backtesting/learnings/reports/HOT_ONE_YEAR_STRATEGY_WORKFLOW_20260503.md`
  - Window: `2025-03-24` to `2026-03-24`. TESTING-only, overfit-aware Calmar optimization; Bailey-style deflation intentionally skipped.
  - ES NY ORB: `combo__orb15m__entry_1300__flat_1430__rr5p0_tp0p2__stop_atr_5p0__gap_orb_10p0__atr7__dir_both__dow_baseline__icf_off__cap1__fvg_first` with `gate_none` -> 115 fills, `30.13R`, Calmar `8.499`, PF `1.799`, DD `-3.55R`, surface `curve`.
  - ES Asia ORB: `combo__orb10m__entry_0600__flat_0700__rr1p5_tp0p7__stop_orb_125p0__gap_atr_0p5__atr20__dir_long__dow_baseline__icf_off__cap2_nonpos__fvg_first` with `gate_skip_bear_high_vol` -> 173 fills, `46.88R`, Calmar `12.656`, PF `1.799`, DD `-3.7R`, surface `curve`.
  - ES NY LSI: `combo__window_0830_1500__rr4p0_tp0p3__gap3p0__atr20__fvgL20_R3__lag16__cap1__htfN2__htf90__dir_long__mode_fvg_limit__dow_exTue` with `gate_skip_high_vol` -> 22 fills, `14.6R`, Calmar `14.598`, PF `3.277`, DD `-1.0R`, surface `soft_curve`.

- **Hot one-year squeeze** (2026-05-03): `backtesting/learnings/reports/HOT_ONE_YEAR_SQUEEZE_20260503.md`
  - Window: `2025-03-24` to `2026-03-24`. TESTING-only second-stage local squeeze around prior screenshot winners.
  - ES NY ORB: `prev_curve_net__combo__rr7p0_tp0p8__dow_none__gap_atr_1p0__wide_t12p5_rr3__icf_on__pre_cancel_tp1__flat_1330` with `gate_skip_medium_vol` -> 222 fills, `111.94R`, Calmar `4.146`, PF `1.671`, DD `-27.0R`, surface `curve`.
  - ES Asia ORB: `prev_curve_net__combo__rr2p0_tp0p7__stop_orb_75p0__gap_atr_0p375__dow_exMon__flat_0600__atr10__wide_t12p5_rr1p5` with `gate_skip_sideways_high_vol` -> 216 fills, `61.61R`, Calmar `9.91`, PF `1.641`, DD `-6.22R`, surface `curve`.
  - ES NY LSI: `prev_curve_net__combo__dow_exWed__fvgL7_R3__rr5p0_tp0p25__stop_struct_75pct__atr14__lag16__entry_1400` with `gate_skip_high_vol` -> 32 fills, `28.64R`, Calmar `20.832`, PF `4.58`, DD `-1.38R`, surface `curve`.

- **Hot structural sequence** (2026-05-03): `backtesting/learnings/reports/HOT_STRUCTURAL_SEQUENCE_20260503.md`
  - Window: `2025-03-24` to `2026-03-24`. Post-trade structural gates around current hot one-year candidates.
  - ES NY ORB: best structural `exclude_fomc` (calendar_news) -> 179 fills, `120.97R`, Calmar `8.641`, PF `1.938`, DD `-14.0R`, delta `5.0R`; TESTING-only.
  - ES Asia ORB: best structural `combo__orb_not_extreme__exclude_fomc` (combo) -> 143 fills, `55.34R`, Calmar `14.636`, PF `1.947`, DD `-3.78R`, delta `-5.73R`; TESTING-only.
  - ES NY LSI: best structural `prior_not_inside_day` (prior_day) -> 27 fills, `21.76R`, Calmar `21.755`, PF `4.121`, DD `-1.0R`, delta `0.44R`; TESTING-only.

- **Hot structural follow-up** (2026-05-03): `backtesting/learnings/reports/HOT_STRUCTURAL_FOLLOWUP_20260503.md`
  - Window: `2025-03-24` to `2026-03-24`. Targeted second pass around positive structural gates from the hot structural sequence.
  - ES NY ORB: best refined structural `exclude_fomc_cpi` -> 174 fills, `125.97R`, delta `10.0R`, Calmar `10.497`, PF `2.017`, DD `-12.0R`, surface `n/a`; TESTING-only.

### ALPHA_V1 ATH Regime Findings (2026-05-05)

Reports: `backtesting/learnings/reports/ALPHA_V1_ATH_REGIME_FIRST_PASS_20260505.md` and `backtesting/learnings/reports/ALPHA_V1_ATH_REGIME_LEG_TARGETS_20260505.md`

- `ES NY ORB` has the cleanest actionable ATH dead zone: signal-time `0.5-1%` below futures ATH was negative (`95` trades, `-5.2R`, `-0.055R` avg). Skipping only that bucket improves portfolio R by `+5.2R` full history and `+5.6R` in `2025+`; ES NY standalone full-history first-payout rate improves from `64.2%` to `68.5%`, and `2025+` improves from `43.8%` payout / `37.5%` breach to `81.2%` payout / `0.0%` breach. Status: `post_filter_only`; exact replay and live ATH gate support required.
- `ES Asia ORB` near-ATH quality is real but not enough for a replacement gate. The `0-0.5%` bucket produced `325` trades, `+61.1R`, `0.188R` avg versus `0.103R` baseline, but keeping only that bucket cuts `-84.8R` from the ALPHA_V1 portfolio and stretches standalone median payout time to `655` days. Treat as attribution/risk context, not a promoted gate.

### ES NY ATH Exact Replay (2026-05-05)

Report: `backtesting/learnings/reports/ALPHA_V1_ES_NY_ATH_EXACT_REPLAY_20260505.md`

Artifacts: `backtesting/data/results/alpha_v1_es_ny_ath_exact_replay_20260505/`

The `ES NY ORB` signal-time `0.5-1.0%` below futures ATH skip was promoted from post-filter research into the live/exact `ORBEngine` as a causal pre-arm gate (`ath_block_min_pct/max_pct`) and exact-replayed on ES futures data from `2016-04-17` through `2026-03-24`.

Exact trade results confirm the dead-zone edge: baseline `849` trades / `+145.8R` / `-12.0R DD` becomes `774` trades / `+155.0R` / `-12.0R DD`. The recent improvement is stronger: `2024+` improves by `+8.5R` with DD improving from `-9.0R` to `-7.5R`; `2025+` improves by `+9.5R` with the same DD improvement.

Funded-account read is **not** clean enough for production promotion. Full-history standalone payout worsens from `65.0%` payout / `32.7%` breach to `60.4%` payout / `37.3%` breach, even though `2024+` improves to `84.7%` payout / `5.1%` breach and `2025+` improves to `75.0%` payout / `9.4%` breach. Status: `post_filter_only` until production live has a trusted ATH seed source; recent-flow watchlist only. Next research target: rolling split diagnostics plus nearby exact band sensitivity before any dry-run recommendation.

### ES NY ATH Band Sensitivity (2026-05-05)

Report: `backtesting/learnings/reports/ALPHA_V1_ES_NY_ATH_BAND_SENSITIVITY_20260505.md`

Artifacts: `backtesting/data/results/alpha_v1_es_ny_ath_band_sensitivity_20260505/`

Exact sensitivity around the ES NY ATH dead zone tested `0.25-0.75%`, `0.50-0.75%`, `0.75-1.00%`, `0.50-1.00%`, and `0.50-1.25%` as live-engine pre-arm ATH blocks. **Best candidate is `0.50-0.75%` below expanding ES futures ATH.**

`0.50-0.75%` improves full-history exact R by `+11.5R` (`+145.8R` to `+157.3R`) while improving full-history payout from `65.0%` to `67.3%`; this fixes the full-history payout damage from the wider `0.50-1.00%` gate. Recent behavior remains useful: `2024+` `+5.0R` and payout `84.7%`; `2025+` `+10.0R` and payout `75.0%`. Rolling 2-year stability: `7/10` windows improve, median rolling delta `+1.75R`, worst window `-6.92R` in `2019-2020`.

Alternatives: `0.25-0.75%` has the best payout safety (`70.0%` full payout, zero `2025+` breaches) but rolling stability is poor (`4/10` positive, `-1.86R` median). `0.75-1.00%` is steadier but too weak in `2025+` (`+1.5R`). Reject `0.50-1.25%`; it removes too much trade flow and hurts full-history account behavior.

Implementation update: production startup can now refresh the ES futures ATH seed from DataBento daily OHLCV, seed only ATH-gated engines, and preserve a higher checkpoint/live ATH if one exists. Added `ALPHA_V1-ES-NY-ATH-SHADOW` as an enabled ES_NY-only no-webhook dry-run profile with `ath_block_min_pct=0.5` and `ath_block_max_pct=0.75`. Status is now `deployability=live_native`; `live_support_notes=exact/live engine gate plus startup ATH seed source are implemented, profile is shadow-only/no-webhook pending forward observation`; `exact_replay_required=completed_through_2026-03-24_and_repeat_before_live_promotion_if_data_extends_materially`. Shadow diagnostics are available in the engine `ath` status payload: `current_gap_pct`, `check_count`, `block_count`, `pass_count`, `last_check`, and `last_block`. TESTING now includes `ES_NY_ATH_GATE`, and the execution frontend shows a dedicated ATH Gate panel so blocked and passed setup decisions can be confirmed during forward testing.
