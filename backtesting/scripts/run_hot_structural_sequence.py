#!/usr/bin/env python3
"""Structural discovery pass around the hot one-year candidates.

This is intentionally not a Bailey-safe promotion workflow. It starts from the
current one-year hot candidates, then tests new context structure around them:
ORB size regimes, prior-day range/trend context, session context, calendar/news
filters, and Hunter-inspired signal-shape proxies.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import run_hot_one_year_squeeze as squeeze  # noqa: E402
import run_hot_one_year_strategy_workflow as prev  # noqa: E402
from orb_backtest.config import StrategyConfig  # noqa: E402
from orb_backtest.data.news_dates import CPI_SET, FOMC_SET, NFP_SET, PPI_SET  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.signals.daily_atr import compute_daily_atr  # noqa: E402


RUN_SLUG = "hot_structural_sequence_20260503"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "HOT_STRUCTURAL_SEQUENCE_20260503.md"
SQUEEZE_SUMMARY_PATH = ROOT / "data" / "results" / "hot_one_year_squeeze_20260503" / "summary.json"
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

STRUCTURAL_LOAD_START = "2024-01-01"
GATE_FAMILIES = (
    "orb_size",
    "prior_day",
    "session_context",
    "calendar_news",
    "hunter_proxy",
    "custom_day_type",
)


@dataclass(frozen=True)
class GateSpec:
    family: str
    gate_id: str
    label: str
    predicate: Callable[[dict[str, Any], TradeResult], bool]
    ordered_group: str = ""
    ordered_rank: int = 0


@dataclass(frozen=True)
class HotLeg:
    leg: prev.LegSpec
    row: dict[str, Any]
    config: StrategyConfig
    base_gate: str


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _round(value: Any, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    val = _finite(value, default=float("nan"))
    if not math.isfinite(val):
        return None
    return round(val, digits)


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


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _time_mask(index: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    start_min = _minutes(start)
    end_min = _minutes(end)
    minutes = index.hour * 60 + index.minute
    if start_min <= end_min:
        return (minutes >= start_min) & (minutes < end_min)
    return (minutes >= start_min) | (minutes < end_min)


def _rolling_percentile(series: pd.Series, window: int = 60, min_periods: int = 10) -> pd.Series:
    def pct(values: np.ndarray) -> float:
        current = values[-1]
        if not np.isfinite(current):
            return np.nan
        valid = values[np.isfinite(values)]
        if len(valid) < min_periods:
            return np.nan
        return float(np.sum(valid <= current) / len(valid))

    return series.rolling(window, min_periods=min_periods).apply(pct, raw=True)


def _slice_trades(trades: list[TradeResult], start: str, end_inclusive: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end_inclusive]


def _filled(trades: list[TradeResult]) -> list[TradeResult]:
    return [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]


def _metrics_for(trades: list[TradeResult], start: str, end_inclusive: str) -> dict[str, Any]:
    return compute_metrics(_slice_trades(trades, start, end_inclusive))


def _score_from_metrics(last1: dict[str, Any], last2: dict[str, Any], min_fills: int) -> float:
    fills = int(last1.get("total_trades", 0) or 0)
    fill_penalty = max(0, min_fills - fills) * 3.0
    return (
        _finite(last1.get("total_r")) * 1.0
        + _finite(last1.get("calmar_ratio")) * 2.0
        + _finite(last1.get("profit_factor")) * 2.0
        + _finite(last2.get("total_r")) * 0.25
        + _finite(last2.get("calmar_ratio")) * 0.5
        - abs(_finite(last1.get("max_drawdown_r"))) * 0.35
        - fill_penalty
    )


def _score_row(
    *,
    hot: HotLeg,
    gate_id: str,
    family: str,
    label: str,
    stage: str,
    component_gates: tuple[str, ...],
    trades: list[TradeResult],
    base_metrics: dict[str, dict[str, Any]],
    last1_start: str,
    last2_start: str,
    end_inclusive: str,
) -> dict[str, Any]:
    last1 = _metrics_for(trades, last1_start, end_inclusive)
    last2 = _metrics_for(trades, last2_start, end_inclusive)
    min_fills = prev.MIN_FILLS_BY_KIND[hot.leg.kind]
    base_last1 = base_metrics["last1"]
    return {
        "leg": hot.leg.key,
        "leg_label": hot.leg.label,
        "symbol": hot.leg.symbol,
        "kind": hot.leg.kind,
        "stage": stage,
        "family": family,
        "gate_id": gate_id,
        "label": label,
        "base_regime_gate": hot.base_gate,
        "component_gates": "|".join(component_gates),
        "last1_fills": int(last1.get("total_trades", 0) or 0),
        "last1_net_r": _round(last1.get("total_r"), 2),
        "last1_calmar": _round(last1.get("calmar_ratio"), 3),
        "last1_pf": _round(last1.get("profit_factor"), 3),
        "last1_wr_pct": _round(_finite(last1.get("win_rate")) * 100.0, 2),
        "last1_dd_r": _round(last1.get("max_drawdown_r"), 2),
        "last2_fills": int(last2.get("total_trades", 0) or 0),
        "last2_net_r": _round(last2.get("total_r"), 2),
        "last2_calmar": _round(last2.get("calmar_ratio"), 3),
        "last2_pf": _round(last2.get("profit_factor"), 3),
        "last2_dd_r": _round(last2.get("max_drawdown_r"), 2),
        "delta_last1_net_r": _round(_finite(last1.get("total_r")) - _finite(base_last1.get("total_r")), 2),
        "delta_last1_calmar": _round(_finite(last1.get("calmar_ratio")) - _finite(base_last1.get("calmar_ratio")), 3),
        "delta_last1_dd_r": _round(_finite(last1.get("max_drawdown_r")) - _finite(base_last1.get("max_drawdown_r")), 2),
        "score": _round(_score_from_metrics(last1, last2, min_fills), 4),
        "eligible_min_fills": int(last1.get("total_trades", 0) or 0) >= min_fills,
    }


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    def fmt(value: Any) -> str:
        if value is None or value == "":
            return "-"
        if isinstance(value, float):
            return f"{value:g}"
        return str(value).replace("|", "\\|")

    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _option_lookup_for_seed(leg: prev.LegSpec, seed: prev.VariantSpec) -> dict[str, prev.OptionSpec]:
    lookup: dict[str, prev.OptionSpec] = {}
    for options in squeeze._options_for_seed(leg, seed.config).values():
        for option in options:
            lookup[option.option_id] = option
    return lookup


def _config_from_squeeze_row(
    leg: prev.LegSpec,
    row: dict[str, Any],
    previous_summary: dict[str, Any],
) -> StrategyConfig:
    seeds = squeeze._seed_variants(leg, previous_summary)
    variant_id = str(row["variant_id"])
    for seed in seeds:
        if not variant_id.startswith(seed.variant_id):
            continue
        lookup = _option_lookup_for_seed(leg, seed)
        options: list[prev.OptionSpec] = []
        for option_id in str(row.get("option_ids", "")).split("|"):
            option = lookup.get(option_id)
            if option is not None:
                options.append(option)
        return prev._variant_config(seed.config, f"{leg.key}__hot_structural_base", options)
    raise ValueError(f"Could not reconstruct squeeze config for {leg.key}: {variant_id}")


def _load_hot_legs() -> tuple[list[HotLeg], dict[str, Any], dict[str, Any]]:
    squeeze_summary = json.loads(SQUEEZE_SUMMARY_PATH.read_text())
    previous_summary = json.loads(PREV_SUMMARY_PATH.read_text())
    all_legs = {leg.key: leg for leg in prev._base_legs()}
    hot_legs: list[HotLeg] = []
    for leg_key in REQUESTED_LEGS:
        leg = all_legs[leg_key]
        row = squeeze_summary["best_curve_squeeze_by_leg"][leg_key]
        config = _config_from_squeeze_row(leg, row, previous_summary)
        hot_legs.append(
            HotLeg(
                leg=leg,
                row=row,
                config=config,
                base_gate=str(row.get("gate", "gate_none")),
            )
        )
    return hot_legs, squeeze_summary, previous_summary


def _daily_context(df: pd.DataFrame, atr_length: int) -> dict[str, dict[str, Any]]:
    rth = df[_time_mask(df.index, "09:30", "16:00")]
    daily = rth.groupby(rth.index.date).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    daily.index = pd.to_datetime(daily.index)
    prior = daily.shift(1)
    prior2 = daily.shift(2)
    prior_range = prior["high"] - prior["low"]
    prior_close_loc = (prior["close"] - prior["low"]) / prior_range.replace(0, np.nan)
    prior_ret = prior["close"] - prior["open"]
    prior_inside = (prior["high"] <= prior2["high"]) & (prior["low"] >= prior2["low"])
    prior_outside = (prior["high"] >= prior2["high"]) & (prior["low"] <= prior2["low"])
    prior_range_pctile = _rolling_percentile(prior_range)

    atr_values = pd.Series(compute_daily_atr(df, length=atr_length), index=df.index)
    day_atr = atr_values.groupby(atr_values.index.normalize()).first()

    out: dict[str, dict[str, Any]] = {}
    for date in daily.index:
        key = date.date().isoformat()
        date_yyyymmdd = date.strftime("%Y%m%d")
        p_range = _finite(prior_range.get(date), default=float("nan"))
        p_ret = _finite(prior_ret.get(date), default=float("nan"))
        p_close_loc = _finite(prior_close_loc.get(date), default=float("nan"))
        out[key] = {
            "prior_range": p_range,
            "prior_range_pctile": _finite(prior_range_pctile.get(date), default=float("nan")),
            "prior_trend_dir": 1 if p_ret > 0 else (-1 if p_ret < 0 else 0),
            "prior_close_loc": p_close_loc,
            "prior_inside_day": bool(prior_inside.get(date, False)),
            "prior_outside_day": bool(prior_outside.get(date, False)),
            "daily_atr": _finite(day_atr.get(date), default=float("nan")),
            "dow": int(date.dayofweek),
            "dom": int(date.day),
            "is_bom3": int(date.day) <= 3,
            "is_mid_month": 8 <= int(date.day) <= 18,
            "is_eom5": int(date.day) >= 25,
            "is_fomc": date_yyyymmdd in FOMC_SET,
            "is_cpi": date_yyyymmdd in CPI_SET,
            "is_nfp": date_yyyymmdd in NFP_SET,
            "is_ppi": date_yyyymmdd in PPI_SET,
            "is_news": date_yyyymmdd in (FOMC_SET | CPI_SET | NFP_SET | PPI_SET),
        }
    return out


def _orb_context(df: pd.DataFrame, config: StrategyConfig) -> dict[str, dict[str, Any]]:
    session = config.sessions[0]
    orb_start = session.orb_start
    orb_end = session.orb_end
    if not orb_start or not orb_end:
        # LSI configs do not define an ORB, but this structural pass still
        # needs a causal opening-range context variable. Use the canonical
        # session opening range as a proxy rather than changing the signal.
        if session.name == "Asia":
            orb_start, orb_end = "20:00", "20:15"
        else:
            orb_start, orb_end = "09:30", "09:45"
    mask = _time_mask(df.index, orb_start, orb_end)
    orb_df = df[mask]
    grouped = orb_df.groupby(orb_df.index.date)
    raw = grouped.agg(
        orb_open=("open", "first"),
        orb_high=("high", "max"),
        orb_low=("low", "min"),
        orb_close=("close", "last"),
    )
    raw.index = pd.to_datetime(raw.index)
    raw["orb_range"] = raw["orb_high"] - raw["orb_low"]
    raw["orb_range_pctile"] = _rolling_percentile(raw["orb_range"], window=60, min_periods=10)
    out: dict[str, dict[str, Any]] = {}
    for date, row in raw.iterrows():
        out[date.date().isoformat()] = {
            "orb_open": _finite(row["orb_open"], default=float("nan")),
            "orb_high": _finite(row["orb_high"], default=float("nan")),
            "orb_low": _finite(row["orb_low"], default=float("nan")),
            "orb_close": _finite(row["orb_close"], default=float("nan")),
            "orb_range": _finite(row["orb_range"], default=float("nan")),
            "orb_range_pctile": _finite(row["orb_range_pctile"], default=float("nan")),
        }
    return out


def _asia_context_for_ny(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    dates = pd.Series(df.index.normalize().unique()).sort_values()
    ranges: list[tuple[pd.Timestamp, float]] = []
    for date in dates:
        prev_day = date - pd.Timedelta(days=1)
        start = prev_day + pd.Timedelta(hours=20)
        end = date + pd.Timedelta(hours=6)
        window = df[(df.index >= start) & (df.index < end)]
        if window.empty:
            continue
        rng = float(window["high"].max() - window["low"].min())
        ranges.append((date, rng))
        open_val = float(window["open"].iloc[0])
        close_val = float(window["close"].iloc[-1])
        ny_open_window = df[(df.index >= date + pd.Timedelta(hours=9, minutes=30)) & (df.index < date + pd.Timedelta(hours=9, minutes=35))]
        ny_open = float(ny_open_window["open"].iloc[0]) if not ny_open_window.empty else float("nan")
        out[date.date().isoformat()] = {
            "asia_range": rng,
            "asia_high": float(window["high"].max()),
            "asia_low": float(window["low"].min()),
            "asia_trend_dir": 1 if close_val > open_val else (-1 if close_val < open_val else 0),
            "ny_open_inside_asia": bool(np.isfinite(ny_open) and window["low"].min() <= ny_open <= window["high"].max()),
            "ny_open_above_asia": bool(np.isfinite(ny_open) and ny_open > window["high"].max()),
            "ny_open_below_asia": bool(np.isfinite(ny_open) and ny_open < window["low"].min()),
        }

    if ranges:
        ser = pd.Series({date: rng for date, rng in ranges}).sort_index()
        pct = _rolling_percentile(ser, window=60, min_periods=10)
        for date, value in pct.items():
            key = date.date().isoformat()
            if key in out:
                out[key]["asia_range_pctile"] = _finite(value, default=float("nan"))
    return out


def _feature_context(df: pd.DataFrame, config: StrategyConfig) -> dict[str, Any]:
    return {
        "daily": _daily_context(df, config.atr_length),
        "orb": _orb_context(df, config),
        "asia": _asia_context_for_ny(df),
    }


def _trade_features(
    trade: TradeResult,
    df: pd.DataFrame,
    context: dict[str, Any],
) -> dict[str, Any]:
    features: dict[str, Any] = {}
    features.update(context["daily"].get(trade.date, {}))
    features.update(context["orb"].get(trade.date, {}))
    features.update(context["asia"].get(trade.date, {}))

    daily_atr = _finite(features.get("daily_atr"), default=float("nan"))
    orb_range = _finite(features.get("orb_range"), default=float("nan"))
    if np.isfinite(daily_atr) and daily_atr > 0 and np.isfinite(orb_range):
        features["orb_atr_pct"] = orb_range / daily_atr * 100.0
    else:
        features["orb_atr_pct"] = float("nan")

    if trade.signal_bar >= 0 and trade.signal_bar < len(df):
        bar = df.iloc[trade.signal_bar]
        high = _finite(bar["high"], default=float("nan"))
        low = _finite(bar["low"], default=float("nan"))
        open_ = _finite(bar["open"], default=float("nan"))
        close = _finite(bar["close"], default=float("nan"))
        candle_range = high - low
        if np.isfinite(candle_range) and candle_range > 0:
            body_pct = abs(close - open_) / candle_range
            if trade.direction == 1:
                close_loc = (close - low) / candle_range
                adverse_wick_pct = (high - max(open_, close)) / candle_range
                dist = (close - _finite(features.get("orb_high"), default=float("nan"))) / max(orb_range, 1e-9) * 100.0
            else:
                close_loc = (high - close) / candle_range
                adverse_wick_pct = (min(open_, close) - low) / candle_range
                dist = (_finite(features.get("orb_low"), default=float("nan")) - close) / max(orb_range, 1e-9) * 100.0
            features.update(
                {
                    "signal_body_pct": body_pct,
                    "signal_close_strength": close_loc,
                    "signal_adverse_wick_pct": adverse_wick_pct,
                    "signal_dist_orb_pct": dist,
                    "signal_closes_outside_orb": dist > 0,
                }
            )

    risk = _finite(trade.risk_points, default=float("nan"))
    if np.isfinite(risk) and np.isfinite(daily_atr) and daily_atr > 0:
        features["risk_atr_pct"] = risk / daily_atr * 100.0
    else:
        features["risk_atr_pct"] = float("nan")
    if np.isfinite(risk) and np.isfinite(orb_range) and orb_range > 0:
        features["risk_orb_pct"] = risk / orb_range * 100.0
    else:
        features["risk_orb_pct"] = float("nan")

    features["prior_trend_aligned"] = int(features.get("prior_trend_dir", 0) or 0) == trade.direction
    features["asia_trend_aligned"] = int(features.get("asia_trend_dir", 0) or 0) == trade.direction
    prior_close_loc = _finite(features.get("prior_close_loc"), default=float("nan"))
    features["prior_close_aligned_extreme"] = (
        prior_close_loc >= 0.66 if trade.direction == 1 else prior_close_loc <= 0.34
    )
    return features


def _has(feature: str, lo: float | None = None, hi: float | None = None) -> Callable[[dict[str, Any], TradeResult], bool]:
    def pred(features: dict[str, Any], _trade: TradeResult) -> bool:
        val = _finite(features.get(feature), default=float("nan"))
        if not np.isfinite(val):
            return False
        if lo is not None and val < lo:
            return False
        if hi is not None and val > hi:
            return False
        return True

    return pred


def _bool(feature: str, expected: bool = True) -> Callable[[dict[str, Any], TradeResult], bool]:
    return lambda features, _trade: bool(features.get(feature, False)) is expected


def _not(pred: Callable[[dict[str, Any], TradeResult], bool]) -> Callable[[dict[str, Any], TradeResult], bool]:
    return lambda features, trade: not pred(features, trade)


def _and(*predicates: Callable[[dict[str, Any], TradeResult], bool]) -> Callable[[dict[str, Any], TradeResult], bool]:
    return lambda features, trade: all(pred(features, trade) for pred in predicates)


def _base_gate_specs(session_name: str) -> list[GateSpec]:
    gates = [
        GateSpec("orb_size", "orb_tiny", "only tiny ORB range pctile <= 20%", _has("orb_range_pctile", hi=0.20), "orb_range", 0),
        GateSpec("orb_size", "orb_low", "only low ORB range pctile <= 33%", _has("orb_range_pctile", hi=0.33), "orb_range", 1),
        GateSpec("orb_size", "orb_mid", "only mid ORB range pctile 33-67%", _has("orb_range_pctile", lo=0.33, hi=0.67), "orb_range", 2),
        GateSpec("orb_size", "orb_high", "only high ORB range pctile >= 67%", _has("orb_range_pctile", lo=0.67), "orb_range", 3),
        GateSpec("orb_size", "orb_not_high", "exclude high ORB range pctile", _has("orb_range_pctile", hi=0.67), "orb_range", 2),
        GateSpec("orb_size", "orb_not_extreme", "exclude extreme ORB range pctile >= 80%", _has("orb_range_pctile", hi=0.80), "orb_range", 3),
        GateSpec("prior_day", "prior_range_low", "only low prior-day range pctile <= 33%", _has("prior_range_pctile", hi=0.33), "prior_range", 0),
        GateSpec("prior_day", "prior_range_mid", "only mid prior-day range pctile 33-67%", _has("prior_range_pctile", lo=0.33, hi=0.67), "prior_range", 1),
        GateSpec("prior_day", "prior_range_high", "only high prior-day range pctile >= 67%", _has("prior_range_pctile", lo=0.67), "prior_range", 2),
        GateSpec("prior_day", "prior_trend_aligned", "prior RTH trend aligns with trade direction", _bool("prior_trend_aligned")),
        GateSpec("prior_day", "prior_trend_fade", "prior RTH trend opposes trade direction", _bool("prior_trend_aligned", False)),
        GateSpec("prior_day", "prior_close_aligned_extreme", "prior close near directional extreme", _bool("prior_close_aligned_extreme")),
        GateSpec("prior_day", "prior_inside_day", "only after inside day", _bool("prior_inside_day")),
        GateSpec("prior_day", "prior_not_inside_day", "exclude inside day", _bool("prior_inside_day", False)),
        GateSpec("prior_day", "prior_outside_day", "only after outside day", _bool("prior_outside_day")),
        GateSpec("calendar_news", "exclude_news", "exclude FOMC/CPI/NFP/PPI dates", _bool("is_news", False)),
        GateSpec("calendar_news", "only_news", "only FOMC/CPI/NFP/PPI dates", _bool("is_news", True)),
        GateSpec("calendar_news", "exclude_fomc", "exclude FOMC dates", _bool("is_fomc", False)),
        GateSpec("calendar_news", "exclude_cpi_nfp", "exclude CPI and NFP dates", lambda f, _t: not bool(f.get("is_cpi")) and not bool(f.get("is_nfp"))),
        GateSpec("calendar_news", "only_bom3", "only day-of-month 1-3", _bool("is_bom3", True)),
        GateSpec("calendar_news", "exclude_bom3", "exclude day-of-month 1-3", _bool("is_bom3", False)),
        GateSpec("calendar_news", "only_mid_month", "only day-of-month 8-18", _bool("is_mid_month", True)),
        GateSpec("calendar_news", "exclude_eom5", "exclude day-of-month >= 25", _bool("is_eom5", False)),
        GateSpec("hunter_proxy", "signal_close_strong_65", "signal closes in directional 65% of candle", _has("signal_close_strength", lo=0.65), "close_strength", 1),
        GateSpec("hunter_proxy", "signal_close_strong_80", "signal closes in directional 80% of candle", _has("signal_close_strength", lo=0.80), "close_strength", 2),
        GateSpec("hunter_proxy", "signal_body_50", "signal body >= 50% of candle", _has("signal_body_pct", lo=0.50), "body", 1),
        GateSpec("hunter_proxy", "signal_body_65", "signal body >= 65% of candle", _has("signal_body_pct", lo=0.65), "body", 2),
        GateSpec("hunter_proxy", "adverse_wick_le_20", "adverse wick <= 20%", _has("signal_adverse_wick_pct", hi=0.20), "wick", 0),
        GateSpec("hunter_proxy", "adverse_wick_le_35", "adverse wick <= 35%", _has("signal_adverse_wick_pct", hi=0.35), "wick", 1),
        GateSpec("hunter_proxy", "dist_orb_near", "signal distance 0-50% of ORB", _has("signal_dist_orb_pct", lo=0.0, hi=50.0), "dist_orb", 0),
        GateSpec("hunter_proxy", "dist_orb_mid", "signal distance 50-100% of ORB", _has("signal_dist_orb_pct", lo=50.0, hi=100.0), "dist_orb", 1),
        GateSpec("hunter_proxy", "dist_orb_far", "signal distance >= 100% of ORB", _has("signal_dist_orb_pct", lo=100.0), "dist_orb", 2),
        GateSpec("hunter_proxy", "signal_outside_orb", "signal close outside ORB edge", _bool("signal_closes_outside_orb", True)),
        GateSpec(
            "custom_day_type",
            "compression_breakout",
            "low prior range plus non-tiny ORB",
            _and(_has("prior_range_pctile", hi=0.33), _has("orb_range_pctile", lo=0.20)),
        ),
        GateSpec(
            "custom_day_type",
            "tiny_orb_prior_trend",
            "tiny/low ORB with prior trend alignment",
            _and(_has("orb_range_pctile", hi=0.33), _bool("prior_trend_aligned")),
        ),
        GateSpec(
            "custom_day_type",
            "momentum_carry",
            "prior trend and prior close extreme align",
            _and(_bool("prior_trend_aligned"), _bool("prior_close_aligned_extreme")),
        ),
        GateSpec(
            "custom_day_type",
            "expansion_stack",
            "high prior range plus high ORB range",
            _and(_has("prior_range_pctile", lo=0.67), _has("orb_range_pctile", lo=0.67)),
        ),
    ]
    if session_name == "NY":
        gates.extend(
            [
                GateSpec("session_context", "asia_range_low", "NY only: low overnight Asia range", _has("asia_range_pctile", hi=0.33), "asia_range", 0),
                GateSpec("session_context", "asia_range_mid", "NY only: mid overnight Asia range", _has("asia_range_pctile", lo=0.33, hi=0.67), "asia_range", 1),
                GateSpec("session_context", "asia_range_high", "NY only: high overnight Asia range", _has("asia_range_pctile", lo=0.67), "asia_range", 2),
                GateSpec("session_context", "asia_trend_aligned", "NY only: Asia trend aligns with trade", _bool("asia_trend_aligned")),
                GateSpec("session_context", "ny_open_inside_asia", "NY opens inside Asia range", _bool("ny_open_inside_asia")),
                GateSpec("session_context", "ny_open_outside_asia", "NY opens outside Asia range", lambda f, _t: bool(f.get("ny_open_above_asia")) or bool(f.get("ny_open_below_asia"))),
                GateSpec(
                    "custom_day_type",
                    "contained_asia_breakout",
                    "NY opens inside Asia range and signal closes outside ORB",
                    _and(_bool("ny_open_inside_asia"), _bool("signal_closes_outside_orb")),
                ),
            ]
        )
    else:
        gates.extend(
            [
                GateSpec("session_context", "asia_prior_rth_trend_aligned", "Asia: prior RTH trend aligns", _bool("prior_trend_aligned")),
                GateSpec("session_context", "asia_prior_rth_fade", "Asia: fade prior RTH trend", _bool("prior_trend_aligned", False)),
                GateSpec("session_context", "asia_prior_close_extreme", "Asia: prior RTH close near directional extreme", _bool("prior_close_aligned_extreme")),
            ]
        )
    return gates


def _feature_rows_for_trades(
    trades: list[TradeResult],
    df: pd.DataFrame,
    context: dict[str, Any],
) -> dict[TradeResult, dict[str, Any]]:
    return {trade: _trade_features(trade, df, context) for trade in trades}


def _apply_gate(
    trades: list[TradeResult],
    feature_rows: dict[TradeResult, dict[str, Any]],
    gate: GateSpec,
) -> list[TradeResult]:
    return [trade for trade in trades if gate.predicate(feature_rows.get(trade, {}), trade)]


def _apply_gate_combo(
    trades: list[TradeResult],
    feature_rows: dict[TradeResult, dict[str, Any]],
    gates: tuple[GateSpec, ...],
) -> list[TradeResult]:
    out = trades
    for gate in gates:
        out = _apply_gate(out, feature_rows, gate)
    return out


def _top_gate_per_family(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for family in GATE_FAMILIES:
        family_rows = [
            row for row in rows
            if row["stage"] == "oat"
            and row["family"] == family
            and row["eligible_min_fills"]
            and _finite(row["last1_net_r"]) > 0
        ]
        if not family_rows:
            continue
        family_rows.sort(
            key=lambda row: (
                _finite(row["score"]),
                _finite(row["last1_calmar"]),
                _finite(row["last1_net_r"]),
            ),
            reverse=True,
        )
        selected[family] = family_rows[0]
    return selected


def _surface_for_combo(
    candidate_row: dict[str, Any],
    leave_one_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    cand_calmar = _finite(candidate_row.get("last1_calmar"))
    if cand_calmar <= 0 or not leave_one_rows:
        return {"surface": "cliff", "plateau_ratio": 0.0, "leave_one_count": len(leave_one_rows)}
    ratios = []
    for row in leave_one_rows:
        ratios.append(_finite(row.get("last1_calmar")) / cand_calmar)
    median_ratio = float(np.median(ratios)) if ratios else 0.0
    ge80 = sum(1 for value in ratios if value >= 0.80)
    ge60 = sum(1 for value in ratios if value >= 0.60)
    if len(ratios) >= 3 and median_ratio >= 0.70 and ge80 >= 2:
        surface = "curve"
    elif len(ratios) >= 2 and median_ratio >= 0.50 and ge60 >= 2:
        surface = "soft_curve"
    else:
        surface = "cliff"
    return {
        "surface": surface,
        "plateau_ratio": round(median_ratio, 3),
        "leave_one_count": len(leave_one_rows),
        "leave_one_ge80_count": ge80,
        "leave_one_ge60_count": ge60,
    }


def _write_report(
    *,
    hot_legs: list[HotLeg],
    rows: list[dict[str, Any]],
    selected_manifest: dict[str, Any],
    last1_start: str,
    last2_start: str,
    end_inclusive: str,
) -> None:
    lines = [
        "# Hot Structural Sequence",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Last-1y window: `{last1_start}` to `{end_inclusive}`",
        f"- Last-2y/context window: `{last2_start}` to `{end_inclusive}`",
        "- Baseline: current `HOT_ONE_YEAR_SQUEEZE` best curve-squeeze candidate per leg, including its existing regime gate.",
        "- Tested structural families: ORB size regimes, prior-day range/trend context, Asia/NY session context, calendar/news filters, Hunter-inspired signal proxies, and custom day-type combinations.",
        "- These are TESTING-only, hot-regime candidates; no Bailey-style deflation or holdout discipline is applied here.",
        "",
        "## Best Structural Candidates",
        "",
    ]
    score_rows = []
    net_rows = []
    for hot in hot_legs:
        leg_rows = [
            row for row in rows
            if row["leg"] == hot.leg.key
            and row["stage"] in {"combo", "oat"}
            and row["eligible_min_fills"]
            and _finite(row["last1_net_r"]) > 0
        ]
        leg_rows.sort(
            key=lambda row: (
                _finite(row["score"]),
                _finite(row["last1_calmar"]),
                _finite(row["last1_net_r"]),
            ),
            reverse=True,
        )
        base = next(row for row in rows if row["leg"] == hot.leg.key and row["stage"] == "baseline")
        score_pick = leg_rows[0] if leg_rows else base
        score_rows.append(
            {
                "leg": hot.leg.label,
                "pick": score_pick["gate_id"],
                "family": score_pick["family"],
                "surface": score_pick.get("surface", "n/a"),
                "fills": score_pick["last1_fills"],
                "net_r": score_pick["last1_net_r"],
                "calmar": score_pick["last1_calmar"],
                "pf": score_pick["last1_pf"],
                "dd": score_pick["last1_dd_r"],
                "delta_r": score_pick["delta_last1_net_r"],
                "base_r": base["last1_net_r"],
            }
        )
        positive = [row for row in leg_rows if _finite(row["delta_last1_net_r"]) > 0]
        positive.sort(
            key=lambda row: (
                _finite(row["delta_last1_net_r"]),
                _finite(row["last1_calmar"]),
                _finite(row["score"]),
            ),
            reverse=True,
        )
        net_pick = positive[0] if positive else None
        net_rows.append(
            {
                "leg": hot.leg.label,
                "pick": net_pick["gate_id"] if net_pick else "none",
                "family": net_pick["family"] if net_pick else "-",
                "surface": net_pick.get("surface", "n/a") if net_pick else "-",
                "fills": net_pick["last1_fills"] if net_pick else "-",
                "net_r": net_pick["last1_net_r"] if net_pick else "-",
                "calmar": net_pick["last1_calmar"] if net_pick else "-",
                "pf": net_pick["last1_pf"] if net_pick else "-",
                "dd": net_pick["last1_dd_r"] if net_pick else "-",
                "delta_r": net_pick["delta_last1_net_r"] if net_pick else "-",
                "base_r": base["last1_net_r"],
            }
        )
    lines.extend(
        [
            "### Best Score / Calmar Tilt",
            "",
            _markdown_table(score_rows, ["leg", "pick", "family", "surface", "fills", "net_r", "calmar", "pf", "dd", "delta_r", "base_r"]),
            "",
            "### Best Net Additions",
            "",
            _markdown_table(net_rows, ["leg", "pick", "family", "surface", "fills", "net_r", "calmar", "pf", "dd", "delta_r", "base_r"]),
        ]
    )

    for hot in hot_legs:
        lines.extend(["", f"## {hot.leg.label}", ""])
        base = next(row for row in rows if row["leg"] == hot.leg.key and row["stage"] == "baseline")
        lines.append(
            f"Baseline after existing `{hot.base_gate}` gate: "
            f"{base['last1_fills']} fills, `{base['last1_net_r']}R`, Calmar `{base['last1_calmar']}`, "
            f"PF `{base['last1_pf']}`, DD `{base['last1_dd_r']}R`."
        )
        lines.extend(["", "### Best OAT Gates", ""])
        oat_rows = [
            row for row in rows
            if row["leg"] == hot.leg.key
            and row["stage"] == "oat"
            and row["eligible_min_fills"]
            and _finite(row["last1_net_r"]) > 0
        ]
        oat_rows.sort(key=lambda row: (_finite(row["score"]), _finite(row["last1_calmar"]), _finite(row["last1_net_r"])), reverse=True)
        lines.append(_markdown_table(oat_rows[:10], ["family", "gate_id", "last1_fills", "last1_net_r", "last1_calmar", "last1_pf", "last1_dd_r", "delta_last1_net_r", "last2_net_r", "label"]))

        lines.extend(["", "### Best Combos", ""])
        combo_rows = [
            row for row in rows
            if row["leg"] == hot.leg.key
            and row["stage"] == "combo"
            and row["eligible_min_fills"]
            and _finite(row["last1_net_r"]) > 0
        ]
        combo_rows.sort(key=lambda row: (_finite(row["score"]), _finite(row["last1_calmar"]), _finite(row["last1_net_r"])), reverse=True)
        lines.append(_markdown_table(combo_rows[:10], ["gate_id", "surface", "last1_fills", "last1_net_r", "last1_calmar", "last1_pf", "last1_dd_r", "delta_last1_net_r", "last2_net_r", "plateau_ratio", "component_gates"]))

        lines.extend(
            [
                "",
                "<details><summary>Selected family gates for combo search</summary>",
                "",
                "```json",
                json.dumps(selected_manifest.get(hot.leg.key, {}), indent=2, sort_keys=True),
                "```",
                "",
                "</details>",
            ]
        )

    lines.extend(
        [
            "",
            "## Read",
            "",
            "- A positive `delta_r` means the structural gate improved the already-gated hot baseline over the last-year window.",
            "- Combo `surface` is a leave-one-gate stability check. `curve` means most drop-one variants retained the candidate Calmar; `cliff` means the combo depends heavily on all filters being stacked.",
            "- The gates are post-trade structural filters, so they identify candidate context variables before we hard-code anything into the engine or live execution config.",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def _write_asset_notes(hot_legs: list[HotLeg], rows: list[dict[str, Any]], last1_start: str, end_inclusive: str) -> None:
    by_symbol: dict[str, list[HotLeg]] = defaultdict(list)
    for hot in hot_legs:
        by_symbol[hot.leg.symbol].append(hot)
    paths = {"NQ": prev.NQ_LEARNINGS_PATH, "ES": prev.ES_LEARNINGS_PATH, "GC": prev.GC_LEARNINGS_PATH}
    for symbol, symbol_legs in by_symbol.items():
        lines = [
            "",
            f"- **Hot structural sequence** (2026-05-03): `backtesting/learnings/reports/HOT_STRUCTURAL_SEQUENCE_20260503.md`",
            f"  - Window: `{last1_start}` to `{end_inclusive}`. Post-trade structural gates around current hot one-year candidates.",
        ]
        for hot in symbol_legs:
            leg_rows = [
                row for row in rows
                if row["leg"] == hot.leg.key
                and row["stage"] in {"combo", "oat"}
                and row["eligible_min_fills"]
                and _finite(row["last1_net_r"]) > 0
            ]
            leg_rows.sort(key=lambda row: (_finite(row["score"]), _finite(row["last1_calmar"]), _finite(row["last1_net_r"])), reverse=True)
            if not leg_rows:
                continue
            row = leg_rows[0]
            lines.append(
                f"  - {hot.leg.label}: best structural `{row['gate_id']}` ({row['family']}) -> "
                f"{row['last1_fills']} fills, `{row['last1_net_r']}R`, Calmar `{row['last1_calmar']}`, "
                f"PF `{row['last1_pf']}`, DD `{row['last1_dd_r']}R`, delta `{row['delta_last1_net_r']}R`; "
                "TESTING-only."
            )
        path = paths[symbol]
        existing = path.read_text().rstrip()
        marker = "- **Hot structural sequence** (2026-05-03):"
        if marker in existing:
            existing = existing.split(marker)[0].rstrip()
        path.write_text(existing + "\n" + "\n".join(lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    hot_legs, squeeze_summary, previous_summary = _load_hot_legs()
    last1_start = str(squeeze_summary["period_start"])
    end_inclusive = str(squeeze_summary["period_end"])
    end_exclusive = str(squeeze_summary["end_exclusive"])
    last2_start = (pd.Timestamp(end_inclusive) - pd.Timedelta(days=730)).date().isoformat()

    # Reuse the existing loader, but widen its warmup/context window.
    prev.LOAD_START = STRUCTURAL_LOAD_START

    print(f"Hot structural sequence: {last1_start} to {end_inclusive}", flush=True)
    print(f"Context/last2 starts: {last2_start}; load starts: {STRUCTURAL_LOAD_START}", flush=True)

    loaded_cache: dict[tuple[str, str], prev.LoadedData] = {}
    all_rows: list[dict[str, Any]] = []
    selected_manifest: dict[str, Any] = {}

    for hot in hot_legs:
        leg = hot.leg
        print(f"\n=== {leg.label} ===", flush=True)
        key = (leg.symbol, leg.timeframe)
        if key not in loaded_cache:
            print(f"  loading {leg.symbol} {leg.timeframe}", flush=True)
            loaded_cache[key] = prev._load_data(leg.symbol, leg.timeframe, end_exclusive, last1_start)
        loaded = loaded_cache[key]

        variant = prev.VariantSpec(
            leg.key,
            "hot_structural_base",
            "baseline",
            "baseline",
            "current hot squeeze winner",
            ("hot_structural_base",),
            hot.config,
        )
        results = prev._run_variants(leg, loaded, [variant], start_date=last2_start, end_date=end_exclusive)
        raw_trades = results[variant.config.name]
        base_trades = squeeze._apply_gate(raw_trades, loaded.regime_lookup, hot.base_gate)
        context = _feature_context(loaded.df_base, hot.config)
        feature_rows = _feature_rows_for_trades(base_trades, loaded.df_base, context)

        base_metrics = {
            "last1": _metrics_for(base_trades, last1_start, end_inclusive),
            "last2": _metrics_for(base_trades, last2_start, end_inclusive),
        }
        all_rows.append(
            _score_row(
                hot=hot,
                gate_id="baseline",
                family="baseline",
                label="current squeeze winner plus existing regime gate",
                stage="baseline",
                component_gates=(),
                trades=base_trades,
                base_metrics=base_metrics,
                last1_start=last1_start,
                last2_start=last2_start,
                end_inclusive=end_inclusive,
            )
        )

        gates = _base_gate_specs(hot.config.sessions[0].name)
        gate_by_id = {gate.gate_id: gate for gate in gates}
        oat_rows: list[dict[str, Any]] = []
        print(f"  OAT structural gates: {len(gates)}", flush=True)
        for gate in gates:
            gated = _apply_gate(base_trades, feature_rows, gate)
            row = _score_row(
                hot=hot,
                gate_id=gate.gate_id,
                family=gate.family,
                label=gate.label,
                stage="oat",
                component_gates=(gate.gate_id,),
                trades=gated,
                base_metrics=base_metrics,
                last1_start=last1_start,
                last2_start=last2_start,
                end_inclusive=end_inclusive,
            )
            oat_rows.append(row)
            all_rows.append(row)

        best_by_family = _top_gate_per_family(oat_rows)
        combo_families = [
            family for family, row in sorted(
                best_by_family.items(),
                key=lambda item: (_finite(item[1]["score"]), _finite(item[1]["last1_calmar"]), _finite(item[1]["last1_net_r"])),
                reverse=True,
            )
            if _finite(row["last1_net_r"]) > 0 and row["eligible_min_fills"]
        ][:5]
        selected_manifest[leg.key] = {
            "base_gate": hot.base_gate,
            "base_variant": hot.row.get("variant_id"),
            "families": {
                family: {
                    "gate_id": best_by_family[family]["gate_id"],
                    "label": best_by_family[family]["label"],
                    "last1_net_r": best_by_family[family]["last1_net_r"],
                    "last1_calmar": best_by_family[family]["last1_calmar"],
                    "delta_last1_net_r": best_by_family[family]["delta_last1_net_r"],
                }
                for family in combo_families
            },
        }
        print(f"  combo families: {combo_families}", flush=True)

        combo_specs = [gate_by_id[best_by_family[family]["gate_id"]] for family in combo_families]
        combo_rows_for_leg: list[dict[str, Any]] = []
        for mask in product([False, True], repeat=len(combo_specs)):
            if not any(mask):
                continue
            selected_gates = tuple(gate for gate, include in zip(combo_specs, mask) if include)
            if len(selected_gates) == 1:
                continue
            combo_id = "combo__" + "__".join(gate.gate_id for gate in selected_gates)
            combo_label = " + ".join(gate.label for gate in selected_gates)
            combo_trades = _apply_gate_combo(base_trades, feature_rows, selected_gates)
            row = _score_row(
                hot=hot,
                gate_id=combo_id,
                family="combo",
                label=combo_label,
                stage="combo",
                component_gates=tuple(gate.gate_id for gate in selected_gates),
                trades=combo_trades,
                base_metrics=base_metrics,
                last1_start=last1_start,
                last2_start=last2_start,
                end_inclusive=end_inclusive,
            )
            combo_rows_for_leg.append(row)

        by_components = {row["component_gates"]: row for row in combo_rows_for_leg}
        for row in combo_rows_for_leg:
            components = tuple(str(row["component_gates"]).split("|")) if row["component_gates"] else ()
            leave_one_rows = []
            if len(components) > 2:
                for idx in range(len(components)):
                    reduced = tuple(component for j, component in enumerate(components) if j != idx)
                    other = by_components.get("|".join(reduced))
                    if other is not None:
                        leave_one_rows.append(other)
            surface = _surface_for_combo(row, leave_one_rows)
            all_rows.append({**row, **surface})

    df_rows = pd.DataFrame(all_rows)
    df_rows.to_csv(RESULT_DIR / "score_rows.csv", index=False)
    (RESULT_DIR / "selected_structural_gates.json").write_text(json.dumps(_safe_json(selected_manifest), indent=2, sort_keys=True))
    summary = {
        "run_slug": RUN_SLUG,
        "last1_start": last1_start,
        "last2_start": last2_start,
        "period_end": end_inclusive,
        "end_exclusive": end_exclusive,
        "load_start": STRUCTURAL_LOAD_START,
        "selected_structural_gates": selected_manifest,
        "best_by_leg": {},
    }
    for hot in hot_legs:
        leg_rows = df_rows[
            (df_rows["leg"] == hot.leg.key)
            & (df_rows["stage"].isin(["oat", "combo"]))
            & (df_rows["eligible_min_fills"])
            & (df_rows["last1_net_r"] > 0)
        ].copy()
        if not leg_rows.empty:
            leg_rows = leg_rows.sort_values(["score", "last1_calmar", "last1_net_r"], ascending=False)
            summary["best_by_leg"][hot.leg.key] = leg_rows.iloc[0].to_dict()
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True))

    _write_report(
        hot_legs=hot_legs,
        rows=all_rows,
        selected_manifest=selected_manifest,
        last1_start=last1_start,
        last2_start=last2_start,
        end_inclusive=end_inclusive,
    )
    _write_asset_notes(hot_legs, all_rows, last1_start, end_inclusive)
    print(f"\nDONE: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
