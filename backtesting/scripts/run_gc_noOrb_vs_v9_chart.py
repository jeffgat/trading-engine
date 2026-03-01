#!/usr/bin/env python3
"""Compare no-ORB liquidity sweep vs v9 regime-sized equity curves.

No-ORB model: QM=100%, stop=12%, rr=5.0, BE=0, tp1=0.2, entry→16:45 (prop window)
v9 regime-sized: QM=10%, stop=9%, rr=3.5, BE=0, tp1=0.2, 2x sizing VIX<18+DXY<SMA50
"""

import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_no_orb, run_backtest_qm
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED  = ("20241218",)
START     = "2016-01-01"


# ── Regime lookup for v9 sizing ──────────────────────────────────────────────

def build_regime_lookup():
    vix_df = pd.read_csv(DATA_DIR / "VIX_daily.csv", index_col=0, parse_dates=True)
    dxy_df = pd.read_csv(DATA_DIR / "DXY_daily.csv", index_col=0, parse_dates=True)
    vix_close = vix_df["Close"].dropna()
    dxy_close = dxy_df["Close"].dropna()
    dxy_sma50 = dxy_close.rolling(50).mean()

    lookup = {}
    for d in sorted(set(vix_close.index.date) | set(dxy_close.index.date)):
        ts = pd.Timestamp(d)
        lookup[str(d)] = {
            "vix": float(vix_close.loc[ts]) if ts in vix_close.index else np.nan,
            "dxy": float(dxy_close.loc[ts]) if ts in dxy_close.index else np.nan,
            "dxy_sma50": float(dxy_sma50.loc[ts]) if ts in dxy_sma50.index and not np.isnan(dxy_sma50.loc[ts]) else np.nan,
        }

    sorted_dates = sorted(lookup.keys())
    shifted = {}
    for i, d in enumerate(sorted_dates):
        shifted[d] = lookup[sorted_dates[i - 1]] if i > 0 else {"vix": np.nan, "dxy": np.nan, "dxy_sma50": np.nan}
    return shifted


def is_favorable(r):
    if r is None:
        return False
    vix, dxy, sma50 = r.get("vix", np.nan), r.get("dxy", np.nan), r.get("dxy_sma50", np.nan)
    return not any(np.isnan(x) for x in [vix, dxy, sma50]) and vix < 18 and dxy < sma50


# ── Run models ───────────────────────────────────────────────────────────────

def run_no_orb(df, df_1m):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="16:45",
        flat_start="16:45", flat_end="16:50",
        stop_atr_pct=12.0, min_gap_atr_pct=1.0,
    )
    cfg = StrategyConfig(
        rr=5.0, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )
    trades = run_backtest_no_orb(df, cfg, start_date=START, df_1m=df_1m)
    return [t for t in trades if t.exit_type != EXIT_NO_FILL]


def run_v9_regime(df, df_1m, regime):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=9.0, min_gap_atr_pct=1.0,
    )
    cfg = StrategyConfig(
        rr=3.5, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )
    trades = run_backtest_qm(df, cfg, start_date=START, df_1m=df_1m)
    sized = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        if is_favorable(regime.get(t.date)):
            sized.append(t._replace(r_multiple=t.r_multiple * 2.0))
        else:
            sized.append(t)
    return sized


# ── Chart ────────────────────────────────────────────────────────────────────

def equity_curve(trades):
    rs = [t.r_multiple for t in sorted(trades, key=lambda t: t.date)]
    return np.cumsum(rs)


def yearly_r(trades):
    by_year = defaultdict(float)
    for t in trades:
        by_year[t.date[:4]] += t.r_multiple
    return dict(sorted(by_year.items()))


