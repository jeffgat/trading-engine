#!/usr/bin/env python3
"""MFE diagnostic and exit-target compression sweep for ALPHA_V1 legs.

Research artifact only. Does not edit execution configs.

Passes:
1. Baseline MFE/MAE diagnostic for the current ALPHA_V1 legs plus NQ NY ORB R11.
2. Exit-only engine sweep: hold entries/stops/session filters fixed; vary rr and TP1_R.
3. Edge-ranked comparison against each leg's current target ladder.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import run_alpha_v1_exit_structure_analysis as exit_struct  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult, run_backtest  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "alpha_v1_exit_target_mfe_sweep_20260505"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_EXIT_TARGET_MFE_SWEEP_20260505.md"

FULL_START = "2016-04-17"
END_INCLUSIVE = "2026-03-24"
END_EXCLUSIVE = "2026-03-25"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"
WORKERS = 8

WINDOWS = {
    "last_1y": (LAST_1Y_START, END_INCLUSIVE),
    "last_2y": (LAST_2Y_START, END_INCLUSIVE),
    "full": (FULL_START, END_INCLUSIVE),
}

MIN_TP1_RATIO = 0.20
MAX_TP1_RATIO = 0.80
BASELINE_POLICY = exit_struct.PolicySpec(
    "baseline_replay",
    "Current TP1/TP2 replay",
    "baseline",
)


@dataclass(frozen=True)
class LegPlan:
    leg: exit_struct.LegSpec
    rr_values: tuple[float, ...]
    tp1_r_values: tuple[float, ...]
    deployability: str
    live_support_notes: str
    exact_replay_required: str

    @property
    def baseline_rr(self) -> float:
        return float(self.leg.config.rr)

    @property
    def baseline_tp1_r(self) -> float:
        return float(self.leg.config.rr * self.leg.config.tp1_ratio)


@dataclass(frozen=True)
class ExitVariant:
    plan: LegPlan
    variant_id: str
    rr: float
    tp1_ratio: float
    tp1_r: float
    config: StrategyConfig


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


def _fmt_float(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text.replace(".", "p")


def _pct(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else 100.0 * float(numerator) / float(denominator)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    return float(np.quantile(np.array(values, dtype=np.float64), q))


def build_nq_ny_orb_r11_leg() -> exit_struct.LegSpec:
    config = StrategyConfig(
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:50",
                entry_start="09:50",
                entry_end="12:00",
                flat_start="15:30",
                flat_end="16:00",
                stop_atr_pct=7.0,
                min_gap_atr_pct=2.5,
            ),
        ),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.4,
        atr_length=12,
        excluded_days=(4,),
        impulse_close_filter=False,
        name="NQ NY ORB R11 baseline",
    )
    return exit_struct.LegSpec(
        key="nq_ny_orb_r11",
        label="NQ NY ORB R11",
        symbol="NQ",
        config=config,
    )


def build_leg_plans() -> list[LegPlan]:
    active = {leg.key: leg for leg in exit_struct.build_active_legs()}
    return [
        LegPlan(
            leg=active["nq_ny_htf_lsi"],
            rr_values=(2.0, 2.5, 3.0, 3.5, 4.0),
            tp1_r_values=(1.0, 1.25, 1.4, 1.5, 1.75, 2.0),
            deployability="live_native",
            live_support_notes="Active ALPHA_V1 HTF-LSI leg; rr/tp1 target knobs are execution-supported.",
            exact_replay_required="yes_before_live_change",
        ),
        LegPlan(
            leg=active["nq_asia_orb"],
            rr_values=(2.5, 3.0, 3.5, 4.0, 5.0, 6.0),
            tp1_r_values=(1.0, 1.25, 1.5, 1.75, 1.8, 2.0, 2.25),
            deployability="live_native",
            live_support_notes="Active ALPHA_V1 ORB leg; rr/tp1 target knobs are execution-supported.",
            exact_replay_required="yes_before_live_change",
        ),
        LegPlan(
            leg=active["es_asia_cont"],
            rr_values=(1.25, 1.5, 1.75, 2.0, 2.5),
            tp1_r_values=(1.0, 1.05, 1.25, 1.5),
            deployability="live_native",
            live_support_notes="Active ALPHA_V1 ORB leg; rr/tp1 target knobs are execution-supported.",
            exact_replay_required="yes_before_live_change",
        ),
        LegPlan(
            leg=active["es_ny_cont"],
            rr_values=(2.0, 2.5, 3.0, 3.5, 4.0, 5.0),
            tp1_r_values=(1.0, 1.25, 1.5, 1.75, 2.0),
            deployability="live_native",
            live_support_notes="Active ALPHA_V1 ORB leg; rr/tp1 target knobs are execution-supported.",
            exact_replay_required="yes_before_live_change",
        ),
        LegPlan(
            leg=build_nq_ny_orb_r11_leg(),
            rr_values=(2.0, 2.5, 3.0, 3.5, 4.0, 4.5),
            tp1_r_values=(1.0, 1.25, 1.4, 1.5, 1.75, 2.0),
            deployability="live_native",
            live_support_notes="Conditional NQ NY ORB R11 branch; standard ORB rr/tp1 knobs are execution-supported.",
            exact_replay_required="yes_before_live_promotion",
        ),
    ]


def _variant_pairs(plan: LegPlan) -> list[tuple[float, float, float]]:
    pairs: dict[tuple[float, float], tuple[float, float, float]] = {}
    for rr in (*plan.rr_values, plan.baseline_rr):
        for tp1_r in (*plan.tp1_r_values, plan.baseline_tp1_r):
            if tp1_r < 1.0 - 1e-9:
                continue
            if tp1_r >= rr - 1e-9:
                continue
            # Keep full precision for StrategyConfig validation. Rounding
            # values like 1/3 to 0.333333 can fail the hard tp1>=1R rule.
            tp1_ratio = float(tp1_r / rr)
            if tp1_ratio < MIN_TP1_RATIO or tp1_ratio > MAX_TP1_RATIO:
                continue
            key = (round(rr, 8), round(tp1_ratio, 8))
            pairs[key] = (float(rr), float(tp1_ratio), round(float(rr * tp1_ratio), 4))
    return sorted(pairs.values(), key=lambda row: (row[0], row[2]))


def _variants_for(plan: LegPlan) -> list[ExitVariant]:
    variants: list[ExitVariant] = []
    for rr, tp1_ratio, tp1_r in _variant_pairs(plan):
        variant_id = f"rr{_fmt_float(rr)}__tp1r{_fmt_float(tp1_r)}"
        name = f"{plan.leg.key}__{variant_id}"[:240]
        try:
            config = replace(plan.leg.config, name=name, rr=rr, tp1_ratio=tp1_ratio)
        except ValueError as exc:
            print(f"  skip {name}: {exc}", flush=True)
            continue
        variants.append(
            ExitVariant(
                plan=plan,
                variant_id=variant_id,
                rr=rr,
                tp1_ratio=tp1_ratio,
                tp1_r=tp1_r,
                config=config,
            )
        )
    return variants


def _slice(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end]


def _exit_stats_from_counts(counts: dict[str, int], total: int) -> dict[str, Any]:
    full_tp = counts.get("tp1_tp2", 0) + counts.get("tp2_single", 0)
    tp1_be = counts.get("tp1_be", 0)
    tp1_eod = counts.get("tp1_eod", 0)
    sl = counts.get("sl", 0)
    eod = counts.get("eod", 0)
    tp1_hit = full_tp + tp1_be + tp1_eod
    return {
        "full_tp_count": full_tp,
        "full_tp_rate_pct": _round(_pct(full_tp, total), 2),
        "tp1_be_count": tp1_be,
        "tp1_be_rate_pct": _round(_pct(tp1_be, total), 2),
        "tp1_eod_count": tp1_eod,
        "tp1_eod_rate_pct": _round(_pct(tp1_eod, total), 2),
        "sl_count": sl,
        "sl_rate_pct": _round(_pct(sl, total), 2),
        "eod_count": eod,
        "eod_rate_pct": _round(_pct(eod, total), 2),
        "tp1_hit_count": tp1_hit,
        "tp1_hit_rate_pct": _round(_pct(tp1_hit, total), 2),
        "tp2_given_tp1_pct": _round(_pct(full_tp, tp1_hit), 2),
    }


def _exit_stats(trades: list[TradeResult]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    for trade in filled:
        name = EXIT_NAMES.get(trade.exit_type, str(trade.exit_type))
        counts[name] = counts.get(name, 0) + 1
    return {"exit_counts": counts, **_exit_stats_from_counts(counts, len(filled))}


def _stop_stats(trades: list[TradeResult], plan: LegPlan) -> dict[str, Any]:
    risks = [float(trade.risk_points) for trade in trades if trade.exit_type != EXIT_NO_FILL and trade.risk_points > 0]
    if not risks:
        return {"median_stop_points": None, "median_stop_ticks": None}
    ticks = [risk / plan.leg.config.instrument.min_tick for risk in risks]
    return {
        "median_stop_points": _round(median(risks), 4),
        "median_stop_ticks": _round(median(ticks), 1),
    }


def _metric_row(
    *,
    variant: ExitVariant,
    trades: list[TradeResult],
    window: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    selected = _slice(trades, start, end)
    metrics = compute_metrics(selected)
    total = int(metrics["total_trades"])
    max_dd_r = abs(float(metrics["max_drawdown_r"]))
    return {
        "leg_key": variant.plan.leg.key,
        "leg_label": variant.plan.leg.label,
        "variant_id": variant.variant_id,
        "window": window,
        "start": start,
        "end": end,
        "rr": variant.rr,
        "tp1_ratio": variant.tp1_ratio,
        "tp1_r": variant.tp1_r,
        "signals": int(metrics["total_signals"]),
        "trades": total,
        "no_fills": int(metrics["no_fills"]),
        "net_r": _round(metrics["total_r"], 2),
        "win_rate_pct": _round(float(metrics["win_rate"]) * 100.0, 2),
        "profit_factor": _round(metrics["profit_factor"], 3),
        "avg_r": _round(metrics["avg_r"], 4),
        "sharpe_ratio": _round(metrics["sharpe_ratio"], 3),
        "max_dd_r": _round(max_dd_r, 2),
        "calmar_ratio": _round(metrics["calmar_ratio"], 3),
        "negative_years": int(sum(1 for value in (metrics.get("r_by_year") or {}).values() if value < 0)),
        "r_by_year": metrics.get("r_by_year") or {},
        **_exit_stats(selected),
        **_stop_stats(selected, variant.plan),
        "deployability": variant.plan.deployability,
        "live_support_notes": variant.plan.live_support_notes,
        "exact_replay_required": variant.plan.exact_replay_required,
    }


def _mfe_diagnostic(plan: LegPlan, symbol_data: exit_struct.SymbolData) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trades = run_backtest(
        symbol_data.df_5m,
        plan.leg.config,
        start_date=FULL_START,
        end_date=END_EXCLUSIVE,
        df_1m=symbol_data.df_1m,
        signal_df_1m=symbol_data.df_1m,
        df_1s=symbol_data.df_1s,
        _maps=symbol_data.maps,
    )
    filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    metrics = compute_metrics(trades)
    replayed = [exit_struct.replay_trade(trade, plan.leg, symbol_data, policy=BASELINE_POLICY) for trade in filled]
    tp1_r = plan.baseline_tp1_r
    rr = plan.baseline_rr
    mfe_values = [float(row["mfe_r"]) for row in replayed]
    tp1_hit_rows = [row for row in replayed if float(row["mfe_r"]) >= tp1_r - 1e-9]
    winner_rows = [row for row in replayed if float(row["r_multiple"]) > 0]

    counts = dict(metrics["exit_breakdown"])
    total = int(metrics["total_trades"])
    exit_stats = _exit_stats_from_counts(counts, total)
    validation_rows = [row for row in replayed if "replay_validation" in row]
    validation_rate = (
        float(np.mean([bool(row["replay_validation"]) for row in validation_rows]))
        if validation_rows
        else 0.0
    )

    diagnostic = {
        "leg_key": plan.leg.key,
        "leg_label": plan.leg.label,
        "symbol": plan.leg.symbol,
        "baseline_rr": rr,
        "baseline_tp1_r": tp1_r,
        "trades": total,
        "net_r": _round(metrics["total_r"], 2),
        "profit_factor": _round(metrics["profit_factor"], 3),
        "max_dd_r": _round(abs(float(metrics["max_drawdown_r"])), 2),
        "win_rate_pct": _round(float(metrics["win_rate"]) * 100.0, 2),
        **exit_stats,
        "mfe_ge_tp1_pct": _round(_pct(sum(1 for value in mfe_values if value >= tp1_r - 1e-9), len(mfe_values)), 2),
        "mfe_ge_2r_pct": _round(_pct(sum(1 for value in mfe_values if value >= 2.0 - 1e-9), len(mfe_values)), 2),
        "mfe_ge_3r_pct": _round(_pct(sum(1 for value in mfe_values if value >= 3.0 - 1e-9), len(mfe_values)), 2),
        "mfe_ge_current_rr_pct": _round(_pct(sum(1 for value in mfe_values if value >= rr - 1e-9), len(mfe_values)), 2),
        "tp1_hit_mfe_p50": _round(_quantile([float(row["mfe_r"]) for row in tp1_hit_rows], 0.50), 2),
        "tp1_hit_mfe_p75": _round(_quantile([float(row["mfe_r"]) for row in tp1_hit_rows], 0.75), 2),
        "tp1_hit_mfe_p90": _round(_quantile([float(row["mfe_r"]) for row in tp1_hit_rows], 0.90), 2),
        "winner_mfe_p50": _round(_quantile([float(row["mfe_r"]) for row in winner_rows], 0.50), 2),
        "winner_mfe_p75": _round(_quantile([float(row["mfe_r"]) for row in winner_rows], 0.75), 2),
        "winner_mfe_p90": _round(_quantile([float(row["mfe_r"]) for row in winner_rows], 0.90), 2),
        "baseline_replay_validation_rate_pct": _round(validation_rate * 100.0, 2),
        "deployability": plan.deployability,
        "live_support_notes": plan.live_support_notes,
        "exact_replay_required": plan.exact_replay_required,
    }

    trade_rows = []
    for row in replayed:
        trade_rows.append(
            {
                "leg_key": plan.leg.key,
                "leg_label": plan.leg.label,
                "date": row["date"],
                "direction": row["direction"],
                "exit_type": row["exit_type"],
                "r_multiple": _round(row["r_multiple"], 4),
                "mae_r": _round(row["mae_r"], 4),
                "mfe_r": _round(row["mfe_r"], 4),
                "fill_time": row["fill_time"],
                "exit_time": row["exit_time"],
            }
        )
    return diagnostic, trade_rows


def _baseline_variant_id(plan: LegPlan) -> str:
    return f"rr{_fmt_float(plan.baseline_rr)}__tp1r{_fmt_float(plan.baseline_tp1_r)}"


def _score_rows(metric_rows: list[dict[str, Any]], plans: list[LegPlan]) -> list[dict[str, Any]]:
    plan_by_key = {plan.leg.key: plan for plan in plans}
    by_variant: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for row in metric_rows:
        by_variant.setdefault((str(row["leg_key"]), str(row["variant_id"])), {})[str(row["window"])] = row

    baseline_by_key: dict[str, dict[str, dict[str, Any]]] = {}
    for plan in plans:
        baseline_by_key[plan.leg.key] = by_variant[(plan.leg.key, _baseline_variant_id(plan))]

    ranked: list[dict[str, Any]] = []
    for (leg_key, variant_id), windows in by_variant.items():
        if not {"last_1y", "last_2y", "full"} <= set(windows):
            continue
        plan = plan_by_key[leg_key]
        base = baseline_by_key[leg_key]
        full = windows["full"]
        last1 = windows["last_1y"]
        last2 = windows["last_2y"]
        base_full = base["full"]
        base_last1 = base["last_1y"]
        base_last2 = base["last_2y"]

        full_net = float(full["net_r"] or 0.0)
        full_pf = float(full["profit_factor"] or 0.0)
        full_dd = float(full["max_dd_r"] or 0.0)
        last1_net = float(last1["net_r"] or 0.0)
        last2_net = float(last2["net_r"] or 0.0)
        base_full_net = float(base_full["net_r"] or 0.0)
        base_full_pf = float(base_full["profit_factor"] or 0.0)
        base_full_dd = float(base_full["max_dd_r"] or 0.0)
        base_last1_net = float(base_last1["net_r"] or 0.0)
        base_last2_net = float(base_last2["net_r"] or 0.0)

        rr = float(full["rr"])
        closer_tp2 = rr < plan.baseline_rr - 1e-9
        near_intact = (
            full_net >= 0.95 * base_full_net
            and full_pf >= base_full_pf - 0.05
            and full_dd <= 1.10 * base_full_dd
            and last1_net >= 0.75 * base_last1_net
            and last2_net >= 0.80 * base_last2_net
            and int(full["negative_years"] or 0) <= int(base_full["negative_years"] or 0)
        )
        loose_intact = (
            full_net >= 0.85 * base_full_net
            and full_pf >= base_full_pf - 0.10
            and full_dd <= 1.25 * base_full_dd
            and last2_net >= 0.65 * base_last2_net
            and int(full["negative_years"] or 0) <= int(base_full["negative_years"] or 0) + 1
        )
        score = (
            100.0 * float(full["calmar_ratio"] or 0.0)
            + 0.35 * full_net
            + 0.75 * last2_net
            + 0.50 * last1_net
            + 0.40 * (float(full["full_tp_rate_pct"] or 0.0) - float(base_full["full_tp_rate_pct"] or 0.0))
            - 0.35 * max(0.0, float(full["tp1_be_rate_pct"] or 0.0) - float(base_full["tp1_be_rate_pct"] or 0.0))
            - 8.0 * max(0, int(full["negative_years"] or 0) - int(base_full["negative_years"] or 0))
        )
        if closer_tp2:
            score += 4.0
        if not loose_intact:
            score -= 40.0

        ranked.append(
            {
                "leg_key": leg_key,
                "leg_label": full["leg_label"],
                "variant_id": variant_id,
                "rr": rr,
                "tp1_ratio": float(full["tp1_ratio"]),
                "tp1_r": float(full["tp1_r"]),
                "closer_tp2": closer_tp2,
                "near_intact": near_intact,
                "loose_intact": loose_intact,
                "promotion_score": _round(score, 3),
                "full_net_r": full_net,
                "full_r_delta": _round(full_net - base_full_net, 2),
                "full_trades": int(full["trades"] or 0),
                "full_wr_pct": float(full["win_rate_pct"] or 0.0),
                "full_pf": full_pf,
                "full_pf_delta": _round(full_pf - base_full_pf, 3),
                "full_dd_r": full_dd,
                "full_dd_delta": _round(full_dd - base_full_dd, 2),
                "full_calmar": float(full["calmar_ratio"] or 0.0),
                "full_negative_years": int(full["negative_years"] or 0),
                "full_full_tp_pct": float(full["full_tp_rate_pct"] or 0.0),
                "full_tp1_be_pct": float(full["tp1_be_rate_pct"] or 0.0),
                "full_sl_pct": float(full["sl_rate_pct"] or 0.0),
                "last_1y_net_r": last1_net,
                "last_1y_r_delta": _round(last1_net - base_last1_net, 2),
                "last_1y_pf": float(last1["profit_factor"] or 0.0),
                "last_1y_dd_r": float(last1["max_dd_r"] or 0.0),
                "last_2y_net_r": last2_net,
                "last_2y_r_delta": _round(last2_net - base_last2_net, 2),
                "last_2y_pf": float(last2["profit_factor"] or 0.0),
                "last_2y_dd_r": float(last2["max_dd_r"] or 0.0),
                "baseline_variant": variant_id == _baseline_variant_id(plan),
                "deployability": full["deployability"],
                "live_support_notes": full["live_support_notes"],
                "exact_replay_required": full["exact_replay_required"],
            }
        )
    return sorted(ranked, key=lambda row: float(row["promotion_score"] or 0.0), reverse=True)


def _best_rows(ranked: list[dict[str, Any]], plans: list[LegPlan]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for plan in plans:
        rows = [row for row in ranked if row["leg_key"] == plan.leg.key]
        baseline = next(row for row in rows if row["baseline_variant"])
        near_closer = [row for row in rows if row["closer_tp2"] and row["near_intact"]]
        loose_closer = [row for row in rows if row["closer_tp2"] and row["loose_intact"]]
        all_closer = [row for row in rows if row["closer_tp2"]]
        best_near = max(near_closer, key=lambda row: float(row["promotion_score"] or 0.0), default=None)
        best_loose = max(loose_closer, key=lambda row: float(row["promotion_score"] or 0.0), default=None)
        best_any = max(rows, key=lambda row: float(row["promotion_score"] or 0.0), default=None)
        best_closer = max(all_closer, key=lambda row: float(row["promotion_score"] or 0.0), default=None)
        selected = best_near or best_loose or baseline
        decision = "test_closer_target" if best_near else ("research_only_closer" if best_loose else "keep_baseline")
        out.append(
            {
                "leg_key": plan.leg.key,
                "leg_label": plan.leg.label,
                "decision": decision,
                "baseline": baseline,
                "selected": selected,
                "best_near_closer": best_near,
                "best_loose_closer": best_loose,
                "best_any": best_any,
                "best_closer": best_closer,
            }
        )
    return out


def _run_sweeps(
    plans: list[LegPlan],
    symbol_cache: dict[str, exit_struct.SymbolData],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[ExitVariant]]:
    all_variants: list[ExitVariant] = []
    for plan in plans:
        all_variants.extend(_variants_for(plan))

    metric_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []

    variants_by_symbol: dict[str, list[ExitVariant]] = {}
    for variant in all_variants:
        variants_by_symbol.setdefault(variant.plan.leg.symbol, []).append(variant)
        cfg = variant.config
        session = cfg.sessions[0]
        manifest_rows.append(
            {
                "leg_key": variant.plan.leg.key,
                "leg_label": variant.plan.leg.label,
                "variant_id": variant.variant_id,
                "symbol": variant.plan.leg.symbol,
                "strategy": cfg.strategy,
                "session": session.name,
                "rr": variant.rr,
                "tp1_ratio": variant.tp1_ratio,
                "tp1_r": variant.tp1_r,
                "orb_start": session.orb_start,
                "orb_end": session.orb_end,
                "entry_start": session.entry_start,
                "entry_end": session.entry_end,
                "flat_start": session.flat_start,
                "flat_end": session.flat_end,
                "stop_atr_pct": session.stop_atr_pct,
                "stop_orb_pct": session.stop_orb_pct,
                "min_gap_atr_pct": session.min_gap_atr_pct,
                "min_gap_orb_pct": session.min_gap_orb_pct,
                "min_stop_points": session.min_stop_points,
                "min_tp1_points": session.min_tp1_points,
                "atr_length": cfg.atr_length,
                "direction_filter": cfg.direction_filter,
                "excluded_days": ",".join(str(day) for day in cfg.excluded_days),
                "deployability": variant.plan.deployability,
                "live_support_notes": variant.plan.live_support_notes,
                "exact_replay_required": variant.plan.exact_replay_required,
            }
        )

    for symbol, variants in sorted(variants_by_symbol.items()):
        data = symbol_cache[symbol]
        print(f"Running {symbol} exit-only sweep: {len(variants)} configs", flush=True)

        def progress(done: int, total: int) -> None:
            if done == total or done % 25 == 0:
                print(f"  {symbol}: {done}/{total}", flush=True)

        results = run_sweep(
            data.df_5m,
            [variant.config for variant in variants],
            n_workers=min(WORKERS, max(1, len(variants))),
            start_date=FULL_START,
            end_date=END_EXCLUSIVE,
            df_1m=data.df_1m,
            df_1s=data.df_1s,
            signal_df_1m=data.df_1m,
            progress_fn=progress,
        )
        variant_by_name = {variant.config.name: variant for variant in variants}
        for config, trades in results:
            variant = variant_by_name[config.name]
            trades = [
                trade
                for trade in sorted(trades, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))
                if trade.exit_type != EXIT_NO_FILL
            ]
            for window, (start, end) in WINDOWS.items():
                metric_rows.append(_metric_row(variant=variant, trades=trades, window=window, start=start, end=end))

    return metric_rows, manifest_rows, all_variants


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


def _compact_rank_row(row: dict[str, Any] | None) -> str:
    if row is None:
        return "none"
    return (
        f"rr {row['rr']:g} / TP1 {row['tp1_r']:g}R "
        f"= {row['full_net_r']:.1f}R PF {row['full_pf']:.2f} DD {row['full_dd_r']:.1f}R "
        f"TP2 {row['full_full_tp_pct']:.1f}% TP1-BE {row['full_tp1_be_pct']:.1f}%"
    )


def _write_report(
    *,
    mfe_rows: list[dict[str, Any]],
    best_rows: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
) -> None:
    mfe_table = []
    for row in mfe_rows:
        mfe_table.append(
            {
                "Leg": row["leg_label"],
                "TP1_R": row["baseline_tp1_r"],
                "RR": row["baseline_rr"],
                "WR": f"{row['win_rate_pct']:.1f}%",
                "TP2%": f"{row['full_tp_rate_pct']:.1f}%",
                "TP1-BE%": f"{row['tp1_be_rate_pct']:.1f}%",
                "TP1 hit%": f"{row['tp1_hit_rate_pct']:.1f}%",
                "TP2/TP1": f"{row['tp2_given_tp1_pct']:.1f}%",
                "MFE>=2R": f"{row['mfe_ge_2r_pct']:.1f}%",
                "MFE>=3R": f"{row['mfe_ge_3r_pct']:.1f}%",
                "MFE>=RR": f"{row['mfe_ge_current_rr_pct']:.1f}%",
                "TP1-hit p75 MFE": row["tp1_hit_mfe_p75"],
            }
        )

    selection_table = []
    for row in best_rows:
        baseline = row["baseline"]
        selected = row["selected"]
        selection_table.append(
            {
                "Leg": row["leg_label"],
                "Decision": row["decision"],
                "Current": f"rr {baseline['rr']:g}/TP1 {baseline['tp1_r']:g}R "
                f"{baseline['full_net_r']:.1f}R PF{baseline['full_pf']:.2f} DD{baseline['full_dd_r']:.1f}",
                "Selected": f"rr {selected['rr']:g}/TP1 {selected['tp1_r']:g}R "
                f"{selected['full_net_r']:.1f}R PF{selected['full_pf']:.2f} DD{selected['full_dd_r']:.1f}",
                "ΔR": selected["full_r_delta"],
                "ΔDD": selected["full_dd_delta"],
                "TP2%": f"{selected['full_full_tp_pct']:.1f}%",
                "TP1-BE%": f"{selected['full_tp1_be_pct']:.1f}%",
            }
        )

    top_ranked = [
        {
            "Leg": row["leg_label"],
            "Variant": f"rr {row['rr']:g}/TP1 {row['tp1_r']:g}R",
            "Near": row["near_intact"],
            "Loose": row["loose_intact"],
            "Full R/PF/DD": f"{row['full_net_r']:.1f}/{row['full_pf']:.2f}/{row['full_dd_r']:.1f}",
            "2Y R/PF/DD": f"{row['last_2y_net_r']:.1f}/{row['last_2y_pf']:.2f}/{row['last_2y_dd_r']:.1f}",
            "TP2%": f"{row['full_full_tp_pct']:.1f}%",
            "TP1-BE%": f"{row['full_tp1_be_pct']:.1f}%",
            "Score": row["promotion_score"],
        }
        for row in ranked[:20]
    ]

    lines = [
        "# ALPHA_V1 Exit Target MFE Sweep (2026-05-05)",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Full window: `{FULL_START}` to `{END_INCLUSIVE}`; recent windows: `{LAST_2Y_START}` and `{LAST_1Y_START}` to `{END_INCLUSIVE}`.",
        "- Scope: active `ALPHA_V1` legs plus `NQ NY ORB R11`.",
        "- Pass 1: fixed-fill MFE/MAE diagnostic using the existing replay helper.",
        "- Pass 2: true engine replay while holding entries, stops, sessions, DOW filters, ORB windows, and gap filters fixed; only `rr` and TP1 distance changed.",
        "- Pass 3: Calmar/edge-first ranking against each leg's baseline. Full TP rate is treated as a diagnostic, not an objective.",
        "- Deployability: all target rows are `live_native`; any selected change still requires exact execution replay before live modification.",
        "",
        "## Pass 1 — MFE Diagnostic",
        "",
        *_md_table(
            mfe_table,
            [
                ("Leg", "Leg"),
                ("TP1_R", "TP1_R"),
                ("RR", "RR"),
                ("WR", "WR"),
                ("TP2%", "TP2%"),
                ("TP1-BE%", "TP1-BE%"),
                ("TP1 hit%", "TP1 hit%"),
                ("TP2/TP1", "TP2/TP1"),
                ("MFE>=2R", "MFE>=2R"),
                ("MFE>=3R", "MFE>=3R"),
                ("MFE>=RR", "MFE>=RR"),
                ("TP1-hit p75 MFE", "TP1-hit p75 MFE"),
            ],
        ),
        "",
        "## Pass 2/3 — Best Target Compression Rows",
        "",
        *_md_table(
            selection_table,
            [
                ("Leg", "Leg"),
                ("Decision", "Decision"),
                ("Current", "Current"),
                ("Selected", "Selected"),
                ("ΔR", "ΔR"),
                ("ΔDD", "ΔDD"),
                ("TP2%", "TP2%"),
                ("TP1-BE%", "TP1-BE%"),
            ],
        ),
        "",
        "## Top Ranked Rows",
        "",
        *_md_table(
            top_ranked,
            [
                ("Leg", "Leg"),
                ("Variant", "Variant"),
                ("Near", "Near"),
                ("Loose", "Loose"),
                ("Full R/PF/DD", "Full R/PF/DD"),
                ("2Y R/PF/DD", "2Y R/PF/DD"),
                ("TP2%", "TP2%"),
                ("TP1-BE%", "TP1-BE%"),
                ("Score", "Score"),
            ],
        ),
        "",
        "## Interpretation",
        "",
        "- Low full-TP rate alone did not mean every TP2 was too far. The best rows had to preserve R production, PF, DD, and recent behavior.",
        "- `test_closer_target` means a closer target preserved the baseline under the strict near-intact screen. `research_only_closer` means a closer target improved some behavior but gave up too much edge for direct promotion. `keep_baseline` means no closer target cleared even the loose screen.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    started = time.time()
    plans = build_leg_plans()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

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

    print("Pass 1: baseline MFE diagnostics", flush=True)
    mfe_rows: list[dict[str, Any]] = []
    mfe_trade_rows: list[dict[str, Any]] = []
    for plan in plans:
        print(f"  MFE {plan.leg.label}", flush=True)
        diagnostic, trade_rows = _mfe_diagnostic(plan, symbol_cache[plan.leg.symbol])
        mfe_rows.append(diagnostic)
        mfe_trade_rows.extend(trade_rows)

    print("Pass 2: exit-only sweeps", flush=True)
    metric_rows, manifest_rows, variants = _run_sweeps(plans, symbol_cache)

    print("Pass 3: ranking vs baselines", flush=True)
    ranked = _score_rows(metric_rows, plans)
    best_rows = _best_rows(ranked, plans)

    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "run_slug": RUN_SLUG,
        "full_start": FULL_START,
        "end_inclusive": END_INCLUSIVE,
        "windows": WINDOWS,
        "variant_count": len(variants),
        "mfe_rows": mfe_rows,
        "best_rows": best_rows,
        "top_ranked": ranked[:50],
        "report_path": str(REPORT_PATH),
        "elapsed_seconds": round(time.time() - started, 2),
    }

    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2), encoding="utf-8")
    pd.DataFrame(mfe_rows).to_csv(RESULT_DIR / "mfe_diagnostics.csv", index=False)
    pd.DataFrame(mfe_trade_rows).to_csv(RESULT_DIR / "mfe_trades.csv", index=False)
    pd.DataFrame(manifest_rows).to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(RESULT_DIR / "variant_metrics.csv", index=False)
    pd.DataFrame(ranked).to_csv(RESULT_DIR / "ranked_variants.csv", index=False)
    _write_report(mfe_rows=mfe_rows, best_rows=best_rows, ranked=ranked)

    print(json.dumps(_safe_json(summary), indent=2))
    print(f"\nSaved report to {REPORT_PATH}")
    print(f"Saved artifacts to {RESULT_DIR}")


if __name__ == "__main__":
    main()
