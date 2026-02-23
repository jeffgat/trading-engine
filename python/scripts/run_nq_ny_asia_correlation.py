#!/usr/bin/env python3
"""NQ NY R20 × NQ Asia R9 Restart — Drawdown Correlation & Gating Analysis.

Combined NQ (NY R20 + Asia R9 Restart) has DD of -24.2R, which is worse than
either leg alone (NY: -21.9R, Asia: -11.3R). If the sessions were independent,
the combined DD should benefit from diversification. The fact that combined DD
exceeds the worst individual leg suggests the drawdown periods overlap.

This script re-runs both backtests and performs 8 sections of analysis:

  1. Individual metrics — side-by-side comparison table
  2. Trade date overlap — how often both sessions fire on the same day
  3. Daily R correlation — Pearson r on concurrent dates + all active dates (0-fill)
  4. Outcome crosstab — Win/Loss 2×2 matrix, conditional win rates
  5. Drawdown period overlap — top 5 DD periods per session, timeline visualization
  6. Monthly R correlation — monthly sums + rolling by year + double-hit months
  7. Regime analysis — ATR percentile buckets, yearly performance buckets
  8. Gating ideas — 6 ideas (A–F) to reduce combined DD

No DB writes. DD is informational only, not a hard filter.
"""

import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import apply_dow_filter, TUE
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import (
    run_backtest,
    EXIT_NO_FILL,
    EXIT_NAMES,
)
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.signals.daily_atr import compute_daily_atr

# ── Constants ─────────────────────────────────────────────────────────────────

ASIA_DOW_EXCL = {TUE}  # Asia R9 Restart excludes Tuesday
START_DATE = "2016-01-01"

LABELS = ["NY", "ASIA"]


# ── Formatting helpers ────────────────────────────────────────────────────────

def sep(title: str = "", char: str = "─", width: int = 74) -> None:
    if title:
        pad = char * max(0, (width - len(title) - 2) // 2)
        print(f"\n{pad} {title} {pad}")
    else:
        print(char * width)


# ── Pearson correlation (no scipy dependency) ─────────────────────────────────

def pearsonr(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Return (r, p_value) using numpy + math.erf for p-value approximation."""
    n = len(x)
    if n < 4:
        return np.nan, np.nan
    r = float(np.corrcoef(x, y)[0, 1])
    if abs(r) >= 1.0:
        return r, 0.0
    t_stat = r * math.sqrt(n - 2) / math.sqrt(1.0 - r * r)
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t_stat) / math.sqrt(2.0))))
    return r, p


# ── Core helpers ──────────────────────────────────────────────────────────────

def trade_to_dict(t) -> dict:
    """Convert TradeResult NamedTuple to dict for analysis helpers."""
    return {
        "date": t.date,
        "session": t.session,
        "direction": t.direction,
        "r_multiple": t.r_multiple,
        "fill_time": t.fill_time,
        "exit_time": t.exit_time,
        "exit_type": EXIT_NAMES.get(t.exit_type, str(t.exit_type)),
        "entry_price": t.entry_price,
        "stop_price": t.stop_price,
        "tp1_price": t.tp1_price,
        "tp2_price": t.tp2_price,
        "pnl_points": t.pnl_points,
        "pnl_usd": t.pnl_usd,
        "gap_size": t.gap_size,
        "risk_points": t.risk_points,
    }


def trade_outcome(t: dict) -> str:
    r = t["r_multiple"]
    if r > 0:
        return "Win"
    elif r < 0:
        return "Loss"
    return "BE"


def quick_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0.0, "avg_r": 0.0, "net_r": 0.0,
                "calmar": 0.0, "max_dd": 0.0, "sharpe": 0.0}
    r = np.array([t["r_multiple"] for t in trades])
    wins = int((r > 0).sum())
    r_eq = np.cumsum(r)
    r_pk = np.maximum.accumulate(r_eq)
    max_dd = float(abs(np.min(r_eq - r_pk)))
    net_r = float(r_eq[-1])
    avg_r = float(np.mean(r))
    std_r = float(np.std(r, ddof=1)) if len(r) > 1 else 1.0
    sharpe = (avg_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0
    return {
        "n": len(trades),
        "wr": wins / len(trades),
        "avg_r": avg_r,
        "net_r": net_r,
        "max_dd": max_dd,
        "calmar": net_r / max_dd if max_dd > 0 else 0.0,
        "sharpe": sharpe,
    }


def monthly_r(trades: list[dict]) -> dict[str, float]:
    m: dict[str, float] = {}
    for t in trades:
        key = t["date"][:7]
        m[key] = m.get(key, 0.0) + t["r_multiple"]
    return m


def r_by_year(trades: list[dict]) -> dict[str, float]:
    yr: dict[str, float] = {}
    for t in trades:
        key = t["date"][:4]
        yr[key] = yr.get(key, 0.0) + t["r_multiple"]
    return yr


def weekly_key(date_str: str) -> str:
    """Return ISO year-week string e.g. '2024-W03'."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ── Config builders (from save_nq_combined_ny_asia.py) ────────────────────────

def make_ny_config() -> StrategyConfig:
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=8.75,
        min_gap_atr_pct=2.25,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=2.625,
        tp1_ratio=0.3,
        atr_length=12,
    )


def make_asia_config() -> StrategyConfig:
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",
        entry_start="20:15",
        entry_end="22:30",
        flat_start="04:00",
        flat_end="07:00",
        stop_atr_pct=4.0,
        min_gap_atr_pct=0.90,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.6,
        atr_length=5,
        impulse_close_filter=True,
    )


# ── Data loading & backtest ──────────────────────────────────────────────────

def run_both_backtests() -> tuple[dict[str, list[dict]], pd.DataFrame]:
    """Run NY R20 and Asia R9 Restart backtests, return filled trades and 5m df."""
    result: dict[str, list[dict]] = {}

    print("  Loading NQ data...")
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"    Loaded [{time.time() - t0:.1f}s]")

    # NY R20
    ny_cfg = make_ny_config()
    print("  Running NY R20 (both, rr=2.625, stop=8.75%, ATR=12, ORB=20m)...")
    t0 = time.time()
    ny_trades = run_backtest(df_5m, ny_cfg, start_date=START_DATE,
                             df_1m=df_1m, df_1s=df_1s)
    ny_filled = [trade_to_dict(t) for t in ny_trades if t.exit_type != EXIT_NO_FILL]
    result["NY"] = ny_filled
    print(f"    NY: {len(ny_filled)} filled trades [{time.time() - t0:.1f}s]")

    # Asia R9 Restart + DOW filter (exclude Tuesday)
    asia_cfg = make_asia_config()
    print("  Running Asia R9 Restart (long, rr=3.0, stop=4.0%, ATR=5, excl-Tue, ICF)...")
    t0 = time.time()
    asia_trades = run_backtest(df_5m, asia_cfg, start_date=START_DATE,
                               df_1m=df_1m, df_1s=df_1s)
    asia_trades = apply_dow_filter(asia_trades, ASIA_DOW_EXCL)
    asia_filled = [trade_to_dict(t) for t in asia_trades if t.exit_type != EXIT_NO_FILL]
    result["ASIA"] = asia_filled
    print(f"    Asia: {len(asia_filled)} filled trades [{time.time() - t0:.1f}s]")

    return result, df_5m


# ── SECTION 1 — Individual Metrics ───────────────────────────────────────────

