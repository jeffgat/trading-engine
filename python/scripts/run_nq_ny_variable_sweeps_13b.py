#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 13b: environmental/regime filters.

Anchor: g=3.0 rr=2.25 tp1=0.7 stop=9.0% long-only 20m ORB entry 09:50-15:00

Tests post-trade filters using external daily data (all use prior-day close
to avoid look-ahead):
  1. VIX — implied vol level + SMA trend
  2. SPY — risk-on/risk-off (SMA20, SMA50)
  3. TNX — US 10Y yield level + trend
  4. DXY — US Dollar Index level + trend
  5. NQ SMA trend gate (price vs own SMA)
  6. ATR volatility gate (high-vol day removal)
  7. Month-of-year seasonality
  8. Cross-environment combinations

Data files used (in python/data/raw/):
  - NQ_5m.csv, NQ_1m.csv (backtest data)
  - VIX_daily.csv, SPY_daily.csv, TNX_daily.csv, DXY_daily.csv
"""

import sys
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import (
    apply_sma_trend_gate,
    apply_atr_volatility_gate,
    apply_dow_filter,
)

START_DATE = "2015-01-01"
DATA_YEARS = 11
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def make_config():
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=3.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.25,
        tp1_ratio=0.7,
        atr_length=14,
        name="NQ NY Env Filters R13b",
    )


HDR_ENV = (f"    {'Filter':>35s}  {'N':>5s}  {'WR':>5s}  {'Net R':>7s}  "
           f"{'R/yr':>6s}  {'Avg R':>7s}  {'PF':>5s}  {'DD':>6s}  {'Calmar':>7s}")


def print_env_header(title):
    print(f"\n{'='*100}")
    print(f"  {title}")
    print(f"{'='*100}")
    print(HDR_ENV)
    print(f"    {'─' * 92}")


def print_env_row(label, m, marker="", indent=4):
    pad = " " * indent
    if m and m["total_trades"] > 0:
        r_yr = m["total_r"] / DATA_YEARS
        print(f"{pad}{label:>35s}  {m['total_trades']:>5d}  {m['win_rate']:>5.1%}  "
              f"{m['total_r']:>7.1f}  {r_yr:>6.1f}  {m['avg_r']:>7.3f}  "
              f"{m['profit_factor']:>5.2f}  {m['max_drawdown_r']:>6.1f}  "
              f"{m['calmar_ratio']:>7.2f}{marker}")
    else:
        print(f"{pad}{label:>35s}      0")


def print_year_breakdown(m, indent=4):
    pad = " " * indent
    if m and "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"{pad}  R by year: {yr_str}")


# ── ENV DATA LOADING ────────────────────────────────────────────────────

def load_daily_csv(filename):
    """Load a daily CSV with Date index."""
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  WARNING: {filename} not found — skipping")
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    print(f"  {filename}: {len(df)} days ({df.index[0].date()} to {df.index[-1].date()})")
    return df


def build_env_lookup(frames):
    """Build date → env dict using prior day's close (no look-ahead).

    Returns dict[str, dict] with all env variables for each trade date.
    """
    series = {}

    for name, col in [("vix", "VIX"), ("spy", "SPY"), ("tnx", "TNX"), ("dxy", "DXY")]:
        if col in frames and frames[col] is not None:
            close = frames[col]["Close"].dropna()
            series[name] = close
            series[f"{name}_sma20"] = close.rolling(20).mean()
            series[f"{name}_sma50"] = close.rolling(50).mean()
            series[f"{name}_sma200"] = close.rolling(200).mean()

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


def analyze_filter(label, filled_trades, env_lookup, filter_fn):
    """Split trades by filter, return IN and OUT metrics."""
    in_trades = []
    out_trades = []
    for t in filled_trades:
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

    return m_in, m_out


def main():
    print("NQ NY ORB — Round 13b: Environmental & Regime Filters")
    print("Anchor: g=3.0 rr=2.25 tp1=0.7 stop=9% long-only 20m ORB 09:50-15:00")
    print("=" * 100)

    # ── Load backtest data
    print("\nLoading NQ data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    # ── Run baseline backtest
    print("\nRunning baseline backtest...")
    config = make_config()
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    m_base = compute_metrics(trades)

    print_env_header("BASELINE")
    print_env_row("no filter (baseline)", m_base, " <-- anchor")
    print_year_breakdown(m_base)

    # ── Load environmental data
    print("\nLoading environmental data...")
    frames = {
        "VIX": load_daily_csv("VIX_daily.csv"),
        "SPY": load_daily_csv("SPY_daily.csv"),
        "TNX": load_daily_csv("TNX_daily.csv"),
        "DXY": load_daily_csv("DXY_daily.csv"),
    }
    env = build_env_lookup(frames)
    print(f"  Env lookup: {len(env)} dates")

    # Track all filter results for summary
    all_filters = []  # (label, m_in, m_out)

    # ══════════════════════════════════════════════════════════════════════
    # 1. VIX — Implied Volatility
    # ══════════════════════════════════════════════════════════════════════
    if frames["VIX"] is not None:
        print_env_header("1. VIX — Implied Volatility (prior-day close)")

        # Buckets
        vix_buckets = [
            ("VIX < 15 (calm)", lambda e: e.get("vix", np.nan) < 15),
            ("VIX 15-20 (normal)", lambda e: 15 <= e.get("vix", np.nan) < 20),
            ("VIX 20-25 (elevated)", lambda e: 20 <= e.get("vix", np.nan) < 25),
            ("VIX 25-30 (high)", lambda e: 25 <= e.get("vix", np.nan) < 30),
            ("VIX > 30 (extreme)", lambda e: e.get("vix", np.nan) >= 30),
        ]
        for label, fn in vix_buckets:
            bucket = [t for t in filled
                      if env.get(t.date) and not np.isnan(env[t.date].get("vix", np.nan))
                      and fn(env[t.date])]
            m = compute_metrics(bucket) if bucket else None
            print_env_row(label, m)

        print()
        # Filter tests
        vix_filters = [
            ("VIX < 18", lambda e: e.get("vix", np.nan) < 18),
            ("VIX < 20", lambda e: e.get("vix", np.nan) < 20),
            ("VIX < 25", lambda e: e.get("vix", np.nan) < 25),
            ("VIX > SMA20 (rising vol)", lambda e: e.get("vix", np.nan) > e.get("vix_sma20", np.nan)),
            ("VIX < SMA20 (falling vol)", lambda e: e.get("vix", np.nan) < e.get("vix_sma20", np.nan)),
            ("VIX > SMA50 (high regime)", lambda e: e.get("vix", np.nan) > e.get("vix_sma50", np.nan)),
            ("VIX < SMA50 (low regime)", lambda e: e.get("vix", np.nan) < e.get("vix_sma50", np.nan)),
        ]
        for label, fn in vix_filters:
            m_in, m_out = analyze_filter(label, filled, env, fn)
            print_env_row(f"IN: {label}", m_in)
            print_env_row(f"OUT: {label}", m_out)
            if m_in:
                all_filters.append((label, m_in, m_out))
            print()

    # ══════════════════════════════════════════════════════════════════════
    # 2. SPY — Risk-On vs Risk-Off
    # ══════════════════════════════════════════════════════════════════════
    if frames["SPY"] is not None:
        print_env_header("2. SPY — Risk-On vs Risk-Off (prior-day close)")

        spy_filters = [
            ("SPY > SMA20 (risk-on)", lambda e: e.get("spy", np.nan) > e.get("spy_sma20", np.nan)),
            ("SPY < SMA20 (risk-off)", lambda e: e.get("spy", np.nan) < e.get("spy_sma20", np.nan)),
            ("SPY > SMA50 (risk-on)", lambda e: e.get("spy", np.nan) > e.get("spy_sma50", np.nan)),
            ("SPY < SMA50 (risk-off)", lambda e: e.get("spy", np.nan) < e.get("spy_sma50", np.nan)),
            ("SPY > SMA200 (bull mkt)", lambda e: e.get("spy", np.nan) > e.get("spy_sma200", np.nan)),
            ("SPY < SMA200 (bear mkt)", lambda e: e.get("spy", np.nan) < e.get("spy_sma200", np.nan)),
        ]
        for label, fn in spy_filters:
            m_in, m_out = analyze_filter(label, filled, env, fn)
            print_env_row(f"IN: {label}", m_in)
            print_env_row(f"OUT: {label}", m_out)
            if m_in:
                all_filters.append((label, m_in, m_out))
            print()

    # ══════════════════════════════════════════════════════════════════════
    # 3. TNX — US 10-Year Yield
    # ══════════════════════════════════════════════════════════════════════
    if frames["TNX"] is not None:
        print_env_header("3. TNX — US 10-Year Yield (prior-day close)")

        # Buckets by yield level
        tnx_buckets = [
            ("TNX < 2.0%", lambda e: e.get("tnx", np.nan) < 2.0),
            ("TNX 2.0-3.0%", lambda e: 2.0 <= e.get("tnx", np.nan) < 3.0),
            ("TNX 3.0-4.0%", lambda e: 3.0 <= e.get("tnx", np.nan) < 4.0),
            ("TNX 4.0-5.0%", lambda e: 4.0 <= e.get("tnx", np.nan) < 5.0),
            ("TNX > 5.0%", lambda e: e.get("tnx", np.nan) >= 5.0),
        ]
        for label, fn in tnx_buckets:
            bucket = [t for t in filled
                      if env.get(t.date) and not np.isnan(env[t.date].get("tnx", np.nan))
                      and fn(env[t.date])]
            m = compute_metrics(bucket) if bucket else None
            print_env_row(label, m)

        print()
        tnx_filters = [
            ("TNX < SMA20 (falling)", lambda e: e.get("tnx", np.nan) < e.get("tnx_sma20", np.nan)),
            ("TNX > SMA20 (rising)", lambda e: e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan)),
            ("TNX < SMA50 (falling)", lambda e: e.get("tnx", np.nan) < e.get("tnx_sma50", np.nan)),
            ("TNX > SMA50 (rising)", lambda e: e.get("tnx", np.nan) > e.get("tnx_sma50", np.nan)),
        ]
        for label, fn in tnx_filters:
            m_in, m_out = analyze_filter(label, filled, env, fn)
            print_env_row(f"IN: {label}", m_in)
            print_env_row(f"OUT: {label}", m_out)
            if m_in:
                all_filters.append((label, m_in, m_out))
            print()

    # ══════════════════════════════════════════════════════════════════════
    # 4. DXY — US Dollar Index
    # ══════════════════════════════════════════════════════════════════════
    if frames["DXY"] is not None:
        print_env_header("4. DXY — US Dollar Index (prior-day close)")

        dxy_filters = [
            ("DXY > SMA20 (strong $)", lambda e: e.get("dxy", np.nan) > e.get("dxy_sma20", np.nan)),
            ("DXY < SMA20 (weak $)", lambda e: e.get("dxy", np.nan) < e.get("dxy_sma20", np.nan)),
            ("DXY > SMA50 (strong $)", lambda e: e.get("dxy", np.nan) > e.get("dxy_sma50", np.nan)),
            ("DXY < SMA50 (weak $)", lambda e: e.get("dxy", np.nan) < e.get("dxy_sma50", np.nan)),
            ("DXY > SMA200 (strong $)", lambda e: e.get("dxy", np.nan) > e.get("dxy_sma200", np.nan)),
            ("DXY < SMA200 (weak $)", lambda e: e.get("dxy", np.nan) < e.get("dxy_sma200", np.nan)),
        ]
        for label, fn in dxy_filters:
            m_in, m_out = analyze_filter(label, filled, env, fn)
            print_env_row(f"IN: {label}", m_in)
            print_env_row(f"OUT: {label}", m_out)
            if m_in:
                all_filters.append((label, m_in, m_out))
            print()

    # ══════════════════════════════════════════════════════════════════════
    # 5. NQ SMA TREND GATE (built-in)
    # ══════════════════════════════════════════════════════════════════════
    print_env_header("5. NQ SMA TREND GATE (price vs own SMA, prior-day)")

    for sma_period in [10, 20, 50, 100, 200]:
        gated = apply_sma_trend_gate(trades, df_5m, sma_period=sma_period)
        m = compute_metrics(gated)
        label = f"NQ with-trend SMA{sma_period}"
        print_env_row(label, m)
        if sma_period in (20, 50, 200):
            print_year_breakdown(m)
        all_filters.append((label, m, None))

    # Also test anti-trend (counter-trend)
    print()
    print(f"    Note: with-trend means long only when NQ > SMA (bullish)")
    print(f"    Since we're already long-only, this only removes longs in downtrends")

    # ══════════════════════════════════════════════════════════════════════
    # 6. ATR VOLATILITY GATE (built-in)
    # ══════════════════════════════════════════════════════════════════════
    print_env_header("6. ATR VOLATILITY GATE (skip high-vol days)")

    for threshold in [1.0, 1.1, 1.25, 1.5, 2.0]:
        gated = apply_atr_volatility_gate(
            trades, df_5m, atr_length=14, atr_sma_length=20, threshold=threshold
        )
        m = compute_metrics(gated)
        label = f"ATR < {threshold:.1f}x SMA20"
        print_env_row(label, m)
        all_filters.append((label, m, None))

    # Also test with different SMA lookback
    print()
    for sma_len in [10, 50]:
        gated = apply_atr_volatility_gate(
            trades, df_5m, atr_length=14, atr_sma_length=sma_len, threshold=1.25
        )
        m = compute_metrics(gated)
        label = f"ATR < 1.25x SMA{sma_len}"
        print_env_row(label, m)

    # ══════════════════════════════════════════════════════════════════════
    # 7. MONTH-OF-YEAR SEASONALITY
    # ══════════════════════════════════════════════════════════════════════
    print_env_header("7. MONTH-OF-YEAR SEASONALITY")

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    monthly_r = {}
    for month_idx in range(1, 13):
        month_trades = [t for t in filled if int(t.date[5:7]) == month_idx]
        m = compute_metrics(month_trades) if month_trades else None
        monthly_r[month_idx] = m
        label = month_names[month_idx - 1]
        print_env_row(label, m)

    # Seasonal groupings
    print(f"\n    Seasonal groupings:")
    print(f"    {'─' * 92}")
    seasonal_groups = [
        ("Q1 (Jan-Mar)", [1, 2, 3]),
        ("Q2 (Apr-Jun)", [4, 5, 6]),
        ("Q3 (Jul-Sep)", [7, 8, 9]),
        ("Q4 (Oct-Dec)", [10, 11, 12]),
        ("Excl worst month", None),  # computed below
        ("Excl worst 2 months", None),
    ]

    # Find worst months by avg R
    month_avg_r = {}
    for mi, m in monthly_r.items():
        if m and m["total_trades"] > 0:
            month_avg_r[mi] = m["avg_r"]
    worst_months = sorted(month_avg_r, key=month_avg_r.get)

    for label, months in seasonal_groups:
        if label == "Excl worst month" and worst_months:
            wm = worst_months[0]
            months_in = [i for i in range(1, 13) if i != wm]
            group_trades = [t for t in filled if int(t.date[5:7]) in months_in]
            label = f"Excl {month_names[wm-1]} (worst avg R)"
        elif label == "Excl worst 2 months" and len(worst_months) >= 2:
            wm1, wm2 = worst_months[0], worst_months[1]
            months_in = [i for i in range(1, 13) if i not in (wm1, wm2)]
            group_trades = [t for t in filled if int(t.date[5:7]) in months_in]
            label = f"Excl {month_names[wm1-1]}+{month_names[wm2-1]}"
        elif months:
            group_trades = [t for t in filled if int(t.date[5:7]) in months]
        else:
            continue
        m = compute_metrics(group_trades) if group_trades else None
        print_env_row(label, m)

    # ══════════════════════════════════════════════════════════════════════
    # 8. CROSS-ENVIRONMENT COMBINATIONS
    # ══════════════════════════════════════════════════════════════════════
    print_env_header("8. CROSS-ENVIRONMENT COMBINATIONS")

    combo_filters = [
        ("VIX<20 + SPY>SMA50",
         lambda e: e.get("vix", np.nan) < 20 and e.get("spy", np.nan) > e.get("spy_sma50", np.nan)),
        ("VIX<25 + SPY>SMA50",
         lambda e: e.get("vix", np.nan) < 25 and e.get("spy", np.nan) > e.get("spy_sma50", np.nan)),
        ("VIX<20 + SPY>SMA200",
         lambda e: e.get("vix", np.nan) < 20 and e.get("spy", np.nan) > e.get("spy_sma200", np.nan)),
        ("VIX<25 + SPY>SMA200",
         lambda e: e.get("vix", np.nan) < 25 and e.get("spy", np.nan) > e.get("spy_sma200", np.nan)),
        ("VIX<SMA20 + SPY>SMA50",
         lambda e: (e.get("vix", np.nan) < e.get("vix_sma20", np.nan)
                    and e.get("spy", np.nan) > e.get("spy_sma50", np.nan))),
        ("VIX<20 + TNX<SMA50",
         lambda e: e.get("vix", np.nan) < 20 and e.get("tnx", np.nan) < e.get("tnx_sma50", np.nan)),
        ("VIX<25 + DXY<SMA50",
         lambda e: e.get("vix", np.nan) < 25 and e.get("dxy", np.nan) < e.get("dxy_sma50", np.nan)),
        ("SPY>SMA50 + TNX<SMA50",
         lambda e: (e.get("spy", np.nan) > e.get("spy_sma50", np.nan)
                    and e.get("tnx", np.nan) < e.get("tnx_sma50", np.nan))),
        ("SPY>SMA50 + DXY<SMA50",
         lambda e: (e.get("spy", np.nan) > e.get("spy_sma50", np.nan)
                    and e.get("dxy", np.nan) < e.get("dxy_sma50", np.nan))),
        ("VIX<20 + SPY>SMA50 + TNX<SMA50",
         lambda e: (e.get("vix", np.nan) < 20
                    and e.get("spy", np.nan) > e.get("spy_sma50", np.nan)
                    and e.get("tnx", np.nan) < e.get("tnx_sma50", np.nan))),
        ("VIX<20 + SPY>SMA50 + DXY<SMA50",
         lambda e: (e.get("vix", np.nan) < 20
                    and e.get("spy", np.nan) > e.get("spy_sma50", np.nan)
                    and e.get("dxy", np.nan) < e.get("dxy_sma50", np.nan))),
    ]

    for label, fn in combo_filters:
        m_in, m_out = analyze_filter(label, filled, env, fn)
        print_env_row(f"IN: {label}", m_in)
        print_env_row(f"OUT: {label}", m_out)
        if m_in:
            all_filters.append((f"COMBO: {label}", m_in, m_out))
        print()

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print(f"  SUMMARY — Top filters by Calmar improvement vs baseline")
    print(f"{'='*100}")

    base_calmar = m_base["calmar_ratio"]
    base_ryr = m_base["total_r"] / DATA_YEARS
    print(f"\n  Baseline: {m_base['total_trades']} trades, {base_ryr:.1f} R/yr, "
          f"DD {m_base['max_drawdown_r']:.1f}R, Calmar {base_calmar:.2f}")

    # Sort filters by Calmar of the IN group
    ranked = []
    for label, m_in, m_out in all_filters:
        if m_in and m_in["total_trades"] >= 200:  # minimum trade count
            calmar_delta = m_in["calmar_ratio"] - base_calmar
            ryr_delta = m_in["total_r"] / DATA_YEARS - base_ryr
            ranked.append((label, m_in, m_out, calmar_delta, ryr_delta))

    ranked.sort(key=lambda x: x[3], reverse=True)

    print(f"\n  {'Filter':<45s}  {'N':>5s}  {'R/yr':>6s}  {'DD':>6s}  "
          f"{'Calmar':>7s}  {'Δ Calmar':>9s}  {'Δ R/yr':>7s}")
    print(f"  {'─' * 90}")

    for label, m_in, m_out, calmar_d, ryr_d in ranked[:20]:
        ryr = m_in["total_r"] / DATA_YEARS
        print(f"  {label:<45s}  {m_in['total_trades']:>5d}  {ryr:>6.1f}  "
              f"{m_in['max_drawdown_r']:>6.1f}  {m_in['calmar_ratio']:>7.2f}  "
              f"{calmar_d:>+8.2f}  {ryr_d:>+6.1f}")

    print(f"\n  WARNING: Post-hoc filtering has HIGH overfitting risk with ~1100 trades.")
    print(f"  Filters that cut >30% of trades should be viewed skeptically.")
    print(f"  Best use: regime SIZING (not hard filtering).")

    elapsed = time.time() - t_start
    print(f"\n{'='*100}")
    print(f"  ALL ANALYSIS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*100}")


if __name__ == "__main__":
    main()
