"""FastAPI router for the IFVG reversal backtester.

Mounted on the existing ORB server under /ifvg/ prefix.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from orb_backtest.data.instruments import get_instrument, list_instruments
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m

from .config import IFVGConfig, KillzoneConfig, ASIA_KZ, LONDON_KZ, default_config, with_overrides
from .engine.simulator import run_backtest
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
from .errors import (
    IFVGError,
    unknown_instrument,
    data_not_found,
    invalid_sweep_spec,
    no_sweep_params,
    backtest_not_found,
    optimization_not_found,
    experiment_not_found,
    invalid_experiment_ids,
    testing_plan_item_not_found,
)
from .experiments import (
    log_ifvg_sweep_runs,
    query_runs,
    compare_runs,
    list_backtest_history,
    toggle_star,
    toggle_hidden,
    list_starred,
    rename_backtest as rename_backtest_db,
    get_instrument_coverage,
    get_param_coverage,
    list_testing_plan,
    create_testing_plan_item,
    update_testing_plan_item,
    delete_testing_plan_item,
    reorder_testing_plan,
)

router = APIRouter()


# ── Response helpers ─────────────────────────────────────────────────


def ok(result) -> dict:
    """Wrap a successful result in the standard envelope."""
    return {"success": True, "result": result}


def register_error_handler(app):
    """Register IFVG error handler on the parent app. Called after mount."""
    @app.exception_handler(IFVGError)
    async def ifvg_error_handler(request: Request, exc: IFVGError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.to_dict()},
        )


# ── Request models ────────────────────────────────────────────────


class IFVGBacktestRequest(BaseModel):
    instrument: str = "NQ"
    start: Optional[str] = None
    end: Optional[str] = None
    name: Optional[str] = None
    notes: Optional[str] = None

    # Risk
    rr: Optional[float] = None
    tp1_ratio: Optional[float] = None
    risk_usd: Optional[float] = None
    min_qty: Optional[float] = None
    qty_step: Optional[float] = None
    be_offset_ticks: Optional[int] = None
    atr_length: Optional[int] = None

    # Session windows
    entry_start: Optional[str] = None
    entry_end: Optional[str] = None
    flat_start: Optional[str] = None
    flat_end: Optional[str] = None

    # Setup params
    max_bars_after_sweep: Optional[int] = None
    min_gap_atr_pct: Optional[float] = None
    gap_window_bars: Optional[int] = None
    min_stop_atr_pct: Optional[float] = None
    max_inversion_bars: Optional[int] = None

    # Candle timeframe: "1m", "3m", "5m", "15m"
    candle_tf: Optional[str] = None

    # Direction
    direction_filter: Optional[str] = None

    # Entry type: "market" or "limit"
    entry_type: Optional[str] = None

    # Singular gap filter
    require_singular_gap: Optional[bool] = None

    # BPR filter: "none", "tight", "loose"
    bpr_filter: Optional[str] = None
    bpr_tight_max_bars: Optional[int] = None

    # Sweep toggles
    use_pdh_sweeps: Optional[bool] = None
    use_pdl_sweeps: Optional[bool] = None
    asia_use_high_sweeps: Optional[bool] = None
    asia_use_low_sweeps: Optional[bool] = None
    london_use_high_sweeps: Optional[bool] = None
    london_use_low_sweeps: Optional[bool] = None

    # 1H Swing sweeps
    use_swing_high_sweeps: Optional[bool] = None
    use_swing_low_sweeps: Optional[bool] = None
    swing_length: Optional[int] = None


class IFVGOptimizeRequest(BaseModel):
    instrument: str = "NQ"
    start: Optional[str] = None
    end: Optional[str] = None
    name: Optional[str] = None
    n_workers: Optional[int] = None

    # Param ranges (lists of values)
    rr: Optional[list[float]] = None
    tp1_ratio: Optional[list[float]] = None
    min_gap_atr_pct: Optional[list[float]] = None
    gap_window_bars: Optional[list[int]] = None
    max_bars_after_sweep: Optional[list[int]] = None
    be_offset_ticks: Optional[list[int]] = None
    min_stop_atr_pct: Optional[list[float]] = None
    max_inversion_bars: Optional[list[int]] = None
    candle_tf: Optional[list[str]] = None
    bpr_filter: Optional[list[str]] = None
    bpr_tight_max_bars: Optional[list[int]] = None


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


# ── Helpers ───────────────────────────────────────────────────────


def _build_config(req: IFVGBacktestRequest) -> IFVGConfig:
    """Build IFVGConfig from request, applying overrides to defaults."""
    try:
        inst = get_instrument(req.instrument)
    except KeyError:
        raise unknown_instrument(req.instrument)

    config = default_config(inst)

    overrides = {}
    for field_name in (
        "rr", "tp1_ratio", "risk_usd", "min_qty", "qty_step",
        "be_offset_ticks", "atr_length",
        "entry_start", "entry_end", "flat_start", "flat_end",
        "max_bars_after_sweep", "min_gap_atr_pct", "gap_window_bars",
        "min_stop_atr_pct", "max_inversion_bars", "candle_tf", "require_singular_gap",
        "direction_filter", "entry_type",
        "bpr_filter", "bpr_tight_max_bars",
        "use_pdh_sweeps", "use_pdl_sweeps",
        "use_swing_high_sweeps", "use_swing_low_sweeps", "swing_length",
        "asia_use_high_sweeps", "asia_use_low_sweeps",
        "london_use_high_sweeps", "london_use_low_sweeps",
    ):
        val = getattr(req, field_name, None)
        if val is not None:
            overrides[field_name] = val

    if req.name:
        overrides["name"] = req.name
    if req.notes:
        overrides["notes"] = req.notes

    return with_overrides(config, **overrides)


# ── Discovery endpoints ─────────────────────────────────────────────


@router.get("/instruments")
async def list_ifvg_instruments():
    """List available instruments."""
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


# ── Backtest endpoints ──────────────────────────────────────────────


@router.post("/backtest")
async def run_ifvg_backtest(req: IFVGBacktestRequest):
    """Run a single IFVG backtest."""
    config = _build_config(req)

    try:
        df = load_5m_data(config.instrument.data_file, start=req.start, end=req.end)
    except FileNotFoundError:
        raise data_not_found(f"Data not found for instrument: {req.instrument}")

    # Load 1m data when candle_tf requires it
    df_1m = None
    if config.candle_tf != "5m":
        try:
            df_1m = load_1m_for_5m(config.instrument.data_file, start=req.start, end=req.end)
        except FileNotFoundError:
            raise data_not_found(f"{req.instrument} (1m data required for candle_tf='{config.candle_tf}')")

    trades = run_backtest(df, config, start_date=req.start, end_date=req.end, df_1m=df_1m)
    result = results_to_dict(trades, config, include_equity_curve=True)

    result_id = save_backtest_result(result)
    result["id"] = result_id

    return ok(result)


@router.get("/backtests")
async def list_ifvg_backtests():
    """List backtest history."""
    return ok(list_backtest_history())


@router.get("/backtests/{result_id}")
async def get_ifvg_backtest(result_id: str):
    """Load a saved IFVG backtest result."""
    result = load_backtest_result(result_id)
    if result is None:
        raise backtest_not_found(result_id)
    result["id"] = result_id
    return ok(result)


@router.delete("/backtests/{result_id}")
async def delete_ifvg_backtest(result_id: str):
    """Delete a saved IFVG backtest result."""
    success = delete_backtest_result(result_id)
    if not success:
        raise backtest_not_found(result_id)
    return ok({"deleted": result_id})


@router.post("/backtests/{result_id}/star")
async def star_ifvg_backtest(result_id: str):
    """Toggle the starred flag for a backtest."""
    new_state = toggle_star(result_id)
    if new_state is None:
        raise backtest_not_found(result_id)
    return ok({"starred": new_state})


@router.post("/backtests/{result_id}/hide")
async def hide_ifvg_backtest(result_id: str):
    """Toggle the hidden flag for a backtest."""
    new_state = toggle_hidden(result_id)
    if new_state is None:
        raise backtest_not_found(result_id)
    return ok({"hidden": new_state})


@router.patch("/backtests/{result_id}/name")
async def rename_ifvg_backtest(result_id: str, body: dict):
    """Rename a backtest's experiment name."""
    new_name = body.get("name", "").strip()
    if not new_name:
        raise IFVGError(
            code="INVALID_NAME",
            reason="Name cannot be empty",
            fix="Provide a non-empty 'name' field in the request body",
        )
    result = rename_backtest_db(result_id, new_name)
    if result is None:
        raise backtest_not_found(result_id)
    return ok({"name": result})


