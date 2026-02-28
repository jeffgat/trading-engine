#!/usr/bin/env python3
"""GC Inversion Longs v9 — Combined Regime Interaction Tests.

Tests:
  1. Regime-based sizing: 2x when VIX < 18 / DXY < SMA50, 1x otherwise
  2. Friday + VIX regime interaction: Are Fridays only weak in high-VIX?
  3. Morning weakness + VIX regime interaction: Is 09:00-10:00 weakness VIX-dependent?
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


def build_config(entry_start="09:35"):
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start=entry_start,
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


def load_macro():
    """Load cached VIX and DXY data."""
    vix_path = DATA_DIR / "VIX_daily.csv"
    dxy_path = DATA_DIR / "DXY_daily.csv"

    if not vix_path.exists() or not dxy_path.exists():
        raise FileNotFoundError(
            "Run run_gc_inv_regime_filter.py first to download macro data"
        )

    vix = pd.read_csv(vix_path, index_col=0, parse_dates=True)
    dxy = pd.read_csv(dxy_path, index_col=0, parse_dates=True)
    return vix, dxy


def build_regime_lookup(vix_df, dxy_df):
    """Build date → regime dict using prior day's close (no look-ahead)."""
    vix_close = vix_df["Close"].dropna()
    dxy_close = dxy_df["Close"].dropna()
    dxy_sma20 = dxy_close.rolling(20).mean()
    dxy_sma50 = dxy_close.rolling(50).mean()

    lookup = {}
    all_dates = sorted(set(vix_close.index.date) | set(dxy_close.index.date))

    last_vix = np.nan
    last_dxy = np.nan
    last_dxy_sma20 = np.nan
    last_dxy_sma50 = np.nan

    for d in all_dates:
        ts = pd.Timestamp(d)
        if ts in vix_close.index:
            last_vix = float(vix_close.loc[ts])
        if ts in dxy_close.index:
            last_dxy = float(dxy_close.loc[ts])
        if ts in dxy_sma20.index and not np.isnan(dxy_sma20.loc[ts]):
            last_dxy_sma20 = float(dxy_sma20.loc[ts])
        if ts in dxy_sma50.index and not np.isnan(dxy_sma50.loc[ts]):
            last_dxy_sma50 = float(dxy_sma50.loc[ts])

        lookup[str(d)] = {
            "vix": last_vix,
            "dxy": last_dxy,
            "dxy_sma20": last_dxy_sma20,
            "dxy_sma50": last_dxy_sma50,
        }

    # Shift: trade on date D uses macro data from D-1
    shifted = {}
    sorted_dates = sorted(lookup.keys())
    for i, d in enumerate(sorted_dates):
        if i > 0:
            shifted[d] = lookup[sorted_dates[i - 1]]
        else:
            shifted[d] = {"vix": np.nan, "dxy": np.nan, "dxy_sma20": np.nan, "dxy_sma50": np.nan}

    return shifted


def print_metrics_row(label, m, indent=4):
    """Print a compact metrics row."""
    pad = " " * indent
    if m and m["total_trades"] > 0:
        print(f"{pad}{label:>28s}  {m['total_trades']:>5d} trades  {m['win_rate']:>5.1%} WR  "
              f"{m['total_r']:>7.1f}R  PF {m['profit_factor']:>5.2f}  DD {m['max_drawdown_r']:>6.1f}R  "
              f"Avg {m['avg_r']:>6.3f}R")
    else:
        print(f"{pad}{label:>28s}      0 trades")


