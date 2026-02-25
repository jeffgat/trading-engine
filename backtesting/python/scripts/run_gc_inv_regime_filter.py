#!/usr/bin/env python3
"""GC Inversion Longs v9 — VIX and DXY Regime Filter Analysis.

Downloads daily VIX and DXY data, then segments existing v9 trades by
macro regime using the PRIOR day's close (no look-ahead bias).

Tests:
  - VIX level buckets: <15, 15-20, 20-30, >30
  - DXY trend: above/below 20 SMA, 50 SMA
  - Combined filters
"""

import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
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


def build_config():
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=1.0,
        max_gap_points=25.0,
        qualifying_move_atr_pct=10.0,
    )
    return StrategyConfig(
        rr=3.5,
        tp1_ratio=0.2,
        risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0,
        qty_step=1.0,
        sessions=(session,),
        instrument=GC,
        strategy="inversion",
        direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS,
        excluded_dates=EXCLUDED,
    )


def download_macro_data():
    """Download VIX and DXY daily data using yfinance."""
    import yfinance as yf

    print("  Downloading VIX (^VIX)...")
    vix = yf.download("^VIX", start="2015-12-01", end="2026-03-01", progress=False)
    if vix.empty:
        raise RuntimeError("Failed to download VIX data")

    print("  Downloading DXY (DX-Y.NYB)...")
    dxy = yf.download("DX-Y.NYB", start="2015-12-01", end="2026-03-01", progress=False)
    if dxy.empty:
        raise RuntimeError("Failed to download DXY data")

    # Flatten multi-level columns if present
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)
    if isinstance(dxy.columns, pd.MultiIndex):
        dxy.columns = dxy.columns.get_level_values(0)

    # Save locally for caching
    vix_path = DATA_DIR / "VIX_daily.csv"
    dxy_path = DATA_DIR / "DXY_daily.csv"
    vix.to_csv(vix_path)
    dxy.to_csv(dxy_path)
    print(f"  VIX: {len(vix)} days ({vix.index[0].date()} to {vix.index[-1].date()})")
    print(f"  DXY: {len(dxy)} days ({dxy.index[0].date()} to {dxy.index[-1].date()})")

    return vix, dxy


def load_or_download_macro():
    """Load cached macro data or download fresh."""
    vix_path = DATA_DIR / "VIX_daily.csv"
    dxy_path = DATA_DIR / "DXY_daily.csv"

    if vix_path.exists() and dxy_path.exists():
        print("  Loading cached macro data...")
        vix = pd.read_csv(vix_path, index_col=0, parse_dates=True)
        dxy = pd.read_csv(dxy_path, index_col=0, parse_dates=True)
        # Check if data is recent enough
        if vix.index[-1] >= pd.Timestamp("2025-01-01") and dxy.index[-1] >= pd.Timestamp("2025-01-01"):
            print(f"  VIX: {len(vix)} days | DXY: {len(dxy)} days")
            return vix, dxy
        print("  Cached data too old, re-downloading...")

    return download_macro_data()


def build_regime_lookup(vix_df, dxy_df):
    """Build date → regime dict using prior day's close (no look-ahead).

    Returns dict[str, dict] with keys: vix_close, dxy_close, dxy_sma20, dxy_sma50
    """
    # VIX: use Close column
    vix_close = vix_df["Close"].dropna()

    # DXY: use Close column, compute SMAs
    dxy_close = dxy_df["Close"].dropna()
    dxy_sma20 = dxy_close.rolling(20).mean()
    dxy_sma50 = dxy_close.rolling(50).mean()

    # Shift by 1 day: use PRIOR day's values for the trade date
    # Trade on date D uses macro data from date D-1 (or latest available before D)
    lookup = {}

    # Build a combined series
    all_dates = sorted(set(vix_close.index.date) | set(dxy_close.index.date))

    last_vix = np.nan
    last_dxy = np.nan
    last_dxy_sma20 = np.nan
    last_dxy_sma50 = np.nan

    for d in all_dates:
        ts = pd.Timestamp(d)
        # Store the PRIOR day's values for the NEXT trading day
        date_str = str(d)

        if ts in vix_close.index:
            last_vix = float(vix_close.loc[ts])
        if ts in dxy_close.index:
            last_dxy = float(dxy_close.loc[ts])
        if ts in dxy_sma20.index and not np.isnan(dxy_sma20.loc[ts]):
            last_dxy_sma20 = float(dxy_sma20.loc[ts])
        if ts in dxy_sma50.index and not np.isnan(dxy_sma50.loc[ts]):
            last_dxy_sma50 = float(dxy_sma50.loc[ts])

        lookup[date_str] = {
            "vix": last_vix,
            "dxy": last_dxy,
            "dxy_sma20": last_dxy_sma20,
            "dxy_sma50": last_dxy_sma50,
        }

    # Shift: trade on date D should use lookup from the prior business day
    # We'll handle this by looking up D-1 (or latest before D)
    shifted = {}
    sorted_dates = sorted(lookup.keys())
    for i, d in enumerate(sorted_dates):
        if i > 0:
            shifted[d] = lookup[sorted_dates[i - 1]]
        else:
            shifted[d] = {"vix": np.nan, "dxy": np.nan, "dxy_sma20": np.nan, "dxy_sma50": np.nan}

    return shifted


