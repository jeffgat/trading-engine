#!/usr/bin/env python3
"""NQ NY LSI RR2/TP0.5 — DOW filter analysis.

Tests the strategy with every DOW exclusion combination to determine
which days are genuinely negative EV vs which are just noise.

Runs on full pre-holdout (2016 to 2025-03-31) with 1s magnifier + regime gate.
All results go through results_to_dict's _apply_replay_filters to match
what the frontend/DB would show.

For each variant: full metrics + per-day breakdown of avg R, trade count, WR.
"""

import sys
import time
from datetime import datetime
from pathlib import Path
from itertools import combinations

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

WF_START = "2016-01-01"
PRE_HOLDOUT_END = "2025-03-31"
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

# Base config WITHOUT excluded_days — we'll filter post-hoc for analysis
CONFIG = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=14,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    excluded_days=(),  # NO DOW exclusion — run all days
    name="DOW analysis",
)


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def per_day_stats(filled_trades):
    """Break down trades by day of week."""
    by_dow = {i: [] for i in range(5)}
    for t in filled_trades:
        dow = datetime.strptime(t.date, "%Y-%m-%d").weekday()
        by_dow[dow].append(t.r_multiple)

    stats = {}
    for dow in range(5):
        rs = by_dow[dow]
        if rs:
            stats[dow] = {
                "trades": len(rs),
                "avg_r": np.mean(rs),
                "total_r": sum(rs),
                "wr": sum(1 for r in rs if r > 0) / len(rs),
                "median_r": np.median(rs),
            }
        else:
            stats[dow] = {"trades": 0, "avg_r": 0, "total_r": 0, "wr": 0, "median_r": 0}
    return stats


