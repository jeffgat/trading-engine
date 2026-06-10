#!/usr/bin/env python3
"""Run the accepted NQ NY ORB native rolling-gate profile on 2025 holdout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (EXEC_SRC, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_nq_ny_orb_native_rolling_gate_exact_replay import (  # noqa: E402
    PROFILE,
    _fmt,
    _mfe_diagnostics,
)
from trader.historical_backtest import run_profile_backtest_sync, save_profile_backtest  # noqa: E402
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402

START_DATE = "2025-01-01"
END_DATE = "2025-12-31"
RUN_ID = "nq_ny_orb_exec_native_rolling_gate_2025_holdout_20260609"
ARTIFACT_DIR = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / RUN_ID
    / "artifacts"
)


def _r_by_month(trades: list[dict[str, Any]]) -> dict[str, float]:
    monthly: dict[str, float] = {}
    for trade in trades:
        month = str(trade.get("date", ""))[:7]
        if not month:
            continue
        monthly[month] = monthly.get(month, 0.0) + float(trade.get("r_multiple") or 0.0)
    return {month: round(value, 3) for month, value in sorted(monthly.items())}


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    summary = payload["result"]["summary"]
    mfe = payload["mfe"]["summary"]
    config = payload["result"]["config"]
    gate_bits = {
        key: value
        for key, value in config.items()
        if "rolling_atr" in key or "orb_range" in key or key.endswith("excluded_dow")
    }
    exit_breakdown = summary.get("exit_breakdown", {})
    monthly_r = payload.get("monthly_r") or {}
    years = summary.get("r_by_year", {})

    md = f"""# NQ NY ORB 2025 Holdout: Native Rolling Gates

- Profile: `{PROFILE}`
- Window: `{START_DATE}` to `{END_DATE}`
- Holdout opened: `2026-06-09`, after the pre-holdout exact/research ordering audit accepted exact replay as the operational baseline.
- Path: exact replay through live execution engines using local parquet data.
- Deployability: `live_native` for the ATR/ORB gates; profile is disabled in `exec_configs.json`.
- Context gates: `{gate_bits}`

## Holdout Metrics

| Trades | Gross R | Net R | PF | DD R | Calmar | Sharpe | Win Rate | MFE p50 | Capture | Years |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| {summary['total_trades']} | {_fmt(summary['total_r'])} | {_fmt(summary['total_net_r'])} | {_fmt(summary['profit_factor'])} | {_fmt(summary['max_drawdown_r'])} | {_fmt(summary['calmar_ratio'])} | {_fmt(summary['sharpe_ratio'])} | {_fmt(summary['win_rate'])} | {_fmt(mfe['p50_mfe_r'])} | {_fmt(mfe['realized_to_mfe_capture'], 4)} | {years} |

## MFE Diagnostics

- Timeframe: `{mfe['timeframe']}`
- Avg / p25 / p50 / p75 / p90 MFE R: `{mfe['avg_mfe_r']}` / `{mfe['p25_mfe_r']}` / `{mfe['p50_mfe_r']}` / `{mfe['p75_mfe_r']}` / `{mfe['p90_mfe_r']}`
- MFE >= 1R / 2R / target: `{mfe['mfe_ge_1r_pct']}%` / `{mfe['mfe_ge_2r_pct']}%` / `{mfe['mfe_ge_target_pct']}%`

## Breakdown

- Exit breakdown: `{exit_breakdown}`
- Monthly R: `{monthly_r}`
- Monthly USD PnL: `{summary.get('pnl_by_month', {})}`

## Interpretation Placeholder

- This artifact is the first opened 2025 holdout read for this candidate.
- Interpret against the accepted pre-holdout exact baseline: 151 trades, +31.74 gross R, PF 1.31, DD -10.03R.
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
        label=f"EXEC EXACT HOLDOUT {PROFILE} {START_DATE} to {END_DATE}",
    )
    mfe = _mfe_diagnostics(result)
    result["summary"]["mfe"] = mfe["summary"]
    result["summary"]["realized_to_mfe_capture"] = mfe["summary"]["realized_to_mfe_capture"]
    result["mfe_trades"] = mfe["trades"]

    payload = {
        "profile": PROFILE,
        "run_id": RUN_ID,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "holdout_status": "opened_once_on_2026-06-09_after_exact_baseline_acceptance",
        "result": result,
        "mfe": mfe,
        "monthly_r": _r_by_month(result["trades"]),
        "pre_holdout_reference": {
            "window": "2021-01-01 to 2024-12-31",
            "trades": 151,
            "gross_r": 31.743,
            "net_r": 27.413,
            "profit_factor": 1.312034434,
            "max_drawdown_r": -10.026,
        },
    }

    if args.save_remote:
        try:
            payload["remote_result_id"] = save_profile_backtest(result)
        except Exception as exc:  # noqa: BLE001
            payload["remote_save_error"] = str(exc)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = ARTIFACT_DIR / "holdout_results.json"
    md_path = ARTIFACT_DIR / "holdout_results.md"
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
