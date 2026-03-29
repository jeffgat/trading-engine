#!/usr/bin/env python3
"""Compare 30m HH/HL-2 + VWAP gate with different entry windows.

Three variants:
  A) Baseline: current 15m HH/HL-2 + VWAP gate (session-aligned from 09:30)
     Entry window: 09:45-13:00. Earliest gate=True at 10:00 (after 2nd 15m bar).
  B) Pre-session 30m: clock-aligned 30m bars starting at 08:30.
     At 09:50 we see 08:30-09:00 and 09:00-09:30 completed bars.
     Entry window: 09:45-13:00 (original).
  C) Session-aligned 30m: 30m bars from 09:00 (09:00-09:30, 09:30-10:00).
     At 10:00 we see both completed. Entry window effectively starts 10:00.

All use FAST_V2 NQ_NY config with excluded Friday.
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "execution" / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import (
    EXIT_NO_FILL,
    TradeResult,
    build_maps,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.signals.daily_atr import compute_daily_atr
from orb_backtest.signals.orb import compute_orb_levels
from orb_backtest.signals.session import compute_session_days, compute_session_masks
from orb_backtest.signals.structure_15m import (
    compute_all_15m_signals,
    compute_hh_hl_patterns,
    resample_session_15m,
)
from orb_backtest.signals.vwap import compute_session_vwap

from run_fast_v2_nq_context_filters import build_profile_legs

FULL_START = "2021-01-01"
RECENT_START = "2024-01-01"
HOLDOUT_START = "2025-01-01"


# ---------------------------------------------------------------------------
# 30m resampling — clock-aligned, not session-aligned
# ---------------------------------------------------------------------------

def resample_clock_30m(
    df: pd.DataFrame,
    align_start: str,
    session_day_id: np.ndarray,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Resample 5m bars to clock-aligned 30m bars.

    30m boundaries are aligned to ``align_start`` (e.g. "08:30" or "09:00").
    Groups every 6 consecutive 5m bars within each session day that fall
    on or after ``align_start``.

    Returns:
        df_30m: 30m OHLCV DataFrame.
        map_5m_to_30m: Mapping array (same semantics as resample_session_15m).
    """
    bars_per_group = 6  # 6 x 5m = 30m

    align_h, align_m = (int(x) for x in align_start.split(":"))
    align_minutes = align_h * 60 + align_m

    timestamps = df.index
    hours = timestamps.hour.values
    minutes = timestamps.minute.values
    bar_minutes = hours * 60 + minutes

    high_vals = df["high"].values.astype(np.float64)
    low_vals = df["low"].values.astype(np.float64)
    open_vals = df["open"].values.astype(np.float64)
    close_vals = df["close"].values.astype(np.float64)
    vol_vals = df["volume"].values.astype(np.float64)

    n = len(df)

    # Assign each bar a position within its session day starting from align_start
    pos_in_day = np.full(n, -1, dtype=np.int64)
    current_day = -1
    counter = 0

    for i in range(n):
        d = int(session_day_id[i])
        bm = int(bar_minutes[i])

        if d != current_day:
            current_day = d
            counter = 0

        if bm < align_minutes:
            continue

        pos_in_day[i] = counter
        counter += 1

    # Group index within day
    group_in_day = np.where(pos_in_day >= 0, pos_in_day // bars_per_group, -1)
    pos_in_group = np.where(pos_in_day >= 0, pos_in_day % bars_per_group, -1)

    # Global 30m bar ID
    global_id = np.where(
        group_in_day >= 0,
        session_day_id * 10000 + group_in_day,
        -1,
    )

    valid_mask = global_id >= 0
    valid_indices = np.where(valid_mask)[0]

    if len(valid_indices) == 0:
        empty = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"], dtype=np.float64,
        )
        return empty, np.full(n, -1, dtype=np.int64)

    gids = global_id[valid_indices]
    unique_gids, first_idx = np.unique(gids, return_index=True)
    order = np.argsort(first_idx)
    unique_gids = unique_gids[order]

    n_30m = len(unique_gids)
    gid_to_pos = {int(g): idx for idx, g in enumerate(unique_gids)}

    bars_open = np.full(n_30m, np.nan)
    bars_high = np.full(n_30m, -np.inf)
    bars_low = np.full(n_30m, np.inf)
    bars_close = np.full(n_30m, np.nan)
    bars_vol = np.zeros(n_30m)
    bars_time = [None] * n_30m
    bars_count = np.zeros(n_30m, dtype=np.int64)

    for raw_i in valid_indices:
        gid = int(global_id[raw_i])
        pos = gid_to_pos[gid]
        p = int(pos_in_group[raw_i])
        if p == 0:
            bars_open[pos] = open_vals[raw_i]
            bars_time[pos] = df.index[raw_i]
        if high_vals[raw_i] > bars_high[pos]:
            bars_high[pos] = high_vals[raw_i]
        if low_vals[raw_i] < bars_low[pos]:
            bars_low[pos] = low_vals[raw_i]
        bars_close[pos] = close_vals[raw_i]
        bars_vol[pos] += vol_vals[raw_i]
        bars_count[pos] += 1

    # Only keep complete 30m bars
    complete_mask = bars_count == bars_per_group
    complete_indices = np.where(complete_mask)[0]

    if len(complete_indices) == 0:
        empty = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"], dtype=np.float64,
        )
        return empty, np.full(n, -1, dtype=np.int64)

    df_30m = pd.DataFrame(
        {
            "open": bars_open[complete_indices],
            "high": bars_high[complete_indices],
            "low": bars_low[complete_indices],
            "close": bars_close[complete_indices],
            "volume": bars_vol[complete_indices],
        },
        index=pd.DatetimeIndex([bars_time[i] for i in complete_indices]),
    )

    old_to_new = np.full(n_30m, -1, dtype=np.int64)
    for new_idx, old_idx in enumerate(complete_indices):
        old_to_new[old_idx] = new_idx

    # Map each 5m bar to its most recent completed 30m bar
    last_bar = bars_per_group - 1
    map_5m = np.full(n, -1, dtype=np.int64)

    for raw_i in range(n):
        gid = int(global_id[raw_i])
        if gid < 0:
            if raw_i > 0:
                map_5m[raw_i] = map_5m[raw_i - 1]
            continue

        pos = gid_to_pos.get(gid, -1)
        if pos < 0:
            if raw_i > 0:
                map_5m[raw_i] = map_5m[raw_i - 1]
            continue

        p = int(pos_in_group[raw_i])
        if p == last_bar:
            new_idx = old_to_new[pos]
            if new_idx >= 0:
                map_5m[raw_i] = new_idx
            elif raw_i > 0:
                map_5m[raw_i] = map_5m[raw_i - 1]
        else:
            if pos > 0:
                new_idx = old_to_new[pos - 1]
                if new_idx >= 0:
                    map_5m[raw_i] = new_idx
                elif raw_i > 0:
                    map_5m[raw_i] = map_5m[raw_i - 1]
            elif raw_i > 0:
                map_5m[raw_i] = map_5m[raw_i - 1]

    return df_30m, map_5m


