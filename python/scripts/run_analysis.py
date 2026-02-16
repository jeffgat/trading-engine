#!/usr/bin/env python3
"""Run volatility regime analysis and rolling performance gate on backtest results.

Investigates two hypotheses from TO_TEST.md:
1. Does the strategy perform differently across volatility regimes?
2. Can a CTA-style performance gate (pause when trailing Sharpe < 0) improve results?

Usage:
    # Realized vol only (no external deps):
    python scripts/run_analysis.py --data NQ_5m.csv --start 2017-01-01 --end 2026-01-01

    # With VIX overlay (requires yfinance):
    python scripts/run_analysis.py --data NQ_5m.csv --start 2017-01-01 --end 2026-01-01 --vix

    # Custom gate parameters:
    python scripts/run_analysis.py --data NQ_5m.csv --start 2017-01-01 --end 2026-01-01 \\
        --gate-window 60 --gate-threshold 0.0 --gate-consecutive 5

    # Load a saved result instead of re-running backtest:
    python scripts/run_analysis.py --result-id 2026-02-15_120000_NQ_ASIA+NY
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_continuation.config import (
    default_config, production_config,
    PROD_NY_SESSION, PROD_ASIA_SESSION,
    PROD_NY_GLOBALS, PROD_ASIA_GLOBALS,
)
from core.config import with_overrides
from core.data.instruments import get_instrument
from core.data.loader import load_5m_data
from core.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from core.results.metrics import compute_metrics
from core.results.export import load_backtest_result

from core.analysis.volatility import (
    compute_realized_vol, load_vix_data,
    tag_trades_with_volatility, compute_regime_breakdown,
    RV_REGIME_ORDER, VIX_REGIME_ORDER,
)
from core.analysis.rolling import compute_rolling_metrics
from core.analysis.performance_gate import (
    GateConfig, simulate_performance_gate,
)

# Map session names to production configs
_PROD_SESSION_MAP = {
    "NY": (PROD_NY_SESSION, PROD_NY_GLOBALS),
    "ASIA": (PROD_ASIA_SESSION, PROD_ASIA_GLOBALS),
}


def main():
    parser = argparse.ArgumentParser(
        description="Volatility regime analysis + rolling performance gate"
    )

    # Data source (either run backtest or load saved result)
    parser.add_argument("--data", default="NQ_5m.csv", help="Data file for backtest")
    parser.add_argument("--start", default="2017-01-01", help="Start date")
    parser.add_argument("--end", default="2026-01-01", help="End date")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol")
    parser.add_argument("--sessions", default="NY,Asia", help="Sessions to backtest (comma-separated)")
    parser.add_argument("--result-id", default=None, help="Load saved result instead of running backtest")

    # Volatility options
    parser.add_argument("--vix", action="store_true", help="Include VIX data (requires yfinance)")
    parser.add_argument("--rv-window", type=int, default=20, help="Realized vol rolling window (days)")

    # Rolling metrics
    parser.add_argument("--rolling-windows", default="20,40,60",
                        help="Comma-separated rolling window sizes (trade count)")

    # Performance gate
    parser.add_argument("--gate-window", type=int, default=60, help="Gate rolling window (trade count)")
    parser.add_argument("--gate-threshold", type=float, default=0.0, help="Gate threshold (Sharpe)")
    parser.add_argument("--gate-consecutive", type=int, default=5,
                        help="Consecutive trades below threshold to close gate")

    args = parser.parse_args()

    # ── Get trade data ───────────────────────────────────────────────
    if args.result_id:
        print(f"Loading saved result: {args.result_id}")
        result = load_backtest_result(args.result_id)
        if result is None:
            print(f"  ERROR: Result '{args.result_id}' not found")
            sys.exit(1)
        trades_list = result.get("trades", [])
        df = None  # No OHLCV data available from saved results
        print(f"  {len(trades_list)} trades loaded")
    else:
        df, trades_list = _run_backtest(args)

    filled_trades = [t for t in trades_list if t.get("exit_type") != "no_fill"]
    print(f"\nTotal filled trades for analysis: {len(filled_trades)}")

    # ── Volatility Regime Analysis ───────────────────────────────────
    print()
    print("=" * 65)
    print("VOLATILITY REGIME ANALYSIS")
    print("=" * 65)

    # Realized volatility
    rv_series = None
    if df is not None:
        print(f"\nComputing {args.rv_window}-day realized volatility from price data...")
        rv_series = compute_realized_vol(df, window=args.rv_window)
        rv_clean = rv_series.dropna()
        print(f"  Range: {rv_clean.min():.1%} to {rv_clean.max():.1%}")
        print(f"  Median: {rv_clean.median():.1%}, Mean: {rv_clean.mean():.1%}")
    elif not args.result_id:
        print("\n  (Realized vol requires OHLCV data — skipping)")

    # VIX data
    vix_series = None
    if args.vix:
        print("\nLoading VIX data...")
        try:
            vix_series = load_vix_data(start=args.start, end=args.end)
            print(f"  {len(vix_series)} daily VIX values loaded")
            print(f"  Range: {vix_series.min():.1f} to {vix_series.max():.1f}")
            print(f"  Median: {vix_series.median():.1f}")
        except ImportError as e:
            print(f"  WARNING: {e}")
        except Exception as e:
            print(f"  ERROR loading VIX data: {e}")

    # Tag trades
    if rv_series is not None or vix_series is not None:
        tag_trades_with_volatility(trades_list, vix_series=vix_series, rv_series=rv_series)

    # Realized vol regime breakdown
    if rv_series is not None:
        rv_breakdown = compute_regime_breakdown(trades_list, regime_key="rv_regime")
        if rv_breakdown:
            _print_regime_table("Realized Volatility Regime", rv_breakdown, RV_REGIME_ORDER)
        else:
            print("\n  No trades tagged with realized vol regime")

    # VIX regime breakdown
    if vix_series is not None:
        vix_breakdown = compute_regime_breakdown(trades_list, regime_key="vix_regime")
        if vix_breakdown:
            _print_regime_table("VIX Regime", vix_breakdown, VIX_REGIME_ORDER)
        else:
            print("\n  No trades tagged with VIX regime")

    # ── Rolling Performance Metrics ──────────────────────────────────
    print()
    print("=" * 65)
    print("ROLLING PERFORMANCE METRICS")
    print("=" * 65)

    windows = [int(w) for w in args.rolling_windows.split(",")]
    rolling = compute_rolling_metrics(trades_list, windows=windows)

    if rolling:
        _print_rolling_summary(rolling, windows)

    # ── Performance Gate Simulation ──────────────────────────────────
    print()
    print("=" * 65)
    print("PERFORMANCE GATE SIMULATION")
    print("=" * 65)

    gate_config = GateConfig(
        window=args.gate_window,
        threshold=args.gate_threshold,
        consecutive_trades=args.gate_consecutive,
    )

    print(f"\n  Gate: Skip trades when {gate_config.window}-trade Sharpe < "
          f"{gate_config.threshold} for {gate_config.consecutive_trades}+ consecutive trades")

    gate_result = simulate_performance_gate(trades_list, gate_config)
    _print_gate_comparison(gate_result)

    print()
    print("=" * 65)


def _run_backtest(args):
    """Run backtest with optimized per-session params."""
    instrument = get_instrument(args.instrument)
    sessions_requested = [s.strip() for s in args.sessions.split(",")]

    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    all_trades = []

    for sess_name in sessions_requested:
        sess_upper = sess_name.upper()
        if sess_upper not in _PROD_SESSION_MAP:
            print(f"  WARNING: Unknown session '{sess_name}', skipping")
            continue

        session, globals_ = _PROD_SESSION_MAP[sess_upper]
        config = default_config(instrument)
        config = with_overrides(config, sessions=(session,), **globals_)

        print(f"\n  Running {sess_upper} backtest...")
        t0 = time.time()
        trades = run_backtest(df, config, start_date=args.start)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"    {len(trades)} signals, {len(filled)} filled [{time.time() - t0:.1f}s]")

        metrics = compute_metrics(trades)
        print(f"    Win rate: {metrics['win_rate']:.1%}, "
              f"Sharpe: {metrics['sharpe_ratio']:.3f}, "
              f"PnL: ${metrics['total_pnl_usd']:,.0f}")

        all_trades.extend(trades)

    # Sort chronologically and convert to trade dicts
    all_trades.sort(key=lambda t: t.date)
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
        }
        for t in all_trades
    ]

    return df, trades_list


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _print_regime_table(title: str, breakdown: dict, regime_order: list[str]):
    """Print a regime breakdown table."""
    print(f"\n  {title} Breakdown:")
    print(f"  {'Regime':<12} {'Trades':>7} {'Win Rate':>9} {'Avg R':>8} "
          f"{'Sharpe':>8} {'PnL ($)':>10} {'PnL (R)':>8}")
    print(f"  {'-' * 12} {'-' * 7} {'-' * 9} {'-' * 8} {'-' * 8} {'-' * 10} {'-' * 8}")

    for regime in regime_order:
        if regime not in breakdown:
            continue
        m = breakdown[regime]
        total_r = sum(1 for _ in range(m["n_trades"]))  # just use n_trades
        pnl_r = m["total_pnl_usd"] / 5000 if m["total_pnl_usd"] else 0
        print(f"  {regime:<12} {m['n_trades']:>7} {m['win_rate']:>8.1%} "
              f"{m['avg_r']:>8.3f} {m['sharpe_ratio']:>8.3f} "
              f"{m['total_pnl_usd']:>10,.0f} {pnl_r:>7.1f}R")

    if "overall" in breakdown:
        m = breakdown["overall"]
        pnl_r = m["total_pnl_usd"] / 5000 if m["total_pnl_usd"] else 0
        print(f"  {'─' * 12} {'─' * 7} {'─' * 9} {'─' * 8} {'─' * 8} {'─' * 10} {'─' * 8}")
        print(f"  {'Overall':<12} {m['n_trades']:>7} {m['win_rate']:>8.1%} "
              f"{m['avg_r']:>8.3f} {m['sharpe_ratio']:>8.3f} "
              f"{m['total_pnl_usd']:>10,.0f} {pnl_r:>7.1f}R")


def _print_rolling_summary(rolling: list[dict], windows: list[int]):
    """Print summary of rolling metrics at key percentiles."""
    import numpy as np

    for w in windows:
        key = f"rolling_{w}_sharpe"
        values = [r[key] for r in rolling if r.get(key) is not None]
        if not values:
            continue
        arr = np.array(values)
        print(f"\n  {w}-Trade Rolling Sharpe:")
        print(f"    Min:     {np.min(arr):>8.3f}")
        print(f"    25th:    {np.percentile(arr, 25):>8.3f}")
        print(f"    Median:  {np.median(arr):>8.3f}")
        print(f"    75th:    {np.percentile(arr, 75):>8.3f}")
        print(f"    Max:     {np.max(arr):>8.3f}")

        # Periods where Sharpe was negative
        negative_pct = float(np.mean(arr < 0)) * 100
        print(f"    Below 0: {negative_pct:.1f}% of observations")

    # Show current (most recent) values
    if rolling:
        latest = rolling[-1]
        print(f"\n  Current (most recent trade: {latest['date']}):")
        for w in windows:
            sharpe_key = f"rolling_{w}_sharpe"
            wr_key = f"rolling_{w}_win_rate"
            avg_r_key = f"rolling_{w}_avg_r"
            if latest.get(sharpe_key) is not None:
                print(f"    {w}-trade: Sharpe={latest[sharpe_key]:>7.3f}, "
                      f"WR={latest[wr_key]:.1%}, "
                      f"AvgR={latest[avg_r_key]:.4f}")


def _print_gate_comparison(result: dict):
    """Print comparison of original vs gated performance."""
    orig = result.get("original_metrics", {})
    gated = result.get("gated_metrics", {})
    skipped = result.get("skipped_metrics", {})

    if not orig:
        print("\n  No trades to analyze")
        return

    print(f"\n  {'':>20} {'Original':>12} {'Gated':>12} {'Skipped':>12}")
    print(f"  {'':>20} {'─' * 12} {'─' * 12} {'─' * 12}")

    _gate_row("Trades", orig.get("total_trades", 0), gated.get("total_trades", 0),
              skipped.get("total_trades", 0), fmt="d")
    _gate_row("Win Rate", orig.get("win_rate", 0), gated.get("win_rate", 0),
              skipped.get("win_rate", 0), fmt="pct")
    _gate_row("Avg R", orig.get("avg_r", 0), gated.get("avg_r", 0),
              skipped.get("avg_r", 0), fmt="r")
    _gate_row("Sharpe", orig.get("sharpe_ratio", 0), gated.get("sharpe_ratio", 0),
              skipped.get("sharpe_ratio", 0), fmt="f3")
    _gate_row("Sortino", orig.get("sortino_ratio", 0), gated.get("sortino_ratio", 0),
              skipped.get("sortino_ratio", 0), fmt="f3")
    _gate_row("Profit Factor", orig.get("profit_factor", 0), gated.get("profit_factor", 0),
              skipped.get("profit_factor", 0), fmt="f2")
    _gate_row("Total PnL ($)", orig.get("total_pnl_usd", 0), gated.get("total_pnl_usd", 0),
              skipped.get("total_pnl_usd", 0), fmt="dollar")
    _gate_row("Max DD ($)", orig.get("max_drawdown_usd", 0), gated.get("max_drawdown_usd", 0),
              skipped.get("max_drawdown_usd", 0), fmt="dollar")
    _gate_row("Calmar", orig.get("calmar_ratio", 0), gated.get("calmar_ratio", 0),
              skipped.get("calmar_ratio", 0), fmt="f3")

    # Gate events summary
    events = result.get("gate_events", [])
    close_events = [e for e in events if e["action"] == "close"]
    if close_events:
        print(f"\n  Gate closed {len(close_events)} time(s):")
        for e in close_events:
            reopen = next((r for r in events if r["action"] == "open" and r["trade_index"] > e["trade_index"]), None)
            duration = (reopen["trade_index"] - e["trade_index"]) if reopen else "ongoing"
            print(f"    Closed at trade #{e['trade_index']} ({e['date']}), "
                  f"Sharpe={e['metric_value']:.3f}, "
                  f"duration={duration} trades")
    else:
        print(f"\n  Gate never closed (trailing Sharpe stayed above threshold)")


def _gate_row(label: str, orig, gated, skipped, fmt: str = "f3"):
    """Print one row of the gate comparison table."""
    def _fmt(v):
        if v is None or v == 0 and fmt != "d":
            if fmt == "dollar":
                return "$0"
            return "—"
        if fmt == "d":
            return f"{int(v):>d}"
        elif fmt == "pct":
            return f"{v:.1%}"
        elif fmt == "r":
            return f"{v:.4f}"
        elif fmt == "f2":
            return f"{v:.2f}"
        elif fmt == "f3":
            return f"{v:.3f}"
        elif fmt == "dollar":
            return f"${v:,.0f}"
        return f"{v}"

    print(f"  {label:>20} {_fmt(orig):>12} {_fmt(gated):>12} {_fmt(skipped):>12}")


if __name__ == "__main__":
    main()
