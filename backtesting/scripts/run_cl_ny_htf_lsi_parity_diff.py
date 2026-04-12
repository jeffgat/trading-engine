#!/usr/bin/env python3
"""Trade-level parity diff for the frozen CL NY HTF-LSI 1m lead."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EXEC_ROOT = ROOT.parent / "execution"
EXEC_SRC = EXEC_ROOT / "src"
EXEC_SCRIPTS = EXEC_ROOT / "scripts"

for path in (ROOT / "src", Path(__file__).resolve().parent, EXEC_SRC, EXEC_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_cl_ny_htf_lsi_exact_replay import (  # noqa: E402
    FULL_START,
    HOLDOUT_START,
    PRE_HOLDOUT_END,
    _load_candidate,
    _run_exact_replay,
    _target_end_date,
)
from run_cross_asset_htf_lsi_broad_discovery import build_config, load_timeframe_data  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.export import results_to_dict  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "cl_ny_htf_lsi_parity_diff"
OUTPUT_JSON = OUTPUT_DIR / "parity_diff.json"
REPORT_PATH = ROOT / "learnings" / "reports" / "CL_NY_HTF_LSI_PARITY_DIFF.md"


def _hhmm(ts: str | None) -> str:
    return (ts or "")[11:16]


def _entry_minute(ts: str | None) -> str:
    return (ts or "")[:16]


def _same_trade_key(trade: dict) -> tuple:
    return (
        trade.get("date"),
        round(float(trade.get("entry_price") or 0.0), 4),
        round(float(trade.get("htf_level_price") or 0.0), 4),
        trade.get("fvg_to_inversion_bars"),
    )


def _strict_key(trade: dict) -> tuple:
    return (trade.get("date"), _entry_minute(trade.get("entry_time")))


def _slice_window(rows: list[dict], which: str) -> list[dict]:
    if which == "pre_holdout":
        return [row for row in rows if row["date"] <= PRE_HOLDOUT_END]
    if which == "holdout":
        return [row for row in rows if row["date"] >= HOLDOUT_START]
    raise ValueError(f"Unknown window {which!r}")


def _load_research_trades(end_date: str) -> tuple[list[dict], list[dict]]:
    candidate = _load_candidate()
    config = build_config(
        symbol="CL",
        timeframe=str(candidate["timeframe"]),
        direction_filter=str(candidate["direction_filter"]),
        entry_mode=str(candidate["entry_mode"]),
        entry_start=str(candidate["entry_start"]),
        entry_end=str(candidate["entry_end"]),
        rr=float(candidate["rr"]),
        tp1_ratio=float(candidate["tp1_ratio"]),
        min_gap_atr_pct=float(candidate["min_gap_atr_pct"]),
        atr_length=int(candidate["atr_length"]),
        htf_level_tf_minutes=int(candidate["htf_level_tf_minutes"]),
        htf_n_left=int(candidate["htf_n_left"]),
        htf_trade_max_per_session=int(candidate["htf_trade_max_per_session"]),
        lsi_fvg_window_left=int(candidate["lsi_fvg_window_left"]),
        lsi_fvg_window_right=int(candidate["lsi_fvg_window_right"]),
        max_fvg_to_inversion_bars=int(candidate["max_fvg_to_inversion_bars"]),
        min_stop_points=float(candidate["min_stop_points"]),
        min_tp1_points=float(candidate["min_tp1_points"]),
        name="CL NY HTF_LSI parity diff research",
    )
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("CL", str(candidate["timeframe"]))
    maps = build_maps(df_base)
    signal_cache = build_signal_cache(df_base, [config], signal_df_1m=signal_df_1m)
    trades = run_backtest(
        df_base,
        config,
        start_date=FULL_START,
        end_date=(pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    research_all = results_to_dict(
        trades,
        config,
        include_trades=True,
        include_equity_curve=False,
    )["trades"]
    research_all = [trade for trade in research_all if trade["date"] <= end_date]
    research_filled = [trade for trade in research_all if trade.get("exit_type") != "no_fill"]
    return research_all, research_filled


def _slot_counts(rows: list[dict], research_only: list[dict]) -> dict[int, int]:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_day[row["date"]].append(row)
    for day_rows in by_day.values():
        day_rows.sort(key=lambda trade: _entry_minute(trade.get("entry_time")))

    counts: Counter[int] = Counter()
    for trade in research_only:
        day_rows = by_day[trade["date"]]
        slot = next(
            idx + 1
            for idx, candidate in enumerate(day_rows)
            if _strict_key(candidate) == _strict_key(trade)
        )
        counts[slot] += 1
    return dict(sorted(counts.items()))


def _fuzzy_match(
    research_filled: list[dict],
    exact: list[dict],
) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    exact_pool: dict[tuple, list[dict]] = defaultdict(list)
    for trade in exact:
        exact_pool[_same_trade_key(trade)].append(trade)

    matched: list[tuple[dict, dict]] = []
    research_only: list[dict] = []
    for trade in research_filled:
        bucket = exact_pool.get(_same_trade_key(trade), [])
        if bucket:
            matched.append((trade, bucket.pop(0)))
        else:
            research_only.append(trade)

    exact_only = [trade for bucket in exact_pool.values() for trade in bucket]
    return matched, research_only, exact_only


def _summarize_window(research_filled: list[dict], exact: list[dict], which: str) -> dict[str, Any]:
    research_rows = _slice_window(research_filled, which)
    exact_rows = _slice_window(exact, which)
    matched, research_only, exact_only = _fuzzy_match(research_rows, exact_rows)

    strict_research_keys = {_strict_key(row) for row in research_rows}
    strict_exact_keys = {_strict_key(row) for row in exact_rows}
    strict_intersection = len(strict_research_keys & strict_exact_keys)

    minute_shifts: Counter[int] = Counter()
    for research_trade, exact_trade in matched:
        r_hhmm = _hhmm(research_trade.get("entry_time"))
        e_hhmm = _hhmm(exact_trade.get("entry_time"))
        if not r_hhmm or not e_hhmm:
            continue
        r_hour, r_minute = map(int, r_hhmm.split(":"))
        e_hour, e_minute = map(int, e_hhmm.split(":"))
        minute_shifts[(e_hour * 60 + e_minute) - (r_hour * 60 + r_minute)] += 1

    return {
        "research_filled_trades": len(research_rows),
        "exact_trades": len(exact_rows),
        "strict_minute_match_count": strict_intersection,
        "matched_same_trade_count": len(matched),
        "research_only_count": len(research_only),
        "exact_only_count": len(exact_only),
        "research_only_day_count": len({trade["date"] for trade in research_only}),
        "exact_only_day_count": len({trade["date"] for trade in exact_only}),
        "minute_shift_distribution": dict(sorted(minute_shifts.items())),
        "research_only_slot_counts": _slot_counts(research_rows, research_only),
        "research_only_days": sorted({trade["date"] for trade in research_only}),
        "research_only_entry_times": Counter(_hhmm(trade.get("entry_time")) for trade in research_only).most_common(12),
        "research_only_fvg_to_inversion": Counter(
            trade.get("fvg_to_inversion_bars") for trade in research_only
        ).most_common(),
        "research_only_htf_level_times": Counter(
            (trade.get("htf_level_time") or "")[11:16] for trade in research_only
        ).most_common(12),
        "exact_only_fvg_to_inversion": Counter(
            trade.get("fvg_to_inversion_bars") for trade in exact_only
        ).most_common(),
        "research_only_samples": [
            {
                "date": trade.get("date"),
                "entry_time": trade.get("entry_time"),
                "exit_time": trade.get("exit_time"),
                "entry_price": trade.get("entry_price"),
                "htf_level_time": trade.get("htf_level_time"),
                "htf_level_price": trade.get("htf_level_price"),
                "fvg_to_inversion_bars": trade.get("fvg_to_inversion_bars"),
                "sweep_to_inversion_bars": trade.get("sweep_to_inversion_bars"),
                "exit_type": trade.get("exit_type"),
            }
            for trade in research_only[:10]
        ],
        "exact_only_samples": [
            {
                "date": trade.get("date"),
                "entry_time": trade.get("entry_time"),
                "exit_time": trade.get("exit_time"),
                "entry_price": trade.get("entry_price"),
                "htf_level_time": trade.get("htf_level_time"),
                "htf_level_price": trade.get("htf_level_price"),
                "fvg_to_inversion_bars": trade.get("fvg_to_inversion_bars"),
                "sweep_to_inversion_bars": trade.get("sweep_to_inversion_bars"),
                "exit_type": trade.get("exit_type"),
            }
            for trade in exact_only[:10]
        ],
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    info = payload["info"]
    pre = payload["windows"]["pre_holdout"]
    holdout = payload["windows"]["holdout"]
    parity_closed = (
        pre["research_only_count"] == 0
        and pre["exact_only_count"] == 0
        and holdout["research_only_count"] == 0
        and holdout["exact_only_count"] == 0
    )

    lines = [
        "# CL NY HTF-LSI Parity Diff",
        "",
        "- Objective: decompose the trade-count gap between the frozen `1m` CL HTF-LSI research branch and the execution-side exact replay prototype.",
        f"- Candidate: `{info['config_summary']}`",
        f"- Exact replay window: `{info['start_date']}` to `{info['end_date']}`",
        "",
        "## Key Findings",
        "",
        f"- Pre-holdout gap: research filled `{pre['research_filled_trades']}` trades vs exact `{pre['exact_trades']}`. Fuzzy same-trade matching recovered `{pre['matched_same_trade_count']}` overlaps, leaving `{pre['research_only_count']}` research-only trades and `{pre['exact_only_count']}` exact-only trades.",
        f"- Holdout gap: research filled `{holdout['research_filled_trades']}` trades vs exact `{holdout['exact_trades']}`. Fuzzy same-trade matching recovered `{holdout['matched_same_trade_count']}` overlaps, leaving `{holdout['research_only_count']}` research-only trades and `{holdout['exact_only_count']}` exact-only trades.",
        f"- Pre-holdout missing-trade slots: `{pre['research_only_slot_counts']}`",
        f"- Holdout missing-trade slots: `{holdout['research_only_slot_counts']}`",
        "",
        "## Window Summary",
        "",
        "| Window | Research Filled | Exact | Strict Minute Match | Fuzzy Same-Trade Match | Research Only | Exact Only |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| Pre-Holdout | {pre['research_filled_trades']} | {pre['exact_trades']} | {pre['strict_minute_match_count']} | {pre['matched_same_trade_count']} | {pre['research_only_count']} | {pre['exact_only_count']} |",
        f"| Holdout | {holdout['research_filled_trades']} | {holdout['exact_trades']} | {holdout['strict_minute_match_count']} | {holdout['matched_same_trade_count']} | {holdout['research_only_count']} | {holdout['exact_only_count']} |",
        "",
        "## Holdout Shape",
        "",
        f"- Minute-shift distribution on matched holdout trades: `{holdout['minute_shift_distribution']}`",
        f"- Missing holdout trade days: `{', '.join(holdout['research_only_days']) or '-'}`",
        f"- Missing holdout FVG-to-inversion bars: `{holdout['research_only_fvg_to_inversion']}`",
        f"- Missing holdout HTF level times: `{holdout['research_only_htf_level_times']}`",
        f"- Missing holdout entry times: `{holdout['research_only_entry_times']}`",
        "",
        "## Pre-Holdout Shape",
        "",
        f"- Minute-shift distribution on matched pre-holdout trades: `{pre['minute_shift_distribution']}`",
        f"- Pre-holdout research-only day count: `{pre['research_only_day_count']}`",
        f"- Pre-holdout missing trade slots: `{pre['research_only_slot_counts']}`",
        f"- Pre-holdout missing FVG-to-inversion bars: `{pre['research_only_fvg_to_inversion']}`",
        f"- Pre-holdout missing HTF level times: `{pre['research_only_htf_level_times']}`",
        "",
        "## Interpretation",
        "",
        "",
    ]

    if parity_closed:
        lines.extend(
            [
                "- Trade-level parity is closed. Exact replay now matches research on every filled trade across pre-holdout and holdout.",
                "- The honest next step is no longer trade-gap debugging. It is downstream operational work: keep the frozen CL candidate as the execution-aligned restart point and validate live-feed behavior separately from this historical exact replay path.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- This diff is the next checkpoint, not the final deployment verdict. The branch stayed positive on the exact replay, so the question is now where the missing trades come from.",
                "- If the remaining misses cluster in slot-1 trades and specific HTF-level publish times, the next debug target is the execution engine's day-reset and level publication lifecycle rather than funded modeling or parameter retuning.",
                "",
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    end_date = _target_end_date()
    research_all, research_filled = _load_research_trades(end_date)
    exact_result = asyncio.run(_run_exact_replay(_load_candidate(), end_date))
    exact_trades = exact_result["trades"]

    payload = {
        "info": {
            "start_date": FULL_START,
            "end_date": end_date,
            "config_summary": _load_candidate()["config_summary"],
            "research_all_trades": len(research_all),
            "research_filled_trades": len(research_filled),
            "research_no_fill_trades": len(research_all) - len(research_filled),
            "exact_trades": len(exact_trades),
        },
        "windows": {
            "pre_holdout": _summarize_window(research_filled, exact_trades, "pre_holdout"),
            "holdout": _summarize_window(research_filled, exact_trades, "holdout"),
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    _write_report(REPORT_PATH, payload)

    print(json.dumps(payload, indent=2, default=str))
    print(f"\nSaved JSON to {OUTPUT_JSON}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
