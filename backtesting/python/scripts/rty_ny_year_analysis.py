#!/usr/bin/env python3
"""Quick analysis: why did RTY NY do so well in 2020, 2023, 2024?"""

import sys
from collections import defaultdict

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_SL, EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_EOD, EXIT_TP2_SINGLE
from orb_backtest.results.metrics import compute_metrics
RTY = get_instrument("RTY")

NY = SessionConfig(
    name="NY", orb_start="09:30", orb_end="09:45",
    entry_start="09:45", entry_end="15:30",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=3.0, min_gap_atr_pct=1.0,
)

CONFIG = StrategyConfig(
    rr=5.5, tp1_ratio=0.45, risk_usd=5000.0, atr_length=14,
    sessions=(NY,), instrument=RTY, strategy="continuation",
    direction_filter="long", use_bar_magnifier=True,
    impulse_close_filter=False, name="RTY NY Analysis",
)

EXIT_NAMES = {0: "NO_FILL", 1: "SL", 2: "TP1+TP2", 3: "TP1+BE", 4: "TP1+EOD", 5: "EOD", 6: "TP2_SINGLE"}

df = load_5m_data("RTY_5m.csv")
df_1m = load_1m_for_5m("RTY_5m.csv")
df_1s = load_1s_for_5m("RTY_5m.csv")

trades = run_backtest(df, CONFIG, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

# Group by year
by_year = defaultdict(list)
for t in filled:
    by_year[t.date[:4]].append(t)

print(f"{'Year':>6} {'Trades':>6} {'WR':>6} {'NetR':>7} {'AvgR':>6} {'BigW':>5} {'SL':>4} {'TP12':>4} {'TP1BE':>5} {'TP1EOD':>6} {'EOD':>4}")
print("-" * 78)

for year in sorted(by_year.keys()):
    tt = by_year[year]
    wins = sum(1 for t in tt if t.r_multiple > 0)
    net_r = sum(t.r_multiple for t in tt)
    avg_r = net_r / len(tt) if tt else 0
    big_wins = sum(1 for t in tt if t.r_multiple >= 3.0)

    exits = defaultdict(int)
    for t in tt:
        exits[t.exit_type] += 1

    wr = wins / len(tt) if tt else 0
    print(f"{year:>6} {len(tt):>6} {wr:>5.1%} {net_r:>7.1f} {avg_r:>6.2f} {big_wins:>5} "
          f"{exits[1]:>4} {exits[2]:>4} {exits[3]:>5} {exits[4]:>6} {exits[5]:>4}")

# Deep dive on 2020, 2023, 2024
for year in ["2020", "2023", "2024"]:
    tt = by_year[year]
    print(f"\n{'='*70}")
    print(f"  {year} DEEP DIVE ({len(tt)} trades, {sum(t.r_multiple for t in tt):.1f}R)")
    print(f"{'='*70}")

    # Monthly breakdown
    by_month = defaultdict(list)
    for t in tt:
        by_month[t.date[:7]].append(t)

    print(f"\n  {'Month':>8} {'Trades':>6} {'WR':>6} {'NetR':>7} {'BigW':>5}")
    print(f"  {'-'*40}")
    for m in sorted(by_month.keys()):
        mt = by_month[m]
        mw = sum(1 for t in mt if t.r_multiple > 0)
        mr = sum(t.r_multiple for t in mt)
        mbig = sum(1 for t in mt if t.r_multiple >= 3.0)
        print(f"  {m:>8} {len(mt):>6} {mw/len(mt):>5.1%} {mr:>7.1f} {mbig:>5}")

    # Top 5 trades
    sorted_trades = sorted(tt, key=lambda t: t.r_multiple, reverse=True)
    print(f"\n  Top 5 winners:")
    for t in sorted_trades[:5]:
        print(f"    {t.date} | {t.r_multiple:>+6.2f}R | {EXIT_NAMES.get(t.exit_type, '?')}")

    print(f"\n  Bottom 5 losers:")
    for t in sorted_trades[-5:]:
        print(f"    {t.date} | {t.r_multiple:>+6.2f}R | {EXIT_NAMES.get(t.exit_type, '?')}")
