#!/usr/bin/env python3
"""Diagnostic read on NQ entry mode vs inversion timing.

This is intentionally a cheap pre-promotion packet. It compares frozen winners
under pure `close`, pure `fvg_limit`, and an exact engine-level timed hybrid:

- choose `close` when sweep->inversion time is at or below a minute threshold
- otherwise use `fvg_limit`

Use this packet to decide whether a new hybrid thesis deserves a full re-sweep.
Do not treat the results as promotion-ready holdout evidence.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections import OrderedDict
from pathlib import Path

from htf_lsi_common import (
    RESULTS_ROOT,
    build_config,
    build_current_nq_ny_htf_lsi_lag24_config,
    load_timeframe_data,
)
from orb_backtest.analysis.regime_research import build_extended_regime_calendar, _regime_lookup
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, build_maps, run_backtest
from orb_backtest.results.metrics import compute_metrics


START_DATE = "2016-01-01"
END_DATE = "2025-03-31"
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
TIMED_HYBRID_THRESHOLDS_MINUTES = (5, 15)

OUTPUT_DIR = RESULTS_ROOT / "nq_entry_mode_inversion_timing_read"
REPORT_PATH = (
    Path(__file__).resolve().parent.parent
    / "learnings"
    / "reports"
    / "NQ_ENTRY_MODE_INVERSION_TIMING_READ.md"
)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def sort_trades(trades: list[TradeResult]) -> list[TradeResult]:
    return sorted(
        trades,
        key=lambda t: (
            t.date,
            t.fill_time or "",
            t.signal_bar,
            t.fill_bar,
            t.exit_time or "",
            t.entry_price,
        ),
    )


def analyze_trade_set(trades: list[TradeResult], timeframe_minutes: int) -> dict:
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    all_r = [0.0 if t.exit_type == EXIT_NO_FILL else float(t.r_multiple) for t in trades]
    filled_r = [float(t.r_multiple) for t in filled]
    all_minutes = [int(t.sweep_to_inversion_bars) * timeframe_minutes for t in trades]
    filled_minutes = [int(t.sweep_to_inversion_bars) * timeframe_minutes for t in filled]

    bins = OrderedDict(
        [
            ("<=5m", lambda minutes: minutes <= 5),
            ("6-15m", lambda minutes: 5 < minutes <= 15),
            (">15m", lambda minutes: minutes > 15),
        ]
    )

    by_bin: dict[str, dict] = {}
    for label, predicate in bins.items():
        subset = [t for t in trades if predicate(int(t.sweep_to_inversion_bars) * timeframe_minutes)]
        subset_filled = [t for t in subset if t.exit_type != EXIT_NO_FILL]
        count = len(subset)
        count_filled = len(subset_filled)
        by_bin[label] = {
            "signals": count,
            "filled": count_filled,
            "fill_rate": (count_filled / count) if count else None,
            "avg_r_all_signals": (
                sum(0.0 if t.exit_type == EXIT_NO_FILL else float(t.r_multiple) for t in subset) / count
            )
            if count
            else None,
            "avg_r_filled": (
                sum(float(t.r_multiple) for t in subset_filled) / count_filled
            )
            if count_filled
            else None,
            "win_rate_filled": (
                sum(1 for t in subset_filled if float(t.r_multiple) > 0.0) / count_filled
            )
            if count_filled
            else None,
        }

    metrics = compute_metrics(trades)
    return {
        "signals": len(trades),
        "filled": len(filled),
        "fill_rate": (len(filled) / len(trades)) if trades else None,
        "avg_r_all_signals": (sum(all_r) / len(all_r)) if all_r else None,
        "avg_r_filled": (sum(filled_r) / len(filled_r)) if filled_r else None,
        "net_r_filled": sum(filled_r),
        "corr_minutes_vs_r_all_signals": pearson(all_minutes, all_r),
        "corr_minutes_vs_r_filled": pearson(filled_minutes, filled_r),
        "metrics": metrics,
        "by_bin": by_bin,
    }


def format_float(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "NA"
    return f"{value:.{digits}f}"


def write_report(results: dict) -> None:
    lines = [
        "# NQ Entry Mode Inversion Timing Read",
        "",
        "- Objective: test whether faster sweep-to-inversion reactions should use `close` instead of `fvg_limit` on frozen NQ winners before reopening the discovery loop.",
        f"- Period: `{START_DATE}` to `{END_DATE}` (pre-holdout only).",
        "- Hybrid rows are exact engine runs using `lsi_entry_mode='timed_hybrid'` with explicit minute thresholds. They are still diagnostic, not promotion-grade holdout evidence.",
        "",
        "## Branch Verdicts",
    ]

    for branch_name, branch in results["branches"].items():
        pure_close = branch["modes"]["close"]
        pure_limit = branch["modes"]["fvg_limit"]
        hybrid_5 = branch["hybrids"]["timed_hybrid_le_5m"]
        hybrid_15 = branch["hybrids"]["timed_hybrid_le_15m"]

        lines.extend(
            [
                f"### {branch_name}",
                f"- Timeframe: `{branch['timeframe_minutes']}m`",
                f"- `close`: avg R/all `{format_float(pure_close['avg_r_all_signals'])}`, Calmar `{format_float(pure_close['metrics']['calmar_ratio'], 2)}`, DD `{format_float(pure_close['metrics']['max_drawdown_r'], 1)}R`",
                f"- `fvg_limit`: avg R/all `{format_float(pure_limit['avg_r_all_signals'])}`, Calmar `{format_float(pure_limit['metrics']['calmar_ratio'], 2)}`, DD `{format_float(pure_limit['metrics']['max_drawdown_r'], 1)}R`",
                f"- `timed_hybrid <=5m`: avg R/all `{format_float(hybrid_5['avg_r_all_signals'])}`, Calmar `{format_float(hybrid_5['metrics']['calmar_ratio'], 2)}`, DD `{format_float(hybrid_5['metrics']['max_drawdown_r'], 1)}R`",
                f"- `timed_hybrid <=15m`: avg R/all `{format_float(hybrid_15['avg_r_all_signals'])}`, Calmar `{format_float(hybrid_15['metrics']['calmar_ratio'], 2)}`, DD `{format_float(hybrid_15['metrics']['max_drawdown_r'], 1)}R`",
                "",
            ]
        )

    lines.extend(
        [
            "## Detailed Matrix",
            "",
            "| Branch | Variant | Signals | Filled | Fill Rate | Avg R / Signal | Avg R / Filled | Net R | Max DD | Calmar |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for branch_name, branch in results["branches"].items():
        rows = [
            ("close", branch["modes"]["close"]),
            ("fvg_limit", branch["modes"]["fvg_limit"]),
            ("timed_hybrid<=5m", branch["hybrids"]["timed_hybrid_le_5m"]),
            ("timed_hybrid<=15m", branch["hybrids"]["timed_hybrid_le_15m"]),
        ]
        for label, row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        branch_name,
                        label,
                        str(row["signals"]),
                        str(row["filled"]),
                        format_float(row["fill_rate"]),
                        format_float(row["avg_r_all_signals"]),
                        format_float(row["avg_r_filled"]),
                        format_float(row["net_r_filled"], 1),
                        format_float(row["metrics"]["max_drawdown_r"], 1),
                        format_float(row["metrics"]["calmar_ratio"], 2),
                    ]
                )
                + " |"
            )

    lines.extend(["", "## Inversion-Time Buckets", ""])

    for branch_name, branch in results["branches"].items():
        lines.append(f"### {branch_name}")
        lines.append("")
        lines.append("| Variant | Bucket | Signals | Filled | Fill Rate | Avg R / Signal | Avg R / Filled | WR Filled |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for label, row in (
            ("close", branch["modes"]["close"]),
            ("fvg_limit", branch["modes"]["fvg_limit"]),
        ):
            for bucket, bucket_row in row["by_bin"].items():
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            label,
                            bucket,
                            str(bucket_row["signals"]),
                            str(bucket_row["filled"]),
                            format_float(bucket_row["fill_rate"]),
                            format_float(bucket_row["avg_r_all_signals"]),
                            format_float(bucket_row["avg_r_filled"]),
                            format_float(bucket_row["win_rate_filled"]),
                        ]
                    )
                    + " |"
                )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading classic 5m data...", flush=True)
    classic_df = load_5m_data("NQ_5m.parquet")
    classic_df_1m = load_1m_for_5m("NQ_5m.parquet")
    classic_df_1s = load_1s_for_5m("NQ_5m.parquet")
    classic_maps = build_maps(classic_df, df_1m=classic_df_1m, df_1s=classic_df_1s)
    classic_lookup = _regime_lookup(build_extended_regime_calendar(classic_df), "combined_regime")

    def classic_gate(trades: list[TradeResult]) -> list[TradeResult]:
        return [
            trade
            for trade in trades
            if trade.exit_type == EXIT_NO_FILL or classic_lookup.get(trade.date) not in AVOID_BUCKETS
        ]

    print("Loading HTF 5m data...", flush=True)
    htf_5m_df, htf_5m_df_1m, htf_5m_df_1s, htf_5m_signal_1m = load_timeframe_data("5m")
    htf_5m_maps = build_maps(htf_5m_df, df_1m=htf_5m_df_1m, df_1s=htf_5m_df_1s)

    print("Loading HTF 2m data...", flush=True)
    htf_2m_df, htf_2m_df_1m, htf_2m_df_1s, htf_2m_signal_1m = load_timeframe_data("2m")
    htf_2m_maps = build_maps(htf_2m_df, df_1m=htf_2m_df_1m, df_1s=htf_2m_df_1s)

    classic_session = SessionConfig(
        name="NY",
        rth_start="09:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    classic_base = StrategyConfig(
        sessions=(classic_session,),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.0,
        tp1_ratio=0.5,
        atr_length=14,
        lsi_n_left=8,
        lsi_n_right=60,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=5,
        lsi_stop_mode="absolute",
        excluded_days=(2, 3),
        name="NQ NY classic LSI RR2/TP0.5 gated probe",
    )

    htf_5m_base = build_current_nq_ny_htf_lsi_lag24_config(
        name="NQ NY HTF_LSI 5m lag24 lead probe"
    )
    htf_2m_base = build_config(
        timeframe="2m",
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_start="08:30",
        entry_end="15:00",
        rr=3.0,
        tp1_ratio=0.6,
        min_gap_atr_pct=3.0,
        atr_length=14,
        htf_level_tf_minutes=60,
        htf_n_left=3,
        htf_trade_max_per_session=1,
        lsi_fvg_window_left=50,
        lsi_fvg_window_right=5,
        max_fvg_to_inversion_bars=0,
        name="NQ NY HTF_LSI 2m anchor probe",
    )

    branches = [
        {
            "name": "classic_lsi_rr2_gated",
            "timeframe_minutes": 5,
            "df": classic_df,
            "df_1m": classic_df_1m,
            "df_1s": classic_df_1s,
            "signal_df_1m": None,
            "maps": classic_maps,
            "base_config": classic_base,
            "gate": classic_gate,
        },
        {
            "name": "htf_lsi_5m_lag24",
            "timeframe_minutes": 5,
            "df": htf_5m_df,
            "df_1m": htf_5m_df_1m,
            "df_1s": htf_5m_df_1s,
            "signal_df_1m": htf_5m_signal_1m,
            "maps": htf_5m_maps,
            "base_config": htf_5m_base,
            "gate": lambda trades: trades,
        },
        {
            "name": "htf_lsi_2m_anchor",
            "timeframe_minutes": 2,
            "df": htf_2m_df,
            "df_1m": htf_2m_df_1m,
            "df_1s": htf_2m_df_1s,
            "signal_df_1m": htf_2m_signal_1m,
            "maps": htf_2m_maps,
            "base_config": htf_2m_base,
            "gate": lambda trades: trades,
        },
    ]

    results: dict[str, dict] = {
        "start_date": START_DATE,
        "end_date": END_DATE,
        "timed_hybrid_threshold_minutes": list(TIMED_HYBRID_THRESHOLDS_MINUTES),
        "branches": {},
    }

    for branch in branches:
        branch_name = branch["name"]
        timeframe_minutes = branch["timeframe_minutes"]
        print(f"\n=== {branch_name} ===", flush=True)

        mode_summary: dict[str, dict] = {}
        for mode in ("close", "fvg_limit"):
            cfg = dataclasses.replace(
                branch["base_config"],
                lsi_entry_mode=mode,
                name=f"{branch_name} {mode}",
            )
            print(f"Running {branch_name} / {mode}...", flush=True)
            trades = run_backtest(
                branch["df"],
                cfg,
                start_date=START_DATE,
                end_date=END_DATE,
                df_1m=branch["df_1m"],
                signal_df_1m=branch["signal_df_1m"],
                df_1s=branch["df_1s"],
                _maps=branch["maps"],
            )
            trades = sort_trades(branch["gate"](trades))
            mode_summary[mode] = analyze_trade_set(trades, timeframe_minutes)

        hybrid_summary: dict[str, dict] = {}
        for threshold in TIMED_HYBRID_THRESHOLDS_MINUTES:
            cfg = dataclasses.replace(
                branch["base_config"],
                lsi_entry_mode="timed_hybrid",
                lsi_close_on_sweep_to_inversion_minutes=threshold,
                name=f"{branch_name} timed_hybrid_le_{threshold}m",
            )
            print(f"Running {branch_name} / timed_hybrid <= {threshold}m...", flush=True)
            trades = run_backtest(
                branch["df"],
                cfg,
                start_date=START_DATE,
                end_date=END_DATE,
                df_1m=branch["df_1m"],
                signal_df_1m=branch["signal_df_1m"],
                df_1s=branch["df_1s"],
                _maps=branch["maps"],
            )
            trades = sort_trades(branch["gate"](trades))
            hybrid_key = f"timed_hybrid_le_{threshold}m"
            hybrid_summary[hybrid_key] = analyze_trade_set(trades, timeframe_minutes)

        results["branches"][branch_name] = {
            "timeframe_minutes": timeframe_minutes,
            "modes": mode_summary,
            "hybrids": hybrid_summary,
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(results, indent=2))
    write_report(results)

    print(f"\nSaved summary: {OUTPUT_DIR / 'summary.json'}", flush=True)
    print(f"Saved report:  {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
