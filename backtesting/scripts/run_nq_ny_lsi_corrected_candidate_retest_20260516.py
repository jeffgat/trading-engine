#!/usr/bin/env python3
"""Retest serious NQ NY LSI/HTF-LSI challengers after stale-level correction."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from htf_lsi_common import build_config as build_htf_config  # noqa: E402
from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data  # noqa: E402
from orb_backtest.analysis.alpha_v1_downside import filter_trades_by_combined_regime  # noqa: E402
from orb_backtest.analysis.regime_research import build_extended_regime_calendar  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from run_cross_asset_eqhl_lsi_broad_discovery import build_config as build_eqhl_config  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_lsi_corrected_candidate_retest_20260516"
OUTPUT_JSON = OUTPUT_DIR / "summary.json"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_CORRECTED_CANDIDATE_RETEST_20260516.md"

START = "2016-01-01"
END_EXCLUSIVE = "2026-05-02"

WINDOWS = {
    "full": ("2016-01-01", END_EXCLUSIVE),
    "rolling_10y": ("2016-05-01", END_EXCLUSIVE),
    "rolling_2y": ("2024-05-01", END_EXCLUSIVE),
    "rolling_1y": ("2025-05-01", END_EXCLUSIVE),
    "holdout": ("2025-04-01", END_EXCLUSIVE),
}


def _slice_trades(trades: list, start: str, end_exclusive: str) -> list:
    return [trade for trade in trades if start <= trade.date < end_exclusive]


def _compact_metrics(trades: list) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    return {
        "trades": int(metrics.get("total_trades", 0)),
        "win_rate_pct": round(float(metrics.get("win_rate", 0.0)) * 100.0, 1),
        "pf": round(float(metrics.get("profit_factor", 0.0)), 3),
        "sharpe": round(float(metrics.get("sharpe_ratio", 0.0)), 3),
        "avg_r": round(float(metrics.get("avg_r", 0.0)), 4),
        "total_r": round(float(metrics.get("total_r", 0.0)), 3),
        "max_dd_r": round(float(metrics.get("max_drawdown_r", 0.0)), 3),
        "calmar": round(float(metrics.get("calmar_ratio", 0.0)), 3),
        "neg_years": sum(1 for value in metrics.get("r_by_year", {}).values() if float(value) < 0.0),
    }


def _candidate(label: str, config, *, timeframe: str = "5m", deployability: str, notes: str = "", exclude_regimes: set[str] | None = None) -> dict:
    return {
        "label": label,
        "config": config,
        "timeframe": timeframe,
        "deployability": deployability,
        "notes": notes,
        "exclude_regimes": exclude_regimes or set(),
    }


def make_candidates() -> list[dict]:
    current = build_current_nq_ny_htf_lsi_lag24_config(
        name="current_active_htf_lag24",
    )
    old_exit_lag24 = build_htf_config(
        timeframe="5m",
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
        htf_trade_max_per_session=2,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=2,
        max_fvg_to_inversion_bars=24,
        name="old_exit_lag24_htf_only",
    )
    gap25_r2_old = build_htf_config(
        timeframe="5m",
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_start="08:30",
        entry_end="15:00",
        rr=3.0,
        tp1_ratio=0.6,
        min_gap_atr_pct=2.5,
        atr_length=14,
        htf_level_tf_minutes=60,
        htf_n_left=3,
        htf_trade_max_per_session=2,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=2,
        max_fvg_to_inversion_bars=0,
        name="gap25_right2_lag0_old_exit",
    )
    gap25_r3_old = dataclasses.replace(
        gap25_r2_old,
        lsi_fvg_window_right=3,
        name="gap25_right3_lag0_old_exit",
    )
    gap25_r2_current = build_htf_config(
        timeframe="5m",
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_start="08:30",
        entry_end="13:30",
        rr=3.5,
        tp1_ratio=0.4,
        min_gap_atr_pct=2.5,
        atr_length=14,
        htf_level_tf_minutes=60,
        htf_n_left=3,
        htf_trade_max_per_session=2,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=2,
        max_fvg_to_inversion_bars=0,
        name="gap25_right2_lag0_current_exit",
    )
    gap25_r3_current = dataclasses.replace(
        gap25_r2_current,
        lsi_fvg_window_right=3,
        name="gap25_right3_lag0_current_exit",
    )
    gap25_r2_lag30_current = dataclasses.replace(
        gap25_r2_current,
        max_fvg_to_inversion_bars=30,
        name="gap25_right2_lag30_current_exit",
    )
    anchor_2m = build_htf_config(
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
        name="secondary_2m_anchor",
    )
    htf_plus_15m_eqhl = dataclasses.replace(
        current,
        htf_lsi_include_eqhl_levels=True,
        eqhl_level_tf_minutes=15,
        eqhl_n_left=2,
        eqhl_tolerance_ticks=1,
        eqhl_min_touches=2,
        eqhl_lookback_bars=48,
        name="current_plus_15m_eqhl_tol1",
    )
    htf_plus_5m_eqhl = dataclasses.replace(
        htf_plus_15m_eqhl,
        eqhl_level_tf_minutes=5,
        name="current_plus_5m_eqhl_tol1",
    )
    htf_plus_60m_eqhl_15pt = dataclasses.replace(
        htf_plus_15m_eqhl,
        eqhl_level_tf_minutes=60,
        eqhl_tolerance_ticks=60,  # NQ min tick is 0.25, so 60 ticks = 15 points.
        name="current_plus_60m_eqhl_15pt",
    )
    standalone_eqhl = build_eqhl_config(
        symbol="NQ",
        timeframe="5m",
        eqhl_tf_minutes=5,
        eqhl_tolerance_ticks=2,
        eqhl_min_touches=2,
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_end="13:00",
        rr=3.25,
        tp1_ratio=0.6,
        min_gap_atr_pct=3.0,
        atr_length=14,
        eqhl_n_left=2,
        eqhl_lookback_bars=48,
        left_minutes=100,
        right_minutes=15,
        min_stop_points=0.0,
        min_tp1_points=0.0,
    )

    return [
        _candidate("current_active_htf_lag24", current, deployability="live_native", notes="Current ALPHA_V1 slot."),
        _candidate("current_active_htf_lag24_skip_bear", current, deployability="post_filter_only", notes="Same current slot, post-filtered to skip bear_high_vol.", exclude_regimes={"bear_high_vol"}),
        _candidate("old_exit_lag24_htf_only", old_exit_lag24, deployability="live_native", notes="Prior frozen lag24 exit/window shape."),
        _candidate("gap25_right2_lag0_skip_bear_old_exit", gap25_r2_old, deployability="post_filter_only", notes="Count challenger as originally studied.", exclude_regimes={"bear_high_vol"}),
        _candidate("gap25_right3_lag0_skip_bear_old_exit", gap25_r3_old, deployability="post_filter_only", notes="Higher-count sibling as originally studied.", exclude_regimes={"bear_high_vol"}),
        _candidate("gap25_right2_lag0_skip_bear_current_exit", gap25_r2_current, deployability="post_filter_only", notes="Count challenger normalized to current exit/window.", exclude_regimes={"bear_high_vol"}),
        _candidate("gap25_right3_lag0_skip_bear_current_exit", gap25_r3_current, deployability="post_filter_only", notes="Higher-count sibling normalized to current exit/window.", exclude_regimes={"bear_high_vol"}),
        _candidate("gap25_right2_lag30_current_exit", gap25_r2_lag30_current, deployability="live_native", notes="Higher-flow late-lag variant normalized to current exit/window."),
        _candidate("secondary_2m_anchor", anchor_2m, timeframe="2m", deployability="research_only", notes="2m secondary anchor; exact/live plumbing not validated in ALPHA."),
        _candidate("current_plus_15m_eqhl_tol1", htf_plus_15m_eqhl, deployability="research_only", notes="Additive EQHL preferred research upgrade; execution unsupported."),
        _candidate("current_plus_5m_eqhl_tol1", htf_plus_5m_eqhl, deployability="research_only", notes="Additive EQHL lower-DD alternate; execution unsupported."),
        _candidate("current_plus_60m_eqhl_15pt", htf_plus_60m_eqhl_15pt, deployability="research_only", notes="Wide additive challenger; execution unsupported."),
        _candidate("standalone_5m_eqhl_lsi", standalone_eqhl, deployability="research_only", notes="Standalone EQHL-LSI phase-one challenger; execution unsupported."),
    ]


def run_candidate(candidate: dict, data_cache: dict, regime_calendar) -> dict:
    timeframe = candidate["timeframe"]
    df_base, df_1m, df_1s, signal_df_1m, maps, signal_cache = data_cache[timeframe]
    config = candidate["config"]
    trades = run_backtest(
        df_base,
        config,
        start_date=START,
        end_date=END_EXCLUSIVE,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    raw_trade_count = len(trades)
    if candidate["exclude_regimes"]:
        trades = filter_trades_by_combined_regime(
            trades,
            regime_calendar,
            exclude=candidate["exclude_regimes"],
        )
    windows = {
        name: _compact_metrics(_slice_trades(trades, start, end_exclusive))
        for name, (start, end_exclusive) in WINDOWS.items()
    }
    return {
        "label": candidate["label"],
        "deployability": candidate["deployability"],
        "timeframe": timeframe,
        "notes": candidate["notes"],
        "exclude_regimes": sorted(candidate["exclude_regimes"]),
        "raw_trade_count": raw_trade_count,
        "kept_trade_count": len(trades),
        "windows": windows,
    }


def _score_row(row: dict) -> tuple[float, float, float, float]:
    holdout = row["windows"]["holdout"]
    full = row["windows"]["full"]
    return (
        float(holdout["total_r"]),
        float(holdout["pf"]),
        float(full["calmar"]),
        float(full["total_r"]),
    )


def write_report(payload: dict) -> None:
    rows = sorted(payload["results"], key=_score_row, reverse=True)
    lines = [
        "# NQ NY LSI Corrected Candidate Retest - 2026-05-16",
        "",
        "- Objective: retest serious NQ NY LSI / HTF-LSI challengers after the stale HTF-level invalidation correction.",
        "- Scope: research-engine comparison through `2026-05-01`; exact live replay is still required before promoting any new live slot.",
        "- Baseline: `current_active_htf_lag24`, matching the current `ALPHA_V1` HTF-LSI slot.",
        "",
        "## Holdout Ranking",
        "",
        "| Candidate | Deployability | Holdout Trades | Holdout PF | Holdout R | Holdout DD | Full R | Full DD | Full Calmar | Notes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        holdout = row["windows"]["holdout"]
        full = row["windows"]["full"]
        lines.append(
            f"| {row['label']} | {row['deployability']} | "
            f"{holdout['trades']} | {holdout['pf']:.3f} | {holdout['total_r']:+.2f} | {holdout['max_dd_r']:.2f}R | "
            f"{full['total_r']:+.2f} | {full['max_dd_r']:.2f}R | {full['calmar']:.2f} | {row['notes']} |"
        )
    lines.extend(
        [
            "",
            "## Full / 10Y / 2Y / 1Y Snapshot",
            "",
            "| Candidate | Full R | 10Y R | 2Y R | 1Y R | Full PF | 10Y PF | 2Y PF | 1Y PF |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        full = row["windows"]["full"]
        ten = row["windows"]["rolling_10y"]
        two = row["windows"]["rolling_2y"]
        one = row["windows"]["rolling_1y"]
        lines.append(
            f"| {row['label']} | {full['total_r']:+.2f} | {ten['total_r']:+.2f} | "
            f"{two['total_r']:+.2f} | {one['total_r']:+.2f} | "
            f"{full['pf']:.3f} | {ten['pf']:.3f} | {two['pf']:.3f} | {one['pf']:.3f} |"
        )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    candidates = make_candidates()
    timeframes = sorted({candidate["timeframe"] for candidate in candidates})
    data_cache = {}
    df_5m_for_regime = None
    for timeframe in timeframes:
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
        configs = [candidate["config"] for candidate in candidates if candidate["timeframe"] == timeframe]
        maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
        signal_cache = build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)
        data_cache[timeframe] = (df_base, df_1m, df_1s, signal_df_1m, maps, signal_cache)
        if timeframe == "5m":
            df_5m_for_regime = df_base
    if df_5m_for_regime is None:
        df_5m_for_regime, *_ = load_timeframe_data("5m")
    regime_calendar = build_extended_regime_calendar(df_5m_for_regime)
    results = [run_candidate(candidate, data_cache, regime_calendar) for candidate in candidates]
    payload = {
        "generated_at": "2026-05-16",
        "start": START,
        "end_inclusive": "2026-05-01",
        "windows": WINDOWS,
        "results": results,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    write_report(payload)
    print(json.dumps(payload, indent=2, default=str))
    print(f"Saved JSON to {OUTPUT_JSON}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
