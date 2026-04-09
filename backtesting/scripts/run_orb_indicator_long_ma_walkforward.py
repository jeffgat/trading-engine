#!/usr/bin/env python3
"""Walk-forward ranking for shortlisted long-horizon MA overlays."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_orb_indicator_long_ma_exploration as base_exp  # noqa: E402
import run_orb_indicator_long_ma_followup as followup  # noqa: E402

from orb_backtest.analysis.alpha_v1_downside import DataCache, run_config  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "results" / "orb_indicator_long_ma_walkforward"
REPORT_PATH = ROOT / "learnings" / "reports" / "ORB_INDICATOR_LONG_MA_WALKFORWARD.md"

START_DATE = "2016-01-01"
END_DATE = "2024-12-31"
HOLDOUT_START = "2025-01-01"

IS_MONTHS = 12
OOS_MONTHS = 3
STEP_MONTHS = 3
MIN_COMBINED_OOS_TRADES = 40
SHORTLIST_SIZE = 4


@dataclass(frozen=True)
class Candidate:
    overlay_key: str
    label: str
    components: tuple[str, ...]
    low: float
    high: float


def load_candidates() -> list[Candidate]:
    df = pd.read_csv(followup.OUTPUT_DIR / "aggregate_summary.csv")
    df = df[
        (df["validation_trades"] >= 40)
        & (df["validation_delta_avg_r"] > 0)
        & (df["positive_validation_anchors"] >= 3)
    ].copy()
    df = df.sort_values(
        by=["validation_delta_avg_r", "positive_window_pct", "validation_retention"],
        ascending=[False, False, False],
    ).head(SHORTLIST_SIZE)
    candidates: list[Candidate] = []
    for _, row in df.iterrows():
        candidates.append(
            Candidate(
                overlay_key=str(row["overlay_key"]),
                label=str(row["candidate_label"]),
                components=tuple(str(row["components"]).split(",")),
                low=0.0,
                high=float(row["upper"]),
            )
        )
    return candidates


def window_ranges(
    start_date: str,
    end_date: str,
    is_months: int,
    oos_months: int,
    step_months: int,
) -> list[tuple[str, str, str, str]]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    out: list[tuple[str, str, str, str]] = []
    current = start
    while current + pd.DateOffset(months=is_months + oos_months) <= end + pd.Timedelta(days=1):
        is_start = current
        is_end = current + pd.DateOffset(months=is_months) - pd.Timedelta(days=1)
        oos_start = is_end + pd.Timedelta(days=1)
        oos_end = oos_start + pd.DateOffset(months=oos_months) - pd.Timedelta(days=1)
        out.append((
            is_start.strftime("%Y-%m-%d"),
            is_end.strftime("%Y-%m-%d"),
            oos_start.strftime("%Y-%m-%d"),
            oos_end.strftime("%Y-%m-%d"),
        ))
        current = current + pd.DateOffset(months=step_months)
    return out


def candidate_mask(frame: pd.DataFrame, components: tuple[str, ...], low: float, high: float) -> pd.Series:
    cols = [f"dist_{name}" for name in components]
    subset = frame[cols]
    return subset.ge(low).all(axis=1) & subset.lt(high).all(axis=1)


def score_candidate(metrics: dict) -> tuple[float, float, int]:
    return (
        float(metrics.get("avg_r", 0.0)),
        float(metrics.get("profit_factor", 0.0)),
        int(metrics.get("total_trades", 0)),
    )


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = load_candidates()
    anchors = base_exp.build_anchor_specs()
    cache = DataCache(start_date=START_DATE, end_date=END_DATE)

    print("ORB indicator long-MA walk-forward")
    print("=" * 70)
    print(f"Candidates: {len(candidates)} | Holdout untouched from {HOLDOUT_START}")

    anchor_trade_maps: dict[str, dict[int, TradeResult]] = {}
    anchor_features: dict[str, pd.DataFrame] = {}
    anchor_candidate_trades: dict[str, dict[str, list[TradeResult]]] = {}

    for anchor in anchors:
        print(f"[{anchor.key}] Preparing anchor stream...")
        trades = run_config(cache, anchor.config, start_date=START_DATE, end_date=END_DATE)
        trades = base_exp.apply_regime_gate(cache, anchor.config, trades, anchor.regime_block_buckets)
        market = cache.get(anchor.config.instrument)
        indicator_df = base_exp.build_indicator_frame(market.df_5m, anchor.config.sessions[0], anchor.config.atr_length)
        filled, features = base_exp.build_trade_features(anchor, trades, indicator_df)
        trade_map = {i: trade for i, trade in enumerate(filled)}
        anchor_trade_maps[anchor.key] = trade_map
        anchor_features[anchor.key] = features
        anchor_candidate_trades[anchor.key] = {}
        for candidate in candidates:
            cols = [f"dist_{name}" for name in candidate.components]
            usable = features.dropna(subset=cols)
            mask = candidate_mask(usable, candidate.components, candidate.low, candidate.high)
            ids = sorted(set(usable.loc[mask, "trade_id"].astype(int).tolist()))
            anchor_candidate_trades[anchor.key][candidate.overlay_key] = [trade_map[i] for i in ids]

    folds = window_ranges(START_DATE, END_DATE, IS_MONTHS, OOS_MONTHS, STEP_MONTHS)
    fold_rows: list[dict[str, object]] = []
    selected_oos_streams: list[TradeResult] = []
    fixed_oos_streams: dict[str, list[TradeResult]] = {c.overlay_key: [] for c in candidates}

    for fold_idx, (is_start, is_end, oos_start, oos_end) in enumerate(folds, start=1):
        candidate_scores = []
        for candidate in candidates:
            combined_is: list[TradeResult] = []
            combined_oos: list[TradeResult] = []
            for anchor in anchors:
                combined_is.extend([
                    t for t in anchor_candidate_trades[anchor.key][candidate.overlay_key]
                    if is_start <= t.date <= is_end
                ])
                combined_oos.extend([
                    t for t in anchor_candidate_trades[anchor.key][candidate.overlay_key]
                    if oos_start <= t.date <= oos_end
                ])
            is_metrics = compute_metrics(combined_is)
            oos_metrics = compute_metrics(combined_oos)
            candidate_scores.append((candidate, is_metrics, oos_metrics))
            fixed_oos_streams[candidate.overlay_key].extend(combined_oos)

        viable = [row for row in candidate_scores if int(row[2].get("total_trades", 0)) >= MIN_COMBINED_OOS_TRADES]
        ranking_pool = viable if viable else candidate_scores
        best_candidate, best_is, best_oos = max(ranking_pool, key=lambda row: score_candidate(row[1]))
        selected_oos_streams.extend([
            t
            for anchor in anchors
            for t in anchor_candidate_trades[anchor.key][best_candidate.overlay_key]
            if oos_start <= t.date <= oos_end
        ])
        fold_rows.append(
            {
                "fold": fold_idx,
                "selected_overlay": best_candidate.overlay_key,
                "is_start": is_start,
                "is_end": is_end,
                "oos_start": oos_start,
                "oos_end": oos_end,
                "selected_is_avg_r": round(float(best_is["avg_r"]), 6),
                "selected_oos_avg_r": round(float(best_oos["avg_r"]), 6),
                "selected_oos_trades": int(best_oos["total_trades"]),
            }
        )

    fixed_rows: list[dict[str, object]] = []
    for candidate in candidates:
        oos_metrics = compute_metrics(fixed_oos_streams[candidate.overlay_key])
        fixed_rows.append(
            {
                "overlay_key": candidate.overlay_key,
                "label": candidate.label,
                "components": ",".join(candidate.components),
                "low": candidate.low,
                "high": candidate.high,
                "oos_trades": int(oos_metrics["total_trades"]),
                "oos_avg_r": round(float(oos_metrics["avg_r"]), 6),
                "oos_pf": round(float(oos_metrics["profit_factor"]), 6),
                "oos_total_r": round(float(oos_metrics["total_r"]), 6),
                "oos_sharpe": round(float(oos_metrics["sharpe_ratio"]), 6),
                "oos_max_dd_r": round(float(oos_metrics["max_drawdown_r"]), 6),
            }
        )

    fixed_df = pd.DataFrame(fixed_rows).sort_values(
        by=["oos_avg_r", "oos_pf", "oos_total_r"],
        ascending=[False, False, False],
    )
    selected_oos_metrics = compute_metrics(selected_oos_streams)

    (OUTPUT_DIR / "fold_rows.csv").write_text(pd.DataFrame(fold_rows).to_csv(index=False))
    (OUTPUT_DIR / "fixed_oos_summary.csv").write_text(fixed_df.to_csv(index=False))
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(
        {
            "candidates": [c.overlay_key for c in candidates],
            "selected_oos_metrics": {
                "total_trades": int(selected_oos_metrics["total_trades"]),
                "avg_r": round(float(selected_oos_metrics["avg_r"]), 6),
                "profit_factor": round(float(selected_oos_metrics["profit_factor"]), 6),
                "total_r": round(float(selected_oos_metrics["total_r"]), 6),
            },
        },
        indent=2,
    ))

    lines = [
        "# ORB Indicator Long-MA Walk-Forward",
        "",
        "## Candidate Overlays",
        "",
    ]
    for candidate in candidates:
        lines.append(f"- `{candidate.overlay_key}`")
    lines.extend(["", "## Fixed OOS Ranking", ""])
    for _, row in fixed_df.iterrows():
        lines.append(
            f"- `{row['overlay_key']}`: oos avgR={row['oos_avg_r']:.3f}, PF={row['oos_pf']:.2f}, "
            f"trades={int(row['oos_trades'])}, totalR={row['oos_total_r']:.1f}"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")

    print("\nFixed OOS ranking:")
    for _, row in fixed_df.iterrows():
        print(
            f"  {row['overlay_key']}: avgR={row['oos_avg_r']:.3f} | "
            f"PF={row['oos_pf']:.2f} | trades={int(row['oos_trades'])}"
        )
    print(f"\nReport: {REPORT_PATH}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
