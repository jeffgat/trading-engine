#!/usr/bin/env python3
"""Test pre-trade structural gates (ORB Size + Volatility Regime) on NY+Asia.

Runs the backtest, then replays trades through each gate to measure impact.
Also sweeps gate parameters to find optimal thresholds.

Usage:
    python scripts/run_pretrade_gates.py
    python scripts/run_pretrade_gates.py --start 2016-01-01 --end 2026-01-01
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_continuation.config import production_config
from core.data.instruments import get_instrument
from core.data.loader import load_5m_data
from core.engine.simulator import run_backtest, EXIT_NO_FILL
from core.results.metrics import compute_metrics
from core.analysis.pre_trade_gates import (
    ORBSizeGateConfig, VolRegimeGateConfig,
    simulate_orb_size_gate, simulate_vol_regime_gate,
    simulate_combined_gates,
    sweep_orb_gate, sweep_vol_gate,
)


def main():
    parser = argparse.ArgumentParser(description="Pre-trade gates: ORB size + vol regime")
    parser.add_argument("--data", default="NQ_5m.csv", help="Data file")
    parser.add_argument("--start", default="2016-01-01", help="Start date")
    parser.add_argument("--end", default="2026-01-01", help="End date")
    parser.add_argument("--instrument", default="NQ", help="Instrument")
    args = parser.parse_args()

    instrument = get_instrument(args.instrument)

    # ── Load data ────────────────────────────────────────────────────
    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    # ── Run backtests per session ────────────────────────────────────
    all_trades = []
    for config in production_config(instrument):
        sess_name = config.sessions[0].name
        print(f"\n  Running {sess_name} backtest...")
        t0 = time.time()
        trades = run_backtest(df, config, start_date=args.start)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"    {len(trades)} signals, {len(filled)} filled [{time.time() - t0:.1f}s]")
        all_trades.extend(trades)

    all_trades.sort(key=lambda t: t.date)
    filled = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]
    print(f"\n  Combined: {len(filled)} filled trades")

    # ── Baseline ─────────────────────────────────────────────────────
    baseline = compute_metrics(all_trades)
    risk_usd = 5000.0
    baseline_r = baseline["total_pnl_usd"] / risk_usd
    print()
    print("=" * 70)
    print("BASELINE (No Gate)")
    print("=" * 70)
    _print_metrics(baseline, risk_usd)

    # ── ORB range distribution ───────────────────────────────────────
    import numpy as np
    orb_ranges = np.array([t.orb_range for t in filled if t.orb_range > 0])
    atrs = np.array([t.daily_atr for t in filled if t.daily_atr > 0 and t.orb_range > 0])
    if len(orb_ranges) > 0 and len(atrs) > 0:
        orb_atr_pcts = (orb_ranges / atrs) * 100
        print(f"\n  ORB Range as % of ATR distribution:")
        print(f"    Min:     {np.min(orb_atr_pcts):>6.1f}%")
        print(f"    5th:     {np.percentile(orb_atr_pcts, 5):>6.1f}%")
        print(f"    25th:    {np.percentile(orb_atr_pcts, 25):>6.1f}%")
        print(f"    Median:  {np.median(orb_atr_pcts):>6.1f}%")
        print(f"    75th:    {np.percentile(orb_atr_pcts, 75):>6.1f}%")
        print(f"    95th:    {np.percentile(orb_atr_pcts, 95):>6.1f}%")
        print(f"    Max:     {np.max(orb_atr_pcts):>6.1f}%")

    # ── ORB Size Gate (default) ──────────────────────────────────────
    print()
    print("=" * 70)
    print("ORB SIZE GATE")
    print("=" * 70)

    orb_result = simulate_orb_size_gate(all_trades)
    _print_gate_comparison(orb_result, risk_usd)

    # ── ORB Size Gate sweep ──────────────────────────────────────────
    print()
    print("-" * 70)
    print("ORB Size Gate — Parameter Sweep")
    print("-" * 70)

    orb_sweep = sweep_orb_gate(all_trades)
    print(f"\n  {'min%':>5} {'max%':>5} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
          f"{'Sharpe':>8} {'Calmar':>8} {'MaxDD':>10} {'Skip':>5}")
    print(f"  {'-'*5} {'-'*5} {'-'*7} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*10} {'-'*5}")
    for r in orb_sweep[:15]:
        print(f"  {r['min_orb_atr_pct']:>5.1f} {r['max_orb_atr_pct']:>5.1f} "
              f"{r['trades']:>7} {r['win_rate']:>5.1%} {r['total_r']:>8.1f} "
              f"{r['sharpe']:>8.3f} {r['calmar']:>8.3f} "
              f"${r['max_dd_usd']:>9,.0f} {r['skipped']:>5}")

    # ── Volatility Regime Gate (default) ─────────────────────────────
    print()
    print("=" * 70)
    print("VOLATILITY REGIME GATE")
    print("=" * 70)

    vol_result = simulate_vol_regime_gate(all_trades)
    _print_gate_comparison(vol_result, risk_usd)

    pct_stats = vol_result.get("percentile_stats", {})
    if pct_stats:
        print(f"\n  ATR Percentile distribution:")
        for k, v in pct_stats.items():
            print(f"    {k}: {v:.1f}")

    # ── Vol Regime Gate sweep ────────────────────────────────────────
    print()
    print("-" * 70)
    print("Volatility Regime Gate — Parameter Sweep")
    print("-" * 70)

    vol_sweep = sweep_vol_gate(all_trades)
    print(f"\n  {'LB':>4} {'lo%':>5} {'hi%':>5} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
          f"{'Sharpe':>8} {'Calmar':>8} {'MaxDD':>10} {'Skip':>5}")
    print(f"  {'-'*4} {'-'*5} {'-'*5} {'-'*7} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*10} {'-'*5}")
    for r in vol_sweep[:15]:
        print(f"  {r['lookback']:>4} {r['low_pct']:>5.1f} {r['high_pct']:>5.1f} "
              f"{r['trades']:>7} {r['win_rate']:>5.1%} {r['total_r']:>8.1f} "
              f"{r['sharpe']:>8.3f} {r['calmar']:>8.3f} "
              f"${r['max_dd_usd']:>9,.0f} {r['skipped']:>5}")

    # ── Combined gate (best from each sweep) ────────────────────────
    print()
    print("=" * 70)
    print("COMBINED GATE (ORB Size + Vol Regime)")
    print("=" * 70)

    # Use best ORB params by Sharpe
    if orb_sweep:
        best_orb = orb_sweep[0]
        orb_cfg = ORBSizeGateConfig(
            min_orb_atr_pct=best_orb["min_orb_atr_pct"],
            max_orb_atr_pct=best_orb["max_orb_atr_pct"],
        )
        print(f"  Best ORB gate: min={best_orb['min_orb_atr_pct']:.1f}%, "
              f"max={best_orb['max_orb_atr_pct']:.1f}%")
    else:
        orb_cfg = ORBSizeGateConfig()

    if vol_sweep:
        best_vol = vol_sweep[0]
        vol_cfg = VolRegimeGateConfig(
            lookback_trades=best_vol["lookback"],
            low_pct=best_vol["low_pct"],
            high_pct=best_vol["high_pct"],
        )
        print(f"  Best vol gate: lookback={best_vol['lookback']}, "
              f"low={best_vol['low_pct']:.0f}%, high={best_vol['high_pct']:.0f}%")
    else:
        vol_cfg = VolRegimeGateConfig()

    combined_result = simulate_combined_gates(all_trades, orb_cfg, vol_cfg)
    _print_gate_comparison(combined_result, risk_usd)

    skip_reasons = combined_result.get("skip_reasons", {})
    if skip_reasons:
        print(f"\n  Skip reasons:")
        print(f"    ORB only:  {skip_reasons.get('orb_only', 0)}")
        print(f"    Vol only:  {skip_reasons.get('vol_only', 0)}")
        print(f"    Both:      {skip_reasons.get('both', 0)}")

    # ── Session-level analysis ───────────────────────────────────────
    print()
    print("=" * 70)
    print("PER-SESSION GATE IMPACT")
    print("=" * 70)

    for sess_name in ["NY", "Asia"]:
        sess_trades = [t for t in all_trades if t.session == sess_name]
        if not sess_trades:
            continue

        sess_filled = [t for t in sess_trades if t.exit_type != EXIT_NO_FILL]
        sess_baseline = compute_metrics(sess_trades)

        print(f"\n  --- {sess_name} ({len(sess_filled)} trades) ---")
        print(f"    Baseline: {sess_baseline['total_pnl_usd']/risk_usd:.1f}R, "
              f"WR={sess_baseline['win_rate']:.1%}, "
              f"Sharpe={sess_baseline['sharpe_ratio']:.3f}")

        # ORB gate with best params
        orb_r = simulate_orb_size_gate(sess_trades, orb_cfg)
        gated = orb_r.get("gated_metrics", {})
        if gated.get("total_trades", 0) > 0:
            print(f"    ORB gate:  {gated['total_pnl_usd']/risk_usd:.1f}R, "
                  f"WR={gated['win_rate']:.1%}, "
                  f"Sharpe={gated['sharpe_ratio']:.3f}, "
                  f"skip={orb_r['skipped_count']}")

        # Vol gate with best params
        vol_r = simulate_vol_regime_gate(sess_trades, vol_cfg)
        gated = vol_r.get("gated_metrics", {})
        if gated.get("total_trades", 0) > 0:
            print(f"    Vol gate:  {gated['total_pnl_usd']/risk_usd:.1f}R, "
                  f"WR={gated['win_rate']:.1%}, "
                  f"Sharpe={gated['sharpe_ratio']:.3f}, "
                  f"skip={vol_r['skipped_count']}")

        # Combined
        comb_r = simulate_combined_gates(sess_trades, orb_cfg, vol_cfg)
        gated = comb_r.get("gated_metrics", {})
        if gated.get("total_trades", 0) > 0:
            print(f"    Combined:  {gated['total_pnl_usd']/risk_usd:.1f}R, "
                  f"WR={gated['win_rate']:.1%}, "
                  f"Sharpe={gated['sharpe_ratio']:.3f}, "
                  f"skip={comb_r['skipped_count']}")

    print()
    print("=" * 70)


def _print_metrics(m: dict, risk_usd: float):
    total_r = m["total_pnl_usd"] / risk_usd
    print(f"  Trades:     {m['total_trades']}")
    print(f"  Win Rate:   {m['win_rate']:.1%}")
    print(f"  Total PnL:  {total_r:.1f}R (${m['total_pnl_usd']:,.0f})")
    print(f"  Sharpe:     {m['sharpe_ratio']:.3f}")
    print(f"  Sortino:    {m['sortino_ratio']:.3f}")
    print(f"  Calmar:     {m['calmar_ratio']:.3f}")
    print(f"  Max DD:     ${m['max_drawdown_usd']:,.0f}")
    print(f"  PF:         {m['profit_factor']:.2f}")


def _print_gate_comparison(result: dict, risk_usd: float):
    orig = result.get("original_metrics", {})
    gated = result.get("gated_metrics", {})
    skipped = result.get("skipped_metrics", {})

    if not orig:
        print("\n  No trades to analyze")
        return

    cfg = result.get("gate_config", {})
    print(f"\n  Config: {cfg}")
    print(f"\n  {'':>20} {'Original':>12} {'Gated':>12} {'Skipped':>12} {'Delta':>10}")
    print(f"  {'':>20} {'─'*12} {'─'*12} {'─'*12} {'─'*10}")

    def _row(label, key, fmt="f3"):
        o = orig.get(key, 0)
        g = gated.get(key, 0) if gated else 0
        s = skipped.get(key, 0) if skipped else 0

        if fmt == "d":
            delta = g - o if o else 0
            print(f"  {label:>20} {o:>12} {g:>12} {s:>12} {delta:>+10}")
        elif fmt == "pct":
            delta = (g - o) * 100 if o else 0
            print(f"  {label:>20} {o:>11.1%} {g:>11.1%} {s:>11.1%} {delta:>+9.1f}pp")
        elif fmt == "r":
            o_r = o / risk_usd if risk_usd else 0
            g_r = g / risk_usd if risk_usd else 0
            s_r = s / risk_usd if risk_usd else 0
            delta = g_r - o_r
            print(f"  {label:>20} {o_r:>11.1f}R {g_r:>11.1f}R {s_r:>11.1f}R {delta:>+9.1f}R")
        elif fmt == "dollar":
            delta = g - o if o else 0
            print(f"  {label:>20} ${o:>10,.0f} ${g:>10,.0f} ${s:>10,.0f} ${delta:>+8,.0f}")
        else:
            delta = g - o if o else 0
            print(f"  {label:>20} {o:>12.3f} {g:>12.3f} {s:>12.3f} {delta:>+10.3f}")

    _row("Trades", "total_trades", "d")
    _row("Win Rate", "win_rate", "pct")
    _row("Total PnL", "total_pnl_usd", "r")
    _row("Sharpe", "sharpe_ratio")
    _row("Sortino", "sortino_ratio")
    _row("Calmar", "calmar_ratio")
    _row("Max DD", "max_drawdown_usd", "dollar")
    _row("Profit Factor", "profit_factor")


if __name__ == "__main__":
    main()
