#!/usr/bin/env python3
"""Test Hunter-style wide-stop target compression and one-loss re-entry on ALPHA_V1 ORB legs.

Scope:
- NQ Asia ORB
- ES Asia ORB
- ES NY ORB

The HTF-LSI leg is intentionally excluded because this pass is testing whether
Hunter ORB mechanics transfer to the current ORB sleeve.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
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
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_widestop_reentry_transfer_20260502"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_WIDESTOP_REENTRY_TRANSFER_20260502.md"

FULL_START = "2016-04-17"
WINDOW_STARTS = {
    "full": FULL_START,
    "2024_plus": "2024-01-01",
    "2025_plus": "2025-01-01",
}
ORB_LEG_KEYS = (
    "nq_asia_orb_long",
    "es_asia_orb_long",
    "es_ny_orb_long",
)
THRESHOLD_QUANTILES = (0.50, 0.65, 0.75, 0.85, 0.90)
TARGET_RRS = (1.10, 1.25, 1.50, 2.00, 3.00, 4.00, 5.00)
REENTRY_VARIANTS = {
    "baseline_cap1": (1, "any_reentry"),
    "cap2_any": (2, "any_reentry"),
    "cap2_after_nonpositive": (2, "after_nonpositive_first"),
    "cap2_after_sl": (2, "after_sl_first"),
    "cap2_after_positive": (2, "after_positive_first"),
    "cap2_after_full_target": (2, "after_full_target_first"),
}
COMBINED_REENTRY_KEYS = ("cap2_any", "cap2_after_nonpositive", "cap2_after_sl")


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


def _rr_label(rr: float) -> str:
    return str(rr).replace(".", "p")


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
        print(f"  rebuilding missing {instrument.symbol} 5m/1m bars from local 1s parquet", flush=True)
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


def _filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end]


def _sort_trades(trades: list[TradeResult]) -> list[TradeResult]:
    return sorted(trades, key=lambda t: (t.date, t.session, t.fill_bar, t.signal_bar, t.exit_bar))


def _metric_row(
    *,
    scope: str,
    variant: str,
    window: str,
    trades: list[TradeResult],
    daily_streams: dict[str, list[TradeResult]] | None = None,
) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    if daily_streams is not None:
        daily = portfolio_daily_frame({name: filled_trades(stream) for name, stream in daily_streams.items()})
        total_series = daily.sum(axis=1) if not daily.empty else pd.Series(dtype=float)
        daily_summary = summarize_daily_returns(total_series)
        max_dd_r = float(daily_summary["max_drawdown_r"])
        sharpe = float(daily_summary["sharpe_ratio"])
        calmar = float(daily_summary["calmar_ratio"])
    else:
        max_dd_r = float(metrics["max_drawdown_r"])
        sharpe = float(metrics["sharpe_ratio"])
        calmar = float(metrics["calmar_ratio"])
    r_by_year = metrics.get("r_by_year") or {}
    return {
        "scope": scope,
        "variant": variant,
        "window": window,
        "signals": int(metrics["total_signals"]),
        "fills": int(metrics["total_trades"]),
        "no_fills": int(metrics["no_fills"]),
        "net_r": _round(metrics["total_r"], 2),
        "win_rate_pct": _pct(metrics["win_rate"]),
        "profit_factor": _round(metrics["profit_factor"], 2),
        "avg_r": _round(metrics["avg_r"], 3),
        "sharpe_ratio": _round(sharpe, 2),
        "max_drawdown_r": _round(max_dd_r, 2),
        "calmar_ratio": _round(calmar, 2),
        "negative_years": int(sum(1 for value in r_by_year.values() if value < 0)),
    }


def _risk_thresholds_from_baseline(trades: list[TradeResult], min_tick: float) -> dict[str, float]:
    risks = np.array([trade.risk_points for trade in filled_trades(trades) if trade.risk_points > 0], dtype=float)
    if len(risks) == 0:
        return {f"q{int(q * 100)}": 0.0 for q in THRESHOLD_QUANTILES}
    thresholds: dict[str, float] = {}
    for q in THRESHOLD_QUANTILES:
        raw = float(np.quantile(risks, q))
        rounded = math.ceil(raw / min_tick) * min_tick if min_tick > 0 else raw
        thresholds[f"q{int(q * 100)}"] = round(float(rounded), 6)
    return thresholds


def _make_config(
    base: StrategyConfig,
    *,
    name: str,
    trade_cap: int,
    reentry_policy: str,
    threshold_points: float = 0.0,
    target_rr: float = 0.0,
) -> StrategyConfig:
    notes = (
        "ALPHA_V1 ORB Hunter-mechanic transfer test. "
        f"cap={trade_cap}, reentry={reentry_policy}, "
        f"wide_stop_threshold_points={threshold_points}, wide_stop_target_rr={target_rr}."
    )
    return with_overrides(
        base,
        name=name,
        notes=notes,
        orb_trade_max_per_session=trade_cap,
        orb_reentry_policy=reentry_policy,
        wide_stop_target_threshold_points=threshold_points,
        wide_stop_target_rr=target_rr,
    )


def _variant_family(variant: str) -> str:
    if variant.startswith("combo_"):
        return "combined"
    if variant.startswith("wide_"):
        return "wide_stop_only"
    return "reentry_only"


def _build_leg_configs(
    leg_key: str,
    base: StrategyConfig,
    thresholds: dict[str, float],
) -> tuple[list[StrategyConfig], dict[str, str], list[dict[str, Any]]]:
    configs_by_name: dict[str, StrategyConfig] = {}
    variant_to_name: dict[str, str] = {}
    manifest_rows: list[dict[str, Any]] = []

    def add_variant(
        variant: str,
        *,
        trade_cap: int,
        reentry_policy: str,
        threshold_label: str = "",
        threshold_points: float = 0.0,
        target_rr: float = 0.0,
        active_wide_rule: bool = False,
        maps_to_variant: str | None = None,
    ) -> None:
        if maps_to_variant is not None:
            variant_to_name[variant] = variant_to_name[maps_to_variant]
        else:
            name = f"{leg_key}_{variant}"
            variant_to_name[variant] = name
            configs_by_name[name] = _make_config(
                base,
                name=name,
                trade_cap=trade_cap,
                reentry_policy=reentry_policy,
                threshold_points=threshold_points,
                target_rr=target_rr,
            )
        manifest_rows.append(
            {
                "leg": leg_key,
                "variant": variant,
                "family": _variant_family(variant),
                "trade_cap": trade_cap,
                "reentry_policy": reentry_policy,
                "threshold_label": threshold_label,
                "threshold_points": threshold_points,
                "target_rr": target_rr,
                "normal_rr": base.rr,
                "active_wide_rule": active_wide_rule,
                "mapped_config": variant_to_name[variant],
            }
        )

    for variant, (trade_cap, policy) in REENTRY_VARIANTS.items():
        add_variant(variant, trade_cap=trade_cap, reentry_policy=policy)

    for threshold_label, threshold_points in thresholds.items():
        for target_rr in TARGET_RRS:
            rr_key = _rr_label(target_rr)
            wide_variant = f"wide_{threshold_label}_rr{rr_key}"
            active = target_rr < base.rr
            add_variant(
                wide_variant,
                trade_cap=1,
                reentry_policy="any_reentry",
                threshold_label=threshold_label,
                threshold_points=threshold_points if active else 0.0,
                target_rr=target_rr if active else 0.0,
                active_wide_rule=active,
                maps_to_variant=None if active else "baseline_cap1",
            )

            for reentry_variant in COMBINED_REENTRY_KEYS:
                trade_cap, policy = REENTRY_VARIANTS[reentry_variant]
                combo_variant = f"combo_{threshold_label}_rr{rr_key}_{reentry_variant}"
                add_variant(
                    combo_variant,
                    trade_cap=trade_cap,
                    reentry_policy=policy,
                    threshold_label=threshold_label,
                    threshold_points=threshold_points if active else 0.0,
                    target_rr=target_rr if active else 0.0,
                    active_wide_rule=active,
                    maps_to_variant=None if active else reentry_variant,
                )

    return list(configs_by_name.values()), variant_to_name, manifest_rows


def _run_configs(
    data: LoadedData,
    configs: list[StrategyConfig],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    print(f"  running {len(configs)} unique configs", flush=True)
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


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline_by_scope_window = {
        (row["scope"], row["window"]): row
        for row in rows
        if row["variant"] == "baseline_cap1"
    }
    ranked = []
    for row in rows:
        baseline = baseline_by_scope_window.get((row["scope"], row["window"]))
        if baseline is None:
            continue
        net_delta = float(row["net_r"]) - float(baseline["net_r"])
        dd_delta = float(row["max_drawdown_r"]) - float(baseline["max_drawdown_r"])
        ranked.append(
            {
                **row,
                "family": _variant_family(str(row["variant"])),
                "delta_net_r": _round(net_delta, 2),
                "delta_dd_r": _round(dd_delta, 2),
                "delta_fills": int(row["fills"]) - int(baseline["fills"]),
            }
        )
    return ranked


def _top_rows(
    rows: list[dict[str, Any]],
    *,
    window: str,
    family: str | None = None,
    limit: int = 10,
    exclude_baseline: bool = True,
) -> list[dict[str, Any]]:
    filtered = [row for row in rows if row["window"] == window]
    if family is not None:
        filtered = [row for row in filtered if row["family"] == family]
    if exclude_baseline:
        filtered = [row for row in filtered if row["variant"] != "baseline_cap1"]
    return sorted(
        filtered,
        key=lambda row: (
            float(row["net_r"]),
            float(row["delta_dd_r"]),
            float(row["profit_factor"] or 0),
        ),
        reverse=True,
    )[:limit]


def _annual_rows(
    leg_streams: dict[str, dict[str, list[TradeResult]]],
    combined_variants: list[str],
) -> list[dict[str, Any]]:
    rows = []
    for leg_key, variant_streams in leg_streams.items():
        for variant, trades in variant_streams.items():
            r_by_year = compute_metrics(trades).get("r_by_year") or {}
            for year, value in r_by_year.items():
                rows.append(
                    {
                        "scope": leg_key,
                        "variant": variant,
                        "year": year,
                        "net_r": _round(value, 2),
                    }
                )

    for variant in combined_variants:
        trades = _sort_trades([trade for streams in leg_streams.values() for trade in streams[variant]])
        r_by_year = compute_metrics(trades).get("r_by_year") or {}
        for year, value in r_by_year.items():
            rows.append(
                {
                    "scope": "combined_orb_sleeve",
                    "variant": variant,
                    "year": year,
                    "net_r": _round(value, 2),
                }
            )
    return rows


def _write_report(
    *,
    overlap_end: str,
    threshold_rows: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
    leg_rankings: list[dict[str, Any]],
    combined_rankings: list[dict[str, Any]],
) -> None:
    baseline_rows = [
        row for row in combined_rankings
        if row["variant"] == "baseline_cap1"
    ]
    reentry_rows = [
        row for row in combined_rankings
        if row["window"] in {"full", "2025_plus", "last_1y"}
        and row["family"] == "reentry_only"
        and row["variant"] != "baseline_cap1"
    ]

    best_full = _top_rows(combined_rankings, window="full", limit=8)
    best_2025 = _top_rows(combined_rankings, window="2025_plus", limit=8)
    best_last1 = _top_rows(combined_rankings, window="last_1y", limit=8)
    best_wide = _top_rows(combined_rankings, window="full", family="wide_stop_only", limit=8)
    best_combo = _top_rows(combined_rankings, window="full", family="combined", limit=8)

    per_leg_best = []
    for leg in ORB_LEG_KEYS:
        leg_rows = [row for row in leg_rankings if row["scope"] == leg and row["window"] == "full"]
        top = _top_rows(leg_rows, window="full", limit=1)
        if top:
            per_leg_best.append(top[0])

    active_manifest = [row for row in manifest_rows if row["active_wide_rule"]]
    report_lines = [
        "# ALPHA_V1 ORB Wide-Stop + Re-Entry Transfer Test",
        "",
        f"- Window: `{FULL_START}` to `{overlap_end}`",
        "- Scope: current active ALPHA_V1 ORB legs only: `NQ Asia ORB`, `ES Asia ORB`, `ES NY ORB`",
        "- Excluded: HTF-LSI leg, because this pass is testing ORB mechanic transfer only",
        "- Wide-stop rule: if realized stop/risk points are above a leg-specific baseline-risk quantile, use a lower effective RR target ladder for that trade",
        "- Re-entry rule: engine-backed `orb_trade_max_per_session=2` with `any_reentry`, `after_nonpositive_first`, `after_sl_first`, and diagnostic positive/full-target policies",
        "- Note: lowered RR also lowers the TP1 ladder through the existing engine rule, while still enforcing the hard minimum TP1 distance of at least `1R`.",
        "",
        "## Baseline Combined ORB Sleeve",
        "",
        _markdown_table(
            baseline_rows,
            [
                "window",
                "signals",
                "fills",
                "net_r",
                "win_rate_pct",
                "profit_factor",
                "sharpe_ratio",
                "max_drawdown_r",
                "negative_years",
            ],
        ),
        "",
        "## Risk Thresholds By Leg",
        "",
        _markdown_table(
            threshold_rows,
            [
                "leg",
                "fills",
                "risk_p50",
                "risk_p65",
                "risk_p75",
                "risk_p85",
                "risk_p90",
                "risk_min",
                "risk_median",
                "risk_max",
            ],
        ),
        "",
        "## Combined Sleeve: Re-Entry Only",
        "",
        _markdown_table(
            sorted(reentry_rows, key=lambda row: (row["window"], row["net_r"]), reverse=True),
            [
                "window",
                "variant",
                "fills",
                "net_r",
                "delta_net_r",
                "win_rate_pct",
                "profit_factor",
                "sharpe_ratio",
                "max_drawdown_r",
                "delta_dd_r",
                "negative_years",
            ],
        ),
        "",
        "## Top Combined Sleeve Variants: Full History",
        "",
        _markdown_table(
            best_full,
            [
                "family",
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
        "## Top Combined Sleeve Variants: 2025+",
        "",
        _markdown_table(
            best_2025,
            [
                "family",
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
        "## Top Combined Sleeve Variants: Last 1y",
        "",
        _markdown_table(
            best_last1,
            [
                "family",
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
        "## Wide-Stop Only Leaders",
        "",
        _markdown_table(
            best_wide,
            [
                "variant",
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
        "## Combined Mechanic Leaders",
        "",
        _markdown_table(
            best_combo,
            [
                "variant",
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
        "## Per-Leg Best Full-History Rows",
        "",
        _markdown_table(
            per_leg_best,
            [
                "scope",
                "family",
                "variant",
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
        "## Read",
        "",
        "- **One-loss / nonpositive re-entry transfers; wide-stop target compression does not.** The cleanest Hunter-style transfer is `cap2_after_nonpositive` / `cap2_after_sl`: full-history combined sleeve improves by about `+58.7R`, keeps `0` negative years, improves Sharpe, and only worsens daily DD by about `-0.8R`.",
        "- **`cap2_any` is the highest-R row, but it is less controlled.** It adds about `+81.6R` full history and `+13.6R` in 2025+, but daily DD worsens by about `-2.0R` full and `-2.7R` in the recent windows. That is attractive as a research branch, less clean as a direct live rule.",
        "- **Wide-stop TP compression is a portfolio-level NO-GO for this sleeve.** Every wide-only combined variant loses net R versus baseline; the best full-history row is still `-4.7R`, the median wide-only row is about `-32.9R`, and recent windows are also negative. It does not buy meaningful drawdown relief.",
        "- **Combined variants mostly inherit the re-entry edge.** The top combined rows are just `cap2_any` plus very light high-threshold target compression, and they underperform pure `cap2_any`. The wide-stop rule is not the source of the improvement.",
        "- Per-leg: `NQ Asia` and `ES Asia` both favor the one-loss/nonpositive re-entry. `ES NY` likes extra flow most, but the best full-history ES NY combo introduces a negative year, so it needs prop/risk validation before any live promotion.",
        "- The variant manifest records which wide-stop rows were active per leg; target RR values at or above a leg's normal RR map back to that leg's matching non-wide re-entry variant.",
        "",
        "## Artifacts",
        "",
        f"- Result directory: `{RESULT_DIR.relative_to(ROOT)}`",
        f"- Active wide-rule config rows: `{len(active_manifest)}`",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    legs = build_alpha_v1_legs()
    orb_legs = {key: legs[key] for key in ORB_LEG_KEYS}
    overlap_end = _available_end(sorted({leg.config.instrument for leg in orb_legs.values()}, key=lambda i: i.symbol))
    windows = _window_bounds(overlap_end)
    print(f"Overlap window: {FULL_START} to {overlap_end}", flush=True)

    leg_variant_streams: dict[str, dict[str, list[TradeResult]]] = {}
    threshold_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    leg_metric_rows: list[dict[str, Any]] = []

    for leg_key, leg in orb_legs.items():
        print(f"\n[{leg_key}] loading data", flush=True)
        data = _load_market_data(leg.config.instrument, end_date=overlap_end)

        base_config = _make_config(
            leg.config,
            name=f"{leg_key}_baseline_threshold_probe",
            trade_cap=1,
            reentry_policy="any_reentry",
        )
        base_trades = _run_configs(data, [base_config], start_date=FULL_START, end_date=overlap_end)[base_config.name]
        filled_base = filled_trades(base_trades)
        thresholds = _risk_thresholds_from_baseline(base_trades, leg.config.min_tick)
        risks = [trade.risk_points for trade in filled_base if trade.risk_points > 0]
        threshold_rows.append(
            {
                "leg": leg_key,
                "fills": len(filled_base),
                "risk_p50": thresholds["q50"],
                "risk_p65": thresholds["q65"],
                "risk_p75": thresholds["q75"],
                "risk_p85": thresholds["q85"],
                "risk_p90": thresholds["q90"],
                "risk_min": _round(min(risks), 2) if risks else None,
                "risk_median": _round(float(np.median(risks)), 2) if risks else None,
                "risk_max": _round(max(risks), 2) if risks else None,
            }
        )

        configs, variant_to_name, leg_manifest = _build_leg_configs(leg_key, leg.config, thresholds)
        manifest_rows.extend(leg_manifest)

        print(f"[{leg_key}] generated {len(variant_to_name)} variants -> {len(configs)} unique configs", flush=True)
        results_by_name = _run_configs(data, configs, start_date=FULL_START, end_date=overlap_end)
        leg_streams = {
            variant: results_by_name[name]
            for variant, name in variant_to_name.items()
        }
        leg_variant_streams[leg_key] = leg_streams

        for variant, trades in leg_streams.items():
            for window_name, (start, end) in windows.items():
                leg_metric_rows.append(
                    _metric_row(
                        scope=leg_key,
                        variant=variant,
                        window=window_name,
                        trades=_filter_window(trades, start, end),
                    )
                )

    combined_metric_rows: list[dict[str, Any]] = []
    all_variants = sorted(next(iter(leg_variant_streams.values())).keys())
    for variant in all_variants:
        for window_name, (start, end) in windows.items():
            window_streams = {
                leg_key: _filter_window(variant_streams[variant], start, end)
                for leg_key, variant_streams in leg_variant_streams.items()
            }
            merged = _sort_trades([trade for stream in window_streams.values() for trade in stream])
            combined_metric_rows.append(
                _metric_row(
                    scope="combined_orb_sleeve",
                    variant=variant,
                    window=window_name,
                    trades=merged,
                    daily_streams=window_streams,
                )
            )

    leg_rankings = _rank_rows(leg_metric_rows)
    combined_rankings = _rank_rows(combined_metric_rows)
    annual_rows = _annual_rows(leg_variant_streams, all_variants)

    pd.DataFrame(threshold_rows).to_csv(RESULT_DIR / "risk_thresholds_by_leg.csv", index=False)
    pd.DataFrame(manifest_rows).to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    pd.DataFrame(leg_metric_rows).to_csv(RESULT_DIR / "leg_metrics_by_window.csv", index=False)
    pd.DataFrame(combined_metric_rows).to_csv(RESULT_DIR / "combined_metrics_by_window.csv", index=False)
    pd.DataFrame(leg_rankings).to_csv(RESULT_DIR / "leg_rankings.csv", index=False)
    pd.DataFrame(combined_rankings).to_csv(RESULT_DIR / "combined_rankings.csv", index=False)
    pd.DataFrame(annual_rows).to_csv(RESULT_DIR / "annual_r_by_variant.csv", index=False)

    summary = {
        "full_start": FULL_START,
        "overlap_end": overlap_end,
        "windows": windows,
        "orb_legs": list(ORB_LEG_KEYS),
        "threshold_quantiles": list(THRESHOLD_QUANTILES),
        "target_rrs": list(TARGET_RRS),
        "reentry_variants": REENTRY_VARIANTS,
        "result_dir": str(RESULT_DIR),
        "report_path": str(REPORT_PATH),
        "top_full": _top_rows(combined_rankings, window="full", limit=10),
        "top_2025_plus": _top_rows(combined_rankings, window="2025_plus", limit=10),
        "top_last_1y": _top_rows(combined_rankings, window="last_1y", limit=10),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    _write_report(
        overlap_end=overlap_end,
        threshold_rows=threshold_rows,
        manifest_rows=manifest_rows,
        leg_rankings=leg_rankings,
        combined_rankings=combined_rankings,
    )
    print(json.dumps({"report": str(REPORT_PATH), "result_dir": str(RESULT_DIR)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