def fmt_metrics(trades, label):
    m = compute_metrics(trades)
    monthly = defaultdict(list)
    for t in trades:
        monthly[t.date[:7]].append(t.r_multiple)
    worst_month = min((sum(v) for v in monthly.values()), default=0)
    return (
        f"{label}\n"
        f"Trades: {m['total_trades']}  |  WR: {m['win_rate']:.1%}  |  Net R: {m['total_r']:.1f}\n"
        f"Sharpe: {m['sharpe_ratio']:.3f}  |  Max DD: {m['max_drawdown_r']:.1f}R  |  Worst mo: {worst_month:.1f}R"
    )


def main():
    print("Loading data...")
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    regime = build_regime_lookup()

    print("Running no-ORB model...")
    no_orb = run_no_orb(df, df_1m)
    print(f"  {len(no_orb)} filled trades")

    print("Running v9 regime-sized model...")
    v9 = run_v9_regime(df, df_1m, regime)
    print(f"  {len(v9)} filled trades")

    # Equity curves
    eq_no_orb = equity_curve(no_orb)
    eq_v9     = equity_curve(v9)

    # Yearly
    yr_no_orb = yearly_r(no_orb)
    yr_v9     = yearly_r(v9)
    all_years = sorted(set(yr_no_orb) | set(yr_v9))

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(16, 10), facecolor="#0d0d0f")
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.3,
                            left=0.07, right=0.97, top=0.88, bottom=0.08)

    C_NORB = "#a78bfa"   # purple — no-ORB
    C_V9   = "#34d399"   # green  — v9 regime
    C_GRID = "#1f1f23"
    C_TEXT = "#e4e4e7"
    C_MUTED= "#71717a"

    plt.rcParams.update({
        "text.color": C_TEXT, "axes.labelcolor": C_TEXT,
        "xtick.color": C_MUTED, "ytick.color": C_MUTED,
        "axes.facecolor": "#111113", "axes.edgecolor": "#27272a",
        "grid.color": C_GRID, "grid.linewidth": 0.5,
        "font.family": "monospace",
    })

    # ── Equity curves (top, spanning both columns) ────────────────────────
    ax_eq = fig.add_subplot(gs[0, :])
    ax_eq.set_facecolor("#111113")
    ax_eq.plot(eq_v9,     color=C_V9,   linewidth=1.8, label="v9 Regime-Sized", zorder=3)
    ax_eq.plot(eq_no_orb, color=C_NORB, linewidth=1.8, label="No-ORB Liq. Sweep", zorder=3)
    ax_eq.axhline(0, color="#3f3f46", linewidth=0.8)
    ax_eq.set_title("Cumulative Equity — GC Inversion Longs", fontsize=13,
                    color=C_TEXT, pad=10, fontweight="bold")
    ax_eq.set_ylabel("Cumulative R", fontsize=10)
    ax_eq.set_xlabel("Trade #", fontsize=10)
    ax_eq.grid(True, axis="y")
    ax_eq.legend(fontsize=10, facecolor="#18181b", edgecolor="#3f3f46",
                 labelcolor=C_TEXT, framealpha=0.9)

    # Drawdown shading
    for eq, color in [(eq_v9, C_V9), (eq_no_orb, C_NORB)]:
        running_max = np.maximum.accumulate(eq)
        dd = eq - running_max
        ax_eq.fill_between(range(len(dd)), dd + running_max, running_max,
                           where=dd < 0, alpha=0.08, color=color, zorder=1)

    # ── Yearly bar chart (bottom-left) ────────────────────────────────────
    ax_yr = fig.add_subplot(gs[1, 0])
    ax_yr.set_facecolor("#111113")
    x = np.arange(len(all_years))
    w = 0.38
    bars_v9    = [yr_v9.get(y, 0) for y in all_years]
    bars_norb  = [yr_no_orb.get(y, 0) for y in all_years]

    for i, (bv, bn) in enumerate(zip(bars_v9, bars_norb)):
        ax_yr.bar(x[i] - w/2, bv, width=w, color=C_V9,   alpha=0.85,
                  edgecolor="#18181b", linewidth=0.4)
        ax_yr.bar(x[i] + w/2, bn, width=w, color=C_NORB, alpha=0.85,
                  edgecolor="#18181b", linewidth=0.4)

    ax_yr.axhline(0, color="#3f3f46", linewidth=0.8)
    ax_yr.set_xticks(x)
    ax_yr.set_xticklabels(all_years, rotation=45, ha="right", fontsize=8)
    ax_yr.set_title("Annual R by Year", fontsize=11, color=C_TEXT, pad=8)
    ax_yr.set_ylabel("R", fontsize=9)
    ax_yr.grid(True, axis="y")
    ax_yr.legend(["v9 Regime-Sized", "No-ORB Liq. Sweep"],
                 fontsize=8, facecolor="#18181b", edgecolor="#3f3f46",
                 labelcolor=C_TEXT, framealpha=0.9)

    # ── Metrics table (bottom-right) ──────────────────────────────────────
    ax_tbl = fig.add_subplot(gs[1, 1])
    ax_tbl.set_facecolor("#111113")
    ax_tbl.axis("off")

    m_v9    = compute_metrics(v9)
    m_norb  = compute_metrics(no_orb)

    monthly_v9   = defaultdict(list)
    monthly_norb = defaultdict(list)
    for t in v9:
        monthly_v9[t.date[:7]].append(t.r_multiple)
    for t in no_orb:
        monthly_norb[t.date[:7]].append(t.r_multiple)
    wm_v9   = min((sum(v) for v in monthly_v9.values()),   default=0)
    wm_norb = min((sum(v) for v in monthly_norb.values()), default=0)

    rows = [
        ["Metric",          "v9 Regime-Sized",                       "No-ORB Liq. Sweep"],
        ["Trades",          str(m_v9["total_trades"]),                str(m_norb["total_trades"])],
        ["Win Rate",        f"{m_v9['win_rate']:.1%}",                f"{m_norb['win_rate']:.1%}"],
        ["Net R",           f"{m_v9['total_r']:.1f}",                 f"{m_norb['total_r']:.1f}"],
        ["Max DD",          f"{m_v9['max_drawdown_r']:.1f}R",         f"{m_norb['max_drawdown_r']:.1f}R"],
        ["Sharpe",          f"{m_v9['sharpe_ratio']:.3f}",            f"{m_norb['sharpe_ratio']:.3f}"],
        ["Profit Factor",   f"{m_v9['profit_factor']:.2f}",           f"{m_norb['profit_factor']:.2f}"],
        ["Worst Month",     f"{wm_v9:.1f}R",                          f"{wm_norb:.1f}R"],
        ["Max Consec. L",   str(m_v9["max_consecutive_losses"]),      str(m_norb["max_consecutive_losses"])],
        ["Avg R/trade",     f"{m_v9['avg_r']:.3f}",                  f"{m_norb['avg_r']:.3f}"],
    ]

    tbl = ax_tbl.table(
        cellText=rows[1:],
        colLabels=rows[0],
        cellLoc="center",
        loc="center",
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)

    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("#27272a")
        if row == 0:
            cell.set_facecolor("#1c1c1f")
            cell.set_text_props(color=C_TEXT, fontweight="bold")
        elif col == 1:
            cell.set_facecolor("#0f1f18")
            cell.set_text_props(color=C_V9)
        elif col == 2:
            cell.set_facecolor("#13101f")
            cell.set_text_props(color=C_NORB)
        else:
            cell.set_facecolor("#111113")
            cell.set_text_props(color=C_MUTED)

    ax_tbl.set_title("Performance Metrics", fontsize=11, color=C_TEXT, pad=8)

    # Subtitle
    fig.text(0.5, 0.925,
             "GC NY Inversion Longs  ·  2016–2026  ·  $5,000 risk/trade",
             ha="center", fontsize=10, color=C_MUTED)

    out = Path(__file__).resolve().parent.parent / "data" / "results" / "gc_noOrb_vs_v9.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"\nChart saved → {out}")
    plt.show()


if __name__ == "__main__":
    main()
