#!/usr/bin/env python3
"""NQ NY Continuation — Variable Sweeps Round 11 (Longs-Only Fresh Start).

R11 anchor (R10 + 1 adoption):
  ORB: 09:30-09:50 (20m), entry until 12:00, flat 15:30-16:00
  stop=7.0%, min_gap_atr=2.5%
  rr=3.5, tp1=0.4, ATR=12, direction=long, ICF=OFF, continuation, 1s magnifier
  DOW gate: excl Fri

R10 adoption applied:
  icf: ON -> OFF (+1.78)

ICF oscillation history: OFF->ON->OFF->OFF->OFF->ON->ON->ON->ON->OFF
If ICF flips back to ON, lock at whichever gives higher Calmar at this anchor.
Adoption rule: Calmar delta > +0.3 AND no NEW negative full years AND trades > 100.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT_NAME = "NQ"
SESSION_NAME = "NY"
SWEEP_ROUND = 11

START_DATE = "2016-01-01"
DATA_YEARS = 10

MIN_TP1_RATIO = 0.2

ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="12:00",
    flat_start="15:30",
    flat_end="16:00",
    stop_atr_pct=7.0,
    min_gap_atr_pct=2.5,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=3.5,
    tp1_ratio=0.4,
    atr_length=12,
    impulse_close_filter=False,
    name="NQ NY Long R11 Anchor",
)

ANCHOR_DOW_EXCL = {4}  # excl Friday


# -- Helpers -------------------------------------------------------------------

def run_and_metric(df_5m, df_1m, df_1s, config, dow_excl=None):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    excl = dow_excl if dow_excl is not None else ANCHOR_DOW_EXCL
    if excl:
        trades = apply_dow_filter(trades, excl)
    return trades, compute_metrics(trades)


HDR = (
    f"    {'#':>3} {'Variable':>24} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}"
)


def print_header(title):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")
    print(HDR)
    print(f"    {'---'*30}")


def print_row(i, label, m, is_base=False):
    marker = " <<<" if is_base else ""
    n_years = max(DATA_YEARS, 1)
    r_yr = m["total_r"] / n_years if m["total_trades"] > 0 else 0
    print(
        f"    {i:>3} {label:>24} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f}{marker}"
    )


def print_years(m):
    rby = m.get("r_by_year", {})
    if rby:
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(rby.items()))
        print(f"      R by year: {yr_str}")


def neg_year_set(m):
    current_year = str(datetime.now().year)
    return {yr for yr, r in m.get("r_by_year", {}).items() if r < 0 and str(yr) != current_year}


def median_stop_ticks(trades):
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / NQ.min_tick for t in filled)


def check_adopt(label, m, anchor_calmar, anchor_neg):
    cal = m["calmar_ratio"]
    delta = cal - anchor_calmar
    new_neg = neg_year_set(m) - anchor_neg
    trades = m["total_trades"]
    adopt = delta > 0.3 and len(new_neg) == 0 and trades > 100
    tag = "ADOPT" if adopt else "skip"
    print(f"      -> {label}: Calmar {cal:.2f} (delta {delta:+.2f}), "
          f"new_neg={sorted(new_neg) if new_neg else 'none'}, trades={trades} => {tag}")
    return adopt, delta


# -- Main ----------------------------------------------------------------------

def main():
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} ORB — Variable Sweeps Round {SWEEP_ROUND} (Longs-Only)")
    print("=" * 90)
    print(f"Anchor: rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, stop={ANCHOR_SESSION.stop_atr_pct}%, "
          f"gap={ANCHOR_SESSION.min_gap_atr_pct}%")
    print(f"ORB={ANCHOR_SESSION.orb_start}-{ANCHOR_SESSION.orb_end}, entry<={ANCHOR_SESSION.entry_end}, "
          f"flat={ANCHOR_SESSION.flat_start}, ATR={ANCHOR.atr_length}, dir={ANCHOR.direction_filter}, "
          f"DOW excl={ANCHOR_DOW_EXCL or 'none'}, ICF={'ON' if ANCHOR.impulse_close_filter else 'OFF'}")
    print(f"MIN_TP1_RATIO={MIN_TP1_RATIO}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        print("  WARNING: 1m data not found — using 5m only")
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    adoptions = []

    # -- 0. ANCHOR BASELINE ----------------------------------------------------
    print_header("0. ANCHOR BASELINE")
    anchor_trades_raw, m_anc_raw = run_and_metric(df_5m, df_1m, df_1s, ANCHOR, dow_excl=set())
    if ANCHOR_DOW_EXCL:
        anchor_trades, m_anc = run_and_metric(df_5m, df_1m, df_1s, ANCHOR)
    else:
        anchor_trades, m_anc = anchor_trades_raw, m_anc_raw
    print_row(0, "ANCHOR", m_anc, is_base=True)
    print_years(m_anc)
    anc_cal = m_anc["calmar_ratio"]
    anc_neg = neg_year_set(m_anc)
    print(f"      Neg years: {sorted(anc_neg) if anc_neg else 'none'}")
    print(f"      Median stop: {median_stop_ticks(anchor_trades):.1f} ticks")

    # -- 1-11: All dimensions (same structure as R10 but compact) ---

    for dim_idx, (dim_name, values, build_fn) in enumerate([
        ("ORB WINDOW", [("10m","09:30","09:40","09:40"),("15m","09:30","09:45","09:45"),
                        ("20m","09:30","09:50","09:50"),("25m","09:30","09:55","09:55"),
                        ("30m","09:30","10:00","10:00")], "orb"),
        ("ATR LENGTH", [5,7,10,12,14,16,20,30], "atr"),
        ("ENTRY END TIME", ["10:30","11:00","11:30","12:00","12:30","13:00","14:00","15:00","15:30"], "entry"),
        ("FLAT START", ["13:00","13:30","14:00","14:30","15:00","15:30","15:50"], "flat"),
        ("ICF", [False, True], "icf"),
        ("DOW EXCLUSION", [("none",set()),("excl Mon",{0}),("excl Tue",{1}),("excl Wed",{2}),
                           ("excl Thu",{3}),("excl Fri",{4}),("excl M+F",{0,4}),("excl Th+F",{3,4})], "dow"),
        ("REWARD:RISK", [1.5,2.0,2.5,3.0,3.25,3.5,3.75,4.0,5.0], "rr"),
        ("TP1 RATIO", [0.2,0.3,0.35,0.4,0.45,0.5,0.6,0.7], "tp1"),
        ("STOP ATR %", [5,6,6.5,7,7.5,8,9,10,12], "stop"),
        ("MIN GAP ATR %", [0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0], "gap"),
        ("DIRECTION", ["both","long","short"], "dir"),
    ], 1):
        anchor_str = {
            "orb": f"{ANCHOR_SESSION.orb_start}-{ANCHOR_SESSION.orb_end}",
            "atr": str(ANCHOR.atr_length),
            "entry": ANCHOR_SESSION.entry_end,
            "flat": ANCHOR_SESSION.flat_start,
            "icf": "ON" if ANCHOR.impulse_close_filter else "OFF",
            "dow": str(ANCHOR_DOW_EXCL or "none"),
            "rr": str(ANCHOR.rr),
            "tp1": f"{ANCHOR.tp1_ratio} (min={MIN_TP1_RATIO})" if build_fn == "tp1" else str(ANCHOR.tp1_ratio),
            "stop": f"{ANCHOR_SESSION.stop_atr_pct}%",
            "gap": f"{ANCHOR_SESSION.min_gap_atr_pct}%",
            "dir": ANCHOR.direction_filter,
        }[build_fn]
        print_header(f"{dim_idx}. {dim_name} (anchor={anchor_str})")
        best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc

        for i, val in enumerate(values, 1):
            if build_fn == "orb":
                label, orb_s, orb_e, entry_s = val
                sess = replace(ANCHOR_SESSION, orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
                cfg = replace(ANCHOR, sessions=(sess,))
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (orb_e == ANCHOR_SESSION.orb_end)
                lbl = f"orb={label}"
            elif build_fn == "atr":
                cfg = replace(ANCHOR, atr_length=val)
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (val == ANCHOR.atr_length)
                lbl = f"atr={val}"
            elif build_fn == "entry":
                sess = replace(ANCHOR_SESSION, entry_end=val)
                cfg = replace(ANCHOR, sessions=(sess,))
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (val == ANCHOR_SESSION.entry_end)
                lbl = f"end={val}"
            elif build_fn == "flat":
                sess = replace(ANCHOR_SESSION, flat_start=val)
                cfg = replace(ANCHOR, sessions=(sess,))
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (val == ANCHOR_SESSION.flat_start)
                lbl = f"flat={val}"
            elif build_fn == "icf":
                cfg = replace(ANCHOR, impulse_close_filter=val)
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (val == ANCHOR.impulse_close_filter)
                lbl = "ICF=ON" if val else "ICF=OFF"
            elif build_fn == "dow":
                label, excluded = val
                filtered = apply_dow_filter(anchor_trades_raw, excluded) if excluded else anchor_trades_raw
                m = compute_metrics(filtered)
                is_base = (excluded == ANCHOR_DOW_EXCL)
                lbl = label
            elif build_fn == "rr":
                cfg = replace(ANCHOR, rr=val)
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (abs(val - ANCHOR.rr) < 0.01)
                lbl = f"rr={val}"
            elif build_fn == "tp1":
                cfg = replace(ANCHOR, tp1_ratio=val)
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (abs(val - ANCHOR.tp1_ratio) < 0.01)
                lbl = f"tp1={val}"
            elif build_fn == "stop":
                sess = replace(ANCHOR_SESSION, stop_atr_pct=float(val))
                cfg = replace(ANCHOR, sessions=(sess,))
                trades_s, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                med = median_stop_ticks(trades_s)
                if med < 10:
                    print(f"    {i:>3} {'stop='+str(val)+'%':>24}  SKIP (median stop {med:.1f} ticks < 10)")
                    continue
                is_base = (abs(val - ANCHOR_SESSION.stop_atr_pct) < 0.01)
                lbl = f"stop={val}%"
            elif build_fn == "gap":
                sess = replace(ANCHOR_SESSION, min_gap_atr_pct=val)
                cfg = replace(ANCHOR, sessions=(sess,))
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (abs(val - ANCHOR_SESSION.min_gap_atr_pct) < 0.01)
                lbl = f"gap={val}%"
            elif build_fn == "dir":
                cfg = replace(ANCHOR, direction_filter=val)
                _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
                is_base = (val == ANCHOR.direction_filter)
                lbl = f"dir={val}"

            print_row(i, lbl, m, is_base=is_base)
            if build_fn == "dir":
                print_years(m)
            if m["calmar_ratio"] > best_cal:
                best_cal, best_lbl, best_m = m["calmar_ratio"], lbl, m

        ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
        if ok:
            adoptions.append((dim_name.lower().replace(" ", "_"), best_lbl, delta))

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    elapsed = time.time() - t0
    print(f"\n{'='*90}")
    print(f"  SUMMARY — Round {SWEEP_ROUND} (Longs-Only, tp1 >= {MIN_TP1_RATIO})")
    print(f"  Anchor Calmar: {anc_cal:.2f} | Neg years: {sorted(anc_neg) if anc_neg else 'none'}")
    print(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"{'='*90}")

    if adoptions:
        print(f"\n  ADOPTIONS ({len(adoptions)}):")
        for var, lbl, delta in adoptions:
            print(f"    {var:<20s} -> {lbl:<20s} (Calmar delta {delta:+.2f})")
        print(f"\n  ** NOT CONVERGED — Update anchor and re-sweep as R{SWEEP_ROUND + 1} **")
    else:
        print(f"\n  ** CONVERGED — No dimensions pass adoption threshold **")
        print(f"  Ready for grid sweep on stop x rr x gap x tp1.")


if __name__ == "__main__":
    main()
