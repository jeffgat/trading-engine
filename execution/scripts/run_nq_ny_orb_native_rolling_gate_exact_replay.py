#!/usr/bin/env python3
"""Run the NQ NY ORB native rolling-gate profile through exact execution replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader.feed import ET  # noqa: E402
from trader.historical_backtest import (  # noqa: E402
    _read_parquet_frame,
    run_profile_backtest_sync,
    save_profile_backtest,
)
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402

PROFILE = "NQ_NY_ORB_NEUTRAL_ROLLING_GATE"
START_DATE = "2021-01-01"
END_DATE = "2024-12-31"
ARTIFACT_DIR = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / "nq_ny_orb_exec_native_rolling_gate_2021_20260609"
    / "artifacts"
)
RESEARCH_ARTIFACT = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / "nq_ny_orb_native_rolling_atr_gate_candidate_2021_20260608"
    / "artifacts"
    / "native_gate_candidate_results.json"
)


def _timestamp(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize(ET)
    return ts.tz_convert(ET)


def _pct(value: float) -> float:
    return round(value * 100.0, 2)


def _mfe_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    target_r = float(result["config"].get("nq_ny_rr", 2.0) or 2.0)

    for trade in result["trades"]:
        if not trade.get("entry_time") or not trade.get("exit_time"):
            continue
        risk_points = float(trade.get("risk_points") or 0.0)
        if risk_points <= 0.0:
            continue

        entry_ts = _timestamp(trade["entry_time"])
        exit_ts = _timestamp(trade["exit_time"])
        if exit_ts < entry_ts:
            continue

        frame = _read_parquet_frame(
            "NQ",
            "1s",
            start=entry_ts.to_pydatetime(),
            end=(exit_ts + pd.Timedelta(seconds=1)).to_pydatetime(),
        )
        if frame.empty:
            continue

        entry = float(trade["entry_price"])
        if trade.get("direction") == "short":
            favorable_points = max(0.0, entry - float(frame["low"].min()))
            mfe_time = frame["low"].idxmin()
        else:
            favorable_points = max(0.0, float(frame["high"].max()) - entry)
            mfe_time = frame["high"].idxmax()

        mfe_r = favorable_points / risk_points
        rows.append({
            "date": trade["date"],
            "session": trade["session"],
            "direction": trade["direction"],
            "entry_time": trade["entry_time"],
            "exit_time": trade["exit_time"],
            "exit_type": trade["exit_type"],
            "r_multiple": trade["r_multiple"],
            "risk_points": trade["risk_points"],
            "mfe_points": round(favorable_points, 4),
            "mfe_r": round(mfe_r, 6),
            "time_to_mfe_seconds": int((pd.Timestamp(mfe_time) - entry_ts).total_seconds()),
        })

    values = np.asarray([row["mfe_r"] for row in rows], dtype=float)
    if len(values) == 0:
        summary = {
            "timeframe": "1s",
            "trade_count": 0,
            "avg_mfe_r": 0.0,
            "p25_mfe_r": 0.0,
            "p50_mfe_r": 0.0,
            "p75_mfe_r": 0.0,
            "p90_mfe_r": 0.0,
            "mfe_ge_1r_pct": 0.0,
            "mfe_ge_2r_pct": 0.0,
            "mfe_ge_target_pct": 0.0,
            "realized_to_mfe_capture": 0.0,
        }
    else:
        total_mfe_r = float(np.sum(values))
        summary = {
            "timeframe": "1s",
            "trade_count": len(rows),
            "avg_mfe_r": round(float(np.mean(values)), 4),
            "p25_mfe_r": round(float(np.quantile(values, 0.25)), 4),
            "p50_mfe_r": round(float(np.quantile(values, 0.50)), 4),
            "p75_mfe_r": round(float(np.quantile(values, 0.75)), 4),
            "p90_mfe_r": round(float(np.quantile(values, 0.90)), 4),
            "mfe_ge_1r_pct": _pct(float(np.mean(values >= 1.0))),
            "mfe_ge_2r_pct": _pct(float(np.mean(values >= 2.0))),
            "mfe_ge_target_pct": _pct(float(np.mean(values >= target_r))),
            "realized_to_mfe_capture": round(
                float(result["summary"].get("total_r", 0.0)) / total_mfe_r,
                4,
            )
            if total_mfe_r > 0.0
            else 0.0,
        }

    return {"summary": summary, "trades": rows}


def _load_research_metrics() -> dict[str, Any]:
    if not RESEARCH_ARTIFACT.exists():
        return {}
    data = json.loads(RESEARCH_ARTIFACT.read_text())
    return dict(data.get("metrics") or {})


def _comparison(exact_summary: dict[str, Any], exact_mfe: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    if not research:
        return {}
    return {
        "research_total_trades": research.get("total_trades"),
        "exact_total_trades": exact_summary.get("total_trades"),
        "delta_total_trades": exact_summary.get("total_trades", 0) - research.get("total_trades", 0),
        "research_total_r": research.get("total_r"),
        "exact_total_r": exact_summary.get("total_r"),
        "delta_total_r": round(exact_summary.get("total_r", 0.0) - research.get("total_r", 0.0), 4),
        "research_profit_factor": research.get("profit_factor"),
        "exact_profit_factor": exact_summary.get("profit_factor"),
        "delta_profit_factor": round(exact_summary.get("profit_factor", 0.0) - research.get("profit_factor", 0.0), 4),
        "research_max_drawdown_r": research.get("max_drawdown_r"),
        "exact_max_drawdown_r": exact_summary.get("max_drawdown_r"),
        "delta_max_drawdown_r": round(
            exact_summary.get("max_drawdown_r", 0.0) - research.get("max_drawdown_r", 0.0),
            4,
        ),
        "research_mfe_p50_r": (research.get("mfe") or {}).get("p50_mfe_r"),
        "exact_mfe_p50_r": exact_mfe.get("p50_mfe_r"),
        "research_capture": research.get("realized_to_mfe_capture"),
        "exact_capture": exact_mfe.get("realized_to_mfe_capture"),
    }


def _fmt(value: Any, digits: int = 2) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    summary = payload["result"]["summary"]
    mfe = payload["mfe"]["summary"]
    comparison = payload.get("comparison") or {}
    config = payload["result"]["config"]
    years = summary.get("r_by_year", {})
    gate_bits = {
        key: value
        for key, value in config.items()
        if "rolling_atr" in key or "orb_range" in key or key.endswith("excluded_dow")
    }

    md = f"""# NQ NY ORB Exact Execution Replay: Native Rolling Gates

