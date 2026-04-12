#!/usr/bin/env python3
"""MA/EMA/VWAP confluence study for NQ NY HTF-LSI."""

from __future__ import annotations

import argparse
import json
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
    load_shortlist_config,
    load_timeframe_data,
    result_row,
    save_json,
)


TOKENS = ("vwap", "sma20", "ema20", "sma50", "ema50")
MODES = {
    "bounce": (0.0, 0.25),
    "magnet": (-0.25, 0.0),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortlist", type=Path, default=RESULTS_ROOT / "nq_ny_htf_lsi_discovery" / "shortlist.json")
    args = parser.parse_args()

    try:
        ensure_required_data()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    anchor = load_shortlist_config(args.shortlist)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    configs = [anchor]
    for token in TOKENS:
        for mode_name, (min_atr, max_atr) in MODES.items():
            configs.append(
                build_config(
                    timeframe="5m",
                    direction_filter=anchor.direction_filter,
                    entry_mode=anchor.lsi_entry_mode,
                    entry_start=anchor.sessions[0].entry_start,
                    entry_end=anchor.sessions[0].entry_end,
                    rr=anchor.rr,
                    tp1_ratio=anchor.tp1_ratio,
                    min_gap_atr_pct=anchor.sessions[0].min_gap_atr_pct,
                    atr_length=anchor.atr_length,
                    htf_level_tf_minutes=anchor.htf_level_tf_minutes,
                    htf_n_left=anchor.htf_n_left,
                    htf_trade_max_per_session=anchor.htf_trade_max_per_session,
                    lsi_fvg_window_left=anchor.lsi_fvg_window_left,
                    lsi_fvg_window_right=anchor.lsi_fvg_window_right,
                    max_fvg_to_inversion_bars=anchor.max_fvg_to_inversion_bars,
                    entry_context_gate=f"{token}_aligned",
                    entry_context_min_atr=min_atr,
                    entry_context_max_atr=max_atr,
                    name=f"NQ NY HTF_LSI confluence {token} {mode_name}",
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
    rows = [result_row(cfg.name, cfg, trades) for cfg, trades in results]
    rows.sort(key=lambda row: (row["validation_calmar"], row["validation_pf"]), reverse=True)
    save_json(RESULTS_ROOT / "nq_ny_htf_lsi_confluence" / "confluence.json", rows)
    print(json.dumps(rows[:10], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
