#!/usr/bin/env python3
"""NQ NY 15m structure + VWAP context filter sweep.

Tests whether 15-minute bar structure (HH/HL, swing scores, multi-day regime)
combined with session VWAP can improve the NQ NY ORB continuation leg.

Baseline: FAST_V2 NQ_NY (stop_atr_pct=8.0, rr=2.5, tp1=0.3, atr_length=14,
entry_end=13:00, both directions, exclude Friday).

Candidate Sets:
A: Local 15m trend + VWAP side (HH/HL-2, HH/HL-3)
B: Local 15m trend + VWAP distance (10%, 15%, bands)
C: Swing score + VWAP (score>=2, score==3)
D: Multi-day regime + VWAP (1-day, 2-day, 2-of-3, with distance)
E: Pullback quality (holds VWAP, holds VWAP+ORB)

Windows:
- Full:    2016-01-01 -> end_date
- Recent:  2024-01-01 -> end_date
- Holdout: 2025-01-01 -> end_date
"""

from __future__ import annotations

import sys
import time
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
# Gate definitions
# ---------------------------------------------------------------------------

def gate_15m_trades(
    trades: list[TradeResult],
    signals: dict[str, np.ndarray],
    gate_name: str,
) -> list[TradeResult]:
    """Filter trades by 15m structure + VWAP gate.

    Each gate checks signals at the trade's signal_bar index.
    """
    close = signals["close"]
    vwap = signals["vwap"]
    atr = signals["daily_atr"]
    n = len(close)

    kept: list[TradeResult] = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        s = t.signal_bar
        if s < 0 or s >= n:
            continue

        c = close[s]
        v = vwap[s]
        a = atr[s]
        d = t.direction  # 1=long, -1=short

        if np.isnan(v) or np.isnan(a) or a <= 0:
            continue

        dist = (c - v) * d  # positive = correct side of VWAP
        dist_pct = dist / a  # as fraction of ATR (not %)

        keep = _eval_gate(gate_name, s, d, c, v, dist, dist_pct, signals)
        if keep:
            kept.append(t)

    return kept


def _eval_gate(
    gate_name: str,
    s: int,
    d: int,
    c: float,
    v: float,
    dist: float,
    dist_pct: float,
    sig: dict[str, np.ndarray],
) -> bool:
    """Evaluate a single gate for one trade."""

    # --- Set A: Local 15m trend + VWAP side ---
    if gate_name == "hh_hl_2_vwap":
        if d == 1:
            return bool(sig["hh_hl_2_bull"][s]) and c > v
        return bool(sig["hh_hl_2_bear"][s]) and c < v

    if gate_name == "hh_hl_3_vwap":
        if d == 1:
            return bool(sig["hh_hl_3_bull"][s]) and c > v
        return bool(sig["hh_hl_3_bear"][s]) and c < v

    # --- Set B: Local 15m trend + VWAP distance ---
    if gate_name == "hh_hl_2_vwap_d10":
        struct = sig["hh_hl_2_bull"][s] if d == 1 else sig["hh_hl_2_bear"][s]
        return bool(struct) and dist_pct >= 0.10

    if gate_name == "hh_hl_2_vwap_d15":
        struct = sig["hh_hl_2_bull"][s] if d == 1 else sig["hh_hl_2_bear"][s]
        return bool(struct) and dist_pct >= 0.15

    if gate_name == "hh_hl_2_vwap_b10_25":
        struct = sig["hh_hl_2_bull"][s] if d == 1 else sig["hh_hl_2_bear"][s]
        return bool(struct) and 0.10 <= dist_pct <= 0.25

    if gate_name == "hh_hl_2_vwap_b15_30":
        struct = sig["hh_hl_2_bull"][s] if d == 1 else sig["hh_hl_2_bear"][s]
        return bool(struct) and 0.15 <= dist_pct <= 0.30

    # --- Set C: Swing score ---
    if gate_name == "score_gte_2":
        if d == 1:
            return int(sig["bull_score"][s]) >= 2
        return int(sig["bear_score"][s]) >= 2

    if gate_name == "score_eq_3":
        if d == 1:
            return int(sig["bull_score"][s]) == 3
        return int(sig["bear_score"][s]) == 3

    # --- Set D: Multi-day regime + VWAP ---
    if gate_name == "regime_1d_vwap":
        if d == 1:
            return bool(sig["regime_1d_bull"][s]) and c > v
        return bool(sig["regime_1d_bear"][s]) and c < v

    if gate_name == "regime_2d_vwap":
        if d == 1:
            return bool(sig["regime_2d_bull"][s]) and c > v
        return bool(sig["regime_2d_bear"][s]) and c < v

    if gate_name == "regime_2of3_vwap":
        if d == 1:
            return bool(sig["regime_2of3_bull"][s]) and c > v
        return bool(sig["regime_2of3_bear"][s]) and c < v

    if gate_name == "regime_2d_vwap_d10":
        if d == 1:
            return bool(sig["regime_2d_bull"][s]) and dist_pct >= 0.10
        return bool(sig["regime_2d_bear"][s]) and dist_pct >= 0.10

    if gate_name == "regime_2d_vwap_d15":
        if d == 1:
            return bool(sig["regime_2d_bull"][s]) and dist_pct >= 0.15
        return bool(sig["regime_2d_bear"][s]) and dist_pct >= 0.15

    # --- Set E: Pullback quality ---
    if gate_name == "pullback_holds_vwap":
        if d == 1:
            return (
                bool(sig["hh_hl_2_bull"][s])
                and c > v
                and bool(sig["holds_vwap_bull"][s])
            )
        return (
            bool(sig["hh_hl_2_bear"][s])
            and c < v
            and bool(sig["holds_vwap_bear"][s])
        )

    if gate_name == "pullback_holds_vwap_orb":
        if d == 1:
            return (
                bool(sig["hh_hl_2_bull"][s])
                and c > v
                and bool(sig["holds_vwap_orb_bull"][s])
            )
        return (
            bool(sig["hh_hl_2_bear"][s])
            and c < v
            and bool(sig["holds_vwap_orb_bear"][s])
        )

    raise ValueError(f"Unknown gate: {gate_name}")


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def filter_window(
    trades: list[TradeResult], start: str, end: str,
) -> list[TradeResult]:
    return [t for t in trades if start <= t.date <= end]


