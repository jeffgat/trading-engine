#!/usr/bin/env python3
"""Walk-forward validation — v9 regime-sized GC inversion longs (standalone).

Identical WF framework as the stacked strategy (36m IS, 12m OOS, 12m step)
but runs v9 regime-sized alone — no clean air signal. Provides the proper
apples-to-apples baseline for comparing vs the stacked strategy.

Fixed params: QM=10%, stop=9%, rr=3.5, tp1=0.2, BE=0, entry→15:00, longs.
Regime sizing: 2x when VIX<18 AND DXY<SMA50 (prior day close).
"""

import sys
import time
from collections import defaultdict
from datetime import datetime
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

GC        = get_instrument("GC")
DATA_DIR  = Path(__file__).resolve().parent.parent / "data" / "raw"
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED  = ("20241218",)
START     = "2016-01-01"
IS_MONTHS = 36
OOS_MONTHS= 12
STEP_MONTHS=12
WARMUP    = 90


# ── Regime lookup ──────────────────────────────────────────────────────────────

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
            "vix":       float(vix_c.loc[ts])   if ts in vix_c.index else np.nan,
            "dxy":       float(dxy_c.loc[ts])   if ts in dxy_c.index else np.nan,
            "dxy_sma50": float(sma50.loc[ts])   if ts in sma50.index and not np.isnan(sma50.loc[ts]) else np.nan,
        }
    sd = sorted(lookup)
    return {d: lookup[sd[i-1]] if i > 0 else {"vix": np.nan, "dxy": np.nan, "dxy_sma50": np.nan}
            for i, d in enumerate(sd)}


def is_favorable(r):
    if r is None:
        return False
    v, d, s = r.get("vix", np.nan), r.get("dxy", np.nan), r.get("dxy_sma50", np.nan)
    return not any(np.isnan(x) for x in [v, d, s]) and v < 18 and d < s


def apply_regime(trades, regime):
    sized = []
    for t in trades:
        mult = 2.0 if is_favorable(regime.get(t.date)) else 1.0
        sized.append(t._replace(r_multiple=t.r_multiple * mult,
                                 pnl_usd=t.pnl_usd * mult))
    return sized


# ── Config ────────────────────────────────────────────────────────────────────

