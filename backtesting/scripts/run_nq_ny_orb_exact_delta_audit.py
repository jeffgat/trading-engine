#!/usr/bin/env python3
"""Audit research-native vs exact-execution NQ NY ORB rolling-gate deltas.

Window is intentionally limited to 2021-2024. The 2025 holdout is not loaded.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BACKTEST_SRC = ROOT / "backtesting" / "src"
EXEC_SRC = ROOT / "execution" / "src"
for path in (BACKTEST_SRC, EXEC_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from orb_backtest.config import default_config, with_overrides  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NAMES,
    EXIT_NO_FILL,
    TradeResult,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.signals.daily_atr import compute_previous_daily_rolling_atr_pct  # noqa: E402
from trader.feed import ET  # noqa: E402
from trader.historical_backtest import _read_parquet_frame  # noqa: E402

RUN_ID = "nq_ny_orb_exact_delta_audit_2021_20260609"
START_DATE = "2021-01-01"
END_DATE = "2024-12-31"
HOLDOUT_START = "2025-01-01"
MAX_PRIOR_ROLLING_ATR_PCT = 1.6228084238855573
MAX_ORB_RANGE_PCT = 0.4657663656763981

DATA_FILE = ROOT / "backtesting" / "data" / "cache" / "nq_ny_lsi_cisd_sequence" / "NQ_5m.parquet"
EXACT_ARTIFACT = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / "nq_ny_orb_exec_native_rolling_gate_2021_20260609"
    / "artifacts"
    / "exact_replay_results.json"
)
ARTIFACT_DIR = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / RUN_ID
    / "artifacts"
)


@dataclass(frozen=True)
class OneSecondPath:
    has_1s_data: bool
    fill_found: bool
    fill_time: str | None
    exit_type: str | None
    exit_time: str | None
    r_multiple: float | None


def _config():
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        risk_usd=5000.0,
        rr=2.0,
        tp1_ratio=1.0,
        exit_mode="single_target",
        continuation_fvg_selection="first",
        orb_trade_max_per_session=1,
        impulse_close_filter=False,
        use_bar_magnifier=True,
        strategy="continuation",
        direction_filter="long",
        ny_orb_start="09:30",
        ny_orb_end="09:45",
        ny_entry_start="09:45",
        ny_entry_end="13:00",
        ny_flat_start="15:50",
        ny_flat_end="16:00",
        ny_stop_atr_pct=10.0,
        ny_min_gap_atr_pct=2.0,
        ny_max_prior_rolling_atr_pct=MAX_PRIOR_ROLLING_ATR_PCT,
        ny_max_orb_range_pct=MAX_ORB_RANGE_PCT,
        name=RUN_ID,
    )


def _ts(value: str | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize(ET)
    return ts.tz_convert(ET)


def _date_ts(date_str: str, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{date_str} {hhmm}", tz=ET)


def _trade_dict(trade: TradeResult, timestamps: pd.DatetimeIndex) -> dict[str, Any]:
    row = trade._asdict()
    row["exit_type_name"] = EXIT_NAMES.get(trade.exit_type, str(trade.exit_type))
    row["signal_time"] = timestamps[trade.signal_bar].isoformat() if trade.signal_bar >= 0 else ""
    return row


def _load_research_trades() -> tuple[list[dict[str, Any]], pd.DataFrame]:
    print("loading 5m research data...", flush=True)
    df = load_5m_data(str(DATA_FILE), start="2016-01-01", end=END_DATE)
    try:
        print("loading 1m research magnifier data...", flush=True)
        df_1m = load_1m_for_5m(str(DATA_FILE), start="2016-01-01", end=END_DATE)
    except FileNotFoundError:
        df_1m = None

    config = _config()
    print("building research signal cache...", flush=True)
    cache = build_signal_cache(df, [config], signal_df_1m=df_1m)
    print("running research-native backtest...", flush=True)
    trades = run_backtest(
        df,
        config,
        start_date=START_DATE,
        end_date=END_DATE,
        df_1m=df_1m,
        signal_df_1m=df_1m,
        _signal_cache=cache,
    )
    print(f"research-native backtest complete: {len(trades)} total candidate rows", flush=True)
    return [_trade_dict(trade, df.index) for trade in trades], df


def _load_exact_payload() -> dict[str, Any]:
    if not EXACT_ARTIFACT.exists():
        raise FileNotFoundError(f"Exact replay artifact not found: {EXACT_ARTIFACT}")
    return json.loads(EXACT_ARTIFACT.read_text())


def _normal_exit(value: str) -> str:
    if value == "tp2_single":
        return "tp2_direct"
    return value


def _day_1s(date_str: str, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cached = cache.get(date_str)
    if cached is not None:
        return cached
    start = _date_ts(date_str, "00:00")
    end = start + pd.Timedelta(days=1)
    frame = _read_parquet_frame("NQ", "1s", start=start.to_pydatetime(), end=end.to_pydatetime())
    cache[date_str] = frame
    return frame


def _simulate_1s_research_setup(trade: dict[str, Any], cache: dict[str, pd.DataFrame]) -> OneSecondPath:
    date_str = trade["date"]
    frame = _day_1s(date_str, cache)
    if frame.empty:
        return OneSecondPath(False, False, None, None, None, None)

    signal_time = _ts(trade["signal_time"])
    eligible_start = signal_time + pd.Timedelta(minutes=5)
    entry_end = _date_ts(date_str, "13:00")
    flat_start = _date_ts(date_str, "15:50")
    entry = float(trade["entry_price"])
    stop = float(trade["stop_price"])
    target = float(trade["tp2_price"])
    risk_points = float(trade["risk_points"])

    scan = frame[(frame.index >= eligible_start) & (frame.index <= entry_end)]
    fills = scan[scan["low"] <= entry]
    if fills.empty:
        return OneSecondPath(True, False, None, None, None, None)

    fill_time = fills.index[0]
    post_fill = frame[(frame.index > fill_time) & (frame.index <= flat_start)]
    for ts, row in post_fill.iterrows():
        sl_hit = float(row["low"]) <= stop
        target_hit = float(row["high"]) >= target
        if sl_hit and target_hit:
            return OneSecondPath(True, True, fill_time.isoformat(), "sl", ts.isoformat(), -1.0)
        if sl_hit:
            return OneSecondPath(True, True, fill_time.isoformat(), "sl", ts.isoformat(), -1.0)
        if target_hit:
            return OneSecondPath(True, True, fill_time.isoformat(), "tp2_direct", ts.isoformat(), 2.0)

    if post_fill.empty:
        exit_time = fill_time
        close = entry
    else:
        exit_time = post_fill.index[-1]
        close = float(post_fill.iloc[-1]["close"])
    r = (close - entry) / risk_points if risk_points > 0 else 0.0
    return OneSecondPath(True, True, fill_time.isoformat(), "eod", exit_time.isoformat(), round(float(r), 6))


def _context_by_date(df: pd.DataFrame, needed_dates: set[str]) -> dict[str, dict[str, Any]]:
    prior_atr_pct = compute_previous_daily_rolling_atr_pct(df, length=14)
    context: dict[str, dict[str, Any]] = {}
    needed = {pd.Timestamp(date_str).date() for date_str in needed_dates}
    for day_date in sorted(needed):
        date_str = day_date.isoformat()
        day = df[df.index.date == day_date]
        if day.empty:
            continue
        orb = day.between_time("09:30", "09:44")
        if orb.empty:
            continue
        day_positions = np.flatnonzero(df.index.date == day_date)
        first_pos = int(day_positions[0]) if len(day_positions) else -1
        rolling = float(prior_atr_pct[first_pos]) if first_pos >= 0 else float("nan")
        orb_open = float(orb.iloc[0]["open"])
        orb_range = float(orb["high"].max() - orb["low"].min())
        orb_range_pct = orb_range / orb_open * 100.0 if orb_open > 0 else float("nan")
        context[date_str] = {
            "prior_rolling_atr_pct": rolling,
            "orb_open": orb_open,
            "orb_range": orb_range,
            "orb_range_pct": orb_range_pct,
            "context_gate_pass": (
                np.isfinite(rolling)
                and rolling <= MAX_PRIOR_ROLLING_ATR_PCT
                and np.isfinite(orb_range_pct)
                and orb_range_pct <= MAX_ORB_RANGE_PCT
            ),
        }
    return context


def _summarize_shared(shared_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not shared_rows:
        return {}
    exact_minus_research_r = np.asarray([row["r_delta"] for row in shared_rows], dtype=float)
    entry_delta = np.asarray([row["entry_delta_points"] for row in shared_rows], dtype=float)
    stop_delta = np.asarray([row["stop_delta_points"] for row in shared_rows], dtype=float)
    return {
        "shared_dates": len(shared_rows),
        "exact_better_count": int(np.sum(exact_minus_research_r > 1e-9)),
        "exact_same_count": int(np.sum(np.isclose(exact_minus_research_r, 0.0))),
        "exact_worse_count": int(np.sum(exact_minus_research_r < -1e-9)),
        "shared_r_delta_sum": round(float(np.sum(exact_minus_research_r)), 6),
        "avg_r_delta": round(float(np.mean(exact_minus_research_r)), 6),
        "median_r_delta": round(float(np.median(exact_minus_research_r)), 6),
        "max_abs_entry_delta_points": round(float(np.max(np.abs(entry_delta))), 6),
        "max_abs_stop_delta_points": round(float(np.max(np.abs(stop_delta))), 6),
        "exit_transition_counts": dict(Counter(row["exit_transition"] for row in shared_rows)),
    }


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    summary = payload["summary"]
    shared = payload["shared_summary"]
    reason_counts = summary["research_only_reason_counts"]
    lines = [
        "# NQ NY ORB Exact Delta Audit",
        "",
        f"- Window: `{START_DATE}` to `{END_DATE}`",
        f"- Holdout: `{HOLDOUT_START}` onward was not loaded or tested.",
        "- Candidate: `NQ_NY_ORB_NEUTRAL_ROLLING_GATE` vs research-native rolling ATR/ORB gate.",
        "",
        "## Set Diff",
        "",
        f"- Research filled dates: `{summary['research_filled_dates']}`",
        f"- Exact filled dates: `{summary['exact_filled_dates']}`",
        f"- Shared dates: `{summary['shared_dates']}`",
        f"- Research-only dates: `{summary['research_only_dates']}`",
        f"- Exact-only dates: `{summary['exact_only_dates']}`",
        "",
        "## First-Pass Research-Only Classification",
        "",
    ]
    if reason_counts:
        for reason, count in reason_counts.items():
            lines.append(f"- `{reason}`: {count}")
    else:
        lines.append("- None; all research-filled dates are present in exact replay.")
    lines.extend(
        [
            "",
            "## Shared-Date Delta",
            "",
            f"- Shared R delta sum, exact minus research: `{shared.get('shared_r_delta_sum')}`",
            f"- Exact better/same/worse shared dates: `{shared.get('exact_better_count')}` / `{shared.get('exact_same_count')}` / `{shared.get('exact_worse_count')}`",
            f"- Median R delta: `{shared.get('median_r_delta')}`",
            f"- Max abs entry delta: `{shared.get('max_abs_entry_delta_points')}` points",
            f"- Max abs stop delta: `{shared.get('max_abs_stop_delta_points')}` points",
            "",
            "## Worst Shared-Date R Deltas",
            "",
            "| Date | Research exit/R | Exact exit/R | Delta | Entry delta | Stop delta |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["shared_rows_sorted_by_delta"][:12]:
        lines.append(
            f"| {row['date']} | {row['research_exit_type']}/{row['research_r']:.3f} | "
            f"{row['exact_exit_type']}/{row['exact_r']:.3f} | {row['r_delta']:.3f} | "
            f"{row['entry_delta_points']:.2f} | {row['stop_delta_points']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Research-Only Dates",
            "",
            "| Date | Research exit/R | Signal | Research fill | 1s check | Reason |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for row in payload["research_only_rows"]:
        one_second_path = row["one_second_path"]
        one_s = "no 1s data"
        if one_second_path["has_1s_data"] and not one_second_path["fill_found"]:
            one_s = "no 1s fill"
        elif one_second_path["fill_found"]:
            one_s = f"{one_second_path['exit_type']} {one_second_path['r_multiple']}"
        lines.append(
            f"| {row['date']} | {row['research_exit_type']}/{row['research_r']:.3f} | "
            f"{row['signal_time']} | {row['research_fill_time']} | {one_s} | {row['reason']} |"
        )
    lines.extend(
        [
            "",
            "## Exact-Only Dates",
            "",
            "| Date | Exact exit/R | Research candidate on date | Note |",
            "|---|---:|---|---|",
        ]
    )
    for row in payload["exact_only_rows"]:
        lines.append(
            f"| {row['date']} | {row['exact_exit_type']}/{row['exact_r']:.3f} | "
            f"{row['research_candidate_exit_type'] or ''}/{row['research_candidate_r'] if row['research_candidate_r'] is not None else ''} | "
            f"{row['note']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The prior 30-date research-only gap was an inherited Friday exclusion in the execution profile; setting `excluded_dow=null` fixed it.",
            "- Remaining exact/research divergence is shared-date 1s exit sequencing plus one exact-only loser, not ATR/ORB gate drift.",
            "- Treat corrected exact replay as the operational baseline unless the 2024-01-16 same-bar target/stop ordering is judged to be a research simulator parity bug.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    research_trades, df = _load_research_trades()
    print("loading exact replay artifact...", flush=True)
    exact_payload = _load_exact_payload()
    exact_trades = list(exact_payload["result"]["trades"])

    research_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    research_filled_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in research_trades:
        research_by_date[trade["date"]].append(trade)
        if int(trade["exit_type"]) != EXIT_NO_FILL:
            research_filled_by_date[trade["date"]].append(trade)

    exact_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in exact_trades:
        exact_by_date[trade["date"]].append(trade)

    research_dates = set(research_filled_by_date)
    exact_dates = set(exact_by_date)
    shared_dates = sorted(research_dates & exact_dates)
    research_only_dates = sorted(research_dates - exact_dates)
    exact_only_dates = sorted(exact_dates - research_dates)

    print(
        "date sets: "
        f"research={len(research_dates)} exact={len(exact_dates)} "
        f"shared={len(shared_dates)} research_only={len(research_only_dates)} "
        f"exact_only={len(exact_only_dates)}",
        flush=True,
    )
    print("computing context for diff dates...", flush=True)
    context = _context_by_date(df, set(research_only_dates) | set(exact_only_dates))

    one_s_cache: dict[str, pd.DataFrame] = {}
    research_only_rows = []
    print("auditing research-only dates with 1s data...", flush=True)
    for date_str in research_only_dates:
        trade = research_filled_by_date[date_str][0]
        path = _simulate_1s_research_setup(trade, one_s_cache)
        ctx = context.get(date_str, {})
        if not ctx.get("context_gate_pass", False):
            reason = "context_gate_mismatch"
        elif not path.has_1s_data:
            reason = "missing_1s_data"
        elif not path.fill_found:
            reason = "research_1m_fill_not_confirmed_by_1s"
        else:
            reason = "1s_path_would_fill__exact_signal_or_state_mismatch"
        research_only_rows.append({
            "date": date_str,
            "research_exit_type": EXIT_NAMES.get(int(trade["exit_type"]), str(trade["exit_type"])),
            "research_r": round(float(trade["r_multiple"]), 6),
            "research_net_r": round(float(trade["net_r_multiple"]), 6),
            "signal_time": trade["signal_time"],
            "research_fill_time": trade["fill_time"],
            "research_exit_time": trade["exit_time"],
            "entry_price": float(trade["entry_price"]),
            "stop_price": float(trade["stop_price"]),
            "tp2_price": float(trade["tp2_price"]),
            "context": ctx,
            "one_second_path": asdict(path),
            "reason": reason,
        })

    shared_rows = []
    for date_str in shared_dates:
        research = research_filled_by_date[date_str][0]
        exact = exact_by_date[date_str][0]
        research_exit = _normal_exit(EXIT_NAMES.get(int(research["exit_type"]), str(research["exit_type"])))
        exact_exit = _normal_exit(str(exact["exit_type"]))
        shared_rows.append({
            "date": date_str,
            "research_exit_type": research_exit,
            "exact_exit_type": exact_exit,
            "exit_transition": f"{research_exit}->{exact_exit}",
            "research_r": round(float(research["r_multiple"]), 6),
            "exact_r": round(float(exact["r_multiple"]), 6),
            "r_delta": round(float(exact["r_multiple"]) - float(research["r_multiple"]), 6),
            "research_entry": float(research["entry_price"]),
            "exact_entry": float(exact["entry_price"]),
            "entry_delta_points": round(float(exact["entry_price"]) - float(research["entry_price"]), 6),
            "research_stop": float(research["stop_price"]),
            "exact_stop": float(exact["stop_price"]),
            "stop_delta_points": round(float(exact["stop_price"]) - float(research["stop_price"]), 6),
            "research_fill_time": research["fill_time"],
            "exact_entry_time": exact.get("entry_time"),
            "research_exit_time": research["exit_time"],
            "exact_exit_time": exact.get("exit_time"),
        })

    exact_only_rows = []
    for date_str in exact_only_dates:
        exact = exact_by_date[date_str][0]
        research_candidates = research_by_date.get(date_str, [])
        first_candidate = research_candidates[0] if research_candidates else None
        note = "no research candidate"
        candidate_exit = None
        candidate_r = None
        if first_candidate is not None:
            candidate_exit = EXIT_NAMES.get(int(first_candidate["exit_type"]), str(first_candidate["exit_type"]))
            candidate_r = round(float(first_candidate["r_multiple"]), 6)
            note = "research candidate was not a filled research trade"
        exact_only_rows.append({
            "date": date_str,
            "exact_exit_type": str(exact["exit_type"]),
            "exact_r": round(float(exact["r_multiple"]), 6),
            "research_candidate_exit_type": candidate_exit,
            "research_candidate_r": candidate_r,
            "note": note,
        })

    reason_counts = dict(Counter(row["reason"] for row in research_only_rows))
    research_only_r = round(sum(row["research_r"] for row in research_only_rows), 6)
    exact_only_r = round(sum(row["exact_r"] for row in exact_only_rows), 6)
    shared_summary = _summarize_shared(shared_rows)
    summary = {
        "run_id": RUN_ID,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "holdout_status": f"{HOLDOUT_START} onward not loaded or tested",
        "research_filled_dates": len(research_dates),
        "exact_filled_dates": len(exact_dates),
        "shared_dates": len(shared_dates),
        "research_only_dates": len(research_only_dates),
        "exact_only_dates": len(exact_only_dates),
        "research_only_r": research_only_r,
        "exact_only_r": exact_only_r,
        "research_only_reason_counts": reason_counts,
        "exact_total_r": exact_payload["result"]["summary"]["total_r"],
        "research_total_r": sum(float(t["r_multiple"]) for rows in research_filled_by_date.values() for t in rows),
    }

    payload = {
        "summary": summary,
        "shared_summary": shared_summary,
        "research_only_rows": research_only_rows,
        "exact_only_rows": exact_only_rows,
        "shared_rows": shared_rows,
        "shared_rows_sorted_by_delta": sorted(shared_rows, key=lambda row: row["r_delta"]),
    }

    json_path = ARTIFACT_DIR / "delta_audit_results.json"
    md_path = ARTIFACT_DIR / "delta_audit_results.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    _write_markdown(payload, md_path)
    print(json.dumps({
        "success": True,
        "json": str(json_path),
        "markdown": str(md_path),
        "summary": summary,
        "shared_summary": shared_summary,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
