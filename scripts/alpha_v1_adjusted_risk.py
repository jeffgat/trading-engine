"""
ALPHA V1 Portfolio Analysis: Adjusted risk per leg vs uniform $400
Periods: Last 10 years (2016-2026), 2025, 2026 YTD
"""
import numpy as np
from collections import defaultdict

# --- R by year for each leg ---
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

# Risk profiles
UNIFORM_RISK = {
    "NQ_NY_LSI": 400,
    "NQ_ASIA_ORB": 400,
    "ES_ASIA_CONT": 400,
    "ES_NY_CONT": 400,
}

ADJUSTED_RISK = {
    "NQ_NY_LSI": 400,
    "NQ_ASIA_ORB": 300,
    "ES_ASIA_CONT": 200,
    "ES_NY_CONT": 500,
}

PAYOUT_USD = 2500
BREACH_USD = -2000


def generate_trades_for_year(leg_name, year, target_r, rng):
    params = leg_params[leg_name]
    wr = params["wr"]
    rr = params["rr"]
    tp1 = params["tp1_ratio"]

    n_trades = trades_per_year[leg_name]
    if year == 2026:
        n_trades = int(n_trades * 63 / 252)

    trades = []
    for _ in range(n_trades):
        if rng.random() < wr:
            r = rng.choice([tp1 * rr, rr, 0.5 * (tp1 * rr + rr)], p=[0.3, 0.4, 0.3])
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


def run_analysis(period_name, years, risk_profile, profile_label, n_sims=300):
    all_legs = ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]
    active_legs = [l for l in all_legs if all(y in legs[l] for y in years)]

    trading_days = sum(252 if y != 2026 else 63 for y in years)
    n_accounts = trading_days // 14

    print(f"\n{'Leg':<20} {'Risk':>6} {'Pay%':>7} {'Bch%':>7} {'PayD':>6} {'BchD':>6} {'MCBch':>6} {'MCPay':>6} {'#Pay':>6} {'#Bch':>6} {'EV$':>8}")
    print("-" * 95)

    leg_data = {}
    for leg in active_legs:
        risk = risk_profile[leg]
        payout_r = PAYOUT_USD / risk
        breach_r = BREACH_USD / risk

        sims = []
        for sim in range(n_sims):
            rng = np.random.default_rng(sim * 42 + 7)
            daily_r = build_daily_r_for_period(leg, years, rng)
            results = simulate_accounts(daily_r, payout_r, breach_r, stagger_days=14)
            sims.append(analyze_results(results))

        s = {k: np.nanmean([x[k] for x in sims]) for k in ["payout_rate", "breach_rate", "avg_payout_days", "avg_breach_days", "payouts", "breaches", "open"]}
        s["max_consec_breach"] = int(np.max([x["max_consec_breach"] for x in sims]))
        s["max_consec_payout"] = int(np.max([x["max_consec_payout"] for x in sims]))
        ev_usd = (s["payout_rate"]/100 * PAYOUT_USD + s["breach_rate"]/100 * BREACH_USD)  # per resolved account
        s["ev_usd"] = ev_usd
        s["risk"] = risk
        leg_data[leg] = s

        print(f"{leg:<20} ${risk:>4} {s['payout_rate']:>6.1f}% {s['breach_rate']:>6.1f}% {s['avg_payout_days']:>5.0f}d {s['avg_breach_days']:>5.0f}d {s['max_consec_breach']:>6d} {s['max_consec_payout']:>6d} {s['payouts']:>5.1f} {s['breaches']:>5.1f} {ev_usd:>+7.0f}")

    # Combined (all legs on one account) — use $400 baseline since combined doesn't have per-leg risk
    comb_sims = []
    for sim in range(n_sims):
        rng = np.random.default_rng(sim * 42 + 7)
        streams = [build_daily_r_for_period(l, years, rng) for l in active_legs]
        min_len = min(len(s) for s in streams)
        combined = [sum(s[i] for s in streams) for i in range(min_len)]
        results = simulate_accounts(combined, PAYOUT_USD / 400, BREACH_USD / 400, stagger_days=14)
        comb_sims.append(analyze_results(results))

    cs = {k: np.nanmean([x[k] for x in comb_sims]) for k in ["payout_rate", "breach_rate", "avg_payout_days", "avg_breach_days", "payouts", "breaches", "open"]}
    cs["max_consec_breach"] = int(np.max([x["max_consec_breach"] for x in comb_sims]))
    cs["max_consec_payout"] = int(np.max([x["max_consec_payout"] for x in comb_sims]))
    ev_usd = (cs["payout_rate"]/100 * PAYOUT_USD + cs["breach_rate"]/100 * BREACH_USD)
    print(f"{'COMBINED_4LEG':<20} $ 400 {cs['payout_rate']:>6.1f}% {cs['breach_rate']:>6.1f}% {cs['avg_payout_days']:>5.0f}d {cs['avg_breach_days']:>5.0f}d {cs['max_consec_breach']:>6d} {cs['max_consec_payout']:>6d} {cs['payouts']:>5.1f} {cs['breaches']:>5.1f} {ev_usd:>+7.0f}")

    # Portfolio totals
    total_payouts = sum(leg_data[l]["payouts"] for l in active_legs)
    total_breaches = sum(leg_data[l]["breaches"] for l in active_legs)
    total_ev = sum(leg_data[l]["ev_usd"] * (leg_data[l]["payouts"] + leg_data[l]["breaches"]) for l in active_legs)
    total_acct_cost = len(active_legs) * 150 * (trading_days / 252)  # rough annual cost
    weighted_pr = total_payouts / (total_payouts + total_breaches) * 100 if (total_payouts + total_breaches) > 0 else 0

    print(f"\n  Portfolio totals ({profile_label}):")
    print(f"  Total payouts/period: {total_payouts:.1f} | Total breaches: {total_breaches:.1f} | Weighted payout rate: {weighted_pr:.1f}%")
    print(f"  Total EV/period: ${total_ev:+,.0f} | Acct cost: ~${total_acct_cost:,.0f} | Net: ~${total_ev - total_acct_cost:+,.0f}")

    return leg_data


