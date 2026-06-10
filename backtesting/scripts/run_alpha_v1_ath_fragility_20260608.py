#!/usr/bin/env python3
"""Fresh ALPHA_V1-A ATH fragility packet.

This expands the quick ATH refresh into four checks:

1. Fresh exact replay through the latest common ES/NQ OHLCV data.
2. Leg-specific ATH bucket and loss-cluster attribution.
3. Focused hard-gate exact replay variants plus post-trade risk haircuts.
4. Path metrics, including drawdown, loss streaks, and a simple +5R/-4R
   first-payout proxy.

Hard gates are live-native for ORB sessions. Risk haircuts are post-trade
research simulations because the live ORB engine currently supports ATH blocks,
not ATH-conditioned risk sizing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BACKTESTING_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKTESTING_ROOT.parent
EXEC_SRC = REPO_ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader.historical_backtest import (  # noqa: E402
    latest_common_end,
    rolling_year_window_endpoints,
    run_profile_backtest_sync,
)
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402

from run_alpha_v1_ath_refresh_20260608 import (  # noqa: E402
    _annotate_ath,
    _markdown_table,
    _result_to_frame,
)


PROFILE = "ALPHA_V1-A"
SYMBOLS = ["ES", "NQ"]
RESULT_DIR = BACKTESTING_ROOT / "data" / "results" / "alpha_v1_ath_fragility_20260608"
REPORT_PATH = BACKTESTING_ROOT / "learnings" / "reports" / "ALPHA_V1_ATH_FRAGILITY_20260608.md"

WINDOWS = {
    "full": None,
    "2024+": "2024-01-01",
    "2025+": "2025-01-01",
    "2026_ytd": "2026-01-01",
    "2026_05+": "2026-05-01",
}
BUCKET_ORDER = [
    "above_prior_ath",
    "0-0.5%",
    "0.5-1%",
    "1-2%",
    "2-5%",
    "5-10%",
    ">10%",
    "unknown",
]
ORB_SESSIONS = ("NQ_NY", "NQ_Asia", "ES_NY", "ES_Asia")
ES_SESSIONS = ("ES_NY", "ES_Asia")


@dataclass(frozen=True)
class ExactVariant:
    name: str
    overrides: dict[str, dict[str, Any]]
    thesis: str


@dataclass(frozen=True)
class HaircutVariant:
    name: str
    sessions: tuple[str, ...]
    buckets: tuple[str, ...]
    factor: float
    thesis: str


EXACT_VARIANTS = [
    ExactVariant(
        name="ES_NY_BLOCK_0P5_0P75",
        overrides={"ES_NY": {"ath_block_min_pct": 0.5, "ath_block_max_pct": 0.75}},
        thesis="Prior ES_NY surgical shadow band.",
    ),
    ExactVariant(
        name="ES_NY_BLOCK_0P5_1P0",
        overrides={"ES_NY": {"ath_block_min_pct": 0.5, "ath_block_max_pct": 1.0}},
        thesis="Broader ES_NY moderate-dip dead-zone block.",
    ),
    ExactVariant(
        name="ES_ASIA_BLOCK_0P5_1P0",
        overrides={"ES_Asia": {"ath_block_min_pct": 0.5, "ath_block_max_pct": 1.0}},
        thesis="ES_Asia-only moderate-dip block.",
    ),
    ExactVariant(
        name="ES_ALL_BLOCK_0P5_1P0",
        overrides={
            "ES_NY": {"ath_block_min_pct": 0.5, "ath_block_max_pct": 1.0},
            "ES_Asia": {"ath_block_min_pct": 0.5, "ath_block_max_pct": 1.0},
        },
        thesis="Combined ES sleeve moderate-dip block.",
    ),
    ExactVariant(
        name="ES_ALL_BLOCK_5P0_10P0",
        overrides={
            "ES_NY": {"ath_block_min_pct": 5.0, "ath_block_max_pct": 10.0},
            "ES_Asia": {"ath_block_min_pct": 5.0, "ath_block_max_pct": 10.0},
        },
        thesis="Combined ES sleeve deeper-dip control.",
    ),
    ExactVariant(
        name="ORB_ALL_BLOCK_0P5_1P0",
        overrides={session: {"ath_block_min_pct": 0.5, "ath_block_max_pct": 1.0} for session in ORB_SESSIONS},
        thesis="Portfolio ORB-wide moderate-dip control. LSI is excluded because it is not ATH-gate native.",
    ),
]

HAIRCUT_VARIANTS = [
    HaircutVariant(
        name="POST_ES_NY_HALF_RISK_0P5_1P0",
        sessions=("ES_NY",),
        buckets=("0.5-1%",),
        factor=0.5,
        thesis="Research-only ES_NY 50% risk haircut in the moderate-dip bucket.",
    ),
    HaircutVariant(
        name="POST_ES_ASIA_HALF_RISK_0P5_1P0",
        sessions=("ES_Asia",),
        buckets=("0.5-1%",),
        factor=0.5,
        thesis="Research-only ES_Asia 50% risk haircut in the moderate-dip bucket.",
    ),
    HaircutVariant(
        name="POST_ES_ALL_HALF_RISK_0P5_1P0",
        sessions=ES_SESSIONS,
        buckets=("0.5-1%",),
        factor=0.5,
        thesis="Research-only ES sleeve 50% risk haircut in the moderate-dip bucket.",
    ),
    HaircutVariant(
        name="POST_ES_ALL_HALF_RISK_5P0_10P0",
        sessions=ES_SESSIONS,
        buckets=("5-10%",),
        factor=0.5,
        thesis="Research-only ES sleeve 50% risk haircut in the deeper-dip bucket.",
    ),
    HaircutVariant(
        name="POST_ORB_ALL_HALF_RISK_0P5_1P0",
        sessions=ORB_SESSIONS,
        buckets=("0.5-1%",),
        factor=0.5,
        thesis="Research-only ORB sleeve 50% risk haircut in the moderate-dip bucket.",
    ),
]


def _run_or_load(
    *,
    config: dict[str, Any],
    start_date: str,
    end_date: str,
    latest_data_ts: datetime,
    path: Path,
    label: str,
    refresh: bool,
    profile_session_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    print(f"RUN {label}", flush=True)
    result = run_profile_backtest_sync(
        config=config,
        profile_name=PROFILE,
        start_date=start_date,
        end_date=end_date,
        latest_data_ts=latest_data_ts,
        label=label,
        profile_session_overrides=profile_session_overrides,
    )
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _prepare_trades(result: dict[str, Any], scenario: str) -> pd.DataFrame:
    trades = _annotate_ath(_result_to_frame(result))
    if trades.empty:
        return trades
    trades["scenario"] = scenario
    trades["scenario_kind"] = "exact"
    trades["scenario_pnl_usd"] = pd.to_numeric(trades["pnl_usd"], errors="coerce").fillna(0.0)
    trades["scenario_configured_net_r"] = pd.to_numeric(
        trades["configured_net_r"], errors="coerce"
    ).fillna(0.0)
    trades["entry_date"] = pd.to_datetime(trades["entry_local"]).dt.date.astype(str)
    return trades


def _window_frame(frame: pd.DataFrame, window: str) -> pd.DataFrame:
    start = WINDOWS[window]
    if start is None or frame.empty:
        return frame
    return frame[pd.to_datetime(frame["entry_local"]) >= pd.Timestamp(start)]


def _max_consecutive(mask: pd.Series | np.ndarray) -> int:
    longest = 0
    current = 0
    for value in mask:
        if bool(value):
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def _path_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "trades": 0,
            "net_pnl_usd": 0.0,
            "configured_net_r": 0.0,
            "avg_configured_r": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "sl_pct": 0.0,
            "max_dd_configured_r": 0.0,
            "max_consecutive_losses": 0,
            "max_consecutive_wins": 0,
            "loss_after_loss_pct": 0.0,
            "three_loss_cluster_count": 0,
            "three_loss_cluster_pct": 0.0,
        }
    ordered = frame.sort_values(["entry_local", "session", "exit_local"]).copy()
    r = pd.to_numeric(ordered["scenario_configured_net_r"], errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(ordered["scenario_pnl_usd"], errors="coerce").fillna(0.0)
    losses = r < 0.0
    wins = r > 0.0
    equity = r.cumsum()
    dd = equity - equity.cummax()
    win_sum = r[wins].sum()
    loss_sum = -r[losses].sum()
    after_loss = losses.shift(1, fill_value=False)
    loss_after_loss_n = int((after_loss & losses).sum())
    after_loss_n = int(after_loss.sum())
    rolling_loss_3 = losses.astype(int).rolling(3).sum().fillna(0) == 3
    return {
        "trades": int(len(ordered)),
        "net_pnl_usd": float(pnl.sum()),
        "configured_net_r": float(r.sum()),
        "avg_configured_r": float(r.mean()),
        "win_rate_pct": float(wins.mean() * 100.0),
        "profit_factor": float(win_sum / loss_sum) if loss_sum > 0.0 else float("inf"),
        "sl_pct": float(ordered["exit_type"].astype(str).str.contains("sl").mean() * 100.0),
        "max_dd_configured_r": float(dd.min()) if len(dd) else 0.0,
        "max_consecutive_losses": _max_consecutive(losses),
        "max_consecutive_wins": _max_consecutive(wins),
        "loss_after_loss_pct": float(loss_after_loss_n / after_loss_n * 100.0) if after_loss_n else 0.0,
        "three_loss_cluster_count": int(rolling_loss_3.sum()),
        "three_loss_cluster_pct": float(rolling_loss_3.mean() * 100.0),
    }


def _bucket_loss_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = [("portfolio", frame), *[(str(k), v) for k, v in frame.groupby("session")]]
    for window in WINDOWS:
        for scope, scope_frame in scopes:
            wframe = _window_frame(scope_frame, window)
            for bucket in BUCKET_ORDER:
                bframe = wframe[wframe["ath_bucket"] == bucket]
                if bframe.empty:
                    continue
                rows.append(
                    {
                        "window": window,
                        "scope": scope,
                        "ath_bucket": bucket,
                        **_path_metrics(bframe),
                    }
                )
    return pd.DataFrame(rows)


def _correlations(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = [("portfolio", frame), *[(str(k), v) for k, v in frame.groupby("session")]]
    for scope, sframe in scopes:
        cleaned = sframe[["scenario_configured_net_r", "ath_gap_pct", "days_since_ath"]].replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if len(cleaned) < 10:
            continue
        rows.append(
            {
                "scope": scope,
                "trades": int(len(cleaned)),
                "pearson_gap": float(
                    cleaned["scenario_configured_net_r"].corr(cleaned["ath_gap_pct"], method="pearson")
                ),
                "spearman_gap": float(
                    cleaned["scenario_configured_net_r"].corr(cleaned["ath_gap_pct"], method="spearman")
                ),
                "pearson_days_since_ath": float(
                    cleaned["scenario_configured_net_r"].corr(cleaned["days_since_ath"], method="pearson")
                ),
                "spearman_days_since_ath": float(
                    cleaned["scenario_configured_net_r"].corr(cleaned["days_since_ath"], method="spearman")
                ),
            }
        )
    return pd.DataFrame(rows)


def _scenario_scorecard(frames: dict[str, pd.DataFrame], *, scenario_meta: dict[str, dict[str, Any]]) -> pd.DataFrame:
    baseline = frames["BASELINE"]
    rows: list[dict[str, Any]] = []
    for name, frame in frames.items():
        meta = scenario_meta.get(name, {})
        for window in WINDOWS:
            metrics = _path_metrics(_window_frame(frame, window))
            base_metrics = _path_metrics(_window_frame(baseline, window))
            rows.append(
                {
                    "scenario": name,
                    "kind": meta.get("kind", "exact"),
                    "deployability": meta.get("deployability", ""),
                    "window": window,
                    "trade_delta": metrics["trades"] - base_metrics["trades"],
                    "delta_pnl_usd": metrics["net_pnl_usd"] - base_metrics["net_pnl_usd"],
                    "delta_configured_net_r": metrics["configured_net_r"] - base_metrics["configured_net_r"],
                    "delta_max_dd_configured_r": metrics["max_dd_configured_r"] - base_metrics["max_dd_configured_r"],
                    "delta_max_consecutive_losses": (
                        metrics["max_consecutive_losses"] - base_metrics["max_consecutive_losses"]
                    ),
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def _apply_haircut(base: pd.DataFrame, variant: HaircutVariant) -> pd.DataFrame:
    frame = base.copy()
    frame["scenario"] = variant.name
    frame["scenario_kind"] = "post_haircut"
    mask = frame["session"].isin(variant.sessions) & frame["ath_bucket"].isin(variant.buckets)
    frame.loc[mask, "scenario_pnl_usd"] = frame.loc[mask, "scenario_pnl_usd"] * variant.factor
    frame.loc[mask, "scenario_configured_net_r"] = (
        frame.loc[mask, "scenario_configured_net_r"] * variant.factor
    )
    frame["haircut_applied"] = mask
    return frame


def _date_range_every(start: date, end: date, every_days: int) -> list[date]:
    out: list[date] = []
    current = start
    while current <= end:
        out.append(current)
        current += timedelta(days=every_days)
    return out


def _simulate_first_payout_proxy(
    frame: pd.DataFrame,
    *,
    window: str,
    payout_r: float = 5.0,
    breach_r: float = -4.0,
    stagger_days: int = 14,
) -> list[dict[str, Any]]:
    wframe = _window_frame(frame, window)
    if wframe.empty:
        return []
    daily = (
        wframe.assign(entry_day=pd.to_datetime(wframe["entry_local"]).dt.date)
        .groupby("entry_day")["scenario_configured_net_r"]
        .sum()
        .sort_index()
    )
    start = daily.index.min()
    end = daily.index.max()
    outcomes: list[dict[str, Any]] = []
    for account_id, start_day in enumerate(_date_range_every(start, end, stagger_days), start=1):
        equity = 0.0
        outcome = "open"
        outcome_day = end
        for day, r_value in daily[daily.index >= start_day].items():
            equity += float(r_value)
            outcome_day = day
            if equity >= payout_r:
                outcome = "payout"
                break
            if equity <= breach_r:
                outcome = "breach"
                break
        outcomes.append(
            {
                "account_id": account_id,
                "window": window,
                "start_date": start_day.isoformat(),
                "outcome_date": outcome_day.isoformat(),
                "outcome": outcome,
                "days_to_outcome": int((outcome_day - start_day).days),
                "final_r": float(equity),
            }
        )
    return outcomes


def _max_consecutive_outcome(outcomes: list[dict[str, Any]], outcome: str) -> int:
    longest = 0
    current = 0
    for row in sorted(outcomes, key=lambda item: item["start_date"]):
        if row["outcome"] == outcome:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _payout_summary(frames: dict[str, pd.DataFrame], *, scenario_meta: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for name, frame in frames.items():
        meta = scenario_meta.get(name, {})
        for window in ("2024+", "2025+", "2026_ytd", "2026_05+"):
            outcomes = _simulate_first_payout_proxy(frame, window=window)
            for row in outcomes:
                detail_rows.append({"scenario": name, **row})
            payouts = [row for row in outcomes if row["outcome"] == "payout"]
            breaches = [row for row in outcomes if row["outcome"] == "breach"]
            resolved = payouts + breaches
            summary_rows.append(
                {
                    "scenario": name,
                    "kind": meta.get("kind", ""),
                    "deployability": meta.get("deployability", ""),
                    "window": window,
                    "accounts": len(outcomes),
                    "payouts": len(payouts),
                    "breaches": len(breaches),
                    "open": len([row for row in outcomes if row["outcome"] == "open"]),
                    "resolved_payout_rate_pct": (
                        len(payouts) / len(resolved) * 100.0 if resolved else 0.0
                    ),
                    "breach_rate_pct": len(breaches) / len(outcomes) * 100.0 if outcomes else 0.0,
                    "median_days_to_payout": (
                        float(np.median([row["days_to_outcome"] for row in payouts])) if payouts else np.nan
                    ),
                    "max_consecutive_breaches": _max_consecutive_outcome(outcomes, "breach"),
                    "ev_per_account_r": (
                        float(np.mean([
                            5.0 if row["outcome"] == "payout" else -4.0 if row["outcome"] == "breach" else row["final_r"]
                            for row in outcomes
                        ]))
                        if outcomes
                        else 0.0
                    ),
                }
            )
    return pd.DataFrame(summary_rows), pd.DataFrame(detail_rows)


def _write_report(
    *,
    start_date: str,
    end_date: str,
    latest_data_ts: datetime,
    baseline_result: dict[str, Any],
    bucket_summary: pd.DataFrame,
    correlations: pd.DataFrame,
    scorecard: pd.DataFrame,
    payout_summary: pd.DataFrame,
) -> None:
    baseline_summary = baseline_result["summary"]
    top_bucket = bucket_summary[
        (bucket_summary["scope"] == "portfolio")
        & bucket_summary["window"].isin(["full", "2025+", "2026_ytd", "2026_05+"])
    ][
        [
            "window",
            "ath_bucket",
            "trades",
            "configured_net_r",
            "avg_configured_r",
            "profit_factor",
            "max_dd_configured_r",
            "max_consecutive_losses",
            "loss_after_loss_pct",
            "three_loss_cluster_count",
        ]
    ].copy()
    leg_focus = bucket_summary[
        (bucket_summary["window"].isin(["2025+", "2026_ytd", "2026_05+"]))
        & (bucket_summary["ath_bucket"].isin(["0.5-1%", "5-10%"]))
        & (bucket_summary["scope"] != "portfolio")
    ][
        [
            "window",
            "scope",
            "ath_bucket",
            "trades",
            "configured_net_r",
            "avg_configured_r",
            "profit_factor",
            "max_dd_configured_r",
            "max_consecutive_losses",
        ]
    ].copy()
    exact_focus = scorecard[
        (scorecard["kind"] == "exact")
        & (scorecard["window"].isin(["full", "2025+", "2026_ytd", "2026_05+"]))
    ][
        [
            "scenario",
            "window",
            "trades",
            "trade_delta",
            "delta_pnl_usd",
            "delta_configured_net_r",
            "configured_net_r",
            "profit_factor",
            "max_dd_configured_r",
            "max_consecutive_losses",
            "delta_max_consecutive_losses",
        ]
    ].copy()
    haircut_focus = scorecard[
        (scorecard["kind"] == "post_haircut")
        & (scorecard["window"].isin(["full", "2025+", "2026_ytd", "2026_05+"]))
    ][
        [
            "scenario",
            "window",
            "trade_delta",
            "delta_pnl_usd",
            "delta_configured_net_r",
            "configured_net_r",
            "profit_factor",
            "max_dd_configured_r",
            "max_consecutive_losses",
        ]
    ].copy()
    payout_focus = payout_summary[
        payout_summary["window"].isin(["2025+", "2026_ytd", "2026_05+"])
    ][
        [
            "scenario",
            "kind",
            "window",
            "accounts",
            "payouts",
            "breaches",
            "resolved_payout_rate_pct",
            "breach_rate_pct",
            "median_days_to_payout",
            "max_consecutive_breaches",
            "ev_per_account_r",
        ]
    ].copy()
    lines = [
        "# ALPHA_V1 ATH Fragility - 2026-06-08",
        "",
        "## Scope",
        "",
        f"- Profile: `{PROFILE}`",
        f"- Exact replay window: `{start_date}` to `{end_date}`",
        f"- Latest common ES/NQ local data timestamp: `{latest_data_ts.isoformat()}`",
        "- Inputs are local ES/NQ OHLCV files only. The latest DataBento pull warned that `2026-05-24` is degraded.",
        "- ATH bucket labels use fill-time 5m-bar context as an attribution proxy. Native hard gates evaluate on the closed signal bar before order arming.",
        "- Exact hard-gate variants are `live_native` for ORB sessions. Post-haircut variants are `research_only` until live ATH-conditioned risk sizing exists.",
        "- First-payout proxy uses a simple `+5R` payout / `-4R` breach model with a new account every 14 calendar days.",
        "",
        "## Fresh Baseline Exact Summary",
        "",
        (
            f"- Trades: `{baseline_summary['total_trades']}`; net PnL: "
            f"`${baseline_summary['total_pnl_usd']:.2f}`; engine-native net R: "
            f"`{baseline_summary.get('total_net_r', 0.0):.2f}`; PF: "
            f"`{baseline_summary['profit_factor']:.2f}`; max DD: "
            f"`${baseline_summary['max_drawdown_usd']:.2f}`; max consecutive losses: "
            f"`{baseline_summary.get('max_consecutive_losses', 0)}`"
        ),
        "",
        "## Baseline ATH Buckets",
        "",
        _markdown_table(top_bucket.round(3)),
        "",
        "## Leg Focus: Moderate and Deeper Dip Buckets",
        "",
        _markdown_table(leg_focus.round(3)),
        "",
        "## Continuous Correlation Check",
        "",
        _markdown_table(correlations.round(4)),
        "",
        "## Exact Native Hard-Gate Scorecard",
        "",
        _markdown_table(exact_focus.round(3)),
        "",
        "## Post-Trade Risk Haircut Scorecard",
        "",
        _markdown_table(haircut_focus.round(3)),
        "",
        "## First-Payout Proxy Scorecard",
        "",
        _markdown_table(payout_focus.round(3)),
        "",
        "## Artifacts",
        "",
        f"- `{RESULT_DIR / 'baseline_raw_result.json'}`",
        f"- `{RESULT_DIR / 'baseline_trades_ath_annotated.csv'}`",
        f"- `{RESULT_DIR / 'bucket_loss_summary.csv'}`",
        f"- `{RESULT_DIR / 'ath_correlations.csv'}`",
        f"- `{RESULT_DIR / 'scenario_scorecard.csv'}`",
        f"- `{RESULT_DIR / 'payout_proxy_summary.csv'}`",
        f"- `{RESULT_DIR / 'payout_proxy_accounts.csv'}`",
        f"- `{RESULT_DIR / 'summary.json'}`",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(DEFAULT_CONFIG)
    latest_data_ts = latest_common_end(SYMBOLS)
    start_date, end_date = rolling_year_window_endpoints(latest_data_ts, args.years)

    baseline_result = _run_or_load(
        config=config,
        start_date=start_date,
        end_date=end_date,
        latest_data_ts=latest_data_ts,
        path=RESULT_DIR / "baseline_raw_result.json",
        label=f"EXEC EXACT {PROFILE} BASELINE {start_date} to {end_date}",
        refresh=args.refresh,
    )
    frames: dict[str, pd.DataFrame] = {
        "BASELINE": _prepare_trades(baseline_result, "BASELINE"),
    }
    scenario_meta: dict[str, dict[str, Any]] = {
        "BASELINE": {
            "kind": "exact",
            "deployability": "live_native",
            "thesis": "Current live execution profile.",
        }
    }
    raw_summaries: dict[str, Any] = {"BASELINE": baseline_result["summary"]}

    frames["BASELINE"].to_csv(RESULT_DIR / "baseline_trades_ath_annotated.csv", index=False)

    for variant in EXACT_VARIANTS:
        result = _run_or_load(
            config=config,
            start_date=start_date,
            end_date=end_date,
            latest_data_ts=latest_data_ts,
            path=RESULT_DIR / f"{variant.name}_raw_result.json",
            label=f"EXEC EXACT {PROFILE} {variant.name} {start_date} to {end_date}",
            refresh=args.refresh,
            profile_session_overrides=variant.overrides,
        )
        frame = _prepare_trades(result, variant.name)
        frame.to_csv(RESULT_DIR / f"{variant.name}_trades_ath_annotated.csv", index=False)
        frames[variant.name] = frame
        raw_summaries[variant.name] = result["summary"]
        scenario_meta[variant.name] = {
            "kind": "exact",
            "deployability": "live_native",
            "thesis": variant.thesis,
            "overrides": variant.overrides,
        }

    for variant in HAIRCUT_VARIANTS:
        frame = _apply_haircut(frames["BASELINE"], variant)
        frame.to_csv(RESULT_DIR / f"{variant.name}_trades_ath_annotated.csv", index=False)
        frames[variant.name] = frame
        scenario_meta[variant.name] = {
            "kind": "post_haircut",
            "deployability": "research_only",
            "thesis": variant.thesis,
            "sessions": variant.sessions,
            "buckets": variant.buckets,
            "factor": variant.factor,
        }

    bucket_summary = _bucket_loss_summary(frames["BASELINE"])
    correlations = _correlations(frames["BASELINE"])
    scorecard = _scenario_scorecard(frames, scenario_meta=scenario_meta)
    payout_summary, payout_accounts = _payout_summary(frames, scenario_meta=scenario_meta)

    bucket_summary.to_csv(RESULT_DIR / "bucket_loss_summary.csv", index=False)
    correlations.to_csv(RESULT_DIR / "ath_correlations.csv", index=False)
    scorecard.to_csv(RESULT_DIR / "scenario_scorecard.csv", index=False)
    payout_summary.to_csv(RESULT_DIR / "payout_proxy_summary.csv", index=False)
    payout_accounts.to_csv(RESULT_DIR / "payout_proxy_accounts.csv", index=False)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": PROFILE,
        "start_date": start_date,
        "end_date": end_date,
        "latest_data_ts": latest_data_ts.isoformat(),
        "exact_variants": [variant.name for variant in EXACT_VARIANTS],
        "haircut_variants": [variant.name for variant in HAIRCUT_VARIANTS],
        "raw_summaries": raw_summaries,
        "paths": {
            "results": str(RESULT_DIR),
            "report": str(REPORT_PATH),
        },
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    _write_report(
        start_date=start_date,
        end_date=end_date,
        latest_data_ts=latest_data_ts,
        baseline_result=baseline_result,
        bucket_summary=bucket_summary,
        correlations=correlations,
        scorecard=scorecard,
        payout_summary=payout_summary,
    )
    print(json.dumps({
        "profile": PROFILE,
        "start_date": start_date,
        "end_date": end_date,
        "latest_data_ts": latest_data_ts.isoformat(),
        "results": str(RESULT_DIR),
        "report": str(REPORT_PATH),
    }, indent=2))


if __name__ == "__main__":
    main()
