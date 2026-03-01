#!/usr/bin/env python3
"""Cross-asset deep analysis for the 4-way portfolio.

Strategies analyzed:
  ID 6693 — GC NY Inv Longs Stacked v9+CleanAir
  ID 6707 — ES LDN 2016-2026 Continuation Both WF Mode
  ID 6717 — NQ NY Long Continuation Accepted (WF Mode)
  ID 6718 — NQ ASIA 2015-2026 v3 flat00 Pipeline NO-GO

Sections:
  1. Pairwise monthly R correlation matrix
  2. Rolling 12-month correlation (by year)
  3. Concurrent trade day analysis (NQ NY ↔ GC NY)
  4. Sequential signal analysis (information cascade)
  5. Regime-conditional performance (VIX / SPY / DXY)
  6. Conditional trade filtering simulation (F1–F6)
  7. Summary & recommendations

All analysis is post-hoc on saved trades from the DB — no re-backtesting.
No DB writes. DD is informational only, not a hard filter.
"""

import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.experiments import DB_PATH

# ── Constants ─────────────────────────────────────────────────────────────────

RUN_IDS = {
    "NQ_ASIA": 6718,
    "ES_LDN":  6707,
    "NQ_NY":   6717,
    "GC_NY":   6693,
}

STRAT_ORDER = ["NQ_ASIA", "ES_LDN", "NQ_NY", "GC_NY"]

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


# ── Formatting helpers ─────────────────────────────────────────────────────────

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
    # Normal approximation for p-value (accurate for n > 30)
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t_stat) / math.sqrt(2.0))))
    return r, p


# ── Data loading ──────────────────────────────────────────────────────────────

def load_trades() -> dict[str, list[dict]]:
    conn = sqlite3.connect(DB_PATH)
    result: dict[str, list[dict]] = {}
    for label, run_id in RUN_IDS.items():
        row = conn.execute(
            "SELECT experiment_name, trades_json FROM runs WHERE id=?", [run_id]
        ).fetchone()
        if row is None:
            print(f"  WARNING: run ID {run_id} ({label}) not found")
            result[label] = []
            continue
        trades = json.loads(row[1]) if row[1] else []
        filled = [t for t in trades if t.get("exit_type") != "no_fill"]
        result[label] = filled
        print(f"  {label:10s} ({run_id}): {len(filled):5d} filled trades  ← {row[0]}")
    conn.close()
    return result


def load_macro() -> dict[str, pd.Series]:
    macro: dict[str, pd.Series] = {}
    for name in ["VIX", "SPY", "DXY"]:
        path = DATA_DIR / f"{name}_daily.csv"
        if not path.exists():
            print(f"  WARNING: {path.name} not found — skipping")
            continue
        df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        macro[name] = df["Close"].sort_index()
        print(f"  {name}: {len(macro[name])} bars  "
              f"{macro[name].index[0].date()} → {macro[name].index[-1].date()}")
    return macro


# ── Core helpers ──────────────────────────────────────────────────────────────

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


def prior_close(series: pd.Series, date_str: str) -> float | None:
    """Prior-day close for a trade date (no look-ahead bias)."""
    dt = pd.Timestamp(date_str)
    available = series[series.index < dt]
    if available.empty:
        return None
    return float(available.iloc[-1])


def prior_close_series(series: pd.Series, trades: list[dict]) -> list[float | None]:
    """Vectorised prior-close lookup for a list of trades."""
    result = []
    for t in trades:
        result.append(prior_close(series, t["date"]))
    return result


def build_monthly_df(all_trades: dict[str, list[dict]]) -> pd.DataFrame:
    monthly = {lbl: monthly_r(trades) for lbl, trades in all_trades.items()}
    all_months = sorted(set().union(*[set(m.keys()) for m in monthly.values()]))
    df = pd.DataFrame(index=all_months)
    for lbl in STRAT_ORDER:
        df[lbl] = [monthly.get(lbl, {}).get(m, np.nan) for m in all_months]
    return df.dropna(how="all")


# ── SECTION 1 ─ Pairwise Monthly R Correlation Matrix ─────────────────────────

