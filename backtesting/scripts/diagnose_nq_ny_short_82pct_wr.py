#!/usr/bin/env python3
"""NQ NY Short — Deep dive into rr=1.5, tp1=0.3, min_stop=10pt (82.9% WR).

Is this WR real or another artifact?
"""

import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime
from statistics import median, mean

import numpy as np

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

# Exit type constants
EXIT_NO_FILL = 0
EXIT_SL = 1
EXIT_TP1_TP2 = 2
EXIT_TP1_BE = 3
EXIT_TP1_EOD = 4
EXIT_EOD = 5
EXIT_TP2_SINGLE = 6

EXIT_NAMES = {
    0: "NO_FILL", 1: "SL", 2: "TP1_TP2", 3: "TP1_BE",
    4: "TP1_EOD", 5: "EOD", 6: "TP2_SINGLE",
}

START_DATE = "2016-01-01"
DATA_YEARS = 10

SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=5.0,
    min_gap_atr_pct=2.0,
    stop_orb_pct=15.0,
    min_gap_orb_pct=7.0,
    min_stop_points=10.0,
)

CONFIG = StrategyConfig(
    sessions=(SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="short",
    rr=1.5,
    tp1_ratio=0.3,
    atr_length=14,
    impulse_close_filter=False,
)


def main():
    print("NQ NY SHORT — 82.9% WR Investigation")
    print("=" * 80)
    print(f"Config: rr={CONFIG.rr}, tp1={CONFIG.tp1_ratio}, orbstop={SESSION.stop_orb_pct}%, "
          f"min_stop={SESSION.min_stop_points}pt")
    print(f"TP1 distance = stop × rr × tp1 = 10pt × 1.5 × 0.3 = 4.5pt (when floor is binding)")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time()-t0:.1f}s]\n")

    trades = run_backtest(df_5m, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    # No DOW filter — look at all trades
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    unfilled = [t for t in trades if t.exit_type == EXIT_NO_FILL]

    print(f"Total candidates: {len(trades)}")
    print(f"Filled: {len(filled)}")
    print(f"Unfilled: {len(unfilled)}")

    # ── 1. EXIT TYPE BREAKDOWN ──
    print("\n" + "=" * 80)
    print("  1. EXIT TYPE BREAKDOWN")
    print("=" * 80)
    exit_counts = Counter(t.exit_type for t in filled)
    exit_r = {}
    for t in filled:
        exit_r.setdefault(t.exit_type, []).append(t.r_multiple)

    for et in sorted(exit_counts.keys()):
        cnt = exit_counts[et]
        rs = exit_r[et]
        avg_r = mean(rs)
        med_r = median(rs)
        min_r = min(rs)
        max_r = max(rs)
        print(f"  {EXIT_NAMES.get(et, str(et)):>12}: {cnt:>5} ({cnt/len(filled)*100:5.1f}%)  "
              f"avg R: {avg_r:+.4f}  med R: {med_r:+.4f}  range: [{min_r:+.3f}, {max_r:+.3f}]")

    # ── 2. STOP DISTANCE DISTRIBUTION ──
    print("\n" + "=" * 80)
    print("  2. STOP DISTANCE DISTRIBUTION (filled trades)")
    print("=" * 80)
    stop_pts = [t.risk_points for t in filled]
    stop_ticks = [t.risk_points / NQ.min_tick for t in filled]

    pcts = [5, 10, 25, 50, 75, 90, 95]
    print(f"  {'Pct':>5} {'Points':>8} {'Ticks':>8}")
    for p in pcts:
        pt = np.percentile(stop_pts, p)
        tk = np.percentile(stop_ticks, p)
        print(f"  {p:>4}% {pt:>8.1f} {tk:>8.0f}")

    # How many at exactly 10pt (floor is binding)?
    at_floor = sum(1 for s in stop_pts if abs(s - 10.0) < 0.01)
    above_floor = sum(1 for s in stop_pts if s > 10.01)
    print(f"\n  At floor (10.0pt): {at_floor} ({at_floor/len(filled)*100:.1f}%)")
    print(f"  Above floor (>10pt): {above_floor} ({above_floor/len(filled)*100:.1f}%)")

    # ── 3. TP1 DISTANCE ──
    print("\n" + "=" * 80)
    print("  3. TP1 DISTANCE (how far price must move for TP1)")
    print("=" * 80)
    tp1_dists = [t.risk_points * CONFIG.rr * CONFIG.tp1_ratio for t in filled]
    print(f"  TP1 formula: risk_pts × rr × tp1 = risk_pts × {CONFIG.rr} × {CONFIG.tp1_ratio}")
    print(f"  {'Pct':>5} {'TP1 pts':>10} {'TP1 ticks':>10}")
    for p in pcts:
        pt = np.percentile(tp1_dists, p)
        tk = pt / NQ.min_tick
        print(f"  {p:>4}% {pt:>10.2f} {tk:>10.0f}")
    print(f"\n  Median TP1 distance: {median(tp1_dists):.2f} pts ({median(tp1_dists)/NQ.min_tick:.0f} ticks)")
    print(f"  Trades with TP1 < 3pt: {sum(1 for d in tp1_dists if d < 3)}")
    print(f"  Trades with TP1 < 5pt: {sum(1 for d in tp1_dists if d < 5)}")
    print(f"  Trades with TP1 < 7pt: {sum(1 for d in tp1_dists if d < 7)}")

    # ── 4. R MULTIPLE DISTRIBUTION ──
    print("\n" + "=" * 80)
    print("  4. R MULTIPLE DISTRIBUTION (filled trades)")
    print("=" * 80)
    r_vals = [t.r_multiple for t in filled]
    print(f"  Mean R: {mean(r_vals):+.4f}")
    print(f"  Median R: {median(r_vals):+.4f}")
    print(f"  {'Pct':>5} {'R':>10}")
    for p in pcts:
        r = np.percentile(r_vals, p)
        print(f"  {p:>4}% {r:>10.4f}")

    # Distribution of R values for TP1_BE trades specifically
    tp1be_r = [t.r_multiple for t in filled if t.exit_type == EXIT_TP1_BE]
    if tp1be_r:
        print(f"\n  TP1_BE trades ({len(tp1be_r)}):")
        print(f"    Mean R: {mean(tp1be_r):+.4f}")
        print(f"    Median R: {median(tp1be_r):+.4f}")
        print(f"    Min R: {min(tp1be_r):+.4f}")
        print(f"    Max R: {max(tp1be_r):+.4f}")
        # How many are exactly at the theoretical tp1_be payout?
        theoretical = 0.5 * CONFIG.tp1_ratio * CONFIG.rr  # half qty at tp1, rest at BE
        print(f"    Theoretical TP1_BE payout: {theoretical:+.4f}R")
        at_theoretical = sum(1 for r in tp1be_r if abs(r - theoretical) < 0.01)
        print(f"    At theoretical: {at_theoretical}/{len(tp1be_r)} ({at_theoretical/len(tp1be_r)*100:.1f}%)")
        # Show spread of actual values
        unique_r = sorted(set(round(r, 4) for r in tp1be_r))
        print(f"    Unique R values: {len(unique_r)}")
        if len(unique_r) <= 20:
            for r_val in unique_r:
                cnt = sum(1 for r in tp1be_r if abs(r - r_val) < 0.001)
                print(f"      R={r_val:+.4f}: {cnt}")

    # ── 5. DOLLAR PNL PER TRADE (real-world viability) ──
    print("\n" + "=" * 80)
    print("  5. DOLLAR PNL AT $5000 RISK")
    print("=" * 80)
    # With 10pt stop: qty = $5000 / (10pt * $20/pt) = 25 contracts
    # TP1_BE payout = 0.5 * 0.3 * 1.5 = 0.225R = $1125
    # Commission = 25 contracts * 2 sides * $0.05 = $2.50 round trip
    qty_at_floor = 5000.0 / (10.0 * 20.0)  # contracts at floor stop
    comm_rt = qty_at_floor * 2 * NQ.commission
    tp1be_dollar = 0.5 * CONFIG.tp1_ratio * CONFIG.rr * 5000.0
    sl_dollar = -5000.0

    print(f"  Position size at 10pt stop: {qty_at_floor:.0f} contracts")
    print(f"  Commission round-trip: ${comm_rt:.2f}")
    print(f"  TP1_BE win (gross): ${tp1be_dollar:.0f}")
    print(f"  TP1_BE win (net of commission): ${tp1be_dollar - comm_rt:.0f}")
    print(f"  SL loss: ${sl_dollar:.0f}")
    print(f"  Commission as % of TP1_BE win: {comm_rt/tp1be_dollar*100:.1f}%")
    print()

    # Now the KEY question: what about slippage?
    # NQ typical slippage = 0.5-1 tick per side = 0.25-0.50 points per side
    for slip_pts in [0.25, 0.5, 1.0, 2.0]:
        # Slippage hurts entry AND exit
        tp1_effective = median(tp1_dists) - 2 * slip_pts  # lose slippage on both entry and exit
        stop_effective = median(stop_pts) + 2 * slip_pts  # stop gets worse
        # Approximate impact on R
        r_impact_per_trade = -2 * slip_pts / median(stop_pts)  # rough
        total_r_impact = r_impact_per_trade * len(filled)
        print(f"  Slippage {slip_pts:.2f}pt/side: effective TP1={tp1_effective:.1f}pt, "
              f"effective stop={stop_effective:.1f}pt, "
              f"~{r_impact_per_trade:+.3f}R/trade, ~{total_r_impact:+.0f}R total")

    # ── 6. YEAR BREAKDOWN WITH EXIT DETAILS ──
    print("\n" + "=" * 80)
    print("  6. YEAR BREAKDOWN WITH EXIT TYPE COUNTS")
    print("=" * 80)
    years = {}
    for t in filled:
        yr = t.date[:4]
        years.setdefault(yr, []).append(t)

    print(f"  {'Year':>6} {'Trades':>6} {'WR':>5} {'R':>7} {'SL':>4} {'TP1BE':>5} "
          f"{'TP1TP2':>6} {'TP1EOD':>6} {'EOD':>4} {'MedStop':>8}")
    for yr in sorted(years.keys()):
        yr_trades = years[yr]
        wins = sum(1 for t in yr_trades if t.r_multiple > 0)
        total_r = sum(t.r_multiple for t in yr_trades)
        et_c = Counter(t.exit_type for t in yr_trades)
        med = median(t.risk_points for t in yr_trades)
        wr = wins / len(yr_trades) if yr_trades else 0
        print(f"  {yr:>6} {len(yr_trades):>6} {wr:>4.0%} {total_r:>+7.1f} "
              f"{et_c.get(1,0):>4} {et_c.get(3,0):>5} {et_c.get(2,0):>6} "
              f"{et_c.get(4,0):>6} {et_c.get(5,0):>4} {med:>7.1f}pt")

    # ── 7. COMPARE: floor-binding vs non-binding trades ──
    print("\n" + "=" * 80)
    print("  7. FLOOR-BINDING vs ORGANIC STOP TRADES")
    print("=" * 80)
    floor_trades = [t for t in filled if t.risk_points <= 10.01]
    organic_trades = [t for t in filled if t.risk_points > 10.01]

    for label, subset in [("Floor-binding (stop=10pt)", floor_trades),
                           ("Organic (stop>10pt)", organic_trades)]:
        if not subset:
            print(f"\n  {label}: 0 trades")
            continue
        wins = sum(1 for t in subset if t.r_multiple > 0)
        total_r = sum(t.r_multiple for t in subset)
        avg_r = mean(t.r_multiple for t in subset)
        med_stop = median(t.risk_points for t in subset)
        wr = wins / len(subset)
        et_c = Counter(t.exit_type for t in subset)
        print(f"\n  {label}: {len(subset)} trades")
        print(f"    WR: {wr:.1%}  Avg R: {avg_r:+.4f}  Total R: {total_r:+.1f}")
        print(f"    Median stop: {med_stop:.1f} pts")
        print(f"    Exits: SL={et_c.get(1,0)}, TP1_BE={et_c.get(3,0)}, "
              f"TP1_TP2={et_c.get(2,0)}, TP1_EOD={et_c.get(4,0)}, EOD={et_c.get(5,0)}")

    elapsed = time.time() - t0
    print(f"\n  Runtime: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
