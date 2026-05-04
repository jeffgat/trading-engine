#!/usr/bin/env python3
"""Targeted structural follow-up around the positive hot-gate leads.

This pass starts where HOT_STRUCTURAL_SEQUENCE_20260503 ended. It only
deepens the legs where structure added net R or was close enough to be worth a
second look, then searches local gate variants and small combinations.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import run_hot_one_year_squeeze as squeeze  # noqa: E402
import run_hot_one_year_strategy_workflow as prev  # noqa: E402
import run_hot_structural_sequence as seq  # noqa: E402


RUN_SLUG = "hot_structural_followup_20260503"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "HOT_STRUCTURAL_FOLLOWUP_20260503.md"

TARGET_LEGS = (
    "nq_ny_orb",
    "es_ny_orb",
    "gc_ny_orb",
    "gc_asia_orb",
)

MAX_COMBO_GATES = 16
MAX_COMBO_SIZE = 4


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return default
    return val if math.isfinite(val) else default


def _metric_sort(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        _finite(row.get("score")),
        _finite(row.get("last1_calmar")),
        _finite(row.get("last1_net_r")),
    )


def _safe_json(data: Any) -> Any:
    return seq._safe_json(data)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    return seq._markdown_table(rows, columns)


def _event_not(*names: str):
    name_set = set(names)

    def pred(features: dict[str, Any], _trade: Any) -> bool:
        if "fomc" in name_set and bool(features.get("is_fomc")):
            return False
        if "cpi" in name_set and bool(features.get("is_cpi")):
            return False
        if "nfp" in name_set and bool(features.get("is_nfp")):
            return False
        if "ppi" in name_set and bool(features.get("is_ppi")):
            return False
        return True

    return pred


def _dom_between(lo: int, hi: int):
    return lambda features, _trade: lo <= int(features.get("dom", 0) or 0) <= hi


def _dist_between(lo: float | None = None, hi: float | None = None):
    return seq._has("signal_dist_orb_pct", lo=lo, hi=hi)


def _gate_specs_for_leg(leg_key: str, session_name: str) -> list[seq.GateSpec]:
    gates: list[seq.GateSpec] = [
        seq.GateSpec("calendar_news", "exclude_fomc", "exclude FOMC", _event_not("fomc"), "news", 1),
        seq.GateSpec("calendar_news", "exclude_cpi", "exclude CPI", _event_not("cpi"), "news", 2),
        seq.GateSpec("calendar_news", "exclude_nfp", "exclude NFP", _event_not("nfp"), "news", 3),
        seq.GateSpec("calendar_news", "exclude_ppi", "exclude PPI", _event_not("ppi"), "news", 4),
        seq.GateSpec("calendar_news", "exclude_cpi_nfp", "exclude CPI+NFP", _event_not("cpi", "nfp"), "news", 5),
        seq.GateSpec("calendar_news", "exclude_fomc_cpi", "exclude FOMC+CPI", _event_not("fomc", "cpi"), "news", 6),
        seq.GateSpec("calendar_news", "exclude_fomc_nfp", "exclude FOMC+NFP", _event_not("fomc", "nfp"), "news", 7),
        seq.GateSpec("calendar_news", "exclude_cpi_nfp_ppi", "exclude CPI+NFP+PPI", _event_not("cpi", "nfp", "ppi"), "news", 8),
        seq.GateSpec("calendar_news", "exclude_all_news", "exclude FOMC+CPI+NFP+PPI", _event_not("fomc", "cpi", "nfp", "ppi"), "news", 9),
        seq.GateSpec("calendar_news", "only_dom_1_10", "only day-of-month 1-10", _dom_between(1, 10), "dom", 1),
        seq.GateSpec("calendar_news", "only_dom_11_20", "only day-of-month 11-20", _dom_between(11, 20), "dom", 2),
        seq.GateSpec("calendar_news", "only_dom_21_31", "only day-of-month 21-31", _dom_between(21, 31), "dom", 3),
        seq.GateSpec("calendar_news", "exclude_dom_1_3", "exclude day-of-month 1-3", lambda f, t: not _dom_between(1, 3)(f, t), "dom", 4),
        seq.GateSpec("calendar_news", "exclude_dom_25_31", "exclude day-of-month 25-31", lambda f, t: not _dom_between(25, 31)(f, t), "dom", 5),
        seq.GateSpec("prior_day", "prior_not_inside_day", "exclude prior inside day", seq._bool("prior_inside_day", False), "prior_inside", 1),
        seq.GateSpec("prior_day", "prior_inside_day", "only prior inside day", seq._bool("prior_inside_day", True), "prior_inside", 2),
        seq.GateSpec("prior_day", "prior_range_le_50", "prior range pctile <= 50%", seq._has("prior_range_pctile", hi=0.50), "prior_range", 1),
        seq.GateSpec("prior_day", "prior_range_le_67", "prior range pctile <= 67%", seq._has("prior_range_pctile", hi=0.67), "prior_range", 2),
        seq.GateSpec("prior_day", "prior_range_ge_33", "prior range pctile >= 33%", seq._has("prior_range_pctile", lo=0.33), "prior_range", 3),
        seq.GateSpec("prior_day", "prior_range_ge_50", "prior range pctile >= 50%", seq._has("prior_range_pctile", lo=0.50), "prior_range", 4),
        seq.GateSpec("prior_day", "prior_trend_aligned", "prior trend aligns", seq._bool("prior_trend_aligned", True), "prior_trend", 1),
        seq.GateSpec("prior_day", "prior_trend_fade", "prior trend fades", seq._bool("prior_trend_aligned", False), "prior_trend", 2),
        seq.GateSpec("prior_day", "prior_close_extreme", "prior close aligned extreme", seq._bool("prior_close_aligned_extreme", True), "prior_close", 1),
        seq.GateSpec("orb_size", "orb_pctile_le_50", "ORB range pctile <= 50%", seq._has("orb_range_pctile", hi=0.50), "orb_range", 1),
        seq.GateSpec("orb_size", "orb_pctile_le_60", "ORB range pctile <= 60%", seq._has("orb_range_pctile", hi=0.60), "orb_range", 2),
        seq.GateSpec("orb_size", "orb_pctile_le_67", "ORB range pctile <= 67%", seq._has("orb_range_pctile", hi=0.67), "orb_range", 3),
        seq.GateSpec("orb_size", "orb_pctile_le_75", "ORB range pctile <= 75%", seq._has("orb_range_pctile", hi=0.75), "orb_range", 4),
        seq.GateSpec("orb_size", "orb_pctile_le_80", "ORB range pctile <= 80%", seq._has("orb_range_pctile", hi=0.80), "orb_range", 5),
        seq.GateSpec("orb_size", "orb_pctile_ge_33", "ORB range pctile >= 33%", seq._has("orb_range_pctile", lo=0.33), "orb_range", 6),
        seq.GateSpec("orb_size", "orb_pctile_ge_50", "ORB range pctile >= 50%", seq._has("orb_range_pctile", lo=0.50), "orb_range", 7),
        seq.GateSpec("signal_shape", "signal_outside_orb", "signal closes outside ORB", seq._bool("signal_closes_outside_orb", True), "dist", 1),
        seq.GateSpec("signal_shape", "dist_orb_0_50", "signal distance 0-50% ORB", _dist_between(0.0, 50.0), "dist", 2),
        seq.GateSpec("signal_shape", "dist_orb_0_100", "signal distance 0-100% ORB", _dist_between(0.0, 100.0), "dist", 3),
        seq.GateSpec("signal_shape", "dist_orb_ge_25", "signal distance >= 25% ORB", _dist_between(25.0, None), "dist", 4),
        seq.GateSpec("signal_shape", "dist_orb_ge_50", "signal distance >= 50% ORB", _dist_between(50.0, None), "dist", 5),
        seq.GateSpec("signal_shape", "body_ge_40", "signal body >= 40%", seq._has("signal_body_pct", lo=0.40), "body", 1),
        seq.GateSpec("signal_shape", "body_ge_50", "signal body >= 50%", seq._has("signal_body_pct", lo=0.50), "body", 2),
        seq.GateSpec("signal_shape", "body_ge_60", "signal body >= 60%", seq._has("signal_body_pct", lo=0.60), "body", 3),
        seq.GateSpec("signal_shape", "close_strength_ge_60", "signal close strength >= 60%", seq._has("signal_close_strength", lo=0.60), "close_strength", 1),
        seq.GateSpec("signal_shape", "close_strength_ge_70", "signal close strength >= 70%", seq._has("signal_close_strength", lo=0.70), "close_strength", 2),
        seq.GateSpec("signal_shape", "close_strength_ge_80", "signal close strength >= 80%", seq._has("signal_close_strength", lo=0.80), "close_strength", 3),
        seq.GateSpec("signal_shape", "adverse_wick_le_20", "adverse wick <= 20%", seq._has("signal_adverse_wick_pct", hi=0.20), "wick", 1),
        seq.GateSpec("signal_shape", "adverse_wick_le_35", "adverse wick <= 35%", seq._has("signal_adverse_wick_pct", hi=0.35), "wick", 2),
        seq.GateSpec("signal_shape", "adverse_wick_le_50", "adverse wick <= 50%", seq._has("signal_adverse_wick_pct", hi=0.50), "wick", 3),
    ]
    if session_name == "NY":
        gates.extend(
            [
                seq.GateSpec("session_context", "asia_range_le_50", "Asia range pctile <= 50%", seq._has("asia_range_pctile", hi=0.50), "asia_range", 1),
                seq.GateSpec("session_context", "asia_range_le_67", "Asia range pctile <= 67%", seq._has("asia_range_pctile", hi=0.67), "asia_range", 2),
                seq.GateSpec("session_context", "asia_range_ge_50", "Asia range pctile >= 50%", seq._has("asia_range_pctile", lo=0.50), "asia_range", 3),
                seq.GateSpec("session_context", "ny_open_inside_asia", "NY open inside Asia range", seq._bool("ny_open_inside_asia", True), "ny_open_asia", 1),
                seq.GateSpec("session_context", "asia_trend_aligned", "Asia trend aligns", seq._bool("asia_trend_aligned", True), "asia_trend", 1),
                seq.GateSpec("session_context", "asia_trend_fade", "Asia trend fades", seq._bool("asia_trend_aligned", False), "asia_trend", 2),
            ]
        )
    else:
        gates.extend(
            [
                seq.GateSpec("session_context", "asia_prior_trend_aligned", "Asia prior RTH trend aligns", seq._bool("prior_trend_aligned", True), "asia_prior_trend", 1),
                seq.GateSpec("session_context", "asia_prior_trend_fade", "Asia prior RTH trend fades", seq._bool("prior_trend_aligned", False), "asia_prior_trend", 2),
            ]
        )

    # Keep the search sympathetic to the prior positive lead for each leg.
    if leg_key == "es_ny_orb":
        gates.append(seq.GateSpec("seed_combo", "fomc_plus_outside", "exclude FOMC + signal outside ORB", seq._and(_event_not("fomc"), seq._bool("signal_closes_outside_orb", True)), "seed", 1))
    elif leg_key == "gc_ny_orb":
        gates.append(seq.GateSpec("seed_combo", "cpi_nfp_plus_outside", "exclude CPI/NFP + signal outside ORB", seq._and(_event_not("cpi", "nfp"), seq._bool("signal_closes_outside_orb", True)), "seed", 1))
    elif leg_key == "gc_asia_orb":
        gates.append(seq.GateSpec("seed_combo", "cpi_nfp_plus_not_inside", "exclude CPI/NFP + no prior inside day", seq._and(_event_not("cpi", "nfp"), seq._bool("prior_inside_day", False)), "seed", 1))
    elif leg_key == "nq_ny_orb":
        gates.append(seq.GateSpec("seed_combo", "cpi_nfp_plus_wick35", "exclude CPI/NFP + adverse wick <=35%", seq._and(_event_not("cpi", "nfp"), seq._has("signal_adverse_wick_pct", hi=0.35)), "seed", 1))
    return gates


def _apply_combo(trades: list[Any], feature_rows: dict[Any, dict[str, Any]], gates: tuple[seq.GateSpec, ...]) -> list[Any]:
    out = trades
    for gate in gates:
        out = seq._apply_gate(out, feature_rows, gate)
    return out


def _score(
    *,
    hot: seq.HotLeg,
    stage: str,
    gate_id: str,
    family: str,
    label: str,
    gates: tuple[seq.GateSpec, ...],
    trades: list[Any],
    base_metrics: dict[str, dict[str, Any]],
    last1_start: str,
    last2_start: str,
    end_inclusive: str,
) -> dict[str, Any]:
    row = seq._score_row(
        hot=hot,
        gate_id=gate_id,
        family=family,
        label=label,
        stage=stage,
        component_gates=tuple(gate.gate_id for gate in gates),
        trades=trades,
        base_metrics=base_metrics,
        last1_start=last1_start,
        last2_start=last2_start,
        end_inclusive=end_inclusive,
    )
    return {**row, "surface": "n/a", "plateau_ratio": None, "neighbor_count": 0}


def _combo_candidates(oat_rows: list[dict[str, Any]], gate_by_id: dict[str, seq.GateSpec]) -> list[seq.GateSpec]:
    rows = [
        row for row in oat_rows
        if row["eligible_min_fills"] and _finite(row["last1_net_r"]) > 0
    ]
    rows.sort(key=_metric_sort, reverse=True)
    selected: list[str] = []
    for row in rows:
        if _finite(row["delta_last1_net_r"]) > 0 and row["gate_id"] in gate_by_id:
            selected.append(row["gate_id"])
    for row in rows:
        if row["gate_id"] in gate_by_id:
            selected.append(row["gate_id"])
        if len(dict.fromkeys(selected)) >= MAX_COMBO_GATES:
            break
    deduped = list(dict.fromkeys(selected))[:MAX_COMBO_GATES]
    return [gate_by_id[gate_id] for gate_id in deduped]


def _combo_valid(gates: tuple[seq.GateSpec, ...]) -> bool:
    groups = [gate.ordered_group or gate.gate_id for gate in gates]
    return len(groups) == len(set(groups))


def _surface_for_combo(row: dict[str, Any], row_by_components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    components = tuple(str(row.get("component_gates", "")).split("|")) if row.get("component_gates") else ()
    cand_calmar = _finite(row.get("last1_calmar"))
    neighbors: list[float] = []
    if len(components) >= 3 and cand_calmar > 0:
        for idx in range(len(components)):
            reduced = "|".join(component for j, component in enumerate(components) if j != idx)
            other = row_by_components.get(reduced)
            if other is not None:
                neighbors.append(_finite(other.get("last1_calmar")))
    if not neighbors or cand_calmar <= 0:
        return {"surface": "cliff", "plateau_ratio": 0.0, "neighbor_count": len(neighbors)}
    ratios = [value / cand_calmar for value in neighbors]
    median_ratio = float(np.median(ratios))
    ge80 = sum(1 for value in ratios if value >= 0.80)
    ge60 = sum(1 for value in ratios if value >= 0.60)
    if len(ratios) >= 3 and median_ratio >= 0.70 and ge80 >= 2:
        surface = "curve"
    elif len(ratios) >= 2 and median_ratio >= 0.50 and ge60 >= 2:
        surface = "soft_curve"
    else:
        surface = "cliff"
    return {
        "surface": surface,
        "plateau_ratio": round(median_ratio, 3),
        "neighbor_count": len(neighbors),
        "neighbor_ge80_count": ge80,
        "neighbor_ge60_count": ge60,
    }


def _write_report(
    *,
    hot_legs: list[seq.HotLeg],
    rows: list[dict[str, Any]],
    selected_manifest: dict[str, Any],
    last1_start: str,
    last2_start: str,
    end_inclusive: str,
) -> None:
    lines = [
        "# Hot Structural Follow-Up",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Last-1y window: `{last1_start}` to `{end_inclusive}`",
        f"- Last-2y/context window: `{last2_start}` to `{end_inclusive}`",
        "- Scope: targeted second pass on the positive structural leads from `HOT_STRUCTURAL_SEQUENCE_20260503`.",
        "- Legs: `NQ NY ORB`, `ES NY ORB`, `GC NY ORB`, `GC Asia ORB`.",
        "- Tested refined news/event exclusions, day-of-month cuts, ORB-size thresholds, prior-day filters, Asia/NY context, and signal-shape thresholds.",
        "- Still TESTING-only and optimized directly on the hot one-year window.",
        "",
        "## Best Net Additions",
        "",
    ]
    summary_rows: list[dict[str, Any]] = []
    for hot in hot_legs:
        base = next(row for row in rows if row["leg"] == hot.leg.key and row["stage"] == "baseline")
        leg_rows = [
            row for row in rows
            if row["leg"] == hot.leg.key
            and row["stage"] != "baseline"
            and row["eligible_min_fills"]
            and _finite(row["last1_net_r"]) > 0
        ]
        positive = [row for row in leg_rows if _finite(row["delta_last1_net_r"]) > 0]
        positive.sort(key=lambda row: (_finite(row["delta_last1_net_r"]), _finite(row["last1_calmar"]), _finite(row["score"])), reverse=True)
        pick = positive[0] if positive else None
        summary_rows.append(
            {
                "leg": hot.leg.label,
                "pick": pick["gate_id"] if pick else "none",
                "stage": pick["stage"] if pick else "-",
                "surface": pick.get("surface", "n/a") if pick else "-",
                "fills": pick["last1_fills"] if pick else "-",
                "net_r": pick["last1_net_r"] if pick else "-",
                "delta_r": pick["delta_last1_net_r"] if pick else "-",
                "calmar": pick["last1_calmar"] if pick else "-",
                "pf": pick["last1_pf"] if pick else "-",
                "dd": pick["last1_dd_r"] if pick else "-",
                "base_r": base["last1_net_r"],
            }
        )
    lines.append(_markdown_table(summary_rows, ["leg", "pick", "stage", "surface", "fills", "net_r", "delta_r", "calmar", "pf", "dd", "base_r"]))

    lines.extend(["", "## Best Score / DD Tilt", ""])
    score_rows: list[dict[str, Any]] = []
    for hot in hot_legs:
        base = next(row for row in rows if row["leg"] == hot.leg.key and row["stage"] == "baseline")
        leg_rows = [
            row for row in rows
            if row["leg"] == hot.leg.key
            and row["stage"] != "baseline"
            and row["eligible_min_fills"]
            and _finite(row["last1_net_r"]) > 0
        ]
        leg_rows.sort(key=_metric_sort, reverse=True)
        pick = leg_rows[0] if leg_rows else base
        score_rows.append(
            {
                "leg": hot.leg.label,
                "pick": pick["gate_id"],
                "stage": pick["stage"],
                "surface": pick.get("surface", "n/a"),
                "fills": pick["last1_fills"],
                "net_r": pick["last1_net_r"],
                "delta_r": pick["delta_last1_net_r"],
                "calmar": pick["last1_calmar"],
                "pf": pick["last1_pf"],
                "dd": pick["last1_dd_r"],
                "base_r": base["last1_net_r"],
            }
        )
    lines.append(_markdown_table(score_rows, ["leg", "pick", "stage", "surface", "fills", "net_r", "delta_r", "calmar", "pf", "dd", "base_r"]))

    for hot in hot_legs:
        lines.extend(["", f"## {hot.leg.label}", ""])
        base = next(row for row in rows if row["leg"] == hot.leg.key and row["stage"] == "baseline")
        lines.append(
            f"Baseline after existing `{hot.base_gate}` gate: "
            f"{base['last1_fills']} fills, `{base['last1_net_r']}R`, Calmar `{base['last1_calmar']}`, "
            f"PF `{base['last1_pf']}`, DD `{base['last1_dd_r']}R`."
        )
        for title, stage in (("Top OAT", "oat"), ("Top Combos", "combo")):
            leg_rows = [
                row for row in rows
                if row["leg"] == hot.leg.key
                and row["stage"] == stage
                and row["eligible_min_fills"]
                and _finite(row["last1_net_r"]) > 0
            ]
            leg_rows.sort(key=lambda row: (_finite(row["delta_last1_net_r"]), _finite(row["last1_calmar"]), _finite(row["score"])), reverse=True)
            lines.extend(["", f"### {title}", ""])
            lines.append(
                _markdown_table(
                    leg_rows[:12],
                    [
                        "gate_id",
                        "family",
                        "surface",
                        "last1_fills",
                        "last1_net_r",
                        "delta_last1_net_r",
                        "last1_calmar",
                        "last1_pf",
                        "last1_dd_r",
                        "last2_net_r",
                        "plateau_ratio",
                        "component_gates",
                    ],
                )
            )
        lines.extend(
            [
                "",
                "<details><summary>Selected combo gates</summary>",
                "",
                "```json",
                json.dumps(selected_manifest.get(hot.leg.key, {}), indent=2, sort_keys=True),
                "```",
                "",
                "</details>",
            ]
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def _write_asset_notes(hot_legs: list[seq.HotLeg], rows: list[dict[str, Any]], last1_start: str, end_inclusive: str) -> None:
    by_symbol: dict[str, list[seq.HotLeg]] = defaultdict(list)
    for hot in hot_legs:
        by_symbol[hot.leg.symbol].append(hot)
    paths = {"NQ": prev.NQ_LEARNINGS_PATH, "ES": prev.ES_LEARNINGS_PATH, "GC": prev.GC_LEARNINGS_PATH}
    for symbol, symbol_legs in by_symbol.items():
        lines = [
            "",
            f"- **Hot structural follow-up** (2026-05-03): `backtesting/learnings/reports/HOT_STRUCTURAL_FOLLOWUP_20260503.md`",
            f"  - Window: `{last1_start}` to `{end_inclusive}`. Targeted second pass around positive structural gates from the hot structural sequence.",
        ]
        for hot in symbol_legs:
            leg_rows = [
                row for row in rows
                if row["leg"] == hot.leg.key
                and row["stage"] != "baseline"
                and row["eligible_min_fills"]
                and _finite(row["last1_net_r"]) > 0
                and _finite(row["delta_last1_net_r"]) > 0
            ]
            leg_rows.sort(key=lambda row: (_finite(row["delta_last1_net_r"]), _finite(row["last1_calmar"]), _finite(row["score"])), reverse=True)
            if not leg_rows:
                lines.append(f"  - {hot.leg.label}: no refined structural gate improved net R over the hot baseline.")
                continue
            row = leg_rows[0]
            lines.append(
                f"  - {hot.leg.label}: best refined structural `{row['gate_id']}` -> "
                f"{row['last1_fills']} fills, `{row['last1_net_r']}R`, delta `{row['delta_last1_net_r']}R`, "
                f"Calmar `{row['last1_calmar']}`, PF `{row['last1_pf']}`, DD `{row['last1_dd_r']}R`, "
                f"surface `{row.get('surface', 'n/a')}`; TESTING-only."
            )
        path = paths[symbol]
        existing = path.read_text().rstrip()
        marker = "- **Hot structural follow-up** (2026-05-03):"
        if marker in existing:
            existing = existing.split(marker)[0].rstrip()
        path.write_text(existing + "\n" + "\n".join(lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    hot_legs_all, squeeze_summary, _previous_summary = seq._load_hot_legs()
    hot_legs = [hot for hot in hot_legs_all if hot.leg.key in TARGET_LEGS]
    last1_start = str(squeeze_summary["period_start"])
    end_inclusive = str(squeeze_summary["period_end"])
    end_exclusive = str(squeeze_summary["end_exclusive"])
    last2_start = (pd.Timestamp(end_inclusive) - pd.Timedelta(days=730)).date().isoformat()
    prev.LOAD_START = seq.STRUCTURAL_LOAD_START

    print(f"Hot structural follow-up: {last1_start} to {end_inclusive}", flush=True)
    print(f"Targets: {', '.join(hot.leg.label for hot in hot_legs)}", flush=True)

    loaded_cache: dict[tuple[str, str], prev.LoadedData] = {}
    all_rows: list[dict[str, Any]] = []
    selected_manifest: dict[str, Any] = {}

    for hot in hot_legs:
        leg = hot.leg
        print(f"\n=== {leg.label} ===", flush=True)
        key = (leg.symbol, leg.timeframe)
        if key not in loaded_cache:
            print(f"  loading {leg.symbol} {leg.timeframe}", flush=True)
            loaded_cache[key] = prev._load_data(leg.symbol, leg.timeframe, end_exclusive, last1_start)
        loaded = loaded_cache[key]

        variant = prev.VariantSpec(
            leg.key,
            "hot_structural_followup_base",
            "baseline",
            "baseline",
            "current hot squeeze winner",
            ("hot_structural_followup_base",),
            hot.config,
        )
        results = prev._run_variants(leg, loaded, [variant], start_date=last2_start, end_date=end_exclusive)
        raw_trades = results[variant.config.name]
        base_trades = squeeze._apply_gate(raw_trades, loaded.regime_lookup, hot.base_gate)
        context = seq._feature_context(loaded.df_base, hot.config)
        feature_rows = seq._feature_rows_for_trades(base_trades, loaded.df_base, context)
        base_metrics = {
            "last1": seq._metrics_for(base_trades, last1_start, end_inclusive),
            "last2": seq._metrics_for(base_trades, last2_start, end_inclusive),
        }
        all_rows.append(
            _score(
                hot=hot,
                stage="baseline",
                gate_id="baseline",
                family="baseline",
                label="current hot squeeze winner plus existing regime gate",
                gates=(),
                trades=base_trades,
                base_metrics=base_metrics,
                last1_start=last1_start,
                last2_start=last2_start,
                end_inclusive=end_inclusive,
            )
        )

        gates = _gate_specs_for_leg(leg.key, hot.config.sessions[0].name)
        gate_by_id = {gate.gate_id: gate for gate in gates}
        print(f"  OAT gates: {len(gates)}", flush=True)
        oat_rows: list[dict[str, Any]] = []
        for gate in gates:
            row = _score(
                hot=hot,
                stage="oat",
                gate_id=gate.gate_id,
                family=gate.family,
                label=gate.label,
                gates=(gate,),
                trades=seq._apply_gate(base_trades, feature_rows, gate),
                base_metrics=base_metrics,
                last1_start=last1_start,
                last2_start=last2_start,
                end_inclusive=end_inclusive,
            )
            oat_rows.append(row)
            all_rows.append(row)

        combo_gates = _combo_candidates(oat_rows, gate_by_id)
        selected_manifest[leg.key] = {
            "base_gate": hot.base_gate,
            "base_variant": hot.row.get("variant_id"),
            "combo_gate_ids": [gate.gate_id for gate in combo_gates],
        }
        print(f"  combo gates: {len(combo_gates)}", flush=True)
        combo_rows: list[dict[str, Any]] = []
        for size in range(2, min(MAX_COMBO_SIZE, len(combo_gates)) + 1):
            for combo in combinations(combo_gates, size):
                if not _combo_valid(combo):
                    continue
                combo_id = "combo__" + "__".join(gate.gate_id for gate in combo)
                row = _score(
                    hot=hot,
                    stage="combo",
                    gate_id=combo_id,
                    family="combo",
                    label=" + ".join(gate.label for gate in combo),
                    gates=combo,
                    trades=_apply_combo(base_trades, feature_rows, combo),
                    base_metrics=base_metrics,
                    last1_start=last1_start,
                    last2_start=last2_start,
                    end_inclusive=end_inclusive,
                )
                combo_rows.append(row)
        row_by_components = {row["component_gates"]: row for row in combo_rows}
        for row in combo_rows:
            all_rows.append({**row, **_surface_for_combo(row, row_by_components)})
        print(f"  combo rows: {len(combo_rows)}", flush=True)

    df = pd.DataFrame(all_rows)
    df.to_csv(RESULT_DIR / "score_rows.csv", index=False)
    (RESULT_DIR / "selected_followup_gates.json").write_text(json.dumps(_safe_json(selected_manifest), indent=2, sort_keys=True))
    summary = {
        "run_slug": RUN_SLUG,
        "last1_start": last1_start,
        "last2_start": last2_start,
        "period_end": end_inclusive,
        "end_exclusive": end_exclusive,
        "target_legs": TARGET_LEGS,
        "selected_followup_gates": selected_manifest,
        "best_net_by_leg": {},
        "best_score_by_leg": {},
    }
    for hot in hot_legs:
        leg_rows = df[
            (df["leg"] == hot.leg.key)
            & (df["stage"] != "baseline")
            & (df["eligible_min_fills"])
            & (df["last1_net_r"] > 0)
        ].copy()
        if leg_rows.empty:
            continue
        positive = leg_rows[leg_rows["delta_last1_net_r"] > 0].sort_values(
            ["delta_last1_net_r", "last1_calmar", "score"],
            ascending=False,
        )
        if not positive.empty:
            summary["best_net_by_leg"][hot.leg.key] = positive.iloc[0].to_dict()
        score = leg_rows.sort_values(["score", "last1_calmar", "last1_net_r"], ascending=False)
        summary["best_score_by_leg"][hot.leg.key] = score.iloc[0].to_dict()
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True))

    _write_report(
        hot_legs=hot_legs,
        rows=all_rows,
        selected_manifest=selected_manifest,
        last1_start=last1_start,
        last2_start=last2_start,
        end_inclusive=end_inclusive,
    )
    _write_asset_notes(hot_legs, all_rows, last1_start, end_inclusive)
    print(f"\nDONE: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
