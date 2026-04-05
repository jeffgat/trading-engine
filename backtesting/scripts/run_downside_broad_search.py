#!/usr/bin/env python3
"""Broad downside search: test all short/both-direction candidates from
TOP_CANDIDATES_PER_ASSET_REPORT as additive legs to the ALPHA_V1 long portfolio.

Candidates tested:
  - NQ NY Short RR2.5 ATR10 (gated + ungated) — from alpha_v1_downside research
  - GC Asia-1 (both) — STRONG, commodity diversifier
  - GC Asia-2 (short) — STRONG, pure short gold
  - GC Asia-3 (short) — short gold variant
  - RTY NY-1 (both) — CONDITIONAL, highest DSR
  - RTY NY-2 (both) — CONDITIONAL, best holdout PR
  - RTY NY-4 (both) — STRONG
  - SI Asia-1 (short) — CONDITIONAL, highest DSR
  - SI Asia-3 (short) — CONDITIONAL, best holdout
  - SI Asia-4 (short) — CONDITIONAL, balanced

For each candidate:
  1. Standalone metrics (full history + holdout)
  2. Portfolio additivity: combined with ALPHA_V1 baseline
  3. Overlap analysis: Jaccard + daily R correlation with baseline
  4. Prop sim: standalone + combined staggered accounts
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES, GC, RTY, SI
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Parameters ────────────────────────────────────────────────────────────

FULL_START = "2016-01-01"
FULL_END = "2026-04-04"
HOLDOUT_START = "2025-01-01"
PROP_START = "2016-01-01"
PROP_END = "2026-04-04"
CYCLE_DAYS = 14

# Standalone prop thresholds
PAYOUT_R = 5.0
BREACH_R = -4.0

# ── ALPHA_V1 Baseline Configs ─────────────────────────────────────────────

ALPHA_V1_LEGS = {
    "NQ_NY_LSI": StrategyConfig(
        sessions=(SessionConfig(
            name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
            flat_start="15:50", flat_end="16:00", stop_atr_pct=0.0, min_gap_atr_pct=5.0),),
        instrument=NQ, strategy="lsi", direction_filter="long", use_bar_magnifier=True,
        rr=3.0, tp1_ratio=0.34, atr_length=10, risk_usd=5000.0,
        lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
        lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
        lsi_first_fvg_only=False, lsi_clean_path=False, lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
        excluded_days=(2, 3), name="NQ NY LSI"),
    "NQ_Asia_ORB": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:15", entry_start="20:15", entry_end="22:30",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=100.0, min_gap_orb_pct=10.0),),
        instrument=NQ, strategy="continuation", direction_filter="long", use_bar_magnifier=True,
        rr=6.0, tp1_ratio=0.3, atr_length=5, risk_usd=5000.0,
        excluded_days=(1,), name="NQ Asia ORB"),
    "ES_Asia_Cont": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:15", entry_start="20:15", entry_end="03:00",
            flat_start="07:00", flat_end="07:30", stop_orb_pct=125.0, min_gap_atr_pct=0.5,
            min_stop_points=3.0, min_tp1_points=3.0),),
        instrument=ES, strategy="continuation", direction_filter="long", use_bar_magnifier=True,
        rr=1.5, tp1_ratio=0.7, atr_length=14, risk_usd=5000.0, name="ES Asia Cont"),
    "ES_NY_Cont": StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="09:45", entry_start="09:45", entry_end="13:00",
            flat_start="15:50", flat_end="16:00", stop_atr_pct=5.0, min_gap_atr_pct=0.25,
            min_stop_points=3.0, min_tp1_points=3.0),),
        instrument=ES, strategy="continuation", direction_filter="long", use_bar_magnifier=True,
        rr=5.0, tp1_ratio=0.2, atr_length=7, risk_usd=5000.0,
        excluded_days=(3,), name="ES NY Cont"),
}

# ── Downside Candidate Configs ────────────────────────────────────────────

DOWNSIDE_CANDIDATES = {
    # NQ NY Short (from alpha_v1_downside research winner)
    "NQ_NY_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="09:55", entry_start="09:55", entry_end="11:30",
            flat_start="11:30", flat_end="16:00", stop_orb_pct=15.0, min_gap_orb_pct=2.5,
            min_stop_points=10.0, min_tp1_points=10.0),),
        instrument=NQ, strategy="continuation", direction_filter="short", use_bar_magnifier=True,
        rr=2.5, tp1_ratio=0.4, atr_length=10, risk_usd=5000.0, name="NQ NY Short RR2.5 ATR10"),

    # GC Asia-1: both directions, STRONG
    "GC_Asia1_Both": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=25.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="both", rr=2.5, tp1_ratio=0.6, atr_length=14,
        name="GC Asia-1 Both"),

    # GC Asia-2: short only, STRONG
    "GC_Asia2_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:15", entry_start="20:15", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.0, tp1_ratio=0.6, atr_length=14,
        name="GC Asia-2 Short"),

    # GC Asia-3: short only
    "GC_Asia3_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.0, tp1_ratio=0.5, atr_length=14,
        name="GC Asia-3 Short"),

    # RTY NY-1: both, highest DSR
    "RTY_NY1_Both": StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="09:40", entry_start="09:40", entry_end="13:00",
            flat_start="15:50", flat_end="16:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=RTY, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="both", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="RTY NY-1 Both"),

    # RTY NY-2: both, best holdout PR
    "RTY_NY2_Both": StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="09:40", entry_start="09:40", entry_end="13:00",
            flat_start="15:50", flat_end="16:00", stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=RTY, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="both", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="RTY NY-2 Both"),

    # RTY NY-4: both, STRONG
    "RTY_NY4_Both": StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="09:40", entry_start="09:40", entry_end="13:00",
            flat_start="15:50", flat_end="16:00", stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=RTY, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="both", rr=3.0, tp1_ratio=0.4, atr_length=14,
        name="RTY NY-4 Both"),

    # SI Asia-1: short, highest DSR
    "SI_Asia1_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=SI, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.5, tp1_ratio=0.6, atr_length=14,
        name="SI Asia-1 Short"),

    # SI Asia-3: short, best holdout
    "SI_Asia3_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=SI, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="SI Asia-3 Short"),

    # SI Asia-4: short, balanced
    "SI_Asia4_Short": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30", entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00", stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=SI, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=3.0, tp1_ratio=0.5, atr_length=14,
        name="SI Asia-4 Short"),
}


# ── Staggered account simulation ─────────────────────────────────────────

def simulate_staggered_accounts(trade_data, start_date, end_date, payout_r, breach_r, stagger_days=14):
    if not trade_data:
        return {"payouts": 0, "breaches": 0, "open": 0, "success_rate": None,
                "ev_per_account": 0.0, "max_consec_breach": 0, "avg_days_to_payout": None}

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
        outcome_date = acct_start
        for t in trade_data:
            if t["date"] < acct_start:
                continue
            cum_r += t["r"]
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
            if future:
                outcome_date = future[-1]["date"]
        results.append({"outcome": outcome, "final_r": cum_r,
                        "calendar_days": (outcome_date - acct_start).days + 1})

    payouts = [r for r in results if r["outcome"] == "payout"]
    breaches = [r for r in results if r["outcome"] == "breach"]
    opens = [r for r in results if r["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    sr = len(payouts) / resolved if resolved else None

    capped = [payout_r if r["outcome"] == "payout" else breach_r if r["outcome"] == "breach" else r["final_r"]
              for r in results]
    ev = float(np.mean(capped)) if capped else 0.0

    mcb = cur = 0
    for r in results:
        if r["outcome"] == "breach":
            cur += 1
            mcb = max(mcb, cur)
        else:
            cur = 0

    return {
        "total": len(results),
        "payouts": len(payouts), "breaches": len(breaches), "open": len(opens),
        "success_rate": round(sr, 4) if sr else None,
        "ev_per_account": round(ev, 4),
        "max_consec_breach": mcb,
        "avg_days_to_payout": round(float(np.mean([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["calendar_days"] for r in payouts])), 1) if payouts else None,
    }


def compute_overlap(dates_a: set, dates_b: set, daily_r_a: dict, daily_r_b: dict) -> dict:
    """Compute Jaccard overlap and daily R correlation between two trade streams."""
    intersection = dates_a & dates_b
    union = dates_a | dates_b
    jaccard = len(intersection) / len(union) if union else 0.0

    # Daily R correlation on shared dates
    common = sorted(intersection)
    if len(common) >= 10:
        ra = np.array([daily_r_a.get(d, 0.0) for d in common])
        rb = np.array([daily_r_b.get(d, 0.0) for d in common])
        corr = float(np.corrcoef(ra, rb)[0, 1]) if np.std(ra) > 0 and np.std(rb) > 0 else 0.0
    else:
        corr = None

    return {"jaccard": round(jaccard, 4), "daily_r_corr": round(corr, 4) if corr is not None else None,
            "shared_dates": len(intersection), "union_dates": len(union)}


def main():
    t0 = time.time()

    print("=" * 110)
    print("BROAD DOWNSIDE SEARCH — Cross-Asset Additivity to ALPHA_V1")
    print("=" * 110)
    print(f"Full history: {FULL_START} to {FULL_END}  |  Holdout: {HOLDOUT_START}+")
    print(f"Candidates: {len(DOWNSIDE_CANDIDATES)}  |  Baseline legs: {len(ALPHA_V1_LEGS)}")
    print()

    # ── Load all data ─────────────────────────────────────────────────────

    print("Loading data...")
    data_map = {}
    for symbol in ["NQ", "ES", "GC", "RTY", "SI"]:
        df_5m = load_5m_data(f"{symbol}_5m.parquet")
        df_1m = load_1m_for_5m(f"{symbol}_5m.parquet")
        data_map[symbol] = (df_5m, df_1m)
        print(f"  {symbol}: {len(df_5m):,} 5m  |  {len(df_1m):,} 1m")

    # ── Run ALPHA_V1 baseline ─────────────────────────────────────────────

    print(f"\n{'=' * 110}")
    print("ALPHA_V1 BASELINE")
    print(f"{'=' * 110}")

    baseline_trade_data = []  # merged {"date", "r", "leg"}
    baseline_dates = set()
    baseline_daily_r = {}  # date -> sum of R on that date

    for leg_name, cfg in ALPHA_V1_LEGS.items():
        symbol = cfg.instrument.symbol
        df_5m, df_1m = data_map[symbol]
        trades = run_backtest(df_5m, cfg, start_date=FULL_START, end_date=FULL_END, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        m = compute_metrics(trades)
        print(f"  {leg_name}: {m['total_trades']} trades  |  WR: {m['win_rate']:.1%}  |  Net R: {m['total_r']:+.1f}  |  DD: {m['max_drawdown_r']:.1f}R")

        for t in filled:
            d = datetime.date.fromisoformat(t.date)
            baseline_trade_data.append({"date": d, "r": t.r_multiple, "leg": leg_name})
            baseline_dates.add(d)
            baseline_daily_r[d] = baseline_daily_r.get(d, 0.0) + t.r_multiple

    baseline_trade_data.sort(key=lambda x: x["date"])
    baseline_net_r = sum(t["r"] for t in baseline_trade_data)

    # Baseline worst rolling windows
    baseline_daily = sorted(baseline_daily_r.items())
    baseline_cum = np.cumsum([r for _, r in baseline_daily])
    peak = np.maximum.accumulate(baseline_cum)
    baseline_max_dd = float((baseline_cum - peak).min())

    print(f"\n  Combined: {len(baseline_trade_data)} trades  |  Net R: {baseline_net_r:+.1f}  |  Max DD: {baseline_max_dd:.1f}R")

    # ── Run all downside candidates ───────────────────────────────────────

    print(f"\n{'=' * 110}")
    print("DOWNSIDE CANDIDATES — Standalone + Additivity")
    print(f"{'=' * 110}")

    results = []

    for cand_name, cfg in DOWNSIDE_CANDIDATES.items():
        symbol = cfg.instrument.symbol
        df_5m, df_1m = data_map[symbol]

        trades = run_backtest(df_5m, cfg, start_date=FULL_START, end_date=FULL_END, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        m_full = compute_metrics(trades)

        holdout_trades = [t for t in trades if t.date >= HOLDOUT_START]
        m_ho = compute_metrics(holdout_trades) if holdout_trades else None

        # Build candidate trade data
        cand_trade_data = sorted(
            [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in filled],
            key=lambda x: x["date"],
        )
        cand_dates = {datetime.date.fromisoformat(t.date) for t in filled}
        cand_daily_r = {}
        for t in filled:
            d = datetime.date.fromisoformat(t.date)
            cand_daily_r[d] = cand_daily_r.get(d, 0.0) + t.r_multiple

        # Overlap with baseline
        overlap = compute_overlap(baseline_dates, cand_dates, baseline_daily_r, cand_daily_r)

        # Combined portfolio metrics
        combined = sorted(baseline_trade_data + [{"date": t["date"], "r": t["r"], "leg": cand_name} for t in cand_trade_data],
                          key=lambda x: x["date"])
        combined_daily_r = {}
        for t in combined:
            combined_daily_r[t["date"]] = combined_daily_r.get(t["date"], 0.0) + t["r"]
        combined_daily = sorted(combined_daily_r.items())
        combined_cum = np.cumsum([r for _, r in combined_daily])
        combined_net_r = float(combined_cum[-1]) if len(combined_cum) else 0.0
        combined_peak = np.maximum.accumulate(combined_cum)
        combined_max_dd = float((combined_cum - combined_peak).min()) if len(combined_cum) else 0.0

        # Combined holdout
        combined_ho_daily = {d: r for d, r in combined_daily_r.items() if d >= datetime.date.fromisoformat(HOLDOUT_START)}
        combined_ho_sorted = sorted(combined_ho_daily.items())
        if combined_ho_sorted:
            combined_ho_cum = np.cumsum([r for _, r in combined_ho_sorted])
            combined_ho_net = float(combined_ho_cum[-1])
            combined_ho_peak = np.maximum.accumulate(combined_ho_cum)
            combined_ho_dd = float((combined_ho_cum - combined_ho_peak).min())
        else:
            combined_ho_net = 0.0
            combined_ho_dd = 0.0

        # Worst rolling 3-month window (combined)
        combined_dates_arr = [d for d, _ in combined_daily]
        combined_r_arr = np.array([r for _, r in combined_daily])
        worst_3m = 0.0
        if len(combined_dates_arr) > 60:
            for i in range(len(combined_dates_arr)):
                window_end = combined_dates_arr[i] + datetime.timedelta(days=90)
                j = i
                while j < len(combined_dates_arr) and combined_dates_arr[j] <= window_end:
                    j += 1
                window_r = float(combined_r_arr[i:j].sum())
                worst_3m = min(worst_3m, window_r)

        # Baseline worst 3m for comparison
        baseline_dates_arr = [d for d, _ in baseline_daily]
        baseline_r_arr = np.array([r for _, r in baseline_daily])
        baseline_worst_3m = 0.0
        if len(baseline_dates_arr) > 60:
            for i in range(len(baseline_dates_arr)):
                window_end = baseline_dates_arr[i] + datetime.timedelta(days=90)
                j = i
                while j < len(baseline_dates_arr) and baseline_dates_arr[j] <= window_end:
                    j += 1
                window_r = float(baseline_r_arr[i:j].sum())
                baseline_worst_3m = min(baseline_worst_3m, window_r)

        # Standalone prop sim
        standalone_acct = simulate_staggered_accounts(cand_trade_data, PROP_START, PROP_END, PAYOUT_R, BREACH_R, CYCLE_DAYS)

        # R by year
        r_by_year = m_full.get("r_by_year", {})
        neg_years = sum(1 for r in r_by_year.values() if r < 0)

        res = {
            "name": cand_name,
            "symbol": symbol,
            "direction": cfg.direction_filter,
            "trades": m_full["total_trades"],
            "wr": m_full["win_rate"],
            "net_r": m_full["total_r"],
            "max_dd": m_full["max_drawdown_r"],
            "calmar": m_full["calmar_ratio"],
            "sharpe": m_full["sharpe_ratio"],
            "neg_years": neg_years,
            "ho_trades": m_ho["total_trades"] if m_ho else 0,
            "ho_net_r": m_ho["total_r"] if m_ho else 0.0,
            "ho_sharpe": m_ho["sharpe_ratio"] if m_ho else 0.0,
            "jaccard": overlap["jaccard"],
            "daily_r_corr": overlap["daily_r_corr"],
            "combined_net_r": combined_net_r,
            "combined_max_dd": combined_max_dd,
            "combined_ho_net": combined_ho_net,
            "combined_ho_dd": combined_ho_dd,
            "combined_worst_3m": worst_3m,
            "baseline_worst_3m": baseline_worst_3m,
            "worst_3m_delta_pct": round((worst_3m - baseline_worst_3m) / abs(baseline_worst_3m) * 100, 1) if baseline_worst_3m != 0 else 0.0,
            "standalone_pay": standalone_acct["success_rate"],
            "standalone_ev": standalone_acct["ev_per_account"],
            "standalone_mcb": standalone_acct["max_consec_breach"],
            "standalone_avg_days": standalone_acct["avg_days_to_payout"],
            "r_by_year": r_by_year,
        }
        results.append(res)

        print(f"\n  {cand_name} ({symbol}, {cfg.direction_filter})")
        print(f"    Standalone:  {m_full['total_trades']} trades  |  WR: {m_full['win_rate']:.1%}  |  Net R: {m_full['total_r']:+.1f}  |  DD: {m_full['max_drawdown_r']:.1f}R  |  Calmar: {m_full['calmar_ratio']:.2f}")
        if m_ho and m_ho["total_trades"] > 0:
            print(f"    Holdout:     {m_ho['total_trades']} trades  |  WR: {m_ho['win_rate']:.1%}  |  Net R: {m_ho['total_r']:+.1f}  |  Sharpe: {m_ho['sharpe_ratio']:.2f}")
        print(f"    Overlap:     Jaccard {overlap['jaccard']:.3f}  |  Daily R corr: {overlap['daily_r_corr']}")
        print(f"    Combined:    Net R: {combined_net_r:+.1f}  |  DD: {combined_max_dd:.1f}R  |  HO Net: {combined_ho_net:+.1f}  |  Worst 3m: {worst_3m:.1f}R (baseline: {baseline_worst_3m:.1f}R)")
        sr = f"{standalone_acct['success_rate']:.1%}" if standalone_acct['success_rate'] else "N/A"
        print(f"    Prop sim:    Pay: {sr}  |  EV: {standalone_acct['ev_per_account']:+.3f}  |  MCB: {standalone_acct['max_consec_breach']}")

    # ── Comparison Tables ─────────────────────────────────────────────────

    print(f"\n\n{'=' * 110}")
    print("STANDALONE COMPARISON (sorted by Calmar)")
    print(f"{'=' * 110}")
    results.sort(key=lambda r: -(r["calmar"] or 0))
    print(f"\n  {'Candidate':<20} {'Sym':>3} {'Dir':>5} {'Trds':>5} {'WR':>5} {'NetR':>7} {'DD':>7} {'Calm':>6} {'Shrp':>5} {'Neg':>3} {'HO-R':>6} {'Pay%':>6} {'EV':>7} {'MCB':>4}")
    print(f"  {'-'*110}")
    for r in results:
        sr = f"{r['standalone_pay']:.1%}" if r['standalone_pay'] else "N/A"
        print(f"  {r['name']:<20} {r['symbol']:>3} {r['direction']:>5} {r['trades']:>5} {r['wr']:>4.1%} {r['net_r']:>+7.1f} {r['max_dd']:>7.1f} {r['calmar']:>6.2f} {r['sharpe']:>5.2f} {r['neg_years']:>3} {r['ho_net_r']:>+6.1f} {sr:>6} {r['standalone_ev']:>+7.3f} {r['standalone_mcb']:>4}")

    print(f"\n\n{'=' * 110}")
    print("ADDITIVITY COMPARISON (sorted by combined worst 3m improvement)")
    print(f"{'=' * 110}")
    results.sort(key=lambda r: -r["worst_3m_delta_pct"])
    print(f"\n  Baseline worst 3m: {results[0]['baseline_worst_3m']:.1f}R  |  Baseline max DD: {baseline_max_dd:.1f}R  |  Baseline net R: {baseline_net_r:+.1f}")
    print(f"\n  {'Candidate':<20} {'Jcrd':>5} {'Corr':>5} {'Comb R':>7} {'Comb DD':>8} {'HO R':>6} {'W3m':>7} {'W3m Δ%':>7} {'Dir':>5} {'Sym':>3}")
    print(f"  {'-'*85}")
    for r in results:
        corr = f"{r['daily_r_corr']:.2f}" if r['daily_r_corr'] is not None else "—"
        print(f"  {r['name']:<20} {r['jaccard']:>5.3f} {corr:>5} {r['combined_net_r']:>+7.1f} {r['combined_max_dd']:>8.1f} {r['combined_ho_net']:>+6.1f} {r['combined_worst_3m']:>7.1f} {r['worst_3m_delta_pct']:>+6.1f}% {r['direction']:>5} {r['symbol']:>3}")

    print(f"\n\n{'=' * 110}")
    print("OVERLAP ANALYSIS (lower = more diversifying)")
    print(f"{'=' * 110}")
    results.sort(key=lambda r: r["jaccard"])
    print(f"\n  {'Candidate':<20} {'Jaccard':>7} {'Daily R Corr':>12} {'Shared Days':>11} {'Symbol':>6}")
    print(f"  {'-'*60}")
    for r in results:
        corr = f"{r['daily_r_corr']:.3f}" if r['daily_r_corr'] is not None else "—"
        print(f"  {r['name']:<20} {r['jaccard']:>7.4f} {corr:>12} {'':>11} {r['symbol']:>6}")

    # ── Year-by-year for top 5 by combined worst 3m ───────────────────────

    print(f"\n\n{'=' * 110}")
    print("YEAR-BY-YEAR (top 5 by combined worst-3m improvement)")
    print(f"{'=' * 110}")
    results.sort(key=lambda r: -r["worst_3m_delta_pct"])
    for r in results[:5]:
        years = sorted(r["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{v:+.1f}" for yr, v in years)
        print(f"\n  {r['name']} ({r['symbol']}, {r['direction']})")
        print(f"  Net R: {r['net_r']:+.1f}  |  DD: {r['max_dd']:.1f}R  |  Calmar: {r['calmar']:.2f}  |  W3m Δ: {r['worst_3m_delta_pct']:+.1f}%")
        print(f"  {yr_str}")

    print(f"\n\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
