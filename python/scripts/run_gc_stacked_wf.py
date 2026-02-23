#!/usr/bin/env python3
"""Walk-forward validation — stacked GC strategy.

Combines two signals into one asset strategy:
  A) v9 regime-sized: ORB-anchored inversion, QM=10%, 2x when VIX<18+DXY<SMA50
  B) Clean-air no-ORB: 100% ATR sweep with no prior bullish FVG zone below (N days)

v9 params are fixed (already validated). Per fold: sweep N (1,2,3,5) on IS,
apply best N to OOS. Combine both signal OOS trades, dedup same-day (v9 wins).

Rolling WF: 36m IS, 12m OOS, 12m step from 2016 onward.
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
from orb_backtest.engine.qualifying_move import run_backtest_no_orb, run_backtest_qm
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
N_VALUES  = [1, 2, 3, 5]
WARMUP    = 90


# ── Regime lookup ─────────────────────────────────────────────────────────────

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
    if r is None: return False
    v, d, s = r.get("vix", np.nan), r.get("dxy", np.nan), r.get("dxy_sma50", np.nan)
    return not any(np.isnan(x) for x in [v, d, s]) and v < 18 and d < s


# ── Signal configs ────────────────────────────────────────────────────────────

def v9_config():
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=9.0, min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=3.5, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50, min_qty=1.0, qty_step=1.0,
        sessions=(sess,), instrument=GC, strategy="inversion",
        direction_filter="long", use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
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
        atr_length=50, min_qty=1.0, qty_step=1.0,
        sessions=(sess,), instrument=GC, strategy="inversion",
        direction_filter="long", use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )


# ── FVG / session helpers ─────────────────────────────────────────────────────

def build_bullish_fvgs(df):
    high  = df["high"].values; low = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values
    h2 = np.roll(high, 2); h1 = np.roll(high, 1); l2 = np.roll(low, 2)
    bull = (h2 < low) & (h2 < h1) & (l2 < low); bull[:2] = False
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


def apply_clean_air(trades, fvg_by_date, session_lows, n):
    sd  = sorted(fvg_by_date.keys())
    idx = {d: i for i, d in enumerate(sd)}
    kept = []
    for t in trades:
        sl = session_lows.get(t.date, float("inf"))
        i  = idx.get(t.date, -1)
        if i < 0: continue
        prior = []
        for pd_ in sd[max(0, i-n): i]: prior.extend(fvg_by_date.get(pd_, []))
        if not prior or all(sl > top for (_, top) in prior): kept.append(t)
    return kept


def apply_regime(trades, regime):
    sized = []
    for t in trades:
        mult = 2.0 if is_favorable(regime.get(t.date)) else 1.0
        sized.append(t._replace(r_multiple=t.r_multiple * mult,
                                  pnl_usd=t.pnl_usd * mult))
    return sized


def dedup_combine(v9_trades, ca_trades):
    """Merge two trade lists; on same date, keep v9 (already validated)."""
    v9_dates = {t.date for t in v9_trades}
    ca_dedup  = [t for t in ca_trades if t.date not in v9_dates]
    return sorted(v9_trades + ca_dedup, key=lambda t: t.date)


# ── Walk-forward ─────────────────────────────────────────────────────────────

def generate_windows(start, end):
    windows, cur = [], datetime.strptime(start, "%Y-%m-%d")
    data_end = datetime.strptime(end, "%Y-%m-%d")
    while True:
        is_e  = cur  + pd.DateOffset(months=IS_MONTHS)
        oos_s = is_e
        oos_e = oos_s + pd.DateOffset(months=OOS_MONTHS)
        if oos_e > data_end: break
        windows.append((cur.strftime("%Y-%m-%d"), is_e.strftime("%Y-%m-%d"),
                        oos_s.strftime("%Y-%m-%d"), oos_e.strftime("%Y-%m-%d")))
        cur += pd.DateOffset(months=STEP_MONTHS)
    return windows


def run_fold(df, df_1m, fvg_by_date, session_lows, regime,
             cfg_v9, cfg_ca, is_s, is_e, oos_s, oos_e):
    def warmup_start(d):
        return (datetime.strptime(d, "%Y-%m-%d") -
                pd.Timedelta(days=WARMUP)).strftime("%Y-%m-%d")

    # ── IS: run both signals, sweep N for clean air ───────────────────────
    is_df    = df.loc[warmup_start(is_s): is_e]
    is_1m    = df_1m.loc[warmup_start(is_s): is_e] if df_1m is not None else None

    # v9 IS trades (fixed params)
    v9_is_all = run_backtest_qm(is_df, cfg_v9, start_date=is_s, df_1m=is_1m)
    v9_is = apply_regime(
        [t for t in v9_is_all if t.exit_type != EXIT_NO_FILL and is_s <= t.date < is_e],
        regime)

    # clean air IS: sweep N
    ca_is_all = run_backtest_no_orb(is_df, cfg_ca, start_date=is_s, df_1m=is_1m)
    ca_is_filled = [t for t in ca_is_all
                    if t.exit_type != EXIT_NO_FILL and is_s <= t.date < is_e]

    best_n = N_VALUES[0]; best_sharpe = float("-inf")
    for n in N_VALUES:
        ca_filt = apply_clean_air(ca_is_filled, fvg_by_date, session_lows, n)
        combined_is = dedup_combine(v9_is, ca_filt)
        if len(combined_is) < 5: continue
        m = compute_metrics(combined_is)
        if m["sharpe_ratio"] > best_sharpe:
            best_sharpe = m["sharpe_ratio"]
            best_n = n

    is_combined = dedup_combine(
        v9_is,
        apply_clean_air(ca_is_filled, fvg_by_date, session_lows, best_n)
    )
    is_m = compute_metrics(is_combined) if is_combined else {}

    # ── OOS: apply best N ────────────────────────────────────────────────
    oos_df   = df.loc[warmup_start(oos_s): oos_e]
    oos_1m   = df_1m.loc[warmup_start(oos_s): oos_e] if df_1m is not None else None

    v9_oos_all = run_backtest_qm(oos_df, cfg_v9, start_date=oos_s, df_1m=oos_1m)
    v9_oos = apply_regime(
        [t for t in v9_oos_all if t.exit_type != EXIT_NO_FILL and oos_s <= t.date < oos_e],
        regime)

    ca_oos_all = run_backtest_no_orb(oos_df, cfg_ca, start_date=oos_s, df_1m=oos_1m)
    ca_oos = apply_clean_air(
        [t for t in ca_oos_all if t.exit_type != EXIT_NO_FILL and oos_s <= t.date < oos_e],
        fvg_by_date, session_lows, best_n)

    oos_combined = dedup_combine(v9_oos, ca_oos)
    oos_m = compute_metrics(oos_combined) if len(oos_combined) >= 3 else {}

    return best_n, best_sharpe, is_m, oos_combined, oos_m


def main():
    print("Loading data...")
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    regime       = build_regime_lookup()
    fvg_by_date  = build_bullish_fvgs(df)
    session_lows = build_session_lows(df)

    cfg_v9 = v9_config()
    cfg_ca = clean_air_config()

    windows = generate_windows(START, df.index[-1].strftime("%Y-%m-%d"))
    print(f"Walk-forward: {len(windows)} folds  (IS={IS_MONTHS}m, OOS={OOS_MONTHS}m)\n")

    all_oos, fold_data = [], []
    t0 = time.time()

    for i, (is_s, is_e, oos_s, oos_e) in enumerate(windows):
        print(f"  Fold {i+1}/{len(windows)}: IS {is_s}→{is_e}  OOS {oos_s}→{oos_e}", end="  ")
        best_n, is_sh, is_m, oos_trades, oos_m = run_fold(
            df, df_1m, fvg_by_date, session_lows, regime,
            cfg_v9, cfg_ca, is_s, is_e, oos_s, oos_e)
        all_oos.extend(oos_trades)

        v9_cnt = sum(1 for t in oos_trades if abs(t.r_multiple) <= 3.6)  # v9 max win ~3.5R
        ca_cnt = len(oos_trades) - v9_cnt
        print(f"N={best_n}  OOS: {oos_m.get('total_trades',0)} trades "
              f"({len([t for t in oos_trades])} total)  "
              f"{oos_m.get('total_r',0):+.1f}R  "
              f"Sharpe {oos_m.get('sharpe_ratio',0):.3f}")
        fold_data.append({"fold": i+1, "is_s": is_s, "is_e": is_e,
                          "oos_s": oos_s, "oos_e": oos_e,
                          "best_n": best_n, "is_sharpe": round(is_sh, 3),
                          "is_trades": is_m.get("total_trades", 0),
                          "oos_trades": oos_m.get("total_trades", 0),
                          "oos_r": round(oos_m.get("total_r", 0), 1),
                          "oos_dd": round(oos_m.get("max_drawdown_r", 0), 1),
                          "oos_sharpe": round(oos_m.get("sharpe_ratio", 0), 3),
                          "oos_wr": oos_m.get("win_rate", 0)})

    all_oos.sort(key=lambda t: t.date)
    combined = compute_metrics(all_oos) if len(all_oos) >= 5 else {}
    elapsed = time.time() - t0

    print(f"\nCompleted in {elapsed:.0f}s\n")

    # ── Fold table ────────────────────────────────────────────────────────
    print("=" * 115)
    print("STACKED GC STRATEGY — WALK-FORWARD (v9 Regime-Sized + Clean Air No-ORB)")
    print("=" * 115)
    print(f"{'Fold':>4} | {'IS Period':<23} | {'OOS Period':<23} | "
          f"{'N':>2} | {'IS Tr':>5} | {'IS Sh':>6} | "
          f"{'OOS Tr':>6} | {'OOS R':>6} | {'OOS DD':>7} | {'OOS Sh':>7} | {'OOS WR':>6}")
    print("-" * 115)

    is_sharpes, oos_sharpes = [], []
    for f in fold_data:
        is_sharpes.append(f["is_sharpe"])
        if f["oos_trades"] > 0: oos_sharpes.append(f["oos_sharpe"])
        sign = "+" if f["oos_r"] >= 0 else ""
        print(f"{f['fold']:>4} | {f['is_s']} → {f['is_e']} | "
              f"{f['oos_s']} → {f['oos_e']} | "
              f"{f['best_n']:>2} | {f['is_trades']:>5} | {f['is_sharpe']:>6.3f} | "
              f"{f['oos_trades']:>6} | {sign}{f['oos_r']:>5.1f} | "
              f"{f['oos_dd']:>7.1f} | {f['oos_sharpe']:>7.3f} | {f['oos_wr']:>5.1%}")

    print("-" * 115)
    avg_is  = sum(is_sharpes)  / len(is_sharpes)  if is_sharpes  else 0
    avg_oos = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0
    wf_eff  = avg_oos / avg_is if avg_is != 0 else 0
    print(f"  Avg IS Sharpe: {avg_is:.3f}   Avg OOS Sharpe: {avg_oos:.3f}   "
          f"WF Efficiency: {wf_eff:.2f}")

    # ── N stability ───────────────────────────────────────────────────────
    n_counts = defaultdict(int)
    for f in fold_data: n_counts[f["best_n"]] += 1
    print(f"\n  Best N per fold: " +
          "  ".join(f"N={n}: {c}/{len(fold_data)}" for n, c in sorted(n_counts.items())))

    # ── Combined OOS ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("COMBINED OOS — STACKED STRATEGY")
    print(f"{'='*70}")
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

    # ── Hold-out comparison ───────────────────────────────────────────────
    holdout = [t for t in all_oos if t.date >= "2024-01-01"]
    if holdout:
        hm = compute_metrics(holdout)
        hy = defaultdict(list)
        for t in holdout: hy[t.date[:4]].append(t.r_multiple)
        print(f"\n{'='*70}")
        print("HOLD-OUT 2024-2025")
        print(f"{'='*70}")
        print(f"  Trades: {hm['total_trades']}  |  WR: {hm['win_rate']:.1%}  |  "
              f"Net R: {hm['total_r']:.1f}  |  DD: {hm['max_drawdown_r']:.1f}R  |  "
              f"Sharpe: {hm['sharpe_ratio']:.3f}")
        for yr in sorted(hy):
            print(f"    {yr}: {sum(hy[yr]):+.1f}R  ({len(hy[yr])} trades)")

    # ── Comparison ────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("COMPARISON vs v9 ALONE (OOS reference)")
    print(f"{'='*70}")
    print(f"  v9 regime-sized WF (alone): WF eff 1.21, OOS Sharpe 3.314, DD -7.3R, 169 trades")
    print(f"  Stacked WF (v9 + clean air): WF eff {wf_eff:.2f}, "
          f"OOS Sharpe {combined.get('sharpe_ratio', 0):.3f}, "
          f"DD {combined.get('max_drawdown_r', 0):.1f}R, "
          f"{combined.get('total_trades', 0)} trades")


if __name__ == "__main__":
    main()
