# Agent-First Code Patterns

Concrete code patterns for the ORB backtesting codebase (Python, FastAPI, NumPy/Numba, React/Vite).

---

## Pattern 1: Config Dataclass (Frozen, Overridable, Serializable)

Every strategy configuration is a frozen dataclass with override support and JSON serialization.

```python
# config.py
from dataclasses import dataclass, replace, asdict
import json

@dataclass(frozen=True)
class SessionConfig:
    name: str = "NY"
    orb_start: str = "09:30"
    orb_end: str = "09:45"
    entry_start: str = "09:45"
    entry_end: str = "13:00"
    flat_start: str = "15:50"
    flat_end: str = "16:00"
    sl_pct: float = 0.075
    min_gap_pct: float = 0.0225
    max_gap_pts: float = 100.0

@dataclass(frozen=True)
class StrategyConfig:
    instrument: Instrument
    sessions: tuple[SessionConfig, ...]
    risk_per_trade: float = 5000.0
    reward_risk: float = 2.5
    tp1_ratio: float = 0.5
    atr_length: int = 14

    def with_overrides(self, **kwargs) -> "StrategyConfig":
        """Create new config with overrides. Supports dot notation for nested fields."""
        updates = {}
        for key, value in kwargs.items():
            if "." in key:
                # Handle nested overrides like "sessions.0.sl_pct"
                parts = key.split(".")
                # Build nested override
                ...
            else:
                updates[key] = value
        return replace(self, **updates)

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)
```

**Key rules**:
- `frozen=True` — configs are immutable after creation
- `with_overrides()` — create variants without mutating the original
- `to_dict()` / `to_json()` — every config is serializable for storage and API transport

---

## Pattern 2: Signal Module (Pure, Vectorized, Deterministic)

Every signal function is a pure function operating on NumPy arrays with no side effects.

```python
# signals/fvg.py
import numpy as np

def detect_bullish_fvg(
    high: np.ndarray,
    low: np.ndarray,
) -> np.ndarray:
    """Detect bullish Fair Value Gaps using 3-candle pattern.

    Args:
        high: High prices array
        low: Low prices array

    Returns:
        Boolean mask where True = bullish FVG detected at this bar
    """
    n = len(high)
    mask = np.zeros(n, dtype=np.bool_)
    # Bar [2] = before, Bar [1] = impulse, Bar [0] = after (current)
    mask[2:] = (
        (high[:-2] < low[2:]) &
        (high[:-2] < high[1:-1]) &
        (low[:-2] < low[2:])
    )
    return mask


def detect_bearish_fvg(
    high: np.ndarray,
    low: np.ndarray,
) -> np.ndarray:
    """Detect bearish Fair Value Gaps using 3-candle pattern."""
    n = len(high)
    mask = np.zeros(n, dtype=np.bool_)
    mask[2:] = (
        (low[:-2] > high[2:]) &
        (low[:-2] > low[1:-1]) &
        (high[:-2] > high[2:])
    )
    return mask
```

**Key rules**:
- No global state — all inputs are parameters
- No side effects — no file I/O, no printing, no mutation
- Deterministic — same inputs always produce same outputs
- Vectorized — operate on full arrays, not bar-by-bar loops (unless Numba JIT)

---

## Pattern 3: Engine Component (Numba-Compatible, Config-Driven)

Simulation logic uses Numba JIT for performance while receiving all parameters explicitly.

```python
# engine/simulator.py
from numba import njit
import numpy as np

@njit
def _simulate_single_trade(
    open_prices: np.ndarray,
    high_prices: np.ndarray,
    low_prices: np.ndarray,
    close_prices: np.ndarray,
    entry_bar: int,
    entry_price: float,
    stop_price: float,
    tp1_price: float,
    tp2_price: float,
    is_long: bool,
    flat_bar: int,
    tp1_ratio: float,
) -> tuple:
    """Simulate a single trade bar-by-bar.

    All parameters are explicit — no global state, no config object
    (Numba can't handle Python objects).

    Returns:
        Tuple of (exit_bar, exit_price, exit_type, hit_tp1)
    """
    hit_tp1 = False
    current_stop = stop_price

    for bar in range(entry_bar + 1, len(close_prices)):
        if bar >= flat_bar:
            return (bar, close_prices[bar], EXIT_EOD, hit_tp1)

        h, l = high_prices[bar], low_prices[bar]

        # Check stop loss
        if is_long and l <= current_stop:
            return (bar, current_stop, EXIT_SL, hit_tp1)
        if not is_long and h >= current_stop:
            return (bar, current_stop, EXIT_SL, hit_tp1)

        # Check TP1
        if not hit_tp1:
            if is_long and h >= tp1_price:
                hit_tp1 = True
                current_stop = entry_price
            elif not is_long and l <= tp1_price:
                hit_tp1 = True
                current_stop = entry_price

        # Check TP2
        if is_long and h >= tp2_price:
            return (bar, tp2_price, EXIT_TP1_TP2 if hit_tp1 else EXIT_TP2_SINGLE, hit_tp1)
        if not is_long and l <= tp2_price:
            return (bar, tp2_price, EXIT_TP1_TP2 if hit_tp1 else EXIT_TP2_SINGLE, hit_tp1)

    return (len(close_prices) - 1, close_prices[-1], EXIT_EOD, hit_tp1)
```

