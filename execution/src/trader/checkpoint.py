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
        "exit_mode": getattr(levels, "exit_mode", "split"),
    }


def _deserialize_levels(data: dict | None) -> Any:
    """Deserialize a TradeLevels dict."""
    if data is None:
        return None
    from .sizing import TradeLevels
    return TradeLevels(**data)


def _float_or_nan(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _serialize_sweep(sweep: Any) -> dict | None:
    """Serialize a SweepEvent to dict."""
    if sweep is None:
        return None
    return {
        "source": sweep.source,
        "level": sweep.level,
        "direction": sweep.direction,
        "bar_index": sweep.bar_index,
        "pivot_time": sweep.pivot_time,
    }


def _deserialize_sweep(data: dict | None) -> Any:
    """Deserialize a SweepEvent dict."""
    if data is None:
        return None
    from .swing import SweepEvent
    # Backward compat: old checkpoints lack pivot_time
    if "pivot_time" not in data:
        data["pivot_time"] = ""
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
    engine_type = getattr(engine, "engine_type", "orb")
    data = {
        "engine_type": engine_type,
        "state": engine._state.value,
        "current_date": engine._current_date,
        "orb_high": engine._orb_high,
        "orb_low": engine._orb_low,
        "daily_atr": engine._daily_atr,
        "ath_high": engine._ath_high,
        "ath_last_update": engine._ath_last_update,
        "ath_last_close": getattr(engine, "_ath_last_close", float("nan")),
        "ath_last_gap_pct": getattr(engine, "_ath_last_gap_pct", float("nan")),
        "ath_check_count": getattr(engine, "_ath_check_count", 0),
        "ath_block_count": getattr(engine, "_ath_block_count", 0),
        "ath_pass_count": getattr(engine, "_ath_pass_count", 0),
        "ath_last_check": getattr(engine, "_ath_last_check", None),
        "ath_last_block": getattr(engine, "_ath_last_block", None),
        "bar_count": engine._bar_count,
        "long_fvg_found": engine._long_fvg_found,
        "short_fvg_found": engine._short_fvg_found,
        "levels": _serialize_levels(engine._levels),
        "tp1_hit": engine._tp1_hit,
        "tp1_bar_count": engine._tp1_bar_count,
        "runner_stop": getattr(engine, "_runner_stop", None),
        "trade_daily_atr": getattr(engine, "_trade_daily_atr", 0.0),
        "fill_bar_idx": engine._fill_bar_idx,
        "fill_timestamp": engine._fill_timestamp.isoformat() if engine._fill_timestamp else None,
        "fill_via_tick": engine._fill_via_tick,
        "armed_at": engine._armed_at.isoformat() if engine._armed_at else None,
        "bars": [_serialize_bar(b) for b in engine._bars],
        "paused": engine.paused,
        "exit_type": engine._exit_type,
        "r_result": engine._r_result,
    }
    if engine_type == "gold_x":
        data.update({
            "goldx_active_family": getattr(engine, "_goldx_active_family", None),
            "goldx_max_hold_at": (
                engine._goldx_max_hold_at.isoformat()
                if getattr(engine, "_goldx_max_hold_at", None)
                else None
            ),
            "goldx_quartile_stop": getattr(engine, "_goldx_quartile_stop", None),
            "goldx_fvg_expiry_at": (
                engine._goldx_fvg_expiry_at.isoformat()
                if getattr(engine, "_goldx_fvg_expiry_at", None)
                else None
            ),
            "goldx_last_classic_entry": (
                engine._goldx_last_classic_entry.isoformat()
                if getattr(engine, "_goldx_last_classic_entry", None)
                else None
            ),
            "goldx_last_classic_exit": (
                engine._goldx_last_classic_exit.isoformat()
                if getattr(engine, "_goldx_last_classic_exit", None)
                else None
            ),
            "goldx_last_fvg_selection": (
                engine._goldx_last_fvg_selection.isoformat()
                if getattr(engine, "_goldx_last_fvg_selection", None)
                else None
            ),
            "goldx_pending_breakouts": [
                {
                    "timestamp": item.timestamp.isoformat(),
                    "bar_index": item.bar_index,
                    "direction": item.direction,
                }
                for item in getattr(engine, "_goldx_pending_breakouts", [])
            ],
        })
    return data


def restore_orb_engine(engine: Any, data: dict) -> bool:
    """Restore an ORBEngine's mutable state from checkpoint data.

    Restores all checkpointed states, then validates against the current
    time to ensure the restored state is still appropriate:
    - ARMED_LIMIT / MANAGING: restore as-is (financial exposure)
    - WAITING_FOR_GAP / ORB_BUILDING: check if entry/ORB window still open
    - FLAT: restore as FLAT
    - IDLE: skip (normal on_bar flow will handle it)

    Returns True if the engine was restored to a non-IDLE state.
    """
    from .engine import State

    state_str = data.get("state", "idle")
    try:
        target_state = State(state_str)
    except ValueError:
        logger.warning("[%s] Unknown checkpoint state '%s', skipping", engine.name, state_str)
        return False

    if target_state == State.IDLE:
        logger.debug("[%s] Checkpoint state is IDLE, skipping", engine.name)
        return False

    # Restore all mutable fields from checkpoint
    engine._current_date = data.get("current_date", "")
    engine._orb_high = data.get("orb_high", float("nan"))
    engine._orb_low = data.get("orb_low", float("nan"))
    engine._daily_atr = data.get("daily_atr", 0.0)
    engine._ath_high = _float_or_nan(data.get("ath_high", float("nan")))
    engine._ath_last_update = data.get("ath_last_update", "")
    engine._ath_last_close = _float_or_nan(data.get("ath_last_close", float("nan")))
    engine._ath_last_gap_pct = _float_or_nan(data.get("ath_last_gap_pct", float("nan")))
    try:
        engine._ath_check_count = int(data.get("ath_check_count", 0) or 0)
    except (TypeError, ValueError):
        engine._ath_check_count = 0
    try:
        engine._ath_block_count = int(data.get("ath_block_count", 0) or 0)
    except (TypeError, ValueError):
        engine._ath_block_count = 0
    try:
        engine._ath_pass_count = int(data.get("ath_pass_count", 0) or 0)
    except (TypeError, ValueError):
        engine._ath_pass_count = 0
    engine._ath_last_check = data.get("ath_last_check")
    engine._ath_last_block = data.get("ath_last_block")
    engine._bar_count = data.get("bar_count", 0)
    engine._long_fvg_found = data.get("long_fvg_found", False)
    engine._short_fvg_found = data.get("short_fvg_found", False)
    engine._levels = _deserialize_levels(data.get("levels"))
    engine._tp1_hit = data.get("tp1_hit", False)
    engine._tp1_bar_count = data.get("tp1_bar_count", -1)
    engine._runner_stop = data.get("runner_stop")
    engine._trade_daily_atr = data.get("trade_daily_atr", data.get("daily_atr", 0.0))
    engine._fill_bar_idx = data.get("fill_bar_idx", -1)

    fill_ts = data.get("fill_timestamp")
    engine._fill_timestamp = datetime.fromisoformat(fill_ts) if fill_ts else None
    engine._fill_via_tick = data.get("fill_via_tick", False)
    armed_at = data.get("armed_at")
    engine._armed_at = datetime.fromisoformat(armed_at) if armed_at else None

    engine._bars = [_deserialize_bar(b) for b in data.get("bars", [])]
    if engine._armed_at is None and target_state == State.ARMED_LIMIT and engine._bars:
        # Backward-compat for older checkpoints written before armed_at existed.
        engine._armed_at = engine._bars[-1].timestamp + timedelta(minutes=5)
    engine.paused = data.get("paused", False)
    engine._exit_type = data.get("exit_type")
    engine._r_result = data.get("r_result")
    if getattr(engine, "engine_type", None) == "gold_x":
        engine._goldx_active_family = data.get("goldx_active_family")
        goldx_max_hold_at = data.get("goldx_max_hold_at")
        engine._goldx_max_hold_at = datetime.fromisoformat(goldx_max_hold_at) if goldx_max_hold_at else None
        engine._goldx_quartile_stop = data.get("goldx_quartile_stop")
        goldx_fvg_expiry_at = data.get("goldx_fvg_expiry_at")
        engine._goldx_fvg_expiry_at = datetime.fromisoformat(goldx_fvg_expiry_at) if goldx_fvg_expiry_at else None
        last_classic_entry = data.get("goldx_last_classic_entry")
        engine._goldx_last_classic_entry = (
            datetime.fromisoformat(last_classic_entry) if last_classic_entry else None
        )
        last_classic_exit = data.get("goldx_last_classic_exit")
        engine._goldx_last_classic_exit = (
            datetime.fromisoformat(last_classic_exit) if last_classic_exit else None
        )
        last_fvg_selection = data.get("goldx_last_fvg_selection")
        engine._goldx_last_fvg_selection = (
            datetime.fromisoformat(last_fvg_selection) if last_fvg_selection else None
        )
        try:
            from .goldx_engine import _GoldXBreakout
            engine._goldx_pending_breakouts = [
                _GoldXBreakout(
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    bar_index=int(item["bar_index"]),
                    direction=int(item["direction"]),
                )
                for item in data.get("goldx_pending_breakouts", [])
            ]
        except (KeyError, TypeError, ValueError):
            engine._goldx_pending_breakouts = []

    # Time-validate: ensure the restored state is still appropriate
    now = datetime.now(tz=ET)
    now_t = now.time()
    validated_state = _validate_orb_state(engine, target_state, now_t)
    engine._state = validated_state

    logger.info(
        "[%s] Restored from checkpoint: state=%s (checkpoint=%s) date=%s "
        "orb=%.2f/%.2f levels=%s tp1_hit=%s exit_type=%s paused=%s",
        engine.name, validated_state.value, state_str, engine._current_date,
        engine._orb_high, engine._orb_low,
        bool(engine._levels), engine._tp1_hit, engine._exit_type, engine.paused,
    )
    return True


def _validate_orb_state(engine: Any, checkpoint_state: Any, now_t) -> Any:
    """Validate a checkpoint state against the current time for ORBEngine.

    If the checkpoint state is no longer valid (e.g. entry window closed),
    return the appropriate adjusted state.
    """
    from .engine import State

    # Financial exposure states — always trust the checkpoint
    if checkpoint_state in (State.ARMED_LIMIT, State.MANAGING):
        return checkpoint_state

    # FLAT — keep as flat
    if checkpoint_state == State.FLAT:
        return State.FLAT

    # WAITING_FOR_GAP — valid only if entry window is still open
    if checkpoint_state == State.WAITING_FOR_GAP:
        if engine._in_entry(now_t):
            return State.WAITING_FOR_GAP
        logger.info(
            "[%s] Checkpoint was WAITING_FOR_GAP but entry window closed — setting FLAT",
            engine.name,
        )
        return State.FLAT

    # ORB_BUILDING — check if ORB window or entry window is still open
    if checkpoint_state == State.ORB_BUILDING:
        if engine._in_orb(now_t):
            return State.ORB_BUILDING
        # ORB window closed — advance based on time
        if engine._in_entry(now_t):
            # ORB data was already restored, advance to WAITING_FOR_GAP
            return State.WAITING_FOR_GAP
        logger.info(
            "[%s] Checkpoint was ORB_BUILDING but session window closed — setting FLAT",
            engine.name,
        )
        return State.FLAT

    # FILLED — treat like MANAGING (transient state)
    if checkpoint_state == State.FILLED:
        return State.MANAGING

    return checkpoint_state


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
        "session_filled_trades": engine._session_filled_trades,
        "active_sweep": _serialize_sweep(engine._active_sweep),
        "active_gap": _serialize_gap(engine._active_gap),
        "pending_gaps": [_serialize_gap(gap) for gap in getattr(engine, "_pending_gaps", [])],
        "active_sweep_instance_id": engine._active_sweep_instance_id,
        "active_htf_level_side": engine._active_htf_level_side,
        "sweep_bar_index": engine._sweep_bar_index,
        "entry_price": engine._entry_price,
        "entry_direction": engine._entry_direction,
        "entry_stop": engine._entry_stop,
        "levels": _serialize_levels(engine._levels),
        "tp1_hit": engine._tp1_hit,
        "tp1_bar_count": engine._tp1_bar_count,
        "fill_bar_count": engine._fill_bar_count,
        "fill_timestamp": engine._fill_timestamp.isoformat() if engine._fill_timestamp else None,
        "bars": [_serialize_bar(b) for b in engine._bars],
        "swing_tracker": engine._swings.to_dict(),
        "htf_levels": engine._htf_levels.to_dict() if getattr(engine, "_htf_levels", None) is not None else None,
        "htf_high_state": dict(getattr(engine, "_htf_high_state", {})),
        "htf_low_state": dict(getattr(engine, "_htf_low_state", {})),
        "paused": engine.paused,
        "exit_type": engine._exit_type,
        "r_result": engine._r_result,
        "skip_reason": getattr(engine, "_skip_reason", None),
        "blocking_gate": getattr(engine, "_blocking_gate", None),
        "regime_gate_status": getattr(engine, "_regime_gate_status", None),
        "fvg_to_inversion_bars": engine._fvg_to_inversion_bars,
        "sweep_to_inversion_bars": engine._sweep_to_inversion_bars,
    }


