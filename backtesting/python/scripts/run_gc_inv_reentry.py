#!/usr/bin/env python3
"""GC Inversion Longs — Re-entry after first trade resolves.

Two-pass test:
  Pass 1: Normal v9 backtest (1 trade/day), record outcomes + exit bars
  Pass 2: For each day with a filled trade, scan for a NEW inversion signal
          starting after the first trade's exit bar. Simulate that second trade.

Analysis:
  - 2nd trade after 1st WINS vs 2nd trade after 1st LOSES
  - Combined (1st + 2nd) vs baseline (1st only)
"""

import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.engine.simulator import (
    EXIT_NO_FILL, EXIT_SL, EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_EOD,
    EXIT_TP2_SINGLE, TradeResult,
    _simulate_single_trade_magnifier,
    _scan_fill_bar_magnifier,
    compute_session_masks, compute_session_days, compute_date_strings,
    compute_daily_atr, compute_orb_levels, detect_fvg,
    _precompute_day_boundaries,
    _SetupCandidate,
)
from orb_backtest.data.bar_mapping import build_5m_to_1m_map, map_1m_to_5m
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED = ("20241218",)
START = "2016-01-01"


def build_session():
    return SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=1.0,
        qualifying_move_atr_pct=10.0,
    )


def build_config():
    return StrategyConfig(
        rr=3.5,
        tp1_ratio=0.2,
        risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0,
        qty_step=1.0,
        sessions=(build_session(),),
        instrument=GC,
        strategy="inversion",
        direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS,
        excluded_dates=EXCLUDED,
    )


import math


