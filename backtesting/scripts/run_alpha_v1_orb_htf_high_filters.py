#!/usr/bin/env python3
"""Evaluate HTF-high-based ORB filters on the active ALPHA_V1 ORB legs.

Questions:
1. If an ORB limit is still pending, and price reaches TP2 before entry while a
   fresh HTF high is also swept pre-fill, does canceling that order help?
2. If the active published HTF high is already at TP1 or higher when the order
   arms, does that identify better-quality ORB trades?

This is an analysis script only. Both ideas are pure trade-removal filters here,
so the script evaluates them off the frozen baseline trade set rather than
adding new simulator toggles.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES, NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import (
    EXIT_NO_FILL,
    EXIT_TP1_TP2,
    EXIT_TP2_SINGLE,
    TradeResult,
    build_maps,
    run_backtest,
)
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.signals.htf_levels import compute_htf_unswept_levels


RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_htf_high_filters_20260417"
SUMMARY_PATH = RESULT_DIR / "summary.json"
RECENT_START = "2024-01-01"


@dataclass(frozen=True)
class HtfSpec:
    tf_minutes: int
    n_left: int
    label: str


@dataclass(frozen=True)
class LegSpec:
    key: str
    label: str
    symbol: str
    config: StrategyConfig
    htf_spec: HtfSpec


def build_orb_legs() -> list[LegSpec]:
    nq_htf = HtfSpec(tf_minutes=60, n_left=3, label="NQ-native HTF (60m, n_left=3)")
    es_htf = HtfSpec(tf_minutes=90, n_left=3, label="ES-native HTF (90m, n_left=3)")
    return [
        LegSpec(
            key="nq_asia_orb",
            label="ORB/NQ_ASIA-RR6",
            symbol="NQ",
            htf_spec=nq_htf,
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="Asia",
                        orb_start="20:00",
                        orb_end="20:15",
                        entry_start="20:15",
                        entry_end="22:30",
                        flat_start="04:00",
                        flat_end="07:00",
                        stop_orb_pct=100.0,
                        min_gap_orb_pct=10.0,
                    ),
                ),
                instrument=NQ,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=6.0,
                tp1_ratio=0.3,
                atr_length=5,
                excluded_days=(1,),
                name="ALPHA_V1 NQ Asia ORB baseline",
            ),
        ),
        LegSpec(
            key="es_asia_cont",
            label="ORB/ES_ASIA-RR1.5",
            symbol="ES",
            htf_spec=es_htf,
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="Asia",
                        orb_start="20:00",
                        orb_end="20:15",
                        entry_start="20:15",
                        entry_end="03:00",
                        flat_start="07:00",
                        flat_end="07:00",
                        stop_orb_pct=125.0,
                        min_gap_atr_pct=0.5,
                        min_stop_points=3.0,
                        min_tp1_points=3.0,
                    ),
                ),
                instrument=ES,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=1.5,
                tp1_ratio=0.7,
                atr_length=14,
                name="ALPHA_V1 ES Asia continuation baseline",
            ),
        ),
        LegSpec(
            key="es_ny_cont",
            label="ORB/ES_NY-RR5",
            symbol="ES",
            htf_spec=es_htf,
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="NY",
                        orb_start="09:30",
                        orb_end="09:45",
                        entry_start="09:45",
                        entry_end="13:00",
                        flat_start="15:50",
                        flat_end="16:00",
                        stop_atr_pct=5.0,
                        min_gap_atr_pct=0.25,
                        min_stop_points=3.0,
                        min_tp1_points=3.0,
                    ),
                ),
                instrument=ES,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=5.0,
                tp1_ratio=0.2,
                atr_length=7,
                excluded_days=(3,),
                name="ALPHA_V1 ES NY continuation baseline",
            ),
        ),
    ]


def trade_key(trade: TradeResult) -> tuple:
    return (
        trade.date,
        trade.session,
        trade.direction,
        trade.signal_bar,
        round(float(trade.entry_price), 6),
        round(float(trade.stop_price), 6),
        round(float(trade.tp2_price), 6),
    )


def filter_window(trades: list[TradeResult], start: str | None = None, end: str | None = None) -> list[TradeResult]:
    out: list[TradeResult] = []
    for trade in trades:
        if start is not None and trade.date < start:
            continue
        if end is not None and trade.date >= end:
            continue
        out.append(trade)
    return out


def summarize_trade_set(trades: list[TradeResult]) -> dict:
    metrics = compute_metrics(trades)
    return {
        "total_signals": int(metrics["total_signals"]),
        "filled_trades": int(metrics["total_trades"]),
        "no_fills": int(metrics["no_fills"]),
        "win_rate": float(metrics["win_rate"]),
        "profit_factor": float(metrics["profit_factor"]),
        "avg_r": float(metrics["avg_r"]),
        "total_r": float(metrics["total_r"]),
        "max_drawdown_r": float(metrics["max_drawdown_r"]),
        "calmar_ratio": float(metrics["calmar_ratio"]),
        "exit_breakdown": dict(metrics["exit_breakdown"]),
    }


def compare_vs_baseline(
    baseline: list[TradeResult],
    variant: list[TradeResult],
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    baseline_window = filter_window(baseline, start=start, end=end)
    variant_window = filter_window(variant, start=start, end=end)

    baseline_summary = summarize_trade_set(baseline_window)
    variant_summary = summarize_trade_set(variant_window)

    baseline_filled = {trade_key(t): t for t in baseline_window if t.exit_type != EXIT_NO_FILL}
    variant_filled = {trade_key(t): t for t in variant_window if t.exit_type != EXIT_NO_FILL}

    baseline_only = [baseline_filled[k] for k in sorted(set(baseline_filled) - set(variant_filled))]
    variant_only = [variant_filled[k] for k in sorted(set(variant_filled) - set(baseline_filled))]

    return {
        "summary": variant_summary,
        "delta_vs_baseline": {
            "filled_trades": variant_summary["filled_trades"] - baseline_summary["filled_trades"],
            "no_fills": variant_summary["no_fills"] - baseline_summary["no_fills"],
            "total_r": variant_summary["total_r"] - baseline_summary["total_r"],
            "max_drawdown_r": variant_summary["max_drawdown_r"] - baseline_summary["max_drawdown_r"],
            "calmar_ratio": variant_summary["calmar_ratio"] - baseline_summary["calmar_ratio"],
        },
        "baseline_only_fills": {
            "count": len(baseline_only),
            "total_r": float(sum(t.r_multiple for t in baseline_only)),
            "wins": sum(1 for t in baseline_only if t.r_multiple > 0),
            "losses": sum(1 for t in baseline_only if t.r_multiple < 0),
            "breakevens": sum(1 for t in baseline_only if t.r_multiple == 0),
        },
        "variant_only_fills": {
            "count": len(variant_only),
            "total_r": float(sum(t.r_multiple for t in variant_only)),
            "wins": sum(1 for t in variant_only if t.r_multiple > 0),
            "losses": sum(1 for t in variant_only if t.r_multiple < 0),
            "breakevens": sum(1 for t in variant_only if t.r_multiple == 0),
        },
    }


def load_symbol_data(symbol: str) -> dict:
    stem = f"{symbol}_5m.parquet"
    df_5m = load_5m_data(stem)
    df_1m = load_1m_for_5m(stem)
    df_1s = load_1s_for_5m(stem)
    return {
        "df_5m": df_5m,
        "df_1m": df_1m,
        "df_1s": df_1s,
        "maps": build_maps(df_5m, df_1m=df_1m, df_1s=df_1s),
    }


def build_fresh_high_sweep_flags(
    high: np.ndarray,
    active_high_price: np.ndarray,
    active_high_instance_id: np.ndarray,
) -> np.ndarray:
    fresh_high_sweep = np.zeros(len(high), dtype=bool)
    current_instance = -10_000_000
    consumed = False
    for i in range(len(high)):
        instance_id = int(active_high_instance_id[i])
        if instance_id != current_instance:
            current_instance = instance_id
            consumed = False
        if instance_id < 0 or consumed:
            continue
        level_price = float(active_high_price[i])
        if not np.isfinite(level_price):
            continue
        if high[i] > level_price:
            fresh_high_sweep[i] = True
            consumed = True
    return fresh_high_sweep


def to_no_fill(trade: TradeResult) -> TradeResult:
    return trade._replace(
        fill_bar=-1,
        exit_type=EXIT_NO_FILL,
        exit_bar=-1,
        pnl_points=0.0,
        pnl_usd=0.0,
        r_multiple=0.0,
        fill_time="",
        exit_time="",
    )


def run_baseline(leg: LegSpec, symbol_data: dict) -> list[TradeResult]:
    return run_backtest(
        symbol_data["df_5m"],
        leg.config,
        df_1m=symbol_data["df_1m"],
        df_1s=symbol_data["df_1s"],
        signal_df_1m=symbol_data["df_1m"],
        _maps=symbol_data["maps"],
    )


def evaluate_leg_filters(
    trades: list[TradeResult],
    *,
    df_5m,
    signal_df_1m,
    htf_spec: HtfSpec,
) -> dict:
    high = np.ascontiguousarray(df_5m["high"].to_numpy(dtype=np.float64))
    htf_levels = compute_htf_unswept_levels(
        df_5m,
        signal_df_1m,
        tf_minutes=htf_spec.tf_minutes,
        n_left=htf_spec.n_left,
    )
    active_high_price = htf_levels["active_high_price"]
    active_high_instance_id = htf_levels["active_high_instance_id"]
    fresh_high_sweep = build_fresh_high_sweep_flags(high, active_high_price, active_high_instance_id)

    annotations: list[dict] = []
    for trade in trades:
        arm_bar = min(trade.signal_bar + 1, len(high) - 1)
        active_high_at_arm = float(active_high_price[arm_bar])
        has_htf_high_ge_tp1 = bool(np.isfinite(active_high_at_arm) and active_high_at_arm >= trade.tp1_price)

        tp2_touched_pre_entry = False
        fresh_high_swept_pre_entry = False
        cancel_tp2_plus_high_sweep = False
        if trade.exit_type != EXIT_NO_FILL and trade.fill_bar > arm_bar:
            tp2_touched_pre_entry = bool(np.any(high[arm_bar:trade.fill_bar] >= trade.tp2_price))
            fresh_high_swept_pre_entry = bool(np.any(fresh_high_sweep[arm_bar:trade.fill_bar]))
            cancel_tp2_plus_high_sweep = tp2_touched_pre_entry and fresh_high_swept_pre_entry

        annotations.append(
            {
                "has_htf_high_ge_tp1": has_htf_high_ge_tp1,
                "active_high_at_arm": active_high_at_arm if np.isfinite(active_high_at_arm) else None,
                "tp2_touched_pre_entry": tp2_touched_pre_entry,
                "fresh_high_swept_pre_entry": fresh_high_swept_pre_entry,
                "cancel_tp2_plus_high_sweep": cancel_tp2_plus_high_sweep,
            }
        )

    cancel_variant = [
        to_no_fill(trade) if annotations[i]["cancel_tp2_plus_high_sweep"] and trade.exit_type != EXIT_NO_FILL else trade
        for i, trade in enumerate(trades)
    ]
    htf_tp1_filter_variant = [
        trade if annotations[i]["has_htf_high_ge_tp1"] or trade.exit_type == EXIT_NO_FILL else to_no_fill(trade)
        for i, trade in enumerate(trades)
    ]

    return {
        "annotations": annotations,
        "cancel_variant": cancel_variant,
        "htf_tp1_filter_variant": htf_tp1_filter_variant,
    }


def summarize_quality_subset(trades: list[TradeResult]) -> dict:
    fills = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    count = len(fills)
    if count == 0:
        return {
            "filled_trades": 0,
            "win_rate": 0.0,
            "avg_r": 0.0,
            "tp2_rate": 0.0,
            "total_r": 0.0,
        }
    wins = sum(1 for trade in fills if trade.r_multiple > 0)
    tp2_hits = sum(1 for trade in fills if trade.exit_type in {EXIT_TP1_TP2, EXIT_TP2_SINGLE})
    return {
        "filled_trades": count,
        "win_rate": wins / count,
        "avg_r": float(sum(trade.r_multiple for trade in fills) / count),
        "tp2_rate": tp2_hits / count,
        "total_r": float(sum(trade.r_multiple for trade in fills)),
    }


def quality_split(
    trades: list[TradeResult],
    annotations: list[dict],
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    window_trades = filter_window(trades, start=start, end=end)
    with_headroom = [
        trade
        for trade, ann in zip(trades, annotations, strict=True)
        if (start is None or trade.date >= start)
        and (end is None or trade.date < end)
        and ann["has_htf_high_ge_tp1"]
    ]
    without_headroom = [
        trade
        for trade, ann in zip(trades, annotations, strict=True)
        if (start is None or trade.date >= start)
        and (end is None or trade.date < end)
        and not ann["has_htf_high_ge_tp1"]
    ]
    return {
        "baseline_fills": summarize_quality_subset(window_trades),
        "with_htf_high_ge_tp1": summarize_quality_subset(with_headroom),
        "without_htf_high_ge_tp1": summarize_quality_subset(without_headroom),
    }


def print_variant_table(leg_label: str, window_label: str, baseline_cmp: dict, variants: dict[str, dict]) -> None:
    print(f"\n{leg_label} — {window_label}")
    print(
        "  "
        f"{'variant':<20} {'fills':>6} {'no_fill':>8} {'net_r':>8} {'max_dd':>8} "
        f"{'delta_r':>8} {'delta_dd':>9} {'base_only_r':>11}"
    )
    rows = [("baseline", baseline_cmp)]
    rows.extend((name, data) for name, data in variants.items())
    for name, data in rows:
        summary = data["summary"]
        delta = data["delta_vs_baseline"]
        base_only = data["baseline_only_fills"]
        print(
            "  "
            f"{name:<20} {summary['filled_trades']:>6d} {summary['no_fills']:>8d} "
            f"{summary['total_r']:>8.1f} {summary['max_drawdown_r']:>8.1f} "
            f"{delta['total_r']:>+8.1f} {delta['max_drawdown_r']:>+9.1f} "
            f"{base_only['total_r']:>+11.1f}"
        )


def print_quality_table(leg_label: str, window_label: str, quality: dict) -> None:
    print(f"\n{leg_label} — {window_label} quality split")
    print(
        "  "
        f"{'bucket':<24} {'fills':>6} {'wr':>7} {'avg_r':>8} {'tp2_rate':>10} {'total_r':>9}"
    )
    for name in ("baseline_fills", "with_htf_high_ge_tp1", "without_htf_high_ge_tp1"):
        row = quality[name]
        print(
            "  "
            f"{name:<24} {row['filled_trades']:>6d} {row['win_rate'] * 100:>6.1f}% "
            f"{row['avg_r']:>8.3f} {row['tp2_rate'] * 100:>9.1f}% {row['total_r']:>+9.1f}"
        )


def main() -> None:
    t0 = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 96)
    print("ALPHA_V1 ORB HTF-HIGH FILTER EXPLORATION")
    print("=" * 96)
    print(f"Recent window starts: {RECENT_START}")

    symbol_data = {symbol: load_symbol_data(symbol) for symbol in ("NQ", "ES")}
    legs = build_orb_legs()
    windows = {
        "full_history": {"start": None, "end": None, "label": "Full History"},
        "recent_2024_plus": {"start": RECENT_START, "end": None, "label": f"Recent ({RECENT_START}+)"}
    }
    summary: dict[str, dict] = {
        "as_of_date": "2026-04-17",
        "recent_start": RECENT_START,
        "htf_assumption": "Instrument-native published unswept HTF high detector (NQ: 60m n_left=3; ES: 90m n_left=3).",
        "legs": {},
    }

    for leg in legs:
        print(f"\nRunning {leg.label} using {leg.htf_spec.label}...")
        leg_t0 = time.time()
        baseline = run_baseline(leg, symbol_data[leg.symbol])
        analysis = evaluate_leg_filters(
            baseline,
            df_5m=symbol_data[leg.symbol]["df_5m"],
            signal_df_1m=symbol_data[leg.symbol]["df_1m"],
            htf_spec=leg.htf_spec,
        )
        cancel_variant = analysis["cancel_variant"]
        htf_tp1_filter_variant = analysis["htf_tp1_filter_variant"]
        annotations = analysis["annotations"]

        filled = sum(1 for t in baseline if t.exit_type != EXIT_NO_FILL)
        net_r = sum(t.r_multiple for t in baseline if t.exit_type != EXIT_NO_FILL)
        cancel_count = sum(1 for ann in annotations if ann["cancel_tp2_plus_high_sweep"])
        headroom_count = sum(1 for ann in annotations if ann["has_htf_high_ge_tp1"])
        print(
            f"  baseline fills={filled:>4d} net_r={net_r:>7.1f} "
            f"| tp2+sweep cancels={cancel_count:>3d} | htf>=tp1 signals={headroom_count:>4d} "
            f"[{time.time() - leg_t0:.1f}s]"
        )

        leg_summary = {
            "label": leg.label,
            "symbol": leg.symbol,
            "htf_spec": {
                "tf_minutes": leg.htf_spec.tf_minutes,
                "n_left": leg.htf_spec.n_left,
                "label": leg.htf_spec.label,
            },
            "raw_counts": {
                "baseline_total_signals": len(baseline),
                "tp2_plus_high_sweep_cancel_count": cancel_count,
                "htf_high_ge_tp1_signal_count": headroom_count,
            },
            "windows": {},
        }

        for window_key, window in windows.items():
            baseline_cmp = compare_vs_baseline(
                baseline,
                baseline,
                start=window["start"],
                end=window["end"],
            )
            variants = {
                "tp2_plus_htf_sweep_cancel": compare_vs_baseline(
                    baseline,
                    cancel_variant,
                    start=window["start"],
                    end=window["end"],
                ),
                "htf_high_ge_tp1_filter": compare_vs_baseline(
                    baseline,
                    htf_tp1_filter_variant,
                    start=window["start"],
                    end=window["end"],
                ),
            }
            quality = quality_split(
                baseline,
                annotations,
                start=window["start"],
                end=window["end"],
            )

            print_variant_table(leg.label, window["label"], baseline_cmp, variants)
            print_quality_table(leg.label, window["label"], quality)

            leg_summary["windows"][window_key] = {
                "baseline": baseline_cmp,
                "tp2_plus_htf_sweep_cancel": variants["tp2_plus_htf_sweep_cancel"],
                "htf_high_ge_tp1_filter": variants["htf_high_ge_tp1_filter"],
                "quality_split": quality,
            }

        summary["legs"][leg.key] = leg_summary

    with SUMMARY_PATH.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved summary to {SUMMARY_PATH}")
    print(f"Completed in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
