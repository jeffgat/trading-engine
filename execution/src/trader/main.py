"""Entry point for the ORB live execution service.

Runs the 7-leg combined longs portfolio:
  NQ NY R11, NQ Asia R9, GC NY R3, ES NY Final, ES Asia Final,
  NQ LDN (G5 gated), NQ NY LSI (LSI 2x)

Usage:
    # Configs with webhooks send live; others are dry-run
    uv run orb-trader

    # Replay historical data for reconciliation
    uv run orb-trader --replay /path/to/NQ_5m.csv --start 2025-01-01

    # Custom config file
    uv run orb-trader --config config/live.toml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
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
        "risk_usd": 200,
        "max_single_risk_usd": 300,
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
        "risk_usd": 150,
        "max_single_risk_usd": 300,
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
        "risk_usd": 250,
        "max_single_risk_usd": 300,
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
        "risk_usd": 250,
        "max_single_risk_usd": 300,
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
        "risk_usd": 100,
        "max_single_risk_usd": 300,
    },
    # --- NQ LDN (ATR-based stop, G5 gated — skip when Asia hit TP1) ---
    "NQ_LDN": {
        "orb_start": "03:00",
        "orb_end": "03:30",
        "entry_start": "03:30",
        "entry_end": "08:25",
        "flat_start": "08:20",
        "flat_end": "08:25",
        "stop_atr_pct": 1.5,
        "stop_basis": "atr",
        "min_gap_atr_pct": 1.0,
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "rr": 6.0,
        "tp1_ratio": 0.7,
        "instrument": "NQ",
        "atr_length": 10,
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": None,  # no DOW exclusion; G5 gate applied instead
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 150,
        "max_single_risk_usd": 300,
    },
}


# ---------------------------------------------------------------------------
# LSI reversal session configs — separate from continuation legs
# ---------------------------------------------------------------------------

LSI_SESSION_CONFIGS = {
    # --- NQ Asia LSI (LSI reversal, inversion-bar-close entry) ---
    "NQ_Asia_LSI": {
        "entry_start": "20:40",
        "entry_end": "23:30",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "rr": 2.0,
        "tp1_ratio": 0.7,
        "min_gap_atr_pct": 1.75,  # 1.75% ATR-40
        "min_stop_points": 0.0,  # absolute floor (0 = disabled, matches backtester)
        "fvg_window_right": 2,
        "fvg_window_left": 15,
        "lsi_entry_mode": "close",
        "instrument": "NQ",
        "atr_length": 40,
        "long_only": True,
        "excluded_dow": None,  # no DOW exclusion
        "qty_multiplier": 1.0,
        "risk_usd": 250,
        "max_single_risk_usd": 300,
        "lsi_n_left": 8,
        "lsi_n_right": 2,
    },
    # --- NQ NY LSI (LSI reversal, 2x sizing, fvg_limit entry) ---
    "NQ_NY_LSI": {
        "entry_start": "09:35",
        "entry_end": "15:30",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "rr": 3.0,
        "tp1_ratio": 0.3,
        "min_gap_atr_pct": 5.0,  # 5% ATR-10
        "min_stop_points": 0.0,
        "fvg_window_right": 5,
        "fvg_window_left": 20,
        "lsi_entry_mode": "fvg_limit",
        "instrument": "NQ",
        "atr_length": 10,
        "long_only": True,
        "excluded_dow": [2, 3],  # Wed, Thu excluded
        "qty_multiplier": 2.0,
        "risk_usd": 250,
        "max_single_risk_usd": 300,
        "lsi_n_left": 8,
        "lsi_n_right": 60,
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
# Execution config profiles (FAST, SLOW, etc.)
# ---------------------------------------------------------------------------

EXEC_CONFIGS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "exec_configs.json"


@dataclass
class WebhookEntry:
    """A single webhook endpoint with a human-readable label."""

    url: str
    label: str = ""
    paused: bool = False
    multiplier: float = 1.0


@dataclass
class ExecutionConfig:
    """Named execution profile with its own session subset and risk overrides."""

    name: str
    enabled: bool = True
    webhooks: list[WebhookEntry] = field(default_factory=list)
    session_overrides: dict[str, dict] = field(default_factory=dict)
    lsi_session_overrides: dict[str, dict] = field(default_factory=dict)

    @property
    def webhook_url(self) -> str:
        """First webhook URL (legacy compat). Empty string if none configured."""
        return self.webhooks[0].url if self.webhooks else ""


def _parse_webhooks(data: dict) -> list[WebhookEntry]:
    """Parse webhooks from exec config dict, migrating legacy webhook_url."""
    # New format: webhooks array
    if "webhooks" in data:
        return [
            WebhookEntry(
                url=w.get("url", ""),
                label=w.get("label", ""),
                paused=w.get("paused", False),
                multiplier=float(w.get("multiplier", 1.0)),
            )
            for w in data["webhooks"]
            if w.get("url")
        ]
    # Legacy: single webhook_url string
    url = data.get("webhook_url", "")
    if url:
        return [WebhookEntry(url=url, label="Default")]
    return []


def load_exec_configs(config: dict | None = None) -> list[ExecutionConfig]:
    """Load execution configs from exec_configs.json.

    Falls back to a single DEFAULT config built from live.toml sessions
    if the file does not exist.
    """
    if EXEC_CONFIGS_PATH.exists():
        with open(EXEC_CONFIGS_PATH) as f:
            raw = json.load(f)
        configs = []
        for name, data in raw.items():
            configs.append(ExecutionConfig(
                name=name,
                enabled=data.get("enabled", True),
                webhooks=_parse_webhooks(data),
                session_overrides=data.get("sessions", {}),
                lsi_session_overrides=data.get("lsi_sessions", {}),
            ))
        if configs:
            return configs

    # Fallback: single DEFAULT config from live.toml
    cfg = config or {}
    sessions_enabled = cfg.get("sessions", {}).get("enabled", [
        "NQ_NY", "NQ_Asia", "GC_NY", "ES_NY", "ES_Asia",
    ])
    lsi_enabled = cfg.get("sessions", {}).get("lsi_enabled", [])
    return [ExecutionConfig(
        name="DEFAULT",
        enabled=True,
        webhooks=[],
        session_overrides={s: {} for s in sessions_enabled},
        lsi_session_overrides={s: {} for s in lsi_enabled},
    )]


def save_exec_configs(configs: list[ExecutionConfig]) -> None:
    """Persist execution configs back to exec_configs.json."""
    raw: dict = {}
    for ec in configs:
        raw[ec.name] = {
            "enabled": ec.enabled,
            "webhooks": [{"url": w.url, "label": w.label, "paused": w.paused, "multiplier": w.multiplier} for w in ec.webhooks],
            "sessions": ec.session_overrides,
            "lsi_sessions": ec.lsi_session_overrides,
        }
    with open(EXEC_CONFIGS_PATH, "w") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")


def apply_atr_values(symbol_map: dict[str, list], atr_values: dict[str, float]) -> None:
    for symbol, target_engines in symbol_map.items():
        atr = atr_values.get(symbol, 0.0)
        if atr > 0:
            for engine in target_engines:
                engine._daily_atr = atr


# ---------------------------------------------------------------------------
# Build engines from config
# ---------------------------------------------------------------------------

def build_engines(
    config: dict,
    broker,
    *,
    config_name: str = "",
    session_list: list[str] | None = None,
    exec_overrides: dict[str, dict] | None = None,
) -> tuple[list, dict[str, list], dict[str, int]]:
    """Build ORBEngine instances from config.

    Args:
        config: TOML config dict.
        broker: TradersPost client for this exec config.
        config_name: Execution config name (e.g. "FAST", "SLOW").
        session_list: Which sessions to build. If None, uses live.toml enabled list.
        exec_overrides: Per-session overrides from the exec config (e.g. risk_usd).

    Returns:
        (engines, symbol_map, atr_lengths) where:
        - symbol_map maps DataBento symbol (e.g. "NQ.FUT") to engines.
        - atr_lengths maps DataBento symbol to the ATR period for that feed.
    """
    from .engine import ORBEngine
    from .overrides import load_overrides

    general = config.get("general", {})
    risk = config.get("risk", {})
    runtime_overrides = load_overrides()

    sessions_enabled = session_list if session_list is not None else config.get("sessions", {}).get("enabled", [
        "NQ_NY", "NQ_Asia", "GC_NY", "ES_NY", "ES_Asia",
    ])
    session_overrides = config.get("sessions", {})
    exec_overrides = exec_overrides or {}

    default_half_days = tuple(config.get("dates", {}).get("half_days", [
        "20250703", "20251128", "20251224", "20250109", "20260119",
    ]))
    default_excluded_dates = tuple(config.get("dates", {}).get("excluded", []))

    engines = []
    symbol_map: dict[str, list] = {}
    # Track ATR length per feed symbol (use the longest if multiple sessions share a feed)
    atr_lengths: dict[str, int] = {}

    for sess_name in sessions_enabled:
        sess_cfg = SESSION_CONFIGS.get(sess_name)
        if sess_cfg is None:
            logger.warning("Unknown session '%s', skipping", sess_name)
            continue

        # Allow per-session overrides from TOML (keyed by lowercase name).
        # TOML [sessions.gc.ny] creates nested dicts, so traverse the path.
        toml_key = sess_name.lower().replace("_", ".")
        toml_overrides: dict = session_overrides
        for part in toml_key.split("."):
            if isinstance(toml_overrides, dict):
                toml_overrides = toml_overrides.get(part, {})
            else:
                toml_overrides = {}
                break
        if not isinstance(toml_overrides, dict):
            toml_overrides = {}
        merged = {**sess_cfg, **toml_overrides, **runtime_overrides.get(sess_name, {}), **exec_overrides.get(sess_name, {})}
        half_days = tuple(merged.get("half_days", default_half_days))
        excluded_dates = tuple(merged.get("excluded_dates", default_excluded_dates))

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

        engine = ORBEngine(
            name=sess_name,
            broker=broker,
            exec_ticker=exec_ticker,
            config_name=config_name,
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
            risk_usd=merged.get("risk_usd", risk.get("risk_usd", 250)),
            point_value=exec_inst["point_value"],
            min_qty=merged.get("min_qty", risk.get("min_qty", 1.0)),
            qty_step=risk.get("qty_step", 1.0),
            be_offset_ticks=risk.get("be_offset_ticks", 0),
            min_tick=exec_inst["min_tick"],
            stop_basis=merged.get("stop_basis", "atr"),
            stop_orb_pct=merged.get("stop_orb_pct", 0.0),
            gap_filter_basis=merged.get("gap_filter_basis", "atr"),
            min_gap_orb_pct=merged.get("min_gap_orb_pct", 0.0),
            min_stop_pts=merged.get("min_stop_pts", 0.0),
            min_tp1_pts=merged.get("min_tp1_pts", 0.0),
            max_single_risk_usd=merged.get("max_single_risk_usd", risk.get("max_single_risk_usd", 500.0)),
            long_only=merged.get("long_only", True),
            icf_enabled=merged.get("icf_enabled", False),
            excluded_dow=merged.get("excluded_dow"),
            fomc_exclusion=merged.get("fomc_exclusion", False),
            excluded_dates=excluded_dates,
            half_days=half_days,
            half_day_flat_start=merged.get("half_day_flat_start", config.get("dates", {}).get("half_day_flat_start", "12:50")),
            half_day_flat_end=merged.get("half_day_flat_end", config.get("dates", {}).get("half_day_flat_end", "13:00")),
        )
        engines.append(engine)
        symbol_map.setdefault(db_symbol, []).append(engine)
        logger.info(
            "[%s] Session engine created: %s (signal=%s, exec=%s, feed=%s, stop=%s, atr=%d, risk=$%s)",
            config_name or "DEFAULT", sess_name, sess_instrument, exec_ticker, db_symbol,
            merged.get("stop_basis", "atr"), sess_atr_length, merged.get("risk_usd", "?"),
        )

    return engines, symbol_map, atr_lengths


def build_lsi_engines(
    config: dict,
    broker,
    symbol_map: dict[str, list],
    atr_lengths: dict[str, int],
    *,
    config_name: str = "",
    lsi_list: list[str] | None = None,
    lsi_overrides: dict[str, dict] | None = None,
) -> list:
    """Build LSIEngine instances for LSI reversal sessions.

    Mutates symbol_map and atr_lengths in-place to register the new engines.
    """
    from .lsi_engine import LSIEngine

    risk = config.get("risk", {})
    lsi_enabled = lsi_list if lsi_list is not None else config.get("sessions", {}).get("lsi_enabled", [])
    lsi_overrides = lsi_overrides or {}
    if not lsi_enabled:
        return []

    default_half_days = tuple(config.get("dates", {}).get("half_days", [
        "20250703", "20251128", "20251224", "20250109", "20260119",
    ]))
    default_excluded_dates = tuple(config.get("dates", {}).get("excluded", []))

    engines = []
    for sess_name in lsi_enabled:
        sess_cfg = LSI_SESSION_CONFIGS.get(sess_name)
        if sess_cfg is None:
            logger.warning("Unknown LSI session '%s', skipping", sess_name)
            continue

        sess_instrument = sess_cfg.get("instrument", "NQ")
        inst = INSTRUMENTS.get(sess_instrument, INSTRUMENTS["NQ"])
        db_symbol = inst["db_symbol"]
        exec_ticker = SIGNAL_TO_EXEC.get(sess_instrument, sess_instrument)
        exec_inst = INSTRUMENTS.get(exec_ticker, inst)

        sess_atr_length = sess_cfg.get("atr_length", 10)
        atr_lengths[db_symbol] = max(atr_lengths.get(db_symbol, 0), sess_atr_length)

        # Merge exec config overrides (e.g. risk_usd) on top of base config
        merged = {**sess_cfg, **lsi_overrides.get(sess_name, {})}
        half_days = tuple(merged.get("half_days", default_half_days))
        excluded_dates = tuple(merged.get("excluded_dates", default_excluded_dates))

        # Handle excluded_dow as list → first value for single exclusion
        excl_dow = merged.get("excluded_dow")

        engine = LSIEngine(
            name=sess_name,
            broker=broker,
            exec_ticker=exec_ticker,
            config_name=config_name,
            entry_start=merged["entry_start"],
            entry_end=merged["entry_end"],
            flat_start=merged["flat_start"],
            flat_end=merged["flat_end"],
            rr=merged["rr"],
            tp1_ratio=merged["tp1_ratio"],
            min_gap_atr_pct=merged.get("min_gap_atr_pct", 5.0),
            min_stop_points=merged.get("min_stop_points", 0.0),
            fvg_window_left=merged.get("fvg_window_left", 10),
            fvg_window_right=merged.get("fvg_window_right", 5),
            lsi_entry_mode=merged.get("lsi_entry_mode", "close"),
            risk_usd=merged.get("risk_usd", risk.get("risk_usd", 250)),
            point_value=exec_inst["point_value"],
            min_qty=merged.get("min_qty", risk.get("min_qty", 1.0)),
            qty_step=risk.get("qty_step", 1.0),
            qty_multiplier=merged.get("qty_multiplier", 1.0),
            min_tick=exec_inst["min_tick"],
            max_single_risk_usd=merged.get("max_single_risk_usd", risk.get("max_single_risk_usd", 500.0)),
            long_only=merged.get("long_only", True),
            excluded_dow=excl_dow,
            excluded_dates=excluded_dates,
            half_days=half_days,
            half_day_flat_start=merged.get("half_day_flat_start", config.get("dates", {}).get("half_day_flat_start", "12:50")),
            half_day_flat_end=merged.get("half_day_flat_end", config.get("dates", {}).get("half_day_flat_end", "13:00")),
            lsi_n_left=merged.get("lsi_n_left", 3),
            lsi_n_right=merged.get("lsi_n_right", 3),
        )
        engines.append(engine)
        symbol_map.setdefault(db_symbol, []).append(engine)
        logger.info(
            "[%s] LSI engine created: %s (signal=%s, exec=%s, feed=%s, qty_mult=%.1f, risk=$%s)",
            config_name or "DEFAULT", sess_name, sess_instrument, exec_ticker, db_symbol,
            merged.get("qty_multiplier", 1.0), merged.get("risk_usd", "?"),
        )

    return engines


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def run_live(config: dict, api_port: int = 8000) -> None:
    """Run the live execution service."""
    import uvicorn

    from .api import DashboardState, LogTailer, create_app
    from .broker import TradersPostClient
    from .feed import ET, DataBentoFeed

    general = config.get("general", {})
    db_cfg = config.get("databento", {})

    # Load execution configs (FAST, SLOW, etc.)
    exec_configs = load_exec_configs(config)
    logger.info("Loaded %d execution config(s): %s", len(exec_configs), [ec.name for ec in exec_configs])

    # Build engines per execution config
    engines_by_config: dict[str, list] = {}
    brokers: list[TradersPostClient] = []
    global_symbol_map: dict[str, list] = {}
    global_atr_lengths: dict[str, int] = {}
    exec_configs_meta: dict[str, dict] = {}  # metadata for API
    multi_brokers_by_config: dict[str, "MultiBroker"] = {}  # for per-account API control

    for ec in exec_configs:
        if not ec.enabled:
            logger.info("Execution config '%s' is disabled, skipping", ec.name)
            continue

        # One broker per webhook endpoint; no webhooks = dry-run stub
        config_brokers: list[TradersPostClient] = []
        webhook_entries = ec.webhooks or []
        if not webhook_entries:
            webhook_entries = [WebhookEntry(url="", label="")]

        for wh in webhook_entries:
            b = TradersPostClient(
                webhook_url=wh.url,
                ticker=general.get("instrument", "MNQ"),
                config_name=f"{ec.name}[{wh.label}]" if wh.label else ec.name,
            )
            b.paused = wh.paused
            b.multiplier = wh.multiplier
            config_brokers.append(b)
            brokers.append(b)

        # Multi-broker fan-out: wrap list so engines send to all accounts
        from .broker import MultiBroker
        broker = MultiBroker(config_brokers)
        multi_brokers_by_config[ec.name] = broker

        # Build continuation engines for this config's sessions
        session_list = list(ec.session_overrides.keys())
        engines, sym_map, atr_lens = build_engines(
            config, broker,
            config_name=ec.name,
            session_list=session_list,
            exec_overrides=ec.session_overrides,
        )

        # Build LSI engines for this config's LSI sessions
        lsi_list = list(ec.lsi_session_overrides.keys())
        lsi_engines = build_lsi_engines(
            config, broker, sym_map, atr_lens,
            config_name=ec.name,
            lsi_list=lsi_list,
            lsi_overrides=ec.lsi_session_overrides,
        )

        config_engines = engines + lsi_engines
        engines_by_config[ec.name] = config_engines

        # Merge into global maps (feed routes bars to ALL engines across all configs)
        for sym, eng_list in sym_map.items():
            global_symbol_map.setdefault(sym, []).extend(eng_list)
        for sym, length in atr_lens.items():
            global_atr_lengths[sym] = max(global_atr_lengths.get(sym, 0), length)

        # Store metadata for API
        exec_configs_meta[ec.name] = {
            "enabled": ec.enabled,
            "webhooks": [{"url": w.url, "label": w.label, "paused": w.paused, "multiplier": w.multiplier} for w in ec.webhooks],
            "sessions": session_list,
            "lsi_sessions": lsi_list,
        }

        n_live_wh = sum(1 for b in config_brokers if not b.dry_run)
        config_mode = "LIVE (%d webhook%s)" % (n_live_wh, "s" if n_live_wh != 1 else "") if n_live_wh else "DRY-RUN (no webhooks)"
        logger.info(
            "[%s] %s — %d engines: sessions=%s lsi=%s",
            ec.name, config_mode, len(config_engines), session_list, lsi_list,
        )

    all_engines = [e for engines in engines_by_config.values() for e in engines]
    if not all_engines:
        logger.error("No session engines configured across any execution config")
        sys.exit(1)

    # Dashboard API — pass engines grouped by config
    has_live = any(not b.dry_run for b in brokers)
    mode = "LIVE" if has_live else "DRY-RUN"
    dashboard = DashboardState(
        engines_by_config=engines_by_config,
        config=config,
        mode=mode,
        exec_configs=exec_configs_meta,
        multi_brokers_by_config=multi_brokers_by_config,
    )

    # Checkpoint persistence — debounced to one write per event loop turn
    from .checkpoint import (
        save_checkpoint, restore_engines, load_trade_history, save_trade_history,
    )
    _checkpoint_pending = False

    def _request_checkpoint():
        nonlocal _checkpoint_pending
        if _checkpoint_pending:
            return
        _checkpoint_pending = True
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon(_do_checkpoint)
        except RuntimeError:
            _do_checkpoint()

    def _do_checkpoint():
        nonlocal _checkpoint_pending
        _checkpoint_pending = False
        save_checkpoint(engines_by_config)

    # Wire callbacks into each engine (both ORBEngine and LSIEngine)
    for engine in all_engines:
        engine.on_state_change = dashboard.on_state_change
        engine.on_trade_exit = dashboard.record_trade
        engine.on_checkpoint = _request_checkpoint

    # Wire G5 gate for NQ_LDN: skip when Asia hit TP1 the prior night.
    # Scoped per config — only checks trade_history from the same config.
    for cfg_name, cfg_engines in engines_by_config.items():
        def _make_g5_gate(config_name: str):
            def _g5_gate(ldn_date: str) -> bool:
                """Return True to BLOCK the trade (Asia TP1 hit prior night)."""
                from datetime import timedelta
                try:
                    ldn_dt = datetime.strptime(ldn_date, "%Y%m%d")
                except ValueError:
                    return False
                asia_dt = ldn_dt - timedelta(days=1)
                while asia_dt.weekday() >= 5:
                    asia_dt -= timedelta(days=1)
                asia_date_str = asia_dt.strftime("%Y%m%d")
                return dashboard.asia_tp1_hit_for_date(asia_date_str, config_name=config_name)
            return _g5_gate

        for engine in cfg_engines:
            if engine.name == "NQ_LDN":
                engine.g5_gate_check = _make_g5_gate(cfg_name)

    app = create_app(dashboard)
    tailer = LogTailer(dashboard)

    uvi_config = uvicorn.Config(
        app, host="0.0.0.0", port=api_port, log_level="warning",
    )
    server = uvicorn.Server(uvi_config)

    # Bar callback — route 5m bars to engines for signal detection (ORB, FVG)
    async def on_bar(symbol: str, bar, daily_atr: float):
        target_engines = global_symbol_map.get(symbol, [])
        for engine in target_engines:
            await engine.on_bar(bar, daily_atr)

    # Tick callback — route 1s bars to engines for fill/exit management
    async def on_tick(symbol: str, tick, daily_atr: float):
        target_engines = global_symbol_map.get(symbol, [])
        for engine in target_engines:
            await engine.on_tick(tick, daily_atr)

    # DataBento feed — subscribe to all symbols needed by active engines
    api_key = _env_or_key(db_cfg, "api_key")
    feed_symbols = list(global_symbol_map.keys())

    global_atr_length = max(global_atr_lengths.values()) if global_atr_lengths else 14

    feed = DataBentoFeed(
        api_key=api_key or None,
        symbols=feed_symbols,
        dataset=db_cfg.get("dataset", "GLBX.MDP3"),
        on_bar=on_bar,
        on_tick=on_tick,
        atr_length=global_atr_length,
    )

    # Refresh ATR from historical daily bars (prior completed day)
    atr_refresh_days = 60
    refresh_info = feed.refresh_atr_daily(lookback_days=atr_refresh_days)
    if refresh_info:
        logger.info(
            "ATR refresh complete: %s",
            {i.symbol: {"last_date": str(i.last_daily_date), "atr": round(i.atr_value, 2)} for i in refresh_info},
        )

    atr_values = feed.get_atr_values()
    apply_atr_values(global_symbol_map, atr_values)

    # recover current-day opening ranges / session state from recent intraday history
    intraday_5m = feed.preload_intraday_5m(lookback_hours=18)
    now_et = datetime.now(tz=ET)
    recovered = 0
    for symbol, target_engines in global_symbol_map.items():
        bars = intraday_5m.get(symbol, [])
        for engine in target_engines:
            if hasattr(engine, "recover_opening_range") and engine.recover_opening_range(bars, now_et):
                recovered += 1
            elif hasattr(engine, "recover_session_state") and engine.recover_session_state(bars, now_et):
                recovered += 1
    logger.info(
        "startup recovery complete: recovered=%d total_engines=%d",
        recovered, len(all_engines),
    )

    # Restore trade history from disk (G5 gate)
    dashboard.trade_history = load_trade_history()
    if dashboard.trade_history:
        logger.info("Restored %d trade(s) from history file", len(dashboard.trade_history))

    # Restore engine state from checkpoint — overwrites time-based recovery
    # with the actual last-known state (now handles all states, not just ARMED/MANAGING)
    checkpoint_restored = restore_engines(engines_by_config)
    if checkpoint_restored > 0:
        logger.info(
            "Checkpoint recovery: %d engine(s) restored from checkpoint",
            checkpoint_restored,
        )
        apply_atr_values(global_symbol_map, atr_values)

    logger.info(
        "Starting ORB Trader — configs=%s feeds=%s total_engines=%d api=:%d",
        list(engines_by_config.keys()), feed_symbols, len(all_engines), api_port,
    )

    # Graceful shutdown handler — cancel/flatten active positions on SIGTERM/SIGINT
    shutdown_event = asyncio.Event()
    last_atr_refresh_date = datetime.now(tz=ET).date()

    def _handle_shutdown_signal(signum, _frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating graceful shutdown...", sig_name)
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_shutdown_signal)

    async def _shutdown_watcher():
        await shutdown_event.wait()
        logger.info("Graceful shutdown: cancelling/flattening active positions...")
        for engine in all_engines:
            try:
                state_val = engine._state.value if hasattr(engine._state, "value") else str(engine._state)
                if state_val == "armed_limit":
                    logger.info("[%s] Shutdown: cancelling pending order", engine.name)
                    await engine.broker.send_cancel(ticker=engine.exec_ticker)
                elif state_val == "managing":
                    logger.info("[%s] Shutdown: flattening open position", engine.name)
                    await engine.broker.send_flatten(ticker=engine.exec_ticker)
            except Exception:
                logger.exception("[%s] Error during shutdown cleanup", engine.name)

        # Final checkpoint
        save_checkpoint(engines_by_config)
        save_trade_history(dashboard.trade_history)
        logger.info("Graceful shutdown complete. Final checkpoint saved.")
        server.should_exit = True

    async def _atr_refresh_loop():
        nonlocal last_atr_refresh_date
        while not shutdown_event.is_set():
            now = datetime.now(tz=ET)
            if last_atr_refresh_date != now.date():
                try:
                    refresh_info = feed.refresh_atr_daily(lookback_days=atr_refresh_days)
                    atr_values = feed.get_atr_values()
                    apply_atr_values(global_symbol_map, atr_values)
                    last_atr_refresh_date = now.date()
                    if refresh_info:
                        logger.info(
                            "Daily ATR refresh complete: %s",
                            {i.symbol: {"last_date": str(i.last_daily_date), "atr": round(i.atr_value, 2)} for i in refresh_info},
                        )
                except Exception:
                    logger.exception("Daily ATR refresh failed")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    try:
        await asyncio.gather(
            feed.run(),
            server.serve(),
            tailer.run(),
            _atr_refresh_loop(),
            _shutdown_watcher(),
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for broker in brokers:
            await broker.close()


async def run_replay(config: dict, csv_path: str, start: str | None, end: str | None) -> None:
    """Replay historical bars through the engine."""
    from .broker import TradersPostClient
    from .feed import ReplayFeed

    broker = TradersPostClient(
        webhook_url="",
        ticker="MNQ",
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
  uv run orb-trader                           # Configs with webhooks send live; others dry-run
  uv run orb-trader --replay NQ_5m.csv       # Replay historical data (always dry-run)
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
        asyncio.run(run_live(config, api_port=args.port))


if __name__ == "__main__":
    cli()
