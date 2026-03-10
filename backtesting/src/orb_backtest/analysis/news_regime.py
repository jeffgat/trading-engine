"""Regime analysis for news straddle events.

Buckets trades by market conditions (volatility, trend, day of week, month,
direction) and computes per-bucket stats to identify what drives win rate.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median

import numpy as np
import pandas as pd

from ..data.loader import DATA_DIR, _load_ohlcv


def _load_daily_features(instrument: str, start: str, end: str) -> pd.DataFrame:
    """Load 5m data, resample to daily, and compute regime features.

    Returns a DataFrame indexed by date (normalized) with columns:
    atr_14, atr_pct, range_pct, realized_vol_5d, realized_vol_21d,
    close_vs_sma20, prev_close, daily_return.
    """
    # Load with padding for warmup
    pad_start = (pd.Timestamp(start) - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    stem = DATA_DIR / f"{instrument}_5m"
    df = _load_ohlcv(stem, pad_start, end)

    if df.empty:
        return pd.DataFrame()

    daily = df.resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["close"])

    close = daily["close"].values
    high = daily["high"].values
    low = daily["low"].values

    # True range + ATR(14)
    prev_close = np.roll(close, 1)
    prev_close[0] = np.nan
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
    )
    atr = np.full_like(tr, np.nan)
    length = 14
    if len(tr) >= length + 1:
        atr[length] = np.nanmean(tr[1:length + 1])
        for i in range(length + 1, len(tr)):
            atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length

    # Shift by 1 day (no lookahead)
    atr_shifted = np.roll(atr, 1)
    atr_shifted[0] = np.nan

    # Daily returns
    returns = np.diff(close, prepend=np.nan) / np.roll(close, 1)
    returns[0] = np.nan
    log_returns = np.log(close / np.roll(close, 1))
    log_returns[0] = np.nan

    # Realized vol (annualized)
    rv5 = pd.Series(log_returns).rolling(5).std().values * np.sqrt(252)
    rv21 = pd.Series(log_returns).rolling(21).std().values * np.sqrt(252)

    # Range %
    range_pct = (high - low) / close

    # Close vs SMA20
    sma20 = pd.Series(close).rolling(20).mean().values
    close_vs_sma20 = close / sma20 - 1

    # Volume relative to 21d MA
    vol_vals = daily["volume"].values.astype(float)
    vol_ma21 = pd.Series(vol_vals).rolling(21).mean().values
    volume_ratio = np.where(vol_ma21 > 0, vol_vals / vol_ma21, np.nan)

    features = pd.DataFrame({
        "atr_14": atr_shifted,
        "atr_pct": np.where(close > 0, atr_shifted / close * 100, np.nan),
        "range_pct": range_pct * 100,
        "realized_vol_5d": rv5 * 100,
        "realized_vol_21d": rv21 * 100,
        "close_vs_sma20": close_vs_sma20 * 100,
        "prev_close": prev_close,
        "daily_return": returns * 100,
        "volume_ratio": volume_ratio,
    }, index=daily.index.normalize())

    return features


def _bucket_stats(events: list[dict]) -> dict:
    """Compute aggregate stats for a bucket of events."""
    filled = [e for e in events if e.get("direction_filled") is not None]
    n = len(filled)
    if n == 0:
        return {
            "trades": 0, "win_rate": 0, "target_hit_rate": 0,
            "avg_final_pts": 0, "total_pts": 0, "avg_mfe": 0, "avg_mae": 0,
            "stop_loss_rate": 0, "whipsaw_rate": 0,
        }

    winners = sum(1 for e in filled if e["final_points"] > 0)
    target_hits = sum(1 for e in filled if e["target_hit"])
    stop_losses = sum(1 for e in filled if e["exit_type"] == "stop_loss")
    whipsaws = sum(1 for e in filled if e["whipsaw"])
    finals = [e["final_points"] for e in filled]
    mfes = [e["mfe_points"] for e in filled]
    maes = [e["mae_points"] for e in filled]

    return {
        "trades": n,
        "win_rate": round(winners / n, 4),
        "target_hit_rate": round(target_hits / n, 4),
        "avg_final_pts": round(sum(finals) / n, 2),
        "total_pts": round(sum(finals), 2),
        "median_final_pts": round(median(finals), 2),
        "avg_mfe": round(sum(mfes) / n, 2),
        "avg_mae": round(sum(maes) / n, 2),
        "stop_loss_rate": round(stop_losses / n, 4),
        "whipsaw_rate": round(whipsaws / n, 4),
    }


def build_news_regime_report(
    events: list[dict],
    instrument: str,
) -> dict:
    """Build a regime report from news straddle events.

    Analyzes trades by:
    - Volatility regime (ATR percentile: low/medium/high)
    - Day of week
    - Month
    - Direction (long vs short)
    - Prior-day return (up vs down)
    - Realized vol (5d) bucket
    """
    if not events:
        return {"error": "No events to analyze"}

    filled = [e for e in events if e.get("direction_filled") is not None]
    if not filled:
        return {"error": "No filled events to analyze"}

    # Determine date range
    dates = [e["date"] for e in filled]
    start = min(dates)
    end = max(dates)

    # Load daily features
    features = _load_daily_features(instrument, start, end)
    if features.empty:
        return {"error": "Could not load daily features"}

    # Enrich events with daily features
    for e in filled:
        dt = pd.Timestamp(e["date"]).normalize()
        e["_weekday"] = dt.dayofweek  # 0=Mon, 4=Fri
        e["_weekday_name"] = dt.strftime("%A")
        e["_month"] = dt.month
        e["_month_name"] = dt.strftime("%b")
        e["_year"] = dt.year

        if dt in features.index:
            row = features.loc[dt]
            e["_atr_pct"] = float(row["atr_pct"]) if pd.notna(row["atr_pct"]) else None
            e["_rv5"] = float(row["realized_vol_5d"]) if pd.notna(row["realized_vol_5d"]) else None
            e["_rv21"] = float(row["realized_vol_21d"]) if pd.notna(row["realized_vol_21d"]) else None
            e["_range_pct"] = float(row["range_pct"]) if pd.notna(row["range_pct"]) else None
            e["_close_vs_sma20"] = float(row["close_vs_sma20"]) if pd.notna(row["close_vs_sma20"]) else None
            e["_daily_return"] = float(row["daily_return"]) if pd.notna(row["daily_return"]) else None
            e["_volume_ratio"] = float(row["volume_ratio"]) if pd.notna(row["volume_ratio"]) else None
        else:
            e["_atr_pct"] = None
            e["_rv5"] = None
            e["_rv21"] = None
            e["_range_pct"] = None
            e["_close_vs_sma20"] = None
            e["_daily_return"] = None
            e["_volume_ratio"] = None

    report: dict = {"dimensions": {}}

    # ── 1. Volatility regime (ATR % terciles) ──
    atr_vals = [e["_atr_pct"] for e in filled if e["_atr_pct"] is not None]
    if len(atr_vals) >= 6:
        p33 = float(np.percentile(atr_vals, 33))
        p67 = float(np.percentile(atr_vals, 67))
        buckets: dict[str, list] = {"Low Vol": [], "Med Vol": [], "High Vol": []}
        for e in filled:
            v = e["_atr_pct"]
            if v is None:
                continue
            if v <= p33:
                buckets["Low Vol"].append(e)
            elif v <= p67:
                buckets["Med Vol"].append(e)
            else:
                buckets["High Vol"].append(e)

        report["dimensions"]["volatility_atr"] = {
            "label": "Volatility (14d ATR %)",
            "thresholds": {"low_max": round(p33, 3), "high_min": round(p67, 3)},
            "buckets": {k: _bucket_stats(v) for k, v in buckets.items()},
        }

    # ── 2. Realized vol (5d) terciles ──
    rv5_vals = [e["_rv5"] for e in filled if e["_rv5"] is not None]
    if len(rv5_vals) >= 6:
        p33 = float(np.percentile(rv5_vals, 33))
        p67 = float(np.percentile(rv5_vals, 67))
        buckets = {"Low RV": [], "Med RV": [], "High RV": []}
        for e in filled:
            v = e["_rv5"]
            if v is None:
                continue
            if v <= p33:
                buckets["Low RV"].append(e)
            elif v <= p67:
                buckets["Med RV"].append(e)
            else:
                buckets["High RV"].append(e)

        report["dimensions"]["realized_vol_5d"] = {
            "label": "Realized Vol (5d annualized)",
            "thresholds": {"low_max": round(p33, 2), "high_min": round(p67, 2)},
            "buckets": {k: _bucket_stats(v) for k, v in buckets.items()},
        }

    # ── 3. Trend (close vs SMA20) ──
    trend_events = [e for e in filled if e["_close_vs_sma20"] is not None]
    if len(trend_events) >= 4:
        buckets = {"Below SMA20": [], "Above SMA20": []}
        for e in trend_events:
            if e["_close_vs_sma20"] < 0:
                buckets["Below SMA20"].append(e)
            else:
                buckets["Above SMA20"].append(e)

        report["dimensions"]["trend_sma20"] = {
            "label": "Trend (Close vs SMA20)",
            "buckets": {k: _bucket_stats(v) for k, v in buckets.items()},
        }

    # ── 4. Prior-day return ──
    return_events = [e for e in filled if e["_daily_return"] is not None]
    if len(return_events) >= 4:
        buckets = {"Prior Day Down": [], "Prior Day Up": []}
        for e in return_events:
            if e["_daily_return"] < 0:
                buckets["Prior Day Down"].append(e)
            else:
                buckets["Prior Day Up"].append(e)

        report["dimensions"]["prior_day_return"] = {
            "label": "Prior-Day Return",
            "buckets": {k: _bucket_stats(v) for k, v in buckets.items()},
        }

    # ── 5. Day of week ──
    dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    dow_buckets: dict[str, list] = {d: [] for d in dow_names}
    for e in filled:
        dow_buckets[e["_weekday_name"]].append(e)
    # Only include days with trades
    dow_buckets = {k: v for k, v in dow_buckets.items() if v}
    if len(dow_buckets) >= 2:
        report["dimensions"]["day_of_week"] = {
            "label": "Day of Week",
            "buckets": {k: _bucket_stats(v) for k, v in dow_buckets.items()},
        }

    # ── 6. Direction ──
    dir_buckets: dict[str, list] = {"Long": [], "Short": []}
    for e in filled:
        if e["direction_filled"] == "long":
            dir_buckets["Long"].append(e)
        else:
            dir_buckets["Short"].append(e)
    dir_buckets = {k: v for k, v in dir_buckets.items() if v}
    if len(dir_buckets) >= 1:
        report["dimensions"]["direction"] = {
            "label": "Direction",
            "buckets": {k: _bucket_stats(v) for k, v in dir_buckets.items()},
        }

    # ── 7. Month ──
    month_buckets: dict[str, list] = {}
    for e in filled:
        key = e["_month_name"]
        month_buckets.setdefault(key, []).append(e)
    # Sort by month number
    month_order = {m: i for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )}
    month_buckets = dict(sorted(month_buckets.items(), key=lambda x: month_order.get(x[0], 0)))
    if len(month_buckets) >= 2:
        report["dimensions"]["month"] = {
            "label": "Month",
            "buckets": {k: _bucket_stats(v) for k, v in month_buckets.items()},
        }

    # ── 8. Volume regime ──
    vol_events = [e for e in filled if e["_volume_ratio"] is not None]
    if len(vol_events) >= 6:
        vr_vals = [e["_volume_ratio"] for e in vol_events]
        p33 = float(np.percentile(vr_vals, 33))
        p67 = float(np.percentile(vr_vals, 67))
        buckets = {"Low Volume": [], "Normal Volume": [], "High Volume": []}
        for e in vol_events:
            v = e["_volume_ratio"]
            if v <= p33:
                buckets["Low Volume"].append(e)
            elif v <= p67:
                buckets["Normal Volume"].append(e)
            else:
                buckets["High Volume"].append(e)

        report["dimensions"]["volume"] = {
            "label": "Volume (vs 21d MA)",
            "thresholds": {"low_max": round(p33, 2), "high_min": round(p67, 2)},
            "buckets": {k: _bucket_stats(v) for k, v in buckets.items()},
        }

    # Summary
    report["total_filled"] = len(filled)
    report["date_range"] = {"start": start, "end": end}
    report["instrument"] = instrument

    return report
