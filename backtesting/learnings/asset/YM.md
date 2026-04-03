# YM (Dow Jones Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $5/point
- **Min tick**: 1.0
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-02 (~10 years, 5m + 1m + 1s)

## Strategies Tested

### 1. Asia Continuation Long-Only — NO-GO
- **Script**: `run_ym_robust_directional.py --session Asia --direction long`
- **Config**: Default Asia session params, 1s magnifier (structural), 1m magnifier (WF)
- **Phase 1 (Structural)**: PASS — 1032 trades, 46% WR, PF 1.06, Sharpe 0.44, +34R, DD -25.6R, Calmar 1.33
- **Phase 2 (Walk-Forward)**: FAIL — WF efficiency 0.28 (need ≥0.50), stability 0.75 (high). 3/6 OOS folds negative. Params unstable across folds (stop ranged 5-12.5%, rr 2.0-3.5).
- **Phase 3 (Prop Filter)**: FAIL — Worst month -6.0R, avg annual R ~3.7R (need ≥24R). Years: 2019 +8.9R, 2020 -2.9R, 2021 +5.7R, 2022 +12.1R, 2023 -0.6R, 2024 -0.8R.
- **Phase 4 (Hold-Out 2025)**: FAIL — 70 trades, WR 40%, Sharpe -1.20, PF 0.86, -6.1R, DD -14.8R.
- **Phase 5 (MC)**: FAIL — DD p95 32.5R (exceeds 30R limit), ruin prob 15.3%.
- **Mode params**: rr=2.0, stop=5.0%, gap=2.0%, tp1=0.6
- **Conclusion**: Marginal structural edge but insufficient for prop firm. Walk-forward inconsistent, recent years (2023-2025) trending badly. Not enough R/year to justify.

### 2. Asia Continuation Short-Only — NO-GO
- **Script**: `run_ym_robust_directional.py --session Asia --direction short`
- **Config**: Default Asia session params, 1s magnifier (structural), 1m magnifier (WF)
- **Phase 1 (Structural)**: FAIL — 909 trades, 43.2% WR, PF 0.90, Sharpe -0.74, -49.3R, DD -81R.
- **Phase 2 (Walk-Forward)**: FAIL — WF efficiency -3.83, combined OOS -40.1R. IS Sharpe often near zero or negative.
- **Phase 3 (Prop Filter)**: FAIL — Negative expectancy (-0.089R). Massive losing years: 2019 -12.5R, 2022 -17.5R, 2024 -21.2R.
- **Phase 4 (Hold-Out 2025)**: FAIL — Sharpe 0.46 (barely missed 0.5), PF 1.06, +2.5R. Surprising recent improvement but insufficient.
- **Phase 5 (MC)**: FAIL — 94.2% ruin probability, DD p95 85.4R.
- **Mode params**: rr=2.0, stop=5.0%, gap=1.5%, tp1=0.5
- **Conclusion**: Structurally unprofitable. Do not revisit without a fundamentally different approach.

### 3. NY Continuation Long-Only — NO-GO
- **Script**: `run_ym_robust_directional.py --session NY --direction long`
- **Config**: Default NY session params, 1s magnifier (structural), 1m magnifier (WF)
- **Phase 1 (Structural)**: FAIL — 895 trades, 45.5% WR, PF 1.02, Sharpe 0.17, +11.1R, DD -45.6R, Calmar 0.24. **Failed on max consec losses = 17 (>15)**.
- **Phase 2 (Walk-Forward)**: PASS — WFE 0.56, stability 0.83 (high). 5/6 OOS folds positive. Stable mode params: rr=3.0, stop=7.5%, gap=1.0%, tp1=0.4.
- **Phase 3 (Prop Filter)**: FAIL — Worst month -6.0R, avg annual R ~5R.
- **Phase 4 (Hold-Out 2025)**: PASS — 110 trades, WR 50.9%, Sharpe 2.40, PF 1.40, +21.7R, DD -6.2R, Calmar 3.49.
- **Phase 5 (MC)**: FAIL — DD p95 46.9R, ruin prob 45.5%.
- **Mode params**: rr=3.0, stop=7.5%, gap=1.0%, tp1=0.4
- **Optimization attempted** (variable sweeps R1-R2 + grid sweep):
  - R1 sweep from WF mode anchor: adopted excl Tuesday (Calmar 0.35→0.65, neg years 2→0)
  - R2 sweep with Tue exclusion: converged, no further adoptions
  - Grid sweep (stop × rr × gap × tp1, 840 combos): best 0-neg-year config = stop=8.0%, rr=2.0, gap=0.75%, tp1=0.5 → Calmar 0.74, Sharpe 1.41, 7.4 R/yr, DD -10.0R
  - Scripts: `run_ym_ny_variable_sweeps_1.py`, `run_ym_ny_variable_sweeps_2.py`, `run_ym_ny_grid_sweep_r1.py`
