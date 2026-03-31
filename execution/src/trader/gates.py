"""Pre-trade gate helpers for continuation sessions.

These gates intentionally mirror the backtesting research logic closely:
- Daily bull/no-low-confidence regime routing for the bull specialist.
- 15m HH/HL + VWAP context confirmation on the signal bar.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DailyHistoryProvider = Callable[[str], list[tuple[date, float, float, float, float]]]
_daily_history_provider: DailyHistoryProvider | None = None


def _bars_to_frame(bars) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [bar.open for bar in bars],
            "high": [bar.high for bar in bars],
            "low": [bar.low for bar in bars],
            "close": [bar.close for bar in bars],
            "volume": [bar.volume for bar in bars],
        },
        index=pd.DatetimeIndex([bar.timestamp for bar in bars]),
    )


def _daily_bars_to_frame(
    daily_bars: list[tuple[date, float, float, float, float]],
) -> pd.DataFrame:
    if not daily_bars:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = pd.DataFrame(
        daily_bars,
        columns=["date", "open", "high", "low", "close"],
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def _append_placeholder_day_if_needed(df: pd.DataFrame, date_key: str) -> pd.DataFrame:
    if df.empty:
        return df

    requested = pd.Timestamp(datetime.strptime(date_key, "%Y%m%d").date())
    if requested in df.index:
        return df

    last_date = df.index[-1]
    if requested != last_date + timedelta(days=1):
        return df

    last_row = df.iloc[-1]
    placeholder = pd.DataFrame(
        {
            "open": [last_row["close"]],
            "high": [last_row["close"]],
            "low": [last_row["close"]],
            "close": [last_row["close"]],
        },
        index=pd.DatetimeIndex([requested]),
    )
    return pd.concat([df, placeholder])


def _build_nq_ny_regime_calendar(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["date", "low_confidence", "regime"])

    close = daily["close"]
    log_returns = np.log(close / close.shift(1))
    realized_vol_21d = log_returns.rolling(21).std() * np.sqrt(252)
    close_vs_sma20 = close / close.rolling(20).mean() - 1.0
    ret_5d = close.pct_change(5)

    calendar = pd.DataFrame(
        {
            "date": daily.index.normalize(),
            "close_vs_sma20": close_vs_sma20.shift(1),
            "ret_5d": ret_5d.shift(1),
            "realized_vol_21d": realized_vol_21d.shift(1),
        }
    )
    calendar["warmup_ok"] = calendar[["close_vs_sma20", "ret_5d", "realized_vol_21d"]].notna().all(axis=1)
    calendar["low_confidence"] = calendar["warmup_ok"] & (
        (calendar["close_vs_sma20"].abs() < 0.0025) | (calendar["ret_5d"].abs() < 0.005)
    )

    bull_mask = calendar["warmup_ok"] & (calendar["close_vs_sma20"] >= 0.005) & (calendar["ret_5d"] > 0.0)
    bear_mask = calendar["warmup_ok"] & (calendar["close_vs_sma20"] <= -0.005) & (calendar["ret_5d"] < 0.0)

    calendar["regime"] = "sideways"
    calendar.loc[bull_mask, "regime"] = "bull"
    calendar.loc[bear_mask, "regime"] = "bear"
    calendar.loc[~calendar["warmup_ok"], "regime"] = "warmup"
    return calendar.reset_index(drop=True)


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_vol = df["volume"].cumsum().replace(0, np.nan)
    return (typical * df["volume"]).cumsum() / cum_vol


def _hh_hl_2_bull(session_bars) -> bool:
    if len(session_bars) < 9:
        return False

    current_idx = len(session_bars) - 1
    current_group = current_idx // 3
    pos_in_group = current_idx % 3
    last_complete_group = current_group if pos_in_group == 2 else current_group - 1
    if last_complete_group < 2:
        return False

    highs: list[float] = []
    lows: list[float] = []
    for group in range(last_complete_group + 1):
        start = group * 3
        chunk = session_bars[start : start + 3]
        if len(chunk) < 3:
            break
        highs.append(max(bar.high for bar in chunk))
        lows.append(min(bar.low for bar in chunk))

    if len(highs) <= last_complete_group:
        return False

    k = last_complete_group
    return (
        highs[k] > highs[k - 1]
        and lows[k] > lows[k - 1]
        and highs[k - 1] > highs[k - 2]
        and lows[k - 1] > lows[k - 2]
    )


def set_daily_history_provider(provider: DailyHistoryProvider | None) -> None:
    global _daily_history_provider
    _daily_history_provider = provider


def build_regime_gate(name: str | None) -> Callable[[str], bool] | None:
    if not name:
        return None
    if name != "bull_no_low_confidence":
        raise ValueError(f"Unknown regime gate: {name}")

    def _gate(date_key: str) -> bool:
        if _daily_history_provider is None:
            logger.warning(
                "Regime gate '%s' has no daily history provider — blocking date=%s",
                name,
                date_key,
            )
            return False

        daily_bars = _daily_history_provider("NQ.FUT")
        if not daily_bars:
            logger.warning(
                "Regime gate '%s' has no NQ daily history — blocking date=%s",
                name,
                date_key,
            )
            return False

        daily = _daily_bars_to_frame(daily_bars)
        daily = _append_placeholder_day_if_needed(daily, date_key)
        calendar = _build_nq_ny_regime_calendar(daily)
        if calendar.empty:
            logger.warning(
                "Regime gate '%s' could not build a calendar from NQ daily history — blocking date=%s",
                name,
                date_key,
            )
            return False

        row_df = calendar.loc[pd.to_datetime(calendar["date"]).dt.strftime("%Y%m%d") == date_key]
        if row_df.empty:
            logger.warning(
                "Regime gate '%s' has no calendar row for date=%s (history_end=%s) — blocking",
                name,
                date_key,
                daily.index[-1].strftime("%Y%m%d") if not daily.empty else "-",
            )
            return False

        row = row_df.iloc[-1]
        if row is None:
            return False
        return str(row["regime"]) == "bull" and not bool(row["low_confidence"])

    return _gate


def build_structure_gate(name: str | None):
    if not name:
        return None
    if name != "hh_hl_2_vwap":
        raise ValueError(f"Unknown structure gate: {name}")

    def _gate(engine, _bar) -> bool:
        session_bars = getattr(engine, "_session_bars", [])
        if len(session_bars) < 3:
            return False

        df = _bars_to_frame(session_bars)
        vwap_value = float(_session_vwap(df).iloc[-1])
        close_value = float(df["close"].iloc[-1])
        if np.isnan(vwap_value):
            return False

        return _hh_hl_2_bull(session_bars) and close_value > vwap_value

    return _gate
