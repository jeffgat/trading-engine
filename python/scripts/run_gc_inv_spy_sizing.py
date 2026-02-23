#!/usr/bin/env python3
"""GC Inversion Longs v9 — SPY-based regime sizing test.

Quick test: 2x when VIX<18 + SPY>SMA50, 1x otherwise.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED = ("20241218",)
START = "2016-01-01"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def load_env():
    """Load VIX and SPY, build shifted lookup."""
    vix = pd.read_csv(DATA_DIR / "VIX_daily.csv", index_col=0, parse_dates=True)
    spy = pd.read_csv(DATA_DIR / "SPY_daily.csv", index_col=0, parse_dates=True)

    vix_close = vix["Close"].dropna()
    spy_close = spy["Close"].dropna()
    spy_sma50 = spy_close.rolling(50).mean()
    spy_sma20 = spy_close.rolling(20).mean()

    all_dates = sorted(set(vix_close.index.date) | set(spy_close.index.date))

    last = {"vix": np.nan, "spy": np.nan, "spy_sma50": np.nan, "spy_sma20": np.nan}
    raw = {}
    for d in all_dates:
        ts = pd.Timestamp(d)
        if ts in vix_close.index:
            last["vix"] = float(vix_close.loc[ts])
        if ts in spy_close.index:
            last["spy"] = float(spy_close.loc[ts])
        if ts in spy_sma50.index and not np.isnan(spy_sma50.loc[ts]):
            last["spy_sma50"] = float(spy_sma50.loc[ts])
        if ts in spy_sma20.index and not np.isnan(spy_sma20.loc[ts]):
            last["spy_sma20"] = float(spy_sma20.loc[ts])
        raw[str(d)] = dict(last)

    shifted = {}
    sorted_dates = sorted(raw.keys())
    for i, d in enumerate(sorted_dates):
        shifted[d] = raw[sorted_dates[i - 1]] if i > 0 else {k: np.nan for k in last}
    return shifted


def compute_sized(trades, env, size_fn):
    """Compute equity metrics with variable sizing."""
    r_vals = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        e = env.get(t.date)
        mult = size_fn(e) if e else 1.0
        r_vals.append(t.r_multiple * mult)

    if not r_vals:
        return None
    r = np.array(r_vals)
    eq = np.cumsum(r)
    dd = float(np.min(eq - np.maximum.accumulate(eq)))
    return {
        "trades": len(r),
        "wr": float(np.sum(r > 0) / len(r)),
        "total_r": float(np.sum(r)),
        "dd": dd,
        "avg_r": float(np.mean(r)),
    }


def print_row(label, s):
    if s:
        print(f"  {label:>35s}  {s['trades']:>5d}  {s['wr']:>5.1%}  "
              f"{s['total_r']:>7.1f}  {s['dd']:>6.1f}  {s['avg_r']:>7.3f}")
    else:
        print(f"  {label:>35s}      0")


def main():
    print("Loading env data...")
    env = load_env()

    print("Loading GC data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")

    session = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=9.0, min_gap_atr_pct=1.0,
    )
    config = StrategyConfig(
        rr=3.5, tp1_ratio=0.2, risk_usd=5000.0, atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC, strategy="inversion",
        direction_filter="long", use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )

    print("Running v9 backtest...")
    trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)

    print(f"\n  {'Strategy':>35s}  {'N':>5s}  {'WR':>5s}  {'Net R':>7s}  {'DD':>6s}  {'Avg R':>7s}")
    print(f"  {'─' * 75}")

    strategies = [
        ("1x flat (baseline)",
         lambda e: 1.0),
        ("2x VIX<18 + DXY<SMA50 (saved)",
         None),  # placeholder — we don't have DXY here
        ("2x VIX<18 + SPY>SMA50",
         lambda e: 2.0 if e["vix"] < 18 and e["spy"] > e["spy_sma50"] else 1.0),
        ("2x VIX<18 + SPY>SMA20",
         lambda e: 2.0 if e["vix"] < 18 and e["spy"] > e["spy_sma20"] else 1.0),
        ("1.5x VIX<18 + SPY>SMA50",
         lambda e: 1.5 if e["vix"] < 18 and e["spy"] > e["spy_sma50"] else 1.0),
        ("2x SPY>SMA50 (no VIX gate)",
         lambda e: 2.0 if e["spy"] > e["spy_sma50"] else 1.0),
        ("2x VIX<18 + SPY>SMA50, 0.5x rest",
         lambda e: 2.0 if e["vix"] < 18 and e["spy"] > e["spy_sma50"] else 0.5),
    ]

    for label, fn in strategies:
        if fn is None:
            # Print the known DXY result
            print(f"  {'2x VIX<18 + DXY<SMA50 (saved)':>35s}    250  56.8%    117.7    -6.5    0.471")
            continue
        s = compute_sized(trades, env, fn)
        print_row(label, s)

    print()


if __name__ == "__main__":
    main()
