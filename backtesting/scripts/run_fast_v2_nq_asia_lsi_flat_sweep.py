#!/usr/bin/env python3
"""NQ Asia LSI — Flat Start/End Window Sweep

Sweeps flat_start for the NQ_Asia_LSI leg using the FAST_V2 anchor config
(saved config ID 12: nq_asia_lsi 2yr_opt phase_1).

Flat start range: 23:00 → 04:00 (15-min steps, cross-midnight)
Flat end is always flat_start + 10 minutes.

Date range: last 2 years (2024-03-16 to 2026-03-16).
"""

import dataclasses
import datetime
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Date range ────────────────────────────────────────────────────────────

START_DATE = "2024-03-16"
END_DATE = "2026-03-16"

# ── Prop firm parameters ──────────────────────────────────────────────────

PAYOUT_TARGET = 5.0
BREACH_LIMIT = -4.0
CYCLE_DAYS = 14

# ── Time helpers ──────────────────────────────────────────────────────────


def time_range(start: str, end: str, step_minutes: int = 15) -> list[str]:
    """Generate HH:MM time strings from start to end (inclusive), wrapping midnight."""
    times = []
    h, m = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    start_min = h * 60 + m
    end_min = eh * 60 + em
    if end_min < start_min:
        end_min += 24 * 60  # wrap midnight
    cur = start_min
    while cur <= end_min:
        actual = cur % (24 * 60)
        times.append(f"{actual // 60:02d}:{actual % 60:02d}")
        cur += step_minutes
    return times