def restore_lsi_engine(engine: Any, data: dict) -> bool:
    """Restore an LSIEngine's mutable state from checkpoint data.

    Restores all checkpointed states, then validates against the current
    time to ensure the restored state is still appropriate:
    - MANAGING: restore as-is (financial exposure)
    - ARMED_LIMIT: restore as MANAGING (legacy checkpoint compat)
    - SCANNING / WAITING_FOR_GAP / WAITING_FOR_INVERSION:
      check if entry window still open
    - FLAT: restore as FLAT
    - IDLE: skip (normal on_bar flow will handle it)

    Returns True if the engine was restored to a non-IDLE state.
    """
    from .lsi_engine import LSIState

    state_str = data.get("state", "idle")
    # Migrate renamed states from old checkpoints
    _STATE_MIGRATIONS = {"waiting_for_sweep": "scanning"}
    state_str = _STATE_MIGRATIONS.get(state_str, state_str)
    try:
        target_state = LSIState(state_str)
    except ValueError:
        logger.warning("[%s] Unknown checkpoint state '%s', skipping", engine.name, state_str)
        return False

    if target_state == LSIState.IDLE:
        logger.debug("[%s] Checkpoint state is IDLE, skipping", engine.name)
        return False

    # Restore all mutable fields from checkpoint
    engine._current_date = data.get("current_date", "")
    engine._daily_atr = data.get("daily_atr", 0.0)
    engine._bar_count = data.get("bar_count", 0)
    engine._session_filled_trades = data.get("session_filled_trades", 0)
    engine._active_sweep = _deserialize_sweep(data.get("active_sweep"))
    engine._active_gap = _deserialize_gap(data.get("active_gap"))
    engine._pending_gaps = [
        gap for gap in (_deserialize_gap(item) for item in data.get("pending_gaps", [])) if gap is not None
    ]
    engine._active_sweep_instance_id = data.get("active_sweep_instance_id", -1)
    engine._active_htf_level_side = data.get("active_htf_level_side", "")
    engine._sweep_bar_index = data.get("sweep_bar_index", 0)
    # Backward compat: old checkpoints have limit_price/direction/stop, new have entry_*
    engine._entry_price = data.get("entry_price", data.get("limit_price", 0.0))
    engine._entry_direction = data.get("entry_direction", data.get("limit_direction", 0))
    engine._entry_stop = data.get("entry_stop", data.get("limit_stop", 0.0))
    engine._levels = _deserialize_levels(data.get("levels"))
    engine._tp1_hit = data.get("tp1_hit", False)
    engine._tp1_bar_count = data.get("tp1_bar_count", -1)
    engine._fill_bar_count = data.get("fill_bar_count", -1)

    fill_ts = data.get("fill_timestamp")
    engine._fill_timestamp = datetime.fromisoformat(fill_ts) if fill_ts else None

    engine._bars = [_deserialize_bar(b) for b in data.get("bars", [])]

    swing_data = data.get("swing_tracker")
    if swing_data:
        engine._swings.restore(swing_data)

    htf_data = data.get("htf_levels")
    if htf_data and getattr(engine, "_htf_levels", None) is not None:
        engine._htf_levels.restore(htf_data)
    engine._htf_high_state = dict(data.get("htf_high_state", getattr(engine, "_htf_high_state", {})))
    engine._htf_low_state = dict(data.get("htf_low_state", getattr(engine, "_htf_low_state", {})))

    engine.paused = data.get("paused", False)
    engine._exit_type = data.get("exit_type")
    engine._r_result = data.get("r_result")
    engine._skip_reason = data.get("skip_reason", getattr(engine, "_skip_reason", None))
    engine._blocking_gate = data.get("blocking_gate", getattr(engine, "_blocking_gate", None))
    engine._regime_gate_status = data.get("regime_gate_status", getattr(engine, "_regime_gate_status", None))
    engine._fvg_to_inversion_bars = data.get("fvg_to_inversion_bars")
    engine._sweep_to_inversion_bars = data.get("sweep_to_inversion_bars")

    # Time-validate: ensure the restored state is still appropriate
    now = datetime.now(tz=ET)
    now_t = now.time()
    validated_state = _validate_lsi_state(engine, target_state, now_t)
    engine._state = validated_state

    # If the validator downgraded to IDLE (new session starting), update the
    # date so the card shows today instead of the stale checkpoint date.
    from .lsi_engine import LSIState
    if validated_state == LSIState.IDLE and engine._current_date != now.strftime("%Y%m%d"):
        old_date = engine._current_date
        engine._current_date = now.strftime("%Y%m%d")
        logger.info(
            "[%s] Updated stale date %s → %s after IDLE downgrade",
            engine.name, old_date, engine._current_date,
        )

    logger.info(
        "[%s] Restored from checkpoint: state=%s (checkpoint=%s) date=%s "
        "levels=%s tp1_hit=%s exit_type=%s paused=%s",
        engine.name, validated_state.value, state_str, engine._current_date,
        bool(engine._levels), engine._tp1_hit, engine._exit_type, engine.paused,
    )
    return True


