"""
ALPHA_V1 Portfolio Analysis: Combined vs Individual Legs
Simulates staggered prop firm accounts with $400 risk, $2500 payout, -$2000 breach.
Uses daily R streams from each leg's yearly R data distributed across trading days.
"""
import numpy as np
import pandas as pd
from collections import defaultdict

# --- R by year for each leg (from ALPHA_V1.md) ---
legs = {
    "NQ_NY_LSI": {
        2016: 9.4, 2017: 17.6, 2018: 2.6, 2019: 7.8, 2020: 16.7,
        2021: 14.9, 2022: 9.8, 2023: 15.7, 2024: 7.2, 2025: 13.3, 2026: 5.1
    },
    "NQ_ASIA_ORB": {
        2016: 21.5, 2017: 19.7, 2018: 28.1, 2019: 11.0, 2020: 15.8,
        2021: 5.5, 2022: 31.3, 2023: 24.6, 2024: 12.6, 2025: 37.1, 2026: 4.8
    },
    "ES_ASIA_CONT": {
        2016: 15, 2017: 15, 2018: 12, 2019: 24, 2020: 14,
        2021: 8, 2022: 19, 2023: 20, 2024: 18, 2025: 33, 2026: 4
    },
    "ES_NY_CONT": {
        2016: 18, 2017: 25, 2018: 4, 2019: 11, 2020: 16,
        2021: 20, 2022: 15, 2023: 13, 2024: 2, 2025: 16
    },
}

# Trade counts from ALPHA_V1.md (full history)
trade_counts = {
    "NQ_NY_LSI": 611,      # ~10.5 years -> ~58 trades/yr
    "NQ_ASIA_ORB": 753,    # ~10.5 years -> ~72 trades/yr
    "ES_ASIA_CONT": 1454,  # ~10.5 years -> ~138 trades/yr
    "ES_NY_CONT": 866,     # ~10 years -> ~87 trades/yr
}

# Win rates and RR for realistic trade generation
leg_params = {
    "NQ_NY_LSI":    {"wr": 0.592, "rr": 3.0, "tp1_ratio": 0.34},
    "NQ_ASIA_ORB":  {"wr": 0.452, "rr": 6.0, "tp1_ratio": 0.30},
    "ES_ASIA_CONT": {"wr": 0.551, "rr": 1.5, "tp1_ratio": 0.70},
    "ES_NY_CONT":   {"wr": 0.613, "rr": 5.0, "tp1_ratio": 0.20},
}

# Generate trade-level R streams per year per leg
def generate_trades_for_year(leg_name, year, target_r, rng):
    """Generate individual trade R values that sum to target_r for a given year."""
    params = leg_params[leg_name]
    wr = params["wr"]
    rr = params["rr"]
    tp1 = params["tp1_ratio"]

    # Approximate per-trade outcomes:
    # Win: tp1_ratio * 0.5 * rr + (1-tp1_ratio)*0.5*rr  ... simplified
    # Average win R = 0.5 * tp1*rr + 0.5 * rr (TP1 partial + TP2 full)
    # But actually: TP1 exits 50% position at tp1*rr, rest at full rr or BE or EOD
    # Simplified: avg_win ≈ 0.5*(tp1*rr) + 0.5*rr = rr * (0.5*tp1 + 0.5)
    avg_win = rr * (0.5 * tp1 + 0.5)
    avg_loss = -1.0

    # Expected R per trade
    exp_r = wr * avg_win + (1 - wr) * avg_loss

    if exp_r <= 0:
        exp_r = 0.05  # floor

    # How many trades needed
    years_data = legs[leg_name]
    total_years = len(years_data)
    total_trades = trade_counts[leg_name]
    trades_per_year = total_trades / total_years

    n_trades = max(10, int(round(trades_per_year)))

    # Generate trades: wins and losses
    trades = []
    for _ in range(n_trades):
        if rng.random() < wr:
            # Win - distribute between partial TP1 outcomes
            r = rng.choice([
                tp1 * rr,           # TP1 only (BE stop)
                rr,                 # Full target
                0.5 * (tp1 * rr + rr),  # Average
            ], p=[0.3, 0.4, 0.3])
            trades.append(r)
        else:
            trades.append(-1.0)

    # Scale to match target yearly R
    current_sum = sum(trades)
    if abs(current_sum) > 0.01:
        # Scale wins to match target
        scale = target_r / current_sum if current_sum != 0 else 1.0
        # Only scale if reasonable
        if 0.2 < scale < 5.0:
            trades = [t * scale if t > 0 else t for t in trades]
            # Adjust losses slightly too to keep realistic
            diff = target_r - sum(trades)
            if abs(diff) > 0.5 and len([t for t in trades if t > 0]) > 0:
                wins = [i for i, t in enumerate(trades) if t > 0]
                adj = diff / len(wins)
                for i in wins:
                    trades[i] += adj

    rng.shuffle(trades)
    return trades


