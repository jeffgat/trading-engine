#!/usr/bin/env python3
"""Follow-up threshold pass for long-horizon MA confluence candidates."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import run_orb_indicator_long_ma_exploration as phase1  # noqa: E402

from orb_backtest.analysis.alpha_v1_downside import DataCache, run_config  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "results" / "orb_indicator_long_ma_followup"
REPORT_PATH = ROOT / "learnings" / "reports" / "ORB_INDICATOR_LONG_MA_FOLLOWUP_RESULTS.md"

ROLLING_WINDOW_MONTHS = 6
ROLLING_STEP_MONTHS = 3
MIN_ANCHOR_TRADES = 12
MIN_WINDOW_TRADES = 20
SELECT_TOP_INDICATOR_SETS = 8


@dataclass(frozen=True)
class Candidate:
    indicator_key: str
    components: tuple[str, ...]
    upper: float

    @property
    def overlay_key(self) -> str:
        return f"{self.indicator_key}__aligned_0_{int(round(self.upper * 100)):02d}"

    @property
    def label(self) -> str:
        return f"{self.indicator_key} aligned [0,{self.upper:.2f}) ATR"


def load_indicator_candidates() -> list[Candidate]:
    df = pd.read_csv(phase1.OUTPUT_DIR / "aggregate_rule_summary.csv")
    aligned = df[
        (df["rule"] == "aligned_near")
        & (df["validation_trades"] >= 40)
        & (df["validation_delta_avg_r"] > 0)
        & (df["positive_validation_anchors"] >= 3)
    ].copy()
    aligned = aligned.sort_values(
        by=["validation_delta_avg_r", "positive_validation_anchors", "validation_retention"],
        ascending=[False, False, False],
    )
    selected = (
        aligned.drop_duplicates(subset=["indicator_set"])
        .head(SELECT_TOP_INDICATOR_SETS)
        [["indicator_set", "components"]]
        .to_dict(orient="records")
    )
    candidates: list[Candidate] = []
    for row in selected:
        components = tuple(str(row["components"]).split(","))
        for upper in (0.10, 0.15, 0.20, 0.25, 0.30):
            candidates.append(Candidate(str(row["indicator_set"]), components, upper))
    return candidates


def segment_metrics(trades: list[TradeResult], start: str, end: str) -> dict:
    return compute_metrics([t for t in trades if start <= t.date <= end and t.exit_type != EXIT_NO_FILL])


def rolling_windows(start: str, end: str, window_months: int, step_months: int) -> list[tuple[str, str]]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    out: list[tuple[str, str]] = []
    current = start_ts
    while current < end_ts:
        win_end = current + pd.DateOffset(months=window_months) - pd.Timedelta(days=1)
        if win_end > end_ts:
            break
        out.append((current.strftime("%Y-%m-%d"), win_end.strftime("%Y-%m-%d")))
        current = current + pd.DateOffset(months=step_months)
    return out


def candidate_mask(frame: pd.DataFrame, components: tuple[str, ...], upper: float) -> pd.Series:
    cols = [f"dist_{name}" for name in components]
    subset = frame[cols]
    return subset.ge(0.0).all(axis=1) & subset.lt(upper).all(axis=1)


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = load_indicator_candidates()
    anchors = phase1.build_anchor_specs()
    cache = DataCache(start_date=phase1.RESEARCH_START, end_date=phase1.PRE_HOLDOUT_END)
    windows = rolling_windows(
        phase1.RESEARCH_START,
        phase1.PRE_HOLDOUT_END,
        ROLLING_WINDOW_MONTHS,
        ROLLING_STEP_MONTHS,
    )

    print("ORB long-MA follow-up")
    print("=" * 70)
    print(f"Indicator-set finalists: {len(set(c.indicator_key for c in candidates))}")

    anchor_candidate_rows: list[dict[str, object]] = []
    combined_base_discovery: list[TradeResult] = []
    combined_base_validation: list[TradeResult] = []
    combined_candidate_streams: dict[tuple[str, str], list[TradeResult]] = {}
    per_candidate_window_rows: list[dict[str, object]] = []

    for anchor in anchors:
        print(f"[{anchor.key}] Frozen rerun...")
        trades = run_config(cache, anchor.config, start_date=phase1.RESEARCH_START, end_date=phase1.PRE_HOLDOUT_END)
        trades = phase1.apply_regime_gate(cache, anchor.config, trades, anchor.regime_block_buckets)
        market = cache.get(anchor.config.instrument)
        indicator_df = phase1.build_indicator_frame(market.df_5m, anchor.config.sessions[0], anchor.config.atr_length)
        filled, features = phase1.build_trade_features(anchor, trades, indicator_df)
        trade_map = {i: trade for i, trade in enumerate(filled)}

        base_disc = segment_metrics(filled, phase1.RESEARCH_START, phase1.DISCOVERY_END)
        base_val = segment_metrics(filled, phase1.VALIDATION_START, phase1.PRE_HOLDOUT_END)
        combined_base_discovery.extend([t for t in filled if phase1.RESEARCH_START <= t.date <= phase1.DISCOVERY_END])
        combined_base_validation.extend([t for t in filled if phase1.VALIDATION_START <= t.date <= phase1.PRE_HOLDOUT_END])

        for candidate in candidates:
            cols = [f"dist_{name}" for name in candidate.components]
            usable = features.dropna(subset=cols)
            if usable.empty:
                continue
            mask = candidate_mask(usable, candidate.components, candidate.upper)
            trade_ids = sorted(set(usable.loc[mask, "trade_id"].astype(int).tolist()))
            selected = [trade_map[i] for i in trade_ids]

            disc = segment_metrics(selected, phase1.RESEARCH_START, phase1.DISCOVERY_END)
            val = segment_metrics(selected, phase1.VALIDATION_START, phase1.PRE_HOLDOUT_END)
            anchor_candidate_rows.append(
                {
                    "anchor": anchor.key,
                    "overlay_key": candidate.overlay_key,
                    "candidate_label": candidate.label,
                    "indicator_key": candidate.indicator_key,
                    "components": ",".join(candidate.components),
                    "upper": candidate.upper,
                    "discovery_trades": int(disc["total_trades"]),
                    "discovery_retention": round(
                        float(disc["total_trades"] / base_disc["total_trades"]), 6
                    ) if base_disc["total_trades"] else np.nan,
                    "discovery_avg_r": round(float(disc["avg_r"]), 6),
                    "discovery_delta_avg_r": round(float(disc["avg_r"] - base_disc["avg_r"]), 6),
                    "validation_trades": int(val["total_trades"]),
                    "validation_retention": round(
                        float(val["total_trades"] / base_val["total_trades"]), 6
                    ) if base_val["total_trades"] else np.nan,
                    "validation_avg_r": round(float(val["avg_r"]), 6),
                    "validation_delta_avg_r": round(float(val["avg_r"] - base_val["avg_r"]), 6),
                }
            )

            combined_candidate_streams.setdefault((candidate.overlay_key, "discovery"), []).extend(
                [t for t in selected if phase1.RESEARCH_START <= t.date <= phase1.DISCOVERY_END]
            )
            combined_candidate_streams.setdefault((candidate.overlay_key, "validation"), []).extend(
                [t for t in selected if phase1.VALIDATION_START <= t.date <= phase1.PRE_HOLDOUT_END]
            )

            for window_start, window_end in windows:
                base_win = segment_metrics(filled, window_start, window_end)
                cand_win = segment_metrics(selected, window_start, window_end)
                if int(base_win["total_trades"]) < MIN_WINDOW_TRADES:
                    continue
                per_candidate_window_rows.append(
                    {
                        "anchor": anchor.key,
                        "overlay_key": candidate.overlay_key,
                        "window_start": window_start,
                        "window_end": window_end,
                        "base_trades": int(base_win["total_trades"]),
                        "cand_trades": int(cand_win["total_trades"]),
                        "delta_avg_r": round(float(cand_win["avg_r"] - base_win["avg_r"]), 6),
                    }
                )

    base_disc = compute_metrics(combined_base_discovery)
    base_val = compute_metrics(combined_base_validation)
    anchor_candidate_df = pd.DataFrame(anchor_candidate_rows)
    window_df = pd.DataFrame(per_candidate_window_rows)

    aggregate_rows: list[dict[str, object]] = []
    for candidate in candidates:
        overlay_key = candidate.overlay_key
        disc = compute_metrics(combined_candidate_streams.get((overlay_key, "discovery"), []))
        val = compute_metrics(combined_candidate_streams.get((overlay_key, "validation"), []))
        anchor_sub = anchor_candidate_df[anchor_candidate_df["overlay_key"] == overlay_key]
        eligible_val = anchor_sub[anchor_sub["validation_trades"] >= MIN_ANCHOR_TRADES]
        win_sub = window_df[window_df["overlay_key"] == overlay_key]
        eligible_windows = win_sub[win_sub["cand_trades"] >= MIN_ANCHOR_TRADES]
        pos_windows = int((eligible_windows["delta_avg_r"] > 0).sum()) if not eligible_windows.empty else 0
        total_windows = int(len(eligible_windows))
        aggregate_rows.append(
            {
                "overlay_key": overlay_key,
                "candidate_label": candidate.label,
                "indicator_key": candidate.indicator_key,
                "components": ",".join(candidate.components),
                "upper": candidate.upper,
                "validation_trades": int(val["total_trades"]),
                "validation_retention": round(
                    float(val["total_trades"] / base_val["total_trades"]), 6
                ) if base_val["total_trades"] else np.nan,
                "validation_avg_r": round(float(val["avg_r"]), 6),
                "validation_delta_avg_r": round(float(val["avg_r"] - base_val["avg_r"]), 6),
                "positive_validation_anchors": int((eligible_val["validation_delta_avg_r"] > 0).sum()),
                "eligible_validation_anchors": int(len(eligible_val)),
                "positive_window_count": pos_windows,
                "eligible_window_count": total_windows,
                "positive_window_pct": round(float(pos_windows / total_windows), 6) if total_windows else np.nan,
            }
        )

    aggregate_df = pd.DataFrame(aggregate_rows).sort_values(
        by=["validation_delta_avg_r", "positive_validation_anchors", "positive_window_pct"],
        ascending=[False, False, False],
    )

    best_by_indicator = (
        aggregate_df.sort_values(
            by=["indicator_key", "validation_delta_avg_r", "positive_window_pct"],
            ascending=[True, False, False],
        )
        .groupby("indicator_key", as_index=False)
        .head(1)
    )

    (OUTPUT_DIR / "anchor_candidate_results.csv").write_text(anchor_candidate_df.to_csv(index=False))
    (OUTPUT_DIR / "rolling_window_results.csv").write_text(window_df.to_csv(index=False))
    (OUTPUT_DIR / "aggregate_summary.csv").write_text(aggregate_df.to_csv(index=False))
    summary = {
        "selected_indicator_sets": sorted(set(c.indicator_key for c in candidates)),
        "best_by_indicator": best_by_indicator.to_dict(orient="records"),
        "aggregate_summary": aggregate_df.to_dict(orient="records"),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "# ORB Indicator Long-MA Follow-Up",
        "",
        "## Scope",
        "",
        f"- Indicator-set finalists from initial pass: {', '.join(sorted(set(c.indicator_key for c in candidates)))}",
        "- Upper bounds tested: 10%, 15%, 20%, 25%, 30% ATR.",
        "- Holdout still untouched for this branch.",
        "",
        "## Best By Indicator",
        "",
    ]
    for _, row in best_by_indicator.iterrows():
        lines.append(
            f"- `{row['overlay_key']}`: val avgR delta {row['validation_delta_avg_r']:+.3f}, "
            f"retention {row['validation_retention']:.1%}, "
            f"pos anchors {int(row['positive_validation_anchors'])}/{int(row['eligible_validation_anchors'])}, "
            f"pos windows {int(row['positive_window_count'])}/{int(row['eligible_window_count'])}"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")

    print("\nTop long-MA follow-up candidates:")
    for _, row in aggregate_df.head(10).iterrows():
        print(
            f"  {row['overlay_key']}: val dAvgR={row['validation_delta_avg_r']:+.3f} | "
            f"ret={row['validation_retention']:.1%} | "
            f"windows={int(row['positive_window_count'])}/{int(row['eligible_window_count'])}"
        )
    print(f"\nReport: {REPORT_PATH}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
