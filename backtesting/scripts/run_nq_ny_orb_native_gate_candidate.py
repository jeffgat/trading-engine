#!/usr/bin/env python3
"""Native pre-trade gate rerun for the selected NQ NY ORB candidate.

Runs the exact pre-holdout candidate selected by
``run_nq_ny_orb_neutral_gate_workflow.py`` using first-class StrategyConfig
session fields instead of post-backtest research filters.

Window: 2021-2024 only. 2025+ holdout is intentionally not loaded or tested.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import default_config, with_overrides  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data  # noqa: E402
from orb_backtest.discovery.tools import _mfe_diagnostics  # noqa: E402
from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NO_FILL,
    TradeResult,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.validate.deflated_sharpe import compute_dsr, compute_psr  # noqa: E402


RUN_ID = "nq_ny_orb_native_rolling_atr_gate_candidate_2021_20260608"
SOURCE_RUN_ID = "nq_ny_orb_neutral_gate_workflow_2021_20260608"
RESULT_DIR = ROOT / "data" / "results" / "discovery_runs" / RUN_ID
ARTIFACT_DIR = RESULT_DIR / "artifacts"
DATA_FILE = ROOT / "data" / "cache" / "nq_ny_lsi_cisd_sequence" / "NQ_5m.parquet"

LOAD_START = "2016-01-01"
DISCOVERY_START = "2021-01-01"
DISCOVERY_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"

MAX_PRIOR_ROLLING_ATR_PCT = 1.6228084238855573
MAX_ORB_RANGE_PCT = 0.4657663656763981
N_TRIALS_RAW = 26
N_TRIALS_EFFECTIVE = 8


def _config():
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        risk_usd=5000.0,
        rr=2.0,
        tp1_ratio=1.0,
        exit_mode="single_target",
        continuation_fvg_selection="first",
        orb_trade_max_per_session=1,
        impulse_close_filter=False,
        use_bar_magnifier=True,
        strategy="continuation",
        direction_filter="long",
        ny_orb_start="09:30",
        ny_orb_end="09:45",
        ny_entry_start="09:45",
        ny_entry_end="13:00",
        ny_flat_start="15:50",
        ny_flat_end="16:00",
        ny_stop_atr_pct=10.0,
        ny_min_gap_atr_pct=2.0,
        ny_max_prior_rolling_atr_pct=MAX_PRIOR_ROLLING_ATR_PCT,
        ny_max_orb_range_pct=MAX_ORB_RANGE_PCT,
        name=RUN_ID,
    )


def _r_multiples(trades: list[TradeResult]) -> np.ndarray:
    return np.asarray(
        [
            float(getattr(trade, "net_r_multiple", 0.0) or trade.r_multiple)
            for trade in trades
            if trade.exit_type != EXIT_NO_FILL
        ],
        dtype=float,
    )


def _capture(mfe_trades: list[dict[str, Any]]) -> float:
    mfe_sum = sum(float(row["mfe_r"]) for row in mfe_trades)
    if mfe_sum <= 0:
        return 0.0
    return sum(float(row["realized_r"]) for row in mfe_trades) / mfe_sum


def _metrics_payload(trades: list[TradeResult], config: Any, mfe_df: Any) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    mfe = _mfe_diagnostics(trades, mfe_df, config)
    r_values = _r_multiples(trades)
    psr = compute_psr(r_values)
    dsr = compute_dsr(r_values, n_trials_raw=N_TRIALS_RAW, n_trials_effective=N_TRIALS_EFFECTIVE)
    r_by_year = {
        str(year): round(float(metrics.get("r_by_year", {}).get(str(year), 0.0)), 4)
        for year in range(2021, 2025)
    }
    return {
        "total_trades": int(metrics.get("total_trades", 0)),
        "total_r": round(float(metrics.get("total_r", 0.0)), 4),
        "avg_r": round(float(metrics.get("avg_r", 0.0)), 4),
        "win_rate_pct": round(float(metrics.get("win_rate", 0.0)) * 100.0, 2),
        "profit_factor": round(float(metrics.get("profit_factor", 0.0)), 4),
        "max_drawdown_r": round(float(metrics.get("max_drawdown_r", 0.0)), 4),
        "calmar": round(float(metrics.get("calmar_ratio", 0.0)), 4),
        "sharpe": round(float(metrics.get("sharpe_ratio", 0.0)), 4),
        "r_by_year": r_by_year,
        "mfe": mfe["summary"],
        "realized_to_mfe_capture": round(_capture(mfe["trades"]), 4),
        "exit_breakdown": metrics.get("exit_breakdown", {}),
        "psr": psr.psr,
        "dsr": dsr.dsr,
        "observed_sharpe_psr": psr.observed_sharpe,
        "n_trials_raw": N_TRIALS_RAW,
        "n_trials_effective": N_TRIALS_EFFECTIVE,
    }


def _previous_selected() -> dict[str, Any] | None:
    path = (
        ROOT
        / "data"
        / "results"
        / "discovery_runs"
        / SOURCE_RUN_ID
        / "artifacts"
        / "gate_workflow_results.json"
    )
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return payload.get("selected_candidate")


def _metric_deltas(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if previous is None:
        return {}
    keys = [
        "total_trades",
        "total_r",
        "profit_factor",
        "max_drawdown_r",
        "calmar",
        "psr",
        "dsr",
        "realized_to_mfe_capture",
    ]
    deltas: dict[str, Any] = {}
    for key in keys:
        if key in current and key in previous:
            deltas[key] = round(float(current[key]) - float(previous[key]), 6)
    return deltas


def _render_markdown(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    prev = payload.get("previous_research_filter_metrics") or {}
    delta = payload.get("metric_deltas_vs_previous_research_filter") or {}
    years = ", ".join(f"{year}:{value:+.1f}" for year, value in m["r_by_year"].items())
    lines = [
        f"# NQ NY ORB Native Gate Candidate: {RUN_ID}",
        "",
        f"- Window: `{DISCOVERY_START}` to `{DISCOVERY_END}`",
        f"- Frozen holdout starts: `{HOLDOUT_START}`; 2025+ was not loaded or tested.",
        "- Candidate: `long__low_or_mid_atr__small_or_mid_orb`",
        "- Native gates: "
        f"`ny_max_prior_rolling_atr_pct={MAX_PRIOR_ROLLING_ATR_PCT:.4f}`, "
        f"`ny_max_orb_range_pct={MAX_ORB_RANGE_PCT:.4f}`",
        "- Anchor: `1:2R`, single target, NY 09:30-09:45 ORB, first 5m continuation FVG, 10% ATR stop, 2% ATR gap.",
        "- Signal path: cached native StrategyConfig fields, not post-backtest trade filtering.",
        "",
        "## Metrics",
        "",
        "| Trades | R | PF | DD R | Calmar | PSR | DSR | MFE p50 | Capture | Years |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        (
            f"| {m['total_trades']} | {m['total_r']:.2f} | {m['profit_factor']:.2f} | "
            f"{m['max_drawdown_r']:.2f} | {m['calmar']:.2f} | {m['psr']:.4f} | "
            f"{m['dsr']:.4f} | {m['mfe']['p50_mfe_r']:.2f} | "
            f"{m['realized_to_mfe_capture']:.2f} | {years} |"
        ),
        "",
        "## Comparison To Prior Research Filter",
        "",
    ]
    if not prev:
        lines.append("- Previous artifact was not found, so no delta was computed.")
    else:
        lines.extend(
            [
                f"- Prior research-filter trades/R/PF/DD: `{prev['total_trades']}` / `{prev['total_r']:.2f}` / `{prev['profit_factor']:.2f}` / `{prev['max_drawdown_r']:.2f}`",
                f"- Delta trades/R/PF/DD: `{delta.get('total_trades', 0):+.0f}` / `{delta.get('total_r', 0.0):+.2f}` / `{delta.get('profit_factor', 0.0):+.4f}` / `{delta.get('max_drawdown_r', 0.0):+.2f}`",
                "- Note: native rolling ATR gating mirrors the original research filter's simple rolling daily true-range ATR%.",
            ]
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- This remains pre-holdout candidate verification, not final deployment approval.",
            "- 2025 holdout should stay sealed until the native-gate candidate is frozen.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_5m_data(str(DATA_FILE), start=LOAD_START, end=DISCOVERY_END)
    try:
        df_1m = load_1m_for_5m(str(DATA_FILE), start=LOAD_START, end=DISCOVERY_END)
    except FileNotFoundError:
        df_1m = None

    config = _config()
    cache = build_signal_cache(df, [config], signal_df_1m=df_1m)
    trades = run_backtest(
        df,
        config,
        start_date=DISCOVERY_START,
        end_date=DISCOVERY_END,
        df_1m=df_1m,
        signal_df_1m=df_1m,
        _signal_cache=cache,
    )
    metrics = _metrics_payload(trades, config, df_1m if df_1m is not None else df)
    previous = _previous_selected()
    payload = {
        "run_id": RUN_ID,
        "source_run_id": SOURCE_RUN_ID,
        "data": {
            "data_file": str(DATA_FILE),
            "load_start": LOAD_START,
            "discovery_start": DISCOVERY_START,
            "discovery_end": DISCOVERY_END,
            "holdout_start": HOLDOUT_START,
            "loaded_1m": df_1m is not None,
        },
        "candidate": {
            "rule_id": "long__low_or_mid_atr__small_or_mid_orb",
            "deployability": "research_engine_native",
            "strategy": "continuation",
            "direction_filter": "long",
            "rr": 2.0,
            "exit_mode": "single_target",
            "ny_orb_window": "09:30-09:45",
            "ny_entry_window": "09:45-13:00",
            "ny_flat_window": "15:50-16:00",
            "ny_stop_atr_pct": 10.0,
            "ny_min_gap_atr_pct": 2.0,
            "ny_max_prior_rolling_atr_pct": MAX_PRIOR_ROLLING_ATR_PCT,
            "ny_max_orb_range_pct": MAX_ORB_RANGE_PCT,
        },
        "metrics": metrics,
        "previous_research_filter_metrics": previous,
        "metric_deltas_vs_previous_research_filter": _metric_deltas(metrics, previous),
    }

    json_path = ARTIFACT_DIR / "native_gate_candidate_results.json"
    md_path = ARTIFACT_DIR / "native_gate_candidate_results.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n")
    md_path.write_text(_render_markdown(payload) + "\n")
    print(
        json.dumps(
            {
                "success": True,
                "json": str(json_path),
                "markdown": str(md_path),
                "trades": metrics["total_trades"],
                "total_r": metrics["total_r"],
                "profit_factor": metrics["profit_factor"],
                "max_drawdown_r": metrics["max_drawdown_r"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
