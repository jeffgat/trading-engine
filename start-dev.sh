#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_API_TARGET="${REMOTE_API_TARGET:-https://143.110.148.234.nip.io}"
BACKTEST_API_HOST="${BACKTEST_API_HOST:-0.0.0.0}"
BACKTEST_API_PORT="${BACKTEST_API_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
USE_REMOTE_BACKTESTING="${USE_REMOTE_BACKTESTING:-0}"
USE_LOCAL_BACKTESTING="${USE_LOCAL_BACKTESTING:-1}"

if [ "$USE_REMOTE_BACKTESTING" = "1" ]; then
  USE_LOCAL_BACKTESTING="0"
fi

if [ -z "${BACKTESTING_API_TARGET:-}" ]; then
  if [ "$USE_LOCAL_BACKTESTING" = "1" ]; then
    BACKTESTING_API_TARGET="http://127.0.0.1:${BACKTEST_API_PORT}"
  else
    BACKTESTING_API_TARGET="$REMOTE_API_TARGET"
  fi
fi

pids=()

cleanup() {
  local status="${1:-$?}"
  trap - EXIT INT TERM

  if [ "${#pids[@]}" -gt 0 ]; then
    echo
    echo "Stopping dev servers..."
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi

  exit "$status"
}

trap 'cleanup $?' EXIT
trap 'cleanup 130' INT
trap 'cleanup 143' TERM

if [ "$USE_LOCAL_BACKTESTING" = "1" ]; then
  echo "Ensuring local default execution backtests exist"
  (
    cd "$ROOT_DIR/backtesting"
    uv run python scripts/seed_execution_default_backtests.py
  )

  echo "Starting backtesting API on http://127.0.0.1:${BACKTEST_API_PORT}"
  (
    cd "$ROOT_DIR/backtesting"
    exec uv run python scripts/run_server.py --host "$BACKTEST_API_HOST" --port "$BACKTEST_API_PORT"
  ) &
  pids+=("$!")
else
  echo "Using remote backtesting API at ${BACKTESTING_API_TARGET}"
fi

echo "Starting frontend on http://127.0.0.1:${FRONTEND_PORT}"
(
  cd "$ROOT_DIR/frontend"
  exec env BACKTESTING_API_TARGET="$BACKTESTING_API_TARGET" npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
pids+=("$!")

if wait -n 2>/dev/null; then
  cleanup 0
else
  status="$?"
  if [ "$status" -eq 2 ]; then
    wait "${pids[@]}"
    cleanup "$?"
  fi
  cleanup "$status"
fi
