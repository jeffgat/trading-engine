#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 15: regime-switched L+S.

Insight: Shorts add the most value when longs are weakest (2022-2023).
Can we find an environmental signal to know WHEN to add shorts?

Approach:
  1. Always trade longs (robust across all regimes, Calmar 17.17)
  2. Run short trades through env filter analysis to find when shorts work
  3. Test regime-switched combined: Long always + Short only when [condition]
  4. Compare against long-only and always-combined baselines

Long:  g=3.0 rr=2.25 tp1=0.7 stop=9.0% entry_end=15:00 (16.5 R/yr, DD -10.6R)
Short: g=1.0 rr=1.25 tp1=0.5 stop=9.0% entry_end=14:00 (from R14 sweet spot)
"""

import sys
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
DATA_YEARS = 11
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def make_long_config():
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=3.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.25,
        tp1_ratio=0.7,
        atr_length=14,
        name="NQ NY Long",
    )


def make_short_config():
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="14:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=1.25,
        tp1_ratio=0.5,
        atr_length=14,
        name="NQ NY Short",
    )


def combine_trades(long_trades, short_trades):
    """Merge L+S, one trade per day (first to fill wins)."""
    long_filled = {t.date: t for t in long_trades if t.exit_type != EXIT_NO_FILL}
    short_filled = {t.date: t for t in short_trades if t.exit_type != EXIT_NO_FILL}

    all_dates = sorted(set(long_filled.keys()) | set(short_filled.keys()))
    combined = []
    for d in all_dates:
        lt = long_filled.get(d)
        st = short_filled.get(d)
        if lt and st:
            combined.append(lt if lt.fill_bar <= st.fill_bar else st)
        elif lt:
            combined.append(lt)
        elif st:
            combined.append(st)
    return combined


def regime_combine(long_trades, short_trades, env_lookup, short_condition):
    """Always trade longs. Only add shorts when short_condition(env) is True.

    When both exist on a day and short is allowed, first-to-fill wins.
    When short is not allowed, only the long trades.
    """
    long_filled = {t.date: t for t in long_trades if t.exit_type != EXIT_NO_FILL}
    short_filled = {t.date: t for t in short_trades if t.exit_type != EXIT_NO_FILL}

    all_dates = sorted(set(long_filled.keys()) | set(short_filled.keys()))
    combined = []
    shorts_taken = 0
    shorts_blocked = 0

    for d in all_dates:
        lt = long_filled.get(d)
        st = short_filled.get(d)
        env = env_lookup.get(d)

        # Check if shorts are allowed today
        short_allowed = False
        if env is not None:
            try:
                short_allowed = short_condition(env)
            except (TypeError, ValueError):
                short_allowed = False

        if lt and st and short_allowed:
            # Both available and shorts allowed — first to fill
            if lt.fill_bar <= st.fill_bar:
                combined.append(lt)
            else:
                combined.append(st)
                shorts_taken += 1
        elif lt:
            combined.append(lt)
            if st and not short_allowed:
                shorts_blocked += 1
        elif st and short_allowed:
            combined.append(st)
            shorts_taken += 1
        elif st:
            shorts_blocked += 1

    return combined, shorts_taken, shorts_blocked


# ── ENV DATA ─────────────────────────────────────────────────────────────

def load_daily_csv(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)


def build_env_lookup(frames):
    """Build date → env dict using prior day's close (no look-ahead)."""
    series = {}
    for name, col in [("vix", "VIX"), ("spy", "SPY"), ("tnx", "TNX"), ("dxy", "DXY")]:
        if col in frames and frames[col] is not None:
            close = frames[col]["Close"].dropna()
            series[name] = close
            series[f"{name}_sma20"] = close.rolling(20).mean()
            series[f"{name}_sma50"] = close.rolling(50).mean()
            series[f"{name}_sma200"] = close.rolling(200).mean()

    all_dates = set()
    for s in series.values():
        all_dates |= set(s.index.date)
    all_dates = sorted(all_dates)

    lookup = {}
    last = {k: np.nan for k in series}
    for d in all_dates:
        ts = pd.Timestamp(d)
        for k, s in series.items():
            if ts in s.index:
                val = s.loc[ts]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                val = float(val)
                if not np.isnan(val):
                    last[k] = val
        lookup[str(d)] = dict(last)

    # Shift by 1 day
    shifted = {}
    sorted_dates = sorted(lookup.keys())
    for i, d in enumerate(sorted_dates):
        shifted[d] = lookup[sorted_dates[i - 1]] if i > 0 else {k: np.nan for k in series}
    return shifted


