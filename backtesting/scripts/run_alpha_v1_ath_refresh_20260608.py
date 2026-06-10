#!/usr/bin/env python3
"""Refresh ALPHA_V1-A exact replay and ATH attribution packet.

Runs the live execution-engine exact replay for ALPHA_V1-A, then reruns the
same profile with a surgical ES_NY 0.50-0.75% ATH block. The baseline trades
are annotated with fill-proxy ATH distance features for quick regime review.

Report bucket/comparison R values are configured-risk R: trade PnL divided by
the current profile risk for that session. Engine-native `net_r_multiple` is
kept in the raw result and summary for execution-model parity.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
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


PROFILE = "ALPHA_V1-A"
SHADOW_NAME = "ALPHA_V1-A_ES_NY_ATH_0P5_0P75"
RESULT_DIR = BACKTESTING_ROOT / "data" / "results" / "alpha_v1_ath_refresh_20260608"
REPORT_PATH = BACKTESTING_ROOT / "learnings" / "reports" / "ALPHA_V1_ATH_REFRESH_20260608.md"
SYMBOLS = ["ES", "NQ"]
WINDOWS = {
    "full": None,
    "2024+": "2024-01-01",
    "2025+": "2025-01-01",
    "2026_ytd": "2026-01-01",
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _pct_bucket(gap_pct: float) -> str:
    if not math.isfinite(gap_pct):
        return "unknown"
    if gap_pct < 0.0:
        return "above_prior_ath"
    if gap_pct <= 0.5:
        return "0-0.5%"
    if gap_pct <= 1.0:
        return "0.5-1%"
    if gap_pct <= 2.0:
        return "1-2%"
    if gap_pct <= 5.0:
        return "2-5%"
    if gap_pct <= 10.0:
        return "5-10%"
    return ">10%"


def _symbol_for_session(session: str) -> str:
    return "ES" if str(session).upper().startswith("ES") else "NQ"


def _risk_for_session(result: dict[str, Any], session: str) -> float:
    config = result.get("config", {})
    key = f"{str(session).lower()}_risk_usd"
    if key in config:
        return _safe_float(config[key], 0.0)
    return _safe_float(config.get("risk_usd"), 0.0)


def _result_to_frame(result: dict[str, Any]) -> pd.DataFrame:
    trades = pd.DataFrame(result.get("trades", []))
    if trades.empty:
        return trades
    trades["entry_local"] = (
        pd.to_datetime(trades["entry_time"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    trades["exit_local"] = (
        pd.to_datetime(trades["exit_time"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    risks = trades["session"].map(lambda session: _risk_for_session(result, str(session)))
    pnl = pd.to_numeric(trades["pnl_usd"], errors="coerce")
    fallback_r = pd.to_numeric(trades.get("net_r_multiple", np.nan), errors="coerce")
    trades["configured_net_r"] = np.where(risks > 0.0, pnl / risks, fallback_r)
    trades["symbol"] = trades["session"].map(_symbol_for_session)
    return trades.sort_values(["entry_local", "session", "exit_local"]).reset_index(drop=True)


def _load_ath_context(symbol: str) -> dict[str, Any]:
    path = BACKTESTING_ROOT / "data" / "raw" / f"{symbol}_5m.parquet"
    df = pd.read_parquet(path, columns=["high", "close"]).sort_index()
    high = df["high"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    cum_high = np.maximum.accumulate(high)
    prior_high = np.concatenate([[np.nan], cum_high[:-1]])

    last_pos = np.empty(len(high), dtype=np.int64)
    running = -np.inf
    last = -1
    for pos, value in enumerate(high):
        if value >= running:
            running = value
            last = pos
        last_pos[pos] = last

    return {
        "index": df.index.to_numpy(),
        "prior_high": prior_high,
        "close": close,
        "last_pos": last_pos,
    }


def _annotate_ath(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    contexts = {symbol: _load_ath_context(symbol) for symbol in sorted(trades["symbol"].unique())}
    rows: list[dict[str, Any]] = []
    for _, trade in trades.iterrows():
        ctx = contexts[str(trade["symbol"])]
        ref_ts = np.datetime64(pd.Timestamp(trade["entry_local"]).floor("5min"))
        pos = int(np.searchsorted(ctx["index"], ref_ts, side="right") - 1)
        gap_pct = float("nan")
        prior_ath = float("nan")
        ref_close = float("nan")
        days_since_ath = float("nan")
        ath_ref_time = None
        if pos >= 0:
            prior_ath = float(ctx["prior_high"][pos])
            ref_close = float(ctx["close"][pos])
            ath_ref_time = pd.Timestamp(ctx["index"][pos]).isoformat()
            if math.isfinite(prior_ath) and prior_ath > 0.0 and math.isfinite(ref_close):
                gap_pct = (prior_ath - ref_close) / prior_ath * 100.0
                last_pos = int(ctx["last_pos"][pos])
                if last_pos >= 0:
                    days_since_ath = float(
                        (ctx["index"][pos] - ctx["index"][last_pos]) / np.timedelta64(1, "D")
                    )
        rows.append(
            {
                "ath_gap_pct": gap_pct,
                "ath_bucket": _pct_bucket(gap_pct),
                "prior_ath": prior_ath,
                "ath_ref_close": ref_close,
                "ath_ref_time": ath_ref_time,
                "days_since_ath": days_since_ath,
            }
        )
    annotated = trades.copy()
    for key in rows[0]:
        annotated[key] = [row[key] for row in rows]
    return annotated


def _trade_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "trades": 0,
            "configured_net_r": 0.0,
            "avg_configured_r": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "sl_pct": 0.0,
            "max_dd_configured_r": 0.0,
        }
    r = pd.to_numeric(frame["configured_net_r"], errors="coerce").fillna(0.0)
    wins = r[r > 0.0].sum()
    losses = -r[r < 0.0].sum()
    equity = r.cumsum()
    dd = equity - equity.cummax()
    return {
        "trades": int(len(frame)),
        "configured_net_r": float(r.sum()),
        "avg_configured_r": float(r.mean()),
        "win_rate_pct": float((r > 0.0).mean() * 100.0),
        "profit_factor": float(wins / losses) if losses > 0.0 else float("inf"),
        "sl_pct": float(frame["exit_type"].astype(str).str.contains("sl").mean() * 100.0),
        "max_dd_configured_r": float(dd.min()) if len(dd) else 0.0,
    }


def _window_frame(frame: pd.DataFrame, window: str) -> pd.DataFrame:
    start = WINDOWS[window]
    if start is None:
        return frame
    return frame[frame["entry_local"] >= pd.Timestamp(start)]


def _bucket_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for window in WINDOWS:
        wframe = _window_frame(frame, window)
        for bucket in BUCKET_ORDER:
            bframe = wframe[wframe["ath_bucket"] == bucket]
            if bframe.empty:
                continue
            rows.append({"window": window, "ath_bucket": bucket, **_trade_metrics(bframe)})
    return pd.DataFrame(rows)


def _correlations(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = [("portfolio", frame), *[(str(k), v) for k, v in frame.groupby("session")]]
    for scope, sframe in scopes:
        cleaned = sframe[["configured_net_r", "ath_gap_pct", "days_since_ath"]].replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if len(cleaned) < 10:
            continue
        rows.append(
            {
                "scope": scope,
                "trades": int(len(cleaned)),
                "pearson_gap": float(
                    cleaned["configured_net_r"].corr(cleaned["ath_gap_pct"], method="pearson")
                ),
                "spearman_gap": float(
                    cleaned["configured_net_r"].corr(cleaned["ath_gap_pct"], method="spearman")
                ),
                "pearson_days_since_ath": float(
                    cleaned["configured_net_r"].corr(cleaned["days_since_ath"], method="pearson")
                ),
                "spearman_days_since_ath": float(
                    cleaned["configured_net_r"].corr(cleaned["days_since_ath"], method="spearman")
                ),
            }
        )
    return pd.DataFrame(rows)


def _comparison_rows(baseline: pd.DataFrame, shadow: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for window in WINDOWS:
        base = _trade_metrics(_window_frame(baseline, window))
        gated = _trade_metrics(_window_frame(shadow, window))
        rows.append(
            {
                "window": window,
                "baseline_trades": base["trades"],
                "shadow_trades": gated["trades"],
                "trade_delta": gated["trades"] - base["trades"],
                "baseline_configured_net_r": base["configured_net_r"],
                "shadow_configured_net_r": gated["configured_net_r"],
                "delta_configured_net_r": gated["configured_net_r"] - base["configured_net_r"],
                "baseline_pf": base["profit_factor"],
                "shadow_pf": gated["profit_factor"],
                "baseline_dd_configured_r": base["max_dd_configured_r"],
                "shadow_dd_configured_r": gated["max_dd_configured_r"],
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame, digits: int = 3) -> str:
    if frame.empty:
        return "_No rows._"
    lines = [
        "| " + " | ".join(map(str, frame.columns)) + " |",
        "| " + " | ".join("---" for _ in frame.columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = []
        for value in row:
            if isinstance(value, float):
                if math.isfinite(value):
                    values.append(f"{value:.{digits}f}")
                elif math.isnan(value):
                    values.append("nan")
                else:
                    values.append("inf")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


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


def _write_report(
    *,
    start_date: str,
    end_date: str,
    latest_data_ts: datetime,
    baseline_result: dict[str, Any],
    shadow_result: dict[str, Any],
    bucket_summary: pd.DataFrame,
    correlations: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    baseline_summary = baseline_result["summary"]
    shadow_summary = shadow_result["summary"]
    top_buckets = bucket_summary[bucket_summary["window"].isin(["full", "2025+", "2026_ytd"])].copy()
    top_buckets = top_buckets[
        [
            "window",
            "ath_bucket",
            "trades",
            "configured_net_r",
            "avg_configured_r",
            "win_rate_pct",
            "profit_factor",
            "sl_pct",
            "max_dd_configured_r",
        ]
    ]
    full_comparison = comparison[comparison["window"] == "full"].iloc[0].to_dict()
    lines = [
        "# ALPHA_V1 ATH Refresh - 2026-06-08",
        "",
        "## Scope",
        "",
        f"- Profile: `{PROFILE}`",
        f"- Exact replay window: `{start_date}` to `{end_date}`",
        f"- Latest common local data timestamp: `{latest_data_ts.isoformat()}`",
        "- Note: this packet uses fill-time 5m-bar ATH context as a quick attribution proxy; "
        "live ORB ATH gates evaluate on the closed signal bar before order arming.",
        "- Bucket and shadow-comparison R values are configured-risk R: trade PnL divided by "
        "the current profile risk for that session. Exact summaries use engine-native net R.",
        "",
        "## Baseline Exact Summary",
        "",
        (
            f"- Trades: `{baseline_summary['total_trades']}`; net PnL: "
            f"`${baseline_summary['total_pnl_usd']:.2f}`; net R: "
            f"`{baseline_summary.get('total_net_r', 0.0):.2f}`; "
            f"PF: `{baseline_summary['profit_factor']:.2f}`; "
            f"max DD: `${baseline_summary['max_drawdown_usd']:.2f}`"
        ),
        "",
        "## Baseline ATH Buckets",
        "",
        _markdown_table(top_buckets.round(3)),
        "",
        "## Continuous Correlation Check",
        "",
        _markdown_table(correlations.round(4)),
        "",
        "## ES NY ATH Shadow Comparison",
        "",
        (
            f"Shadow applies only `ES_NY ath_block_min_pct=0.5` and "
            f"`ath_block_max_pct=0.75` to `{PROFILE}`."
        ),
        (
            f"Full-window deltas: `${shadow_summary['total_pnl_usd'] - baseline_summary['total_pnl_usd']:.2f}` "
            f"net PnL; `{shadow_summary.get('total_net_r', 0.0) - baseline_summary.get('total_net_r', 0.0):.2f}` "
            f"engine-native net R; "
            f"`{full_comparison['delta_configured_net_r']:.2f}` configured-risk net R."
        ),
        "",
        _markdown_table(comparison.round(3)),
        "",
        "## Shadow Exact Summary",
        "",
        (
            f"- Trades: `{shadow_summary['total_trades']}`; net PnL: "
            f"`${shadow_summary['total_pnl_usd']:.2f}`; net R: "
            f"`{shadow_summary.get('total_net_r', 0.0):.2f}`; "
            f"PF: `{shadow_summary['profit_factor']:.2f}`; "
            f"max DD: `${shadow_summary['max_drawdown_usd']:.2f}`"
        ),
        "",
        "## Artifacts",
        "",
        f"- `{RESULT_DIR / 'ALPHA_V1-A_raw_result.json'}`",
        f"- `{RESULT_DIR / 'ALPHA_V1-A_trades_ath_annotated.csv'}`",
        f"- `{RESULT_DIR / 'ALPHA_V1-A_ath_bucket_summary.csv'}`",
        f"- `{RESULT_DIR / 'ALPHA_V1-A_ath_correlations.csv'}`",
        f"- `{RESULT_DIR / 'ALPHA_V1-A_ES_NY_ATH_0P5_0P75_raw_result.json'}`",
        f"- `{RESULT_DIR / 'ALPHA_V1-A_ES_NY_ATH_0P5_0P75_trades_ath_annotated.csv'}`",
        f"- `{RESULT_DIR / 'shadow_comparison.csv'}`",
        f"- `{RESULT_DIR / 'summary.json'}`",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=5, help="Rolling exact replay window in years")
    parser.add_argument("--refresh", action="store_true", help="Ignore cached raw exact results")
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
        path=RESULT_DIR / "ALPHA_V1-A_raw_result.json",
        label=f"EXEC EXACT {PROFILE} {start_date} to {end_date}",
        refresh=args.refresh,
    )
    shadow_result = _run_or_load(
        config=config,
        start_date=start_date,
        end_date=end_date,
        latest_data_ts=latest_data_ts,
        path=RESULT_DIR / "ALPHA_V1-A_ES_NY_ATH_0P5_0P75_raw_result.json",
        label=f"EXEC EXACT {SHADOW_NAME} {start_date} to {end_date}",
        refresh=args.refresh,
        profile_session_overrides={
            "ES_NY": {
                "ath_block_min_pct": 0.5,
                "ath_block_max_pct": 0.75,
            }
        },
    )

    baseline_trades = _annotate_ath(_result_to_frame(baseline_result))
    shadow_trades = _annotate_ath(_result_to_frame(shadow_result))
    baseline_trades.to_csv(RESULT_DIR / "ALPHA_V1-A_trades_ath_annotated.csv", index=False)
    shadow_trades.to_csv(
        RESULT_DIR / "ALPHA_V1-A_ES_NY_ATH_0P5_0P75_trades_ath_annotated.csv",
        index=False,
    )

    bucket_summary = _bucket_summary(baseline_trades)
    correlations = _correlations(baseline_trades)
    comparison = _comparison_rows(baseline_trades, shadow_trades)
    bucket_summary.to_csv(RESULT_DIR / "ALPHA_V1-A_ath_bucket_summary.csv", index=False)
    correlations.to_csv(RESULT_DIR / "ALPHA_V1-A_ath_correlations.csv", index=False)
    comparison.to_csv(RESULT_DIR / "shadow_comparison.csv", index=False)

    full_comparison = comparison[comparison["window"] == "full"].iloc[0].to_dict()
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": PROFILE,
        "shadow": SHADOW_NAME,
        "start_date": start_date,
        "end_date": end_date,
        "latest_data_ts": latest_data_ts.isoformat(),
        "baseline_trades": int(baseline_result["summary"]["total_trades"]),
        "baseline_total_pnl_usd": float(baseline_result["summary"].get("total_pnl_usd", 0.0)),
        "baseline_engine_net_r": float(baseline_result["summary"].get("total_net_r", 0.0)),
        "baseline_configured_net_r": float(full_comparison["baseline_configured_net_r"]),
        "shadow_trades": int(shadow_result["summary"]["total_trades"]),
        "shadow_total_pnl_usd": float(shadow_result["summary"].get("total_pnl_usd", 0.0)),
        "shadow_engine_net_r": float(shadow_result["summary"].get("total_net_r", 0.0)),
        "shadow_configured_net_r": float(full_comparison["shadow_configured_net_r"]),
        "delta_pnl_usd": float(
            shadow_result["summary"].get("total_pnl_usd", 0.0)
            - baseline_result["summary"].get("total_pnl_usd", 0.0)
        ),
        "delta_engine_net_r": float(
            shadow_result["summary"].get("total_net_r", 0.0)
            - baseline_result["summary"].get("total_net_r", 0.0)
        ),
        "delta_configured_net_r": float(full_comparison["delta_configured_net_r"]),
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
        shadow_result=shadow_result,
        bucket_summary=bucket_summary,
        correlations=correlations,
        comparison=comparison,
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