def _validate_lsi_state(engine: Any, checkpoint_state: Any, now_t) -> Any:
    """Validate a checkpoint state against the current time for LSIEngine.

    If the checkpoint state is no longer valid (e.g. entry window closed),
    return the appropriate adjusted state.
    """
    from .lsi_engine import LSIState

    # Financial exposure states — always trust the checkpoint
    if checkpoint_state in (LSIState.ARMED_LIMIT, LSIState.MANAGING):
        return checkpoint_state

    # FLAT — usually keep as flat, but with two exceptions:
    #
    # 1. Pre-session (before entry window): downgrade to IDLE so the normal
    #    IDLE→SCANNING transition fires when the entry window opens.
    #
    # 2. Entry window still open AND no trade was taken: downgrade to
    #    SCANNING.  This handles the case where a previous buggy process
    #    checkpointed FLAT prematurely (e.g. recover_session_state set FLAT
    #    instead of IDLE before the entry window, which then persisted).
    #    If the engine already took a trade (has levels), keep FLAT — the
    #    session genuinely completed.
    if checkpoint_state == LSIState.FLAT:
        # Pre-session check: downgrade to IDLE so IDLE→SCANNING fires at entry_start.
        # For daytime sessions: now < entry_start means pre-session.
        # For cross-midnight sessions: the daytime gap between flat_end and
        # entry_start (e.g. 07:00–20:40) is the pre-session window.
        if not engine._crosses_midnight and now_t < engine._entry_start_t:
            logger.info(
                "[%s] Checkpoint was FLAT but entry window hasn't started — setting IDLE",
                engine.name,
            )
            return LSIState.IDLE
        if engine._crosses_midnight and engine._flat_end_t <= now_t < engine._entry_start_t:
            logger.info(
                "[%s] Checkpoint was FLAT but cross-midnight entry window hasn't started — setting IDLE",
                engine.name,
            )
            return LSIState.IDLE

        now = datetime.now(tz=ET)
        same_session_date = engine._current_date == now.strftime("%Y%m%d")
        if engine._crosses_midnight:
            yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")
            same_session_date = same_session_date or (
                engine._current_date == yesterday and now_t < engine._flat_end_t
            )
        blocking_gate = getattr(engine, "_blocking_gate", None)
        if same_session_date and blocking_gate is None and getattr(engine, "regime_gate_checks", ()):
            blocking_gate = engine._blocking_regime_gate_name(engine._current_date)
            if blocking_gate is not None:
                engine._record_regime_gate_status(engine._current_date, blocking_gate)

        if same_session_date and (
            getattr(engine, "_skip_reason", None) == "regime_gate"
            or blocking_gate
        ):
            logger.info(
                "[%s] Checkpoint was FLAT due to regime gate - keeping FLAT",
                engine.name,
            )
            return LSIState.FLAT

        if (
            engine._in_entry(now_t)
            and engine._levels is None
            and (
                not getattr(engine, "_is_htf_variant", lambda: False)()
                or engine.htf_trade_max_per_session <= 0
                or engine._session_filled_trades < engine.htf_trade_max_per_session
            )
        ):
            logger.info(
                "[%s] Checkpoint was FLAT with no trade during open entry window — setting SCANNING",
                engine.name,
            )
            return LSIState.SCANNING
        return LSIState.FLAT

    # Setup-discovery states — valid only if entry window still open
    _discovery_states = (
        LSIState.SCANNING,
        LSIState.WAITING_FOR_GAP,
        LSIState.COLLECTING_GAPS,
        LSIState.WAITING_FOR_INVERSION,
    )
    if checkpoint_state in _discovery_states:
        if engine._in_entry(now_t):
            return checkpoint_state
        logger.info(
            "[%s] Checkpoint was %s but entry window closed — setting FLAT",
            engine.name, checkpoint_state.value,
        )
        return LSIState.FLAT

    return checkpoint_state


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
            if engine_type in {"orb", "hunter_orb", "gold_x"}:
                if restore_orb_engine(engine, engine_data):
                    restored += 1
            elif engine_type == "lsi":
                if restore_lsi_engine(engine, engine_data):
                    restored += 1

    logger.info("Checkpoint recovery: %d engine(s) restored", restored)
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
