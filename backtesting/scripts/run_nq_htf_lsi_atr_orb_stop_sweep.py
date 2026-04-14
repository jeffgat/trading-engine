#!/usr/bin/env python3
"""Broad stop-source sweep for the current NQ NY HTF-LSI operating lead.

Tests whether the current `5m lag24` HTF-LSI branch benefits from using capped
ATR% or ORB% stop distances instead of the default structural stop.

Assumption for ORB-based rows:
- use a minimal NY opening range of `08:30-08:35`
- keep the rest of the current HTF-LSI lead unchanged
- cap ATR/ORB stop distances at the structural invalidation point
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.alpha_v1_downside import filter_trades_by_combined_regime  # noqa: E402
from orb_backtest.analysis.regime_research import build_extended_regime_calendar  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_htf_lsi_atr_orb_stop_sweep"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_HTF_LSI_ATR_ORB_STOP_SWEEP.md"
HOLDOUT_START = "2025-04-01"
EXCLUDE_REGIMES = frozenset({"bear_high_vol"})

STOP_SPECS = (
    {"label": "absolute", "stop_mode": "absolute", "stop_atr_pct": 0.0, "stop_orb_pct": 0.0},
    {"label": "atr_5pct", "stop_mode": "atr_pct", "stop_atr_pct": 5.0, "stop_orb_pct": 0.0},
    {"label": "atr_10pct", "stop_mode": "atr_pct", "stop_atr_pct": 10.0, "stop_orb_pct": 0.0},
    {"label": "atr_15pct", "stop_mode": "atr_pct", "stop_atr_pct": 15.0, "stop_orb_pct": 0.0},
    {"label": "atr_20pct", "stop_mode": "atr_pct", "stop_atr_pct": 20.0, "stop_orb_pct": 0.0},
    {"label": "orb_50pct", "stop_mode": "orb_pct", "stop_atr_pct": 0.0, "stop_orb_pct": 50.0},
    {"label": "orb_75pct", "stop_mode": "orb_pct", "stop_atr_pct": 0.0, "stop_orb_pct": 75.0},
    {"label": "orb_100pct", "stop_mode": "orb_pct", "stop_atr_pct": 0.0, "stop_orb_pct": 100.0},
)

BASE_CONFIG = build_current_nq_ny_htf_lsi_lag24_config(
    name="NQ NY HTF-LSI Lead ATR/ORB Stop Sweep",
)


def _slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        trade
        for trade in trades
        if (start is None or trade.date >= start) and (end is None or trade.date < end)
    ]


def _apply_gate(trades, regime_calendar):
    return filter_trades_by_combined_regime(
        trades,
        regime_calendar,
        include=set(),
        exclude=set(EXCLUDE_REGIMES),
        include_low_confidence=True,
    )


def _trade_shape_stats(trades, min_tick: float) -> dict[str, float]:
    filled = [trade for trade in trades if trade.exit_type != 0]
    if not filled:
        return {
            "median_stop_ticks": 0.0,
            "median_tp1_r": 0.0,
            "median_tp2_r": 0.0,
        }
    return {
        "median_stop_ticks": median(trade.risk_points / min_tick for trade in filled),
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


def _period_summary(trades, min_tick: float) -> dict[str, float | int]:
    metrics = compute_metrics(trades)
    shape = _trade_shape_stats(trades, min_tick)
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


def _write_report(rows: list[dict]) -> None:
    lines = [
        "# NQ HTF-LSI ATR / ORB Stop Sweep",
        "",
        "- Date: `2026-04-13`",
        "- Scope: current NQ NY HTF-LSI operating lead only (`5m lag24`, `long`, `fvg_limit`, `08:30-13:30`, `rr=3.5`, `tp1=0.4`, skip `bear_high_vol`).",
        "- Objective: broad stop-source probe using ORB-style and ATR-style distances while keeping targets on the current `risk` basis.",
        "- ORB assumption: use a minimal NY opening range of `08:30-08:35` so ORB stop rows are available from the first eligible entry bar.",
        "- Rule: ATR% and ORB% stop distances are capped at the structural invalidation point.",
        "- Holdout split: pre-holdout `< 2025-04-01`, holdout `>= 2025-04-01`.",
        "",
        "## Stop Menu",
        "",
        "- `absolute`",
        "- `atr_pct`: `5%`, `10%`, `15%`, `20%` of daily ATR",
        "- `orb_pct`: `50%`, `75%`, `100%` of the `08:30-08:35` opening range",
        "",
        "| Rank | Stop Label | Mode | Stop Value | Pre PF | Pre AvgR | Pre Calmar | Pre DD | Hold PF | Hold AvgR | Hold Calmar | Med Stop (ticks) | Med TP1 R | Med TP2 R |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    ranked = sorted(rows, key=_rank_key, reverse=True)
    for idx, row in enumerate(ranked, start=1):
        pre = row["pre_holdout"]
        hold = row["holdout"]
        lines.append(
            "| "
            f"{idx} | `{row['label']}` | `{row['stop_mode']}` | `{row['stop_value_label']}` | "
            f"{pre['profit_factor']:.3f} | {pre['avg_r']:.3f} | {pre['calmar']:.3f} | {pre['max_dd_r']:.2f} | "
            f"{hold['profit_factor']:.3f} | {hold['avg_r']:.3f} | {hold['calmar']:.3f} | "
            f"{pre['median_stop_ticks']:.1f} | {pre['median_tp1_r']:.2f} | {pre['median_tp2_r']:.2f} |"
        )

    baseline = next(row for row in ranked if row["label"] == "absolute")
    best = ranked[0]
    lines.extend(
        [
            "",
            "## Quick Read",
            "",
            f"- Baseline: `absolute` -> pre PF `{baseline['pre_holdout']['profit_factor']:.3f}`, pre avg R `{baseline['pre_holdout']['avg_r']:.3f}`, pre Calmar `{baseline['pre_holdout']['calmar']:.3f}`, holdout PF `{baseline['holdout']['profit_factor']:.3f}`.",
            f"- Best pre-holdout row: `{best['label']}` -> pre PF `{best['pre_holdout']['profit_factor']:.3f}`, pre avg R `{best['pre_holdout']['avg_r']:.3f}`, pre Calmar `{best['pre_holdout']['calmar']:.3f}`, holdout PF `{best['holdout']['profit_factor']:.3f}`.",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading NQ data for current 5m HTF-LSI lead...", flush=True)
    df_5m, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    print(
        f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
        f"1s: {len(df_1s) if df_1s is not None else 0:,}",
        flush=True,
    )

    regime_calendar = build_extended_regime_calendar(df_5m)
    instrument = BASE_CONFIG.instrument
    base_session = BASE_CONFIG.sessions[0]

    configs: list = []
    config_meta: dict[str, dict] = {}
    for spec in STOP_SPECS:
        session = replace(
            base_session,
            orb_start="08:30",
            orb_end="08:35",
            stop_atr_pct=float(spec["stop_atr_pct"]),
            stop_orb_pct=float(spec["stop_orb_pct"]),
        )
        cfg = replace(
            BASE_CONFIG,
            sessions=(session,),
            lsi_stop_mode=str(spec["stop_mode"]),
            lsi_target_mode="risk",
            name=f"NQ NY HTF-LSI Lead ATR/ORB Stop Sweep {spec['label']}",
        )
        configs.append(cfg)
        config_meta[cfg.name] = spec

    print(f"Building shared maps and signal cache for {len(configs)} configs...", flush=True)
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_5m, configs, signal_df_1m=signal_df_1m)

    def progress(done: int, total: int):
        print(f"  [{done:>2}/{total}] complete", flush=True)

    print("Running sweep...", flush=True)
    results = run_sweep(
        df_5m,
        configs,
        n_workers=min(8, len(configs)),
        progress_fn=progress,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _prebuilt_maps=maps,
        _prebuilt_signal_cache=signal_cache,
    )

    rows: list[dict] = []
    for cfg, trades in results:
        spec = config_meta[cfg.name]
        gated_trades = _apply_gate(trades, regime_calendar)
        rows.append(
            {
                "label": str(spec["label"]),
                "stop_mode": str(spec["stop_mode"]),
                "stop_atr_pct": float(spec["stop_atr_pct"]),
                "stop_orb_pct": float(spec["stop_orb_pct"]),
                "stop_value_label": (
                    f"{spec['stop_atr_pct']:.0f}% ATR"
                    if spec["stop_mode"] == "atr_pct"
                    else (f"{spec['stop_orb_pct']:.0f}% ORB" if spec["stop_mode"] == "orb_pct" else "structural")
                ),
                "config_name": cfg.name,
                "pre_holdout": _period_summary(
                    _slice_trades(gated_trades, end=HOLDOUT_START),
                    instrument.min_tick,
                ),
                "holdout": _period_summary(
                    _slice_trades(gated_trades, start=HOLDOUT_START),
                    instrument.min_tick,
                ),
            }
        )

    rows.sort(key=_rank_key, reverse=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "holdout_start": HOLDOUT_START,
        "exclude_regimes": sorted(EXCLUDE_REGIMES),
        "stop_specs": list(STOP_SPECS),
        "base_params": {
            "strategy": BASE_CONFIG.strategy,
            "timeframe": "5m",
            "direction_filter": BASE_CONFIG.direction_filter,
            "entry_mode": BASE_CONFIG.lsi_entry_mode,
            "entry_start": base_session.entry_start,
            "entry_end": base_session.entry_end,
            "rr": BASE_CONFIG.rr,
            "tp1_ratio": BASE_CONFIG.tp1_ratio,
            "min_gap_atr_pct": base_session.min_gap_atr_pct,
            "atr_length": BASE_CONFIG.atr_length,
            "htf_level_tf_minutes": BASE_CONFIG.htf_level_tf_minutes,
            "htf_n_left": BASE_CONFIG.htf_n_left,
            "htf_trade_max_per_session": BASE_CONFIG.htf_trade_max_per_session,
            "htf_lsi_inversion_ordinal": BASE_CONFIG.htf_lsi_inversion_ordinal,
            "lsi_fvg_window_left": BASE_CONFIG.lsi_fvg_window_left,
            "lsi_fvg_window_right": BASE_CONFIG.lsi_fvg_window_right,
            "max_fvg_to_inversion_bars": BASE_CONFIG.max_fvg_to_inversion_bars,
            "orb_start": "08:30",
            "orb_end": "08:35",
        },
        "rows": rows,
    }

    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(rows)

    best = rows[0]
    baseline = next(row for row in rows if row["label"] == "absolute")
    print("\nTop rows:", flush=True)
    print(
        f"  baseline absolute -> pre PF {baseline['pre_holdout']['profit_factor']:.3f}, "
        f"avg R {baseline['pre_holdout']['avg_r']:.3f}, "
        f"hold PF {baseline['holdout']['profit_factor']:.3f}",
        flush=True,
    )
    print(
        f"  best {best['label']} -> pre PF {best['pre_holdout']['profit_factor']:.3f}, "
        f"avg R {best['pre_holdout']['avg_r']:.3f}, "
        f"hold PF {best['holdout']['profit_factor']:.3f}",
        flush=True,
    )
    print(f"\nSaved summary to {OUTPUT_DIR / 'summary.json'}", flush=True)
    print(f"Saved report to {REPORT_PATH}", flush=True)
    print(f"Elapsed: {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
