#!/usr/bin/env python3
"""One-year hot-regime strategy workflow across NQ/ES/GC ORB and LSI legs.

This deliberately departs from the normal robust workflow. The objective is to
make the last available year look as strong as possible, while still rejecting
obvious one-cell cliffs by checking the local parameter surface around winners.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from itertools import product
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config  # noqa: E402
from orb_backtest.analysis.gates import apply_dow_filter  # noqa: E402
from orb_backtest.analysis.regime_research import build_extended_regime_calendar, _regime_lookup  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, GC, NQ, Instrument  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "hot_one_year_strategy_workflow_20260503"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "HOT_ONE_YEAR_STRATEGY_WORKFLOW_20260503.md"
NQ_LEARNINGS_PATH = ROOT / "learnings" / "asset" / "NQ.md"
ES_LEARNINGS_PATH = ROOT / "learnings" / "asset" / "ES.md"
GC_LEARNINGS_PATH = ROOT / "learnings" / "asset" / "GC.md"

# Warmup gives ATR/pivot calculations room while still keeping the last-year
# sweep much lighter than a full-history pass.
LOAD_START = "2025-01-01"
MIN_FILLS_BY_KIND = {"orb": 30, "lsi": 8, "htf_lsi": 12}
WORKERS_BY_SYMBOL = {"NQ": 4, "ES": 4, "GC": 1}

DOW_LABELS = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
REGIME_GATES: dict[str, tuple[str, ...]] = {
    "gate_none": (),
    "gate_skip_medium_vol": ("bull_medium_vol", "sideways_medium_vol"),
    "gate_skip_bear_high_vol": ("bear_high_vol",),
    "gate_skip_high_vol": ("bull_high_vol", "bear_high_vol", "sideways_high_vol"),
}


@dataclass(frozen=True)
class LoadedData:
    symbol: str
    timeframe: str
    instrument: Instrument
    df_base: pd.DataFrame
    df_1m: pd.DataFrame | None
    df_1s: pd.DataFrame | None
    signal_df_1m: pd.DataFrame | None
    regime_lookup: dict[str, str]


@dataclass(frozen=True)
class LegSpec:
    key: str
    label: str
    symbol: str
    kind: str
    timeframe: str
    base_config: StrategyConfig
    baseline_note: str


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


def _round(value: Any, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return round(val, digits)


def _pct(value: Any) -> float | None:
    val = _round(value, 6)
    return None if val is None else round(float(val) * 100.0, 2)


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
    return "\n".join([header, sep, *body])


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return out.dropna(subset=["open", "high", "low", "close"]).astype(float)


def _load_raw(symbol: str, end_date: str | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    filename = f"{symbol}_5m.parquet"
    try:
        df_5m = load_5m_data(filename, start=LOAD_START, end=end_date)
    except FileNotFoundError:
        df_1s = load_1s_for_5m(filename, start=LOAD_START, end=end_date)
        df_5m = _resample_ohlcv(df_1s, "5min")
    else:
        try:
            df_1s = load_1s_for_5m(filename, start=LOAD_START, end=end_date)
        except FileNotFoundError:
            df_1s = None

    try:
        df_1m = load_1m_for_5m(filename, start=LOAD_START, end=end_date)
    except FileNotFoundError:
        if df_1s is None:
            df_1s = load_1s_for_5m(filename, start=LOAD_START, end=end_date)
        df_1m = _resample_ohlcv(df_1s, "1min")

    return df_5m, df_1m, df_1s


def _instrument(symbol: str) -> Instrument:
    return {"NQ": NQ, "ES": ES, "GC": GC}[symbol]


def _load_data(symbol: str, timeframe: str, end_date: str | None, regime_holdout_start: str) -> LoadedData:
    df_5m, df_1m, df_1s = _load_raw(symbol, end_date)
    if timeframe == "5m":
        df_base = df_5m
    elif timeframe == "3m":
        df_base = _resample_ohlcv(df_1m, "3min")
    elif timeframe == "2m":
        df_base = _resample_ohlcv(df_1m, "2min")
    elif timeframe == "1m":
        df_base = df_1m
    else:
        raise ValueError(f"Unsupported timeframe {timeframe!r}")

    try:
        regime_calendar = build_extended_regime_calendar(
            df_5m,
            start_date=LOAD_START,
            end_date=end_date,
            holdout_start=regime_holdout_start,
        )
        regime_lookup = _regime_lookup(regime_calendar, "combined_regime")
    except Exception as exc:
        print(f"    regime calendar unavailable for {symbol}: {exc}", flush=True)
        regime_lookup = {}

    return LoadedData(
        symbol=symbol,
        timeframe=timeframe,
        instrument=_instrument(symbol),
        df_base=df_base,
        df_1m=df_1m,
        df_1s=df_1s,
        signal_df_1m=df_1m,
        regime_lookup=regime_lookup,
    )


def _available_end_inclusive(symbols: list[str]) -> str:
    max_dates = []
    for symbol in symbols:
        try:
            df = load_5m_data(f"{symbol}_5m.parquet", start="2026-01-01")
        except FileNotFoundError:
            df = load_1s_for_5m(f"{symbol}_5m.parquet", start="2026-01-01")
        max_dates.append(df.index.max().normalize())
    return min(max_dates).date().isoformat()


def _orb_session(name: str, orb_start: str, orb_minutes: int, **kwargs: Any) -> SessionConfig:
    hour, minute = map(int, orb_start.split(":"))
    total = hour * 60 + minute + orb_minutes
    total %= 24 * 60
    orb_end = f"{total // 60:02d}:{total % 60:02d}"
    return SessionConfig(name=name, orb_start=orb_start, orb_end=orb_end, entry_start=orb_end, **kwargs)


def _base_legs() -> list[LegSpec]:
    nq_ny_orb = StrategyConfig(
        sessions=(
            _orb_session(
                "NY", "09:30", 20,
                entry_end="12:00", flat_start="15:30", flat_end="16:00",
                stop_atr_pct=7.0, min_gap_atr_pct=2.5,
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
        name="nq_ny_orb_base_r11",
    )
    nq_asia_orb = StrategyConfig(
        sessions=(
            _orb_session(
                "Asia", "20:00", 15,
                entry_end="22:30", flat_start="04:00", flat_end="07:00",
                stop_atr_pct=4.0, min_gap_atr_pct=0.9,
            ),
        ),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.6,
        atr_length=5,
        impulse_close_filter=True,
        excluded_days=(1,),
        name="nq_asia_orb_base_r9",
    )
    nq_ny_lsi = build_current_nq_ny_htf_lsi_lag24_config(name="nq_ny_lsi_base_htf_lag24")

    es_ny_orb = StrategyConfig(
        sessions=(
            _orb_session(
                "NY", "09:30", 15,
                entry_end="13:00", flat_start="15:50", flat_end="16:00",
                stop_atr_pct=5.0, min_gap_atr_pct=0.25,
                min_stop_points=3.0, min_tp1_points=3.0,
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
        name="es_ny_orb_base_final",
    )
    es_asia_orb = StrategyConfig(
        sessions=(
            _orb_session(
                "Asia", "20:00", 15,
                entry_end="03:00", flat_start="07:00", flat_end="07:00",
                stop_orb_pct=125.0, min_gap_atr_pct=0.5,
                min_stop_points=3.0, min_tp1_points=3.0,
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
        name="es_asia_orb_base_final",
    )
    es_ny_lsi = StrategyConfig(
        sessions=(
            SessionConfig(
                name="NY",
                rth_start="08:30",
                sweep_start="08:30",
                sweep_end="14:00",
                entry_start="08:30",
                entry_end="14:00",
                flat_start="15:50",
                flat_end="16:00",
                min_gap_atr_pct=3.0,
                min_stop_points=3.0,
                min_tp1_points=3.0,
            ),
        ),
        instrument=ES,
        strategy="htf_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.5,
        tp1_ratio=0.5,
        atr_length=14,
        lsi_entry_mode="fvg_limit",
        lsi_stop_mode="absolute",
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=3,
        htf_level_tf_minutes=90,
        htf_n_left=3,
        htf_trade_max_per_session=2,
        max_fvg_to_inversion_bars=0,
        name="es_ny_lsi_base_htf_balanced",
    )

    gc_ny_orb = StrategyConfig(
        sessions=(
            _orb_session(
                "NY", "09:30", 8,
                entry_end="12:00", flat_start="13:30", flat_end="16:00",
                stop_atr_pct=4.5, min_gap_atr_pct=3.0,
            ),
        ),
        instrument=GC,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=9.0,
        tp1_ratio=0.35,
        atr_length=7,
        impulse_close_filter=True,
        excluded_days=(4,),
        name="gc_ny_orb_base_r3",
    )
    gc_asia_orb = StrategyConfig(
        sessions=(
            _orb_session(
                "Asia", "20:00", 30,
                entry_end="23:15", flat_start="04:00", flat_end="07:00",
                stop_orb_pct=25.0, min_gap_atr_pct=1.0,
            ),
        ),
        instrument=GC,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=2.5,
        tp1_ratio=0.6,
        atr_length=14,
        name="gc_asia_orb_base_asia1",
    )
    gc_ny_lsi = StrategyConfig(
        sessions=(
            SessionConfig(
                name="NY",
                rth_start="09:30",
                sweep_start="09:35",
                sweep_end="10:30",
                entry_start="09:35",
                entry_end="10:30",
                flat_start="15:00",
                flat_end="16:00",
                min_gap_atr_pct=5.0,
            ),
        ),
        instrument=GC,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=9.0,
        tp1_ratio=0.4,
        atr_length=7,
        lsi_entry_mode="fvg_limit",
        lsi_stop_mode="absolute",
        lsi_n_left=5,
        lsi_n_right=75,
        lsi_fvg_window_left=10,
        lsi_fvg_window_right=10,
        name="gc_ny_lsi_base_fvgl",
    )
    gc_asia_lsi = StrategyConfig(
        sessions=(
            SessionConfig(
                name="Asia",
                rth_start="20:00",
                sweep_start="20:00",
                sweep_end="23:15",
                entry_start="20:05",
                entry_end="23:15",
                flat_start="04:00",
                flat_end="07:00",
                min_gap_atr_pct=5.0,
            ),
        ),
        instrument=GC,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=9.0,
        tp1_ratio=0.4,
        atr_length=7,
        lsi_entry_mode="fvg_limit",
        lsi_stop_mode="absolute",
        lsi_n_left=5,
        lsi_n_right=36,
        lsi_fvg_window_left=10,
        lsi_fvg_window_right=10,
        name="gc_asia_lsi_base_ny_lsi_transplant",
    )

    return [
        LegSpec("nq_ny_orb", "NQ NY ORB", "NQ", "orb", "5m", nq_ny_orb, "NQ R11 NY continuation long"),
        LegSpec("nq_asia_orb", "NQ Asia ORB", "NQ", "orb", "5m", nq_asia_orb, "NQ R9 Asia restart final"),
        LegSpec("nq_ny_lsi", "NQ NY LSI", "NQ", "htf_lsi", "5m", nq_ny_lsi, "current ALPHA_V1 HTF-LSI lag24 operating row"),
        LegSpec("es_ny_orb", "ES NY ORB", "ES", "orb", "5m", es_ny_orb, "ES NY ORB final"),
        LegSpec("es_asia_orb", "ES Asia ORB", "ES", "orb", "5m", es_asia_orb, "ES Asia ORB final"),
        LegSpec("es_ny_lsi", "ES NY LSI", "ES", "htf_lsi", "3m", es_ny_lsi, "ES 3m HTF-LSI balanced restart branch"),
        LegSpec("gc_ny_orb", "GC NY ORB", "GC", "orb", "5m", gc_ny_orb, "GC NY R3 high-RR continuation"),
        LegSpec("gc_asia_orb", "GC Asia ORB", "GC", "orb", "5m", gc_asia_orb, "GC Asia-1 ORB continuation"),
        LegSpec("gc_ny_lsi", "GC NY LSI", "GC", "lsi", "5m", gc_ny_lsi, "GC NY fvg_limit LSI conditional GO"),
        LegSpec("gc_asia_lsi", "GC Asia LSI", "GC", "lsi", "5m", gc_asia_lsi, "GC NY LSI mechanics transplanted to Asia; no prior GC Asia LSI winner"),
    ]


def _session_replace(config: StrategyConfig, **updates: Any) -> StrategyConfig:
    return replace(config, sessions=(replace(config.sessions[0], **updates),))


def _variant_config(base: StrategyConfig, name: str, options: OptionSpec | list[OptionSpec]) -> StrategyConfig:
    opts = options if isinstance(options, list) else [options]
    direct: dict[str, Any] = {}
    session: dict[str, Any] = {}
    option_ids = []
    for option in opts:
        option_ids.append(option.option_id)
        if option.direct:
            direct.update(option.direct)
        if option.session:
            session.update(option.session)
    cfg = base
    if session:
        cfg = _session_replace(cfg, **session)
    if direct:
        cfg = replace(cfg, **direct)
    return replace(cfg, name=name, notes="one-year hot workflow: " + ",".join(option_ids))


def _cfg_payload(config: StrategyConfig) -> str:
    payload = asdict(config)
    payload.pop("name", None)
    payload.pop("notes", None)
    return json.dumps(_safe_json(payload), sort_keys=True, default=str)


def _dedupe_variants(variants: list[VariantSpec]) -> list[VariantSpec]:
    seen: set[str] = set()
    out: list[VariantSpec] = []
    for variant in variants:
        key = _cfg_payload(variant.config)
        if key in seen:
            continue
        seen.add(key)
        out.append(variant)
    return out


def _valid_rr_tp1(rr: float, tp1: float) -> bool:
    return rr >= 1.0 and rr * tp1 >= 1.0


def _rr_option(rr: float, tp1: float) -> OptionSpec:
    suffix = f"rr{str(rr).replace('.', 'p')}_tp{str(tp1).replace('.', 'p')}"
    return OptionSpec("rr_tp1", suffix, f"rr={rr:g}, tp1={tp1:g}", direct={"rr": rr, "tp1_ratio": tp1})


def _dow_option(option_id: str, excluded: tuple[int, ...]) -> OptionSpec:
    if excluded:
        label = "exclude " + ",".join(DOW_LABELS[d] for d in excluded)
    else:
        label = "include all weekdays"
    return OptionSpec("dow", option_id, label, direct={"excluded_days": excluded})


def _time_to_minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _minutes_to_time(total: int) -> str:
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def _orb_minutes(session: SessionConfig) -> int:
    diff = _time_to_minutes(session.orb_end) - _time_to_minutes(session.orb_start)
    return diff if diff >= 0 else diff + 24 * 60


def _orb_window_option(orb_start: str, minutes: int) -> OptionSpec:
    orb_end = _minutes_to_time(_time_to_minutes(orb_start) + minutes)
    return OptionSpec(
        "orb_window",
        f"orb{minutes}m",
        f"ORB {minutes}m",
        session={"orb_end": orb_end, "entry_start": orb_end},
    )


def _stop_option(mode: str, value: float) -> OptionSpec:
    clean = str(value).replace(".", "p")
    if mode == "atr":
        return OptionSpec(
            "stop",
            f"stop_atr_{clean}",
            f"stop_atr_pct={value:g}",
            session={"stop_atr_pct": value, "stop_orb_pct": 0.0},
        )
    return OptionSpec(
        "stop",
        f"stop_orb_{clean}",
        f"stop_orb_pct={value:g}",
        session={"stop_orb_pct": value, "stop_atr_pct": 0.0},
    )


def _gap_option(mode: str, value: float) -> OptionSpec:
    clean = str(value).replace(".", "p")
    if mode == "atr":
        return OptionSpec(
            "gap",
            f"gap_atr_{clean}",
            f"min_gap_atr_pct={value:g}",
            session={"min_gap_atr_pct": value, "min_gap_orb_pct": 0.0},
        )
    return OptionSpec(
        "gap",
        f"gap_orb_{clean}",
        f"min_gap_orb_pct={value:g}",
        session={"min_gap_orb_pct": value, "min_gap_atr_pct": 0.0},
    )


def _unique_options(options: list[OptionSpec]) -> list[OptionSpec]:
    seen: set[str] = set()
    out = []
    for option in options:
        if option.option_id in seen:
            continue
        seen.add(option.option_id)
        out.append(option)
    return out


def _dow_options(base: StrategyConfig) -> list[OptionSpec]:
    baseline = tuple(base.excluded_days)
    options = [_dow_option("dow_baseline", baseline), _dow_option("dow_none", ())]
    options.extend(_dow_option(f"dow_ex{DOW_LABELS[day]}", (day,)) for day in range(5))
    return _unique_options(options)


def _orb_options(leg: LegSpec) -> dict[str, list[OptionSpec]]:
    base = leg.base_config
    session = base.sessions[0]
    orb_base = _orb_minutes(session)
    if session.name == "NY" and leg.symbol == "GC":
        orb_values = [5, 8, 10, 15, 20, 30]
    elif session.name == "NY":
        orb_values = sorted({10, 15, 20, 25, 30, orb_base})
    else:
        orb_values = sorted({10, 15, 20, 30, 45, 60, orb_base})

    if leg.symbol == "GC" and session.name == "NY":
        rr_tp = [(3.0, 0.4), (4.0, 0.3), (5.0, 0.25), (6.0, 0.2), (7.0, 0.2), (8.0, 0.2), (9.0, 0.35), (10.0, 0.2)]
        stop_atr = [3.0, 4.0, 4.5, 5.0, 6.0, 7.5]
        stop_orb = [25.0, 50.0, 75.0, 100.0]
        gaps_atr = [0.5, 1.0, 2.0, 3.0, 4.0, 5.0]
        atrs = [5, 7, 10, 14]
    elif leg.symbol == "GC":
        rr_tp = [(1.5, 0.7), (2.0, 0.5), (2.5, 0.6), (3.0, 0.4), (4.0, 0.3), (5.0, 0.25)]
        stop_atr = [5.0, 7.5, 10.0, 12.5, 15.0]
        stop_orb = [25.0, 50.0, 75.0, 100.0]
        gaps_atr = [0.0, 0.5, 1.0, 1.5, 2.0]
        atrs = [7, 10, 14, 20]
    elif leg.symbol == "NQ" and session.name == "Asia":
        rr_tp = [(2.0, 0.5), (2.5, 0.5), (3.0, 0.6), (4.0, 0.3), (5.0, 0.25), (6.0, 0.3), (7.0, 0.2), (8.0, 0.2)]
        stop_atr = [3.0, 4.0, 5.0, 6.0, 7.5]
        stop_orb = [50.0, 75.0, 100.0, 125.0]
        gaps_atr = [0.0, 0.5, 0.9, 1.5, 2.5, 3.0]
        atrs = [5, 7, 10, 14]
    elif leg.symbol == "NQ":
        rr_tp = [(2.0, 0.5), (3.0, 0.4), (3.5, 0.4), (4.0, 0.3), (5.0, 0.2), (6.0, 0.2), (7.0, 0.2)]
        stop_atr = [4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
        stop_orb = [25.0, 50.0, 75.0, 100.0]
        gaps_atr = [0.0, 1.0, 1.5, 2.0, 2.5, 3.0]
        atrs = [7, 10, 12, 14, 20]
    elif session.name == "Asia":
        rr_tp = [(1.5, 0.7), (1.75, 0.6), (2.0, 0.5), (2.5, 0.4), (3.0, 0.35), (4.0, 0.25)]
        stop_atr = [5.0, 7.5, 10.0, 12.0, 15.0]
        stop_orb = [75.0, 100.0, 125.0, 150.0]
        gaps_atr = [0.0, 0.25, 0.5, 0.75, 1.0]
        atrs = [7, 10, 14, 20]
    else:
        rr_tp = [(3.0, 0.35), (4.0, 0.25), (5.0, 0.2), (6.0, 0.2), (7.0, 0.2)]
        stop_atr = [3.0, 4.0, 5.0, 6.0, 7.0]
        stop_orb = [25.0, 50.0, 75.0, 100.0]
        gaps_atr = [0.0, 0.1, 0.25, 0.5, 0.75]
        atrs = [5, 7, 10, 14]

    entry_ends = {
        "NY": ["11:00", "12:00", "13:00", "14:00", "15:30"],
        "Asia": ["22:30", "23:15", "00:00", "03:00", "04:00", "06:00"],
    }[session.name]
    flat_starts = {
        "NY": ["13:30", "14:30", "15:30", "15:50"],
        "Asia": ["04:00", "06:00", "07:00"],
    }[session.name]

    return {
        "orb_window": [_orb_window_option(session.orb_start, value) for value in orb_values],
        "entry_end": [
            OptionSpec("entry_end", f"entry_{value.replace(':', '')}", f"entry_end={value}", session={"entry_end": value})
            for value in entry_ends
        ],
        "flat_start": [
            OptionSpec("flat_start", f"flat_{value.replace(':', '')}", f"flat_start={value}", session={"flat_start": value})
            for value in flat_starts
        ],
        "rr_tp1": [_rr_option(rr, tp1) for rr, tp1 in rr_tp if _valid_rr_tp1(rr, tp1)],
        "stop": [_stop_option("atr", value) for value in stop_atr] + [_stop_option("orb", value) for value in stop_orb],
        "gap": [_gap_option("atr", value) for value in gaps_atr] + [_gap_option("orb", value) for value in [0.0, 5.0, 10.0, 15.0]],
        "atr": [OptionSpec("atr", f"atr{value}", f"atr_length={value}", direct={"atr_length": value}) for value in atrs],
        "direction": [
            OptionSpec("direction", f"dir_{value}", f"direction={value}", direct={"direction_filter": value})
            for value in ("long", "short", "both")
        ],
        "dow": _dow_options(base),
        "icf": [
            OptionSpec("icf", "icf_off", "impulse close filter off", direct={"impulse_close_filter": False}),
            OptionSpec("icf", "icf_on", "impulse close filter on", direct={"impulse_close_filter": True}),
        ],
        "reentry": [
            OptionSpec("reentry", "cap1", "one trade/session", direct={"orb_trade_max_per_session": 1, "orb_reentry_policy": "any_reentry"}),
            OptionSpec("reentry", "cap2_any", "up to two trades", direct={"orb_trade_max_per_session": 2, "orb_reentry_policy": "any_reentry"}),
            OptionSpec("reentry", "cap2_nonpos", "second trade after <=0R", direct={"orb_trade_max_per_session": 2, "orb_reentry_policy": "after_nonpositive_first"}),
            OptionSpec("reentry", "uncapped_any", "uncapped non-overlap", direct={"orb_trade_max_per_session": 0, "orb_reentry_policy": "any_reentry"}),
        ],
        "fvg_selection": [
            OptionSpec("fvg_selection", "fvg_first", "first FVG", direct={"continuation_fvg_selection": "first"}),
            OptionSpec("fvg_selection", "fvg_extreme", "extreme/chasing FVG", direct={"continuation_fvg_selection": "extreme"}),
        ],
    }


def _lsi_options(leg: LegSpec) -> dict[str, list[OptionSpec]]:
    base = leg.base_config
    session = base.sessions[0]
    is_asia = session.name == "Asia"
    if leg.symbol == "GC":
        rr_tp = [(3.0, 0.4), (4.0, 0.3), (5.0, 0.25), (6.0, 0.2), (7.0, 0.2), (9.0, 0.4), (10.0, 0.2)]
        gaps = [2.0, 3.0, 4.0, 5.0, 6.0]
        atrs = [5, 7, 10, 14]
        lefts = [3, 5, 8, 10, 12]
        rights = [24, 36, 48, 60, 75, 90] if is_asia else [45, 60, 75, 90, 120]
    else:
        rr_tp = [(1.5, 0.7), (2.0, 0.5), (2.5, 0.5), (3.0, 0.3), (3.5, 0.3), (4.5, 0.2)]
        gaps = [3.0, 4.0, 5.0, 6.0]
        atrs = [7, 10, 14]
        lefts = [5, 8, 10, 12, 20]
        rights = [45, 60, 65, 78, 90, 120]

    entry_ends = ["10:15", "10:30", "11:00", "13:00", "15:30"] if not is_asia else ["22:30", "23:15", "00:00", "03:00"]
    flat_starts = ["13:30", "14:30", "15:00", "15:50"] if not is_asia else ["00:00", "03:00", "04:00", "06:00"]
    fvg_windows = [(7, 3), (10, 5), (10, 10), (20, 3), (20, 5), (30, 5)]

    return {
        "entry_end": [
            OptionSpec("entry_end", f"entry_{value.replace(':', '')}", f"entry_end={value}", session={"entry_end": value, "sweep_end": value})
            for value in entry_ends
        ],
        "flat_start": [
            OptionSpec("flat_start", f"flat_{value.replace(':', '')}", f"flat_start={value}", session={"flat_start": value})
            for value in flat_starts
        ],
        "rr_tp1": [_rr_option(rr, tp1) for rr, tp1 in rr_tp if _valid_rr_tp1(rr, tp1)],
        "gap": [
            OptionSpec("gap", f"gap{str(value).replace('.', 'p')}", f"min_gap_atr_pct={value:g}", session={"min_gap_atr_pct": value})
            for value in gaps
        ],
        "atr": [OptionSpec("atr", f"atr{value}", f"atr_length={value}", direct={"atr_length": value}) for value in atrs],
        "n_left": [OptionSpec("n_left", f"nL{value}", f"lsi_n_left={value}", direct={"lsi_n_left": value}) for value in lefts],
        "n_right": [OptionSpec("n_right", f"nR{value}", f"lsi_n_right={value}", direct={"lsi_n_right": value}) for value in rights],
        "fvg_window": [
            OptionSpec(
                "fvg_window",
                f"fvgL{left}_R{right}",
                f"FVG {left}/{right}",
                direct={"lsi_fvg_window_left": left, "lsi_fvg_window_right": right},
            )
            for left, right in fvg_windows
        ],
        "direction": [
            OptionSpec("direction", f"dir_{value}", f"direction={value}", direct={"direction_filter": value})
            for value in ("long", "short", "both")
        ],
        "entry_mode": [
            OptionSpec("entry_mode", "mode_fvg_limit", "FVG limit entry", direct={"lsi_entry_mode": "fvg_limit"}),
            OptionSpec("entry_mode", "mode_close", "close entry", direct={"lsi_entry_mode": "close"}),
        ],
        "dow": _dow_options(base),
    }


def _htf_lsi_options(leg: LegSpec) -> dict[str, list[OptionSpec]]:
    base = leg.base_config
    session = base.sessions[0]
    if leg.symbol == "NQ":
        windows = [("08:30", "12:30"), ("08:30", "13:30"), ("08:30", "14:30"), ("09:30", "13:30")]
        rr_tp = [(2.5, 0.4), (3.0, 0.4), (3.5, 0.4), (4.0, 0.3), (5.0, 0.2)]
        gaps = [1.0, 2.0, 2.5, 3.0, 4.0]
        fvg_windows = [(10, 2), (20, 2), (20, 3), (20, 5), (30, 2)]
        max_inv = [0, 12, 24, 36, 48]
        htf_tfs = [60]
    else:
        windows = [("08:30", "13:00"), ("08:30", "14:00"), ("08:30", "15:00")]
        rr_tp = [(2.0, 0.5), (2.5, 0.5), (3.0, 0.6), (3.5, 0.4), (4.0, 0.3)]
        gaps = [2.0, 2.5, 3.0, 4.0]
        fvg_windows = [(20, 3), (20, 5), (33, 3), (33, 5), (60, 9)]
        max_inv = [0, 16, 24, 36]
        htf_tfs = [60, 90]

    return {
        "entry_window": [
            OptionSpec(
                "entry_window",
                f"window_{start.replace(':', '')}_{end.replace(':', '')}",
                f"{start}-{end}",
                session={"entry_start": start, "entry_end": end, "sweep_start": start, "sweep_end": end},
            )
            for start, end in windows
        ],
        "rr_tp1": [_rr_option(rr, tp1) for rr, tp1 in rr_tp if _valid_rr_tp1(rr, tp1)],
        "gap": [
            OptionSpec("gap", f"gap{str(value).replace('.', 'p')}", f"min_gap_atr_pct={value:g}", session={"min_gap_atr_pct": value})
            for value in gaps
        ],
        "atr": [OptionSpec("atr", f"atr{value}", f"atr_length={value}", direct={"atr_length": value}) for value in [10, 14, 20]],
        "fvg_window": [
            OptionSpec(
                "fvg_window",
                f"fvgL{left}_R{right}",
                f"FVG {left}/{right}",
                direct={"lsi_fvg_window_left": left, "lsi_fvg_window_right": right},
            )
            for left, right in fvg_windows
        ],
        "max_inv": [
            OptionSpec("max_inv", f"lag{value}", f"max_fvg_to_inversion_bars={value}", direct={"max_fvg_to_inversion_bars": value})
            for value in max_inv
        ],
        "trade_cap": [
            OptionSpec("trade_cap", f"cap{value}", f"htf_trade_max_per_session={value}", direct={"htf_trade_max_per_session": value})
            for value in [1, 2, 3, 0]
        ],
        "htf_left": [
            OptionSpec("htf_left", f"htfN{value}", f"htf_n_left={value}", direct={"htf_n_left": value})
            for value in [2, 3, 4, 5]
        ],
        "htf_tf": [
            OptionSpec("htf_tf", f"htf{value}", f"htf_level_tf_minutes={value}", direct={"htf_level_tf_minutes": value})
            for value in htf_tfs
        ],
        "direction": [
            OptionSpec("direction", f"dir_{value}", f"direction={value}", direct={"direction_filter": value})
            for value in ("long", "both")
        ],
        "entry_mode": [
            OptionSpec("entry_mode", "mode_fvg_limit", "FVG limit entry", direct={"lsi_entry_mode": "fvg_limit"}),
            OptionSpec("entry_mode", "mode_close", "close entry", direct={"lsi_entry_mode": "close"}),
        ],
        "dow": _dow_options(base),
    }


def _options_for_leg(leg: LegSpec) -> dict[str, list[OptionSpec]]:
    if leg.kind == "orb":
        return _orb_options(leg)
    if leg.kind == "htf_lsi":
        return _htf_lsi_options(leg)
    return _lsi_options(leg)


def _baseline_variant(leg: LegSpec) -> VariantSpec:
    return VariantSpec(
        leg.key,
        "baseline",
        "baseline",
        "baseline",
        leg.baseline_note,
        ("baseline",),
        replace(leg.base_config, name=f"{leg.key}__baseline"),
    )


def _oat_variants(leg: LegSpec, options_by_category: dict[str, list[OptionSpec]]) -> list[VariantSpec]:
    variants: list[VariantSpec] = []
    for category, options in options_by_category.items():
        for option in options:
            name = f"{leg.key}__oat__{option.option_id}"[:240]
            try:
                config = _variant_config(leg.base_config, name, option)
            except ValueError as exc:
                print(f"    skip invalid OAT {name}: {exc}", flush=True)
                continue
            variants.append(
                VariantSpec(
                    leg.key,
                    f"oat__{option.option_id}",
                    "oat",
                    option.category,
                    option.label,
                    (option.option_id,),
                    config,
                )
            )
    return _dedupe_variants(variants)


def _best_options_from_oat(
    leg: LegSpec,
    options_by_category: dict[str, list[OptionSpec]],
    oat_rows: list[dict[str, Any]],
    keep: int = 2,
) -> dict[str, list[OptionSpec]]:
    option_lookup = {option.option_id: option for options in options_by_category.values() for option in options}
    baseline_payload = _cfg_payload(leg.base_config)
    selected: dict[str, list[OptionSpec]] = {}
    for category, options in options_by_category.items():
        picked: list[OptionSpec] = []
        for option in options:
            try:
                if _cfg_payload(_variant_config(leg.base_config, "tmp", option)) == baseline_payload:
                    picked.append(option)
                    break
            except ValueError:
                continue
        rows = [row for row in oat_rows if row["category"] == category]
        rows.sort(key=lambda row: (float(row["last1_calmar"] or -999), float(row["last1_net_r"] or -999)), reverse=True)
        for row in rows:
            option = option_lookup.get(str(row["primary_option"]))
            if option is None or option in picked:
                continue
            picked.append(option)
            if len(picked) >= keep:
                break
        if not picked:
            picked = options[:keep]
        selected[category] = picked[:keep]
    return selected


def _combo_variants(leg: LegSpec, selected_options: dict[str, list[OptionSpec]], cap: int = 6000) -> list[VariantSpec]:
    categories = list(selected_options)
    variants: list[VariantSpec] = []
    for combo in product(*(selected_options[category] for category in categories)):
        option_ids = tuple(option.option_id for option in combo)
        suffix = "__".join(option_ids)
        name = f"{leg.key}__combo__{suffix}"[:240]
        try:
            config = _variant_config(leg.base_config, name, list(combo))
        except ValueError as exc:
            print(f"    skip invalid combo {name}: {exc}", flush=True)
            continue
        variants.append(
            VariantSpec(
                leg.key,
                f"combo__{suffix}",
                "combo",
                "combo",
                ", ".join(option.label for option in combo),
                option_ids,
                config,
            )
        )
    variants = _dedupe_variants(variants)
    if len(variants) > cap:
        idx = np.linspace(0, len(variants) - 1, num=cap, dtype=int)
        variants = [variants[int(i)] for i in idx]
    return variants


def _filled(trades: list[TradeResult]) -> list[TradeResult]:
    return [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]


def _slice(trades: list[TradeResult], start: str, end_inclusive: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end_inclusive]


def _apply_regime_gate(trades: list[TradeResult], lookup: dict[str, str], gate_id: str) -> list[TradeResult]:
    avoid = set(REGIME_GATES[gate_id])
    if not avoid or not lookup:
        return trades
    return [trade for trade in trades if trade.exit_type == EXIT_NO_FILL or lookup.get(trade.date) not in avoid]


def _run_variants(
    leg: LegSpec,
    loaded: LoadedData,
    variants: list[VariantSpec],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    if not variants:
        return {}
    configs = [variant.config for variant in variants]
    workers = min(WORKERS_BY_SYMBOL[leg.symbol], max(1, len(configs)))
    print(f"    running {len(configs)} configs with {workers} worker(s)", flush=True)
    results = run_sweep(
        loaded.df_base,
        configs,
        n_workers=workers,
        start_date=start_date,
        end_date=end_date,
        df_1m=loaded.df_1m,
        df_1s=loaded.df_1s,
        signal_df_1m=loaded.signal_df_1m,
        progress_fn=lambda done, total: print(f"      {done}/{total}", flush=True) if done % 1000 == 0 or done == total else None,
    )
    out: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        out[config.name] = sorted(trades, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))
    return out


def _metrics_for(trades: list[TradeResult], start: str, end_inclusive: str) -> dict[str, Any]:
    return compute_metrics(_slice(trades, start, end_inclusive))


def _score_metric_row(
    leg: LegSpec,
    variant: VariantSpec,
    trades: list[TradeResult],
    *,
    gate_id: str,
    period_start: str,
    period_end: str,
    cal_2025_start: str,
    cal_2025_end: str,
) -> dict[str, Any]:
    last1 = _metrics_for(trades, period_start, period_end)
    year2025 = _metrics_for(trades, cal_2025_start, cal_2025_end)
    full_loaded = compute_metrics(trades)
    r_by_year = full_loaded.get("r_by_year") or {}
    return {
        "leg": leg.key,
        "leg_label": leg.label,
        "symbol": leg.symbol,
        "kind": leg.kind,
        "timeframe": leg.timeframe,
        "variant_id": variant.variant_id,
        "stage": variant.stage,
        "category": variant.category,
        "label": variant.label,
        "option_ids": "|".join(variant.option_ids),
        "primary_option": variant.option_ids[0] if variant.option_ids else "",
        "gate": gate_id,
        "last1_fills": int(last1["total_trades"]),
        "last1_signals": int(last1["total_signals"]),
        "last1_net_r": _round(last1["total_r"], 2),
        "last1_wr_pct": _pct(last1["win_rate"]),
        "last1_pf": _round(last1["profit_factor"], 3),
        "last1_avg_r": _round(last1["avg_r"], 4),
        "last1_sharpe": _round(last1["sharpe_ratio"], 3),
        "last1_dd_r": _round(last1["max_drawdown_r"], 2),
        "last1_calmar": _round(last1["calmar_ratio"], 3),
        "y2025_fills": int(year2025["total_trades"]),
        "y2025_net_r": _round(year2025["total_r"], 2),
        "y2025_pf": _round(year2025["profit_factor"], 3),
        "y2025_dd_r": _round(year2025["max_drawdown_r"], 2),
        "y2025_calmar": _round(year2025["calmar_ratio"], 3),
        "loaded_fills": int(full_loaded["total_trades"]),
        "loaded_net_r": _round(full_loaded["total_r"], 2),
        "loaded_dd_r": _round(full_loaded["max_drawdown_r"], 2),
        "loaded_calmar": _round(full_loaded["calmar_ratio"], 3),
        "loaded_negative_years": int(sum(1 for value in r_by_year.values() if value < 0)),
        "eligible_min_fills": int(last1["total_trades"]) >= MIN_FILLS_BY_KIND[leg.kind],
    }


def _manifest_row(leg: LegSpec, variant: VariantSpec) -> dict[str, Any]:
    cfg = variant.config
    session = cfg.sessions[0]
    return {
        "leg": leg.key,
        "variant_id": variant.variant_id,
        "stage": variant.stage,
        "option_ids": "|".join(variant.option_ids),
        "strategy": cfg.strategy,
        "timeframe": leg.timeframe,
        "session": session.name,
        "orb_start": session.orb_start,
        "orb_end": session.orb_end,
        "entry_start": session.entry_start,
        "entry_end": session.entry_end,
        "flat_start": session.flat_start,
        "rr": cfg.rr,
        "tp1_ratio": cfg.tp1_ratio,
        "atr_length": cfg.atr_length,
        "direction_filter": cfg.direction_filter,
        "excluded_days": ",".join(str(day) for day in cfg.excluded_days),
        "stop_atr_pct": session.stop_atr_pct,
        "stop_orb_pct": session.stop_orb_pct,
        "min_gap_atr_pct": session.min_gap_atr_pct,
        "min_gap_orb_pct": session.min_gap_orb_pct,
        "impulse_close_filter": cfg.impulse_close_filter,
        "orb_trade_max_per_session": cfg.orb_trade_max_per_session,
        "orb_reentry_policy": cfg.orb_reentry_policy,
        "continuation_fvg_selection": cfg.continuation_fvg_selection,
        "lsi_entry_mode": cfg.lsi_entry_mode,
        "lsi_n_left": cfg.lsi_n_left,
        "lsi_n_right": cfg.lsi_n_right,
        "lsi_fvg_window_left": cfg.lsi_fvg_window_left,
        "lsi_fvg_window_right": cfg.lsi_fvg_window_right,
        "htf_level_tf_minutes": cfg.htf_level_tf_minutes,
        "htf_n_left": cfg.htf_n_left,
        "htf_trade_max_per_session": cfg.htf_trade_max_per_session,
        "max_fvg_to_inversion_bars": cfg.max_fvg_to_inversion_bars,
    }


def _add_baseline_deltas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = {row["leg"]: row for row in rows if row["variant_id"] == "baseline" and row["gate"] == "gate_none"}
    out = []
    for row in rows:
        base = baseline[row["leg"]]
        out.append(
            {
                **row,
                "delta_last1_net_r": _round(float(row["last1_net_r"] or 0.0) - float(base["last1_net_r"] or 0.0), 2),
                "delta_last1_calmar": _round(float(row["last1_calmar"] or 0.0) - float(base["last1_calmar"] or 0.0), 3),
                "delta_last1_dd_r": _round(float(row["last1_dd_r"] or 0.0) - float(base["last1_dd_r"] or 0.0), 2),
            }
        )
    return out


def _add_plateau_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_leg_gate: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["stage"] == "combo":
            by_leg_gate[(row["leg"], row["gate"])].append(row)

    stats: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (leg, gate), group in by_leg_gate.items():
        vectors = {row["variant_id"]: tuple(str(row["option_ids"]).split("|")) for row in group}
        for row in group:
            candidate = vectors[row["variant_id"]]
            candidate_calmar = float(row["last1_calmar"] or 0.0)
            neighbor_values = []
            if candidate_calmar > 0:
                for other in group:
                    if other["variant_id"] == row["variant_id"]:
                        continue
                    other_vec = vectors[other["variant_id"]]
                    if len(other_vec) != len(candidate):
                        continue
                    hamming = sum(a != b for a, b in zip(candidate, other_vec))
                    if hamming == 1:
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
                status = "curve"
            elif len(neighbor_values) >= 2 and ratio >= 0.45 and ge60 >= 2:
                status = "soft_curve"
            else:
                status = "cliff"
            stats[(leg, gate, row["variant_id"])] = {
                "neighbor_count": len(neighbor_values),
                "neighbor_median_calmar": _round(median_neighbor, 3),
                "neighbor_ge80_count": ge80,
                "neighbor_ge60_count": ge60,
                "plateau_ratio": _round(ratio, 3),
                "surface": status,
            }

    out = []
    for row in rows:
        row_stats = stats.get(
            (row["leg"], row["gate"], row["variant_id"]),
            {
                "neighbor_count": 0,
                "neighbor_median_calmar": None,
                "neighbor_ge80_count": 0,
                "neighbor_ge60_count": 0,
                "plateau_ratio": None,
                "surface": "n/a",
            },
        )
        out.append({**row, **row_stats})
    return out


def _top_rows(
    rows: list[dict[str, Any]],
    leg_key: str,
    sort_key: str,
    *,
    require_curve: bool = False,
    limit: int = 5,
) -> list[dict[str, Any]]:
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
            float(row[sort_key] or -999),
            float(row["last1_net_r"] or -999),
            float(row["last1_pf"] or 0.0),
        ),
        reverse=True,
    )[:limit]


def _baseline_for_leg(rows: list[dict[str, Any]], leg_key: str) -> dict[str, Any]:
    return next(row for row in rows if row["leg"] == leg_key and row["variant_id"] == "baseline" and row["gate"] == "gate_none")


def _write_report(
    *,
    legs: list[LegSpec],
    period_start: str,
    period_end: str,
    loaded_start: str,
    rows: list[dict[str, Any]],
    selected_options: dict[str, dict[str, list[str]]],
) -> None:
    lines = [
        "# Hot One-Year Strategy Workflow",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Optimization window: `{period_start}` to `{period_end}`",
        f"- Loaded warmup window starts: `{loaded_start}`",
        "- Objective: maximize last-year Calmar while looking for Hunter-like recent R.",
        "- This intentionally skips Bailey-style deflation and holdout discipline.",
        "- Cliff control: selected winners should be `curve` or `soft_curve` by one-step local-neighbor checks.",
        "- `GC Asia LSI` has no prior promoted anchor; it uses validated GC NY LSI mechanics transplanted to Asia as the seed.",
        "",
        "## Baselines",
        "",
    ]

    baseline_rows = []
    for leg in legs:
        row = _baseline_for_leg(rows, leg.key)
        baseline_rows.append(
            {
                "leg": leg.key,
                "note": leg.baseline_note,
                "fills": row["last1_fills"],
                "net_r": row["last1_net_r"],
                "calmar": row["last1_calmar"],
                "pf": row["last1_pf"],
                "dd": row["last1_dd_r"],
                "y2025_r": row["y2025_net_r"],
            }
        )
    lines.append(_markdown_table(baseline_rows, ["leg", "note", "fills", "net_r", "calmar", "pf", "dd", "y2025_r"]))
    lines.extend(["", "## Best Candidates", ""])

    summary_rows = []
    for leg in legs:
        best_curve = _top_rows(rows, leg.key, "last1_calmar", require_curve=True, limit=1)
        best_raw = _top_rows(rows, leg.key, "last1_calmar", require_curve=False, limit=1)
        best_net_curve = _top_rows(rows, leg.key, "last1_net_r", require_curve=True, limit=1)
        pick = best_curve[0] if best_curve else (best_raw[0] if best_raw else _baseline_for_leg(rows, leg.key))
        summary_rows.append(
            {
                "leg": leg.key,
                "pick": pick["variant_id"][:72],
                "gate": pick["gate"],
                "surface": pick["surface"],
                "fills": pick["last1_fills"],
                "net_r": pick["last1_net_r"],
                "calmar": pick["last1_calmar"],
                "pf": pick["last1_pf"],
                "dd": pick["last1_dd_r"],
                "y2025_r": pick["y2025_net_r"],
                "plateau": pick["plateau_ratio"],
            }
        )

        lines.extend([f"### {leg.label}", ""])
        local_rows = []
        for name, subset in (("baseline", [_baseline_for_leg(rows, leg.key)]), ("best_curve_calmar", best_curve), ("best_raw_calmar", best_raw), ("best_curve_net", best_net_curve)):
            if not subset:
                continue
            row = subset[0]
            local_rows.append(
                {
                    "pick": name,
                    "variant": row["variant_id"][:90],
                    "gate": row["gate"],
                    "surface": row["surface"],
                    "fills": row["last1_fills"],
                    "net_r": row["last1_net_r"],
                    "calmar": row["last1_calmar"],
                    "pf": row["last1_pf"],
                    "dd": row["last1_dd_r"],
                    "y2025_r": row["y2025_net_r"],
                    "plateau": row["plateau_ratio"],
                    "n_ge80": row["neighbor_ge80_count"],
                }
            )
        lines.append(_markdown_table(local_rows, ["pick", "variant", "gate", "surface", "fills", "net_r", "calmar", "pf", "dd", "y2025_r", "plateau", "n_ge80"]))
        lines.extend(["", "**Selected option seeds**", "", "```json", json.dumps(selected_options.get(leg.key, {}), indent=2, sort_keys=True), "```", ""])

    lines.extend(["## Cross-Leg Summary", "", _markdown_table(summary_rows, ["leg", "pick", "gate", "surface", "fills", "net_r", "calmar", "pf", "dd", "y2025_r", "plateau"]), ""])
    lines.extend([
        "## Read",
        "",
        "- Treat these as TESTING-only hot-regime candidates. They are optimized directly on the last year.",
        "- `curve` means the best row had nearby one-step neighbors retaining enough Calmar to look like a surface; `soft_curve` is usable but thinner.",
        "- `cliff` rows can still be interesting diagnostics, but they should not be treated as optimized params without another local sweep.",
        "- For comparison, the recent Hunter ORB branches remain the benchmark because they reached roughly triple-digit R in the hot window; the table above shows which candidates even enter that neighborhood.",
    ])
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def _write_learnings(legs: list[LegSpec], rows: list[dict[str, Any]], period_start: str, period_end: str) -> None:
    by_symbol: dict[str, list[LegSpec]] = defaultdict(list)
    for leg in legs:
        by_symbol[leg.symbol].append(leg)

    def bullet_lines(symbol_legs: list[LegSpec]) -> str:
        out = [
            f"- **Hot one-year strategy workflow** (2026-05-03): `backtesting/learnings/reports/HOT_ONE_YEAR_STRATEGY_WORKFLOW_20260503.md`",
            f"  - Window: `{period_start}` to `{period_end}`. TESTING-only, overfit-aware Calmar optimization; Bailey-style deflation intentionally skipped.",
        ]
        for leg in symbol_legs:
            best = _top_rows(rows, leg.key, "last1_calmar", require_curve=True, limit=1)
            if not best:
                best = _top_rows(rows, leg.key, "last1_calmar", require_curve=False, limit=1)
            row = best[0] if best else _baseline_for_leg(rows, leg.key)
            out.append(
                f"  - {leg.label}: `{row['variant_id']}` with `{row['gate']}` -> "
                f"{row['last1_fills']} fills, `{row['last1_net_r']}R`, Calmar `{row['last1_calmar']}`, "
                f"PF `{row['last1_pf']}`, DD `{row['last1_dd_r']}R`, surface `{row['surface']}`."
            )
        return "\n".join(out)

    for symbol, path in (("NQ", NQ_LEARNINGS_PATH), ("ES", ES_LEARNINGS_PATH), ("GC", GC_LEARNINGS_PATH)):
        note = bullet_lines(by_symbol[symbol])
        path.write_text(path.read_text().rstrip() + "\n" + note + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    legs = _base_legs()
    symbols = sorted({leg.symbol for leg in legs})
    end_inclusive = _available_end_inclusive(symbols)
    end_exclusive = (pd.Timestamp(end_inclusive) + pd.Timedelta(days=1)).date().isoformat()
    period_start = (pd.Timestamp(end_inclusive) - pd.Timedelta(days=365)).date().isoformat()
    cal_2025_start, cal_2025_end = "2025-01-01", "2025-12-31"

    print(f"Hot one-year workflow: {period_start} to {end_inclusive}", flush=True)
    data: dict[tuple[str, str], LoadedData] = {}
    for symbol, timeframe in sorted({(leg.symbol, leg.timeframe) for leg in legs}):
        print(f"Loading {symbol} {timeframe} data...", flush=True)
        data[(symbol, timeframe)] = _load_data(symbol, timeframe, end_exclusive, period_start)

    all_rows: list[dict[str, Any]] = []
    all_manifest: list[dict[str, Any]] = []
    selected_manifest: dict[str, dict[str, list[str]]] = {}

    for leg in legs:
        print(f"\n=== {leg.label} ===", flush=True)
        loaded = data[(leg.symbol, leg.timeframe)]
        options_by_category = _options_for_leg(leg)
        baseline = _baseline_variant(leg)

        baseline_trades = _run_variants(leg, loaded, [baseline], start_date=period_start, end_date=end_exclusive)[baseline.config.name]
        baseline_gated = _apply_regime_gate(baseline_trades, loaded.regime_lookup, "gate_none")
        all_rows.append(
            _score_metric_row(
                leg,
                baseline,
                baseline_gated,
                gate_id="gate_none",
                period_start=period_start,
                period_end=end_inclusive,
                cal_2025_start=cal_2025_start,
                cal_2025_end=cal_2025_end,
            )
        )
        all_manifest.append(_manifest_row(leg, baseline))

        oat_variants = _oat_variants(leg, options_by_category)
        oat_results = _run_variants(leg, loaded, oat_variants, start_date=period_start, end_date=end_exclusive)
        oat_rows: list[dict[str, Any]] = []
        for variant in oat_variants:
            trades = oat_results[variant.config.name]
            all_manifest.append(_manifest_row(leg, variant))
            for gate_id in REGIME_GATES:
                gated = _apply_regime_gate(trades, loaded.regime_lookup, gate_id)
                row = _score_metric_row(
                    leg,
                    variant,
                    gated,
                    gate_id=gate_id,
                    period_start=period_start,
                    period_end=end_inclusive,
                    cal_2025_start=cal_2025_start,
                    cal_2025_end=cal_2025_end,
                )
                all_rows.append(row)
                oat_rows.append(row)

        selected = _best_options_from_oat(leg, options_by_category, oat_rows, keep=2)
        selected_manifest[leg.key] = {category: [option.option_id for option in opts] for category, opts in selected.items()}
        combo_variants = _combo_variants(leg, selected)
        print(f"    selected options: {selected_manifest[leg.key]}", flush=True)
        print(f"    combo variants: {len(combo_variants)}", flush=True)

        combo_results = _run_variants(leg, loaded, combo_variants, start_date=period_start, end_date=end_exclusive)
        for variant in combo_variants:
            trades = combo_results[variant.config.name]
            all_manifest.append(_manifest_row(leg, variant))
            for gate_id in REGIME_GATES:
                gated = _apply_regime_gate(trades, loaded.regime_lookup, gate_id)
                all_rows.append(
                    _score_metric_row(
                        leg,
                        variant,
                        gated,
                        gate_id=gate_id,
                        period_start=period_start,
                        period_end=end_inclusive,
                        cal_2025_start=cal_2025_start,
                        cal_2025_end=cal_2025_end,
                    )
                )

    scored_rows = _add_plateau_stats(_add_baseline_deltas(all_rows))
    pd.DataFrame(scored_rows).to_csv(RESULT_DIR / "score_rows.csv", index=False)
    pd.DataFrame(all_manifest).drop_duplicates().to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    (RESULT_DIR / "selected_options.json").write_text(json.dumps(_safe_json(selected_manifest), indent=2, sort_keys=True))
    summary = {
        "run_slug": RUN_SLUG,
        "load_start": LOAD_START,
        "period_start": period_start,
        "period_end": end_inclusive,
        "end_exclusive": end_exclusive,
        "min_fills_by_kind": MIN_FILLS_BY_KIND,
        "regime_gates": REGIME_GATES,
        "best_curve_calmar_by_leg": {
            leg.key: (_top_rows(scored_rows, leg.key, "last1_calmar", require_curve=True, limit=1) or [None])[0]
            for leg in legs
        },
        "best_raw_calmar_by_leg": {
            leg.key: (_top_rows(scored_rows, leg.key, "last1_calmar", require_curve=False, limit=1) or [None])[0]
            for leg in legs
        },
        "best_curve_net_by_leg": {
            leg.key: (_top_rows(scored_rows, leg.key, "last1_net_r", require_curve=True, limit=1) or [None])[0]
            for leg in legs
        },
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True, default=str))

    _write_report(
        legs=legs,
        period_start=period_start,
        period_end=end_inclusive,
        loaded_start=LOAD_START,
        rows=scored_rows,
        selected_options=selected_manifest,
    )
    _write_learnings(legs, scored_rows, period_start, end_inclusive)
    print(f"\nDONE: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
