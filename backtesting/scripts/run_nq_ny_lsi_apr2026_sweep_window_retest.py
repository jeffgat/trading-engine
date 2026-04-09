#!/usr/bin/env python3
"""NQ NY LSI retest for the April 2026 sweep-window / stale-pivot hypothesis.

Study design:
1. Patched controls on 2016-01-01 to 2025-12-31
2. Corrected anchor with sweep window 08:30-14:30 ET and all weekdays enabled
3. Broad lsi_n_left sweep with lsi_n_right fixed at 60
4. Post-hoc DOW combo analysis on the best corrected variant
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, build_maps, build_signal_cache, run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
END_DATE = "2026-01-01"  # exclusive -> includes 2025-12-31
YEARS = 10.0
LEFT_VALUES = [8, 10, 12, 15, 20, 25, 30, 40]
EXTENDED_LEFT_VALUES = [50, 60]
DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}


BASE_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

CORRECTED_SESSION = replace(
    BASE_SESSION,
    sweep_start="08:30",
    sweep_end="14:30",
)

BASE_CONFIG = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="lsi",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=3.0,
    tp1_ratio=0.34,
    atr_length=10,
    lsi_n_left=8,
    lsi_n_right=60,
    lsi_fvg_window_left=20,
    lsi_fvg_window_right=5,
    lsi_stop_mode="absolute",
    lsi_entry_mode="fvg_limit",
)


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def neg_years(metrics: dict) -> int:
    return sum(1 for year, value in metrics["r_by_year"].items() if year != "2026" and value < 0)


def trade_count_by_dow(trades: list) -> dict[str, int]:
    from datetime import datetime

    counts: dict[str, int] = {}
    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL:
            continue
        dow = datetime.strptime(trade.date, "%Y-%m-%d").weekday()
        label = DOW_NAMES[dow]
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def summarize(label: str, config: StrategyConfig, trades: list) -> dict:
    metrics = compute_metrics(trades)
    filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    stop_ticks = [trade.risk_points / config.instrument.min_tick for trade in filled]
    summary = {
        "label": label,
        "name": config.name or label,
        "trades": metrics["total_trades"],
        "trades_per_year": metrics["total_trades"] / YEARS,
        "win_rate": metrics["win_rate"],
        "pf": metrics["profit_factor"],
        "sharpe": metrics["sharpe_ratio"],
        "net_r": metrics["total_r"],
        "max_dd_r": metrics["max_drawdown_r"],
        "calmar": metrics["calmar_ratio"],
        "median_stop_ticks": median(stop_ticks) if stop_ticks else 0.0,
        "neg_years": neg_years(metrics),
        "r_by_year": metrics["r_by_year"],
        "pnl_by_dow": metrics["pnl_by_dow"],
        "trade_count_by_dow": trade_count_by_dow(trades),
    }
    return summary


def print_summary(summary: dict) -> None:
    print(
        f"{summary['label']:<26} "
        f"trades={summary['trades']:>4} "
        f"wr={fmt_pct(summary['win_rate']):>6} "
        f"pf={summary['pf']:.2f} "
        f"sharpe={summary['sharpe']:.2f} "
        f"netR={summary['net_r']:+.1f} "
        f"dd={summary['max_dd_r']:.1f} "
        f"calmar={summary['calmar']:.2f} "
        f"medStop={summary['median_stop_ticks']:.1f}t "
        f"negY={summary['neg_years']}",
        flush=True,
    )


def dow_combo_table(trades: list) -> list[dict]:
    rows = []
    weekdays = [0, 1, 2, 3, 4]
    for count in range(0, 6):
        for excluded in combinations(weekdays, count):
            filtered = apply_dow_filter(trades, set(excluded))
            metrics = compute_metrics(filtered)
            rows.append(
                {
                    "excluded_days": [DOW_NAMES[d] for d in excluded],
                    "trades": metrics["total_trades"],
                    "win_rate": metrics["win_rate"],
                    "pf": metrics["profit_factor"],
                    "sharpe": metrics["sharpe_ratio"],
                    "net_r": metrics["total_r"],
                    "max_dd_r": metrics["max_drawdown_r"],
                    "calmar": metrics["calmar_ratio"],
                    "neg_years": neg_years(metrics),
                }
            )
    rows.sort(key=lambda row: (row["calmar"], row["net_r"], row["trades"]), reverse=True)
    return rows


def main() -> None:
    started = time.time()

    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")

    print("Building bar maps...", flush=True)
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)

    patched_frozen = replace(
        BASE_CONFIG,
        excluded_days=(2, 3),
        name="NQ NY 2016-2025 ALPHA_LSI patched frozen",
    )
    patched_all_days = replace(
        BASE_CONFIG,
        excluded_days=(),
        name="NQ NY 2016-2025 ALPHA_LSI patched allDays",
    )
    corrected_anchor = replace(
        BASE_CONFIG,
        sessions=(CORRECTED_SESSION,),
        excluded_days=(),
        name="NQ NY 2016-2025 ALPHA_LSI allDays sweep0830-1430 anchor",
    )

    sweep_configs = [
        replace(
            corrected_anchor,
            lsi_n_left=value,
            name=f"NQ NY 2016-2025 ALPHA_LSI allDays sweep0830-1430 nleft{value}",
        )
        for value in LEFT_VALUES
    ]
    configs = [patched_frozen, patched_all_days, corrected_anchor, *sweep_configs]

    print("Building signal cache for all study configs...", flush=True)
    signal_cache = build_signal_cache(df_5m, configs)

    control_results: dict[str, tuple[dict, list]] = {}
    for label, cfg in [
        ("patched_frozen", patched_frozen),
        ("patched_all_days", patched_all_days),
        ("corrected_anchor", corrected_anchor),
    ]:
        print(f"Running {label}...", flush=True)
        trades = run_backtest(
            df_5m,
            cfg,
            start_date=START_DATE,
            end_date=END_DATE,
            df_1m=df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        control_results[label] = (summarize(label, cfg, trades), trades)
        print_summary(control_results[label][0])

    print("\nSweeping lsi_n_left...", flush=True)
    sweep_rows: list[dict] = []
    sweep_trade_map: dict[int, list] = {}
    for cfg in sweep_configs:
        trades = run_backtest(
            df_5m,
            cfg,
            start_date=START_DATE,
            end_date=END_DATE,
            df_1m=df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        row = summarize(f"n_left={cfg.lsi_n_left}", cfg, trades)
        row["lsi_n_left"] = cfg.lsi_n_left
        sweep_rows.append(row)
        sweep_trade_map[cfg.lsi_n_left] = trades
        print_summary(row)

    best_initial = max(sweep_rows, key=lambda row: (row["calmar"], row["net_r"], row["trades"]))
    if best_initial["lsi_n_left"] == max(LEFT_VALUES):
        print("\nWinner landed at the upper boundary. Extending sweep to 50/60...", flush=True)
        extended_configs = [
            replace(
                corrected_anchor,
                lsi_n_left=value,
                name=f"NQ NY 2016-2025 ALPHA_LSI allDays sweep0830-1430 nleft{value}",
            )
            for value in EXTENDED_LEFT_VALUES
        ]
        signal_cache = build_signal_cache(df_5m, [*configs, *extended_configs])
        for cfg in extended_configs:
            trades = run_backtest(
                df_5m,
                cfg,
                start_date=START_DATE,
                end_date=END_DATE,
                df_1m=df_1m,
                df_1s=df_1s,
                _maps=maps,
                _signal_cache=signal_cache,
            )
            row = summarize(f"n_left={cfg.lsi_n_left}", cfg, trades)
            row["lsi_n_left"] = cfg.lsi_n_left
            sweep_rows.append(row)
            sweep_trade_map[cfg.lsi_n_left] = trades
            print_summary(row)

    sweep_rows.sort(key=lambda row: (row["calmar"], row["net_r"], row["trades"]), reverse=True)
    best_row = sweep_rows[0]
    best_trades = sweep_trade_map[best_row["lsi_n_left"]]

    print("\nTop lsi_n_left rows:", flush=True)
    for row in sweep_rows[:5]:
        print_summary(row)

    print("\nPost-hoc DOW combo analysis on the best corrected variant...", flush=True)
    dow_rows = dow_combo_table(best_trades)
    for row in dow_rows[:10]:
        excluded = ",".join(row["excluded_days"]) if row["excluded_days"] else "none"
        print(
            f"exclude={excluded:<15} trades={row['trades']:>4} "
            f"wr={fmt_pct(row['win_rate']):>6} pf={row['pf']:.2f} "
            f"sharpe={row['sharpe']:.2f} netR={row['net_r']:+.1f} "
            f"dd={row['max_dd_r']:.1f} calmar={row['calmar']:.2f} negY={row['neg_years']}",
            flush=True,
        )

    wed_thu = next(row for row in dow_rows if row["excluded_days"] == ["Wed", "Thu"])

    payload = {
        "study_window": {"start": START_DATE, "end_exclusive": END_DATE},
        "controls": {key: value[0] for key, value in control_results.items()},
        "sweep_rows": sweep_rows,
        "best_corrected_variant": best_row,
        "dow_top10": dow_rows[:10],
        "dow_wed_thu": wed_thu,
        "elapsed_sec": round(time.time() - started, 2),
    }
    print("\nJSON_SUMMARY", json.dumps(payload, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