def _fmt_metric(m: dict) -> str:
    return (
        f"{m['total_trades']:>4} tr | WR {m['win_rate']:.1%} | "
        f"R {m['total_r']:>7.1f} | Sharpe {m['sharpe_ratio']:>5.2f} | "
        f"Calmar {m['calmar_ratio']:>5.2f}"
    )


def _print_table(
    title: str,
    baseline_trades: list[TradeResult],
    gated_sets: dict[str, list[TradeResult]],
    start: str,
    end: str,
) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    base_w = filter_window(baseline_trades, start, end)
    m_base = compute_metrics(base_w)
    print(f"  {'baseline':<25} {_fmt_metric(m_base)}")
    for gate_name, trades in gated_sets.items():
        window = filter_window(trades, start, end)
        m = compute_metrics(window)
        keep_pct = m["total_trades"] / m_base["total_trades"] if m_base["total_trades"] else 0.0
        dr = m["total_r"] - m_base["total_r"]
        print(
            f"  {gate_name:<25} {_fmt_metric(m)} | keep {keep_pct:>5.1%} | "
            f"dR {dr:+6.1f}"
        )


# ---------------------------------------------------------------------------
# Gate sets (ordered per user spec)
# ---------------------------------------------------------------------------

GATE_SETS = {
    "Set A: Local 15m Trend + VWAP Side": [
        "hh_hl_2_vwap",
        "hh_hl_3_vwap",
    ],
    "Set B: Local 15m Trend + VWAP Distance": [
        "hh_hl_2_vwap_d10",
        "hh_hl_2_vwap_d15",
        "hh_hl_2_vwap_b10_25",
        "hh_hl_2_vwap_b15_30",
    ],
    "Set C: Swing Score + VWAP": [
        "score_gte_2",
        "score_eq_3",
    ],
    "Set D: Multi-Day Regime + VWAP": [
        "regime_1d_vwap",
        "regime_2d_vwap",
        "regime_2of3_vwap",
        "regime_2d_vwap_d10",
        "regime_2d_vwap_d15",
    ],
    "Set E: Pullback Quality": [
        "pullback_holds_vwap",
        "pullback_holds_vwap_orb",
    ],
}

