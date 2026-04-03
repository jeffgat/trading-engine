#!/usr/bin/env python3
"""NQ NY LSI RR2/TP0.5 + medium-vol gate — 5-year backtest (2021-2026).

Uses WF mode params (ATR=14) and 1s magnifier. Saves to DB.
"""

import sys
import time
from pathlib import Path
from statistics import median

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
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
START_DATE = "2021-01-01"
END_DATE = "2026-03-31"

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

CONFIG = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=14,  # WF mode param
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(2, 3),
    name="NQ NY LSI RR2 TP0.5 Gated 2021-2026",
    notes=(
        "NY LSI fvg_limit long, RR=2.0, TP1=0.5, ATR=14 (WF mode), gap=5.0%, "
        "n_left=8, n_right=60, Mon/Tue/Fri, 1s magnifier. "
        "Medium-vol regime avoidance gate (skip bull_medium_vol + sideways_medium_vol). "
        "Full 8-step strategy workflow: PSR 1.0, DSR 0.785, 100% holdout payout rate."
    ),
)


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def main():
    t0 = time.time()

    print(f"NQ NY LSI RR2/TP0.5 + Medium-Vol Gate — 5-Year Backtest", flush=True)
    print(f"Period: {START_DATE} to {END_DATE}", flush=True)
    print(f"Config: RR=2.0 | TP1=0.5 | ATR=14 | gap=5.0% | fvg_limit | long | MTF", flush=True)
    print(f"Gate: skip bull_medium_vol + sideways_medium_vol\n", flush=True)

    print("Loading data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}", flush=True)

    print("Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    print(f"\nRunning backtest ({START_DATE} to {END_DATE})...", flush=True)
    trades_raw = run_backtest(df_5m, CONFIG, start_date=START_DATE, end_date=END_DATE,
                              df_1m=df_1m, df_1s=df_1s, _maps=maps)
    trades = gate_fn(trades_raw)
    elapsed = time.time() - t0

    m = compute_metrics(trades)
    filled = _filled_trades(trades)
    raw_filled = _filled_trades(trades_raw)
    removed = len(raw_filled) - len(filled)
    pct_removed = 100 * removed / len(raw_filled) if raw_filled else 0

    print(f"  Completed in {elapsed:.1f}s\n", flush=True)

    print(f"  {'Trades (raw)':<24} {len(raw_filled):>10d}", flush=True)
    print(f"  {'Trades (gated)':<24} {len(filled):>10d} ({removed} removed, {pct_removed:.0f}%)", flush=True)
    print(f"  {'Win Rate':<24} {m['win_rate']:>9.1%}", flush=True)
    print(f"  {'Profit Factor':<24} {m['profit_factor']:>10.2f}", flush=True)
    print(f"  {'Net R':<24} {m['total_r']:>9.1f}R", flush=True)
    print(f"  {'Max DD':<24} {m['max_drawdown_r']:>9.1f}R", flush=True)
    print(f"  {'Calmar':<24} {m['calmar_ratio']:>10.2f}", flush=True)
    print(f"  {'Sharpe':<24} {m['sharpe_ratio']:>10.3f}", flush=True)
    print(f"  {'Avg R/trade':<24} {m['avg_r']:>10.3f}", flush=True)
    print(f"  {'Max Consec Losses':<24} {m['max_consecutive_losses']:>10d}", flush=True)

    med_stop = median(t.risk_points / NQ.min_tick for t in filled) if filled else 0
    print(f"  {'Median stop (ticks)':<24} {med_stop:>10.0f}", flush=True)

    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:", flush=True)
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>+8.1f}R{flag}", flush=True)
        neg = sum(1 for v in rby.values() if v < 0)
        print(f"  Negative years: {neg}", flush=True)

    # Exit type breakdown
    from collections import Counter
    exit_counts = Counter(t.exit_type for t in filled)
    exit_names = {1: "SL", 2: "TP1+TP2", 3: "TP1+BE", 4: "TP1+EOD", 5: "EOD", 6: "TP2_SINGLE"}
    print(f"\n  Exit breakdown:", flush=True)
    for etype, count in sorted(exit_counts.items()):
        name = exit_names.get(etype, f"type_{etype}")
        pct = 100 * count / len(filled)
        print(f"    {name:<12} {count:>4} ({pct:>5.1f}%)", flush=True)

    # Monthly breakdown
    rbm = m.get("r_by_month", {})
    if rbm:
        worst_months = sorted(rbm.items(), key=lambda x: x[1])[:5]
        best_months = sorted(rbm.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"\n  Best 5 months:", flush=True)
        for mk, r in best_months:
            print(f"    {mk}: {r:>+7.1f}R", flush=True)
        print(f"  Worst 5 months:", flush=True)
        for mk, r in worst_months:
            print(f"    {mk}: {r:>+7.1f}R", flush=True)

    # Save to DB
    print(f"\nSaving to DB...", flush=True)
    result = results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved! Result ID: {result_id}", flush=True)
    print(f"  Experiment name: {CONFIG.name}", flush=True)
    print(f"\nTotal time: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
