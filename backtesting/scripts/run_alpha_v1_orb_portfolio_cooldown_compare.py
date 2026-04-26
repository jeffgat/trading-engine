#!/usr/bin/env python3
"""Compare ALPHA_V1 ORB portfolio under cooldown-capped stagger launches.

Model:
- Seed one account on the first trading day of the window
- Launch another account whenever the master daily R stream moves another
  +/-2R away from the last launch anchor
- Cap fresh launches at one account per start date
- Enforce a minimum calendar-day cooldown between launch dates
- Account resolution uses the same daily R stream with +5R payout / -4R breach
"""

from __future__ import annotations

import gc
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import build_alpha_v1_legs, filled_trades, summarize_daily_returns
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import TradeResult, build_maps, build_signal_cache
from orb_backtest.optimize.parallel import run_sweep


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_portfolio_cooldown_compare"
SUMMARY_PATH = RESULT_DIR / "summary.json"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_PORTFOLIO_COOLDOWN_COMPARE.md"

FULL_START = "2016-04-17"
AVAILABLE_END = "2026-03-24"

PAYOUT_R = 5.0
BREACH_R = -4.0
R_TRIGGER = 2.0
COOLDOWNS = (
    (1, "1 day"),
    (7, "7 days"),
    (14, "14 days"),
)

ORB_LEG_KEYS = (
    "nq_asia_orb_long",
    "es_asia_orb_long",
    "es_ny_orb_long",
)
PROFILE_SPECS = {
    "current_single_trade": {
        "label": "Current single-trade legs",
        "orb_trade_max_per_session_by_leg": {
            "nq_asia_orb_long": 1,
            "es_asia_orb_long": 1,
            "es_ny_orb_long": 1,
        },
        "orb_reentry_policy_by_leg": {
            "nq_asia_orb_long": "any_reentry",
            "es_asia_orb_long": "any_reentry",
            "es_ny_orb_long": "any_reentry",
        },
    },
    "optimized_rules": {
        "label": "Optimized rules",
        "orb_trade_max_per_session_by_leg": {
            "nq_asia_orb_long": 2,
            "es_asia_orb_long": 2,
            "es_ny_orb_long": 2,
        },
        "orb_reentry_policy_by_leg": {
            "nq_asia_orb_long": "after_nonpositive_first",
            "es_asia_orb_long": "after_nonpositive_first",
            "es_ny_orb_long": "any_reentry",
        },
    },
}
WINDOWS = (
    {
        "key": "last_10y_available",
        "label": "Last 10y available",
        "start": FULL_START,
        "end": AVAILABLE_END,
    },
    {
        "key": "calendar_2024",
        "label": "2024",
        "start": "2024-01-01",
        "end": "2024-12-31",
    },
    {
        "key": "calendar_2025",
        "label": "2025",
        "start": "2025-01-01",
        "end": "2025-12-31",
    },
    {
        "key": "calendar_2026_ytd",
        "label": "2026 YTD",
        "start": "2026-01-01",
        "end": AVAILABLE_END,
    },
)


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


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
    return "\n".join([header, sep, *body]) if body else "\n".join([header, sep])