def main():
    t0 = time.time()

    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)

    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    df_pre = df_5m.loc[:PRE_HOLDOUT_END]
    df_pre_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_pre_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    # Run ONE backtest with no DOW exclusion (all 5 days)
    print("Running backtest (all days, no DOW filter)...", flush=True)
    trades_raw = run_backtest(df_pre, CONFIG, start_date=WF_START,
                              df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
    trades_gated = gate_fn(trades_raw)
    filled_all = _filled_trades(trades_gated)
    print(f"  Total gated filled trades: {len(filled_all)}", flush=True)

    # ── Part 1: Per-day breakdown ─────────────────────────────────────
    print(f"\n{'='*90}", flush=True)
    print("PART 1: PER-DAY BREAKDOWN (regime-gated, all days included)", flush=True)
    print(f"{'='*90}\n", flush=True)

    day_stats = per_day_stats(filled_all)
    print(f"  {'Day':<6} {'Trades':>7} {'Total R':>9} {'Avg R':>8} {'Median R':>9} {'WR%':>7}", flush=True)
    print(f"  {'-'*50}", flush=True)
    for dow in range(5):
        s = day_stats[dow]
        flag = " ◄ NEGATIVE" if s["total_r"] < 0 else ""
        print(f"  {DOW_NAMES[dow]:<6} {s['trades']:>7} {s['total_r']:>+9.1f} {s['avg_r']:>+8.3f} "
              f"{s['median_r']:>+9.3f} {s['wr']:>6.1%}{flag}", flush=True)

    total_r_all = sum(s["total_r"] for s in day_stats.values())
    print(f"  {'TOTAL':<6} {len(filled_all):>7} {total_r_all:>+9.1f}", flush=True)

    # ── Per-day per-year breakdown ────────────────────────────────────
    print(f"\n{'='*90}", flush=True)
    print("PART 1b: PER-DAY PER-YEAR R (is the day consistently bad or just one bad year?)", flush=True)
    print(f"{'='*90}\n", flush=True)

    years = sorted(set(t.date[:4] for t in filled_all))
    header = f"  {'Day':<6}" + "".join(f"{y:>8}" for y in years) + f"{'TOTAL':>9}"
    print(header, flush=True)
    print(f"  {'-'*(6 + 8*len(years) + 9)}", flush=True)

    for dow in range(5):
        row = f"  {DOW_NAMES[dow]:<6}"
        total = 0
        neg_years = 0
        for y in years:
            yr_trades = [t.r_multiple for t in filled_all
                         if datetime.strptime(t.date, "%Y-%m-%d").weekday() == dow and t.date[:4] == y]
            yr_r = sum(yr_trades)
            total += yr_r
            if yr_r < 0:
                neg_years += 1
            row += f"{yr_r:>+8.1f}"
        row += f"{total:>+9.1f}"
        row += f"  ({neg_years} neg yr)"
        print(row, flush=True)

    # ── Part 2: DOW exclusion variants ────────────────────────────────
    print(f"\n{'='*90}", flush=True)
    print("PART 2: DOW EXCLUSION VARIANTS", flush=True)
    print(f"{'='*90}\n", flush=True)

    # Test: no exclusion, each single day excluded, common combos
    variants = [
        ("ALL days", set()),
        ("No Mon", {0}),
        ("No Tue", {1}),
        ("No Wed", {2}),
        ("No Thu", {3}),
        ("No Fri", {4}),
        ("No Wed+Thu (MTF)", {2, 3}),
        ("No Mon+Wed+Thu", {0, 2, 3}),
        ("No Tue+Wed+Thu", {1, 2, 3}),
        ("No Wed+Thu+Fri", {2, 3, 4}),
        ("No Mon+Wed", {0, 2}),
        ("No Thu+Fri", {3, 4}),
    ]

    results = []
    for name, excl in variants:
        filtered = apply_dow_filter(trades_gated, excl)
        m = compute_metrics(filtered)
        filled = _filled_trades(filtered)
        rby = m.get("r_by_year", {})
        neg_yr = sum(1 for v in rby.values() if v < 0)
        results.append({
            "name": name,
            "excl": excl,
            "trades": len(filled),
            "wr": m["win_rate"],
            "pf": m["profit_factor"],
            "net_r": m["total_r"],
            "dd": m["max_drawdown_r"],
            "calmar": m["calmar_ratio"],
            "sharpe": m["sharpe_ratio"],
            "avg_r": m["avg_r"],
            "neg_yr": neg_yr,
            "rby": rby,
        })

    # Sort by Calmar
    results.sort(key=lambda r: r["calmar"], reverse=True)

    print(f"  {'Variant':<22} {'Tr':>4} {'WR%':>6} {'PF':>5} {'NetR':>7} {'DD':>7} {'Calm':>7} "
          f"{'Shrp':>6} {'AvgR':>7} {'NegYr':>5}", flush=True)
    print(f"  {'-'*90}", flush=True)

    for r in results:
        print(f"  {r['name']:<22} {r['trades']:>4} {r['wr']:>5.1%} {r['pf']:>5.2f} "
              f"{r['net_r']:>+7.1f} {r['dd']:>7.1f} {r['calmar']:>7.2f} "
              f"{r['sharpe']:>6.2f} {r['avg_r']:>+7.3f} {r['neg_yr']:>5}", flush=True)

    # ── Part 3: Statistical significance per day ──────────────────────
    print(f"\n{'='*90}", flush=True)
    print("PART 3: STATISTICAL SIGNIFICANCE (t-test: is day's avg R significantly != 0?)", flush=True)
    print(f"{'='*90}\n", flush=True)

    from scipy import stats as scipy_stats

    print(f"  {'Day':<6} {'N':>5} {'Avg R':>8} {'Std R':>8} {'t-stat':>8} {'p-value':>9} {'Significant?':<15}", flush=True)
    print(f"  {'-'*65}", flush=True)

    for dow in range(5):
        rs = [t.r_multiple for t in filled_all if datetime.strptime(t.date, "%Y-%m-%d").weekday() == dow]
        if len(rs) >= 3:
            t_stat, p_val = scipy_stats.ttest_1samp(rs, 0)
            sig = "YES (p<0.05)" if p_val < 0.05 else "NO"
            print(f"  {DOW_NAMES[dow]:<6} {len(rs):>5} {np.mean(rs):>+8.3f} {np.std(rs):>8.3f} "
                  f"{t_stat:>8.3f} {p_val:>9.4f} {sig:<15}", flush=True)
        else:
            print(f"  {DOW_NAMES[dow]:<6} {len(rs):>5} insufficient data", flush=True)

    # ── Part 4: Bootstrap confidence intervals per day ─────────────────
    print(f"\n{'='*90}", flush=True)
    print("PART 4: BOOTSTRAP 95% CI FOR DAILY AVG R (10,000 resamples)", flush=True)
    print(f"{'='*90}\n", flush=True)

    rng = np.random.default_rng(42)
    n_boot = 10000

    print(f"  {'Day':<6} {'N':>5} {'Avg R':>8} {'CI Low':>8} {'CI High':>9} {'Contains 0?':<15}", flush=True)
    print(f"  {'-'*55}", flush=True)

    for dow in range(5):
        rs = np.array([t.r_multiple for t in filled_all if datetime.strptime(t.date, "%Y-%m-%d").weekday() == dow])
        if len(rs) >= 5:
            boot_means = np.array([np.mean(rng.choice(rs, size=len(rs), replace=True)) for _ in range(n_boot)])
            ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
            contains_zero = "YES (not sig)" if ci_low <= 0 <= ci_high else "NO (significant)"
            print(f"  {DOW_NAMES[dow]:<6} {len(rs):>5} {np.mean(rs):>+8.3f} {ci_low:>+8.3f} {ci_high:>+9.3f} {contains_zero:<15}", flush=True)

    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
