# Deploy Shared Experiments DB to Digital Ocean

This guide sets up a shared SQLite experiments database on the existing Digital Ocean droplet (`143.110.148.234`) so both the backtesting engine and execution service can read/write from the same DB.

## Who Does What

| Step | Who | Requires SSH? |
|------|-----|---------------|
| Phase 1: Deploy the DB API service on the droplet | **Jeff** (has SSH access) | Yes |
| Phase 2: Create the code files (remote client, API script) | **Jeff** (commits to repo) | No |
| Phase 3: Pull the branch and set one env var | **Chris** | No |

Chris never needs SSH access to the droplet. All his reads/writes go through HTTP.

## Architecture

```
┌──────────────────────┐         ┌───────────────────────────────────┐
│  Chris's Machine     │         │  DO Droplet (143.110.148.234)     │
│  (backtesting engine)│         │                                   │
│                      │  HTTP   │  ┌─────────────────────────────┐  │
│  experiments.py ─────┼────────►│  │  experiments-api (port 8100) │  │
│  (reads & writes     │         │  │  FastAPI + SQLite            │  │
│   via API, not local)│         │  │  /opt/experiments-db/        │  │
│                      │         │  └─────────────────────────────┘  │
└──────────────────────┘         │                                   │
                                 │  ┌─────────────────────────────┐  │
┌──────────────────────┐         │  │  orb-trader (port 8000)     │  │
│  Jeff's Machine      │         │  │  execution service           │  │
│  (execution service) │         │  └─────────────────────────────┘  │
└──────────────────────┘         └───────────────────────────────────┘
```

**Key decisions:**
- SQLite DB lives at `/opt/experiments-db/experiments.db` on the droplet
- A lightweight FastAPI service (port 8100) wraps the DB with the same API the frontend already uses
- The backtesting engine's `experiments.py` gets a new remote mode — when `EXPERIMENTS_DB_URL` is set, all reads/writes go through the API instead of local SQLite
- No schema changes, no Postgres migration, no new managed services

---

## Phase 1: Deploy the DB API on the Droplet (Jeff)

Jeff runs all of these commands. He has SSH access to the droplet.

### 1.1 Get Chris's current experiments.db

Chris needs to send his `experiments.db` file to Jeff. It's at:

```
backtesting/data/results/experiments.db
```

He can send it via Slack, Google Drive, AirDrop, etc. Jeff saves it somewhere locally (e.g. `~/Downloads/experiments.db`).

### 1.2 Create the files

Jeff creates these 4 files in the repo and commits them to the `main` branch (or a branch Chris can pull from).

#### File 1: `backtesting/deploy/experiments_api.py`

Standalone FastAPI app that wraps the existing experiments module.

```python
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from orb_backtest.experiments import (
    init_db,
    log_run,
    log_optimization,
    log_sweep_runs,
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
    rowid = log_run(req.result_dict, req.result_id, req.run_type, req.git_hash)
    return ok({"rowid": rowid})


@app.get("/api/backtests")
def list_backtests():
    return ok(list_backtest_history())


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
def get_starred():
    return ok(list_starred())


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
    count = log_sweep_runs(req.all_results, req.optimization_id)
    return ok({"count": count})


@app.get("/api/optimizations")
def list_optimizations():
    return ok(list_optimization_history())


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
```

#### File 2: `backtesting/deploy/experiments-db.service`

```ini
[Unit]
Description=Shared Experiments DB API
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/experiments-db
ExecStart=/usr/local/bin/uv run python /opt/experiments-db/experiments_api.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/experiments-db/.env

[Install]
WantedBy=multi-user.target
```

#### File 3: `backtesting/deploy/deploy_db.sh`

