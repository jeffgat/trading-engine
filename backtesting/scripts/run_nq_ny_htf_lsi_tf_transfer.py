#!/usr/bin/env python3
"""Timeframe transfer study for NQ NY HTF-LSI."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import product
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
    load_shortlist_config,
    load_timeframe_data,
    result_row,
    save_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortlist", type=Path, default=RESULTS_ROOT / "nq_ny_htf_lsi_discovery" / "shortlist.json")
    parser.add_argument("--trade-caps", type=str, default="1,2,3")
    parser.add_argument("--output-dir", type=Path, default=RESULTS_ROOT / "nq_ny_htf_lsi_tf_transfer")
    args = parser.parse_args()

    try:
        ensure_required_data()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    anchor = load_shortlist_config(args.shortlist)
    trade_caps = tuple(int(item.strip()) for item in args.trade_caps.split(",") if item.strip())
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []

    for timeframe in ("5m", "3m", "2m", "1m"):
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
        configs = []
        for direction, entry_mode, cap in product(("long", "short", "both"), ("fvg_limit", "close"), trade_caps):
            configs.append(
                build_config(
                    timeframe=timeframe,
                    direction_filter=direction,
                    entry_mode=entry_mode,
                    entry_start=anchor.sessions[0].entry_start,
                    entry_end=anchor.sessions[0].entry_end,
                    rr=anchor.rr,
                    tp1_ratio=anchor.tp1_ratio,
                    min_gap_atr_pct=anchor.sessions[0].min_gap_atr_pct,
                    atr_length=anchor.atr_length,
                    htf_level_tf_minutes=anchor.htf_level_tf_minutes,
                    htf_n_left=anchor.htf_n_left,
                    htf_trade_max_per_session=cap,
                    lsi_fvg_window_left=anchor.lsi_fvg_window_left,
                    lsi_fvg_window_right=anchor.lsi_fvg_window_right,
                    max_fvg_to_inversion_bars=anchor.max_fvg_to_inversion_bars,
                    name=f"NQ NY HTF_LSI {timeframe} transfer {direction} {entry_mode} cap{cap}",
                )
            )

        results = run_sweep(
            df_base,
            configs,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        rows = [result_row(cfg.name, cfg, trades) | {"timeframe": timeframe} for cfg, trades in results]
        rows.sort(key=lambda row: (row["validation_calmar"], row["validation_pf"]), reverse=True)
        save_json(out_dir / f"{timeframe}.json", rows)
        all_rows.extend(rows[:5])

    all_rows.sort(key=lambda row: (row["validation_calmar"], row["validation_pf"]), reverse=True)
    save_json(out_dir / "summary.json", all_rows)
    print(json.dumps(all_rows[:10], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
