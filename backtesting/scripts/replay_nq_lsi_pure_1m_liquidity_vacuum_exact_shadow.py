#!/usr/bin/env python3
"""Exact live-engine replay for the pure 1m liquidity-vacuum side branch.

This does not fetch DataBento data. It reuses the already-built broad
discretionary challenger matrix, converts the frozen liquidity-vacuum feature
values into a scored CSV, and injects those decisions into the live LSI engine
as a shadow sizing provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
EXECUTION_SRC = REPO_ROOT / "execution" / "src"
if str(EXECUTION_SRC) not in sys.path:
    sys.path.insert(0, str(EXECUTION_SRC))

from trader.historical_backtest import run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402
from trader.orderbook_features import (  # noqa: E402
    OrderbookDynamicSizingConfig,
    OrderbookVelocityTierSizer,
    ScoredFeatureLookupProvider,
)


RUN_SLUG = "nq_ny_lsi_pure_1m_liquidity_vacuum_exact_shadow_20260517"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_MATRIX_DIR = ROOT / "data" / "results" / "nq_lsi_broad_discretionary_challenger_matrix_20260517"
PROFILE_NAME = "NQ_LSI_PURE_1M_OBV_SHADOW"
SESSION_NAME = "NQ_NY_LSI_PURE_1M"
CANDIDATE = "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200"
FEATURE = "ob_vacuum_confirm_last_10s_score"
BRANCH = "liquidity_vacuum_book_pull"
WEIGHT_PROFILE = "tier_0p5_1_1p5"


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = sum(value for value in values if value < 0)
    if losses == 0:
        return 0.0
    return abs(wins / losses)


def _trade_dynamic(trade: dict[str, Any]) -> dict[str, Any]:
    context = trade.get("entry_context") or {}
    dynamic = context.get("dynamic_sizing") or {}
    return dynamic if isinstance(dynamic, dict) else {}


def _build_shadow_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade in trades:
        dynamic = _trade_dynamic(trade)
        risk_weight = float(dynamic.get("risk_weight", 1.0) or 1.0)
        r_multiple = float(trade["r_multiple"])
        weighted_r = r_multiple * risk_weight
        rows.append({
            "date": trade["date"],
            "session": trade["session"],
            "entry_time": trade.get("entry_time", ""),
            "exit_time": trade.get("exit_time", ""),
            "direction": trade["direction"],
            "entry_price": trade["entry_price"],
            "exit_type": trade["exit_type"],
            "qty": trade["qty"],
            "r_multiple": r_multiple,
            "risk_weight": risk_weight,
            "weighted_r": weighted_r,
            "tier": dynamic.get("tier", ""),
            "feature": dynamic.get("feature", ""),
            "feature_value": dynamic.get("feature_value"),
            "coverage": dynamic.get("coverage"),
            "sample_count": dynamic.get("sample_count"),
            "active": dynamic.get("active"),
            "reason": dynamic.get("reason", ""),
            "shadow": dynamic.get("shadow"),
            "applied": dynamic.get("applied"),
            "would_effective_qty_multiplier": dynamic.get("would_effective_qty_multiplier"),
            "effective_qty_multiplier": dynamic.get("effective_qty_multiplier"),
            "actual_qty_multiplier": dynamic.get("actual_qty_multiplier"),
        })
    return rows


def _summary(
    rows: list[dict[str, Any]],
    expected_dates: set[str],
    thresholds: dict[str, float],
    scored_csv: Path,
) -> dict[str, Any]:
    r_values = [float(row["r_multiple"]) for row in rows]
    weighted = [float(row["weighted_r"]) for row in rows]
    dates = {str(row["date"]) for row in rows}
    tiers = Counter(str(row["tier"] or "missing") for row in rows)
    active_count = sum(1 for row in rows if bool(row["active"]))
    fallback_count = sum(1 for row in rows if str(row["tier"] or "") == "fallback")
    return {
        "profile": PROFILE_NAME,
        "session": SESSION_NAME,
        "candidate": CANDIDATE,
        "branch": BRANCH,
        "feature": FEATURE,
        "weight_profile": WEIGHT_PROFILE,
        "thresholds": thresholds,
        "trades": len(rows),
        "date_match": dates == expected_dates,
        "missing_dates": sorted(expected_dates - dates),
        "extra_dates": sorted(dates - expected_dates),
        "dynamic_decisions": len([row for row in rows if row["tier"]]),
        "active_decisions": active_count,
        "fallback_decisions": fallback_count,
        "tier_counts": dict(sorted(tiers.items())),
        "baseline_total_r": sum(r_values),
        "baseline_avg_r": sum(r_values) / len(r_values) if r_values else 0.0,
        "baseline_pf": _profit_factor(r_values),
        "baseline_max_dd_r": _max_drawdown(r_values),
        "shadow_weighted_r": sum(weighted),
        "shadow_avg_r": sum(weighted) / len(weighted) if weighted else 0.0,
        "shadow_pf": _profit_factor(weighted),
        "shadow_max_dd_r": _max_drawdown(weighted),
        "shadow_delta_r": sum(weighted) - sum(r_values),
        "databento_fetches": 0,
        "source_scored_csv": str(scored_csv),
    }


def _load_thresholds(matrix_dir: Path) -> dict[str, float]:
    thresholds = pd.read_csv(matrix_dir / "frozen_thresholds.csv")
    row = thresholds[
        (thresholds["candidate"] == CANDIDATE)
        & (thresholds["feature"] == FEATURE)
    ]
    if len(row) != 1:
        raise SystemExit(f"Expected one frozen threshold row for {CANDIDATE} / {FEATURE}, found {len(row)}")
    record = row.iloc[0]
    return {
        "low_threshold": float(record["low_threshold_q33"]),
        "high_threshold": float(record["high_threshold_q66"]),
    }


def _build_scored_csv(matrix_dir: Path, output_dir: Path, thresholds: dict[str, float]) -> tuple[Path, set[str]]:
    matrix = pd.read_csv(matrix_dir / "trade_feature_matrix.csv")
    frame = matrix[
        (matrix["candidate"] == CANDIDATE)
        & (matrix["period"] == "holdout")
    ].copy()
    if frame.empty:
        raise SystemExit(f"No holdout feature rows found for {CANDIDATE}")
    if FEATURE not in frame:
        raise SystemExit(f"Missing feature column: {FEATURE}")

    scored = pd.DataFrame({
        "trade_uid": frame["trade_uid"],
        "date": frame["date"].astype(str),
        "candidate": frame["candidate"],
        "branch": BRANCH,
        "feature": FEATURE,
        "profile": WEIGHT_PROFILE,
        "signal_start": frame["signal_start"],
        "signal_end": frame["signal_end"],
        "direction": frame["direction"].astype(int),
        "feature_value": pd.to_numeric(frame[FEATURE], errors="coerce"),
        "coverage": 1.0,
        "sample_count": 1,
        "reason": "existing_mbp10_liquidity_vacuum_feature_lab",
        "low_threshold": thresholds["low_threshold"],
        "high_threshold": thresholds["high_threshold"],
    })
    if scored["feature_value"].isna().any():
        missing = int(scored["feature_value"].isna().sum())
        raise SystemExit(f"Missing {FEATURE} values in {missing} rows")

    output_dir.mkdir(parents=True, exist_ok=True)
    scored_csv = output_dir / "liquidity_vacuum_scored_replay.csv"
    scored.to_csv(scored_csv, index=False)
    return scored_csv, set(scored["date"].astype(str))


def _write_report(output_dir: Path, summary: dict[str, Any]) -> None:
    report = output_dir / "report.md"
    report.write_text(
        "\n".join([
            "# NQ NY LSI Pure 1m Liquidity-Vacuum Exact Shadow Replay",
            "",
            f"- Profile: `{PROFILE_NAME}`",
            f"- Session: `{SESSION_NAME}`",
            f"- Candidate: `{CANDIDATE}`",
            f"- Branch: `{BRANCH}`",
            f"- Feature: `{FEATURE}`",
            "- DataBento fetches: `0`",
            f"- Trades: `{summary['trades']}`",
            f"- Date match: `{summary['date_match']}`",
            f"- Active decisions: `{summary['active_decisions']}`",
            f"- Fallback decisions: `{summary['fallback_decisions']}`",
            f"- Tier counts: `{summary['tier_counts']}`",
            "",
            "## Frozen Rule",
            "",
            f"- Low: feature `< {summary['thresholds']['low_threshold']:.6f}`, weight `0.5x`",
            f"- Mid: feature `[{summary['thresholds']['low_threshold']:.6f}, {summary['thresholds']['high_threshold']:.6f})`, weight `1.0x`",
            f"- High: feature `>= {summary['thresholds']['high_threshold']:.6f}`, weight `1.5x`",
            "",
            "## Exact Replay Read",
            "",
            f"- Baseline exact R: `{summary['baseline_total_r']:.3f}R`",
            f"- Baseline exact avg: `{summary['baseline_avg_r']:.3f}R`",
            f"- Baseline exact PF: `{summary['baseline_pf']:.2f}`",
            f"- Baseline exact max DD: `{summary['baseline_max_dd_r']:.3f}R`",
            f"- Shadow weighted R: `{summary['shadow_weighted_r']:.3f}R`",
            f"- Shadow weighted avg: `{summary['shadow_avg_r']:.3f}R`",
            f"- Shadow weighted PF: `{summary['shadow_pf']:.2f}`",
            f"- Shadow weighted max DD: `{summary['shadow_max_dd_r']:.3f}R`",
            f"- Shadow delta: `{summary['shadow_delta_r']:+.3f}R`",
            "",
            "Interpretation: this pushes liquidity-vacuum one step closer to implementation, but it is still "
            "a scored-feature replay. A live-native liquidity-vacuum cache still needs MBP-10 depth fields, "
            "not only top-of-book midpoint samples.",
            "",
        ])
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--matrix-dir", type=Path, default=DEFAULT_MATRIX_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    thresholds = _load_thresholds(args.matrix_dir)
    scored_csv, replay_dates = _build_scored_csv(args.matrix_dir, args.output_dir, thresholds)
    config = OrderbookDynamicSizingConfig(
        feature=FEATURE,
        low_threshold=thresholds["low_threshold"],
        high_threshold=thresholds["high_threshold"],
        min_coverage=0.0,
        low_weight=0.5,
        mid_weight=1.0,
        high_weight=1.5,
        directions=(1,),
    )
    provider = ScoredFeatureLookupProvider.from_csv(
        scored_csv,
        candidate=CANDIDATE,
        feature=FEATURE,
        profile=WEIGHT_PROFILE,
        sizer=OrderbookVelocityTierSizer(config),
    )

    start_date = min(replay_dates)
    end_date = max(replay_dates)
    result = run_profile_backtest_sync(
        config=load_config(args.config),
        profile_name=PROFILE_NAME,
        start_date=start_date,
        end_date=end_date,
        label=f"EXEC EXACT LIQUIDITY VACUUM SHADOW {PROFILE_NAME} {start_date} to {end_date}",
        dynamic_sizing_providers={SESSION_NAME: provider},
        dynamic_sizing_shadow=True,
    )
    rows = _build_shadow_rows(result["trades"])
    summary = _summary(rows, replay_dates, thresholds, scored_csv)
    summary["output_dir"] = str(args.output_dir)
    summary["source_matrix_dir"] = str(args.matrix_dir)
    summary["generated_at"] = datetime.now().isoformat()

    pd.DataFrame(rows).to_csv(args.output_dir / "exact_shadow_trades.csv", index=False)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    _write_report(args.output_dir, summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["date_match"] and summary["fallback_decisions"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
