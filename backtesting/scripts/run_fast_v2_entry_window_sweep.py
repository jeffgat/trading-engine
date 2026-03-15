#!/usr/bin/env python3
"""FAST_V2 Entry Window Optimization — Phase 1 Prop Firm + Calmar + Net R

Sweeps entry_start and/or entry_end for each of the 5 FAST_V2 legs:
  1. NQ_NY      (ORB cont)  — sweep entry_end only (entry_start = orb_end)
  2. NQ_Asia    (ORB cont)  — sweep entry_end only
  3. ES_Asia    (ORB cont)  — sweep entry_end only
  4. NQ_Asia_LSI            — sweep entry_start + entry_end
  5. NQ_NY_LSI              — sweep entry_start + entry_end

Constraints: entry window cannot start before session start or end after the
following session start.

All other params are locked to current FAST_V2 values.
Date range: last 2 years (2024-03-14 to 2026-03-14).
"""

import dataclasses
import datetime
import json
import sys
import time
from itertools import product
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Date range ────────────────────────────────────────────────────────────

START_DATE = "2024-03-14"
END_DATE = "2026-03-14"

# ── Prop firm parameters ──────────────────────────────────────────────────

PAYOUT_TARGET = 5.0
BREACH_LIMIT = -4.0
CYCLE_DAYS = 14

# ── Time helpers ──────────────────────────────────────────────────────────


def time_range(start: str, end: str, step_minutes: int = 30) -> list[str]:
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


# ── FAST_V2 Anchor Configs ────────────────────────────────────────────────

LEGS = {
    "NQ_NY": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:45",
                entry_start="09:45",
                entry_end="13:00",
                flat_start="15:50",
                flat_end="16:00",
                stop_atr_pct=8.0,
                min_gap_atr_pct=2.25,
            ),),
            instrument=NQ,
            strategy="continuation",
            direction_filter="both",
            use_bar_magnifier=True,
            rr=2.5,
            tp1_ratio=0.3,
            atr_length=14,
            risk_usd=5000.0,
            excluded_days=(4,),  # Friday
        ),
        "data": "NQ",
        # entry_start is locked to orb_end; sweep entry_end only
        # Constraint: cannot go past 20:00 (Asia session start), but flat_end=16:00
        # is the hard ceiling so sweep up to 16:00
        "sweep_entry_start": None,
        "sweep_entry_end": time_range("10:00", "16:00", 30),
    },
    "NQ_Asia": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="22:30",
                flat_start="04:00",
                flat_end="07:00",
                stop_atr_pct=4.0,
                stop_orb_pct=150.0,
                min_gap_atr_pct=0.9,
                min_gap_orb_pct=15.0,
            ),),
            instrument=NQ,
            strategy="continuation",
            direction_filter="long",
            use_bar_magnifier=True,
            rr=5.0,
            tp1_ratio=0.25,
            atr_length=5,
            risk_usd=5000.0,
            excluded_days=(1,),  # Tuesday
            excluded_dates=("20241218",),
            half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        ),
        "data": "NQ",
        # entry_start locked to orb_end (20:15)
        # Constraint: cannot go past 09:30 next day (NY session start)
        # flat_start=04:00 is practical ceiling, but sweep up to 04:00
        "sweep_entry_start": None,
        "sweep_entry_end": time_range("21:00", "04:00", 30),
    },
    "ES_Asia": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:10",
                entry_start="20:10",
                entry_end="03:00",
                flat_start="06:45",
                flat_end="07:00",
                stop_atr_pct=2.5,
                min_gap_atr_pct=1.0,
            ),),
            instrument=ES,
            strategy="continuation",
            direction_filter="long",
            use_bar_magnifier=True,
            rr=1.75,
            tp1_ratio=0.3,
            atr_length=5,
            risk_usd=5000.0,
            excluded_dates=("20241218",),
            half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        ),
        "data": "ES",
        # entry_start locked to orb_end (20:10)
        # Constraint: cannot go past 09:30 (NY start), flat at 06:45
        "sweep_entry_start": None,
        "sweep_entry_end": time_range("21:00", "06:30", 30),
    },
    "NQ_Asia_LSI": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="ASIA",
                rth_start="20:00",
                entry_start="20:40",
                entry_end="23:30",
                flat_start="00:00",
                flat_end="01:00",
                stop_atr_pct=0.0,
                min_gap_atr_pct=1.75,
            ),),
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
        ),
        "data": "NQ",
        # rth_start=20:00 — entry_start must be >= 20:00
        # Constraint: cannot go past 09:30 next day (NY session start)
        "sweep_entry_start": time_range("20:15", "21:30", 15),
        "sweep_entry_end": time_range("22:00", "04:00", 30),
    },
    "NQ_NY_LSI": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY",
                rth_start="09:30",
                entry_start="09:35",
                entry_end="15:30",
                flat_start="15:50",
                flat_end="16:00",
                stop_atr_pct=0.0,
                min_gap_atr_pct=3.75,
            ),),
            instrument=NQ,
            strategy="lsi",
            direction_filter="long",
            use_bar_magnifier=True,
            rr=2.5,
            tp1_ratio=0.2,
            atr_length=10,
            risk_usd=5000.0,
            lsi_n_left=5,
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
        ),
        "data": "NQ",
        # rth_start=09:30 — entry_start must be >= 09:30
        # Constraint: cannot go past 20:00 (Asia session start), flat at 15:50
        "sweep_entry_start": time_range("09:35", "10:30", 5),
        "sweep_entry_end": time_range("11:00", "15:50", 30),
    },
}


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


