# Global Brief

Use this as the short cross-asset entrypoint before loading detailed histories.

## Default Read Order

1. `backtesting/learnings/README.md`
2. The relevant `backtesting/learnings/briefs/assets/{SYMBOL}.md`
3. `backtesting/learnings/asset/{SYMBOL}.md` only if the brief is not enough
4. `backtesting/learnings/indexes/assets/{SYMBOL}.md` or `backtesting/learnings/registry/catalog.json` to find specific reports and result folders
5. `backtesting/learnings/global/strategy-memory.md` when you need cross-asset nuance or historical reasoning that spans multiple assets

## What Lives Where

- `backtesting/learnings/global/strategy-memory.md`
  Full cross-asset strategy memory. This replaced the old skill-local learnings file.
- `backtesting/learnings/asset/{SYMBOL}.md`
  Detailed asset histories and conclusions.
- `backtesting/learnings/reports/`
  Long-form writeups and council outputs.
- `backtesting/data/results/`
  Raw evidence and exports. Do not treat it as the first thing to load.

## Practical Rule

For a new backtest on an asset like `NQ`, start with the `NQ` brief, then the `NQ` detailed history, then the `NQ` index. Only open individual reports or result artifacts when the brief or index tells you which ones matter.
