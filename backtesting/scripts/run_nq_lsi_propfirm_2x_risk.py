#!/usr/bin/env python3
"""Re-simulate prop firm accounts with 2x risk sizing.

Doubling risk_usd means each trade's dollar impact doubles. Since R-multiples
are normalised (1R = risk_usd), doubling risk is equivalent to halving the
payout/breach thresholds: +2.5R payout / -2.0R breach instead of +5R / -4R.

This script re-runs the FULL sweep (same grid) but only re-does the staggered
account simulation with halved thresholds — no need to re-run backtests since
R-multiples don't change.
"""

import dataclasses
import datetime
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import generate_param_grid, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.engine.simulator import EXIT_NO_FILL


# ── Anchor config (from DB run #1335) ──────────────────────────────────────

INSTRUMENT = get_instrument("NQ")

NY_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

ANCHOR = StrategyConfig(
    strategy="lsi",
    direction_filter="long",
    rr=3.0,
    tp1_ratio=0.3,
    risk_usd=5000.0,
    atr_length=10,
    use_bar_magnifier=True,
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
    excluded_days=(2, 3),
    sessions=(NY_SESSION,),
    instrument=INSTRUMENT,
)

# ── Date range ─────────────────────────────────────────────────────────────

START_DATE = "2024-03-08"
END_DATE = "2026-03-03"

# ── Prop firm parameters — 2x RISK (halved thresholds) ────────────────────

# Original: +5R payout / -4R breach with $5k risk
# 2x risk:  +2.5R payout / -2.0R breach (same $ thresholds, double risk per trade)
PAYOUT_TARGET_1X = 5.0
BREACH_LIMIT_1X = -4.0
PAYOUT_TARGET_2X = 2.5    # halved — equivalent to doubling risk
BREACH_LIMIT_2X = -2.0    # halved — equivalent to doubling risk
CYCLE_DAYS = 14


# ── Grid: same as original sweep ──────────────────────────────────────────

PARAM_GRID = {
    "rr": [2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0],
    "tp1_ratio": [0.15, 0.2, 0.25, 0.3, 0.4, 0.5],
    "ny_min_gap_atr_pct": [2.5, 3.75, 5.0, 7.5],
    "lsi_n_left": [5, 6, 7, 8, 10],
}


def simulate_staggered_accounts(
    trades: list,
    start_date: str,
    end_date: str,
    payout_r: float = 5.0,
    breach_r: float = -4.0,
    stagger_days: int = CYCLE_DAYS,
) -> dict:
    """Simulate staggered prop firm accounts with unlimited duration."""
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return _empty_cycle_stats()

    trade_data = []
    for t in filled:
        trade_data.append({
            "date": datetime.date.fromisoformat(t.date),
            "r": t.r_multiple,
        })
    trade_data.sort(key=lambda x: x["date"])

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
            future_trades = [t for t in trade_data if t["date"] >= acct_start]
            outcome_date = future_trades[-1]["date"] if future_trades else acct_start

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

    total = len(results)
    payouts = [r for r in results if r["outcome"] == "payout"]
    breaches = [r for r in results if r["outcome"] == "breach"]
    opens = [r for r in results if r["outcome"] == "open"]

    n_payouts = len(payouts)
    n_breaches = len(breaches)
    n_open = len(opens)
    resolved = n_payouts + n_breaches
    success_rate = n_payouts / resolved if resolved > 0 else None

    payout_rate = n_payouts / total if total > 0 else 0.0
    breach_rate = n_breaches / total if total > 0 else 0.0

    avg_trades_to_payout = np.mean([r["trades_taken"] for r in payouts]) if payouts else None
    avg_days_to_payout = np.mean([r["calendar_days"] for r in payouts]) if payouts else None
    median_days_to_payout = np.median([r["calendar_days"] for r in payouts]) if payouts else None

    avg_trades_to_breach = np.mean([r["trades_taken"] for r in breaches]) if breaches else None
    avg_days_to_breach = np.mean([r["calendar_days"] for r in breaches]) if breaches else None
    median_days_to_breach = np.median([r["calendar_days"] for r in breaches]) if breaches else None

    avg_open_r = np.mean([r["final_r"] for r in opens]) if opens else None
    median_open_r = np.median([r["final_r"] for r in opens]) if opens else None

    capped_rs = []
    for r in results:
        if r["outcome"] == "payout":
            capped_rs.append(payout_r)
        elif r["outcome"] == "breach":
            capped_rs.append(breach_r)
        else:
            capped_rs.append(r["final_r"])
    ev_per_account = np.mean(capped_rs) if capped_rs else 0.0

    return {
        "total_accounts": total,
        "payouts": n_payouts,
        "breaches": n_breaches,
        "open": n_open,
        "payout_rate": round(payout_rate, 4),
        "breach_rate": round(breach_rate, 4),
        "success_rate_resolved": round(success_rate, 4) if success_rate is not None else None,
        "avg_trades_to_payout": round(float(avg_trades_to_payout), 1) if avg_trades_to_payout is not None else None,
        "avg_days_to_payout": round(float(avg_days_to_payout), 1) if avg_days_to_payout is not None else None,
        "median_days_to_payout": round(float(median_days_to_payout), 1) if median_days_to_payout is not None else None,
        "avg_trades_to_breach": round(float(avg_trades_to_breach), 1) if avg_trades_to_breach is not None else None,
        "avg_days_to_breach": round(float(avg_days_to_breach), 1) if avg_days_to_breach is not None else None,
        "median_days_to_breach": round(float(median_days_to_breach), 1) if median_days_to_breach is not None else None,
        "avg_open_r": round(float(avg_open_r), 4) if avg_open_r is not None else None,
        "median_open_r": round(float(median_open_r), 4) if median_open_r is not None else None,
        "ev_per_account": round(float(ev_per_account), 4),
        "account_details": results,
    }


