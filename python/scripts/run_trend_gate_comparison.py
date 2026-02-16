#!/usr/bin/env python3
"""Compare trend gate methods: SMA, EMA, ROC, ADX, Donchian, Dual EMA.

Computes indicator arrays from the DataFrame at analysis time (not stored on
TradeResult), looks up values at each trade's signal_bar, and runs the
generalized indicator trend gate for each method+period combination.

Usage:
    python scripts/run_trend_gate_comparison.py
    python scripts/run_trend_gate_comparison.py --data NQ_5m.csv --start 2024-01-01 --end 2026-01-01
    python scripts/run_trend_gate_comparison.py --data ES_5m.csv --instrument ES --sessions NY,Asia,LDN
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np

from orb_continuation.config import (
    production_config,
    default_config,
    LDN_SESSION,
)
from core.config import with_overrides
from core.data.instruments import get_instrument
from core.data.loader import load_5m_data
from core.engine.simulator import run_backtest, EXIT_NO_FILL, TradeResult
from core.results.metrics import compute_metrics
from core.signals.daily_atr import (
    compute_daily_sma,
    compute_daily_ema,
    compute_daily_roc,
    compute_daily_adx,
    compute_daily_donchian_mid,
)
from core.analysis.pre_trade_gates import simulate_indicator_trend_gate


# ---------------------------------------------------------------------------
# Indicator definitions
# ---------------------------------------------------------------------------

def _build_indicator_configs():
    """Return list of (label, compute_fn, gate_kwargs) tuples."""
    configs = []

    # SMA
    for p in (10, 20, 50):
        configs.append({
            "label": f"SMA({p})",
            "indicator": "sma",
            "period": p,
            "method": "close_vs_indicator",
            "mode": "with_trend",
        })

    # EMA
    for p in (10, 20, 50):
        configs.append({
            "label": f"EMA({p})",
            "indicator": "ema",
            "period": p,
            "method": "close_vs_indicator",
            "mode": "with_trend",
        })

    # ROC
    for p in (5, 10, 20):
        configs.append({
            "label": f"ROC({p})",
            "indicator": "roc",
            "period": p,
            "method": "sign",
            "mode": "with_trend",
        })

    # ADX with threshold
    for thresh in (25, 30, 35):
        configs.append({
            "label": f"ADX(14)>{thresh}",
            "indicator": "adx",
            "period": 14,
            "method": "threshold",
            "threshold": float(thresh),
            "mode": "with_trend",
        })

    # Donchian Mid
    for p in (10, 20, 50):
        configs.append({
            "label": f"Donchian({p})",
            "indicator": "donchian",
            "period": p,
            "method": "close_vs_indicator",
            "mode": "with_trend",
        })

    # Dual EMA (crossover: fast vs slow)
    for fast, slow in [(10, 20), (10, 50), (20, 50)]:
        configs.append({
            "label": f"EMA({fast}/{slow})",
            "indicator": "dual_ema",
            "fast_period": fast,
            "slow_period": slow,
            "method": "crossover",
            "mode": "with_trend",
        })

    return configs


def _compute_indicator_arrays(df, indicator_cfg):
    """Compute (indicator_5m, close_5m) arrays for a given config.

    For most indicators, returns (prev_close, indicator_values).
    For crossover (dual EMA), returns (fast_ema, slow_ema) as
    (indicator, prev_close) in the gate's crossover convention.
    """
    ind_type = indicator_cfg["indicator"]

    if ind_type == "sma":
        prev_close, sma = compute_daily_sma(df, length=indicator_cfg["period"])
        return sma, prev_close

    elif ind_type == "ema":
        prev_close, ema = compute_daily_ema(df, length=indicator_cfg["period"])
        return ema, prev_close

    elif ind_type == "roc":
        prev_close, roc = compute_daily_roc(df, length=indicator_cfg["period"])
        return roc, prev_close

    elif ind_type == "adx":
        prev_close, adx, di_diff = compute_daily_adx(df, length=indicator_cfg["period"])
        return adx, prev_close

    elif ind_type == "donchian":
        prev_close, mid = compute_daily_donchian_mid(df, length=indicator_cfg["period"])
        return mid, prev_close

    elif ind_type == "dual_ema":
        _, fast_ema = compute_daily_ema(df, length=indicator_cfg["fast_period"])
        _, slow_ema = compute_daily_ema(df, length=indicator_cfg["slow_period"])
        # crossover convention: indicator=fast, prev_close=slow
        return fast_ema, slow_ema

    else:
        raise ValueError(f"Unknown indicator type: {ind_type}")


def _lookup_at_signal_bars(arr_5m, filled_trades):
    """Look up 5m array values at each filled trade's signal_bar index."""
    signal_bars = np.array([t.signal_bar for t in filled_trades], dtype=np.int64)
    # Clip to valid range
    valid = (signal_bars >= 0) & (signal_bars < len(arr_5m))
    result = np.full(len(filled_trades), np.nan)
    result[valid] = arr_5m[signal_bars[valid]]
    return result


