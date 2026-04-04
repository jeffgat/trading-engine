"""
ALPHA V1 Portfolio Analysis v2: Adjusted risk per leg vs uniform $400
Shows per-leg AND portfolio-level metrics (all 4 accounts combined).
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

UNIFORM_RISK = {"NQ_NY_LSI": 400, "NQ_ASIA_ORB": 400, "ES_ASIA_CONT": 400, "ES_NY_CONT": 400}
ADJUSTED_RISK = {"NQ_NY_LSI": 400, "NQ_ASIA_ORB": 300, "ES_ASIA_CONT": 200, "ES_NY_CONT": 500}

PAYOUT_USD = 2500
BREACH_USD = -2000
N_SIMS = 300
ALL_LEGS = ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]


def generate_trades_for_year(leg_name, year, target_r, rng):
    params = leg_params[leg_name]
    wr, rr, tp1 = params["wr"], params["rr"], params["tp1_ratio"]
    n_trades = trades_per_year[leg_name]
    if year == 2026:
        n_trades = int(n_trades * 63 / 252)
    trades = []
    for _ in range(n_trades):
        if rng.random() < wr:
            trades.append(rng.choice([tp1 * rr, rr, 0.5 * (tp1 * rr + rr)], p=[0.3, 0.4, 0.3]))
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
                    for i in wins:
                        trades[i] += diff / len(wins)
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
                acct["status"] = "PAYOUT"; break
            elif acct["equity_r"] <= breach_r:
                acct["status"] = "BREACH"; break
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
        if s == "BREACH": cb += 1; cp = 0; max_cb = max(max_cb, cb)
        else: cp += 1; cb = 0; max_cp = max(max_cp, cp)
    return {
        "payouts": len(payouts), "breaches": len(breaches), "open": len(opens),
        "payout_rate": payout_rate, "breach_rate": breach_rate,
        "avg_payout_days": avg_payout_days, "avg_breach_days": avg_breach_days,
        "max_consec_breach": max_cb, "max_consec_payout": max_cp,
    }


def run_full_analysis(period_name, years, risk_profile, profile_label, n_sims=N_SIMS):
    active_legs = [l for l in ALL_LEGS if all(y in legs[l] for y in years)]
    trading_days = sum(252 if y != 2026 else 63 for y in years)

    # Per-leg simulation
    leg_sims = {}
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
        leg_sims[leg] = sims

    # Portfolio-level: merge all 4 legs' account streams per sim
    # Each leg spawns its own accounts independently. Portfolio = union of all accounts.
    portfolio_sims = []
    for sim in range(n_sims):
        all_payouts = 0
        all_breaches = 0
        all_open = 0
        all_payout_days = []
        all_breach_days = []
        all_sequence = []  # (start_day, status) across all legs for consec tracking

        for leg in active_legs:
            risk = risk_profile[leg]
            payout_r = PAYOUT_USD / risk
            breach_r = BREACH_USD / risk
            rng = np.random.default_rng(sim * 42 + 7)
            daily_r = build_daily_r_for_period(leg, years, rng)
            results = simulate_accounts(daily_r, payout_r, breach_r, stagger_days=14)

            for r in results:
                if r["status"] == "PAYOUT":
                    all_payouts += 1
                    all_payout_days.append(r["days"])
                    all_sequence.append((r["start"], "PAYOUT"))
                elif r["status"] == "BREACH":
                    all_breaches += 1
                    all_breach_days.append(r["days"])
                    all_sequence.append((r["start"], "BREACH"))
                else:
                    all_open += 1

        resolved = all_payouts + all_breaches
        pr = all_payouts / resolved * 100 if resolved else 0
        br = all_breaches / resolved * 100 if resolved else 0
        apd = np.mean(all_payout_days) if all_payout_days else float('nan')
        abd = np.mean(all_breach_days) if all_breach_days else float('nan')

        # Consecutive streaks across portfolio (sorted by start time)
        all_sequence.sort(key=lambda x: x[0])
        max_cb = max_cp = cb = cp = 0
        for _, status in all_sequence:
            if status == "BREACH": cb += 1; cp = 0; max_cb = max(max_cb, cb)
            else: cp += 1; cb = 0; max_cp = max(max_cp, cp)

        portfolio_sims.append({
            "payouts": all_payouts, "breaches": all_breaches, "open": all_open,
            "payout_rate": pr, "breach_rate": br,
            "avg_payout_days": apd, "avg_breach_days": abd,
            "max_consec_breach": max_cb, "max_consec_payout": max_cp,
        })

    # Print results
    print(f"\n  {profile_label}")
    print(f"  {'Leg':<20} {'Risk':>6} {'Pay%':>7} {'Bch%':>7} {'PayD':>6} {'BchD':>6} {'MCBch':>6} {'MCPay':>6} {'EV$':>8}")
    print("  " + "-" * 85)

    leg_data = {}
    for leg in active_legs:
        risk = risk_profile[leg]
        sims = leg_sims[leg]
        s = {k: np.nanmean([x[k] for x in sims]) for k in ["payout_rate", "breach_rate", "avg_payout_days", "avg_breach_days", "payouts", "breaches", "open"]}
        s["max_consec_breach"] = int(np.max([x["max_consec_breach"] for x in sims]))
        s["max_consec_payout"] = int(np.max([x["max_consec_payout"] for x in sims]))
        ev = s["payout_rate"]/100 * PAYOUT_USD + s["breach_rate"]/100 * BREACH_USD
        s["ev_usd"] = ev
        s["risk"] = risk
        leg_data[leg] = s
        print(f"  {leg:<20} ${risk:>4} {s['payout_rate']:>6.1f}% {s['breach_rate']:>6.1f}% {s['avg_payout_days']:>5.0f}d {s['avg_breach_days']:>5.0f}d {s['max_consec_breach']:>6d} {s['max_consec_payout']:>6d} {ev:>+7.0f}")

    # Portfolio row
    ps = {k: np.nanmean([x[k] for x in portfolio_sims]) for k in ["payout_rate", "breach_rate", "avg_payout_days", "avg_breach_days", "payouts", "breaches", "open"]}
    ps["max_consec_breach"] = int(np.max([x["max_consec_breach"] for x in portfolio_sims]))
    ps["max_consec_payout"] = int(np.max([x["max_consec_payout"] for x in portfolio_sims]))
    pev = ps["payout_rate"]/100 * PAYOUT_USD + ps["breach_rate"]/100 * BREACH_USD
    print("  " + "-" * 85)
    print(f"  {'PORTFOLIO (4 accts)':<20} {'mix':>6} {ps['payout_rate']:>6.1f}% {ps['breach_rate']:>6.1f}% {ps['avg_payout_days']:>5.0f}d {ps['avg_breach_days']:>5.0f}d {ps['max_consec_breach']:>6d} {ps['max_consec_payout']:>6d} {pev:>+7.0f}")

    # Totals
    total_pay = ps["payouts"]
    total_bch = ps["breaches"]
    total_open = ps["open"]
    n_legs = len(active_legs)
    acct_cost = n_legs * 150 * (trading_days / 252)
    total_ev = total_pay * PAYOUT_USD + total_bch * BREACH_USD - n_legs * 150 * (total_pay + total_bch)

    print(f"\n  Avg per period: {total_pay:.1f} payouts, {total_bch:.1f} breaches, {total_open:.1f} open")
    print(f"  Gross EV: ${total_pay * PAYOUT_USD - total_bch * 2000:+,.0f}  |  Acct cost ({n_legs}×$150×{total_pay+total_bch:.0f} resolved): ${n_legs * 150 * (total_pay + total_bch):,.0f}")
    print(f"  Net EV: ${total_pay * PAYOUT_USD + total_bch * BREACH_USD - n_legs * 150 * (total_pay + total_bch):+,.0f}")

    return leg_data, ps


# === Run ===
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

    u_legs, u_port = run_full_analysis(period_name, years, UNIFORM_RISK, "UNIFORM $400")
    a_legs, a_port = run_full_analysis(period_name, years, ADJUSTED_RISK, "ADJUSTED (LSI=$400, NQ_ASIA=$300, ES_ASIA=$200, ES_NY=$500)")

    # Delta
    print(f"\n  DELTA (Adjusted - Uniform)")
    print(f"  {'':.<20} {'dPay%':>8} {'dPayD':>8} {'dBchD':>8} {'dMCBch':>8} {'dEV$':>8}")
    active = [l for l in ALL_LEGS if l in u_legs and l in a_legs]
    for leg in active:
        u, a = u_legs[leg], a_legs[leg]
        print(f"  {leg:<20} {a['payout_rate']-u['payout_rate']:>+7.1f}% {a['avg_payout_days']-u['avg_payout_days']:>+7.0f}d {a['avg_breach_days']-u['avg_breach_days']:>+7.0f}d {a['max_consec_breach']-u['max_consec_breach']:>+8d} {a['ev_usd']-u['ev_usd']:>+7.0f}")
    print(f"  {'PORTFOLIO':<20} {a_port['payout_rate']-u_port['payout_rate']:>+7.1f}% {a_port['avg_payout_days']-u_port['avg_payout_days']:>+7.0f}d {a_port['avg_breach_days']-u_port['avg_breach_days']:>+7.0f}d {a_port['max_consec_breach']-u_port['max_consec_breach']:>+8d} {(a_port['payout_rate']/100*2500+a_port['breach_rate']/100*-2000)-(u_port['payout_rate']/100*2500+u_port['breach_rate']/100*-2000):>+7.0f}")
