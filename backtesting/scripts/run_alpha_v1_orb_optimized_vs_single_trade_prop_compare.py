"""Compare ALPHA_V1 ORB optimized re-entry rules vs current single-trade legs.

Scope:
- ORB sleeve only: NQ Asia, ES Asia, ES NY from ALPHA_V1
- Baseline: all three legs stay at cap=1
- Optimized rules:
  * NQ Asia -> cap=2 after_nonpositive_first
  * ES Asia -> cap=2 after_nonpositive_first
  * ES NY   -> cap=2 any_reentry
- Metrics:
  * combined sleeve net R / max DD
  * prop phase-one payout + breach counts and rates

Windows:
- Last 10 years available in repo: 2016-04-17 to 2026-03-24
- Calendar 2024: 2024-01-01 to 2024-12-31
- Calendar 2025: 2025-01-01 to 2025-12-31
- Calendar 2026 YTD available: 2026-01-01 to 2026-03-24
"""

from __future__ import annotations

import gc
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import build_alpha_v1_legs, filled_trades, portfolio_daily_frame, summarize_daily_returns
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import PropFirmProfile, build_prop_scorecard, simulate_account_attempts
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import TradeResult, build_maps, build_signal_cache
from orb_backtest.optimize.parallel import run_sweep


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_optimized_vs_single_trade_prop_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_OPTIMIZED_VS_SINGLE_TRADE_PROP_COMPARE.md"

FULL_START = "2016-04-17"
AVAILABLE_END = "2026-03-24"

ORB_LEG_KEYS = (
    "nq_asia_orb_long",
    "es_asia_orb_long",
    "es_ny_orb_long",
)
PROFILE_SPECS = {
    "current_single_trade": {
        "label": "Current single-trade legs",
        "orb_trade_max_per_session_by_leg": {
            "nq_asia_orb_long": 1,
            "es_asia_orb_long": 1,
            "es_ny_orb_long": 1,
        },
        "orb_reentry_policy_by_leg": {
            "nq_asia_orb_long": "any_reentry",
            "es_asia_orb_long": "any_reentry",
            "es_ny_orb_long": "any_reentry",
        },
    },
    "optimized_rules": {
        "label": "Optimized rules",
        "orb_trade_max_per_session_by_leg": {
            "nq_asia_orb_long": 2,
            "es_asia_orb_long": 2,
            "es_ny_orb_long": 2,
        },
        "orb_reentry_policy_by_leg": {
            "nq_asia_orb_long": "after_nonpositive_first",
            "es_asia_orb_long": "after_nonpositive_first",
            "es_ny_orb_long": "any_reentry",
        },
    },
}
WINDOWS = (
    {
        "key": "last_10y_available",
        "label": "Last 10y available",
        "start": FULL_START,
        "end": AVAILABLE_END,
    },
    {
        "key": "calendar_2024",
        "label": "2024",
        "start": "2024-01-01",
        "end": "2024-12-31",
    },
    {
        "key": "calendar_2025",
        "label": "2025",
        "start": "2025-01-01",
        "end": "2025-12-31",
    },
    {
        "key": "calendar_2026_ytd",
        "label": "2026 YTD",
        "start": "2026-01-01",
        "end": AVAILABLE_END,
    },
)

PROP_PROFILE = PropFirmProfile(
    account_fee=50.0,
    reset_fee=50.0,
    payout_split=0.80,
    payout_target_r=5.0,
    breach_limit_r=-4.0,
    daily_loss_limit_r=-2.0,
    min_trading_days=5,
    cohort_sizes=(10, 25, 50),
    block_size_days=14,
)


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        if abs(value) >= 100 or value == int(value):
            return f"{value:.0f}"
        return f"{value:.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |")
    return "\n".join([header, sep, *body]) if body else "\n".join([header, sep])


def _daily_sleeve_summary(named_streams: dict[str, list[TradeResult]]) -> dict[str, Any]:
    filled_streams = {name: filled_trades(trades) for name, trades in named_streams.items()}
    daily = portfolio_daily_frame(filled_streams)
    total_series = daily.sum(axis=1) if not daily.empty else pd.Series(dtype=float)
    summary = summarize_daily_returns(total_series)
    fill_count = sum(len(stream) for stream in filled_streams.values())
    return {
        "fills": fill_count,
        "net_r": _round(summary["total_r"], 2),
        "max_dd_r": _round(summary["max_drawdown_r"], 2),
        "sharpe_ratio": _round(summary["sharpe_ratio"], 2),
    }


