#!/usr/bin/env python3
"""Search for orthogonal companions against the current NQ NY HTF-LSI lead.

Candidate pool mixes:
- serious nearby NQ challengers from the current research tree
- the additive EQHL branch
- existing ALPHA_V1 baseline portfolio legs for contrast

Ranking emphasizes:
- low trade-date overlap / low daily-R correlation vs the lead
- positive standalone quality
- positive 50/50 blend behavior vs the lead on pre-holdout and holdout
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BACKTEST_SRC = ROOT / "backtesting" / "src"
BACKTEST_SCRIPTS = ROOT / "backtesting" / "scripts"
for path in (BACKTEST_SRC, BACKTEST_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from htf_lsi_common import HOLDOUT_START, build_config as build_htf_config, build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data  # noqa: E402
from orb_backtest.analysis.alpha_v1_downside import (  # noqa: E402
    DataCache,
    build_alpha_v1_legs,
    daily_r_series,
    pairwise_overlap,
    run_config,
    split_period_metrics,
    summarize_daily_returns,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from run_cross_asset_eqhl_lsi_broad_discovery import (  # noqa: E402
    build_config as build_eqhl_config,
    load_timeframe_data as load_eqhl_timeframe_data,
)


OUTPUT_DIR = ROOT / "backtesting" / "data" / "results" / "nq_ny_htf_lsi_orthogonal_companion_search"
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "NQ_NY_HTF_LSI_ORTHOGONAL_COMPANION_SEARCH.md"
SYMBOL = "NQ"


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    family: str
    source: str
    timeframe: str | None = None
    in_portfolio: bool = False


def split_series(series: pd.Series, *, holdout_start: str = HOLDOUT_START) -> dict[str, pd.Series]:
    ts = pd.Timestamp(holdout_start)
    return {
        "full": series,
        "pre_holdout": series[series.index < ts],
        "holdout": series[series.index >= ts],
    }


def blend_vs_lead(lead: pd.Series, candidate: pd.Series) -> dict[str, dict]:
    index = lead.index.union(candidate.index)
    lead_aligned = lead.reindex(index, fill_value=0.0)
    candidate_aligned = candidate.reindex(index, fill_value=0.0)
    combo = (lead_aligned * 0.5 + candidate_aligned * 0.5).sort_index()
    return {
        "lead_only": {name: summarize_daily_returns(series) for name, series in split_series(lead_aligned).items()},
        "candidate_only": {name: summarize_daily_returns(series) for name, series in split_series(candidate_aligned).items()},
        "blend_50_50": {name: summarize_daily_returns(series) for name, series in split_series(combo).items()},
    }


def build_nq_candidates() -> list[tuple[Candidate, object]]:
    lead = Candidate(
        key="lead",
        label="NQ NY HTF_LSI 5m lag24 control",
        family="htf_lsi_lead",
        source="research",
        timeframe="5m",
    )
    additive = Candidate(
        key="additive_eqhl",
        label="NQ NY HTF_LSI 5m lag24 + EQHL15m tol1",
        family="htf_plus_eqhl_15m_tol1",
        source="research",
        timeframe="5m",
    )
    two_min = Candidate(
        key="htf_2m_anchor",
        label="NQ NY HTF_LSI 2m secondary anchor",
        family="htf_lsi_2m_anchor",
        source="research",
        timeframe="2m",
    )
    eqhl_5m = Candidate(
        key="eqhl_5m_5pt",
        label="NQ NY EQHL_LSI 5m eqhl5m 5pt",
        family="eqhl_5m_to_5m_5pt",
        source="research",
        timeframe="5m",
    )
    eqhl_3m = Candidate(
        key="eqhl_3m_15pt",
        label="NQ NY EQHL_LSI 3m eqhl15m 15pt",
        family="eqhl_3m_to_15m_15pt",
        source="research",
        timeframe="3m",
    )

    return [
        (lead, build_current_nq_ny_htf_lsi_lag24_config(name=lead.label)),
        (
            additive,
            replace(
                build_current_nq_ny_htf_lsi_lag24_config(name=additive.label),
                htf_lsi_include_eqhl_levels=True,
                eqhl_level_tf_minutes=15,
                eqhl_n_left=2,
                eqhl_tolerance_ticks=1,
                eqhl_min_touches=2,
                eqhl_lookback_bars=48,
            ),
        ),
        (
            two_min,
            build_htf_config(
                timeframe="2m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_start="08:30",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=3,
                htf_trade_max_per_session=1,
                lsi_fvg_window_left=50,
                lsi_fvg_window_right=5,
                max_fvg_to_inversion_bars=0,
                name=two_min.label,
            ),
        ),
        (
            eqhl_5m,
            replace(
                build_eqhl_config(
                    symbol=SYMBOL,
                    timeframe="5m",
                    eqhl_tf_minutes=5,
                    eqhl_tolerance_ticks=20,
                    tolerance_label="5p",
                    eqhl_min_touches=2,
                    direction_filter="long",
                    entry_mode="fvg_limit",
                    entry_end="13:00",
                    rr=2.75,
                    tp1_ratio=0.6,
                    min_gap_atr_pct=3.0,
                    atr_length=14,
                    eqhl_n_left=2,
                    eqhl_lookback_bars=48,
                    left_minutes=80,
                    right_minutes=10,
                    min_stop_points=0.0,
                    min_tp1_points=0.0,
                ),
                name=eqhl_5m.label,
            ),
        ),
        (
            eqhl_3m,
            replace(
                build_eqhl_config(
                    symbol=SYMBOL,
                    timeframe="3m",
                    eqhl_tf_minutes=15,
                    eqhl_tolerance_ticks=60,
                    tolerance_label="15p",
                    eqhl_min_touches=2,
                    direction_filter="long",
                    entry_mode="fvg_limit",
                    entry_end="13:00",
                    rr=2.75,
                    tp1_ratio=0.5,
                    min_gap_atr_pct=3.0,
                    atr_length=14,
                    eqhl_n_left=2,
                    eqhl_lookback_bars=48,
                    left_minutes=81,
                    right_minutes=12,
                    min_stop_points=0.0,
                    min_tp1_points=0.0,
                ),
                name=eqhl_3m.label,
            ),
        ),
    ]


def run_research_candidate(candidate: Candidate, config) -> list:
    if candidate.family.startswith("eqhl_"):
        df_base, signal_df_1m, df_1s = load_eqhl_timeframe_data(SYMBOL, candidate.timeframe)
        maps = build_maps(df_base, df_1m=signal_df_1m, df_1s=df_1s)
        signal_cache = build_signal_cache(df_base, [config], signal_df_1m=signal_df_1m)
        return run_backtest(
            df_base,
            config,
            df_1m=signal_df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )

    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(candidate.timeframe or "5m")
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, [config], signal_df_1m=signal_df_1m)
    return run_backtest(
        df_base,
        config,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )


def build_baseline_candidates() -> list[tuple[Candidate, object]]:
    legs = build_alpha_v1_legs()
    return [
        (
            Candidate(
                key="legacy_nq_ny_lsi",
                label="ALPHA_V1 NQ NY legacy LSI",
                family="legacy_nq_ny_lsi",
                source="baseline_alpha_v1",
                in_portfolio=False,
            ),
            legs["nq_ny_lsi_long"].config,
        ),
        (
            Candidate(
                key="nq_asia_orb",
                label="ALPHA_V1 NQ Asia ORB",
                family="nq_asia_orb",
                source="baseline_alpha_v1",
                in_portfolio=True,
            ),
            legs["nq_asia_orb_long"].config,
        ),
        (
            Candidate(
                key="es_asia_orb",
                label="ALPHA_V1 ES Asia ORB",
                family="es_asia_orb",
                source="baseline_alpha_v1",
                in_portfolio=True,
            ),
            legs["es_asia_orb_long"].config,
        ),
        (
            Candidate(
                key="es_ny_orb",
                label="ALPHA_V1 ES NY ORB",
                family="es_ny_orb",
                source="baseline_alpha_v1",
                in_portfolio=True,
            ),
            legs["es_ny_orb_long"].config,
        ),
    ]


def score_row(row: dict) -> tuple:
    holdout_blend = row["blend"]["blend_50_50"]["holdout"]
    pre_blend = row["blend"]["blend_50_50"]["pre_holdout"]
    holdout_corr = row["overlap"]["holdout"]["daily_r_correlation"]
    if holdout_corr is None:
        holdout_corr = 1.0
    return (
        holdout_blend["calmar_ratio"],
        holdout_blend["total_r"],
        pre_blend["calmar_ratio"],
        -row["overlap"]["holdout"]["jaccard_overlap"],
        -holdout_corr,
    )


def write_report(payload: dict) -> None:
    lines = [
        "# NQ NY HTF-LSI Orthogonal Companion Search",
        "",
        "- Objective: search for a genuinely different companion against the current `NQ NY HTF_LSI 5m lag24` lead.",
        "- Ranking lens: low overlap, low daily-R correlation, acceptable standalone quality, and positive 50/50 blend behavior.",
        "",
        "## Ranked Candidates",
        "",
        "| Candidate | Family | In Book | Holdout Corr | Holdout Jaccard | Holdout 50/50 Calmar | Holdout 50/50 Total R | Pre 50/50 Calmar |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["ranked_candidates"]:
        holdout_corr = row["overlap"]["holdout"]["daily_r_correlation"]
        if holdout_corr is None:
            holdout_corr = float("nan")
        lines.append(
            f"| {row['label']} | {row['family']} | {str(row['in_portfolio'])} | "
            f"{holdout_corr:.3f} | "
            f"{row['overlap']['holdout']['jaccard_overlap']:.3f} | "
            f"{row['blend']['blend_50_50']['holdout']['calmar_ratio']:.2f} | "
            f"{row['blend']['blend_50_50']['holdout']['total_r']:.2f} | "
            f"{row['blend']['blend_50_50']['pre_holdout']['calmar_ratio']:.2f} |"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    research_candidates = build_nq_candidates()
    baseline_candidates = build_baseline_candidates()

    streams = {}
    lead_key = "lead"

    for candidate, config in research_candidates:
        print(f"Running research candidate {candidate.key}...", flush=True)
        streams[candidate.key] = {
            "candidate": candidate,
            "trades": run_research_candidate(candidate, config),
        }

    cache = DataCache(start_date="2016-01-01")
    for candidate, config in baseline_candidates:
        print(f"Running baseline candidate {candidate.key}...", flush=True)
        streams[candidate.key] = {
            "candidate": candidate,
            "trades": run_config(cache, config),
        }

    lead_trades = streams[lead_key]["trades"]
    lead_series = daily_r_series(lead_trades)

    rows = []
    for key, item in streams.items():
        if key == lead_key:
            continue
        candidate = item["candidate"]
        trades = item["trades"]
        overlap = {
            "full": pairwise_overlap({"lead": lead_trades, "candidate": trades})[0],
            "pre_holdout": pairwise_overlap(
                {
                    "lead": [t for t in lead_trades if t.date < HOLDOUT_START],
                    "candidate": [t for t in trades if t.date < HOLDOUT_START],
                }
            )[0],
            "holdout": pairwise_overlap(
                {
                    "lead": [t for t in lead_trades if t.date >= HOLDOUT_START],
                    "candidate": [t for t in trades if t.date >= HOLDOUT_START],
                }
            )[0],
        }
        candidate_series = daily_r_series(trades)
        blend = blend_vs_lead(lead_series, candidate_series)
        rows.append(
            {
                "key": candidate.key,
                "label": candidate.label,
                "family": candidate.family,
                "source": candidate.source,
                "in_portfolio": candidate.in_portfolio,
                "standalone": split_period_metrics(trades, holdout_start=HOLDOUT_START),
                "overlap": overlap,
                "blend": blend,
            }
        )

    ranked = sorted(rows, key=score_row, reverse=True)
    payload = {
        "lead": streams[lead_key]["candidate"].label,
        "ranked_candidates": ranked,
    }
    (OUTPUT_DIR / "orthogonal_companion_search.json").write_text(json.dumps(payload, indent=2, default=str))
    write_report(payload)
    print(f"Saved orthogonal companion search to {OUTPUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