def section1_individual(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 1 — Individual Metrics (Side-by-Side)")

    ny_m = quick_metrics(all_trades["NY"])
    asia_m = quick_metrics(all_trades["ASIA"])

    # Combined
    merged = sorted(all_trades["NY"] + all_trades["ASIA"], key=lambda t: t["date"])
    comb_m = quick_metrics(merged)

    col_w = 16
    print(f"\n  {'Metric':<20s}{'NY R20':>{col_w}s}{'Asia R9':>{col_w}s}{'Combined':>{col_w}s}")
    print(f"  {'─'*68}")

    rows = [
        ("Trades", f"{ny_m['n']}", f"{asia_m['n']}", f"{comb_m['n']}"),
        ("Win Rate", f"{ny_m['wr']:.1%}", f"{asia_m['wr']:.1%}", f"{comb_m['wr']:.1%}"),
        ("Avg R", f"{ny_m['avg_r']:.3f}", f"{asia_m['avg_r']:.3f}", f"{comb_m['avg_r']:.3f}"),
        ("Net R", f"{ny_m['net_r']:.1f}", f"{asia_m['net_r']:.1f}", f"{comb_m['net_r']:.1f}"),
        ("Max DD (R)", f"{ny_m['max_dd']:.1f}", f"{asia_m['max_dd']:.1f}", f"{comb_m['max_dd']:.1f}"),
        ("Calmar", f"{ny_m['calmar']:.2f}", f"{asia_m['calmar']:.2f}", f"{comb_m['calmar']:.2f}"),
        ("Sharpe", f"{ny_m['sharpe']:.2f}", f"{asia_m['sharpe']:.2f}", f"{comb_m['sharpe']:.2f}"),
        ("Direction", "Both", "Long only", "—"),
        ("ORB Window", "09:30-09:50", "20:00-20:15", "—"),
        ("Entry End", "15:30", "22:30", "—"),
        ("Flat Start", "15:50", "04:00", "—"),
    ]
    for row in rows:
        metric, ny_v, asia_v, comb_v = row
        print(f"  {metric:<20s}{ny_v:>{col_w}s}{asia_v:>{col_w}s}{comb_v:>{col_w}s}")

    # R by year
    ny_yr = r_by_year(all_trades["NY"])
    asia_yr = r_by_year(all_trades["ASIA"])
    comb_yr = r_by_year(merged)
    all_year_keys = sorted(set(ny_yr) | set(asia_yr))

    print(f"\n  R by Year:")
    print(f"  {'Year':<8s}{'NY R20':>{col_w}s}{'Asia R9':>{col_w}s}{'Combined':>{col_w}s}")
    print(f"  {'─'*56}")
    for yr in all_year_keys:
        print(f"  {yr:<8s}{ny_yr.get(yr, 0.0):>+{col_w}.1f}"
              f"{asia_yr.get(yr, 0.0):>+{col_w}.1f}"
              f"{comb_yr.get(yr, 0.0):>+{col_w}.1f}")

    neg_ny = sum(1 for v in ny_yr.values() if v < 0)
    neg_asia = sum(1 for v in asia_yr.values() if v < 0)
    neg_comb = sum(1 for v in comb_yr.values() if v < 0)
    print(f"\n  Negative full years:  NY={neg_ny}  Asia={neg_asia}  Combined={neg_comb}")


# ── SECTION 2 — Trade Date Overlap ───────────────────────────────────────────

def section2_overlap(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 2 — Trade Date Overlap")
    print(f"\n  Note: Asia session at 20:00 ET on date X corresponds to date X")
    print(f"  in trade records. NY on date X is the same calendar day.")
    print(f"  'Same date' means NY traded during the day and Asia traded that evening.\n")

    ny_dates = {t["date"] for t in all_trades["NY"]}
    asia_dates = {t["date"] for t in all_trades["ASIA"]}
    overlap = sorted(ny_dates & asia_dates)
    ny_only = ny_dates - asia_dates
    asia_only = asia_dates - ny_dates
    all_dates = ny_dates | asia_dates

    print(f"  Overall:")
    print(f"    NY active dates:     {len(ny_dates)}")
    print(f"    Asia active dates:   {len(asia_dates)}")
    print(f"    Both fire same day:  {len(overlap)}  "
          f"({len(overlap)/len(all_dates)*100:.1f}% of all active dates)")
    print(f"    NY only:             {len(ny_only)}")
    print(f"    Asia only:           {len(asia_only)}")

    # By year
    years = sorted(set(d[:4] for d in all_dates))
    col_w = 10
    print(f"\n  {'Year':<6s}{'NY':>{col_w}s}{'Asia':>{col_w}s}{'Both':>{col_w}s}"
          f"{'Overlap%':>{col_w}s}")
    print(f"  {'─'*46}")
    for yr in years:
        ny_yr = sum(1 for d in ny_dates if d[:4] == yr)
        asia_yr = sum(1 for d in asia_dates if d[:4] == yr)
        both_yr = sum(1 for d in overlap if d[:4] == yr)
        active_yr = sum(1 for d in all_dates if d[:4] == yr)
        pct = both_yr / active_yr * 100 if active_yr else 0
        print(f"  {yr:<6s}{ny_yr:>{col_w}d}{asia_yr:>{col_w}d}"
              f"{both_yr:>{col_w}d}{pct:>{col_w}.1f}%")


# ── SECTION 3 — Daily R Correlation ──────────────────────────────────────────

def section3_daily_corr(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 3 — Daily R Correlation")

    ny_by_date = {t["date"]: t["r_multiple"] for t in all_trades["NY"]}
    asia_by_date = {t["date"]: t["r_multiple"] for t in all_trades["ASIA"]}

    # Concurrent dates only
    concurrent = sorted(set(ny_by_date) & set(asia_by_date))
    if len(concurrent) < 10:
        print(f"\n  Insufficient concurrent dates ({len(concurrent)}) — skipping.")
        return

    ny_r = np.array([ny_by_date[d] for d in concurrent])
    asia_r = np.array([asia_by_date[d] for d in concurrent])
    r_conc, p_conc = pearsonr(ny_r, asia_r)

    print(f"\n  Concurrent dates (both filled): {len(concurrent)}")
    print(f"  Pearson r (concurrent):  {r_conc:+.4f}  (p={p_conc:.4f})")

    # All active dates (0-fill for missing)
    all_dates = sorted(set(ny_by_date) | set(asia_by_date))
    ny_all = np.array([ny_by_date.get(d, 0.0) for d in all_dates])
    asia_all = np.array([asia_by_date.get(d, 0.0) for d in all_dates])
    r_all, p_all = pearsonr(ny_all, asia_all)

    print(f"\n  All active dates (0-fill): {len(all_dates)}")
    print(f"  Pearson r (0-fill):      {r_all:+.4f}  (p={p_all:.4f})")

    # Interpretation
    if abs(r_conc) < 0.10:
        print(f"\n  -> Near-zero daily correlation — sessions are effectively independent day-to-day.")
    elif abs(r_conc) < 0.30:
        print(f"\n  -> Weak daily correlation — some overlap but mostly independent.")
    else:
        print(f"\n  -> Meaningful daily correlation — daily R moves together.")


# ── SECTION 4 — Outcome Crosstab (Win/Loss matrix) ──────────────────────────

def section4_crosstab(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 4 — Outcome Crosstab (Win/Loss Matrix)")

    ny_by_date = {t["date"]: t for t in all_trades["NY"]}
    asia_by_date = {t["date"]: t for t in all_trades["ASIA"]}
    concurrent = sorted(set(ny_by_date) & set(asia_by_date))

    print(f"\n  Concurrent trade dates: {len(concurrent)}")
    if len(concurrent) < 10:
        print("  Insufficient concurrent dates for analysis.")
        return

    outcomes = ["Win", "Loss", "BE"]
    crosstab: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d in concurrent:
        crosstab[trade_outcome(ny_by_date[d])][trade_outcome(asia_by_date[d])] += 1

    col_w = 9
    print(f"\n  Crosstab  NY (rows) x Asia (cols)\n")
    hdr = (f"  {'NY v  Asia ->':18s}"
           + "".join(f"{o:>{col_w}s}" for o in outcomes)
           + f"{'Total':>{col_w}s}")
    print(hdr)
    print(f"  {'─'*54}")
    for ny_out in outcomes:
        row_total = sum(crosstab[ny_out][asia_out] for asia_out in outcomes)
        row = f"  {ny_out:18s}"
        for asia_out in outcomes:
            row += f"{crosstab[ny_out][asia_out]:>{col_w}d}"
        row += f"{row_total:>{col_w}d}"
        print(row)

    col_totals = [sum(crosstab[ny_out][asia_out] for ny_out in outcomes)
                  for asia_out in outcomes]
    grand_total = sum(col_totals)
    print(f"  {'─'*54}")
    total_row = (f"  {'Total':18s}"
                 + "".join(f"{ct:>{col_w}d}" for ct in col_totals)
                 + f"{grand_total:>{col_w}d}")
    print(total_row)

    # Conditional win rates
    print(f"\n  Conditional win rates:")

    # P(Asia wins | unconditional) on overlap days
    asia_wins_total = sum(crosstab[ny_out]["Win"] for ny_out in outcomes)
    uncond_wr = asia_wins_total / grand_total if grand_total else 0.0
    print(f"    P(Asia wins | unconditional):    {uncond_wr:.1%}  "
          f"({asia_wins_total}/{grand_total})")

    # P(Asia wins | NY won/lost)
    for ny_out in ["Win", "Loss"]:
        total_given = sum(crosstab[ny_out][asia_out] for asia_out in outcomes)
        if total_given == 0:
            continue
        asia_win_given = crosstab[ny_out]["Win"]
        print(f"    P(Asia wins | NY {ny_out:5s}):      "
              f"{asia_win_given/total_given:.1%}  ({asia_win_given}/{total_given})")

    # Win-rate delta
    ny_win_n = sum(crosstab["Win"][asia_out] for asia_out in outcomes)
    ny_loss_n = sum(crosstab["Loss"][asia_out] for asia_out in outcomes)
    if ny_win_n > 5 and ny_loss_n > 5:
        asia_wr_given_ny_win = crosstab["Win"]["Win"] / ny_win_n
        asia_wr_given_ny_loss = crosstab["Loss"]["Win"] / ny_loss_n
        diff = asia_wr_given_ny_win - asia_wr_given_ny_loss
        print(f"\n  Win-rate delta (P(Asia wins|NY wins) - P(Asia wins|NY loses)): {diff:+.1%}")
        if abs(diff) < 0.05:
            print(f"  -> INDEPENDENT: Asia outcome is largely independent of NY outcome on same day")
        elif diff > 0.05:
            print(f"  -> POSITIVE CORRELATION: Both tend to win/lose together (concentration risk)")
        else:
            print(f"  -> NEGATIVE CORRELATION: Asia tends to win when NY loses (hedge behavior)")

    # Combined R on concurrent days
    combined_r = np.array([
        ny_by_date[d]["r_multiple"] + asia_by_date[d]["r_multiple"]
        for d in concurrent
    ])
    both_win = int((combined_r > 0).sum())
    both_lose = int((combined_r < 0).sum())
    print(f"\n  Combined daily R on concurrent dates:")
    print(f"    Net positive days:  {both_win}/{len(concurrent)} ({both_win/len(concurrent):.1%})")
    print(f"    Net negative days:  {both_lose}/{len(concurrent)} ({both_lose/len(concurrent):.1%})")
    print(f"    Avg combined R:     {np.mean(combined_r):+.3f}")
    print(f"    Worst combined day: {np.min(combined_r):+.3f}")
    print(f"    Best combined day:  {np.max(combined_r):+.3f}")


# ── SECTION 5 — Drawdown Period Overlap ──────────────────────────────────────

def _find_top_dd_periods(trades: list[dict], n: int = 5) -> list[dict]:
    """Find top N worst drawdown periods from a list of trade dicts.

    Returns list of dicts with keys: start_date, end_date, depth, trades.
    """
    if not trades:
        return []

    sorted_trades = sorted(trades, key=lambda t: t["date"])
    r = np.array([t["r_multiple"] for t in sorted_trades])
    dates = [t["date"] for t in sorted_trades]

    r_eq = np.cumsum(r)
    r_pk = np.maximum.accumulate(r_eq)
    dd = r_eq - r_pk  # negative during drawdowns

    # Find distinct DD periods: each time we reach a new equity high,
    # the previous DD period ends (if any)
    periods = []
    in_dd = False
    dd_start_idx = 0
    dd_trough = 0.0
    dd_trough_idx = 0

    for i in range(len(r_eq)):
        if dd[i] < 0:
            if not in_dd:
                in_dd = True
                dd_start_idx = i
                dd_trough = dd[i]
                dd_trough_idx = i
            elif dd[i] < dd_trough:
                dd_trough = dd[i]
                dd_trough_idx = i
        else:
            if in_dd:
                periods.append({
                    "start_date": dates[dd_start_idx],
                    "end_date": dates[i],
                    "trough_date": dates[dd_trough_idx],
                    "depth": abs(dd_trough),
                    "n_trades": i - dd_start_idx,
                })
                in_dd = False

    # Handle DD that's still ongoing at the end
    if in_dd:
        periods.append({
            "start_date": dates[dd_start_idx],
            "end_date": dates[-1],
            "trough_date": dates[dd_trough_idx],
            "depth": abs(dd_trough),
            "n_trades": len(dates) - dd_start_idx,
        })

    # Sort by depth (worst first), return top N
    periods.sort(key=lambda p: p["depth"], reverse=True)
    return periods[:n]


def _date_ranges_overlap(s1: str, e1: str, s2: str, e2: str) -> bool:
    """Check if two date ranges [s1,e1] and [s2,e2] overlap."""
    return s1 <= e2 and s2 <= e1


def section5_drawdown_overlap(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 5 — Drawdown Period Overlap")

    ny_periods = _find_top_dd_periods(all_trades["NY"])
    asia_periods = _find_top_dd_periods(all_trades["ASIA"])

    # Also compute combined DD periods
    merged = sorted(all_trades["NY"] + all_trades["ASIA"], key=lambda t: t["date"])
    comb_periods = _find_top_dd_periods(merged)

    for label, periods in [("NY R20", ny_periods), ("Asia R9", asia_periods),
                           ("Combined", comb_periods)]:
        print(f"\n  Top 5 Drawdown Periods — {label}:")
        print(f"  {'#':<4s}{'Start':<14s}{'Trough':<14s}{'End':<14s}{'Depth':>8s}{'Trades':>8s}")
        print(f"  {'─'*62}")
        for i, p in enumerate(periods, 1):
            print(f"  {i:<4d}{p['start_date']:<14s}{p['trough_date']:<14s}"
                  f"{p['end_date']:<14s}{p['depth']:>8.1f}{p['n_trades']:>8d}")

    # Check overlap between NY and Asia top DD periods
    print(f"\n  DD Period Overlap Matrix (NY top 5 vs Asia top 5):")
    print(f"  {'':8s}", end="")
    for j in range(len(asia_periods)):
        print(f"{'Asia#' + str(j+1):>10s}", end="")
    print()
    print(f"  {'─'*(8 + 10 * len(asia_periods))}")

    overlap_count = 0
    for i, ny_p in enumerate(ny_periods):
        print(f"  {'NY#' + str(i+1):<8s}", end="")
        for j, asia_p in enumerate(asia_periods):
            overlaps = _date_ranges_overlap(
                ny_p["start_date"], ny_p["end_date"],
                asia_p["start_date"], asia_p["end_date"])
            if overlaps:
                overlap_count += 1
                print(f"{'OVERLAP':>10s}", end="")
            else:
                print(f"{'—':>10s}", end="")
        print()

    total_pairs = len(ny_periods) * len(asia_periods)
    print(f"\n  Overlapping pairs: {overlap_count}/{total_pairs}")
    if overlap_count > total_pairs * 0.5:
        print(f"  -> HIGH OVERLAP: Drawdown periods frequently coincide.")
        print(f"     This explains why combined DD ({comb_periods[0]['depth'] if comb_periods else 0:.1f}R) "
              f"exceeds worst individual leg.")
    elif overlap_count > 0:
        print(f"  -> PARTIAL OVERLAP: Some drawdown periods coincide.")
    else:
        print(f"  -> NO OVERLAP: Drawdown periods are independent (good diversification).")

    # Text timeline of the worst DD period from each
    if ny_periods and asia_periods:
        print(f"\n  Timeline of worst drawdown period from each session:")
        ny_worst = ny_periods[0]
        asia_worst = asia_periods[0]

        # Simple text timeline
        all_dates_str = sorted(set([
            ny_worst["start_date"], ny_worst["end_date"],
            asia_worst["start_date"], asia_worst["end_date"],
        ]))
        earliest = min(all_dates_str)
        latest = max(all_dates_str)

        print(f"    NY worst:   [{ny_worst['start_date']}] ——— "
              f"[{ny_worst['trough_date']} peak -{ny_worst['depth']:.1f}R] ——— "
              f"[{ny_worst['end_date']}]")
        print(f"    Asia worst: [{asia_worst['start_date']}] ——— "
              f"[{asia_worst['trough_date']} peak -{asia_worst['depth']:.1f}R] ——— "
              f"[{asia_worst['end_date']}]")

        if _date_ranges_overlap(ny_worst["start_date"], ny_worst["end_date"],
                                asia_worst["start_date"], asia_worst["end_date"]):
            # Compute overlap range
            o_start = max(ny_worst["start_date"], asia_worst["start_date"])
            o_end = min(ny_worst["end_date"], asia_worst["end_date"])
            print(f"    OVERLAP:    [{o_start}] to [{o_end}]")
        else:
            print(f"    NO OVERLAP between worst DD periods.")


# ── SECTION 6 — Monthly R Correlation ────────────────────────────────────────

def section6_monthly_corr(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 6 — Monthly R Correlation")

    ny_monthly = monthly_r(all_trades["NY"])
    asia_monthly = monthly_r(all_trades["ASIA"])

    all_months = sorted(set(ny_monthly) | set(asia_monthly))
    common_months = sorted(set(ny_monthly) & set(asia_monthly))

    if len(common_months) < 10:
        print(f"\n  Insufficient common months ({len(common_months)}) — skipping.")
        return

    # Correlation on common months
    ny_m = np.array([ny_monthly[m] for m in common_months])
    asia_m = np.array([asia_monthly[m] for m in common_months])
    r_common, p_common = pearsonr(ny_m, asia_m)

    print(f"\n  Common months: {len(common_months)}  "
          f"({common_months[0]} -> {common_months[-1]})")
    print(f"  Pearson r (common months): {r_common:+.4f}  (p={p_common:.4f})")

    # 0-fill for all months
    ny_all = np.array([ny_monthly.get(m, 0.0) for m in all_months])
    asia_all = np.array([asia_monthly.get(m, 0.0) for m in all_months])
    r_all, p_all = pearsonr(ny_all, asia_all)
    print(f"  Pearson r (0-fill):        {r_all:+.4f}  (p={p_all:.4f})")

    # Double-hit months: both negative
    double_hit = [m for m in common_months
                  if ny_monthly[m] < 0 and asia_monthly[m] < 0]
    print(f"\n  Double-hit months (both negative): {len(double_hit)} / {len(common_months)}"
          f" ({len(double_hit)/len(common_months)*100:.1f}%)")
    if double_hit:
        print(f"  {'Month':<10s}{'NY R':>10s}{'Asia R':>10s}{'Combined':>10s}")
        print(f"  {'─'*40}")
        for m in double_hit:
            print(f"  {m:<10s}{ny_monthly[m]:>+10.2f}{asia_monthly[m]:>+10.2f}"
                  f"{ny_monthly[m]+asia_monthly[m]:>+10.2f}")

    # Rolling by year
    years = sorted(set(m[:4] for m in common_months))
    print(f"\n  Rolling yearly monthly-R correlation:")
    col_w = 12
    print(f"  {'Year':<6s}{'Months':>{col_w}s}{'r':>{col_w}s}{'p-value':>{col_w}s}")
    print(f"  {'─'*42}")
    for yr in years:
        yr_months = [m for m in common_months if m[:4] == yr]
        if len(yr_months) < 6:
            print(f"  {yr:<6s}{len(yr_months):>{col_w}d}{'N/A (< 6)':>{col_w+12}s}")
            continue
        ny_yr = np.array([ny_monthly[m] for m in yr_months])
        asia_yr = np.array([asia_monthly[m] for m in yr_months])
        r_yr, p_yr = pearsonr(ny_yr, asia_yr)
        flag = " *" if abs(r_yr) > 0.50 else ""
        print(f"  {yr:<6s}{len(yr_months):>{col_w}d}{r_yr:>+{col_w}.3f}{p_yr:>{col_w}.4f}{flag}")

    print(f"\n  (* = |r| > 0.50 within that year)")


# ── SECTION 7 — Regime Analysis ──────────────────────────────────────────────

def section7_regime_analysis(all_trades: dict[str, list[dict]], df_5m: pd.DataFrame) -> None:
    sep("SECTION 7 — Regime Analysis")

    # ── 7a: ATR regime buckets ────────────────────────────────────────────────
    sep("7a — ATR Regime (High Vol vs Low Vol)")

    # Compute daily ATR mapped to 5m bars
    atr_5m = compute_daily_atr(df_5m, length=14)

    # Build a date -> ATR mapping from 5m data
    atr_series = pd.Series(atr_5m, index=df_5m.index)
    daily_atr = atr_series.resample("1D").first().dropna()

    # Map trade dates to daily ATR
    date_to_atr: dict[str, float] = {}
    for dt, val in daily_atr.items():
        if not np.isnan(val):
            date_to_atr[dt.strftime("%Y-%m-%d")] = float(val)

    # Compute ATR percentiles
    atr_values = np.array(list(date_to_atr.values()))
    if len(atr_values) > 0:
        p20 = float(np.percentile(atr_values, 20))
        p50 = float(np.percentile(atr_values, 50))
        p80 = float(np.percentile(atr_values, 80))

        print(f"\n  Daily ATR percentiles (ATR-14):")
        print(f"    P20={p20:.1f}  P50={p50:.1f}  P80={p80:.1f}")

        # Bucket trades by ATR regime
        buckets = [
            ("Low (P0-P20)", 0, p20),
            ("Below-Avg (P20-P50)", p20, p50),
            ("Above-Avg (P50-P80)", p50, p80),
            ("High (P80-P100)", p80, float("inf")),
        ]

        col_w = 12
        print(f"\n  {'Regime':<22s}{'':4s}{'NY n':>{col_w}s}{'NY Avg R':>{col_w}s}"
              f"{'Asia n':>{col_w}s}{'Asia Avg R':>{col_w}s}"
              f"{'Comb Avg R':>{col_w}s}")
        print(f"  {'─'*84}")

        for label, lo, hi in buckets:
            ny_bucket = [t for t in all_trades["NY"]
                         if t["date"] in date_to_atr
                         and lo <= date_to_atr[t["date"]] < hi]
            asia_bucket = [t for t in all_trades["ASIA"]
                           if t["date"] in date_to_atr
                           and lo <= date_to_atr[t["date"]] < hi]
            combined_bucket = ny_bucket + asia_bucket

            ny_m = quick_metrics(ny_bucket) if ny_bucket else {"n": 0, "avg_r": 0.0}
            asia_m = quick_metrics(asia_bucket) if asia_bucket else {"n": 0, "avg_r": 0.0}
            comb_m = quick_metrics(combined_bucket) if combined_bucket else {"avg_r": 0.0}

            print(f"  {label:<22s}{'':4s}{ny_m['n']:>{col_w}d}{ny_m['avg_r']:>+{col_w}.3f}"
                  f"{asia_m['n']:>{col_w}d}{asia_m['avg_r']:>+{col_w}.3f}"
                  f"{comb_m['avg_r']:>+{col_w}.3f}")

        # Check if both underperform in high vol
        ny_high = [t for t in all_trades["NY"]
                   if t["date"] in date_to_atr and date_to_atr[t["date"]] >= p80]
        asia_high = [t for t in all_trades["ASIA"]
                     if t["date"] in date_to_atr and date_to_atr[t["date"]] >= p80]
        ny_low = [t for t in all_trades["NY"]
                  if t["date"] in date_to_atr and date_to_atr[t["date"]] < p50]
        asia_low = [t for t in all_trades["ASIA"]
                    if t["date"] in date_to_atr and date_to_atr[t["date"]] < p50]

        ny_high_m = quick_metrics(ny_high) if ny_high else {"avg_r": 0.0}
        ny_low_m = quick_metrics(ny_low) if ny_low else {"avg_r": 0.0}
        asia_high_m = quick_metrics(asia_high) if asia_high else {"avg_r": 0.0}
        asia_low_m = quick_metrics(asia_low) if asia_low else {"avg_r": 0.0}

        print(f"\n  High-vol penalty:")
        print(f"    NY:   high-vol avg R = {ny_high_m['avg_r']:+.3f}  "
              f"vs low-vol avg R = {ny_low_m['avg_r']:+.3f}  "
              f"(delta = {ny_high_m['avg_r'] - ny_low_m['avg_r']:+.3f})")
        print(f"    Asia: high-vol avg R = {asia_high_m['avg_r']:+.3f}  "
              f"vs low-vol avg R = {asia_low_m['avg_r']:+.3f}  "
              f"(delta = {asia_high_m['avg_r'] - asia_low_m['avg_r']:+.3f})")

        if ny_high_m["avg_r"] < ny_low_m["avg_r"] and asia_high_m["avg_r"] < asia_low_m["avg_r"]:
            print(f"    -> Both sessions underperform in high-vol: shared regime vulnerability")
        else:
            print(f"    -> Mixed: sessions respond differently to volatility regimes")

    # ── 7b: Yearly performance buckets ────────────────────────────────────────
    sep("7b — Yearly Performance Buckets")

    ny_yr = r_by_year(all_trades["NY"])
    asia_yr = r_by_year(all_trades["ASIA"])
    common_years = sorted(set(ny_yr) & set(asia_yr))

    if common_years:
        print(f"\n  {'Year':<8s}{'NY R':>10s}{'Asia R':>10s}{'NY rank':>10s}{'Asia rank':>10s}")
        print(f"  {'─'*48}")

        # Rank years by performance
        ny_sorted = sorted(common_years, key=lambda y: ny_yr[y])
        asia_sorted = sorted(common_years, key=lambda y: asia_yr[y])
        ny_rank = {y: i + 1 for i, y in enumerate(ny_sorted)}
        asia_rank = {y: i + 1 for i, y in enumerate(asia_sorted)}

        for yr in common_years:
            flag = " **" if ny_rank[yr] <= 3 and asia_rank[yr] <= 3 else ""
            print(f"  {yr:<8s}{ny_yr[yr]:>+10.1f}{asia_yr[yr]:>+10.1f}"
                  f"{ny_rank[yr]:>10d}{asia_rank[yr]:>10d}{flag}")

        # Rank correlation
        ny_ranks = np.array([ny_rank[y] for y in common_years], dtype=float)
        asia_ranks = np.array([asia_rank[y] for y in common_years], dtype=float)
        rank_r, rank_p = pearsonr(ny_ranks, asia_ranks)
        print(f"\n  Rank correlation (Pearson on ranks): {rank_r:+.3f} (p={rank_p:.4f})")
        print(f"  (** = year ranked in bottom 3 for BOTH sessions)")

        if rank_r > 0.50:
            print(f"  -> Strong positive rank correlation: bad years tend to be bad for both.")
        elif rank_r > 0.20:
            print(f"  -> Moderate rank correlation: some tendency to co-move across years.")
        else:
            print(f"  -> Weak rank correlation: yearly performance is largely independent.")


# ── SECTION 8 — Gating Ideas ────────────────────────────────────────────────

def section8_gating(all_trades: dict[str, list[dict]], df_5m: pd.DataFrame) -> None:
    sep("SECTION 8 — Gating Ideas")

    ny_trades = all_trades["NY"]
    asia_trades = all_trades["ASIA"]

    # Build lookup structures
    ny_by_date = {t["date"]: t for t in ny_trades}
    asia_by_date = {t["date"]: t for t in asia_trades}

    # Baseline (ungated)
    baseline_trades = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
    baseline_m = quick_metrics(baseline_trades)

    print(f"\n  BASELINE (ungated):")
    print(f"    Trades: {baseline_m['n']}  Net R: {baseline_m['net_r']:.1f}  "
          f"DD: {baseline_m['max_dd']:.1f}  Calmar: {baseline_m['calmar']:.2f}  "
          f"Sharpe: {baseline_m['sharpe']:.2f}")

    gate_results: list[tuple[str, str, dict]] = [
        ("Baseline", "No gating", baseline_m)
    ]
    gate_trade_lists: dict[str, list[dict]] = {"Baseline": baseline_trades}

    # ── Gate A: Skip Asia after NY loss (same day) ────────────────────────────
    sep("Gate A — Skip Asia after NY loss (same day)")
    print(f"\n  Logic: If NY lost on date X, skip Asia that evening (date X).")
    print(f"  No look-ahead: NY completes by 15:50, Asia opens at 20:00.\n")

    gate_a_asia = []
    skipped_a = 0
    for t in asia_trades:
        d = t["date"]
        if d in ny_by_date and ny_by_date[d]["r_multiple"] < 0:
            skipped_a += 1
            continue
        gate_a_asia.append(t)

    gate_a_trades = sorted(ny_trades + gate_a_asia, key=lambda t: t["date"])
    gate_a_m = quick_metrics(gate_a_trades)
    gate_results.append(("A", "Skip Asia after NY loss", gate_a_m))
    gate_trade_lists["A"] = gate_a_trades

    print(f"  Asia trades skipped: {skipped_a}")
    print(f"  Remaining: {gate_a_m['n']} trades  Net R: {gate_a_m['net_r']:.1f}  "
          f"DD: {gate_a_m['max_dd']:.1f}  Calmar: {gate_a_m['calmar']:.2f}")

    # ── Gate B: Skip Asia after NY loss streak (2+) ──────────────────────────
    sep("Gate B — Skip Asia after NY loss streak (2+ consecutive)")
    print(f"\n  Logic: Only gate Asia after NY lost 2+ in a row.\n")

    # Build NY loss streak tracker
    ny_sorted = sorted(ny_trades, key=lambda t: t["date"])
    ny_streak: dict[str, int] = {}  # date -> consecutive loss count ending this date
    streak_count = 0
    for t in ny_sorted:
        if t["r_multiple"] < 0:
            streak_count += 1
        else:
            streak_count = 0
        ny_streak[t["date"]] = streak_count

    gate_b_asia = []
    skipped_b = 0
    for t in asia_trades:
        d = t["date"]
        if d in ny_streak and ny_streak[d] >= 2:
            skipped_b += 1
            continue
        gate_b_asia.append(t)

    gate_b_trades = sorted(ny_trades + gate_b_asia, key=lambda t: t["date"])
    gate_b_m = quick_metrics(gate_b_trades)
    gate_results.append(("B", "Skip Asia after 2+ NY losses", gate_b_m))
    gate_trade_lists["B"] = gate_b_trades

    print(f"  Asia trades skipped: {skipped_b}")
    print(f"  Remaining: {gate_b_m['n']} trades  Net R: {gate_b_m['net_r']:.1f}  "
          f"DD: {gate_b_m['max_dd']:.1f}  Calmar: {gate_b_m['calmar']:.2f}")

    # ── Gate C: Skip NY after Asia loss (prior evening) ──────────────────────
    sep("Gate C — Skip NY after Asia loss (prior evening)")
    print(f"\n  Logic: If Asia lost on date X evening, skip NY on date X+1 morning.")
    print(f"  Reverse causality test.\n")

    # Build Asia date -> next trading date mapping
    asia_dates_sorted = sorted(asia_by_date.keys())
    asia_loss_dates = {t["date"] for t in asia_trades if t["r_multiple"] < 0}

    # For each NY trade, check if Asia lost the prior day
    ny_dates_sorted = sorted(ny_by_date.keys())
    # Build a mapping: for each NY date, find the most recent Asia date before it
    gate_c_ny = []
    skipped_c = 0
    for t in ny_trades:
        d = t["date"]
        # Find the previous calendar day (or closest Asia trading day before)
        prev_day = None
        d_dt = datetime.strptime(d, "%Y-%m-%d")
        # Check up to 5 days back (handles weekends)
        for offset in range(1, 6):
            candidate = (d_dt - pd.Timedelta(days=offset)).strftime("%Y-%m-%d")
            if candidate in asia_by_date:
                prev_day = candidate
                break

        if prev_day and prev_day in asia_loss_dates:
            skipped_c += 1
            continue
        gate_c_ny.append(t)

    gate_c_trades = sorted(gate_c_ny + asia_trades, key=lambda t: t["date"])
    gate_c_m = quick_metrics(gate_c_trades)
    gate_results.append(("C", "Skip NY after Asia loss (prior eve)", gate_c_m))
    gate_trade_lists["C"] = gate_c_trades

    print(f"  NY trades skipped: {skipped_c}")
    print(f"  Remaining: {gate_c_m['n']} trades  Net R: {gate_c_m['net_r']:.1f}  "
          f"DD: {gate_c_m['max_dd']:.1f}  Calmar: {gate_c_m['calmar']:.2f}")

    # ── Gate D: Weekly loss cap ──────────────────────────────────────────────
    sep("Gate D — Weekly Loss Cap")
    print(f"\n  Logic: If combined weekly R drops below -X, skip rest of week.\n")

    # Test multiple cap levels
    cap_levels = [2.0, 3.0, 4.0, 5.0]

    col_w = 12
    print(f"  {'Cap':>6s}{'Trades':>{col_w}s}{'Skipped':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}")
    print(f"  {'─'*78}")

    best_d_calmar = 0.0
    best_d_cap = 0.0
    best_d_m = baseline_m
    best_d_trades: list[dict] = baseline_trades

    for cap in cap_levels:
        all_sorted = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
        weekly_r: dict[str, float] = {}
        halted_weeks: set[str] = set()

        kept = []
        skipped_count = 0
        for t in all_sorted:
            wk = weekly_key(t["date"])
            if wk in halted_weeks:
                skipped_count += 1
                continue
            kept.append(t)
            weekly_r[wk] = weekly_r.get(wk, 0.0) + t["r_multiple"]
            if weekly_r[wk] <= -cap:
                halted_weeks.add(wk)

        m = quick_metrics(kept)
        marker = " <-" if m["calmar"] > best_d_calmar else ""
        if m["calmar"] > best_d_calmar:
            best_d_calmar = m["calmar"]
            best_d_cap = cap
            best_d_m = m
            best_d_trades = kept
        print(f"  {cap:>5.1f}R{m['n']:>{col_w}d}{skipped_count:>{col_w}d}"
              f"{m['net_r']:>{col_w}.1f}{m['max_dd']:>{col_w}.1f}"
              f"{m['calmar']:>{col_w}.2f}{m['sharpe']:>{col_w}.2f}{marker}")

    gate_results.append(("D", f"Weekly cap -{best_d_cap:.0f}R", best_d_m))
    gate_trade_lists["D"] = best_d_trades

    # ── Gate E: Mutual cooldown ──────────────────────────────────────────────
    sep("Gate E — Mutual Cooldown")
    print(f"\n  Logic: If EITHER session loses, skip the NEXT trade from EITHER session.")
    print(f"  Tests whether losses cluster in bursts.\n")

    all_sorted = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
    gate_e_kept = []
    skip_next = False
    skipped_e = 0
    for t in all_sorted:
        if skip_next:
            skipped_e += 1
            skip_next = False
            # Check if this skipped trade was also a loss — if so, would have
            # triggered another skip. But we already skipped it, so the chain breaks.
            continue
        gate_e_kept.append(t)
        if t["r_multiple"] < 0:
            skip_next = True

    gate_e_m = quick_metrics(gate_e_kept)
    gate_results.append(("E", "Mutual cooldown (1 trade)", gate_e_m))
    gate_trade_lists["E"] = gate_e_kept

    print(f"  Trades skipped: {skipped_e}")
    print(f"  Remaining: {gate_e_m['n']} trades  Net R: {gate_e_m['net_r']:.1f}  "
          f"DD: {gate_e_m['max_dd']:.1f}  Calmar: {gate_e_m['calmar']:.2f}")

    # ── Gate F: ATR-based skip (high vol day, skip Asia) ─────────────────────
    sep("Gate F — ATR-Based Skip (High Vol -> Skip Asia)")
    print(f"\n  Logic: If daily ATR is above 80th percentile, skip Asia that evening.")
    print(f"  High vol may cause both sessions to whipsaw.\n")

    atr_5m = compute_daily_atr(df_5m, length=14)
    atr_series = pd.Series(atr_5m, index=df_5m.index)
    daily_atr = atr_series.resample("1D").first().dropna()

    date_to_atr: dict[str, float] = {}
    for dt, val in daily_atr.items():
        if not np.isnan(val):
            date_to_atr[dt.strftime("%Y-%m-%d")] = float(val)

    atr_values = np.array(list(date_to_atr.values()))

    # Test multiple percentile thresholds
    pct_levels = [70, 75, 80, 85, 90]

    col_w = 12
    print(f"  {'Pctile':>8s}{'Trades':>{col_w}s}{'Skipped':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}")
    print(f"  {'─'*80}")

    best_f_calmar = 0.0
    best_f_pct = 80
    best_f_m = baseline_m
    best_f_trades: list[dict] = baseline_trades

    for pct in pct_levels:
        threshold = float(np.percentile(atr_values, pct))
        gate_f_asia = []
        skipped_f = 0
        for t in asia_trades:
            d = t["date"]
            if d in date_to_atr and date_to_atr[d] >= threshold:
                skipped_f += 1
                continue
            gate_f_asia.append(t)

        gate_f_trades = sorted(ny_trades + gate_f_asia, key=lambda t: t["date"])
        m = quick_metrics(gate_f_trades)
        marker = " <-" if m["calmar"] > best_f_calmar else ""
        if m["calmar"] > best_f_calmar:
            best_f_calmar = m["calmar"]
            best_f_pct = pct
            best_f_m = m
            best_f_trades = gate_f_trades
        print(f"  P{pct:>3d}{' ':>4s}{m['n']:>{col_w}d}{skipped_f:>{col_w}d}"
              f"{m['net_r']:>{col_w}.1f}{m['max_dd']:>{col_w}.1f}"
              f"{m['calmar']:>{col_w}.2f}{m['sharpe']:>{col_w}.2f}{marker}")

    gate_results.append(("F", f"Skip Asia when ATR > P{best_f_pct}", best_f_m))
    gate_trade_lists["F"] = best_f_trades

    # ── Gate G: Stack D + C (weekly cap + skip NY after Asia loss) ────────────
    sep("Gate G — Stack: Weekly Cap + Skip NY after Asia Loss")
    print(f"\n  Logic: Combine best weekly cap (-{best_d_cap:.0f}R) with Gate C logic.")
    print(f"  Both are independent mechanisms that reduced DD.\n")

    # Start with Gate C filtered NY trades, then apply weekly cap
    gate_g_all = sorted(gate_c_ny + asia_trades, key=lambda t: t["date"])
    weekly_r_g: dict[str, float] = {}
    halted_weeks_g: set[str] = set()
    gate_g_kept = []
    skipped_g = 0
    for t in gate_g_all:
        wk = weekly_key(t["date"])
        if wk in halted_weeks_g:
            skipped_g += 1
            continue
        gate_g_kept.append(t)
        weekly_r_g[wk] = weekly_r_g.get(wk, 0.0) + t["r_multiple"]
        if weekly_r_g[wk] <= -best_d_cap:
            halted_weeks_g.add(wk)

    gate_g_m = quick_metrics(gate_g_kept)
    gate_results.append(("G", f"Stack: Weekly -{best_d_cap:.0f}R + skip NY after Asia loss", gate_g_m))
    gate_trade_lists["G"] = gate_g_kept

    print(f"  Trades removed (C filter): {skipped_c}")
    print(f"  Trades removed (weekly cap): {skipped_g}")
    print(f"  Remaining: {gate_g_m['n']} trades  Net R: {gate_g_m['net_r']:.1f}  "
          f"DD: {gate_g_m['max_dd']:.1f}  Calmar: {gate_g_m['calmar']:.2f}")

    # ── Gate H: Equity curve filter ──────────────────────────────────────────
    sep("Gate H — Equity Curve Filter")
    print(f"\n  Logic: Only trade when rolling equity (last N trades) is above its")
    print(f"  moving average. Pause during equity dips.\n")

    ma_lengths = [20, 30, 50, 75, 100]

    col_w = 12
    print(f"  {'MA len':>8s}{'Trades':>{col_w}s}{'Skipped':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}")
    print(f"  {'─'*80}")

    best_h_calmar = 0.0
    best_h_ma = 50
    best_h_m = baseline_m
    best_h_trades: list[dict] = baseline_trades

    for ma_len in ma_lengths:
        all_sorted_h = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
        # Build equity curve and its MA
        eq_values: list[float] = []
        cumulative = 0.0
        for t in all_sorted_h:
            cumulative += t["r_multiple"]
            eq_values.append(cumulative)

        eq_arr = np.array(eq_values)
        # Simple moving average of equity curve
        eq_ma = np.full(len(eq_arr), np.nan)
        for i in range(ma_len - 1, len(eq_arr)):
            eq_ma[i] = np.mean(eq_arr[max(0, i - ma_len + 1):i + 1])

        # Now re-iterate: take trade only if equity BEFORE this trade is above MA
        # Use the equity and MA from the PREVIOUS trade (no look-ahead)
        kept_h = []
        skipped_h = 0
        for i, t in enumerate(all_sorted_h):
            if i == 0:
                # Always take the first trade
                kept_h.append(t)
                continue
            prev_eq = eq_values[i - 1]
            prev_ma = eq_ma[i - 1]
            if np.isnan(prev_ma) or prev_eq >= prev_ma:
                kept_h.append(t)
            else:
                skipped_h += 1

        m = quick_metrics(kept_h)
        marker = " <-" if m["calmar"] > best_h_calmar else ""
        if m["calmar"] > best_h_calmar:
            best_h_calmar = m["calmar"]
            best_h_ma = ma_len
            best_h_m = m
            best_h_trades = kept_h
        print(f"  {ma_len:>6d}{' ':>2s}{m['n']:>{col_w}d}{skipped_h:>{col_w}d}"
              f"{m['net_r']:>{col_w}.1f}{m['max_dd']:>{col_w}.1f}"
              f"{m['calmar']:>{col_w}.2f}{m['sharpe']:>{col_w}.2f}{marker}")

    gate_results.append(("H", f"Equity curve MA({best_h_ma})", best_h_m))
    gate_trade_lists["H"] = best_h_trades

    # ── Gate I: Monthly loss cap ─────────────────────────────────────────────
    sep("Gate I — Monthly Loss Cap")
    print(f"\n  Logic: If combined monthly R drops below -X, skip rest of month.\n")

    monthly_caps = [3.0, 4.0, 5.0, 6.0, 8.0]

    col_w = 12
    print(f"  {'Cap':>6s}{'Trades':>{col_w}s}{'Skipped':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}")
    print(f"  {'─'*78}")

    best_i_calmar = 0.0
    best_i_cap = 5.0
    best_i_m = baseline_m
    best_i_trades: list[dict] = baseline_trades

    for cap in monthly_caps:
        all_sorted_i = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
        month_r: dict[str, float] = {}
        halted_months: set[str] = set()

        kept_i = []
        skipped_count_i = 0
        for t in all_sorted_i:
            month = t["date"][:7]
            if month in halted_months:
                skipped_count_i += 1
                continue
            kept_i.append(t)
            month_r[month] = month_r.get(month, 0.0) + t["r_multiple"]
            if month_r[month] <= -cap:
                halted_months.add(month)

        m = quick_metrics(kept_i)
        marker = " <-" if m["calmar"] > best_i_calmar else ""
        if m["calmar"] > best_i_calmar:
            best_i_calmar = m["calmar"]
            best_i_cap = cap
            best_i_m = m
            best_i_trades = kept_i
        print(f"  {cap:>5.1f}R{m['n']:>{col_w}d}{skipped_count_i:>{col_w}d}"
              f"{m['net_r']:>{col_w}.1f}{m['max_dd']:>{col_w}.1f}"
              f"{m['calmar']:>{col_w}.2f}{m['sharpe']:>{col_w}.2f}{marker}")

    gate_results.append(("I", f"Monthly cap -{best_i_cap:.0f}R", best_i_m))
    gate_trade_lists["I"] = best_i_trades

    # ── Gate J: Max consecutive combined losses ──────────────────────────────
    sep("Gate J — Consecutive Loss Streak Pause")
    print(f"\n  Logic: After N consecutive losses across both sessions, skip next")
    print(f"  1-2 trades. Unlike mutual cooldown (E), only triggers after a streak.\n")

    streak_thresholds = [3, 4, 5]
    pause_lengths = [1, 2]

    col_w = 12
    print(f"  {'Streak':>8s}{'Pause':>8s}{'Trades':>{col_w}s}{'Skipped':>{col_w}s}"
          f"{'Net R':>{col_w}s}{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}")
    print(f"  {'─'*92}")

    best_j_calmar = 0.0
    best_j_streak = 4
    best_j_pause = 1
    best_j_m = baseline_m
    best_j_trades: list[dict] = baseline_trades

    for streak_thresh in streak_thresholds:
        for pause_len in pause_lengths:
            all_sorted_j = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
            kept_j = []
            skipped_j = 0
            consec_losses = 0
            pause_remaining = 0

            for t in all_sorted_j:
                if pause_remaining > 0:
                    skipped_j += 1
                    pause_remaining -= 1
                    continue
                kept_j.append(t)
                if t["r_multiple"] < 0:
                    consec_losses += 1
                    if consec_losses >= streak_thresh:
                        pause_remaining = pause_len
                        consec_losses = 0  # reset after triggering
                else:
                    consec_losses = 0

            m = quick_metrics(kept_j)
            marker = " <-" if m["calmar"] > best_j_calmar else ""
            if m["calmar"] > best_j_calmar:
                best_j_calmar = m["calmar"]
                best_j_streak = streak_thresh
                best_j_pause = pause_len
                best_j_m = m
                best_j_trades = kept_j
            print(f"  {streak_thresh:>6d}L{' ':>1s}{pause_len:>5d}T{' ':>1s}"
                  f"{m['n']:>{col_w}d}{skipped_j:>{col_w}d}"
                  f"{m['net_r']:>{col_w}.1f}{m['max_dd']:>{col_w}.1f}"
                  f"{m['calmar']:>{col_w}.2f}{m['sharpe']:>{col_w}.2f}{marker}")

    gate_results.append(("J", f"Pause {best_j_pause}T after {best_j_streak} consec losses", best_j_m))
    gate_trade_lists["J"] = best_j_trades

    # ── Gate K: Overlap day half-sizing ──────────────────────────────────────
    sep("Gate K — Overlap Day Half-Sizing")
    print(f"\n  Logic: On days both sessions fire, reduce each to 0.5x risk.")
    print(f"  Caps daily exposure to 1R instead of 2R on overlap days.\n")

    ny_date_set = {t["date"] for t in ny_trades}
    asia_date_set = {t["date"] for t in asia_trades}
    overlap_dates = ny_date_set & asia_date_set

    scale_levels = [0.25, 0.33, 0.5, 0.67, 0.75]

    col_w = 12
    print(f"  Overlap dates: {len(overlap_dates)}\n")
    print(f"  {'Scale':>8s}{'Trades':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}")
    print(f"  {'─'*68}")

    best_k_calmar = 0.0
    best_k_scale = 0.5
    best_k_m = baseline_m
    best_k_trades: list[dict] = baseline_trades

    for scale in scale_levels:
        scaled_trades = []
        for t in ny_trades + asia_trades:
            new_t = dict(t)
            if t["date"] in overlap_dates:
                new_t["r_multiple"] = t["r_multiple"] * scale
            scaled_trades.append(new_t)
        scaled_trades.sort(key=lambda x: x["date"])

        m = quick_metrics(scaled_trades)
        marker = " <-" if m["calmar"] > best_k_calmar else ""
        if m["calmar"] > best_k_calmar:
            best_k_calmar = m["calmar"]
            best_k_scale = scale
            best_k_m = m
            best_k_trades = scaled_trades
        print(f"  {scale:>6.2f}x{' ':>1s}{m['n']:>{col_w}d}{m['net_r']:>{col_w}.1f}"
              f"{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}"
              f"{m['sharpe']:>{col_w}.2f}{marker}")

    gate_results.append(("K", f"Overlap day {best_k_scale:.2f}x sizing", best_k_m))
    gate_trade_lists["K"] = best_k_trades

    # ── Gate L: Rolling DD throttle ──────────────────────────────────────────
    sep("Gate L — Rolling DD Throttle")
    print(f"\n  Logic: When current DD exceeds threshold, scale to 0.5x until recovery.")
    print(f"  Adaptive — reduces exposure during deep drawdowns.\n")

    dd_thresholds = [6.0, 8.0, 10.0, 12.0, 15.0]
    recovery_offsets = [5.0]  # recover when DD improves by this much from threshold

    col_w = 12
    print(f"  {'DD thr':>8s}{'Recov':>8s}{'Trades':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}{'Bars @0.5x':>{col_w}s}")
    print(f"  {'─'*92}")

    best_l_calmar = 0.0
    best_l_thr = 10.0
    best_l_m = baseline_m
    best_l_trades: list[dict] = baseline_trades

    for dd_thr in dd_thresholds:
        for recov in recovery_offsets:
            all_sorted_l = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
            kept_l = []
            cumulative_r = 0.0
            peak_r = 0.0
            throttled_count = 0

            for t in all_sorted_l:
                current_dd = peak_r - cumulative_r  # positive number

                new_t = dict(t)
                if current_dd >= dd_thr:
                    new_t["r_multiple"] = t["r_multiple"] * 0.5
                    throttled_count += 1
                kept_l.append(new_t)

                cumulative_r += new_t["r_multiple"]
                peak_r = max(peak_r, cumulative_r)

            m = quick_metrics(kept_l)
            marker = " <-" if m["calmar"] > best_l_calmar else ""
            if m["calmar"] > best_l_calmar:
                best_l_calmar = m["calmar"]
                best_l_thr = dd_thr
                best_l_m = m
                best_l_trades = kept_l
            print(f"  {dd_thr:>6.0f}R{' ':>1s}{recov:>5.0f}R{' ':>2s}"
                  f"{m['n']:>{col_w}d}{m['net_r']:>{col_w}.1f}"
                  f"{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}"
                  f"{m['sharpe']:>{col_w}.2f}{throttled_count:>{col_w}d}{marker}")

    gate_results.append(("L", f"DD throttle 0.5x when DD > {best_l_thr:.0f}R", best_l_m))
    gate_trade_lists["L"] = best_l_trades

    # ── Gate M: Fine-tune weekly cap (Gate D) ────────────────────────────────
    sep("Gate M — Fine-Tune Weekly Cap")
    print(f"\n  Logic: Sweep weekly cap at 0.5R resolution around best value ({best_d_cap:.0f}R).\n")

    fine_caps = [round(best_d_cap - 1.5 + i * 0.5, 1) for i in range(7)]
    # Ensure all are positive
    fine_caps = [c for c in fine_caps if c > 0]

    col_w = 12
    print(f"  {'Cap':>6s}{'Trades':>{col_w}s}{'Skipped':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}")
    print(f"  {'─'*78}")

    best_m_calmar = 0.0
    best_m_cap = best_d_cap
    best_m_m = baseline_m
    best_m_trades: list[dict] = baseline_trades

    for cap in fine_caps:
        all_sorted_m = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
        weekly_r_m: dict[str, float] = {}
        halted_weeks_m: set[str] = set()

        kept_m = []
        skipped_m = 0
        for t in all_sorted_m:
            wk = weekly_key(t["date"])
            if wk in halted_weeks_m:
                skipped_m += 1
                continue
            kept_m.append(t)
            weekly_r_m[wk] = weekly_r_m.get(wk, 0.0) + t["r_multiple"]
            if weekly_r_m[wk] <= -cap:
                halted_weeks_m.add(wk)

        m = quick_metrics(kept_m)
        marker = " <-" if m["calmar"] > best_m_calmar else ""
        if m["calmar"] > best_m_calmar:
            best_m_calmar = m["calmar"]
            best_m_cap = cap
            best_m_m = m
            best_m_trades = kept_m
        print(f"  {cap:>5.1f}R{m['n']:>{col_w}d}{skipped_m:>{col_w}d}"
              f"{m['net_r']:>{col_w}.1f}{m['max_dd']:>{col_w}.1f}"
              f"{m['calmar']:>{col_w}.2f}{m['sharpe']:>{col_w}.2f}{marker}")

    gate_results.append(("M", f"Weekly cap -{best_m_cap:.1f}R (fine-tuned)", best_m_m))
    gate_trade_lists["M"] = best_m_trades

    print(f"\n  Best fine-tuned cap: -{best_m_cap:.1f}R  Calmar: {best_m_calmar:.2f}")

    # Show R by year for fine-tuned D
    best_m_yr = r_by_year(best_m_trades)
    baseline_yr_m = r_by_year(baseline_trades)
    all_year_keys_m = sorted(set(baseline_yr_m) | set(best_m_yr))
    print(f"\n  R by Year (fine-tuned weekly cap -{best_m_cap:.1f}R):")
    print(f"  {'Year':<8s}{'Baseline':>12s}{'Gated':>12s}{'Delta':>12s}")
    print(f"  {'─'*44}")
    neg_count_m = 0
    for yr in all_year_keys_m:
        b = baseline_yr_m.get(yr, 0.0)
        g = best_m_yr.get(yr, 0.0)
        flag = " *" if g < 0 else ""
        if g < 0:
            neg_count_m += 1
        print(f"  {yr:<8s}{b:>+12.1f}{g:>+12.1f}{g - b:>+12.1f}{flag}")
    print(f"\n  Negative full years: {neg_count_m}")

    # ── Gate N: Stack D + L (weekly cap + DD throttle) ───────────────────────
    sep("Gate N — Stack: Weekly Cap + DD Throttle")
    print(f"\n  Logic: Apply weekly cap (-{best_m_cap:.1f}R) first, then DD throttle")
    print(f"  (0.5x when DD > {best_l_thr:.0f}R). Weekly cap prevents cascade weeks,")
    print(f"  DD throttle dampens prolonged drawdowns.\n")

    # Sweep DD thresholds with the best weekly cap applied first
    dl_dd_thresholds = [6.0, 8.0, 10.0, 12.0, 15.0]

    col_w = 12
    print(f"  Weekly cap: -{best_m_cap:.1f}R (fixed)\n")
    print(f"  {'DD thr':>8s}{'Trades':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}{'@0.5x':>{col_w}s}")
    print(f"  {'─'*80}")

    best_n_calmar = 0.0
    best_n_thr = 10.0
    best_n_m = baseline_m
    best_n_trades: list[dict] = baseline_trades

    for dd_thr in dl_dd_thresholds:
        # First: apply weekly cap
        all_sorted_n = sorted(ny_trades + asia_trades, key=lambda t: t["date"])
        weekly_r_n: dict[str, float] = {}
        halted_weeks_n: set[str] = set()
        after_weekly: list[dict] = []

        for t in all_sorted_n:
            wk = weekly_key(t["date"])
            if wk in halted_weeks_n:
                continue
            after_weekly.append(t)
            weekly_r_n[wk] = weekly_r_n.get(wk, 0.0) + t["r_multiple"]
            if weekly_r_n[wk] <= -best_m_cap:
                halted_weeks_n.add(wk)

        # Then: apply DD throttle on remaining trades
        kept_n = []
        cumulative_r_n = 0.0
        peak_r_n = 0.0
        throttled_n = 0

        for t in after_weekly:
            current_dd = peak_r_n - cumulative_r_n

            new_t = dict(t)
            if current_dd >= dd_thr:
                new_t["r_multiple"] = t["r_multiple"] * 0.5
                throttled_n += 1
            kept_n.append(new_t)

            cumulative_r_n += new_t["r_multiple"]
            peak_r_n = max(peak_r_n, cumulative_r_n)

        m = quick_metrics(kept_n)
        marker = " <-" if m["calmar"] > best_n_calmar else ""
        if m["calmar"] > best_n_calmar:
            best_n_calmar = m["calmar"]
            best_n_thr = dd_thr
            best_n_m = m
            best_n_trades = kept_n
        print(f"  {dd_thr:>6.0f}R{' ':>1s}{m['n']:>{col_w}d}{m['net_r']:>{col_w}.1f}"
              f"{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}"
              f"{m['sharpe']:>{col_w}.2f}{throttled_n:>{col_w}d}{marker}")

    gate_results.append(("N", f"Stack: Weekly -{best_m_cap:.1f}R + DD throttle >{best_n_thr:.0f}R", best_n_m))
    gate_trade_lists["N"] = best_n_trades

    print(f"\n  Best D+L stack: weekly -{best_m_cap:.1f}R + DD throttle >{best_n_thr:.0f}R")
    print(f"    Calmar: {best_n_calmar:.2f}  Net R: {best_n_m['net_r']:.1f}  DD: {best_n_m['max_dd']:.1f}")

    # Compare all D-family variants
    sep("Gate D Family Comparison")
    d_family = [
        ("D orig", f"Weekly cap -{best_d_cap:.0f}R", best_d_m, best_d_trades),
        ("M fine", f"Weekly cap -{best_m_cap:.1f}R", best_m_m, best_m_trades),
        ("N stack", f"Weekly -{best_m_cap:.1f}R + DD >{best_n_thr:.0f}R", best_n_m, best_n_trades),
    ]

    col_w = 12
    print(f"\n  {'ID':<10s}{'Description':<38s}{'Trades':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}")
    print(f"  {'─'*96}")
    print(f"  {'Baseline':<10s}{'No gating':<38s}{baseline_m['n']:>{col_w}d}"
          f"{baseline_m['net_r']:>{col_w}.1f}{baseline_m['max_dd']:>{col_w}.1f}"
          f"{baseline_m['calmar']:>{col_w}.2f}{baseline_m['sharpe']:>{col_w}.2f}")
    for vid, desc, m, trades in d_family:
        print(f"  {vid:<10s}{desc:<38s}{m['n']:>{col_w}d}{m['net_r']:>{col_w}.1f}"
              f"{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}"
              f"{m['sharpe']:>{col_w}.2f}")

    # R by year for all D-family
    print(f"\n  R by Year (D family):")
    all_yrs = sorted(set().union(*(r_by_year(tr).keys() for _, _, _, tr in d_family)))
    hdr = f"  {'Year':<8s}{'Baseline':>12s}"
    for vid, _, _, _ in d_family:
        hdr += f"{vid:>12s}"
    print(hdr)
    print(f"  {'─'*(8 + 12 * (1 + len(d_family)))}")

    d_yr_maps = [(vid, r_by_year(tr)) for vid, _, _, tr in d_family]
    for yr in all_yrs:
        row = f"  {yr:<8s}{baseline_yr_m.get(yr, 0.0):>+12.1f}"
        for vid, yr_map in d_yr_maps:
            row += f"{yr_map.get(yr, 0.0):>+12.1f}"
        print(row)

    # ── Summary comparison ───────────────────────────────────────────────────
    sep("GATING SUMMARY")

    col_w = 12
    print(f"\n  {'ID':<10s}{'Description':<40s}{'Trades':>{col_w}s}{'Net R':>{col_w}s}"
          f"{'DD':>{col_w}s}{'Calmar':>{col_w}s}{'Sharpe':>{col_w}s}{'DD chg':>{col_w}s}")
    print(f"  {'─'*110}")

    for gid, desc, m in gate_results:
        dd_delta = baseline_m["max_dd"] - m["max_dd"]
        dd_note = f"{dd_delta:+.1f}" if gid != "Baseline" else "—"
        print(f"  {gid:<10s}{desc:<40s}{m['n']:>{col_w}d}{m['net_r']:>{col_w}.1f}"
              f"{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}"
              f"{m['sharpe']:>{col_w}.2f}{dd_note:>{col_w}s}")

    # Find best gate by Calmar (excluding baseline)
    non_baseline = [(gid, desc, m) for gid, desc, m in gate_results if gid != "Baseline"]
    if non_baseline:
        best_gate = max(non_baseline, key=lambda x: x[2]["calmar"])
        print(f"\n  Best gate by Calmar: {best_gate[0]} — {best_gate[1]}")
        print(f"    Calmar: {best_gate[2]['calmar']:.2f} vs baseline {baseline_m['calmar']:.2f}")
        print(f"    DD:     {best_gate[2]['max_dd']:.1f} vs baseline {baseline_m['max_dd']:.1f}")
        print(f"    Net R:  {best_gate[2]['net_r']:.1f} vs baseline {baseline_m['net_r']:.1f}")

        calmar_lift = (best_gate[2]["calmar"] / baseline_m["calmar"] - 1) * 100
        dd_reduction = baseline_m["max_dd"] - best_gate[2]["max_dd"]
        print(f"    Calmar lift: {calmar_lift:+.1f}%")
        print(f"    DD reduction: {dd_reduction:+.1f}R")

    # R by year for baseline vs best gate
    if non_baseline:
        best_gid = best_gate[0]

        # Use the gate_trade_lists dict to get the actual trade list
        best_gate_trades = gate_trade_lists.get(best_gid, baseline_trades)
        baseline_yr = r_by_year(baseline_trades)
        best_yr = r_by_year(best_gate_trades)
        all_year_keys = sorted(set(baseline_yr) | set(best_yr))

        print(f"\n  R by Year — Baseline vs Best Gate ({best_gid}):")
        print(f"  {'Year':<8s}{'Baseline':>12s}{best_gid:>12s}{'Delta':>12s}")
        print(f"  {'─'*44}")
        for yr in all_year_keys:
            b = baseline_yr.get(yr, 0.0)
            g = best_yr.get(yr, 0.0)
            print(f"  {yr:<8s}{b:>+12.1f}{g:>+12.1f}{g - b:>+12.1f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    sep("NQ NY R20 x ASIA R9 RESTART — DRAWDOWN CORRELATION ANALYSIS", "=")
    print(f"\n  Combined DD (-24.2R) exceeds worst individual leg (NY: -21.9R, Asia: -11.3R)")
    print(f"  Goal: Quantify correlation, identify causes, test DD-reduction gates\n")
    print(f"  NY R20:  both, rr=2.625, stop=8.75%, gap=2.25%, tp1=0.3, ATR=12, ORB=20m")
    print(f"  Asia R9: long, rr=3.0,   stop=4.0%,  gap=0.90%, tp1=0.6, ATR=5,  ORB=15m, excl-Tue, ICF\n")

    t0_total = time.time()

    print("  Running backtests...")
    all_trades, df_5m = run_both_backtests()

    total = sum(len(v) for v in all_trades.values())
    if total == 0:
        print("ERROR: No trades loaded — aborting.")
        sys.exit(1)

    print(f"\n  Total filled trades: {total}")

    section1_individual(all_trades)
    section2_overlap(all_trades)
    section3_daily_corr(all_trades)
    section4_crosstab(all_trades)
    section5_drawdown_overlap(all_trades)
    section6_monthly_corr(all_trades)
    section7_regime_analysis(all_trades, df_5m)
    section8_gating(all_trades, df_5m)

    print(f"\n  Total runtime: {time.time() - t0_total:.1f}s")


if __name__ == "__main__":
    main()
