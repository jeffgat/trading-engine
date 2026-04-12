#!/usr/bin/env python3
"""Focused 5m and 1m HTF-LSI lag follow-up."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import StrategyConfig
from orb_backtest.engine import simulator
from orb_backtest.optimize.walkforward import generate_windows
from orb_backtest.results.metrics import compute_metrics

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    RESULTS_ROOT,
    VALIDATION_START,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    save_json,
    slice_trades,
)

LAG_CURVE_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_lag_curve"
OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_5m_1m_followup"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_5M_1M_FOLLOWUP.md"

FIVE_MINUTE_WF_LAGS = [0, 20, 24, 30]
ONE_MINUTE_WF_LAGS = [0, 10, 15]
MINUTE_CAPS = [0, 5, 10, 15, 20, 30, 45, 60, 90, 120, 150]


def _load_rows(timeframe: str) -> list[dict]:
    path = LAG_CURVE_DIR / f"{timeframe}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing lag curve artifact: {path}")
    return json.loads(path.read_text())


def _row_by_lag(rows: list[dict], lag: int) -> dict:
    return next(row for row in rows if int(row["max_fvg_to_inversion_bars"]) == lag)


def _config_from_row(row: dict) -> StrategyConfig:
    return build_config(
        timeframe=row["timeframe"],
        direction_filter=row["direction_filter"],
        entry_mode=row["entry_mode"],
        entry_start=row["entry_start"],
        entry_end=row["entry_end"],
        rr=float(row["rr"]),
        tp1_ratio=float(row["tp1_ratio"]),
        min_gap_atr_pct=float(row["min_gap_atr_pct"]),
        atr_length=int(row["atr_length"]),
        htf_level_tf_minutes=int(row["htf_level_tf_minutes"]),
        htf_n_left=int(row["htf_n_left"]),
        htf_trade_max_per_session=int(row["htf_trade_max_per_session"]),
        lsi_fvg_window_left=int(row["lsi_fvg_window_left"]),
        lsi_fvg_window_right=int(row["lsi_fvg_window_right"]),
        max_fvg_to_inversion_bars=int(row["max_fvg_to_inversion_bars"]),
        entry_context_gate=row.get("entry_context_gate", ""),
        entry_context_min_atr=float(row.get("entry_context_min_atr", 0.0)),
        entry_context_max_atr=float(row.get("entry_context_max_atr", 0.0)),
        name=row["label"],
    )


def _metric_slice(trades, start: str, end: str) -> dict:
    return compute_metrics(slice_trades(trades, start, end))


def _run_fixed_walkforward(timeframe: str, rows_by_lag: dict[int, dict]) -> list[dict]:
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
    windows = generate_windows(DISCOVERY_START, HOLDOUT_START, is_months=36, oos_months=12, step_months=12)
    out = []
    for lag, row in rows_by_lag.items():
        cfg = _config_from_row(row)
        combined_oos = []
        folds = []
        for window in windows:
            trades = simulator.run_backtest(
                df_base,
                cfg,
                start_date=window.oos_start,
                end_date=window.oos_end,
                df_1m=df_1m,
                signal_df_1m=signal_df_1m,
                df_1s=df_1s,
            )
            oos = slice_trades(trades, window.oos_start, window.oos_end)
            metrics = compute_metrics(oos)
            combined_oos.extend(oos)
            folds.append(
                {
                    "oos_start": window.oos_start,
                    "oos_end": window.oos_end,
                    "trades": int(metrics["total_trades"]),
                    "avg_r": float(metrics["avg_r"]),
                    "pf": float(metrics["profit_factor"]),
                    "calmar": float(metrics["calmar_ratio"]),
                    "max_dd_r": float(metrics["max_drawdown_r"]),
                    "total_r": float(metrics["total_r"]),
                }
            )
        combined = compute_metrics(combined_oos)
        out.append(
            {
                "timeframe": timeframe,
                "lag": lag,
                "label": row["label"],
                "walkforward": {
                    "folds": folds,
                    "combined": {
                        "trades": int(combined["total_trades"]),
                        "avg_r": float(combined["avg_r"]),
                        "pf": float(combined["profit_factor"]),
                        "calmar": float(combined["calmar_ratio"]),
                        "max_dd_r": float(combined["max_drawdown_r"]),
                        "total_r": float(combined["total_r"]),
                    },
                },
            }
        )
    return out


def _minute_normalized_rows(rows: list[dict], timeframe_minutes: int) -> list[dict]:
    out = []
    for minute_cap in MINUTE_CAPS:
        if minute_cap == 0:
            lag = 0
        else:
            lag = minute_cap // timeframe_minutes
        row = _row_by_lag(rows, lag)
        out.append(
            {
                "minute_cap": minute_cap,
                "lag_bars": lag,
                "label": row["label"],
                "discovery_pf": row["discovery_pf"],
                "discovery_avg_r": row["discovery_avg_r"],
                "discovery_trades": row["discovery_trades"],
                "validation_pf": row["validation_pf"],
                "validation_avg_r": row["validation_avg_r"],
                "validation_calmar": row["validation_calmar"],
                "validation_trades": row["validation_trades"],
                "validation_trade_retention": row["validation_trade_retention"],
            }
        )
    return out


def _write_report(payload: dict) -> None:
    lines = [
        "# NQ NY HTF-LSI 5m / 1m Follow-Up",
        "",
        f"- Holdout remains untouched for these follow-up reads.",
        f"- Fixed walk-forward uses `36m IS / 12m OOS / 12m step` over `{DISCOVERY_START}` to `{HOLDOUT_START}`.",
        "",
        "## 5m Late-Lag Follow-Up",
        "",
        "| Lag | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["five_minute_followup"]:
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['lag']} | {row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{row['validation_trades']} | {wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | {wf['trades']} |"
        )

    lines.extend(
        [
            "",
            "## Minute-Normalized 5m vs 1m",
            "",
            "| Timeframe | Minute Cap | Lag Bars | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | Val Retention |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for timeframe in ("5m", "1m"):
        for row in payload["minute_normalized"][timeframe]:
            lines.append(
                f"| {timeframe} | {row['minute_cap']} | {row['lag_bars']} | "
                f"{row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
                f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | "
                f"{row['validation_calmar']:.3f} | {row['validation_trades']} | "
                f"{row['validation_trade_retention']:.3f} |"
            )

    lines.extend(
        [
            "",
            "## 1m Fixed-Candidate Follow-Up",
            "",
            "| Lag | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["one_minute_followup"]:
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['lag']} | {row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{row['validation_trades']} | {wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | {wf['trades']} |"
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    ensure_required_data()

    rows_5m = _load_rows("5m")
    rows_1m = _load_rows("1m")

    five_rows = {lag: _row_by_lag(rows_5m, lag) for lag in FIVE_MINUTE_WF_LAGS}
    one_rows = {lag: _row_by_lag(rows_1m, lag) for lag in ONE_MINUTE_WF_LAGS}

    print("Running fixed walk-forward for 5m follow-up candidates...", flush=True)
    five_wf = _run_fixed_walkforward("5m", five_rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(
        OUTPUT_DIR / "five_minute_partial.json",
        {
            "five_minute_followup": [
                {
                    "lag": lag,
                    "label": five_rows[lag]["label"],
                    "discovery_pf": five_rows[lag]["discovery_pf"],
                    "discovery_avg_r": five_rows[lag]["discovery_avg_r"],
                    "discovery_trades": five_rows[lag]["discovery_trades"],
                    "validation_pf": five_rows[lag]["validation_pf"],
                    "validation_avg_r": five_rows[lag]["validation_avg_r"],
                    "validation_calmar": five_rows[lag]["validation_calmar"],
                    "validation_trades": five_rows[lag]["validation_trades"],
                    "validation_trade_retention": five_rows[lag]["validation_trade_retention"],
                    "walkforward": next(row for row in five_wf if row["lag"] == lag)["walkforward"],
                }
                for lag in FIVE_MINUTE_WF_LAGS
            ]
        },
    )
    print("Running fixed walk-forward for 1m follow-up candidates...", flush=True)
    one_wf = _run_fixed_walkforward("1m", one_rows)

    five_lookup = {row["lag"]: row for row in five_wf}
    one_lookup = {row["lag"]: row for row in one_wf}

    five_payload = []
    for lag in FIVE_MINUTE_WF_LAGS:
        row = five_rows[lag]
        five_payload.append(
            {
                "lag": lag,
                "label": row["label"],
                "discovery_pf": row["discovery_pf"],
                "discovery_avg_r": row["discovery_avg_r"],
                "discovery_trades": row["discovery_trades"],
                "validation_pf": row["validation_pf"],
                "validation_avg_r": row["validation_avg_r"],
                "validation_calmar": row["validation_calmar"],
                "validation_trades": row["validation_trades"],
                "validation_trade_retention": row["validation_trade_retention"],
                "walkforward": five_lookup[lag]["walkforward"],
            }
        )

    one_payload = []
    for lag in ONE_MINUTE_WF_LAGS:
        row = one_rows[lag]
        one_payload.append(
            {
                "lag": lag,
                "label": row["label"],
                "discovery_pf": row["discovery_pf"],
                "discovery_avg_r": row["discovery_avg_r"],
                "discovery_trades": row["discovery_trades"],
                "validation_pf": row["validation_pf"],
                "validation_avg_r": row["validation_avg_r"],
                "validation_calmar": row["validation_calmar"],
                "validation_trades": row["validation_trades"],
                "validation_trade_retention": row["validation_trade_retention"],
                "walkforward": one_lookup[lag]["walkforward"],
            }
        )

    payload = {
        "five_minute_followup": five_payload,
        "one_minute_followup": one_payload,
        "minute_normalized": {
            "5m": _minute_normalized_rows(rows_5m, timeframe_minutes=5),
            "1m": _minute_normalized_rows(rows_1m, timeframe_minutes=1),
        },
    }

    save_json(OUTPUT_DIR / "followup.json", payload)
    _write_report(payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
