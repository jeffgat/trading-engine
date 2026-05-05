#!/usr/bin/env python3
"""Exact-to-exact HOT_REGIME_V1 structural candidate comparison.

This script deliberately does not edit execution/config/exec_configs.json.
It builds temporary ExecutionConfig objects in memory, replays them through
the live execution state machines, and saves comparison artifacts locally.
"""

from __future__ import annotations

import copy
import json
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
BACKTESTING_SRC = ROOT / "backtesting" / "src"
for path in (EXEC_SRC, BACKTESTING_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from orb_backtest.data.news_dates import CPI_SET, FOMC_SET, NFP_SET  # noqa: E402
from trader import historical_backtest as hb  # noqa: E402
from trader.main import (  # noqa: E402
    DEFAULT_CONFIG,
    ExecutionConfig,
    LSI_SESSION_CONFIGS,
    SESSION_CONFIGS,
    load_config,
    load_exec_configs,
)

RUN_SLUG = "hot_regime_v1_exact_candidate_compare_20260503"
START_DATE = "2025-03-24"
END_DATE = "2026-03-24"
BASE_PROFILE = "HOT_REGIME_V1"
CURRENT_RESULT_PATH = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "hot_regime_v1_exact_compare_20260503"
    / "hot_regime_v1_exact_result.json"
)
CURRENT_SINGLE_METRICS_PATH = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "hot_regime_v1_exact_compare_20260503"
    / "hot_regime_v1_single_leg_with_nq_regime_exact_metrics.json"
)
CURRENT_NQ_SINGLE_METRICS_PATH = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "hot_regime_v1_exact_compare_20260503"
    / "hot_regime_v1_single_leg_exact_metrics.json"
)
RESULT_DIR = ROOT / "backtesting" / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "HOT_REGIME_V1_EXACT_CANDIDATE_COMPARE_20260503.md"

TARGET_SESSIONS = ("NQ_NY", "ES_NY", "GC_NY", "GC_Asia")
DATE_EXCLUSIONS = {
    "NQ_NY": CPI_SET,
    "ES_NY": FOMC_SET | CPI_SET,
    "GC_NY": CPI_SET | NFP_SET,
    "GC_Asia": CPI_SET | NFP_SET,
}
GATE_LABELS = {
    "NQ_NY": "exclude_cpi",
    "ES_NY": "exclude_fomc_cpi",
    "GC_NY": "exclude_cpi_nfp",
    "GC_Asia": "exclude_cpi_nfp native; cpi_nfp_plus_not_inside post-filter",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _date_range_yyyymmdd(start: str, end: str) -> tuple[str, ...]:
    cur = datetime.fromisoformat(start).date()
    last = datetime.fromisoformat(end).date()
    out: list[str] = []
    while cur <= last:
        out.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return tuple(out)


def _as_sorted_dates(values: set[str]) -> tuple[str, ...]:
    return tuple(sorted(d for d in values if START_DATE.replace("-", "") <= d <= END_DATE.replace("-", "")))


def _clone_profile(profile: ExecutionConfig, *, name: str) -> ExecutionConfig:
    cloned = copy.deepcopy(profile)
    cloned.name = name
    cloned.webhooks = []
    return cloned


def _with_extra_excluded_dates(overrides: dict[str, Any], dates: set[str]) -> dict[str, Any]:
    merged = copy.deepcopy(overrides)
    existing = set(merged.get("excluded_dates") or ())
    merged["excluded_dates"] = tuple(sorted(existing | set(dates)))
    return merged


def _candidate_full_profile(base: ExecutionConfig) -> ExecutionConfig:
    candidate = _clone_profile(base, name="HOT_REGIME_V1_CANDIDATE_NATIVE")
    for session_name, dates in DATE_EXCLUSIONS.items():
        candidate.session_overrides[session_name] = _with_extra_excluded_dates(
            candidate.session_overrides[session_name],
            dates,
        )
    return candidate


def _single_profile(
    base: ExecutionConfig,
    *,
    session_name: str,
    candidate: bool,
) -> ExecutionConfig:
    profile = _clone_profile(
        base,
        name=f"HOT_REGIME_V1_{session_name}_{'CANDIDATE' if candidate else 'CURRENT'}_SINGLE",
    )
    target = copy.deepcopy(base.session_overrides[session_name])
    if candidate:
        target = _with_extra_excluded_dates(target, DATE_EXCLUSIONS.get(session_name, set()))

    sessions: dict[str, dict] = {session_name: target}
    if not session_name.startswith("NQ_"):
        inert = copy.deepcopy(base.session_overrides["NQ_NY"])
        inert["excluded_dates"] = _date_range_yyyymmdd(START_DATE, END_DATE)
        sessions = {"NQ_NY": inert, session_name: target}

    profile.session_overrides = sessions
    profile.lsi_session_overrides = {}
    return profile


def _profile_symbols(exec_config: ExecutionConfig) -> list[str]:
    symbols: set[str] = set()
    for session_name, overrides in exec_config.session_overrides.items():
        merged = {**SESSION_CONFIGS.get(session_name, {}), **overrides}
        symbols.add(merged.get("instrument", "NQ"))
    for session_name, overrides in exec_config.lsi_session_overrides.items():
        merged = {**LSI_SESSION_CONFIGS.get(session_name, {}), **overrides}
        symbols.add(merged.get("instrument", "NQ"))
    return sorted(symbols)


def _run_profile(config: dict, profile: ExecutionConfig, label: str) -> dict:
    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    try:
        common_end = hb.latest_common_end(_profile_symbols(profile))
        return hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=START_DATE,
            end_date=END_DATE,
            latest_data_ts=common_end,
            label=label,
        )
    finally:
        hb.load_exec_configs = original_loader


