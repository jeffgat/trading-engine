# Agent Instructions

This `AGENTS.md` file is the canonical instruction file for Pine Script work. `CLAUDE.md` is only a compatibility pointer for Anthropic tooling.

TradingView references for visual validation, alert parity, and research history. The systematic research engine is `../backtesting`; live execution is `../execution`.

Use Pine v6 for new scripts unless an existing file requires otherwise. Current references live mostly in `atlas_indicators/`, `ilm/HEAD_ilm.pine`, and `orb_continuation/HEAD_*.pine`; older `orb_continuation/v*.pine` files are historical snapshots.

FVG pattern:

- Bullish: `high[2] < low and high[2] < high[1] and low[2] < low`
- Bearish: `low[2] > high and low[2] > low[1] and high[2] > high`

Common futures sessions are Eastern: NY `09:30-09:45`, Asia `20:00-20:15`, LDN often `03:00-03:15`.

Production alert payloads must stay compatible with `../execution/src/trader/broker.py` and TradersPost. Treat Pine results as reference output; confirm parity against `../backtesting/src/orb_backtest/engine/simulator.py` or the execution engines before making research/live claims.
