#!/usr/bin/env python3
"""Quick comparison: ES NY fine-tune grid winner vs R6 anchor."""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DOW_EXCL = {3, 4}

BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:55",
    entry_start="09:55",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,
    min_gap_atr_pct=1.5,
)

BASE = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=ES,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=5.0,
    tp1_ratio=0.4,
    atr_length=3,
    impulse_close_filter=True,
    name="ES NY",
)

CONFIGS = [
    ("R6 Anchor (stop=3.0, rr=5.0, gap=1.5, tp1=0.4, ATR=3)",
     BASE_SESSION, BASE),
    ("Grid Winner (stop=2.5, rr=5.5, gap=1.5, tp1=0.3, ATR=3)",
     replace(BASE_SESSION, stop_atr_pct=2.5),
     replace(BASE, rr=5.5, tp1_ratio=0.3)),
    ("Runner-up #2 (stop=2.5, rr=5.5, gap=1.5, tp1=0.35, ATR=3)",
     replace(BASE_SESSION, stop_atr_pct=2.5),
     replace(BASE, rr=5.5, tp1_ratio=0.35)),
    ("Runner-up #4 (stop=3.0, rr=4.5, gap=1.25, tp1=0.35, ATR=3)",
     replace(BASE_SESSION, stop_atr_pct=3.0, min_gap_atr_pct=1.25),
     replace(BASE, rr=4.5, tp1_ratio=0.35)),
]


def main():
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("ES_5m.csv")
    df_1m = load_1m_for_5m("ES_5m.csv")
    df_1s = load_1s_for_5m("ES_5m.csv")
    print(f"  Loaded in {time.time()-t0:.1f}s\n")

    for label, sess, cfg in CONFIGS:
        config = replace(cfg, sessions=(sess,))
        trades = run_backtest(df, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        trades = apply_dow_filter(trades, DOW_EXCL)
        m = compute_metrics(trades)

        print("=" * 80)
        print(f"  {label}")
        print("=" * 80)
        print(f"  Trades:        {m['total_trades']}")
        print(f"  Win Rate:      {m['win_rate']:.1%}")
        print(f"  Profit Factor: {m['profit_factor']:.2f}")
        print(f"  Sharpe:        {m['sharpe_ratio']:.3f}")
        print(f"  Sortino:       {m['sortino_ratio']:.3f}")
        print(f"  Net R:         {m['total_r']:.1f}")
        print(f"  Avg R/trade:   {m['avg_r']:.3f}")
        print(f"  Max DD (R):    {m['max_drawdown_r']:.1f}")
        print(f"  Calmar:        {m['calmar_ratio']:.2f}")
        print(f"  Avg Win R:     {m['avg_win_r']:.3f}")
        print(f"  Avg Loss R:    {m['avg_loss_r']:.3f}")
        print(f"  Max Consec W:  {m.get('max_consec_wins', 'N/A')}")
        print(f"  Max Consec L:  {m.get('max_consec_losses', 'N/A')}")

        if "exit_breakdown" in m:
            print(f"\n  Exit Breakdown:")
            for exit_type, count in sorted(m["exit_breakdown"].items()):
                pct = count / m["total_trades"] * 100 if m["total_trades"] > 0 else 0
                print(f"    {exit_type}: {count} ({pct:.1f}%)")

        if "r_by_year" in m:
            print(f"\n  R by Year:")
            years = sorted(m["r_by_year"].items())
            for yr, r in years:
                bar = "+" * int(max(r, 0) / 2) if r > 0 else "-" * int(abs(r) / 2)
                print(f"    {yr}: {r:>+7.1f}  {bar}")

        if "r_by_month" in m:
            print(f"\n  R by Month:")
            months = sorted(m["r_by_month"].items())
            for mo, r in months:
                print(f"    {mo:>2}: {r:>+7.1f}")

        print()


if __name__ == "__main__":
    main()
