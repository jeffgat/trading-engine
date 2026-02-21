#!/usr/bin/env python3
"""No-ORB GC liquidity sweep inversions — sweep entry windows across the day.

Tests whether the same signal (QM sweep + FVG inversion) works during different
time windows: LDN session, NY morning, full NY, extended NY, and LDN+NY combined.
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

# Best params from prior sweep — vary only session window
QM_VALUES   = [75.0, 100.0, 125.0]
STOP        = 13.0
RR          = 3.5
TP1         = 0.2
ATR_LEN     = 50
BE          = 10
MIN_GAP     = 1.0
MAX_GAP_PTS = 25.0

# Named time windows to test
WINDOWS = {
    "LDN":          ("03:00", "03:15", "03:15", "08:20", "08:20", "08:25"),
    "LDN extended": ("02:00", "02:15", "02:15", "09:00", "09:00", "09:05"),
    "NY morning":   ("09:30", "09:35", "09:35", "12:00", "15:50", "16:00"),
    "NY full":      ("09:30", "09:35", "09:35", "15:00", "15:50", "16:00"),
    "NY extended":  ("09:30", "09:35", "09:35", "17:00", "17:00", "17:05"),
    "NY+after":     ("09:30", "09:35", "09:35", "20:00", "20:00", "20:05"),
}

# LDN+NY combined runs two sessions at once
LDN_SESSION = SessionConfig(
    name="LDN", orb_start="03:00", orb_end="03:15",
    entry_start="03:15", entry_end="08:20",
    flat_start="08:20", flat_end="08:25",
    stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP, max_gap_points=MAX_GAP_PTS,
)
NY_SESSION = SessionConfig(
    name="NY", orb_start="09:30", orb_end="09:35",
    entry_start="09:35", entry_end="15:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP, max_gap_points=MAX_GAP_PTS,
)


def make_config(sessions, qm):
    sessions_with_qm = tuple(
        SessionConfig(**{**s.__dict__, "qualifying_move_atr_pct": qm})
        for s in sessions
    )
    return StrategyConfig(
        rr=RR, tp1_ratio=TP1, risk_usd=5000.0,
        atr_length=ATR_LEN,
        min_qty=1.0, qty_step=1.0,
        sessions=sessions_with_qm, instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def session_from_window(name, orb_s, orb_e, entry_s, entry_e, flat_s, flat_e, qm):
    sess_name = "LDN" if "LDN" in name else "NY"
    return SessionConfig(
        name=sess_name,
        orb_start=orb_s, orb_end=orb_e,
        entry_start=entry_s, entry_end=entry_e,
        flat_start=flat_s, flat_end=flat_e,
        stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP,
        max_gap_points=MAX_GAP_PTS, qualifying_move_atr_pct=qm,
    )


def run_and_stats(df, df_1m, sessions, qm):
    cfg = make_config(sessions, qm)
    # Override qm already baked in sessions — pass sessions directly
    cfg2 = StrategyConfig(
        rr=RR, tp1_ratio=TP1, risk_usd=5000.0,
        atr_length=ATR_LEN,
        min_qty=1.0, qty_step=1.0,
        sessions=sessions, instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )
    trades = run_backtest_no_orb(df, cfg2, start_date="2016-01-01", df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if len(filled) < 10:
        return None, filled
    return compute_metrics(filled), filled


def main():
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    results = []
    t0 = time.time()

    for window_name, (orb_s, orb_e, entry_s, entry_e, flat_s, flat_e) in WINDOWS.items():
        for qm in QM_VALUES:
            sess_name = "LDN" if "LDN" in window_name else "NY"
            session = SessionConfig(
                name=sess_name,
                orb_start=orb_s, orb_end=orb_e,
                entry_start=entry_s, entry_end=entry_e,
                flat_start=flat_s, flat_end=flat_e,
                stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP,
                max_gap_points=MAX_GAP_PTS, qualifying_move_atr_pct=qm,
            )
            m, filled = run_and_stats(df, df_1m, (session,), qm)
            if m is None:
                results.append({"window": window_name, "qm": qm, "sessions": "single",
                                 "trades": len(filled), "wr": 0, "net_r": 0, "max_dd": 0,
                                 "sharpe": 0, "pf": 0})
                continue
            dd = round(m["max_drawdown_r"], 1)
            nr = round(m["total_r"], 1)

            # Per-year for printing later
            yearly = defaultdict(list)
            for t in filled:
                yearly[t.date[:4]].append(t.r_multiple)
            monthly = defaultdict(list)
            for t in filled:
                monthly[t.date[:7]].append(t.r_multiple)
            worst_month = min((sum(v) for v in monthly.values()), default=0)

            results.append({
                "window": window_name, "qm": qm, "sessions": "single",
                "trades": m["total_trades"], "wr": m["win_rate"],
                "net_r": nr, "max_dd": dd,
                "sharpe": round(m["sharpe_ratio"], 3),
                "pf": round(m["profit_factor"], 2),
                "r_per_dd": round(nr / abs(dd), 1) if dd < 0 else 999,
                "worst_month": round(worst_month, 1),
                "mcl": m["max_consecutive_losses"],
                "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
            })

    # LDN + NY combined
    for qm in QM_VALUES:
        ldn = SessionConfig(
            name="LDN", orb_start="03:00", orb_end="03:15",
            entry_start="03:15", entry_end="08:20",
            flat_start="08:20", flat_end="08:25",
            stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP,
            max_gap_points=MAX_GAP_PTS, qualifying_move_atr_pct=qm,
        )
        ny = SessionConfig(
            name="NY", orb_start="09:30", orb_end="09:35",
            entry_start="09:35", entry_end="15:00",
            flat_start="15:50", flat_end="16:00",
            stop_atr_pct=STOP, min_gap_atr_pct=MIN_GAP,
            max_gap_points=MAX_GAP_PTS, qualifying_move_atr_pct=qm,
        )
        m, filled = run_and_stats(df, df_1m, (ldn, ny), qm)
        if m is None:
            results.append({"window": "LDN+NY", "qm": qm, "sessions": "combined",
                             "trades": len(filled), "wr": 0, "net_r": 0, "max_dd": 0,
                             "sharpe": 0, "pf": 0})
            continue
        dd = round(m["max_drawdown_r"], 1)
        nr = round(m["total_r"], 1)
        yearly = defaultdict(list)
        for t in filled:
            yearly[t.date[:4]].append(t.r_multiple)
        monthly = defaultdict(list)
        for t in filled:
            monthly[t.date[:7]].append(t.r_multiple)
        worst_month = min((sum(v) for v in monthly.values()), default=0)
        results.append({
            "window": "LDN+NY", "qm": qm, "sessions": "combined",
            "trades": m["total_trades"], "wr": m["win_rate"],
            "net_r": nr, "max_dd": dd,
            "sharpe": round(m["sharpe_ratio"], 3),
            "pf": round(m["profit_factor"], 2),
            "r_per_dd": round(nr / abs(dd), 1) if dd < 0 else 999,
            "worst_month": round(worst_month, 1),
            "mcl": m["max_consecutive_losses"],
            "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
        })

    print(f"Done in {time.time()-t0:.0f}s\n")

    # Summary table
    print("=" * 120)
    print("NO-ORB LIQUIDITY SWEEP — GC longs, stop=13%, rr=3.5, varying entry window + QM%")
    print("=" * 120)
    hdr = (f"{'Window':<16} | {'QM%':>5} | {'Trades':>6} | {'WR':>6} | "
           f"{'Net R':>7} | {'Max DD':>7} | {'R/DD':>5} | {'Sharpe':>7} | {'PF':>5} | "
           f"{'WorstMo':>7} | {'MCL':>4}")
    print(hdr)
    print("-" * 120)

    results.sort(key=lambda r: r.get("sharpe", 0), reverse=True)
    for r in results:
        marker = " ***" if r.get("max_dd", 0) >= -12.0 and r.get("net_r", 0) > 0 else ""
        print(
            f"{r['window']:<16} | {r['qm']:>5.0f} | {r['trades']:>6} | {r.get('wr', 0):>5.1%} | "
            f"{r.get('net_r', 0):>7.1f} | {r.get('max_dd', 0):>7.1f} | "
            f"{r.get('r_per_dd', 0):>5.1f} | {r.get('sharpe', 0):>7.3f} | "
            f"{r.get('pf', 0):>5.2f} | {r.get('worst_month', 0):>7.1f} | "
            f"{r.get('mcl', 0):>4}{marker}"
        )

    # Yearly breakdown for best config per window
    print(f"\n{'='*90}")
    print("BEST CONFIG PER WINDOW — yearly R breakdown")
    print(f"{'='*90}")
    seen_windows = set()
    for r in results:
        w = r["window"]
        if w in seen_windows or "yearly" not in r:
            continue
        seen_windows.add(w)
        print(f"\n{w}  QM={r['qm']:.0f}%  |  {r['trades']} trades, {r['net_r']}R, "
              f"{r['max_dd']}R DD, Sharpe {r['sharpe']:.3f}")
        for yr in sorted(r["yearly"]):
            print(f"  {yr}: {r['yearly'][yr]:+.1f}R")

    print(f"\nv9 baseline (ORB-anchored, NY only): 250 trades, 74.7R, -5.2R DD, Sharpe 3.80")


if __name__ == "__main__":
    main()