ALL_GATES = [g for gates in GATE_SETS.values() for g in gates]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    print("NQ NY 15m Structure + VWAP Context Filter Sweep")
    print("=" * 72)
    print("Baseline: FAST_V2 NQ_NY continuation leg")

    # Build FAST_V2 NQ_NY leg
    legs = build_profile_legs("FAST_V2")
    leg = legs["NQ_NY"]
    cfg = leg.config
    session = leg.session

    print(f"\nConfig: rr={cfg.rr}, tp1={cfg.tp1_ratio}, "
          f"stop_atr={session.stop_atr_pct}%, gap_atr={session.min_gap_atr_pct}%, "
          f"atr_len={cfg.atr_length}, entry_end={session.entry_end}")

    # Load data
    print("\nLoading NQ data...")
    t1 = time.time()
    df_5m = load_5m_data("NQ_5m.parquet", start=FULL_START, end=None)
    df_1m = load_1m_for_5m("NQ_5m.parquet", start=FULL_START, end=None)
    end_date = df_5m.index[-1].strftime("%Y-%m-%d")
    print(f"  5m={len(df_5m):,} | 1m={len(df_1m):,} | range {FULL_START} -> {end_date} [{time.time() - t1:.1f}s]")

    # Run baseline backtest
    print("\nRunning baseline backtest...")
    t1 = time.time()
    maps = build_maps(df_5m, df_1m)
    signal_cache = build_signal_cache(df_5m, [cfg])
    trades_raw = run_backtest(
        df_5m, cfg, start_date=FULL_START, end_date=end_date,
        df_1m=df_1m, _maps=maps, _signal_cache=signal_cache,
    )
    if leg.excluded_dow:
        trades_raw = apply_dow_filter(trades_raw, set(leg.excluded_dow))
    baseline = [t for t in trades_raw if t.exit_type != EXIT_NO_FILL]
    baseline.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    m = compute_metrics(baseline)
    print(f"  {m['total_trades']} trades | WR {m['win_rate']:.1%} | "
          f"R {m['total_r']:.1f} | Sharpe {m['sharpe_ratio']:.2f} | "
          f"Calmar {m['calmar_ratio']:.2f} [{time.time() - t1:.1f}s]")

    # Pre-compute 15m structure signals
    print("\nComputing 15m structure signals...")
    t1 = time.time()
    timestamps = df_5m.index
    masks = compute_session_masks(timestamps, session)
    new_day, session_day_id = compute_session_days(timestamps, session)

    high = df_5m["high"].values.astype(np.float64)
    low = df_5m["low"].values.astype(np.float64)
    close = df_5m["close"].values.astype(np.float64)
    volume = df_5m["volume"].values.astype(np.float64)

    vwap = compute_session_vwap(high, low, close, volume, session_day_id)
    daily_atr = compute_daily_atr(df_5m, cfg.atr_length)
    orb_high, orb_low, orb_ready = compute_orb_levels(df_5m, masks["in_orb"], masks["in_rth"], new_day)

    signals = compute_all_15m_signals(
        df_5m, session, vwap, daily_atr, orb_high, orb_low, orb_ready, session_day_id,
    )
    print(f"  Done [{time.time() - t1:.1f}s]")

    # Apply all gates
    print("\nApplying 17 gates...")
    t1 = time.time()
    gated: dict[str, list[TradeResult]] = {}
    for gate_name in ALL_GATES:
        gated[gate_name] = gate_15m_trades(baseline, signals, gate_name)
    print(f"  Done [{time.time() - t1:.1f}s]")

    # Print results per candidate set
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
        for w_name, w_start, w_end in windows:
            if w_start > end_date:
                continue
            _print_table(
                f"NQ_NY | {w_name} ({w_start} -> {w_end})",
                baseline,
                subset,
                w_start,
                w_end,
            )

    # Summary: rank all gates by Calmar on full window
    print(f"\n{'=' * 72}")
    print("Summary: All Gates Ranked by Full-Window Calmar")
    print("=" * 72)

    base_full = filter_window(baseline, FULL_START, end_date)
    m_base_full = compute_metrics(base_full)

    rankings: list[tuple[str, dict]] = []
    for gate_name in ALL_GATES:
        w = filter_window(gated[gate_name], FULL_START, end_date)
        m_g = compute_metrics(w)
        rankings.append((gate_name, m_g))
    rankings.sort(key=lambda x: x[1]["calmar_ratio"], reverse=True)

    print(f"  {'baseline':<25} {_fmt_metric(m_base_full)}")
    for gate_name, m_g in rankings:
        keep_pct = m_g["total_trades"] / m_base_full["total_trades"] if m_base_full["total_trades"] else 0.0
        dr = m_g["total_r"] - m_base_full["total_r"]
        marker = " <-- BEST" if gate_name == rankings[0][0] else ""
        print(
            f"  {gate_name:<25} {_fmt_metric(m_g)} | keep {keep_pct:>5.1%} | "
            f"dR {dr:+6.1f}{marker}"
        )

    # Save best result to DB
    best_gate, best_m = rankings[0]
    best_trades = filter_window(gated[best_gate], FULL_START, end_date)
    if best_m["calmar_ratio"] > m_base_full["calmar_ratio"]:
        print(f"\nSaving best gate '{best_gate}' to DB...")
        save_cfg = with_overrides(
            cfg,
            name=f"NQ NY 15m {best_gate} ({FULL_START[:4]}-{end_date[:4]})",
            notes=(
                f"15m structure + VWAP context filter research. "
                f"Gate: {best_gate}. "
                f"Baseline: {m_base_full['total_trades']} trades, "
                f"{m_base_full['total_r']:.1f}R, Calmar {m_base_full['calmar_ratio']:.2f}. "
                f"Gated: {best_m['total_trades']} trades, "
                f"{best_m['total_r']:.1f}R, Calmar {best_m['calmar_ratio']:.2f}."
            ),
        )
        result = results_to_dict(best_trades, save_cfg, include_trades=True, include_equity_curve=True)
        result_id = save_backtest_result(result)
        print(f"  Saved! ID: {result_id}")
    else:
        print(f"\nNo gate improved Calmar over baseline ({m_base_full['calmar_ratio']:.2f}). Nothing saved.")

    print(f"\nDone in {(time.time() - t0) / 60:.1f} minutes")


if __name__ == "__main__":
    main()
