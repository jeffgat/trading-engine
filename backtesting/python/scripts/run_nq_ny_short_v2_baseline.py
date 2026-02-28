#!/usr/bin/env python3
"""NQ NY Short v2 Baseline — Fresh start with dual 10pt floors.

Default baseline (15m ORB, ATR stop 7.5%) fails at PF 0.95.
Testing adjusted configs using known-positive starting points from diagnostics.
"""

import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime
from statistics import median

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT = NQ
START_DATE = "2016-01-01"
DATA_YEARS = 10


def median_stop_ticks(trades):
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / INSTRUMENT.min_tick for t in filled)


def neg_year_set(m):
    current_year = str(datetime.now().year)
    return {yr for yr, r in m.get("r_by_year", {}).items() if r < 0 and str(yr) != current_year}


def run_config(df_5m, df_1m, df_1s, session, config, label):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    filled = [t for t in trades if t.exit_type != 0]
    med_ticks = median_stop_ticks(trades)
    med_stop_pts = median(t.risk_points for t in filled if t.risk_points > 0) if filled else 0
    neg = neg_year_set(m)
    r_yr = m["total_r"] / DATA_YEARS
    et_c = Counter(t.exit_type for t in filled)

    passed = m["total_trades"] > 100 and m["profit_factor"] > 1.0 and med_ticks >= 10
    marker = " PASS" if passed else " FAIL"

    print(f"\n  {label}{marker}")
    print(f"  {'─' * 65}")
    print(f"  Trades: {m['total_trades']:<6}  WR: {m['win_rate']:.1%}  PF: {m['profit_factor']:.2f}  "
          f"Sharpe: {m['sharpe_ratio']:.2f}  Calmar: {m['calmar_ratio']:.2f}")
    print(f"  Net R: {m['total_r']:.1f}  R/yr: {r_yr:.1f}  MaxDD: {m['max_drawdown_r']:.1f}R  "
          f"Med stop: {med_stop_pts:.1f}pt ({med_ticks:.0f}t)")
    print(f"  Neg years: {len(neg)} {sorted(neg) if neg else ''}")

    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"  R by year: {yr_str}")

    print(f"  Exits: SL={et_c.get(1,0)}, TP1_BE={et_c.get(3,0)}, "
          f"TP1_TP2={et_c.get(2,0)}, TP1_EOD={et_c.get(4,0)}, EOD={et_c.get(5,0)}")

    return m, med_ticks, passed


def main():
    print("NQ NY Short v2 — Baseline Exploration (dual 10pt floors)")
    print("=" * 70)

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    # ── A. Default NY session (15m ORB, ATR stop) ──
    print("\n" + "=" * 70)
    print("  A. DEFAULT NY SESSION (15m ORB, stop_atr=7.5%, gap=2.25%)")
    print("=" * 70)

    default_session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=7.5,
        min_gap_atr_pct=2.25,
        min_stop_points=10.0,
        min_tp1_points=10.0,
    )
    default_config = StrategyConfig(
        sessions=(default_session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=2.5,
        tp1_ratio=0.5,
        atr_length=14,
    )
    run_config(df_5m, df_1m, df_1s, default_session, default_config,
               "Default (15m ORB, ATR 7.5%, rr=2.5, tp1=0.5)")

    # ── B. ORB-based 20m (best from diagnostics) ──
    print("\n" + "=" * 70)
    print("  B. ORB-BASED 20m (orbstop=15%, orbgap=7%)")
    print("=" * 70)

    orb_session = SessionConfig(
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

    configs_b = [
        ("ORB 15%, rr=2.5, tp1=0.5", 2.5, 0.5),
        ("ORB 15%, rr=3.0, tp1=0.3", 3.0, 0.3),
        ("ORB 15%, rr=2.0, tp1=0.4", 2.0, 0.4),
        ("ORB 15%, rr=3.0, tp1=0.5", 3.0, 0.5),
        ("ORB 15%, rr=2.0, tp1=0.3", 2.0, 0.3),
    ]
    for label, rr, tp1 in configs_b:
        cfg = StrategyConfig(
            sessions=(orb_session,),
            instrument=NQ,
            strategy="continuation",
            use_bar_magnifier=True,
            risk_usd=5000.0,
            direction_filter="short",
            rr=rr,
            tp1_ratio=tp1,
            atr_length=14,
        )
        run_config(df_5m, df_1m, df_1s, orb_session, cfg, label)

    # ── C. ATR-based with wider stops + 20m ORB ──
    print("\n" + "=" * 70)
    print("  C. ATR-BASED 20m ORB, WIDER STOPS")
    print("=" * 70)

    for stop_atr, gap_atr in [(10.0, 2.25), (12.5, 2.25)]:
        atr_session = SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end="09:50",
            entry_start="09:50",
            entry_end="15:00",
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=stop_atr,
            min_gap_atr_pct=gap_atr,
            min_stop_points=10.0,
            min_tp1_points=10.0,
        )
        for rr, tp1 in [(3.0, 0.5), (4.0, 0.5), (4.0, 0.6)]:
            cfg = StrategyConfig(
                sessions=(atr_session,),
                instrument=NQ,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="short",
                rr=rr,
                tp1_ratio=tp1,
                atr_length=14,
            )
            run_config(df_5m, df_1m, df_1s, atr_session, cfg,
                       f"ATR {stop_atr}%, rr={rr}, tp1={tp1}")

    # ── D. Both directions with dual floors ──
    print("\n" + "=" * 70)
    print("  D. BOTH DIRECTIONS (ORB-based 20m)")
    print("=" * 70)

    for rr, tp1 in [(2.5, 0.5), (3.0, 0.4), (3.0, 0.5), (2.0, 0.4)]:
        cfg = StrategyConfig(
            sessions=(orb_session,),
            instrument=NQ,
            strategy="continuation",
            use_bar_magnifier=True,
            risk_usd=5000.0,
            direction_filter="both",
            rr=rr,
            tp1_ratio=tp1,
            atr_length=14,
        )
        run_config(df_5m, df_1m, df_1s, orb_session, cfg,
                   f"BOTH, ORB 15%, rr={rr}, tp1={tp1}")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
