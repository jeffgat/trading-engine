#!/usr/bin/env python3
"""Initial long-horizon MA confluence exploration on frozen ORB anchors."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_orb_indicator_confluence_exploration as base_exp  # noqa: E402

from orb_backtest.analysis.alpha_v1_downside import DataCache, run_config  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.signals.daily_atr import compute_daily_atr  # noqa: E402
from orb_backtest.signals.session import compute_session_days  # noqa: E402
from orb_backtest.signals.vwap import compute_session_vwap  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "results" / "orb_indicator_long_ma_exploration"
REPORT_PATH = ROOT / "learnings" / "reports" / "ORB_INDICATOR_LONG_MA_INITIAL_RESULTS.md"
SPEC_PATH = ROOT / "learnings" / "reports" / "ORB_INDICATOR_LONG_MA_INITIAL_SPEC.md"

RESEARCH_START = base_exp.RESEARCH_START
DISCOVERY_END = base_exp.DISCOVERY_END
VALIDATION_START = base_exp.VALIDATION_START
PRE_HOLDOUT_END = base_exp.PRE_HOLDOUT_END
HOLDOUT_START = base_exp.HOLDOUT_START

MIN_TRADES_PER_ANCHOR_SEGMENT = 12
MIN_COMBINED_VALIDATION_TRADES = 40
MIN_RETENTION = 0.10
MAX_RETENTION = 0.90

INDICATOR_SETS: dict[str, tuple[str, ...]] = {
    "sma100": ("sma100",),
    "sma200": ("sma200",),
    "sma300": ("sma300",),
    "ema100": ("ema100",),
    "ema200": ("ema200",),
    "ema300": ("ema300",),
    "vwap_sma100": ("vwap", "sma100"),
    "vwap_sma200": ("vwap", "sma200"),
    "vwap_sma300": ("vwap", "sma300"),
    "vwap_ema100": ("vwap", "ema100"),
    "vwap_ema200": ("vwap", "ema200"),
    "vwap_ema300": ("vwap", "ema300"),
    "sma100_sma200": ("sma100", "sma200"),
    "sma100_sma300": ("sma100", "sma300"),
    "sma200_sma300": ("sma200", "sma300"),
    "ema100_ema200": ("ema100", "ema200"),
    "ema100_ema300": ("ema100", "ema300"),
    "ema200_ema300": ("ema200", "ema300"),
    "sma100_ema100": ("sma100", "ema100"),
    "sma200_ema200": ("sma200", "ema200"),
    "sma300_ema300": ("sma300", "ema300"),
}

RULES = base_exp.RULES


def build_anchor_specs():
    return base_exp.build_anchor_specs()


def apply_regime_gate(cache, config, trades, blocked_buckets):
    return base_exp.apply_regime_gate(cache, config, trades, blocked_buckets)


def build_indicator_frame(df: pd.DataFrame, session, atr_length: int) -> pd.DataFrame:
    close = df["close"]
    daily_atr = compute_daily_atr(df, length=atr_length)
    _, session_day_id = compute_session_days(df.index, session)
    vwap = compute_session_vwap(
        df["high"].values.astype(np.float64),
        df["low"].values.astype(np.float64),
        close.values.astype(np.float64),
        df["volume"].fillna(0.0).values.astype(np.float64),
        session_day_id,
    )
    indicator_df = pd.DataFrame(index=df.index)
    indicator_df["daily_atr"] = daily_atr
    indicator_df["vwap"] = pd.Series(vwap, index=df.index).shift(1)
    for period in (100, 200, 300):
        indicator_df[f"ema{period}"] = (
            close.ewm(span=period, adjust=False, min_periods=period).mean().shift(1)
        )
        indicator_df[f"sma{period}"] = (
            close.rolling(period, min_periods=period).mean().shift(1)
        )
    return indicator_df


def build_trade_features(anchor, trades, indicator_df: pd.DataFrame):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    rows: list[dict[str, object]] = []
    for trade_id, trade in enumerate(filled):
        fill_bar = trade.fill_bar
        if fill_bar < 0 or fill_bar >= len(indicator_df):
            continue
        row = indicator_df.iloc[fill_bar]
        atr = float(row["daily_atr"]) if pd.notna(row["daily_atr"]) else np.nan
        if not np.isfinite(atr) or atr <= 0:
            continue
        feature_row: dict[str, object] = {
            "trade_id": trade_id,
            "anchor": anchor.key,
            "label": anchor.label,
            "date": trade.date,
            "segment": base_exp._segment_for_date(trade.date),
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "r_multiple": trade.r_multiple,
            "daily_atr": atr,
        }
        for name in ("vwap", "sma100", "sma200", "sma300", "ema100", "ema200", "ema300"):
            value = float(row[name]) if pd.notna(row[name]) else np.nan
            feature_row[name] = value
            feature_row[f"dist_{name}"] = (
                float(trade.direction) * (trade.entry_price - value) / atr
                if np.isfinite(value)
                else np.nan
            )
        rows.append(feature_row)
    return filled, pd.DataFrame(rows)


def write_spec(path: Path, anchors) -> None:
    lines = [
        "# ORB Indicator Long-MA Initial Research Spec",
        "",
        "## Objective",
        "",
        "Fresh pre-holdout exploration of long-horizon moving-average confluence on frozen ORB anchors.",
        "This branch extends the earlier SMA20/EMA20 work by testing slower 5m trend references.",
        "",
        "## Bailey Posture",
        "",
        f"- Discovery window: {RESEARCH_START} to {DISCOVERY_END}",
        f"- Validation window: {VALIDATION_START} to {PRE_HOLDOUT_END}",
        f"- Already-opened holdout remains unused for this branch: {HOLDOUT_START}+",
        "- Base ORB parameters remain frozen.",
        "- This pass is heuristic only: post-trade overlay filtering on actual filled trades.",
        "",
        "## Indicator Set",
        "",
        "- Single indicators: SMA100, SMA200, SMA300, EMA100, EMA200, EMA300.",
        "- Combos: VWAP paired with each long MA, same-family long-MA pairs, and same-period SMA/EMA pairs.",
        "- All indicator values come from the previous completed 5m bar at the fill bar.",
        "- Distances are normalized by prior-day daily ATR.",
        "",
        "## Anchor Universe",
        "",
    ]
    for anchor in anchors:
        gate_note = (
            f", regime block={','.join(anchor.regime_block_buckets)}"
            if anchor.regime_block_buckets
            else ""
        )
        lines.append(
            f"- `{anchor.key}`: {anchor.label} | session={anchor.config.sessions[0].name} | "
            f"direction={anchor.config.direction_filter}{gate_note}"
        )
    lines.extend(
        [
            "",
            "## Rule Families",
            "",
            "- aligned_near: [0.0, 0.20) ATR",
            "- aligned_far: [0.20, +inf) ATR",
            "- reversion_near: [-0.20, 0.0) ATR",
            "- reversion_far: (-inf, -0.20) ATR",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    anchors = build_anchor_specs()
    cache = DataCache(start_date=RESEARCH_START, end_date=PRE_HOLDOUT_END)
    write_spec(SPEC_PATH, anchors)

    base_segment_trades: dict[str, list] = {"discovery": [], "validation": []}
    anchor_rows: list[dict[str, object]] = []
    aggregate_store: dict[tuple[str, str], list] = {}
    base_summary_rows: list[dict[str, object]] = []

    print("ORB long-MA confluence exploration")
    print("=" * 70)
    print(f"Indicator sets: {len(INDICATOR_SETS)} | Holdout reserved from {HOLDOUT_START}")

    for anchor in anchors:
        print(f"\n[{anchor.key}] Running frozen anchor...")
        trades = run_config(cache, anchor.config, start_date=RESEARCH_START, end_date=PRE_HOLDOUT_END)
        trades = apply_regime_gate(cache, anchor.config, trades, anchor.regime_block_buckets)
        market = cache.get(anchor.config.instrument)
        indicator_df = build_indicator_frame(market.df_5m, anchor.config.sessions[0], anchor.config.atr_length)
        filled, features = build_trade_features(anchor, trades, indicator_df)

        base_disc = base_exp._metrics_for_segment(filled, RESEARCH_START, DISCOVERY_END)
        base_val = base_exp._metrics_for_segment(filled, VALIDATION_START, PRE_HOLDOUT_END)
        base_summary_rows.append(
            {
                "anchor": anchor.key,
                "label": anchor.label,
                "source": anchor.source,
                "discovery_trades": int(base_disc["total_trades"]),
                "discovery_avg_r": round(float(base_disc["avg_r"]), 6),
                "validation_trades": int(base_val["total_trades"]),
                "validation_avg_r": round(float(base_val["avg_r"]), 6),
            }
        )
        base_segment_trades["discovery"].extend([t for t in filled if RESEARCH_START <= t.date <= DISCOVERY_END])
        base_segment_trades["validation"].extend([t for t in filled if VALIDATION_START <= t.date <= PRE_HOLDOUT_END])

        trade_map = {i: trade for i, trade in enumerate(filled)}
        for indicator_key, components in INDICATOR_SETS.items():
            cols = [f"dist_{name}" for name in components]
            usable = features.dropna(subset=cols)
            if usable.empty:
                continue
            for rule in RULES:
                mask = base_exp._rule_mask(usable, cols, rule)
                selected_ids = set(usable.loc[mask, "trade_id"].astype(int).tolist())
                selected = [trade_map[i] for i in sorted(selected_ids)]
                disc_metrics = base_exp._metrics_for_segment(selected, RESEARCH_START, DISCOVERY_END)
                val_metrics = base_exp._metrics_for_segment(selected, VALIDATION_START, PRE_HOLDOUT_END)
                disc_trades = int(disc_metrics["total_trades"])
                val_trades = int(val_metrics["total_trades"])
                disc_base = int(base_disc["total_trades"])
                val_base = int(base_val["total_trades"])
                overlay_key = f"{indicator_key}__{rule.key}"
                anchor_rows.append(
                    {
                        "anchor": anchor.key,
                        "label": anchor.label,
                        "source": anchor.source,
                        "indicator_set": indicator_key,
                        "components": ",".join(components),
                        "rule": rule.key,
                        "rule_label": rule.label,
                        "overlay_key": overlay_key,
                        "discovery_trades": disc_trades,
                        "discovery_retention": round(float(disc_trades / disc_base), 6) if disc_base else np.nan,
                        "discovery_avg_r": round(float(disc_metrics["avg_r"]), 6),
                        "discovery_delta_avg_r": round(float(disc_metrics["avg_r"] - base_disc["avg_r"]), 6),
                        "validation_trades": val_trades,
                        "validation_retention": round(float(val_trades / val_base), 6) if val_base else np.nan,
                        "validation_avg_r": round(float(val_metrics["avg_r"]), 6),
                        "validation_delta_avg_r": round(float(val_metrics["avg_r"] - base_val["avg_r"]), 6),
                    }
                )
                aggregate_store.setdefault((overlay_key, "discovery"), []).extend(
                    [t for t in selected if RESEARCH_START <= t.date <= DISCOVERY_END]
                )
                aggregate_store.setdefault((overlay_key, "validation"), []).extend(
                    [t for t in selected if VALIDATION_START <= t.date <= PRE_HOLDOUT_END]
                )

    anchor_df = pd.DataFrame(anchor_rows)
    base_df = pd.DataFrame(base_summary_rows)

    aggregate_rows: list[dict[str, object]] = []
    base_disc = compute_metrics(base_segment_trades["discovery"])
    base_val = compute_metrics(base_segment_trades["validation"])
    for overlay_key in sorted({row["overlay_key"] for row in anchor_rows}):
        indicator_key, rule_key = overlay_key.split("__", 1)
        disc_metrics = compute_metrics(aggregate_store.get((overlay_key, "discovery"), []))
        val_metrics = compute_metrics(aggregate_store.get((overlay_key, "validation"), []))
        eligible_val = anchor_df[
            (anchor_df["overlay_key"] == overlay_key)
            & (anchor_df["validation_trades"] >= MIN_TRADES_PER_ANCHOR_SEGMENT)
        ]
        aggregate_rows.append(
            {
                "overlay_key": overlay_key,
                "indicator_set": indicator_key,
                "components": ",".join(INDICATOR_SETS[indicator_key]),
                "rule": rule_key,
                "discovery_trades": int(disc_metrics["total_trades"]),
                "discovery_retention": round(
                    float(disc_metrics["total_trades"] / base_disc["total_trades"]), 6
                ) if base_disc["total_trades"] else np.nan,
                "discovery_avg_r": round(float(disc_metrics["avg_r"]), 6),
                "discovery_delta_avg_r": round(float(disc_metrics["avg_r"] - base_disc["avg_r"]), 6),
                "validation_trades": int(val_metrics["total_trades"]),
                "validation_retention": round(
                    float(val_metrics["total_trades"] / base_val["total_trades"]), 6
                ) if base_val["total_trades"] else np.nan,
                "validation_avg_r": round(float(val_metrics["avg_r"]), 6),
                "validation_pf": round(float(val_metrics["profit_factor"]), 6),
                "validation_delta_avg_r": round(float(val_metrics["avg_r"] - base_val["avg_r"]), 6),
                "positive_validation_anchors": int((eligible_val["validation_delta_avg_r"] > 0).sum()),
                "eligible_validation_anchors": int(len(eligible_val)),
            }
        )

    aggregate_df = pd.DataFrame(aggregate_rows).sort_values(
        by=["validation_delta_avg_r", "positive_validation_anchors", "validation_trades"],
        ascending=[False, False, False],
    )

    shortlist_df = aggregate_df[
        (aggregate_df["rule"] == "aligned_near")
        & (aggregate_df["validation_trades"] >= MIN_COMBINED_VALIDATION_TRADES)
        & (aggregate_df["validation_retention"] >= MIN_RETENTION)
        & (aggregate_df["validation_retention"] <= MAX_RETENTION)
        & (aggregate_df["validation_delta_avg_r"] > 0)
        & (aggregate_df["positive_validation_anchors"] >= 3)
    ].copy()

    payload = {
        "meta": {
            "research_start": RESEARCH_START,
            "discovery_end": DISCOVERY_END,
            "validation_start": VALIDATION_START,
            "pre_holdout_end": PRE_HOLDOUT_END,
            "holdout_reserved_from": HOLDOUT_START,
            "indicator_sets": {k: list(v) for k, v in INDICATOR_SETS.items()},
        },
        "aggregate_rules": aggregate_df.to_dict(orient="records"),
        "shortlist": shortlist_df.to_dict(orient="records"),
    }

    (OUTPUT_DIR / "base_anchor_summary.csv").write_text(base_df.to_csv(index=False))
    (OUTPUT_DIR / "anchor_rule_results.csv").write_text(anchor_df.to_csv(index=False))
    (OUTPUT_DIR / "aggregate_rule_summary.csv").write_text(aggregate_df.to_csv(index=False))
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2))

    lines = [
        "# ORB Indicator Long-MA Initial Results",
        "",
        "## Scope",
        "",
        f"- Frozen anchors tested: {len(anchors)}",
        f"- Indicator sets: {len(INDICATOR_SETS)}",
        f"- Discovery: {RESEARCH_START} to {DISCOVERY_END}",
        f"- Validation: {VALIDATION_START} to {PRE_HOLDOUT_END}",
        f"- Holdout still reserved for this branch: {HOLDOUT_START}+",
        "",
        "## Validation Leaders",
        "",
    ]
    top_rows = shortlist_df.head(12) if not shortlist_df.empty else aggregate_df.head(12)
    for _, row in top_rows.iterrows():
        lines.append(
            f"- `{row['overlay_key']}`: val avgR delta {row['validation_delta_avg_r']:+.3f}, "
            f"retention {row['validation_retention']:.1%}, "
            f"val trades {int(row['validation_trades'])}, "
            f"anchors {int(row['positive_validation_anchors'])}/{int(row['eligible_validation_anchors'])}"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")

    print("\nTop long-MA validation overlays:")
    for _, row in top_rows.head(10).iterrows():
        print(
            f"  {row['overlay_key']}: val dAvgR={row['validation_delta_avg_r']:+.3f} | "
            f"ret={row['validation_retention']:.1%} | trades={int(row['validation_trades'])}"
        )
    print(f"\nSpec: {SPEC_PATH}")
    print(f"Report: {REPORT_PATH}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
