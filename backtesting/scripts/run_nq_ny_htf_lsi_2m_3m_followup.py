#!/usr/bin/env python3
"""Focused stitched-OOS follow-up for 2m and 3m HTF-LSI branches."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.optimize.walkforward import generate_windows
from orb_backtest.results.metrics import compute_metrics

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    RESULTS_ROOT,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    save_json,
    slice_trades,
)

LAG_CURVE_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_lag_curve"
OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_2m_3m_followup"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_2M_3M_FOLLOWUP.md"

# 2m: compare the honest lag0 baseline with the best validation row in the
# late-lag recovery zone that still keeps a meaningful sample.
# 3m: compare the honest lag0 baseline with the best validation row in the
# 25-30 bar recovery plateau.
CANDIDATE_LAGS = {
    "2m": (0, 26),
    "3m": (0, 30),
}


def _load_rows(timeframe: str, lags: tuple[int, ...]) -> dict[int, dict]:
    path = LAG_CURVE_DIR / f"{timeframe}.json"
    rows = json.loads(path.read_text())
    return {lag: next(row for row in rows if row["max_fvg_to_inversion_bars"] == lag) for lag in lags}


def _config_from_row(row: dict):
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


def _stitched_oos_payload(trades) -> dict:
    windows = generate_windows(DISCOVERY_START, HOLDOUT_START, is_months=36, oos_months=12, step_months=12)
    combined = []
    folds = []
    for window in windows:
        oos = slice_trades(trades, window.oos_start, window.oos_end)
        metrics = compute_metrics(oos)
        combined.extend(oos)
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
    combined_metrics = compute_metrics(combined)
    return {
        "folds": folds,
        "combined": {
            "trades": int(combined_metrics["total_trades"]),
            "avg_r": float(combined_metrics["avg_r"]),
            "pf": float(combined_metrics["profit_factor"]),
            "calmar": float(combined_metrics["calmar_ratio"]),
            "max_dd_r": float(combined_metrics["max_drawdown_r"]),
            "total_r": float(combined_metrics["total_r"]),
        },
    }


def _write_report(payload: dict[str, list[dict]]) -> None:
    lines = [
        "# NQ NY HTF-LSI 2m / 3m Follow-Up",
        "",
        "- Focused stitched OOS comparison for the honest `lag=0` baseline versus the strongest plausible late-lag challenger in each timeframe.",
        f"- OOS windows: `36m IS / 12m OOS / 12m step` from `{DISCOVERY_START}` to `{HOLDOUT_START}`.",
        "",
    ]
    for timeframe in ("2m", "3m"):
        lines.extend(
            [
                f"## {timeframe}",
                "",
                "| Lag | Validation PF | Validation Avg R | Validation Calmar | Validation Trades | Val Retention | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
                "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in payload[timeframe]:
            wf = row["walkforward"]["combined"]
            lines.append(
                f"| {row['lag']} | {row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | "
                f"{row['validation_calmar']:.3f} | {row['validation_trades']} | {row['validation_trade_retention']:.3f} | "
                f"{wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | {wf['trades']} | {wf['max_dd_r']:.2f} |"
            )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    ensure_required_data()
    summary: dict[str, list[dict]] = {}

    for timeframe, lags in CANDIDATE_LAGS.items():
        row_map = _load_rows(timeframe, lags)
        configs = [_config_from_row(row_map[lag]) for lag in lags]

        print(f"Running {timeframe} follow-up candidates...", flush=True)
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
        results = run_sweep(
            df_base,
            configs,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )

        payload = []
        for cfg, trades in results:
            lag = int(cfg.max_fvg_to_inversion_bars)
            row = row_map[lag]
            payload.append(
                {
                    "timeframe": timeframe,
                    "lag": lag,
                    "label": row["label"],
                    "direction_filter": row["direction_filter"],
                    "entry_mode": row["entry_mode"],
                    "trade_cap": row["htf_trade_max_per_session"],
                    "validation_pf": row["validation_pf"],
                    "validation_avg_r": row["validation_avg_r"],
                    "validation_calmar": row["validation_calmar"],
                    "validation_trades": row["validation_trades"],
                    "validation_trade_retention": row["validation_trade_retention"],
                    "discovery_pf": row["discovery_pf"],
                    "discovery_avg_r": row["discovery_avg_r"],
                    "discovery_trades": row["discovery_trades"],
                    "walkforward": _stitched_oos_payload(trades),
                }
            )
        payload.sort(key=lambda row: row["lag"])
        summary[timeframe] = payload
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        save_json(OUTPUT_DIR / f"{timeframe}.json", payload)

    save_json(OUTPUT_DIR / "summary.json", summary)
    _write_report(summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
