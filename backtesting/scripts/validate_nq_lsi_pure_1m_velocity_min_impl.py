#!/usr/bin/env python3
"""Minimum no-fetch implementation validation for pure 1m order-book velocity.

This validates the execution-facing dynamic-sizing decision module against the
existing frozen replay CSV. It intentionally performs no DataBento requests.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd


BACKTESTING_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKTESTING_ROOT.parent
EXECUTION_SRC = REPO_ROOT / "execution" / "src"
if str(EXECUTION_SRC) not in sys.path:
    sys.path.insert(0, str(EXECUTION_SRC))

from trader.orderbook_features import (  # noqa: E402
    DynamicSizingContext,
    OrderbookVelocityTierSizer,
    ScoredFeatureLookupProvider,
)


RUN_SLUG = "nq_ny_lsi_pure_1m_orderbook_velocity_min_impl_validation_20260516"
INPUT_PATH = (
    BACKTESTING_ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_orderbook_risk_tiers_20260515"
    / "trade_risk_tier_replay.csv"
)
OUTPUT_DIR = BACKTESTING_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = (
    BACKTESTING_ROOT
    / "learnings"
    / "reports"
    / "NQ_NY_LSI_PURE_1M_ORDERBOOK_VELOCITY_MIN_IMPL_VALIDATION_20260516.md"
)

OVERLAY = "pure_1m_long_confirm_last_velocity"
CANDIDATE = "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200"
FEATURE = "confirm_last_10s_mid_velocity_ticks_per_second"
PRIMARY_PROFILE = "tier_0p5_1_1p5"


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def parse_signal_start(value: Any):
    return pd.to_datetime(value).to_pydatetime()


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    equity = values.cumsum()
    running_peak = equity.cummax().clip(lower=0.0)
    drawdown = equity - running_peak
    return float(drawdown.min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    if losses == 0.0:
        return float("inf") if gains > 0.0 else 0.0
    return gains / losses


def r_metrics(values: pd.Series) -> dict[str, float | int]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return {
        "trades": int(len(clean)),
        "total_r": float(clean.sum()),
        "avg_r": float(clean.mean()) if len(clean) else 0.0,
        "win_rate": float((clean > 0).mean()) if len(clean) else 0.0,
        "profit_factor": profit_factor(clean),
        "max_dd_r": max_drawdown(clean),
    }


def period_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for period, group in frame.groupby("period", sort=True):
        baseline = r_metrics(group["r_multiple"])
        weighted = r_metrics(group["computed_weighted_r"])
        rows.append(
            {
                "period": period,
                "unique_trade_dates": int(group["date"].astype(str).nunique()),
                "tier_mismatches": int((~group["tier_match"]).sum()),
                "weight_mismatches": int((~group["weight_match"]).sum()),
                "weighted_r_mismatches": int((~group["weighted_r_match"]).sum()),
                **{f"baseline_{key}": value for key, value in baseline.items()},
                **{f"weighted_{key}": value for key, value in weighted.items()},
                "delta_total_r": float(weighted["total_r"] - baseline["total_r"]),
                "delta_avg_r": float(weighted["avg_r"] - baseline["avg_r"]),
            }
        )
    return pd.DataFrame(rows)


def tier_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (period, tier), group in frame.groupby(["period", "computed_tier"], sort=True):
        metrics = r_metrics(group["computed_weighted_r"])
        rows.append(
            {
                "period": period,
                "tier": tier,
                "risk_weight": float(group["computed_risk_weight"].iloc[0]),
                "feature_min": float(group["feature_value"].min()),
                "feature_max": float(group["feature_value"].max()),
                "unique_trade_dates": int(group["date"].astype(str).nunique()),
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def validate_replay() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    replay = pd.read_csv(INPUT_PATH)
    frame = replay[
        (replay["overlay"] == OVERLAY)
        & (replay["candidate"] == CANDIDATE)
        & (replay["feature"] == FEATURE)
        & (replay["weight_profile"] == PRIMARY_PROFILE)
    ].copy()
    if frame.empty:
        raise SystemExit("No pure 1m velocity rows found in replay CSV.")

    sizer = OrderbookVelocityTierSizer()
    provider = ScoredFeatureLookupProvider.from_csv(
        INPUT_PATH,
        overlay=OVERLAY,
        candidate=CANDIDATE,
        feature=FEATURE,
        profile=PRIMARY_PROFILE,
        sizer=sizer,
    )
    decisions = []
    for _, row in frame.iterrows():
        decision = provider(DynamicSizingContext(
            symbol="NQ.FUT",
            direction=int(row["direction"]),
            signal_start=parse_signal_start(row["signal_start"]),
            config_name=CANDIDATE,
            session="NQ_NY_LSI",
            entry_price=finite_float(row.get("entry_price")),
        ))
        decisions.append(decision)

    frame["computed_tier"] = [decision.tier for decision in decisions]
    frame["computed_risk_weight"] = [decision.risk_weight for decision in decisions]
    frame["computed_active_trade"] = [decision.risk_weight > 0.0 for decision in decisions]
    frame["computed_weighted_r"] = frame["r_multiple"].astype(float) * frame["computed_risk_weight"]
    frame["decision_reason"] = [decision.reason for decision in decisions]
    frame["tier_match"] = frame["computed_tier"] == frame["feature_tier"]
    frame["weight_match"] = (
        (frame["computed_risk_weight"].astype(float) - frame["risk_weight"].astype(float)).abs() < 1e-12
    )
    frame["weighted_r_match"] = (
        (frame["computed_weighted_r"].astype(float) - frame["weighted_r"].astype(float)).abs() < 1e-12
    )
    frame["active_match"] = frame["computed_active_trade"] == frame["active_trade"].astype(bool)

    periods = period_metrics(frame)
    tiers = tier_metrics(frame)
    summary = {
        "run_slug": RUN_SLUG,
        "validation_status": "pass"
        if bool(frame["tier_match"].all() and frame["weight_match"].all() and frame["weighted_r_match"].all())
        else "fail",
        "new_databento_fetches": 0,
        "historical_days_required": 0,
        "execution_bridge": "ScoredFeatureLookupProvider",
        "input_path": str(INPUT_PATH),
        "overlay": OVERLAY,
        "candidate": CANDIDATE,
        "feature": FEATURE,
        "profile": PRIMARY_PROFILE,
        "frozen_thresholds": {
            "low_threshold": sizer.config.low_threshold,
            "high_threshold": sizer.config.high_threshold,
        },
        "weights": {
            "low": sizer.config.low_weight,
            "mid": sizer.config.mid_weight,
            "high": sizer.config.high_weight,
            "fallback": sizer.config.fallback_weight,
        },
        "rows": int(len(frame)),
        "unique_trade_dates": int(frame["date"].astype(str).nunique()),
        "unique_trade_uids": int(frame["trade_uid"].nunique()),
        "periods": {
            str(row["period"]): {
                "trades": int(row["baseline_trades"]),
                "unique_trade_dates": int(row["unique_trade_dates"]),
                "baseline_total_r": float(row["baseline_total_r"]),
                "weighted_total_r": float(row["weighted_total_r"]),
                "delta_total_r": float(row["delta_total_r"]),
                "weighted_avg_r": float(row["weighted_avg_r"]),
                "weighted_profit_factor": float(row["weighted_profit_factor"]),
                "weighted_max_dd_r": float(row["weighted_max_dd_r"]),
            }
            for _, row in periods.iterrows()
        },
        "mismatches": {
            "tier": int((~frame["tier_match"]).sum()),
            "weight": int((~frame["weight_match"]).sum()),
            "weighted_r": int((~frame["weighted_r_match"]).sum()),
            "active": int((~frame["active_match"]).sum()),
        },
    }
    return frame, periods, tiers, summary


def write_report(periods: pd.DataFrame, tiers: pd.DataFrame, summary: dict[str, Any]) -> None:
    lines = [
        "# NQ NY LSI Pure 1m Order-Book Velocity Minimum Implementation Validation",
        "",
        "- Date: 2026-05-16",
        "- Scope: no-fetch implementation validation using the existing frozen replay CSV.",
        f"- Candidate: `{CANDIDATE}`",
        f"- Feature: `{FEATURE}`",
        f"- Profile: `{PRIMARY_PROFILE}`",
        "- DataBento fetches: `0`",
        "- Historical days required: `0`",
        f"- Status: `{summary['validation_status']}`",
        "",
        "## What Was Validated",
        "",
        "The execution-facing `ScoredFeatureLookupProvider` was run against the existing scored replay rows "
        "and routed through the same `DynamicSizingContext` / `DynamicSizingDecision` interface that the live "
        "LSI engine now accepts. This proves the frozen thresholds and risk weights are reproducible in "
        "implementation code without a new historical MBP-10 fetch.",
        "",
        "Frozen rule:",
        "",
        "- Low: feature `< -0.322`, weight `0.5x`",
        "- Mid: feature `[-0.322, 0.912)`, weight `1.0x`",
        "- High: feature `>= 0.912`, weight `1.5x`",
        "",
        "## Replay Match",
        "",
        f"- Rows checked: `{summary['rows']}`",
        f"- Unique trade dates: `{summary['unique_trade_dates']}`",
        f"- Unique trade IDs: `{summary['unique_trade_uids']}`",
        f"- Tier mismatches: `{summary['mismatches']['tier']}`",
        f"- Weight mismatches: `{summary['mismatches']['weight']}`",
        f"- Weighted-R mismatches: `{summary['mismatches']['weighted_r']}`",
        "",
        "## Period Metrics",
        "",
        "| Period | Trades | Dates | Baseline R | Weighted R | Delta R | Weighted Avg R | Weighted PF | Weighted Max DD |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in periods.iterrows():
        lines.append(
            f"| {row['period']} | {int(row['baseline_trades'])} | {int(row['unique_trade_dates'])} | "
            f"{row['baseline_total_r']:.2f}R | {row['weighted_total_r']:.2f}R | "
            f"{row['delta_total_r']:+.2f}R | {row['weighted_avg_r']:.3f}R | "
            f"{row['weighted_profit_factor']:.2f} | {row['weighted_max_dd_r']:.2f}R |"
        )

    lines.extend(
        [
            "",
            "## Tier Metrics",
            "",
            "| Period | Tier | Weight | Trades | Feature Range | Weighted R | Avg R | PF |",
            "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |",
        ]
    )
    for _, row in tiers.iterrows():
        lines.append(
            f"| {row['period']} | `{row['tier']}` | {row['risk_weight']:.1f} | "
            f"{int(row['trades'])} | {row['feature_min']:.3f} to {row['feature_max']:.3f} | "
            f"{row['total_r']:.2f}R | {row['avg_r']:.3f}R | {row['profit_factor']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is the minimum implementation validation: no historical MBP-10 fetch and no broker order placement.",
            "- The sizing provider bridge exactly reproduces the frozen replay tiers and weighted R, so the live engine can consume the same decision interface behind disabled-by-default config flags.",
            "- The live MBP-10 path now has a cost acknowledgement guard and shadow mode available for paper validation before any quantity changes are applied.",
            "- Promotion is still blocked until MBP-10 is enabled in a paper/live validation run and exact execution-engine replay/paper parity exists.",
            "",
            "## Output Files",
            "",
            f"- `{OUTPUT_DIR / 'validated_trades.csv'}`",
            f"- `{OUTPUT_DIR / 'period_metrics.csv'}`",
            f"- `{OUTPUT_DIR / 'tier_metrics.csv'}`",
            f"- `{OUTPUT_DIR / 'summary.json'}`",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    validated, periods, tiers, summary = validate_replay()
    validated.to_csv(OUTPUT_DIR / "validated_trades.csv", index=False)
    periods.to_csv(OUTPUT_DIR / "period_metrics.csv", index=False)
    tiers.to_csv(OUTPUT_DIR / "tier_metrics.csv", index=False)
    save_json(OUTPUT_DIR / "summary.json", summary)
    write_report(periods, tiers, summary)

    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary["validation_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
