#!/usr/bin/env python3
"""Hot-regime ablation/optimization pass for the active ALPHA_V1 legs.

This is intentionally *not* a robust-promotion workflow. It mirrors the spirit
of TESTING's H_ORB_ABLATED leg: find high-R, recent-regime candidates that may
be useful for forward testing while similar market conditions persist, then
report the 10-year context as the warning layer.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config  # noqa: E402
from orb_backtest.analysis.gates import apply_dow_filter  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ, Instrument  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, run_backtest  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "alpha_v1_hot_regime_ablation_20260503"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_HOT_REGIME_ABLATION_20260503.md"
ALPHA_PATH = ROOT / "learnings" / "ALPHA_V1.md"
NQ_LEARNINGS_PATH = ROOT / "learnings" / "asset" / "NQ.md"
ES_LEARNINGS_PATH = ROOT / "learnings" / "asset" / "ES.md"

FULL_START = "2016-04-17"
WORKERS = 6

HOT_SCORE_FORMULA = (
    "3*last1_net + 2*last2_net + full_net "
    "- 0.50*abs(last1_dd) - 0.25*abs(last2_dd) - 0.10*abs(full_dd) "
    "- 10*full_negative_years - 25*(last1_fills<12)"
)

DOW_LABELS = {
    0: "Mon",
    1: "Tue",
    2: "Wed",
    3: "Thu",
    4: "Fri",
}


@dataclass(frozen=True)
class LoadedData:
    instrument: Instrument
    df_5m: pd.DataFrame
    df_1m: pd.DataFrame | None
    df_1s: pd.DataFrame | None
    signal_df_1m: pd.DataFrame | None


@dataclass(frozen=True)
class LegSpec:
    key: str
    label: str
    kind: str
    config: StrategyConfig


@dataclass(frozen=True)
class OptionSpec:
    category: str
    option_id: str
    label: str
    direct: dict[str, Any] | None = None
    session: dict[str, Any] | None = None


@dataclass(frozen=True)
class VariantSpec:
    leg_key: str
    variant_id: str
    stage: str
    category: str
    label: str
    option_ids: tuple[str, ...]
    config: StrategyConfig


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * 100.0, 2)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        if abs(value) >= 100:
            return f"{value:.1f}"
        if abs(value) >= 10:
            return f"{value:.2f}"
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body]) if body else "\n".join([header, sep])


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        val = float(data)
        return val if math.isfinite(val) else None
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    return data


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return out.dropna(subset=["open", "high", "low", "close"]).astype(float)


def _data_file_for(instrument: Instrument) -> str:
    return f"{instrument.symbol}_5m.parquet"


def _load_data(instrument: Instrument) -> LoadedData:
    filename = _data_file_for(instrument)
    try:
        df_5m = load_5m_data(filename, start=FULL_START, end=None)
    except FileNotFoundError:
        df_1s = load_1s_for_5m(filename, start=FULL_START, end=None)
        df_5m = _resample_ohlcv(df_1s, "5min")

    try:
        df_1m = load_1m_for_5m(filename, start=FULL_START, end=None)
    except FileNotFoundError:
        df_1s = load_1s_for_5m(filename, start=FULL_START, end=None)
        df_1m = _resample_ohlcv(df_1s, "1min")

    try:
        df_1s = load_1s_for_5m(filename, start=FULL_START, end=None)
    except FileNotFoundError:
        df_1s = None

    return LoadedData(
        instrument=instrument,
        df_5m=df_5m,
        df_1m=df_1m,
        df_1s=df_1s,
        signal_df_1m=df_1m,
    )


def _available_end_exclusive(data_by_symbol: dict[str, LoadedData]) -> tuple[str, str]:
    max_dates = [loaded.df_5m.index.max().normalize() for loaded in data_by_symbol.values()]
    end_inclusive = min(max_dates)
    end_exclusive = end_inclusive + pd.Timedelta(days=1)
    return end_inclusive.date().isoformat(), end_exclusive.date().isoformat()


def _active_alpha_v1_legs() -> list[LegSpec]:
    nq_ny_htf_lsi = build_current_nq_ny_htf_lsi_lag24_config(
        name="alpha_v1_hot_nq_ny_htf_lsi_baseline"
    )

    nq_asia = StrategyConfig(
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
        name="alpha_v1_hot_nq_asia_orb_baseline",
    )

    es_asia = StrategyConfig(
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
        name="alpha_v1_hot_es_asia_orb_baseline",
    )

    es_ny = StrategyConfig(
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
        name="alpha_v1_hot_es_ny_orb_baseline",
    )

    return [
        LegSpec("nq_ny_htf_lsi", "NQ NY HTF-LSI", "htf_lsi", nq_ny_htf_lsi),
        LegSpec("nq_asia_orb", "NQ Asia ORB", "orb", nq_asia),
        LegSpec("es_asia_orb", "ES Asia ORB", "orb", es_asia),
        LegSpec("es_ny_orb", "ES NY ORB", "orb", es_ny),
    ]


def _session_replace(config: StrategyConfig, **updates: Any) -> StrategyConfig:
    return replace(config, sessions=(replace(config.sessions[0], **updates),))


def _variant_config(base: StrategyConfig, name: str, option: OptionSpec | list[OptionSpec]) -> StrategyConfig:
    options = option if isinstance(option, list) else [option]
    direct: dict[str, Any] = {}
    session: dict[str, Any] = {}
    option_labels = []
    for opt in options:
        option_labels.append(opt.option_id)
        if opt.direct:
            direct.update(opt.direct)
        if opt.session:
            session.update(opt.session)
    cfg = base
    if session:
        cfg = _session_replace(cfg, **session)
    if direct:
        cfg = replace(cfg, **direct)
    return replace(
        cfg,
        name=name,
        notes="Hot-regime ALPHA_V1 ablation candidate: " + ",".join(option_labels),
    )


def _dedupe_variants(variants: list[VariantSpec]) -> list[VariantSpec]:
    seen: set[str] = set()
    out: list[VariantSpec] = []
    for variant in variants:
        payload = asdict(variant.config)
        payload.pop("name", None)
        payload.pop("notes", None)
        key = json.dumps(_safe_json(payload), sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(variant)
    return out


def _filled(trades: list[TradeResult]) -> list[TradeResult]:
    return [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]


def _risk_quantiles(trades: list[TradeResult], min_tick: float) -> dict[str, float]:
    values = np.asarray([trade.risk_points for trade in _filled(trades) if trade.risk_points > 0.0], dtype=float)
    if len(values) == 0:
        return {"q75": 0.0, "q85": 0.0}
    out: dict[str, float] = {}
    for label, q in (("q75", 0.75), ("q85", 0.85)):
        raw = float(np.quantile(values, q))
        rounded = math.ceil(raw / min_tick) * min_tick if min_tick > 0 else raw
        out[label] = round(float(rounded), 6)
    return out


def _valid_rr_tp1(rr: float, tp1: float) -> bool:
    return rr >= 1.0 and (rr * tp1) >= 1.0


def _dow_option(option_id: str, excluded: tuple[int, ...]) -> OptionSpec:
    if excluded:
        label = "exclude " + ",".join(DOW_LABELS[d] for d in excluded)
    else:
        label = "include all weekdays"
    return OptionSpec("dow", option_id, label, direct={"excluded_days": excluded})


def _rr_option(rr: float, tp1: float) -> OptionSpec:
    return OptionSpec(
        "rr_tp1",
        f"rr{str(rr).replace('.', 'p')}_tp{str(tp1).replace('.', 'p')}",
        f"rr={rr:g}, tp1={tp1:g}",
        direct={"rr": rr, "tp1_ratio": tp1},
    )


def _orb_options(leg: LegSpec, baseline_trades: list[TradeResult]) -> dict[str, list[OptionSpec]]:
    base = leg.config
    session = base.sessions[0]
    risk_q = _risk_quantiles(baseline_trades, base.min_tick)

    if leg.key == "nq_asia_orb":
        entry_ends = ("22:30", "23:15", "00:00")
        stops = (75.0, 100.0, 125.0)
        gaps = (0.0, 5.0, 10.0, 15.0)
        rr_tp = ((4.0, 0.3), (5.0, 0.25), (6.0, 0.3), (7.0, 0.2), (8.0, 0.2))
        atrs = (5, 7, 14)
        stop_key = "stop_orb_pct"
        gap_key = "min_gap_orb_pct"
    elif leg.key == "es_asia_orb":
        entry_ends = ("02:00", "03:00", "04:00", "06:00")
        stops = (75.0, 100.0, 125.0, 150.0)
        gaps = (0.0, 0.25, 0.5, 0.75, 1.0)
        rr_tp = ((1.5, 0.7), (2.0, 0.5), (2.5, 0.4), (3.0, 0.35), (4.0, 0.25))
        atrs = (7, 10, 14, 20)
        stop_key = "stop_orb_pct"
        gap_key = "min_gap_atr_pct"
    else:
        entry_ends = ("11:00", "12:00", "13:00", "14:00")
        stops = (3.0, 4.0, 5.0, 6.0, 7.0)
        gaps = (0.0, 0.1, 0.25, 0.5, 0.75)
        rr_tp = ((3.0, 0.35), (4.0, 0.25), (5.0, 0.2), (6.0, 0.2), (7.0, 0.2))
        atrs = (5, 7, 10, 14)
        stop_key = "stop_atr_pct"
        gap_key = "min_gap_atr_pct"

    dow_options = [_dow_option("dow_baseline", tuple(base.excluded_days))]
    if tuple(base.excluded_days) != ():
        dow_options.append(_dow_option("dow_none", ()))
    for day in range(5):
        excluded = (day,)
        if excluded != tuple(base.excluded_days):
            dow_options.append(_dow_option(f"dow_ex{DOW_LABELS[day]}", excluded))

    reentry_options = [
        OptionSpec(
            "reentry",
            "cap1",
            "one trade per session",
            direct={"orb_trade_max_per_session": 1, "orb_reentry_policy": "any_reentry"},
        ),
        OptionSpec(
            "reentry",
            "cap2_after_nonpositive",
            "second trade only after <=0R first trade",
            direct={"orb_trade_max_per_session": 2, "orb_reentry_policy": "after_nonpositive_first"},
        ),
        OptionSpec(
            "reentry",
            "cap2_any",
            "up to two non-overlapping trades",
            direct={"orb_trade_max_per_session": 2, "orb_reentry_policy": "any_reentry"},
        ),
        OptionSpec(
            "reentry",
            "uncapped_any",
            "uncapped non-overlapping trades",
            direct={"orb_trade_max_per_session": 0, "orb_reentry_policy": "any_reentry"},
        ),
    ]

    wide_options = [
        OptionSpec(
            "wide_stop",
            "wide_none",
            "no wide-stop target compression",
            direct={"wide_stop_target_threshold_points": 0.0, "wide_stop_target_rr": 0.0},
        )
    ]
    for q_label, threshold in risk_q.items():
        for target_rr in (1.0, 1.5, 2.0, 3.0):
            if target_rr <= base.rr and target_rr >= 1.0 and threshold > 0:
                wide_options.append(
                    OptionSpec(
                        "wide_stop",
                        f"wide_{q_label}_rr{str(target_rr).replace('.', 'p')}",
                        f"if risk>={threshold:g} pts, target rr={target_rr:g}",
                        direct={
                            "wide_stop_target_threshold_points": threshold,
                            "wide_stop_target_rr": target_rr,
                        },
                    )
                )

    return {
        "entry": [
            OptionSpec("entry", f"entry_{value.replace(':', '')}", f"entry_end={value}", session={"entry_end": value})
            for value in entry_ends
        ],
        "dow": dow_options,
        "rr_tp1": [_rr_option(rr, tp1) for rr, tp1 in rr_tp if _valid_rr_tp1(rr, tp1)],
        "stop": [
            OptionSpec("stop", f"{stop_key}_{str(value).replace('.', 'p')}", f"{stop_key}={value:g}", session={stop_key: value})
            for value in stops
        ],
        "gap": [
            OptionSpec("gap", f"{gap_key}_{str(value).replace('.', 'p')}", f"{gap_key}={value:g}", session={gap_key: value})
            for value in gaps
        ],
        "atr": [
            OptionSpec("atr", f"atr{value}", f"atr_length={value}", direct={"atr_length": value})
            for value in atrs
        ],
        "reentry": reentry_options,
        "fvg_selection": [
            OptionSpec("fvg_selection", "fvg_first", "first valid FVG", direct={"continuation_fvg_selection": "first"}),
            OptionSpec("fvg_selection", "fvg_extreme", "chase more extreme same-day FVG", direct={"continuation_fvg_selection": "extreme"}),
        ],
        "wide_stop": wide_options,
    }


def _htf_lsi_options(leg: LegSpec, baseline_trades: list[TradeResult]) -> dict[str, list[OptionSpec]]:
    base = leg.config
    return {
        "entry_window": [
            OptionSpec("entry_window", f"window_{s.replace(':', '')}_{e.replace(':', '')}", f"{s}-{e}", session={"entry_start": s, "entry_end": e})
            for s, e in (
                ("08:30", "11:30"),
                ("08:30", "12:30"),
                ("08:30", "13:30"),
                ("08:30", "14:30"),
                ("09:30", "13:30"),
            )
        ],
        "dow": [
            _dow_option("dow_none", ()),
            *[_dow_option(f"dow_ex{DOW_LABELS[day]}", (day,)) for day in range(5)],
        ],
        "rr_tp1": [
            _rr_option(rr, tp1)
            for rr, tp1 in (
                (2.0, 0.5),
                (2.5, 0.4),
                (3.0, 0.4),
                (3.5, 0.4),
                (4.0, 0.3),
                (5.0, 0.2),
            )
            if _valid_rr_tp1(rr, tp1)
        ],
        "min_gap": [
            OptionSpec("min_gap", f"gap{str(value).replace('.', 'p')}", f"min_gap_atr_pct={value:g}", session={"min_gap_atr_pct": value})
            for value in (1.0, 2.0, 3.0, 4.0, 5.0)
        ],
        "fvg_window": [
            OptionSpec(
                "fvg_window",
                f"fvgL{left}_R{right}",
                f"lsi_fvg_window_left={left}, right={right}",
                direct={"lsi_fvg_window_left": left, "lsi_fvg_window_right": right},
            )
            for left, right in ((10, 2), (20, 1), (20, 2), (20, 5), (30, 2), (30, 5))
        ],
        "max_inv": [
            OptionSpec("max_inv", f"lag{value}", f"max_fvg_to_inversion_bars={value}", direct={"max_fvg_to_inversion_bars": value})
            for value in (0, 12, 24, 36, 48)
        ],
        "trade_cap": [
            OptionSpec("trade_cap", f"cap{value}", f"htf_trade_max_per_session={value}", direct={"htf_trade_max_per_session": value})
            for value in (1, 2, 3, 0)
        ],
        "htf_left": [
            OptionSpec("htf_left", f"htfN{value}", f"htf_n_left={value}", direct={"htf_n_left": value})
            for value in (2, 3, 4, 5)
        ],
        "entry_mode": [
            OptionSpec("entry_mode", "mode_fvg_limit", "FVG limit entry", direct={"lsi_entry_mode": "fvg_limit"}),
            OptionSpec("entry_mode", "mode_close", "close entry", direct={"lsi_entry_mode": "close"}),
        ],
    }


def _options_for_leg(leg: LegSpec, baseline_trades: list[TradeResult]) -> dict[str, list[OptionSpec]]:
    if leg.kind == "htf_lsi":
        return _htf_lsi_options(leg, baseline_trades)
    return _orb_options(leg, baseline_trades)


def _baseline_variant(leg: LegSpec) -> VariantSpec:
    return VariantSpec(
        leg_key=leg.key,
        variant_id="baseline",
        stage="baseline",
        category="baseline",
        label="Current ALPHA_V1 baseline",
        option_ids=("baseline",),
        config=replace(leg.config, name=f"{leg.key}__baseline"),
    )


def _oat_variants(leg: LegSpec, options_by_category: dict[str, list[OptionSpec]]) -> list[VariantSpec]:
    variants = []
    for category, options in options_by_category.items():
        for option in options:
            name = f"{leg.key}__oat__{option.option_id}"
            try:
                config = _variant_config(leg.config, name, option)
            except ValueError as exc:
                print(f"    skip invalid OAT {name}: {exc}", flush=True)
                continue
            variants.append(
                VariantSpec(
                    leg_key=leg.key,
                    variant_id=f"oat__{option.option_id}",
                    stage="oat",
                    category=category,
                    label=option.label,
                    option_ids=(option.option_id,),
                    config=config,
                )
            )
    return _dedupe_variants(variants)


def _cfg_payload(config: StrategyConfig) -> str:
    payload = asdict(config)
    payload.pop("name", None)
    payload.pop("notes", None)
    return json.dumps(_safe_json(payload), sort_keys=True, default=str)


def _best_options_from_oat(
    *,
    leg: LegSpec,
    options_by_category: dict[str, list[OptionSpec]],
    oat_score_rows: list[dict[str, Any]],
    keep_by_category: dict[str, int],
) -> dict[str, list[OptionSpec]]:
    baseline_payload = _cfg_payload(leg.config)
    option_lookup = {option.option_id: option for options in options_by_category.values() for option in options}
    best: dict[str, list[OptionSpec]] = {}
    for category, options in options_by_category.items():
        category_rows = [row for row in oat_score_rows if row["category"] == category]
        category_rows.sort(key=lambda row: float(row["hot_score"]), reverse=True)
        selected: list[OptionSpec] = []

        # Keep the baseline-equivalent option visible when one exists.
        for option in options:
            try:
                if _cfg_payload(_variant_config(leg.config, "tmp", option)) == baseline_payload:
                    selected.append(option)
                    break
            except ValueError:
                continue

        for row in category_rows:
            opt = option_lookup.get(str(row["primary_option"]))
            if opt is None or opt in selected:
                continue
            selected.append(opt)
            if len(selected) >= keep_by_category.get(category, 2):
                break
        if not selected:
            selected = options[:1]
        best[category] = selected[: keep_by_category.get(category, 2)]
    return best


def _combo_categories(kind: str) -> dict[str, int]:
    if kind == "htf_lsi":
        return {
            "entry_window": 2,
            "dow": 2,
            "rr_tp1": 2,
            "min_gap": 2,
            "fvg_window": 2,
            "max_inv": 2,
            "trade_cap": 2,
            "entry_mode": 1,
        }
    return {
        "entry": 2,
        "dow": 2,
        "rr_tp1": 2,
        "stop": 2,
        "gap": 2,
        "reentry": 2,
        "fvg_selection": 1,
        "wide_stop": 1,
    }


def _combo_variants(
    leg: LegSpec,
    selected_options: dict[str, list[OptionSpec]],
    *,
    cap: int = 180,
) -> list[VariantSpec]:
    categories = [cat for cat in _combo_categories(leg.kind) if cat in selected_options]
    variants: list[VariantSpec] = []
    for combo in product(*(selected_options[cat] for cat in categories)):
        option_ids = tuple(option.option_id for option in combo)
        suffix = "__".join(option_ids)
        name = f"{leg.key}__combo__{suffix}"[:240]
        try:
            config = _variant_config(leg.config, name, list(combo))
        except ValueError as exc:
            print(f"    skip invalid combo {name}: {exc}", flush=True)
            continue
        variants.append(
            VariantSpec(
                leg_key=leg.key,
                variant_id=f"combo__{suffix}",
                stage="combo",
                category="combo_grid",
                label=", ".join(option.label for option in combo),
                option_ids=option_ids,
                config=config,
            )
        )
    variants = _dedupe_variants(variants)
    if len(variants) > cap:
        # Deterministic thinning while keeping broad coverage across the option grid.
        idx = np.linspace(0, len(variants) - 1, num=cap, dtype=int)
        variants = [variants[int(i)] for i in idx]
    return variants


def _run_variants(
    loaded: LoadedData,
    variants: list[VariantSpec],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    if not variants:
        return {}
    configs = [variant.config for variant in variants]
    print(f"    running {len(configs)} configs", flush=True)
    results = run_sweep(
        loaded.df_5m,
        configs,
        n_workers=min(WORKERS, max(1, len(configs))),
        start_date=start_date,
        end_date=end_date,
        df_1m=loaded.df_1m,
        df_1s=loaded.df_1s,
        signal_df_1m=loaded.signal_df_1m,
    )
    out: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        out[config.name] = sorted(trades, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))
    return out


def _window_filter(trades: list[TradeResult], start: str, end_inclusive: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end_inclusive]


def _metric_row(
    *,
    leg: LegSpec,
    variant: VariantSpec,
    trades: list[TradeResult],
    window: str,
    start: str,
    end_inclusive: str,
) -> dict[str, Any]:
    selected = _window_filter(trades, start, end_inclusive)
    metrics = compute_metrics(selected)
    r_by_year = metrics.get("r_by_year") or {}
    return {
        "leg": leg.key,
        "leg_label": leg.label,
        "variant_id": variant.variant_id,
        "stage": variant.stage,
        "category": variant.category,
        "label": variant.label,
        "primary_option": variant.option_ids[0] if variant.option_ids else "",
        "option_ids": ",".join(variant.option_ids),
        "window": window,
        "start": start,
        "end": end_inclusive,
        "signals": int(metrics["total_signals"]),
        "fills": int(metrics["total_trades"]),
        "no_fills": int(metrics["no_fills"]),
        "net_r": _round(metrics["total_r"], 2),
        "win_rate_pct": _pct(metrics["win_rate"]),
        "profit_factor": _round(metrics["profit_factor"], 3),
        "avg_r": _round(metrics["avg_r"], 4),
        "sharpe_ratio": _round(metrics["sharpe_ratio"], 3),
        "max_drawdown_r": _round(metrics["max_drawdown_r"], 2),
        "calmar_ratio": _round(metrics["calmar_ratio"], 3),
        "negative_years": int(sum(1 for value in r_by_year.values() if value < 0)),
    }


def _score_from_window_rows(rows: list[dict[str, Any]]) -> float:
    by_window = {row["window"]: row for row in rows}
    full = by_window["full"]
    last2 = by_window["last_2y"]
    last1 = by_window["last_1y"]
    score = (
        3.0 * float(last1["net_r"])
        + 2.0 * float(last2["net_r"])
        + float(full["net_r"])
        - 0.50 * abs(float(last1["max_drawdown_r"]))
        - 0.25 * abs(float(last2["max_drawdown_r"]))
        - 0.10 * abs(float(full["max_drawdown_r"]))
        - 10.0 * int(full["negative_years"])
    )
    if int(last1["fills"]) < 12:
        score -= 25.0
    return round(score, 3)


def _score_rows(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in metric_rows:
        grouped[(row["leg"], row["variant_id"])].append(row)

    scores = []
    for (leg, variant), rows in grouped.items():
        if {row["window"] for row in rows} >= {"full", "last_2y", "last_1y"}:
            first = rows[0]
            by_window = {row["window"]: row for row in rows}
            baseline = variant == "baseline"
            scores.append(
                {
                    "leg": leg,
                    "variant_id": variant,
                    "stage": first["stage"],
                    "category": first["category"],
                    "label": first["label"],
                    "primary_option": first["primary_option"],
                    "option_ids": first["option_ids"],
                    "hot_score": _score_from_window_rows(rows),
                    "full_net_r": by_window["full"]["net_r"],
                    "full_dd_r": by_window["full"]["max_drawdown_r"],
                    "full_pf": by_window["full"]["profit_factor"],
                    "full_fills": by_window["full"]["fills"],
                    "full_negative_years": by_window["full"]["negative_years"],
                    "last2_net_r": by_window["last_2y"]["net_r"],
                    "last2_dd_r": by_window["last_2y"]["max_drawdown_r"],
                    "last2_pf": by_window["last_2y"]["profit_factor"],
                    "last2_fills": by_window["last_2y"]["fills"],
                    "last1_net_r": by_window["last_1y"]["net_r"],
                    "last1_dd_r": by_window["last_1y"]["max_drawdown_r"],
                    "last1_pf": by_window["last_1y"]["profit_factor"],
                    "last1_fills": by_window["last_1y"]["fills"],
                    "is_baseline": baseline,
                }
            )
    return scores


def _add_deltas(score_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline_by_leg = {row["leg"]: row for row in score_rows if row["variant_id"] == "baseline"}
    out = []
    for row in score_rows:
        baseline = baseline_by_leg[row["leg"]]
        out.append(
            {
                **row,
                "delta_hot_score": _round(float(row["hot_score"]) - float(baseline["hot_score"]), 2),
                "delta_full_net_r": _round(float(row["full_net_r"]) - float(baseline["full_net_r"]), 2),
                "delta_last2_net_r": _round(float(row["last2_net_r"]) - float(baseline["last2_net_r"]), 2),
                "delta_last1_net_r": _round(float(row["last1_net_r"]) - float(baseline["last1_net_r"]), 2),
                "delta_full_dd_r": _round(float(row["full_dd_r"]) - float(baseline["full_dd_r"]), 2),
                "delta_last1_dd_r": _round(float(row["last1_dd_r"]) - float(baseline["last1_dd_r"]), 2),
            }
        )
    return out


def _manifest_row(variant: VariantSpec) -> dict[str, Any]:
    session = variant.config.sessions[0]
    return {
        "leg": variant.leg_key,
        "variant_id": variant.variant_id,
        "stage": variant.stage,
        "category": variant.category,
        "label": variant.label,
        "option_ids": ",".join(variant.option_ids),
        "strategy": variant.config.strategy,
        "direction_filter": variant.config.direction_filter,
        "entry_start": session.entry_start,
        "entry_end": session.entry_end,
        "flat_start": session.flat_start,
        "rr": variant.config.rr,
        "tp1_ratio": variant.config.tp1_ratio,
        "atr_length": variant.config.atr_length,
        "excluded_days": ",".join(str(day) for day in variant.config.excluded_days),
        "stop_atr_pct": session.stop_atr_pct,
        "stop_orb_pct": session.stop_orb_pct,
        "min_gap_atr_pct": session.min_gap_atr_pct,
        "min_gap_orb_pct": session.min_gap_orb_pct,
        "orb_trade_max_per_session": variant.config.orb_trade_max_per_session,
        "orb_reentry_policy": variant.config.orb_reentry_policy,
        "continuation_fvg_selection": variant.config.continuation_fvg_selection,
        "wide_stop_target_threshold_points": variant.config.wide_stop_target_threshold_points,
        "wide_stop_target_rr": variant.config.wide_stop_target_rr,
        "lsi_entry_mode": variant.config.lsi_entry_mode,
        "lsi_fvg_window_left": variant.config.lsi_fvg_window_left,
        "lsi_fvg_window_right": variant.config.lsi_fvg_window_right,
        "max_fvg_to_inversion_bars": variant.config.max_fvg_to_inversion_bars,
        "htf_trade_max_per_session": variant.config.htf_trade_max_per_session,
        "htf_n_left": variant.config.htf_n_left,
    }


def _annual_rows(variant_results: dict[str, tuple[LegSpec, VariantSpec, list[TradeResult]]]) -> list[dict[str, Any]]:
    rows = []
    for _, (leg, variant, trades) in variant_results.items():
        if variant.stage not in {"baseline", "combo"}:
            continue
        r_by_year = compute_metrics(trades).get("r_by_year") or {}
        for year, net_r in r_by_year.items():
            rows.append(
                {
                    "leg": leg.key,
                    "variant_id": variant.variant_id,
                    "year": year,
                    "net_r": _round(net_r, 2),
                }
            )
    return rows


def _top_for_leg(score_rows: list[dict[str, Any]], leg_key: str, key: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = [row for row in score_rows if row["leg"] == leg_key and not row["is_baseline"]]
    return sorted(
        rows,
        key=lambda row: (
            float(row[key]),
            float(row["last1_pf"] or 0.0),
            float(row["delta_last1_dd_r"] or 0.0),
        ),
        reverse=True,
    )[:limit]


def _baseline_for_leg(score_rows: list[dict[str, Any]], leg_key: str) -> dict[str, Any]:
    return next(row for row in score_rows if row["leg"] == leg_key and row["is_baseline"])


def _top_oat(score_rows: list[dict[str, Any]], leg_key: str, *, limit: int = 8) -> list[dict[str, Any]]:
    rows = [
        row for row in score_rows
        if row["leg"] == leg_key and row["stage"] == "oat" and not row["is_baseline"]
    ]
    return sorted(rows, key=lambda row: float(row["delta_hot_score"]), reverse=True)[:limit]


def _worst_oat(score_rows: list[dict[str, Any]], leg_key: str, *, limit: int = 5) -> list[dict[str, Any]]:
    rows = [
        row for row in score_rows
        if row["leg"] == leg_key and row["stage"] == "oat" and not row["is_baseline"]
    ]
    return sorted(rows, key=lambda row: float(row["delta_hot_score"]))[:limit]


def _full_warning(row: dict[str, Any]) -> str:
    warnings = []
    if int(row["full_negative_years"]) > 0:
        warnings.append(f"{row['full_negative_years']} negative years")
    if float(row["full_dd_r"]) < -25:
        warnings.append(f"deep full DD {row['full_dd_r']}R")
    if float(row["full_pf"] or 0) < 1.15:
        warnings.append(f"low full PF {row['full_pf']}")
    if int(row["last1_fills"]) < 12:
        warnings.append(f"thin last-1y count {row['last1_fills']}")
    return "; ".join(warnings) if warnings else "warning layer acceptable for TESTING"


def _portfolio_daily(trades_by_leg: dict[str, list[TradeResult]]) -> pd.Series:
    daily: dict[pd.Timestamp, float] = defaultdict(float)
    for trades in trades_by_leg.values():
        for trade in _filled(trades):
            daily[pd.Timestamp(trade.date)] += float(trade.r_multiple)
    if not daily:
        return pd.Series(dtype=float)
    return pd.Series(daily).sort_index()


def _series_dd(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    curve = series.cumsum()
    peak = curve.cummax()
    return float((curve - peak).min())


def _portfolio_row(label: str, trades_by_leg: dict[str, list[TradeResult]], windows: dict[str, tuple[str, str]]) -> dict[str, Any]:
    row = {"portfolio": label}
    all_trades = sorted([trade for trades in trades_by_leg.values() for trade in trades], key=lambda t: (t.date, t.signal_bar))
    for window, (start, end) in windows.items():
        selected_by_leg = {leg: _window_filter(trades, start, end) for leg, trades in trades_by_leg.items()}
        selected_all = [trade for trades in selected_by_leg.values() for trade in trades]
        metrics = compute_metrics(selected_all)
        daily = _portfolio_daily(selected_by_leg)
        row[f"{window}_fills"] = int(metrics["total_trades"])
        row[f"{window}_net_r"] = _round(metrics["total_r"], 2)
        row[f"{window}_pf"] = _round(metrics["profit_factor"], 3)
        row[f"{window}_dd_r"] = _round(_series_dd(daily), 2)
    full_metrics = compute_metrics(all_trades)
    row["full_negative_years"] = int(sum(1 for value in (full_metrics.get("r_by_year") or {}).values() if value < 0))
    return row


def _write_report(
    *,
    end_inclusive: str,
    windows: dict[str, tuple[str, str]],
    score_rows: list[dict[str, Any]],
    portfolio_rows: list[dict[str, Any]],
    h_orb_context: dict[str, Any],
) -> None:
    lines = [
        "# ALPHA_V1 Hot-Regime Ablation",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Window: `{FULL_START}` to `{end_inclusive}`",
        "- Intent: deliberately search for TESTING-only high-R hot-regime candidates, inspired by `H_ORB_ABLATED`.",
        "- This is not a robust promotion packet. Full-history stats are shown as warning context.",
        f"- Hot score: `{HOT_SCORE_FORMULA}`",
        "",
        "## Execution Context",
        "",
        "- `TESTING.H_ORB_ABLATED` is dry-mode only (`webhooks: []`).",
        "- Its style: no stress gate, no Tuesday, later signal window, EMA disabled, body filter removed, all non-overlap reentries, and no wide-stop target reduction (`reduced_target_rr=2R`).",
        "- This pass borrows the *research posture*, not the Hunter-specific rules.",
        "",
        "```json",
        json.dumps(h_orb_context, indent=2, sort_keys=True),
        "```",
        "",
        "## Baselines",
        "",
    ]

    baseline_rows = []
    for leg in ("nq_ny_htf_lsi", "nq_asia_orb", "es_asia_orb", "es_ny_orb"):
        row = _baseline_for_leg(score_rows, leg)
        baseline_rows.append(
            {
                "leg": leg,
                "full_net": row["full_net_r"],
                "full_dd": row["full_dd_r"],
                "full_pf": row["full_pf"],
                "last2_net": row["last2_net_r"],
                "last1_net": row["last1_net_r"],
                "last1_pf": row["last1_pf"],
                "last1_fills": row["last1_fills"],
                "hot_score": row["hot_score"],
            }
        )
    lines.append(
        _markdown_table(
            baseline_rows,
            ["leg", "full_net", "full_dd", "full_pf", "last2_net", "last1_net", "last1_pf", "last1_fills", "hot_score"],
        )
    )
    lines.extend(["", "## Hot Candidates By Leg", ""])

    for leg in ("nq_ny_htf_lsi", "nq_asia_orb", "es_asia_orb", "es_ny_orb"):
        baseline = _baseline_for_leg(score_rows, leg)
        best_last1 = _top_for_leg(score_rows, leg, "last1_net_r", limit=1)[0]
        best_last2 = _top_for_leg(score_rows, leg, "last2_net_r", limit=1)[0]
        best_score = _top_for_leg(score_rows, leg, "hot_score", limit=1)[0]
        rows = []
        for label, row in (("baseline", baseline), ("best_last1", best_last1), ("best_last2", best_last2), ("best_score", best_score)):
            rows.append(
                {
                    "pick": label,
                    "variant": row["variant_id"][:80],
                    "stage": row["stage"],
                    "full_net": row["full_net_r"],
                    "full_dd": row["full_dd_r"],
                    "full_pf": row["full_pf"],
                    "neg_y": row["full_negative_years"],
                    "last2_net": row["last2_net_r"],
                    "last1_net": row["last1_net_r"],
                    "last1_dd": row["last1_dd_r"],
                    "last1_pf": row["last1_pf"],
                    "fills1y": row["last1_fills"],
                    "hot_score": row["hot_score"],
                    "warning": _full_warning(row),
                }
            )
        lines.extend(
            [
                f"### {baseline['leg']}",
                "",
                _markdown_table(
                    rows,
                    [
                        "pick",
                        "variant",
                        "stage",
                        "full_net",
                        "full_dd",
                        "full_pf",
                        "neg_y",
                        "last2_net",
                        "last1_net",
                        "last1_dd",
                        "last1_pf",
                        "fills1y",
                        "hot_score",
                        "warning",
                    ],
                ),
                "",
                "**Top OAT contributors**",
                "",
                _markdown_table(
                    _top_oat(score_rows, leg),
                    [
                        "category",
                        "primary_option",
                        "label",
                        "delta_hot_score",
                        "delta_last1_net_r",
                        "delta_last2_net_r",
                        "delta_full_net_r",
                        "delta_last1_dd_r",
                    ],
                ),
                "",
                "**Worst OAT removals/changes**",
                "",
                _markdown_table(
                    _worst_oat(score_rows, leg),
                    [
                        "category",
                        "primary_option",
                        "label",
                        "delta_hot_score",
                        "delta_last1_net_r",
                        "delta_last2_net_r",
                        "delta_full_net_r",
                    ],
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Portfolio View",
            "",
            "This is a simple separate-account R aggregation of replacing each leg with its per-leg best hot-score row. It is a sizing/read-through proxy, not a prop simulation.",
            "",
            _markdown_table(
                portfolio_rows,
                [
                    "portfolio",
                    "full_fills",
                    "full_net_r",
                    "full_pf",
                    "full_dd_r",
                    "full_negative_years",
                    "last_2y_fills",
                    "last_2y_net_r",
                    "last_2y_pf",
                    "last_2y_dd_r",
                    "last_1y_fills",
                    "last_1y_net_r",
                    "last_1y_pf",
                    "last_1y_dd_r",
                ],
            ),
            "",
            "## Interpretation",
            "",
            "- Treat any last-1y winner here as a TESTING-only branch. The point is forward observation, not portfolio promotion.",
            "- A candidate is more interesting when it improves last 1y and last 2y together without exploding full-history DD or creating many negative full years.",
            "- Candidates that win last 1y by removing protective filters but degrade full-history PF/DD are exactly the hot-regime archetype: potentially useful while conditions persist, fragile when they stop.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def _read_h_orb_ablated_context() -> dict[str, Any]:
    config_path = REPO_ROOT / "execution" / "config" / "exec_configs.json"
    raw = json.loads(config_path.read_text())
    return raw["TESTING"]["sessions"]["H_ORB_ABLATED"]


def _write_learnings(score_rows: list[dict[str, Any]], portfolio_rows: list[dict[str, Any]], end_inclusive: str) -> None:
    def pick(leg: str) -> dict[str, Any]:
        return _top_for_leg(score_rows, leg, "hot_score", limit=1)[0]

    picks = {leg: pick(leg) for leg in ("nq_ny_htf_lsi", "nq_asia_orb", "es_asia_orb", "es_ny_orb")}
    alpha_note = f"""

