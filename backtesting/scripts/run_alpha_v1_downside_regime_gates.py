#!/usr/bin/env python3
"""Regime gate sweep for the 3 promoted NQ NY continuation short candidates.

Step 1: Attribution — show per-bucket performance for each candidate
Step 2: Gate sweep — test exclusion combinations on the worst-performing buckets
Step 3: Compare gated vs ungated on standalone prop sim + combined portfolio

Uses the same causal regime framework as the LSI downside research:
  trend: bull / bear / sideways  (close_vs_sma20 + ret_5d, shifted 1 session)
  vol:   low / medium / high     (realized_vol_21d, tercile on pre-holdout)
  combined: 9 buckets (3x3)
"""

import datetime
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.alpha_v1_downside import filter_trades_by_combined_regime
from orb_backtest.analysis.regime_research import (
    attribute_strategy_by_regime,
    build_extended_regime_calendar,
    compute_bucket_metrics,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

# ── Date parameters ───────────────────────────────────────────────────────

FULL_START = "2016-01-01"
FULL_END = "2026-04-04"
HOLDOUT_START = "2025-01-01"
PROP_START = "2016-01-01"
PROP_END = "2026-04-04"
CYCLE_DAYS = 14

# Prop thresholds (standalone short account)
PAYOUT_R = 5.0
BREACH_R = -4.0


# ── Short candidate configs ──────────────────────────────────────────────

def _short_session() -> SessionConfig:
    return SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:55",
        entry_start="09:55",
        entry_end="11:30",
        flat_start="11:30",
        flat_end="16:00",
        stop_orb_pct=15.0,
        min_gap_orb_pct=2.5,
        min_stop_points=10.0,
        min_tp1_points=10.0,
    )


