#!/usr/bin/env python3
"""Bailey-aware challenger workflow for the NQ 3x3 regime framework.

Implements a fixed first wave:
1. Baseline
2. Three trend challengers
3. Three volatility challengers
4. One combo finalist built only after Stage A promotion

Selection is done on pre-holdout data only. Holdout is revealed once for:
- baseline
- best trend challenger
- best vol challenger
- combo finalist
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.regime_research import (
    REGIME_RESEARCH_HOLDOUT_END,
    REGIME_RESEARCH_HOLDOUT_START,
    PRE_HOLDOUT_END,
    RegimeChallengerSpec,
    TrendFeatureSpec,
    TrialCounter,
    VolFeatureSpec,
    _filled_trades,
    _metrics_snapshot,
    _regime_lookup,
    _serialize_challenger_spec,
    attribute_strategy_by_regime,
    build_combo_challenger_spec,
    build_stage_a_scoreboard,
    compute_bucket_metrics,
    evaluate_challenger_stage_a,
    make_baseline_challenger_spec,
    run_regime_holdout,
    select_challenger_finalists,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

OUTPUT_DIR = ROOT / "data" / "results" / "nq_regime_challengers"


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
        name="NQ NY Cont Long R11",
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
        tp1_ratio=0.5,
        atr_length=14,
        impulse_close_filter=False,
        excluded_days=(0,),
        name="NQ NY Short v2",
    )


def make_nq_asia_r9_config() -> StrategyConfig:
    session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",
        entry_start="20:15",
        entry_end="22:30",
        flat_start="04:00",
        flat_end="07:00",
        stop_atr_pct=4.0,
        min_gap_atr_pct=0.90,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.6,
        atr_length=5,
        impulse_close_filter=True,
        name="NQ Asia Cont Long R9",
    )


def _make_lsi_session() -> SessionConfig:
    return SessionConfig(
        name="NY",
        rth_start="09:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )


def make_lsi_close_both() -> StrategyConfig:
    return StrategyConfig(
        sessions=(_make_lsi_session(),),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=1.5,
        tp1_ratio=0.7,
        atr_length=14,
        lsi_n_left=10,
        lsi_n_right=65,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=3,
        lsi_stop_mode="absolute",
        lsi_entry_mode="close",
        excluded_days=(2, 3),
        name="NQ NY LSI Close Both",
    )


def make_lsi_fvg_limit_both() -> StrategyConfig:
    return StrategyConfig(
        sessions=(_make_lsi_session(),),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=3.0,
        tp1_ratio=0.4,
        atr_length=10,
        lsi_n_left=10,
        lsi_n_right=120,
        lsi_fvg_window_left=30,
        lsi_fvg_window_right=15,
        lsi_stop_mode="absolute",
        lsi_entry_mode="fvg_limit",
        excluded_days=(2, 3),
        name="NQ NY LSI FVGLimit Both",
    )


BENCHMARK_STRATEGIES = {
    "nq_ny_long_r11": {"config_fn": make_nq_ny_long_r11_config, "excluded_days": {4}},
    "nq_ny_short_v2": {"config_fn": make_nq_ny_short_v2_config, "excluded_days": {0}},
    "nq_asia_r9": {"config_fn": make_nq_asia_r9_config, "excluded_days": {1}},
    "lsi_close_both": {"config_fn": make_lsi_close_both},
    "lsi_fvg_limit_both": {"config_fn": make_lsi_fvg_limit_both},
}


def build_first_wave_challenger_specs() -> list[RegimeChallengerSpec]:
    baseline = make_baseline_challenger_spec(
        trend_sma_threshold=0.005,
        trend_ret5d_threshold=0.0,
        vol_method="tercile",
    )

    return [
        baseline,
        RegimeChallengerSpec(
            name="trend_ema20",
            family="trend_only",
            trend=TrendFeatureSpec(
                name="close_vs_ema20",
                feature_col="close_vs_ema20",
                formula="close / EMA20 - 1",
                bull_threshold=0.005,
                bear_threshold=-0.005,
                ret5d_threshold=0.0,
            ),
            vol=baseline.vol,
            description="Trend challenger: replace SMA20 with EMA20.",
        ),
        RegimeChallengerSpec(
            name="trend_ema10_20_spread",
            family="trend_only",
            trend=TrendFeatureSpec(
                name="ema10_20_spread",
                feature_col="ema10_20_spread",
                formula="EMA10 / EMA20 - 1",
                bull_threshold=0.0025,
                bear_threshold=-0.0025,
                ret5d_threshold=0.0,
            ),
            vol=baseline.vol,
            description="Trend challenger: EMA10/EMA20 spread with ret_5d confirmation.",
        ),
        RegimeChallengerSpec(
            name="trend_lr20_slope",
            family="trend_only",
            trend=TrendFeatureSpec(
                name="lr20_slope_norm",
                feature_col="lr20_slope_norm",
                formula="20-day linear-regression slope normalized by current close",
                bull_threshold=0.0010,
                bear_threshold=-0.0010,
                ret5d_threshold=0.0,
            ),
            vol=baseline.vol,
            description="Trend challenger: normalized 20-day regression slope.",
        ),
        RegimeChallengerSpec(
            name="vol_ewma21",
            family="vol_only",
            trend=baseline.trend,
            vol=VolFeatureSpec(
                name="ewma_vol_21d",
                feature_col="ewma_vol_21d",
                formula="EWMA variance of daily log returns with lambda=0.94, annualized",
                bucketing_method="tercile",
            ),
            description="Vol challenger: EWMA realized volatility.",
        ),
        RegimeChallengerSpec(
            name="vol_atr20_pct",
            family="vol_only",
            trend=baseline.trend,
            vol=VolFeatureSpec(
                name="atr20_pct",
                feature_col="atr20_pct",
                formula="ATR20 / close",
                bucketing_method="tercile",
            ),
            description="Vol challenger: normalized ATR20.",
        ),
        RegimeChallengerSpec(
            name="vol_yang_zhang21",
            family="vol_only",
            trend=baseline.trend,
            vol=VolFeatureSpec(
                name="yang_zhang_21d",
                feature_col="yang_zhang_21d",
                formula="21-day Yang-Zhang volatility, annualized",
                bucketing_method="tercile",
            ),
            description="Vol challenger: Yang-Zhang daily volatility.",
        ),
    ]


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def write_markdown(path: Path, content: str) -> None:
    path.write_text(content)


def _serialize_stage_a_result(result: dict) -> dict:
    return {
        "name": result["name"],
        "family": result["family"],
        "challenger_spec": result["challenger_spec"],
        "audit": result["audit"],
        "walkforward": result["walkforward"],
        "pre_holdout_vol_thresholds": result["pre_holdout_vol_thresholds"],
        "selection_metrics": result["selection_metrics"],
        "stage_a_only": result["stage_a_only"],
        "holdout_excluded": result["holdout_excluded"],
        "calendar_rows": int(len(result["calendar"])),
    }


def _subset_trades(
    trades: list,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list:
    return [
        trade
        for trade in trades
        if (start_date is None or trade.date >= start_date)
        and (end_date is None or trade.date <= end_date)
    ]


def _make_avoidance_gate(regime_calendar: pd.DataFrame, blocked_buckets: set[str]):
    lookup = _regime_lookup(regime_calendar, "combined_regime")

    def gate(trades: list) -> list:
        return [
            trade
            for trade in trades
            if trade.exit_type == EXIT_NO_FILL or lookup.get(trade.date) not in blocked_buckets
        ]

    return gate


def _evaluate_gate_metrics(
    baseline_trades: list,
    gated_trades: list,
    holdout_start: str,
    holdout_end: str,
) -> dict:
    pre_holdout_end = (pd.Timestamp(holdout_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    baseline_pre = _subset_trades(baseline_trades, end_date=pre_holdout_end)
    gated_pre = _subset_trades(gated_trades, end_date=pre_holdout_end)
    baseline_holdout = _subset_trades(baseline_trades, start_date=holdout_start, end_date=holdout_end)
    gated_holdout = _subset_trades(gated_trades, start_date=holdout_start, end_date=holdout_end)

    return {
        "overall": {
            "baseline_filled_trades": len(_filled_trades(baseline_trades)),
            "gated_filled_trades": len(_filled_trades(gated_trades)),
            "baseline_metrics": _metrics_snapshot(compute_metrics(baseline_trades)),
            "gated_metrics": _metrics_snapshot(compute_metrics(gated_trades)),
        },
        "pre_holdout": {
            "baseline_filled_trades": len(_filled_trades(baseline_pre)),
            "gated_filled_trades": len(_filled_trades(gated_pre)),
            "baseline_metrics": _metrics_snapshot(compute_metrics(baseline_pre)),
            "gated_metrics": _metrics_snapshot(compute_metrics(gated_pre)),
        },
        "holdout": {
            "baseline_filled_trades": len(_filled_trades(baseline_holdout)),
            "gated_filled_trades": len(_filled_trades(gated_holdout)),
            "baseline_metrics": _metrics_snapshot(compute_metrics(baseline_holdout)),
            "gated_metrics": _metrics_snapshot(compute_metrics(gated_holdout)),
        },
    }


def run_benchmark_suite(
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame | None,
    df_1s: pd.DataFrame | None,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, list]:
    trades_by_strategy: dict[str, list] = {}
    for strategy_name, strategy_info in BENCHMARK_STRATEGIES.items():
        config = strategy_info["config_fn"]()
        trades = run_backtest(
            df_5m,
            config,
            start_date=start_date,
            end_date=end_date,
            df_1m=df_1m,
            df_1s=df_1s,
        )
        excluded_days = strategy_info.get("excluded_days")
        if excluded_days:
            trades = apply_dow_filter(trades, excluded_days)
        trades_by_strategy[strategy_name] = trades
    return trades_by_strategy


def freeze_avoidance_buckets(
    attributions: dict[str, pd.DataFrame],
    max_buckets: int = 2,
    min_trade_count: int = 25,
) -> dict:
    frames = []
    for strategy_name, attr_df in attributions.items():
        if attr_df.empty:
            continue
        pre = attr_df[attr_df["period"] == "pre_holdout"].copy()
        if pre.empty:
            continue
        pre["strategy_name"] = strategy_name
        frames.append(pre)

    if not frames:
        return {
            "blocked_buckets": [],
            "selection_basis": "No pre-holdout attribution data available.",
            "aggregate_bucket_metrics": [],
        }

    combined = pd.concat(frames, ignore_index=True)
    bucket_metrics = compute_bucket_metrics(combined, "combined_regime")
    bucket_metrics = bucket_metrics[
        bucket_metrics["bucket"].astype(str).str.endswith(("_low_vol", "_medium_vol", "_high_vol"))
    ].copy()
    eligible = bucket_metrics[
        (bucket_metrics["trade_count"] >= min_trade_count)
        & (bucket_metrics["avg_r"] < 0)
    ].copy()
    if eligible.empty:
        blocked_buckets: list[str] = []
    else:
        eligible = eligible.sort_values(
            ["avg_r", "total_r", "trade_count"],
            ascending=[True, True, False],
        )
        blocked_buckets = eligible.head(max_buckets)["bucket"].astype(str).tolist()

    return {
        "blocked_buckets": blocked_buckets,
        "selection_basis": (
            "Pre-holdout only. Buckets frozen before holdout reveal by worst aggregate avg_r, "
            f"subject to trade_count >= {min_trade_count}."
        ),
        "aggregate_bucket_metrics": bucket_metrics.to_dict(orient="records"),
    }


def evaluate_downstream_usefulness(
    finalist_name: str,
    regime_calendar: pd.DataFrame,
    benchmark_trades: dict[str, list],
    holdout_start: str,
    holdout_end: str,
) -> dict:
    attributions = {
        strategy_name: attribute_strategy_by_regime(trades, regime_calendar, holdout_start)
        for strategy_name, trades in benchmark_trades.items()
    }
    freeze = freeze_avoidance_buckets(attributions)
    blocked_buckets = set(freeze["blocked_buckets"])
    gate = _make_avoidance_gate(regime_calendar, blocked_buckets)

    strategy_results: dict[str, dict] = {}
    aggregate_holdout_delta = 0.0
    aggregate_pre_delta = 0.0

    for strategy_name, trades in benchmark_trades.items():
        gated_trades = gate(trades) if blocked_buckets else list(trades)
        metrics = _evaluate_gate_metrics(trades, gated_trades, holdout_start, holdout_end)
        pre_delta = (
            float(metrics["pre_holdout"]["gated_metrics"].get("total_r") or 0.0)
            - float(metrics["pre_holdout"]["baseline_metrics"].get("total_r") or 0.0)
        )
        holdout_delta = (
            float(metrics["holdout"]["gated_metrics"].get("total_r") or 0.0)
            - float(metrics["holdout"]["baseline_metrics"].get("total_r") or 0.0)
        )
        aggregate_pre_delta += pre_delta
        aggregate_holdout_delta += holdout_delta
        strategy_results[strategy_name] = {
            "gate_metrics": metrics,
            "pre_holdout_total_r_delta": round(pre_delta, 4),
            "holdout_total_r_delta": round(holdout_delta, 4),
            "attribution_rows": int(len(attributions[strategy_name])),
        }

    return {
        "finalist_name": finalist_name,
        "blocked_buckets": freeze["blocked_buckets"],
        "bucket_freeze": freeze,
        "strategy_results": strategy_results,
        "aggregate_pre_holdout_total_r_delta": round(aggregate_pre_delta, 4),
        "aggregate_holdout_total_r_delta": round(aggregate_holdout_delta, 4),
    }


def format_finalist_memo(
    stage_a_scoreboard: dict,
    selection: dict,
    stage_a_results: dict[str, dict],
    combo_spec: RegimeChallengerSpec | None,
    trial_counter: TrialCounter,
) -> str:
    lines = [
        "# NQ Regime Challenger Finalist Memo",
        "",
        "## Guardrails",
        "",
        f"- Holdout reserved: {REGIME_RESEARCH_HOLDOUT_START} to {REGIME_RESEARCH_HOLDOUT_END}",
        "- Ranking used pre-holdout Stage A metrics only.",
        "- Bailey posture: PBO/DSR not implemented here; selection remains heuristic with explicit trial tracking.",
        "",
        "## Stage A Scoreboard",
        "",
    ]

    for row in stage_a_scoreboard["rows"]:
        lines.append(
            f"- {row['name']} [{row['family']}]: "
            f"drift={row['threshold_drift_score']:.6f}, "
            f"agreement={row['mean_label_agreement']:.4f}, "
            f"min_bucket_share={row['min_bucket_share']:.4f}, "
            f"min_bucket_days={row['min_bucket_days']}, "
            f"min_bucket_episodes={row['min_bucket_episodes']}, "
            f"ambiguity={row['ambiguity_rate']:.4f}, "
            f"year_concentration={row['distribution_concentration']:.4f}"
        )

    lines.extend(
        [
            "",
            "## Finalists",
            "",
            f"- Baseline anchor: {selection['baseline_name']}",
            f"- Best trend challenger: {selection['best_trend_name']}",
            f"- Best vol challenger: {selection['best_vol_name']}",
            f"- Combo finalist: {combo_spec.name if combo_spec is not None else 'none'}",
            "",
            "## Rejections",
            "",
        ]
    )

    rejected_rows = [row for row in selection["ranked"] if row["rejected"]]
    if rejected_rows:
        for row in rejected_rows:
            lines.append(f"- {row['name']}: {', '.join(row['rejection_reasons'])}")
    else:
        lines.append("- No challengers were rejected by the Stage A hard filters.")

    lines.extend(
        [
            "",
            "## Trial Count",
            "",
            f"```text\n{trial_counter.summary()}\n```",
        ]
    )

    return "\n".join(lines)


def format_holdout_memo(
    holdout_results: dict[str, dict],
    downstream_results: dict[str, dict],
) -> str:
    lines = [
        "# NQ Regime Challenger Holdout Memo",
        "",
        "Holdout was revealed once after finalist freeze. No new challengers were created afterward.",
        "",
    ]

    for name, result in holdout_results.items():
        lines.append(f"## {name}")
        lines.append("")
        lines.append(
            f"- Holdout days: {result['holdout_days']} | ambiguity entries: {result['holdout_ambiguity_count']}"
        )

        biggest_shifts = sorted(
            result["distribution_diff"].items(),
            key=lambda item: abs(item[1]["diff"]),
            reverse=True,
        )[:3]
        if biggest_shifts:
            lines.append("- Largest distribution shifts:")
            for bucket, diff in biggest_shifts:
                lines.append(
                    f"  - {bucket}: pre={diff['pre_holdout_pct']:.4f}, "
                    f"holdout={diff['holdout_pct']:.4f}, diff={diff['diff']:+.4f}"
                )

        downstream = downstream_results.get(name, {})
        blocked_buckets = downstream.get("blocked_buckets", [])
        lines.append(
            f"- Frozen downstream avoidance buckets: {', '.join(blocked_buckets) if blocked_buckets else 'none'}"
        )
        lines.append(
            f"- Aggregate downstream delta: pre={downstream.get('aggregate_pre_holdout_total_r_delta', 0.0):+.4f}R, "
            f"holdout={downstream.get('aggregate_holdout_total_r_delta', 0.0):+.4f}R"
        )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=REGIME_RESEARCH_HOLDOUT_START)
    parser.add_argument("--holdout-end", default=REGIME_RESEARCH_HOLDOUT_END)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stage_a_dir = output_dir / "stage_a"
    stage_a_dir.mkdir(parents=True, exist_ok=True)
    holdout_dir = output_dir / "holdout"
    holdout_dir.mkdir(parents=True, exist_ok=True)
    downstream_dir = output_dir / "downstream"
    downstream_dir.mkdir(parents=True, exist_ok=True)

    trial_counter = TrialCounter()

    print("NQ Regime Challenger Workflow")
    print("=" * 72)
    print(f"Output dir: {output_dir}")
    print(f"Holdout: {args.holdout_start} to {args.holdout_end}")

    t0 = time.time()
    print("\n[1/6] Loading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file, start=args.start, end=args.end)
    try:
        df_1m = load_1m_for_5m(NQ.data_file, start=args.start, end=args.end)
    except FileNotFoundError:
        df_1m = None
    try:
        df_1s = load_1s_for_5m(NQ.data_file, start=args.start, end=args.end)
    except FileNotFoundError:
        df_1s = None
    print(
        f"  5m={len(df_5m):,} | "
        f"1m={len(df_1m) if df_1m is not None else 0:,} | "
        f"1s={len(df_1s) if df_1s is not None else 0:,} "
        f"[{time.time() - t0:.1f}s]"
    )

    print("\n[2/6] Evaluating Stage A registry...", flush=True)
    stage1_specs = build_first_wave_challenger_specs()
    stage_a_results: list[dict] = []
    results_by_name: dict[str, dict] = {}
    for spec in stage1_specs:
        result = evaluate_challenger_stage_a(df_5m, spec, holdout_start=args.holdout_start)
        stage_a_results.append(result)
        results_by_name[spec.name] = result
        trial_counter.add("stage_a_model_specs", 1)
        trial_counter.add("stage_a_wf_folds", int(result["walkforward"].get("n_folds", 0)))
        write_json(stage_a_dir / f"{spec.name}.json", _serialize_stage_a_result(result))
        result["calendar"].to_csv(stage_a_dir / f"{spec.name}_calendar.csv", index=False)
        print(
            f"  {spec.name}: agreement={result['selection_metrics']['mean_label_agreement']:.4f} | "
            f"min_bucket_share={result['selection_metrics']['min_bucket_share']:.4f}"
        )

    selection = select_challenger_finalists(stage_a_results, baseline_name="baseline_v1")
    combo_spec: RegimeChallengerSpec | None = None
    if selection["best_trend_name"] and selection["best_vol_name"]:
        combo_spec = build_combo_challenger_spec(
            results_by_name[selection["best_trend_name"]],
            results_by_name[selection["best_vol_name"]],
        )
        combo_result = evaluate_challenger_stage_a(df_5m, combo_spec, holdout_start=args.holdout_start)
        stage_a_results.append(combo_result)
        results_by_name[combo_spec.name] = combo_result
        trial_counter.add("stage_a_model_specs", 1)
        trial_counter.add("stage_a_wf_folds", int(combo_result["walkforward"].get("n_folds", 0)))
        write_json(stage_a_dir / f"{combo_spec.name}.json", _serialize_stage_a_result(combo_result))
        combo_result["calendar"].to_csv(stage_a_dir / f"{combo_spec.name}_calendar.csv", index=False)
    else:
        print(
            "  No valid combo finalist: "
            f"trend={selection['best_trend_name']}, vol={selection['best_vol_name']}",
            flush=True,
        )

    registry_payload = {
        "wave_name": "nq_regime_challengers_v1",
        "holdout_start": args.holdout_start,
        "holdout_end": args.holdout_end,
        "stage_order": [
            "baseline",
            "trend_only",
            "vol_only",
            "combo_finalist",
        ],
        "stage1_registry": [_serialize_challenger_spec(spec) for spec in stage1_specs],
        "combo_spec": _serialize_challenger_spec(combo_spec) if combo_spec is not None else None,
        "model_spec_count": len(stage_a_results),
        "holdout_used_for_ranking": False,
    }
    write_json(output_dir / "challenger_registry.json", registry_payload)

    stage_a_scoreboard = build_stage_a_scoreboard(stage_a_results, trial_counter, args.holdout_start)
    write_json(output_dir / "stage_a_scoreboard.json", stage_a_scoreboard)
    write_json(
        output_dir / "finalist_selection.json",
        {
            **selection,
            "combo_name": combo_spec.name if combo_spec is not None else None,
            "model_spec_count": len(stage_a_results),
        },
    )
    write_markdown(
        output_dir / "finalist_memo.md",
        format_finalist_memo(stage_a_scoreboard, selection, results_by_name, combo_spec, trial_counter),
    )

    finalists = [
        "baseline_v1",
        selection["best_trend_name"],
        selection["best_vol_name"],
        combo_spec.name if combo_spec is not None else None,
    ]
    finalists = [name for idx, name in enumerate(finalists) if name is not None and name not in finalists[:idx]]

    print("\n[3/6] Revealing holdout for frozen finalists...", flush=True)
    holdout_results: dict[str, dict] = {}
    for name in finalists:
        result = results_by_name[name]
        spec_dict = result["challenger_spec"]
        frozen_params = {
            "trend_sma_threshold": float(spec_dict["trend"]["bull_threshold"]),
            "trend_ret5d_threshold": float(spec_dict["trend"]["ret5d_threshold"]),
            "vol_method": str(spec_dict["vol"]["bucketing_method"]),
            "vol_thresholds": result["pre_holdout_vol_thresholds"],
        }
        holdout_result = run_regime_holdout(
            df_5m,
            frozen_params=frozen_params,
            holdout_start=args.holdout_start,
            holdout_end=args.holdout_end,
            challenger_spec=RegimeChallengerSpec(
                name=spec_dict["name"],
                family=spec_dict["family"],
                trend=TrendFeatureSpec(**spec_dict["trend"]),
                vol=VolFeatureSpec(**spec_dict["vol"]),
                low_conf_trend_threshold=float(spec_dict["low_conf_trend_threshold"]),
                low_conf_ret5d_threshold=float(spec_dict["low_conf_ret5d_threshold"]),
                warmup_length=int(spec_dict["warmup_length"]),
                description=str(spec_dict.get("description", "")),
            ),
        )
        holdout_results[name] = holdout_result
        trial_counter.add("stage_b_holdout_reveals", 1)
        write_json(holdout_dir / f"{name}.json", holdout_result)
        print(f"  {name}: holdout_days={holdout_result['holdout_days']}")
    write_json(output_dir / "holdout_reveal.json", holdout_results)

    print("\n[4/6] Running downstream benchmark suite...", flush=True)
    benchmark_trades = run_benchmark_suite(
        df_5m,
        df_1m=df_1m,
        df_1s=df_1s,
        start_date=args.start,
        end_date=args.end,
    )
    trial_counter.add("downstream_benchmark_runs", len(benchmark_trades))
    print(f"  Benchmarks: {', '.join(benchmark_trades.keys())}")

    print("\n[5/6] Evaluating frozen downstream usefulness...", flush=True)
    downstream_results: dict[str, dict] = {}
    for name in finalists:
        downstream = evaluate_downstream_usefulness(
            finalist_name=name,
            regime_calendar=results_by_name[name]["calendar"],
            benchmark_trades=benchmark_trades,
            holdout_start=args.holdout_start,
            holdout_end=args.holdout_end,
        )
        downstream_results[name] = downstream
        write_json(downstream_dir / f"{name}.json", downstream)
        print(
            f"  {name}: blocked={downstream['blocked_buckets']} | "
            f"holdout_delta={downstream['aggregate_holdout_total_r_delta']:+.4f}R"
        )
    write_json(output_dir / "downstream_finalists.json", downstream_results)

    write_markdown(output_dir / "holdout_memo.md", format_holdout_memo(holdout_results, downstream_results))

    print("\n[6/6] Saving trial log...", flush=True)
    write_json(
        output_dir / "trial_counter.json",
        {
            "phases": trial_counter.phases,
            "total": trial_counter.total,
            "model_spec_count": len(stage_a_results),
        },
    )

    elapsed = time.time() - t0
    print(f"\nDone. Total time: {elapsed:.1f}s")
    print(f"Output: {output_dir}")
    print(trial_counter.summary())


if __name__ == "__main__":
    main()
