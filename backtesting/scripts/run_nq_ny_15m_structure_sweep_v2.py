#!/usr/bin/env python3
"""NQ NY 15m structure sweep v2 — relaxed gates for higher trade retention.

Round 1 found HH/HL-2 + VWAP is a strong filter (Calmar 2x baseline) but
keeps only ~35% of trades. This sweep tests relaxed variants that trade off
some edge sharpness for higher retention:

Set F: Relaxed structure (HH-only, HL-only, HH-or-HL) + VWAP
Set G: Widened lookback (any HH/HL in last 2-3 15m pairs) + VWAP
Set H: Swing score + VWAP distance (score alone was weak, distance may help)
Set I: VWAP-only gates (no structure) as retention ceiling reference
Set J: Best combos with relaxed distance floors

Windows: Full (2016+), Recent (2024+), 2025 Holdout
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

def gate_trades(
    trades: list[TradeResult],
    sig: dict[str, np.ndarray],
    gate_name: str,
) -> list[TradeResult]:
    """Filter trades by gate. Returns kept trades."""
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

        c = close[s]
        v = vwap[s]
        a = atr[s]
        d = t.direction

        if np.isnan(v) or np.isnan(a) or a <= 0:
            continue

        dist = (c - v) * d
        dist_pct = dist / a

        if _eval(gate_name, s, d, c, v, dist, dist_pct, sig):
            kept.append(t)

    return kept


def _struct(sig: dict, key_prefix: str, s: int, d: int) -> bool:
    """Check a bull/bear structure signal at index s."""
    if d == 1:
        return bool(sig[f"{key_prefix}_bull"][s])
    return bool(sig[f"{key_prefix}_bear"][s])


def _eval(
    gate: str, s: int, d: int, c: float, v: float,
    dist: float, dist_pct: float, sig: dict,
) -> bool:
    # --- Set F: Relaxed structure + VWAP side ---
    if gate == "hh_only_vwap":
        return _struct(sig, "hh_only", s, d) and dist > 0

    if gate == "hl_only_vwap":
        return _struct(sig, "hl_only", s, d) and dist > 0

    if gate == "hh_or_hl_vwap":
        return _struct(sig, "hh_or_hl", s, d) and dist > 0

    # --- Set F with distance ---
    if gate == "hh_only_vwap_d10":
        return _struct(sig, "hh_only", s, d) and dist_pct >= 0.10

    if gate == "hl_only_vwap_d10":
        return _struct(sig, "hl_only", s, d) and dist_pct >= 0.10

    if gate == "hh_or_hl_vwap_d10":
        return _struct(sig, "hh_or_hl", s, d) and dist_pct >= 0.10

    if gate == "hh_or_hl_vwap_d15":
        return _struct(sig, "hh_or_hl", s, d) and dist_pct >= 0.15

    # --- Set G: Widened lookback + VWAP ---
    if gate == "any2of3_vwap":
        return _struct(sig, "hh_hl_any2of3", s, d) and dist > 0

    if gate == "any2of4_vwap":
        return _struct(sig, "hh_hl_any2of4", s, d) and dist > 0

    if gate == "any2of3_vwap_d10":
        return _struct(sig, "hh_hl_any2of3", s, d) and dist_pct >= 0.10

    if gate == "any2of3_vwap_d15":
        return _struct(sig, "hh_hl_any2of3", s, d) and dist_pct >= 0.15

    if gate == "any2of4_vwap_d10":
        return _struct(sig, "hh_hl_any2of4", s, d) and dist_pct >= 0.10

    # --- Set H: Swing score + VWAP distance ---
    if gate == "score_gte2_d10":
        score = int(sig["bull_score"][s]) if d == 1 else int(sig["bear_score"][s])
        return score >= 2 and dist_pct >= 0.10

    if gate == "score_gte2_d15":
        score = int(sig["bull_score"][s]) if d == 1 else int(sig["bear_score"][s])
        return score >= 2 and dist_pct >= 0.15

    if gate == "score_eq3_d10":
        score = int(sig["bull_score"][s]) if d == 1 else int(sig["bear_score"][s])
        return score == 3 and dist_pct >= 0.10

    # --- Set I: VWAP-only (no structure) as reference ---
    if gate == "vwap_side_only":
        return dist > 0

    if gate == "vwap_d10_only":
        return dist_pct >= 0.10

    if gate == "vwap_d15_only":
        return dist_pct >= 0.15

    # --- Set J: Best R1 combos with relaxed distance ---
    if gate == "hh_hl_2_vwap_d5":
        return _struct(sig, "hh_hl_2", s, d) and dist_pct >= 0.05

    if gate == "hh_or_hl_vwap_d5":
        return _struct(sig, "hh_or_hl", s, d) and dist_pct >= 0.05

    if gate == "any2of3_vwap_d5":
        return _struct(sig, "hh_hl_any2of3", s, d) and dist_pct >= 0.05

    raise ValueError(f"Unknown gate: {gate}")


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


def _print_table(
    title: str, baseline: list[TradeResult],
    gated: dict[str, list[TradeResult]], start: str, end: str,
) -> None:
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


# ---------------------------------------------------------------------------
# Gate sets
# ---------------------------------------------------------------------------

GATE_SETS = {
    "Set F: Relaxed Structure + VWAP": [
        "hh_only_vwap", "hl_only_vwap", "hh_or_hl_vwap",
        "hh_only_vwap_d10", "hl_only_vwap_d10",
        "hh_or_hl_vwap_d10", "hh_or_hl_vwap_d15",
    ],
    "Set G: Widened Lookback + VWAP": [
        "any2of3_vwap", "any2of4_vwap",
        "any2of3_vwap_d10", "any2of3_vwap_d15",
        "any2of4_vwap_d10",
    ],
    "Set H: Swing Score + VWAP Distance": [
        "score_gte2_d10", "score_gte2_d15", "score_eq3_d10",
    ],
    "Set I: VWAP-Only (Reference)": [
        "vwap_side_only", "vwap_d10_only", "vwap_d15_only",
    ],
    "Set J: Relaxed Distance Floors": [
        "hh_hl_2_vwap_d5", "hh_or_hl_vwap_d5", "any2of3_vwap_d5",
    ],
}

ALL_GATES = [g for gates in GATE_SETS.values() for g in gates]

# Round 1 best gates for comparison
R1_REFERENCE = {
    "hh_hl_2_vwap": None,
    "hh_hl_2_vwap_d15": None,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    print("NQ NY 15m Structure Sweep v2 — Relaxed Gates")
    print("=" * 72)

    legs = build_profile_legs("FAST_V2")
    leg = legs["NQ_NY"]
    cfg = leg.config
    session = leg.session

    print(f"\nConfig: rr={cfg.rr}, tp1={cfg.tp1_ratio}, "
          f"stop_atr={session.stop_atr_pct}%, atr_len={cfg.atr_length}")

    # Load data
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
    # Add hh_hl_2 keys for Set J (reuse from existing signals)
    sig["hh_hl_2_bull"] = sig["hh_hl_2_bull"]
    sig["hh_hl_2_bear"] = sig["hh_hl_2_bear"]
    print(f"  Done [{time.time() - t1:.1f}s]")

    # Apply all gates + R1 references
    print(f"\nApplying {len(ALL_GATES)} gates + R1 references...")
    t1 = time.time()
    gated: dict[str, list[TradeResult]] = {}
    for g in ALL_GATES:
        gated[g] = gate_trades(baseline, sig, g)

    # R1 reference gates (inline, don't need structure_15m import)
    from run_nq_ny_15m_structure_sweep import gate_15m_trades
    for g in R1_REFERENCE:
        gated[f"R1:{g}"] = gate_15m_trades(baseline, sig, g)
    print(f"  Done [{time.time() - t1:.1f}s]")

    # Print per-set tables
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
            _print_table(f"NQ_NY | {wn} ({ws} -> {we})", baseline, subset, ws, we)

    # Summary ranked by Calmar
    print(f"\n{'=' * 72}")
    print("Summary: All Gates + R1 References Ranked by Full-Window Calmar")
    print("=" * 72)

    base_full = filter_window(baseline, FULL_START, end_date)
    mb_full = compute_metrics(base_full)

    all_names = ALL_GATES + [f"R1:{g}" for g in R1_REFERENCE]
    rankings = []
    for g in all_names:
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

    # Sweet-spot analysis: gates with keep >= 40% and Calmar >= 1.5x baseline
    print(f"\n{'=' * 72}")
    print("Sweet Spot: keep >= 40% AND Calmar >= 1.5x baseline")
    print("=" * 72)
    base_calmar = mb_full["calmar_ratio"]
    sweet = [
        (g, m) for g, m in rankings
        if (m["total_trades"] / mb_full["total_trades"] if mb_full["total_trades"] else 0) >= 0.40
        and m["calmar_ratio"] >= base_calmar * 1.5
    ]
    if sweet:
        for g, m in sweet:
            kp = m["total_trades"] / mb_full["total_trades"] if mb_full["total_trades"] else 0.0
            dr = m["total_r"] - mb_full["total_r"]
            print(f"  {g:<25} {_fmt(m)} | keep {kp:>5.1%} | dR {dr:+6.1f}")
    else:
        print("  (none found)")

    print(f"\nDone in {(time.time() - t0) / 60:.1f} minutes")


if __name__ == "__main__":
    main()
