#!/usr/bin/env python3
"""NQ NY No-ORB Inversion — Clean Air vs Within-FVG Sweep.

Phase A: Sweep QM/stop/RR/tp1 across long, short, and both directions
         to find viable no-ORB inversion configs.
Phase B: Apply clean-air filter (no prior FVG zones in sweep path) at
         varying lookback windows on the best config per direction.

Bar magnifier ON, ATR 14, entry 09:50–15:00, flat 15:50.
"""

import sys
import time
from collections import defaultdict
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

NQ = get_instrument("NQ")
START_DATE = "2015-01-01"


# ---------------------------------------------------------------------------
# Config builder
# ---------------------------------------------------------------------------

QM_ATR_PCTS = [50, 75, 100, 125, 150, 200]
STOP_ATR_PCTS = [7, 9, 11, 13]
RRS = [2.0, 3.0, 4.0, 5.0]
TP1_RATIOS = [0.2, 0.4, 0.6]
DIRECTIONS = ["short", "long", "both"]


def make_config(qm_atr_pct, stop_atr_pct, rr, tp1_ratio, direction):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:50", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=stop_atr_pct,
        min_gap_atr_pct=3.0,
        max_gap_points=100.0,
        qualifying_move_atr_pct=qm_atr_pct,
    )
    return StrategyConfig(
        rr=rr, tp1_ratio=tp1_ratio, risk_usd=5000.0,
        atr_length=14,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=NQ,
        strategy="inversion", direction_filter=direction,
        use_bar_magnifier=True,
    )


def stats(trades):
    if len(trades) < 5:
        return None
    m = compute_metrics(trades)
    monthly = defaultdict(list)
    yearly = defaultdict(list)
    for t in trades:
        monthly[t.date[:7]].append(t.r_multiple)
        yearly[t.date[:4]].append(t.r_multiple)
    wm = min((sum(v) for v in monthly.values()), default=0)
    return {
        **m,
        "worst_month": round(wm, 1),
        "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
        "trades_per_year": len(trades) / max(len(yearly), 1),
    }


# ---------------------------------------------------------------------------
# Phase A — Parameter sweep per direction
# ---------------------------------------------------------------------------

def run_phase_a(df, df_1m):
    param_combos = list(product(QM_ATR_PCTS, STOP_ATR_PCTS, RRS, TP1_RATIOS))
    total = len(param_combos) * len(DIRECTIONS)
    print(f"Phase A: {len(param_combos)} param combos × {len(DIRECTIONS)} directions = {total} runs\n")

    all_results = {d: [] for d in DIRECTIONS}
    t0 = time.time()
    run_count = 0

    for direction in DIRECTIONS:
        print(f"\n--- Direction: {direction.upper()} ---")
        for i, (qm, stop, rr, tp1) in enumerate(param_combos, 1):
            run_count += 1
            cfg = make_config(qm, stop, rr, tp1, direction)
            trades = run_backtest_no_orb(df, cfg, start_date=START_DATE, df_1m=df_1m)
            filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
            m = stats(filled)
            if m is None:
                continue
            all_results[direction].append({
                "dir": direction, "qm": qm, "stop": stop, "rr": rr, "tp1": tp1,
                "trades": len(filled), "wr": m["win_rate"],
                "net_r": m["total_r"], "dd": m["max_drawdown_r"],
                "calmar": m["calmar_ratio"], "sharpe": m["sharpe_ratio"],
                "pf": m["profit_factor"], "wm": m["worst_month"],
                "mcl": m["max_consecutive_losses"],
                "yearly": m["yearly"],
            })
            if i % 20 == 0:
                elapsed = time.time() - t0
                print(f"  [{direction} {i}/{len(param_combos)}] {elapsed:.0f}s")

    elapsed = time.time() - t0
    print(f"\nPhase A done in {elapsed:.0f}s\n")

    # Print top 20 per direction, sorted by Calmar
    best_per_dir = {}
    for direction in DIRECTIONS:
        res = all_results[direction]
        res.sort(key=lambda r: r["calmar"], reverse=True)

        print("=" * 140)
        print(f"PHASE A — TOP 20 BY CALMAR: {direction.upper()}")
        print("=" * 140)
        print(f"  {'#':>3} | {'QM%':>4} | {'Stop%':>5} | {'RR':>4} | {'TP1':>4} | "
              f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Max DD':>7} | "
              f"{'Calmar':>7} | {'Sharpe':>7} | {'PF':>5} | {'WM':>6} | {'MCL':>4}")
        print("-" * 140)
        for rank, r in enumerate(res[:20], 1):
            nr = round(r["net_r"], 1)
            dd = round(r["dd"], 1)
            pos = " +" if r["calmar"] > 0 else ""
            print(f"  {rank:>3} | {r['qm']:>4} | {r['stop']:>5} | {r['rr']:>4.1f} | "
                  f"{r['tp1']:>4.1f} | {r['trades']:>6} | {r['wr']:>5.1%} | "
                  f"{nr:>7.1f} | {dd:>7.1f} | {r['calmar']:>7.2f} | "
                  f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['wm']:>6.1f} | "
                  f"{r['mcl']:>4}")

        # Yearly breakdown for top 3
        print(f"\n  YEARLY R — TOP 3 ({direction.upper()})")
        print(f"  {'-'*80}")
        for rank, r in enumerate(res[:3], 1):
            print(f"  #{rank}: QM={r['qm']}% Stop={r['stop']}% RR={r['rr']} TP1={r['tp1']}")
            for yr in sorted(r["yearly"]):
                print(f"    {yr}: {r['yearly'][yr]:>+6.1f}R")
            print()

        if res:
            best_per_dir[direction] = res[0]

    return best_per_dir


