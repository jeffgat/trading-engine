"""Runtime config overrides — persisted to JSON, sparse diffs on top of SESSION_CONFIGS defaults."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "overrides.json"

# Fields that are editable at runtime
EDITABLE_FIELDS: frozenset[str] = frozenset({
    # Session times
    "orb_start", "orb_end", "entry_start", "entry_end",
    "flat_start", "flat_end", "excluded_dow",
    # Strategy
    "rr", "tp1_ratio", "exit_mode", "stop_atr_pct", "stop_orb_pct",
    "min_gap_atr_pct", "min_gap_orb_pct", "max_gap_atr_pct",
    # Risk & sizing
    "risk_usd", "min_qty", "max_single_risk_usd", "be_offset_ticks",
    # Toggles
    "long_only", "short_only", "icf_enabled", "fomc_exclusion",
    "min_stop_pts", "min_tp1_pts",
    # Regime filters
    "ath_block_min_pct", "ath_block_max_pct",
})

# LSI-specific editable fields (for NQ_NY_LSI and future LSI sessions)
LSI_EDITABLE_FIELDS: frozenset[str] = frozenset({
    "entry_start", "entry_end", "sweep_start", "sweep_end", "flat_start", "flat_end", "excluded_dow",
    "rr", "tp1_ratio", "exit_mode", "min_gap_atr_pct", "min_stop_points", "stop_atr_pct",
    "fvg_window_right", "fvg_window_left", "lsi_entry_mode", "lsi_stop_mode", "lsi_target_mode",
    "lsi_confirmation_mode", "lsi_variant", "base_bar_minutes",
    "lsi_reset_swing_window_on_new_day", "cisd_min_leg_bars", "cisd_min_leg_atr_pct", "cisd_max_leg_bars",
    "htf_level_tf_minutes", "htf_n_left", "htf_trade_max_per_session", "max_fvg_to_inversion_bars",
    "risk_usd", "min_qty", "max_single_risk_usd",
    "qty_multiplier", "long_only",
})

# Fields that must NOT be changed at runtime (derived from instrument)
READONLY_FIELDS: frozenset[str] = frozenset({
    "point_value", "min_tick", "exec_ticker", "qty_step",
    "instrument", "stop_basis", "gap_filter_basis",
})


def load_overrides(path: Path = DEFAULT_PATH) -> dict[str, dict[str, Any]]:
    """Load overrides from JSON file. Returns {} if file doesn't exist."""
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load overrides from %s: %s", path, exc)
        return {}


def save_overrides(overrides: dict[str, dict[str, Any]], path: Path = DEFAULT_PATH) -> None:
    """Persist overrides to JSON file. Creates parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(overrides, f, indent=2)
    logger.info("Saved config overrides to %s", path)


def validate_fields(fields: dict[str, Any], allowed: frozenset[str] | None = None) -> tuple[dict[str, Any], list[str]]:
    """Validate and filter override fields.

    Args:
        fields: Dict of field name → value.
        allowed: Set of allowed field names. Defaults to EDITABLE_FIELDS.

    Returns (valid_fields, error_messages).
    """
    editable = allowed or EDITABLE_FIELDS
    errors: list[str] = []
    valid: dict[str, Any] = {}
    for key, value in fields.items():
        if key in READONLY_FIELDS:
            errors.append(f"Field '{key}' is read-only and cannot be overridden")
        elif key not in editable:
            errors.append(f"Unknown field '{key}'")
        else:
            valid[key] = value
    return valid, errors
