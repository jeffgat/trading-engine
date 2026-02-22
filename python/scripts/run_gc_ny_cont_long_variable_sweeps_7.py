#!/usr/bin/env python3
"""Step 2 — Variable Sweeps Round 7: GC NY Continuation Longs.

Anchor (from R6 adoptions):
  stop=4.5%, rr=9.0, tp1=0.5, ATR 20, min_gap=5.0%, max_gap_atr=25%
  ICF=True, 8m ORB (09:30-09:38), entry→13:00, flat 15:50, long-only, FOMC excluded
"""

import sys, time, datetime
from dataclasses import replace
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10.15
CPY = "2026"

GC_NY = SessionConfig(name="NY", orb_start="09:30", orb_end="09:38", entry_start="09:38",
    entry_end="13:00", flat_start="15:50", flat_end="16:00",
    stop_atr_pct=4.5, min_gap_atr_pct=5.0, max_gap_points=25.0, max_gap_atr_pct=25.0)

ANCHOR = StrategyConfig(rr=9.0, tp1_ratio=0.5, risk_usd=5000.0, atr_length=20,
    min_qty=1.0, qty_step=1.0, sessions=(GC_NY,), instrument=GC,
    strategy="continuation", direction_filter="long", impulse_close_filter=True,
    use_bar_magnifier=True,
    half_days=("20250703","20251128","20251224","20250109","20260119"),
    excluded_dates=FOMC_DATES)

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(GC.data_file, start=START_DATE)
df_1m = load_1m_for_5m(GC.data_file, start=START_DATE)
df_1s = load_1s_for_5m(GC.data_file, start=START_DATE)
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} | {time.time()-t0:.1f}s")

