#!/usr/bin/env python3
"""Regime gate sweep for top downside candidates from broad search.

Tests regime gates on:
  - GC Asia-2 Short (best W3m additivity with positive holdout)
  - GC Asia-3 Short (best W3m additivity overall)
  - SI Asia-1 Short (best standalone prop metrics, negative correlation)
  - SI Asia-4 Short (best standalone Calmar)
  - GC Asia-1 Both (most R, 0 neg years, commodity diversifier)

Uses per-asset regime calendars (causal, tercile vol, 1-session shifted).
"""

import datetime
import itertools
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.alpha_v1_downside import filter_trades_by_combined_regime
from orb_backtest.analysis.regime_research import (
    attribute_strategy_by_regime,
    build_extended_regime_calendar,
    compute_bucket_metrics,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import GC, SI
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

FULL_START = "2016-01-01"
FULL_END = "2026-04-04"
HOLDOUT_START = "2025-01-01"
PROP_START = "2016-01-01"
PROP_END = "2026-04-04"
CYCLE_DAYS = 14
PAYOUT_R = 5.0
BREACH_R = -4.0

CANDIDATES = {
    "GC_Asia2_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:15", entry_start="20:15", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.0, tp1_ratio=0.6, atr_length=14,
        name="GC Asia-2 Short"),

    "GC_Asia3_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.0, tp1_ratio=0.5, atr_length=14,
        name="GC Asia-3 Short"),

    "GC_Asia1_Both": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=25.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="both", rr=2.5, tp1_ratio=0.6, atr_length=14,
        name="GC Asia-1 Both"),

    "SI_Asia1_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=SI, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.5, tp1_ratio=0.6, atr_length=14,
        name="SI Asia-1 Short"),

    "SI_Asia4_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=SI, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=3.0, tp1_ratio=0.5, atr_length=14,
        name="SI Asia-4 Short"),
}

# Gate variants to test
GATE_VARIANTS = {
    "ungated": frozenset(),
    "skip_bull_low": frozenset(["bull_low_vol"]),
    "skip_bull_med": frozenset(["bull_medium_vol"]),
    "skip_bull_low+med": frozenset(["bull_low_vol", "bull_medium_vol"]),
    "skip_bull_all": frozenset(["bull_low_vol", "bull_medium_vol", "bull_high_vol"]),
    "skip_sw_low": frozenset(["sideways_low_vol"]),
    "skip_sw_med": frozenset(["sideways_medium_vol"]),
    "skip_sw_low+med": frozenset(["sideways_low_vol", "sideways_medium_vol"]),
    "skip_bull+sw_low": frozenset(["bull_low_vol", "sideways_low_vol"]),
    "skip_bull+sw_med": frozenset(["bull_medium_vol", "sideways_medium_vol"]),
    "skip_bull+sw_low+med": frozenset(["bull_low_vol", "bull_medium_vol", "sideways_low_vol", "sideways_medium_vol"]),
    "skip_bear_low": frozenset(["bear_low_vol"]),
    "skip_bear_med": frozenset(["bear_medium_vol"]),
    "skip_bear_low+med": frozenset(["bear_low_vol", "bear_medium_vol"]),
}


def simulate_staggered_accounts(trade_data, start_date, end_date, payout_r, breach_r, stagger_days=14):
    if not trade_data:
        return {"success_rate": None, "ev_per_account": 0.0, "max_consec_breach": 0, "avg_days_to_payout": None}
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
                outcome = "payout"; outcome_date = t["date"]; break
            elif cum_r <= breach_r:
                outcome = "breach"; outcome_date = t["date"]; break
        if outcome == "open":
            future = [t for t in trade_data if t["date"] >= acct_start]
            if future: outcome_date = future[-1]["date"]
        results.append({"outcome": outcome, "final_r": cum_r, "days": (outcome_date - acct_start).days + 1})
    payouts = [r for r in results if r["outcome"] == "payout"]
    breaches = [r for r in results if r["outcome"] == "breach"]
    resolved = len(payouts) + len(breaches)
    sr = len(payouts) / resolved if resolved else None
    capped = [payout_r if r["outcome"] == "payout" else breach_r if r["outcome"] == "breach" else r["final_r"] for r in results]
    ev = float(np.mean(capped)) if capped else 0.0
    mcb = cur = 0
    for r in results:
        if r["outcome"] == "breach": cur += 1; mcb = max(mcb, cur)
        else: cur = 0
    return {
        "success_rate": round(sr, 4) if sr else None,
        "ev_per_account": round(ev, 4),
        "max_consec_breach": mcb,
        "avg_days_to_payout": round(float(np.mean([r["days"] for r in payouts])), 1) if payouts else None,
    }


