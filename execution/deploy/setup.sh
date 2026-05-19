#!/usr/bin/env bash
# ORB Trader — DigitalOcean Droplet Setup Script
#
# Run this on a fresh Ubuntu 24.04 droplet:
#   ssh root@YOUR_IP 'bash -s' < deploy/setup.sh
#
# Prerequisites: create a $6/mo droplet (1 vCPU, 1 GB RAM, Ubuntu 24.04)
set -euo pipefail

APP_USER="trader"
APP_DIR="/opt/orb-trader"
REPO_URL=""  # Set this to your git repo URL, or scp files manually

echo "=== 1. System packages ==="
apt-get update -qq
apt-get install -y -qq curl git build-essential

echo "=== 2. Create app user ==="
if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
    echo "Created user: $APP_USER"
fi

echo "=== 3. Install uv ==="
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Make uv available system-wide
    cp /root/.local/bin/uv /usr/local/bin/uv
    cp /root/.local/bin/uvx /usr/local/bin/uvx 2>/dev/null || true
fi
uv --version

echo "=== 4. Create app directory ==="
mkdir -p "$APP_DIR"

echo "=== 5. Set up .env file ==="
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" <<'ENVEOF'
# ORB Trader secrets — fill these in after setup
DATABENTO_API_KEY=
MAIN_DB_URL=http://127.0.0.1:8100
ENVEOF
    chmod 600 "$APP_DIR/.env"
    echo "Created $APP_DIR/.env — fill in your API keys!"
else
    echo ".env already exists, skipping"
fi

echo "=== 6. Copy application files ==="
echo ""
echo "Now copy your execution/ directory to the droplet:"
echo ""
echo "  scp -r execution/* root@YOUR_IP:$APP_DIR/"
echo ""
echo "Then fill in your API keys:"
echo ""
echo "  ssh root@YOUR_IP 'nano $APP_DIR/.env'"
echo ""
echo "Then install the systemd service:"
echo ""
echo "  ssh root@YOUR_IP 'bash $APP_DIR/deploy/install-service.sh'"
echo ""
echo "=== Setup complete ==="
