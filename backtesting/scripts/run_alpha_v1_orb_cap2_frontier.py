"""Explore the practical cap=2 frontier for the ALPHA_V1 ORB sleeve.

This follows the broad re-entry study by answering narrower questions:
1. Which ORB legs actually deserve the second same-session trade slot?
2. Should trade 2 depend on how trade 1 ended?

Scope:
- Same 2-year window as the prior re-entry study
- Only the three ORB legs in ALPHA_V1
- No engine changes; this is a post-trade frontier over the cap=2 streams
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import (
    DataCache,
    build_alpha_v1_legs,
    filled_trades,
    portfolio_daily_frame,
    summarize_daily_returns,
)
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.engine.simulator import (
    EXIT_NAMES,
    EXIT_SL,
    EXIT_TP1_TP2,
    EXIT_TP2_SINGLE,
    TradeResult,
)
from orb_backtest.optimize.parallel import run_sweep


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_cap2_frontier"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_CAP2_FRONTIER.md"

START_DATE = "2024-04-17"
END_DATE = "2026-04-17"

LEG_KEYS = (
    "nq_asia_orb_long",
    "es_asia_orb_long",
    "es_ny_orb_long",
)
LEG_LABELS = {
    "nq_asia_orb_long": "NQ Asia ORB",
    "es_asia_orb_long": "ES Asia ORB",
    "es_ny_orb_long": "ES NY ORB",
}


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * 100.0, 2)


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
    daily = portfolio_daily_frame({name: filled_trades(trades) for name, trades in named_streams.items()})
    total_series = daily.sum(axis=1) if not daily.empty else pd.Series(dtype=float)
    summary = summarize_daily_returns(total_series)
    fill_count = sum(len(filled_trades(stream)) for stream in named_streams.values())
    return {
        "fills": fill_count,
        "total_r": _round(summary["total_r"], 2),
        "max_drawdown_r": _round(summary["max_drawdown_r"], 2),
        "sharpe_ratio": _round(summary["sharpe_ratio"], 2),
        "calmar_ratio": _round(summary["calmar_ratio"], 2),
        "negative_days": int(summary["negative_days"]),
    }


def _session_anchor_time(config: StrategyConfig) -> str:
    session = config.sessions[0]
    return session.orb_start or session.rth_start or session.entry_start


def _session_crosses_midnight(config: StrategyConfig) -> bool:
    session = config.sessions[0]
    start_time = _session_anchor_time(config)
    end_time = session.flat_end or session.entry_end
    return bool(start_time and end_time and end_time < start_time)


def _session_day_key(trade: TradeResult, config: StrategyConfig) -> tuple[str, str]:
    session_name = config.sessions[0].name
    ts_str = trade.fill_time or trade.exit_time
    if not ts_str:
        return session_name, trade.date

    ts = pd.Timestamp(ts_str)
    session_date = ts.date()
    if _session_crosses_midnight(config):
        anchor_time = _session_anchor_time(config)
        if ts.strftime("%H:%M") < anchor_time:
            session_date = (ts - pd.Timedelta(days=1)).date()
    return session_name, session_date.isoformat()


def _trade_ordinals(trades: list[TradeResult], config: StrategyConfig) -> list[dict[str, Any]]:
    rows = []
    ordinal_by_day: dict[tuple[str, str], int] = defaultdict(int)
    for trade in sorted(
        filled_trades(trades),
        key=lambda t: (t.date, t.session, t.fill_bar, t.signal_bar, t.exit_bar),
    ):
        key = _session_day_key(trade, config)
        ordinal_by_day[key] += 1
        rows.append(
            {
                "trade": trade,
                "date": key[1],
                "session": key[0],
                "ordinal": ordinal_by_day[key],
            }
        )
    return rows


def _split_cap2_stream(trades: list[TradeResult], config: StrategyConfig) -> dict[str, Any]:
    rows = _trade_ordinals(trades, config)
    grouped: dict[tuple[str, str], list[TradeResult]] = defaultdict(list)
    for row in rows:
        grouped[(row["date"], row["session"])].append(row["trade"])

    days = []
    for key, grouped_trades in grouped.items():
        grouped_trades = sorted(grouped_trades, key=lambda t: (t.fill_bar, t.signal_bar, t.exit_bar))
        first_trade = grouped_trades[0] if grouped_trades else None
        second_trade = grouped_trades[1] if len(grouped_trades) >= 2 else None
        later_trades = grouped_trades[2:] if len(grouped_trades) > 2 else []
        days.append(
            {
                "session_day": key,
                "first_trade": first_trade,
                "second_trade": second_trade,
                "later_trades": later_trades,
                "all_trades": grouped_trades,
            }
        )

    return {
        "rows": rows,
        "days": days,
        "max_trades_per_day": max((len(day["all_trades"]) for day in days), default=0),
        "trade_count_distribution": dict(
            sorted(Counter(len(day["all_trades"]) for day in days if day["all_trades"]).items())
        ),
    }


def _run_leg_variants(
    cache: DataCache,
    base_config: StrategyConfig,
    leg_key: str,
) -> tuple[list[TradeResult], list[TradeResult]]:
    market = cache.get(base_config.instrument)
    cap1 = with_overrides(
        base_config,
        orb_trade_max_per_session=1,
        name=f"{leg_key} cap1 frontier",
        notes="ALPHA_V1 ORB cap=2 frontier baseline leg.",
    )
    cap2 = with_overrides(
        base_config,
        orb_trade_max_per_session=2,
        name=f"{leg_key} cap2 frontier",
        notes="ALPHA_V1 ORB cap=2 frontier candidate leg.",
    )
    results = run_sweep(
        market.df_5m,
        [cap1, cap2],
        n_workers=1,
        start_date=START_DATE,
        end_date=END_DATE,
        df_1m=market.df_1m,
        df_1s=market.df_1s,
    )
    by_name = {config.name: trades for config, trades in results}
    cap1_trades = by_name[cap1.name]
    cap2_trades = by_name[cap2.name]
    if base_config.excluded_days:
        excluded = set(base_config.excluded_days)
        cap1_trades = apply_dow_filter(cap1_trades, excluded)
        cap2_trades = apply_dow_filter(cap2_trades, excluded)
    return cap1_trades, cap2_trades


def _policy_any(_first: TradeResult, _second: TradeResult) -> bool:
    return True


def _policy_after_positive(first: TradeResult, _second: TradeResult) -> bool:
    return first.r_multiple > 0


def _policy_after_nonpositive(first: TradeResult, _second: TradeResult) -> bool:
    return first.r_multiple <= 0


def _policy_after_sl(first: TradeResult, _second: TradeResult) -> bool:
    return first.exit_type == EXIT_SL


def _policy_after_full_target(first: TradeResult, _second: TradeResult) -> bool:
    return first.exit_type in {EXIT_TP1_TP2, EXIT_TP2_SINGLE}


POLICIES: dict[str, tuple[str, Callable[[TradeResult, TradeResult], bool]]] = {
    "any_reentry": ("Keep the second trade whenever it exists.", _policy_any),
    "after_positive_first": ("Only keep trade 2 after a positive trade 1.", _policy_after_positive),
    "after_nonpositive_first": ("Only keep trade 2 after a non-positive trade 1.", _policy_after_nonpositive),
    "after_sl_first": ("Only keep trade 2 after trade 1 stops out.", _policy_after_sl),
    "after_full_target_first": (
        "Only keep trade 2 after trade 1 hits the full target.",
        _policy_after_full_target,
    ),
}


def _combo_label(enabled_legs: tuple[str, ...]) -> str:
    if not enabled_legs:
        return "Cap1 on all ORB legs"
    return "Cap2 on " + " + ".join(LEG_LABELS[key] for key in enabled_legs)


def _build_variant_stream(
    leg_key: str,
    enabled_for_cap2: bool,
    policy_name: str,
    baseline_stream: list[TradeResult],
    cap2_split: dict[str, Any],
) -> tuple[list[TradeResult], int]:
    if not enabled_for_cap2:
        return filled_trades(baseline_stream), 0

    _, policy_fn = POLICIES[policy_name]
    kept: list[TradeResult] = []
    added_reentries = 0
    for day in cap2_split["days"]:
        first_trade = day["first_trade"]
        second_trade = day["second_trade"]
        if first_trade is not None:
            kept.append(first_trade)
        if first_trade is not None and second_trade is not None and policy_fn(first_trade, second_trade):
            kept.append(second_trade)
            added_reentries += 1
    kept.sort(key=lambda t: (t.date, t.session, t.fill_bar, t.signal_bar, t.exit_bar))
    return kept, added_reentries


def _exit_type_rows(leg_key: str, cap2_split: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[TradeResult]] = defaultdict(list)
    for day in cap2_split["days"]:
        first_trade = day["first_trade"]
        second_trade = day["second_trade"]
        if first_trade is None or second_trade is None:
            continue
        groups[EXIT_NAMES.get(first_trade.exit_type, str(first_trade.exit_type))].append(second_trade)

    rows = []
    for exit_name, second_trades in sorted(groups.items()):
        total_r = sum(trade.r_multiple for trade in second_trades)
        rows.append(
            {
                "leg": LEG_LABELS[leg_key],
                "first_exit": exit_name,
                "count": len(second_trades),
                "avg_r_trade2": _round(total_r / len(second_trades), 2),
                "total_r_trade2": _round(total_r, 2),
                "win_rate_pct_trade2": _pct(sum(1 for trade in second_trades if trade.r_multiple > 0) / len(second_trades)),
            }
        )
    return rows


def _sign_rows(leg_key: str, cap2_split: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[TradeResult]] = defaultdict(list)
    for day in cap2_split["days"]:
        first_trade = day["first_trade"]
        second_trade = day["second_trade"]
        if first_trade is None or second_trade is None:
            continue
        bucket = "positive_first" if first_trade.r_multiple > 0 else "nonpositive_first"
        groups[bucket].append(second_trade)

    rows = []
    for label, second_trades in sorted(groups.items()):
        total_r = sum(trade.r_multiple for trade in second_trades)
        rows.append(
            {
                "leg": LEG_LABELS[leg_key],
                "first_bucket": label,
                "count": len(second_trades),
                "avg_r_trade2": _round(total_r / len(second_trades), 2),
                "total_r_trade2": _round(total_r, 2),
                "win_rate_pct_trade2": _pct(sum(1 for trade in second_trades if trade.r_multiple > 0) / len(second_trades)),
            }
        )
    return rows


def _hour_rows(leg_key: str, cap2_split: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[TradeResult]] = defaultdict(list)
    for day in cap2_split["days"]:
        second_trade = day["second_trade"]
        if second_trade is None or not second_trade.fill_time:
            continue
        bucket = pd.Timestamp(second_trade.fill_time).strftime("%H")
        groups[bucket].append(second_trade)

    rows = []
    for hour_bucket, second_trades in sorted(groups.items()):
        total_r = sum(trade.r_multiple for trade in second_trades)
        rows.append(
            {
                "leg": LEG_LABELS[leg_key],
                "fill_hour": hour_bucket,
                "count": len(second_trades),
                "avg_r_trade2": _round(total_r / len(second_trades), 2),
                "total_r_trade2": _round(total_r, 2),
            }
        )
    return rows


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    cache = DataCache(start_date=START_DATE, end_date=END_DATE)
    legs = build_alpha_v1_legs()
    orb_legs = {key: legs[key] for key in LEG_KEYS}

    baseline_streams: dict[str, list[TradeResult]] = {}
    cap2_splits: dict[str, dict[str, Any]] = {}
    diagnostics_exit_rows: list[dict[str, Any]] = []
    diagnostics_sign_rows: list[dict[str, Any]] = []
    diagnostics_hour_rows: list[dict[str, Any]] = []

    for leg_key, leg in orb_legs.items():
        cap1_trades, cap2_trades = _run_leg_variants(cache, leg.config, leg_key)
        baseline_streams[leg_key] = cap1_trades
        cap2_split = _split_cap2_stream(cap2_trades, leg.config)
        cap2_splits[leg_key] = cap2_split
        diagnostics_exit_rows.extend(_exit_type_rows(leg_key, cap2_split))
        diagnostics_sign_rows.extend(_sign_rows(leg_key, cap2_split))
        diagnostics_hour_rows.extend(_hour_rows(leg_key, cap2_split))

    baseline_summary = _daily_sleeve_summary(baseline_streams)

    leg_subsets: list[tuple[str, ...]] = []
    for subset_size in range(0, len(LEG_KEYS) + 1):
        leg_subsets.extend(combinations(LEG_KEYS, subset_size))

    frontier_rows: list[dict[str, Any]] = []
    for enabled_legs in leg_subsets:
        enabled_set = set(enabled_legs)
        for policy_name, (policy_desc, _) in POLICIES.items():
            if not enabled_legs and policy_name != "any_reentry":
                continue

            named_streams: dict[str, list[TradeResult]] = {}
            added_reentries = 0
            for leg_key in LEG_KEYS:
                stream, leg_added = _build_variant_stream(
                    leg_key=leg_key,
                    enabled_for_cap2=leg_key in enabled_set,
                    policy_name=policy_name,
                    baseline_stream=baseline_streams[leg_key],
                    cap2_split=cap2_splits[leg_key],
                )
                named_streams[leg_key] = stream
                added_reentries += leg_added

            sleeve = _daily_sleeve_summary(named_streams)
            frontier_rows.append(
                {
                    "variant": _combo_label(enabled_legs),
                    "policy": policy_name,
                    "policy_desc": policy_desc,
                    "cap2_legs": len(enabled_legs),
                    "added_reentries": added_reentries,
                    "fills": sleeve["fills"],
                    "total_r": sleeve["total_r"],
                    "delta_vs_cap1_r": _round(sleeve["total_r"] - baseline_summary["total_r"], 2),
                    "sharpe_ratio": sleeve["sharpe_ratio"],
                    "max_drawdown_r": sleeve["max_drawdown_r"],
                    "calmar_ratio": sleeve["calmar_ratio"],
                    "negative_days": sleeve["negative_days"],
                }
            )

    top_total_r = sorted(frontier_rows, key=lambda row: (row["total_r"], row["sharpe_ratio"]), reverse=True)[:12]
    top_sharpe = sorted(
        [row for row in frontier_rows if row["delta_vs_cap1_r"] > 0],
        key=lambda row: (row["sharpe_ratio"], row["total_r"]),
        reverse=True,
    )[:12]

    report_lines = [
        "# ALPHA_V1 ORB Cap=2 Frontier",
        "",
        f"- Window: `{START_DATE}` to `{END_DATE}`",
        "- Scope: the three ORB legs in `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`)",
        "- Baseline reference: cap=1 on all ORB legs",
        "- Frontier tested: leg-selective cap=2 plus simple trade-1 outcome policies for trade 2",
        "",
        "## Baseline ORB Sleeve",
        "",
        _markdown_table(
            [
                {
                    "fills": baseline_summary["fills"],
                    "total_r": baseline_summary["total_r"],
                    "sharpe_ratio": baseline_summary["sharpe_ratio"],
                    "max_drawdown_r": baseline_summary["max_drawdown_r"],
                    "calmar_ratio": baseline_summary["calmar_ratio"],
                    "negative_days": baseline_summary["negative_days"],
                }
            ],
            ["fills", "total_r", "sharpe_ratio", "max_drawdown_r", "calmar_ratio", "negative_days"],
        ),
        "",
        "## Trade 2 By First Exit Type",
        "",
        _markdown_table(
            diagnostics_exit_rows,
            ["leg", "first_exit", "count", "avg_r_trade2", "total_r_trade2", "win_rate_pct_trade2"],
        ),
        "",
        "## Trade 2 By First Outcome Sign",
        "",
        _markdown_table(
            diagnostics_sign_rows,
            ["leg", "first_bucket", "count", "avg_r_trade2", "total_r_trade2", "win_rate_pct_trade2"],
        ),
        "",
        "## Trade 2 By Fill Hour",
        "",
        _markdown_table(
            diagnostics_hour_rows,
            ["leg", "fill_hour", "count", "avg_r_trade2", "total_r_trade2"],
        ),
        "",
        "## Top Frontier Variants By Total R",
        "",
        _markdown_table(
            top_total_r,
            [
                "variant",
                "policy",
                "added_reentries",
                "fills",
                "total_r",
                "delta_vs_cap1_r",
                "sharpe_ratio",
                "max_drawdown_r",
                "calmar_ratio",
            ],
        ),
        "",
        "## Top Frontier Variants By Sharpe",
        "",
        _markdown_table(
            top_sharpe,
            [
                "variant",
                "policy",
                "added_reentries",
                "fills",
                "total_r",
                "delta_vs_cap1_r",
                "sharpe_ratio",
                "max_drawdown_r",
                "calmar_ratio",
            ],
        ),
        "",
    ]

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    payload = {
        "window": {"start": START_DATE, "end": END_DATE},
        "baseline": baseline_summary,
        "diagnostics": {
            "by_first_exit": diagnostics_exit_rows,
            "by_first_sign": diagnostics_sign_rows,
            "by_fill_hour": diagnostics_hour_rows,
        },
        "frontier": frontier_rows,
        "top_total_r": top_total_r,
        "top_sharpe": top_sharpe,
        "report_path": str(REPORT_PATH),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("ALPHA_V1 ORB CAP=2 FRONTIER")
    print(f"Window: {START_DATE} to {END_DATE}")
    print("")
    print(_markdown_table(
        top_total_r[:8],
        [
            "variant",
            "policy",
            "added_reentries",
            "total_r",
            "delta_vs_cap1_r",
            "sharpe_ratio",
            "max_drawdown_r",
        ],
    ))
    print("")
    print(f"Report written to: {REPORT_PATH}")
    print(f"Summary JSON written to: {RESULT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
