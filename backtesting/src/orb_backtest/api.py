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
    ib_config,
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
    vwap_results_to_dict,
    vwap_grid_results_to_dict,
    gapfill_results_to_dict,
    gapfill_grid_results_to_dict,
)
from .vwap_config import (
    VWAPStrategyConfig,
    VWAPSessionConfig,
    default_vwap_config,
    with_vwap_overrides,
    NY_VWAP_SESSION,
    ASIA_VWAP_SESSION,
    LDN_VWAP_SESSION,
)
from .engine.vwap_simulator import run_vwap_backtest
from .gapfill_config import (
    GapFillStrategyConfig,
    GapFillSessionConfig,
    default_gapfill_config,
    with_gapfill_overrides,
    NY_GAPFILL_SESSION,
)
from .engine.gapfill_simulator import run_gapfill_backtest
from .optimize.parallel_gapfill import run_gapfill_sweep
from .optimize.walkforward_gapfill import _generate_gapfill_param_grid
from .engine.news_straddle import (
    NewsStraddleConfig,
    run_news_straddle,
    run_news_straddle_sweep,
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
    log_news_straddle_run,
    list_news_straddle_history,
    get_news_straddle_run,
    delete_news_straddle_run,
    list_risk_engine_layouts,
    save_risk_engine_layout,
    delete_risk_engine_layout,
    log_regime_report,
    list_regime_reports,
    get_regime_report,
    delete_regime_report,
    list_saved_configs,
    get_saved_config,
    create_saved_config,
    update_saved_config,
    delete_saved_config,
)
from .analysis.regime_reports import build_regime_report, RegimeReportConfig

