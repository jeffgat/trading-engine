#!/usr/bin/env python3
"""Investigate exit-structure variants for the active ALPHA_V1 legs.

This script keeps the entry logic fixed to the current ALPHA_V1 lineup, then
replays each filled trade with alternative exit policies so we can answer:

1. Does the current TP1/TP2 partialing outperform an all-or-nothing full TP?
2. What happens if we split the take-profit into three levels?
3. What happens if we scale out on drawdown instead of scaling out on strength?
4. What do session-level MAE / MFE distributions imply about practical target
   sizing for prop-firm drawdown constraints?

Important caveat:
    These counterfactuals keep the original fills fixed. That is exact for the
    cap=1 ORB legs. It is only an approximation for the active NQ NY HTF-LSI
    leg because alternative exits could slightly change same-session re-entry
    availability on cap=2 days.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES, NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult, build_maps, run_backtest
from orb_backtest.results.metrics import compute_metrics

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config


DEFAULT_RECENT_START = "2024-01-01"
OUTPUT_DIR = ROOT / "data" / "results" / "alpha_v1_exit_structure_analysis_20260423"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_EXIT_STRUCTURE_ANALYSIS.md"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"
TRADE_CSV_PATH = OUTPUT_DIR / "policy_trade_analysis.csv"
TARGET_FRONTIER_CSV_PATH = OUTPUT_DIR / "target_frontier.csv"


@dataclass(frozen=True)
class LegSpec:
    key: str
    label: str
    symbol: str
    config: StrategyConfig


@dataclass(frozen=True)
class ProfitStep:
    r_multiple: float
    fraction: float
    label: str
    move_stop_to_be: bool = False


@dataclass(frozen=True)
class StopScaleStep:
    adverse_r: float
    fraction: float
    label: str


@dataclass(frozen=True)
class PolicySpec:
    key: str
    label: str
    kind: str


@dataclass
class SymbolData:
    df_5m: pd.DataFrame
    df_1m: pd.DataFrame
    df_1s: pd.DataFrame | None
    maps: dict
    ts_1m_ns: np.ndarray
    high_1m: np.ndarray
    low_1m: np.ndarray
    close_1m: np.ndarray
    ts_1s_ns: np.ndarray | None
    high_1s: np.ndarray | None
    low_1s: np.ndarray | None
    close_1s: np.ndarray | None


def build_active_legs() -> list[LegSpec]:
    return [
        LegSpec(
            key="nq_ny_htf_lsi",
            label="HTF_LSI/NQ_NY-L24",
            symbol="NQ",
            config=build_current_nq_ny_htf_lsi_lag24_config(
                name="ALPHA_V1 NQ NY HTF_LSI baseline",
            ),
        ),
        LegSpec(
            key="nq_asia_orb",
            label="ORB/NQ_ASIA-RR6",
            symbol="NQ",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="Asia",
                        orb_start="20:00",
                        orb_end="20:15",
                        entry_start="20:15",
                        entry_end="22:30",
                        flat_start="04:00",
                        flat_end="07:00",
                        stop_orb_pct=100.0,
                        min_gap_orb_pct=10.0,
                    ),
                ),
                instrument=NQ,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=6.0,
                tp1_ratio=0.3,
                atr_length=5,
                excluded_days=(1,),
                name="ALPHA_V1 NQ Asia ORB baseline",
            ),
        ),
        LegSpec(
            key="es_asia_cont",
            label="ORB/ES_ASIA-RR1.5",
            symbol="ES",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="Asia",
                        orb_start="20:00",
                        orb_end="20:15",
                        entry_start="20:15",
                        entry_end="03:00",
                        flat_start="07:00",
                        flat_end="07:00",
                        stop_orb_pct=125.0,
                        min_gap_atr_pct=0.5,
                        min_stop_points=3.0,
                        min_tp1_points=3.0,
                    ),
                ),
                instrument=ES,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=1.5,
                tp1_ratio=0.7,
                atr_length=14,
                name="ALPHA_V1 ES Asia continuation baseline",
            ),
        ),
        LegSpec(
            key="es_ny_cont",
            label="ORB/ES_NY-RR5",
            symbol="ES",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="NY",
                        orb_start="09:30",
                        orb_end="09:45",
                        entry_start="09:45",
                        entry_end="13:00",
                        flat_start="15:50",
                        flat_end="16:00",
                        stop_atr_pct=5.0,
                        min_gap_atr_pct=0.25,
                        min_stop_points=3.0,
                        min_tp1_points=3.0,
                    ),
                ),
                instrument=ES,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=5.0,
                tp1_ratio=0.2,
                atr_length=7,
                excluded_days=(3,),
                name="ALPHA_V1 ES NY continuation baseline",
            ),
        ),
    ]


POLICIES = (
    PolicySpec("baseline_replay", "Current TP1/TP2 replay", "baseline"),
    PolicySpec("full_target_only", "Full TP only", "full_target_only"),
    PolicySpec("tp3_midpoint", "3-level TP (TP1 / midpoint / TP2)", "tp3_midpoint"),
    PolicySpec("drawdown_scale_50", "Drawdown scale (50% at -0.5R, rest at -1R)", "drawdown_scale_50"),
)


def _safe_round(value: float, digits: int = 4) -> float:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return 0.0
    return round(float(value), digits)


def _fraction(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return out.dropna(subset=["open", "high", "low", "close"]).astype(float)


def load_symbol_data(filename_5m: str, *, start: str | None, end: str | None) -> SymbolData:
    df_1s = load_1s_for_5m(filename_5m, start=start, end=end)

    try:
        df_5m = load_5m_data(filename_5m, start=start, end=end)
    except FileNotFoundError:
        if df_1s is None:
            raise
        df_5m = _resample_ohlcv(df_1s, "5min")

    try:
        df_1m = load_1m_for_5m(filename_5m, start=start, end=end)
    except FileNotFoundError:
        if df_1s is None:
            raise
        df_1m = _resample_ohlcv(df_1s, "1min")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)

    ts_1m_ns = df_1m.index.view("i8")
    high_1m = np.ascontiguousarray(df_1m["high"].to_numpy(dtype=np.float64))
    low_1m = np.ascontiguousarray(df_1m["low"].to_numpy(dtype=np.float64))
    close_1m = np.ascontiguousarray(df_1m["close"].to_numpy(dtype=np.float64))

    if df_1s is not None:
        ts_1s_ns = df_1s.index.view("i8")
        high_1s = np.ascontiguousarray(df_1s["high"].to_numpy(dtype=np.float64))
        low_1s = np.ascontiguousarray(df_1s["low"].to_numpy(dtype=np.float64))
        close_1s = np.ascontiguousarray(df_1s["close"].to_numpy(dtype=np.float64))
    else:
        ts_1s_ns = None
        high_1s = None
        low_1s = None
        close_1s = None

    return SymbolData(
        df_5m=df_5m,
        df_1m=df_1m,
        df_1s=df_1s,
        maps=maps,
        ts_1m_ns=ts_1m_ns,
        high_1m=high_1m,
        low_1m=low_1m,
        close_1m=close_1m,
        ts_1s_ns=ts_1s_ns,
        high_1s=high_1s,
        low_1s=low_1s,
        close_1s=close_1s,
    )


def _build_trade_dict(trade: TradeResult) -> dict:
    return {
        "date": trade.date,
        "session": trade.session,
        "direction": "long" if trade.direction == 1 else "short",
        "entry_price": float(trade.entry_price),
        "stop_price": float(trade.stop_price),
        "tp1_price": float(trade.tp1_price),
        "tp2_price": float(trade.tp2_price),
        "exit_type": EXIT_NAMES.get(trade.exit_type, "unknown"),
        "pnl_usd": float(trade.pnl_usd),
        "pnl_points": float(trade.pnl_points),
        "r_multiple": float(trade.r_multiple),
        "qty": float(trade.qty),
        "gap_size": float(trade.gap_size),
        "risk_points": float(trade.risk_points),
        "fill_time": trade.fill_time,
        "exit_time": trade.exit_time,
    }


def _summarize_trade_dicts(trades: list[dict]) -> dict:
    filled = [t for t in trades if t["exit_type"] != "no_fill"]
    if not filled:
        return {
            "total_signals": len(trades),
            "filled_trades": 0,
            "no_fills": len(trades),
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_r": 0.0,
            "total_r": 0.0,
            "max_drawdown_r": 0.0,
            "calmar_ratio": 0.0,
            "exit_breakdown": {"no_fill": len(trades)},
        }

    r_values = np.array([float(t["r_multiple"]) for t in filled], dtype=np.float64)
    pnl_values = np.array([float(t["pnl_usd"]) for t in filled], dtype=np.float64)
    wins = pnl_values > 0
    losses = pnl_values < 0
    total_wins = float(np.sum(pnl_values[wins]))
    total_losses = float(np.sum(pnl_values[losses]))

    r_equity = np.cumsum(r_values)
    r_peak = np.maximum.accumulate(r_equity)
    r_drawdown = r_equity - r_peak
    max_drawdown_r = abs(float(np.min(r_drawdown))) if len(r_drawdown) else 0.0
    total_r = float(r_equity[-1]) if len(r_equity) else 0.0
    calmar = (total_r / max_drawdown_r) if max_drawdown_r > 0 else 0.0

    exit_breakdown: dict[str, int] = {}
    for trade in trades:
        exit_breakdown[trade["exit_type"]] = exit_breakdown.get(trade["exit_type"], 0) + 1

    return {
        "total_signals": len(trades),
        "filled_trades": len(filled),
        "no_fills": exit_breakdown.get("no_fill", 0),
        "win_rate": float(np.mean(wins)) if len(filled) else 0.0,
        "profit_factor": abs(total_wins / total_losses) if total_losses != 0 else 0.0,
        "avg_r": float(np.mean(r_values)) if len(r_values) else 0.0,
        "total_r": total_r,
        "max_drawdown_r": max_drawdown_r,
        "calmar_ratio": calmar,
        "exit_breakdown": exit_breakdown,
    }


def _slice_trade_dicts(trades: list[dict], *, start: str | None = None, end: str | None = None) -> list[dict]:
    out: list[dict] = []
    for trade in trades:
        if start is not None and trade["date"] < start:
            continue
        if end is not None and trade["date"] >= end:
            continue
        out.append(trade)
    return out


def _favorable_r(direction: int, entry_price: float, price: float, risk_points: float) -> float:
    if risk_points <= 0:
        return 0.0
    if direction == 1:
        return max(0.0, (price - entry_price) / risk_points)
    return max(0.0, (entry_price - price) / risk_points)


def _adverse_r(direction: int, entry_price: float, price: float, risk_points: float) -> float:
    if risk_points <= 0:
        return 0.0
    if direction == 1:
        return max(0.0, (entry_price - price) / risk_points)
    return max(0.0, (price - entry_price) / risk_points)


def _price_for_profit_r(direction: int, entry_price: float, risk_points: float, r_multiple: float) -> float:
    if direction == 1:
        return entry_price + risk_points * r_multiple
    return entry_price - risk_points * r_multiple


def _price_for_adverse_r(direction: int, entry_price: float, risk_points: float, adverse_r: float) -> float:
    if direction == 1:
        return entry_price - risk_points * adverse_r
    return entry_price + risk_points * adverse_r


def _first_flat_timestamp(fill_time: pd.Timestamp, flat_start: str) -> pd.Timestamp:
    hh, mm = (int(part) for part in flat_start.split(":"))
    flat_ts = fill_time.normalize() + pd.Timedelta(hours=hh, minutes=mm)
    if flat_ts < fill_time:
        flat_ts += pd.Timedelta(days=1)
    return flat_ts


def _crosses_adverse(direction: int, high_price: float, low_price: float, level_price: float) -> bool:
    if direction == 1:
        return low_price <= level_price
    return high_price >= level_price


def _crosses_profit(direction: int, high_price: float, low_price: float, level_price: float) -> bool:
    if direction == 1:
        return high_price >= level_price
    return low_price <= level_price


def _make_policy_steps(trade: TradeResult, policy: PolicySpec) -> tuple[list[dict], list[dict]]:
    tp1_r = _favorable_r(trade.direction, trade.entry_price, trade.tp1_price, trade.risk_points)
    tp2_r = _favorable_r(trade.direction, trade.entry_price, trade.tp2_price, trade.risk_points)
    half_fraction = _fraction(trade.half_qty / trade.qty) if trade.qty > 0 else 0.5
    remainder_fraction = _fraction(1.0 - half_fraction)

    if policy.kind == "baseline":
        if trade.half_qty >= trade.qty - 1e-9:
            profit_steps = [
                {
                    "label": "tp1_be_trigger",
                    "r_multiple": tp1_r,
                    "fraction": 0.0,
                    "price": trade.tp1_price,
                    "move_stop_to_be": True,
                },
                {
                    "label": "tp2_full",
                    "r_multiple": tp2_r,
                    "fraction": 1.0,
                    "price": trade.tp2_price,
                    "move_stop_to_be": False,
                },
            ]
        else:
            profit_steps = [
                {
                    "label": "tp1_partial",
                    "r_multiple": tp1_r,
                    "fraction": half_fraction,
                    "price": trade.tp1_price,
                    "move_stop_to_be": True,
                },
                {
                    "label": "tp2_final",
                    "r_multiple": tp2_r,
                    "fraction": remainder_fraction,
                    "price": trade.tp2_price,
                    "move_stop_to_be": False,
                },
            ]
        stop_steps: list[dict] = []
        return profit_steps, stop_steps

    if policy.kind == "full_target_only":
        return [
            {
                "label": "tp_full",
                "r_multiple": tp2_r,
                "fraction": 1.0,
                "price": trade.tp2_price,
                "move_stop_to_be": False,
            }
        ], []

    if policy.kind == "tp3_midpoint":
        midpoint_r = (tp1_r + tp2_r) / 2.0
        midpoint_price = _price_for_profit_r(trade.direction, trade.entry_price, trade.risk_points, midpoint_r)
        return [
            {
                "label": "tp1_third",
                "r_multiple": tp1_r,
                "fraction": 1.0 / 3.0,
                "price": trade.tp1_price,
                "move_stop_to_be": True,
            },
            {
                "label": "tp2_mid",
                "r_multiple": midpoint_r,
                "fraction": 1.0 / 3.0,
                "price": midpoint_price,
                "move_stop_to_be": False,
            },
            {
                "label": "tp3_final",
                "r_multiple": tp2_r,
                "fraction": 1.0 / 3.0,
                "price": trade.tp2_price,
                "move_stop_to_be": False,
            },
        ], []

    if policy.kind == "drawdown_scale_50":
        return [
            {
                "label": "tp_full",
                "r_multiple": tp2_r,
                "fraction": 1.0,
                "price": trade.tp2_price,
                "move_stop_to_be": False,
            }
        ], [
            {
                "label": "sl1_half",
                "adverse_r": 0.5,
                "fraction": 0.5,
                "price": _price_for_adverse_r(trade.direction, trade.entry_price, trade.risk_points, 0.5),
            },
        ]

    raise ValueError(f"Unsupported policy {policy.kind!r}")


def _make_target_frontier_steps(trade: TradeResult, final_target_r: float) -> tuple[list[dict], list[dict]]:
    tp1_r = _favorable_r(trade.direction, trade.entry_price, trade.tp1_price, trade.risk_points)
    half_fraction = _fraction(trade.half_qty / trade.qty) if trade.qty > 0 else 0.5
    remainder_fraction = _fraction(1.0 - half_fraction)
    final_price = _price_for_profit_r(trade.direction, trade.entry_price, trade.risk_points, final_target_r)

    if trade.half_qty >= trade.qty - 1e-9:
        return [
            {
                "label": "tp1_be_trigger",
                "r_multiple": tp1_r,
                "fraction": 0.0,
                "price": trade.tp1_price,
                "move_stop_to_be": True,
            },
            {
                "label": "tp_final",
                "r_multiple": final_target_r,
                "fraction": 1.0,
                "price": final_price,
                "move_stop_to_be": False,
            },
        ], []

    return [
        {
            "label": "tp1_partial",
            "r_multiple": tp1_r,
            "fraction": half_fraction,
            "price": trade.tp1_price,
            "move_stop_to_be": True,
        },
        {
            "label": "tp_final",
            "r_multiple": final_target_r,
            "fraction": remainder_fraction,
            "price": final_price,
            "move_stop_to_be": False,
        },
    ], []


def _process_adverse_event(
    trade: TradeResult,
    state: dict,
    level_price: float,
    label: str,
    fraction: float | None,
) -> None:
    remaining = state["remaining_fraction"]
    if remaining <= 1e-12:
        return

    if fraction is None:
        realized_fraction = remaining
    else:
        realized_fraction = min(remaining, _fraction(fraction))

    if trade.direction == 1:
        pnl_points = (level_price - trade.entry_price) * realized_fraction
    else:
        pnl_points = (trade.entry_price - level_price) * realized_fraction

    state["realized_points"] += pnl_points
    state["remaining_fraction"] = max(0.0, remaining - realized_fraction)
    state["exit_label"] = label
    if fraction is None or state["remaining_fraction"] <= 1e-12:
        state["closed"] = True


def _process_profit_event(trade: TradeResult, state: dict, step: dict) -> None:
    remaining = state["remaining_fraction"]
    if remaining <= 1e-12:
        return

    realized_fraction = min(remaining, _fraction(step["fraction"]))
    if realized_fraction > 0:
        if trade.direction == 1:
            pnl_points = (step["price"] - trade.entry_price) * realized_fraction
        else:
            pnl_points = (trade.entry_price - step["price"]) * realized_fraction
        state["realized_points"] += pnl_points
        state["remaining_fraction"] = max(0.0, remaining - realized_fraction)

    if step["move_stop_to_be"]:
        state["current_stop_price"] = trade.entry_price
        state["stop_steps"] = []
    state["exit_label"] = step["label"]
    if state["remaining_fraction"] <= 1e-12:
        state["closed"] = True


def _process_bar_events(
    trade: TradeResult,
    state: dict,
    high_price: float,
    low_price: float,
    close_price: float,
    *,
    consider_profit: bool,
    is_aggregate_bar: bool,
) -> None:
    direction = trade.direction
    current_stop = state["current_stop_price"]

    adverse_events: list[tuple[str, float, float | None]] = []
    if _crosses_adverse(direction, high_price, low_price, current_stop):
        adverse_events.append(("hard_stop", current_stop, None))
    for step in state["stop_steps"]:
        if _crosses_adverse(direction, high_price, low_price, step["price"]):
            adverse_events.append((step["label"], step["price"], step["fraction"]))

    if direction == 1:
        adverse_events.sort(key=lambda row: row[1], reverse=True)
    else:
        adverse_events.sort(key=lambda row: row[1])

    profit_events: list[dict] = []
    if consider_profit:
        for step in state["profit_steps"]:
            if _crosses_profit(direction, high_price, low_price, step["price"]):
                profit_events.append(step)
        if direction == 1:
            profit_events.sort(key=lambda step: step["price"])
        else:
            profit_events.sort(key=lambda step: step["price"], reverse=True)

    if consider_profit and adverse_events and profit_events:
        label, level_price, fraction = adverse_events[0]
        _process_adverse_event(trade, state, level_price, label, fraction)
        return

    if adverse_events:
        used_stop_labels = set()
        for label, level_price, fraction in adverse_events:
            if state["closed"]:
                break
            if label in used_stop_labels:
                continue
            _process_adverse_event(trade, state, level_price, label, fraction)
            used_stop_labels.add(label)
        state["stop_steps"] = [step for step in state["stop_steps"] if step["label"] not in used_stop_labels]
        return

    if not consider_profit:
        return

    used_profit_labels = set()
    for step in profit_events:
        if state["closed"]:
            break
        if step["label"] in used_profit_labels:
            continue
        _process_profit_event(trade, state, step)
        used_profit_labels.add(step["label"])

        if is_aggregate_bar and not state["closed"]:
            if _crosses_adverse(direction, high_price, low_price, state["current_stop_price"]):
                _process_adverse_event(trade, state, state["current_stop_price"], "hard_stop", None)
                break

    if used_profit_labels:
        state["profit_steps"] = [
            step for step in state["profit_steps"] if step["label"] not in used_profit_labels
        ]


def replay_trade(
    trade: TradeResult,
    leg: LegSpec,
    symbol_data: SymbolData,
    *,
    policy: PolicySpec | None = None,
    custom_target_r: float | None = None,
) -> dict:
    if trade.exit_type == EXIT_NO_FILL:
        record = _build_trade_dict(trade)
        record.update(
            {
                "mae_r": 0.0,
                "mfe_r": 0.0,
                "replay_validation": True,
                "session_flat_time": None,
            }
        )
        return record

    if policy is None and custom_target_r is None:
        raise ValueError("Either a policy or a custom target R must be provided")

    if custom_target_r is not None:
        profit_steps, stop_steps = _make_target_frontier_steps(trade, custom_target_r)
        policy_label = f"target_frontier_{custom_target_r:g}R"
    else:
        assert policy is not None
        profit_steps, stop_steps = _make_policy_steps(trade, policy)
        policy_label = policy.key

    fill_time = pd.Timestamp(trade.fill_time)
    flat_time = _first_flat_timestamp(fill_time, leg.config.sessions[0].flat_start)
    end_cutoff = flat_time + pd.Timedelta(minutes=1)

    start_idx = int(np.searchsorted(symbol_data.ts_1m_ns, fill_time.value, side="left"))
    end_idx = int(np.searchsorted(symbol_data.ts_1m_ns, end_cutoff.value, side="left")) - 1
    end_idx = min(end_idx, len(symbol_data.ts_1m_ns) - 1)

    state = {
        "remaining_fraction": 1.0,
        "realized_points": 0.0,
        "current_stop_price": float(trade.stop_price),
        "profit_steps": [dict(step) for step in profit_steps],
        "stop_steps": [dict(step) for step in stop_steps],
        "closed": False,
        "exit_label": "eod",
        "exit_time": None,
    }

    max_favorable_r = 0.0
    max_adverse_r = 0.0

    for minute_idx in range(start_idx, end_idx + 1):
        minute_ts_ns = int(symbol_data.ts_1m_ns[minute_idx])
        minute_ts = pd.Timestamp(minute_ts_ns)
        high_1m = float(symbol_data.high_1m[minute_idx])
        low_1m = float(symbol_data.low_1m[minute_idx])
        close_1m = float(symbol_data.close_1m[minute_idx])

        if trade.direction == 1:
            max_favorable_r = max(max_favorable_r, _favorable_r(trade.direction, trade.entry_price, high_1m, trade.risk_points))
            max_adverse_r = max(max_adverse_r, _adverse_r(trade.direction, trade.entry_price, low_1m, trade.risk_points))
        else:
            max_favorable_r = max(max_favorable_r, _favorable_r(trade.direction, trade.entry_price, low_1m, trade.risk_points))
            max_adverse_r = max(max_adverse_r, _adverse_r(trade.direction, trade.entry_price, high_1m, trade.risk_points))

        is_flat_bar = minute_ts >= flat_time

        levels_crossed = False
        if _crosses_adverse(trade.direction, high_1m, low_1m, state["current_stop_price"]):
            levels_crossed = True
        if not levels_crossed:
            for step in state["stop_steps"]:
                if _crosses_adverse(trade.direction, high_1m, low_1m, step["price"]):
                    levels_crossed = True
                    break
        if not levels_crossed and not is_flat_bar:
            for step in state["profit_steps"]:
                if _crosses_profit(trade.direction, high_1m, low_1m, step["price"]):
                    levels_crossed = True
                    break

        if levels_crossed and symbol_data.ts_1s_ns is not None:
            second_start = int(np.searchsorted(symbol_data.ts_1s_ns, minute_ts_ns, side="left"))
            second_end = int(
                np.searchsorted(symbol_data.ts_1s_ns, minute_ts_ns + 60_000_000_000, side="left")
            )
            if second_end > second_start:
                for second_idx in range(second_start, second_end):
                    if state["closed"]:
                        break
                    _process_bar_events(
                        trade,
                        state,
                        float(symbol_data.high_1s[second_idx]),
                        float(symbol_data.low_1s[second_idx]),
                        float(symbol_data.close_1s[second_idx]),
                        consider_profit=not is_flat_bar,
                        is_aggregate_bar=False,
                    )
                    if state["closed"]:
                        state["exit_time"] = pd.Timestamp(int(symbol_data.ts_1s_ns[second_idx])).isoformat()
                        break
            else:
                _process_bar_events(
                    trade,
                    state,
                    high_1m,
                    low_1m,
                    close_1m,
                    consider_profit=not is_flat_bar,
                    is_aggregate_bar=True,
                )
                if state["closed"]:
                    state["exit_time"] = minute_ts.isoformat()
        elif levels_crossed:
            _process_bar_events(
                trade,
                state,
                high_1m,
                low_1m,
                close_1m,
                consider_profit=not is_flat_bar,
                is_aggregate_bar=True,
            )
            if state["closed"]:
                state["exit_time"] = minute_ts.isoformat()

        if state["closed"]:
            break

        if is_flat_bar:
            if trade.direction == 1:
                state["realized_points"] += (close_1m - trade.entry_price) * state["remaining_fraction"]
            else:
                state["realized_points"] += (trade.entry_price - close_1m) * state["remaining_fraction"]
            state["remaining_fraction"] = 0.0
            state["closed"] = True
            state["exit_label"] = "eod"
            state["exit_time"] = minute_ts.isoformat()
            break

    if not state["closed"]:
        minute_idx = end_idx
        close_1m = float(symbol_data.close_1m[minute_idx])
        if trade.direction == 1:
            state["realized_points"] += (close_1m - trade.entry_price) * state["remaining_fraction"]
        else:
            state["realized_points"] += (trade.entry_price - close_1m) * state["remaining_fraction"]
        state["remaining_fraction"] = 0.0
        state["closed"] = True
        state["exit_label"] = "eod"
        state["exit_time"] = pd.Timestamp(int(symbol_data.ts_1m_ns[minute_idx])).isoformat()

    pnl_usd = state["realized_points"] * trade.qty * leg.config.point_value - (
        2.0 * trade.qty * leg.config.commission_per_contract
    )
    r_multiple = state["realized_points"] / trade.risk_points if trade.risk_points > 0 else 0.0

    result = {
        "policy_key": policy_label,
        "date": trade.date,
        "session": trade.session,
        "direction": "long" if trade.direction == 1 else "short",
        "entry_price": float(trade.entry_price),
        "stop_price": float(trade.stop_price),
        "tp1_price": float(trade.tp1_price),
        "tp2_price": float(trade.tp2_price),
        "exit_type": state["exit_label"],
        "pnl_usd": float(pnl_usd),
        "pnl_points": float(state["realized_points"]),
        "r_multiple": float(r_multiple),
        "qty": float(trade.qty),
        "gap_size": float(trade.gap_size),
        "risk_points": float(trade.risk_points),
        "fill_time": trade.fill_time,
        "exit_time": state["exit_time"],
        "mae_r": float(max_adverse_r),
        "mfe_r": float(max_favorable_r),
        "session_flat_time": flat_time.isoformat(),
    }

    if policy is not None and policy.kind == "baseline":
        result["replay_validation"] = (
            abs(result["r_multiple"] - trade.r_multiple) <= 0.02
            and result["exit_type"] == EXIT_NAMES.get(trade.exit_type, "unknown")
        )

    return result


def _target_candidates(leg: LegSpec) -> list[float]:
    tp1_r = leg.config.rr * leg.config.tp1_ratio
    current_final_r = leg.config.rr
    candidates = {current_final_r}
    for level in (1.5, 2.0, 2.5, 3.0, 4.0, 5.0):
        if level > tp1_r + 1e-9 and level <= current_final_r + 1e-9:
            candidates.add(level)
    return sorted(candidates)


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p75": 0.0, "p90": 0.0}
    arr = np.array(values, dtype=np.float64)
    return {
        "p50": float(np.quantile(arr, 0.50)),
        "p75": float(np.quantile(arr, 0.75)),
        "p90": float(np.quantile(arr, 0.90)),
    }


def _excursion_summary(trades: list[dict]) -> dict:
    filled = [t for t in trades if t["exit_type"] != "no_fill"]
    if not filled:
        return {
            "avg_mae_r": 0.0,
            "avg_mfe_r": 0.0,
            "mae_quantiles": {"p50": 0.0, "p75": 0.0, "p90": 0.0},
            "mfe_quantiles": {"p50": 0.0, "p75": 0.0, "p90": 0.0},
            "winner_mae_quantiles": {"p50": 0.0, "p75": 0.0, "p90": 0.0},
            "winner_count": 0,
        }

    maes = [float(t["mae_r"]) for t in filled]
    mfes = [float(t["mfe_r"]) for t in filled]
    winners = [t for t in filled if t["r_multiple"] > 0]
    winner_maes = [float(t["mae_r"]) for t in winners]
    return {
        "avg_mae_r": float(np.mean(maes)),
        "avg_mfe_r": float(np.mean(mfes)),
        "mae_quantiles": _quantiles(maes),
        "mfe_quantiles": _quantiles(mfes),
        "winner_mae_quantiles": _quantiles(winner_maes),
        "winner_count": len(winners),
    }


def _run_leg(
    leg: LegSpec,
    symbol_data: SymbolData,
    *,
    start: str | None,
    end: str | None,
    recent_start: str,
) -> tuple[dict, list[dict], list[dict]]:
    trades = run_backtest(
        symbol_data.df_5m,
        leg.config,
        start_date=start,
        end_date=end,
        df_1m=symbol_data.df_1m,
        signal_df_1m=symbol_data.df_1m,
        df_1s=symbol_data.df_1s,
        _maps=symbol_data.maps,
    )

    baseline_metrics = compute_metrics(trades)
    baseline_trade_dicts = [_build_trade_dict(trade) for trade in trades]

    policy_rows: list[dict] = []
    per_trade_rows: list[dict] = []

    for policy in POLICIES:
        replayed = [
            replay_trade(trade, leg, symbol_data, policy=policy)
            for trade in trades
        ]
        full_summary = _summarize_trade_dicts(replayed)
        recent_summary = _summarize_trade_dicts(_slice_trade_dicts(replayed, start=recent_start))
        excursion = _excursion_summary(replayed)

        validation_rate = None
        if policy.kind == "baseline":
            validations = [
                bool(row.get("replay_validation"))
                for row in replayed
                if row["exit_type"] != "no_fill"
            ]
            validation_rate = float(np.mean(validations)) if validations else 0.0

        policy_rows.append(
            {
                "leg_key": leg.key,
                "leg_label": leg.label,
                "policy_key": policy.key,
                "policy_label": policy.label,
                "full": full_summary,
                "recent": recent_summary,
                "excursion": excursion,
                "baseline_validation_rate": validation_rate,
            }
        )

        for row in replayed:
            out_row = {
                "leg_key": leg.key,
                "leg_label": leg.label,
                "policy_key": policy.key,
                "policy_label": policy.label,
                "date": row["date"],
                "direction": row["direction"],
                "exit_type": row["exit_type"],
                "r_multiple": _safe_round(row["r_multiple"], 4),
                "mae_r": _safe_round(row["mae_r"], 4),
                "mfe_r": _safe_round(row["mfe_r"], 4),
                "fill_time": row["fill_time"],
                "exit_time": row["exit_time"],
            }
            if "replay_validation" in row:
                out_row["replay_validation"] = row["replay_validation"]
            per_trade_rows.append(out_row)

    frontier_rows: list[dict] = []
    for target_r in _target_candidates(leg):
        replayed = [
            replay_trade(trade, leg, symbol_data, custom_target_r=target_r)
            for trade in trades
        ]
        full_summary = _summarize_trade_dicts(replayed)
        recent_summary = _summarize_trade_dicts(_slice_trade_dicts(replayed, start=recent_start))
        excursion = _excursion_summary(replayed)
        frontier_rows.append(
            {
                "leg_key": leg.key,
                "leg_label": leg.label,
                "target_r": float(target_r),
                "full_total_r": _safe_round(full_summary["total_r"], 4),
                "full_max_dd_r": _safe_round(full_summary["max_drawdown_r"], 4),
                "full_calmar": _safe_round(full_summary["calmar_ratio"], 4),
                "full_win_rate": _safe_round(full_summary["win_rate"], 4),
                "recent_total_r": _safe_round(recent_summary["total_r"], 4),
                "recent_max_dd_r": _safe_round(recent_summary["max_drawdown_r"], 4),
                "recent_calmar": _safe_round(recent_summary["calmar_ratio"], 4),
                "winner_mae_p75": _safe_round(excursion["winner_mae_quantiles"]["p75"], 4),
                "winner_mae_p90": _safe_round(excursion["winner_mae_quantiles"]["p90"], 4),
            }
        )

    leg_payload = {
        "leg_key": leg.key,
        "leg_label": leg.label,
        "symbol": leg.symbol,
        "window": {
            "full_start": str(symbol_data.df_5m.index.min().date()),
            "full_end": str(symbol_data.df_5m.index.max().date()),
            "recent_start": recent_start,
        },
        "baseline_engine": {
            "total_trades": int(baseline_metrics["total_trades"]),
            "win_rate": float(baseline_metrics["win_rate"]),
            "profit_factor": float(baseline_metrics["profit_factor"]),
            "avg_r": float(baseline_metrics["avg_r"]),
            "total_r": float(baseline_metrics["total_r"]),
            "max_drawdown_r": abs(float(baseline_metrics["max_drawdown_r"])),
            "calmar_ratio": float(baseline_metrics["calmar_ratio"]),
            "exit_breakdown": dict(baseline_metrics["exit_breakdown"]),
        },
        "policy_summaries": policy_rows,
        "target_frontier": frontier_rows,
    }

    return leg_payload, per_trade_rows, frontier_rows


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _write_report(summary: dict) -> None:
    lines = [
        "# ALPHA_V1 Exit Structure Analysis",
        "",
        "- Objective: pressure-test whether the active `ALPHA_V1` exit structure benefits from the current TP1/TP2 ladder or whether simpler / more prop-friendly exits dominate.",
        "- Method: keep the active `ALPHA_V1` fills fixed, then replay each filled trade with alternative exits on the same intraday path using 1-minute data and 1-second drill-down only when a minute touches a live threshold.",
        "- Policies compared:",
        "  - `Current TP1/TP2 replay`",
        "  - `Full TP only`",
        "  - `3-level TP (TP1 / midpoint / TP2)`",
        "  - `Drawdown scale (50% at -0.5R, rest at -1R)`",
        f"- Common recent window for all legs: `{summary['recent_start']}` onward.",
        "- Caveat: these are same-fill counterfactuals. That is exact for the cap=1 ORB legs and approximate for the cap=2 NQ NY HTF-LSI leg because alternative exits could affect same-session re-entry availability.",
        "",
    ]

    for leg in summary["legs"]:
        lines.extend(
            [
                f"## {leg['leg_label']}",
                "",
                f"- Backtest window: `{leg['window']['full_start']}` to `{leg['window']['full_end']}`",
                "",
                "### Policy Comparison",
                "",
                "| Policy | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | Full Win Rate | p75 Winner MAE (R) |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

        for row in leg["policy_summaries"]:
            full_summary = row["full"]
            recent_summary = row["recent"]
            lines.append(
                f"| {row['policy_label']} | "
                f"{full_summary['total_r']:.1f} | "
                f"{full_summary['max_drawdown_r']:.1f} | "
                f"{full_summary['calmar_ratio']:.2f} | "
                f"{recent_summary['total_r']:.1f} | "
                f"{recent_summary['max_drawdown_r']:.1f} | "
                f"{recent_summary['calmar_ratio']:.2f} | "
                f"{_format_pct(full_summary['win_rate'])} | "
                f"{row['excursion']['winner_mae_quantiles']['p75']:.2f} |"
            )

        lines.extend(
            [
                "",
                "### Target Frontier",
                "",
                "| Final Target (R) | Full Net R | Full Max DD (R) | Full Calmar | Recent Net R | Recent Max DD (R) | Recent Calmar | p75 Winner MAE (R) | p90 Winner MAE (R) |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in leg["target_frontier"]:
            lines.append(
                f"| {row['target_r']:.1f} | "
                f"{row['full_total_r']:.1f} | "
                f"{row['full_max_dd_r']:.1f} | "
                f"{row['full_calmar']:.2f} | "
                f"{row['recent_total_r']:.1f} | "
                f"{row['recent_max_dd_r']:.1f} | "
                f"{row['recent_calmar']:.2f} | "
                f"{row['winner_mae_p75']:.2f} | "
                f"{row['winner_mae_p90']:.2f} |"
            )
        lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze exit structures for the active ALPHA_V1 legs.")
    parser.add_argument("--start", default=None, help="Optional start date (YYYY-MM-DD).")
    parser.add_argument("--end", default=None, help="Optional end date (YYYY-MM-DD, inclusive).")
    parser.add_argument(
        "--recent-start",
        default=DEFAULT_RECENT_START,
        help="Shared recent window start used in the report.",
    )
    args = parser.parse_args()

    legs = build_active_legs()
    symbol_cache: dict[str, SymbolData] = {}
    for symbol in sorted({leg.symbol for leg in legs}):
        data_file = NQ.data_file if symbol == "NQ" else ES.data_file
        symbol_cache[symbol] = load_symbol_data(data_file, start=args.start, end=args.end)

    all_trade_rows: list[dict] = []
    frontier_rows: list[dict] = []
    leg_payloads: list[dict] = []

    for leg in legs:
        payload, trade_rows, target_rows = _run_leg(
            leg,
            symbol_cache[leg.symbol],
            start=args.start,
            end=args.end,
            recent_start=args.recent_start,
        )
        leg_payloads.append(payload)
        all_trade_rows.extend(trade_rows)
        frontier_rows.extend(target_rows)

    summary = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "start": args.start,
        "end": args.end,
        "recent_start": args.recent_start,
        "legs": leg_payloads,
        "report_path": str(REPORT_PATH),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    pd.DataFrame(all_trade_rows).to_csv(TRADE_CSV_PATH, index=False)
    pd.DataFrame(frontier_rows).to_csv(TARGET_FRONTIER_CSV_PATH, index=False)
    _write_report(summary)

    print(json.dumps(summary, indent=2))
    print(f"\nSaved summary to {SUMMARY_PATH}")
    print(f"Saved per-trade analysis to {TRADE_CSV_PATH}")
    print(f"Saved target frontier to {TARGET_FRONTIER_CSV_PATH}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
