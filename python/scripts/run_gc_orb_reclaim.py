#!/usr/bin/env python3
"""ORB Reclaim strategy for GC — longs only, magnifier ON.

Entry logic:
  1. Compute 5-min ORB (09:30-09:35)
  2. During entry window, wait for price to break below ORB low
  3. When a candle closes back above ORB low → enter LONG at close
  4. Stop = lowest low during the breakdown
  5. TP1/TP2/BE use same partial-exit logic as the main engine

One trade per session-day. Uses 1m bars for exit simulation (magnifier).
"""

import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.bar_mapping import build_5m_to_1m_map
from orb_backtest.engine.simulator import (
    TradeResult, _simulate_exit_magnifier,
    EXIT_NO_FILL, EXIT_SL, EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_EOD,
    EXIT_NAMES,
)
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.signals.daily_atr import compute_daily_atr

GC = get_instrument("GC")

# ── Config ───────────────────────────────────────────────────────────────────

RR = 3.5
TP1_RATIO = 0.2
ATR_LENGTH = 50
RISK_USD = 5000.0
STOP_ATR_PCT = 9.0       # Max stop as % of ATR (cap oversized stops)
MIN_STOP_PTS = 1.0       # Minimum stop distance in points

ORB_START = "09:30"
ORB_END = "09:35"
ENTRY_START = "09:35"
ENTRY_END = "15:00"
FLAT_START = "15:50"
FLAT_END = "16:00"

START_DATE = "2016-01-01"


def detect_reclaim_signals(df, df_1m, atr_series):
    """Detect ORB reclaim signals on 5m bars.

    Returns list of dicts with signal info for each reclaim found.
    """
    idx = df.index
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    open_ = df["open"].values

    # Build session-day groups
    dates = idx.date
    times = idx.time

    from datetime import time as dt_time
    orb_start_t = dt_time(int(ORB_START.split(":")[0]), int(ORB_START.split(":")[1]))
    orb_end_t = dt_time(int(ORB_END.split(":")[0]), int(ORB_END.split(":")[1]))
    entry_start_t = dt_time(int(ENTRY_START.split(":")[0]), int(ENTRY_START.split(":")[1]))
    entry_end_t = dt_time(int(ENTRY_END.split(":")[0]), int(ENTRY_END.split(":")[1]))
    flat_start_t = dt_time(int(FLAT_START.split(":")[0]), int(FLAT_START.split(":")[1]))

    # Build 5m→1m mapping
    map_5m_to_1m = build_5m_to_1m_map(df, df_1m)

    signals = []

    # Group bars by date
    unique_dates = sorted(set(dates))
    bar_by_date = defaultdict(list)
    for i, d in enumerate(dates):
        bar_by_date[d].append(i)

    for day in unique_dates:
        day_str = str(day)
        if day_str < START_DATE:
            continue

        bars = bar_by_date[day]
        if not bars:
            continue

        # Get ATR for this day
        atr_val = atr_series.get(day_str, None)
        if atr_val is None or atr_val <= 0:
            continue

        # Find ORB bars (09:30-09:35)
        orb_bars = [i for i in bars if orb_start_t <= times[i] < orb_end_t]
        if not orb_bars:
            continue

        orb_high = max(high[i] for i in orb_bars)
        orb_low = min(low[i] for i in orb_bars)

        if orb_high == orb_low:
            continue

        # Entry window bars
        entry_bars = [i for i in bars if entry_start_t <= times[i] < entry_end_t]
        if not entry_bars:
            continue

        # Find flat bar start
        flat_bars = [i for i in bars if times[i] >= flat_start_t]
        flat_bar_start = flat_bars[0] if flat_bars else bars[-1]

        # Scan for reclaim pattern: break below ORB low, then close above
        swept = False
        sweep_low = float("inf")

        for i in entry_bars:
            if low[i] < orb_low:
                swept = True
                sweep_low = min(sweep_low, low[i])

            if swept and close[i] > orb_low:
                # RECLAIM signal
                entry_price = close[i]
                stop_price = sweep_low

                # Use ATR-based stop instead of sweep low
                stop_dist = atr_val * STOP_ATR_PCT / 100.0
                if stop_dist < MIN_STOP_PTS:
                    break
                stop_price = entry_price - stop_dist

                risk_pts = entry_price - stop_price
                tp1_price = entry_price + risk_pts * RR * TP1_RATIO
                tp2_price = entry_price + risk_pts * RR
                be_price = entry_price

                # Find 1m bar index for the reclaim candle
                fill_bar_1m = -1
                if i in map_5m_to_1m:
                    # Use the last 1m bar of this 5m candle (entry at close)
                    start_1m, end_1m = map_5m_to_1m[i]
                    fill_bar_1m = end_1m

                # Find flat start and last bar in 1m
                flat_start_1m = -1
                last_bar_1m = -1
                if flat_bar_start in map_5m_to_1m:
                    flat_start_1m = map_5m_to_1m[flat_bar_start][0]
                if bars[-1] in map_5m_to_1m:
                    last_bar_1m = map_5m_to_1m[bars[-1]][1]

                signals.append({
                    "date": day_str,
                    "signal_bar": i,
                    "fill_bar": i,
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "tp1_price": tp1_price,
                    "tp2_price": tp2_price,
                    "be_price": be_price,
                    "risk_pts": risk_pts,
                    "orb_high": orb_high,
                    "orb_low": orb_low,
                    "sweep_low": sweep_low,
                    "flat_bar_start": flat_bar_start,
                    "last_bar": bars[-1],
                    "fill_bar_1m": fill_bar_1m,
                    "flat_start_1m": flat_start_1m,
                    "last_bar_1m": last_bar_1m,
                })
                break  # One trade per session-day

    return signals


