#!/usr/bin/env python3
"""Engine-level replay of NQ NY ORB R11 15m structure + VWAP gates.

This is the follow-up to the entry-time proxy screen in
``run_alpha_v1_next_steps_20260516.py``.  The gate is applied at the
continuation candidate's signal bar before ORB daily candidate selection, so a
rejected first setup can still be replaced by a later same-day valid setup.
"""

from __future__ import annotations

import csv
import math
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
BT_ROOT = SCRIPT_DIR.parent

for path in (BT_ROOT / "src", SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import get_instrument  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NAMES,
    EXIT_NO_FILL,
    TradeResult,
    build_maps,
    build_signal_cache,
    run_backtest,
)


RUN_SLUG = "alpha_v1_r11_structure_gate_engine_replay_20260516"
OUT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_R11_STRUCTURE_GATE_ENGINE_REPLAY_20260516.md"

FULL_START = "2016-04-17"
END_EXCLUSIVE = "2026-03-25"
LAST_1Y_START = "2025-03-25"

GATES = (
    "",
    "any2of3_vwap_d10",
    "hh_or_hl_vwap_d10",
    "score_gte2_vwap_d10",
    "any2of3_vwap",
    "hh_hl_2_vwap",
)

WINDOWS = (
    ("full", FULL_START, END_EXCLUSIVE),
    ("2024_plus", "2024-01-01", END_EXCLUSIVE),
    ("2025_plus", "2025-01-01", END_EXCLUSIVE),
    ("last_1y", LAST_1Y_START, END_EXCLUSIVE),
)


def _round(value: Any, digits: int = 3) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return round(number, digits)


def _fmt(value: Any, digits: int = 1) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "-"
    return f"{number:,.{digits}f}"


def _fmt_r(value: Any, digits: int = 1) -> str:
    return f"{_fmt(value, digits)}R"


def _fmt_pct(value: Any, digits: int = 1) -> str:
    return f"{_fmt(value, digits)}%"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def max_drawdown(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    equity = np.concatenate([[0.0], np.cumsum(values)])
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def profit_factor(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    wins = values[values > 0.0].sum()
    losses = values[values < 0.0].sum()
    if losses == 0.0:
        return float("inf") if wins > 0.0 else 0.0
    return float(wins / abs(losses))


def net_r(trade: TradeResult) -> float:
    return float(trade.net_r_multiple or trade.r_multiple)


def gross_r(trade: TradeResult) -> float:
    return float(trade.r_multiple)


def filled(trades: list[TradeResult]) -> list[TradeResult]:
    return [t for t in trades if t.exit_type != EXIT_NO_FILL]


def trade_day(trade: TradeResult) -> pd.Timestamp:
    source = trade.fill_time or trade.date
    timestamp = pd.Timestamp(source)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("America/New_York")
    else:
        timestamp = timestamp.tz_convert("America/New_York")
    return timestamp.normalize().tz_localize(None)


def in_window(trades: list[TradeResult], start: str, end_exclusive: str) -> list[TradeResult]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end_exclusive)
    return [t for t in trades if start_ts <= trade_day(t) < end_ts]


def summarize(trades: list[TradeResult], *, total_candidates: int) -> dict[str, Any]:
    values = np.array([net_r(t) for t in trades], dtype=np.float64)
    gross_values = np.array([gross_r(t) for t in trades], dtype=np.float64)
    exit_types = [EXIT_NAMES.get(t.exit_type, str(t.exit_type)) for t in trades]
    full_targets = sum(1 for name in exit_types if name in {"tp1_tp2", "tp2_single"})
    stops = sum(1 for name in exit_types if name in {"sl", "be_sl"})
    avg = float(values.mean()) if values.size else 0.0
    std = float(values.std(ddof=1)) if values.size > 1 else 0.0
    sharpe = avg / std * math.sqrt(252.0) if std > 0.0 else 0.0
    return {
        "candidates": int(total_candidates),
        "trades": int(len(trades)),
        "keep_rate_pct": 0.0 if total_candidates == 0 else float(len(trades) / total_candidates * 100.0),
        "net_r": float(values.sum()) if values.size else 0.0,
        "gross_r": float(gross_values.sum()) if gross_values.size else 0.0,
        "win_rate_pct": float((values > 0.0).mean() * 100.0) if values.size else 0.0,
        "pf": profit_factor(values),
        "closed_dd_r": max_drawdown(values),
        "avg_r": avg,
        "sharpe": sharpe,
        "full_target_pct": 0.0 if not trades else float(full_targets / len(trades) * 100.0),
        "stop_pct": 0.0 if not trades else float(stops / len(trades) * 100.0),
    }


def build_r11_config(gate: str = "") -> StrategyConfig:
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
        instrument=get_instrument("MNQ"),
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=250.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.4,
        exit_mode="split",
        atr_length=12,
        excluded_days=(4,),
        impulse_close_filter=False,
        structure_vwap_gate=gate,
        name=f"NQ NY ORB R11 {gate or 'baseline'}",
    )


