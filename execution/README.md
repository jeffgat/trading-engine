Execution Service — Complete
Location: execution/

Architecture

DataBento (1m bars) → feed.py (aggregate to 5m + ATR) → engine.py (state machine) → broker.py (webhooks) → TradersPost → Broker
Modules
Module	Purpose
feed.py	- DataBento live streaming + 1m→5m aggregation + incremental daily ATR (Wilder's). Also has ReplayFeed for historical CSV replay testing.
engine.py	- Per-session state machine: IDLE → ORB_BUILDING → SCANNING → ARMED → FILLED → MANAGING → FLAT. Handles FVG detection, fill inference, TP1/TP2/SL/BE/EOD management.
broker.py	- Async TradersPost webhook client. All 7 JSON payload formats match HEAD_prod_nq_ny_asia.pine exactly. Live/dry-run auto-derived from webhook URL.
sizing.py	- Position sizing + trade level computation (entry, stop, TP1, TP2, BE, qty). Identical math to Pine Script.
main.py	- CLI entry point. Self-contained production configs (no backtester import needed). Supports --replay, --config.
logging_config.py	- Structured logging to console + rotating files. Separate trades.log, webhooks.log for audit trail.

Usage
# Install dependencies
cd execution && uv sync

# Run (configs with webhooks send live; others are dry-run)
export DATABENTO_API_KEY=db-xxxxx
uv run orb-trader

# Replay historical data for reconciliation
uv run orb-trader --replay ../python/data/raw/NQ_5m.csv --start 2025-01-01
DataBento Plan
Standard Plan ($179/mo) + CME Non-Pro Top-of-Book ($3/mo) = ~$182/mo total. Latency is ~590 microseconds (vs your 5-minute bars = 300,000,000 microseconds). Completely sufficient.

Key Design Decisions
Self-contained for deployment — production configs are embedded in main.py (mirrors config_prod.py), no backtester dependency needed at runtime
Async throughout — asyncio event loop, aiohttp for webhooks, DataBento iterator runs in the main loop
Fill inference from price — matches Pine Script behavior (infer fill when price touches limit level)
One trade per session per day — same as Pine Script hasTradedToday flag
ReplayFeed for reconciliation — feed historical CSVs through the same engine to verify signals match backtest output

To check on it anytime

ssh root@143.110.148.234
journalctl -u orb-trader -f          # live log stream
journalctl -u orb-trader --since today  # today's logs
systemctl status orb-trader           # quick health check