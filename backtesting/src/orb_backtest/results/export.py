"""Export backtest results as structured dicts for DB storage and LLM consumption."""

from __future__ import annotations

import re
import time
from datetime import datetime

import numpy as np

from ..config import StrategyConfig
from ..engine.simulator import TradeResult, EXIT_NAMES, EXIT_NO_FILL
from .metrics import compute_metrics
from ..analysis.gates import DOW_NAMES, apply_dow_filter
from ..experiments import (
    log_run,
    log_optimization,
    get_backtest_result,
    delete_backtest_run,
    rename_backtest,
    list_optimization_history,
    get_optimization_result,
    delete_optimization_run,
)


# ---------------------------------------------------------------------------
# ID generation helpers
# ---------------------------------------------------------------------------

# Abbreviations for swept param names in optimization IDs
_PARAM_ABBREV: dict[str, str] = {
    "rr": "rr",
    "tp1_ratio": "tp1",
    "runner_trail_mode": "trail",
    "runner_trail_trigger_r": "trig",
    "runner_trail_stop_r": "lock",
    "runner_trail_step_r": "step",
    "runner_trail_gap_r": "gapr",
    "runner_trail_atr_pct": "atrtrail",

    "atr_length": "atr",
    "risk_usd": "risk",
    "lsi_confirmation_mode": "confirm",
    "cisd_min_leg_bars": "cisdmin",
    "cisd_min_leg_atr_pct": "cisdatr",
    "cisd_max_leg_bars": "cisdmax",
    "ny_stop_atr_pct": "ny.stop",
    "ny_stop_orb_pct": "ny.orbstop",
    "ny_min_gap_atr_pct": "ny.gap",
    "ny_min_gap_orb_pct": "ny.orbgap",
    "asia_stop_atr_pct": "asia.stop",
    "asia_stop_orb_pct": "asia.orbstop",
    "asia_min_gap_atr_pct": "asia.gap",
    "asia_min_gap_orb_pct": "asia.orbgap",
    "ldn_stop_atr_pct": "ldn.stop",
    "ldn_stop_orb_pct": "ldn.orbstop",
    "ldn_min_gap_atr_pct": "ldn.gap",
    "ldn_min_gap_orb_pct": "ldn.orbgap",
}


def _short_hash() -> str:
    """6-char hex from timestamp nanos (16.7M possibilities)."""
    return format(time.time_ns() % (16**6), "06x")


