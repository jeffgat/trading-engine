# Agent-First Core Principles

These 8 principles govern all architecture decisions in the ORB backtesting platform.

---

## 1. Configs Should Be Canonical, Not Scattered

Every operation must accept a **frozen, serializable config dataclass** as its single source of truth. No global variables, no scattered parameters, no magic numbers.

```python
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class SessionConfig:
    orb_start: str = "09:30"
    orb_end: str = "09:45"
    entry_start: str = "09:45"
    entry_end: str = "13:00"
    flat_start: str = "15:50"
    flat_end: str = "16:00"
    sl_pct: float = 0.075       # stop loss as % of daily ATR
    min_gap_pct: float = 0.0225  # min FVG size as % of ATR
    max_gap_pts: float = 100.0   # max FVG size in points

@dataclass(frozen=True)
class StrategyConfig:
    instrument: Instrument
    sessions: tuple[SessionConfig, ...]
    risk_per_trade: float = 5000.0
    reward_risk: float = 2.5
    tp1_ratio: float = 0.5
    atr_length: int = 14
    be_offset_ticks: int = 4

    def with_overrides(self, **kwargs) -> "StrategyConfig":
        """Create a new config with dot-notation overrides."""
        return replace(self, **kwargs)
```

**Why**: An agent or optimizer can construct any config programmatically. Every backtest result stores the exact config that produced it. No ambiguity about what parameters were used.

---

## 2. Signals Should Be Pure and Composable

Every signal module (FVG detection, ORB computation, session filtering) must be a **pure function**: arrays in, arrays out, no side effects, deterministic.

```python
# signals/fvg.py — Pure vectorized signal generation
import numpy as np

def detect_bullish_fvg(
    high: np.ndarray, low: np.ndarray
) -> np.ndarray:
    """Detect bullish FVGs. Returns boolean mask.

    Pure function: same inputs always produce same outputs.
    No global state, no side effects.
    """
    mask = np.zeros(len(high), dtype=np.bool_)
    mask[2:] = (high[:-2] < low[2:]) & (high[:-2] < high[1:-1]) & (low[:-2] < low[2:])
    return mask
```

**Why**: Pure functions are testable in isolation, composable in any order, parallelizable across instruments/sessions, and cacheable. An optimizer can swap signal modules without changing the engine.

---

## 3. Results Should Be Self-Describing

Every backtest result must be a **complete, self-describing record** that includes the config, trades, metrics, and equity curve. A result file alone must contain everything needed to understand and reproduce the backtest.

```python
# Result schema — complete and self-describing
result = {
    "id": "bt_20240115_143022_abc123",
    "timestamp": "2024-01-15T14:30:22Z",
    "config": {
        "instrument": {"symbol": "NQ", "point_value": 20.0, "tick_size": 0.25},
        "sessions": [{"name": "NY", "orb_start": "09:30", ...}],
        "risk_per_trade": 5000.0,
        "reward_risk": 2.5,
        # ... complete config
    },
    "metrics": {
        "total_trades": 145,
        "win_rate": 0.483,
        "profit_factor": 1.62,
        "sharpe_ratio": 1.85,
        "sortino_ratio": 2.31,
        "max_drawdown": -12500.0,
        "max_drawdown_pct": 0.08,
        "net_pnl": 47250.0,
        "avg_win": 6850.0,
        "avg_loss": -4200.0,
        # ... complete metrics
    },
    "trades": [...],  # full trade list with entry/exit details
    "equity_curve": [...],  # cumulative PnL series
}
```

**Why**: An agent can compare results, rank strategies, and make decisions based on structured metrics. Results are portable — share a JSON file, get the full picture.

---

## 4. The Pipeline Should Be Composable, Not Monolithic

The backtesting pipeline must be composed of **independent stages** that can be called, tested, and replaced individually.

```
Pipeline stages (each is independent):

1. data.load(instrument, timeframe)     → DataFrame (OHLCV)
2. signals.orb(df, session_config)      → ORB high/low arrays
3. signals.fvg(df)                      → FVG detection arrays
4. signals.session(df, session_config)  → Session time masks
5. signals.atr(df, length)              → Daily ATR array
6. engine.simulate(df, signals, config) → list[TradeResult]
7. results.metrics(trades, config)      → MetricsDict
8. results.export(trades, metrics, config) → BacktestResult JSON
```

