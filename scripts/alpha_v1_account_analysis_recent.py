"""
ALPHA V1 Portfolio Analysis: Recent periods (2024, 2025, 2026 YTD)
Simulates staggered prop firm accounts per period.
"""
import numpy as np
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
        2021: 20, 2022: 15, 2023: 13, 2024: 2, 2025: 16, 2026: 1.8
    },
}

# Trade counts per year (derived from total trades / years)
trades_per_year = {
    "NQ_NY_LSI": 58,
    "NQ_ASIA_ORB": 72,
    "ES_ASIA_CONT": 138,
    "ES_NY_CONT": 87,
}

leg_params = {
    "NQ_NY_LSI":    {"wr": 0.592, "rr": 3.0, "tp1_ratio": 0.34},
    "NQ_ASIA_ORB":  {"wr": 0.452, "rr": 6.0, "tp1_ratio": 0.30},
    "ES_ASIA_CONT": {"wr": 0.551, "rr": 1.5, "tp1_ratio": 0.70},
    "ES_NY_CONT":   {"wr": 0.613, "rr": 5.0, "tp1_ratio": 0.20},
}


def generate_trades_for_year(leg_name, year, target_r, rng):
    params = leg_params[leg_name]
    wr = params["wr"]
    rr = params["rr"]
    tp1 = params["tp1_ratio"]

    n_trades = trades_per_year[leg_name]
    if year == 2026:
        n_trades = int(n_trades * 63 / 252)  # Q1 only

    trades = []
    for _ in range(n_trades):
        if rng.random() < wr:
            r = rng.choice([
                tp1 * rr,
                rr,
                0.5 * (tp1 * rr + rr),
            ], p=[0.3, 0.4, 0.3])
            trades.append(r)
        else:
            trades.append(-1.0)

    current_sum = sum(trades)
    if abs(current_sum) > 0.01 and current_sum != 0:
        scale = target_r / current_sum
        if 0.2 < scale < 5.0:
            trades = [t * scale if t > 0 else t for t in trades]
            diff = target_r - sum(trades)
            if abs(diff) > 0.5:
                wins = [i for i, t in enumerate(trades) if t > 0]
                if wins:
                    adj = diff / len(wins)
                    for i in wins:
                        trades[i] += adj

    rng.shuffle(trades)
    return trades


def build_daily_r_for_period(leg_name, years, rng):
    all_daily = []
    for year in years:
        if year not in legs[leg_name]:
            continue
        target_r = legs[leg_name][year]
        year_trades = generate_trades_for_year(leg_name, year, target_r, rng)

        trading_days = 252 if year != 2026 else 63

        daily_r = [0.0] * trading_days
        if len(year_trades) <= trading_days:
            trade_days = rng.choice(trading_days, size=len(year_trades), replace=False)
            trade_days.sort()
            for i, td in enumerate(trade_days):
                daily_r[td] = year_trades[i]
        else:
            for i, trade in enumerate(year_trades):
                daily_r[i % trading_days] += trade

        all_daily.extend(daily_r)
    return all_daily


def simulate_accounts(daily_r_series, payout_r, breach_r, stagger_days=14):
    n_days = len(daily_r_series)
    results = []

    for start_day in range(0, n_days, stagger_days):
        acct = {"start": start_day, "equity_r": 0.0, "status": "OPEN", "days": 0}

        for day_idx in range(start_day, n_days):
            acct["days"] += 1
            acct["equity_r"] += daily_r_series[day_idx]

            if acct["equity_r"] >= payout_r:
                acct["status"] = "PAYOUT"
                break
            elif acct["equity_r"] <= breach_r:
                acct["status"] = "BREACH"
                break

        results.append(acct)
    return results


def analyze_results(results):
    payouts = [r for r in results if r["status"] == "PAYOUT"]
    breaches = [r for r in results if r["status"] == "BREACH"]
    opens = [r for r in results if r["status"] == "OPEN"]
    resolved = payouts + breaches

    payout_rate = len(payouts) / len(resolved) * 100 if resolved else 0
    breach_rate = len(breaches) / len(resolved) * 100 if resolved else 0
    avg_payout_days = np.mean([p["days"] for p in payouts]) if payouts else float('nan')
    avg_breach_days = np.mean([b["days"] for b in breaches]) if breaches else float('nan')

    sequence = [r["status"] for r in sorted(results, key=lambda x: x["start"]) if r["status"] in ("PAYOUT", "BREACH")]
    max_cb = max_cp = cb = cp = 0
    for s in sequence:
        if s == "BREACH":
            cb += 1; cp = 0; max_cb = max(max_cb, cb)
        else:
            cp += 1; cb = 0; max_cp = max(max_cp, cp)

    return {
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "payout_rate": payout_rate,
        "breach_rate": breach_rate,
        "avg_payout_days": avg_payout_days,
        "avg_breach_days": avg_breach_days,
        "max_consec_breach": max_cb,
        "max_consec_payout": max_cp,
    }


RISK_USD = 400
PAYOUT_R = 2500 / RISK_USD   # 6.25R
BREACH_R = -2000 / RISK_USD  # -5.0R
N_SIMS = 300

all_legs = ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]

periods = {
    "2024": [2024],
    "2025": [2025],
    "2026 YTD": [2026],
}

