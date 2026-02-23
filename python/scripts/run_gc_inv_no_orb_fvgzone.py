#!/usr/bin/env python3
"""No-ORB GC — prior FVG zone sweep filter.

Additional gate: the session's qualifying sweep (the low) must dip into or
through a prior bullish FVG zone from the last N trading days. This means
price specifically targeted a known order flow zone before reversing — a
higher-quality liquidity grab than a random ATR sweep.

Prior bullish FVG zone: gap between high[2] and low[0] from a prior 5m bar.
"Swept into zone" = session_low <= prior_fvg_top (entered the gap from above).

Tests N = 3, 5, 10, 20 lookback days to see what window gives the best signal.

Fixed: QM=100%, stop=12%, rr=5.0, BE=0, tp1=0.2, entry→16:45, longs.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED  = ("20241218",)


def make_config():
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="16:45",
        flat_start="16:45", flat_end="16:50",
        stop_atr_pct=12.0, min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=5.0, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )


def build_prior_bullish_fvgs(df: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    """
    Detect all bullish FVGs in 5m data and return a lookup:
      date_str -> list of (fvg_bottom, fvg_top) zones formed ON that date.

    Bullish FVG: high[2] < low[0] AND high[2] < high[1] AND low[2] < low[0]
    Zone: bottom = high[2], top = low[0]
    """
    high = df["high"].values
    low  = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values

    high_2 = np.roll(high, 2)
    high_1 = np.roll(high, 1)
    low_2  = np.roll(low, 2)

    # Bullish FVG pattern (no ORB filter)
    bull_fvg = (
        (high_2 < low) &
        (high_2 < high_1) &
        (low_2  < low)
    )
    bull_fvg[:2] = False

    fvg_by_date: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for i in np.where(bull_fvg)[0]:
        d = dates[i]
        bottom = float(high_2[i])   # top of bar[2]
        top    = float(low[i])      # low of bar[0] = top of gap
        if bottom < top:            # valid gap
            fvg_by_date[d].append((bottom, top))

    return dict(fvg_by_date)


def build_session_lows(df: pd.DataFrame) -> dict[str, float]:
    """Session low (09:30-16:45) per trading date."""
    mask = (df.index.time >= pd.Timestamp("09:30").time()) & \
           (df.index.time <= pd.Timestamp("16:45").time())
    session = df[mask].copy()
    session["date_str"] = session.index.strftime("%Y-%m-%d")
    return session.groupby("date_str")["low"].min().to_dict()


def filter_by_prior_fvg(
    filled: list,
    fvg_by_date: dict,
    session_lows: dict,
    lookback_days: int,
) -> tuple[list, list]:
    """
    Keep trades where session_low <= top of ANY bullish FVG from the
    prior `lookback_days` trading days (sweep entered the FVG zone).
    """
    sorted_dates = sorted(fvg_by_date.keys())
    # Build date → index mapping for fast lookback
    date_to_idx = {d: i for i, d in enumerate(sorted_dates)}

    kept, excluded = [], []
    for t in filled:
        trade_date = t.date  # "YYYY-MM-DD"
        sess_low   = session_lows.get(trade_date, float("inf"))

        # Collect FVG zones from prior N trading days
        if trade_date not in date_to_idx:
            # No FVG data for this date's lookback window — skip
            excluded.append(t)
            continue

        idx = date_to_idx.get(trade_date, -1)
        prior_zones = []
        for past_d in sorted_dates[max(0, idx - lookback_days): idx]:
            prior_zones.extend(fvg_by_date.get(past_d, []))

        if not prior_zones:
            excluded.append(t)
            continue

        # Check if session low swept into ANY prior bullish FVG zone
        swept_fvg = any(sess_low <= fvg_top for (_, fvg_top) in prior_zones)
        if swept_fvg:
            kept.append(t)
        else:
            excluded.append(t)

    return kept, excluded


def print_stats(label: str, filled: list) -> dict:
    if len(filled) < 5:
        print(f"  {label}: only {len(filled)} trades — insufficient")
        return {}
    m = compute_metrics(filled)
    yearly = defaultdict(list)
    for t in filled:
        yearly[t.date[:4]].append(t.r_multiple)
    monthly = defaultdict(list)
    for t in filled:
        monthly[t.date[:7]].append(t.r_multiple)
    wm = min((sum(v) for v in monthly.values()), default=0)
    marker = " ***" if m["max_drawdown_r"] >= -10.0 else ""
    print(f"  {label:<30} | {m['total_trades']:>4} trades | "
          f"WR {m['win_rate']:>5.1%} | {m['total_r']:>7.1f}R | "
          f"DD {m['max_drawdown_r']:>6.1f}R | "
          f"Sharpe {m['sharpe_ratio']:>6.3f} | "
          f"WM {wm:>5.1f}R | MCL {m['max_consecutive_losses']}{marker}")
    return m


def main():
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    print("Computing prior FVG zones and session lows...")
    fvg_by_date  = build_prior_bullish_fvgs(df)
    session_lows = build_session_lows(df)
    total_fvgs   = sum(len(v) for v in fvg_by_date.values())
    print(f"  {total_fvgs:,} bullish FVGs across {len(fvg_by_date)} dates\n")

    t0 = time.time()
    cfg    = make_config()
    trades = run_backtest_no_orb(df, cfg, start_date="2016-01-01", df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    print(f"Base no-ORB backtest: {len(filled)} filled trades  ({time.time()-t0:.0f}s)\n")

    print("=" * 105)
    print("NO-ORB GC — PRIOR FVG ZONE SWEEP FILTER (QM=100%, stop=12%, rr=5.0, BE=0, →16:45, longs)")
    print("=" * 105)
    print(f"  {'Filter':<30} | {'Trades':>4}        | {'WR':>5}   | {'Net R':>7}  | "
          f"{'Max DD':>6}   | {'Sharpe':>6}   | {'WM':>5}   | MCL")
    print("-" * 105)

    # Baseline
    print_stats("BASE (no FVG filter)", filled)

    # Swept into prior FVG — vary lookback
    for lookback in [3, 5, 10, 20]:
        kept, excl = filter_by_prior_fvg(filled, fvg_by_date, session_lows, lookback)
        print_stats(f"Prior FVG swept (N={lookback:>2} days)", kept)

    print()

    # Show excluded group for best lookback (5 days)
    kept5, excl5 = filter_by_prior_fvg(filled, fvg_by_date, session_lows, 5)
    print(f"\nN=5 detail:")
    print_stats("  KEPT (swept into prior FVG)", kept5)
    print_stats("  EXCLUDED (no prior FVG swept)", excl5)

    print(f"\nYearly breakdown — N=5 kept ({len(kept5)} trades):")
    if kept5:
        m5 = compute_metrics(kept5)
        yearly5 = defaultdict(list)
        for t in kept5:
            yearly5[t.date[:4]].append(t.r_multiple)
        for yr in sorted(yearly5):
            print(f"  {yr}: {sum(yearly5[yr]):+.1f}R  ({len(yearly5[yr])} trades)")

    print(f"\nv9 baseline: 250 trades, 74.7R, -5.2R DD, Sharpe 3.80")


if __name__ == "__main__":
    main()
