"""Remote main DB client — proxies DB operations through the main DB API.

Set MAIN_DB_URL=http://143.110.148.234:8100 to activate.
EXPERIMENTS_DB_URL is still honored as a compatibility alias.
All functions match the signatures in experiments.py so they can be swapped in.
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from urllib.parse import quote, urlencode
from typing import Any

API_URL = (
    os.environ.get("MAIN_DB_URL")
    or os.environ.get("EXPERIMENTS_DB_URL", "")
).rstrip("/")

# Timeout in seconds — large payloads (trades + equity curves) need more time.
_TIMEOUT = 120


def _request(method: str, path: str, body: dict | None = None) -> Any:
    """Make an HTTP request to the main DB API."""
    url = f"{API_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        raise RuntimeError(f"Main DB API error ({e.code}): {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach main DB API at {API_URL}: {e}") from e

    if not result.get("success"):
        raise RuntimeError(f"Main DB API returned error: {result.get('error')}")

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
    serialized_results = []
    for item in all_results:
        if isinstance(item, dict):
            serialized_results.append(item)
            continue
        config, trades = item
        from .results.export import results_to_dict
        serialized_results.append(results_to_dict(trades, config, include_trades=False))

    resp = _post("/api/sweep-runs", {
        "all_results": serialized_results,
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


# --- Sync / Import ---

# --- News Straddle CRUD ---

def log_news_straddle_run(result_dict, result_id):
    resp = _post("/api/news-straddle/runs", {
        "result_dict": result_dict,
        "result_id": result_id,
    })
    return resp.get("rowid")


def list_news_straddle_history(limit=100):
    return _get(f"/api/news-straddle/runs?limit={limit}")


def get_news_straddle_run(result_id):
    try:
        return _get(f"/api/news-straddle/runs/{result_id}")
    except RuntimeError:
        return None


def delete_news_straddle_run(result_id):
    try:
        _delete(f"/api/news-straddle/runs/{result_id}")
        return True
    except RuntimeError:
        return False


# --- Regime Reports CRUD ---

def log_regime_report(result_dict, result_id):
    resp = _post("/api/regime-reports", {
        "result_dict": result_dict,
        "result_id": result_id,
    })
    return resp.get("rowid")


def list_regime_reports(limit=100):
    return _get(f"/api/regime-reports?limit={limit}")


def get_regime_report(result_id):
    try:
        return _get(f"/api/regime-reports/{result_id}")
    except RuntimeError:
        return None


def delete_regime_report(result_id):
    try:
        _delete(f"/api/regime-reports/{result_id}")
        return True
    except RuntimeError:
        return False


# --- Risk Engine Layouts ---

def list_risk_engine_layouts():
    return _get("/api/risk-engine/layouts")


def save_risk_engine_layout(name, account_risk, strategies):
    return _post("/api/risk-engine/layouts", {
        "name": name,
        "accountRisk": account_risk,
        "strategies": strategies,
    })


def delete_risk_engine_layout(name):
    try:
        _delete(f"/api/risk-engine/layouts/{quote(str(name), safe='')}")
        return True
    except RuntimeError:
        return False


# --- Saved Configs CRUD ---

def list_saved_configs(limit=200):
    return _get(f"/api/configs?limit={limit}")


def get_saved_config(config_id):
    try:
        return _get(f"/api/configs/{config_id}")
    except RuntimeError:
        return None


def create_saved_config(name, notes, instrument, sessions, strategy, config):
    return _post("/api/configs", {
        "name": name,
        "notes": notes,
        "instrument": instrument,
        "sessions": sessions,
        "strategy": strategy,
        "config": config,
    })


def update_saved_config(config_id, name, notes, instrument, sessions, strategy, config):
    try:
        return _put(f"/api/configs/{config_id}", {
            "name": name,
            "notes": notes,
            "instrument": instrument,
            "sessions": sessions,
            "strategy": strategy,
            "config": config,
        })
    except RuntimeError:
        return None


def delete_saved_config(config_id):
    try:
        _delete(f"/api/configs/{config_id}")
        return True
    except RuntimeError:
        return False


# --- Sync / Import ---

def import_runs(rows):
    resp = _post("/api/sync/import", {"runs": rows, "optimizations": []})
    return resp.get("runs_imported", 0)


def import_optimizations(rows):
    resp = _post("/api/sync/import", {"runs": [], "optimizations": rows})
    return resp.get("optimizations_imported", 0)


# --- Live Trades CRUD ---

def log_live_trade(trade):
    resp = _post("/api/live-trades", {"trade": trade})
    return resp.get("rowid")


def list_live_trades(session="", config_name="", date_from="", date_to="", limit=500):
    params = urlencode({k: v for k, v in {
        "session": session,
        "config": config_name,
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
    }.items() if v})
    return _get(f"/api/live-trades?{params}")


def get_live_trade(trade_id):
    try:
        return _get(f"/api/live-trades/{trade_id}")
    except RuntimeError:
        return None


def update_live_trade(trade_id, updates):
    try:
        return _patch(f"/api/live-trades/{trade_id}", {"updates": updates})
    except RuntimeError:
        return None


def delete_live_trade(trade_id):
    try:
        _delete(f"/api/live-trades/{trade_id}")
        return True
    except RuntimeError:
        return False


# --- Execution Logs ---

def log_execution_log(log_type, entry):
    resp = _post(f"/api/execution-logs/{quote(str(log_type), safe='')}", {"entry": entry})
    return resp.get("rowid")


def log_execution_logs_batch(log_type, entries):
    resp = _post(f"/api/execution-logs/{quote(str(log_type), safe='')}", {"entries": entries})
    return resp.get("count", 0)


def list_execution_logs(
    log_type,
    limit=500,
    offset=0,
    config="",
    session="",
    level="",
    account="",
    search="",
):
    params = urlencode({k: v for k, v in {
        "limit": limit,
        "offset": offset,
        "config": config,
        "session": session,
        "level": level,
        "account": account,
        "search": search,
    }.items() if v or k in {"limit", "offset"}})
    result = _get(f"/api/execution-logs/{quote(str(log_type), safe='')}?{params}")
    return result.get("entries", []), result.get("total", 0)


def count_execution_logs(log_type):
    result = _get(f"/api/execution-logs/{quote(str(log_type), safe='')}/count")
    return result.get("count", 0)


# --- Execution Configs ---

def upsert_execution_config(config_name, enabled=None, max_open_contracts=None, config=None):
    body = {}
    if enabled is not None:
        body["enabled"] = enabled
    if max_open_contracts is not None:
        body["max_open_contracts"] = max_open_contracts
    if config is not None:
        body["config"] = config
    return _put(f"/api/execution-configs/{quote(str(config_name), safe='')}", body)


def list_execution_configs_db():
    result = _get("/api/execution-configs")
    return result.get("configs", [])


def replace_execution_config_webhooks(config_name, webhooks):
    result = _put(
        f"/api/execution-configs/{quote(str(config_name), safe='')}/webhooks",
        {"webhooks": webhooks},
    )
    return result.get("webhooks", [])


def patch_execution_config_webhook(config_name, webhook_index, updates):
    try:
        result = _patch(
            f"/api/execution-configs/{quote(str(config_name), safe='')}/webhooks/{webhook_index}",
            updates,
        )
        return result.get("webhook")
    except RuntimeError:
        return None
