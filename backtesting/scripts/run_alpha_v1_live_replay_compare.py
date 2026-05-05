#!/usr/bin/env python3
"""Compare ALPHA_V1 research metrics with live-engine exact replay."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
for path in (EXEC_SRC,):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from trader.historical_backtest import _compute_summary, latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, LSI_SESSION_CONFIGS, SESSION_CONFIGS, load_config, load_exec_configs  # noqa: E402


PROFILE_NAME = "ALPHA_V1-A"
FULL_START = "2016-04-17"
END_DATE = "2026-03-24"
LAST_1Y_START = "2025-03-24"

RESULT_DIR = ROOT / "backtesting" / "data" / "results" / "alpha_v1_live_replay_compare_20260503"
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "ALPHA_V1_LIVE_REPLAY_COMPARE_20260503.md"
RESEARCH_LEG_METRICS = ROOT / "backtesting" / "data" / "results" / "alpha_v1_orb_reentry_promotion_20260502" / "per_leg_window_metrics.csv"
RESEARCH_PORTFOLIO_METRICS = ROOT / "backtesting" / "data" / "results" / "alpha_v1_orb_reentry_promotion_20260502" / "combined_window_metrics.csv"

SESSION_TO_LEG = {
    "NQ_NY_LSI": "nq_ny_htf_lsi",
    "NQ_Asia": "nq_asia_orb",
    "ES_Asia": "es_asia_orb",
    "ES_NY": "es_ny_orb",
}

LEG_LABELS = {
    "nq_ny_htf_lsi": "NQ NY HTF-LSI",
    "nq_asia_orb": "NQ Asia ORB",
    "es_asia_orb": "ES Asia ORB",
    "es_ny_orb": "ES NY ORB",
    "combined": "Combined ALPHA_V1",
}

WINDOWS = {
    "full": (FULL_START, END_DATE),
    "last_1y": (LAST_1Y_START, END_DATE),
}

DOC_ACTIVE_METRICS = {
    "nq_ny_htf_lsi": {"window": "Full History", "fills": 493, "net_r": 86.6, "win_rate_pct": 52.1, "profit_factor": 1.43, "max_dd": -10.0, "calmar": 8.63},
    "nq_asia_orb": {"window": "Full History", "fills": 753, "net_r": 212.0, "win_rate_pct": 45.2, "profit_factor": None, "max_dd": -10.2, "calmar": None},
    "es_asia_orb": {"window": "Full History", "fills": 1454, "net_r": 183.3, "win_rate_pct": 55.1, "profit_factor": 1.28, "max_dd": -12.5, "calmar": 14.68},
    "es_ny_orb": {"window": "Full History", "fills": 866, "net_r": 142.8, "win_rate_pct": 61.3, "profit_factor": 1.42, "max_dd": -10.4, "calmar": 13.74},
}

RESEARCH_CONFIGS = {
    "nq_ny_htf_lsi": {
        "session": "NQ_NY_LSI",
        "strategy": "htf_lsi",
        "entry_start": "08:30",
        "entry_end": "13:30",
        "sweep_start": "08:30",
        "sweep_end": "15:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "rr": 3.5,
        "tp1_ratio": 0.4,
        "atr_length": 14,
        "min_gap_atr_pct": 3.0,
        "fvg_window_left": 20,
        "fvg_window_right": 2,
        "max_fvg_to_inversion_bars": 24,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "htf_trade_max_per_session": 2,
        "lsi_entry_mode": "fvg_limit",
        "long_only": True,
        "excluded_dow": None,
    },
    "nq_asia_orb": {
        "session": "NQ_Asia",
        "strategy": "continuation",
        "orb_start": "20:00",
        "orb_end": "20:15",
        "entry_start": "20:15",
        "entry_end": "22:30",
        "flat_start": "04:00",
        "flat_end": "04:00",
        "stop_basis": "orb",
        "gap_filter_basis": "orb",
        "stop_orb_pct": 100.0,
        "min_gap_orb_pct": 10.0,
        "atr_length": 5,
        "rr": 6.0,
        "tp1_ratio": 0.3,
        "long_only": True,
        "excluded_dow": [1],
    },
    "es_asia_orb": {
        "session": "ES_Asia",
        "strategy": "continuation",
        "orb_start": "20:00",
        "orb_end": "20:15",
        "entry_start": "20:15",
        "entry_end": "03:00",
        "flat_start": "07:00",
        "flat_end": "07:00",
        "stop_basis": "orb",
        "gap_filter_basis": "atr",
        "stop_orb_pct": 125.0,
        "min_gap_atr_pct": 0.5,
        "atr_length": 14,
        "rr": 1.5,
        "tp1_ratio": 0.7,
        "min_stop_pts": 3.0,
        "min_tp1_pts": 3.0,
        "long_only": True,
        "excluded_dow": None,
    },
    "es_ny_orb": {
        "session": "ES_NY",
        "strategy": "continuation",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "13:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "stop_basis": "atr",
        "gap_filter_basis": "atr",
        "stop_atr_pct": 5.0,
        "min_gap_atr_pct": 0.25,
        "atr_length": 7,
        "rr": 5.0,
        "tp1_ratio": 0.2,
        "min_stop_pts": 3.0,
        "min_tp1_pts": 3.0,
        "long_only": True,
        "excluded_dow": [3],
    },
}

RESEARCH_RISK_REFERENCE_USD = {
    "nq_ny_htf_lsi": {
        "source": "ALPHA_V1 risk-sizing table / promotion packet",
        "risk_usd": 300,
    },
    "nq_asia_orb": {
        "source": "ALPHA_V1 risk-sizing table / promotion packet",
        "risk_usd": 300,
    },
    "es_asia_orb": {
        "source": "ALPHA_V1 risk-sizing table / promotion packet",
        "risk_usd": 200,
    },
    "es_ny_orb": {
        "source": "ALPHA_V1 risk-sizing table / promotion packet",
        "risk_usd": 300,
    },
}


def _slice_trades(trades: list[dict[str, Any]], start: str, end: str, leg: str | None = None) -> list[dict[str, Any]]:
    return [
        trade
        for trade in trades
        if start <= trade["date"] <= end
        and (leg is None or SESSION_TO_LEG.get(trade["session"]) == leg)
    ]


def _metric_value(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key)
    return float(value) if value is not None else 0.0


def _live_row(leg: str, window: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "leg": leg,
        "leg_label": LEG_LABELS[leg],
        "window": window,
        "fills": int(metrics.get("total_trades", 0)),
        "net_r": round(_metric_value(metrics, "total_r"), 2),
        "win_rate_pct": round(_metric_value(metrics, "win_rate") * 100.0, 2),
        "profit_factor": round(_metric_value(metrics, "profit_factor"), 3),
        "max_dd": round(_metric_value(metrics, "max_drawdown_r"), 2),
        "calmar": round(_metric_value(metrics, "calmar_ratio"), 3),
        "sharpe": round(_metric_value(metrics, "sharpe_ratio"), 3),
    }


def _read_research_rows() -> dict[tuple[str, str], dict[str, Any]]:
    research: dict[tuple[str, str], dict[str, Any]] = {}
    leg_df = pd.read_csv(RESEARCH_LEG_METRICS)
    for _, row in leg_df[(leg_df["profile"] == "baseline") & (leg_df["window"].isin(WINDOWS))].iterrows():
        leg = str(row["scope"])
        research[(leg, str(row["window"]))] = {
            "leg": leg,
            "leg_label": LEG_LABELS[leg],
            "window": str(row["window"]),
            "fills": int(row["fills"]),
            "net_r": round(float(row["net_r"]), 2),
            "win_rate_pct": round(float(row["win_rate_pct"]), 2),
            "profit_factor": round(float(row["profit_factor"]), 3),
            "max_dd": round(float(row["max_dd"]), 2),
            "calmar": round(float(row["calmar"]), 3),
            "sharpe": round(float(row["sharpe"]), 3),
        }

    portfolio_df = pd.read_csv(RESEARCH_PORTFOLIO_METRICS)
    for _, row in portfolio_df[(portfolio_df["profile"] == "baseline") & (portfolio_df["window"].isin(WINDOWS))].iterrows():
        leg = "combined"
        research[(leg, str(row["window"]))] = {
            "leg": leg,
            "leg_label": LEG_LABELS[leg],
            "window": str(row["window"]),
            "fills": int(row["fills"]),
            "net_r": round(float(row["net_r"]), 2),
            "win_rate_pct": round(float(row["win_rate_pct"]), 2),
            "profit_factor": round(float(row["profit_factor"]), 3),
            "max_dd": round(float(row["max_dd"]), 2),
            "calmar": round(float(row["calmar"]), 3),
            "sharpe": round(float(row["sharpe"]), 3),
        }
    return research


def _compare_rows(research: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    return {
        **live,
        "research_fills": research["fills"],
        "research_net_r": research["net_r"],
        "research_win_rate_pct": research["win_rate_pct"],
        "research_profit_factor": research["profit_factor"],
        "research_max_dd": research["max_dd"],
        "research_calmar": research["calmar"],
        "delta_fills": live["fills"] - research["fills"],
        "delta_net_r": round(live["net_r"] - research["net_r"], 2),
        "delta_pf": round(live["profit_factor"] - research["profit_factor"], 3),
        "delta_max_dd": round(live["max_dd"] - research["max_dd"], 2),
        "delta_calmar": round(live["calmar"] - research["calmar"], 3),
    }


def _merged_exec_configs(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    exec_configs = {cfg.name: cfg for cfg in load_exec_configs(config)}
    exec_config = exec_configs[PROFILE_NAME]
    by_leg: dict[str, dict[str, Any]] = {}
    for leg, research_config in RESEARCH_CONFIGS.items():
        session = str(research_config["session"])
        if leg == "nq_ny_htf_lsi":
            by_leg[leg] = {
                **LSI_SESSION_CONFIGS.get(session, {}),
                **exec_config.lsi_session_overrides.get(session, {}),
            }
        else:
            by_leg[leg] = {
                **SESSION_CONFIGS.get(session, {}),
                **exec_config.session_overrides.get(session, {}),
            }
    return by_leg


def _config_mismatches(config: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    exec_by_leg = _merged_exec_configs(config)
    for leg, research_config in RESEARCH_CONFIGS.items():
        exec_config = exec_by_leg.get(leg, {})
        for key, research_value in research_config.items():
            if key in {"session", "strategy"}:
                continue
            if key not in exec_config:
                continue
            live_value = exec_config[key]
            if live_value != research_value:
                mismatches.append({
                    "leg": leg,
                    "leg_label": LEG_LABELS[leg],
                    "key": key,
                    "research": research_value,
                    "execution": live_value,
                })
    return mismatches


def _risk_mismatches(config: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    exec_by_leg = _merged_exec_configs(config)
    for leg, risk_ref in RESEARCH_RISK_REFERENCE_USD.items():
        live_risk = exec_by_leg.get(leg, {}).get("risk_usd")
        if live_risk != risk_ref["risk_usd"]:
            mismatches.append({
                "leg": leg,
                "leg_label": LEG_LABELS[leg],
                "source": risk_ref["source"],
                "research_risk_usd": risk_ref["risk_usd"],
                "execution_risk_usd": live_risk,
            })
    return mismatches


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _write_report(payload: dict[str, Any]) -> None:
    lines = [
        "# ALPHA_V1 Research vs Live-Engine Exact Replay",
        "",
        f"- Profile replayed: `{PROFILE_NAME}` from `execution/config/exec_configs.json`.",
        f"- Exact replay path: `execution/src/trader/historical_backtest.py` via `run_profile_backtest_sync`.",
        f"- Full window: `{FULL_START}` to `{END_DATE}`.",
        f"- Last-1y hot window: `{LAST_1Y_START}` to `{END_DATE}`.",
        "- Research baseline source: `backtesting/data/results/alpha_v1_orb_reentry_promotion_20260502/*_window_metrics.csv`, which is linked from `backtesting/learnings/ALPHA_V1.md` as the active four-leg promotion packet baseline.",
        "- Note: exact replay exports filled trades only; research rows include signal/fill counts, so this report compares research fills to exact filled trades.",
        "",
        "## Side-by-Side",
        "",
        "| Window | Leg | Research fills | Exact fills | d fills | Research R | Exact R | d R | Research WR | Exact WR | Research PF | Exact PF | Research DD | Exact DD |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in payload["comparison_rows"]:
        lines.append(
            f"| {row['window']} | {row['leg_label']} | "
            f"{row['research_fills']} | {row['fills']} | {row['delta_fills']} | "
            f"{_fmt(row['research_net_r'])} | {_fmt(row['net_r'])} | {_fmt(row['delta_net_r'])} | "
            f"{_fmt(row['research_win_rate_pct'])}% | {_fmt(row['win_rate_pct'])}% | "
            f"{_fmt(row['research_profit_factor'], 3)} | {_fmt(row['profit_factor'], 3)} | "
            f"{_fmt(row['research_max_dd'])}R | {_fmt(row['max_dd'])}R |"
        )

    lines.extend([
        "",
        "## Config Parity",
        "",
    ])
    if payload["config_mismatches"]:
        lines.extend([
            "| Leg | Key | Research | Execution |",
            "| --- | --- | --- | --- |",
        ])
        for item in payload["config_mismatches"]:
            lines.append(
                f"| {item['leg_label']} | `{item['key']}` | `{item['research']}` | `{item['execution']}` |"
            )
    else:
        lines.append("No strategy-parameter mismatches were found for the compared keys.")

    lines.extend([
        "",
        "## Risk Sizing Drift",
        "",
    ])
    if payload["risk_mismatches"]:
        lines.extend([
            "| Leg | Research reference | Execution `ALPHA_V1-A` |",
            "| --- | ---: | ---: |",
        ])
        for item in payload["risk_mismatches"]:
            lines.append(
                f"| {item['leg_label']} | ${item['research_risk_usd']} | ${item['execution_risk_usd']} |"
            )
    else:
        lines.append("No risk-sizing drift was found against the ALPHA_V1 risk reference.")

    lines.extend([
        "",
        "R-level metrics are still compared, but contract sizing can matter if live portfolio caps bind.",
        "",
        "## Interpretation",
        "",
        "- Divergence is primarily live state-machine semantics and fill/order lifecycle: exact replay uses the production ORB/LSI engines, tick-order fills while armed/managing, real pending-order state, and portfolio contract caps.",
        "- No ALPHA_V1 active leg currently has an NQ-anchored regime gate in `ALPHA_V1-A`; the NQ daily-history caveat remains important for gated non-NQ profiles, but it was not a driver in this pass.",
        "- The current exact replay is a combined-profile replay, not separate-account isolation. That matches the available execution profile, but differs from the ALPHA portfolio thesis where legs are intended to run on separate funded accounts.",
        "- The live replay can therefore diverge from research even when the visible knobs match, especially around limit-order retests, TP/SL ordering, cancellations, flat handling, and any position-cap interaction.",
        "",
        "## ALPHA_V1 Active-Section Metric Drift",
        "",
        "The top active-leg tables in `ALPHA_V1.md` use mixed historical windows/vintages. The same-document promotion packet baseline over `2016-04-17` to `2026-03-24` is the research source used above. For awareness, the active-section full-history metrics differ from that packet for several legs:",
        "",
        "| Leg | Active-section fills/R | Packet baseline fills/R |",
        "| --- | ---: | ---: |",
    ])

    research_lookup = {
        (row["leg"], row["window"]): row
        for row in payload["research_rows"]
    }
    for leg, doc_row in DOC_ACTIVE_METRICS.items():
        packet = research_lookup.get((leg, "full"))
        if not packet:
            continue
        lines.append(
            f"| {LEG_LABELS[leg]} | {doc_row['fills']} / {_fmt(doc_row['net_r'])}R | "
            f"{packet['fills']} / {_fmt(packet['net_r'])}R |"
        )

    lines.extend([
        "",
        "## Artifacts",
        "",
        f"- JSON payload: `{payload['paths']['json']}`",
        f"- Exact trades CSV: `{payload['paths']['trades_csv']}`",
        f"- Metrics CSV: `{payload['paths']['metrics_csv']}`",
    ])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    common_end = latest_common_end(["NQ", "ES"])
    requested_end = datetime.fromisoformat(END_DATE)
    if common_end.date() < requested_end.date():
        raise RuntimeError(f"Common NQ/ES data ends at {common_end.date()}, before requested {END_DATE}")

    reuse_existing = "--reuse-existing" in sys.argv
    trades_path = RESULT_DIR / "exact_trades.csv"
    if reuse_existing and trades_path.exists():
        print(f"Reusing exact trades from {trades_path}...", flush=True)
        trades = pd.read_csv(trades_path).fillna("").to_dict("records")
        result = {"summary": _compute_summary(trades), "config": {}}
    else:
        print(f"Running exact replay for {PROFILE_NAME} {FULL_START} to {END_DATE}...", flush=True)
        result = run_profile_backtest_sync(
            config=config,
            profile_name=PROFILE_NAME,
            start_date=FULL_START,
            end_date=END_DATE,
            label=f"EXEC EXACT {PROFILE_NAME} ALPHA_V1 compare {FULL_START} to {END_DATE}",
        )
        trades = result["trades"]

    research = _read_research_rows()
    live_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []

    for window, (start, end) in WINDOWS.items():
        for leg in list(LEG_LABELS):
            leg_trades = _slice_trades(trades, start, end, None if leg == "combined" else leg)
            live = _live_row(leg, window, _compute_summary(leg_trades))
            live_rows.append(live)
            research_row = research.get((leg, window))
            if research_row is not None:
                comparison_rows.append(_compare_rows(research_row, live))

    payload = {
        "info": {
            "profile_name": PROFILE_NAME,
            "full_start": FULL_START,
            "last_1y_start": LAST_1Y_START,
            "end_date": END_DATE,
            "latest_common_end": common_end.isoformat(),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "research_source": {
            "leg_metrics": str(RESEARCH_LEG_METRICS),
            "portfolio_metrics": str(RESEARCH_PORTFOLIO_METRICS),
        },
        "research_configs": RESEARCH_CONFIGS,
        "config_mismatches": _config_mismatches(config),
        "risk_mismatches": _risk_mismatches(config),
        "research_rows": list(research.values()),
        "live_rows": live_rows,
        "comparison_rows": comparison_rows,
        "exact_summary": result["summary"],
        "paths": {
            "json": str(RESULT_DIR / "alpha_v1_live_replay_compare.json"),
            "trades_csv": str(RESULT_DIR / "exact_trades.csv"),
            "metrics_csv": str(RESULT_DIR / "comparison_metrics.csv"),
            "report": str(REPORT_PATH),
        },
    }

    pd.DataFrame(trades).to_csv(trades_path, index=False)
    _write_csv(RESULT_DIR / "comparison_metrics.csv", comparison_rows)
    (RESULT_DIR / "alpha_v1_live_replay_compare.json").write_text(json.dumps(payload, indent=2, default=str))
    _write_report(payload)

    print(json.dumps({
        "comparison_rows": comparison_rows,
        "config_mismatches": payload["config_mismatches"],
        "risk_mismatches": payload["risk_mismatches"],
    }, indent=2, default=str))
    print(f"Saved result directory: {RESULT_DIR}")
    print(f"Saved report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
