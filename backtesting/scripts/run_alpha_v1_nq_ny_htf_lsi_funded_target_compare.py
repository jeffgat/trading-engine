#!/usr/bin/env python3
"""Compare NQ NY HTF-LSI final targets under funded-account constraints.

This follow-up narrows in on the only active ALPHA_V1 leg where lowering the
final target looked credible in the exact engine sweep: `NQ NY HTF-LSI`.

Method:
1. Keep the first scale distance fixed at the current `1.4R`.
2. Rerun the exact research engine for:
   - current branch: `3.5R` final target, `tp1_ratio=0.4`
   - reduced branch: `2.0R` final target, `tp1_ratio=0.7`
3. Score both trade streams with the funded first-payout model:
   - fixed standard profile (`$500 / $250`)
   - pre-holdout risk sweep (`$200..$600`) to freeze each target's best risk
4. Evaluate the frozen-risk profiles on the untouched holdout window.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config  # noqa: E402
from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    FundedFirstPayoutProfile,
    build_funded_first_payout_scorecard,
    simulate_funded_first_payouts,
)
from orb_backtest.config import StrategyConfig, with_overrides  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


FULL_START = "2016-01-01"
PRE_HOLDOUT_END_INCLUSIVE = "2025-03-31"
HOLDOUT_START = "2025-04-01"
RECENT_START = "2024-01-01"
FIXED_TP1_R = 1.4

OUTPUT_DIR = ROOT / "data" / "results" / "alpha_v1_nq_ny_htf_lsi_funded_target_compare_20260423"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_NQ_NY_HTF_LSI_FUNDED_TARGET_COMPARE.md"

FIXED_FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0,
    starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0,
    max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0,
    risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0,
)
RISK_VALUES = (200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0, 550.0, 600.0)

WINDOWS = (
    {
        "key": "full",
        "label": "Full",
        "start": FULL_START,
        "start_label": FULL_START,
    },
    {
        "key": "pre_holdout",
        "label": "Pre-Holdout",
        "start": FULL_START,
        "end": HOLDOUT_START,
        "start_label": FULL_START,
        "end_label": PRE_HOLDOUT_END_INCLUSIVE,
    },
    {
        "key": "recent",
        "label": "Recent",
        "start": RECENT_START,
        "start_label": RECENT_START,
    },
    {
        "key": "holdout",
        "label": "Holdout",
        "start": HOLDOUT_START,
        "start_label": HOLDOUT_START,
    },
)


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    value = float(value)
    if not math.isfinite(value):
        return None
    return round(value, digits)


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
    body = [
        "| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body]) if body else "\n".join([header, sep])


def _slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        trade
        for trade in trades
        if (start is None or trade.date >= start)
        and (end is None or trade.date < end)
    ]


def _trading_dates_between(df: pd.DataFrame, start: str, end_exclusive: str) -> list[str]:
    idx = df.index[(df.index >= start) & (df.index < end_exclusive)]
    if len(idx) == 0:
        return []
    dates = pd.Index(pd.to_datetime(idx.normalize()).unique()).sort_values()
    return [d.strftime("%Y-%m-%d") for d in dates]


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return out.dropna(subset=["open", "high", "low", "close"]).astype(float)


def _load_timeframe_data_resilient(
    filename_5m: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None, pd.DataFrame]:
    df_1s = load_1s_for_5m(filename_5m, start=start, end=end)

    try:
        df_5m = load_5m_data(filename_5m, start=start, end=end)
    except FileNotFoundError:
        if df_1s is None:
            raise
        df_5m = _resample_ohlcv(df_1s, "5min")

    try:
        df_1m = load_1m_for_5m(filename_5m, start=start, end=end)
    except FileNotFoundError:
        if df_1s is None:
            raise
        df_1m = _resample_ohlcv(df_1s, "1min")

    return df_5m, df_1m, df_1s, df_1m


def _rank_score(row: pd.Series) -> float:
    payout_rate = float(row["payout_rate"])
    breach_rate = float(row["breach_rate"])
    avg_days = float(row["average_days_to_payout"] or 999.0)
    median_days = float(row["median_days_to_payout"] or 999.0)
    return round(
        (payout_rate * 100.0)
        - (breach_rate * 35.0)
        - (avg_days * 0.35)
        - (median_days * 0.15),
        3,
    )


def _config_summary(config: StrategyConfig) -> str:
    session = config.sessions[0]
    return (
        f"{config.direction_filter} {config.lsi_entry_mode} "
        f"{session.entry_start}-{session.entry_end} "
        f"rr{config.rr} tp{config.tp1_ratio} "
        f"gap{session.min_gap_atr_pct} "
        f"htf{config.htf_level_tf_minutes} n{config.htf_n_left} "
        f"cap{config.htf_trade_max_per_session} "
        f"fvgL{config.lsi_fvg_window_left} fvgR{config.lsi_fvg_window_right} "
        f"lag{config.max_fvg_to_inversion_bars}"
    )


def _variant_specs() -> list[dict[str, Any]]:
    current = build_current_nq_ny_htf_lsi_lag24_config(
        name="ALPHA_V1 NQ NY HTF_LSI current 3.5R",
    )
    reduced_rr = 2.0
    reduced_tp1_ratio = FIXED_TP1_R / reduced_rr
    reduced = with_overrides(
        current,
        rr=reduced_rr,
        tp1_ratio=reduced_tp1_ratio,
        name="ALPHA_V1 NQ NY HTF_LSI reduced 2R",
    )
    return [
        {
            "key": "current_3p5r",
            "label": "Current 3.5R",
            "config": current,
        },
        {
            "key": "reduced_2r",
            "label": "Reduced 2R",
            "config": reduced,
        },
    ]


def _metrics_snapshot(metrics: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "total_trades",
        "win_rate",
        "profit_factor",
        "avg_r",
        "total_r",
        "max_drawdown_r",
        "calmar_ratio",
    )
    out: dict[str, Any] = {}
    for key in keep:
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            out[key] = _round(value, 4)
        else:
            out[key] = value
    return out


def _funded_scorecard(
    *,
    label: str,
    trades,
    trading_dates: list[str],
    profile: FundedFirstPayoutProfile,
) -> dict[str, Any]:
    outcomes = simulate_funded_first_payouts(
        specialist_name=label,
        trades=trades,
        trading_dates=trading_dates,
        profile=profile,
    )
    scorecard = build_funded_first_payout_scorecard(outcomes, profile)
    payouts = int((outcomes["outcome"] == "payout").sum()) if not outcomes.empty else 0
    breaches = int((outcomes["outcome"] == "breach").sum()) if not outcomes.empty else 0
    resolved = payouts + breaches
    return {
        "scorecard": scorecard,
        "counts": {
            "starts": int(len(outcomes)),
            "payouts": payouts,
            "breaches": breaches,
            "resolved_payout_rate": _round((payouts / resolved) if resolved else None, 4),
        },
    }


def _sweep_risk(trades, trading_dates: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for risk in RISK_VALUES:
        profile = replace(
            FIXED_FUNDED_PROFILE,
            risk_pre_payout_usd=risk,
            risk_post_payout_usd=max(100.0, risk / 2.0),
        )
        scorecard_bundle = _funded_scorecard(
            label=f"risk_{int(risk)}",
            trades=trades,
            trading_dates=trading_dates,
            profile=profile,
        )
        score = scorecard_bundle["scorecard"]
        rows.append(
            {
                "risk_pre_usd": int(risk),
                "risk_post_usd": int(max(100.0, risk / 2.0)),
                "starts": int(score["total_starts"]),
                "payout_rate": float(score["payout_rate"]),
                "breach_rate": float(score["breach_rate"]),
                "open_rate": float(score["open_rate"]),
                "average_days_to_payout": score["average_days_to_payout"],
                "median_days_to_payout": score["median_days_to_payout"],
                "average_trades_to_payout": score["average_trades_to_payout"],
                "average_first_payout_amount_usd": score["average_first_payout_amount_usd"],
                "average_net_after_fee_usd": score["average_net_after_fee_usd"],
                "ev_per_start_usd": float(score["ev_per_start_usd"]),
            }
        )

    df = pd.DataFrame(rows)
    df["rank_score"] = df.apply(_rank_score, axis=1)
    df = df.sort_values("risk_pre_usd").reset_index(drop=True)
    best = df.sort_values(
        by=[
            "rank_score",
            "payout_rate",
            "breach_rate",
            "average_days_to_payout",
            "ev_per_start_usd",
        ],
        ascending=[False, False, True, True, False],
    ).iloc[0]
    return {
        "best_row": {k: (v.item() if hasattr(v, "item") else v) for k, v in best.to_dict().items()},
        "rows": [{k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()} for row in df.to_dict(orient="records")],
    }


def _window_end_exclusive(window_key: str, available_end_exclusive: str) -> str:
    if window_key == "pre_holdout":
        return HOLDOUT_START
    return available_end_exclusive


def _write_report(payload: dict[str, Any]) -> None:
    info = payload["info"]
    variants = payload["variants"]

    metric_rows = []
    fixed_rows = []
    risk_rows = []
    frozen_holdout_rows = []

    for key, variant in variants.items():
        label = variant["label"]
        for window_key in ("full", "pre_holdout", "recent", "holdout"):
            metrics = variant["metrics_by_window"][window_key]
            fixed = variant["fixed_profile_scorecards"][window_key]
            metric_rows.append(
                {
                    "target": label,
                    "window": variant["window_labels"][window_key],
                    "trades": metrics["total_trades"],
                    "win_rate": _round(float(metrics["win_rate"]) * 100.0 if metrics["win_rate"] is not None else None, 2),
                    "profit_factor": metrics["profit_factor"],
                    "avg_r": metrics["avg_r"],
                    "net_r": metrics["total_r"],
                    "max_dd_r": metrics["max_drawdown_r"],
                    "calmar": metrics["calmar_ratio"],
                }
            )
            fixed_rows.append(
                {
                    "target": label,
                    "window": variant["window_labels"][window_key],
                    "risk_pre_usd": int(FIXED_FUNDED_PROFILE.risk_pre_payout_usd),
                    "risk_post_usd": int(FIXED_FUNDED_PROFILE.risk_post_payout_usd),
                    "payout_rate": _round(float(fixed["scorecard"]["payout_rate"]) * 100.0, 2),
                    "breach_rate": _round(float(fixed["scorecard"]["breach_rate"]) * 100.0, 2),
                    "open_rate": _round(float(fixed["scorecard"]["open_rate"]) * 100.0, 2),
                    "avg_days_to_payout": fixed["scorecard"]["average_days_to_payout"],
                    "median_days_to_payout": fixed["scorecard"]["median_days_to_payout"],
                    "ev_per_start_usd": fixed["scorecard"]["ev_per_start_usd"],
                }
            )

        best = variant["pre_holdout_risk_sweep"]["best_row"]
        risk_rows.append(
            {
                "target": label,
                "risk_pre_usd": best["risk_pre_usd"],
                "risk_post_usd": best["risk_post_usd"],
                "payout_rate": _round(float(best["payout_rate"]) * 100.0, 2),
                "breach_rate": _round(float(best["breach_rate"]) * 100.0, 2),
                "avg_days_to_payout": best["average_days_to_payout"],
                "median_days_to_payout": best["median_days_to_payout"],
                "ev_per_start_usd": best["ev_per_start_usd"],
                "rank_score": best["rank_score"],
            }
        )

        frozen = variant["holdout_frozen_risk_scorecard"]
        frozen_holdout_rows.append(
            {
                "target": label,
                "risk_pre_usd": int(frozen["profile"]["risk_pre_payout_usd"]),
                "risk_post_usd": int(frozen["profile"]["risk_post_payout_usd"]),
                "payout_rate": _round(float(frozen["scorecard"]["payout_rate"]) * 100.0, 2),
                "breach_rate": _round(float(frozen["scorecard"]["breach_rate"]) * 100.0, 2),
                "open_rate": _round(float(frozen["scorecard"]["open_rate"]) * 100.0, 2),
                "avg_days_to_payout": frozen["scorecard"]["average_days_to_payout"],
                "median_days_to_payout": frozen["scorecard"]["median_days_to_payout"],
                "ev_per_start_usd": frozen["scorecard"]["ev_per_start_usd"],
            }
        )

    current_fixed_holdout = variants["current_3p5r"]["fixed_profile_scorecards"]["holdout"]["scorecard"]
    reduced_fixed_holdout = variants["reduced_2r"]["fixed_profile_scorecards"]["holdout"]["scorecard"]
    current_frozen_holdout = variants["current_3p5r"]["holdout_frozen_risk_scorecard"]["scorecard"]
    reduced_frozen_holdout = variants["reduced_2r"]["holdout_frozen_risk_scorecard"]["scorecard"]

    def _winner(metric: str, higher_is_better: bool = True) -> str:
        cur = float(current_fixed_holdout.get(metric) or 0.0)
        red = float(reduced_fixed_holdout.get(metric) or 0.0)
        if abs(cur - red) < 1e-9:
            return "tie"
        return "Current 3.5R" if (cur > red) == higher_is_better else "Reduced 2R"

    lines = [
        "# ALPHA_V1 NQ NY HTF-LSI Funded Target Compare",
        "",
        "- Scope: the active `NQ NY HTF-LSI` leg only.",
        "- Exact configs compared:",
        f"  - `Current 3.5R`: `{variants['current_3p5r']['config_summary']}`",
        f"  - `Reduced 2R`: `{variants['reduced_2r']['config_summary']}`",
        f"- First scale is held constant at `{FIXED_TP1_R}R`, so the reduced target uses `tp1_ratio = 0.7`.",
        f"- Full data window: `{FULL_START}` to `{info['available_end_inclusive']}`.",
        "- Fixed funded profile: `$50k` start, `$2k` trailing EOD DD, first payout floor `$52.5k`, challenge fee `$100`, risk `$500` pre-payout / `$250` post-payout`.",
        "- Robustness step: risk is selected on pre-holdout only (`2016-01-01` to `2025-03-31`) and then frozen for the holdout replay.",
        "",
        "## Summary",
        "",
        (
            f"- Fixed-risk holdout payout rate winner: `{_winner('payout_rate', higher_is_better=True)}` "
            f"(`3.5R={current_fixed_holdout['payout_rate']:.1%}`, `2R={reduced_fixed_holdout['payout_rate']:.1%}`)."
        ),
        (
            f"- Fixed-risk holdout breach rate winner: "
            f"`{'Current 3.5R' if float(current_fixed_holdout['breach_rate']) < float(reduced_fixed_holdout['breach_rate']) else 'Reduced 2R' if float(reduced_fixed_holdout['breach_rate']) < float(current_fixed_holdout['breach_rate']) else 'tie'}` "
            f"(`3.5R={current_fixed_holdout['breach_rate']:.1%}`, `2R={reduced_fixed_holdout['breach_rate']:.1%}`)."
        ),
        (
            f"- Frozen-risk holdout EV per start: "
            f"`3.5R=${current_frozen_holdout['ev_per_start_usd']}` vs `2R=${reduced_frozen_holdout['ev_per_start_usd']}`."
        ),
        "",
        "## Exact Backtest Metrics",
        "",
        _markdown_table(
            metric_rows,
            ["target", "window", "trades", "win_rate", "profit_factor", "avg_r", "net_r", "max_dd_r", "calmar"],
        ),
        "",
        "## Fixed Funded Profile",
        "",
        _markdown_table(
            fixed_rows,
            [
                "target",
                "window",
                "risk_pre_usd",
                "risk_post_usd",
                "payout_rate",
                "breach_rate",
                "open_rate",
                "avg_days_to_payout",
                "median_days_to_payout",
                "ev_per_start_usd",
            ],
        ),
        "",
        "## Pre-Holdout Best Risk",
        "",
        _markdown_table(
            risk_rows,
            [
                "target",
                "risk_pre_usd",
                "risk_post_usd",
                "payout_rate",
                "breach_rate",
                "avg_days_to_payout",
                "median_days_to_payout",
                "ev_per_start_usd",
                "rank_score",
            ],
        ),
        "",
        "## Holdout With Frozen Risk",
        "",
        _markdown_table(
            frozen_holdout_rows,
            [
                "target",
                "risk_pre_usd",
                "risk_post_usd",
                "payout_rate",
                "breach_rate",
                "open_rate",
                "avg_days_to_payout",
                "median_days_to_payout",
                "ev_per_start_usd",
            ],
        ),
        "",
        "## Notes",
        "",
        "- The fixed funded table answers the straightforward question: what happens if you trade each target with the current house risk profile.",
        "- The frozen-risk holdout table is the cleaner operational read: each target gets one pre-holdout risk choice, then we see how that risk policy survives out of sample.",
    ]

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    variants = _variant_specs()
    df_base, df_1m, df_1s, signal_df_1m = _load_timeframe_data_resilient(
        variants[0]["config"].instrument.data_file,
        start=FULL_START,
    )
    available_end_ts = pd.Timestamp(df_base.index.max()).normalize()
    available_end_inclusive = available_end_ts.strftime("%Y-%m-%d")
    available_end_exclusive = (available_end_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, [variant["config"] for variant in variants], signal_df_1m=signal_df_1m)

    payload_variants: dict[str, Any] = {}
    metrics_rows: list[dict[str, Any]] = []
    fixed_scorecard_rows: list[dict[str, Any]] = []
    risk_sweep_rows: list[dict[str, Any]] = []
    frozen_holdout_rows: list[dict[str, Any]] = []

    for variant in variants:
        key = variant["key"]
        label = variant["label"]
        config = variant["config"]
        print(f"[run] {label} -> {config.name}", flush=True)
        trades = run_backtest(
            df_base,
            config,
            start_date=FULL_START,
            end_date=available_end_exclusive,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )

        window_metrics: dict[str, Any] = {}
        fixed_profile_scorecards: dict[str, Any] = {}
        window_labels: dict[str, str] = {}
        for window in WINDOWS:
            end_exclusive = _window_end_exclusive(window["key"], available_end_exclusive)
            window_trades = _slice_trades(trades, window["start"], end_exclusive)
            trading_dates = _trading_dates_between(df_base, window["start"], end_exclusive)
            end_label = window.get("end_label", available_end_inclusive)
            window_label = f"{window['start_label']} to {end_label}"
            metrics = _metrics_snapshot(compute_metrics(window_trades))
            funded = _funded_scorecard(
                label=f"{key}_{window['key']}_fixed",
                trades=window_trades,
                trading_dates=trading_dates,
                profile=FIXED_FUNDED_PROFILE,
            )

            window_metrics[window["key"]] = metrics
            fixed_profile_scorecards[window["key"]] = funded
            window_labels[window["key"]] = window_label

            metrics_rows.append(
                {
                    "target": label,
                    "window": window_label,
                    **metrics,
                }
            )
            fixed_scorecard_rows.append(
                {
                    "target": label,
                    "window": window_label,
                    "risk_pre_usd": int(FIXED_FUNDED_PROFILE.risk_pre_payout_usd),
                    "risk_post_usd": int(FIXED_FUNDED_PROFILE.risk_post_payout_usd),
                    **funded["scorecard"],
                    **funded["counts"],
                }
            )

        pre_holdout_trades = _slice_trades(trades, FULL_START, HOLDOUT_START)
        pre_holdout_dates = _trading_dates_between(df_base, FULL_START, HOLDOUT_START)
        risk_sweep = _sweep_risk(pre_holdout_trades, pre_holdout_dates)
        for row in risk_sweep["rows"]:
            risk_sweep_rows.append({"target": label, **row})

        best = risk_sweep["best_row"]
        frozen_profile = replace(
            FIXED_FUNDED_PROFILE,
            risk_pre_payout_usd=float(best["risk_pre_usd"]),
            risk_post_payout_usd=float(best["risk_post_usd"]),
        )
        holdout_trades = _slice_trades(trades, HOLDOUT_START, available_end_exclusive)
        holdout_dates = _trading_dates_between(df_base, HOLDOUT_START, available_end_exclusive)
        frozen_holdout = _funded_scorecard(
            label=f"{key}_holdout_frozen",
            trades=holdout_trades,
            trading_dates=holdout_dates,
            profile=frozen_profile,
        )
        frozen_holdout_rows.append(
            {
                "target": label,
                "risk_pre_usd": int(frozen_profile.risk_pre_payout_usd),
                "risk_post_usd": int(frozen_profile.risk_post_payout_usd),
                **frozen_holdout["scorecard"],
                **frozen_holdout["counts"],
            }
        )

        payload_variants[key] = {
            "label": label,
            "config_summary": _config_summary(config),
            "rr": config.rr,
            "tp1_ratio": config.tp1_ratio,
            "metrics_by_window": window_metrics,
            "fixed_profile_scorecards": fixed_profile_scorecards,
            "pre_holdout_risk_sweep": risk_sweep,
            "holdout_frozen_risk_scorecard": {
                "profile": {
                    "risk_pre_payout_usd": frozen_profile.risk_pre_payout_usd,
                    "risk_post_payout_usd": frozen_profile.risk_post_payout_usd,
                },
                "scorecard": frozen_holdout["scorecard"],
                "counts": frozen_holdout["counts"],
            },
            "window_labels": window_labels,
        }

    payload = {
        "info": {
            "full_start": FULL_START,
            "pre_holdout_end_inclusive": PRE_HOLDOUT_END_INCLUSIVE,
            "holdout_start": HOLDOUT_START,
            "recent_start": RECENT_START,
            "available_end_inclusive": available_end_inclusive,
            "fixed_tp1_r": FIXED_TP1_R,
            "risk_values": list(RISK_VALUES),
            "fixed_funded_profile": {
                "challenge_fee": FIXED_FUNDED_PROFILE.challenge_fee,
                "starting_balance_usd": FIXED_FUNDED_PROFILE.starting_balance_usd,
                "trailing_drawdown_usd": FIXED_FUNDED_PROFILE.trailing_drawdown_usd,
                "max_trailing_breach_usd": FIXED_FUNDED_PROFILE.max_trailing_breach_usd,
                "first_payout_floor_usd": FIXED_FUNDED_PROFILE.first_payout_floor_usd,
                "risk_pre_payout_usd": FIXED_FUNDED_PROFILE.risk_pre_payout_usd,
                "risk_post_payout_usd": FIXED_FUNDED_PROFILE.risk_post_payout_usd,
            },
            "risk_selection_rule": "pre-holdout payout-heavy rank score",
        },
        "variants": payload_variants,
        "tables": {
            "metrics_rows": metrics_rows,
            "fixed_profile_scorecard_rows": fixed_scorecard_rows,
            "pre_holdout_risk_sweep_rows": risk_sweep_rows,
            "holdout_frozen_risk_rows": frozen_holdout_rows,
        },
    }

    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))
    pd.DataFrame(metrics_rows).to_csv(OUTPUT_DIR / "metrics_by_window.csv", index=False)
    pd.DataFrame(fixed_scorecard_rows).to_csv(OUTPUT_DIR / "fixed_profile_scorecards.csv", index=False)
    pd.DataFrame(risk_sweep_rows).to_csv(OUTPUT_DIR / "pre_holdout_risk_sweep.csv", index=False)
    pd.DataFrame(frozen_holdout_rows).to_csv(OUTPUT_DIR / "holdout_frozen_risk_scorecards.csv", index=False)
    _write_report(payload)

    print(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {OUTPUT_DIR / 'summary.json'}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
