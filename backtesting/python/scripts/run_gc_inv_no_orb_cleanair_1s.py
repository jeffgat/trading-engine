#!/usr/bin/env python3
"""Re-validate GC no-ORB clean air inversions with clean 1s magnifier data.

Prior test (2026-02-20) used 1m magnifier only and showed NO-GO (-281.6R
unfiltered, -28.9R best clean air). This re-test uses the clean 1s data
(available 2026-02-21) via hierarchical 5m→1m→1s magnifier to validate
whether higher-resolution fill/exit changes the result.

Strategy: No-ORB liquidity sweep inversion (longs only)
- No ORB anchor — qualifying sweep measured from session extremes
- QM=100% ATR (price must fall 100% of daily ATR from session high)
- Then enter LONG on bearish FVG inversion (close > FVG top)
- Clean air filter: session low must NOT dip into any prior bullish FVG zone

Fixed: QM=100%, stop=12%, rr=5.0, BE=0, tp1=0.2, entry→16:45, longs.
Sweep: clean air lookback N = 1, 2, 3, 5, 10, 20 days + unfiltered base.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED = ()  # No excluded dates for first pass — evaluate raw signal


def make_config():
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="16:45",
        flat_start="16:45", flat_end="16:50",
        stop_atr_pct=12.0, min_gap_atr_pct=1.0,
        max_gap_points=25.0, qualifying_move_atr_pct=100.0,
    )
    return StrategyConfig(
        rr=5.0, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )


def build_bullish_fvgs(df: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    """Bullish FVGs per date: zone = (bottom=high[2], top=low[0])."""
    high = df["high"].values
    low = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values

    high_2 = np.roll(high, 2)
    high_1 = np.roll(high, 1)
    low_2 = np.roll(low, 2)

    bull = (high_2 < low) & (high_2 < high_1) & (low_2 < low)
    bull[:2] = False

    fvg_by_date: dict[str, list] = defaultdict(list)
    for i in np.where(bull)[0]:
        bottom, top = float(high_2[i]), float(low[i])
        if bottom < top:
            fvg_by_date[dates[i]].append((bottom, top))
    return dict(fvg_by_date)


def build_session_lows(df: pd.DataFrame) -> dict[str, float]:
    mask = (df.index.time >= pd.Timestamp("09:30").time()) & \
           (df.index.time <= pd.Timestamp("16:45").time())
    s = df[mask].copy()
    s["ds"] = s.index.strftime("%Y-%m-%d")
    return s.groupby("ds")["low"].min().to_dict()


def clean_air_filter(filled, fvg_by_date, session_lows, lookback):
    """Keep trades where session_low is ABOVE all prior FVG zones (clean air)."""
    sorted_dates = sorted(fvg_by_date.keys())
    date_to_idx = {d: i for i, d in enumerate(sorted_dates)}

    kept = []
    for t in filled:
        sess_low = session_lows.get(t.date, float("inf"))
        idx = date_to_idx.get(t.date, -1)
        if idx < 0:
            continue

        prior_zones = []
        for past_d in sorted_dates[max(0, idx - lookback): idx]:
            prior_zones.extend(fvg_by_date.get(past_d, []))

        if not prior_zones or all(sess_low > fvg_top for (_, fvg_top) in prior_zones):
            kept.append(t)

    return kept


def stats(trades):
    if len(trades) < 5:
        return None
    m = compute_metrics(trades)
    monthly = defaultdict(list)
    yearly = defaultdict(list)
    for t in trades:
        monthly[t.date[:7]].append(t.r_multiple)
        yearly[t.date[:4]].append(t.r_multiple)
    wm = min((sum(v) for v in monthly.values()), default=0)
    nr = m["total_r"]
    dd = m["max_drawdown_r"]
    calmar = round(abs(nr / len(yearly)) / abs(dd), 2) if dd < 0 else 999
    return {
        **m,
        "worst_month": round(wm, 1),
        "calmar": calmar,
        "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
        "trades_per_year": len(trades) / max(len(yearly), 1),
        "neg_years": sum(1 for v in yearly.values() if sum(v) < 0),
    }


def main():
    print("=" * 110)
    print("GC NO-ORB CLEAN AIR INVERSIONS — RE-VALIDATION ON CLEAN 1s DATA")
    print("=" * 110)
    print("Config: QM=100%, stop=12%, rr=5.0, tp1=0.2, ATR 50, entry→16:45, longs only")
    print("Magnifier: hierarchical 5m→1m→1s")
    print()

    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    bars_1m = f"{len(df_1m):,} 1m" if df_1m is not None else "no 1m"
    bars_1s = f"{len(df_1s):,} 1s" if df_1s is not None else "no 1s"
    print(f"Loaded {len(df):,} 5m bars, {bars_1m} bars, {bars_1s} bars\n")

    fvg_by_date = build_bullish_fvgs(df)
    session_lows = build_session_lows(df)

    t0 = time.time()
    trades = run_backtest_no_orb(df, make_config(), start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    elapsed = time.time() - t0
    print(f"Base (unfiltered): {len(filled)} filled trades  ({elapsed:.0f}s)\n")

    # Unfiltered base metrics
    base_m = stats(filled)
    if base_m:
        dd = round(base_m["max_drawdown_r"], 1)
        nr = round(base_m["total_r"], 1)
        print(f"  Unfiltered: {len(filled)} trades, {base_m['win_rate']:.1%} WR, "
              f"{nr:.1f}R net, {dd:.1f}R DD, Calmar {base_m['calmar']}, "
              f"Sharpe {base_m['sharpe_ratio']:.3f}, {base_m['neg_years']} neg years")
    print()

    # Clean air sweep
    print("=" * 120)
    print("CLEAN AIR FILTER — vary lookback N")
    print("  Keeps trades where session low stays ABOVE all prior bullish FVG zones (N-day lookback)")
    print("=" * 120)
    print(f"  {'N':>4} | {'Trades':>6} | {'T/yr':>5} | {'WR':>6} | {'Net R':>7} | "
          f"{'Max DD':>7} | {'Calmar':>7} | {'Sharpe':>7} | {'PF':>5} | "
          f"{'WM':>6} | {'MCL':>4} | {'Neg Yr':>6}")
    print("-" * 120)

    results = {}
    for n in [1, 2, 3, 5, 10, 20]:
        kept = clean_air_filter(filled, fvg_by_date, session_lows, n)
        m = stats(kept)
        if m is None:
            print(f"  N={n:>2}: insufficient trades (<5)")
            continue
        results[n] = (kept, m)
        dd = round(m["max_drawdown_r"], 1)
        nr = round(m["total_r"], 1)
        print(f"  N={n:>2} | {len(kept):>6} | {m['trades_per_year']:>5.1f} | "
              f"{m['win_rate']:>5.1%} | {nr:>7.1f} | {dd:>7.1f} | "
              f"{m['calmar']:>7.2f} | {m['sharpe_ratio']:>7.3f} | "
              f"{m['profit_factor']:>5.2f} | {m['worst_month']:>6.1f} | "
              f"{m['max_consecutive_losses']:>4} | {m['neg_years']:>6}")

    # Yearly breakdown
    print(f"\n{'='*110}")
    print("YEARLY BREAKDOWN PER LOOKBACK")
    print(f"{'='*110}")
    years = sorted({t.date[:4] for t in filled})
    header = f"{'Year':<6}" + "".join(f"  N={n:>2}      " for n in results)
    print(header)
    print("-" * len(header))
    for yr in years:
        row = f"{yr:<6}"
        for n, (kept, m) in results.items():
            val = m["yearly"].get(yr, 0)
            cnt = sum(1 for t in kept if t.date[:4] == yr)
            row += f"  {val:>+6.1f}({cnt:>3})"
        print(row)

    # Exit type breakdown for best N
    if results:
        best_n = max(results, key=lambda n: results[n][1]["calmar"])
        best_trades, best_m = results[best_n]
        print(f"\n{'='*80}")
        print(f"EXIT TYPE BREAKDOWN — N={best_n} (best Calmar)")
        print(f"{'='*80}")
        from orb_backtest.engine.simulator import EXIT_NAMES
        exit_counts = defaultdict(int)
        for t in best_trades:
            exit_counts[EXIT_NAMES.get(t.exit_type, f"type_{t.exit_type}")] += 1
        for ename, cnt in sorted(exit_counts.items(), key=lambda x: -x[1]):
            print(f"  {ename:<20}: {cnt:>4} ({cnt/len(best_trades):>5.1%})")

    # Compare to continuation longs baseline
    print(f"\n{'='*80}")
    print("REFERENCE COMPARISON")
    print(f"{'='*80}")
    print(f"  GC Cont Longs R6:  561 trades, 39.6% WR, 158.0R, -11.2R DD, Calmar 14.10, Sharpe 2.570")
    print(f"  Prior 1m-only unf: -281.6R (2026-02-20, 1m magnifier)")
    print(f"  Prior 1m-only N=1:  -28.9R best clean air (2026-02-20, 1m magnifier)")
    if results and 1 in results:
        _, m1 = results[1]
        dd1 = round(m1["max_drawdown_r"], 1)
        nr1 = round(m1["total_r"], 1)
        print(f"  New clean air N=1: {sum(1 for _ in results[1][0])} trades, "
              f"{m1['win_rate']:.1%} WR, {nr1:.1f}R, {dd1:.1f}R DD, "
              f"Calmar {m1['calmar']}, Sharpe {m1['sharpe_ratio']:.3f}")


if __name__ == "__main__":
    main()
