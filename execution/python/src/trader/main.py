"""Entry point for the ORB live execution service.

Usage:
    # Live mode (dry-run by default)
    uv run orb-trader

    # Live mode with real webhooks
    uv run orb-trader --live

    # Replay historical data for reconciliation
    uv run orb-trader --replay /path/to/NQ_5m.csv --start 2025-01-01

    # Custom config file
    uv run orb-trader --config config/live.toml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Default config path relative to execution/ directory
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "live.toml"

# ---------------------------------------------------------------------------
# Instrument definitions (self-contained — no dependency on backtester)
# ---------------------------------------------------------------------------

INSTRUMENTS = {
    "NQ": {"point_value": 20.0, "min_tick": 0.25, "commission": 0.05, "db_symbol": "NQ.FUT"},
    "MNQ": {"point_value": 2.0, "min_tick": 0.25, "commission": 0.05, "db_symbol": "MNQ.FUT"},
    "ES": {"point_value": 50.0, "min_tick": 0.25, "commission": 0.05, "db_symbol": "ES.FUT"},
    "MES": {"point_value": 5.0, "min_tick": 0.25, "commission": 0.05, "db_symbol": "MES.FUT"},
    "YM": {"point_value": 5.0, "min_tick": 1.0, "commission": 0.05, "db_symbol": "YM.FUT"},
    "MYM": {"point_value": 0.5, "min_tick": 1.0, "commission": 0.05, "db_symbol": "MYM.FUT"},
}

# ---------------------------------------------------------------------------
# Session configs (mirrors config_prod.py — self-contained for deployment)
# ---------------------------------------------------------------------------

SESSION_CONFIGS = {
    "NY": {
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "13:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "stop_atr_pct": 6.75,
        "min_gap_atr_pct": 2.5,
        "max_gap_atr_pct": 25.0,
        "rr": 3.5,
        "tp1_ratio": 0.5,
        "instrument": "NQ",
    },
    "Asia": {
        "orb_start": "20:00",
        "orb_end": "20:15",
        "entry_start": "20:15",
        "entry_end": "23:15",
        "flat_start": "06:45",
        "flat_end": "07:00",
        "stop_atr_pct": 5.75,
        "min_gap_atr_pct": 1.25,
        "max_gap_atr_pct": 11.0,
        "rr": 1.75,
        "tp1_ratio": 0.25,
        "instrument": "NQ",
    },
    "LDN": {
        "orb_start": "03:00",
        "orb_end": "03:15",
        "entry_start": "03:15",
        "entry_end": "08:25",
        "flat_start": "08:20",
        "flat_end": "08:25",
        "stop_atr_pct": 3.0,
        "min_gap_atr_pct": 1.25,
        "max_gap_atr_pct": 85.0,
        "rr": 2.75,
        "tp1_ratio": 0.3,
        "instrument": "ES",
    },
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict:
    """Load TOML config file."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    with open(path, "rb") as f:
        return tomllib.load(f)


def _env_or_key(cfg: dict, key: str, env_key: str | None = None) -> str:
    """Get value from config or environment variable."""
    if env_key and env_key in os.environ:
        return os.environ[env_key]
    env_from_cfg = cfg.get(f"{key}_env")
    if env_from_cfg and env_from_cfg in os.environ:
        return os.environ[env_from_cfg]
    return cfg.get(key, "")


# ---------------------------------------------------------------------------
# Build engines from config
# ---------------------------------------------------------------------------

