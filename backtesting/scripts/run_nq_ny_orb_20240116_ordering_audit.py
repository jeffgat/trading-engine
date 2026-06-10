#!/usr/bin/env python3
"""Audit the 2024-01-16 NQ NY ORB research/exact ordering mismatch.

This script is intentionally scoped to a single pre-holdout date. It does not
load or test 2025+ data.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_nq_ny_orb_exact_delta_audit import (  # noqa: E402
    DATA_FILE,
    END_DATE,
    HOLDOUT_START,
    ROOT,
    START_DATE,
    _date_ts,
    _load_exact_payload,
    _load_research_trades,
    _ts,
)
from orb_backtest.data.loader import load_1m_for_5m  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL  # noqa: E402
from trader.feed import ET  # noqa: E402
from trader.historical_backtest import _read_parquet_frame  # noqa: E402

RUN_ID = "nq_ny_orb_20240116_ordering_audit_20260609"
TARGET_DATE = "2024-01-16"
ARTIFACT_DIR = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / RUN_ID
    / "artifacts"
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return str(value)


def _to_et_index(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    idx = pd.DatetimeIndex(out.index)
    if idx.tz is None:
        idx = idx.tz_localize(ET)
    else:
        idx = idx.tz_convert(ET)
    out.index = idx
    return out.sort_index()


def _first_time(frame: pd.DataFrame, mask: pd.Series) -> pd.Timestamp | None:
    hits = frame[mask]
    if hits.empty:
        return None
    return pd.Timestamp(hits.index[0])


def _trade_for_date(trades: list[dict[str, Any]], date: str) -> dict[str, Any]:
    for trade in trades:
        if trade.get("date") == date and int(trade.get("exit_type", -999)) != EXIT_NO_FILL:
            return trade
    raise RuntimeError(f"No filled research trade found for {date}")


def _exact_trade_for_date(payload: dict[str, Any], date: str) -> dict[str, Any]:
    for trade in payload["result"]["trades"]:
        if trade.get("date") == date:
            return trade
    raise RuntimeError(f"No exact trade found for {date}")


def _price_row(row: pd.Series) -> dict[str, float]:
    return {
        "open": round(float(row["open"]), 4),
        "high": round(float(row["high"]), 4),
        "low": round(float(row["low"]), 4),
        "close": round(float(row["close"]), 4),
    }


def _flagged_tape(
    frame: pd.DataFrame,
    entry: float,
    stop: float,
    target: float,
    fill_time: pd.Timestamp | None,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.DataFrame:
    tape = frame[(frame.index >= window_start) & (frame.index <= window_end)].copy()
    tape["touches_entry"] = tape["low"] <= entry
    tape["touches_stop"] = tape["low"] <= stop
    tape["touches_target"] = tape["high"] >= target
    if fill_time is None:
        tape["phase"] = "unknown"
    else:
        tape["phase"] = "pre_fill"
        tape.loc[tape.index == fill_time, "phase"] = "fill_second"
        tape.loc[tape.index > fill_time, "phase"] = "post_fill"
    tape.index.name = "timestamp"
    return tape


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    research = payload["research_trade"]
    exact = payload["exact_trade"]
    one_min = payload["one_minute_bar"]
    seq = payload["one_second_sequence"]
    decision = payload["decision"]

    target_after_fill = seq.get("first_target_touch_after_fill")
    if target_after_fill is None:
        target_after_fill = "none before exact stop"

    lines = [
        "# NQ NY ORB 2024-01-16 Ordering Audit",
        "",
        f"- Window context: `{START_DATE}` to `{END_DATE}` only.",
        f"- Holdout: `{HOLDOUT_START}` onward was not loaded or tested.",
        "- Purpose: explain the single largest shared-date delta from the exact/research audit.",
        "",
        "## Trade Comparison",
        "",
        "| Path | Entry | Stop | Target | Fill/entry time | Exit time | Exit | R |",
        "|---|---:|---:|---:|---|---|---|---:|",
        (
            f"| Research 1m magnifier | {research['entry_price']:.2f} | "
            f"{research['stop_price']:.4f} | {research['tp2_price']:.4f} | "
            f"{research['fill_time']} | {research['exit_time']} | "
            f"{research['exit_type_name']} | {research['r_multiple']:.3f} |"
        ),
        (
            f"| Exact 1s replay | {exact['entry_price']:.2f} | "
            f"{exact['stop_price']:.4f} | {exact['tp2_price']:.4f} | "
            f"{exact['entry_time']} | {exact['exit_time']} | "
            f"{exact['exit_type']} | {exact['r_multiple']:.3f} |"
        ),
        "",
        "## 11:00 1m Bar",
        "",
        (
            f"- OHLC: open `{one_min['open']}`, high `{one_min['high']}`, "
            f"low `{one_min['low']}`, close `{one_min['close']}`."
        ),
        f"- Touches entry: `{one_min['touches_entry']}`.",
        f"- Touches target: `{one_min['touches_target']}`.",
        f"- Touches stop: `{one_min['touches_stop']}`.",
        f"- Ambiguous at 1m: `{one_min['ambiguous_for_research_exit']}`.",
        "",
        "## 1s Ordering",
        "",
        f"- Eligible from: `{seq['eligible_start']}`.",
        f"- First target touch after eligibility: `{seq['first_target_touch_after_eligible']}`.",
        f"- First entry fill after eligibility: `{seq['first_entry_touch_after_eligible']}`.",
        f"- First stop touch after fill: `{seq['first_stop_touch_after_fill']}`.",
        f"- First target touch after fill: `{target_after_fill}`.",
        f"- Target came before fill: `{seq['target_before_fill']}`.",
        f"- Exact 1s path outcome: `{seq['one_second_outcome']}`.",
        "",
        "## Decision",
        "",
        f"- `{decision['label']}`",
        f"- {decision['reason']}",
        f"- Next action: {decision['next_action']}",
        "",
        "## Files",
        "",
        f"- 1s flagged tape: `{payload['tape_csv']}`",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    research_trades, _df_5m = _load_research_trades()
    exact_payload = _load_exact_payload()

    research = dict(_trade_for_date(research_trades, TARGET_DATE))
    research["exit_type_name"] = EXIT_NAMES.get(
        int(research["exit_type"]), str(research["exit_type"])
    )
    exact = dict(_exact_trade_for_date(exact_payload, TARGET_DATE))

    entry = float(research["entry_price"])
    stop = float(research["stop_price"])
    target = float(research["tp2_price"])

    signal_time = _ts(research["signal_time"])
    eligible_start = signal_time + pd.Timedelta(minutes=5)
    one_minute_start = _date_ts(TARGET_DATE, "11:00")
    one_minute_end = one_minute_start + pd.Timedelta(minutes=1)
    tape_start = one_minute_start - pd.Timedelta(seconds=15)
    tape_end = one_minute_start + pd.Timedelta(minutes=1, seconds=20)

    target_next_date = (
        pd.Timestamp(TARGET_DATE) + pd.Timedelta(days=1)
    ).date().isoformat()
    df_1m = _to_et_index(
        load_1m_for_5m(str(DATA_FILE), start=TARGET_DATE, end=target_next_date)
    )
    minute_rows = df_1m[
        (df_1m.index >= one_minute_start) & (df_1m.index < one_minute_end)
    ]
    if minute_rows.empty:
        raise RuntimeError(f"Missing 1m row for {TARGET_DATE} 11:00 ET")
    minute = minute_rows.iloc[0]

    df_1s = _to_et_index(
        _read_parquet_frame(
            "NQ",
            "1s",
            start=tape_start.to_pydatetime(),
            end=tape_end.to_pydatetime(),
        )
    )
    if df_1s.empty:
        raise RuntimeError(f"Missing 1s data for {TARGET_DATE} around 11:00 ET")

    eligible = df_1s[df_1s.index >= eligible_start]
    first_target_after_eligible = _first_time(eligible, eligible["high"] >= target)
    first_entry_after_eligible = _first_time(eligible, eligible["low"] <= entry)

    if first_entry_after_eligible is None:
        post_fill = eligible.iloc[0:0]
    else:
        post_fill = df_1s[df_1s.index > first_entry_after_eligible]
    first_stop_after_fill = _first_time(post_fill, post_fill["low"] <= stop)
    first_target_after_fill = _first_time(post_fill, post_fill["high"] >= target)

    if first_entry_after_eligible is None:
        one_second_outcome = "no_fill"
    elif first_stop_after_fill is not None and (
        first_target_after_fill is None or first_stop_after_fill <= first_target_after_fill
    ):
        one_second_outcome = "sl"
    elif first_target_after_fill is not None:
        one_second_outcome = "tp2_direct"
    else:
        one_second_outcome = "open_after_window"

    target_before_fill = (
        first_target_after_eligible is not None
        and first_entry_after_eligible is not None
        and first_target_after_eligible < first_entry_after_eligible
    )

    tape = _flagged_tape(
        df_1s,
        entry=entry,
        stop=stop,
        target=target,
        fill_time=first_entry_after_eligible,
        window_start=tape_start,
        window_end=tape_end,
    )
    tape_csv = ARTIFACT_DIR / "one_second_tape_20240116_105945_110120.csv"
    tape.to_csv(tape_csv)

    one_minute_bar = {
        **_price_row(minute),
        "timestamp": one_minute_start.isoformat(),
        "touches_entry": bool(float(minute["low"]) <= entry),
        "touches_target": bool(float(minute["high"]) >= target),
        "touches_stop": bool(float(minute["low"]) <= stop),
        "ambiguous_for_research_exit": bool(
            float(minute["low"]) <= entry and float(minute["high"]) >= target
        ),
    }

    sequence = {
        "eligible_start": eligible_start.isoformat(),
        "first_target_touch_after_eligible": first_target_after_eligible,
        "first_entry_touch_after_eligible": first_entry_after_eligible,
        "first_stop_touch_after_fill": first_stop_after_fill,
        "first_target_touch_after_fill": first_target_after_fill,
        "target_before_fill": bool(target_before_fill),
        "one_second_outcome": one_second_outcome,
        "matches_exact_entry_time": (
            first_entry_after_eligible is not None
            and first_entry_after_eligible == _ts(exact["entry_time"])
        ),
        "matches_exact_exit_time": (
            first_stop_after_fill is not None
            and first_stop_after_fill == _ts(exact["exit_time"])
        ),
    }

    decision = {
        "label": "accept_exact_replay_as_operational_baseline",
        "reason": (
            "The research 1m magnifier counted a target touch on the same "
            "11:00 minute that contained the limit fill, but the 1s tape shows "
            "the first target touch after eligibility occurred at 10:59:45 ET "
            "and the 11:00 target burst ended before the entry filled at "
            "11:00:57 ET. The exact engine's post-fill 1s path matches the "
            "executable sequence and stops out at 11:01:07 ET."
        ),
        "next_action": (
            "Do not patch execution. Treat the corrected exact replay as the "
            "pre-holdout operational baseline; keep 2025 sealed until the "
            "promotion decision explicitly opens holdout."
        ),
    }

    payload = {
        "run_id": RUN_ID,
        "target_date": TARGET_DATE,
        "window": {"start": START_DATE, "end": END_DATE},
        "holdout_status": f"{HOLDOUT_START} onward not loaded or tested",
        "research_trade": research,
        "exact_trade": exact,
        "one_minute_bar": one_minute_bar,
        "one_second_sequence": sequence,
        "decision": decision,
        "tape_csv": str(tape_csv),
    }

    json_path = ARTIFACT_DIR / "ordering_audit_results.json"
    md_path = ARTIFACT_DIR / "ordering_audit_results.md"
    json_path.write_text(json.dumps(payload, indent=2, default=_json_safe) + "\n")
    _write_markdown(json.loads(json.dumps(payload, default=_json_safe)), md_path)

    print(
        json.dumps(
            {
                "success": True,
                "json": str(json_path),
                "markdown": str(md_path),
                "tape_csv": str(tape_csv),
                "decision": decision["label"],
                "one_second_sequence": json.loads(
                    json.dumps(sequence, default=_json_safe)
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