def main():
    t0 = time.time()
    print("=" * 110)
    print("DOWNSIDE CANDIDATES — Regime Gate Sweep")
    print("=" * 110)
    print()

    # Load data and build per-asset regime calendars
    print("Loading data...")
    data_map = {}
    regime_cals = {}
    for symbol, instr in [("GC", GC), ("SI", SI)]:
        df_5m = load_5m_data(f"{symbol}_5m.parquet")
        df_1m = load_1m_for_5m(f"{symbol}_5m.parquet")
        data_map[symbol] = (df_5m, df_1m)
        regime_cals[symbol] = build_extended_regime_calendar(df_5m, start_date=FULL_START, end_date=FULL_END, holdout_start=HOLDOUT_START)
        print(f"  {symbol}: {len(df_5m):,} 5m  |  regime cal: {len(regime_cals[symbol])} days")

    # Run backtests (ungated)
    print(f"\n{'=' * 110}")
    print("BACKTESTS (ungated)")
    print(f"{'=' * 110}")

    raw_trades = {}
    filled_trades = {}
    for name, cfg in CANDIDATES.items():
        symbol = cfg.instrument.symbol
        df_5m, df_1m = data_map[symbol]
        trades = run_backtest(df_5m, cfg, start_date=FULL_START, end_date=FULL_END, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        raw_trades[name] = trades
        filled_trades[name] = filled
        m = compute_metrics(trades)
        print(f"  {name}: {m['total_trades']} trades  |  Net R: {m['total_r']:+.1f}  |  DD: {m['max_drawdown_r']:.1f}R  |  Calmar: {m['calmar_ratio']:.2f}")

    # Attribution
    print(f"\n{'=' * 110}")
    print("REGIME ATTRIBUTION")
    print(f"{'=' * 110}")

    for name, trades in raw_trades.items():
        symbol = CANDIDATES[name].instrument.symbol
        attr_df = attribute_strategy_by_regime(trades, regime_cals[symbol], holdout_start=HOLDOUT_START)
        if attr_df.empty:
            continue
        bm = compute_bucket_metrics(attr_df, group_col="combined_regime")
        print(f"\n  ── {name} ({symbol}) ──")
        print(f"  {'Regime':<25} {'Trades':>6} {'WR':>6} {'Avg R':>7} {'Tot R':>8} {'PF':>6} {'Max DD':>8}")
        print(f"  {'-'*70}")
        for _, row in bm.iterrows():
            pf = f"{row['profit_factor']:.2f}" if row['profit_factor'] < 100 else "inf"
            print(f"  {row['bucket']:<25} {row['trade_count']:>6} {row['win_rate']:>5.1%} {row['avg_r']:>+7.3f} {row['total_r']:>+8.2f} {pf:>6} {row['max_drawdown_r']:>8.2f}")

    # Gate sweep
    print(f"\n{'=' * 110}")
    print("GATE SWEEP")
    print(f"{'=' * 110}")

    # Also add dynamic gates from worst buckets per candidate
    dynamic_gates = {}
    for name, trades in raw_trades.items():
        symbol = CANDIDATES[name].instrument.symbol
        attr_df = attribute_strategy_by_regime(trades, regime_cals[symbol], holdout_start=HOLDOUT_START)
        if attr_df.empty:
            continue
        bm = compute_bucket_metrics(attr_df, group_col="combined_regime")
        neg = bm[bm["avg_r"] < 0].sort_values("avg_r")
        for _, row in neg.head(3).iterrows():
            b = row["bucket"]
            gn = f"skip_{b}"
            if gn not in GATE_VARIANTS and gn not in dynamic_gates:
                dynamic_gates[gn] = frozenset([b])

    all_gates = {**GATE_VARIANTS}
    for gn, excl in dynamic_gates.items():
        if gn not in all_gates:
            all_gates[gn] = excl

    gate_results = []
    for name in CANDIDATES:
        symbol = CANDIDATES[name].instrument.symbol
        filled = filled_trades[name]
        cal = regime_cals[symbol]

        for gate_name, exclude in all_gates.items():
            gated = filter_trades_by_combined_regime(filled, cal, include=set(), exclude=set(exclude), include_low_confidence=True)
            if len(gated) < 20:
                continue
            m = compute_metrics(gated)
            ho = [t for t in gated if t.date >= HOLDOUT_START]
            m_ho = compute_metrics(ho) if len(ho) >= 5 else None
            td = sorted([{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in gated], key=lambda x: x["date"])
            acct = simulate_staggered_accounts(td, PROP_START, PROP_END, PAYOUT_R, BREACH_R, CYCLE_DAYS)
            rby = m.get("r_by_year", {})
            neg_y = sum(1 for r in rby.values() if r < 0)

            gate_results.append({
                "candidate": name, "gate": gate_name,
                "exclude": ", ".join(sorted(exclude)) if exclude else "(none)",
                "trades": m["total_trades"],
                "removed": compute_metrics(filled)["total_trades"] - m["total_trades"],
                "wr": m["win_rate"], "net_r": m["total_r"], "max_dd": m["max_drawdown_r"],
                "calmar": m["calmar_ratio"], "sharpe": m["sharpe_ratio"], "neg_years": neg_y,
                "ho_r": m_ho["total_r"] if m_ho else None,
                "ho_trades": m_ho["total_trades"] if m_ho else 0,
                "pay": acct["success_rate"], "ev": acct["ev_per_account"],
                "mcb": acct["max_consec_breach"], "avg_days": acct["avg_days_to_payout"],
                "r_by_year": rby,
            })

    # Print per-candidate results
    for name in CANDIDATES:
        rows = sorted([r for r in gate_results if r["candidate"] == name],
                      key=lambda r: (r["neg_years"], -(r["calmar"] or 0)))
        print(f"\n\n  ── {name} ──")
        print(f"  {'Gate':<30} {'Trds':>5} {'-Rm':>4} {'WR':>5} {'NetR':>7} {'DD':>7} {'Calm':>6} {'Neg':>3} {'H-R':>6} {'Pay%':>6} {'EV':>7} {'MCB':>4}")
        print(f"  {'-'*100}")
        for r in rows:
            hr = f"{r['ho_r']:+.1f}" if r['ho_r'] is not None else "—"
            pr = f"{r['pay']:.1%}" if r['pay'] else "N/A"
            print(f"  {r['gate']:<30} {r['trades']:>5} {r['removed']:>4} {r['wr']:>4.1%} {r['net_r']:>+7.1f} {r['max_dd']:>7.1f} {r['calmar']:>6.2f} {r['neg_years']:>3} {hr:>6} {pr:>6} {r['ev']:>+7.3f} {r['mcb']:>4}")

    # Top results across all candidates
    print(f"\n\n{'=' * 110}")
    print("TOP GATED VARIANTS (by payout rate, then Calmar)")
    print(f"{'=' * 110}")

    by_pay = sorted(gate_results, key=lambda r: (-(r["pay"] or 0), -(r["calmar"] or 0)))
    print(f"\n  {'Candidate':<18} {'Gate':<28} {'Trds':>5} {'NetR':>7} {'Calm':>6} {'Neg':>3} {'H-R':>6} {'Pay%':>6} {'EV':>7} {'MCB':>4}")
    print(f"  {'-'*105}")
    for r in by_pay[:25]:
        hr = f"{r['ho_r']:+.1f}" if r['ho_r'] is not None else "—"
        pr = f"{r['pay']:.1%}" if r['pay'] else "N/A"
        print(f"  {r['candidate']:<18} {r['gate']:<28} {r['trades']:>5} {r['net_r']:>+7.1f} {r['calmar']:>6.02f} {r['neg_years']:>3} {hr:>6} {pr:>6} {r['ev']:>+7.3f} {r['mcb']:>4}")

    # Year-by-year for top 5
    print(f"\n\n{'=' * 110}")
    print("YEAR-BY-YEAR (top 5 by payout rate)")
    print(f"{'=' * 110}")
    for r in by_pay[:5]:
        years = sorted(r["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{v:+.1f}" for yr, v in years)
        print(f"\n  {r['candidate']} | {r['gate']}")
        print(f"  Calmar: {r['calmar']:.2f}  |  Net R: {r['net_r']:+.1f}  |  DD: {r['max_dd']:.1f}R  |  Neg years: {r['neg_years']}  |  Pay: {r['pay']:.1%}")
        print(f"  {yr_str}")

    print(f"\n\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
