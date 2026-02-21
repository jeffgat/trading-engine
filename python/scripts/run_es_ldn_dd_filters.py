#!/usr/bin/env python3
"""ES London ORB Continuation — ATR volatility gate + day-of-week filter sweep.

Tests two DD-reduction approaches post-hoc on the WF mode params:
  rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5, be=0, both directions

Filter 1: ATR volatility gate
  Skip trades when daily ATR > ATR_SMA(N) * threshold.
  Sweeps: atr_sma_length=[10,20,40], threshold=[1.1,1.2,1.3,1.5,2.0]

Filter 2: Day-of-week filter
  Shows R and DD contribution per weekday, then tests excluding each day.
"""

import sys, time
from datetime import datetime
sys.path.insert(0, "src")

import numpy as np

from orb_backtest.config import LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_atr_volatility_gate, apply_dow_filter, DOW_NAMES

START_DATE = "2016-01-01"

ATR_SMA_LENGTHS = [10, 20, 40]
ATR_THRESHOLDS  = [1.1, 1.2, 1.3, 1.5, 2.0]


def get_metrics(trades):
    m = compute_metrics(trades)
    return {
        "trades": m["total_trades"], "wr": m["win_rate"], "pf": m["profit_factor"],
        "sharpe": m["sharpe_ratio"], "total_r": m["total_r"],
        "max_dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
    }


def print_table(title, rows, sort_key="sharpe", n=25):
    sorted_rows = sorted(rows, key=lambda r: r[sort_key], reverse=True)
    print(f"\n{'='*110}")
    print(f"  {title} (top {n} by {sort_key})")
    print(f"{'='*110}")
    print(f"{'#':>3} {'Label':<30} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7}")
    print("-" * 110)
    for i, r in enumerate(sorted_rows[:n], 1):
        print(f"{i:>3} {r['label']:<30} {r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} "
              f"{r['sharpe']:>7.2f} {r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f}")


