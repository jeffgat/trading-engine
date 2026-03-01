#!/usr/bin/env python3
"""Compare Python backtester results against TradingView export.

Parses a TradingView strategy trade export CSV, groups legs into logical trades,
runs the Python backtest for the same period, and compares trade-by-trade.

Usage:
    python scripts/compare_tv.py --tv-csv ../tradingview_reports/ORB_V5_A_CME_MINI_NQ1!_2026-02-13_c30f6.csv --data NQ_5m.csv --start 2024-01-01 --end 2025-01-01
"""

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, with_overrides, NY_SESSION, ASIA_SESSION
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NAMES, EXIT_NO_FILL


# ---------------------------------------------------------------------------
# TV CSV parsing
# ---------------------------------------------------------------------------

@dataclass
class TVLeg:
    """One leg (row-pair) from the TV export."""
    trade_num: int
    direction: str        # "long" or "short"
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    exit_signal: str      # e.g. "a-l-sl", "n-l-tp1"
    qty: int
    pnl: float


@dataclass
class TVTrade:
    """A logical trade (1-2 legs merged)."""
    date: str             # YYYY-MM-DD of entry (trading day)
    session: str          # "NY" or "Asia"
    direction: str        # "long" or "short"
    entry_time: str
    entry_price: float
    exit_type: str        # mapped to Python exit types
    total_qty: int
    total_pnl: float
    legs: list


def _parse_tv_csv(filepath: str) -> list[TVLeg]:
    """Parse TradingView export CSV into legs."""
    legs = []
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Group rows by trade number (each trade has 2 rows: exit + entry)
        rows_by_trade: dict[int, list[dict]] = {}
        for row in reader:
            tnum = int(row["Trade #"])
            rows_by_trade.setdefault(tnum, []).append(row)

    for tnum, rows in sorted(rows_by_trade.items()):
        entry_row = None
        exit_row = None
        for r in rows:
            if r["Type"].startswith("Entry"):
                entry_row = r
            elif r["Type"].startswith("Exit"):
                exit_row = r

        if entry_row is None or exit_row is None:
            continue

        direction = "long" if "long" in entry_row["Type"] else "short"
        legs.append(TVLeg(
            trade_num=tnum,
            direction=direction,
            entry_time=entry_row["Date and time"],
            entry_price=float(entry_row["Price USD"]),
            exit_time=exit_row["Date and time"],
            exit_price=float(exit_row["Price USD"]),
            exit_signal=exit_row["Signal"],
            qty=int(float(exit_row["Position size (qty)"])),
            pnl=float(exit_row["Net P&L USD"]),
        ))

    return legs


def _map_exit_type(signals: list[str]) -> str:
    """Map TV exit signal(s) to Python exit type name."""
    if len(signals) == 1:
        sig = signals[0]
        if sig.endswith("-sl"):
            return "sl"
        if sig.endswith("-tp2"):
            return "tp2_single"
        if "eod-flat" in sig:
            return "eod"
        if sig.endswith("-tp1"):
            return "tp1_eod"  # single leg tp1 without runner = likely eod'd
        if sig.endswith("-be"):
            return "tp1_be"   # single leg be = probably single contract
        return sig
    elif len(signals) == 2:
        sigs = set(s.split("-")[-1] for s in signals)
        if sigs == {"sl"}:
            return "sl"
        if sigs == {"tp1", "tp2"}:
            return "tp1_tp2"
        if sigs == {"tp1", "be"}:
            return "tp1_be"
        if "tp1" in sigs and any("eod" in s for s in signals):
            return "tp1_eod"
        if all("eod" in s for s in signals):
            return "eod"
        # Fallback
        return "+".join(sorted(signals))
    return "+".join(sorted(signals))


