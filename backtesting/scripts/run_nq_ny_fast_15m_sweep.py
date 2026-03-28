#!/usr/bin/env python3
"""NQ NY FAST profile — 15m structure + VWAP context filter sweep (R1 + R2 combined).

Tests all gates from both rounds on the FAST NQ_NY config:
  long-only, rr=3.5, tp1=0.4, stop_atr=7%, atr_len=12, entry_end=12:00, excl Friday.

Windows: Full (2016+), Recent (2024+), 2025 Holdout
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

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
from orb_backtest.signals.structure_15m import compute_all_15m_signals
from orb_backtest.signals.vwap import compute_session_vwap

from run_fast_v2_nq_context_filters import build_profile_legs

FULL_START = "2016-01-01"
RECENT_START = "2024-01-01"
HOLDOUT_START = "2025-01-01"


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------

def _struct(sig: dict, key: str, s: int, d: int) -> bool:
    if d == 1:
        return bool(sig[f"{key}_bull"][s])
    return bool(sig[f"{key}_bear"][s])


def gate_trades(
    trades: list[TradeResult],
    sig: dict[str, np.ndarray],
    gate_name: str,
) -> list[TradeResult]:
    close = sig["close"]
    vwap = sig["vwap"]
    atr = sig["daily_atr"]
    n = len(close)
    kept: list[TradeResult] = []

    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        s = t.signal_bar
        if s < 0 or s >= n:
            continue
        c, v, a, d = close[s], vwap[s], atr[s], t.direction
        if np.isnan(v) or np.isnan(a) or a <= 0:
            continue
        dist = (c - v) * d
        dp = dist / a

        keep = False

        # R1 gates
        if gate_name == "hh_hl_2_vwap":
            keep = _struct(sig, "hh_hl_2", s, d) and dist > 0
        elif gate_name == "hh_hl_3_vwap":
            keep = _struct(sig, "hh_hl_3", s, d) and dist > 0
        elif gate_name == "hh_hl_2_vwap_d10":
            keep = _struct(sig, "hh_hl_2", s, d) and dp >= 0.10
        elif gate_name == "hh_hl_2_vwap_d15":
            keep = _struct(sig, "hh_hl_2", s, d) and dp >= 0.15
        elif gate_name == "score_gte_2":
            sc = int(sig["bull_score"][s]) if d == 1 else int(sig["bear_score"][s])
            keep = sc >= 2
        elif gate_name == "score_eq_3":
            sc = int(sig["bull_score"][s]) if d == 1 else int(sig["bear_score"][s])
            keep = sc == 3
        elif gate_name == "pullback_holds_vwap":
            keep = _struct(sig, "hh_hl_2", s, d) and dist > 0 and (
                bool(sig["holds_vwap_bull"][s]) if d == 1 else bool(sig["holds_vwap_bear"][s])
            )

        # R2 gates
        elif gate_name == "hh_or_hl_vwap":
            keep = _struct(sig, "hh_or_hl", s, d) and dist > 0
        elif gate_name == "hh_or_hl_vwap_d15":
            keep = _struct(sig, "hh_or_hl", s, d) and dp >= 0.15
        elif gate_name == "any2of3_vwap":
            keep = _struct(sig, "hh_hl_any2of3", s, d) and dist > 0
        elif gate_name == "any2of3_vwap_d15":
            keep = _struct(sig, "hh_hl_any2of3", s, d) and dp >= 0.15
        elif gate_name == "any2of4_vwap":
            keep = _struct(sig, "hh_hl_any2of4", s, d) and dist > 0
        elif gate_name == "any2of4_vwap_d10":
            keep = _struct(sig, "hh_hl_any2of4", s, d) and dp >= 0.10
        elif gate_name == "score_gte2_d15":
            sc = int(sig["bull_score"][s]) if d == 1 else int(sig["bear_score"][s])
            keep = sc >= 2 and dp >= 0.15

        # VWAP-only
        elif gate_name == "vwap_side_only":
            keep = dist > 0
        elif gate_name == "vwap_d10_only":
            keep = dp >= 0.10
        elif gate_name == "vwap_d15_only":
            keep = dp >= 0.15
        elif gate_name == "vwap_d20_only":
            keep = dp >= 0.20
        else:
            raise ValueError(f"Unknown gate: {gate_name}")

        if keep:
            kept.append(t)
    return kept


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [t for t in trades if start <= t.date <= end]


def _fmt(m: dict) -> str:
    return (
        f"{m['total_trades']:>4} tr | WR {m['win_rate']:.1%} | "
        f"R {m['total_r']:>7.1f} | Sharpe {m['sharpe_ratio']:>5.2f} | "
        f"Calmar {m['calmar_ratio']:>5.2f}"
    )


def _print_table(title, baseline, gated, start, end):
    print(f"\n{title}")
    print("-" * len(title))
    bw = filter_window(baseline, start, end)
    mb = compute_metrics(bw)
    print(f"  {'baseline':<25} {_fmt(mb)}")
    for gn, trades in gated.items():
        w = filter_window(trades, start, end)
        m = compute_metrics(w)
        kp = m["total_trades"] / mb["total_trades"] if mb["total_trades"] else 0.0
        dr = m["total_r"] - mb["total_r"]
        print(f"  {gn:<25} {_fmt(m)} | keep {kp:>5.1%} | dR {dr:+6.1f}")


def _print_yearly(label, trades):
    yr_r = defaultdict(float)
    yr_n = defaultdict(int)
    for t in trades:
        y = t.date[:4]
        yr_r[y] += t.r_multiple
        yr_n[y] += 1
    print(f"\n{label} — Yearly R:")
    neg = 0
    for y in sorted(yr_r):
        r = yr_r[y]
        print(f"  {y}: {yr_n[y]:>4} tr  {r:>+7.1f}R")
        if r < 0:
            neg += 1
    print(f"  Negative years: {neg}/{len(yr_r)}")


# ---------------------------------------------------------------------------
# Gate sets
# ---------------------------------------------------------------------------

GATE_SETS = {
    "R1: Structure + VWAP": [
        "hh_hl_2_vwap", "hh_hl_3_vwap",
        "hh_hl_2_vwap_d10", "hh_hl_2_vwap_d15",
        "score_gte_2", "score_eq_3",
        "pullback_holds_vwap",
    ],
    "R2: Relaxed + VWAP Distance": [
        "hh_or_hl_vwap", "hh_or_hl_vwap_d15",
        "any2of3_vwap", "any2of3_vwap_d15",
        "any2of4_vwap", "any2of4_vwap_d10",
        "score_gte2_d15",
    ],
    "VWAP-Only (Reference)": [
        "vwap_side_only", "vwap_d10_only", "vwap_d15_only", "vwap_d20_only",
    ],
}

ALL_GATES = [g for gates in GATE_SETS.values() for g in gates]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    print("NQ NY FAST Profile — 15m Structure + VWAP Sweep")
    print("=" * 72)

    legs = build_profile_legs("FAST")
    leg = legs["NQ_NY"]
    cfg = leg.config
    session = leg.session

    print(f"\nConfig: rr={cfg.rr}, tp1={cfg.tp1_ratio}, stop_atr={session.stop_atr_pct}%, "
          f"gap_atr={session.min_gap_atr_pct}%, atr_len={cfg.atr_length}, "
          f"dir={cfg.direction_filter}, entry_end={session.entry_end}")

    print("\nLoading NQ data...")
    t1 = time.time()
    df_5m = load_5m_data("NQ_5m.parquet", start=FULL_START, end=None)
    df_1m = load_1m_for_5m("NQ_5m.parquet", start=FULL_START, end=None)
    end_date = df_5m.index[-1].strftime("%Y-%m-%d")
    print(f"  5m={len(df_5m):,} | 1m={len(df_1m):,} [{time.time() - t1:.1f}s]")

    # Baseline
    print("\nRunning baseline...")
    t1 = time.time()
    maps = build_maps(df_5m, df_1m)
    cache = build_signal_cache(df_5m, [cfg])
    trades_raw = run_backtest(
        df_5m, cfg, start_date=FULL_START, end_date=end_date,
        df_1m=df_1m, _maps=maps, _signal_cache=cache,
    )
    if leg.excluded_dow:
        trades_raw = apply_dow_filter(trades_raw, set(leg.excluded_dow))
    baseline = [t for t in trades_raw if t.exit_type != EXIT_NO_FILL]
    baseline.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    mb = compute_metrics(baseline)
    print(f"  {mb['total_trades']} tr | WR {mb['win_rate']:.1%} | "
          f"R {mb['total_r']:.1f} | Sharpe {mb['sharpe_ratio']:.2f} | "
          f"Calmar {mb['calmar_ratio']:.2f} [{time.time() - t1:.1f}s]")

    _print_yearly("Baseline", baseline)

    # Signals
    print("\nComputing 15m signals...")
    t1 = time.time()
    ts = df_5m.index
    masks = compute_session_masks(ts, session)
    new_day, session_day_id = compute_session_days(ts, session)
    high = df_5m["high"].values.astype(np.float64)
    low = df_5m["low"].values.astype(np.float64)
    close = df_5m["close"].values.astype(np.float64)
    volume = df_5m["volume"].values.astype(np.float64)
    vwap = compute_session_vwap(high, low, close, volume, session_day_id)
    daily_atr = compute_daily_atr(df_5m, cfg.atr_length)
    orb_high, orb_low, orb_ready = compute_orb_levels(df_5m, masks["in_orb"], masks["in_rth"], new_day)
    sig = compute_all_15m_signals(
        df_5m, session, vwap, daily_atr, orb_high, orb_low, orb_ready, session_day_id,
    )
    print(f"  Done [{time.time() - t1:.1f}s]")

    # Gates
    print(f"\nApplying {len(ALL_GATES)} gates...")
    t1 = time.time()
    gated = {g: gate_trades(baseline, sig, g) for g in ALL_GATES}
    print(f"  Done [{time.time() - t1:.1f}s]")

    # Per-set tables
    windows = [
        ("Full", FULL_START, end_date),
        ("Recent", RECENT_START, end_date),
        ("2025 Holdout", HOLDOUT_START, end_date),
    ]

    for set_title, gate_names in GATE_SETS.items():
        print(f"\n{'=' * 72}")
        print(set_title)
        print("=" * 72)
        subset = {g: gated[g] for g in gate_names}
        for wn, ws, we in windows:
            if ws > end_date:
                continue
            _print_table(f"NQ_NY FAST | {wn} ({ws} -> {we})", baseline, subset, ws, we)

    # Summary
    print(f"\n{'=' * 72}")
    print("Summary: All Gates Ranked by Full-Window Calmar")
    print("=" * 72)

    base_full = filter_window(baseline, FULL_START, end_date)
    mb_full = compute_metrics(base_full)
    rankings = []
    for g in ALL_GATES:
        w = filter_window(gated[g], FULL_START, end_date)
        m = compute_metrics(w)
        rankings.append((g, m))
    rankings.sort(key=lambda x: x[1]["calmar_ratio"], reverse=True)

    print(f"  {'baseline':<25} {_fmt(mb_full)}")
    for i, (g, m) in enumerate(rankings):
        kp = m["total_trades"] / mb_full["total_trades"] if mb_full["total_trades"] else 0.0
        dr = m["total_r"] - mb_full["total_r"]
        tag = " <-- BEST" if i == 0 else ""
        print(f"  {g:<25} {_fmt(m)} | keep {kp:>5.1%} | dR {dr:+6.1f}{tag}")

    # Sweet spot
    print(f"\n{'=' * 72}")
    print("Sweet Spot: keep >= 40% AND Calmar >= 1.5x baseline")
    print("=" * 72)
    bc = mb_full["calmar_ratio"]
    sweet = [
        (g, m) for g, m in rankings
        if (m["total_trades"] / mb_full["total_trades"] if mb_full["total_trades"] else 0) >= 0.40
        and m["calmar_ratio"] >= bc * 1.5
    ]
    if sweet:
        for g, m in sweet:
            kp = m["total_trades"] / mb_full["total_trades"] if mb_full["total_trades"] else 0.0
            dr = m["total_r"] - mb_full["total_r"]
            print(f"  {g:<25} {_fmt(m)} | keep {kp:>5.1%} | dR {dr:+6.1f}")
    else:
        print("  (none found)")

    # Yearly for top 3
    print(f"\n{'=' * 72}")
    print("Yearly Breakdown — Top 3 Gates")
    print("=" * 72)
    for g, m in rankings[:3]:
        _print_yearly(g, filter_window(gated[g], FULL_START, end_date))

    print(f"\nDone in {(time.time() - t0) / 60:.1f} minutes")


if __name__ == "__main__":
    main()