def find_second_inversion_after(
    df, df_1m, config, session, first_trades,
):
    """Scan for second inversion signal after each first trade exits.

    For each filled first trade, scan bars after exit_bar for a new bearish FVG
    inversion (producing a LONG). If found, simulate it and return the result.
    """
    timestamps = df.index
    masks = compute_session_masks(timestamps, session)
    new_session_day, session_day_id = compute_session_days(timestamps, session)
    daily_atr = compute_daily_atr(df, config.atr_length)
    orb_high, orb_low, orb_ready = compute_orb_levels(
        df, masks["in_orb"], masks["in_rth"], new_session_day
    )
    fvg = detect_fvg(
        df["high"].values, df["low"].values, daily_atr,
        orb_high, orb_low,
        session.min_gap_atr_pct, session.max_gap_points,
    )
    date_strs = compute_date_strings(timestamps)
    excluded = set(config.excluded_dates)

    valid_short = (
        fvg["short_fvg"] & masks["in_entry"] & masks["in_rth"] & orb_ready
    )
    if excluded:
        exclude_arr = np.array(list(excluded))
        exclude_mask = np.isin(date_strs, exclude_arr)
        valid_short &= ~exclude_mask

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    dates = timestamps.date
    n = len(df)

    short_fvg_top = fvg["short_fvg_top"]

    # Build exit_bar lookup: date → exit_bar index
    exit_bar_by_date = {}
    for t in first_trades:
        if t.exit_type != EXIT_NO_FILL and t.exit_bar >= 0:
            exit_bar_by_date[t.date] = t.exit_bar

    # QM gate: track running low per session day
    qm_pct = session.qualifying_move_atr_pct
    session_running_low = {}

    # Scan for second inversion candidates (bearish FVG → LONG)
    # Only consider signals AFTER the first trade's exit bar
    second_candidates = []

    pending_short = []  # bearish FVGs waiting for bullish inversion → long
    seen_second = set()

    for i in range(n):
        sd = session_day_id[i]
        date_str = str(dates[i])

        # Track running low for QM gate
        if sd not in session_running_low:
            session_running_low[sd] = low[i]
        elif low[i] < session_running_low[sd]:
            session_running_low[sd] = low[i]

        # Only register NEW FVGs that appear AFTER the first trade's exit
        exit_bar = exit_bar_by_date.get(date_str, -1)
        if exit_bar < 0:
            continue  # no first trade on this day

        # Register bearish FVGs as pending (only after exit of first trade)
        if valid_short[i] and i > exit_bar:
            pending_short.append((
                i, short_fvg_top[i],
                fvg["short_gap_size"][i], daily_atr[i], sd, date_str,
            ))

        # Check pending for bullish inversion (close above FVG top → LONG)
        remaining = []
        for pending in pending_short:
            fvg_bar, inv_level, gap_size, atr, fvg_sd, fvg_date = pending

            if sd != fvg_sd or i <= fvg_bar:
                remaining.append(pending)
                continue
            if not masks["in_entry"][i]:
                continue

            if close[i] > inv_level and date_str not in seen_second:
                # QM gate for longs
                if qm_pct > 0.0:
                    orb_l = orb_low[i]
                    if not np.isnan(orb_l) and not np.isnan(atr) and atr > 0:
                        qualifying_level = orb_l - (qm_pct / 100.0) * atr
                        running_low = session_running_low.get(sd, float("inf"))
                        if running_low > qualifying_level:
                            remaining.append(pending)
                            continue

                seen_second.add(date_str)
                second_candidates.append(_SetupCandidate(
                    date_str=date_str,
                    session=session.name,
                    direction=1,
                    signal_bar=i - 1,
                    entry_price=close[i],
                    gap_size=gap_size,
                    daily_atr=atr,
                ))
                continue
            remaining.append(pending)
        pending_short = remaining

        # Cleanup old session days
        pending_short = [p for p in pending_short if p[4] >= sd]

    if not second_candidates:
        return []

    # Simulate the second candidates
    bar_map = build_5m_to_1m_map(df, df_1m)
    high_1m = df_1m["high"].values.astype(np.float64)
    low_1m = df_1m["low"].values.astype(np.float64)
    close_1m = df_1m["close"].values.astype(np.float64)

    half_day_set = set(HALF_DAYS)
    day_bounds = _precompute_day_boundaries(
        timestamps, masks, half_day_set, date_strs, session_day_id
    )

    results = []
    for cand in second_candidates:
        atr = cand.daily_atr
        if np.isnan(atr) or atr <= 0:
            continue

        entry = cand.entry_price
        stop_dist = (session.stop_atr_pct / 100.0) * atr
        stop = entry - stop_dist
        risk_pts = entry - stop
        if risk_pts <= 0:
            continue

        qty_raw = config.risk_usd / (risk_pts * config.point_value)
        qty = math.floor(qty_raw / config.qty_step) * config.qty_step
        if qty < config.min_qty:
            continue

        is_single = qty <= config.min_qty
        half_qty = qty if is_single else max(
            math.floor((qty / 2) / config.qty_step) * config.qty_step,
            config.min_qty,
        )

        tp1 = entry + config.rr * risk_pts * config.tp1_ratio
        tp2 = entry + config.rr * risk_pts
        be = entry

        sd = session_day_id[cand.signal_bar]
        entry_bar_start = cand.signal_bar + 1
        bounds = day_bounds.get(sd)
        if bounds is None:
            continue

        entry_bar_end = bounds["entry_last"]
        if entry_bar_end < 0 or entry_bar_end < entry_bar_start:
            continue

        flat_bar_start = bounds["flat_first"]
        if flat_bar_start < 0:
            flat_bar_start = min(entry_bar_end + 200, n - 1)
        last_bar = min(flat_bar_start + 20, n - 1)

        # Map to 1m
        es_1m = bar_map[entry_bar_start, 0]
        ee_1m = bar_map[min(entry_bar_end, len(bar_map) - 1), 1] - 1
        fs_1m = bar_map[min(flat_bar_start, len(bar_map) - 1), 0]
        lb_1m = bar_map[min(last_bar, len(bar_map) - 1), 1] - 1

        fill_bar_1m, exit_type, exit_bar_1m, pnl_pts, _, _ = _simulate_single_trade_magnifier(
            high_1m, low_1m, close_1m,
            es_1m, ee_1m, fs_1m, lb_1m,
            1,  # direction = long
            entry, stop, tp1, tp2, be,
            is_single, qty, half_qty,
            config.point_value,
            config.commission_per_contract,
        )

        fill_bar = map_1m_to_5m(fill_bar_1m, bar_map) if fill_bar_1m >= 0 else -1
        exit_bar = map_1m_to_5m(exit_bar_1m, bar_map) if exit_bar_1m >= 0 else -1

        pnl_usd = pnl_pts * qty * config.point_value
        if exit_type != EXIT_NO_FILL:
            pnl_usd -= 2 * qty * config.commission_per_contract
        r_multiple = pnl_pts / risk_pts if risk_pts > 0 else 0.0

        results.append(TradeResult(
            date=cand.date_str, session="NY_2nd",
            direction=1, signal_bar=cand.signal_bar,
            fill_bar=fill_bar, entry_price=entry,
            stop_price=stop, tp1_price=tp1, tp2_price=tp2,
            exit_type=exit_type, exit_bar=exit_bar,
            pnl_points=pnl_pts, pnl_usd=pnl_usd,
            r_multiple=r_multiple, qty=qty, half_qty=half_qty,
            gap_size=cand.gap_size, risk_points=risk_pts,
            fill_time=str(timestamps[fill_bar]) if fill_bar >= 0 else "",
            exit_time=str(timestamps[exit_bar]) if exit_bar >= 0 else "",
        ))

    return results