def _load_market_data(base_config: StrategyConfig) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    df_5m = load_5m_data(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    try:
        df_1m = load_1m_for_5m(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    except FileNotFoundError:
        df_1m = None
    try:
        df_1s = load_1s_for_5m(base_config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    except FileNotFoundError:
        df_1s = None
    return df_5m, df_1m, df_1s


def _make_leg_config(leg_key: str, base_config: StrategyConfig, profile_key: str) -> StrategyConfig:
    profile = PROFILE_SPECS[profile_key]
    trade_cap = profile["orb_trade_max_per_session_by_leg"][leg_key]
    policy = profile["orb_reentry_policy_by_leg"][leg_key]
    return with_overrides(
        base_config,
        name=f"{leg_key}_{profile_key}",
        notes=f"ALPHA_V1 ORB {profile_key} prop compare.",
        orb_trade_max_per_session=trade_cap,
        orb_reentry_policy=policy,
    )


def _run_window(
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame | None,
    df_1s: pd.DataFrame | None,
    configs: list[StrategyConfig],
    maps: dict,
    signal_cache: dict,
    *,
    start_date: str,
    end_date: str,
) -> dict[str, list[TradeResult]]:
    results = run_sweep(
        df_5m,
        configs,
        n_workers=min(len(configs), 6),
        start_date=start_date,
        end_date=end_date,
        df_1m=df_1m,
        df_1s=df_1s,
        _prebuilt_maps=maps,
        _prebuilt_signal_cache=signal_cache,
    )
    by_name: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        by_name[config.name] = trades
    return by_name


def _trading_dates_from_df(df_5m: pd.DataFrame, start: str, end: str) -> list[str]:
    mask = (df_5m.index >= pd.Timestamp(start)) & (df_5m.index <= pd.Timestamp(end) + pd.Timedelta(days=1))
    dates = pd.Series(df_5m.index[mask].date).drop_duplicates().astype(str).tolist()
    return dates


def _combined_trade_stream(named_streams: dict[str, list[TradeResult]]) -> list[TradeResult]:
    return sorted(
        [trade for stream in named_streams.values() for trade in filled_trades(stream)],
        key=lambda t: (t.date, t.session, t.fill_time or "", t.fill_bar, t.signal_bar, t.exit_time or "", t.exit_bar),
    )


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    legs = build_alpha_v1_legs()
    orb_legs = {key: legs[key] for key in ORB_LEG_KEYS}
    grouped_leg_keys: dict[str, list[str]] = defaultdict(list)
    for leg_key in ORB_LEG_KEYS:
        grouped_leg_keys[orb_legs[leg_key].config.instrument.symbol].append(leg_key)

    trading_dates_source: pd.DataFrame | None = None
    window_profile_streams: dict[str, dict[str, dict[str, list[TradeResult]]]] = {
        window["key"]: {profile_key: {} for profile_key in PROFILE_SPECS}
        for window in WINDOWS
    }

    for symbol, leg_keys in grouped_leg_keys.items():
        base_config = orb_legs[leg_keys[0]].config
        df_5m, df_1m, df_1s = _load_market_data(base_config)
        if trading_dates_source is None:
            trading_dates_source = df_5m

        configs: list[StrategyConfig] = []
        config_by_leg_profile: dict[tuple[str, str], StrategyConfig] = {}
        for leg_key in leg_keys:
            for profile_key in PROFILE_SPECS:
                config = _make_leg_config(leg_key, orb_legs[leg_key].config, profile_key)
                configs.append(config)
                config_by_leg_profile[(leg_key, profile_key)] = config

        print(f"[compare] Loading maps for {symbol} ({len(df_5m):,} 5m rows)")
        maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
        print(f"[compare] Building signal cache for {symbol}")
        signal_cache = build_signal_cache(df_5m, configs)

        for window in WINDOWS:
            print(
                f"[compare] {symbol} {window['label']} "
                f"({window['start']} to {window['end']})"
            )
            by_name = _run_window(
                df_5m,
                df_1m,
                df_1s,
                configs,
                maps,
                signal_cache,
                start_date=window["start"],
                end_date=window["end"],
            )
            for leg_key in leg_keys:
                for profile_key in PROFILE_SPECS:
                    config = config_by_leg_profile[(leg_key, profile_key)]
                    window_profile_streams[window["key"]][profile_key][leg_key] = by_name[config.name]

        del maps
        del signal_cache
        del df_5m
        del df_1m
        del df_1s
        gc.collect()

    if trading_dates_source is None:
        raise ValueError("No trading dates source loaded.")

    comparison_rows: list[dict[str, Any]] = []
    payload_rows: list[dict[str, Any]] = []
    for window in WINDOWS:
        trading_dates = _trading_dates_from_df(trading_dates_source, window["start"], window["end"])
        for profile_key, profile_spec in PROFILE_SPECS.items():
            named_streams = window_profile_streams[window["key"]][profile_key]
            sleeve = _daily_sleeve_summary(named_streams)
            combined_trades = _combined_trade_stream(named_streams)
            outcomes = simulate_account_attempts(
                specialist_name=f"alpha_v1_orb_{profile_key}_{window['key']}",
                trades=combined_trades,
                trading_dates=trading_dates,
                profile=PROP_PROFILE,
                risk_per_r_usd=5000.0,
            )
            scorecard = build_prop_scorecard(outcomes, PROP_PROFILE)
            payouts = int((outcomes["outcome"] == "payout").sum()) if not outcomes.empty else 0
            breaches = int((outcomes["outcome"] == "breach").sum()) if not outcomes.empty else 0
            resolved = payouts + breaches
            resolved_payout_rate = payouts / resolved if resolved else None

            row = {
                "period": window["label"],
                "window": f"{window['start']} to {window['end']}",
                "rules": profile_spec["label"],
                "max_dd_r": sleeve["max_dd_r"],
                "net_r": sleeve["net_r"],
                "payouts": payouts,
                "breaches": breaches,
                "payout_rate": _round(scorecard["first_payout_rate"] * 100.0, 2),
                "breach_rate": _round(scorecard["breach_rate"] * 100.0, 2),
                "payout_vs_breach_rate": f"{_round(scorecard['first_payout_rate'] * 100.0, 2)}% / {_round(scorecard['breach_rate'] * 100.0, 2)}%",
                "resolved_payout_rate": _round(resolved_payout_rate * 100.0, 2) if resolved_payout_rate is not None else None,
            }
            comparison_rows.append(row)
            payload_rows.append(
                {
                    **row,
                    "scorecard": scorecard,
                    "total_attempts": int(scorecard["total_attempts"]),
                    "open": int((outcomes["outcome"] == "open").sum()) if not outcomes.empty else 0,
                    "sharpe_ratio": sleeve["sharpe_ratio"],
                }
            )

    report_lines = [
        "# ALPHA_V1 ORB Optimized Rules Vs Single-Trade Legs",
        "",
        "- Scope: the three ORB legs from `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`).",
        "- Comparison:",
        "  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.",
        "  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.",
        "- Prop scorecard model: `+5R` payout, `-4R` breach, `-2R` daily loss limit, `5` minimum trading days, `$50` fee + `$50` reset, `80%` payout split.",
        f"- Last 10 years available in repo: `{FULL_START}` to `{AVAILABLE_END}`.",
        f"- `2026` is partial in this repo: `{WINDOWS[-1]['start']}` to `{WINDOWS[-1]['end']}`.",
        "",
        "## Comparison Table",
        "",
        _markdown_table(
            comparison_rows,
            [
                "period",
                "window",
                "rules",
                "max_dd_r",
                "net_r",
                "payouts",
                "breaches",
                "payout_rate",
                "breach_rate",
                "resolved_payout_rate",
            ],
        ),
        "",
    ]

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload_rows, indent=2), encoding="utf-8")

    print("ALPHA_V1 ORB OPTIMIZED VS SINGLE-TRADE PROP COMPARE")
    print(f"Available history: {FULL_START} to {AVAILABLE_END}")
    print("")
    print(
        _markdown_table(
            comparison_rows,
            [
                "period",
                "rules",
                "max_dd_r",
                "net_r",
                "payouts",
                "breaches",
                "payout_rate",
                "breach_rate",
                "resolved_payout_rate",
            ],
        )
    )
    print("")
    print(f"Report written to: {REPORT_PATH}")
    print(f"Summary JSON written to: {RESULT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