def _get_session_configs(instrument, session_names):
    """Build per-session StrategyConfig list supporting NY, Asia, LDN."""
    prod_configs = production_config(instrument)
    config_map = {cfg.sessions[0].name: cfg for cfg in prod_configs}

    # Add LDN if requested (uses default params since not optimized)
    if "LDN" in session_names and "LDN" not in config_map:
        base = default_config(instrument)
        ldn_cfg = with_overrides(base, sessions=(LDN_SESSION,))
        config_map["LDN"] = ldn_cfg

    configs = []
    for name in session_names:
        if name in config_map:
            configs.append(config_map[name])
        else:
            print(f"  Warning: unknown session '{name}', skipping")
    return configs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compare trend gate methods")
    parser.add_argument("--data", default="NQ_5m.csv", help="Data file")
    parser.add_argument("--start", default="2016-01-01", help="Start date")
    parser.add_argument("--end", default="2026-01-01", help="End date")
    parser.add_argument("--instrument", default="NQ", help="Instrument")
    parser.add_argument("--sessions", default="NY,Asia", help="Sessions (comma-separated)")
    args = parser.parse_args()

    instrument = get_instrument(args.instrument)
    session_names = [s.strip() for s in args.sessions.split(",")]
    risk_usd = 5000.0

    # ── Load data ────────────────────────────────────────────────────
    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    # ── Run backtests per session ────────────────────────────────────
    configs = _get_session_configs(instrument, session_names)
    all_trades: list[TradeResult] = []
    for config in configs:
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
    print()
    print("=" * 80)
    print("BASELINE (No Gate)")
    print("=" * 80)
    _print_metrics(baseline, risk_usd)

    # ── Compare all indicator methods ────────────────────────────────
    print()
    print("=" * 80)
    print("TREND GATE COMPARISON (with_trend mode)")
    print("=" * 80)

    indicator_configs = _build_indicator_configs()
    results = []

    t0 = time.time()
    for icfg in indicator_configs:
        indicator_5m, close_5m = _compute_indicator_arrays(df, icfg)
        indicator_at_signal = _lookup_at_signal_bars(indicator_5m, filled)
        close_at_signal = _lookup_at_signal_bars(close_5m, filled)

        r = simulate_indicator_trend_gate(
            all_trades,
            indicator_at_signal=indicator_at_signal,
            prev_close_at_signal=close_at_signal,
            mode=icfg["mode"],
            method=icfg["method"],
            threshold=icfg.get("threshold", 0.0),
            label=icfg["label"],
        )

        gated = r.get("gated_metrics", {})
        if gated.get("total_trades", 0) > 0:
            results.append({
                "label": icfg["label"],
                "trades": gated["total_trades"],
                "win_rate": gated["win_rate"],
                "total_r": gated["total_pnl_usd"] / risk_usd,
                "sharpe": gated["sharpe_ratio"],
                "calmar": gated.get("calmar_ratio", 0),
                "max_dd_usd": gated["max_drawdown_usd"],
                "max_dd_r": gated["max_drawdown_usd"] / risk_usd,
                "pf": gated["profit_factor"],
                "skipped": r["skipped_count"],
                "method": icfg["method"],
                "_config": icfg,
            })

    print(f"  Computed {len(indicator_configs)} indicator variants in {time.time() - t0:.1f}s")

    # Sort by Sharpe descending
    results.sort(key=lambda x: x["sharpe"], reverse=True)

    # Print comparison table
    print()
    b_r = baseline["total_pnl_usd"] / risk_usd
    b_sharpe = baseline["sharpe_ratio"]
    print(f"  Baseline: {baseline['total_trades']} trades, {b_r:.1f}R, "
          f"Sharpe {b_sharpe:.3f}, MaxDD ${baseline['max_drawdown_usd']:,.0f}")
    print()
    print(f"  {'Rank':>4} {'Method':<16} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
          f"{'Sharpe':>8} {'dSharpe':>8} {'Calmar':>8} {'MaxDD(R)':>9} {'PF':>6} {'Skip':>5}")
    print(f"  {'─'*4} {'─'*16} {'─'*7} {'─'*6} {'─'*8} "
          f"{'─'*8} {'─'*8} {'─'*8} {'─'*9} {'─'*6} {'─'*5}")
    for rank, r in enumerate(results, 1):
        d_sharpe = r["sharpe"] - b_sharpe
        print(f"  {rank:>4} {r['label']:<16} {r['trades']:>7} {r['win_rate']:>5.1%} "
              f"{r['total_r']:>8.1f} {r['sharpe']:>8.3f} {d_sharpe:>+8.3f} "
              f"{r['calmar']:>8.3f} {r['max_dd_r']:>9.1f} {r['pf']:>6.2f} {r['skipped']:>5}")

    # ── Counter-trend comparison for top 3 ───────────────────────────
    if len(results) >= 3:
        print()
        print("=" * 80)
        print("COUNTER-TREND COMPARISON (top 3 methods)")
        print("=" * 80)

        for r in results[:3]:
            icfg = dict(r["_config"])
            icfg["mode"] = "counter_trend"

            indicator_5m, close_5m = _compute_indicator_arrays(df, icfg)
            indicator_at_signal = _lookup_at_signal_bars(indicator_5m, filled)
            close_at_signal = _lookup_at_signal_bars(close_5m, filled)

            cr = simulate_indicator_trend_gate(
                all_trades,
                indicator_at_signal=indicator_at_signal,
                prev_close_at_signal=close_at_signal,
                mode="counter_trend",
                method=icfg["method"],
                threshold=icfg.get("threshold", 0.0),
                label=icfg["label"],
            )
            cg = cr.get("gated_metrics", {})
            if cg.get("total_trades", 0) > 0:
                ct_r = cg["total_pnl_usd"] / risk_usd
                print(f"\n  {r['label']}")
                print(f"    With-trend:    {r['trades']} trades, {r['total_r']:.1f}R, "
                      f"Sharpe {r['sharpe']:.3f}, MaxDD {r['max_dd_r']:.1f}R")
                print(f"    Counter-trend: {cg['total_trades']} trades, {ct_r:.1f}R, "
                      f"Sharpe {cg['sharpe_ratio']:.3f}, MaxDD {cg['max_drawdown_usd']/risk_usd:.1f}R")

    # ── Per-session breakdown for top 3 ──────────────────────────────
    if len(results) >= 3:
        print()
        print("=" * 80)
        print("PER-SESSION BREAKDOWN (top 3 methods)")
        print("=" * 80)

        for r in results[:3]:
            icfg = r["_config"]
            print(f"\n  --- {r['label']} ---")

            indicator_5m, close_5m = _compute_indicator_arrays(df, icfg)

            for sess_name in session_names:
                sess_trades = [t for t in all_trades if t.session == sess_name]
                sess_filled = [t for t in sess_trades if t.exit_type != EXIT_NO_FILL]
                if not sess_filled:
                    continue

                sess_baseline = compute_metrics(sess_trades)
                ind_at = _lookup_at_signal_bars(indicator_5m, sess_filled)
                close_at = _lookup_at_signal_bars(close_5m, sess_filled)

                sr = simulate_indicator_trend_gate(
                    sess_trades,
                    indicator_at_signal=ind_at,
                    prev_close_at_signal=close_at,
                    mode=icfg["mode"],
                    method=icfg["method"],
                    threshold=icfg.get("threshold", 0.0),
                    label=icfg["label"],
                )
                sg = sr.get("gated_metrics", {})
                if sg.get("total_trades", 0) > 0:
                    sb_r = sess_baseline["total_pnl_usd"] / risk_usd
                    sg_r = sg["total_pnl_usd"] / risk_usd
                    print(f"    {sess_name:6s} base: {len(sess_filled)} trades, {sb_r:.1f}R, "
                          f"Sharpe {sess_baseline['sharpe_ratio']:.3f}  |  "
                          f"gated: {sg['total_trades']} trades, {sg_r:.1f}R, "
                          f"Sharpe {sg['sharpe_ratio']:.3f}, skip={sr['skipped_count']}")

    # ── Deep sweep on best method ────────────────────────────────────
    if results:
        best = results[0]
        icfg = best["_config"]
        ind_type = icfg["indicator"]

        print()
        print("=" * 80)
        print(f"DEEP SWEEP: {best['label']} (best by Sharpe)")
        print("=" * 80)

        if ind_type in ("sma", "ema", "donchian"):
            _deep_sweep_period(df, all_trades, filled, ind_type, icfg["method"], risk_usd, b_sharpe)
        elif ind_type == "roc":
            _deep_sweep_period(df, all_trades, filled, "roc", "sign", risk_usd, b_sharpe)
        elif ind_type == "adx":
            _deep_sweep_adx(df, all_trades, filled, risk_usd, b_sharpe)
        elif ind_type == "dual_ema":
            _deep_sweep_dual_ema(df, all_trades, filled, risk_usd, b_sharpe)

    print()
    print("=" * 80)
    print("Done.")


