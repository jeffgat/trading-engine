#!/usr/bin/env python3
"""Detailed prop sim for Tier 1 downside candidates across multiple periods.

Reports exact payout/breach/open counts, drawdown, and year-by-year R
for full history, 2024, 2025, and 2026 periods.
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.alpha_v1_downside import filter_trades_by_combined_regime
from orb_backtest.analysis.regime_research import build_extended_regime_calendar
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, GC, SI
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

FULL_START = "2016-01-01"
FULL_END = "2026-04-05"
HOLDOUT_START = "2025-01-01"
PAYOUT_R = 5.0
BREACH_R = -4.0
CYCLE_DAYS = 14

PERIODS = {
    "Full (2016-2026)": ("2016-01-01", "2026-04-05"),
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026": ("2026-01-01", "2026-04-05"),
}

CANDIDATES = {
    "NQ NY Short RR2.5 ATR10": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY", orb_start="09:30", orb_end="09:55", entry_start="09:55", entry_end="11:30",
                flat_start="11:30", flat_end="16:00", stop_orb_pct=15.0, min_gap_orb_pct=2.5,
                min_stop_points=10.0, min_tp1_points=10.0),),
            instrument=NQ, strategy="continuation", direction_filter="short", use_bar_magnifier=True,
            rr=2.5, tp1_ratio=0.4, atr_length=10, risk_usd=5000.0, name="NQ NY Short RR2.5 ATR10"),
        "gate": frozenset(["bull_low_vol"]),
        "gate_name": "skip_bull_low_vol",
    },
    "SI Asia-1 Short": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
                flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
            instrument=SI, strategy="continuation", use_bar_magnifier=True,
            risk_usd=5000.0, direction_filter="short", rr=2.5, tp1_ratio=0.6, atr_length=14,
            name="SI Asia-1 Short"),
        "gate": frozenset(["bull_medium_vol"]),
        "gate_name": "skip_bull_medium_vol",
    },
    "GC Asia-1 Both": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
                flat_start="04:00", flat_end="07:00", stop_orb_pct=25.0, min_gap_atr_pct=1.0),),
            instrument=GC, strategy="continuation", use_bar_magnifier=True,
            risk_usd=5000.0, direction_filter="both", rr=2.5, tp1_ratio=0.6, atr_length=14,
            name="GC Asia-1 Both"),
        "gate": frozenset(),
        "gate_name": "ungated",
    },
}


def simulate_staggered_accounts(trade_data, start_date, end_date, payout_r, breach_r, stagger_days=14):
    if not trade_data:
        return {"total": 0, "payouts": 0, "breaches": 0, "open": 0, "success_rate": None,
                "ev_per_account": 0.0, "max_consec_breach": 0, "avg_days_to_payout": None,
                "median_days_to_payout": None, "avg_days_to_breach": None}

    d_start = datetime.date.fromisoformat(start_date)
    d_end = datetime.date.fromisoformat(end_date)
    starts = []
    s = d_start
    while s <= d_end:
        starts.append(s)
        s += datetime.timedelta(days=stagger_days)

    results = []
    for acct_start in starts:
        cum_r = 0.0
        outcome = "open"
        outcome_date = acct_start
        for t in trade_data:
            if t["date"] < acct_start:
                continue
            cum_r += t["r"]
            if cum_r >= payout_r:
                outcome = "payout"
                outcome_date = t["date"]
                break
            elif cum_r <= breach_r:
                outcome = "breach"
                outcome_date = t["date"]
                break
        if outcome == "open":
            future = [t for t in trade_data if t["date"] >= acct_start]
            if future:
                outcome_date = future[-1]["date"]
        results.append({"outcome": outcome, "final_r": cum_r,
                        "days": (outcome_date - acct_start).days + 1})

    payouts = [r for r in results if r["outcome"] == "payout"]
    breaches = [r for r in results if r["outcome"] == "breach"]
    opens = [r for r in results if r["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    sr = len(payouts) / resolved if resolved else None

    capped = [payout_r if r["outcome"] == "payout" else breach_r if r["outcome"] == "breach" else r["final_r"]
              for r in results]
    ev = float(np.mean(capped)) if capped else 0.0

    mcb = cur = 0
    for r in results:
        if r["outcome"] == "breach":
            cur += 1
            mcb = max(mcb, cur)
        else:
            cur = 0

    return {
        "total": len(results),
        "payouts": len(payouts), "breaches": len(breaches), "open": len(opens),
        "success_rate": round(sr, 4) if sr else None,
        "ev_per_account": round(ev, 4),
        "max_consec_breach": mcb,
        "avg_days_to_payout": round(float(np.mean([r["days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["days"] for r in payouts])), 1) if payouts else None,
        "avg_days_to_breach": round(float(np.mean([r["days"] for r in breaches])), 1) if breaches else None,
    }


def main():
    t0 = time.time()
    print("=" * 120)
    print("TIER 1 DOWNSIDE CANDIDATES — Detailed Prop Sim + Drawdown + Year-by-Year")
    print("=" * 120)
    print(f"Prop sim: +{PAYOUT_R}R payout / {BREACH_R}R breach / {CYCLE_DAYS}-day stagger")
    print()

    # Load data + regime calendars
    print("Loading data...")
    data_map = {}
    regime_cals = {}
    for symbol, instr in [("NQ", NQ), ("GC", GC), ("SI", SI)]:
        df_5m = load_5m_data(f"{symbol}_5m.parquet")
        df_1m = load_1m_for_5m(f"{symbol}_5m.parquet")
        data_map[symbol] = (df_5m, df_1m)
        regime_cals[symbol] = build_extended_regime_calendar(
            df_5m, start_date=FULL_START, end_date=FULL_END, holdout_start=HOLDOUT_START)
        print(f"  {symbol}: {len(df_5m):,} 5m bars  |  regime cal: {len(regime_cals[symbol])} days")

    # Run each candidate
    for cand_name, cand in CANDIDATES.items():
        cfg = cand["config"]
        gate = cand["gate"]
        gate_name = cand["gate_name"]
        symbol = cfg.instrument.symbol
        df_5m, df_1m = data_map[symbol]

        print(f"\n\n{'=' * 120}")
        print(f"  {cand_name}  |  Gate: {gate_name}")
        print(f"{'=' * 120}")

        # Run full backtest
        trades = run_backtest(df_5m, cfg, start_date=FULL_START, end_date=FULL_END, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

        # Apply regime gate
        if gate:
            cal = regime_cals[symbol]
            gated = filter_trades_by_combined_regime(filled, cal, include=set(), exclude=set(gate), include_low_confidence=True)
        else:
            gated = filled

        # Full metrics
        m = compute_metrics(gated)
        print(f"\n  Trades: {m['total_trades']}  |  WR: {m['win_rate']:.1%}  |  Net R: {m['total_r']:+.1f}  |  Max DD: {m['max_drawdown_r']:.1f}R  |  Calmar: {m['calmar_ratio']:.2f}")

        # Year-by-year
        r_by_year = m.get("r_by_year", {})
        print(f"\n  Year-by-Year R:")
        for yr in sorted(r_by_year.keys()):
            bar = "+" * int(max(0, r_by_year[yr])) + "-" * int(max(0, -r_by_year[yr]))
            print(f"    {yr}: {r_by_year[yr]:>+7.1f}R  {bar}")

        # Drawdown details
        print(f"\n  Max Drawdown: {m['max_drawdown_r']:.2f}R")

        # Compute equity curve for drawdown detail
        trade_data = sorted(
            [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in gated],
            key=lambda x: x["date"],
        )
        daily_r = {}
        for t in trade_data:
            daily_r[t["date"]] = daily_r.get(t["date"], 0.0) + t["r"]
        daily_sorted = sorted(daily_r.items())
        if daily_sorted:
            cum = np.cumsum([r for _, r in daily_sorted])
            peak = np.maximum.accumulate(cum)
            dd = cum - peak
            # Top 5 drawdowns
            print(f"\n  Top 5 Drawdown Troughs:")
            dd_with_dates = list(zip([d for d, _ in daily_sorted], dd))
            # Find distinct drawdown periods
            seen_periods = []
            sorted_dd = sorted(dd_with_dates, key=lambda x: x[1])
            for d, dd_val in sorted_dd[:20]:
                # Skip if within 30 days of an already-reported trough
                too_close = False
                for prev_d in seen_periods:
                    if abs((d - prev_d).days) < 30:
                        too_close = True
                        break
                if too_close:
                    continue
                seen_periods.append(d)
                if len(seen_periods) >= 5:
                    break
            for i, d in enumerate(seen_periods):
                dd_val = dict(dd_with_dates)[d]
                print(f"    {i+1}. {d}: {dd_val:.2f}R")

        # Prop sim by period
        print(f"\n  {'─' * 100}")
        print(f"  PROP SIM BY PERIOD")
        print(f"  {'─' * 100}")
        print(f"  {'Period':<22} {'Accts':>5} {'Payouts':>7} {'Breaches':>8} {'Open':>4} {'Pay%':>6} {'EV/acct':>8} {'MCB':>4} {'Avg Days':>8} {'Med Days':>8} {'Avg Br D':>8}")
        print(f"  {'-' * 100}")

        for period_name, (p_start, p_end) in PERIODS.items():
            # Filter trades to period for the sim
            period_trades = [t for t in trade_data if datetime.date.fromisoformat(p_start) <= t["date"] <= datetime.date.fromisoformat(p_end)]
            acct = simulate_staggered_accounts(period_trades, p_start, p_end, PAYOUT_R, BREACH_R, CYCLE_DAYS)

            sr = f"{acct['success_rate']:.1%}" if acct['success_rate'] else "N/A"
            avg_d = f"{acct['avg_days_to_payout']:.0f}" if acct['avg_days_to_payout'] else "—"
            med_d = f"{acct['median_days_to_payout']:.0f}" if acct['median_days_to_payout'] else "—"
            avg_br = f"{acct['avg_days_to_breach']:.0f}" if acct['avg_days_to_breach'] else "—"
            print(f"  {period_name:<22} {acct['total']:>5} {acct['payouts']:>7} {acct['breaches']:>8} {acct['open']:>4} {sr:>6} {acct['ev_per_account']:>+8.3f} {acct['max_consec_breach']:>4} {avg_d:>8} {med_d:>8} {avg_br:>8}")

        # Per-year trade counts in the period
        print(f"\n  Trades per year (gated):")
        for yr in sorted(set(t.date[:4] for t in gated)):
            yr_trades = [t for t in gated if t.date.startswith(yr)]
            yr_wins = sum(1 for t in yr_trades if t.r_multiple > 0)
            yr_r = sum(t.r_multiple for t in yr_trades)
            print(f"    {yr}: {len(yr_trades)} trades  |  WR: {yr_wins/len(yr_trades):.1%}  |  R: {yr_r:+.1f}")

    print(f"\n\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
