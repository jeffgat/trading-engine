#!/usr/bin/env python3
"""Prop firm phase 1 sweep: NQ NY Continuation — long vs both directions

Anchor from "nq_ny 2yr_opt phase_1":
  rr=2, tp1=0.7, stop=9%, gap=2.25%, ORB=09:30-09:45,
  entry<=13:00, flat=15:50, both directions, ATR=14, bar magnifier, ICF=OFF

Sweeps tp1_ratio, rr, stop_atr_pct across long-only and both-directions.
"""

import dataclasses
import datetime
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import generate_param_grid, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.engine.simulator import EXIT_NO_FILL

# ── Anchor config ─────────────────────────────────────────────────────────

INSTRUMENT = get_instrument("NQ")

NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=2.25,
)

ANCHOR = StrategyConfig(
    strategy="continuation",
    direction_filter="both",
    rr=2.0,
    tp1_ratio=0.7,
    risk_usd=5000.0,
    atr_length=14,
    use_bar_magnifier=True,
    impulse_close_filter=False,
    sessions=(NY_SESSION,),
    instrument=INSTRUMENT,
)

# ── Date range ─────────────────────────────────────────────────────────────

START_DATE = "2024-03-14"
END_DATE = "2026-03-14"

# ── Prop firm cycle parameters ─────────────────────────────────────────────

PAYOUT_TARGET = 5.0
BREACH_LIMIT = -4.0
CYCLE_DAYS = 14

# ── Grid ───────────────────────────────────────────────────────────────────

PARAM_GRID = {
    "rr": [1.5, 1.75, 2.0, 2.25, 2.5, 3.0],
    "tp1_ratio": [0.3, 0.4, 0.5, 0.6, 0.7],
    "ny_stop_atr_pct": [6.0, 7.0, 8.0, 9.0, 10.0, 12.0],
}

# Direction variants
DIRECTION_VARIANTS = [
    ("long", "long"),
    ("both", "both"),
]


def simulate_staggered_accounts(
    trades: list,
    start_date: str,
    end_date: str,
    payout_r: float = PAYOUT_TARGET,
    breach_r: float = BREACH_LIMIT,
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

    max_concurrent = 0
    for i, r in enumerate(results):
        concurrent = sum(
            1 for r2 in results
            if r2["account_start"] <= r["account_start"]
            and r2["outcome_date"] >= r["account_start"]
        )
        max_concurrent = max(max_concurrent, concurrent)

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
        "max_concurrent_accounts": max_concurrent,
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
        "ev_per_account": 0.0, "max_concurrent_accounts": 0,
        "account_details": [],
    }


def config_label(cfg: StrategyConfig) -> str:
    d = cfg.direction_filter or "both"
    sess = cfg.sessions[0]
    return f"rr={cfg.rr} tp1={cfg.tp1_ratio} stop={sess.stop_atr_pct} {d}"


