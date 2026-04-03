"""NQ regime research workflow — 3x3 trend x volatility framework.

Builds a causal, Bailey-aware regime research pipeline:
1. Extend the existing trend-only regime calendar with a volatility axis.
2. Validate the regime framework itself (audit, threshold search, walk-forward, holdout).
3. Attribute existing strategies by regime bucket.
4. Evaluate specialist promotion criteria.
5. Optimize specialists within target regimes.
6. Validate the full gated system and feed into prop-firm downstream evaluation.

The regime framework is treated as its own model with dedicated validation,
separate from downstream strategy tuning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd

from ..config import StrategyConfig
from ..engine.simulator import EXIT_NO_FILL, TradeResult
from ..results.metrics import compute_metrics
from .prop_regime_specialist import (
    PropFirmProfile,
    build_nq_ny_regime_calendar,
    build_prop_scorecard,
    build_regime_confusion_log,
    build_yearly_regime_summary,
    evaluate_specialist,
    simulate_account_attempts,
    trading_dates_from_calendar,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGIME_RESEARCH_HOLDOUT_START = "2024-03-01"
REGIME_RESEARCH_HOLDOUT_END = "2026-02-28"
PRE_HOLDOUT_END = "2024-02-29"

VALID_TREND_REGIMES = {"bull", "bear", "sideways", "warmup"}
VALID_VOL_REGIMES = {"low_vol", "medium_vol", "high_vol"}
VALID_COMBINED_PREFIXES = {"bull", "bear", "sideways"}

# ---------------------------------------------------------------------------
# Challenger specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrendFeatureSpec:
    """Frozen definition of a trend feature and its classification thresholds."""

    name: str
    feature_col: str
    formula: str
    bull_threshold: float
    bear_threshold: float
    ret5d_threshold: float = 0.0
    shift_by_one_session: bool = True


@dataclass(frozen=True)
class VolFeatureSpec:
    """Frozen definition of a volatility feature and its bucketing method."""

    name: str
    feature_col: str
    formula: str
    bucketing_method: str = "tercile"
    shift_by_one_session: bool = True
    live_recreatable: bool = True


@dataclass(frozen=True)
class RegimeChallengerSpec:
    """Complete definition of a regime challenger."""

    name: str
    family: str
    trend: TrendFeatureSpec
    vol: VolFeatureSpec
    low_conf_trend_threshold: float = 0.0025
    low_conf_ret5d_threshold: float = 0.005
    warmup_length: int = 21
    description: str = ""


def make_baseline_challenger_spec(
    trend_sma_threshold: float = 0.005,
    trend_ret5d_threshold: float = 0.0,
    vol_method: str = "tercile",
) -> RegimeChallengerSpec:
    """Return the current regime baseline as an explicit challenger spec."""
    return RegimeChallengerSpec(
        name="baseline_v1",
        family="baseline",
        trend=TrendFeatureSpec(
            name="close_vs_sma20",
            feature_col="close_vs_sma20",
            formula="close / SMA20 - 1",
            bull_threshold=trend_sma_threshold,
            bear_threshold=-trend_sma_threshold,
            ret5d_threshold=trend_ret5d_threshold,
        ),
        vol=VolFeatureSpec(
            name="realized_vol_21d",
            feature_col="realized_vol_21d",
            formula="rolling 21-day std of daily log returns annualized",
            bucketing_method=vol_method,
        ),
        description="Current baseline: close_vs_sma20 + ret_5d sign + realized_vol_21d terciles.",
    )


# ---------------------------------------------------------------------------
# Trial counter
# ---------------------------------------------------------------------------


@dataclass
class TrialCounter:
    """Track cumulative trial counts across research phases for Bailey-aware reporting."""

    phases: dict[str, int] = field(default_factory=dict)

    def add(self, phase: str, count: int) -> None:
        self.phases[phase] = self.phases.get(phase, 0) + count

    @property
    def total(self) -> int:
        return sum(self.phases.values())

    def summary(self) -> str:
        lines = [f"Trial count by phase (total={self.total}):"]
        for phase, count in sorted(self.phases.items()):
            lines.append(f"  {phase}: {count}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers (reimplemented from prop_regime_specialist to avoid coupling)
# ---------------------------------------------------------------------------


def _filled_trades(trades: Iterable[TradeResult]) -> list[TradeResult]:
    return [t for t in trades if t.exit_type != EXIT_NO_FILL]


def _regime_lookup(
    regime_calendar: pd.DataFrame,
    col: str = "regime",
) -> dict[str, str]:
    """Build a date-string -> regime-label lookup dict."""
    cal = regime_calendar.copy()
    cal["_date_str"] = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
    return dict(zip(cal["_date_str"], cal[col].astype(str)))


def _metrics_snapshot(metrics: dict) -> dict:
    keys = [
        "total_signals", "total_trades", "win_rate", "profit_factor",
        "avg_r", "total_r", "max_drawdown_r", "sharpe_ratio", "calmar_ratio",
        "max_consecutive_losses", "r_by_year",
    ]
    snap = {key: metrics.get(key) for key in keys}
    for key in ("win_rate", "profit_factor", "avg_r", "total_r",
                "max_drawdown_r", "sharpe_ratio", "calmar_ratio"):
        if snap.get(key) is not None:
            snap[key] = round(float(snap[key]), 4)
    if snap.get("r_by_year"):
        snap["r_by_year"] = {str(k): round(float(v), 4) for k, v in snap["r_by_year"].items()}
    return snap


def _dominant_year_share(in_metrics: dict) -> float:
    total_r = float(in_metrics.get("total_r", 0.0))
    yearly = in_metrics.get("r_by_year", {}) or {}
    if total_r <= 0 or not yearly:
        return 1.0 if total_r <= 0 else 0.0
    max_year = max(float(v) for v in yearly.values())
    return max_year / total_r if total_r else 0.0


def _json_number(value: float) -> float | str:
    if np.isinf(value):
        return "inf"
    return round(float(value), 4)


def _expected_combined_regimes() -> list[str]:
    """Return the canonical 3x3 combined buckets in sorted order."""
    return [
        f"{trend}_{vol}"
        for trend in sorted(VALID_COMBINED_PREFIXES)
        for vol in sorted(VALID_VOL_REGIMES)
    ]


def _serialize_challenger_spec(spec: RegimeChallengerSpec) -> dict:
    """Return a machine-readable representation of a challenger spec."""
    return {
        "name": spec.name,
        "family": spec.family,
        "description": spec.description,
        "trend": {
            "name": spec.trend.name,
            "feature_col": spec.trend.feature_col,
            "formula": spec.trend.formula,
            "bull_threshold": spec.trend.bull_threshold,
            "bear_threshold": spec.trend.bear_threshold,
            "ret5d_threshold": spec.trend.ret5d_threshold,
            "shift_by_one_session": spec.trend.shift_by_one_session,
        },
        "vol": {
            "name": spec.vol.name,
            "feature_col": spec.vol.feature_col,
            "formula": spec.vol.formula,
            "bucketing_method": spec.vol.bucketing_method,
            "shift_by_one_session": spec.vol.shift_by_one_session,
            "live_recreatable": spec.vol.live_recreatable,
        },
        "low_conf_trend_threshold": spec.low_conf_trend_threshold,
        "low_conf_ret5d_threshold": spec.low_conf_ret5d_threshold,
        "warmup_length": spec.warmup_length,
    }


# ---------------------------------------------------------------------------
# Step 1: Extended regime calendar
# ---------------------------------------------------------------------------


def _build_daily_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 5m bars into daily OHLCV."""
    daily = (
        df.resample("1D")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        .dropna(subset=["close"])
        .copy()
    )
    return daily[daily["volume"] > 0].copy()


def _normalized_lr_slope(series: pd.Series, window: int) -> pd.Series:
    """Rolling linear-regression slope normalized by the current price."""
    x = np.arange(window, dtype=np.float64)

    def _fit(values: np.ndarray) -> float:
        if np.isnan(values).any() or values[-1] == 0:
            return np.nan
        slope = np.polyfit(x, values, 1)[0]
        return float(slope / values[-1])

    return series.rolling(window, min_periods=window).apply(_fit, raw=True)


def _compute_ewma_vol(log_returns: pd.Series, lam: float, min_periods: int) -> pd.Series:
    """EWMA annualized volatility using a fixed decay factor."""
    values = log_returns.to_numpy(dtype=np.float64)
    ewma_var = np.full(len(values), np.nan, dtype=np.float64)
    prev_var = np.nan
    valid_count = 0

    for i, ret in enumerate(values):
        if np.isnan(ret):
            continue
        valid_count += 1
        squared = ret * ret
        prev_var = squared if np.isnan(prev_var) else lam * prev_var + (1.0 - lam) * squared
        if valid_count >= min_periods:
            ewma_var[i] = prev_var

    return pd.Series(np.sqrt(ewma_var * 252.0), index=log_returns.index)


