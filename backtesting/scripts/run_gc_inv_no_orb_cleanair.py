#!/usr/bin/env python3
"""No-ORB GC — "clean air" sweep filter (inverted FVG zone gate).

Keep only trades where the session's qualifying sweep did NOT dip into
any prior bullish FVG zone — the sweep happens in clean air, no known
order zones to absorb it. Tests lookback N = 1, 2, 3, 5, 10, 20 days.

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


def build_bullish_fvgs(df: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    """Bullish FVGs per date: zone = (high[2], low[0])."""
    high  = df["high"].values
    low   = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values

    high_2 = np.roll(high, 2)
    high_1 = np.roll(high, 1)
    low_2  = np.roll(low, 2)

    bull = (high_2 < low) & (high_2 < high_1) & (low_2 < low)
    bull[:2] = False

    fvg_by_date: dict[str, list] = defaultdict(list)
    for i in np.where(bull)[0]:
        bottom, top = float(high_2[i]), float(low[i])
        if bottom < top:
            fvg_by_date[dates[i]].append((bottom, top))
    return dict(fvg_by_date)


def build_session_lows(df: pd.DataFrame) -> dict[str, float]:
    mask = (df.index.time >= pd.Timestamp("09:30").time()) & \
           (df.index.time <= pd.Timestamp("16:45").time())
    s = df[mask].copy()
    s["ds"] = s.index.strftime("%Y-%m-%d")
    return s.groupby("ds")["low"].min().to_dict()


def clean_air_filter(filled, fvg_by_date, session_lows, lookback):
    """Keep trades where session_low is ABOVE all prior FVG zones (clean air)."""
    sorted_dates = sorted(fvg_by_date.keys())
    date_to_idx  = {d: i for i, d in enumerate(sorted_dates)}

    kept = []
    for t in filled:
        sess_low = session_lows.get(t.date, float("inf"))
        idx = date_to_idx.get(t.date, -1)
        if idx < 0:
            continue

        prior_zones = []
        for past_d in sorted_dates[max(0, idx - lookback): idx]:
            prior_zones.extend(fvg_by_date.get(past_d, []))

        # "Clean air": no prior FVG zone contains or is above the session low
        # i.e., session_low > every prior fvg_top (sweep stayed above all zones)
        if not prior_zones or all(sess_low > fvg_top for (_, fvg_top) in prior_zones):
            kept.append(t)

    return kept


def stats(trades):
    if len(trades) < 5:
        return None
    m = compute_metrics(trades)
    monthly = defaultdict(list)
    yearly  = defaultdict(list)
    for t in trades:
        monthly[t.date[:7]].append(t.r_multiple)
        yearly[t.date[:4]].append(t.r_multiple)
    wm = min((sum(v) for v in monthly.values()), default=0)
    return {**m,
            "worst_month": round(wm, 1),
            "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
            "trades_per_year": len(trades) / len(yearly)}


def main():
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    fvg_by_date  = build_bullish_fvgs(df)
    session_lows = build_session_lows(df)

    t0     = time.time()
    trades = run_backtest_no_orb(df, make_config(), start_date="2016-01-01", df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    print(f"Base: {len(filled)} filled trades  ({time.time()-t0:.0f}s)\n")

    print("=" * 110)
    print("NO-ORB GC — CLEAN AIR SWEEP (no prior FVG zone), vary lookback N")
    print("=" * 110)
    print(f"  {'N':>4} | {'Trades':>6} | {'T/yr':>5} | {'WR':>6} | {'Net R':>7} | "
          f"{'Max DD':>7} | {'R/DD':>5} | {'Sharpe':>7} | {'PF':>5} | {'WM':>6} | {'MCL':>4}")
    print("-" * 110)

    results = {}
    for n in [1, 2, 3, 5, 10, 20]:
        kept = clean_air_filter(filled, fvg_by_date, session_lows, n)
        m    = stats(kept)
        if m is None:
            print(f"  N={n:>2}: insufficient trades")
            continue
        results[n] = (kept, m)
        dd = round(m["max_drawdown_r"], 1)
        nr = round(m["total_r"], 1)
        rdd = round(nr / abs(dd), 1) if dd < 0 else 999
        marker = " ***" if dd >= -10.0 else ""
        print(f"  N={n:>2} | {len(kept):>6} | {m['trades_per_year']:>5.1f} | "
              f"{m['win_rate']:>5.1%} | {nr:>7.1f} | {dd:>7.1f} | {rdd:>5.1f} | "
              f"{m['sharpe_ratio']:>7.3f} | {m['profit_factor']:>5.2f} | "
              f"{m['worst_month']:>6.1f} | {m['max_consecutive_losses']:>4}{marker}")

    # Yearly breakdown for each N
    print(f"\n{'='*90}")
    print("YEARLY BREAKDOWN PER LOOKBACK")
    print(f"{'='*90}")
    years = sorted({t.date[:4] for t in filled})
    header = f"{'Year':<6}" + "".join(f"  N={n:>2}" for n in results)
    print(header)
    print("-" * len(header))
    for yr in years:
        row = f"{yr:<6}"
        for n, (kept, m) in results.items():
            val = m["yearly"].get(yr, 0)
            cnt = sum(1 for t in kept if t.date[:4] == yr)
            row += f"  {val:>+5.1f}({cnt:>2})"
        print(row)

    print(f"\nv9 baseline: 250 trades, ~25/yr, 74.7R, -5.2R DD, Sharpe 3.80")


if __name__ == "__main__":
    main()
