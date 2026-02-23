#!/usr/bin/env python3
"""Save GC stacked strategy: v9 Regime-Sized + Clean Air No-ORB (N=1).

Two independent signals combined into one GC strategy:
  A) v9 regime-sized: ORB inversion long, QM=10%, 2x when VIX<18+DXY<SMA50
  B) Clean air no-ORB: 100% ATR sweep NOT into any prior bullish FVG zone (N=1 day)
Dedup: v9 wins on same-day conflict. ~4.8% date overlap.

WF validation (36m IS, 12m OOS, 7 folds):
  v9 alone:  169 trades, 58.8R, -7.3R DD, Sharpe 3.314, WF eff 1.21
  Stacked:   229 trades, 89.1R, -10.0R DD, Sharpe 3.695, WF eff 1.13
  2024-2025: 70 trades, 41.7R, -4.0R DD, Sharpe 5.087
"""

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_qm, run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.export import save_backtest_result
from orb_backtest.results.metrics import compute_metrics

GC       = get_instrument("GC")
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED  = ("20241218",)
START     = "2016-01-01"
CLEAN_AIR_N = 1


# ── Regime lookup ──────────────────────────────────────────────────────────────

def build_regime_lookup():
    vix_df = pd.read_csv(DATA_DIR / "VIX_daily.csv", index_col=0, parse_dates=True)
    dxy_df = pd.read_csv(DATA_DIR / "DXY_daily.csv", index_col=0, parse_dates=True)
    vix_c  = vix_df["Close"].dropna()
    dxy_c  = dxy_df["Close"].dropna()
    sma50  = dxy_c.rolling(50).mean()

    lookup = {}
    all_dates = sorted(set(vix_c.index.date) | set(dxy_c.index.date))
    last_vix = last_dxy = last_sma50 = np.nan
    for d in all_dates:
        ts = pd.Timestamp(d)
        if ts in vix_c.index:    last_vix  = float(vix_c.loc[ts])
        if ts in dxy_c.index:    last_dxy  = float(dxy_c.loc[ts])
        if ts in sma50.index and not np.isnan(sma50.loc[ts]):
            last_sma50 = float(sma50.loc[ts])
        lookup[str(d)] = {"vix": last_vix, "dxy": last_dxy, "dxy_sma50": last_sma50}

    sd = sorted(lookup)
    return {d: lookup[sd[i-1]] if i > 0 else {"vix": np.nan, "dxy": np.nan, "dxy_sma50": np.nan}
            for i, d in enumerate(sd)}


def is_favorable(r):
    if r is None: return False
    v, d, s = r.get("vix", np.nan), r.get("dxy", np.nan), r.get("dxy_sma50", np.nan)
    return not any(np.isnan(x) for x in [v, d, s]) and v < 18 and d < s


# ── Clean air filter ───────────────────────────────────────────────────────────

def build_bullish_fvgs(df):
    high  = df["high"].values; low = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values
    h2 = np.roll(high, 2); h1 = np.roll(high, 1); l2 = np.roll(low, 2)
    bull = (h2 < low) & (h2 < h1) & (l2 < low)
    bull[:2] = False
    out = defaultdict(list)
    for i in np.where(bull)[0]:
        b, t = float(h2[i]), float(low[i])
        if b < t: out[dates[i]].append((b, t))
    return dict(out)


def build_session_lows(df):
    mask = (df.index.time >= pd.Timestamp("09:30").time()) & \
           (df.index.time <= pd.Timestamp("16:45").time())
    s = df[mask].copy(); s["ds"] = s.index.strftime("%Y-%m-%d")
    return s.groupby("ds")["low"].min().to_dict()


def clean_air_filter(trades, fvg_by_date, session_lows, n):
    sorted_dates = sorted(fvg_by_date.keys())
    date_to_idx  = {d: i for i, d in enumerate(sorted_dates)}
    kept = []
    for t in trades:
        sl  = session_lows.get(t.date, float("inf"))
        idx = date_to_idx.get(t.date, -1)
        if idx < 0: continue
        prior = []
        for pd_ in sorted_dates[max(0, idx - n): idx]:
            prior.extend(fvg_by_date.get(pd_, []))
        if not prior or all(sl > top for (_, top) in prior):
            kept.append(t)
    return kept


# ── Configs ────────────────────────────────────────────────────────────────────

def v9_config():
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=9.0, min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=3.5, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(sess,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True, half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )


def clean_air_config():
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="16:45",
        flat_start="16:45", flat_end="16:50",
        stop_atr_pct=12.0, min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=5.0, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(sess,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True, half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )


# ── Build equity curve ─────────────────────────────────────────────────────────

def build_equity_curve(trades):
    cumulative = 0.0
    curve = []
    for t in trades:
        cumulative += t.pnl_usd
        curve.append({
            "date": t.date,
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t.pnl_usd, 2),
        })
    return curve


