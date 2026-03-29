# Progress Tracking Template

This template is used to create a temporary progress file that survives context compaction. The agent creates it at the start of the workflow, updates it after every significant result, and deletes it after Step 6.

**File location**: `python/{asset}_{session}_progress.md` (e.g., `python/es_ny_progress.md`)

---

Copy everything below this line into the progress file, filling in values as you go:

---

```markdown
# {INSTRUMENT} {SESSION} {STRATEGY} {DIRECTION} — Optimization Progress

**Started**: {DATE}
**Current Step**: {1-6} — {step name}
**Sweep Round**: R{N}

## Instrument & Data
- Symbol: {INSTRUMENT} | Tick size: {TICK_SIZE} | Point value: {POINT_VALUE}
- Data: {DATA_FILE_5M} | Start: {START_DATE} | Years: {DATA_YEARS}
- 1m: {YES/NO} | 1s: {YES/NO}

## Current Anchor Config

| Parameter | Value |
|-----------|-------|
| stop_atr_pct | |
| stop_orb_pct | |
| orb_start | |
| orb_end | |
| entry_start | |
| entry_end | |
| flat_start | |
| flat_end | |
| atr_length | |
| direction_filter | |
| rr | |
| tp1_ratio | |
| min_gap_atr_pct | |
| max_gap_atr_pct | |
| max_gap_points | |
| impulse_close_filter | |
| dow_exclusion | |
| sma_period | |
| qualifying_move_atr_pct | |
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

<!-- Append one entry per sweep pass/round. Keep ALL previous entries — this is the history. -->
<!-- Stand-alone pass runs once (13 dims). Core rounds iterate (3 dims) until converged. -->

### Stand-Alone Pass (R1)
- **Anchor entering**: {one-line config summary: stop=X%, rr=X, gap=X%, tp1=X, dir=X, ...}
- **Adoptions**: {dim: old→new (Calmar Δ+X.XX)} or "0 stand-alone adoptions"
- **Anchor exiting**: {updated one-line summary}
- **Calmar**: {before} → {after}

<!-- Copy this block for each core convergence round:
### Core R{N}
- **Anchor entering**: {one-line: stop=X%, rr=X, tp1=X}
- **Adoptions**: {dim: old→new (Calmar Δ+X.XX)} or "0 core adoptions — CONVERGED"
- **Anchor exiting**: {updated one-line summary}
- **Calmar**: {before} → {after}
-->

## Grid Sweep Log

<!-- Append one entry per grid sweep. -->

<!-- Copy this block for each grid:
### Grid R{N}
- **Combos**: {total} | Skipped (<10 tick): {count} | 0-neg-year: {count}
- **Winner**: stop={X}%, rr={X}, gap={X}%, tp1={X} | Calmar={X.XX}
- **Anchor Calmar**: {X.XX}
- **Delta vs anchor**: {+X.XX}
- **Decision**: {Proceed to pipeline / Loop back to variable sweeps R{N+1}}
-->

## Pipeline Result

<!-- Fill after robust pipeline completes. Leave blank until then. -->

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | | |
| 2 — Walk-Forward | | |
| 3 — Prop Filter | | |
| 4 — Hold-Out OOS | | |
| 5 — Monte Carlo | | |
| **Verdict** | | |

## Scripts Generated

<!-- Check off as each script is created. -->

- [ ] `run_{asset}_{session}_baseline.py`
- [ ] `run_{asset}_{session}_variable_sweeps_1.py`

<!-- Add more as they are generated -->

## Next Action

<!-- Update this after every step. This tells the agent exactly what to do next. -->

{What to do next — e.g., "Run variable sweeps R2 with updated anchor" or "Generate grid sweep script" or "Run robust pipeline"}
```
