#!/usr/bin/env python3
"""NQ NY neutral ORB gate workflow.

Tests causal day-level gates suggested by the 10-year regime diagnostic while
keeping the user's neutral strategy anchor fixed:

- NY 09:30-09:45 ORB
- first 5m continuation FVG outside the range
- 10% ATR stop, 2% ATR gap
- single-target 2R exit

Performance is evaluated on 2021-2024 only; 2025+ remains untouched holdout.
Volatility/ORB thresholds are calibrated from 2016-2020 market distributions,
not from 2021-2024 trade outcomes.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import default_config, with_overrides  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data  # noqa: E402
from orb_backtest.discovery.tools import _mfe_diagnostics  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.validate.deflated_sharpe import (  # noqa: E402
    compute_dsr,
    compute_psr,
    estimate_effective_trials,
)


RUN_ID = "nq_ny_orb_neutral_gate_workflow_2021_20260608"
RESULT_DIR = ROOT / "data" / "results" / "discovery_runs" / RUN_ID
ARTIFACT_DIR = RESULT_DIR / "artifacts"
DATA_FILE = ROOT / "data" / "cache" / "nq_ny_lsi_cisd_sequence" / "NQ_5m.parquet"

CALIBRATION_START = "2016-01-01"
CALIBRATION_END = "2020-12-31"
DISCOVERY_START = "2021-01-01"
DISCOVERY_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"

MIN_TRADES = 40
MONDAY = 0


@dataclass(frozen=True)
class GateRule:
    """A tested candidate rule."""

    rule_id: str
    direction: str
    exclude_monday: bool
    atr_gate: str
    orb_gate: str
    deployability: str
    live_support_notes: str


def _base_config(direction: str):
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        risk_usd=5000.0,
        rr=2.0,
        tp1_ratio=1.0,
        exit_mode="single_target",
        continuation_fvg_selection="first",
        orb_trade_max_per_session=1,
        impulse_close_filter=False,
        use_bar_magnifier=True,
        strategy="continuation",
        direction_filter=direction,
        ny_orb_start="09:30",
        ny_orb_end="09:45",
        ny_entry_start="09:45",
        ny_entry_end="13:00",
        ny_flat_start="15:50",
        ny_flat_end="16:00",
        ny_stop_atr_pct=10.0,
        ny_min_gap_atr_pct=2.0,
        name=f"{RUN_ID} {direction}",
    )


def _daily_context(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
    )
    prev_close = daily["close"].shift(1)
    true_range = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily["atr14"] = true_range.rolling(14, min_periods=14).mean()
    daily["prior_atr14_pct"] = (daily["atr14"] / daily["close"] * 100.0).shift(1)
    daily["date"] = daily.index.date
    return daily


def _orb_context(df: pd.DataFrame) -> pd.DataFrame:
    intraday = df.between_time("09:30", "09:40")
    rows: list[dict[str, Any]] = []
    for session_date, group in intraday.groupby(intraday.index.date):
        if group.empty:
            continue
        orb_open = float(group["open"].iloc[0])
        if not np.isfinite(orb_open) or orb_open <= 0:
            continue
        orb_high = float(group["high"].max())
        orb_low = float(group["low"].min())
        rows.append(
            {
                "date": session_date,
                "orb_range_pct": (orb_high - orb_low) / orb_open * 100.0,
            }
        )
    return pd.DataFrame(rows)


def _context_maps(df: pd.DataFrame) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    daily = _daily_context(df)
    orb = _orb_context(df)
    context = daily[["date", "prior_atr14_pct"]].merge(orb, on="date", how="left")

    calibration = context[
        (context["date"] >= date.fromisoformat(CALIBRATION_START))
        & (context["date"] <= date.fromisoformat(CALIBRATION_END))
    ]
    thresholds = {
        "atr_p33": float(calibration["prior_atr14_pct"].quantile(1 / 3)),
        "atr_p66": float(calibration["prior_atr14_pct"].quantile(2 / 3)),
        "orb_p33": float(calibration["orb_range_pct"].quantile(1 / 3)),
        "orb_p66": float(calibration["orb_range_pct"].quantile(2 / 3)),
    }
    atr_by_date = {
        d.isoformat(): float(v)
        for d, v in zip(context["date"], context["prior_atr14_pct"], strict=False)
        if pd.notna(v)
    }
    orb_by_date = {
        d.isoformat(): float(v)
        for d, v in zip(context["date"], context["orb_range_pct"], strict=False)
        if pd.notna(v)
    }
    return thresholds, atr_by_date, orb_by_date


def _rules() -> list[GateRule]:
    rules = [
        GateRule(
            rule_id="baseline_both",
            direction="both",
            exclude_monday=False,
            atr_gate="none",
            orb_gate="none",
            deployability="live_native",
            live_support_notes="Native StrategyConfig direction/session parameters; exact replay still required.",
        ),
        GateRule(
            rule_id="baseline_both_no_monday",
            direction="both",
            exclude_monday=True,
            atr_gate="none",
            orb_gate="none",
            deployability="live_native",
            live_support_notes="Monday skip is known before order arming; exact replay still required.",
        ),
    ]
    for exclude_monday in (False, True):
        for atr_gate in ("none", "low_or_mid_atr", "low_atr_only"):
            for orb_gate in ("none", "small_or_mid_orb", "small_orb_only", "large_orb_only"):
                rule_id = "__".join(
                    part
                    for part in [
                        "long",
                        "no_monday" if exclude_monday else "",
                        atr_gate if atr_gate != "none" else "",
                        orb_gate if orb_gate != "none" else "",
                    ]
                    if part
                )
                has_context_gate = atr_gate != "none" or orb_gate != "none"
                deployability = "post_filter_only" if has_context_gate else "live_native"
                notes = (
                    "ATR/ORB gates are causal and known before entry, but are applied here as research filters; "
                    "add native pre-trade config gates before execution."
                    if has_context_gate
                    else "Long-only and optional Monday skip are native/live-known StrategyConfig logic; exact replay still required."
                )
                rules.append(
                    GateRule(
                        rule_id=rule_id,
                        direction="long",
                        exclude_monday=exclude_monday,
                        atr_gate=atr_gate,
                        orb_gate=orb_gate,
                        deployability=deployability,
                        live_support_notes=notes,
                    )
                )
    return rules


def _passes_gate(
    trade: TradeResult,
    rule: GateRule,
    thresholds: dict[str, float],
    atr_by_date: dict[str, float],
    orb_by_date: dict[str, float],
) -> bool:
    if rule.exclude_monday and datetime.strptime(trade.date, "%Y-%m-%d").weekday() == MONDAY:
        return False

    atr_value = atr_by_date.get(trade.date)
    if rule.atr_gate == "low_or_mid_atr" and atr_value is not None and atr_value > thresholds["atr_p66"]:
        return False
    if rule.atr_gate == "low_atr_only" and atr_value is not None and atr_value > thresholds["atr_p33"]:
        return False

    orb_value = orb_by_date.get(trade.date)
    if rule.orb_gate == "small_or_mid_orb" and orb_value is not None and orb_value > thresholds["orb_p66"]:
        return False
    if rule.orb_gate == "small_orb_only" and orb_value is not None and orb_value > thresholds["orb_p33"]:
        return False
    if rule.orb_gate == "large_orb_only" and orb_value is not None and orb_value <= thresholds["orb_p66"]:
        return False

    return True


def _apply_rule(
    trades: list[TradeResult],
    rule: GateRule,
    thresholds: dict[str, float],
    atr_by_date: dict[str, float],
    orb_by_date: dict[str, float],
) -> list[TradeResult]:
    return [trade for trade in trades if _passes_gate(trade, rule, thresholds, atr_by_date, orb_by_date)]


def _date_filter(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end]


def _r_multiples(trades: list[TradeResult]) -> np.ndarray:
    return np.asarray(
        [
            float(getattr(trade, "net_r_multiple", 0.0) or trade.r_multiple)
            for trade in trades
            if trade.exit_type != EXIT_NO_FILL
        ],
        dtype=float,
    )


def _trade_dates(trades: list[TradeResult]) -> set[str]:
    return {trade.date for trade in trades if trade.exit_type != EXIT_NO_FILL}


def _capture(mfe_trades: list[dict[str, Any]]) -> float:
    mfe_sum = sum(float(row["mfe_r"]) for row in mfe_trades)
    if mfe_sum <= 0:
        return 0.0
    return sum(float(row["realized_r"]) for row in mfe_trades) / mfe_sum


def _metrics_row(
    rule: GateRule,
    trades: list[TradeResult],
    config: Any,
    mfe_df: pd.DataFrame | None,
    *,
    n_trials_raw: int,
    n_trials_effective: int,
) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    mfe = _mfe_diagnostics(trades, mfe_df, config)
    r_values = _r_multiples(trades)
    psr = compute_psr(r_values)
    dsr = compute_dsr(r_values, n_trials_raw=n_trials_raw, n_trials_effective=n_trials_effective)
    r_by_year = {str(year): round(float(metrics.get("r_by_year", {}).get(str(year), 0.0)), 4) for year in range(2021, 2025)}
    positive_years = sum(1 for value in r_by_year.values() if value > 0)
    return {
        "rule_id": rule.rule_id,
        "direction": rule.direction,
        "exclude_monday": rule.exclude_monday,
        "atr_gate": rule.atr_gate,
        "orb_gate": rule.orb_gate,
        "deployability": rule.deployability,
        "live_support_notes": rule.live_support_notes,
        "exact_replay_required": True,
        "total_trades": int(metrics.get("total_trades", 0)),
        "total_r": round(float(metrics.get("total_r", 0.0)), 4),
        "avg_r": round(float(metrics.get("avg_r", 0.0)), 4),
        "win_rate_pct": round(float(metrics.get("win_rate", 0.0)) * 100.0, 2),
        "profit_factor": round(float(metrics.get("profit_factor", 0.0)), 4),
        "max_drawdown_r": round(float(metrics.get("max_drawdown_r", 0.0)), 4),
        "calmar": round(float(metrics.get("calmar_ratio", 0.0)), 4),
        "sharpe": round(float(metrics.get("sharpe_ratio", 0.0)), 4),
        "r_by_year": r_by_year,
        "positive_years": positive_years,
        "min_year_r": round(min(r_by_year.values()) if r_by_year else 0.0, 4),
        "r_2022_2023": round(r_by_year.get("2022", 0.0) + r_by_year.get("2023", 0.0), 4),
        "mfe": mfe["summary"],
        "realized_to_mfe_capture": round(_capture(mfe["trades"]), 4),
        "exit_breakdown": metrics.get("exit_breakdown", {}),
        "psr": psr.psr,
        "dsr": dsr.dsr,
        "observed_sharpe_psr": psr.observed_sharpe,
        "n_trials_raw": n_trials_raw,
        "n_trials_effective": n_trials_effective,
        "trade_dates": sorted(_trade_dates(trades)),
    }


def _candidate_sort_key(row: dict[str, Any]) -> tuple[float, float, float, float]:
    min_trade_penalty = 0.0 if row["total_trades"] >= MIN_TRADES else -9999.0
    return (
        min_trade_penalty + row["r_2022_2023"],
        row["min_year_r"],
        row["calmar"],
        row["total_r"],
    )


def _passes_promotion_stats(row: dict[str, Any]) -> bool:
    return (
        row["total_trades"] >= MIN_TRADES
        and row["psr"] >= 0.85
        and row["dsr"] >= 0.50
        and row["min_year_r"] >= 0.0
    )


def _folds() -> list[tuple[str, str, str, str]]:
    folds: list[tuple[str, str, str, str]] = []
    is_start = pd.Timestamp(DISCOVERY_START)
    final_end = pd.Timestamp(DISCOVERY_END)
    while True:
        is_end = is_start + pd.DateOffset(months=12) - pd.DateOffset(days=1)
        oos_start = is_end + pd.DateOffset(days=1)
        oos_end = oos_start + pd.DateOffset(months=3) - pd.DateOffset(days=1)
        if oos_end > final_end:
            break
        folds.append(
            (
                is_start.strftime("%Y-%m-%d"),
                is_end.strftime("%Y-%m-%d"),
                oos_start.strftime("%Y-%m-%d"),
                oos_end.strftime("%Y-%m-%d"),
            )
        )
        is_start = is_start + pd.DateOffset(months=3)
    return folds


def _wf_select(
    rules: list[GateRule],
    streams: dict[str, list[TradeResult]],
    thresholds: dict[str, float],
    atr_by_date: dict[str, float],
    orb_by_date: dict[str, float],
) -> dict[str, Any]:
    fold_rows: list[dict[str, Any]] = []
    combined_oos: list[TradeResult] = []

    for is_start, is_end, oos_start, oos_end in _folds():
        scored: list[tuple[tuple[float, float, float], GateRule, list[TradeResult], dict[str, Any]]] = []
        for rule in rules:
            trades = _date_filter(
                _apply_rule(streams[rule.direction], rule, thresholds, atr_by_date, orb_by_date),
                is_start,
                is_end,
            )
            metrics = compute_metrics(trades)
            if int(metrics.get("total_trades", 0)) < 20:
                continue
            score = (
                float(metrics.get("calmar_ratio", 0.0)),
                float(metrics.get("total_r", 0.0)),
                float(metrics.get("profit_factor", 0.0)),
            )
            scored.append((score, rule, trades, metrics))
        if not scored:
            continue
        scored.sort(key=lambda item: item[0], reverse=True)
        _, selected, _, is_metrics = scored[0]
        oos_trades = _date_filter(
            _apply_rule(streams[selected.direction], selected, thresholds, atr_by_date, orb_by_date),
            oos_start,
            oos_end,
        )
        oos_metrics = compute_metrics(oos_trades)
        combined_oos.extend(oos_trades)
        fold_rows.append(
            {
                "is_start": is_start,
                "is_end": is_end,
                "oos_start": oos_start,
                "oos_end": oos_end,
                "selected_rule": selected.rule_id,
                "is_trades": int(is_metrics.get("total_trades", 0)),
                "is_total_r": round(float(is_metrics.get("total_r", 0.0)), 4),
                "is_calmar": round(float(is_metrics.get("calmar_ratio", 0.0)), 4),
                "oos_trades": int(oos_metrics.get("total_trades", 0)),
                "oos_total_r": round(float(oos_metrics.get("total_r", 0.0)), 4),
                "oos_calmar": round(float(oos_metrics.get("calmar_ratio", 0.0)), 4),
                "oos_r_by_year": oos_metrics.get("r_by_year", {}),
            }
        )

    combined = compute_metrics(combined_oos)
    return {
        "settings": {"is_months": 12, "oos_months": 3, "step_months": 3, "objective": "calmar"},
        "folds": fold_rows,
        "selected_rule_counts": dict(Counter(row["selected_rule"] for row in fold_rows)),
        "combined_oos_metrics": {
            "total_trades": int(combined.get("total_trades", 0)),
            "total_r": round(float(combined.get("total_r", 0.0)), 4),
            "avg_r": round(float(combined.get("avg_r", 0.0)), 4),
            "win_rate_pct": round(float(combined.get("win_rate", 0.0)) * 100.0, 2),
            "profit_factor": round(float(combined.get("profit_factor", 0.0)), 4),
            "max_drawdown_r": round(float(combined.get("max_drawdown_r", 0.0)), 4),
            "calmar": round(float(combined.get("calmar_ratio", 0.0)), 4),
            "r_by_year": {str(k): round(float(v), 4) for k, v in combined.get("r_by_year", {}).items()},
        },
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    rows = payload["candidate_rows"]
    top_rows = sorted(rows, key=_candidate_sort_key, reverse=True)[:12]
    wf = payload["walk_forward_selection"]

    lines = [
        f"# NQ NY Neutral ORB Gate Workflow: {RUN_ID}",
        "",
        f"- Discovery/evaluation window: `{DISCOVERY_START}` to `{DISCOVERY_END}`",
        f"- Frozen holdout starts: `{HOLDOUT_START}`; no holdout trades were loaded or tested.",
        "- Anchor: `1:2R`, single target, NY 09:30-09:45 ORB, first 5m continuation FVG, 10% ATR stop, 2% ATR gap.",
        "- Threshold calibration: market-only `2016-01-01` to `2020-12-31` distributions.",
        f"- Raw candidate rules tested: `{payload['trial_counts']['n_trials_raw']}`; effective trials: `{payload['trial_counts']['n_trials_effective']}`.",
        "",
        "## Thresholds",
        "",
        f"- Low ATR cutoff: prior-day ATR14% <= `{payload['thresholds']['atr_p33']:.4f}`",
        f"- Low/mid ATR cutoff: prior-day ATR14% <= `{payload['thresholds']['atr_p66']:.4f}`",
        f"- Small ORB cutoff: ORB range% <= `{payload['thresholds']['orb_p33']:.4f}`",
        f"- Small/mid ORB cutoff: ORB range% <= `{payload['thresholds']['orb_p66']:.4f}`",
        "",
        "## Top Candidate Rules",
        "",
        "| Rule | Deploy | Trades | R | 22+23 R | Min Year R | PF | DD R | Calmar | PSR | DSR | MFE p50 | Capture | Years |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in top_rows:
        years = ", ".join(f"{year}:{value:+.1f}" for year, value in row["r_by_year"].items())
        lines.append(
            "| "
            f"`{row['rule_id']}` | "
            f"`{row['deployability']}` | "
            f"{row['total_trades']} | "
            f"{row['total_r']:.2f} | "
            f"{row['r_2022_2023']:.2f} | "
            f"{row['min_year_r']:.2f} | "
            f"{row['profit_factor']:.2f} | "
            f"{row['max_drawdown_r']:.2f} | "
            f"{row['calmar']:.2f} | "
            f"{row['psr']:.4f} | "
            f"{row['dsr']:.4f} | "
            f"{row['mfe']['p50_mfe_r']:.2f} | "
            f"{row['realized_to_mfe_capture']:.2f} | "
            f"{years} |"
        )

    best = payload["selected_candidate"]
    lines.extend(
        [
            "",
            "## Selected Candidate Read",
            "",
            f"- Selected rule: `{best['rule_id']}`",
            f"- Verdict: `{best['verdict']}`",
            f"- Reason: {best['selection_reason']}",
            f"- Deployability: `{best['deployability']}`",
            f"- Live support note: {best['live_support_notes']}",
            "",
            "## Rolling 12m/3m Selection Check",
            "",
            f"- Combined OOS trades: `{wf['combined_oos_metrics']['total_trades']}`",
            f"- Combined OOS R: `{wf['combined_oos_metrics']['total_r']:.2f}`",
            f"- Combined OOS PF/DD/Calmar: `{wf['combined_oos_metrics']['profit_factor']:.2f}` / `{wf['combined_oos_metrics']['max_drawdown_r']:.2f}` / `{wf['combined_oos_metrics']['calmar']:.2f}`",
            f"- Selected rule counts: `{json.dumps(wf['selected_rule_counts'], sort_keys=True)}`",
            "",
            "| OOS Window | Selected Rule | OOS Trades | OOS R | OOS Calmar |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in wf["folds"]:
        lines.append(
            f"| {row['oos_start']} to {row['oos_end']} | `{row['selected_rule']}` | "
            f"{row['oos_trades']} | {row['oos_total_r']:.2f} | {row['oos_calmar']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- This is candidate discovery, not final deployment approval.",
            "- ATR/ORB context gates are causal but not currently native StrategyConfig fields in this workflow; exact replay should wait until they are implemented as pre-trade engine gates.",
            "- 2025+ remains untouched for phase-one/holdout validation.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_5m_data(str(DATA_FILE), start=CALIBRATION_START, end=DISCOVERY_END)
    try:
        df_1m = load_1m_for_5m(str(DATA_FILE), start=CALIBRATION_START, end=DISCOVERY_END)
    except FileNotFoundError:
        df_1m = None

    thresholds, atr_by_date, orb_by_date = _context_maps(df)
    configs = {"both": _base_config("both"), "long": _base_config("long")}
    streams = {
        direction: run_backtest(
            df,
            config,
            start_date=DISCOVERY_START,
            end_date=DISCOVERY_END,
            df_1m=df_1m,
            signal_df_1m=df_1m,
        )
        for direction, config in configs.items()
    }
    rules = _rules()

    trade_date_sets = [
        _trade_dates(_apply_rule(streams[rule.direction], rule, thresholds, atr_by_date, orb_by_date))
        for rule in rules
    ]
    n_trials_raw = len(rules)
    n_trials_effective = estimate_effective_trials(trade_date_sets)

    rows = [
        _metrics_row(
            rule,
            _apply_rule(streams[rule.direction], rule, thresholds, atr_by_date, orb_by_date),
            configs[rule.direction],
            df_1m if df_1m is not None else df,
            n_trials_raw=n_trials_raw,
            n_trials_effective=n_trials_effective,
        )
        for rule in rules
    ]
    promotable = [row for row in rows if _passes_promotion_stats(row)]
    live_native_promotable = [row for row in promotable if row["deployability"] == "live_native"]
    if live_native_promotable:
        selected = sorted(live_native_promotable, key=_candidate_sort_key, reverse=True)[0]
        verdict = "PROMOTE"
        reason = "Best live-native rule passing min-trades, annual-floor, PSR, and DSR gates."
    elif promotable:
        selected = sorted(promotable, key=_candidate_sort_key, reverse=True)[0]
        verdict = "CHALLENGER"
        reason = (
            "Best rule passing min-trades, annual-floor, PSR, and DSR gates, "
            "but native ATR/ORB pre-trade gates must be implemented before exact replay."
        )
    else:
        selected = sorted(rows, key=_candidate_sort_key, reverse=True)[0]
        verdict = "REJECT"
        reason = "No candidate passed the min-trades, annual-floor, PSR, and DSR promotion gates."
    selected = dict(selected)
    selected["verdict"] = verdict
    selected["selection_reason"] = reason

    wf = _wf_select(rules, streams, thresholds, atr_by_date, orb_by_date)

    payload = {
        "run_id": RUN_ID,
        "source_runs": [
            "nq_ny_orb_neutral_20260608",
            "nq_ny_orb_mfe_exit_direction_2021_20260608",
        ],
        "data": {
            "data_file": str(DATA_FILE),
            "calibration_start": CALIBRATION_START,
            "calibration_end": CALIBRATION_END,
            "discovery_start": DISCOVERY_START,
            "discovery_end": DISCOVERY_END,
            "holdout_start": HOLDOUT_START,
        },
        "anchor_config": {
            "rr": 2.0,
            "tp1_ratio": 1.0,
            "exit_mode": "single_target",
            "strategy": "continuation",
            "session": "NY",
            "orb_window": "09:30-09:45",
            "entry_window": "09:45-13:00",
            "flat_window": "15:50-16:00",
            "stop_atr_pct": 10.0,
            "min_gap_atr_pct": 2.0,
            "atr_length": 14,
            "continuation_fvg_selection": "first",
        },
        "thresholds": thresholds,
        "trial_counts": {
            "n_trials_raw": n_trials_raw,
            "n_trials_effective": n_trials_effective,
            "min_trades": MIN_TRADES,
        },
        "candidate_rows": sorted(rows, key=_candidate_sort_key, reverse=True),
        "selected_candidate": selected,
        "walk_forward_selection": wf,
        "pbo_cscv": {
            "implemented": False,
            "note": "This workflow computes PSR/DSR/effective trials; CSCV/PBO is not implemented here.",
        },
    }

    json_path = ARTIFACT_DIR / "gate_workflow_results.json"
    md_path = ARTIFACT_DIR / "gate_workflow_results.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n")
    md_path.write_text(_render_markdown(payload) + "\n")
    print(json.dumps({"success": True, "json": str(json_path), "markdown": str(md_path), "selected": selected["rule_id"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
