#!/usr/bin/env python3
"""FAST config variable sweep: direction, stop basis, DOW exclusion.

Tests each FAST leg with structural variants to understand which
design choices are robust vs overfit:
  1. Direction: long only vs both
  2. Stop basis: ATR vs ORB (ORB continuation legs only)
  3. DOW exclusion: with vs without (legs that have exclusions)

Each variant runs the full backtest + staggered prop firm simulation.
"""

import datetime
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import FRI, TUE, WED, THU, apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (
    apply_structure_vwap_gate,
    build_nq_ny_regime_calendar,
    build_structure_vwap_signals,
    filter_trades_by_low_confidence,
    filter_trades_by_regime,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES, GC
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
PAYOUT_TARGET = 5.0
BREACH_LIMIT = -4.0
CYCLE_DAYS = 14


def simulate_staggered_accounts(trades, start_date, end_date,
                                 payout_r=PAYOUT_TARGET, breach_r=BREACH_LIMIT,
                                 stagger_days=CYCLE_DAYS):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return {"success_rate": None, "ev_per_account": 0, "payouts": 0,
                "breaches": 0, "open": 0, "total": 0, "max_consec_breaches": 0,
                "avg_days_to_payout": None}

    trade_data = sorted(
        [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in filled],
        key=lambda x: x["date"],
    )

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

        for t in trade_data:
            if t["date"] < acct_start:
                continue
            cum_r += t["r"]
            trades_taken += 1
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
        results.append({"outcome": outcome, "final_r": cum_r,
                        "calendar_days": calendar_days})

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

    max_consec = consec = 0
    for r in results:
        if r["outcome"] == "breach":
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0

    avg_days = float(np.mean([r["calendar_days"] for r in payouts])) if payouts else None

    # Phase 5: Cohort EV for 10/25/50 accounts
    cohort_evs = {}
    for size in [10, 25, 50]:
        if resolved > 0 and success_rate is not None:
            exp_payouts = round(size * success_rate, 1)
            exp_breaches = round(size * (1 - success_rate), 1)
            cohort_ev = size * ev
            cohort_evs[size] = {
                "payouts": exp_payouts, "breaches": exp_breaches,
                "ev": round(cohort_ev, 1),
            }

    # Breach clustering by year
    breach_by_year = {}
    for r in results:
        if r["outcome"] == "breach":
            yr = r.get("outcome_date", r.get("account_start", ""))[:4] if "outcome_date" in r else ""

    # Handoff rate: accounts that reach payout / total started
    handoff_rate = len(payouts) / len(results) if results else 0

    return {
        "total": len(results), "payouts": len(payouts), "breaches": len(breaches),
        "open": len(opens), "success_rate": success_rate,
        "ev_per_account": round(ev, 3), "max_consec_breaches": max_consec,
        "avg_days_to_payout": round(avg_days, 0) if avg_days else None,
        "cohort_evs": cohort_evs, "handoff_rate": round(handoff_rate, 3),
    }


def run_variant(df, config, start_date, end_date, df_1m=None, df_1s=None,
                dow_excl=None, gate_type=None, bull_cal=None, bull_signals=None):
    """Run a single variant and return metrics + prop results."""
    trades = run_backtest(df, config, start_date=start_date, df_1m=df_1m, df_1s=df_1s)

    if dow_excl:
        trades = apply_dow_filter(trades, dow_excl)

    if gate_type == "bull_specialist" and bull_cal is not None:
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        filled = filter_trades_by_regime(filled, bull_cal, include={"bull"})
        filled = filter_trades_by_low_confidence(filled, bull_cal, include_low_confidence=False)
        filled = apply_structure_vwap_gate(filled, bull_signals, "hh_hl_2_vwap")
        no_fills = [t for t in trades if t.exit_type == EXIT_NO_FILL]
        trades = filled + no_fills

    m = compute_metrics(trades)
    pf = simulate_staggered_accounts(trades, start_date, end_date)
    return m, pf


def print_row(label, m, pf):
    sr = f"{pf['success_rate']:.0%}" if pf["success_rate"] is not None else "N/A"
    ev = f"{pf['ev_per_account']:+.2f}" if pf["ev_per_account"] else "N/A"
    pbo = f"{pf['payouts']}/{pf['breaches']}/{pf['open']}"
    days = f"{pf['avg_days_to_payout']:.0f}" if pf["avg_days_to_payout"] else "N/A"
    neg_years = sum(1 for v in m.get("r_by_year", {}).values() if v < 0)
    print(f"  {label:<30} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
          f"{m['profit_factor']:>5.2f} {m['total_r']:>+8.1f} {m['sharpe_ratio']:>6.3f} "
          f"{m['max_drawdown_r']:>7.1f} {sr:>5} {ev:>6} {pf['max_consec_breaches']:>4} "
          f"{days:>5} {neg_years:>3}")


def section(title):
    print(f"\n{'='*120}\n  {title}\n{'='*120}")
    print(f"  {'Variant':<30} {'Tr':>6} {'WR':>5} {'PF':>5} {'Net R':>8} {'Shrp':>6} "
          f"{'DD':>7} {'Succ':>5} {'EV':>6} {'MCB':>4} {'Days':>5} {'Neg':>3}")
    print(f"  {'-'*30} {'-'*6} {'-'*5} {'-'*5} {'-'*8} {'-'*6} {'-'*7} {'-'*5} "
          f"{'-'*6} {'-'*4} {'-'*5} {'-'*3}")


def main():
    t_global = time.time()

    # Load data
    print("Loading data...")
    data = {}
    for symbol, inst in [("NQ", NQ), ("ES", ES), ("GC", GC)]:
        t0 = time.time()
        df = load_5m_data(inst.data_file)
        df_1m = load_1m_for_5m(inst.data_file)
        try:
            df_1s = load_1s_for_5m(inst.data_file)
        except FileNotFoundError:
            df_1s = None
        data[symbol] = {"5m": df, "1m": df_1m, "1s": df_1s,
                        "end": df.index[-1].strftime("%Y-%m-%d")}
        print(f"  {symbol}: {len(df):,} bars -> {data[symbol]['end']} [{time.time()-t0:.1f}s]")

    # Pre-build bull specialist signals
    print("Building bull specialist signals...")
    bull_cal = build_nq_ny_regime_calendar(data["NQ"]["5m"])
    bull_session = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:50",
        entry_start="09:50", entry_end="12:00",
        flat_start="15:30", flat_end="16:00",
        stop_atr_pct=6.0, min_gap_atr_pct=2.5,
    )
    bull_signals = build_structure_vwap_signals(data["NQ"]["5m"], bull_session, atr_length=12)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 1: NQ_NY
    # ══════════════════════════════════════════════════════════════════════
    section("NQ_NY — Direction + DOW")
    nq_ny_sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="12:00",
        flat_start="15:30", flat_end="16:00",
        stop_atr_pct=7.0, min_gap_atr_pct=2.5,
    )
    d = data["NQ"]
    for direction in ["long", "both"]:
        for dow_label, dow_set in [("Fri excl", {FRI}), ("No DOW excl", set())]:
            cfg = StrategyConfig(
                sessions=(nq_ny_sess,), instrument=NQ, strategy="continuation",
                use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
                rr=3.5, tp1_ratio=0.4, atr_length=12, excluded_dates=("20241218",),
            )
            m, pf = run_variant(d["5m"], cfg, START_DATE, d["end"], d["1m"], d["1s"],
                                dow_excl=dow_set if dow_set else None)
            print_row(f"{direction} | {dow_label}", m, pf)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 2: NQ_NY_BULL_SPECIALIST
    # ══════════════════════════════════════════════════════════════════════
    section("NQ_NY_BULL_SPECIALIST — Direction + DOW")
    nq_bull_sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:50",
        entry_start="09:50", entry_end="12:00",
        flat_start="15:30", flat_end="16:00",
        stop_atr_pct=6.0, min_gap_atr_pct=2.5,
    )
    for direction in ["long", "both"]:
        for dow_label, dow_set in [("Fri excl", {FRI}), ("No DOW excl", set())]:
            cfg = StrategyConfig(
                sessions=(nq_bull_sess,), instrument=NQ, strategy="continuation",
                use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
                rr=3.0, tp1_ratio=0.6, atr_length=12, excluded_dates=("20241218",),
            )
            m, pf = run_variant(d["5m"], cfg, START_DATE, d["end"], d["1m"], d["1s"],
                                dow_excl=dow_set if dow_set else None,
                                gate_type="bull_specialist",
                                bull_cal=bull_cal, bull_signals=bull_signals)
            print_row(f"{direction} | {dow_label}", m, pf)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 3: NQ_Asia — Direction + Stop Basis + DOW
    # ══════════════════════════════════════════════════════════════════════
    section("NQ_Asia — Direction + Stop Basis + DOW")
    for direction in ["long", "both"]:
        for stop_label, sess_kwargs in [
            ("ORB 100%", {"stop_orb_pct": 100.0, "min_gap_orb_pct": 10.0}),
            ("ATR 5%", {"stop_atr_pct": 5.0, "min_gap_atr_pct": 1.0}),
            ("ATR 7%", {"stop_atr_pct": 7.0, "min_gap_atr_pct": 1.0}),
        ]:
            for dow_label, dow_set in [("Tue excl", {TUE}), ("No DOW excl", set())]:
                sess = SessionConfig(
                    name="Asia", orb_start="20:00", orb_end="20:15",
                    entry_start="20:15", entry_end="22:30",
                    flat_start="04:00", flat_end="07:00",
                    **sess_kwargs,
                )
                cfg = StrategyConfig(
                    sessions=(sess,), instrument=NQ, strategy="continuation",
                    use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
                    rr=6.0, tp1_ratio=0.3, atr_length=5, excluded_dates=("20241218",),
                )
                m, pf = run_variant(d["5m"], cfg, START_DATE, d["end"], d["1m"], d["1s"],
                                    dow_excl=dow_set if dow_set else None)
                print_row(f"{direction} | {stop_label} | {dow_label}", m, pf)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 4: GC_NY — Direction + DOW
    # ══════════════════════════════════════════════════════════════════════
    section("GC_NY — Direction + DOW")
    gc_sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:40",
        entry_start="09:40", entry_end="12:00",
        flat_start="13:30", flat_end="16:00",
        stop_atr_pct=4.5, min_gap_atr_pct=3.0,
    )
    g = data["GC"]
    for direction in ["long", "both"]:
        for dow_label, dow_set in [("Fri excl", {FRI}), ("No DOW excl", set())]:
            cfg = StrategyConfig(
                sessions=(gc_sess,), instrument=GC, strategy="continuation",
                use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
                rr=9.0, tp1_ratio=0.35, atr_length=7, impulse_close_filter=True,
                excluded_dates=FOMC_DATES,
            )
            m, pf = run_variant(g["5m"], cfg, START_DATE, g["end"], g["1m"], g["1s"],
                                dow_excl=dow_set if dow_set else None)
            print_row(f"{direction} | {dow_label}", m, pf)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 5: ES_NY — Direction + DOW
    # ══════════════════════════════════════════════════════════════════════
    section("ES_NY — Direction + DOW")
    es_ny_sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=5.0, min_gap_atr_pct=0.25,
        min_stop_points=3.0, min_tp1_points=3.0,
    )
    e = data["ES"]
    for direction in ["long", "both"]:
        for dow_label, dow_set in [("Thu excl", {THU}), ("No DOW excl", set())]:
            cfg = StrategyConfig(
                sessions=(es_ny_sess,), instrument=ES, strategy="continuation",
                use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
                rr=5.0, tp1_ratio=0.2, atr_length=7, excluded_dates=("20241218",),
            )
            m, pf = run_variant(e["5m"], cfg, START_DATE, e["end"], e["1m"], e["1s"],
                                dow_excl=dow_set if dow_set else None)
            print_row(f"{direction} | {dow_label}", m, pf)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 6: ES_Asia — Direction + Stop Basis
    # ══════════════════════════════════════════════════════════════════════
    section("ES_Asia — Direction + Stop Basis")
    for direction in ["long", "both"]:
        for stop_label, sess_kwargs in [
            ("ORB 125%", {"stop_orb_pct": 125.0, "min_gap_atr_pct": 0.5}),
            ("ATR 5%", {"stop_atr_pct": 5.0, "min_gap_atr_pct": 0.5}),
            ("ATR 7%", {"stop_atr_pct": 7.0, "min_gap_atr_pct": 0.5}),
        ]:
            sess = SessionConfig(
                name="Asia", orb_start="20:00", orb_end="20:15",
                entry_start="20:15", entry_end="03:00",
                flat_start="07:00", flat_end="07:00",
                min_stop_points=3.0, min_tp1_points=3.0,
                **sess_kwargs,
            )
            cfg = StrategyConfig(
                sessions=(sess,), instrument=ES, strategy="continuation",
                use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
                rr=1.5, tp1_ratio=0.7, atr_length=14, excluded_dates=("20241218",),
            )
            m, pf = run_variant(e["5m"], cfg, START_DATE, e["end"], e["1m"], e["1s"])
            print_row(f"{direction} | {stop_label}", m, pf)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 7: NQ_LDN — Direction only (no DOW excl in anchor)
    # ══════════════════════════════════════════════════════════════════════
    section("NQ_LDN — Direction")
    nq_ldn_sess = SessionConfig(
        name="LDN", orb_start="03:00", orb_end="03:30",
        entry_start="03:30", entry_end="08:25",
        flat_start="08:20", flat_end="08:25",
        stop_atr_pct=1.5, min_gap_atr_pct=1.0,
    )
    for direction in ["long", "both"]:
        cfg = StrategyConfig(
            sessions=(nq_ldn_sess,), instrument=NQ, strategy="continuation",
            use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
            rr=6.0, tp1_ratio=0.7, atr_length=10, excluded_dates=("20241218",),
        )
        m, pf = run_variant(d["5m"], cfg, START_DATE, d["end"], d["1m"], d["1s"])
        print_row(f"{direction}", m, pf)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 8: NQ_Asia_LSI — Direction only
    # ══════════════════════════════════════════════════════════════════════
    section("NQ_Asia_LSI — Direction")
    nq_asia_lsi_sess = SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:05", rth_start="20:00",
        entry_start="20:40", entry_end="23:30",
        flat_start="04:00", flat_end="07:00",
        min_gap_atr_pct=1.75,
    )
    for direction in ["long", "both"]:
        cfg = StrategyConfig(
            sessions=(nq_asia_lsi_sess,), instrument=NQ, strategy="lsi",
            use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
            rr=2.0, tp1_ratio=0.7, atr_length=40,
            lsi_n_left=8, lsi_n_right=2,
            lsi_fvg_window_left=15, lsi_fvg_window_right=2,
            lsi_entry_mode="close", excluded_dates=("20241218",),
        )
        m, pf = run_variant(d["5m"], cfg, START_DATE, d["end"], d["1m"], d["1s"])
        print_row(f"{direction}", m, pf)

    # ══════════════════════════════════════════════════════════════════════
    # LEG 9: NQ_NY_LSI — Direction + DOW
    # ══════════════════════════════════════════════════════════════════════
    section("NQ_NY_LSI — Direction + DOW")
    nq_ny_lsi_sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:45", rth_start="09:30",
        entry_start="09:35", entry_end="15:30",
        flat_start="15:50", flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    for direction in ["long", "both"]:
        for dow_label, dow_set in [("Wed+Thu excl", {WED, THU}), ("No DOW excl", set())]:
            cfg = StrategyConfig(
                sessions=(nq_ny_lsi_sess,), instrument=NQ, strategy="lsi",
                use_bar_magnifier=True, risk_usd=5000.0, direction_filter=direction,
                rr=3.0, tp1_ratio=0.34, atr_length=10,
                lsi_n_left=8, lsi_n_right=60,
                lsi_fvg_window_left=20, lsi_fvg_window_right=5,
                lsi_entry_mode="fvg_limit", excluded_dates=("20241218",),
            )
            m, pf = run_variant(d["5m"], cfg, START_DATE, d["end"], d["1m"], d["1s"],
                                dow_excl=dow_set if dow_set else None)
            print_row(f"{direction} | {dow_label}", m, pf)

    elapsed = time.time() - t_global
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
