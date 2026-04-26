#!/usr/bin/env python3
"""Explore ES NY sizing in the ALPHA_V1 ORB portfolio.

Questions answered:
- How often does ES NY take a second trade under the optimized rules?
- Is there benefit to risking down the second ES NY trade?
- Is there benefit to risking down ES NY generally?

Portfolio model:
- Combined ORB sleeve only: NQ Asia, ES Asia, ES NY
- Live-weighted dollar sizing baseline: NQ Asia = $250, ES Asia = $250, ES NY = $400
- Fresh-account model: one fresh account max per day, next-day launch trigger from
  the master combined USD daily stream, with a +$1,000 / -$1,000 equivalent anchor step
  (same as 2R when account-R is $500)
- Resolution model: +$2,500 payout / -$2,000 breach
"""

from __future__ import annotations

import gc
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import build_alpha_v1_legs, filled_trades
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import TradeResult, build_maps, build_signal_cache
from orb_backtest.optimize.parallel import run_sweep
ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_esny_risk_explore"
SUMMARY_PATH = RESULT_DIR / "summary.json"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_ESNY_RISK_EXPLORE.md"

FULL_START = "2016-04-17"
AVAILABLE_END = "2026-03-24"

PAYOUT_USD = 2500.0
BREACH_USD = -2000.0
ACCOUNT_R_USD = 500.0
TRIGGER_R = 2.0
TRIGGER_USD = ACCOUNT_R_USD * TRIGGER_R
MIN_GAP_DAYS = 1

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

BASE_RISK_MAP = {
    "nq_asia_orb_long": 250.0,
    "es_asia_orb_long": 250.0,
    "es_ny_orb_long": 400.0,
}


class Variant(NamedTuple):
    key: str
    label: str
    profile_key: str
    esny_trade1_risk: float
    esny_trade2_risk: float


