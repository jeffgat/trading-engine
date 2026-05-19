# Agent Instructions

This `AGENTS.md` file is the canonical instruction file for backtesting work. `CLAUDE.md` is only a compatibility pointer for Anthropic tooling.

Python research engine for ORB/FVG, LSI/HTF-LSI/reference-LSI, CISD, IB, VWAP, gap-fill, news, regime, and portfolio workflows.

Commands:

```bash
uv sync --extra data --extra storage --extra api --extra dev
uv run python scripts/run_backtest.py --data NQ_5m.csv --instrument NQ --sessions NY --name "NQ NY Baseline"
uv run python scripts/run_optimize.py --data NQ_5m.csv --instrument NQ --sessions NY --sweep ny_stop_atr_pct=5:25:1 --name "NQ NY stop sweep"
uv run python scripts/run_server.py
uv run pytest
```

Core map: `config.py` owns `Instrument`, `SessionConfig`, `StrategyConfig`, defaults, and `with_overrides()`; `engine/simulator.py` owns `run_backtest()` and signal extraction; `signals/` owns FVG, ORB, swing/sweep, HTF/reference levels; `optimize/` owns grid/LHS/Optuna/WFO; `results/` and `experiments*.py` serialize dashboard-visible runs.

Research discipline:

- Before strategy work, read `learnings/README.md`, `learnings/briefs/GLOBAL.md`, then `learnings/briefs/assets/{SYMBOL}.md`; open detailed histories/reports only as needed.
- After meaningful conclusions, update detailed learnings with metrics and DB experiment names, then run `uv run python scripts/build_learnings_registry.py`.
- Always give runs and sweeps a unique descriptive `--name`; dashboard review needs saved results with trades and equity curve.
- Optimize on Calmar first, report drawdown in R, and use train/validation/test, walk-forward, Monte Carlo/bootstrap, and deployability labels before promotion.

Engine invariants:

- Times/session logic are US Eastern. 5m bars drive signals; 1m/1s data improves fills, exits, charts, and exact replay.
- Results and reports use R units, not raw USD PnL.
- Hard constraints: `rr >= 1.0`, `tp1_ratio * rr >= 1.0`, `exit_mode="single_target"` requires `tp1_ratio=1.0`, and final stop distance is floored at `5%` of daily ATR.
- Strategy modes include `continuation`, `reversal`, `inversion`, `cisd`, `lsi`, `htf_lsi`, `reference_lsi`, and `ib`.
- Liquidity sweeps must use `signals/swing.py` plus `signals/liquidity_sweep.py`; pivots and sweeps use strict greater/less-than logic, so touches do not count.
- `run_backtest()` defaults to one filled trade per strategy/session day; portfolio scripts may intentionally combine independent legs and allow overlap.

Historical runs for `execution/config/exec_configs.json` profiles must use execution exact replay, not a hand-built research config:

```bash
cd ../execution
PYTHONUNBUFFERED=1 .venv/bin/python scripts/save_exact_exec_backtests.py --profiles FAST_V1.1 FAST_V2.1 GENERAL_V1 --years 5
```
