"""FastAPI server for the ORB+FVG backtester."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd
from fastapi import FastAPI, Query, Request
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
from .data.loader import load_5m_data, load_1m_for_5m
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
    testing_plan_item_not_found,
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
from .results.metrics import compute_metrics, recompute_summary
from .optimize.grid import generate_param_grid, linspace_range
from .optimize.parallel import run_sweep
from .experiments import (
    log_sweep_runs,
    query_runs,
    compare_runs as compare_experiment_runs,
    list_backtest_history,
    toggle_star,
    list_starred,
    toggle_hidden,
    rename_backtest as rename_backtest_db,
    get_instrument_coverage,
    get_param_coverage,
    list_testing_plan,
    create_testing_plan_item,
    update_testing_plan_item,
    delete_testing_plan_item,
    reorder_testing_plan,
)

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

    ny_stop_atr_pct: Optional[float] = None
    ny_min_gap_atr_pct: Optional[float] = None
    ny_stop_orb_pct: Optional[float] = None
    ny_min_gap_orb_pct: Optional[float] = None
    asia_stop_atr_pct: Optional[float] = None
    asia_min_gap_atr_pct: Optional[float] = None
    asia_stop_orb_pct: Optional[float] = None
    asia_min_gap_orb_pct: Optional[float] = None
    ldn_stop_atr_pct: Optional[float] = None
    ldn_min_gap_atr_pct: Optional[float] = None
    ldn_stop_orb_pct: Optional[float] = None
    ldn_min_gap_orb_pct: Optional[float] = None


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
            "stop_orb_pct": getattr(sess, "stop_orb_pct", 0.0),
            "min_gap_orb_pct": getattr(sess, "min_gap_orb_pct", 0.0),
        }
        for sess in SESSION_MAP.values()
    ])


# ── Candle data endpoint ────────────────────────────────────────────


@app.get("/api/candles")
def get_candles(
    instrument: str = Query(...),
    date: str = Query(..., description="Trade date YYYY-MM-DD"),
    session: str = Query(..., description="Session name: NY, Asia, LDN"),
):
    """Return OHLCV bars for a single session-day (1-min if available, else 5-min).

    Used by the TradeChartModal to render a candlestick chart for a specific trade.
    Includes 30 min padding before ORB start and 15 min after flat end.
    """
    try:
        inst = get_instrument(instrument)
    except KeyError:
        raise unknown_instrument(instrument)

    if session not in SESSION_MAP:
        raise unknown_session(session)

    sess = SESSION_MAP[session]

    # Parse the trade date
    try:
        trade_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise data_not_found(f"Invalid date format: {date}. Use YYYY-MM-DD.")

    # Compute time window with padding
    orb_h, orb_m = (int(x) for x in sess.orb_start.split(":"))
    flat_h, flat_m = (int(x) for x in sess.flat_end.split(":"))

    orb_start_min = orb_h * 60 + orb_m
    flat_end_min = flat_h * 60 + flat_m
    crosses_midnight = orb_start_min > flat_end_min

    # Build start/end timestamps with padding
    padding_before = timedelta(minutes=30)
    padding_after = timedelta(minutes=15)

    window_start_time = datetime.combine(trade_date, datetime.min.time().replace(hour=orb_h, minute=orb_m)) - padding_before
    if crosses_midnight:
        window_end_time = datetime.combine(trade_date + timedelta(days=1), datetime.min.time().replace(hour=flat_h, minute=flat_m)) + padding_after
    else:
        window_end_time = datetime.combine(trade_date, datetime.min.time().replace(hour=flat_h, minute=flat_m)) + padding_after

    # Load data with a date range that covers the window.
    # Prefer 1-minute data for higher-resolution charts; fall back to 5-min
    # if the 1m file doesn't exist or the data is too sparse.
    # Forward-filled bars (volume=0) are excluded from chart display since
    # they render as invisible flat lines; they exist only for the backtest
    # engine's stop/TP detection.
    load_start = (window_start_time - timedelta(days=1)).strftime("%Y-%m-%d")
    load_end = (window_end_time + timedelta(days=1)).strftime("%Y-%m-%d")

    MIN_REAL_BARS = 50  # minimum traded bars to use 1m data

    def _load_and_window(loader, *args):
        df = loader(*args)
        tz = df.index.tz
        if tz is not None:
            ws = pd.Timestamp(window_start_time, tz=tz)
            we = pd.Timestamp(window_end_time, tz=tz)
        else:
            ws = pd.Timestamp(window_start_time)
            we = pd.Timestamp(window_end_time)
        windowed = df.loc[(df.index >= ws) & (df.index <= we)]
        # Strip forward-filled bars (volume=0) for chart display
        if "volume" in windowed.columns:
            windowed = windowed[windowed["volume"] > 0]
        return windowed

    bars = pd.DataFrame()
    try:
        bars = _load_and_window(load_1m_for_5m, inst.data_file, load_start, load_end)
    except FileNotFoundError:
        pass

    # Fall back to 5-min if 1m data is missing or too sparse
    if len(bars) < MIN_REAL_BARS:
        try:
            bars_5m = _load_and_window(load_5m_data, inst.data_file, load_start, load_end)
            # Use 5m if it has more real bars than the 1m data
            if len(bars_5m) >= len(bars):
                bars = bars_5m
        except FileNotFoundError as e:
            if bars.empty:
                raise data_not_found(str(e))

    if bars.empty:
        return []

    # Return as list of {time, open, high, low, close}
    result = []
    for ts, row in bars.iterrows():
        result.append({
            "time": ts.isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })

    return result


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
        "rr", "tp1_ratio", "risk_usd", "atr_length",
        "name", "notes",
        "ny_stop_atr_pct", "ny_min_gap_atr_pct", "ny_stop_orb_pct", "ny_min_gap_orb_pct",
        "asia_stop_atr_pct", "asia_min_gap_atr_pct", "asia_stop_orb_pct", "asia_min_gap_orb_pct",
        "ldn_stop_atr_pct", "ldn_min_gap_atr_pct", "ldn_stop_orb_pct", "ldn_min_gap_orb_pct",
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
def get_backtest(result_id: str, start: Optional[str] = None, end: Optional[str] = None):
    data = load_backtest_result(result_id)
    if data is None:
        raise backtest_not_found(result_id)
    data["id"] = result_id

    # Date-range filtering: recompute summary and equity curve for the window
    if (start or end) and "trades" in data:
        trades = data["trades"]
        if start:
            trades = [t for t in trades if t["date"] >= start]
        if end:
            trades = [t for t in trades if t["date"] <= end]

        data["trades"] = trades
        data["summary"] = recompute_summary(trades)

        # Rebuild equity curve from filtered filled trades
        filled = [t for t in trades if t["exit_type"] != "no_fill"]
        cumulative = 0.0
        curve = []
        for t in filled:
            cumulative += t["pnl_usd"]
            curve.append({
                "date": t["date"],
                "pnl_cumulative": round(cumulative, 2),
                "pnl_per_trade": round(t["pnl_usd"], 2),
            })
        data["equity_curve"] = curve

    return ok(data)


@app.delete("/api/backtests/{result_id}")
def delete_backtest(result_id: str):
    if not delete_backtest_result(result_id):
        raise backtest_not_found(result_id)
    return ok({"deleted": result_id})


@app.post("/api/backtests/{result_id}/star")
def star_backtest(result_id: str):
    new_state = toggle_star(result_id)
    if new_state is None:
        raise backtest_not_found(result_id)
    return ok({"starred": new_state})


@app.post("/api/backtests/{result_id}/hide")
def hide_backtest(result_id: str):
    new_state = toggle_hidden(result_id)
    if new_state is None:
        raise backtest_not_found(result_id)
    return ok({"hidden": new_state})


@app.patch("/api/backtests/{result_id}/name")
def rename_backtest_endpoint(result_id: str, body: dict):
    new_name = body.get("name", "").strip()
    if not new_name:
        raise BacktestError("Name cannot be empty")
    result = rename_backtest_db(result_id, new_name)
    if result is None:
        raise backtest_not_found(result_id)
    return ok({"name": result})


@app.get("/api/starred")
def get_starred():
    return ok(list_starred())


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


# ── Coverage endpoints ───────────────────────────────────────────────


@app.get("/api/coverage")
def get_coverage():
    return ok(get_instrument_coverage())


@app.get("/api/coverage/{instrument}/params")
def get_coverage_params(instrument: str):
    return ok(get_param_coverage(instrument))


# ── Testing plan endpoints ───────────────────────────────────────────


class TestingPlanCreateRequest(BaseModel):
    instrument: str
    title: str
    notes: Optional[str] = None


class TestingPlanUpdateRequest(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class TestingPlanReorderRequest(BaseModel):
    instrument: str
    item_ids: list[int]


@app.get("/api/testing-plan")
def get_testing_plan(instrument: Optional[str] = None):
    return ok(list_testing_plan(instrument))


@app.post("/api/testing-plan")
def create_plan_item(req: TestingPlanCreateRequest):
    item = create_testing_plan_item(req.instrument, req.title, req.notes)
    return ok(item)


@app.put("/api/testing-plan/{item_id}")
def update_plan_item(item_id: int, req: TestingPlanUpdateRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = update_testing_plan_item(item_id, **updates)
    if result is None:
        raise testing_plan_item_not_found(item_id)
    return ok(result)


@app.delete("/api/testing-plan/{item_id}")
def delete_plan_item(item_id: int):
    if not delete_testing_plan_item(item_id):
        raise testing_plan_item_not_found(item_id)
    return ok({"deleted": item_id})


@app.post("/api/testing-plan/reorder")
def reorder_plan(req: TestingPlanReorderRequest):
    reorder_testing_plan(req.instrument, req.item_ids)
    return ok({"reordered": True})
