#!/usr/bin/env python3
"""Native single-target exit sweep for ALPHA_V1 legs.

Research artifact only. Does not edit execution configs.

Compares each current split TP1/TP2 ladder against:
1. full-position single target at the current TP1 distance
2. a focused sweep of native ``exit_mode='single_target'`` RR targets

The five-leg scope matches the 2026-05-05 target work:
- active ALPHA_V1 NQ NY HTF-LSI
- active ALPHA_V1 NQ Asia ORB
- active ALPHA_V1 ES Asia ORB
- active ALPHA_V1 ES NY ORB
- conditional NQ NY ORB R11
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import run_alpha_v1_exit_structure_analysis as exit_struct  # noqa: E402
import run_alpha_v1_exit_target_mfe_sweep_20260505 as target_sweep  # noqa: E402
from orb_backtest.config import StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.export import results_to_dict, save_backtest_result  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "alpha_v1_single_target_sweep_20260506"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_SINGLE_TARGET_SWEEP_20260506.md"

FULL_START = "2016-04-17"
END_INCLUSIVE = "2026-03-24"
END_EXCLUSIVE = "2026-03-25"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"
WORKERS = 8

WINDOWS = {
    "full": (FULL_START, END_INCLUSIVE),
    "last_2y": (LAST_2Y_START, END_INCLUSIVE),
    "last_1y": (LAST_1Y_START, END_INCLUSIVE),
}


@dataclass(frozen=True)
class SingleTargetPlan:
    leg: exit_struct.LegSpec
    target_values: tuple[float, ...]
    deployability: str
    live_support_notes: str
    exact_replay_required: str

    @property
    def baseline_rr(self) -> float:
        return float(self.leg.config.rr)

    @property
    def baseline_tp1_r(self) -> float:
        return round(float(self.leg.config.rr * self.leg.config.tp1_ratio), 4)


@dataclass(frozen=True)
class Variant:
    plan: SingleTargetPlan
    variant_id: str
    structure: str
    target_r: float
    config: StrategyConfig


def _fmt_float(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text.replace(".", "p")


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        value = float(data)
        return value if math.isfinite(value) else None
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    return data


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _pct(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else 100.0 * float(numerator) / float(denominator)


def build_plans() -> list[SingleTargetPlan]:
    leg_plans = target_sweep.build_leg_plans()
    by_key = {plan.leg.key: plan for plan in leg_plans}

    return [
        SingleTargetPlan(
            leg=by_key["nq_ny_htf_lsi"].leg,
            target_values=(1.0, 1.2, 1.25, 1.4, 1.5, 1.6, 1.75, 1.8, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0),
            deployability="live_native",
            live_support_notes="Native single-target support exists in research and live HTF-LSI execution.",
            exact_replay_required="yes_before_live_change",
        ),
        SingleTargetPlan(
            leg=by_key["nq_asia_orb"].leg,
            target_values=(1.0, 1.25, 1.5, 1.75, 1.8, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0),
            deployability="live_native",
            live_support_notes="Native single-target support exists in research and live ORB execution.",
            exact_replay_required="yes_before_live_change",
        ),
        SingleTargetPlan(
            leg=by_key["es_asia_cont"].leg,
            target_values=(1.0, 1.05, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0),
            deployability="live_native",
            live_support_notes="Native single-target support exists in research and live ORB execution.",
            exact_replay_required="yes_before_live_change",
        ),
        SingleTargetPlan(
            leg=by_key["es_ny_cont"].leg,
            target_values=(1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0),
            deployability="live_native",
            live_support_notes="Native single-target support exists in research and live ORB execution.",
            exact_replay_required="yes_before_live_change",
        ),
        SingleTargetPlan(
            leg=by_key["nq_ny_orb_r11"].leg,
            target_values=(1.0, 1.25, 1.4, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0, 4.5),
            deployability="live_native",
            live_support_notes="Native single-target support exists in research and live ORB execution.",
            exact_replay_required="yes_before_live_promotion",
        ),
    ]


def _unique_targets(plan: SingleTargetPlan) -> tuple[float, ...]:
    values = {round(float(v), 4) for v in plan.target_values if float(v) >= 1.0}
    values.add(plan.baseline_tp1_r)
    values.add(plan.baseline_rr)
    return tuple(sorted(values))


def build_variants(plans: list[SingleTargetPlan]) -> list[Variant]:
    variants: list[Variant] = []
    for plan in plans:
        baseline_name = f"ALPHA V1 SingleTarget Sweep {plan.leg.label} Current Split 20260506"[:240]
        variants.append(
            Variant(
                plan=plan,
                variant_id="current_split",
                structure="current_split",
                target_r=plan.baseline_rr,
                config=replace(plan.leg.config, name=baseline_name, exit_mode="split"),
            )
        )
        for target_r in _unique_targets(plan):
            name = (
                f"ALPHA V1 SingleTarget Sweep {plan.leg.label} "
                f"Target {_fmt_float(target_r)}R 20260506"
            )[:240]
            cfg = replace(
                plan.leg.config,
                name=name,
                rr=float(target_r),
                tp1_ratio=1.0,
                exit_mode="single_target",
            )
            marker = "single_at_current_tp1" if math.isclose(target_r, plan.baseline_tp1_r, abs_tol=1e-9) else "single_sweep"
            variants.append(
                Variant(
                    plan=plan,
                    variant_id=f"single_target_{_fmt_float(target_r)}r",
                    structure=marker,
                    target_r=float(target_r),
                    config=cfg,
                )
            )
    return variants


def _slice(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end]


def _exit_stats(trades: list[TradeResult]) -> dict[str, Any]:
    filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    counts: dict[str, int] = {}
    for trade in filled:
        name = EXIT_NAMES.get(trade.exit_type, str(trade.exit_type))
        counts[name] = counts.get(name, 0) + 1
    total = len(filled)
    full_target = counts.get("tp1_tp2", 0) + counts.get("tp2_single", 0)
    tp1_be = counts.get("tp1_be", 0)
    tp1_eod = counts.get("tp1_eod", 0)
    sl = counts.get("sl", 0)
    eod = counts.get("eod", 0)
    return {
        "exit_counts": counts,
        "target_count": full_target,
        "target_rate_pct": _round(_pct(full_target, total), 2),
        "tp1_be_count": tp1_be,
        "tp1_be_rate_pct": _round(_pct(tp1_be, total), 2),
        "tp1_eod_count": tp1_eod,
        "tp1_eod_rate_pct": _round(_pct(tp1_eod, total), 2),
        "sl_count": sl,
        "sl_rate_pct": _round(_pct(sl, total), 2),
        "eod_count": eod,
        "eod_rate_pct": _round(_pct(eod, total), 2),
    }


def _metric_row(variant: Variant, trades: list[TradeResult], window: str, start: str, end: str) -> dict[str, Any]:
    selected = _slice(trades, start, end)
    metrics = compute_metrics(selected)
    max_dd_r = abs(float(metrics["max_drawdown_r"]))
    total = int(metrics["total_trades"])
    return {
        "leg_key": variant.plan.leg.key,
        "leg_label": variant.plan.leg.label,
        "symbol": variant.plan.leg.symbol,
        "variant_id": variant.variant_id,
        "structure": variant.structure,
        "window": window,
        "target_r": float(variant.target_r),
        "baseline_rr": variant.plan.baseline_rr,
        "baseline_tp1_r": variant.plan.baseline_tp1_r,
        "rr": float(variant.config.rr),
        "tp1_ratio": float(variant.config.tp1_ratio),
        "exit_mode": variant.config.exit_mode,
        "trades": total,
        "signals": int(metrics["total_signals"]),
        "no_fills": int(metrics["no_fills"]),
        "net_r": _round(metrics["total_r"], 3),
        "win_rate_pct": _round(float(metrics["win_rate"]) * 100.0, 2),
        "profit_factor": _round(metrics["profit_factor"], 4),
        "avg_r": _round(metrics["avg_r"], 4),
        "sharpe_ratio": _round(metrics["sharpe_ratio"], 4),
        "max_dd_r": _round(max_dd_r, 3),
        "calmar_ratio": _round(metrics["calmar_ratio"], 4),
        "negative_years": int(sum(1 for value in (metrics.get("r_by_year") or {}).values() if value < 0)),
        "r_by_year": metrics.get("r_by_year") or {},
        **_exit_stats(selected),
        "deployability": variant.plan.deployability,
        "live_support_notes": variant.plan.live_support_notes,
        "exact_replay_required": variant.plan.exact_replay_required,
    }


def _material_delta(best: dict[str, Any], baseline: dict[str, Any]) -> str:
    delta_r = float(best["net_r"]) - float(baseline["net_r"])
    delta_pf = float(best["profit_factor"]) - float(baseline["profit_factor"])
    delta_dd = float(best["max_dd_r"]) - float(baseline["max_dd_r"])
    if delta_r >= 10.0 and delta_pf >= -0.03 and delta_dd <= 1.0:
        return "material_upgrade"
    if delta_r >= 5.0 and delta_pf >= 0.02 and delta_dd <= 1.0:
        return "upgrade"
    if delta_r >= -3.0 and delta_pf >= -0.03 and delta_dd < -0.5:
        return "smoother_tradeoff"
    if delta_r <= -5.0 or delta_pf <= -0.05:
        return "inferior"
    return "mixed"


def _score_single(row: dict[str, Any], baseline: dict[str, Any]) -> float:
    net_r = float(row["net_r"] or 0.0)
    pf = float(row["profit_factor"] or 0.0)
    dd = float(row["max_dd_r"] or 0.0)
    calmar = float(row["calmar_ratio"] or 0.0)
    target_pct = float(row["target_rate_pct"] or 0.0)
    base_net = float(baseline["net_r"] or 0.0)
    base_pf = float(baseline["profit_factor"] or 0.0)
    base_dd = float(baseline["max_dd_r"] or 0.0)
    penalty = 0.0
    if net_r < 0.90 * base_net:
        penalty += 40.0
    if pf < base_pf - 0.10:
        penalty += 30.0
    if dd > 1.25 * base_dd:
        penalty += 20.0
    if int(row["negative_years"]) > int(baseline["negative_years"]) + 1:
        penalty += 20.0
    return 100.0 * calmar + 0.45 * net_r + 8.0 * pf + 0.20 * target_pct - 4.0 * dd - penalty


def rank_rows(metric_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_leg: dict[str, list[dict[str, Any]]] = {}
    full_rows = [row for row in metric_rows if row["window"] == "full"]
    for row in full_rows:
        by_leg.setdefault(str(row["leg_key"]), []).append(row)

    best_rows: list[dict[str, Any]] = []
    ranked_rows: list[dict[str, Any]] = []
    for leg_key, rows in by_leg.items():
        baseline = next(row for row in rows if row["variant_id"] == "current_split")
        single_rows = [row for row in rows if row["exit_mode"] == "single_target"]
        by_variant_window = {
            (row["leg_key"], row["variant_id"], row["window"]): row
            for row in metric_rows
        }
        for row in single_rows:
            row["score"] = _round(_score_single(row, baseline), 4)
            row["delta_r"] = _round(float(row["net_r"]) - float(baseline["net_r"]), 3)
            row["delta_pf"] = _round(float(row["profit_factor"]) - float(baseline["profit_factor"]), 4)
            row["delta_dd"] = _round(float(row["max_dd_r"]) - float(baseline["max_dd_r"]), 3)
            row["material_read"] = _material_delta(row, baseline)
            row["last_2y_net_r"] = by_variant_window[(row["leg_key"], row["variant_id"], "last_2y")]["net_r"]
            row["last_1y_net_r"] = by_variant_window[(row["leg_key"], row["variant_id"], "last_1y")]["net_r"]
            ranked_rows.append(row)

        best_by_score = max(single_rows, key=lambda row: float(row["score"] or 0.0))
        best_by_calmar = max(single_rows, key=lambda row: float(row["calmar_ratio"] or 0.0))
        best_by_net = max(single_rows, key=lambda row: float(row["net_r"] or 0.0))
        at_current_tp1 = next(
            row for row in single_rows
            if math.isclose(float(row["target_r"]), float(baseline["baseline_tp1_r"]), abs_tol=1e-9)
        )
        best_rows.append(
            {
                "leg_key": leg_key,
                "leg_label": baseline["leg_label"],
                "baseline": baseline,
                "single_at_current_tp1": at_current_tp1,
                "best_by_score": best_by_score,
                "best_by_calmar": best_by_calmar,
                "best_by_net": best_by_net,
                "deployability": baseline["deployability"],
                "live_support_notes": baseline["live_support_notes"],
                "exact_replay_required": baseline["exact_replay_required"],
            }
        )
    ranked_rows.sort(key=lambda row: float(row["score"] or 0.0), reverse=True)
    return best_rows, ranked_rows


def _md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    lines = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        cells = []
        for _, key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                value = f"{value:.2f}"
            cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _compact(row: dict[str, Any]) -> str:
    return (
        f"{row['target_r']:g}R "
        f"{float(row['net_r']):+.1f}R PF {float(row['profit_factor']):.2f} "
        f"DD -{float(row['max_dd_r']):.1f}R Target {float(row['target_rate_pct']):.1f}%"
    )


def write_report(best_rows: list[dict[str, Any]], ranked_rows: list[dict[str, Any]]) -> None:
    comparison = []
    for item in best_rows:
        baseline = item["baseline"]
        current_tp1 = item["single_at_current_tp1"]
        best = item["best_by_score"]
        comparison.append(
            {
                "Leg": item["leg_label"],
                "Current Split": _compact(baseline),
                "Single @ TP1": _compact(current_tp1),
                "Best Single": _compact(best),
                "Best Target": f"{best['target_r']:g}R",
                "ΔR": best["delta_r"],
                "ΔPF": best["delta_pf"],
                "ΔDD": best["delta_dd"],
                "Read": best["material_read"],
            }
        )

    top = [
        {
            "Leg": row["leg_label"],
            "Target": f"{row['target_r']:g}R",
            "Net R": row["net_r"],
            "PF": row["profit_factor"],
            "DD": row["max_dd_r"],
            "WR": f"{row['win_rate_pct']:.1f}%",
            "Target%": f"{row['target_rate_pct']:.1f}%",
            "2Y R": row["last_2y_net_r"],
            "Read": row["material_read"],
        }
        for row in ranked_rows[:25]
    ]

    lines = [
        "# ALPHA_V1 Native Single-Target Sweep (2026-05-06)",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Full window: `{FULL_START}` to `{END_INCLUSIVE}`; recent windows start `{LAST_2Y_START}` and `{LAST_1Y_START}`.",
        "- Scope: active ALPHA_V1 legs plus NQ NY ORB R11.",
        "- Structure: current split ladders compared against native `exit_mode=single_target` with `tp1_ratio=1.0` and RR as the only target.",
        "- Ranking: Calmar-first composite, with R/PF/DD penalties versus each leg's current split baseline.",
        "- Deployability: all single-target rows are `live_native`; exact replay is still required before changing live config.",
        "",
        "## Leg Comparison",
        "",
        *_md_table(
            comparison,
            [
                ("Leg", "Leg"),
                ("Current Split", "Current Split"),
                ("Single @ TP1", "Single @ TP1"),
                ("Best Single", "Best Single"),
                ("Best Target", "Best Target"),
                ("ΔR", "ΔR"),
                ("ΔPF", "ΔPF"),
                ("ΔDD", "ΔDD"),
                ("Read", "Read"),
            ],
        ),
        "",
        "## Top Single-Target Rows",
        "",
        *_md_table(
            top,
            [
                ("Leg", "Leg"),
                ("Target", "Target"),
                ("Net R", "Net R"),
                ("PF", "PF"),
                ("DD", "DD"),
                ("WR", "WR"),
                ("Target%", "Target%"),
                ("2Y R", "2Y R"),
                ("Read", "Read"),
            ],
        ),
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def save_selected_backtests(
    *,
    best_rows: list[dict[str, Any]],
    trades_by_name: dict[str, list[TradeResult]],
    variant_by_id: dict[tuple[str, str], Variant],
) -> list[dict[str, str]]:
    saved: list[dict[str, str]] = []
    for item in best_rows:
        for label, row in (
            ("current_split", item["baseline"]),
            ("single_at_current_tp1", item["single_at_current_tp1"]),
            ("best_single_target", item["best_by_score"]),
        ):
            variant = variant_by_id[(str(row["leg_key"]), str(row["variant_id"]))]
            trades = trades_by_name[variant.config.name]
            result = results_to_dict(trades, variant.config, include_trades=True, include_equity_curve=True)
            result_id = save_backtest_result(result)
            saved.append(
                {
                    "leg_key": str(row["leg_key"]),
                    "leg_label": str(row["leg_label"]),
                    "selection": label,
                    "variant_id": str(row["variant_id"]),
                    "result_id": result_id,
                }
            )
    return saved


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    plans = build_plans()
    variants = build_variants(plans)
    variant_by_id = {(variant.plan.leg.key, variant.variant_id): variant for variant in variants}

    print(f"Running {len(variants)} configs across {len(plans)} legs", flush=True)
    print("Loading symbol data...", flush=True)
    symbol_cache: dict[str, exit_struct.SymbolData] = {}
    for symbol in sorted({plan.leg.symbol for plan in plans}):
        data_file = NQ.data_file if symbol == "NQ" else ES.data_file
        symbol_cache[symbol] = exit_struct.load_symbol_data(data_file, start=FULL_START, end=END_EXCLUSIVE)
        data = symbol_cache[symbol]
        print(
            f"  {symbol}: 5m={len(data.df_5m):,} 1m={len(data.df_1m):,} "
            f"1s={len(data.df_1s) if data.df_1s is not None else 0:,}",
            flush=True,
        )

    metric_rows: list[dict[str, Any]] = []
    trades_by_name: dict[str, list[TradeResult]] = {}
    manifest_rows: list[dict[str, Any]] = []

    variants_by_symbol: dict[str, list[Variant]] = {}
    for variant in variants:
        variants_by_symbol.setdefault(variant.plan.leg.symbol, []).append(variant)
        session = variant.config.sessions[0]
        manifest_rows.append(
            {
                "leg_key": variant.plan.leg.key,
                "leg_label": variant.plan.leg.label,
                "variant_id": variant.variant_id,
                "structure": variant.structure,
                "target_r": variant.target_r,
                "symbol": variant.plan.leg.symbol,
                "strategy": variant.config.strategy,
                "session": session.name,
                "entry_window": f"{session.entry_start}-{session.entry_end}",
                "flat_window": f"{session.flat_start}-{session.flat_end}",
                "rr": variant.config.rr,
                "tp1_ratio": variant.config.tp1_ratio,
                "exit_mode": variant.config.exit_mode,
                "deployability": variant.plan.deployability,
                "live_support_notes": variant.plan.live_support_notes,
                "exact_replay_required": variant.plan.exact_replay_required,
            }
        )

    for symbol, symbol_variants in sorted(variants_by_symbol.items()):
        data = symbol_cache[symbol]
        print(f"Running {symbol} sweep: {len(symbol_variants)} configs", flush=True)

        def progress(done: int, total: int) -> None:
            if done == total or done % 10 == 0:
                print(f"  {symbol}: {done}/{total}", flush=True)

        results = run_sweep(
            data.df_5m,
            [variant.config for variant in symbol_variants],
            n_workers=min(WORKERS, max(1, len(symbol_variants))),
            start_date=FULL_START,
            end_date=END_EXCLUSIVE,
            df_1m=data.df_1m,
            df_1s=data.df_1s,
            signal_df_1m=data.df_1m,
            progress_fn=progress,
        )
        variant_by_name = {variant.config.name: variant for variant in symbol_variants}
        for config, trades in results:
            variant = variant_by_name[config.name]
            trades = sorted(trades, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))
            trades_by_name[config.name] = trades
            filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
            for window, (start, end) in WINDOWS.items():
                metric_rows.append(_metric_row(variant, filled, window, start, end))

    best_rows, ranked_rows = rank_rows(metric_rows)
    saved_backtests = save_selected_backtests(
        best_rows=best_rows,
        trades_by_name=trades_by_name,
        variant_by_id=variant_by_id,
    )

    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "run_slug": RUN_SLUG,
        "full_start": FULL_START,
        "end_inclusive": END_INCLUSIVE,
        "variant_count": len(variants),
        "best_rows": best_rows,
        "top_ranked": ranked_rows[:50],
        "saved_backtests": saved_backtests,
        "report_path": str(REPORT_PATH),
        "elapsed_seconds": round(time.time() - started, 2),
    }

    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2), encoding="utf-8")
    pd.DataFrame(manifest_rows).to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(RESULT_DIR / "variant_metrics.csv", index=False)
    pd.DataFrame(ranked_rows).to_csv(RESULT_DIR / "ranked_single_targets.csv", index=False)
    pd.DataFrame(saved_backtests).to_csv(RESULT_DIR / "saved_backtests.csv", index=False)
    write_report(best_rows, ranked_rows)

    print(json.dumps(_safe_json(summary), indent=2), flush=True)
    print(f"Saved report to {REPORT_PATH}", flush=True)
    print(f"Saved artifacts to {RESULT_DIR}", flush=True)


if __name__ == "__main__":
    main()
