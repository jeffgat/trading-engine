#!/usr/bin/env python3
"""Guarded cross-asset ORB futures surface v1 workflow.

This is a rejection-first ORB parameter research workflow for supported liquid
futures across NY, Asia, and London sessions. It deliberately separates search
from holdout/exact replay so the automation does not become a backtest
overfitting loop.

Default use:

    uv run python scripts/run_orb_autoresearch_flow.py --mode plan

Small smoke run:

    uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset seed --assets NQ --sessions NY

Larger runs require explicit caps/allowance because trial counts matter.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import (  # noqa: E402
    ASIA_SESSION,
    LDN_SESSION,
    NY_SESSION,
    SessionConfig,
    StrategyConfig,
    default_config,
)
from orb_backtest.data.instruments import get_instrument  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NO_FILL,
    TradeResult,
    build_maps,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.validate.deflated_sharpe import (  # noqa: E402
    compute_dsr,
    compute_psr,
    estimate_effective_trials,
)


DEFAULT_RUN_ID = "orb_futures_surface_v1_20260618"

DEFAULT_ASSETS = ("NQ", "ES", "CL", "GC", "SI", "RTY", "YM")
DEFAULT_SESSIONS = ("NY", "Asia", "LDN")
SESSION_TEMPLATES: dict[str, SessionConfig] = {
    "NY": NY_SESSION,
    "Asia": ASIA_SESSION,
    "LDN": LDN_SESSION,
}

DOW_EXCLUSIONS: tuple[int | None, ...] = (None, 0, 1, 2, 3, 4)
DOW_LABELS = {None: "none", 0: "no_mon", 1: "no_tue", 2: "no_wed", 3: "no_thu", 4: "no_fri"}
DOW_NAMES = {None: "None", 0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}

ATR_GATES_LIVE_NATIVE = ("none", "low_or_mid_atr", "low_atr_only")
ORB_GATES_LIVE_NATIVE = ("none", "small_or_mid_orb", "small_orb_only")
ORB_GATES_WITH_RESEARCH = (*ORB_GATES_LIVE_NATIVE, "large_orb_only")

DATA_START = "2021-01-01"
TRAIN_START = "2021-01-01"
TRAIN_END = "2023-12-31"
VALIDATION_START = "2024-01-01"
VALIDATION_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"

BASE_RISK_USD = 5000.0
BASE_ATR_LENGTH = 14
MIN_TRAIN_TRADES = 40
MIN_VALIDATION_TRADES = 8
TOP_PER_SLEEVE = 3
MAX_DEFAULT_STREAMS_PER_SLEEVE = 96
MAX_EFFECTIVE_TRIAL_ESTIMATE_SETS = 1200
STRESS_SLIPPAGE_TICKS_PER_SIDE = 2.0


@dataclass(frozen=True)
class ORBSearchSpace:
    """Bounded ORB parameter space used by the autoresearch flow."""

    orb_minutes: tuple[int, ...] = (5, 15, 30)
    stop_atr_pct: tuple[float, ...] = (10.0,)
    min_gap_atr_pct: tuple[float, ...] = (0.0,)
    rr: tuple[float, ...] = (1.0, 1.5, 2.0)
    directions: tuple[str, ...] = ("long", "short", "both")
    dow_exclusions: tuple[int | None, ...] = DOW_EXCLUSIONS
    atr_gates: tuple[str, ...] = ATR_GATES_LIVE_NATIVE
    orb_gates: tuple[str, ...] = ORB_GATES_LIVE_NATIVE

    @property
    def stream_count(self) -> int:
        return (
            len(self.orb_minutes)
            * len(self.stop_atr_pct)
            * len(self.min_gap_atr_pct)
            * len(self.rr)
            * len(self.directions)
        )

    @property
    def post_filter_count(self) -> int:
        return len(self.dow_exclusions) * len(self.atr_gates) * len(self.orb_gates)

    @property
    def raw_candidates_per_sleeve(self) -> int:
        return self.stream_count * self.post_filter_count


@dataclass(frozen=True)
class AutoresearchSpec:
    """Serializable spec for a single ORB autoresearch run."""

    run_id: str = DEFAULT_RUN_ID
    strategy: str = "orb_breakout"
    assets: tuple[str, ...] = DEFAULT_ASSETS
    sessions: tuple[str, ...] = DEFAULT_SESSIONS
    data_start: str = DATA_START
    train_start: str = TRAIN_START
    train_end: str = TRAIN_END
    validation_start: str = VALIDATION_START
    validation_end: str = VALIDATION_END
    holdout_start: str = HOLDOUT_START
    risk_usd: float = BASE_RISK_USD
    atr_length: int = BASE_ATR_LENGTH
    min_train_trades: int = MIN_TRAIN_TRADES
    min_validation_trades: int = MIN_VALIDATION_TRADES
    top_per_sleeve: int = TOP_PER_SLEEVE
    search_space: ORBSearchSpace = field(default_factory=ORBSearchSpace)
    include_holdout: bool = False
    objective_stack: tuple[str, ...] = (
        "validation_positive_edge",
        "train_validation_transfer",
        "dsr_psr",
        "annual_consistency",
        "drawdown_calmar",
        "deployability",
    )
    phase_order: tuple[str, ...] = (
        "canonical_orb_engine",
        "baseline_family_replication",
        "broad_coarse_surface",
        "module_ablations",
        "robust_cluster_promotion",
        "frozen_holdout_then_paper",
    )
    baseline_families: tuple[str, ...] = (
        "ES/NQ RTH 5/15/30 plain ORB",
        "TORB-style probe-time sweep via OR minute grid",
        "CL crude oil ORB",
        "threshold-adjusted ORB with protective ATR/OR stops",
    )
    module_ablation_order: tuple[str, ...] = (
        "stops",
        "exits",
        "confirmations",
        "filters",
        "sizing_overlays",
    )
    promotion_rules: tuple[str, ...] = (
        "Prefer neighboring parameter clusters over isolated maxima.",
        "Require train/validation transfer before any holdout read.",
        "Require PSR/DSR with explicit raw/effective trial counts.",
        "Promote only exact-replay queue candidates, not live approvals.",
        "Run 2x cost/slippage stress and no-single-year checks before paper trading.",
    )
    guardrails: tuple[str, ...] = (
        "Holdout is never opened unless --open-holdout is passed.",
        "Search space is fixed before run artifacts are written.",
        "Trial counts are reported per sleeve and globally.",
        "Large sleeves use bounded deterministic effective-trial estimation and report the approximation metadata.",
        "Candidates with large_orb_only are post_filter_only unless live min-ORB support exists.",
        "Promotion output is exact-replay queue only, not live deployment.",
    )

    @property
    def sleeve_count(self) -> int:
        return len(self.assets) * len(self.sessions)

    @property
    def raw_candidate_count(self) -> int:
        return self.sleeve_count * self.search_space.raw_candidates_per_sleeve


@dataclass(frozen=True)
class ORBAutoresearchRule:
    """One searched ORB rule, including native params and causal gates."""

    asset: str
    session: str
    orb_minutes: int
    stop_atr_pct: float
    min_gap_atr_pct: float
    rr: float
    direction: str
    excluded_dow: int | None
    atr_gate: str
    orb_gate: str

    @property
    def rule_id(self) -> str:
        parts = [
            self.asset.lower(),
            self.session.lower(),
            f"orb{self.orb_minutes}",
            f"stop{_slug_num(self.stop_atr_pct)}",
            f"gap{_slug_num(self.min_gap_atr_pct)}",
            f"rr{_slug_num(self.rr)}",
            self.direction,
            DOW_LABELS[self.excluded_dow],
        ]
        if self.atr_gate != "none":
            parts.append(self.atr_gate)
        if self.orb_gate != "none":
            parts.append(self.orb_gate)
        return "__".join(parts)

    @property
    def stream_key(self) -> tuple[int, float, float, float, str]:
        return (self.orb_minutes, self.stop_atr_pct, self.min_gap_atr_pct, self.rr, self.direction)

    @property
    def excluded_days_tuple(self) -> tuple[int, ...]:
        return () if self.excluded_dow is None else (self.excluded_dow,)

    @property
    def native_supported(self) -> bool:
        return self.orb_gate != "large_orb_only"

    @property
    def deployability(self) -> str:
        return "live_native" if self.native_supported else "post_filter_only"

    @property
    def live_support_notes(self) -> str:
        if self.native_supported:
            return (
                "ORB window, stop/gap ATR params, RR, direction, DOW exclusion, "
                "max prior rolling ATR, and max ORB range are StrategyConfig/live-config expressible."
            )
        return "large_orb_only is a causal research filter but needs native min_orb_range_pct support."


def _slug_num(value: float) -> str:
    text = f"{value:g}".replace(".", "p")
    return text.replace("-", "m")


def _result_dir(spec: AutoresearchSpec) -> Path:
    return ROOT / "data" / "results" / spec.run_id


def _report_path(spec: AutoresearchSpec) -> Path:
    return ROOT / "learnings" / "reports" / f"{spec.run_id.upper()}.md"


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if math.isnan(float(value)):
            return None
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_float_tuple(value: str | None, default: tuple[float, ...]) -> tuple[float, ...]:
    if not value:
        return default
    return tuple(float(part.strip()) for part in value.split(",") if part.strip())


def _parse_int_tuple(value: str | None, default: tuple[int, ...]) -> tuple[int, ...]:
    if not value:
        return default
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def _preset_space(name: str, *, include_post_filter_only: bool, strategy: str) -> ORBSearchSpace:
    orb_gates = ORB_GATES_WITH_RESEARCH if include_post_filter_only else ORB_GATES_LIVE_NATIVE
    is_plain_orb = strategy == "orb_breakout"
    if name == "seed":
        return ORBSearchSpace(
            orb_minutes=(5, 15, 30),
            stop_atr_pct=(10.0,),
            min_gap_atr_pct=(0.0,) if is_plain_orb else (2.0,),
            rr=(1.0, 1.5, 2.0),
            directions=("long", "short", "both"),
            orb_gates=orb_gates,
        )
    if name == "broad":
        return ORBSearchSpace(
            orb_minutes=(5, 15, 30),
            stop_atr_pct=(5.0, 7.5, 10.0, 12.5),
            min_gap_atr_pct=(0.0,) if is_plain_orb else (1.0, 2.0, 3.0),
            rr=(1.0, 1.25, 1.5, 2.0, 2.5),
            directions=("long", "short", "both"),
            dow_exclusions=DOW_EXCLUSIONS,
            atr_gates=ATR_GATES_LIVE_NATIVE,
            orb_gates=orb_gates,
        )
    raise ValueError(f"Unknown preset: {name}")


def _data_file_for(symbol: str) -> Path:
    if symbol == "NQ":
        return ROOT / "data" / "cache" / "nq_ny_lsi_cisd_sequence" / "NQ_5m.parquet"
    return ROOT / "data" / "raw" / f"{symbol}_5m.parquet"


def _load_asset_data(symbol: str, start: str) -> tuple[Path, pd.DataFrame, pd.DataFrame | None]:
    data_file = _data_file_for(symbol)
    df = load_5m_data(str(data_file), start=start)
    try:
        df_1m = load_1m_for_5m(str(data_file), start=start)
    except FileNotFoundError:
        df_1m = None
    return data_file, df, df_1m


def _add_minutes(time_text: str, minutes: int) -> str:
    base = datetime.strptime(time_text, "%H:%M")
    return (base + timedelta(minutes=minutes)).strftime("%H:%M")


def _base_session(session_name: str, rule: ORBAutoresearchRule | None = None) -> SessionConfig:
    template = SESSION_TEMPLATES[session_name]
    if rule is None:
        return replace(template, max_prior_rolling_atr_pct=0.0, max_orb_range_pct=0.0)
    orb_end = _add_minutes(template.orb_start, rule.orb_minutes)
    return replace(
        template,
        orb_end=orb_end,
        entry_start=orb_end,
        stop_atr_pct=rule.stop_atr_pct,
        min_gap_atr_pct=rule.min_gap_atr_pct,
        max_prior_rolling_atr_pct=0.0,
        max_orb_range_pct=0.0,
    )


def _threshold_value(thresholds: dict[str, float], gate: str, kind: str) -> float:
    if kind == "atr":
        if gate == "low_or_mid_atr":
            return thresholds["atr_p66"]
        if gate == "low_atr_only":
            return thresholds["atr_p33"]
    if kind == "orb":
        if gate == "small_or_mid_orb":
            return thresholds["orb_p66"]
        if gate == "small_orb_only":
            return thresholds["orb_p33"]
    return 0.0


def _config_for_rule(rule: ORBAutoresearchRule, spec: AutoresearchSpec, thresholds: dict[str, float] | None = None) -> StrategyConfig:
    inst = get_instrument(rule.asset)
    session = _base_session(rule.session, rule)
    if thresholds and rule.native_supported:
        session = replace(
            session,
            max_prior_rolling_atr_pct=_threshold_value(thresholds, rule.atr_gate, "atr"),
            max_orb_range_pct=_threshold_value(thresholds, rule.orb_gate, "orb"),
        )
    cfg = default_config(inst)
    return replace(
        cfg,
        sessions=(session,),
        risk_usd=spec.risk_usd,
        rr=rule.rr,
        tp1_ratio=1.0,
        exit_mode="single_target",
        atr_length=spec.atr_length,
        strategy=spec.strategy,
        direction_filter=rule.direction,
        excluded_days=rule.excluded_days_tuple,
        continuation_fvg_selection="first",
        orb_breakout_trigger="touch",
        orb_trade_max_per_session=1,
        impulse_close_filter=False,
        use_bar_magnifier=True,
        name=rule.rule_id,
    )


def _stream_config(
    asset: str,
    session: str,
    orb_minutes: int,
    stop_atr_pct: float,
    min_gap_atr_pct: float,
    rr: float,
    direction: str,
    spec: AutoresearchSpec,
) -> StrategyConfig:
    rule = ORBAutoresearchRule(
        asset=asset,
        session=session,
        orb_minutes=orb_minutes,
        stop_atr_pct=stop_atr_pct,
        min_gap_atr_pct=min_gap_atr_pct,
        rr=rr,
        direction=direction,
        excluded_dow=None,
        atr_gate="none",
        orb_gate="none",
    )
    return _config_for_rule(rule, spec)


def _session_context(
    df: pd.DataFrame,
    session_name: str,
    orb_minutes: int,
    *,
    calibration_start: str,
    calibration_end: str,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    daily = (
        df.resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
        .copy()
    )
    prev_close = daily["close"].shift(1)
    true_range = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily["atr14"] = true_range.rolling(BASE_ATR_LENGTH, min_periods=BASE_ATR_LENGTH).mean()
    daily["prior_atr14_pct"] = (daily["atr14"] / daily["close"] * 100.0).shift(1)
    daily["date"] = daily.index.date

    template = SESSION_TEMPLATES[session_name]
    start_t = pd.Timestamp(template.orb_start).time()
    end_t = pd.Timestamp(_add_minutes(template.orb_start, orb_minutes)).time()
    times = df.index.time
    if start_t < end_t:
        mask = [(t >= start_t and t < end_t) for t in times]
    else:
        mask = [(t >= start_t or t < end_t) for t in times]
    intraday = df.loc[mask]

    orb_rows: list[dict[str, Any]] = []
    for session_date, group in intraday.groupby(intraday.index.date):
        if group.empty:
            continue
        orb_open = float(group["open"].iloc[0])
        if not np.isfinite(orb_open) or orb_open <= 0:
            continue
        orb_high = float(group["high"].max())
        orb_low = float(group["low"].min())
        orb_rows.append({"date": session_date, "orb_range_pct": (orb_high - orb_low) / orb_open * 100.0})
    orb = pd.DataFrame(orb_rows)
    context = daily[["date", "prior_atr14_pct"]].merge(orb, on="date", how="left")

    start_date = datetime.fromisoformat(calibration_start).date()
    end_date = datetime.fromisoformat(calibration_end).date()
    calibration = context[(context["date"] >= start_date) & (context["date"] <= end_date)]
    thresholds = {
        "atr_p33": float(calibration["prior_atr14_pct"].quantile(1 / 3)),
        "atr_p66": float(calibration["prior_atr14_pct"].quantile(2 / 3)),
        "orb_p33": float(calibration["orb_range_pct"].quantile(1 / 3)),
        "orb_p66": float(calibration["orb_range_pct"].quantile(2 / 3)),
    }
    atr_by_date = {
        d.isoformat(): float(v)
        for d, v in zip(context["date"], context["prior_atr14_pct"], strict=False)
        if pd.notna(v)
    }
    orb_by_date = {
        d.isoformat(): float(v)
        for d, v in zip(context["date"], context["orb_range_pct"], strict=False)
        if pd.notna(v)
    }
    return thresholds, atr_by_date, orb_by_date


def _period_trades(trades: list[TradeResult], start: str, end: str | None) -> list[TradeResult]:
    if end is None:
        return [trade for trade in trades if trade.date >= start]
    return [trade for trade in trades if start <= trade.date <= end]


def _filled(trades: list[TradeResult]) -> list[TradeResult]:
    return [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]


def _r_multiples(trades: list[TradeResult]) -> np.ndarray:
    return np.asarray(
        [
            float(getattr(trade, "net_r_multiple", 0.0) or trade.r_multiple)
            for trade in trades
            if trade.exit_type != EXIT_NO_FILL
        ],
        dtype=float,
    )


def _trade_dates(trades: list[TradeResult]) -> set[str]:
    return {trade.date for trade in trades if trade.exit_type != EXIT_NO_FILL}


def _estimate_effective_trials_bounded(
    trade_date_sets: list[set[str]],
    *,
    max_sets: int = MAX_EFFECTIVE_TRIAL_ESTIMATE_SETS,
) -> tuple[int, dict[str, Any]]:
    """Estimate effective trials without letting broad grids become quadratic.

    ``estimate_effective_trials`` is exact enough for small grids, but its
    greedy overlap clustering can become expensive once a sleeve expands into
    tens of thousands of post-filter variants. For large sleeves, sample the
    frozen candidate order deterministically and scale the sampled effective
    count by the same ratio as the raw sleeve size.
    """

    n_raw = len(trade_date_sets)
    if n_raw <= max_sets:
        effective = estimate_effective_trials(trade_date_sets)
        return effective, {
            "method": "full",
            "raw_sets": n_raw,
            "sampled_sets": n_raw,
            "sample_effective_sets": effective,
            "scaled_effective_sets": effective,
            "max_sets": max_sets,
        }

    step = max(1, math.ceil(n_raw / max_sets))
    sampled = trade_date_sets[::step][:max_sets]
    sample_effective = estimate_effective_trials(sampled)
    scaled_effective = min(
        n_raw,
        max(sample_effective, int(math.ceil(sample_effective * n_raw / max(len(sampled), 1)))),
    )
    return scaled_effective, {
        "method": "deterministic_stride_scaled",
        "raw_sets": n_raw,
        "sampled_sets": len(sampled),
        "sample_effective_sets": sample_effective,
        "scaled_effective_sets": scaled_effective,
        "stride": step,
        "max_sets": max_sets,
    }


def _passes_gate(
    trade: TradeResult,
    rule: ORBAutoresearchRule,
    thresholds: dict[str, float],
    atr_by_date: dict[str, float],
    orb_by_date: dict[str, float],
) -> bool:
    if rule.excluded_dow is not None and datetime.strptime(trade.date, "%Y-%m-%d").weekday() == rule.excluded_dow:
        return False

    atr_value = atr_by_date.get(trade.date)
    if rule.atr_gate != "none":
        if atr_value is None or not np.isfinite(atr_value):
            return False
        if rule.atr_gate == "low_or_mid_atr" and atr_value > thresholds["atr_p66"]:
            return False
        if rule.atr_gate == "low_atr_only" and atr_value > thresholds["atr_p33"]:
            return False

    orb_value = orb_by_date.get(trade.date)
    if rule.orb_gate != "none":
        if orb_value is None or not np.isfinite(orb_value):
            return False
        if rule.orb_gate == "small_or_mid_orb" and orb_value > thresholds["orb_p66"]:
            return False
        if rule.orb_gate == "small_orb_only" and orb_value > thresholds["orb_p33"]:
            return False
        if rule.orb_gate == "large_orb_only" and orb_value <= thresholds["orb_p66"]:
            return False

    return True


def _apply_rule(
    trades: list[TradeResult],
    rule: ORBAutoresearchRule,
    thresholds: dict[str, float],
    atr_by_date: dict[str, float],
    orb_by_date: dict[str, float],
) -> list[TradeResult]:
    return [trade for trade in trades if _passes_gate(trade, rule, thresholds, atr_by_date, orb_by_date)]


def _r_by_month(trades: list[TradeResult]) -> dict[str, float]:
    rows = defaultdict(float)
    for trade in _filled(trades):
        rows[trade.date[:7]] += float(getattr(trade, "net_r_multiple", 0.0) or trade.r_multiple)
    return {key: round(value, 4) for key, value in rows.items()}


def _metrics_summary(trades: list[TradeResult], *, years: tuple[int, ...]) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    r_values = _r_multiples(trades)
    psr = compute_psr(r_values)
    r_by_year = {str(year): round(float(metrics.get("r_by_year", {}).get(str(year), 0.0)), 4) for year in years}
    month_r = _r_by_month(trades)
    return {
        "total_trades": int(metrics.get("total_trades", 0)),
        "total_r": round(float(metrics.get("total_r", 0.0)), 4),
        "avg_r": round(float(metrics.get("avg_r", 0.0)), 4),
        "win_rate_pct": round(float(metrics.get("win_rate", 0.0)) * 100.0, 2),
        "profit_factor": round(float(metrics.get("profit_factor", 0.0)), 4),
        "max_drawdown_r": round(float(metrics.get("max_drawdown_r", 0.0)), 4),
        "calmar": round(float(metrics.get("calmar_ratio", 0.0)), 4),
        "sharpe": round(float(metrics.get("sharpe_ratio", 0.0)), 4),
        "max_consecutive_losses": int(metrics.get("max_consecutive_losses", 0)),
        "r_by_year": r_by_year,
        "positive_years": int(sum(1 for value in r_by_year.values() if value > 0)),
        "min_year_r": round(min(r_by_year.values()) if r_by_year else 0.0, 4),
        "worst_month_r": round(min(month_r.values()) if month_r else 0.0, 4),
        "psr": psr.psr,
        "observed_sharpe_psr": psr.observed_sharpe,
    }


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses <= 0:
        return math.inf if wins > 0 else 0.0
    return wins / losses


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _stress_metrics(
    trades: list[TradeResult],
    *,
    min_tick: float,
    years: tuple[int, ...],
) -> dict[str, Any]:
    """Revalue trades with doubled commission and adverse slippage.

    Base ``net_r_multiple`` already includes one commission pass. The stress
    subtracts one more commission haircut, plus a round trip of adverse slippage.
    """

    values_by_year = {str(year): 0.0 for year in years}
    values: list[float] = []
    for trade in _filled(trades):
        if trade.risk_points <= 0:
            continue
        base_net_r = float(trade.net_r_multiple or trade.r_multiple)
        commission_haircut_r = max(0.0, float(trade.r_multiple) - base_net_r)
        slippage_haircut_r = (2.0 * STRESS_SLIPPAGE_TICKS_PER_SIDE * min_tick) / float(trade.risk_points)
        stressed_r = base_net_r - commission_haircut_r - slippage_haircut_r
        values.append(stressed_r)
        year = trade.date[:4]
        if year in values_by_year:
            values_by_year[year] += stressed_r

    total_r = float(sum(values))
    max_dd = _max_drawdown(values)
    r_by_year = {year: round(value, 4) for year, value in values_by_year.items()}
    return {
        "stress_name": f"2x_commission_plus_{STRESS_SLIPPAGE_TICKS_PER_SIDE:g}_ticks_per_side",
        "slippage_ticks_per_side": STRESS_SLIPPAGE_TICKS_PER_SIDE,
        "total_trades": len(values),
        "total_r": round(total_r, 4),
        "profit_factor": round(float(_profit_factor(values)), 4),
        "max_drawdown_r": round(max_dd, 4),
        "calmar": round(total_r / abs(max_dd), 4) if max_dd < 0 else (math.inf if total_r > 0 else 0.0),
        "r_by_year": r_by_year,
        "positive_years": int(sum(1 for value in r_by_year.values() if value > 0)),
        "min_year_r": round(min(r_by_year.values()) if r_by_year else 0.0, 4),
    }


def _no_single_year_dependency(metrics: dict[str, Any]) -> bool:
    r_by_year = [float(value) for value in metrics.get("r_by_year", {}).values()]
    total_r = float(metrics.get("total_r", 0.0))
    if total_r <= 0 or not r_by_year:
        return False
    return (total_r - max(r_by_year)) > 0 and sum(1 for value in r_by_year if value > 0) >= 3


def _build_rules(asset: str, session: str, space: ORBSearchSpace) -> list[ORBAutoresearchRule]:
    return [
        ORBAutoresearchRule(
            asset=asset,
            session=session,
            orb_minutes=orb_minutes,
            stop_atr_pct=stop_atr_pct,
            min_gap_atr_pct=min_gap_atr_pct,
            rr=rr,
            direction=direction,
            excluded_dow=dow,
            atr_gate=atr_gate,
            orb_gate=orb_gate,
        )
        for orb_minutes in space.orb_minutes
        for stop_atr_pct in space.stop_atr_pct
        for min_gap_atr_pct in space.min_gap_atr_pct
        for rr in space.rr
        for direction in space.directions
        for dow in space.dow_exclusions
        for atr_gate in space.atr_gates
        for orb_gate in space.orb_gates
    ]


def _stream_keys(space: ORBSearchSpace) -> list[tuple[int, float, float, float, str]]:
    return [
        (orb_minutes, stop_atr_pct, min_gap_atr_pct, rr, direction)
        for orb_minutes in space.orb_minutes
        for stop_atr_pct in space.stop_atr_pct
        for min_gap_atr_pct in space.min_gap_atr_pct
        for rr in space.rr
        for direction in space.directions
    ]


def _score_key(row: dict[str, Any], spec: AutoresearchSpec) -> tuple:
    train = row["train_metrics"]
    validation = row["validation_metrics"]
    combined = row["preholdout_metrics"]
    validation_ok = (
        validation["total_trades"] >= spec.min_validation_trades
        and validation["total_r"] > 0
        and validation["profit_factor"] > 1.0
    )
    train_ok = (
        train["total_trades"] >= spec.min_train_trades
        and train["total_r"] > 0
        and train["profit_factor"] > 1.0
    )
    transfer = validation["total_r"] / abs(train["max_drawdown_r"] or -1.0)
    return (
        int(row["deployability"] == "live_native"),
        int(train_ok),
        int(validation_ok),
        int(row["dsr"] >= 0.5),
        int(row.get("cluster_score", 0.0) >= 0.4),
        int(row.get("cost_slippage_stress_pass", False)),
        int(row.get("no_single_year_dependency", False)),
        row.get("cluster_score", 0.0),
        combined["positive_years"],
        validation["total_r"],
        validation["profit_factor"],
        transfer,
        -abs(combined["max_drawdown_r"]),
        combined["calmar"],
        combined["total_r"],
    )


def _verdict(row: dict[str, Any], spec: AutoresearchSpec) -> str:
    train = row["train_metrics"]
    validation = row["validation_metrics"]
    combined = row["preholdout_metrics"]
    live_native = row["deployability"] == "live_native"
    train_ok = train["total_trades"] >= spec.min_train_trades and train["total_r"] > 0 and train["profit_factor"] > 1.0
    validation_ok = (
        validation["total_trades"] >= spec.min_validation_trades
        and validation["total_r"] > 0
        and validation["profit_factor"] > 1.0
    )
    deflated_ok = row["dsr"] >= 0.5 and combined["psr"] >= 0.85
    cluster_ok = row.get("cluster_score", 0.0) >= 0.4
    stress_ok = bool(row.get("cost_slippage_stress_pass", False))
    no_single_year_dependency = bool(row.get("no_single_year_dependency", False))
    if live_native and train_ok and validation_ok and deflated_ok and cluster_ok and stress_ok and no_single_year_dependency:
        return "PROMOTE_TO_EXACT_REPLAY_QUEUE"
    if live_native and train_ok and validation_ok and cluster_ok and stress_ok and no_single_year_dependency:
        return "CHALLENGER"
    if not live_native and train_ok and validation_ok and cluster_ok and stress_ok and no_single_year_dependency:
        return "IMPLEMENTATION_REQUIRED"
    return "REJECT"


def _cluster_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["orb_minutes"],
        row["stop_atr_pct"],
        row["min_gap_atr_pct"],
        row["rr"],
        row["direction"],
        row["excluded_dow"],
        row["atr_gate"],
        row["orb_gate"],
    )


def _row_good_for_cluster(row: dict[str, Any], spec: AutoresearchSpec) -> bool:
    train = row["train_metrics"]
    validation = row["validation_metrics"]
    return (
        train["total_trades"] >= spec.min_train_trades
        and train["total_r"] > 0
        and train["profit_factor"] > 1.0
        and validation["total_trades"] >= spec.min_validation_trades
        and validation["total_r"] > 0
        and validation["profit_factor"] > 1.0
    )


def _neighbor_values(values: tuple[Any, ...], value: Any) -> list[Any]:
    ordered = list(values)
    try:
        index = ordered.index(value)
    except ValueError:
        return []
    neighbors = []
    for neighbor_index in (index - 1, index + 1):
        if 0 <= neighbor_index < len(ordered):
            neighbors.append(ordered[neighbor_index])
    return neighbors


def _assign_cluster_scores(rows: list[dict[str, Any]], space: ORBSearchSpace, spec: AutoresearchSpec) -> None:
    by_key = {_cluster_key(row): row for row in rows}
    numeric_axes = {
        "orb_minutes": space.orb_minutes,
        "stop_atr_pct": space.stop_atr_pct,
        "min_gap_atr_pct": space.min_gap_atr_pct,
        "rr": space.rr,
    }
    for row in rows:
        neighbor_rows = []
        for axis, values in numeric_axes.items():
            if len(values) <= 1:
                continue
            for neighbor_value in _neighbor_values(values, row[axis]):
                probe = dict(row)
                probe[axis] = neighbor_value
                neighbor = by_key.get(_cluster_key(probe))
                if neighbor is not None:
                    neighbor_rows.append(neighbor)
        if not neighbor_rows:
            row["cluster_score"] = 1.0
            row["cluster_neighbor_count"] = 0
            row["cluster_good_neighbor_count"] = 0
            continue
        good = sum(1 for neighbor in neighbor_rows if _row_good_for_cluster(neighbor, spec))
        row["cluster_score"] = round(good / len(neighbor_rows), 4)
        row["cluster_neighbor_count"] = len(neighbor_rows)
        row["cluster_good_neighbor_count"] = good


def _evaluate_sleeve(
    spec: AutoresearchSpec,
    asset: str,
    session_name: str,
    df: pd.DataFrame,
    df_1m: pd.DataFrame | None,
) -> dict[str, Any]:
    space = spec.search_space
    contexts = {
        orb_minutes: _session_context(
            df,
            session_name,
            orb_minutes,
            calibration_start=spec.train_start,
            calibration_end=spec.train_end,
        )
        for orb_minutes in space.orb_minutes
    }
    stream_configs = {
        key: _stream_config(asset, session_name, *key, spec=spec)
        for key in _stream_keys(space)
    }
    maps = build_maps(df, df_1m=df_1m)
    cache = build_signal_cache(df, list(stream_configs.values()), signal_df_1m=df_1m)
    streams: dict[tuple[int, float, float, float, str], list[TradeResult]] = {}
    run_end = None if spec.include_holdout else spec.validation_end
    for key, cfg in stream_configs.items():
        trades = run_backtest(
            df,
            cfg,
            start_date=spec.train_start,
            end_date=run_end,
            df_1m=df_1m,
            signal_df_1m=df_1m,
            _maps=maps,
            _signal_cache=cache,
        )
        streams[key] = trades

    rows: list[dict[str, Any]] = []
    trade_date_sets: list[set[str]] = []
    preholdout_by_rule: dict[str, list[TradeResult]] = {}
    rules = _build_rules(asset, session_name, space)
    for rule in rules:
        thresholds, atr_by_date, orb_by_date = contexts[rule.orb_minutes]
        candidate_trades = _apply_rule(streams[rule.stream_key], rule, thresholds, atr_by_date, orb_by_date)
        train_trades = _period_trades(candidate_trades, spec.train_start, spec.train_end)
        validation_trades = _period_trades(candidate_trades, spec.validation_start, spec.validation_end)
        preholdout_trades = _period_trades(candidate_trades, spec.train_start, spec.validation_end)
        holdout_trades = _period_trades(candidate_trades, spec.holdout_start, None) if spec.include_holdout else []
        preholdout_metrics = _metrics_summary(preholdout_trades, years=(2021, 2022, 2023, 2024))
        stress_metrics = _stress_metrics(
            preholdout_trades,
            min_tick=get_instrument(asset).min_tick,
            years=(2021, 2022, 2023, 2024),
        )
        preholdout_by_rule[rule.rule_id] = preholdout_trades
        trade_date_sets.append(_trade_dates(preholdout_trades))
        row = {
            "asset": asset,
            "session": session_name,
            "rule_id": rule.rule_id,
            "orb_minutes": rule.orb_minutes,
            "stop_atr_pct": rule.stop_atr_pct,
            "min_gap_atr_pct": rule.min_gap_atr_pct,
            "rr": rule.rr,
            "direction": rule.direction,
            "excluded_dow": DOW_NAMES[rule.excluded_dow],
            "atr_gate": rule.atr_gate,
            "orb_gate": rule.orb_gate,
            "deployability": rule.deployability,
            "live_support_notes": rule.live_support_notes,
            "exact_replay_required": True,
            "train_metrics": _metrics_summary(train_trades, years=(2021, 2022, 2023)),
            "validation_metrics": _metrics_summary(validation_trades, years=(2024,)),
            "preholdout_metrics": preholdout_metrics,
            "stress_metrics": stress_metrics,
            "cost_slippage_stress_pass": (
                stress_metrics["total_trades"] >= spec.min_train_trades + spec.min_validation_trades
                and stress_metrics["total_r"] > 0
                and stress_metrics["profit_factor"] > 1.0
                and stress_metrics["min_year_r"] >= 0
            ),
            "no_single_year_dependency": _no_single_year_dependency(preholdout_metrics),
            "holdout_metrics": _metrics_summary(holdout_trades, years=(2025, 2026)) if spec.include_holdout else None,
        }
        rows.append(row)

    _assign_cluster_scores(rows, space, spec)
    n_trials_raw = len(rows)
    n_trials_effective, effective_trial_estimation = _estimate_effective_trials_bounded(trade_date_sets)
    for row in rows:
        dsr = compute_dsr(
            _r_multiples(preholdout_by_rule[row["rule_id"]]),
            n_trials_raw=n_trials_raw,
            n_trials_effective=n_trials_effective,
        )
        row["dsr"] = dsr.dsr
        row["expected_max_sharpe"] = dsr.expected_max_sharpe
        row["n_trials_raw"] = n_trials_raw
        row["n_trials_effective"] = n_trials_effective
        row["verdict"] = _verdict(row, spec)

    ranked = sorted(rows, key=lambda row: _score_key(row, spec), reverse=True)
    top = ranked[: spec.top_per_sleeve]
    return {
        "asset": asset,
        "session": session_name,
        "data": {
            "rows_5m": int(len(df)),
            "has_1m": df_1m is not None,
            "latest": df.index.max().date().isoformat() if len(df) else None,
        },
        "trial_counts": {
            "stream_configs": space.stream_count,
            "post_filter_configs": space.post_filter_count,
            "raw_candidates": n_trials_raw,
            "effective_candidates": n_trials_effective,
            "effective_trial_estimation": effective_trial_estimation,
        },
        "thresholds_by_orb_minutes": {str(k): v[0] for k, v in contexts.items()},
        "all_rows": rows,
        "top": top,
    }


def _flatten(row: dict[str, Any], rank: int | None = None) -> dict[str, Any]:
    train = row["train_metrics"]
    validation = row["validation_metrics"]
    combined = row["preholdout_metrics"]
    stress = row["stress_metrics"]
    holdout = row.get("holdout_metrics") or {}
    return {
        "rank": rank,
        "asset": row["asset"],
        "session": row["session"],
        "rule_id": row["rule_id"],
        "verdict": row["verdict"],
        "deployability": row["deployability"],
        "orb_minutes": row["orb_minutes"],
        "stop_atr_pct": row["stop_atr_pct"],
        "min_gap_atr_pct": row["min_gap_atr_pct"],
        "rr": row["rr"],
        "direction": row["direction"],
        "excluded_dow": row["excluded_dow"],
        "atr_gate": row["atr_gate"],
        "orb_gate": row["orb_gate"],
        "train_trades": train["total_trades"],
        "train_r": train["total_r"],
        "train_pf": train["profit_factor"],
        "train_dd_r": train["max_drawdown_r"],
        "validation_trades": validation["total_trades"],
        "validation_r": validation["total_r"],
        "validation_pf": validation["profit_factor"],
        "validation_dd_r": validation["max_drawdown_r"],
        "preholdout_trades": combined["total_trades"],
        "preholdout_r": combined["total_r"],
        "preholdout_pf": combined["profit_factor"],
        "preholdout_dd_r": combined["max_drawdown_r"],
        "preholdout_calmar": combined["calmar"],
        "positive_years": combined["positive_years"],
        "cluster_score": row.get("cluster_score"),
        "cluster_neighbor_count": row.get("cluster_neighbor_count"),
        "cluster_good_neighbor_count": row.get("cluster_good_neighbor_count"),
        "stress_name": stress["stress_name"],
        "stress_total_r": stress["total_r"],
        "stress_pf": stress["profit_factor"],
        "stress_min_year_r": stress["min_year_r"],
        "cost_slippage_stress_pass": row.get("cost_slippage_stress_pass"),
        "no_single_year_dependency": row.get("no_single_year_dependency"),
        "psr": combined["psr"],
        "dsr": row["dsr"],
        "holdout_trades": holdout.get("total_trades"),
        "holdout_r": holdout.get("total_r"),
        "holdout_pf": holdout.get("profit_factor"),
        "exact_replay_required": row["exact_replay_required"],
    }


def _markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = []
        for _, key in columns:
            value = row.get(key)
            if value is None:
                values.append("")
            elif isinstance(value, float):
                values.append(f"{value:.2f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _plan_rows(spec: AutoresearchSpec) -> list[dict[str, Any]]:
    return [
        {
            "asset": asset,
            "session": session,
            "stream_configs": spec.search_space.stream_count,
            "post_filters": spec.search_space.post_filter_count,
            "raw_candidates": spec.search_space.raw_candidates_per_sleeve,
        }
        for asset in spec.assets
        for session in spec.sessions
    ]


def _render_plan_report(spec: AutoresearchSpec) -> str:
    plan_rows = _plan_rows(spec)
    cols = [
        ("Asset", "asset"),
        ("Session", "session"),
        ("Streams", "stream_configs"),
        ("Post Filters", "post_filters"),
        ("Raw Candidates", "raw_candidates"),
    ]
    return "\n".join(
        [
            "# ORB Futures Surface v1 Plan",
            "",
            "## Purpose",
            "",
            (
                "This is a guarded autoresearch flow for ORB futures surface parameters across "
                f"`{list(spec.assets)}` and `{list(spec.sessions)}`. It is designed as a "
                "rejection engine: broad search is allowed, but promotion requires validation, "
                "deflated metrics, deployability labels, and exact replay."
            ),
            "",
            "## Frozen Spec",
            "",
            f"- Strategy: `{spec.strategy}`",
            f"- Train: `{spec.train_start}` to `{spec.train_end}`",
            f"- Validation: `{spec.validation_start}` to `{spec.validation_end}`",
            f"- Holdout: `{spec.holdout_start}` onward; opened in this run: `{spec.include_holdout}`",
            f"- Search streams per sleeve: `{spec.search_space.stream_count}`",
            f"- Post-filter variants per stream: `{spec.search_space.post_filter_count}`",
            f"- Raw candidates per sleeve: `{spec.search_space.raw_candidates_per_sleeve}`",
            f"- Total raw candidates: `{spec.raw_candidate_count}`",
            "",
            "## Implementation Order",
            "",
            *[f"{index}. {item}" for index, item in enumerate(spec.phase_order, start=1)],
            "",
            "## Baseline Families",
            "",
            *[f"- {item}" for item in spec.baseline_families],
            "",
            "## Module Ablation Order",
            "",
            *[f"- {item}" for item in spec.module_ablation_order],
            "",
            "## Promotion Rules",
            "",
            *[f"- {item}" for item in spec.promotion_rules],
            "",
            "## Search Space",
            "",
            f"- ORB minutes: `{list(spec.search_space.orb_minutes)}`",
            f"- Stop ATR%: `{list(spec.search_space.stop_atr_pct)}`",
            f"- Min gap ATR%: `{list(spec.search_space.min_gap_atr_pct)}`",
            f"- RR: `{list(spec.search_space.rr)}`",
            f"- Directions: `{list(spec.search_space.directions)}`",
            f"- DOW exclusions: `{[DOW_LABELS[d] for d in spec.search_space.dow_exclusions]}`",
            f"- ATR gates: `{list(spec.search_space.atr_gates)}`",
            f"- ORB gates: `{list(spec.search_space.orb_gates)}`",
            "",
            "## Guardrails",
            "",
            *[f"- {item}" for item in spec.guardrails],
            "",
            "## Sleeve Trial Budget",
            "",
            _markdown_table(plan_rows, cols),
            "",
            "## Commands",
            "",
            "```bash",
            "cd backtesting",
            "uv run python scripts/run_orb_autoresearch_flow.py --mode plan --preset broad",
            "uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset seed --assets NQ --sessions NY",
            "uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset seed --strategy continuation --assets NQ --sessions NY",
            "uv run python scripts/run_orb_autoresearch_flow.py --mode run --preset broad --allow-large-run",
            "```",
            "",
        ]
    )


def _render_run_report(payload: dict[str, Any]) -> str:
    spec = payload["spec"]
    result_dir = Path(payload["result_dir"])
    top_rows = payload["top_candidates"]
    cols = [
        ("Asset", "asset"),
        ("Sess", "session"),
        ("Rank", "rank"),
        ("Verdict", "verdict"),
        ("Rule", "rule_id"),
        ("Val R", "validation_r"),
        ("Val PF", "validation_pf"),
        ("Pre R", "preholdout_r"),
        ("Pre DD", "preholdout_dd_r"),
        ("Cal", "preholdout_calmar"),
        ("Cluster", "cluster_score"),
        ("Stress", "cost_slippage_stress_pass"),
        ("No1Yr", "no_single_year_dependency"),
        ("DSR", "dsr"),
        ("Dep", "deployability"),
    ]
    return "\n".join(
        [
            "# ORB Futures Surface v1 Results",
            "",
            "## Executive Read",
            "",
            (
                f"Ran `{payload['run_id']}` with train `{spec['train_start']}`-`{spec['train_end']}` "
                f"and validation `{spec['validation_start']}`-`{spec['validation_end']}`. "
                f"Strategy `{spec['strategy']}`. Holdout opened: `{spec['include_holdout']}`."
            ),
            "",
            f"- Sleeves evaluated: `{len(payload['sleeve_reports'])}`",
            f"- Raw candidates evaluated: `{payload['raw_candidates_evaluated']}`",
            f"- Top candidates emitted: `{len(top_rows)}`",
            "",
            "## Top Candidates",
            "",
            _markdown_table(top_rows, cols),
            "",
            "## Method Notes",
            "",
            "- Ranking uses validation transfer first, neighboring-parameter cluster support, deflated metrics, annual consistency, drawdown, Calmar, and deployability.",
            "- Plain `orb_breakout` uses completed OR levels directly; `continuation` keeps the older ORB+FVG confirmation lineage.",
            f"- Stress gate revalues preholdout trades with doubled commission plus `{STRESS_SLIPPAGE_TICKS_PER_SIDE:g}` adverse ticks per side.",
            "- No-single-year gate requires positive preholdout R after removing the best year.",
            "- `PROMOTE_TO_EXACT_REPLAY_QUEUE` is a queue label, not a live/dry-run recommendation.",
            "- The default gate set is live-native only. Use `--include-post-filter-only` to allow research-only large-ORB lower-bound ideas.",
            "- Large sleeves use bounded deterministic effective-trial estimation; see each sleeve's `trial_counts.effective_trial_estimation` in `summary.json`.",
            "- PBO/CSCV is not implemented here; PSR/DSR/effective trial counts are used as the available Bailey-style guardrail.",
            "",
            "## Artifacts",
            "",
            f"- `{result_dir / 'spec.json'}`",
            f"- `{result_dir / 'all_candidates.csv'}`",
            f"- `{result_dir / 'top_candidates.csv'}`",
            f"- `{result_dir / 'summary.json'}`",
            f"- `{result_dir / 'report.md'}`",
            "",
        ]
    )


def _write_plan(spec: AutoresearchSpec) -> None:
    result_dir = _result_dir(spec)
    report_path = _report_path(spec)
    result_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    for stale_name in ("summary.json", "all_candidates.csv", "top_candidates.csv"):
        (result_dir / stale_name).unlink(missing_ok=True)
    spec_payload = asdict(spec)
    (result_dir / "spec.json").write_text(json.dumps(spec_payload, indent=2, default=_json_default) + "\n")
    pd.DataFrame(_plan_rows(spec)).to_csv(result_dir / "trial_plan.csv", index=False)
    report = _render_plan_report(spec)
    (result_dir / "report.md").write_text(report + "\n")
    report_path.write_text(report + "\n")


def _run(spec: AutoresearchSpec) -> dict[str, Any]:
    result_dir = _result_dir(spec)
    report_path = _report_path(spec)
    result_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    sleeve_reports: list[dict[str, Any]] = []
    all_flat_rows: list[dict[str, Any]] = []
    top_flat_rows: list[dict[str, Any]] = []
    latest_dates: list[str] = []

    for asset in spec.assets:
        data_file, df, df_1m = _load_asset_data(asset, spec.data_start)
        if df.empty:
            raise RuntimeError(f"No data loaded for {asset} from {data_file}")
        latest_dates.append(df.index.max().date().isoformat())
        print(
            f"[{asset}] loaded {len(df):,} 5m rows; 1m={'yes' if df_1m is not None else 'no'}; latest={latest_dates[-1]}",
            flush=True,
        )
        for session_name in spec.sessions:
            print(f"  [{asset} {session_name}] evaluating autoresearch sleeve", flush=True)
            sleeve = _evaluate_sleeve(spec, asset, session_name, df, df_1m)
            sleeve_top_flat = [_flatten(row, rank=i + 1) for i, row in enumerate(sleeve["top"])]
            for row in sleeve["all_rows"]:
                all_flat_rows.append(_flatten(row))
            top_flat_rows.extend(sleeve_top_flat)
            sleeve_reports.append(
                {
                    "asset": asset,
                    "session": session_name,
                    "data": sleeve["data"],
                    "trial_counts": sleeve["trial_counts"],
                    "thresholds_by_orb_minutes": sleeve["thresholds_by_orb_minutes"],
                    "top": sleeve["top"],
                    "top_flat": sleeve_top_flat,
                }
            )
            print(f"  [{asset} {session_name}] best={sleeve_top_flat[0]['rule_id'] if sleeve_top_flat else 'none'}", flush=True)

    payload = {
        "run_id": spec.run_id,
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "latest_data_date": max(latest_dates) if latest_dates else None,
        "spec": asdict(spec),
        "result_dir": str(result_dir),
        "report_path": str(report_path),
        "sleeve_reports": sleeve_reports,
        "raw_candidates_evaluated": len(all_flat_rows),
        "top_candidates": top_flat_rows,
        "bailey_note": "CSCV/PBO is not implemented in this runner; PSR/DSR/effective trials are reported.",
    }
    (result_dir / "spec.json").write_text(json.dumps(asdict(spec), indent=2, default=_json_default) + "\n")
    (result_dir / "summary.json").write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    pd.DataFrame(all_flat_rows).to_csv(result_dir / "all_candidates.csv", index=False)
    pd.DataFrame(top_flat_rows).to_csv(result_dir / "top_candidates.csv", index=False)
    report = _render_run_report(payload)
    (result_dir / "report.md").write_text(report + "\n")
    report_path.write_text(report + "\n")
    return payload


def _build_spec(args: argparse.Namespace) -> AutoresearchSpec:
    space = _preset_space(
        args.preset,
        include_post_filter_only=args.include_post_filter_only,
        strategy=args.strategy,
    )
    if args.orb_minutes:
        space = replace(space, orb_minutes=_parse_int_tuple(args.orb_minutes, space.orb_minutes))
    if args.stop_atr_pct:
        space = replace(space, stop_atr_pct=_parse_float_tuple(args.stop_atr_pct, space.stop_atr_pct))
    if args.min_gap_atr_pct:
        space = replace(space, min_gap_atr_pct=_parse_float_tuple(args.min_gap_atr_pct, space.min_gap_atr_pct))
    if args.rr:
        space = replace(space, rr=_parse_float_tuple(args.rr, space.rr))
    if args.directions:
        space = replace(space, directions=_parse_csv(args.directions, space.directions))
    return AutoresearchSpec(
        run_id=args.run_id,
        strategy=args.strategy,
        assets=_parse_csv(args.assets, DEFAULT_ASSETS),
        sessions=_parse_csv(args.sessions, DEFAULT_SESSIONS),
        include_holdout=args.open_holdout,
        top_per_sleeve=args.top_per_sleeve,
        search_space=space,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "run"), default="plan")
    parser.add_argument("--preset", choices=("seed", "broad"), default="broad")
    parser.add_argument("--strategy", choices=("orb_breakout", "continuation"), default="orb_breakout")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--assets", help="Comma-separated assets. Default: NQ,ES,GC,SI,RTY,YM")
    parser.add_argument("--sessions", help="Comma-separated sessions. Default: NY,Asia,LDN")
    parser.add_argument("--orb-minutes", help="Comma-separated ORB minute values")
    parser.add_argument("--stop-atr-pct", help="Comma-separated stop ATR percentages")
    parser.add_argument("--min-gap-atr-pct", help="Comma-separated min gap ATR percentages")
    parser.add_argument("--rr", help="Comma-separated RR values")
    parser.add_argument("--directions", help="Comma-separated directions: long,short,both")
    parser.add_argument("--top-per-sleeve", type=int, default=TOP_PER_SLEEVE)
    parser.add_argument("--open-holdout", action="store_true", help="Evaluate frozen finalists on holdout. Off by default.")
    parser.add_argument(
        "--include-post-filter-only",
        action="store_true",
        help="Include large-ORB lower-bound research gates. Off by default to keep search live-native.",
    )
    parser.add_argument(
        "--allow-large-run",
        action="store_true",
        help="Allow runs with more than the default stream cap per sleeve.",
    )
    args = parser.parse_args()

    spec = _build_spec(args)
    result_dir = _result_dir(spec)
    report_path = _report_path(spec)
    _write_plan(spec)
    if args.mode == "plan":
        print(
            json.dumps(
                {
                    "success": True,
                    "mode": "plan",
                    "run_id": spec.run_id,
                    "sleeves": spec.sleeve_count,
                    "stream_configs_per_sleeve": spec.search_space.stream_count,
                    "post_filters_per_stream": spec.search_space.post_filter_count,
                    "raw_candidates": spec.raw_candidate_count,
                    "report": str(report_path),
                    "spec": str(result_dir / "spec.json"),
                },
                indent=2,
            )
        )
        return 0

    if spec.search_space.stream_count > MAX_DEFAULT_STREAMS_PER_SLEEVE and not args.allow_large_run:
        raise SystemExit(
            "Refusing large autoresearch run: "
            f"{spec.search_space.stream_count} stream configs per sleeve exceeds "
            f"{MAX_DEFAULT_STREAMS_PER_SLEEVE}. Re-run with --allow-large-run after reviewing "
            f"{result_dir / 'trial_plan.csv'}."
        )

    payload = _run(spec)
    print(
        json.dumps(
            {
                "success": True,
                "mode": "run",
                "run_id": spec.run_id,
                "raw_candidates_evaluated": payload["raw_candidates_evaluated"],
                "top_candidates": len(payload["top_candidates"]),
                "report": str(report_path),
                "summary": str(result_dir / "summary.json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
