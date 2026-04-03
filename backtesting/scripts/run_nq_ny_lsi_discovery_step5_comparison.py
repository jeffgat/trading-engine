#!/usr/bin/env python3
"""NQ NY LSI Discovery — Step 5: Head-to-head comparison.

Compares 3 candidates × 2 gate variants (ungated + medium-vol avoidance) = 6 configs.

Candidates:
  OLD: NY LSI fvg_limit v2 (RR=3.0, TP1=0.3, ATR=10) — existing best, Calmar 20.37
  NEW-A: fvg_limit (RR=2.0, TP1=0.5, ATR=10)
  NEW-B: fvg_limit + 1stFVG (RR=2.0, TP1=0.5, ATR=14)

All share: n_left=8, n_right=60, fvg_left=20, fvg_right=5, gap=5.0%, long-only, Mon/Tue/Fri.
Uses 1s magnifier. Pre-holdout through 2025-03-31.
"""

import sys
import time
from pathlib import Path
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.regime_research import (
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

WF_START = "2016-01-01"
PRE_HOLDOUT_END = "2025-03-31"
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

# OLD: existing best — NY LSI fvg_limit v2 (RR=3.0, TP1=0.3)
OLD = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=3.0, tp1_ratio=0.34, atr_length=10,  # 0.3 was pre-constraint; 0.34 is min valid (clamped to 1R at runtime)
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(2, 3),
    name="OLD: RR3.0 TP0.3 ATR10",
)

# NEW-A: fvg_limit (RR=2.0, TP1=0.5, ATR=10)
NEW_A = replace(OLD, rr=2.0, tp1_ratio=0.5, name="NEW-A: RR2.0 TP0.5 ATR10")

# NEW-B: fvg_limit + 1stFVG (RR=2.0, TP1=0.5, ATR=14)
NEW_B = replace(OLD, rr=2.0, tp1_ratio=0.5, atr_length=14,
                lsi_first_fvg_only=True, name="NEW-B: RR2.0 TP0.5 ATR14 1stFVG")

CANDIDATES = {"OLD": OLD, "NEW-A": NEW_A, "NEW-B": NEW_B}


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def main():
    t0 = time.time()

    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}", flush=True)

    print("Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    df_pre = df_5m.loc[:PRE_HOLDOUT_END]
    df_pre_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_pre_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    # Run all 6 variants
    rows = []
    for cname, cfg in CANDIDATES.items():
        t1 = time.time()
        trades = run_backtest(df_pre, cfg, start_date=WF_START,
                              df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
        gated = gate_fn(trades)
        elapsed = time.time() - t1

        for variant, tr in [("ungated", trades), ("gated", gated)]:
            m = compute_metrics(tr)
            filled = _filled_trades(tr)
            rby = m.get("r_by_year", {})
            neg = sum(1 for v in rby.values() if v < 0)
            min_yr = min(rby.values()) if rby else 0
            min_yr_key = min(rby, key=rby.get) if rby else "?"
            rows.append({
                "name": f"{cname} {variant}",
                "trades": m["total_trades"],
                "wr": m["win_rate"],
                "pf": m["profit_factor"],
                "net_r": m["total_r"],
                "dd": m["max_drawdown_r"],
                "calmar": m["calmar_ratio"],
                "sharpe": m["sharpe_ratio"],
                "r_yr": m["total_r"] / 9.25,
                "neg_yr": neg,
                "worst_yr": f"{min_yr_key}:{min_yr:+.1f}",
                "rby": rby,
            })

        print(f"  {cname} done [{elapsed:.1f}s]", flush=True)

    # Print comparison table
    print(f"\n{'='*150}", flush=True)
    print("HEAD-TO-HEAD COMPARISON — PRE-HOLDOUT (2016 to 2025-03-31)", flush=True)
    print(f"{'='*150}", flush=True)
    print(f"{'Config':<30} {'Tr':>4} {'WR%':>6} {'PF':>5} {'NetR':>7} {'DD':>7} {'Calm':>7} {'Shrp':>6} "
          f"{'R/yr':>6} {'NegYr':>5} {'Worst Year':<15}", flush=True)
    print("-" * 150, flush=True)

    for r in rows:
        print(f"{r['name']:<30} {r['trades']:>4} {r['wr']:>5.1%} {r['pf']:>5.2f} "
              f"{r['net_r']:>+7.1f} {r['dd']:>7.1f} {r['calmar']:>7.2f} {r['sharpe']:>6.2f} "
              f"{r['r_yr']:>6.1f} {r['neg_yr']:>5} {r['worst_yr']:<15}", flush=True)

    # R by year detail
    print(f"\n{'='*150}", flush=True)
    print("R BY YEAR", flush=True)
    print(f"{'='*150}", flush=True)

    all_years = sorted(set(y for r in rows for y in r["rby"]))
    header = f"{'Config':<30} " + " ".join(f"{y:>7}" for y in all_years)
    print(header, flush=True)
    print("-" * len(header), flush=True)

    for r in rows:
        vals = " ".join(f"{r['rby'].get(y, 0):>+7.1f}" for y in all_years)
        print(f"{r['name']:<30} {vals}", flush=True)

    # Gate impact summary
    print(f"\n{'='*150}", flush=True)
    print("GATE IMPACT (gated - ungated)", flush=True)
    print(f"{'='*150}", flush=True)
    print(f"{'Candidate':<15} {'ΔCalmar':>8} {'ΔSharpe':>8} {'ΔDD':>7} {'ΔNegYr':>7} {'Trades removed':>15}", flush=True)
    print("-" * 70, flush=True)

    for cname in CANDIDATES:
        ug = next(r for r in rows if r["name"] == f"{cname} ungated")
        g = next(r for r in rows if r["name"] == f"{cname} gated")
        removed = ug["trades"] - g["trades"]
        pct = 100 * removed / ug["trades"] if ug["trades"] else 0
        print(f"{cname:<15} {g['calmar'] - ug['calmar']:>+8.2f} {g['sharpe'] - ug['sharpe']:>+8.2f} "
              f"{g['dd'] - ug['dd']:>+7.1f} {g['neg_yr'] - ug['neg_yr']:>+7d} "
              f"{removed:>6} ({pct:.0f}%)", flush=True)

    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
