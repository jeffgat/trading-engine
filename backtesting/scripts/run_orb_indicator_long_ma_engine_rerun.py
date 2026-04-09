#!/usr/bin/env python3
"""Engine-level rerun for the strongest long-horizon MA overlays."""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_orb_indicator_long_ma_exploration as base_exp  # noqa: E402

from orb_backtest.analysis.alpha_v1_downside import DataCache, run_config  # noqa: E402
from orb_backtest.config import StrategyConfig, with_overrides  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "results" / "orb_indicator_long_ma_engine_rerun"
REPORT_PATH = ROOT / "learnings" / "reports" / "ORB_INDICATOR_LONG_MA_ENGINE_RERUN.md"

START_DATE = "2016-01-01"
DISCOVERY_END = "2022-12-31"
VALIDATION_START = "2023-01-01"
END_DATE = "2024-12-31"
HOLDOUT_START = "2025-01-01"
TOP_VARIANTS = 2


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    gate: str = ""
    min_atr: float = 0.0
    max_atr: float = 0.0


def _round(value: float | int) -> float | int:
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return 0.0
    return round(float(value), 6)


def _retention(trades: int, base_trades: int) -> float:
    if base_trades <= 0:
        return 0.0
    return float(trades) / float(base_trades)


def _variant_config(config: StrategyConfig, variant: Variant) -> StrategyConfig:
    if variant.key == "base":
        return config
    return with_overrides(
        config,
        entry_context_gate=variant.gate,
        entry_context_min_atr=variant.min_atr,
        entry_context_max_atr=variant.max_atr,
        name=f"{config.name}__{variant.key}",
    )


def _segment_metrics(trades: list[TradeResult], start: str, end: str) -> dict:
    return compute_metrics([
        t for t in trades
        if t.exit_type != EXIT_NO_FILL and start <= t.date <= end
    ])