# === Run all periods with both profiles ===

periods = {
    "LAST 10 YEARS (2016-2026)": list(range(2016, 2027)),
    "2025": [2025],
    "2026 YTD": [2026],
}

for period_name, years in periods.items():
    trading_days = sum(252 if y != 2026 else 63 for y in years)
    n_accounts = trading_days // 14

    print("\n" + "=" * 95)
    print(f"  {period_name}  |  ~{trading_days} trading days  |  ~{n_accounts} accounts/leg")
    print("=" * 95)

    print(f"\n  >>> UNIFORM $400 RISK <<<")
    uniform_data = run_analysis(period_name, years, UNIFORM_RISK, "Uniform $400")

    print(f"\n  >>> ADJUSTED RISK (NQ_LSI=$400, NQ_ASIA=$300, ES_ASIA=$200, ES_NY=$500) <<<")
    adjusted_data = run_analysis(period_name, years, ADJUSTED_RISK, "Adjusted")

    # Delta comparison
    print(f"\n  >>> DELTA (Adjusted - Uniform) <<<")
    all_legs = ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]
    active = [l for l in all_legs if l in uniform_data and l in adjusted_data]
    print(f"  {'Leg':<20} {'dPay%':>8} {'dBchD':>8} {'dPayD':>8} {'dEV$':>8} {'dMCBch':>8}")
    for leg in active:
        u = uniform_data[leg]
        a = adjusted_data[leg]
        dp = a["payout_rate"] - u["payout_rate"]
        db = a["avg_breach_days"] - u["avg_breach_days"]
        dd = a["avg_payout_days"] - u["avg_payout_days"]
        de = a["ev_usd"] - u["ev_usd"]
        dm = a["max_consec_breach"] - u["max_consec_breach"]
        print(f"  {leg:<20} {dp:>+7.1f}% {db:>+7.0f}d {dd:>+7.0f}d {de:>+7.0f} {dm:>+8d}")
