"""Trade state persistence — checkpoint engine state to JSON for crash recovery.

Follows the same file-based JSON pattern as overrides.py.
Two files:
  config/checkpoint.json  — engine state snapshots (per config, per engine)
  config/trade_history.json — completed trades for G5 gate
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
CHECKPOINT_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "checkpoint.json"
TRADE_HISTORY_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "trade_history.json"

CHECKPOINT_VERSION = 1
TRADE_HISTORY_VERSION = 1
TRADE_HISTORY_RETENTION_DAYS = 7


# ---------------------------------------------------------------------------
# Atomic file write
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically: write to temp file, then rename.

    Prevents corruption if the process is killed mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_bar(bar: Any) -> dict:
    """Serialize a Bar to a JSON-safe dict."""
    return {
        "timestamp": bar.timestamp.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def _deserialize_bar(data: dict) -> Any:
    """Deserialize a Bar dict back to a Bar instance."""
    from .engine import Bar
    return Bar(
        timestamp=datetime.fromisoformat(data["timestamp"]),
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        volume=data["volume"],
    )


def _serialize_levels(levels: Any) -> dict | None:
    """Serialize a frozen TradeLevels dataclass to dict."""
    if levels is None:
        return None
    return {
        "entry": levels.entry,
        "stop": levels.stop,
        "tp1": levels.tp1,
        "tp2": levels.tp2,
        "be": levels.be,
        "qty": levels.qty,
        "half_qty": levels.half_qty,
        "is_single_contract": levels.is_single_contract,
        "risk_pts": levels.risk_pts,
        "direction": levels.direction,
        "gap_size": levels.gap_size,
    }


def _deserialize_levels(data: dict | None) -> Any:
    """Deserialize a TradeLevels dict."""
    if data is None:
        return None
    from .sizing import TradeLevels
    return TradeLevels(**data)


def _serialize_sweep(sweep: Any) -> dict | None:
    """Serialize a SweepEvent to dict."""
    if sweep is None:
        return None
    return {
        "source": sweep.source,
        "level": sweep.level,
        "direction": sweep.direction,
        "bar_index": sweep.bar_index,
    }


def _deserialize_sweep(data: dict | None) -> Any:
    """Deserialize a SweepEvent dict."""
    if data is None:
        return None
    from .sweep import SweepEvent
    return SweepEvent(**data)


def _serialize_gap(gap: Any) -> dict | None:
    """Serialize a GapInfo to dict."""
    if gap is None:
        return None
    return {
        "top": gap.top,
        "bottom": gap.bottom,
        "is_bullish": gap.is_bullish,
        "impulse_high": gap.impulse_high,
        "impulse_low": gap.impulse_low,
        "bar_index": gap.bar_index,
    }


def _deserialize_gap(data: dict | None) -> Any:
    """Deserialize a GapInfo dict."""
    if data is None:
        return None
    from .lsi_engine import GapInfo
    return GapInfo(**data)


# ---------------------------------------------------------------------------
# ORBEngine serialization
# ---------------------------------------------------------------------------

def serialize_orb_engine(engine: Any) -> dict:
    """Snapshot an ORBEngine's mutable state."""
    return {
        "engine_type": "orb",
        "state": engine._state.value,
        "current_date": engine._current_date,
        "orb_high": engine._orb_high,
        "orb_low": engine._orb_low,
        "daily_atr": engine._daily_atr,
        "bar_count": engine._bar_count,
        "long_fvg_found": engine._long_fvg_found,
        "short_fvg_found": engine._short_fvg_found,
        "levels": _serialize_levels(engine._levels),
        "tp1_hit": engine._tp1_hit,
        "tp1_bar_count": engine._tp1_bar_count,
        "fill_bar_idx": engine._fill_bar_idx,
        "fill_timestamp": engine._fill_timestamp.isoformat() if engine._fill_timestamp else None,
        "bars": [_serialize_bar(b) for b in engine._bars],
    }


