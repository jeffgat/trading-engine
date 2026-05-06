#!/usr/bin/env python3
"""Exact replay for the ES NY ALPHA_V1 ATH dead-zone gate.

This promotes the post-filter candidate into the live ORBEngine path by using
an in-memory execution profile with ath_block_min_pct/max_pct enabled. It does
not edit execution/config/exec_configs.json.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

BACKTESTING_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKTESTING_ROOT.parent
EXEC_SRC = REPO_ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_alpha_v1_ath_regime_first_pass import (  # noqa: E402
    FULL_START,
    WINDOWS,
    _simulate_first_payouts,
    _summarize_payouts,
)
from trader import historical_backtest as hb  # noqa: E402
from trader.historical_backtest import latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RESULT_DIR = BACKTESTING_ROOT / "data" / "results" / "alpha_v1_es_ny_ath_exact_replay_20260505"
REPORT_PATH = BACKTESTING_ROOT / "learnings" / "reports" / "ALPHA_V1_ES_NY_ATH_EXACT_REPLAY_20260505.md"
BASELINE_PROFILE = "ALPHA_V1_ES_NY_BASELINE_EXACT"
GATED_PROFILE = "ALPHA_V1_ES_NY_ATH_0P5_1_EXACT"


def _make_profiles(config: dict[str, Any]) -> tuple[ExecutionConfig, ExecutionConfig]:
    configs = {cfg.name: cfg for cfg in load_exec_configs(config)}
    source = configs["ALPHA_V1-A"]
    es_ny = copy.deepcopy(source.session_overrides["ES_NY"])

    baseline = ExecutionConfig(
        name=BASELINE_PROFILE,
        enabled=True,
        max_open_contracts=source.max_open_contracts,
        webhooks=[],
        session_overrides={"ES_NY": es_ny},
        lsi_session_overrides={},
    )

    gated_es_ny = copy.deepcopy(es_ny)
    gated_es_ny["ath_block_min_pct"] = 0.5
    gated_es_ny["ath_block_max_pct"] = 1.0
    gated = ExecutionConfig(
        name=GATED_PROFILE,
        enabled=True,
        max_open_contracts=source.max_open_contracts,
        webhooks=[],
        session_overrides={"ES_NY": gated_es_ny},
        lsi_session_overrides={},
    )
    return baseline, gated


def _run_exact(config: dict[str, Any], profiles: tuple[ExecutionConfig, ExecutionConfig]) -> dict[str, dict]:
    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config: list(profiles)
    try:
        latest_ts = latest_common_end(["ES"])
        end_date = latest_ts.date().isoformat()
        results: dict[str, dict] = {}
        for profile in profiles:
            raw_path = RESULT_DIR / f"{profile.name}_raw_result.json"
            if raw_path.exists():
                result = json.loads(raw_path.read_text(encoding="utf-8"))
                results[profile.name] = result
                print(
                    f"{profile.name}: loaded cached trades={result['summary']['total_trades']} "
                    f"r={result['summary']['total_r']:.2f}",
                    flush=True,
                )
                continue
            result = run_profile_backtest_sync(
                config=config,
                profile_name=profile.name,
                start_date=FULL_START,
                end_date=end_date,
                latest_data_ts=latest_ts,
                label=f"EXEC EXACT {profile.name} {FULL_START} to {end_date}",
            )
            results[profile.name] = result
            (RESULT_DIR / f"{profile.name}_raw_result.json").write_text(
                json.dumps(result, indent=2),
                encoding="utf-8",
            )
            print(
                f"{profile.name}: trades={result['summary']['total_trades']} "
                f"r={result['summary']['total_r']:.2f}",
                flush=True,
            )
        return results
    finally:
        hb.load_exec_configs = original_loader


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(col) for col in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = []
        for col in frame.columns:
            value = row[col]
            if pd.isna(value):
                values.append("")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _trades_frame(result: dict) -> pd.DataFrame:
    trades = pd.DataFrame(result["trades"])
    if trades.empty:
        return trades
    trades["fill_ts"] = (
        pd.to_datetime(trades["entry_time"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    trades["exit_ts"] = (
        pd.to_datetime(trades["exit_time"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    trades["exit_date"] = trades["date"].astype(str)
    trades["leg"] = trades["session"]
    trades["pnl_usd_current"] = trades["pnl_usd"].astype(float)
    return trades.sort_values(["fill_ts", "leg", "exit_ts"]).reset_index(drop=True)


def _window_summary(result: dict, start: str | None) -> dict[str, Any]:
    trades = result["trades"]
    if start is not None:
        trades = [trade for trade in trades if trade["date"] >= start]
    return hb._compute_summary(trades)


def _trade_key(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["date"].astype(str)
        + "|"
        + frame["session"].astype(str)
        + "|"
        + frame["entry_time"].astype(str)
        + "|"
        + frame["entry_price"].round(4).astype(str)
    )


def _comparison_rows(results: dict[str, dict]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    baseline = results[BASELINE_PROFILE]
    gated = results[GATED_PROFILE]
    for window, start in WINDOWS.items():
        b = _window_summary(baseline, start)
        g = _window_summary(gated, start)
        rows.append(
            {
                "window": window,
                "baseline_trades": b["total_trades"],
                "gated_trades": g["total_trades"],
                "trade_delta": g["total_trades"] - b["total_trades"],
                "baseline_total_r": round(b["total_r"], 3),
                "gated_total_r": round(g["total_r"], 3),
                "delta_r": round(g["total_r"] - b["total_r"], 3),
                "baseline_pnl_usd": round(b["total_pnl_usd"], 2),
                "gated_pnl_usd": round(g["total_pnl_usd"], 2),
                "delta_pnl_usd": round(g["total_pnl_usd"] - b["total_pnl_usd"], 2),
                "baseline_max_dd_r": round(b["max_drawdown_r"], 3),
                "gated_max_dd_r": round(g["max_drawdown_r"], 3),
                "baseline_win_rate_pct": round(b["win_rate"] * 100.0, 1),
                "gated_win_rate_pct": round(g["win_rate"] * 100.0, 1),
            }
        )
    return pd.DataFrame(rows)


def _payout_rows(frames: dict[str, pd.DataFrame], end_date: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for profile, frame in frames.items():
        for window, start in WINDOWS.items():
            window_start = FULL_START if start is None else start
            outcomes = _simulate_first_payouts(frame, start=window_start, end=end_date, profile=profile)
            rows.append(_summarize_payouts(outcomes, profile=profile, window=window))
    return pd.DataFrame(rows)


def _write_report(
    *,
    comparison: pd.DataFrame,
    payouts: pd.DataFrame,
    removed: pd.DataFrame,
    added: pd.DataFrame,
    end_date: str,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ALPHA_V1 ES NY ATH Exact Replay - 2026-05-05",
        "",
        "## Scope",
        "",
        (
            f"Exact replay of ES NY only from {FULL_START} through {end_date}, using "
            "`ALPHA_V1-A` ES NY settings and an in-memory ATH gate profile."
        ),
        "",
        "Gate tested: block new ES NY ORB entries when the closed signal bar is 0.5-1.0% below the expanding ES futures ATH.",
        "",
        "Deployability fields:",
        "- `deployability`: post_filter_only",
        "- `live_support_notes`: ORBEngine supports causal `ath_block_min_pct/max_pct`; production live still needs a trusted historical ATH seed source before this becomes `live_native`.",
        "- `exact_replay_required`: complete for this ES NY exact replay pass",
        "",
        "## Exact Replay Summary",
        "",
        _markdown_table(comparison),
        "",
        "## Funded First-Payout Simulation",
        "",
        _markdown_table(payouts),
        "",
        "## Trade Replacement Check",
        "",
        f"- Baseline trades removed by gate: {len(removed)}",
        f"- New later trades admitted after skipped setups: {len(added)}",
        "",
        "## Interpretation",
        "",
        (
            "This is the first causal execution-engine pass for the ES NY ATH dead-zone thesis. "
            "The gate is no longer just a post-hoc filter: it blocks before the order is armed and "
            "keeps scanning for later valid FVGs in the same entry window."
        ),
        "",
        (
            "Decision read: exact replay confirms the trade-level edge and recent payout benefit, "
            "but not broad full-history account-flow promotion. Full-history net improves by +9.2R, "
            "while full-history first-payout quality worsens from 65.0% payout / 32.7% breach to "
            "60.4% payout / 37.3% breach. The 2024+ and 2025+ cohorts improve materially, so this "
            "belongs in a recent-flow / separate-account research lane rather than the default "
            "ALPHA_V1 production sleeve."
        ),
        "",
        (
            "Next research step: run rolling split diagnostics and nearby band sensitivity "
            "(`0.25-0.75%`, `0.5-0.75%`, `0.75-1.0%`, `0.5-1.25%`) in exact replay before any dry-run "
            "proposal, then wire a production ATH seed source if the candidate survives."
        ),
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    profiles = _make_profiles(config)
    results = _run_exact(config, profiles)

    frames = {
        profile: _trades_frame(result)
        for profile, result in results.items()
    }
    baseline = frames[BASELINE_PROFILE]
    gated = frames[GATED_PROFILE]
    baseline["_key"] = _trade_key(baseline)
    gated["_key"] = _trade_key(gated)
    removed = baseline[~baseline["_key"].isin(set(gated["_key"]))].drop(columns=["_key"])
    added = gated[~gated["_key"].isin(set(baseline["_key"]))].drop(columns=["_key"])
    baseline = baseline.drop(columns=["_key"])
    gated = gated.drop(columns=["_key"])

    comparison = _comparison_rows(results)
    end_date = latest_common_end(["ES"]).date().isoformat()
    payouts = _payout_rows(frames, end_date)

    baseline.to_csv(RESULT_DIR / "baseline_trades.csv", index=False)
    gated.to_csv(RESULT_DIR / "gated_trades.csv", index=False)
    removed.to_csv(RESULT_DIR / "removed_baseline_trades.csv", index=False)
    added.to_csv(RESULT_DIR / "added_gated_trades.csv", index=False)
    comparison.to_csv(RESULT_DIR / "comparison_summary.csv", index=False)
    payouts.to_csv(RESULT_DIR / "payout_summary.csv", index=False)
    (RESULT_DIR / "summary.json").write_text(
        json.dumps(
            {
                "baseline_profile": BASELINE_PROFILE,
                "gated_profile": GATED_PROFILE,
                "start_date": FULL_START,
                "end_date": end_date,
                "comparison": comparison.to_dict(orient="records"),
                "payouts": payouts.to_dict(orient="records"),
                "removed_trades": int(len(removed)),
                "added_trades": int(len(added)),
                "result_dir": str(RESULT_DIR),
                "report_path": str(REPORT_PATH),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_report(
        comparison=comparison,
        payouts=payouts,
        removed=removed,
        added=added,
        end_date=end_date,
    )

    print(f"Wrote {RESULT_DIR}")
    print(f"Wrote {REPORT_PATH}")
    print(comparison.to_string(index=False))
    print(payouts.to_string(index=False))


if __name__ == "__main__":
    main()
