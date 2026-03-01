#!/usr/bin/env python3
"""NQ NY ORB — Drawdown depth/frequency analysis.

How often does the strategy hit various DD thresholds?
Critical for prop firm account sizing.

Config: g=3.0 rr=2.25 tp1=0.7 stop=9% long-only 20m ORB
"""

import sys
import time
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics


def make_config():
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=3.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.25,
        tp1_ratio=0.7,
        atr_length=14,
        name="NQ NY DD Analysis",
    )


def main():
    print("NQ NY ORB — Drawdown Depth & Frequency Analysis")
    print("Config: g=3.0 rr=2.25 tp1=0.7 stop=9% long-only 20m ORB")
    print("=" * 90)

    print("\nLoading data...", flush=True)
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")

    config = make_config()
    trades = run_backtest(df_5m, config, start_date="2015-01-01", df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    filled.sort(key=lambda t: t.date)

    m = compute_metrics(trades)
    print(f"\nBaseline: {m['total_trades']} trades, {m['total_r']:.1f}R, "
          f"DD {m['max_drawdown_r']:.1f}R, Calmar {m['calmar_ratio']:.2f}")

    # ── Build equity curve and DD series ──────────────────────────────────
    cumulative_r = 0.0
    peak_r = 0.0
    equity = []  # (date, cumulative_r, drawdown_r, peak_r)

    for t in filled:
        cumulative_r += t.r_multiple
        if cumulative_r > peak_r:
            peak_r = cumulative_r
        dd = cumulative_r - peak_r  # negative when in drawdown
        equity.append((t.date, cumulative_r, dd, peak_r))

    # ── Breach events at various thresholds ───────────────────────────────
    thresholds = [-4.0, -5.0, -6.0, -7.0, -8.0, -9.0, -10.0]

    print(f"\n{'='*90}")
    print(f"  DRAWDOWN BREACH EVENTS")
    print(f"{'='*90}")

    for thresh in thresholds:
        # Find distinct breach events (DD crosses below threshold)
        breaches = []
        in_breach = False
        breach_start = None
        breach_deepest = 0.0
        breach_deepest_date = None

        for date, cum_r, dd, pk in equity:
            if dd <= thresh and not in_breach:
                # New breach
                in_breach = True
                breach_start = date
                breach_deepest = dd
                breach_deepest_date = date
            elif dd <= thresh and in_breach:
                # Continuing breach — track deepest
                if dd < breach_deepest:
                    breach_deepest = dd
                    breach_deepest_date = date
            elif dd > thresh and in_breach:
                # Recovered from breach
                breaches.append((breach_start, date, breach_deepest, breach_deepest_date))
                in_breach = False

        # If still in breach at end
        if in_breach:
            breaches.append((breach_start, equity[-1][0], breach_deepest, breach_deepest_date))

        years = 11.0
        freq = len(breaches) / years

        print(f"\n  DD <= {thresh:.0f}R: {len(breaches)} events in 11 years ({freq:.1f}/year)")
        if breaches:
            print(f"  {'Start':<12s}  {'Recovery':<12s}  {'Deepest':>8s}  {'Deep Date':<12s}  {'Duration':>10s}")
            print(f"  {'─'*60}")
            for start, end, deep, deep_date in breaches:
                # Duration in trading days
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                end_dt = datetime.strptime(end, "%Y-%m-%d")
                days = (end_dt - start_dt).days
                print(f"  {start:<12s}  {end:<12s}  {deep:>+7.1f}R  {deep_date:<12s}  {days:>8d} days")

    # ── DD by year ────────────────────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  MAX DRAWDOWN BY YEAR")
    print(f"{'='*90}")
    print(f"\n  {'Year':<6s}  {'Max DD':>7s}  {'Trades':>7s}  {'Net R':>7s}  {'Worst Streak':>13s}")
    print(f"  {'─'*45}")

    # Group by year
    from collections import defaultdict
    year_trades = defaultdict(list)
    for t in filled:
        yr = int(t.date[:4])
        year_trades[yr].append(t)

    for yr in sorted(year_trades.keys()):
        yr_filled = year_trades[yr]
        cum = 0.0
        pk = 0.0
        max_dd = 0.0

        # Also compute worst losing streak
        streak = 0
        worst_streak = 0
        net_r = sum(t.r_multiple for t in yr_filled)

        for t in yr_filled:
            cum += t.r_multiple
            if cum > pk:
                pk = cum
            dd = cum - pk
            if dd < max_dd:
                max_dd = dd

            if t.r_multiple < 0:
                streak += 1
                worst_streak = max(worst_streak, streak)
            else:
                streak = 0

        print(f"  {yr:<6d}  {max_dd:>+6.1f}R  {len(yr_filled):>7d}  {net_r:>+6.1f}R  {worst_streak:>10d} losses")

    # ── Monthly DD distribution ───────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  MONTHLY P&L DISTRIBUTION")
    print(f"{'='*90}")

    monthly_r = defaultdict(float)
    for t in filled:
        month_key = t.date[:7]  # YYYY-MM
        monthly_r[month_key] += t.r_multiple

    months_sorted = sorted(monthly_r.keys())
    monthly_vals = [monthly_r[m] for m in months_sorted]

    # Stats
    import statistics
    neg_months = [v for v in monthly_vals if v < 0]
    pos_months = [v for v in monthly_vals if v >= 0]

    print(f"\n  Total months: {len(monthly_vals)}")
    print(f"  Positive: {len(pos_months)} ({len(pos_months)/len(monthly_vals)*100:.0f}%)")
    print(f"  Negative: {len(neg_months)} ({len(neg_months)/len(monthly_vals)*100:.0f}%)")
    print(f"  Mean monthly R: {statistics.mean(monthly_vals):+.2f}")
    print(f"  Median monthly R: {statistics.median(monthly_vals):+.2f}")
    print(f"  Std dev: {statistics.stdev(monthly_vals):.2f}")

    # Worst months
    worst_months = sorted(zip(months_sorted, [monthly_r[m] for m in months_sorted]),
                          key=lambda x: x[1])
    print(f"\n  WORST 15 MONTHS:")
    print(f"  {'Month':<10s}  {'R':>7s}")
    print(f"  {'─'*20}")
    for month, r in worst_months[:15]:
        print(f"  {month:<10s}  {r:>+6.1f}R")

    # Best months
    best_months = sorted(zip(months_sorted, [monthly_r[m] for m in months_sorted]),
                         key=lambda x: x[1], reverse=True)
    print(f"\n  BEST 10 MONTHS:")
    print(f"  {'Month':<10s}  {'R':>7s}")
    print(f"  {'─'*20}")
    for month, r in best_months[:10]:
        print(f"  {month:<10s}  {r:>+6.1f}R")

    # ── Consecutive losing trades ─────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  CONSECUTIVE LOSS ANALYSIS")
    print(f"{'='*90}")

    streak = 0
    streak_r = 0.0
    streaks = []  # (length, total_r, start_date, end_date)
    streak_start = None

    for t in filled:
        if t.r_multiple < 0:
            if streak == 0:
                streak_start = t.date
            streak += 1
            streak_r += t.r_multiple
        else:
            if streak > 0:
                streaks.append((streak, streak_r, streak_start, t.date))
            streak = 0
            streak_r = 0.0

    if streak > 0:
        streaks.append((streak, streak_r, streak_start, filled[-1].date))

    streaks.sort(key=lambda x: x[1])  # sort by total R lost

    print(f"\n  WORST 10 LOSING STREAKS (by R lost):")
    print(f"  {'Losses':>7s}  {'R Lost':>7s}  {'Start':<12s}  {'End':<12s}")
    print(f"  {'─'*45}")
    for length, total_r, start, end in streaks[:10]:
        print(f"  {length:>7d}  {total_r:>+6.1f}R  {start:<12s}  {end:<12s}")

    print(f"\n  Streak distribution:")
    from collections import Counter
    streak_counts = Counter(s[0] for s in streaks)
    for length in sorted(streak_counts.keys()):
        print(f"    {length} consecutive losses: {streak_counts[length]} times")

    print(f"\n{'='*90}")
    print(f"  ANALYSIS COMPLETE")
    print(f"{'='*90}")


if __name__ == "__main__":
    main()