def analyze_regime(label, trades_in, trades_out):
    """Print regime comparison."""
    m_in = compute_metrics(trades_in) if trades_in else None
    m_out = compute_metrics(trades_out) if trades_out else None

    print(f"\n  {label}")
    print(f"  {'─'*70}")
    print(f"  {'':>12s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Avg R':>7s} {'PF':>6s} {'Max DD':>7s}")

    if m_in and m_in["total_trades"] > 0:
        print(f"  {'IN filter':>12s} {m_in['total_trades']:>7d} {m_in['win_rate']:>5.1%} "
              f"{m_in['total_r']:>7.1f} {m_in['avg_r']:>7.3f} {m_in['profit_factor']:>6.2f} "
              f"{m_in['max_drawdown_r']:>7.1f}")
    else:
        print(f"  {'IN filter':>12s}       0")

    if m_out and m_out["total_trades"] > 0:
        print(f"  {'OUT filter':>12s} {m_out['total_trades']:>7d} {m_out['win_rate']:>5.1%} "
              f"{m_out['total_r']:>7.1f} {m_out['avg_r']:>7.3f} {m_out['profit_factor']:>6.2f} "
              f"{m_out['max_drawdown_r']:>7.1f}")
    else:
        print(f"  {'OUT filter':>12s}       0")

    return m_in, m_out