def restore_orb_engine(engine: Any, data: dict) -> bool:
    """Restore an ORBEngine's mutable state from checkpoint data.

    Only restores states with financial exposure (ARMED_LONG, MANAGING).
    Returns True if the engine was restored to an active state.
    """
    from .engine import State

    state_str = data.get("state", "idle")
    try:
        target_state = State(state_str)
    except ValueError:
        logger.warning("[%s] Unknown checkpoint state '%s', skipping", engine.name, state_str)
        return False

    if target_state not in (State.ARMED_LONG, State.MANAGING):
        logger.info(
            "[%s] Checkpoint state '%s' has no financial exposure, skipping",
            engine.name, state_str,
        )
        return False

    engine._state = target_state
    engine._current_date = data.get("current_date", "")
    engine._orb_high = data.get("orb_high", float("nan"))
    engine._orb_low = data.get("orb_low", float("nan"))
    engine._daily_atr = data.get("daily_atr", 0.0)
    engine._bar_count = data.get("bar_count", 0)
    engine._long_fvg_found = data.get("long_fvg_found", False)
    engine._short_fvg_found = data.get("short_fvg_found", False)
    engine._levels = _deserialize_levels(data.get("levels"))
    engine._tp1_hit = data.get("tp1_hit", False)
    engine._tp1_bar_count = data.get("tp1_bar_count", -1)
    engine._fill_bar_idx = data.get("fill_bar_idx", -1)

    fill_ts = data.get("fill_timestamp")
    engine._fill_timestamp = datetime.fromisoformat(fill_ts) if fill_ts else None

    engine._bars = [_deserialize_bar(b) for b in data.get("bars", [])]

    logger.info(
        "[%s] Restored from checkpoint: state=%s date=%s levels=%s tp1_hit=%s",
        engine.name, state_str, engine._current_date,
        bool(engine._levels), engine._tp1_hit,
    )
    return True


# ---------------------------------------------------------------------------
# LSIEngine serialization
# ---------------------------------------------------------------------------

def serialize_lsi_engine(engine: Any) -> dict:
    """Snapshot an LSIEngine's mutable state."""
    return {
        "engine_type": "lsi",
        "state": engine._state.value,
        "current_date": engine._current_date,
        "daily_atr": engine._daily_atr,
        "bar_count": engine._bar_count,
        "active_sweep": _serialize_sweep(engine._active_sweep),
        "active_gap": _serialize_gap(engine._active_gap),
        "sweep_bar_index": engine._sweep_bar_index,
        "limit_price": engine._limit_price,
        "limit_direction": engine._limit_direction,
        "limit_stop": engine._limit_stop,
        "levels": _serialize_levels(engine._levels),
        "tp1_hit": engine._tp1_hit,
        "tp1_bar_count": engine._tp1_bar_count,
        "fill_bar_count": engine._fill_bar_count,
        "fill_timestamp": engine._fill_timestamp.isoformat() if engine._fill_timestamp else None,
        "bars": [_serialize_bar(b) for b in engine._bars],
    }


def restore_lsi_engine(engine: Any, data: dict) -> bool:
    """Restore an LSIEngine's mutable state from checkpoint data.

    Only restores states with financial exposure (ARMED_LIMIT, MANAGING).
    Returns True if the engine was restored to an active state.
    """
    from .lsi_engine import LSIState

    state_str = data.get("state", "idle")
    try:
        target_state = LSIState(state_str)
    except ValueError:
        logger.warning("[%s] Unknown checkpoint state '%s', skipping", engine.name, state_str)
        return False

    if target_state not in (LSIState.ARMED_LIMIT, LSIState.MANAGING):
        logger.info(
            "[%s] Checkpoint state '%s' has no financial exposure, skipping",
            engine.name, state_str,
        )
        return False

    engine._state = target_state
    engine._current_date = data.get("current_date", "")
    engine._daily_atr = data.get("daily_atr", 0.0)
    engine._bar_count = data.get("bar_count", 0)
    engine._active_sweep = _deserialize_sweep(data.get("active_sweep"))
    engine._active_gap = _deserialize_gap(data.get("active_gap"))
    engine._sweep_bar_index = data.get("sweep_bar_index", 0)
    engine._limit_price = data.get("limit_price", 0.0)
    engine._limit_direction = data.get("limit_direction", 0)
    engine._limit_stop = data.get("limit_stop", 0.0)
    engine._levels = _deserialize_levels(data.get("levels"))
    engine._tp1_hit = data.get("tp1_hit", False)
    engine._tp1_bar_count = data.get("tp1_bar_count", -1)
    engine._fill_bar_count = data.get("fill_bar_count", -1)

    fill_ts = data.get("fill_timestamp")
    engine._fill_timestamp = datetime.fromisoformat(fill_ts) if fill_ts else None

    engine._bars = [_deserialize_bar(b) for b in data.get("bars", [])]

    logger.info(
        "[%s] Restored from checkpoint: state=%s date=%s levels=%s tp1_hit=%s",
        engine.name, state_str, engine._current_date,
        bool(engine._levels), engine._tp1_hit,
    )
    return True


# ---------------------------------------------------------------------------
# Checkpoint read / write
# ---------------------------------------------------------------------------

