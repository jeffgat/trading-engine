#!/usr/bin/env python3
"""Walk-forward validation — no-ORB GC clean air sweep signal.

Rolling WF: 36-month IS, 12-month OOS, 12-month step.
Each fold: sweep N lookback (1, 2, 3, 5 days), pick best by Sharpe.
Fixed: QM=100%, stop=12%, rr=5.0, BE=0, tp1=0.2, entry→16:45, longs.
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
from orb_backtest.engine.qualifying_move import run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC        = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED  = ("20241218",)
START     = "2016-01-01"
IS_MONTHS = 36
OOS_MONTHS= 12
STEP_MONTHS=12
N_VALUES  = [1, 2, 3, 5]
WARMUP_DAYS = 90


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_config():
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


def build_bullish_fvgs(df: pd.DataFrame) -> dict[str, list]:
    high  = df["high"].values
    low   = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values
    h2 = np.roll(high, 2); h1 = np.roll(high, 1); l2 = np.roll(low, 2)
    bull = (h2 < low) & (h2 < h1) & (l2 < low)
    bull[:2] = False
    out: dict[str, list] = defaultdict(list)
    for i in np.where(bull)[0]:
        b, t = float(h2[i]), float(low[i])
        if b < t:
            out[dates[i]].append((b, t))
    return dict(out)


def build_session_lows(df: pd.DataFrame) -> dict[str, float]:
    mask = (df.index.time >= pd.Timestamp("09:30").time()) & \
           (df.index.time <= pd.Timestamp("16:45").time())
    s = df[mask].copy()
    s["ds"] = s.index.strftime("%Y-%m-%d")
    return s.groupby("ds")["low"].min().to_dict()


def clean_air_filter(trades, fvg_by_date, session_lows, n):
    sorted_dates = sorted(fvg_by_date.keys())
    date_to_idx  = {d: i for i, d in enumerate(sorted_dates)}
    kept = []
    for t in trades:
        sl  = session_lows.get(t.date, float("inf"))
        idx = date_to_idx.get(t.date, -1)
        if idx < 0:
            continue
        prior = []
        for pd_ in sorted_dates[max(0, idx - n): idx]:
            prior.extend(fvg_by_date.get(pd_, []))
        if not prior or all(sl > top for (_, top) in prior):
            kept.append(t)
    return kept


def generate_windows(start: str, end: str):
    """Generate rolling IS/OOS windows."""
    windows = []
    is_s = datetime.strptime(start, "%Y-%m-%d")
    data_end = datetime.strptime(end, "%Y-%m-%d")
    step = pd.DateOffset(months=STEP_MONTHS)
    is_offset  = pd.DateOffset(months=IS_MONTHS)
    oos_offset = pd.DateOffset(months=OOS_MONTHS)

    cur = is_s
    while True:
        is_e   = cur + is_offset
        oos_s  = is_e
        oos_e  = oos_s + oos_offset
        if oos_e > data_end:
            break
        windows.append((
            cur.strftime("%Y-%m-%d"),
            is_e.strftime("%Y-%m-%d"),
            oos_s.strftime("%Y-%m-%d"),
            oos_e.strftime("%Y-%m-%d"),
        ))
        cur += step
    return windows


def run_fold(df, df_1m, fvg_by_date, session_lows, cfg,
             is_start, is_end, oos_start, oos_end):
    """Run one WF fold: sweep N on IS, apply best to OOS."""
    warmup = (datetime.strptime(is_start, "%Y-%m-%d") -
              pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")

    # IS sweep
    is_df    = df.loc[warmup: is_end]
    is_df_1m = df_1m.loc[warmup: is_end] if df_1m is not None else None
    is_all   = run_backtest_no_orb(is_df, cfg, start_date=is_start, df_1m=is_df_1m)
    is_filled = [t for t in is_all
                 if t.exit_type != EXIT_NO_FILL and is_start <= t.date < is_end]

    best_n      = N_VALUES[0]
    best_sharpe = float("-inf")
    best_is_m   = {}
    is_results  = {}

    for n in N_VALUES:
        kept = clean_air_filter(is_filled, fvg_by_date, session_lows, n)
        if len(kept) < 5:
            continue
        m = compute_metrics(kept)
        is_results[n] = (kept, m)
        if m["sharpe_ratio"] > best_sharpe:
            best_sharpe = m["sharpe_ratio"]
            best_n      = n
            best_is_m   = m

    # OOS test with best N
    oos_warmup = (datetime.strptime(oos_start, "%Y-%m-%d") -
                  pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    oos_df    = df.loc[oos_warmup: oos_end]
    oos_df_1m = df_1m.loc[oos_warmup: oos_end] if df_1m is not None else None
    oos_all   = run_backtest_no_orb(oos_df, cfg, start_date=oos_start, df_1m=oos_df_1m)
    oos_filled = [t for t in oos_all
                  if t.exit_type != EXIT_NO_FILL and oos_start <= t.date < oos_end]
    oos_kept  = clean_air_filter(oos_filled, fvg_by_date, session_lows, best_n)
    oos_m     = compute_metrics(oos_kept) if len(oos_kept) >= 3 else {}

    return best_n, best_sharpe, best_is_m, oos_kept, oos_m, is_results


def main():
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    print("Building FVG lookup and session lows (full history)...")
    fvg_by_date  = build_bullish_fvgs(df)
    session_lows = build_session_lows(df)
    cfg          = make_config()

    windows = generate_windows(START, df.index[-1].strftime("%Y-%m-%d"))
    print(f"Walk-forward: {len(windows)} folds  "
          f"(IS={IS_MONTHS}m, OOS={OOS_MONTHS}m, step={STEP_MONTHS}m)\n")

    all_oos_trades = []
    fold_data      = []
    t0 = time.time()

    for i, (is_s, is_e, oos_s, oos_e) in enumerate(windows):
        print(f"  Fold {i+1}/{len(windows)}: IS {is_s}→{is_e}  OOS {oos_s}→{oos_e}", end="  ")
        best_n, is_sharpe, is_m, oos_trades, oos_m, is_results = run_fold(
            df, df_1m, fvg_by_date, session_lows, cfg,
            is_s, is_e, oos_s, oos_e
        )
        all_oos_trades.extend(oos_trades)
        fold_data.append({
            "fold": i + 1, "is_s": is_s, "is_e": is_e,
            "oos_s": oos_s, "oos_e": oos_e,
            "best_n": best_n,
            "is_trades": is_m.get("total_trades", 0),
            "is_sharpe": round(is_m.get("sharpe_ratio", 0), 3),
            "is_wr":     is_m.get("win_rate", 0),
            "is_r":      round(is_m.get("total_r", 0), 1),
            "oos_trades":oos_m.get("total_trades", 0),
            "oos_sharpe":round(oos_m.get("sharpe_ratio", 0), 3),
            "oos_wr":    oos_m.get("win_rate", 0),
            "oos_r":     round(oos_m.get("total_r", 0), 1),
            "oos_dd":    round(oos_m.get("max_drawdown_r", 0), 1),
            "oos_trades_list": oos_trades,
        })
        oos_status = (f"N={best_n}  OOS: {oos_m.get('total_trades',0)} trades  "
                      f"{oos_m.get('total_r',0):.1f}R  "
                      f"Sharpe {oos_m.get('sharpe_ratio',0):.3f}")
        print(oos_status)

    elapsed = time.time() - t0

    # ── Combined OOS metrics ──────────────────────────────────────────────────
    all_oos_trades.sort(key=lambda t: t.date)
    combined = compute_metrics(all_oos_trades) if len(all_oos_trades) >= 5 else {}

    print(f"\nCompleted in {elapsed:.0f}s\n")

    # ── Fold table ────────────────────────────────────────────────────────────
    print("=" * 115)
    print("NO-ORB CLEAN AIR — WALK-FORWARD RESULTS")
    print("=" * 115)
    hdr = (f"{'Fold':>4} | {'IS Period':<23} | {'OOS Period':<23} | "
           f"{'N':>2} | {'IS Tr':>5} | {'IS Sh':>6} | "
           f"{'OOS Tr':>6} | {'OOS R':>6} | {'OOS DD':>7} | {'OOS Sh':>7} | {'OOS WR':>6}")
    print(hdr)
    print("-" * 115)

    is_sharpes  = []
    oos_sharpes = []

    for f in fold_data:
        is_sharpes.append(f["is_sharpe"])
        if f["oos_trades"] > 0:
            oos_sharpes.append(f["oos_sharpe"])
        oos_pos = "+" if f["oos_r"] >= 0 else ""
        print(f"{f['fold']:>4} | {f['is_s']} → {f['is_e']} | "
              f"{f['oos_s']} → {f['oos_e']} | "
              f"{f['best_n']:>2} | {f['is_trades']:>5} | {f['is_sharpe']:>6.3f} | "
              f"{f['oos_trades']:>6} | {oos_pos}{f['oos_r']:>5.1f} | "
              f"{f['oos_dd']:>7.1f} | {f['oos_sharpe']:>7.3f} | {f['oos_wr']:>5.1%}")

    print("-" * 115)
    avg_is  = sum(is_sharpes)  / len(is_sharpes)  if is_sharpes  else 0
    avg_oos = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0
    wf_eff  = avg_oos / avg_is if avg_is != 0 else 0
    print(f"  Avg IS Sharpe: {avg_is:.3f}   Avg OOS Sharpe: {avg_oos:.3f}   "
          f"WF Efficiency: {wf_eff:.2f}")

    # ── N stability ───────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("BEST N PER FOLD (parameter stability)")
    print(f"{'='*60}")
    n_counts = defaultdict(int)
    for f in fold_data:
        n_counts[f["best_n"]] += 1
    for n, cnt in sorted(n_counts.items()):
        print(f"  N={n}: {cnt} folds ({cnt/len(fold_data):.0%})")

    # ── Combined OOS ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("COMBINED OOS METRICS (all folds concatenated)")
    print(f"{'='*60}")
    if combined:
        oos_yearly = defaultdict(list)
        oos_monthly = defaultdict(list)
        for t in all_oos_trades:
            oos_yearly[t.date[:4]].append(t.r_multiple)
            oos_monthly[t.date[:7]].append(t.r_multiple)
        wm = min((sum(v) for v in oos_monthly.values()), default=0)
        print(f"  Trades:      {combined['total_trades']}")
        print(f"  Win Rate:    {combined['win_rate']:.1%}")
        print(f"  Net R:       {combined['total_r']:.1f}")
        print(f"  Max DD:      {combined['max_drawdown_r']:.1f}R")
        print(f"  Sharpe:      {combined['sharpe_ratio']:.3f}")
        print(f"  PF:          {combined['profit_factor']:.2f}")
        print(f"  Worst Month: {wm:.1f}R")
        print(f"  MCL:         {combined['max_consecutive_losses']}")
        print(f"  WF Efficiency: {wf_eff:.2f}  (OOS/IS Sharpe ratio)")
        print(f"\n  Yearly OOS:")
        for yr in sorted(oos_yearly):
            r = sum(oos_yearly[yr])
            n = len(oos_yearly[yr])
            print(f"    {yr}: {r:+.1f}R  ({n} trades)")
    else:
        print("  Insufficient OOS trades for combined metrics.")

    # ── Hold-out comparison: 2024-2025 ───────────────────────────────────────
    holdout = [t for t in all_oos_trades if t.date >= "2024-01-01"]
    if holdout:
        hm = compute_metrics(holdout)
        print(f"\n{'='*60}")
        print("HOLD-OUT: 2024-2025 OOS performance")
        print(f"{'='*60}")
        print(f"  Trades: {hm['total_trades']}  |  WR: {hm['win_rate']:.1%}  |  "
              f"Net R: {hm['total_r']:.1f}  |  DD: {hm['max_drawdown_r']:.1f}R  |  "
              f"Sharpe: {hm['sharpe_ratio']:.3f}")

    print(f"\n  v9 WF OOS reference: WF efficiency 0.82, OOS Sharpe ~2.5, DD -4.0R")
    print(f"  Full-history (in-sample): 121 trades (N=1), 59.5R, -6.5R DD, Sharpe 4.978")


if __name__ == "__main__":
    main()