# ── Build configs for a leg ───────────────────────────────────────────────


def build_leg_configs(leg_name: str, leg: dict) -> list[tuple[str, StrategyConfig]]:
    """Generate all entry window variants for a leg. Returns (label, config) pairs."""
    base_cfg = leg["config"]
    base_sess = base_cfg.sessions[0]
    entry_starts = leg["sweep_entry_start"]
    entry_ends = leg["sweep_entry_end"]

    configs = []

    if entry_starts and entry_ends:
        # Sweep both dimensions
        for es, ee in product(entry_starts, entry_ends):
            # entry_start must be before entry_end (accounting for midnight wrap)
            new_sess = dataclasses.replace(base_sess, entry_start=es, entry_end=ee)
            new_cfg = dataclasses.replace(base_cfg, sessions=(new_sess,))
            label = f"{leg_name} es={es} ee={ee}"
            configs.append((label, new_cfg))
    elif entry_ends:
        # Sweep entry_end only (ORB legs)
        for ee in entry_ends:
            new_sess = dataclasses.replace(base_sess, entry_end=ee)
            new_cfg = dataclasses.replace(base_cfg, sessions=(new_sess,))
            label = f"{leg_name} ee={ee}"
            configs.append((label, new_cfg))
    elif entry_starts:
        # Sweep entry_start only
        for es in entry_starts:
            new_sess = dataclasses.replace(base_sess, entry_start=es)
            new_cfg = dataclasses.replace(base_cfg, sessions=(new_sess,))
            label = f"{leg_name} es={es}"
            configs.append((label, new_cfg))

    return configs


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    t0 = time.time()

    print("=" * 120)
    print("FAST_V2 Entry Window Optimization — Phase 1 Prop Firm + Calmar + Net R")
    print("=" * 120)
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Prop firm: +{PAYOUT_TARGET}R / {BREACH_LIMIT}R, new account every {CYCLE_DAYS} days\n")

    # ── Load data ─────────────────────────────────────────────────────────
    print("Loading data...")
    data_cache = {}
    for symbol in ("NQ", "ES"):
        df_5m = load_5m_data(f"{symbol}_5m.parquet")
        df_1m = load_1m_for_5m(f"{symbol}_5m.parquet")
        data_cache[symbol] = (df_5m, df_1m)
        print(f"  {symbol}: {len(df_5m):,} 5m bars  |  {len(df_1m):,} 1m bars")

    print()

    # ── Run each leg ──────────────────────────────────────────────────────
    all_results = {}

    for leg_name, leg in LEGS.items():
        configs = build_leg_configs(leg_name, leg)
        symbol = leg["data"]
        df_5m, df_1m = data_cache[symbol]

        print(f"\n{'='*100}")
        print(f"  {leg_name}: {len(configs)} entry window variants")
        print(f"{'='*100}")

        # Show current/anchor value
        anchor_sess = leg["config"].sessions[0]
        print(f"  Anchor: entry_start={anchor_sess.entry_start} entry_end={anchor_sess.entry_end}")

        if leg["sweep_entry_start"]:
            print(f"  Sweep entry_start: {leg['sweep_entry_start'][0]} → {leg['sweep_entry_start'][-1]} ({len(leg['sweep_entry_start'])} values)")
        if leg["sweep_entry_end"]:
            print(f"  Sweep entry_end:   {leg['sweep_entry_end'][0]} → {leg['sweep_entry_end'][-1]} ({len(leg['sweep_entry_end'])} values)")

        rows = []
        for i, (label, cfg) in enumerate(configs):
            trades = run_backtest(df_5m, cfg, start_date=START_DATE, end_date=END_DATE, df_1m=df_1m)
            m = compute_metrics(trades)
            acct = simulate_staggered_accounts(trades, START_DATE, END_DATE)

            sess = cfg.sessions[0]
            rows.append({
                "label": label,
                "entry_start": sess.entry_start,
                "entry_end": sess.entry_end,
                "trades": m["total_trades"],
                "win_rate": m["win_rate"],
                "net_r": m["total_r"],
                "avg_r": m["avg_r"],
                "max_dd_r": m["max_drawdown_r"],
                "calmar": m["calmar_ratio"],
                "sharpe": m["sharpe_ratio"],
                "pf": m["profit_factor"],
                "r_per_year": m["total_r"] / 2.0,  # 2-year window
                "success_rate": acct["success_rate"],
                "ev_per_account": acct["ev_per_account"],
                "payouts": acct["payouts"],
                "breaches": acct["breaches"],
                "open": acct["open"],
                "total_accounts": acct["total_accounts"],
                "avg_days_to_payout": acct["avg_days_to_payout"],
                "median_days_to_payout": acct["median_days_to_payout"],
            })

            if (i + 1) % 25 == 0 or (i + 1) == len(configs):
                elapsed = time.time() - t0
                print(f"  [{i+1}/{len(configs)}] {elapsed:.0f}s elapsed")

        # Sort by composite score: success_rate * 0.4 + calmar_norm * 0.3 + net_r_norm * 0.3
        # But first just sort by calmar for display
        rows_by_calmar = sorted(rows, key=lambda r: r["calmar"], reverse=True)
        rows_by_propfirm = sorted(
            rows,
            key=lambda r: (
                r["success_rate"] or 0,
                r["ev_per_account"],
                r["calmar"],
            ),
            reverse=True,
        )

        all_results[leg_name] = {
            "all_rows": rows,
            "by_calmar": rows_by_calmar,
            "by_propfirm": rows_by_propfirm,
        }

        # ── Print top results ─────────────────────────────────────────────

        print(f"\n  TOP 15 BY CALMAR — {leg_name}")
        print(f"  {'#':>3} {'Entry Window':<22} {'Tr':>4} {'WR%':>6} {'NetR':>6} {'R/yr':>5} {'MaxDD':>6} {'Calm':>6} {'Shrp':>5} "
              f"{'Acct':>4} {'Pay':>3} {'Br':>3} {'SuccR%':>7} {'AvgDPay':>7} {'EV/a':>6}")
        print(f"  {'-'*110}")

        for i, r in enumerate(rows_by_calmar[:15]):
            sr = f"{r['success_rate']:.0%}" if r["success_rate"] is not None else "N/A"
            adp = f"{r['avg_days_to_payout']:.0f}" if r["avg_days_to_payout"] is not None else "-"
            window = f"{r['entry_start']}-{r['entry_end']}"
            # Mark anchor with *
            anchor_window = f"{anchor_sess.entry_start}-{anchor_sess.entry_end}"
            marker = " *" if window == anchor_window else ""
            print(
                f"  {i+1:>3} {window:<20}{marker:>2} {r['trades']:>4} {r['win_rate']:>5.1%} {r['net_r']:>6.1f} "
                f"{r['r_per_year']:>5.1f} {r['max_dd_r']:>6.2f} {r['calmar']:>6.2f} {r['sharpe']:>5.2f} "
                f"{r['total_accounts']:>4} {r['payouts']:>3} {r['breaches']:>3} "
                f"{sr:>7} {adp:>7} {r['ev_per_account']:>6.3f}"
            )

        print(f"\n  TOP 15 BY PROP FIRM — {leg_name}")
        print(f"  {'#':>3} {'Entry Window':<22} {'Tr':>4} {'WR%':>6} {'NetR':>6} {'Calm':>6} "
              f"{'Acct':>4} {'Pay':>3} {'Br':>3} {'Opn':>3} {'SuccR%':>7} {'AvgDPay':>7} {'MedDPay':>7} {'EV/a':>6}")
        print(f"  {'-'*110}")

        for i, r in enumerate(rows_by_propfirm[:15]):
            sr = f"{r['success_rate']:.0%}" if r["success_rate"] is not None else "N/A"
            adp = f"{r['avg_days_to_payout']:.0f}" if r["avg_days_to_payout"] is not None else "-"
            mdp = f"{r['median_days_to_payout']:.0f}" if r["median_days_to_payout"] is not None else "-"
            window = f"{r['entry_start']}-{r['entry_end']}"
            marker = " *" if window == anchor_window else ""
            print(
                f"  {i+1:>3} {window:<20}{marker:>2} {r['trades']:>4} {r['win_rate']:>5.1%} {r['net_r']:>6.1f} "
                f"{r['calmar']:>6.2f} "
                f"{r['total_accounts']:>4} {r['payouts']:>3} {r['breaches']:>3} {r['open']:>3} "
                f"{sr:>7} {adp:>7} {mdp:>7} {r['ev_per_account']:>6.3f}"
            )

    # ── Summary across all legs ───────────────────────────────────────────

    print(f"\n\n{'='*120}")
    print("RECOMMENDED ENTRY WINDOWS — Best balanced (Calmar + Prop Firm)")
    print(f"{'='*120}")

    for leg_name, res in all_results.items():
        rows = res["all_rows"]
        # Composite rank: normalize calmar and success_rate, combine
        if not rows:
            continue
        max_calmar = max(r["calmar"] for r in rows) or 1
        max_net_r = max(r["net_r"] for r in rows) or 1

        for r in rows:
            sr = r["success_rate"] or 0
            calmar_norm = r["calmar"] / max_calmar if max_calmar > 0 else 0
            net_r_norm = r["net_r"] / max_net_r if max_net_r > 0 else 0
            r["composite"] = sr * 0.4 + calmar_norm * 0.3 + net_r_norm * 0.3

        best = max(rows, key=lambda r: r["composite"])
        anchor_sess = LEGS[leg_name]["config"].sessions[0]
        current = f"{anchor_sess.entry_start}-{anchor_sess.entry_end}"
        recommended = f"{best['entry_start']}-{best['entry_end']}"
        changed = " (CHANGED)" if current != recommended else " (same)"

        sr = f"{best['success_rate']:.0%}" if best["success_rate"] is not None else "N/A"
        print(f"\n  {leg_name}:")
        print(f"    Current:     {current}")
        print(f"    Recommended: {recommended}{changed}")
        print(f"    Trades={best['trades']}  WR={best['win_rate']:.1%}  Net R={best['net_r']:.1f}  "
              f"Calmar={best['calmar']:.2f}  Sharpe={best['sharpe']:.2f}  "
              f"SuccRate={sr}  EV={best['ev_per_account']:.3f}R")

    # ── Save results ──────────────────────────────────────────────────────

    output_path = Path(__file__).parent.parent / "data" / "results" / "fast_v2_entry_window_sweep.json"
    save_data = {
        "sweep_info": {
            "description": "FAST_V2 Entry Window Optimization — Phase 1",
            "start_date": START_DATE,
            "end_date": END_DATE,
            "payout_target": PAYOUT_TARGET,
            "breach_limit": BREACH_LIMIT,
            "stagger_days": CYCLE_DAYS,
            "sweep_time_s": round(time.time() - t0, 1),
        },
    }

    def convert(obj):
        if isinstance(obj, tuple):
            return list(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    for leg_name, res in all_results.items():
        save_data[leg_name] = {
            "top20_by_calmar": res["by_calmar"][:20],
            "top20_by_propfirm": res["by_propfirm"][:20],
        }

    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2, default=convert)

    print(f"\n\nResults saved to {output_path}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
