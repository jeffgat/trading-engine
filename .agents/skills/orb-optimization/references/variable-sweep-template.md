# Variable Sweep Script Template

When generating a variable sweep script, produce a **complete, runnable** Python file
using the appropriate template below. Replace all `{PLACEHOLDERS}` with concrete values for the
asset, session, and current anchor config.

There are two template types:

- **Stand-alone template** (Step 2a): Used for `_variable_sweeps_1.py`. Sweeps 13 independent dimensions once. No re-sweeping.
- **Core convergence template** (Step 2b): Used for `_variable_sweeps_2.py`, `_3.py`, etc. Sweeps 3 core dimensions (stop, RR, TP1) iteratively until convergence.

## Placeholders

| Placeholder | Description | Example |
|---|---|---|
| `{INSTRUMENT}` | Symbol (uppercase) | `ES` |
| `{INSTRUMENT_LOWER}` | Symbol (lowercase, for filenames) | `es` |
| `{INSTRUMENT_IMPORT}` | Python variable for instrument import | `ES` (or `SIX_B` for 6B) |
| `{SESSION}` | Session name in SessionConfig | `NY` |
| `{SESSION_UPPER}` | For display | `NY` |
| `{SESSION_LOWER}` | For filenames | `ny` |
| `{STRATEGY}` | `continuation`, `reversal`, or `inversion` | `continuation` |
| `{SWEEP_ROUND}` | Sweep iteration number | `1` |
| `{START_DATE}` | Backtest start date | `2016-01-01` |
| `{DATA_YEARS}` | Number of full calendar years in sample | `10` |
| `{DATA_FILE_5M}` | 5m CSV filename | `ES_5m.csv` |
| `{ORB_START}` | ORB window open | `09:30` |
| `{ORB_END}` | ORB window close | `09:45` |
| `{ENTRY_START}` | Entry window open (usually = ORB_END) | `09:45` |
| `{ENTRY_END}` | Entry window close | `12:00` |
| `{FLAT_START}` | Flat/EOD start | `15:50` |
| `{FLAT_END}` | Flat/EOD end | `16:00` |
| `{STOP_ATR}` | stop_atr_pct anchor value | `7.5` |
| `{STOP_ORB}` | stop_orb_pct anchor value (0=off) | `0.0` |
| `{MIN_GAP_ATR}` | min_gap_atr_pct anchor value | `2.25` |
| `{MAX_GAP_POINTS}` | max_gap_points anchor value | `100.0` |
| `{MAX_GAP_ATR}` | max_gap_atr_pct anchor value (0=off) | `0.0` |
| `{RR_RATIO}` | rr anchor value | `2.0` |
| `{TP1_RATIO}` | tp1_ratio anchor value | `0.5` |
| `{ATR_PERIOD}` | atr_length anchor value | `14` |
| `{DIRECTION}` | direction_filter anchor value | `both` |
| `{ICF}` | impulse_close_filter anchor value | `False` |
| `{EXCLUDED_DAYS}` | DOW exclusion set (Python literal) | `set()` or `{3}` |
| `{EXCLUDED_DAYS_LABEL}` | Human-readable DOW label | `none` or `excl Thu` |
| `{SMA_PERIOD}` | SMA trend gate period (0 = OFF) | `0` |
| `{QM_PCT}` | Qualifying move ATR % (0 = OFF, inversion only) | `0.0` |
| `{WEEKLY_CAP}` | Weekly loss cap in R (0 = OFF) | `0.0` |
| `{MONTHLY_CAP}` | Monthly loss cap in R (0 = OFF) | `0.0` |
| `{PREV_ADOPTIONS}` | Summary of what changed from last round | `stop: 7.5% -> 3.0% (+0.45)` |

## Session-Appropriate Sweep Values

When filling in the sweep arrays, use session-appropriate times:

**NY session** (orb ~09:30):
- entry_end: `["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "14:00", "15:00"]`
- flat_start: `["13:00", "14:00", "14:30", "15:00", "15:30", "15:50"]`

**Asia session** (orb ~20:00, crosses midnight):
- entry_end: `["22:00", "23:00", "00:00", "01:00", "02:00", "03:00"]`
- flat_start: `["04:00", "05:00", "06:00", "06:30", "06:45"]`

**LDN session** (orb ~03:00):
- entry_end: `["04:30", "05:00", "06:00", "07:00", "08:00", "08:25"]`
- flat_start: `["07:00", "07:30", "08:00", "08:20"]`

---

## Stand-Alone Template (Step 2a — `_variable_sweeps_1.py`)

This template sweeps 13 independent dimensions in a single pass. No re-sweeping — adoptions are
collected and applied once to form the anchor for the core convergence loop.

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} {STRATEGY} — Stand-Alone Variable Sweeps (Round 1).

