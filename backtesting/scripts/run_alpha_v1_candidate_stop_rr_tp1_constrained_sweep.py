#!/usr/bin/env python3
"""Constrained RR/TP1 plus stop-source sweep for ALPHA_V1 candidates.

Creates research artifacts only. Does not edit execution configs.

Target constraint:
- rr <= 3.0
- 1.0 <= rr * tp1_ratio <= 1.5

Stop sweep:
- ORB candidates: ATR% and ORB% stops
- LSI/HTF-LSI/CISD candidates: ATR% stop mode only. Native LSI setups do not
  define an ORB range, so ORB% stops are skipped rather than reported as no-ops.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import run_alpha_v1_candidate_rr_tp1_constrained_sweep as target_sweep  # noqa: E402
from orb_backtest.analysis.gates import apply_dow_filter  # noqa: E402
from orb_backtest.config import StrategyConfig  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "alpha_v1_candidate_stop_rr_tp1_constrained_sweep_20260504"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_CANDIDATE_STOP_RR_TP1_CONSTRAINED_SWEEP_20260504.md"

FULL_START = target_sweep.FULL_START
END_INCLUSIVE = target_sweep.END_INCLUSIVE
END_EXCLUSIVE = target_sweep.END_EXCLUSIVE
WINDOWS = target_sweep.WINDOWS
WORKERS = target_sweep.WORKERS

ATR_STOP_VALUES = (3.0, 5.0, 7.0, 8.0, 10.0, 12.0)
ORB_STOP_VALUES = (17.0, 50.0, 75.0, 100.0, 125.0, 150.0)


@dataclass(frozen=True)
class StopTargetVariant:
    candidate: target_sweep.CandidateSpec
    variant_id: str
    rr: float
    tp1_ratio: float
    tp1_r: float
    stop_source: str
    stop_value: float
    config: StrategyConfig


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        value = float(data)
        return value if math.isfinite(value) else None
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    return data


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _fmt_float(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text.replace(".", "p")


def _is_lsi_family(config: StrategyConfig) -> bool:
    return config.strategy in {"lsi", "htf_lsi", "reference_lsi"}


def _session_replace(config: StrategyConfig, **updates: Any) -> StrategyConfig:
    return replace(config, sessions=(replace(config.sessions[0], **updates),))


def _with_stop(
    config: StrategyConfig,
    *,
    name: str,
    rr: float,
    tp1_ratio: float,
    stop_source: str,
    stop_value: float,
) -> StrategyConfig:
    cfg = replace(config, name=name, rr=rr, tp1_ratio=tp1_ratio)
    if _is_lsi_family(cfg):
        if stop_source != "atr_pct":
            raise ValueError("Native LSI-family candidates only support atr_pct stop sweep here.")
        cfg = _session_replace(cfg, stop_atr_pct=stop_value, stop_orb_pct=0.0)
        return replace(cfg, lsi_stop_mode="atr_pct")
    if stop_source == "atr_pct":
        return _session_replace(cfg, stop_atr_pct=stop_value, stop_orb_pct=0.0)
    if stop_source == "orb_pct":
        return _session_replace(cfg, stop_atr_pct=0.0, stop_orb_pct=stop_value)
    raise ValueError(f"Unknown stop source {stop_source!r}")


def _variants_for(candidate: target_sweep.CandidateSpec) -> list[StopTargetVariant]:
    variants: list[StopTargetVariant] = []
    stop_options = [("atr_pct", value) for value in ATR_STOP_VALUES]
    if not _is_lsi_family(candidate.base_config):
        stop_options.extend(("orb_pct", value) for value in ORB_STOP_VALUES)

    for rr, tp1_ratio, tp1_r in target_sweep._target_pairs():
        for stop_source, stop_value in stop_options:
            variant_id = (
                f"{stop_source}{_fmt_float(stop_value)}"
                f"__rr{_fmt_float(rr)}__tp1r{_fmt_float(tp1_r)}"
            )
            name = f"{candidate.key}__{variant_id}"[:240]
            try:
                cfg = _with_stop(
                    candidate.base_config,
                    name=name,
                    rr=rr,
                    tp1_ratio=tp1_ratio,
                    stop_source=stop_source,
                    stop_value=stop_value,
                )
            except ValueError as exc:
                print(f"  skip {name}: {exc}", flush=True)
                continue
            variants.append(
                StopTargetVariant(
                    candidate=candidate,
                    variant_id=variant_id,
                    rr=rr,
                    tp1_ratio=tp1_ratio,
                    tp1_r=tp1_r,
                    stop_source=stop_source,
                    stop_value=stop_value,
                    config=cfg,
                )
            )
    return variants


def _metric_row(
    *,
    variant: StopTargetVariant,
    trades: list[TradeResult],
    window: str,
    start: str,
    end_inclusive: str,
) -> dict[str, Any]:
    selected = [trade for trade in trades if start <= trade.date <= end_inclusive]
    metrics = compute_metrics(selected)
    return {
        "candidate": variant.candidate.key,
        "label": variant.candidate.label,
        "source_group": variant.candidate.source_group,
        "variant_id": variant.variant_id,
        "window": window,
        "start": start,
        "end": end_inclusive,
        "stop_source": variant.stop_source,
        "stop_value": variant.stop_value,
        "rr": variant.rr,
        "tp1_ratio": variant.tp1_ratio,
        "tp1_r": variant.tp1_r,
        "signals": int(metrics["total_signals"]),
        "trades": int(metrics["total_trades"]),
        "no_fills": int(metrics["no_fills"]),
        "net_r": _round(metrics["total_r"], 2),
        "win_rate_pct": _round(float(metrics["win_rate"]) * 100.0, 2),
        "profit_factor": _round(metrics["profit_factor"], 3),
        "avg_r": _round(metrics["avg_r"], 4),
        "sharpe_ratio": _round(metrics["sharpe_ratio"], 3),
        "max_dd_r": _round(metrics["max_drawdown_r"], 2),
        "calmar_ratio": _round(metrics["calmar_ratio"], 3),
        "negative_years": int(sum(1 for value in (metrics.get("r_by_year") or {}).values() if value < 0)),
        "deployability": variant.candidate.deployability,
        "live_support_notes": variant.candidate.live_support_notes,
        "exact_replay_required": variant.candidate.exact_replay_required,
    }


def _score_rows(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_variant: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in metric_rows:
        by_variant.setdefault((str(row["candidate"]), str(row["variant_id"])), []).append(row)

    ranked: list[dict[str, Any]] = []
    for (candidate, variant_id), rows in by_variant.items():
        by_window = {str(row["window"]): row for row in rows}
        if not {"last_1y", "last_2y", "full"} <= set(by_window):
            continue
        last1 = by_window["last_1y"]
        last2 = by_window["last_2y"]
        full = by_window["full"]
        score = (
            3.0 * float(last1["net_r"] or 0.0)
            + 2.0 * float(last2["net_r"] or 0.0)
            + 0.75 * float(full["net_r"] or 0.0)
            - 0.75 * abs(float(last1["max_dd_r"] or 0.0))
            - 0.35 * abs(float(last2["max_dd_r"] or 0.0))
            - 0.10 * abs(float(full["max_dd_r"] or 0.0))
            - 8.0 * int(full["negative_years"] or 0)
        )
        if int(last1["trades"] or 0) < 12:
            score -= 20.0
        ranked.append(
            {
                "candidate": candidate,
                "label": full["label"],
                "source_group": full["source_group"],
                "variant_id": variant_id,
                "stop_source": full["stop_source"],
                "stop_value": float(full["stop_value"]),
                "rr": float(full["rr"]),
                "tp1_ratio": float(full["tp1_ratio"]),
                "tp1_r": float(full["tp1_r"]),
                "promotion_score": round(score, 3),
                "last_1y_net_r": float(last1["net_r"] or 0.0),
                "last_1y_trades": int(last1["trades"] or 0),
                "last_1y_wr_pct": float(last1["win_rate_pct"] or 0.0),
                "last_1y_pf": float(last1["profit_factor"] or 0.0),
                "last_1y_dd_r": float(last1["max_dd_r"] or 0.0),
                "last_2y_net_r": float(last2["net_r"] or 0.0),
                "last_2y_trades": int(last2["trades"] or 0),
                "last_2y_wr_pct": float(last2["win_rate_pct"] or 0.0),
                "last_2y_pf": float(last2["profit_factor"] or 0.0),
                "last_2y_dd_r": float(last2["max_dd_r"] or 0.0),
                "full_net_r": float(full["net_r"] or 0.0),
                "full_trades": int(full["trades"] or 0),
                "full_wr_pct": float(full["win_rate_pct"] or 0.0),
                "full_pf": float(full["profit_factor"] or 0.0),
                "full_dd_r": float(full["max_dd_r"] or 0.0),
                "full_negative_years": int(full["negative_years"] or 0),
                "deployability": full["deployability"],
                "live_support_notes": full["live_support_notes"],
                "exact_replay_required": full["exact_replay_required"],
            }
        )
    return sorted(ranked, key=lambda row: row["promotion_score"], reverse=True)


def _best_by_candidate(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in ranked:
        if row["candidate"] in seen:
            continue
        seen.add(str(row["candidate"]))
        out.append(row)
    return out


def _best_by_stop_source(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in ranked:
        key = (str(row["candidate"]), str(row["stop_source"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _manifest_row(variant: StopTargetVariant) -> dict[str, Any]:
    session = variant.config.sessions[0]
    return {
        "candidate": variant.candidate.key,
        "label": variant.candidate.label,
        "source_group": variant.candidate.source_group,
        "variant_id": variant.variant_id,
        "instrument": variant.config.instrument.symbol,
        "strategy": variant.config.strategy,
        "stop_source": variant.stop_source,
        "stop_value": variant.stop_value,
        "lsi_stop_mode": variant.config.lsi_stop_mode,
        "rr": variant.rr,
        "tp1_ratio": variant.tp1_ratio,
        "tp1_r": variant.tp1_r,
        "stop_atr_pct": session.stop_atr_pct,
        "stop_orb_pct": session.stop_orb_pct,
        "min_stop_points": session.min_stop_points,
        "min_tp1_points": session.min_tp1_points,
        "orb_start": session.orb_start,
        "orb_end": session.orb_end,
        "entry_start": session.entry_start,
        "entry_end": session.entry_end,
        "flat_start": session.flat_start,
        "flat_end": session.flat_end,
        "deployability": variant.candidate.deployability,
        "live_support_notes": variant.candidate.live_support_notes,
        "exact_replay_required": variant.candidate.exact_replay_required,
        "inclusion_notes": variant.candidate.inclusion_notes,
    }


def _md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    out = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        cells = []
        for _, key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                value = f"{value:.2f}"
            cells.append(str(value))
        out.append("| " + " | ".join(cells) + " |")
    return out


def _write_report(
    *,
    candidates: list[target_sweep.CandidateSpec],
    ranked: list[dict[str, Any]],
    best_by_source: list[dict[str, Any]],
) -> None:
    best = _best_by_candidate(ranked)
    rows = [
        {
            "rank": idx,
            "candidate": row["label"],
            "group": row["source_group"],
            "stop": f"{row['stop_source']} {row['stop_value']:g}",
            "rr": row["rr"],
            "tp1_ratio": row["tp1_ratio"],
            "TP1_R": row["tp1_r"],
            "1y R/tr/WR/PF/DD": (
                f"{row['last_1y_net_r']:.1f}/{row['last_1y_trades']}/"
                f"{row['last_1y_wr_pct']:.1f}%/{row['last_1y_pf']:.2f}/{row['last_1y_dd_r']:.1f}"
            ),
            "2y R/tr/PF/DD": (
                f"{row['last_2y_net_r']:.1f}/{row['last_2y_trades']}/"
                f"{row['last_2y_pf']:.2f}/{row['last_2y_dd_r']:.1f}"
            ),
            "full R/tr/WR/PF/DD": (
                f"{row['full_net_r']:.1f}/{row['full_trades']}/"
                f"{row['full_wr_pct']:.1f}%/{row['full_pf']:.2f}/{row['full_dd_r']:.1f}"
            ),
            "deployability": row["deployability"],
        }
        for idx, row in enumerate(best, start=1)
    ]

    source_rows = [
        {
            "candidate": row["label"],
            "stop_source": row["stop_source"],
            "stop_value": row["stop_value"],
            "rr": row["rr"],
            "tp1_ratio": row["tp1_ratio"],
            "TP1_R": row["tp1_r"],
            "1y R": row["last_1y_net_r"],
            "2y R": row["last_2y_net_r"],
            "full R": row["full_net_r"],
            "full PF": row["full_pf"],
            "full DD": row["full_dd_r"],
        }
        for row in best_by_source
    ]

    lines = [
        "# ALPHA_V1 Candidate Stop + RR/TP1 Constrained Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Windows: last 1y `{target_sweep.LAST_1Y_START}` to `{END_INCLUSIVE}`, last 2y `{target_sweep.LAST_2Y_START}` to `{END_INCLUSIVE}`, full `{FULL_START}` to `{END_INCLUSIVE}`.",
        "- Target constraint preserved: `rr <= 3.0` and `1.0 <= rr * tp1_ratio <= 1.5`.",
        f"- RR/TP1 target menu: `{target_sweep._target_pairs()}`.",
        f"- ATR stop values: `{ATR_STOP_VALUES}`.",
        f"- ORB stop values: `{ORB_STOP_VALUES}`.",
        "- ORB-style candidates swept both ATR% and ORB% stops.",
        "- LSI/HTF-LSI/CISD candidates swept ATR% stop mode only; native LSI setups do not define an ORB range, so ORB% stop rows were skipped rather than treated as valid comparisons.",
        "",
        "## Candidate Set",
        "",
        *_md_table(
            [
                {
                    "candidate": candidate.label,
                    "key": candidate.key,
                    "group": candidate.source_group,
                    "strategy": candidate.base_config.strategy,
                    "deployability": candidate.deployability,
                    "exact": candidate.exact_replay_required,
                }
                for candidate in candidates
            ],
            [
                ("Candidate", "candidate"),
                ("Key", "key"),
                ("Group", "group"),
                ("Strategy", "strategy"),
                ("Deployability", "deployability"),
                ("Exact", "exact"),
            ],
        ),
        "",
        "## Best Overall Per Candidate",
        "",
        *_md_table(
            rows,
            [
                ("Rank", "rank"),
                ("Candidate", "candidate"),
                ("Group", "group"),
                ("Stop", "stop"),
                ("rr", "rr"),
                ("tp1_ratio", "tp1_ratio"),
                ("TP1_R", "TP1_R"),
                ("1y R/tr/WR/PF/DD", "1y R/tr/WR/PF/DD"),
                ("2y R/tr/PF/DD", "2y R/tr/PF/DD"),
                ("full R/tr/WR/PF/DD", "full R/tr/WR/PF/DD"),
                ("Deployability", "deployability"),
            ],
        ),
        "",
        "## Best By Stop Source",
        "",
        *_md_table(
            source_rows,
            [
                ("Candidate", "candidate"),
                ("Stop Source", "stop_source"),
                ("Stop Value", "stop_value"),
                ("rr", "rr"),
                ("tp1_ratio", "tp1_ratio"),
                ("TP1_R", "TP1_R"),
                ("1y R", "1y R"),
                ("2y R", "2y R"),
                ("full R", "full R"),
                ("full PF", "full PF"),
                ("full DD", "full DD"),
            ],
        ),
        "",
        "## Read",
        "",
        "- This is a research sweep, not an execution-config change.",
        "- Any live-native winner still needs exact execution replay before promotion.",
        "- ORB% stop rows are only valid for ORB-style candidates in this packet.",
        "",
        "## Artifacts",
        "",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
        f"- Ranked rows CSV: `backtesting/data/results/{RUN_SLUG}/ranked_candidates.csv`",
        f"- Best by candidate CSV: `backtesting/data/results/{RUN_SLUG}/best_by_candidate.csv`",
        f"- Best by stop source CSV: `backtesting/data/results/{RUN_SLUG}/best_by_stop_source.csv`",
        f"- Window metrics CSV: `backtesting/data/results/{RUN_SLUG}/window_metrics.csv`",
        f"- Variant manifest CSV: `backtesting/data/results/{RUN_SLUG}/variant_manifest.csv`",
        f"- Script: `backtesting/scripts/run_alpha_v1_candidate_stop_rr_tp1_constrained_sweep.py`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def _load_data_by_key() -> dict[str, dict[str, Any]]:
    return target_sweep._load_data_by_key()


def _run_group(data_key: str, variants: list[StopTargetVariant], loaded: dict[str, Any]) -> dict[str, list[TradeResult]]:
    if not variants:
        return {}
    print(f"Running {data_key}: {len(variants)} configs", flush=True)

    def progress(done: int, total: int) -> None:
        if done == total or done % 50 == 0:
            print(f"  {data_key}: {done}/{total}", flush=True)

    results = run_sweep(
        loaded["df"],
        [variant.config for variant in variants],
        n_workers=min(WORKERS, max(1, len(variants))),
        start_date=FULL_START,
        end_date=END_EXCLUSIVE,
        df_1m=loaded["df_1m"],
        df_1s=loaded["df_1s"],
        signal_df_1m=loaded["signal_df_1m"],
        progress_fn=progress,
    )
    by_name = {variant.config.name: variant for variant in variants}
    out: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        variant = by_name[config.name]
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        out[variant.config.name] = [
            trade for trade in sorted(trades, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))
            if trade.exit_type != EXIT_NO_FILL
        ]
    return out


def main() -> None:
    t0 = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = target_sweep._all_candidates()
    variants = [variant for candidate in candidates for variant in _variants_for(candidate)]
    print(f"Candidate legs: {len(candidates)}", flush=True)
    print(f"Target pairs: {len(target_sweep._target_pairs())}", flush=True)
    print(f"ATR stops: {ATR_STOP_VALUES}", flush=True)
    print(f"ORB stops: {ORB_STOP_VALUES}", flush=True)
    print(f"Total configs: {len(variants)}", flush=True)

    loaded_by_key = _load_data_by_key()
    variants_by_data: dict[str, list[StopTargetVariant]] = {}
    for variant in variants:
        variants_by_data.setdefault(variant.candidate.data_key, []).append(variant)

    trades_by_name: dict[str, list[TradeResult]] = {}
    for data_key, group_variants in variants_by_data.items():
        trades_by_name.update(_run_group(data_key, group_variants, loaded_by_key[data_key]))

    manifest_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for variant in variants:
        trades = trades_by_name.get(variant.config.name, [])
        manifest_rows.append(_manifest_row(variant))
        for window, (start, end) in WINDOWS.items():
            metric_rows.append(_metric_row(variant=variant, trades=trades, window=window, start=start, end_inclusive=end))

    ranked = _score_rows(metric_rows)
    best = _best_by_candidate(ranked)
    best_by_source = _best_by_stop_source(ranked)

    pd.DataFrame(manifest_rows).to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(RESULT_DIR / "window_metrics.csv", index=False)
    pd.DataFrame(ranked).to_csv(RESULT_DIR / "ranked_candidates.csv", index=False)
    pd.DataFrame(best).to_csv(RESULT_DIR / "best_by_candidate.csv", index=False)
    pd.DataFrame(best_by_source).to_csv(RESULT_DIR / "best_by_stop_source.csv", index=False)

    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "run_slug": RUN_SLUG,
        "constraint": {
            "rr_max": 3.0,
            "tp1_r_min": 1.0,
            "tp1_r_max": 1.5,
            "target_pairs": [
                {"rr": rr, "tp1_ratio": tp1, "tp1_r": tp1r}
                for rr, tp1, tp1r in target_sweep._target_pairs()
            ],
        },
        "stop_values": {
            "atr_pct": ATR_STOP_VALUES,
            "orb_pct": ORB_STOP_VALUES,
            "orb_pct_note": "ORB% stops skipped for LSI/HTF-LSI/CISD candidates because native LSI sessions do not define an ORB range.",
        },
        "windows": WINDOWS,
        "candidates": [
            {
                "key": candidate.key,
                "label": candidate.label,
                "source_group": candidate.source_group,
                "strategy": candidate.base_config.strategy,
                "deployability": candidate.deployability,
                "live_support_notes": candidate.live_support_notes,
                "exact_replay_required": candidate.exact_replay_required,
            }
            for candidate in candidates
        ],
        "best_by_candidate": best,
        "best_by_stop_source": best_by_source,
        "top_50": ranked[:50],
        "notes": [
            "Research sweep only; execution configs were not edited.",
            "Live-native candidates still require exact execution replay before promotion.",
            "Stop source and stop value were swept alongside constrained RR/TP1 target pairs.",
        ],
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True) + "\n")
    _write_report(candidates=candidates, ranked=ranked, best_by_source=best_by_source)

    print("\nBest by candidate:", flush=True)
    for row in best:
        print(
            f"  {row['candidate']:<36} {row['stop_source']}={row['stop_value']:>6.1f} "
            f"rr={row['rr']:.2f} tp1={row['tp1_ratio']:.4f} TP1_R={row['tp1_r']:.2f} | "
            f"1y {row['last_1y_net_r']:+.1f}R 2y {row['last_2y_net_r']:+.1f}R "
            f"full {row['full_net_r']:+.1f}R",
            flush=True,
        )
    print(f"\nSaved: {RESULT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Elapsed: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
