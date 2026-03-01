#!/usr/bin/env python3
"""Query experiment tracking database.

Usage:
    python scripts/query_experiments.py
    python scripts/query_experiments.py --instrument NQ --min-sharpe 1.0
    python scripts/query_experiments.py --param ny_stop_atr_pct=15:20
    python scripts/query_experiments.py --sessions NY --csv results.csv
    python scripts/query_experiments.py --name "atr_stops_baseline"
    python scripts/query_experiments.py --after 2026-02-01 --before 2026-02-14
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tabulate import tabulate
from orb_backtest.experiments import query_runs


def parse_param_filter(spec: str) -> tuple[str, tuple[float, float]]:
    """Parse 'name=min:max' into (name, (min, max))."""
    name, range_str = spec.split("=", 1)
    parts = range_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid param filter: {spec} (expected name=min:max)")
    return name, (float(parts[0]), float(parts[1]))


def main():
    parser = argparse.ArgumentParser(description="Query ORB experiment tracking DB")
    parser.add_argument("--instrument", default=None, help="Filter by instrument (e.g. NQ)")
    parser.add_argument("--sessions", default=None, help="Filter by sessions (e.g. NY, NY+Asia)")
    parser.add_argument("--min-pf", type=float, default=None, help="Min profit factor")
    parser.add_argument("--min-sharpe", type=float, default=None, help="Min Sharpe ratio")
    parser.add_argument("--name", default=None, help="Filter by experiment name (partial match)")
    parser.add_argument("--after", default=None, help="Runs after this date (YYYY-MM-DD)")
    parser.add_argument("--before", default=None, help="Runs before this date (YYYY-MM-DD)")
    parser.add_argument("--param", action="append", default=None,
                        help="Param filter: name=min:max (repeatable)")
    parser.add_argument("--type", default=None, choices=["backtest", "optimization"],
                        help="Filter by run type")
    parser.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    parser.add_argument("--csv", default=None, metavar="FILE", help="Export to CSV file")

    args = parser.parse_args()

    # Build filters
    filters = {}
    if args.instrument:
        filters["instrument"] = args.instrument
    if args.sessions:
        filters["sessions"] = args.sessions
    if args.min_pf is not None:
        filters["min_profit_factor"] = args.min_pf
    if args.min_sharpe is not None:
        filters["min_sharpe"] = args.min_sharpe
    if args.name:
        filters["experiment_name"] = args.name
    if args.after:
        filters["date_from"] = args.after
    if args.before:
        filters["date_to"] = args.before
    if args.type:
        filters["run_type"] = args.type

    # Parse param filters
    if args.param:
        param_filters = {}
        for spec in args.param:
            name, bounds = parse_param_filter(spec)
            param_filters[name] = bounds
        filters["param_filters"] = param_filters

    rows = query_runs(limit=args.limit, **filters)

    if not rows:
        print("No matching runs found.")
        return

    # Build display table
    table_rows = []
    for r in rows:
        metrics = json.loads(r["metrics_json"]) if isinstance(r["metrics_json"], str) else r["metrics_json"]
        table_rows.append({
            "id": r["id"],
            "timestamp": r["timestamp"][:16],
            "type": r["run_type"],
            "instrument": r.get("instrument", ""),
            "sessions": r.get("sessions", ""),
            "trades": r["total_trades"],
            "win_rate": f"{metrics.get('win_rate', 0):.1%}",
            "pnl": f"${metrics.get('total_pnl_usd', 0):,.0f}",
            "pf": f"{metrics.get('profit_factor', 0):.2f}",
            "sharpe": f"{metrics.get('sharpe_ratio', 0):.3f}",
            "name": r.get("experiment_name") or "",
        })

    print(tabulate(table_rows, headers="keys", tablefmt="simple"))
    print(f"\n{len(rows)} run(s) found.")

    # CSV export
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=table_rows[0].keys())
            writer.writeheader()
            writer.writerows(table_rows)
        print(f"Exported to {args.csv}")


if __name__ == "__main__":
    main()