def main():
    print("Loading data...")
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    regime       = build_regime_lookup()
    fvg_by_date  = build_bullish_fvgs(df)
    session_lows = build_session_lows(df)

    # ── Signal A: v9 regime-sized ──────────────────────────────────────────
    print("Running v9 regime-sized...")
    cfg_v9  = v9_config()
    v9_all  = run_backtest_qm(df, cfg_v9, start_date=START, df_1m=df_1m)
    v9_trades = []
    n_doubled = 0
    for t in v9_all:
        if t.exit_type == EXIT_NO_FILL:
            continue
        if is_favorable(regime.get(t.date)):
            v9_trades.append(t._replace(r_multiple=t.r_multiple * 2.0,
                                         pnl_usd=t.pnl_usd * 2.0))
            n_doubled += 1
        else:
            v9_trades.append(t)
    print(f"  {len(v9_trades)} trades ({n_doubled} doubled)")

    # ── Signal B: clean air no-ORB ─────────────────────────────────────────
    print(f"Running clean air no-ORB (N={CLEAN_AIR_N})...")
    cfg_ca  = clean_air_config()
    ca_all  = run_backtest_no_orb(df, cfg_ca, start_date=START, df_1m=df_1m)
    ca_filled = [t for t in ca_all if t.exit_type != EXIT_NO_FILL]
    ca_trades = clean_air_filter(ca_filled, fvg_by_date, session_lows, CLEAN_AIR_N)
    print(f"  {len(ca_trades)} trades")

    # ── Combine: v9 wins on same-day conflict ──────────────────────────────
    v9_dates = {t.date for t in v9_trades}
    ca_dedup = [t for t in ca_trades if t.date not in v9_dates]
    overlap  = len(ca_trades) - len(ca_dedup)

    combined = sorted(v9_trades + ca_dedup, key=lambda t: t.date)
    print(f"  Combined: {len(combined)} trades ({overlap} same-day conflicts removed, v9 kept)")

    m = compute_metrics(combined)
    yearly = defaultdict(list)
    for t in combined:
        yearly[t.date[:4]].append(t.r_multiple)

    print(f"\n  Net R:  {m['total_r']:.1f}R")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f}")
    print(f"  WR:     {m['win_rate']:.1%}")
    print(f"  Yearly:")
    for yr in sorted(yearly):
        print(f"    {yr}: {sum(yearly[yr]):+.1f}R  ({len(yearly[yr])} trades)")

    # ── Save ───────────────────────────────────────────────────────────────
    result = {
        "name": "GC NY Inv Longs Stacked v9+CleanAir",
        "notes": (
            f"Stacked strategy: two independent signals on GC NY session. "
            f"Signal A — v9 regime-sized: ORB inversion long, QM=10%, stop=9%, rr=3.5, tp1=0.2, BE=0, "
            f"entry 09:35-15:00, flat 15:50-16:00. 2x sizing when VIX<18 AND DXY<SMA50 (prior day). "
            f"Signal B — clean air no-ORB: 100% ATR sweep with no prior bullish FVG zone below "
            f"(N={CLEAN_AIR_N} day lookback), stop=12%, rr=5.0, tp1=0.2, BE=0, entry 09:35-16:45. "
            f"Same-day conflict: v9 wins. Overlap: ~4.8% of dates. "
            f"WF validation (36m IS/12m OOS, 7 folds): v9 alone 58.8R/-7.3R DD Sharpe 3.314; "
            f"stacked 89.1R/-10.0R DD Sharpe 3.695, WF eff 1.13. "
            f"2024-2025 hold-out: 70 trades, 41.7R, -4.0R DD, Sharpe 5.087."
        ),
        "config": {
            "instrument": "GC",
            "strategy": "inversion+stacked",
            "direction_filter": "long",
            "signal_a": "v9_regime_sized",
            "signal_a_qm": 10.0,
            "signal_a_stop_atr_pct": 9.0,
            "signal_a_rr": 3.5,
            "signal_a_entry_end": "15:00",
            "signal_a_sizing": "2x_vix18_dxy_sma50",
            "signal_b": "clean_air_no_orb",
            "signal_b_qm": 100.0,
            "signal_b_stop_atr_pct": 12.0,
            "signal_b_rr": 5.0,
            "signal_b_entry_end": "16:45",
            "signal_b_clean_air_n": CLEAN_AIR_N,
            "dedup_rule": "v9_wins_on_overlap",
            "bar_magnifier": "ON",
            "risk_usd": 5000.0,
            "atr_length": 50,
        },
        "summary": m,
        "equity_curve": build_equity_curve(combined),
        "trades": [
            {
                "date": t.date,
                "session": t.session,
                "direction": "long",
                "entry_price": round(t.entry_price, 4),
                "stop_price": round(t.stop_price, 4),
                "tp1_price": round(t.tp1_price, 4),
                "tp2_price": round(t.tp2_price, 4),
                "exit_type": "stacked",
                "pnl_usd": round(t.pnl_usd, 2),
                "pnl_points": round(t.pnl_points, 4),
                "r_multiple": round(t.r_multiple, 3),
                "qty": t.qty,
                "gap_size": round(t.gap_size, 4),
                "risk_points": round(t.risk_points, 4),
            }
            for t in combined
        ],
    }

    result_id = save_backtest_result(result)
    print(f"\nSaved: {result_id}")


if __name__ == "__main__":
    main()