# Also test risk sizing per period
risk_levels = [200, 300, 400, 500, 600]

for period_name, years in periods.items():
    # Check which legs have data for this period
    active_legs = [l for l in all_legs if all(y in legs[l] for y in years)]

    trading_days = sum(252 if y != 2026 else 63 for y in years)
    n_possible_accounts = trading_days // 14

    print("=" * 90)
    print(f"  PERIOD: {period_name}  |  ~{trading_days} trading days  |  ~{n_possible_accounts} staggered accounts possible")
    print("=" * 90)

    # --- Individual legs at $400 ---
    print(f"\n{'Leg':<20} {'Pay%':>6} {'Bch%':>6} {'PayD':>6} {'BchD':>6} {'MCBch':>6} {'MCPay':>6} {'#Pay':>6} {'#Bch':>6} {'#Open':>6} {'EV$':>8}")
    print("-" * 90)

    period_summary = {}
    for leg in active_legs:
        sims = []
        for sim in range(N_SIMS):
            rng = np.random.default_rng(sim * 42 + 7)
            daily_r = build_daily_r_for_period(leg, years, rng)
            results = simulate_accounts(daily_r, PAYOUT_R, BREACH_R, stagger_days=14)
            sims.append(analyze_results(results))

        s = {k: np.nanmean([x[k] for x in sims]) for k in ["payout_rate", "breach_rate", "avg_payout_days", "avg_breach_days", "payouts", "breaches", "open"]}
        s["max_consec_breach"] = int(np.max([x["max_consec_breach"] for x in sims]))
        s["max_consec_payout"] = int(np.max([x["max_consec_payout"] for x in sims]))
        ev_usd = (s["payout_rate"]/100 * PAYOUT_R + s["breach_rate"]/100 * BREACH_R) * RISK_USD
        s["ev_usd"] = ev_usd
        period_summary[leg] = s

        print(f"{leg:<20} {s['payout_rate']:>5.1f}% {s['breach_rate']:>5.1f}% {s['avg_payout_days']:>5.0f}d {s['avg_breach_days']:>5.0f}d {s['max_consec_breach']:>6d} {s['max_consec_payout']:>6d} {s['payouts']:>5.1f} {s['breaches']:>5.1f} {s['open']:>5.1f} {ev_usd:>+7.0f}")

    # Combined
    comb_sims = []
    for sim in range(N_SIMS):
        rng = np.random.default_rng(sim * 42 + 7)
        streams = [build_daily_r_for_period(l, years, rng) for l in active_legs]
        min_len = min(len(s) for s in streams)
        combined = [sum(s[i] for s in streams) for i in range(min_len)]
        results = simulate_accounts(combined, PAYOUT_R, BREACH_R, stagger_days=14)
        comb_sims.append(analyze_results(results))

    cs = {k: np.nanmean([x[k] for x in comb_sims]) for k in ["payout_rate", "breach_rate", "avg_payout_days", "avg_breach_days", "payouts", "breaches", "open"]}
    cs["max_consec_breach"] = int(np.max([x["max_consec_breach"] for x in comb_sims]))
    cs["max_consec_payout"] = int(np.max([x["max_consec_payout"] for x in comb_sims]))
    ev_usd = (cs["payout_rate"]/100 * PAYOUT_R + cs["breach_rate"]/100 * BREACH_R) * RISK_USD
    cs["ev_usd"] = ev_usd

    print(f"{'COMBINED_4LEG':<20} {cs['payout_rate']:>5.1f}% {cs['breach_rate']:>5.1f}% {cs['avg_payout_days']:>5.0f}d {cs['avg_breach_days']:>5.0f}d {cs['max_consec_breach']:>6d} {cs['max_consec_payout']:>6d} {cs['payouts']:>5.1f} {cs['breaches']:>5.1f} {cs['open']:>5.1f} {ev_usd:>+7.0f}")

    # --- Risk sizing per leg for this period ---
    print(f"\n  Risk sizing analysis for {period_name}:")
    for leg in active_legs:
        print(f"\n  {leg}:")
        print(f"  {'Risk':>6} {'Pay%':>7} {'Bch%':>7} {'PayD':>6} {'BchD':>6} {'EV$':>8}")
        for risk in risk_levels:
            pr = 2500 / risk
            br = -2000 / risk
            sims = []
            for sim in range(200):
                rng = np.random.default_rng(sim * 42 + 7)
                daily_r = build_daily_r_for_period(leg, years, rng)
                results = simulate_accounts(daily_r, pr, br, stagger_days=14)
                sims.append(analyze_results(results))
            avg_pr = np.nanmean([x["payout_rate"] for x in sims])
            avg_br = np.nanmean([x["breach_rate"] for x in sims])
            avg_pd = np.nanmean([x["avg_payout_days"] for x in sims])
            avg_bd = np.nanmean([x["avg_breach_days"] for x in sims])
            ev = (avg_pr/100 * (2500/risk) + avg_br/100 * (-2000/risk)) * risk
            print(f"  ${risk:>5} {avg_pr:>6.1f}% {avg_br:>6.1f}% {avg_pd:>5.0f}d {avg_bd:>5.0f}d {ev:>+7.0f}")

    print()