- Profile: `{PROFILE}`
- Window: `{START_DATE}` to `{END_DATE}`
- Holdout: `2025-01-01` onward remains untouched.
- Path: exact replay through live execution engines using local parquet data.
- Deployability: `live_native` for the ATR/ORB gates; profile is disabled in `exec_configs.json`.
- Context gates: `{gate_bits}`

## Exact Replay Metrics

| Trades | Gross R | Net R | PF | DD R | Calmar | Sharpe | MFE p50 | Capture | Years |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| {summary['total_trades']} | {_fmt(summary['total_r'])} | {_fmt(summary['total_net_r'])} | {_fmt(summary['profit_factor'])} | {_fmt(summary['max_drawdown_r'])} | {_fmt(summary['calmar_ratio'])} | {_fmt(summary['sharpe_ratio'])} | {_fmt(mfe['p50_mfe_r'])} | {_fmt(mfe['realized_to_mfe_capture'], 4)} | {years} |

## MFE Diagnostics

- Timeframe: `{mfe['timeframe']}`
- Avg / p25 / p50 / p75 / p90 MFE R: `{mfe['avg_mfe_r']}` / `{mfe['p25_mfe_r']}` / `{mfe['p50_mfe_r']}` / `{mfe['p75_mfe_r']}` / `{mfe['p90_mfe_r']}`
- MFE >= 1R / 2R / target: `{mfe['mfe_ge_1r_pct']}%` / `{mfe['mfe_ge_2r_pct']}%` / `{mfe['mfe_ge_target_pct']}%`

