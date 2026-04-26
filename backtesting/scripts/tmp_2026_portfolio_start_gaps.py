#!/usr/bin/env python3
from __future__ import annotations

import statistics
from collections import defaultdict

import pandas as pd

from run_alpha_v1_orb_r_trigger_stagger_compare import (
    AVAILABLE_END,
    ORB_LEG_KEYS,
    R_TRIGGER,
    _build_r_trigger_start_dates,
    _load_market_data,
    _make_leg_config,
    _run_window,
    _subject_daily_series,
    _trading_dates_from_df,
    build_alpha_v1_legs,
    build_maps,
    build_signal_cache,
    datetime,
)


def main() -> None:
    start = "2026-01-01"
    end = AVAILABLE_END
    profiles = ("current_single_trade", "optimized_rules")

    legs = build_alpha_v1_legs()
    orb_legs = {key: legs[key] for key in ORB_LEG_KEYS}
    grouped_leg_keys: dict[str, list[str]] = defaultdict(list)
    for leg_key in ORB_LEG_KEYS:
        symbol = orb_legs[leg_key].config.instrument.symbol
        grouped_leg_keys[symbol].append(leg_key)

    window_profile_streams = {profile_key: {} for profile_key in profiles}
    window_symbol_dates: dict[str, list[str]] = {}

    for symbol, leg_keys in grouped_leg_keys.items():
        base_config = orb_legs[leg_keys[0]].config
        df_5m, df_1m, df_1s = _load_market_data(base_config)
        window_symbol_dates[symbol] = _trading_dates_from_df(df_5m, start, end)

        configs = []
        config_by_leg_profile = {}
        for leg_key in leg_keys:
            for profile_key in profiles:
                config = _make_leg_config(leg_key, orb_legs[leg_key].config, profile_key)
                configs.append(config)
                config_by_leg_profile[(leg_key, profile_key)] = config

        maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
        signal_cache = build_signal_cache(df_5m, configs)
        by_name = _run_window(
            df_5m,
            df_1m,
            df_1s,
            configs,
            maps,
            signal_cache,
            start_date=start,
            end_date=end,
        )
        for leg_key in leg_keys:
            for profile_key in profiles:
                config = config_by_leg_profile[(leg_key, profile_key)]
                window_profile_streams[profile_key][leg_key] = by_name[config.name]

    trading_dates = sorted({d for dates in window_symbol_dates.values() for d in dates})

    for profile_key in profiles:
        daily_series, _ = _subject_daily_series("portfolio", window_profile_streams[profile_key], trading_dates)
        dated_daily_r = [
            (date_str, float(daily_series.loc[pd.Timestamp(date_str)]))
            for date_str in trading_dates
        ]
        starts = _build_r_trigger_start_dates(dated_daily_r, R_TRIGGER)
        dt_starts = [datetime.strptime(s, "%Y-%m-%d") for s in starts]
        all_gaps = [(dt_starts[i] - dt_starts[i - 1]).days for i in range(1, len(dt_starts))]

        unique_starts: list[str] = []
        for s in starts:
            if not unique_starts or unique_starts[-1] != s:
                unique_starts.append(s)
        dt_unique = [datetime.strptime(s, "%Y-%m-%d") for s in unique_starts]
        unique_gaps = [(dt_unique[i] - dt_unique[i - 1]).days for i in range(1, len(dt_unique))]

        print(profile_key)
        print("starts", starts)
        print("avg_gap_all_launches", round(statistics.mean(all_gaps), 2) if all_gaps else None)
        print("avg_gap_unique_dates", round(statistics.mean(unique_gaps), 2) if unique_gaps else None)
        print("median_gap_all_launches", round(statistics.median(all_gaps), 2) if all_gaps else None)
        print("median_gap_unique_dates", round(statistics.median(unique_gaps), 2) if unique_gaps else None)
        print("---")


if __name__ == "__main__":
    main()
