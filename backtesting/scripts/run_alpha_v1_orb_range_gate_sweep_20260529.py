#!/usr/bin/env python3
"""Broad ORB range gate search for ALPHA_V1 ORB legs.

This is an attribution/search pass, not an engine promotion. It annotates
cached ALPHA exact trade streams with causal ORB range context and sweeps
two-sided percentile bands to see whether "middle-sized" ORBs have promise.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.signals.daily_atr import compute_daily_atr  # noqa: E402


RUN_SLUG = "alpha_v1_orb_range_gate_sweep_20260529"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_RANGE_GATE_SWEEP_20260529.md"

PRIMARY_STREAM = ROOT / "data" / "results" / "alpha_v1_recent_payout_sim_20260506" / "trade_stream.csv"
SPLIT_EXACT_STREAM = (
    ROOT / "data" / "results" / "alpha_v1_single_vs_split_exact_compare_20260506" / "split_exact_trades.csv"
)
FEE_AWARE_STREAM = ROOT / "data" / "results" / "alpha_v1_payout_with_fees_20260507" / "exact_trades_by_profile.csv"

ORB_LEGS = {
    "nq_asia_orb",
    "es_asia_orb",
    "es_ny_orb",
    "nq_ny_orb_r11",
}


@dataclass(frozen=True)
class LegSpec:
    label: str
    symbol: str
    orb_start: str
    orb_end: str
    atr_length: int


LEG_SPECS = {
    "nq_asia_orb": LegSpec("NQ Asia ORB", "NQ", "20:00", "20:15", 5),
    "es_asia_orb": LegSpec("ES Asia ORB", "ES", "20:00", "20:15", 14),
    "es_ny_orb": LegSpec("ES NY ORB", "ES", "09:30", "09:45", 7),
    "nq_ny_orb_r11": LegSpec("NQ NY ORB R11", "NQ", "09:30", "09:50", 12),
}

PCT_THRESHOLDS = sorted({0.0, 0.1, 0.2, 0.25, 0.3, 1 / 3, 0.4, 0.5, 0.6, 2 / 3, 0.7, 0.75, 0.8, 0.9, 1.0})
ATR_PCT_THRESHOLDS = [0.0, 5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0, 25.0, 30.0, 40.0, 60.0, 100.0]
WINDOWS = {
    "full": None,
    "2024+": "2024-01-01",
    "2025+": "2025-01-01",
}


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


def _load_5m(symbol: str) -> pd.DataFrame:
    candidates = [
        ROOT / "data" / "raw" / f"{symbol}_5m.parquet",
        ROOT / "data" / "cache" / "nq_ny_lsi_cisd_sequence" / f"{symbol}_5m.parquet",
    ]
    for path in candidates:
        if path.exists():
            df = pd.read_parquet(path).sort_index()
            return df[["open", "high", "low", "close"]].copy()
    raise FileNotFoundError(f"No 5m parquet found for {symbol}: {candidates}")


def _orb_context_for_leg(leg: str) -> pd.DataFrame:
    spec = LEG_SPECS[leg]
    df = _load_5m(spec.symbol)
    atr = compute_daily_atr(df, length=spec.atr_length)
    df = df.copy()
    df["daily_atr"] = atr
    mask = _time_mask(df.index, spec.orb_start, spec.orb_end)
    orb = (
        df.loc[mask]
        .groupby(df.loc[mask].index.date)
        .agg(
            orb_open=("open", "first"),
            orb_high=("high", "max"),
            orb_low=("low", "min"),
            orb_close=("close", "last"),
            daily_atr=("daily_atr", "first"),
        )
    )
    orb.index = pd.to_datetime(orb.index)
    orb["date"] = orb.index.date.astype(str)
    orb["leg"] = leg
    orb["leg_label"] = spec.label
    orb["symbol"] = spec.symbol
    orb["orb_start"] = spec.orb_start
    orb["orb_end"] = spec.orb_end
    orb["atr_length"] = spec.atr_length
    orb["orb_range"] = orb["orb_high"] - orb["orb_low"]
    orb["orb_range_pctile60"] = _rolling_percentile(orb["orb_range"], window=60, min_periods=10)
    orb["orb_atr_pct"] = np.where(
        orb["daily_atr"] > 0,
        orb["orb_range"] / orb["daily_atr"] * 100.0,
        np.nan,
    )
    return orb.reset_index(drop=True)


def _normalise_primary_stream() -> pd.DataFrame:
    df = pd.read_csv(PRIMARY_STREAM)
    df = df[df["leg"].isin(ORB_LEGS)].copy()
    df["stream"] = "alpha_v1_active_exact_full"
    df["stream_label"] = "ALPHA_V1 active exact stream"
    df["r_for_eval"] = df["r_multiple"].astype(float)
    return df


def _normalise_split_exact_stream() -> pd.DataFrame:
    df = pd.read_csv(SPLIT_EXACT_STREAM)
    df = df[df["comparison_leg"].isin({"es_asia_orb", "es_ny_orb", "nq_ny_orb_r11"})].copy()
    df["leg"] = df["comparison_leg"]
    df["stream"] = "split_exact_counterparts"
    df["stream_label"] = "Exact split counterpart streams"
    df["r_for_eval"] = df["r_multiple"].astype(float)
    return df


def _normalise_fee_stream() -> pd.DataFrame:
    df = pd.read_csv(FEE_AWARE_STREAM)
    df = df[(df["profile"] == "aggressive_sprint") & df["leg"].isin(ORB_LEGS)].copy()
    df["stream"] = "alpha_v1_fee_aware_aggressive_2023"
    df["stream_label"] = "ALPHA_V1 fee-aware aggressive sprint 2023+"
    df["r_for_eval"] = df["net_r_multiple"].astype(float)
    return df


def _load_streams() -> pd.DataFrame:
    frames = [
        _normalise_primary_stream(),
        _normalise_split_exact_stream(),
        _normalise_fee_stream(),
    ]
    keep = ["stream", "stream_label", "leg", "date", "entry_time", "exit_time", "r_for_eval"]
    out = pd.concat([frame[keep] for frame in frames], ignore_index=True)
    out["date"] = out["date"].astype(str)
    out["entry_ts"] = pd.to_datetime(out["entry_time"], utc=True, errors="coerce")
    out["exit_ts"] = pd.to_datetime(out["exit_time"], utc=True, errors="coerce")
    out = out[out["exit_ts"].notna()].copy()
    return out.sort_values(["stream", "leg", "exit_ts"]).reset_index(drop=True)


def _metrics(values: pd.Series) -> dict[str, Any]:
    r = values.astype(float).to_numpy()
    if len(r) == 0:
        return {
            "trades": 0,
            "total_r": 0.0,
            "avg_r": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_dd_r": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
        }
    wins = r[r > 0]
    losses = r[r < 0]
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    total_r = float(np.sum(r))
    max_dd_r = float(np.min(dd)) if len(dd) else 0.0
    std = float(np.std(r, ddof=1)) if len(r) > 1 else 0.0
    return {
        "trades": int(len(r)),
        "total_r": total_r,
        "avg_r": float(np.mean(r)),
        "win_rate": float(np.mean(r > 0)),
        "profit_factor": float(abs(np.sum(wins) / np.sum(losses))) if np.sum(losses) < 0 else 0.0,
        "max_dd_r": max_dd_r,
        "sharpe": float(np.mean(r) / std * np.sqrt(252.0)) if std > 0 else 0.0,
        "calmar": float(total_r / abs(max_dd_r)) if max_dd_r < 0 else 0.0,
    }


def _round(value: Any, digits: int = 3) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _metric_row(prefix: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        f"{prefix}_trades": metrics["trades"],
        f"{prefix}_total_r": _round(metrics["total_r"], 2),
        f"{prefix}_avg_r": _round(metrics["avg_r"], 4),
        f"{prefix}_wr_pct": _round(metrics["win_rate"] * 100.0, 2),
        f"{prefix}_pf": _round(metrics["profit_factor"], 3),
        f"{prefix}_dd_r": _round(metrics["max_dd_r"], 2),
        f"{prefix}_sharpe": _round(metrics["sharpe"], 3),
        f"{prefix}_calmar": _round(metrics["calmar"], 3),
    }


def _band_label(feature: str, lo: float, hi: float) -> str:
    if feature == "orb_range_pctile60":
        return f"{lo:.0%}-{hi:.0%}"
    return f"{lo:.1f}-{hi:.1f}"


def _sweep_feature(df: pd.DataFrame, *, feature: str, thresholds: list[float]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = ["stream", "stream_label", "leg", "leg_label"]
    for keys, group in df.groupby(group_cols, dropna=False):
        stream, stream_label, leg, leg_label = keys
        valid_group = group[group[feature].notna()].copy()
        if valid_group.empty:
            continue
        baseline = _metrics(valid_group["r_for_eval"])
        for lo in thresholds:
            for hi in thresholds:
                if not lo < hi:
                    continue
                kept = valid_group[(valid_group[feature] >= lo) & (valid_group[feature] <= hi)].copy()
                if kept.empty:
                    continue
                kept_m = _metrics(kept["r_for_eval"])
                keep_pct = kept_m["trades"] / baseline["trades"] * 100.0 if baseline["trades"] else 0.0
                dd_improvement = kept_m["max_dd_r"] - baseline["max_dd_r"]
                row = {
                    "stream": stream,
                    "stream_label": stream_label,
                    "leg": leg,
                    "leg_label": leg_label,
                    "feature": feature,
                    "band": _band_label(feature, lo, hi),
                    "lo": _round(lo, 4),
                    "hi": _round(hi, 4),
                    "keep_pct": _round(keep_pct, 2),
                    "delta_total_r": _round(kept_m["total_r"] - baseline["total_r"], 2),
                    "delta_avg_r": _round(kept_m["avg_r"] - baseline["avg_r"], 4),
                    "delta_dd_r": _round(dd_improvement, 2),
                    "delta_pf": _round(kept_m["profit_factor"] - baseline["profit_factor"], 3),
                    "delta_calmar": _round(kept_m["calmar"] - baseline["calmar"], 3),
                    "quality_score": _round(
                        (kept_m["avg_r"] - baseline["avg_r"]) * 100.0
                        + max(0.0, dd_improvement) * 1.5
                        + (kept_m["profit_factor"] - baseline["profit_factor"]) * 2.0
                        - max(0.0, baseline["total_r"] - kept_m["total_r"]) * 0.05,
                        4,
                    ),
                    **_metric_row("base", baseline),
                    **_metric_row("kept", kept_m),
                }
                rows.append(row)
    return pd.DataFrame(rows)


def _portfolio_sweep(df: pd.DataFrame, *, feature: str, thresholds: list[float]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (stream, stream_label), group in df.groupby(["stream", "stream_label"], dropna=False):
        valid_group = group[group[feature].notna()].copy()
        if valid_group.empty:
            continue
        baseline = _metrics(valid_group.sort_values("exit_ts")["r_for_eval"])
        for lo in thresholds:
            for hi in thresholds:
                if not lo < hi:
                    continue
                kept = valid_group[(valid_group[feature] >= lo) & (valid_group[feature] <= hi)].copy()
                if kept.empty:
                    continue
                kept = kept.sort_values("exit_ts")
                kept_m = _metrics(kept["r_for_eval"])
                keep_pct = kept_m["trades"] / baseline["trades"] * 100.0 if baseline["trades"] else 0.0
                dd_improvement = kept_m["max_dd_r"] - baseline["max_dd_r"]
                rows.append(
                    {
                        "stream": stream,
                        "stream_label": stream_label,
                        "leg": "portfolio_orb",
                        "leg_label": "ORB sleeve portfolio",
                        "feature": feature,
                        "band": _band_label(feature, lo, hi),
                        "lo": _round(lo, 4),
                        "hi": _round(hi, 4),
                        "keep_pct": _round(keep_pct, 2),
                        "delta_total_r": _round(kept_m["total_r"] - baseline["total_r"], 2),
                        "delta_avg_r": _round(kept_m["avg_r"] - baseline["avg_r"], 4),
                        "delta_dd_r": _round(dd_improvement, 2),
                        "delta_pf": _round(kept_m["profit_factor"] - baseline["profit_factor"], 3),
                        "delta_calmar": _round(kept_m["calmar"] - baseline["calmar"], 3),
                        "quality_score": _round(
                            (kept_m["avg_r"] - baseline["avg_r"]) * 100.0
                            + max(0.0, dd_improvement) * 1.5
                            + (kept_m["profit_factor"] - baseline["profit_factor"]) * 2.0
                            - max(0.0, baseline["total_r"] - kept_m["total_r"]) * 0.05,
                            4,
                        ),
                        **_metric_row("base", baseline),
                        **_metric_row("kept", kept_m),
                    }
                )
    return pd.DataFrame(rows)


def _window_summary(df: pd.DataFrame, *, start: str | None) -> pd.DataFrame:
    subset = df.copy()
    if start is not None:
        subset = subset[subset["date"] >= start].copy()
    rows: list[dict[str, Any]] = []
    for keys, group in subset.groupby(["stream", "stream_label", "leg", "leg_label"], dropna=False):
        stream, stream_label, leg, leg_label = keys
        metrics = _metrics(group.sort_values("exit_ts")["r_for_eval"])
        rows.append(
            {
                "stream": stream,
                "stream_label": stream_label,
                "leg": leg,
                "leg_label": leg_label,
                **_metric_row("base", metrics),
            }
        )
    return pd.DataFrame(rows)


def _bucket_summary(df: pd.DataFrame) -> pd.DataFrame:
    bins = [0.0, 0.2, 1 / 3, 0.5, 2 / 3, 0.8, 1.0]
    labels = ["0-20", "20-33", "33-50", "50-67", "67-80", "80-100"]
    tmp = df[df["orb_range_pctile60"].notna()].copy()
    tmp["pctile_bucket"] = pd.cut(tmp["orb_range_pctile60"], bins=bins, labels=labels, include_lowest=True)
    rows: list[dict[str, Any]] = []
    for keys, group in tmp.groupby(["stream", "stream_label", "leg", "leg_label", "pctile_bucket"], dropna=True):
        stream, stream_label, leg, leg_label, bucket = keys
        metrics = _metrics(group.sort_values("exit_ts")["r_for_eval"])
        rows.append(
            {
                "stream": stream,
                "stream_label": stream_label,
                "leg": leg,
                "leg_label": leg_label,
                "pctile_bucket": str(bucket),
                **_metric_row("bucket", metrics),
            }
        )
    return pd.DataFrame(rows)


def _top_candidates(sweeps: pd.DataFrame) -> pd.DataFrame:
    candidates = sweeps[
        (sweeps["feature"] == "orb_range_pctile60")
        & (sweeps["kept_trades"] >= np.maximum(40, sweeps["base_trades"] * 0.25))
        & (sweeps["keep_pct"] <= 90.0)
        & (sweeps["keep_pct"] >= 25.0)
    ].copy()
    if candidates.empty:
        return candidates
    candidates["net_positive"] = candidates["delta_total_r"] >= 0
    candidates = candidates.sort_values(
        ["stream", "leg", "net_positive", "quality_score", "delta_dd_r", "delta_avg_r"],
        ascending=[True, True, False, False, False, False],
    )
    return candidates.groupby(["stream", "leg"], as_index=False).head(8)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _write_report(
    *,
    annotated: pd.DataFrame,
    baseline: pd.DataFrame,
    top: pd.DataFrame,
    bucket: pd.DataFrame,
    portfolio_top: pd.DataFrame,
) -> None:
    primary_top = top[top["stream"] == "alpha_v1_active_exact_full"].copy()
    primary_cols = [
        "leg_label",
        "band",
        "kept_trades",
        "keep_pct",
        "kept_total_r",
        "delta_total_r",
        "kept_avg_r",
        "delta_avg_r",
        "kept_pf",
        "delta_pf",
        "kept_dd_r",
        "delta_dd_r",
        "quality_score",
    ]
    primary_best = (
        primary_top.sort_values(["leg", "quality_score"], ascending=[True, False])
        .groupby("leg", as_index=False)
        .head(3)
    )
    portfolio_cols = [
        "stream_label",
        "band",
        "kept_trades",
        "keep_pct",
        "kept_total_r",
        "delta_total_r",
        "kept_avg_r",
        "delta_avg_r",
        "kept_pf",
        "delta_pf",
        "kept_dd_r",
        "delta_dd_r",
        "quality_score",
    ]
    portfolio_best = portfolio_top.sort_values(["stream", "quality_score"], ascending=[True, False]).groupby("stream").head(5)

    baseline_cols = [
        "stream_label",
        "leg_label",
        "base_trades",
        "base_total_r",
        "base_avg_r",
        "base_wr_pct",
        "base_pf",
        "base_dd_r",
        "base_calmar",
    ]
    base_primary = baseline[baseline["stream"] == "alpha_v1_active_exact_full"].sort_values("leg")

    bucket_primary = bucket[bucket["stream"] == "alpha_v1_active_exact_full"].copy()
    bucket_cols = ["leg_label", "pctile_bucket", "bucket_trades", "bucket_total_r", "bucket_avg_r", "bucket_pf", "bucket_dd_r"]

    lines = [
        "# ALPHA_V1 ORB Range Gate Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        "- Purpose: broad post-filter search for ORB range percentile sweet spots, especially `orb_mid`-style bands that skip tiny and extreme-large opening ranges.",
        "- Primary stream: `alpha_v1_recent_payout_sim_20260506/trade_stream.csv` active exact ORB legs, `2016-04-17` through `2026-03-24`.",
        "- Secondary streams: exact split counterparts for ES Asia / ES NY / NQ R11, plus current fee-aware aggressive sprint trades from `2023-01-01` through `2026-03-24`.",
        "- ORB range percentile: rolling 60 completed session ranges, current session included after ORB completion; minimum 10 prior/current observations.",
        "- Status: `post_filter_only` / `research_only`; no live pre-arm ORB-size gate exists yet.",
        "",
        "## Primary Baseline",
        "",
        _markdown_table(base_primary.to_dict("records"), baseline_cols),
        "",
        "## Operating Read",
        "",
        "- The active ORB sleeve has a real quality-concentration effect, but the evidence does not support a simple hard rule that skips both tiny and very large ORBs across all legs.",
        "- Sleeve-wide `40%-67%` ORB percentile kept only `27%` of trades but improved average R/trade (`0.186R -> 0.232R`), PF (`1.397 -> 1.503`), and max DD (`-19.87R -> -10.78R`). It also gave up `-347.2R` of total edge, so this is more promising as a risk throttle or specialist sleeve than a full replacement.",
        "- Do not blindly skip all high ORBs: the `80%-100%` sleeve bucket remained strong, and ES NY, NQ Asia, and NQ R11 each had profitable very-large ORB buckets. The weak high-range pocket is mostly `67%-80%`, not the full high tail.",
        "- ES Asia is the cleanest true-gate follow-up: `0%-20%` and `67%-100%` underperformed, while `20%-67%` improved PF/DD versus baseline. This deserves a causal engine replay before any promotion.",
        "- ES NY, NQ Asia, and NQ R11 are not clean `orb_mid` candidates because each has at least one strong non-mid bucket. For those legs, treat ORB size as context or sizing input, not an outright skip rule.",
        "",
        "## Best Primary Percentile Bands",
        "",
        _markdown_table(primary_best.to_dict("records"), primary_cols),
        "",
        "## Portfolio-Level Bands",
        "",
        _markdown_table(portfolio_best.to_dict("records"), portfolio_cols),
        "",
        "## Primary Percentile Bucket Attribution",
        "",
        _markdown_table(bucket_primary.to_dict("records"), bucket_cols),
        "",
        "## Files",
        "",
        f"- Annotated trades: `backtesting/data/results/{RUN_SLUG}/annotated_trades.csv`",
        f"- Band sweep: `backtesting/data/results/{RUN_SLUG}/band_sweep.csv`",
        f"- Top candidates: `backtesting/data/results/{RUN_SLUG}/top_candidates.csv`",
        f"- Bucket summary: `backtesting/data/results/{RUN_SLUG}/bucket_summary.csv`",
        f"- Baseline summary: `backtesting/data/results/{RUN_SLUG}/baseline_summary.csv`",
        "",
        "## Interpretation Notes",
        "",
        "- A positive `delta_avg_r` with large negative `delta_total_r` means the band concentrates quality but gives up too much flow for a sleeve-wide replacement.",
        "- A positive `delta_dd_r` means drawdown improved because max DD became less negative.",
        "- These bands are searched directly on the evaluation stream; promotion would need causal engine support, exact replay, and out-of-sample validation.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    context = pd.concat([_orb_context_for_leg(leg) for leg in sorted(ORB_LEGS)], ignore_index=True)
    trades = _load_streams()
    annotated = trades.merge(
        context[
            [
                "leg",
                "date",
                "leg_label",
                "symbol",
                "orb_start",
                "orb_end",
                "atr_length",
                "orb_range",
                "daily_atr",
                "orb_range_pctile60",
                "orb_atr_pct",
            ]
        ],
        on=["leg", "date"],
        how="left",
    )
    annotated = annotated[annotated["leg"].isin(ORB_LEGS)].copy()
    annotated = annotated.sort_values(["stream", "leg", "exit_ts"]).reset_index(drop=True)

    baseline = pd.concat([_window_summary(annotated, start=start).assign(window=window) for window, start in WINDOWS.items()])
    primary_window = baseline[baseline["window"] == "full"].copy()

    pct_sweep = _sweep_feature(annotated, feature="orb_range_pctile60", thresholds=PCT_THRESHOLDS)
    atr_sweep = _sweep_feature(annotated, feature="orb_atr_pct", thresholds=ATR_PCT_THRESHOLDS)
    portfolio_pct = _portfolio_sweep(annotated, feature="orb_range_pctile60", thresholds=PCT_THRESHOLDS)
    portfolio_atr = _portfolio_sweep(annotated, feature="orb_atr_pct", thresholds=ATR_PCT_THRESHOLDS)
    sweeps = pd.concat([pct_sweep, atr_sweep, portfolio_pct, portfolio_atr], ignore_index=True)
    bucket = _bucket_summary(annotated)
    top = _top_candidates(sweeps)
    portfolio_top = sweeps[
        (sweeps["leg"] == "portfolio_orb")
        & (sweeps["feature"] == "orb_range_pctile60")
        & (sweeps["kept_trades"] >= np.maximum(100, sweeps["base_trades"] * 0.25))
        & (sweeps["keep_pct"] <= 90.0)
        & (sweeps["keep_pct"] >= 25.0)
    ].copy()

    annotated.to_csv(RESULT_DIR / "annotated_trades.csv", index=False)
    sweeps.to_csv(RESULT_DIR / "band_sweep.csv", index=False)
    top.to_csv(RESULT_DIR / "top_candidates.csv", index=False)
    bucket.to_csv(RESULT_DIR / "bucket_summary.csv", index=False)
    baseline.to_csv(RESULT_DIR / "baseline_summary.csv", index=False)
    context.to_csv(RESULT_DIR / "orb_context.csv", index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "primary_stream": str(PRIMARY_STREAM.relative_to(ROOT)),
        "report": str(REPORT_PATH.relative_to(ROOT)),
        "result_dir": str(RESULT_DIR.relative_to(ROOT)),
        "annotated_rows": int(len(annotated)),
        "missing_orb_context_rows": int(annotated["orb_range_pctile60"].isna().sum()),
        "streams": sorted(annotated["stream"].unique().tolist()),
        "primary_baseline": primary_window[primary_window["stream"] == "alpha_v1_active_exact_full"].to_dict("records"),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_report(
        annotated=annotated,
        baseline=primary_window,
        top=top,
        bucket=bucket,
        portfolio_top=portfolio_top,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
