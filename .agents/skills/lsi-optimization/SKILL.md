---
name: lsi-optimization
description: "End-to-end optimization workflow for the LSI (Liquidity Sweep Inversion) strategy. Six-step pipeline from baseline through prop-firm-ready validated config. Use when the user asks to optimize, test, or run sweeps for an LSI strategy on any instrument/session. Triggers on 'lsi optimization', 'optimize lsi', 'lsi sweeps', 'lsi baseline', 'lsi variable sweeps', 'lsi pipeline', or any request to run the LSI workflow end-to-end or by step."
---

# LSI Optimization

Six-step end-to-end workflow for the Liquidity Sweep Inversion (LSI) strategy. Generates runnable Python scripts at each step.

**Strategy recap**: LSI = swing level swept → FVG forms within window → FVG inverted → entry at inversion bar close. Stop is **structural** (geometric, not ATR-based). ORB window is vestigial (minimal 09:30-09:35, unused). FVG detection uses `detect_fvg_no_orb` — no ORB directional filter.

**HARD CONSTRAINT — 10-Tick Minimum Stop**: Skip any config where `median(t.risk_points / instrument.min_tick) < 10`. LSI structural stops are inherently wider than ATR stops — 10 ticks is a floor, not a target.

**HARD CONSTRAINT — Minimum TP1 Ratio 0.2**: Never test or adopt `tp1_ratio < 0.2`.

**DD is NOT a hard filter**: Always set `max_drawdown_r=999.0`. Report DD as INFO.

Calmar ratio is the primary optimization objective throughout.

## Before Starting

Gather from user:
1. **Instrument** symbol (NQ, ES, GC, CL, etc.)
2. **Session** (NY, ASIA, LDN)
3. **Direction hint** (longs, shorts, or both — longs tend to dominate LSI)

Then verify:
- Read `python/learnings/{SYMBOL}.md` — if LSI + this session/direction is already NO-GO, stop.
- Confirm data files exist: `{SYMBOL}_5m.csv` (required), `{SYMBOL}_1m.csv`, `{SYMBOL}_1s.parquet`.
- Determine `START_DATE` (default `2016-01-01`).
- Compute `DATA_YEARS` from start to current date.

## Progress Tracking

Maintain `python/{asset}_{session}_lsi_progress.md` throughout. Create from `references/progress-template.md` at Step 1. Update after every significant result. Delete after Step 6.

If a progress file already exists, **resume from where it left off**.

## Step 1: Baseline

Generate `run_{asset}_{session}_lsi_baseline.py`.

```python
SESSION = SessionConfig(
    name="{SESSION}",
    orb_start="09:30", orb_end="09:35",   # minimal — unused by LSI
    entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=0.0,        # unused — LSI uses structural stop
    min_gap_atr_pct=2.25,
)

BASELINE = StrategyConfig(
    rr=2.625, tp1_ratio=0.3, atr_length=14,
    sessions=(SESSION,), instrument={INSTRUMENT},
    strategy="lsi", direction_filter="both",
    use_bar_magnifier=True,
    lsi_n_left=3, lsi_n_right=3,
    lsi_fvg_window_left=10, lsi_fvg_window_right=10,
    lsi_stop_mode="absolute",
)
```

Run both directions. Print directional breakdown and median stop ticks.

**Pass criteria**: >100 trades AND PF >1.0 AND median stop >= 10 ticks (per direction).

**Progress**: Create progress file from `references/progress-template.md`. Record baseline metrics per direction. Set Next Action.

## Step 2: Variable Sweeps

Generate `run_{asset}_{session}_lsi_variable_sweeps_{N}.py`. See `references/variable-sweep-template.md` for complete runnable script template.

### Step 2a: Stand-Alone Sweeps (single pass, no re-sweep)

| # | Dimension | Config field | Typical values |
|---|-----------|-------------|----------------|
| 1 | Direction | `direction_filter` | both, long, short |
| 2 | LSI N-Left | `lsi_n_left` | 2, 3, 4, 5, 6, 8, 10 |
| 3 | LSI N-Right | `lsi_n_right` | 2, 3, 4, 5, 6, 8, 10 |
| 4 | FVG Window Left | `lsi_fvg_window_left` | 3, 5, 7, 10, 15, 20 |
| 5 | FVG Window Right | `lsi_fvg_window_right` | 3, 5, 7, 10, 15, 20 |
| 6 | Min Gap ATR % | `min_gap_atr_pct` | 0.5, 1.0, 1.5, 2.25, 3.0, 4.0, 5.0 |
| 7 | ATR Length | `atr_length` | 5, 7, 10, 14, 20, 30 |
| 8 | Entry Start | `entry_start` | 09:35, 10:00, 10:30 |
| 9 | Entry End | `entry_end` | 11:00, 12:00, 13:00, 14:00, 15:30 |
| 10 | DOW Exclusion | post-backtest filter | none, Mon, Tue, Wed, Thu, Fri, Mon+Fri, Thu+Fri |
| 11 | SMA Trend Gate | post-backtest filter | OFF, 20, 50, 100, 200 |
| 12 | Weekly Loss Cap | post-backtest | OFF, 2.0, 3.0, 4.0, 5.0, 7.0 |
| 13 | Monthly Loss Cap | post-backtest | OFF, 3.0, 5.0, 7.0, 10.0, 15.0 |

