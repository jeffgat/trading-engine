#!/usr/bin/env python3
"""Save GC NY Inv Longs v9 Regime-Sized no BE offset to main DB.

Config: v9 (QM=10% confirmed optimal) + regime sizing (2x when VIX<18 AND
DXY<SMA50, prior day close). BE stop moves to exact entry.
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


def build_regime_lookup():
    vix_df = pd.read_csv(DATA_DIR / "VIX_daily.csv", index_col=0, parse_dates=True)
    dxy_df = pd.read_csv(DATA_DIR / "DXY_daily.csv", index_col=0, parse_dates=True)

    vix_close = vix_df["Close"].dropna()
    dxy_close = dxy_df["Close"].dropna()
    dxy_sma50 = dxy_close.rolling(50).mean()

    lookup = {}
    all_dates = sorted(set(vix_close.index.date) | set(dxy_close.index.date))

    last_vix = np.nan
    last_dxy = np.nan
    last_dxy_sma50 = np.nan

    for d in all_dates:
        ts = pd.Timestamp(d)
        if ts in vix_close.index:
            last_vix = float(vix_close.loc[ts])
        if ts in dxy_close.index:
            last_dxy = float(dxy_close.loc[ts])
        if ts in dxy_sma50.index and not np.isnan(dxy_sma50.loc[ts]):
            last_dxy_sma50 = float(dxy_sma50.loc[ts])
        lookup[str(d)] = {"vix": last_vix, "dxy": last_dxy, "dxy_sma50": last_dxy_sma50}

    # Shift: trade on date D uses macro data from D-1
    sorted_dates = sorted(lookup.keys())
    shifted = {}
    for i, d in enumerate(sorted_dates):
        shifted[d] = lookup[sorted_dates[i - 1]] if i > 0 else {"vix": np.nan, "dxy": np.nan, "dxy_sma50": np.nan}

    return shifted


def is_favorable(r):
    if r is None:
        return False
    vix, dxy, sma50 = r.get("vix", np.nan), r.get("dxy", np.nan), r.get("dxy_sma50", np.nan)
    return not (np.isnan(vix) or np.isnan(dxy) or np.isnan(sma50)) and vix < 18 and dxy < sma50


def main():
    print("Loading macro data...")
    regime = build_regime_lookup()

    print("Loading GC data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")

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

    config = StrategyConfig(
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
        name="GC NY Inv Longs v9 Regime-Sized no BE offset",
        notes="v9 (QM=10% confirmed optimal via 0-30% sweep) + regime sizing "
              "(2x when VIX<18 AND DXY<SMA50, prior day close). "
              "BE stop moves to exact entry.",
    )

    print("Running backtest...")
    trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)

    sized_trades = []
    n_doubled = 0
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            sized_trades.append(t)
            continue
        if is_favorable(regime.get(t.date)):
            sized_trades.append(t._replace(
                r_multiple=t.r_multiple * 2.0,
                pnl_usd=t.pnl_usd * 2.0,
                qty=t.qty * 2.0,
                half_qty=t.half_qty * 2.0,
            ))
            n_doubled += 1
        else:
            sized_trades.append(t)

    filled = [t for t in sized_trades if t.exit_type != EXIT_NO_FILL]
    print(f"  {n_doubled}/{len(filled)} trades doubled (favorable regime)")

    result = results_to_dict(sized_trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    m = result["summary"]
    print(f"\nSaved: {result_id}")
    print(f"Trades: {m['total_trades']}, WR: {m['win_rate']:.1%}, Net R: {m['total_r']:.1f}, "
          f"DD: {m['max_drawdown_r']:.1f}, Sharpe: {m['sharpe_ratio']:.3f}")


if __name__ == "__main__":
    main()