def _resample_agg(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open"])


def _load_market_data(base_config: StrategyConfig) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    symbol = base_config.instrument.symbol
    df_5m: pd.DataFrame | None
    df_1m: pd.DataFrame | None
    df_1s: pd.DataFrame | None

    try:
        df_5m = load_5m_data(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    except FileNotFoundError:
        df_5m = None

    try:
        df_1m = load_1m_for_5m(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    except FileNotFoundError:
        df_1m = None

    try:
        df_1s = load_1s_for_5m(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    except FileNotFoundError:
        df_1s = None

    if df_5m is None or df_1m is None:
        if df_1s is None:
            raise FileNotFoundError(f"{symbol} is missing required 5m/1m bars and no 1s source was found.")
        print(f"[data] rebuilding missing {symbol} bars from local 1s parquet")
        if df_1m is None:
            df_1m = _resample_agg(df_1s, "1min")
        if df_5m is None:
            df_5m = _resample_agg(df_1s, "5min")

    return df_5m, df_1m, df_1s


def _make_leg_config(leg_key: str, base_config: StrategyConfig, profile_key: str) -> StrategyConfig:
    profile = PROFILE_SPECS[profile_key]
    return with_overrides(
        base_config,
        name=f"{leg_key}_{profile_key}",
        notes=f"ALPHA_V1 ORB portfolio cooldown compare {profile_key}.",
        orb_trade_max_per_session=profile["orb_trade_max_per_session_by_leg"][leg_key],
        orb_reentry_policy=profile["orb_reentry_policy_by_leg"][leg_key],
    )


def _run_window(
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame | None,
    df_1s: pd.DataFrame | None,
    configs: list[StrategyConfig],
    maps: dict,
    signal_cache: dict,
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    results = run_sweep(
        df_5m,
        configs,
        n_workers=min(len(configs), 6),
        start_date=start_date,
        end_date=end_date,
        df_1m=df_1m,
        df_1s=df_1s,
        _prebuilt_maps=maps,
        _prebuilt_signal_cache=signal_cache,
    )
    by_name: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        by_name[config.name] = trades
    return by_name


def _trading_dates_from_df(df_5m: pd.DataFrame, start: str, end: str) -> list[str]:
    mask = (df_5m.index >= pd.Timestamp(start)) & (df_5m.index <= pd.Timestamp(end) + pd.Timedelta(days=1))
    return pd.Series(df_5m.index[mask].date).drop_duplicates().astype(str).tolist()


def _daily_r_series(trades: list[TradeResult], trading_dates: list[str]) -> pd.Series:
    daily = defaultdict(float)
    for trade in filled_trades(trades):
        daily[trade.date] += float(trade.r_multiple)
    dt_index = pd.to_datetime(trading_dates)
    return pd.Series([daily.get(date_str, 0.0) for date_str in trading_dates], index=dt_index, dtype=float)


def _portfolio_daily_series(named_streams: dict[str, list[TradeResult]], trading_dates: list[str]) -> tuple[pd.Series, int]:
    leg_series = [_daily_r_series(trades, trading_dates) for trades in named_streams.values()]
    total_series = sum(leg_series, pd.Series(0.0, index=pd.to_datetime(trading_dates)))
    trade_count = sum(len(filled_trades(trades)) for trades in named_streams.values())
    return total_series, trade_count


def _build_cooldown_start_dates(
    dated_daily_r: list[tuple[str, float]],
    trigger_r: float,
    min_gap_days: int,
) -> list[str]:
    if not dated_daily_r:
        return []

    dates = [date_str for date_str, _ in dated_daily_r]
    daily_r = [r for _, r in dated_daily_r]
    starts = [dates[0]]
    last_start_dt = datetime.strptime(dates[0], "%Y-%m-%d")

    cumulative = 0.0
    anchor = 0.0
    for idx, pnl_r in enumerate(daily_r):
        cumulative += pnl_r
        delta = cumulative - anchor
        if abs(delta) < trigger_r:
            continue
        if idx + 1 >= len(dates):
            break

        next_start = dates[idx + 1]
        next_start_dt = datetime.strptime(next_start, "%Y-%m-%d")
        if (next_start_dt - last_start_dt).days < min_gap_days:
            continue

        starts.append(next_start)
        anchor += trigger_r if delta > 0 else -trigger_r
        last_start_dt = next_start_dt

    return starts


def _simulate_accounts_from_start_dates(
    dated_daily_r: list[tuple[str, float]],
    start_dates: list[str],
    payout_r: float,
    breach_r: float,
) -> list[dict[str, Any]]:
    if not dated_daily_r or not start_dates:
        return []

    dates = [date_str for date_str, _ in dated_daily_r]
    daily_r = [r for _, r in dated_daily_r]
    results: list[dict[str, Any]] = []
    for start_str in start_dates:
        first_idx: int | None = None
        for idx, date_str in enumerate(dates):
            if date_str >= start_str:
                first_idx = idx
                break
        if first_idx is None:
            continue

        equity = 0.0
        status = "OPEN"
        stop_idx = first_idx
        for stop_idx in range(first_idx, len(dates)):
            equity += daily_r[stop_idx]
            if equity >= payout_r:
                status = "PAYOUT"
                break
            if equity <= breach_r:
                status = "BREACH"
                break

        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(dates[min(stop_idx, len(dates) - 1)], "%Y-%m-%d")
        results.append(
            {
                "start": start_str,
                "status": status,
                "equity_r": round(equity, 4),
                "cal_days": (end_dt - start_dt).days + 1,
            }
        )
    return results


def _summarize_accounts(results: list[dict[str, Any]]) -> dict[str, Any]:
    payouts = [row for row in results if row["status"] == "PAYOUT"]
    breaches = [row for row in results if row["status"] == "BREACH"]
    opens = [row for row in results if row["status"] == "OPEN"]
    resolved = payouts + breaches
    payout_days = sorted(row["cal_days"] for row in payouts)
    breach_days = sorted(row["cal_days"] for row in breaches)
    return {
        "starts": len(results),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "payout_rate_starts": (len(payouts) / len(results) * 100.0) if results else 0.0,
        "breach_rate_starts": (len(breaches) / len(results) * 100.0) if results else 0.0,
        "resolved_payout_rate": (len(payouts) / len(resolved) * 100.0) if resolved else 0.0,
        "avg_payout_days": (sum(payout_days) / len(payout_days)) if payout_days else None,
        "avg_breach_days": (sum(breach_days) / len(breach_days)) if breach_days else None,
    }


def _start_gap_stats(start_dates: list[str]) -> dict[str, float | None]:
    if len(start_dates) <= 1:
        return {
            "avg_start_gap_days": None,
            "median_start_gap_days": None,
        }

    dt_starts = [datetime.strptime(s, "%Y-%m-%d") for s in start_dates]
    gaps = [(dt_starts[i] - dt_starts[i - 1]).days for i in range(1, len(dt_starts))]
    return {
        "avg_start_gap_days": _round(sum(gaps) / len(gaps), 2) if gaps else None,
        "median_start_gap_days": _round(float(pd.Series(gaps).median()), 2) if gaps else None,
    }


def _write_report(payload: dict[str, Any]) -> None:
    lines = [
        "# ALPHA_V1 ORB Portfolio Cooldown Compare",
        "",
        "- Scope: combined ALPHA_V1 ORB portfolio only (`NQ Asia`, `ES Asia`, `ES NY`).",
        "- Rules compared:",
        "  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.",
        "  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.",
        f"- Trigger model: seed one account on the first trading day of each window, then add a new account when the master daily stream moves another `+/-{R_TRIGGER:g}R` away from the last launch anchor.",
        "- Cooldown model: only one fresh account can be launched per start date, with a minimum cooldown of `1`, `7`, or `14` calendar days between launches.",
        f"- Resolution model: `+{PAYOUT_R:g}R` payout / `{BREACH_R:g}R` breach on the same daily R stream.",
        f"- `2026 YTD` is partial in this repo: `2026-01-01` to `{AVAILABLE_END}`.",
        "",
        "## Portfolio",
        "",
        _markdown_table(
            payload["comparison_rows"],
            [
                "period",
                "rules",
                "cooldown_label",
                "trades",
                "starts",
                "payouts",
                "breaches",
                "open",
                "resolved_payout_rate",
                "avg_start_gap_days",
                "net_r",
                "max_dd_r",
            ],
        ),
        "",
        "## Optimized Minus Current",
        "",
        _markdown_table(
            payload["delta_rows"],
            [
                "period",
                "cooldown_label",
                "trade_delta",
                "start_delta",
                "payout_delta",
                "breach_delta",
                "open_delta",
                "resolved_payout_rate_delta",
                "avg_start_gap_days_delta",
                "net_r_delta",
                "max_dd_r_delta",
            ],
        ),
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    legs = build_alpha_v1_legs()
    symbol_to_leg_keys: dict[str, list[str]] = defaultdict(list)
    for leg_key in ORB_LEG_KEYS:
        symbol_to_leg_keys[legs[leg_key].config.instrument.symbol].append(leg_key)

    window_profile_streams: dict[str, dict[str, dict[str, list[TradeResult]]]] = {
        window["key"]: {profile_key: {} for profile_key in PROFILE_SPECS}
        for window in WINDOWS
    }
    window_symbol_dates: dict[str, dict[str, list[str]]] = {
        window["key"]: {}
        for window in WINDOWS
    }

    for symbol, leg_keys in symbol_to_leg_keys.items():
        base_config = legs[leg_keys[0]].config
        print(f"[data] loading {symbol}")
        df_5m, df_1m, df_1s = _load_market_data(base_config)

        configs: list[StrategyConfig] = []
        config_by_leg_profile: dict[tuple[str, str], StrategyConfig] = {}
        for leg_key in leg_keys:
            base_leg_config = legs[leg_key].config
            for profile_key in PROFILE_SPECS:
                config = _make_leg_config(leg_key, base_leg_config, profile_key)
                configs.append(config)
                config_by_leg_profile[(leg_key, profile_key)] = config

        maps = build_maps(df_5m, df_1m, None, df_1s)
        signal_cache = build_signal_cache(df_5m, configs)
        for window in WINDOWS:
            print(f"[compare] {symbol} {window['label']} ({window['start']} to {window['end']})")
            window_symbol_dates[window["key"]][symbol] = _trading_dates_from_df(
                df_5m,
                window["start"],
                window["end"],
            )
            by_name = _run_window(
                df_5m,
                df_1m,
                df_1s,
                configs,
                maps,
                signal_cache,
                start_date=window["start"],
                end_date=window["end"],
            )
            for leg_key in leg_keys:
                for profile_key in PROFILE_SPECS:
                    config = config_by_leg_profile[(leg_key, profile_key)]
                    window_profile_streams[window["key"]][profile_key][leg_key] = by_name[config.name]

        del maps
        del signal_cache
        del df_5m
        del df_1m
        del df_1s
        gc.collect()

    window_trading_dates: dict[str, list[str]] = {}
    for window in WINDOWS:
        date_set: set[str] = set()
        for symbol_dates in window_symbol_dates[window["key"]].values():
            date_set.update(symbol_dates)
        window_trading_dates[window["key"]] = sorted(date_set)

    comparison_rows: list[dict[str, Any]] = []
    indexed_rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for window in WINDOWS:
        trading_dates = window_trading_dates[window["key"]]
        for profile_key, profile_spec in PROFILE_SPECS.items():
            named_streams = window_profile_streams[window["key"]][profile_key]
            daily_series, trade_count = _portfolio_daily_series(named_streams, trading_dates)
            summary = summarize_daily_returns(daily_series)
            dated_daily_r = [
                (date_str, float(daily_series.loc[pd.Timestamp(date_str)]))
                for date_str in trading_dates
            ]
            for cooldown_days, cooldown_label in COOLDOWNS:
                starts = _build_cooldown_start_dates(dated_daily_r, R_TRIGGER, cooldown_days)
                account_results = _simulate_accounts_from_start_dates(dated_daily_r, starts, PAYOUT_R, BREACH_R)
                acct = _summarize_accounts(account_results)
                gap_stats = _start_gap_stats(starts)

                row = {
                    "period": window["label"],
                    "window": f"{window['start']} to {window['end']}",
                    "rules": profile_spec["label"],
                    "cooldown_days": cooldown_days,
                    "cooldown_label": cooldown_label,
                    "trades": trade_count,
                    "starts": acct["starts"],
                    "payouts": acct["payouts"],
                    "breaches": acct["breaches"],
                    "open": acct["open"],
                    "payout_rate_starts": _round(acct["payout_rate_starts"], 2),
                    "breach_rate_starts": _round(acct["breach_rate_starts"], 2),
                    "resolved_payout_rate": _round(acct["resolved_payout_rate"], 2),
                    "avg_payout_days": _round(acct["avg_payout_days"], 2),
                    "avg_breach_days": _round(acct["avg_breach_days"], 2),
                    **gap_stats,
                    "net_r": _round(summary["total_r"], 2),
                    "max_dd_r": _round(summary["max_drawdown_r"], 2),
                }
                comparison_rows.append(row)
                indexed_rows[(window["key"], profile_key, cooldown_days)] = row

    delta_rows: list[dict[str, Any]] = []
    for window in WINDOWS:
        for cooldown_days, cooldown_label in COOLDOWNS:
            cur = indexed_rows[(window["key"], "current_single_trade", cooldown_days)]
            opt = indexed_rows[(window["key"], "optimized_rules", cooldown_days)]
            delta_rows.append(
                {
                    "period": window["label"],
                    "cooldown_days": cooldown_days,
                    "cooldown_label": cooldown_label,
                    "trade_delta": opt["trades"] - cur["trades"],
                    "start_delta": opt["starts"] - cur["starts"],
                    "payout_delta": opt["payouts"] - cur["payouts"],
                    "breach_delta": opt["breaches"] - cur["breaches"],
                    "open_delta": opt["open"] - cur["open"],
                    "resolved_payout_rate_delta": _round(float(opt["resolved_payout_rate"]) - float(cur["resolved_payout_rate"]), 2),
                    "avg_start_gap_days_delta": _round(float(opt["avg_start_gap_days"]) - float(cur["avg_start_gap_days"]), 2),
                    "net_r_delta": _round(float(opt["net_r"]) - float(cur["net_r"]), 2),
                    "max_dd_r_delta": _round(float(opt["max_dd_r"]) - float(cur["max_dd_r"]), 2),
                }
            )

    payload = {
        "info": {
            "scope": "ALPHA_V1 ORB portfolio only",
            "full_start": FULL_START,
            "available_end": AVAILABLE_END,
            "payout_r": PAYOUT_R,
            "breach_r": BREACH_R,
            "r_trigger": R_TRIGGER,
            "cooldowns_days": [days for days, _ in COOLDOWNS],
            "trigger_semantics": "seed at window start, trigger next-day starts off master daily R stream",
            "cooldown_semantics": "one fresh account max per start date, with minimum calendar-day cooldown between launches",
        },
        "comparison_rows": comparison_rows,
        "delta_rows": delta_rows,
    }
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2))
    _write_report(payload)
    print(f"[saved] {SUMMARY_PATH}")
    print(f"[saved] {REPORT_PATH}")


if __name__ == "__main__":
    main()
