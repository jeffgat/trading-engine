#!/usr/bin/env python3
"""Save NQ NY LSI Prop Firm 2x Risk config to the experiments DB.

Best config from prop firm phase 1 grid sweep (2x risk sizing):
  rr=2.5, tp1=0.2, gap=3.75%, nl=5, long-only, Mon/Tue/Fri

2x risk = $10k/trade → +2.5R payout / -2.0R breach (same $ thresholds as 1x)

Prop firm results (2024-2026, 2x risk):
  52 accounts | 34 payouts | 14 breaches | 4 open
  Success rate: 70.8% | EV per account: +1.168R
  Median days to payout: 38 | Median days to breach: 21
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics


def make_config():
    sess = SessionConfig(
        name="NY",
        rth_start="09:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=3.75,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.5,
        tp1_ratio=0.2,
        atr_length=10,
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
        excluded_days=(2, 3),  # Wed+Thu excluded = Mon/Tue/Fri
        name="NQ NY LSI Prop Firm 2x Risk 2024-2026",
        notes=(
            "Best config from prop firm phase 1 grid sweep with 2x risk sizing. "
            "Anchor from DB run #1335. Grid: rr x tp1 x gap x n_left x 2 DOW variants (1680 configs). "
            "2x risk = halved thresholds (+2.5R payout / -2.0R breach). "
            "Prop firm: 71% success rate, median 38 days to payout, EV +1.17R/account. "
            "At 1x risk: 91% success rate, median 174 days to payout, EV +3.42R/account."
        ),
    )


def main():
    config = make_config()

    print(f"Saving: {config.name}")
    print(f"Config: rr=2.5 | tp1=0.2 | gap=3.75% | nl=5 | ATR=10")
    print(f"LSI long only | Mon/Tue/Fri | bar magnifier")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} [{time.time()-t0:.1f}s]")

    print("\nRunning backtest (2024-2026)...", flush=True)
    t0 = time.time()
    trades = run_backtest(df_5m, config, start_date="2024-03-08", end_date="2026-03-03", df_1m=df_1m)
    m = compute_metrics(trades)
    print(f"  Completed in {time.time()-t0:.1f}s")

    print(f"\n  Trades: {m['total_trades']}")
    print(f"  WR: {m['win_rate']:.1%}")
    print(f"  PF: {m['profit_factor']:.2f}")
    print(f"  Net R: {m['total_r']:.1f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f}")

    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:")
        for yr, r in sorted(rby.items()):
            print(f"    {yr}: {r:+.1f}R")

    # Median stop check
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    med_stop = median(t.risk_points / NQ.min_tick for t in filled) if filled else 0
    print(f"\n  Median stop: {med_stop:.1f} ticks")
    if med_stop < 10:
        print("  ERROR: Median stop < 10 ticks — NOT saving!")
        return

    print("\nSaving to DB...", flush=True)
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved! Result ID: {result_id}")
    print(f"  Experiment name: {config.name}")


if __name__ == "__main__":
    main()
