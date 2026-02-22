#!/usr/bin/env python3
"""NQ Asia R4 × ES Asia R5 — Correlation & Portfolio Analysis.

Both strategies trade the same Asia ORB window (20:00-20:10 ET).
This script re-runs both backtests and performs 9 sections of analysis:

  1. Individual metrics — side-by-side comparison table
  2. Trade date overlap — how often both fire on the same day, by year
  3. Daily R correlation — Pearson r on concurrent trade dates + all active dates (0-fill)
  4. Monthly R correlation — monthly sums correlation + rolling by year
  5. Concurrent outcome crosstab — Win/Loss/BE matrix on overlap days, conditional win rates
  6. Combined portfolio — merged equity curve, combined Net R / DD / Calmar, R by year
  7. Diversification benefit & recommendations
  8. First-to-fill only simulation — fill order analysis on overlap days
  9. Overlap day sizing variants — 6 sizing strategies exploiting second-to-fill edge

No DB writes. DD is informational only, not a hard filter.
"""

import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import (
    run_backtest,
    EXIT_NO_FILL,
    EXIT_NAMES,
)
from orb_backtest.results.metrics import compute_metrics

# ── Constants ─────────────────────────────────────────────────────────────────

NQ_DOW_EXCL = {3}  # no-Thursday
ES_DOW_EXCL = {3}  # no-Thursday
START_DATE = "2016-01-01"

LABELS = ["NQ_ASIA", "ES_ASIA"]


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
                "calmar": 0.0, "max_dd": 0.0}
    r = np.array([t["r_multiple"] for t in trades])
    wins = int((r > 0).sum())
    r_eq = np.cumsum(r)
    r_pk = np.maximum.accumulate(r_eq)
    max_dd = float(abs(np.min(r_eq - r_pk)))
    net_r = float(r_eq[-1])
    return {
        "n": len(trades),
        "wr": wins / len(trades),
        "avg_r": float(np.mean(r)),
        "net_r": net_r,
        "max_dd": max_dd,
        "calmar": net_r / max_dd if max_dd > 0 else 0.0,
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


# ── Config builders ───────────────────────────────────────────────────────────

def make_nq_asia_config() -> StrategyConfig:
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="01:00",
        flat_start="00:00",
        flat_end="07:00",
        stop_atr_pct=3.7,
        min_gap_atr_pct=0.90,
        max_gap_points=0.0,
        max_gap_atr_pct=5.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=1.75,
        tp1_ratio=0.35,
        atr_length=5,
        name="NQ Asia R4 Final",
    )


def make_es_asia_config() -> StrategyConfig:
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="03:00",
        flat_start="06:45",
        flat_end="07:00",
        stop_atr_pct=3.0,
        min_gap_atr_pct=0.5,
        max_gap_points=50.0,
        max_gap_atr_pct=0.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.0,
        tp1_ratio=0.5,
        atr_length=5,
        name="ES Asia R5 Final",
    )


# ── Data loading & backtest ──────────────────────────────────────────────────

def run_both_backtests() -> dict[str, list[dict]]:
    """Run NQ Asia R4 and ES Asia R5 backtests, return filled trades as dicts."""
    result: dict[str, list[dict]] = {}

    # NQ Asia R4
    print("  Loading NQ data...")
    t0 = time.time()
    nq_5m = load_5m_data("NQ_5m.csv")
    nq_1m = load_1m_for_5m("NQ_5m.csv")
    nq_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"    NQ loaded [{time.time() - t0:.1f}s]")

    nq_cfg = make_nq_asia_config()
    print("  Running NQ Asia R4 backtest...")
    t0 = time.time()
    nq_trades = run_backtest(nq_5m, nq_cfg, start_date=START_DATE,
                             df_1m=nq_1m, df_1s=nq_1s)
    nq_trades = apply_dow_filter(nq_trades, NQ_DOW_EXCL)
    nq_filled = [trade_to_dict(t) for t in nq_trades if t.exit_type != EXIT_NO_FILL]
    result["NQ_ASIA"] = nq_filled
    print(f"    NQ Asia: {len(nq_filled)} filled trades [{time.time() - t0:.1f}s]")

    # ES Asia R5
    print("  Loading ES data...")
    t0 = time.time()
    es_5m = load_5m_data("ES_5m.csv")
    es_1m = load_1m_for_5m("ES_5m.csv")
    es_1s = load_1s_for_5m("ES_5m.csv")
    print(f"    ES loaded [{time.time() - t0:.1f}s]")

    es_cfg = make_es_asia_config()
    print("  Running ES Asia R5 backtest...")
    t0 = time.time()
    es_trades = run_backtest(es_5m, es_cfg, start_date=START_DATE,
                             df_1m=es_1m, df_1s=es_1s)
    es_trades = apply_dow_filter(es_trades, ES_DOW_EXCL)
    es_filled = [trade_to_dict(t) for t in es_trades if t.exit_type != EXIT_NO_FILL]
    result["ES_ASIA"] = es_filled
    print(f"    ES Asia: {len(es_filled)} filled trades [{time.time() - t0:.1f}s]")

    return result


# ── SECTION 1 — Individual Metrics ───────────────────────────────────────────