- **Conclusion**: Optimization improved consistency (0 neg years, Calmar 0.74) but R/yr peaked at ~7.4. Not enough absolute return to justify as a standalone strategy. The edge is real but too small — YM's $5/pt value limits R generation per trade.

### 4. NY Continuation Short-Only — NO-GO
- **Script**: `run_ym_robust_directional.py --session NY --direction short`
- **Config**: Default NY session params, 1s magnifier (structural), 1m magnifier (WF)
- **Phase 1 (Structural)**: PASS — 857 trades, 47.6% WR, PF 1.11, Sharpe 0.77, +49.5R, DD -30.1R, Calmar 1.64.
- **Phase 2 (Walk-Forward)**: FAIL — WFE -0.25, 4/6 OOS folds negative despite high stability (0.88). Combined OOS -13.3R. Edge is in-sample only.
- **Phase 3 (Prop Filter)**: FAIL — Negative expectancy (-0.027R). 2019 -16.3R, 2020 -5.7R, 2021 -1.2R, 2022 -4.9R. Only recent folds (2023-2024) positive.
- **Phase 4 (Hold-Out 2025)**: FAIL — WR 38.5%, Sharpe -0.67, PF 0.91, -5.6R.
- **Phase 5 (MC)**: FAIL — DD p95 69R, ruin prob 79%.
- **Mode params**: rr=3.0, stop=10.0%, gap=2.5%, tp1=0.5
- **Conclusion**: Deceptive — strong structural metrics (+49.5R) but completely fails walk-forward. The full-history edge is overfit to specific regimes. 2019-2022 OOS folds all negative. Do not pursue.

## Key Findings

- **Asia session is dead for YM**: Both in original directional tests and the 3-session discovery sweep (1,296 configs), all Asia configs have 3+ neg years with no viable edge.
- **NY longs have a real but thin edge**: Pass WF (0.56 efficiency) with high param stability and excellent 2025 holdout (Sharpe 2.40, +21.7R). But R/year ceiling is ~7.4R even after full optimization. YM's $5/pt value limits per-trade R generation.
- **NY shorts are a trap**: Look great in-sample (PF 1.11, +49.5R) but WFE is -0.25. Classic overfitting.
- **LDN longs are the strongest walk-forward signal**: 30m ORB longs in London session produced WF Calmars of 4.4–5.0 with WFE 0.6–0.96 and high stability. However, 2/3 candidates failed the 2025 holdout (negative R), and all DSR < 0.05 (overfit to search space).
- **LDN-1 (ORB 25%, RR 3.5, TP1 0.6, long)** is the only YM config to survive holdout (+18.0R, Calmar 1.50) but has PSR 0.837 (weak) and 2016 structural blowup (-30R). Not recommended.
- **Tuesday exclusion is the single biggest improvement for NY**: Calmar nearly doubled (0.35→0.65), eliminated both negative years.
- **YM is comprehensively explored**: 6 strategy tests covering all 3 sessions, both directions, continuation + LSI, with 3,888-config discovery sweep + full pipeline. The $5/pt point value is the structural bottleneck — insufficient R generation per trade for prop firm viability.

