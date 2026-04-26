"""Validate the ALPHA_V1 ORB conditioned cap=2 rule over full available history.

Validation design:
- Freeze the engine rule at orb_trade_max_per_session=2 and
  orb_reentry_policy=after_nonpositive_first
- Compare against cap=1 baseline and cap=2 any-reentry
- Check three major windows:
  * historical pre-recent: 2016-04-17 to 2024-04-16
  * recent available: 2024-04-17 to 2026-03-24
  * full available history: 2016-04-17 to 2026-03-24
- Check rolling 2-year windows stepped yearly across the same history

Note: current repo data ends on 2026-03-24, so the "10-year" check uses the
full available history from 2016-04-17 through 2026-03-24.
"""

from __future__ import annotations

import gc
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import (
    build_alpha_v1_legs,
    filled_trades,
    portfolio_daily_frame,
    summarize_daily_returns,
)
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import TradeResult, build_maps, build_signal_cache
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_cap2_conditioned_10y_validation"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_CAP2_CONDITIONED_10Y_VALIDATION.md"

FULL_START = "2016-04-17"
RECENT_START = "2024-04-17"
PRE_RECENT_END = "2024-04-16"
AVAILABLE_END = "2026-03-24"

ORB_LEG_KEYS = (
    "nq_asia_orb_long",
    "es_asia_orb_long",
    "es_ny_orb_long",
)
LEG_LABELS = {
    "nq_asia_orb_long": "NQ Asia ORB",
    "es_asia_orb_long": "ES Asia ORB",
    "es_ny_orb_long": "ES NY ORB",
}
VARIANTS = {
    "cap1_baseline": {
        "trade_cap": 1,
        "reentry_policy": "any_reentry",
        "label": "cap=1 baseline",
    },
    "cap2_any_reentry": {
        "trade_cap": 2,
        "reentry_policy": "any_reentry",
        "label": "cap=2 any re-entry",
    },
    "cap2_after_nonpositive_first": {
        "trade_cap": 2,
        "reentry_policy": "after_nonpositive_first",
        "label": "cap=2 after nonpositive first trade",
    },
}
MAJOR_WINDOWS = (
    {
        "key": "historical_pre_recent",
        "label": "Historical pre-recent",
        "start": FULL_START,
        "end": PRE_RECENT_END,
        "group": "major",
    },
    {
        "key": "recent_available",
        "label": "Recent available",
        "start": RECENT_START,
        "end": AVAILABLE_END,
        "group": "major",
    },
    {
        "key": "full_available",
        "label": "Full available history",
        "start": FULL_START,
        "end": AVAILABLE_END,
        "group": "major",
    },
)


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


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |")
    return "\n".join([header, sep, *body]) if body else "\n".join([header, sep])


def _window_years(start: str, end: str) -> float:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    return round(((end_ts - start_ts).days + 1) / 365.25, 2)


def _rolling_windows() -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    start_ts = pd.Timestamp(FULL_START)
    available_end_ts = pd.Timestamp(AVAILABLE_END)
    idx = 1
    while True:
        end_ts = start_ts + pd.DateOffset(years=2) - pd.Timedelta(days=1)
        if end_ts > available_end_ts:
            break
        windows.append(
            {
                "key": f"rolling_{idx:02d}",
                "label": f"Rolling {idx:02d}",
                "start": start_ts.date().isoformat(),
                "end": end_ts.date().isoformat(),
                "group": "rolling",
            }
        )
        start_ts = start_ts + pd.DateOffset(years=1)
        idx += 1
    return windows


def _daily_sleeve_summary(named_streams: dict[str, list[TradeResult]]) -> dict[str, Any]:
    filled_streams = {name: filled_trades(trades) for name, trades in named_streams.items()}
    daily = portfolio_daily_frame(filled_streams)
    total_series = daily.sum(axis=1) if not daily.empty else pd.Series(dtype=float)
    summary = summarize_daily_returns(total_series)
    fill_count = sum(len(stream) for stream in filled_streams.values())
    return {
        "fills": fill_count,
        "total_r": _round(summary["total_r"], 2),
        "max_drawdown_r": _round(summary["max_drawdown_r"], 2),
        "sharpe_ratio": _round(summary["sharpe_ratio"], 2),
        "calmar_ratio": _round(summary["calmar_ratio"], 2),
        "negative_days": int(summary["negative_days"]),
    }


