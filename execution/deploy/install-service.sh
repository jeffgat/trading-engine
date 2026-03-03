#!/usr/bin/env bash
# Install the orb-trader systemd service
set -euo pipefail

APP_DIR="/opt/orb-trader"

echo "=== Installing Python dependencies ==="
cd "$APP_DIR"
uv sync

echo "=== Installing systemd service ==="
cp "$APP_DIR/deploy/orb-trader.service" /etc/systemd/system/orb-trader.service
systemctl daemon-reload
systemctl enable orb-trader

echo "=== Starting service ==="
systemctl start orb-trader
systemctl status orb-trader --no-pager

echo ""
echo "Service installed and running!"
echo ""
echo "Useful commands:"
echo "  systemctl status orb-trader      # Check status"
echo "  journalctl -u orb-trader -f      # Follow logs"
echo "  systemctl restart orb-trader     # Restart"
echo "  systemctl stop orb-trader        # Stop"
echo ""
echo "Log files:"
echo "  $APP_DIR/logs/trader.log         # Main log"
echo "  $APP_DIR/logs/trades.log         # Trade audit trail"
echo "  $APP_DIR/logs/webhooks.log       # Per-account webhook activity"
