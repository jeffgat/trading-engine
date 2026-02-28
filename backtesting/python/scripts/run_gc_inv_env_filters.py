#!/usr/bin/env python3
"""GC Inversion Longs v9 — Extended Environmental Filters.

Tests 4 additional macro/environmental filters:
  1. GVZ (Gold Volatility Index) — gold-specific implied vol
  2. TNX (US 10Y Yield) — level and trend
  3. SPY trend — risk-on vs risk-off
  4. Month-of-year seasonality
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


def download_env_data():
    """Download GVZ, TNX, SPY daily data via yfinance."""
    import yfinance as yf

    tickers = {
        "GVZ": "^GVZ",
        "TNX": "^TNX",
        "SPY": "SPY",
    }

    frames = {}
    for name, ticker in tickers.items():
        path = DATA_DIR / f"{name}_daily.csv"
        if path.exists():
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            if df.index[-1] >= pd.Timestamp("2025-01-01"):
                print(f"  {name}: cached ({len(df)} days)")
                frames[name] = df
                continue

        print(f"  Downloading {name} ({ticker})...")
        df = yf.download(ticker, start="2015-12-01", end="2026-03-01", progress=False)
        if df.empty:
            print(f"  WARNING: Failed to download {name}")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.to_csv(path)
        print(f"  {name}: {len(df)} days ({df.index[0].date()} to {df.index[-1].date()})")
        frames[name] = df

    return frames


def build_env_lookup(frames):
    """Build date → env dict using prior day's close (no look-ahead).

    Returns dict[str, dict] with keys: gvz, tnx, tnx_sma20, tnx_sma50,
    spy, spy_sma20, spy_sma50
    """
    series = {}

    if "GVZ" in frames:
        series["gvz"] = frames["GVZ"]["Close"].dropna()

    if "TNX" in frames:
        tnx = frames["TNX"]["Close"].dropna()
        series["tnx"] = tnx
        series["tnx_sma20"] = tnx.rolling(20).mean()
        series["tnx_sma50"] = tnx.rolling(50).mean()

    if "SPY" in frames:
        spy = frames["SPY"]["Close"].dropna()
        series["spy"] = spy
        series["spy_sma20"] = spy.rolling(20).mean()
        series["spy_sma50"] = spy.rolling(50).mean()

    # Collect all dates
    all_dates = set()
    for s in series.values():
        all_dates |= set(s.index.date)
    all_dates = sorted(all_dates)

    # Forward-fill lookup
    lookup = {}
    last = {k: np.nan for k in series}

    for d in all_dates:
        ts = pd.Timestamp(d)
        for k, s in series.items():
            if ts in s.index:
                val = s.loc[ts]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                val = float(val)
                if not np.isnan(val):
                    last[k] = val
        lookup[str(d)] = dict(last)

    # Shift by 1 day: trade on D uses env from D-1
    shifted = {}
    sorted_dates = sorted(lookup.keys())
    for i, d in enumerate(sorted_dates):
        if i > 0:
            shifted[d] = lookup[sorted_dates[i - 1]]
        else:
            shifted[d] = {k: np.nan for k in series}

    return shifted


def print_row(label, m, indent=4):
    pad = " " * indent
    if m and m["total_trades"] > 0:
        print(f"{pad}{label:>30s}  {m['total_trades']:>5d}  {m['win_rate']:>5.1%}  "
              f"{m['total_r']:>7.1f}  {m['avg_r']:>7.3f}  {m['profit_factor']:>5.2f}  "
              f"{m['max_drawdown_r']:>6.1f}")
    else:
        print(f"{pad}{label:>30s}      0")


def analyze_filter(label, trades, env_lookup, filter_fn):
    """Split trades by filter, print comparison."""
    in_trades = []
    out_trades = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        e = env_lookup.get(t.date)
        if e is None:
            continue
        try:
            if filter_fn(e):
                in_trades.append(t)
            else:
                out_trades.append(t)
        except (TypeError, ValueError):
            continue

    m_in = compute_metrics(in_trades) if in_trades else None
    m_out = compute_metrics(out_trades) if out_trades else None

    print(f"\n    {label}")
    print(f"    {'─' * 72}")
    print(f"    {'':>30s}  {'N':>5s}  {'WR':>5s}  {'Net R':>7s}  {'Avg R':>7s}  {'PF':>5s}  {'DD':>6s}")
    print_row("IN filter", m_in)
    print_row("OUT filter", m_out)

    return m_in, m_out


def main():
    print("=" * 78)
    print("  GC Inversion Longs v9 — Extended Environmental Filters")
    print("=" * 78)

    # Download / load env data
    print("\nEnvironmental data:")
    frames = download_env_data()
    env = build_env_lookup(frames)

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
          f"{m_base['win_rate']:.1%} WR, DD {m_base['max_drawdown_r']:.1f}R")

    # ══════════════════════════════════════════════════════════════════════
    # 1. GVZ (Gold Volatility Index)
    # ══════════════════════════════════════════════════════════════════════
    if "GVZ" in frames:
        print("\n" + "=" * 78)
        print("  1. GVZ — Gold Volatility Index (prior day close)")
        print("=" * 78)

        # Buckets
        gvz_buckets = [
            ("GVZ < 14", lambda e: e.get("gvz", np.nan) < 14),
            ("GVZ 14-17", lambda e: 14 <= e.get("gvz", np.nan) < 17),
            ("GVZ 17-20", lambda e: 17 <= e.get("gvz", np.nan) < 20),
            ("GVZ 20-25", lambda e: 20 <= e.get("gvz", np.nan) < 25),
            ("GVZ > 25", lambda e: e.get("gvz", np.nan) >= 25),
        ]

        print(f"\n    {'Bucket':>30s}  {'N':>5s}  {'WR':>5s}  {'Net R':>7s}  {'Avg R':>7s}  {'PF':>5s}  {'DD':>6s}")
        print(f"    {'─' * 72}")
        for label, fn in gvz_buckets:
            bucket = [t for t in filled
                      if env.get(t.date) and not np.isnan(env[t.date].get("gvz", np.nan))
                      and fn(env[t.date])]
            m = compute_metrics(bucket) if bucket else None
            print_row(label, m)

        # Filter tests
        gvz_filters = [
            ("GVZ < 15", lambda e: e.get("gvz", np.nan) < 15),
            ("GVZ < 17", lambda e: e.get("gvz", np.nan) < 17),
            ("GVZ < 20", lambda e: e.get("gvz", np.nan) < 20),
            ("GVZ > 20", lambda e: e.get("gvz", np.nan) > 20),
        ]
        for label, fn in gvz_filters:
            analyze_filter(label, trades, env, fn)
    else:
        print("\n  GVZ data not available — skipping")

    # ══════════════════════════════════════════════════════════════════════
    # 2. TNX (US 10Y Yield)
    # ══════════════════════════════════════════════════════════════════════
    if "TNX" in frames:
        print("\n" + "=" * 78)
        print("  2. TNX — US 10-Year Yield (prior day close)")
        print("=" * 78)

        # Buckets by yield level
        tnx_buckets = [
            ("TNX < 2.0%", lambda e: e.get("tnx", np.nan) < 2.0),
            ("TNX 2.0-3.0%", lambda e: 2.0 <= e.get("tnx", np.nan) < 3.0),
            ("TNX 3.0-4.0%", lambda e: 3.0 <= e.get("tnx", np.nan) < 4.0),
            ("TNX 4.0-5.0%", lambda e: 4.0 <= e.get("tnx", np.nan) < 5.0),
            ("TNX > 5.0%", lambda e: e.get("tnx", np.nan) >= 5.0),
        ]

        print(f"\n    {'Bucket':>30s}  {'N':>5s}  {'WR':>5s}  {'Net R':>7s}  {'Avg R':>7s}  {'PF':>5s}  {'DD':>6s}")
        print(f"    {'─' * 72}")
        for label, fn in tnx_buckets:
            bucket = [t for t in filled
                      if env.get(t.date) and not np.isnan(env[t.date].get("tnx", np.nan))
                      and fn(env[t.date])]
            m = compute_metrics(bucket) if bucket else None
            print_row(label, m)

        # Trend filters
        tnx_filters = [
            ("TNX < SMA20 (falling)", lambda e: e.get("tnx", np.nan) < e.get("tnx_sma20", np.nan)),
            ("TNX > SMA20 (rising)", lambda e: e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan)),
            ("TNX < SMA50 (falling)", lambda e: e.get("tnx", np.nan) < e.get("tnx_sma50", np.nan)),
            ("TNX > SMA50 (rising)", lambda e: e.get("tnx", np.nan) > e.get("tnx_sma50", np.nan)),
        ]
        for label, fn in tnx_filters:
            analyze_filter(label, trades, env, fn)
    else:
        print("\n  TNX data not available — skipping")

    # ══════════════════════════════════════════════════════════════════════
    # 3. SPY Trend (Risk-On vs Risk-Off)
    # ══════════════════════════════════════════════════════════════════════
    if "SPY" in frames:
        print("\n" + "=" * 78)
        print("  3. SPY — Risk-On vs Risk-Off (prior day close)")
        print("=" * 78)

        spy_filters = [
            ("SPY > SMA20 (risk-on)", lambda e: e.get("spy", np.nan) > e.get("spy_sma20", np.nan)),
            ("SPY < SMA20 (risk-off)", lambda e: e.get("spy", np.nan) < e.get("spy_sma20", np.nan)),
            ("SPY > SMA50 (risk-on)", lambda e: e.get("spy", np.nan) > e.get("spy_sma50", np.nan)),
            ("SPY < SMA50 (risk-off)", lambda e: e.get("spy", np.nan) < e.get("spy_sma50", np.nan)),
        ]
        for label, fn in spy_filters:
            analyze_filter(label, trades, env, fn)
    else:
        print("\n  SPY data not available — skipping")

    # ══════════════════════════════════════════════════════════════════════
    # 4. Month-of-Year Seasonality
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  4. Month-of-Year Seasonality")
    print("=" * 78)

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    print(f"\n    {'Month':>10s}  {'N':>5s}  {'WR':>5s}  {'Net R':>7s}  {'Avg R':>7s}  {'PF':>5s}  {'DD':>6s}")
    print(f"    {'─' * 55}")

    monthly_stats = {}
    for month_idx in range(1, 13):
        month_trades = [t for t in filled
                        if int(t.date[5:7]) == month_idx]
        m = compute_metrics(month_trades) if month_trades else None
        monthly_stats[month_idx] = m
        label = month_names[month_idx - 1]
        if m and m["total_trades"] > 0:
            print(f"    {label:>10s}  {m['total_trades']:>5d}  {m['win_rate']:>5.1%}  "
                  f"{m['total_r']:>7.1f}  {m['avg_r']:>7.3f}  {m['profit_factor']:>5.2f}  "
                  f"{m['max_drawdown_r']:>6.1f}")
        else:
            print(f"    {label:>10s}      0")

    # Seasonal groupings
    print("\n    Seasonal groupings:")
    seasonal_groups = [
        ("Strong (Jan,Sep,Oct,Nov)", [1, 9, 10, 11]),
        ("Weak (Mar,Apr,May,Jun)", [3, 4, 5, 6]),
        ("Neutral (Feb,Jul,Aug,Dec)", [2, 7, 8, 12]),
    ]

    for label, months in seasonal_groups:
        group_trades = [t for t in filled if int(t.date[5:7]) in months]
        m = compute_metrics(group_trades) if group_trades else None
        print_row(label, m)

    # ══════════════════════════════════════════════════════════════════════
    # 5. Best Combined Filters (cross-env)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  5. Cross-Environment Combinations")
    print("=" * 78)

    # Load VIX and DXY from cached files
    vix_path = DATA_DIR / "VIX_daily.csv"
    dxy_path = DATA_DIR / "DXY_daily.csv"
    has_vix_dxy = vix_path.exists() and dxy_path.exists()

    if has_vix_dxy:
        vix_df = pd.read_csv(vix_path, index_col=0, parse_dates=True)
        dxy_df = pd.read_csv(dxy_path, index_col=0, parse_dates=True)
        vix_close = vix_df["Close"].dropna()
        dxy_close = dxy_df["Close"].dropna()
        dxy_sma50 = dxy_close.rolling(50).mean()

        # Merge VIX/DXY into env lookup
        all_dates_vd = sorted(set(vix_close.index.date) | set(dxy_close.index.date))
        last_vix = np.nan
        last_dxy = np.nan
        last_dxy_sma50 = np.nan
        vix_dxy_raw = {}
        for d in all_dates_vd:
            ts = pd.Timestamp(d)
            if ts in vix_close.index:
                last_vix = float(vix_close.loc[ts])
            if ts in dxy_close.index:
                last_dxy = float(dxy_close.loc[ts])
            if ts in dxy_sma50.index and not np.isnan(dxy_sma50.loc[ts]):
                last_dxy_sma50 = float(dxy_sma50.loc[ts])
            vix_dxy_raw[str(d)] = {"vix": last_vix, "dxy": last_dxy, "dxy_sma50": last_dxy_sma50}

        # Shift
        sorted_vd = sorted(vix_dxy_raw.keys())
        vix_dxy = {}
        for i, d in enumerate(sorted_vd):
            if i > 0:
                vix_dxy[d] = vix_dxy_raw[sorted_vd[i - 1]]
            else:
                vix_dxy[d] = {"vix": np.nan, "dxy": np.nan, "dxy_sma50": np.nan}

        # Merge into env
        for d in env:
            if d in vix_dxy:
                env[d].update(vix_dxy[d])

    combo_filters = []
    if has_vix_dxy and "GVZ" in frames:
        combo_filters.append(
            ("VIX<18 + GVZ<17",
             lambda e: e.get("vix", np.nan) < 18 and e.get("gvz", np.nan) < 17))
        combo_filters.append(
            ("VIX<18 + DXY<SMA50 + GVZ<20",
             lambda e: (e.get("vix", np.nan) < 18
                        and e.get("dxy", np.nan) < e.get("dxy_sma50", np.nan)
                        and e.get("gvz", np.nan) < 20)))
    if has_vix_dxy and "TNX" in frames:
        combo_filters.append(
            ("VIX<18 + TNX<SMA50",
             lambda e: e.get("vix", np.nan) < 18 and e.get("tnx", np.nan) < e.get("tnx_sma50", np.nan)))
        combo_filters.append(
            ("VIX<18 + DXY<SMA50 + TNX<SMA50",
             lambda e: (e.get("vix", np.nan) < 18
                        and e.get("dxy", np.nan) < e.get("dxy_sma50", np.nan)
                        and e.get("tnx", np.nan) < e.get("tnx_sma50", np.nan))))
    if "GVZ" in frames and "TNX" in frames:
        combo_filters.append(
            ("GVZ<17 + TNX<SMA50",
             lambda e: e.get("gvz", np.nan) < 17 and e.get("tnx", np.nan) < e.get("tnx_sma50", np.nan)))
    if "SPY" in frames and has_vix_dxy:
        combo_filters.append(
            ("VIX<18 + SPY>SMA50",
             lambda e: e.get("vix", np.nan) < 18 and e.get("spy", np.nan) > e.get("spy_sma50", np.nan)))

    for label, fn in combo_filters:
        analyze_filter(label, trades, env, fn)

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    print(f"\n  Baseline: {m_base['total_trades']} trades, {m_base['total_r']:.1f}R, "
          f"{m_base['win_rate']:.1%} WR, DD {m_base['max_drawdown_r']:.1f}R")
    print("\n  Look for filters that improve avg R and/or reduce DD vs baseline.")
    print("  Remember: post-hoc filtering on 250 trades has high overfitting risk.")
    print("  Best use: regime SIZING (not filtering).\n")


if __name__ == "__main__":
    main()
