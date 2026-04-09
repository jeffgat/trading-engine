#!/usr/bin/env python3
"""Engine-level rerun for shortlisted ORB indicator-confluence overlays.

This is the first structural check after the earlier post-trade overlay work.
Instead of filtering completed trades after the fact, the overlay is enforced
inside the simulator on the actual fill bar.
"""

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

import run_orb_indicator_confluence_exploration as base_exp  # noqa: E402

from orb_backtest.analysis.alpha_v1_downside import DataCache, run_config  # noqa: E402
from orb_backtest.config import StrategyConfig, with_overrides  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "results" / "orb_indicator_confluence_engine_rerun"
REPORT_PATH = ROOT / "learnings" / "reports" / "ORB_INDICATOR_CONFLUENCE_ENGINE_RERUN.md"

START_DATE = "2016-01-01"
DISCOVERY_END = "2022-12-31"
VALIDATION_START = "2023-01-01"
END_DATE = "2024-12-31"
HOLDOUT_START = "2025-01-01"


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    gate: str = ""
    min_atr: float = 0.0
    max_atr: float = 0.0


VARIANTS: tuple[Variant, ...] = (
    Variant("base", "Base frozen anchor"),
    Variant("sma20_aligned_0_20", "SMA20 aligned [0,20%) ATR", "sma20_aligned", 0.0, 0.20),
    Variant("vwap_ema20_aligned_0_10", "VWAP+EMA20 aligned [0,10%) ATR", "vwap_ema20_aligned", 0.0, 0.10),
)


def _segment_metrics(trades: list[TradeResult], start: str, end: str) -> dict:
    return compute_metrics([
        t for t in trades
        if t.exit_type != EXIT_NO_FILL and start <= t.date <= end
    ])


def _round(value: float | int) -> float | int:
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return 0.0
    return round(float(value), 6)


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


