#!/usr/bin/env python3
"""No-fetch exact-engine probe for the 3m trapped-reversal side branch.

The profile is written to a temporary exec config in the result directory so
this does not change live configuration. The goal is to discover whether the
current execution engine can reproduce the 3m research trade dates closely
enough to justify a real parity implementation task.
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

import trader.main as trader_main  # noqa: E402
from trader.historical_backtest import run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402
from trader.orderbook_features import (  # noqa: E402
    OrderbookDynamicSizingConfig,
    OrderbookVelocityTierSizer,
    ScoredFeatureLookupProvider,
)


RUN_SLUG = "nq_lsi_3m_trapped_reversal_exact_shadow_probe_20260517"
OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_3M_TRAPPED_REVERSAL_EXACT_PROBE_20260517.md"
MATRIX_DIR = ROOT / "data" / "results" / "nq_lsi_broad_discretionary_challenger_matrix_20260517"
RISK_REPLAY_CSV = MATRIX_DIR / "risk_tier_replay.csv"
PROFILE_NAME = "NQ_LSI_3M_TRAPPED_REVERSAL_PROBE"
SESSION_NAME = "NQ_NY_LSI"
CANDIDATE = "add_3m_hourly_atr12p5_b3_a7p5"
FEATURE = "trapped_reversal_confirm_score"
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


def _profile_config() -> dict[str, Any]:
    return {
        PROFILE_NAME: {
            "enabled": False,
            "max_open_contracts": 20,
            "webhooks": [],
            "sessions": {},
            "lsi_sessions": {
                SESSION_NAME: {
                    "entry_start": "09:35",
                    "entry_end": "15:30",
                    "sweep_start": "09:30",
                    "sweep_end": "15:30",
                    "flat_start": "15:50",
                    "flat_end": "16:00",
                    "rr": 2.0,
                    "tp1_ratio": 0.5,
                    "min_gap_atr_pct": 5.0,
                    "min_stop_points": 0.0,
                    "stop_atr_pct": 12.5,
                    "fvg_window_left": 33,
                    "fvg_window_right": 8,
                    "lsi_entry_mode": "level_limit",
                    "lsi_stop_mode": "atr_pct",
                    "lsi_confirmation_mode": "inversion_or_cisd",
                    "lsi_variant": "htf-LSI",
                    "instrument": "NQ",
                    "atr_length": 10,
                    "long_only": False,
                    "excluded_dow": None,
                    "qty_multiplier": 1.0,
                    "risk_usd": 250,
                    "max_single_risk_usd": 500,
                    "lsi_n_left": 13,
                    "lsi_n_right": 100,
                    "lsi_reset_swing_window_on_new_day": False,
                    "cisd_min_leg_bars": 3,
                    "cisd_min_leg_atr_pct": 7.5,
                    "cisd_max_leg_bars": 100,
                    "base_bar_minutes": 3,
                    "htf_level_tf_minutes": 60,
                    "htf_n_left": 3,
                    "htf_trade_max_per_session": 1,
                    "dynamic_sizing_shadow": True,
                }
            },
        }
    }


def _load_thresholds() -> dict[str, float]:
    thresholds = pd.read_csv(MATRIX_DIR / "frozen_thresholds.csv")
    row = thresholds[
        (thresholds["candidate"] == CANDIDATE)
        & (thresholds["feature"] == FEATURE)
    ]
    if len(row) != 1:
        raise SystemExit(f"Expected one threshold row for {CANDIDATE} / {FEATURE}; found {len(row)}")
    record = row.iloc[0]
    return {
        "low_threshold": float(record["low_threshold_q33"]),
        "high_threshold": float(record["high_threshold_q66"]),
    }


def _expected_holdout_rows() -> pd.DataFrame:
    replay = pd.read_csv(RISK_REPLAY_CSV)
    rows = replay[
        (replay["candidate"] == CANDIDATE)
        & (replay["feature"] == FEATURE)
        & (replay["weight_profile"] == WEIGHT_PROFILE)
        & (replay["period"] == "holdout")
    ].copy()
    if rows.empty:
        raise SystemExit("No 3m trapped-reversal holdout rows found")
    return rows


def _provider(thresholds: dict[str, float]) -> ScoredFeatureLookupProvider:
    config = OrderbookDynamicSizingConfig(
        feature=FEATURE,
        low_threshold=thresholds["low_threshold"],
        high_threshold=thresholds["high_threshold"],
        min_coverage=0.0,
        low_weight=0.5,
        mid_weight=1.0,
        high_weight=1.5,
        directions=(-1, 1),
    )
    return ScoredFeatureLookupProvider.from_csv(
        RISK_REPLAY_CSV,
        candidate=CANDIDATE,
        feature=FEATURE,
        profile=WEIGHT_PROFILE,
        sizer=OrderbookVelocityTierSizer(config),
    )


def _shadow_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for trade in trades:
        dynamic = _trade_dynamic(trade)
        r_multiple = float(trade["r_multiple"])
        risk_weight = float(dynamic.get("risk_weight", 1.0) or 1.0)
        rows.append({
            "date": trade["date"],
            "session": trade["session"],
            "entry_time": trade.get("entry_time", ""),
            "exit_time": trade.get("exit_time", ""),
            "direction": trade["direction"],
            "entry_price": trade["entry_price"],
            "exit_type": trade["exit_type"],
            "r_multiple": r_multiple,
            "risk_weight": risk_weight,
            "weighted_r": r_multiple * risk_weight,
            "tier": dynamic.get("tier", ""),
            "feature_value": dynamic.get("feature_value"),
            "active": dynamic.get("active"),
            "reason": dynamic.get("reason", ""),
            "signal_start": dynamic.get("signal_start", ""),
            "shadow": dynamic.get("shadow"),
        })
    return rows


def _summary(rows: list[dict[str, Any]], expected: pd.DataFrame, thresholds: dict[str, float]) -> dict[str, Any]:
    expected_dates = set(expected["date"].astype(str))
    exact_dates = {str(row["date"]) for row in rows}
    r_values = [float(row["r_multiple"]) for row in rows]
    weighted = [float(row["weighted_r"]) for row in rows]
    fallback_count = sum(1 for row in rows if str(row["tier"] or "") == "fallback")
    tiers = Counter(str(row["tier"] or "missing") for row in rows)
    date_match = exact_dates == expected_dates
    return {
        "run_slug": RUN_SLUG,
        "profile": PROFILE_NAME,
        "session": SESSION_NAME,
        "candidate": CANDIDATE,
        "feature": FEATURE,
        "thresholds": thresholds,
        "databento_fetches": 0,
        "expected_research_holdout_trades": int(len(expected)),
        "exact_trades": len(rows),
        "date_match": date_match,
        "missing_dates": sorted(expected_dates - exact_dates),
        "extra_dates": sorted(exact_dates - expected_dates),
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
        "parity_status": "pass" if date_match and fallback_count == 0 else "blocked",
    }


def _write_report(summary: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "\n".join([
            "# NQ NY LSI 3m Trapped-Reversal Exact Probe",
            "",
            "- Date: 2026-05-17",
            "- Scope: no-fetch exact-engine probe using a temporary execution profile.",
            f"- Candidate: `{CANDIDATE}`",
            f"- Feature: `{FEATURE}`",
            "- DataBento fetches: `0`",
            f"- Parity status: `{summary['parity_status']}`",
            "",
            "## Probe Read",
            "",
            f"- Research holdout trades expected: `{summary['expected_research_holdout_trades']}`",
            f"- Exact trades produced: `{summary['exact_trades']}`",
            f"- Date match: `{summary['date_match']}`",
            f"- Missing dates: `{len(summary['missing_dates'])}`",
            f"- Extra dates: `{len(summary['extra_dates'])}`",
            f"- Fallback decisions: `{summary['fallback_decisions']}`",
            f"- Tier counts: `{summary['tier_counts']}`",
            "",
            "## Exact Metrics",
            "",
            f"- Exact baseline R: `{summary['baseline_total_r']:.3f}R`",
            f"- Exact baseline avg: `{summary['baseline_avg_r']:.3f}R`",
            f"- Exact baseline PF: `{summary['baseline_pf']:.2f}`",
            f"- Exact baseline max DD: `{summary['baseline_max_dd_r']:.3f}R`",
            f"- Shadow weighted R: `{summary['shadow_weighted_r']:.3f}R`",
            f"- Shadow weighted avg: `{summary['shadow_avg_r']:.3f}R`",
            f"- Shadow weighted PF: `{summary['shadow_pf']:.2f}`",
            f"- Shadow weighted max DD: `{summary['shadow_max_dd_r']:.3f}R`",
            f"- Shadow delta: `{summary['shadow_delta_r']:+.3f}R`",
            "",
            "## Interpretation",
            "",
            "This is a probe, not a promotion packet. A `blocked` result means the execution profile can run "
            "3m bars, but the signal stream is not yet exact-parity with the research candidate or the scored "
            "feature rows. That would make exact 3m parity the next engineering task before live shadowing.",
            "",
            "## Output Files",
            "",
            f"- `{OUTPUT_DIR / 'temp_exec_configs.json'}`",
            f"- `{OUTPUT_DIR / 'exact_shadow_trades.csv'}`",
            f"- `{OUTPUT_DIR / 'summary.json'}`",
        ])
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temp_exec_config = OUTPUT_DIR / "temp_exec_configs.json"
    temp_exec_config.write_text(json.dumps(_profile_config(), indent=2) + "\n")
    trader_main.EXEC_CONFIGS_PATH = temp_exec_config

    expected = _expected_holdout_rows()
    thresholds = _load_thresholds()
    start_date = str(expected["date"].min())
    end_date = str(expected["date"].max())
    result = run_profile_backtest_sync(
        config=load_config(args.config),
        profile_name=PROFILE_NAME,
        start_date=start_date,
        end_date=end_date,
        label=f"EXEC EXACT 3M TRAPPED REVERSAL PROBE {start_date} to {end_date}",
        dynamic_sizing_providers={SESSION_NAME: _provider(thresholds)},
        dynamic_sizing_shadow=True,
    )
    rows = _shadow_rows(result["trades"])
    summary = _summary(rows, expected, thresholds)
    summary["output_dir"] = str(OUTPUT_DIR)
    summary["generated_at"] = datetime.now().isoformat()

    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "exact_shadow_trades.csv", index=False)
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    _write_report(summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
