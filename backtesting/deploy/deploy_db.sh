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
    "pydantic>=2.0",
]

[project.scripts]
experiments-db = "experiments_api:app"
TOML

    echo "--- Creating .env ---"
    ssh "$DROPLET" "printf 'EXPERIMENTS_DB_PATH=/opt/experiments-db/experiments.db\nEXPERIMENTS_DB_URL=\n' > $REMOTE_DIR/.env"

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
