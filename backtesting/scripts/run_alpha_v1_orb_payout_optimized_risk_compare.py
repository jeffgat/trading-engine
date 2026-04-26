#!/usr/bin/env python3
"""Compare ALPHA_V1 ORB sleeve profiles using funded first-payout optimized risk.

Why this exists:
- The earlier ALPHA_V1 ORB prop comparison used an R-threshold challenge model.
- In that model, changing the dollar value of 1R does not change payout or breach
  counts; it only changes cash EV.
- To make "risk optimization" meaningful, this script switches to the repo's
  funded first-payout USD model, sweeps pre-payout risk, freezes the best funded
  risk per profile, then reruns the comparison windows.

Scope:
- ORB sleeve only: NQ Asia, ES Asia, ES NY from ALPHA_V1
- Baseline: all three legs stay at cap=1
- Optimized rules:
  * NQ Asia -> cap=2 after_nonpositive_first
  * ES Asia -> cap=2 after_nonpositive_first
  * ES NY   -> cap=2 any_reentry

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
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import (
    build_alpha_v1_legs,
    filled_trades,
    portfolio_daily_frame,
    summarize_daily_returns,
)
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (
    FundedFirstPayoutProfile,
    build_funded_first_payout_scorecard,
    simulate_funded_first_payouts,
)
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import TradeResult, build_maps, build_signal_cache
from orb_backtest.optimize.parallel import run_sweep


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_payout_optimized_risk_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_PAYOUT_OPTIMIZED_RISK_COMPARE.md"

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

FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0,
    starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0,
    max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0,
    risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0,
)
RISK_VALUES = (200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0, 550.0, 600.0)


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
        notes=f"ALPHA_V1 ORB {profile_key} payout-optimized funded compare.",
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
    return pd.Series(df_5m.index[mask].date).drop_duplicates().astype(str).tolist()


def _combined_trade_stream(named_streams: dict[str, list[TradeResult]]) -> list[TradeResult]:
    return sorted(
        [trade for stream in named_streams.values() for trade in filled_trades(stream)],
        key=lambda t: (t.date, t.session, t.fill_time or "", t.fill_bar, t.signal_bar, t.exit_time or "", t.exit_bar),
    )


def _rank_score(row: pd.Series) -> float:
    payout_rate = float(row["payout_rate"])
    breach_rate = float(row["breach_rate"])
    avg_days = float(row["average_days_to_payout"] or 999.0)
    median_days = float(row["median_days_to_payout"] or 999.0)
    return round(
        (payout_rate * 100.0)
        - (breach_rate * 35.0)
        - (avg_days * 0.35)
        - (median_days * 0.15),
        3,
    )


def _sweep_profile_risk(
    *,
    profile_key: str,
    trades: list[TradeResult],
    trading_dates: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for risk in RISK_VALUES:
        funded_profile = replace(
            FUNDED_PROFILE,
            risk_pre_payout_usd=risk,
            risk_post_payout_usd=max(100.0, risk / 2.0),
        )
        outcomes = simulate_funded_first_payouts(
            specialist_name=f"alpha_v1_orb_{profile_key}_risk_{int(risk)}",
            trades=trades,
            trading_dates=trading_dates,
            profile=funded_profile,
        )
        score = build_funded_first_payout_scorecard(outcomes, funded_profile)
        row = {
            "risk_pre_usd": int(risk),
            "risk_post_usd": int(max(100.0, risk / 2.0)),
            "starts": int(score["total_starts"]),
            "payout_rate": float(score["payout_rate"]),
            "breach_rate": float(score["breach_rate"]),
            "open_rate": float(score["open_rate"]),
            "average_days_to_payout": score["average_days_to_payout"],
            "median_days_to_payout": score["median_days_to_payout"],
            "average_trades_to_payout": score["average_trades_to_payout"],
            "average_first_payout_amount_usd": score["average_first_payout_amount_usd"],
            "average_net_after_fee_usd": score["average_net_after_fee_usd"],
            "ev_per_start_usd": float(score["ev_per_start_usd"]),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df["rank_score"] = df.apply(_rank_score, axis=1)
    df = df.sort_values("risk_pre_usd").reset_index(drop=True)
    best = df.sort_values(
        by=["rank_score", "payout_rate", "breach_rate", "average_days_to_payout", "ev_per_start_usd"],
        ascending=[False, False, True, True, False],
    ).iloc[0]
    return {
        "best_row": {k: (v.item() if hasattr(v, "item") else v) for k, v in best.to_dict().items()},
        "rows": [{k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()} for row in df.to_dict(orient="records")],
    }


def _write_report(payload: dict[str, Any]) -> None:
    lines = [
        "# ALPHA_V1 ORB Payout-Optimized Risk Compare",
        "",
        "- Scope: the three ORB legs from `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`).",
        "- Comparison:",
        "  - `Current single-trade legs` = all three ORB legs keep `orb_trade_max_per_session=1`.",
        "  - `Optimized rules` = `NQ Asia cap=2 after_nonpositive_first`, `ES Asia cap=2 after_nonpositive_first`, `ES NY cap=2 any_reentry`.",
        "- Important: the earlier R-based prop table cannot respond to dollar risk changes. This rerun uses the funded first-payout USD model instead.",
        "- Funded model: `$50k` start, `$2k` trailing EOD DD capped at `$50k`, first payout floor `$52.5k`, challenge fee `$100`.",
        "- Risk sweep: `risk_pre_payout_usd` in `200..600` by `50`, with `risk_post_payout_usd = max(100, risk_pre / 2)`.",
        "- Best-risk selection rule copied from the existing portfolio first-payout sweep: maximize payout-heavy rank score with breach and time-to-payout penalties.",
        "",
        "## Chosen Risk Settings",
        "",
    ]

    risk_rows = []
    for profile_key, sweep in payload["risk_sweeps"].items():
        best = sweep["best_row"]
        risk_rows.append(
            {
                "rules": PROFILE_SPECS[profile_key]["label"],
                "risk_pre_usd": best["risk_pre_usd"],
                "risk_post_usd": best["risk_post_usd"],
                "payout_rate": _round(best["payout_rate"] * 100.0, 2),
                "breach_rate": _round(best["breach_rate"] * 100.0, 2),
                "avg_days_to_payout": best["average_days_to_payout"],
                "ev_per_start_usd": _round(best["ev_per_start_usd"], 2),
                "rank_score": best["rank_score"],
            }
        )
    lines.append(
        _markdown_table(
            risk_rows,
            [
                "rules",
                "risk_pre_usd",
                "risk_post_usd",
                "payout_rate",
                "breach_rate",
                "avg_days_to_payout",
                "ev_per_start_usd",
                "rank_score",
            ],
        )
    )

    lines.extend(["", "## Comparison Table", ""])
    lines.append(
        _markdown_table(
            payload["comparison_rows"],
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
        )
    )

    lines.extend(["", "## Notes", ""])
    lines.append("- `max_dd_r` and `net_r` stay in R-space, so they are unchanged from the earlier comparison.")
    lines.append("- The funded-account payout/breach counts and rates are the fields that actually change when risk sizing changes.")

    REPORT_PATH.write_text("\n".join(lines))


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

    full_trading_dates = _trading_dates_from_df(trading_dates_source, FULL_START, AVAILABLE_END)
    risk_sweeps: dict[str, dict[str, Any]] = {}
    for profile_key in PROFILE_SPECS:
        combined_trades = _combined_trade_stream(window_profile_streams["last_10y_available"][profile_key])
        risk_sweeps[profile_key] = _sweep_profile_risk(
            profile_key=profile_key,
            trades=combined_trades,
            trading_dates=full_trading_dates,
        )
        best = risk_sweeps[profile_key]["best_row"]
        print(
            f"[risk] {profile_key}: pre ${best['risk_pre_usd']} / post ${best['risk_post_usd']} | "
            f"payout {best['payout_rate']:.1%} | breach {best['breach_rate']:.1%} | "
            f"avg days {best['average_days_to_payout']}"
        )

    comparison_rows: list[dict[str, Any]] = []
    payload_rows: list[dict[str, Any]] = []
    for window in WINDOWS:
        trading_dates = _trading_dates_from_df(trading_dates_source, window["start"], window["end"])
        for profile_key, profile_spec in PROFILE_SPECS.items():
            named_streams = window_profile_streams[window["key"]][profile_key]
            sleeve = _daily_sleeve_summary(named_streams)
            combined_trades = _combined_trade_stream(named_streams)
            best = risk_sweeps[profile_key]["best_row"]
            funded_profile = replace(
                FUNDED_PROFILE,
                risk_pre_payout_usd=float(best["risk_pre_usd"]),
                risk_post_payout_usd=float(best["risk_post_usd"]),
            )
            outcomes = simulate_funded_first_payouts(
                specialist_name=f"alpha_v1_orb_{profile_key}_{window['key']}",
                trades=combined_trades,
                trading_dates=trading_dates,
                profile=funded_profile,
            )
            scorecard = build_funded_first_payout_scorecard(outcomes, funded_profile)
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
                "payout_rate": _round(scorecard["payout_rate"] * 100.0, 2),
                "breach_rate": _round(scorecard["breach_rate"] * 100.0, 2),
                "resolved_payout_rate": _round(resolved_payout_rate * 100.0, 2) if resolved_payout_rate is not None else None,
            }
            comparison_rows.append(row)
            payload_rows.append(
                {
                    **row,
                    "risk_pre_usd": int(best["risk_pre_usd"]),
                    "risk_post_usd": int(best["risk_post_usd"]),
                    "open_rate": _round(scorecard["open_rate"] * 100.0, 2),
                    "average_days_to_payout": scorecard["average_days_to_payout"],
                    "ev_per_start_usd": _round(scorecard["ev_per_start_usd"], 2),
                }
            )

    payload = {
        "info": {
            "scope": "ALPHA_V1 ORB sleeve only",
            "full_start": FULL_START,
            "available_end": AVAILABLE_END,
            "risk_values": list(RISK_VALUES),
            "funded_profile_base": {
                "challenge_fee": FUNDED_PROFILE.challenge_fee,
                "starting_balance_usd": FUNDED_PROFILE.starting_balance_usd,
                "trailing_drawdown_usd": FUNDED_PROFILE.trailing_drawdown_usd,
                "max_trailing_breach_usd": FUNDED_PROFILE.max_trailing_breach_usd,
                "first_payout_floor_usd": FUNDED_PROFILE.first_payout_floor_usd,
            },
            "selection_rule": "portfolio first-payout rank_score",
        },
        "risk_sweeps": risk_sweeps,
        "comparison_rows": comparison_rows,
        "detailed_rows": payload_rows,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))
    _write_report(payload)

    print("ALPHA_V1 ORB PAYOUT-OPTIMIZED RISK COMPARE")
    print("=" * 72)
    for row in comparison_rows:
        print(row)
    print(f"\nWrote {RESULT_DIR / 'summary.json'}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
