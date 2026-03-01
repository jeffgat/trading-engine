#!/usr/bin/env python3
"""Run the 5-leg combined longs production portfolio backtest.

Legs:
  1. NQ NY    — rr=3.5, stop=7.0% ATR-12, tp1=0.4, exclude Fri
  2. NQ Asia  — rr=6.0, stop=ORB-based (APPROX: 5.25% ATR), tp1=0.3, exclude Tue
  3. GC NY    — rr=9.0, stop=4.5% ATR-7, tp1=0.35, exclude Fri+FOMC, ICF on
  4. ES NY    — rr=5.0, stop=5.0% ATR-7, tp1=0.2, exclude Thu
  5. ES Asia  — rr=1.5, stop=ORB-based (APPROX: 5.25% ATR), tp1=0.7

NOTE: Legs 2 and 5 use ORB-based stops in production. The backtesting engine
only supports ATR-based stops, so these legs run with approximate ATR-based
equivalents. Results will differ slightly from Pine Script.

Usage:
    python scripts/run_5leg_prod.py
    python scripts/run_5leg_prod.py --start 2020-01-01 --end 2026-01-01
    python scripts/run_5leg_prod.py --mc-sims 5000
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import save_backtest_result
from orb_backtest.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig
from orb_backtest.analysis.gates import apply_dow_filter


# ── Data directory (sibling repo) ─────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parents[3] / ".." / "backtests" / "python" / "data" / "raw"

# ── Half-days (shared across all legs) ────────────────────────────────────
HALF_DAYS = (
    "20250703", "20251128", "20251224", "20250109", "20260119",
    "20240703", "20241129", "20241224",
)


# ── Leg definitions ───────────────────────────────────────────────────────

def _leg1_nq_ny():
    """Leg 1: NQ NY — rr=3.5, stop=7.0% ATR-12, tp1=0.4, exclude Friday."""
    inst = get_instrument("NQ")
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:50",
        entry_start="09:50", entry_end="12:00",
        flat_start="15:30", flat_end="16:00",
        stop_atr_pct=7.0,
        min_gap_atr_pct=2.5,
        max_gap_points=0,
        max_gap_atr_pct=0,
    )
    return StrategyConfig(
        rr=3.5, tp1_ratio=0.4, atr_length=12,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg1 NQ NY",
    ), inst, {4}  # exclude Friday


def _leg2_nq_asia():
    """Leg 2: NQ Asia — rr=6.0, ORB-stop (approx 5.25% ATR), tp1=0.3, exclude Tuesday.

    NOTE: Production uses stop_orb_pct=100 and min_gap_orb_pct=10.
    Engine only supports ATR-based stops, so we approximate.
    """
    inst = get_instrument("NQ")
    session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="22:30",
        flat_start="04:00", flat_end="07:00",
        stop_atr_pct=5.25,   # approximate ORB-based stop
        min_gap_atr_pct=0.9,  # approximate ORB-based gap filter
        max_gap_points=0,
        max_gap_atr_pct=0,
    )
    return StrategyConfig(
        rr=6.0, tp1_ratio=0.3, atr_length=5,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg2 NQ Asia",
        notes="APPROX: ORB-based stop replaced with ATR-based",
    ), inst, {1}  # exclude Tuesday


def _leg3_gc_ny():
    """Leg 3: GC NY — rr=9.0, stop=4.5% ATR-7, tp1=0.35, exclude Fri+FOMC, ICF on."""
    inst = get_instrument("GC")
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:40",
        entry_start="09:40", entry_end="12:00",
        flat_start="13:30", flat_end="16:00",
        stop_atr_pct=4.5,
        min_gap_atr_pct=3.0,
        max_gap_points=0,
        max_gap_atr_pct=0,
    )
    return StrategyConfig(
        rr=9.0, tp1_ratio=0.35, atr_length=7,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        impulse_close_filter=True,
        half_days=HALF_DAYS,
        excluded_dates=FOMC_DATES,
        name="Leg3 GC NY",
    ), inst, {4}  # exclude Friday


def _leg4_es_ny():
    """Leg 4: ES NY — rr=5.0, stop=5.0% ATR-7, tp1=0.2, exclude Thursday."""
    inst = get_instrument("ES")
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=0.25,
        max_gap_points=0,
        max_gap_atr_pct=0,
    )
    return StrategyConfig(
        rr=5.0, tp1_ratio=0.2, atr_length=7,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg4 ES NY",
    ), inst, {3}  # exclude Thursday


def _leg5_es_asia():
    """Leg 5: ES Asia — rr=1.5, ORB-stop (approx 5.25% ATR), tp1=0.7.

    NOTE: Production uses stop_orb_pct=125 and min_gap based on ATR-14.
    Engine only supports ATR-based stops, so we approximate.
    """
    inst = get_instrument("ES")
    session = SessionConfig(
        name="Asia",
        orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="03:00",
        flat_start="07:00", flat_end="07:00",
        stop_atr_pct=5.25,   # approximate ORB-based stop
        min_gap_atr_pct=0.5,
        max_gap_points=0,
        max_gap_atr_pct=0,
    )
    return StrategyConfig(
        rr=1.5, tp1_ratio=0.7, atr_length=14,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=inst,
        direction_filter="long",
        half_days=HALF_DAYS,
        name="Leg5 ES Asia",
        notes="APPROX: ORB-based stop replaced with ATR-based",
    ), inst, set()  # no DOW exclusion


# ── Main ──────────────────────────────────────────────────────────────────

LEGS = [
    ("Leg 1: NQ NY",   _leg1_nq_ny,  "NQ"),
    ("Leg 2: NQ Asia",  _leg2_nq_asia, "NQ"),
    ("Leg 3: GC NY",   _leg3_gc_ny,  "GC"),
    ("Leg 4: ES NY",   _leg4_es_ny,  "ES"),
    ("Leg 5: ES Asia",  _leg5_es_asia, "ES"),
]


def main():
    parser = argparse.ArgumentParser(description="5-leg combined longs production backtest")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--mc-sims", type=int, default=2000, help="Monte Carlo simulations")
    parser.add_argument("--mc-seed", type=int, default=42, help="MC random seed")
    parser.add_argument("--data-dir", default=None, help="Override data directory")
    parser.add_argument("--name", default="5-Leg Combined Longs Prod", help="Experiment name")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR

    # ── Load data for each instrument ─────────────────────────────────
    print("=" * 70)
    print("5-LEG COMBINED LONGS PORTFOLIO — PRODUCTION BACKTEST")
    print("=" * 70)
    print()

    data_cache = {}  # {symbol: DataFrame}
    for symbol in ("NQ", "ES", "GC"):
        data_file = data_dir / f"{symbol}_5m.parquet"
        if not data_file.exists():
            data_file = data_dir / f"{symbol}_5m.csv"
        if not data_file.exists():
            print(f"ERROR: Data file not found for {symbol} in {data_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"Loading {symbol} data: {data_file.name}")
        t0 = time.time()
        df = load_5m_data(str(data_file), start=args.start, end=args.end)
        data_cache[symbol] = df
        print(f"  {len(df):,} bars ({df.index[0].date()} → {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    print()

    # ── Run each leg ──────────────────────────────────────────────────
    all_trades = []
    leg_results = []

    for leg_name, leg_fn, symbol in LEGS:
        config, inst, excluded_dow = leg_fn()
        df = data_cache[symbol]

        print("-" * 70)
        print(f"{leg_name}  ({symbol}, rr={config.rr}, tp1={config.tp1_ratio}, "
              f"stop_atr={config.sessions[0].stop_atr_pct}%)")
        if config.notes:
            print(f"  ⚠ {config.notes}")

        t0 = time.time()
        trades = run_backtest(df, config, start_date=args.start)

        # Apply DOW exclusion post-trade
        if excluded_dow:
            dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
            excluded_str = ", ".join(dow_names[d] for d in excluded_dow)
            trades = apply_dow_filter(trades, excluded_dow)
            print(f"  DOW exclusion: {excluded_str}")

        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        elapsed = time.time() - t0
        print(f"  {len(filled)} filled trades [{elapsed:.1f}s]")

        metrics = compute_metrics(trades)
        _print_leg_summary(metrics)

        leg_results.append({
            "name": leg_name,
            "symbol": symbol,
            "config": config,
            "trades": trades,
            "filled": filled,
            "metrics": metrics,
        })

        # Tag trades with leg info for combined analysis
        all_trades.extend(trades)

    # ── Combined portfolio ────────────────────────────────────────────
    all_trades.sort(key=lambda t: t.date)
    all_filled = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]

    print()
    print("=" * 70)
    print("COMBINED PORTFOLIO (5 Legs)")
    print("=" * 70)

    combined_metrics = compute_metrics(all_trades)
    _print_combined_summary(combined_metrics)

    # Per-leg contribution
    print("\n  Per-leg contribution:")
    print(f"  {'Leg':<20} {'Trades':>7} {'WR':>7} {'Net R':>8} {'Sharpe':>8} {'Calmar':>8}")
    print(f"  {'-'*20} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*8}")
    for lr in leg_results:
        m = lr["metrics"]
        print(f"  {lr['name']:<20} {m['total_trades']:>7} {m['win_rate']:>6.1%} "
              f"{m['total_r']:>8.1f} {m['sharpe_ratio']:>8.3f} {m['calmar_ratio']:>8.2f}")
    total_r = combined_metrics["total_r"]
    print(f"  {'COMBINED':<20} {combined_metrics['total_trades']:>7} {combined_metrics['win_rate']:>6.1%} "
          f"{total_r:>8.1f} {combined_metrics['sharpe_ratio']:>8.3f} {combined_metrics['calmar_ratio']:>8.2f}")

    # PnL by year
    if combined_metrics["r_by_year"]:
        print("\n  R by year:")
        for year, r in sorted(combined_metrics["r_by_year"].items()):
            print(f"    {year}: {r:>+8.1f}R")

    # ── Monte Carlo ───────────────────────────────────────────────────
    if args.mc_sims > 0:
        print()
        print("=" * 70)
        print(f"MONTE CARLO — BOOTSTRAP ({args.mc_sims:,} sims)")
        print("=" * 70)

        mc_config = MonteCarloConfig(
            n_simulations=args.mc_sims,
            method="bootstrap",
            seed=args.mc_seed,
        )

        t0 = time.time()
        mc_result = run_monte_carlo(all_trades, mc_config, ruin_threshold=-10.0)
        print(f"  Completed in {time.time() - t0:.1f}s")
        _print_mc_summary(mc_result)

    # ── Save result ───────────────────────────────────────────────────
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
            "r_multiple": round(t.r_multiple, 3),
            "qty": t.qty,
            "gap_size": round(t.gap_size, 4),
            "risk_points": round(t.risk_points, 4),
        }
        for t in all_trades
    ]

    equity_curve = []
    cumulative = 0.0
    for t in all_filled:
        cumulative += t.pnl_usd
        equity_curve.append({
            "date": t.date,
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t.pnl_usd, 2),
        })

    result_dict = {
        "name": args.name,
        "notes": "5-leg combined longs. Legs 2,5 approx (ORB stop → ATR stop).",
        "config": {
            "legs": [lr["name"] for lr in leg_results],
            "strategy": "continuation",
            "direction_filter": "long",
            "risk_usd": 5000.0,
        },
        "summary": combined_metrics,
        "equity_curve": equity_curve,
        "trades": trades_list,
    }

    result_id = save_backtest_result(result_dict)
    print(f"\n  Results saved: {result_id}")
    print("  View in dashboard → Backtests tab")
    print("=" * 70)


# ── Output helpers ────────────────────────────────────────────────────────

def _print_leg_summary(m: dict):
    print(f"  WR={m['win_rate']:.1%}  Net R={m['total_r']:.1f}  "
          f"Sharpe={m['sharpe_ratio']:.3f}  Calmar={m['calmar_ratio']:.2f}  "
          f"Max DD={m['max_drawdown_r']:.1f}R  PF={m['profit_factor']:.2f}")


def _print_combined_summary(m: dict):
    print(f"\n  Trades:          {m['total_trades']}")
    print(f"  Win rate:        {m['win_rate']:.1%}")
    print(f"  Total R:         {m['total_r']:.1f}")
    print(f"  Avg R:           {m['avg_r']:.3f}")
    print(f"  Profit Factor:   {m['profit_factor']:.2f}")
    print(f"  Sharpe:          {m['sharpe_ratio']:.3f}")
    print(f"  Sortino:         {m['sortino_ratio']:.3f}")
    print(f"  Calmar:          {m['calmar_ratio']:.2f}")
    print(f"  Max DD:          {m['max_drawdown_r']:.1f}R")
    print(f"  Max Consec Wins: {m['max_consecutive_wins']}")
    print(f"  Max Consec Loss: {m['max_consecutive_losses']}")


def _print_mc_summary(result):
    p = result.final_pnl_percentiles
    print(f"\n  Trades: {result.n_trades}")
    print(f"  Final PnL (R):")
    print(f"    5th:  {p['p5']:>8.1f}R    50th: {p['p50']:>8.1f}R    95th: {p['p95']:>8.1f}R")
    print(f"    Actual: {result.actual_final_pnl:>8.1f}R")

    p = result.max_dd_percentiles
    print(f"  Max Drawdown (R):")
    print(f"    5th:  {p['p5']:>8.1f}R    50th: {p['p50']:>8.1f}R    95th: {p['p95']:>8.1f}R")
    print(f"    Actual: {result.actual_max_drawdown:>8.1f}R")

    print(f"  Ruin probability: {result.ruin_probability:.1%}  (P(DD < {result.ruin_threshold}R))")


if __name__ == "__main__":
    main()