def simulate_trades(signals, df, df_1m):
    """Simulate exit for each reclaim signal using 1m magnifier."""
    idx = df.index
    idx_1m = df_1m.index
    high_1m = df_1m["high"].values
    low_1m = df_1m["low"].values
    close_1m = df_1m["close"].values

    high_5m = df["high"].values
    low_5m = df["low"].values
    close_5m = df["close"].values

    results = []

    for sig in signals:
        entry_price = sig["entry_price"]
        stop_price = sig["stop_price"]
        tp1_price = sig["tp1_price"]
        tp2_price = sig["tp2_price"]
        be_price = sig["be_price"]
        risk_pts = sig["risk_pts"]

        # Compute qty
        qty = max(1.0, (RISK_USD / (risk_pts * GC.point_value)))
        qty = round(qty)  # round to nearest contract
        if qty < 1:
            qty = 1.0
        half_qty = qty / 2.0 if qty >= 2 else qty
        is_single = qty < 2

        # Try 1m magnifier simulation
        if sig["fill_bar_1m"] >= 0 and sig["flat_start_1m"] >= 0 and sig["last_bar_1m"] >= 0:
            exit_type, exit_bar_1m, pnl_pts = _simulate_exit_magnifier(
                high_1m, low_1m, close_1m,
                sig["fill_bar_1m"],
                sig["flat_start_1m"],
                sig["last_bar_1m"],
                1,  # direction = long
                entry_price, stop_price,
                tp1_price, tp2_price, be_price,
                is_single, qty, half_qty,
            )
            exit_bar_5m = sig["last_bar"]  # approximate
            fill_time = str(idx[sig["fill_bar"]])
            exit_time = str(idx_1m[exit_bar_1m]) if exit_bar_1m >= 0 else ""
        else:
            # Fallback to 5m simulation
            exit_type, exit_bar_5m, pnl_pts = _simulate_exit_5m(
                high_5m, low_5m, close_5m,
                sig["fill_bar"], sig["flat_bar_start"], sig["last_bar"],
                entry_price, stop_price, tp1_price, tp2_price, be_price,
                is_single, qty, half_qty,
            )
            fill_time = str(idx[sig["fill_bar"]])
            exit_time = str(idx[exit_bar_5m]) if exit_bar_5m >= 0 else ""

        pnl_usd = pnl_pts * GC.point_value * qty
        if exit_type != EXIT_NO_FILL:
            pnl_usd -= 2 * qty * GC.commission
        r_multiple = pnl_pts / risk_pts if risk_pts > 0 else 0.0

        results.append(TradeResult(
            date=sig["date"],
            session="NY",
            direction=1,
            signal_bar=sig["signal_bar"],
            fill_bar=sig["fill_bar"],
            entry_price=entry_price,
            stop_price=stop_price,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            exit_type=exit_type,
            exit_bar=exit_bar_5m,
            pnl_points=pnl_pts,
            pnl_usd=pnl_usd,
            r_multiple=r_multiple,
            qty=qty,
            half_qty=half_qty,
            gap_size=0.0,  # no FVG gap for reclaim
            risk_points=risk_pts,
            fill_time=fill_time,
            exit_time=exit_time,
        ))

    return results


