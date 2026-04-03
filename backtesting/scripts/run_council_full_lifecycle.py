#!/usr/bin/env python3
"""Council 4-leg portfolio: full account lifecycle simulation.

Models the complete prop firm account lifecycle:
  Phase 1 (Sprint): $50K start, risk $400/trade, target $52.5K (+5R at $500/R),
                     breach at trailing DD floor. Cost: $150 to start.
  Phase 2 (Extraction): After first payout ($500 withdrawal), risk $200/trade.
                         Every Friday, if balance > $52.5K, withdraw to $52K.
                         Account dies when balance hits trailing DD floor.

Trailing DD: floor starts at $48K, trails EOD balance upward,
             stops trailing once it reaches $50K. Account breaches when
             balance touches the floor.

Tracks: total $ withdrawn per account over full lifetime, net profit
        after $150 startup cost.
"""

import datetime
import sys
import time
from collections import defaultdict
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
CYCLE_DAYS = 14

# ── Account model ──────────────────────────────────────────────────────────
ACCOUNT_START = 50_000.0
TRAILING_DD = 2_000.0        # trailing drawdown amount
TRAIL_STOP_AT = 52_000.0     # floor stops trailing once it reaches this
FIRST_PAYOUT_TARGET = 52_500.0
FIRST_PAYOUT_WITHDRAWAL = 500.0
PHASE2_RISK_USD = 200.0      # risk per trade after first payout
PHASE1_RISK_USD = 400.0      # risk per trade during sprint
WEEKLY_WITHDRAWAL_THRESHOLD = 52_500.0  # must be above this to withdraw on Friday
WEEKLY_WITHDRAWAL_FLOOR = 52_000.0      # withdraw down to this level
ACCOUNT_COST = 150.0          # cost to start each account


