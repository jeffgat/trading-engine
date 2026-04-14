#!/usr/bin/env python3
"""Compare alternative LSI stop/target constructions on the current NQ leads.

Scope:
- regular NQ NY LSI final branch (`rr=2.0`, `tp1=0.5`, Thu excl, medium-vol gate)
- current NQ NY HTF-LSI operating lead (`5m lag24`, `08:30-13:30`, `rr=3.5`, `tp1=0.4`,
  skip `bear_high_vol`)

Both anchors are run across the same stop/target menu:
- `absolute`
- `gap_1x`, `gap_2x`, `gap_3x`, `gap_4x`
- `struct_50pct`, `struct_75pct`

Target modes:
- `risk`           -> TP1/TP2 from actual stop distance
- `structural`     -> TP1/TP2 from full structural distance, with TP1 >= 1R and TP2 >= 1.5R
- `left_structure` -> TP1/TP2 from unswept swing pivots to the left of the setup

This is an evidence packet, not a promotion step. We rank on pre-holdout and
report holdout second to see whether any improvement is honest.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config  # noqa: E402
from orb_backtest.analysis.alpha_v1_downside import filter_trades_by_combined_regime  # noqa: E402
from orb_backtest.analysis.regime_research import build_extended_regime_calendar  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_lsi_structural_stop_target_sweep"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_LSI_STRUCTURAL_STOP_TARGET_SWEEP.md"

HOLDOUT_START = "2025-04-01"

STOP_MODES = (
    "absolute",
    "gap_1x",
    "gap_2x",
    "gap_3x",
    "gap_4x",
    "struct_50pct",
    "struct_75pct",
)
TARGET_MODES = ("risk", "structural", "left_structure")

REGULAR_LSI_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

REGULAR_LSI_BASE = StrategyConfig(
    sessions=(REGULAR_LSI_SESSION,),
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
    lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
    excluded_days=(3,),
    name="NQ NY LSI Final",
)

ANCHOR_SPECS = (
    {
        "anchor_id": "nq_ny_lsi_final",
        "label": "NQ NY LSI Final",
        "config": REGULAR_LSI_BASE,
        "exclude_regimes": frozenset({"bull_medium_vol", "sideways_medium_vol"}),
        "gate_label": "skip_medium_vol",
        "notes": "Long-only regular LSI final branch with Thu exclusion and medium-vol avoidance.",
    },
    {
        "anchor_id": "nq_ny_htf_lsi_current",
        "label": "NQ NY HTF-LSI Current",
        "config": build_current_nq_ny_htf_lsi_lag24_config(
            name="NQ NY HTF_LSI Current",
        ),
        "exclude_regimes": frozenset({"bear_high_vol"}),
        "gate_label": "skip_bear_high_vol",
        "notes": "Current operating HTF-LSI lead (`5m lag24`, `08:30-13:30`, `rr=3.5`, `tp1=0.4`).",
    },
)


def _slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        trade
        for trade in trades
        if (start is None or trade.date >= start) and (end is None or trade.date < end)
    ]


def _apply_gate(trades, regime_calendar, exclude_regimes: frozenset[str]):
    if not exclude_regimes:
        return trades
    return filter_trades_by_combined_regime(
        trades,
        regime_calendar,
        include=set(),
        exclude=set(exclude_regimes),
        include_low_confidence=True,
    )


def _trade_shape_stats(trades):
    filled = [trade for trade in trades if trade.exit_type != 0]
    if not filled:
        return {
            "median_stop_ticks": 0.0,
            "median_tp1_r": 0.0,
            "median_tp2_r": 0.0,
        }
    return {
        "median_stop_ticks": median(trade.risk_points / NQ.min_tick for trade in filled),
        "median_tp1_r": median(
            abs(trade.tp1_price - trade.entry_price) / trade.risk_points
            for trade in filled
            if trade.risk_points > 0
        ),
        "median_tp2_r": median(
            abs(trade.tp2_price - trade.entry_price) / trade.risk_points
            for trade in filled
            if trade.risk_points > 0
        ),
    }


def _period_summary(trades) -> dict:
    metrics = compute_metrics(trades)
    shape = _trade_shape_stats(trades)
    return {
        "trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "profit_factor": float(metrics["profit_factor"]),
        "avg_r": float(metrics["avg_r"]),
        "total_r": float(metrics["total_r"]),
        "calmar": float(metrics["calmar_ratio"]),
        "max_dd_r": float(metrics["max_drawdown_r"]),
        **shape,
    }


def _row(anchor_spec: dict, config: StrategyConfig, trades) -> dict:
    pre_holdout = _slice_trades(trades, end=HOLDOUT_START)
    holdout = _slice_trades(trades, start=HOLDOUT_START)
    return {
        "anchor_id": anchor_spec["anchor_id"],
        "anchor_label": anchor_spec["label"],
        "gate_label": anchor_spec["gate_label"],
        "stop_mode": config.lsi_stop_mode,
        "target_mode": config.lsi_target_mode,
        "entry_mode": config.lsi_entry_mode,
        "rr": float(config.rr),
        "tp1_ratio": float(config.tp1_ratio),
        "config_name": config.name,
        "pre_holdout": _period_summary(pre_holdout),
        "holdout": _period_summary(holdout),
    }


def _rank_key(row: dict) -> tuple:
    pre = row["pre_holdout"]
    holdout = row["holdout"]
    return (
        pre["calmar"],
        pre["profit_factor"],
        pre["avg_r"],
        holdout["profit_factor"],
        holdout["avg_r"],
        -pre["max_dd_r"],
        pre["trades"],
    )


def _format_pct(value: float) -> str:
    return f"{value:.1%}"


def _write_report(rows: list[dict], payload: dict) -> None:
    lines = [
        "# NQ LSI Structural Stop / Target Sweep",
        "",
        "- Date: `2026-04-13`",
        "- Objective: test tighter LSI stops plus two structural target constructions: structural-risk-basis targets and left-side unswept-pivot targets.",
        "- Scope: regular NQ NY LSI final branch plus the current NQ NY HTF-LSI operating lead.",
        "- Holdout split: pre-holdout `< 2025-04-01`, holdout `>= 2025-04-01`.",
        "",
        "## Stop / Target Menu",
        "",
        "- Stops: `absolute`, `gap_1x`, `gap_2x`, `gap_3x`, `gap_4x`, `struct_50pct`, `struct_75pct`.",
        "- Targets:",
        "  - `risk`: TP1/TP2 from actual stop distance.",
        "  - `structural`: TP1/TP2 from full structural distance, with `TP1 >= 1R` and `TP2 >= 1.5R` on actual risk.",
        "  - `left_structure`: TP1/TP2 from unswept swing pivots to the left of the setup; longs target left-side highs, shorts target left-side lows, while still enforcing the minimum 1R / 1.5R floors.",
        "",
    ]

    for anchor in ANCHOR_SPECS:
        anchor_rows = [row for row in rows if row["anchor_id"] == anchor["anchor_id"]]
        anchor_rows.sort(key=_rank_key, reverse=True)
        lines.extend(
            [
                f"## {anchor['label']}",
                "",
                f"- Gate: `{anchor['gate_label']}`",
                f"- Notes: {anchor['notes']}",
                "",
                "| Rank | Stop | Target | Pre PF | Pre AvgR | Pre Calmar | Pre DD | Hold PF | Hold AvgR | Hold Calmar | Med Stop (ticks) | Med TP1 R | Med TP2 R |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for idx, row in enumerate(anchor_rows[:8], start=1):
            pre = row["pre_holdout"]
            hold = row["holdout"]
            lines.append(
                "| "
                f"{idx} | `{row['stop_mode']}` | `{row['target_mode']}` | "
                f"{pre['profit_factor']:.3f} | {pre['avg_r']:.3f} | {pre['calmar']:.3f} | {pre['max_dd_r']:.2f} | "
                f"{hold['profit_factor']:.3f} | {hold['avg_r']:.3f} | {hold['calmar']:.3f} | "
                f"{pre['median_stop_ticks']:.1f} | {pre['median_tp1_r']:.2f} | {pre['median_tp2_r']:.2f} |"
            )
        lines.append("")

        baseline = next(row for row in anchor_rows if row["stop_mode"] == "absolute" and row["target_mode"] == "risk")
        best = anchor_rows[0]
        best_left = next(row for row in anchor_rows if row["target_mode"] == "left_structure")
        lines.extend(
            [
                "### Quick Read",
                "",
                f"- Baseline: `{baseline['stop_mode']}` + `{baseline['target_mode']}` "
                f"-> pre PF `{baseline['pre_holdout']['profit_factor']:.3f}`, "
                f"pre avg R `{baseline['pre_holdout']['avg_r']:.3f}`, "
                f"holdout PF `{baseline['holdout']['profit_factor']:.3f}`.",
                f"- Best pre-holdout row: `{best['stop_mode']}` + `{best['target_mode']}` "
                f"-> pre PF `{best['pre_holdout']['profit_factor']:.3f}`, "
                f"pre avg R `{best['pre_holdout']['avg_r']:.3f}`, "
                f"holdout PF `{best['holdout']['profit_factor']:.3f}`.",
                f"- Best `left_structure` row: `{best_left['stop_mode']}` + `left_structure` "
                f"-> pre PF `{best_left['pre_holdout']['profit_factor']:.3f}`, "
                f"pre avg R `{best_left['pre_holdout']['avg_r']:.3f}`, "
                f"holdout PF `{best_left['holdout']['profit_factor']:.3f}`.",
                "",
            ]
        )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}", flush=True)

    regime_calendar = build_extended_regime_calendar(df_5m)

    configs: list[StrategyConfig] = []
    config_to_anchor: dict[str, dict] = {}
    for anchor in ANCHOR_SPECS:
        for stop_mode in STOP_MODES:
            for target_mode in TARGET_MODES:
                cfg = replace(
                    anchor["config"],
                    lsi_stop_mode=stop_mode,
                    lsi_target_mode=target_mode,
                    name=f"{anchor['label']} {stop_mode} {target_mode}",
                )
                configs.append(cfg)
                config_to_anchor[cfg.name] = anchor

    print(f"Building shared maps and signal cache for {len(configs)} configs...", flush=True)
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_5m, configs, signal_df_1m=df_1m)

    def progress(done: int, total: int):
        print(f"  [{done:>2}/{total}] complete", flush=True)

    print("Running sweep...", flush=True)
    results = run_sweep(
        df_5m,
        configs,
        n_workers=min(8, len(configs)),
        progress_fn=progress,
        df_1m=df_1m,
        signal_df_1m=df_1m,
        df_1s=df_1s,
        _prebuilt_maps=maps,
        _prebuilt_signal_cache=signal_cache,
    )

    rows: list[dict] = []
    for config, trades in results:
        anchor_spec = config_to_anchor[config.name]
        gated_trades = _apply_gate(trades, regime_calendar, anchor_spec["exclude_regimes"])
        rows.append(_row(anchor_spec, config, gated_trades))

    rows.sort(key=_rank_key, reverse=True)
    payload = {
        "generated_at": "2026-04-13",
        "holdout_start": HOLDOUT_START,
        "stop_modes": list(STOP_MODES),
        "target_modes": list(TARGET_MODES),
        "anchors": [
            {
                "anchor_id": anchor["anchor_id"],
                "label": anchor["label"],
                "gate_label": anchor["gate_label"],
                "notes": anchor["notes"],
            }
            for anchor in ANCHOR_SPECS
        ],
        "rows": rows,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(rows, payload)

    print("\nTop rows by anchor:", flush=True)
    for anchor in ANCHOR_SPECS:
        anchor_rows = [row for row in rows if row["anchor_id"] == anchor["anchor_id"]]
        anchor_rows.sort(key=_rank_key, reverse=True)
        best = anchor_rows[0]
        baseline = next(row for row in anchor_rows if row["stop_mode"] == "absolute" and row["target_mode"] == "risk")
        print(f"  {anchor['label']}", flush=True)
        print(
            "    baseline "
            f"{baseline['stop_mode']}/{baseline['target_mode']} -> "
            f"pre PF {baseline['pre_holdout']['profit_factor']:.3f}, "
            f"avg R {baseline['pre_holdout']['avg_r']:.3f}, "
            f"hold PF {baseline['holdout']['profit_factor']:.3f}",
            flush=True,
        )
        print(
            "    best     "
            f"{best['stop_mode']}/{best['target_mode']} -> "
            f"pre PF {best['pre_holdout']['profit_factor']:.3f}, "
            f"avg R {best['pre_holdout']['avg_r']:.3f}, "
            f"hold PF {best['holdout']['profit_factor']:.3f}",
            flush=True,
        )

    print(f"\nSaved summary to {OUTPUT_DIR / 'summary.json'}", flush=True)
    print(f"Saved report to {REPORT_PATH}", flush=True)
    print(f"Elapsed: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
