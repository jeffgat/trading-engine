#!/usr/bin/env bash
# Deploy the execution service to the DigitalOcean droplet.
#
# Usage (from repo root):
#   bash execution/deploy/deploy.sh
#
# What it does:
#   1. rsync execution/ source to /opt/orb-trader/ on the droplet
#   2. Restart the orb-trader systemd service
#
# Prerequisites:
#   - SSH access to root@143.110.148.234 (set up SSH keys)
#   - Initial setup already done (setup.sh + install-service.sh)
set -euo pipefail

DROPLET="root@143.110.148.234"
REMOTE_DIR="/opt/orb-trader"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Deploying from $LOCAL_DIR ==="

echo "--- Syncing source files ---"
rsync -avz --delete \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude 'logs/' \
    "$LOCAL_DIR/" "$DROPLET:$REMOTE_DIR/"

echo "--- Installing dependencies ---"
ssh "$DROPLET" "cd $REMOTE_DIR && uv sync"

echo "--- Restarting service ---"
ssh "$DROPLET" "systemctl restart orb-trader"

echo "--- Verifying ---"
sleep 3
ssh "$DROPLET" "systemctl is-active orb-trader && ss -tlnp | grep 8000 || echo 'WARNING: port 8000 not yet listening (may take a few seconds for ATR warmup)'"

echo "=== Deploy complete ==="
