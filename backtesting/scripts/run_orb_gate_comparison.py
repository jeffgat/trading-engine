#!/usr/bin/env python3
"""Save two backtest results for frontend comparison: No Gate vs ORB Size Gate.

Both use identical NY+Asia optimized params. The gated version filters out
trades where the ORB range is outside 5-20% of daily ATR.

Usage:
    python scripts/run_orb_gate_comparison.py
    python scripts/run_orb_gate_comparison.py --start 2016-01-01 --end 2026-01-01
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
    ORBSizeGateConfig, simulate_orb_size_gate,
)

ORB_GATE = ORBSizeGateConfig(min_orb_atr_pct=5.0, max_orb_atr_pct=20.0)


def main():
    parser = argparse.ArgumentParser(description="Save No Gate vs ORB Gate results for frontend")
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

    # ── Shared config dict ───────────────────────────────────────────
    base_config = {
        "instrument": instrument.symbol,
        "point_value": instrument.point_value,
        "risk_usd": 5000.0,
        "atr_length": 14,
        "strategy": "continuation",
        "ny_rr": PROD_NY_GLOBALS["rr"],
        "ny_tp1_ratio": PROD_NY_GLOBALS["tp1_ratio"],
        "ny_stop_atr_pct": PROD_NY_SESSION.stop_atr_pct,
        "ny_min_gap_atr_pct": PROD_NY_SESSION.min_gap_atr_pct,
        "ny_max_gap_atr_pct": PROD_NY_SESSION.max_gap_atr_pct,
        "ny_orb_window": f"{PROD_NY_SESSION.orb_start}-{PROD_NY_SESSION.orb_end}",
        "ny_entry_window": f"{PROD_NY_SESSION.entry_start}-{PROD_NY_SESSION.entry_end}",
        "ny_flat_window": f"{PROD_NY_SESSION.flat_start}-{PROD_NY_SESSION.flat_end}",
        "asia_rr": PROD_ASIA_GLOBALS["rr"],
        "asia_tp1_ratio": PROD_ASIA_GLOBALS["tp1_ratio"],
        "asia_stop_atr_pct": PROD_ASIA_SESSION.stop_atr_pct,
        "asia_min_gap_atr_pct": PROD_ASIA_SESSION.min_gap_atr_pct,
        "asia_max_gap_atr_pct": PROD_ASIA_SESSION.max_gap_atr_pct,
        "asia_orb_window": f"{PROD_ASIA_SESSION.orb_start}-{PROD_ASIA_SESSION.orb_end}",
        "asia_entry_window": f"{PROD_ASIA_SESSION.entry_start}-{PROD_ASIA_SESSION.entry_end}",
        "asia_flat_window": f"{PROD_ASIA_SESSION.flat_start}-{PROD_ASIA_SESSION.flat_end}",
    }

    # ── Save NO GATE result ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Saving: NY+Asia Combined (No Gate)")
    print("=" * 60)

    no_gate_result = _build_result(
        all_trades,
        base_config,
        name="NY+Asia Combined (No Gate)",
        notes="No ORB size gate. Baseline for comparison.",
    )
    no_gate_id = save_backtest_result(no_gate_result)
    m = no_gate_result["summary"]
    print(f"  {m['total_trades']} trades, {m['win_rate']:.1%} WR, "
          f"{m['total_pnl_usd']/5000:.1f}R, Sharpe {m['sharpe_ratio']:.3f}")
    print(f"  Saved: {no_gate_id}")

    # ── Apply ORB gate ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Saving: NY+Asia Combined (ORB Gate {ORB_GATE.min_orb_atr_pct}-{ORB_GATE.max_orb_atr_pct}%)")
    print("=" * 60)

    # Filter trades through the gate
    filled = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]
    gated_trades = []
    for t in filled:
        atr = t.daily_atr
        orb = t.orb_range
        if atr <= 0 or orb <= 0:
            gated_trades.append(t)
            continue
        orb_atr_pct = (orb / atr) * 100.0
        if ORB_GATE.min_orb_atr_pct <= orb_atr_pct <= ORB_GATE.max_orb_atr_pct:
            gated_trades.append(t)

    gated_config = dict(base_config)
    gated_config["orb_gate_min_atr_pct"] = ORB_GATE.min_orb_atr_pct
    gated_config["orb_gate_max_atr_pct"] = ORB_GATE.max_orb_atr_pct

    gated_result = _build_result(
        gated_trades,
        gated_config,
        name="NY+Asia Combined (ORB Gate 5-20%)",
        notes=f"ORB size gate: only take trades where ORB range is {ORB_GATE.min_orb_atr_pct}-{ORB_GATE.max_orb_atr_pct}% of daily ATR.",
    )
    gated_id = save_backtest_result(gated_result)
    m = gated_result["summary"]
    print(f"  {m['total_trades']} trades, {m['win_rate']:.1%} WR, "
          f"{m['total_pnl_usd']/5000:.1f}R, Sharpe {m['sharpe_ratio']:.3f}")
    print(f"  Saved: {gated_id}")

    print("\n  Done! Compare both in the dashboard.")


def _build_result(
    trades: list[TradeResult],
    config: dict,
    name: str,
    notes: str,
) -> dict:
    """Build a result dict matching the frontend's expected format."""
    metrics = compute_metrics(trades)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    # Equity curve
    equity_curve = []
    cumulative = 0.0
    for t in filled:
        cumulative += t.pnl_usd
        equity_curve.append({
            "date": t.date,
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t.pnl_usd, 2),
        })

    # Trade list
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


if __name__ == "__main__":
    main()