def main():
    t0 = time.time()

    # ── Load data ──────────────────────────────────────────────────────────
    print("Loading NQ data...")
    df = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  5m: {len(df):,} bars  |  1m: {len(df_1m):,} bars")

    # ── Generate grid ──────────────────────────────────────────────────────
    all_configs = []

    for dir_name, dir_filter in DIRECTION_VARIANTS:
        base = dataclasses.replace(ANCHOR, direction_filter=dir_filter)
        configs = generate_param_grid(base, PARAM_GRID)
        all_configs.extend(configs)
        print(f"  DIR={dir_name}: {len(configs)} configs")

    print(f"\n{describe_grid(PARAM_GRID)}")
    print(f"x {len(DIRECTION_VARIANTS)} direction variants = {len(all_configs):,} total configs\n")

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

    # ── Compute metrics + staggered account simulations ──────────────────
    print("Computing metrics and staggered account simulations...")
    print(f"  Model: new account every {CYCLE_DAYS} days, +{PAYOUT_TARGET}R / {BREACH_LIMIT}R")

    rows = []
    for cfg, trades in results:
        metrics = compute_metrics(trades)
        acct_stats = simulate_staggered_accounts(
            trades, START_DATE, END_DATE,
            payout_r=PAYOUT_TARGET, breach_r=BREACH_LIMIT, stagger_days=CYCLE_DAYS,
        )

        rows.append({
            "config": cfg,
            "label": config_label(cfg),
            "rr": cfg.rr,
            "tp1_ratio": cfg.tp1_ratio,
            "stop_atr_pct": cfg.sessions[0].stop_atr_pct,
            "direction": cfg.direction_filter or "both",
            # Standard metrics
            "trades": metrics["total_trades"],
            "win_rate": metrics["win_rate"],
            "net_r": metrics["total_r"],
            "max_dd_r": metrics["max_drawdown_r"],
            "calmar": metrics["calmar_ratio"],
            "sharpe": metrics["sharpe_ratio"],
            "pf": metrics["profit_factor"],
            "avg_r": metrics["avg_r"],
            # Staggered account stats
            "total_accounts": acct_stats["total_accounts"],
            "payouts": acct_stats["payouts"],
            "breaches": acct_stats["breaches"],
            "open": acct_stats["open"],
            "payout_rate": acct_stats["payout_rate"],
            "breach_rate": acct_stats["breach_rate"],
            "success_rate": acct_stats["success_rate_resolved"],
            "ev_per_account": acct_stats["ev_per_account"],
            "avg_trades_to_payout": acct_stats["avg_trades_to_payout"],
            "avg_days_to_payout": acct_stats["avg_days_to_payout"],
            "median_days_to_payout": acct_stats["median_days_to_payout"],
            "avg_trades_to_breach": acct_stats["avg_trades_to_breach"],
            "avg_days_to_breach": acct_stats["avg_days_to_breach"],
            "median_days_to_breach": acct_stats["median_days_to_breach"],
            "avg_open_r": acct_stats["avg_open_r"],
            "median_open_r": acct_stats["median_open_r"],
            "max_concurrent": acct_stats["max_concurrent_accounts"],
            "account_details": acct_stats["account_details"],
        })

    # Filter: >= 50 trades
    rows = [r for r in rows if r["trades"] >= 50]

    rows_by_calmar = sorted(rows, key=lambda r: r["calmar"], reverse=True)

    rows_by_propfirm = sorted(
        rows,
        key=lambda r: (
            r["success_rate"] or 0,
            r["ev_per_account"],
            -abs(r.get("avg_days_to_payout") or 9999),
            r["calmar"],
        ),
        reverse=True,
    )

    # ── Print results ──────────────────────────────────────────────────────

    print(f"\n{'=' * 155}")
    print("TOP 25 BY CALMAR — NQ NY Continuation (long vs both)")
    print(f"{'=' * 155}")
    print(f"{'#':>3} {'Config':<38} {'Tr':>4} {'WR%':>6} {'NetR':>6} {'MaxDD':>6} {'Calm':>5} {'Shrp':>5} "
          f"{'Acct':>4} {'Pay':>4} {'Brch':>4} {'Open':>4} {'SuccR%':>7} {'AvgDPay':>7} {'AvgDBr':>6} {'EV/act':>7}")
    print("-" * 155)

    for i, r in enumerate(rows_by_calmar[:25]):
        sr = f"{r['success_rate']:.0%}" if r["success_rate"] is not None else "N/A"
        adp = f"{r['avg_days_to_payout']:.0f}" if r["avg_days_to_payout"] is not None else "-"
        adb = f"{r['avg_days_to_breach']:.0f}" if r["avg_days_to_breach"] is not None else "-"
        print(
            f"{i+1:>3} {r['label']:<38} {r['trades']:>4} {r['win_rate']:>5.1%} {r['net_r']:>6.1f} "
            f"{r['max_dd_r']:>6.2f} {r['calmar']:>5.2f} {r['sharpe']:>5.2f} "
            f"{r['total_accounts']:>4} {r['payouts']:>4} {r['breaches']:>4} {r['open']:>4} "
            f"{sr:>7} {adp:>7} {adb:>6} {r['ev_per_account']:>7.3f}"
        )

    print(f"\n{'=' * 155}")
    print("TOP 25 BY PROP FIRM SUCCESS (success rate -> EV -> time to payout)")
    print(f"{'=' * 155}")
    print(f"{'#':>3} {'Config':<38} {'Tr':>4} {'WR%':>6} {'NetR':>6} {'Calm':>5} "
          f"{'Acct':>4} {'Pay':>4} {'Brch':>4} {'Open':>4} {'SuccR%':>7} "
          f"{'AvgTrP':>6} {'AvgDP':>5} {'MedDP':>5} {'AvgTrB':>6} {'AvgDB':>5} {'MedDB':>5} {'EV/act':>7}")
    print("-" * 155)

    for i, r in enumerate(rows_by_propfirm[:25]):
        sr = f"{r['success_rate']:.0%}" if r["success_rate"] is not None else "N/A"
        atp = f"{r['avg_trades_to_payout']:.0f}" if r["avg_trades_to_payout"] is not None else "-"
        adp = f"{r['avg_days_to_payout']:.0f}" if r["avg_days_to_payout"] is not None else "-"
        mdp = f"{r['median_days_to_payout']:.0f}" if r["median_days_to_payout"] is not None else "-"
        atb = f"{r['avg_trades_to_breach']:.0f}" if r["avg_trades_to_breach"] is not None else "-"
        adb = f"{r['avg_days_to_breach']:.0f}" if r["avg_days_to_breach"] is not None else "-"
        mdb = f"{r['median_days_to_breach']:.0f}" if r["median_days_to_breach"] is not None else "-"
        print(
            f"{i+1:>3} {r['label']:<38} {r['trades']:>4} {r['win_rate']:>5.1%} {r['net_r']:>6.1f} {r['calmar']:>5.2f} "
            f"{r['total_accounts']:>4} {r['payouts']:>4} {r['breaches']:>4} {r['open']:>4} {sr:>7} "
            f"{atp:>6} {adp:>5} {mdp:>5} {atb:>6} {adb:>5} {mdb:>5} {r['ev_per_account']:>7.3f}"
        )

    # ── Detailed top 5 ────────────────────────────────────────────────────

    print(f"\n{'=' * 155}")
    print("DETAILED ACCOUNT ANALYSIS — TOP 5 BY SUCCESS RATE")
    print(f"{'=' * 155}")

    for i, r in enumerate(rows_by_propfirm[:5]):
        sr = f"{r['success_rate']:.1%}" if r["success_rate"] is not None else "N/A"
        print(f"\n{'─' * 100}")
        print(f"  #{i+1}: {r['label']}")
        print(f"  Strategy: {r['trades']} trades  |  WR: {r['win_rate']:.1%}  |  Net R: {r['net_r']:.2f}  |  Max DD: {r['max_dd_r']:.2f}R  |  Calmar: {r['calmar']:.2f}  |  Sharpe: {r['sharpe']:.2f}")
        print(f"  Accounts: {r['total_accounts']} started  |  {r['payouts']} payouts  |  {r['breaches']} breaches  |  {r['open']} still open")
        print(f"  Success Rate: {sr}  |  EV per account: {r['ev_per_account']:.3f}R")

        if r["avg_trades_to_payout"] is not None:
            print(f"  Payout: avg {r['avg_trades_to_payout']:.1f} trades / {r['avg_days_to_payout']:.0f} days  (median {r['median_days_to_payout']:.0f} days)")
        if r["avg_trades_to_breach"] is not None:
            print(f"  Breach: avg {r['avg_trades_to_breach']:.1f} trades / {r['avg_days_to_breach']:.0f} days  (median {r['median_days_to_breach']:.0f} days)")

        if r["avg_open_r"] is not None:
            print(f"  Open accounts: avg {r['avg_open_r']:.2f}R  |  median {r['median_open_r']:.2f}R")

        details = r["account_details"]
        if details:
            print(f"\n  Account-by-account:")
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

    # ── Save ───────────────────────────────────────────────────────────────

    output_path = Path(__file__).parent.parent / "data" / "results" / "nq_ny_cont_propfirm_sweep_v2.json"

    save_data = {
        "sweep_info": {
            "anchor_name": "nq_ny 2yr_opt phase_1",
            "model": f"staggered accounts — new every {CYCLE_DAYS} days, +{PAYOUT_TARGET}R / {BREACH_LIMIT}R",
            "start_date": START_DATE,
            "end_date": END_DATE,
            "payout_target": PAYOUT_TARGET,
            "breach_limit": BREACH_LIMIT,
            "stagger_days": CYCLE_DAYS,
            "total_configs": len(all_configs),
            "eligible_configs": len(rows),
            "grid": {k: [str(v) for v in vs] for k, vs in PARAM_GRID.items()},
            "direction_variants": [name for name, _ in DIRECTION_VARIANTS],
            "sweep_time_s": round(sweep_time, 1),
        },
        "top50_by_calmar": [
            {k: v for k, v in r.items() if k not in ("config", "account_details")}
            for r in rows_by_calmar[:50]
        ],
        "top50_by_propfirm": [
            {k: v for k, v in r.items() if k not in ("config", "account_details")}
            for r in rows_by_propfirm[:50]
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
