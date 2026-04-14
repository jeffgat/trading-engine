from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class LRLRResult:
    present: bool
    level_count: int = 0
    nearest_level_price: float = 0.0
    farthest_level_price: float = 0.0
    span_bars: int = 0
    price_span_atr: float = 0.0
    slope_atr_per_bar: float = 0.0
    fit_error_atr: float = 0.0
    tp1_path_present: bool = False
    nearest_tp1_gap_atr: float = 0.0


def _line_stats(cluster: list[tuple[int, float]], daily_atr: float) -> tuple[float, float]:
    x = np.array([bar for bar, _ in cluster], dtype=float)
    y = np.array([price for _, price in cluster], dtype=float)
    x_centered = x - x.mean()
    denom = float(np.dot(x_centered, x_centered))
    if denom <= 0.0:
        return 0.0, 0.0
    slope = float(np.dot(x_centered, y - y.mean()) / denom)
    fitted = y.mean() + slope * x_centered
    rmse = float(np.sqrt(np.mean((y - fitted) ** 2)))
    return slope / daily_atr, rmse / daily_atr


def _lrlr_bar_budget(minutes: int, bar_minutes: float) -> int:
    return max(1, int(math.ceil(float(minutes) / max(bar_minutes, 1e-9))))


def detect_lrlr_cluster(
    *,
    high: np.ndarray,
    low: np.ndarray,
    pivot_high_confirm_idx: np.ndarray,
    pivot_high_idx: np.ndarray,
    pivot_high_price: np.ndarray,
    pivot_low_confirm_idx: np.ndarray,
    pivot_low_idx: np.ndarray,
    pivot_low_price: np.ndarray,
    direction: int,
    entry_price: float,
    left_end_bar: int,
    daily_atr: float,
    bar_minutes: float,
    min_levels: int,
    lookback_minutes: int,
    max_pivot_gap_minutes: int,
    max_cluster_span_minutes: int,
    max_price_span_atr: float,
    monotonic_tolerance_atr: float,
    line_tolerance_atr: float,
    tp1_price: float | None = None,
    tp1_buffer_atr: float = 0.0,
) -> LRLRResult:
    """Detect an LRLR-style chain of unswept pivots immediately left of an LSI setup.

    For longs we require a descending chain of unswept swing highs above entry.
    For shorts we require an ascending chain of unswept swing lows below entry.
    """
    if (not np.isfinite(daily_atr)) or daily_atr <= 0.0 or left_end_bar <= 0 or min_levels < 1:
        return LRLRResult(False)

    if direction == 1:
        confirm_idx = pivot_high_confirm_idx
        pivot_idx = pivot_high_idx
        pivot_price = pivot_high_price
        path_prices = high
    else:
        confirm_idx = pivot_low_confirm_idx
        pivot_idx = pivot_low_idx
        pivot_price = pivot_low_price
        path_prices = low

    if len(pivot_idx) == 0:
        return LRLRResult(False)

    lookback_bars = _lrlr_bar_budget(lookback_minutes, bar_minutes)
    max_gap_bars = _lrlr_bar_budget(max_pivot_gap_minutes, bar_minutes)
    max_cluster_span_bars = _lrlr_bar_budget(max_cluster_span_minutes, bar_minutes)
    max_price_span = max_price_span_atr * daily_atr
    monotonic_tolerance = monotonic_tolerance_atr * daily_atr

    window_start = max(0, left_end_bar - lookback_bars + 1)
    hi = int(np.searchsorted(confirm_idx, left_end_bar, side="right"))
    lo = int(np.searchsorted(pivot_idx[:hi], window_start, side="left"))

    candidates: list[tuple[int, float]] = []
    for j in range(lo, hi):
        bar = int(pivot_idx[j])
        price = float(pivot_price[j])
        if bar >= left_end_bar or not np.isfinite(price):
            continue
        if direction == 1:
            if price <= entry_price:
                continue
            if np.max(path_prices[bar + 1:left_end_bar + 1]) > price:
                continue
        else:
            if price >= entry_price:
                continue
            if np.min(path_prices[bar + 1:left_end_bar + 1]) < price:
                continue
        candidates.append((bar, price))

    if len(candidates) < min_levels:
        return LRLRResult(False)

    best: LRLRResult | None = None
    for seed in range(len(candidates) - 1, -1, -1):
        cluster = [candidates[seed]]
        cluster_min = candidates[seed][1]
        cluster_max = candidates[seed][1]
        latest_bar = candidates[seed][0]

        for j in range(seed - 1, -1, -1):
            bar, price = candidates[j]
            if cluster[0][0] - bar > max_gap_bars:
                break
            if latest_bar - bar > max_cluster_span_bars:
                break
            if direction == 1 and price < (cluster[0][1] - monotonic_tolerance):
                break
            if direction == -1 and price > (cluster[0][1] + monotonic_tolerance):
                break

            next_min = min(cluster_min, price)
            next_max = max(cluster_max, price)
            if (next_max - next_min) > max_price_span:
                break

            cluster.insert(0, (bar, price))
            cluster_min = next_min
            cluster_max = next_max

        if len(cluster) < min_levels:
            continue

        if len(cluster) == 1:
            slope_atr_per_bar = 0.0
            fit_error_atr = 0.0
        else:
            slope_atr_per_bar, fit_error_atr = _line_stats(cluster, daily_atr)
            if direction == 1 and slope_atr_per_bar >= 0.0:
                continue
            if direction == -1 and slope_atr_per_bar <= 0.0:
                continue
            if fit_error_atr > line_tolerance_atr:
                continue

        span_bars = cluster[-1][0] - cluster[0][0]
        result = LRLRResult(
            present=True,
            level_count=len(cluster),
            nearest_level_price=float(cluster[-1][1]),
            farthest_level_price=float(cluster[0][1]),
            span_bars=int(span_bars),
            price_span_atr=float((cluster_max - cluster_min) / daily_atr),
            slope_atr_per_bar=float(slope_atr_per_bar),
            fit_error_atr=float(fit_error_atr),
        )
        if tp1_price is not None and np.isfinite(tp1_price):
            if direction == 1:
                nearest_tp1_gap_atr = max(0.0, (result.nearest_level_price - float(tp1_price)) / daily_atr)
            else:
                nearest_tp1_gap_atr = max(0.0, (float(tp1_price) - result.nearest_level_price) / daily_atr)
            result = LRLRResult(
                present=result.present,
                level_count=result.level_count,
                nearest_level_price=result.nearest_level_price,
                farthest_level_price=result.farthest_level_price,
                span_bars=result.span_bars,
                price_span_atr=result.price_span_atr,
                slope_atr_per_bar=result.slope_atr_per_bar,
                fit_error_atr=result.fit_error_atr,
                tp1_path_present=nearest_tp1_gap_atr <= tp1_buffer_atr,
                nearest_tp1_gap_atr=float(nearest_tp1_gap_atr),
            )
        if best is None:
            best = result
            continue
        if result.level_count > best.level_count:
            best = result
            continue
        if result.level_count == best.level_count and result.fit_error_atr < best.fit_error_atr:
            best = result
            continue
        if (
            result.level_count == best.level_count
            and math.isclose(result.fit_error_atr, best.fit_error_atr)
            and abs(result.nearest_level_price - entry_price) < abs(best.nearest_level_price - entry_price)
        ):
            best = result

    return best if best is not None else LRLRResult(False)