def _retention(trades: int, base_trades: int) -> float:
    if base_trades <= 0:
        return 0.0
    return float(trades) / float(base_trades)


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    anchors = base_exp.build_anchor_specs()
    cache = DataCache(start_date=START_DATE, end_date=END_DATE)

    print("ORB indicator confluence engine rerun")
    print("=" * 70)
    print(f"Anchors: {len(anchors)} | Holdout untouched from {HOLDOUT_START}")

    anchor_rows: list[dict[str, object]] = []
    aggregate_streams: dict[tuple[str, str], list[TradeResult]] = {}
    base_anchor_metrics: dict[tuple[str, str], dict] = {}

    for anchor in anchors:
        print(f"\n[{anchor.key}]")
        for variant in VARIANTS:
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
                    "label": anchor.label,
                    "source": anchor.source,
                    "variant_key": variant.key,
                    "variant_label": variant.label,
                    "discovery_trades": int(disc["total_trades"]),
                    "discovery_avg_r": _round(float(disc["avg_r"])),
                    "discovery_pf": _round(float(disc["profit_factor"])),
                    "discovery_total_r": _round(float(disc["total_r"])),
                    "discovery_retention": _round(_retention(int(disc["total_trades"]), int(base_disc["total_trades"]))),
                    "discovery_delta_avg_r": _round(float(disc["avg_r"]) - float(base_disc["avg_r"])),
                    "validation_trades": int(val["total_trades"]),
                    "validation_avg_r": _round(float(val["avg_r"])),
                    "validation_pf": _round(float(val["profit_factor"])),
                    "validation_total_r": _round(float(val["total_r"])),
                    "validation_retention": _round(_retention(int(val["total_trades"]), int(base_val["total_trades"]))),
                    "validation_delta_avg_r": _round(float(val["avg_r"]) - float(base_val["avg_r"])),
                    "pre_holdout_trades": int(pre["total_trades"]),
                    "pre_holdout_avg_r": _round(float(pre["avg_r"])),
                    "pre_holdout_pf": _round(float(pre["profit_factor"])),
                    "pre_holdout_total_r": _round(float(pre["total_r"])),
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
    for variant in VARIANTS:
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
    base_segment_metrics = {
        row["segment"]: row
        for row in aggregate_rows
        if row["variant_key"] == "base"
    }

    aggregate_compare_rows: list[dict[str, object]] = []
    for row in aggregate_rows:
        base_row = base_segment_metrics[row["segment"]]
        aggregate_compare_rows.append(
            {
                **row,
                "retention_vs_base": _round(_retention(int(row["trades"]), int(base_row["trades"]))),
                "delta_avg_r_vs_base": _round(float(row["avg_r"]) - float(base_row["avg_r"])),
                "delta_total_r_vs_base": _round(float(row["total_r"]) - float(base_row["total_r"])),
            }
        )
    aggregate_compare_df = pd.DataFrame(aggregate_compare_rows)
    aggregate_compare_df.to_csv(OUTPUT_DIR / "aggregate_segment_summary.csv", index=False)

    validation_anchor_view = anchor_df[anchor_df["variant_key"] != "base"].copy()
    validation_anchor_view["validation_positive"] = validation_anchor_view["validation_delta_avg_r"] > 0
    validation_anchor_counts = (
        validation_anchor_view.groupby("variant_key")["validation_positive"]
        .sum()
        .astype(int)
        .to_dict()
    )

    summary = {
        "meta": {
            "start_date": START_DATE,
            "discovery_end": DISCOVERY_END,
            "validation_start": VALIDATION_START,
            "end_date": END_DATE,
            "holdout_start": HOLDOUT_START,
            "anchors": [anchor.key for anchor in anchors],
        },
        "aggregate_segments": aggregate_compare_rows,
        "validation_positive_anchor_counts": validation_anchor_counts,
        "runtime_seconds": round(time.time() - t0, 2),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    validation_rows = aggregate_compare_df.query("segment == 'validation'").sort_values(
        by=["delta_avg_r_vs_base", "retention_vs_base", "total_r"],
        ascending=[False, False, False],
    )
    pre_rows = aggregate_compare_df.query("segment == 'pre_holdout'").sort_values(
        by=["delta_avg_r_vs_base", "retention_vs_base", "total_r"],
        ascending=[False, False, False],
    )

    lines = [
        "# ORB Indicator Confluence Engine Rerun",
        "",
        "## Objective",
        "",
        "Structural rerun of the two shortlisted fill-time overlays from the prior post-trade exploration.",
        "This pass enforces the overlay inside the simulator at the actual fill bar on the frozen 9-anchor basket.",
        "",
        "## Scope",
        "",
        f"- Pre-holdout only: {START_DATE} to {END_DATE}",
        f"- Final holdout remains untouched: {HOLDOUT_START}+",
        "- Variants: base anchors, SMA20 aligned [0,20%) ATR, VWAP+EMA20 aligned [0,10%) ATR",
        "",
        "## Aggregate Validation",
        "",
    ]

    for _, row in validation_rows.iterrows():
        if row["variant_key"] == "base":
            continue
        lines.append(
            f"- `{row['variant_key']}`: trades={int(row['trades'])}, avgR={row['avg_r']:.3f}, "
            f"PF={row['profit_factor']:.2f}, totalR={row['total_r']:.1f}, "
            f"retention={row['retention_vs_base'] * 100:.1f}%, "
            f"delta avgR vs base={row['delta_avg_r_vs_base']:+.3f}, "
            f"positive anchors={validation_anchor_counts.get(row['variant_key'], 0)}/{len(anchors)}"
        )

    lines.extend(
        [
            "",
            "## Aggregate Pre-Holdout",
            "",
        ]
    )
    for _, row in pre_rows.iterrows():
        if row["variant_key"] == "base":
            continue
        lines.append(
            f"- `{row['variant_key']}`: trades={int(row['trades'])}, avgR={row['avg_r']:.3f}, "
            f"PF={row['profit_factor']:.2f}, totalR={row['total_r']:.1f}, "
            f"retention={row['retention_vs_base'] * 100:.1f}%, "
            f"delta avgR vs base={row['delta_avg_r_vs_base']:+.3f}"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This is the first engine-integrated pass. It is more realistic than the earlier post-trade overlay study.",
            "- It still uses the frozen anchor universe and does not touch the 2025+ final holdout.",
            "- If one overlay remains clearly positive here, the next step is a proper promotion decision and then a frozen holdout read.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines))

    print("\nSaved:")
    print(f"  - {OUTPUT_DIR / 'anchor_variant_summary.csv'}")
    print(f"  - {OUTPUT_DIR / 'aggregate_segment_summary.csv'}")
    print(f"  - {OUTPUT_DIR / 'summary.json'}")
    print(f"  - {REPORT_PATH}")
    print(f"\nCompleted in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
