#!/usr/bin/env python3
"""NQ NY Continuation Short — Baseline Test.

Fresh start on fixed engine. Tests if NQ NY shorts have any edge at default params.
Warning: Post-fix R2 long sweeps showed dir=short with negative Calmar (-0.41)
at the long anchor, but shorts need independent optimization with different params.

Baseline config (standard defaults):
  ORB: 09:30-09:45 (15m), entry until 15:30, flat 15:50-16:00
  stop=5.0%, rr=2.0, gap=1.0%, tp1=0.5, ATR=14
  direction=short, ICF=OFF, continuation, 1s magnifier

Pass criteria: >100 trades AND PF >1.0 AND median stop >= 10 ticks.
"""

import sys
import time
from statistics import median

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10


def median_stop_ticks(trades):
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / NQ.min_tick for t in filled)


def main():
    print("NQ NY Continuation Short — Baseline Test")
    print("=" * 80)

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time() - t0:.1f}s]")

    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=1.0,
    )
    config = StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=2.0,
        tp1_ratio=0.5,
        atr_length=14,
        impulse_close_filter=False,
        name="NQ NY Short Baseline",
    )

    print("\nRunning backtest...", flush=True)
    t1 = time.time()
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    print(f"  Backtest completed in {time.time() - t1:.1f}s")

    m = compute_metrics(trades)
    med_ticks = median_stop_ticks(trades)
    n_years = max(DATA_YEARS, 1)

    print(f"\n{'='*80}")
    print(f"  BASELINE RESULTS")
    print(f"{'='*80}")
    print(f"  Trades:      {m['total_trades']}")
    print(f"  Win Rate:    {m['win_rate']:.1%}")
    print(f"  PF:          {m['profit_factor']:.2f}")
    print(f"  Sharpe:      {m['sharpe_ratio']:.2f}")
    print(f"  Net R:       {m['total_r']:.1f}")
    print(f"  R/yr:        {m['total_r'] / n_years:.1f}")
    print(f"  Max DD:      {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar:      {m.get('calmar_ratio', 0):.2f}")
    print(f"  Median stop: {med_ticks:.1f} ticks")

    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"  R by year:   {yr_str}")
        # Count neg full years (exclude current partial year)
        from datetime import datetime
        current_year = str(datetime.now().year)
        full_years = {y: r for y, r in m["r_by_year"].items() if str(y) != current_year}
        neg_years = [y for y, r in sorted(full_years.items()) if r < 0]
        print(f"  Neg years:   {neg_years if neg_years else 'none'}")

    # Pass criteria
    print(f"\n{'='*80}")
    print(f"  PASS CRITERIA")
    print(f"{'='*80}")
    trades_pass = m["total_trades"] > 100
    pf_pass = m["profit_factor"] > 1.0
    ticks_pass = med_ticks >= 10
    print(f"  Trades > 100:       {'PASS' if trades_pass else 'FAIL'} ({m['total_trades']})")
    print(f"  PF > 1.0:           {'PASS' if pf_pass else 'FAIL'} ({m['profit_factor']:.2f})")
    print(f"  Median stop >= 10t: {'PASS' if ticks_pass else 'FAIL'} ({med_ticks:.1f})")

    all_pass = trades_pass and pf_pass and ticks_pass
    print(f"\n  {'>>> BASELINE PASS — proceed to variable sweeps' if all_pass else '>>> BASELINE FAIL — record NO-GO'}")

    # Also test a few alternative starting configs to find the best baseline
    print(f"\n\n{'='*80}")
    print(f"  ALTERNATIVE BASELINES (looking for any edge)")
    print(f"{'='*80}")

    alternatives = [
        ("stop=3.0%, rr=3.0", 3.0, 3.0, 1.0, 0.5, 14, "09:30", "09:45"),
        ("stop=5.0%, rr=3.0", 5.0, 3.0, 1.0, 0.5, 14, "09:30", "09:45"),
        ("stop=7.0%, rr=2.0", 7.0, 2.0, 1.0, 0.5, 14, "09:30", "09:45"),
        ("stop=10.0%, rr=2.5", 10.0, 2.5, 1.0, 0.5, 14, "09:30", "09:45"),
        ("stop=5.0%, rr=2.0, 20m ORB", 5.0, 2.0, 1.0, 0.5, 14, "09:30", "09:50"),
        ("stop=5.0%, rr=2.0, ATR=30", 5.0, 2.0, 1.0, 0.5, 30, "09:30", "09:45"),
        ("stop=5.0%, rr=2.0, gap=2.0%", 5.0, 2.0, 2.0, 0.5, 14, "09:30", "09:45"),
        ("stop=5.0%, rr=2.5, gap=1.5%", 5.0, 2.5, 1.5, 0.5, 14, "09:30", "09:45"),
        ("stop=3.5%, rr=3.75, gap=1.0% (Asia anchor)", 3.5, 3.75, 1.0, 0.6, 30, "09:30", "09:45"),
        ("stop=7.0%, rr=3.0, ATR=20 (Long anchor)", 7.0, 3.0, 2.5, 0.5, 20, "09:30", "09:50"),
    ]

    HDR = (f"    {'#':>3} {'Config':>45} {'Trades':>6} {'WR':>5} {'PF':>5} "
           f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedTk':>6}")
    print(HDR)
    print(f"    {'---' * 35}")

    # Print primary baseline first
    calmar = m.get("calmar_ratio", 0)
    print(f"    {0:>3} {'DEFAULT (stop=5%, rr=2.0, 15m)':>45} {m['total_trades']:>6} "
          f"{m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} "
          f"{m['total_r']:>7.1f} {m['total_r']/n_years:>6.1f} {m['max_drawdown_r']:>6.1f} "
          f"{calmar:>7.2f} {med_ticks:>6.1f}")

    for i, (label, stop, rr, gap, tp1, atr, orb_start, orb_end) in enumerate(alternatives, 1):
        entry_start = orb_end
        s = SessionConfig(
            name="NY",
            orb_start=orb_start,
            orb_end=orb_end,
            entry_start=entry_start,
            entry_end="15:30",
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=stop,
            min_gap_atr_pct=gap,
        )
        c = StrategyConfig(
            sessions=(s,),
            instrument=NQ,
            strategy="continuation",
            use_bar_magnifier=True,
            risk_usd=5000.0,
            direction_filter="short",
            rr=rr,
            tp1_ratio=tp1,
            atr_length=atr,
            impulse_close_filter=False,
            name=f"NQ NY Short Alt {i}",
        )
        t = run_backtest(df_5m, c, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        am = compute_metrics(t)
        mt = median_stop_ticks(t)
        ac = am.get("calmar_ratio", 0)
        print(f"    {i:>3} {label:>45} {am['total_trades']:>6} "
              f"{am['win_rate']:>5.1%} {am['profit_factor']:>5.2f} {am['sharpe_ratio']:>6.2f} "
              f"{am['total_r']:>7.1f} {am['total_r']/n_years:>6.1f} {am['max_drawdown_r']:>6.1f} "
              f"{ac:>7.2f} {mt:>6.1f}")
        if i <= 3 or ac > 1.0:
            rby = am.get("r_by_year", {})
            if rby:
                yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(rby.items()))
                print(f"        R by year: {yr_str}")

    print(f"\n  Select best alternative as anchor if any has Calmar > 1.0 and passes criteria.")
    print(f"  Otherwise: BASELINE FAIL — record NO-GO.")


if __name__ == "__main__":
    main()
