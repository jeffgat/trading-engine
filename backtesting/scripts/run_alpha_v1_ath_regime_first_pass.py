#!/usr/bin/env python3
"""First-pass futures ATH regime attribution for active ALPHA_V1 legs.

This is deliberately an attribution script, not a simulator change.  It uses
the saved active ALPHA_V1 baseline trade export from the 2026-05-02 reentry
promotion packet, then annotates each filled trade with point-in-time ATH
features computed from the local continuous futures data only.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_ath_regime_first_pass_20260505"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ATH_REGIME_FIRST_PASS_20260505.md"
SOURCE_TRADES = ROOT / "data" / "results" / "alpha_v1_orb_reentry_promotion_20260502" / "baseline_trades.csv"
FULL_START = "2016-04-17"
WINDOWS = {
    "full": None,
    "2024+": "2024-01-01",
    "2025+": "2025-01-01",
}


PCT_BUCKETS = [
    "above_prior_ath",
    "0-0.5%",
    "0.5-1%",
    "1-2%",
    "2-5%",
    "5-10%",
    ">10%",
    "unknown",
]
ATR_BUCKETS = [
    "above_prior_ath",
    "0-0.5 ATR",
    "0.5-1 ATR",
    "1-2 ATR",
    "2-5 ATR",
    ">5 ATR",
    "unknown",
]
ROOM_R_BUCKETS = [
    "above_prior_ath",
    "0-1R",
    "1-2R",
    "2-5R",
    "5-10R",
    ">10R",
    "unknown",
]
AGE_BUCKETS = [
    "0-1d",
    "2-5d",
    "6-20d",
    "21-60d",
    ">60d",
    "unknown",
]


@dataclass(frozen=True)
class SymbolContext:
    symbol: str
    df_full: pd.DataFrame
    df_trade_window: pd.DataFrame
    cum_high: np.ndarray
    cum_close: np.ndarray
    prior_cum_high: np.ndarray
    last_ath_pos: np.ndarray
    daily_features: pd.DataFrame


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return f"{100.0 * float(value):.1f}%"


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _load_5m(symbol: str) -> pd.DataFrame:
    path = ROOT / "data" / "raw" / f"{symbol}_5m.parquet"
    df = pd.read_parquet(path)
    df = df.sort_index()
    return df[["open", "high", "low", "close", "volume"]].copy()


def _last_ath_positions(high: np.ndarray) -> np.ndarray:
    out = np.empty(len(high), dtype=np.int64)
    running = -np.inf
    last_pos = -1
    for i, value in enumerate(high):
        if value >= running:
            running = value
            last_pos = i
        out[i] = last_pos
    return out


def _daily_features(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.resample("1D")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
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
    daily["atr14_prior"] = true_range.rolling(14, min_periods=14).mean().shift(1)
    prior_daily_ath = daily["high"].cummax().shift(1)
    daily["new_ath_day"] = daily["high"] > prior_daily_ath
    daily["new_ath_20d_count_prior"] = daily["new_ath_day"].shift(1).rolling(20, min_periods=1).sum()
    daily["prior_close_ath"] = daily["close"].cummax().shift(1)
    daily["prior_high_ath"] = prior_daily_ath
    return daily


def _build_symbol_context(symbol: str) -> SymbolContext:
    df_full = _load_5m(symbol)
    df_trade_window = df_full[df_full.index >= FULL_START]
    high = df_full["high"].to_numpy(dtype=float)
    close = df_full["close"].to_numpy(dtype=float)
    cum_high = np.maximum.accumulate(high)
    cum_close = np.maximum.accumulate(close)
    prior_cum_high = np.concatenate([[np.nan], cum_high[:-1]])
    return SymbolContext(
        symbol=symbol,
        df_full=df_full,
        df_trade_window=df_trade_window,
        cum_high=cum_high,
        cum_close=cum_close,
        prior_cum_high=prior_cum_high,
        last_ath_pos=_last_ath_positions(high),
        daily_features=_daily_features(df_full),
    )


def _pct_bucket(gap_pct: float) -> str:
    if not math.isfinite(gap_pct):
        return "unknown"
    if gap_pct < 0:
        return "above_prior_ath"
    if gap_pct <= 0.5:
        return "0-0.5%"
    if gap_pct <= 1.0:
        return "0.5-1%"
    if gap_pct <= 2.0:
        return "1-2%"
    if gap_pct <= 5.0:
        return "2-5%"
    if gap_pct <= 10.0:
        return "5-10%"
    return ">10%"


def _atr_bucket(distance_atr: float) -> str:
    if not math.isfinite(distance_atr):
        return "unknown"
    if distance_atr < 0:
        return "above_prior_ath"
    if distance_atr <= 0.5:
        return "0-0.5 ATR"
    if distance_atr <= 1.0:
        return "0.5-1 ATR"
    if distance_atr <= 2.0:
        return "1-2 ATR"
    if distance_atr <= 5.0:
        return "2-5 ATR"
    return ">5 ATR"


def _room_r_bucket(room_r: float) -> str:
    if not math.isfinite(room_r):
        return "unknown"
    if room_r < 0:
        return "above_prior_ath"
    if room_r <= 1.0:
        return "0-1R"
    if room_r <= 2.0:
        return "1-2R"
    if room_r <= 5.0:
        return "2-5R"
    if room_r <= 10.0:
        return "5-10R"
    return ">10R"


def _age_bucket(days: float) -> str:
    if not math.isfinite(days):
        return "unknown"
    if days <= 1:
        return "0-1d"
    if days <= 5:
        return "2-5d"
    if days <= 20:
        return "6-20d"
    if days <= 60:
        return "21-60d"
    return ">60d"


def _event_position(ctx: SymbolContext, timestamp: pd.Timestamp, *, include_bar: bool) -> int:
    side = "right" if include_bar else "left"
    pos = int(ctx.df_full.index.searchsorted(timestamp, side=side) - 1)
    return max(0, min(pos, len(ctx.df_full) - 1))


def _daily_row(ctx: SymbolContext, timestamp: pd.Timestamp) -> pd.Series | None:
    key = timestamp.normalize()
    idx = ctx.daily_features.index.searchsorted(key, side="right") - 1
    if idx < 0:
        return None
    return ctx.daily_features.iloc[int(idx)]


def _annotate_context(
    trade: pd.Series,
    ctx: SymbolContext,
    *,
    context: str,
) -> dict[str, Any]:
    if context == "signal":
        signal_bar = int(trade["signal_bar"])
        if signal_bar < 0 or signal_bar >= len(ctx.df_trade_window):
            timestamp = pd.Timestamp(trade["fill_time"])
            pos = _event_position(ctx, timestamp, include_bar=False)
        else:
            timestamp = pd.Timestamp(ctx.df_trade_window.index[signal_bar])
            pos = _event_position(ctx, timestamp, include_bar=True)
        event_price = float(ctx.df_full["close"].iloc[pos])
        include_current_bar = True
    elif context == "fill":
        timestamp = pd.Timestamp(trade["fill_time"])
        pos = _event_position(ctx, timestamp, include_bar=False)
        event_price = float(trade["entry_price"])
        include_current_bar = False
    else:
        raise ValueError(f"unknown context {context!r}")

    ath = float(ctx.cum_high[pos])
    close_ath = float(ctx.cum_close[pos])
    prior_ath = float(ctx.prior_cum_high[pos]) if math.isfinite(ctx.prior_cum_high[pos]) else ath
    ath_for_distance = ath if include_current_bar else prior_ath
    if not math.isfinite(ath_for_distance) or ath_for_distance <= 0:
        ath_for_distance = ath

    gap_points = ath_for_distance - event_price
    gap_pct = (gap_points / ath_for_distance) * 100.0 if ath_for_distance > 0 else np.nan
    close_gap_pct = ((close_ath - event_price) / close_ath) * 100.0 if close_ath > 0 else np.nan
    last_ath_pos = int(ctx.last_ath_pos[pos])
    last_ath_ts = ctx.df_full.index[last_ath_pos] if last_ath_pos >= 0 else pd.NaT
    days_since_ath = (timestamp - last_ath_ts).total_seconds() / 86400.0 if pd.notna(last_ath_ts) else np.nan

    daily = _daily_row(ctx, timestamp)
    atr14 = float(daily["atr14_prior"]) if daily is not None and math.isfinite(float(daily["atr14_prior"])) else np.nan
    ath_gap_atr = gap_points / atr14 if math.isfinite(atr14) and atr14 > 0 else np.nan
    risk_points = float(trade["risk_points"])
    room_to_ath_r = gap_points / risk_points if risk_points > 0 else np.nan

    event_bar_high = float(ctx.df_full["high"].iloc[pos])
    event_bar_close = float(ctx.df_full["close"].iloc[pos])
    prior_ath_before_bar = prior_ath
    event_bar_swept_prior_ath = bool(math.isfinite(prior_ath_before_bar) and event_bar_high > prior_ath_before_bar)
    event_bar_closed_above_prior_ath = bool(math.isfinite(prior_ath_before_bar) and event_bar_close > prior_ath_before_bar)

    recent_ath_count = (
        float(daily["new_ath_20d_count_prior"])
        if daily is not None and math.isfinite(float(daily["new_ath_20d_count_prior"]))
        else np.nan
    )

    return {
        "context": context,
        "context_time": timestamp.isoformat(),
        "context_pos": pos,
        "context_price": event_price,
        "ath_price": ath_for_distance,
        "ath_gap_points": gap_points,
        "ath_gap_pct": gap_pct,
        "ath_pct_bucket": _pct_bucket(gap_pct),
        "close_ath_gap_pct": close_gap_pct,
        "ath_gap_atr": ath_gap_atr,
        "ath_atr_bucket": _atr_bucket(ath_gap_atr),
        "room_to_ath_r": room_to_ath_r,
        "room_to_ath_r_bucket": _room_r_bucket(room_to_ath_r),
        "last_ath_time": "" if pd.isna(last_ath_ts) else last_ath_ts.isoformat(),
        "days_since_ath": days_since_ath,
        "ath_age_bucket": _age_bucket(days_since_ath),
        "recent_ath_20d_count": recent_ath_count,
        "event_bar_swept_prior_ath": event_bar_swept_prior_ath,
        "event_bar_closed_above_prior_ath": event_bar_closed_above_prior_ath,
    }


def _load_and_annotate_trades() -> pd.DataFrame:
    trades = pd.read_csv(SOURCE_TRADES)
    trades["fill_ts"] = pd.to_datetime(trades["fill_time"])
    trades["exit_ts"] = pd.to_datetime(trades["exit_time"])
    trades = trades.sort_values(["fill_ts", "leg", "leg_trade_ordinal"]).reset_index(drop=True)

    contexts = {symbol: _build_symbol_context(symbol) for symbol in sorted(trades["symbol"].unique())}
    rows: list[dict[str, Any]] = []
    for _, trade in trades.iterrows():
        ctx = contexts[str(trade["symbol"])]
        base = trade.to_dict()
        for context in ("signal", "fill"):
            rows.append({**base, **_annotate_context(trade, ctx, context=context)})
    annotated = pd.DataFrame(rows)
    annotated["window_full"] = True
    annotated["window_2024+"] = annotated["fill_ts"] >= pd.Timestamp("2024-01-01")
    annotated["window_2025+"] = annotated["fill_ts"] >= pd.Timestamp("2025-01-01")
    return annotated


def _profit_factor(r: pd.Series) -> float:
    wins = float(r[r > 0].sum())
    losses = float(-r[r < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def _max_dd_r(frame: pd.DataFrame) -> float:
    ordered = frame.sort_values(["fill_ts", "leg", "leg_trade_ordinal"])
    equity = ordered["r_multiple"].astype(float).cumsum()
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min()) if len(dd) else 0.0


def _bucket_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "trades": 0,
            "net_r": 0.0,
            "avg_r": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_dd_r": 0.0,
            "tp2_rate": 0.0,
            "sl_rate": 0.0,
            "tp1_be_rate": 0.0,
            "eod_rate": 0.0,
        }
    r = frame["r_multiple"].astype(float)
    exits = frame["exit_name"].astype(str)
    return {
        "trades": int(len(frame)),
        "net_r": float(r.sum()),
        "avg_r": float(r.mean()),
        "win_rate": float((r > 0).mean()),
        "profit_factor": _profit_factor(r),
        "max_dd_r": _max_dd_r(frame),
        "tp2_rate": float(exits.isin(["tp1_tp2", "tp2_single"]).mean()),
        "sl_rate": float((exits == "sl").mean()),
        "tp1_be_rate": float((exits == "tp1_be").mean()),
        "eod_rate": float(exits.isin(["eod", "tp1_eod"]).mean()),
    }


def _summaries(annotated: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_specs = [
        ("ath_pct_bucket", PCT_BUCKETS),
        ("ath_atr_bucket", ATR_BUCKETS),
        ("room_to_ath_r_bucket", ROOM_R_BUCKETS),
        ("ath_age_bucket", AGE_BUCKETS),
    ]
    rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    for context in ("signal", "fill"):
        context_df = annotated[annotated["context"] == context].copy()
        for window, start in WINDOWS.items():
            window_df = context_df if start is None else context_df[context_df["fill_ts"] >= pd.Timestamp(start)]
            for leg in [*sorted(window_df["leg"].unique()), "portfolio"]:
                leg_df = window_df if leg == "portfolio" else window_df[window_df["leg"] == leg]
                baseline = _bucket_metrics(leg_df)
                baseline_rows.append({"context": context, "window": window, "leg": leg, **baseline})
                for feature, order in feature_specs:
                    for bucket in order:
                        bucket_df = leg_df[leg_df[feature] == bucket]
                        metrics = _bucket_metrics(bucket_df)
                        rows.append(
                            {
                                "context": context,
                                "window": window,
                                "leg": leg,
                                "feature": feature,
                                "bucket": bucket,
                                "baseline_trades": baseline["trades"],
                                "baseline_net_r": baseline["net_r"],
                                "baseline_avg_r": baseline["avg_r"],
                                "avg_r_delta": metrics["avg_r"] - baseline["avg_r"],
                                **metrics,
                            }
                        )
    return pd.DataFrame(rows), pd.DataFrame(baseline_rows)


def _frame_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    metrics = _bucket_metrics(frame)
    return {
        "trades": metrics["trades"],
        "net_r": metrics["net_r"],
        "avg_r": metrics["avg_r"],
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "max_dd_r": metrics["max_dd_r"],
    }


def _filter_evaluations(annotated: pd.DataFrame) -> pd.DataFrame:
    signal = annotated[annotated["context"] == "signal"].copy()
    filter_specs = [
        (
            "baseline",
            "No ATH filter",
            lambda frame: pd.Series(True, index=frame.index),
        ),
        (
            "skip_pct_0p5_1_all",
            "Skip signal-time 0.5-1% below futures ATH on all legs",
            lambda frame: frame["ath_pct_bucket"] != "0.5-1%",
        ),
        (
            "skip_pct_0p5_1_plus_lsi_5_10",
            "Skip 0.5-1% on all legs plus HTF-LSI 5-10%",
            lambda frame: ~(
                (frame["ath_pct_bucket"] == "0.5-1%")
                | ((frame["leg"] == "nq_ny_htf_lsi") & (frame["ath_pct_bucket"] == "5-10%"))
            ),
        ),
        (
            "skip_lsi_atr_0p5_1",
            "Skip HTF-LSI 0.5-1 ATR below futures ATH",
            lambda frame: ~(
                (frame["leg"] == "nq_ny_htf_lsi") & (frame["ath_atr_bucket"] == "0.5-1 ATR")
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for window, start in WINDOWS.items():
        window_frame = signal if start is None else signal[signal["fill_ts"] >= pd.Timestamp(start)]
        base_metrics = _frame_metrics(window_frame)
        for key, label, mask_fn in filter_specs:
            selected = window_frame[mask_fn(window_frame)]
            metrics = _frame_metrics(selected)
            rows.append(
                {
                    "window": window,
                    "filter": key,
                    "label": label,
                    "removed_trades": base_metrics["trades"] - metrics["trades"],
                    "net_r_delta": metrics["net_r"] - base_metrics["net_r"],
                    "avg_r_delta": metrics["avg_r"] - base_metrics["avg_r"],
                    "pf_delta": metrics["profit_factor"] - base_metrics["profit_factor"],
                    "max_dd_r_delta": metrics["max_dd_r"] - base_metrics["max_dd_r"],
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def _top_bucket_rows(summary: pd.DataFrame, *, context: str, window: str, feature: str, min_trades: int) -> pd.DataFrame:
    subset = summary[
        (summary["context"] == context)
        & (summary["window"] == window)
        & (summary["feature"] == feature)
        & (summary["trades"] >= min_trades)
        & (summary["leg"] != "portfolio")
    ].copy()
    if subset.empty:
        return subset
    subset["score"] = subset["avg_r_delta"]
    return subset.sort_values(["score", "trades"], ascending=[False, False])


def _format_summary_rows(frame: pd.DataFrame, *, limit: int = 12) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in frame.head(limit).iterrows():
        rows.append(
            {
                "Leg": row["leg"],
                "Bucket": row["bucket"],
                "Trades": int(row["trades"]),
                "Net R": round(float(row["net_r"]), 1),
                "Avg R": round(float(row["avg_r"]), 3),
                "Base Avg R": round(float(row["baseline_avg_r"]), 3),
                "Delta": round(float(row["avg_r_delta"]), 3),
                "WR": _pct(float(row["win_rate"])),
                "TP2": _pct(float(row["tp2_rate"])),
                "SL": _pct(float(row["sl_rate"])),
            }
        )
    return rows


def _leg_pct_table(summary: pd.DataFrame, *, context: str, window: str) -> list[dict[str, Any]]:
    subset = summary[
        (summary["context"] == context)
        & (summary["window"] == window)
        & (summary["feature"] == "ath_pct_bucket")
        & (summary["leg"] != "portfolio")
        & (summary["trades"] > 0)
    ]
    rows: list[dict[str, Any]] = []
    for leg, leg_df in subset.groupby("leg", sort=True):
        leg_df = leg_df.sort_values("trades", ascending=False)
        best = leg_df[leg_df["trades"] >= 30].sort_values("avg_r", ascending=False).head(1)
        worst = leg_df[leg_df["trades"] >= 30].sort_values("avg_r", ascending=True).head(1)
        total_trades = int(leg_df["trades"].sum())
        near = leg_df[leg_df["bucket"].isin(["above_prior_ath", "0-0.5%", "0.5-1%", "1-2%"])]
        far = leg_df[leg_df["bucket"].isin(["2-5%", "5-10%", ">10%"])]
        rows.append(
            {
                "Leg": leg,
                "Trades": total_trades,
                "Near ATH R": round(float(near["net_r"].sum()), 1),
                "Near Avg": round(float((near["net_r"].sum() / near["trades"].sum()) if near["trades"].sum() else 0.0), 3),
                "Far R": round(float(far["net_r"].sum()), 1),
                "Far Avg": round(float((far["net_r"].sum() / far["trades"].sum()) if far["trades"].sum() else 0.0), 3),
                "Best >=30": f"{best.iloc[0]['bucket']} ({best.iloc[0]['avg_r']:.3f}R)" if not best.empty else "-",
                "Worst >=30": f"{worst.iloc[0]['bucket']} ({worst.iloc[0]['avg_r']:.3f}R)" if not worst.empty else "-",
            }
        )
    return rows


def _filter_report_rows(filter_eval: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    subset = filter_eval[
        filter_eval["filter"].isin(["baseline", "skip_pct_0p5_1_all", "skip_lsi_atr_0p5_1"])
    ].copy()
    for _, row in subset.iterrows():
        rows.append(
            {
                "Window": row["window"],
                "Filter": row["filter"],
                "Removed": int(row["removed_trades"]),
                "Trades": int(row["trades"]),
                "Net R": round(float(row["net_r"]), 1),
                "Delta R": round(float(row["net_r_delta"]), 1),
                "Avg R": round(float(row["avg_r"]), 3),
                "PF": round(float(row["profit_factor"]), 2) if math.isfinite(float(row["profit_factor"])) else "inf",
                "DD R": round(float(row["max_dd_r"]), 1),
            }
        )
    return rows


def _write_report(
    annotated: pd.DataFrame,
    summary: pd.DataFrame,
    baseline: pd.DataFrame,
    filter_eval: pd.DataFrame,
) -> None:
    full_signal = baseline[(baseline["context"] == "signal") & (baseline["window"] == "full")]
    base_rows = [
        {
            "Leg": row["leg"],
            "Trades": int(row["trades"]),
            "Net R": round(float(row["net_r"]), 1),
            "Avg R": round(float(row["avg_r"]), 3),
            "WR": _pct(float(row["win_rate"])),
            "PF": round(float(row["profit_factor"]), 2) if math.isfinite(float(row["profit_factor"])) else "inf",
            "DD R": round(float(row["max_dd_r"]), 1),
        }
        for _, row in full_signal.sort_values("leg").iterrows()
    ]

    signal_pct_rows = _leg_pct_table(summary, context="signal", window="full")
    signal_pct_recent_rows = _leg_pct_table(summary, context="signal", window="2024+")
    best_full = _format_summary_rows(
        _top_bucket_rows(summary, context="signal", window="full", feature="ath_pct_bucket", min_trades=30),
        limit=10,
    )
    best_atr = _format_summary_rows(
        _top_bucket_rows(summary, context="signal", window="full", feature="ath_atr_bucket", min_trades=30),
        limit=10,
    )
    filter_rows = _filter_report_rows(filter_eval)

    portfolio_pct = summary[
        (summary["context"] == "signal")
        & (summary["window"] == "full")
        & (summary["feature"] == "ath_pct_bucket")
        & (summary["leg"] == "portfolio")
        & (summary["trades"] > 0)
    ].copy()
    portfolio_pct["bucket"] = pd.Categorical(portfolio_pct["bucket"], PCT_BUCKETS, ordered=True)
    portfolio_pct = portfolio_pct.sort_values("bucket")
    portfolio_rows = [
        {
            "Bucket": row["bucket"],
            "Trades": int(row["trades"]),
            "Net R": round(float(row["net_r"]), 1),
            "Avg R": round(float(row["avg_r"]), 3),
            "WR": _pct(float(row["win_rate"])),
            "TP2": _pct(float(row["tp2_rate"])),
            "SL": _pct(float(row["sl_rate"])),
        }
        for _, row in portfolio_pct.iterrows()
    ]

    source_count = annotated[annotated["context"] == "signal"].shape[0]
    report = f"""# ALPHA_V1 ATH Regime First Pass

