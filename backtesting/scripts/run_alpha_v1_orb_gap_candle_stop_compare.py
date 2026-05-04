#!/usr/bin/env python3
"""Compare ALPHA_V1 ORB baseline stops vs FVG impulse-candle structural stops.

This is a one-off research probe for the three ORB legs referenced by
ALPHA_V1_ORB_REENTRY_2Y.md.  It leaves the canonical engine/configs untouched
and monkey-patches continuation candidates at runtime when the structural
variant marker is present in config notes.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import (
    build_alpha_v1_legs,
    filled_trades,
    portfolio_daily_frame,
    summarize_daily_returns,
)
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES, NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine import simulator
from orb_backtest.engine.simulator import EXIT_NAMES, TradeResult, build_maps, build_signal_cache
from orb_backtest.results.metrics import compute_metrics


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_gap_candle_stop_compare_20260503"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_GAP_CANDLE_STOP_COMPARE_20260503.md"

FULL_START = "2016-04-17"
ORB_LEG_KEYS = ("nq_asia_orb_long", "es_asia_orb_long", "es_ny_orb_long")
STRUCTURAL_MARKER = "[structural_gap_impulse_stop]"
STOP_BUFFER_POINTS = 1.0
CURRENT_RISK_USD = {
    "nq_asia_orb_long": 300.0,
    "es_asia_orb_long": 200.0,
    "es_ny_orb_long": 300.0,
}
FUNDED_PROFILE = {
    "starting_balance_usd": 50_000.0,
    "trailing_drawdown_usd": 2_000.0,
    "max_trailing_breach_usd": 50_000.0,
    "first_payout_floor_usd": 52_500.0,
    "first_payout_amount_usd": 500.0,
    "challenge_fee_usd": 150.0,
    "cohort_spacing_days": 14,
}


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * 100.0, 2)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        if abs(value) >= 100 or value == int(value):
            return f"{value:.0f}"
        return f"{value:.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _resample_agg(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return (
        df.resample(rule)
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
        .dropna(subset=["open"])
    )


def _load_market_data(symbol: str, end_date: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    instrument = NQ if symbol == "NQ" else ES
    df_1s = None
    try:
        df_5m = load_5m_data(instrument.data_file, start=FULL_START, end=end_date)
    except FileNotFoundError:
        df_5m = None
    try:
        df_1m = load_1m_for_5m(instrument.data_file, start=FULL_START, end=end_date)
    except FileNotFoundError:
        df_1m = None
    try:
        df_1s = load_1s_for_5m(instrument.data_file, start=FULL_START, end=end_date)
    except FileNotFoundError:
        pass
    if df_5m is None or df_1m is None:
        if df_1s is None:
            raise FileNotFoundError(f"{symbol} is missing 5m/1m bars and no 1s fallback exists.")
        if df_1m is None:
            df_1m = _resample_agg(df_1s, "1min")
        if df_5m is None:
            df_5m = _resample_agg(df_1s, "5min")
    return df_5m, df_1m, df_1s


def _patch_structural_stop_extractor() -> None:
    original = simulator._extract_setup_candidates

    def wrapped(df, session, config, signal_df_1m=None, _signal_cache=None):
        candidates = original(df, session, config, signal_df_1m=signal_df_1m, _signal_cache=_signal_cache)
        if STRUCTURAL_MARKER not in (config.notes or ""):
            return candidates
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        patched = []
        for cand in candidates:
            if config.strategy not in {"continuation", "reversal"}:
                patched.append(cand)
                continue
            impulse_bar = int(cand.signal_bar) - 1
            if impulse_bar < 0:
                patched.append(cand)
                continue
            if cand.direction == 1:
                structural_stop = float(low[impulse_bar]) - STOP_BUFFER_POINTS
            else:
                structural_stop = float(high[impulse_bar]) + STOP_BUFFER_POINTS
            patched.append(replace(cand, structural_stop_price=structural_stop))
        return patched

    simulator._extract_setup_candidates = wrapped


def _make_structural_config(base: StrategyConfig, leg_key: str) -> StrategyConfig:
    return with_overrides(
        base,
        name=f"{leg_key}_gap_impulse_structural_stop",
        notes=(
            f"{base.notes} {STRUCTURAL_MARKER} Stop uses FVG impulse candle "
            f"low/high plus {STOP_BUFFER_POINTS:g} point buffer; existing hard stop floors unchanged."
        ),
    )


def _sort_trades(trades: list[TradeResult]) -> list[TradeResult]:
    return sorted(trades, key=lambda t: (t.date, t.session, t.fill_bar, t.signal_bar, t.exit_bar))


def _run_leg_configs(
    symbol: str,
    configs: list[StrategyConfig],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    df_5m, df_1m, df_1s = _load_market_data(symbol, end_date=end_date)
    maps = build_maps(df_5m, df_1m, None, df_1s)
    signal_cache = build_signal_cache(df_5m, configs, signal_df_1m=df_1m)
    streams: dict[str, list[TradeResult]] = {}
    for config in configs:
        trades = simulator.run_backtest(
            df_5m,
            config,
            start_date=start_date,
            end_date=end_date,
            df_1m=df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        streams[config.name] = _sort_trades(trades)
    return streams


def _trade_rows(profile: str, leg_key: str, trades: list[TradeResult]) -> list[dict[str, Any]]:
    rows = []
    for ordinal, trade in enumerate(filled_trades(trades), start=1):
        exit_ts = pd.Timestamp(trade.exit_time or trade.fill_time or trade.date)
        fill_ts = pd.Timestamp(trade.fill_time or trade.exit_time or trade.date)
        rows.append(
            {
                "profile": profile,
                "leg": leg_key,
                "exit_ts": exit_ts,
                "fill_ts": fill_ts,
                "exit_date": exit_ts.normalize().date().isoformat(),
                "date": trade.date,
                "r_multiple": float(trade.r_multiple),
                "risk_points": float(trade.risk_points),
                "pnl_usd_current": float(trade.r_multiple) * CURRENT_RISK_USD[leg_key],
                "exit_type": trade.exit_type,
                "exit_name": EXIT_NAMES.get(trade.exit_type, str(trade.exit_type)),
            }
        )
    rows.sort(key=lambda row: (row["exit_ts"], row["leg"], row["fill_ts"]))
    return rows


def _filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end]


def _metric_row(
    *,
    scope: str,
    profile: str,
    window: str,
    trades: list[TradeResult],
    daily_streams: dict[str, list[TradeResult]] | None = None,
) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    if daily_streams is not None:
        daily = portfolio_daily_frame({name: filled_trades(stream) for name, stream in daily_streams.items()})
        total = daily.sum(axis=1) if not daily.empty else pd.Series(dtype=float)
        daily_summary = summarize_daily_returns(total)
        dd = float(daily_summary["max_drawdown_r"])
        sharpe = float(daily_summary["sharpe_ratio"])
    else:
        dd = float(metrics["max_drawdown_r"])
        sharpe = float(metrics["sharpe_ratio"])
    r_by_year = metrics.get("r_by_year") or {}
    return {
        "scope": scope,
        "profile": profile,
        "window": window,
        "signals": int(metrics["total_signals"]),
        "fills": int(metrics["total_trades"]),
        "net_r": _round(metrics["total_r"], 2),
        "dd_r": _round(dd, 2),
        "wr_pct": _pct(metrics["win_rate"]),
        "pf": _round(metrics["profit_factor"], 2),
        "avg_r": _round(metrics["avg_r"], 3),
        "sharpe": _round(sharpe, 2),
        "negative_years": int(sum(1 for value in r_by_year.values() if value < 0)),
    }


def _daily_frame(rows: list[dict[str, Any]], value_col: str) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    piv = df.pivot_table(index="exit_date", columns="leg", values=value_col, aggfunc="sum").fillna(0.0)
    piv.index = pd.to_datetime(piv.index)
    return piv.sort_index()


def simulate_first_payouts(rows: list[dict[str, Any]], *, start: str, end: str) -> list[dict[str, Any]]:
    trades = [row for row in rows if start <= row["exit_date"] <= end]
    trades.sort(key=lambda row: (row["exit_ts"], row["leg"], row["fill_ts"]))
    if not trades:
        return []
    cohort_starts = pd.date_range(
        pd.Timestamp(start).normalize(),
        pd.Timestamp(end).normalize(),
        freq=f"{int(FUNDED_PROFILE['cohort_spacing_days'])}D",
    )
    outcomes = []
    for account_id, cohort_start in enumerate(cohort_starts, start=1):
        balance = float(FUNDED_PROFILE["starting_balance_usd"])
        floor = balance - float(FUNDED_PROFILE["trailing_drawdown_usd"])
        high_eod = balance
        current_day = None
        trade_count = 0
        outcome = "open"
        outcome_date = pd.Timestamp(end).date().isoformat()
        for row in [trade for trade in trades if trade["exit_ts"] >= cohort_start]:
            trade_day = row["exit_date"]
            if current_day is not None and trade_day != current_day:
                high_eod = max(high_eod, balance)
                floor = max(floor, min(high_eod - float(FUNDED_PROFILE["trailing_drawdown_usd"]), float(FUNDED_PROFILE["max_trailing_breach_usd"])))
            current_day = trade_day
            balance += float(row["pnl_usd_current"])
            trade_count += 1
            if balance <= floor:
                outcome = "breach"
                outcome_date = trade_day
                break
            if balance >= float(FUNDED_PROFILE["first_payout_floor_usd"]):
                outcome = "payout"
                outcome_date = trade_day
                break
        net_after_fee = (
            float(FUNDED_PROFILE["first_payout_amount_usd"]) - float(FUNDED_PROFILE["challenge_fee_usd"])
            if outcome == "payout"
            else -float(FUNDED_PROFILE["challenge_fee_usd"])
        )
        outcomes.append(
            {
                "account_id": account_id,
                "start_date": cohort_start.date().isoformat(),
                "outcome": outcome,
                "outcome_date": outcome_date,
                "days_to_outcome": int((pd.Timestamp(outcome_date) - cohort_start).days),
                "trades_to_outcome": trade_count,
                "net_after_fee_usd": _round(net_after_fee, 2),
            }
        )
    return outcomes


def summarize_payouts(profile: str, window: str, outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    payouts = [row for row in outcomes if row["outcome"] == "payout"]
    breaches = [row for row in outcomes if row["outcome"] == "breach"]
    max_run = 0
    run = 0
    for row in outcomes:
        if row["outcome"] == "breach":
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return {
        "profile": profile,
        "window": window,
        "accounts": len(outcomes),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": sum(1 for row in outcomes if row["outcome"] == "open"),
        "payout_rate_pct": _pct(len(payouts) / len(outcomes)) if outcomes else 0.0,
        "breach_rate_pct": _pct(len(breaches) / len(outcomes)) if outcomes else 0.0,
        "ev_per_account_usd": _round(float(np.mean([row["net_after_fee_usd"] for row in outcomes])), 2) if outcomes else 0.0,
        "median_days_to_payout": _round(float(np.median([row["days_to_outcome"] for row in payouts])), 1) if payouts else None,
        "max_consecutive_breaches": max_run,
    }


def _add_deltas(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    baseline = {
        (row["scope"], row["window"]): row
        for row in rows
        if row["profile"] == "current_stop"
    }
    out = []
    for row in rows:
        new = dict(row)
        base = baseline.get((row["scope"], row["window"]))
        if base is not None and row["profile"] != "current_stop":
            for key in keys:
                new[f"delta_{key}"] = _round(float(row[key]) - float(base[key]), 2)
        else:
            for key in keys:
                new[f"delta_{key}"] = 0.0
        out.append(new)
    return out


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    _patch_structural_stop_extractor()

    base_legs = build_alpha_v1_legs()
    leg_configs: dict[str, tuple[StrategyConfig, StrategyConfig]] = {}
    for leg_key in ORB_LEG_KEYS:
        base = base_legs[leg_key].config
        leg_configs[leg_key] = (base, _make_structural_config(base, leg_key))

    end_dates = []
    for symbol in ("NQ", "ES"):
        df_5m, _, _ = _load_market_data(symbol)
        end_dates.append(pd.Timestamp(df_5m.index.max()).date())
    overlap_end = min(end_dates).isoformat()
    windows = {
        "10yr": (FULL_START, overlap_end),
        "2024": ("2024-01-01", "2024-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "2026": ("2026-01-01", overlap_end),
    }
    print(f"overlap: {FULL_START} -> {overlap_end}", flush=True)

    streams: dict[str, dict[str, list[TradeResult]]] = {"current_stop": {}, "gap_impulse_stop": {}}
    for symbol in ("NQ", "ES"):
        symbol_leg_keys = [key for key in ORB_LEG_KEYS if base_legs[key].config.instrument.symbol == symbol]
        configs = []
        for key in symbol_leg_keys:
            configs.extend(leg_configs[key])
        print(f"running {symbol}: {len(configs)} configs", flush=True)
        by_name = _run_leg_configs(symbol, configs, start_date=FULL_START, end_date=overlap_end)
        for key in symbol_leg_keys:
            base, structural = leg_configs[key]
            streams["current_stop"][key] = by_name[base.name]
            streams["gap_impulse_stop"][key] = by_name[structural.name]

    metric_rows = []
    for window, (start, end) in windows.items():
        for profile in ("current_stop", "gap_impulse_stop"):
            combined_streams = {
                key: _filter_window(streams[profile][key], start, end)
                for key in ORB_LEG_KEYS
            }
            combined_trades = [trade for stream in combined_streams.values() for trade in stream]
            metric_rows.append(
                _metric_row(
                    scope="combined_orb_sleeve",
                    profile=profile,
                    window=window,
                    trades=combined_trades,
                    daily_streams=combined_streams,
                )
            )
            for key in ORB_LEG_KEYS:
                metric_rows.append(
                    _metric_row(
                        scope=key,
                        profile=profile,
                        window=window,
                        trades=combined_streams[key],
                    )
                )

    metric_rows = _add_deltas(metric_rows, ("net_r", "dd_r"))
    all_trade_rows = {
        profile: [
            row
            for key in ORB_LEG_KEYS
            for row in _trade_rows(profile, key, streams[profile][key])
        ]
        for profile in ("current_stop", "gap_impulse_stop")
    }

    payout_rows = []
    payout_summaries = []
    for window, (start, end) in windows.items():
        for profile in ("current_stop", "gap_impulse_stop"):
            outcomes = simulate_first_payouts(all_trade_rows[profile], start=start, end=end)
            for row in outcomes:
                row["profile"] = profile
                row["window"] = window
            payout_rows.extend(outcomes)
            payout_summaries.append(summarize_payouts(profile, window, outcomes))

    payout_summaries = _add_deltas(
        [{"scope": "combined_orb_sleeve", **row} for row in payout_summaries],
        ("payouts", "breaches", "ev_per_account_usd"),
    )

    pd.DataFrame(metric_rows).to_csv(RESULT_DIR / "metrics_by_scope_window.csv", index=False)
    pd.DataFrame(payout_summaries).to_csv(RESULT_DIR / "funded_first_payout_summary.csv", index=False)
    pd.DataFrame(payout_rows).to_csv(RESULT_DIR / "funded_first_payout_accounts.csv", index=False)
    for profile, rows in all_trade_rows.items():
        pd.DataFrame(rows).drop(columns=["fill_ts", "exit_ts"], errors="ignore").to_csv(
            RESULT_DIR / f"{profile}_filled_trades.csv",
            index=False,
        )

    summary = {
        "run": "alpha_v1_orb_gap_candle_stop_compare_20260503",
        "overlap_start": FULL_START,
        "overlap_end": overlap_end,
        "stop_variant": "FVG impulse candle low/high +/- 1.0 point, with engine hard stop floors unchanged",
        "orb_legs": list(ORB_LEG_KEYS),
        "funded_profile": FUNDED_PROFILE,
        "metrics": metric_rows,
        "funded_first_payout_summary": payout_summaries,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    combined_rows = [row for row in metric_rows if row["scope"] == "combined_orb_sleeve"]
    combined_cols = [
        "window", "profile", "fills", "net_r", "delta_net_r", "dd_r", "delta_dd_r",
        "wr_pct", "pf", "avg_r", "sharpe", "negative_years",
    ]
    leg_cols = ["scope", "window", "profile", "fills", "net_r", "delta_net_r", "dd_r", "delta_dd_r", "pf"]
    payout_cols = [
        "window", "profile", "accounts", "payouts", "delta_payouts", "breaches", "delta_breaches",
        "open", "payout_rate_pct", "breach_rate_pct", "ev_per_account_usd", "delta_ev_per_account_usd",
        "median_days_to_payout", "max_consecutive_breaches",
    ]
    lines = [
        "# ALPHA_V1 ORB Gap-Candle Stop Compare (2026-05-03)",
        "",
        f"- Window: `{FULL_START}` to `{overlap_end}`",
        "- Scope: NQ Asia ORB, ES Asia ORB, ES NY ORB from `ALPHA_V1_ORB_REENTRY_2Y.md`.",
        "- Variant: current stop logic versus FVG impulse-candle structural stop.",
        f"- Structural stop: long `low[signal_bar - 1] - {STOP_BUFFER_POINTS:g}`; short `high[signal_bar - 1] + {STOP_BUFFER_POINTS:g}`. Existing engine hard floors remain active: at least 5% daily ATR and each leg's configured point floor.",
        "",
        "## Combined ORB Sleeve",
        "",
        _markdown_table(combined_rows, combined_cols),
        "",
        "## Funded First-Payout Model",
        "",
        "- Model: $50k account, $2k trailing drawdown capped at $50k, first payout at $52.5k, $500 first withdrawal, $150 challenge fee, new cohort every 14 calendar days.",
        "",
        _markdown_table(payout_summaries, payout_cols),
        "",
        "## Per-Leg Metrics",
        "",
        _markdown_table([row for row in metric_rows if row["scope"] != "combined_orb_sleeve"], leg_cols),
        "",
        "## Artifacts",
        "",
        f"- Result directory: `{RESULT_DIR.relative_to(ROOT)}`",
        "- `metrics_by_scope_window.csv`",
        "- `funded_first_payout_summary.csv`",
        "- `current_stop_filled_trades.csv`",
        "- `gap_impulse_stop_filled_trades.csv`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT_PATH)
    print(RESULT_DIR / "summary.json")


if __name__ == "__main__":
    main()
