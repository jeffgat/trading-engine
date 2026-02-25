"""Logging configuration for the execution service.

Writes structured logs to both console and rotating file.
Trade events get a separate log file for reconciliation.
"""

from __future__ import annotations

import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


class _ETFormatter(logging.Formatter):
    """Formatter that renders timestamps in Eastern Time."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        ct = datetime.fromtimestamp(record.created, tz=ET)
        if datefmt:
            return ct.strftime(datefmt)
        return ct.isoformat()

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with console + file handlers."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = _ETFormatter(
        "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # Rotating file handler — main log
    main_file = logging.handlers.RotatingFileHandler(
        LOG_DIR / "trader.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    main_file.setFormatter(fmt)
    root.addHandler(main_file)

    # Separate trade log — one line per webhook/state change
    trade_logger = logging.getLogger("trader.trades")
    trade_fmt = _ETFormatter(
        "%(asctime)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    trade_file = logging.handlers.RotatingFileHandler(
        LOG_DIR / "trades.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
    )
    trade_file.setFormatter(trade_fmt)
    trade_logger.addHandler(trade_file)
    trade_logger.propagate = True  # also goes to main log
