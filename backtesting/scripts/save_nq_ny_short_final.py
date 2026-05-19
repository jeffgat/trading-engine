#!/usr/bin/env python3
"""Save NQ NY Short NO-GO diagnostic to the main DB.

Best config found: ORB-based orbstop=15%, rr=3.0, tp1=0.3, 20m ORB,
  with dual 10pt floors (min_stop_points=10, min_tp1_points=10).

Full-history (2016-2026): 967 trades, 61.5% WR, PF 1.10, Sharpe 0.67,
  37.3R (3.7 R/yr), DD -26.6R, Calmar 1.40, 4 negative years.

Verdict: NO-GO — marginal edge, 4 negative years, fragile to slippage.
"""

import sys
import time
from statistics import median

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10


def make_config():
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=2.0,
        stop_orb_pct=15.0,
        min_gap_orb_pct=7.0,
        min_stop_points=10.0,
        min_tp1_points=10.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=3.0,
        tp1_ratio=0.3,
        atr_length=14,
        impulse_close_filter=False,
        name="NQ NY Short NO-GO Final",
        notes=(
            "Best config from NQ NY continuation shorts investigation. "
            "ORB-based orbstop=15%, 20m ORB (09:30-09:50), rr=3.0, tp1=0.3, "
            "with dual 10pt floors (min_stop_points=10, min_tp1_points=10). "
            "Verdict: NO-GO — 4 negative years, Calmar 1.40, PF 1.10, fragile edge. "
            "Investigation revealed tp1=0.2 trap (88% WR artifact from 3.3pt TP1 targets), "
            "variable sweep oscillation (8 ATR-based rounds never converged), "
            "ORB-based orbstop=15% best stop mechanism but still marginal. "
            "ATR-based stops only viable at extreme rr=4.0 with massive DD. "
            "NQ continuation shorts have no structural edge."
        ),
    )


def main():
    print("Saving NQ NY Short NO-GO Final to DB")
    print("=" * 60)

    print("\nLoading data...")
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    config = make_config()
    print("Running backtest...")
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)

    m = compute_metrics(trades)
    filled = [t for t in trades if t.exit_type != 0]
    med_stop = median(t.risk_points for t in filled if t.risk_points > 0) if filled else 0
    med_stop_ticks = med_stop / NQ.min_tick

    print(f"\n  Trades: {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  PF: {m['profit_factor']:.2f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.2f}")
    print(f"  Net R: {m['total_r']:.1f}")
    print(f"  R/yr: {m['total_r'] / DATA_YEARS:.1f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")
    print(f"  Median stop: {med_stop:.1f}pt ({med_stop_ticks:.0f} ticks)")

    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        neg = [yr for yr, r in years if r < 0 and str(yr) != "2026"]
        print(f"  R by year: {yr_str}")
        print(f"  Negative full years: {len(neg)}")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)

    print(f"\n  Saved as: {result_id}")
    print("  Done.")


if __name__ == "__main__":
    main()