def build_engines(
    config: dict,
    broker,
) -> tuple[list, dict[str, list]]:
    """Build SessionEngine instances from config.

    Returns:
        (engines, symbol_map) where symbol_map maps DataBento symbol
        (e.g. "NQ.FUT") to the list of engines that consume its bars.
    """
    from .engine import SessionEngine

    general = config.get("general", {})
    risk = config.get("risk", {})
    default_instrument = general.get("instrument", "MNQ")

    sessions_enabled = config.get("sessions", {}).get("enabled", ["NY", "Asia"])
    session_overrides = config.get("sessions", {})

    # Half-day and excluded date configs
    half_days = tuple(config.get("dates", {}).get("half_days", [
        "20250703", "20251128", "20251224", "20250109", "20260119",
    ]))
    excluded_dates = tuple(config.get("dates", {}).get("excluded", ["20241218"]))

    engines = []
    # Maps DataBento symbol (e.g. "NQ.FUT") → list of engines
    symbol_map: dict[str, list] = {}

    for sess_name in sessions_enabled:
        sess_cfg = SESSION_CONFIGS.get(sess_name)
        if sess_cfg is None:
            logger.warning("Unknown session '%s', skipping", sess_name)
            continue

        # Allow per-session overrides from TOML
        toml_overrides = session_overrides.get(sess_name.lower(), {})
        merged = {**sess_cfg, **toml_overrides}

        # Per-session instrument (e.g. LDN uses ES, NY/Asia use NQ)
        sess_instrument = merged.get("instrument", default_instrument)
        inst = INSTRUMENTS.get(sess_instrument, INSTRUMENTS["MNQ"])
        db_symbol = inst["db_symbol"]

        engine = SessionEngine(
            name=sess_name,
            broker=broker,
            orb_start=merged["orb_start"],
            orb_end=merged["orb_end"],
            entry_start=merged["entry_start"],
            entry_end=merged["entry_end"],
            flat_start=merged["flat_start"],
            flat_end=merged["flat_end"],
            stop_atr_pct=merged["stop_atr_pct"],
            min_gap_atr_pct=merged["min_gap_atr_pct"],
            max_gap_atr_pct=merged["max_gap_atr_pct"],
            rr=merged["rr"],
            tp1_ratio=merged["tp1_ratio"],
            risk_usd=risk.get("risk_usd", 500),
            point_value=inst["point_value"],
            min_qty=risk.get("min_qty", 1.0),
            qty_step=risk.get("qty_step", 1.0),
            be_offset_ticks=risk.get("be_offset_ticks", 4),
            min_tick=inst["min_tick"],
            excluded_dates=excluded_dates,
            half_days=half_days,
            half_day_flat_start=config.get("dates", {}).get("half_day_flat_start", "12:50"),
            half_day_flat_end=config.get("dates", {}).get("half_day_flat_end", "13:00"),
        )
        engines.append(engine)
        symbol_map.setdefault(db_symbol, []).append(engine)
        logger.info(
            "Session engine created: %s (instrument=%s, feed=%s)",
            sess_name, sess_instrument, db_symbol,
        )

    return engines, symbol_map


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def run_live(config: dict, live: bool = False, api_port: int = 8000) -> None:
    """Run the live execution service."""
    import uvicorn

    from .api import DashboardState, LogTailer, create_app
    from .broker import TradersPostClient
    from .feed import DataBentoFeed

    general = config.get("general", {})
    db_cfg = config.get("databento", {})
    tp_cfg = config.get("traderspost", {})

    dry_run = not live
    instrument_name = general.get("instrument", "MNQ")

    # TradersPost client
    webhook_url = _env_or_key(tp_cfg, "webhook_url")
    if not webhook_url and not dry_run:
        logger.error("TRADERSPOST_WEBHOOK_URL not set — cannot run in live mode")
        sys.exit(1)

    broker = TradersPostClient(
        webhook_url=webhook_url or "https://traderspost.io/api/v1/webhook/dry-run",
        ticker=instrument_name,
        dry_run=dry_run,
    )

    # Build session engines with per-session instrument routing
    engines, symbol_map = build_engines(config, broker)
    if not engines:
        logger.error("No session engines configured")
        sys.exit(1)

    # Dashboard API
    mode = "LIVE" if not dry_run else "DRY-RUN"
    dashboard = DashboardState(engines=engines, config=config, mode=mode)

    # Wire state change callback into each engine
    for engine in engines:
        engine.on_state_change = dashboard.on_state_change

    app = create_app(dashboard)
    tailer = LogTailer(dashboard)

    uvi_config = uvicorn.Config(
        app, host="0.0.0.0", port=api_port, log_level="warning",
    )
    server = uvicorn.Server(uvi_config)

    # Bar callback — route 5m bars to engines for signal detection (ORB, FVG)
    async def on_bar(symbol: str, bar, daily_atr: float):
        target_engines = symbol_map.get(symbol, [])
        for engine in target_engines:
            await engine.on_bar(bar, daily_atr)

    # Tick callback — route 1s bars to engines for fill/exit management
    async def on_tick(symbol: str, tick, daily_atr: float):
        target_engines = symbol_map.get(symbol, [])
        for engine in target_engines:
            await engine.on_tick(tick, daily_atr)

    # DataBento feed — subscribe to all symbols needed by active engines
    api_key = _env_or_key(db_cfg, "api_key")
    feed_symbols = list(symbol_map.keys())

    feed = DataBentoFeed(
        api_key=api_key or None,
        symbols=feed_symbols,
        dataset=db_cfg.get("dataset", "GLBX.MDP3"),
        on_bar=on_bar,
        on_tick=on_tick,
        atr_length=config.get("general", {}).get("atr_length", 14),
    )

    # Seed ATR from historical daily bars so it's ready on first live bar
    feed.warm_up(lookback_days=30)

    logger.info(
        "Starting ORB Trader [%s] — feeds=%s sessions=%s api=:%d",
        mode, feed_symbols,
        [(e.name, sym) for sym, engs in symbol_map.items() for e in engs],
        api_port,
    )

    try:
        await asyncio.gather(
            feed.run(),
            server.serve(),
            tailer.run(),
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await broker.close()
        server.should_exit = True


async def run_replay(config: dict, csv_path: str, start: str | None, end: str | None) -> None:
    """Replay historical bars through the engine."""
    from .broker import TradersPostClient
    from .feed import ReplayFeed

    general = config.get("general", {})
    instrument_name = general.get("instrument", "MNQ")

    broker = TradersPostClient(
        webhook_url="",
        ticker=instrument_name,
        dry_run=True,
    )

    engines, _symbol_map = build_engines(config, broker)

    async def on_bar(bar, daily_atr):
        for engine in engines:
            await engine.on_bar(bar, daily_atr)

    feed = ReplayFeed(
        csv_path=csv_path,
        on_bar=on_bar,
        atr_length=config.get("general", {}).get("atr_length", 14),
        start_date=start,
        end_date=end,
    )

    logger.info(
        "Replaying %s — sessions=%s start=%s end=%s",
        csv_path, [e.name for e in engines], start or "all", end or "all",
    )
    await feed.run()
    logger.info("Replay complete")

    # Print final status
    for engine in engines:
        logger.info("Final state: %s", engine.status_dict())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli() -> None:
    """Command-line entry point."""
    from dotenv import load_dotenv
    from .logging_config import setup_logging

    # Load .env file from execution/ directory (secrets stay out of git)
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)

    parser = argparse.ArgumentParser(
        description="ORB Trader — live execution service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run orb-trader                           # Dry-run with default config
  uv run orb-trader --live                    # Live mode (sends real webhooks)
  uv run orb-trader --replay NQ_5m.csv       # Replay historical data
  uv run orb-trader --config my_config.toml   # Custom config
""",
    )

    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help="Path to TOML config file",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Enable live mode (sends real webhooks to TradersPost)",
    )
    parser.add_argument(
        "--replay", type=str, default=None,
        help="Replay historical 5m CSV instead of live streaming",
    )
    parser.add_argument(
        "--start", type=str, default=None,
        help="Start date for replay (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="End date for replay (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Dashboard API port (default: 8000)",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )

    args = parser.parse_args()

    setup_logging(level=args.log_level)

    # Load config
    if args.config.exists():
        config = load_config(args.config)
        logger.info("Loaded config from %s", args.config)
    else:
        logger.warning("Config file %s not found — using defaults", args.config)
        config = {}

    if args.replay:
        asyncio.run(run_replay(config, args.replay, args.start, args.end))
    else:
        asyncio.run(run_live(config, live=args.live, api_port=args.port))


if __name__ == "__main__":
    cli()
