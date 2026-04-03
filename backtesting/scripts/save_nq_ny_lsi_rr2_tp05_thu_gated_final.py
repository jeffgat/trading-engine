#!/usr/bin/env python3
"""Save NQ NY LSI RR2/TP0.5 Thu-only + medium-vol gate — final config.

Full 8-step strategy workflow validated:
  - PSR 0.9999, DSR 0.709, MC 99.3% survival, 0.7% ruin
  - Holdout: 45tr, 66.7% WR, +11.2R, DD -2.6R, 100% payout rate
  - Pre-holdout: 543tr, 60.6% WR, +115.2R, Calmar 15.24, 0 neg years

Saves two runs: full history (2016-2026) and 5-year (2021-2026).
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
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

# excluded_days=() because LSI engine doesn't respect it — DOW filter applied post-hoc
CONFIG_FULL = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=14,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(3,),  # Thu excluded — results_to_dict will apply this
    name="NQ NY LSI RR2 TP0.5 Thu Gated 2016-2026",
    notes=(
        "NY LSI fvg_limit long, RR=2.0, TP1=0.5, ATR=14 (WF mode), gap=5.0%, "
        "n_left=8, n_right=60, Thu excluded, 1s magnifier. "
        "Medium-vol regime avoidance gate (skip bull_medium_vol + sideways_medium_vol). "
        "Full 8-step workflow: PSR 0.9999, DSR 0.709, MC 99.3% survival 0.7% ruin, "
        "holdout 100% payout rate. Thu-only exclusion beats Wed+Thu on Calmar (15.24 vs 12.04) "
        "and MC survival (99.3% vs 96.9%) while keeping 138 more trades."
    ),
)

CONFIG_5YR = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=14,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(3,),
    name="NQ NY LSI RR2 TP0.5 Thu Gated 2021-2026",
    notes="5-year slice of the final config. Same as full history but 2021-2026 only.",
)


def make_gate(regime_cal):
    lookup = _regime_lookup(regime_cal, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def run_and_save(df, config, start, end, df_1m, df_1s, maps, gate_fn):
    print(f"\n{'─'*60}", flush=True)
    print(f"  {config.name}", flush=True)
    print(f"  Period: {start} to {end}", flush=True)
    print(f"{'─'*60}", flush=True)

    t0 = time.time()
    trades = run_backtest(df, config, start_date=start, end_date=end,
                          df_1m=df_1m, df_1s=df_1s, _maps=maps)
    # Apply regime gate BEFORE results_to_dict (which handles DOW filter)
    trades = gate_fn(trades)
    elapsed = time.time() - t0

    # Compute metrics on what results_to_dict will produce (DOW filtered)
    from orb_backtest.results.export import _apply_replay_filters
    display_trades = _apply_replay_filters(trades, config)
    m = compute_metrics(display_trades)
    filled = _filled_trades(display_trades)

    print(f"  Completed in {elapsed:.1f}s", flush=True)
    print(f"  Trades: {len(filled)}", flush=True)
    print(f"  WR: {m['win_rate']:.1%}  PF: {m['profit_factor']:.2f}", flush=True)
    print(f"  Net R: {m['total_r']:+.1f}R  DD: {m['max_drawdown_r']:.1f}R", flush=True)
    print(f"  Calmar: {m['calmar_ratio']:.2f}  Sharpe: {m['sharpe_ratio']:.3f}", flush=True)

    rby = m.get("r_by_year", {})
    for y, r in sorted(rby.items()):
        flag = " <--" if r < 0 else ""
        print(f"    {y}: {r:>+7.1f}R{flag}", flush=True)

    med_stop = median(t.risk_points / NQ.min_tick for t in filled) if filled else 0
    print(f"  Median stop: {med_stop:.0f} ticks", flush=True)

    if med_stop < 10:
        print("  ERROR: Median stop < 10 ticks — NOT saving!", flush=True)
        return None

    print("  Saving to DB...", flush=True)
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved! ID: {result_id}", flush=True)
    return result_id


def main():
    t0 = time.time()

    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df, df_1m=df_1m, df_1s=df_1s)
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}", flush=True)

    regime_cal = build_extended_regime_calendar(df)
    gate_fn = make_gate(regime_cal)

    # Full history
    id_full = run_and_save(df, CONFIG_FULL, "2016-01-01", "2026-03-31",
                           df_1m, df_1s, maps, gate_fn)

    # 5-year
    id_5yr = run_and_save(df, CONFIG_5YR, "2021-01-01", "2026-03-31",
                          df_1m, df_1s, maps, gate_fn)

    print(f"\nDone! Total time: {time.time() - t0:.0f}s", flush=True)
    print(f"  Full history: {id_full}", flush=True)
    print(f"  5-year: {id_5yr}", flush=True)


if __name__ == "__main__":
    main()