def v9_config():
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=9.0, min_gap_atr_pct=1.0,
        max_gap_points=25.0, qualifying_move_atr_pct=10.0,
    )
    return StrategyConfig(
        rr=3.5, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(sess,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True, half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )


# ── Window generation ─────────────────────────────────────────────────────────

def generate_windows(start: str, end: str):
    windows = []
    cur = datetime.strptime(start, "%Y-%m-%d")
    data_end = datetime.strptime(end, "%Y-%m-%d")
    is_off  = pd.DateOffset(months=IS_MONTHS)
    oos_off = pd.DateOffset(months=OOS_MONTHS)
    step    = pd.DateOffset(months=STEP_MONTHS)
    while True:
        is_e  = cur + is_off
        oos_s = is_e
        oos_e = oos_s + oos_off
        if oos_e > data_end:
            break
        windows.append((cur.strftime("%Y-%m-%d"), is_e.strftime("%Y-%m-%d"),
                        oos_s.strftime("%Y-%m-%d"), oos_e.strftime("%Y-%m-%d")))
        cur += step
    return windows


def warmup_start(date_str):
    return (datetime.strptime(date_str, "%Y-%m-%d") -
            pd.Timedelta(days=WARMUP)).strftime("%Y-%m-%d")


# ── Fold ──────────────────────────────────────────────────────────────────────

def run_fold(df, df_1m, regime, cfg, is_s, is_e, oos_s, oos_e):
    # IS (no param to sweep — v9 is fixed)
    is_df   = df.loc[warmup_start(is_s): is_e]
    is_1m   = df_1m.loc[warmup_start(is_s): is_e] if df_1m is not None else None
    is_all  = run_backtest_qm(is_df, cfg, start_date=is_s, df_1m=is_1m)
    is_trades = apply_regime(
        [t for t in is_all if t.exit_type != EXIT_NO_FILL and is_s <= t.date < is_e],
        regime)
    is_m = compute_metrics(is_trades) if len(is_trades) >= 3 else {}

    # OOS
    oos_df  = df.loc[warmup_start(oos_s): oos_e]
    oos_1m  = df_1m.loc[warmup_start(oos_s): oos_e] if df_1m is not None else None
    oos_all = run_backtest_qm(oos_df, cfg, start_date=oos_s, df_1m=oos_1m)
    oos_trades = apply_regime(
        [t for t in oos_all if t.exit_type != EXIT_NO_FILL and oos_s <= t.date < oos_e],
        regime)
    oos_m = compute_metrics(oos_trades) if len(oos_trades) >= 3 else {}

    return is_m, oos_trades, oos_m


def main():
    print("Loading data...")
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    regime = build_regime_lookup()
    cfg    = v9_config()

    windows = generate_windows(START, df.index[-1].strftime("%Y-%m-%d"))
    print(f"Walk-forward: {len(windows)} folds  "
          f"(IS={IS_MONTHS}m, OOS={OOS_MONTHS}m, step={STEP_MONTHS}m)\n")

    all_oos, fold_data = [], []
    t0 = time.time()

    for i, (is_s, is_e, oos_s, oos_e) in enumerate(windows):
        print(f"  Fold {i+1}/{len(windows)}: IS {is_s}→{is_e}  OOS {oos_s}→{oos_e}", end="  ")
        is_m, oos_trades, oos_m = run_fold(df, df_1m, regime, cfg, is_s, is_e, oos_s, oos_e)
        all_oos.extend(oos_trades)
        print(f"OOS: {oos_m.get('total_trades',0)} trades  "
              f"{oos_m.get('total_r',0):+.1f}R  "
              f"Sharpe {oos_m.get('sharpe_ratio',0):.3f}")
        fold_data.append({
            "fold": i+1, "is_s": is_s, "is_e": is_e,
            "oos_s": oos_s, "oos_e": oos_e,
            "is_trades": is_m.get("total_trades", 0),
            "is_sharpe": round(is_m.get("sharpe_ratio", 0), 3),
            "oos_trades": oos_m.get("total_trades", 0),
            "oos_r":     round(oos_m.get("total_r", 0), 1),
            "oos_dd":    round(oos_m.get("max_drawdown_r", 0), 1),
            "oos_sharpe":round(oos_m.get("sharpe_ratio", 0), 3),
            "oos_wr":    oos_m.get("win_rate", 0),
        })

    elapsed = time.time() - t0
    all_oos.sort(key=lambda t: t.date)
    combined = compute_metrics(all_oos) if len(all_oos) >= 5 else {}

    print(f"\nCompleted in {elapsed:.0f}s\n")

    # ── Fold table ─────────────────────────────────────────────────────────
    print("=" * 110)
    print("v9 REGIME-SIZED — WALK-FORWARD (standalone baseline)")
    print("=" * 110)
    print(f"{'Fold':>4} | {'IS Period':<23} | {'OOS Period':<23} | "
          f"{'IS Tr':>5} | {'IS Sh':>6} | "
          f"{'OOS Tr':>6} | {'OOS R':>6} | {'OOS DD':>7} | {'OOS Sh':>7} | {'OOS WR':>6}")
    print("-" * 110)

    is_sharpes, oos_sharpes = [], []
    for f in fold_data:
        is_sharpes.append(f["is_sharpe"])
        if f["oos_trades"] > 0:
            oos_sharpes.append(f["oos_sharpe"])
        sign = "+" if f["oos_r"] >= 0 else ""
        print(f"{f['fold']:>4} | {f['is_s']} → {f['is_e']} | "
              f"{f['oos_s']} → {f['oos_e']} | "
              f"{f['is_trades']:>5} | {f['is_sharpe']:>6.3f} | "
              f"{f['oos_trades']:>6} | {sign}{f['oos_r']:>5.1f} | "
              f"{f['oos_dd']:>7.1f} | {f['oos_sharpe']:>7.3f} | {f['oos_wr']:>5.1%}")

    print("-" * 110)
    avg_is  = sum(is_sharpes)  / len(is_sharpes)  if is_sharpes  else 0
    avg_oos = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0
    wf_eff  = avg_oos / avg_is if avg_is != 0 else 0
    print(f"  Avg IS Sharpe: {avg_is:.3f}   Avg OOS Sharpe: {avg_oos:.3f}   "
          f"WF Efficiency: {wf_eff:.2f}")

    # ── Combined OOS ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("COMBINED OOS METRICS (v9 regime-sized alone)")
    print(f"{'='*60}")
    if combined:
        oos_yr = defaultdict(list); oos_mo = defaultdict(list)
        for t in all_oos:
            oos_yr[t.date[:4]].append(t.r_multiple)
            oos_mo[t.date[:7]].append(t.r_multiple)
        wm = min((sum(v) for v in oos_mo.values()), default=0)
        marker = " *** PROP VIABLE" if combined["max_drawdown_r"] >= -10.0 else ""
        print(f"  Trades:      {combined['total_trades']}  (~{combined['total_trades']/len(oos_yr):.0f}/yr)")
        print(f"  Win Rate:    {combined['win_rate']:.1%}")
        print(f"  Net R:       {combined['total_r']:.1f}")
        print(f"  Max DD:      {combined['max_drawdown_r']:.1f}R{marker}")
        print(f"  Sharpe:      {combined['sharpe_ratio']:.3f}")
        print(f"  PF:          {combined['profit_factor']:.2f}")
        print(f"  Worst Month: {wm:.1f}R")
        print(f"  MCL:         {combined['max_consecutive_losses']}")
        print(f"  WF Efficiency: {wf_eff:.2f}")
        print(f"\n  Yearly OOS:")
        for yr in sorted(oos_yr):
            r = sum(oos_yr[yr]); n = len(oos_yr[yr])
            print(f"    {yr}: {r:+.1f}R  ({n} trades)")

    # ── Hold-out ───────────────────────────────────────────────────────────
    holdout = [t for t in all_oos if t.date >= "2024-01-01"]
    if holdout:
        hm = compute_metrics(holdout)
        hy = defaultdict(list)
        for t in holdout: hy[t.date[:4]].append(t.r_multiple)
        print(f"\n{'='*60}")
        print("HOLD-OUT 2024-2025")
        print(f"{'='*60}")
        print(f"  Trades: {hm['total_trades']}  |  WR: {hm['win_rate']:.1%}  |  "
              f"Net R: {hm['total_r']:.1f}  |  DD: {hm['max_drawdown_r']:.1f}R  |  "
              f"Sharpe: {hm['sharpe_ratio']:.3f}")
        for yr in sorted(hy):
            print(f"    {yr}: {sum(hy[yr]):+.1f}R  ({len(hy[yr])} trades)")

    print(f"\n  Note: stacked WF (v9 + clean air) reference — "
          f"WF eff 1.13, OOS Sharpe 3.695, DD -10.0R, 229 trades")


if __name__ == "__main__":
    main()