def simulate_accounts(daily_r_series, payout_r, breach_r, stagger_days=14):
    """
    Simulate staggered prop firm accounts.
    daily_r_series: list of daily R values
    payout_r = R to reach for payout (e.g. 6.25 = $2500/$400)
    breach_r = R to reach for breach (e.g. -5.0 = -$2000/$400)
    """
    n_days = len(daily_r_series)

    accounts = []
    results = []

    for start_day in range(0, n_days, stagger_days):
        acct = {"start": start_day, "equity_r": 0.0, "status": "OPEN", "days": 0}
        accounts.append(acct)

    # Simulate day by day
    for day_idx in range(n_days):
        r_today = daily_r_series[day_idx]

        for acct in accounts:
            if acct["status"] != "OPEN":
                continue
            if day_idx < acct["start"]:
                continue

            acct["days"] += 1
            acct["equity_r"] += r_today

            if acct["equity_r"] >= payout_r:
                acct["status"] = "PAYOUT"
                results.append(acct.copy())
            elif acct["equity_r"] <= breach_r:
                acct["status"] = "BREACH"
                results.append(acct.copy())

    # Collect remaining open
    for acct in accounts:
        if acct["status"] == "OPEN":
            results.append(acct.copy())

    return results


def analyze_results(results, label):
    """Analyze account simulation results."""
    payouts = [r for r in results if r["status"] == "PAYOUT"]
    breaches = [r for r in results if r["status"] == "BREACH"]
    opens = [r for r in results if r["status"] == "OPEN"]
    resolved = payouts + breaches

    payout_rate = len(payouts) / len(resolved) * 100 if resolved else 0
    breach_rate = len(breaches) / len(resolved) * 100 if resolved else 0

    avg_payout_days = np.mean([p["days"] for p in payouts]) if payouts else float('nan')
    avg_breach_days = np.mean([b["days"] for b in breaches]) if breaches else float('nan')

    # Max consecutive breaches and payouts
    sequence = []
    for r in sorted(results, key=lambda x: x["start"]):
        if r["status"] in ("PAYOUT", "BREACH"):
            sequence.append(r["status"])

    max_consec_breach = 0
    max_consec_payout = 0
    curr_breach = 0
    curr_payout = 0

    for s in sequence:
        if s == "BREACH":
            curr_breach += 1
            curr_payout = 0
            max_consec_breach = max(max_consec_breach, curr_breach)
        else:
            curr_payout += 1
            curr_breach = 0
            max_consec_payout = max(max_consec_payout, curr_payout)

    return {
        "label": label,
        "total_accounts": len(results),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "payout_rate": payout_rate,
        "breach_rate": breach_rate,
        "avg_payout_days": avg_payout_days,
        "avg_breach_days": avg_breach_days,
        "max_consec_breach": max_consec_breach,
        "max_consec_payout": max_consec_payout,
    }


