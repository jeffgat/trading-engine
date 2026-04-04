#!/usr/bin/env python3
"""Build the frozen ALPHA_V1 downside baseline report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.alpha_v1_downside import (  # noqa: E402
    DEFAULT_HOLDOUT_START,
    OUTPUT_ROOT,
    baseline_trade_streams,
    build_alpha_v1_legs,
    build_drawdown_clusters,
    daily_r_series,
    ensure_daily_index,
    pairwise_overlap,
    portfolio_daily_frame,
    research_packet,
    split_period_metrics,
    strategy_attribution_packet,
    summarize_daily_returns,
    weakest_rolling_windows,
    DataCache,
)


def write_summary(packet: dict, path: Path) -> None:
    baseline = packet["combined_portfolio"]
    lines = [
        "# ALPHA_V1 Downside Baseline",
        "",
        f"- Holdout start: `{packet['holdout_start']}`.",
        f"- Legs: `{', '.join(sorted(packet['legs']))}`.",
        f"- Full total R: `{baseline['metrics']['full']['total_r']}`.",
        f"- Holdout total R: `{baseline['metrics']['holdout']['total_r']}`.",
        f"- Full max DD: `{baseline['metrics']['full']['max_drawdown_r']}`R.",
        f"- Holdout downside-regime net R: `{baseline['regime_attribution']['downside_regime_net_r']['holdout']}`.",
        "",
        "## Weakest Rolling Windows",
        "",
    ]
    for label in ("1m", "3m", "6m"):
        rows = baseline["weakest_rolling_windows"].get(label, [])
        if not rows:
            continue
        worst = rows[0]
        lines.append(
            f"- `{label}` worst: `{worst['start_date']} -> {worst['end_date']}` = `{worst['window_r']}`R."
        )
    lines.extend(
        [
            "",
            "## Deepest Drawdown Clusters",
            "",
        ]
    )
    for row in baseline["drawdown_clusters_top10"][:5]:
        lines.append(
            f"- `{row['start_date']} -> {row['trough_date']}` | DD `{row['drawdown_r']}`R | recovery `{row['recovery_date']}`."
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT / "baseline"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("ALPHA_V1 Downside Baseline")
    print("=" * 72)
    print(f"Output dir: {output_dir}")

    cache = DataCache(start_date=args.start, end_date=args.end)
    legs = build_alpha_v1_legs()
    streams = baseline_trade_streams(cache)

    per_leg = {}
    for key, leg in legs.items():
        market = cache.get(leg.config.instrument)
        per_leg[key] = {
            "config": leg.config.name,
            "metrics": split_period_metrics(streams[key], holdout_start=args.holdout_start),
            "regime_attribution": strategy_attribution_packet(
                streams[key],
                market.regime_calendar,
                holdout_start=args.holdout_start,
            ),
        }
        print(
            f"  {key:<18} "
            f"trades={per_leg[key]['metrics']['full'].get('total_trades', 0):>4} "
            f"netR={per_leg[key]['metrics']['full'].get('total_r', 0.0):>+8.1f}"
        )

    combined_trades = [trade for stream in streams.values() for trade in stream]
    combined_daily = ensure_daily_index(daily_r_series(combined_trades))
    combined_holdout_daily = combined_daily[combined_daily.index >= pd.Timestamp(args.holdout_start)]
    nq_regime = cache.get(legs["nq_ny_lsi_long"].config.instrument).regime_calendar

    packet = {
        "holdout_start": args.holdout_start,
        "start": args.start,
        "end": args.end,
        "legs": sorted(streams),
        "per_leg": per_leg,
        "combined_portfolio": {
            "metrics": {
                "full": summarize_daily_returns(combined_daily),
                "holdout": summarize_daily_returns(combined_holdout_daily),
            },
            "regime_attribution": strategy_attribution_packet(
                combined_trades,
                nq_regime,
                holdout_start=args.holdout_start,
            ),
            "drawdown_clusters_top10": build_drawdown_clusters(combined_daily, top_n=10),
            "weakest_rolling_windows": weakest_rolling_windows(combined_daily, top_n=10),
            "pairwise_trade_overlap": pairwise_overlap(streams),
        },
    }

    (output_dir / "baseline_packet.json").write_text(json.dumps(packet, indent=2))
    write_summary(packet, output_dir / "summary.md")

    overlap_df = pd.DataFrame(packet["combined_portfolio"]["pairwise_trade_overlap"])
    overlap_df.to_csv(output_dir / "pairwise_overlap.csv", index=False)

    daily_df = portfolio_daily_frame(streams)
    daily_df["alpha_v1_total"] = daily_df.sum(axis=1)
    daily_df.to_csv(output_dir / "daily_r.csv")

    print("\nSaved:")
    print(f"  {output_dir / 'baseline_packet.json'}")
    print(f"  {output_dir / 'summary.md'}")
    print(f"  {output_dir / 'pairwise_overlap.csv'}")
    print(f"  {output_dir / 'daily_r.csv'}")


if __name__ == "__main__":
    main()