```bash
#!/usr/bin/env bash
# Deploy the shared experiments DB API to the droplet.
#
# Usage (from repo root):
#   bash backtesting/deploy/deploy_db.sh
#
# First time? Run with --setup flag:
#   bash backtesting/deploy/deploy_db.sh --setup
set -euo pipefail

DROPLET="root@143.110.148.234"
REMOTE_DIR="/opt/experiments-db"
LOCAL_SRC="$(cd "$(dirname "$0")/.." && pwd)/src"
LOCAL_DEPLOY="$(cd "$(dirname "$0")" && pwd)"

# --- First-time setup ---
if [[ "${1:-}" == "--setup" ]]; then
    echo "=== First-time setup ==="

    echo "--- Creating directories ---"
    ssh "$DROPLET" "mkdir -p $REMOTE_DIR/backups"

    echo "--- Uploading current experiments.db ---"
    DB_FILE="${2:-$(cd "$(dirname "$0")/.." && pwd)/data/results/experiments.db}"
    if [[ -f "$DB_FILE" ]]; then
        scp "$DB_FILE" "$DROPLET:$REMOTE_DIR/experiments.db"
        echo "    Uploaded experiments.db ($(du -h "$DB_FILE" | cut -f1))"
    else
        echo "    WARNING: No experiments.db found at $DB_FILE"
        echo "    The API will create a fresh empty DB."
    fi

    echo "--- Creating pyproject.toml ---"
    ssh "$DROPLET" "cat > $REMOTE_DIR/pyproject.toml" << 'TOML'
[project]
name = "experiments-db"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
]

[project.scripts]
experiments-db = "experiments_api:app"
TOML

    echo "--- Creating .env ---"
    ssh "$DROPLET" "echo 'EXPERIMENTS_DB_PATH=/opt/experiments-db/experiments.db' > $REMOTE_DIR/.env"

    echo "--- Installing uv dependencies ---"
    ssh "$DROPLET" "cd $REMOTE_DIR && uv sync"

    echo "--- Installing systemd service ---"
    scp "$LOCAL_DEPLOY/experiments-db.service" "$DROPLET:/etc/systemd/system/experiments-db.service"
    ssh "$DROPLET" "systemctl daemon-reload && systemctl enable experiments-db"

    echo "=== Setup complete. Now run without --setup to deploy. ==="
    exit 0
fi

# --- Deploy ---
echo "=== Deploying experiments DB API ==="

echo "--- Syncing backtesting source (for experiments module) ---"
rsync -avz --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$LOCAL_SRC/" "$DROPLET:$REMOTE_DIR/src/"

echo "--- Syncing API script ---"
scp "$LOCAL_DEPLOY/experiments_api.py" "$DROPLET:$REMOTE_DIR/experiments_api.py"

echo "--- Restarting service ---"
ssh "$DROPLET" "systemctl restart experiments-db"

echo "--- Verifying ---"
sleep 2
ssh "$DROPLET" "systemctl is-active experiments-db && curl -s http://localhost:8100/api/health | head -c 200 || echo 'WARNING: service not responding yet'"

echo "=== Deploy complete ==="
```

#### File 4: `backtesting/src/orb_backtest/experiments_remote.py`

HTTP client that matches the `experiments.py` function signatures. When active, all DB operations go through HTTP to the droplet instead of touching local SQLite.

```python
"""Remote experiments client — proxies all DB operations through the shared API.

Set EXPERIMENTS_DB_URL=http://143.110.148.234:8100 to activate.
All functions match the signatures in experiments.py so they can be swapped in.
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
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
        resp = _post(f"/api/backtests/{result_id}/star", {})
        return resp.get("starred")
    except RuntimeError:
        return None


def toggle_hidden(result_id):
    try:
        resp = _post(f"/api/backtests/{result_id}/hide", {})
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


# --- Query / Compare ---

def query_runs(**filters):
    params = "&".join(f"{k}={v}" for k, v in filters.items() if v is not None)
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
        path += f"?instrument={instrument}"
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
```

### 1.3 Modify experiments.py

Add a conditional import at the top of `backtesting/src/orb_backtest/experiments.py`. Right after the existing imports (after line 12), add:

```python
import os as _os

# If EXPERIMENTS_DB_URL is set, all operations proxy through the remote API.
# This allows the backtesting engine to use a shared DB on the droplet.
if _os.environ.get("EXPERIMENTS_DB_URL"):
    from .experiments_remote import *  # noqa: F401, F403
```

This means: if the env var is set, the remote client's functions override everything below. If the env var is not set, the module works exactly as before (local SQLite).

### 1.4 Deploy to the droplet

