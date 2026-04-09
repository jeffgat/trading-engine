#!/usr/bin/env python3
"""Initial ORB indicator-confluence exploration on frozen anchor legs.

This script is intentionally discovery-oriented and Bailey-aware:

- base strategy params are frozen
- 2025-01-01+ holdout is untouched
- discovery happens on 2016-01-01..2022-12-31
- validation happens on 2023-01-01..2024-12-31
- indicator overlays are broad/coarse, not fine-tuned

Execution posture:
- post-trade overlay filtering on actual filled trades
- indicator values taken from the previous completed 5m bar at the fill bar
- distances normalized by prior-day daily ATR

Outputs:
- research spec markdown
- detailed anchor x rule CSV
- aggregate rule summary CSV
- JSON payload
- markdown findings report
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.alpha_v1_downside import (  # noqa: E402
    DataCache,
    build_alpha_v1_legs,
    run_config,
)
from orb_backtest.analysis.regime_research import _regime_lookup  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import CL, ES, GC, NQ, RTY, SI  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.signals.daily_atr import compute_daily_atr  # noqa: E402
from orb_backtest.signals.session import compute_session_days  # noqa: E402
from orb_backtest.signals.vwap import compute_session_vwap  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "results" / "orb_indicator_confluence_exploration"
REPORT_DIR = ROOT / "learnings" / "reports"

RESEARCH_START = "2016-01-01"
DISCOVERY_END = "2022-12-31"
VALIDATION_START = "2023-01-01"
PRE_HOLDOUT_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"

MIN_TRADES_PER_ANCHOR_SEGMENT = 12
MIN_COMBINED_VALIDATION_TRADES = 40
MIN_RETENTION = 0.15
MAX_RETENTION = 0.85

REGIME_AVOID_BUCKETS = ("bull_medium_vol", "sideways_medium_vol")


@dataclass(frozen=True)
class AnchorSpec:
    key: str
    label: str
    source: str
    config: StrategyConfig
    regime_block_buckets: tuple[str, ...] = ()


@dataclass(frozen=True)
class OverlayRule:
    key: str
    family: str
    low: float | None
    high: float | None
    label: str


INDICATOR_SETS: dict[str, tuple[str, ...]] = {
    "vwap": ("vwap",),
    "ema20": ("ema20",),
    "ema50": ("ema50",),
    "sma20": ("sma20",),
    "sma50": ("sma50",),
    "vwap_ema20": ("vwap", "ema20"),
    "vwap_ema50": ("vwap", "ema50"),
    "ema20_ema50": ("ema20", "ema50"),
    "vwap_ema20_ema50": ("vwap", "ema20", "ema50"),
}

RULES: tuple[OverlayRule, ...] = (
    OverlayRule("aligned_near", "aligned", 0.0, 0.20, "aligned 0% to 20% ATR"),
    OverlayRule("aligned_far", "aligned", 0.20, None, "aligned >= 20% ATR"),
    OverlayRule("reversion_near", "reversion", -0.20, 0.0, "reversion -20% to 0% ATR"),
    OverlayRule("reversion_far", "reversion", None, -0.20, "reversion <= -20% ATR"),
)


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _fmt_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    if math.isnan(value) or math.isinf(value):
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _round_metrics(metrics: dict) -> dict:
    keep = {
        "total_trades",
        "win_rate",
        "profit_factor",
        "avg_r",
        "total_r",
        "max_drawdown_r",
        "sharpe_ratio",
        "calmar_ratio",
        "avg_win_r",
        "avg_loss_r",
    }
    out: dict[str, float | int] = {}
    for key in keep:
        value = metrics.get(key)
        if isinstance(value, (int, np.integer)):
            out[key] = int(value)
        elif isinstance(value, (float, np.floating)):
            out[key] = round(float(value), 6)
    return out


def _segment_for_date(date: str) -> str | None:
    if RESEARCH_START <= date <= DISCOVERY_END:
        return "discovery"
    if VALIDATION_START <= date <= PRE_HOLDOUT_END:
        return "validation"
    if date >= HOLDOUT_START:
        return "holdout"
    return None


def build_anchor_specs() -> list[AnchorSpec]:
    alpha = build_alpha_v1_legs()
    anchors = [
        AnchorSpec(
            key="alpha_nq_asia_orb_long",
            label="ALPHA NQ Asia ORB long",
            source="ALPHA_V1",
            config=alpha["nq_asia_orb_long"].config,
        ),
        AnchorSpec(
            key="alpha_es_asia_orb_long",
            label="ALPHA ES Asia ORB long",
            source="ALPHA_V1",
            config=alpha["es_asia_orb_long"].config,
        ),
        AnchorSpec(
            key="alpha_es_ny_orb_long",
            label="ALPHA ES NY ORB long",
            source="ALPHA_V1",
            config=alpha["es_ny_orb_long"].config,
        ),
        AnchorSpec(
            key="gc_asia1_ungated",
            label="GC Asia-1 ungated",
            source="Top Candidates",
            config=StrategyConfig(
                sessions=(SessionConfig(
                    name="Asia",
                    orb_start="20:00",
                    orb_end="20:30",
                    entry_start="20:30",
                    entry_end="23:15",
                    flat_start="04:00",
                    flat_end="07:00",
                    stop_orb_pct=25.0,
                    min_gap_atr_pct=1.0,
                ),),
                instrument=GC,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="both",
                rr=2.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="GC Asia-1 30m ORB25 RR2.5 TP0.6 both",
            ),
        ),
        AnchorSpec(
            key="rty_ny1",
            label="RTY NY-1",
            source="Top Candidates",
            config=StrategyConfig(
                sessions=(SessionConfig(
                    name="NY",
                    orb_start="09:30",
                    orb_end="09:40",
                    entry_start="09:40",
                    entry_end="13:00",
                    flat_start="15:50",
                    flat_end="16:00",
                    stop_orb_pct=75.0,
                    min_gap_atr_pct=1.0,
                ),),
                instrument=RTY,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="both",
                rr=3.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="RTY NY-1 10m ORB75 RR3.5 TP0.6 both",
            ),
        ),
        AnchorSpec(
            key="es_nya_gated",
            label="ES NY-A gated",
            source="Top Candidates",
            config=StrategyConfig(
                sessions=(SessionConfig(
                    name="NY",
                    orb_start="09:30",
                    orb_end="10:15",
                    entry_start="10:15",
                    entry_end="12:00",
                    flat_start="15:50",
                    flat_end="16:00",
                    stop_atr_pct=8.0,
                    min_gap_atr_pct=1.0,
                ),),
                instrument=ES,
                strategy="continuation",
                use_bar_magnifier=False,
                risk_usd=5000.0,
                direction_filter="both",
                rr=3.5,
                tp1_ratio=0.3,
                atr_length=14,
                name="ES NY-A 45m ATR8 RR3.5 TP0.3 both gated",
            ),
            regime_block_buckets=REGIME_AVOID_BUCKETS,
        ),
        AnchorSpec(
            key="nq_asiab_gated",
            label="NQ Asia-B gated",
            source="Top Candidates",
            config=StrategyConfig(
                sessions=(SessionConfig(
                    name="Asia",
                    orb_start="20:00",
                    orb_end="20:15",
                    entry_start="20:15",
                    entry_end="23:15",
                    flat_start="04:00",
                    flat_end="07:00",
                    stop_orb_pct=100.0,
                    min_gap_atr_pct=1.0,
                ),),
                instrument=NQ,
                strategy="continuation",
                use_bar_magnifier=False,
                risk_usd=5000.0,
                direction_filter="long",
                rr=3.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="Asia-B 15m ORB100 RR3.5 TP0.6 gated",
            ),
            regime_block_buckets=REGIME_AVOID_BUCKETS,
        ),
        AnchorSpec(
            key="si_asia1",
            label="SI Asia-1",
            source="Top Candidates",
            config=StrategyConfig(
                sessions=(SessionConfig(
                    name="Asia",
                    orb_start="20:00",
                    orb_end="20:30",
                    entry_start="20:30",
                    entry_end="23:15",
                    flat_start="04:00",
                    flat_end="07:00",
                    stop_orb_pct=75.0,
                    min_gap_atr_pct=1.0,
                ),),
                instrument=SI,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="short",
                rr=2.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="SI Asia-1 30m ORB75 RR2.5 TP0.6 short",
            ),
        ),
        AnchorSpec(
            key="cl_ldn2",
            label="CL LDN-2",
            source="Top Candidates",
            config=StrategyConfig(
                sessions=(SessionConfig(
                    name="LDN",
                    orb_start="03:00",
                    orb_end="03:30",
                    entry_start="03:30",
                    entry_end="07:00",
                    flat_start="08:20",
                    flat_end="08:25",
                    stop_atr_pct=8.0,
                    min_gap_atr_pct=1.0,
                ),),
                instrument=CL,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=3.0,
                tp1_ratio=0.6,
                atr_length=14,
                name="CL LDN-2 30m ATR8 RR3.0 TP0.6 long",
            ),
        ),
    ]
    return anchors


def apply_regime_gate(
    cache: DataCache,
    config: StrategyConfig,
    trades: list[TradeResult],
    blocked_buckets: tuple[str, ...],
) -> list[TradeResult]:
    if not blocked_buckets:
        return trades
    lookup = _regime_lookup(cache.get(config.instrument).regime_calendar, "combined_regime")
    blocked = set(blocked_buckets)
    return [
        t
        for t in trades
        if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in blocked
    ]


def build_indicator_frame(df: pd.DataFrame, session: SessionConfig, atr_length: int) -> pd.DataFrame:
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
    indicator_df["ema20"] = close.ewm(span=20, adjust=False, min_periods=20).mean().shift(1)
    indicator_df["ema50"] = close.ewm(span=50, adjust=False, min_periods=50).mean().shift(1)
    indicator_df["sma20"] = close.rolling(20, min_periods=20).mean().shift(1)
    indicator_df["sma50"] = close.rolling(50, min_periods=50).mean().shift(1)
    return indicator_df


def build_trade_features(
    anchor: AnchorSpec,
    trades: list[TradeResult],
    indicator_df: pd.DataFrame,
) -> tuple[list[TradeResult], pd.DataFrame]:
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
            "segment": _segment_for_date(trade.date),
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "r_multiple": trade.r_multiple,
            "daily_atr": atr,
        }
        for name in ("vwap", "ema20", "ema50", "sma20", "sma50"):
            value = float(row[name]) if pd.notna(row[name]) else np.nan
            feature_row[name] = value
            feature_row[f"dist_{name}"] = (
                float(trade.direction) * (trade.entry_price - value) / atr
                if np.isfinite(value)
                else np.nan
            )
        rows.append(feature_row)
    return filled, pd.DataFrame(rows)


def _rule_mask(frame: pd.DataFrame, component_cols: list[str], rule: OverlayRule) -> pd.Series:
    subset = frame[component_cols]
    mask = pd.Series(True, index=frame.index)
    if rule.low is not None:
        mask &= subset.ge(rule.low).all(axis=1)
    if rule.high is not None:
        mask &= subset.lt(rule.high).all(axis=1)
    return mask


def _metrics_for_segment(trades: Iterable[TradeResult], start: str, end: str) -> dict:
    seg_trades = [t for t in trades if start <= t.date <= end]
    return compute_metrics(seg_trades)


def write_research_spec(path: Path, anchors: list[AnchorSpec]) -> None:
    lines = [
        "# ORB Indicator Confluence Initial Research Spec",
        "",
        "## Objective",
        "",
        "Broad initial exploration of SMA / EMA / VWAP confluence on frozen ORB anchors.",
        "The goal is not parameter optimization. The goal is to detect whether certain broad",
        "distance bands look directionally promising enough to justify deeper follow-up.",
        "",
        "## Bailey Posture",
        "",
        "- Base strategy parameters are frozen.",
        "- 2025-01-01+ remains untouched final holdout.",
        "- Discovery window: 2016-01-01 to 2022-12-31.",
        "- Validation window: 2023-01-01 to 2024-12-31.",
        "- Overlay rules are coarse buckets, not fine sweeps.",
        "- This pass is heuristic. It uses post-trade overlay filtering, not full engine-level",
        "  re-simulation with the overlay integrated into signal generation.",
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
            f"- `{anchor.key}`: {anchor.label} [{anchor.source}]"
            f" | session={anchor.config.sessions[0].name}"
            f" | strategy={anchor.config.strategy}"
            f" | direction={anchor.config.direction_filter}"
            f" | rr={anchor.config.rr}"
            f" | tp1={anchor.config.tp1_ratio}"
            f" | atr_len={anchor.config.atr_length}{gate_note}"
        )
    lines.extend(
        [
            "",
            "## Indicator Set",
            "",
            "- Single indicators: VWAP, EMA20, EMA50, SMA20, SMA50.",
            "- Combo indicators: VWAP+EMA20, VWAP+EMA50, EMA20+EMA50, VWAP+EMA20+EMA50.",
            "- Indicator values are read from the previous completed 5m bar at each trade fill bar.",
            "- All distances are normalized by prior-day daily ATR.",
            "",
            "Signed distance formula:",
            "",
            "```text",
            "signed_dist = direction * (entry_price - indicator_prev) / prev_daily_atr",
            "```",
            "",
            "Interpretation:",
            "",
            "- Positive signed distance = aligned with trade direction.",
            "- Negative signed distance = opposite-side / reversion setup.",
            "",
            "## Overlay Families",
            "",
            "- `aligned_near`: all indicator distances in `[0.0, 0.20)` ATR.",
            "- `aligned_far`: all indicator distances in `[0.20, +inf)` ATR.",
            "- `reversion_near`: all indicator distances in `[-0.20, 0.0)` ATR.",
            "- `reversion_far`: all indicator distances in `(-inf, -0.20)` ATR.",
            "",
            "## Outputs",
            "",
            "- Per-anchor rule table with discovery and validation metrics.",
            "- Aggregate cross-anchor rule table.",
            "- Shortlist candidates only when validation improves average R with acceptable retention.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    anchors = build_anchor_specs()
    spec_path = REPORT_DIR / "ORB_INDICATOR_CONFLUENCE_INITIAL_SPEC.md"
    report_path = REPORT_DIR / "ORB_INDICATOR_CONFLUENCE_INITIAL_RESULTS.md"
    write_research_spec(spec_path, anchors)

    print("ORB indicator confluence exploration")
    print("=" * 70)
    print(f"Anchors: {len(anchors)} | Holdout untouched from {HOLDOUT_START}")

    cache = DataCache(start_date=RESEARCH_START, end_date=PRE_HOLDOUT_END)

    base_segment_trades: dict[str, list[TradeResult]] = {"discovery": [], "validation": []}
    anchor_rows: list[dict[str, object]] = []
    aggregate_store: dict[tuple[str, str], list[TradeResult]] = {}
    base_summary_rows: list[dict[str, object]] = []

    for anchor in anchors:
        print(f"\n[{anchor.key}] Running frozen anchor...")
        trades = run_config(cache, anchor.config, start_date=RESEARCH_START, end_date=PRE_HOLDOUT_END)
        trades = apply_regime_gate(cache, anchor.config, trades, anchor.regime_block_buckets)
        market = cache.get(anchor.config.instrument)
        indicator_df = build_indicator_frame(market.df_5m, anchor.config.sessions[0], anchor.config.atr_length)
        filled, features = build_trade_features(anchor, trades, indicator_df)

        base_disc = _metrics_for_segment(filled, RESEARCH_START, DISCOVERY_END)
        base_val = _metrics_for_segment(filled, VALIDATION_START, PRE_HOLDOUT_END)
        base_summary_rows.append(
            {
                "anchor": anchor.key,
                "label": anchor.label,
                "source": anchor.source,
                "discovery_trades": int(base_disc["total_trades"]),
                "discovery_avg_r": round(float(base_disc["avg_r"]), 6),
                "discovery_pf": round(float(base_disc["profit_factor"]), 6),
                "discovery_total_r": round(float(base_disc["total_r"]), 6),
                "validation_trades": int(base_val["total_trades"]),
                "validation_avg_r": round(float(base_val["avg_r"]), 6),
                "validation_pf": round(float(base_val["profit_factor"]), 6),
                "validation_total_r": round(float(base_val["total_r"]), 6),
            }
        )
        base_segment_trades["discovery"].extend([t for t in filled if RESEARCH_START <= t.date <= DISCOVERY_END])
        base_segment_trades["validation"].extend([t for t in filled if VALIDATION_START <= t.date <= PRE_HOLDOUT_END])

        trade_map = {i: trade for i, trade in enumerate(filled)}
        print(
            f"  Base: discovery {base_disc['total_trades']} trades, avgR={base_disc['avg_r']:.3f} | "
            f"validation {base_val['total_trades']} trades, avgR={base_val['avg_r']:.3f}"
        )

        for indicator_key, components in INDICATOR_SETS.items():
            cols = [f"dist_{name}" for name in components]
            usable = features.dropna(subset=cols)
            if usable.empty:
                continue
            for rule in RULES:
                mask = _rule_mask(usable, cols, rule)
                selected_ids = set(usable.loc[mask, "trade_id"].astype(int).tolist())
                selected = [trade_map[i] for i in sorted(selected_ids)]
                disc_metrics = _metrics_for_segment(selected, RESEARCH_START, DISCOVERY_END)
                val_metrics = _metrics_for_segment(selected, VALIDATION_START, PRE_HOLDOUT_END)
                disc_trades = int(disc_metrics["total_trades"])
                val_trades = int(val_metrics["total_trades"])
                disc_base = int(base_disc["total_trades"])
                val_base = int(base_val["total_trades"])
                disc_ret = disc_trades / disc_base if disc_base else np.nan
                val_ret = val_trades / val_base if val_base else np.nan
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
                        "discovery_retention": round(float(disc_ret), 6) if np.isfinite(disc_ret) else np.nan,
                        "discovery_avg_r": round(float(disc_metrics["avg_r"]), 6),
                        "discovery_pf": round(float(disc_metrics["profit_factor"]), 6),
                        "discovery_total_r": round(float(disc_metrics["total_r"]), 6),
                        "discovery_delta_avg_r": round(float(disc_metrics["avg_r"] - base_disc["avg_r"]), 6),
                        "validation_trades": val_trades,
                        "validation_retention": round(float(val_ret), 6) if np.isfinite(val_ret) else np.nan,
                        "validation_avg_r": round(float(val_metrics["avg_r"]), 6),
                        "validation_pf": round(float(val_metrics["profit_factor"]), 6),
                        "validation_total_r": round(float(val_metrics["total_r"]), 6),
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
    for overlay_key in sorted({row["overlay_key"] for row in anchor_rows}):
        indicator_key, rule_key = overlay_key.split("__", 1)
        indicator_components = ",".join(INDICATOR_SETS[indicator_key])
        rule = next(r for r in RULES if r.key == rule_key)
        disc_metrics = compute_metrics(aggregate_store.get((overlay_key, "discovery"), []))
        val_metrics = compute_metrics(aggregate_store.get((overlay_key, "validation"), []))
        base_disc = compute_metrics(base_segment_trades["discovery"])
        base_val = compute_metrics(base_segment_trades["validation"])

        eligible_disc = anchor_df[
            (anchor_df["overlay_key"] == overlay_key)
            & (anchor_df["discovery_trades"] >= MIN_TRADES_PER_ANCHOR_SEGMENT)
        ]
        eligible_val = anchor_df[
            (anchor_df["overlay_key"] == overlay_key)
            & (anchor_df["validation_trades"] >= MIN_TRADES_PER_ANCHOR_SEGMENT)
        ]

        aggregate_rows.append(
            {
                "overlay_key": overlay_key,
                "indicator_set": indicator_key,
                "components": indicator_components,
                "rule": rule.key,
                "rule_label": rule.label,
                "discovery_trades": int(disc_metrics["total_trades"]),
                "discovery_retention": round(
                    float(disc_metrics["total_trades"] / base_disc["total_trades"]), 6
                ) if base_disc["total_trades"] else np.nan,
                "discovery_avg_r": round(float(disc_metrics["avg_r"]), 6),
                "discovery_pf": round(float(disc_metrics["profit_factor"]), 6),
                "discovery_delta_avg_r": round(float(disc_metrics["avg_r"] - base_disc["avg_r"]), 6),
                "validation_trades": int(val_metrics["total_trades"]),
                "validation_retention": round(
                    float(val_metrics["total_trades"] / base_val["total_trades"]), 6
                ) if base_val["total_trades"] else np.nan,
                "validation_avg_r": round(float(val_metrics["avg_r"]), 6),
                "validation_pf": round(float(val_metrics["profit_factor"]), 6),
                "validation_delta_avg_r": round(float(val_metrics["avg_r"] - base_val["avg_r"]), 6),
                "positive_discovery_anchors": int((eligible_disc["discovery_delta_avg_r"] > 0).sum()),
                "eligible_discovery_anchors": int(len(eligible_disc)),
                "positive_validation_anchors": int((eligible_val["validation_delta_avg_r"] > 0).sum()),
                "eligible_validation_anchors": int(len(eligible_val)),
                "median_validation_delta_avg_r": round(
                    float(eligible_val["validation_delta_avg_r"].median()), 6
                ) if not eligible_val.empty else np.nan,
            }
        )

    aggregate_df = pd.DataFrame(aggregate_rows).sort_values(
        by=["validation_delta_avg_r", "positive_validation_anchors", "validation_trades"],
        ascending=[False, False, False],
    )

    shortlist_df = aggregate_df[
        (aggregate_df["validation_trades"] >= MIN_COMBINED_VALIDATION_TRADES)
        & (aggregate_df["validation_retention"] >= MIN_RETENTION)
        & (aggregate_df["validation_retention"] <= MAX_RETENTION)
        & (aggregate_df["validation_delta_avg_r"] > 0)
        & (aggregate_df["positive_validation_anchors"] >= 3)
    ].copy()
    shortlist_df = shortlist_df.sort_values(
        by=["validation_delta_avg_r", "positive_validation_anchors", "validation_trades"],
        ascending=[False, False, False],
    )

    best_per_anchor = (
        anchor_df[anchor_df["validation_trades"] >= MIN_TRADES_PER_ANCHOR_SEGMENT]
        .sort_values(by=["anchor", "validation_delta_avg_r", "validation_trades"], ascending=[True, False, False])
        .groupby("anchor", as_index=False)
        .head(1)
    )

    base_disc = compute_metrics(base_segment_trades["discovery"])
    base_val = compute_metrics(base_segment_trades["validation"])

    payload = {
        "meta": {
            "research_start": RESEARCH_START,
            "discovery_end": DISCOVERY_END,
            "validation_start": VALIDATION_START,
            "pre_holdout_end": PRE_HOLDOUT_END,
            "holdout_start": HOLDOUT_START,
            "indicator_sets": {k: list(v) for k, v in INDICATOR_SETS.items()},
            "rules": [rule.__dict__ for rule in RULES],
            "note": (
                "Heuristic initial exploration only. Uses post-trade overlay filtering on filled trades; "
                "holdout 2025-01-01+ untouched."
            ),
        },
        "base_combined": {
            "discovery": _round_metrics(base_disc),
            "validation": _round_metrics(base_val),
        },
        "anchors": base_summary_rows,
        "aggregate_rules": aggregate_df.to_dict(orient="records"),
        "shortlist": shortlist_df.to_dict(orient="records"),
        "best_per_anchor": best_per_anchor.to_dict(orient="records"),
    }

    (OUTPUT_DIR / "base_anchor_summary.csv").write_text(base_df.to_csv(index=False))
    (OUTPUT_DIR / "anchor_rule_results.csv").write_text(anchor_df.to_csv(index=False))
    (OUTPUT_DIR / "aggregate_rule_summary.csv").write_text(aggregate_df.to_csv(index=False))
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2))

    report_lines = [
        "# ORB Indicator Confluence Initial Results",
        "",
        "## Scope",
        "",
        f"- Frozen anchors tested: {len(anchors)}",
        f"- Discovery: {RESEARCH_START} to {DISCOVERY_END}",
        f"- Validation: {VALIDATION_START} to {PRE_HOLDOUT_END}",
        f"- Holdout untouched: {HOLDOUT_START}+",
        "- Method: post-trade overlay filter on filled trades using prior-bar indicator states.",
        "- Important: these results are heuristic and are not yet full engine-level reruns.",
        "",
        "## Combined Base Book",
        "",
        f"- Discovery: {base_disc['total_trades']} trades | avgR={_fmt_num(base_disc['avg_r'], 3)} | "
        f"PF={_fmt_num(base_disc['profit_factor'], 2)} | totalR={_fmt_num(base_disc['total_r'], 1)}",
        f"- Validation: {base_val['total_trades']} trades | avgR={_fmt_num(base_val['avg_r'], 3)} | "
        f"PF={_fmt_num(base_val['profit_factor'], 2)} | totalR={_fmt_num(base_val['total_r'], 1)}",
        "",
        "## Validation Leaders",
        "",
    ]

    top_rows = shortlist_df.head(10) if not shortlist_df.empty else aggregate_df.head(10)
    if top_rows.empty:
        report_lines.append("- No overlay met the minimum shortlist criteria.")
    else:
        for _, row in top_rows.iterrows():
            report_lines.append(
                f"- `{row['overlay_key']}`: val avgR delta {row['validation_delta_avg_r']:+.3f}, "
                f"retention {_fmt_pct(row['validation_retention'])}, "
                f"val trades {int(row['validation_trades'])}, "
                f"positive anchors {int(row['positive_validation_anchors'])}/{int(row['eligible_validation_anchors'])}"
            )

    report_lines.extend(["", "## Best Rule Per Anchor", ""])
    if best_per_anchor.empty:
        report_lines.append("- No anchor-level overlay cleared the minimum validation trade threshold.")
    else:
        for _, row in best_per_anchor.iterrows():
            report_lines.append(
                f"- `{row['anchor']}`: `{row['overlay_key']}` | "
                f"val avgR delta {row['validation_delta_avg_r']:+.3f} | "
                f"retention {_fmt_pct(row['validation_retention'])} | "
                f"val trades {int(row['validation_trades'])}"
            )

    report_lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Positive results here are promotion candidates for a second pass only.",
            "- Second pass should rerun a very small frozen shortlist as true engine-level entry filters,",
            "  then walk-forward again before touching the final holdout.",
            "",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n")

    print("\nTop validation overlays:")
    preview = top_rows.head(8)
    if preview.empty:
        print("  None.")
    else:
        for _, row in preview.iterrows():
            print(
                f"  {row['overlay_key']}: val dAvgR={row['validation_delta_avg_r']:+.3f} | "
                f"ret={row['validation_retention']:.1%} | "
                f"trades={int(row['validation_trades'])} | "
                f"anchors={int(row['positive_validation_anchors'])}/{int(row['eligible_validation_anchors'])}"
            )

    print(f"\nWrote spec: {spec_path}")
    print(f"Wrote report: {report_path}")
    print(f"Output dir: {OUTPUT_DIR}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
