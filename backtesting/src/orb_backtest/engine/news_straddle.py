"""News straddle backtest engine.

Simulates placing stop-buy above and stop-sell below price 1 second before
a scheduled news event (NFP/CPI at 08:30 ET), then tracking the outcome
over a configurable observation window.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from statistics import median
import hashlib

import pandas as pd

from ..data.loader import DATA_DIR, _load_ohlcv
from ..data.news_dates import NFP_SET, CPI_SET, NFP_DATES, CPI_DATES


@dataclass
class NewsStraddleConfig:
    buffer_points: float = 5.0
    target_points: float = 25.0
    event_types: tuple[str, ...] = ("NFP", "CPI")
    observation_window_seconds: int = 120
    instrument: str = "NQ"
    stop_loss_points: float | None = None  # fixed stop after fill, None = no stop


@dataclass
class NewsStraddleEvent:
    date: str
    event_type: str
    reference_price: float
    buffer_points: float
    target_points: float
    direction_filled: str | None  # "long", "short", or None
    fill_price: float
    seconds_to_fill: int
    mfe_points: float
    mae_points: float
    time_to_mfe_seconds: int
    target_hit: bool
    time_to_target_seconds: int | None
    whipsaw: bool
    final_points: float
    exit_type: str  # "target", "stop_loss", "eow" (end of window), "no_fill"


def _get_event_dates(event_types: tuple[str, ...]) -> list[tuple[str, str]]:
    """Return sorted list of (YYYYMMDD, event_type) tuples."""
    dates: list[tuple[str, str]] = []
    for et in event_types:
        if et.upper() == "NFP":
            dates.extend((d, "NFP") for d in NFP_DATES)
        elif et.upper() == "CPI":
            dates.extend((d, "CPI") for d in CPI_DATES)
    dates.sort(key=lambda x: x[0])
    return dates


def _load_1s_data(
    instrument: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load 1-second data for an instrument."""
    stem = DATA_DIR / f"{instrument}_1s"
    return _load_ohlcv(stem, start, end)