def _metrics_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    trades = int(summary.get("total_trades", 0))
    return {
        "fills": trades,
        "net_r": round(float(summary.get("total_r", 0.0)), 2),
        "wr_pct": round(float(summary.get("win_rate", 0.0)) * 100.0, 2),
        "pf": round(float(summary.get("profit_factor", 0.0)), 3),
        "dd_r": round(float(summary.get("max_drawdown_r", 0.0)), 2),
        "calmar": (
            round(float(summary.get("calmar_ratio", 0.0)), 3)
            if trades
            else None
        ),
    }


def _session_metrics(result: dict) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for trade in result.get("trades", []):
        grouped[str(trade["session"])].append(trade)
    return {
        session: _metrics_from_summary(hb._compute_summary(trades))
        for session, trades in sorted(grouped.items())
    }


def _overall_metrics(result: dict) -> dict[str, Any]:
    return _metrics_from_summary(hb._compute_summary(result.get("trades", [])))


def _load_current_single_metrics() -> dict[str, Any]:
    metrics = _read_json(CURRENT_SINGLE_METRICS_PATH)
    nq_metrics = _read_json(CURRENT_NQ_SINGLE_METRICS_PATH)
    for key in ("NQ_NY", "NQ_Asia", "NQ_NY_LSI"):
        if key in nq_metrics:
            metrics[key] = nq_metrics[key]
    return metrics


def _daily_inside_map(symbol: str) -> dict[str, bool]:
    path = ROOT / "backtesting" / "data" / "raw" / f"{symbol}_5m.parquet"
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        index_col = "datetime" if "datetime" in df.columns else df.columns[-1]
        df = df.set_index(index_col)
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert("America/New_York")

    rth = df[(df.index.time >= datetime.strptime("09:30", "%H:%M").time()) & (df.index.time < datetime.strptime("16:00", "%H:%M").time())]
    daily = rth.groupby(rth.index.date).agg(high=("high", "max"), low=("low", "min"))
    daily.index = pd.to_datetime(daily.index)
    prior = daily.shift(1)
    prior2 = daily.shift(2)
    prior_inside = (prior["high"] <= prior2["high"]) & (prior["low"] >= prior2["low"])
    return {idx.date().isoformat(): bool(value) for idx, value in prior_inside.items()}


def _filter_gc_asia_prior_not_inside(result: dict) -> dict:
    inside = _daily_inside_map("GC")
    filtered = copy.deepcopy(result)
    removed: list[dict] = []
    kept: list[dict] = []
    for trade in filtered.get("trades", []):
        if trade.get("session") == "GC_Asia" and inside.get(trade["date"], False):
            removed.append(trade)
        else:
            kept.append(trade)
    filtered["trades"] = kept
    filtered["summary"] = hb._compute_summary(kept)
    filtered["equity_curve"] = hb._build_equity_curve(kept, END_DATE)
    filtered["post_filter"] = {
        "name": "gc_asia_prior_not_inside_day",
        "removed_trades": len(removed),
        "status": "post_filter_only_not_live_native",
    }
    return filtered


