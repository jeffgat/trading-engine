#!/usr/bin/env python3
"""Exit microstructure diff for the frozen CL NY HTF-LSI 1m lead."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

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
from run_cl_ny_htf_lsi_parity_diff import _load_research_trades, _strict_key  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "cl_ny_htf_lsi_exit_diff"
OUTPUT_JSON = OUTPUT_DIR / "summary.json"
REPORT_PATH = ROOT / "learnings" / "reports" / "CL_NY_HTF_LSI_EXIT_DIFF.md"


def _slice_window(rows: list[dict], which: str, end_date: str) -> list[dict]:
    if which == "pre_holdout":
        return [row for row in rows if FULL_START <= row["date"] <= PRE_HOLDOUT_END]
    if which == "holdout":
        return [row for row in rows if HOLDOUT_START <= row["date"] <= end_date]
    raise ValueError(f"Unknown window {which!r}")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def _seconds_delta(research_trade: dict, exact_trade: dict) -> int | None:
    r_ts = _parse_ts(research_trade.get("exit_time"))
    e_ts = _parse_ts(exact_trade.get("exit_time"))
    if r_ts is None or e_ts is None:
        return None
    return int(round((e_ts - r_ts).total_seconds()))


def _r_delta(research_trade: dict, exact_trade: dict) -> float:
    return round(float(exact_trade.get("r_multiple") or 0.0) - float(research_trade.get("r_multiple") or 0.0), 3)


def _match_trades(research_rows: list[dict], exact_rows: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    exact_by_key = {_strict_key(trade): trade for trade in exact_rows}
    research_by_key = {_strict_key(trade): trade for trade in research_rows}

    matched: list[tuple[dict, dict]] = []
    research_only: list[dict] = []

    for trade in research_rows:
        key = _strict_key(trade)
        exact_trade = exact_by_key.get(key)
        if exact_trade is None:
            research_only.append(trade)
        else:
            matched.append((trade, exact_trade))

    exact_only = [trade for key, trade in exact_by_key.items() if key not in research_by_key]
    matched.sort(key=lambda pair: (_strict_key(pair[0])[0], _strict_key(pair[0])[1]))
    return matched, research_only, exact_only


def _top_items(counter: Counter, limit: int = 12) -> list[list[Any]]:
    return [[key, value] for key, value in counter.most_common(limit)]


def _sample_row(research_trade: dict, exact_trade: dict) -> dict[str, Any]:
    return {
        "date": research_trade.get("date"),
        "entry_time": research_trade.get("entry_time"),
        "research_exit_time": research_trade.get("exit_time"),
        "exact_exit_time": exact_trade.get("exit_time"),
        "research_exit_type": research_trade.get("exit_type"),
        "exact_exit_type": exact_trade.get("exit_type"),
        "research_r": round(float(research_trade.get("r_multiple") or 0.0), 3),
        "exact_r": round(float(exact_trade.get("r_multiple") or 0.0), 3),
        "delta_r": _r_delta(research_trade, exact_trade),
        "exit_seconds_delta": _seconds_delta(research_trade, exact_trade),
        "entry_price": research_trade.get("entry_price"),
        "stop_price": research_trade.get("stop_price"),
        "tp1_price": research_trade.get("tp1_price"),
        "tp2_price": research_trade.get("tp2_price"),
    }


def _summarize_window(research_rows: list[dict], exact_rows: list[dict]) -> dict[str, Any]:
    matched, research_only, exact_only = _match_trades(research_rows, exact_rows)

    exit_transition_counts: Counter[tuple[str, str]] = Counter()
    exit_seconds_counter: Counter[int] = Counter()
    r_delta_counter: Counter[float] = Counter()
    date_to_delta_r: dict[str, float] = defaultdict(float)
    date_to_abs_delta_r: dict[str, float] = defaultdict(float)

    exit_type_diff_samples: list[dict[str, Any]] = []
    same_type_r_diff_samples: list[dict[str, Any]] = []
    negative_delta_samples: list[dict[str, Any]] = []

    exit_type_match_count = 0
    same_type_r_diff_count = 0
    exact_worse_count = 0
    exact_better_count = 0
    same_r_count = 0

    for research_trade, exact_trade in matched:
        transition = (
            str(research_trade.get("exit_type") or ""),
            str(exact_trade.get("exit_type") or ""),
        )
        exit_transition_counts[transition] += 1

        delta_r = _r_delta(research_trade, exact_trade)
        r_delta_counter[delta_r] += 1
        date_to_delta_r[str(research_trade.get("date"))] += delta_r
        date_to_abs_delta_r[str(research_trade.get("date"))] += abs(delta_r)

        exit_seconds = _seconds_delta(research_trade, exact_trade)
        if exit_seconds is not None:
            exit_seconds_counter[exit_seconds] += 1

        if transition[0] == transition[1]:
            exit_type_match_count += 1
            if delta_r != 0:
                same_type_r_diff_count += 1

        if delta_r < 0:
            exact_worse_count += 1
            negative_delta_samples.append(_sample_row(research_trade, exact_trade))
        elif delta_r > 0:
            exact_better_count += 1
        else:
            same_r_count += 1

        if transition[0] != transition[1]:
            exit_type_diff_samples.append(_sample_row(research_trade, exact_trade))
        elif delta_r != 0:
            same_type_r_diff_samples.append(_sample_row(research_trade, exact_trade))

    net_delta_r = round(sum(date_to_delta_r.values()), 3)
    negative_delta_r = round(sum(delta for delta in date_to_delta_r.values() if delta < 0), 3)
    positive_delta_r = round(sum(delta for delta in date_to_delta_r.values() if delta > 0), 3)

    exit_type_diff_samples.sort(key=lambda row: (abs(float(row["delta_r"])), row["date"]), reverse=True)
    same_type_r_diff_samples.sort(key=lambda row: (abs(float(row["delta_r"])), row["date"]), reverse=True)
    negative_delta_samples.sort(key=lambda row: (float(row["delta_r"]), row["date"]))

    return {
        "matched_trade_count": len(matched),
        "research_only_count": len(research_only),
        "exact_only_count": len(exact_only),
        "exit_type_match_count": exit_type_match_count,
        "exit_type_diff_count": len(matched) - exit_type_match_count,
        "same_type_r_diff_count": same_type_r_diff_count,
        "exact_worse_count": exact_worse_count,
        "exact_better_count": exact_better_count,
        "same_r_count": same_r_count,
        "net_delta_r": net_delta_r,
        "negative_date_delta_r": negative_delta_r,
        "positive_date_delta_r": positive_delta_r,
        "top_exit_transitions": [
            [f"{research_exit}->{exact_exit}", count]
            for (research_exit, exact_exit), count in exit_transition_counts.most_common(16)
        ],
        "top_nonflat_r_deltas": [
            [delta, count]
            for delta, count in sorted(
                ((delta, count) for delta, count in r_delta_counter.items() if delta != 0.0),
                key=lambda item: (abs(float(item[0])), item[1]),
                reverse=True,
            )[:16]
        ],
        "exit_seconds_distribution": _top_items(exit_seconds_counter, limit=16),
        "top_negative_dates": [
            [date, round(delta, 3)]
            for date, delta in sorted(date_to_delta_r.items(), key=lambda item: (item[1], item[0]))[:12]
        ],
        "top_abs_delta_dates": [
            [date, round(delta, 3)]
            for date, delta in sorted(date_to_abs_delta_r.items(), key=lambda item: (-item[1], item[0]))[:12]
        ],
        "exit_type_diff_samples": exit_type_diff_samples[:20],
        "same_type_r_diff_samples": same_type_r_diff_samples[:20],
        "negative_delta_samples": negative_delta_samples[:20],
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    info = payload["info"]
    pre = payload["windows"]["pre_holdout"]
    holdout = payload["windows"]["holdout"]

    def _table_rows(window: dict[str, Any], label: str) -> list[str]:
        return [
            (
                f"| {label} | {window['matched_trade_count']} | {window['exit_type_diff_count']} | "
                f"{window['same_type_r_diff_count']} | {window['exact_worse_count']} | "
                f"{window['exact_better_count']} | {window['net_delta_r']:.3f} |"
            )
        ]

    def _bullet_rows(rows: list[list[Any]], default: str = "`none`") -> list[str]:
        if not rows:
            return [f"- {default}"]
        return [f"- `{label}`: `{value}`" for label, value in rows]

    lines = [
        "# CL NY HTF-LSI Exit Diff",
        "",
        "- Objective: explain why the exact replay is still slightly softer than research after full trade-count parity was closed.",
        f"- Candidate: `{info['config_summary']}`",
        f"- Window: `{info['start_date']}` to `{info['end_date']}`",
        "",
        "## Key Findings",
        "",
        f"- Pre-holdout matched `{pre['matched_trade_count']}` trades and still gave back `{pre['net_delta_r']:.3f}R` in exact replay.",
        f"- Holdout matched `{holdout['matched_trade_count']}` trades and still gave back `{holdout['net_delta_r']:.3f}R` in exact replay.",
        f"- Pre-holdout exit-type disagreements: `{pre['exit_type_diff_count']}` trades. Same-exit-type but different R: `{pre['same_type_r_diff_count']}` trades.",
        f"- Holdout exit-type disagreements: `{holdout['exit_type_diff_count']}` trades. Same-exit-type but different R: `{holdout['same_type_r_diff_count']}` trades.",
        "",
        "## Window Summary",
        "",
        "| Window | Matched Trades | Exit-Type Diff | Same-Type R Diff | Exact Worse | Exact Better | Net Delta R |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        *_table_rows(pre, "Pre-Holdout"),
        *_table_rows(holdout, "Holdout"),
        "",
        "## Pre-Holdout Transition Mix",
        "",
        *_bullet_rows(pre["top_exit_transitions"]),
        "",
        "## Holdout Transition Mix",
        "",
        *_bullet_rows(holdout["top_exit_transitions"]),
        "",
        "## Pre-Holdout Worst Dates",
        "",
        *_bullet_rows(pre["top_negative_dates"]),
        "",
        "## Holdout Worst Dates",
        "",
        *_bullet_rows(holdout["top_negative_dates"]),
        "",
        "## Holdout Exit-Type Diff Samples",
        "",
    ]

    if holdout["exit_type_diff_samples"]:
        for sample in holdout["exit_type_diff_samples"]:
            lines.append(
                "- "
                f"`{sample['date']} {sample['entry_time']}` "
                f"`{sample['research_exit_type']}->{sample['exact_exit_type']}` "
                f"deltaR `{sample['delta_r']:.3f}` "
                f"exitSec `{sample['exit_seconds_delta']}`"
            )
    else:
        lines.append("- `none`")

    lines.extend(
        [
            "",
            "## Holdout Same-Type R Diff Samples",
            "",
        ]
    )
    if holdout["same_type_r_diff_samples"]:
        for sample in holdout["same_type_r_diff_samples"]:
            lines.append(
                "- "
                f"`{sample['date']} {sample['entry_time']}` "
                f"`{sample['research_exit_type']}` "
                f"deltaR `{sample['delta_r']:.3f}` "
                f"exitSec `{sample['exit_seconds_delta']}`"
            )
    else:
        lines.append("- `none`")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    candidate = _load_candidate()
    end_date = _target_end_date()
    _all_research, research_filled = _load_research_trades(end_date)
    exact = asyncio.run(_run_exact_replay(candidate, end_date))["trades"]

    payload = {
        "info": {
            "config_summary": candidate["config_summary"],
            "start_date": FULL_START,
            "end_date": end_date,
        },
        "windows": {
            "pre_holdout": _summarize_window(
                _slice_window(research_filled, "pre_holdout", end_date),
                _slice_window(exact, "pre_holdout", end_date),
            ),
            "holdout": _summarize_window(
                _slice_window(research_filled, "holdout", end_date),
                _slice_window(exact, "holdout", end_date),
            ),
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
