#!/usr/bin/env python3
"""Run combined NY+Asia portfolio backtest with per-session optimized params.

Since rr and tp1_ratio are global config params (not per-session), this script
runs each session separately with its own optimized parameters, then merges
the trade lists chronologically for combined portfolio metrics and Monte Carlo.

Usage:
    python scripts/run_combined_portfolio.py --data NQ_5m.csv \
        --start 2024-01-01 --end 2026-01-01 --mc-sims 2000
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
from core.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from core.results.metrics import compute_metrics
from core.results.export import save_backtest_result
from core.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig


def main():
    parser = argparse.ArgumentParser(description="Combined NY+Asia portfolio backtest + Monte Carlo")
    parser.add_argument("--data", default="NQ_5m.csv", help="Data file")
    parser.add_argument("--start", default="2024-01-01", help="Start date")
    parser.add_argument("--end", default="2026-01-01", help="End date")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol")
    parser.add_argument("--mc-sims", type=int, default=2000, help="Monte Carlo simulations")
    parser.add_argument("--mc-seed", type=int, default=42, help="MC random seed")
    parser.add_argument("--ruin-threshold", type=float, default=-10.0, help="Ruin threshold in R")
    args = parser.parse_args()

    instrument = get_instrument(args.instrument)

    # Load data once
    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")
    print()

    # ── Run per-session backtests ─────────────────────────────────────
    configs = production_config(instrument)
    ny_config, asia_config = configs[0], configs[1]

    print("=" * 60)
    print("NY SESSION")
    print("=" * 60)
    print(f"  rr={ny_config.rr}, tp1_ratio={ny_config.tp1_ratio}")
    print(f"  stop_atr_pct={ny_config.sessions[0].stop_atr_pct}, "
          f"min_gap_atr_pct={ny_config.sessions[0].min_gap_atr_pct}, "
          f"max_gap_atr_pct={ny_config.sessions[0].max_gap_atr_pct}")

    t0 = time.time()
    ny_trades = run_backtest(df, ny_config, start_date=args.start)
    ny_filled = [t for t in ny_trades if t.exit_type != EXIT_NO_FILL]
    print(f"  {len(ny_trades)} signals, {len(ny_filled)} filled [{time.time() - t0:.1f}s]")

    ny_metrics = compute_metrics(ny_trades)
    _print_session_summary("NY", ny_metrics)

    # ── Run Asia session ────────────────────────────────────────────
    print()
    print("=" * 60)
    print("ASIA SESSION")
    print("=" * 60)
    print(f"  rr={asia_config.rr}, tp1_ratio={asia_config.tp1_ratio}")
    print(f"  stop_atr_pct={asia_config.sessions[0].stop_atr_pct}, "
          f"min_gap_atr_pct={asia_config.sessions[0].min_gap_atr_pct}, "
          f"max_gap_atr_pct={asia_config.sessions[0].max_gap_atr_pct}")

    t0 = time.time()
    asia_trades = run_backtest(df, asia_config, start_date=args.start)
    asia_filled = [t for t in asia_trades if t.exit_type != EXIT_NO_FILL]
    print(f"  {len(asia_trades)} signals, {len(asia_filled)} filled [{time.time() - t0:.1f}s]")

    asia_metrics = compute_metrics(asia_trades)
    _print_session_summary("Asia", asia_metrics)

    # ── Combined portfolio ──────────────────────────────────────────
    print()
    print("=" * 60)
    print("COMBINED PORTFOLIO (NY + Asia)")
    print("=" * 60)

    # Merge all trades (including no-fills) sorted by date
    all_trades = sorted(ny_trades + asia_trades, key=lambda t: t.date)
    all_filled = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]
    print(f"  Total signals: {len(all_trades)}")
    print(f"  Total filled:  {len(all_filled)}")

    combined_metrics = compute_metrics(all_trades)
    _print_combined_summary(combined_metrics)

    # Session breakdown within combined
    ny_in_combined = [t for t in all_filled if t.session == "NY"]
    asia_in_combined = [t for t in all_filled if t.session == "Asia"]
    print(f"\n  Session contribution:")
    print(f"    NY:   {len(ny_in_combined)} trades, "
          f"${sum(t.pnl_usd for t in ny_in_combined):,.0f}")
    print(f"    Asia: {len(asia_in_combined)} trades, "
          f"${sum(t.pnl_usd for t in asia_in_combined):,.0f}")

    # Check for same-day overlaps
    ny_dates = {t.date for t in ny_filled}
    asia_dates = {t.date for t in asia_filled}
    overlap_dates = ny_dates & asia_dates
    print(f"\n  Days with both sessions active: {len(overlap_dates)}")
    if overlap_dates:
        # Combined PnL on overlap days
        overlap_pnl = sum(t.pnl_usd for t in all_filled if t.date in overlap_dates)
        print(f"  Combined PnL on overlap days: ${overlap_pnl:,.0f}")

    # ── Save combined result for frontend ───────────────────────────
    # Build config dict with both sessions' params
    combined_config = {
        "instrument": instrument.symbol,
        "point_value": instrument.point_value,
        "risk_usd": ny_config.risk_usd,
        "atr_length": ny_config.atr_length,
        "strategy": "continuation",
        # NY params
        "ny_rr": PROD_NY_GLOBALS["rr"],
        "ny_tp1_ratio": PROD_NY_GLOBALS["tp1_ratio"],
        "ny_be_offset_ticks": PROD_NY_GLOBALS["be_offset_ticks"],
        "ny_stop_atr_pct": PROD_NY_SESSION.stop_atr_pct,
        "ny_min_gap_atr_pct": PROD_NY_SESSION.min_gap_atr_pct,
        "ny_max_gap_atr_pct": PROD_NY_SESSION.max_gap_atr_pct,
        "ny_orb_window": f"{PROD_NY_SESSION.orb_start}-{PROD_NY_SESSION.orb_end}",
        "ny_entry_window": f"{PROD_NY_SESSION.entry_start}-{PROD_NY_SESSION.entry_end}",
        "ny_flat_window": f"{PROD_NY_SESSION.flat_start}-{PROD_NY_SESSION.flat_end}",
        # Asia params
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

    # Build equity curve from chronologically sorted filled trades
    equity_curve = []
    cumulative = 0.0
    for t in all_filled:
        cumulative += t.pnl_usd
        equity_curve.append({
            "date": t.date,
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t.pnl_usd, 2),
        })

    # Build trade list
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

    result_dict = {
        "name": "NY+Asia Combined Portfolio",
        "notes": f"NY (rr={PROD_NY_GLOBALS['rr']}) + Asia (rr={PROD_ASIA_GLOBALS['rr']}). Production config.",
        "config": combined_config,
        "summary": combined_metrics,
        "equity_curve": equity_curve,
        "trades": trades_list,
    }

    result_id = save_backtest_result(result_dict)
    print(f"\n  Results saved: {result_id}")
    print("  View in dashboard -> Backtests tab")

    # ── Monte Carlo on combined portfolio ───────────────────────────
    print()
    print("=" * 60)
    print(f"MONTE CARLO — BOOTSTRAP ({args.mc_sims:,} sims)")
    print("=" * 60)

    mc_config = MonteCarloConfig(
        n_simulations=args.mc_sims,
        method="bootstrap",
        seed=args.mc_seed,
    )

    t0 = time.time()
    mc_bootstrap = run_monte_carlo(all_trades, mc_config, ruin_threshold=args.ruin_threshold)
    print(f"  Completed in {time.time() - t0:.1f}s")
    _print_mc_summary(mc_bootstrap)

    # Also run shuffle for path dependency analysis
    print()
    print("=" * 60)
    print(f"MONTE CARLO — SHUFFLE ({args.mc_sims:,} sims)")
    print("=" * 60)

    mc_shuffle_config = MonteCarloConfig(
        n_simulations=args.mc_sims,
        method="shuffle",
        seed=args.mc_seed,
    )

    t0 = time.time()
    mc_shuffle = run_monte_carlo(all_trades, mc_shuffle_config, ruin_threshold=args.ruin_threshold)
    print(f"  Completed in {time.time() - t0:.1f}s")
    _print_mc_summary(mc_shuffle)

    # ── Drawdown analysis for account sizing ────────────────────────
    print()
    print("=" * 60)
    print("ACCOUNT SIZING ANALYSIS")
    print("=" * 60)

    risk_usd = 5000.0
    actual_dd_r = mc_bootstrap.actual_max_drawdown
    median_dd_r = mc_bootstrap.max_dd_percentiles["p50"]
    worst_dd_r = mc_bootstrap.max_dd_percentiles["p5"]
    p25_dd_r = mc_bootstrap.max_dd_percentiles["p25"]

    print(f"  Risk per trade: ${risk_usd:,.0f}")
    print(f"  Actual max DD:  {actual_dd_r:.1f}R = ${actual_dd_r * risk_usd:,.0f}")
    print(f"  Median DD (MC): {median_dd_r:.1f}R = ${median_dd_r * risk_usd:,.0f}")
    print(f"  25th pct DD:    {p25_dd_r:.1f}R = ${p25_dd_r * risk_usd:,.0f}")
    print(f"  5th pct DD:     {worst_dd_r:.1f}R = ${worst_dd_r * risk_usd:,.0f}")
    print()

    # Conservative: size for 2x worst-case MC drawdown
    buffer = 2.0
    required_capital = abs(worst_dd_r * risk_usd * buffer)
    print(f"  Conservative sizing (2x worst MC DD):")
    print(f"    Min account: ${required_capital:,.0f}")
    print(f"    Risk as % of account: {risk_usd / required_capital * 100:.1f}%")
    print()

    # Moderate: size for 1.5x 25th percentile DD
    buffer_mod = 1.5
    required_mod = abs(p25_dd_r * risk_usd * buffer_mod)
    print(f"  Moderate sizing (1.5x p25 DD):")
    print(f"    Min account: ${required_mod:,.0f}")
    print(f"    Risk as % of account: {risk_usd / required_mod * 100:.1f}%")

    # Ruin at various thresholds
    print()
    print(f"  Ruin probability (bootstrap, {args.mc_sims:,} sims):")
    for thresh in [-8.0, -10.0, -12.0, -15.0]:
        import numpy as np
        dd_arr = np.array(mc_bootstrap.max_drawdowns)
        ruin_pct = float(np.sum(dd_arr < thresh) / len(dd_arr) * 100)
        print(f"    P(DD < {thresh:.0f}R) = {ruin_pct:.1f}% = ${thresh * risk_usd:,.0f}")

    print("=" * 60)


def _print_session_summary(session: str, m: dict):
    print(f"\n  {session} Results:")
    print(f"    Trades:       {m['total_trades']}")
    print(f"    Win rate:     {m['win_rate']:.1%}")
    print(f"    Total PnL:    ${m['total_pnl_usd']:,.0f} ({m['total_pnl_usd']/5000:.1f}R)")
    print(f"    Avg R:        {m['avg_r']:.3f}")
    print(f"    Profit Factor:{m['profit_factor']:.2f}")
    print(f"    Sharpe:       {m['sharpe_ratio']:.3f}")
    print(f"    Sortino:      {m['sortino_ratio']:.3f}")
    print(f"    Calmar:       {m['calmar_ratio']:.3f}")
    print(f"    Max DD:       ${m['max_drawdown_usd']:,.0f}")


def _print_combined_summary(m: dict):
    print(f"\n  Trades:          {m['total_trades']}")
    print(f"  Win rate:        {m['win_rate']:.1%}")
    print(f"  Total PnL:       ${m['total_pnl_usd']:,.0f} ({m['total_pnl_usd']/5000:.1f}R)")
    print(f"  Avg R:           {m['avg_r']:.3f}")
    print(f"  Profit Factor:   {m['profit_factor']:.2f}")
    print(f"  Sharpe:          {m['sharpe_ratio']:.3f}")
    print(f"  Sortino:         {m['sortino_ratio']:.3f}")
    print(f"  Calmar:          {m['calmar_ratio']:.3f}")
    print(f"  Max DD:          ${m['max_drawdown_usd']:,.0f}")
    print(f"  Max Consec Wins: {m['max_consecutive_wins']}")
    print(f"  Max Consec Loss: {m['max_consecutive_losses']}")

    if m["pnl_by_year"]:
        print(f"\n  PnL by year:")
        for year, pnl in m["pnl_by_year"].items():
            print(f"    {year}: ${pnl:>10,.0f}")


def _print_mc_summary(result):
    p = result.final_pnl_percentiles
    print(f"\n  Trades: {result.n_trades}")
    print(f"  Final PnL (R-multiples):")
    print(f"    5th:    {p['p5']:>8.2f}R")
    print(f"    25th:   {p['p25']:>8.2f}R")
    print(f"    50th:   {p['p50']:>8.2f}R  (median)")
    print(f"    75th:   {p['p75']:>8.2f}R")
    print(f"    95th:   {p['p95']:>8.2f}R")
    print(f"    Actual: {result.actual_final_pnl:>8.2f}R")

    p = result.max_dd_percentiles
    print(f"\n  Max Drawdown (R-multiples):")
    print(f"    5th:    {p['p5']:>8.2f}R  (worst)")
    print(f"    25th:   {p['p25']:>8.2f}R")
    print(f"    50th:   {p['p50']:>8.2f}R  (median)")
    print(f"    75th:   {p['p75']:>8.2f}R")
    print(f"    95th:   {p['p95']:>8.2f}R  (best)")
    print(f"    Actual: {result.actual_max_drawdown:>8.2f}R")

    p = result.sharpe_percentiles
    print(f"\n  Sharpe Ratio:")
    print(f"    5th:    {p['p5']:>8.3f}")
    print(f"    50th:   {p['p50']:>8.3f}  (median)")
    print(f"    95th:   {p['p95']:>8.3f}")
    print(f"    Actual: {result.actual_sharpe:>8.3f}")

    print(f"\n  Ruin probability: {result.ruin_probability:.1%}")
    print(f"    (P(max drawdown < {result.ruin_threshold}R))")


if __name__ == "__main__":
    main()
