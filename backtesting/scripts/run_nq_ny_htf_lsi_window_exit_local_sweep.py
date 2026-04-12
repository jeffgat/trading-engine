#!/usr/bin/env python3
"""Focused window and exit sweep around the NQ NY HTF-LSI 5m lag24 lead.

This is a local refinement pass, not a branch reopen:
- holds structure fixed to the promoted 5m lag24 lead
- sweeps entry windows inside the current 08:30-15:00 envelope
- compares ungated vs the two historically-used regime gates
- sweeps rr/tp1 only on the best ungated and best bear-high-vol-gated windows

Selection is done on pre-holdout data only. Stitched OOS and opened holdout
metrics are reported only as secondary reads for the finalists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import (  # noqa: E402
    DISCOVERY_START,
    HOLDOUT_START,
    build_config,
    load_timeframe_data,
    result_row,
    save_json,
)
from orb_backtest.analysis.alpha_v1_downside import filter_trades_by_combined_regime  # noqa: E402
from orb_backtest.analysis.regime_research import build_extended_regime_calendar  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from run_nq_ny_htf_lsi_phase_one import reconstruct_combined_oos_trades, trading_dates_between  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_window_exit_local_sweep"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_WINDOW_EXIT_LOCAL_SWEEP.md"

WINDOW_STARTS = ("08:30", "09:00", "09:30", "10:00")
WINDOW_ENDS = ("11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00")
RR_VALUES = (2.5, 2.75, 3.0, 3.25, 3.5)
TP1_VALUES = (0.4, 0.5, 0.6, 0.7)

MIN_DISCOVERY_TRADES = 250
MIN_VALIDATION_TRADES = 80

GATE_SPECS = (
    {"label": "ungated", "exclude_regimes": frozenset()},
    {"label": "skip_bear_high_vol", "exclude_regimes": frozenset({"bear_high_vol"})},
    {"label": "skip_medium_vol", "exclude_regimes": frozenset({"bull_medium_vol", "sideways_medium_vol"})},
)

EXIT_SWEEP_GATES = ("ungated", "skip_bear_high_vol")


def _window_minutes(start: str, end: str) -> int:
    start_ts = pd.Timestamp(f"2000-01-01 {start}")
    end_ts = pd.Timestamp(f"2000-01-01 {end}")
    return int((end_ts - start_ts).total_seconds() // 60)


def _build_anchor_config(*, entry_start: str, entry_end: str, rr: float, tp1_ratio: float, name: str):
    return build_config(
        timeframe="5m",
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_start=entry_start,
        entry_end=entry_end,
        rr=rr,
        tp1_ratio=tp1_ratio,
        min_gap_atr_pct=3.0,
        atr_length=14,
        htf_level_tf_minutes=60,
        htf_n_left=3,
        htf_trade_max_per_session=2,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=2,
        max_fvg_to_inversion_bars=24,
        name=name,
    )


def _apply_gate(trades, regime_calendar: pd.DataFrame, exclude_regimes: frozenset[str]):
    if not exclude_regimes:
        return trades
    return filter_trades_by_combined_regime(
        trades,
        regime_calendar,
        include=set(),
        exclude=set(exclude_regimes),
        include_low_confidence=True,
    )


def _rank_key(row: dict) -> tuple:
    return (
        float(row.get("validation_calmar") or 0.0),
        float(row.get("validation_pf") or 0.0),
        float(row.get("validation_avg_r") or 0.0),
        float(row.get("discovery_pf") or 0.0),
        float(row.get("discovery_avg_r") or 0.0),
        -float(row.get("validation_max_dd_r") or 0.0),
        int(row.get("validation_trades") or 0),
    )


def _meaningful(row: dict) -> bool:
    return (
        int(row.get("discovery_trades") or 0) >= MIN_DISCOVERY_TRADES
        and int(row.get("validation_trades") or 0) >= MIN_VALIDATION_TRADES
    )


def _evaluate_rows(results, regime_calendar: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for config, trades in results:
        session = config.sessions[0]
        for gate in GATE_SPECS:
            gated_trades = _apply_gate(trades, regime_calendar, gate["exclude_regimes"])
            row = result_row(config.name, config, gated_trades, gate_label=gate["label"])
            row["window_label"] = f"{session.entry_start}-{session.entry_end}"
            row["window_minutes"] = _window_minutes(session.entry_start, session.entry_end)
            rows.append(row)
    rows.sort(key=_rank_key, reverse=True)
    return rows


def _pick_best_windows(window_rows: list[dict]) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for gate in EXIT_SWEEP_GATES:
        gate_rows = [row for row in window_rows if row["gate"] == gate and _meaningful(row)]
        if gate_rows:
            gate_rows.sort(key=_rank_key, reverse=True)
            best[gate] = gate_rows[0]
    return best


def _finalist_metrics(
    finalists: list[dict],
    *,
    df_base: pd.DataFrame,
    df_1m: pd.DataFrame,
    df_1s: pd.DataFrame,
    signal_df_1m: pd.DataFrame,
    maps: dict,
    signal_cache: dict,
    regime_calendar: pd.DataFrame,
) -> list[dict]:
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    oos_dates = trading_dates_between(df_base, "2019-01-01", HOLDOUT_START)
    holdout_dates = trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive)

    out = []
    for finalist in finalists:
        config = finalist["config"]
        trades_oos = reconstruct_combined_oos_trades(
            df_base,
            df_1m,
            df_1s,
            signal_df_1m,
            maps,
            signal_cache,
            config,
        )
        trades_holdout = run_backtest(
            df_base,
            config,
            start_date=HOLDOUT_START,
            end_date=holdout_end_exclusive,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )

        trades_oos = _apply_gate(trades_oos, regime_calendar, finalist["exclude_regimes"])
        trades_holdout = _apply_gate(trades_holdout, regime_calendar, finalist["exclude_regimes"])
        oos = compute_metrics(trades_oos)
        holdout = compute_metrics(trades_holdout)

        session = config.sessions[0]
        out.append(
            {
                "label": finalist["label"],
                "gate": finalist["gate"],
                "window_label": f"{session.entry_start}-{session.entry_end}",
                "rr": float(config.rr),
                "tp1_ratio": float(config.tp1_ratio),
                "oos_trades": int(oos["total_trades"]),
                "oos_pf": float(oos["profit_factor"]),
                "oos_avg_r": float(oos["avg_r"]),
                "oos_calmar": float(oos["calmar_ratio"]),
                "oos_total_r": float(oos["total_r"]),
                "holdout_trades": int(holdout["total_trades"]),
                "holdout_pf": float(holdout["profit_factor"]),
                "holdout_avg_r": float(holdout["avg_r"]),
                "holdout_calmar": float(holdout["calmar_ratio"]),
                "holdout_total_r": float(holdout["total_r"]),
                "holdout_end_inclusive": holdout_end_inclusive,
                "oos_dates": len(oos_dates),
                "holdout_dates": len(holdout_dates),
            }
        )
    out.sort(
        key=lambda row: (
            row["oos_calmar"],
            row["oos_pf"],
            row["oos_avg_r"],
            row["holdout_pf"],
            row["holdout_avg_r"],
        ),
        reverse=True,
    )
    return out


def _write_report(
    *,
    baseline_gate_rows: list[dict],
    top_windows: dict[str, list[dict]],
    selected_windows: dict[str, dict],
    top_exit_rows: dict[str, list[dict]],
    finalists: list[dict],
) -> None:
    lines = [
        "# NQ NY HTF-LSI Window + Exit Local Sweep",
        "",
        "- Objective: answer whether the promoted `5m lag24` lead has a better sub-window inside `08:30-15:00`, and whether `rr / tp1` should move when that branch is compared gated vs ungated.",
        "- Scope: structure held fixed to the promoted lead (`long`, `fvg_limit`, `gap3.0`, `htf60`, `n3`, `cap2`, `fvgL20`, `fvgR2`, `lag24`).",
        "- Selection discipline: all ranking uses pre-holdout discovery/validation only. Stitched OOS and opened holdout are reported only as secondary reads for the finalists.",
        "",
        "## Current Window Gate Check",
        "",
        "| Gate | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in baseline_gate_rows:
        lines.append(
            f"| `{row['gate']}` | {row['discovery_trades']} | {row['discovery_pf']:.3f} | "
            f"{row['validation_trades']} | {row['validation_pf']:.3f} | "
            f"{row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Best Windows By Gate",
            "",
        ]
    )
    for gate, rows in top_windows.items():
        lines.extend(
            [
                f"### {gate}",
                "",
                "| Window | Minutes | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in rows[:5]:
            lines.append(
                f"| `{row['window_label']}` | {row['window_minutes']} | {row['discovery_trades']} | "
                f"{row['discovery_pf']:.3f} | {row['validation_trades']} | {row['validation_pf']:.3f} | "
                f"{row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Local Exit Sweep",
            "",
        ]
    )
    for gate, rows in top_exit_rows.items():
        winner = selected_windows[gate]
        lines.extend(
            [
                f"### {gate} on `{winner['window_label']}`",
                "",
                "| RR | TP1 | Disc Trades | Disc PF | Val Trades | Val PF | Val Avg R | Val Calmar |",
                "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in rows[:5]:
            lines.append(
                f"| {row['rr']:.2f} | {row['tp1_ratio']:.2f} | {row['discovery_trades']} | {row['discovery_pf']:.3f} | "
                f"{row['validation_trades']} | {row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | "
                f"{row['validation_calmar']:.3f} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Finalist Secondary Read",
            "",
            "| Label | Gate | Window | RR | TP1 | OOS PF | OOS Avg R | OOS Calmar | Holdout PF | Holdout Avg R | Holdout Calmar |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in finalists:
        lines.append(
            f"| `{row['label']}` | `{row['gate']}` | `{row['window_label']}` | {row['rr']:.2f} | {row['tp1_ratio']:.2f} | "
            f"{row['oos_pf']:.3f} | {row['oos_avg_r']:.3f} | {row['oos_calmar']:.3f} | "
            f"{row['holdout_pf']:.3f} | {row['holdout_avg_r']:.3f} | {row['holdout_calmar']:.3f} |"
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    regime_calendar = build_extended_regime_calendar(df_base)
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)

    window_configs = []
    for entry_start in WINDOW_STARTS:
        for entry_end in WINDOW_ENDS:
            if _window_minutes(entry_start, entry_end) <= 0:
                continue
            name = f"NQ NY HTF_LSI window {entry_start}-{entry_end} rr3.0 tp0.6 lag24"
            window_configs.append(
                _build_anchor_config(
                    entry_start=entry_start,
                    entry_end=entry_end,
                    rr=3.0,
                    tp1_ratio=0.6,
                    name=name,
                )
            )

    window_signal_cache = build_signal_cache(df_base, window_configs, signal_df_1m=signal_df_1m)
    window_results = run_sweep(
        df_base,
        window_configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _prebuilt_maps=maps,
        _prebuilt_signal_cache=window_signal_cache,
    )
    window_rows = _evaluate_rows(window_results, regime_calendar)
    save_json(OUTPUT_DIR / "window_rows.json", window_rows)

    baseline_gate_rows = [
        row
        for row in window_rows
        if row["window_label"] == "08:30-15:00"
    ]
    baseline_gate_rows.sort(key=lambda row: row["gate"])

    top_windows: dict[str, list[dict]] = {}
    for gate in {row["gate"] for row in window_rows}:
        gate_rows = [row for row in window_rows if row["gate"] == gate and _meaningful(row)]
        gate_rows.sort(key=_rank_key, reverse=True)
        top_windows[gate] = gate_rows

    selected_windows = _pick_best_windows(window_rows)
    save_json(OUTPUT_DIR / "selected_windows.json", selected_windows)

    selected_window_specs = {
        (row["entry_start"], row["entry_end"])
        for row in selected_windows.values()
    }

    exit_configs = []
    for entry_start, entry_end in sorted(selected_window_specs):
        for rr in RR_VALUES:
            for tp1_ratio in TP1_VALUES:
                if rr * tp1_ratio < 1.0:
                    continue
                name = f"NQ NY HTF_LSI exit {entry_start}-{entry_end} rr{rr} tp{tp1_ratio} lag24"
                exit_configs.append(
                    _build_anchor_config(
                        entry_start=entry_start,
                        entry_end=entry_end,
                        rr=rr,
                        tp1_ratio=tp1_ratio,
                        name=name,
                    )
                )

    exit_signal_cache = build_signal_cache(df_base, exit_configs, signal_df_1m=signal_df_1m)
    exit_results = run_sweep(
        df_base,
        exit_configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _prebuilt_maps=maps,
        _prebuilt_signal_cache=exit_signal_cache,
    )
    exit_rows_all = _evaluate_rows(exit_results, regime_calendar)
    save_json(OUTPUT_DIR / "exit_rows.json", exit_rows_all)

    top_exit_rows: dict[str, list[dict]] = {}
    chosen_finalists: list[dict] = []
    seen = set()
    for gate, winner in selected_windows.items():
        gate_rows = [
            row
            for row in exit_rows_all
            if row["gate"] == gate
            and row["window_label"] == winner["window_label"]
            and _meaningful(row)
        ]
        gate_rows.sort(key=_rank_key, reverse=True)
        top_exit_rows[gate] = gate_rows
        if gate_rows:
            top = gate_rows[0]
            key = (gate, top["window_label"], top["rr"], top["tp1_ratio"])
            if key not in seen:
                seen.add(key)
                chosen_finalists.append(
                    {
                        "label": f"best_{gate}",
                        "gate": gate,
                        "exclude_regimes": next(spec["exclude_regimes"] for spec in GATE_SPECS if spec["label"] == gate),
                        "config": _build_anchor_config(
                            entry_start=top["entry_start"],
                            entry_end=top["entry_end"],
                            rr=float(top["rr"]),
                            tp1_ratio=float(top["tp1_ratio"]),
                            name=f"NQ NY HTF_LSI finalist {gate} {top['window_label']} rr{top['rr']} tp{top['tp1_ratio']}",
                        ),
                    }
                )

    for gate in EXIT_SWEEP_GATES:
        exclude_regimes = next(spec["exclude_regimes"] for spec in GATE_SPECS if spec["label"] == gate)
        key = (gate, "08:30-15:00", 3.0, 0.6)
        if key in seen:
            continue
        seen.add(key)
        chosen_finalists.append(
            {
                "label": f"baseline_{gate}",
                "gate": gate,
                "exclude_regimes": exclude_regimes,
                "config": _build_anchor_config(
                    entry_start="08:30",
                    entry_end="15:00",
                    rr=3.0,
                    tp1_ratio=0.6,
                    name=f"NQ NY HTF_LSI baseline {gate} 08:30-15:00 rr3.0 tp0.6 lag24",
                ),
            }
        )

    finalist_configs = [row["config"] for row in chosen_finalists]
    finalist_signal_cache = build_signal_cache(df_base, finalist_configs, signal_df_1m=signal_df_1m)
    finalists = _finalist_metrics(
        chosen_finalists,
        df_base=df_base,
        df_1m=df_1m,
        df_1s=df_1s,
        signal_df_1m=signal_df_1m,
        maps=maps,
        signal_cache=finalist_signal_cache,
        regime_calendar=regime_calendar,
    )
    save_json(OUTPUT_DIR / "finalists.json", finalists)

    _write_report(
        baseline_gate_rows=baseline_gate_rows,
        top_windows=top_windows,
        selected_windows=selected_windows,
        top_exit_rows=top_exit_rows,
        finalists=finalists,
    )

    print(
        json.dumps(
            {
                "selected_windows": selected_windows,
                "top_exit_rows": {gate: rows[:3] for gate, rows in top_exit_rows.items()},
                "finalists": finalists,
                "report_path": str(REPORT_PATH),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
