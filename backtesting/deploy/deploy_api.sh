#!/usr/bin/env bash
# Deploy the full backtesting API to the DigitalOcean droplet.
#
# Usage (from repo root):
#   bash backtesting/deploy/deploy_api.sh
#
# First time on the droplet:
#   bash backtesting/deploy/deploy_api.sh --setup
#
# Optional market-data sync after code deploy:
#   bash backtesting/deploy/deploy_api.sh --sync-data
set -euo pipefail

DROPLET="root@143.110.148.234"
REMOTE_DIR="/opt/orb-backtester"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_DEPLOY="$(cd "$(dirname "$0")" && pwd)"

SETUP=0
SYNC_DATA=0
for arg in "$@"; do
    case "$arg" in
        --setup) SETUP=1 ;;
        --sync-data) SYNC_DATA=1 ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

if [[ "$SETUP" == "1" ]]; then
    echo "=== First-time backtester API setup ==="

    echo "--- Creating directories ---"
    ssh "$DROPLET" "mkdir -p $REMOTE_DIR/data/raw $REMOTE_DIR/data/cache $REMOTE_DIR/data/results $REMOTE_DIR/data/optimizations"

    echo "--- Creating .env if missing ---"
    ssh "$DROPLET" "if [ ! -f $REMOTE_DIR/.env ]; then cat > $REMOTE_DIR/.env <<'ENV'
BACKTEST_API_HOST=127.0.0.1
BACKTEST_API_PORT=8200
MAIN_DB_URL=http://127.0.0.1:8100
EXPERIMENTS_DB_URL=http://127.0.0.1:8100
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=orb-backtests-data
ENV
fi"

    echo "--- Installing systemd service ---"
    scp "$LOCAL_DEPLOY/orb-backtester.service" "$DROPLET:/etc/systemd/system/orb-backtester.service"
    ssh "$DROPLET" "systemctl daemon-reload && systemctl enable orb-backtester"

    echo "=== Setup complete. Fill R2 values in $REMOTE_DIR/.env if you want server-side data sync, then run deploy. ==="
fi

echo "--- Ensuring remote .env exists ---"
ssh "$DROPLET" "mkdir -p $REMOTE_DIR/data/raw $REMOTE_DIR/data/cache $REMOTE_DIR/data/results $REMOTE_DIR/data/optimizations && if [ ! -f $REMOTE_DIR/.env ]; then cat > $REMOTE_DIR/.env <<'ENV'
BACKTEST_API_HOST=127.0.0.1
BACKTEST_API_PORT=8200
MAIN_DB_URL=http://127.0.0.1:8100
EXPERIMENTS_DB_URL=http://127.0.0.1:8100
R2_BUCKET_NAME=orb-backtests-data
ENV
fi
if ! grep -q '^MAIN_DB_URL=' $REMOTE_DIR/.env; then printf '\nMAIN_DB_URL=http://127.0.0.1:8100\n' >> $REMOTE_DIR/.env; fi"
ssh "$DROPLET" "if grep -q '^BACKTEST_API_HOST=' $REMOTE_DIR/.env; then sed -i 's/^BACKTEST_API_HOST=.*/BACKTEST_API_HOST=127.0.0.1/' $REMOTE_DIR/.env; else printf '\nBACKTEST_API_HOST=127.0.0.1\n' >> $REMOTE_DIR/.env; fi"

echo "=== Deploying backtester API from $LOCAL_DIR ==="

echo "--- Syncing source files ---"
rsync -avz --delete \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude '/data/' \
    --exclude '.pytest_cache/' \
    "$LOCAL_DIR/" "$DROPLET:$REMOTE_DIR/"

echo "--- Installing dependencies ---"
ssh "$DROPLET" "cd $REMOTE_DIR && uv sync --extra storage --extra api"

if [[ "$SYNC_DATA" == "1" ]]; then
    echo "--- Syncing raw market data from R2 ---"
    ssh "$DROPLET" "cd $REMOTE_DIR && uv run --extra storage python scripts/sync_data.py download raw"
fi

echo "--- Installing latest service unit ---"
scp "$LOCAL_DEPLOY/orb-backtester.service" "$DROPLET:/etc/systemd/system/orb-backtester.service"
ssh "$DROPLET" "systemctl daemon-reload && systemctl enable orb-backtester"

echo "--- Restarting service ---"
ssh "$DROPLET" "systemctl restart orb-backtester"

echo "--- Verifying ---"
sleep 3
ssh "$DROPLET" "systemctl is-active orb-backtester && curl -sf http://localhost:8200/api/health | head -c 200 || echo 'WARNING: service not responding yet'"

echo "=== Deploy complete ==="