Date: 2026-05-05

## Scope

- Source trades: `{SOURCE_TRADES.relative_to(ROOT)}`
- Trade set: active ALPHA_V1 baseline from the reentry promotion packet, `{source_count:,}` filled trades.
- Instruments: local continuous futures data only (`NQ_5m.parquet`, `ES_5m.parquet`).
- ATH definition: expanding all-time high of the available continuous futures 5-minute high, with history starting at each file's first bar.
- Decision-safe context: `signal` includes the closed setup bar; `fill` uses only prior completed 5-minute data before the fill timestamp.

This is attribution, not a promoted filter. Buckets with fewer than 30 trades should be treated as color only.

## Baseline Check

{_markdown_table(base_rows, ["Leg", "Trades", "Net R", "Avg R", "WR", "PF", "DD R"])}

## Portfolio By Signal-Time ATH Distance

{_markdown_table(portfolio_rows, ["Bucket", "Trades", "Net R", "Avg R", "WR", "TP2", "SL"])}

## Per-Leg Near/Far Split

Near ATH = above prior ATH through 2% below prior ATH. Far = more than 2% below prior ATH.

{_markdown_table(signal_pct_rows, ["Leg", "Trades", "Near ATH R", "Near Avg", "Far R", "Far Avg", "Best >=30", "Worst >=30"])}

