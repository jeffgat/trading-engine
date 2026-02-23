#!/usr/bin/env python3
"""Re-save GC regime-sized models with regime params in config dict.

Deletes old entries and creates new ones with regime_sizing, regime_rule,
and regime_multiplier keys so the frontend Variables Tested panel shows them.
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
from orb_backtest.results.export import results_to_dict, save_backtest_result, delete_backtest_result

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED = ("20241218",)
START = "2016-01-01"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def load_vix():
    vix = pd.read_csv(DATA_DIR / "VIX_daily.csv", index_col=0, parse_dates=True)
    return vix["Close"].dropna()


def load_dxy():
    dxy = pd.read_csv(DATA_DIR / "DXY_daily.csv", index_col=0, parse_dates=True)
    close = dxy["Close"].dropna()
    return close, close.rolling(50).mean()


def load_spy():
    spy = pd.read_csv(DATA_DIR / "SPY_daily.csv", index_col=0, parse_dates=True)
    close = spy["Close"].dropna()
    return close, close.rolling(20).mean()


def build_shifted_lookup(series_dict):
    """Build a prior-day lookup from named series."""
    all_dates = set()
    for s in series_dict.values():
        all_dates |= set(s.index.date)
    all_dates = sorted(all_dates)

    last = {k: np.nan for k in series_dict}
    raw = {}
    for d in all_dates:
        ts = pd.Timestamp(d)
        for k, s in series_dict.items():
            if ts in s.index:
                val = s.loc[ts]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                val = float(val)
                if not np.isnan(val):
                    last[k] = val
        raw[str(d)] = dict(last)

    shifted = {}
    sorted_dates = sorted(raw.keys())
    for i, d in enumerate(sorted_dates):
        shifted[d] = raw[sorted_dates[i - 1]] if i > 0 else {k: np.nan for k in last}
    return shifted


def build_base_config(name, notes):
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
        name=name,
        notes=notes,
    )


def apply_sizing(trades, env, favorable_fn):
    sized = []
    n_doubled = 0
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            sized.append(t)
            continue
        e = env.get(t.date)
        if e and favorable_fn(e):
            sized.append(t._replace(
                r_multiple=t.r_multiple * 2.0,
                pnl_usd=t.pnl_usd * 2.0,
                qty=t.qty * 2.0,
                half_qty=t.half_qty * 2.0,
            ))
            n_doubled += 1
        else:
            sized.append(t)
    return sized, n_doubled


def main():
    # Delete old entries
    old_ids = [
        "bt-gc-ny-inversion-longs-v9-regime-sized-go-82ece0",
        "bt-gc-ny-inversion-longs-v9-regime-sized-sp-a9afa8",
    ]
    for old_id in old_ids:
        if delete_backtest_result(old_id):
            print(f"Deleted: {old_id}")
        else:
            print(f"Not found (already deleted?): {old_id}")

    # Load data
    print("\nLoading macro data...")
    vix_close = load_vix()
    dxy_close, dxy_sma50 = load_dxy()
    spy_close, spy_sma20 = load_spy()

    env_dxy = build_shifted_lookup({"vix": vix_close, "dxy": dxy_close, "dxy_sma50": dxy_sma50})
    env_spy = build_shifted_lookup({"vix": vix_close, "spy": spy_close, "spy_sma20": spy_sma20})

    print("Loading GC data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")

    # ── Model 1: 2x VIX<18 + DXY<SMA50 ──────────────────────────────────

    print("\n--- Model 1: 2x VIX<18 + DXY<SMA50 ---")
    config1 = build_base_config(
        name="GC NY Inversion Longs v9 Regime-Sized GO",
        notes="v9 (10% QM) + regime-based sizing: 2x when VIX<18 AND DXY<SMA50 "
              "(prior day close), 1x otherwise. Favorable regime = calm markets + weak dollar.",
    )

    trades1 = run_backtest_qm(df, config1, start_date=START, df_1m=df_1m)
    sized1, n1 = apply_sizing(
        trades1, env_dxy,
        lambda e: e["vix"] < 18 and e["dxy"] < e["dxy_sma50"],
    )
    print(f"  {n1} doubled, {len([t for t in sized1 if t.exit_type != EXIT_NO_FILL]) - n1} at 1x")

    result1 = results_to_dict(sized1, config1, include_trades=True, include_equity_curve=True)
    # Inject regime params into config
    result1["config"]["regime_sizing"] = "ON"
    result1["config"]["regime_rule"] = "VIX<18 + DXY<SMA50"
    result1["config"]["regime_multiplier"] = "2x favorable, 1x default"

    rid1 = save_backtest_result(result1)
    m1 = result1["summary"]
    print(f"  Saved: {rid1}")
    print(f"  {m1['total_trades']} trades, {m1['win_rate']:.1%} WR, {m1['total_r']:.1f}R, DD {m1['max_drawdown_r']:.1f}")

    # ── Model 2: 2x VIX<18 + SPY>SMA20 ──────────────────────────────────

    print("\n--- Model 2: 2x VIX<18 + SPY>SMA20 ---")
    config2 = build_base_config(
        name="GC NY Inversion Longs v9 Regime-Sized SPY",
        notes="v9 (10% QM) + regime-based sizing: 2x when VIX<18 AND SPY>SMA20 "
              "(prior day close), 1x otherwise. Favorable regime = calm VIX + risk-on equities.",
    )

    trades2 = run_backtest_qm(df, config2, start_date=START, df_1m=df_1m)
    sized2, n2 = apply_sizing(
        trades2, env_spy,
        lambda e: e["vix"] < 18 and e["spy"] > e["spy_sma20"],
    )
    print(f"  {n2} doubled, {len([t for t in sized2 if t.exit_type != EXIT_NO_FILL]) - n2} at 1x")

    result2 = results_to_dict(sized2, config2, include_trades=True, include_equity_curve=True)
    result2["config"]["regime_sizing"] = "ON"
    result2["config"]["regime_rule"] = "VIX<18 + SPY>SMA20"
    result2["config"]["regime_multiplier"] = "2x favorable, 1x default"

    rid2 = save_backtest_result(result2)
    m2 = result2["summary"]
    print(f"  Saved: {rid2}")
    print(f"  {m2['total_trades']} trades, {m2['win_rate']:.1%} WR, {m2['total_r']:.1f}R, DD {m2['max_drawdown_r']:.1f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