SHORT_CANDIDATES = {
    "RR2.0_ATR10": StrategyConfig(
        sessions=(_short_session(),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="short",
        use_bar_magnifier=True,
        rr=2.0,
        tp1_ratio=0.5,
        atr_length=10,
        risk_usd=5000.0,
        name="NQ NY Short RR2.0 ATR10",
    ),
    "RR2.5_ATR12": StrategyConfig(
        sessions=(_short_session(),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="short",
        use_bar_magnifier=True,
        rr=2.5,
        tp1_ratio=0.4,
        atr_length=12,
        risk_usd=5000.0,
        name="NQ NY Short RR2.5 ATR12",
    ),
    "RR2.5_ATR10": StrategyConfig(
        sessions=(_short_session(),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="short",
        use_bar_magnifier=True,
        rr=2.5,
        tp1_ratio=0.4,
        atr_length=10,
        risk_usd=5000.0,
        name="NQ NY Short RR2.5 ATR10",
    ),
}

# ── All 9 combined regime buckets ─────────────────────────────────────────

ALL_REGIMES = [
    "bull_low_vol", "bull_medium_vol", "bull_high_vol",
    "bear_low_vol", "bear_medium_vol", "bear_high_vol",
    "sideways_low_vol", "sideways_medium_vol", "sideways_high_vol",
]

# Gate variants to test: exclude 1 or 2 buckets at a time from the worst performers
# We'll build these dynamically after seeing the attribution results,
# but also include the known-good gates from the LSI research
PREDEFINED_GATES = {
    "ungated": frozenset(),
    "skip_bull_low": frozenset(["bull_low_vol"]),
    "skip_bull_med": frozenset(["bull_medium_vol"]),
    "skip_bull_low+med": frozenset(["bull_low_vol", "bull_medium_vol"]),
    "skip_bull_all": frozenset(["bull_low_vol", "bull_medium_vol", "bull_high_vol"]),
    "skip_sideways_low": frozenset(["sideways_low_vol"]),
    "skip_sideways_med": frozenset(["sideways_medium_vol"]),
    "skip_sideways_low+med": frozenset(["sideways_low_vol", "sideways_medium_vol"]),
    "skip_sideways_all": frozenset(["sideways_low_vol", "sideways_medium_vol", "sideways_high_vol"]),
    "skip_bull+sw_low": frozenset(["bull_low_vol", "sideways_low_vol"]),
    "skip_bull+sw_med": frozenset(["bull_medium_vol", "sideways_medium_vol"]),
    "skip_bull+sw_low+med": frozenset(["bull_low_vol", "bull_medium_vol", "sideways_low_vol", "sideways_medium_vol"]),
    "skip_low_conf": "LOW_CONF",  # special: exclude low-confidence days
}


# ── Prop sim ──────────────────────────────────────────────────────────────

def simulate_staggered_accounts(
    trade_data: list[dict],
    start_date: str,
    end_date: str,
    payout_r: float,
    breach_r: float,
    stagger_days: int = 14,
) -> dict:
    if not trade_data:
        return {"total_accounts": 0, "payouts": 0, "breaches": 0, "open": 0,
                "success_rate": None, "ev_per_account": 0.0,
                "max_consec_breach": 0, "max_consec_payout": 0,
                "avg_days_to_payout": None, "median_days_to_payout": None,
                "avg_days_to_breach": None, "account_details": []}

    d_start = datetime.date.fromisoformat(start_date)
    d_end = datetime.date.fromisoformat(end_date)

    account_starts = []
    s = d_start
    while s <= d_end:
        account_starts.append(s)
        s += datetime.timedelta(days=stagger_days)

    results = []
    for acct_start in account_starts:
        cum_r = 0.0
        outcome = "open"
        trades_taken = 0
        outcome_date = None
        peak_r = 0.0
        trough_r = 0.0

        for t in trade_data:
            if t["date"] < acct_start:
                continue
            cum_r += t["r"]
            trades_taken += 1
            peak_r = max(peak_r, cum_r)
            trough_r = min(trough_r, cum_r)

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
            outcome_date = future[-1]["date"] if future else acct_start

        calendar_days = (outcome_date - acct_start).days + 1
        results.append({
            "account_start": acct_start.isoformat(),
            "outcome": outcome,
            "final_r": round(cum_r, 4),
            "trades_taken": trades_taken,
            "calendar_days": calendar_days,
        })

    payouts = [r for r in results if r["outcome"] == "payout"]
    breaches = [r for r in results if r["outcome"] == "breach"]
    opens = [r for r in results if r["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    success_rate = len(payouts) / resolved if resolved > 0 else None

    capped_rs = []
    for r in results:
        if r["outcome"] == "payout":
            capped_rs.append(payout_r)
        elif r["outcome"] == "breach":
            capped_rs.append(breach_r)
        else:
            capped_rs.append(r["final_r"])
    ev = float(np.mean(capped_rs)) if capped_rs else 0.0

    max_consec_breach = max_consec_payout = cur_b = cur_p = 0
    for r in results:
        if r["outcome"] == "breach":
            cur_b += 1
            max_consec_breach = max(max_consec_breach, cur_b)
        else:
            cur_b = 0
        if r["outcome"] == "payout":
            cur_p += 1
            max_consec_payout = max(max_consec_payout, cur_p)
        else:
            cur_p = 0

    return {
        "total_accounts": len(results),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": round(success_rate, 4) if success_rate is not None else None,
        "ev_per_account": round(ev, 4),
        "max_consec_breach": max_consec_breach,
        "max_consec_payout": max_consec_payout,
        "avg_days_to_payout": round(float(np.mean([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "avg_days_to_breach": round(float(np.mean([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "account_details": results,
    }


def main():
    t0 = time.time()

    print("=" * 100)
    print("ALPHA_V1 DOWNSIDE — Regime Gate Sweep")
    print("=" * 100)
    print()

    # ── Load data ─────────────────────────────────────────────────────────

    print("Loading data...")
    nq_5m = load_5m_data("NQ_5m.parquet")
    nq_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  NQ: {len(nq_5m):,} 5m  |  {len(nq_1m):,} 1m")

    # ── Build regime calendar ─────────────────────────────────────────────

    print("Building regime calendar...")
    regime_cal = build_extended_regime_calendar(
        nq_5m,
        start_date=FULL_START,
        end_date=FULL_END,
        holdout_start=HOLDOUT_START,
    )
    print(f"  {len(regime_cal)} trading days")

    # Show regime distribution
    dist = regime_cal[regime_cal["regime"] != "warmup"]["combined_regime"].value_counts()
    print(f"\n  Regime distribution:")
    for regime, count in dist.sort_index().items():
        pct = count / len(regime_cal[regime_cal["regime"] != "warmup"]) * 100
        print(f"    {regime:<25} {count:>5} days  ({pct:>5.1f}%)")

    # ── Run backtests (ungated — gate applied post-trade) ─────────────────

    print(f"\n{'=' * 100}")
    print("RUNNING BACKTESTS (ungated)")
    print(f"{'=' * 100}")

    raw_results = {}  # cand_name -> list[TradeResult] (all trades including no-fills)
    filled_results = {}  # cand_name -> list[TradeResult] (filled only)

    for cand_name, cfg in SHORT_CANDIDATES.items():
        trades = run_backtest(nq_5m, cfg, start_date=FULL_START, end_date=FULL_END, df_1m=nq_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        raw_results[cand_name] = trades
        filled_results[cand_name] = filled
        m = compute_metrics(trades)
        print(f"\n  {cand_name}: {m['total_trades']} trades  |  WR: {m['win_rate']:.1%}  |  Net R: {m['total_r']:+.1f}  |  DD: {m['max_drawdown_r']:.1f}R  |  Calmar: {m['calmar_ratio']:.2f}")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 1: REGIME ATTRIBUTION
    # ══════════════════════════════════════════════════════════════════════

    print(f"\n\n{'=' * 100}")
    print("STEP 1: REGIME ATTRIBUTION (per-bucket performance)")
    print(f"{'=' * 100}")

    for cand_name, trades in raw_results.items():
        attr_df = attribute_strategy_by_regime(trades, regime_cal, holdout_start=HOLDOUT_START)
        if attr_df.empty:
            continue

        bucket_metrics = compute_bucket_metrics(attr_df, group_col="combined_regime")

        print(f"\n  ── {cand_name} ──")
        print(f"  {'Regime':<25} {'Trades':>6} {'WR':>6} {'Avg R':>7} {'Tot R':>8} {'PF':>6} {'Max DD':>8}")
        print(f"  {'-'*70}")
        for _, row in bucket_metrics.iterrows():
            pf_str = f"{row['profit_factor']:.2f}" if row['profit_factor'] < 100 else "inf"
            print(f"  {row['bucket']:<25} {row['trade_count']:>6} {row['win_rate']:>5.1%} {row['avg_r']:>+7.3f} {row['total_r']:>+8.2f} {pf_str:>6} {row['max_drawdown_r']:>8.2f}")

        # Pre-holdout vs holdout split
        for period_name, period_df in [("Pre-holdout", attr_df[attr_df["period"] == "pre_holdout"]),
                                        ("Holdout", attr_df[attr_df["period"] == "holdout"])]:
            if period_df.empty:
                continue
            bm = compute_bucket_metrics(period_df, group_col="combined_regime")
            print(f"\n  {period_name}:")
            print(f"  {'Regime':<25} {'Trades':>6} {'WR':>6} {'Avg R':>7} {'Tot R':>8} {'PF':>6}")
            print(f"  {'-'*62}")
            for _, row in bm.iterrows():
                pf_str = f"{row['profit_factor']:.2f}" if row['profit_factor'] < 100 else "inf"
                print(f"  {row['bucket']:<25} {row['trade_count']:>6} {row['win_rate']:>5.1%} {row['avg_r']:>+7.3f} {row['total_r']:>+8.2f} {pf_str:>6}")

    # ══════════════════════════════════════════════════════════════════════
    # STEP 2: GATE SWEEP
    # ══════════════════════════════════════════════════════════════════════

    print(f"\n\n{'=' * 100}")
    print("STEP 2: GATE SWEEP — Testing exclusion combinations")
    print(f"{'=' * 100}")

    # Also dynamically build gates from the worst 1-2 buckets per candidate
    # by examining which buckets had worst avg_r across all candidates
    worst_buckets = set()
    for cand_name, trades in raw_results.items():
        attr_df = attribute_strategy_by_regime(trades, regime_cal, holdout_start=HOLDOUT_START)
        if attr_df.empty:
            continue
        bm = compute_bucket_metrics(attr_df, group_col="combined_regime")
        negative = bm[bm["avg_r"] < 0].sort_values("avg_r")
        for _, row in negative.head(3).iterrows():
            worst_buckets.add(row["bucket"])

    # Add single-bucket gates for each worst bucket
    dynamic_gates = {}
    for bucket in worst_buckets:
        gate_name = f"skip_{bucket}"
        if gate_name not in PREDEFINED_GATES:
            dynamic_gates[gate_name] = frozenset([bucket])

    # Add pairwise combinations of worst buckets
    for b1, b2 in itertools.combinations(sorted(worst_buckets), 2):
        gate_name = f"skip_{b1}+{b2}"
        if gate_name not in PREDEFINED_GATES:
            dynamic_gates[gate_name] = frozenset([b1, b2])

    all_gates = {}
    for name, excl in PREDEFINED_GATES.items():
        if excl != "LOW_CONF":
            all_gates[name] = {"exclude": excl, "low_conf": True}
        else:
            all_gates[name] = {"exclude": frozenset(), "low_conf": False}
    for name, excl in dynamic_gates.items():
        all_gates[name] = {"exclude": excl, "low_conf": True}

    print(f"\n  Testing {len(all_gates)} gate variants across {len(SHORT_CANDIDATES)} candidates")
    print(f"  Worst buckets identified: {sorted(worst_buckets)}")

    # Run all gate × candidate combinations
    gate_results = []  # list of dicts

    for cand_name, raw_trades in raw_results.items():
        filled = filled_results[cand_name]

        for gate_name, gate_spec in all_gates.items():
            exclude = gate_spec["exclude"]
            low_conf = gate_spec["low_conf"]

            gated = filter_trades_by_combined_regime(
                filled,
                regime_cal,
                include=set(),
                exclude=set(exclude),
                include_low_confidence=low_conf,
            )

            if len(gated) < 20:
                continue

            m = compute_metrics(gated)

            # Holdout split
            holdout_gated = [t for t in gated if t.date >= HOLDOUT_START]
            m_h = compute_metrics(holdout_gated) if len(holdout_gated) >= 5 else None

            # Prop sim
            trade_data = sorted(
                [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in gated],
                key=lambda x: x["date"],
            )
            acct = simulate_staggered_accounts(trade_data, PROP_START, PROP_END, PAYOUT_R, BREACH_R, CYCLE_DAYS)

            # R by year
            r_by_year = m.get("r_by_year", {})
            neg_years = sum(1 for r in r_by_year.values() if r < 0)

            gate_results.append({
                "candidate": cand_name,
                "gate": gate_name,
                "exclude": ", ".join(sorted(exclude)) if exclude else "(none)",
                "trades": m["total_trades"],
                "trades_removed": compute_metrics(filled)["total_trades"] - m["total_trades"],
                "wr": m["win_rate"],
                "net_r": m["total_r"],
                "max_dd": m["max_drawdown_r"],
                "calmar": m["calmar_ratio"],
                "sharpe": m["sharpe_ratio"],
                "neg_years": neg_years,
                "holdout_r": m_h["total_r"] if m_h else None,
                "holdout_trades": m_h["total_trades"] if m_h else 0,
                "holdout_sharpe": m_h["sharpe_ratio"] if m_h else None,
                "pay_rate": acct["success_rate"],
                "ev_acct": acct["ev_per_account"],
                "avg_days": acct["avg_days_to_payout"],
                "mcb": acct["max_consec_breach"],
                "r_by_year": r_by_year,
            })

    # ── Print results per candidate ───────────────────────────────────────

    for cand_name in SHORT_CANDIDATES:
        cand_rows = [r for r in gate_results if r["candidate"] == cand_name]
        cand_rows.sort(key=lambda r: (r["neg_years"], -(r["calmar"] or 0)))

        print(f"\n\n  ── {cand_name} ──")
        print(f"  {'Gate':<30} {'Trds':>5} {'-Rm':>4} {'WR':>5} {'NetR':>7} {'DD':>7} {'Calm':>6} {'Shrp':>5} {'Neg':>3} {'H-R':>6} {'Pay%':>6} {'EV':>7} {'AvgD':>5} {'MCB':>4}")
        print(f"  {'-'*120}")
        for r in cand_rows:
            hr = f"{r['holdout_r']:+.1f}" if r['holdout_r'] is not None else "—"
            pr = f"{r['pay_rate']:.1%}" if r['pay_rate'] is not None else "N/A"
            avgd = f"{r['avg_days']:.0f}" if r['avg_days'] is not None else "—"
            print(f"  {r['gate']:<30} {r['trades']:>5} {r['trades_removed']:>4} {r['wr']:>4.1%} {r['net_r']:>+7.1f} {r['max_dd']:>7.1f} {r['calmar']:>6.2f} {r['sharpe']:>5.2f} {r['neg_years']:>3} {hr:>6} {pr:>6} {r['ev_acct']:>+7.3f} {avgd:>5} {r['mcb']:>4}")

    # ── Cross-candidate best gates ────────────────────────────────────────

    print(f"\n\n{'=' * 100}")
    print("STEP 3: BEST GATES (ranked by Calmar, 0 negative years preferred)")
    print(f"{'=' * 100}")

    # Filter to 0-neg-year gates first, then rank by calmar
    zero_neg = [r for r in gate_results if r["neg_years"] == 0]
    if zero_neg:
        zero_neg.sort(key=lambda r: -(r["calmar"] or 0))
        print(f"\n  0-negative-year variants ({len(zero_neg)} found):")
        print(f"  {'Candidate':<16} {'Gate':<30} {'Trds':>5} {'WR':>5} {'NetR':>7} {'DD':>7} {'Calm':>6} {'H-R':>6} {'Pay%':>6} {'EV':>7} {'MCB':>4}")
        print(f"  {'-'*120}")
        for r in zero_neg[:20]:
            hr = f"{r['holdout_r']:+.1f}" if r['holdout_r'] is not None else "—"
            pr = f"{r['pay_rate']:.1%}" if r['pay_rate'] is not None else "N/A"
            print(f"  {r['candidate']:<16} {r['gate']:<30} {r['trades']:>5} {r['wr']:>4.1%} {r['net_r']:>+7.1f} {r['max_dd']:>7.1f} {r['calmar']:>6.2f} {hr:>6} {pr:>6} {r['ev_acct']:>+7.3f} {r['mcb']:>4}")
    else:
        print("\n  No 0-negative-year variants found.")

    # Also show top by success rate
    by_pay = sorted(gate_results, key=lambda r: (-(r["pay_rate"] or 0), -(r["ev_acct"] or 0)))
    print(f"\n  Top by payout rate:")
    print(f"  {'Candidate':<16} {'Gate':<30} {'Trds':>5} {'NetR':>7} {'Calm':>6} {'Neg':>3} {'H-R':>6} {'Pay%':>6} {'EV':>7} {'AvgD':>5} {'MCB':>4}")
    print(f"  {'-'*110}")
    for r in by_pay[:15]:
        hr = f"{r['holdout_r']:+.1f}" if r['holdout_r'] is not None else "—"
        pr = f"{r['pay_rate']:.1%}" if r['pay_rate'] is not None else "N/A"
        avgd = f"{r['avg_days']:.0f}" if r['avg_days'] is not None else "—"
        print(f"  {r['candidate']:<16} {r['gate']:<30} {r['trades']:>5} {r['net_r']:>+7.1f} {r['calmar']:>6.2f} {r['neg_years']:>3} {hr:>6} {pr:>6} {r['ev_acct']:>+7.3f} {avgd:>5} {r['mcb']:>4}")

    # ── Year-by-year for top 5 ────────────────────────────────────────────

    print(f"\n\n{'=' * 100}")
    print("YEAR-BY-YEAR for top Calmar variants")
    print(f"{'=' * 100}")

    top_calmar = sorted(gate_results, key=lambda r: (r["neg_years"], -(r["calmar"] or 0)))[:5]
    for r in top_calmar:
        years = sorted(r["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{v:+.1f}" for yr, v in years)
        print(f"\n  {r['candidate']} | {r['gate']}")
        print(f"  Calmar: {r['calmar']:.2f}  |  Net R: {r['net_r']:+.1f}  |  DD: {r['max_dd']:.1f}R  |  Neg years: {r['neg_years']}")
        print(f"  {yr_str}")

    print(f"\n\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
