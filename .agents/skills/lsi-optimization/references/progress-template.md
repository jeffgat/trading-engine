# LSI Progress Tracking Template

**File location**: `python/{asset}_{session}_lsi_progress.md` (e.g., `python/nq_ny_lsi_progress.md`)

Copy everything below this line into the progress file, filling in values as you go:

---

```markdown
# {INSTRUMENT} {SESSION} LSI {DIRECTION} — Optimization Progress

**Started**: {DATE}
**Current Step**: {1-6} — {step name}
**Sweep Round**: R{N}

## Instrument & Data
- Symbol: {INSTRUMENT} | Tick: {TICK_SIZE} | Point value: {POINT_VALUE}
- Data: {DATA_FILE_5M} | Start: {START_DATE} | Years: {DATA_YEARS}
- 1m: {YES/NO} | 1s: {YES/NO}

## Current Anchor Config

| Parameter | Value |
|-----------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| lsi_n_left | |
| lsi_n_right | |
| lsi_fvg_window_left | |
| lsi_fvg_window_right | |
| entry_start | |
| entry_end | |
| flat_start | |
| flat_end | |
| atr_length | |
| direction_filter | |
| rr | |
| tp1_ratio | |
| min_gap_atr_pct | |
| dow_exclusion | |
| sma_period | |
| weekly_loss_cap_r | |
| monthly_loss_cap_r | |

## Current Anchor Metrics

| Metric | Value |
|--------|-------|
| Trades | |
| Win Rate | |
| PF | |
| Sharpe | |
| Net R | |
| R/yr | |
| Max DD | |
| Calmar | |
| Neg full years | |
| Median stop (ticks) | |

## Adoption Log

<!-- Append one entry per sweep pass/round. Keep ALL previous entries. -->

### Stand-Alone Pass (R1)
- **Anchor entering**: {one-line config summary: n_left=X, n_right=X, fvg_left=X, fvg_right=X, rr=X, gap=X%, tp1=X, dir=X}
- **Adoptions**: {dim: old→new (Calmar Δ+X.XX)} or "0 stand-alone adoptions"
- **Anchor exiting**: {updated one-line summary}
- **Calmar**: {before} → {after}

<!-- Copy this block for each core convergence round:
### Core R{N}
- **Anchor entering**: {one-line: rr=X, tp1=X}
- **Adoptions**: {dim: old→new (Calmar Δ+X.XX)} or "0 core adoptions — CONVERGED"
- **Anchor exiting**: {updated one-line summary}
- **Calmar**: {before} → {after}
-->

## Grid Sweep Log

<!-- Append one entry per grid sweep. -->

<!-- Copy this block for each grid:
### Grid R{N}
- **Combos**: {total} | Skipped (<10 tick): {count} | 0-neg-year: {count}
- **Winner**: rr={X}, tp1={X}, gap={X}% | Calmar={X.XX}
- **Anchor Calmar**: {X.XX}
- **Delta vs anchor**: {+X.XX}
- **Decision**: {Proceed to pipeline / Loop back to variable sweeps R{N+1}}
-->

## Pipeline Result

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | | |
| 2 — Walk-Forward | | |
| 3 — Prop Filter | | |
| 4 — Hold-Out OOS | | |
| 5 — Monte Carlo | | |
| **Verdict** | | |

## Scripts Generated

- [ ] `run_{asset}_{session}_lsi_baseline.py`
- [ ] `run_{asset}_{session}_lsi_variable_sweeps_1.py`

<!-- Add more as generated -->

## Next Action

{What to do next — e.g., "Run variable sweeps R2 with updated anchor" or "Generate grid sweep script"}
```