# ---------------------------------------------------------------------------
# Phase B — Clean air filter
# ---------------------------------------------------------------------------

def build_bullish_fvgs(df: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    """Bullish FVGs per date: zone = (high[2], low[0])."""
    high = df["high"].values
    low = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values

    high_2 = np.roll(high, 2)
    high_1 = np.roll(high, 1)
    low_2 = np.roll(low, 2)

    bull = (high_2 < low) & (high_2 < high_1) & (low_2 < low)
    bull[:2] = False

    fvg_by_date: dict[str, list] = defaultdict(list)
    for i in np.where(bull)[0]:
        bottom, top = float(high_2[i]), float(low[i])
        if bottom < top:
            fvg_by_date[dates[i]].append((bottom, top))
    return dict(fvg_by_date)


def build_bearish_fvgs(df: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    """Bearish FVGs per date: zone = (high[0], low[2])."""
    high = df["high"].values
    low = df["low"].values
    dates = df.index.strftime("%Y-%m-%d").values

    high_2 = np.roll(high, 2)
    low_1 = np.roll(low, 1)
    low_2 = np.roll(low, 2)

    bear = (low_2 > high) & (low_2 > low_1) & (high_2 > high)
    bear[:2] = False

    fvg_by_date: dict[str, list] = defaultdict(list)
    for i in np.where(bear)[0]:
        bottom, top = float(high[i]), float(low_2[i])
        if bottom < top:
            fvg_by_date[dates[i]].append((bottom, top))
    return dict(fvg_by_date)


def build_session_lows(df: pd.DataFrame) -> dict[str, float]:
    """Session lows during NY hours (09:30–15:50)."""
    mask = ((df.index.time >= pd.Timestamp("09:30").time()) &
            (df.index.time <= pd.Timestamp("15:50").time()))
    s = df[mask].copy()
    s["ds"] = s.index.strftime("%Y-%m-%d")
    return s.groupby("ds")["low"].min().to_dict()


def build_session_highs(df: pd.DataFrame) -> dict[str, float]:
    """Session highs during NY hours (09:30–15:50)."""
    mask = ((df.index.time >= pd.Timestamp("09:30").time()) &
            (df.index.time <= pd.Timestamp("15:50").time()))
    s = df[mask].copy()
    s["ds"] = s.index.strftime("%Y-%m-%d")
    return s.groupby("ds")["high"].max().to_dict()


def clean_air_filter_longs(filled, fvg_by_date, session_lows, lookback):
    """For longs: keep trades where session_low > all prior bullish FVG tops (clean air below)."""
    sorted_dates = sorted(fvg_by_date.keys())
    date_to_idx = {d: i for i, d in enumerate(sorted_dates)}

    kept = []
    for t in filled:
        sess_low = session_lows.get(t.date, float("inf"))
        idx = date_to_idx.get(t.date, -1)
        if idx < 0:
            continue

        prior_zones = []
        for past_d in sorted_dates[max(0, idx - lookback): idx]:
            prior_zones.extend(fvg_by_date.get(past_d, []))

        if not prior_zones or all(sess_low > fvg_top for (_, fvg_top) in prior_zones):
            kept.append(t)

    return kept


def clean_air_filter_shorts(filled, fvg_by_date, session_highs, lookback):
    """For shorts: keep trades where session_high < all prior bearish FVG bottoms (clean air above)."""
    sorted_dates = sorted(fvg_by_date.keys())
    date_to_idx = {d: i for i, d in enumerate(sorted_dates)}

    kept = []
    for t in filled:
        sess_high = session_highs.get(t.date, 0.0)
        idx = date_to_idx.get(t.date, -1)
        if idx < 0:
            continue

        prior_zones = []
        for past_d in sorted_dates[max(0, idx - lookback): idx]:
            prior_zones.extend(fvg_by_date.get(past_d, []))

        if not prior_zones or all(sess_high < fvg_bottom for (fvg_bottom, _) in prior_zones):
            kept.append(t)

    return kept


def print_comparison_row(label, m, trades):
    if m is None:
        print(f"  {label:<16} | insufficient trades (<5)")
        return
    nr = round(m["net_r"], 1)
    dd = round(m["dd"], 1)
    calmar = round(m["calmar"], 2)
    print(f"  {label:<16} | {len(trades):>6} | {m['trades_per_year']:>5.1f} | "
          f"{m['wr']:>5.1%} | {nr:>7.1f} | {dd:>7.1f} | {calmar:>7.2f} | "
          f"{m['sharpe']:>7.3f} | {m['pf']:>5.2f} | {m['wm']:>6.1f} | "
          f"{m['mcl']:>4}")


def run_phase_b(df, df_1m, best_per_dir):
    bull_fvgs = build_bullish_fvgs(df)
    bear_fvgs = build_bearish_fvgs(df)
    session_lows = build_session_lows(df)
    session_highs = build_session_highs(df)

    def row_stats(trade_list):
        m = stats(trade_list)
        if m is None:
            return None
        return {
            "wr": m["win_rate"], "net_r": m["total_r"],
            "dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
            "sharpe": m["sharpe_ratio"], "pf": m["profit_factor"],
            "wm": m["worst_month"], "mcl": m["max_consecutive_losses"],
            "yearly": m["yearly"], "trades_per_year": m["trades_per_year"],
        }

    for direction, best in best_per_dir.items():
        print("\n\n" + "=" * 140)
        print(f"PHASE B — CLEAN AIR FILTER: {direction.upper()}")
        print(f"Config: QM={best['qm']}% Stop={best['stop']}% "
              f"RR={best['rr']} TP1={best['tp1']}")
        print("=" * 140)

        cfg = make_config(best["qm"], best["stop"], best["rr"], best["tp1"], direction)
        t0 = time.time()
        trades = run_backtest_no_orb(df, cfg, start_date=START_DATE, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"\nBase: {len(filled)} filled trades ({time.time()-t0:.0f}s)\n")

        # Split into longs and shorts for direction="both"
        if direction == "both":
            long_trades = [t for t in filled if t.direction == 1]
            short_trades = [t for t in filled if t.direction == -1]
        elif direction == "long":
            long_trades = filled
            short_trades = []
        else:
            long_trades = []
            short_trades = filled

        # Header
        print(f"  {'Filter':<16} | {'Trades':>6} | {'T/yr':>5} | {'WR':>6} | "
              f"{'Net R':>7} | {'Max DD':>7} | {'Calmar':>7} | {'Sharpe':>7} | "
              f"{'PF':>5} | {'WM':>6} | {'MCL':>4}")
        print("-" * 140)

        # All trades
        m_all = row_stats(filled)
        print_comparison_row("ALL", m_all, filled)

        if long_trades:
            print_comparison_row("  Longs only", row_stats(long_trades), long_trades)
        if short_trades:
            print_comparison_row("  Shorts only", row_stats(short_trades), short_trades)
        print()

        # Apply clean-air filter per direction
        results = {}
        for n in [1, 2, 3, 5, 10, 20]:
            # Longs: sweep dropped into clean air (no bullish FVG zones below)
            kept_long = clean_air_filter_longs(long_trades, bull_fvgs, session_lows, n) if long_trades else []
            # Shorts: sweep rallied into clean air (no bearish FVG zones above)
            kept_short = clean_air_filter_shorts(short_trades, bear_fvgs, session_highs, n) if short_trades else []

            kept = kept_long + kept_short
            kept.sort(key=lambda t: t.date)

            kept_set = set(id(t) for t in kept)
            complement = [t for t in filled if id(t) not in kept_set]

            m_clean = row_stats(kept)
            m_within = row_stats(complement)

            results[n] = {"clean": (kept, m_clean), "within": (complement, m_within)}

            print_comparison_row(f"Clean N={n}", m_clean, kept)
            print_comparison_row(f"Within N={n}", m_within, complement)
            print()

        # Yearly breakdown
        if not m_all:
            continue
        print(f"\n  {'='*100}")
        print(f"  YEARLY: ALL vs CLEAN AIR vs WITHIN FVG ({direction.upper()})")
        print(f"  {'='*100}")
        years = sorted({t.date[:4] for t in filled})
        header = f"  {'Year':<6}  {'ALL':>10}"
        for n in [1, 3, 5, 10, 20]:
            header += f"  {'C-N='+str(n):>10}  {'W-N='+str(n):>10}"
        print(header)
        print("  " + "-" * (len(header) - 2))

        for yr in years:
            row = f"  {yr:<6}"
            all_yr_r = m_all["yearly"].get(yr, 0)
            all_yr_cnt = sum(1 for t in filled if t.date[:4] == yr)
            row += f"  {all_yr_r:>+5.1f}({all_yr_cnt:>3})"

            for n in [1, 3, 5, 10, 20]:
                kept, m_c = results[n]["clean"]
                comp, m_w = results[n]["within"]

                c_yr = m_c["yearly"].get(yr, 0) if m_c else 0
                c_cnt = sum(1 for t in kept if t.date[:4] == yr)
                w_yr = m_w["yearly"].get(yr, 0) if m_w else 0
                w_cnt = sum(1 for t in comp if t.date[:4] == yr)

                row += f"  {c_yr:>+5.1f}({c_cnt:>3})  {w_yr:>+5.1f}({w_cnt:>3})"
            print(row)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    df = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    best_per_dir = run_phase_a(df, df_1m)
    if not best_per_dir:
        print("No viable configs found in Phase A.")
        return

    run_phase_b(df, df_1m, best_per_dir)


if __name__ == "__main__":
    main()