def _deep_sweep_period(df, all_trades, filled, ind_type, method, risk_usd, b_sharpe):
    """Fine-grained period sweep for single-period indicators."""
    periods = list(range(5, 61, 5))
    sweep_results = []

    for p in periods:
        cfg = {"indicator": ind_type, "period": p, "method": method, "mode": "with_trend"}
        indicator_5m, close_5m = _compute_indicator_arrays(df, cfg)
        ind_at = _lookup_at_signal_bars(indicator_5m, filled)
        close_at = _lookup_at_signal_bars(close_5m, filled)

        r = simulate_indicator_trend_gate(
            all_trades,
            indicator_at_signal=ind_at,
            prev_close_at_signal=close_at,
            mode="with_trend",
            method=method,
            label=f"{ind_type.upper()}({p})",
        )
        gated = r.get("gated_metrics", {})
        if gated.get("total_trades", 0) > 0:
            sweep_results.append({
                "period": p,
                "trades": gated["total_trades"],
                "win_rate": gated["win_rate"],
                "total_r": gated["total_pnl_usd"] / risk_usd,
                "sharpe": gated["sharpe_ratio"],
                "calmar": gated.get("calmar_ratio", 0),
                "max_dd_r": gated["max_drawdown_usd"] / risk_usd,
                "pf": gated["profit_factor"],
                "skipped": r["skipped_count"],
            })

    sweep_results.sort(key=lambda x: x["sharpe"], reverse=True)

    print(f"\n  {ind_type.upper()} period sweep (5 to 60, step 5)")
    print(f"\n  {'Period':>7} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
          f"{'Sharpe':>8} {'dSharpe':>8} {'Calmar':>8} {'MaxDD(R)':>9} {'PF':>6}")
    print(f"  {'─'*7} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*9} {'─'*6}")
    for r in sweep_results:
        d_sharpe = r["sharpe"] - b_sharpe
        print(f"  {r['period']:>7} {r['trades']:>7} {r['win_rate']:>5.1%} "
              f"{r['total_r']:>8.1f} {r['sharpe']:>8.3f} {d_sharpe:>+8.3f} "
              f"{r['calmar']:>8.3f} {r['max_dd_r']:>9.1f} {r['pf']:>6.2f}")


