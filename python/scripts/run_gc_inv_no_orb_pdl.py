#!/usr/bin/env python3
"""No-ORB GC — prior day's low sweep filter.

Additional gate on top of QM=100%: the session's qualifying sweep must also
take out the prior day's low (price grabs liquidity from prior structure).

Approach: run base no-ORB backtest, then filter trades where the session low
(09:35-16:45) on trade date was <= prior trading day's session low.

Fixed: QM=100%, stop=12%, rr=5.0, BE=0, tp1=0.2, entry→16:45, longs.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED  = ("20241218",)


def make_config():
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="16:45",
        flat_start="16:45", flat_end="16:50",
        stop_atr_pct=12.0, min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=5.0, tp1_ratio=0.2, risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=EXCLUDED,
    )


def build_session_lows(df: pd.DataFrame) -> dict[str, float]:
    """Compute session low (09:30-16:45 ET) per trading date from 5m data."""
    mask = (df.index.time >= pd.Timestamp("09:30").time()) & \
           (df.index.time <= pd.Timestamp("16:45").time())
    session = df[mask].copy()
    session["date_str"] = session.index.strftime("%Y-%m-%d")
    return session.groupby("date_str")["low"].min().to_dict()


def print_stats(label: str, filled: list, hdr: str) -> None:
    if len(filled) < 5:
        print(f"\n{label}: only {len(filled)} trades — insufficient")
        return
    m = compute_metrics(filled)
    dd = round(m["max_drawdown_r"], 1)
    nr = round(m["total_r"], 1)
    yearly = defaultdict(list)
    for t in filled:
        yearly[t.date[:4]].append(t.r_multiple)
    monthly = defaultdict(list)
    for t in filled:
        monthly[t.date[:7]].append(t.r_multiple)
    wm = min((sum(v) for v in monthly.values()), default=0)

    print(f"\n{'='*75}")
    print(f"{label}")
    print(f"{'='*75}")
    print(f"  Trades: {m['total_trades']}  |  WR: {m['win_rate']:.1%}  |  "
          f"Net R: {nr}  |  Max DD: {dd}R")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f}  |  PF: {m['profit_factor']:.2f}  |  "
          f"Worst month: {wm:.1f}R  |  MCL: {m['max_consecutive_losses']}")
    print(f"  Yearly:")
    for yr in sorted(yearly):
        print(f"    {yr}: {sum(yearly[yr]):+.1f}R  ({len(yearly[yr])} trades)")


def main():
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars")

    # Build prior day's low lookup
    session_lows = build_session_lows(df)
    sorted_dates = sorted(session_lows.keys())
    prior_day_low = {}
    for i, d in enumerate(sorted_dates):
        if i > 0:
            prior_day_low[d] = session_lows[sorted_dates[i - 1]]

    t0 = time.time()
    cfg = make_config()
    trades = run_backtest_no_orb(df, cfg, start_date="2016-01-01", df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    print(f"\nBase no-ORB: {len(filled)} filled trades  ({time.time()-t0:.0f}s)")

    # Filter 1: session low <= prior day's low
    pdl_filtered = [
        t for t in filled
        if t.date in prior_day_low
        and session_lows.get(t.date, float("inf")) <= prior_day_low[t.date]
    ]
    pdl_excluded = [t for t in filled if t not in pdl_filtered]

    hdr = f"{'Metric':<18} | {'Value':>10}"

    print_stats(
        "BASE (QM=100%, no PDL filter)",
        filled, hdr,
    )
    print_stats(
        "PDL FILTER: session low <= prior day's low",
        pdl_filtered, hdr,
    )
    print_stats(
        "EXCLUDED by PDL filter (session low > prior day's low)",
        pdl_excluded, hdr,
    )

    # Quick percentage breakdown
    print(f"\n{'='*75}")
    print(f"FILTER IMPACT")
    print(f"{'='*75}")
    print(f"  Base trades:    {len(filled)}")
    print(f"  PDL filtered:   {len(pdl_filtered)} ({len(pdl_filtered)/len(filled):.1%} kept)")
    print(f"  PDL excluded:   {len(pdl_excluded)} ({len(pdl_excluded)/len(filled):.1%} removed)")
    if len(pdl_filtered) >= 5 and len(filled) >= 5:
        m_base = compute_metrics(filled)
        m_filt = compute_metrics(pdl_filtered)
        print(f"\n  WR:     {m_base['win_rate']:.1%} → {m_filt['win_rate']:.1%}")
        print(f"  Net R:  {m_base['total_r']:.1f} → {m_filt['total_r']:.1f}")
        print(f"  Max DD: {m_base['max_drawdown_r']:.1f}R → {m_filt['max_drawdown_r']:.1f}R")
        print(f"  Sharpe: {m_base['sharpe_ratio']:.3f} → {m_filt['sharpe_ratio']:.3f}")

    print(f"\nv9 baseline: 250 trades, 74.7R, -5.2R DD, Sharpe 3.80")


if __name__ == "__main__":
    main()