def simulate_full_lifecycle(trade_data, start_date, end_date, stagger_days=CYCLE_DAYS):
    """Simulate staggered accounts with full lifecycle (sprint + extraction).

    trade_data: list of {"date": datetime.date, "r": float} sorted by date.
    Returns list of account results with total withdrawals and lifecycle stats.
    """
    d_start = datetime.date.fromisoformat(start_date)
    d_end = datetime.date.fromisoformat(end_date)

    account_starts = []
    s = d_start
    while s <= d_end:
        account_starts.append(s)
        s += datetime.timedelta(days=stagger_days)

    results = []

    for acct_start in account_starts:
        balance = ACCOUNT_START
        floor = ACCOUNT_START - TRAILING_DD  # starts at $48K
        phase = "sprint"  # or "extraction"
        risk_usd = PHASE1_RISK_USD
        total_withdrawn = 0.0
        withdrawals = []  # list of (date, amount)
        trades_taken = 0
        outcome = "open"
        outcome_date = None
        first_payout_date = None
        peak_balance = ACCOUNT_START
        last_processed_date = None

        for t in trade_data:
            if t["date"] < acct_start:
                continue

            # Before processing trade: check for Friday withdrawal (phase 2)
            if phase == "extraction" and t["date"] != last_processed_date:
                # Check all Fridays between last_processed_date and t["date"]
                check_start = (last_processed_date + datetime.timedelta(days=1)
                               if last_processed_date else t["date"])
                check_end = t["date"]
                d = check_start
                while d <= check_end:
                    if d.weekday() == 4:  # Friday
                        if balance > WEEKLY_WITHDRAWAL_THRESHOLD:
                            withdrawal = balance - WEEKLY_WITHDRAWAL_FLOOR
                            balance = WEEKLY_WITHDRAWAL_FLOOR
                            total_withdrawn += withdrawal
                            withdrawals.append((d, withdrawal))
                    d += datetime.timedelta(days=1)

            # Process trade
            # Convert R to $ using current phase risk
            dollar_pnl = t["r"] * risk_usd
            balance += dollar_pnl
            trades_taken += 1
            last_processed_date = t["date"]

            # Update trailing DD floor (trails EOD high-water mark)
            if balance > peak_balance:
                peak_balance = balance
                new_floor = peak_balance - TRAILING_DD
                if new_floor > floor and floor < TRAIL_STOP_AT:
                    # Floor trails up but stops at TRAIL_STOP_AT
                    floor = min(new_floor, TRAIL_STOP_AT)

            # Check breach
            if balance <= floor:
                outcome = "breach"
                outcome_date = t["date"]
                break

            # Check first payout (phase 1 -> phase 2 transition)
            if phase == "sprint" and balance >= FIRST_PAYOUT_TARGET:
                # Withdraw first payout
                balance -= FIRST_PAYOUT_WITHDRAWAL
                total_withdrawn += FIRST_PAYOUT_WITHDRAWAL
                withdrawals.append((t["date"], FIRST_PAYOUT_WITHDRAWAL))
                first_payout_date = t["date"]
                phase = "extraction"
                risk_usd = PHASE2_RISK_USD

        # If still open, check final Fridays
        if outcome == "open" and phase == "extraction" and last_processed_date:
            # No more trades, but account is still alive
            outcome_date = last_processed_date

        if outcome_date is None:
            future = [t for t in trade_data if t["date"] >= acct_start]
            outcome_date = future[-1]["date"] if future else acct_start

        calendar_days = (outcome_date - acct_start).days + 1
        sprint_days = None
        extraction_days = None
        if first_payout_date:
            sprint_days = (first_payout_date - acct_start).days + 1
            extraction_days = (outcome_date - first_payout_date).days
        elif outcome == "breach":
            sprint_days = calendar_days  # breached during sprint

        results.append({
            "account_start": acct_start,
            "outcome": outcome,
            "phase_at_end": phase,
            "balance": round(balance, 2),
            "floor": round(floor, 2),
            "total_withdrawn": round(total_withdrawn, 2),
            "n_withdrawals": len(withdrawals),
            "withdrawals": withdrawals,
            "trades_taken": trades_taken,
            "calendar_days": calendar_days,
            "sprint_days": sprint_days,
            "extraction_days": extraction_days,
            "first_payout_date": first_payout_date,
            "outcome_date": outcome_date,
            "net_profit": round(total_withdrawn - ACCOUNT_COST, 2),
            "reached_extraction": phase == "extraction" or first_payout_date is not None,
        })

    return results


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

    # ── Leg configs (same as council portfolio) ────────────────────────────
    legs = {}

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

    # ── Run backtests ──────────────────────────────────────────────────────
    all_leg_trades = {}
    for name, leg in legs.items():
        t0 = time.time()
        trades = run_backtest(
            leg["df"], leg["config"], start_date=START_DATE,
            df_1m=leg["df_1m"], df_1s=leg["df_1s"],
        )
        if leg["dow_excl"]:
            trades = apply_dow_filter(trades, leg["dow_excl"])
        all_leg_trades[name] = trades
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        m = compute_metrics(trades)
        print(f"  {name}: {m['total_trades']} trades, {m['total_r']:+.1f}R [{time.time()-t0:.1f}s]")

    # ── Build merged trade stream for combined portfolio ───────────────────
    # Normalize R to $ using the backtest risk_usd ($5000) to get true R,
    # then the simulation applies phase-specific risk_usd
    all_filled = []
    for name, trades in all_leg_trades.items():
        for t in trades:
            if t.exit_type != EXIT_NO_FILL:
                all_filled.append({"date": datetime.date.fromisoformat(t.date),
                                   "r": t.r_multiple})
    all_filled.sort(key=lambda x: x["date"])
    combined_end = max(leg["end"] for leg in legs.values())

    # Also build per-leg trade data
    per_leg_data = {}
    for name, trades in all_leg_trades.items():
        filled = [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple}
                  for t in trades if t.exit_type != EXIT_NO_FILL]
        filled.sort(key=lambda x: x["date"])
        per_leg_data[name] = filled

    # ── Run full lifecycle simulation ──────────────────────────────────────
    print("\n  Running full lifecycle simulation...")

    sim_results = {}
    for name in list(legs.keys()) + ["COMBINED"]:
        td = all_filled if name == "COMBINED" else per_leg_data[name]
        end = combined_end if name == "COMBINED" else legs[name]["end"]
        sim_results[name] = simulate_full_lifecycle(td, START_DATE, end)

    # ── Print results ──────────────────────────────────────────────────────
    print("\n" + "=" * 140)
    print("  FULL LIFECYCLE SIMULATION — COUNCIL 4-LEG PORTFOLIO")
    print(f"  Sprint: ${ACCOUNT_START:,.0f} start, ${PHASE1_RISK_USD:.0f}/trade risk, "
          f"target ${FIRST_PAYOUT_TARGET:,.0f}, trailing DD ${TRAILING_DD:,.0f}")
    print(f"  Extraction: ${PHASE2_RISK_USD:.0f}/trade risk, withdraw above "
          f"${WEEKLY_WITHDRAWAL_THRESHOLD:,.0f} to ${WEEKLY_WITHDRAWAL_FLOOR:,.0f} every Friday")
    print(f"  Account cost: ${ACCOUNT_COST:.0f}")
    print("=" * 140)

    for name in list(legs.keys()) + ["COMBINED"]:
        res = sim_results[name]
        total = len(res)
        reached_extraction = [r for r in res if r["reached_extraction"]]
        sprint_breaches = [r for r in res if r["outcome"] == "breach" and not r["reached_extraction"]]
        extraction_breaches = [r for r in res if r["outcome"] == "breach" and r["reached_extraction"]]
        still_open = [r for r in res if r["outcome"] == "open"]

        total_withdrawn_all = sum(r["total_withdrawn"] for r in res)
        total_cost = total * ACCOUNT_COST
        total_net = total_withdrawn_all - total_cost

        avg_withdrawn_per_acct = np.mean([r["total_withdrawn"] for r in res])
        avg_net_per_acct = np.mean([r["net_profit"] for r in res])

        # Accounts that reached extraction
        if reached_extraction:
            avg_withdrawals_ext = np.mean([r["n_withdrawals"] for r in reached_extraction])
            avg_total_withdrawn_ext = np.mean([r["total_withdrawn"] for r in reached_extraction])
            avg_extraction_days = np.mean([r["extraction_days"] for r in reached_extraction
                                           if r["extraction_days"] is not None])
            med_extraction_days = np.median([r["extraction_days"] for r in reached_extraction
                                             if r["extraction_days"] is not None])
            avg_sprint_days_ext = np.mean([r["sprint_days"] for r in reached_extraction
                                           if r["sprint_days"] is not None])
        else:
            avg_withdrawals_ext = avg_total_withdrawn_ext = 0
            avg_extraction_days = med_extraction_days = avg_sprint_days_ext = 0

        # Sprint breach stats
        if sprint_breaches:
            avg_sprint_breach_days = np.mean([r["sprint_days"] for r in sprint_breaches
                                              if r["sprint_days"] is not None])
        else:
            avg_sprint_breach_days = 0

        label = f"{'='*5} {name} {'='*5}" if name == "COMBINED" else name
        print(f"\n  ┌─ {label} {'─' * max(0, 90 - len(label))}┐")

        print(f"  │ Accounts started:       {total:>6}     (cost: ${total_cost:>10,.0f})")
        print(f"  │ Reached extraction:      {len(reached_extraction):>6}     ({len(reached_extraction)/total:.0%} of accounts)")
        print(f"  │ Sprint breaches:         {len(sprint_breaches):>6}     (never reached first payout)")
        print(f"  │ Extraction breaches:     {len(extraction_breaches):>6}     (breached after first payout)")
        print(f"  │ Still open:              {len(still_open):>6}")
        print(f"  │")
        print(f"  │ Total $ withdrawn:                  ${total_withdrawn_all:>12,.2f}")
        print(f"  │ Total account costs:                ${total_cost:>12,.2f}")
        print(f"  │ ─────────────────────────────────────────────────────")
        print(f"  │ NET PROFIT:                         ${total_net:>12,.2f}")
        print(f"  │")
        print(f"  │ Avg withdrawn / account:            ${avg_withdrawn_per_acct:>12,.2f}")
        print(f"  │ Avg net profit / account:           ${avg_net_per_acct:>12,.2f}")
        print(f"  │")
        if reached_extraction:
            print(f"  │ Among accounts that reached extraction:")
            print(f"  │   Avg sprint duration:              {avg_sprint_days_ext:>8.0f} days")
            print(f"  │   Avg extraction duration:          {avg_extraction_days:>8.0f} days")
            print(f"  │   Med extraction duration:          {med_extraction_days:>8.0f} days")
            print(f"  │   Avg # withdrawals:                {avg_withdrawals_ext:>8.1f}")
            print(f"  │   Avg total withdrawn:              ${avg_total_withdrawn_ext:>10,.2f}")
        if sprint_breaches:
            print(f"  │ Sprint breaches avg duration:       {avg_sprint_breach_days:>8.0f} days")

        # ── Per-year breakdown ──
        by_year = defaultdict(lambda: {"started": 0, "reached_ext": 0, "sprint_breach": 0,
                                        "ext_breach": 0, "withdrawn": 0.0, "open": 0})
        for r in res:
            yr = r["account_start"].year
            by_year[yr]["started"] += 1
            if r["reached_extraction"]:
                by_year[yr]["reached_ext"] += 1
            if r["outcome"] == "breach" and not r["reached_extraction"]:
                by_year[yr]["sprint_breach"] += 1
            if r["outcome"] == "breach" and r["reached_extraction"]:
                by_year[yr]["ext_breach"] += 1
            if r["outcome"] == "open":
                by_year[yr]["open"] += 1
            by_year[yr]["withdrawn"] += r["total_withdrawn"]

        years = sorted(by_year.keys())
        print(f"  │")
        print(f"  │ {'Year':>6} {'Start':>6} {'ExtOK':>6} {'SpBr':>6} {'ExBr':>6} "
              f"{'Open':>5} {'Withdrawn':>12} {'Cost':>8} {'Net':>12}")
        print(f"  │ {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*6} {'─'*5} {'─'*12} {'─'*8} {'─'*12}")
        for yr in years:
            d = by_year[yr]
            cost = d["started"] * ACCOUNT_COST
            net = d["withdrawn"] - cost
            print(f"  │ {yr:>6} {d['started']:>6} {d['reached_ext']:>6} "
                  f"{d['sprint_breach']:>6} {d['ext_breach']:>6} {d['open']:>5} "
                  f"${d['withdrawn']:>11,.2f} ${cost:>7,.0f} ${net:>11,.2f}")

        # Totals row
        t_started = sum(d["started"] for d in by_year.values())
        t_ext = sum(d["reached_ext"] for d in by_year.values())
        t_sbr = sum(d["sprint_breach"] for d in by_year.values())
        t_ebr = sum(d["ext_breach"] for d in by_year.values())
        t_open = sum(d["open"] for d in by_year.values())
        t_w = sum(d["withdrawn"] for d in by_year.values())
        t_c = t_started * ACCOUNT_COST
        t_n = t_w - t_c
        print(f"  │ {'TOTAL':>6} {t_started:>6} {t_ext:>6} {t_sbr:>6} {t_ebr:>6} "
              f"{t_open:>5} ${t_w:>11,.2f} ${t_c:>7,.0f} ${t_n:>11,.2f}")
        print(f"  └{'─' * 105}┘")

    elapsed = time.time() - t_global
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