def _deep_sweep_adx(df, all_trades, filled, risk_usd, b_sharpe):
    """Fine-grained ADX threshold sweep."""
    thresholds = list(range(15, 46, 5))
    sweep_results = []

    for thresh in thresholds:
        cfg = {"indicator": "adx", "period": 14, "method": "threshold",
               "threshold": float(thresh), "mode": "with_trend"}
        indicator_5m, close_5m = _compute_indicator_arrays(df, cfg)
        ind_at = _lookup_at_signal_bars(indicator_5m, filled)
        close_at = _lookup_at_signal_bars(close_5m, filled)

        r = simulate_indicator_trend_gate(
            all_trades,
            indicator_at_signal=ind_at,
            prev_close_at_signal=close_at,
            mode="with_trend",
            method="threshold",
            threshold=float(thresh),
            label=f"ADX(14)>{thresh}",
        )
        gated = r.get("gated_metrics", {})
        if gated.get("total_trades", 0) > 0:
            sweep_results.append({
                "threshold": thresh,
                "trades": gated["total_trades"],
                "win_rate": gated["win_rate"],
                "total_r": gated["total_pnl_usd"] / risk_usd,
                "sharpe": gated["sharpe_ratio"],
                "calmar": gated.get("calmar_ratio", 0),
                "max_dd_r": gated["max_drawdown_usd"] / risk_usd,
                "pf": gated["profit_factor"],
                "skipped": r["skipped_count"],
            })

    sweep_results.sort(key=lambda x: x["sharpe"], reverse=True)

    print(f"\n  ADX(14) threshold sweep (15 to 45, step 5)")
    print(f"\n  {'Thresh':>7} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
          f"{'Sharpe':>8} {'dSharpe':>8} {'Calmar':>8} {'MaxDD(R)':>9} {'PF':>6}")
    print(f"  {'─'*7} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*9} {'─'*6}")
    for r in sweep_results:
        d_sharpe = r["sharpe"] - b_sharpe
        print(f"  {r['threshold']:>7} {r['trades']:>7} {r['win_rate']:>5.1%} "
              f"{r['total_r']:>8.1f} {r['sharpe']:>8.3f} {d_sharpe:>+8.3f} "
              f"{r['calmar']:>8.3f} {r['max_dd_r']:>9.1f} {r['pf']:>6.2f}")