def main():
    print("ES LDN — ATR Volatility Gate + Day-of-Week Filter")
    print("=" * 70)

    t0 = time.time()
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)
    print(f"Data loaded in {time.time() - t0:.1f}s")

    config = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        rr=3.0,
        tp1_ratio=0.5,
        name="ES LDN WF mode",
    )
    config = with_overrides(config, ldn_stop_atr_pct=1.5, ldn_min_gap_atr_pct=1.25)

    print("Running base backtest...", flush=True)
    t0 = time.time()
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    print(f"Done in {time.time() - t0:.1f}s")

    base = get_metrics(trades)
    print(f"\nBaseline: {base['trades']} trades, {base['wr']:.1%} WR, PF {base['pf']:.2f}, "
          f"Sharpe {base['sharpe']:.2f}, {base['total_r']:.1f}R, DD {base['max_dd']:.1f}R")

    # ── ATR VOLATILITY GATE ─────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print(f"  FILTER 1: ATR VOLATILITY GATE")
    print(f"  ATR_SMA lengths: {ATR_SMA_LENGTHS}  |  Thresholds: {ATR_THRESHOLDS}")
    print(f"  Skip trade when daily_ATR > ATR_SMA(N) * threshold")
    print(f"{'='*70}")

    atr_rows = [{"label": "BASELINE (no filter)", **base}]

    for sma_len in ATR_SMA_LENGTHS:
        for thresh in ATR_THRESHOLDS:
            gated = apply_atr_volatility_gate(
                trades, df_5m,
                atr_sma_length=sma_len,
                threshold=thresh,
            )
            m = get_metrics(gated)
            if m["trades"] < 50:
                continue
            atr_rows.append({
                "label": f"ATR_SMA{sma_len} x{thresh}",
                **m,
            })

    print_table("ATR GATE — BEST BY SHARPE", atr_rows, sort_key="sharpe")
    print_table("ATR GATE — LOWEST DD (trades>=200)",
                [r for r in atr_rows if r["trades"] >= 200],
                sort_key="max_dd", n=15)

    # Before/after for the single best ATR config (by Sharpe, excluding baseline)
    non_base = [r for r in atr_rows if r["label"] != "BASELINE (no filter)"]
    if non_base:
        best_atr = max(non_base, key=lambda r: r["sharpe"])
        print(f"\n  Best ATR gate config: {best_atr['label']}")
        print(f"  {'':30} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7}")
        print(f"  {'Baseline':<30} {base['trades']:>7} {base['wr']:>5.1%} {base['pf']:>6.2f} "
              f"{base['sharpe']:>7.2f} {base['total_r']:>7.1f} {base['max_dd']:>7.1f}")
        print(f"  {best_atr['label']:<30} {best_atr['trades']:>7} {best_atr['wr']:>5.1%} "
              f"{best_atr['pf']:>6.2f} {best_atr['sharpe']:>7.2f} {best_atr['total_r']:>7.1f} "
              f"{best_atr['max_dd']:>7.1f}")

    # ── DAY OF WEEK FILTER ──────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print(f"  FILTER 2: DAY-OF-WEEK ANALYSIS")
    print(f"{'='*70}")

    # Per-weekday breakdown
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    dow_stats = {d: {"r": [], "trades": 0} for d in range(5)}
    for t in filled:
        dow = datetime.strptime(t.date, "%Y-%m-%d").weekday()
        if dow in dow_stats:
            dow_stats[dow]["r"].append(t.r_multiple)
            dow_stats[dow]["trades"] += 1

    print(f"\n  {'Day':<10} {'Trades':>7} {'WR':>6} {'Net R':>8} {'Avg R':>7} {'MaxDD':>8}")
    print("  " + "-" * 55)
    for dow in range(5):
        rs = np.array(dow_stats[dow]["r"])
        if len(rs) == 0:
            continue
        equity = np.cumsum(rs)
        peak = np.maximum.accumulate(equity)
        dd = float(np.min(equity - peak))
        wr = float(np.mean(rs > 0))
        print(f"  {DOW_NAMES[dow]:<10} {len(rs):>7} {wr:>5.1%} {float(rs.sum()):>8.1f}R "
              f"{float(rs.mean()):>7.3f} {dd:>7.1f}R")

    # Test excluding each single day
    print(f"\n  EXCLUDE SINGLE DAY:")
    print(f"  {'Excluded':<10} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'vs Base DD':>10}")
    print("  " + "-" * 80)
    dow_rows = []
    for dow in range(5):
        filtered = apply_dow_filter(trades, excluded_days={dow})
        m = get_metrics(filtered)
        dd_delta = m["max_dd"] - base["max_dd"]
        print(f"  {DOW_NAMES[dow]:<10} {m['trades']:>7} {m['wr']:>5.1%} {m['pf']:>6.2f} "
              f"{m['sharpe']:>7.2f} {m['total_r']:>7.1f} {m['max_dd']:>7.1f} {dd_delta:>+10.1f}R")
        dow_rows.append({"label": f"excl {DOW_NAMES[dow]}", **m})

    # Test excluding worst two days
    print(f"\n  EXCLUDE PAIRS OF DAYS:")
    print(f"  {'Excluded':<15} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'vs Base DD':>10}")
    print("  " + "-" * 85)
    for d1 in range(5):
        for d2 in range(d1 + 1, 5):
            filtered = apply_dow_filter(trades, excluded_days={d1, d2})
            m = get_metrics(filtered)
            if m["trades"] < 100:
                continue
            dd_delta = m["max_dd"] - base["max_dd"]
            label = f"excl {DOW_NAMES[d1]}+{DOW_NAMES[d2]}"
            print(f"  {label:<15} {m['trades']:>7} {m['wr']:>5.1%} {m['pf']:>6.2f} "
                  f"{m['sharpe']:>7.2f} {m['total_r']:>7.1f} {m['max_dd']:>7.1f} {dd_delta:>+10.1f}R")

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Baseline:     {base['trades']} trades, Sharpe {base['sharpe']:.2f}, "
          f"Net R {base['total_r']:.1f}, DD {base['max_dd']:.1f}R")
    if non_base:
        best_atr_calmar = max(non_base, key=lambda r: r["calmar"])
        print(f"  Best ATR (Sharpe):  {best_atr['label']} → "
              f"Sharpe {best_atr['sharpe']:.2f}, DD {best_atr['max_dd']:.1f}R, "
              f"{best_atr['trades']} trades")
        print(f"  Best ATR (Calmar):  {best_atr_calmar['label']} → "
              f"Calmar {best_atr_calmar['calmar']:.2f}, DD {best_atr_calmar['max_dd']:.1f}R")


if __name__ == "__main__":
    main()