app = FastAPI(title="ORB+FVG Backtester API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_MAP = {"NY": NY_SESSION, "Asia": ASIA_SESSION, "LDN": LDN_SESSION}
VWAP_SESSION_MAP = {"NY": NY_VWAP_SESSION, "Asia": ASIA_VWAP_SESSION, "LDN": LDN_VWAP_SESSION}
GAPFILL_SESSION_MAP = {"NY": NY_GAPFILL_SESSION}


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
    strategy: Optional[str] = None
    direction_filter: Optional[str] = None
    use_bar_magnifier: Optional[bool] = None
    reverse_direction: Optional[bool] = None

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
            "rth_start": sess.rth_start,
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
    timeframe: str = Query("1m", description="Bar timeframe: 1m or 5m"),
    sweep_time: str = Query("", description="Optional ISO timestamp of LSI sweep for dynamic chart padding"),
):
    """Return OHLCV bars for a single session-day (1-min if available, else 5-min).

    Used by the TradeChartModal to render a candlestick chart for a specific trade.
    Includes 30 min padding before ORB start and 15 min after flat end.
    When timeframe="5m", skips 1m data entirely. When timeframe="1m" (default),
    tries 1m first and falls back to 5m if missing or too sparse.
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

    # Compute time window with padding (rth_start for LSI, orb_start for ORB strategies)
    rth_start = sess.rth_start or sess.orb_start
    orb_h, orb_m = (int(x) for x in rth_start.split(":"))
    flat_h, flat_m = (int(x) for x in sess.flat_end.split(":"))

    orb_start_min = orb_h * 60 + orb_m
    flat_end_min = flat_h * 60 + flat_m
    crosses_midnight = orb_start_min > flat_end_min

    # Build start/end timestamps with padding.
    # Default 120 min pre-padding. When lsi_sweep_time is available, extend
    # dynamically so the sweep bar is always visible in the chart.
    padding_before = timedelta(minutes=120)
    padding_after = timedelta(minutes=15)

    window_start_time = datetime.combine(trade_date, datetime.min.time().replace(hour=orb_h, minute=orb_m)) - padding_before

    # Dynamic padding: if the sweep occurred before our window, extend back
    if sweep_time:
        try:
            sweep_dt = datetime.fromisoformat(sweep_time)
            # Strip timezone info for comparison with naive window_start_time
            if sweep_dt.tzinfo is not None:
                sweep_dt = sweep_dt.replace(tzinfo=None)
            # Extend window to include sweep bar + 30 min of context before it
            if sweep_dt < window_start_time:
                window_start_time = sweep_dt - timedelta(minutes=30)
        except (ValueError, TypeError):
            pass  # ignore malformed sweep times
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
    if timeframe == "5m":
        # 5m explicitly requested — skip 1m entirely
        try:
            bars = _load_and_window(load_5m_data, inst.data_file, load_start, load_end)
        except FileNotFoundError as e:
            raise data_not_found(str(e))
    else:
        # 1m preferred, fall back to 5m if missing or too sparse
        try:
            bars = _load_and_window(load_1m_for_5m, inst.data_file, load_start, load_end)
        except FileNotFoundError:
            pass

        if len(bars) < MIN_REAL_BARS:
            try:
                bars_5m = _load_and_window(load_5m_data, inst.data_file, load_start, load_end)
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

    if req.strategy == "ib":
        config = ib_config(instrument)
        # IB config has its own session (IB_NY_SESSION with 09:30-10:30 window);
        # don't overwrite with standard SESSION_MAP sessions.
    else:
        config = default_config(instrument)
        config = with_overrides(config, sessions=tuple(sessions))

    # Apply param overrides
    overrides = {}
    for field in (
        "rr", "tp1_ratio", "risk_usd", "atr_length",
        "strategy", "direction_filter", "use_bar_magnifier", "reverse_direction",
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


# ── Saved configs endpoints ──────────────────────────────────────────


class SavedConfigRequest(BaseModel):
    name: str
    notes: Optional[str] = None
    instrument: str
    sessions: list[str]
    strategy: str
    config: dict[str, Any]


@app.get("/api/configs")
def list_configs(limit: int = Query(200)):
    return ok(list_saved_configs(limit=limit))


@app.get("/api/configs/{config_id}")
def get_config(config_id: int):
    result = get_saved_config(config_id)
    if result is None:
        raise BacktestError("CONFIG_NOT_FOUND", f"Config '{config_id}' not found", "Check the config id", status_code=404)
    return ok(result)


@app.post("/api/configs")
def create_config(req: SavedConfigRequest):
    result = create_saved_config(
        name=req.name.strip(),
        notes=req.notes,
        instrument=req.instrument,
        sessions=req.sessions,
        strategy=req.strategy,
        config=req.config,
    )
    return ok(result)


@app.put("/api/configs/{config_id}")
def update_config(config_id: int, req: SavedConfigRequest):
    result = update_saved_config(
        config_id,
        name=req.name.strip(),
        notes=req.notes,
        instrument=req.instrument,
        sessions=req.sessions,
        strategy=req.strategy,
        config=req.config,
    )
    if result is None:
        raise BacktestError("CONFIG_NOT_FOUND", f"Config '{config_id}' not found", "Check the config id", status_code=404)
    return ok(result)


@app.delete("/api/configs/{config_id}")
def delete_config(config_id: int):
    if not delete_saved_config(config_id):
        raise BacktestError("CONFIG_NOT_FOUND", f"Config '{config_id}' not found", "Check the config id", status_code=404)
    return ok({"deleted": True})


# ── VWAP Reversion endpoints ────────────────────────────────────────


class VWAPBacktestRequest(BaseModel):
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
    tp2_mode: Optional[str] = None
    direction_filter: Optional[str] = None

    ny_deviation_atr_pct: Optional[float] = None
    ny_deviation_std: Optional[float] = None
    ny_deviation_mode: Optional[str] = None
    ny_rejection_mode: Optional[str] = None
    ny_stop_atr_pct: Optional[float] = None
    asia_deviation_atr_pct: Optional[float] = None
    asia_deviation_std: Optional[float] = None
    asia_deviation_mode: Optional[str] = None
    asia_rejection_mode: Optional[str] = None
    asia_stop_atr_pct: Optional[float] = None
    ldn_deviation_atr_pct: Optional[float] = None
    ldn_deviation_std: Optional[float] = None
    ldn_deviation_mode: Optional[str] = None
    ldn_rejection_mode: Optional[str] = None
    ldn_stop_atr_pct: Optional[float] = None


@app.post("/api/vwap/backtest")
def run_vwap_backtest_endpoint(req: VWAPBacktestRequest):
    try:
        instrument = get_instrument(req.instrument)
    except KeyError:
        raise unknown_instrument(req.instrument)

    sessions = []
    for s in req.sessions:
        if s not in VWAP_SESSION_MAP:
            raise unknown_session(s)
        sessions.append(VWAP_SESSION_MAP[s])

    config = default_vwap_config(instrument)
    config = with_vwap_overrides(config, sessions=tuple(sessions))

    # Apply param overrides
    overrides = {}
    for field_name in (
        "rr", "tp1_ratio", "risk_usd", "atr_length", "tp2_mode",
        "direction_filter", "name", "notes",
        "ny_deviation_atr_pct", "ny_deviation_std", "ny_deviation_mode",
        "ny_rejection_mode", "ny_stop_atr_pct",
        "asia_deviation_atr_pct", "asia_deviation_std", "asia_deviation_mode",
        "asia_rejection_mode", "asia_stop_atr_pct",
        "ldn_deviation_atr_pct", "ldn_deviation_std", "ldn_deviation_mode",
        "ldn_rejection_mode", "ldn_stop_atr_pct",
    ):
        val = getattr(req, field_name, None)
        if val is not None:
            overrides[field_name] = val

    if overrides:
        config = with_vwap_overrides(config, **overrides)

    # Load data
    try:
        df = load_5m_data(instrument.data_file, req.start, req.end)
    except FileNotFoundError as e:
        raise data_not_found(str(e))

    df_1m = None
    try:
        df_1m = load_1m_for_5m(instrument.data_file, req.start, req.end)
    except FileNotFoundError:
        pass

    trades = run_vwap_backtest(df, config, start_date=req.start, end_date=req.end, df_1m=df_1m)
    result = vwap_results_to_dict(trades, config, include_equity_curve=True)
    result_id = save_backtest_result(result)
    result["id"] = result_id

    return ok(result)


# ── Gap Fill endpoints ────────────────────────────────────────────


class GapFillBacktestRequest(BaseModel):
    instrument: str = "ES"
    sessions: list[str] = ["NY"]
    start: Optional[str] = None
    end: Optional[str] = None
    name: Optional[str] = None
    notes: Optional[str] = None
    stop_multiplier: Optional[float] = None
    tp1_ratio: Optional[float] = None
    risk_usd: Optional[float] = None
    atr_length: Optional[int] = None
    min_gap_atr_pct: Optional[float] = None
    max_gap_atr_pct: Optional[float] = None
    min_gap_points: Optional[float] = None
    max_gap_staleness_days: Optional[int] = None
    direction_filter: Optional[str] = None


@app.post("/api/gapfill/backtest")
def run_gapfill_backtest_endpoint(req: GapFillBacktestRequest):
    try:
        instrument = get_instrument(req.instrument)
    except KeyError:
        raise unknown_instrument(req.instrument)

    sessions = []
    for s in req.sessions:
        if s not in GAPFILL_SESSION_MAP:
            raise unknown_session(s)
        sessions.append(GAPFILL_SESSION_MAP[s])

    config = default_gapfill_config(instrument)
    config = with_gapfill_overrides(config, sessions=tuple(sessions))

    # Apply param overrides
    overrides = {}
    for field_name in (
        "stop_multiplier", "tp1_ratio", "risk_usd", "atr_length",
        "min_gap_atr_pct", "max_gap_atr_pct", "min_gap_points",
        "max_gap_staleness_days", "direction_filter", "name", "notes",
    ):
        val = getattr(req, field_name, None)
        if val is not None:
            overrides[field_name] = val

    if overrides:
        config = with_gapfill_overrides(config, **overrides)

    # Load data
    try:
        df = load_5m_data(instrument.data_file, req.start, req.end)
    except FileNotFoundError as e:
        raise data_not_found(str(e))

    df_1m = None
    try:
        df_1m = load_1m_for_5m(instrument.data_file, req.start, req.end)
    except FileNotFoundError:
        pass

    trades = run_gapfill_backtest(df, config, start_date=req.start, end_date=req.end, df_1m=df_1m)
    result = gapfill_results_to_dict(trades, config, include_equity_curve=True)
    result_id = save_backtest_result(result)
    result["id"] = result_id

    return ok(result)


class GapFillOptimizeRequest(BaseModel):
    instrument: str = "ES"
    sessions: list[str] = ["NY"]
    start: Optional[str] = None
    end: Optional[str] = None
    sweeps: dict[str, str] = {}
    metric: str = "sharpe_ratio"


@app.post("/api/gapfill/optimize")
def run_gapfill_optimize_endpoint(req: GapFillOptimizeRequest):
    if not req.sweeps:
        raise no_sweep_params()

    try:
        instrument = get_instrument(req.instrument)
    except KeyError:
        raise unknown_instrument(req.instrument)

    sessions = []
    for s in req.sessions:
        if s not in GAPFILL_SESSION_MAP:
            raise unknown_session(s)
        sessions.append(GAPFILL_SESSION_MAP[s])

    config = default_gapfill_config(instrument)
    config = with_gapfill_overrides(config, sessions=tuple(sessions))

    # Parse sweep specs
    param_ranges: dict[str, list[float]] = {}
    for param_name, spec in req.sweeps.items():
        try:
            param_ranges[param_name] = _parse_sweep_spec(spec)
        except (ValueError, IndexError):
            raise invalid_sweep_spec(param_name, spec)

    # Generate grid
    configs = _generate_gapfill_param_grid(config, param_ranges)

    # Load data
    try:
        df = load_5m_data(instrument.data_file, start=req.start, end=req.end)
    except FileNotFoundError as e:
        raise data_not_found(str(e))

    df_1m = None
    try:
        df_1m = load_1m_for_5m(instrument.data_file, req.start, req.end)
    except FileNotFoundError:
        pass

    # Run sweep
    results = run_gapfill_sweep(df, configs, start_date=req.start, end_date=req.end, df_1m=df_1m)

    result = gapfill_grid_results_to_dict(results, swept_params=param_ranges)
    result_id = save_optimization_result(result)
    result["id"] = result_id

    return ok(result)


# ── News Straddle endpoints ─────────────────────────────────────────


class NewsStraddleRequest(BaseModel):
    buffer_points: float = 5.0
    target_points: float = 25.0
    event_types: list[str] = ["NFP", "CPI"]
    observation_window_seconds: int = 120
    instrument: str = "NQ"
    start: Optional[str] = None
    end: Optional[str] = None
    stop_loss_points: Optional[float] = None


class NewsStraddleSweepRequest(BaseModel):
    buffer_range: str = "1:20:1"
    target_range: str = "10:50:5"
    event_types: list[str] = ["NFP", "CPI"]
    observation_window_seconds: int = 120
    instrument: str = "NQ"
    start: Optional[str] = None
    end: Optional[str] = None
    stop_loss_points: Optional[float] = None


def _parse_range_spec(spec: str) -> list[float]:
    """Parse 'start:stop:step' into a list of floats."""
    parts = spec.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid range spec: {spec}")
    start, stop, step = float(parts[0]), float(parts[1]), float(parts[2])
    values = []
    v = start
    while v <= stop + 1e-9:
        values.append(round(v, 4))
        v += step
    return values


@app.get("/api/news-candles")
def get_news_candles(
    instrument: str = Query("NQ"),
    date: str = Query(..., description="Event date YYYY-MM-DD"),
    seconds_before: int = Query(1, description="Seconds before 08:30 release to include"),
    seconds_after: int = Query(300, description="Seconds after 08:30 release to include"),
):
    """Return 1s OHLCV bars around a news event.

    The window is [08:30 - seconds_before, 08:30 + seconds_after] ET.
    Used by the NewsTradeChartModal to render a candlestick chart for a
    specific news straddle event.
    """
    from .engine.news_straddle import _load_1s_data

    try:
        trade_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise data_not_found(f"Invalid date format: {date}. Use YYYY-MM-DD.")

    # Load 1s data for this date
    load_start = (trade_date - timedelta(days=1)).strftime("%Y-%m-%d")
    load_end = (trade_date + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        df = _load_1s_data(instrument, load_start, load_end)
    except FileNotFoundError as e:
        raise data_not_found(str(e))

    # Window: centered on 08:30:00 release time
    release = pd.Timestamp(datetime.combine(
        trade_date, datetime.min.time().replace(hour=8, minute=30)
    ))
    ws = release - pd.Timedelta(seconds=seconds_before)
    we = release + pd.Timedelta(seconds=seconds_after)

    tz = df.index.tz
    if tz is not None:
        ws = ws.tz_localize(tz)
        we = we.tz_localize(tz)

    windowed = df.loc[(df.index >= ws) & (df.index <= we)]

    if windowed.empty:
        return []

    result = []
    for ts, row in windowed.iterrows():
        result.append({
            "time": ts.isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })

    return result


@app.post("/api/news-straddle")
def run_news_straddle_endpoint(req: NewsStraddleRequest):
    """Run a single news straddle backtest with fixed params."""
    import hashlib as _hl

    config = NewsStraddleConfig(
        buffer_points=req.buffer_points,
        target_points=req.target_points,
        event_types=tuple(req.event_types),
        observation_window_seconds=req.observation_window_seconds,
        instrument=req.instrument,
        stop_loss_points=req.stop_loss_points,
    )
    result = run_news_straddle(config, start=req.start, end=req.end)

    # Auto-save to history
    result["config"]["date_start"] = req.start
    result["config"]["date_end"] = req.end
    fingerprint = f"{req.buffer_points}_{req.target_points}_{req.observation_window_seconds}_{req.event_types}_{req.start}_{req.end}_{req.stop_loss_points}"
    result_id = _hl.md5(fingerprint.encode()).hexdigest()[:12]
    try:
        log_news_straddle_run(result, result_id)
    except Exception:
        pass  # don't block the response

    return ok(result)


@app.post("/api/news-straddle/sweep")
def run_news_straddle_sweep_endpoint(req: NewsStraddleSweepRequest):
    """Run a buffer x target sweep for the news straddle strategy."""
    buffer_values = _parse_range_spec(req.buffer_range)
    target_values = _parse_range_spec(req.target_range)

    result = run_news_straddle_sweep(
        buffer_range=buffer_values,
        target_range=target_values,
        event_types=tuple(req.event_types),
        observation_window_seconds=req.observation_window_seconds,
        instrument=req.instrument,
        start=req.start,
        end=req.end,
        stop_loss_points=req.stop_loss_points,
    )
    return ok(result)


# ── News Straddle History ────────────────────────────────────────────

@app.get("/api/news-straddle/runs")
def list_news_straddle_runs_endpoint(limit: int = Query(100)):
    """List saved news straddle backtest runs."""
    return ok(list_news_straddle_history(limit))


@app.get("/api/news-straddle/runs/{result_id}")
def get_news_straddle_run_endpoint(result_id: str):
    """Load a full news straddle result."""
    result = get_news_straddle_run(result_id)
    if result is None:
        raise experiment_not_found(result_id)
    return ok(result)


@app.delete("/api/news-straddle/runs/{result_id}")
def delete_news_straddle_run_endpoint(result_id: str):
    """Delete a news straddle run."""
    if not delete_news_straddle_run(result_id):
        raise experiment_not_found(result_id)
    return ok({"deleted": True})


class NewsStraddleRunSaveRequest(BaseModel):
    result_dict: dict
    result_id: str


@app.post("/api/news-straddle/runs")
def save_news_straddle_run_endpoint(req: NewsStraddleRunSaveRequest):
    """Save a news straddle run (used by remote sync)."""
    rowid = log_news_straddle_run(req.result_dict, req.result_id)
    return ok({"rowid": rowid})


# ── Regime Reports ───────────────────────────────────────────────────


class RegimeReportRequest(BaseModel):
    backtest_result_id: str
    method: Optional[str] = "both"


@app.post("/api/regime-reports")
def create_regime_report(req: RegimeReportRequest):
    """Generate and save a regime report for a backtest result."""
    import hashlib as _hl
    import time as _time

    cfg = RegimeReportConfig(method=req.method or "both")
    report = build_regime_report(req.backtest_result_id, cfg)

    fingerprint = f"{req.backtest_result_id}_{cfg.method}_{int(_time.time())}"
    result_id = _hl.md5(fingerprint.encode()).hexdigest()[:12]
    log_regime_report(report, result_id)
    report["result_id"] = result_id
    return ok(report)


@app.get("/api/regime-reports")
def list_regime_reports_endpoint(limit: int = Query(100)):
    """List saved regime reports."""
    return ok(list_regime_reports(limit=limit))


@app.get("/api/regime-reports/{result_id}")
def get_regime_report_endpoint(result_id: str):
    """Load a full regime report."""
    result = get_regime_report(result_id)
    if result is None:
        raise experiment_not_found(result_id)
    return ok(result)


@app.delete("/api/regime-reports/{result_id}")
def delete_regime_report_endpoint(result_id: str):
    """Delete a regime report."""
    if not delete_regime_report(result_id):
        raise experiment_not_found(result_id)
    return ok({"deleted": True})


# ── Risk Engine Layouts ────────────────────────────────────────────


class RiskEngineLayoutRequest(BaseModel):
    name: str
    accountRisk: float
    strategies: list[dict]


@app.get("/api/risk-engine/layouts")
def get_risk_engine_layouts():
    """List all saved risk engine layouts."""
    return ok(list_risk_engine_layouts())


@app.post("/api/risk-engine/layouts")
def save_risk_engine_layout_endpoint(req: RiskEngineLayoutRequest):
    """Create or update a risk engine layout."""
    layout = save_risk_engine_layout(req.name, req.accountRisk, req.strategies)
    return ok(layout)


@app.delete("/api/risk-engine/layouts/{name}")
def delete_risk_engine_layout_endpoint(name: str):
    """Delete a risk engine layout by name."""
    if not delete_risk_engine_layout(name):
        raise BacktestError("LAYOUT_NOT_FOUND", f"Layout '{name}' not found", "Check the layout name", status_code=404)
    return ok({"deleted": name})
