#!/usr/bin/env python3
"""Validate execution-facing scored-feature providers for orderflow branches.

This is a no-fetch bridge check. It does not prove each branch is live-native;
it proves the frozen research rows can be replayed through the execution sizing
interface without tier, weight, or weighted-R drift.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
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
    OrderbookDynamicSizingConfig,
    OrderbookVelocityTierSizer,
    ScoredFeatureLookupProvider,
)


RUN_SLUG = "nq_lsi_orderflow_side_branch_provider_validation_20260517"
MATRIX_DIR = BACKTESTING_ROOT / "data" / "results" / "nq_lsi_broad_discretionary_challenger_matrix_20260517"
INPUT_PATH = MATRIX_DIR / "risk_tier_replay.csv"
THRESHOLDS_PATH = MATRIX_DIR / "frozen_thresholds.csv"
OUTPUT_DIR = BACKTESTING_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = (
    BACKTESTING_ROOT
    / "learnings"
    / "reports"
    / "NQ_NY_LSI_ORDERFLOW_SIDE_BRANCH_PROVIDER_VALIDATION_20260517.md"
)
PRIMARY_PROFILE = "tier_0p5_1_1p5"


@dataclass(frozen=True)
class BranchSpec:
    track: str
    candidate: str
    feature: str
    branch: str
    timeframe: str
    promotion_role: str
    exact_status: str
    directions: tuple[int, ...]


SPECS = (
    BranchSpec(
        track="pure_1m_velocity_champion",
        candidate="pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200",
        feature="confirm_last_10s_mid_velocity_ticks_per_second",
        branch="current_orderbook_survivor",
        timeframe="1m",
        promotion_role="shadow champion",
        exact_status="exact shadow pass: +9.25R vs +5.50R baseline, 0 fallbacks",
        directions=(1,),
    ),
    BranchSpec(
        track="pure_1m_liquidity_vacuum_side_branch",
        candidate="pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200",
        feature="ob_vacuum_confirm_last_10s_score",
        branch="liquidity_vacuum_book_pull",
        timeframe="1m",
        promotion_role="side research",
        exact_status="scored exact shadow pass: +7.25R vs +5.50R baseline, 0 fallbacks",
        directions=(1,),
    ),
    BranchSpec(
        track="three_minute_trapped_reversal_side_branch",
        candidate="add_3m_hourly_atr12p5_b3_a7p5",
        feature="trapped_reversal_confirm_score",
        branch="absorption_then_release",
        timeframe="3m",
        promotion_role="side research",
        exact_status="research/stress pass only; execution-engine parity not implemented",
        directions=(-1, 1),
    ),
)


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def max_drawdown(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return 0.0
    equity = clean.cumsum()
    running_peak = equity.cummax().clip(lower=0.0)
    return float((equity - running_peak).min())


def profit_factor(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    gains = float(clean[clean > 0].sum())
    losses = float(-clean[clean < 0].sum())
    if losses == 0.0:
        return float("inf") if gains > 0.0 else 0.0
    return gains / losses


def r_metrics(values: pd.Series) -> dict[str, float | int]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return {
        "trades": int(len(clean)),
        "total_r": float(clean.sum()),
        "avg_r": float(clean.mean()) if len(clean) else 0.0,
        "profit_factor": profit_factor(clean),
        "max_dd_r": max_drawdown(clean),
    }


def load_thresholds() -> pd.DataFrame:
    thresholds = pd.read_csv(THRESHOLDS_PATH)
    return thresholds.set_index(["candidate", "feature"], drop=False)


def sizer_for(spec: BranchSpec, thresholds: pd.DataFrame) -> OrderbookVelocityTierSizer:
    try:
        row = thresholds.loc[(spec.candidate, spec.feature)]
    except KeyError as exc:
        raise SystemExit(f"Missing frozen thresholds for {spec.candidate} / {spec.feature}") from exc
    config = OrderbookDynamicSizingConfig(
        feature=spec.feature,
        low_threshold=float(row["low_threshold_q33"]),
        high_threshold=float(row["high_threshold_q66"]),
        min_coverage=0.0,
        low_weight=0.5,
        mid_weight=1.0,
        high_weight=1.5,
        directions=spec.directions,
    )
    return OrderbookVelocityTierSizer(config)


def validate_spec(spec: BranchSpec, replay: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    frame = replay[
        (replay["candidate"] == spec.candidate)
        & (replay["feature"] == spec.feature)
        & (replay["weight_profile"] == PRIMARY_PROFILE)
    ].copy()
    if frame.empty:
        raise SystemExit(f"No replay rows for {spec.candidate} / {spec.feature} / {PRIMARY_PROFILE}")

    provider = ScoredFeatureLookupProvider.from_csv(
        INPUT_PATH,
        candidate=spec.candidate,
        feature=spec.feature,
        profile=PRIMARY_PROFILE,
        sizer=sizer_for(spec, thresholds),
    )
    decisions = []
    for _, row in frame.iterrows():
        decision = provider(DynamicSizingContext(
            symbol="NQ.FUT",
            direction=int(row["direction"]),
            signal_start=pd.to_datetime(row["signal_start"]).to_pydatetime(),
            config_name=spec.candidate,
            session="NQ_NY_LSI",
            entry_price=finite_float(row.get("entry_price")),
            feature=spec.feature,
        ))
        decisions.append(decision)

    frame["track"] = spec.track
    frame["promotion_role"] = spec.promotion_role
    frame["exact_status"] = spec.exact_status
    frame["computed_tier"] = [decision.tier for decision in decisions]
    frame["computed_risk_weight"] = [decision.risk_weight for decision in decisions]
    frame["computed_weighted_r"] = frame["r_multiple"].astype(float) * frame["computed_risk_weight"]
    frame["decision_reason"] = [decision.reason for decision in decisions]
    frame["tier_match"] = frame["computed_tier"] == frame["feature_tier"]
    frame["weight_match"] = (
        (frame["computed_risk_weight"].astype(float) - frame["risk_weight"].astype(float)).abs() < 1e-12
    )
    frame["weighted_r_match"] = (
        (frame["computed_weighted_r"].astype(float) - frame["weighted_r"].astype(float)).abs() < 1e-12
    )
    return frame


def build_period_metrics(validated: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (track, period), group in validated.groupby(["track", "period"], sort=False):
        baseline = r_metrics(group["r_multiple"])
        weighted = r_metrics(group["computed_weighted_r"])
        first = group.iloc[0]
        rows.append({
            "track": track,
            "period": period,
            "candidate": first["candidate"],
            "timeframe": first["timeframe"],
            "branch": first["branch"],
            "feature": first["feature"],
            "promotion_role": first["promotion_role"],
            "exact_status": first["exact_status"],
            "rows": int(len(group)),
            "tier_mismatches": int((~group["tier_match"]).sum()),
            "weight_mismatches": int((~group["weight_match"]).sum()),
            "weighted_r_mismatches": int((~group["weighted_r_match"]).sum()),
            **{f"baseline_{key}": value for key, value in baseline.items()},
            **{f"weighted_{key}": value for key, value in weighted.items()},
            "delta_total_r": float(weighted["total_r"] - baseline["total_r"]),
            "delta_avg_r": float(weighted["avg_r"] - baseline["avg_r"]),
        })
    return pd.DataFrame(rows)


def build_summary(validated: pd.DataFrame, periods: pd.DataFrame) -> dict[str, Any]:
    return {
        "run_slug": RUN_SLUG,
        "new_databento_fetches": 0,
        "input_path": str(INPUT_PATH),
        "primary_profile": PRIMARY_PROFILE,
        "status": "pass"
        if bool(validated["tier_match"].all() and validated["weight_match"].all() and validated["weighted_r_match"].all())
        else "fail",
        "rows": int(len(validated)),
        "tracks": {
            str(track): {
                "rows": int(len(group)),
                "tier_mismatches": int((~group["tier_match"]).sum()),
                "weight_mismatches": int((~group["weight_match"]).sum()),
                "weighted_r_mismatches": int((~group["weighted_r_match"]).sum()),
            }
            for track, group in validated.groupby("track", sort=False)
        },
        "periods": periods.to_dict(orient="records"),
    }


def write_report(periods: pd.DataFrame, summary: dict[str, Any]) -> None:
    if summary["status"] == "pass":
        match_lines = [
            "- Tier mismatches: `0`",
            "- Weight mismatches: `0`",
            "- Weighted-R mismatches: `0`",
        ]
    else:
        match_lines = ["- Tier/weight mismatches found; inspect output CSV."]

    lines = [
        "# NQ NY LSI Orderflow Side-Branch Provider Validation",
        "",
        "- Date: 2026-05-17",
        "- Scope: no-fetch execution-facing provider validation for the champion and two side branches.",
        "- DataBento fetches: `0`",
        f"- Profile: `{PRIMARY_PROFILE}`",
        f"- Status: `{summary['status']}`",
        "",
        "## Provider Match",
        "",
        f"- Rows checked: `{summary['rows']}`",
        *match_lines,
        "",
        "## Period Read",
        "",
        "| Track | Period | Trades | Baseline R | Weighted R | Delta R | Weighted Avg | PF | Max DD | Exact Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in periods.iterrows():
        lines.append(
            f"| `{row['track']}` | `{row['period']}` | {int(row['baseline_trades'])} | "
            f"{row['baseline_total_r']:.2f}R | {row['weighted_total_r']:.2f}R | "
            f"{row['delta_total_r']:+.2f}R | {row['weighted_avg_r']:.3f}R | "
            f"{row['weighted_profit_factor']:.2f} | {row['weighted_max_dd_r']:.2f}R | "
            f"{row['exact_status']} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- Pure 1m velocity remains the shadow champion because it has live-engine exact shadow support and the best exact weighted R.",
        "- Pure 1m liquidity-vacuum has now cleared scored exact-shadow replay, but still needs a live-native MBP-10 depth/microprice calculator before it can shadow from streaming data.",
        "- 3m trapped-reversal remains research-only. The provider bridge can reproduce its frozen tiers, but execution parity for the 3m candidate and a live/replay feature calculator are still required.",
        "",
        "## Output Files",
        "",
        f"- `{OUTPUT_DIR / 'validated_trades.csv'}`",
        f"- `{OUTPUT_DIR / 'period_metrics.csv'}`",
        f"- `{OUTPUT_DIR / 'summary.json'}`",
    ])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    replay = pd.read_csv(INPUT_PATH)
    thresholds = load_thresholds()
    validated = pd.concat(
        [validate_spec(spec, replay, thresholds) for spec in SPECS],
        ignore_index=True,
    )
    periods = build_period_metrics(validated)
    summary = build_summary(validated, periods)

    validated.to_csv(OUTPUT_DIR / "validated_trades.csv", index=False)
    periods.to_csv(OUTPUT_DIR / "period_metrics.csv", index=False)
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    write_report(periods, summary)
    print(json.dumps(summary, indent=2, default=str), flush=True)
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
