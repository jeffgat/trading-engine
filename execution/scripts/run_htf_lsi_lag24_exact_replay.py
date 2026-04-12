#!/usr/bin/env python3
"""Run exact live-engine replay for the promoted NQ NY HTF-LSI lag24 branch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
BACKTEST_SRC = ROOT / "backtesting" / "src"
BACKTEST_SCRIPTS = ROOT / "backtesting" / "scripts"
for path in (EXEC_SRC, BACKTEST_SRC, BACKTEST_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from trader.historical_backtest import _compute_summary, latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402


PROFILE_NAME = "HTF_LSI_5M_LAG24"
FULL_START = "2016-01-01"
PRE_HOLDOUT_END = "2025-03-31"
HOLDOUT_START = "2025-04-01"

OUTPUT_DIR = ROOT / "backtesting" / "data" / "results" / "nq_ny_htf_lsi_lag24_exact_replay"
OUTPUT_JSON = OUTPUT_DIR / "exact_replay_compare.json"
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "NQ_NY_HTF_LSI_LAG24_EXACT_REPLAY.md"


def _slice_trades(trades: list[dict], start: str | None = None, end: str | None = None) -> list[dict]:
    return [
        trade
        for trade in trades
        if (start is None or trade["date"] >= start)
        and (end is None or trade["date"] <= end)
    ]


def _slice_research_trades(trades: list, start: str | None = None, end: str | None = None) -> list:
    return [
        trade
        for trade in trades
        if (start is None or trade.date >= start)
        and (end is None or trade.date <= end)
    ]


def _config_summary(config) -> str:
    session = config.sessions[0]
    return (
        f"{config.direction_filter} {config.lsi_entry_mode} "
        f"{session.entry_start}-{session.entry_end} "
        f"rr{config.rr} tp{config.tp1_ratio} "
        f"gap{session.min_gap_atr_pct} "
        f"htf{config.htf_level_tf_minutes} n{config.htf_n_left} "
        f"cap{config.htf_trade_max_per_session} "
        f"fvgL{config.lsi_fvg_window_left} fvgR{config.lsi_fvg_window_right} "
        f"lag{config.max_fvg_to_inversion_bars}"
    )


def _run_research_metrics(common_end) -> tuple[dict, str, str]:
    config = build_current_nq_ny_htf_lsi_lag24_config(
        name="NQ NY HTF_LSI 5m lag24 exact replay research",
    )
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    research_data_end = pd.Timestamp(df_base.index.max()).normalize().date()
    holdout_end = min(common_end.date(), research_data_end).isoformat()
    holdout_end_exclusive = (
        pd.Timestamp(holdout_end).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, [config], signal_df_1m=signal_df_1m)
    trades = run_backtest(
        df_base,
        config,
        start_date=FULL_START,
        end_date=holdout_end_exclusive,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    return (
        {
            "full": compute_metrics(trades),
            "pre_holdout": compute_metrics(_slice_research_trades(trades, FULL_START, PRE_HOLDOUT_END)),
            "holdout": compute_metrics(_slice_research_trades(trades, HOLDOUT_START, holdout_end)),
        },
        holdout_end,
        _config_summary(config),
    )


def _delta_row(exact_metrics: dict, research_metrics: dict) -> dict:
    return {
        "trades_delta": int(exact_metrics.get("total_trades", 0) - research_metrics.get("total_trades", 0)),
        "pf_delta": round(float(exact_metrics.get("profit_factor", 0.0) - research_metrics.get("profit_factor", 0.0)), 4),
        "avg_r_delta": round(float(exact_metrics.get("avg_r", 0.0) - research_metrics.get("avg_r", 0.0)), 4),
        "calmar_delta": round(float(exact_metrics.get("calmar_ratio", 0.0) - research_metrics.get("calmar_ratio", 0.0)), 4),
        "max_dd_r_delta": round(float(exact_metrics.get("max_drawdown_r", 0.0) - research_metrics.get("max_drawdown_r", 0.0)), 4),
    }


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def _write_report(path: Path, payload: dict) -> None:
    info = payload["info"]
    exact = payload["exact"]
    research = payload["research"]
    delta = payload["delta"]

    lines = [
        "# NQ NY HTF-LSI Lag24 Exact Replay",
        "",
        "- Objective: replay the current `5m lag=24` branch through the live execution engine and compare it with the current research definition.",
        f"- Profile: `{info['profile_name']}`",
        f"- Research config: `{info['research_config']}`",
        f"- Full replay window: `{info['full_start']}` to `{info['holdout_end_inclusive']}`",
        "",
        "## Windows",
        "",
        "| Window | Exact Trades | Exact PF | Exact Avg R | Exact Calmar | Research Trades | Research PF | Research Avg R | Research Calmar | Delta Trades | Delta PF | Delta Avg R |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for key, label in (("pre_holdout", "Pre-Holdout"), ("holdout", "Holdout")):
        exact_metrics = exact[key]
        research_metrics = research[key]
        delta_metrics = delta[key]
        lines.append(
            f"| {label} | "
            f"{int(exact_metrics.get('total_trades', 0))} | "
            f"{float(exact_metrics.get('profit_factor', 0.0)):.3f} | "
            f"{float(exact_metrics.get('avg_r', 0.0)):.3f} | "
            f"{float(exact_metrics.get('calmar_ratio', 0.0)):.3f} | "
            f"{int(research_metrics.get('total_trades', 0))} | "
            f"{float(research_metrics.get('profit_factor', 0.0)):.3f} | "
            f"{float(research_metrics.get('avg_r', 0.0)):.3f} | "
            f"{float(research_metrics.get('calmar_ratio', 0.0)):.3f} | "
            f"{delta_metrics['trades_delta']} | "
            f"{delta_metrics['pf_delta']:.3f} | "
            f"{delta_metrics['avg_r_delta']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Exact Replay Full-Window Snapshot",
            "",
            f"- Trades: `{int(exact['full'].get('total_trades', 0))}`",
            f"- PF: `{float(exact['full'].get('profit_factor', 0.0)):.3f}`",
            f"- Avg R: `{float(exact['full'].get('avg_r', 0.0)):.3f}`",
            f"- Total R: `{float(exact['full'].get('total_r', 0.0)):.3f}`",
            f"- Max DD: `{float(exact['full'].get('max_drawdown_r', 0.0)):.3f}R`",
            f"- Calmar: `{float(exact['full'].get('calmar_ratio', 0.0)):.3f}`",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    config = load_config(DEFAULT_CONFIG)
    common_end = latest_common_end(["NQ"])
    research_metrics, holdout_end, research_config_summary = _run_research_metrics(common_end)
    result = run_profile_backtest_sync(
        config=config,
        profile_name=PROFILE_NAME,
        start_date=FULL_START,
        end_date=holdout_end,
        latest_data_ts=common_end,
        label=f"EXEC EXACT {PROFILE_NAME} {FULL_START} to {holdout_end}",
    )

    trades = result["trades"]
    exact_full = result["summary"]
    exact_pre = _compute_summary(_slice_trades(trades, FULL_START, PRE_HOLDOUT_END))
    exact_holdout = _compute_summary(_slice_trades(trades, HOLDOUT_START, holdout_end))

    payload = {
        "info": {
            "profile_name": PROFILE_NAME,
            "full_start": FULL_START,
            "pre_holdout_end_inclusive": PRE_HOLDOUT_END,
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end,
            "latest_common_end": common_end.isoformat(),
            "research_config": research_config_summary,
        },
        "exact": {
            "full": exact_full,
            "pre_holdout": exact_pre,
            "holdout": exact_holdout,
        },
        "research": research_metrics,
        "delta": {
            "pre_holdout": _delta_row(exact_pre, research_metrics["pre_holdout"]),
            "holdout": _delta_row(exact_holdout, research_metrics["holdout"]),
        },
    }

    _save_json(OUTPUT_JSON, payload)
    _write_report(REPORT_PATH, payload)

    print(json.dumps(payload, indent=2, default=str))
    print(f"\nSaved JSON to {OUTPUT_JSON}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