# ── OUTPUT ───────────────────────────────────────────────────────────────

HDR = (f"    {'Config':>50s}  {'N':>5s}  {'WR':>5s}  {'Net R':>7s}  "
       f"{'R/yr':>6s}  {'PF':>5s}  {'DD':>6s}  {'Calmar':>7s}  {'S taken':>7s}")


def print_header(title):
    print(f"\n{'='*110}")
    print(f"  {title}")
    print(f"{'='*110}")
    print(HDR)
    print(f"    {'─' * 105}")


def print_row(label, m, shorts_taken=None, marker=""):
    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
    s_str = f"{shorts_taken:>7d}" if shorts_taken is not None else "      -"
    print(f"    {label:>50s}  {m['total_trades']:>5d}  {m['win_rate']:>5.1%}  "
          f"{m['total_r']:>7.1f}  {r_yr:>6.1f}  {m['profit_factor']:>5.2f}  "
          f"{m['max_drawdown_r']:>6.1f}  {m['calmar_ratio']:>7.2f}  {s_str}{marker}")


def print_years(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"      R by year: {yr_str}")


def main():
    print("NQ NY ORB — Round 15: Regime-Switched L+S")
    print("Always Long + Short only when environment favors it")
    print("=" * 110)

    # ── Load data
    print("\nLoading NQ data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    # ── Run both directions
    print("\nRunning backtests...")
    long_trades = run_backtest(df_5m, make_long_config(), start_date=START_DATE, df_1m=df_1m)
    short_trades = run_backtest(df_5m, make_short_config(), start_date=START_DATE, df_1m=df_1m)

    long_filled = [t for t in long_trades if t.exit_type != EXIT_NO_FILL]
    short_filled = [t for t in short_trades if t.exit_type != EXIT_NO_FILL]
    print(f"  Long filled: {len(long_filled)} | Short filled: {len(short_filled)}")

    # ── Load env data
    print("\nLoading environmental data...")
    frames = {
        "VIX": load_daily_csv("VIX_daily.csv"),
        "SPY": load_daily_csv("SPY_daily.csv"),
        "TNX": load_daily_csv("TNX_daily.csv"),
        "DXY": load_daily_csv("DXY_daily.csv"),
    }
    env = build_env_lookup(frames)
    print(f"  Env dates: {len(env)}")

    # ── Baselines
    m_long = compute_metrics(long_trades)
    m_short = compute_metrics(short_trades)
    combined_always = combine_trades(long_trades, short_trades)
    m_combined = compute_metrics(combined_always)

    print_header("BASELINES")
    print_row("Long only", m_long, marker=" <-- anchor")
    print_years(m_long)
    print_row("Short only", m_short)
    print_years(m_short)
    print_row("Combined always (L+S)", m_combined,
              shorts_taken=len([t for t in combined_always if t.direction == -1]))
    print_years(m_combined)

    # ══════════════════════════════════════════════════════════════════════
    # 1. ANALYZE SHORT TRADES BY ENVIRONMENT
    # ══════════════════════════════════════════════════════════════════════
    print_header("1. SHORT-ONLY TRADES SPLIT BY ENVIRONMENT")
    print(f"    (Which conditions make shorts profitable?)\n")

    def analyze_short_env(label, condition):
        """Split short-only trades by env condition."""
        in_trades = []
        out_trades = []
        for t in short_filled:
            e = env.get(t.date)
            if e is None:
                continue
            try:
                if condition(e):
                    in_trades.append(t)
                else:
                    out_trades.append(t)
            except (TypeError, ValueError):
                continue

        m_in = compute_metrics(in_trades) if in_trades else None
        m_out = compute_metrics(out_trades) if out_trades else None

        in_ryr = m_in["total_r"] / DATA_YEARS if m_in and m_in["total_trades"] > 0 else 0
        out_ryr = m_out["total_r"] / DATA_YEARS if m_out and m_out["total_trades"] > 0 else 0
        in_avg = m_in["avg_r"] if m_in and m_in["total_trades"] > 0 else 0
        out_avg = m_out["avg_r"] if m_out and m_out["total_trades"] > 0 else 0
        in_n = m_in["total_trades"] if m_in else 0
        out_n = m_out["total_trades"] if m_out else 0

        print(f"    {label}")
        print(f"      IN:  {in_n:>5d} trades, {in_ryr:>5.1f} R/yr, avg {in_avg:>+.3f}R"
              f"{'  <-- shorts work here' if in_avg > 0.05 else ''}")
        print(f"      OUT: {out_n:>5d} trades, {out_ryr:>5.1f} R/yr, avg {out_avg:>+.3f}R"
              f"{'  <-- shorts work here' if out_avg > 0.05 else ''}")
        print()
        return condition

    # VIX-based
    analyze_short_env("VIX > 20 (elevated vol)",
                      lambda e: e.get("vix", np.nan) > 20)
    analyze_short_env("VIX > 25 (high vol)",
                      lambda e: e.get("vix", np.nan) > 25)
    analyze_short_env("VIX > SMA20 (rising vol)",
                      lambda e: e.get("vix", np.nan) > e.get("vix_sma20", np.nan))
    analyze_short_env("VIX > SMA50 (high regime)",
                      lambda e: e.get("vix", np.nan) > e.get("vix_sma50", np.nan))

    # SPY-based
    analyze_short_env("SPY < SMA20 (risk-off)",
                      lambda e: e.get("spy", np.nan) < e.get("spy_sma20", np.nan))
    analyze_short_env("SPY < SMA50 (risk-off)",
                      lambda e: e.get("spy", np.nan) < e.get("spy_sma50", np.nan))
    analyze_short_env("SPY < SMA200 (bear market)",
                      lambda e: e.get("spy", np.nan) < e.get("spy_sma200", np.nan))

    # TNX-based (rising rates = bearish for tech)
    analyze_short_env("TNX > SMA20 (rising yields)",
                      lambda e: e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan))
    analyze_short_env("TNX > SMA50 (rising yields)",
                      lambda e: e.get("tnx", np.nan) > e.get("tnx_sma50", np.nan))

    # DXY-based (strong dollar = risk-off)
    analyze_short_env("DXY > SMA20 (strong dollar)",
                      lambda e: e.get("dxy", np.nan) > e.get("dxy_sma20", np.nan))
    analyze_short_env("DXY > SMA50 (strong dollar)",
                      lambda e: e.get("dxy", np.nan) > e.get("dxy_sma50", np.nan))

    # Combined
    analyze_short_env("VIX > SMA50 + SPY < SMA50",
                      lambda e: (e.get("vix", np.nan) > e.get("vix_sma50", np.nan)
                                 and e.get("spy", np.nan) < e.get("spy_sma50", np.nan)))
    analyze_short_env("SPY < SMA50 + DXY > SMA20",
                      lambda e: (e.get("spy", np.nan) < e.get("spy_sma50", np.nan)
                                 and e.get("dxy", np.nan) > e.get("dxy_sma20", np.nan)))
    analyze_short_env("TNX > SMA20 + DXY > SMA20",
                      lambda e: (e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan)
                                 and e.get("dxy", np.nan) > e.get("dxy_sma20", np.nan)))
    analyze_short_env("VIX > 20 + SPY < SMA50",
                      lambda e: (e.get("vix", np.nan) > 20
                                 and e.get("spy", np.nan) < e.get("spy_sma50", np.nan)))
    analyze_short_env("VIX > SMA20 + TNX > SMA20",
                      lambda e: (e.get("vix", np.nan) > e.get("vix_sma20", np.nan)
                                 and e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan)))
    analyze_short_env("SPY < SMA200 (strongest bear)",
                      lambda e: e.get("spy", np.nan) < e.get("spy_sma200", np.nan))
    analyze_short_env("VIX > SMA50 + TNX > SMA50",
                      lambda e: (e.get("vix", np.nan) > e.get("vix_sma50", np.nan)
                                 and e.get("tnx", np.nan) > e.get("tnx_sma50", np.nan)))

    # ══════════════════════════════════════════════════════════════════════
    # 2. REGIME-SWITCHED COMBINED: LONG ALWAYS + SHORT WHEN [CONDITION]
    # ══════════════════════════════════════════════════════════════════════
    print_header("2. REGIME-SWITCHED: Long always + Short when [condition]")

    regime_conditions = [
        # Single signals
        ("S when VIX > 20",
         lambda e: e.get("vix", np.nan) > 20),
        ("S when VIX > 25",
         lambda e: e.get("vix", np.nan) > 25),
        ("S when VIX > SMA20",
         lambda e: e.get("vix", np.nan) > e.get("vix_sma20", np.nan)),
        ("S when VIX > SMA50",
         lambda e: e.get("vix", np.nan) > e.get("vix_sma50", np.nan)),
        ("S when SPY < SMA20",
         lambda e: e.get("spy", np.nan) < e.get("spy_sma20", np.nan)),
        ("S when SPY < SMA50",
         lambda e: e.get("spy", np.nan) < e.get("spy_sma50", np.nan)),
        ("S when SPY < SMA200",
         lambda e: e.get("spy", np.nan) < e.get("spy_sma200", np.nan)),
        ("S when TNX > SMA20",
         lambda e: e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan)),
        ("S when TNX > SMA50",
         lambda e: e.get("tnx", np.nan) > e.get("tnx_sma50", np.nan)),
        ("S when DXY > SMA20",
         lambda e: e.get("dxy", np.nan) > e.get("dxy_sma20", np.nan)),
        ("S when DXY > SMA50",
         lambda e: e.get("dxy", np.nan) > e.get("dxy_sma50", np.nan)),
        # Combined signals
        ("S when VIX>SMA50 + SPY<SMA50",
         lambda e: (e.get("vix", np.nan) > e.get("vix_sma50", np.nan)
                    and e.get("spy", np.nan) < e.get("spy_sma50", np.nan))),
        ("S when SPY<SMA50 + DXY>SMA20",
         lambda e: (e.get("spy", np.nan) < e.get("spy_sma50", np.nan)
                    and e.get("dxy", np.nan) > e.get("dxy_sma20", np.nan))),
        ("S when TNX>SMA20 + DXY>SMA20",
         lambda e: (e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan)
                    and e.get("dxy", np.nan) > e.get("dxy_sma20", np.nan))),
        ("S when VIX>20 + SPY<SMA50",
         lambda e: (e.get("vix", np.nan) > 20
                    and e.get("spy", np.nan) < e.get("spy_sma50", np.nan))),
        ("S when VIX>SMA20 + TNX>SMA20",
         lambda e: (e.get("vix", np.nan) > e.get("vix_sma20", np.nan)
                    and e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan))),
        ("S when SPY<SMA200",
         lambda e: e.get("spy", np.nan) < e.get("spy_sma200", np.nan)),
        ("S when VIX>SMA50 + TNX>SMA50",
         lambda e: (e.get("vix", np.nan) > e.get("vix_sma50", np.nan)
                    and e.get("tnx", np.nan) > e.get("tnx_sma50", np.nan))),
        # Triple
        ("S when VIX>SMA50+SPY<SMA50+DXY>SMA20",
         lambda e: (e.get("vix", np.nan) > e.get("vix_sma50", np.nan)
                    and e.get("spy", np.nan) < e.get("spy_sma50", np.nan)
                    and e.get("dxy", np.nan) > e.get("dxy_sma20", np.nan))),
        ("S when VIX>20+SPY<SMA200",
         lambda e: (e.get("vix", np.nan) > 20
                    and e.get("spy", np.nan) < e.get("spy_sma200", np.nan))),
        ("S when VIX>SMA20+SPY<SMA50+TNX>SMA20",
         lambda e: (e.get("vix", np.nan) > e.get("vix_sma20", np.nan)
                    and e.get("spy", np.nan) < e.get("spy_sma50", np.nan)
                    and e.get("tnx", np.nan) > e.get("tnx_sma20", np.nan))),
    ]

    results = []
    for label, condition in regime_conditions:
        comb, s_taken, s_blocked = regime_combine(long_trades, short_trades, env, condition)
        m = compute_metrics(comb)
        print_row(label, m, shorts_taken=s_taken)
        print_years(m)
        results.append((label, m, s_taken, s_blocked))

    # ══════════════════════════════════════════════════════════════════════
    # 3. RANKING — sorted by Calmar
    # ══════════════════════════════════════════════════════════════════════
    print_header("3. RANKING BY CALMAR (regime-switched vs baselines)")

    all_ranked = []
    # Add baselines
    all_ranked.append(("LONG ONLY", m_long, None, None))
    all_ranked.append(("COMBINED ALWAYS", m_combined,
                       len([t for t in combined_always if t.direction == -1]), None))
    all_ranked.extend(results)

    all_ranked.sort(key=lambda x: x[1]["calmar_ratio"], reverse=True)

    for i, (label, m, s_taken, _) in enumerate(all_ranked, 1):
        ryr = m["total_r"] / DATA_YEARS
        marker = ""
        if label == "LONG ONLY":
            marker = " <-- long baseline"
        elif label == "COMBINED ALWAYS":
            marker = " <-- combined baseline"
        print(f"    {i:>2}. {label:<50s}  R/yr={ryr:>5.1f}  DD={m['max_drawdown_r']:>6.1f}  "
              f"Calmar={m['calmar_ratio']:>6.2f}  N={m['total_trades']:>5d}"
              f"{'  S=' + str(s_taken) if s_taken is not None else ''}{marker}")

    # ══════════════════════════════════════════════════════════════════════
    # 4. TOP 5 DETAILED BREAKDOWN
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'='*110}")
    print(f"  TOP 5 — Detailed year-by-year")
    print(f"{'='*110}")

    for i, (label, m, s_taken, _) in enumerate(all_ranked[:5], 1):
        ryr = m["total_r"] / DATA_YEARS
        print(f"\n  #{i}: {label}")
        print(f"      R/yr={ryr:.1f}  DD={m['max_drawdown_r']:.1f}  Calmar={m['calmar_ratio']:.2f}  "
              f"N={m['total_trades']}  WR={m['win_rate']:.1%}  PF={m['profit_factor']:.2f}")
        print_years(m)

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'='*110}")
    print(f"  SUMMARY")
    print(f"{'='*110}")

    # Find best regime-switched (excluding baselines)
    regime_only = [(l, m, s, b) for l, m, s, b in all_ranked
                   if l not in ("LONG ONLY", "COMBINED ALWAYS")]
    best_regime = max(regime_only, key=lambda x: x[1]["calmar_ratio"])

    long_ryr = m_long["total_r"] / DATA_YEARS
    comb_ryr = m_combined["total_r"] / DATA_YEARS
    regime_ryr = best_regime[1]["total_r"] / DATA_YEARS

    print(f"\n  {'Config':<50s}  {'R/yr':>6s}  {'DD':>6s}  {'Calmar':>7s}")
    print(f"  {'─'*75}")
    print(f"  {'Long only':<50s}  {long_ryr:>6.1f}  {m_long['max_drawdown_r']:>6.1f}  "
          f"{m_long['calmar_ratio']:>7.2f}")
    print(f"  {'Combined always (L+S)':<50s}  {comb_ryr:>6.1f}  {m_combined['max_drawdown_r']:>6.1f}  "
          f"{m_combined['calmar_ratio']:>7.2f}")
    print(f"  {best_regime[0]:<50s}  {regime_ryr:>6.1f}  {best_regime[1]['max_drawdown_r']:>6.1f}  "
          f"{best_regime[1]['calmar_ratio']:>7.2f}")

    print(f"\n  Best regime switch: {best_regime[0]}")
    print(f"  Shorts taken: {best_regime[2]} | Shorts blocked: {best_regime[3]}")

    if best_regime[1]["calmar_ratio"] > m_long["calmar_ratio"]:
        print(f"\n  >> REGIME SWITCH BEATS LONG-ONLY — worth pursuing!")
    elif best_regime[1]["calmar_ratio"] > m_combined["calmar_ratio"]:
        print(f"\n  >> REGIME SWITCH BEATS COMBINED-ALWAYS but not LONG-ONLY")
        print(f"     Consider if the extra R/yr justifies the Calmar drop")
    else:
        print(f"\n  >> LONG-ONLY STILL WINS — regime switching doesn't help")

    print(f"\n  CAUTION: Regime switching on 11 years has overfitting risk.")
    print(f"  Any signal that only activates in 2-3 years is unreliable.")
    print(f"  Prefer signals that activate in 5+ distinct years.")

    elapsed = time.time() - t_start
    print(f"\n{'='*110}")
    print(f"  ALL ANALYSIS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*110}")


if __name__ == "__main__":
    main()
