"""Remote experiments client — proxies all DB operations through the shared API.

Set EXPERIMENTS_DB_URL=http://143.110.148.234:8100 to activate.
All functions match the signatures in experiments.py so they can be swapped in.
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from urllib.parse import urlencode
from typing import Any, Optional


API_URL = os.environ.get("EXPERIMENTS_DB_URL", "").rstrip("/")


def _request(method: str, path: str, body: dict | None = None) -> Any:
    """Make an HTTP request to the experiments API."""
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        raise RuntimeError(f"Experiments API error ({e.code}): {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach experiments API at {API_URL}: {e}") from e

    if not result.get("success"):
        raise RuntimeError(f"Experiments API returned error: {result.get('error')}")

    return result.get("result")


def _get(path: str) -> Any:
    return _request("GET", path)


def _post(path: str, body: dict) -> Any:
    return _request("POST", path, body)


def _delete(path: str) -> Any:
    return _request("DELETE", path)


def _patch(path: str, body: dict) -> Any:
    return _request("PATCH", path, body)


def _put(path: str, body: dict) -> Any:
    return _request("PUT", path, body)


# --- DB init (no-op for remote) ---

def init_db():
    _get("/api/health")
    return None


def backup_db():
    return None  # Backups happen server-side


# --- Backtest CRUD ---

def log_run(result_dict, result_id, run_type="backtest", git_hash=None):
    resp = _post("/api/runs", {
        "result_dict": result_dict,
        "result_id": result_id,
        "run_type": run_type,
        "git_hash": git_hash,
    })
    return resp.get("rowid")


def list_backtest_history(limit=100):
    return _get(f"/api/backtests?limit={limit}")


def get_backtest_result(result_id):
    try:
        return _get(f"/api/backtests/{result_id}")
    except RuntimeError:
        return None


def delete_backtest_run(result_id):
    try:
        _delete(f"/api/backtests/{result_id}")
        return True
    except RuntimeError:
        return False


def rename_backtest(result_id, new_name):
    try:
        resp = _patch(f"/api/backtests/{result_id}/name", {"name": new_name})
        return resp.get("name")
    except RuntimeError:
        return None


def toggle_star(result_id):
    try:
        resp = _request("POST", f"/api/backtests/{result_id}/star")
        return resp.get("starred")
    except RuntimeError:
        return None


def toggle_hidden(result_id):
    try:
        resp = _request("POST", f"/api/backtests/{result_id}/hide")
        return resp.get("hidden")
    except RuntimeError:
        return None


def list_starred(limit=100):
    return _get(f"/api/starred?limit={limit}")


# --- Optimization CRUD ---

def log_optimization(result_dict, result_id):
    resp = _post("/api/optimizations", {
        "result_dict": result_dict,
        "result_id": result_id,
    })
    return resp.get("rowid")


def log_sweep_runs(all_results, optimization_id):
    resp = _post("/api/sweep-runs", {
        "all_results": all_results,
        "optimization_id": optimization_id,
    })
    return resp.get("count")


def list_optimization_history(limit=100):
    return _get(f"/api/optimizations?limit={limit}")


def get_optimization_result(result_id):
    try:
        return _get(f"/api/optimizations/{result_id}")
    except RuntimeError:
        return None


def delete_optimization_run(result_id):
    try:
        _delete(f"/api/optimizations/{result_id}")
        return True
    except RuntimeError:
        return False


def list_recent_runs(limit=50):
    return query_runs(limit=limit)


# --- Query / Compare ---

def query_runs(**filters):
    clean = {k: v for k, v in filters.items() if v is not None}
    params = urlencode(clean)
    return _get(f"/api/experiments?{params}")


def compare_runs(run_ids):
    ids_str = ",".join(str(x) for x in run_ids)
    return _get(f"/api/experiments/compare?ids={ids_str}")


# --- Coverage ---

def get_instrument_coverage():
    return _get("/api/coverage")


def get_param_coverage(instrument):
    return _get(f"/api/coverage/{instrument}/params")


# --- Testing Plan ---

def list_testing_plan(instrument=None):
    path = "/api/testing-plan"
    if instrument:
        path += "?" + urlencode({"instrument": instrument})
    return _get(path)


def create_testing_plan_item(instrument, title, notes=None):
    return _post("/api/testing-plan", {
        "instrument": instrument,
        "title": title,
        "notes": notes,
    })


def update_testing_plan_item(item_id, **updates):
    return _put(f"/api/testing-plan/{item_id}", updates)


def delete_testing_plan_item(item_id):
    try:
        _delete(f"/api/testing-plan/{item_id}")
        return True
    except RuntimeError:
        return False


def reorder_testing_plan(instrument, item_ids):
    resp = _post("/api/testing-plan/reorder", {
        "instrument": instrument,
        "item_ids": item_ids,
    })
    return resp.get("reordered", False)
