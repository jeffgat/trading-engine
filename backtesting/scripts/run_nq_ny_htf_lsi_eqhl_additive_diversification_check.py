#!/usr/bin/env python3
"""Diversification check for incumbent additive HTF-LSI vs wide additive EQHL challenger."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import HOLDOUT_START, build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data  # noqa: E402
from orb_backtest.analysis.alpha_v1_downside import (  # noqa: E402
    daily_r_series,
    pairwise_overlap,
    portfolio_daily_frame,
    summarize_daily_returns,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_eqhl_additive_diversification_check"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_EQHL_ADDITIVE_DIVERSIFICATION_CHECK.md"
WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def split_trades(trades, *, holdout_start: str = HOLDOUT_START) -> dict[str, list]:
    return {
        "full": list(trades),
        "pre_holdout": [trade for trade in trades if trade.date < holdout_start],
        "holdout": [trade for trade in trades if trade.date >= holdout_start],
    }


def split_series(series: pd.Series, *, holdout_start: str = HOLDOUT_START) -> dict[str, pd.Series]:
    ts = pd.Timestamp(holdout_start)
    return {
        "full": series,
        "pre_holdout": series[series.index < ts],
        "holdout": series[series.index >= ts],
    }


def build_candidates():
    incumbent = replace(
        build_current_nq_ny_htf_lsi_lag24_config(
            name="NQ NY HTF_LSI 5m lag24 operating lead",
        ),
        htf_lsi_include_eqhl_levels=True,
        eqhl_level_tf_minutes=15,
        eqhl_n_left=2,
        eqhl_tolerance_ticks=1,
        eqhl_min_touches=2,
        eqhl_lookback_bars=48,
        name="NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 incumbent",
    )
    challenger = replace(
        build_current_nq_ny_htf_lsi_lag24_config(
            name="NQ NY HTF_LSI 5m lag24 + EQHL60m 15pt",
        ),
        htf_lsi_include_eqhl_levels=True,
        eqhl_level_tf_minutes=60,
        eqhl_n_left=2,
        eqhl_tolerance_ticks=60,
        eqhl_min_touches=2,
        eqhl_lookback_bars=48,
        name="NQ NY HTF_LSI 5m lag24 + EQHL60m 15pt challenger",
    )
    return {
        "incumbent": incumbent,
        "challenger": challenger,
    }


def blend_metrics(daily_inc: pd.Series, daily_chal: pd.Series) -> list[dict]:
    rows = []
    split_inc = split_series(daily_inc)
    split_chal = split_series(daily_chal)
    for challenger_weight in WEIGHTS:
        incumbent_weight = 1.0 - challenger_weight
        combo = (
            daily_inc.reindex(daily_inc.index.union(daily_chal.index), fill_value=0.0) * incumbent_weight
            + daily_chal.reindex(daily_inc.index.union(daily_chal.index), fill_value=0.0) * challenger_weight
        ).sort_index()
        split_combo = split_series(combo)
        rows.append(
            {
                "incumbent_weight": incumbent_weight,
                "challenger_weight": challenger_weight,
                "full": summarize_daily_returns(split_combo["full"]),
                "pre_holdout": summarize_daily_returns(split_combo["pre_holdout"]),
                "holdout": summarize_daily_returns(split_combo["holdout"]),
                "incumbent_only_holdout": summarize_daily_returns(split_inc["holdout"]),
                "challenger_only_holdout": summarize_daily_returns(split_chal["holdout"]),
            }
        )
    return rows


def write_report(payload: dict) -> None:
    full_overlap = payload["overlap"]["full"][0]
    pre_overlap = payload["overlap"]["pre_holdout"][0]
    holdout_overlap = payload["overlap"]["holdout"][0]
    lines = [
        "# NQ NY HTF-LSI Additive Diversification Check",
        "",
        "- Objective: test whether the wide additive `60m EQHL 15pt` challenger deserves a backup/diversification slot next to the incumbent `15m EQHL tol1` additive lead.",
        "- Method: rerun both frozen `5m lag24` additive branches, measure trade-date overlap and daily-R correlation, then test constant-gross-risk blends where incumbent weight + challenger weight = 1.0.",
        f"- Holdout split: `{HOLDOUT_START}` onward.",
        "",
        "## Overlap",
        "",
        f"- Full sample: shared trade dates `{full_overlap['shared_trade_dates']}`, Jaccard `{full_overlap['jaccard_overlap']:.3f}`, daily-R correlation `{full_overlap['daily_r_correlation']}`.",
        f"- Pre-holdout: shared trade dates `{pre_overlap['shared_trade_dates']}`, Jaccard `{pre_overlap['jaccard_overlap']:.3f}`, daily-R correlation `{pre_overlap['daily_r_correlation']}`.",
        f"- Holdout: shared trade dates `{holdout_overlap['shared_trade_dates']}`, Jaccard `{holdout_overlap['jaccard_overlap']:.3f}`, daily-R correlation `{holdout_overlap['daily_r_correlation']}`.",
        "",
        "## Constant-Risk Blend Sweep",
        "",
        "| Inc Weight | Chal Weight | Pre Total R | Pre DD | Pre Calmar | Holdout Total R | Holdout DD | Holdout Calmar |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["blend_rows"]:
        lines.append(
            f"| {row['incumbent_weight']:.2f} | {row['challenger_weight']:.2f} | "
            f"{row['pre_holdout']['total_r']:.2f} | {row['pre_holdout']['max_drawdown_r']:.2f} | {row['pre_holdout']['calmar_ratio']:.2f} | "
            f"{row['holdout']['total_r']:.2f} | {row['holdout']['max_drawdown_r']:.2f} | {row['holdout']['calmar_ratio']:.2f} |"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configs = build_candidates()
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, list(configs.values()), signal_df_1m=signal_df_1m)

    streams = {}
    for label, config in configs.items():
        print(f"Running {label}...", flush=True)
        streams[label] = run_backtest(
            df_base,
            config,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )

    overlap = {
        "full": pairwise_overlap({key: value for key, value in streams.items()}),
        "pre_holdout": pairwise_overlap({key: split_trades(value)["pre_holdout"] for key, value in streams.items()}),
        "holdout": pairwise_overlap({key: split_trades(value)["holdout"] for key, value in streams.items()}),
    }

    daily = portfolio_daily_frame(streams)
    daily_inc = daily["incumbent"] if "incumbent" in daily else daily_r_series(streams["incumbent"])
    daily_chal = daily["challenger"] if "challenger" in daily else daily_r_series(streams["challenger"])
    blend_rows = blend_metrics(daily_inc, daily_chal)

    payload = {
        "overlap": overlap,
        "blend_rows": blend_rows,
    }
    (OUTPUT_DIR / "diversification_check.json").write_text(json.dumps(payload, indent=2, default=str))
    write_report(payload)
    print(f"Saved diversification check to {OUTPUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
