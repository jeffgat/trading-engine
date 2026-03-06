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
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .overrides import EDITABLE_FIELDS, load_overrides, save_overrides, validate_fields

if TYPE_CHECKING:
    from .engine import ORBEngine, TradeRecord

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"

# Known execution config names (used to distinguish config tag from asset tag in log parsing)
_KNOWN_CONFIGS: set[str] = set()


# ---------------------------------------------------------------------------
# Dashboard state (shared between engine and API)
# ---------------------------------------------------------------------------

@dataclass
class DashboardState:
    """In-memory state store read by API, written by engines."""

    engines_by_config: dict[str, list] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    mode: str = "DRY-RUN"
    start_time: float = field(default_factory=time.time)
    trade_history: list[TradeRecord] = field(default_factory=list)
    exec_configs: dict[str, dict] = field(default_factory=dict)
    multi_brokers_by_config: dict[str, Any] = field(default_factory=dict)
    _ws_clients: set[WebSocket] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        # Register config names for log parsing
        _KNOWN_CONFIGS.update(self.engines_by_config.keys())

    @property
    def all_engines(self) -> list:
        """Flat list of all engines across all configs."""
        return [e for engines in self.engines_by_config.values() for e in engines]

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

    def record_trade(self, record: TradeRecord) -> None:
        """Called by engines on trade exit. Stores record for G5 gate queries."""
        self.trade_history.append(record)
        logger.info(
            "Trade recorded: [%s] %s %s exit=%s tp1=%s",
            record.config_name, record.session, record.date,
            record.exit_type, record.tp1_hit,
        )
        # Persist to disk for crash recovery
        from .checkpoint import save_trade_history
        save_trade_history(self.trade_history)

    def asia_tp1_hit_for_date(self, date: str, config_name: str = "") -> bool:
        """Check if any Asia session hit TP1 on the given date (for G5 gate).

        When config_name is provided, only checks trades from that config.
        """
        for r in self.trade_history:
            if r.date == date and r.tp1_hit and r.session in ("NQ_Asia", "ES_Asia"):
                if config_name and r.config_name != config_name:
                    continue
                return True
        return False

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
            "configs": {
                cfg_name: {
                    "engines": [e.status_dict() for e in engines],
                }
                for cfg_name, engines in self.engines_by_config.items()
            },
            "uptime_seconds": round(time.time() - self.start_time),
            "mode": self.mode,
        }


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def parse_trade_log_line(line: str) -> dict | None:
    """Parse a trade log line into a structured dict.

    Formats (new — with config tag):
      - YYYY-MM-DD HH:MM:SS | CONFIG | ASSET | SESSION | EVENT | key=value ...

    Legacy formats (backward-compatible):
      - YYYY-MM-DD HH:MM:SS | SESSION | EVENT | key=value ...
      - YYYY-MM-DD HH:MM:SS | ASSET | SESSION | EVENT | key=value ...
    """
    line = line.strip()
    if not line:
        return None

    parts = [part.strip() for part in line.split(" | ")]
    if len(parts) < 3:
        return None

    timestamp = parts[0]
    config = None
    asset = ""

    # Detect config tag: known config name (FAST, SLOW, DEFAULT) or uppercase
    # non-asset string in parts[1]
    remaining = parts[1:]
    if remaining and remaining[0].upper() in _KNOWN_CONFIGS | {"DEFAULT"}:
        config = remaining[0].upper()
        remaining = remaining[1:]

    # Detect asset tag
    if remaining and remaining[0].lower() in {"nq", "es", "gc"}:
        asset = remaining[0].lower()
        remaining = remaining[1:]

    if len(remaining) < 2:
        return None

    session = remaining[0]
    event = remaining[1]
    detail_str = " | ".join(remaining[2:]) if len(remaining) > 2 else ""

    details: dict[str, str] = {}

    if detail_str:
        for match in re.finditer(r'(\w+)=(\S+)', detail_str):
            details[match.group(1)] = match.group(2)

    # Some events embed key=value in the event string itself
    if not details and " " in event:
        ev_parts = event.split(None, 1)
        event = ev_parts[0]
        if len(ev_parts) > 1:
            for match in re.finditer(r'(\w+)=(\S+)', ev_parts[1]):
                details[match.group(1)] = match.group(2)

    return {
        "timestamp": timestamp,
        "config": config,
        "asset": asset or None,
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


def parse_webhook_log_line(line: str) -> dict | None:
    """Parse a webhook log line into a structured dict.

    Format: YYYY-MM-DD HH:MM:SS | CONFIG[ACCOUNT] | STATUS | HTTP_CODE | LATENCYms | PAYLOAD
    DRY-RUN: YYYY-MM-DD HH:MM:SS | CONFIG[ACCOUNT] | DRY-RUN | LATENCYms | PAYLOAD
    """
    line = line.strip()
    if not line:
        return None

    parts = [p.strip() for p in line.split(" | ", maxsplit=5)]
    if len(parts) < 4:
        return None

    result: dict = {
        "timestamp": parts[0],
        "account": parts[1],
        "status": parts[2],  # OK, FAILED, DRY-RUN, ERROR
    }

    if parts[2] == "DRY-RUN":
        result["latency"] = parts[3] if len(parts) > 3 else ""
        result["payload"] = parts[4] if len(parts) > 4 else ""
    else:
        result["http_code"] = parts[3] if len(parts) > 3 else ""
        result["latency"] = parts[4] if len(parts) > 4 else ""
        result["payload"] = parts[5] if len(parts) > 5 else ""

    return result


def _read_log_lines(
    path: Path,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    level: str = "",
    config_filter: str = "",
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

    # Filter by config name (trade log only)
    if config_filter:
        config_upper = config_filter.upper()
        entries = [e for e in entries if e.get("config", "").upper() == config_upper]

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
        webhook_log = LOG_DIR / "webhooks.log"

        # Seek to end of existing files
        for path in [trade_log, main_log, webhook_log]:
            if path.exists():
                self._positions[str(path)] = path.stat().st_size
                self._inodes[str(path)] = path.stat().st_ino

        while True:
            await asyncio.sleep(self.poll_interval)

            if not self.state._ws_clients:
                continue

            await self._tail_file(trade_log, "trade_log", parse_trade_log_line)
            await self._tail_file(main_log, "log", parse_main_log_line)
            await self._tail_file(webhook_log, "webhook_log", parse_webhook_log_line)

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
        config: str = Query("", description="Filter by execution config name"),
    ):
        entries, total = _read_log_lines(
            LOG_DIR / "trades.log",
            limit=limit,
            offset=offset,
            search=search,
            config_filter=config,
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

    @app.get("/api/logs/webhooks")
    async def get_webhook_logs(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        search: str = Query(""),
        account: str = Query("", description="Filter by account/config name"),
    ):
        entries, total = _read_log_lines(
            LOG_DIR / "webhooks.log",
            limit=limit,
            offset=offset,
            search=search if not account else account,
            parser=parse_webhook_log_line,
        )
        return {"entries": entries, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/trades/history")
    async def get_trade_history(
        session: str = Query("", description="Filter by session name"),
        config: str = Query("", description="Filter by execution config name"),
        limit: int = Query(100, ge=1, le=1000),
    ):
        records = state.trade_history
        if config:
            records = [r for r in records if r.config_name == config]
        if session:
            records = [r for r in records if r.session == session]
        # newest first, then limit
        records = list(reversed(records))[:limit]
        from dataclasses import asdict
        return {"trades": [asdict(r) for r in records], "total": len(state.trade_history)}

    @app.get("/api/config")
    async def get_config():
        overrides = load_overrides()
        all_engines = state.all_engines
        risk_cfg = state.config.get("risk", {})
        return {
            "config": state.config,
            "baseline_r": risk_cfg.get("baseline_r", 250),
            "sessions": {
                f"{e.config_name}:{e.name}" if e.config_name else e.name: _session_info(e)
                for e in all_engines
            },
            "overrides": {
                e.name: overrides.get(e.name, {}) for e in all_engines
            },
            "defaults": {
                e.name: _defaults_for_session(e.name) for e in all_engines
            },
            "exec_configs": state.exec_configs,
        }

    # ── Config override endpoints ──────────────────────────────────

    @app.patch("/api/config/sessions/{session_name}")
    async def update_session_config(session_name: str, body: SessionOverrideRequest):
        from .overrides import LSI_EDITABLE_FIELDS
        engine = _find_engine(state, session_name)
        if engine is None:
            raise HTTPException(404, f"Session '{session_name}' not found")

        allowed = LSI_EDITABLE_FIELDS if _is_lsi_engine(engine) else None
        valid_fields, errors = validate_fields(body.overrides, allowed=allowed)
        if errors:
            raise HTTPException(422, detail=errors)
        if not valid_fields:
            raise HTTPException(400, "No valid fields to update")

        # Safety: reject if engine is mid-trade (covers both ORBEngine and LSIEngine states)
        blocked_states = {"armed_limit", "filled", "managing"}
        if engine._state.value in blocked_states:
            raise HTTPException(
                409,
                f"Session '{session_name}' is in state '{engine._state.value}'. "
                "Config changes are blocked while a trade is active.",
            )

        # Load, merge, persist
        overrides = load_overrides()
        session_overrides = overrides.get(session_name, {})
        session_overrides.update(valid_fields)

        # Remove overrides that match the default value (keep sparse)
        defaults = _defaults_for_session(session_name)
        session_overrides = {
            k: v for k, v in session_overrides.items() if defaults.get(k) != v
        }

        if session_overrides:
            overrides[session_name] = session_overrides
        elif session_name in overrides:
            del overrides[session_name]
        save_overrides(overrides)

        # Apply to in-memory engine
        _apply_overrides_to_engine(engine, valid_fields)

        await state.broadcast({"type": "config_update", "data": {
            "session": session_name,
            "config": _session_info(engine),
            "overrides": overrides.get(session_name, {}),
        }})

        return {
            "session": session_name,
            "config": _session_info(engine),
            "overrides": overrides.get(session_name, {}),
        }

    # ── Exec config webhook endpoints ──────────────────────────────

    @app.put("/api/config/exec/{config_name}/webhooks")
    async def update_exec_webhooks(config_name: str, body: "ExecWebhooksRequest"):
        """Replace the webhooks list for an execution config and persist to disk."""
        from .main import EXEC_CONFIGS_PATH, WebhookEntry, load_exec_configs, save_exec_configs
        import json

        configs = load_exec_configs()
        target = next((c for c in configs if c.name == config_name), None)
        if target is None:
            raise HTTPException(404, f"Exec config '{config_name}' not found")

        # Validate — reject empty URLs
        new_webhooks = []
        for w in body.webhooks:
            url = (w.get("url") or "").strip()
            label = (w.get("label") or "").strip()
            if not url:
                raise HTTPException(422, "Each webhook must have a non-empty url")
            new_webhooks.append(WebhookEntry(url=url, label=label))

        target.webhooks = new_webhooks
        save_exec_configs(configs)

        # Update metadata so the API reflects the change immediately
        state.exec_configs[config_name]["webhooks"] = [
            {"url": w.url, "label": w.label, "paused": w.paused, "multiplier": w.multiplier}
            for w in new_webhooks
        ]

        await state.broadcast({"type": "config_update", "data": {
            "exec_config": config_name,
            "webhooks": state.exec_configs[config_name]["webhooks"],
        }})

        return {"config": config_name, "webhooks": state.exec_configs[config_name]["webhooks"]}

    @app.patch("/api/config/exec/{config_name}/webhooks/{webhook_index}")
    async def patch_webhook(config_name: str, webhook_index: int, body: "WebhookPatchRequest"):
        """Update pause state or multiplier for a single webhook entry."""
        from .main import load_exec_configs, save_exec_configs

        if config_name not in state.exec_configs:
            raise HTTPException(404, f"Exec config '{config_name}' not found")

        wh_list = state.exec_configs[config_name].get("webhooks", [])
        if webhook_index < 0 or webhook_index >= len(wh_list):
            raise HTTPException(404, f"Webhook index {webhook_index} out of range")

        if body.multiplier is not None and body.multiplier <= 0:
            raise HTTPException(422, "multiplier must be > 0")

        # Persist to disk
        configs = load_exec_configs()
        target = next((c for c in configs if c.name == config_name), None)
        if target and webhook_index < len(target.webhooks):
            wh = target.webhooks[webhook_index]
            if body.paused is not None:
                wh.paused = body.paused
            if body.multiplier is not None:
                wh.multiplier = body.multiplier
            save_exec_configs(configs)

        # Apply to live runtime broker (no restart needed)
        multi_broker = state.multi_brokers_by_config.get(config_name)
        if multi_broker and webhook_index < len(multi_broker._brokers):
            live_broker = multi_broker._brokers[webhook_index]
            if body.paused is not None:
                live_broker.paused = body.paused
            if body.multiplier is not None:
                live_broker.multiplier = body.multiplier

        # Update in-memory metadata
        wh_meta = state.exec_configs[config_name]["webhooks"][webhook_index]
        if body.paused is not None:
            wh_meta["paused"] = body.paused
        if body.multiplier is not None:
            wh_meta["multiplier"] = body.multiplier

        await state.broadcast({"type": "accounts_update", "data": {
            "exec_config": config_name,
            "webhooks": state.exec_configs[config_name]["webhooks"],
        }})

        return {"config": config_name, "webhook_index": webhook_index, "webhook": wh_meta}

    @app.post("/api/config/exec/{config_name}/webhooks/{webhook_index}/flatten")
    async def flatten_webhook(config_name: str, webhook_index: int):
        """Send a flatten payload to a single specific webhook account."""
        if config_name not in state.exec_configs:
            raise HTTPException(404, f"Exec config '{config_name}' not found")

        multi_broker = state.multi_brokers_by_config.get(config_name)
        if multi_broker is None:
            raise HTTPException(404, f"No broker found for config '{config_name}'")

        if webhook_index < 0 or webhook_index >= len(multi_broker._brokers):
            raise HTTPException(404, f"Webhook index {webhook_index} out of range")

        broker = multi_broker._brokers[webhook_index]

        # Collect distinct exec tickers from all engines in this config
        cfg_engines = state.engines_by_config.get(config_name, [])
        tickers = list({e.exec_ticker for e in cfg_engines}) or ["MNQ"]

        for t in tickers:
            await broker.send_flatten(ticker=t)

        label = (state.exec_configs[config_name].get("webhooks", [{}])[webhook_index] or {}).get("label", "")
        logger.info("[%s] Per-account flatten sent to index=%d label=%s tickers=%s", config_name, webhook_index, label, tickers)

        return {"config": config_name, "webhook_index": webhook_index, "tickers": tickers, "status": "sent"}

    @app.delete("/api/config/sessions/{session_name}")
    async def reset_session_config(session_name: str):
        engine = _find_engine(state, session_name)
        if engine is None:
            raise HTTPException(404, f"Session '{session_name}' not found")

        if engine._state.value in {"armed_limit", "filled", "managing"}:
            raise HTTPException(
                409, "Cannot reset config while a trade is active",
            )

        # Remove overrides for this session
        overrides = load_overrides()
        if session_name in overrides:
            del overrides[session_name]
            save_overrides(overrides)

        # Reset engine fields to defaults
        _apply_defaults_to_engine(engine, session_name, state.config)

        await state.broadcast({"type": "config_update", "data": {
            "session": session_name,
            "config": _session_info(engine),
            "overrides": {},
        }})

        return {
            "session": session_name,
            "config": _session_info(engine),
            "overrides": {},
        }

    # ── Engine pause/resume endpoints ─────────────────────────────

    @app.post("/api/engines/{session_name}/pause")
    async def pause_engine(session_name: str, config: str | None = None):
        """Pause a single engine leg. Sends cancel/flatten if mid-trade."""
        engine = _find_engine(state, session_name, config)
        if engine is None:
            raise HTTPException(404, f"Engine '{session_name}' not found")
        if engine.paused:
            return {"session": session_name, "paused": True, "action": "already_paused"}

        # Safe cleanup: cancel pending orders or flatten open positions
        state_val = engine._state.value
        action_taken = "none"

        if state_val == "armed_limit":
            await engine.broker.send_cancel(ticker=engine.exec_ticker)
            action_taken = "cancelled"
            logger.info("[%s] Pause: cancelled pending order", engine.name)
        elif state_val in ("managing", "filled"):
            await engine.broker.send_flatten(ticker=engine.exec_ticker)
            action_taken = "flattened"
            logger.info("[%s] Pause: flattened open position", engine.name)

        engine.paused = True
        logger.info("[%s] Engine paused (action=%s)", engine.name, action_taken)

        # Trigger status broadcast so frontend updates immediately
        state.on_state_change(engine.status_dict())

        return {"session": session_name, "paused": True, "action": action_taken}

    @app.post("/api/engines/{session_name}/resume")
    async def resume_engine(session_name: str, config: str | None = None):
        """Resume a paused engine leg."""
        engine = _find_engine(state, session_name, config)
        if engine is None:
            raise HTTPException(404, f"Engine '{session_name}' not found")
        if not engine.paused:
            return {"session": session_name, "paused": False, "action": "already_running"}

        engine.paused = False
        logger.info("[%s] Engine resumed", engine.name)

        # Trigger status broadcast
        state.on_state_change(engine.status_dict())

        return {"session": session_name, "paused": False}

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


class SessionOverrideRequest(BaseModel):
    """Sparse dict of fields to override for a session."""

    overrides: dict[str, Any]


class ExecWebhooksRequest(BaseModel):
    """Replacement webhooks list for an execution config."""

    webhooks: list[dict[str, Any]]


class WebhookPatchRequest(BaseModel):
    """Partial update for a single webhook entry (pause state or multiplier)."""

    paused: bool | None = None
    multiplier: float | None = None


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _find_engine(state: DashboardState, name: str, config_name: str | None = None):
    """Find engine by session name, optionally scoped to a config."""
    for e in state.all_engines:
        if e.name == name:
            if config_name is None or e.config_name == config_name:
                return e
    return None


def _apply_overrides_to_engine(engine, fields: dict) -> None:
    """Apply override fields to a live ORBEngine or LSIEngine."""
    from .engine import _parse_time

    time_fields = {"orb_start", "orb_end", "entry_start", "entry_end",
                   "flat_start", "flat_end"}

    for key, value in fields.items():
        setattr(engine, key, value)

    # Re-parse cached time objects if any time field changed
    if time_fields & fields.keys():
        if hasattr(engine, "_orb_start_t"):
            engine._orb_start_t = _parse_time(engine.orb_start)
            engine._orb_end_t = _parse_time(engine.orb_end)
        engine._entry_start_t = _parse_time(engine.entry_start)
        engine._entry_end_t = _parse_time(engine.entry_end)
        engine._flat_start_t = _parse_time(engine.flat_start)
        engine._flat_end_t = _parse_time(engine.flat_end)


def _apply_defaults_to_engine(engine, session_name: str, config: dict) -> None:
    """Reset engine fields back to config defaults."""
    from .engine import _parse_time
    from .main import SESSION_CONFIGS, LSI_SESSION_CONFIGS
    from .overrides import LSI_EDITABLE_FIELDS

    risk = config.get("risk", {})

    if _is_lsi_engine(engine):
        defaults = LSI_SESSION_CONFIGS.get(session_name, {})
        for key in LSI_EDITABLE_FIELDS:
            if key in defaults:
                setattr(engine, key, defaults[key])
            elif key == "risk_usd":
                setattr(engine, key, risk.get("risk_usd", 250))
            elif key == "min_qty":
                setattr(engine, key, risk.get("min_qty", 1.0))
    else:
        defaults = SESSION_CONFIGS.get(session_name, {})
        for key in EDITABLE_FIELDS:
            if key in defaults:
                setattr(engine, key, defaults[key])
            elif key == "risk_usd":
                setattr(engine, key, risk.get("risk_usd", 250))
            elif key == "min_qty":
                setattr(engine, key, risk.get("min_qty", 1.0))
            elif key == "max_single_risk_usd":
                setattr(engine, key, risk.get("max_single_risk_usd", 500.0))
            elif key == "be_offset_ticks":
                setattr(engine, key, risk.get("be_offset_ticks", 0))

    # Re-parse cached time objects
    if hasattr(engine, "_orb_start_t"):
        engine._orb_start_t = _parse_time(engine.orb_start)
        engine._orb_end_t = _parse_time(engine.orb_end)
    engine._entry_start_t = _parse_time(engine.entry_start)
    engine._entry_end_t = _parse_time(engine.entry_end)
    engine._flat_start_t = _parse_time(engine.flat_start)
    engine._flat_end_t = _parse_time(engine.flat_end)


def _is_lsi_engine(engine) -> bool:
    """Check if an engine is an LSIEngine (vs ORBEngine)."""
    return hasattr(engine, "qty_multiplier") and not hasattr(engine, "orb_start")


def _defaults_for_session(name: str) -> dict:
    """Get the raw config defaults for a session (editable fields only)."""
    from .main import SESSION_CONFIGS, LSI_SESSION_CONFIGS

    cfg = LSI_SESSION_CONFIGS.get(name)
    if cfg is not None:
        from .overrides import LSI_EDITABLE_FIELDS
        return {k: v for k, v in cfg.items() if k in LSI_EDITABLE_FIELDS}

    cfg = SESSION_CONFIGS.get(name, {})
    return {k: v for k, v in cfg.items() if k in EDITABLE_FIELDS}


def _session_info(engine) -> dict:
    """Extract session config info from an engine instance."""
    if _is_lsi_engine(engine):
        return {
            "type": "lsi",
            "config_name": engine.config_name,
            "entry_start": engine.entry_start,
            "entry_end": engine.entry_end,
            "flat_start": engine.flat_start,
            "flat_end": engine.flat_end,
            "rr": engine.rr,
            "tp1_ratio": engine.tp1_ratio,
            "min_gap_atr_pct": engine.min_gap_atr_pct,
            "min_stop_points": engine.min_stop_points,
            "fvg_window_right": engine.fvg_window_right,
            "fvg_window_left": engine.fvg_window_left,
            "lsi_entry_mode": engine.lsi_entry_mode,
            "risk_usd": engine.risk_usd,
            "point_value": engine.point_value,
            "min_qty": engine.min_qty,
            "max_single_risk_usd": engine.max_single_risk_usd,
            "qty_step": engine.qty_step,
            "qty_multiplier": engine.qty_multiplier,
            "min_tick": engine.min_tick,
            "long_only": engine.long_only,
            "excluded_dow": engine.excluded_dow,
            "exec_ticker": engine.exec_ticker,
        }
    return {
        "type": "continuation",
        "config_name": engine.config_name,
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
        "max_single_risk_usd": engine.max_single_risk_usd,
        "qty_step": engine.qty_step,
        "be_offset_ticks": engine.be_offset_ticks,
        "min_tick": engine.min_tick,
        "long_only": engine.long_only,
        "icf_enabled": engine.icf_enabled,
        "excluded_dow": engine.excluded_dow,
        "fomc_exclusion": engine.fomc_exclusion,
        "min_stop_pts": engine.min_stop_pts,
        "min_tp1_pts": engine.min_tp1_pts,
        "exec_ticker": engine.exec_ticker,
    }