def _group_legs_into_trades(legs: list[TVLeg]) -> list[TVTrade]:
    """Group consecutive legs with same entry time+price into logical trades."""
    trades = []
    i = 0
    while i < len(legs):
        leg = legs[i]
        group = [leg]

        # Look ahead for legs with same entry time and price
        j = i + 1
        while j < len(legs):
            next_leg = legs[j]
            if (next_leg.entry_time == leg.entry_time
                    and next_leg.entry_price == leg.entry_price
                    and next_leg.direction == leg.direction):
                group.append(next_leg)
                j += 1
            else:
                break

        # Determine session from exit signal
        first_signal = group[0].exit_signal
        if first_signal.startswith("a-"):
            session = "Asia"
        elif first_signal.startswith("n-") or first_signal.startswith("ny"):
            session = "NY"
        elif first_signal.startswith("asia"):
            session = "Asia"
        else:
            session = "Unknown"

        # Parse entry date — TV times are in NY timezone
        entry_dt = pd.Timestamp(leg.entry_time, tz="America/New_York")
        # Trading date: use the calendar date of entry
        trade_date = str(entry_dt.date())

        exit_signals = [g.exit_signal for g in group]
        exit_type = _map_exit_type(exit_signals)

        trades.append(TVTrade(
            date=trade_date,
            session=session,
            direction=leg.direction,
            entry_time=leg.entry_time,
            entry_price=leg.entry_price,
            exit_type=exit_type,
            total_qty=sum(g.qty for g in group),
            total_pnl=sum(g.pnl for g in group),
            legs=group,
        ))

        i = j

    return trades


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _compare(tv_trades: list[TVTrade], py_trades: list[dict]) -> dict:
    """Compare TV and Python trades, matching by date + session + direction."""

    # Build lookup: (date, session, direction) -> trade
    tv_lookup: dict[tuple, TVTrade] = {}
    for t in tv_trades:
        key = (t.date, t.session, t.direction)
        if key in tv_lookup:
            # Duplicate — shouldn't happen with 1-trade-per-day enforcement
            print(f"  WARNING: duplicate TV trade key {key}")
        tv_lookup[key] = t

    py_lookup: dict[tuple, dict] = {}
    for t in py_trades:
        key = (t["date"], t["session"], t["direction"])
        if key in py_lookup:
            print(f"  WARNING: duplicate PY trade key {key}")
        py_lookup[key] = t

    all_keys = set(tv_lookup.keys()) | set(py_lookup.keys())
    matched_keys = set(tv_lookup.keys()) & set(py_lookup.keys())
    tv_only = set(tv_lookup.keys()) - set(py_lookup.keys())
    py_only = set(py_lookup.keys()) - set(tv_lookup.keys())

    # Per-match comparison
    entry_matches = 0       # entry price within 1 tick (0.25)
    entry_close = 0         # entry price within 5 points
    exit_type_matches = 0
    pnl_direction_matches = 0
    total_matched = len(matched_keys)

    mismatches = []

    for key in sorted(matched_keys):
        tv = tv_lookup[key]
        py = py_lookup[key]

        entry_diff = abs(tv.entry_price - py["entry_price"])
        if entry_diff <= 0.25:
            entry_matches += 1
        if entry_diff <= 5.0:
            entry_close += 1

        if tv.exit_type == py["exit_type"]:
            exit_type_matches += 1

        tv_win = tv.total_pnl > 0
        py_win = py["pnl_usd"] > 0
        if tv_win == py_win:
            pnl_direction_matches += 1

        if tv.exit_type != py["exit_type"] or entry_diff > 5.0:
            mismatches.append({
                "date": key[0],
                "session": key[1],
                "direction": key[2],
                "tv_entry": tv.entry_price,
                "py_entry": py["entry_price"],
                "entry_diff": round(entry_diff, 2),
                "tv_exit_type": tv.exit_type,
                "py_exit_type": py["exit_type"],
                "tv_pnl": round(tv.total_pnl, 2),
                "py_pnl": round(py["pnl_usd"], 2),
                "tv_qty": tv.total_qty,
                "py_qty": int(py["qty"]),
            })

    return {
        "total_tv": len(tv_trades),
        "total_py": len(py_trades),
        "matched": total_matched,
        "tv_only": len(tv_only),
        "py_only": len(py_only),
        "entry_exact": entry_matches,
        "entry_close_5pt": entry_close,
        "exit_type_match": exit_type_matches,
        "pnl_direction_match": pnl_direction_matches,
        "mismatches": mismatches,
        "tv_only_list": sorted(tv_only),
        "py_only_list": sorted(py_only),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compare Python backtest vs TradingView export")
    parser.add_argument("--tv-csv", required=True, help="Path to TradingView export CSV")
    parser.add_argument("--data", required=True, help="Data file for Python backtest")
    parser.add_argument("--start", default="2024-01-01", help="Start date")
    parser.add_argument("--end", default="2025-01-01", help="End date")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol")
    parser.add_argument("--risk-usd", type=float, default=5000.0, help="Risk per trade USD")
    parser.add_argument("--show-mismatches", type=int, default=20, help="Number of mismatches to show")
    args = parser.parse_args()

    # --- Parse TV trades ---
    print("Parsing TradingView export...")
    legs = _parse_tv_csv(args.tv_csv)
    tv_trades = _group_legs_into_trades(legs)
    print(f"  {len(legs)} legs → {len(tv_trades)} logical trades")

    tv_session_counts = {}
    tv_exit_counts = {}
    for t in tv_trades:
        tv_session_counts[t.session] = tv_session_counts.get(t.session, 0) + 1
        tv_exit_counts[t.exit_type] = tv_exit_counts.get(t.exit_type, 0) + 1
    print(f"  Sessions: {tv_session_counts}")
    print(f"  Exit types: {tv_exit_counts}")

    # --- Run Python backtest ---
    print(f"\nRunning Python backtest ({args.start} to {args.end})...")
    instrument = get_instrument(args.instrument)
    config = default_config(instrument)
    config = with_overrides(config,
                            sessions=(NY_SESSION, ASIA_SESSION),
                            risk_usd=args.risk_usd)

    df = load_5m_data(args.data, start=args.start, end=args.end)
    print(f"  {len(df):,} bars loaded")

    trades = run_backtest(df, config, start_date=args.start)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    print(f"  {len(trades)} signals, {len(filled)} filled trades")

    # Convert to dicts for comparison
    py_trades = []
    for t in filled:
        py_trades.append({
            "date": t.date,
            "session": t.session,
            "direction": "long" if t.direction == 1 else "short",
            "entry_price": t.entry_price,
            "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
            "pnl_usd": t.pnl_usd,
            "qty": t.qty,
        })

    py_session_counts = {}
    py_exit_counts = {}
    for t in py_trades:
        py_session_counts[t["session"]] = py_session_counts.get(t["session"], 0) + 1
        py_exit_counts[t["exit_type"]] = py_exit_counts.get(t["exit_type"], 0) + 1
    print(f"  Sessions: {py_session_counts}")
    print(f"  Exit types: {py_exit_counts}")

    # --- Compare ---
    print("\n" + "=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)

    result = _compare(tv_trades, py_trades)

    print(f"\n  Trade counts:")
    print(f"    TradingView:   {result['total_tv']} logical trades")
    print(f"    Python:        {result['total_py']} filled trades")
    print()
    print(f"  Matching:")
    print(f"    Matched (date+session+dir): {result['matched']}")
    print(f"    TV only (not in Python):    {result['tv_only']}")
    print(f"    Python only (not in TV):    {result['py_only']}")
    print()

    if result["matched"] > 0:
        m = result["matched"]
        print(f"  Among {m} matched trades:")
        print(f"    Entry within 1 tick (0.25): {result['entry_exact']:4d} ({result['entry_exact']/m:.1%})")
        print(f"    Entry within 5 pts:         {result['entry_close_5pt']:4d} ({result['entry_close_5pt']/m:.1%})")
        print(f"    Exit type agreement:        {result['exit_type_match']:4d} ({result['exit_type_match']/m:.1%})")
        print(f"    PnL direction agreement:    {result['pnl_direction_match']:4d} ({result['pnl_direction_match']/m:.1%})")

    # Unmatched trades
    if result["tv_only_list"]:
        print(f"\n  TV-only trades (first 10):")
        for key in result["tv_only_list"][:10]:
            print(f"    {key[0]}  {key[1]:5s}  {key[2]:5s}")

    if result["py_only_list"]:
        print(f"\n  Python-only trades (first 10):")
        for key in result["py_only_list"][:10]:
            print(f"    {key[0]}  {key[1]:5s}  {key[2]:5s}")

    # Mismatches
    if result["mismatches"]:
        n_show = min(len(result["mismatches"]), args.show_mismatches)
        print(f"\n  Mismatches (entry>5pt or exit type differs) — showing {n_show}/{len(result['mismatches'])}:")
        print(f"    {'Date':<12s} {'Sess':5s} {'Dir':5s} {'TV Entry':>10s} {'PY Entry':>10s} {'Diff':>6s} {'TV Exit':>10s} {'PY Exit':>10s} {'TV PnL':>12s} {'PY PnL':>12s}")
        print(f"    {'-'*12} {'-'*5} {'-'*5} {'-'*10} {'-'*10} {'-'*6} {'-'*10} {'-'*10} {'-'*12} {'-'*12}")
        for mm in result["mismatches"][:n_show]:
            print(f"    {mm['date']:<12s} {mm['session']:5s} {mm['direction']:5s} {mm['tv_entry']:>10.2f} {mm['py_entry']:>10.2f} {mm['entry_diff']:>6.2f} {mm['tv_exit_type']:>10s} {mm['py_exit_type']:>10s} {mm['tv_pnl']:>12.2f} {mm['py_pnl']:>12.2f}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