### Hot-Regime Ablation / Overfit Candidate Pass (2026-05-03)

Report: `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_ABLATION_20260503.md`

Artifacts: `backtesting/data/results/alpha_v1_hot_regime_ablation_20260503/`

Intentional TESTING-only research pass inspired by `TESTING.H_ORB_ABLATED`: maximize recent R with last 1y weighted most, last 2y second, and full 10y as warning context. Hot score used: `{HOT_SCORE_FORMULA}`. Window was `{FULL_START}` to `{end_inclusive}`.

Best hot-score candidates by active leg:

| Leg | Candidate | Full R / DD | Last 2y R | Last 1y R | Warning |
|-----|-----------|-------------|-----------|-----------|---------|
| NQ NY HTF-LSI | `{picks['nq_ny_htf_lsi']['variant_id']}` | `{picks['nq_ny_htf_lsi']['full_net_r']}R / {picks['nq_ny_htf_lsi']['full_dd_r']}R` | `{picks['nq_ny_htf_lsi']['last2_net_r']}R` | `{picks['nq_ny_htf_lsi']['last1_net_r']}R` | {_full_warning(picks['nq_ny_htf_lsi'])} |
| NQ Asia ORB | `{picks['nq_asia_orb']['variant_id']}` | `{picks['nq_asia_orb']['full_net_r']}R / {picks['nq_asia_orb']['full_dd_r']}R` | `{picks['nq_asia_orb']['last2_net_r']}R` | `{picks['nq_asia_orb']['last1_net_r']}R` | {_full_warning(picks['nq_asia_orb'])} |
| ES Asia ORB | `{picks['es_asia_orb']['variant_id']}` | `{picks['es_asia_orb']['full_net_r']}R / {picks['es_asia_orb']['full_dd_r']}R` | `{picks['es_asia_orb']['last2_net_r']}R` | `{picks['es_asia_orb']['last1_net_r']}R` | {_full_warning(picks['es_asia_orb'])} |
| ES NY ORB | `{picks['es_ny_orb']['variant_id']}` | `{picks['es_ny_orb']['full_net_r']}R / {picks['es_ny_orb']['full_dd_r']}R` | `{picks['es_ny_orb']['last2_net_r']}R` | `{picks['es_ny_orb']['last1_net_r']}R` | {_full_warning(picks['es_ny_orb'])} |

