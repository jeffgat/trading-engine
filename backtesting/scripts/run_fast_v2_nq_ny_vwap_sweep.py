#!/usr/bin/env python3
"""FAST_V2 NQ_NY VWAP context sweep.

Sweeps:
- VWAP slope lookback
- Minimum same-side distance from VWAP at the signal bar

The config source is the merged live FAST_V2 NQ_NY leg:
execution main defaults + FAST_V2 profile overrides.

Distance is measured as % of daily ATR:
  long  -> close >= vwap + (pct/100) * ATR
  short -> close <= vwap - (pct/100) * ATR

Slope rule:
  long  -> vwap[s] > vwap[s-lookback]
  short -> vwap[s] < vwap[s-lookback]

lookback=0 disables the slope filter.
distance_pct=0 disables the distance filter.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "execution" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.signals.daily_atr import compute_daily_atr

from run_fast_v2_nq_context_filters import build_fast_v2_legs, build_leg_context

FULL_START = "2016-01-01"
RECENT_START = "2024-01-01"

LOOKBACKS = (0, 1, 2, 3, 4, 6, 8)
DIST_PCTS = (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 45.0)


def filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    out = [t for t in trades if start <= t.date <= end]
    out.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    return out


def gate_vwap_context(
    trades: list[TradeResult],
    close: np.ndarray,
    vwap: np.ndarray,
    atr: np.ndarray,
    lookback: int,
    distance_pct: float,
) -> list[TradeResult]:
    kept: list[TradeResult] = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        s = t.signal_bar
        if s < 0 or s >= len(close):
            continue
        if np.isnan(close[s]) or np.isnan(vwap[s]):
            continue

        dist_ok = True
        if distance_pct > 0:
            if np.isnan(atr[s]):
                continue
            threshold = (distance_pct / 100.0) * atr[s]
            if t.direction == 1:
                dist_ok = close[s] >= vwap[s] + threshold
            else:
                dist_ok = close[s] <= vwap[s] - threshold
        else:
            if t.direction == 1:
                dist_ok = close[s] > vwap[s]
            else:
                dist_ok = close[s] < vwap[s]

        slope_ok = True
        if lookback > 0:
            if s < lookback or np.isnan(vwap[s - lookback]):
                continue
            if t.direction == 1:
                slope_ok = vwap[s] > vwap[s - lookback]
            else:
                slope_ok = vwap[s] < vwap[s - lookback]

        if dist_ok and slope_ok:
            kept.append(t)
    return kept


def _print_baseline(label: str, trades: list[TradeResult], start: str, end: str) -> dict:
    window = filter_window(trades, start, end)
    m = compute_metrics(window)
    print(
        f"{label}: {m['total_trades']} tr | WR {m['win_rate']:.1%} | "
        f"R {m['total_r']:.1f} | Sharpe {m['sharpe_ratio']:.2f} | Calmar {m['calmar_ratio']:.2f}"
    )
    return m


def main() -> None:
    parser = argparse.ArgumentParser(description="FAST_V2 NQ_NY VWAP sweep")
    parser.add_argument("--end", default="2025-12-31", help="Backtest end date")
    args = parser.parse_args()

    t0 = time.time()
    print("FAST_V2 NQ_NY VWAP Sweep")
    print("=" * 80)

    legs = build_fast_v2_legs()
    leg = legs["NQ_NY"]
    print(f"Leg: {leg.name} | symbol={leg.symbol} | strategy={leg.strategy}")

    print("\nLoading NQ data...")
    df_5m = load_5m_data("NQ_5m.parquet", start=FULL_START, end=args.end)
    df_1m = load_1m_for_5m("NQ_5m.parquet", start=FULL_START, end=args.end)
    print(f"  5m={len(df_5m):,}, 1m={len(df_1m):,}")

    print("\nRunning baseline backtest...")
    trades = run_backtest(df_5m, leg.config, start_date=FULL_START, end_date=args.end, df_1m=df_1m)
    if leg.excluded_dow:
        trades = apply_dow_filter(trades, set(leg.excluded_dow))
    trades = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    trades.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    print(f"  baseline fills={len(trades)}")

    ctx = build_leg_context(df_5m, leg.session)
    atr = compute_daily_atr(df_5m, length=leg.config.atr_length)

    # Signal-bar same-side distance from VWAP as % ATR
    dist_pcts = []
    for t in trades:
        s = t.signal_bar
        if s < 0 or s >= len(ctx.close) or np.isnan(ctx.vwap[s]) or np.isnan(atr[s]) or atr[s] <= 0:
            continue
        diff = (ctx.close[s] - ctx.vwap[s]) * (1 if t.direction == 1 else -1)
        dist_pcts.append((diff / atr[s]) * 100.0)
    dist_arr = np.array(dist_pcts, dtype=float)

    print("\nBaseline windows")
    m_full = _print_baseline("  full  ", trades, FULL_START, args.end)
    m_recent = _print_baseline("  recent", trades, RECENT_START, args.end)

    if len(dist_arr) > 0:
        print("\nSignal-bar same-side VWAP distance (% ATR)")
        for p in (5, 25, 50, 75, 90, 95):
            print(f"  p{p:>2}: {np.percentile(dist_arr, p):>6.2f}")

    results = []
    print("\nSweeping lookback x distance...")
    for lookback in LOOKBACKS:
        for dist_pct in DIST_PCTS:
            gated = gate_vwap_context(trades, ctx.close, ctx.vwap, atr, lookback, dist_pct)
            full_trades = filter_window(gated, FULL_START, args.end)
            recent_trades = filter_window(gated, RECENT_START, args.end)
            mf = compute_metrics(full_trades)
            mr = compute_metrics(recent_trades)
            results.append({
                "lookback": lookback,
                "dist_pct": dist_pct,
                "full_trades": mf["total_trades"],
                "full_wr": mf["win_rate"],
                "full_r": mf["total_r"],
                "full_sharpe": mf["sharpe_ratio"],
                "full_calmar": mf["calmar_ratio"],
                "recent_trades": mr["total_trades"],
                "recent_wr": mr["win_rate"],
                "recent_r": mr["total_r"],
                "recent_sharpe": mr["sharpe_ratio"],
                "recent_calmar": mr["calmar_ratio"],
                "delta_full_r": mf["total_r"] - m_full["total_r"],
                "delta_recent_r": mr["total_r"] - m_recent["total_r"],
            })

    stable = [
        r for r in results
        if r["delta_full_r"] > 0
        and r["delta_recent_r"] > 0
        and r["full_trades"] >= 0.70 * m_full["total_trades"]
        and r["recent_trades"] >= 0.70 * m_recent["total_trades"]
    ]
    stable.sort(key=lambda r: (r["delta_full_r"] + r["delta_recent_r"], r["full_calmar"]), reverse=True)

    by_full = sorted(results, key=lambda r: (r["delta_full_r"], r["full_calmar"]), reverse=True)
    by_recent = sorted(results, key=lambda r: (r["delta_recent_r"], r["recent_calmar"]), reverse=True)

    def _print_rows(title: str, rows: list[dict]) -> None:
        print(f"\n{title}")
        print("-" * len(title))
        print("  lb  dist% | full_tr  full_R  dR_full  Cal_full | recent_tr  recent_R  dR_recent  Cal_recent")
        for r in rows[:10]:
            print(
                f"  {r['lookback']:>2}  {r['dist_pct']:>5.1f} | "
                f"{r['full_trades']:>7} {r['full_r']:>7.1f} {r['delta_full_r']:>+8.1f} {r['full_calmar']:>9.2f} | "
                f"{r['recent_trades']:>9} {r['recent_r']:>8.1f} {r['delta_recent_r']:>+10.1f} {r['recent_calmar']:>11.2f}"
            )

    _print_rows("Top By Full-History Delta R", by_full)
    _print_rows("Top By Recent Delta R", by_recent)
    _print_rows("Top Stable Candidates", stable)

    print(f"\nDone in {(time.time() - t0) / 60:.1f} minutes")


if __name__ == "__main__":
    main()
