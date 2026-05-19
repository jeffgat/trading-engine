#!/usr/bin/env bash
# Deploy the main DB API to the droplet.
#
# Usage (from repo root):
#   bash backtesting/deploy/deploy_db.sh
#
# First time? Run with --setup flag:
#   bash backtesting/deploy/deploy_db.sh --setup
set -euo pipefail

DROPLET="root@143.110.148.234"
REMOTE_DIR="/opt/main-db"
LEGACY_REMOTE_DIR="/opt/experiments-db"
LOCAL_SRC="$(cd "$(dirname "$0")/.." && pwd)/src"
LOCAL_DEPLOY="$(cd "$(dirname "$0")" && pwd)"

# --- First-time setup ---
if [[ "${1:-}" == "--setup" ]]; then
    echo "=== First-time setup ==="

    echo "--- Creating directories ---"
    ssh "$DROPLET" "mkdir -p $REMOTE_DIR/backups"

    echo "--- Uploading current experiments.db as main.db ---"
    DB_FILE="${2:-$(cd "$(dirname "$0")/.." && pwd)/data/results/experiments.db}"
    if [[ -f "$DB_FILE" ]]; then
        scp "$DB_FILE" "$DROPLET:$REMOTE_DIR/main.db"
        echo "    Uploaded main.db ($(du -h "$DB_FILE" | cut -f1))"
    else
        echo "    WARNING: No experiments.db found at $DB_FILE"
        echo "    The API will create a fresh empty DB."
    fi

    echo "--- Creating pyproject.toml ---"
    ssh "$DROPLET" "cat > $REMOTE_DIR/pyproject.toml" << 'TOML'
[project]
name = "main-db"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "pydantic>=2.0",
]

[project.scripts]
main-db = "experiments_api:app"
TOML

    echo "--- Creating .env ---"
    ssh "$DROPLET" "printf 'MAIN_DB_PATH=/opt/main-db/main.db\nMAIN_DB_URL=\nEXPERIMENTS_DB_PATH=/opt/main-db/main.db\nEXPERIMENTS_DB_URL=\n' > $REMOTE_DIR/.env"

    echo "--- Installing uv dependencies ---"
    ssh "$DROPLET" "cd $REMOTE_DIR && uv sync"

    echo "--- Installing systemd service ---"
    scp "$LOCAL_DEPLOY/main-db.service" "$DROPLET:/etc/systemd/system/main-db.service"
    ssh "$DROPLET" "systemctl daemon-reload && systemctl enable main-db"

    echo "=== Setup complete. Now run without --setup to deploy. ==="
    exit 0
fi

# --- Deploy ---
echo "=== Deploying main DB API ==="

echo "--- Ensuring main DB directory exists ---"
ssh "$DROPLET" "mkdir -p $REMOTE_DIR/backups && if [ ! -f $REMOTE_DIR/main.db ] && [ -f $LEGACY_REMOTE_DIR/experiments.db ]; then cp $LEGACY_REMOTE_DIR/experiments.db $REMOTE_DIR/main.db; fi"

echo "--- Ensuring pyproject.toml exists ---"
ssh "$DROPLET" "if [ ! -f $REMOTE_DIR/pyproject.toml ]; then cat > $REMOTE_DIR/pyproject.toml <<'TOML'
[project]
name = \"main-db\"
version = \"0.1.0\"
requires-python = \">=3.11\"
dependencies = [
    \"fastapi>=0.115\",
    \"uvicorn[standard]>=0.34\",
    \"pydantic>=2.0\",
]

[project.scripts]
main-db = \"experiments_api:app\"
TOML
fi"

echo "--- Ensuring .env exists ---"
ssh "$DROPLET" "if [ ! -f $REMOTE_DIR/.env ]; then printf 'MAIN_DB_PATH=/opt/main-db/main.db\nMAIN_DB_URL=\nEXPERIMENTS_DB_PATH=/opt/main-db/main.db\nEXPERIMENTS_DB_URL=\n' > $REMOTE_DIR/.env; fi"

echo "--- Syncing backtesting source (for experiments module) ---"
rsync -avz --delete \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    "$LOCAL_SRC/" "$DROPLET:$REMOTE_DIR/src/"

echo "--- Syncing API script ---"
scp "$LOCAL_DEPLOY/experiments_api.py" "$DROPLET:$REMOTE_DIR/experiments_api.py"

echo "--- Installing uv dependencies ---"
ssh "$DROPLET" "cd $REMOTE_DIR && uv sync"

echo "--- Syncing systemd service ---"
scp "$LOCAL_DEPLOY/main-db.service" "$DROPLET:/etc/systemd/system/main-db.service"
ssh "$DROPLET" "systemctl daemon-reload && systemctl enable main-db"

echo "--- Restarting service ---"
ssh "$DROPLET" "systemctl restart main-db"

echo "--- Verifying ---"
sleep 2
ssh "$DROPLET" "systemctl is-active main-db && curl -s http://localhost:8100/api/health | head -c 200 || echo 'WARNING: service not responding yet'"

echo "=== Deploy complete ==="
