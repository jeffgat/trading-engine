#!/usr/bin/env python3
"""Run round-2 NQ prop regime-specialist research.

Round 2 keeps the round-1 regime model fixed and focuses on:
- paper-trade handling for the bull winner
- context-gated bear continuation variants
- a narrow sideways VWAP refinement around the round-1 winner
- low-confidence day routing as a no-trade ablation
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, replace
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (
    DEFAULT_HOLDOUT_START,
    PropFirmProfile,
    apply_bull_hh_hl_vwap_gate,
    apply_structure_vwap_gate,
    build_prop_scorecard,
    build_nq_ny_regime_calendar,
    build_regime_confusion_log,
    build_structure_vwap_signals,
    build_yearly_regime_summary,
    evaluate_specialist,
    filter_trades_by_low_confidence,
    simulate_account_attempts,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.optimize.parallel_vwap import run_vwap_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.vwap_config import default_vwap_config, with_vwap_overrides


OUTPUT_DIR = ROOT / "data" / "results" / "nq_prop_regime_specialists_round2"
LOW_CONF_POLICIES = {
    "all_days": True,
    "no_low_confidence": False,
}
BEAR_GATES = (
    "hh_hl_2_vwap",
    "hh_hl_3_vwap",
    "any2of3_vwap_d5",
    "score_gte_2",
    "score_eq_3",
    "regime_2d_vwap",
    "regime_2of3_vwap",
    "pullback_holds_vwap",
    "pullback_holds_vwap_orb",
)


def make_nq_ny_long_r11_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="12:00",
        flat_start="15:30",
        flat_end="16:00",
        stop_atr_pct=7.0,
        min_gap_atr_pct=2.5,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.4,
        atr_length=12,
        impulse_close_filter=False,
        excluded_days=(4,),
        name="NQ NY Cont Long R11 Final",
        notes="Round-2 bull paper-trade anchor.",
    )


def make_nq_ny_short_v2_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:55",
        entry_start="09:55",
        entry_end="11:00",
        flat_start="11:00",
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=0.0,
        stop_orb_pct=17.0,
        min_gap_orb_pct=5.0,
        min_stop_points=10.0,
        min_tp1_points=10.0,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=2.0,
        tp1_ratio=0.3,
        atr_length=14,
        impulse_close_filter=False,
        excluded_days=(0,),
        name="NQ NY Short v2",
        notes="Round-2 bear context-gate anchor.",
    )


def build_sideways_round2_candidates():
    """Small refinement grid centered on the round-1 VWAP winner."""

    base = default_vwap_config(NQ)
    configs = []
    for deviation, rr, tp1, stop_atr in product(
        [15.0, 20.0, 25.0],
        [1.75, 2.0, 2.25],
        [0.3, 0.5],
        [7.5, 10.0],
    ):
        cfg = with_vwap_overrides(
            base,
            rr=rr,
            tp1_ratio=tp1,
            direction_filter="long",
            ny_deviation_atr_pct=deviation,
            ny_stop_atr_pct=stop_atr,
            ny_rejection_mode="pinbar",
            ny_min_wick_atr_pct=10.0,
            ny_max_body_atr_pct=5.0,
        )
        cfg = replace(
            cfg,
            name=(
                f"NQ NY VWAP R2 dev{deviation:.0f}_rr{rr:.2f}_tp1{tp1:.2f}_"
                f"stop{stop_atr:.1f}_pinbar_long"
            ),
            notes="Round-2 sideways refinement around round-1 winner.",
        )
        configs.append(cfg)
    return configs


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def _specialization_value(value: float | str | None) -> float:
    if value == "inf":
        return float("inf")
    if value is None:
        return float("-inf")
    return float(value)


def _candidate_sort_key(record: dict) -> tuple:
    readout = record["readout"]
    scorecard = record["scorecard"]
    in_avg_r = float(readout["in_regime"].get("avg_r") or 0.0)
    total_trades = int(readout["full_history"].get("total_trades") or 0)
    ev = float(scorecard.get("ev_per_attempt") or 0.0)
    payout_rate = float(scorecard.get("first_payout_rate") or 0.0)
    return (
        bool(readout["survives_round1"]),
        bool(readout["passes_round1"]["specialization_ratio_gte_1_5"]),
        _specialization_value(readout["specialization_ratio"]),
        in_avg_r,
        ev,
        payout_rate,
        total_trades,
    )


def _evaluate_candidate(
    *,
    specialist_name: str,
    target_regime: str,
    family: str,
    source_name: str,
    route_policy: str,
    include_low_confidence: bool,
    trades: list,
    regime_calendar: pd.DataFrame,
    holdout_start: str,
    trading_dates: list[str],
    profile: PropFirmProfile,
    risk_per_r_usd: float,
    extra: dict | None = None,
) -> dict:
    eval_trades = filter_trades_by_low_confidence(
        trades,
        regime_calendar,
        include_low_confidence=include_low_confidence,
    )
    readout = evaluate_specialist(
        specialist_name=specialist_name,
        target_regime=target_regime,
        trades=eval_trades,
        regime_calendar=regime_calendar,
        holdout_start=holdout_start,
    )
    outcomes = simulate_account_attempts(
        specialist_name=specialist_name,
        trades=eval_trades,
        trading_dates=trading_dates,
        profile=profile,
        risk_per_r_usd=risk_per_r_usd,
    )
    scorecard = build_prop_scorecard(outcomes, profile)

    record = {
        "specialist_name": specialist_name,
        "target_regime": target_regime,
        "family": family,
        "source_name": source_name,
        "route_policy": route_policy,
        "include_low_confidence": include_low_confidence,
        "risk_per_r_usd": risk_per_r_usd,
        "readout": readout,
        "scorecard": scorecard,
        "outcomes": outcomes,
    }
    if extra:
        record.update(extra)
    return record


def _records_to_frame(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        readout = record["readout"]
        scorecard = record["scorecard"]
        rows.append(
            {
                "specialist_name": record["specialist_name"],
                "target_regime": record["target_regime"],
                "family": record["family"],
                "source_name": record["source_name"],
                "route_policy": record["route_policy"],
                "include_low_confidence": record["include_low_confidence"],
                "survives_round1": readout["survives_round1"],
                "specialization_ratio": readout["specialization_ratio"],
                "specialization_ratio_numeric": _specialization_value(readout["specialization_ratio"]),
                "in_regime_avg_r": readout["in_regime"]["avg_r"],
                "out_of_regime_avg_r": readout["out_of_regime"]["avg_r"],
                "in_regime_trades": readout["in_regime"]["total_trades"],
                "full_history_trades": readout["full_history"]["total_trades"],
                "holdout_in_regime_avg_r": readout["holdout_in_regime"]["avg_r"],
                "ev_per_attempt": scorecard["ev_per_attempt"],
                "first_payout_rate": scorecard["first_payout_rate"],
                "pass_rate": scorecard["pass_rate"],
                "average_days_to_payout": scorecard["average_days_to_payout"],
            }
        )
    return pd.DataFrame(rows).sort_values(
        by=[
            "survives_round1",
            "specialization_ratio_numeric",
            "in_regime_avg_r",
            "ev_per_attempt",
            "first_payout_rate",
            "full_history_trades",
        ],
        ascending=[False, False, False, False, False, False],
    )


def _top_by_regime(records: list[dict], require_survivor: bool) -> list[dict]:
    best: list[dict] = []
    for regime in ("bull", "bear", "sideways"):
        regime_records = [r for r in records if r["target_regime"] == regime]
        if require_survivor:
            regime_records = [r for r in regime_records if r["readout"]["survives_round1"]]
        if not regime_records:
            continue
        best.append(max(regime_records, key=_candidate_sort_key))
    return best


def _record_to_json(record: dict) -> dict:
    extra = {
        key: value
        for key, value in record.items()
        if key not in {"readout", "scorecard", "outcomes"}
    }
    extra["readout"] = record["readout"]
    extra["scorecard"] = record["scorecard"]
    return extra


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--vwap-workers", type=int, default=4)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Prop Regime Specialists — Round 2")
    print("=" * 72)
    print(f"Output dir: {output_dir}")

    t0 = time.time()
    print("\nLoading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file, start=args.start, end=args.end)
    try:
        df_1m = load_1m_for_5m(NQ.data_file, start=args.start, end=args.end)
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file, start=args.start, end=args.end)
    print(
        f"  5m={len(df_5m):,} | "
        f"1m={len(df_1m) if df_1m is not None else 0:,} | "
        f"1s={len(df_1s):,} "
        f"[{time.time() - t0:.1f}s]"
    )

    print("\nBuilding regime calendar...", flush=True)
    regime_calendar = build_nq_ny_regime_calendar(df_5m, start_date=args.start, end_date=args.end)
    confusion_log = build_regime_confusion_log(regime_calendar)
    yearly_summary = build_yearly_regime_summary(regime_calendar)
    trading_dates_by_policy = {
        policy: trading_dates_from_calendar(regime_calendar, include_low_confidence=include_low_conf)
        for policy, include_low_conf in LOW_CONF_POLICIES.items()
    }
    print(
        f"  Calendar rows={len(regime_calendar):,} | "
        f"low-confidence={len(confusion_log):,}"
    )

    profile = PropFirmProfile()
    records: list[dict] = []

    print("\nEvaluating bull paper-trade anchor...", flush=True)
    bull_config = make_nq_ny_long_r11_config()
    bull_trades = run_backtest(
        df_5m,
        bull_config,
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    bull_trades = apply_dow_filter(bull_trades, set(bull_config.excluded_days))
    bull_trades = apply_bull_hh_hl_vwap_gate(bull_trades, df_5m, bull_config.sessions[0])

    for policy, include_low_conf in LOW_CONF_POLICIES.items():
        records.append(
            _evaluate_candidate(
                specialist_name=f"nq_ny_bull_long_r11_hh_hl_vwap__{policy}",
                target_regime="bull",
                family="continuation_long_context_gated",
                source_name="round1_bull_winner",
                route_policy=policy,
                include_low_confidence=include_low_conf,
                trades=bull_trades,
                regime_calendar=regime_calendar,
                holdout_start=args.holdout_start,
                trading_dates=trading_dates_by_policy[policy],
                profile=profile,
                risk_per_r_usd=bull_config.risk_usd,
            )
        )

    print("\nEvaluating bear context-gated variants...", flush=True)
    bear_config = make_nq_ny_short_v2_config()
    bear_trades = run_backtest(
        df_5m,
        bear_config,
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    bear_trades = apply_dow_filter(bear_trades, set(bear_config.excluded_days))
    bear_signals = build_structure_vwap_signals(df_5m, bear_config.sessions[0], bear_config.atr_length)

    for policy, include_low_conf in LOW_CONF_POLICIES.items():
        records.append(
            _evaluate_candidate(
                specialist_name=f"nq_ny_bear_short_v2__baseline__{policy}",
                target_regime="bear",
                family="continuation_short_baseline",
                source_name="baseline",
                route_policy=policy,
                include_low_confidence=include_low_conf,
                trades=bear_trades,
                regime_calendar=regime_calendar,
                holdout_start=args.holdout_start,
                trading_dates=trading_dates_by_policy[policy],
                profile=profile,
                risk_per_r_usd=bear_config.risk_usd,
            )
        )

    for gate_name in BEAR_GATES:
        gated_trades = apply_structure_vwap_gate(bear_trades, bear_signals, gate_name)
        for policy, include_low_conf in LOW_CONF_POLICIES.items():
            records.append(
                _evaluate_candidate(
                    specialist_name=f"nq_ny_bear_short_v2__{gate_name}__{policy}",
                    target_regime="bear",
                    family="continuation_short_context_gated",
                    source_name=gate_name,
                    route_policy=policy,
                    include_low_confidence=include_low_conf,
                    trades=gated_trades,
                    regime_calendar=regime_calendar,
                    holdout_start=args.holdout_start,
                    trading_dates=trading_dates_by_policy[policy],
                    profile=profile,
                    risk_per_r_usd=bear_config.risk_usd,
                )
            )

    print("\nRunning focused sideways VWAP sweep...", flush=True)
    sideways_configs = build_sideways_round2_candidates()
    vwap_results = run_vwap_sweep(
        df_5m,
        sideways_configs,
        n_workers=max(1, args.vwap_workers),
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
    )
    for config, trades in vwap_results:
        metrics = compute_metrics(trades)
        for policy, include_low_conf in LOW_CONF_POLICIES.items():
            records.append(
                _evaluate_candidate(
                    specialist_name=(
                        f"nq_ny_sideways_vwap__{config.name.lower().replace(' ', '_')}__{policy}"
                    ),
                    target_regime="sideways",
                    family="vwap_reversion_refined",
                    source_name=config.name,
                    route_policy=policy,
                    include_low_confidence=include_low_conf,
                    trades=trades,
                    regime_calendar=regime_calendar,
                    holdout_start=args.holdout_start,
                    trading_dates=trading_dates_by_policy[policy],
                    profile=profile,
                    risk_per_r_usd=config.risk_usd,
                    extra={
                        "config_name": config.name,
                        "full_history_avg_r": (
                            None if metrics.get("avg_r") is None else float(metrics["avg_r"])
                        ),
                    },
                )
            )

    ranking_df = _records_to_frame(records)
    shortlist_records = _top_by_regime(records, require_survivor=True)
    near_miss_records = _top_by_regime(records, require_survivor=False)

    ranking_df.to_csv(output_dir / "specialist_ranking.csv", index=False)
    yearly_summary.to_csv(output_dir / "regime_yearly_summary.csv", index=False)
    regime_calendar.to_csv(output_dir / "regime_calendar.csv", index=False)
    confusion_log.to_csv(output_dir / "confusion_log.csv", index=False)

    pd.DataFrame(
        [
            {
                "target_regime": r["target_regime"],
                "specialist_name": r["specialist_name"],
                "route_policy": r["route_policy"],
                "source_name": r["source_name"],
                "ev_per_attempt": r["scorecard"]["ev_per_attempt"],
                "first_payout_rate": r["scorecard"]["first_payout_rate"],
                "specialization_ratio": r["readout"]["specialization_ratio"],
            }
            for r in shortlist_records
        ]
    ).to_csv(output_dir / "paper_trade_shortlist.csv", index=False)

    write_json(
        output_dir / "selected_candidates.json",
        {
            "paper_trade_shortlist": [_record_to_json(r) for r in shortlist_records],
            "top_candidate_per_regime": [_record_to_json(r) for r in near_miss_records],
        },
    )
    write_json(
        output_dir / "prop_scorecards.json",
        {record["specialist_name"]: record["scorecard"] for record in records},
    )
    write_json(
        output_dir / "specialist_readouts.json",
        {record["specialist_name"]: record["readout"] for record in records},
    )

    low_conf_summary_rows = []
    for regime in ("bull", "bear", "sideways"):
        regime_records = [r for r in records if r["target_regime"] == regime]
        for policy in LOW_CONF_POLICIES:
            policy_records = [r for r in regime_records if r["route_policy"] == policy]
            if not policy_records:
                continue
            best = max(policy_records, key=_candidate_sort_key)
            low_conf_summary_rows.append(
                {
                    "target_regime": regime,
                    "route_policy": policy,
                    "best_candidate": best["specialist_name"],
                    "survives_round1": best["readout"]["survives_round1"],
                    "specialization_ratio": best["readout"]["specialization_ratio"],
                    "in_regime_avg_r": best["readout"]["in_regime"]["avg_r"],
                    "ev_per_attempt": best["scorecard"]["ev_per_attempt"],
                }
            )
    pd.DataFrame(low_conf_summary_rows).to_csv(output_dir / "low_confidence_policy_summary.csv", index=False)

    summary_lines = [
        "# NQ Prop Regime Specialists — Round 2",
        "",
        "## Regime Rules",
        "",
        "- Reused round-1 rules unchanged to avoid moving the specialist goalposts.",
        "- `bull`: prior close >= +0.5% vs SMA20 and prior 5d return > 0.",
        "- `bear`: prior close <= -0.5% vs SMA20 and prior 5d return < 0.",
        "- `sideways`: everything else after warmup.",
        "- `low_confidence`: abs(close_vs_sma20) < 0.25% or abs(ret_5d) < 0.5%.",
        "",
        "## Round-2 Search Scope",
        "",
        f"- Bear gates tested: `{len(BEAR_GATES)}` context filters on the short continuation baseline.",
        f"- Sideways configs tested: `{len(sideways_configs)}` focused VWAP refinements around the round-1 winner.",
        f"- Low-confidence days in calendar: `{len(confusion_log)}` of `{len(regime_calendar)}` total rows.",
        "",
        "## Paper-Trade Shortlist",
        "",
    ]
    if not shortlist_records:
        summary_lines.append("- No candidate cleared the specialist survival rules in round 2.")
    else:
        for record in shortlist_records:
            summary_lines.append(
                f"- `{record['target_regime']}`: `{record['specialist_name']}` | "
                f"route `{record['route_policy']}` | EV/attempt `{record['scorecard']['ev_per_attempt']}` | "
                f"specialization `{record['readout']['specialization_ratio']}`"
            )

    summary_lines.extend(
        [
            "",
            "## Best Candidate Per Regime",
            "",
        ]
    )
    for record in near_miss_records:
        summary_lines.append(
            f"- `{record['target_regime']}`: `{record['specialist_name']}` | "
            f"survives `{record['readout']['survives_round1']}` | "
            f"ratio `{record['readout']['specialization_ratio']}` | "
            f"EV/attempt `{record['scorecard']['ev_per_attempt']}`"
        )

    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
