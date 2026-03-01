#!/usr/bin/env python3
"""No-ORB GC — prop-valid entry windows.

Prop rule: positions must be flat 17:00-18:00 ET.
Tests single-session configs ending <= 16:45, plus a two-session
split (NY regular + after-hours) to see if the 18-20 window adds edge.

Fixes QM=100%, stop=12%, rr=5.0, BE=0, longs only.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

QM      = 100.0
STOP    = 12.0
RR      = 5.0
TP1     = 0.2
ATR_LEN = 50
MIN_GAP = 1.0
MAX_GAP = 25.0

# Prop-valid single sessions (all flat before 17:00)
SINGLE_WINDOWS = [
    ("12:00", "12:00", "12:05"),
    ("14:00", "14:00", "14:05"),
    ("15:00", "15:50", "16:00"),
    ("16:00", "16:00", "16:05"),
    ("16:45", "16:45", "16:50"),
]

# After-hours session (18:05-20:00, flat by 20:05)
AH_SESSION_ONLY = ("18:05", "20:00", "20:00", "20:05")


def make_single_session(entry_end, flat_start, flat_end):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end=entry_end,
        flat_start=flat_start, flat_end=flat_end,
        stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP,
    )
    return StrategyConfig(
        rr=RR, tp1_ratio=TP1, risk_usd=5000.0,
        atr_length=ATR_LEN,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def make_split_config(ny_end, ny_flat_start, ny_flat_end,
                      ah_start, ah_end, ah_flat_start, ah_flat_end):
    """Two sessions: NY regular + after-hours."""
    ny = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end=ny_end,
        flat_start=ny_flat_start, flat_end=ny_flat_end,
        stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP,
    )
    ah = SessionConfig(
        name="AH",
        orb_start="18:00", orb_end="18:05",
        entry_start=ah_start, entry_end=ah_end,
        flat_start=ah_flat_start, flat_end=ah_flat_end,
        stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP,
    )
    return StrategyConfig(
        rr=RR, tp1_ratio=TP1, risk_usd=5000.0,
        atr_length=ATR_LEN,
        min_qty=1.0, qty_step=1.0,
        sessions=(ny, ah), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def stats_for(trades):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if len(filled) < 10:
        return None, filled
    m = compute_metrics(filled)
    yearly = defaultdict(list)
    for t in filled:
        yearly[t.date[:4]].append(t.r_multiple)
    monthly = defaultdict(list)
    for t in filled:
        monthly[t.date[:7]].append(t.r_multiple)
    worst_month = min((sum(v) for v in monthly.values()), default=0)
    return {
        "trades": m["total_trades"], "wr": m["win_rate"],
        "net_r": round(m["total_r"], 1),
        "max_dd": round(m["max_drawdown_r"], 1),
        "sharpe": round(m["sharpe_ratio"], 3),
        "pf": round(m["profit_factor"], 2),
        "r_per_dd": round(m["total_r"] / abs(m["max_drawdown_r"]), 1) if m["max_drawdown_r"] < 0 else 999,
        "worst_month": round(worst_month, 1),
        "mcl": m["max_consecutive_losses"],
        "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
    }, filled


def print_row(label, r, marker=""):
    print(f"{label:<22} | {r['trades']:>6} | {r['wr']:>5.1%} | "
          f"{r['net_r']:>7.1f} | {r['max_dd']:>7.1f} | "
          f"{r['r_per_dd']:>5.1f} | {r['sharpe']:>7.3f} | "
          f"{r['pf']:>5.2f} | {r['worst_month']:>7.1f} | "
          f"{r['mcl']:>4}{marker}")


def main():
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    results = {}
    t0 = time.time()

    # Single-session prop-valid configs
    for entry_end, flat_start, flat_end in SINGLE_WINDOWS:
        cfg = make_single_session(entry_end, flat_start, flat_end)
        trades = run_backtest_no_orb(df, cfg, start_date="2016-01-01", df_1m=df_1m)
        m, _ = stats_for(trades)
        label = f"NY only → {entry_end}"
        if m:
            results[label] = m
            print(f"  {label}: {m['trades']} trades, {m['net_r']}R, {m['max_dd']}R DD, Sharpe {m['sharpe']:.3f}")
        else:
            print(f"  {label}: insufficient trades")

    # AH session only (QM from 18:05)
    ah_entry, ah_end, ah_flat_s, ah_flat_e = AH_SESSION_ONLY
    ah_cfg = SessionConfig(
        name="AH",
        orb_start="18:00", orb_end="18:05",
        entry_start=ah_entry, entry_end=ah_end,
        flat_start=ah_flat_s, flat_end=ah_flat_e,
        stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP,
    )
    ah_only_cfg = StrategyConfig(
        rr=RR, tp1_ratio=TP1, risk_usd=5000.0,
        atr_length=ATR_LEN,
        min_qty=1.0, qty_step=1.0,
        sessions=(ah_cfg,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )
    ah_trades = run_backtest_no_orb(df, ah_only_cfg, start_date="2016-01-01", df_1m=df_1m)
    ah_m, _ = stats_for(ah_trades)
    if ah_m:
        results["AH only (18:05-20:00)"] = ah_m
        print(f"  AH only (18:05-20:00): {ah_m['trades']} trades, {ah_m['net_r']}R, {ah_m['max_dd']}R DD, Sharpe {ah_m['sharpe']:.3f}")
    else:
        print(f"  AH only (18:05-20:00): insufficient trades")

    # Split: NY 09:35-16:45 + AH 18:05-20:00
    for ny_end, ny_flat_s, ny_flat_e in [("16:00", "16:00", "16:05"), ("16:45", "16:45", "16:50")]:
        cfg = make_split_config(ny_end, ny_flat_s, ny_flat_e, "18:05", "20:00", "20:00", "20:05")
        trades = run_backtest_no_orb(df, cfg, start_date="2016-01-01", df_1m=df_1m)
        m, _ = stats_for(trades)
        label = f"NY→{ny_end} + AH→20:00"
        if m:
            results[label] = m
            print(f"  {label}: {m['trades']} trades, {m['net_r']}R, {m['max_dd']}R DD, Sharpe {m['sharpe']:.3f}")
        else:
            print(f"  {label}: insufficient trades")

    print(f"\nDone in {time.time()-t0:.0f}s\n")

    hdr = (f"{'Window':<22} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | "
           f"{'Max DD':>7} | {'R/DD':>5} | {'Sharpe':>7} | {'PF':>5} | "
           f"{'WorstMo':>7} | {'MCL':>4}")
    print("=" * 110)
    print("NO-ORB GC — PROP-VALID WINDOWS (QM=100%, stop=12%, rr=5.0, BE=0, longs)")
    print("=" * 110)
    print(hdr)
    print("-" * 110)
    for label, r in results.items():
        marker = " ***" if r["max_dd"] >= -10.0 and r["net_r"] > 0 else ""
        print_row(label, r, marker)

    print(f"\n{'='*70}")
    print("YEARLY BREAKDOWN")
    print(f"{'='*70}")
    for label, r in results.items():
        if "yearly" not in r:
            continue
        print(f"\n{label} | {r['trades']} trades, {r['net_r']}R, {r['max_dd']}R DD, Sharpe {r['sharpe']:.3f}")
        for yr in sorted(r["yearly"]):
            print(f"  {yr}: {r['yearly'][yr]:+.1f}R")

    print(f"\nv9 baseline (ORB-anchored, NY only): 250 trades, 74.7R, -5.2R DD, Sharpe 3.80")


if __name__ == "__main__":
    main()