## Recent 2024+ Near/Far Split

{_markdown_table(signal_pct_recent_rows, ["Leg", "Trades", "Near ATH R", "Near Avg", "Far R", "Far Avg", "Best >=30", "Worst >=30"])}

## Strongest Full-History Percent Buckets

{_markdown_table(best_full, ["Leg", "Bucket", "Trades", "Net R", "Avg R", "Base Avg R", "Delta", "WR", "TP2", "SL"])}

## Strongest Full-History ATR-Normalized Buckets

{_markdown_table(best_atr, ["Leg", "Bucket", "Trades", "Net R", "Avg R", "Base Avg R", "Delta", "WR", "TP2", "SL"])}

## Simple Filter Probe

This is not optimization. It only tests the most obvious weak bucket from the first pass.

{_markdown_table(filter_rows, ["Window", "Filter", "Removed", "Trades", "Net R", "Delta R", "Avg R", "PF", "DD R"])}

## First-Pass Read

1. The clearest broad weak zone is `0.5-1%` below futures ATH at signal time. Full history is basically flat (`381` trades for `+2.6R`), and skipping it raises average R and PF while preserving almost all full-history net R.
2. The recent read is stronger: skipping `0.5-1%` improves `2024+` from `+158.6R` to `+161.9R`, and `2025+` from `+106.3R / -11.2R DD` to `+111.5R / -8.5R DD`.
3. This is not a universal "near ATH is good" result. ES Asia likes the closest ATH band, NQ Asia is strongest in deeper ATH drawdowns or 1-2% below ATH, and NQ NY HTF-LSI is best around 2-5% below ATH.
4. The next honest step is a pre-registered same-regime OOS check for `skip_pct_0p5_1_all`, plus leg-specific diagnostics for ES-near-ATH and HTF-LSI 2-5% behavior. Do not promote any threshold from this report directly.

