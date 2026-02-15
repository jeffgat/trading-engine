# Agent-First Checklist

Check every item before marking a feature complete. These patterns cost little to build now but become expensive to retrofit later.

---

## Architecture Checklist

### Config Layer
- [ ] Every operation accepts a frozen `StrategyConfig` or `SessionConfig` dataclass
- [ ] Configs support `with_overrides()` for creating variants
- [ ] Configs are JSON-serializable via `to_dict()` / `to_json()`
- [ ] No magic numbers — all parameters live in config dataclasses
- [ ] New parameters have sensible defaults so existing configs still work

### Signal Modules
- [ ] Every signal function is pure: arrays in, arrays out, no side effects
- [ ] Signal functions are deterministic: same inputs always produce same outputs
- [ ] Signals are vectorized with NumPy (or JIT-compiled with Numba for loops)
- [ ] No global state — all inputs are function parameters
- [ ] Signal modules can be tested independently with synthetic data

### Engine Components
- [ ] Simulation receives config as explicit parameters (not global state)
- [ ] Numba `@njit` functions use only primitive types and arrays
- [ ] Exit types are defined as module-level integer constants
- [ ] Engine returns structured `TradeResult` tuples/NamedTuples
- [ ] Engine is decoupled from signal generation (receives pre-computed signals)

### API Endpoints
- [ ] Every endpoint validates input with Pydantic models and `Field` constraints
- [ ] Every response follows the structured `{success, result, error}` pattern
- [ ] Every error returns `{code, reason, fix}` — never raw tracebacks
- [ ] Same endpoint serves dashboard, CLI scripts, and future agents
- [ ] POST endpoints for mutations, GET for reads, DELETE for removal

### Result Schemas
- [ ] Every backtest result includes the complete config that produced it
- [ ] Results have unique IDs and timestamps
- [ ] Results include full trade list, metrics, and equity curve
- [ ] Results are JSON-serializable and self-contained
- [ ] A result file alone is sufficient to understand and reproduce the backtest

### Composable Pipeline
- [ ] Pipeline stages (data → signals → simulate → metrics → export) are independent
- [ ] Each stage can be called, tested, and replaced individually
- [ ] Optimization composes from the same `run_backtest()` primitive
- [ ] Adding a new signal module doesn't require changes to the engine
- [ ] CLI, API, and optimizer all use the same pipeline

### Data Layer
- [ ] Instrument specs are in a declarative registry (not hardcoded)
- [ ] Data loading is instrument-agnostic (parameterized by symbol)
- [ ] Data caching uses Parquet for fast reloads
- [ ] Data validation checks expected column names and types
- [ ] Missing data returns a structured error with download instructions

### Frontend Integration
- [ ] Dashboard consumes FastAPI endpoints only (no direct Python imports)
- [ ] TypeScript interfaces mirror Python result schemas
- [ ] API calls go through custom hooks (not raw `fetch` in components)
- [ ] Structured errors from API are displayed with `{code, reason, fix}`
- [ ] Config state in frontend matches the config schema in backend

---

## Anti-Pattern Checklist

Reject code that does any of the following:

- [ ] Global mutable state for strategy parameters
- [ ] Signal function with side effects (file I/O, printing, mutation)
- [ ] Frontend importing Python modules directly
- [ ] Hardcoded instrument specs (point value, tick size) as literals
- [ ] Backtest result without the config that produced it
- [ ] Magic numbers in signal or engine logic
- [ ] Error responses as plain strings
- [ ] Optimization engine that duplicates backtest logic instead of composing it
- [ ] Numba function that accepts Python objects (must be primitives/arrays)
- [ ] API endpoint that returns raw exception tracebacks

---

## What NOT to Do (Strategic Pitfalls)

1. **Don't scatter parameters** — All strategy parameters belong in `StrategyConfig` or `SessionConfig`. If you're tempted to add a parameter as a function argument that isn't in a config, add it to the config instead.

2. **Don't couple signals to the engine** — Signal generation and trade simulation are separate stages. A new signal module should slot in without modifying `simulator.py`.

3. **Don't build a separate optimization engine** — Optimization is `run_backtest()` called in a loop with different configs. No parallel code path.

4. **Don't return results without configs** — Every result must include the exact config that produced it. Comparing results without knowing their configs is meaningless.

5. **Don't hardcode instruments** — Adding a new instrument should require one line in the registry, not changes across multiple files.