**Do NOT sweep `lsi_stop_mode`** — "fvg" mode produces degenerate results (22% WR) at standard RR params. Stick to `"absolute"`.

### Step 2b: Core Convergence Loop (iterative re-sweep)

LSI has only 2 core dimensions (structural stop is fixed — not a free parameter):

| # | Dimension | Config field | Typical values |
|---|-----------|-------------|----------------|
| 1 | R:R ratio | `rr` | 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0 |
| 2 | TP1 ratio | `tp1_ratio` | 0.2, 0.3, 0.4, 0.5, 0.6, 0.7 |

Re-sweep until 0 adoptions in a full pass. Typically converges in 1-2 rounds.

### Sweep Script Requirements

- Print table per dimension: Trades, WR, PF, Sharpe, Net R, R/yr, MaxDD, Calmar, NegYr, MedStop.
- **Adoption rule**: Calmar delta > +0.3 AND no new negative full years AND trades >100 AND median stop >= 10 ticks.
- DOW and SMA filters applied post-backtest via `apply_dow_filter()` / `apply_sma_trend_gate()` from `gates.py`.
- Loss caps applied post-backtest via `apply_weekly_loss_cap()` / `apply_monthly_loss_cap()` from `gates.py`.

## Step 3: Grid Sweep

Generate `run_{asset}_{session}_lsi_grid_sweep_r{N}.py`.

LSI has a fixed structural stop — grid over RR × TP1 × min_gap (3D):

```python
RR_VALUES   = [anchor-0.5, anchor-0.25, anchor, anchor+0.25, anchor+0.5]
TP1_VALUES  = [anchor-0.1, anchor, anchor+0.1]  # min 0.2 hard constraint
GAP_VALUES  = [anchor-0.5, anchor, anchor+0.5, anchor+1.0]
```

Target: 100-300 combos. Print Top 20 by Calmar (all) and Top 20 (0 neg years only).

**Decision**: Grid winner >0.5 Calmar above anchor → loop back to variable sweeps. Otherwise converged → proceed to Step 4.

## Step 4: Robust Pipeline

Generate `run_{asset}_{session}_lsi_robust_pipeline.py`. See `references/pipeline-template.md`.

Five phases:
1. **Structural**: Trades >100, WR >35%, PF >1.2, Calmar >0.5, median stop >= 10 ticks
2. **Walk-Forward**: 36m IS / 12m OOS / 12m step. Objective: sharpe. PASS: WF efficiency >0.5, stability >=0.4
3. **Prop Firm**: `max_drawdown_r=999.0`, `min_annual_r=12.0`, `max_monthly_loss_r=5.0`. DD INFO only.
4. **Hold-Out OOS**: 2025+ data. PASS: PF >0.9, R >0, Sharpe >0.5
5. **Monte Carlo**: 1000 bootstraps. Ruin = -25R. PASS: survival >=60%

**Verdict**: GO (5/5), CONDITIONAL (4/5), NO-GO (≤3/5).

## Step 5: Save Final Config

Generate `save_{asset}_{session}_lsi_r{N}_final.py`. See `references/save-template.md`.

```python
CONFIG = StrategyConfig(
    ...,
    name="{INSTRUMENT} {SESSION} LSI {direction} 2016-2026 Final",
    notes="Post lsi-optimization pipeline.",
)
result = results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
save_backtest_result(result)
```

## Step 6: Update Learnings

Open `python/learnings/{SYMBOL}.md`. Add LSI section with GO/CONDITIONAL/NO-GO status, final config table, key metrics from each pipeline phase, all scripts generated, parameter sensitivity notes. Delete progress file.

## Script Naming Convention

| Step | Pattern | Example |
|------|---------|---------|
| Baseline | `run_{asset}_{session}_lsi_baseline.py` | `run_nq_ny_lsi_baseline.py` |
| Variable sweeps | `run_{asset}_{session}_lsi_variable_sweeps_{N}.py` | `run_nq_ny_lsi_variable_sweeps_1.py` |
| Grid sweep | `run_{asset}_{session}_lsi_grid_sweep_r{N}.py` | `run_nq_ny_lsi_grid_sweep_r1.py` |
| Robust pipeline | `run_{asset}_{session}_lsi_robust_pipeline.py` | `run_nq_ny_lsi_robust_pipeline.py` |
| Save final | `save_{asset}_{session}_lsi_r{N}_final.py` | `save_nq_ny_lsi_r1_final.py` |

## Key Code Conventions

1. `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))` at top.
2. `use_bar_magnifier=True` always. Load 1s via `load_1s_for_5m` (returns None if missing).
3. `stop_atr_pct=0.0` in SessionConfig — structural stop only.
4. `strategy="lsi"` always.
5. DOW/SMA/loss cap filters: post-backtest, not baked into config.
6. `dataclasses.replace()` for config variants.
7. Exclude current partial year when counting negative years.
8. Progress file: `python/{asset}_{session}_lsi_progress.md`.

## References

- `references/variable-sweep-template.md` — Complete runnable script template for sweep scripts
- `references/progress-template.md` — Progress file template (copy and fill in)
- `references/pipeline-template.md` — Robust pipeline script template
- `references/save-template.md` — Save final config script template