def simulate_single_event(
    df_1s: pd.DataFrame,
    date_str: str,
    event_type: str,
    config: NewsStraddleConfig,
) -> NewsStraddleEvent | None:
    """Simulate a news straddle for a single event."""
    year, month, day = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
    ref_time = datetime(year, month, day, 8, 29, 59)
    release_time = datetime(year, month, day, 8, 30, 0)

    if ref_time not in df_1s.index:
        return None

    reference_price = float(df_1s.loc[ref_time, "close"])
    stop_buy = reference_price + config.buffer_points
    stop_sell = reference_price - config.buffer_points

    window_end = release_time + timedelta(seconds=config.observation_window_seconds)
    window = df_1s.loc[release_time:window_end]

    if window.empty:
        return None

    # Phase 1: Find fill
    direction_filled = None
    fill_price = 0.0
    fill_idx = -1
    seconds_to_fill = 0
    whipsaw = False

    for i, (ts, bar) in enumerate(window.iterrows()):
        high = float(bar["high"])
        low = float(bar["low"])
        bar_open = float(bar["open"])

        long_triggered = high >= stop_buy
        short_triggered = low <= stop_sell

        if long_triggered and short_triggered:
            bar_close = float(bar["close"])
            if bar_close >= bar_open:
                direction_filled = "long"
                fill_price = stop_buy
            else:
                direction_filled = "short"
                fill_price = stop_sell
            whipsaw = True
            fill_idx = i
            seconds_to_fill = i
            break
        elif long_triggered:
            direction_filled = "long"
            fill_price = stop_buy
            fill_idx = i
            seconds_to_fill = i
            break
        elif short_triggered:
            direction_filled = "short"
            fill_price = stop_sell
            fill_idx = i
            seconds_to_fill = i
            break

    if direction_filled is None:
        return NewsStraddleEvent(
            date=f"{year}-{month:02d}-{day:02d}",
            event_type=event_type,
            reference_price=reference_price,
            buffer_points=config.buffer_points,
            target_points=config.target_points,
            direction_filled=None,
            fill_price=0.0,
            seconds_to_fill=0,
            mfe_points=0.0,
            mae_points=0.0,
            time_to_mfe_seconds=0,
            target_hit=False,
            time_to_target_seconds=None,
            whipsaw=False,
            final_points=0.0,
            exit_type="no_fill",
        )

    # Phase 2: Track post-fill excursions with stop loss + target exit
    #
    # Fill-bar assumption: the 1s news candle that fills our stop order
    # continues in that direction to its extreme (high for long, low for short).
    # If that extreme hits our target → immediate win.
    # If the candle wicks through our entry but closes on the wrong side → loss.
    # Otherwise, subsequent bars use normal target / stop-loss tracking.
    post_fill = window.iloc[fill_idx:]
    mfe = 0.0
    mae = 0.0
    time_to_mfe = 0
    target_hit = False
    time_to_target: int | None = None
    is_long = direction_filled == "long"
    exit_type = "eow"
    final_points = 0.0

    opposite_level = stop_sell if is_long else stop_buy
    sl = config.stop_loss_points

    for j, (ts, bar) in enumerate(post_fill.iterrows()):
        high = float(bar["high"])
        low = float(bar["low"])
        bar_close = float(bar["close"])

        if is_long:
            favorable = high - fill_price
            adverse = fill_price - low
        else:
            favorable = fill_price - low
            adverse = high - fill_price

        if favorable > mfe:
            mfe = favorable
            time_to_mfe = j

        mae = max(mae, adverse)

        if not whipsaw:
            if is_long and low <= opposite_level:
                whipsaw = True
            elif not is_long and high >= opposite_level:
                whipsaw = True

        # --- Fill bar (j == 0): special handling ---
        if j == 0:
            # Assume price reaches the candle extreme; check target first
            if favorable >= config.target_points:
                target_hit = True
                time_to_target = 0
                final_points = config.target_points
                exit_type = "target"
                break

            # Wick-and-reverse: filled but close is on wrong side of entry
            close_against = (is_long and bar_close < fill_price) or (
                not is_long and bar_close > fill_price
            )
            if close_against:
                if is_long:
                    final_points = bar_close - fill_price  # negative
                else:
                    final_points = fill_price - bar_close  # negative
                exit_type = "stop_loss"
                break

            # Fill bar didn't hit target or reverse — continue to next bars
            continue

        # --- Subsequent bars (j > 0) ---

        # Check if both SL and TP hit on the same bar
        sl_hit = sl is not None and adverse >= sl
        tp_hit = favorable >= config.target_points

        if sl_hit and tp_hit:
            # Ambiguous bar — 50/50 coin flip using deterministic hash
            seed = f"{date_str}_{j}_{config.buffer_points}_{config.target_points}"
            coin = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 2
            if coin == 0:
                final_points = config.target_points
                target_hit = True
                time_to_target = j
                exit_type = "target"
            else:
                final_points = -sl
                exit_type = "stop_loss"
            break

        # Stop loss exit
        if sl_hit:
            final_points = -sl
            exit_type = "stop_loss"
            break

        # Target exit
        if tp_hit:
            target_hit = True
            time_to_target = j
            final_points = config.target_points
            exit_type = "target"
            break

    # End of window -- compute final from last bar close
    if exit_type == "eow":
        last_bar = post_fill.iloc[-1]
        last_close = float(last_bar["close"])
        if is_long:
            final_points = last_close - fill_price
        else:
            final_points = fill_price - last_close

    return NewsStraddleEvent(
        date=f"{year}-{month:02d}-{day:02d}",
        event_type=event_type,
        reference_price=reference_price,
        buffer_points=config.buffer_points,
        target_points=config.target_points,
        direction_filled=direction_filled,
        fill_price=fill_price,
        seconds_to_fill=seconds_to_fill,
        mfe_points=round(mfe, 2),
        mae_points=round(mae, 2),
        time_to_mfe_seconds=time_to_mfe,
        target_hit=target_hit,
        time_to_target_seconds=time_to_target,
        whipsaw=whipsaw,
        final_points=round(final_points, 2),
        exit_type=exit_type,
    )