def save_checkpoint(
    engines_by_config: dict[str, list],
    path: Path = CHECKPOINT_PATH,
) -> None:
    """Write checkpoint for all engines across all configs."""
    configs_data: dict[str, dict] = {}

    for config_name, engines in engines_by_config.items():
        config_engines: dict[str, dict] = {}
        for engine in engines:
            # Distinguish ORB vs LSI by checking for orb_start attribute
            if hasattr(engine, "orb_start"):
                config_engines[engine.name] = serialize_orb_engine(engine)
            else:
                config_engines[engine.name] = serialize_lsi_engine(engine)
        configs_data[config_name] = config_engines

    checkpoint = {
        "version": CHECKPOINT_VERSION,
        "written_at": datetime.now(tz=ET).isoformat(),
        "configs": configs_data,
    }

    try:
        _atomic_write(path, checkpoint)
        logger.debug("Checkpoint written to %s", path)
    except Exception:
        logger.exception("Failed to write checkpoint to %s", path)


def load_checkpoint(path: Path = CHECKPOINT_PATH) -> dict | None:
    """Load checkpoint from disk. Returns None if file missing or corrupt."""
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if data.get("version") != CHECKPOINT_VERSION:
            logger.warning(
                "Checkpoint version mismatch: got %s, expected %s",
                data.get("version"), CHECKPOINT_VERSION,
            )
            return None
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load checkpoint from %s: %s", path, exc)
        return None


def restore_engines(
    engines_by_config: dict[str, list],
    path: Path = CHECKPOINT_PATH,
) -> int:
    """Restore engine state from checkpoint file.

    Returns number of engines restored to active states.
    """
    checkpoint = load_checkpoint(path)
    if checkpoint is None:
        logger.info("No checkpoint file found, starting fresh")
        return 0

    now = datetime.now(tz=ET)
    today_str = now.strftime("%Y%m%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y%m%d")

    written_at_str = checkpoint.get("written_at", "")
    logger.info("Loading checkpoint written at %s", written_at_str)

    configs_data = checkpoint.get("configs", {})
    restored = 0

    for config_name, engines in engines_by_config.items():
        config_data = configs_data.get(config_name, {})
        for engine in engines:
            engine_data = config_data.get(engine.name)
            if engine_data is None:
                continue

            ckpt_date = engine_data.get("current_date", "")

            # Staleness check: checkpoint must be from today or yesterday
            # (yesterday is valid for cross-midnight sessions like NQ_Asia)
            if ckpt_date not in (today_str, yesterday_str):
                logger.info(
                    "[%s] Checkpoint date '%s' is stale (today=%s), skipping",
                    engine.name, ckpt_date, today_str,
                )
                continue

            engine_type = engine_data.get("engine_type", "orb")
            if engine_type == "orb":
                if restore_orb_engine(engine, engine_data):
                    restored += 1
            elif engine_type == "lsi":
                if restore_lsi_engine(engine, engine_data):
                    restored += 1

    logger.info("Checkpoint recovery: %d engine(s) restored to active state", restored)
    return restored


# ---------------------------------------------------------------------------
# Trade history persistence
# ---------------------------------------------------------------------------

def save_trade_history(
    trades: list,
    path: Path = TRADE_HISTORY_PATH,
) -> None:
    """Persist trade history to JSON with retention pruning."""
    from dataclasses import asdict

    # Prune trades older than retention window
    cutoff = datetime.now(tz=ET) - timedelta(days=TRADE_HISTORY_RETENTION_DAYS)
    cutoff_str = cutoff.strftime("%Y%m%d")

    recent_trades = [t for t in trades if t.date >= cutoff_str]

    data = {
        "version": TRADE_HISTORY_VERSION,
        "written_at": datetime.now(tz=ET).isoformat(),
        "trades": [asdict(t) for t in recent_trades],
    }

    try:
        _atomic_write(path, data)
        logger.debug("Trade history written: %d trades", len(recent_trades))
    except Exception:
        logger.exception("Failed to write trade history to %s", path)


def load_trade_history(path: Path = TRADE_HISTORY_PATH) -> list:
    """Load trade history from disk. Returns empty list if missing."""
    if not path.exists():
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if data.get("version") != TRADE_HISTORY_VERSION:
            logger.warning("Trade history version mismatch, starting fresh")
            return []

        from .engine import TradeRecord
        trades = []
        for t in data.get("trades", []):
            trades.append(TradeRecord(**t))
        return trades
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        logger.warning("Failed to load trade history from %s: %s", path, exc)
        return []
