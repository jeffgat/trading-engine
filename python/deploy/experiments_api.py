"""Standalone FastAPI service for the shared experiments DB.

Run on the droplet at port 8100 alongside the execution service (port 8000).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Point DB_PATH to the droplet's shared location BEFORE importing experiments
os.environ["EXPERIMENTS_DB_PATH"] = "/opt/experiments-db/experiments.db"

# Add the backtesting source to the path so we can import experiments
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from orb_backtest.experiments import (
    init_db,
    log_run,
    log_optimization,
    list_backtest_history,
    list_optimization_history,
    get_backtest_result,
    get_optimization_result,
    delete_backtest_run,
    delete_optimization_run,
    rename_backtest,
    toggle_star,
    toggle_hidden,
    list_starred,
    query_runs,
    compare_runs,
    get_instrument_coverage,
    get_param_coverage,
    list_testing_plan,
    create_testing_plan_item,
    update_testing_plan_item,
    delete_testing_plan_item,
    reorder_testing_plan,
    import_runs,
    import_optimizations,
)

app = FastAPI(title="Shared Experiments DB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def ok(data):
    return {"success": True, "result": data}


def fail(msg, status=400):
    return JSONResponse({"success": False, "error": msg}, status_code=status)


# --- Health ---

@app.get("/api/health")
def health():
    init_db()
    return ok("healthy")


# --- Backtest CRUD ---

class LogRunRequest(BaseModel):
    result_dict: dict
    result_id: str
    run_type: str = "backtest"
    git_hash: Optional[str] = None

@app.post("/api/runs")
def create_run(req: LogRunRequest):
    rowid = log_run(req.result_dict, req.result_id, req.run_type, git_hash=req.git_hash)
    return ok({"rowid": rowid})


@app.get("/api/backtests")
def list_backtests(limit: int = 100):
    return ok(list_backtest_history(limit=limit))


@app.get("/api/backtests/{result_id}")
def get_backtest(result_id: str):
    row = get_backtest_result(result_id)
    if row is None:
        return fail("not found", 404)
    return ok(row)


@app.delete("/api/backtests/{result_id}")
def delete_backtest(result_id: str):
    success = delete_backtest_run(result_id)
    if not success:
        return fail("not found", 404)
    return ok({"deleted": True})


@app.post("/api/backtests/{result_id}/star")
def star_backtest(result_id: str):
    val = toggle_star(result_id)
    if val is None:
        return fail("not found", 404)
    return ok({"starred": val})


@app.post("/api/backtests/{result_id}/hide")
def hide_backtest(result_id: str):
    val = toggle_hidden(result_id)
    if val is None:
        return fail("not found", 404)
    return ok({"hidden": val})


class RenameRequest(BaseModel):
    name: str

@app.patch("/api/backtests/{result_id}/name")
def rename_backtest_ep(result_id: str, req: RenameRequest):
    name = rename_backtest(result_id, req.name)
    if name is None:
        return fail("not found", 404)
    return ok({"name": name})


@app.get("/api/starred")
def get_starred(limit: int = 100):
    return ok(list_starred(limit=limit))


# --- Optimization CRUD ---

class LogOptimizationRequest(BaseModel):
    result_dict: dict
    result_id: str

@app.post("/api/optimizations")
def create_optimization(req: LogOptimizationRequest):
    rowid = log_optimization(req.result_dict, req.result_id)
    return ok({"rowid": rowid})


class LogSweepRunsRequest(BaseModel):
    all_results: list
    optimization_id: str

@app.post("/api/sweep-runs")
def create_sweep_runs(req: LogSweepRunsRequest):
    # Data arrives pre-serialized as dicts from the remote client.
    # Call log_run() directly instead of log_sweep_runs() which expects
    # native (StrategyConfig, list[TradeResult]) tuples.
    # Pre-compute git hash once for the entire batch (avoids N subprocess calls).
    from orb_backtest.experiments import _get_git_hash
    git_hash = _get_git_hash()
    count = 0
    for result_dict in req.all_results:
        log_run(result_dict, req.optimization_id, run_type="optimization", git_hash=git_hash)
        count += 1
    return ok({"count": count})


@app.get("/api/optimizations")
def list_optimizations(limit: int = 100):
    return ok(list_optimization_history(limit=limit))


@app.get("/api/optimizations/{result_id}")
def get_optimization(result_id: str):
    row = get_optimization_result(result_id)
    if row is None:
        return fail("not found", 404)
    return ok(row)


@app.delete("/api/optimizations/{result_id}")
def delete_optimization(result_id: str):
    success = delete_optimization_run(result_id)
    if not success:
        return fail("not found", 404)
    return ok({"deleted": True})


# --- Sync / Import ---

class SyncImportRequest(BaseModel):
    runs: list[dict] = []
    optimizations: list[dict] = []

@app.post("/api/sync/import")
def sync_import(req: SyncImportRequest):
    runs_count = import_runs(req.runs)
    opts_count = import_optimizations(req.optimizations)
    return ok({"runs_imported": runs_count, "optimizations_imported": opts_count})


# --- Query / Compare ---

@app.get("/api/experiments")
def list_experiments(
    instrument: Optional[str] = None,
    sessions: Optional[str] = None,
    min_sharpe: Optional[float] = None,
    min_profit_factor: Optional[float] = None,
    experiment_name: Optional[str] = None,
    run_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 200,
):
    filters = {}
    if instrument:
        filters["instrument"] = instrument
    if sessions:
        filters["sessions"] = sessions
    if min_sharpe is not None:
        filters["min_sharpe"] = min_sharpe
    if min_profit_factor is not None:
        filters["min_profit_factor"] = min_profit_factor
    if experiment_name:
        filters["experiment_name"] = experiment_name
    if run_type:
        filters["run_type"] = run_type
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    filters["limit"] = limit
    return ok(query_runs(**filters))


@app.get("/api/experiments/compare")
def compare_experiments(ids: str = Query(...)):
    run_ids = [int(x.strip()) for x in ids.split(",")]
    return ok(compare_runs(run_ids))


# --- Coverage ---

@app.get("/api/coverage")
def get_coverage():
    return ok(get_instrument_coverage())


@app.get("/api/coverage/{instrument}/params")
def get_coverage_params(instrument: str):
    return ok(get_param_coverage(instrument))


# --- Testing Plan ---

class PlanItemCreate(BaseModel):
    instrument: str
    title: str
    notes: Optional[str] = None

class PlanItemUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

class PlanReorder(BaseModel):
    instrument: str
    item_ids: list[int]

@app.get("/api/testing-plan")
def get_testing_plan(instrument: Optional[str] = None):
    return ok(list_testing_plan(instrument))

@app.post("/api/testing-plan")
def create_plan_item(req: PlanItemCreate):
    return ok(create_testing_plan_item(req.instrument, req.title, req.notes))

@app.put("/api/testing-plan/{item_id}")
def update_plan_item(item_id: int, req: PlanItemUpdate):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = update_testing_plan_item(item_id, **updates)
    if result is None:
        return fail("not found", 404)
    return ok(result)

@app.delete("/api/testing-plan/{item_id}")
def delete_plan_item(item_id: int):
    success = delete_testing_plan_item(item_id)
    if not success:
        return fail("not found", 404)
    return ok({"deleted": True})

@app.post("/api/testing-plan/reorder")
def reorder_plan(req: PlanReorder):
    success = reorder_testing_plan(req.instrument, req.item_ids)
    return ok({"reordered": success})


if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8100)
