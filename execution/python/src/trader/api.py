"""Dashboard API for the ORB execution service.

Provides REST endpoints and WebSocket streaming for the monitoring frontend.
Runs in-process alongside the trading engine via asyncio.gather().
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from .engine import SessionEngine

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"


# ---------------------------------------------------------------------------
# Dashboard state (shared between engine and API)
# ---------------------------------------------------------------------------

@dataclass
class DashboardState:
    """In-memory state store read by API, written by engines."""

    engines: list[SessionEngine] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    mode: str = "DRY-RUN"
    start_time: float = field(default_factory=time.time)
    _ws_clients: set[WebSocket] = field(default_factory=set, repr=False)

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        dead: list[WebSocket] = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    def on_state_change(self, status: dict) -> None:
        """Called by engines on state transitions. Schedules WS broadcast."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast({
                "type": "status",
                "data": self._build_status(),
            }))
        except RuntimeError:
            pass  # No event loop — skip (e.g. during tests)

    def _build_status(self) -> dict:
        return {
            "engines": [e.status_dict() for e in self.engines],
            "uptime_seconds": round(time.time() - self.start_time),
            "mode": self.mode,
        }


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def parse_trade_log_line(line: str) -> dict | None:
    """Parse a trade log line into a structured dict.

    Format: YYYY-MM-DD HH:MM:SS | SESSION | EVENT | key=value ...
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split(" | ", maxsplit=2)
    if len(parts) < 2:
        return None

    timestamp = parts[0].strip()

    # The rest is "SESSION | EVENT | key=value ..." or "SESSION | EVENT"
    rest = parts[1] if len(parts) == 2 else parts[1] + " | " + parts[2]

    # Split into session and event+details
    rest_parts = rest.split(" | ", maxsplit=1)
    session = rest_parts[0].strip()
    event_and_details = rest_parts[1].strip() if len(rest_parts) > 1 else ""

    # Split event from key=value details
    event_parts = event_and_details.split(" | ", maxsplit=1)
    event = event_parts[0].strip()

    details: dict[str, str] = {}
    detail_str = event_parts[1].strip() if len(event_parts) > 1 else ""

    # Also check if event itself contains key=value pairs after the event name
    # Format: "LONG_SETUP | entry=21450.25 stop=21380.00"
    # or: "FILLED | dir=long entry=21450.25 bar_time=2026-02-23 10:30:00"
    if detail_str:
        for match in re.finditer(r'(\w+)=(\S+)', detail_str):
            details[match.group(1)] = match.group(2)

    # Some events embed key=value in the event string itself
    # e.g. "LONG_SETUP | entry=21450.25 stop=21380.00 ..."
    if not details and " " in event:
        # The event name is the first word
        ev_parts = event.split(None, 1)
        event = ev_parts[0]
        if len(ev_parts) > 1:
            for match in re.finditer(r'(\w+)=(\S+)', ev_parts[1]):
                details[match.group(1)] = match.group(2)

    return {
        "timestamp": timestamp,
        "session": session,
        "event": event,
        "details": details,
    }


def parse_main_log_line(line: str) -> dict | None:
    """Parse a main log line into a structured dict.

    Format: YYYY-MM-DD HH:MM:SS | LEVEL | logger_name | message
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split(" | ", maxsplit=3)
    if len(parts) < 4:
        return None

    return {
        "timestamp": parts[0].strip(),
        "level": parts[1].strip(),
        "logger": parts[2].strip(),
        "message": parts[3].strip(),
    }


def _read_log_lines(
    path: Path,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    level: str = "",
    parser=None,
) -> tuple[list[dict], int]:
    """Read and parse log lines from a file (newest first).

    Returns (entries, total_count).
    """
    if not path.exists():
        return [], 0

    with open(path, "r") as f:
        raw_lines = f.readlines()

    # Parse all lines
    entries = []
    for line in raw_lines:
        parsed = parser(line) if parser else None
        if parsed is not None:
            entries.append(parsed)

    # Filter by level (main log only)
    if level:
        level_upper = level.upper()
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "WARN": 2, "ERROR": 3, "CRITICAL": 4}
        min_level = level_order.get(level_upper, 0)
        entries = [
            e for e in entries
            if level_order.get(e.get("level", "").upper().strip(), 0) >= min_level
        ]

    # Filter by search text
    if search:
        search_lower = search.lower()
        entries = [
            e for e in entries
            if search_lower in str(e).lower()
        ]

    total = len(entries)

    # Reverse for newest-first, then paginate
    entries.reverse()
    entries = entries[offset:offset + limit]

    return entries, total


# ---------------------------------------------------------------------------
# Log tailing for WebSocket
# ---------------------------------------------------------------------------