VARIANTS = (
    Variant("current_base", "Current baseline", "current_single_trade", 400.0, 400.0),
    Variant("optimized_base", "Optimized baseline", "optimized_rules", 400.0, 400.0),
    Variant("optimized_esny_t2_0", "Optimized ES_NY trade2 $0", "optimized_rules", 400.0, 0.0),
    Variant("optimized_esny_t2_100", "Optimized ES_NY trade2 $100", "optimized_rules", 400.0, 100.0),
    Variant("optimized_esny_t2_200", "Optimized ES_NY trade2 $200", "optimized_rules", 400.0, 200.0),
    Variant("optimized_esny_t2_250", "Optimized ES_NY trade2 $250", "optimized_rules", 400.0, 250.0),
    Variant("optimized_esny_t2_300", "Optimized ES_NY trade2 $300", "optimized_rules", 400.0, 300.0),
    Variant("optimized_esny_all_300", "Optimized ES_NY all $300", "optimized_rules", 300.0, 300.0),
    Variant("optimized_esny_all_250", "Optimized ES_NY all $250", "optimized_rules", 250.0, 250.0),
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
        notes=f"ALPHA_V1 ORB ES NY risk explore {profile_key}.",
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


def _trade_sort_key(trade: TradeResult) -> tuple[Any, ...]:
    return (
        trade.date,
        trade.session,
        trade.fill_time or "",
        trade.fill_bar,
        trade.signal_bar,
        trade.exit_time or "",
        trade.exit_bar,
    )


def _filled_sorted(trades: list[TradeResult]) -> list[TradeResult]:
    return sorted(filled_trades(trades), key=_trade_sort_key)


def _tag_ordinals(trades: list[TradeResult]) -> list[tuple[TradeResult, int]]:
    tagged: list[tuple[TradeResult, int]] = []
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for trade in _filled_sorted(trades):
        key = (trade.date, trade.session)
        counts[key] += 1
        tagged.append((trade, counts[key]))
    return tagged


def _compute_daily_usd_series(
    named_streams: dict[str, list[TradeResult]],
    trading_dates: list[str],
    variant: Variant,
) -> pd.Series:
    daily = defaultdict(float)
    for leg_key, trades in named_streams.items():
        tagged = _tag_ordinals(trades)
        for trade, ordinal in tagged:
            if leg_key == "es_ny_orb_long":
                risk_usd = variant.esny_trade1_risk if ordinal == 1 else variant.esny_trade2_risk
            else:
                risk_usd = BASE_RISK_MAP[leg_key]
            daily[trade.date] += float(trade.r_multiple) * risk_usd
    index = pd.to_datetime(trading_dates)
    return pd.Series([daily.get(date_str, 0.0) for date_str in trading_dates], index=index, dtype=float)


def _build_cooldown_start_dates_usd(
    dated_daily_usd: list[tuple[str, float]],
    trigger_usd: float,
    min_gap_days: int,
) -> list[str]:
    if not dated_daily_usd:
        return []

    dates = [date_str for date_str, _ in dated_daily_usd]
    daily_usd = [pnl for _, pnl in dated_daily_usd]
    starts = [dates[0]]
    last_start_dt = datetime.strptime(dates[0], "%Y-%m-%d")

    cumulative = 0.0
    anchor = 0.0
    for idx, pnl in enumerate(daily_usd):
        cumulative += pnl
        delta = cumulative - anchor
        if abs(delta) < trigger_usd:
            continue
        if idx + 1 >= len(dates):
            break

        next_start = dates[idx + 1]
        next_start_dt = datetime.strptime(next_start, "%Y-%m-%d")
        if (next_start_dt - last_start_dt).days < min_gap_days:
            continue

        starts.append(next_start)
        anchor += trigger_usd if delta > 0 else -trigger_usd
        last_start_dt = next_start_dt

    return starts


def _simulate_accounts_from_start_dates(
    dated_daily_usd: list[tuple[str, float]],
    start_dates: list[str],
    payout_usd: float,
    breach_usd: float,
) -> list[dict[str, Any]]:
    if not dated_daily_usd or not start_dates:
        return []

    dates = [date_str for date_str, _ in dated_daily_usd]
    daily_usd = [pnl for _, pnl in dated_daily_usd]
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
            equity += daily_usd[stop_idx]
            if equity >= payout_usd:
                status = "PAYOUT"
                break
            if equity <= breach_usd:
                status = "BREACH"
                break

        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        end_dt = datetime.strptime(dates[min(stop_idx, len(dates) - 1)], "%Y-%m-%d")
        results.append(
            {
                "start": start_str,
                "status": status,
                "equity_usd": round(equity, 2),
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


def _portfolio_usd_metrics(daily_usd_series: pd.Series) -> dict[str, Any]:
    if daily_usd_series.empty:
        return {"net_usd": 0.0, "max_dd_usd": 0.0, "sharpe_ratio": 0.0}
    equity = daily_usd_series.cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    std = float(daily_usd_series.std(ddof=1)) if len(daily_usd_series) > 1 else 0.0
    avg = float(daily_usd_series.mean())
    sharpe = (avg / std * math.sqrt(252.0)) if std > 0 else 0.0
    return {
        "net_usd": _round(float(daily_usd_series.sum()), 2),
        "max_dd_usd": _round(float(drawdown.min()), 2),
        "sharpe_ratio": _round(sharpe, 2),
    }


def _esny_trade_stats(trades: list[TradeResult]) -> dict[str, Any]:
    tagged = _tag_ordinals(trades)
    first_trades = [trade for trade, ordinal in tagged if ordinal == 1]
    second_trades = [trade for trade, ordinal in tagged if ordinal == 2]
    trade_days = len({trade.date for trade in first_trades})

    def summarize(group: list[TradeResult]) -> dict[str, Any]:
        if not group:
            return {"count": 0, "win_rate_pct": 0.0, "avg_r": 0.0, "total_r": 0.0}
        wins = sum(1 for trade in group if trade.r_multiple > 0)
        total_r = sum(float(trade.r_multiple) for trade in group)
        return {
            "count": len(group),
            "win_rate_pct": _round(wins / len(group) * 100.0, 2),
            "avg_r": _round(total_r / len(group), 3),
            "total_r": _round(total_r, 2),
        }

    first_summary = summarize(first_trades)
    second_summary = summarize(second_trades)
    return {
        "trade_days": trade_days,
        "days_with_2_trades": len(second_trades),
        "days_with_2_trades_pct": _round(len(second_trades) / trade_days * 100.0, 2) if trade_days else 0.0,
        "first_trade_count": first_summary["count"],
        "first_trade_win_rate_pct": first_summary["win_rate_pct"],
        "first_trade_avg_r": first_summary["avg_r"],
        "first_trade_total_r": first_summary["total_r"],
        "second_trade_count": second_summary["count"],
        "second_trade_win_rate_pct": second_summary["win_rate_pct"],
        "second_trade_avg_r": second_summary["avg_r"],
        "second_trade_total_r": second_summary["total_r"],
    }


def _write_report(payload: dict[str, Any]) -> None:
    lines = [
        "# ALPHA_V1 ORB ES NY Risk Explore",
        "",
        "- Scope: combined ORB sleeve only (`NQ Asia`, `ES Asia`, `ES NY`).",
        "- Profile basis:",
        "  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.",
        "  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.",
        "- Dollar sizing basis: `NQ Asia=$250`, `ES Asia=$250`, `ES NY=$400` from `execution/config/exec_configs.json`.",
        f"- Fresh-account model: one fresh account max per day, next-day trigger every `${TRIGGER_USD:,.0f}` move in the combined master daily USD stream.",
        f"- Resolution model: `+${PAYOUT_USD:,.0f}` payout / `${BREACH_USD:,.0f}` breach.",
        "",
        "## ES NY Trade-2 Frequency",
        "",
        _markdown_table(
            payload["esny_trade_rows"],
            [
                "period",
                "trade_days",
                "days_with_2_trades",
                "days_with_2_trades_pct",
                "first_trade_avg_r",
                "first_trade_total_r",
                "second_trade_avg_r",
                "second_trade_total_r",
            ],
        ),
        "",
        "## Portfolio Variants",
        "",
        _markdown_table(
            payload["portfolio_rows"],
            [
                "period",
                "variant",
                "starts",
                "payouts",
                "breaches",
                "open",
                "resolved_payout_rate",
                "avg_start_gap_days",
                "net_usd",
                "max_dd_usd",
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

    esny_trade_rows: list[dict[str, Any]] = []
    portfolio_rows: list[dict[str, Any]] = []
    for window in WINDOWS:
        optimized_esny_stream = window_profile_streams[window["key"]]["optimized_rules"]["es_ny_orb_long"]
        esny_trade_rows.append(
            {
                "period": window["label"],
                **_esny_trade_stats(optimized_esny_stream),
            }
        )

        trading_dates = window_trading_dates[window["key"]]
        for variant in VARIANTS:
            named_streams = window_profile_streams[window["key"]][variant.profile_key]
            daily_usd_series = _compute_daily_usd_series(named_streams, trading_dates, variant)
            dated_daily_usd = [
                (date_str, float(daily_usd_series.loc[pd.Timestamp(date_str)]))
                for date_str in trading_dates
            ]
            starts = _build_cooldown_start_dates_usd(dated_daily_usd, TRIGGER_USD, MIN_GAP_DAYS)
            account_results = _simulate_accounts_from_start_dates(
                dated_daily_usd,
                starts,
                PAYOUT_USD,
                BREACH_USD,
            )
            acct = _summarize_accounts(account_results)
            gap_stats = _start_gap_stats(starts)
            metrics = _portfolio_usd_metrics(daily_usd_series)
            portfolio_rows.append(
                {
                    "period": window["label"],
                    "window": f"{window['start']} to {window['end']}",
                    "variant": variant.label,
                    "profile_key": variant.profile_key,
                    "esny_trade1_risk": variant.esny_trade1_risk,
                    "esny_trade2_risk": variant.esny_trade2_risk,
                    "starts": acct["starts"],
                    "payouts": acct["payouts"],
                    "breaches": acct["breaches"],
                    "open": acct["open"],
                    "resolved_payout_rate": _round(acct["resolved_payout_rate"], 2),
                    "avg_payout_days": _round(acct["avg_payout_days"], 2),
                    "avg_breach_days": _round(acct["avg_breach_days"], 2),
                    **gap_stats,
                    **metrics,
                }
            )

    payload = {
        "info": {
            "scope": "ALPHA_V1 ORB sleeve only",
            "full_start": FULL_START,
            "available_end": AVAILABLE_END,
            "payout_usd": PAYOUT_USD,
            "breach_usd": BREACH_USD,
            "trigger_usd": TRIGGER_USD,
            "account_r_usd": ACCOUNT_R_USD,
            "min_gap_days": MIN_GAP_DAYS,
            "base_risk_map": BASE_RISK_MAP,
        },
        "esny_trade_rows": esny_trade_rows,
        "portfolio_rows": portfolio_rows,
    }
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2))
    _write_report(payload)
    print(f"[saved] {SUMMARY_PATH}")
    print(f"[saved] {REPORT_PATH}")


if __name__ == "__main__":
    main()
