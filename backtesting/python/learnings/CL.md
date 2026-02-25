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

---

## What Works on CL

- **10-minute ORB** (09:30-09:40) — ORB 10m was +218% vs ORB 15m in R1. This structural finding may still hold at wider stops.
- **ATR 10** — Short ATR adapts to CL's volatile sessions. Likely still valid.
- **entry_end 14:00** — CL has afternoon continuation. Likely still valid.

## What Doesn't Work on CL

- **Continuation at stop_atr_pct < 7%** — Sub-tick stops, invalidated by 10-tick floor. The optimizer consistently pushed toward impossibly tight stops, masking the lack of edge at realistic distances.
- **Reversal / inversion strategies** — Not yet tested on clean data.
- **Asia / LDN sessions** — Not yet tested.

## Parameter Sensitivity

All parameter sensitivity findings from R1-R4 are **INVALID** — they were measured at sub-tick stop distances. The dominant "finding" (tight stops + high RR = best Calmar) was a simulator artifact.

## Prop Firm Considerations

CL continuation has no viable edge at realistic stop distances. Not deployable.

## Outstanding Questions

- Re-test continuation with stop_atr_pct range starting at 7%+ (realistic 10+ tick stops)
- Test other instruments for similar sub-tick stop contamination (GC, ES, NQ have wider ATR-to-tick ratios and are likely unaffected)
- Continuation long-only vs short-only at realistic stops
- Reversal / inversion strategies on clean data
- Asia / LDN sessions on CL