Jeff runs these from the repo root:

```bash
# 1. Get Chris's experiments.db file and save it somewhere, e.g. ~/Downloads/experiments.db

# 2. Make the deploy script executable
chmod +x backtesting/deploy/deploy_db.sh

# 3. First-time setup (pass the path to Chris's DB as second arg)
bash backtesting/deploy/deploy_db.sh --setup ~/Downloads/experiments.db

# 4. Deploy the code
bash backtesting/deploy/deploy_db.sh

# 5. Verify
curl http://143.110.148.234:8100/api/health
# → {"success": true, "result": "healthy"}

curl http://143.110.148.234:8100/api/backtests | python3 -m json.tool | head -20
# → should show Chris's backtest history
```

### 1.5 Commit and push

Jeff commits all 4 new files + the experiments.py change and pushes to `main` so Chris can pull them.

---

## Phase 2: Switch to the Shared DB (Chris)

Chris does these steps on his machine. **No SSH access needed.**

### 2.1 Pull the latest code

```bash
git pull origin main
```

This gets the new `experiments_remote.py` and the updated `experiments.py` with the conditional import.

### 2.2 Set the environment variable

Add to `~/.zshrc` (or `~/.bashrc`):

```bash
export EXPERIMENTS_DB_URL="http://143.110.148.234:8100"
```

Then reload:

```bash
source ~/.zshrc
```

Or, if using a `.env` file in the backtesting directory, add:

```
EXPERIMENTS_DB_URL=http://143.110.148.234:8100
```

### 2.3 Verify it works

```bash
# Quick health check
curl http://143.110.148.234:8100/api/health

# Run a backtest — it should write to the remote DB
cd backtesting/python
python scripts/run_backtest.py  # or your usual entry point

# Confirm the new run shows up
curl http://143.110.148.234:8100/api/backtests | python3 -m json.tool | head -10
```

### 2.4 Update the frontend proxy (optional)

If Chris runs the backtesting frontend locally and wants it to show data from the shared DB, update `backtesting/frontend/vite.config.ts`:

```typescript
proxy: {
  "/api": {
    target: "http://143.110.148.234:8100",
  },
}
```

### 2.5 Switch back to local mode

To go back to local SQLite (e.g. for offline work), just unset the env var:

```bash
unset EXPERIMENTS_DB_URL
```

Everything will use the local `experiments.db` again.

---

## Ongoing Operations (Jeff)

These require SSH to the droplet. Only Jeff runs these.

### Redeploy after code changes

When `experiments.py` or the API script changes:

```bash
bash backtesting/deploy/deploy_db.sh
```

### Backup the DB

The DB auto-backs up before deletes (server-side). For manual backups:

```bash
ssh root@143.110.148.234 "cp /opt/experiments-db/experiments.db /opt/experiments-db/backups/experiments_$(date +%Y%m%d_%H%M%S).db"
```

### Check logs

```bash
ssh root@143.110.148.234 "journalctl -u experiments-db -f"
```

### Restart the service

```bash
ssh root@143.110.148.234 "systemctl restart experiments-db"
```

---

## File Summary

Files to create:

| File | Purpose |
|------|---------|
| `backtesting/deploy/experiments_api.py` | Standalone FastAPI wrapping experiments module |
| `backtesting/deploy/experiments-db.service` | systemd unit file |
| `backtesting/deploy/deploy_db.sh` | Deploy script (with `--setup` for first time) |
| `backtesting/src/orb_backtest/experiments_remote.py` | HTTP client matching experiments.py interface |

Files to modify:

| File | Change |
|------|--------|
| `backtesting/src/orb_backtest/experiments.py` | Add conditional import for remote mode |
| `backtesting/frontend/vite.config.ts` (optional) | Point proxy at `:8100` for experiment endpoints |

Environment variables:

| Var | Value | Set by |
|-----|-------|--------|
| `EXPERIMENTS_DB_URL` | `http://143.110.148.234:8100` | Chris (in `~/.zshrc` or `.env`) |
| `EXPERIMENTS_DB_PATH` | `/opt/experiments-db/experiments.db` | Jeff (on droplet, in `/opt/experiments-db/.env`) |