def section1_individual(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 1 — Individual Metrics (Side-by-Side)")

    col_w = 16
    print(f"\n  {'Metric':<20s}{'NQ Asia R4':>{col_w}s}{'ES Asia R5':>{col_w}s}")
    print(f"  {'─'*52}")

    for label in LABELS:
        trades = all_trades[label]
        m = quick_metrics(trades)
        years = r_by_year(trades)
        sorted_yrs = sorted(years.items())
        neg_yrs = sum(1 for _, v in sorted_yrs if v < 0)

        if label == "NQ_ASIA":
            nq = m
            nq_neg = neg_yrs
            nq_years = sorted_yrs
        else:
            es = m
            es_neg = neg_yrs
            es_years = sorted_yrs

    rows = [
        ("Trades", f"{nq['n']}", f"{es['n']}"),
        ("Win Rate", f"{nq['wr']:.1%}", f"{es['wr']:.1%}"),
        ("Avg R", f"{nq['avg_r']:.3f}", f"{es['avg_r']:.3f}"),
        ("Net R", f"{nq['net_r']:.1f}", f"{es['net_r']:.1f}"),
        ("Max DD (R)", f"{nq['max_dd']:.1f}", f"{es['max_dd']:.1f}"),
        ("Calmar", f"{nq['calmar']:.2f}", f"{es['calmar']:.2f}"),
        ("Negative Years", f"{nq_neg}", f"{es_neg}"),
        ("Direction", "Both", "Long only"),
        ("ORB", "20:00-20:10", "20:00-20:10"),
        ("Entry End", "01:00", "03:00"),
        ("Flat Start", "00:00", "06:45"),
    ]
    for metric, nq_v, es_v in rows:
        print(f"  {metric:<20s}{nq_v:>{col_w}s}{es_v:>{col_w}s}")

    print(f"\n  R by Year:")
    all_year_keys = sorted(set(y for y, _ in nq_years) | set(y for y, _ in es_years))
    nq_yr_map = dict(nq_years)
    es_yr_map = dict(es_years)
    print(f"  {'Year':<8s}{'NQ Asia':>{col_w}s}{'ES Asia':>{col_w}s}{'Combined':>{col_w}s}")
    print(f"  {'─'*56}")
    for yr in all_year_keys:
        nq_r = nq_yr_map.get(yr, 0.0)
        es_r = es_yr_map.get(yr, 0.0)
        print(f"  {yr:<8s}{nq_r:>+{col_w}.1f}{es_r:>+{col_w}.1f}{nq_r+es_r:>+{col_w}.1f}")


# ── SECTION 2 — Trade Date Overlap ───────────────────────────────────────────

def section2_overlap(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 2 — Trade Date Overlap")

    nq_dates = {t["date"] for t in all_trades["NQ_ASIA"]}
    es_dates = {t["date"] for t in all_trades["ES_ASIA"]}
    overlap = sorted(nq_dates & es_dates)
    nq_only = nq_dates - es_dates
    es_only = es_dates - nq_dates
    all_dates = nq_dates | es_dates

    print(f"\n  Overall:")
    print(f"    NQ Asia active dates:   {len(nq_dates)}")
    print(f"    ES Asia active dates:   {len(es_dates)}")
    print(f"    Both fire same day:     {len(overlap)}  "
          f"({len(overlap)/len(all_dates)*100:.1f}% of all active dates)")
    print(f"    NQ only:                {len(nq_only)}")
    print(f"    ES only:                {len(es_only)}")

    # By year
    years = sorted(set(d[:4] for d in all_dates))
    col_w = 10
    print(f"\n  {'Year':<6s}{'NQ':>{col_w}s}{'ES':>{col_w}s}{'Both':>{col_w}s}"
          f"{'Overlap%':>{col_w}s}")
    print(f"  {'─'*46}")
    for yr in years:
        nq_yr = sum(1 for d in nq_dates if d[:4] == yr)
        es_yr = sum(1 for d in es_dates if d[:4] == yr)
        both_yr = sum(1 for d in overlap if d[:4] == yr)
        active_yr = sum(1 for d in all_dates if d[:4] == yr)
        pct = both_yr / active_yr * 100 if active_yr else 0
        print(f"  {yr:<6s}{nq_yr:>{col_w}d}{es_yr:>{col_w}d}"
              f"{both_yr:>{col_w}d}{pct:>{col_w}.1f}%")


# ── SECTION 3 — Daily R Correlation ──────────────────────────────────────────

def section3_daily_corr(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 3 — Daily R Correlation")

    nq_by_date = {t["date"]: t["r_multiple"] for t in all_trades["NQ_ASIA"]}
    es_by_date = {t["date"]: t["r_multiple"] for t in all_trades["ES_ASIA"]}

    # Concurrent dates only
    concurrent = sorted(set(nq_by_date) & set(es_by_date))
    if len(concurrent) < 10:
        print(f"\n  Insufficient concurrent dates ({len(concurrent)}) — skipping.")
        return

    nq_r = np.array([nq_by_date[d] for d in concurrent])
    es_r = np.array([es_by_date[d] for d in concurrent])
    r_conc, p_conc = pearsonr(nq_r, es_r)

    print(f"\n  Concurrent dates (both filled): {len(concurrent)}")
    print(f"  Pearson r (concurrent):  {r_conc:+.4f}  (p={p_conc:.4f})")

    # All active dates (0-fill for missing)
    all_dates = sorted(set(nq_by_date) | set(es_by_date))
    nq_all = np.array([nq_by_date.get(d, 0.0) for d in all_dates])
    es_all = np.array([es_by_date.get(d, 0.0) for d in all_dates])
    r_all, p_all = pearsonr(nq_all, es_all)

    print(f"\n  All active dates (0-fill): {len(all_dates)}")
    print(f"  Pearson r (0-fill):      {r_all:+.4f}  (p={p_all:.4f})")

    sig = "***" if abs(r_conc) > 0.30 else ""
    if abs(r_conc) < 0.10:
        print(f"\n  → Near-zero daily correlation — strategies are effectively independent day-to-day. {sig}")
    elif abs(r_conc) < 0.30:
        print(f"\n  → Weak daily correlation — some overlap but mostly independent. {sig}")
    else:
        print(f"\n  → Meaningful daily correlation — daily R moves together. {sig}")


# ── SECTION 4 — Monthly R Correlation ────────────────────────────────────────

def section4_monthly_corr(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 4 — Monthly R Correlation")

    nq_monthly = monthly_r(all_trades["NQ_ASIA"])
    es_monthly = monthly_r(all_trades["ES_ASIA"])

    all_months = sorted(set(nq_monthly) | set(es_monthly))
    common_months = sorted(set(nq_monthly) & set(es_monthly))

    if len(common_months) < 10:
        print(f"\n  Insufficient common months ({len(common_months)}) — skipping.")
        return

    # Correlation on common months
    nq_m = np.array([nq_monthly[m] for m in common_months])
    es_m = np.array([es_monthly[m] for m in common_months])
    r_common, p_common = pearsonr(nq_m, es_m)

    print(f"\n  Common months: {len(common_months)}  "
          f"({common_months[0]} → {common_months[-1]})")
    print(f"  Pearson r (common months): {r_common:+.4f}  (p={p_common:.4f})")

    # 0-fill for all months
    nq_all = np.array([nq_monthly.get(m, 0.0) for m in all_months])
    es_all = np.array([es_monthly.get(m, 0.0) for m in all_months])
    r_all, p_all = pearsonr(nq_all, es_all)
    print(f"  Pearson r (0-fill):        {r_all:+.4f}  (p={p_all:.4f})")

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
        nq_yr = np.array([nq_monthly[m] for m in yr_months])
        es_yr = np.array([es_monthly[m] for m in yr_months])
        r_yr, p_yr = pearsonr(nq_yr, es_yr)
        flag = " *" if abs(r_yr) > 0.50 else ""
        print(f"  {yr:<6s}{len(yr_months):>{col_w}d}{r_yr:>+{col_w}.3f}{p_yr:>{col_w}.4f}{flag}")

    print(f"\n  (* = |r| > 0.50 within that year)")


# ── SECTION 5 — Concurrent Outcome Crosstab ──────────────────────────────────

def section5_crosstab(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 5 — Concurrent Outcome Crosstab")

    nq_by_date = {t["date"]: t for t in all_trades["NQ_ASIA"]}
    es_by_date = {t["date"]: t for t in all_trades["ES_ASIA"]}
    concurrent = sorted(set(nq_by_date) & set(es_by_date))

    print(f"\n  Concurrent trade dates: {len(concurrent)}")
    if len(concurrent) < 10:
        print("  Insufficient concurrent dates for analysis.")
        return

    outcomes = ["Win", "Loss", "BE"]
    crosstab: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d in concurrent:
        crosstab[trade_outcome(nq_by_date[d])][trade_outcome(es_by_date[d])] += 1

    col_w = 9
    print(f"\n  Crosstab  NQ Asia (rows) × ES Asia (cols)\n")
    hdr = (f"  {'NQ↓  ES→':18s}"
           + "".join(f"{o:>{col_w}s}" for o in outcomes)
           + f"{'Total':>{col_w}s}")
    print(hdr)
    print(f"  {'─'*54}")
    for nq_out in outcomes:
        row_total = sum(crosstab[nq_out][es_out] for es_out in outcomes)
        row = f"  {nq_out:18s}"
        for es_out in outcomes:
            row += f"{crosstab[nq_out][es_out]:>{col_w}d}"
        row += f"{row_total:>{col_w}d}"
        print(row)

    col_totals = [sum(crosstab[nq_out][es_out] for nq_out in outcomes)
                  for es_out in outcomes]
    grand_total = sum(col_totals)
    print(f"  {'─'*54}")
    total_row = (f"  {'Total':18s}"
                 + "".join(f"{ct:>{col_w}d}" for ct in col_totals)
                 + f"{grand_total:>{col_w}d}")
    print(total_row)

    # Conditional win rates
    print(f"\n  Conditional win rates:")

    # P(ES wins | unconditional)
    es_wins_total = sum(crosstab[nq_out]["Win"] for nq_out in outcomes)
    uncond_wr = es_wins_total / grand_total if grand_total else 0.0
    print(f"    P(ES wins | unconditional):     {uncond_wr:.1%}  "
          f"({es_wins_total}/{grand_total})")

    # P(ES wins | NQ won/lost)
    for nq_out in ["Win", "Loss"]:
        total_given = sum(crosstab[nq_out][es_out] for es_out in outcomes)
        if total_given == 0:
            continue
        es_win_given = crosstab[nq_out]["Win"]
        print(f"    P(ES wins | NQ {nq_out:5s}):         "
              f"{es_win_given/total_given:.1%}  ({es_win_given}/{total_given})")

    # P(NQ wins | ES won/lost)
    nq_wins_total = sum(crosstab["Win"][es_out] for es_out in outcomes)
    for es_out in ["Win", "Loss"]:
        total_given = sum(crosstab[nq_out][es_out] for nq_out in outcomes)
        if total_given == 0:
            continue
        nq_win_given = crosstab["Win"][es_out]
        print(f"    P(NQ wins | ES {es_out:5s}):         "
              f"{nq_win_given/total_given:.1%}  ({nq_win_given}/{total_given})")

    # Win-rate delta
    nq_win_n = sum(crosstab["Win"][es_out] for es_out in outcomes)
    nq_loss_n = sum(crosstab["Loss"][es_out] for es_out in outcomes)
    if nq_win_n > 5 and nq_loss_n > 5:
        es_wr_given_nq_win = crosstab["Win"]["Win"] / nq_win_n
        es_wr_given_nq_loss = crosstab["Loss"]["Win"] / nq_loss_n
        diff = es_wr_given_nq_win - es_wr_given_nq_loss
        print(f"\n  Win-rate delta (P(ES wins|NQ wins) - P(ES wins|NQ loses)): {diff:+.1%}")
        if abs(diff) < 0.05:
            print(f"  → INDEPENDENT: ES outcome is largely independent of NQ outcome on same day")
        elif diff > 0.05:
            print(f"  → POSITIVE CORRELATION: Both tend to win/lose together (concentration risk)")
        else:
            print(f"  → NEGATIVE CORRELATION: ES tends to win when NQ loses (hedge behavior)")

    # Combined R on concurrent days
    combined_r = []
    for d in concurrent:
        combined_r.append(nq_by_date[d]["r_multiple"] + es_by_date[d]["r_multiple"])
    combined_r = np.array(combined_r)
    both_win = sum(1 for r in combined_r if r > 0)
    both_lose = sum(1 for r in combined_r if r < 0)
    print(f"\n  Combined daily R on concurrent dates:")
    print(f"    Net positive days:  {both_win}/{len(concurrent)} ({both_win/len(concurrent):.1%})")
    print(f"    Net negative days:  {both_lose}/{len(concurrent)} ({both_lose/len(concurrent):.1%})")
    print(f"    Avg combined R:     {np.mean(combined_r):+.3f}")
    print(f"    Worst combined day: {np.min(combined_r):+.3f}")
    print(f"    Best combined day:  {np.max(combined_r):+.3f}")


# ── SECTION 6 — Combined Portfolio ───────────────────────────────────────────

def section6_portfolio(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 6 — Combined Portfolio")

    nq_trades = all_trades["NQ_ASIA"]
    es_trades = all_trades["ES_ASIA"]

    # Merge and sort by date
    merged = []
    for t in nq_trades:
        entry = dict(t)
        entry["_source"] = "NQ_ASIA"
        merged.append(entry)
    for t in es_trades:
        entry = dict(t)
        entry["_source"] = "ES_ASIA"
        merged.append(entry)
    merged.sort(key=lambda t: t["date"])

    port_m = quick_metrics(merged)

    # Individual metrics for comparison
    nq_m = quick_metrics(nq_trades)
    es_m = quick_metrics(es_trades)

    col_w = 16
    print(f"\n  {'Metric':<20s}{'NQ Asia':>{col_w}s}{'ES Asia':>{col_w}s}{'Combined':>{col_w}s}")
    print(f"  {'─'*68}")
    rows = [
        ("Trades", f"{nq_m['n']}", f"{es_m['n']}", f"{port_m['n']}"),
        ("Win Rate", f"{nq_m['wr']:.1%}", f"{es_m['wr']:.1%}", f"{port_m['wr']:.1%}"),
        ("Avg R", f"{nq_m['avg_r']:.3f}", f"{es_m['avg_r']:.3f}", f"{port_m['avg_r']:.3f}"),
        ("Net R", f"{nq_m['net_r']:.1f}", f"{es_m['net_r']:.1f}", f"{port_m['net_r']:.1f}"),
        ("Max DD (R)", f"{nq_m['max_dd']:.1f}", f"{es_m['max_dd']:.1f}", f"{port_m['max_dd']:.1f}"),
        ("Calmar", f"{nq_m['calmar']:.2f}", f"{es_m['calmar']:.2f}", f"{port_m['calmar']:.2f}"),
    ]
    for metric, nq_v, es_v, p_v in rows:
        print(f"  {metric:<20s}{nq_v:>{col_w}s}{es_v:>{col_w}s}{p_v:>{col_w}s}")

    # R by year
    nq_yr = r_by_year(nq_trades)
    es_yr = r_by_year(es_trades)
    port_yr = r_by_year(merged)
    all_year_keys = sorted(set(nq_yr) | set(es_yr))

    print(f"\n  R by Year:")
    print(f"  {'Year':<8s}{'NQ Asia':>{col_w}s}{'ES Asia':>{col_w}s}{'Combined':>{col_w}s}")
    print(f"  {'─'*56}")
    for yr in all_year_keys:
        print(f"  {yr:<8s}{nq_yr.get(yr, 0.0):>+{col_w}.1f}"
              f"{es_yr.get(yr, 0.0):>+{col_w}.1f}"
              f"{port_yr.get(yr, 0.0):>+{col_w}.1f}")

    neg_nq = sum(1 for v in nq_yr.values() if v < 0)
    neg_es = sum(1 for v in es_yr.values() if v < 0)
    neg_port = sum(1 for v in port_yr.values() if v < 0)
    print(f"\n  Negative years:  NQ={neg_nq}  ES={neg_es}  Combined={neg_port}")

    # Compute years for annualized R
    if all_year_keys:
        n_years = len(all_year_keys)
        # Exclude partial years at boundaries
        first_yr_r = port_yr.get(all_year_keys[0], 0.0)
        last_yr_r = port_yr.get(all_year_keys[-1], 0.0)
        annual_r = port_m["net_r"] / n_years
        print(f"  Avg annual R (combined): {annual_r:.1f}")


# ── SECTION 7 — Diversification Benefit & Recommendations ────────────────────

def section7_recommendations(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 7 — Diversification Benefit & Recommendations")

    nq_m = quick_metrics(all_trades["NQ_ASIA"])
    es_m = quick_metrics(all_trades["ES_ASIA"])

    # Combined portfolio
    merged = []
    for t in all_trades["NQ_ASIA"]:
        entry = dict(t)
        entry["_source"] = "NQ_ASIA"
        merged.append(entry)
    for t in all_trades["ES_ASIA"]:
        entry = dict(t)
        entry["_source"] = "ES_ASIA"
        merged.append(entry)
    merged.sort(key=lambda t: t["date"])
    port_m = quick_metrics(merged)

    # Diversification metrics
    print(f"\n  Calmar Comparison:")
    print(f"    NQ Asia standalone:  {nq_m['calmar']:.2f}")
    print(f"    ES Asia standalone:  {es_m['calmar']:.2f}")
    print(f"    Combined portfolio:  {port_m['calmar']:.2f}")

    # Theoretical worst case: if perfectly correlated, DD would be additive
    theoretical_dd = nq_m["max_dd"] + es_m["max_dd"]
    dd_reduction = (1.0 - port_m["max_dd"] / theoretical_dd) * 100 if theoretical_dd > 0 else 0
    print(f"\n  Drawdown Analysis:")
    print(f"    NQ Asia max DD:       {nq_m['max_dd']:.1f}R")
    print(f"    ES Asia max DD:       {es_m['max_dd']:.1f}R")
    print(f"    Additive DD (worst):  {theoretical_dd:.1f}R  (if perfectly correlated)")
    print(f"    Actual combined DD:   {port_m['max_dd']:.1f}R")
    print(f"    DD reduction:         {dd_reduction:.1f}%  "
          f"(actual vs additive worst-case)")

    # Monthly R correlation summary
    nq_monthly = monthly_r(all_trades["NQ_ASIA"])
    es_monthly = monthly_r(all_trades["ES_ASIA"])
    common = sorted(set(nq_monthly) & set(es_monthly))
    if len(common) >= 10:
        nq_arr = np.array([nq_monthly[m] for m in common])
        es_arr = np.array([es_monthly[m] for m in common])
        r_val, p_val = pearsonr(nq_arr, es_arr)
        div_score = 1.0 - abs(r_val)
        quality = "excellent" if div_score > 0.85 else "good" if div_score > 0.70 else "moderate"
        print(f"\n  Diversification Score: {div_score:.3f}  "
              f"(monthly |r| = {abs(r_val):.3f})  [{quality}]")

    # Worst / best concurrent days
    nq_by_date = {t["date"]: t for t in all_trades["NQ_ASIA"]}
    es_by_date = {t["date"]: t for t in all_trades["ES_ASIA"]}
    concurrent = sorted(set(nq_by_date) & set(es_by_date))

    if concurrent:
        worst_day = None
        best_day = None
        worst_r = float("inf")
        best_r = float("-inf")
        for d in concurrent:
            combined = nq_by_date[d]["r_multiple"] + es_by_date[d]["r_multiple"]
            if combined < worst_r:
                worst_r = combined
                worst_day = d
            if combined > best_r:
                best_r = combined
                best_day = d

        print(f"\n  Concurrent Day Extremes:")
        if worst_day:
            print(f"    Worst day: {worst_day}  combined R = {worst_r:+.3f}  "
                  f"(NQ={nq_by_date[worst_day]['r_multiple']:+.3f}, "
                  f"ES={es_by_date[worst_day]['r_multiple']:+.3f})")
        if best_day:
            print(f"    Best day:  {best_day}  combined R = {best_r:+.3f}  "
                  f"(NQ={nq_by_date[best_day]['r_multiple']:+.3f}, "
                  f"ES={es_by_date[best_day]['r_multiple']:+.3f})")

    # Trading verdict
    sep("TRADING VERDICT")

    print(f"\n  Both NQ Asia R4 and ES Asia R5 trade the same ORB window (20:00-20:10 ET).")
    print(f"  Key question: does running both add diversification or just concentration?\n")

    # Determine recommendation based on data
    corr_low = len(common) >= 10 and abs(r_val) < 0.30
    dd_benefit = dd_reduction > 10
    calmar_benefit = port_m["calmar"] > max(nq_m["calmar"], es_m["calmar"]) * 0.8

    if corr_low and dd_benefit:
        print(f"  VERDICT: RUN BOTH")
        print(f"  Despite sharing the same ORB window:")
        if abs(r_val) < 0.10:
            print(f"    - Monthly correlation is near-zero (r={r_val:+.3f})")
        else:
            print(f"    - Monthly correlation is low (r={r_val:+.3f})")
        print(f"    - Actual DD is {dd_reduction:.0f}% less than worst-case additive DD")
        print(f"    - Combined Calmar {port_m['calmar']:.2f} benefits from diversification")
        print(f"    - Different instruments (NQ vs ES), different configs, different exit profiles")
    elif not corr_low:
        print(f"  VERDICT: CAUTION — MEANINGFUL CORRELATION")
        print(f"    - Monthly r = {r_val:+.3f} — strategies move together")
        print(f"    - Running both adds less diversification than expected")
        print(f"    - Consider: run both at half sizing, or pick the higher-Calmar one")
    else:
        print(f"  VERDICT: RUN BOTH (mild benefit)")
        print(f"    - Correlation is low enough to justify running both")
        print(f"    - DD reduction is modest ({dd_reduction:.0f}%) — benefits are real but small")

    print(f"\n  Position sizing note:")
    print(f"    Both strategies risk $5,000 per trade. On overlap days (~{len(concurrent)}"
          f" of {len(set(nq_by_date) | set(es_by_date))} active dates),")
    print(f"    total session risk is $10,000. If this exceeds your single-session")
    print(f"    risk limit, reduce each to $2,500 on concurrent days.")
    sep()


# ── SECTION 8 — First-to-Fill Only Simulation ─────────────────────────────────

def section8_first_to_fill(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 8 — First-to-Fill Only (Overlap Day Simulation)")

    nq_by_date = {t["date"]: t for t in all_trades["NQ_ASIA"]}
    es_by_date = {t["date"]: t for t in all_trades["ES_ASIA"]}
    concurrent = sorted(set(nq_by_date) & set(es_by_date))
    nq_only_dates = set(nq_by_date) - set(es_by_date)
    es_only_dates = set(es_by_date) - set(nq_by_date)

    print(f"\n  Concurrent dates: {len(concurrent)}")
    print(f"  NQ-only dates:    {len(nq_only_dates)}")
    print(f"  ES-only dates:    {len(es_only_dates)}")

    # On overlap days, determine which filled first
    nq_first = []  # dates where NQ filled before ES
    es_first = []  # dates where ES filled before NQ
    same_time = []  # rare: identical fill times
    nq_first_trades_nq = []  # the NQ trade on NQ-first days
    nq_first_trades_es = []  # the ES trade on NQ-first days
    es_first_trades_nq = []
    es_first_trades_es = []

    for d in concurrent:
        nq_t = nq_by_date[d]
        es_t = es_by_date[d]
        nq_ft = nq_t["fill_time"]
        es_ft = es_t["fill_time"]

        if nq_ft < es_ft:
            nq_first.append(d)
            nq_first_trades_nq.append(nq_t)
            nq_first_trades_es.append(es_t)
        elif es_ft < nq_ft:
            es_first.append(d)
            es_first_trades_nq.append(nq_t)
            es_first_trades_es.append(es_t)
        else:
            same_time.append(d)

    print(f"\n  Fill order on overlap days:")
    print(f"    NQ fills first: {len(nq_first)}  ({len(nq_first)/len(concurrent)*100:.1f}%)")
    print(f"    ES fills first: {len(es_first)}  ({len(es_first)/len(concurrent)*100:.1f}%)")
    if same_time:
        print(f"    Same time:      {len(same_time)}")

    # Performance of first-filler vs second-filler
    col_w = 12
    print(f"\n  Performance by fill order (overlap days only):")
    print(f"  {'':22s}{'Trades':>{col_w}s}{'WR':>{col_w}s}{'Avg R':>{col_w}s}{'Net R':>{col_w}s}")
    print(f"  {'─'*70}")

    if nq_first_trades_nq:
        nq1_m = quick_metrics(nq_first_trades_nq)
        es2_m = quick_metrics(nq_first_trades_es)
        print(f"  {'NQ (filled 1st)':22s}{nq1_m['n']:>{col_w}d}{nq1_m['wr']:>{col_w}.1%}"
              f"{nq1_m['avg_r']:>{col_w}.3f}{nq1_m['net_r']:>{col_w}.1f}")
        print(f"  {'ES (filled 2nd)':22s}{es2_m['n']:>{col_w}d}{es2_m['wr']:>{col_w}.1%}"
              f"{es2_m['avg_r']:>{col_w}.3f}{es2_m['net_r']:>{col_w}.1f}")
    if es_first_trades_es:
        es1_m = quick_metrics(es_first_trades_es)
        nq2_m = quick_metrics(es_first_trades_nq)
        print(f"  {'ES (filled 1st)':22s}{es1_m['n']:>{col_w}d}{es1_m['wr']:>{col_w}.1%}"
              f"{es1_m['avg_r']:>{col_w}.3f}{es1_m['net_r']:>{col_w}.1f}")
        print(f"  {'NQ (filled 2nd)':22s}{nq2_m['n']:>{col_w}d}{nq2_m['wr']:>{col_w}.1%}"
              f"{nq2_m['avg_r']:>{col_w}.3f}{nq2_m['net_r']:>{col_w}.1f}")

    # Does first-filler outcome predict second-filler outcome?
    print(f"\n  Does the first-to-fill outcome predict the second?")
    for first_label, first_trades, second_trades in [
        ("NQ first", nq_first_trades_nq, nq_first_trades_es),
        ("ES first", es_first_trades_es, es_first_trades_nq),
    ]:
        if len(first_trades) < 20:
            continue
        # Note: both trades are live simultaneously so "first outcome" isn't
        # known before the second fills — this is about correlation, not prediction
        first_win = [i for i, t in enumerate(first_trades) if t["r_multiple"] > 0]
        first_loss = [i for i, t in enumerate(first_trades) if t["r_multiple"] < 0]
        if first_win:
            second_r_given_win = np.array([second_trades[i]["r_multiple"] for i in first_win])
            wr_given_win = float((second_r_given_win > 0).mean())
        if first_loss:
            second_r_given_loss = np.array([second_trades[i]["r_multiple"] for i in first_loss])
            wr_given_loss = float((second_r_given_loss > 0).mean())
        if first_win and first_loss:
            print(f"    {first_label} → 2nd WR when 1st wins: {wr_given_win:.1%} (n={len(first_win)})  "
                  f"| 2nd WR when 1st loses: {wr_given_loss:.1%} (n={len(first_loss)})")

    # ── Build 3 portfolio variants ──────────────────────────────────────────
    # A) BOTH: current approach (all trades)
    both_trades = []
    for t in all_trades["NQ_ASIA"]:
        both_trades.append(dict(t, _source="NQ"))
    for t in all_trades["ES_ASIA"]:
        both_trades.append(dict(t, _source="ES"))
    both_trades.sort(key=lambda t: t["date"])

    # B) FIRST-TO-FILL ONLY: on overlap days, take only the first-to-fill;
    #    on non-overlap days, take whichever fired
    ftf_trades = []
    for d in nq_only_dates:
        ftf_trades.append(dict(nq_by_date[d], _source="NQ"))
    for d in es_only_dates:
        ftf_trades.append(dict(es_by_date[d], _source="ES"))
    for d in nq_first:
        ftf_trades.append(dict(nq_by_date[d], _source="NQ"))
    for d in es_first:
        ftf_trades.append(dict(es_by_date[d], _source="ES"))
    for d in same_time:
        # Tie-break: pick the one with better standalone Calmar (NQ)
        ftf_trades.append(dict(nq_by_date[d], _source="NQ"))
    ftf_trades.sort(key=lambda t: t["date"])

    # C) SECOND-TO-FILL ONLY (for comparison): take the laggard on overlap days
    stf_trades = []
    for d in nq_only_dates:
        stf_trades.append(dict(nq_by_date[d], _source="NQ"))
    for d in es_only_dates:
        stf_trades.append(dict(es_by_date[d], _source="ES"))
    for d in nq_first:
        stf_trades.append(dict(es_by_date[d], _source="ES"))  # ES was second
    for d in es_first:
        stf_trades.append(dict(nq_by_date[d], _source="NQ"))  # NQ was second
    for d in same_time:
        stf_trades.append(dict(es_by_date[d], _source="ES"))
    stf_trades.sort(key=lambda t: t["date"])

    # ── Compare all variants ────────────────────────────────────────────────
    both_m = quick_metrics(both_trades)
    ftf_m = quick_metrics(ftf_trades)
    stf_m = quick_metrics(stf_trades)
    nq_m = quick_metrics(all_trades["NQ_ASIA"])
    es_m = quick_metrics(all_trades["ES_ASIA"])

    sep("Portfolio Variant Comparison")
    col_w = 14
    print(f"\n  {'Variant':<22s}{'Trades':>{col_w}s}{'WR':>{col_w}s}{'Avg R':>{col_w}s}"
          f"{'Net R':>{col_w}s}{'Max DD':>{col_w}s}{'Calmar':>{col_w}s}")
    print(f"  {'─'*106}")
    for label, m in [
        ("NQ Asia only", nq_m),
        ("ES Asia only", es_m),
        ("Both (current)", both_m),
        ("First-to-fill only", ftf_m),
        ("Second-to-fill only", stf_m),
    ]:
        print(f"  {label:<22s}{m['n']:>{col_w}d}{m['wr']:>{col_w}.1%}{m['avg_r']:>{col_w}.3f}"
              f"{m['net_r']:>{col_w}.1f}{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}")

    # R by year for both vs first-to-fill
    both_yr = r_by_year(both_trades)
    ftf_yr = r_by_year(ftf_trades)
    all_year_keys = sorted(set(both_yr) | set(ftf_yr))

    print(f"\n  R by Year (Both vs First-to-Fill):")
    print(f"  {'Year':<8s}{'Both':>{col_w}s}{'First-Fill':>{col_w}s}{'Delta':>{col_w}s}")
    print(f"  {'─'*50}")
    for yr in all_year_keys:
        b = both_yr.get(yr, 0.0)
        f = ftf_yr.get(yr, 0.0)
        print(f"  {yr:<8s}{b:>+{col_w}.1f}{f:>+{col_w}.1f}{f-b:>+{col_w}.1f}")

    # What fraction of first-to-fill trades come from each asset?
    nq_count_ftf = sum(1 for t in ftf_trades if t["_source"] == "NQ")
    es_count_ftf = sum(1 for t in ftf_trades if t["_source"] == "ES")
    print(f"\n  First-to-fill composition: NQ={nq_count_ftf} ({nq_count_ftf/len(ftf_trades)*100:.1f}%)  "
          f"ES={es_count_ftf} ({es_count_ftf/len(ftf_trades)*100:.1f}%)")

    # Cost of first-to-fill vs both
    r_cost = both_m["net_r"] - ftf_m["net_r"]
    calmar_delta = ftf_m["calmar"] - both_m["calmar"]
    print(f"\n  First-to-fill vs Both:")
    print(f"    Net R cost:     {r_cost:+.1f}R  (trades lost: {both_m['n'] - ftf_m['n']})")
    print(f"    Calmar delta:   {calmar_delta:+.2f}")
    if calmar_delta > 0:
        print(f"    → First-to-fill has BETTER risk-adjusted returns (higher Calmar)")
    else:
        print(f"    → Both has BETTER risk-adjusted returns (higher Calmar)")


# ── SECTION 9 — Overlap Day Sizing Variants ──────────────────────────────────

def section9_sizing_variants(all_trades: dict[str, list[dict]]) -> dict | None:
    sep("SECTION 9 — Overlap Day Sizing Variants")

    nq_by_date = {t["date"]: t for t in all_trades["NQ_ASIA"]}
    es_by_date = {t["date"]: t for t in all_trades["ES_ASIA"]}
    overlap_dates = sorted(set(nq_by_date) & set(es_by_date))
    nq_only_dates = sorted(set(nq_by_date) - set(es_by_date))
    es_only_dates = sorted(set(es_by_date) - set(nq_by_date))

    # Classify overlap days by fill order
    nq_first: list[str] = []
    es_first: list[str] = []
    same_time: list[str] = []

    for d in overlap_dates:
        nq_ft = nq_by_date[d]["fill_time"]
        es_ft = es_by_date[d]["fill_time"]
        if nq_ft < es_ft:
            nq_first.append(d)
        elif es_ft < nq_ft:
            es_first.append(d)
        else:
            same_time.append(d)

    distinguishable = len(nq_first) + len(es_first)
    print(f"\n  Overlap dates: {len(overlap_dates)}  "
          f"(NQ first: {len(nq_first)}, ES first: {len(es_first)}, "
          f"same bar: {len(same_time)})")
    print(f"  NQ-only dates: {len(nq_only_dates)}")
    print(f"  ES-only dates: {len(es_only_dates)}")
    print(f"  Distinguishable order: {distinguishable}")

    # ── 9a. Fill timing gap distribution ─────────────────────────────────────
    sep("9a — Fill Timing Gap Distribution (distinguishable-order days)")

    from datetime import datetime

    gap_minutes: list[float] = []
    for d in nq_first + es_first:
        nq_ft = nq_by_date[d]["fill_time"]
        es_ft = es_by_date[d]["fill_time"]
        try:
            t1 = datetime.fromisoformat(nq_ft)
            t2 = datetime.fromisoformat(es_ft)
            gap_m = abs((t2 - t1).total_seconds()) / 60.0
            gap_minutes.append(gap_m)
        except (ValueError, TypeError):
            continue

    if gap_minutes:
        gap_arr = np.array(gap_minutes)
        buckets = [
            ("0-5 min", 0, 5),
            ("5-15 min", 5, 15),
            ("15-30 min", 15, 30),
            ("30-60 min", 30, 60),
            ("1-2 hours", 60, 120),
            ("2+ hours", 120, float("inf")),
        ]
        print(f"\n  Minutes between first and second fill (n={len(gap_arr)}):")
        print(f"  {'Bucket':<14s}{'Count':>8s}{'Pct':>8s}{'Cumul':>8s}")
        print(f"  {'─'*38}")
        cumul = 0
        for label, lo, hi in buckets:
            count = int(((gap_arr >= lo) & (gap_arr < hi)).sum())
            cumul += count
            pct = count / len(gap_arr) * 100
            cum_pct = cumul / len(gap_arr) * 100
            print(f"  {label:<14s}{count:>8d}{pct:>7.1f}%{cum_pct:>7.1f}%")

        print(f"\n  Median gap:  {np.median(gap_arr):.0f} min")
        print(f"  Mean gap:    {np.mean(gap_arr):.0f} min")
        print(f"  p25 / p75:   {np.percentile(gap_arr, 25):.0f} / "
              f"{np.percentile(gap_arr, 75):.0f} min")

    # ── Sizing simulation helper ─────────────────────────────────────────────
    # Build date→category sets for O(1) lookup. Cross-midnight sessions can
    # produce multiple trades on the same calendar date, so we iterate the
    # full trade lists (not the deduped dicts) to preserve every trade.
    nq_only_set = set(nq_only_dates)
    es_only_set = set(es_only_dates)
    nq_first_set = set(nq_first)
    es_first_set = set(es_first)
    same_time_set = set(same_time)

    def apply_sizing(
        first_scale: float,
        second_scale: float,
        both_scale: float,
        non_overlap_scale: float,
    ) -> list[dict]:
        """Build portfolio with adjusted r_multiples from full trade lists."""
        adjusted: list[dict] = []
        # Process every NQ trade
        for t in all_trades["NQ_ASIA"]:
            d = t["date"]
            new_t = dict(t)
            if d in nq_only_set:
                new_t["r_multiple"] *= non_overlap_scale
            elif d in nq_first_set:
                new_t["r_multiple"] *= first_scale   # NQ was first
            elif d in es_first_set:
                new_t["r_multiple"] *= second_scale   # NQ was second
            elif d in same_time_set:
                new_t["r_multiple"] *= both_scale
            else:
                new_t["r_multiple"] *= non_overlap_scale
            adjusted.append(new_t)
        # Process every ES trade
        for t in all_trades["ES_ASIA"]:
            d = t["date"]
            new_t = dict(t)
            if d in es_only_set:
                new_t["r_multiple"] *= non_overlap_scale
            elif d in es_first_set:
                new_t["r_multiple"] *= first_scale   # ES was first
            elif d in nq_first_set:
                new_t["r_multiple"] *= second_scale   # ES was second
            elif d in same_time_set:
                new_t["r_multiple"] *= both_scale
            else:
                new_t["r_multiple"] *= non_overlap_scale
            adjusted.append(new_t)
        adjusted.sort(key=lambda t: t["date"])
        return adjusted

    # ── 9b. Variant definitions and comparison ───────────────────────────────
    sep("9b — Sizing Variant Comparison")

    variants = [
        # (ID, Description, first_scale, second_scale, both_scale, non_overlap_scale)
        ("A", "Baseline (1.0x all)", 1.0, 1.0, 1.0, 1.0),
        ("B", "Boost overlap 1.25x", 1.25, 1.25, 1.25, 1.0),
        ("C", "Boost overlap 1.5x", 1.5, 1.5, 1.5, 1.0),
        ("D", "Add to 2nd (1.0/1.5x)", 1.0, 1.5, 1.25, 1.0),
        ("E", "Add more to 2nd (1.0/2.0x)", 1.0, 2.0, 1.5, 1.0),
        ("F", "Shift to 2nd (0.5/1.5x)", 0.5, 1.5, 1.0, 1.0),
    ]

    variant_results: list[tuple[str, str, dict, dict[str, float]]] = []
    for vid, desc, fs, ss, bs, nos in variants:
        trades = apply_sizing(fs, ss, bs, nos)
        m = quick_metrics(trades)
        yr = r_by_year(trades)
        variant_results.append((vid, desc, m, yr))

    # Summary table
    col_w = 12
    print(f"\n  {'ID':<4s}{'Description':<28s}{'Trades':>{col_w}s}{'WR':>{col_w}s}"
          f"{'Avg R':>{col_w}s}{'Net R':>{col_w}s}{'Max DD':>{col_w}s}{'Calmar':>{col_w}s}")
    print(f"  {'─'*100}")
    for vid, desc, m, yr in variant_results:
        print(f"  {vid:<4s}{desc:<28s}{m['n']:>{col_w}d}{m['wr']:>{col_w}.1%}"
              f"{m['avg_r']:>{col_w}.3f}{m['net_r']:>{col_w}.1f}"
              f"{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}")

    # ── 9c. R by year for all variants ───────────────────────────────────────
    sep("9c — R by Year (All Variants)")

    all_year_keys = sorted(
        set().union(*(yr.keys() for _, _, _, yr in variant_results))
    )
    # Header
    hdr = f"  {'Year':<8s}" + "".join(f"{vid:>{col_w}s}" for vid, _, _, _ in variant_results)
    print(f"\n{hdr}")
    print(f"  {'─'*(8 + col_w * len(variant_results))}")

    neg_years_by_variant: dict[str, int] = {}
    for yr_key in all_year_keys:
        row = f"  {yr_key:<8s}"
        for vid, _, m, yr_map in variant_results:
            val = yr_map.get(yr_key, 0.0)
            row += f"{val:>+{col_w}.1f}"
            if val < 0:
                neg_years_by_variant[vid] = neg_years_by_variant.get(vid, 0) + 1
        print(row)

    print(f"\n  Negative years:")
    for vid, desc, _, _ in variant_results:
        neg = neg_years_by_variant.get(vid, 0)
        flag = " ⚠" if neg > 0 else ""
        print(f"    {vid}: {neg}{flag}")

    # ── 9d. Recommendation ───────────────────────────────────────────────────
    sep("9d — Recommendation")

    # Find best Calmar variant
    best_vid, best_desc, best_m, best_yr = max(
        variant_results, key=lambda x: x[2]["calmar"]
    )
    baseline_m = variant_results[0][2]  # Variant A

    print(f"\n  Best Calmar variant: {best_vid} — {best_desc}")
    print(f"    Calmar:  {best_m['calmar']:.2f}  (baseline A: {baseline_m['calmar']:.2f})")
    print(f"    Net R:   {best_m['net_r']:.1f}  (baseline A: {baseline_m['net_r']:.1f})")
    print(f"    Max DD:  {best_m['max_dd']:.1f}  (baseline A: {baseline_m['max_dd']:.1f})")

    calmar_lift = (best_m["calmar"] / baseline_m["calmar"] - 1) * 100 if baseline_m["calmar"] > 0 else 0
    net_r_lift = best_m["net_r"] - baseline_m["net_r"]
    print(f"    Calmar lift: {calmar_lift:+.1f}%")
    print(f"    Net R lift:  {net_r_lift:+.1f}R")

    # Check for negative years in best variant
    best_neg = neg_years_by_variant.get(best_vid, 0)
    if best_neg > 0:
        print(f"\n    WARNING: Best variant has {best_neg} negative year(s).")
        # Find best with 0 negative years
        safe_variants = [
            (vid, desc, m, yr) for vid, desc, m, yr in variant_results
            if neg_years_by_variant.get(vid, 0) == 0
        ]
        if safe_variants:
            safe_best = max(safe_variants, key=lambda x: x[2]["calmar"])
            print(f"    Best with 0 neg years: {safe_best[0]} — {safe_best[1]} "
                  f"(Calmar {safe_best[2]['calmar']:.2f})")

    # Practical considerations
    print(f"\n  Practical considerations:")
    print(f"    - Both fills are limit orders. You can't wait to see which fills first.")
    print(f"    - Variant D/E: When 2nd fill triggers, add to that position at market.")
    print(f"    - Variant F: Pre-size both at 0.5x when dual signals exist;")
    print(f"      add 1.0x to whichever fills second.")
    print(f"    - Same-bar fills ({len(same_time)} of {len(overlap_dates)} overlap days) "
          f"get uniform scaling.")

    if gap_minutes:
        pct_under_5 = float((np.array(gap_minutes) < 5).mean()) * 100
        print(f"    - {pct_under_5:.0f}% of distinguishable fills are < 5 min apart — "
              f"reaction time is tight.")

    # ── 9e. Conditional sizing: boost 2nd only when 1st already exited ───────
    sep("9e — Conditional Sizing (boost 2nd when 1st already exited as winner)")

    TP1_PLUS = {"tp1_tp2", "tp1_be", "tp1_eod", "tp2_single"}
    TP2_ONLY = {"tp1_tp2", "tp2_single"}

    # Classify each distinguishable-order day by first trade's state at second fill
    first_won_tp1_dates: set[str] = set()   # first exited, hit TP1+
    first_won_tp2_dates: set[str] = set()   # first exited, hit TP2
    first_lost_dates: set[str] = set()      # first exited as loser
    first_open_dates: set[str] = set()      # first still open when second fills

    for d in nq_first:
        first_t, second_t = nq_by_date[d], es_by_date[d]
        if first_t["exit_time"] <= second_t["fill_time"]:
            if first_t["exit_type"] in TP1_PLUS:
                first_won_tp1_dates.add(d)
            if first_t["exit_type"] in TP2_ONLY:
                first_won_tp2_dates.add(d)
            if first_t["r_multiple"] <= 0:
                first_lost_dates.add(d)
        else:
            first_open_dates.add(d)

    for d in es_first:
        first_t, second_t = es_by_date[d], nq_by_date[d]
        if first_t["exit_time"] <= second_t["fill_time"]:
            if first_t["exit_type"] in TP1_PLUS:
                first_won_tp1_dates.add(d)
            if first_t["exit_type"] in TP2_ONLY:
                first_won_tp2_dates.add(d)
            if first_t["r_multiple"] <= 0:
                first_lost_dates.add(d)
        else:
            first_open_dates.add(d)

    n_dist = len(nq_first) + len(es_first)
    # Count by category
    # A date can be in first_won_tp1 OR first_lost OR first_open (mutually exclusive
    # for won vs lost, but tp2 is a subset of tp1+)
    exited_as_winner_tp1 = len(first_won_tp1_dates)
    exited_as_winner_tp2 = len(first_won_tp2_dates)
    exited_as_loser = len(first_lost_dates)
    still_open = len(first_open_dates)

    print(f"\n  First trade state when second fills ({n_dist} distinguishable-order days):")
    print(f"    First exited as winner (TP1+):  {exited_as_winner_tp1}  "
          f"({exited_as_winner_tp1/n_dist*100:.1f}%)")
    print(f"    First exited as winner (TP2):   {exited_as_winner_tp2}  "
          f"({exited_as_winner_tp2/n_dist*100:.1f}%)")
    print(f"    First exited as loser (SL/EOD): {exited_as_loser}  "
          f"({exited_as_loser/n_dist*100:.1f}%)")
    print(f"    First still open:               {still_open}  "
          f"({still_open/n_dist*100:.1f}%)")

    # Second-to-fill win rate conditioned on first trade's state
    def second_filler_stats(date_set: set[str], label: str) -> None:
        second_trades = []
        for d in date_set:
            if d in nq_first_set:
                second_trades.append(es_by_date[d])
            elif d in es_first_set:
                second_trades.append(nq_by_date[d])
        if not second_trades:
            print(f"    {label:<38s}  n=0")
            return
        m = quick_metrics(second_trades)
        print(f"    {label:<38s}  n={m['n']:<5d}  WR={m['wr']:.1%}  "
              f"Avg R={m['avg_r']:+.3f}  Net R={m['net_r']:+.1f}")

    print(f"\n  Second-to-fill performance by first trade's state:")
    second_filler_stats(first_won_tp1_dates, "1st exited winner (TP1+)")
    second_filler_stats(first_won_tp2_dates, "1st exited winner (TP2 only)")
    second_filler_stats(first_lost_dates, "1st exited loser")
    second_filler_stats(first_open_dates, "1st still open")
    # All second-fillers for comparison
    all_second = []
    for d in nq_first:
        all_second.append(es_by_date[d])
    for d in es_first:
        all_second.append(nq_by_date[d])
    m_all = quick_metrics(all_second)
    print(f"    {'All second-fillers (baseline)':<38s}  n={m_all['n']:<5d}  WR={m_all['wr']:.1%}  "
          f"Avg R={m_all['avg_r']:+.3f}  Net R={m_all['net_r']:+.1f}")

    # ── Conditional sizing variants ──────────────────────────────────────────

    def apply_two_way_sizing(
        boost_dates: set[str],
        second_boost: float,
        reduce_dates: set[str],
        second_reduce: float,
    ) -> list[dict]:
        """Scale second-to-fill: boost on boost_dates, reduce on reduce_dates,
        1.0x everywhere else. Scales r_multiple, pnl_usd, and pnl_points."""
        adjusted: list[dict] = []
        for t in all_trades["NQ_ASIA"]:
            d = t["date"]
            new_t = dict(t)
            # NQ is second-to-fill on es_first dates
            if d in es_first_set:
                if d in boost_dates:
                    new_t["r_multiple"] *= second_boost
                    new_t["pnl_usd"] *= second_boost
                    new_t["pnl_points"] *= second_boost
                elif d in reduce_dates:
                    new_t["r_multiple"] *= second_reduce
                    new_t["pnl_usd"] *= second_reduce
                    new_t["pnl_points"] *= second_reduce
            adjusted.append(new_t)
        for t in all_trades["ES_ASIA"]:
            d = t["date"]
            new_t = dict(t)
            # ES is second-to-fill on nq_first dates
            if d in nq_first_set:
                if d in boost_dates:
                    new_t["r_multiple"] *= second_boost
                    new_t["pnl_usd"] *= second_boost
                    new_t["pnl_points"] *= second_boost
                elif d in reduce_dates:
                    new_t["r_multiple"] *= second_reduce
                    new_t["pnl_usd"] *= second_reduce
                    new_t["pnl_points"] *= second_reduce
            adjusted.append(new_t)
        adjusted.sort(key=lambda t: t["date"])
        return adjusted

    # ── Legacy variants A, G-J (kept for continuity) ─────────────────────────
    cond_variants = [
        ("A", "Baseline (1.0x all)", set(), 1.0),
        ("G", "2nd 1.5x if 1st won (TP1+)", first_won_tp1_dates, 1.5),
        ("H", "2nd 2.0x if 1st won (TP1+)", first_won_tp1_dates, 2.0),
        ("I", "2nd 1.5x if 1st won (TP2)", first_won_tp2_dates, 1.5),
        ("J", "2nd 2.0x if 1st won (TP2)", first_won_tp2_dates, 2.0),
    ]

    cond_results: list[tuple[str, str, dict, dict[str, float]]] = []
    for vid, desc, boost_dates, boost in cond_variants:
        if vid == "A":
            trades = apply_sizing(1.0, 1.0, 1.0, 1.0)
        else:
            trades = apply_two_way_sizing(boost_dates, boost, set(), 1.0)
        m = quick_metrics(trades)
        yr = r_by_year(trades)
        cond_results.append((vid, desc, m, yr))

    print(f"\n  Conditional sizing variants (legacy):")
    col_w = 12
    print(f"  {'ID':<4s}{'Description':<32s}{'Trades':>{col_w}s}{'WR':>{col_w}s}"
          f"{'Avg R':>{col_w}s}{'Net R':>{col_w}s}{'Max DD':>{col_w}s}{'Calmar':>{col_w}s}")
    print(f"  {'─'*108}")
    for vid, desc, m, yr in cond_results:
        print(f"  {vid:<4s}{desc:<32s}{m['n']:>{col_w}d}{m['wr']:>{col_w}.1%}"
              f"{m['avg_r']:>{col_w}.3f}{m['net_r']:>{col_w}.1f}"
              f"{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}")

    # ── 9e-1. Fine-grained boost sweep (TP1+ trigger) ───────────────────────
    sep("9e-1 — Boost Sweep: 2nd-to-fill when 1st exited as TP1+ winner")

    boost_levels = [round(1.0 + i * 0.1, 1) for i in range(0, 16)]  # 1.0 to 2.5
    tp1_sweep: list[tuple[float, dict]] = []
    best_tp1_calmar = 0.0
    best_tp1_boost = 1.0

    print(f"\n  {'Boost':>7s}{'Net R':>10s}{'Max DD':>10s}{'Calmar':>10s}")
    print(f"  {'─'*37}")
    for boost in boost_levels:
        if boost == 1.0:
            trades = apply_sizing(1.0, 1.0, 1.0, 1.0)
        else:
            trades = apply_two_way_sizing(first_won_tp1_dates, boost, set(), 1.0)
        m = quick_metrics(trades)
        tp1_sweep.append((boost, m))
        marker = " ◀" if m["calmar"] > best_tp1_calmar else ""
        if m["calmar"] > best_tp1_calmar:
            best_tp1_calmar = m["calmar"]
            best_tp1_boost = boost
        print(f"  {boost:>6.1f}x{m['net_r']:>10.1f}{m['max_dd']:>10.1f}"
              f"{m['calmar']:>10.2f}{marker}")

    print(f"\n  Calmar-maximizing boost (TP1+): {best_tp1_boost:.1f}x "
          f"→ Calmar {best_tp1_calmar:.2f}")

    # ── 9e-2. Fine-grained boost sweep (TP2 trigger) ────────────────────────
    sep("9e-2 — Boost Sweep: 2nd-to-fill when 1st exited as TP2 winner")

    tp2_sweep: list[tuple[float, dict]] = []
    best_tp2_calmar = 0.0
    best_tp2_boost = 1.0

    print(f"\n  {'Boost':>7s}{'Net R':>10s}{'Max DD':>10s}{'Calmar':>10s}")
    print(f"  {'─'*37}")
    for boost in boost_levels:
        if boost == 1.0:
            trades = apply_sizing(1.0, 1.0, 1.0, 1.0)
        else:
            trades = apply_two_way_sizing(first_won_tp2_dates, boost, set(), 1.0)
        m = quick_metrics(trades)
        tp2_sweep.append((boost, m))
        marker = " ◀" if m["calmar"] > best_tp2_calmar else ""
        if m["calmar"] > best_tp2_calmar:
            best_tp2_calmar = m["calmar"]
            best_tp2_boost = boost
        print(f"  {boost:>6.1f}x{m['net_r']:>10.1f}{m['max_dd']:>10.1f}"
              f"{m['calmar']:>10.2f}{marker}")

    print(f"\n  Calmar-maximizing boost (TP2): {best_tp2_boost:.1f}x "
          f"→ Calmar {best_tp2_calmar:.2f}")

    # ── 9e-3. Reduce sweep: scale down 2nd when 1st lost ────────────────────
    sep("9e-3 — Reduce Sweep: 2nd-to-fill when 1st exited as loser")

    reduce_levels = [round(0.25 + i * 0.05, 2) for i in range(0, 14)]  # 0.25 to 0.90
    reduce_sweep: list[tuple[float, dict]] = []
    best_reduce_calmar = 0.0
    best_reduce_factor = 1.0

    print(f"\n  First-lost dates: {len(first_lost_dates)}")
    print(f"\n  {'Reduce':>8s}{'Net R':>10s}{'Max DD':>10s}{'Calmar':>10s}")
    print(f"  {'─'*38}")
    # Include 1.0 baseline for comparison
    baseline_trades = apply_sizing(1.0, 1.0, 1.0, 1.0)
    baseline_m = quick_metrics(baseline_trades)
    best_reduce_calmar = baseline_m["calmar"]
    best_reduce_factor = 1.0
    print(f"  {'1.00x':>8s}{baseline_m['net_r']:>10.1f}{baseline_m['max_dd']:>10.1f}"
          f"{baseline_m['calmar']:>10.2f}  (baseline)")
    for factor in reduce_levels:
        trades = apply_two_way_sizing(set(), 1.0, first_lost_dates, factor)
        m = quick_metrics(trades)
        reduce_sweep.append((factor, m))
        marker = " ◀" if m["calmar"] > best_reduce_calmar else ""
        if m["calmar"] > best_reduce_calmar:
            best_reduce_calmar = m["calmar"]
            best_reduce_factor = factor
        print(f"  {factor:>7.2f}x{m['net_r']:>10.1f}{m['max_dd']:>10.1f}"
              f"{m['calmar']:>10.2f}{marker}")

    print(f"\n  Calmar-maximizing reduce: {best_reduce_factor:.2f}x "
          f"→ Calmar {best_reduce_calmar:.2f}")

    # ── 9e-4. Combined variants ──────────────────────────────────────────────
    sep("9e-4 — Combined Variants (boost when won + reduce when lost)")

    combined_variants = [
        ("A", "Baseline (1.0x all)",
         set(), 1.0, set(), 1.0),
        ("K", f"TP1+ boost {best_tp1_boost:.1f}x + reduce {best_reduce_factor:.2f}x",
         first_won_tp1_dates, best_tp1_boost, first_lost_dates, best_reduce_factor),
        ("L", f"TP2 boost {best_tp2_boost:.1f}x + reduce {best_reduce_factor:.2f}x",
         first_won_tp2_dates, best_tp2_boost, first_lost_dates, best_reduce_factor),
        ("M", f"TP1+ boost {best_tp1_boost:.1f}x only (no reduce)",
         first_won_tp1_dates, best_tp1_boost, set(), 1.0),
        ("N", f"Reduce {best_reduce_factor:.2f}x only (no boost)",
         set(), 1.0, first_lost_dates, best_reduce_factor),
    ]

    combined_results: list[tuple[str, str, dict, dict[str, float]]] = []
    for vid, desc, b_dates, b_factor, r_dates, r_factor in combined_variants:
        if vid == "A":
            trades = apply_sizing(1.0, 1.0, 1.0, 1.0)
        else:
            trades = apply_two_way_sizing(b_dates, b_factor, r_dates, r_factor)
        m = quick_metrics(trades)
        yr = r_by_year(trades)
        combined_results.append((vid, desc, m, yr))

    col_w = 12
    print(f"\n  {'ID':<4s}{'Description':<46s}{'Net R':>{col_w}s}{'Max DD':>{col_w}s}{'Calmar':>{col_w}s}")
    print(f"  {'─'*86}")
    for vid, desc, m, yr in combined_results:
        print(f"  {vid:<4s}{desc:<46s}{m['net_r']:>{col_w}.1f}"
              f"{m['max_dd']:>{col_w}.1f}{m['calmar']:>{col_w}.2f}")

    # R by year for combined variants
    all_year_keys_c = sorted(
        set().union(*(yr.keys() for _, _, _, yr in combined_results))
    )
    print(f"\n  R by Year (Combined Variants):")
    hdr = f"  {'Year':<8s}" + "".join(f"{vid:>{col_w}s}" for vid, _, _, _ in combined_results)
    print(hdr)
    print(f"  {'─'*(8 + col_w * len(combined_results))}")
    neg_c: dict[str, int] = {}
    for yr_key in all_year_keys_c:
        row = f"  {yr_key:<8s}"
        for vid, _, _, yr_map in combined_results:
            val = yr_map.get(yr_key, 0.0)
            row += f"{val:>+{col_w}.1f}"
            if val < 0:
                neg_c[vid] = neg_c.get(vid, 0) + 1
        print(row)

    print(f"\n  Negative years: ", end="")
    print("  ".join(f"{vid}={neg_c.get(vid, 0)}" for vid, _, _, _ in combined_results))

    # ── 9e-5. Updated recommendation ─────────────────────────────────────────
    sep("9e-5 — Production Sizing Recommendation")

    # Find best Calmar among combined variants (excluding baseline)
    best_combined = max(combined_results[1:], key=lambda x: x[2]["calmar"])
    baseline_c = combined_results[0][2]  # Variant A

    print(f"\n  Sweep summary:")
    print(f"    Best TP1+ boost:  {best_tp1_boost:.1f}x → Calmar {best_tp1_calmar:.2f}")
    print(f"    Best TP2 boost:   {best_tp2_boost:.1f}x → Calmar {best_tp2_calmar:.2f}")
    print(f"    Best reduce:      {best_reduce_factor:.2f}x → Calmar {best_reduce_calmar:.2f}")

    lift = (best_combined[2]["calmar"] / baseline_c["calmar"] - 1) * 100
    print(f"\n  RECOMMENDED VARIANT: {best_combined[0]} — {best_combined[1]}")
    print(f"    Calmar: {best_combined[2]['calmar']:.2f}  "
          f"({lift:+.1f}% vs baseline {baseline_c['calmar']:.2f})")
    print(f"    Net R:  {best_combined[2]['net_r']:.1f}  "
          f"({best_combined[2]['net_r'] - baseline_c['net_r']:+.1f}R vs baseline)")
    print(f"    Max DD: {best_combined[2]['max_dd']:.1f}  "
          f"(baseline {baseline_c['max_dd']:.1f})")
    print(f"    Neg yrs: {neg_c.get(best_combined[0], 0)}")

    # Print R-by-year for recommended variant
    rec_yr = combined_results[[i for i, (v,_,_,_) in enumerate(combined_results)
                               if v == best_combined[0]][0]][3]
    print(f"\n  R by Year (recommended variant {best_combined[0]}):")
    print(f"  {'Year':<8s}{'Baseline':>12s}{best_combined[0]:>12s}{'Delta':>12s}")
    print(f"  {'─'*44}")
    baseline_yr = combined_results[0][3]
    for yr_key in sorted(set(baseline_yr) | set(rec_yr)):
        b_val = baseline_yr.get(yr_key, 0.0)
        r_val = rec_yr.get(yr_key, 0.0)
        print(f"  {yr_key:<8s}{b_val:>+12.1f}{r_val:>+12.1f}{r_val - b_val:>+12.1f}")

    print(f"\n  Production sizing rule:")
    print(f"    On overlap days where the first-to-fill has already exited:")
    print(f"      - If 1st exited as TP1+ winner → boost 2nd to {best_tp1_boost:.1f}x")
    if best_reduce_factor < 1.0:
        print(f"      - If 1st exited as loser       → reduce 2nd to {best_reduce_factor:.2f}x")
    print(f"      - If 1st still open             → keep 2nd at 1.0x")
    print(f"    On non-overlap or same-bar fill days → 1.0x (unchanged)")
    sep()

    # Return recommended variant for optional DB save
    rec_idx = [i for i, (v, _, _, _) in enumerate(combined_results)
               if v == best_combined[0]][0]
    _, rec_desc, _, _ = combined_results[rec_idx]
    rec_trades = apply_two_way_sizing(
        first_won_tp1_dates, best_tp1_boost,
        first_lost_dates if best_reduce_factor < 1.0 else set(),
        best_reduce_factor,
    )
    return {
        "variant_id": best_combined[0],
        "description": rec_desc,
        "trades": rec_trades,
        "tp1_boost": best_tp1_boost,
        "reduce_factor": best_reduce_factor,
    }


# ── DB Save ───────────────────────────────────────────────────────────────────

def compute_full_metrics(trades: list[dict]) -> dict:
    """Compute full metrics dict from trade dicts (mirrors compute_metrics)."""
    if not trades:
        return {}

    pnl_usd = np.array([t["pnl_usd"] for t in trades])
    r_mult = np.array([t["r_multiple"] for t in trades])

    wins = pnl_usd > 0
    losses = pnl_usd < 0

    total_wins = float(np.sum(pnl_usd[wins]))
    total_losses = float(np.sum(pnl_usd[losses]))

    # USD equity curve / drawdown
    equity = np.cumsum(pnl_usd)
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak
    max_dd_usd = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0

    # R equity curve / drawdown
    r_equity = np.cumsum(r_mult)
    r_peak = np.maximum.accumulate(r_equity)
    r_drawdown = r_equity - r_peak
    max_dd_r = float(np.min(r_drawdown)) if len(r_drawdown) > 0 else 0.0
    net_r = float(r_equity[-1]) if len(r_equity) > 0 else 0.0

    avg_r = float(np.mean(r_mult))
    std_r = float(np.std(r_mult, ddof=1)) if len(r_mult) > 1 else 1.0
    sharpe = (avg_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0

    downside = np.minimum(r_mult, 0.0)
    downside_std = float(np.sqrt(np.mean(downside ** 2)))
    sortino = (avg_r / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

    calmar = (net_r / abs(max_dd_r)) if max_dd_r != 0 else 0.0

    # Max DD as % of peak equity
    max_dd_pct = 0.0
    if len(peak) > 0 and np.max(peak) > 0:
        dd_pct = drawdown / np.where(peak > 0, peak, 1.0) * 100
        max_dd_pct = float(np.min(dd_pct))

    # Consecutive wins/losses
    def _max_consec(arr: np.ndarray) -> int:
        if len(arr) == 0:
            return 0
        best = current = 0
        for v in arr:
            if v:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best

    max_consec_wins = _max_consec(pnl_usd > 0)
    max_consec_losses = _max_consec(pnl_usd < 0)

    # Exit type breakdown
    exit_counts: dict[str, int] = {}
    for t in trades:
        et = t.get("exit_type", "unknown")
        exit_counts[et] = exit_counts.get(et, 0) + 1

    # Breakdowns by time
    yr_r: dict[str, float] = {}
    yr_pnl: dict[str, float] = {}
    mo_pnl: dict[str, float] = {}
    dow_pnl: dict[str, float] = {}
    for t in trades:
        d = t["date"]
        yr_r[d[:4]] = yr_r.get(d[:4], 0.0) + t["r_multiple"]
        yr_pnl[d[:4]] = yr_pnl.get(d[:4], 0.0) + t["pnl_usd"]
        mo_pnl[d[:7]] = mo_pnl.get(d[:7], 0.0) + t["pnl_usd"]

    # Direction breakdown
    long_pnl = sum(t["pnl_usd"] for t in trades if t["direction"] == "long")
    short_pnl = sum(t["pnl_usd"] for t in trades if t["direction"] == "short")
    long_r = sum(t["r_multiple"] for t in trades if t["direction"] == "long")
    short_r = sum(t["r_multiple"] for t in trades if t["direction"] == "short")
    long_trades = [t for t in trades if t["direction"] == "long"]
    short_trades = [t for t in trades if t["direction"] == "short"]
    long_wins = sum(1 for t in long_trades if t["pnl_usd"] > 0)
    short_wins = sum(1 for t in short_trades if t["pnl_usd"] > 0)

    return {
        "total_signals": len(trades),
        "total_trades": len(trades),
        "no_fills": 0,
        "win_count": int(np.sum(wins)),
        "loss_count": int(np.sum(losses)),
        "be_count": int(np.sum(~wins & ~losses)),
        "win_rate": float(np.mean(wins)),
        "total_pnl_usd": float(np.sum(pnl_usd)),
        "avg_pnl_usd": float(np.mean(pnl_usd)),
        "avg_win_usd": float(np.mean(pnl_usd[wins])) if wins.any() else 0.0,
        "avg_loss_usd": float(np.mean(pnl_usd[losses])) if losses.any() else 0.0,
        "largest_win_usd": float(np.max(pnl_usd)),
        "largest_loss_usd": float(np.min(pnl_usd)),
        "profit_factor": abs(total_wins / total_losses) if total_losses != 0 else 0.0,
        "avg_r": avg_r,
        "avg_win_r": float(np.mean(r_mult[wins])) if wins.any() else 0.0,
        "avg_loss_r": float(np.mean(r_mult[losses])) if losses.any() else 0.0,
        "total_r": net_r,
        "max_drawdown_usd": max_dd_usd,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_r": max_dd_r,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
        "exit_breakdown": exit_counts,
        "r_by_year": yr_r,
        "pnl_by_year": yr_pnl,
        "pnl_by_month": mo_pnl,
        "pnl_by_dow": dow_pnl,
        "long_trades": len(long_trades),
        "short_trades": len(short_trades),
        "long_win_rate": long_wins / len(long_trades) if long_trades else 0.0,
        "short_win_rate": short_wins / len(short_trades) if short_trades else 0.0,
        "long_pnl_usd": long_pnl,
        "short_pnl_usd": short_pnl,
        "long_r": long_r,
        "short_r": short_r,
    }


def save_variant_to_db(
    variant_info: dict,
    nq_cfg: StrategyConfig,
    es_cfg: StrategyConfig,
) -> int:
    """Save the recommended sizing variant to experiments.db."""
    from orb_backtest.experiments import log_run

    trades = variant_info["trades"]
    summary = compute_full_metrics(trades)

    # Build combined config representing both strategies
    config = {
        "instrument": "NQ+ES",
        "strategy": "continuation",
        "portfolio_type": "conditional_sizing",
        "tp1_boost": variant_info["tp1_boost"],
        "reduce_factor": variant_info["reduce_factor"],
        "risk_usd": 5000.0,
        # NQ Asia params
        "nq_rr": nq_cfg.rr,
        "nq_tp1_ratio": nq_cfg.tp1_ratio,
        "nq_atr_length": nq_cfg.atr_length,
        "nq_direction": nq_cfg.direction_filter,
        "asia_stop_atr_pct": nq_cfg.sessions[0].stop_atr_pct,
        "asia_min_gap_atr_pct": nq_cfg.sessions[0].min_gap_atr_pct,
        "asia_orb_window": f"{nq_cfg.sessions[0].orb_start}-{nq_cfg.sessions[0].orb_end}",
        "asia_entry_window": f"{nq_cfg.sessions[0].entry_start}-{nq_cfg.sessions[0].entry_end}",
        "asia_flat_window": f"{nq_cfg.sessions[0].flat_start}-{nq_cfg.sessions[0].flat_end}",
        # ES Asia params
        "es_rr": es_cfg.rr,
        "es_tp1_ratio": es_cfg.tp1_ratio,
        "es_atr_length": es_cfg.atr_length,
        "es_direction": es_cfg.direction_filter,
    }

    # Build equity curve
    equity_curve = []
    cumulative = 0.0
    for t in trades:
        cumulative += t["pnl_usd"]
        equity_curve.append({
            "date": t["date"],
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t["pnl_usd"], 2),
        })

    # Build trade list for DB
    trade_list = []
    for t in trades:
        trade_list.append({
            "date": t["date"],
            "session": t["session"],
            "direction": t["direction"],
            "entry_price": round(t["entry_price"], 4),
            "stop_price": round(t["stop_price"], 4),
            "tp1_price": round(t["tp1_price"], 4),
            "tp2_price": round(t["tp2_price"], 4),
            "exit_type": t["exit_type"],
            "pnl_usd": round(t["pnl_usd"], 2),
            "pnl_points": round(t["pnl_points"], 4),
            "r_multiple": round(t["r_multiple"], 3),
            "qty": 1,
            "gap_size": round(t["gap_size"], 4),
            "risk_points": round(t["risk_points"], 4),
            "entry_time": t.get("fill_time", ""),
            "exit_time": t.get("exit_time", ""),
        })

    result_dict = {
        "name": f"NQ+ES ASIA Conditional Sizing {variant_info['variant_id']} "
                f"(TP1+ boost {variant_info['tp1_boost']:.1f}x)",
        "notes": (
            f"Variant {variant_info['variant_id']}: {variant_info['description']}. "
            f"On overlap days, boost 2nd-to-fill by {variant_info['tp1_boost']:.1f}x "
            f"when 1st exited as TP1+ winner. "
            f"From run_nq_es_asia_correlation.py section 9e."
        ),
        "config": config,
        "summary": summary,
        "equity_curve": equity_curve,
        "trades": trade_list,
    }

    import hashlib, json
    h = hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()[:6]
    result_id = f"bt-nqes.asia.cond-{h}"

    row_id = log_run(result_dict, result_id)
    return row_id


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    save_mode = "--save" in sys.argv

    sep("NQ ASIA R4 × ES ASIA R5 — CORRELATION & PORTFOLIO ANALYSIS", "═")
    print(f"\n  Both trade Asia ORB 20:00-20:10 ET")
    print(f"  NQ: both directions, stop=3.7%, rr=1.75, gap=0.90%, tp1=0.35")
    print(f"  ES: long only, stop=3.0%, rr=2.0, gap=0.5%, tp1=0.5\n")

    t0_total = time.time()

    print("  Running backtests...")
    all_trades = run_both_backtests()

    total = sum(len(v) for v in all_trades.values())
    if total == 0:
        print("ERROR: No trades loaded — aborting.")
        sys.exit(1)

    print(f"\n  Total filled trades: {total}")

    section1_individual(all_trades)
    section2_overlap(all_trades)
    section3_daily_corr(all_trades)
    section4_monthly_corr(all_trades)
    section5_crosstab(all_trades)
    section6_portfolio(all_trades)
    section7_recommendations(all_trades)
    section8_first_to_fill(all_trades)
    variant_info = section9_sizing_variants(all_trades)

    if save_mode and variant_info:
        sep("SAVING TO DB")
        nq_cfg = make_nq_asia_config()
        es_cfg = make_es_asia_config()
        row_id = save_variant_to_db(variant_info, nq_cfg, es_cfg)
        print(f"\n  Saved recommended variant to experiments.db (row ID: {row_id})")
        print(f"    Name: NQ+ES ASIA Conditional Sizing {variant_info['variant_id']} "
              f"(TP1+ boost {variant_info['tp1_boost']:.1f}x)")

    print(f"\n  Total runtime: {time.time() - t0_total:.1f}s")
    if not save_mode:
        print(f"  (Use --save to persist recommended variant to DB)")


if __name__ == "__main__":
    main()
