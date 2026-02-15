"""FastAPI server for the ORB+FVG backtester."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .config import (
    default_config,
    with_overrides,
    NY_SESSION,
    ASIA_SESSION,
    LDN_SESSION,
)
from .data.instruments import get_instrument, list_instruments
from .data.loader import load_5m_data
from .engine.simulator import run_backtest, EXIT_NO_FILL
from .errors import (
    BacktestError,
    unknown_instrument,
    unknown_session,
    data_not_found,
    invalid_sweep_spec,
    no_sweep_params,
    backtest_not_found,
    optimization_not_found,
    experiment_not_found,
    invalid_experiment_ids,
)
from .results.export import (
    results_to_dict,
    grid_results_to_dict,
    save_backtest_result,
    load_backtest_result,
    delete_backtest_result,
    save_optimization_result,
    list_optimization_results,
    load_optimization_result,
    delete_optimization_result,
)
from .results.metrics import compute_metrics
from .optimize.grid import generate_param_grid, linspace_range
from .optimize.parallel import run_sweep
from .experiments import log_sweep_runs, query_runs, compare_runs as compare_experiment_runs, list_backtest_history

app = FastAPI(title="ORB+FVG Backtester API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_MAP = {"NY": NY_SESSION, "Asia": ASIA_SESSION, "LDN": LDN_SESSION}


# ── Response helpers ─────────────────────────────────────────────────


def ok(result: Any) -> dict:
    """Wrap a successful result in the standard envelope."""
    return {"success": True, "result": result}


@app.exception_handler(BacktestError)
async def backtest_error_handler(request: Request, exc: BacktestError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.to_dict()},
    )


# ── Request models ───────────────────────────────────────────────────


class BacktestRequest(BaseModel):
    instrument: str = "NQ"
    sessions: list[str] = ["NY"]
    start: Optional[str] = None
    end: Optional[str] = None
    name: Optional[str] = None
    notes: Optional[str] = None
    rr: Optional[float] = None
    tp1_ratio: Optional[float] = None
    risk_usd: Optional[float] = None
    atr_length: Optional[int] = None
    be_offset_ticks: Optional[int] = None
    ny_stop_atr_pct: Optional[float] = None
    ny_min_gap_atr_pct: Optional[float] = None
    ny_max_gap_points: Optional[float] = None
    asia_stop_atr_pct: Optional[float] = None
    asia_min_gap_atr_pct: Optional[float] = None
    asia_max_gap_points: Optional[float] = None
    ldn_stop_atr_pct: Optional[float] = None
    ldn_min_gap_atr_pct: Optional[float] = None
    ldn_max_gap_points: Optional[float] = None


# ── Discovery endpoints ─────────────────────────────────────────────


@app.get("/api/instruments")
def get_instruments():
    instruments = list_instruments()
    return ok([
        {
            "symbol": inst.symbol,
            "point_value": inst.point_value,
            "min_tick": inst.min_tick,
            "commission": inst.commission,
            "data_file": inst.data_file,
            "exchange_tz": inst.exchange_tz,
        }
        for inst in instruments.values()
    ])


@app.get("/api/sessions")
def get_sessions():
    return ok([
        {
            "name": sess.name,
            "orb_start": sess.orb_start,
            "orb_end": sess.orb_end,
            "entry_start": sess.entry_start,
            "entry_end": sess.entry_end,
            "flat_start": sess.flat_start,
            "flat_end": sess.flat_end,
            "stop_atr_pct": sess.stop_atr_pct,
            "min_gap_atr_pct": sess.min_gap_atr_pct,
            "max_gap_points": sess.max_gap_points,
        }
        for sess in SESSION_MAP.values()
    ])


# ── Backtest endpoints ──────────────────────────────────────────────


@app.post("/api/backtest")
def run_backtest_endpoint(req: BacktestRequest):
    try:
        instrument = get_instrument(req.instrument)
    except KeyError:
        raise unknown_instrument(req.instrument)

    sessions = []
    for s in req.sessions:
        if s not in SESSION_MAP:
            raise unknown_session(s)
        sessions.append(SESSION_MAP[s])

    config = default_config(instrument)
    config = with_overrides(config, sessions=tuple(sessions))

    # Apply param overrides
    overrides = {}
    for field in (
        "rr", "tp1_ratio", "risk_usd", "atr_length", "be_offset_ticks",
        "name", "notes",
        "ny_stop_atr_pct", "ny_min_gap_atr_pct", "ny_max_gap_points",
        "asia_stop_atr_pct", "asia_min_gap_atr_pct", "asia_max_gap_points",
        "ldn_stop_atr_pct", "ldn_min_gap_atr_pct", "ldn_max_gap_points",
    ):
        val = getattr(req, field)
        if val is not None:
            overrides[field] = val

    if overrides:
        config = with_overrides(config, **overrides)

    # Load data
    try:
        df = load_5m_data(instrument.data_file, start=req.start, end=req.end)
    except FileNotFoundError as e:
        raise data_not_found(str(e))

    # Run backtest
    trades = run_backtest(df, config, start_date=req.start)

    # Build response with equity curve
    result = results_to_dict(
        trades, config,
        include_trades=True,
        include_equity_curve=True,
    )

    # Auto-save
    result_id = save_backtest_result(result)
    result["id"] = result_id

    return ok(result)


@app.get("/api/backtests")
def list_backtests():
    return ok(list_backtest_history())


@app.get("/api/backtests/{result_id}")
def get_backtest(result_id: str):
    data = load_backtest_result(result_id)
    if data is None:
        raise backtest_not_found(result_id)
    data["id"] = result_id
    return ok(data)


@app.delete("/api/backtests/{result_id}")
def delete_backtest(result_id: str):
    if not delete_backtest_result(result_id):
        raise backtest_not_found(result_id)
    return ok({"deleted": result_id})


# ── Optimization endpoints ──────────────────────────────────────────


class OptimizeRequest(BaseModel):
    instrument: str = "NQ"
    sessions: list[str] = ["NY"]
    start: Optional[str] = None
    end: Optional[str] = None
    sweeps: dict[str, str] = {}
    metric: str = "sharpe_ratio"


def _parse_sweep_spec(spec: str) -> list[float]:
    """Parse '5:25:5' or '1.0,2.0,3.0' into a list of floats."""
    if ":" in spec:
        parts = spec.split(":")
        start, stop, step = float(parts[0]), float(parts[1]), float(parts[2])
        return linspace_range(start, stop, step)
    return [float(v) for v in spec.split(",")]


@app.post("/api/optimize")
def run_optimize_endpoint(req: OptimizeRequest):
    if not req.sweeps:
        raise no_sweep_params()

    try:
        instrument = get_instrument(req.instrument)
    except KeyError:
        raise unknown_instrument(req.instrument)

    sessions = []
    for s in req.sessions:
        if s not in SESSION_MAP:
            raise unknown_session(s)
        sessions.append(SESSION_MAP[s])

    config = default_config(instrument)
    config = with_overrides(config, sessions=tuple(sessions))

    # Parse sweep specs
    param_ranges: dict[str, list[float]] = {}
    for param_name, spec in req.sweeps.items():
        try:
            param_ranges[param_name] = _parse_sweep_spec(spec)
        except (ValueError, IndexError):
            raise invalid_sweep_spec(param_name, spec)

    # Generate grid
    configs = generate_param_grid(config, param_ranges)

    # Load data
    try:
        df = load_5m_data(instrument.data_file, start=req.start, end=req.end)
    except FileNotFoundError as e:
        raise data_not_found(str(e))

    # Run sweep
    results = run_sweep(df, configs, start_date=req.start)

    # Build result dict
    result = grid_results_to_dict(results, swept_params=param_ranges)

    # Auto-save
    result_id = save_optimization_result(result)
    # Log individual sweep runs to experiment DB
    try:
        log_sweep_runs(results, result_id)
    except Exception:
        pass
    result["id"] = result_id

    return ok(result)


@app.get("/api/optimizations")
def list_optimizations():
    return ok(list_optimization_results())


@app.get("/api/optimizations/{result_id}")
def get_optimization(result_id: str):
    data = load_optimization_result(result_id)
    if data is None:
        raise optimization_not_found(result_id)
    data["id"] = result_id
    return ok(data)


@app.delete("/api/optimizations/{result_id}")
def delete_optimization(result_id: str):
    if not delete_optimization_result(result_id):
        raise optimization_not_found(result_id)
    return ok({"deleted": result_id})


# ── Experiment tracking endpoints ────────────────────────────────────


@app.get("/api/experiments")
def list_experiments(
    instrument: Optional[str] = None,
    sessions: Optional[str] = None,
    min_pf: Optional[float] = None,
    min_sharpe: Optional[float] = None,
    name: Optional[str] = None,
    run_type: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = 50,
):
    filters = {}
    if instrument:
        filters["instrument"] = instrument
    if sessions:
        filters["sessions"] = sessions
    if min_pf is not None:
        filters["min_profit_factor"] = min_pf
    if min_sharpe is not None:
        filters["min_sharpe"] = min_sharpe
    if name:
        filters["experiment_name"] = name
    if run_type:
        filters["run_type"] = run_type
    if after:
        filters["date_from"] = after
    if before:
        filters["date_to"] = before
    return ok(query_runs(limit=limit, **filters))


@app.get("/api/experiments/compare")
def compare_experiments(ids: str):
    try:
        run_ids = [int(x.strip()) for x in ids.split(",")]
    except ValueError:
        raise invalid_experiment_ids()
    return ok(compare_experiment_runs(run_ids))


@app.get("/api/experiments/{run_id}")
def get_experiment(run_id: int):
    rows = compare_experiment_runs([run_id])
    if not rows:
        raise experiment_not_found(run_id)
    return ok(rows[0])