def main():
    print("=" * 78)
    print("  GC Inversion Longs v9 — Combined Regime Interaction Tests")
    print("=" * 78)

    # Load data
    print("\nLoading macro data...")
    vix_df, dxy_df = load_macro()
    regime = build_regime_lookup(vix_df, dxy_df)

    print("Loading GC data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")

    config = build_config()
    print("Running v9 backtest...")
    trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    m_base = compute_metrics(trades)
    print(f"\n  Baseline: {m_base['total_trades']} trades, {m_base['total_r']:.1f}R, "
          f"{m_base['win_rate']:.1%} WR, DD {m_base['max_drawdown_r']:.1f}R")

    # Attach regime to each trade
    def get_regime(t):
        r = regime.get(t.date)
        if r is None or np.isnan(r.get("vix", np.nan)):
            return None
        return r

    # ══════════════════════════════════════════════════════════════════════
    # TEST 1: Regime-Based Sizing
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  TEST 1: Regime-Based Sizing")
    print("  Trade 2x size in favorable regime (VIX < 18), 1x otherwise")
    print("=" * 78)

    # Simulate sizing by doubling R for favorable regime trades
    # Method: create weighted R series and compute equity curve
    def compute_sized_metrics(trades_list, size_fn, label):
        """Compute metrics with variable sizing.
        size_fn(regime_dict) -> multiplier (1.0 or 2.0)
        """
        r_values = []
        for t in trades_list:
            if t.exit_type == EXIT_NO_FILL:
                continue
            r = get_regime(t)
            mult = size_fn(r) if r else 1.0
            r_values.append(t.r_multiple * mult)

        if not r_values:
            return None

        r_arr = np.array(r_values)
        equity = np.cumsum(r_arr)
        running_max = np.maximum.accumulate(equity)
        drawdowns = equity - running_max
        max_dd = float(np.min(drawdowns))
        total_r = float(np.sum(r_arr))
        wins = np.sum(r_arr > 0)
        total = len(r_arr)

        return {
            "trades": total,
            "win_rate": float(wins / total) if total > 0 else 0,
            "total_r": total_r,
            "max_dd": max_dd,
            "avg_r": float(np.mean(r_arr)),
            "sharpe": float(np.mean(r_arr) / np.std(r_arr) * np.sqrt(252)) if np.std(r_arr) > 0 else 0,
        }

    sizing_strategies = [
        ("1x flat (baseline)", lambda r: 1.0),
        ("2x when VIX < 18", lambda r: 2.0 if r["vix"] < 18 else 1.0),
        ("2x when VIX < 20", lambda r: 2.0 if r["vix"] < 20 else 1.0),
        ("2x when VIX < 25", lambda r: 2.0 if r["vix"] < 25 else 1.0),
        ("2x VIX<18 + DXY<SMA50", lambda r: 2.0 if r["vix"] < 18 and r["dxy"] < r["dxy_sma50"] and not np.isnan(r["dxy_sma50"]) else 1.0),
        ("2x VIX<20 + DXY<SMA50", lambda r: 2.0 if r["vix"] < 20 and r["dxy"] < r["dxy_sma50"] and not np.isnan(r["dxy_sma50"]) else 1.0),
        ("1.5x when VIX < 18", lambda r: 1.5 if r["vix"] < 18 else 1.0),
        ("0.5x when VIX > 25", lambda r: 0.5 if r["vix"] > 25 else 1.0),
        ("2x VIX<18, 0.5x VIX>25", lambda r: 2.0 if r["vix"] < 18 else (0.5 if r["vix"] > 25 else 1.0)),
    ]

    print(f"\n  {'Strategy':>30s}  {'Trades':>6s}  {'WR':>5s}  {'Net R':>7s}  {'Max DD':>7s}  {'Avg R':>7s}")
    print(f"  {'─' * 72}")

    for label, fn in sizing_strategies:
        result = compute_sized_metrics(filled, fn, label)
        if result:
            print(f"  {label:>30s}  {result['trades']:>6d}  {result['win_rate']:>4.1%}  "
                  f"{result['total_r']:>7.1f}  {result['max_dd']:>7.1f}  {result['avg_r']:>7.3f}")

    # ══════════════════════════════════════════════════════════════════════
    # TEST 2: Friday + VIX Regime Interaction
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  TEST 2: Friday + VIX Regime Interaction")
    print("  Are Fridays only weak in high-VIX? If low-VIX Fridays are fine,")
    print("  the Friday filter is just a VIX proxy.")
    print("=" * 78)

    # Parse day of week from trade date
    def get_dow(t):
        try:
            dt = pd.Timestamp(t.date)
            return dt.dayofweek  # 0=Mon, 4=Fri
        except Exception:
            return -1

    friday_trades = [t for t in filled if get_dow(t) == 4]
    non_friday_trades = [t for t in filled if get_dow(t) != 4 and get_dow(t) >= 0]

    # Friday by VIX regime
    vix_thresholds = [18, 20, 25]

    for vix_thresh in vix_thresholds:
        print(f"\n  VIX threshold: {vix_thresh}")
        print(f"  {'─' * 72}")

        # Fridays in low VIX
        fri_low = [t for t in friday_trades
                   if get_regime(t) and get_regime(t)["vix"] < vix_thresh]
        fri_high = [t for t in friday_trades
                    if get_regime(t) and get_regime(t)["vix"] >= vix_thresh]
        nonfri_low = [t for t in non_friday_trades
                      if get_regime(t) and get_regime(t)["vix"] < vix_thresh]
        nonfri_high = [t for t in non_friday_trades
                       if get_regime(t) and get_regime(t)["vix"] >= vix_thresh]

        m_fl = compute_metrics(fri_low) if fri_low else None
        m_fh = compute_metrics(fri_high) if fri_high else None
        m_nfl = compute_metrics(nonfri_low) if nonfri_low else None
        m_nfh = compute_metrics(nonfri_high) if nonfri_high else None

        print_metrics_row(f"Friday + VIX < {vix_thresh}", m_fl)
        print_metrics_row(f"Friday + VIX >= {vix_thresh}", m_fh)
        print_metrics_row(f"Mon-Thu + VIX < {vix_thresh}", m_nfl)
        print_metrics_row(f"Mon-Thu + VIX >= {vix_thresh}", m_nfh)

    # ══════════════════════════════════════════════════════════════════════
    # TEST 3: Morning Weakness + VIX Regime Interaction
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  TEST 3: Morning Weakness + VIX Regime Interaction")
    print("  Is the 09:35-10:00 weakness VIX-dependent?")
    print("=" * 78)

    # Classify trades by entry hour
    def get_entry_hour(t):
        """Extract hour from entry time."""
        try:
            if hasattr(t, 'entry_time') and t.entry_time:
                # entry_time might be a string like "09:45" or a full timestamp
                ts = pd.Timestamp(t.entry_time)
                return ts.hour
        except Exception:
            pass
        return -1

    # Since we can't easily get entry time from TradeResult, use a proxy:
    # Run separate backtests with different entry_start to isolate time windows
    print("\n  Running backtests with different entry windows to isolate time segments...")

    # Early window: 09:35-10:00 only
    config_early = build_config(entry_start="09:35")
    # We'll approximate by comparing full vs delayed start

    # Instead of entry_time (which isn't in TradeResult), let's do a cleaner test:
    # Run with entry_start=10:00 and compare the DIFFERENCE to baseline.
    # Trades in baseline but NOT in delayed = "early" trades (09:35-10:00 entries)

    config_delayed = build_config(entry_start="10:00")
    print("  Running delayed-start (10:00) backtest...")
    trades_delayed = run_backtest_qm(df, config_delayed, start_date=START, df_1m=df_1m)
    filled_delayed = [t for t in trades_delayed if t.exit_type != EXIT_NO_FILL]

    # Early trades = trades in baseline that share a date with no trade in delayed
    delayed_dates = {t.date for t in filled_delayed}
    baseline_dates = {t.date for t in filled}

    early_only_trades = [t for t in filled if t.date not in delayed_dates]
    late_trades = [t for t in filled if t.date in delayed_dates]

    print(f"\n  Early-only trades (09:35-10:00): {len(early_only_trades)}")
    print(f"  Late trades (10:00+ in baseline): {len(late_trades)}")

    # Early trades by VIX regime
    for vix_thresh in vix_thresholds:
        print(f"\n  VIX threshold: {vix_thresh}")
        print(f"  {'─' * 72}")

        early_low = [t for t in early_only_trades
                     if get_regime(t) and get_regime(t)["vix"] < vix_thresh]
        early_high = [t for t in early_only_trades
                      if get_regime(t) and get_regime(t)["vix"] >= vix_thresh]
        late_low = [t for t in late_trades
                    if get_regime(t) and get_regime(t)["vix"] < vix_thresh]
        late_high = [t for t in late_trades
                     if get_regime(t) and get_regime(t)["vix"] >= vix_thresh]

        m_el = compute_metrics(early_low) if early_low else None
        m_eh = compute_metrics(early_high) if early_high else None
        m_ll = compute_metrics(late_low) if late_low else None
        m_lh = compute_metrics(late_high) if late_high else None

        print_metrics_row(f"Early (09:35-10) + VIX < {vix_thresh}", m_el)
        print_metrics_row(f"Early (09:35-10) + VIX >= {vix_thresh}", m_eh)
        print_metrics_row(f"Late (10:00+) + VIX < {vix_thresh}", m_ll)
        print_metrics_row(f"Late (10:00+) + VIX >= {vix_thresh}", m_lh)

    # ══════════════════════════════════════════════════════════════════════
    # TEST 4: Combined Regime Filter Equity Simulation
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  TEST 4: Best Combined Strategies (Yearly Breakdown)")
    print("=" * 78)

    # Compare strategies with yearly breakdown
    strategies = [
        ("v9 Baseline (1x flat)", lambda t, r: 1.0, lambda t, r: True),
        ("Skip VIX > 25", lambda t, r: 1.0, lambda t, r: r["vix"] < 25),
        ("Skip VIX > 25 + Skip Fri", lambda t, r: 1.0, lambda t, r: r["vix"] < 25 and get_dow(t) != 4),
        ("2x VIX<18, skip VIX>25", lambda t, r: 2.0 if r["vix"] < 18 else 1.0, lambda t, r: r["vix"] < 25),
        ("2x VIX<18, 0.5x VIX>25", lambda t, r: 2.0 if r["vix"] < 18 else (0.5 if r["vix"] > 25 else 1.0), lambda t, r: True),
        ("2x VIX<18 only, 0x else", lambda t, r: 2.0, lambda t, r: r["vix"] < 18),
    ]

    for label, size_fn, filter_fn in strategies:
        print(f"\n  {label}")
        print(f"  {'─' * 72}")

        # Build sized R series with filtering
        yearly_r = {}
        total_r_vals = []
        for t in filled:
            r = get_regime(t)
            if r is None or np.isnan(r.get("vix", np.nan)):
                continue
            if not filter_fn(t, r):
                continue
            mult = size_fn(t, r)
            sized_r = t.r_multiple * mult
            total_r_vals.append(sized_r)

            year = t.date[:4]
            if year not in yearly_r:
                yearly_r[year] = []
            yearly_r[year].append(sized_r)

        if not total_r_vals:
            print("    No trades")
            continue

        r_arr = np.array(total_r_vals)
        equity = np.cumsum(r_arr)
        running_max = np.maximum.accumulate(equity)
        drawdowns = equity - running_max
        max_dd = float(np.min(drawdowns))
        total_r = float(np.sum(r_arr))
        n_trades = len(r_arr)
        wr = float(np.sum(r_arr > 0) / n_trades) if n_trades > 0 else 0

        print(f"    TOTAL: {n_trades} trades, {wr:.1%} WR, {total_r:.1f}R, DD {max_dd:.1f}R, Avg {np.mean(r_arr):.3f}R")

        print(f"    {'Year':>6s}  {'Trades':>6s}  {'Net R':>7s}  {'Avg R':>7s}")
        for year in sorted(yearly_r.keys()):
            yr = np.array(yearly_r[year])
            print(f"    {year:>6s}  {len(yr):>6d}  {np.sum(yr):>7.1f}  {np.mean(yr):>7.3f}")

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    print("""
  Key questions to answer:
  1. Does regime-based sizing improve total R without blowing up DD?
  2. Are Fridays weak in ALL regimes, or just high-VIX?
  3. Is morning weakness a VIX artifact?

  Decision: Use regime data for SIZING (not filtering) if it improves R
  without increasing DD beyond -6R.
""")


if __name__ == "__main__":
    main()