Research read: this pass should not supersede the robust ALPHA_V1 operating profile. Use it to select dry-run TESTING candidates only, with full-history drawdown/negative-year warnings attached.
"""
    ALPHA_PATH.write_text(ALPHA_PATH.read_text().rstrip() + "\n" + alpha_note.strip() + "\n")

    nq_note = f"""

- **ALPHA_V1 hot-regime ablation pass** (2026-05-03): `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_ABLATION_20260503.md`
  - Scope included the active NQ legs: NQ NY HTF-LSI and NQ Asia ORB, plus ES legs for portfolio context. This is TESTING-only, overfit-aware research inspired by `H_ORB_ABLATED`, not a robust promotion packet.
  - Best NQ NY HTF-LSI hot-score branch: `{picks['nq_ny_htf_lsi']['variant_id']}` -> full `{picks['nq_ny_htf_lsi']['full_net_r']}R / {picks['nq_ny_htf_lsi']['full_dd_r']}R DD`, last 2y `{picks['nq_ny_htf_lsi']['last2_net_r']}R`, last 1y `{picks['nq_ny_htf_lsi']['last1_net_r']}R`; warning: {_full_warning(picks['nq_ny_htf_lsi'])}.
  - Best NQ Asia ORB hot-score branch: `{picks['nq_asia_orb']['variant_id']}` -> full `{picks['nq_asia_orb']['full_net_r']}R / {picks['nq_asia_orb']['full_dd_r']}R DD`, last 2y `{picks['nq_asia_orb']['last2_net_r']}R`, last 1y `{picks['nq_asia_orb']['last1_net_r']}R`; warning: {_full_warning(picks['nq_asia_orb'])}.
