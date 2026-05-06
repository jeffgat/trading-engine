#!/usr/bin/env python3
"""Exit and gate deep-dive for ES NY ORB and NQ NY ORB R11.

Research artifact only. Does not edit execution configs.

This follows up the ALPHA_V1 exit target MFE sweep by asking whether the two
NY ORB legs need a different runner-management policy rather than a simple
closer TP2:

- single-target exits at fixed R levels
- full exit at the current TP1
- keep original stop after TP1 instead of moving to breakeven
- delayed breakeven after TP1
- pre-trade bucket diagnostics by entry time, weekday, stop size, and gap size
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import run_alpha_v1_exit_structure_analysis as exit_struct  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "es_nq_ny_orb_exit_deepdive_20260505"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "ES_NQ_NY_ORB_EXIT_DEEPDIVE_20260505.md"

FULL_START = "2016-04-17"
END_INCLUSIVE = "2026-03-24"
END_EXCLUSIVE = "2026-03-25"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"
WINDOWS = {
    "last_1y": (LAST_1Y_START, END_INCLUSIVE),
    "last_2y": (LAST_2Y_START, END_INCLUSIVE),
    "full": (FULL_START, END_INCLUSIVE),
}


@dataclass(frozen=True)
class LegPlan:
    key: str
    label: str
    symbol: str
    config: StrategyConfig
    deployability: str
    live_support_notes: str
    exact_replay_required: str

    @property
    def tp1_r(self) -> float:
        return float(self.config.rr * self.config.tp1_ratio)


@dataclass(frozen=True)
class PolicySpec:
    key: str
    label: str
    family: str
    deployability: str
    live_support_notes: str
    final_target_r: float | None = None
    tp1_r: float | None = None
    be_trigger_r: float | None = None


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        value = float(data)
        return value if math.isfinite(value) else None
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    return data


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _pct(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else 100.0 * float(numerator) / float(denominator)


def build_plans() -> list[LegPlan]:
    es_config = StrategyConfig(
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
        impulse_close_filter=False,
        name="ES NY ORB ALPHA_V1 baseline",
    )
    nq_config = StrategyConfig(
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:50",
                entry_start="09:50",
                entry_end="12:00",
                flat_start="15:30",
                flat_end="16:00",
                stop_atr_pct=7.0,
                min_gap_atr_pct=2.5,
            ),
        ),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.4,
        atr_length=12,
        excluded_days=(4,),
        impulse_close_filter=False,
        name="NQ NY ORB R11 baseline",
    )
    return [
        LegPlan(
            key="es_ny_orb",
            label="ES NY ORB",
            symbol="ES",
            config=es_config,
            deployability="live_native",
            live_support_notes="Active ALPHA_V1 ES_NY ORB leg; baseline rr/tp1 fields are supported.",
            exact_replay_required="yes_before_live_change",
        ),
        LegPlan(
            key="nq_ny_orb_r11",
            label="NQ NY ORB R11",
            symbol="NQ",
            config=nq_config,
            deployability="live_native",
            live_support_notes="Conditional NQ NY ORB R11 branch; standard ORB fields are supported.",
            exact_replay_required="yes_before_live_promotion",
        ),
    ]


def policies_for(plan: LegPlan) -> list[PolicySpec]:
    policy_rows = [
        PolicySpec(
            key="full_at_current_tp1",
            label=f"Full exit at current TP1 ({plan.tp1_r:g}R)",
            family="single_target",
            deployability="research_only",
            live_support_notes="Requires full-position TP1/single-target support in execution config before deployment.",
            final_target_r=plan.tp1_r,
        ),
        PolicySpec(
            key="split_no_be_current_rr",
            label="Current TP1 partial, no BE move",
            family="split_no_be",
            deployability="research_only",
            live_support_notes="Delayed/no breakeven runner management is not a current live-native ALPHA execution knob.",
            tp1_r=plan.tp1_r,
            final_target_r=float(plan.config.rr),
        ),
    ]

    for target_r in (1.0, 1.25, 1.4, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        if target_r > float(plan.config.rr) + 1e-9:
            continue
        policy_rows.append(
            PolicySpec(
                key=f"single_{str(target_r).replace('.', 'p')}r",
                label=f"Single target {target_r:g}R",
                family="single_target",
                deployability="research_only",
                live_support_notes="Single-target/full-position exits need execution support before deployment.",
                final_target_r=target_r,
            )
        )

    for trigger_r in (1.5, 2.0, 2.5, 3.0):
        if trigger_r <= plan.tp1_r + 1e-9 or trigger_r >= float(plan.config.rr) - 1e-9:
            continue
        policy_rows.append(
            PolicySpec(
                key=f"split_delayed_be_{str(trigger_r).replace('.', 'p')}r",
                label=f"Current TP1 partial, BE only after {trigger_r:g}R",
                family="split_delayed_be",
                deployability="research_only",
                live_support_notes="Delayed breakeven is a research-only runner-management rule until implemented in execution.",
                tp1_r=plan.tp1_r,
                final_target_r=float(plan.config.rr),
                be_trigger_r=trigger_r,
            )
        )
    return policy_rows


def _price_for_profit_r(direction: int, entry_price: float, risk_points: float, r_multiple: float) -> float:
    return entry_price + direction * risk_points * r_multiple


def _crosses_profit(direction: int, high_price: float, low_price: float, level_price: float) -> bool:
    return high_price >= level_price if direction == 1 else low_price <= level_price


def _crosses_stop(direction: int, high_price: float, low_price: float, level_price: float) -> bool:
    return low_price <= level_price if direction == 1 else high_price >= level_price


def _first_flat_timestamp(fill_time: pd.Timestamp, flat_start: str) -> pd.Timestamp:
    hh, mm = (int(part) for part in flat_start.split(":"))
    flat_ts = fill_time.normalize() + pd.Timedelta(hours=hh, minutes=mm)
    if flat_ts < fill_time:
        flat_ts += pd.Timedelta(days=1)
    return flat_ts


def _favorable_r(direction: int, entry_price: float, price: float, risk_points: float) -> float:
    if risk_points <= 0:
        return 0.0
    return max(0.0, direction * (price - entry_price) / risk_points)


def _adverse_r(direction: int, entry_price: float, price: float, risk_points: float) -> float:
    if risk_points <= 0:
        return 0.0
    return max(0.0, -direction * (price - entry_price) / risk_points)


def _profit_steps(trade: TradeResult, policy: PolicySpec) -> list[dict[str, Any]]:
    if policy.family == "single_target":
        assert policy.final_target_r is not None
        return [
            {
                "label": "single_target",
                "r_multiple": policy.final_target_r,
                "price": _price_for_profit_r(trade.direction, trade.entry_price, trade.risk_points, policy.final_target_r),
                "fraction": 1.0,
                "move_stop_to_be": False,
                "be_trigger_only": False,
            }
        ]

    half_fraction = max(0.0, min(1.0, float(trade.half_qty / trade.qty))) if trade.qty > 0 else 0.5
    remainder_fraction = max(0.0, 1.0 - half_fraction)
    assert policy.tp1_r is not None
    assert policy.final_target_r is not None
    steps = [
        {
            "label": "tp1_partial",
            "r_multiple": policy.tp1_r,
            "price": _price_for_profit_r(trade.direction, trade.entry_price, trade.risk_points, policy.tp1_r),
            "fraction": half_fraction,
            "move_stop_to_be": False,
            "be_trigger_only": False,
        }
    ]
    if policy.family == "split_delayed_be":
        assert policy.be_trigger_r is not None
        steps.append(
            {
                "label": "be_trigger",
                "r_multiple": policy.be_trigger_r,
                "price": _price_for_profit_r(trade.direction, trade.entry_price, trade.risk_points, policy.be_trigger_r),
                "fraction": 0.0,
                "move_stop_to_be": True,
                "be_trigger_only": True,
            }
        )
    steps.append(
        {
            "label": "tp2_final",
            "r_multiple": policy.final_target_r,
            "price": _price_for_profit_r(trade.direction, trade.entry_price, trade.risk_points, policy.final_target_r),
            "fraction": remainder_fraction,
            "move_stop_to_be": False,
            "be_trigger_only": False,
        }
    )
    return steps


def _realize_profit(trade: TradeResult, state: dict[str, Any], step: dict[str, Any]) -> None:
    remaining = float(state["remaining_fraction"])
    if remaining <= 1e-12:
        return
    realized_fraction = min(remaining, max(0.0, min(1.0, float(step["fraction"]))))
    if realized_fraction > 0:
        state["realized_points"] += direction_points(trade, step["price"]) * realized_fraction
        state["remaining_fraction"] = max(0.0, remaining - realized_fraction)
        state["partial_taken"] = state["partial_taken"] or state["remaining_fraction"] > 1e-12
    if step["move_stop_to_be"]:
        state["current_stop_price"] = float(trade.entry_price)
        state["be_active"] = True
    if state["remaining_fraction"] <= 1e-12:
        state["closed"] = True
        state["exit_type"] = "tp1_tp2" if state["partial_taken"] else "tp2_single"


def direction_points(trade: TradeResult, price: float) -> float:
    return trade.direction * (float(price) - float(trade.entry_price))


def _realize_stop(trade: TradeResult, state: dict[str, Any]) -> None:
    remaining = float(state["remaining_fraction"])
    if remaining <= 1e-12:
        return
    state["realized_points"] += direction_points(trade, state["current_stop_price"]) * remaining
    state["remaining_fraction"] = 0.0
    state["closed"] = True
    if state["partial_taken"] and state["be_active"] and abs(float(state["current_stop_price"]) - float(trade.entry_price)) < 1e-9:
        state["exit_type"] = "tp1_be"
    elif state["partial_taken"]:
        state["exit_type"] = "tp1_sl"
    else:
        state["exit_type"] = "sl"


def _process_bar(trade: TradeResult, state: dict[str, Any], high_price: float, low_price: float, *, consider_profit: bool) -> None:
    stop_hit = _crosses_stop(trade.direction, high_price, low_price, state["current_stop_price"])
    profit_hits = []
    if consider_profit:
        for step in state["profit_steps"]:
            if _crosses_profit(trade.direction, high_price, low_price, step["price"]):
                profit_hits.append(step)
    profit_hits.sort(key=lambda step: step["price"], reverse=trade.direction == -1)

    # Same-bar ambiguity is handled conservatively: stop first.
    if stop_hit:
        _realize_stop(trade, state)
        return

    used_labels = set()
    for step in profit_hits:
        if state["closed"]:
            break
        if step["label"] in used_labels:
            continue
        _realize_profit(trade, state, step)
        used_labels.add(step["label"])
        if not state["closed"] and _crosses_stop(trade.direction, high_price, low_price, state["current_stop_price"]):
            _realize_stop(trade, state)
            break
    if used_labels:
        state["profit_steps"] = [step for step in state["profit_steps"] if step["label"] not in used_labels]


def replay_policy_trade(
    trade: TradeResult,
    plan: LegPlan,
    symbol_data: exit_struct.SymbolData,
    policy: PolicySpec,
) -> dict[str, Any]:
    fill_time = pd.Timestamp(trade.fill_time)
    flat_time = _first_flat_timestamp(fill_time, plan.config.sessions[0].flat_start)
    end_cutoff = flat_time + pd.Timedelta(minutes=1)
    start_idx = int(np.searchsorted(symbol_data.ts_1m_ns, fill_time.value, side="left"))
    end_idx = int(np.searchsorted(symbol_data.ts_1m_ns, end_cutoff.value, side="left")) - 1
    end_idx = min(end_idx, len(symbol_data.ts_1m_ns) - 1)

    state: dict[str, Any] = {
        "remaining_fraction": 1.0,
        "realized_points": 0.0,
        "current_stop_price": float(trade.stop_price),
        "profit_steps": _profit_steps(trade, policy),
        "partial_taken": False,
        "be_active": False,
        "closed": False,
        "exit_type": "eod",
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

        max_favorable_r = max(
            max_favorable_r,
            _favorable_r(trade.direction, trade.entry_price, high_1m if trade.direction == 1 else low_1m, trade.risk_points),
        )
        max_adverse_r = max(
            max_adverse_r,
            _adverse_r(trade.direction, trade.entry_price, low_1m if trade.direction == 1 else high_1m, trade.risk_points),
        )

        is_flat_bar = minute_ts >= flat_time
        levels_crossed = _crosses_stop(trade.direction, high_1m, low_1m, state["current_stop_price"])
        if not levels_crossed and not is_flat_bar:
            levels_crossed = any(
                _crosses_profit(trade.direction, high_1m, low_1m, step["price"])
                for step in state["profit_steps"]
            )

        if levels_crossed and symbol_data.ts_1s_ns is not None:
            second_start = int(np.searchsorted(symbol_data.ts_1s_ns, minute_ts_ns, side="left"))
            second_end = int(np.searchsorted(symbol_data.ts_1s_ns, minute_ts_ns + 60_000_000_000, side="left"))
            for second_idx in range(second_start, second_end):
                if state["closed"]:
                    break
                _process_bar(
                    trade,
                    state,
                    float(symbol_data.high_1s[second_idx]),
                    float(symbol_data.low_1s[second_idx]),
                    consider_profit=not is_flat_bar,
                )
                if state["closed"]:
                    state["exit_time"] = pd.Timestamp(int(symbol_data.ts_1s_ns[second_idx])).isoformat()
                    break
        elif levels_crossed:
            _process_bar(trade, state, high_1m, low_1m, consider_profit=not is_flat_bar)
            if state["closed"]:
                state["exit_time"] = minute_ts.isoformat()

        if state["closed"]:
            break

        if is_flat_bar:
            state["realized_points"] += direction_points(trade, close_1m) * float(state["remaining_fraction"])
            state["remaining_fraction"] = 0.0
            state["closed"] = True
            state["exit_type"] = "tp1_eod" if state["partial_taken"] else "eod"
            state["exit_time"] = minute_ts.isoformat()
            break

    if not state["closed"]:
        close_1m = float(symbol_data.close_1m[end_idx])
        state["realized_points"] += direction_points(trade, close_1m) * float(state["remaining_fraction"])
        state["remaining_fraction"] = 0.0
        state["closed"] = True
        state["exit_type"] = "tp1_eod" if state["partial_taken"] else "eod"
        state["exit_time"] = pd.Timestamp(int(symbol_data.ts_1m_ns[end_idx])).isoformat()

    pnl_usd = state["realized_points"] * trade.qty * plan.config.point_value - (
        2.0 * trade.qty * plan.config.commission_per_contract
    )
    return {
        "leg_key": plan.key,
        "leg_label": plan.label,
        "policy_key": policy.key,
        "policy_label": policy.label,
        "family": policy.family,
        "date": trade.date,
        "fill_time": trade.fill_time,
        "exit_time": state["exit_time"],
        "exit_type": state["exit_type"],
        "direction": "long" if trade.direction == 1 else "short",
        "entry_price": float(trade.entry_price),
        "stop_price": float(trade.stop_price),
        "risk_points": float(trade.risk_points),
        "gap_size": float(trade.gap_size),
        "r_multiple": float(state["realized_points"] / trade.risk_points) if trade.risk_points > 0 else 0.0,
        "pnl_usd": float(pnl_usd),
        "mae_r": float(max_adverse_r),
        "mfe_r": float(max_favorable_r),
        "deployability": policy.deployability,
        "live_support_notes": policy.live_support_notes,
    }


def _summarize_dict_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "trades": 0,
            "net_r": 0.0,
            "profit_factor": 0.0,
            "win_rate_pct": 0.0,
            "max_dd_r": 0.0,
            "avg_r": 0.0,
            "exit_counts": {},
        }
    r_values = np.array([float(t["r_multiple"]) for t in trades], dtype=np.float64)
    pnl_values = np.array([float(t["pnl_usd"]) for t in trades], dtype=np.float64)
    wins = pnl_values > 0
    losses = pnl_values < 0
    total_wins = float(np.sum(pnl_values[wins]))
    total_losses = float(np.sum(pnl_values[losses]))
    equity = np.cumsum(r_values)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    counts: dict[str, int] = {}
    for trade in trades:
        counts[str(trade["exit_type"])] = counts.get(str(trade["exit_type"]), 0) + 1
    total = len(trades)
    full_tp = counts.get("tp1_tp2", 0) + counts.get("tp2_single", 0)
    return {
        "trades": total,
        "net_r": _round(float(equity[-1]), 2),
        "profit_factor": _round(abs(total_wins / total_losses) if total_losses != 0 else 0.0, 3),
        "win_rate_pct": _round(float(np.mean(wins)) * 100.0, 2),
        "max_dd_r": _round(abs(float(np.min(dd))), 2),
        "avg_r": _round(float(np.mean(r_values)), 4),
        "exit_counts": counts,
        "full_tp_pct": _round(_pct(full_tp, total), 2),
        "tp1_be_pct": _round(_pct(counts.get("tp1_be", 0), total), 2),
        "tp1_sl_pct": _round(_pct(counts.get("tp1_sl", 0), total), 2),
        "sl_pct": _round(_pct(counts.get("sl", 0), total), 2),
        "eod_pct": _round(_pct(counts.get("eod", 0), total), 2),
    }


def _baseline_summary(trades: list[TradeResult]) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    counts = dict(metrics["exit_breakdown"])
    total = int(metrics["total_trades"])
    full_tp = counts.get("tp1_tp2", 0) + counts.get("tp2_single", 0)
    return {
        "trades": total,
        "net_r": _round(metrics["total_r"], 2),
        "profit_factor": _round(metrics["profit_factor"], 3),
        "win_rate_pct": _round(float(metrics["win_rate"]) * 100.0, 2),
        "max_dd_r": _round(abs(float(metrics["max_drawdown_r"])), 2),
        "avg_r": _round(metrics["avg_r"], 4),
        "exit_counts": counts,
        "full_tp_pct": _round(_pct(full_tp, total), 2),
        "tp1_be_pct": _round(_pct(counts.get("tp1_be", 0), total), 2),
        "tp1_sl_pct": 0.0,
        "sl_pct": _round(_pct(counts.get("sl", 0), total), 2),
        "eod_pct": _round(_pct(counts.get("eod", 0), total), 2),
    }


def _windowed_policy_rows(plan: LegPlan, policy: PolicySpec, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for window, (start, end) in WINDOWS.items():
        selected = [trade for trade in trades if start <= str(trade["date"]) <= end]
        summary = _summarize_dict_trades(selected)
        rows.append(
            {
                "leg_key": plan.key,
                "leg_label": plan.label,
                "policy_key": policy.key,
                "policy_label": policy.label,
                "family": policy.family,
                "window": window,
                "deployability": policy.deployability,
                "live_support_notes": policy.live_support_notes,
                **summary,
            }
        )
    return rows


def _windowed_baseline_rows(plan: LegPlan, trades: list[TradeResult]) -> list[dict[str, Any]]:
    rows = []
    for window, (start, end) in WINDOWS.items():
        selected = [trade for trade in trades if start <= trade.date <= end]
        rows.append(
            {
                "leg_key": plan.key,
                "leg_label": plan.label,
                "policy_key": "baseline",
                "policy_label": "Current live-native baseline",
                "family": "baseline",
                "window": window,
                "deployability": plan.deployability,
                "live_support_notes": plan.live_support_notes,
                **_baseline_summary(selected),
            }
        )
    return rows


def _score_policy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for row in rows:
        by_policy.setdefault((str(row["leg_key"]), str(row["policy_key"])), {})[str(row["window"])] = row
    baselines = {leg_key: windows for (leg_key, policy), windows in by_policy.items() if policy == "baseline"}
    ranked = []
    for (leg_key, policy), windows in by_policy.items():
        if not {"full", "last_2y", "last_1y"} <= set(windows):
            continue
        full = windows["full"]
        last2 = windows["last_2y"]
        last1 = windows["last_1y"]
        base_full = baselines[leg_key]["full"]
        base_last2 = baselines[leg_key]["last_2y"]
        base_last1 = baselines[leg_key]["last_1y"]
        full_net = float(full["net_r"] or 0.0)
        base_net = float(base_full["net_r"] or 0.0)
        full_pf = float(full["profit_factor"] or 0.0)
        base_pf = float(base_full["profit_factor"] or 0.0)
        full_dd = float(full["max_dd_r"] or 0.0)
        base_dd = float(base_full["max_dd_r"] or 0.0)
        near_intact = (
            full_net >= 0.95 * base_net
            and full_pf >= base_pf - 0.05
            and full_dd <= 1.10 * base_dd
            and float(last2["net_r"] or 0.0) >= 0.80 * float(base_last2["net_r"] or 0.0)
            and float(last1["net_r"] or 0.0) >= 0.75 * float(base_last1["net_r"] or 0.0)
        )
        loose_intact = (
            full_net >= 0.85 * base_net
            and full_pf >= base_pf - 0.10
            and full_dd <= 1.25 * base_dd
            and float(last2["net_r"] or 0.0) >= 0.65 * float(base_last2["net_r"] or 0.0)
        )
        score = (
            full_net
            + 2.0 * float(last2["net_r"] or 0.0)
            + 1.5 * float(last1["net_r"] or 0.0)
            + 30.0 * (full_pf - base_pf)
            - 3.0 * max(0.0, full_dd - base_dd)
            + 0.5 * (float(full["full_tp_pct"] or 0.0) - float(base_full["full_tp_pct"] or 0.0))
        )
        if not loose_intact:
            score -= 40.0
        ranked.append(
            {
                "leg_key": leg_key,
                "leg_label": full["leg_label"],
                "policy_key": policy,
                "policy_label": full["policy_label"],
                "family": full["family"],
                "near_intact": near_intact,
                "loose_intact": loose_intact,
                "score": _round(score, 3),
                "full_net_r": full_net,
                "full_r_delta": _round(full_net - base_net, 2),
                "full_pf": full_pf,
                "full_pf_delta": _round(full_pf - base_pf, 3),
                "full_dd_r": full_dd,
                "full_dd_delta": _round(full_dd - base_dd, 2),
                "full_wr_pct": float(full["win_rate_pct"] or 0.0),
                "full_full_tp_pct": float(full["full_tp_pct"] or 0.0),
                "full_tp1_be_pct": float(full["tp1_be_pct"] or 0.0),
                "full_tp1_sl_pct": float(full["tp1_sl_pct"] or 0.0),
                "last_2y_net_r": float(last2["net_r"] or 0.0),
                "last_2y_r_delta": _round(float(last2["net_r"] or 0.0) - float(base_last2["net_r"] or 0.0), 2),
                "last_1y_net_r": float(last1["net_r"] or 0.0),
                "last_1y_r_delta": _round(float(last1["net_r"] or 0.0) - float(base_last1["net_r"] or 0.0), 2),
                "deployability": full["deployability"],
                "live_support_notes": full["live_support_notes"],
            }
        )
    return sorted(ranked, key=lambda row: float(row["score"] or 0.0), reverse=True)


def _bucket_value(trade: TradeResult, bucket: str, plan: LegPlan, risk_edges: list[float], gap_edges: list[float]) -> str:
    fill_ts = pd.Timestamp(trade.fill_time)
    if bucket == "dow":
        return fill_ts.day_name()[:3]
    if bucket == "entry_time":
        minutes = fill_ts.hour * 60 + fill_ts.minute
        if minutes < 10 * 60 + 30:
            return "early"
        if minutes < 11 * 60 + 30:
            return "mid"
        return "late"
    if bucket == "risk_q":
        value = float(trade.risk_points)
        idx = int(np.searchsorted(risk_edges, value, side="right")) + 1
        return f"Q{min(max(idx, 1), 4)}"
    if bucket == "gap_q":
        value = float(trade.gap_size)
        idx = int(np.searchsorted(gap_edges, value, side="right")) + 1
        return f"Q{min(max(idx, 1), 4)}"
    raise ValueError(bucket)


def _bucket_rows(plan: LegPlan, trades: list[TradeResult]) -> list[dict[str, Any]]:
    filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    baseline = _baseline_summary(filled)
    risk_edges = [float(np.quantile([t.risk_points for t in filled], q)) for q in (0.25, 0.50, 0.75)]
    gap_edges = [float(np.quantile([t.gap_size for t in filled], q)) for q in (0.25, 0.50, 0.75)]
    rows = []
    for bucket in ("dow", "entry_time", "risk_q", "gap_q"):
        groups: dict[str, list[TradeResult]] = {}
        for trade in filled:
            groups.setdefault(_bucket_value(trade, bucket, plan, risk_edges, gap_edges), []).append(trade)
        for value, group in sorted(groups.items()):
            if len(group) < 20:
                continue
            summary = _baseline_summary(group)
            rows.append(
                {
                    "leg_key": plan.key,
                    "leg_label": plan.label,
                    "bucket": bucket,
                    "value": value,
                    "trades": summary["trades"],
                    "net_r": summary["net_r"],
                    "avg_r": summary["avg_r"],
                    "profit_factor": summary["profit_factor"],
                    "win_rate_pct": summary["win_rate_pct"],
                    "max_dd_r": summary["max_dd_r"],
                    "full_tp_pct": summary["full_tp_pct"],
                    "tp1_be_pct": summary["tp1_be_pct"],
                    "sl_pct": summary["sl_pct"],
                    "skip_delta_r": _round(-float(summary["net_r"] or 0.0), 2),
                    "skip_damage_vs_total_pct": _round(_pct(float(summary["net_r"] or 0.0), float(baseline["net_r"] or 1.0)), 2),
                    "deployability": "post_filter_only",
                    "live_support_notes": "Bucket is known pre-trade, but exact live gate support/parity is required before deployment.",
                }
            )
    return rows


def _md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    lines = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        cells = []
        for _, key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                value = f"{value:.2f}"
            cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _write_report(policy_ranked: list[dict[str, Any]], bucket_rows: list[dict[str, Any]]) -> None:
    best_tables = []
    for leg in ("ES NY ORB", "NQ NY ORB R11"):
        rows = [row for row in policy_ranked if row["leg_label"] == leg][:10]
        best_tables.extend(
            {
                "Leg": row["leg_label"],
                "Policy": row["policy_label"],
                "Family": row["family"],
                "Near": row["near_intact"],
                "Loose": row["loose_intact"],
                "Full R/PF/DD": f"{row['full_net_r']:.1f}/{row['full_pf']:.2f}/{row['full_dd_r']:.1f}",
                "ΔR/ΔDD": f"{row['full_r_delta']:+.1f}/{row['full_dd_delta']:+.1f}",
                "2Y ΔR": row["last_2y_r_delta"],
                "1Y ΔR": row["last_1y_r_delta"],
                "TP2%": f"{row['full_full_tp_pct']:.1f}%",
                "TP1-BE%": f"{row['full_tp1_be_pct']:.1f}%",
                "Deploy": row["deployability"],
                "Live Support": row["live_support_notes"],
                "Exact": "yes_after_live_native_impl" if row["deployability"] == "research_only" else "yes_before_live_change",
            }
            for row in rows
        )

    weak_buckets = sorted(
        [row for row in bucket_rows if int(row["trades"]) >= 40],
        key=lambda row: float(row["avg_r"] or 0.0),
    )[:16]
    bucket_table = [
        {
            "Leg": row["leg_label"],
            "Bucket": f"{row['bucket']}={row['value']}",
            "Trades": row["trades"],
            "Net R": row["net_r"],
            "Avg R": row["avg_r"],
            "PF": row["profit_factor"],
            "WR": f"{row['win_rate_pct']:.1f}%",
            "TP2%": f"{row['full_tp_pct']:.1f}%",
            "TP1-BE%": f"{row['tp1_be_pct']:.1f}%",
            "Skip ΔR": row["skip_delta_r"],
        }
        for row in weak_buckets
    ]

    lines = [
        "# ES/NQ NY ORB Exit Deep-Dive (2026-05-05)",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Full window: `{FULL_START}` to `{END_INCLUSIVE}`.",
        "- Scope: `ES NY ORB` and `NQ NY ORB R11` only.",
        "- Purpose: explore runner-management alternatives before spending effort on NQ Asia and NQ HTF-LSI target optimization.",
        "- Important deployability note: baseline and normal rr/tp1 changes are live-native; single-target, no-BE, and delayed-BE policies are `research_only` until the execution engine supports them directly.",
        "",
        "## Policy Replay Ranking",
        "",
        *_md_table(
            best_tables,
            [
                ("Leg", "Leg"),
                ("Policy", "Policy"),
                ("Family", "Family"),
                ("Near", "Near"),
                ("Loose", "Loose"),
                ("Full R/PF/DD", "Full R/PF/DD"),
                ("ΔR/ΔDD", "ΔR/ΔDD"),
                ("2Y ΔR", "2Y ΔR"),
                ("1Y ΔR", "1Y ΔR"),
                ("TP2%", "TP2%"),
                ("TP1-BE%", "TP1-BE%"),
                ("Deploy", "Deploy"),
                ("Live Support", "Live Support"),
                ("Exact", "Exact"),
            ],
        ),
        "",
        "## Weak Pre-Trade Buckets",
        "",
        *_md_table(
            bucket_table,
            [
                ("Leg", "Leg"),
                ("Bucket", "Bucket"),
                ("Trades", "Trades"),
                ("Net R", "Net R"),
                ("Avg R", "Avg R"),
                ("PF", "PF"),
                ("WR", "WR"),
                ("TP2%", "TP2%"),
                ("TP1-BE%", "TP1-BE%"),
                ("Skip ΔR", "Skip ΔR"),
            ],
        ),
        "",
        "## Read",
        "",
        "- The missed branch is not plain TP2 compression; it is runner management. A true full-position exit at the current TP1 is the strongest research policy for both legs, especially ES NY.",
        "- Delaying breakeven after TP1 also looks strong, but it changes the live risk profile by allowing partial winners to become `tp1_sl` givebacks. Treat it as secondary to the simpler full-at-TP1 thesis.",
        "- Current execution does not expose a true full-position TP1 / single-target mode for multi-contract positions. The existing wide-stop target compression path is not equivalent; this must be implemented before exact replay or live consideration.",
        "- Bucket diagnostics did not find an obvious negative pre-trade slice. The weaker buckets are still positive, so gating is less attractive than fixing the exit policy.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    plans = build_plans()
    symbol_cache: dict[str, exit_struct.SymbolData] = {}
    for symbol in sorted({plan.symbol for plan in plans}):
        data_file = NQ.data_file if symbol == "NQ" else ES.data_file
        print(f"Loading {symbol} data", flush=True)
        symbol_cache[symbol] = exit_struct.load_symbol_data(data_file, start=FULL_START, end=END_EXCLUSIVE)

    baseline_rows: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []
    policy_trade_rows: list[dict[str, Any]] = []
    bucket_rows: list[dict[str, Any]] = []

    for plan in plans:
        data = symbol_cache[plan.symbol]
        print(f"Running baseline {plan.label}", flush=True)
        trades = run_backtest(
            data.df_5m,
            plan.config,
            start_date=FULL_START,
            end_date=END_EXCLUSIVE,
            df_1m=data.df_1m,
            signal_df_1m=data.df_1m,
            df_1s=data.df_1s,
            _maps=data.maps,
        )
        trades = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
        baseline_rows.extend(_windowed_baseline_rows(plan, trades))
        bucket_rows.extend(_bucket_rows(plan, trades))

        for policy in policies_for(plan):
            print(f"  policy {policy.key}", flush=True)
            replayed = [replay_policy_trade(trade, plan, data, policy) for trade in trades]
            policy_trade_rows.extend(replayed)
            policy_rows.extend(_windowed_policy_rows(plan, policy, replayed))

    all_policy_rows = [*baseline_rows, *policy_rows]
    ranked = _score_policy_rows(all_policy_rows)
    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "run_slug": RUN_SLUG,
        "full_start": FULL_START,
        "end_inclusive": END_INCLUSIVE,
        "ranked": ranked,
        "elapsed_seconds": round(time.time() - started, 2),
        "report_path": str(REPORT_PATH),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2), encoding="utf-8")
    pd.DataFrame(all_policy_rows).to_csv(RESULT_DIR / "policy_metrics.csv", index=False)
    pd.DataFrame(policy_trade_rows).to_csv(RESULT_DIR / "policy_trades.csv", index=False)
    pd.DataFrame(ranked).to_csv(RESULT_DIR / "ranked_policies.csv", index=False)
    pd.DataFrame(bucket_rows).to_csv(RESULT_DIR / "bucket_diagnostics.csv", index=False)
    _write_report(ranked, bucket_rows)
    print(json.dumps(_safe_json(summary), indent=2))
    print(f"\nSaved report to {REPORT_PATH}")
    print(f"Saved artifacts to {RESULT_DIR}")


if __name__ == "__main__":
    main()