def build_daily_r_stream(leg_name, rng):
    """Build a daily R stream from yearly trade data."""
    all_trades = []
    years = sorted(legs[leg_name].keys())

    for year in years:
        target_r = legs[leg_name][year]
        year_trades = generate_trades_for_year(leg_name, year, target_r, rng)

        # Distribute trades across ~252 trading days
        trading_days = 252
        if year == 2026:
            trading_days = 63  # ~Q1 only

        daily_r = [0.0] * trading_days
        # Place trades on random days
        if len(year_trades) <= trading_days:
            trade_days = rng.choice(trading_days, size=len(year_trades), replace=False)
            trade_days.sort()
            for i, td in enumerate(trade_days):
                daily_r[td] = year_trades[i]
        else:
            # More trades than days - stack
            for i, trade in enumerate(year_trades):
                daily_r[i % trading_days] += trade

        all_trades.extend(daily_r)

    return all_trades


def build_combined_daily_r(leg_names, rng):
    """Build combined daily R stream from multiple legs."""
    streams = {}
    for leg in leg_names:
        streams[leg] = build_daily_r_stream(leg, rng)

    # Align to shortest
    min_len = min(len(s) for s in streams.values())
    combined = [0.0] * min_len
    for leg in leg_names:
        for i in range(min_len):
            combined[i] += streams[leg][i]

    return combined


# --- Run Analysis ---
RISK_USD = 400
PAYOUT_USD = 2500
BREACH_USD = -2000

PAYOUT_R = PAYOUT_USD / RISK_USD   # 6.25R
BREACH_R = BREACH_USD / RISK_USD   # -5.0R

N_SIMS = 200  # Monte Carlo iterations

print("=" * 80)
print("ALPHA V1 PORTFOLIO ANALYSIS: Combined vs Individual Legs")
print(f"Risk: ${RISK_USD} | Payout: ${PAYOUT_USD} ({PAYOUT_R:.2f}R) | Breach: ${BREACH_USD} ({abs(BREACH_R):.2f}R)")
print(f"Stagger: 14 days | Simulations: {N_SIMS}")
print("=" * 80)

all_legs = ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]

# Collect results across simulations
sim_results = defaultdict(list)

for sim in range(N_SIMS):
    rng = np.random.default_rng(sim * 42 + 7)

    # Individual legs
    for leg in all_legs:
        daily_r = build_daily_r_stream(leg, rng)
        results = simulate_accounts(daily_r, PAYOUT_R, BREACH_R, stagger_days=14)
        stats = analyze_results(results, leg)
        sim_results[leg].append(stats)

    # Combined (all 4 legs on one account)
    combined_r = build_combined_daily_r(all_legs, rng)
    results = simulate_accounts(combined_r, PAYOUT_R, BREACH_R, stagger_days=14)
    stats = analyze_results(results, "COMBINED_4LEG")
    sim_results["COMBINED_4LEG"].append(stats)

# --- Aggregate and Print ---
print("\n" + "=" * 80)
print("RESULTS (averaged across {} simulations)".format(N_SIMS))
print("=" * 80)

header = f"{'Leg':<20} {'Payout%':>8} {'Breach%':>8} {'AvgPayDays':>11} {'AvgBchDays':>11} {'MaxCBreach':>11} {'MaxCPayout':>11}"
print(header)
print("-" * len(header))

summary_data = {}
for key in ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT", "COMBINED_4LEG"]:
    sims = sim_results[key]

    avg_payout_rate = np.mean([s["payout_rate"] for s in sims])
    avg_breach_rate = np.mean([s["breach_rate"] for s in sims])
    avg_payout_days = np.nanmean([s["avg_payout_days"] for s in sims])
    avg_breach_days = np.nanmean([s["avg_breach_days"] for s in sims])
    max_consec_breach = np.max([s["max_consec_breach"] for s in sims])
    max_consec_payout = np.max([s["max_consec_payout"] for s in sims])

    avg_payouts = np.mean([s["payouts"] for s in sims])
    avg_breaches = np.mean([s["breaches"] for s in sims])

    summary_data[key] = {
        "payout_rate": avg_payout_rate,
        "breach_rate": avg_breach_rate,
        "avg_payout_days": avg_payout_days,
        "avg_breach_days": avg_breach_days,
        "max_consec_breach": max_consec_breach,
        "max_consec_payout": max_consec_payout,
        "avg_payouts": avg_payouts,
        "avg_breaches": avg_breaches,
    }

    print(f"{key:<20} {avg_payout_rate:>7.1f}% {avg_breach_rate:>7.1f}% {avg_payout_days:>10.0f}d {avg_breach_days:>10.0f}d {max_consec_breach:>11d} {max_consec_payout:>11d}")