### 5. 3-Session ORB Continuation Discovery (NY + Asia + LDN) — NO-GO
- **Status**: **NO-GO** (DSR overfit across all candidates; holdout failed for 2/3 promoted)
- **Scripts**: `run_ym_orb_discovery.py`, `run_ym_orb_discovery_pipeline.py`, `run_ym_orb_phase_one.py`
- **Sweep**: 1,296 configs per session (4 ORB windows × 2 stop modes × 4 RR × 4 TP1 × 3 directions × 5 stop values), 3,888 total. Pre-holdout <2025-01. 1m magnifier.
- **Asia**: Dead — all configs 3+ neg years, best score -1.48. No edge.
- **NY**: Marginal — best config (15m ORB, ATR 5%, RR 3.5, TP1 0.3, long) Calmar 1.93, 1 neg year, but only ~3R/yr.
- **LDN**: Surprise — 30m ORB longs showed structural life. 3 candidates promoted to discovery pipeline.

#### Discovery Pipeline (walk-forward 12m IS / 3m OOS / 3m step, Calmar objective):
| Candidate | OOS R | Calmar | Sharpe | DD | WFE | Stability | Verdict |
|-----------|-------|--------|--------|------|-----|-----------|---------|
| LDN-3 (ATR 15%, RR 2.0, TP1 0.6, long) | +56.9 | 4.98 | 1.29 | -11.4 | 0.878 | 0.823 | PROMOTE |
| LDN-2 (ATR 15%, RR 2.5, TP1 0.5, long) | +61.1 | 4.38 | 1.37 | -13.9 | 0.960 | 0.839 | PROMOTE |
| LDN-1 (ORB 25%, RR 3.5, TP1 0.6, long) | +81.9 | 4.37 | 1.15 | -18.7 | 0.609 | 0.871 | PROMOTE |
| NY-1 (ATR 5%, RR 3.5, TP1 0.3, long) | +24.9 | 1.09 | 0.44 | -22.9 | 1.430 | 0.839 | CHALLENGER |

#### Phase-One Results (structural + prop sim + holdout + PSR/DSR):
| Candidate | Pre R | HO R | Pre PR | HO PR | PSR | DSR | Verdict |
|-----------|-------|------|--------|-------|-----|-----|---------|
| LDN-3 | +38.8 | **-2.5** | 53.9% | 8.3% | 0.928 | 0.029 | CONDITIONAL |
| LDN-2 | +40.0 | **-1.6** | 52.1% | 9.1% | 0.931 | 0.031 | CONDITIONAL |
| LDN-1 | +41.3 | **+18.0** | 47.7% | 26.5% | 0.837 | 0.008 | CONDITIONAL |

- **LDN-3/LDN-2**: Failed holdout (negative R in 2025). Walk-forward success did not transfer.
- **LDN-1**: Survived holdout (+18.0R, Calmar 1.50, Sharpe 1.79) but PSR weak (0.837), DSR overfit (0.008), and 2016 structural blowup (-30.0R).
- **All DSR < 0.05**: Edge does not survive selection bias from 1,296-trial search space.
- **Conclusion**: LDN longs are the best profile found for YM but the edge is too thin to pass the overfitting gate. Not recommended for prop firm deployment.

### 6. NY LSI (Liquidity Sweep Inversion) — Both Directions — NO-GO
- **Status**: **NO-GO** (definitive — losing strategy, no edge)
- **Baseline** (2026-03-01): ORB 09:30-09:35, entry 09:35-15:30, flat 15:50, rr=2.625, tp1=0.3, gap=2.25%, n_left=3, n_right=3, fvg_window=10, absolute stop
- **Both**: 2408 trades, 53.4% WR, **PF 0.90**, -102.5R net, Sharpe -0.74, DD -118.7R, **7/10 neg years**
- **Longs**: 1176 trades, 53.6% WR, PF 0.91, -42.2R net, 7 neg years
- **Shorts**: 1232 trades, 53.3% WR, PF 0.89, -60.2R net, 7 neg years
- **R by year (both)**: 2016:-10 2017:-33 2018:-11 2019:-23 2020:+4 2021:-23 2022:+13 2023:-15 2024:+3 2025:-3
- **Conclusion**: PF < 1.0 in all directions. YM lacks LSI edge entirely. Median stop 74 ticks is fine but the signal is structurally unprofitable.
- **Script**: `run_ym_ny_lsi_baseline.py`
