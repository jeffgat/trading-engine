#!/usr/bin/env python3
"""Test Trend Alignment Gate and Consecutive Loss Gate on NY+Asia.

Runs backtest, then replays trades through each gate with parameter sweeps.
Saves best-gated results for frontend comparison.

Usage:
    python scripts/run_trend_consec_gates.py
    python scripts/run_trend_consec_gates.py --start 2016-01-01 --end 2026-01-01
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_continuation.config import (
    production_config,
    PROD_NY_SESSION, PROD_ASIA_SESSION,
    PROD_NY_GLOBALS, PROD_ASIA_GLOBALS,
)
from core.data.instruments import get_instrument
from core.data.loader import load_5m_data
from core.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES, TradeResult
from core.results.metrics import compute_metrics
from core.results.export import save_backtest_result
from core.analysis.pre_trade_gates import (
    TrendAlignmentGateConfig, ConsecLossGateConfig,
    simulate_trend_alignment_gate, simulate_consec_loss_gate,
    sweep_trend_gate, sweep_consec_loss_gate,
)

import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Trend Alignment + Consecutive Loss gates")
    parser.add_argument("--data", default="NQ_5m.csv", help="Data file")
    parser.add_argument("--start", default="2016-01-01", help="Start date")
    parser.add_argument("--end", default="2026-01-01", help="End date")
    parser.add_argument("--instrument", default="NQ", help="Instrument")
    parser.add_argument("--save", action="store_true", help="Save best results for frontend")
    args = parser.parse_args()

    instrument = get_instrument(args.instrument)

    # ── Load data ────────────────────────────────────────────────────
    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    # ── Run backtests per session ────────────────────────────────────
    all_trades: list[TradeResult] = []
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
    print()
    print("=" * 70)
    print("BASELINE (No Gate)")
    print("=" * 70)
    _print_metrics(baseline, risk_usd)

    # ── Trend Alignment Gate ─────────────────────────────────────────
    print()
    print("=" * 70)
    print("TREND ALIGNMENT GATE (prev close vs 20-day SMA)")
    print("=" * 70)

    # With-trend
    trend_with = simulate_trend_alignment_gate(
        all_trades, TrendAlignmentGateConfig(mode="with_trend")
    )
    print("\n  --- WITH TREND (longs above SMA, shorts below) ---")
    _print_gate_comparison(trend_with, risk_usd)
    counts = trend_with.get("alignment_counts", {})
    print(f"\n  Alignment: {counts.get('with_trend', 0)} with-trend, "
          f"{counts.get('counter_trend', 0)} counter-trend, "
          f"{counts.get('unknown', 0)} unknown")

    # Counter-trend
    trend_counter = simulate_trend_alignment_gate(
        all_trades, TrendAlignmentGateConfig(mode="counter_trend")
    )
    print("\n  --- COUNTER TREND (longs below SMA, shorts above) ---")
    _print_gate_comparison(trend_counter, risk_usd)

    # Per-session breakdown
    print()
    print("-" * 70)
    print("Trend Alignment — Per Session")
    print("-" * 70)

    for sess_name in ["NY", "Asia"]:
        sess_trades = [t for t in all_trades if t.session == sess_name]
        if not sess_trades:
            continue

        sess_filled = [t for t in sess_trades if t.exit_type != EXIT_NO_FILL]
        sess_baseline = compute_metrics(sess_trades)

        print(f"\n  --- {sess_name} ({len(sess_filled)} trades) ---")
        print(f"    Baseline:      {sess_baseline['total_pnl_usd']/risk_usd:.1f}R, "
              f"WR={sess_baseline['win_rate']:.1%}, "
              f"Sharpe={sess_baseline['sharpe_ratio']:.3f}")

        for mode in ["with_trend", "counter_trend"]:
            r = simulate_trend_alignment_gate(
                sess_trades, TrendAlignmentGateConfig(mode=mode)
            )
            gated = r.get("gated_metrics", {})
            if gated.get("total_trades", 0) > 0:
                label = "With-trend" if mode == "with_trend" else "Counter"
                print(f"    {label:14s} {gated['total_pnl_usd']/risk_usd:.1f}R, "
                      f"WR={gated['win_rate']:.1%}, "
                      f"Sharpe={gated['sharpe_ratio']:.3f}, "
                      f"skip={r['skipped_count']}")

    # ── Consecutive Loss Gate ────────────────────────────────────────
    print()
    print("=" * 70)
    print("CONSECUTIVE LOSS GATE")
    print("=" * 70)

    # Default: 3 losses → skip 2
    consec_default = simulate_consec_loss_gate(all_trades)
    print(f"\n  Default: skip {consec_default.get('gate_config', {}).get('skip_count', 2)} "
          f"trades after {consec_default.get('gate_config', {}).get('n_losses', 3)} consecutive losses")
    _print_gate_comparison(consec_default, risk_usd)
    print(f"\n  Gate triggered: {consec_default.get('times_triggered', 0)} times")

    # Sweep
    print()
    print("-" * 70)
    print("Consecutive Loss Gate — Parameter Sweep")
    print("-" * 70)

    consec_sweep = sweep_consec_loss_gate(all_trades)
    print(f"\n  {'Losses':>7} {'Skip':>5} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
          f"{'Sharpe':>8} {'Calmar':>8} {'MaxDD':>10} {'Skip':>5} {'Trig':>5}")
    print(f"  {'-'*7} {'-'*5} {'-'*7} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*10} {'-'*5} {'-'*5}")
    for r in consec_sweep[:20]:
        print(f"  {r['n_losses']:>7} {r['skip_count']:>5} "
              f"{r['trades']:>7} {r['win_rate']:>5.1%} {r['total_r']:>8.1f} "
              f"{r['sharpe']:>8.3f} {r['calmar']:>8.3f} "
              f"${r['max_dd_usd']:>9,.0f} {r['skipped']:>5} {r['times_triggered']:>5}")

    # ── Per-session consecutive loss gate ────────────────────────────
    print()
    print("-" * 70)
    print("Consecutive Loss Gate — Per Session")
    print("-" * 70)

    for sess_name in ["NY", "Asia"]:
        sess_trades = [t for t in all_trades if t.session == sess_name]
        if not sess_trades:
            continue

        sess_filled = [t for t in sess_trades if t.exit_type != EXIT_NO_FILL]
        sess_baseline = compute_metrics(sess_trades)

        print(f"\n  --- {sess_name} ({len(sess_filled)} trades) ---")
        print(f"    Baseline:      {sess_baseline['total_pnl_usd']/risk_usd:.1f}R, "
              f"WR={sess_baseline['win_rate']:.1%}, "
              f"Sharpe={sess_baseline['sharpe_ratio']:.3f}")

        # Best from sweep for this session
        sess_sweep = sweep_consec_loss_gate(sess_trades)
        if sess_sweep:
            best = sess_sweep[0]
            print(f"    Best gate:     {best['total_r']:.1f}R, "
                  f"WR={best['win_rate']:.1%}, "
                  f"Sharpe={best['sharpe']:.3f}, "
                  f"n_losses={best['n_losses']}, skip={best['skip_count']}, "
                  f"skip={best['skipped']}")

    # ── Save best results for frontend ───────────────────────────────
    if args.save:
        _save_results(all_trades, instrument, trend_with, trend_counter,
                      consec_sweep, risk_usd)

    print()
    print("=" * 70)


def _save_results(all_trades, instrument, trend_with, trend_counter,
                  consec_sweep, risk_usd):
    """Save gated results for frontend comparison."""
    base_config = _build_base_config(instrument)

    # Trend with-trend
    trend_gated = trend_with.get("gated_metrics", {})
    if trend_gated.get("total_trades", 0) > 0:
        filled = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]
        trend_trades = []
        for t in filled:
            close = t.prev_daily_close
            sma = t.daily_sma20
            if close <= 0 or sma <= 0 or np.isnan(close) or np.isnan(sma):
                trend_trades.append(t)
                continue
            is_with = (t.direction == 1 and close > sma) or (t.direction == -1 and close < sma)
            if is_with:
                trend_trades.append(t)

        config = dict(base_config)
        config["trend_gate"] = "with_trend (prev close vs 20-SMA)"
        result = _build_result(
            trend_trades, config,
            name="NY+Asia Combined (Trend Gate)",
            notes="Only take trades aligned with daily trend (prev close vs 20-day SMA).",
        )
        rid = save_backtest_result(result)
        m = result["summary"]
        print(f"\n  Saved Trend Gate: {m['total_trades']} trades, "
              f"{m['total_pnl_usd']/risk_usd:.1f}R, Sharpe {m['sharpe_ratio']:.3f}")
        print(f"    ID: {rid}")

    # Consecutive loss gate (best by Sharpe)
    if consec_sweep:
        best = consec_sweep[0]
        cfg = ConsecLossGateConfig(n_losses=best["n_losses"], skip_count=best["skip_count"])
        r = simulate_consec_loss_gate(all_trades, cfg)
        gated = r.get("gated_metrics", {})
        if gated.get("total_trades", 0) > 0:
            # Replay to get the actual trade list
            filled = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]
            consec_trades = []
            consec_losses = 0
            skip_remaining = 0
            for t in filled:
                if skip_remaining > 0:
                    skip_remaining -= 1
                    continue
                consec_trades.append(t)
                if t.pnl_usd < 0:
                    consec_losses += 1
                else:
                    consec_losses = 0
                if consec_losses >= cfg.n_losses:
                    skip_remaining = cfg.skip_count
                    consec_losses = 0

            config = dict(base_config)
            config["consec_loss_gate_n"] = cfg.n_losses
            config["consec_loss_gate_skip"] = cfg.skip_count
            result = _build_result(
                consec_trades, config,
                name=f"NY+Asia Combined (Consec Loss {cfg.n_losses}L-{cfg.skip_count}S)",
                notes=f"Skip {cfg.skip_count} trades after {cfg.n_losses} consecutive losses.",
            )
            rid = save_backtest_result(result)
            m = result["summary"]
            print(f"\n  Saved Consec Loss Gate: {m['total_trades']} trades, "
                  f"{m['total_pnl_usd']/risk_usd:.1f}R, Sharpe {m['sharpe_ratio']:.3f}")
            print(f"    ID: {rid}")


def _build_base_config(instrument):
    return {
        "instrument": instrument.symbol,
        "point_value": instrument.point_value,
        "risk_usd": 5000.0,
        "atr_length": 14,
        "strategy": "continuation",
        "ny_rr": PROD_NY_GLOBALS["rr"],
        "ny_tp1_ratio": PROD_NY_GLOBALS["tp1_ratio"],
        "ny_be_offset_ticks": PROD_NY_GLOBALS["be_offset_ticks"],
        "ny_stop_atr_pct": PROD_NY_SESSION.stop_atr_pct,
        "ny_min_gap_atr_pct": PROD_NY_SESSION.min_gap_atr_pct,
        "ny_max_gap_atr_pct": PROD_NY_SESSION.max_gap_atr_pct,
        "ny_orb_window": f"{PROD_NY_SESSION.orb_start}-{PROD_NY_SESSION.orb_end}",
        "ny_entry_window": f"{PROD_NY_SESSION.entry_start}-{PROD_NY_SESSION.entry_end}",
        "ny_flat_window": f"{PROD_NY_SESSION.flat_start}-{PROD_NY_SESSION.flat_end}",
        "asia_rr": PROD_ASIA_GLOBALS["rr"],
        "asia_tp1_ratio": PROD_ASIA_GLOBALS["tp1_ratio"],
        "asia_be_offset_ticks": PROD_ASIA_GLOBALS["be_offset_ticks"],
        "asia_stop_atr_pct": PROD_ASIA_SESSION.stop_atr_pct,
        "asia_min_gap_atr_pct": PROD_ASIA_SESSION.min_gap_atr_pct,
        "asia_max_gap_atr_pct": PROD_ASIA_SESSION.max_gap_atr_pct,
        "asia_orb_window": f"{PROD_ASIA_SESSION.orb_start}-{PROD_ASIA_SESSION.orb_end}",
        "asia_entry_window": f"{PROD_ASIA_SESSION.entry_start}-{PROD_ASIA_SESSION.entry_end}",
        "asia_flat_window": f"{PROD_ASIA_SESSION.flat_start}-{PROD_ASIA_SESSION.flat_end}",
    }


def _build_result(trades, config, name, notes):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    metrics = compute_metrics(trades)

    equity_curve = []
    cumulative = 0.0
    for t in filled:
        cumulative += t.pnl_usd
        equity_curve.append({
            "date": t.date,
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t.pnl_usd, 2),
        })

    trades_list = [
        {
            "date": t.date,
            "session": t.session,
            "direction": "long" if t.direction == 1 else "short",
            "entry_price": round(t.entry_price, 4),
            "stop_price": round(t.stop_price, 4),
            "tp1_price": round(t.tp1_price, 4),
            "tp2_price": round(t.tp2_price, 4),
            "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
            "pnl_usd": round(t.pnl_usd, 2),
            "pnl_points": round(t.pnl_points, 4),
            "r_multiple": round(t.r_multiple, 3),
            "qty": t.qty,
            "gap_size": round(t.gap_size, 4),
            "risk_points": round(t.risk_points, 4),
            "daily_atr": round(t.daily_atr, 4),
            "orb_range": round(t.orb_range, 4),
        }
        for t in trades
    ]

    return {
        "name": name,
        "notes": notes,
        "config": config,
        "summary": metrics,
        "equity_curve": equity_curve,
        "trades": trades_list,
    }


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
