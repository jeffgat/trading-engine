---
name: agent-first
description: >
  Guide for building agent-first code in the ORB backtesting platform. Use when creating new features,
  API endpoints, signal modules, engine components, dashboard views, or refactoring existing code. Ensures
  every piece of code follows agent-first architecture: structured configs, composable signal pipelines,
  canonical result schemas, API-first design, structured errors, and reproducible backtest history.
  Triggers on new feature, new API route, new signal module, new engine component, schema design, refactor,
  architecture decision.
---

# Agent-First Development Guide

Encode agent-first architecture patterns into every piece of code built for the ORB backtesting platform. The core philosophy: **build every operation as a composable, API-accessible, reproducible unit.** Every action the dashboard performs should go through the same code path a script or agent would use via the API.

## When to Use

Activate this skill when:

- Building a new feature, signal module, or engine component
- Creating or modifying a FastAPI endpoint
- Designing or modifying config dataclasses or result schemas
- Creating a new backtesting workflow or optimization strategy
- Refactoring existing Python modules or frontend components
- Making architecture decisions about the signal pipeline
- Building multi-step workflows (data loading → signals → simulation → metrics)
- Adding error handling or validation logic
- The user invokes `/agent-first` or asks to "make this agent-ready"

## Do NOT Use When

- Fixing a trivial typo or single-line bug
- Updating styling/CSS-only changes with no logic
- Writing Pine Script (Pine Script has its own conventions)
- The task is purely about UI polish with no state or action changes
- Quick exploratory data analysis or one-off scripts

## Workflow

### Step 1: Classify the Work

Before writing any code, classify what is being built:

| Building... | Key agent-first concerns |
|------------|------------------------|
| API endpoint | Structured request/response, config validation, result schema, error responses |
| Config/schema | Frozen dataclass, `with_overrides()` support, serializable to JSON |
| Signal module | Pure function, vectorized, deterministic, testable in isolation |
| Engine component | Numba-compatible, receives config as parameter, returns structured results |
| Dashboard component | Consumes API (not direct imports), displays canonical result schema |
| Optimization workflow | Composable from single-backtest primitives, parallelizable |
| Data pipeline | Instrument-agnostic, cacheable, validates input shape |

### Step 2: Apply Core Principles

Load `references/core-principles.md` for the full 8 principles with code examples.

For every piece of code, verify these **non-negotiable requirements**:

1. **Canonical Configs** — Every operation accepts a frozen, serializable `StrategyConfig` dataclass
2. **Composable Pipeline** — Signal generation, simulation, and metrics are independent, composable stages
3. **Structured Results** — Every backtest returns a complete `BacktestResult` with config, trades, metrics, equity curve
4. **API-First** — Dashboard consumes FastAPI endpoints; no direct Python imports in frontend
5. **Reproducibility** — Every result can be reproduced from its saved config + data
6. **Structured Errors** — Every error includes what went wrong and how to fix it

### Step 3: Apply Patterns

Load `references/patterns.md` for concrete code patterns in Python/FastAPI/React including:

- Config dataclass pattern (frozen, overridable, serializable)
- Signal module pattern (pure, vectorized, deterministic)
- API endpoint pattern (validated request, structured response)
- Structured error pattern
- Result schema pattern (complete, self-describing)
- Composable pipeline pattern

### Step 4: Check Against Checklist

Load `references/checklist.md` for the complete checklist of what must be present in production code.

Run through the checklist before marking any feature complete:

- [ ] Config is a frozen dataclass with `with_overrides()` support
- [ ] Signal functions are pure, vectorized, and deterministic
- [ ] Engine accepts config as parameter (no global state)
- [ ] API endpoint validates input and returns structured response
- [ ] Results include full config used to generate them (reproducibility)
- [ ] Errors are structured with code + reason + fix
- [ ] Dashboard fetches from API (not direct Python imports)
- [ ] Optimization composes from single-backtest primitives
- [ ] New parameters have sensible defaults in config

### Step 5: Review for Anti-Patterns

Reject code that violates these rules:

| Anti-Pattern | Fix |
|-------------|-----|
| Global mutable state for strategy params | Use frozen dataclass passed as argument |
| Signal function with side effects | Make pure: inputs in, outputs out, no mutation |
| Frontend imports Python modules directly | Route through FastAPI endpoint |
| Hardcoded instrument specs | Use `Instrument` dataclass from config |
| Backtest result without config attached | Always bundle config with result for reproducibility |
| Magic numbers in signal logic | Extract to `SessionConfig` or `StrategyConfig` fields |
| Error returns only a string message | Return structured error with code + reason + fix |
| Optimization that can't reuse single-backtest logic | Compose from the same `run_backtest()` primitive |

## Automation Ladder

Load `references/automation-ladder.md` for the full progression framework:

- Level 0: MANUAL — User tunes all parameters by hand
- Level 1: INFORMED — System shows metrics and suggests parameter ranges
- Level 2: GRID SWEEP — System runs parameter grid, user picks best
- Level 3: AUTO-OPTIMIZE — System finds optimal parameters within constraints
- Level 4: ADAPTIVE — System adjusts parameters based on regime detection

Design every feature to support progression up this ladder without architectural changes.

## Error Handling

| Error | Recovery |
|-------|----------|
| Config missing required field | Validate with defaults in dataclass; raise `ValueError` with field name and expected type |
| Data file not found | Return structured error with expected path and download instructions |
| Signal array shape mismatch | Validate input shape at module boundary; include expected vs actual shape in error |
| Numba compilation failure | Ensure all types are explicit; add `@njit` type annotations |
| API endpoint returns 500 | Catch exceptions in endpoint, return structured JSON error, never raw traceback |