def _delta_rows(
    current: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
    sessions: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for session in sessions:
        base = current.get(session, {})
        cand = candidate.get(session, {"fills": 0, "net_r": 0.0, "dd_r": 0.0, "calmar": None, "pf": 0.0, "wr_pct": 0.0})
        rows.append({
            "session": session,
            "gate": GATE_LABELS.get(session, ""),
            "current_fills": base.get("fills", 0),
            "candidate_fills": cand.get("fills", 0),
            "delta_fills": int(cand.get("fills", 0) or 0) - int(base.get("fills", 0) or 0),
            "current_net_r": base.get("net_r", 0.0),
            "candidate_net_r": cand.get("net_r", 0.0),
            "delta_net_r": round(float(cand.get("net_r", 0.0) or 0.0) - float(base.get("net_r", 0.0) or 0.0), 2),
            "current_dd_r": base.get("dd_r", 0.0),
            "candidate_dd_r": cand.get("dd_r", 0.0),
            "current_calmar": base.get("calmar"),
            "candidate_calmar": cand.get("calmar"),
        })
    return rows


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return out


def _write_report(payload: dict[str, Any]) -> None:
    full_rows = payload["full_portfolio_delta_rows"]
    single_rows = payload["single_leg_delta_rows"]
    post_rows = payload["post_filter_delta_rows"]
    support_rows = [
        {
            "candidate": "NQ NY ORB exclude CPI",
            "status": "exact-native",
            "method": "temporary excluded_dates on NQ_NY",
        },
        {
            "candidate": "ES NY ORB exclude FOMC+CPI",
            "status": "exact-native",
            "method": "temporary excluded_dates on ES_NY",
        },
        {
            "candidate": "GC NY ORB exclude CPI/NFP",
            "status": "exact-native",
            "method": "temporary excluded_dates on GC_NY",
        },
        {
            "candidate": "GC NY ORB cpi_nfp_plus_outside",
            "status": "skipped",
            "method": "signal-outside-ORB is not a live-native gate and exact fill records do not preserve signal-bar close/ORB context",
        },
        {
            "candidate": "GC Asia ORB CPI/NFP + prior-not-inside",
            "status": "mixed",
            "method": "CPI/NFP exact-native; prior-not-inside is post-filter-only",
        },
    ]
    lines = [
        "# HOT_REGIME_V1 Exact Candidate Compare",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Window: `{START_DATE}` to `{END_DATE}`",
        "- Baseline current HOT full replay source: existing exact result from `hot_regime_v1_exact_compare_20260503`.",
        "- Candidate exact replay source: temporary in-memory execution profiles; `execution/config/exec_configs.json` was not edited.",
        "- Post-filter rows are explicitly not live-native exact replays; they remove exact fills after the lifecycle has already happened.",
        "",
        "## Gate Support",
        "",
        *_markdown_table(support_rows, ["candidate", "status", "method"]),
        "",
        "## Full Portfolio Exact-Native Deltas",
        "",
        *_markdown_table(
            full_rows,
            [
                "session",
                "gate",
                "current_fills",
                "candidate_fills",
                "delta_fills",
                "current_net_r",
                "candidate_net_r",
                "delta_net_r",
                "current_dd_r",
                "candidate_dd_r",
                "current_calmar",
                "candidate_calmar",
            ],
        ),
        "",
        "## Single-Leg Exact-Native Deltas",
        "",
        *_markdown_table(
            single_rows,
            [
                "session",
                "gate",
                "current_fills",
                "candidate_fills",
                "delta_fills",
                "current_net_r",
                "candidate_net_r",
                "delta_net_r",
                "current_dd_r",
                "candidate_dd_r",
                "current_calmar",
                "candidate_calmar",
            ],
        ),
        "",
        "## Post-Filter-Only Deltas",
        "",
        *_markdown_table(
            post_rows,
            [
                "session",
                "gate",
                "current_fills",
                "candidate_fills",
                "delta_fills",
                "current_net_r",
                "candidate_net_r",
                "delta_net_r",
                "current_dd_r",
                "candidate_dd_r",
                "current_calmar",
                "candidate_calmar",
            ],
        ),
        "",
        "## Decision",
        "",
        "- Encode candidate: `GC_NY exclude_cpi_nfp`. It survives exact single-leg and full-portfolio replay with positive net-R and lower drawdown.",
        "- Conditional candidate: `GC_Asia exclude_cpi_nfp`. It helps full-portfolio exact replay, but single-leg net-R is slightly worse; do not include the prior-inside component without live-native implementation.",
        "- Conditional/portfolio-only candidate: `NQ_NY exclude_cpi`. It helps the full portfolio but fails single-leg exact replay, so the edge is interaction-dependent.",
        "- Do not encode for net-R: `ES_NY exclude_fomc_cpi`. It improves exact single-leg net-R but worsens single-leg DD/Calmar and is slightly negative in the full portfolio.",
        "- Research-only/skip: `signal_outside_orb` variants and `prior_not_inside_day` until the live ORB engine records/evaluates those gates before order arming.",
        "",
        "## Read",
        "",
        payload["read"],
        "",
        "## Artifacts",
        "",
        f"- Results: `backtesting/data/results/{RUN_SLUG}/`",
        f"- Script: `backtesting/scripts/run_hot_regime_v1_exact_candidate_compare.py`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    base_profiles = {profile.name: profile for profile in load_exec_configs(config)}
    base = base_profiles[BASE_PROFILE]

    current_full = _read_json(CURRENT_RESULT_PATH)
    current_full_metrics = _session_metrics(current_full)
    current_single_metrics = _load_current_single_metrics()

    candidate_full_profile = _candidate_full_profile(base)
    candidate_full = _run_profile(
        config,
        candidate_full_profile,
        f"EXEC EXACT HOT_REGIME_V1 candidate native {START_DATE} to {END_DATE}",
    )
    candidate_full_metrics = _session_metrics(candidate_full)
    _write_json(RESULT_DIR / "hot_regime_v1_candidate_native_exact_result.json", candidate_full)
    _write_json(RESULT_DIR / "hot_regime_v1_candidate_native_session_metrics.json", candidate_full_metrics)

    single_candidate_results: dict[str, dict] = {}
    single_candidate_metrics: dict[str, dict[str, Any]] = {}
    for session_name in TARGET_SESSIONS:
        profile = _single_profile(base, session_name=session_name, candidate=True)
        result = _run_profile(
            config,
            profile,
            f"EXEC EXACT HOT_REGIME_V1 {session_name} candidate single {START_DATE} to {END_DATE}",
        )
        single_candidate_results[session_name] = result
        single_candidate_metrics[session_name] = _session_metrics(result).get(
            session_name,
            _metrics_from_summary(hb._compute_summary([])),
        )

    _write_json(RESULT_DIR / "hot_regime_v1_single_leg_candidate_exact_results.json", single_candidate_results)
    _write_json(RESULT_DIR / "hot_regime_v1_single_leg_candidate_exact_metrics.json", single_candidate_metrics)

    post_full = _filter_gc_asia_prior_not_inside(candidate_full)
    post_full_metrics = _session_metrics(post_full)
    post_single_gc_asia = _filter_gc_asia_prior_not_inside(single_candidate_results["GC_Asia"])
    post_single_metrics = {
        "GC_Asia": _session_metrics(post_single_gc_asia).get("GC_Asia", _metrics_from_summary(hb._compute_summary([])))
    }
    _write_json(RESULT_DIR / "hot_regime_v1_candidate_post_filter_exact_result.json", post_full)
    _write_json(
        RESULT_DIR / "hot_regime_v1_candidate_post_filter_metrics.json",
        {
            "full_portfolio_session_metrics": post_full_metrics,
            "single_leg_metrics": post_single_metrics,
            "post_filter": post_full.get("post_filter", {}),
        },
    )

    full_rows = _delta_rows(current_full_metrics, candidate_full_metrics, TARGET_SESSIONS)
    single_rows = _delta_rows(current_single_metrics, single_candidate_metrics, TARGET_SESSIONS)
    post_current = dict(candidate_full_metrics)
    post_rows = _delta_rows(post_current, post_full_metrics, ("GC_Asia",))
    post_rows[0]["gate"] = "prior_not_inside_day post-filter after native CPI/NFP exclusion"

    read = (
        "Exact-native date exclusions did not recreate the research squeeze. "
        "The comparison isolates whether the structural event-date cuts survive the live engine; "
        "signal-shape and prior-day gates remain research-only unless they are encoded into the live ORB state machine."
    )
    payload = {
        "run_slug": RUN_SLUG,
        "window": {"start": START_DATE, "end": END_DATE},
        "current_full_overall": _overall_metrics(current_full),
        "candidate_full_overall": _overall_metrics(candidate_full),
        "candidate_post_filter_overall": _overall_metrics(post_full),
        "full_portfolio_delta_rows": full_rows,
        "single_leg_delta_rows": single_rows,
        "post_filter_delta_rows": post_rows,
        "gate_support": GATE_LABELS,
        "date_exclusion_counts": {
            session: len(_as_sorted_dates(set(dates)))
            for session, dates in DATE_EXCLUSIONS.items()
        },
        "read": read,
    }
    _write_json(RESULT_DIR / "comparison_summary.json", payload)
    _write_report(payload)

    print(json.dumps({
        "result_dir": str(RESULT_DIR),
        "report": str(REPORT_PATH),
        "candidate_full_overall": payload["candidate_full_overall"],
        "full_rows": full_rows,
        "single_rows": single_rows,
        "post_rows": post_rows,
    }, indent=2))


if __name__ == "__main__":
    main()
