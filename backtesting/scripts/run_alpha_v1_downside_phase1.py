#!/usr/bin/env python3
"""Phase-one prop firm analysis for ALPHA_V1 downside short candidates.

Runs the 3 promoted NQ NY continuation short candidates from the wave-1
downside research, both standalone and combined with the ALPHA_V1 long book.

Simulates staggered prop firm accounts at multiple risk levels.
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Date range: full history for metrics, last 2Y for prop sim ────────────

FULL_START = "2016-01-01"
FULL_END = "2026-04-04"
HOLDOUT_START = "2025-01-01"
PROP_START = "2016-01-01"  # full-history prop sim
PROP_END = "2026-04-04"
CYCLE_DAYS = 14

# ── Prop firm thresholds ──────────────────────────────────────────────────

# Standalone short account: full risk
PAYOUT_STANDALONE = 5.0
BREACH_STANDALONE = -4.0

# Combined portfolio (ALPHA_V1 + short leg): each trade = 0.2R on combined account
# 5 legs at 0.2R each = 1.0R total risk per concurrent trade day
# Thresholds scaled: +5R payout / -4R breach at full-risk = +25R / -20R at 0.2R
RISK_FRACTION_COMBINED = 0.2
PAYOUT_COMBINED = 25.0
BREACH_COMBINED = -20.0

# ── 3 Promoted NQ NY Short Candidates ────────────────────────────────────

def _short_session(orb_end: str, entry_end: str, stop_orb: float, gap_orb: float) -> SessionConfig:
    return SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end=orb_end,
        entry_start=orb_end,
        entry_end=entry_end,
        flat_start=entry_end,
        flat_end="16:00",
        stop_orb_pct=stop_orb,
        min_gap_orb_pct=gap_orb,
        min_stop_points=10.0,
        min_tp1_points=10.0,
    )

SHORT_CANDIDATES = {
    "NQ_NY_Short_RR2.0_ATR10": StrategyConfig(
        sessions=(_short_session("09:55", "11:30", 15.0, 2.5),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="short",
        use_bar_magnifier=True,
        rr=2.0,
        tp1_ratio=0.5,
        atr_length=10,
        risk_usd=5000.0,
        name="NQ NY Short RR2.0 TP0.5 ATR10 — Phase 1",
    ),
    "NQ_NY_Short_RR2.5_ATR12": StrategyConfig(
        sessions=(_short_session("09:55", "11:30", 15.0, 2.5),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="short",
        use_bar_magnifier=True,
        rr=2.5,
        tp1_ratio=0.4,
        atr_length=12,
        risk_usd=5000.0,
        name="NQ NY Short RR2.5 TP0.4 ATR12 — Phase 1",
    ),
    "NQ_NY_Short_RR2.5_ATR10": StrategyConfig(
        sessions=(_short_session("09:55", "11:30", 15.0, 2.5),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="short",
        use_bar_magnifier=True,
        rr=2.5,
        tp1_ratio=0.4,
        atr_length=10,
        risk_usd=5000.0,
        name="NQ NY Short RR2.5 TP0.4 ATR10 — Phase 1",
    ),
}

# ── ALPHA_V1 Long Book (4 legs) ──────────────────────────────────────────

ALPHA_V1_LEGS = {
    "NQ_NY_LSI": StrategyConfig(
        sessions=(SessionConfig(
            name="NY",
            rth_start="09:30",
            entry_start="09:35",
            entry_end="15:30",
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=0.0,
            min_gap_atr_pct=5.0,
        ),),
        instrument=NQ,
        strategy="lsi",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=3.0,
        tp1_ratio=0.34,
        atr_length=10,
        risk_usd=5000.0,
        lsi_n_left=8,
        lsi_n_right=60,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=5,
        lsi_stop_mode="absolute",
        lsi_entry_mode="fvg_limit",
        lsi_first_fvg_only=False,
        lsi_clean_path=False,
        lsi_be_swing_n_left=0,
        lsi_cancel_on_swing=False,
        excluded_days=(2, 3),  # Wed, Thu
        name="NQ NY LSI (ALPHA_V1)",
    ),
    "NQ_Asia_ORB": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia",
            orb_start="20:00",
            orb_end="20:15",
            entry_start="20:15",
            entry_end="22:30",
            flat_start="04:00",
            flat_end="07:00",
            stop_orb_pct=100.0,
            min_gap_orb_pct=10.0,
        ),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=6.0,
        tp1_ratio=0.3,
        atr_length=5,
        risk_usd=5000.0,
        excluded_days=(1,),  # Tuesday
        name="NQ Asia ORB (ALPHA_V1)",
    ),
    "ES_Asia_Cont": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia",
            orb_start="20:00",
            orb_end="20:15",
            entry_start="20:15",
            entry_end="03:00",
            flat_start="07:00",
            flat_end="07:30",
            stop_orb_pct=125.0,
            min_gap_atr_pct=0.5,
            min_stop_points=3.0,
            min_tp1_points=3.0,
        ),),
        instrument=ES,
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=1.5,
        tp1_ratio=0.7,
        atr_length=14,
        risk_usd=5000.0,
        name="ES Asia Cont (ALPHA_V1)",
    ),
    "ES_NY_Cont": StrategyConfig(
        sessions=(SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end="09:45",
            entry_start="09:45",
            entry_end="13:00",
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=5.0,
            min_gap_atr_pct=0.25,
            min_stop_points=3.0,
            min_tp1_points=3.0,
        ),),
        instrument=ES,
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=5.0,
        tp1_ratio=0.2,
        atr_length=7,
        risk_usd=5000.0,
        excluded_days=(3,),  # Thursday
        name="ES NY Cont (ALPHA_V1)",
    ),
}


# ── Staggered account simulation ─────────────────────────────────────────

def simulate_staggered_accounts(
    trade_data: list[dict],
    start_date: str,
    end_date: str,
    payout_r: float,
    breach_r: float,
    stagger_days: int = 14,
) -> dict:
    if not trade_data:
        return _empty()

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
            "peak_r": round(peak_r, 4),
            "trough_r": round(trough_r, 4),
            "trades_taken": trades_taken,
            "calendar_days": calendar_days,
            "outcome_date": outcome_date.isoformat(),
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

    # Max consecutive breaches
    max_consec_breach = 0
    cur = 0
    for r in results:
        if r["outcome"] == "breach":
            cur += 1
            max_consec_breach = max(max_consec_breach, cur)
        else:
            cur = 0

    # Max consecutive payouts
    max_consec_payout = 0
    cur = 0
    for r in results:
        if r["outcome"] == "payout":
            cur += 1
            max_consec_payout = max(max_consec_payout, cur)
        else:
            cur = 0

    return {
        "total_accounts": len(results),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": round(success_rate, 4) if success_rate is not None else None,
        "ev_per_account": round(ev, 4),
        "max_consec_breach": max_consec_breach,
        "max_consec_payout": max_consec_payout,
        "avg_trades_to_payout": round(float(np.mean([r["trades_taken"] for r in payouts])), 1) if payouts else None,
        "avg_days_to_payout": round(float(np.mean([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "avg_trades_to_breach": round(float(np.mean([r["trades_taken"] for r in breaches])), 1) if breaches else None,
        "avg_days_to_breach": round(float(np.mean([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "median_days_to_breach": round(float(np.median([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "avg_open_r": round(float(np.mean([r["final_r"] for r in opens])), 4) if opens else None,
        "account_details": results,
    }


def _empty():
    return {"total_accounts": 0, "payouts": 0, "breaches": 0, "open": 0,
            "success_rate": None, "ev_per_account": 0.0,
            "max_consec_breach": 0, "max_consec_payout": 0,
            "avg_trades_to_payout": None, "avg_days_to_payout": None,
            "median_days_to_payout": None, "avg_trades_to_breach": None,
            "avg_days_to_breach": None, "median_days_to_breach": None,
            "avg_open_r": None, "account_details": []}


def print_account_table(details):
    print(f"  {'Started':<12} {'Outcome':<10} {'Final R':>8} {'Peak R':>7} {'Trough':>7} {'Trades':>6} {'Days':>6} {'Resolved':<12}")
    print(f"  {'-'*75}")
    for d in details:
        oc = d['outcome'].upper()
        if d['outcome'] == 'payout':
            oc = f"\033[92m{oc}\033[0m"
        elif d['outcome'] == 'breach':
            oc = f"\033[91m{oc}\033[0m"
        else:
            oc = f"\033[93m{oc}\033[0m"
        print(f"  {d['account_start']:<12} {oc:<19} {d['final_r']:>8.3f} {d['peak_r']:>7.3f} {d['trough_r']:>7.3f} {d['trades_taken']:>6} {d['calendar_days']:>6} {d['outcome_date']:<12}")


def print_summary(label: str, acct: dict):
    sr = acct["success_rate"]
    sr_str = f"{sr:.1%}" if sr is not None else "N/A"
    print(f"\n  [{label}]")
    print(f"  Accounts: {acct['total_accounts']}  |  Payouts: {acct['payouts']}  |  Breaches: {acct['breaches']}  |  Open: {acct['open']}")
    print(f"  Success Rate: {sr_str}  |  EV/acct: {acct['ev_per_account']:+.3f}R")
    print(f"  Max consec breach: {acct['max_consec_breach']}  |  Max consec payout: {acct['max_consec_payout']}")
    if acct["avg_days_to_payout"] is not None:
        print(f"  Avg days to payout: {acct['avg_days_to_payout']:.0f}  (median {acct['median_days_to_payout']:.0f})")
    if acct["avg_days_to_breach"] is not None:
        print(f"  Avg days to breach: {acct['avg_days_to_breach']:.0f}  (median {acct['median_days_to_breach']:.0f})")
    if acct["avg_open_r"] is not None:
        print(f"  Open accounts avg R: {acct['avg_open_r']:+.3f}")


def main():
    t0 = time.time()

    print("=" * 100)
    print("ALPHA_V1 DOWNSIDE — Phase 1 Prop Firm Analysis")
    print("=" * 100)
    print(f"3 promoted NQ NY continuation short candidates")
    print(f"Full history: {FULL_START} to {FULL_END}")
    print(f"Holdout: {HOLDOUT_START}+")
    print(f"Prop sim: {PROP_START} to {PROP_END}, new account every {CYCLE_DAYS} days")
    print()

    # ── Load data ─────────────────────────────────────────────────────────

    print("Loading data...")
    nq_5m = load_5m_data("NQ_5m.parquet")
    nq_1m = load_1m_for_5m("NQ_5m.parquet")
    es_5m = load_5m_data("ES_5m.parquet")
    es_1m = load_1m_for_5m("ES_5m.parquet")
    print(f"  NQ: {len(nq_5m):,} 5m  |  {len(nq_1m):,} 1m")
    print(f"  ES: {len(es_5m):,} 5m  |  {len(es_1m):,} 1m")

    data_map = {"NQ": (nq_5m, nq_1m), "ES": (es_5m, es_1m)}

    # ── Run ALPHA_V1 long legs ────────────────────────────────────────────

    print(f"\n{'=' * 100}")
    print("ALPHA_V1 BASELINE (4 long legs)")
    print(f"{'=' * 100}")

    baseline_trades = {}  # leg_name -> list of filled trades
    baseline_trade_data = []  # merged {"date", "r", "leg"}

    for leg_name, cfg in ALPHA_V1_LEGS.items():
        symbol = cfg.instrument.symbol
        df_5m, df_1m = data_map[symbol]
        trades = run_backtest(df_5m, cfg, start_date=FULL_START, end_date=FULL_END, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        baseline_trades[leg_name] = filled
        m = compute_metrics(trades)

        print(f"\n  {leg_name}: {m['total_trades']} trades  |  WR: {m['win_rate']:.1%}  |  Net R: {m['total_r']:+.1f}  |  DD: {m['max_drawdown_r']:.1f}R  |  Calmar: {m['calmar_ratio']:.2f}")

        for t in filled:
            baseline_trade_data.append({
                "date": datetime.date.fromisoformat(t.date),
                "r": t.r_multiple,
                "leg": leg_name,
            })

    baseline_trade_data.sort(key=lambda x: x["date"])
    baseline_net_r = sum(t["r"] for t in baseline_trade_data)
    print(f"\n  Baseline combined: {len(baseline_trade_data)} trades  |  Net R: {baseline_net_r:+.1f}")

    # ── Run short candidates ──────────────────────────────────────────────

    print(f"\n{'=' * 100}")
    print("SHORT CANDIDATES — Standalone Performance")
    print(f"{'=' * 100}")

    short_results = {}  # candidate_name -> {trades, metrics, trade_data}

    for cand_name, cfg in SHORT_CANDIDATES.items():
        df_5m, df_1m = data_map["NQ"]
        trades = run_backtest(df_5m, cfg, start_date=FULL_START, end_date=FULL_END, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        m = compute_metrics(trades)

        # Split holdout
        holdout_trades = [t for t in trades if t.date >= HOLDOUT_START]
        m_holdout = compute_metrics(holdout_trades) if holdout_trades else None

        trade_data = sorted(
            [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple, "leg": cand_name} for t in filled],
            key=lambda x: x["date"],
        )

        short_results[cand_name] = {
            "trades": filled,
            "metrics_full": m,
            "metrics_holdout": m_holdout,
            "trade_data": trade_data,
        }

        print(f"\n  {cand_name}")
        print(f"    Full:    {m['total_trades']} trades  |  WR: {m['win_rate']:.1%}  |  Net R: {m['total_r']:+.1f}  |  DD: {m['max_drawdown_r']:.1f}R  |  Calmar: {m['calmar_ratio']:.2f}  |  Sharpe: {m['sharpe_ratio']:.2f}")
        if m_holdout and m_holdout["total_trades"] > 0:
            print(f"    Holdout: {m_holdout['total_trades']} trades  |  WR: {m_holdout['win_rate']:.1%}  |  Net R: {m_holdout['total_r']:+.1f}  |  DD: {m_holdout['max_drawdown_r']:.1f}R  |  Sharpe: {m_holdout['sharpe_ratio']:.2f}")
        if "r_by_year" in m:
            years = sorted(m["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{r:+.1f}" for yr, r in years)
            print(f"    R by year: {yr_str}")

    # ── Standalone prop sim for each short candidate ──────────────────────

    print(f"\n{'=' * 100}")
    print("STANDALONE SHORT LEG — Prop Firm Accounts (+5R / -4R)")
    print(f"{'=' * 100}")

    standalone_accts = {}
    for cand_name, res in short_results.items():
        acct = simulate_staggered_accounts(
            res["trade_data"], PROP_START, PROP_END,
            payout_r=PAYOUT_STANDALONE, breach_r=BREACH_STANDALONE,
            stagger_days=CYCLE_DAYS,
        )
        standalone_accts[cand_name] = acct
        print_summary(cand_name, acct)

    # ── Combined portfolio prop sim (ALPHA_V1 + each short) ───────────────

    print(f"\n{'=' * 100}")
    print("COMBINED PORTFOLIO (ALPHA_V1 + Short Leg)")
    print(f"Each trade = {RISK_FRACTION_COMBINED}R on combined account")
    print(f"Thresholds: +{PAYOUT_COMBINED}R / {BREACH_COMBINED}R")
    print(f"{'=' * 100}")

    combined_accts = {}
    for cand_name, res in short_results.items():
        # Merge baseline + short candidate trades, scale to combined risk fraction
        merged = []
        for t in baseline_trade_data:
            merged.append({
                "date": t["date"],
                "r": t["r"] * RISK_FRACTION_COMBINED,
                "leg": t["leg"],
            })
        for t in res["trade_data"]:
            merged.append({
                "date": t["date"],
                "r": t["r"] * RISK_FRACTION_COMBINED,
                "leg": t["leg"],
            })
        merged.sort(key=lambda x: x["date"])

        acct = simulate_staggered_accounts(
            merged, PROP_START, PROP_END,
            payout_r=PAYOUT_COMBINED, breach_r=BREACH_COMBINED,
            stagger_days=CYCLE_DAYS,
        )
        combined_accts[cand_name] = acct
        print_summary(f"ALPHA_V1 + {cand_name}", acct)

    # ── Baseline-only combined for comparison ─────────────────────────────

    print(f"\n{'=' * 100}")
    print("BASELINE-ONLY COMBINED (no short leg)")
    print(f"{'=' * 100}")

    baseline_scaled = [{"date": t["date"], "r": t["r"] * RISK_FRACTION_COMBINED, "leg": t["leg"]}
                       for t in baseline_trade_data]
    baseline_scaled.sort(key=lambda x: x["date"])

    baseline_acct = simulate_staggered_accounts(
        baseline_scaled, PROP_START, PROP_END,
        payout_r=PAYOUT_COMBINED, breach_r=BREACH_COMBINED,
        stagger_days=CYCLE_DAYS,
    )
    print_summary("ALPHA_V1 Baseline Only", baseline_acct)

    # ── Comparison table ──────────────────────────────────────────────────

    print(f"\n\n{'=' * 100}")
    print("COMPARISON: STANDALONE SHORT ACCOUNTS")
    print(f"{'=' * 100}")
    print(f"\n  {'Candidate':<30} {'Pay%':>6} {'EV/acct':>8} {'AvgD':>6} {'MedD':>6} {'MCBch':>6} {'MCPay':>6}")
    print(f"  {'-'*74}")
    for cand_name, acct in standalone_accts.items():
        sr = f"{acct['success_rate']:.1%}" if acct['success_rate'] else "N/A"
        avgd = f"{acct['avg_days_to_payout']:.0f}" if acct['avg_days_to_payout'] else "—"
        medd = f"{acct['median_days_to_payout']:.0f}" if acct['median_days_to_payout'] else "—"
        print(f"  {cand_name:<30} {sr:>6} {acct['ev_per_account']:>+8.3f} {avgd:>6} {medd:>6} {acct['max_consec_breach']:>6} {acct['max_consec_payout']:>6}")

    print(f"\n\n{'=' * 100}")
    print("COMPARISON: COMBINED PORTFOLIO ACCOUNTS")
    print(f"{'=' * 100}")
    print(f"\n  {'Portfolio':<40} {'Pay%':>6} {'EV/acct':>8} {'AvgD':>6} {'MedD':>6} {'MCBch':>6} {'MCPay':>6}")
    print(f"  {'-'*84}")

    # Baseline first
    sr = f"{baseline_acct['success_rate']:.1%}" if baseline_acct['success_rate'] else "N/A"
    avgd = f"{baseline_acct['avg_days_to_payout']:.0f}" if baseline_acct['avg_days_to_payout'] else "—"
    medd = f"{baseline_acct['median_days_to_payout']:.0f}" if baseline_acct['median_days_to_payout'] else "—"
    print(f"  {'ALPHA_V1 (baseline, no short)':<40} {sr:>6} {baseline_acct['ev_per_account']:>+8.3f} {avgd:>6} {medd:>6} {baseline_acct['max_consec_breach']:>6} {baseline_acct['max_consec_payout']:>6}")

    for cand_name, acct in combined_accts.items():
        sr = f"{acct['success_rate']:.1%}" if acct['success_rate'] else "N/A"
        avgd = f"{acct['avg_days_to_payout']:.0f}" if acct['avg_days_to_payout'] else "—"
        medd = f"{acct['median_days_to_payout']:.0f}" if acct['median_days_to_payout'] else "—"
        label = f"+ {cand_name}"
        print(f"  {label:<40} {sr:>6} {acct['ev_per_account']:>+8.3f} {avgd:>6} {medd:>6} {acct['max_consec_breach']:>6} {acct['max_consec_payout']:>6}")

    # ── Account-by-account for the best standalone candidate ──────────────

    # Find best standalone by success rate then EV
    best_standalone = max(standalone_accts.items(),
                         key=lambda x: (x[1]["success_rate"] or 0, x[1]["ev_per_account"]))
    print(f"\n\n{'=' * 100}")
    print(f"BEST STANDALONE ACCOUNT DETAILS: {best_standalone[0]}")
    print(f"{'=' * 100}")
    print_account_table(best_standalone[1]["account_details"])

    # ── Account-by-account for best combined ──────────────────────────────

    best_combined = max(combined_accts.items(),
                        key=lambda x: (x[1]["success_rate"] or 0, x[1]["ev_per_account"]))
    print(f"\n\n{'=' * 100}")
    print(f"BEST COMBINED ACCOUNT DETAILS: ALPHA_V1 + {best_combined[0]}")
    print(f"{'=' * 100}")
    print_account_table(best_combined[1]["account_details"])

    print(f"\n\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