**Key rules**:
- All parameters are explicit primitives (Numba requirement)
- No Python objects — use tuples, arrays, and scalars
- Return structured tuples, not dicts
- Exit type constants defined at module level as integers

---

## Pattern 4: API Endpoint (Validated Request, Structured Response)

Every FastAPI endpoint validates input, runs the backtest pipeline, and returns a structured response.

```python
# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

class BacktestRequest(BaseModel):
    symbol: str = "NQ"
    sessions: list[str] = ["NY"]
    risk_per_trade: float = Field(default=5000.0, gt=0)
    reward_risk: float = Field(default=2.5, gt=0)
    tp1_ratio: float = Field(default=0.5, ge=0, le=1)
    atr_length: int = Field(default=14, gt=0)
    # Session-level overrides
    sl_pct: Optional[float] = None
    min_gap_pct: Optional[float] = None
    max_gap_pts: Optional[float] = None

class BacktestResponse(BaseModel):
    success: bool
    result: Optional[dict] = None
    error: Optional[dict] = None

@app.post("/api/backtest", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest):
    try:
        # 1. Build config from request
        config = build_config_from_request(request)

        # 2. Load data
        df = load_data(config.instrument.symbol)

        # 3. Run pipeline
        trades = simulate(df, config)
        metrics = compute_metrics(trades, config)
        result = export_result(trades, metrics, config)

        # 4. Save for history
        save_result(result)

        return BacktestResponse(success=True, result=result)

    except BacktestError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": e.code, "reason": e.reason, "fix": e.fix},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "reason": str(e),
                "fix": "Check server logs for details",
            },
        )
```

**Key rules**:
- Pydantic models for request validation with `Field` constraints
- Structured response with `success` flag and optional `result`/`error`
- Errors are always structured `{code, reason, fix}`, never raw tracebacks
- Same endpoint serves dashboard, CLI, and future agents

---

## Pattern 5: Structured Error Response

Every error includes a machine-readable code, human-readable reason, and actionable fix.

```python
# errors.py
from fastapi import HTTPException

class BacktestError(Exception):
    """Structured error for backtest operations."""
    def __init__(self, code: str, reason: str, fix: str):
        self.code = code
        self.reason = reason
        self.fix = fix
        super().__init__(reason)

    def to_dict(self) -> dict:
        return {"code": self.code, "reason": self.reason, "fix": self.fix}

    def to_http(self, status: int = 422) -> HTTPException:
        return HTTPException(status_code=status, detail=self.to_dict())

# Error catalog — every known error in one place
ERRORS = {
    "DATA_NOT_FOUND": lambda sym: BacktestError(
        "DATA_NOT_FOUND",
        f"No data file found for instrument '{sym}'",
        f"Download data: python scripts/download_data.py {sym}",
    ),
    "INVALID_SESSION": lambda name: BacktestError(
        "INVALID_SESSION",
        f"Unknown session '{name}'",
        "Valid sessions: NY, ASIA, LDN",
    ),
    "EMPTY_RESULT": lambda config: BacktestError(
        "EMPTY_RESULT",
        f"Backtest produced zero trades for {config.instrument.symbol}",
        "Widen entry window, lower min_gap_pct, or check session times match data timezone",
    ),
    "INVALID_PARAM_RANGE": lambda param, val, lo, hi: BacktestError(
        "INVALID_PARAM_RANGE",
        f"Parameter '{param}' value {val} outside valid range [{lo}, {hi}]",
        f"Set '{param}' between {lo} and {hi}",
    ),
    "INSTRUMENT_NOT_FOUND": lambda sym: BacktestError(
        "INSTRUMENT_NOT_FOUND",
        f"Instrument '{sym}' not in registry",
        f"Available instruments: {', '.join(INSTRUMENTS.keys())}",
    ),
}
```

