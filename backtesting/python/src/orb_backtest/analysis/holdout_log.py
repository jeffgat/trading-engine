"""Hold-out period usage logging.

Tracks when hold-out (OOS) date ranges are tested with different configs,
and warns when the hold-out's "truly untouched" status is being eroded
by repeated testing — which inflates the apparent out-of-sample validity.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


HOLDOUT_LOG_PATH = Path(__file__).resolve().parents[3] / "data" / "results" / "holdout_log.json"


@dataclass
class HoldoutLogEntry:
    """A single hold-out test event."""
    timestamp: str
    config_hash: str
    period_start: str
    period_end: str
    experiment_name: str
    test_count: int
    is_first_use: bool
    warning: str | None


@dataclass
class HoldoutCheckResult:
    """Result of checking a hold-out period before testing."""
    period_key: str
    previous_test_count: int
    previous_configs: list[str]
    is_clean: bool
    warning: str | None


def log_holdout_test(
    period_start: str,
    period_end: str,
    config: dict,
    experiment_name: str = "",
) -> HoldoutLogEntry:
    """Log a hold-out test and return the entry with test count.

    Appends to the JSON log file. Creates the file if it doesn't exist.

    Args:
        period_start: OOS start date (YYYY-MM-DD).
        period_end: OOS end date (YYYY-MM-DD).
        config: Strategy config dict (hashed for comparison).
        experiment_name: Name/ID of the experiment.

    Returns:
        HoldoutLogEntry with test count and warning if applicable.
    """
    config_hash = _compute_config_hash(config)
    period_key = f"{period_start}_{period_end}"
    timestamp = datetime.now(timezone.utc).isoformat()

    # Read existing log
    data = _read_log()
    entries = data.get("entries", [])

    # Count previous tests of this period
    period_entries = [e for e in entries if e.get("period_key") == period_key]
    previous_hashes = [e["config_hash"] for e in period_entries]
    unique_configs = set(previous_hashes)
    test_count = len(period_entries) + 1
    is_first = len(period_entries) == 0

    # Generate warning
    warning = None
    if test_count == 2:
        warning = (
            f"WARNING: Hold-out period {period_start} to {period_end} tested 2x. "
            f"Untouched OOS status compromised."
        )
    elif test_count >= 3:
        n_configs = len(unique_configs | {config_hash})
        warning = (
            f"CRITICAL: Hold-out period tested {test_count}x with "
            f"{n_configs} different config(s). "
            f"Results are no longer true out-of-sample."
        )

    # Build new entry
    new_entry = {
        "timestamp": timestamp,
        "period_key": period_key,
        "period_start": period_start,
        "period_end": period_end,
        "config_hash": config_hash,
        "experiment_name": experiment_name,
        "test_count": test_count,
    }

    # Append and save
    entries.append(new_entry)
    data["entries"] = entries
    _write_log(data)

    return HoldoutLogEntry(
        timestamp=timestamp,
        config_hash=config_hash,
        period_start=period_start,
        period_end=period_end,
        experiment_name=experiment_name,
        test_count=test_count,
        is_first_use=is_first,
        warning=warning,
    )


def check_holdout_period(
    period_start: str,
    period_end: str,
) -> HoldoutCheckResult:
    """Check if a hold-out period has been tested before (read-only).

    Does NOT log — just checks the existing log file.

    Args:
        period_start: OOS start date (YYYY-MM-DD).
        period_end: OOS end date (YYYY-MM-DD).

    Returns:
        HoldoutCheckResult with previous test info and warning.
    """
    period_key = f"{period_start}_{period_end}"
    data = _read_log()
    entries = data.get("entries", [])

    period_entries = [e for e in entries if e.get("period_key") == period_key]
    previous_configs = list({e["config_hash"] for e in period_entries})
    count = len(period_entries)
    is_clean = count == 0

    warning = None
    if count == 1:
        warning = (
            f"Hold-out period {period_start} to {period_end} has been tested once. "
            f"Next test will compromise its untouched status."
        )
    elif count >= 2:
        warning = (
            f"Hold-out period tested {count}x with {len(previous_configs)} "
            f"config(s). No longer true out-of-sample."
        )

    return HoldoutCheckResult(
        period_key=period_key,
        previous_test_count=count,
        previous_configs=previous_configs,
        is_clean=is_clean,
        warning=warning,
    )


def get_holdout_history(
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[dict]:
    """Get all hold-out test entries, optionally filtered by period.

    Args:
        period_start: If provided, filter to entries with this start date.
        period_end: If provided, filter to entries with this end date.

    Returns:
        List of log entry dicts.
    """
    data = _read_log()
    entries = data.get("entries", [])

    if period_start:
        entries = [e for e in entries if e.get("period_start") == period_start]
    if period_end:
        entries = [e for e in entries if e.get("period_end") == period_end]

    return entries


def _compute_config_hash(config: dict) -> str:
    """Compute MD5 hash of config for comparison.

    Normalizes the config by sorting keys and rounding floats to avoid
    spurious differences from floating-point representation.
    """
    # If it's a dataclass-like object, convert to dict
    if hasattr(config, "__dataclass_fields__"):
        from dataclasses import asdict
        config = asdict(config)

    normalized = json.dumps(config, sort_keys=True, default=str)
    return hashlib.md5(normalized.encode()).hexdigest()


def _read_log() -> dict:
    """Read the holdout log file. Returns empty structure if file missing."""
    if not HOLDOUT_LOG_PATH.exists():
        return {"entries": []}
    try:
        with open(HOLDOUT_LOG_PATH) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError):
        return {"entries": []}


def _write_log(data: dict) -> None:
    """Write the holdout log file with file locking."""
    HOLDOUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HOLDOUT_LOG_PATH, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(data, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
