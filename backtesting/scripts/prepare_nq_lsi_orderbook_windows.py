#!/usr/bin/env python3
"""Prepare sparse MBP-10 download windows around NQ NY LSI candidates."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import run_nq_ny_lsi_orderflow_impulse_proxy as impulse
from orb_backtest.engine.simulator import EXIT_NO_FILL


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = ROOT / "data" / "results" / "nq_ny_lsi_orderbook_windows"


@dataclass
class Window:
    symbol: str
    start: pd.Timestamp
    end: pd.Timestamp
    candidate: str
    timeframe: str
    trade_date: str
    contributors: set[str] = field(default_factory=set)
    trade_count: int = 1

    def to_row(self) -> dict:
        candidates = sorted(self.contributors or {self.candidate})
        return {
            "symbol": self.symbol,
            "start": self.start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": self.end.strftime("%Y-%m-%dT%H:%M:%S"),
            "candidates": "|".join(candidates),
            "timeframe": self.timeframe,
            "trade_date": self.trade_date,
            "trade_count": self.trade_count,
        }


def parse_ts(value: str) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.Timestamp(value).tz_localize(None)


def candidate_windows(
    *,
    start: str,
    end: str | None,
    pre_seconds: int,
    post_seconds: int,
    max_sweep_lookback_minutes: int,
) -> list[Window]:
    data = impulse.load_signal_data()
    candidates = impulse.build_candidate_runs()
    windows: list[Window] = []

    for candidate in candidates:
        t0 = time.time()
        trades = impulse.run_candidate(candidate, data)
        df = data[candidate.timeframe]
        delta = impulse.timeframe_delta(candidate.timeframe)
        filled = [
            trade for trade in trades
            if trade.exit_type != EXIT_NO_FILL
            and trade.date >= start
            and (end is None or trade.date < end)
            and 0 <= trade.signal_bar < len(df)
        ]
        for trade in filled:
            signal_start = pd.Timestamp(df.index[trade.signal_bar])
            signal_end = signal_start + delta
            anchor_start = signal_start
            sweep_time = parse_ts(trade.lsi_sweep_time)
            if sweep_time is not None:
                sweep_gap = signal_start - sweep_time
                if pd.Timedelta(0) <= sweep_gap <= pd.Timedelta(minutes=max_sweep_lookback_minutes):
                    anchor_start = min(anchor_start, sweep_time)
            window_start = anchor_start - pd.Timedelta(seconds=pre_seconds)
            window_end = signal_end + pd.Timedelta(seconds=post_seconds)
            windows.append(
                Window(
                    symbol="NQ",
                    start=window_start,
                    end=window_end,
                    candidate=candidate.key,
                    timeframe=candidate.timeframe,
                    trade_date=trade.date,
                    contributors={candidate.key},
                )
            )
        print(
            f"  windows {candidate.key:<58} {len(filled):>4} trades "
            f"[{time.time() - t0:.1f}s]",
            flush=True,
        )
    return windows


def merge_windows(windows: list[Window], *, merge_gap_seconds: int) -> list[Window]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda win: (win.symbol, win.start, win.end))
    merged: list[Window] = []
    current = ordered[0]
    for window in ordered[1:]:
        merge_gap = pd.Timedelta(seconds=merge_gap_seconds)
        if window.symbol == current.symbol and window.start <= current.end + merge_gap:
            current.end = max(current.end, window.end)
            current.contributors.update(window.contributors or {window.candidate})
            current.trade_count += window.trade_count
            if current.timeframe != window.timeframe:
                current.timeframe = "mixed"
            continue
        merged.append(current)
        current = window
    merged.append(current)
    return merged


def write_csv(path: Path, windows: list[Window]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        fieldnames = ["symbol", "start", "end", "candidates", "timeframe", "trade_date", "trade_count"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for window in windows:
            writer.writerow(window.to_row())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-04-01", help="Trade start date inclusive.")
    parser.add_argument("--end", default=None, help="Trade end date exclusive.")
    parser.add_argument("--pre-seconds", type=int, default=120)
    parser.add_argument("--post-seconds", type=int, default=60)
    parser.add_argument("--max-sweep-lookback-minutes", type=int, default=10)
    parser.add_argument("--merge-gap-seconds", type=int, default=30)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    print("Preparing NQ NY LSI order-book windows", flush=True)
    raw = candidate_windows(
        start=args.start,
        end=args.end,
        pre_seconds=args.pre_seconds,
        post_seconds=args.post_seconds,
        max_sweep_lookback_minutes=args.max_sweep_lookback_minutes,
    )
    merged = merge_windows(raw, merge_gap_seconds=args.merge_gap_seconds)

    raw_path = args.out_dir / "raw_windows.csv"
    merged_path = args.out_dir / "orderbook_windows.csv"
    write_csv(raw_path, raw)
    write_csv(merged_path, merged)

    raw_seconds = sum((window.end - window.start).total_seconds() for window in raw)
    merged_seconds = sum((window.end - window.start).total_seconds() for window in merged)
    print(f"Raw windows:    {len(raw):,} ({raw_seconds / 3600:.2f} hours)")
    print(f"Merged windows: {len(merged):,} ({merged_seconds / 3600:.2f} hours)")
    print(f"Wrote {raw_path}")
    print(f"Wrote {merged_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
