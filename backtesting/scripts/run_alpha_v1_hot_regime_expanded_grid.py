#!/usr/bin/env python3
"""Expanded hot-regime Cartesian grid for ALPHA_V1 legs.

This builds on ``run_alpha_v1_hot_regime_ablation.py``. The first pass gives
one-at-a-time attribution; this pass takes the top OAT families and runs a
larger top-3-per-category combo grid for overnight-style hot-regime discovery.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

import run_alpha_v1_hot_regime_ablation as base


RUN_SLUG = "alpha_v1_hot_regime_expanded_grid_20260503"
RESULT_DIR = base.ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = base.ROOT / "learnings" / "reports" / "ALPHA_V1_HOT_REGIME_EXPANDED_GRID_20260503.md"
SOURCE_SCORE_PATH = base.RESULT_DIR / "variant_scores.csv"


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    return data


def _top3_options_from_first_pass(
    leg: base.LegSpec,
    options_by_category: dict[str, list[base.OptionSpec]],
    source_scores: pd.DataFrame,
) -> dict[str, list[base.OptionSpec]]:
    option_lookup = {option.option_id: option for options in options_by_category.values() for option in options}
    selected: dict[str, list[base.OptionSpec]] = {}

    # Keep explosive combo size focused: these were strongly answered by OAT.
    forced_keep = {
        "fvg_selection": 1,
        "wide_stop": 1,
        "entry_mode": 1,
    }
    keep_default = 3

    baseline_payload = base._cfg_payload(leg.config)
    leg_scores = source_scores[(source_scores["leg"] == leg.key) & (source_scores["stage"] == "oat")]
    for category, options in options_by_category.items():
        keep = forced_keep.get(category, keep_default)
        rows = leg_scores[leg_scores["category"] == category].sort_values("hot_score", ascending=False)
        picked: list[base.OptionSpec] = []

        for option in options:
            try:
                if base._cfg_payload(base._variant_config(leg.config, "tmp", option)) == baseline_payload:
                    picked.append(option)
                    break
            except ValueError:
                continue

        for _, row in rows.iterrows():
            option = option_lookup.get(str(row["primary_option"]))
            if option is None or option in picked:
                continue
            picked.append(option)
            if len(picked) >= keep:
                break

        if not picked:
            picked = options[:keep]
        selected[category] = picked[:keep]
    return selected


def _expanded_combo_variants(
    leg: base.LegSpec,
    selected_options: dict[str, list[base.OptionSpec]],
) -> list[base.VariantSpec]:
    # Large enough to be a real Cartesian pass, still finite enough for local use.
    return base._combo_variants(leg, selected_options, cap=10_000)


def _write_expanded_report(
    *,
    end_inclusive: str,
    windows: dict[str, tuple[str, str]],
    score_rows: list[dict[str, Any]],
    portfolio_rows: list[dict[str, Any]],
    selected_option_manifest: dict[str, dict[str, list[str]]],
) -> None:
    lines = [
        "# ALPHA_V1 Hot-Regime Expanded Grid",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Window: `{base.FULL_START}` to `{end_inclusive}`",
        "- Intent: larger top-3-per-category Cartesian expansion after the OAT attribution pass.",
        "- This is TESTING-only hot-regime research, not a robust promotion packet.",
        f"- Score formula: `{base.HOT_SCORE_FORMULA}`",
        "- FVG extreme chasing, wide-stop target compression, and close-entry HTF-LSI were kept constrained because the OAT pass already showed they were destructive.",
        "",
        "## Selected Combo Seeds",
        "",
        "```json",
        json.dumps(selected_option_manifest, indent=2, sort_keys=True),
        "```",
        "",
        "## Best Candidates",
        "",
    ]

    for leg in ("nq_ny_htf_lsi", "nq_asia_orb", "es_asia_orb", "es_ny_orb"):
        baseline = base._baseline_for_leg(score_rows, leg)
        best_last1 = base._top_for_leg(score_rows, leg, "last1_net_r", limit=1)[0]
        best_last2 = base._top_for_leg(score_rows, leg, "last2_net_r", limit=1)[0]
        best_score = base._top_for_leg(score_rows, leg, "hot_score", limit=1)[0]
        rows = []
        for label, row in (("baseline", baseline), ("best_last1", best_last1), ("best_last2", best_last2), ("best_score", best_score)):
            rows.append(
                {
                    "pick": label,
                    "variant": row["variant_id"][:90],
                    "full_net": row["full_net_r"],
                    "full_dd": row["full_dd_r"],
                    "full_pf": row["full_pf"],
                    "neg_y": row["full_negative_years"],
                    "last2_net": row["last2_net_r"],
                    "last1_net": row["last1_net_r"],
                    "last1_dd": row["last1_dd_r"],
                    "last1_pf": row["last1_pf"],
                    "fills1y": row["last1_fills"],
                    "hot_score": row["hot_score"],
                    "warning": base._full_warning(row),
                }
            )
        lines.extend(
            [
                f"### {leg}",
                "",
                base._markdown_table(
                    rows,
                    [
                        "pick",
                        "variant",
                        "full_net",
                        "full_dd",
                        "full_pf",
                        "neg_y",
                        "last2_net",
                        "last1_net",
                        "last1_dd",
                        "last1_pf",
                        "fills1y",
                        "hot_score",
                        "warning",
                    ],
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Portfolio Proxy",
            "",
            base._markdown_table(
                portfolio_rows,
                [
                    "portfolio",
                    "full_fills",
                    "full_net_r",
                    "full_pf",
                    "full_dd_r",
                    "full_negative_years",
                    "last_2y_fills",
                    "last_2y_net_r",
                    "last_2y_pf",
                    "last_2y_dd_r",
                    "last_1y_fills",
                    "last_1y_net_r",
                    "last_1y_pf",
                    "last_1y_dd_r",
                ],
            ),
            "",
            "## Read",
            "",
            "- Prefer the best-score rows for TESTING candidates unless the explicit goal is maximum recent R regardless of 10-year warning damage.",
            "- Any branch here should be dry-run forward tested first; this pass intentionally leans into recent-market overfit risk.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    if not SOURCE_SCORE_PATH.exists():
        raise FileNotFoundError(f"Run first-pass script before expanded grid: {SOURCE_SCORE_PATH}")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    source_scores = pd.read_csv(SOURCE_SCORE_PATH)
    legs = base._active_alpha_v1_legs()
    symbols = sorted({leg.config.instrument.symbol for leg in legs})
    data_by_symbol = {symbol: base._load_data(base.NQ if symbol == "NQ" else base.ES) for symbol in symbols}
    end_inclusive, end_exclusive = base._available_end_exclusive(data_by_symbol)
    end_ts = pd.Timestamp(end_inclusive)
    windows = {
        "full": (base.FULL_START, end_inclusive),
        "last_2y": ((end_ts - pd.Timedelta(days=730)).date().isoformat(), end_inclusive),
        "last_1y": ((end_ts - pd.Timedelta(days=365)).date().isoformat(), end_inclusive),
    }

    all_metric_rows: list[dict[str, Any]] = []
    all_manifest_rows: list[dict[str, Any]] = []
    variant_results: dict[str, tuple[base.LegSpec, base.VariantSpec, list[base.TradeResult]]] = {}
    baseline_streams: dict[str, list[base.TradeResult]] = {}
    hot_streams: dict[str, list[base.TradeResult]] = {}
    selected_option_manifest: dict[str, dict[str, list[str]]] = {}

    for leg in legs:
        print(f"\n=== EXPANDED {leg.label} ===", flush=True)
        loaded = data_by_symbol[leg.config.instrument.symbol]

        baseline_variant = base._baseline_variant(leg)
        baseline_result = base._run_variants(loaded, [baseline_variant], start_date=base.FULL_START, end_date=end_exclusive)
        baseline_trades = baseline_result[baseline_variant.config.name]
        baseline_streams[leg.key] = baseline_trades
        variant_results[f"{leg.key}::baseline"] = (leg, baseline_variant, baseline_trades)

        options_by_category = base._options_for_leg(leg, baseline_trades)
        selected_options = _top3_options_from_first_pass(leg, options_by_category, source_scores)
        selected_option_manifest[leg.key] = {cat: [opt.option_id for opt in opts] for cat, opts in selected_options.items()}

        combo_variants = _expanded_combo_variants(leg, selected_options)
        print(f"    selected options: {selected_option_manifest[leg.key]}", flush=True)
        print(f"    expanded combos: {len(combo_variants)}", flush=True)
        combo_results = base._run_variants(loaded, combo_variants, start_date=base.FULL_START, end_date=end_exclusive)

        for variant, trades in [(baseline_variant, baseline_trades), *[(v, combo_results[v.config.name]) for v in combo_variants]]:
            variant_results[f"{leg.key}::{variant.variant_id}"] = (leg, variant, trades)
            all_manifest_rows.append(base._manifest_row(variant))
            for window, (start, end) in windows.items():
                all_metric_rows.append(base._metric_row(leg=leg, variant=variant, trades=trades, window=window, start=start, end_inclusive=end))

        leg_scores = base._add_deltas(base._score_rows([r for r in all_metric_rows if r["leg"] == leg.key]))
        best_hot = base._top_for_leg(leg_scores, leg.key, "hot_score", limit=1)[0]
        hot_streams[leg.key] = variant_results[f"{leg.key}::{best_hot['variant_id']}"][2]
        print(
            f"    best expanded hot-score: {best_hot['variant_id']} | "
            f"last1 {best_hot['last1_net_r']}R | last2 {best_hot['last2_net_r']}R | full {best_hot['full_net_r']}R",
            flush=True,
        )

    score_rows = base._add_deltas(base._score_rows(all_metric_rows))
    annual_rows = base._annual_rows(variant_results)
    portfolio_rows = [
        base._portfolio_row("baseline_current_alpha_v1", baseline_streams, windows),
        base._portfolio_row("replace_each_leg_with_best_expanded_hot_score", hot_streams, windows),
    ]

    pd.DataFrame(all_metric_rows).to_csv(RESULT_DIR / "metrics_by_window.csv", index=False)
    pd.DataFrame(score_rows).to_csv(RESULT_DIR / "variant_scores.csv", index=False)
    pd.DataFrame(all_manifest_rows).to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    pd.DataFrame(annual_rows).to_csv(RESULT_DIR / "annual_r.csv", index=False)
    pd.DataFrame(portfolio_rows).to_csv(RESULT_DIR / "portfolio_proxy.csv", index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "source_score_path": str(SOURCE_SCORE_PATH),
        "full_start": base.FULL_START,
        "end_inclusive": end_inclusive,
        "end_exclusive": end_exclusive,
        "windows": windows,
        "hot_score_formula": base.HOT_SCORE_FORMULA,
        "selected_option_manifest": selected_option_manifest,
        "best_hot_score_by_leg": {
            leg.key: base._top_for_leg(score_rows, leg.key, "hot_score", limit=1)[0]
            for leg in legs
        },
        "best_last1_by_leg": {
            leg.key: base._top_for_leg(score_rows, leg.key, "last1_net_r", limit=1)[0]
            for leg in legs
        },
        "portfolio_proxy": portfolio_rows,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True, default=str))

    _write_expanded_report(
        end_inclusive=end_inclusive,
        windows=windows,
        score_rows=score_rows,
        portfolio_rows=portfolio_rows,
        selected_option_manifest=selected_option_manifest,
    )
    print("\nDONE EXPANDED", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Results: {RESULT_DIR}", flush=True)


if __name__ == "__main__":
    main()
