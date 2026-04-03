#!/usr/bin/env python3
"""NQ NY LSI RR2/TP0.5 — Verify Wed+Thu exclusion matches frontend.

Runs the CORRECT way: excluded_days=(2,3) in the config so the ENGINE
skips Wed/Thu, then applies regime gate, then computes metrics.

This should match what results_to_dict produces and what the frontend shows.
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from statistics import median

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

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

AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

# Method A: excluded_days in config (engine skips Wed/Thu)
CONFIG_ENGINE_EXCL = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=14,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    excluded_days=(2, 3),  # Engine-level Wed+Thu exclusion
    name="Engine DOW excl",
)

# Method B: no excluded_days (post-hoc DOW filter)
CONFIG_NO_EXCL = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=14,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    excluded_days=(),  # No engine exclusion
    name="Post-hoc DOW excl",
)


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def print_metrics_block(m, filled, label):
    rby = m.get("r_by_year", {})
    neg_yr = sum(1 for v in rby.values() if v < 0)
    print(f"\n  {label}", flush=True)
    print(f"  {'Trades':<20} {len(filled):>8}", flush=True)
    print(f"  {'Win Rate':<20} {m['win_rate']:>7.1%}", flush=True)
    print(f"  {'PF':<20} {m['profit_factor']:>8.2f}", flush=True)
    print(f"  {'Net R':<20} {m['total_r']:>+8.1f}R", flush=True)
    print(f"  {'Max DD':<20} {m['max_drawdown_r']:>8.1f}R", flush=True)
    print(f"  {'Calmar':<20} {m['calmar_ratio']:>8.2f}", flush=True)
    print(f"  {'Sharpe':<20} {m['sharpe_ratio']:>8.3f}", flush=True)
    print(f"  {'Avg R':<20} {m['avg_r']:>+8.3f}", flush=True)
    print(f"  {'Neg Years':<20} {neg_yr:>8}", flush=True)
    print(f"\n  R by year:", flush=True)
    for y, r in sorted(rby.items()):
        flag = " <--" if r < 0 else ""
        print(f"    {y}: {r:>+8.1f}R{flag}", flush=True)

    # Check for Wed/Thu trades
    wed_thu = [t for t in filled if datetime.strptime(t.date, "%Y-%m-%d").weekday() in (2, 3)]
    if wed_thu:
        print(f"\n  WARNING: {len(wed_thu)} trades on Wed/Thu found!", flush=True)
        for t in wed_thu[:5]:
            dow = datetime.strptime(t.date, "%Y-%m-%d").strftime("%A")
            print(f"    {t.date} ({dow}): {t.r_multiple:+.3f}R", flush=True)
    else:
        print(f"\n  Confirmed: 0 trades on Wed/Thu", flush=True)


def main():
    t0 = time.time()

    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)

    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    df_pre = df_5m.loc[:"2025-03-31"]
    df_pre_1m = df_1m.loc[:"2025-03-31"] if df_1m is not None else None
    df_pre_1s = df_1s.loc[:"2025-03-31"] if df_1s is not None else None

    # ── Method A: Engine-level DOW exclusion ──────────────────────────
    print(f"\n{'='*70}", flush=True)
    print("  METHOD A: excluded_days=(2,3) in config → regime gate", flush=True)
    print(f"{'='*70}", flush=True)

    trades_a = run_backtest(df_pre, CONFIG_ENGINE_EXCL, start_date="2016-01-01",
                            df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
    trades_a_gated = gate_fn(trades_a)
    filled_a = _filled_trades(trades_a_gated)
    m_a = compute_metrics(trades_a_gated)
    print_metrics_block(m_a, filled_a, "Engine DOW + regime gate")

    # ── Method B: Post-hoc DOW filter ─────────────────────────────────
    print(f"\n{'='*70}", flush=True)
    print("  METHOD B: no excluded_days → regime gate → post-hoc DOW filter", flush=True)
    print(f"{'='*70}", flush=True)

    from orb_backtest.analysis.gates import apply_dow_filter

    trades_b = run_backtest(df_pre, CONFIG_NO_EXCL, start_date="2016-01-01",
                            df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
    trades_b_gated = gate_fn(trades_b)
    trades_b_dow = apply_dow_filter(trades_b_gated, {2, 3})
    filled_b = _filled_trades(trades_b_dow)
    m_b = compute_metrics(trades_b_dow)
    print_metrics_block(m_b, filled_b, "Post-hoc DOW + regime gate")

    # ── Method C: What results_to_dict would do (engine excl + double DOW) ─
    print(f"\n{'='*70}", flush=True)
    print("  METHOD C: Engine DOW → regime gate → results_to_dict DOW (double filter)", flush=True)
    print(f"{'='*70}", flush=True)

    # This is what actually got saved to DB in the 5yr run
    trades_c_dow = apply_dow_filter(trades_a_gated, {2, 3})
    filled_c = _filled_trades(trades_c_dow)
    m_c = compute_metrics(trades_c_dow)
    print_metrics_block(m_c, filled_c, "Double DOW filter (what DB shows)")

    # ── Comparison ────────────────────────────────────────────────────
    print(f"\n{'='*70}", flush=True)
    print("  COMPARISON", flush=True)
    print(f"{'='*70}\n", flush=True)

    print(f"  {'Method':<45} {'Trades':>7} {'Net R':>8} {'Calmar':>8} {'Sharpe':>8}", flush=True)
    print(f"  {'-'*80}", flush=True)
    print(f"  {'A: Engine DOW + gate':<45} {len(filled_a):>7} {m_a['total_r']:>+8.1f} {m_a['calmar_ratio']:>8.2f} {m_a['sharpe_ratio']:>8.3f}", flush=True)
    print(f"  {'B: Post-hoc DOW + gate':<45} {len(filled_b):>7} {m_b['total_r']:>+8.1f} {m_b['calmar_ratio']:>8.2f} {m_b['sharpe_ratio']:>8.3f}", flush=True)
    print(f"  {'C: Engine DOW + gate + DOW again (DB bug)':<45} {len(filled_c):>7} {m_c['total_r']:>+8.1f} {m_c['calmar_ratio']:>8.2f} {m_c['sharpe_ratio']:>8.3f}", flush=True)

    if len(filled_a) == len(filled_b):
        print(f"\n  Methods A and B MATCH — engine DOW exclusion works correctly for LSI.", flush=True)
    else:
        print(f"\n  Methods A and B DIFFER by {abs(len(filled_a) - len(filled_b))} trades.", flush=True)
        print(f"  Engine DOW exclusion does NOT work for LSI — the bug is confirmed.", flush=True)

    print(f"\n  Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
