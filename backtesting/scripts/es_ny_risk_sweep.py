#!/usr/bin/env python3
"""Sweep risk levels for ES NY Cont using actual trade data."""
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL

ES = get_instrument("ES")

SESSION = SessionConfig(
    name="NY", orb_start="09:30", orb_end="09:45",
    entry_start="09:45", entry_end="13:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=5.0, min_gap_atr_pct=0.25,
    min_stop_points=3.0, min_tp1_points=3.0,
)
CONFIG = StrategyConfig(
    sessions=(SESSION,), instrument=ES, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=5.0, tp1_ratio=0.2, atr_length=7, excluded_days=(3,),
)

PAYOUT_USD = 2500
BREACH_USD = -2000

data_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
print("Loading ES data...")
df = load_5m_data(str(data_dir / "ES_5m.csv"))
df_1m = load_1m_for_5m(str(data_dir / "ES_5m.csv"))
try:
    df_1s = load_1s_for_5m(str(data_dir / "ES_5m.csv"))
except Exception:
    df_1s = None
maps = build_maps(df, df_1m=df_1m, df_1s=df_1s)

print("Running backtest...")
trades = run_backtest(df, CONFIG, df_1m=df_1m, df_1s=df_1s, _maps=maps)
filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
print(f"  {len(filled)} trades, Net R: {sum(t.r_multiple for t in filled):+.1f}")

# Build dated R
daily = defaultdict(float)
for t in filled:
    daily[str(t.date)[:10]] += t.r_multiple
trading_cal = sorted(daily.keys())


def simulate(dated_daily, risk):
    payout_usd = PAYOUT_USD
    breach_usd = BREACH_USD
    results = []
    first_dt = datetime.strptime(dated_daily[0][0], "%Y-%m-%d")
    last_dt = datetime.strptime(dated_daily[-1][0], "%Y-%m-%d")
    dates = [d for d, _ in dated_daily]
    r_vals = [r for _, r in dated_daily]

    start_date = first_dt
    while start_date <= last_dt:
        start_str = start_date.strftime("%Y-%m-%d")
        first_idx = None
        for i, d in enumerate(dates):
            if d >= start_str:
                first_idx = i; break

        if first_idx is not None:
            eq_usd = 0.0
            days = 0
            status = "OPEN"
            end_idx = first_idx
            for idx in range(first_idx, len(dates)):
                days += 1
                eq_usd += r_vals[idx] * risk
                end_idx = idx
                if eq_usd >= payout_usd:
                    status = "PAYOUT"; break
                elif eq_usd <= breach_usd:
                    status = "BREACH"; break

            end_dt = datetime.strptime(dates[end_idx], "%Y-%m-%d")
            cal_days = (end_dt - start_date).days + 1
            results.append({"start": start_str, "days": days, "cal_days": cal_days, "status": status})

        start_date += timedelta(days=14)
    return results


def analyze(results):
    payouts = [r for r in results if r["status"] == "PAYOUT"]
    breaches = [r for r in results if r["status"] == "BREACH"]
    opens = [r for r in results if r["status"] == "OPEN"]
    resolved = payouts + breaches
    pr = len(payouts) / len(resolved) * 100 if resolved else 0
    br = len(breaches) / len(resolved) * 100 if resolved else 0
    apd = np.mean([p["cal_days"] for p in payouts]) if payouts else float('nan')
    abd = np.mean([b["cal_days"] for b in breaches]) if breaches else float('nan')
    seq = [r["status"] for r in sorted(results, key=lambda x: x["start"]) if r["status"] in ("PAYOUT", "BREACH")]
    mcb = mcp = cb = cp = 0
    for s in seq:
        if s == "BREACH": cb += 1; cp = 0; mcb = max(mcb, cb)
        else: cp += 1; cb = 0; mcp = max(mcp, cp)
    return pr, br, apd, abd, mcb, mcp, len(payouts), len(breaches), len(opens)


periods = {
    "FULL HISTORY": (None, None),
    "2025": ("2025-01-01", "2026-01-01"),
    "2026 YTD": ("2026-01-01", None),
}

risk_levels = [200, 250, 300, 350, 400, 500]

for period_name, (start, end) in periods.items():
    cal = trading_cal
    if start: cal = [d for d in cal if d >= start]
    if end: cal = [d for d in cal if d < end]
    if not cal: continue

    r_by_date = dict((d, daily.get(d, 0.0)) for d in cal)
    dated = [(d, r_by_date.get(d, 0.0)) for d in cal]
    net_r = sum(r for _, r in dated)

    print(f"\n{'='*90}")
    print(f"  ES NY CONT — {period_name}  |  Net R: {net_r:+.1f}  |  {len(cal)} trading days")
    print(f"{'='*90}")
    print(f"  {'Risk':>6} {'Pay%':>7} {'Bch%':>7} {'PayD':>7} {'BchD':>7} {'MCBch':>6} {'MCPay':>6} {'#Pay':>6} {'#Bch':>6} {'#Open':>6} {'EV$':>8}")
    print("  " + "-" * 85)

    for risk in risk_levels:
        results = simulate(dated, risk)
        pr, br, apd, abd, mcb, mcp, npay, nbch, nopen = analyze(results)
        ev = pr/100 * PAYOUT_USD + br/100 * BREACH_USD
        print(f"  ${risk:>5} {pr:>6.1f}% {br:>6.1f}% {apd:>6.0f}d {abd:>6.0f}d {mcb:>6d} {mcp:>6d} {npay:>6d} {nbch:>6d} {nopen:>6d} {ev:>+7.0f}")
