#!/usr/bin/env python3
"""Council-recommended 4-leg portfolio: yearly payout/breach breakdown.

Runs the 4 legs recommended by the LLM Council:
  1. NQ_NY_LSI (long, Wed+Thu excl)
  2. NQ_Asia ORB (long, ORB 100%, Tue excl)
  3. ES_Asia ORB (long, ORB 125%)
  4. ES_NY ORB (long, Thu excl)

Then simulates staggered prop firm accounts per leg AND combined,
with payouts/breaches broken down by year.
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import apply_dow_filter, TUE, WED, THU
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
PAYOUT_TARGET = 5.0
BREACH_LIMIT = -4.0
CYCLE_DAYS = 14


def simulate_staggered_with_yearly(trades, start_date, end_date,
                                    payout_r=PAYOUT_TARGET, breach_r=BREACH_LIMIT,
                                    stagger_days=CYCLE_DAYS):
    """Simulate staggered accounts and return per-year payout/breach counts."""
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return {"total": 0, "payouts": 0, "breaches": 0, "open": 0,
                "by_year": {}, "results": []}

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
        outcome_date = None
        trades_taken = 0

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
        results.append({
            "account_start": acct_start,
            "outcome": outcome,
            "outcome_date": outcome_date,
            "final_r": cum_r,
            "calendar_days": calendar_days,
            "trades_taken": trades_taken,
        })

    # Aggregate totals
    payouts = [r for r in results if r["outcome"] == "payout"]
    breaches = [r for r in results if r["outcome"] == "breach"]
    opens = [r for r in results if r["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    success_rate = len(payouts) / resolved if resolved > 0 else None

    # EV
    capped_rs = []
    for r in results:
        if r["outcome"] == "payout":
            capped_rs.append(payout_r)
        elif r["outcome"] == "breach":
            capped_rs.append(breach_r)
        else:
            capped_rs.append(r["final_r"])
    ev = float(np.mean(capped_rs)) if capped_rs else 0.0

    # Max consecutive breaches
    max_consec = consec = 0
    for r in results:
        if r["outcome"] == "breach":
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0

    # Avg days to payout
    avg_days = float(np.mean([r["calendar_days"] for r in payouts])) if payouts else None
    median_days_payout = float(np.median([r["calendar_days"] for r in payouts])) if payouts else None
    avg_days_breach = float(np.mean([r["calendar_days"] for r in breaches])) if breaches else None
    median_days_breach = float(np.median([r["calendar_days"] for r in breaches])) if breaches else None

    # Per-year breakdown: use outcome_date year for resolved accounts
    by_year = {}
    for r in results:
        if r["outcome"] in ("payout", "breach"):
            yr = r["outcome_date"].year
        else:
            yr = r["account_start"].year  # open accounts: use start year
        if yr not in by_year:
            by_year[yr] = {"payouts": 0, "breaches": 0, "open": 0}
        key = {"payout": "payouts", "breach": "breaches", "open": "open"}[r["outcome"]]
        by_year[yr][key] += 1

    return {
        "total": len(results),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": success_rate,
        "ev_per_account": round(ev, 3),
        "max_consec_breaches": max_consec,
        "avg_days_to_payout": round(avg_days, 0) if avg_days else None,
        "median_days_to_payout": round(median_days_payout, 0) if median_days_payout else None,
        "avg_days_to_breach": round(avg_days_breach, 0) if avg_days_breach else None,
        "median_days_to_breach": round(median_days_breach, 0) if median_days_breach else None,
        "by_year": by_year,
        "results": results,
    }


def main():
    t_global = time.time()

    # ── Load data ──────────────────────────────────────────────────────────
    print("Loading data...")
    nq_5m = load_5m_data(NQ.data_file)
    nq_1m = load_1m_for_5m(NQ.data_file)
    nq_1s = load_1s_for_5m(NQ.data_file)
    es_5m = load_5m_data(ES.data_file)
    es_1m = load_1m_for_5m(ES.data_file)
    try:
        es_1s = load_1s_for_5m(ES.data_file)
    except FileNotFoundError:
        es_1s = None
    nq_end = nq_5m.index[-1].strftime("%Y-%m-%d")
    es_end = es_5m.index[-1].strftime("%Y-%m-%d")
    print(f"  NQ: {len(nq_5m):,} bars -> {nq_end}")
    print(f"  ES: {len(es_5m):,} bars -> {es_end}")

    # ── Leg configs ────────────────────────────────────────────────────────
    legs = {}

    # 1. NQ_NY_LSI
    legs["NQ_NY_LSI"] = {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY", orb_start="09:30", orb_end="09:45", rth_start="09:30",
                entry_start="09:35", entry_end="15:30",
                flat_start="15:50", flat_end="16:00",
                min_gap_atr_pct=5.0,
            ),),
            instrument=NQ, strategy="lsi",
            use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
            rr=3.0, tp1_ratio=0.34, atr_length=10,
            lsi_n_left=8, lsi_n_right=60,
            lsi_fvg_window_left=20, lsi_fvg_window_right=5,
            lsi_entry_mode="fvg_limit",
        ),
        "df": nq_5m, "df_1m": nq_1m, "df_1s": nq_1s, "end": nq_end,
        "dow_excl": {WED, THU},
    }

    # 2. NQ_Asia ORB
    legs["NQ_Asia"] = {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia", orb_start="20:00", orb_end="20:15",
                entry_start="20:15", entry_end="22:30",
                flat_start="04:00", flat_end="07:00",
                stop_orb_pct=100.0, min_gap_orb_pct=10.0,
            ),),
            instrument=NQ, strategy="continuation",
            use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
            rr=6.0, tp1_ratio=0.3, atr_length=5,
        ),
        "df": nq_5m, "df_1m": nq_1m, "df_1s": nq_1s, "end": nq_end,
        "dow_excl": {TUE},
    }

    # 3. ES_Asia ORB
    legs["ES_Asia"] = {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia", orb_start="20:00", orb_end="20:15",
                entry_start="20:15", entry_end="03:00",
                flat_start="07:00", flat_end="07:00",
                stop_orb_pct=125.0, min_gap_atr_pct=0.5,
                min_stop_points=3.0, min_tp1_points=3.0,
            ),),
            instrument=ES, strategy="continuation",
            use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
            rr=1.5, tp1_ratio=0.7, atr_length=14,
        ),
        "df": es_5m, "df_1m": es_1m, "df_1s": es_1s, "end": es_end,
        "dow_excl": None,
    }

    # 4. ES_NY ORB
    legs["ES_NY"] = {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY", orb_start="09:30", orb_end="09:45",
                entry_start="09:45", entry_end="13:00",
                flat_start="15:50", flat_end="16:00",
                stop_atr_pct=5.0, min_gap_atr_pct=0.25,
                min_stop_points=3.0, min_tp1_points=3.0,
            ),),
            instrument=ES, strategy="continuation",
            use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
            rr=5.0, tp1_ratio=0.2, atr_length=7,
        ),
        "df": es_5m, "df_1m": es_1m, "df_1s": es_1s, "end": es_end,
        "dow_excl": {THU},
    }

    # ── Run backtests and prop sim per leg ──────────────────────────────────
    all_leg_trades = {}
    all_leg_results = {}

    for name, leg in legs.items():
        t0 = time.time()
        trades = run_backtest(
            leg["df"], leg["config"], start_date=START_DATE,
            df_1m=leg["df_1m"], df_1s=leg["df_1s"],
        )
        if leg["dow_excl"]:
            trades = apply_dow_filter(trades, leg["dow_excl"])

        m = compute_metrics(trades)
        pf = simulate_staggered_with_yearly(trades, START_DATE, leg["end"])
        all_leg_trades[name] = trades
        all_leg_results[name] = {"metrics": m, "prop": pf}
        print(f"  {name}: {m['total_trades']} trades, {m['total_r']:+.1f}R, "
              f"Sharpe {m['sharpe_ratio']:.2f}, DD {m['max_drawdown_r']:.1f}R [{time.time()-t0:.1f}s]")

    # ── Combined portfolio simulation ──────────────────────────────────────
    # Merge all filled trades from all legs, sorted by date
    print("\n  Merging trades for combined portfolio...")
    all_filled = []
    for name, trades in all_leg_trades.items():
        for t in trades:
            if t.exit_type != EXIT_NO_FILL:
                all_filled.append(t)

    # Sort by date
    all_filled.sort(key=lambda t: t.date)

    # Use the latest end date
    combined_end = max(leg["end"] for leg in legs.values())
    combined_pf = simulate_staggered_with_yearly(all_filled, START_DATE, combined_end)
    all_leg_results["COMBINED"] = {"prop": combined_pf}

    # ── Print results ──────────────────────────────────────────────────────
    print("\n" + "=" * 130)
    print("  PROP FIRM PAYOUT/BREACH BREAKDOWN — COUNCIL 4-LEG PORTFOLIO")
    print("=" * 130)

    # Get all years across all legs
    all_years = set()
    for name, res in all_leg_results.items():
        all_years.update(res["prop"]["by_year"].keys())
    all_years = sorted(all_years)

    # ── Per-leg totals ──
    print("\n  ┌─ FULL HISTORY TOTALS ─────────────────────────────────────────────────────────┐")
    print(f"  {'Leg':<14} {'Accts':>6} {'Pay':>5} {'Br':>4} {'Op':>3} "
          f"{'Succ%':>6} {'EV':>7} {'MCB':>4} "
          f"{'AvgPay':>7} {'MedPay':>7} {'AvgBr':>7} {'MedBr':>7}")
    print(f"  {'─'*14} {'─'*6} {'─'*5} {'─'*4} {'─'*3} "
          f"{'─'*6} {'─'*7} {'─'*4} "
          f"{'─'*7} {'─'*7} {'─'*7} {'─'*7}")
    for name in list(legs.keys()) + ["COMBINED"]:
        pf = all_leg_results[name]["prop"]
        sr = f"{pf['success_rate']:.1%}" if pf["success_rate"] is not None else "N/A"
        ev = f"{pf['ev_per_account']:+.2f}R" if pf["ev_per_account"] else "N/A"
        dp = f"{pf['avg_days_to_payout']:.0f}d" if pf["avg_days_to_payout"] else "N/A"
        mdp = f"{pf['median_days_to_payout']:.0f}d" if pf.get("median_days_to_payout") else "N/A"
        db = f"{pf['avg_days_to_breach']:.0f}d" if pf.get("avg_days_to_breach") else "N/A"
        mdb = f"{pf['median_days_to_breach']:.0f}d" if pf.get("median_days_to_breach") else "N/A"
        label = f"** {name} **" if name == "COMBINED" else name
        print(f"  {label:<14} {pf['total']:>6} {pf['payouts']:>5} {pf['breaches']:>4} {pf['open']:>3} "
              f"{sr:>6} {ev:>7} {pf['max_consec_breaches']:>4} "
              f"{dp:>7} {mdp:>7} {db:>7} {mdb:>7}")

    # ── Per-year breakdown per leg ──
    print("\n  ┌─ PAYOUTS BY YEAR ─────────────────────────────────────────────────────────────┐")
    header = f"  {'Leg':<14}"
    for yr in all_years:
        header += f" {yr:>6}"
    header += f" {'TOTAL':>7}"
    print(header)
    print(f"  {'─'*14}" + "".join(f" {'─'*6}" for _ in all_years) + f" {'─'*7}")

    for name in list(legs.keys()) + ["COMBINED"]:
        pf = all_leg_results[name]["prop"]
        row = f"  {name:<14}"
        total_p = 0
        for yr in all_years:
            yr_data = pf["by_year"].get(yr, {"payouts": 0})
            p = yr_data.get("payouts", 0)
            total_p += p
            row += f" {p:>6}"
        row += f" {total_p:>7}"
        print(row)

    print(f"\n  ┌─ BREACHES BY YEAR ────────────────────────────────────────────────────────────┐")
    print(header)
    print(f"  {'─'*14}" + "".join(f" {'─'*6}" for _ in all_years) + f" {'─'*7}")

    for name in list(legs.keys()) + ["COMBINED"]:
        pf = all_leg_results[name]["prop"]
        row = f"  {name:<14}"
        total_b = 0
        for yr in all_years:
            yr_data = pf["by_year"].get(yr, {"breaches": 0})
            b = yr_data.get("breaches", 0)
            total_b += b
            row += f" {b:>6}"
        row += f" {total_b:>7}"
        print(row)

    # ── 2025 and 2026 focus ──
    print(f"\n  ┌─ 2025 + 2026 FOCUS ───────────────────────────────────────────────────────────┐")
    print(f"  {'Leg':<14} {'2025 Pay':>8} {'2025 Br':>8} {'2025 %':>7} "
          f"{'2026 Pay':>8} {'2026 Br':>8} {'2026 %':>7}")
    print(f"  {'─'*14} {'─'*8} {'─'*8} {'─'*7} {'─'*8} {'─'*8} {'─'*7}")

    for name in list(legs.keys()) + ["COMBINED"]:
        pf = all_leg_results[name]["prop"]
        for yr_label, yr in [("2025", 2025), ("2026", 2026)]:
            pass  # handled in row below

        yr25 = pf["by_year"].get(2025, {"payouts": 0, "breaches": 0})
        yr26 = pf["by_year"].get(2026, {"payouts": 0, "breaches": 0})
        p25 = yr25.get("payouts", 0)
        b25 = yr25.get("breaches", 0)
        p26 = yr26.get("payouts", 0)
        b26 = yr26.get("breaches", 0)
        r25 = p25 / (p25 + b25) if (p25 + b25) > 0 else 0
        r26 = p26 / (p26 + b26) if (p26 + b26) > 0 else 0
        label = f"** {name} **" if name == "COMBINED" else name
        print(f"  {label:<14} {p25:>8} {b25:>8} {r25:>6.0%} "
              f"{p26:>8} {b26:>8} {r26:>6.0%}")

    # ── Net $ economics ──
    print(f"\n  ┌─ NET $ ECONOMICS (at $100 reset, $500 payout) ────────────────────────────────┐")
    print(f"  {'Leg':<14} {'Payouts':>8} {'Revenue':>10} {'Breaches':>8} {'Cost':>10} {'Net $':>10}")
    print(f"  {'─'*14} {'─'*8} {'─'*10} {'─'*8} {'─'*10} {'─'*10}")

    for name in list(legs.keys()) + ["COMBINED"]:
        pf = all_leg_results[name]["prop"]
        revenue = pf["payouts"] * 500
        cost = pf["breaches"] * 100
        net = revenue - cost
        label = f"** {name} **" if name == "COMBINED" else name
        print(f"  {label:<14} {pf['payouts']:>8} ${revenue:>9,} {pf['breaches']:>8} "
              f"${cost:>9,} ${net:>9,}")

    elapsed = time.time() - t_global
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
