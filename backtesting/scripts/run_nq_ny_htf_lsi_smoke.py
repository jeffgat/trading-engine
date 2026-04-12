#!/usr/bin/env python3
"""Smoke baseline for NQ NY HTF-LSI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.optimize.parallel import run_sweep

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    RESULTS_ROOT,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    result_row,
    save_json,
)


def main() -> int:
    try:
        ensure_required_data()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    configs = [
        build_config(
            timeframe="5m",
            direction_filter="both",
            entry_mode=entry_mode,
            htf_level_tf_minutes=60,
            htf_trade_max_per_session=1,
            name=f"NQ NY HTF_LSI smoke 5m htf60 cap1 both {entry_mode}",
        )
        for entry_mode in ("fvg_limit", "close")
    ]

    results = run_sweep(
        df_base,
        configs,
        n_workers=1,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    rows = [result_row(cfg.name, cfg, trades) for cfg, trades in results]
    save_json(RESULTS_ROOT / "nq_ny_htf_lsi_smoke" / "smoke.json", rows)

    for row in rows:
        print(
            f"{row['label']}: disc_pf={row['discovery_pf']:.3f} "
            f"disc_avg_r={row['discovery_avg_r']:.3f} "
            f"val_pf={row['validation_pf']:.3f} trades={row['pre_holdout_trades']}"
        )

    best_pf = max((row["discovery_pf"] for row in rows), default=0.0)
    max_trades = max((row["pre_holdout_trades"] for row in rows), default=0)
    if best_pf < 0.90 or max_trades < 50:
        print("Smoke baseline failed stop conditions.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