def add_minutes(t: str, minutes: int) -> str:
    """Add minutes to an HH:MM string, wrapping at midnight."""
    h, m = map(int, t.split(":"))
    total = (h * 60 + m + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


# ── Anchor config (nq_asia_lsi 2yr_opt phase_1, saved config ID 12) ──────

ASIA_SESSION = SessionConfig(
    name="ASIA",
    rth_start="20:00",
    entry_start="20:40",
    entry_end="23:30",
    flat_start="00:00",
    flat_end="00:10",
    stop_atr_pct=0.0,
    min_gap_atr_pct=1.75,
)

ANCHOR = StrategyConfig(
    sessions=(ASIA_SESSION,),
    instrument=NQ,
    strategy="lsi",
    direction_filter="long",
    use_bar_magnifier=True,
    rr=1.75,
    tp1_ratio=0.7,
    atr_length=40,
    risk_usd=5000.0,
    lsi_n_left=3,
    lsi_n_right=3,
    lsi_fvg_window_left=10,
    lsi_fvg_window_right=10,
    lsi_stop_mode="absolute",
    lsi_entry_mode="close",
    lsi_first_fvg_only=False,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
)

# ── Sweep range ───────────────────────────────────────────────────────────
# Flat start: 23:00 → 04:00 in 15-min steps (cross-midnight)
# Flat end = flat_start + 10 minutes (fixed 10-min window)

FLAT_STARTS = time_range("23:00", "04:00", 15)


# ── Staggered account simulation ─────────────────────────────────────────


def simulate_staggered_accounts(
    trades: list,
    start_date: str,
    end_date: str,
    payout_r: float = PAYOUT_TARGET,
    breach_r: float = BREACH_LIMIT,
    stagger_days: int = CYCLE_DAYS,
) -> dict:
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return _empty()

    trade_data = sorted(
        [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in filled],
        key=lambda x: x["date"],
    )

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

    total = len(results)
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

    return {
        "total_accounts": total,
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": round(success_rate, 4) if success_rate is not None else None,
        "ev_per_account": round(ev, 4),
        "avg_days_to_payout": round(float(np.mean([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "avg_days_to_breach": round(float(np.mean([r["calendar_days"] for r in breaches])), 1) if breaches else None,
    }


def _empty():
    return {"total_accounts": 0, "payouts": 0, "breaches": 0, "open": 0,
            "success_rate": None, "ev_per_account": 0.0,
            "avg_days_to_payout": None, "median_days_to_payout": None,
            "avg_days_to_breach": None}


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    t0 = time.time()

    print("=" * 120)
    print("NQ Asia LSI — Flat Start Window Sweep (FAST_V2)")
    print("=" * 120)
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Prop firm: +{PAYOUT_TARGET}R / {BREACH_LIMIT}R, new account every {CYCLE_DAYS} days")
    print(f"Anchor flat: {ASIA_SESSION.flat_start}-{ASIA_SESSION.flat_end}")
    print(f"Sweep flat_start: {FLAT_STARTS[0]} → {FLAT_STARTS[-1]} ({len(FLAT_STARTS)} values, 15-min steps)")
    print(f"Flat window = 10 minutes (flat_end = flat_start + 10m)\n")

    # ── Load data ─────────────────────────────────────────────────────────
    print("Loading NQ data...")
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  NQ: {len(df_5m):,} 5m bars  |  {len(df_1m):,} 1m bars\n")

    # ── Build configs ─────────────────────────────────────────────────────
    configs = []
    for fs in FLAT_STARTS:
        fe = add_minutes(fs, 10)
        new_sess = dataclasses.replace(ASIA_SESSION, flat_start=fs, flat_end=fe)
        new_cfg = dataclasses.replace(ANCHOR, sessions=(new_sess,))
        label = f"flat={fs}-{fe}"
        configs.append((label, new_cfg))

    print(f"Running {len(configs)} flat window variants...\n")

    # ── Run sweep ─────────────────────────────────────────────────────────
    rows = []
    for i, (label, cfg) in enumerate(configs):
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, end_date=END_DATE, df_1m=df_1m)
        m = compute_metrics(trades)
        acct = simulate_staggered_accounts(trades, START_DATE, END_DATE)

        sess = cfg.sessions[0]
        rows.append({
            "label": label,
            "flat_start": sess.flat_start,
            "flat_end": sess.flat_end,
            "trades": m["total_trades"],
            "win_rate": m["win_rate"],
            "net_r": m["total_r"],
            "avg_r": m["avg_r"],
            "max_dd_r": m["max_drawdown_r"],
            "calmar": m["calmar_ratio"],
            "sharpe": m["sharpe_ratio"],
            "pf": m["profit_factor"],
            "r_per_year": m["total_r"] / 2.0,
            "success_rate": acct["success_rate"],
            "ev_per_account": acct["ev_per_account"],
            "payouts": acct["payouts"],
            "breaches": acct["breaches"],
            "open": acct["open"],
            "total_accounts": acct["total_accounts"],
            "avg_days_to_payout": acct["avg_days_to_payout"],
            "median_days_to_payout": acct["median_days_to_payout"],
        })

        if (i + 1) % 5 == 0 or (i + 1) == len(configs):
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(configs)}] {elapsed:.0f}s elapsed")

    # ── Sort and display ──────────────────────────────────────────────────
    rows_by_calmar = sorted(rows, key=lambda r: r["calmar"], reverse=True)

    anchor_flat = f"{ASIA_SESSION.flat_start}-{ASIA_SESSION.flat_end}"

    print(f"\n{'='*120}")
    print(f"  ALL RESULTS BY CALMAR")
    print(f"{'='*120}")
    print(f"  {'#':>3} {'Flat Window':<16} {'Tr':>4} {'WR%':>6} {'NetR':>6} {'R/yr':>5} {'MaxDD':>6} {'Calm':>6} {'Shrp':>5} {'PF':>5} "
          f"{'Acct':>4} {'Pay':>3} {'Br':>3} {'SuccR%':>7} {'AvgDPay':>7} {'EV/a':>6}")
    print(f"  {'-'*120}")

    for i, r in enumerate(rows_by_calmar):
        sr = f"{r['success_rate']:.0%}" if r["success_rate"] is not None else "N/A"
        adp = f"{r['avg_days_to_payout']:.0f}" if r["avg_days_to_payout"] is not None else "-"
        window = f"{r['flat_start']}-{r['flat_end']}"
        marker = " *" if window == anchor_flat else ""
        print(
            f"  {i+1:>3} {window:<14}{marker:>2} {r['trades']:>4} {r['win_rate']:>5.1%} {r['net_r']:>6.1f} "
            f"{r['r_per_year']:>5.1f} {r['max_dd_r']:>6.2f} {r['calmar']:>6.2f} {r['sharpe']:>5.2f} {r['pf']:>5.2f} "
            f"{r['total_accounts']:>4} {r['payouts']:>3} {r['breaches']:>3} "
            f"{sr:>7} {adp:>7} {r['ev_per_account']:>6.3f}"
        )

    # ── Recommendation ────────────────────────────────────────────────────
    # Composite: success_rate * 0.4 + calmar_norm * 0.3 + net_r_norm * 0.3
    max_calmar = max(r["calmar"] for r in rows) or 1
    max_net_r = max(r["net_r"] for r in rows) or 1

    for r in rows:
        sr = r["success_rate"] or 0
        calmar_norm = r["calmar"] / max_calmar if max_calmar > 0 else 0
        net_r_norm = r["net_r"] / max_net_r if max_net_r > 0 else 0
        r["composite"] = sr * 0.4 + calmar_norm * 0.3 + net_r_norm * 0.3

    best = max(rows, key=lambda r: r["composite"])
    recommended = f"{best['flat_start']}-{best['flat_end']}"
    changed = " (CHANGED)" if anchor_flat != recommended else " (same)"

    sr = f"{best['success_rate']:.0%}" if best["success_rate"] is not None else "N/A"
    print(f"\n{'='*120}")
    print(f"  RECOMMENDATION")
    print(f"{'='*120}")
    print(f"  Current:     {anchor_flat}")
    print(f"  Recommended: {recommended}{changed}")
    print(f"  Trades={best['trades']}  WR={best['win_rate']:.1%}  Net R={best['net_r']:.1f}  "
          f"Calmar={best['calmar']:.2f}  Sharpe={best['sharpe']:.2f}  "
          f"SuccRate={sr}  EV={best['ev_per_account']:.3f}R")

    # ── Save results ──────────────────────────────────────────────────────
    output_path = Path(__file__).parent.parent / "data" / "results" / "fast_v2_nq_asia_lsi_flat_sweep.json"

    def convert(obj):
        if isinstance(obj, tuple):
            return list(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    save_data = {
        "sweep_info": {
            "description": "NQ Asia LSI flat start window sweep (FAST_V2)",
            "anchor_flat": anchor_flat,
            "sweep_range": f"{FLAT_STARTS[0]} → {FLAT_STARTS[-1]}",
            "step_minutes": 15,
            "flat_window_minutes": 10,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "payout_target": PAYOUT_TARGET,
            "breach_limit": BREACH_LIMIT,
            "stagger_days": CYCLE_DAYS,
            "sweep_time_s": round(time.time() - t0, 1),
        },
        "all_results_by_calmar": rows_by_calmar,
        "recommendation": {
            "flat_window": recommended,
            "changed": anchor_flat != recommended,
            **{k: best[k] for k in ("trades", "win_rate", "net_r", "calmar", "sharpe",
                                      "success_rate", "ev_per_account", "composite")},
        },
    }

    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2, default=convert)

    print(f"\nResults saved to {output_path}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
