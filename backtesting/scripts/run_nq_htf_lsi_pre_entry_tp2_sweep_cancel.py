#!/usr/bin/env python3
"""Evaluate HTF-LSI pre-entry TP2 cancel with and without a fresh sweep requirement."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.engine.simulator import EXIT_NO_FILL, build_maps, run_backtest
from orb_backtest.results.metrics import compute_metrics

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data


RESULT_DIR = ROOT / "data" / "results" / "nq_htf_lsi_pre_entry_tp2_sweep_cancel_20260417"
SUMMARY_PATH = RESULT_DIR / "summary.json"
RECENT_START = "2024-01-01"


def filter_window(trades, start: str | None = None, end: str | None = None):
    return [
        trade for trade in trades
        if (start is None or trade.date >= start) and (end is None or trade.date < end)
    ]


def summarize(trades):
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


def trade_key(trade):
    return (
        trade.date,
        trade.session,
        trade.direction,
        trade.signal_bar,
        round(float(trade.entry_price), 6),
        round(float(trade.stop_price), 6),
        round(float(trade.tp2_price), 6),
    )


def compare(baseline, variant, *, start: str | None = None, end: str | None = None):
    baseline_window = filter_window(baseline, start=start, end=end)
    variant_window = filter_window(variant, start=start, end=end)

    baseline_summary = summarize(baseline_window)
    variant_summary = summarize(variant_window)

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


def print_table(window_label: str, rows: dict[str, dict]) -> None:
    print(f"\n{window_label}")
    print(
        "  "
        f"{'variant':<18} {'fills':>6} {'no_fill':>8} {'net_r':>8} {'max_dd':>8} "
        f"{'delta_r':>8} {'delta_dd':>9} {'base_only_r':>11} {'var_only_r':>10}"
    )
    for name, data in rows.items():
        summary = data["summary"]
        delta = data["delta_vs_baseline"]
        base_only = data["baseline_only_fills"]
        var_only = data["variant_only_fills"]
        print(
            "  "
            f"{name:<18} {summary['filled_trades']:>6d} {summary['no_fills']:>8d} "
            f"{summary['total_r']:>8.1f} {summary['max_drawdown_r']:>8.1f} "
            f"{delta['total_r']:>+8.1f} {delta['max_drawdown_r']:>+9.1f} "
            f"{base_only['total_r']:>+11.1f} {var_only['total_r']:>+10.1f}"
        )


def main() -> None:
    t0 = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 92)
    print("NQ HTF-LSI PRE-ENTRY TP2 + SWEEP CANCEL")
    print("=" * 92)

    df, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    maps = build_maps(df, df_1m=df_1m, df_1s=df_1s)

    baseline_config = build_current_nq_ny_htf_lsi_lag24_config(
        name="NQ NY HTF_LSI baseline",
    )
    variants = {
        "baseline": baseline_config,
        "tp2_only": replace(
            baseline_config,
            name="NQ NY HTF_LSI tp2 pre-entry cancel",
            limit_cancel_on_pre_entry_target_touch="tp2",
        ),
        "tp2_plus_sweep": replace(
            baseline_config,
            name="NQ NY HTF_LSI tp2+sweep pre-entry cancel",
            limit_cancel_on_pre_entry_target_touch="tp2",
            limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep=True,
        ),
    }

    results = {}
    for name, config in variants.items():
        t_variant = time.time()
        trades = run_backtest(
            df,
            config,
            df_1m=df_1m,
            df_1s=df_1s,
            signal_df_1m=signal_df_1m,
            _maps=maps,
        )
        results[name] = trades
        filled = sum(1 for t in trades if t.exit_type != EXIT_NO_FILL)
        net_r = sum(t.r_multiple for t in trades if t.exit_type != EXIT_NO_FILL)
        print(f"{name:<18} fills={filled:>4d} net_r={net_r:>7.1f} [{time.time() - t_variant:.1f}s]")

    baseline = results["baseline"]
    full_rows = {
        name: compare(baseline, trades)
        for name, trades in results.items()
    }
    recent_rows = {
        name: compare(baseline, trades, start=RECENT_START)
        for name, trades in results.items()
    }

    print_table("Full History", full_rows)
    print_table(f"Recent ({RECENT_START}+)", recent_rows)

    summary = {
        "as_of_date": "2026-04-17",
        "recent_start": RECENT_START,
        "variants": {
            "baseline": full_rows["baseline"],
            "tp2_only": full_rows["tp2_only"],
            "tp2_plus_sweep": full_rows["tp2_plus_sweep"],
        },
        "recent_variants": {
            "baseline": recent_rows["baseline"],
            "tp2_only": recent_rows["tp2_only"],
            "tp2_plus_sweep": recent_rows["tp2_plus_sweep"],
        },
    }
    with SUMMARY_PATH.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved summary to {SUMMARY_PATH}")
    print(f"Completed in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