def load_variants() -> list[Variant]:
    df = pd.read_csv(ROOT / "data" / "results" / "orb_indicator_long_ma_walkforward" / "fixed_oos_summary.csv")
    top = df.head(TOP_VARIANTS)
    variants = [Variant("base", "Base frozen anchor")]
    for _, row in top.iterrows():
        high = float(row["high"])
        gate = f"{str(row['components']).replace(',', '_')}_aligned"
        variants.append(
            Variant(
                key=str(row["overlay_key"]),
                label=str(row["label"]),
                gate=gate,
                min_atr=0.0,
                max_atr=high,
            )
        )
    return variants


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    variants = load_variants()
    anchors = base_exp.build_anchor_specs()
    cache = DataCache(start_date=START_DATE, end_date=END_DATE)

    print("ORB indicator long-MA engine rerun")
    print("=" * 70)
    print(f"Variants: {len(variants) - 1} challengers | Holdout reserved from {HOLDOUT_START}")

    anchor_rows: list[dict[str, object]] = []
    aggregate_streams: dict[tuple[str, str], list[TradeResult]] = {}
    base_anchor_metrics: dict[tuple[str, str], dict] = {}

    for anchor in anchors:
        print(f"\n[{anchor.key}]")
        for variant in variants:
            cfg = _variant_config(anchor.config, variant)
            print(f"  - {variant.label}")
            trades = run_config(cache, cfg, start_date=START_DATE, end_date=END_DATE)
            trades = base_exp.apply_regime_gate(cache, cfg, trades, anchor.regime_block_buckets)

            disc = _segment_metrics(trades, START_DATE, DISCOVERY_END)
            val = _segment_metrics(trades, VALIDATION_START, END_DATE)
            pre = _segment_metrics(trades, START_DATE, END_DATE)

            if variant.key == "base":
                base_anchor_metrics[(anchor.key, "discovery")] = disc
                base_anchor_metrics[(anchor.key, "validation")] = val
                base_anchor_metrics[(anchor.key, "pre_holdout")] = pre

            base_disc = base_anchor_metrics.get((anchor.key, "discovery"), {"total_trades": 0, "avg_r": 0.0})
            base_val = base_anchor_metrics.get((anchor.key, "validation"), {"total_trades": 0, "avg_r": 0.0})
            base_pre = base_anchor_metrics.get((anchor.key, "pre_holdout"), {"total_trades": 0, "avg_r": 0.0})

            anchor_rows.append(
                {
                    "anchor": anchor.key,
                    "variant_key": variant.key,
                    "variant_label": variant.label,
                    "gate": variant.gate,
                    "discovery_trades": int(disc["total_trades"]),
                    "discovery_avg_r": _round(float(disc["avg_r"])),
                    "discovery_retention": _round(_retention(int(disc["total_trades"]), int(base_disc["total_trades"]))),
                    "discovery_delta_avg_r": _round(float(disc["avg_r"]) - float(base_disc["avg_r"])),
                    "validation_trades": int(val["total_trades"]),
                    "validation_avg_r": _round(float(val["avg_r"])),
                    "validation_retention": _round(_retention(int(val["total_trades"]), int(base_val["total_trades"]))),
                    "validation_delta_avg_r": _round(float(val["avg_r"]) - float(base_val["avg_r"])),
                    "pre_holdout_trades": int(pre["total_trades"]),
                    "pre_holdout_avg_r": _round(float(pre["avg_r"])),
                    "pre_holdout_retention": _round(_retention(int(pre["total_trades"]), int(base_pre["total_trades"]))),
                    "pre_holdout_delta_avg_r": _round(float(pre["avg_r"]) - float(base_pre["avg_r"])),
                }
            )

            for segment, start, end in (
                ("discovery", START_DATE, DISCOVERY_END),
                ("validation", VALIDATION_START, END_DATE),
                ("pre_holdout", START_DATE, END_DATE),
            ):
                aggregate_streams.setdefault((variant.key, segment), []).extend([
                    t for t in trades
                    if t.exit_type != EXIT_NO_FILL and start <= t.date <= end
                ])

    anchor_df = pd.DataFrame(anchor_rows)
    anchor_df.to_csv(OUTPUT_DIR / "anchor_variant_summary.csv", index=False)

    aggregate_rows: list[dict[str, object]] = []
    for variant in variants:
        for segment in ("discovery", "validation", "pre_holdout"):
            metrics = compute_metrics(aggregate_streams[(variant.key, segment)])
            aggregate_rows.append(
                {
                    "variant_key": variant.key,
                    "variant_label": variant.label,
                    "segment": segment,
                    "trades": int(metrics["total_trades"]),
                    "avg_r": _round(float(metrics["avg_r"])),
                    "profit_factor": _round(float(metrics["profit_factor"])),
                    "total_r": _round(float(metrics["total_r"])),
                    "sharpe_ratio": _round(float(metrics["sharpe_ratio"])),
                    "max_drawdown_r": _round(float(metrics["max_drawdown_r"])),
                }
            )

    aggregate_df = pd.DataFrame(aggregate_rows)
    base_segment_metrics = {row["segment"]: row for row in aggregate_rows if row["variant_key"] == "base"}
    compare_rows: list[dict[str, object]] = []
    for row in aggregate_rows:
        base_row = base_segment_metrics[row["segment"]]
        compare_rows.append(
            {
                **row,
                "retention_vs_base": _round(_retention(int(row["trades"]), int(base_row["trades"]))),
                "delta_avg_r_vs_base": _round(float(row["avg_r"]) - float(base_row["avg_r"])),
            }
        )
    compare_df = pd.DataFrame(compare_rows)
    compare_df.to_csv(OUTPUT_DIR / "aggregate_segment_summary.csv", index=False)
    (OUTPUT_DIR / "summary.json").write_text(json.dumps({"aggregate_segments": compare_rows}, indent=2))

    lines = [
        "# ORB Indicator Long-MA Engine Rerun",
        "",
        "## Aggregate Validation",
        "",
    ]
    for _, row in compare_df.query("segment == 'validation'").sort_values(
        by=["delta_avg_r_vs_base", "retention_vs_base"], ascending=[False, False]
    ).iterrows():
        if row["variant_key"] == "base":
            continue
        lines.append(
            f"- `{row['variant_key']}`: trades={int(row['trades'])}, avgR={row['avg_r']:.3f}, "
            f"PF={row['profit_factor']:.2f}, retention={row['retention_vs_base']:.1%}, "
            f"delta avgR vs base={row['delta_avg_r_vs_base']:+.3f}"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")

    print(f"\nReport: {REPORT_PATH}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
