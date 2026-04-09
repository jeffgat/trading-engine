#!/usr/bin/env python3
"""Frozen holdout read for promoted ORB indicator-confluence overlays."""

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

OUTPUT_DIR = ROOT / "data" / "results" / "orb_indicator_confluence_holdout_read"
REPORT_PATH = ROOT / "learnings" / "reports" / "ORB_INDICATOR_CONFLUENCE_HOLDOUT_READ.md"

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


def _holdout_metrics(trades: list[TradeResult]) -> dict:
    return compute_metrics([
        t for t in trades
        if t.exit_type != EXIT_NO_FILL and t.date >= HOLDOUT_START
    ])


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    anchors = base_exp.build_anchor_specs()
    cache = DataCache(start_date=HOLDOUT_START, end_date=None)

    print("ORB indicator confluence holdout read")
    print("=" * 70)
    print(f"Anchors: {len(anchors)} | Holdout start: {HOLDOUT_START}")

    anchor_rows: list[dict[str, object]] = []
    aggregate_streams: dict[str, list[TradeResult]] = {}
    base_anchor_metrics: dict[str, dict] = {}
    holdout_end_dates: list[str] = []

    for anchor in anchors:
        print(f"\n[{anchor.key}]")
        for variant in VARIANTS:
            cfg = _variant_config(anchor.config, variant)
            print(f"  - {variant.label}")
            trades = run_config(cache, cfg, start_date=HOLDOUT_START, end_date=None)
            trades = base_exp.apply_regime_gate(cache, cfg, trades, anchor.regime_block_buckets)
            filled_holdout = [t for t in trades if t.exit_type != EXIT_NO_FILL and t.date >= HOLDOUT_START]
            if filled_holdout:
                holdout_end_dates.append(max(t.date for t in filled_holdout))
            metrics = _holdout_metrics(trades)

            if variant.key == "base":
                base_anchor_metrics[anchor.key] = metrics
            base_metrics = base_anchor_metrics.get(anchor.key, {"total_trades": 0, "avg_r": 0.0, "total_r": 0.0})

            anchor_rows.append(
                {
                    "anchor": anchor.key,
                    "label": anchor.label,
                    "source": anchor.source,
                    "variant_key": variant.key,
                    "variant_label": variant.label,
                    "holdout_trades": int(metrics["total_trades"]),
                    "holdout_avg_r": _round(float(metrics["avg_r"])),
                    "holdout_pf": _round(float(metrics["profit_factor"])),
                    "holdout_total_r": _round(float(metrics["total_r"])),
                    "holdout_sharpe": _round(float(metrics["sharpe_ratio"])),
                    "holdout_max_dd_r": _round(float(metrics["max_drawdown_r"])),
                    "holdout_retention": _round(_retention(int(metrics["total_trades"]), int(base_metrics["total_trades"]))),
                    "holdout_delta_avg_r": _round(float(metrics["avg_r"]) - float(base_metrics["avg_r"])),
                    "holdout_delta_total_r": _round(float(metrics["total_r"]) - float(base_metrics["total_r"])),
                }
            )

            aggregate_streams.setdefault(variant.key, []).extend(filled_holdout)

    anchor_df = pd.DataFrame(anchor_rows)
    anchor_df.to_csv(OUTPUT_DIR / "anchor_holdout_summary.csv", index=False)

    aggregate_rows: list[dict[str, object]] = []
    for variant in VARIANTS:
        metrics = compute_metrics(aggregate_streams[variant.key])
        aggregate_rows.append(
            {
                "variant_key": variant.key,
                "variant_label": variant.label,
                "trades": int(metrics["total_trades"]),
                "avg_r": _round(float(metrics["avg_r"])),
                "profit_factor": _round(float(metrics["profit_factor"])),
                "total_r": _round(float(metrics["total_r"])),
                "sharpe_ratio": _round(float(metrics["sharpe_ratio"])),
                "max_drawdown_r": _round(float(metrics["max_drawdown_r"])),
            }
        )

    base_row = next(row for row in aggregate_rows if row["variant_key"] == "base")
    aggregate_compare_rows: list[dict[str, object]] = []
    for row in aggregate_rows:
        aggregate_compare_rows.append(
            {
                **row,
                "retention_vs_base": _round(_retention(int(row["trades"]), int(base_row["trades"]))),
                "delta_avg_r_vs_base": _round(float(row["avg_r"]) - float(base_row["avg_r"])),
                "delta_total_r_vs_base": _round(float(row["total_r"]) - float(base_row["total_r"])),
            }
        )

    aggregate_df = pd.DataFrame(aggregate_compare_rows).sort_values(
        by=["delta_avg_r_vs_base", "retention_vs_base", "total_r"],
        ascending=[False, False, False],
    )
    aggregate_df.to_csv(OUTPUT_DIR / "aggregate_holdout_summary.csv", index=False)

    holdout_anchor_view = anchor_df[anchor_df["variant_key"] != "base"].copy()
    positive_anchor_counts: dict[str, int] = {}
    positive_anchor_counts_50: dict[str, int] = {}
    for variant_key, group in holdout_anchor_view.groupby("variant_key"):
        positive_anchor_counts[variant_key] = int((group["holdout_delta_avg_r"] > 0).sum())
        positive_anchor_counts_50[variant_key] = int(
            ((group["holdout_delta_avg_r"] > 0) & (group["holdout_trades"] >= 50)).sum()
        )

    summary = {
        "meta": {
            "holdout_start": HOLDOUT_START,
            "holdout_end": max(holdout_end_dates) if holdout_end_dates else None,
            "anchors": [anchor.key for anchor in anchors],
        },
        "aggregate_holdout": aggregate_compare_rows,
        "positive_anchor_counts": positive_anchor_counts,
        "positive_anchor_counts_50": positive_anchor_counts_50,
        "runtime_seconds": round(time.time() - t0, 2),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "# ORB Indicator Confluence Holdout Read",
        "",
        "## Objective",
        "",
        "Frozen holdout read for the promoted engine-integrated indicator overlays.",
        "This is the first and only 2025+ read for this research branch.",
        "",
        "## Scope",
        "",
        f"- Holdout start: {HOLDOUT_START}",
        f"- Holdout end in current data: {summary['meta']['holdout_end']}",
        "- Variants: base anchors, SMA20 aligned [0,20%) ATR, VWAP+EMA20 aligned [0,10%) ATR",
        "",
        "## Aggregate Holdout",
        "",
    ]
    for _, row in aggregate_df.iterrows():
        if row["variant_key"] == "base":
            continue
        lines.append(
            f"- `{row['variant_key']}`: trades={int(row['trades'])}, avgR={row['avg_r']:.3f}, "
            f"PF={row['profit_factor']:.2f}, totalR={row['total_r']:.1f}, "
            f"retention={row['retention_vs_base'] * 100:.1f}%, "
            f"delta avgR vs base={row['delta_avg_r_vs_base']:+.3f}, "
            f"positive anchors={positive_anchor_counts.get(row['variant_key'], 0)}/{len(anchors)}, "
            f"positive anchors (>=50 trades)={positive_anchor_counts_50.get(row['variant_key'], 0)}/{len(anchors)}"
        )

    winner = aggregate_df.iloc[0]
    lines.extend(
        [
            "",
            "## Readout",
            "",
            f"- Best aggregate holdout transfer: `{winner['variant_key']}`",
            "- This holdout read should be treated as final for this branch. No more threshold tuning off these results.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines))

    print("\nSaved:")
    print(f"  - {OUTPUT_DIR / 'anchor_holdout_summary.csv'}")
    print(f"  - {OUTPUT_DIR / 'aggregate_holdout_summary.csv'}")
    print(f"  - {OUTPUT_DIR / 'summary.json'}")
    print(f"  - {REPORT_PATH}")
    print(f"\nCompleted in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