class LogTailer:
    """Tails log files and broadcasts new lines to WebSocket clients."""

    def __init__(self, state: DashboardState, poll_interval: float = 0.5) -> None:
        self.state = state
        self.poll_interval = poll_interval
        self._positions: dict[str, int] = {}
        self._inodes: dict[str, int] = {}

    async def run(self) -> None:
        """Poll log files forever, broadcasting new lines."""
        trade_log = LOG_DIR / "trades.log"
        main_log = LOG_DIR / "trader.log"

        # Seek to end of existing files
        for path in [trade_log, main_log]:
            if path.exists():
                self._positions[str(path)] = path.stat().st_size
                self._inodes[str(path)] = path.stat().st_ino

        while True:
            await asyncio.sleep(self.poll_interval)

            if not self.state._ws_clients:
                continue

            await self._tail_file(trade_log, "trade_log", parse_trade_log_line)
            await self._tail_file(main_log, "log", parse_main_log_line)

    async def _tail_file(self, path: Path, msg_type: str, parser) -> None:
        """Read new lines from a log file and broadcast."""
        key = str(path)
        if not path.exists():
            return

        try:
            stat = path.stat()
        except OSError:
            return

        # Check for rotation (inode change or file shrunk)
        prev_inode = self._inodes.get(key, 0)
        prev_pos = self._positions.get(key, 0)

        if stat.st_ino != prev_inode or stat.st_size < prev_pos:
            # File was rotated — start from beginning
            prev_pos = 0
            self._inodes[key] = stat.st_ino

        if stat.st_size <= prev_pos:
            return

        try:
            with open(path, "r") as f:
                f.seek(prev_pos)
                new_data = f.read()
                self._positions[key] = f.tell()
        except OSError:
            return

        for line in new_data.splitlines():
            parsed = parser(line)
            if parsed is not None:
                await self.state.broadcast({"type": msg_type, "data": parsed})


# ---------------------------------------------------------------------------
# WebSocket logging handler
# ---------------------------------------------------------------------------

class WebSocketLogHandler(logging.Handler):
    """Logging handler that broadcasts to WebSocket clients."""

    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.state = state

    def emit(self, record: logging.LogRecord) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        msg = {
            "timestamp": self.format(record).split(" | ")[0] if " | " in self.format(record) else "",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        loop.create_task(self.state.broadcast({"type": "log", "data": msg}))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def create_app(state: DashboardState) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="ORB Trader Dashboard", version="0.1.0")

    # CORS for frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── REST endpoints ──────────────────────────────────────────────

    @app.get("/api/status")
    async def get_status():
        return state._build_status()

    @app.get("/api/logs/trades")
    async def get_trade_logs(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        search: str = Query(""),
    ):
        entries, total = _read_log_lines(
            LOG_DIR / "trades.log",
            limit=limit,
            offset=offset,
            search=search,
            parser=parse_trade_log_line,
        )
        return {"entries": entries, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/logs/main")
    async def get_main_logs(
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        level: str = Query(""),
        search: str = Query(""),
    ):
        entries, total = _read_log_lines(
            LOG_DIR / "trader.log",
            limit=limit,
            offset=offset,
            search=search,
            level=level,
            parser=parse_main_log_line,
        )
        return {"entries": entries, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/config")
    async def get_config():
        return {
            "config": state.config,
            "sessions": {e.name: _session_info(e) for e in state.engines},
        }

    # ── WebSocket ───────────────────────────────────────────────────

    @app.websocket("/api/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        state._ws_clients.add(ws)
        logger.info("WebSocket client connected (%d total)", len(state._ws_clients))

        # Send initial status
        try:
            await ws.send_json({"type": "status", "data": state._build_status()})
        except Exception:
            state._ws_clients.discard(ws)
            return

        try:
            while True:
                # Keep connection alive — client can send pings
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            state._ws_clients.discard(ws)
            logger.info("WebSocket client disconnected (%d remaining)", len(state._ws_clients))

    # ── Static files (production) ───────────────────────────────────

    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
        logger.info("Serving frontend from %s", FRONTEND_DIST)

    return app


def _session_info(engine) -> dict:
    """Extract session config info from an engine instance."""
    return {
        "orb_start": engine.orb_start,
        "orb_end": engine.orb_end,
        "entry_start": engine.entry_start,
        "entry_end": engine.entry_end,
        "flat_start": engine.flat_start,
        "flat_end": engine.flat_end,
        "stop_atr_pct": engine.stop_atr_pct,
        "stop_basis": engine.stop_basis,
        "stop_orb_pct": engine.stop_orb_pct,
        "min_gap_atr_pct": engine.min_gap_atr_pct,
        "max_gap_atr_pct": engine.max_gap_atr_pct,
        "gap_filter_basis": engine.gap_filter_basis,
        "min_gap_orb_pct": engine.min_gap_orb_pct,
        "rr": engine.rr,
        "tp1_ratio": engine.tp1_ratio,
        "risk_usd": engine.risk_usd,
        "point_value": engine.point_value,
        "min_qty": engine.min_qty,
        "qty_step": engine.qty_step,
        "be_offset_ticks": engine.be_offset_ticks,
        "min_tick": engine.min_tick,
        "long_only": engine.long_only,
        "icf_enabled": engine.icf_enabled,
        "excluded_dow": engine.excluded_dow,
        "fomc_exclusion": engine.fomc_exclusion,
        "min_stop_pts": engine.min_stop_pts,
        "min_tp1_pts": engine.min_tp1_pts,
    }
