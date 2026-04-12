# Learnings Library

This directory is the canonical research memory for the backtesting workspace.

## Retrieval Order

Load context in layers so agents do not jump straight into giant histories or raw result files:

1. `backtesting/learnings/README.md`
2. `backtesting/learnings/briefs/GLOBAL.md`
3. `backtesting/learnings/briefs/assets/{SYMBOL}.md`
4. `backtesting/learnings/asset/{SYMBOL}.md` and `backtesting/learnings/global/strategy-memory.md` only when more detail is needed
5. `backtesting/learnings/indexes/assets/{SYMBOL}.md` or `backtesting/learnings/registry/catalog.json` to find exact reports and result artifacts
6. `backtesting/learnings/reports/` and `backtesting/data/results/` only when you need long-form reasoning or raw evidence

## Source Of Truth

- `asset/*.md`
  Detailed, manually maintained per-asset histories. This is where strategy conclusions belong.
- `global/strategy-memory.md`
  Detailed cross-asset strategy memory migrated out of the skill folder.
- `reports/*.md` and `reports/*.html`
  Long-form research reports, pipeline writeups, and council outputs.
- `backtesting/data/results/*`
  Raw evidence, exports, and experiment artifacts. This is an evidence store, not a briefing layer.
- `briefs/*`, `indexes/*`, and `registry/catalog.json`
  Generated access layers for humans and agents. Do not hand-edit these files.

## Update Workflow

When new learnings are added:

1. Update the detailed source file first:
   - `asset/{SYMBOL}.md` for asset conclusions
   - `global/strategy-memory.md` for cross-asset or cross-strategy conclusions
   - `reports/` for long-form writeups
2. Keep raw experiment outputs under `backtesting/data/results/`
3. Regenerate the access layer:

```bash
uv run python backtesting/scripts/build_learnings_registry.py
```

## Conventions

- New narrative learnings should live under `backtesting/learnings/`, not under `.agents/skills/.../references`.
- `backtesting/data/results/` should only hold artifacts, machine outputs, and evidence files.
- When a report narrates a specific result directory, keep the report stem aligned with the result slug when possible.
  Example: `backtesting/learnings/reports/CL_NY_HTF_LSI_PHASE_ONE.md` <-> `backtesting/data/results/cl_ny_htf_lsi_phase_one/`
- Treat `briefs/` as the default LLM loading layer and `reports/` plus `data/results/` as opt-in deeper context.