"""
    NQ_LEARNINGS_PATH.write_text(NQ_LEARNINGS_PATH.read_text().rstrip() + "\n" + nq_note.strip() + "\n")

    es_note = f"""

- **ALPHA_V1 hot-regime ablation pass** (2026-05-03): `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_ABLATION_20260503.md`
  - Scope included ES Asia ORB and ES NY ORB from the active ALPHA_V1 sleeve. This is TESTING-only, overfit-aware research inspired by `H_ORB_ABLATED`, not a robust promotion packet.
  - Best ES Asia ORB hot-score branch: `{picks['es_asia_orb']['variant_id']}` -> full `{picks['es_asia_orb']['full_net_r']}R / {picks['es_asia_orb']['full_dd_r']}R DD`, last 2y `{picks['es_asia_orb']['last2_net_r']}R`, last 1y `{picks['es_asia_orb']['last1_net_r']}R`; warning: {_full_warning(picks['es_asia_orb'])}.
  - Best ES NY ORB hot-score branch: `{picks['es_ny_orb']['variant_id']}` -> full `{picks['es_ny_orb']['full_net_r']}R / {picks['es_ny_orb']['full_dd_r']}R DD`, last 2y `{picks['es_ny_orb']['last2_net_r']}R`, last 1y `{picks['es_ny_orb']['last1_net_r']}R`; warning: {_full_warning(picks['es_ny_orb'])}.