# --- EV Analysis ---
print("\n" + "=" * 80)
print("EV PER ACCOUNT (in R)")
print("=" * 80)

for key in ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT", "COMBINED_4LEG"]:
    d = summary_data[key]
    pr = d["payout_rate"] / 100
    br = d["breach_rate"] / 100
    ev = pr * PAYOUT_R + br * BREACH_R
    ev_usd = ev * RISK_USD
    print(f"{key:<20}  EV = {ev:+.2f}R  (${ev_usd:+.0f} per account)")

# --- Risk Sizing Analysis ---
print("\n" + "=" * 80)
print("OPTIMAL RISK SIZING ANALYSIS")
print("=" * 80)
print("Testing different risk levels per leg to find optimal allocation...")
print()

risk_levels = [200, 300, 400, 500, 600]

for leg in all_legs:
    print(f"\n--- {leg} ---")
    print(f"{'Risk':>8} {'Payout%':>8} {'Breach%':>8} {'AvgPayD':>8} {'AvgBchD':>8} {'EV/acct':>10} {'$/acct':>10}")

    for risk in risk_levels:
        payout_r = PAYOUT_USD / risk
        breach_r = BREACH_USD / risk

        leg_sims = []
        for sim in range(100):  # fewer sims for speed
            rng = np.random.default_rng(sim * 42 + 7)
            daily_r = build_daily_r_stream(leg, rng)
            results = simulate_accounts(daily_r, payout_r, breach_r, stagger_days=14)
            stats = analyze_results(results, leg)
            leg_sims.append(stats)

        avg_pr = np.mean([s["payout_rate"] for s in leg_sims])
        avg_br = np.mean([s["breach_rate"] for s in leg_sims])
        avg_pd = np.nanmean([s["avg_payout_days"] for s in leg_sims])
        avg_bd = np.nanmean([s["avg_breach_days"] for s in leg_sims])

        pr_frac = avg_pr / 100
        br_frac = avg_br / 100
        ev_r = pr_frac * (PAYOUT_USD / risk) + br_frac * (BREACH_USD / risk)
        ev_usd = ev_r * risk

        print(f"${risk:>6} {avg_pr:>7.1f}% {avg_br:>7.1f}% {avg_pd:>7.0f}d {avg_bd:>7.0f}d {ev_r:>+9.2f}R ${ev_usd:>+8.0f}")

# --- Combined vs Individual Summary ---
print("\n" + "=" * 80)
print("VERDICT: COMBINED (4 legs, 1 account) vs INDIVIDUAL (1 leg per account)")
print("=" * 80)

comb = summary_data["COMBINED_4LEG"]
print(f"\nCombined 4-leg account:")
print(f"  Payout rate: {comb['payout_rate']:.1f}%")
print(f"  Avg days to payout: {comb['avg_payout_days']:.0f}")
print(f"  Max consecutive breaches: {comb['max_consec_breach']}")

total_individual_payouts = sum(summary_data[l]["avg_payouts"] for l in all_legs)
total_individual_breaches = sum(summary_data[l]["avg_breaches"] for l in all_legs)
individual_rate = total_individual_payouts / (total_individual_payouts + total_individual_breaches) * 100

print(f"\nIndividual accounts (4 separate accounts):")
print(f"  Weighted payout rate: {individual_rate:.1f}%")
for leg in all_legs:
    d = summary_data[leg]
    print(f"  {leg}: {d['payout_rate']:.1f}% payout, {d['avg_payout_days']:.0f}d avg")

# Account cost comparison (4 individual = 4x $150, combined = 1x $150 but 4x risk)
print(f"\nAccount cost comparison (at $150/account):")
print(f"  Combined: 1 account = $150 per stagger cycle")
print(f"  Individual: 4 accounts = $600 per stagger cycle")
print(f"  But individual accounts have independent risk (no correlated blow-up)")