def _empty_cycle_stats():
    return {
        "total_accounts": 0, "payouts": 0, "breaches": 0,
        "open": 0, "payout_rate": 0.0, "breach_rate": 0.0,
        "success_rate_resolved": None,
        "avg_trades_to_payout": None, "avg_days_to_payout": None,
        "median_days_to_payout": None,
        "avg_trades_to_breach": None, "avg_days_to_breach": None,
        "median_days_to_breach": None,
        "avg_open_r": None, "median_open_r": None,
        "ev_per_account": 0.0, "account_details": [],
    }


def config_label(cfg: StrategyConfig) -> str:
    excl = cfg.excluded_days
    if excl == (2, 3):
        dow = "MTF"
    elif excl == (3,):
        dow = "MTWF"
    elif excl == (2,):
        dow = "MTRF"
    else:
        dow = "ALL"
    return f"rr={cfg.rr} tp1={cfg.tp1_ratio} gap={cfg.sessions[0].min_gap_atr_pct} nl={cfg.lsi_n_left} {dow}"


def main():
    t0 = time.time()

    # ── Load data ──────────────────────────────────────────────────────────
    print("Loading NQ data...")
    df = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  5m: {len(df):,} bars  |  1m: {len(df_1m):,} bars")

    # ── Generate grid ──────────────────────────────────────────────────────
    all_configs = []
    for dow_name, excl_days in [("wed_thu", (2, 3)), ("thu_only", (3,))]:
        base = dataclasses.replace(ANCHOR, excluded_days=excl_days)
        configs = generate_param_grid(base, PARAM_GRID)
        all_configs.extend(configs)
        print(f"  DOW={dow_name}: {len(configs)} configs")

    print(f"\n{describe_grid(PARAM_GRID)}")
    print(f"x 2 DOW variants = {len(all_configs):,} total configs\n")

    # ── Run sweep ──────────────────────────────────────────────────────────
    print("Running sweep...")

    def progress(done, total):
        if done % 50 == 0 or done == total:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            print(f"  [{done}/{total}] {rate:.1f} configs/s  ETA: {eta:.0f}s")

    results = run_sweep(
        df, all_configs,
        n_workers=8,
        progress_fn=progress,
        start_date=START_DATE,
        end_date=END_DATE,
        df_1m=df_1m,
    )

    sweep_time = time.time() - t0
    print(f"\nSweep complete: {len(results)} configs in {sweep_time:.1f}s\n")

    # ── Compute metrics + staggered account simulations for BOTH risk levels ──

    print("=" * 160)
    print("COMPARING 1x RISK (+5R/-4R) vs 2x RISK (+2.5R/-2.0R)")
    print("=" * 160)
    print(f"  1x risk: $5k/trade → need +5R ($25k profit) for payout, breach at -4R ($20k loss)")
    print(f"  2x risk: $10k/trade → need +2.5R ($25k profit) for payout, breach at -2.0R ($20k loss)")
    print(f"  Same dollar thresholds, faster resolution, more variance per trade\n")

    rows = []
    for cfg, trades in results:
        metrics = compute_metrics(trades)

        # Simulate BOTH risk levels
        acct_1x = simulate_staggered_accounts(
            trades, START_DATE, END_DATE,
            payout_r=PAYOUT_TARGET_1X, breach_r=BREACH_LIMIT_1X, stagger_days=CYCLE_DAYS,
        )
        acct_2x = simulate_staggered_accounts(
            trades, START_DATE, END_DATE,
            payout_r=PAYOUT_TARGET_2X, breach_r=BREACH_LIMIT_2X, stagger_days=CYCLE_DAYS,
        )

        rows.append({
            "config": cfg,
            "label": config_label(cfg),
            "rr": cfg.rr,
            "tp1_ratio": cfg.tp1_ratio,
            "gap": cfg.sessions[0].min_gap_atr_pct,
            "n_left": cfg.lsi_n_left,
            "excluded_days": cfg.excluded_days,
            "dow": "MTF" if cfg.excluded_days == (2, 3) else "MTWF" if cfg.excluded_days == (3,) else "?",
            # Standard metrics
            "trades": metrics["total_trades"],
            "win_rate": metrics["win_rate"],
            "net_r": metrics["total_r"],
            "max_dd_r": metrics["max_drawdown_r"],
            "calmar": metrics["calmar_ratio"],
            "sharpe": metrics["sharpe_ratio"],
            "pf": metrics["profit_factor"],
            "avg_r": metrics["avg_r"],
            # 1x risk stats
            "1x_accounts": acct_1x["total_accounts"],
            "1x_payouts": acct_1x["payouts"],
            "1x_breaches": acct_1x["breaches"],
            "1x_open": acct_1x["open"],
            "1x_success": acct_1x["success_rate_resolved"],
            "1x_ev": acct_1x["ev_per_account"],
            "1x_avg_days_pay": acct_1x["avg_days_to_payout"],
            "1x_med_days_pay": acct_1x["median_days_to_payout"],
            "1x_avg_days_breach": acct_1x["avg_days_to_breach"],
            "1x_med_days_breach": acct_1x["median_days_to_breach"],
            # 2x risk stats
            "2x_accounts": acct_2x["total_accounts"],
            "2x_payouts": acct_2x["payouts"],
            "2x_breaches": acct_2x["breaches"],
            "2x_open": acct_2x["open"],
            "2x_success": acct_2x["success_rate_resolved"],
            "2x_ev": acct_2x["ev_per_account"],
            "2x_avg_days_pay": acct_2x["avg_days_to_payout"],
            "2x_med_days_pay": acct_2x["median_days_to_payout"],
            "2x_avg_days_breach": acct_2x["avg_days_to_breach"],
            "2x_med_days_breach": acct_2x["median_days_to_breach"],
            # Account details for detailed view
            "1x_details": acct_1x["account_details"],
            "2x_details": acct_2x["account_details"],
        })

    # Filter: >= 50 trades
    rows = [r for r in rows if r["trades"] >= 50]

    # ── SIDE-BY-SIDE COMPARISON: Top 25 by 2x success rate ────────────────

    rows_by_2x = sorted(
        rows,
        key=lambda r: (
            r["2x_success"] or 0,
            r["2x_ev"],
            -abs(r.get("2x_avg_days_pay") or 9999),
            r["calmar"],
        ),
        reverse=True,
    )

    print(f"\n{'=' * 180}")
    print("TOP 25 BY 2x RISK SUCCESS RATE — side-by-side comparison")
    print(f"{'=' * 180}")
    hdr = (f"{'#':>3} {'Config':<35} {'Tr':>4} {'WR%':>6} {'Calm':>5} "
           f"│ {'1x Suc%':>7} {'1x P/B/O':>10} {'1x MdPay':>7} {'1x EV':>6} "
           f"│ {'2x Suc%':>7} {'2x P/B/O':>10} {'2x MdPay':>7} {'2x EV':>6}")
    print(hdr)
    print("-" * 180)

    for i, r in enumerate(rows_by_2x[:25]):
        s1 = f"{r['1x_success']:.0%}" if r["1x_success"] is not None else "N/A"
        s2 = f"{r['2x_success']:.0%}" if r["2x_success"] is not None else "N/A"
        pbo1 = f"{r['1x_payouts']}/{r['1x_breaches']}/{r['1x_open']}"
        pbo2 = f"{r['2x_payouts']}/{r['2x_breaches']}/{r['2x_open']}"
        mdp1 = f"{r['1x_med_days_pay']:.0f}" if r["1x_med_days_pay"] is not None else "-"
        mdp2 = f"{r['2x_med_days_pay']:.0f}" if r["2x_med_days_pay"] is not None else "-"
        print(
            f"{i+1:>3} {r['label']:<35} {r['trades']:>4} {r['win_rate']:>5.1%} {r['calmar']:>5.2f} "
            f"│ {s1:>7} {pbo1:>10} {mdp1:>7} {r['1x_ev']:>6.3f} "
            f"│ {s2:>7} {pbo2:>10} {mdp2:>7} {r['2x_ev']:>6.3f}"
        )

    # ── TOP 25 by Calmar with both risk levels ───────────────────────────

    rows_by_calmar = sorted(rows, key=lambda r: r["calmar"], reverse=True)

    print(f"\n{'=' * 180}")
    print("TOP 25 BY CALMAR — side-by-side comparison")
    print(f"{'=' * 180}")
    print(hdr)
    print("-" * 180)

    for i, r in enumerate(rows_by_calmar[:25]):
        s1 = f"{r['1x_success']:.0%}" if r["1x_success"] is not None else "N/A"
        s2 = f"{r['2x_success']:.0%}" if r["2x_success"] is not None else "N/A"
        pbo1 = f"{r['1x_payouts']}/{r['1x_breaches']}/{r['1x_open']}"
        pbo2 = f"{r['2x_payouts']}/{r['2x_breaches']}/{r['2x_open']}"
        mdp1 = f"{r['1x_med_days_pay']:.0f}" if r["1x_med_days_pay"] is not None else "-"
        mdp2 = f"{r['2x_med_days_pay']:.0f}" if r["2x_med_days_pay"] is not None else "-"
        print(
            f"{i+1:>3} {r['label']:<35} {r['trades']:>4} {r['win_rate']:>5.1%} {r['calmar']:>5.2f} "
            f"│ {s1:>7} {pbo1:>10} {mdp1:>7} {r['1x_ev']:>6.3f} "
            f"│ {s2:>7} {pbo2:>10} {mdp2:>7} {r['2x_ev']:>6.3f}"
        )

    # ── Detailed analysis: top 5 by 2x success rate ─────────────────────

    print(f"\n{'=' * 160}")
    print("DETAILED ACCOUNT ANALYSIS — TOP 5 BY 2x RISK SUCCESS RATE")
    print(f"{'=' * 160}")

    for i, r in enumerate(rows_by_2x[:5]):
        s1 = f"{r['1x_success']:.1%}" if r["1x_success"] is not None else "N/A"
        s2 = f"{r['2x_success']:.1%}" if r["2x_success"] is not None else "N/A"
        print(f"\n{'─' * 120}")
        print(f"  #{i+1}: {r['label']}")
        print(f"  Strategy: {r['trades']} trades  |  WR: {r['win_rate']:.1%}  |  Net R: {r['net_r']:.2f}  |  Max DD: {r['max_dd_r']:.2f}R  |  Calmar: {r['calmar']:.2f}")

        print(f"\n  1x RISK ($5k/trade → +5R/-4R):")
        print(f"    Accounts: {r['1x_accounts']}  |  {r['1x_payouts']} payouts  |  {r['1x_breaches']} breaches  |  {r['1x_open']} open")
        print(f"    Success: {s1}  |  EV: {r['1x_ev']:.3f}R")
        if r["1x_med_days_pay"] is not None:
            print(f"    Payout: avg {r['1x_avg_days_pay']:.0f} days  (median {r['1x_med_days_pay']:.0f} days)")
        if r["1x_med_days_breach"] is not None:
            print(f"    Breach: avg {r['1x_avg_days_breach']:.0f} days  (median {r['1x_med_days_breach']:.0f} days)")

        print(f"\n  2x RISK ($10k/trade → +2.5R/-2.0R):")
        print(f"    Accounts: {r['2x_accounts']}  |  {r['2x_payouts']} payouts  |  {r['2x_breaches']} breaches  |  {r['2x_open']} open")
        print(f"    Success: {s2}  |  EV: {r['2x_ev']:.3f}R")
        if r["2x_med_days_pay"] is not None:
            print(f"    Payout: avg {r['2x_avg_days_pay']:.0f} days  (median {r['2x_med_days_pay']:.0f} days)")
        if r["2x_med_days_breach"] is not None:
            print(f"    Breach: avg {r['2x_avg_days_breach']:.0f} days  (median {r['2x_med_days_breach']:.0f} days)")

        # Show 2x account-by-account breakdown
        details = r["2x_details"]
        if details:
            print(f"\n  2x RISK Account-by-account:")
            print(f"  {'Started':<12} {'Outcome':<10} {'Final R':>8} {'Peak R':>7} {'Trough':>7} {'Trades':>6} {'Days':>6} {'Resolved':<12}")
            for d in details:
                outcome_col = d['outcome'].upper()
                if d['outcome'] == 'payout':
                    outcome_col = f"\033[92m{outcome_col}\033[0m"
                elif d['outcome'] == 'breach':
                    outcome_col = f"\033[91m{outcome_col}\033[0m"
                else:
                    outcome_col = f"\033[93m{outcome_col}\033[0m"
                print(f"  {d['account_start']:<12} {outcome_col:<19} {d['final_r']:>8.3f} {d['peak_r']:>7.3f} {d['trough_r']:>7.3f} {d['trades_taken']:>6} {d['calendar_days']:>6} {d['outcome_date']:<12}")

    # ── Summary comparison ────────────────────────────────────────────────

    print(f"\n{'=' * 100}")
    print("SUMMARY: Best config at each risk level")
    print(f"{'=' * 100}")

    best_1x = sorted(rows, key=lambda r: (r["1x_success"] or 0, r["1x_ev"]), reverse=True)[0]
    best_2x = rows_by_2x[0]

    for label, r, risk_label in [
        ("Best 1x config", best_1x, "1x"),
        ("Best 2x config", best_2x, "2x"),
    ]:
        sr = r[f"{risk_label}_success"]
        sr_str = f"{sr:.1%}" if sr is not None else "N/A"
        mdp = r[f"{risk_label}_med_days_pay"]
        mdp_str = f"{mdp:.0f}" if mdp is not None else "-"
        mdb = r[f"{risk_label}_med_days_breach"]
        mdb_str = f"{mdb:.0f}" if mdb is not None else "-"
        print(f"\n  {label}: {r['label']}")
        print(f"    {r['trades']} trades  |  WR: {r['win_rate']:.1%}  |  Calmar: {r['calmar']:.2f}")
        print(f"    Success: {sr_str}  |  P/B/O: {r[f'{risk_label}_payouts']}/{r[f'{risk_label}_breaches']}/{r[f'{risk_label}_open']}  |  EV: {r[f'{risk_label}_ev']:.3f}R")
        print(f"    Median days to payout: {mdp_str}  |  Median days to breach: {mdb_str}")

    # ── Save results ──────────────────────────────────────────────────────

    output_path = Path(__file__).parent.parent / "data" / "results" / "nq_lsi_propfirm_2x_risk.json"

    save_data = {
        "sweep_info": {
            "description": "Prop firm sweep: 1x vs 2x risk comparison",
            "model_1x": "+5R payout / -4R breach ($5k risk)",
            "model_2x": "+2.5R payout / -2.0R breach ($10k risk — equivalent to doubling position size)",
            "start_date": START_DATE,
            "end_date": END_DATE,
            "stagger_days": CYCLE_DAYS,
            "total_configs": len(rows),
            "sweep_time_s": round(time.time() - t0, 1),
        },
        "top50_by_2x_success": [
            {k: v for k, v in r.items() if k not in ("config", "1x_details", "2x_details")}
            for r in rows_by_2x[:50]
        ],
        "top50_by_calmar": [
            {k: v for k, v in r.items() if k not in ("config", "1x_details", "2x_details")}
            for r in rows_by_calmar[:50]
        ],
    }

    def convert(obj):
        if isinstance(obj, tuple):
            return list(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2, default=convert)

    print(f"\nResults saved to {output_path}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