**Why**: An optimizer calls stages 1-8 with different configs in parallel. A new signal module (e.g., volume filter) slots into step 3 without touching the engine. The dashboard can display results from any stage independently.

---

## 5. The API Should Be the Single Source of Truth

The React dashboard must consume **FastAPI endpoints only** — never import Python modules directly. The API is the contract between frontend and backend.

```python
# api.py — Structured endpoint
@app.post("/api/backtest")
async def run_backtest(request: BacktestRequest) -> BacktestResponse:
    """Run a single backtest. Same endpoint used by dashboard and scripts."""
    try:
        config = build_config(request)
        df = load_data(config.instrument)
        trades = simulate(df, config)
        metrics = compute_metrics(trades, config)
        result = export_result(trades, metrics, config)
        save_result(result)
        return BacktestResponse(success=True, result=result)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail={
            "code": "VALIDATION_ERROR",
            "reason": str(e),
            "fix": "Check parameter types and ranges",
        })
```

```typescript
// Frontend — consumes the same API
const response = await fetch("/api/backtest", {
  method: "POST",
  body: JSON.stringify(config),
});
const result: BacktestResult = await response.json();
```

**Why**: One code path for all consumers. The dashboard, CLI scripts, and future agents all use the same API. Changes to the engine are invisible to the frontend as long as the API contract holds.

---

## 6. Errors Should Be Structured and Actionable

Every error must include a machine-readable code, a human-readable reason, and an actionable fix.

```python
# Structured error responses
class BacktestError(Exception):
    def __init__(self, code: str, reason: str, fix: str):
        self.code = code
        self.reason = reason
        self.fix = fix

# Error catalog
ERRORS = {
    "DATA_NOT_FOUND": lambda sym: BacktestError(
        code="DATA_NOT_FOUND",
        reason=f"No data file found for {sym}",
        fix=f"Run: python scripts/download_data.py {sym}",
    ),
    "INVALID_SESSION": lambda name: BacktestError(
        code="INVALID_SESSION",
        reason=f"Unknown session '{name}'",
        fix="Valid sessions: NY, ASIA, LDN",
    ),
    "EMPTY_RESULT": lambda: BacktestError(
        code="EMPTY_RESULT",
        reason="Backtest produced zero trades",
        fix="Widen entry window, lower min_gap_pct, or check session times",
    ),
}
```

**Why**: An agent can parse error codes and take corrective action automatically. An optimizer can skip invalid configs without crashing. The dashboard can display meaningful error messages.

---

## 7. Instruments Should Be Declarative, Not Hardcoded

Every instrument's specs (point value, tick size, symbol) must be defined in a **declarative registry**, not scattered as magic numbers.

```python
@dataclass(frozen=True)
class Instrument:
    symbol: str
    point_value: float
    tick_size: float
    currency: str = "USD"

# Instrument registry — single source of truth
INSTRUMENTS = {
    "NQ": Instrument("NQ", point_value=20.0, tick_size=0.25),
    "MNQ": Instrument("MNQ", point_value=2.0, tick_size=0.25),
    "ES": Instrument("ES", point_value=50.0, tick_size=0.25),
    "MES": Instrument("MES", point_value=5.0, tick_size=0.25),
    "NKD": Instrument("NKD", point_value=5.0, tick_size=5.0),
}
```

**Why**: Adding a new instrument means adding one line to the registry. Position sizing, PnL calculation, and lot rounding all derive from the instrument spec automatically. No risk of using NQ's point value for an ES backtest.

---

## 8. History Should Enable Comparison

Every backtest and optimization result must be saved with enough context to enable meaningful comparison across runs.

```python
# Save with full context to DB
def save_result(result: dict) -> str:
    """Save result to experiments.db with unique ID and full config."""
    result_id = generate_backtest_id(result)
    log_run(result, result_id)
    return result_id

# Compare across runs
def compare_results(result_ids: list[str]) -> dict:
    """Load multiple results from DB and compare key metrics side by side."""
    results = [get_backtest_result(rid) for rid in result_ids]
    return {
        "configs_diff": diff_configs([r["config"] for r in results]),
        "metrics_comparison": tabulate_metrics([r["metrics"] for r in results]),
    }
```

**Why**: An agent can query the experiment DB to find the best-performing config, detect parameter drift, or identify which changes improved/degraded performance. Optimization results feed into the next round of experimentation.