@router.get("/starred")
async def get_ifvg_starred():
    """List starred backtest runs."""
    return ok(list_starred())


# ── Optimization endpoints ──────────────────────────────────────────


@router.post("/optimize")
async def run_ifvg_optimize(req: IFVGOptimizeRequest):
    """Run an IFVG parameter optimization sweep."""
    try:
        inst = get_instrument(req.instrument)
    except KeyError:
        raise unknown_instrument(req.instrument)

    base = default_config(inst)

    param_ranges = {}
    for field_name in ("rr", "tp1_ratio", "min_gap_atr_pct", "gap_window_bars",
                       "max_bars_after_sweep", "be_offset_ticks",
                       "min_stop_atr_pct", "max_inversion_bars", "candle_tf",
                       "bpr_filter", "bpr_tight_max_bars"):
        val = getattr(req, field_name, None)
        if val is not None:
            param_ranges[field_name] = val

    if not param_ranges:
        raise no_sweep_params()

    configs = generate_param_grid(base, param_ranges)

    try:
        df = load_5m_data(inst.data_file, start=req.start, end=req.end)
    except FileNotFoundError:
        raise data_not_found(f"Data not found for instrument: {req.instrument}")

    # Load 1m data if any config uses a non-5m timeframe
    df_1m = None
    needs_1m = any(c.candle_tf != "5m" for c in configs)
    if needs_1m:
        try:
            df_1m = load_1m_for_5m(inst.data_file, start=req.start, end=req.end)
        except FileNotFoundError:
            raise data_not_found(f"{req.instrument} (1m data required for non-5m candle_tf)")

    results = run_sweep(
        df, configs,
        n_workers=req.n_workers,
        start_date=req.start,
        end_date=req.end,
        df_1m=df_1m,
    )

    # Build response
    grid_result = grid_results_to_dict(
        [(config, trades) for config, trades, _ in results],
        swept_params=param_ranges,
    )

    # Auto-save optimization
    result_id = save_optimization_result(grid_result)
    # Log individual sweep runs to experiment DB
    try:
        log_ifvg_sweep_runs(results, result_id)
    except Exception:
        pass
    grid_result["id"] = result_id

    if req.name:
        grid_result["name"] = req.name

    return ok(grid_result)


