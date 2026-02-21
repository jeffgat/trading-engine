#!/usr/bin/env python3
"""Save GC Inversion Longs v9 with SPY regime sizing to experiments DB.

Model: 2x size when VIX < 18 AND SPY > SMA20 (prior day), 1x otherwise.
Result: 135.0R total, -8.3R DD.
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
from orb_backtest.results.export import results_to_dict, save_backtest_result

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED = ("20241218",)
START = "2016-01-01"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def build_env_lookup():
    """Build date → env dict using prior day's close (no look-ahead)."""
    vix = pd.read_csv(DATA_DIR / "VIX_daily.csv", index_col=0, parse_dates=True)
    spy = pd.read_csv(DATA_DIR / "SPY_daily.csv", index_col=0, parse_dates=True)

    vix_close = vix["Close"].dropna()
    spy_close = spy["Close"].dropna()
    spy_sma20 = spy_close.rolling(20).mean()

    all_dates = sorted(set(vix_close.index.date) | set(spy_close.index.date))

    last = {"vix": np.nan, "spy": np.nan, "spy_sma20": np.nan}
    raw = {}
    for d in all_dates:
        ts = pd.Timestamp(d)
        if ts in vix_close.index:
            last["vix"] = float(vix_close.loc[ts])
        if ts in spy_close.index:
            last["spy"] = float(spy_close.loc[ts])
        if ts in spy_sma20.index and not np.isnan(spy_sma20.loc[ts]):
            last["spy_sma20"] = float(spy_sma20.loc[ts])
        raw[str(d)] = dict(last)

    shifted = {}
    sorted_dates = sorted(raw.keys())
    for i, d in enumerate(sorted_dates):
        shifted[d] = raw[sorted_dates[i - 1]] if i > 0 else {k: np.nan for k in last}
    return shifted


def is_favorable(env_dict):
    if env_dict is None:
        return False
    vix = env_dict.get("vix", np.nan)
    spy = env_dict.get("spy", np.nan)
    sma20 = env_dict.get("spy_sma20", np.nan)
    if np.isnan(vix) or np.isnan(spy) or np.isnan(sma20):
        return False
    return vix < 18 and spy > sma20


def main():
    print("Loading env data...")
    env = build_env_lookup()

    print("Loading GC data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")

    session = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=9.0, min_gap_atr_pct=1.0,
        max_gap_points=25.0, qualifying_move_atr_pct=10.0,
    )
    config = StrategyConfig(
        rr=3.5, tp1_ratio=0.2, risk_usd=5000.0, atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC, strategy="inversion",
        direction_filter="long", use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
        name="GC NY Inversion Longs v9 Regime-Sized SPY",
        notes="v9 (10% QM) + regime-based sizing: 2x when VIX<18 AND SPY>SMA20 "
              "(prior day close), 1x otherwise. 250 trades, 135.0R, -8.3R DD. "
              "Favorable regime = calm VIX + risk-on equities.",
    )

    print("Running backtest...")
    trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)

    sized_trades = []
    n_doubled = 0
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            sized_trades.append(t)
            continue
        e = env.get(t.date)
        if is_favorable(e):
            sized_trades.append(t._replace(
                r_multiple=t.r_multiple * 2.0,
                pnl_usd=t.pnl_usd * 2.0,
                qty=t.qty * 2.0,
                half_qty=t.half_qty * 2.0,
            ))
            n_doubled += 1
        else:
            sized_trades.append(t)

    print(f"  {n_doubled} trades doubled (VIX<18 + SPY>SMA20)")
    print(f"  {len([t for t in sized_trades if t.exit_type != EXIT_NO_FILL]) - n_doubled} trades at 1x")

    result = results_to_dict(sized_trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    m = result["summary"]
    print(f"\nSaved: {result_id}")
    print(f"Trades: {m['total_trades']}, WR: {m['win_rate']:.1%}, Net R: {m['total_r']:.1f}, DD: {m['max_drawdown_r']:.1f}")


if __name__ == "__main__":
    main()
