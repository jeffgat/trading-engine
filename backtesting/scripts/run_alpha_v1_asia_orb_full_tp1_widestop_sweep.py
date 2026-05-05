#!/usr/bin/env python3
"""Sweep full-exit-at-TP1 behavior for large-stop ALPHA_V1 Asia ORB trades."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import (
    build_alpha_v1_legs,
    filled_trades,
    portfolio_daily_frame,
    summarize_daily_returns,
)
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.instruments import Instrument
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import TradeResult
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_asia_orb_full_tp1_widestop_sweep_20260504"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ASIA_ORB_FULL_TP1_WIDESTOP_SWEEP_20260504.md"

FULL_START = "2016-04-17"
LEG_KEYS = ("nq_asia_orb_long", "es_asia_orb_long")
THRESHOLD_GRID = {
    "nq_asia_orb_long": (5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0),
    "es_asia_orb_long": (3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 15.0, 20.0),
}
WINDOW_STARTS = {
    "full": FULL_START,
    "2024_plus": "2024-01-01",
    "2025_plus": "2025-01-01",
}


@dataclass
class LoadedData:
    df_5m: pd.DataFrame
    df_1m: pd.DataFrame | None
    df_1s: pd.DataFrame | None


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
        if abs(value) >= 100 or value == int(value):
            return f"{value:.0f}"
        return f"{value:.2f}"
    return str(value)


def _threshold_label(value: float) -> str:
    return str(value).replace(".", "p")


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body]) if body else "\n".join([header, sep])


def _resample_agg(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open"])


def _load_market_data(instrument: Instrument, *, end_date: str) -> LoadedData:
    df_1s: pd.DataFrame | None = None
    try:
        df_5m = load_5m_data(instrument.data_file, start=FULL_START, end=end_date)
    except FileNotFoundError:
        df_5m = None
    try:
        df_1m = load_1m_for_5m(instrument.data_file, start=FULL_START, end=end_date)
    except FileNotFoundError:
        df_1m = None
    try:
        df_1s = load_1s_for_5m(instrument.data_file, start=FULL_START, end=end_date)
    except FileNotFoundError:
        pass
    if df_5m is None or df_1m is None:
        if df_1s is None:
            raise FileNotFoundError(f"{instrument.symbol} is missing 5m/1m bars and no 1s fallback is available.")
        if df_1m is None:
            df_1m = _resample_agg(df_1s, "1min")
        if df_5m is None:
            df_5m = _resample_agg(df_1s, "5min")
    return LoadedData(df_5m=df_5m, df_1m=df_1m, df_1s=df_1s)


def _available_end(instruments: list[Instrument]) -> str:
    ends = []
    for instrument in instruments:
        try:
            df = load_5m_data(instrument.data_file, start=FULL_START, end=None)
        except FileNotFoundError:
            df = load_1s_for_5m(instrument.data_file, start=FULL_START, end=None)
        ends.append(pd.Timestamp(df.index.max()).date())
    return min(ends).isoformat()


def _window_bounds(overlap_end: str) -> dict[str, tuple[str, str]]:
    end_ts = pd.Timestamp(overlap_end)
    return {
        **{key: (start, overlap_end) for key, start in WINDOW_STARTS.items()},
        "last_1y": ((end_ts - pd.Timedelta(days=365)).date().isoformat(), overlap_end),
    }


def _sort_trades(trades: list[TradeResult]) -> list[TradeResult]:
    return sorted(trades, key=lambda t: (t.date, t.session, t.fill_bar, t.signal_bar, t.exit_bar))


def _filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end]


def _make_config(base: StrategyConfig, leg_key: str, threshold: float | None) -> StrategyConfig:
    if threshold is None:
        name = f"{leg_key}_baseline"
        return with_overrides(
            base,
            name=name,
            notes="ALPHA_V1 Asia ORB baseline for full-TP1 large-stop sweep.",
            wide_stop_target_threshold_points=0.0,
            wide_stop_target_rr=0.0,
            wide_stop_full_exit_at_tp1=False,
        )
    label = _threshold_label(threshold)
    name = f"{leg_key}_full_tp1_sl{label}"
    return with_overrides(
        base,
        name=name,
        notes=(
            "ALPHA_V1 Asia ORB full-exit-at-normal-TP1 large-stop sweep. "
            f"large_sl_threshold_points={threshold}."
        ),
        wide_stop_target_threshold_points=threshold,
        wide_stop_target_rr=0.0,
        wide_stop_full_exit_at_tp1=True,
    )


def _run_configs(
    data: LoadedData,
    configs: list[StrategyConfig],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    results = run_sweep(
        data.df_5m,
        configs,
        n_workers=min(6, len(configs)),
        start_date=start_date,
        end_date=end_date,
        df_1m=data.df_1m,
        df_1s=data.df_1s,
    )
    by_name: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        by_name[config.name] = _sort_trades(trades)
    return by_name


def _risk_distribution(trades: list[TradeResult]) -> dict[str, Any]:
    risks = np.array([trade.risk_points for trade in filled_trades(trades) if trade.risk_points > 0], dtype=float)
    if len(risks) == 0:
        return {
            "fills": 0,
            "risk_min": None,
            "risk_p50": None,
            "risk_p75": None,
            "risk_p90": None,
            "risk_max": None,
        }
    return {
        "fills": int(len(risks)),
        "risk_min": _round(float(np.min(risks)), 2),
        "risk_p50": _round(float(np.quantile(risks, 0.50)), 2),
        "risk_p75": _round(float(np.quantile(risks, 0.75)), 2),
        "risk_p90": _round(float(np.quantile(risks, 0.90)), 2),
        "risk_max": _round(float(np.max(risks)), 2),
    }


def _metric_row(
    *,
    scope: str,
    variant: str,
    threshold: float | None,
    window: str,
    trades: list[TradeResult],
    baseline: dict[str, Any] | None = None,
    daily_streams: dict[str, list[TradeResult]] | None = None,
) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    if daily_streams is not None:
        daily = portfolio_daily_frame({name: filled_trades(stream) for name, stream in daily_streams.items()})
        total_series = daily.sum(axis=1) if not daily.empty else pd.Series(dtype=float)
        daily_summary = summarize_daily_returns(total_series)
        max_dd_r = float(daily_summary["max_drawdown_r"])
        sharpe = float(daily_summary["sharpe_ratio"])
    else:
        max_dd_r = float(metrics["max_drawdown_r"])
        sharpe = float(metrics["sharpe_ratio"])
    r_by_year = metrics.get("r_by_year") or {}
    row = {
        "scope": scope,
        "variant": variant,
        "large_sl_threshold_points": threshold,
        "window": window,
        "signals": int(metrics["total_signals"]),
        "fills": int(metrics["total_trades"]),
        "net_r": _round(metrics["total_r"], 2),
        "win_rate_pct": _pct(metrics["win_rate"]),
        "profit_factor": _round(metrics["profit_factor"], 2),
        "avg_r": _round(metrics["avg_r"], 3),
        "sharpe_ratio": _round(sharpe, 2),
        "max_drawdown_r": _round(max_dd_r, 2),
        "negative_years": int(sum(1 for value in r_by_year.values() if value < 0)),
        "exit_breakdown": json.dumps(metrics.get("exit_breakdown", {}), sort_keys=True),
        "deployability": "research_only",
        "live_support_notes": (
            "Research simulator supports wide_stop_full_exit_at_tp1; live execution support and exact replay parity are not yet wired."
        ),
        "exact_replay_required": True,
    }
    if baseline is not None:
        row["delta_net_r"] = _round(float(row["net_r"]) - float(baseline["net_r"]), 2)
        row["delta_dd_r"] = _round(float(row["max_drawdown_r"]) - float(baseline["max_drawdown_r"]), 2)
        row["delta_fills"] = int(row["fills"]) - int(baseline["fills"])
    else:
        row["delta_net_r"] = 0.0
        row["delta_dd_r"] = 0.0
        row["delta_fills"] = 0
    return row


def _top_rows(rows: list[dict[str, Any]], *, scope: str, window: str, limit: int = 8) -> list[dict[str, Any]]:
    filtered = [
        row for row in rows
        if row["scope"] == scope and row["window"] == window and row["variant"] != "baseline"
    ]
    return sorted(
        filtered,
        key=lambda row: (
            float(row["net_r"]),
            float(row["delta_dd_r"]),
            float(row["profit_factor"] or 0),
        ),
        reverse=True,
    )[:limit]


def _write_report(
    *,
    overlap_end: str,
    risk_rows: list[dict[str, Any]],
    leg_rows: list[dict[str, Any]],
    combo_rows: list[dict[str, Any]],
) -> None:
    baseline_combo = [row for row in combo_rows if row["variant"] == "baseline"]
    report_lines = [
        "# ALPHA_V1 Asia ORB Full-TP1 Wide-Stop Sweep (2026-05-04)",
        "",
        f"- Window: `{FULL_START}` to `{overlap_end}`",
        "- Scope: `NQ Asia ORB` and `ES Asia ORB` only.",
        "- Test: if `risk_points >= large_sl_threshold_points`, exit the full trade at the normal TP1 level instead of taking a partial at TP1 and targeting TP2.",
        "- Baseline behavior and all entries/stops/re-entry caps remain unchanged.",
        "- Deployability: all rows are `research_only` until execution/exact replay support for `wide_stop_full_exit_at_tp1` is wired.",
        "",
        "## Baseline Risk Distribution",
        "",
        _markdown_table(
            risk_rows,
            ["leg", "fills", "risk_min", "risk_p50", "risk_p75", "risk_p90", "risk_max"],
        ),
        "",
        "## Two-Leg Baseline",
        "",
        _markdown_table(
            baseline_combo,
            [
                "window",
                "fills",
                "net_r",
                "profit_factor",
                "sharpe_ratio",
                "max_drawdown_r",
                "negative_years",
            ],
        ),
        "",
        "## Best NQ Asia Rows",
        "",
        _markdown_table(
            _top_rows(leg_rows, scope="nq_asia_orb_long", window="full"),
            [
                "large_sl_threshold_points",
                "fills",
                "net_r",
                "delta_net_r",
                "profit_factor",
                "max_drawdown_r",
                "delta_dd_r",
                "negative_years",
            ],
        ),
        "",
        "## Best ES Asia Rows",
        "",
        _markdown_table(
            _top_rows(leg_rows, scope="es_asia_orb_long", window="full"),
            [
                "large_sl_threshold_points",
                "fills",
                "net_r",
                "delta_net_r",
                "profit_factor",
                "max_drawdown_r",
                "delta_dd_r",
                "negative_years",
            ],
        ),
        "",
        "## Best Combined NQ+ES Asia Rows",
        "",
        _markdown_table(
            _top_rows(combo_rows, scope="combined_nq_es_asia_orb", window="full", limit=10),
            [
                "variant",
                "fills",
                "net_r",
                "delta_net_r",
                "profit_factor",
                "sharpe_ratio",
                "max_drawdown_r",
                "delta_dd_r",
                "negative_years",
            ],
        ),
        "",
        "## Recent Combined Check",
        "",
        _markdown_table(
            _top_rows(combo_rows, scope="combined_nq_es_asia_orb", window="2025_plus", limit=10),
            [
                "variant",
                "fills",
                "net_r",
                "delta_net_r",
                "profit_factor",
                "sharpe_ratio",
                "max_drawdown_r",
                "delta_dd_r",
                "negative_years",
            ],
        ),
        "",
        "## Read",
        "",
    ]
    best_nq = _top_rows(leg_rows, scope="nq_asia_orb_long", window="full", limit=1)
    best_es = _top_rows(leg_rows, scope="es_asia_orb_long", window="full", limit=1)
    best_combo = _top_rows(combo_rows, scope="combined_nq_es_asia_orb", window="full", limit=1)
    if best_nq:
        report_lines.append(
            f"- NQ Asia best full-history threshold is `{best_nq[0]['large_sl_threshold_points']}` points, "
            f"but its full-history delta is `{best_nq[0]['delta_net_r']}R`."
        )
    if best_es:
        report_lines.append(
            f"- ES Asia best full-history threshold is `{best_es[0]['large_sl_threshold_points']}` points, "
            f"with full-history delta `{best_es[0]['delta_net_r']}R`."
        )
    if best_combo:
        report_lines.append(
            f"- Combined best full-history pair is `{best_combo[0]['variant']}` with delta "
            f"`{best_combo[0]['delta_net_r']}R` and DD change `{best_combo[0]['delta_dd_r']}R`."
        )
    report_lines.extend(
        [
            "- Treat this as a research-only exit-management probe, not a deployable config, until live sizing/order handling can close the entire remaining position at TP1 conditionally by stop size.",
            "",
            "## Artifacts",
            "",
            f"- Result directory: `{RESULT_DIR.relative_to(ROOT)}`",
            "- `leg_metrics_by_window.csv`",
            "- `combined_metrics_by_window.csv`",
            "- `risk_distribution.csv`",
            "- `summary.json`",
        ]
    )
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    legs = build_alpha_v1_legs()
    selected = {key: legs[key] for key in LEG_KEYS}
    overlap_end = _available_end(sorted({leg.config.instrument for leg in selected.values()}, key=lambda i: i.symbol))
    windows = _window_bounds(overlap_end)
    print(f"Overlap window: {FULL_START} to {overlap_end}", flush=True)

    leg_streams: dict[str, dict[str, list[TradeResult]]] = {}
    leg_thresholds: dict[str, dict[str, float | None]] = {}
    risk_rows: list[dict[str, Any]] = []

    for leg_key, leg in selected.items():
        print(f"\n[{leg_key}] loading data", flush=True)
        data = _load_market_data(leg.config.instrument, end_date=overlap_end)
        thresholds = {f"sl{_threshold_label(value)}": value for value in THRESHOLD_GRID[leg_key]}
        leg_thresholds[leg_key] = {"baseline": None, **thresholds}
        configs = [_make_config(leg.config, leg_key, threshold) for threshold in leg_thresholds[leg_key].values()]
        print(f"[{leg_key}] running {len(configs)} configs", flush=True)
        by_name = _run_configs(data, configs, start_date=FULL_START, end_date=overlap_end)
        streams: dict[str, list[TradeResult]] = {}
        for variant, threshold in leg_thresholds[leg_key].items():
            streams[variant] = by_name[_make_config(leg.config, leg_key, threshold).name]
        leg_streams[leg_key] = streams
        risk_rows.append({"leg": leg_key, **_risk_distribution(streams["baseline"])})

    leg_rows: list[dict[str, Any]] = []
    for leg_key, streams in leg_streams.items():
        for window_name, (start, end) in windows.items():
            baseline_row = _metric_row(
                scope=leg_key,
                variant="baseline",
                threshold=None,
                window=window_name,
                trades=_filter_window(streams["baseline"], start, end),
            )
            leg_rows.append(baseline_row)
            for variant, trades in streams.items():
                if variant == "baseline":
                    continue
                leg_rows.append(
                    _metric_row(
                        scope=leg_key,
                        variant=variant,
                        threshold=leg_thresholds[leg_key][variant],
                        window=window_name,
                        trades=_filter_window(trades, start, end),
                        baseline=baseline_row,
                    )
                )

    combo_rows: list[dict[str, Any]] = []
    nq_variants = list(leg_streams["nq_asia_orb_long"].keys())
    es_variants = list(leg_streams["es_asia_orb_long"].keys())
    for window_name, (start, end) in windows.items():
        baseline_streams = {
            "nq_asia_orb_long": _filter_window(leg_streams["nq_asia_orb_long"]["baseline"], start, end),
            "es_asia_orb_long": _filter_window(leg_streams["es_asia_orb_long"]["baseline"], start, end),
        }
        baseline_merged = _sort_trades([trade for stream in baseline_streams.values() for trade in stream])
        baseline_row = _metric_row(
            scope="combined_nq_es_asia_orb",
            variant="baseline",
            threshold=None,
            window=window_name,
            trades=baseline_merged,
            daily_streams=baseline_streams,
        )
        combo_rows.append(baseline_row)
        for nq_variant in nq_variants:
            for es_variant in es_variants:
                if nq_variant == "baseline" and es_variant == "baseline":
                    continue
                variant = f"nq_{nq_variant}__es_{es_variant}"
                streams = {
                    "nq_asia_orb_long": _filter_window(leg_streams["nq_asia_orb_long"][nq_variant], start, end),
                    "es_asia_orb_long": _filter_window(leg_streams["es_asia_orb_long"][es_variant], start, end),
                }
                merged = _sort_trades([trade for stream in streams.values() for trade in stream])
                combo_rows.append(
                    _metric_row(
                        scope="combined_nq_es_asia_orb",
                        variant=variant,
                        threshold=None,
                        window=window_name,
                        trades=merged,
                        baseline=baseline_row,
                        daily_streams=streams,
                    )
                )

    pd.DataFrame(risk_rows).to_csv(RESULT_DIR / "risk_distribution.csv", index=False)
    pd.DataFrame(leg_rows).to_csv(RESULT_DIR / "leg_metrics_by_window.csv", index=False)
    pd.DataFrame(combo_rows).to_csv(RESULT_DIR / "combined_metrics_by_window.csv", index=False)
    summary = {
        "full_start": FULL_START,
        "overlap_end": overlap_end,
        "threshold_grid": THRESHOLD_GRID,
        "windows": windows,
        "top_nq_full": _top_rows(leg_rows, scope="nq_asia_orb_long", window="full", limit=10),
        "top_es_full": _top_rows(leg_rows, scope="es_asia_orb_long", window="full", limit=10),
        "top_combined_full": _top_rows(combo_rows, scope="combined_nq_es_asia_orb", window="full", limit=10),
        "top_combined_2025_plus": _top_rows(combo_rows, scope="combined_nq_es_asia_orb", window="2025_plus", limit=10),
        "deployability": "research_only",
        "live_support_notes": "Requires live/exact-replay support for conditional full exit at TP1 by stop size.",
        "exact_replay_required": True,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    _write_report(overlap_end=overlap_end, risk_rows=risk_rows, leg_rows=leg_rows, combo_rows=combo_rows)
    print(json.dumps({"report": str(REPORT_PATH), "result_dir": str(RESULT_DIR)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