def trade_rows(label: str, gate: str, trades: list[TradeResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for t in trades:
        rows.append(
            {
                "variant": label,
                "structure_vwap_gate": gate,
                "date": t.date,
                "session": t.session,
                "direction": t.direction,
                "signal_bar": t.signal_bar,
                "fill_bar": t.fill_bar,
                "exit_bar": t.exit_bar,
                "fill_time": t.fill_time,
                "exit_time": t.exit_time,
                "exit_type": EXIT_NAMES.get(t.exit_type, str(t.exit_type)),
                "entry_price": _round(t.entry_price, 2),
                "stop_price": _round(t.stop_price, 2),
                "tp1_price": _round(t.tp1_price, 2),
                "tp2_price": _round(t.tp2_price, 2),
                "risk_points": _round(t.risk_points, 2),
                "qty": _round(t.qty, 0),
                "gross_r": _round(t.r_multiple, 4),
                "net_r": _round(net_r(t), 4),
                "commission_usd": _round(t.commission_usd, 2),
                "pnl_usd": _round(t.pnl_usd, 2),
            }
        )
    return rows


def config_rows() -> list[list[str]]:
    cfg = build_r11_config("")
    session = cfg.sessions[0]
    return [
        ["instrument", cfg.instrument.symbol],
        ["session", f"{session.name} ({session.orb_start}-{session.orb_end} ORB, {session.entry_start}-{session.entry_end} entry, flat {session.flat_start})"],
        ["strategy", cfg.strategy],
        ["direction_filter", cfg.direction_filter],
        ["stop_atr_pct", str(session.stop_atr_pct)],
        ["min_gap_atr_pct", str(session.min_gap_atr_pct)],
        ["atr_length", str(cfg.atr_length)],
        ["rr", str(cfg.rr)],
        ["tp1_ratio", str(cfg.tp1_ratio)],
        ["exit_mode", cfg.exit_mode],
        ["excluded_days", "Friday"],
        ["risk_usd", f"${cfg.risk_usd:,.0f}"],
        ["commission", f"${cfg.instrument.commission:.3f}/contract/side"],
        ["magnifier", "5m -> 1m hierarchical"],
    ]


def deployability(gate: str) -> str:
    return "live_native" if not gate else "post_filter_only"


def live_support_notes(gate: str) -> str:
    if not gate:
        return "Baseline NQ NY ORB R11 parameters are already expressible in the live ORB execution profile."
    return "Causal research-engine gate, but production execution does not yet compute 15m structure/VWAP before arming."


def exact_replay_required(gate: str) -> str:
    if not gate:
        return "completed_through_2026-03-24"
    return "yes_after_live_pretrade_gate_implementation"


def main() -> None:
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("ALPHA_V1 R11 structure gate engine replay")
    print("=" * 72)
    print("Loading NQ data...")
    df_5m = load_5m_data("NQ_5m.parquet", start=FULL_START, end=END_EXCLUSIVE)
    df_1m = load_1m_for_5m("NQ_5m.parquet", start=FULL_START, end=END_EXCLUSIVE)
    print(f"  5m={len(df_5m):,} | 1m={len(df_1m):,}")

    configs = [build_r11_config(gate) for gate in GATES]
    print("Building maps/cache...")
    maps = build_maps(df_5m, df_1m)
    cache = build_signal_cache(df_5m, configs)

    all_filled: dict[str, list[TradeResult]] = {}
    all_candidates: dict[str, int] = {}
    metrics_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    all_trade_rows: list[dict[str, Any]] = []

    for cfg in configs:
        gate = cfg.structure_vwap_gate
        label = gate or "baseline"
        print(f"Running {label}...")
        raw = run_backtest(
            df_5m,
            cfg,
            start_date=FULL_START,
            end_date=END_EXCLUSIVE,
            df_1m=df_1m,
            _maps=maps,
            _signal_cache=cache,
        )
        filled_trades = filled(raw)
        all_filled[label] = filled_trades
        all_candidates[label] = len(raw)

        full_metrics = summarize(filled_trades, total_candidates=len(raw))
        metrics_rows.append(
            {
                "variant": label,
                "structure_vwap_gate": gate,
                **{k: _round(v, 4) for k, v in full_metrics.items()},
                "deployability": deployability(gate),
                "live_support_notes": live_support_notes(gate),
                "exact_replay_required": exact_replay_required(gate),
            }
        )
        for window, start, end in WINDOWS:
            subset = in_window(filled_trades, start, end)
            window_metrics = summarize(subset, total_candidates=len(raw))
            window_rows.append(
                {
                    "window": window,
                    "start": start,
                    "end_exclusive": end,
                    "variant": label,
                    "structure_vwap_gate": gate,
                    **{k: _round(v, 4) for k, v in window_metrics.items()},
                    "deployability": deployability(gate),
                    "live_support_notes": live_support_notes(gate),
                    "exact_replay_required": exact_replay_required(gate),
                }
            )
        all_trade_rows.extend(trade_rows(label, gate, filled_trades))

        print(
            "  {trades} trades | {net:+.1f}R net | PF {pf:.2f} | DD {dd:.1f}R".format(
                trades=full_metrics["trades"],
                net=full_metrics["net_r"],
                pf=full_metrics["pf"],
                dd=full_metrics["closed_dd_r"],
            )
        )

    _write_csv(OUT_DIR / "variant_metrics.csv", metrics_rows)
    _write_csv(OUT_DIR / "window_metrics.csv", window_rows)
    _write_csv(OUT_DIR / "filled_trades.csv", all_trade_rows)

    baseline = next(row for row in metrics_rows if row["variant"] == "baseline")
    metric_table: list[list[Any]] = []
    for row in metrics_rows:
        delta = float(row["net_r"]) - float(baseline["net_r"])
        metric_table.append(
            [
                row["variant"],
                int(row["trades"]),
                _fmt_pct(row["keep_rate_pct"]),
                _fmt_r(row["net_r"]),
                f"{delta:+.1f}R",
                _fmt(row["pf"], 2),
                _fmt_r(row["closed_dd_r"]),
                _fmt_pct(row["win_rate_pct"]),
                _fmt_pct(row["full_target_pct"]),
                row["deployability"],
            ]
        )

    last_rows: list[list[Any]] = []
    for window_name in ("2025_plus", "last_1y"):
        base = next(row for row in window_rows if row["window"] == window_name and row["variant"] == "baseline")
        for row in [r for r in window_rows if r["window"] == window_name]:
            delta = float(row["net_r"]) - float(base["net_r"])
            last_rows.append(
                [
                    window_name,
                    row["variant"],
                    int(row["trades"]),
                    _fmt_r(row["net_r"]),
                    f"{delta:+.1f}R",
                    _fmt(row["pf"], 2),
                    _fmt_r(row["closed_dd_r"]),
                ]
            )

    deploy_rows = [
        [
            row["variant"],
            row["deployability"],
            row["live_support_notes"],
            row["exact_replay_required"],
        ]
        for row in metrics_rows
    ]

    any2 = next(row for row in metrics_rows if row["variant"] == "any2of3_vwap_d10")
    any2_delta = float(any2["net_r"]) - float(baseline["net_r"])
    if any2_delta >= 0.0 and float(any2["closed_dd_r"]) >= float(baseline["closed_dd_r"]):
        verdict = (
            "`any2of3_vwap_d10` survived the true candidate replay and is worth a "
            "proper execution-parity implementation pass."
        )
    elif any2_delta >= -5.0:
        verdict = (
            "`any2of3_vwap_d10` is close but not a clean ALPHA upgrade on the "
            "research engine; keep it as a discretionary/context overlay, not a "
            "replacement gate yet."
        )
    else:
        verdict = (
            "`any2of3_vwap_d10` did not survive the true candidate replay. The "
            "proxy improvement was mostly not enough once the engine could choose "
            "later same-day setups."
        )

    report = f"""# ALPHA_V1 R11 Structure Gate Engine Replay - 2026-05-16

Report path: `{REPORT_PATH.relative_to(BT_ROOT)}`
Results path: `{OUT_DIR.relative_to(BT_ROOT)}`

## Why this run exists

The prior R11 read used an entry-minus-one-5m proxy because the cached exact CSV
did not include the original signal bar. This run adds a narrow
`structure_vwap_gate` research field to the ORB engine and applies each gate at
the candidate signal bar before one-trade-per-day ORB selection.

Deployability label: baseline is `live_native`; structure-gated variants are
`post_filter_only`. The replay itself is candidate-level and causal inside the
research engine, but the production execution router does not yet have this
pre-trade structure/VWAP gate.

## R11 Config

{md_table(["Parameter", "Value"], config_rows())}

## Full-Window Results

{md_table(["Variant", "Trades", "Keep", "Net R", "Delta", "PF", "DD", "WR", "Full TP", "Deployability"], metric_table)}

## Recent Windows

{md_table(["Window", "Variant", "Trades", "Net R", "Delta", "PF", "DD"], last_rows)}

## Deployability Details

{md_table(["Variant", "Deployability", "Live support notes", "Exact replay required"], deploy_rows)}

## Read

{verdict}

Strict `hh_hl_2_vwap` remains a high-selectivity diagnostic rather than an
ALPHA-grade replacement unless a separate lower-risk specialist sleeve is being
designed. The comparison that matters for candidate #7 is whether
`any2of3_vwap_d10` beats baseline without sacrificing the full-history R pool.

Artifacts:

- `variant_metrics.csv`
- `window_metrics.csv`
- `filled_trades.csv`

Runtime: {time.time() - t0:.1f}s
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"\nWrote {REPORT_PATH}")
    print(f"Wrote {OUT_DIR}")
    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
