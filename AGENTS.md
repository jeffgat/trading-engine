# Agent Instructions

This `AGENTS.md` file is the canonical instruction file for this repo. `CLAUDE.md` files are only compatibility pointers for Anthropic tooling.

Workspace for futures strategy research, live/dry execution, dashboards, and TradingView parity:

- `backtesting/` — Python research engine, sweeps, data sync, learnings, experiment DB
- `execution/` — DataBento -> execution engines -> TradersPost service
- `frontend/` — React dashboard for research and execution
- `pinescript/` — TradingView references and alert-parity scripts

For scoped work, also read the local `AGENTS.md` in the relevant directory:

- [backtesting/AGENTS.md](backtesting/AGENTS.md)
- [execution/AGENTS.md](execution/AGENTS.md)
- [frontend/AGENTS.md](frontend/AGENTS.md)
- [pinescript/AGENTS.md](pinescript/AGENTS.md)

Research-memory workflow for strategy/backtesting questions:

- Directly read required briefing files first when the task is strategy work: `backtesting/learnings/README.md`, `backtesting/learnings/briefs/GLOBAL.md`, then `backtesting/learnings/briefs/assets/{SYMBOL}.md`.
- Use `cd backtesting && uv run python scripts/research_memory.py ask "<question>"` to locate relevant prior work when the exact file/report is unknown.
- Treat research-memory results as a source map. Before making conclusions, changing direction, or recommending stop/continue, open and read the cited files directly.
- Use experiment DB queries, saved artifacts, and deterministic replay/stress runs for numeric truth; do not treat retrieval scores or summaries as validation evidence.
