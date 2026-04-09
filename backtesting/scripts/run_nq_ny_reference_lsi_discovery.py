#!/usr/bin/env python3
"""NQ NY reference-level LSI discovery pipeline.

Implements the first-pass workflow for the reference-level LSI branch:
1. Baseline on pre-holdout data only
2. Stage A structural sweep
3. Stage B RR/TP1 sweep on shortlisted structures
4. Fixed-candidate walk-forward ranking on pre-holdout data
5. PSR/DSR on promoted candidates only

The final holdout starts at 2025-01-01 and is never touched by this script.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import REF_LSI_LEVELS, SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.optimize.walkforward import generate_windows
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.validate.deflated_sharpe import compute_dsr, compute_psr, estimate_effective_trials


RESEARCH_START = "2016-01-01"
DISCOVERY_END = "2022-12-31"
VALIDATION_START = "2023-01-01"
VALIDATION_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"

STAGE_A_DIRECTIONS = ["long", "short", "both"]
STAGE_A_ENTRY_ENDS = ["11:00", "12:00", "13:00", "14:00"]
STAGE_A_EDGES = ["near", "far"]
STAGE_A_GAP_LOOKBACK = [3, 6, 9, 12]
STAGE_A_INVERSION_MAX = [6, 12, 18]

STAGE_B_RR = [1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
STAGE_B_TP1 = [0.5, 0.6, 0.7, 0.8]

LEVEL_GROUPS = {
    "all": REF_LSI_LEVELS,
    "previous_day_asia": (
        "previous_day_high",
        "previous_day_low",
        "asia_high",
        "asia_low",
    ),
    "pdh_asia_low": (
        "previous_day_high",
        "asia_low",
    ),
    "previous_day_asia_low": (
        "previous_day_high",
        "previous_day_low",
        "asia_low",
    ),
}


def output_dir_for_run(timeframe: str, level_group: str) -> Path:
    if timeframe == "5m" and level_group == "all":
        return ROOT / "data" / "results" / "nq_ny_reference_lsi_discovery"
    suffix = timeframe if level_group == "all" else f"{timeframe}_{level_group}"
    return ROOT / "data" / "results" / f"nq_ny_reference_lsi_discovery_{suffix}"


def report_path_for_run(timeframe: str, level_group: str) -> Path:
    if timeframe == "5m" and level_group == "all":
        return ROOT / "learnings" / "reports" / "NQ_NY_REFERENCE_LSI_DISCOVERY.md"
    suffix = timeframe.upper() if level_group == "all" else f"{timeframe.upper()}_{level_group.upper()}"
    return ROOT / "learnings" / "reports" / f"NQ_NY_REFERENCE_LSI_DISCOVERY_{suffix}.md"


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    out = df.resample(rule, label="left", closed="left").agg(agg)
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out.astype(
        {
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
        }
    )


def load_timeframe_data(timeframe: str) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    if timeframe == "5m":
        df_base = load_5m_data("NQ_5m.parquet")
        df_1m = load_1m_for_5m("NQ_5m.parquet")
        df_1s = load_1s_for_5m("NQ_5m.parquet")
        return df_base, df_1m, df_1s

    df_raw_1m = load_5m_data("NQ_1m.parquet")
    df_1s = load_5m_data("NQ_1s.parquet")
    if timeframe == "2m":
        return _resample_ohlcv(df_raw_1m, "2min"), df_raw_1m, df_1s
    if timeframe == "3m":
        return _resample_ohlcv(df_raw_1m, "3min"), df_raw_1m, df_1s
    if timeframe == "1m":
        # Passing the same 1m frame as both base and first drill-down layer keeps
        # the existing hierarchical path intact and still allows 1s resolution on
        # ambiguous bars.
        return df_raw_1m, df_raw_1m, df_1s
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def build_session(entry_end: str) -> SessionConfig:
    return SessionConfig(
        name="NY",
        rth_start="08:30",
        entry_start="08:30",
        entry_end=entry_end,
        flat_start="14:00",
        flat_end="14:05",
        min_gap_atr_pct=5.0,
    )


def build_config(
    *,
    timeframe: str = "5m",
    reference_levels: tuple[str, ...] = REF_LSI_LEVELS,
    direction_filter: str = "both",
    entry_end: str = "14:00",
    rr: float = 2.0,
    tp1_ratio: float = 0.5,
    gap_lookback: int = 12,
    inversion_max: int = 18,
    gap_entry_edge: str = "near",
    name: str = "",
) -> StrategyConfig:
    session = build_session(entry_end)
    if not name:
        name = (
            f"NQ NY reference_lsi {timeframe} "
            f"{direction_filter} {entry_end} "
            f"{gap_entry_edge} gap{gap_lookback} inv{inversion_max} "
            f"rr{rr} tp{tp1_ratio}"
        )
    return StrategyConfig(
        instrument=NQ,
        sessions=(session,),
        strategy="reference_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter=direction_filter,
        rr=rr,
        tp1_ratio=tp1_ratio,
        atr_length=10,
        ref_lsi_gap_lookback_bars=gap_lookback,
        ref_lsi_inversion_max_bars=inversion_max,
        ref_lsi_gap_entry_edge=gap_entry_edge,
        ref_lsi_reference_levels=reference_levels,
        name=name,
    )


def slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        t for t in trades
        if (start is None or t.date >= start)
        and (end is None or t.date < end)
    ]


def metric_row(label: str, config: StrategyConfig, trades) -> dict:
    pre = compute_metrics(trades)
    discovery = compute_metrics(slice_trades(trades, RESEARCH_START, f"{int(DISCOVERY_END[:4]) + 1}-01-01"))
    validation = compute_metrics(slice_trades(trades, VALIDATION_START, HOLDOUT_START))
    session = config.sessions[0]
    return {
        "label": label,
        "direction_filter": config.direction_filter,
        "entry_end": session.entry_end,
        "gap_entry_edge": config.ref_lsi_gap_entry_edge,
        "gap_lookback": config.ref_lsi_gap_lookback_bars,
        "inversion_max": config.ref_lsi_inversion_max_bars,
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "pre_trades": int(pre["total_trades"]),
        "pre_pf": round(float(pre["profit_factor"]), 4),
        "pre_avg_r": round(float(pre["avg_r"]), 4),
        "pre_total_r": round(float(pre["total_r"]), 2),
        "pre_max_dd_r": round(float(pre["max_drawdown_r"]), 2),
        "discovery_trades": int(discovery["total_trades"]),
        "discovery_pf": round(float(discovery["profit_factor"]), 4),
        "discovery_avg_r": round(float(discovery["avg_r"]), 4),
        "validation_trades": int(validation["total_trades"]),
        "validation_pf": round(float(validation["profit_factor"]), 4),
        "validation_avg_r": round(float(validation["avg_r"]), 4),
        "validation_total_r": round(float(validation["total_r"]), 2),
        "validation_max_dd_r": round(float(validation["max_drawdown_r"]), 2),
    }


def baseline_alive(row: dict) -> bool:
    return (
        row["pre_pf"] >= 1.05
        and row["pre_avg_r"] > 0.0
        and row["pre_trades"] >= 150
        and row["validation_pf"] >= 1.0
    )


def stage_a_survivor(row: dict) -> bool:
    return (
        row["pre_pf"] > 1.0
        and row["validation_pf"] > 1.0
        and row["pre_trades"] >= 100
    )


def sort_key(row: dict) -> tuple:
    return (
        row["validation_avg_r"],
        row["validation_pf"],
        row["pre_avg_r"],
        row["pre_total_r"],
    )


def plateau_score(candidate_row: dict, stage_b_rows: list[dict]) -> float:
    neighbors = [
        row for row in stage_b_rows
        if row["direction_filter"] == candidate_row["direction_filter"]
        and row["entry_end"] == candidate_row["entry_end"]
        and row["gap_entry_edge"] == candidate_row["gap_entry_edge"]
        and row["gap_lookback"] == candidate_row["gap_lookback"]
        and row["inversion_max"] == candidate_row["inversion_max"]
        and abs(row["rr"] - candidate_row["rr"]) <= 0.25 + 1e-9
        and abs(row["tp1_ratio"] - candidate_row["tp1_ratio"]) <= 0.10 + 1e-9
    ]
    if not neighbors:
        return 0.0
    return round(float(np.mean([row["validation_avg_r"] for row in neighbors])), 4)


def run_fixed_walkforward(df_5m, df_1m, df_1s, config: StrategyConfig, n_workers: int = 1) -> dict:
    del n_workers  # reserved for future use
    windows = generate_windows(RESEARCH_START, HOLDOUT_START, is_months=36, oos_months=12, step_months=12)
    combined_oos = []
    fold_rows = []
    for window in windows:
        trades = simulator.run_backtest(
            df_5m,
            config,
            start_date=window.oos_start,
            end_date=window.oos_end,
            df_1m=df_1m,
            df_1s=df_1s,
        )
        oos = slice_trades(trades, window.oos_start, window.oos_end)
        metrics = compute_metrics(oos)
        combined_oos.extend(oos)
        fold_rows.append(
            {
                "oos_start": window.oos_start,
                "oos_end": window.oos_end,
                "trades": int(metrics["total_trades"]),
                "avg_r": round(float(metrics["avg_r"]), 4),
                "pf": round(float(metrics["profit_factor"]), 4),
                "total_r": round(float(metrics["total_r"]), 2),
                "max_dd_r": round(float(metrics["max_drawdown_r"]), 2),
            }
        )
    combined = compute_metrics(combined_oos)
    return {
        "folds": fold_rows,
        "combined": {
            "trades": int(combined["total_trades"]),
            "avg_r": round(float(combined["avg_r"]), 4),
            "pf": round(float(combined["profit_factor"]), 4),
            "total_r": round(float(combined["total_r"]), 2),
            "max_dd_r": round(float(combined["max_drawdown_r"]), 2),
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def write_markdown_report(
    timeframe: str,
    level_group: str,
    report_path: Path,
    baseline_row: dict,
    alive: bool,
    stage_a_rows: list[dict],
    stage_b_rows: list[dict],
    promoted: list[dict],
) -> None:
    lines = [
        f"# NQ NY Reference LSI Discovery ({timeframe})",
        "",
        f"- Base signal timeframe: `{timeframe}`",
        f"- Reference level group: `{level_group}`",
        f"- Holdout frozen at `{HOLDOUT_START}` and not used.",
        f"- Discovery `{RESEARCH_START}` to `{DISCOVERY_END}`.",
        f"- Validation `{VALIDATION_START}` to `{VALIDATION_END}`.",
        "",
        "## Baseline",
        "",
        f"- pre-holdout trades: `{baseline_row['pre_trades']}`",
        f"- pre-holdout PF / avgR: `{baseline_row['pre_pf']}` / `{baseline_row['pre_avg_r']}`",
        f"- validation trades: `{baseline_row['validation_trades']}`",
        f"- validation PF / avgR: `{baseline_row['validation_pf']}` / `{baseline_row['validation_avg_r']}`",
        f"- structurally alive: `{'YES' if alive else 'NO'}`",
        "",
    ]

    if stage_a_rows:
        lines.extend(["## Stage A Top 10", ""])
        for row in stage_a_rows[:10]:
            lines.append(
                f"- `{row['label']}`: val avgR `{row['validation_avg_r']}`, "
                f"val PF `{row['validation_pf']}`, pre trades `{row['pre_trades']}`"
            )
        lines.append("")

    if stage_b_rows:
        lines.extend(["## Stage B Top 10", ""])
        for row in stage_b_rows[:10]:
            lines.append(
                f"- `{row['label']}`: val avgR `{row['validation_avg_r']}`, "
                f"val PF `{row['validation_pf']}`, rr `{row['rr']}`, tp1 `{row['tp1_ratio']}`"
            )
        lines.append("")

    if promoted:
        lines.extend(["## Promoted", ""])
        for row in promoted:
            lines.append(
                f"- `{row['label']}`: WF avgR `{row['walkforward']['combined']['avg_r']}`, "
                f"WF PF `{row['walkforward']['combined']['pf']}`, plateau `{row['plateau_score']}`, "
                f"PSR `{row['psr']['psr']}`, DSR `{row['dsr']['dsr']}`"
            )
        lines.append("")

    report_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframe", choices=("5m", "3m", "2m", "1m"), default="5m")
    parser.add_argument("--reference-level-group", choices=tuple(LEVEL_GROUPS), default="all")
    parser.add_argument("--baseline-only", action="store_true", help="Run only the baseline branch.")
    parser.add_argument("--n-workers", type=int, default=8, help="Parallel workers for sweeps.")
    args = parser.parse_args()

    timeframe = args.timeframe
    level_group = args.reference_level_group
    reference_levels = LEVEL_GROUPS[level_group]
    output_dir = output_dir_for_run(timeframe, level_group)
    report_path = report_path_for_run(timeframe, level_group)

    t0 = time.time()
    print(
        f"Loading NQ data for {timeframe} reference-LSI discovery ({level_group})...",
        flush=True,
    )
    df_base, df_1m, df_1s = load_timeframe_data(timeframe)
    print(f"  base rows ({timeframe}): {len(df_base):,}", flush=True)
    print(f"  1m rows: {len(df_1m):,}" if df_1m is not None else "  1m rows: not available", flush=True)
    print(f"  1s rows: {len(df_1s):,}" if df_1s is not None else "  1s rows: not available", flush=True)

    baseline_config = build_config(
        timeframe=timeframe,
        reference_levels=reference_levels,
        direction_filter="both",
        entry_end="14:00",
        rr=2.0,
        tp1_ratio=0.5,
        gap_lookback=12,
        inversion_max=18,
        gap_entry_edge="near",
        name=f"NQ NY reference_lsi {timeframe} {level_group} baseline",
    )
    print("Running baseline...", flush=True)
    baseline_trades = simulator.run_backtest(
        df_base,
        baseline_config,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    baseline_row = metric_row("baseline", baseline_config, baseline_trades)
    alive = baseline_alive(baseline_row)

    payload: dict[str, object] = {
        "info": {
            "timeframe": timeframe,
            "reference_level_group": level_group,
            "reference_levels": list(reference_levels),
            "holdout_start": HOLDOUT_START,
            "discovery_end": DISCOVERY_END,
            "validation_start": VALIDATION_START,
            "validation_end": VALIDATION_END,
            "base_rows": len(df_base),
            "drilldown_1m_rows": 0 if df_1m is None else len(df_1m),
            "drilldown_1s_rows": 0 if df_1s is None else len(df_1s),
        },
        "baseline": baseline_row,
        "baseline_alive": alive,
    }

    if args.baseline_only:
        write_json(output_dir / "baseline_only.json", payload)
        write_markdown_report(timeframe, level_group, report_path, baseline_row, alive, [], [], [])
        print(f"Baseline complete in {time.time() - t0:.1f}s", flush=True)
        return

    if not alive:
        print("Baseline failed structural-alive gate. Writing no-go memo and stopping.", flush=True)
        write_json(output_dir / "baseline_no_go.json", payload)
        write_markdown_report(timeframe, level_group, report_path, baseline_row, alive, [], [], [])
        return

    stage_a_configs: list[StrategyConfig] = []
    for direction in STAGE_A_DIRECTIONS:
        for entry_end in STAGE_A_ENTRY_ENDS:
            for edge in STAGE_A_EDGES:
                for gap_lookback in STAGE_A_GAP_LOOKBACK:
                    for inversion_max in STAGE_A_INVERSION_MAX:
                        label = (
                            f"NQ NY reference_lsi {timeframe} {level_group} {direction} {entry_end} "
                            f"{edge} gap{gap_lookback} inv{inversion_max} rr2 tp0.5"
                        )
                        stage_a_configs.append(
                            build_config(
                                timeframe=timeframe,
                                reference_levels=reference_levels,
                                direction_filter=direction,
                                entry_end=entry_end,
                                rr=2.0,
                                tp1_ratio=0.5,
                                gap_lookback=gap_lookback,
                                inversion_max=inversion_max,
                                gap_entry_edge=edge,
                                name=label,
                            )
                        )

    print(f"Running Stage A structural sweep ({len(stage_a_configs)} configs)...", flush=True)
    stage_a_results = run_sweep(
        df_base,
        stage_a_configs,
        n_workers=args.n_workers,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    stage_a_rows = [metric_row(cfg.name, cfg, trades) for cfg, trades in stage_a_results]
    stage_a_rows.sort(key=sort_key, reverse=True)
    stage_a_survivors = [row for row in stage_a_rows if stage_a_survivor(row)][:8]
    payload["stage_a"] = {
        "top_rows": stage_a_rows[:25],
        "survivors": stage_a_survivors,
    }

    stage_b_configs: list[StrategyConfig] = []
    for survivor in stage_a_survivors:
        for rr in STAGE_B_RR:
            for tp1 in STAGE_B_TP1:
                if rr * tp1 < 1.0:
                    continue
                label = (
                    f"NQ NY reference_lsi {timeframe} {level_group} {survivor['direction_filter']} {survivor['entry_end']} "
                    f"{survivor['gap_entry_edge']} gap{survivor['gap_lookback']} "
                    f"inv{survivor['inversion_max']} rr{rr} tp{tp1}"
                )
                stage_b_configs.append(
                    build_config(
                        timeframe=timeframe,
                        reference_levels=reference_levels,
                        direction_filter=survivor["direction_filter"],
                        entry_end=survivor["entry_end"],
                        rr=rr,
                        tp1_ratio=tp1,
                        gap_lookback=survivor["gap_lookback"],
                        inversion_max=survivor["inversion_max"],
                        gap_entry_edge=survivor["gap_entry_edge"],
                        name=label,
                    )
                )

    print(f"Running Stage B reward sweep ({len(stage_b_configs)} configs)...", flush=True)
    stage_b_results = run_sweep(
        df_base,
        stage_b_configs,
        n_workers=args.n_workers,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    stage_b_rows = [metric_row(cfg.name, cfg, trades) for cfg, trades in stage_b_results]
    stage_b_rows.sort(key=sort_key, reverse=True)
    payload["stage_b"] = {"top_rows": stage_b_rows[:40]}

    raw_trial_results = list(stage_a_results) + list(stage_b_results)
    raw_trial_count = len(raw_trial_results)
    trade_date_sets = [
        {t.date for t in trades if t.exit_type != EXIT_NO_FILL}
        for _, trades in raw_trial_results
    ]
    effective_trials = estimate_effective_trials(trade_date_sets)

    promoted_rows = []
    stage_b_lookup = {cfg.name: (cfg, trades) for cfg, trades in stage_b_results}
    for row in stage_b_rows[:6]:
        cfg, trades = stage_b_lookup[row["label"]]
        wf = run_fixed_walkforward(df_base, df_1m, df_1s, cfg)
        pre_holdout_trades = slice_trades(trades, RESEARCH_START, HOLDOUT_START)
        r_multiples = np.array(
            [t.r_multiple for t in pre_holdout_trades if t.exit_type != EXIT_NO_FILL],
            dtype=float,
        )
        psr = compute_psr(r_multiples)
        dsr = compute_dsr(
            r_multiples,
            n_trials_raw=raw_trial_count,
            n_trials_effective=effective_trials,
        )
        promoted_rows.append(
            {
                **row,
                "plateau_score": plateau_score(row, stage_b_rows),
                "walkforward": wf,
                "psr": dataclasses.asdict(psr),
                "dsr": dataclasses.asdict(dsr),
            }
        )

    promoted_rows.sort(
        key=lambda row: (
            row["walkforward"]["combined"]["avg_r"],
            row["walkforward"]["combined"]["pf"],
            row["plateau_score"],
            row["validation_avg_r"],
        ),
        reverse=True,
    )
    promoted_rows = promoted_rows[:3]

    payload["promotion"] = {
        "raw_trials": raw_trial_count,
        "effective_trials": effective_trials,
        "promoted": promoted_rows,
    }

    write_json(output_dir / "discovery_results.json", payload)
    write_markdown_report(timeframe, level_group, report_path, baseline_row, alive, stage_a_rows, stage_b_rows, promoted_rows)
    print(f"Discovery complete in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