def _variant_config(base_config: StrategyConfig, leg_key: str, variant_key: str) -> StrategyConfig:
    spec = VARIANTS[variant_key]
    return with_overrides(
        base_config,
        name=f"{leg_key}_{variant_key}",
        notes="ALPHA_V1 ORB 10y conditioned cap=2 validation.",
        orb_trade_max_per_session=spec["trade_cap"],
        orb_reentry_policy=spec["reentry_policy"],
    )


def _load_market_data(base_config: StrategyConfig) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    df_5m = load_5m_data(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    try:
        df_1m = load_1m_for_5m(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    except FileNotFoundError:
        df_1m = None
    try:
        df_1s = load_1s_for_5m(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    except FileNotFoundError:
        df_1s = None
    return df_5m, df_1m, df_1s


def _run_window(
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame | None,
    df_1s: pd.DataFrame | None,
    configs: list[StrategyConfig],
    maps: dict,
    signal_cache: dict,
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    results = run_sweep(
        df_5m,
        configs,
        n_workers=min(len(configs), 6),
        start_date=start_date,
        end_date=end_date,
        df_1m=df_1m,
        df_1s=df_1s,
        _prebuilt_maps=maps,
        _prebuilt_signal_cache=signal_cache,
    )
    by_name: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        by_name[config.name] = trades
    return by_name


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    windows = [*MAJOR_WINDOWS, *_rolling_windows()]
    legs = build_alpha_v1_legs()
    orb_legs = {key: legs[key] for key in ORB_LEG_KEYS}
    grouped_leg_keys: dict[str, list[str]] = defaultdict(list)
    for leg_key in ORB_LEG_KEYS:
        grouped_leg_keys[orb_legs[leg_key].config.instrument.symbol].append(leg_key)

    window_variant_streams: dict[str, dict[str, dict[str, list[TradeResult]]]] = {
        window["key"]: {variant: {} for variant in VARIANTS}
        for window in windows
    }

    for symbol, leg_keys in grouped_leg_keys.items():
        base_config = orb_legs[leg_keys[0]].config
        df_5m, df_1m, df_1s = _load_market_data(base_config)
        actual_end = pd.Timestamp(df_5m.index.max()).date().isoformat()
        if actual_end != AVAILABLE_END:
            raise ValueError(
                f"Expected available end {AVAILABLE_END} for {symbol}, got {actual_end}."
            )

        configs: list[StrategyConfig] = []
        config_by_leg_variant: dict[tuple[str, str], StrategyConfig] = {}
        for leg_key in leg_keys:
            for variant_key in VARIANTS:
                config = _variant_config(orb_legs[leg_key].config, leg_key, variant_key)
                configs.append(config)
                config_by_leg_variant[(leg_key, variant_key)] = config

        print(f"[validation] Loading maps for {symbol} ({len(df_5m):,} 5m rows)")
        maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
        print(f"[validation] Building signal cache for {symbol}")
        signal_cache = build_signal_cache(df_5m, configs)

        for window in windows:
            print(
                f"[validation] {symbol} {window['label']} "
                f"({window['start']} to {window['end']})"
            )
            by_name = _run_window(
                df_5m,
                df_1m,
                df_1s,
                configs,
                maps,
                signal_cache,
                start_date=window["start"],
                end_date=window["end"],
            )
            for leg_key in leg_keys:
                for variant_key in VARIANTS:
                    config = config_by_leg_variant[(leg_key, variant_key)]
                    window_variant_streams[window["key"]][variant_key][leg_key] = by_name[config.name]

        del maps
        del signal_cache
        del df_5m
        del df_1m
        del df_1s
        gc.collect()

    major_rows: list[dict[str, Any]] = []
    combined_by_window_variant: dict[tuple[str, str], dict[str, Any]] = {}
    for window in windows:
        baseline_total_r = None
        cap2_any_total_r = None
        for variant_key, spec in VARIANTS.items():
            sleeve = _daily_sleeve_summary(window_variant_streams[window["key"]][variant_key])
            if variant_key == "cap1_baseline":
                baseline_total_r = sleeve["total_r"]
            if variant_key == "cap2_any_reentry":
                cap2_any_total_r = sleeve["total_r"]
            row = {
                "window_key": window["key"],
                "window": f"{window['start']} to {window['end']}",
                "label": window["label"],
                "window_group": window["group"],
                "years": _window_years(window["start"], window["end"]),
                "variant": variant_key,
                "cap": spec["trade_cap"],
                "reentry_policy": spec["reentry_policy"],
                **sleeve,
                "r_per_year": _round(sleeve["total_r"] / _window_years(window["start"], window["end"]), 2),
                "delta_vs_cap1_r": _round(sleeve["total_r"] - baseline_total_r, 2) if baseline_total_r is not None else 0.0,
                "delta_vs_cap2_any_r": _round(sleeve["total_r"] - cap2_any_total_r, 2) if cap2_any_total_r is not None else None,
            }
            combined_by_window_variant[(window["key"], variant_key)] = row
            if window["group"] == "major":
                major_rows.append(row)

    rolling_rows: list[dict[str, Any]] = []
    rolling_total_beats = 0
    rolling_sharpe_beats = 0
    rolling_cond_sharpe_vs_any = 0
    rolling_cond_dd_better_than_any = 0
    for window in windows:
        if window["group"] != "rolling":
            continue
        baseline = combined_by_window_variant[(window["key"], "cap1_baseline")]
        any_reentry = combined_by_window_variant[(window["key"], "cap2_any_reentry")]
        conditioned = combined_by_window_variant[(window["key"], "cap2_after_nonpositive_first")]
        delta_r = conditioned["total_r"] - baseline["total_r"]
        delta_sharpe = conditioned["sharpe_ratio"] - baseline["sharpe_ratio"]
        if delta_r > 0:
            rolling_total_beats += 1
        if delta_sharpe > 0:
            rolling_sharpe_beats += 1
        if conditioned["sharpe_ratio"] > any_reentry["sharpe_ratio"]:
            rolling_cond_sharpe_vs_any += 1
        if conditioned["max_drawdown_r"] > any_reentry["max_drawdown_r"]:
            rolling_cond_dd_better_than_any += 1
        rolling_rows.append(
            {
                "window": f"{window['start']} to {window['end']}",
                "years": _window_years(window["start"], window["end"]),
                "baseline_total_r": baseline["total_r"],
                "cap2_any_total_r": any_reentry["total_r"],
                "conditioned_total_r": conditioned["total_r"],
                "conditioned_delta_vs_cap1_r": _round(delta_r, 2),
                "conditioned_delta_vs_cap2_any_r": _round(conditioned["total_r"] - any_reentry["total_r"], 2),
                "baseline_sharpe": baseline["sharpe_ratio"],
                "cap2_any_sharpe": any_reentry["sharpe_ratio"],
                "conditioned_sharpe": conditioned["sharpe_ratio"],
                "conditioned_max_drawdown_r": conditioned["max_drawdown_r"],
            }
        )

    rolling_scorecard = {
        "rolling_windows": len(rolling_rows),
        "conditioned_beats_cap1_total_r_windows": rolling_total_beats,
        "conditioned_beats_cap1_sharpe_windows": rolling_sharpe_beats,
        "conditioned_beats_cap2_any_sharpe_windows": rolling_cond_sharpe_vs_any,
        "conditioned_has_better_drawdown_than_cap2_any_windows": rolling_cond_dd_better_than_any,
        "conditioned_median_delta_vs_cap1_r": _round(
            pd.Series([row["conditioned_delta_vs_cap1_r"] for row in rolling_rows]).median(),
            2,
        ) if rolling_rows else None,
        "conditioned_mean_delta_vs_cap1_r": _round(
            pd.Series([row["conditioned_delta_vs_cap1_r"] for row in rolling_rows]).mean(),
            2,
        ) if rolling_rows else None,
    }

    full_leg_rows: list[dict[str, Any]] = []
    for leg_key in ORB_LEG_KEYS:
        baseline_total_r = None
        cap2_any_total_r = None
        for variant_key, spec in VARIANTS.items():
            trades = window_variant_streams["full_available"][variant_key][leg_key]
            metrics = compute_metrics(trades)
            if variant_key == "cap1_baseline":
                baseline_total_r = metrics["total_r"]
            if variant_key == "cap2_any_reentry":
                cap2_any_total_r = metrics["total_r"]
            full_leg_rows.append(
                {
                    "leg": LEG_LABELS[leg_key],
                    "variant": variant_key,
                    "cap": spec["trade_cap"],
                    "reentry_policy": spec["reentry_policy"],
                    "fills": int(metrics["total_trades"]),
                    "win_rate_pct": _pct(metrics["win_rate"]),
                    "avg_r": _round(metrics["avg_r"], 2),
                    "total_r": _round(metrics["total_r"], 2),
                    "r_per_year": _round(metrics["total_r"] / _window_years(FULL_START, AVAILABLE_END), 2),
                    "delta_vs_cap1_r": _round(metrics["total_r"] - baseline_total_r, 2) if baseline_total_r is not None else 0.0,
                    "delta_vs_cap2_any_r": _round(metrics["total_r"] - cap2_any_total_r, 2) if cap2_any_total_r is not None else None,
                    "sharpe_ratio": _round(metrics["sharpe_ratio"], 2),
                    "max_drawdown_r": _round(metrics["max_drawdown_r"], 2),
                }
            )

    report_lines = [
        "# ALPHA_V1 ORB Cap=2 Conditioned 10-Year Validation",
        "",
        "- Requested check: validate the engine-backed `cap=2 + after_nonpositive_first` rule against the full available history.",
        f"- Available data window used: `{FULL_START}` to `{AVAILABLE_END}`.",
        "- Current repo data ends on `2026-03-24`, so this is the longest available history rather than a literal through-today 10-year span.",
        "- Rolling windows: full 2-year windows stepped yearly; the most recent partial window is shown separately in the major-window table.",
        "",
        "## Major Windows",
        "",
        _markdown_table(
            major_rows,
            [
                "label",
                "window",
                "years",
                "variant",
                "fills",
                "total_r",
                "r_per_year",
                "delta_vs_cap1_r",
                "delta_vs_cap2_any_r",
                "sharpe_ratio",
                "max_drawdown_r",
                "negative_days",
            ],
        ),
        "",
        "## Rolling 2-Year Scorecard",
        "",
        _markdown_table(
            [rolling_scorecard],
            [
                "rolling_windows",
                "conditioned_beats_cap1_total_r_windows",
                "conditioned_beats_cap1_sharpe_windows",
                "conditioned_beats_cap2_any_sharpe_windows",
                "conditioned_has_better_drawdown_than_cap2_any_windows",
                "conditioned_median_delta_vs_cap1_r",
                "conditioned_mean_delta_vs_cap1_r",
            ],
        ),
        "",
        "## Rolling 2-Year Detail",
        "",
        _markdown_table(
            rolling_rows,
            [
                "window",
                "baseline_total_r",
                "cap2_any_total_r",
                "conditioned_total_r",
                "conditioned_delta_vs_cap1_r",
                "conditioned_delta_vs_cap2_any_r",
                "baseline_sharpe",
                "cap2_any_sharpe",
                "conditioned_sharpe",
                "conditioned_max_drawdown_r",
            ],
        ),
        "",
        "## Full Available Per-Leg Read",
        "",
        _markdown_table(
            full_leg_rows,
            [
                "leg",
                "variant",
                "fills",
                "win_rate_pct",
                "avg_r",
                "total_r",
                "r_per_year",
                "delta_vs_cap1_r",
                "delta_vs_cap2_any_r",
                "sharpe_ratio",
                "max_drawdown_r",
            ],
        ),
        "",
    ]

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    payload = {
        "full_start": FULL_START,
        "available_end": AVAILABLE_END,
        "major_windows": major_rows,
        "rolling_scorecard": rolling_scorecard,
        "rolling_windows": rolling_rows,
        "full_available_per_leg": full_leg_rows,
        "report_path": str(REPORT_PATH),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("ALPHA_V1 ORB CAP=2 CONDITIONED 10Y VALIDATION")
    print(f"Available history: {FULL_START} to {AVAILABLE_END}")
    print("")
    print(
        _markdown_table(
            major_rows,
            [
                "label",
                "window",
                "variant",
                "total_r",
                "delta_vs_cap1_r",
                "delta_vs_cap2_any_r",
                "sharpe_ratio",
                "max_drawdown_r",
            ],
        )
    )
    print("")
    print(f"Report written to: {REPORT_PATH}")
    print(f"Summary JSON written to: {RESULT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
