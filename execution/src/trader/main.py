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
    "SI": {"point_value": 5000.0, "min_tick": 0.005, "commission": 0.05, "db_symbol": "SI.FUT"},
    "SIL": {"point_value": 1000.0, "min_tick": 0.005, "commission": 0.05, "db_symbol": "SIL.FUT"},
}

# Signal instrument → execution instrument mapping.
# We subscribe to full-size contracts (NQ, ES, GC) for signal data via DataBento
# but execute on micro contracts (MNQ, MES, MGC) via TradersPost.
SIGNAL_TO_EXEC: dict[str, str] = {
    "NQ": "MNQ",
    "ES": "MES",
    "GC": "MGC",
    "YM": "MYM",
    "SI": "SIL",
    # Micros map to themselves
    "MNQ": "MNQ",
    "MES": "MES",
    "MGC": "MGC",
    "MYM": "MYM",
    "SIL": "SIL",
}

# ---------------------------------------------------------------------------
# 5-leg combined longs portfolio session configs
# From COMBINED_LONGS_5LEG_PINE_SPEC.md
# ---------------------------------------------------------------------------

SESSION_CONFIGS = {
    # --- NQ NY R11 (ATR-based stop, Friday exclusion) ---
    "NQ_NY": {
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
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
    # --- GC Asia-1 (ORB-based stop, both directions, regime gate) ---
    "GC_Asia": {
        "orb_start": "20:00",
        "orb_end": "20:30",  # 30m ORB
        "entry_start": "20:30",
        "entry_end": "23:15",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "stop_orb_pct": 25.0,
        "stop_basis": "orb",
        "min_gap_atr_pct": 1.0,
        "gap_filter_basis": "atr",
        "rr": 2.5,
        "tp1_ratio": 0.6,
        "instrument": "GC",
        "atr_length": 14,
        "long_only": False,
        "icf_enabled": False,
        "excluded_dow": None,
        "fomc_exclusion": False,
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
    # --- SI Asia-1 Short (ORB-based stop, short-only continuation, regime gated) ---
    "SI_Asia": {
        "orb_start": "20:00",
        "orb_end": "20:30",
        "entry_start": "20:30",
        "entry_end": "23:15",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "stop_orb_pct": 75.0,
        "stop_basis": "orb",
        "min_gap_atr_pct": 1.0,
        "gap_filter_basis": "atr",
        "rr": 2.5,
        "tp1_ratio": 0.6,
        "instrument": "SI",
        "atr_length": 14,
        "long_only": False,
        "short_only": True,
        "icf_enabled": False,
        "excluded_dow": None,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 200,
        "max_single_risk_usd": 300,
    },
    # --- NQ NY Short (ORB-based stop, short-only continuation, regime gated) ---
    "NQ_NY_Short": {
        "orb_start": "09:30",
        "orb_end": "09:55",
        "entry_start": "09:55",
        "entry_end": "11:30",
        "flat_start": "11:30",
        "flat_end": "16:00",
        "stop_orb_pct": 15.0,
        "stop_basis": "orb",
        "min_gap_orb_pct": 2.5,
        "gap_filter_basis": "orb",
        "rr": 2.5,
        "tp1_ratio": 0.4,
        "instrument": "NQ",
        "atr_length": 10,
        "long_only": False,
        "short_only": True,
        "icf_enabled": False,
        "excluded_dow": None,
        "fomc_exclusion": False,
        "min_stop_pts": 10.0,
        "min_tp1_pts": 10.0,
        "risk_usd": 200,
        "max_single_risk_usd": 300,
    },
    # --- NQ Hunter ORB (TradingView Hunter/classic parity leg, MNQ execution) ---
    "H_ORB": {
        "engine_type": "hunter_orb",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "11:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "instrument": "NQ",
        "exec_ticker": "MNQ",
        "atr_length": 14,
        "risk_usd": 350,
        "max_single_risk_usd": 350,
        "max_contracts": 20,
        "long_only": False,
        "short_only": False,
        "excluded_dow": [1],
        "body_min_pct": 55.0,
        "rejection_wick_max_pct": 20.0,
        "sl_buffer_points": 1.0,
        "hunter_target_rr": 2.0,
        "large_sl_threshold_points": 50.0,
        "reduced_target_rr": 1.0,
        "max_hold_minutes": 270,
        "ema15_enabled": True,
        "ema15_length": 14,
        "ema15_source": "close",
        "ema15_tolerance_points": 2.0,
        "ema15_max_distance": None,
        "reentry_policy": "after_each_loss",
        "allow_same_bar_win_reentry": True,
        "same_bar_win_reentry_max_minutes": 5.0,
        "reentry_max_extension_pct": 100.0,
        "enable_fast_reentry_exhaustion_filter": True,
        "fast_reentry_exhaustion_max_minutes": 10.1,
        "fast_reentry_exhaustion_max_extension_pct": 12.0,
        "fast_reentry_exhaustion_min_ema15_distance": 50.0,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "hunter",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "hunter",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- NQ Hunter ORB 10y-safe stress-gated branch, dry-run research leg ---
    "H_ORB_SAFE": {
        "engine_type": "hunter_orb",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "11:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "instrument": "NQ",
        "exec_ticker": "MNQ",
        "atr_length": 14,
        "risk_usd": 350,
        "max_single_risk_usd": 350,
        "max_contracts": 20,
        "long_only": False,
        "short_only": False,
        "excluded_dow": None,
        "regime_gates": [
            "block_bull_high_vol",
            "block_bear_high_vol",
            "block_bear_medium_vol",
        ],
        "body_min_pct": 55.0,
        "rejection_wick_max_pct": 100.0,
        "sl_buffer_points": 1.0,
        "hunter_target_rr": 2.0,
        "large_sl_threshold_points": 50.0,
        "reduced_target_rr": 1.0,
        "max_hold_minutes": 270,
        "ema15_enabled": True,
        "ema15_length": 14,
        "ema15_source": "close",
        "ema15_tolerance_points": 0.0,
        "ema15_max_distance": None,
        "reentry_policy": "legacy_one_reentry_after_loss",
        "allow_same_bar_win_reentry": False,
        "same_bar_win_reentry_max_minutes": 5.0,
        "reentry_max_extension_pct": None,
        "enable_fast_reentry_exhaustion_filter": False,
        "fast_reentry_exhaustion_max_minutes": 10.1,
        "fast_reentry_exhaustion_max_extension_pct": 12.0,
        "fast_reentry_exhaustion_min_ema15_distance": 50.0,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "hunter",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "hunter",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- NQ Hunter ORB ablated 2025+ combo, dry-run research leg ---
    "H_ORB_ABLATED": {
        "engine_type": "hunter_orb",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        # Entry end is exclusive; 13:05 allows the 13:00 signal bar.
        "entry_end": "13:05",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "instrument": "NQ",
        "exec_ticker": "MNQ",
        "atr_length": 14,
        "risk_usd": 350,
        "max_single_risk_usd": 350,
        "max_contracts": 20,
        "long_only": False,
        "short_only": False,
        "excluded_dow": [1],
        "body_min_pct": 0.0,
        "rejection_wick_max_pct": 20.0,
        "sl_buffer_points": 1.0,
        "hunter_target_rr": 2.0,
        "large_sl_threshold_points": 50.0,
        "reduced_target_rr": 2.0,
        "max_hold_minutes": 270,
        "ema15_enabled": False,
        "ema15_length": 14,
        "ema15_source": "close",
        "ema15_tolerance_points": 2.0,
        "ema15_max_distance": None,
        "reentry_policy": "all_nonoverlap",
        "allow_same_bar_win_reentry": False,
        "same_bar_win_reentry_max_minutes": 5.0,
        "reentry_max_extension_pct": None,
        "enable_fast_reentry_exhaustion_filter": False,
        "fast_reentry_exhaustion_max_minutes": 10.1,
        "fast_reentry_exhaustion_max_extension_pct": 12.0,
        "fast_reentry_exhaustion_min_ema15_distance": 50.0,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "hunter",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "hunter",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
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
        "lsi_variant": "legacy-LSI",
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
    max_open_contracts: float = 0.0
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
                max_open_contracts=float(data.get("max_open_contracts", 0.0)),
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
            "max_open_contracts": ec.max_open_contracts,
            "webhooks": [{"url": w.url, "label": w.label, "paused": w.paused, "multiplier": w.multiplier} for w in ec.webhooks],
            "sessions": ec.session_overrides,
            "lsi_sessions": ec.lsi_session_overrides,
        }
    with open(EXEC_CONFIGS_PATH, "w") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")


def _required_regime_daily_symbols(engines: list) -> list[str]:
    """Collect extra daily-history symbols required by configured regime gates."""
    from .gates import required_daily_history_symbols_for_regime_gates

    required: set[str] = set()
    for engine in engines:
        required.update(
            required_daily_history_symbols_for_regime_gates(
                getattr(engine, "regime_gates", ()),
            )
        )
    return sorted(required)


def apply_atr_values(
    symbol_map: dict[str, list],
    atr_values_by_symbol: dict[str, dict[int, float]],
) -> None:
    for symbol, target_engines in symbol_map.items():
        symbol_atrs = atr_values_by_symbol.get(symbol, {})
        for engine in target_engines:
            atr = symbol_atrs.get(getattr(engine, "atr_length", 14), 0.0)
            if atr > 0:
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
    position_manager=None,
) -> tuple[list, dict[str, list], dict[str, set[int]]]:
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
        - atr_lengths maps DataBento symbol to ATR periods needed by that feed.
    """
    from .engine import ORBEngine
    from .gates import build_regime_gates, build_structure_gate, normalize_regime_gates
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
    # track ATR lengths per feed symbol
    atr_lengths: dict[str, set[int]] = {}

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
        regime_gates = normalize_regime_gates(
            merged.get("regime_gate"),
            merged.get("regime_gates"),
        )
        compiled_regime_gates = build_regime_gates(regime_gates)

        # Per-session instrument (signal data source) and execution ticker
        sess_instrument = merged.get("instrument", "NQ")
        inst = INSTRUMENTS.get(sess_instrument, INSTRUMENTS["NQ"])
        db_symbol = inst["db_symbol"]

        # Resolve execution ticker: use micro contract for order routing
        exec_ticker = merged.get("exec_ticker") or SIGNAL_TO_EXEC.get(sess_instrument, sess_instrument)
        exec_inst = INSTRUMENTS.get(exec_ticker, inst)

        # track ATR lengths per symbol
        sess_atr_length = merged.get("atr_length", 14)
        atr_lengths.setdefault(db_symbol, set()).add(sess_atr_length)

        common_kwargs = dict(
            name=sess_name,
            broker=broker,
            exec_ticker=exec_ticker,
            config_name=config_name,
            allow_5m_fill_detection=False,
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
            atr_length=sess_atr_length,
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
            short_only=merged.get("short_only", False),
            icf_enabled=merged.get("icf_enabled", False),
            excluded_dow=merged.get("excluded_dow"),
            fomc_exclusion=merged.get("fomc_exclusion", False),
            regime_gate=regime_gates[0] if len(regime_gates) == 1 else None,
            regime_gates=regime_gates,
            regime_gate_check=compiled_regime_gates[0][1] if len(compiled_regime_gates) == 1 else None,
            regime_gate_checks=compiled_regime_gates,
            structure_gate=merged.get("structure_gate"),
            structure_gate_check=build_structure_gate(merged.get("structure_gate")),
            excluded_dates=excluded_dates,
            half_days=half_days,
            half_day_flat_start=merged.get("half_day_flat_start", config.get("dates", {}).get("half_day_flat_start", "12:50")),
            half_day_flat_end=merged.get("half_day_flat_end", config.get("dates", {}).get("half_day_flat_end", "13:00")),
            position_manager=position_manager,
            position_limit_key=f"{config_name or 'DEFAULT'}:{db_symbol}",
        )
        if merged.get("engine_type") == "hunter_orb":
            from .hunter_orb_engine import HunterORBEngine

            engine = HunterORBEngine(
                **common_kwargs,
                engine_type=merged.get("engine_type", "hunter_orb"),
                body_min_pct=merged.get("body_min_pct", 55.0),
                rejection_wick_max_pct=merged.get("rejection_wick_max_pct", 20.0),
                sl_buffer_points=merged.get("sl_buffer_points", 1.0),
                hunter_target_rr=merged.get("hunter_target_rr", 2.0),
                large_sl_threshold_points=merged.get("large_sl_threshold_points", 50.0),
                reduced_target_rr=merged.get("reduced_target_rr", 1.0),
                max_hold_minutes=merged.get("max_hold_minutes", 270),
                max_contracts=merged.get("max_contracts", 20.0),
                ema15_enabled=merged.get("ema15_enabled", True),
                ema15_length=merged.get("ema15_length", 14),
                ema15_source=merged.get("ema15_source", "close"),
                ema15_tolerance_points=merged.get("ema15_tolerance_points", 2.0),
                ema15_max_distance=merged.get("ema15_max_distance"),
                reentry_policy=merged.get("reentry_policy", "after_each_loss"),
                allow_same_bar_win_reentry=merged.get("allow_same_bar_win_reentry", True),
                same_bar_win_reentry_max_minutes=merged.get("same_bar_win_reentry_max_minutes", 5.0),
                reentry_max_extension_pct=merged.get("reentry_max_extension_pct", 100.0),
                enable_fast_reentry_exhaustion_filter=merged.get("enable_fast_reentry_exhaustion_filter", True),
                fast_reentry_exhaustion_max_minutes=merged.get("fast_reentry_exhaustion_max_minutes", 10.1),
                fast_reentry_exhaustion_max_extension_pct=merged.get("fast_reentry_exhaustion_max_extension_pct", 12.0),
                fast_reentry_exhaustion_min_ema15_distance=merged.get("fast_reentry_exhaustion_min_ema15_distance", 50.0),
            )
        else:
            engine = ORBEngine(**common_kwargs)
        engines.append(engine)
        symbol_map.setdefault(db_symbol, []).append(engine)
        logger.info(
            "[%s] Session engine created: %s (type=%s, signal=%s, exec=%s, feed=%s, stop=%s, atr=%d, risk=$%s, regime_gates=%s, structure_gate=%s)",
            config_name or "DEFAULT", sess_name, merged.get("engine_type", "orb"),
            sess_instrument, exec_ticker, db_symbol,
            merged.get("stop_basis", "atr"), sess_atr_length, merged.get("risk_usd", "?"),
            ",".join(regime_gates) if regime_gates else "-",
            merged.get("structure_gate") or "-",
        )

    return engines, symbol_map, atr_lengths


def build_lsi_engines(
    config: dict,
    broker,
    symbol_map: dict[str, list],
    atr_lengths: dict[str, set[int]],
    *,
    config_name: str = "",
    lsi_list: list[str] | None = None,
    lsi_overrides: dict[str, dict] | None = None,
    position_manager=None,
) -> list:
    """Build LSIEngine instances for LSI reversal sessions.

    Mutates symbol_map and atr_lengths in-place to register the new engines.
    """
    from .gates import build_regime_gates, normalize_regime_gates
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

        # Merge exec config overrides (e.g. risk_usd) on top of base config
        merged = {**sess_cfg, **lsi_overrides.get(sess_name, {})}
        sess_instrument = merged.get("instrument", "NQ")
        inst = INSTRUMENTS.get(sess_instrument, INSTRUMENTS["NQ"])
        db_symbol = inst["db_symbol"]
        exec_ticker = SIGNAL_TO_EXEC.get(sess_instrument, sess_instrument)
        exec_inst = INSTRUMENTS.get(exec_ticker, inst)
        sess_atr_length = merged.get("atr_length", sess_cfg.get("atr_length", 14))
        atr_lengths.setdefault(db_symbol, set()).add(sess_atr_length)
        half_days = tuple(merged.get("half_days", default_half_days))
        excluded_dates = tuple(merged.get("excluded_dates", default_excluded_dates))
        regime_gates = normalize_regime_gates(
            merged.get("regime_gate"),
            merged.get("regime_gates"),
        )
        compiled_regime_gates = build_regime_gates(regime_gates)

        # Handle excluded_dow as list → first value for single exclusion
        excl_dow = merged.get("excluded_dow")

        engine = LSIEngine(
            name=sess_name,
            broker=broker,
            exec_ticker=exec_ticker,
            config_name=config_name,
            entry_start=merged["entry_start"],
            entry_end=merged["entry_end"],
            sweep_start=merged.get("sweep_start"),
            sweep_end=merged.get("sweep_end"),
            flat_start=merged["flat_start"],
            flat_end=merged["flat_end"],
            rr=merged["rr"],
            tp1_ratio=merged["tp1_ratio"],
            atr_length=sess_atr_length,
            min_gap_atr_pct=merged.get("min_gap_atr_pct", 5.0),
            min_stop_points=merged.get("min_stop_points", 0.0),
            fvg_window_left=merged.get("fvg_window_left", 10),
            fvg_window_right=merged.get("fvg_window_right", 5),
            lsi_entry_mode=merged.get("lsi_entry_mode", "close"),
            lsi_variant=merged.get("lsi_variant", "legacy-LSI"),
            risk_usd=merged.get("risk_usd", risk.get("risk_usd", 250)),
            point_value=exec_inst["point_value"],
            min_qty=merged.get("min_qty", risk.get("min_qty", 1.0)),
            qty_step=risk.get("qty_step", 1.0),
            qty_multiplier=merged.get("qty_multiplier", 1.0),
            min_tick=exec_inst["min_tick"],
            max_single_risk_usd=merged.get("max_single_risk_usd", risk.get("max_single_risk_usd", 500.0)),
            long_only=merged.get("long_only", True),
            excluded_dow=excl_dow,
            regime_gate=regime_gates[0] if len(regime_gates) == 1 else None,
            regime_gates=regime_gates,
            regime_gate_check=compiled_regime_gates[0][1] if len(compiled_regime_gates) == 1 else None,
            regime_gate_checks=compiled_regime_gates,
            excluded_dates=excluded_dates,
            half_days=half_days,
            half_day_flat_start=merged.get("half_day_flat_start", config.get("dates", {}).get("half_day_flat_start", "12:50")),
            half_day_flat_end=merged.get("half_day_flat_end", config.get("dates", {}).get("half_day_flat_end", "13:00")),
            lsi_n_left=merged.get("lsi_n_left", 3),
            lsi_n_right=merged.get("lsi_n_right", 3),
            htf_level_tf_minutes=merged.get("htf_level_tf_minutes", 60),
            htf_n_left=merged.get("htf_n_left", 5),
            htf_trade_max_per_session=merged.get("htf_trade_max_per_session", 1),
            max_fvg_to_inversion_bars=merged.get("max_fvg_to_inversion_bars", 0),
        )
        engine.position_manager = position_manager
        engine.position_limit_key = f"{config_name or 'DEFAULT'}:{db_symbol}"
        engines.append(engine)
        symbol_map.setdefault(db_symbol, []).append(engine)
        logger.info(
            "[%s] LSI engine created: %s (signal=%s, exec=%s, feed=%s, variant=%s, qty_mult=%.1f, risk=$%s, regime_gates=%s)",
            config_name or "DEFAULT", sess_name, sess_instrument, exec_ticker, db_symbol,
            merged.get("lsi_variant", "legacy-LSI"),
            merged.get("qty_multiplier", 1.0), merged.get("risk_usd", "?"),
            ",".join(regime_gates) if regime_gates else "-",
        )

    return engines


# ---------------------------------------------------------------------------
# Shutdown helpers
# ---------------------------------------------------------------------------

def _checkpoint_shutdown_flat(engine) -> None:
    """Persist shutdown-driven cancel/flatten as FLAT for restart safety.

    During graceful shutdown we intentionally cancel pending entries and flatten
    open positions before writing the final checkpoint. If we keep the old
    in-memory state (`armed_limit` / `managing`), a restart will restore stale
    exposure and can emit duplicate exit orders later in the session.
    """
    state = getattr(engine, "_state", None)
    flat_state = getattr(getattr(state, "__class__", None), "FLAT", None)
    if flat_state is not None:
        engine._state = flat_state

    cleanup_task = getattr(engine, "_cleanup_task", None)
    if cleanup_task is not None and not cleanup_task.done():
        cleanup_task.cancel()
        engine._cleanup_task = None

    release_position_cap = getattr(engine, "_release_position_cap", None)
    if callable(release_position_cap):
        release_position_cap()

    notify_state_change = getattr(engine, "_notify_state_change", None)
    if callable(notify_state_change):
        notify_state_change()


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def run_live(config: dict, api_port: int = 8000) -> None:
    """Run the live execution service."""
    import uvicorn

    from .api import DashboardState, LogTailer, create_app
    from .broker import TradersPostClient
    from .feed import ET, DataBentoFeed
    from .gates import set_daily_history_provider
    from .position_limits import ContractCapManager

    general = config.get("general", {})
    db_cfg = config.get("databento", {})

    # Load execution configs (FAST, SLOW, etc.)
    exec_configs = load_exec_configs(config)
    logger.info("Loaded %d execution config(s): %s", len(exec_configs), [ec.name for ec in exec_configs])

    # Build engines per execution config
    engines_by_config: dict[str, list] = {}
    brokers: list[TradersPostClient] = []
    global_symbol_map: dict[str, list] = {}
    global_atr_lengths: dict[str, set[int]] = {}
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
        position_manager = ContractCapManager(max_open_contracts=ec.max_open_contracts)

        # Build continuation engines for this config's sessions
        session_list = list(ec.session_overrides.keys())
        engines, sym_map, atr_lens = build_engines(
            config, broker,
            config_name=ec.name,
            session_list=session_list,
            exec_overrides=ec.session_overrides,
            position_manager=position_manager,
        )

        # Build LSI engines for this config's LSI sessions
        lsi_list = list(ec.lsi_session_overrides.keys())
        lsi_engines = build_lsi_engines(
            config, broker, sym_map, atr_lens,
            config_name=ec.name,
            lsi_list=lsi_list,
            lsi_overrides=ec.lsi_session_overrides,
            position_manager=position_manager,
        )

        orb_by_name = {engine.name: engine for engine in engines}
        lsi_by_name = {engine.name: engine for engine in lsi_engines}
        nq_ny_orb = orb_by_name.get("NQ_NY")
        nq_ny_lsi = lsi_by_name.get("NQ_NY_LSI")
        if nq_ny_orb is not None and nq_ny_lsi is not None:
            def _make_nq_ny_overlap_check(orb_engine):
                def _check(direction: int) -> bool:
                    if direction != 1:
                        return False
                    levels = getattr(orb_engine, "_levels", None)
                    state = getattr(getattr(orb_engine, "_state", None), "value", "")
                    if state not in {"armed_limit", "filled", "managing"}:
                        return False
                    return bool(levels is not None and getattr(levels, "direction", 0) == -1)

                return _check

            nq_ny_lsi.trade_overlap_check = _make_nq_ny_overlap_check(nq_ny_orb)

        config_engines = engines + lsi_engines
        engines_by_config[ec.name] = config_engines

        # Merge into global maps (feed routes bars to ALL engines across all configs)
        for sym, eng_list in sym_map.items():
            global_symbol_map.setdefault(sym, []).extend(eng_list)
        for sym, lengths in atr_lens.items():
            global_atr_lengths.setdefault(sym, set()).update(lengths)

        # Store metadata for API
        exec_configs_meta[ec.name] = {
            "enabled": ec.enabled,
            "max_open_contracts": ec.max_open_contracts,
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
    async def on_bar(symbol: str, bar, daily_atrs: dict[int, float]):
        target_engines = global_symbol_map.get(symbol, [])
        for engine in target_engines:
            daily_atr = daily_atrs.get(getattr(engine, "atr_length", 14), 0.0)
            try:
                await engine.on_bar(bar, daily_atr)
            except Exception:
                logger.exception("[%s] on_bar failed — engine isolated", getattr(engine, "name", "?"))

    # Tick callback — route 1s bars to engines for fill/exit management
    async def on_tick(symbol: str, tick, daily_atrs: dict[int, float]):
        target_engines = global_symbol_map.get(symbol, [])
        for engine in target_engines:
            daily_atr = daily_atrs.get(getattr(engine, "atr_length", 14), 0.0)
            try:
                await engine.on_tick(tick, daily_atr)
            except Exception:
                logger.exception("[%s] on_tick failed — engine isolated", getattr(engine, "name", "?"))

    # DataBento feed — subscribe to all symbols needed by active engines
    api_key = _env_or_key(db_cfg, "api_key")
    feed_symbols = list(global_symbol_map.keys())
    daily_only_symbols = [
        symbol for symbol in _required_regime_daily_symbols(all_engines)
        if symbol not in feed_symbols
    ]

    feed = DataBentoFeed(
        api_key=api_key or None,
        symbols=feed_symbols,
        daily_only_symbols=daily_only_symbols,
        dataset=db_cfg.get("dataset", "GLBX.MDP3"),
        on_bar=on_bar,
        on_tick=on_tick,
        atr_lengths_by_symbol=global_atr_lengths,
    )
    if daily_only_symbols:
        logger.info("Daily-history-only symbols added for regime gates: %s", daily_only_symbols)
    set_daily_history_provider(feed.get_daily_history_for_symbol)

    # Refresh ATR from historical daily bars (prior completed day)
    atr_refresh_days = 60
    refresh_info = feed.refresh_atr_daily(lookback_days=atr_refresh_days)
    if refresh_info:
        logger.info(
            "ATR refresh complete: %s",
            {i.symbol: {"last_date": str(i.last_daily_date), "atr": round(i.atr_value, 2)} for i in refresh_info},
        )

    atr_values = {
        symbol: feed.get_atr_values_for_symbol(symbol) for symbol in feed_symbols
    }
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

    for cfg_name, cfg_engines in engines_by_config.items():
        if not cfg_engines:
            continue
        position_manager = getattr(cfg_engines[0], "position_manager", None)
        if position_manager is None or not position_manager.enabled:
            continue
        for engine in cfg_engines:
            levels = getattr(engine, "_levels", None)
            state = getattr(engine, "_state", None)
            if levels is None or state is None:
                continue
            state_value = getattr(state, "value", "")
            if state_value not in {"armed_limit", "managing"}:
                continue
            if getattr(engine, "_tp1_hit", False) and not levels.is_single_contract:
                position_manager.adjust(
                    engine.position_limit_key,
                    max(0.0, levels.qty - levels.half_qty),
                    owner_id=engine.name,
                )
            else:
                position_manager.adjust(
                    engine.position_limit_key,
                    levels.qty,
                    owner_id=engine.name,
                )

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
                    _checkpoint_shutdown_flat(engine)
                elif state_val == "managing":
                    logger.info("[%s] Shutdown: flattening open position", engine.name)
                    await engine.broker.send_flatten(ticker=engine.exec_ticker)
                    _checkpoint_shutdown_flat(engine)
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
                    atr_values = {
                        symbol: feed.get_atr_values_for_symbol(symbol) for symbol in feed_symbols
                    }
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

    replay_atr_lengths = sorted({
        length for lengths in atr_lengths.values() for length in lengths
    }) or [14]

    async def on_bar(bar, daily_atrs: dict[int, float]):
        for engine in engines:
            daily_atr = daily_atrs.get(getattr(engine, "atr_length", 14), 0.0)
            await engine.on_bar(bar, daily_atr)

    feed = ReplayFeed(
        csv_path=csv_path,
        on_bar=on_bar,
        atr_lengths=replay_atr_lengths,
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