## Research Comparison

| Metric | Native research backtest | Exact execution replay | Delta |
|---|---:|---:|---:|
| Trades | {comparison.get('research_total_trades', '')} | {comparison.get('exact_total_trades', '')} | {comparison.get('delta_total_trades', '')} |
| Gross R | {_fmt(comparison.get('research_total_r', 0.0))} | {_fmt(comparison.get('exact_total_r', 0.0))} | {_fmt(comparison.get('delta_total_r', 0.0))} |
| PF | {_fmt(comparison.get('research_profit_factor', 0.0))} | {_fmt(comparison.get('exact_profit_factor', 0.0))} | {_fmt(comparison.get('delta_profit_factor', 0.0), 4)} |
| DD R | {_fmt(comparison.get('research_max_drawdown_r', 0.0))} | {_fmt(comparison.get('exact_max_drawdown_r', 0.0))} | {_fmt(comparison.get('delta_max_drawdown_r', 0.0))} |
| MFE p50 R | {_fmt(comparison.get('research_mfe_p50_r', 0.0))} | {_fmt(comparison.get('exact_mfe_p50_r', 0.0))} | |
| Capture | {_fmt(comparison.get('research_capture', 0.0), 4)} | {_fmt(comparison.get('exact_capture', 0.0), 4)} | |

## Notes

- Exact replay stays positive pre-holdout but is weaker than the native research backtest.
- 2022 has no trades under these gates in this pre-holdout replay.
- The gap is expected to come from live-engine exactness: 1s fills/exits, execution state handling, and commission-adjusted contract sizing versus the research simulator path.
"""
    path.write_text(md)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-remote", action="store_true", help="Also save the result to the shared run API.")
    args = parser.parse_args()

    config = load_config(DEFAULT_CONFIG)
    result = run_profile_backtest_sync(
        config=config,
        profile_name=PROFILE,
        start_date=START_DATE,
        end_date=END_DATE,
        label=f"EXEC EXACT {PROFILE} {START_DATE} to {END_DATE}",
    )
    mfe = _mfe_diagnostics(result)
    result["summary"]["mfe"] = mfe["summary"]
    result["summary"]["realized_to_mfe_capture"] = mfe["summary"]["realized_to_mfe_capture"]
    result["mfe_trades"] = mfe["trades"]

    research_metrics = _load_research_metrics()
    payload = {
        "profile": PROFILE,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "holdout_status": "2025-01-01 onward not loaded or tested",
        "result": result,
        "mfe": mfe,
        "research_metrics": research_metrics,
        "comparison": _comparison(result["summary"], mfe["summary"], research_metrics),
    }

    if args.save_remote:
        try:
            payload["remote_result_id"] = save_profile_backtest(result)
        except Exception as exc:  # noqa: BLE001
            payload["remote_save_error"] = str(exc)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = ARTIFACT_DIR / "exact_replay_results.json"
    md_path = ARTIFACT_DIR / "exact_replay_results.md"
    json_path.write_text(json.dumps(payload, indent=2))
    _write_markdown(payload, md_path)

    summary = result["summary"]
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    if payload.get("remote_result_id"):
        print(f"remote_result_id={payload['remote_result_id']}")
    if payload.get("remote_save_error"):
        print(f"remote_save_error={payload['remote_save_error']}")
    print(
        "summary: "
        f"trades={summary['total_trades']} "
        f"gross_r={summary['total_r']:.3f} "
        f"net_r={summary['total_net_r']:.3f} "
        f"pf={summary['profit_factor']:.3f} "
        f"dd_r={summary['max_drawdown_r']:.3f} "
        f"mfe_p50={mfe['summary']['p50_mfe_r']:.3f} "
        f"capture={mfe['summary']['realized_to_mfe_capture']:.4f}"
    )


if __name__ == "__main__":
    main()
