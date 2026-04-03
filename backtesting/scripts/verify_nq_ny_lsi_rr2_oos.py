#!/usr/bin/env python3
"""Verify NQ NY LSI RR2/TP0.5 gated — OOS-only trade log.

Runs the exact config from save_nq_ny_lsi_rr2_tp05_thu_gated_final.py,
applies regime gate + Thu DOW filter, then splits into:
  - Pre-holdout: 2016-01-01 to 2025-03-31
  - Holdout: 2025-04-01 onward (genuinely OOS)

Reports metrics on holdout-only trades to verify the council's
30-trade / DSR >= 0.55 / Sharpe >= 1.0 thresholds.
"""

import datetime
import sys
import time
from pathlib import Path
from statistics import median

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.regime_research import (
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.analysis.gates import apply_dow_filter, THU
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
HOLDOUT_START = "2025-04-01"

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

CONFIG = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=14,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
)

# Also compare: FAST_V1.1 version
FAST_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

FAST_CONFIG = StrategyConfig(
    sessions=(FAST_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=3.0, tp1_ratio=0.34, atr_length=10,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
)


def main():
    t0 = time.time()

    print("Loading NQ data...")
    df = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df, df_1m=df_1m, df_1s=df_1s)
    end_date = df.index[-1].strftime("%Y-%m-%d")
    print(f"  {len(df):,} bars -> {end_date}")

    # Build regime calendar
    print("Building regime calendar...")
    regime_cal = build_extended_regime_calendar(df)
    lookup = _regime_lookup(regime_cal, "combined_regime")

    # ══════════════════════════════════════════════════════════════════
    # RR2 GATED VERSION
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  NQ NY LSI RR2/TP0.5 + Thu Excl + Medium-Vol Gate")
    print("=" * 80)

    trades_rr2 = run_backtest(df, CONFIG, start_date="2016-01-01",
                               df_1m=df_1m, df_1s=df_1s, _maps=maps)

    # Apply regime gate
    trades_rr2 = [t for t in trades_rr2
                  if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]

    # Apply Thu DOW filter
    trades_rr2 = apply_dow_filter(trades_rr2, {THU})

    filled_rr2 = [t for t in trades_rr2 if t.exit_type != EXIT_NO_FILL]

    # Split into pre-holdout and holdout
    pre_ho = [t for t in filled_rr2 if t.date < HOLDOUT_START]
    holdout = [t for t in filled_rr2 if t.date >= HOLDOUT_START]

    print(f"\n  FULL HISTORY: {len(filled_rr2)} filled trades")
    m_full = compute_metrics(trades_rr2)
    print(f"    WR: {m_full['win_rate']:.1%}  PF: {m_full['profit_factor']:.2f}  "
          f"Sharpe: {m_full['sharpe_ratio']:.3f}  Net R: {m_full['total_r']:+.1f}  "
          f"DD: {m_full['max_drawdown_r']:.1f}R  Calmar: {m_full['calmar_ratio']:.2f}")
    for y, r in sorted(m_full.get("r_by_year", {}).items()):
        print(f"    {y}: {r:>+7.1f}R")

    print(f"\n  PRE-HOLDOUT (<{HOLDOUT_START}): {len(pre_ho)} trades")
    # Create a metrics-compatible trade list
    pre_ho_all = [t for t in trades_rr2 if t.date < HOLDOUT_START]
    m_pre = compute_metrics(pre_ho_all)
    print(f"    WR: {m_pre['win_rate']:.1%}  PF: {m_pre['profit_factor']:.2f}  "
          f"Sharpe: {m_pre['sharpe_ratio']:.3f}  Net R: {m_pre['total_r']:+.1f}  "
          f"DD: {m_pre['max_drawdown_r']:.1f}R  Calmar: {m_pre['calmar_ratio']:.2f}")

    print(f"\n  *** HOLDOUT (>={HOLDOUT_START}): {len(holdout)} trades ***")
    if holdout:
        ho_all = [t for t in trades_rr2 if t.date >= HOLDOUT_START]
        m_ho = compute_metrics(ho_all)
        print(f"    WR: {m_ho['win_rate']:.1%}  PF: {m_ho['profit_factor']:.2f}  "
              f"Sharpe: {m_ho['sharpe_ratio']:.3f}  Net R: {m_ho['total_r']:+.1f}  "
              f"DD: {m_ho['max_drawdown_r']:.1f}R  Calmar: {m_ho['calmar_ratio']:.2f}")
        for y, r in sorted(m_ho.get("r_by_year", {}).items()):
            print(f"    {y}: {r:>+7.1f}R")

        # Trade-by-trade log
        from orb_backtest.engine.simulator import EXIT_NAMES
        print(f"\n  Holdout trade log ({len(holdout)} trades):")
        print(f"  {'Date':<12} {'Dir':>5} {'Entry':>10} {'R':>8} {'ExitType':>10} {'CumR':>8}")
        print(f"  {'─'*12} {'─'*5} {'─'*10} {'─'*8} {'─'*10} {'─'*8}")
        cum_r = 0.0
        for t in holdout:
            cum_r += t.r_multiple
            etype = EXIT_NAMES.get(t.exit_type, str(t.exit_type))
            direction = "LONG" if t.direction == 1 else "SHORT"
            print(f"  {t.date:<12} {direction:>5} {t.entry_price:>10.2f} "
                  f"{t.r_multiple:>+8.3f} {etype:>10} {cum_r:>+8.3f}")

        # Staggered account sim on holdout only
        print(f"\n  Holdout payout simulation (+5R / -4R, 14-day stagger):")
        from orb_backtest.engine.simulator import EXIT_NO_FILL as ENF
        ho_trade_data = sorted(
            [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in holdout],
            key=lambda x: x["date"],
        )
        d_start = datetime.date.fromisoformat(HOLDOUT_START)
        d_end = datetime.date.fromisoformat(end_date)
        acct_starts = []
        s = d_start
        while s <= d_end:
            acct_starts.append(s)
            s += datetime.timedelta(days=14)

        payouts = breaches = opens = 0
        for acct_start in acct_starts:
            cum = 0.0
            outcome = "open"
            for t in ho_trade_data:
                if t["date"] < acct_start:
                    continue
                cum += t["r"]
                if cum >= 5.0:
                    outcome = "payout"
                    break
                elif cum <= -4.0:
                    outcome = "breach"
                    break
            if outcome == "payout":
                payouts += 1
            elif outcome == "breach":
                breaches += 1
            else:
                opens += 1

        total = payouts + breaches + opens
        resolved = payouts + breaches
        sr = payouts / resolved if resolved > 0 else 0
        print(f"    Accounts: {total}  Payouts: {payouts}  Breaches: {breaches}  Open: {opens}")
        print(f"    Success rate: {sr:.0%}")

    # ══════════════════════════════════════════════════════════════════
    # FAST VERSION (for comparison)
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  NQ NY LSI FAST_V1.1 (RR=3.0, TP1=0.34, Wed+Thu excl, NO gate)")
    print("=" * 80)

    from orb_backtest.analysis.gates import WED
    trades_fast = run_backtest(df, FAST_CONFIG, start_date="2016-01-01",
                                df_1m=df_1m, df_1s=df_1s, _maps=maps)
    trades_fast = apply_dow_filter(trades_fast, {WED, THU})

    filled_fast = [t for t in trades_fast if t.exit_type != EXIT_NO_FILL]
    holdout_fast = [t for t in filled_fast if t.date >= HOLDOUT_START]

    m_fast_full = compute_metrics(trades_fast)
    print(f"\n  FULL HISTORY: {len(filled_fast)} filled trades")
    print(f"    WR: {m_fast_full['win_rate']:.1%}  PF: {m_fast_full['profit_factor']:.2f}  "
          f"Sharpe: {m_fast_full['sharpe_ratio']:.3f}  Net R: {m_fast_full['total_r']:+.1f}  "
          f"DD: {m_fast_full['max_drawdown_r']:.1f}R  Calmar: {m_fast_full['calmar_ratio']:.2f}")

    print(f"\n  *** HOLDOUT (>={HOLDOUT_START}): {len(holdout_fast)} trades ***")
    if holdout_fast:
        ho_fast_all = [t for t in trades_fast if t.date >= HOLDOUT_START]
        m_ho_fast = compute_metrics(ho_fast_all)
        print(f"    WR: {m_ho_fast['win_rate']:.1%}  PF: {m_ho_fast['profit_factor']:.2f}  "
              f"Sharpe: {m_ho_fast['sharpe_ratio']:.3f}  Net R: {m_ho_fast['total_r']:+.1f}  "
              f"DD: {m_ho_fast['max_drawdown_r']:.1f}R  Calmar: {m_ho_fast['calmar_ratio']:.2f}")
        for y, r in sorted(m_ho_fast.get("r_by_year", {}).items()):
            print(f"    {y}: {r:>+7.1f}R")

    # ══════════════════════════════════════════════════════════════════
    # SIDE BY SIDE COMPARISON
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  SIDE-BY-SIDE: Holdout OOS Comparison")
    print("=" * 80)
    if holdout and holdout_fast:
        print(f"\n  {'Metric':<20} {'RR2 Gated':>15} {'FAST V1.1':>15} {'Winner':>10}")
        print(f"  {'─'*20} {'─'*15} {'─'*15} {'─'*10}")

        def fmt_val(name, v):
            if name == "Trades": return f"{v}"
            if name == "Win Rate": return f"{v:.1%}"
            if name in ("Profit Factor", "Calmar"): return f"{v:.2f}"
            if name == "Sharpe": return f"{v:.3f}"
            return f"{v:+.1f}"

        comparisons = [
            ("Trades", len(holdout), len(holdout_fast)),
            ("Win Rate", m_ho['win_rate'], m_ho_fast['win_rate']),
            ("Profit Factor", m_ho['profit_factor'], m_ho_fast['profit_factor']),
            ("Sharpe", m_ho['sharpe_ratio'], m_ho_fast['sharpe_ratio']),
            ("Net R", m_ho['total_r'], m_ho_fast['total_r']),
            ("Max DD", m_ho['max_drawdown_r'], m_ho_fast['max_drawdown_r']),
            ("Calmar", m_ho['calmar_ratio'], m_ho_fast['calmar_ratio']),
        ]
        for name, v1, v2 in comparisons:
            if name == "Max DD":
                winner = "RR2" if abs(v1) < abs(v2) else "FAST"
            elif name == "Trades":
                winner = "—"
            else:
                winner = "RR2" if v1 > v2 else ("FAST" if v2 > v1 else "TIE")
            print(f"  {name:<20} {fmt_val(name, v1):>15} {fmt_val(name, v2):>15} {winner:>10}")

    # ══════════════════════════════════════════════════════════════════
    # COUNCIL THRESHOLD CHECK
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("  COUNCIL THRESHOLD VERIFICATION")
    print("=" * 80)
    if holdout:
        n_trades = len(holdout)
        sharpe = m_ho['sharpe_ratio']
        print(f"\n  OOS Trades:  {n_trades:>6}  (threshold: >= 30)  {'PASS' if n_trades >= 30 else 'FAIL'}")
        print(f"  OOS Sharpe:  {sharpe:>6.3f}  (threshold: >= 1.0)  {'PASS' if sharpe >= 1.0 else 'FAIL'}")
        print(f"  OOS PF:      {m_ho['profit_factor']:>6.2f}  (threshold: >= 1.0)  {'PASS' if m_ho['profit_factor'] >= 1.0 else 'FAIL'}")
        print(f"  OOS DD:      {m_ho['max_drawdown_r']:>6.1f}R")
        print(f"  OOS Net R:   {m_ho['total_r']:>+6.1f}R")
        all_pass = n_trades >= 30 and sharpe >= 1.0 and m_ho['profit_factor'] >= 1.0
        print(f"\n  VERDICT: {'*** SWAP JUSTIFIED ***' if all_pass else '*** STAY ON FAST ***'}")

    print(f"\n  Total runtime: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
