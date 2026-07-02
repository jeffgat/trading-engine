#!/usr/bin/env python3
"""NQ NY VWAP reversion fixed-R discovery starter.

Research artifact only. Keeps 2025+ holdout closed.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.holdout_log import check_holdout_period  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import build_maps  # noqa: E402
from orb_backtest.engine.vwap_simulator import (  # noqa: E402
    build_vwap_signal_cache,
    run_vwap_backtest,
)
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.vwap_config import default_vwap_config, with_vwap_overrides  # noqa: E402


RUN_SLUG = "nq_ny_vwap_reversion_fixed_rr_pipeline_20260629"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_REVERSION_FIXED_RR_PIPELINE_20260629.md"

PRE_START = "2016-01-01"
PRE_END_EXCLUSIVE = "2025-01-01"
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-06-06"

ACCOUNT_USD = 2000.0
RISK_USD = 500.0
ACCOUNT_R_CAPACITY = ACCOUNT_USD / RISK_USD


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _r2(value: Any) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(value, 2) if math.isfinite(value) else 0.0


def _full_year_stats(r_by_year: dict[str, Any]) -> tuple[int, float, str]:
    years = {year: float(value) for year, value in r_by_year.items() if year <= "2024"}
    if not years:
        return 0, 0.0, ""
    neg_years = sum(1 for value in years.values() if value < 0)
    worst_year, worst_value = min(years.items(), key=lambda item: item[1])
    return neg_years, round(worst_value, 2), worst_year


def _config_label(config) -> str:
    session = config.sessions[0]
    return (
        f"dev{session.deviation_atr_pct:g}_stop{session.stop_atr_pct:g}_"
        f"{session.entry_start.replace(':', '')}-{session.entry_end.replace(':', '')}_"
        f"{config.direction_filter}"
    )


def _make_configs():
    base = with_vwap_overrides(
        default_vwap_config(NQ),
        rr=1.5,
        risk_usd=RISK_USD,
        tp1_ratio=1.0,
        tp2_mode="fixed_rr",
        half_days=(),
    )
    configs = []
    for deviation_atr_pct in (10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0):
        for stop_atr_pct in (0.0, 5.0, 10.0, 20.0):
            for entry_start in ("09:35", "10:00"):
                for entry_end in ("10:30", "11:30", "12:00"):
                    for direction_filter in ("both", "long", "short"):
                        if entry_start >= entry_end:
                            continue
                        configs.append(
                            with_vwap_overrides(
                                base,
                                direction_filter=direction_filter,
                                ny_entry_start=entry_start,
                                ny_entry_end=entry_end,
                                ny_deviation_atr_pct=deviation_atr_pct,
                                ny_stop_atr_pct=stop_atr_pct,
                                ny_rejection_mode="close",
                            )
                        )
    return configs


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    holdout_check = check_holdout_period(HOLDOUT_START, HOLDOUT_END)
    print(
        f"Phase 0: holdout {HOLDOUT_START} to {HOLDOUT_END}; "
        f"previous_tests={holdout_check.previous_test_count}; clean={holdout_check.is_clean}"
    )

    print(f"Loading NQ 5m/1m data {PRE_START} to {PRE_END_EXCLUSIVE}...")
    df_5m = load_5m_data(NQ.data_file, start=PRE_START, end=PRE_END_EXCLUSIVE)
    df_1m = load_1m_for_5m(NQ.data_file, start=PRE_START, end=PRE_END_EXCLUSIVE)

    configs = _make_configs()
    print(f"Phase 1/2 coarse screen: {len(configs)} configs; fixed rr=1.5 risk=${RISK_USD:g}")

    signal_cache = build_vwap_signal_cache(df_5m, configs)
    maps = build_maps(df_5m, df_1m)

    rows: list[dict[str, Any]] = []
    for idx, config in enumerate(configs, start=1):
        trades = run_vwap_backtest(
            df_5m,
            config,
            start_date=PRE_START,
            end_date=PRE_END_EXCLUSIVE,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        metrics = compute_metrics(trades)
        session = config.sessions[0]
        neg_years, worst_year_r, worst_year = _full_year_stats(metrics["r_by_year"])
        row = {
            "rank_score": 0.0,
            "variant_id": _config_label(config),
            "instrument": "NQ",
            "session": "NY",
            "strategy": "vwap_reversion",
            "rr": config.rr,
            "risk_usd": config.risk_usd,
            "account_usd": ACCOUNT_USD,
            "account_r_capacity": ACCOUNT_R_CAPACITY,
            "entry_start": session.entry_start,
            "entry_end": session.entry_end,
            "deviation_atr_pct": session.deviation_atr_pct,
            "stop_atr_pct": session.stop_atr_pct,
            "rejection_mode": session.rejection_mode,
            "direction_filter": config.direction_filter,
            "total_trades": metrics["total_trades"],
            "total_r": _r2(metrics["total_r"]),
            "total_net_r": _r2(metrics["total_net_r"]),
            "avg_r": _r2(metrics["avg_r"]),
            "profit_factor": _r2(metrics["profit_factor"]),
            "win_rate": _r2(metrics["win_rate"]),
            "max_drawdown_r": _r2(metrics["max_drawdown_r"]),
            "sharpe": _r2(metrics["sharpe_ratio"]),
            "calmar": _r2(metrics["calmar_ratio"]),
            "neg_years": neg_years,
            "worst_year": worst_year,
            "worst_year_r": worst_year_r,
            "long_r": _r2(metrics["long_r"]),
            "short_r": _r2(metrics["short_r"]),
            "breaches_2000_500_account": bool(metrics["max_drawdown_r"] <= -ACCOUNT_R_CAPACITY),
            "deployability": "research_only",
            "live_support_notes": (
                "VWAP reversion is implemented in research backtester; current execution "
                "engine only exposes VWAP as a context gate, not this entry/exit strategy."
            ),
            "exact_replay_required": "yes",
        }
        if row["total_trades"] >= 100:
            row["rank_score"] = (
                row["total_r"]
                + 10.0 * row["profit_factor"]
                + 2.0 * row["calmar"]
                - 2.0 * row["neg_years"]
                + row["max_drawdown_r"] * 0.2
            )
        rows.append(row)
        if idx % 50 == 0:
            print(f"  completed {idx}/{len(configs)}")

    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["total_r", "profit_factor", "max_drawdown_r", "total_trades"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))

    csv_path = RESULT_DIR / "coarse_screen.csv"
    summary_path = RESULT_DIR / "summary.json"
    df.to_csv(csv_path, index=False)

    top = df.head(20).to_dict(orient="records")
    positive = df[(df["total_r"] > 0) & (df["total_trades"] >= 100)]
    summary = {
        "run_slug": RUN_SLUG,
        "phase": "discovery_start_coarse_screen",
        "pre_holdout_start": PRE_START,
        "pre_holdout_end_exclusive": PRE_END_EXCLUSIVE,
        "holdout_start": HOLDOUT_START,
        "holdout_end": HOLDOUT_END,
        "holdout_previous_tests": holdout_check.previous_test_count,
        "holdout_clean": holdout_check.is_clean,
        "account_usd": ACCOUNT_USD,
        "risk_usd": RISK_USD,
        "account_r_capacity": ACCOUNT_R_CAPACITY,
        "raw_configs": len(configs),
        "positive_configs_min_100_trades": int(len(positive)),
        "top_rows": top,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(_safe(summary), indent=2) + "\n")

    report_lines = [
        "# NQ NY VWAP Reversion Fixed-R Pipeline Start",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Phase: holdout freeze + fixed-R coarse structural screen",
        f"- Pre-holdout discovery: `{PRE_START}` to `<{PRE_END_EXCLUSIVE}`",
        f"- Reserved holdout: `{HOLDOUT_START}` to `{HOLDOUT_END}`; previous logged tests: `{holdout_check.previous_test_count}`",
        f"- Account test: `${ACCOUNT_USD:g}` account, `${RISK_USD:g}` risk/trade = `{ACCOUNT_R_CAPACITY:.1f}R` account capacity",
        f"- Fixed exit: `rr=1.5`, `tp1_ratio=1.0` single target",
        f"- Raw configs: `{len(configs)}`",
        f"- Positive configs with at least 100 trades: `{len(positive)}`",
        "",
        "## Top Rows By Total R",
        "",
        df.head(12)[
            [
                "rank",
                "variant_id",
                "total_trades",
                "total_r",
                "profit_factor",
                "win_rate",
                "max_drawdown_r",
                "neg_years",
                "worst_year",
                "worst_year_r",
                "breaches_2000_500_account",
                "deployability",
            ]
        ].to_markdown(index=False),
        "",
        "## Read",
        "",
        "- This is not a final promotion packet. It is the first coarse screen before walk-forward, plateau checks, PSR/DSR, or phase-one payout modeling.",
        "- All rows are `research_only` until the VWAP reversion strategy exists in the live execution engine and exact replay confirms parity.",
        "- The `$500` risk on a `$2,000` account means any path worse than `-4R` breaches the account.",
        "",
        "## Artifacts",
        "",
        f"- CSV: `backtesting/data/results/{RUN_SLUG}/coarse_screen.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {REPORT_PATH}")
    print(f"Elapsed {summary['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