def _simulate_exit_5m(high, low, close, fill_bar, flat_start, last_bar,
                      entry_price, stop_price, tp1_price, tp2_price, be_price,
                      is_single, qty, half_qty):
    """Fallback 5m exit simulation."""
    tp1_hit = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    for i in range(fill_bar + 1, last_bar + 1):
        is_flat = i >= flat_start
        sl_hit = low[i] <= current_stop
        tp1_trigger = high[i] >= tp1_price and not tp1_hit
        tp2_trigger = high[i] >= tp2_price

        if is_flat and not sl_hit:
            if tp1_hit:
                pnl_points += (close[i] - entry_price) * (remaining_qty / qty)
                return EXIT_TP1_EOD, i, pnl_points
            else:
                pnl_points = close[i] - entry_price
                return EXIT_EOD, i, pnl_points

        if sl_hit and not tp1_hit:
            pnl_points = current_stop - entry_price
            return EXIT_SL, i, pnl_points

        if is_single:
            if tp1_trigger:
                tp1_hit = True
                current_stop = be_price
            if sl_hit and tp1_hit:
                pnl_points = current_stop - entry_price
                return EXIT_TP1_BE, i, pnl_points
        else:
            if sl_hit and tp1_trigger:
                pnl_points = current_stop - entry_price
                return EXIT_SL, i, pnl_points
            if tp1_trigger:
                leg1 = (tp1_price - entry_price) * (half_qty / qty)
                pnl_points += leg1
                tp1_hit = True
                remaining_qty -= half_qty
                current_stop = be_price
            if tp1_hit:
                if sl_hit:
                    pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                    return EXIT_TP1_BE, i, pnl_points
                if tp2_trigger:
                    pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                    return EXIT_TP1_TP2, i, pnl_points

    pnl_points = close[last_bar] - entry_price
    return EXIT_EOD, last_bar, pnl_points


def build_daily_atr(df):
    """Build daily ATR lookup dict from per-bar ATR array."""
    atr_arr = compute_daily_atr(df, length=ATR_LENGTH)
    # Map date string to ATR value (take last non-NaN value per day)
    result = {}
    dates = df.index.date
    for i in range(len(atr_arr)):
        val = atr_arr[i]
        if not np.isnan(val):
            result[str(dates[i])] = val
    return result


def main():
    print("=" * 70)
    print("  GC NY ORB RECLAIM — Longs Only + Magnifier")
    print("=" * 70)
    print(f"  rr={RR}, tp1_ratio={TP1_RATIO}, atr_length={ATR_LENGTH}")
    print(f"  stop_atr_pct={STOP_ATR_PCT}%")
    print(f"  ORB: {ORB_START}-{ORB_END}, Entry: {ENTRY_START}-{ENTRY_END}")
    print()

    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars [{time.time()-t0:.1f}s]")
    print()

    # Build ATR
    atr = build_daily_atr(df)

    # Detect signals
    print("Detecting ORB reclaim signals...")
    t0 = time.time()
    signals = detect_reclaim_signals(df, df_1m, atr)
    print(f"  {len(signals)} reclaim signals found [{time.time()-t0:.1f}s]")
    print()

    if not signals:
        print("No signals found. Exiting.")
        return

    # Simulate
    print("Simulating trades on 1m bars...")
    t0 = time.time()
    trades = simulate_trades(signals, df, df_1m)
    print(f"  {len(trades)} trades simulated [{time.time()-t0:.1f}s]")
    print()

    # Metrics
    m = compute_metrics(trades)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    print("=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"  Signals:          {m['total_signals']}")
    print(f"  Filled trades:    {m['total_trades']}")
    print()
    print(f"  Win rate:         {m['win_rate']:.1%}")
    print(f"  Net R:            {m['total_r']:.1f}R")
    print(f"  Avg R:            {m['avg_r']:.3f}R")
    print(f"  Profit factor:    {m['profit_factor']:.2f}")
    print(f"  Sharpe ratio:     {m['sharpe_ratio']:.3f}")
    print(f"  Calmar ratio:     {m['calmar_ratio']:.2f}")
    print(f"  Max DD (R):       {m['max_drawdown_r']:.1f}R")
    print(f"  Max consec wins:  {m['max_consecutive_wins']}")
    print(f"  Max consec losses:{m['max_consecutive_losses']}")
    print()

    # Exit breakdown
    print("  Exit breakdown:")
    for exit_type, count in sorted(m["exit_breakdown"].items()):
        pct = count / m["total_signals"] * 100 if m["total_signals"] > 0 else 0
        print(f"    {exit_type:15s} {count:4d} ({pct:5.1f}%)")
    print()

    # R by year
    r_by_year = m.get("r_by_year", {})
    if r_by_year:
        print("  R by year:")
        for year, r in sorted(r_by_year.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {year}: {r:>8.1f}R{flag}")
    print("=" * 60)

    # Save
    session_cfg = SessionConfig(
        name="NY", orb_start=ORB_START, orb_end=ORB_END,
        entry_start=ENTRY_START, entry_end=ENTRY_END,
        flat_start=FLAT_START, flat_end=FLAT_END,
        stop_atr_pct=STOP_ATR_PCT, min_gap_atr_pct=0.0, max_gap_points=0.0,
    )
    config = StrategyConfig(
        rr=RR, tp1_ratio=TP1_RATIO, risk_usd=RISK_USD,
        atr_length=ATR_LENGTH,
        sessions=(session_cfg,), instrument=GC,
        strategy="reclaim", direction_filter="long",
        use_bar_magnifier=True,
        name="GC NY ORB Reclaim Longs v1",
        notes="ORB Reclaim: price breaks below 5-min ORB low, then closes back above. Entry at close, stop at sweep low. Magnifier ON.",
    )
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"\nResults saved: {result_id}")


if __name__ == "__main__":
    main()