def _compute_summary(events: list[NewsStraddleEvent]) -> dict:
    """Compute aggregate stats from a list of events."""
    filled = [e for e in events if e.direction_filled is not None]
    total = len(events)
    n_filled = len(filled)

    if n_filled == 0:
        return {
            "total_events": total, "events_with_data": total,
            "fills": 0, "no_fills": total, "long_fills": 0, "short_fills": 0,
            "target_hit_count": 0, "target_hit_rate": 0.0,
            "whipsaw_count": 0, "whipsaw_rate": 0.0,
            "avg_mfe": 0.0, "avg_mae": 0.0, "median_mfe": 0.0, "median_mae": 0.0,
            "avg_final_points": 0.0, "pct_profitable": 0.0,
            "avg_seconds_to_fill": 0.0, "avg_time_to_mfe_seconds": 0.0,
            "stop_loss_count": 0, "stop_loss_rate": 0.0,
            "by_event_type": {},
        }

    long_fills = sum(1 for e in filled if e.direction_filled == "long")
    short_fills = sum(1 for e in filled if e.direction_filled == "short")
    target_hits = sum(1 for e in filled if e.target_hit)
    whipsaws = sum(1 for e in filled if e.whipsaw)
    stop_losses = sum(1 for e in filled if e.exit_type == "stop_loss")
    mfes = [e.mfe_points for e in filled]
    maes = [e.mae_points for e in filled]
    finals = [e.final_points for e in filled]
    profitable = sum(1 for e in filled if e.final_points > 0)

    by_type: dict[str, dict] = {}
    for et in set(e.event_type for e in filled):
        typed = [e for e in filled if e.event_type == et]
        typed_hits = sum(1 for e in typed if e.target_hit)
        typed_sl = sum(1 for e in typed if e.exit_type == "stop_loss")
        by_type[et] = {
            "fills": len(typed),
            "target_hit_count": typed_hits,
            "target_hit_rate": round(typed_hits / len(typed), 4) if typed else 0,
            "avg_mfe": round(sum(e.mfe_points for e in typed) / len(typed), 2),
            "avg_mae": round(sum(e.mae_points for e in typed) / len(typed), 2),
            "avg_final_points": round(sum(e.final_points for e in typed) / len(typed), 2),
            "whipsaw_count": sum(1 for e in typed if e.whipsaw),
            "stop_loss_count": typed_sl,
            "stop_loss_rate": round(typed_sl / len(typed), 4) if typed else 0,
        }

    return {
        "total_events": total, "events_with_data": total,
        "fills": n_filled, "no_fills": total - n_filled,
        "long_fills": long_fills, "short_fills": short_fills,
        "target_hit_count": target_hits,
        "target_hit_rate": round(target_hits / n_filled, 4),
        "whipsaw_count": whipsaws,
        "whipsaw_rate": round(whipsaws / n_filled, 4),
        "avg_mfe": round(sum(mfes) / n_filled, 2),
        "avg_mae": round(sum(maes) / n_filled, 2),
        "median_mfe": round(median(mfes), 2),
        "median_mae": round(median(maes), 2),
        "avg_final_points": round(sum(finals) / n_filled, 2),
        "pct_profitable": round(profitable / n_filled, 4),
        "avg_seconds_to_fill": round(sum(e.seconds_to_fill for e in filled) / n_filled, 2),
        "avg_time_to_mfe_seconds": round(
            sum(e.time_to_mfe_seconds for e in filled) / n_filled, 2
        ),
        "stop_loss_count": stop_losses,
        "stop_loss_rate": round(stop_losses / n_filled, 4),
        "by_event_type": by_type,
    }


def run_news_straddle(
    config: NewsStraddleConfig,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Run a news straddle backtest."""
    df_1s = _load_1s_data(config.instrument, start, end)
    event_dates = _get_event_dates(config.event_types)

    if start:
        start_yyyymmdd = start.replace("-", "")
        event_dates = [(d, et) for d, et in event_dates if d >= start_yyyymmdd]
    if end:
        end_yyyymmdd = end.replace("-", "")
        event_dates = [(d, et) for d, et in event_dates if d <= end_yyyymmdd]

    events: list[NewsStraddleEvent] = []
    skipped = 0
    for date_str, event_type in event_dates:
        result = simulate_single_event(df_1s, date_str, event_type, config)
        if result is not None:
            events.append(result)
        else:
            skipped += 1

    summary = _compute_summary(events)
    summary["total_events"] = len(event_dates)
    summary["events_with_data"] = len(events)
    summary["skipped_no_data"] = skipped

    return {
        "config": {
            "buffer_points": config.buffer_points,
            "target_points": config.target_points,
            "event_types": list(config.event_types),
            "observation_window_seconds": config.observation_window_seconds,
            "instrument": config.instrument,
            "stop_loss_points": config.stop_loss_points,
        },
        "summary": summary,
        "events": [asdict(e) for e in events],
    }


def run_news_straddle_sweep(
    buffer_range: list[float],
    target_range: list[float],
    event_types: tuple[str, ...] = ("NFP", "CPI"),
    observation_window_seconds: int = 120,
    instrument: str = "NQ",
    start: str | None = None,
    end: str | None = None,
    stop_loss_points: float | None = None,
) -> dict:
    """Sweep over buffer x target grid."""
    df_1s = _load_1s_data(instrument, start, end)
    event_dates = _get_event_dates(event_types)
    if start:
        start_yyyymmdd = start.replace("-", "")
        event_dates = [(d, et) for d, et in event_dates if d >= start_yyyymmdd]
    if end:
        end_yyyymmdd = end.replace("-", "")
        event_dates = [(d, et) for d, et in event_dates if d <= end_yyyymmdd]

    results: list[dict] = []

    for buffer_pts in buffer_range:
        for target_pts in target_range:
            config = NewsStraddleConfig(
                buffer_points=buffer_pts,
                target_points=target_pts,
                event_types=event_types,
                observation_window_seconds=observation_window_seconds,
                instrument=instrument,
                stop_loss_points=stop_loss_points,
            )

            events: list[NewsStraddleEvent] = []
            for date_str, event_type in event_dates:
                result = simulate_single_event(df_1s, date_str, event_type, config)
                if result is not None:
                    events.append(result)

            summary = _compute_summary(events)
            results.append({
                "buffer_points": buffer_pts,
                "target_points": target_pts,
                **summary,
            })

    return {
        "swept_params": {
            "buffer_points": buffer_range,
            "target_points": target_range,
        },
        "results": results,
        "total_combinations": len(results),
        "event_types": list(event_types),
        "observation_window_seconds": observation_window_seconds,
        "instrument": instrument,
    }
