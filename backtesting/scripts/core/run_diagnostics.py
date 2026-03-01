#!/usr/bin/env python3
"""Run statistical diagnostics on backtest trade results.

Subcommands:
    autocorrelation  — Test R-multiples for serial correlation (Ljung-Box)
    conditional      — Conditional win probabilities and streak analysis
    regime           — CUSUM regime-change detection
    holdout          — Check/log hold-out period usage

Usage:
    # From saved backtest result
    python scripts/core/run_diagnostics.py autocorrelation --result <id>
    python scripts/core/run_diagnostics.py conditional --result <id>
    python scripts/core/run_diagnostics.py regime --result <id>

    # From live backtest
    python scripts/core/run_diagnostics.py autocorrelation --data NQ_5m.csv --sessions NY

    # Hold-out period management
    python scripts/core/run_diagnostics.py holdout check --start 2025-01-01 --end 2026-01-01
    python scripts/core/run_diagnostics.py holdout log --start 2025-01-01 --end 2026-01-01 \\
        --name "NQ NY Holdout Test"
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))


# ---------------------------------------------------------------------------
# Trade loading helpers (shared across subcommands)
# ---------------------------------------------------------------------------

def _load_trades(args):
    """Load trades from --result or --data."""
    from orb_backtest.engine.simulator import EXIT_NO_FILL

    if args.result:
        from orb_backtest.results.export import load_backtest_result
        data = load_backtest_result(args.result)
        if data is None:
            print(f"Error: backtest '{args.result}' not found", file=sys.stderr)
            sys.exit(1)
        trades_dicts = data.get("trades", [])
        if not trades_dicts:
            print("Error: no trades in saved result", file=sys.stderr)
            sys.exit(1)
        trades = _reconstruct_trades(trades_dicts)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"Loaded {len(filled)} filled trades from result '{args.result}'")
        return trades
    elif hasattr(args, "data") and args.data:
        return _run_fresh_backtest(args)
    else:
        print("Error: provide either --result or --data", file=sys.stderr)
        sys.exit(1)


def _run_fresh_backtest(args):
    """Run a fresh backtest and return trades."""
    from orb_backtest.config import default_config, with_overrides, NY_SESSION, ASIA_SESSION, LDN_SESSION
    from orb_backtest.data.instruments import get_instrument
    from orb_backtest.data.loader import load_5m_data
    from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL

    session_map = {"NY": NY_SESSION, "Asia": ASIA_SESSION, "LDN": LDN_SESSION}
    instrument = get_instrument(getattr(args, "instrument", "NQ"))
    sessions = tuple(session_map[s.strip()] for s in args.sessions.split(","))
    config = default_config(instrument)
    config = with_overrides(config, sessions=sessions)

    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=getattr(args, "start", None), end=getattr(args, "end", None))
    print(f"  {len(df):,} bars [{time.time() - t0:.1f}s]")

    print("Running backtest...")
    t0 = time.time()
    trades = run_backtest(df, config, start_date=getattr(args, "start", None))
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    print(f"  {len(filled)} filled trades [{time.time() - t0:.1f}s]")
    return trades


def _reconstruct_trades(trades_dicts):
    """Reconstruct TradeResult objects from saved JSON trade dicts."""
    from orb_backtest.engine.simulator import TradeResult

    EXIT_NAME_TO_INT = {
        "no_fill": 0, "sl": 1, "tp1_tp2": 2, "tp1_be": 3,
        "tp1_eod": 4, "eod": 5, "tp2_single": 6,
    }

    results = []
    for t in trades_dicts:
        exit_type = t.get("exit_type", "no_fill")
        if isinstance(exit_type, str):
            exit_type = EXIT_NAME_TO_INT.get(exit_type, 0)

        results.append(TradeResult(
            date=t.get("date", ""),
            session=t.get("session", ""),
            direction=1 if t.get("direction") == "long" else -1,
            signal_bar=0,
            fill_bar=0 if exit_type != 0 else -1,
            entry_price=t.get("entry_price", 0.0),
            stop_price=t.get("stop_price", 0.0),
            tp1_price=t.get("tp1_price", 0.0),
            tp2_price=t.get("tp2_price", 0.0),
            exit_type=exit_type,
            exit_bar=0,
            pnl_points=t.get("pnl_points", 0.0),
            pnl_usd=t.get("pnl_usd", 0.0),
            r_multiple=t.get("r_multiple", 0.0),
            qty=t.get("qty", 0.0),
            half_qty=0.0,
            gap_size=t.get("gap_size", 0.0),
            risk_points=t.get("risk_points", 0.0),
            fill_time=t.get("fill_time", ""),
            exit_time=t.get("exit_time", ""),
        ))
    return results


# ---------------------------------------------------------------------------
# Shared CLI arguments
# ---------------------------------------------------------------------------

def _add_data_args(parser):
    """Add common data source arguments to a subparser."""
    parser.add_argument("--result", default=None, help="Saved backtest result ID")
    parser.add_argument("--data", default=None, help="Data file name or path")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol")
    parser.add_argument("--sessions", default="NY", help="Comma-separated: NY,Asia,LDN")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", default=None, help="Output JSON file path")


# ---------------------------------------------------------------------------
# Subcommand: autocorrelation
# ---------------------------------------------------------------------------

def cmd_autocorrelation(args):
    """Test R-multiples for serial correlation (Ljung-Box)."""
    from orb_backtest.analysis.autocorrelation import (
        check_mc_assumptions,
        autocorrelation_result_to_dict,
    )

    trades = _load_trades(args)
    result = check_mc_assumptions(trades, max_lag=args.max_lag, alpha=args.alpha)

    print()
    print("=" * 60)
    print("AUTOCORRELATION ANALYSIS (Ljung-Box Test)")
    print("=" * 60)
    print(f"  Trades:           {result.n_trades}")
    print(f"  Max lag tested:   {result.max_lag}")
    print()

    # ACF values
    print("  ACF by lag:")
    threshold = 2.0 / (result.n_trades ** 0.5) if result.n_trades > 0 else 0
    for i, acf_val in enumerate(result.acf_values, 1):
        sig = " *" if i in result.significant_lags else ""
        print(f"    Lag {i:2d}: {acf_val:>8.4f}{sig}")
    print(f"    (* = |ACF| > {threshold:.4f}, significant at 95% CI)")
    print()

    # Ljung-Box test
    print(f"  Ljung-Box Q:      {result.ljung_box_stat:.4f}")
    print(f"  p-value:          {result.ljung_box_p_value:.6f}")
    print(f"  Significant lags: {result.significant_lags or 'none'}")
    print()

    # Recommendation
    if result.has_autocorrelation:
        print(f"  RESULT: Serial correlation DETECTED (p={result.ljung_box_p_value:.4f} < {args.alpha})")
        print(f"  >> Recommendation: Use --method block_bootstrap for Monte Carlo")
        print(f"     Standard i.i.d. bootstrap will UNDERESTIMATE drawdown risk")
    else:
        print(f"  RESULT: No significant autocorrelation (p={result.ljung_box_p_value:.4f} >= {args.alpha})")
        print(f"  >> i.i.d. bootstrap is valid for this trade sequence")
    print("=" * 60)

    if args.output:
        Path(args.output).write_text(json.dumps(autocorrelation_result_to_dict(result), indent=2))
        print(f"\nResults saved to: {args.output}")


# ---------------------------------------------------------------------------
# Subcommand: conditional
# ---------------------------------------------------------------------------

def cmd_conditional(args):
    """Conditional win probabilities and streak analysis."""
    from orb_backtest.analysis.conditional_stats import (
        compute_conditional_stats,
        conditional_stats_to_dict,
    )

    trades = _load_trades(args)
    result = compute_conditional_stats(trades)

    print()
    print("=" * 60)
    print("CONDITIONAL STATISTICS")
    print("=" * 60)
    print(f"  Trades:     {result.n_trades}")
    print(f"  Win rate:   {result.win_rate:.1%}")
    print()

    # Conditional probabilities
    print("  CONDITIONAL WIN PROBABILITIES")
    print(f"    P(win | prev win):   {result.p_win_after_win:.1%}")
    print(f"    P(win | prev loss):  {result.p_win_after_loss:.1%}")
    delta = result.p_win_after_win - result.p_win_after_loss
    if abs(delta) > 0.05:
        direction = "hot hand" if delta > 0 else "mean reversion"
        print(f"    >> Delta: {delta:+.1%} ({direction} effect)")
    else:
        print(f"    >> Delta: {delta:+.1%} (negligible)")
    print()

    print(f"    P(win | in drawdown): {result.p_win_in_drawdown:.1%}")
    print()

    # P(win | N consecutive losses)
    if result.p_win_after_n_losses:
        print("    P(win | after N consecutive losses):")
        for n_losses, p in sorted(result.p_win_after_n_losses.items()):
            print(f"      After {n_losses} losses: {p:.1%}")
        print()

    # Streak analysis
    print("  STREAK ANALYSIS")
    print(f"    Max consecutive wins:   {result.max_consecutive_wins}")
    print(f"    Max consecutive losses: {result.max_consecutive_losses}")
    print(f"    Expected max losses (i.i.d.): {result.expected_max_consecutive_losses:.1f}")
    print(f"    Z-score: {result.streak_z_score:+.2f}", end="")
    if abs(result.streak_z_score) > 2:
        print("  ** SIGNIFICANT (|Z| > 2)")
    elif abs(result.streak_z_score) > 1.5:
        print("  * marginal")
    else:
        print("  (within expectations)")
    print()

    # Performance in drawdown
    print("  PERFORMANCE IN DRAWDOWN")
    for level, stats in result.performance_in_drawdown.items():
        if stats["n_trades"] > 0:
            print(f"    DD > {level}: {stats['n_trades']} trades, "
                  f"WR={stats['win_rate']:.1%}, avg_R={stats['avg_r']:+.2f}")
        else:
            print(f"    DD > {level}: no trades")
    print()

    # R-series autocorrelation
    if result.r_autocorrelations:
        print("  R-SERIES AUTOCORRELATION (lags 1-5)")
        for i, acf in enumerate(result.r_autocorrelations, 1):
            print(f"    Lag {i}: {acf:>8.4f}")
        print()

    # Independence test
    print("  INDEPENDENCE TEST (chi-squared)")
    print(f"    Chi2 stat: {result.chi2_stat:.4f}")
    print(f"    p-value:   {result.chi2_p_value:.6f}")
    if result.outcomes_independent:
        print("    >> Win/loss outcomes appear INDEPENDENT of prior outcome")
    else:
        print("    >> Win/loss outcomes are NOT independent (p < 0.05)")
        print("       Trade outcomes depend on the prior trade's result")
    print("=" * 60)

    if args.output:
        Path(args.output).write_text(json.dumps(conditional_stats_to_dict(result), indent=2))
        print(f"\nResults saved to: {args.output}")


# ---------------------------------------------------------------------------
# Subcommand: regime
# ---------------------------------------------------------------------------

def cmd_regime(args):
    """CUSUM regime-change detection."""
    from orb_backtest.analysis.regime_change import (
        detect_regime_change,
        regime_change_to_dict,
    )

    trades = _load_trades(args)
    result = detect_regime_change(trades, alpha=args.alpha, min_segment=args.min_segment)

    print()
    print("=" * 60)
    print("REGIME CHANGE DETECTION (CUSUM Test)")
    print("=" * 60)
    print(f"  Trades:          {result.n_trades}")
    print(f"  CUSUM statistic: {result.cusum_stat:.4f}")
    print(f"  Critical value:  {result.critical_value:.4f} (alpha={args.alpha})")
    print(f"  Confidence:      {result.confidence_level:.1%}")
    print()

    if result.break_detected:
        print(f"  BREAK DETECTED at trade #{result.break_index} ({result.break_date})")
        print()

        if result.before_metrics and result.after_metrics:
            b = result.before_metrics
            a = result.after_metrics
            print(f"  {'Metric':<16} {'Before':>10} {'After':>10} {'Change':>10}")
            print(f"  {'-'*16} {'-'*10} {'-'*10} {'-'*10}")
            for key in ["n_trades", "avg_r", "win_rate", "sharpe", "calmar"]:
                bv = b[key]
                av = a[key]
                if isinstance(bv, int):
                    print(f"  {key:<16} {bv:>10} {av:>10}")
                else:
                    delta = av - bv
                    print(f"  {key:<16} {bv:>10.4f} {av:>10.4f} {delta:>+10.4f}")
            print()
            print("  >> Strategy behavior has structurally changed.")
            print("     Review whether recent regime is still viable for live trading.")
    else:
        print("  No structural break detected.")
        print("  >> Strategy behavior appears stationary across the sample period.")
    print("=" * 60)

    if args.output:
        Path(args.output).write_text(json.dumps(regime_change_to_dict(result), indent=2))
        print(f"\nResults saved to: {args.output}")


# ---------------------------------------------------------------------------
# Subcommand: holdout
# ---------------------------------------------------------------------------

def cmd_holdout(args):
    """Check or log hold-out period usage."""
    if args.holdout_action == "check":
        _holdout_check(args)
    elif args.holdout_action == "log":
        _holdout_log(args)
    elif args.holdout_action == "history":
        _holdout_history(args)
    else:
        print(f"Unknown holdout action: {args.holdout_action}", file=sys.stderr)
        sys.exit(1)


def _holdout_check(args):
    """Check if a hold-out period has been tested before."""
    from orb_backtest.analysis.holdout_log import check_holdout_period

    result = check_holdout_period(args.start, args.end)

    print()
    print("=" * 60)
    print("HOLD-OUT PERIOD CHECK")
    print("=" * 60)
    print(f"  Period: {args.start} to {args.end}")
    print(f"  Previous tests: {result.previous_test_count}")
    print(f"  Unique configs: {len(result.previous_configs)}")
    print()

    if result.is_clean:
        print("  STATUS: CLEAN — this period has never been tested.")
        print("  >> Safe to use as a true out-of-sample hold-out.")
    else:
        print(f"  {result.warning}")
    print("=" * 60)


def _holdout_log(args):
    """Log a hold-out test."""
    from orb_backtest.analysis.holdout_log import log_holdout_test

    config = {}
    if args.config:
        config = json.loads(args.config)

    entry = log_holdout_test(
        period_start=args.start,
        period_end=args.end,
        config=config,
        experiment_name=args.name or "",
    )

    print()
    print("=" * 60)
    print("HOLD-OUT TEST LOGGED")
    print("=" * 60)
    print(f"  Period:     {entry.period_start} to {entry.period_end}")
    print(f"  Experiment: {entry.experiment_name or '(unnamed)'}")
    print(f"  Config hash: {entry.config_hash[:12]}...")
    print(f"  Test count: {entry.test_count}")
    print(f"  First use:  {entry.is_first_use}")
    print()

    if entry.warning:
        print(f"  {entry.warning}")
    else:
        print("  No warnings.")
    print("=" * 60)


def _holdout_history(args):
    """Show hold-out test history."""
    from orb_backtest.analysis.holdout_log import get_holdout_history

    entries = get_holdout_history(
        period_start=getattr(args, "start", None),
        period_end=getattr(args, "end", None),
    )

    print()
    print("=" * 60)
    print("HOLD-OUT TEST HISTORY")
    print("=" * 60)

    if not entries:
        print("  No hold-out tests logged yet.")
    else:
        for e in entries:
            print(f"  [{e['timestamp'][:19]}] {e['period_key']}")
            print(f"    Config: {e['config_hash'][:12]}...  "
                  f"Experiment: {e.get('experiment_name', '?')}")
        print()
        print(f"  Total entries: {len(entries)}")

        # Summary by period
        periods = {}
        for e in entries:
            pk = e["period_key"]
            periods.setdefault(pk, set()).add(e["config_hash"])
        print()
        print("  Period summary:")
        for pk, configs in sorted(periods.items()):
            n_tests = sum(1 for e in entries if e["period_key"] == pk)
            status = "CLEAN" if n_tests == 0 else f"{n_tests} tests, {len(configs)} configs"
            print(f"    {pk}: {status}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Statistical diagnostics for backtest trade results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test for autocorrelation
  python scripts/core/run_diagnostics.py autocorrelation --result <id>

  # Conditional statistics
  python scripts/core/run_diagnostics.py conditional --data NQ_5m.csv --sessions NY

  # Regime change detection
  python scripts/core/run_diagnostics.py regime --result <id>

  # Hold-out period management
  python scripts/core/run_diagnostics.py holdout check --start 2025-01-01 --end 2026-01-01
  python scripts/core/run_diagnostics.py holdout log --start 2025-01-01 --end 2026-01-01 --name "test"
  python scripts/core/run_diagnostics.py holdout history
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- autocorrelation ---
    p_ac = subparsers.add_parser("autocorrelation", help="Ljung-Box autocorrelation test")
    _add_data_args(p_ac)
    p_ac.add_argument("--max-lag", type=int, default=10, help="Maximum lag to test (default: 10)")
    p_ac.add_argument("--alpha", type=float, default=0.05, help="Significance level (default: 0.05)")

    # --- conditional ---
    p_cs = subparsers.add_parser("conditional", help="Conditional statistics analysis")
    _add_data_args(p_cs)

    # --- regime ---
    p_rc = subparsers.add_parser("regime", help="CUSUM regime-change detection")
    _add_data_args(p_rc)
    p_rc.add_argument("--alpha", type=float, default=0.05, help="Significance level (default: 0.05)")
    p_rc.add_argument("--min-segment", type=int, default=20, help="Min trades per segment (default: 20)")

    # --- holdout ---
    p_ho = subparsers.add_parser("holdout", help="Hold-out period tracking")
    ho_sub = p_ho.add_subparsers(dest="holdout_action", required=True)

    ho_check = ho_sub.add_parser("check", help="Check if hold-out has been used")
    ho_check.add_argument("--start", required=True, help="Period start (YYYY-MM-DD)")
    ho_check.add_argument("--end", required=True, help="Period end (YYYY-MM-DD)")

    ho_log = ho_sub.add_parser("log", help="Log a hold-out test")
    ho_log.add_argument("--start", required=True, help="Period start (YYYY-MM-DD)")
    ho_log.add_argument("--end", required=True, help="Period end (YYYY-MM-DD)")
    ho_log.add_argument("--name", default=None, help="Experiment name")
    ho_log.add_argument("--config", default=None, help="Config as JSON string")

    ho_hist = ho_sub.add_parser("history", help="Show hold-out test history")
    ho_hist.add_argument("--start", default=None, help="Filter by period start")
    ho_hist.add_argument("--end", default=None, help="Filter by period end")

    args = parser.parse_args()

    if args.command == "autocorrelation":
        cmd_autocorrelation(args)
    elif args.command == "conditional":
        cmd_conditional(args)
    elif args.command == "regime":
        cmd_regime(args)
    elif args.command == "holdout":
        cmd_holdout(args)


if __name__ == "__main__":
    main()