# ---------------------------------------------------------------------------
# Gate application
# ---------------------------------------------------------------------------

def apply_15m_hh_hl_2_vwap_gate(
    trades: list[TradeResult],
    sig_15m: dict[str, np.ndarray],
) -> list[TradeResult]:
    """Baseline: 15m HH/HL-2 + VWAP side (current implementation)."""
    close = sig_15m["close"]
    vwap = sig_15m["vwap"]
    n = len(close)
    kept: list[TradeResult] = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        s = t.signal_bar
        if s < 0 or s >= n:
            continue
        c, v, d = close[s], vwap[s], t.direction
        if np.isnan(v):
            continue
        if d == 1:
            keep = bool(sig_15m["hh_hl_2_bull"][s]) and c > v
        else:
            keep = bool(sig_15m["hh_hl_2_bear"][s]) and c < v
        if keep:
            kept.append(t)
    return kept


def apply_30m_hh_hl_2_vwap_gate(
    trades: list[TradeResult],
    hh_hl: dict[str, np.ndarray],
    close: np.ndarray,
    vwap: np.ndarray,
) -> list[TradeResult]:
    """30m HH/HL-2 + VWAP side gate."""
    n = len(close)
    kept: list[TradeResult] = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        s = t.signal_bar
        if s < 0 or s >= n:
            continue
        c, v, d = close[s], vwap[s], t.direction
        if np.isnan(v):
            continue
        if d == 1:
            keep = bool(hh_hl["bullish"][s]) and c > v
        else:
            keep = bool(hh_hl["bearish"][s]) and c < v
        if keep:
            kept.append(t)
    return kept


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [t for t in trades if start <= t.date <= end]