def _slugify(text: str, max_len: int = 40) -> str:
    """Convert text to a lowercase, hyphen-separated ID slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _sessions_from_config(config: dict) -> list[str]:
    """Extract sorted session names from a config dict."""
    seen: set[str] = set()
    result: list[str] = []
    for key in config:
        if key.endswith("_orb_window") or key.endswith("_entry_window"):
            sess = key.split("_")[0].upper()
            if sess not in seen:
                seen.add(sess)
                result.append(sess)
    return sorted(result)


def _trade_cost_fields(t: TradeResult) -> dict:
    commission_usd = getattr(t, "commission_usd", 0.0)
    gross_pnl_usd = getattr(t, "gross_pnl_usd", 0.0) or (t.pnl_usd + commission_usd)
    net_r_multiple = getattr(t, "net_r_multiple", 0.0)
    return {
        "net_pnl_usd": round(t.pnl_usd, 2),
        "gross_pnl_usd": round(gross_pnl_usd, 2),
        "commission_usd": round(commission_usd, 2),
        "net_r_multiple": round(net_r_multiple, 3),
    }


def generate_backtest_id(result: dict) -> str:
    """Generate a backtest ID: ``bt-{descriptor}-{hash6}``."""
    config = result.get("config", {})
    name = result.get("name", "")

    if name:
        descriptor = _slugify(name)
    else:
        instrument = config.get("instrument", "unk").lower()
        sessions = _sessions_from_config(config)
        sess_str = ".".join(s.lower() for s in sessions) or "unk"
        rr = config.get("rr", "")
        rr_str = f"{rr:g}" if isinstance(rr, (int, float)) else str(rr)
        descriptor = f"{instrument}-{sess_str}-rr{rr_str}"

    return f"bt-{descriptor}-{_short_hash()}"


def generate_optimization_id(result: dict) -> str:
    """Generate an optimization ID: ``opt-{descriptor}-{hash6}``."""
    all_results = result.get("all_results", [])
    swept_params = result.get("swept_params", {})

    instrument = "unk"
    if all_results:
        instrument = all_results[0].get("config", {}).get("instrument", "unk").lower()

    abbrevs = [
        _PARAM_ABBREV.get(p, _slugify(p, max_len=10))
        for p in sorted(swept_params.keys())
    ]

    n_combos = result.get("total_combinations", len(all_results))

    parts = [instrument] + abbrevs + [f"{n_combos}c"]
    descriptor = "-".join(parts)[:40]

    return f"opt-{descriptor}-{_short_hash()}"


def _build_equity_curve(trades: list[TradeResult]) -> list[dict]:
    """Build cumulative equity curve from filled trades.

    Returns list of {date, pnl_cumulative, pnl_per_trade} dicts.
    """
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return []

    cumulative = 0.0
    curve = []
    for t in filled:
        cumulative += t.pnl_usd
        curve.append({
            "date": t.date,
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t.pnl_usd, 2),
        })
    return curve


def _apply_replay_filters(
    trades: list[TradeResult],
    config: StrategyConfig,
) -> list[TradeResult]:
    """Apply config-driven replay filters before computing metrics or saving."""
    filtered = trades
    if config.excluded_days:
        filtered = apply_dow_filter(filtered, set(config.excluded_days))
    return filtered


def results_to_dict(
    trades: list[TradeResult],
    config: StrategyConfig,
    include_trades: bool = True,
    include_equity_curve: bool = False,
) -> dict:
    """Convert backtest results to a structured dict.

    Args:
        trades: List of TradeResult from the simulator.
        config: Strategy configuration used for this run.
        include_trades: Whether to include the full trade list.

    Returns:
        Dict ready for json.dumps() or LLM consumption.
    """
    trades = _apply_replay_filters(trades, config)
    metrics = compute_metrics(trades)

    # Config summary (flat, easy for LLMs to parse)
    config_dict = {
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "exit_mode": config.exit_mode,
        "runner_trail_mode": config.runner_trail_mode,
        "runner_trail_trigger_r": config.runner_trail_trigger_r,
        "runner_trail_stop_r": config.runner_trail_stop_r,
        "runner_trail_step_r": config.runner_trail_step_r,
        "runner_trail_gap_r": config.runner_trail_gap_r,
        "runner_trail_atr_pct": config.runner_trail_atr_pct,
        "risk_usd": config.risk_usd,
        "atr_length": config.atr_length,

        "min_qty": config.min_qty,
        "qty_step": config.qty_step,
    }

    if config.strategy:
        config_dict["strategy"] = config.strategy
    if config.direction_filter:
        config_dict["direction_filter"] = config.direction_filter
    config_dict["reverse_direction"] = config.reverse_direction
    config_dict["swing_n_bars"] = config.swing_n_bars
    if config.strategy in {"continuation", "reversal"}:
        config_dict["orb_trade_max_per_session"] = config.orb_trade_max_per_session
        config_dict["orb_reentry_policy"] = config.orb_reentry_policy
    if config.use_bar_magnifier:
        config_dict["bar_magnifier"] = "ON"
    else:
        config_dict["bar_magnifier"] = "OFF"
    config_dict["impulse_close_filter"] = "ON" if config.impulse_close_filter else "OFF"
    if config.half_days:
        config_dict["half_days"] = list(config.half_days)
    if config.excluded_dates:
        config_dict["excluded_dates"] = list(config.excluded_dates)
    if config.excluded_days:
        config_dict["excluded_days"] = [DOW_NAMES[d] for d in config.excluded_days]

    # Add per-session params
    for sess in config.sessions:
        prefix = sess.name.lower()
        # ORB-based params override ATR-based — only export the active one
        if sess.stop_orb_pct > 0:
            config_dict[f"{prefix}_stop_orb_pct"] = sess.stop_orb_pct
        else:
            config_dict[f"{prefix}_stop_atr_pct"] = sess.stop_atr_pct
        if getattr(sess, "min_gap_orb_pct", 0.0) > 0:
            config_dict[f"{prefix}_min_gap_orb_pct"] = sess.min_gap_orb_pct
        else:
            config_dict[f"{prefix}_min_gap_atr_pct"] = sess.min_gap_atr_pct
        if sess.qualifying_move_atr_pct > 0:
            config_dict[f"{prefix}_qualifying_move_atr_pct"] = sess.qualifying_move_atr_pct
        if sess.min_stop_points > 0:
            config_dict[f"{prefix}_min_stop_points"] = sess.min_stop_points
        if sess.min_tp1_points > 0:
            config_dict[f"{prefix}_min_tp1_points"] = sess.min_tp1_points
        if sess.orb_start and sess.orb_end:
            config_dict[f"{prefix}_orb_window"] = f"{sess.orb_start}-{sess.orb_end}"
        if sess.rth_start:
            config_dict[f"{prefix}_rth_start"] = sess.rth_start
        if sess.sweep_start and sess.sweep_end:
            config_dict[f"{prefix}_sweep_window"] = f"{sess.sweep_start}-{sess.sweep_end}"
        config_dict[f"{prefix}_entry_window"] = f"{sess.entry_start}-{sess.entry_end}"
        config_dict[f"{prefix}_flat_window"] = f"{sess.flat_start}-{sess.flat_end}"

    # LSI params
    if config.strategy in {"lsi", "htf_lsi"}:
        config_dict["lsi_fvg_window_left"] = config.lsi_fvg_window_left
        config_dict["lsi_fvg_window_right"] = config.lsi_fvg_window_right
    if config.strategy in {"lsi", "htf_lsi", "reference_lsi"}:
        config_dict["lsi_stop_mode"] = config.lsi_stop_mode
        config_dict["lsi_target_mode"] = config.lsi_target_mode
        config_dict["lsi_entry_mode"] = config.lsi_entry_mode
        config_dict["lsi_confirmation_mode"] = config.lsi_confirmation_mode
        config_dict["cisd_min_leg_bars"] = config.cisd_min_leg_bars
        config_dict["cisd_min_leg_atr_pct"] = config.cisd_min_leg_atr_pct
        config_dict["cisd_max_leg_bars"] = config.cisd_max_leg_bars
        if config.lsi_close_on_sweep_to_inversion_minutes > 0:
            config_dict["lsi_close_on_sweep_to_inversion_minutes"] = (
                config.lsi_close_on_sweep_to_inversion_minutes
            )
    if config.strategy in {"lsi", "htf_lsi", "reference_lsi"}:
        config_dict["lsi_lrlr_enabled"] = config.lsi_lrlr_enabled
        config_dict["lsi_lrlr_gate"] = config.lsi_lrlr_gate
        config_dict["lsi_lrlr_swing_n_left"] = config.lsi_lrlr_swing_n_left
        config_dict["lsi_lrlr_swing_n_right"] = config.lsi_lrlr_swing_n_right
        config_dict["lsi_lrlr_min_pivots"] = config.lsi_lrlr_min_pivots
        config_dict["lsi_lrlr_lookback_minutes"] = config.lsi_lrlr_lookback_minutes
        config_dict["lsi_lrlr_max_pivot_gap_minutes"] = config.lsi_lrlr_max_pivot_gap_minutes
        config_dict["lsi_lrlr_max_cluster_span_minutes"] = config.lsi_lrlr_max_cluster_span_minutes
        config_dict["lsi_lrlr_max_price_span_atr"] = config.lsi_lrlr_max_price_span_atr
        config_dict["lsi_lrlr_monotonic_tolerance_atr"] = config.lsi_lrlr_monotonic_tolerance_atr
        config_dict["lsi_lrlr_line_tolerance_atr"] = config.lsi_lrlr_line_tolerance_atr
        config_dict["lsi_lrlr_tp1_path_enabled"] = config.lsi_lrlr_tp1_path_enabled
        config_dict["lsi_lrlr_tp1_buffer_atr"] = config.lsi_lrlr_tp1_buffer_atr
    if config.strategy == "lsi":
        config_dict["lsi_n_left"] = config.lsi_n_left
        config_dict["lsi_n_right"] = config.lsi_n_right
        config_dict["lsi_first_fvg_only"] = config.lsi_first_fvg_only
        config_dict["lsi_clean_path"] = config.lsi_clean_path
        config_dict["lsi_be_swing_n_left"] = config.lsi_be_swing_n_left
        config_dict["lsi_cancel_on_swing"] = config.lsi_cancel_on_swing
        config_dict["lsi_sweep_gate"] = config.lsi_sweep_gate
        config_dict["lsi_stale_breach_consumes_pivot"] = config.lsi_stale_breach_consumes_pivot
    if config.strategy == "htf_lsi":
        config_dict["htf_level_tf_minutes"] = config.htf_level_tf_minutes
        config_dict["htf_n_left"] = config.htf_n_left
        config_dict["htf_trade_max_per_session"] = config.htf_trade_max_per_session
        config_dict["htf_lsi_inversion_ordinal"] = config.htf_lsi_inversion_ordinal
        config_dict["max_fvg_to_inversion_bars"] = config.max_fvg_to_inversion_bars
        config_dict["htf_lsi_include_htf_levels"] = config.htf_lsi_include_htf_levels
        config_dict["htf_lsi_include_eqhl_levels"] = config.htf_lsi_include_eqhl_levels
        config_dict["eqhl_level_tf_minutes"] = config.eqhl_level_tf_minutes
        config_dict["eqhl_n_left"] = config.eqhl_n_left
        config_dict["eqhl_tolerance_ticks"] = config.eqhl_tolerance_ticks
        config_dict["eqhl_min_touches"] = config.eqhl_min_touches
        config_dict["eqhl_lookback_bars"] = config.eqhl_lookback_bars
        config_dict["data_sweep_min_daily_atr_pct"] = config.data_sweep_min_daily_atr_pct
        config_dict["data_sweep_require_session_extreme"] = config.data_sweep_require_session_extreme
        config_dict["data_sweep_release_window_minutes"] = config.data_sweep_release_window_minutes
        if config.htf_lsi_reference_levels:
            config_dict["htf_lsi_reference_levels"] = ",".join(config.htf_lsi_reference_levels)
        if config.data_sweep_event_types:
            config_dict["data_sweep_event_types"] = ",".join(config.data_sweep_event_types)
    if config.strategy == "reference_lsi":
        config_dict["ref_lsi_gap_lookback_bars"] = config.ref_lsi_gap_lookback_bars
        config_dict["ref_lsi_inversion_max_bars"] = config.ref_lsi_inversion_max_bars
        config_dict["ref_lsi_gap_entry_edge"] = config.ref_lsi_gap_entry_edge
        config_dict["data_sweep_min_daily_atr_pct"] = config.data_sweep_min_daily_atr_pct
        config_dict["data_sweep_require_session_extreme"] = config.data_sweep_require_session_extreme
        config_dict["data_sweep_release_window_minutes"] = config.data_sweep_release_window_minutes
        if config.data_sweep_event_types:
            config_dict["data_sweep_event_types"] = ",".join(config.data_sweep_event_types)

    if config.instrument:
        config_dict["instrument"] = config.instrument.symbol
        config_dict["point_value"] = config.instrument.point_value
        config_dict["commission_per_contract"] = config.commission_per_contract

    result = {
        "config": config_dict,
        "summary": metrics,
    }

    if config.name:
        result["name"] = config.name
    if config.notes:
        result["notes"] = config.notes

    if include_equity_curve:
        result["equity_curve"] = _build_equity_curve(trades)

    if include_trades:
        result["trades"] = [
            {
                "date": t.date,
                "session": t.session,
                "direction": "long" if t.direction == 1 else "short",
                "entry_price": round(t.entry_price, 4),
                "stop_price": round(t.stop_price, 4),
                "tp1_price": round(t.tp1_price, 4),
                "tp2_price": round(t.tp2_price, 4),
                "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
                "pnl_usd": round(t.pnl_usd, 2),
                **_trade_cost_fields(t),
                "pnl_points": round(t.pnl_points, 4),
                "r_multiple": round(t.r_multiple, 3),
                "qty": t.qty,
                "gap_size": round(t.gap_size, 4),
                "risk_points": round(t.risk_points, 4),
                "entry_time": t.fill_time,
                "exit_time": t.exit_time,
                "lsi_swept_level": t.lsi_swept_level if t.lsi_swept_level else None,
                "lsi_fvg_top": t.lsi_fvg_top if t.lsi_fvg_top else None,
                "lsi_fvg_bottom": t.lsi_fvg_bottom if t.lsi_fvg_bottom else None,
                "lsi_fvg_time": t.lsi_fvg_time if t.lsi_fvg_time else None,
                "lsi_sweep_time": t.lsi_sweep_time if t.lsi_sweep_time else None,
                "lsi_confirmation_type": t.lsi_confirmation_type if t.lsi_confirmation_type else None,
                "lsi_cisd_level": t.lsi_cisd_level if t.lsi_cisd_level else None,
                "lsi_cisd_time": t.lsi_cisd_time if t.lsi_cisd_time else None,
                "reference_level_name": t.reference_level_name if t.reference_level_name else None,
                "reference_level_price": t.reference_level_price if t.reference_level_name else None,
                "htf_level_time": t.htf_level_time if t.htf_level_time else None,
                "htf_level_price": t.htf_level_price if t.htf_level_side else None,
                "htf_level_side": t.htf_level_side if t.htf_level_side else None,
                "htf_level_tf_minutes": t.htf_level_tf_minutes if t.htf_level_side else None,
                "fvg_to_inversion_bars": t.fvg_to_inversion_bars if t.htf_level_side else None,
                "sweep_to_inversion_bars": t.sweep_to_inversion_bars if t.htf_level_side else None,
                "inversion_ordinal": t.inversion_ordinal if t.htf_level_side else None,
                "lsi_lrlr_present": t.lsi_lrlr_present,
                "lsi_lrlr_level_count": t.lsi_lrlr_level_count if t.lsi_lrlr_present else None,
                "lsi_lrlr_nearest_level_price": t.lsi_lrlr_nearest_level_price if t.lsi_lrlr_present else None,
                "lsi_lrlr_farthest_level_price": t.lsi_lrlr_farthest_level_price if t.lsi_lrlr_present else None,
                "lsi_lrlr_span_bars": t.lsi_lrlr_span_bars if t.lsi_lrlr_present else None,
                "lsi_lrlr_price_span_atr": round(t.lsi_lrlr_price_span_atr, 4) if t.lsi_lrlr_present else None,
                "lsi_lrlr_slope_atr_per_bar": round(t.lsi_lrlr_slope_atr_per_bar, 6) if t.lsi_lrlr_present else None,
                "lsi_lrlr_fit_error_atr": round(t.lsi_lrlr_fit_error_atr, 6) if t.lsi_lrlr_present else None,
                "lsi_lrlr_tp1_path_present": t.lsi_lrlr_tp1_path_present if t.lsi_lrlr_present else None,
                "lsi_lrlr_nearest_tp1_gap_atr": round(t.lsi_lrlr_nearest_tp1_gap_atr, 6) if t.lsi_lrlr_present else None,
            }
            for t in trades
        ]

    return result


def vwap_results_to_dict(
    trades: list[TradeResult],
    config,  # VWAPStrategyConfig
    include_trades: bool = True,
    include_equity_curve: bool = False,
) -> dict:
    """Convert VWAP backtest results to a structured dict.

    Same shape as results_to_dict() but flattens VWAPStrategyConfig
    with VWAP-specific session-prefixed params.
    """
    metrics = compute_metrics(trades)

    config_dict = {
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "risk_usd": config.risk_usd,
        "atr_length": config.atr_length,
        "min_qty": config.min_qty,
        "qty_step": config.qty_step,
        "tp2_mode": config.tp2_mode,
        "strategy": "vwap_reversion",
    }

    if config.direction_filter:
        config_dict["direction_filter"] = config.direction_filter
    if config.use_bar_magnifier:
        config_dict["bar_magnifier"] = "ON"

    # Add per-session params
    for sess in config.sessions:
        prefix = sess.name.lower()
        config_dict[f"{prefix}_entry_window"] = f"{sess.entry_start}-{sess.entry_end}"
        config_dict[f"{prefix}_flat_window"] = f"{sess.flat_start}-{sess.flat_end}"
        config_dict[f"{prefix}_deviation_atr_pct"] = sess.deviation_atr_pct
        config_dict[f"{prefix}_deviation_std"] = sess.deviation_std
        config_dict[f"{prefix}_deviation_mode"] = sess.deviation_mode
        config_dict[f"{prefix}_rejection_mode"] = sess.rejection_mode
        config_dict[f"{prefix}_stop_atr_pct"] = sess.stop_atr_pct
        config_dict[f"{prefix}_vwap_anchor"] = sess.vwap_anchor
        if sess.min_wick_atr_pct > 0:
            config_dict[f"{prefix}_min_wick_atr_pct"] = sess.min_wick_atr_pct
        if sess.max_body_atr_pct > 0:
            config_dict[f"{prefix}_max_body_atr_pct"] = sess.max_body_atr_pct

    if config.instrument:
        config_dict["instrument"] = config.instrument.symbol
        config_dict["point_value"] = config.instrument.point_value
        config_dict["commission_per_contract"] = config.commission_per_contract

    # Flatten VWAP-specific params to top level for DB column matching
    # Take from first session (for single-session configs)
    if config.sessions:
        first_sess = config.sessions[0]
        config_dict["deviation_atr_pct"] = first_sess.deviation_atr_pct
        config_dict["deviation_std"] = first_sess.deviation_std
        config_dict["deviation_mode"] = first_sess.deviation_mode
        config_dict["rejection_mode"] = first_sess.rejection_mode
        config_dict["tp2_mode"] = config.tp2_mode
        config_dict["vwap_anchor"] = first_sess.vwap_anchor
        config_dict["stop_atr_buffer_pct"] = first_sess.stop_atr_pct

    result = {
        "config": config_dict,
        "summary": metrics,
    }

    if config.name:
        result["name"] = config.name
    if config.notes:
        result["notes"] = config.notes

    if include_equity_curve:
        result["equity_curve"] = _build_equity_curve(trades)

    if include_trades:
        result["trades"] = [
            {
                "date": t.date,
                "session": t.session,
                "direction": "long" if t.direction == 1 else "short",
                "entry_price": round(t.entry_price, 4),
                "stop_price": round(t.stop_price, 4),
                "tp1_price": round(t.tp1_price, 4),
                "tp2_price": round(t.tp2_price, 4),
                "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
                "pnl_usd": round(t.pnl_usd, 2),
                **_trade_cost_fields(t),
                "pnl_points": round(t.pnl_points, 4),
                "r_multiple": round(t.r_multiple, 3),
                "qty": t.qty,
                "gap_size": round(t.gap_size, 4),
                "risk_points": round(t.risk_points, 4),
                "entry_time": t.fill_time,
                "exit_time": t.exit_time,
            }
            for t in trades
        ]

    return result


def vwap_grid_results_to_dict(
    all_results: list[tuple],  # list of (VWAPStrategyConfig, list[TradeResult])
    swept_params: dict[str, list] | None = None,
) -> dict:
    """Convert VWAP grid sweep results to a summary dict."""
    summaries = []
    for config, trades in all_results:
        d = vwap_results_to_dict(trades, config, include_trades=False)
        summaries.append(d)

    filled_summaries = [s for s in summaries if s["summary"]["total_trades"] > 0]

    best_by_sharpe = max(filled_summaries, key=lambda s: s["summary"]["sharpe_ratio"]) if filled_summaries else None
    best_by_pnl = max(filled_summaries, key=lambda s: s["summary"]["total_pnl_usd"]) if filled_summaries else None
    best_by_pf = max(filled_summaries, key=lambda s: s["summary"]["profit_factor"]) if filled_summaries else None
    best_by_calmar = max(filled_summaries, key=lambda s: s["summary"].get("calmar_ratio", 0)) if filled_summaries else None

    result = {
        "total_combinations": len(summaries),
        "best_by_sharpe": best_by_sharpe,
        "best_by_pnl": best_by_pnl,
        "best_by_profit_factor": best_by_pf,
        "best_by_calmar": best_by_calmar,
        "all_results": summaries,
    }

    if swept_params is not None:
        def _coerce(v):
            try:
                return float(v)
            except (ValueError, TypeError):
                return v
        result["swept_params"] = {k: [_coerce(v) for v in vs] for k, vs in swept_params.items()}

    return result


def gapfill_results_to_dict(
    trades: list[TradeResult],
    config,  # GapFillStrategyConfig
    include_trades: bool = True,
    include_equity_curve: bool = False,
) -> dict:
    """Convert Gap Fill backtest results to a structured dict."""
    metrics = compute_metrics(trades)

    config_dict = {
        "stop_multiplier": config.stop_multiplier,
        "tp1_ratio": config.tp1_ratio,
        "risk_usd": config.risk_usd,
        "atr_length": config.atr_length,
        "min_gap_atr_pct": config.min_gap_atr_pct,
        "max_gap_atr_pct": config.max_gap_atr_pct,
        "min_gap_points": config.min_gap_points,
        "max_gap_staleness_days": config.max_gap_staleness_days,
        "min_qty": config.min_qty,
        "qty_step": config.qty_step,
        "strategy": "gap_fill",
    }

    if config.direction_filter:
        config_dict["direction_filter"] = config.direction_filter
    if config.use_bar_magnifier:
        config_dict["bar_magnifier"] = "ON"

    # Per-session params
    for sess in config.sessions:
        prefix = sess.name.lower()
        config_dict[f"{prefix}_rth_open"] = sess.rth_open
        config_dict[f"{prefix}_flat_window"] = f"{sess.flat_start}-{sess.flat_end}"

    if config.instrument:
        config_dict["instrument"] = config.instrument.symbol
        config_dict["point_value"] = config.instrument.point_value

    result = {
        "config": config_dict,
        "summary": metrics,
    }

    if config.name:
        result["name"] = config.name
    if config.notes:
        result["notes"] = config.notes

    if include_equity_curve:
        result["equity_curve"] = _build_equity_curve(trades)

    if include_trades:
        result["trades"] = [
            {
                "date": t.date,
                "session": t.session,
                "direction": "long" if t.direction == 1 else "short",
                "entry_price": round(t.entry_price, 4),
                "stop_price": round(t.stop_price, 4),
                "tp1_price": round(t.tp1_price, 4),
                "tp2_price": round(t.tp2_price, 4),
                "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
                "pnl_usd": round(t.pnl_usd, 2),
                **_trade_cost_fields(t),
                "pnl_points": round(t.pnl_points, 4),
                "r_multiple": round(t.r_multiple, 3),
                "qty": t.qty,
                "gap_size": round(t.gap_size, 4),
                "risk_points": round(t.risk_points, 4),
                "entry_time": t.fill_time,
                "exit_time": t.exit_time,
            }
            for t in trades
        ]

    return result


def gapfill_grid_results_to_dict(
    all_results: list[tuple],  # list of (GapFillStrategyConfig, list[TradeResult])
    swept_params: dict[str, list] | None = None,
) -> dict:
    """Convert Gap Fill grid sweep results to a summary dict."""
    summaries = []
    for config, trades in all_results:
        d = gapfill_results_to_dict(trades, config, include_trades=False)
        summaries.append(d)

    filled_summaries = [s for s in summaries if s["summary"]["total_trades"] > 0]

    best_by_sharpe = max(filled_summaries, key=lambda s: s["summary"]["sharpe_ratio"]) if filled_summaries else None
    best_by_pnl = max(filled_summaries, key=lambda s: s["summary"]["total_pnl_usd"]) if filled_summaries else None
    best_by_pf = max(filled_summaries, key=lambda s: s["summary"]["profit_factor"]) if filled_summaries else None
    best_by_calmar = max(filled_summaries, key=lambda s: s["summary"].get("calmar_ratio", 0)) if filled_summaries else None

    result = {
        "total_combinations": len(summaries),
        "best_by_sharpe": best_by_sharpe,
        "best_by_pnl": best_by_pnl,
        "best_by_profit_factor": best_by_pf,
        "best_by_calmar": best_by_calmar,
        "all_results": summaries,
    }

    if swept_params is not None:
        def _coerce(v):
            try:
                return float(v)
            except (ValueError, TypeError):
                return v
        result["swept_params"] = {k: [_coerce(v) for v in vs] for k, vs in swept_params.items()}

    return result


def save_backtest_result(result: dict) -> str:
    """Save a backtest result to the DB and return its ID.

    ID format: ``bt-{descriptor}-{hash6}``
    """
    result_id = generate_backtest_id(result)
    log_run(result, result_id)
    return result_id


def load_backtest_result(result_id: str) -> dict | None:
    """Load a full backtest result by ID from the DB."""
    return get_backtest_result(result_id)


def delete_backtest_result(result_id: str) -> bool:
    """Delete a saved backtest result from the DB."""
    return delete_backtest_run(result_id)


def grid_results_to_dict(
    all_results: list[tuple[StrategyConfig, list[TradeResult]]],
    swept_params: dict[str, list] | None = None,
) -> dict:
    """Convert grid sweep results to a summary dict.

    Args:
        all_results: List of (config, trades) tuples from grid sweep.
        swept_params: Optional dict mapping param names to swept values.

    Returns:
        Dict with best results and all combination summaries.
    """
    summaries = []
    for config, trades in all_results:
        d = results_to_dict(trades, config, include_trades=False)
        summaries.append(d)

    # Find best by different metrics
    filled_summaries = [s for s in summaries if s["summary"]["total_trades"] > 0]

    best_by_sharpe = max(filled_summaries, key=lambda s: s["summary"]["sharpe_ratio"]) if filled_summaries else None
    best_by_pnl = max(filled_summaries, key=lambda s: s["summary"]["total_pnl_usd"]) if filled_summaries else None
    best_by_pf = max(filled_summaries, key=lambda s: s["summary"]["profit_factor"]) if filled_summaries else None
    best_by_calmar = max(filled_summaries, key=lambda s: s["summary"].get("calmar_ratio", 0)) if filled_summaries else None

    result = {
        "total_combinations": len(summaries),
        "best_by_sharpe": best_by_sharpe,
        "best_by_pnl": best_by_pnl,
        "best_by_profit_factor": best_by_pf,
        "best_by_calmar": best_by_calmar,
        "all_results": summaries,
    }

    if swept_params is not None:
        def _coerce(v):
            try:
                return float(v)
            except (ValueError, TypeError):
                return v
        result["swept_params"] = {k: [_coerce(v) for v in vs] for k, vs in swept_params.items()}

    return result


def save_optimization_result(result: dict) -> str:
    """Save an optimization result to the DB and return its ID.

    ID format: ``opt-{descriptor}-{hash6}``
    """
    result_id = generate_optimization_id(result)
    log_optimization(result, result_id)
    return result_id


def list_optimization_results() -> list[dict]:
    """List all saved optimization results as metadata dicts, newest first."""
    return list_optimization_history()


def load_optimization_result(result_id: str) -> dict | None:
    """Load a full optimization result by ID from the DB."""
    return get_optimization_result(result_id)


def delete_optimization_result(result_id: str) -> bool:
    """Delete a saved optimization result from the DB."""
    return delete_optimization_run(result_id)


def _trades_to_minimal(trades: list[TradeResult]) -> list[dict]:
    """Convert trades to minimal dicts (for compact storage in optimization results)."""
    return [
        {
            "date": t.date,
            "session": t.session,
            "direction": "long" if t.direction == 1 else "short",
            "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
            "pnl_usd": round(t.pnl_usd, 2),
            **_trade_cost_fields(t),
            "r_multiple": round(t.r_multiple, 3),
        }
        for t in trades
        if t.exit_type != EXIT_NO_FILL
    ]


def get_experiment_history(limit: int = 50, **filters) -> list[dict]:
    """Query experiment history from the SQLite DB.

    Convenience wrapper for API/dashboard use.
    """
    from ..experiments import query_runs
    return query_runs(limit=limit, **filters)