def main():
    print("=" * 70)
    print("  GC Inversion Longs v9 — VIX / DXY Regime Filter")
    print("=" * 70)

    # Load macro data
    print("\nMacro data:")
    vix_df, dxy_df = load_or_download_macro()
    regime = build_regime_lookup(vix_df, dxy_df)

    # Run v9 backtest
    print("\nLoading GC data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")

    config = build_config()
    print("Running v9 backtest...")
    trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    m_base = compute_metrics(trades)

    print(f"\n  Baseline: {m_base['total_trades']} trades, {m_base['total_r']:.1f}R, "
          f"{m_base['win_rate']:.1%} WR, {m_base['max_drawdown_r']:.1f}R DD")

    # Attach regime data to each trade
    missing = 0
    for t in filled:
        r = regime.get(t.date)
        if r is None or np.isnan(r.get("vix", np.nan)):
            missing += 1
    if missing:
        print(f"  ({missing} trades missing macro data — will be excluded from regime analysis)")

    # ══════════════════════════════════════════════════════════════════════
    # VIX ANALYSIS
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  VIX REGIME ANALYSIS (prior day close)")
    print("=" * 70)

    # VIX buckets
    vix_buckets = [
        ("VIX < 15", lambda r: r["vix"] < 15),
        ("VIX 15-20", lambda r: 15 <= r["vix"] < 20),
        ("VIX 20-25", lambda r: 20 <= r["vix"] < 25),
        ("VIX 25-30", lambda r: 25 <= r["vix"] < 30),
        ("VIX > 30", lambda r: r["vix"] >= 30),
    ]

    print(f"\n  {'Bucket':>12s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Avg R':>7s} {'PF':>6s} {'Max DD':>7s}")
    print(f"  {'─'*55}")

    for label, fn in vix_buckets:
        bucket_trades = []
        for t in trades:
            r = regime.get(t.date)
            if r is None or np.isnan(r.get("vix", np.nan)):
                continue
            if t.exit_type == EXIT_NO_FILL:
                continue
            if fn(r):
                bucket_trades.append(t)

        if bucket_trades:
            m = compute_metrics(bucket_trades)
            print(f"  {label:>12s} {m['total_trades']:>7d} {m['win_rate']:>5.1%} "
                  f"{m['total_r']:>7.1f} {m['avg_r']:>7.3f} {m['profit_factor']:>6.2f} "
                  f"{m['max_drawdown_r']:>7.1f}")
        else:
            print(f"  {label:>12s}       0")

    # VIX filter tests
    vix_filters = [
        ("VIX > 15", lambda r: r["vix"] > 15),
        ("VIX > 18", lambda r: r["vix"] > 18),
        ("VIX > 20", lambda r: r["vix"] > 20),
        ("VIX < 25", lambda r: r["vix"] < 25),
        ("VIX < 30", lambda r: r["vix"] < 30),
        ("VIX 15-30", lambda r: 15 <= r["vix"] < 30),
    ]

    print(f"\n  VIX Filter Tests (IN = trades passing filter):")
    for label, fn in vix_filters:
        in_trades = [t for t in trades
                     if regime.get(t.date) and not np.isnan(regime[t.date].get("vix", np.nan))
                     and fn(regime[t.date])]
        out_trades = [t for t in trades
                      if regime.get(t.date) and not np.isnan(regime[t.date].get("vix", np.nan))
                      and not fn(regime[t.date])]
        analyze_regime(label, in_trades, out_trades)

    # ══════════════════════════════════════════════════════════════════════
    # DXY ANALYSIS
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  DXY REGIME ANALYSIS (prior day close)")
    print("=" * 70)

    # DXY trend filters
    dxy_filters = [
        ("DXY < SMA20", lambda r: r["dxy"] < r["dxy_sma20"] if not np.isnan(r["dxy_sma20"]) else False),
        ("DXY > SMA20", lambda r: r["dxy"] > r["dxy_sma20"] if not np.isnan(r["dxy_sma20"]) else False),
        ("DXY < SMA50", lambda r: r["dxy"] < r["dxy_sma50"] if not np.isnan(r["dxy_sma50"]) else False),
        ("DXY > SMA50", lambda r: r["dxy"] > r["dxy_sma50"] if not np.isnan(r["dxy_sma50"]) else False),
    ]

    for label, fn in dxy_filters:
        in_trades = [t for t in trades
                     if regime.get(t.date) and not np.isnan(regime[t.date].get("dxy", np.nan))
                     and fn(regime[t.date])]
        out_trades = [t for t in trades
                      if regime.get(t.date) and not np.isnan(regime[t.date].get("dxy", np.nan))
                      and not fn(regime[t.date])]
        analyze_regime(label, in_trades, out_trades)

    # ══════════════════════════════════════════════════════════════════════
    # COMBINED FILTERS
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  COMBINED REGIME FILTERS")
    print("=" * 70)

    combined_filters = [
        ("VIX>20 + DXY<SMA20",
         lambda r: r["vix"] > 20 and r["dxy"] < r["dxy_sma20"] if not np.isnan(r.get("dxy_sma20", np.nan)) else False),
        ("VIX>20 + DXY<SMA50",
         lambda r: r["vix"] > 20 and r["dxy"] < r["dxy_sma50"] if not np.isnan(r.get("dxy_sma50", np.nan)) else False),
        ("VIX>15 + DXY<SMA20",
         lambda r: r["vix"] > 15 and r["dxy"] < r["dxy_sma20"] if not np.isnan(r.get("dxy_sma20", np.nan)) else False),
        ("VIX>15 + DXY<SMA50",
         lambda r: r["vix"] > 15 and r["dxy"] < r["dxy_sma50"] if not np.isnan(r.get("dxy_sma50", np.nan)) else False),
        ("VIX<25 + DXY<SMA20",
         lambda r: r["vix"] < 25 and r["dxy"] < r["dxy_sma20"] if not np.isnan(r.get("dxy_sma20", np.nan)) else False),
    ]

    for label, fn in combined_filters:
        in_trades = [t for t in trades
                     if regime.get(t.date) and not np.isnan(regime[t.date].get("vix", np.nan))
                     and not np.isnan(regime[t.date].get("dxy", np.nan))
                     and fn(regime[t.date])]
        out_trades = [t for t in trades
                      if regime.get(t.date) and not np.isnan(regime[t.date].get("vix", np.nan))
                      and not np.isnan(regime[t.date].get("dxy", np.nan))
                      and not fn(regime[t.date])]
        analyze_regime(label, in_trades, out_trades)

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  BASELINE COMPARISON")
    print("=" * 70)
    print(f"\n  v9 Baseline: {m_base['total_trades']} trades, {m_base['win_rate']:.1%} WR, "
          f"{m_base['total_r']:.1f}R, PF {m_base['profit_factor']:.2f}, DD {m_base['max_drawdown_r']:.1f}R")
    print(f"\n  Look for filters where IN has better avg R AND lower DD than baseline.")
    print(f"  But beware: cutting trades on 250 total is high overfitting risk.")
    print()


if __name__ == "__main__":
    main()