"""
    ES_LEARNINGS_PATH.write_text(ES_LEARNINGS_PATH.read_text().rstrip() + "\n" + es_note.strip() + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    legs = _active_alpha_v1_legs()
    symbols = sorted({leg.config.instrument.symbol for leg in legs})
    data_by_symbol = {symbol: _load_data(NQ if symbol == "NQ" else ES) for symbol in symbols}
    end_inclusive, end_exclusive = _available_end_exclusive(data_by_symbol)
    end_ts = pd.Timestamp(end_inclusive)
    windows = {
        "full": (FULL_START, end_inclusive),
        "last_2y": ((end_ts - pd.Timedelta(days=730)).date().isoformat(), end_inclusive),
        "last_1y": ((end_ts - pd.Timedelta(days=365)).date().isoformat(), end_inclusive),
    }

    h_orb_context = _read_h_orb_ablated_context()

    all_metric_rows: list[dict[str, Any]] = []
    all_score_rows: list[dict[str, Any]] = []
    all_manifest_rows: list[dict[str, Any]] = []
    all_annual_rows: list[dict[str, Any]] = []
    variant_results: dict[str, tuple[LegSpec, VariantSpec, list[TradeResult]]] = {}
    baseline_streams: dict[str, list[TradeResult]] = {}
    hot_streams: dict[str, list[TradeResult]] = {}

    for leg in legs:
        print(f"\n=== {leg.label} ===", flush=True)
        loaded = data_by_symbol[leg.config.instrument.symbol]
        baseline_variant = _baseline_variant(leg)
        baseline_result = _run_variants(
            loaded,
            [baseline_variant],
            start_date=FULL_START,
            end_date=end_exclusive,
        )
        baseline_trades = baseline_result[baseline_variant.config.name]
        baseline_streams[leg.key] = baseline_trades
        variant_results[f"{leg.key}::baseline"] = (leg, baseline_variant, baseline_trades)

        options_by_category = _options_for_leg(leg, baseline_trades)
        oat_variants = _oat_variants(leg, options_by_category)
        oat_results = _run_variants(
            loaded,
            oat_variants,
            start_date=FULL_START,
            end_date=end_exclusive,
        )

        stage_variants = [baseline_variant, *oat_variants]
        stage_results = {baseline_variant.config.name: baseline_trades, **oat_results}
        stage_metric_rows: list[dict[str, Any]] = []
        for variant in stage_variants:
            trades = stage_results[variant.config.name]
            variant_results[f"{leg.key}::{variant.variant_id}"] = (leg, variant, trades)
            all_manifest_rows.append(_manifest_row(variant))
            for window, (start, end) in windows.items():
                row = _metric_row(leg=leg, variant=variant, trades=trades, window=window, start=start, end_inclusive=end)
                stage_metric_rows.append(row)
                all_metric_rows.append(row)

        stage_scores = _add_deltas(_score_rows(stage_metric_rows))
        oat_score_rows = [row for row in stage_scores if row["stage"] == "oat"]
        selected_options = _best_options_from_oat(
            leg=leg,
            options_by_category=options_by_category,
            oat_score_rows=oat_score_rows,
            keep_by_category=_combo_categories(leg.kind),
        )

        print("    combo seed options:", {k: [o.option_id for o in v] for k, v in selected_options.items()}, flush=True)
        combo_variants = _combo_variants(leg, selected_options)
        combo_results = _run_variants(
            loaded,
            combo_variants,
            start_date=FULL_START,
            end_date=end_exclusive,
        )

        combo_metric_rows: list[dict[str, Any]] = []
        for variant in combo_variants:
            trades = combo_results[variant.config.name]
            variant_results[f"{leg.key}::{variant.variant_id}"] = (leg, variant, trades)
            all_manifest_rows.append(_manifest_row(variant))
            for window, (start, end) in windows.items():
                row = _metric_row(leg=leg, variant=variant, trades=trades, window=window, start=start, end_inclusive=end)
                combo_metric_rows.append(row)
                all_metric_rows.append(row)

        leg_metric_rows = stage_metric_rows + combo_metric_rows
        leg_scores = _add_deltas(_score_rows(leg_metric_rows))
        all_score_rows.extend(leg_scores)
        best_hot = _top_for_leg(leg_scores, leg.key, "hot_score", limit=1)[0]
        best_key = f"{leg.key}::{best_hot['variant_id']}"
        hot_streams[leg.key] = variant_results[best_key][2]
        print(
            f"    best hot-score: {best_hot['variant_id']} | "
            f"last1 {best_hot['last1_net_r']}R | last2 {best_hot['last2_net_r']}R | "
            f"full {best_hot['full_net_r']}R",
            flush=True,
        )

    all_score_rows = _add_deltas(all_score_rows)
    all_annual_rows = _annual_rows(variant_results)
    portfolio_rows = [
        _portfolio_row("baseline_current_alpha_v1", baseline_streams, windows),
        _portfolio_row("replace_each_leg_with_best_hot_score", hot_streams, windows),
    ]

    metrics_df = pd.DataFrame(all_metric_rows)
    scores_df = pd.DataFrame(all_score_rows)
    manifest_df = pd.DataFrame(all_manifest_rows)
    annual_df = pd.DataFrame(all_annual_rows)
    portfolio_df = pd.DataFrame(portfolio_rows)

    metrics_df.to_csv(RESULT_DIR / "metrics_by_window.csv", index=False)
    scores_df.to_csv(RESULT_DIR / "variant_scores.csv", index=False)
    manifest_df.to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    annual_df.to_csv(RESULT_DIR / "annual_r.csv", index=False)
    portfolio_df.to_csv(RESULT_DIR / "portfolio_proxy.csv", index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "full_start": FULL_START,
        "end_inclusive": end_inclusive,
        "end_exclusive": end_exclusive,
        "windows": windows,
        "hot_score_formula": HOT_SCORE_FORMULA,
        "h_orb_ablated_context": h_orb_context,
        "best_hot_score_by_leg": {
            leg.key: _top_for_leg(all_score_rows, leg.key, "hot_score", limit=1)[0]
            for leg in legs
        },
        "best_last1_by_leg": {
            leg.key: _top_for_leg(all_score_rows, leg.key, "last1_net_r", limit=1)[0]
            for leg in legs
        },
        "portfolio_proxy": portfolio_rows,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True))

    _write_report(
        end_inclusive=end_inclusive,
        windows=windows,
        score_rows=all_score_rows,
        portfolio_rows=portfolio_rows,
        h_orb_context=h_orb_context,
    )
    _write_learnings(all_score_rows, portfolio_rows, end_inclusive)

    print("\nDONE", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Results: {RESULT_DIR}", flush=True)


if __name__ == "__main__":
    main()