R1 anchor:
  ORB: {ORB_START}-{ORB_END}, entry until {ENTRY_END}, flat {FLAT_START}-{FLAT_END}
  stop_atr={STOP_ATR}%, stop_orb={STOP_ORB}%, min_gap_atr={MIN_GAP_ATR}%, max_gap_pts={MAX_GAP_POINTS}, max_gap_atr={MAX_GAP_ATR}
  rr={RR_RATIO}, tp1={TP1_RATIO}, ATR={ATR_PERIOD}, direction={DIRECTION}, ICF={ICF}, {STRATEGY}, 1s magnifier
  DOW gate: {EXCLUDED_DAYS_LABEL}

Stand-alone pass: 13 independent dimensions swept once (direction, stop method, ORB window,
entry end, flat time, ATR length, min gap, DOW, ICF, SMA trend gate, qualifying move,
weekly loss cap, monthly loss cap). Adoptions feed into core convergence.

Adoption rule: Calmar delta > +0.3 AND no NEW negative full years AND trades > 100.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import (
    apply_dow_filter,
    apply_sma_trend_gate,
    apply_weekly_loss_cap,
    apply_monthly_loss_cap,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT_NAME = "{INSTRUMENT}"
SESSION_NAME = "{SESSION_UPPER}"
SWEEP_ROUND = 1

START_DATE = "{START_DATE}"
DATA_YEARS = {DATA_YEARS}

ANCHOR_SESSION = SessionConfig(
    name="{SESSION}",
    orb_start="{ORB_START}",
    orb_end="{ORB_END}",
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_START}",
    flat_end="{FLAT_END}",
    stop_atr_pct={STOP_ATR},
    stop_orb_pct={STOP_ORB},
    min_gap_atr_pct={MIN_GAP_ATR},
    max_gap_points={MAX_GAP_POINTS},
    max_gap_atr_pct={MAX_GAP_ATR},
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument={INSTRUMENT_IMPORT},
    strategy="{STRATEGY}",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="{DIRECTION}",
    rr={RR_RATIO},
    tp1_ratio={TP1_RATIO},
    atr_length={ATR_PERIOD},
    impulse_close_filter={ICF},
    name="{INSTRUMENT} {SESSION_UPPER} R1 Stand-Alone",
)

ANCHOR_DOW_EXCL = {EXCLUDED_DAYS}
ANCHOR_SMA_PERIOD = {SMA_PERIOD}        # 0 = OFF
ANCHOR_QM_PCT = {QM_PCT}                # 0.0 = OFF (inversion only)
ANCHOR_WEEKLY_CAP = {WEEKLY_CAP}        # 0.0 = OFF
ANCHOR_MONTHLY_CAP = {MONTHLY_CAP}      # 0.0 = OFF


# -- Helpers -------------------------------------------------------------------