def _fmt(m: dict) -> str:
    return (
        f"{m['total_trades']:>4} tr | WR {m['win_rate']:.1%} | "
        f"R {m['total_r']:>7.1f} | Sharpe {m['sharpe_ratio']:>5.2f} | "
        f"Calmar {m['calmar_ratio']:>5.2f} | DD {m['max_drawdown_r']:>6.1f}R"
    )


def _print_yearly(label: str, trades: list[TradeResult]) -> None:
    yr_r: dict[str, float] = defaultdict(float)
    yr_n: dict[str, int] = defaultdict(int)
    for t in trades:
        y = t.date[:4]
        yr_r[y] += t.r_multiple
        yr_n[y] += 1
    print(f"\n  {label} — Yearly R:")
    neg = 0
    for y in sorted(yr_r):
        r = yr_r[y]
        mark = " <<<" if r < 0 else ""
        print(f"    {y}: {yr_n[y]:>4} tr  {r:>+7.1f}R{mark}")
        if r < 0:
            neg += 1
    print(f"    Negative years: {neg}/{len(yr_r)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    print("=" * 80)
    print("NQ NY 30m HH/HL-2 + VWAP Gate — Entry Window Comparison")
    print("=" * 80)

    # --- Build FAST_V2 NQ_NY leg ---
    legs = build_profile_legs("FAST_V2")
    leg = legs["NQ_NY"]
    cfg = leg.config
    session = leg.session

    print(f"\nConfig: rr={cfg.rr}, tp1={cfg.tp1_ratio}, "
          f"stop_atr={session.stop_atr_pct}%, gap_atr={session.min_gap_atr_pct}%, "
          f"atr_len={cfg.atr_length}, dir={cfg.direction_filter}, "
          f"entry={session.entry_start}-{session.entry_end}")

    # --- Load data ---
    print("\nLoading NQ data...")
    t1 = time.time()
    df_5m = load_5m_data("NQ_5m.parquet", start=FULL_START, end=None)
    df_1m = load_1m_for_5m("NQ_5m.parquet", start=FULL_START, end=None)
    end_date = df_5m.index[-1].strftime("%Y-%m-%d")
    print(f"  5m={len(df_5m):,} | 1m={len(df_1m):,} | range {FULL_START} -> {end_date} [{time.time() - t1:.1f}s]")

    # --- Pre-compute shared arrays ---
    ts = df_5m.index
    masks = compute_session_masks(ts, session)
    new_day, session_day_id = compute_session_days(ts, session)
    high = df_5m["high"].values.astype(np.float64)
    low = df_5m["low"].values.astype(np.float64)
    close = df_5m["close"].values.astype(np.float64)
    volume = df_5m["volume"].values.astype(np.float64)
    vwap = compute_session_vwap(high, low, close, volume, session_day_id)
    daily_atr = compute_daily_atr(df_5m, cfg.atr_length)
    orb_high, orb_low, orb_ready = compute_orb_levels(
        df_5m, masks["in_orb"], masks["in_rth"], new_day,
    )

    maps = build_maps(df_5m, df_1m)
    cache = build_signal_cache(df_5m, [cfg])

    # =====================================================================
    # 1. BASELINE — no gate, entry 09:45-13:00
    # =====================================================================
    print("\n--- Running baseline (no gate, entry 09:45-13:00) ---")
    t1 = time.time()
    trades_raw = run_backtest(
        df_5m, cfg, start_date=FULL_START, end_date=end_date,
        df_1m=df_1m, _maps=maps, _signal_cache=cache,
    )
    if leg.excluded_dow:
        trades_raw = apply_dow_filter(trades_raw, set(leg.excluded_dow))
    baseline = [t for t in trades_raw if t.exit_type != EXIT_NO_FILL]
    baseline.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    print(f"  {_fmt(compute_metrics(baseline))} [{time.time() - t1:.1f}s]")

    # =====================================================================
    # 2. Variant A — current 15m HH/HL-2 + VWAP (session-aligned from 09:30)
    #    Entry window: 09:45-13:00. Earliest gate=True at bar after 10:00.
    # =====================================================================
    print("\n--- Computing 15m structure signals (session-aligned from 09:30) ---")
    t1 = time.time()
    sig_15m = compute_all_15m_signals(
        df_5m, session, vwap, daily_atr, orb_high, orb_low, orb_ready, session_day_id,
    )
    variant_a = apply_15m_hh_hl_2_vwap_gate(baseline, sig_15m)
    print(f"  Variant A (15m HH/HL-2 from 09:30): {_fmt(compute_metrics(variant_a))} [{time.time() - t1:.1f}s]")

    # =====================================================================
    # 3. Variant B — true 30m bars starting 08:30, entry 09:45-13:00
    #    30m bars: 08:30-09:00, 09:00-09:30, 09:30-10:00, ...
    #    At 09:50 (first possible signal): sees 08:30-09:00 and 09:00-09:30
    # =====================================================================
    print("\n--- Computing 30m structure (clock-aligned from 08:30) ---")
    t1 = time.time()
    df_30m_b, map_b = resample_clock_30m(df_5m, "08:30", session_day_id)
    hh_hl_b = compute_hh_hl_patterns(df_30m_b, map_b, n_bars=2)
    variant_b = apply_30m_hh_hl_2_vwap_gate(baseline, hh_hl_b, close, vwap)
    print(f"  Variant B (30m from 08:30, entry 09:45): {_fmt(compute_metrics(variant_b))} [{time.time() - t1:.1f}s]")
    print(f"  30m bars: {len(df_30m_b):,} | First bar example: {df_30m_b.index[0] if len(df_30m_b) else 'N/A'}")

    # =====================================================================
    # 4. Variant C — true 30m bars starting 09:00, entry effectively 10:00
    #    30m bars: 09:00-09:30, 09:30-10:00, 10:00-10:30, ...
    #    At 10:00: sees 09:00-09:30 and 09:30-10:00
    # =====================================================================
    print("\n--- Computing 30m structure (clock-aligned from 09:00) ---")
    t1 = time.time()
    df_30m_c, map_c = resample_clock_30m(df_5m, "09:00", session_day_id)
    hh_hl_c = compute_hh_hl_patterns(df_30m_c, map_c, n_bars=2)
    variant_c = apply_30m_hh_hl_2_vwap_gate(baseline, hh_hl_c, close, vwap)
    print(f"  Variant C (30m from 09:00, entry ~10:00): {_fmt(compute_metrics(variant_c))} [{time.time() - t1:.1f}s]")
    print(f"  30m bars: {len(df_30m_c):,} | First bar example: {df_30m_c.index[0] if len(df_30m_c) else 'N/A'}")

    # =====================================================================
    # Comparison tables
    # =====================================================================
    variants = {
        "A: 15m HH/HL-2 (09:30)": variant_a,
        "B: 30m HH/HL-2 (08:30)": variant_b,
        "C: 30m HH/HL-2 (09:00)": variant_c,
    }

    windows = [
        ("Full", FULL_START, end_date),
        ("Recent", RECENT_START, end_date),
        ("2025 Holdout", HOLDOUT_START, end_date),
    ]

    for w_name, w_start, w_end in windows:
        if w_start > end_date:
            continue
        print(f"\n{'=' * 80}")
        print(f"  {w_name} ({w_start} -> {w_end})")
        print("=" * 80)

        bw = filter_window(baseline, w_start, w_end)
        mb = compute_metrics(bw)
        print(f"  {'Baseline (no gate)':<30} {_fmt(mb)}")

        for name, trades in variants.items():
            w = filter_window(trades, w_start, w_end)
            m = compute_metrics(w)
            n_base = mb["total_trades"]
            keep = m["total_trades"] / n_base if n_base else 0.0
            dr = m["total_r"] - mb["total_r"]
            print(f"  {name:<30} {_fmt(m)} | keep {keep:>5.1%} | dR {dr:+6.1f}")

    # Yearly breakdown for each variant
    print(f"\n{'=' * 80}")
    print("Yearly Breakdown")
    print("=" * 80)

    _print_yearly("Baseline", filter_window(baseline, FULL_START, end_date))
    for name, trades in variants.items():
        _print_yearly(name, filter_window(trades, FULL_START, end_date))

    # Signal timing analysis
    print(f"\n{'=' * 80}")
    print("Signal Timing: First Trade Time Distribution")
    print("=" * 80)

    for name, trades in [("Baseline", baseline)] + list(variants.items()):
        fill_times: list[str] = []
        for t in trades:
            if t.fill_time:
                ft = t.fill_time
                # Handle "YYYY-MM-DD HH:MM" or "HH:MM" formats
                try:
                    parts = ft.split(" ")
                    time_part = parts[-1] if len(parts) > 1 else parts[0]
                    hm = time_part.split(":")
                    if len(hm) >= 2:
                        fill_times.append(f"{int(hm[0]):02d}:{int(hm[1]):02d}")
                except (ValueError, IndexError):
                    continue
        if fill_times:
            # Count by 30m bucket
            buckets: dict[str, int] = defaultdict(int)
            for ft in fill_times:
                h, m = int(ft[:2]), int(ft[3:5])
                bucket_m = (m // 30) * 30
                buckets[f"{h:02d}:{bucket_m:02d}"] += 1
            print(f"\n  {name}:")
            for b in sorted(buckets):
                bar = "#" * (buckets[b] // 2)
                print(f"    {b}: {buckets[b]:>4} {bar}")

    # Save results to DB
    print(f"\n{'=' * 80}")
    print("Saving results to DB...")
    print("=" * 80)

    for label, trades, notes in [
        (
            "NQ NY FAST_V2 15m HH/HL-2 VWAP (baseline gate)",
            variant_a,
            "Variant A: 15m session-aligned HH/HL-2 + VWAP. Entry 09:45-13:00. "
            "Earliest gate=True ~10:00.",
        ),
        (
            "NQ NY FAST_V2 30m HH/HL-2 VWAP pre-session (08:30)",
            variant_b,
            "Variant B: True 30m bars from 08:30. At 09:50 sees 08:30-09:00 & "
            "09:00-09:30 bars. Entry window 09:45-13:00.",
        ),
        (
            "NQ NY FAST_V2 30m HH/HL-2 VWAP (09:00, eff 10:00)",
            variant_c,
            "Variant C: True 30m bars from 09:00. At 10:00 sees 09:00-09:30 & "
            "09:30-10:00 bars. Effective entry start 10:00.",
        ),
    ]:
        w = filter_window(trades, FULL_START, end_date)
        m = compute_metrics(w)
        save_cfg = with_overrides(
            cfg,
            name=f"{label} ({FULL_START[:4]}-{end_date[:4]})",
            notes=notes,
        )
        result = results_to_dict(w, save_cfg, include_trades=True, include_equity_curve=True)
        rid = save_backtest_result(result)
        print(f"  {label}: {m['total_trades']} tr, {m['total_r']:.1f}R, "
              f"Calmar {m['calmar_ratio']:.2f} -> ID {rid}")

    print(f"\nDone in {(time.time() - t0) / 60:.1f} minutes")


if __name__ == "__main__":
    main()
