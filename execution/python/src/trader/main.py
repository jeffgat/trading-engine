"""Entry point for the ORB live execution service.

Runs the 5-leg combined longs portfolio:
  NQ NY R11, NQ Asia R9, GC NY R3, ES NY Final, ES Asia Final

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
from datetime import datetime
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
    "GC": {"point_value": 100.0, "min_tick": 0.10, "commission": 0.05, "db_symbol": "GC.FUT"},
    "MGC": {"point_value": 10.0, "min_tick": 0.10, "commission": 0.05, "db_symbol": "MGC.FUT"},
    "YM": {"point_value": 5.0, "min_tick": 1.0, "commission": 0.05, "db_symbol": "YM.FUT"},
    "MYM": {"point_value": 0.5, "min_tick": 1.0, "commission": 0.05, "db_symbol": "MYM.FUT"},
}

# Signal instrument → execution instrument mapping.
# We subscribe to full-size contracts (NQ, ES, GC) for signal data via DataBento
# but execute on micro contracts (MNQ, MES, MGC) via TradersPost.
SIGNAL_TO_EXEC: dict[str, str] = {
    "NQ": "MNQ",
    "ES": "MES",
    "GC": "MGC",
    "YM": "MYM",
    # Micros map to themselves
    "MNQ": "MNQ",
    "MES": "MES",
    "MGC": "MGC",
    "MYM": "MYM",
}

# ---------------------------------------------------------------------------
# 5-leg combined longs portfolio session configs
# From COMBINED_LONGS_5LEG_PINE_SPEC.md
# ---------------------------------------------------------------------------

SESSION_CONFIGS = {
    # --- NQ NY R11 (ATR-based stop, Friday exclusion) ---
    "NQ_NY": {
        "orb_start": "09:30",
        "orb_end": "09:50",
        "entry_start": "09:50",
        "entry_end": "12:00",
        "flat_start": "15:30",
        "flat_end": "16:00",
        "stop_atr_pct": 7.0,
        "stop_basis": "atr",
        "min_gap_atr_pct": 2.5,
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "rr": 3.5,
        "tp1_ratio": 0.4,
        "instrument": "NQ",
        "atr_length": 12,
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": 4,  # Friday (Monday=0..Sunday=6)
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- NQ Asia R9 (ORB-based stop, Tuesday exclusion) ---
    "NQ_Asia": {
        "orb_start": "20:00",
        "orb_end": "20:15",
        "entry_start": "20:15",
        "entry_end": "22:30",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "stop_atr_pct": 0.0,  # not used — stop is ORB-based
        "stop_basis": "orb",
        "stop_orb_pct": 100.0,
        "min_gap_atr_pct": 0.0,  # not used — gap filter is ORB-based
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "orb",
        "min_gap_orb_pct": 10.0,
        "rr": 6.0,
        "tp1_ratio": 0.3,
        "instrument": "NQ",
        "atr_length": 5,  # only for warmup, not used in stop/gap
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": 1,  # Tuesday (Monday=0..Sunday=6)
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- GC NY R3 (ATR-based stop, Friday+FOMC exclusion, ICF ON) ---
    "GC_NY": {
        "orb_start": "09:30",
        "orb_end": "09:40",  # 8m ORB → 10m approx on 5m chart (2 bars)
        "entry_start": "09:40",
        "entry_end": "12:00",
        "flat_start": "13:30",
        "flat_end": "16:00",
        "stop_atr_pct": 4.5,
        "stop_basis": "atr",
        "min_gap_atr_pct": 3.0,
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "rr": 9.0,
        "tp1_ratio": 0.35,
        "instrument": "GC",
        "atr_length": 7,
        "long_only": True,
        "icf_enabled": True,
        "excluded_dow": 4,  # Friday
        "fomc_exclusion": True,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- ES NY Final (ATR-based stop, Thursday exclusion, dual floor) ---
    "ES_NY": {
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "13:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "stop_atr_pct": 5.0,
        "stop_basis": "atr",
        "min_gap_atr_pct": 0.25,
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "rr": 5.0,
        "tp1_ratio": 0.2,
        "instrument": "ES",
        "atr_length": 7,
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": 3,  # Thursday
        "fomc_exclusion": False,
        "min_stop_pts": 3.0,
        "min_tp1_pts": 3.0,
    },
    # --- ES Asia Final (ORB-based stop, ATR-based gap, no DOW excl, dual floor) ---
    "ES_Asia": {
        "orb_start": "20:00",
        "orb_end": "20:15",
        "entry_start": "20:15",
        "entry_end": "03:00",
        "flat_start": "07:00",
        "flat_end": "07:00",  # flat_start == flat_end → instant flat at 07:00
        "stop_atr_pct": 0.0,  # not used — stop is ORB-based
        "stop_basis": "orb",
        "stop_orb_pct": 125.0,
        "min_gap_atr_pct": 0.5,  # gap filter IS ATR-based (hybrid)
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "min_gap_orb_pct": 0.0,
        "rr": 1.5,
        "tp1_ratio": 0.7,
        "instrument": "ES",
        "atr_length": 14,
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": None,  # no DOW exclusion — trades every day
        "fomc_exclusion": False,
        "min_stop_pts": 3.0,
        "min_tp1_pts": 3.0,
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
) -> tuple[list, dict[str, list], dict[str, int]]:
    """Build SessionEngine instances from config.

    Returns:
        (engines, symbol_map, atr_lengths) where:
        - symbol_map maps DataBento symbol (e.g. "NQ.FUT") to engines.
        - atr_lengths maps DataBento symbol to the ATR period for that feed.
    """
    from .engine import SessionEngine

    general = config.get("general", {})
    risk = config.get("risk", {})

    sessions_enabled = config.get("sessions", {}).get("enabled", [
        "NQ_NY", "NQ_Asia", "GC_NY", "ES_NY", "ES_Asia",
    ])
    session_overrides = config.get("sessions", {})

    # Half-day and excluded date configs
    half_days = tuple(config.get("dates", {}).get("half_days", [
        "20250703", "20251128", "20251224", "20250109", "20260119",
    ]))
    excluded_dates = tuple(config.get("dates", {}).get("excluded", []))

    engines = []
    symbol_map: dict[str, list] = {}
    # Track ATR length per feed symbol (use the longest if multiple sessions share a feed)
    atr_lengths: dict[str, int] = {}

    for sess_name in sessions_enabled:
        sess_cfg = SESSION_CONFIGS.get(sess_name)
        if sess_cfg is None:
            logger.warning("Unknown session '%s', skipping", sess_name)
            continue

        # Allow per-session overrides from TOML (keyed by lowercase name)
        toml_key = sess_name.lower().replace("_", ".")
        toml_overrides = session_overrides.get(toml_key, {})
        merged = {**sess_cfg, **toml_overrides}

        # Per-session instrument (signal data source) and execution ticker
        sess_instrument = merged.get("instrument", "NQ")
        inst = INSTRUMENTS.get(sess_instrument, INSTRUMENTS["NQ"])
        db_symbol = inst["db_symbol"]

        # Resolve execution ticker: use micro contract for order routing
        exec_ticker = merged.get("exec_ticker") or SIGNAL_TO_EXEC.get(sess_instrument, sess_instrument)
        exec_inst = INSTRUMENTS.get(exec_ticker, inst)

        # Track ATR length per symbol (use max of all sessions for that symbol)
        sess_atr_length = merged.get("atr_length", 14)
        atr_lengths[db_symbol] = max(atr_lengths.get(db_symbol, 0), sess_atr_length)

        engine = SessionEngine(
            name=sess_name,
            broker=broker,
            exec_ticker=exec_ticker,
            orb_start=merged["orb_start"],
            orb_end=merged["orb_end"],
            entry_start=merged["entry_start"],
            entry_end=merged["entry_end"],
            flat_start=merged["flat_start"],
            flat_end=merged["flat_end"],
            stop_atr_pct=merged.get("stop_atr_pct", 0.0),
            min_gap_atr_pct=merged.get("min_gap_atr_pct", 0.0),
            max_gap_atr_pct=merged.get("max_gap_atr_pct", 0),
            rr=merged["rr"],
            tp1_ratio=merged["tp1_ratio"],
            risk_usd=risk.get("risk_usd", 250),
            point_value=exec_inst["point_value"],
            min_qty=risk.get("min_qty", 1.0),
            qty_step=risk.get("qty_step", 1.0),
            be_offset_ticks=risk.get("be_offset_ticks", 0),
            min_tick=exec_inst["min_tick"],
            stop_basis=merged.get("stop_basis", "atr"),
            stop_orb_pct=merged.get("stop_orb_pct", 0.0),
            gap_filter_basis=merged.get("gap_filter_basis", "atr"),
            min_gap_orb_pct=merged.get("min_gap_orb_pct", 0.0),
            min_stop_pts=merged.get("min_stop_pts", 0.0),
            min_tp1_pts=merged.get("min_tp1_pts", 0.0),
            max_single_risk_usd=risk.get("max_single_risk_usd", 500.0),
            long_only=merged.get("long_only", True),
            icf_enabled=merged.get("icf_enabled", False),
            excluded_dow=merged.get("excluded_dow"),
            fomc_exclusion=merged.get("fomc_exclusion", False),
            excluded_dates=excluded_dates,
            half_days=half_days,
            half_day_flat_start=config.get("dates", {}).get("half_day_flat_start", "12:50"),
            half_day_flat_end=config.get("dates", {}).get("half_day_flat_end", "13:00"),
        )
        engines.append(engine)
        symbol_map.setdefault(db_symbol, []).append(engine)
        logger.info(
            "Session engine created: %s (signal=%s, exec=%s, feed=%s, stop=%s, atr=%d)",
            sess_name, sess_instrument, exec_ticker, db_symbol,
            merged.get("stop_basis", "atr"), sess_atr_length,
        )

    return engines, symbol_map, atr_lengths


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def run_live(config: dict, live: bool = False, api_port: int = 8000) -> None:
    """Run the live execution service."""
    import uvicorn

    from .api import DashboardState, LogTailer, create_app
    from .broker import TradersPostClient
    from .feed import ET, DataBentoFeed

    general = config.get("general", {})
    db_cfg = config.get("databento", {})
    tp_cfg = config.get("traderspost", {})

    dry_run = not live

    # TradersPost client (default ticker is a fallback — each session overrides
    # with its own exec_ticker derived from SIGNAL_TO_EXEC mapping)
    webhook_url = _env_or_key(tp_cfg, "webhook_url")
    if not webhook_url and not dry_run:
        logger.error("TRADERSPOST_WEBHOOK_URL not set — cannot run in live mode")
        sys.exit(1)

    broker = TradersPostClient(
        webhook_url=webhook_url or "https://traderspost.io/api/v1/webhook/dry-run",
        ticker=general.get("instrument", "MNQ"),
        dry_run=dry_run,
    )

    # Build session engines with per-session instrument routing
    engines, symbol_map, atr_lengths = build_engines(config, broker)
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

    # Use the max ATR length across all sessions for the global feed ATR
    # (individual session ATR needs are handled by the per-symbol ATR calculator)
    global_atr_length = max(atr_lengths.values()) if atr_lengths else 14

    feed = DataBentoFeed(
        api_key=api_key or None,
        symbols=feed_symbols,
        dataset=db_cfg.get("dataset", "GLBX.MDP3"),
        on_bar=on_bar,
        on_tick=on_tick,
        atr_length=global_atr_length,
    )

    # Seed ATR from historical daily bars so it's ready on first live bar
    feed.warm_up(lookback_days=30)

    # Seed engines with warmup ATR values so the dashboard shows ATR
    # immediately (before the first live bar arrives for that symbol).
    atr_values = feed.get_atr_values()
    for symbol, target_engines in symbol_map.items():
        atr = atr_values.get(symbol, 0.0)
        if atr > 0:
            for engine in target_engines:
                engine._daily_atr = atr

    # recover current-day opening ranges from recent intraday history so
    # sessions can continue scanning after service restarts.
    intraday_5m = feed.preload_intraday_5m(lookback_hours=18)
    now_et = datetime.now(tz=ET)
    recovered = 0
    for symbol, target_engines in symbol_map.items():
        bars = intraday_5m.get(symbol, [])
        for engine in target_engines:
            if engine.recover_opening_range(bars, now_et):
                recovered += 1
    logger.info(
        "startup recovery complete: recovered_or=%d total_sessions=%d",
        recovered,
        len(engines),
    )

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

    broker = TradersPostClient(
        webhook_url="",
        ticker="MNQ",
        dry_run=True,
    )

    engines, _symbol_map, atr_lengths = build_engines(config, broker)

    global_atr_length = max(atr_lengths.values()) if atr_lengths else 14

    async def on_bar(bar, daily_atr):
        for engine in engines:
            await engine.on_bar(bar, daily_atr)

    feed = ReplayFeed(
        csv_path=csv_path,
        on_bar=on_bar,
        atr_length=global_atr_length,
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
        description="ORB Trader — 5-leg combined longs execution service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run orb-trader                           # Dry-run with default config
  uv run orb-trader --live                    # Live mode (sends real webhooks)
  uv run orb-trader --replay NQ_5m.csv       # Replay historical data
  uv run orb-trader --config my_config.toml   # Custom config

5-Leg Portfolio:
  NQ_NY   — NQ NY R11  (ATR stop, rr=3.5,  Fri excl)
  NQ_Asia — NQ Asia R9 (ORB stop, rr=6.0,  Tue excl)
  GC_NY   — GC NY R3   (ATR stop, rr=9.0,  Fri+FOMC excl, ICF)
  ES_NY   — ES NY      (ATR stop, rr=5.0,  Thu excl, dual floor)
  ES_Asia — ES Asia    (ORB stop, rr=1.5,  no DOW excl, dual floor)
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
