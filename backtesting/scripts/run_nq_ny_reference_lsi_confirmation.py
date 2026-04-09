#!/usr/bin/env python3
"""Final pre-holdout confirmation pass for NQ NY reference_lsi.

This script is intentionally tiny. It only rechecks the strongest follow-up
neighborhood before any final decision about touching the frozen 2025+ holdout.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.optimize.walkforward import generate_windows
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.validate.deflated_sharpe import compute_dsr, compute_psr, estimate_effective_trials


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_reference_lsi_confirmation"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_REFERENCE_LSI_CONFIRMATION.md"
SPEC_PATH = ROOT / "learnings" / "reports" / "NQ_NY_REFERENCE_LSI_CONFIRMATION_SPEC.md"

RESEARCH_START = "2016-01-01"
DISCOVERY_END = "2022-12-31"
VALIDATION_START = "2023-01-01"
VALIDATION_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"

STRUCTURES = [
    {"gap_lookback": 6, "inversion_max": 15},
    {"gap_lookback": 6, "inversion_max": 18},
    {"gap_lookback": 8, "inversion_max": 18},
    {"gap_lookback": 12, "inversion_max": 12},
]
RR_VALUES = [3.0, 3.25]
TP1_VALUES = [0.7, 0.8]


def build_session() -> SessionConfig:
    return SessionConfig(
        name="NY",
        rth_start="08:30",
        entry_start="08:30",
        entry_end="11:00",
        flat_start="14:00",
        flat_end="14:05",
        min_gap_atr_pct=5.0,
    )


def build_config(
    *,
    gap_lookback: int,
    inversion_max: int,
    rr: float,
    tp1_ratio: float,
    name: str = "",
) -> StrategyConfig:
    if not name:
        name = (
            "NQ NY reference_lsi both 11:00 near "
            f"gap{gap_lookback} inv{inversion_max} rr{rr} tp{tp1_ratio}"
        )
    return StrategyConfig(
        instrument=NQ,
        sessions=(build_session(),),
        strategy="reference_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter="both",
        rr=rr,
        tp1_ratio=tp1_ratio,
        atr_length=10,
        ref_lsi_gap_lookback_bars=gap_lookback,
        ref_lsi_inversion_max_bars=inversion_max,
        ref_lsi_gap_entry_edge="near",
        name=name,
    )


def slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        t for t in trades
        if (start is None or t.date >= start)
        and (end is None or t.date < end)
    ]


def metric_row(config: StrategyConfig, trades) -> dict:
    pre = compute_metrics(trades)
    discovery = compute_metrics(slice_trades(trades, RESEARCH_START, VALIDATION_START))
    validation = compute_metrics(slice_trades(trades, VALIDATION_START, HOLDOUT_START))
    return {
        "label": config.name,
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


def ranking_key(row: dict) -> tuple:
    return (
        row["validation_avg_r"],
        row["validation_pf"],
        row["pre_avg_r"],
        row["pre_total_r"],
    )


def plateau_score(candidate_row: dict, rows: list[dict]) -> float:
    neighbors = [
        row for row in rows
        if abs(row["gap_lookback"] - candidate_row["gap_lookback"]) <= 2
        and abs(row["inversion_max"] - candidate_row["inversion_max"]) <= 3
        and abs(row["rr"] - candidate_row["rr"]) <= 0.25 + 1e-9
        and abs(row["tp1_ratio"] - candidate_row["tp1_ratio"]) <= 0.10 + 1e-9
    ]
    if not neighbors:
        return 0.0
    return round(float(np.mean([row["validation_avg_r"] for row in neighbors])), 4)


def run_fixed_walkforward(df_5m, df_1m, df_1s, config: StrategyConfig) -> dict:
    windows = generate_windows(RESEARCH_START, HOLDOUT_START, is_months=36, oos_months=12, step_months=12)
    combined_oos = []
    folds = []
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
        folds.append(
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
        "folds": folds,
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


def decision_text(promoted: list[dict]) -> list[str]:
    if not promoted:
        return [
            "- No config survived the confirmation pass strongly enough to justify holdout.",
            "- Stop at discovery and keep the 2025+ holdout closed.",
        ]
    best = promoted[0]
    psr = best["psr"]["psr"]
    dsr = best["dsr"]["dsr"]
    if psr >= 0.95 and dsr >= 0.50:
        return [
            f"- Best config `{best['label']}` cleared a strong PSR/DSR gate (`PSR {psr:.4f}`, `DSR {dsr:.4f}`).",
            "- This branch is ready for a frozen holdout read.",
        ]
    if psr >= 0.85 and dsr >= 0.50:
        return [
            f"- Best config `{best['label']}` cleared a moderate PSR/DSR gate (`PSR {psr:.4f}`, `DSR {dsr:.4f}`).",
            "- Holdout is defensible, but it should be framed as a cautious read rather than a full promotion.",
        ]
    return [
        f"- Best config `{best['label']}` is still below the repo's moderate PSR bar (`PSR {psr:.4f}`, `DSR {dsr:.4f}`).",
        "- Keep the 2025+ holdout closed and treat this branch as discovery-only for now.",
    ]


def write_spec() -> None:
    lines = [
        "# NQ NY Reference LSI Confirmation Spec",
        "",
        "- Holdout `2025-01-01+` remains frozen.",
        "- This pass only retests the strongest post-follow-up neighborhood before any holdout decision.",
        "",
        "## Fixed Choices",
        "",
        "- `direction_filter = both`",
        "- `entry_end = 11:00`",
        "- `ref_lsi_gap_entry_edge = near`",
        "- `atr_length = 10`",
        "- `min_gap_atr_pct = 5.0`",
        "",
        "## Structures",
        "",
    ]
    for struct in STRUCTURES:
        lines.append(f"- `gap{struct['gap_lookback']} / inv{struct['inversion_max']}`")
    lines.extend(
        [
            "",
            "## Reward Choices",
            "",
            f"- `rr`: {RR_VALUES}",
            f"- `tp1_ratio`: {TP1_VALUES}",
            "",
            f"- Total raw trials: `{len(STRUCTURES) * len(RR_VALUES) * len(TP1_VALUES)}`",
        ]
    )
    SPEC_PATH.write_text("\n".join(lines))


def write_report(payload: dict) -> None:
    lines = [
        "# NQ NY Reference LSI Confirmation",
        "",
        f"- Holdout frozen at `{HOLDOUT_START}` and not used.",
        f"- Discovery `{RESEARCH_START}` to `{DISCOVERY_END}`.",
        f"- Validation `{VALIDATION_START}` to `{VALIDATION_END}`.",
        f"- Raw trials `{payload['info']['raw_trials']}`, effective trials `{payload['info']['effective_trials']}`.",
        "",
        "## Top Rows",
        "",
    ]
    for row in payload["top_rows"]:
        lines.append(
            f"- `{row['label']}`: val avgR `{row['validation_avg_r']}`, "
            f"val PF `{row['validation_pf']}`, pre trades `{row['pre_trades']}`"
        )
    lines.extend(["", "## Promoted", ""])
    for row in payload["promoted"]:
        lines.append(
            f"- `{row['label']}`: WF avgR `{row['walkforward']['combined']['avg_r']}`, "
            f"WF PF `{row['walkforward']['combined']['pf']}`, plateau `{row['plateau_score']}`, "
            f"PSR `{row['psr']['psr']}`, DSR `{row['dsr']['dsr']}`"
        )
    lines.extend(["", "## Decision", ""])
    lines.extend(payload["decision"])
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    t0 = time.time()
    write_spec()

    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")

    configs = []
    for struct in STRUCTURES:
        for rr in RR_VALUES:
            for tp1 in TP1_VALUES:
                if rr * tp1 < 1.0:
                    continue
                configs.append(
                    build_config(
                        gap_lookback=struct["gap_lookback"],
                        inversion_max=struct["inversion_max"],
                        rr=rr,
                        tp1_ratio=tp1,
                    )
                )

    print(f"Running confirmation sweep ({len(configs)} configs)...", flush=True)
    sweep_results = run_sweep(
        df_5m,
        configs,
        n_workers=8,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        df_1s=df_1s,
    )

    rows = [metric_row(cfg, trades) for cfg, trades in sweep_results]
    rows.sort(key=ranking_key, reverse=True)

    raw_trial_count = len(sweep_results)
    trade_date_sets = [
        {t.date for t in trades if t.exit_type != EXIT_NO_FILL}
        for _, trades in sweep_results
    ]
    effective_trials = estimate_effective_trials(trade_date_sets)

    sweep_lookup = {cfg.name: (cfg, trades) for cfg, trades in sweep_results}
    promoted = []
    for row in rows:
        cfg, trades = sweep_lookup[row["label"]]
        wf = run_fixed_walkforward(df_5m, df_1m, df_1s, cfg)
        pre_holdout = slice_trades(trades, RESEARCH_START, HOLDOUT_START)
        r_multiples = np.array(
            [t.r_multiple for t in pre_holdout if t.exit_type != EXIT_NO_FILL],
            dtype=float,
        )
        psr = compute_psr(r_multiples)
        dsr = compute_dsr(
            r_multiples,
            n_trials_raw=raw_trial_count,
            n_trials_effective=effective_trials,
        )
        promoted.append(
            {
                **row,
                "plateau_score": plateau_score(row, rows),
                "walkforward": wf,
                "psr": dataclasses.asdict(psr),
                "dsr": dataclasses.asdict(dsr),
            }
        )

    promoted.sort(
        key=lambda row: (
            row["walkforward"]["combined"]["avg_r"],
            row["walkforward"]["combined"]["pf"],
            row["plateau_score"],
            row["validation_avg_r"],
        ),
        reverse=True,
    )
    promoted = promoted[:3]
    decision = decision_text(promoted)

    payload = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "raw_trials": raw_trial_count,
            "effective_trials": effective_trials,
        },
        "top_rows": rows,
        "promoted": promoted,
        "decision": decision,
    }
    write_json(OUTPUT_DIR / "confirmation_results.json", payload)
    write_report(payload)
    print(f"Confirmation complete in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
