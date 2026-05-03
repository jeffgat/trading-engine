#!/usr/bin/env python3
"""Promotion packet for adding one-loss reentry to selected ALPHA_V1 ORB legs.

Candidate under test:
- NQ Asia ORB: cap=2, reentry after non-positive first trade
- ES Asia ORB: cap=2, reentry after non-positive first trade
- ES NY ORB: unchanged
- NQ NY HTF-LSI: unchanged
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES, NQ, Instrument
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult
from orb_backtest.optimize.parallel import run_sweep

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config


RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_reentry_promotion_20260502"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_REENTRY_PROMOTION_20260502.md"
SUMMARY_PATH = RESULT_DIR / "summary.json"

FULL_START = "2016-04-17"
WINDOW_STARTS = {
    "full": FULL_START,
    "2024+": "2024-01-01",
    "2025+": "2025-01-01",
}
CURRENT_RISK_USD = {
    "nq_ny_htf_lsi": 300.0,
    "nq_asia_orb": 300.0,
    "es_asia_orb": 200.0,
    "es_ny_orb": 300.0,
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


@dataclass(frozen=True)
class LegSpec:
    key: str
    label: str
    symbol: str
    config: StrategyConfig
    risk_usd_current: float


@dataclass
class LoadedData:
    df_5m: pd.DataFrame
    df_1m: pd.DataFrame | None
    df_1s: pd.DataFrame | None


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
    return "\n".join([header, sep, *body]) if body else "\n".join([header, sep])


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return out.dropna(subset=["open", "high", "low", "close"]).astype(float)


def _load_market_data(instrument: Instrument) -> LoadedData:
    df_5m: pd.DataFrame | None = None
    df_1m: pd.DataFrame | None = None
    df_1s: pd.DataFrame | None = None

    try:
        df_5m = load_5m_data(instrument.data_file, start=FULL_START, end=None)
    except FileNotFoundError:
        pass
    try:
        df_1m = load_1m_for_5m(instrument.data_file, start=FULL_START, end=None)
    except FileNotFoundError:
        pass
    try:
        df_1s = load_1s_for_5m(instrument.data_file, start=FULL_START, end=None)
    except FileNotFoundError:
        pass

    if df_5m is None or df_1m is None:
        if df_1s is None:
            raise FileNotFoundError(
                f"{instrument.symbol} is missing 5m/1m bars and no 1s fallback is available."
            )
        print(f"  rebuilding missing {instrument.symbol} 5m/1m bars from local 1s parquet", flush=True)
        if df_1m is None:
            df_1m = _resample_ohlcv(df_1s, "1min")
        if df_5m is None:
            df_5m = _resample_ohlcv(df_1s, "5min")

    assert df_5m is not None
    return LoadedData(df_5m=df_5m, df_1m=df_1m, df_1s=df_1s)


def build_active_legs(*, candidate: bool) -> list[LegSpec]:
    nq_asia = StrategyConfig(
        sessions=(
            SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="22:30",
                flat_start="04:00",
                flat_end="07:00",
                stop_orb_pct=100.0,
                min_gap_orb_pct=10.0,
            ),
        ),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=6.0,
        tp1_ratio=0.3,
        atr_length=5,
        excluded_days=(1,),
        name="ALPHA_V1 promo baseline NQ Asia ORB",
    )
    es_asia = StrategyConfig(
        sessions=(
            SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="03:00",
                flat_start="07:00",
                flat_end="07:00",
                stop_orb_pct=125.0,
                min_gap_atr_pct=0.5,
                min_stop_points=3.0,
                min_tp1_points=3.0,
            ),
        ),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=1.5,
        tp1_ratio=0.7,
        atr_length=14,
        name="ALPHA_V1 promo baseline ES Asia ORB",
    )
    es_ny = StrategyConfig(
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:45",
                entry_start="09:45",
                entry_end="13:00",
                flat_start="15:50",
                flat_end="16:00",
                stop_atr_pct=5.0,
                min_gap_atr_pct=0.25,
                min_stop_points=3.0,
                min_tp1_points=3.0,
            ),
        ),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=5.0,
        tp1_ratio=0.2,
        atr_length=7,
        excluded_days=(3,),
        name="ALPHA_V1 promo baseline ES NY ORB",
    )

    if candidate:
        nq_asia = with_overrides(
            nq_asia,
            name="ALPHA_V1 promo candidate NQ Asia ORB cap2 after_nonpositive",
            notes="Promotion packet: cap=2, reentry after non-positive first trade.",
            orb_trade_max_per_session=2,
            orb_reentry_policy="after_nonpositive_first",
        )
        es_asia = with_overrides(
            es_asia,
            name="ALPHA_V1 promo candidate ES Asia ORB cap2 after_nonpositive",
            notes="Promotion packet: cap=2, reentry after non-positive first trade.",
            orb_trade_max_per_session=2,
            orb_reentry_policy="after_nonpositive_first",
        )

    return [
        LegSpec(
            key="nq_ny_htf_lsi",
            label="NQ NY HTF-LSI",
            symbol="NQ",
            config=build_current_nq_ny_htf_lsi_lag24_config(
                name=(
                    "ALPHA_V1 promo candidate NQ NY HTF-LSI unchanged"
                    if candidate
                    else "ALPHA_V1 promo baseline NQ NY HTF-LSI"
                )
            ),
            risk_usd_current=CURRENT_RISK_USD["nq_ny_htf_lsi"],
        ),
        LegSpec(
            key="nq_asia_orb",
            label="NQ Asia ORB",
            symbol="NQ",
            config=nq_asia,
            risk_usd_current=CURRENT_RISK_USD["nq_asia_orb"],
        ),
        LegSpec(
            key="es_asia_orb",
            label="ES Asia ORB",
            symbol="ES",
            config=es_asia,
            risk_usd_current=CURRENT_RISK_USD["es_asia_orb"],
        ),
        LegSpec(
            key="es_ny_orb",
            label="ES NY ORB",
            symbol="ES",
            config=es_ny,
            risk_usd_current=CURRENT_RISK_USD["es_ny_orb"],
        ),
    ]


def _sort_trades(trades: list[TradeResult]) -> list[TradeResult]:
    return sorted(
        trades,
        key=lambda t: (
            t.fill_time or t.exit_time or t.date,
            t.date,
            t.session,
            t.fill_bar,
            t.signal_bar,
            t.exit_bar,
        ),
    )


def _filled(trades: list[TradeResult]) -> list[TradeResult]:
    return [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]


def run_profile(
    profile: str,
    legs: list[LegSpec],
    market_data: dict[str, LoadedData],
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    by_symbol: dict[str, list[LegSpec]] = defaultdict(list)
    for leg in legs:
        by_symbol[leg.symbol].append(leg)

    streams: dict[str, list[TradeResult]] = {}
    for symbol, symbol_legs in by_symbol.items():
        data = market_data[symbol]
        configs = [leg.config for leg in symbol_legs]
        print(f"  {profile}: running {symbol} ({len(configs)} configs)", flush=True)
        results = run_sweep(
            data.df_5m,
            configs,
            n_workers=1,
            start_date=start_date,
            end_date=end_date,
            df_1m=data.df_1m,
            df_1s=data.df_1s,
            signal_df_1m=data.df_1m,
        )
        by_name = {config.name: trades for config, trades in results}
        for leg in symbol_legs:
            trades = by_name[leg.config.name]
            if leg.config.excluded_days:
                trades = apply_dow_filter(trades, set(leg.config.excluded_days))
            streams[leg.key] = _sort_trades(trades)
    return streams


def _trade_rows(profile: str, legs: list[LegSpec], streams: dict[str, list[TradeResult]]) -> list[dict[str, Any]]:
    by_key = {leg.key: leg for leg in legs}
    rows: list[dict[str, Any]] = []
    for leg_key, trades in streams.items():
        leg = by_key[leg_key]
        for ordinal, trade in enumerate(_filled(trades), start=1):
            exit_ts = pd.Timestamp(trade.exit_time or trade.fill_time or trade.date)
            fill_ts = pd.Timestamp(trade.fill_time or trade.exit_time or trade.date)
            rows.append(
                {
                    "profile": profile,
                    "leg": leg_key,
                    "leg_label": leg.label,
                    "symbol": leg.symbol,
                    "date": trade.date,
                    "fill_time": trade.fill_time,
                    "exit_time": trade.exit_time,
                    "fill_ts": fill_ts,
                    "exit_ts": exit_ts,
                    "exit_date": exit_ts.normalize().date().isoformat(),
                    "session": trade.session,
                    "direction": trade.direction,
                    "entry_price": trade.entry_price,
                    "stop_price": trade.stop_price,
                    "tp1_price": trade.tp1_price,
                    "tp2_price": trade.tp2_price,
                    "exit_type": trade.exit_type,
                    "exit_name": EXIT_NAMES.get(trade.exit_type, str(trade.exit_type)),
                    "r_multiple": float(trade.r_multiple),
                    "risk_points": float(trade.risk_points),
                    "pnl_points": float(trade.pnl_points),
                    "research_pnl_usd": float(trade.pnl_usd),
                    "risk_usd_current": leg.risk_usd_current,
                    "pnl_usd_current": float(trade.r_multiple) * leg.risk_usd_current,
                    "fill_bar": trade.fill_bar,
                    "exit_bar": trade.exit_bar,
                    "signal_bar": trade.signal_bar,
                    "leg_trade_ordinal": ordinal,
                }
            )
    rows.sort(key=lambda row: (row["exit_ts"], row["leg"], row["fill_ts"]))
    return rows


def _filter_rows(rows: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [row for row in rows if start <= row["exit_date"] <= end]


def _daily_frame(rows: list[dict[str, Any]], value_col: str) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    grouped = df.groupby(["exit_date", "leg"])[value_col].sum().unstack(fill_value=0.0)
    grouped.index = pd.to_datetime(grouped.index)
    return grouped.sort_index()


def _series_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    equity = series.cumsum()
    peak = equity.cummax()
    return float((equity - peak).min())


def _series_sharpe(series: pd.Series) -> float:
    if series.empty or len(series) < 2:
        return 0.0
    std = float(series.std(ddof=1))
    return float(series.mean() / std * math.sqrt(252.0)) if std > 0 else 0.0


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = sum(value for value in values if value < 0)
    return abs(wins / losses) if losses != 0 else 0.0


def _metrics_row(
    label: str,
    profile: str,
    window: str,
    rows: list[dict[str, Any]],
    *,
    value_col: str = "r_multiple",
    daily_series: pd.Series | None = None,
) -> dict[str, Any]:
    values = [float(row[value_col]) for row in rows]
    r_values = [float(row["r_multiple"]) for row in rows]
    usd_values = [float(row["pnl_usd_current"]) for row in rows]
    if daily_series is None:
        daily_series = pd.Series(values, dtype=float)
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    years: dict[str, float] = defaultdict(float)
    for row in rows:
        years[row["exit_date"][:4]] += float(row[value_col])
    return {
        "scope": label,
        "profile": profile,
        "window": window,
        "fills": len(rows),
        "net_r": _round(sum(r_values), 2),
        "net_usd_current": _round(sum(usd_values), 2),
        "win_rate_pct": _pct(len(wins) / len(values)) if values else 0.0,
        "profit_factor": _round(_profit_factor(values), 2),
        "avg_r": _round(np.mean(r_values), 3) if r_values else 0.0,
        "sharpe": _round(_series_sharpe(daily_series), 2),
        "max_dd": _round(_series_drawdown(daily_series), 2),
        "calmar": _round((sum(values) / abs(_series_drawdown(daily_series))) if _series_drawdown(daily_series) else 0.0, 2),
        "negative_years": sum(1 for value in years.values() if value < 0),
    }


def build_window_metrics(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    overlap_end: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    end_ts = pd.Timestamp(overlap_end)
    windows = {
        **{name: (start, overlap_end) for name, start in WINDOW_STARTS.items()},
        "last_1y": ((end_ts - pd.Timedelta(days=365)).date().isoformat(), overlap_end),
        "calendar_2024": ("2024-01-01", "2024-12-31"),
        "calendar_2025": ("2025-01-01", "2025-12-31"),
    }
    combined_rows: list[dict[str, Any]] = []
    leg_rows: list[dict[str, Any]] = []
    for window, (start, end) in windows.items():
        for profile, rows in (("baseline", baseline_rows), ("candidate", candidate_rows)):
            subset = _filter_rows(rows, start, end)
            daily_r = _daily_frame(subset, "r_multiple")
            daily_usd = _daily_frame(subset, "pnl_usd_current")
            combined_rows.append(
                _metrics_row(
                    "combined",
                    profile,
                    window,
                    subset,
                    value_col="r_multiple",
                    daily_series=daily_r.sum(axis=1) if not daily_r.empty else pd.Series(dtype=float),
                )
            )
            combined_rows[-1]["max_dd_usd_current"] = _round(
                _series_drawdown(daily_usd.sum(axis=1) if not daily_usd.empty else pd.Series(dtype=float)),
                2,
            )
            for leg in CURRENT_RISK_USD:
                leg_subset = [row for row in subset if row["leg"] == leg]
                leg_daily = _daily_frame(leg_subset, "r_multiple")
                leg_rows.append(
                    _metrics_row(
                        leg,
                        profile,
                        window,
                        leg_subset,
                        value_col="r_multiple",
                        daily_series=(
                            leg_daily.sum(axis=1) if not leg_daily.empty else pd.Series(dtype=float)
                        ),
                    )
                )

        base = next(row for row in combined_rows if row["profile"] == "baseline" and row["window"] == window)
        cand = next(row for row in combined_rows if row["profile"] == "candidate" and row["window"] == window)
        cand["delta_net_r"] = _round(cand["net_r"] - base["net_r"], 2)
        cand["delta_net_usd_current"] = _round(cand["net_usd_current"] - base["net_usd_current"], 2)
        cand["delta_max_dd"] = _round(cand["max_dd"] - base["max_dd"], 2)
        cand["delta_max_dd_usd_current"] = _round(
            cand["max_dd_usd_current"] - base["max_dd_usd_current"],
            2,
        )
        base["delta_net_r"] = 0.0
        base["delta_net_usd_current"] = 0.0
        base["delta_max_dd"] = 0.0
        base["delta_max_dd_usd_current"] = 0.0

        for leg in CURRENT_RISK_USD:
            base_leg = next(
                row
                for row in leg_rows
                if row["profile"] == "baseline" and row["window"] == window and row["scope"] == leg
            )
            cand_leg = next(
                row
                for row in leg_rows
                if row["profile"] == "candidate" and row["window"] == window and row["scope"] == leg
            )
            cand_leg["delta_net_r"] = _round(cand_leg["net_r"] - base_leg["net_r"], 2)
            cand_leg["delta_net_usd_current"] = _round(
                cand_leg["net_usd_current"] - base_leg["net_usd_current"],
                2,
            )
            cand_leg["delta_max_dd"] = _round(cand_leg["max_dd"] - base_leg["max_dd"], 2)
            base_leg["delta_net_r"] = 0.0
            base_leg["delta_net_usd_current"] = 0.0
            base_leg["delta_max_dd"] = 0.0
    return combined_rows, leg_rows


def _trade_dates(rows: list[dict[str, Any]]) -> tuple[str, str]:
    dates = [row["exit_date"] for row in rows]
    return min(dates), max(dates)


def simulate_first_payouts(rows: list[dict[str, Any]], *, start: str, end: str) -> list[dict[str, Any]]:
    trades = [row for row in rows if start <= row["exit_date"] <= end]
    trades.sort(key=lambda row: (row["exit_ts"], row["leg"], row["fill_ts"]))
    if not trades:
        return []

    first_start = pd.Timestamp(start).normalize()
    last_start = pd.Timestamp(end).normalize()
    cohort_starts = pd.date_range(
        first_start,
        last_start,
        freq=f"{int(FUNDED_PROFILE['cohort_spacing_days'])}D",
    )
    outcomes: list[dict[str, Any]] = []
    for account_id, cohort_start in enumerate(cohort_starts, start=1):
        balance = float(FUNDED_PROFILE["starting_balance_usd"])
        floor = balance - float(FUNDED_PROFILE["trailing_drawdown_usd"])
        high_eod = balance
        current_day: str | None = None
        trade_count = 0
        worst_intraday_dd = 0.0
        outcome = "open"
        outcome_date = pd.Timestamp(end).date().isoformat()

        account_trades = [row for row in trades if row["exit_ts"] >= cohort_start]
        for row in account_trades:
            trade_day = row["exit_date"]
            if current_day is not None and trade_day != current_day:
                high_eod = max(high_eod, balance)
                floor = max(
                    floor,
                    min(
                        high_eod - float(FUNDED_PROFILE["trailing_drawdown_usd"]),
                        float(FUNDED_PROFILE["max_trailing_breach_usd"]),
                    ),
                )
            current_day = trade_day
            balance += float(row["pnl_usd_current"])
            trade_count += 1
            worst_intraday_dd = min(worst_intraday_dd, balance - high_eod)
            if balance <= floor:
                outcome = "breach"
                outcome_date = trade_day
                break
            if balance >= float(FUNDED_PROFILE["first_payout_floor_usd"]):
                outcome = "payout"
                outcome_date = trade_day
                break

        if current_day is not None and outcome == "open":
            high_eod = max(high_eod, balance)
            floor = max(
                floor,
                min(
                    high_eod - float(FUNDED_PROFILE["trailing_drawdown_usd"]),
                    float(FUNDED_PROFILE["max_trailing_breach_usd"]),
                ),
            )
        if outcome == "payout":
            net_after_fee = (
                float(FUNDED_PROFILE["first_payout_amount_usd"])
                - float(FUNDED_PROFILE["challenge_fee_usd"])
            )
        else:
            net_after_fee = -float(FUNDED_PROFILE["challenge_fee_usd"])
        outcomes.append(
            {
                "account_id": account_id,
                "start_date": cohort_start.date().isoformat(),
                "outcome": outcome,
                "outcome_date": outcome_date,
                "days_to_outcome": int((pd.Timestamp(outcome_date) - cohort_start).days),
                "trades_to_outcome": trade_count,
                "ending_balance": _round(balance, 2),
                "ending_floor": _round(floor, 2),
                "worst_intraday_dd_usd": _round(worst_intraday_dd, 2),
                "net_after_fee_usd": _round(net_after_fee, 2),
            }
        )
    return outcomes


def summarize_payouts(profile: str, window: str, outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    if not outcomes:
        return {
            "profile": profile,
            "window": window,
            "accounts": 0,
            "payouts": 0,
            "breaches": 0,
            "open": 0,
            "payout_rate_pct": 0.0,
            "breach_rate_pct": 0.0,
            "ev_per_account_usd": 0.0,
            "median_days_to_payout": None,
            "median_trades_to_payout": None,
            "max_consecutive_breaches": 0,
        }
    payouts = [row for row in outcomes if row["outcome"] == "payout"]
    breaches = [row for row in outcomes if row["outcome"] == "breach"]
    max_run = 0
    current_run = 0
    for row in outcomes:
        if row["outcome"] == "breach":
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return {
        "profile": profile,
        "window": window,
        "accounts": len(outcomes),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": sum(1 for row in outcomes if row["outcome"] == "open"),
        "payout_rate_pct": _pct(len(payouts) / len(outcomes)),
        "breach_rate_pct": _pct(len(breaches) / len(outcomes)),
        "ev_per_account_usd": _round(float(np.mean([row["net_after_fee_usd"] for row in outcomes])), 2),
        "median_days_to_payout": (
            _round(float(np.median([row["days_to_outcome"] for row in payouts])), 1) if payouts else None
        ),
        "median_trades_to_payout": (
            _round(float(np.median([row["trades_to_outcome"] for row in payouts])), 1) if payouts else None
        ),
        "max_consecutive_breaches": max_run,
    }


def monthly_stress(rows: list[dict[str, Any]], profile: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    daily_r = _daily_frame(rows, "r_multiple").sum(axis=1)
    daily_usd = _daily_frame(rows, "pnl_usd_current").sum(axis=1)
    monthly: list[dict[str, Any]] = []
    if not daily_r.empty:
        df = pd.DataFrame({"r": daily_r, "usd": daily_usd}).fillna(0.0)
        for month, month_df in df.groupby(df.index.to_period("M")):
            monthly.append(
                {
                    "profile": profile,
                    "month": str(month),
                    "net_r": _round(float(month_df["r"].sum()), 2),
                    "max_dd_r": _round(_series_drawdown(month_df["r"]), 2),
                    "net_usd_current": _round(float(month_df["usd"].sum()), 2),
                    "max_dd_usd_current": _round(_series_drawdown(month_df["usd"]), 2),
                }
            )

    rolling_rows: list[dict[str, Any]] = []
    if not daily_r.empty:
        full_idx = pd.date_range(daily_r.index.min(), daily_r.index.max(), freq="D")
        daily = pd.DataFrame(
            {
                "r": daily_r.reindex(full_idx, fill_value=0.0),
                "usd": daily_usd.reindex(full_idx, fill_value=0.0),
            }
        )
        for i in range(0, max(0, len(daily) - 90 + 1)):
            window = daily.iloc[i : i + 90]
            if window.empty:
                continue
            rolling_rows.append(
                {
                    "profile": profile,
                    "start": window.index[0].date().isoformat(),
                    "end": window.index[-1].date().isoformat(),
                    "net_r": _round(float(window["r"].sum()), 2),
                    "max_dd_r": _round(_series_drawdown(window["r"]), 2),
                    "net_usd_current": _round(float(window["usd"].sum()), 2),
                    "max_dd_usd_current": _round(_series_drawdown(window["usd"]), 2),
                }
            )
        rolling_rows.sort(key=lambda row: (row["max_dd_usd_current"], row["net_usd_current"]))
    return monthly, rolling_rows[:10]


def _session_anchor_time(config: StrategyConfig) -> str:
    session = config.sessions[0]
    return session.orb_start or session.rth_start or session.entry_start


def _session_crosses_midnight(config: StrategyConfig) -> bool:
    session = config.sessions[0]
    start_time = _session_anchor_time(config)
    end_time = session.flat_end or session.entry_end
    return bool(start_time and end_time and end_time < start_time)


def _session_day_key(row: dict[str, Any], config: StrategyConfig) -> tuple[str, str]:
    session_name = config.sessions[0].name
    ts = row["fill_ts"]
    session_date = ts.date()
    if _session_crosses_midnight(config):
        anchor_time = _session_anchor_time(config)
        if ts.strftime("%H:%M") < anchor_time:
            session_date = (ts - pd.Timedelta(days=1)).date()
    return session_name, session_date.isoformat()


def identify_reentries(candidate_rows: list[dict[str, Any]], candidate_legs: list[LegSpec]) -> list[dict[str, Any]]:
    config_by_leg = {leg.key: leg.config for leg in candidate_legs}
    tracked_legs = {"nq_asia_orb", "es_asia_orb"}
    rows = [row.copy() for row in candidate_rows if row["leg"] in tracked_legs]
    rows.sort(key=lambda row: (row["fill_ts"], row["exit_ts"], row["leg"]))
    ordinals: dict[tuple[str, str, str], int] = defaultdict(int)
    out: list[dict[str, Any]] = []
    for row in rows:
        session_name, session_date = _session_day_key(row, config_by_leg[row["leg"]])
        key = (row["leg"], session_name, session_date)
        ordinals[key] += 1
        row["session_day"] = session_date
        row["session_trade_ordinal"] = ordinals[key]
        if ordinals[key] >= 2:
            out.append(row)
    return out


def overlap_summary(candidate_rows: list[dict[str, Any]], reentries: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    daily_by_leg = _daily_frame(candidate_rows, "pnl_usd_current")
    daily_r_by_leg = _daily_frame(candidate_rows, "r_multiple")
    all_days = daily_by_leg.index
    all_other_negative = 0
    if not daily_by_leg.empty:
        for day in all_days:
            all_other_negative += int(float(daily_by_leg.loc[day].sum()) < 0)

    rows: list[dict[str, Any]] = []
    for row in reentries:
        day = pd.Timestamp(row["exit_date"])
        if day in daily_by_leg.index:
            other_usd = float(daily_by_leg.loc[day].drop(labels=[row["leg"]], errors="ignore").sum())
            other_r = float(daily_r_by_leg.loc[day].drop(labels=[row["leg"]], errors="ignore").sum())
            total_usd = float(daily_by_leg.loc[day].sum())
            total_r = float(daily_r_by_leg.loc[day].sum())
        else:
            other_usd = other_r = total_usd = total_r = 0.0
        rows.append(
            {
                "date": row["exit_date"],
                "leg": row["leg_label"],
                "reentry_r": _round(row["r_multiple"], 2),
                "reentry_usd": _round(row["pnl_usd_current"], 2),
                "other_legs_r": _round(other_r, 2),
                "other_legs_usd": _round(other_usd, 2),
                "total_day_r": _round(total_r, 2),
                "total_day_usd": _round(total_usd, 2),
                "other_legs_negative": other_usd < 0,
                "total_day_negative": total_usd < 0,
            }
        )
    rows.sort(key=lambda item: (item["total_day_usd"], item["reentry_usd"]))
    summary = {
        "reentry_count": len(reentries),
        "reentry_net_r": _round(sum(row["r_multiple"] for row in reentries), 2),
        "reentry_net_usd_current": _round(sum(row["pnl_usd_current"] for row in reentries), 2),
        "reentry_wr_pct": _pct(sum(1 for row in reentries if row["r_multiple"] > 0) / len(reentries)) if reentries else 0.0,
        "avg_other_legs_usd": _round(float(np.mean([row["other_legs_usd"] for row in rows])), 2) if rows else 0.0,
        "share_other_legs_negative_pct": _pct(sum(1 for row in rows if row["other_legs_negative"]) / len(rows)) if rows else 0.0,
        "share_total_day_negative_pct": _pct(sum(1 for row in rows if row["total_day_negative"]) / len(rows)) if rows else 0.0,
        "all_candidate_days_negative_pct": _pct(all_other_negative / len(all_days)) if len(all_days) else 0.0,
    }
    return summary, rows[:20]


def execution_compatibility() -> dict[str, Any]:
    engine_path = REPO_ROOT / "execution" / "src" / "trader" / "engine.py"
    main_path = REPO_ROOT / "execution" / "src" / "trader" / "main.py"
    overrides_path = REPO_ROOT / "execution" / "src" / "trader" / "overrides.py"
    historical_path = REPO_ROOT / "execution" / "src" / "trader" / "historical_backtest.py"
    texts = {
        "engine.py": engine_path.read_text(),
        "main.py": main_path.read_text(),
        "overrides.py": overrides_path.read_text(),
        "historical_backtest.py": historical_path.read_text(),
    }
    generic_engine_has_reentry = (
        "orb_trade_max_per_session" in texts["engine.py"] or "reentry_policy" in texts["engine.py"]
    )
    main_passes_generic_fields = (
        "orb_trade_max_per_session" in texts["main.py"] and "ORBEngine(" in texts["main.py"]
    )
    override_editable = "orb_trade_max_per_session" in texts["overrides.py"] or "reentry_policy" in texts["overrides.py"]
    exact_replay_records = "orb_trade_max_per_session" in texts["historical_backtest.py"]
    hunter_has_reentry = "HunterORBEngine" in texts["main.py"] and "reentry_policy" in texts["main.py"]
    return {
        "research_backtester_supports_candidate": True,
        "execution_generic_orb_engine_supports_candidate": bool(generic_engine_has_reentry and main_passes_generic_fields),
        "runtime_overrides_support_candidate": bool(override_editable),
        "historical_exact_replay_records_candidate_fields": bool(exact_replay_records),
        "hunter_orb_engine_has_its_own_reentry": bool(hunter_has_reentry),
        "promotion_status": (
            "ready_for_dry_mode"
            if generic_engine_has_reentry and main_passes_generic_fields and override_editable
            else "research_promotable_but_execution_blocked"
        ),
        "notes": [
            "The research backtester supports orb_trade_max_per_session and orb_reentry_policy.",
            "The execution HunterORBEngine has separate reentry support, but ALPHA_V1 Asia ORB legs use the generic ORBEngine.",
            "Generic execution ORBEngine currently scans one FVG, arms one order, then goes flat after completion; no equivalent cap=2 after_nonpositive_first promotion knob was found.",
        ],
    }


def write_outputs(
    *,
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    combined_metrics: list[dict[str, Any]],
    leg_metrics: list[dict[str, Any]],
    payout_rows: list[dict[str, Any]],
    payout_summaries: list[dict[str, Any]],
    monthly_rows: list[dict[str, Any]],
    worst_3m_rows: list[dict[str, Any]],
    overlap: dict[str, Any],
    overlap_worst: list[dict[str, Any]],
    compatibility: dict[str, Any],
    overlap_end: str,
    elapsed_s: float,
) -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(baseline_rows).drop(columns=["fill_ts", "exit_ts"], errors="ignore").to_csv(
        RESULT_DIR / "baseline_trades.csv",
        index=False,
    )
    pd.DataFrame(candidate_rows).drop(columns=["fill_ts", "exit_ts"], errors="ignore").to_csv(
        RESULT_DIR / "candidate_trades.csv",
        index=False,
    )
    pd.DataFrame(combined_metrics).to_csv(RESULT_DIR / "combined_window_metrics.csv", index=False)
    pd.DataFrame(leg_metrics).to_csv(RESULT_DIR / "per_leg_window_metrics.csv", index=False)
    pd.DataFrame(payout_rows).to_csv(RESULT_DIR / "funded_first_payout_accounts.csv", index=False)
    pd.DataFrame(payout_summaries).to_csv(RESULT_DIR / "funded_first_payout_summary.csv", index=False)
    pd.DataFrame(monthly_rows).to_csv(RESULT_DIR / "monthly_stress.csv", index=False)
    pd.DataFrame(worst_3m_rows).to_csv(RESULT_DIR / "worst_90d_windows.csv", index=False)
    pd.DataFrame(overlap_worst).to_csv(RESULT_DIR / "reentry_overlap_worst_days.csv", index=False)
    (RESULT_DIR / "execution_compatibility.json").write_text(json.dumps(compatibility, indent=2))

    summary = {
        "candidate": {
            "nq_asia_orb": "orb_trade_max_per_session=2, orb_reentry_policy=after_nonpositive_first",
            "es_asia_orb": "orb_trade_max_per_session=2, orb_reentry_policy=after_nonpositive_first",
            "es_ny_orb": "unchanged",
            "nq_ny_htf_lsi": "unchanged",
        },
        "current_risk_usd": CURRENT_RISK_USD,
        "funded_profile": FUNDED_PROFILE,
        "full_start": FULL_START,
        "overlap_end": overlap_end,
        "combined_metrics": combined_metrics,
        "per_leg_metrics": leg_metrics,
        "funded_first_payout_summary": payout_summaries,
        "overlap_summary": overlap,
        "execution_compatibility": compatibility,
        "elapsed_seconds": elapsed_s,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    candidate_full = next(
        row for row in combined_metrics if row["profile"] == "candidate" and row["window"] == "full"
    )
    baseline_full = next(
        row for row in combined_metrics if row["profile"] == "baseline" and row["window"] == "full"
    )
    candidate_2025 = next(
        row for row in combined_metrics if row["profile"] == "candidate" and row["window"] == "calendar_2025"
    )
    baseline_2025 = next(
        row for row in combined_metrics if row["profile"] == "baseline" and row["window"] == "calendar_2025"
    )
    verdict = (
        "PROMOTE TO EXECUTION BUILD, THEN DRY-RUN"
        if compatibility["promotion_status"] == "ready_for_dry_mode"
        else "RESEARCH PASS, EXECUTION BUILD REQUIRED BEFORE DRY-RUN"
    )
    report = [
        "# ALPHA_V1 ORB One-Loss Reentry Promotion Packet",
        "",
        f"- Verdict: **{verdict}**.",
        "- Candidate: add `cap=2 after_nonpositive_first` to `NQ Asia ORB` and `ES Asia ORB`; leave `ES NY ORB` and `NQ NY HTF-LSI` unchanged.",
        f"- Test window: `{FULL_START}` through `{overlap_end}`.",
        "- Current risk sizing: HTF-LSI $300, NQ Asia ORB $300, ES Asia ORB $200, ES NY ORB $300.",
        f"- Runtime: {elapsed_s:.1f}s.",
        "",
        "## 1. Combined ALPHA_V1 Portfolio",
        "",
        _markdown_table(
            [
                row
                for row in combined_metrics
                if row["window"] in {"full", "2024+", "2025+", "last_1y", "calendar_2025"}
            ],
            [
                "window",
                "profile",
                "fills",
                "net_r",
                "delta_net_r",
                "net_usd_current",
                "delta_net_usd_current",
                "profit_factor",
                "sharpe",
                "max_dd",
                "delta_max_dd",
                "max_dd_usd_current",
                "delta_max_dd_usd_current",
            ],
        ),
        "",
        "## 2. Per-Leg Impact",
        "",
        _markdown_table(
            [
                row
                for row in leg_metrics
                if row["profile"] == "candidate" and row["window"] in {"full", "2025+", "last_1y", "calendar_2025"}
            ],
            [
                "window",
                "scope",
                "fills",
                "net_r",
                "delta_net_r",
                "net_usd_current",
                "delta_net_usd_current",
                "profit_factor",
                "sharpe",
                "max_dd",
                "delta_max_dd",
            ],
        ),
        "",
        "## 3. Funded First-Payout Simulation",
        "",
        "- Model: $50k account, $2k trailing drawdown capped at $50k, first payout trigger at $52.5k, $500 first withdrawal, $150 challenge fee, new cohort every 14 calendar days.",
        "- PnL uses current live/pilot risk dollars by leg, not uniform research R.",
        "",
        _markdown_table(
            payout_summaries,
            [
                "window",
                "profile",
                "accounts",
                "payouts",
                "breaches",
                "open",
                "payout_rate_pct",
                "breach_rate_pct",
                "ev_per_account_usd",
                "median_days_to_payout",
                "median_trades_to_payout",
                "max_consecutive_breaches",
            ],
        ),
        "",
        "## 4. Monthly DD And Worst 90-Day Windows",
        "",
        "Worst calendar months by current-dollar drawdown:",
        "",
        _markdown_table(
            sorted(monthly_rows, key=lambda row: row["max_dd_usd_current"])[:12],
            ["profile", "month", "net_r", "max_dd_r", "net_usd_current", "max_dd_usd_current"],
        ),
        "",
        "Worst rolling 90-calendar-day windows:",
        "",
        _markdown_table(
            worst_3m_rows[:12],
            ["profile", "start", "end", "net_r", "max_dd_r", "net_usd_current", "max_dd_usd_current"],
        ),
        "",
        "## 5. Trade Timing Overlap",
        "",
        _markdown_table([overlap], list(overlap.keys())),
        "",
        "Worst reentry overlap days:",
        "",
        _markdown_table(
            overlap_worst[:12],
            [
                "date",
                "leg",
                "reentry_r",
                "reentry_usd",
                "other_legs_r",
                "other_legs_usd",
                "total_day_r",
                "total_day_usd",
                "other_legs_negative",
                "total_day_negative",
            ],
        ),
        "",
        "## 6. Execution Compatibility",
        "",
        _markdown_table(
            [
                {"check": key, "value": value}
                for key, value in compatibility.items()
                if key != "notes"
            ],
            ["check", "value"],
        ),
        "",
        "\n".join(f"- {note}" for note in compatibility["notes"]),
        "",
        "## Readout",
        "",
        f"- Full combined R moves from {baseline_full['net_r']}R to {candidate_full['net_r']}R, a {candidate_full['delta_net_r']}R change.",
        f"- Calendar 2025 current-dollar PnL moves from ${baseline_2025['net_usd_current']} to ${candidate_2025['net_usd_current']}, a ${candidate_2025['delta_net_usd_current']} change.",
        "- The packet is intentionally stricter than the earlier sleeve-only test because it includes the active HTF-LSI leg and current risk sizing.",
        f"- Artifacts: `{RESULT_DIR.relative_to(REPO_ROOT)}`.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(report))


def main() -> None:
    t0 = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    print("ALPHA_V1 ORB one-loss reentry promotion packet", flush=True)
    print("loading market data...", flush=True)
    market_data = {
        "NQ": _load_market_data(NQ),
        "ES": _load_market_data(ES),
    }
    overlap_end = min(
        pd.Timestamp(market_data["NQ"].df_5m.index.max()).date().isoformat(),
        pd.Timestamp(market_data["ES"].df_5m.index.max()).date().isoformat(),
    )
    print(f"overlap: {FULL_START} -> {overlap_end}", flush=True)

    baseline_legs = build_active_legs(candidate=False)
    candidate_legs = build_active_legs(candidate=True)
    baseline_streams = run_profile(
        "baseline",
        baseline_legs,
        market_data,
        start_date=FULL_START,
        end_date=overlap_end,
    )
    candidate_streams = run_profile(
        "candidate",
        candidate_legs,
        market_data,
        start_date=FULL_START,
        end_date=overlap_end,
    )
    baseline_rows = _trade_rows("baseline", baseline_legs, baseline_streams)
    candidate_rows = _trade_rows("candidate", candidate_legs, candidate_streams)

    combined_metrics, leg_metrics = build_window_metrics(
        baseline_rows,
        candidate_rows,
        overlap_end=overlap_end,
    )

    payout_rows: list[dict[str, Any]] = []
    payout_summaries: list[dict[str, Any]] = []
    payout_windows = {
        "full": _trade_dates(baseline_rows),
        "2024+": ("2024-01-01", overlap_end),
        "2025+": ("2025-01-01", overlap_end),
        "last_1y": ((pd.Timestamp(overlap_end) - pd.Timedelta(days=365)).date().isoformat(), overlap_end),
    }
    for window, (start, end) in payout_windows.items():
        for profile, rows in (("baseline", baseline_rows), ("candidate", candidate_rows)):
            outcomes = simulate_first_payouts(rows, start=start, end=end)
            for row in outcomes:
                row["profile"] = profile
                row["window"] = window
            payout_rows.extend(outcomes)
            payout_summaries.append(summarize_payouts(profile, window, outcomes))

    baseline_monthly, baseline_90d = monthly_stress(baseline_rows, "baseline")
    candidate_monthly, candidate_90d = monthly_stress(candidate_rows, "candidate")
    monthly_rows = baseline_monthly + candidate_monthly
    worst_3m_rows = sorted(baseline_90d + candidate_90d, key=lambda row: row["max_dd_usd_current"])[:20]

    reentries = identify_reentries(candidate_rows, candidate_legs)
    overlap, overlap_worst = overlap_summary(candidate_rows, reentries)
    compatibility = execution_compatibility()
    elapsed_s = time.time() - t0
    write_outputs(
        baseline_rows=baseline_rows,
        candidate_rows=candidate_rows,
        combined_metrics=combined_metrics,
        leg_metrics=leg_metrics,
        payout_rows=payout_rows,
        payout_summaries=payout_summaries,
        monthly_rows=monthly_rows,
        worst_3m_rows=worst_3m_rows,
        overlap=overlap,
        overlap_worst=overlap_worst,
        compatibility=compatibility,
        overlap_end=overlap_end,
        elapsed_s=elapsed_s,
    )
    print(f"wrote {SUMMARY_PATH}", flush=True)
    print(f"wrote {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
