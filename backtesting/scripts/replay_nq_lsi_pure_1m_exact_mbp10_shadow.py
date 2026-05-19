#!/usr/bin/env python3
"""Exact live-engine replay with MBP-10-derived dynamic sizing in shadow mode.

This does not fetch DataBento data. It reuses the local MBP-10 replay validation
CSV, injects those decisions into the live LSI engine as a shadow sizing
provider, and reports what the frozen order-book sizing ladder would have done
on the exact execution-engine trade set.
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
from trader.orderbook_features import ScoredFeatureLookupProvider  # noqa: E402


RUN_SLUG = "nq_ny_lsi_pure_1m_exact_mbp10_shadow_20260516"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_REPLAY_CSV = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_pure_1m_velocity_mbp10_replay_validation_20260516"
    / "replay_validation.csv"
)
PROFILE_NAME = "NQ_LSI_PURE_1M_OBV_SHADOW"
SESSION_NAME = "NQ_NY_LSI_PURE_1M"
CANDIDATE = "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200"


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


def _summary(rows: list[dict[str, Any]], expected_dates: set[str]) -> dict[str, Any]:
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
    }


def _write_report(output_dir: Path, summary: dict[str, Any]) -> None:
    report = output_dir / "report.md"
    report.write_text(
        "\n".join([
            "# NQ NY LSI Pure 1m Exact MBP-10 Shadow Replay",
            "",
            f"- Profile: `{PROFILE_NAME}`",
            f"- Session: `{SESSION_NAME}`",
            f"- Candidate: `{CANDIDATE}`",
            "- DataBento fetches: `0`",
            f"- Trades: `{summary['trades']}`",
            f"- Date match: `{summary['date_match']}`",
            f"- Active decisions: `{summary['active_decisions']}`",
            f"- Fallback decisions: `{summary['fallback_decisions']}`",
            f"- Tier counts: `{summary['tier_counts']}`",
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
            "Interpretation: this is still shadow-only. It proves the exact live-engine replay can consume "
            "the locally replayed MBP-10 feature decisions and persist decision metadata, without changing "
            "executed quantities.",
            "",
        ])
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--replay-csv", type=Path, default=DEFAULT_REPLAY_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    replay = pd.read_csv(args.replay_csv)
    if replay.empty:
        raise SystemExit(f"Replay CSV is empty: {args.replay_csv}")
    replay_dates = set(replay["date"].astype(str))
    start_date = min(replay_dates)
    end_date = max(replay_dates)

    provider = ScoredFeatureLookupProvider.from_csv(
        args.replay_csv,
        candidate=CANDIDATE,
    )
    config = load_config(args.config)
    result = run_profile_backtest_sync(
        config=config,
        profile_name=PROFILE_NAME,
        start_date=start_date,
        end_date=end_date,
        label=f"EXEC EXACT MBP10 SHADOW {PROFILE_NAME} {start_date} to {end_date}",
        dynamic_sizing_providers={SESSION_NAME: provider},
        dynamic_sizing_shadow=True,
    )
    rows = _build_shadow_rows(result["trades"])
    summary = _summary(rows, replay_dates)
    summary["source_replay_csv"] = str(args.replay_csv)
    summary["output_dir"] = str(args.output_dir)
    summary["generated_at"] = datetime.now().isoformat()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output_dir / "exact_shadow_trades.csv", index=False)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    _write_report(args.output_dir, summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["date_match"] and summary["fallback_decisions"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
