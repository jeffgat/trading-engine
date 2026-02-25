#!/usr/bin/env python3
"""Combine four starred strategies into a single portfolio run.

Strategies combined (all risk $5000/trade):
  ID 6707 — ES LDN 2016-2026 Continuation Both WF Mode
  ID 6718 — NQ ASIA 2015-2026 v3 flat00 Pipeline NO-GO
  ID 6717 — NQ NY Long Continuation Accepted (WF Mode)
  ID 6693 — GC NY Inv Longs Stacked v9+CleanAir

Trades are merged chronologically. Because all legs share risk_usd=5000,
R-multiples and USD PnL are directly additive across instruments.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.experiments import log_run, init_db, DB_PATH
from orb_backtest.results.export import generate_backtest_id

# ── Strategy legs to combine ────────────────────────────────────────────────
RUN_IDS = [6707, 6718, 6717, 6693]

PORTFOLIO_NAME = "4-Way Portfolio: ES LDN + NQ ASIA + NQ NY + GC NY"
NOTES = (
    "Combined portfolio: "
    "ES LDN (WF continuation, ID=6707) + "
    "NQ ASIA v3 flat00 (ID=6718) + "
    "NQ NY Long WF continuation (ID=6717) + "
    "GC NY Inv Longs v9+CleanAir (ID=6693). "
    "All legs risk $5,000/trade. Trades merged chronologically by date."
)


def main():
    import sqlite3

    init_db()
    conn = sqlite3.connect(DB_PATH)

    # ── 1. Load filled trades from each run ──────────────────────────────────
    all_trades: list[dict] = []
    components: list[dict] = []

    for run_id in RUN_IDS:
        row = conn.execute(
            "SELECT experiment_name, instrument, sessions, trades_json FROM runs WHERE id=?",
            [run_id],
        ).fetchone()

        if row is None:
            print(f"  WARNING: run ID {run_id} not found — skipping")
            continue

        name, instrument, sessions, trades_json = row
        trades = json.loads(trades_json) if trades_json else []
        filled = [t for t in trades if t.get("exit_type") != "no_fill"]

        all_trades.extend(filled)
        components.append(
            {"id": run_id, "name": name, "instrument": instrument,
             "sessions": sessions or "", "trade_count": len(filled)}
        )
        print(f"  Loaded {len(filled):>5} filled trades  ← {name}")

    conn.close()

    if not all_trades:
        print("ERROR: No trades loaded — aborting.")
        sys.exit(1)

    # ── 2. Sort chronologically ──────────────────────────────────────────────
    all_trades.sort(key=lambda t: t["date"])

    print(f"\n  Total merged trades: {len(all_trades)}")
    print(f"  Date range: {all_trades[0]['date']} → {all_trades[-1]['date']}")

    # ── 3. Compute combined metrics ──────────────────────────────────────────
    from orb_backtest.results.metrics import recompute_summary

    summary = recompute_summary(all_trades)

    # recompute_summary omits total_r / max_drawdown_r — compute them here
    r_arr = np.array([t["r_multiple"] for t in all_trades], dtype=float)
    r_eq = np.cumsum(r_arr)
    r_pk = np.maximum.accumulate(r_eq)
    r_dd = r_eq - r_pk
    summary["total_r"] = float(r_eq[-1])
    summary["max_drawdown_r"] = float(np.min(r_dd))

    # R by year (for frontend charts)
    r_by_year: dict[str, float] = {}
    for t in all_trades:
        yr = t["date"][:4]
        r_by_year[yr] = r_by_year.get(yr, 0.0) + t["r_multiple"]
    summary["r_by_year"] = dict(sorted(r_by_year.items()))

    # ── 4. Build equity curve ────────────────────────────────────────────────
    equity_curve: list[dict] = []
    cum_usd = 0.0
    for t in all_trades:
        cum_usd += t["pnl_usd"]
        equity_curve.append({
            "date": t["date"],
            "pnl_cumulative": round(cum_usd, 2),
            "pnl_per_trade": round(t["pnl_usd"], 2),
        })

    # ── 5. Config dict ────────────────────────────────────────────────────────
    config = {
        "instrument": "PORTFOLIO",
        "risk_usd": 5000.0,
        "strategy": "multi-instrument",
        "components": [
            f"{c['instrument']} {c['sessions']} (id={c['id']})"
            for c in components
        ],
    }

    # ── 6. Save ───────────────────────────────────────────────────────────────
    result = {
        "name": PORTFOLIO_NAME,
        "notes": NOTES,
        "config": config,
        "summary": summary,
        "trades": all_trades,
        "equity_curve": equity_curve,
    }

    result_id = generate_backtest_id(result)
    row_id = log_run(result, result_id)

    # ── 7. Print summary ──────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("COMBINED PORTFOLIO METRICS")
    print("=" * 60)
    print(f"  Saved run ID  : {row_id}")
    print(f"  Result ID     : {result_id}")
    print(f"  Trades        : {summary['total_trades']}")
    print(f"  Win Rate      : {summary['win_rate']:.2%}")
    print(f"  Total R       : {summary['total_r']:+.2f}R")
    print(f"  Max DD (R)    : {summary['max_drawdown_r']:.2f}R")
    print(f"  Calmar        : {summary['calmar_ratio']:.3f}")
    print(f"  Sharpe        : {summary['sharpe_ratio']:.3f}")
    print(f"  Profit Factor : {summary['profit_factor']:.3f}")
    print()
    print("  R by year:")
    for yr, r in summary["r_by_year"].items():
        print(f"    {yr}: {r:+.2f}R")
    print()
    print(f"  Name: {PORTFOLIO_NAME}")
    print("  View in dashboard → Saved Strategies tab")


if __name__ == "__main__":
    main()
