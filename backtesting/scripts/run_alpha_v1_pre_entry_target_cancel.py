#!/usr/bin/env python3
"""Explore pre-entry TP-touch cancellation for active ALPHA_V1 legs.

Compares the active ALPHA_V1 lineup from ``backtesting/learnings/ALPHA_V1.md``
across three variants:
1. Baseline behaviour
2. Cancel pending limit orders if TP1 is touched before entry
3. Cancel pending limit orders if TP2 is touched before entry

The script writes a machine-readable summary JSON and prints compact tables for
full history and a recent window.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES, NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, build_maps, run_backtest
from orb_backtest.results.metrics import compute_metrics

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config


RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_pre_entry_target_cancel_20260417"
SUMMARY_PATH = RESULT_DIR / "summary.json"
RECENT_START = "2024-01-01"


@dataclass(frozen=True)
class LegSpec:
    key: str
    label: str
    symbol: str
    config: StrategyConfig


def build_active_legs() -> list[LegSpec]:
    return [
        LegSpec(
            key="nq_ny_htf_lsi",
            label="HTF_LSI/NQ_NY-L24",
            symbol="NQ",
            config=build_current_nq_ny_htf_lsi_lag24_config(
                name="ALPHA_V1 NQ NY HTF_LSI baseline",
            ),
        ),
        LegSpec(
            key="nq_asia_orb",
            label="ORB/NQ_ASIA-RR6",
            symbol="NQ",
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


def run_variant(leg: LegSpec, cancel_mode: str, symbol_data: dict) -> list[TradeResult]:
    label = cancel_mode or "baseline"
    config = replace(
        leg.config,
        name=f"{leg.config.name} [{label}]",
        limit_cancel_on_pre_entry_target_touch=cancel_mode,
    )
    return run_backtest(
        symbol_data["df_5m"],
        config,
        df_1m=symbol_data["df_1m"],
        df_1s=symbol_data["df_1s"],
        signal_df_1m=symbol_data["df_1m"],
        _maps=symbol_data["maps"],
    )


def print_window_table(leg_label: str, window_label: str, baseline_cmp: dict, variants: dict[str, dict]) -> None:
    print(f"\n{leg_label} — {window_label}")
    print(
        "  "
        f"{'variant':<10} {'fills':>6} {'no_fill':>8} {'net_r':>8} {'max_dd':>8} "
        f"{'delta_r':>8} {'delta_dd':>9} {'base_only_r':>11} {'var_only_r':>10}"
    )
    rows = [("baseline", baseline_cmp)]
    rows.extend((name, data) for name, data in variants.items())
    for name, data in rows:
        summary = data["summary"]
        delta = data["delta_vs_baseline"]
        base_only = data["baseline_only_fills"]
        var_only = data["variant_only_fills"]
        print(
            "  "
            f"{name:<10} {summary['filled_trades']:>6d} {summary['no_fills']:>8d} "
            f"{summary['total_r']:>8.1f} {summary['max_drawdown_r']:>8.1f} "
            f"{delta['total_r']:>+8.1f} {delta['max_drawdown_r']:>+9.1f} "
            f"{base_only['total_r']:>+11.1f} {var_only['total_r']:>+10.1f}"
        )


def main() -> None:
    t0 = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 92)
    print("ALPHA_V1 PRE-ENTRY TARGET TOUCH CANCEL EXPLORATION")
    print("=" * 92)
    print(f"Recent window starts: {RECENT_START}")

    symbol_data = {symbol: load_symbol_data(symbol) for symbol in ("NQ", "ES")}
    legs = build_active_legs()

    windows = {
        "full_history": {"start": None, "end": None, "label": "Full History"},
        "recent_2024_plus": {"start": RECENT_START, "end": None, "label": f"Recent ({RECENT_START}+)"}
    }
    summary: dict[str, dict] = {
        "as_of_date": "2026-04-17",
        "recent_start": RECENT_START,
        "legs": {},
    }

    for leg in legs:
        print(f"\nRunning {leg.label}...")
        leg_results: dict[str, list[TradeResult]] = {}
        for cancel_mode in ("", "tp1", "tp2"):
            label = cancel_mode or "baseline"
            t_leg = time.time()
            leg_results[label] = run_variant(leg, cancel_mode, symbol_data[leg.symbol])
            filled = sum(1 for t in leg_results[label] if t.exit_type != EXIT_NO_FILL)
            net_r = sum(t.r_multiple for t in leg_results[label] if t.exit_type != EXIT_NO_FILL)
            print(f"  {label:<8} fills={filled:>4d} net_r={net_r:>7.1f} [{time.time() - t_leg:.1f}s]")

        baseline = leg_results["baseline"]
        leg_summary = {
            "label": leg.label,
            "symbol": leg.symbol,
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
                name: compare_vs_baseline(
                    baseline,
                    leg_results[name],
                    start=window["start"],
                    end=window["end"],
                )
                for name in ("tp1", "tp2")
            }
            print_window_table(leg.label, window["label"], baseline_cmp, variants)
            leg_summary["windows"][window_key] = {
                "baseline": baseline_cmp,
                "tp1": variants["tp1"],
                "tp2": variants["tp2"],
            }

        summary["legs"][leg.key] = leg_summary

    with SUMMARY_PATH.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved summary to {SUMMARY_PATH}")
    print(f"Completed in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