def _deep_sweep_dual_ema(df, all_trades, filled, risk_usd, b_sharpe):
    """Fine-grained dual EMA crossover sweep."""
    pairs = [(5, 10), (5, 20), (5, 50), (10, 20), (10, 30), (10, 40), (10, 50),
             (15, 30), (15, 50), (20, 40), (20, 50), (20, 60), (30, 60)]
    sweep_results = []

    for fast, slow in pairs:
        cfg = {"indicator": "dual_ema", "fast_period": fast, "slow_period": slow,
               "method": "crossover", "mode": "with_trend"}
        indicator_5m, close_5m = _compute_indicator_arrays(df, cfg)
        ind_at = _lookup_at_signal_bars(indicator_5m, filled)
        close_at = _lookup_at_signal_bars(close_5m, filled)

        r = simulate_indicator_trend_gate(
            all_trades,
            indicator_at_signal=ind_at,
            prev_close_at_signal=close_at,
            mode="with_trend",
            method="crossover",
            label=f"EMA({fast}/{slow})",
        )
        gated = r.get("gated_metrics", {})
        if gated.get("total_trades", 0) > 0:
            sweep_results.append({
                "pair": f"{fast}/{slow}",
                "trades": gated["total_trades"],
                "win_rate": gated["win_rate"],
                "total_r": gated["total_pnl_usd"] / risk_usd,
                "sharpe": gated["sharpe_ratio"],
                "calmar": gated.get("calmar_ratio", 0),
                "max_dd_r": gated["max_drawdown_usd"] / risk_usd,
                "pf": gated["profit_factor"],
                "skipped": r["skipped_count"],
            })

    sweep_results.sort(key=lambda x: x["sharpe"], reverse=True)

    print(f"\n  Dual EMA crossover sweep")
    print(f"\n  {'Pair':>9} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
          f"{'Sharpe':>8} {'dSharpe':>8} {'Calmar':>8} {'MaxDD(R)':>9} {'PF':>6}")
    print(f"  {'─'*9} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*9} {'─'*6}")
    for r in sweep_results:
        d_sharpe = r["sharpe"] - b_sharpe
        print(f"  {r['pair']:>9} {r['trades']:>7} {r['win_rate']:>5.1%} "
              f"{r['total_r']:>8.1f} {r['sharpe']:>8.3f} {d_sharpe:>+8.3f} "
              f"{r['calmar']:>8.3f} {r['max_dd_r']:>9.1f} {r['pf']:>6.2f}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_metrics(m: dict, risk_usd: float):
    total_r = m["total_pnl_usd"] / risk_usd
    print(f"  Trades:     {m['total_trades']}")
    print(f"  Win Rate:   {m['win_rate']:.1%}")
    print(f"  Total PnL:  {total_r:.1f}R (${m['total_pnl_usd']:,.0f})")
    print(f"  Sharpe:     {m['sharpe_ratio']:.3f}")
    print(f"  Sortino:    {m['sortino_ratio']:.3f}")
    print(f"  Calmar:     {m['calmar_ratio']:.3f}")
    print(f"  Max DD:     ${m['max_drawdown_usd']:,.0f} ({m['max_drawdown_usd']/risk_usd:.1f}R)")
    print(f"  PF:         {m['profit_factor']:.2f}")


if __name__ == "__main__":
    main()