@router.get("/optimizations")
async def list_ifvg_optimizations():
    """List optimization history."""
    return ok(list_optimization_results())


@router.get("/optimizations/{result_id}")
async def get_ifvg_optimization(result_id: str):
    """Load a full optimization result."""
    data = load_optimization_result(result_id)
    if data is None:
        raise optimization_not_found(result_id)
    data["id"] = result_id
    return ok(data)


@router.delete("/optimizations/{result_id}")
async def delete_ifvg_optimization(result_id: str):
    """Delete an optimization result."""
    if not delete_optimization_result(result_id):
        raise optimization_not_found(result_id)
    return ok({"deleted": result_id})


# ── Experiment tracking endpoints ────────────────────────────────────


@router.get("/experiments")
async def list_ifvg_experiments(
    instrument: Optional[str] = None,
    min_pf: Optional[float] = None,
    min_sharpe: Optional[float] = None,
    name: Optional[str] = None,
    run_type: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = 50,
):
    """Query experiment runs with filters."""
    filters = {}
    if instrument:
        filters["instrument"] = instrument
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


@router.get("/experiments/compare")
async def compare_ifvg_experiments(ids: str):
    """Compare specific experiment runs by ID."""
    try:
        run_ids = [int(x.strip()) for x in ids.split(",")]
    except ValueError:
        raise invalid_experiment_ids()
    return ok(compare_runs(run_ids))


@router.get("/experiments/{run_id}")
async def get_ifvg_experiment(run_id: int):
    """Get a single experiment run by ID."""
    rows = compare_runs([run_id])
    if not rows:
        raise experiment_not_found(run_id)
    return ok(rows[0])


# ── Coverage endpoints ───────────────────────────────────────────────


@router.get("/coverage")
async def get_ifvg_coverage():
    """Aggregate coverage stats grouped by instrument."""
    return ok(get_instrument_coverage())


@router.get("/coverage/{instrument}/params")
async def get_ifvg_coverage_params(instrument: str):
    """Return distinct values of key sweep params for an instrument."""
    return ok(get_param_coverage(instrument))


# ── Testing plan endpoints ───────────────────────────────────────────


@router.get("/testing-plan")
async def get_ifvg_testing_plan(instrument: Optional[str] = None):
    """List testing plan items."""
    return ok(list_testing_plan(instrument))


@router.post("/testing-plan")
async def create_ifvg_plan_item(req: TestingPlanCreateRequest):
    """Create a new testing plan item."""
    item = create_testing_plan_item(req.instrument, req.title, req.notes)
    return ok(item)


@router.put("/testing-plan/{item_id}")
async def update_ifvg_plan_item(item_id: int, req: TestingPlanUpdateRequest):
    """Update a testing plan item."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = update_testing_plan_item(item_id, **updates)
    if result is None:
        raise testing_plan_item_not_found(item_id)
    return ok(result)


@router.delete("/testing-plan/{item_id}")
async def delete_ifvg_plan_item(item_id: int):
    """Delete a testing plan item."""
    if not delete_testing_plan_item(item_id):
        raise testing_plan_item_not_found(item_id)
    return ok({"deleted": item_id})


@router.post("/testing-plan/reorder")
async def reorder_ifvg_plan(req: TestingPlanReorderRequest):
    """Reorder testing plan items."""
    reorder_testing_plan(req.instrument, req.item_ids)
    return ok({"reordered": True})
