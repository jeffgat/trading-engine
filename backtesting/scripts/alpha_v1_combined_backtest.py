#!/usr/bin/env python3
"""
ALPHA V1 Combined Portfolio Backtest
Runs all 4 legs on actual data, merges trade streams, simulates prop accounts.
Periods: Full history, 2024, 2025, 2026 YTD
"""
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.analysis.gates import apply_dow_filter

# ── Instruments ──────────────────────────────────────────────────────────
NQ = get_instrument("NQ")
ES = get_instrument("ES")

# ── Leg 1: NQ NY LSI (FAST_V1.1) ────────────────────────────────────────
LEG1_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)
LEG1_CONFIG = StrategyConfig(
    sessions=(LEG1_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=3.0, tp1_ratio=0.34, atr_length=10,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(2, 3),  # Wed+Thu
)

# ── Leg 2: NQ Asia ORB ──────────────────────────────────────────────────
LEG2_SESSION = SessionConfig(
    name="Asia", orb_start="20:00", orb_end="20:15",
    entry_start="20:15", entry_end="22:30",
    flat_start="04:00", flat_end="07:00",
    stop_orb_pct=100.0, min_gap_orb_pct=10.0,
)
LEG2_CONFIG = StrategyConfig(
    sessions=(LEG2_SESSION,), instrument=NQ, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=6.0, tp1_ratio=0.3, atr_length=5,
    excluded_days=(1,),  # Tue
)

# ── Leg 3: ES Asia ORB Cont ─────────────────────────────────────────────
LEG3_SESSION = SessionConfig(
    name="Asia", orb_start="20:00", orb_end="20:15",
    entry_start="20:15", entry_end="03:00",
    flat_start="07:00", flat_end="07:00",
    stop_orb_pct=125.0, min_gap_atr_pct=0.5,
    min_stop_points=3.0, min_tp1_points=3.0,
)
LEG3_CONFIG = StrategyConfig(
    sessions=(LEG3_SESSION,), instrument=ES, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=1.5, tp1_ratio=0.7, atr_length=14,
)

# ── Leg 4: ES NY ORB Cont ───────────────────────────────────────────────
LEG4_SESSION = SessionConfig(
    name="NY", orb_start="09:30", orb_end="09:45",
    entry_start="09:45", entry_end="13:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=5.0, min_gap_atr_pct=0.25,
    min_stop_points=3.0, min_tp1_points=3.0,
)
LEG4_CONFIG = StrategyConfig(
    sessions=(LEG4_SESSION,), instrument=ES, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=5.0, tp1_ratio=0.2, atr_length=7,
    excluded_days=(3,),  # Thu
)

# ── All legs ─────────────────────────────────────────────────────────────
LEGS = [
    ("NQ_NY_LSI",    LEG1_CONFIG, "NQ"),
    ("NQ_ASIA_ORB",  LEG2_CONFIG, "NQ"),
    ("ES_ASIA_CONT", LEG3_CONFIG, "ES"),
    ("ES_NY_CONT",   LEG4_CONFIG, "ES"),
]

# ── Prop firm sim ────────────────────────────────────────────────────────
PAYOUT_USD = 2500
BREACH_USD = -2000
STAGGER_DAYS = 14


def simulate_staggered_accounts(dated_daily_r, payout_r, breach_r, stagger_calendar_days=14):
    """Simulate staggered accounts using calendar-day stagger.

    dated_daily_r: list of (date_str, r_value) tuples sorted by date.
    Accounts start every stagger_calendar_days calendar days.
    """
    if not dated_daily_r:
        return []

    from datetime import datetime, timedelta

    dates = [d for d, _ in dated_daily_r]
    r_vals = [r for _, r in dated_daily_r]
    first_date = datetime.strptime(dates[0], "%Y-%m-%d")
    last_date = datetime.strptime(dates[-1], "%Y-%m-%d")

    # Build date->index lookup
    date_to_idx = {d: i for i, d in enumerate(dates)}

    # Generate account start dates every N calendar days
    results = []
    start_date = first_date
    while start_date <= last_date:
        start_str = start_date.strftime("%Y-%m-%d")
        # Find first trading day on or after start_date
        first_trading_idx = None
        for i, d in enumerate(dates):
            if d >= start_str:
                first_trading_idx = i
                break

        if first_trading_idx is not None:
            eq = 0.0
            trading_days = 0
            status = "OPEN"
            for idx in range(first_trading_idx, len(dates)):
                trading_days += 1
                eq += r_vals[idx]
                if eq >= payout_r:
                    status = "PAYOUT"; break
                elif eq <= breach_r:
                    status = "BREACH"; break

            # Calendar days from account start to resolution
            end_dt = datetime.strptime(dates[min(idx, len(dates)-1)], "%Y-%m-%d") if status != "OPEN" else datetime.strptime(dates[-1], "%Y-%m-%d")
            cal_days = (end_dt - start_date).days + 1

            results.append({
                "start": start_str, "days": trading_days, "cal_days": cal_days,
                "equity_r": eq, "status": status,
            })

        start_date += timedelta(days=stagger_calendar_days)

    return results


def analyze_accounts(results):
    payouts = [r for r in results if r["status"] == "PAYOUT"]
    breaches = [r for r in results if r["status"] == "BREACH"]
    opens = [r for r in results if r["status"] == "OPEN"]
    resolved = payouts + breaches
    pr = len(payouts) / len(resolved) * 100 if resolved else 0
    br = len(breaches) / len(resolved) * 100 if resolved else 0
    apd = np.mean([p["cal_days"] for p in payouts]) if payouts else float('nan')
    abd = np.mean([b["cal_days"] for b in breaches]) if breaches else float('nan')
    apd_td = np.mean([p["days"] for p in payouts]) if payouts else float('nan')
    abd_td = np.mean([b["days"] for b in breaches]) if breaches else float('nan')
    seq = [r["status"] for r in sorted(results, key=lambda x: x["start"]) if r["status"] in ("PAYOUT", "BREACH")]
    mcb = mcp = cb = cp = 0
    for s in seq:
        if s == "BREACH": cb += 1; cp = 0; mcb = max(mcb, cb)
        else: cp += 1; cb = 0; mcp = max(mcp, cp)
    return {
        "payouts": len(payouts), "breaches": len(breaches), "open": len(opens),
        "payout_rate": pr, "breach_rate": br,
        "avg_payout_days": apd, "avg_breach_days": abd,
        "avg_payout_td": apd_td, "avg_breach_td": abd_td,
        "max_consec_breach": mcb, "max_consec_payout": mcp,
    }


def trades_to_daily_r(filled_trades, start_date=None, end_date=None):
    """Convert trade list to daily R series indexed by date."""
    daily = defaultdict(float)
    for t in filled_trades:
        date_str = str(t.date)[:10] if hasattr(t.date, 'strftime') else t.date[:10]
        daily[date_str] += t.r_multiple

    if not daily:
        return []

    # Build contiguous daily series (trading days only = days with any activity across legs)
    all_dates = sorted(daily.keys())
    if start_date:
        all_dates = [d for d in all_dates if d >= start_date]
    if end_date:
        all_dates = [d for d in all_dates if d < end_date]

    return [(d, daily.get(d, 0.0)) for d in all_dates]


def build_daily_r_from_dates(dated_r, trading_dates):
    """Map dated R values onto a trading calendar, filling non-trade days with 0."""
    r_by_date = dict(dated_r)
    return [r_by_date.get(d, 0.0) for d in trading_dates]


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    t0_total = time.time()

    # Load data
    print("=" * 90)
    print("  ALPHA V1 COMBINED PORTFOLIO BACKTEST — ACTUAL TRADE DATA")
    print("=" * 90)

    data_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    data = {}
    maps_cache = {}

    for symbol in ("NQ", "ES"):
        print(f"\nLoading {symbol}...")
        t0 = time.time()
        df = load_5m_data(str(data_dir / f"{symbol}_5m.csv"))
        df_1m = load_1m_for_5m(str(data_dir / f"{symbol}_5m.csv"))
        try:
            df_1s = load_1s_for_5m(str(data_dir / f"{symbol}_5m.csv"))
        except Exception:
            df_1s = None
        data[symbol] = {"5m": df, "1m": df_1m, "1s": df_1s}
        maps_cache[symbol] = build_maps(df, df_1m=df_1m, df_1s=df_1s)
        print(f"  {len(df):,} bars ({df.index[0].date()} → {df.index[-1].date()}) [{time.time()-t0:.1f}s]")

    # Run each leg
    leg_trades = {}
    for leg_name, config, symbol in LEGS:
        print(f"\nRunning {leg_name}...")
        t0 = time.time()
        d = data[symbol]
        trades = run_backtest(d["5m"], config, df_1m=d["1m"], df_1s=d["1s"], _maps=maps_cache[symbol])
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        leg_trades[leg_name] = filled
        net_r = sum(t.r_multiple for t in filled)
        wr = sum(1 for t in filled if t.r_multiple > 0) / len(filled) * 100 if filled else 0
        print(f"  {len(filled)} trades, Net R: {net_r:+.1f}, WR: {wr:.1f}% [{time.time()-t0:.1f}s]")

    # Build trading calendar from all legs
    all_dates = set()
    for trades in leg_trades.values():
        for t in trades:
            all_dates.add(str(t.date)[:10])
    trading_calendar = sorted(all_dates)

    # ── Analyze periods ──────────────────────────────────────────────────
    risk_profiles = {
        "UNIFORM $400": {"NQ_NY_LSI": 400, "NQ_ASIA_ORB": 400, "ES_ASIA_CONT": 400, "ES_NY_CONT": 400},
        "ADJUSTED":     {"NQ_NY_LSI": 400, "NQ_ASIA_ORB": 300, "ES_ASIA_CONT": 200, "ES_NY_CONT": 300},
    }

    periods = {
        "FULL HISTORY": (None, None),
        "2025": ("2025-01-01", "2026-01-01"),
        "2026 YTD": ("2026-01-01", None),
    }

    for period_name, (start, end) in periods.items():
        # Filter trading calendar for period
        cal = trading_calendar
        if start:
            cal = [d for d in cal if d >= start]
        if end:
            cal = [d for d in cal if d < end]

        if not cal:
            continue

        from datetime import datetime
        first_dt = datetime.strptime(cal[0], "%Y-%m-%d")
        last_dt = datetime.strptime(cal[-1], "%Y-%m-%d")
        cal_span = (last_dt - first_dt).days
        n_accts = cal_span // 14 + 1

        print(f"\n{'='*90}")
        print(f"  {period_name}  |  {cal[0]} → {cal[-1]}  |  {cal_span} cal days  |  {len(cal)} trading days  |  ~{n_accts} accts/leg")
        print(f"  Stagger: every 14 CALENDAR days  |  PayD/BchD = calendar days")
        print(f"{'='*90}")

        # Per-leg R by year for this period
        print(f"\n  R by year per leg:")
        for leg_name in ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]:
            trades = leg_trades[leg_name]
            yearly = defaultdict(float)
            for t in trades:
                d = str(t.date)[:10]
                if start and d < start: continue
                if end and d >= end: continue
                yearly[d[:4]] += t.r_multiple
            yr_str = " | ".join(f"{y}:{r:+.1f}" for y, r in sorted(yearly.items()))
            total = sum(yearly.values())
            print(f"  {leg_name:<20} {yr_str}  = {total:+.1f}R")

        for profile_name, risk_map in risk_profiles.items():
            print(f"\n  >>> {profile_name} <<<")
            print(f"  {'Leg':<20} {'Risk':>6} {'Pay%':>7} {'Bch%':>7} {'PayD':>7} {'BchD':>7} {'MCBch':>6} {'MCPay':>6} {'#Pay':>6} {'#Bch':>6} {'#Open':>6} {'EV$':>8}")
            print("  " + "-" * 105)

            # Per-leg accounts
            all_portfolio_results = []
            for leg_name in ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]:
                risk = risk_map[leg_name]
                payout_r = PAYOUT_USD / risk
                breach_r = BREACH_USD / risk

                trades = leg_trades[leg_name]
                dated_r = trades_to_daily_r(trades, start, end)
                # Fill in non-trade days with 0 using trading calendar
                r_by_date = dict(dated_r)
                full_dated = [(d, r_by_date.get(d, 0.0)) for d in cal]

                results = simulate_staggered_accounts(full_dated, payout_r, breach_r)
                stats = analyze_accounts(results)
                ev = stats["payout_rate"]/100 * PAYOUT_USD + stats["breach_rate"]/100 * BREACH_USD

                print(f"  {leg_name:<20} ${risk:>4} {stats['payout_rate']:>6.1f}% {stats['breach_rate']:>6.1f}% "
                      f"{stats['avg_payout_days']:>6.0f}d {stats['avg_breach_days']:>6.0f}d "
                      f"{stats['max_consec_breach']:>6d} {stats['max_consec_payout']:>6d} "
                      f"{stats['payouts']:>6d} {stats['breaches']:>6d} {stats['open']:>6d} {ev:>+7.0f}")

                for r in results:
                    r["leg"] = leg_name
                all_portfolio_results.extend(results)

            # Portfolio row (all 4 legs' accounts merged)
            port_stats = analyze_accounts(all_portfolio_results)
            port_ev = port_stats["payout_rate"]/100 * PAYOUT_USD + port_stats["breach_rate"]/100 * BREACH_USD
            print("  " + "-" * 105)
            print(f"  {'PORTFOLIO (4 accts)':<20} {'mix':>6} {port_stats['payout_rate']:>6.1f}% {port_stats['breach_rate']:>6.1f}% "
                  f"{port_stats['avg_payout_days']:>6.0f}d {port_stats['avg_breach_days']:>6.0f}d "
                  f"{port_stats['max_consec_breach']:>6d} {port_stats['max_consec_payout']:>6d} "
                  f"{port_stats['payouts']:>6d} {port_stats['breaches']:>6d} {port_stats['open']:>6d} {port_ev:>+7.0f}")

            # COMBINED single account — each leg contributes $ PnL at its risk level
            # Account threshold is in USD: +$2500 payout, -$2000 breach
            # Each trade's dollar contribution = r_multiple * leg_risk
            for comb_label, comb_risk_map in [
                ("COMBINED $400 flat", {"NQ_NY_LSI": 400, "NQ_ASIA_ORB": 400, "ES_ASIA_CONT": 400, "ES_NY_CONT": 400}),
                ("COMBINED adjusted",  {"NQ_NY_LSI": 400, "NQ_ASIA_ORB": 300, "ES_ASIA_CONT": 200, "ES_NY_CONT": 300}),
            ]:
                all_usd_by_date = defaultdict(float)
                for leg_name in ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]:
                    leg_risk = comb_risk_map[leg_name]
                    trades = leg_trades[leg_name]
                    for t in trades:
                        d = str(t.date)[:10]
                        if start and d < start: continue
                        if end and d >= end: continue
                        all_usd_by_date[d] += t.r_multiple * leg_risk

                # Convert to R at a notional base (use $400 as the R unit for display)
                # But sim in USD directly: payout at +$2500, breach at -$2000
                combined_dated = [(d, all_usd_by_date.get(d, 0.0)) for d in cal]
                # Simulate in USD space
                combined_results = simulate_staggered_accounts(
                    combined_dated, PAYOUT_USD, BREACH_USD
                )
                comb_stats = analyze_accounts(combined_results)
                comb_ev = comb_stats["payout_rate"]/100 * PAYOUT_USD + comb_stats["breach_rate"]/100 * BREACH_USD
                risk_str = "  mix" if "adjusted" in comb_label else "$ 400"
                print(f"  {comb_label:<20} {risk_str:>6} {comb_stats['payout_rate']:>6.1f}% {comb_stats['breach_rate']:>6.1f}% "
                      f"{comb_stats['avg_payout_days']:>6.0f}d {comb_stats['avg_breach_days']:>6.0f}d "
                      f"{comb_stats['max_consec_breach']:>6d} {comb_stats['max_consec_payout']:>6d} "
                      f"{comb_stats['payouts']:>6d} {comb_stats['breaches']:>6d} {comb_stats['open']:>6d} {comb_ev:>+7.0f}")

    # ── Payout distribution for COMBINED adjusted ─────────────────────────
    print(f"\n{'='*90}")
    print("  PAYOUT TIME DISTRIBUTION — COMBINED ADJUSTED (1 account, LSI=$400 NQ_ASIA=$300 ES_ASIA=$200 ES_NY=$400)")
    print(f"{'='*90}")

    comb_risk_map = {"NQ_NY_LSI": 400, "NQ_ASIA_ORB": 300, "ES_ASIA_CONT": 200, "ES_NY_CONT": 300}

    for period_name, (start, end) in periods.items():
        cal = trading_calendar
        if start:
            cal = [d for d in cal if d >= start]
        if end:
            cal = [d for d in cal if d < end]
        if not cal:
            continue

        all_usd_by_date = defaultdict(float)
        for leg_name in ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]:
            leg_risk = comb_risk_map[leg_name]
            for t in leg_trades[leg_name]:
                d = str(t.date)[:10]
                if start and d < start: continue
                if end and d >= end: continue
                all_usd_by_date[d] += t.r_multiple * leg_risk

        combined_dated = [(d, all_usd_by_date.get(d, 0.0)) for d in cal]
        results = simulate_staggered_accounts(combined_dated, PAYOUT_USD, BREACH_USD)

        payouts = [r for r in results if r["status"] == "PAYOUT"]
        breaches = [r for r in results if r["status"] == "BREACH"]

        print(f"\n  {period_name}:")
        if payouts:
            pay_days = sorted([p["cal_days"] for p in payouts])
            print(f"    Payouts: {len(payouts)}")
            print(f"    Fastest: {min(pay_days)}d  |  Slowest: {max(pay_days)}d  |  Median: {pay_days[len(pay_days)//2]}d  |  Avg: {np.mean(pay_days):.0f}d")
            print(f"    Distribution: {pay_days}")
        else:
            print(f"    No payouts resolved")

        if breaches:
            bch_days = sorted([b["cal_days"] for b in breaches])
            print(f"    Breaches: {len(breaches)}")
            print(f"    Fastest: {min(bch_days)}d  |  Slowest: {max(bch_days)}d  |  Avg: {np.mean(bch_days):.0f}d")
            print(f"    Distribution: {bch_days}")
        else:
            print(f"    No breaches")

    print(f"\n\nTotal runtime: {time.time()-t0_total:.1f}s")


if __name__ == "__main__":
    main()