def run_and_metric(df_5m, df_1m, df_1s, config, dow_excl=None, sma_period=None,
                   weekly_cap=None, monthly_cap=None):
    """Run backtest and apply the full filter chain.

    Filter order: DOW -> SMA -> Weekly cap -> Monthly cap.
    Loss caps are order-sensitive and must be applied last.
    """
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    # DOW filter
    excl = dow_excl if dow_excl is not None else ANCHOR_DOW_EXCL
    if excl:
        trades = apply_dow_filter(trades, excl)
    # SMA trend gate
    sma = sma_period if sma_period is not None else ANCHOR_SMA_PERIOD
    if sma > 0:
        trades = apply_sma_trend_gate(trades, df_5m, sma_period=sma)
    # Weekly loss cap
    wcap = weekly_cap if weekly_cap is not None else ANCHOR_WEEKLY_CAP
    if wcap > 0:
        trades = apply_weekly_loss_cap(trades, cap_r=wcap)
    # Monthly loss cap
    mcap = monthly_cap if monthly_cap is not None else ANCHOR_MONTHLY_CAP
    if mcap > 0:
        trades = apply_monthly_loss_cap(trades, cap_r=mcap)
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
    """Median stop distance in ticks. Configs with < 10 ticks are rejected."""
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / {INSTRUMENT_IMPORT}.tick_size for t in filled)


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
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} ORB — Stand-Alone Variable Sweeps (Round 1)")
    print("=" * 90)
    stop_desc = f"orb={ANCHOR_SESSION.stop_orb_pct}%" if ANCHOR_SESSION.stop_orb_pct > 0 else f"atr={ANCHOR_SESSION.stop_atr_pct}%"
    print(f"Anchor: rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, stop={stop_desc}, "
          f"gap={ANCHOR_SESSION.min_gap_atr_pct}%")
    print(f"ORB={ANCHOR_SESSION.orb_start}-{ANCHOR_SESSION.orb_end}, entry<={ANCHOR_SESSION.entry_end}, "
          f"flat={ANCHOR_SESSION.flat_start}, ATR={ANCHOR.atr_length}, dir={ANCHOR.direction_filter}, "
          f"DOW excl={ANCHOR_DOW_EXCL or 'none'}, ICF={'ON' if ANCHOR.impulse_close_filter else 'OFF'}")
    sma_desc = f"SMA={ANCHOR_SMA_PERIOD}" if ANCHOR_SMA_PERIOD > 0 else "SMA=OFF"
    qm_desc = f"QM={ANCHOR_QM_PCT}%" if ANCHOR_QM_PCT > 0 else "QM=OFF"
    wcap_desc = f"WkCap={ANCHOR_WEEKLY_CAP}R" if ANCHOR_WEEKLY_CAP > 0 else "WkCap=OFF"
    mcap_desc = f"MoCap={ANCHOR_MONTHLY_CAP}R" if ANCHOR_MONTHLY_CAP > 0 else "MoCap=OFF"
    print(f"  {sma_desc}, {qm_desc}, {wcap_desc}, {mcap_desc}")
    print("\nPhase: STAND-ALONE (13 dims, single pass, no re-sweep)")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("{DATA_FILE_5M}")
    try:
        df_1m = load_1m_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1m data not found — using 5m only")
        df_1m = None
    df_1s = load_1s_for_5m("{DATA_FILE_5M}")  # returns None if missing
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    adoptions = []

    # -- 0. ANCHOR BASELINE ----------------------------------------------------
    print_header("0. ANCHOR BASELINE")
    # Single backtest run; derive DOW-filtered version only if needed
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

    # ══════════════════════════════════════════════════════════════════════════
    # STAND-ALONE SWEEPS (13 dims — single pass, no re-sweep)
    # ══════════════════════════════════════════════════════════════════════════

    # -- SA-1. DIRECTION -------------------------------------------------------
    print_header(f"SA-1. DIRECTION (anchor={ANCHOR.direction_filter})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, d in enumerate(["both", "long", "short"], 1):
        cfg = replace(ANCHOR, direction_filter=d)
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"dir={d}", m, is_base=(d == ANCHOR.direction_filter))
        print_years(m)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"dir={d}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("direction", best_lbl, delta))

    # -- SA-2. STOP METHOD (ATR vs ORB%) ---------------------------------------
    # Test the ALTERNATIVE stop method to whatever the anchor uses
    if ANCHOR_SESSION.stop_orb_pct > 0:
        # Anchor uses ORB% — test ATR values
        alt_vals = [1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0]
        print_header(f"SA-2. STOP METHOD — test ATR (anchor uses ORB%={ANCHOR_SESSION.stop_orb_pct})")
        best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
        for i, s in enumerate(alt_vals, 1):
            sess = replace(ANCHOR_SESSION, stop_atr_pct=s, stop_orb_pct=0.0)
            cfg = replace(ANCHOR, sessions=(sess,))
            trades_s, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
            med_ticks = median_stop_ticks(trades_s)
            if med_ticks < 10:
                print(f"    {i:>3} {'atr=' + str(s) + '%':>24}  SKIP (median stop {med_ticks:.1f} ticks < 10)")
                continue
            print_row(i, f"atr={s}%", m)
            if m["calmar_ratio"] > best_cal:
                best_cal, best_lbl, best_m = m["calmar_ratio"], f"atr={s}%", m
        ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
        if ok:
            adoptions.append(("stop_method->ATR", best_lbl, delta))
    else:
        # Anchor uses ATR — test ORB% values
        alt_vals = [25, 50, 75, 100, 125, 150, 200]
        print_header(f"SA-2. STOP METHOD — test ORB% (anchor uses ATR={ANCHOR_SESSION.stop_atr_pct}%)")
        best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
        for i, s in enumerate(alt_vals, 1):
            sess = replace(ANCHOR_SESSION, stop_orb_pct=s, stop_atr_pct=0.0)
            cfg = replace(ANCHOR, sessions=(sess,))
            trades_s, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
            med_ticks = median_stop_ticks(trades_s)
            if med_ticks < 10:
                print(f"    {i:>3} {'orb=' + str(s) + '%':>24}  SKIP (median stop {med_ticks:.1f} ticks < 10)")
                continue
            print_row(i, f"orb={s}%", m)
            if m["calmar_ratio"] > best_cal:
                best_cal, best_lbl, best_m = m["calmar_ratio"], f"orb={s}%", m
        ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
        if ok:
            adoptions.append(("stop_method->ORB%", best_lbl, delta))

    # -- SA-3. ORB WINDOW ------------------------------------------------------
    orb_windows = [
        ("5m",  "{ORB_START}", "??:??", "??:??"),   # fill with ORB_START + 5m
        ("10m", "{ORB_START}", "??:??", "??:??"),   # fill with ORB_START + 10m
        ("15m", "{ORB_START}", "??:??", "??:??"),   # fill with ORB_START + 15m
        ("20m", "{ORB_START}", "??:??", "??:??"),
        ("30m", "{ORB_START}", "??:??", "??:??"),
        ("45m", "{ORB_START}", "??:??", "??:??"),
        ("60m", "{ORB_START}", "??:??", "??:??"),
    ]
    print_header(f"SA-3. ORB WINDOW (anchor={ANCHOR_SESSION.orb_start}-{ANCHOR_SESSION.orb_end})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, (label, orb_s, orb_e, entry_s) in enumerate(orb_windows, 1):
        sess = replace(ANCHOR_SESSION, orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        is_base = (orb_e == ANCHOR_SESSION.orb_end)
        print_row(i, f"orb={label}", m, is_base=is_base)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"orb={label}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("orb_window", best_lbl, delta))

    # -- SA-4. ENTRY END TIME --------------------------------------------------
    entry_ends = [...]  # fill with session-appropriate values
    print_header(f"SA-4. ENTRY END TIME (anchor={ANCHOR_SESSION.entry_end})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, ee in enumerate(entry_ends, 1):
        sess = replace(ANCHOR_SESSION, entry_end=ee)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"end={ee}", m, is_base=(ee == ANCHOR_SESSION.entry_end))
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"end={ee}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("entry_end", best_lbl, delta))

    # -- SA-5. FLAT START TIME -------------------------------------------------
    flat_starts = [...]  # fill with session-appropriate values
    print_header(f"SA-5. FLAT START (anchor={ANCHOR_SESSION.flat_start})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, fs in enumerate(flat_starts, 1):
        sess = replace(ANCHOR_SESSION, flat_start=fs)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"flat={fs}", m, is_base=(fs == ANCHOR_SESSION.flat_start))
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"flat={fs}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("flat_start", best_lbl, delta))

    # -- SA-6. ATR LENGTH ------------------------------------------------------
    atr_vals = [5, 7, 10, 14, 20, 30]
    print_header(f"SA-6. ATR LENGTH (anchor={ANCHOR.atr_length})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, atr in enumerate(atr_vals, 1):
        cfg = replace(ANCHOR, atr_length=atr)
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"atr={atr}", m, is_base=(atr == ANCHOR.atr_length))
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"atr={atr}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("atr_length", best_lbl, delta))

    # -- SA-7. MIN GAP ATR % ---------------------------------------------------
    gap_vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0]
    print_header(f"SA-7. MIN GAP ATR % (anchor={ANCHOR_SESSION.min_gap_atr_pct}%)")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, g in enumerate(gap_vals, 1):
        sess = replace(ANCHOR_SESSION, min_gap_atr_pct=g)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"gap={g}%", m, is_base=(abs(g - ANCHOR_SESSION.min_gap_atr_pct) < 0.01))
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"gap={g}%", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("min_gap_atr_pct", best_lbl, delta))

    # -- SA-8. DOW EXCLUSION (post-filter on raw trades) -----------------------
    dow_sets = [
        ("none",      set()),
        ("excl Mon",  {0}),
        ("excl Tue",  {1}),
        ("excl Wed",  {2}),
        ("excl Thu",  {3}),
        ("excl Fri",  {4}),
        ("excl M+F",  {0, 4}),
        ("excl Th+F", {3, 4}),
    ]
    print_header(f"SA-8. DOW EXCLUSION (anchor={ANCHOR_DOW_EXCL or 'none'})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, (label, excluded) in enumerate(dow_sets, 1):
        filtered = apply_dow_filter(anchor_trades_raw, excluded) if excluded else anchor_trades_raw
        m = compute_metrics(filtered)
        is_base = (excluded == ANCHOR_DOW_EXCL)
        print_row(i, label, m, is_base=is_base)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("dow_exclusion", best_lbl, delta))

    # -- SA-9. ICF (Impulse Close Filter) --------------------------------------
    print_header(f"SA-9. ICF (anchor={'ON' if ANCHOR.impulse_close_filter else 'OFF'})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, icf in enumerate([False, True], 1):
        cfg = replace(ANCHOR, impulse_close_filter=icf)
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        label = "ICF=ON" if icf else "ICF=OFF"
        print_row(i, label, m, is_base=(icf == ANCHOR.impulse_close_filter))
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("icf", best_lbl, delta))

    # -- SA-10. SMA TREND GATE (post-trade filter) -----------------------------
    sma_vals = [0, 10, 20, 50, 100, 200]  # 0 = OFF
    print_header(f"SA-10. SMA TREND GATE (anchor={'OFF' if ANCHOR_SMA_PERIOD == 0 else ANCHOR_SMA_PERIOD})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, sma in enumerate(sma_vals, 1):
        label = "SMA=OFF" if sma == 0 else f"SMA={sma}"
        if sma == 0:
            # No SMA gate — use raw anchor trades with DOW filter only
            filtered = apply_dow_filter(anchor_trades_raw, ANCHOR_DOW_EXCL) if ANCHOR_DOW_EXCL else anchor_trades_raw
            m = compute_metrics(filtered)
        else:
            # Apply SMA gate to raw trades, then DOW filter
            sma_filtered = apply_sma_trend_gate(anchor_trades_raw, df_5m, sma_period=sma)
            if ANCHOR_DOW_EXCL:
                sma_filtered = apply_dow_filter(sma_filtered, ANCHOR_DOW_EXCL)
            m = compute_metrics(sma_filtered)
        is_base = (sma == ANCHOR_SMA_PERIOD)
        print_row(i, label, m, is_base=is_base)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("sma_trend_gate", best_lbl, delta))

    # -- SA-11. QUALIFYING MOVE (inversion only) --------------------------------
    if ANCHOR.strategy == "inversion":
        from orb_backtest.engine.qualifying_move import run_backtest_qm
        qm_vals = [0, 25, 50, 75, 100, 150, 200]  # 0 = OFF
        print_header(f"SA-11. QUALIFYING MOVE (anchor={'OFF' if ANCHOR_QM_PCT == 0 else str(ANCHOR_QM_PCT) + '%'})")
        best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
        for i, qm in enumerate(qm_vals, 1):
            label = "QM=OFF" if qm == 0 else f"QM={qm}%"
            sess = replace(ANCHOR_SESSION, qualifying_move_atr_pct=float(qm))
            cfg = replace(ANCHOR, sessions=(sess,))
            trades_qm = run_backtest_qm(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
            if ANCHOR_DOW_EXCL:
                trades_qm = apply_dow_filter(trades_qm, ANCHOR_DOW_EXCL)
            if ANCHOR_SMA_PERIOD > 0:
                trades_qm = apply_sma_trend_gate(trades_qm, df_5m, sma_period=ANCHOR_SMA_PERIOD)
            m = compute_metrics(trades_qm)
            is_base = (qm == ANCHOR_QM_PCT)
            print_row(i, label, m, is_base=is_base)
            if m["calmar_ratio"] > best_cal:
                best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
        ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
        if ok:
            adoptions.append(("qualifying_move", best_lbl, delta))
    else:
        print(f"\n  SA-11. QUALIFYING MOVE — SKIPPED (strategy={ANCHOR.strategy}, inversion only)")

    # -- SA-12. WEEKLY LOSS CAP ------------------------------------------------
    wcap_vals = [0.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]  # 0 = OFF
    print_header(f"SA-12. WEEKLY LOSS CAP (anchor={'OFF' if ANCHOR_WEEKLY_CAP == 0 else str(ANCHOR_WEEKLY_CAP) + 'R'})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, wcap in enumerate(wcap_vals, 1):
        label = "WkCap=OFF" if wcap == 0 else f"WkCap={wcap}R"
        if wcap == 0:
            # No weekly cap — use DOW-filtered anchor trades
            m = m_anc
        else:
            # Apply weekly cap to DOW-filtered anchor trades (order-sensitive, apply last)
            capped = apply_weekly_loss_cap(anchor_trades, cap_r=wcap)
            m = compute_metrics(capped)
        is_base = (abs(wcap - ANCHOR_WEEKLY_CAP) < 0.01)
        print_row(i, label, m, is_base=is_base)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("weekly_loss_cap", best_lbl, delta))

    # -- SA-13. MONTHLY LOSS CAP -----------------------------------------------
    mcap_vals = [0.0, 3.0, 5.0, 7.0, 10.0, 15.0]  # 0 = OFF
    print_header(f"SA-13. MONTHLY LOSS CAP (anchor={'OFF' if ANCHOR_MONTHLY_CAP == 0 else str(ANCHOR_MONTHLY_CAP) + 'R'})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, mcap in enumerate(mcap_vals, 1):
        label = "MoCap=OFF" if mcap == 0 else f"MoCap={mcap}R"
        if mcap == 0:
            m = m_anc
        else:
            # Apply monthly cap to DOW-filtered anchor trades (order-sensitive, apply last)
            capped = apply_monthly_loss_cap(anchor_trades, cap_r=mcap)
            m = compute_metrics(capped)
        is_base = (abs(mcap - ANCHOR_MONTHLY_CAP) < 0.01)
        print_row(i, label, m, is_base=is_base)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("monthly_loss_cap", best_lbl, delta))

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY — STAND-ALONE PASS
    # ══════════════════════════════════════════════════════════════════════════
    elapsed = time.time() - t0
    print(f"\n{'='*90}")
    print(f"  SUMMARY — Stand-Alone Pass (13 dimensions)")
    print(f"  Anchor Calmar: {anc_cal:.2f} | Neg years: {sorted(anc_neg) if anc_neg else 'none'}")
    print(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"{'='*90}")

    if adoptions:
        print(f"\n  STAND-ALONE ADOPTIONS ({len(adoptions)}):")
        for var, lbl, delta in adoptions:
            print(f"    {var:<20s} -> {lbl:<20s} (Calmar delta {delta:+.2f})")
        print(f"\n  ** Update anchor with stand-alone adoptions, then run Core Convergence (R2) **")
    else:
        print(f"\n  ** No stand-alone adoptions — proceed to Core Convergence (R2) with current anchor **")


if __name__ == "__main__":
    main()
```

---

## Core Convergence Template (Step 2b — `_variable_sweeps_{N}.py`, N>=2)

This template sweeps 3 core dimensions (stop, RR, TP1) that form a tight feedback loop.
Re-sweep until 0 adoptions in a full pass. Each round generates a new script with N incremented.

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} {STRATEGY} — Core Convergence Round {SWEEP_ROUND}.

R{SWEEP_ROUND} anchor:
  ORB: {ORB_START}-{ORB_END}, entry until {ENTRY_END}, flat {FLAT_START}-{FLAT_END}
  stop_atr={STOP_ATR}%, stop_orb={STOP_ORB}%, min_gap_atr={MIN_GAP_ATR}%, max_gap_pts={MAX_GAP_POINTS}, max_gap_atr={MAX_GAP_ATR}
  rr={RR_RATIO}, tp1={TP1_RATIO}, ATR={ATR_PERIOD}, direction={DIRECTION}, ICF={ICF}, {STRATEGY}, 1s magnifier
  DOW gate: {EXCLUDED_DAYS_LABEL}

{PREV_ADOPTIONS}

Core convergence: 3 dimensions (stop, RR, TP1) swept iteratively until 0 adoptions.
Adoption rule: Calmar delta > +0.3 AND no NEW negative full years AND trades > 100.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import (
    apply_dow_filter,
    apply_sma_trend_gate,
    apply_weekly_loss_cap,
    apply_monthly_loss_cap,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT_NAME = "{INSTRUMENT}"
SESSION_NAME = "{SESSION_UPPER}"
SWEEP_ROUND = {SWEEP_ROUND}

START_DATE = "{START_DATE}"
DATA_YEARS = {DATA_YEARS}

ANCHOR_SESSION = SessionConfig(
    name="{SESSION}",
    orb_start="{ORB_START}",
    orb_end="{ORB_END}",
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_START}",
    flat_end="{FLAT_END}",
    stop_atr_pct={STOP_ATR},
    stop_orb_pct={STOP_ORB},
    min_gap_atr_pct={MIN_GAP_ATR},
    max_gap_points={MAX_GAP_POINTS},
    max_gap_atr_pct={MAX_GAP_ATR},
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument={INSTRUMENT_IMPORT},
    strategy="{STRATEGY}",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="{DIRECTION}",
    rr={RR_RATIO},
    tp1_ratio={TP1_RATIO},
    atr_length={ATR_PERIOD},
    impulse_close_filter={ICF},
    name="{INSTRUMENT} {SESSION_UPPER} R{SWEEP_ROUND} Core",
)

ANCHOR_DOW_EXCL = {EXCLUDED_DAYS}
ANCHOR_SMA_PERIOD = {SMA_PERIOD}        # 0 = OFF
ANCHOR_QM_PCT = {QM_PCT}                # 0.0 = OFF (inversion only)
ANCHOR_WEEKLY_CAP = {WEEKLY_CAP}        # 0.0 = OFF
ANCHOR_MONTHLY_CAP = {MONTHLY_CAP}      # 0.0 = OFF


# -- Helpers -------------------------------------------------------------------

def run_and_metric(df_5m, df_1m, df_1s, config, dow_excl=None, sma_period=None,
                   weekly_cap=None, monthly_cap=None):
    """Run backtest and apply the full filter chain.

    Filter order: DOW -> SMA -> Weekly cap -> Monthly cap.
    Loss caps are order-sensitive and must be applied last.
    """
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    # DOW filter
    excl = dow_excl if dow_excl is not None else ANCHOR_DOW_EXCL
    if excl:
        trades = apply_dow_filter(trades, excl)
    # SMA trend gate
    sma = sma_period if sma_period is not None else ANCHOR_SMA_PERIOD
    if sma > 0:
        trades = apply_sma_trend_gate(trades, df_5m, sma_period=sma)
    # Weekly loss cap
    wcap = weekly_cap if weekly_cap is not None else ANCHOR_WEEKLY_CAP
    if wcap > 0:
        trades = apply_weekly_loss_cap(trades, cap_r=wcap)
    # Monthly loss cap
    mcap = monthly_cap if monthly_cap is not None else ANCHOR_MONTHLY_CAP
    if mcap > 0:
        trades = apply_monthly_loss_cap(trades, cap_r=mcap)
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
    """Median stop distance in ticks. Configs with < 10 ticks are rejected."""
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / {INSTRUMENT_IMPORT}.tick_size for t in filled)


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
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} ORB — Core Convergence Round {SWEEP_ROUND}")
    print("=" * 90)
    stop_desc = f"orb={ANCHOR_SESSION.stop_orb_pct}%" if ANCHOR_SESSION.stop_orb_pct > 0 else f"atr={ANCHOR_SESSION.stop_atr_pct}%"
    print(f"Anchor: rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, stop={stop_desc}, "
          f"gap={ANCHOR_SESSION.min_gap_atr_pct}%")
    print(f"ORB={ANCHOR_SESSION.orb_start}-{ANCHOR_SESSION.orb_end}, entry<={ANCHOR_SESSION.entry_end}, "
          f"flat={ANCHOR_SESSION.flat_start}, ATR={ANCHOR.atr_length}, dir={ANCHOR.direction_filter}, "
          f"DOW excl={ANCHOR_DOW_EXCL or 'none'}, ICF={'ON' if ANCHOR.impulse_close_filter else 'OFF'}")
    print(f"\nPhase: CORE CONVERGENCE (3 dims: stop, RR, TP1)")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("{DATA_FILE_5M}")
    try:
        df_1m = load_1m_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1m data not found — using 5m only")
        df_1m = None
    df_1s = load_1s_for_5m("{DATA_FILE_5M}")  # returns None if missing
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    adoptions = []

    # -- 0. ANCHOR BASELINE ----------------------------------------------------
    print_header("0. ANCHOR BASELINE")
    anchor_trades, m_anc = run_and_metric(df_5m, df_1m, df_1s, ANCHOR)
    print_row(0, "ANCHOR", m_anc, is_base=True)
    print_years(m_anc)
    anc_cal = m_anc["calmar_ratio"]
    anc_neg = neg_year_set(m_anc)
    print(f"      Neg years: {sorted(anc_neg) if anc_neg else 'none'}")

    # ══════════════════════════════════════════════════════════════════════════
    # CORE CONVERGENCE (3 dims — iterative until 0 adoptions)
    # ══════════════════════════════════════════════════════════════════════════

    # -- C-1. STOP SIZE (ATR% or ORB%) ----------------------------------------
    if ANCHOR_SESSION.stop_orb_pct > 0:
        # ORB%-based stop — sweep ORB% values
        stop_vals = [25, 50, 75, 100, 125, 150, 175, 200]
        anchor_val = ANCHOR_SESSION.stop_orb_pct
        print_header(f"C-1. STOP ORB % (anchor={anchor_val}%)")
        best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
        for i, s in enumerate(stop_vals, 1):
            sess = replace(ANCHOR_SESSION, stop_orb_pct=s)
            cfg = replace(ANCHOR, sessions=(sess,))
            trades_s, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
            med_ticks = median_stop_ticks(trades_s)
            if med_ticks < 10:
                print(f"    {i:>3} {'stop_orb=' + str(s) + '%':>24}  SKIP (median stop {med_ticks:.1f} ticks < 10)")
                continue
            print_row(i, f"stop_orb={s}%", m, is_base=(abs(s - anchor_val) < 0.01))
            if m["calmar_ratio"] > best_cal:
                best_cal, best_lbl, best_m = m["calmar_ratio"], f"stop_orb={s}%", m
        ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
        if ok:
            adoptions.append(("stop_orb_pct", best_lbl, delta))
    else:
        # ATR-based stop — sweep ATR% values
        stop_vals = [1.0, 2.0, 3.0, 4.0, 5.0, 7.5, 10.0, 12.0, 15.0]
        print_header(f"C-1. STOP ATR % (anchor={ANCHOR_SESSION.stop_atr_pct}%)")
        best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
        for i, s in enumerate(stop_vals, 1):
            sess = replace(ANCHOR_SESSION, stop_atr_pct=s)
            cfg = replace(ANCHOR, sessions=(sess,))
            trades_s, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
            med_ticks = median_stop_ticks(trades_s)
            if med_ticks < 10:
                print(f"    {i:>3} {'stop=' + str(s) + '%':>24}  SKIP (median stop {med_ticks:.1f} ticks < 10)")
                continue
            print_row(i, f"stop={s}%", m, is_base=(abs(s - ANCHOR_SESSION.stop_atr_pct) < 0.01))
            if m["calmar_ratio"] > best_cal:
                best_cal, best_lbl, best_m = m["calmar_ratio"], f"stop={s}%", m
        ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
        if ok:
            adoptions.append(("stop_atr_pct", best_lbl, delta))

    # -- C-2. REWARD:RISK -----------------------------------------------------
    rr_vals = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    print_header(f"C-2. REWARD:RISK (anchor={ANCHOR.rr})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, rr in enumerate(rr_vals, 1):
        cfg = replace(ANCHOR, rr=rr)
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"rr={rr}", m, is_base=(abs(rr - ANCHOR.rr) < 0.01))
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"rr={rr}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("rr", best_lbl, delta))

    # -- C-3. TP1 RATIO -------------------------------------------------------
    MIN_TP1 = 0.2  # hard constraint — never test tp1 below 0.2
    tp1_vals = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    print_header(f"C-3. TP1 RATIO (anchor={ANCHOR.tp1_ratio})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, tp1 in enumerate(tp1_vals, 1):
        if tp1 < MIN_TP1:
            print(f"    {i:>3} {'tp1=' + str(tp1):>24}  SKIP (tp1_ratio < {MIN_TP1})")
            continue
        cfg = replace(ANCHOR, tp1_ratio=tp1)
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"tp1={tp1}", m, is_base=(abs(tp1 - ANCHOR.tp1_ratio) < 0.01))
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"tp1={tp1}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("tp1_ratio", best_lbl, delta))

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY — CORE CONVERGENCE
    # ══════════════════════════════════════════════════════════════════════════
    elapsed = time.time() - t0
    print(f"\n{'='*90}")
    print(f"  SUMMARY — Core Convergence Round {SWEEP_ROUND}")
    print(f"  Anchor Calmar: {anc_cal:.2f} | Neg years: {sorted(anc_neg) if anc_neg else 'none'}")
    print(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"{'='*90}")

    if adoptions:
        print(f"\n  CORE ADOPTIONS ({len(adoptions)}):")
        for var, lbl, delta in adoptions:
            print(f"    {var:<20s} -> {lbl:<20s} (Calmar delta {delta:+.2f})")
        print(f"\n  ** NOT CONVERGED — Update anchor and re-sweep core dims as R{SWEEP_ROUND + 1} **")
    else:
        print(f"\n  ** CONVERGED — No core dimensions pass adoption threshold **")
        print(f"  Ready for grid sweep on stop x rr x gap x tp1.")


if __name__ == "__main__":
    main()
```

---

## Generation Rules

1. **Fill all `??:??` ORB window times** by computing `ORB_START + N minutes` for each window size.
   Use the session's ORB start time as the base. For Asia sessions crossing midnight, handle
   the wrap correctly (e.g., `20:00 + 45m = 20:45`, `20:00 + 90m = 21:30`).

2. **Fill `entry_ends` and `flat_starts`** with the session-appropriate values from the table above.
   Always include the anchor value in the array.

3. **Adjust sweep value ranges** to center around the anchor. For example, if anchor stop is 1.0%,
   sweep `[0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]`. If anchor stop is 7.5%,
   sweep `[3.0, 4.0, 5.0, 6.0, 7.5, 9.0, 10.0, 12.0, 15.0]`. The anchor value must always
   appear in the sweep array.

4. **`ANCHOR_DOW_EXCL`** is `set()` for the stand-alone pass (round 1). Subsequent core rounds
   carry forward adopted exclusions from the stand-alone pass.

5. **`DATA_YEARS`** should be calculated from `START_DATE` to today, counting only full calendar years.
   E.g., `2016-01-01` to `2026-02-22` has 10 full years (2016-2025).

6. **1s data**: Always attempt `load_1s_for_5m()`. The loader returns `None` if unavailable; the
   simulator gracefully falls back to 1m then 5m.

7. **Round 1 (stand-alone) uses default anchor values** from the asset's learnings file or `config.py`
   defaults. Round 2+ (core) updates the anchor with all adoptions from prior rounds and documents
   those changes in the docstring's `PREV_ADOPTIONS` block.

8. **The `SWEEP_ROUND + 1` in the core summary** uses the integer constant defined at the top of the
   script, so it computes the next round number automatically at runtime (e.g., if `SWEEP_ROUND=3`,
   it prints `R4`).

9. **Stop method (stand-alone dim SA-2)**: SA-2 always tests the alternative stop method. If anchor
   uses ATR (`stop_orb_pct=0`), SA-2 tests ORB% values. If anchor uses ORB% (`stop_orb_pct > 0`),
   SA-2 tests ATR values. When the alternative method is adopted, update the anchor accordingly and
   core convergence will sweep the newly-adopted method's values in C-1.

10. **Two-phase script naming**:
    - Stand-alone pass: `run_{INSTRUMENT_LOWER}_{SESSION_LOWER}_variable_sweeps_1.py`
    - Core convergence rounds: `run_{INSTRUMENT_LOWER}_{SESSION_LOWER}_variable_sweeps_{N}.py` (N=2, 3, ...)

11. **Which template to use**: For round 1, always use the Stand-Alone Template. For round 2+,
    always use the Core Convergence Template. The stand-alone pass is never repeated — if a large
    stand-alone adoption (Δ>1.0 Calmar) occurs, the core loop will naturally adjust.

12. **SMA Trend Gate (SA-10)**: Applied as a post-trade filter on raw anchor trades. When sweeping,
    test each SMA period against the anchor baseline. `OFF` (0) means no SMA gate. The gate needs
    `df_5m` which is already loaded. After DOW and SMA adoptions, the anchor baseline must include
    both filters for subsequent dims.

13. **Qualifying Move (SA-11)**: Only meaningful for `strategy="inversion"`. Wrap in
    `if ANCHOR.strategy == "inversion":` guard — skip entirely for continuation/reversal. Uses
    `run_backtest_qm()` from `orb_backtest.engine.qualifying_move` instead of `run_backtest()`.
    Import is conditional (inside the guard) to avoid import errors when the module isn't needed.

14. **Loss Caps (SA-12/13)**: Weekly and monthly loss caps are order-sensitive risk overlays.
    They must be applied LAST in the filter chain (after DOW and SMA) because they process trades
    chronologically. `OFF` (0.0) means no cap. Apply to the DOW-filtered (and SMA-filtered if adopted)
    anchor trades, not to raw trades.

15. **New anchor state variables**: `ANCHOR_SMA_PERIOD`, `ANCHOR_QM_PCT`, `ANCHOR_WEEKLY_CAP`,
    `ANCHOR_MONTHLY_CAP` track adopted values for the 4 new dims. Default to 0/0.0 (all OFF).
    When adopted, the `run_and_metric()` helper automatically applies the full filter chain.