def print_metrics_table(label, m):
    print(f"\n  {label}")
    print(f"  {'─'*55}")
    print(f"  Trades:  {m['total_trades']:>6d}     Win Rate: {m['win_rate']:>6.1%}")
    print(f"  Net R:   {m['total_r']:>6.1f}R     Avg R:    {m['avg_r']:>6.3f}R")
    print(f"  Sharpe:  {m['sharpe_ratio']:>6.3f}     PF:       {m['profit_factor']:>6.2f}")
    print(f"  Max DD:  {m['max_drawdown_r']:>6.1f}R     Calmar:   {m['calmar_ratio']:>6.2f}")


def main():
    print("=" * 70)
    print("  GC Inversion Longs — Re-entry Test")
    print("  2nd inversion after 1st trade exits")
    print("=" * 70)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    config = build_config()
    session = config.sessions[0]

    # ── Pass 1: Normal backtest ─────────────────────────────────────────
    print("\nPass 1: Running v9 baseline (1 trade/day)...")
    t0 = time.time()
    first_trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)
    print(f"  Done in {time.time() - t0:.1f}s")

    filled_first = [t for t in first_trades if t.exit_type != EXIT_NO_FILL]
    m1 = compute_metrics(first_trades)
    print_metrics_table("Pass 1: First trade per day (v9 baseline)", m1)

    # Classify first trades
    winners = [t for t in filled_first if t.r_multiple > 0]
    losers = [t for t in filled_first if t.r_multiple <= 0]
    print(f"\n  Winners: {len(winners)} | Losers: {len(losers)}")

    # ── Pass 2: Find second inversion after exit ────────────────────────
    print("\nPass 2: Scanning for 2nd inversion after each first trade exits...")
    t0 = time.time()
    second_trades = find_second_inversion_after(df, df_1m, config, session, filled_first)
    print(f"  Done in {time.time() - t0:.1f}s")

    filled_second = [t for t in second_trades if t.exit_type != EXIT_NO_FILL]
    print(f"  Found {len(second_trades)} 2nd candidates, {len(filled_second)} filled")

    if not filled_second:
        print("\n  No second trades found. Done.")
        return

    # ── Analysis: 2nd trade conditional on 1st outcome ──────────────────
    winner_dates = set(t.date for t in winners)
    loser_dates = set(t.date for t in losers)

    second_after_win = [t for t in filled_second if t.date in winner_dates]
    second_after_loss = [t for t in filled_second if t.date in loser_dates]

    print(f"\n  2nd trades after 1st WIN:  {len(second_after_win)}")
    print(f"  2nd trades after 1st LOSS: {len(second_after_loss)}")

    # ── Results tables ──────────────────────────────────────────────────
    print("\n" + "═" * 70)

    if filled_second:
        m_all_2nd = compute_metrics(second_trades)
        print_metrics_table("ALL 2nd trades", m_all_2nd)

    if second_after_win:
        # Need to wrap in a format compute_metrics can handle
        r_list = [t.r_multiple for t in second_after_win]
        n = len(r_list)
        w = sum(1 for r in r_list if r > 0)
        total_r = sum(r_list)
        avg_r = total_r / n
        wr = w / n
        print(f"\n  2nd trade AFTER WINNER (n={n})")
        print(f"  {'─'*40}")
        print(f"  WR: {wr:.1%} | Net R: {total_r:.1f} | Avg R: {avg_r:.3f}")

    if second_after_loss:
        r_list = [t.r_multiple for t in second_after_loss]
        n = len(r_list)
        w = sum(1 for r in r_list if r > 0)
        total_r = sum(r_list)
        avg_r = total_r / n
        wr = w / n
        print(f"\n  2nd trade AFTER LOSER (n={n})")
        print(f"  {'─'*40}")
        print(f"  WR: {wr:.1%} | Net R: {total_r:.1f} | Avg R: {avg_r:.3f}")

    # ── Combined: 1st + 2nd ─────────────────────────────────────────────
    print("\n" + "═" * 70)

    # Combined: all 1st + all 2nd
    combined_all = sorted(first_trades + second_trades, key=lambda t: t.date)
    m_combined = compute_metrics(combined_all)
    print_metrics_table("COMBINED: 1st + all 2nd trades", m_combined)

    # Combined: 1st + 2nd only after losses
    if second_after_loss:
        combined_loss = sorted(first_trades + [t for t in second_trades if t.date in loser_dates],
                               key=lambda t: t.date)
        m_loss = compute_metrics(combined_loss)
        print_metrics_table("COMBINED: 1st + 2nd after LOSS only", m_loss)

    # Combined: 1st + 2nd only after wins
    if second_after_win:
        combined_win = sorted(first_trades + [t for t in second_trades if t.date in winner_dates],
                              key=lambda t: t.date)
        m_win = compute_metrics(combined_win)
        print_metrics_table("COMBINED: 1st + 2nd after WIN only", m_win)

    # ── Summary ─────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print("  SUMMARY")
    print("═" * 70)
    print(f"  {'Config':>35s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'PF':>6s} {'Max DD':>7s}")
    print(f"  {'─'*70}")
    print(f"  {'v9 Baseline (1st only)':>35s} {m1['total_trades']:>7d} {m1['win_rate']:>5.1%} {m1['total_r']:>7.1f} {m1['profit_factor']:>6.2f} {m1['max_drawdown_r']:>7.1f}")
    if filled_second:
        print(f"  {'+ all 2nd trades':>35s} {m_combined['total_trades']:>7d} {m_combined['win_rate']:>5.1%} {m_combined['total_r']:>7.1f} {m_combined['profit_factor']:>6.2f} {m_combined['max_drawdown_r']:>7.1f}")
    if second_after_loss:
        print(f"  {'+ 2nd after LOSS only':>35s} {m_loss['total_trades']:>7d} {m_loss['win_rate']:>5.1%} {m_loss['total_r']:>7.1f} {m_loss['profit_factor']:>6.2f} {m_loss['max_drawdown_r']:>7.1f}")
    if second_after_win:
        print(f"  {'+ 2nd after WIN only':>35s} {m_win['total_trades']:>7d} {m_win['win_rate']:>5.1%} {m_win['total_r']:>7.1f} {m_win['profit_factor']:>6.2f} {m_win['max_drawdown_r']:>7.1f}")

    print()


if __name__ == "__main__":
    main()