## Artifacts

- Annotated trades: `data/results/alpha_v1_ath_regime_first_pass_20260505/annotated_trades.csv`
- Bucket summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/bucket_summary.csv`
- Baseline summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/baseline_summary.csv`
- Filter probes: `data/results/alpha_v1_ath_regime_first_pass_20260505/filter_evaluation.csv`
- Machine summary: `data/results/alpha_v1_ath_regime_first_pass_20260505/summary.json`
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    annotated = _load_and_annotate_trades()
    summary, baseline = _summaries(annotated)
    filter_eval = _filter_evaluations(annotated)

    annotated.to_csv(RESULT_DIR / "annotated_trades.csv", index=False)
    summary.to_csv(RESULT_DIR / "bucket_summary.csv", index=False)
    baseline.to_csv(RESULT_DIR / "baseline_summary.csv", index=False)
    filter_eval.to_csv(RESULT_DIR / "filter_evaluation.csv", index=False)

    payload = {
        "source_trades": str(SOURCE_TRADES.relative_to(ROOT)),
        "report": str(REPORT_PATH.relative_to(ROOT)),
        "result_dir": str(RESULT_DIR.relative_to(ROOT)),
        "trade_rows": int(annotated[annotated["context"] == "signal"].shape[0]),
        "contexts": ["signal", "fill"],
        "features": ["ath_pct_bucket", "ath_atr_bucket", "room_to_ath_r_bucket", "ath_age_bucket"],
        "windows": list(WINDOWS.keys()),
        "filter_probe": "skip_pct_0p5_1_all",
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2))
    _write_report(annotated, summary, baseline, filter_eval)

    full_portfolio = baseline[
        (baseline["context"] == "signal") & (baseline["window"] == "full") & (baseline["leg"] == "portfolio")
    ].iloc[0]
    print("ALPHA_V1 ATH regime first pass complete")
    print(f"Trades: {int(full_portfolio['trades'])} | Net R: {full_portfolio['net_r']:.1f} | Avg R: {full_portfolio['avg_r']:.3f}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
