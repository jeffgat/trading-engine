#!/usr/bin/env python3
"""Explore "chasing" newer ORB gaps for the ALPHA_V1 ORB legs.

Compares the frozen ALPHA_V1 ORB continuation legs under two same-day FVG
selection rules:

1. ``first``   — current engine behavior (first valid FVG per session-day)
2. ``extreme`` — ratchet to the most aggressive same-direction FVG of the day
                 (highest bullish gap / lowest bearish gap)

The study window is the trailing two years ending 2026-04-17, with a small
warmup buffer for ATR and regime calculations.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.alpha_v1_downside import (  # noqa: E402
    DataCache,
    build_alpha_v1_legs,
    filter_trades_by_combined_regime,
    run_config,
)
from orb_backtest.analysis.regime_research import (  # noqa: E402
    attribute_strategy_by_regime,
    compute_bucket_metrics,
)
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


REQUESTED_WINDOW_START = "2024-04-17"
REQUESTED_WINDOW_END = "2026-04-17"
WARMUP_START = "2024-01-01"
LEG_KEYS = (
    "nq_asia_orb_long",
    "es_asia_orb_long",
    "es_ny_orb_long",
)
LEG_LABELS = {
    "nq_asia_orb_long": "NQ Asia ORB",
    "es_asia_orb_long": "ES Asia ORB",
    "es_ny_orb_long": "ES NY ORB",
}
GATES: dict[str, dict[str, Any]] = {
    "ungated": {
        "include": frozenset(),
        "exclude": frozenset(),
        "description": "No regime filter",
    },
    "only_bull_all": {
        "include": frozenset({"bull_low_vol", "bull_medium_vol", "bull_high_vol"}),
        "exclude": frozenset(),
        "description": "Only bull regimes",
    },
    "only_high_vol": {
        "include": frozenset({"bull_high_vol", "bear_high_vol", "sideways_high_vol"}),
        "exclude": frozenset(),
        "description": "Only high-vol regimes",
    },
    "only_bull_high_vol": {
        "include": frozenset({"bull_high_vol"}),
        "exclude": frozenset(),
        "description": "Only bull high vol",
    },
    "only_bull_med_high_vol": {
        "include": frozenset({"bull_medium_vol", "bull_high_vol"}),
        "exclude": frozenset(),
        "description": "Only bull medium/high vol",
    },
}

RESULTS_DIR = ROOT / "data" / "results"
REPORTS_DIR = ROOT / "learnings" / "reports"


def _select_window_end(cache: DataCache) -> str:
    last_dates = []
    for key in LEG_KEYS:
        leg = build_alpha_v1_legs()[key]
        market = cache.get(leg.config.instrument)
        last_dates.append(pd.Timestamp(market.df_5m.index.max()).date().isoformat())
    return min(REQUESTED_WINDOW_END, min(last_dates))


def _metrics_snapshot(trades: list[TradeResult]) -> dict[str, float]:
    metrics = compute_metrics(trades)
    total_signals = int(metrics["total_signals"])
    filled = int(metrics["total_trades"])
    fill_rate = (filled / total_signals) if total_signals else 0.0
    return {
        "total_signals": total_signals,
        "filled_trades": filled,
        "no_fills": int(metrics["no_fills"]),
        "fill_rate": round(fill_rate, 4),
        "win_rate": round(float(metrics["win_rate"]), 4),
        "profit_factor": round(float(metrics["profit_factor"]), 4),
        "avg_r": round(float(metrics["avg_r"]), 4),
        "total_r": round(float(metrics["total_r"]), 4),
        "max_drawdown_r": round(float(metrics["max_drawdown_r"]), 4),
        "calmar_ratio": round(float(metrics["calmar_ratio"]), 4),
        "sharpe_ratio": round(float(metrics["sharpe_ratio"]), 4),
    }


def _trade_key(trade: TradeResult) -> tuple[str, str]:
    return trade.date, trade.session


def _trade_map(trades: list[TradeResult]) -> dict[tuple[str, str], TradeResult]:
    return {_trade_key(trade): trade for trade in trades}


def _trade_r(trade: TradeResult | None) -> float:
    if trade is None or trade.exit_type == EXIT_NO_FILL:
        return 0.0
    return float(trade.r_multiple)


def _selection_summary(
    baseline_trades: list[TradeResult],
    chase_trades: list[TradeResult],
) -> dict[str, Any]:
    base_map = _trade_map(baseline_trades)
    chase_map = _trade_map(chase_trades)
    all_keys = sorted(set(base_map) | set(chase_map))

    changed_days = 0
    higher_entry_days = 0
    lower_entry_days = 0
    base_no_fill_to_chase_fill = 0
    chase_no_fill_to_base_fill = 0
    entry_deltas: list[float] = []
    per_day_r_delta = 0.0

    for key in all_keys:
        base_trade = base_map.get(key)
        chase_trade = chase_map.get(key)
        if base_trade is None or chase_trade is None:
            changed_days += 1
            per_day_r_delta += _trade_r(chase_trade) - _trade_r(base_trade)
            continue

        entry_delta = float(chase_trade.entry_price) - float(base_trade.entry_price)
        changed = (
            base_trade.signal_bar != chase_trade.signal_bar
            or abs(entry_delta) > 1e-9
        )
        if changed:
            changed_days += 1
            entry_deltas.append(entry_delta)
            if entry_delta > 0:
                higher_entry_days += 1
            elif entry_delta < 0:
                lower_entry_days += 1

        if base_trade.exit_type == EXIT_NO_FILL and chase_trade.exit_type != EXIT_NO_FILL:
            base_no_fill_to_chase_fill += 1
        if base_trade.exit_type != EXIT_NO_FILL and chase_trade.exit_type == EXIT_NO_FILL:
            chase_no_fill_to_base_fill += 1

        per_day_r_delta += _trade_r(chase_trade) - _trade_r(base_trade)

    avg_entry_delta = sum(entry_deltas) / len(entry_deltas) if entry_deltas else 0.0
    return {
        "candidate_days": len(all_keys),
        "changed_days": changed_days,
        "changed_share": round(changed_days / len(all_keys), 4) if all_keys else 0.0,
        "higher_entry_days": higher_entry_days,
        "lower_entry_days": lower_entry_days,
        "avg_entry_delta_points_on_changed_days": round(avg_entry_delta, 4),
        "baseline_no_fill_to_chase_fill": base_no_fill_to_chase_fill,
        "chase_no_fill_to_baseline_fill": chase_no_fill_to_base_fill,
        "per_day_total_r_delta": round(per_day_r_delta, 4),
    }


def _bucket_delta_rows(
    baseline_trades: list[TradeResult],
    chase_trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    window_start: str,
) -> list[dict[str, Any]]:
    base_attr = attribute_strategy_by_regime(
        baseline_trades,
        regime_calendar,
        holdout_start=window_start,
    )
    chase_attr = attribute_strategy_by_regime(
        chase_trades,
        regime_calendar,
        holdout_start=window_start,
    )
    base_bucket = compute_bucket_metrics(base_attr, "combined_regime")
    chase_bucket = compute_bucket_metrics(chase_attr, "combined_regime")

    if base_bucket.empty and chase_bucket.empty:
        return []

    merged = (
        base_bucket.rename(
            columns={
                "trade_count": "baseline_trade_count",
                "avg_r": "baseline_avg_r",
                "total_r": "baseline_total_r",
                "win_rate": "baseline_win_rate",
                "profit_factor": "baseline_profit_factor",
                "max_drawdown_r": "baseline_max_drawdown_r",
            }
        )
        .merge(
            chase_bucket.rename(
                columns={
                    "trade_count": "chase_trade_count",
                    "avg_r": "chase_avg_r",
                    "total_r": "chase_total_r",
                    "win_rate": "chase_win_rate",
                    "profit_factor": "chase_profit_factor",
                    "max_drawdown_r": "chase_max_drawdown_r",
                }
            ),
            on="bucket",
            how="outer",
        )
        .fillna(0.0)
        .sort_values("bucket")
    )

    rows: list[dict[str, Any]] = []
    for row in merged.to_dict(orient="records"):
        rows.append(
            {
                "bucket": str(row["bucket"]),
                "baseline_trade_count": int(row["baseline_trade_count"]),
                "chase_trade_count": int(row["chase_trade_count"]),
                "delta_trade_count": int(row["chase_trade_count"] - row["baseline_trade_count"]),
                "baseline_avg_r": round(float(row["baseline_avg_r"]), 4),
                "chase_avg_r": round(float(row["chase_avg_r"]), 4),
                "delta_avg_r": round(float(row["chase_avg_r"] - row["baseline_avg_r"]), 4),
                "baseline_total_r": round(float(row["baseline_total_r"]), 4),
                "chase_total_r": round(float(row["chase_total_r"]), 4),
                "delta_total_r": round(float(row["chase_total_r"] - row["baseline_total_r"]), 4),
            }
        )
    return rows


def _gate_rows(
    baseline_trades: list[TradeResult],
    chase_trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, gate in GATES.items():
        gated_base = filter_trades_by_combined_regime(
            baseline_trades,
            regime_calendar,
            include=set(gate["include"]),
            exclude=set(gate["exclude"]),
            include_low_confidence=True,
        )
        gated_chase = filter_trades_by_combined_regime(
            chase_trades,
            regime_calendar,
            include=set(gate["include"]),
            exclude=set(gate["exclude"]),
            include_low_confidence=True,
        )
        base_metrics = _metrics_snapshot(gated_base)
        chase_metrics = _metrics_snapshot(gated_chase)
        rows.append(
            {
                "gate": label,
                "description": gate["description"],
                "baseline_filled_trades": base_metrics["filled_trades"],
                "chase_filled_trades": chase_metrics["filled_trades"],
                "delta_filled_trades": chase_metrics["filled_trades"] - base_metrics["filled_trades"],
                "baseline_total_r": base_metrics["total_r"],
                "chase_total_r": chase_metrics["total_r"],
                "delta_total_r": round(chase_metrics["total_r"] - base_metrics["total_r"], 4),
                "baseline_calmar_ratio": base_metrics["calmar_ratio"],
                "chase_calmar_ratio": chase_metrics["calmar_ratio"],
                "delta_calmar_ratio": round(chase_metrics["calmar_ratio"] - base_metrics["calmar_ratio"], 4),
                "baseline_fill_rate": base_metrics["fill_rate"],
                "chase_fill_rate": chase_metrics["fill_rate"],
            }
        )
    return rows


def _fmt_pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def _fmt_num(value: float, digits: int = 2, signed: bool = False) -> str:
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def _metrics_table(title: str, baseline: dict[str, float], chase: dict[str, float]) -> list[str]:
    delta_r = chase["total_r"] - baseline["total_r"]
    delta_calmar = chase["calmar_ratio"] - baseline["calmar_ratio"]
    delta_fill_rate = chase["fill_rate"] - baseline["fill_rate"]
    return [
        f"### {title}",
        "",
        "| Variant | Signals | Filled | No fill | Fill rate | WR | PF | Avg R | Total R | DD (R) | Calmar | Sharpe |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| Baseline (`first`) | {baseline['total_signals']} | {baseline['filled_trades']} | "
            f"{baseline['no_fills']} | {_fmt_pct(baseline['fill_rate'])} | {_fmt_pct(baseline['win_rate'])} | "
            f"{baseline['profit_factor']:.2f} | {baseline['avg_r']:.3f} | {baseline['total_r']:+.2f} | "
            f"{baseline['max_drawdown_r']:+.2f} | {baseline['calmar_ratio']:.2f} | {baseline['sharpe_ratio']:.2f} |"
        ),
        (
            f"| Chase (`extreme`) | {chase['total_signals']} | {chase['filled_trades']} | "
            f"{chase['no_fills']} | {_fmt_pct(chase['fill_rate'])} | {_fmt_pct(chase['win_rate'])} | "
            f"{chase['profit_factor']:.2f} | {chase['avg_r']:.3f} | {chase['total_r']:+.2f} | "
            f"{chase['max_drawdown_r']:+.2f} | {chase['calmar_ratio']:.2f} | {chase['sharpe_ratio']:.2f} |"
        ),
        (
            f"| Delta (chase - baseline) | 0 | {chase['filled_trades'] - baseline['filled_trades']:+d} | "
            f"{chase['no_fills'] - baseline['no_fills']:+d} | {_fmt_pct(delta_fill_rate)} | "
            f"{_fmt_pct(chase['win_rate'] - baseline['win_rate'])} | "
            f"{_fmt_num(chase['profit_factor'] - baseline['profit_factor'], signed=True)} | "
            f"{_fmt_num(chase['avg_r'] - baseline['avg_r'], 3, True)} | {delta_r:+.2f} | "
            f"{chase['max_drawdown_r'] - baseline['max_drawdown_r']:+.2f} | {delta_calmar:+.2f} | "
            f"{chase['sharpe_ratio'] - baseline['sharpe_ratio']:+.2f} |"
        ),
        "",
    ]


def _selection_table(selection: dict[str, Any]) -> list[str]:
    return [
        "### Selection Diagnostics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Candidate days compared | {selection['candidate_days']} |",
        f"| Days where chase changed the chosen gap | {selection['changed_days']} |",
        f"| Changed-share | {_fmt_pct(selection['changed_share'])} |",
        f"| Days with higher chase entry | {selection['higher_entry_days']} |",
        f"| Days with lower chase entry | {selection['lower_entry_days']} |",
        f"| Avg entry delta on changed days (pts) | {selection['avg_entry_delta_points_on_changed_days']:+.2f} |",
        f"| Baseline no-fill -> chase fill | {selection['baseline_no_fill_to_chase_fill']} |",
        f"| Chase no-fill -> baseline fill | {selection['chase_no_fill_to_baseline_fill']} |",
        f"| Total per-day R delta | {selection['per_day_total_r_delta']:+.2f} |",
        "",
    ]


def _bucket_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["### Regime Attribution Delta", "", "_No filled trades to attribute._", ""]
    lines = [
        "### Regime Attribution Delta",
        "",
        "| Bucket | Base Tr | Chase Tr | Delta Tr | Base Avg R | Chase Avg R | Delta Avg R | Base Total R | Chase Total R | Delta Total R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['bucket']} | {row['baseline_trade_count']} | {row['chase_trade_count']} | "
            f"{row['delta_trade_count']:+d} | {row['baseline_avg_r']:+.3f} | {row['chase_avg_r']:+.3f} | "
            f"{row['delta_avg_r']:+.3f} | {row['baseline_total_r']:+.2f} | {row['chase_total_r']:+.2f} | "
            f"{row['delta_total_r']:+.2f} |"
        )
    lines.append("")
    return lines


def _gate_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "### Hypothesis Gates",
        "",
        "| Gate | Description | Base Tr | Chase Tr | Delta Tr | Base Total R | Chase Total R | Delta Total R | Base Calmar | Chase Calmar | Delta Calmar |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['gate']} | {row['description']} | {row['baseline_filled_trades']} | "
            f"{row['chase_filled_trades']} | {row['delta_filled_trades']:+d} | "
            f"{row['baseline_total_r']:+.2f} | {row['chase_total_r']:+.2f} | {row['delta_total_r']:+.2f} | "
            f"{row['baseline_calmar_ratio']:.2f} | {row['chase_calmar_ratio']:.2f} | {row['delta_calmar_ratio']:+.2f} |"
        )
    lines.append("")
    return lines


def main() -> None:
    t0 = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("ALPHA_V1 ORB Gap-Chase Exploration")
    print("=" * 80)
    print(f"Requested evaluation window: {REQUESTED_WINDOW_START} -> {REQUESTED_WINDOW_END}")
    print(f"Warmup start: {WARMUP_START}")

    cache = DataCache(start_date=WARMUP_START, end_date=REQUESTED_WINDOW_END)
    window_end = _select_window_end(cache)
    print(f"Actual evaluation window:    {REQUESTED_WINDOW_START} -> {window_end}")

    legs = build_alpha_v1_legs()
    payload: dict[str, Any] = {
        "metadata": {
            "requested_window_start": REQUESTED_WINDOW_START,
            "requested_window_end": REQUESTED_WINDOW_END,
            "actual_window_start": REQUESTED_WINDOW_START,
            "actual_window_end": window_end,
            "warmup_start": WARMUP_START,
            "generated_at": pd.Timestamp.now("UTC").isoformat(),
            "selector_modes": {
                "baseline": "first",
                "chase": "extreme",
            },
        },
        "legs": {},
    }

    report_lines = [
        "# ALPHA_V1 ORB Gap-Chase Exploration",
        "",
        f"- Requested evaluation window: `{REQUESTED_WINDOW_START}` -> `{REQUESTED_WINDOW_END}`",
        f"- Actual evaluation window: `{REQUESTED_WINDOW_START}` -> `{window_end}`",
        f"- Warmup start: `{WARMUP_START}`",
        "- Baseline selector: `first` (existing engine behavior)",
        "- Chase selector: `extreme` (ratchet to highest bullish / lowest bearish same-day FVG)",
        "",
    ]

    combined_summary = {
        "baseline_total_r": 0.0,
        "chase_total_r": 0.0,
        "baseline_filled_trades": 0,
        "chase_filled_trades": 0,
    }

    for key in LEG_KEYS:
        leg = legs[key]
        label = LEG_LABELS[key]
        print(f"\nRunning {label}...", flush=True)
        base_config = replace(
            leg.config,
            continuation_fvg_selection="first",
            name=f"{label} {REQUESTED_WINDOW_START} {window_end} first-gap",
        )
        chase_config = replace(
            leg.config,
            continuation_fvg_selection="extreme",
            name=f"{label} {REQUESTED_WINDOW_START} {window_end} chase-gap",
        )

        base_trades = run_config(
            cache,
            base_config,
            start_date=REQUESTED_WINDOW_START,
            end_date=window_end,
        )
        chase_trades = run_config(
            cache,
            chase_config,
            start_date=REQUESTED_WINDOW_START,
            end_date=window_end,
        )
        market = cache.get(base_config.instrument)
        regime_calendar = market.regime_calendar[
            (market.regime_calendar["date"] >= REQUESTED_WINDOW_START)
            & (market.regime_calendar["date"] <= window_end)
        ].copy()

        base_metrics = _metrics_snapshot(base_trades)
        chase_metrics = _metrics_snapshot(chase_trades)
        selection = _selection_summary(base_trades, chase_trades)
        bucket_rows = _bucket_delta_rows(base_trades, chase_trades, regime_calendar, REQUESTED_WINDOW_START)
        gate_rows = _gate_rows(base_trades, chase_trades, regime_calendar)

        payload["legs"][key] = {
            "label": label,
            "symbol": base_config.instrument.symbol,
            "baseline_metrics": base_metrics,
            "chase_metrics": chase_metrics,
            "selection_diagnostics": selection,
            "bucket_deltas": bucket_rows,
            "gate_sweep": gate_rows,
        }

        combined_summary["baseline_total_r"] += base_metrics["total_r"]
        combined_summary["chase_total_r"] += chase_metrics["total_r"]
        combined_summary["baseline_filled_trades"] += base_metrics["filled_trades"]
        combined_summary["chase_filled_trades"] += chase_metrics["filled_trades"]

        report_lines.extend([f"## {label}", ""])
        report_lines.extend(_metrics_table("Performance", base_metrics, chase_metrics))
        report_lines.extend(_selection_table(selection))
        report_lines.extend(_bucket_table(bucket_rows))
        report_lines.extend(_gate_table(gate_rows))

        print(
            f"  baseline {base_metrics['filled_trades']} trades, {base_metrics['total_r']:+.1f}R | "
            f"chase {chase_metrics['filled_trades']} trades, {chase_metrics['total_r']:+.1f}R"
        )

    payload["combined_orb_summary"] = {
        "baseline_total_r": round(combined_summary["baseline_total_r"], 4),
        "chase_total_r": round(combined_summary["chase_total_r"], 4),
        "delta_total_r": round(combined_summary["chase_total_r"] - combined_summary["baseline_total_r"], 4),
        "baseline_filled_trades": combined_summary["baseline_filled_trades"],
        "chase_filled_trades": combined_summary["chase_filled_trades"],
        "delta_filled_trades": combined_summary["chase_filled_trades"] - combined_summary["baseline_filled_trades"],
    }

    report_lines.extend(
        [
            "## Combined ORB Summary",
            "",
            "| Metric | Baseline | Chase | Delta |",
            "|---|---:|---:|---:|",
            f"| Filled trades | {combined_summary['baseline_filled_trades']} | {combined_summary['chase_filled_trades']} | {combined_summary['chase_filled_trades'] - combined_summary['baseline_filled_trades']:+d} |",
            f"| Total R | {combined_summary['baseline_total_r']:+.2f} | {combined_summary['chase_total_r']:+.2f} | {combined_summary['chase_total_r'] - combined_summary['baseline_total_r']:+.2f} |",
            "",
        ]
    )

    slug = f"alpha_v1_orb_gap_chase_{REQUESTED_WINDOW_START.replace('-', '')}_{window_end.replace('-', '')}"
    json_path = RESULTS_DIR / f"{slug}.json"
    report_path = REPORTS_DIR / f"{slug.upper()}.md"

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report_path.write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")

    print("\nCombined ORB summary")
    print(
        f"  baseline {combined_summary['baseline_filled_trades']} trades, {combined_summary['baseline_total_r']:+.1f}R"
    )
    print(
        f"  chase    {combined_summary['chase_filled_trades']} trades, {combined_summary['chase_total_r']:+.1f}R"
    )
    print(f"  delta    {combined_summary['chase_total_r'] - combined_summary['baseline_total_r']:+.1f}R")
    print(f"\nSaved JSON:   {json_path}")
    print(f"Saved report: {report_path}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
