"""Shared helpers for ALPHA_V1 downside-variant discovery.

This module standardizes the wave-1 downside research workflow:
- frozen ALPHA_V1 baseline legs
- unified holdout handling (`2025-01-01+`)
- causal trend x vol regime attribution
- pairwise overlap and portfolio additivity checks
- standardized research packets with PSR/DSR annotations
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..analysis.gates import apply_dow_filter
from ..analysis.regime_research import (
    attribute_strategy_by_regime,
    build_extended_regime_calendar,
    compute_bucket_metrics,
)
from ..config import SessionConfig, StrategyConfig
from ..data.instruments import ES, NQ, Instrument
from ..data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from ..engine.simulator import EXIT_NO_FILL, TradeResult, run_backtest
from ..optimize.parallel import run_sweep
from ..results.export import results_to_dict
from ..results.metrics import compute_metrics
from ..validate.deflated_sharpe import annotate_trades


DEFAULT_HOLDOUT_START = "2025-01-01"
DEFAULT_BASELINE_COMPARISON = "ALPHA_V1_frozen_4leg"
DEFAULT_TRACK = "generalist"
DEFAULT_DOW_TRUST = "low_trust"
DOWNSIDE_REGIMES = ("bear_medium_vol", "bear_high_vol")
OUTPUT_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "results" / "alpha_v1_downside"


@dataclass(frozen=True)
class CandidateLabel:
    """Portable metadata for all downside-research packets."""

    family: str
    session: str
    direction_mode: str
    track: str
    baseline_comparison: str
    candidate_name: str


@dataclass(frozen=True)
class CandidateSpec:
    """Config plus packet metadata and optional regime gating."""

    label: CandidateLabel
    config: StrategyConfig
    include_regimes: tuple[str, ...] = ()
    exclude_regimes: tuple[str, ...] = ()
    include_low_confidence: bool = True
    companion_leg: str | None = None
    quick_screen: bool = False
    notes: str = ""


@dataclass(frozen=True)
class PromotionThresholds:
    """Wave-1 promotion thresholds from the ALPHA_V1 downside plan."""

    min_trades_per_year_generalist: float = 25.0
    min_trades_per_year_specialist: float = 15.0
    min_psr: float = 0.95
    min_dsr: float = 0.50
    min_downside_improvement_pct: float = 20.0
    max_full_dd_worsening_pct: float = 10.0
    min_rolling_3m_dd_improvement_pct: float = 15.0
    max_holdout_net_r_drop_pct: float = 10.0
    min_avg_win_r: float = 0.15


@dataclass
class LoadedMarketData:
    instrument: Instrument
    df_5m: pd.DataFrame
    df_1m: pd.DataFrame | None
    df_1s: pd.DataFrame | None
    regime_calendar: pd.DataFrame


@dataclass
class DataCache:
    """Lazy cache for instrument data plus unified regime calendars."""

    start_date: str | None = None
    end_date: str | None = None

    def __post_init__(self) -> None:
        self._loaded: dict[str, LoadedMarketData] = {}

    def get(self, instrument: Instrument) -> LoadedMarketData:
        symbol = instrument.symbol
        if symbol not in self._loaded:
            df_5m = load_5m_data(instrument.data_file, start=self.start_date, end=self.end_date)
            try:
                df_1m = load_1m_for_5m(instrument.data_file, start=self.start_date, end=self.end_date)
            except FileNotFoundError:
                df_1m = None
            try:
                df_1s = load_1s_for_5m(instrument.data_file, start=self.start_date, end=self.end_date)
            except FileNotFoundError:
                df_1s = None
            regime_start = _regime_history_start(self.start_date)
            regime_df_5m = load_5m_data(instrument.data_file, start=regime_start, end=self.end_date)
            regime_calendar = build_extended_regime_calendar(
                regime_df_5m,
                start_date=regime_start,
                end_date=self.end_date,
                holdout_start=DEFAULT_HOLDOUT_START,
            )
            self._loaded[symbol] = LoadedMarketData(
                instrument=instrument,
                df_5m=df_5m,
                df_1m=df_1m,
                df_1s=df_1s,
                regime_calendar=regime_calendar,
            )
        return self._loaded[symbol]


def _regime_history_start(start_date: str | None) -> str | None:
    """Backfill enough history for causal regime thresholds and warmup."""

    if start_date is None:
        return None
    threshold_start = "2023-01-01"
    return min(start_date, threshold_start)


@dataclass(frozen=True)
class BaselineLeg:
    key: str
    family: str
    session: str
    config: StrategyConfig


def build_alpha_v1_legs() -> dict[str, BaselineLeg]:
    """Return the frozen ALPHA_V1 long-only baseline book."""

    nq_ny_lsi_session = SessionConfig(
        name="NY",
        rth_start="09:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    nq_ny_lsi = StrategyConfig(
        sessions=(nq_ny_lsi_session,),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.34,
        atr_length=10,
        lsi_n_left=8,
        lsi_n_right=60,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=5,
        lsi_stop_mode="absolute",
        lsi_entry_mode="fvg_limit",
        excluded_days=(2, 3),
        name="alpha_v1_nq_ny_lsi_long",
        notes="Frozen ALPHA_V1 baseline leg.",
    )

    nq_asia_session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",
        entry_start="20:15",
        entry_end="22:30",
        flat_start="04:00",
        flat_end="07:00",
        stop_orb_pct=100.0,
        min_gap_orb_pct=10.0,
    )
    nq_asia = StrategyConfig(
        sessions=(nq_asia_session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=6.0,
        tp1_ratio=0.3,
        atr_length=5,
        excluded_days=(1,),
        name="alpha_v1_nq_asia_orb_long",
        notes="Frozen ALPHA_V1 baseline leg.",
    )

    es_asia_session = SessionConfig(
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
    )
    es_asia = StrategyConfig(
        sessions=(es_asia_session,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=1.5,
        tp1_ratio=0.7,
        atr_length=14,
        name="alpha_v1_es_asia_orb_long",
        notes="Frozen ALPHA_V1 baseline leg.",
    )

    es_ny_session = SessionConfig(
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
    )
    es_ny = StrategyConfig(
        sessions=(es_ny_session,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=5.0,
        tp1_ratio=0.2,
        atr_length=7,
        excluded_days=(3,),
        name="alpha_v1_es_ny_orb_long",
        notes="Frozen ALPHA_V1 baseline leg.",
    )

    return {
        "nq_ny_lsi_long": BaselineLeg("nq_ny_lsi_long", "nq_ny_lsi", "NY", nq_ny_lsi),
        "nq_asia_orb_long": BaselineLeg("nq_asia_orb_long", "nq_asia_orb", "Asia", nq_asia),
        "es_asia_orb_long": BaselineLeg("es_asia_orb_long", "es_asia_orb", "Asia", es_asia),
        "es_ny_orb_long": BaselineLeg("es_ny_orb_long", "es_ny_orb", "NY", es_ny),
    }


def baseline_trade_streams(cache: DataCache) -> dict[str, list[TradeResult]]:
    """Run the frozen ALPHA_V1 baseline legs."""

    legs = build_alpha_v1_legs()
    return {key: run_config(cache, leg.config) for key, leg in legs.items()}


def filled_trades(trades: list[TradeResult]) -> list[TradeResult]:
    return [t for t in trades if t.exit_type != EXIT_NO_FILL]


def run_config(
    cache: DataCache,
    config: StrategyConfig,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[TradeResult]:
    """Run one config with standard post-trade filters."""

    market = cache.get(config.instrument)
    trades = run_backtest(
        market.df_5m,
        config,
        start_date=start_date or cache.start_date,
        end_date=end_date or cache.end_date,
        df_1m=market.df_1m,
        df_1s=market.df_1s,
    )
    if config.excluded_days:
        trades = apply_dow_filter(trades, set(config.excluded_days))
    return trades


def run_candidate_family(
    cache: DataCache,
    specs: list[CandidateSpec],
    n_workers: int = 1,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, list[TradeResult]]:
    """Run a group of candidate specs with the same instrument."""

    if not specs:
        return {}

    instrument = specs[0].config.instrument
    if any(spec.config.instrument.symbol != instrument.symbol for spec in specs):
        raise ValueError("Candidate family mixes instruments; split it before running.")

    market = cache.get(instrument)
    raw_results = run_sweep(
        market.df_5m,
        [spec.config for spec in specs],
        n_workers=n_workers,
        start_date=start_date or cache.start_date,
        end_date=end_date or cache.end_date,
        df_1m=market.df_1m,
        df_1s=market.df_1s,
    )
    by_name: dict[str, list[TradeResult]] = {}
    for config, trades in raw_results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        by_name[config.name] = trades
    return by_name


def merge_trade_streams(streams: list[list[TradeResult]]) -> list[TradeResult]:
    merged = [trade for stream in streams for trade in stream]
    return sorted(merged, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))


def daily_r_series(trades: list[TradeResult]) -> pd.Series:
    daily: dict[str, float] = defaultdict(float)
    for trade in filled_trades(trades):
        daily[trade.date] += float(trade.r_multiple)
    if not daily:
        return pd.Series(dtype=float)
    series = pd.Series(daily, dtype=float).sort_index()
    series.index = pd.to_datetime(series.index)
    return series


def ensure_daily_index(series: pd.Series) -> pd.Series:
    if series.empty:
        return series.astype(float)
    idx = pd.date_range(series.index.min(), series.index.max(), freq="B")
    return series.reindex(idx, fill_value=0.0).astype(float)


def portfolio_daily_frame(named_streams: dict[str, list[TradeResult]]) -> pd.DataFrame:
    all_series = {name: daily_r_series(trades) for name, trades in named_streams.items()}
    if not all_series:
        return pd.DataFrame()
    index = pd.Index(sorted(set().union(*[set(s.index) for s in all_series.values()])))
    df = pd.DataFrame(index=index)
    for name, series in all_series.items():
        df[name] = series.reindex(index, fill_value=0.0)
    return df.sort_index()


def summarize_daily_returns(series: pd.Series) -> dict[str, float | int]:
    series = ensure_daily_index(series)
    if series.empty:
        return {
            "total_r": 0.0,
            "max_drawdown_r": 0.0,
            "sharpe_ratio": 0.0,
            "calmar_ratio": 0.0,
            "negative_days": 0,
        }
    cum_r = series.cumsum()
    peaks = cum_r.cummax()
    drawdown = cum_r - peaks
    max_dd = float(drawdown.min())
    total_r = float(cum_r.iloc[-1])
    negative_days = int((series < 0).sum())
    std = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    sharpe = float(series.mean() / std * np.sqrt(252)) if std > 0 else 0.0
    years = max(len(series) / 252.0, 1e-9)
    calmar = float((total_r / years) / abs(max_dd)) if max_dd < 0 else 0.0
    return {
        "total_r": round(total_r, 4),
        "max_drawdown_r": round(max_dd, 4),
        "sharpe_ratio": round(sharpe, 4),
        "calmar_ratio": round(calmar, 4),
        "negative_days": negative_days,
    }


def split_period_metrics(
    trades: list[TradeResult],
    holdout_start: str = DEFAULT_HOLDOUT_START,
) -> dict[str, dict[str, Any]]:
    """Return full/pre-holdout/holdout metrics for a trade stream."""

    full = compute_metrics(trades)
    pre = compute_metrics([t for t in trades if t.date < holdout_start])
    holdout = compute_metrics([t for t in trades if t.date >= holdout_start])
    return {
        "full": full,
        "pre_holdout": pre,
        "holdout": holdout,
    }


def build_drawdown_clusters(series: pd.Series, top_n: int = 10) -> list[dict[str, Any]]:
    """Return the deepest drawdown episodes in a daily R series."""

    series = ensure_daily_index(series)
    if series.empty:
        return []

    cum_r = series.cumsum()
    peaks = cum_r.cummax()
    drawdown = cum_r - peaks

    clusters: list[dict[str, Any]] = []
    current_start: pd.Timestamp | None = None
    current_peak_date: pd.Timestamp | None = None
    current_peak_value = 0.0

    for idx in series.index:
        dd_val = float(drawdown.loc[idx])
        if dd_val < 0 and current_start is None:
            current_start = idx
            peak_idx = peaks.loc[:idx].idxmax()
            current_peak_date = peak_idx
            current_peak_value = float(peaks.loc[peak_idx])
        elif dd_val >= 0 and current_start is not None:
            cluster_drawdown = drawdown.loc[current_start:idx]
            trough_date = cluster_drawdown.idxmin()
            clusters.append(
                {
                    "peak_date": current_peak_date.strftime("%Y-%m-%d") if current_peak_date is not None else "",
                    "start_date": current_start.strftime("%Y-%m-%d"),
                    "trough_date": trough_date.strftime("%Y-%m-%d"),
                    "recovery_date": idx.strftime("%Y-%m-%d"),
                    "peak_r": round(current_peak_value, 4),
                    "trough_r": round(float(cum_r.loc[trough_date]), 4),
                    "drawdown_r": round(float(cluster_drawdown.min()), 4),
                    "trading_days": int(len(cluster_drawdown)),
                }
            )
            current_start = None
            current_peak_date = None
            current_peak_value = 0.0

    if current_start is not None:
        cluster_drawdown = drawdown.loc[current_start:]
        trough_date = cluster_drawdown.idxmin()
        clusters.append(
            {
                "peak_date": current_peak_date.strftime("%Y-%m-%d") if current_peak_date is not None else "",
                "start_date": current_start.strftime("%Y-%m-%d"),
                "trough_date": trough_date.strftime("%Y-%m-%d"),
                "recovery_date": None,
                "peak_r": round(current_peak_value, 4),
                "trough_r": round(float(cum_r.loc[trough_date]), 4),
                "drawdown_r": round(float(cluster_drawdown.min()), 4),
                "trading_days": int(len(cluster_drawdown)),
            }
        )

    return sorted(clusters, key=lambda row: row["drawdown_r"])[:top_n]


def weakest_rolling_windows(
    series: pd.Series,
    windows: dict[str, int] | None = None,
    top_n: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    series = ensure_daily_index(series)
    if windows is None:
        windows = {"1m": 21, "3m": 63, "6m": 126}
    results: dict[str, list[dict[str, Any]]] = {}
    if series.empty:
        return {name: [] for name in windows}
    for label, length in windows.items():
        rolls = series.rolling(length).sum().dropna()
        if rolls.empty:
            results[label] = []
            continue
        rows = []
        for end_idx, value in rolls.nsmallest(min(top_n, len(rolls))).items():
            end_pos = series.index.get_loc(end_idx)
            start_idx = series.index[max(0, end_pos - length + 1)]
            rows.append(
                {
                    "start_date": start_idx.strftime("%Y-%m-%d"),
                    "end_date": end_idx.strftime("%Y-%m-%d"),
                    "window_r": round(float(value), 4),
                    "trading_days": length,
                }
            )
        results[label] = rows
    return results


def pairwise_overlap(named_streams: dict[str, list[TradeResult]]) -> list[dict[str, Any]]:
    """Compute pairwise trade-date overlap and daily-R correlation."""

    keys = sorted(named_streams)
    daily = portfolio_daily_frame(named_streams)
    rows: list[dict[str, Any]] = []
    for i, left in enumerate(keys):
        left_dates = {trade.date for trade in filled_trades(named_streams[left])}
        for right in keys[i + 1:]:
            right_dates = {trade.date for trade in filled_trades(named_streams[right])}
            shared = left_dates & right_dates
            union = left_dates | right_dates
            corr = None
            if not daily.empty:
                corr = float(daily[left].corr(daily[right]))
            rows.append(
                {
                    "left": left,
                    "right": right,
                    "shared_trade_dates": len(shared),
                    "left_trade_dates": len(left_dates),
                    "right_trade_dates": len(right_dates),
                    "jaccard_overlap": round(len(shared) / len(union), 4) if union else 0.0,
                    "left_overlap_share": round(len(shared) / len(left_dates), 4) if left_dates else 0.0,
                    "right_overlap_share": round(len(shared) / len(right_dates), 4) if right_dates else 0.0,
                    "daily_r_correlation": round(corr, 4) if corr is not None and not np.isnan(corr) else None,
                }
            )
    return rows


def filter_trades_by_combined_regime(
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
    include_low_confidence: bool = True,
) -> list[TradeResult]:
    """Apply causal combined-regime gating to a trade stream."""

    include = include or set()
    exclude = exclude or set()
    cal = regime_calendar.copy()
    cal["date_str"] = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
    regime_lookup = dict(zip(cal["date_str"], cal["combined_regime"]))
    low_conf_lookup = dict(zip(cal["date_str"], cal["low_confidence"].astype(bool)))

    kept: list[TradeResult] = []
    for trade in trades:
        regime = regime_lookup.get(trade.date)
        if regime is None:
            continue
        if not include_low_confidence and low_conf_lookup.get(trade.date, False):
            continue
        if include and regime not in include:
            continue
        if exclude and regime in exclude:
            continue
        kept.append(trade)
    return kept


def strategy_attribution_packet(
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    holdout_start: str = DEFAULT_HOLDOUT_START,
) -> dict[str, Any]:
    attr = attribute_strategy_by_regime(trades, regime_calendar, holdout_start=holdout_start)
    if attr.empty:
        return {
            "bucket_metrics": [],
            "pre_holdout_bucket_metrics": [],
            "holdout_bucket_metrics": [],
            "downside_regime_net_r": {"pre_holdout": 0.0, "holdout": 0.0, "full": 0.0},
        }
    bucket_metrics = compute_bucket_metrics(attr, "combined_regime")
    pre_df = attr[attr["period"] == "pre_holdout"]
    holdout_df = attr[attr["period"] == "holdout"]
    return {
        "bucket_metrics": bucket_metrics.to_dict(orient="records"),
        "pre_holdout_bucket_metrics": (
            compute_bucket_metrics(pre_df, "combined_regime").to_dict(orient="records")
            if not pre_df.empty else []
        ),
        "holdout_bucket_metrics": (
            compute_bucket_metrics(holdout_df, "combined_regime").to_dict(orient="records")
            if not holdout_df.empty else []
        ),
        "downside_regime_net_r": {
            "pre_holdout": round(sum_regime_net_r(pre_df, DOWNSIDE_REGIMES), 4),
            "holdout": round(sum_regime_net_r(holdout_df, DOWNSIDE_REGIMES), 4),
            "full": round(sum_regime_net_r(attr, DOWNSIDE_REGIMES), 4),
        },
    }


def sum_regime_net_r(attr_df: pd.DataFrame, regimes: tuple[str, ...]) -> float:
    if attr_df.empty:
        return 0.0
    subset = attr_df[attr_df["combined_regime"].isin(regimes)]
    return float(subset["r_multiple"].sum()) if not subset.empty else 0.0


def trades_per_year(metrics: dict[str, Any]) -> float:
    r_by_year = metrics.get("r_by_year") or {}
    years = max(len(r_by_year), 1)
    return float(metrics.get("total_trades", 0)) / years


def is_degenerate_payoff(metrics: dict[str, Any], thresholds: PromotionThresholds) -> bool:
    if metrics.get("total_trades", 0) == 0:
        return True
    avg_win_r = abs(float(metrics.get("avg_win_r", 0.0) or 0.0))
    return avg_win_r < thresholds.min_avg_win_r


def percentage_change(base_value: float, candidate_value: float) -> float | None:
    if abs(base_value) < 1e-9:
        return None
    return ((candidate_value - base_value) / abs(base_value)) * 100.0


def improvement_vs_negative(base_value: float, candidate_value: float) -> float | None:
    """Return improvement percent when 'more positive / less negative' is better."""

    if abs(base_value) < 1e-9:
        return None
    return ((candidate_value - base_value) / abs(base_value)) * 100.0


def dd_improvement_pct(base_value: float, candidate_value: float) -> float | None:
    """Positive when candidate drawdown is smaller in absolute value."""

    base_abs = abs(base_value)
    cand_abs = abs(candidate_value)
    if base_abs < 1e-9:
        return None
    return ((base_abs - cand_abs) / base_abs) * 100.0


def build_generalist_promotion_memo(
    baseline_holdout_daily: pd.Series,
    baseline_full_daily: pd.Series,
    baseline_attr: dict[str, Any],
    combined_holdout_daily: pd.Series,
    combined_full_daily: pd.Series,
    combined_attr: dict[str, Any],
    standalone_metrics: dict[str, Any],
    psr_dsr: dict[str, Any],
    thresholds: PromotionThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or PromotionThresholds()

    full_metrics = standalone_metrics.get("full", {})
    trades_year = trades_per_year(full_metrics)
    structural = {
        "non_degenerate_payoff": not is_degenerate_payoff(full_metrics, thresholds),
        "positive_pre_holdout_edge": float(standalone_metrics.get("pre_holdout", {}).get("total_r", 0.0)) > 0.0,
        "min_trades_per_year": trades_year >= thresholds.min_trades_per_year_generalist,
    }
    structural_pass = all(structural.values())

    baseline_downside = float(baseline_attr["downside_regime_net_r"]["holdout"])
    combined_downside = float(combined_attr["downside_regime_net_r"]["holdout"])
    downside_improvement = improvement_vs_negative(baseline_downside, combined_downside)

    baseline_full = summarize_daily_returns(baseline_full_daily)
    combined_full = summarize_daily_returns(combined_full_daily)
    baseline_holdout = summarize_daily_returns(baseline_holdout_daily)
    combined_holdout = summarize_daily_returns(combined_holdout_daily)

    baseline_roll_3m = weakest_rolling_windows(baseline_full_daily, {"3m": 63}, top_n=1)["3m"]
    combined_roll_3m = weakest_rolling_windows(combined_full_daily, {"3m": 63}, top_n=1)["3m"]
    baseline_roll_val = float(baseline_roll_3m[0]["window_r"]) if baseline_roll_3m else 0.0
    combined_roll_val = float(combined_roll_3m[0]["window_r"]) if combined_roll_3m else 0.0
    rolling_improvement = dd_improvement_pct(baseline_roll_val, combined_roll_val)

    full_dd_worsening = percentage_change(
        abs(float(baseline_full["max_drawdown_r"])),
        abs(float(combined_full["max_drawdown_r"])),
    )
    holdout_net_r_change = percentage_change(
        float(baseline_holdout["total_r"]),
        float(combined_holdout["total_r"]),
    )

    rule_a = (
        downside_improvement is not None
        and downside_improvement >= thresholds.min_downside_improvement_pct
        and full_dd_worsening is not None
        and full_dd_worsening <= thresholds.max_full_dd_worsening_pct
    )
    rule_b = (
        rolling_improvement is not None
        and rolling_improvement >= thresholds.min_rolling_3m_dd_improvement_pct
        and holdout_net_r_change is not None
        and holdout_net_r_change >= -thresholds.max_holdout_net_r_drop_pct
    )

    psr_ok = float(psr_dsr["psr"]["value"]) >= thresholds.min_psr
    dsr_ok = float(psr_dsr["dsr"]["value"]) >= thresholds.min_dsr

    if structural_pass and (rule_a or rule_b) and psr_ok and dsr_ok:
        verdict = "promote"
        answer = "Adds unique downside value without violating the wave-1 generalist guardrails."
    elif structural_pass and (rule_a or rule_b) and psr_ok:
        verdict = "challenger"
        answer = "Shows additive downside value, but Bailey deflation remains below the default promotion bar."
    else:
        verdict = "reject"
        answer = "Looks more like a weaker substitute or an insufficiently robust add-on than a unique downside leg."

    return {
        "question": "Does this leg add unique downside value to the current book, or is it just a lower-quality substitute for an existing long leg?",
        "answer": answer,
        "verdict": verdict,
        "structural_screen": {**structural, "pass": structural_pass},
        "psr_dsr_screen": {
            "psr": float(psr_dsr["psr"]["value"]),
            "dsr": float(psr_dsr["dsr"]["value"]),
            "psr_pass": psr_ok,
            "dsr_pass": dsr_ok,
        },
        "additivity_checks": {
            "rule_a_downside_improvement_pct": round(downside_improvement, 4) if downside_improvement is not None else None,
            "rule_a_full_dd_worsening_pct": round(full_dd_worsening, 4) if full_dd_worsening is not None else None,
            "rule_a_pass": bool(rule_a),
            "rule_b_rolling_3m_improvement_pct": round(rolling_improvement, 4) if rolling_improvement is not None else None,
            "rule_b_holdout_net_r_change_pct": round(holdout_net_r_change, 4) if holdout_net_r_change is not None else None,
            "rule_b_pass": bool(rule_b),
        },
    }


def serialize_config(config: StrategyConfig) -> dict[str, Any]:
    return results_to_dict([], config, include_trades=False)["config"]


def research_packet(
    spec: CandidateSpec,
    trades: list[TradeResult],
    family_trade_sets: list[set[str]],
    n_trials_raw: int,
    baseline_streams: dict[str, list[TradeResult]],
    holdout_start: str = DEFAULT_HOLDOUT_START,
    thresholds: PromotionThresholds | None = None,
    companion_trades: list[TradeResult] | None = None,
    regime_calendar: pd.DataFrame | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or PromotionThresholds()
    regime_calendar = regime_calendar if regime_calendar is not None else pd.DataFrame()

    standalone_periods = split_period_metrics(trades, holdout_start=holdout_start)
    standalone_attr = strategy_attribution_packet(trades, regime_calendar, holdout_start=holdout_start)
    r_multiples = np.array([trade.r_multiple for trade in filled_trades(trades)], dtype=float)
    psr_dsr = annotate_trades(r_multiples, n_trials_raw=n_trials_raw, trade_date_sets=family_trade_sets)

    baseline_full_trades = merge_trade_streams(list(baseline_streams.values()))
    combined_trades = merge_trade_streams([baseline_full_trades, trades])
    combined_attr = strategy_attribution_packet(combined_trades, regime_calendar, holdout_start=holdout_start)
    baseline_attr = strategy_attribution_packet(baseline_full_trades, regime_calendar, holdout_start=holdout_start)

    baseline_daily = ensure_daily_index(daily_r_series(baseline_full_trades))
    combined_daily = ensure_daily_index(daily_r_series(combined_trades))
    baseline_holdout_daily = baseline_daily[baseline_daily.index >= pd.Timestamp(holdout_start)]
    combined_holdout_daily = combined_daily[combined_daily.index >= pd.Timestamp(holdout_start)]

    memo = build_generalist_promotion_memo(
        baseline_holdout_daily=baseline_holdout_daily,
        baseline_full_daily=baseline_daily,
        baseline_attr=baseline_attr,
        combined_holdout_daily=combined_holdout_daily,
        combined_full_daily=combined_daily,
        combined_attr=combined_attr,
        standalone_metrics=standalone_periods,
        psr_dsr=psr_dsr,
        thresholds=thresholds,
    )

    overlap = pairwise_overlap(
        {
            **{key: value for key, value in baseline_streams.items()},
            spec.label.candidate_name: trades,
        }
    )

    packet = {
        "label": asdict(spec.label),
        "candidate_config": serialize_config(spec.config),
        "holdout_start": holdout_start,
        "dow_filter_posture": DEFAULT_DOW_TRUST,
        "notes": spec.notes,
        "standalone": {
            "metrics": standalone_periods,
            "regime_attribution": standalone_attr,
            "psr_dsr": psr_dsr,
        },
        "combined_with_alpha_v1": {
            "metrics": {
                "full": summarize_daily_returns(combined_daily),
                "holdout": summarize_daily_returns(combined_holdout_daily),
            },
            "regime_attribution": combined_attr,
            "drawdown_clusters_top10": build_drawdown_clusters(combined_daily, top_n=10),
            "weakest_rolling_windows": weakest_rolling_windows(combined_daily, top_n=10),
        },
        "baseline_reference": {
            "metrics": {
                "full": summarize_daily_returns(baseline_daily),
                "holdout": summarize_daily_returns(baseline_holdout_daily),
            },
            "regime_attribution": baseline_attr,
        },
        "overlap_additivity": {
            "pairwise_overlap": overlap,
        },
        "promotion_memo": memo,
    }

    if companion_trades is not None:
        packet["same_family_book"] = {
            "companion_metrics": split_period_metrics(companion_trades, holdout_start=holdout_start),
            "candidate_metrics": standalone_periods,
            "dual_book_metrics": split_period_metrics(
                merge_trade_streams([companion_trades, trades]),
                holdout_start=holdout_start,
            ),
        }

    return packet


def packet_summary_row(packet: dict[str, Any]) -> dict[str, Any]:
    additivity = packet["promotion_memo"]["additivity_checks"]
    standalone_full = packet["standalone"]["metrics"]["full"]
    standalone_holdout = packet["standalone"]["metrics"]["holdout"]
    return {
        "family": packet["label"]["family"],
        "candidate_name": packet["label"]["candidate_name"],
        "session": packet["label"]["session"],
        "direction_mode": packet["label"]["direction_mode"],
        "track": packet["label"]["track"],
        "verdict": packet["promotion_memo"]["verdict"],
        "full_trades": standalone_full.get("total_trades", 0),
        "full_total_r": round(float(standalone_full.get("total_r", 0.0)), 4),
        "holdout_total_r": round(float(standalone_holdout.get("total_r", 0.0)), 4),
        "psr": packet["standalone"]["psr_dsr"]["psr"]["value"],
        "dsr": packet["standalone"]["psr_dsr"]["dsr"]["value"],
        "rule_a_downside_improvement_pct": additivity["rule_a_downside_improvement_pct"],
        "rule_b_rolling_3m_improvement_pct": additivity["rule_b_rolling_3m_improvement_pct"],
        "rule_b_holdout_net_r_change_pct": additivity["rule_b_holdout_net_r_change_pct"],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def make_label(
    family: str,
    session: str,
    direction_mode: str,
    candidate_name: str,
    track: str = DEFAULT_TRACK,
    baseline_comparison: str = DEFAULT_BASELINE_COMPARISON,
) -> CandidateLabel:
    return CandidateLabel(
        family=family,
        session=session,
        direction_mode=direction_mode,
        track=track,
        baseline_comparison=baseline_comparison,
        candidate_name=candidate_name,
    )


def clone_with_name(config: StrategyConfig, name: str, notes: str = "") -> StrategyConfig:
    return replace(config, name=name, notes=notes or config.notes)
