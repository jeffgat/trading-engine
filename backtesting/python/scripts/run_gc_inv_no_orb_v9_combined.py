#!/usr/bin/env python3
"""No-ORB GC — combine clean-air no-ORB trades with v9 regime-sized trades.

Stacks two independent signals on the same instrument:
  A) v9 regime-sized: ORB-anchored inversion, QM=10%, regime 2x sizing
  B) no-ORB clean air: 100% ATR sweep NOT into any prior bullish FVG (N=5 days)

Since each signal fires on different conditions, combined equity should have
better diversification and potentially lower DD per R than either alone.
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
from orb_backtest.engine.qualifying_move import run_backtest_no_orb, run_backtest_qm
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC       = get_instrument("GC")
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED  = ("20241218",)
START     = "2016-01-01"


# ── Regime lookup (for v9 sizing) ────────────────────────────────────────────

def build_regime_lookup():
    vix_df = pd.read_csv(DATA_DIR / "VIX_daily.csv", index_col=0, parse_dates=True)
    dxy_df = pd.read_csv(DATA_DIR / "DXY_daily.csv", index_col=0, parse_dates=True)
    vix_c  = vix_df["Close"].dropna()
    dxy_c  = dxy_df["Close"].dropna()
    sma50  = dxy_c.rolling(50).mean()

    lookup = {}
    for d in sorted(set(vix_c.index.date) | set(dxy_c.index.date)):
        ts = pd.Timestamp(d)
        lookup[str(d)] = {
            "vix":      float(vix_c.loc[ts])  if ts in vix_c.index else np.nan,
            "dxy":      float(dxy_c.loc[ts])  if ts in dxy_c.index else np.nan,
            "dxy_sma50":float(sma50.loc[ts])  if ts in sma50.index and not np.isnan(sma50.loc[ts]) else np.nan,
        }
    sd = sorted(lookup)
    return {d: lookup[sd[i-1]] if i > 0 else {"vix": np.nan, "dxy": np.nan, "dxy_sma50": np.nan}
            for i, d in enumerate(sd)}


def is_favorable(r):
    if r is None:
        return False
    v, d, s = r.get("vix", np.nan), r.get("dxy", np.nan), r.get("dxy_sma50", np.nan)
    return not any(np.isnan(x) for x in [v, d, s]) and v < 18 and d < s


# ── Prior FVG detection ───────────────────────────────────────────────────────

def build_bullish_fvgs(df: pd.DataFrame) -> dict[str, list]:
    high  = df["high"].values
    low   = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values
    h2 = np.roll(high, 2); h1 = np.roll(high, 1); l2 = np.roll(low, 2)
    bull = (h2 < low) & (h2 < h1) & (l2 < low)
    bull[:2] = False
    fvg: dict[str, list] = defaultdict(list)
    for i in np.where(bull)[0]:
        b, t = float(h2[i]), float(low[i])
        if b < t:
            fvg[dates[i]].append((b, t))
    return dict(fvg)


def build_session_lows(df: pd.DataFrame) -> dict[str, float]:
    mask = (df.index.time >= pd.Timestamp("09:30").time()) & \
           (df.index.time <= pd.Timestamp("16:45").time())
    s = df[mask].copy()
    s["ds"] = s.index.strftime("%Y-%m-%d")
    return s.groupby("ds")["low"].min().to_dict()


def clean_air_filter(trades, fvg_by_date, session_lows, lookback=5):
    sorted_dates = sorted(fvg_by_date.keys())
    date_to_idx  = {d: i for i, d in enumerate(sorted_dates)}
    kept = []
    for t in trades:
        sess_low = session_lows.get(t.date, float("inf"))
        idx = date_to_idx.get(t.date, -1)
        if idx < 0:
            continue
        prior = []
        for pd_ in sorted_dates[max(0, idx - lookback): idx]:
            prior.extend(fvg_by_date.get(pd_, []))
        if not prior or all(sess_low > top for (_, top) in prior):
            kept.append(t)
    return kept


# ── Run each model ────────────────────────────────────────────────────────────

def run_v9(df, df_1m, regime):
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=9.0, min_gap_atr_pct=1.0,
        max_gap_points=25.0, qualifying_move_atr_pct=10.0,
    )
    cfg = StrategyConfig(
        rr=3.5, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(sess,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True, half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )
    trades = run_backtest_qm(df, cfg, start_date=START, df_1m=df_1m)
    sized = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        mult = 2.0 if is_favorable(regime.get(t.date)) else 1.0
        sized.append(t._replace(r_multiple=t.r_multiple * mult,
                                 pnl_usd=t.pnl_usd * mult))
    return sized


def run_no_orb_clean(df, df_1m, fvg_by_date, session_lows, lookback=5):
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="16:45",
        flat_start="16:45", flat_end="16:50",
        stop_atr_pct=12.0, min_gap_atr_pct=1.0,
        max_gap_points=25.0, qualifying_move_atr_pct=100.0,
    )
    cfg = StrategyConfig(
        rr=5.0, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(sess,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True, half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )
    trades = run_backtest_no_orb(df, cfg, start_date=START, df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    return clean_air_filter(filled, fvg_by_date, session_lows, lookback)


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_model(label, trades):
    if len(trades) < 5:
        print(f"  {label}: insufficient trades")
        return
    m = compute_metrics(trades)
    yearly  = defaultdict(list)
    monthly = defaultdict(list)
    for t in trades:
        yearly[t.date[:4]].append(t.r_multiple)
        monthly[t.date[:7]].append(t.r_multiple)
    wm = min((sum(v) for v in monthly.values()), default=0)
    dd = round(m["max_drawdown_r"], 1)
    nr = round(m["total_r"], 1)
    marker = " ***" if dd >= -10.0 else ""

    print(f"\n{'─'*70}")
    print(f"  {label}")
    print(f"{'─'*70}")
    print(f"  Trades: {m['total_trades']}  (~{m['total_trades']/len(yearly):.0f}/yr)  |  "
          f"WR: {m['win_rate']:.1%}  |  Net R: {nr}  |  Max DD: {dd}R{marker}")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f}  |  PF: {m['profit_factor']:.2f}  |  "
          f"Worst month: {wm:.1f}R  |  MCL: {m['max_consecutive_losses']}")
    print(f"  Yearly:")
    for yr in sorted(yearly):
        print(f"    {yr}: {sum(yearly[yr]):+.1f}R  ({len(yearly[yr])} trades)")


def check_overlap(v9_trades, no_orb_trades):
    v9_dates   = {t.date for t in v9_trades}
    norb_dates = {t.date for t in no_orb_trades}
    overlap    = v9_dates & norb_dates
    print(f"\n  Overlap check: {len(overlap)} dates have trades in both signals "
          f"({len(overlap)/max(len(v9_dates),1):.1%} of v9 dates)")
    return overlap


def main():
    print("Loading data...")
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    regime       = build_regime_lookup()
    fvg_by_date  = build_bullish_fvgs(df)
    session_lows = build_session_lows(df)

    t0 = time.time()
    print("Running v9 regime-sized...")
    v9 = run_v9(df, df_1m, regime)
    print(f"  {len(v9)} trades")

    print("Running no-ORB clean air (N=5)...")
    no_orb = run_no_orb_clean(df, df_1m, fvg_by_date, session_lows, lookback=5)
    print(f"  {len(no_orb)} trades  ({time.time()-t0:.0f}s total)\n")

    # Combined: merge + sort by date
    combined = sorted(v9 + no_orb, key=lambda t: t.date)

    print("=" * 70)
    print("GC INVERSION LONGS — SIGNAL COMBINATION")
    print("=" * 70)

    print_model("A) v9 Regime-Sized alone", v9)
    print_model("B) No-ORB Clean Air alone (N=5)", no_orb)

    overlap = check_overlap(v9, no_orb)

    # Handle same-day overlap: if both fire on same date, only keep the first (by entry_price proxy)
    # For simplicity: remove no-ORB trades on days v9 already traded
    v9_dates    = {t.date for t in v9}
    no_orb_dedup = [t for t in no_orb if t.date not in v9_dates]
    combined_dedup = sorted(v9 + no_orb_dedup, key=lambda t: t.date)

    print_model("C) Combined (v9 + no-ORB, dedup: v9 wins on overlap)", combined_dedup)
    print_model("D) Combined (all, allow same-day dual signals)", combined)

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    for label, trades in [
        ("v9 Regime-Sized", v9),
        ("No-ORB Clean Air", no_orb),
        ("Combined (dedup)",  combined_dedup),
    ]:
        if len(trades) < 5:
            continue
        m  = compute_metrics(trades)
        yr = defaultdict(list)
        for t in trades:
            yr[t.date[:4]].append(t.r_multiple)
        monthly = defaultdict(list)
        for t in trades:
            monthly[t.date[:7]].append(t.r_multiple)
        wm = min((sum(v) for v in monthly.values()), default=0)
        print(f"  {label:<28} | {m['total_trades']:>4} trades | "
              f"WR {m['win_rate']:>5.1%} | {m['total_r']:>7.1f}R | "
              f"DD {m['max_drawdown_r']:>6.1f}R | "
              f"Sharpe {m['sharpe_ratio']:>6.3f} | WM {wm:>5.1f}R")

    print(f"\n  v9 baseline (no sizing): 250 trades, 74.7R, -5.2R DD, Sharpe 3.80")


if __name__ == "__main__":
    main()
