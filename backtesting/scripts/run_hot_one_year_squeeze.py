#!/usr/bin/env python3
"""Second-stage hot one-year squeeze across the screenshot winner legs.

This starts from the 2026-05-03 hot workflow winners, then searches locally
around those configs with wider regime gates, Hunter-style ORB mechanics, and
extra LSI execution/target variants. It is intentionally an overfit-aware
TESTING-only search for last-year heat, not a robust promotion pipeline.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import replace
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import run_hot_one_year_strategy_workflow as prev  # noqa: E402
from orb_backtest.config import StrategyConfig  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402


RUN_SLUG = "hot_one_year_squeeze_20260503"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "HOT_ONE_YEAR_SQUEEZE_20260503.md"
PREV_SUMMARY_PATH = ROOT / "data" / "results" / "hot_one_year_strategy_workflow_20260503" / "summary.json"

REQUESTED_LEGS = (
    "nq_ny_orb",
    "nq_asia_orb",
    "nq_ny_lsi",
    "es_ny_orb",
    "es_asia_orb",
    "es_ny_lsi",
    "gc_ny_orb",
    "gc_asia_orb",
    "gc_ny_lsi",
)

KEEP_OPTIONS_PER_CATEGORY = 3
MAX_COMBO_CATEGORIES = 7

GATE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "gate_none": {"include": (), "exclude": ()},
    "gate_skip_medium_vol": {"include": (), "exclude": ("bull_medium_vol", "sideways_medium_vol")},
    "gate_skip_bear_high_vol": {"include": (), "exclude": ("bear_high_vol",)},
    "gate_skip_high_vol": {"include": (), "exclude": ("bull_high_vol", "bear_high_vol", "sideways_high_vol")},
    "gate_skip_bull_medium_vol": {"include": (), "exclude": ("bull_medium_vol",)},
    "gate_skip_sideways_medium_vol": {"include": (), "exclude": ("sideways_medium_vol",)},
    "gate_skip_sideways_high_vol": {"include": (), "exclude": ("sideways_high_vol",)},
    "gate_skip_bear_medium_high": {"include": (), "exclude": ("bear_medium_vol", "bear_high_vol")},
    "gate_only_bull": {"include": ("bull_low_vol", "bull_medium_vol", "bull_high_vol"), "exclude": ()},
    "gate_only_bear": {"include": ("bear_low_vol", "bear_medium_vol", "bear_high_vol"), "exclude": ()},
    "gate_only_sideways": {"include": ("sideways_low_vol", "sideways_medium_vol", "sideways_high_vol"), "exclude": ()},
    "gate_only_low_vol": {"include": ("bull_low_vol", "bear_low_vol", "sideways_low_vol"), "exclude": ()},
    "gate_only_medium_vol": {"include": ("bull_medium_vol", "bear_medium_vol", "sideways_medium_vol"), "exclude": ()},
    "gate_only_high_vol": {"include": ("bull_high_vol", "bear_high_vol", "sideways_high_vol"), "exclude": ()},
    "gate_only_bull_high_vol": {"include": ("bull_high_vol",), "exclude": ()},
    "gate_only_bull_medium_vol": {"include": ("bull_medium_vol",), "exclude": ()},
    "gate_only_bear_medium_vol": {"include": ("bear_medium_vol",), "exclude": ()},
    "gate_only_sideways_low_vol": {"include": ("sideways_low_vol",), "exclude": ()},
}


def _slug_num(value: float | int) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", "p")


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _time(total: int) -> str:
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def _dedupe_values(values: list[Any]) -> list[Any]:
    out = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _rr_option(rr: float, tp1: float) -> prev.OptionSpec:
    return prev._rr_option(round(rr, 3), round(tp1, 3))


def _dow_options(config: StrategyConfig) -> list[prev.OptionSpec]:
    baseline = tuple(config.excluded_days)
    options = [
        prev._dow_option("dow_current", baseline),
        prev._dow_option("dow_none", ()),
    ]
    options.extend(prev._dow_option(f"dow_ex{prev.DOW_LABELS[day]}", (day,)) for day in range(5))
    return _unique_options(options)


def _unique_options(options: list[prev.OptionSpec]) -> list[prev.OptionSpec]:
    seen = set()
    out = []
    for option in options:
        if option.option_id in seen:
            continue
        seen.add(option.option_id)
        out.append(option)
    return out


def _orb_window_option(session, minutes: int) -> prev.OptionSpec:
    return prev._orb_window_option(session.orb_start, minutes)


def _entry_end_options(category: str, values: list[str]) -> list[prev.OptionSpec]:
    return [
        prev.OptionSpec(category, f"{category}_{value.replace(':', '')}", f"{category}={value}", session={category: value})
        for value in values
    ]


def _flat_start_options(values: list[str]) -> list[prev.OptionSpec]:
    return [
        prev.OptionSpec("flat_start", f"flat_{value.replace(':', '')}", f"flat_start={value}", session={"flat_start": value})
        for value in values
    ]


def _rr_tp_options(config: StrategyConfig, *, high_rr: bool = False, low_rr: bool = False) -> list[prev.OptionSpec]:
    rr = float(config.rr)
    tp = float(config.tp1_ratio)
    rr_values = [rr, rr - 1.0, rr - 0.5, rr + 0.5, rr + 1.0]
    if high_rr:
        rr_values += [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
    elif low_rr:
        rr_values += [1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
    else:
        rr_values += [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
    tp_values = [tp, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8]
    pairs = []
    for rr_val in sorted({round(v, 3) for v in rr_values if 1.0 <= v <= 12.0}):
        for tp_val in sorted({round(v, 3) for v in tp_values if 0.1 <= v <= 1.0}):
            if prev._valid_rr_tp1(rr_val, tp_val):
                pairs.append((rr_val, tp_val))
    # Always keep the current pair first; cap only the OAT menu, not the final
    # selected options that come out of scoring.
    ordered = [(rr, tp)] + [pair for pair in pairs if pair != (rr, tp)]
    return _unique_options([_rr_option(rr_val, tp_val) for rr_val, tp_val in ordered])


def _stop_options(symbol: str, config: StrategyConfig) -> list[prev.OptionSpec]:
    session = config.sessions[0]
    atr_current = float(session.stop_atr_pct or 0.0)
    orb_current = float(session.stop_orb_pct or 0.0)
    if symbol == "NQ":
        atr_values = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]
        orb_values = [25.0, 50.0, 75.0, 100.0, 125.0, 150.0]
    elif symbol == "ES":
        atr_values = [3.0, 4.0, 5.0, 6.0, 7.5, 10.0, 12.5, 15.0]
        orb_values = [50.0, 75.0, 100.0, 125.0, 150.0]
    else:
        atr_values = [3.0, 4.0, 4.5, 5.0, 6.0, 7.5, 10.0, 12.5]
        orb_values = [25.0, 50.0, 75.0, 100.0, 125.0]
    if atr_current > 0:
        atr_values += [atr_current, atr_current * 0.8, atr_current * 1.2]
    if orb_current > 0:
        orb_values += [orb_current, orb_current * 0.75, orb_current * 1.25]
    options = [prev._stop_option("atr", round(v, 3)) for v in sorted({v for v in atr_values if v > 0})]
    options += [prev._stop_option("orb", round(v, 3)) for v in sorted({v for v in orb_values if v > 0})]
    return _unique_options(options)


def _gap_options(symbol: str, config: StrategyConfig) -> list[prev.OptionSpec]:
    session = config.sessions[0]
    atr_current = float(session.min_gap_atr_pct or 0.0)
    orb_current = float(session.min_gap_orb_pct or 0.0)
    if symbol == "NQ":
        atr_values = [0.0, 0.5, 0.9, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
        orb_values = [0.0, 5.0, 10.0, 15.0, 20.0]
    elif symbol == "ES":
        atr_values = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5]
        orb_values = [0.0, 5.0, 10.0, 15.0, 20.0]
    else:
        atr_values = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]
        orb_values = [0.0, 5.0, 10.0, 15.0, 20.0]
    if atr_current >= 0:
        atr_values += [atr_current, atr_current * 0.75, atr_current * 1.25]
    if orb_current >= 0:
        orb_values += [orb_current, orb_current * 0.75, orb_current * 1.25]
    options = [prev._gap_option("atr", round(v, 3)) for v in sorted({v for v in atr_values if v >= 0})]
    options += [prev._gap_option("orb", round(v, 3)) for v in sorted({v for v in orb_values if v >= 0})]
    return _unique_options(options)


def _wide_stop_options(symbol: str, config: StrategyConfig) -> list[prev.OptionSpec]:
    if symbol == "NQ":
        thresholds = [75.0, 100.0, 125.0, 150.0]
    elif symbol == "ES":
        thresholds = [12.5, 15.0, 20.0, 25.0, 30.0]
    else:
        thresholds = [15.0, 20.0, 30.0, 40.0, 50.0]
    rr_values = [1.0, 1.25, 1.5, 2.0, 3.0]
    options = [
        prev.OptionSpec(
            "wide_stop",
            "wide_none",
            "wide stop target compression off",
            direct={"wide_stop_target_threshold_points": 0.0, "wide_stop_target_rr": 0.0},
        )
    ]
    for threshold in thresholds:
        for rr in rr_values:
            if rr > config.rr:
                continue
            options.append(
                prev.OptionSpec(
                    "wide_stop",
                    f"wide_t{_slug_num(threshold)}_rr{_slug_num(rr)}",
                    f"if stop >= {threshold:g} pts, target rr={rr:g}",
                    direct={"wide_stop_target_threshold_points": threshold, "wide_stop_target_rr": rr},
                )
            )
    return _unique_options(options)


def _reentry_options() -> list[prev.OptionSpec]:
    return [
        prev.OptionSpec("reentry", "cap1", "one trade/session", direct={"orb_trade_max_per_session": 1, "orb_reentry_policy": "any_reentry"}),
        prev.OptionSpec("reentry", "cap2_any", "up to two trades", direct={"orb_trade_max_per_session": 2, "orb_reentry_policy": "any_reentry"}),
        prev.OptionSpec("reentry", "cap2_nonpos", "second trade after <=0R", direct={"orb_trade_max_per_session": 2, "orb_reentry_policy": "after_nonpositive_first"}),
        prev.OptionSpec("reentry", "cap2_sl", "second trade after SL", direct={"orb_trade_max_per_session": 2, "orb_reentry_policy": "after_sl_first"}),
        prev.OptionSpec("reentry", "cap2_full", "second trade after full target", direct={"orb_trade_max_per_session": 2, "orb_reentry_policy": "after_full_target_first"}),
        prev.OptionSpec("reentry", "cap3_any", "up to three trades", direct={"orb_trade_max_per_session": 3, "orb_reentry_policy": "any_reentry"}),
        prev.OptionSpec("reentry", "cap3_nonpos", "third trade path after <=0R", direct={"orb_trade_max_per_session": 3, "orb_reentry_policy": "after_nonpositive_first"}),
        prev.OptionSpec("reentry", "uncapped_any", "uncapped non-overlap", direct={"orb_trade_max_per_session": 0, "orb_reentry_policy": "any_reentry"}),
    ]


def _pre_entry_cancel_options(*, htf: bool = False) -> list[prev.OptionSpec]:
    options = [
        prev.OptionSpec(
            "pre_entry_cancel",
            "pre_cancel_none",
            "no pre-entry target-touch cancel",
            direct={
                "limit_cancel_on_pre_entry_target_touch": "",
                "limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep": False,
            },
        ),
        prev.OptionSpec(
            "pre_entry_cancel",
            "pre_cancel_tp1",
            "cancel pending limit after TP1 touch",
            direct={
                "limit_cancel_on_pre_entry_target_touch": "tp1",
                "limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep": False,
            },
        ),
        prev.OptionSpec(
            "pre_entry_cancel",
            "pre_cancel_tp2",
            "cancel pending limit after TP2 touch",
            direct={
                "limit_cancel_on_pre_entry_target_touch": "tp2",
                "limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep": False,
            },
        ),
    ]
    if htf:
        options.append(
            prev.OptionSpec(
                "pre_entry_cancel",
                "pre_cancel_tp1_after_htf_sweep",
                "cancel TP1 touch only after fresh HTF sweep",
                direct={
                    "limit_cancel_on_pre_entry_target_touch": "tp1",
                    "limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep": True,
                },
            )
        )
    return options


def _orb_options_local(leg: prev.LegSpec, config: StrategyConfig) -> dict[str, list[prev.OptionSpec]]:
    session = config.sessions[0]
    seed_orb = prev._orb_minutes(session)
    if session.name == "NY":
        orb_values = [seed_orb - 10, seed_orb - 5, seed_orb, seed_orb + 5, seed_orb + 10, 8, 10, 15, 20, 25, 30]
        entry_values = ["11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:30"]
        flat_values = ["13:30", "14:00", "14:30", "15:00", "15:30", "15:50"]
    else:
        orb_values = [seed_orb - 15, seed_orb - 5, seed_orb, seed_orb + 5, seed_orb + 15, 10, 15, 20, 30, 45, 60]
        entry_values = ["22:00", "22:30", "23:00", "23:15", "23:30", "00:00", "01:00", "03:00", "04:00", "06:00"]
        flat_values = ["00:00", "03:00", "04:00", "05:00", "06:00", "07:00"]

    high_rr = leg.symbol == "GC" and session.name == "NY"
    low_rr = session.name == "Asia" and leg.symbol == "ES"
    return {
        "orb_window": [_orb_window_option(session, value) for value in sorted({int(v) for v in orb_values if 5 <= int(v) <= 75})],
        "entry_end": _entry_end_options("entry_end", _dedupe_values([session.entry_end] + entry_values)),
        "flat_start": _flat_start_options(_dedupe_values([session.flat_start] + flat_values)),
        "rr_tp1": _rr_tp_options(config, high_rr=high_rr, low_rr=low_rr),
        "stop": _stop_options(leg.symbol, config),
        "gap": _gap_options(leg.symbol, config),
        "atr": [
            prev.OptionSpec("atr", f"atr{value}", f"atr_length={value}", direct={"atr_length": value})
            for value in sorted({config.atr_length, 5, 7, 10, 12, 14, 20, 30})
        ],
        "direction": [
            prev.OptionSpec("direction", f"dir_{value}", f"direction={value}", direct={"direction_filter": value})
            for value in ("long", "short", "both")
        ],
        "dow": _dow_options(config),
        "icf": [
            prev.OptionSpec("icf", "icf_off", "impulse close filter off", direct={"impulse_close_filter": False}),
            prev.OptionSpec("icf", "icf_on", "impulse close filter on", direct={"impulse_close_filter": True}),
        ],
        "reentry": _reentry_options(),
        "fvg_selection": [
            prev.OptionSpec("fvg_selection", "fvg_first", "first FVG", direct={"continuation_fvg_selection": "first"}),
            prev.OptionSpec("fvg_selection", "fvg_extreme", "extreme/chasing FVG", direct={"continuation_fvg_selection": "extreme"}),
        ],
        "wide_stop": _wide_stop_options(leg.symbol, config),
        "pre_entry_cancel": _pre_entry_cancel_options(),
    }


def _lsi_common_options(leg: prev.LegSpec, config: StrategyConfig) -> dict[str, list[prev.OptionSpec]]:
    session = config.sessions[0]
    is_asia = session.name == "Asia"
    if is_asia:
        entry_values = ["22:00", "22:30", "23:00", "23:15", "23:30", "00:00", "01:00", "03:00"]
        flat_values = ["00:00", "03:00", "04:00", "05:00", "06:00", "07:00"]
    else:
        entry_values = ["10:15", "10:30", "11:00", "12:00", "13:00", "14:00", "15:00", "15:30"]
        flat_values = ["13:30", "14:30", "15:00", "15:30", "15:50"]

    high_rr = leg.symbol == "GC"
    return {
        "entry_end": [
            prev.OptionSpec(
                "entry_end",
                f"entry_{value.replace(':', '')}",
                f"entry_end={value}",
                session={"entry_end": value, "sweep_end": value},
            )
            for value in _dedupe_values([session.entry_end] + entry_values)
        ],
        "flat_start": _flat_start_options(_dedupe_values([session.flat_start] + flat_values)),
        "rr_tp1": _rr_tp_options(config, high_rr=high_rr),
        "gap": [
            prev.OptionSpec("gap", f"gap{_slug_num(value)}", f"min_gap_atr_pct={value:g}", session={"min_gap_atr_pct": value})
            for value in sorted({session.min_gap_atr_pct, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0})
        ],
        "atr": [
            prev.OptionSpec("atr", f"atr{value}", f"atr_length={value}", direct={"atr_length": value})
            for value in sorted({config.atr_length, 5, 7, 10, 14, 20, 30})
        ],
        "fvg_window": [
            prev.OptionSpec(
                "fvg_window",
                f"fvgL{left}_R{right}",
                f"FVG {left}/{right}",
                direct={"lsi_fvg_window_left": left, "lsi_fvg_window_right": right},
            )
            for left, right in _dedupe_values([
                (config.lsi_fvg_window_left, config.lsi_fvg_window_right),
                (7, 3), (10, 2), (10, 5), (10, 10), (20, 2), (20, 3), (20, 5), (30, 5), (33, 3), (60, 9),
            ])
        ],
        "direction": [
            prev.OptionSpec("direction", f"dir_{value}", f"direction={value}", direct={"direction_filter": value})
            for value in ("long", "short", "both")
        ],
        "entry_mode": [
            prev.OptionSpec("entry_mode", "mode_fvg_limit", "FVG limit entry", direct={"lsi_entry_mode": "fvg_limit", "lsi_close_on_sweep_to_inversion_minutes": 0}),
            prev.OptionSpec("entry_mode", "mode_close", "close entry", direct={"lsi_entry_mode": "close", "lsi_close_on_sweep_to_inversion_minutes": 0}),
            prev.OptionSpec("entry_mode", "mode_level_limit", "level limit entry", direct={"lsi_entry_mode": "level_limit", "lsi_close_on_sweep_to_inversion_minutes": 0}),
            prev.OptionSpec("entry_mode", "mode_timed_hybrid_30", "timed hybrid <=30m close", direct={"lsi_entry_mode": "timed_hybrid", "lsi_close_on_sweep_to_inversion_minutes": 30}),
            prev.OptionSpec("entry_mode", "mode_timed_hybrid_60", "timed hybrid <=60m close", direct={"lsi_entry_mode": "timed_hybrid", "lsi_close_on_sweep_to_inversion_minutes": 60}),
        ],
        "dow": _dow_options(config),
        "lsi_stop_mode": [
            prev.OptionSpec("lsi_stop_mode", f"stop_{mode}", f"lsi_stop_mode={mode}", direct={"lsi_stop_mode": mode})
            for mode in ("absolute", "fvg", "gap_1x", "gap_2x", "struct_50pct", "struct_75pct")
        ],
        "lsi_target_mode": [
            prev.OptionSpec("lsi_target_mode", f"target_{mode}", f"lsi_target_mode={mode}", direct={"lsi_target_mode": mode})
            for mode in ("risk", "structural", "left_structure")
        ],
        "lsi_clean_path": [
            prev.OptionSpec("lsi_clean_path", "clean_off", "clean path off", direct={"lsi_clean_path": False}),
            prev.OptionSpec("lsi_clean_path", "clean_on", "clean path on", direct={"lsi_clean_path": True}),
        ],
        "lsi_first_fvg": [
            prev.OptionSpec("lsi_first_fvg", "first_fvg_off", "first FVG only off", direct={"lsi_first_fvg_only": False}),
            prev.OptionSpec("lsi_first_fvg", "first_fvg_on", "first FVG only on", direct={"lsi_first_fvg_only": True}),
        ],
        "lsi_sweep_gate": [
            prev.OptionSpec("lsi_sweep_gate", f"sweep_gate_{gate}", f"lsi_sweep_gate={gate}", direct={"lsi_sweep_gate": gate})
            for gate in ("sweep_window", "entry", "rth")
        ],
        "lsi_stale_pivot": [
            prev.OptionSpec("lsi_stale_pivot", "stale_consumes_on", "stale breach consumes pivot", direct={"lsi_stale_breach_consumes_pivot": True}),
            prev.OptionSpec("lsi_stale_pivot", "stale_consumes_off", "stale breach does not consume pivot", direct={"lsi_stale_breach_consumes_pivot": False}),
        ],
        "pre_entry_cancel": _pre_entry_cancel_options(htf=leg.kind == "htf_lsi"),
    }


def _classic_lsi_options_local(leg: prev.LegSpec, config: StrategyConfig) -> dict[str, list[prev.OptionSpec]]:
    options = _lsi_common_options(leg, config)
    session = config.sessions[0]
    right_values = [24, 36, 45, 48, 60, 75, 90, 120] if session.name == "Asia" else [36, 45, 60, 75, 90, 120]
    options.update(
        {
            "n_left": [
                prev.OptionSpec("n_left", f"nL{value}", f"lsi_n_left={value}", direct={"lsi_n_left": value})
                for value in sorted({config.lsi_n_left, 2, 3, 5, 8, 10, 12})
            ],
            "n_right": [
                prev.OptionSpec("n_right", f"nR{value}", f"lsi_n_right={value}", direct={"lsi_n_right": value})
                for value in sorted({config.lsi_n_right, *right_values})
            ],
        }
    )
    return options


def _htf_lsi_options_local(leg: prev.LegSpec, config: StrategyConfig) -> dict[str, list[prev.OptionSpec]]:
    options = _lsi_common_options(leg, config)
    session = config.sessions[0]
    starts = _dedupe_values([session.entry_start, "08:00", "08:30", "09:00", "09:30"])
    ends = _dedupe_values([session.entry_end, "12:30", "13:00", "13:30", "14:00", "14:30", "15:00"])
    windows = []
    for start in starts:
        for end in ends:
            if _minutes(start) < _minutes(end):
                windows.append((start, end))
    options.update(
        {
            "entry_window": [
                prev.OptionSpec(
                    "entry_window",
                    f"window_{start.replace(':', '')}_{end.replace(':', '')}",
                    f"{start}-{end}",
                    session={"entry_start": start, "entry_end": end, "sweep_start": start, "sweep_end": end},
                )
                for start, end in windows
            ],
            "max_inv": [
                prev.OptionSpec("max_inv", f"lag{value}", f"max_fvg_to_inversion_bars={value}", direct={"max_fvg_to_inversion_bars": value})
                for value in sorted({config.max_fvg_to_inversion_bars, 0, 8, 12, 16, 24, 36, 48})
            ],
            "trade_cap": [
                prev.OptionSpec("trade_cap", f"cap{value}", f"htf_trade_max_per_session={value}", direct={"htf_trade_max_per_session": value})
                for value in (1, 2, 3, 0)
            ],
            "htf_left": [
                prev.OptionSpec("htf_left", f"htfN{value}", f"htf_n_left={value}", direct={"htf_n_left": value})
                for value in sorted({config.htf_n_left, 2, 3, 4, 5, 6})
            ],
            "htf_tf": [
                prev.OptionSpec("htf_tf", f"htf{value}", f"htf_level_tf_minutes={value}", direct={"htf_level_tf_minutes": value})
                for value in (30, 60, 90)
            ],
            "htf_sweep_source": [
                prev.OptionSpec("htf_sweep_source", "src_htf", "HTF levels only", direct={"htf_lsi_include_htf_levels": True, "htf_lsi_include_eqhl_levels": False}),
                prev.OptionSpec("htf_sweep_source", "src_htf_eqhl", "HTF + EQH/EQL levels", direct={"htf_lsi_include_htf_levels": True, "htf_lsi_include_eqhl_levels": True}),
                prev.OptionSpec("htf_sweep_source", "src_eqhl", "EQH/EQL levels only", direct={"htf_lsi_include_htf_levels": False, "htf_lsi_include_eqhl_levels": True}),
            ],
        }
    )
    return options


def _options_for_seed(leg: prev.LegSpec, config: StrategyConfig) -> dict[str, list[prev.OptionSpec]]:
    if leg.kind == "orb":
        return _orb_options_local(leg, config)
    if leg.kind == "htf_lsi":
        return _htf_lsi_options_local(leg, config)
    return _classic_lsi_options_local(leg, config)


def _lookup_options(leg: prev.LegSpec) -> dict[str, prev.OptionSpec]:
    out = {}
    for options in prev._options_for_leg(leg).values():
        for option in options:
            out[option.option_id] = option
    return out


def _config_from_prev_row(leg: prev.LegSpec, row: dict[str, Any], seed_name: str) -> StrategyConfig:
    lookup = _lookup_options(leg)
    options = []
    for option_id in str(row["option_ids"]).split("|"):
        option = lookup.get(option_id)
        if option is not None:
            options.append(option)
    return prev._variant_config(leg.base_config, f"{leg.key}__{seed_name}", options)


def _seed_variants(leg: prev.LegSpec, summary: dict[str, Any]) -> list[prev.VariantSpec]:
    seeds = []
    for seed_key, section in (
        ("prev_curve_calmar", "best_curve_calmar_by_leg"),
        ("prev_curve_net", "best_curve_net_by_leg"),
    ):
        row = summary[section].get(leg.key)
        if not row:
            continue
        config = _config_from_prev_row(leg, row, seed_key)
        seeds.append(
            prev.VariantSpec(
                leg.key,
                seed_key,
                "seed",
                "seed",
                f"{seed_key}: {row['label']}",
                tuple(str(row["option_ids"]).split("|")),
                config,
            )
        )
    return prev._dedupe_variants(seeds)


def _variant_from_options(
    leg: prev.LegSpec,
    seed: prev.VariantSpec,
    variant_id: str,
    stage: str,
    category: str,
    options: list[prev.OptionSpec],
) -> prev.VariantSpec | None:
    try:
        config = prev._variant_config(seed.config, f"{leg.key}__{variant_id}"[:240], options)
    except ValueError as exc:
        print(f"    skip invalid {variant_id}: {exc}", flush=True)
        return None
    return prev.VariantSpec(
        leg.key,
        variant_id,
        stage,
        category,
        ", ".join(option.label for option in options) if options else seed.label,
        tuple(option.option_id for option in options) if options else seed.option_ids,
        config,
    )


def _oat_variants(leg: prev.LegSpec, seeds: list[prev.VariantSpec]) -> tuple[list[prev.VariantSpec], dict[str, dict[str, prev.OptionSpec]]]:
    variants = []
    option_lookup_by_category: dict[str, dict[str, prev.OptionSpec]] = defaultdict(dict)
    for seed in seeds:
        options_by_category = _options_for_seed(leg, seed.config)
        for category, options in options_by_category.items():
            for option in options:
                option_lookup_by_category[category][option.option_id] = option
                variant = _variant_from_options(
                    leg,
                    seed,
                    f"{seed.variant_id}__oat__{option.option_id}",
                    "oat",
                    category,
                    [option],
                )
                if variant is not None:
                    variants.append(variant)
    return prev._dedupe_variants(variants), option_lookup_by_category


def _apply_gate(trades: list[TradeResult], lookup: dict[str, str], gate_id: str) -> list[TradeResult]:
    if gate_id == "gate_none" or not lookup:
        return trades
    rule = GATE_RULES[gate_id]
    include = set(rule["include"])
    exclude = set(rule["exclude"])
    out = []
    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL:
            out.append(trade)
            continue
        regime = lookup.get(trade.date)
        if include and regime not in include:
            continue
        if exclude and regime in exclude:
            continue
        out.append(trade)
    return out


def _score_rows_for_results(
    leg: prev.LegSpec,
    loaded: prev.LoadedData,
    variants: list[prev.VariantSpec],
    results: dict[str, list[TradeResult]],
    *,
    period_start: str,
    period_end: str,
    cal_2025_start: str,
    cal_2025_end: str,
) -> list[dict[str, Any]]:
    rows = []
    for variant in variants:
        trades = results[variant.config.name]
        for gate_id in GATE_RULES:
            gated = _apply_gate(trades, loaded.regime_lookup, gate_id)
            row = prev._score_metric_row(
                leg,
                variant,
                gated,
                gate_id=gate_id,
                period_start=period_start,
                period_end=period_end,
                cal_2025_start=cal_2025_start,
                cal_2025_end=cal_2025_end,
            )
            rows.append(row)
    return rows


def _add_scores(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        net = float(row["last1_net_r"] or 0.0)
        calmar = float(row["last1_calmar"] or 0.0)
        dd = abs(float(row["last1_dd_r"] or 0.0))
        pf = float(row["last1_pf"] or 0.0)
        fills = int(row["last1_fills"] or 0)
        fill_penalty = 0.0 if row["eligible_min_fills"] else (prev.MIN_FILLS_BY_KIND[row["kind"]] - fills) * 2.0
        squeeze_score = net + 2.0 * calmar + 1.5 * math.log(max(pf, 1.0)) - 0.25 * dd - fill_penalty
        net_dd_score = net / max(dd, 1.0)
        out.append(
            {
                **row,
                "squeeze_score": round(squeeze_score, 4),
                "net_dd_score": round(net_dd_score, 4),
            }
        )
    return out


def _select_options(
    oat_rows: list[dict[str, Any]],
    option_lookup_by_category: dict[str, dict[str, prev.OptionSpec]],
) -> tuple[dict[str, list[prev.OptionSpec]], list[str]]:
    rows = [
        row for row in oat_rows
        if row["stage"] == "oat"
        and row["eligible_min_fills"]
        and float(row["last1_net_r"] or -999) > 0
    ]
    selected: dict[str, list[prev.OptionSpec]] = {}
    category_best: dict[str, float] = {}
    for category, lookup in option_lookup_by_category.items():
        cat_rows = [row for row in rows if row["category"] == category and row["primary_option"] in lookup]
        cat_rows.sort(
            key=lambda row: (
                float(row["squeeze_score"] or -999),
                float(row["last1_calmar"] or -999),
                float(row["last1_net_r"] or -999),
            ),
            reverse=True,
        )
        picked = []
        seen = set()
        for row in cat_rows:
            option_id = str(row["primary_option"])
            if option_id in seen:
                continue
            seen.add(option_id)
            picked.append(lookup[option_id])
            if len(picked) >= KEEP_OPTIONS_PER_CATEGORY:
                break
        if not picked:
            picked = list(lookup.values())[:KEEP_OPTIONS_PER_CATEGORY]
        selected[category] = picked
        category_best[category] = float(cat_rows[0]["squeeze_score"] or -999) if cat_rows else -999.0

    priority = sorted(category_best, key=lambda category: category_best[category], reverse=True)
    return selected, priority[:MAX_COMBO_CATEGORIES]


def _combo_variants(
    leg: prev.LegSpec,
    seeds: list[prev.VariantSpec],
    selected: dict[str, list[prev.OptionSpec]],
    combo_categories: list[str],
) -> list[prev.VariantSpec]:
    variants = []
    for seed in seeds:
        option_groups = [selected[category] for category in combo_categories]
        for combo in product(*option_groups):
            suffix = "__".join(option.option_id for option in combo)
            variant = _variant_from_options(
                leg,
                seed,
                f"{seed.variant_id}__combo__{suffix}",
                "combo",
                "combo",
                list(combo),
            )
            if variant is not None:
                variants.append(variant)
    return prev._dedupe_variants(variants)


def _add_plateau_stats_fast(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["stage"] == "combo":
            grouped[(row["leg"], row["gate"])].append(row)

    stats: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (leg, gate), group in grouped.items():
        vector_map: dict[tuple[str, ...], dict[str, Any]] = {}
        category_values: dict[int, set[str]] = defaultdict(set)
        for row in group:
            vector = tuple(str(row["option_ids"]).split("|"))
            vector_map[vector] = row
            for idx, option_id in enumerate(vector):
                category_values[idx].add(option_id)
        for vector, row in vector_map.items():
            candidate_calmar = float(row["last1_calmar"] or 0.0)
            neighbor_values = []
            if candidate_calmar > 0:
                for idx, values in category_values.items():
                    for value in values:
                        if value == vector[idx]:
                            continue
                        neighbor = list(vector)
                        neighbor[idx] = value
                        other = vector_map.get(tuple(neighbor))
                        if other is None:
                            continue
                        val = float(other["last1_calmar"] or 0.0)
                        if math.isfinite(val):
                            neighbor_values.append(val)
            if neighbor_values:
                median_neighbor = float(np.median(neighbor_values))
                ge80 = sum(1 for value in neighbor_values if value >= 0.80 * candidate_calmar)
                ge60 = sum(1 for value in neighbor_values if value >= 0.60 * candidate_calmar)
                ratio = median_neighbor / candidate_calmar if candidate_calmar else 0.0
            else:
                median_neighbor = 0.0
                ge80 = 0
                ge60 = 0
                ratio = 0.0
            if len(neighbor_values) >= 3 and ratio >= 0.60 and ge80 >= 2:
                surface = "curve"
            elif len(neighbor_values) >= 2 and ratio >= 0.45 and ge60 >= 2:
                surface = "soft_curve"
            else:
                surface = "cliff"
            stats[(leg, gate, row["variant_id"])] = {
                "neighbor_count": len(neighbor_values),
                "neighbor_median_calmar": prev._round(median_neighbor, 3),
                "neighbor_ge80_count": ge80,
                "neighbor_ge60_count": ge60,
                "plateau_ratio": prev._round(ratio, 3),
                "surface": surface,
            }

    out = []
    for row in rows:
        out.append(
            {
                **row,
                **stats.get(
                    (row["leg"], row["gate"], row["variant_id"]),
                    {
                        "neighbor_count": 0,
                        "neighbor_median_calmar": None,
                        "neighbor_ge80_count": 0,
                        "neighbor_ge60_count": 0,
                        "plateau_ratio": None,
                        "surface": "n/a",
                    },
                ),
            }
        )
    return out


def _top_rows(rows: list[dict[str, Any]], leg_key: str, metric: str, *, require_curve: bool, limit: int = 5) -> list[dict[str, Any]]:
    leg_rows = [
        row for row in rows
        if row["leg"] == leg_key
        and row["variant_id"] != "baseline"
        and row["eligible_min_fills"]
        and float(row["last1_net_r"] or -999) > 0
    ]
    if require_curve:
        leg_rows = [row for row in leg_rows if row["surface"] in {"curve", "soft_curve"}]
    return sorted(
        leg_rows,
        key=lambda row: (
            float(row[metric] or -999),
            float(row["last1_calmar"] or -999),
            float(row["last1_net_r"] or -999),
            float(row["last1_pf"] or 0.0),
        ),
        reverse=True,
    )[:limit]


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _short_variant(row: dict[str, Any]) -> str:
    label = str(row.get("label", ""))
    return label if len(label) <= 180 else label[:177] + "..."


def _write_report(
    legs: list[prev.LegSpec],
    rows: list[dict[str, Any]],
    selected_manifest: dict[str, Any],
    combo_categories: dict[str, list[str]],
    *,
    period_start: str,
    period_end: str,
    loaded_start: str,
) -> None:
    lines = [
        "# Hot One-Year Squeeze",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Window: `{period_start}` to `{period_end}`",
        f"- Loaded warmup starts: `{loaded_start}`",
        "- Scope: the nine screenshot legs only; `GC Asia LSI` was not included.",
        "- Objective: squeeze last-year Calmar and net/DD without Bailey-style deflation.",
        "- Added: wider local grids, richer regime gates, ORB wide-stop compression, extra ORB reentry policies, split directions, finer windows, and extra LSI stop/target/entry modes.",
        "",
        "## Cross-Leg Winners",
        "",
        "| leg | best squeeze | gate | surface | fills | net_r | calmar | pf | dd | y2025_r | plateau |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for leg in legs:
        row = (_top_rows(rows, leg.key, "squeeze_score", require_curve=True, limit=1) or [None])[0]
        if row is None:
            continue
        lines.append(
            f"| {leg.key} | {_short_variant(row)} | {row['gate']} | {row['surface']} | "
            f"{row['last1_fills']} | {_fmt(row['last1_net_r'])} | {_fmt(row['last1_calmar'])} | "
            f"{_fmt(row['last1_pf'])} | {_fmt(row['last1_dd_r'])} | {_fmt(row['y2025_net_r'])} | {_fmt(row.get('plateau_ratio'))} |"
        )

    for leg in legs:
        lines += [
            "",
            f"## {leg.label}",
            "",
            "| pick | gate | surface | fills | net_r | calmar | pf | dd | squeeze | y2025_r | plateau | variant |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        picks = [
            ("best_curve_squeeze", _top_rows(rows, leg.key, "squeeze_score", require_curve=True, limit=1)),
            ("best_curve_calmar", _top_rows(rows, leg.key, "last1_calmar", require_curve=True, limit=1)),
            ("best_curve_net", _top_rows(rows, leg.key, "last1_net_r", require_curve=True, limit=1)),
            ("best_raw_calmar", _top_rows(rows, leg.key, "last1_calmar", require_curve=False, limit=1)),
            ("best_raw_net", _top_rows(rows, leg.key, "last1_net_r", require_curve=False, limit=1)),
        ]
        seen = set()
        for name, found in picks:
            if not found:
                continue
            row = found[0]
            key = (name, row["variant_id"], row["gate"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"| {name} | {row['gate']} | {row['surface']} | {row['last1_fills']} | "
                f"{_fmt(row['last1_net_r'])} | {_fmt(row['last1_calmar'])} | {_fmt(row['last1_pf'])} | "
                f"{_fmt(row['last1_dd_r'])} | {_fmt(row['squeeze_score'])} | {_fmt(row['y2025_net_r'])} | "
                f"{_fmt(row.get('plateau_ratio'))} | {_short_variant(row)} |"
            )
        lines += [
            "",
            f"Combo categories searched: `{', '.join(combo_categories.get(leg.key, []))}`",
            "",
            "<details><summary>Selected local options</summary>",
            "",
            "```json",
            json.dumps(selected_manifest.get(leg.key, {}), indent=2, sort_keys=True),
            "```",
            "",
            "</details>",
        ]

    lines += [
        "",
        "## Read",
        "",
        "- These are TESTING-only hot-regime candidates optimized directly on the last year.",
        "- `curve`/`soft_curve` rows passed a one-step local-neighbor check inside the final combo grid.",
        "- `raw` rows are diagnostics; use them only if a follow-up local grid turns the area from cliff into curve.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def _write_asset_notes(legs: list[prev.LegSpec], rows: list[dict[str, Any]], period_start: str, period_end: str) -> None:
    by_symbol: dict[str, list[prev.LegSpec]] = defaultdict(list)
    for leg in legs:
        by_symbol[leg.symbol].append(leg)
    paths = {"NQ": prev.NQ_LEARNINGS_PATH, "ES": prev.ES_LEARNINGS_PATH, "GC": prev.GC_LEARNINGS_PATH}
    for symbol, symbol_legs in by_symbol.items():
        lines = [
            "",
            f"- **Hot one-year squeeze** (2026-05-03): `backtesting/learnings/reports/HOT_ONE_YEAR_SQUEEZE_20260503.md`",
            f"  - Window: `{period_start}` to `{period_end}`. TESTING-only second-stage local squeeze around prior screenshot winners.",
        ]
        for leg in symbol_legs:
            row = (_top_rows(rows, leg.key, "squeeze_score", require_curve=True, limit=1) or [None])[0]
            if row is None:
                continue
            lines.append(
                f"  - {leg.label}: `{row['variant_id']}` with `{row['gate']}` -> "
                f"{row['last1_fills']} fills, `{row['last1_net_r']}R`, Calmar `{row['last1_calmar']}`, "
                f"PF `{row['last1_pf']}`, DD `{row['last1_dd_r']}R`, surface `{row['surface']}`."
            )
        path = paths[symbol]
        path.write_text(path.read_text().rstrip() + "\n" + "\n".join(lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    previous_summary = json.loads(PREV_SUMMARY_PATH.read_text())
    period_start = str(previous_summary["period_start"])
    period_end = str(previous_summary["period_end"])
    end_exclusive = str(previous_summary["end_exclusive"])
    cal_2025_start = "2025-01-01"
    cal_2025_end = "2025-12-31"

    all_legs = {leg.key: leg for leg in prev._base_legs()}
    legs = [all_legs[key] for key in REQUESTED_LEGS]
    end_date = prev._available_end_inclusive(sorted({leg.symbol for leg in legs}))
    print(f"Common data end: {end_date}", flush=True)
    print(f"Squeeze window: {period_start} to {period_end}", flush=True)

    loaded_cache: dict[tuple[str, str], prev.LoadedData] = {}
    all_rows: list[dict[str, Any]] = []
    all_manifest: list[dict[str, Any]] = []
    selected_manifest: dict[str, Any] = {}
    combo_categories_by_leg: dict[str, list[str]] = {}

    for leg in legs:
        print(f"\n=== {leg.label} ===", flush=True)
        key = (leg.symbol, leg.timeframe)
        if key not in loaded_cache:
            loaded_cache[key] = prev._load_data(leg.symbol, leg.timeframe, end_date, period_start)
        loaded = loaded_cache[key]

        baseline = prev._baseline_variant(leg)
        baseline_results = prev._run_variants(leg, loaded, [baseline], start_date=period_start, end_date=end_exclusive)
        all_rows.extend(
            _score_rows_for_results(
                leg,
                loaded,
                [baseline],
                baseline_results,
                period_start=period_start,
                period_end=period_end,
                cal_2025_start=cal_2025_start,
                cal_2025_end=cal_2025_end,
            )
        )
        all_manifest.append(prev._manifest_row(leg, baseline))

        seeds = _seed_variants(leg, previous_summary)
        print(f"    seeds: {[seed.variant_id for seed in seeds]}", flush=True)

        seed_results = prev._run_variants(leg, loaded, seeds, start_date=period_start, end_date=end_exclusive)
        seed_rows = _score_rows_for_results(
            leg,
            loaded,
            seeds,
            seed_results,
            period_start=period_start,
            period_end=period_end,
            cal_2025_start=cal_2025_start,
            cal_2025_end=cal_2025_end,
        )
        all_rows.extend(seed_rows)
        for seed in seeds:
            all_manifest.append(prev._manifest_row(leg, seed))

        oat_variants, option_lookup_by_category = _oat_variants(leg, seeds)
        print(f"    OAT variants: {len(oat_variants)}", flush=True)
        oat_results = prev._run_variants(leg, loaded, oat_variants, start_date=period_start, end_date=end_exclusive)
        oat_rows = _add_scores(
            _score_rows_for_results(
                leg,
                loaded,
                oat_variants,
                oat_results,
                period_start=period_start,
                period_end=period_end,
                cal_2025_start=cal_2025_start,
                cal_2025_end=cal_2025_end,
            )
        )
        all_rows.extend(oat_rows)
        for variant in oat_variants:
            all_manifest.append(prev._manifest_row(leg, variant))

        selected, combo_categories = _select_options(oat_rows, option_lookup_by_category)
        selected_manifest[leg.key] = {category: [option.option_id for option in options] for category, options in selected.items()}
        combo_categories_by_leg[leg.key] = combo_categories
        print(f"    combo categories: {combo_categories}", flush=True)

        combo_variants = _combo_variants(leg, seeds, selected, combo_categories)
        print(f"    combo variants: {len(combo_variants)}", flush=True)
        combo_results = prev._run_variants(leg, loaded, combo_variants, start_date=period_start, end_date=end_exclusive)
        combo_rows = _score_rows_for_results(
            leg,
            loaded,
            combo_variants,
            combo_results,
            period_start=period_start,
            period_end=period_end,
            cal_2025_start=cal_2025_start,
            cal_2025_end=cal_2025_end,
        )
        all_rows.extend(combo_rows)
        for variant in combo_variants:
            all_manifest.append(prev._manifest_row(leg, variant))

    scored_rows = _add_scores(prev._add_baseline_deltas(all_rows))
    scored_rows = _add_plateau_stats_fast(scored_rows)

    pd.DataFrame(scored_rows).to_csv(RESULT_DIR / "score_rows.csv", index=False)
    pd.DataFrame(all_manifest).drop_duplicates().to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    (RESULT_DIR / "selected_options.json").write_text(json.dumps(prev._safe_json(selected_manifest), indent=2, sort_keys=True))
    (RESULT_DIR / "combo_categories.json").write_text(json.dumps(combo_categories_by_leg, indent=2, sort_keys=True))

    summary = {
        "run_slug": RUN_SLUG,
        "period_start": period_start,
        "period_end": period_end,
        "end_exclusive": end_exclusive,
        "load_start": prev.LOAD_START,
        "gate_rules": GATE_RULES,
        "combo_categories_by_leg": combo_categories_by_leg,
        "best_curve_squeeze_by_leg": {
            leg.key: (_top_rows(scored_rows, leg.key, "squeeze_score", require_curve=True, limit=1) or [None])[0]
            for leg in legs
        },
        "best_curve_calmar_by_leg": {
            leg.key: (_top_rows(scored_rows, leg.key, "last1_calmar", require_curve=True, limit=1) or [None])[0]
            for leg in legs
        },
        "best_curve_net_by_leg": {
            leg.key: (_top_rows(scored_rows, leg.key, "last1_net_r", require_curve=True, limit=1) or [None])[0]
            for leg in legs
        },
        "best_raw_calmar_by_leg": {
            leg.key: (_top_rows(scored_rows, leg.key, "last1_calmar", require_curve=False, limit=1) or [None])[0]
            for leg in legs
        },
        "best_raw_net_by_leg": {
            leg.key: (_top_rows(scored_rows, leg.key, "last1_net_r", require_curve=False, limit=1) or [None])[0]
            for leg in legs
        },
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(prev._safe_json(summary), indent=2, sort_keys=True, default=str))

    _write_report(
        legs,
        scored_rows,
        selected_manifest,
        combo_categories_by_leg,
        period_start=period_start,
        period_end=period_end,
        loaded_start=prev.LOAD_START,
    )
    _write_asset_notes(legs, scored_rows, period_start, period_end)
    print(f"\nDONE: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
