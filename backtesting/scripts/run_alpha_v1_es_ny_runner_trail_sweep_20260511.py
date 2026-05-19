#!/usr/bin/env python3
"""Runner-trailing exit sweep for the ALPHA_V1 ES NY ORB leg.

Research artifact only. This does not edit live execution configs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "alpha_v1_es_ny_runner_trail_sweep_20260511"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ES_NY_RUNNER_TRAIL_SWEEP_20260511.md"

DEFAULT_START = "2016-04-17"
DEFAULT_END = "2026-03-25"  # exclusive, keeps the ALPHA_V1 common end date through 2026-03-24

WINDOWS = {
    "full": ("2016-04-17", "2026-03-25"),
    "last_2y": ("2024-03-24", "2026-03-25"),
    "last_1y": ("2025-03-24", "2026-03-25"),
    "holdout_2025p": ("2025-01-01", "2026-03-25"),
}


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _round(value: Any, digits: int = 3) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _fmt(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def build_es_ny_config() -> StrategyConfig:
    return StrategyConfig(
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:45",
                entry_start="09:45",
                entry_end="13:00",
                flat_start="15:50",
                flat_end="16:00",
                stop_atr_pct=5.0,
                min_gap_atr_pct=0.25,
                min_stop_points=3.0,
                min_tp1_points=3.0,
            ),
        ),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=5.0,
        tp1_ratio=0.2,
        atr_length=7,
        excluded_days=(3,),
        impulse_close_filter=False,
        name="ALPHA_V1 ES NY ORB baseline",
        notes="Baseline ES_NY ORB leg from backtesting/learnings/ALPHA_V1.md",
    )


def build_variants(base: StrategyConfig) -> list[StrategyConfig]:
    variants: list[tuple[str, dict[str, Any]]] = [
        ("baseline", {}),
        ("step_2r_lock_1r", {
            "runner_trail_mode": "step_r",
            "runner_trail_trigger_r": 2.0,
            "runner_trail_stop_r": 1.0,
            "runner_trail_step_r": 1.0,
        }),
        ("step_2p5r_lock_1r", {
            "runner_trail_mode": "step_r",
            "runner_trail_trigger_r": 2.5,
            "runner_trail_stop_r": 1.0,
            "runner_trail_step_r": 1.0,
        }),
        ("step_3r_lock_1r", {
            "runner_trail_mode": "step_r",
            "runner_trail_trigger_r": 3.0,
            "runner_trail_stop_r": 1.0,
            "runner_trail_step_r": 1.0,
        }),
        ("step_3r_lock_1p5r", {
            "runner_trail_mode": "step_r",
            "runner_trail_trigger_r": 3.0,
            "runner_trail_stop_r": 1.5,
            "runner_trail_step_r": 1.0,
        }),
        ("step_4r_lock_2r", {
            "runner_trail_mode": "step_r",
            "runner_trail_trigger_r": 4.0,
            "runner_trail_stop_r": 2.0,
            "runner_trail_step_r": 1.0,
        }),
    ]

    for gap_r in (0.75, 1.0, 1.25, 1.5, 2.0, 2.5):
        variants.append((
            f"risk_gap_{_fmt(gap_r)}r",
            {
                "runner_trail_mode": "risk",
                "runner_trail_gap_r": gap_r,
            },
        ))

    for atr_pct in (5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0):
        variants.append((
            f"atr_gap_{_fmt(atr_pct)}pct",
            {
                "runner_trail_mode": "atr",
                "runner_trail_atr_pct": atr_pct,
            },
        ))

    configs = []
    for variant_id, overrides in variants:
        configs.append(
            replace(
                base,
                name=f"ALPHA_V1 ES NY runner trail {variant_id}",
                notes="ES_NY ORB runner-trailing research sweep; research-only until execution support is added.",
                **overrides,
            )
        )
    return configs


def _filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date < end]


def _tp1_be_stats(trades: list[TradeResult]) -> dict[str, Any]:
    filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    tp1_be = [trade for trade in filled if EXIT_NAMES.get(trade.exit_type) == "tp1_be"]
    positive_tp1_be = [trade for trade in tp1_be if trade.r_multiple > 0.5001]
    return {
        "tp1_be_count": len(tp1_be),
        "tp1_be_avg_r": _round(np.mean([trade.r_multiple for trade in tp1_be]), 4) if tp1_be else 0.0,
        "positive_runner_stop_count": len(positive_tp1_be),
        "positive_runner_stop_avg_r": _round(np.mean([trade.r_multiple for trade in positive_tp1_be]), 4)
        if positive_tp1_be else 0.0,
    }


def summarize_variant(config: StrategyConfig, trades: list[TradeResult], variant_id: str) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    row: dict[str, Any] = {
        "variant_id": variant_id,
        "trail_mode": config.runner_trail_mode or "none",
        "trail_trigger_r": config.runner_trail_trigger_r,
        "trail_stop_r": config.runner_trail_stop_r,
        "trail_step_r": config.runner_trail_step_r,
        "trail_gap_r": config.runner_trail_gap_r,
        "trail_atr_pct": config.runner_trail_atr_pct,
        "deployability": "research_only" if config.runner_trail_mode else "live_native",
        "live_support_notes": (
            "Current ALPHA_V1 ES_NY ORB baseline."
            if not config.runner_trail_mode
            else "Runner trailing is supported in the research backtester only; exact execution support is required before deployment."
        ),
        "exact_replay_required": "yes_before_live_change",
        "trades": metrics["total_trades"],
        "win_rate": _round(metrics["win_rate"], 4),
        "total_r": _round(metrics["total_r"], 2),
        "avg_r": _round(metrics["avg_r"], 4),
        "profit_factor": _round(metrics["profit_factor"], 3),
        "sharpe": _round(metrics["sharpe_ratio"], 3),
        "max_dd_r": _round(metrics["max_drawdown_r"], 2),
        "calmar": _round(metrics["calmar_ratio"], 3),
        "exit_breakdown": metrics["exit_breakdown"],
    }
    row.update(_tp1_be_stats(trades))

    for window_name, (start, end) in WINDOWS.items():
        window_trades = _filter_window(trades, start, end)
        wm = compute_metrics(window_trades)
        row[f"{window_name}_trades"] = wm["total_trades"]
        row[f"{window_name}_total_r"] = _round(wm["total_r"], 2)
        row[f"{window_name}_max_dd_r"] = _round(wm["max_drawdown_r"], 2)
        row[f"{window_name}_calmar"] = _round(wm["calmar_ratio"], 3)
        row[f"{window_name}_profit_factor"] = _round(wm["profit_factor"], 3)
    return row


def _variant_id(config: StrategyConfig) -> str:
    return config.name.replace("ALPHA_V1 ES NY runner trail ", "")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row[key], sort_keys=True) if isinstance(row[key], dict) else row[key] for key in keys})


def _report(rows: list[dict[str, Any]], elapsed: float, use_1s: bool, start: str, end: str) -> str:
    ranked = sorted(rows, key=lambda row: (row["calmar"] or -999, row["total_r"] or -999), reverse=True)
    recent_ranked = sorted(rows, key=lambda row: (row["last_2y_calmar"] or -999, row["last_2y_total_r"] or -999), reverse=True)
    baseline = next(row for row in rows if row["variant_id"] == "baseline")

    def table_line(row: dict[str, Any]) -> str:
        return (
            f"| `{row['variant_id']}` | {row['trail_mode']} | {row['trades']} | "
            f"{row['total_r']:+.2f} | {row['max_dd_r']:.2f} | {row['calmar']:.3f} | "
            f"{row['profit_factor']:.3f} | {row['last_2y_total_r']:+.2f} | {row['last_2y_calmar']:.3f} | "
            f"{row['holdout_2025p_total_r']:+.2f} | {row['holdout_2025p_max_dd_r']:.2f} | "
            f"{row['positive_runner_stop_count']} | {row['deployability']} |"
        )

    lines = [
        "# ALPHA_V1 ES NY Runner-Trail Sweep",
        "",
        f"- Scope: active `ALPHA_V1` ES NY ORB leg, `rr=5.0`, `tp1_ratio=0.2`, long only.",
        f"- Date window: `{start}` through `{end}` exclusive.",
        f"- Magnifier: `5m -> 1m`{' -> 1s' if use_1s else ''}.",
        f"- Runtime: `{elapsed:.1f}s`.",
        "- Deployability: every trailing row is `research_only` until the execution engine supports the same runner stop policy and exact replay is rerun.",
        "",
        "## Baseline",
        "",
        (
            f"Baseline printed `{baseline['trades']}` trades, `{baseline['total_r']:+.2f}R`, "
            f"`{baseline['max_dd_r']:.2f}R` max DD, Calmar `{baseline['calmar']:.3f}`, "
            f"last-2Y `{baseline['last_2y_total_r']:+.2f}R`, and 2025+ `{baseline['holdout_2025p_total_r']:+.2f}R`."
        ),
        "",
        "## Verdict",
        "",
        (
            "Runner trailing confirms the recent discomfort but does not beat the current split ladder as an "
            "all-weather replacement. `risk_gap_0p75r` is the best recent challenger, improving last-2Y and "
            "2025+ R/DD, but it gives up too much full-history R/PF. `atr_gap_5pct` is the smoothest DD "
            "candidate, but also leaves substantial full-history R on the table. Step locks are worse than "
            "the baseline on full-history quality. Treat all trailing rows as research-only until exact "
            "execution support exists and the candidate is rerun through the live/exact engine."
        ),
        "",
        "## Top Full-History Rows",
        "",
        "| Variant | Mode | Trades | Net R | Max DD R | Calmar | PF | Last 2Y R | Last 2Y Calmar | 2025+ R | 2025+ DD R | Positive Runner Stops | Deployability |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    lines.extend(table_line(row) for row in ranked[:8])
    lines.extend([
        "",
        "## Top Recent Rows",
        "",
        "| Variant | Mode | Trades | Net R | Max DD R | Calmar | PF | Last 2Y R | Last 2Y Calmar | 2025+ R | 2025+ DD R | Positive Runner Stops | Deployability |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    lines.extend(table_line(row) for row in recent_ranked[:8])
    lines.extend([
        "",
        "## Files",
        "",
        f"- Summary CSV: `backtesting/data/results/{RUN_SLUG}/summary.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep ES NY ALPHA_V1 runner-trailing exit policies.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--use-1s", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    base = build_es_ny_config()
    configs = build_variants(base)

    print(f"Loading ES data {args.start} to {args.end}...")
    df = load_5m_data("ES_5m.csv", start=args.start, end=args.end)
    df_1m = load_1m_for_5m("ES_5m.csv", start=args.start, end=args.end)
    df_1s = load_1s_for_5m("ES_5m.csv", start=args.start, end=args.end) if args.use_1s else None
    print(f"  5m bars: {len(df):,}")
    print(f"  1m bars: {len(df_1m):,}")
    print(f"  1s bars: {len(df_1s):,}" if df_1s is not None else "  1s bars: not loaded")
    print(f"Running {len(configs)} variants...")

    t0 = time.time()

    def progress(done: int, total: int) -> None:
        print(f"\r  [{done}/{total}]", end="", flush=True)

    results = run_sweep(
        df,
        configs,
        n_workers=args.workers,
        progress_fn=progress,
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.1f}s")

    rows = [summarize_variant(config, trades, _variant_id(config)) for config, trades in results]
    rows = sorted(rows, key=lambda row: (row["calmar"] or -999, row["total_r"] or -999), reverse=True)

    _write_csv(RESULT_DIR / "summary.csv", rows)
    with (RESULT_DIR / "summary.json").open("w") as f:
        json.dump(_safe_json({"rows": rows}), f, indent=2, sort_keys=True)

    report = _report(rows, elapsed, df_1s is not None, args.start, args.end)
    REPORT_PATH.write_text(report)

    print(f"Wrote {RESULT_DIR / 'summary.csv'}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
