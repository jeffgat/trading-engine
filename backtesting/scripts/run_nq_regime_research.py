#!/usr/bin/env python3
"""NQ Regime Research — 3x3 Trend x Volatility framework.

12-step pipeline:
  1. Load NQ 5m data, freeze holdout
  2. Build extended regime calendar (trend + vol)
  3. Phase A — Regime definition audit
  4. Phase B — Threshold search
  5. Phase C — Walk-forward validation
  6. Phase D — Holdout confirmation
  7. Attribution — Run each robust strategy, attribute by regime
  8. Promotion — Evaluate specialist criteria
  9. Specialist optimization — WF within target regimes
 10. Full gated system validation
 11. Prop downstream evaluation
 12. Save all artifacts

Usage:
  uv run python scripts/run_nq_regime_research.py
  uv run python scripts/run_nq_regime_research.py --phase A
  uv run python scripts/run_nq_regime_research.py --workers 8
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.regime_research import (
    REGIME_RESEARCH_HOLDOUT_END,
    REGIME_RESEARCH_HOLDOUT_START,
    TrialCounter,
    attribute_strategy_by_regime,
    audit_regime_definition,
    build_attribution_summary,
    build_extended_regime_calendar,
    compute_bucket_metrics,
    compute_vol_thresholds,
    evaluate_promotion_criteria,
    evaluate_prop_downstream,
    make_regime_gate,
    optimize_specialist_in_regime,
    run_regime_holdout,
    search_regime_thresholds,
    validate_gated_system,
    validate_regime_walkforward,
)
from orb_backtest.analysis.prop_regime_specialist import PropFirmProfile
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

OUTPUT_DIR = ROOT / "data" / "results" / "nq_regime_research"


# ---------------------------------------------------------------------------
# Strategy config factories (frozen configs from existing GO/CONDITIONAL strategies)
# ---------------------------------------------------------------------------


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
        tp1_ratio=0.5,  # Clamped from 0.3 to satisfy tp1_ratio * rr >= 1.0
        atr_length=14,
        impulse_close_filter=False,
        excluded_days=(0,),
        name="NQ NY Short v2",
    )


def make_nq_asia_r9_config() -> StrategyConfig:
    sess = SessionConfig(
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
        sessions=(sess,),
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


STRATEGIES = {
    "nq_ny_long_r11": {
        "config_fn": make_nq_ny_long_r11_config,
        "excluded_days": {4},  # Friday
    },
    "nq_ny_short_v2": {
        "config_fn": make_nq_ny_short_v2_config,
        "excluded_days": {0},  # Monday
    },
    "nq_asia_r9": {
        "config_fn": make_nq_asia_r9_config,
        "excluded_days": {1},  # Tuesday
    },
}


# ---------------------------------------------------------------------------
# Threshold search variants
# ---------------------------------------------------------------------------

def build_threshold_variants() -> list[dict]:
    """Build pre-declared set of regime threshold variants to search."""
    variants = []
    for sma_thresh in [0.0025, 0.005, 0.01]:
        for ret5d_thresh in [0.0, 0.0025, 0.005]:
            for vol_method in ["tercile", "quartile"]:
                variants.append({
                    "trend_sma_threshold": sma_thresh,
                    "trend_ret5d_threshold": ret5d_thresh,
                    "vol_method": vol_method,
                })
    return variants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def write_markdown(path: Path, content: str) -> None:
    path.write_text(content)


def format_rule_spec(audit: dict) -> str:
    """Format the regime rule spec as a markdown document."""
    lines = [
        "# NQ Regime Research — Regime Rule Specification\n",
        "## Definition\n",
        "```",
        audit["rule_spec"],
        "```\n",
        "## Pre-Holdout Summary\n",
        f"- Total tradable days: {audit['pre_holdout_summary']['total_days']}",
        f"- Low-confidence days: {audit['pre_holdout_summary']['low_confidence_days']}",
        "",
        "### Trend Counts",
    ]

    for k, v in sorted(audit["pre_holdout_summary"]["trend_counts"].items()):
        pct = v / max(audit["pre_holdout_summary"]["total_days"], 1) * 100
        lines.append(f"  - {k}: {v} ({pct:.1f}%)")

    lines.append("\n### Volatility Counts")
    for k, v in sorted(audit["pre_holdout_summary"]["vol_counts"].items()):
        pct = v / max(audit["pre_holdout_summary"]["total_days"], 1) * 100
        lines.append(f"  - {k}: {v} ({pct:.1f}%)")

    lines.append("\n### Combined 3x3 Counts")
    for k, v in sorted(audit["pre_holdout_summary"]["combined_counts"].items()):
        pct = v / max(audit["pre_holdout_summary"]["total_days"], 1) * 100
        lines.append(f"  - {k}: {v} ({pct:.1f}%)")

    lines.append("\n## Episode Analysis\n")
    lines.append("### Combined Regime Episodes")
    for ep in audit["combined_episodes"]:
        lines.append(
            f"  - {ep['regime']}: {ep['episode_count']} episodes, "
            f"mean={ep['mean_duration']:.1f}d, median={ep['median_duration']:.1f}d, "
            f"range=[{ep['min_duration']}, {ep['max_duration']}]"
        )

    return "\n".join(lines)


def format_validation_memo(
    audit: dict,
    search_results: pd.DataFrame,
    wf_validation: dict,
    holdout_result: dict,
    trial_counter: TrialCounter,
) -> str:
    """Format the regime validation memo as markdown."""
    lines = [
        "# NQ Regime Research — Validation Memo\n",
        "## Phase A: Regime Definition Audit\n",
        f"Pre-holdout days: {audit['pre_holdout_summary']['total_days']}",
        f"Low-confidence days: {audit['pre_holdout_summary']['low_confidence_days']}",
        f"Ambiguity log entries: {audit['ambiguity_log_count']}",
        "",
        "## Phase B: Threshold Search\n",
        f"Variants tested: {len(search_results)}",
    ]

    if not search_results.empty:
        best = search_results.sort_values("min_bucket_share", ascending=False).iloc[0]
        lines.append(
            f"Best variant (by min_bucket_share): trial #{int(best['trial_id'])} "
            f"(SMA={best['trend_sma_threshold']}, ret5d={best['trend_ret5d_threshold']}, "
            f"vol={best['vol_method']})"
        )
        lines.append(f"  min_bucket_share: {best['min_bucket_share']:.4f}")
        lines.append(f"  ambiguity_rate: {best['ambiguity_rate']:.4f}")

    lines.append("\n## Phase C: Walk-Forward Validation\n")
    lines.append(f"Folds: {wf_validation.get('n_folds', 0)}")
    lines.append(f"Mean label agreement: {wf_validation.get('mean_label_agreement', 0):.4f}")

    criteria = wf_validation.get("pass_criteria", {})
    lines.append(f"Stable frequencies: {'PASS' if criteria.get('stable_frequencies') else 'FAIL'}")
    lines.append(f"No sparse buckets: {'PASS' if criteria.get('no_sparse_buckets') else 'FAIL'}")

    if wf_validation.get("sparse_violations"):
        lines.append(f"Sparse violations: {', '.join(wf_validation['sparse_violations'])}")

    lines.append("\n## Phase D: Holdout Confirmation\n")
    lines.append(f"Holdout period: {holdout_result.get('holdout_start')} to {holdout_result.get('holdout_end')}")
    lines.append(f"Holdout days: {holdout_result.get('holdout_days', 0)}")

    if holdout_result.get("distribution_diff"):
        lines.append("\nDistribution comparison (holdout vs pre-holdout):")
        for bucket, diff in sorted(holdout_result["distribution_diff"].items()):
            lines.append(
                f"  {bucket}: pre={diff['pre_holdout_pct']:.3f} "
                f"holdout={diff['holdout_pct']:.3f} "
                f"diff={diff['diff']:+.3f}"
            )

    lines.append(f"\n## Trial Count\n\n{trial_counter.summary()}")
    lines.append(
        "\n**Bailey posture**: Results are heuristic. Regime-definition search and "
        "strategy-parameter search are tracked as separate but cumulative sources "
        "of multiple testing. No formal multiple-testing corrections applied."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=REGIME_RESEARCH_HOLDOUT_START)
    parser.add_argument("--holdout-end", default=REGIME_RESEARCH_HOLDOUT_END)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--phase",
        default=None,
        help="Run a single phase: A, B, C, D, attribution, promotion, optimize, gate, prop, or all (default).",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trial_counter = TrialCounter()
    run_all = args.phase is None or args.phase.lower() == "all"

    print("NQ Regime Research — 3x3 Trend x Volatility Framework")
    print("=" * 72)
    print(f"Output dir: {output_dir}")
    print(f"Holdout: {args.holdout_start} to {args.holdout_end}")
    if args.phase:
        print(f"Phase: {args.phase}")

    # -----------------------------------------------------------------------
    # Step 1: Load NQ data
    # -----------------------------------------------------------------------
    t0 = time.time()
    print("\n[Step 1] Loading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file, start=args.start, end=args.end)
    try:
        df_1m = load_1m_for_5m(NQ.data_file, start=args.start, end=args.end)
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file, start=args.start, end=args.end)
    print(
        f"  5m={len(df_5m):,} | "
        f"1m={len(df_1m) if df_1m is not None else 0:,} | "
        f"1s={len(df_1s) if df_1s is not None else 0:,} "
        f"[{time.time() - t0:.1f}s]"
    )

    # -----------------------------------------------------------------------
    # Step 2: Build extended regime calendar
    # -----------------------------------------------------------------------
    print("\n[Step 2] Building extended regime calendar (trend + vol)...", flush=True)
    t1 = time.time()
    regime_calendar = build_extended_regime_calendar(
        df_5m,
        start_date=args.start,
        end_date=args.end,
        holdout_start=args.holdout_start,
    )
    vol_thresholds = compute_vol_thresholds(regime_calendar, args.holdout_start)
    regime_calendar.to_csv(output_dir / "regime_calendar.csv", index=False)
    print(
        f"  Calendar rows={len(regime_calendar):,} | "
        f"vol_thresholds={vol_thresholds} "
        f"[{time.time() - t1:.1f}s]"
    )

    # -----------------------------------------------------------------------
    # Step 3: Phase A — Regime definition audit
    # -----------------------------------------------------------------------
    if run_all or args.phase and args.phase.upper() == "A":
        print("\n[Step 3] Phase A — Regime definition audit...", flush=True)
        t2 = time.time()
        audit = audit_regime_definition(regime_calendar, args.holdout_start)
        write_json(output_dir / "regime_audit.json", audit)
        write_markdown(output_dir / "regime_rule_spec.md", format_rule_spec(audit))
        print(
            f"  Pre-holdout days: {audit['pre_holdout_summary']['total_days']} | "
            f"Low-confidence: {audit['pre_holdout_summary']['low_confidence_days']} "
            f"[{time.time() - t2:.1f}s]"
        )

    # -----------------------------------------------------------------------
    # Step 4: Phase B — Threshold search
    # -----------------------------------------------------------------------
    if run_all or args.phase and args.phase.upper() == "B":
        print("\n[Step 4] Phase B — Threshold search...", flush=True)
        t3 = time.time()
        variants = build_threshold_variants()
        search_results = search_regime_thresholds(df_5m, variants, args.holdout_start)
        search_results.to_csv(output_dir / "threshold_search.csv", index=False)
        trial_counter.add("phase_b_threshold_search", len(variants))
        print(
            f"  Variants tested: {len(variants)} | "
            f"Best min_bucket_share: "
            f"{search_results['min_bucket_share'].max():.4f} "
            f"[{time.time() - t3:.1f}s]"
        )

    # -----------------------------------------------------------------------
    # Step 5: Phase C — Walk-forward validation
    # -----------------------------------------------------------------------
    if run_all or args.phase and args.phase.upper() == "C":
        print("\n[Step 5] Phase C — Walk-forward validation...", flush=True)
        t4 = time.time()
        wf_validation = validate_regime_walkforward(
            df_5m,
            holdout_start=args.holdout_start,
        )
        write_json(output_dir / "regime_wf_validation.json", wf_validation)
        n_folds = wf_validation.get("n_folds", 0)
        trial_counter.add("phase_c_wf_folds", n_folds)
        print(
            f"  Folds: {n_folds} | "
            f"Mean agreement: {wf_validation.get('mean_label_agreement', 0):.4f} | "
            f"Stable: {wf_validation['pass_criteria'].get('stable_frequencies', False)} "
            f"[{time.time() - t4:.1f}s]"
        )

    # -----------------------------------------------------------------------
    # Step 6: Phase D — Holdout confirmation
    # -----------------------------------------------------------------------
    if run_all or args.phase and args.phase.upper() == "D":
        print("\n[Step 6] Phase D — Holdout confirmation...", flush=True)
        t5 = time.time()

        # Use best threshold variant from Phase B if available,
        # otherwise fall back to defaults
        best_sma_thresh = 0.005
        best_ret5d_thresh = 0.0
        best_vol_method = "tercile"
        search_path = output_dir / "threshold_search.csv"
        if search_path.exists():
            search_df = pd.read_csv(search_path)
            if not search_df.empty:
                best_row = search_df.sort_values("min_bucket_share", ascending=False).iloc[0]
                best_sma_thresh = float(best_row["trend_sma_threshold"])
                best_ret5d_thresh = float(best_row["trend_ret5d_threshold"])
                best_vol_method = str(best_row["vol_method"])
                print(f"  Using Phase B best: SMA={best_sma_thresh}, ret5d={best_ret5d_thresh}, vol={best_vol_method}")

        frozen_params = {
            "trend_sma_threshold": best_sma_thresh,
            "trend_ret5d_threshold": best_ret5d_thresh,
            "vol_method": best_vol_method,
            "vol_thresholds": vol_thresholds,
        }
        holdout_result = run_regime_holdout(
            df_5m,
            frozen_params,
            holdout_start=args.holdout_start,
            holdout_end=args.holdout_end,
        )
        write_json(output_dir / "regime_holdout.json", holdout_result)
        trial_counter.add("phase_d_holdout", 1)
        print(
            f"  Holdout days: {holdout_result['holdout_days']} | "
            f"Ambiguity: {holdout_result['holdout_ambiguity_count']} "
            f"[{time.time() - t5:.1f}s]"
        )

    # -----------------------------------------------------------------------
    # Step 7: Attribution — Run each robust strategy, attribute by regime
    # -----------------------------------------------------------------------
    attributions: dict[str, pd.DataFrame] = {}

    if run_all or args.phase and args.phase.lower() == "attribution":
        print("\n[Step 7] Strategy attribution...", flush=True)
        t6 = time.time()

        for strategy_name, strategy_info in STRATEGIES.items():
            print(f"  Running {strategy_name}...", flush=True)
            config = strategy_info["config_fn"]()
            trades = run_backtest(
                df_5m, config,
                start_date=args.start, end_date=args.end,
                df_1m=df_1m, df_1s=df_1s,
            )
            if strategy_info.get("excluded_days"):
                trades = apply_dow_filter(trades, strategy_info["excluded_days"])

            attr_df = attribute_strategy_by_regime(trades, regime_calendar, args.holdout_start)
            attr_df.to_csv(output_dir / f"attribution_{strategy_name}.csv", index=False)
            attributions[strategy_name] = attr_df

            bucket_metrics = compute_bucket_metrics(attr_df)
            print(f"    Trades: {len(attr_df)} | Buckets: {len(bucket_metrics)}")

        # Combined attribution summary
        attr_summary = build_attribution_summary(attributions)
        write_json(output_dir / "strategy_attribution.json", attr_summary)
        print(f"  Attribution complete [{time.time() - t6:.1f}s]")

    # -----------------------------------------------------------------------
    # Step 8: Promotion — Evaluate specialist criteria
    # -----------------------------------------------------------------------
    promotion_results: dict[str, list[dict]] = {}

    if run_all or args.phase and args.phase.lower() == "promotion":
        print("\n[Step 8] Specialist promotion evaluation...", flush=True)
        t7 = time.time()

        # If attributions not run in this invocation, reload from CSV
        if not attributions:
            for strategy_name in STRATEGIES:
                csv_path = output_dir / f"attribution_{strategy_name}.csv"
                if csv_path.exists():
                    attributions[strategy_name] = pd.read_csv(csv_path)

        # Get all combined regime buckets
        all_buckets = set()
        if regime_calendar is not None:
            warmup_ok = regime_calendar[regime_calendar["warmup_ok"] == True]  # noqa: E712
            all_buckets = set(warmup_ok["combined_regime"].unique()) - {"warmup"}

        promotion_memo_lines = [
            "# NQ Regime Research — Specialist Promotion Memo\n",
        ]

        for strategy_name, strategy_info in STRATEGIES.items():
            print(f"  Evaluating {strategy_name}...", flush=True)
            config = strategy_info["config_fn"]()
            trades = run_backtest(
                df_5m, config,
                start_date=args.start, end_date=args.end,
                df_1m=df_1m, df_1s=df_1s,
            )
            if strategy_info.get("excluded_days"):
                trades = apply_dow_filter(trades, strategy_info["excluded_days"])

            strategy_promotions = []
            promotion_memo_lines.append(f"\n## {strategy_name}\n")

            for target_regime in sorted(all_buckets):
                result = evaluate_promotion_criteria(
                    strategy_name=strategy_name,
                    target_regime=target_regime,
                    trades=trades,
                    regime_calendar=regime_calendar,
                    holdout_start=args.holdout_start,
                )
                strategy_promotions.append(result)
                trial_counter.add("phase_8_promotion_evaluations", 1)

                status = "PROMOTED" if result["promoted"] else "NOT PROMOTED"
                promotion_memo_lines.append(f"### {target_regime}: {status}")
                for crit_name, crit_data in result["criteria"].items():
                    pass_str = "PASS" if crit_data["pass"] else "FAIL"
                    promotion_memo_lines.append(
                        f"  - {crit_name}: {pass_str} (value={crit_data['value']}, "
                        f"threshold={crit_data['threshold']})"
                    )

            promotion_results[strategy_name] = strategy_promotions

        write_json(output_dir / "promotion_results.json", promotion_results)
        write_markdown(
            output_dir / "specialist_promotion_memo.md",
            "\n".join(promotion_memo_lines),
        )
        print(f"  Promotion evaluation complete [{time.time() - t7:.1f}s]")

    # -----------------------------------------------------------------------
    # Step 9: Specialist optimization (WF within target regimes)
    # -----------------------------------------------------------------------
    specialist_configs: dict[str, dict] = {}

    if run_all or args.phase and args.phase.lower() == "optimize":
        print("\n[Step 9] Specialist optimization...", flush=True)
        t8 = time.time()

        opt_dir = output_dir / "specialist_optimization"
        opt_dir.mkdir(parents=True, exist_ok=True)

        # Find promoted pairs
        if not promotion_results:
            promo_path = output_dir / "promotion_results.json"
            if promo_path.exists():
                promotion_results = json.loads(promo_path.read_text())

        promoted_pairs: list[tuple[str, str, dict]] = []
        for strategy_name, promos in promotion_results.items():
            for promo in promos:
                if isinstance(promo, dict) and promo.get("promoted"):
                    promoted_pairs.append((
                        strategy_name,
                        promo["target_regime"],
                        STRATEGIES[strategy_name],
                    ))

        if not promoted_pairs:
            print("  No promoted pairs found. Skipping optimization.")
        else:
            for strategy_name, target_regime, strategy_info in promoted_pairs:
                print(f"  Optimizing {strategy_name} for {target_regime}...", flush=True)
                config = strategy_info["config_fn"]()

                # Small parameter ranges for specialist tuning
                param_ranges = {
                    "rr": [config.rr - 0.5, config.rr, config.rr + 0.5],
                    "tp1_ratio": [
                        max(0.2, config.tp1_ratio - 0.1),
                        config.tp1_ratio,
                        min(1.0, config.tp1_ratio + 0.1),
                    ],
                }

                opt_result = optimize_specialist_in_regime(
                    df=df_5m,
                    base_config=config,
                    regime_calendar=regime_calendar,
                    target_regime=target_regime,
                    param_ranges=param_ranges,
                    holdout_start=args.holdout_start,
                    objective="calmar",
                    n_workers=args.workers,
                    df_1m=df_1m,
                    df_1s=df_1s,
                )
                trial_counter.add("phase_9_specialist_optimization", opt_result.get("trial_count", 0))

                regime_dir = opt_dir / target_regime.replace(" ", "_")
                regime_dir.mkdir(parents=True, exist_ok=True)
                write_json(regime_dir / "wf_result.json", opt_result)

                specialist_configs[target_regime] = {
                    "strategy_name": strategy_name,
                    "target_regime": target_regime,
                    "wf_result": opt_result,
                }

                print(
                    f"    WF efficiency: {opt_result.get('walk_forward_efficiency', 0):.4f} | "
                    f"Trials: {opt_result.get('trial_count', 0)}"
                )

        print(f"  Optimization complete [{time.time() - t8:.1f}s]")

    # -----------------------------------------------------------------------
    # Step 10: Full gated system validation
    # -----------------------------------------------------------------------
    if run_all or args.phase and args.phase.lower() == "gate":
        print("\n[Step 10] Full gated system validation...", flush=True)
        t9 = time.time()

        # Build specialists dict: target_regime -> {"trades": [...]}
        specialists_for_gate: dict[str, dict] = {}

        for strategy_name, strategy_info in STRATEGIES.items():
            config = strategy_info["config_fn"]()
            trades = run_backtest(
                df_5m, config,
                start_date=args.start, end_date=args.end,
                df_1m=df_1m, df_1s=df_1s,
            )
            if strategy_info.get("excluded_days"):
                trades = apply_dow_filter(trades, strategy_info["excluded_days"])

            # Check which regimes this strategy is promoted for
            if promotion_results and strategy_name in promotion_results:
                for promo in promotion_results[strategy_name]:
                    if isinstance(promo, dict) and promo.get("promoted"):
                        target = promo["target_regime"]
                        specialists_for_gate[target] = {"trades": trades}

        if specialists_for_gate:
            gate_result = validate_gated_system(
                specialists_for_gate,
                regime_calendar,
                holdout_start=args.holdout_start,
            )
            write_json(output_dir / "gated_system_result.json", gate_result)

            # Format scorecard
            scorecard_lines = [
                "# NQ Regime Research — Gated System Scorecard\n",
            ]
            combined = gate_result.get("combined_system", {})
            scorecard_lines.append(f"Total gated trades: {combined.get('total_gated_trades', 0)}")
            scorecard_lines.append(f"Trade date coverage: {combined.get('trade_date_coverage_rate', 0):.4f}")

            cm = combined.get("combined_metrics", {})
            scorecard_lines.append(f"Combined Calmar: {cm.get('calmar_ratio', 'N/A')}")
            scorecard_lines.append(f"Combined Sharpe: {cm.get('sharpe_ratio', 'N/A')}")
            scorecard_lines.append(f"Combined Net R: {cm.get('total_r', 'N/A')}")

            for target, spec_data in gate_result.get("specialist_results", {}).items():
                scorecard_lines.append(f"\n## {target}")
                scorecard_lines.append(f"  Gated trades: {spec_data.get('gated_trades', 0)}")
                scorecard_lines.append(f"  Gate activation rate: {spec_data.get('gate_activation_rate', 0):.4f}")
                gm = spec_data.get("gated_metrics", {})
                scorecard_lines.append(f"  Calmar: {gm.get('calmar_ratio', 'N/A')}")
                scorecard_lines.append(f"  Net R: {gm.get('total_r', 'N/A')}")

            write_markdown(output_dir / "gated_system_scorecard.md", "\n".join(scorecard_lines))
            print(f"  Gated system validated [{time.time() - t9:.1f}s]")
        else:
            print("  No promoted specialists to gate. Skipping.")

    # -----------------------------------------------------------------------
    # Step 11: Prop downstream evaluation
    # -----------------------------------------------------------------------
    if run_all or args.phase and args.phase.lower() == "prop":
        print("\n[Step 11] Prop downstream evaluation...", flush=True)
        t10 = time.time()

        prop_dir = output_dir / "prop_handoff"
        prop_dir.mkdir(parents=True, exist_ok=True)

        prop_results: dict[str, dict] = {}

        for strategy_name, strategy_info in STRATEGIES.items():
            config = strategy_info["config_fn"]()
            trades = run_backtest(
                df_5m, config,
                start_date=args.start, end_date=args.end,
                df_1m=df_1m, df_1s=df_1s,
            )
            if strategy_info.get("excluded_days"):
                trades = apply_dow_filter(trades, strategy_info["excluded_days"])

            # Check if promoted for any regime
            promoted_regimes = []
            if promotion_results and strategy_name in promotion_results:
                for promo in promotion_results[strategy_name]:
                    if isinstance(promo, dict) and promo.get("promoted"):
                        promoted_regimes.append(promo["target_regime"])

            for target_regime in promoted_regimes:
                gate = make_regime_gate(regime_calendar, target_regime)
                gated_trades = gate(trades)

                prop_result = evaluate_prop_downstream(
                    specialist_name=f"{strategy_name}_{target_regime}",
                    gated_trades=gated_trades,
                    regime_calendar=regime_calendar,
                    holdout_start=args.holdout_start,
                )
                prop_results[f"{strategy_name}_{target_regime}"] = prop_result

        write_json(prop_dir / "prop_scorecards.json", prop_results)
        print(f"  Prop evaluation complete [{time.time() - t10:.1f}s]")

    # -----------------------------------------------------------------------
    # Step 12: Save all artifacts + validation memo
    # -----------------------------------------------------------------------
    print("\n[Step 12] Saving final artifacts...", flush=True)

    # Load intermediate results if not already in memory
    audit = {}
    audit_path = output_dir / "regime_audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())

    search_results = pd.DataFrame()
    search_path = output_dir / "threshold_search.csv"
    if search_path.exists():
        search_results = pd.read_csv(search_path)

    wf_validation = {}
    wf_path = output_dir / "regime_wf_validation.json"
    if wf_path.exists():
        wf_validation = json.loads(wf_path.read_text())

    holdout_result = {}
    holdout_path = output_dir / "regime_holdout.json"
    if holdout_path.exists():
        holdout_result = json.loads(holdout_path.read_text())

    if audit:
        memo = format_validation_memo(
            audit, search_results, wf_validation, holdout_result, trial_counter,
        )
        write_markdown(output_dir / "regime_validation_memo.md", memo)

    # Save trial counter
    write_json(output_dir / "trial_counter.json", {
        "phases": trial_counter.phases,
        "total": trial_counter.total,
    })

    elapsed = time.time() - t0
    print(f"\nDone. Total time: {elapsed:.1f}s")
    print(f"Output: {output_dir}")
    print(trial_counter.summary())


if __name__ == "__main__":
    main()