def section1_correlation(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 1 — Pairwise Monthly R Correlation Matrix")

    df = build_monthly_df(all_trades)
    print(f"\n  Monthly data: {len(df)} months  "
          f"{df.index[0]} → {df.index[-1]}")
    print(f"  Months with data per strategy: {df.notna().sum().to_dict()}\n")

    n = len(STRAT_ORDER)
    corr_mat = np.full((n, n), 1.0)
    pval_mat = np.full((n, n), 0.0)

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            x, y = df[STRAT_ORDER[i]], df[STRAT_ORDER[j]]
            mask = x.notna() & y.notna()
            if mask.sum() < 10:
                corr_mat[i, j] = pval_mat[i, j] = np.nan
            else:
                corr_mat[i, j], pval_mat[i, j] = pearsonr(
                    x[mask].values, y[mask].values
                )

    col_w = 14
    header = f"  {'':16s}" + "".join(f"{lbl:>{col_w}s}" for lbl in STRAT_ORDER)

    print(f"  Pearson Correlation (monthly R):\n")
    print(header)
    print(f"  {'─'*72}")
    for i, row_lbl in enumerate(STRAT_ORDER):
        row = f"  {row_lbl:16s}"
        for j in range(n):
            v = corr_mat[i, j]
            if np.isnan(v):
                row += f"{'N/A':>{col_w}s}"
            elif i == j:
                row += f"{'1.000':>{col_w}s}"
            else:
                flag = "*" if abs(v) > 0.30 else " "
                row += f"{v:>{col_w-1}.3f}{flag}"
        print(row)

    print(f"\n  (* = |r| > 0.30 — meaningfully correlated)\n")
    print(f"  P-values:\n")
    print(header)
    print(f"  {'─'*72}")
    for i, row_lbl in enumerate(STRAT_ORDER):
        row = f"  {row_lbl:16s}"
        for j in range(n):
            if i == j:
                row += f"{'—':>{col_w}s}"
            elif np.isnan(pval_mat[i, j]):
                row += f"{'N/A':>{col_w}s}"
            else:
                row += f"{pval_mat[i, j]:>{col_w}.4f}"
        print(row)

    flags = []
    for i in range(n):
        for j in range(i + 1, n):
            r_val = corr_mat[i, j]
            if not np.isnan(r_val) and abs(r_val) > 0.30:
                flags.append(
                    f"  *** {STRAT_ORDER[i]} ↔ {STRAT_ORDER[j]}: "
                    f"r={r_val:+.3f}  p={pval_mat[i,j]:.4f}"
                )

    if flags:
        print(f"\n  Flagged pairs (|r| > 0.30):")
        for f in flags:
            print(f)
    else:
        print(f"\n  No pairs exceed |r| > 0.30 — portfolio is well-diversified monthly.")


# ── SECTION 2 ─ Rolling 12-Month Correlation by Year ─────────────────────────

def section2_rolling(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 2 — Rolling 12-Month Correlation (by Year)")

    df = build_monthly_df(all_trades)
    years = sorted(set(m[:4] for m in df.index))

    pairs = [
        (STRAT_ORDER[i], STRAT_ORDER[j])
        for i in range(len(STRAT_ORDER))
        for j in range(i + 1, len(STRAT_ORDER))
    ]
    pair_labels = [f"{a[:5]}↔{b[:5]}" for a, b in pairs]

    col_w = 13
    header = f"  {'Year':6s}" + "".join(f"{p:>{col_w}s}" for p in pair_labels)
    print(f"\n  Rolling 12-month Pearson correlation per year:\n")
    print(header)
    print(f"  {'─'*85}")

    for yr in years:
        yr_months = [m for m in df.index if m[:4] == yr]
        if len(yr_months) < 6:
            continue
        row = f"  {yr:6s}"
        for a, b in pairs:
            x, y = df.loc[yr_months, a], df.loc[yr_months, b]
            mask = x.notna() & y.notna()
            if mask.sum() < 6:
                row += f"{'N/A':>{col_w}s}"
            else:
                r, _ = pearsonr(x[mask].values, y[mask].values)
                flag = "*" if abs(r) > 0.50 else " "
                row += f"{r:>{col_w-1}.3f}{flag}"
        print(row)

    print(f"\n  (* = |r| > 0.50 within that 12-month window)")


# ── SECTION 3 ─ Concurrent Trade Day Analysis (NQ NY ↔ GC NY) ────────────────

def section3_concurrent(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 3 — Concurrent Trade Day Analysis (NQ NY ↔ GC NY)")

    nq_by_date = {t["date"]: t for t in all_trades["NQ_NY"]}
    gc_by_date = {t["date"]: t for t in all_trades["GC_NY"]}
    concurrent = sorted(set(nq_by_date) & set(gc_by_date))

    print(f"\n  Concurrent trade dates (both filled): {len(concurrent)}")
    if len(concurrent) < 10:
        print("  Insufficient concurrent dates for analysis.")
        return

    outcomes = ["Win", "Loss", "BE"]
    crosstab: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d in concurrent:
        crosstab[trade_outcome(nq_by_date[d])][trade_outcome(gc_by_date[d])] += 1

    col_w = 9
    print(f"\n  Crosstab  NQ NY (rows) × GC NY (cols)\n")
    hdr = f"  {'NQ↓  GC→':18s}" + "".join(f"{o:>{col_w}s}" for o in outcomes) + f"{'Total':>{col_w}s}"
    print(hdr)
    print(f"  {'─'*54}")
    for nq_out in outcomes:
        row_total = sum(crosstab[nq_out][gc_out] for gc_out in outcomes)
        row = f"  {nq_out:18s}"
        for gc_out in outcomes:
            row += f"{crosstab[nq_out][gc_out]:>{col_w}d}"
        row += f"{row_total:>{col_w}d}"
        print(row)

    col_totals = [sum(crosstab[nq_out][gc_out] for nq_out in outcomes) for gc_out in outcomes]
    grand_total = sum(col_totals)
    print(f"  {'─'*54}")
    total_row = f"  {'Total':18s}" + "".join(f"{ct:>{col_w}d}" for ct in col_totals)
    total_row += f"{grand_total:>{col_w}d}"
    print(total_row)

    print(f"\n  Conditional win rates:")
    gc_wins_total = sum(crosstab[nq_out]["Win"] for nq_out in outcomes)
    unconditional_wr = gc_wins_total / grand_total if grand_total else 0.0
    print(f"    P(GC wins | unconditional):  {unconditional_wr:.1%}  ({gc_wins_total}/{grand_total})")

    for nq_out in ["Win", "Loss"]:
        total_given = sum(crosstab[nq_out][gc_out] for gc_out in outcomes)
        if total_given == 0:
            continue
        gc_win_given = crosstab[nq_out]["Win"]
        print(f"    P(GC wins | NQ {nq_out:5s}):      {gc_win_given/total_given:.1%}  ({gc_win_given}/{total_given})")

    nq_win = sum(crosstab["Win"][gc_out] for gc_out in outcomes)
    nq_loss = sum(crosstab["Loss"][gc_out] for gc_out in outcomes)
    if nq_win > 5 and nq_loss > 5:
        gc_wr_given_win = crosstab["Win"]["Win"] / nq_win
        gc_wr_given_loss = crosstab["Loss"]["Win"] / nq_loss
        diff = gc_wr_given_win - gc_wr_given_loss
        print(f"\n  Win-rate delta (P(GC wins|NQ wins) - P(GC wins|NQ loses)): {diff:+.1%}")
        if abs(diff) < 0.05:
            print(f"  → DIVERSIFICATION CONFIRMED: GC outcome is largely independent of NQ NY")
        elif diff > 0.05:
            print(f"  → POSITIVE CORRELATION: GC tends to win when NQ wins (concentration risk)")
        else:
            print(f"  → NEGATIVE CORRELATION: GC tends to win when NQ loses (good hedge)")


# ── SECTION 4 ─ Sequential Signal Analysis ───────────────────────────────────

def _print_bucket_table(title: str, buckets: dict[str, list[dict]], order: list[str]) -> None:
    print(f"  {title}")
    col_w = 9
    hdr = f"  {'Bucket':20s}{'Trades':>{col_w}s}{'WR':>{col_w}s}{'Avg R':>{col_w}s}{'Net R':>{col_w}s}"
    print(hdr)
    print(f"  {'─'*56}")
    for key in order:
        ts = buckets.get(key, [])
        if not ts:
            print(f"  {key:20s}{'0':>{col_w}s}{'—':>{col_w}s}{'—':>{col_w}s}{'—':>{col_w}s}")
            continue
        r = np.array([t["r_multiple"] for t in ts])
        conf = " †" if len(ts) < 50 else ""
        print(
            f"  {key:20s}{len(ts):>{col_w}d}"
            f"{(r>0).mean():>{col_w}.1%}"
            f"{np.mean(r):>{col_w}.3f}"
            f"{np.sum(r):>{col_w}.2f}"
            f"{conf}"
        )


def _print_comparison(baseline: list[dict], filtered: list[dict]) -> None:
    b, f = quick_metrics(baseline), quick_metrics(filtered)
    removed = b["n"] - f["n"]
    print(f"  {'':22s}{'Baseline':>12s}{'Filtered':>12s}{'Delta':>10s}")
    print(f"  {'─'*56}")
    print(f"  {'Trades':22s}{b['n']:>12d}{f['n']:>12d}{-removed:>+10d}")
    print(f"  {'Win Rate':22s}{b['wr']:>12.1%}{f['wr']:>12.1%}{(f['wr']-b['wr']):>+10.1%}")
    print(f"  {'Avg R':22s}{b['avg_r']:>12.3f}{f['avg_r']:>12.3f}{(f['avg_r']-b['avg_r']):>+10.3f}")
    print(f"  {'Net R':22s}{b['net_r']:>12.2f}{f['net_r']:>12.2f}{(f['net_r']-b['net_r']):>+10.2f}")
    print(f"  {'Calmar (INFO)':22s}{b['calmar']:>12.3f}{f['calmar']:>12.3f}{(f['calmar']-b['calmar']):>+10.3f}")
    if f["n"] < 50:
        print(f"  [LOW CONFIDENCE: filtered set has only {f['n']} trades]")


def _find_prev_trade(trade_date_str: str, trade_by_date: dict[str, dict],
                     max_days: int = 4) -> dict | None:
    """Return the most recent trade in trade_by_date within max_days before date_str."""
    d = date.fromisoformat(trade_date_str)
    for offset in range(1, max_days + 1):
        candidate = (d - timedelta(days=offset)).isoformat()
        if candidate in trade_by_date:
            return trade_by_date[candidate]
    return None


def section4_sequential(all_trades: dict[str, list[dict]]) -> None:
    sep("SECTION 4 — Sequential Signal Analysis (Information Cascade)")

    nq_asia_by_date = {t["date"]: t for t in all_trades["NQ_ASIA"]}
    es_ldn_by_date  = {t["date"]: t for t in all_trades["ES_LDN"]}
    nq_ny_by_date   = {t["date"]: t for t in all_trades["NQ_NY"]}
    gc_ny_by_date   = {t["date"]: t for t in all_trades["GC_NY"]}

    # ── 4A: ES LDN outcome → NQ NY performance ────────────────────────────────
    print(f"\n  4A — Does ES LDN predict NQ NY?")
    print(f"       (Same calendar date: ES LDN completes ~08:25 ET, NQ NY opens ~09:50 ET)\n")

    buckets_4a: dict[str, list[dict]] = {"ES_Win": [], "ES_Loss": [], "ES_NoTrade": []}
    for d, nq_t in sorted(nq_ny_by_date.items()):
        es_t = es_ldn_by_date.get(d)
        if es_t is None:
            buckets_4a["ES_NoTrade"].append(nq_t)
        elif es_t["r_multiple"] > 0:
            buckets_4a["ES_Win"].append(nq_t)
        else:
            buckets_4a["ES_Loss"].append(nq_t)

    _print_bucket_table("NQ NY performance by ES LDN outcome:", buckets_4a,
                        ["ES_Win", "ES_Loss", "ES_NoTrade"])

    print(f"\n  Simulation — Skip NQ NY when ES LDN lost (exit_type=sl):\n")
    es_sl_dates = {d for d, t in es_ldn_by_date.items() if t["exit_type"] == "sl"}
    baseline_nq_ny = list(nq_ny_by_date.values())
    filtered_nq_ny = [t for t in baseline_nq_ny if t["date"] not in es_sl_dates]
    _print_comparison(baseline_nq_ny, filtered_nq_ny)

    # ── 4B: NQ ASIA outcome → ES LDN performance ─────────────────────────────
    print(f"\n  4B — Does NQ ASIA predict ES LDN?")
    print(f"       (NQ ASIA date D fires ~20:00 ET → ES LDN fires morning of D+1)\n")

    buckets_4b: dict[str, list[dict]] = {"ASIA_Win": [], "ASIA_Loss": [], "ASIA_NoTrade": []}
    for d, es_t in sorted(es_ldn_by_date.items()):
        asia_t = _find_prev_trade(d, nq_asia_by_date, max_days=4)
        if asia_t is None:
            buckets_4b["ASIA_NoTrade"].append(es_t)
        elif asia_t["r_multiple"] > 0:
            buckets_4b["ASIA_Win"].append(es_t)
        else:
            buckets_4b["ASIA_Loss"].append(es_t)

    _print_bucket_table("ES LDN performance by NQ ASIA outcome (prior night):", buckets_4b,
                        ["ASIA_Win", "ASIA_Loss", "ASIA_NoTrade"])

    print(f"\n  Simulation — Skip ES LDN when NQ ASIA lost previous night (sl):\n")
    asia_sl_dates = {d for d, t in nq_asia_by_date.items() if t["exit_type"] == "sl"}
    # For each ES LDN trade, check if prior-night ASIA was an SL
    f3_skip_es: set[str] = set()
    for d in es_ldn_by_date:
        asia_t = _find_prev_trade(d, nq_asia_by_date, max_days=4)
        if asia_t is not None and asia_t["exit_type"] == "sl":
            f3_skip_es.add(d)
    baseline_es = list(es_ldn_by_date.values())
    filtered_es = [t for t in baseline_es if t["date"] not in f3_skip_es]
    _print_comparison(baseline_es, filtered_es)

    # ── 4C: NQ NY outcome → GC NY (exploratory) ───────────────────────────────
    print(f"\n  4C — Does NQ NY outcome correlate with GC NY final exit?")
    print(f"       (Exploratory — partial overlap in NY hours)\n")

    concurrent = sorted(set(nq_ny_by_date) & set(gc_ny_by_date))
    if len(concurrent) < 20:
        print(f"  Insufficient concurrent dates ({len(concurrent)}) for analysis — skipping.")
        return

    buckets_4c: dict[str, list[dict]] = {"NQ_Win": [], "NQ_Loss": [], "NQ_BE": []}
    for d in concurrent:
        out = trade_outcome(nq_ny_by_date[d])
        gc_t = gc_ny_by_date[d]
        if out == "Win":
            buckets_4c["NQ_Win"].append(gc_t)
        elif out == "Loss":
            buckets_4c["NQ_Loss"].append(gc_t)
        else:
            buckets_4c["NQ_BE"].append(gc_t)

    _print_bucket_table("GC NY performance given NQ NY outcome (same day):", buckets_4c,
                        ["NQ_Win", "NQ_Loss", "NQ_BE"])
    print(f"  († = < 50 trades, low confidence)")


# ── SECTION 5 ─ Regime-Conditional Performance ───────────────────────────────

def _vix_bucket(v: float) -> str:
    if v < 15:   return "VIX<15"
    elif v < 20: return "VIX 15-20"
    elif v < 25: return "VIX 20-25"
    elif v < 30: return "VIX 25-30"
    else:        return "VIX>30"


VIX_ORDER = ["VIX<15", "VIX 15-20", "VIX 20-25", "VIX 25-30", "VIX>30"]


def _print_regime_table(label: str, buckets: dict[str, list[float]],
                        bucket_order: list[str], col_w: int = 9) -> None:
    hdr = f"  {'Bucket':16s}{'Trades':>{col_w}s}{'WR':>{col_w}s}{'Avg R':>{col_w}s}{'Net R':>{col_w}s}"
    print(f"  Strategy: {label}")
    print(hdr)
    print(f"  {'─'*52}")
    for bk in bucket_order:
        rs = buckets.get(bk, [])
        if not rs:
            print(f"  {bk:16s}{'0':>{col_w}s}{'—':>{col_w}s}{'—':>{col_w}s}{'—':>{col_w}s}")
            continue
        r = np.array(rs)
        conf = " †" if len(rs) < 50 else ""
        print(
            f"  {bk:16s}{len(rs):>{col_w}d}"
            f"{(r>0).mean():>{col_w}.1%}"
            f"{np.mean(r):>{col_w}.3f}"
            f"{np.sum(r):>{col_w}.2f}"
            f"{conf}"
        )
    print()


def section5_regime(all_trades: dict[str, list[dict]], macro: dict[str, pd.Series]) -> None:
    sep("SECTION 5 — Regime-Conditional Performance (VIX / SPY / DXY)")

    vix = macro.get("VIX")
    spy = macro.get("SPY")
    dxy = macro.get("DXY")
    spy_sma20 = spy.rolling(20).mean() if spy is not None else None
    dxy_sma50 = dxy.rolling(50).mean() if dxy is not None else None

    # ── 5A: VIX buckets ───────────────────────────────────────────────────────
    if vix is None:
        print("\n  VIX data unavailable — skipping 5A/5D.")
    else:
        print(f"\n  5A — VIX Bucket Performance (prior-day VIX close)\n")
        for label in STRAT_ORDER:
            trades = all_trades[label]
            buckets: dict[str, list[float]] = defaultdict(list)
            missing = 0
            for t in trades:
                v = prior_close(vix, t["date"])
                if v is None:
                    missing += 1
                else:
                    buckets[_vix_bucket(v)].append(t["r_multiple"])
            if missing:
                print(f"  ({label}: {missing} trades missing VIX data)")
            _print_regime_table(label, buckets, VIX_ORDER)

    # ── 5B: SPY trend ─────────────────────────────────────────────────────────
    if spy is not None and spy_sma20 is not None:
        print(f"  5B — SPY Trend (prior-day close vs 20-day SMA)\n")
        for label in STRAT_ORDER:
            trades = all_trades[label]
            risk_on: list[float] = []
            risk_off: list[float] = []
            missing = 0
            for t in trades:
                s = prior_close(spy, t["date"])
                sma = prior_close(spy_sma20, t["date"])
                if s is None or sma is None:
                    missing += 1
                    continue
                if s >= sma:
                    risk_on.append(t["r_multiple"])
                else:
                    risk_off.append(t["r_multiple"])

            def _fmt(rs: list[float]) -> str:
                if not rs:
                    return f"{'0':>6s}  {'—':>7s}  {'—':>7s}  {'—':>8s}"
                r = np.array(rs)
                return f"{len(rs):>6d}  {(r>0).mean():>7.1%}  {np.mean(r):>7.3f}  {np.sum(r):>8.2f}"

            print(f"  {label}  ({missing} missing SPY)")
            print(f"  {'State':14s}{'Trades':>6s}  {'WR':>7s}  {'Avg R':>7s}  {'Net R':>8s}")
            print(f"  {'Risk-On (≥SMA)':14s}{_fmt(risk_on)}")
            print(f"  {'Risk-Off (<SMA)':14s}{_fmt(risk_off)}")
            print()
    else:
        print(f"\n  5B — SPY data unavailable — skipping.\n")

    # ── 5C: DXY trend (GC and ES only) ───────────────────────────────────────
    if dxy is not None and dxy_sma50 is not None:
        print(f"  5C — DXY Trend (prior-day close vs 50-day SMA) — GC and ES only\n")
        for label in ["GC_NY", "ES_LDN"]:
            trades = all_trades[label]
            strong_usd: list[float] = []
            weak_usd: list[float] = []
            missing = 0
            for t in trades:
                d_val = prior_close(dxy, t["date"])
                sma = prior_close(dxy_sma50, t["date"])
                if d_val is None or sma is None:
                    missing += 1
                    continue
                if d_val >= sma:
                    strong_usd.append(t["r_multiple"])
                else:
                    weak_usd.append(t["r_multiple"])

            def _fmt_dxy(rs: list[float]) -> str:
                if not rs:
                    return f"{'0':>6s}  {'—':>7s}  {'—':>7s}  {'—':>8s}"
                r = np.array(rs)
                return f"{len(rs):>6d}  {(r>0).mean():>7.1%}  {np.mean(r):>7.3f}  {np.sum(r):>8.2f}"

            print(f"  {label}  ({missing} missing DXY)")
            print(f"  {'State':22s}{'Trades':>6s}  {'WR':>7s}  {'Avg R':>7s}  {'Net R':>8s}")
            print(f"  {'DXY≥SMA50 (strong$)':22s}{_fmt_dxy(strong_usd)}")
            print(f"  {'DXY<SMA50 (weak$)':22s}{_fmt_dxy(weak_usd)}")
            print()
    else:
        print(f"  5C — DXY data unavailable — skipping.\n")

    # ── 5D: Cross-strategy avg R by VIX bucket ────────────────────────────────
    if vix is None:
        return

    print(f"  5D — Cross-Strategy Avg R by VIX Bucket (concentration risk)\n")
    table: dict[str, dict[str, tuple[float, int]]] = defaultdict(dict)
    for label in STRAT_ORDER:
        for t in all_trades[label]:
            v = prior_close(vix, t["date"])
            if v is None:
                continue
            bk = _vix_bucket(v)
            if label not in table[bk]:
                table[bk][label] = [0.0, 0]
            table[bk][label][0] += t["r_multiple"]
            table[bk][label][1] += 1

    col_w = 16
    header = f"  {'VIX Bucket':15s}" + "".join(f"{lbl:>{col_w}s}" for lbl in STRAT_ORDER)
    print(header)
    print(f"  {'─'*79}")
    for bk in VIX_ORDER:
        row = f"  {bk:15s}"
        for label in STRAT_ORDER:
            if label in table[bk]:
                total_r, n = table[bk][label]
                avg_r = total_r / n
                row += f"{avg_r:>+{col_w-5}.3f} (n={n:3d})"
            else:
                row += f"{'—':>{col_w}s}"
        print(row)
    print(f"  (values = avg R per trade, n = trade count in that bucket)")
    print(f"  († = < 50 trades per bucket)")


# ── SECTION 6 ─ Conditional Trade Filtering Simulation ───────────────────────

def section6_filters(
    all_trades: dict[str, list[dict]], macro: dict[str, pd.Series]
) -> list[tuple]:
    sep("SECTION 6 — Conditional Trade Filtering Simulation")

    nq_asia = list(all_trades["NQ_ASIA"])
    es_ldn  = list(all_trades["ES_LDN"])
    nq_ny   = list(all_trades["NQ_NY"])
    gc_ny   = list(all_trades["GC_NY"])

    nq_asia_by_date = {t["date"]: t for t in nq_asia}
    es_ldn_by_date  = {t["date"]: t for t in es_ldn}
    nq_ny_by_date   = {t["date"]: t for t in nq_ny}
    gc_ny_by_date   = {t["date"]: t for t in gc_ny}

    vix = macro.get("VIX")
    spy = macro.get("SPY")
    spy_sma20 = spy.rolling(20).mean() if spy is not None else None

    def portfolio_metrics(
        nqa: list[dict], es: list[dict], nqny: list[dict], gc: list[dict]
    ) -> dict:
        merged = nqa + es + nqny + gc
        merged.sort(key=lambda t: t["date"])
        return quick_metrics(merged)

    # Baseline
    base_m = portfolio_metrics(nq_asia, es_ldn, nq_ny, gc_ny)

    # Precompute ES LDN SL dates
    es_sl_dates = {d for d, t in es_ldn_by_date.items() if t["exit_type"] == "sl"}

    # Precompute NQ ASIA prior-night SL indicator for each NQ NY / ES LDN trade
    def asia_sl_night_before(trade_date: str) -> bool:
        asia_t = _find_prev_trade(trade_date, nq_asia_by_date, max_days=4)
        return asia_t is not None and asia_t["exit_type"] == "sl"

    filters: list[tuple[str, str, dict]] = []

    # F1 — Skip NQ NY when ES LDN lost (sl) same morning
    f1_nq_ny = [t for t in nq_ny if t["date"] not in es_sl_dates]
    filters.append(("F1", "Skip NQ NY when ES LDN=sl same morning",
                    portfolio_metrics(nq_asia, es_ldn, f1_nq_ny, gc_ny)))

    # F2 — Skip NQ NY when NQ ASIA lost (sl) previous night
    f2_nq_ny = [t for t in nq_ny if not asia_sl_night_before(t["date"])]
    filters.append(("F2", "Skip NQ NY when NQ ASIA=sl prev night",
                    portfolio_metrics(nq_asia, es_ldn, f2_nq_ny, gc_ny)))

    # F3 — Skip ES LDN when NQ ASIA lost (sl) previous night
    f3_es = [t for t in es_ldn if not asia_sl_night_before(t["date"])]
    filters.append(("F3", "Skip ES LDN when NQ ASIA=sl prev night",
                    portfolio_metrics(nq_asia, f3_es, nq_ny, gc_ny)))

    # F4 — Skip ES LDN + NQ NY when VIX_prev > 25
    if vix is not None:
        f4_es   = [t for t in es_ldn if (lambda v: v is None or v <= 25)(prior_close(vix, t["date"]))]
        f4_nqny = [t for t in nq_ny  if (lambda v: v is None or v <= 25)(prior_close(vix, t["date"]))]
        filters.append(("F4", "Skip ES LDN + NQ NY when VIX_prev>25",
                        portfolio_metrics(nq_asia, f4_es, f4_nqny, gc_ny)))
    else:
        print(f"\n  F4/F5 skipped — VIX data unavailable.")

    # F5 — Skip NQ NY when VIX_prev > 25 AND SPY_prev < SMA20
    if vix is not None and spy is not None and spy_sma20 is not None:
        def f5_keep(t: dict) -> bool:
            v = prior_close(vix, t["date"])
            s = prior_close(spy, t["date"])
            sma = prior_close(spy_sma20, t["date"])
            if v is None or s is None or sma is None:
                return True
            return not (v > 25 and s < sma)

        f5_nqny = [t for t in nq_ny if f5_keep(t)]
        filters.append(("F5", "Skip NQ NY when VIX>25 AND SPY<SMA20",
                        portfolio_metrics(nq_asia, es_ldn, f5_nqny, gc_ny)))

    # F6 — Double GC NY sizing when NQ NY loses same day
    concurrent = set(nq_ny_by_date) & set(gc_ny_by_date)
    nq_loss_dates = {d for d in concurrent if nq_ny_by_date[d]["r_multiple"] < 0}
    f6_gc: list[dict] = []
    for t in gc_ny:
        f6_gc.append(t)
        if t["date"] in nq_loss_dates:
            f6_gc.append(t)  # double the position (additive R)
    filters.append(("F6", "Double GC NY sizing when NQ NY=loss same day",
                    portfolio_metrics(nq_asia, es_ldn, nq_ny, f6_gc)))

    # ── Print results ──────────────────────────────────────────────────────────
    print(f"\n  Baseline portfolio: {base_m['n']} trades | "
          f"WR {base_m['wr']:.1%} | Net R {base_m['net_r']:.2f} | "
          f"Calmar (INFO) {base_m['calmar']:.3f}\n")

    col_w = 10
    hdr = (f"  {'Filter':6s}  {'Trades':>{col_w}s}{'WR':>{col_w}s}"
           f"{'Avg R':>{col_w}s}{'Net R':>{col_w}s}{'Calmar':>{col_w}s}{'ΔCalmar':>{col_w}s}"
           f"  Description")
    print(hdr)
    print(f"  {'─'*100}")

    b = base_m
    print(f"  {'BASE':6s}  {b['n']:>{col_w}d}{b['wr']:>{col_w}.1%}"
          f"{b['avg_r']:>{col_w}.3f}{b['net_r']:>{col_w}.2f}"
          f"{b['calmar']:>{col_w}.3f}{'—':>{col_w}s}  Baseline (no filters)")

    summary_rows: list[tuple[str, str, float, int]] = []
    for name, desc, m in filters:
        delta_calmar = m["calmar"] - b["calmar"]
        conf = " †" if m["n"] < 50 else ""
        print(
            f"  {name:6s}  {m['n']:>{col_w}d}{m['wr']:>{col_w}.1%}"
            f"{m['avg_r']:>{col_w}.3f}{m['net_r']:>{col_w}.2f}"
            f"{m['calmar']:>{col_w}.3f}{delta_calmar:>+{col_w}.3f}"
            f"  {desc}{conf}"
        )
        summary_rows.append((name, desc, delta_calmar, m["n"]))

    print(f"\n  † = < 50 trades in filtered portfolio  |  Calmar is informational only")
    return summary_rows


# ── SECTION 7 ─ Summary & Recommendations ────────────────────────────────────

def section7_summary(
    all_trades: dict[str, list[dict]], filter_summary: list[tuple]
) -> None:
    sep("SECTION 7 — Summary & Recommendations")

    # Diversification score
    df = build_monthly_df(all_trades)
    n = len(STRAT_ORDER)
    corr_values: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            x, y = df[STRAT_ORDER[i]], df[STRAT_ORDER[j]]
            mask = x.notna() & y.notna()
            if mask.sum() >= 10:
                r, _ = pearsonr(x[mask].values, y[mask].values)
                if not math.isnan(r):
                    corr_values.append(abs(r))

    avg_abs_corr = float(np.mean(corr_values)) if corr_values else 0.0
    div_score = 1.0 - avg_abs_corr
    quality = "excellent" if div_score > 0.85 else "good" if div_score > 0.70 else "moderate"
    print(f"\n  Cross-asset diversification score:  {div_score:.3f}  "
          f"(avg pairwise |r| = {avg_abs_corr:.3f})  [{quality}]")

    # Compute baseline calmar for % improvement
    all_combined = [t for trades in all_trades.values() for t in trades]
    base_calmar = quick_metrics(all_combined)["calmar"]

    # Filter improvements
    print(f"\n  Filters sorted by Calmar improvement:\n")
    col_w = 10
    hdr = f"  {'Filter':6s}  {'ΔCalmar':>10s}{'%Improv':>10s}{'Trades':>8s}  Description"
    print(hdr)
    print(f"  {'─'*72}")
    best_filter: tuple | None = None
    best_delta = 0.0

    for name, desc, delta_calmar, n_trades in sorted(
        filter_summary, key=lambda x: x[2], reverse=True
    ):
        pct = delta_calmar / base_calmar * 100 if base_calmar > 0 else 0.0
        conf = " †" if n_trades < 50 else ""
        marker = "***" if pct > 10.0 else "   "
        print(f"  {marker} {name:4s}  {delta_calmar:>+10.3f}{pct:>+9.1f}%{n_trades:>8d}  {desc}{conf}")
        if delta_calmar > best_delta:
            best_delta = delta_calmar
            best_filter = (name, desc, delta_calmar)

    if best_filter and best_filter[2] > 0:
        pct_best = best_filter[2] / base_calmar * 100 if base_calmar > 0 else 0.0
        print(f"\n  Top finding: The most valuable cross-asset signal is:")
        print(f"    {best_filter[0]}: {best_filter[1]}")
        print(f"    (Calmar delta: {best_filter[2]:+.3f} / {pct_best:+.1f}% improvement)")
    else:
        print(f"\n  No filter improved portfolio Calmar — baseline may already be well-optimized.")

    print(f"\n  Sample-size caution:")
    print(f"    † Any finding labelled with † has < 50 supporting trades and is LOW CONFIDENCE.")
    print(f"    Recommendations with n > 100 are suitable for live deployment.")
    print(f"    Recommendations with 50 ≤ n ≤ 100 warrant paper-trading confirmation.")
    sep()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    sep("4-WAY PORTFOLIO: CROSS-ASSET DEEP ANALYSIS", "═")
    print(f"\n  NQ ASIA (6718) | ES LDN (6707) | NQ NY (6717) | GC NY (6693)\n")

    print("  Loading trades from DB ...")
    all_trades = load_trades()

    total = sum(len(v) for v in all_trades.values())
    if total == 0:
        print("ERROR: No trades loaded — aborting.")
        sys.exit(1)

    print(f"\n  Loading macro regime data ...")
    macro = load_macro()

    section1_correlation(all_trades)
    section2_rolling(all_trades)
    section3_concurrent(all_trades)
    section4_sequential(all_trades)
    section5_regime(all_trades, macro)
    filter_summary = section6_filters(all_trades, macro)
    section7_summary(all_trades, filter_summary)


if __name__ == "__main__":
    main()