**Key rules**:
- `code` is machine-readable (ALL_CAPS with underscores)
- `reason` explains what went wrong in plain English
- `fix` tells the caller exactly how to resolve it
- Never raise bare `Exception` with string-only messages from API code

---

## Pattern 6: Result Schema (Complete, Self-Describing)

Every backtest result bundles the config, trades, metrics, and equity curve into one portable record.

```python
# results/export.py
from datetime import datetime
from uuid import uuid4

def export_result(
    trades: list[TradeResult],
    metrics: dict,
    config: StrategyConfig,
) -> dict:
    """Build a complete, self-describing backtest result."""
    return {
        "id": f"bt_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:6]}",
        "timestamp": datetime.now().isoformat(),
        "config": config.to_dict(),
        "metrics": metrics,
        "trades": [trade_to_dict(t) for t in trades],
        "equity_curve": build_equity_curve(trades),
        "meta": {
            "engine_version": "2.0",
            "data_range": {
                "start": trades[0].entry_date if trades else None,
                "end": trades[-1].exit_date if trades else None,
            },
            "total_bars_processed": None,  # populated by engine
        },
    }
```

**Key rules**:
- Every result has a unique `id` and `timestamp`
- `config` is the complete config used — not a summary, not a diff
- `meta` includes engine version and data range for reproducibility
- The result file alone is sufficient to understand the backtest

---

## Pattern 7: Composable Pipeline

The backtest pipeline is composed of independent stages. An optimizer calls the same stages with different configs.

```python
# Pipeline composition — each stage is independent
def run_backtest(config: StrategyConfig) -> dict:
    """Full backtest pipeline composed from independent stages."""
    # Stage 1: Load data
    df = load_data(config.instrument.symbol)

    # Stage 2: Compute signals (all independent, can parallelize)
    orb_high, orb_low = compute_orb(df, config.sessions)
    bull_fvg, bear_fvg = detect_fvg(df)
    session_masks = compute_session_masks(df, config.sessions)
    daily_atr = compute_daily_atr(df, config.atr_length)

    # Stage 3: Simulate trades
    trades = simulate_trades(
        df, orb_high, orb_low, bull_fvg, bear_fvg,
        session_masks, daily_atr, config
    )

    # Stage 4: Compute metrics
    metrics = compute_metrics(trades, config)

    # Stage 5: Export result
    return export_result(trades, metrics, config)


# Optimizer composes the same pipeline
def run_optimization(base_config: StrategyConfig, sweep: dict) -> list[dict]:
    """Grid sweep reuses run_backtest — no separate optimization engine."""
    configs = generate_grid(base_config, sweep)
    results = []
    for cfg in configs:
        result = run_backtest(cfg)
        results.append(result)
    return results
```

**Key rules**:
- `run_backtest()` is the atomic unit — optimizer, CLI, and API all call it
- Each stage can be tested independently
- Adding a new signal (e.g., volume filter) means adding one stage, not rewriting the engine
- Optimization is just `run_backtest()` in a loop with different configs

---

## Pattern 8: Dashboard API Integration

The React dashboard consumes FastAPI endpoints exclusively. No direct Python imports.

```typescript
// hooks/useBacktest.ts
interface BacktestConfig {
  symbol: string;
  sessions: string[];
  risk_per_trade: number;
  reward_risk: number;
  tp1_ratio: number;
  sl_pct?: number;
  min_gap_pct?: number;
  max_gap_pts?: number;
}

interface BacktestResult {
  id: string;
  timestamp: string;
  config: BacktestConfig;
  metrics: MetricsData;
  trades: Trade[];
  equity_curve: EquityCurvePoint[];
}

export function useBacktest() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<StructuredError | null>(null);

  const run = async (config: BacktestConfig) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) {
        const err = await res.json();
        // Structured error from API: { code, reason, fix }
        setError(err.detail);
        return;
      }
      const data = await res.json();
      setResult(data.result);
    } finally {
      setLoading(false);
    }
  };

  return { run, loading, result, error };
}
```

**Key rules**:
- TypeScript interfaces mirror the Python result schema
- Errors are displayed using the structured `{code, reason, fix}` format
- The hook is the boundary — components never call `fetch` directly
- Same API could be consumed by a CLI tool, a Jupyter notebook, or an agent