def _compute_atr_pct(
    daily: pd.DataFrame,
    window: int,
) -> pd.Series:
    """Daily ATR divided by close using a simple rolling true-range mean."""
    prev_close = daily["close"].shift(1)
    true_range = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(window, min_periods=window).mean()
    return atr / daily["close"].replace(0, np.nan)


def _compute_yang_zhang_vol(
    daily: pd.DataFrame,
    window: int,
) -> pd.Series:
    """Yang-Zhang annualized volatility on daily OHLC."""
    prev_close = daily["close"].shift(1)
    log_ho = np.log(daily["high"] / daily["open"])
    log_lo = np.log(daily["low"] / daily["open"])
    log_co = np.log(daily["close"] / daily["open"])
    log_oc = np.log(daily["open"] / prev_close)
    log_cc = np.log(daily["close"] / prev_close)

    sigma_open = log_oc.rolling(window, min_periods=window).var()
    sigma_close = log_cc.rolling(window, min_periods=window).var()
    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)
    rs_mean = rs.rolling(window, min_periods=window).mean()

    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    yz_var = sigma_open + k * sigma_close + (1.0 - k) * rs_mean
    yz_var = yz_var.clip(lower=0.0)
    return np.sqrt(yz_var * 252.0)


def _build_daily_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Build the full set of daily features used by the challenger registry."""
    daily = _build_daily_ohlcv(df)
    close = daily["close"]
    prev_close = close.shift(1)
    log_returns = np.log(close / prev_close)

    features = pd.DataFrame(
        {
            "date": daily.index.normalize(),
            "open": daily["open"],
            "high": daily["high"],
            "low": daily["low"],
            "close": close,
            "volume": daily["volume"],
            "ret_5d": close.pct_change(5),
            "close_vs_sma20": close / close.rolling(20, min_periods=20).mean() - 1.0,
            "close_vs_ema20": close / close.ewm(span=20, adjust=False, min_periods=20).mean() - 1.0,
            "ema10_20_spread": (
                close.ewm(span=10, adjust=False, min_periods=10).mean()
                / close.ewm(span=20, adjust=False, min_periods=20).mean()
            ) - 1.0,
            "lr20_slope_norm": _normalized_lr_slope(close, 20),
            "realized_vol_21d": log_returns.rolling(21, min_periods=21).std() * np.sqrt(252.0),
            "ewma_vol_21d": _compute_ewma_vol(log_returns, lam=0.94, min_periods=21),
            "atr20_pct": _compute_atr_pct(daily, 20),
            "yang_zhang_21d": _compute_yang_zhang_vol(daily, 21),
        },
        index=daily.index,
    )
    return features


def _apply_feature_shifts(
    features: pd.DataFrame,
    shift_feature_cols: Sequence[str],
) -> pd.DataFrame:
    """Shift selected daily features by one full session."""
    shifted = features.copy()
    for col in shift_feature_cols:
        shifted[col] = shifted[col].shift(1)
    return shifted


def _render_rule_spec(
    spec: RegimeChallengerSpec,
    vol_threshold_method: str,
) -> str:
    """Human-readable rule specification for audit outputs."""
    bull_thresh = abs(spec.trend.bull_threshold) * 100
    bear_thresh = abs(spec.trend.bear_threshold) * 100
    bear_ret_threshold = -spec.trend.ret5d_threshold if spec.trend.ret5d_threshold > 0 else 0.0
    return (
        "Trend axis (point-in-time, shifted by 1 session):\n"
        f"  feature: {spec.trend.formula}\n"
        f"  bull:     {spec.trend.feature_col} >= +{bull_thresh:.2f}% AND ret_5d > {spec.trend.ret5d_threshold:.4f}\n"
        f"  bear:     {spec.trend.feature_col} <= -{bear_thresh:.2f}% AND ret_5d < {bear_ret_threshold:.4f}\n"
        "  sideways: everything else (after warmup)\n\n"
        "Volatility axis (point-in-time, shifted by 1 session):\n"
        f"  feature: {spec.vol.formula}\n"
        "  thresholds computed on pre-holdout data only\n"
        f"  bucketing: {vol_threshold_method}\n\n"
        "Combined: trend_regime + '_' + vol_regime (e.g., 'bull_high_vol')\n"
        f"Low-confidence: |trend_value| < {spec.low_conf_trend_threshold:.4f} OR |ret_5d| < {spec.low_conf_ret5d_threshold:.4f}\n"
        f"Warmup: first {spec.warmup_length} sessions, or insufficient history for {spec.trend.feature_col}, ret_5d, or {spec.vol.feature_col}"
    )


def compute_vol_thresholds(
    regime_calendar: pd.DataFrame,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    method: str = "tercile",
    vol_col: str = "realized_vol_21d",
) -> dict[str, float]:
    """Compute volatility bucketing thresholds on pre-holdout data only.

    Args:
        regime_calendar: DataFrame with ``date``, ``realized_vol_21d``, ``warmup_ok`` columns.
        holdout_start: Holdout start date (YYYY-MM-DD). Only data before this date is used.
        method: ``"tercile"`` (33/67 percentiles) or ``"quartile"`` (25/50/75 percentiles).

    Returns:
        Dict with ``"low_upper"`` and ``"medium_upper"`` thresholds.
        For quartile method, also includes ``"q25"``, ``"q50"``, ``"q75"``.
    """
    cal = regime_calendar.copy()
    cal["_date_ts"] = pd.to_datetime(cal["date"])
    pre = cal[(cal["_date_ts"] < pd.Timestamp(holdout_start)) & (cal["warmup_ok"] == True)]  # noqa: E712
    vol = pre[vol_col].dropna()

    if vol.empty:
        raise ValueError("No valid pre-holdout volatility data for threshold computation")

    if method == "tercile":
        low_upper = float(np.percentile(vol, 100 / 3))
        medium_upper = float(np.percentile(vol, 200 / 3))
        return {"low_upper": round(low_upper, 6), "medium_upper": round(medium_upper, 6)}
    elif method == "quartile":
        q25 = float(np.percentile(vol, 25))
        q50 = float(np.percentile(vol, 50))
        q75 = float(np.percentile(vol, 75))
        return {
            "low_upper": round(q25, 6),
            "medium_upper": round(q75, 6),
            "q25": round(q25, 6),
            "q50": round(q50, 6),
            "q75": round(q75, 6),
        }
    else:
        raise ValueError(f"Unknown vol method: {method!r}. Use 'tercile' or 'quartile'.")


def _classify_vol(vol_value: float, thresholds: dict[str, float]) -> str:
    """Classify a single volatility value into low/medium/high."""
    if pd.isna(vol_value):
        return "unknown"
    if vol_value <= thresholds["low_upper"]:
        return "low_vol"
    elif vol_value <= thresholds["medium_upper"]:
        return "medium_vol"
    else:
        return "high_vol"


def build_extended_regime_calendar(
    df: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
    trend_sma_threshold: float = 0.005,
    trend_ret5d_threshold: float = 0.0,
    vol_method: str = "tercile",
    vol_thresholds: dict[str, float] | None = None,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    challenger_spec: RegimeChallengerSpec | None = None,
) -> pd.DataFrame:
    """Build 3x3 regime calendar with trend and volatility axes.

    Wraps ``build_nq_ny_regime_calendar()`` and adds:
    - ``vol_regime``: low_vol / medium_vol / high_vol
    - ``combined_regime``: e.g. ``"bull_high_vol"``, ``"sideways_low_vol"``

    The original ``regime`` column (bull/bear/sideways/warmup) is preserved unchanged.

    If ``vol_thresholds`` is None, tercile/quartile thresholds are computed from
    pre-holdout data. Pass explicit thresholds for fold-by-fold walk-forward use.

    Args:
        df: 5m OHLCV DataFrame with DatetimeIndex.
        start_date: Optional start date filter.
        end_date: Optional end date filter.
        trend_sma_threshold: Threshold for close_vs_sma20 bull/bear classification.
        trend_ret5d_threshold: Threshold for ret_5d bull/bear classification.
        vol_method: Volatility bucketing method (``"tercile"`` or ``"quartile"``).
        vol_thresholds: Pre-computed vol thresholds. If None, computed from pre-holdout.
        holdout_start: Holdout start date for vol threshold computation.

    Returns:
        DataFrame with columns: date, close_vs_sma20, ret_5d, realized_vol_21d,
        warmup_ok, low_confidence, regime, vol_regime, combined_regime.
    """
    spec = challenger_spec or make_baseline_challenger_spec(
        trend_sma_threshold=trend_sma_threshold,
        trend_ret5d_threshold=trend_ret5d_threshold,
        vol_method=vol_method,
    )

    features = _build_daily_feature_frame(df)
    shift_cols = {"ret_5d"}
    if spec.trend.shift_by_one_session:
        shift_cols.add(spec.trend.feature_col)
    if spec.vol.shift_by_one_session:
        shift_cols.add(spec.vol.feature_col)
    features = _apply_feature_shifts(features, sorted(shift_cols))

    cal = features.reset_index(drop=True).copy()
    cal["trend_value"] = cal[spec.trend.feature_col]
    cal["vol_value"] = cal[spec.vol.feature_col]
    cal["_session_number"] = np.arange(len(cal)) + 1
    cal["warmup_ok"] = (
        cal[["trend_value", "ret_5d", "vol_value"]].notna().all(axis=1)
        & (cal["_session_number"] > spec.warmup_length)
    )
    cal["low_confidence"] = cal["warmup_ok"] & (
        (cal["trend_value"].abs() < spec.low_conf_trend_threshold)
        | (cal["ret_5d"].abs() < spec.low_conf_ret5d_threshold)
    )

    bull_mask = (
        cal["warmup_ok"]
        & (cal["trend_value"] >= spec.trend.bull_threshold)
        & (cal["ret_5d"] > spec.trend.ret5d_threshold)
    )
    bear_ret_threshold = -spec.trend.ret5d_threshold if spec.trend.ret5d_threshold > 0 else 0.0
    bear_mask = (
        cal["warmup_ok"]
        & (cal["trend_value"] <= spec.trend.bear_threshold)
        & (cal["ret_5d"] < bear_ret_threshold)
    )

    cal["regime"] = "sideways"
    cal.loc[bull_mask, "regime"] = "bull"
    cal.loc[bear_mask, "regime"] = "bear"
    cal.loc[~cal["warmup_ok"], "regime"] = "warmup"

    if start_date is not None:
        cal = cal[cal["date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        cal = cal[cal["date"] <= pd.Timestamp(end_date)]

    if vol_thresholds is None:
        vol_thresholds = compute_vol_thresholds(
            cal,
            holdout_start,
            spec.vol.bucketing_method,
            vol_col=spec.vol.feature_col,
        )

    cal["vol_regime"] = cal[spec.vol.feature_col].apply(
        lambda v: _classify_vol(v, vol_thresholds)
    )
    cal.loc[~cal["warmup_ok"], "vol_regime"] = "unknown"
    cal["combined_regime"] = cal.apply(
        lambda row: (
            f"{row['regime']}_{row['vol_regime']}"
            if row["regime"] != "warmup"
            else "warmup"
        ),
        axis=1,
    )
    cal["challenger_name"] = spec.name
    cal["challenger_family"] = spec.family
    return cal.drop(columns="_session_number").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 2: Phase A — Regime definition audit
# ---------------------------------------------------------------------------


def count_regime_episodes(
    regime_calendar: pd.DataFrame,
    regime_col: str = "combined_regime",
) -> pd.DataFrame:
    """Count contiguous episodes per regime label.

    An episode is a consecutive run of identical labels. Returns statistics
    per regime: episode count, mean/median/min/max duration in days.
    """
    cal = regime_calendar[regime_calendar["warmup_ok"] == True].copy()  # noqa: E712
    if cal.empty:
        return pd.DataFrame(columns=[
            "regime", "episode_count", "mean_duration",
            "median_duration", "min_duration", "max_duration",
        ])

    cal = cal.sort_values("date").reset_index(drop=True)
    cal["_episode_id"] = (cal[regime_col] != cal[regime_col].shift()).cumsum()

    episode_stats = (
        cal.groupby(["_episode_id", regime_col])
        .size()
        .reset_index(name="duration")
    )

    summary = (
        episode_stats.groupby(regime_col)["duration"]
        .agg(["count", "mean", "median", "min", "max"])
        .reset_index()
    )
    summary.columns = [
        "regime", "episode_count", "mean_duration",
        "median_duration", "min_duration", "max_duration",
    ]
    summary["mean_duration"] = summary["mean_duration"].round(2)
    summary["median_duration"] = summary["median_duration"].round(2)

    return summary.sort_values("episode_count", ascending=False).reset_index(drop=True)


def _build_yearly_counts(
    regime_calendar: pd.DataFrame,
    regime_col: str,
) -> pd.DataFrame:
    """Build yearly counts for any regime column."""
    cal = regime_calendar[regime_calendar["warmup_ok"] == True].copy()  # noqa: E712
    if cal.empty:
        return pd.DataFrame(columns=["year"])

    cal["year"] = pd.to_datetime(cal["date"]).dt.year.astype(str)
    summary = (
        cal.groupby(["year", regime_col])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    summary["total"] = summary.select_dtypes(include="number").sum(axis=1)
    return summary


def audit_regime_definition(
    regime_calendar: pd.DataFrame,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    challenger_spec: RegimeChallengerSpec | None = None,
) -> dict:
    """Phase A: produce rule spec, yearly counts, ambiguity log, and episode counts.

    Returns:
        Dict with keys: rule_spec, yearly_trend_counts, yearly_vol_counts,
        yearly_combined_counts, ambiguity_log, pre_holdout_summary,
        trend_episodes, vol_episodes, combined_episodes.
    """
    cal = regime_calendar.copy()
    cal["_date_ts"] = pd.to_datetime(cal["date"])
    pre = cal[cal["_date_ts"] < pd.Timestamp(holdout_start)]

    spec = challenger_spec or make_baseline_challenger_spec()
    rule_spec = _render_rule_spec(spec, spec.vol.bucketing_method)

    yearly_trend = build_yearly_regime_summary(cal)
    yearly_vol = _build_yearly_counts(cal, "vol_regime")
    yearly_combined = _build_yearly_counts(cal, "combined_regime")

    ambiguity_log = build_regime_confusion_log(cal)

    # Pre-holdout summary
    pre_warmup = pre[pre["warmup_ok"] == True]  # noqa: E712
    pre_trend_counts = pre_warmup["regime"].value_counts().to_dict() if not pre_warmup.empty else {}
    pre_vol_counts = pre_warmup["vol_regime"].value_counts().to_dict() if not pre_warmup.empty else {}
    pre_combined_counts = pre_warmup["combined_regime"].value_counts().to_dict() if not pre_warmup.empty else {}

    pre_holdout_summary = {
        "total_days": int(len(pre_warmup)),
        "trend_counts": {str(k): int(v) for k, v in pre_trend_counts.items()},
        "vol_counts": {str(k): int(v) for k, v in pre_vol_counts.items()},
        "combined_counts": {str(k): int(v) for k, v in pre_combined_counts.items()},
        "low_confidence_days": int(pre["low_confidence"].sum()) if "low_confidence" in pre.columns else 0,
    }

    # Episode counts
    trend_episodes = count_regime_episodes(cal, "regime")
    vol_episodes = count_regime_episodes(cal, "vol_regime")
    combined_episodes = count_regime_episodes(cal, "combined_regime")

    return {
        "rule_spec": rule_spec,
        "yearly_trend_counts": yearly_trend.to_dict(orient="records"),
        "yearly_vol_counts": yearly_vol.to_dict(orient="records"),
        "yearly_combined_counts": yearly_combined.to_dict(orient="records"),
        "ambiguity_log_count": len(ambiguity_log),
        "pre_holdout_summary": pre_holdout_summary,
        "trend_episodes": trend_episodes.to_dict(orient="records"),
        "vol_episodes": vol_episodes.to_dict(orient="records"),
        "combined_episodes": combined_episodes.to_dict(orient="records"),
    }


# ---------------------------------------------------------------------------
# Step 3: Phase B — Threshold search
# ---------------------------------------------------------------------------


def search_regime_thresholds(
    df: pd.DataFrame,
    threshold_variants: list[dict],
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
) -> pd.DataFrame:
    """Compare threshold variants on pre-holdout data.

    Each variant is a dict with keys:
    - ``trend_sma_threshold`` (float)
    - ``trend_ret5d_threshold`` (float)
    - ``vol_method`` (str: "tercile" or "quartile")

    Returns DataFrame with one row per variant: trial_id, variant params,
    bucket frequencies (%), episode counts, min_bucket_share, ambiguity_rate.
    """
    rows: list[dict] = []

    for trial_id, variant in enumerate(threshold_variants):
        sma_thresh = variant.get("trend_sma_threshold", 0.005)
        ret5d_thresh = variant.get("trend_ret5d_threshold", 0.0)
        vol_method = variant.get("vol_method", "tercile")

        cal = build_extended_regime_calendar(
            df,
            trend_sma_threshold=sma_thresh,
            trend_ret5d_threshold=ret5d_thresh,
            vol_method=vol_method,
            holdout_start=holdout_start,
        )

        # Filter to pre-holdout only
        cal["_date_ts"] = pd.to_datetime(cal["date"])
        pre = cal[(cal["_date_ts"] < pd.Timestamp(holdout_start)) & (cal["warmup_ok"] == True)]  # noqa: E712

        if pre.empty:
            continue

        total_days = len(pre)

        # Bucket frequencies
        combined_counts = pre["combined_regime"].value_counts()
        bucket_freqs = (combined_counts / total_days * 100).to_dict()
        min_bucket_share = float(combined_counts.min() / total_days) if not combined_counts.empty else 0.0

        # Trend frequencies
        trend_counts = pre["regime"].value_counts()
        trend_freqs = (trend_counts / total_days * 100).to_dict()

        # Vol frequencies
        vol_counts = pre["vol_regime"].value_counts()
        vol_freqs = (vol_counts / total_days * 100).to_dict()

        # Episode counts
        combined_episodes = count_regime_episodes(pre, "combined_regime")
        total_episodes = int(combined_episodes["episode_count"].sum()) if not combined_episodes.empty else 0
        min_bucket_episodes = int(combined_episodes["episode_count"].min()) if not combined_episodes.empty else 0

        # Ambiguity rate
        ambiguity_rate = float(pre["low_confidence"].sum() / total_days) if total_days > 0 else 0.0

        row = {
            "trial_id": trial_id,
            "trend_sma_threshold": sma_thresh,
            "trend_ret5d_threshold": ret5d_thresh,
            "vol_method": vol_method,
            "total_pre_holdout_days": total_days,
            "n_combined_buckets": len(combined_counts),
            "min_bucket_share": round(min_bucket_share, 4),
            "min_bucket_episodes": min_bucket_episodes,
            "total_episodes": total_episodes,
            "ambiguity_rate": round(ambiguity_rate, 4),
        }

        # Add individual bucket frequencies
        for regime_label, freq in sorted(bucket_freqs.items()):
            row[f"freq_{regime_label}"] = round(freq, 2)

        # Add trend and vol summaries
        for label, freq in sorted(trend_freqs.items()):
            row[f"trend_{label}_pct"] = round(freq, 2)
        for label, freq in sorted(vol_freqs.items()):
            row[f"vol_{label}_pct"] = round(freq, 2)

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 4: Phase C — Regime walk-forward validation
# ---------------------------------------------------------------------------


def validate_regime_walkforward(
    df: pd.DataFrame,
    frozen_trend_sma_threshold: float = 0.005,
    frozen_trend_ret5d_threshold: float = 0.0,
    vol_method: str = "tercile",
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    is_months: int = 12,
    oos_months: int = 3,
    step_months: int = 3,
    challenger_spec: RegimeChallengerSpec | None = None,
) -> dict:
    """Phase C: validate regime label stability across walk-forward folds.

    For each fold:
    1. Recompute vol tercile thresholds on IS data only.
    2. Apply IS-derived thresholds to OOS data.
    3. Also apply global (pre-holdout) thresholds to OOS data.
    4. Measure label agreement between IS-derived and global labels.
    5. Track bucket frequency stability across OOS windows.

    Pass criteria:
    - Bucket frequencies stable: std < 10% of mean across folds.
    - No bucket < 5% of days in any fold.
    - Thresholds don't drift wildly across folds.

    Returns:
        Dict with folds, cross_fold_stability, threshold_drift, pass_criteria.
    """
    from ..optimize.walkforward import generate_windows

    spec = challenger_spec or make_baseline_challenger_spec(
        trend_sma_threshold=frozen_trend_sma_threshold,
        trend_ret5d_threshold=frozen_trend_ret5d_threshold,
        vol_method=vol_method,
    )

    # Build global (pre-holdout) calendar and thresholds
    global_cal = build_extended_regime_calendar(
        df,
        trend_sma_threshold=frozen_trend_sma_threshold,
        trend_ret5d_threshold=frozen_trend_ret5d_threshold,
        vol_method=vol_method,
        holdout_start=holdout_start,
        challenger_spec=spec,
    )
    global_thresholds = compute_vol_thresholds(
        global_cal,
        holdout_start,
        spec.vol.bucketing_method,
        vol_col=spec.vol.feature_col,
    )

    # Generate walk-forward windows within pre-holdout
    data_start = df.index[0].strftime("%Y-%m-%d")
    windows = generate_windows(
        data_start, holdout_start,
        is_months, oos_months, step_months,
    )

    if not windows:
        return {
            "folds": [],
            "cross_fold_stability": {},
            "threshold_drift": {},
            "pass_criteria": {"stable_frequencies": False, "no_sparse_buckets": False},
            "error": "No valid walk-forward windows generated",
        }

    fold_results: list[dict] = []
    all_oos_bucket_freqs: list[dict[str, float]] = []
    all_is_thresholds: list[dict[str, float]] = []

    for fold_idx, window in enumerate(windows):
        # Build IS-only calendar for threshold computation
        is_cal = build_extended_regime_calendar(
            df,
            start_date=window.is_start,
            end_date=window.is_end,
            trend_sma_threshold=frozen_trend_sma_threshold,
            trend_ret5d_threshold=frozen_trend_ret5d_threshold,
            vol_method=vol_method,
            holdout_start=window.is_end,  # Use IS end as "holdout" for threshold computation
            challenger_spec=spec,
        )
        is_thresholds = compute_vol_thresholds(
            is_cal,
            window.is_end,
            spec.vol.bucketing_method,
            vol_col=spec.vol.feature_col,
        )
        all_is_thresholds.append(is_thresholds)

        # Apply IS-derived thresholds to OOS period
        oos_cal_is_thresh = build_extended_regime_calendar(
            df,
            start_date=window.oos_start,
            end_date=window.oos_end,
            trend_sma_threshold=frozen_trend_sma_threshold,
            trend_ret5d_threshold=frozen_trend_ret5d_threshold,
            vol_method=vol_method,
            vol_thresholds=is_thresholds,
            holdout_start=holdout_start,
            challenger_spec=spec,
        )

        # Apply global thresholds to OOS period
        oos_cal_global = build_extended_regime_calendar(
            df,
            start_date=window.oos_start,
            end_date=window.oos_end,
            trend_sma_threshold=frozen_trend_sma_threshold,
            trend_ret5d_threshold=frozen_trend_ret5d_threshold,
            vol_method=vol_method,
            vol_thresholds=global_thresholds,
            holdout_start=holdout_start,
            challenger_spec=spec,
        )

        # Filter to warmup_ok days
        oos_is = oos_cal_is_thresh[oos_cal_is_thresh["warmup_ok"] == True]  # noqa: E712
        oos_gl = oos_cal_global[oos_cal_global["warmup_ok"] == True]  # noqa: E712

        if oos_is.empty or oos_gl.empty:
            continue

        # Label agreement
        n_days = len(oos_is)
        is_labels = oos_is["combined_regime"].values
        gl_labels = oos_gl["combined_regime"].values
        min_len = min(len(is_labels), len(gl_labels))
        agreement = float(np.mean(is_labels[:min_len] == gl_labels[:min_len]))

        # Bucket frequencies for this OOS window (using IS-derived thresholds)
        bucket_freqs = (oos_is["combined_regime"].value_counts() / n_days).to_dict()
        all_oos_bucket_freqs.append(bucket_freqs)

        fold_results.append({
            "fold_idx": fold_idx,
            "is_start": window.is_start,
            "is_end": window.is_end,
            "oos_start": window.oos_start,
            "oos_end": window.oos_end,
            "oos_days": n_days,
            "label_agreement": round(agreement, 4),
            "is_vol_thresholds": {k: round(v, 6) for k, v in is_thresholds.items()},
            "oos_bucket_frequencies": {k: round(v, 4) for k, v in bucket_freqs.items()},
        })

    # Cross-fold stability analysis
    if all_oos_bucket_freqs:
        all_buckets = set()
        for freq_dict in all_oos_bucket_freqs:
            all_buckets.update(freq_dict.keys())

        stability: dict[str, dict] = {}
        sparse_violations: list[str] = []

        for bucket in sorted(all_buckets):
            bucket_values = [f.get(bucket, 0.0) for f in all_oos_bucket_freqs]
            mean_freq = float(np.mean(bucket_values))
            std_freq = float(np.std(bucket_values))
            cv = std_freq / mean_freq if mean_freq > 0 else float("inf")

            stability[bucket] = {
                "mean_frequency": round(mean_freq, 4),
                "std_frequency": round(std_freq, 4),
                "cv": round(cv, 4),
                "min_frequency": round(float(min(bucket_values)), 4),
                "max_frequency": round(float(max(bucket_values)), 4),
            }

            if min(bucket_values) < 0.05:
                sparse_violations.append(bucket)
    else:
        stability = {}
        sparse_violations = []

    # Threshold drift
    if all_is_thresholds:
        low_uppers = [t["low_upper"] for t in all_is_thresholds]
        med_uppers = [t["medium_upper"] for t in all_is_thresholds]
        threshold_drift = {
            "low_upper_mean": round(float(np.mean(low_uppers)), 6),
            "low_upper_std": round(float(np.std(low_uppers)), 6),
            "medium_upper_mean": round(float(np.mean(med_uppers)), 6),
            "medium_upper_std": round(float(np.std(med_uppers)), 6),
            "global_low_upper": global_thresholds["low_upper"],
            "global_medium_upper": global_thresholds["medium_upper"],
        }
    else:
        threshold_drift = {}

    # Pass criteria
    stable_frequencies = all(
        s["cv"] < 0.10 for s in stability.values()
    ) if stability else False
    no_sparse_buckets = len(sparse_violations) == 0

    return {
        "folds": fold_results,
        "global_vol_thresholds": {k: round(v, 6) for k, v in global_thresholds.items()},
        "cross_fold_stability": stability,
        "threshold_drift": threshold_drift,
        "sparse_violations": sparse_violations,
        "pass_criteria": {
            "stable_frequencies": stable_frequencies,
            "no_sparse_buckets": no_sparse_buckets,
        },
        "n_folds": len(fold_results),
        "mean_label_agreement": round(
            float(np.mean([f["label_agreement"] for f in fold_results])), 4
        ) if fold_results else 0.0,
    }


# ---------------------------------------------------------------------------
# Step 5: Phase D — Regime holdout
# ---------------------------------------------------------------------------


def run_regime_holdout(
    df: pd.DataFrame,
    frozen_params: dict,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    holdout_end: str = REGIME_RESEARCH_HOLDOUT_END,
    challenger_spec: RegimeChallengerSpec | None = None,
) -> dict:
    """Phase D: run frozen regime framework on holdout period.

    Confirm the regime map stays interpretable and operationally usable.
    Does NOT retune thresholds.

    Args:
        df: Full 5m OHLCV DataFrame.
        frozen_params: Dict with ``trend_sma_threshold``, ``trend_ret5d_threshold``,
            ``vol_method``, ``vol_thresholds`` (the frozen thresholds from pre-holdout).
        holdout_start: Start of holdout period.
        holdout_end: End of holdout period.

    Returns:
        Dict with holdout distribution, comparison with pre-holdout, and edge cases.
    """
    vol_thresholds = frozen_params.get("vol_thresholds")
    if vol_thresholds is None:
        raise ValueError("frozen_params must include 'vol_thresholds'")
    spec = challenger_spec or make_baseline_challenger_spec(
        trend_sma_threshold=frozen_params.get("trend_sma_threshold", 0.005),
        trend_ret5d_threshold=frozen_params.get("trend_ret5d_threshold", 0.0),
        vol_method=frozen_params.get("vol_method", "tercile"),
    )

    # Build full calendar with frozen thresholds
    full_cal = build_extended_regime_calendar(
        df,
        trend_sma_threshold=frozen_params.get("trend_sma_threshold", 0.005),
        trend_ret5d_threshold=frozen_params.get("trend_ret5d_threshold", 0.0),
        vol_method=frozen_params.get("vol_method", "tercile"),
        vol_thresholds=vol_thresholds,
        holdout_start=holdout_start,
        challenger_spec=spec,
    )

    full_cal["_date_ts"] = pd.to_datetime(full_cal["date"])

    # Split pre-holdout and holdout
    pre = full_cal[
        (full_cal["_date_ts"] < pd.Timestamp(holdout_start))
        & (full_cal["warmup_ok"] == True)  # noqa: E712
    ]
    holdout = full_cal[
        (full_cal["_date_ts"] >= pd.Timestamp(holdout_start))
        & (full_cal["_date_ts"] <= pd.Timestamp(holdout_end))
        & (full_cal["warmup_ok"] == True)  # noqa: E712
    ]

    def _distribution(subset: pd.DataFrame) -> dict[str, float]:
        if subset.empty:
            return {}
        counts = subset["combined_regime"].value_counts()
        return {str(k): round(int(v) / len(subset), 4) for k, v in counts.items()}

    pre_dist = _distribution(pre)
    holdout_dist = _distribution(holdout)

    # Distribution consistency: chi-squared-like comparison
    all_buckets = sorted(set(list(pre_dist.keys()) + list(holdout_dist.keys())))
    distribution_diff = {}
    for bucket in all_buckets:
        pre_pct = pre_dist.get(bucket, 0.0)
        holdout_pct = holdout_dist.get(bucket, 0.0)
        distribution_diff[bucket] = {
            "pre_holdout_pct": round(pre_pct, 4),
            "holdout_pct": round(holdout_pct, 4),
            "diff": round(holdout_pct - pre_pct, 4),
        }

    # Holdout ambiguity
    holdout_full = full_cal[
        (full_cal["_date_ts"] >= pd.Timestamp(holdout_start))
        & (full_cal["_date_ts"] <= pd.Timestamp(holdout_end))
    ]
    holdout_ambiguity = build_regime_confusion_log(holdout_full)

    # Episode counts in holdout
    holdout_episodes = count_regime_episodes(holdout_full, "combined_regime")

    return {
        "holdout_start": holdout_start,
        "holdout_end": holdout_end,
        "holdout_days": int(len(holdout)),
        "pre_holdout_days": int(len(pre)),
        "pre_holdout_distribution": pre_dist,
        "holdout_distribution": holdout_dist,
        "distribution_diff": distribution_diff,
        "holdout_ambiguity_count": len(holdout_ambiguity),
        "holdout_episodes": holdout_episodes.to_dict(orient="records"),
        "frozen_params": {
            k: (round(v, 6) if isinstance(v, float) else v)
            for k, v in frozen_params.items()
            if k != "vol_thresholds"
        },
        "frozen_vol_thresholds": {k: round(v, 6) for k, v in vol_thresholds.items()},
        "challenger_spec": _serialize_challenger_spec(spec),
    }


# ---------------------------------------------------------------------------
# Challenger evaluation helpers
# ---------------------------------------------------------------------------


def _pre_holdout_distribution_concentration(
    regime_calendar: pd.DataFrame,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
) -> float:
    """Return the worst single-year share for any combined bucket pre-holdout."""
    cal = regime_calendar.copy()
    cal["_date_ts"] = pd.to_datetime(cal["date"])
    pre = cal[
        (cal["_date_ts"] < pd.Timestamp(holdout_start))
        & (cal["warmup_ok"] == True)  # noqa: E712
    ].copy()
    if pre.empty:
        return 1.0

    pre["year"] = pd.to_datetime(pre["date"]).dt.year.astype(str)
    worst_share = 0.0
    for _, group in pre.groupby("combined_regime"):
        yearly_counts = group["year"].value_counts()
        if not yearly_counts.empty:
            worst_share = max(worst_share, float(yearly_counts.max() / len(group)))
    return round(worst_share, 4)


def evaluate_challenger_stage_a(
    df: pd.DataFrame,
    spec: RegimeChallengerSpec,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    is_months: int = 12,
    oos_months: int = 3,
    step_months: int = 3,
) -> dict:
    """Run the Stage A framework-only evaluation for a challenger."""
    calendar = build_extended_regime_calendar(
        df,
        holdout_start=holdout_start,
        challenger_spec=spec,
    )
    audit = audit_regime_definition(calendar, holdout_start=holdout_start, challenger_spec=spec)
    walkforward = validate_regime_walkforward(
        df,
        holdout_start=holdout_start,
        is_months=is_months,
        oos_months=oos_months,
        step_months=step_months,
        challenger_spec=spec,
    )
    vol_thresholds = compute_vol_thresholds(
        calendar,
        holdout_start=holdout_start,
        method=spec.vol.bucketing_method,
        vol_col=spec.vol.feature_col,
    )

    pre_summary = audit["pre_holdout_summary"]
    bucket_counts = pre_summary.get("combined_counts", {})
    expected_buckets = _expected_combined_regimes()
    min_bucket_days = min((int(bucket_counts.get(bucket, 0)) for bucket in expected_buckets), default=0)
    episode_rows = {
        str(row["regime"]): int(row["episode_count"])
        for row in audit.get("combined_episodes", [])
    }
    min_bucket_episodes = min((episode_rows.get(bucket, 0) for bucket in expected_buckets), default=0)
    total_pre_holdout_days = int(pre_summary.get("total_days", 0))
    ambiguity_rate = (
        float(pre_summary.get("low_confidence_days", 0)) / total_pre_holdout_days
        if total_pre_holdout_days > 0 else 0.0
    )
    min_bucket_share = float(min_bucket_days / total_pre_holdout_days) if total_pre_holdout_days > 0 else 0.0

    threshold_drift = walkforward.get("threshold_drift", {})
    threshold_drift_score = round(
        float(abs(threshold_drift.get("low_upper_std", 0.0)) + abs(threshold_drift.get("medium_upper_std", 0.0))),
        6,
    )

    return {
        "name": spec.name,
        "family": spec.family,
        "challenger_spec": _serialize_challenger_spec(spec),
        "calendar": calendar,
        "audit": audit,
        "walkforward": walkforward,
        "pre_holdout_vol_thresholds": vol_thresholds,
        "selection_metrics": {
            "total_pre_holdout_days": total_pre_holdout_days,
            "min_bucket_share": round(min_bucket_share, 4),
            "min_bucket_days": int(min_bucket_days),
            "min_bucket_episodes": int(min_bucket_episodes),
            "ambiguity_rate": round(ambiguity_rate, 4),
            "mean_label_agreement": float(walkforward.get("mean_label_agreement", 0.0)),
            "threshold_drift_score": threshold_drift_score,
            "distribution_concentration": _pre_holdout_distribution_concentration(calendar, holdout_start),
        },
        "stage_a_only": True,
        "holdout_excluded": True,
    }


def build_stage_a_scoreboard(
    stage_a_results: Sequence[dict],
    trial_counter: TrialCounter,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
) -> dict:
    """Build a machine-readable Stage A scoreboard."""
    family_counts: dict[str, int] = {}
    rows: list[dict] = []

    for result in stage_a_results:
        family = str(result.get("family", "unknown"))
        family_counts[family] = family_counts.get(family, 0) + 1
        row = {
            "name": result["name"],
            "family": family,
            **result["selection_metrics"],
        }
        rows.append(row)

    rows.sort(key=lambda row: (row["family"], row["name"]))
    return {
        "ranking_period_end": PRE_HOLDOUT_END,
        "holdout_start": holdout_start,
        "holdout_used_for_ranking": False,
        "trial_counts": dict(trial_counter.phases),
        "trial_count_total": trial_counter.total,
        "family_counts": family_counts,
        "rows": rows,
    }


def select_challenger_finalists(
    stage_a_results: Sequence[dict],
    baseline_name: str = "baseline_v1",
    max_ambiguity_delta: float = 0.05,
    min_bucket_share: float = 0.035,
    min_bucket_days: int = 35,
) -> dict:
    """Select the best trend and vol challengers using Stage A metrics only."""
    result_by_name = {result["name"]: result for result in stage_a_results}
    if baseline_name not in result_by_name:
        raise ValueError(f"Baseline '{baseline_name}' not found in stage_a_results")

    baseline_ambiguity = float(result_by_name[baseline_name]["selection_metrics"]["ambiguity_rate"])

    ranked: list[dict] = []
    for result in stage_a_results:
        metrics = result["selection_metrics"]
        reasons: list[str] = []
        if not result["challenger_spec"]["vol"]["live_recreatable"]:
            reasons.append("not_live_recreatable")
        if not result["challenger_spec"]["trend"]["shift_by_one_session"]:
            reasons.append("trend_not_shifted")
        if not result["challenger_spec"]["vol"]["shift_by_one_session"]:
            reasons.append("vol_not_shifted")
        if metrics["min_bucket_share"] < min_bucket_share:
            reasons.append("thin_bucket_share")
        if metrics["min_bucket_days"] < min_bucket_days:
            reasons.append("thin_bucket_days")
        if metrics["ambiguity_rate"] > baseline_ambiguity + max_ambiguity_delta:
            reasons.append("ambiguity_above_baseline_limit")

        ranked.append({
            "name": result["name"],
            "family": result["family"],
            "rejected": bool(reasons),
            "rejection_reasons": reasons,
            "sort_key": (
                float(metrics["threshold_drift_score"]),
                -float(metrics["mean_label_agreement"]),
                -float(metrics["min_bucket_share"]),
                -int(metrics["min_bucket_episodes"]),
                float(metrics["distribution_concentration"]),
                result["name"],
            ),
        })

    def _pick(family: str) -> str | None:
        candidates = [
            row for row in ranked
            if row["family"] == family and not row["rejected"]
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda row: row["sort_key"])[0]["name"]

    best_trend = _pick("trend_only")
    best_vol = _pick("vol_only")
    return {
        "baseline_name": baseline_name,
        "baseline_ambiguity_rate": baseline_ambiguity,
        "best_trend_name": best_trend,
        "best_vol_name": best_vol,
        "ranked": ranked,
    }


def build_combo_challenger_spec(
    trend_result: dict,
    vol_result: dict,
) -> RegimeChallengerSpec:
    """Create the single combo finalist from the winning trend and vol challengers."""
    trend_spec = trend_result["challenger_spec"]["trend"]
    vol_spec = vol_result["challenger_spec"]["vol"]
    return RegimeChallengerSpec(
        name="combo_best_trend_best_vol",
        family="combo",
        trend=TrendFeatureSpec(
            name=str(trend_spec["name"]),
            feature_col=str(trend_spec["feature_col"]),
            formula=str(trend_spec["formula"]),
            bull_threshold=float(trend_spec["bull_threshold"]),
            bear_threshold=float(trend_spec["bear_threshold"]),
            ret5d_threshold=float(trend_spec["ret5d_threshold"]),
            shift_by_one_session=bool(trend_spec["shift_by_one_session"]),
        ),
        vol=VolFeatureSpec(
            name=str(vol_spec["name"]),
            feature_col=str(vol_spec["feature_col"]),
            formula=str(vol_spec["formula"]),
            bucketing_method=str(vol_spec["bucketing_method"]),
            shift_by_one_session=bool(vol_spec["shift_by_one_session"]),
            live_recreatable=bool(vol_spec["live_recreatable"]),
        ),
        low_conf_trend_threshold=float(trend_result["challenger_spec"]["low_conf_trend_threshold"]),
        low_conf_ret5d_threshold=float(trend_result["challenger_spec"]["low_conf_ret5d_threshold"]),
        warmup_length=max(
            int(trend_result["challenger_spec"]["warmup_length"]),
            int(vol_result["challenger_spec"]["warmup_length"]),
        ),
        description="Single combo finalist built from the best Stage A trend and vol challengers.",
    )


# ---------------------------------------------------------------------------
# Step 6: Strategy attribution
# ---------------------------------------------------------------------------


def attribute_strategy_by_regime(
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
) -> pd.DataFrame:
    """Attribute each filled trade to its combined regime bucket.

    Returns a DataFrame with one row per trade, enriched with regime labels
    and period (pre-holdout / holdout).
    """
    filled = _filled_trades(trades)
    if not filled:
        return pd.DataFrame()

    trend_lookup = _regime_lookup(regime_calendar, "regime")
    vol_lookup = _regime_lookup(regime_calendar, "vol_regime")
    combined_lookup = _regime_lookup(regime_calendar, "combined_regime")

    rows = []
    for t in filled:
        rows.append({
            "date": t.date,
            "direction": t.direction,
            "r_multiple": float(t.r_multiple),
            "exit_type": int(t.exit_type),
            "trend_regime": trend_lookup.get(t.date, "unknown"),
            "vol_regime": vol_lookup.get(t.date, "unknown"),
            "combined_regime": combined_lookup.get(t.date, "unknown"),
            "period": "holdout" if t.date >= holdout_start else "pre_holdout",
            "year": t.date[:4],
        })

    return pd.DataFrame(rows)


def compute_bucket_metrics(
    attribution_df: pd.DataFrame,
    group_col: str = "combined_regime",
) -> pd.DataFrame:
    """Compute per-bucket metrics from an attribution DataFrame.

    Returns DataFrame with one row per bucket: trade_count, avg_r, total_r,
    win_rate, profit_factor, max_drawdown_r.
    """
    if attribution_df.empty:
        return pd.DataFrame()

    results = []
    for bucket, group in attribution_df.groupby(group_col):
        rs = group["r_multiple"].values
        n = len(rs)
        wins = int((rs > 0).sum())
        gross_profit = float(rs[rs > 0].sum()) if wins > 0 else 0.0
        gross_loss = float(abs(rs[rs < 0].sum())) if (rs < 0).any() else 0.0

        cum_r = np.cumsum(rs)
        peak = np.maximum.accumulate(cum_r)
        dd = cum_r - peak
        max_dd = float(dd.min()) if len(dd) > 0 else 0.0

        results.append({
            "bucket": str(bucket),
            "trade_count": n,
            "avg_r": round(float(rs.mean()), 4) if n > 0 else 0.0,
            "total_r": round(float(rs.sum()), 4),
            "win_rate": round(wins / n, 4) if n > 0 else 0.0,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else float("inf"),
            "max_drawdown_r": round(max_dd, 4),
        })

    return pd.DataFrame(results).sort_values("total_r", ascending=False).reset_index(drop=True)


def build_attribution_summary(
    attributions: dict[str, pd.DataFrame],
) -> dict:
    """Aggregate attribution across multiple strategies.

    Args:
        attributions: Dict mapping strategy_name -> attribution DataFrame
            (output of ``attribute_strategy_by_regime()``).

    Returns:
        Dict with per-strategy bucket metrics and cross-strategy comparison.
    """
    summary: dict[str, dict] = {}

    for strategy_name, attr_df in attributions.items():
        if attr_df.empty:
            summary[strategy_name] = {"buckets": [], "by_year": []}
            continue

        bucket_metrics = compute_bucket_metrics(attr_df, "combined_regime")
        year_metrics = compute_bucket_metrics(attr_df, "year")

        # Pre-holdout vs holdout split
        pre_df = attr_df[attr_df["period"] == "pre_holdout"]
        holdout_df = attr_df[attr_df["period"] == "holdout"]
        pre_metrics = compute_bucket_metrics(pre_df, "combined_regime") if not pre_df.empty else pd.DataFrame()
        holdout_metrics = compute_bucket_metrics(holdout_df, "combined_regime") if not holdout_df.empty else pd.DataFrame()

        summary[strategy_name] = {
            "buckets": bucket_metrics.to_dict(orient="records"),
            "by_year": year_metrics.to_dict(orient="records"),
            "pre_holdout_buckets": pre_metrics.to_dict(orient="records") if not pre_metrics.empty else [],
            "holdout_buckets": holdout_metrics.to_dict(orient="records") if not holdout_metrics.empty else [],
            "total_trades": len(attr_df),
            "total_r": round(float(attr_df["r_multiple"].sum()), 4),
        }

    return summary


# ---------------------------------------------------------------------------
# Step 7: Specialist promotion
# ---------------------------------------------------------------------------


def evaluate_promotion_criteria(
    strategy_name: str,
    target_regime: str,
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    min_trades: int = 75,
    min_episodes: int = 10,
    max_dominant_year_share: float = 0.50,
    min_specialization_ratio: float = 1.5,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    regime_col: str = "combined_regime",
) -> dict:
    """Evaluate whether a strategy qualifies for specialist promotion.

    Checks:
    1. Positive in-regime expectancy (avg_r > 0)
    2. Specialization ratio >= min_specialization_ratio
    3. Enough trades in target regime (>= min_trades)
    4. Enough distinct regime episodes with trades (>= min_episodes)
    5. Not single-year dominated (<= max_dominant_year_share)

    Returns dict with pass/fail per criterion, computed values, and overall verdict.
    """
    filled = _filled_trades(trades)
    lookup = _regime_lookup(regime_calendar, regime_col)

    # Split trades by regime — pre-holdout only to avoid contamination
    in_regime = [
        t for t in filled
        if lookup.get(t.date) == target_regime and t.date < holdout_start
    ]
    out_regime = [
        t for t in filled
        if lookup.get(t.date) not in (target_regime, "warmup", None) and t.date < holdout_start
    ]

    in_metrics = compute_metrics(in_regime)
    out_metrics = compute_metrics(out_regime)

    in_avg_r = float(in_metrics.get("avg_r", 0.0))
    out_avg_r = float(out_metrics.get("avg_r", 0.0))
    in_trades = int(in_metrics.get("total_trades", 0))

    # Specialization ratio
    if out_metrics.get("total_trades", 0) == 0:
        spec_ratio = float("inf") if in_avg_r > 0 else 0.0
    elif out_avg_r <= 0 and in_avg_r > 0:
        spec_ratio = float("inf")
    else:
        spec_ratio = in_avg_r / max(abs(out_avg_r), 1e-9)

    # Episode counting: how many distinct regime episodes had at least one trade
    # Pre-holdout only to avoid holdout contamination
    cal = regime_calendar[regime_calendar["warmup_ok"] == True].copy()  # noqa: E712
    cal["_date_ts"] = pd.to_datetime(cal["date"])
    cal = cal[cal["_date_ts"] < pd.Timestamp(holdout_start)]
    cal = cal.sort_values("date").reset_index(drop=True)
    cal["_episode_id"] = (cal[regime_col] != cal[regime_col].shift()).cumsum()

    target_episodes = cal[cal[regime_col] == target_regime]
    if not target_episodes.empty:
        episode_ids = set(target_episodes["_episode_id"])
        # Count how many of these episodes have at least one trade
        trade_dates = {t.date for t in in_regime}
        cal_date_strs = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
        episodes_with_trades = set()
        for _, row in target_episodes.iterrows():
            date_str = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
            if date_str in trade_dates:
                episodes_with_trades.add(row["_episode_id"])
        n_episodes_with_trades = len(episodes_with_trades)
        n_total_episodes = len(episode_ids)
    else:
        n_episodes_with_trades = 0
        n_total_episodes = 0

    # Dominant year share
    dom_year_share = _dominant_year_share(in_metrics)

    # Criteria evaluation
    criteria = {
        "positive_in_regime_expectancy": {
            "pass": in_avg_r > 0,
            "value": round(in_avg_r, 4),
            "threshold": "> 0",
        },
        "specialization_ratio": {
            "pass": spec_ratio >= min_specialization_ratio,
            "value": _json_number(spec_ratio),
            "threshold": f">= {min_specialization_ratio}",
        },
        "min_in_regime_trades": {
            "pass": in_trades >= min_trades,
            "value": in_trades,
            "threshold": f">= {min_trades}",
        },
        "min_episodes_with_trades": {
            "pass": n_episodes_with_trades >= min_episodes,
            "value": n_episodes_with_trades,
            "total_target_episodes": n_total_episodes,
            "threshold": f">= {min_episodes}",
        },
        "not_single_year_dominated": {
            "pass": dom_year_share <= max_dominant_year_share,
            "value": round(dom_year_share, 4),
            "threshold": f"<= {max_dominant_year_share}",
        },
    }

    all_pass = all(c["pass"] for c in criteria.values())

    return {
        "strategy_name": strategy_name,
        "target_regime": target_regime,
        "promoted": all_pass,
        "criteria": criteria,
        "in_regime_metrics": _metrics_snapshot(in_metrics),
        "out_regime_metrics": _metrics_snapshot(out_metrics),
    }


# ---------------------------------------------------------------------------
# Step 8: Specialist optimization within regime
# ---------------------------------------------------------------------------


def make_regime_gate(
    regime_calendar: pd.DataFrame,
    target_regime: str,
    regime_col: str = "combined_regime",
) -> Callable[[list[TradeResult]], list[TradeResult]]:
    """Create a post-trade gate that keeps only target-regime trades.

    Operates on trade dates (strings), so it is safe to use as a simple
    ``gate_fn`` in walk-forward optimization (no bar-index dependency).
    """
    lookup = _regime_lookup(regime_calendar, regime_col)

    def gate(trades: list[TradeResult]) -> list[TradeResult]:
        return [t for t in trades if lookup.get(t.date) == target_regime]

    return gate


def optimize_specialist_in_regime(
    df: pd.DataFrame,
    base_config: StrategyConfig,
    regime_calendar: pd.DataFrame,
    target_regime: str,
    param_ranges: dict[str, list],
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    is_months: int = 12,
    oos_months: int = 3,
    step_months: int = 3,
    objective: str = "calmar",
    n_workers: int | None = None,
    regime_col: str = "combined_regime",
    df_1m: pd.DataFrame | None = None,
    df_1s: pd.DataFrame | None = None,
) -> dict:
    """Walk-forward optimize a strategy within target-regime observations only.

    Uses ``make_regime_gate()`` as ``gate_fn`` in ``run_walkforward()``, so only
    target-regime trades are scored during IS optimization and OOS evaluation.

    Args:
        df: Full 5m OHLCV DataFrame.
        base_config: Base strategy configuration.
        regime_calendar: Extended regime calendar with combined_regime column.
        target_regime: Target combined regime (e.g., ``"bull_high_vol"``).
        param_ranges: Dict mapping param names to lists of values to sweep.
        holdout_start: Pre-holdout end date.
        is_months: Walk-forward IS months.
        oos_months: Walk-forward OOS months.
        step_months: Walk-forward step months.
        objective: Optimization objective (``"calmar"``, ``"sharpe"``, etc.).
        n_workers: Parallel workers for grid search.
        regime_col: Column name for regime lookup.
        df_1m: Optional 1m data for bar magnifier.
        df_1s: Optional 1s data for bar magnifier.

    Returns:
        Dict with walk-forward result summary, best params per fold,
        combined OOS metrics, and trial count.
    """
    from ..optimize.walkforward import run_walkforward

    gate = make_regime_gate(regime_calendar, target_regime, regime_col)

    # Slice data to pre-holdout to prevent walk-forward from generating
    # folds that overlap with the holdout period.
    pre_holdout_df = df.loc[:holdout_start]
    pre_holdout_1m = df_1m.loc[:holdout_start] if df_1m is not None else None
    pre_holdout_1s = df_1s.loc[:holdout_start] if df_1s is not None else None

    wf_result = run_walkforward(
        df=pre_holdout_df,
        base_config=base_config,
        param_ranges=param_ranges,
        is_months=is_months,
        oos_months=oos_months,
        step_months=step_months,
        objective=objective,
        n_workers=n_workers,
        start_date=pre_holdout_df.index[0].strftime("%Y-%m-%d"),
        gate_fn=gate,
        df_1m=pre_holdout_1m,
        df_1s=pre_holdout_1s,
    )

    # Total configs evaluated across all folds
    from ..optimize.grid import generate_param_grid
    n_configs = len(generate_param_grid(base_config, param_ranges))
    trial_count = n_configs * len(wf_result.folds)

    # Best params per fold
    fold_summaries = []
    for fold in wf_result.folds:
        fold_summaries.append({
            "fold_idx": fold.fold_index,
            "is_period": f"{fold.is_start} to {fold.is_end}",
            "oos_period": f"{fold.oos_start} to {fold.oos_end}",
            "best_params": fold.best_params,
            "is_objective": round(fold.is_objective_value, 4),
            "oos_objective": round(fold.oos_objective_value, 4),
            "oos_trades": len([t for t in fold.oos_trades if t.exit_type != EXIT_NO_FILL]),
        })

    combined_oos_metrics = _metrics_snapshot(wf_result.combined_oos_metrics)

    return {
        "target_regime": target_regime,
        "objective": objective,
        "n_folds": len(wf_result.folds),
        "n_configs_per_fold": n_configs,
        "trial_count": trial_count,
        "walk_forward_efficiency": round(wf_result.walk_forward_efficiency, 4),
        "combined_oos_metrics": combined_oos_metrics,
        "fold_summaries": fold_summaries,
    }


# ---------------------------------------------------------------------------
# Step 9: Full gated system validation
# ---------------------------------------------------------------------------


def validate_gated_system(
    specialists: dict[str, dict],
    regime_calendar: pd.DataFrame,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
    regime_col: str = "combined_regime",
) -> dict:
    """Validate the full regime-gated specialist system across all dates.

    Args:
        specialists: Dict mapping target_regime -> {
            "trades": list[TradeResult],
            "config": StrategyConfig (optional),
        }
        regime_calendar: Extended regime calendar.
        holdout_start: Holdout start date.
        regime_col: Column for regime lookup.

    Returns:
        Dict with per-specialist metrics, combined system metrics,
        gate activation rates, and holdout performance.
    """
    lookup = _regime_lookup(regime_calendar, regime_col)
    specialist_results: dict[str, dict] = {}
    all_gated_trades: list[TradeResult] = []

    for target_regime, spec_data in specialists.items():
        trades = spec_data["trades"]
        filled = _filled_trades(trades)

        # Gated: only target-regime trades
        gated = [t for t in filled if lookup.get(t.date) == target_regime]
        # Non-target: would have fired outside target regime
        non_target = [t for t in filled if lookup.get(t.date) not in (target_regime, "warmup", None)]

        gated_metrics = compute_metrics(gated)
        non_target_metrics = compute_metrics(non_target)
        full_metrics = compute_metrics(filled)

        n_filled = len(filled)
        n_gated = len(gated)
        n_non_target = len(non_target)

        # Pre-holdout / holdout split
        gated_pre = [t for t in gated if t.date < holdout_start]
        gated_holdout = [t for t in gated if t.date >= holdout_start]
        pre_metrics = compute_metrics(gated_pre)
        holdout_metrics = compute_metrics(gated_holdout)

        specialist_results[target_regime] = {
            "ungated_trades": n_filled,
            "gated_trades": n_gated,
            "non_target_trades": n_non_target,
            "gate_activation_rate": round(n_non_target / n_filled, 4) if n_filled > 0 else 0.0,
            "gated_metrics": _metrics_snapshot(gated_metrics),
            "non_target_metrics": _metrics_snapshot(non_target_metrics),
            "full_ungated_metrics": _metrics_snapshot(full_metrics),
            "pre_holdout_metrics": _metrics_snapshot(pre_metrics),
            "holdout_metrics": _metrics_snapshot(holdout_metrics),
        }

        all_gated_trades.extend(gated)

    # Combined system metrics
    all_gated_trades.sort(key=lambda t: (t.date, t.signal_bar))
    combined_metrics = compute_metrics(all_gated_trades)
    combined_pre = [t for t in all_gated_trades if t.date < holdout_start]
    combined_holdout = [t for t in all_gated_trades if t.date >= holdout_start]

    # Coverage: fraction of target-regime days with at least one trade
    # Split by pre-holdout and holdout for clean reporting
    warmup_ok_cal = regime_calendar[regime_calendar["warmup_ok"] == True].copy()  # noqa: E712
    warmup_ok_cal["_date_str"] = pd.to_datetime(warmup_ok_cal["date"]).dt.strftime("%Y-%m-%d")
    warmup_ok_cal["_date_ts"] = pd.to_datetime(warmup_ok_cal["date"])

    # Target-regime days (days where at least one specialist is active)
    active_regimes = set(specialists.keys())
    target_days = set(
        warmup_ok_cal[warmup_ok_cal[regime_col].isin(active_regimes)]["_date_str"]
    )

    all_trade_dates = {t.date for t in all_gated_trades}
    pre_trade_dates = {t.date for t in combined_pre}
    holdout_trade_dates = {t.date for t in combined_holdout}

    pre_target_days = set(
        warmup_ok_cal[
            (warmup_ok_cal[regime_col].isin(active_regimes))
            & (warmup_ok_cal["_date_ts"] < pd.Timestamp(holdout_start))
        ]["_date_str"]
    )
    holdout_target_days = set(
        warmup_ok_cal[
            (warmup_ok_cal[regime_col].isin(active_regimes))
            & (warmup_ok_cal["_date_ts"] >= pd.Timestamp(holdout_start))
        ]["_date_str"]
    )

    coverage_all = len(all_trade_dates & target_days) / len(target_days) if target_days else 0.0
    coverage_pre = len(pre_trade_dates & pre_target_days) / len(pre_target_days) if pre_target_days else 0.0
    coverage_holdout = len(holdout_trade_dates & holdout_target_days) / len(holdout_target_days) if holdout_target_days else 0.0

    return {
        "specialist_results": specialist_results,
        "combined_system": {
            "total_gated_trades": len(all_gated_trades),
            "combined_metrics": _metrics_snapshot(combined_metrics),
            "pre_holdout_metrics": _metrics_snapshot(compute_metrics(combined_pre)),
            "holdout_metrics": _metrics_snapshot(compute_metrics(combined_holdout)),
            "target_day_coverage_rate": round(coverage_all, 4),
            "pre_holdout_coverage_rate": round(coverage_pre, 4),
            "holdout_coverage_rate": round(coverage_holdout, 4),
        },
    }


# ---------------------------------------------------------------------------
# Step 10: Prop downstream evaluation
# ---------------------------------------------------------------------------


def evaluate_prop_downstream(
    specialist_name: str,
    gated_trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    profile: PropFirmProfile | None = None,
    risk_per_r_usd: float = 5000.0,
    holdout_start: str = REGIME_RESEARCH_HOLDOUT_START,
) -> dict:
    """Run prop-firm staggered account simulation on regime-gated trades.

    Wraps existing ``simulate_account_attempts()`` + ``build_prop_scorecard()``
    from ``prop_regime_specialist``.

    Returns dict with account outcomes summary and scorecard.
    """
    if profile is None:
        profile = PropFirmProfile()

    trading_dates = trading_dates_from_calendar(regime_calendar)

    # Pre-holdout trades only for account simulation
    pre_holdout_trades = [t for t in gated_trades if t.date < holdout_start]

    outcomes = simulate_account_attempts(
        specialist_name=specialist_name,
        trades=pre_holdout_trades,
        trading_dates=[d for d in trading_dates if d < holdout_start],
        profile=profile,
        risk_per_r_usd=risk_per_r_usd,
    )

    scorecard = build_prop_scorecard(outcomes, profile)

    return {
        "specialist_name": specialist_name,
        "n_pre_holdout_trades": len(_filled_trades(pre_holdout_trades)),
        "n_account_attempts": len(outcomes),
        "scorecard": scorecard,
    }