def rm(config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    m["neg_full_years"] = sum(1 for y,r in m.get("r_by_year",{}).items() if r<0 and y!=CPY)
    m["r_per_yr"] = m["total_r"]/DATA_YEARS
    return m

def rmt(config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    m["neg_full_years"] = sum(1 for y,r in m.get("r_by_year",{}).items() if r<0 and y!=CPY)
    m["r_per_yr"] = m["total_r"]/DATA_YEARS
    return trades, m

def pt(results, dim_name, dk="value"):
    print(f"\n{'─'*90}\n  DIMENSION: {dim_name}\n{'─'*90}")
    print(f"  {'Value':<12} {'Trades':>7} {'WR':>7} {'PF':>6} {'Sharpe':>8} {'Net R':>8} {'R/yr':>7} {'MaxDD':>8} {'Calmar':>8} {'NegYr':>6}")
    print(f"  {'-'*86}")
    for r in results:
        mk = " ◄ANCHOR" if r.get("is_anchor") else ""
        print(f"  {str(r[dk]):<12} {r['total_trades']:>7} {r['win_rate']:>6.1%} {r['profit_factor']:>6.2f} {r['sharpe_ratio']:>8.3f} {r['total_r']:>8.1f} {r['r_per_yr']:>7.1f} {r['max_drawdown_r']:>8.1f} {r['calmar_ratio']:>8.2f} {r['neg_full_years']:>6}{mk}")

def df(trades, ed):
    return [t for t in trades if t.exit_type==EXIT_NO_FILL or datetime.date.fromisoformat(t.date).weekday() not in ed]

def sw_stop():
    R=[]
    for v in [3.0,3.5,4.0,4.5,5.0,6.0,7.5,10.0,12.0,15.0]:
        m=rm(replace(ANCHOR,sessions=(replace(GC_NY,stop_atr_pct=v),))); m["value"]=v; m["is_anchor"]=(v==4.5); R.append(m)
    pt(R,"Stop ATR %"); return R

def sw_orb():
    R=[]
    for l,s,e,es in [("5m","09:30","09:35","09:35"),("8m","09:30","09:38","09:38"),("10m","09:30","09:40","09:40"),("15m","09:30","09:45","09:45"),("20m","09:30","09:50","09:50"),("25m","09:30","09:55","09:55"),("30m","09:30","10:00","10:00")]:
        m=rm(replace(ANCHOR,sessions=(replace(GC_NY,orb_start=s,orb_end=e,entry_start=es),))); m["value"]=l; m["is_anchor"]=(l=="8m"); R.append(m)
    pt(R,"ORB Window"); return R

def sw_atr():
    R=[]
    for v in [3,5,7,10,14,16,18,20,22,25,30,50]:
        m=rm(replace(ANCHOR,atr_length=v)); m["value"]=v; m["is_anchor"]=(v==20); R.append(m)
    pt(R,"ATR Length"); return R

def sw_ee():
    R=[]
    for v in ["10:30","11:00","11:30","12:00","13:00","14:00","15:00"]:
        m=rm(replace(ANCHOR,sessions=(replace(GC_NY,entry_end=v),))); m["value"]=v; m["is_anchor"]=(v=="13:00"); R.append(m)
    pt(R,"Entry End Time"); return R

def sw_fs():
    R=[]
    for v in ["13:00","14:00","14:30","15:00","15:30","15:50"]:
        m=rm(replace(ANCHOR,sessions=(replace(GC_NY,flat_start=v),))); m["value"]=v; m["is_anchor"]=(v=="15:50"); R.append(m)
    pt(R,"Flat Start Time"); return R

def sw_dir():
    R=[]
    for v in ["long","both","short"]:
        m=rm(replace(ANCHOR,direction_filter=v)); m["value"]=v; m["is_anchor"]=(v=="long"); R.append(m)
    pt(R,"Direction"); return R

def sw_rr():
    R=[]
    for v in [3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0,11.0,12.0]:
        m=rm(replace(ANCHOR,rr=v)); m["value"]=v; m["is_anchor"]=(v==9.0); R.append(m)
    pt(R,"R:R Ratio"); return R

def sw_tp1():
    R=[]
    for v in [0.3,0.4,0.5,0.6,0.7,0.8]:
        m=rm(replace(ANCHOR,tp1_ratio=v)); m["value"]=v; m["is_anchor"]=(v==0.5); R.append(m)
    pt(R,"TP1 Ratio"); return R

def sw_gap():
    R=[]
    for v in [1.0,2.0,2.5,3.0,3.5,4.0,5.0,6.0,7.0,8.0]:
        m=rm(replace(ANCHOR,sessions=(replace(GC_NY,min_gap_atr_pct=v),))); m["value"]=v; m["is_anchor"]=(v==5.0); R.append(m)
    pt(R,"Min Gap ATR %"); return R

def sw_dow():
    ta = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    R=[]
    for l,es in [("none",set()),("Mon",{0}),("Tue",{1}),("Wed",{2}),("Thu",{3}),("Fri",{4}),("Mon+Fri",{0,4}),("Thu+Fri",{3,4})]:
        f = df(ta,es) if es else ta
        m=compute_metrics(f); m["neg_full_years"]=sum(1 for y,r in m.get("r_by_year",{}).items() if r<0 and y!=CPY)
        m["r_per_yr"]=m["total_r"]/DATA_YEARS; m["value"]=l; m["is_anchor"]=(l=="none"); R.append(m)
    pt(R,"DOW Exclusion"); return R

def sw_mga():
    R=[]
    for l,v in [("OFF",0.0),("15%",15.0),("20%",20.0),("25%",25.0),("30%",30.0),("40%",40.0),("50%",50.0),("75%",75.0)]:
        m=rm(replace(ANCHOR,sessions=(replace(GC_NY,max_gap_atr_pct=v),))); m["value"]=l; m["is_anchor"]=(l=="25%"); R.append(m)
    pt(R,"Max Gap ATR %"); return R

def sw_icf():
    R=[]
    for v in [False,True]:
        m=rm(replace(ANCHOR,impulse_close_filter=v)); m["value"]=v; m["is_anchor"]=(v==True); R.append(m)
    pt(R,"ICF"); return R

if __name__ == "__main__":
    print(f"\n{'='*90}\n  GC NY CONT LONGS — VARIABLE SWEEPS ROUND 7\n  Anchor: stop=4.5%, rr=9.0, tp1=0.5, ATR 20, gap=5.0%, max_gap_atr=25%\n          ICF=True, 8m ORB, entry→13:00, flat 15:50, long-only, FOMC excl\n{'='*90}")
    ts=time.time()
    print("\nRunning anchor...")
    at, am = rmt(ANCHOR)
    filled=[t for t in at if t.exit_type!=EXIT_NO_FILL]
    if filled:
        st=[abs(t.entry_price-t.stop_price)/GC.min_tick for t in filled]
        print(f"  Stop ticks — median: {np.median(st):.0f}, p10: {np.percentile(st,10):.0f}, p25: {np.percentile(st,25):.0f}")
    print(f"  Anchor: {am['total_trades']} trades, Calmar {am['calmar_ratio']:.2f}, Net R {am['total_r']:.1f}, DD {am['max_drawdown_r']:.1f}, Neg years {am['neg_full_years']}")
    print(f"\n  R by year:")
    for y,r in sorted(am.get("r_by_year",{}).items()):
        print(f"    {y}: {r:>+8.1f}{' ←NEG' if r<0 and y!=CPY else ''}")
    ac,an=am["calmar_ratio"],am["neg_full_years"]

    sweeps={}
    for i,(n,f) in enumerate([("stop",sw_stop),("orb",sw_orb),("atr",sw_atr),("entry_end",sw_ee),("flat",sw_fs),("dir",sw_dir),("rr",sw_rr),("tp1",sw_tp1),("gap",sw_gap),("dow",sw_dow),("max_gap_atr",sw_mga),("icf",sw_icf)],1):
        print(f"\n[{i}/12] {n}..."); sweeps[n]=f()

    print(f"\n{'='*90}\n  ROUND 7 SUMMARY — Anchor Calmar: {ac:.2f} | Neg years: {an}\n{'='*90}")
    adoptions=[]
    print(f"  {'Dim':<20} {'Best':<15} {'Calmar':>12} {'Δ':>10} {'NegYr':>8} {'Trades':>8} {'Decision':>12}")
    print(f"  {'-'*88}")
    for dn,res in sweeps.items():
        best=max(res,key=lambda r:r["calmar_ratio"])
        anch=next((r for r in res if r.get("is_anchor")),res[0])
        d=best["calmar_ratio"]-anch["calmar_ratio"]
        if dn=="dow": dec="  SKIP-DOW"; ad=False
        else: ad=d>0.3 and best["neg_full_years"]<=an and best["total_trades"]>100; dec="→ ADOPT" if ad else "  keep"
        if ad: adoptions.append((dn,best["value"],best["calmar_ratio"],d))
        print(f"  {dn:<20} {str(best['value']):<15} {best['calmar_ratio']:>12.2f} {d:>+10.2f} {best['neg_full_years']:>8} {best['total_trades']:>8} {dec:>12}")

    print(f"\n  Total adoptions: {len(adoptions)}")
    if adoptions:
        print("\n  Adopted:")
        for dn,v,c,d in adoptions: print(f"    {dn}: {v} (Calmar {c:.2f}, Δ={d:+.2f})")
        print(f"\n  → Re-sweep (Round 8).")
    else: print(f"\n  → CONVERGED. Ready for grid sweep.")
    print(f"\n  Elapsed: {time.time()-ts:.0f}s ({(time.time()-ts)/60:.1f}m)")
