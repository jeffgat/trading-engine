#!/usr/bin/env python3
"""Save exact execution-engine historical backtests to the shared DB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader.historical_backtest import (  # noqa: E402
    latest_common_end,
    rolling_year_window_endpoints,
    run_profile_backtest_sync,
    save_profile_backtest,
)
from trader.main import DEFAULT_CONFIG, LSI_SESSION_CONFIGS, SESSION_CONFIGS, load_config, load_exec_configs  # noqa: E402


def _profile_symbols(exec_config) -> list[str]:
    symbols: set[str] = set()
    for session_name, overrides in exec_config.session_overrides.items():
        merged = {**SESSION_CONFIGS.get(session_name, {}), **overrides}
        symbols.add(merged.get("instrument", "NQ"))
    for session_name, overrides in exec_config.lsi_session_overrides.items():
        merged = {**LSI_SESSION_CONFIGS.get(session_name, {}), **overrides}
        symbols.add(merged.get("instrument", "NQ"))
    return sorted(symbols)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to execution live.toml",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        required=True,
        help="Execution profile names from exec_configs.json",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Rolling window size in years",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    exec_configs = {cfg.name: cfg for cfg in load_exec_configs(config)}

    requested = [exec_configs[name] for name in args.profiles]
    symbols = sorted({symbol for cfg in requested for symbol in _profile_symbols(cfg)})
    common_end = latest_common_end(symbols)
    start_date, end_date = rolling_year_window_endpoints(common_end, args.years)

    print(f"Common latest data timestamp: {common_end.isoformat()}")
    print(f"Replay window: {start_date} -> {end_date}")

    for profile_name in args.profiles:
        result = run_profile_backtest_sync(
            config=config,
            profile_name=profile_name,
            start_date=start_date,
            end_date=end_date,
            latest_data_ts=common_end,
            label=f"EXEC EXACT {profile_name} Last {args.years}Y {start_date} to {end_date}",
        )
        result_id = save_profile_backtest(result)
        print(
            f"{profile_name}: {result_id} | trades={result['summary']['total_trades']} "
            f"pnl={result['summary']['total_pnl_usd']:.2f} sharpe={result['summary']['sharpe_ratio']:.2f}"
        )


if __name__ == "__main__":
    main()
