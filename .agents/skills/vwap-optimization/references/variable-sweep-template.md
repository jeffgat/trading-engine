# VWAP Variable Sweep Script Template

When generating a variable sweep script, produce a **complete, runnable** Python file
using the appropriate template below. Replace all `{PLACEHOLDERS}` with concrete values for the
asset, session, and current anchor config.

There are two template types:

- **Stand-alone template** (Step 2a): Used for `_vwap_variable_sweeps_1.py`. Sweeps 12 independent dimensions once. No re-sweeping.
- **Core convergence template** (Step 2b): Used for `_vwap_variable_sweeps_2.py`, `_3.py`, etc. Sweeps 3 core dimensions (stop_buffer, RR, TP1) iteratively until convergence.

## Placeholders

| Placeholder | Description | Example |
|---|---|---|
| `{INSTRUMENT}` | Symbol (uppercase) | `NQ` |
| `{INSTRUMENT_LOWER}` | Symbol (lowercase, for filenames) | `nq` |
| `{INSTRUMENT_IMPORT}` | Python variable for instrument import | `NQ` |
| `{SESSION}` | Session name in VWAPSessionConfig | `NY` |
| `{SESSION_UPPER}` | For display | `NY` |
| `{SESSION_LOWER}` | For filenames | `ny` |
| `{SESSION_PREFIX}` | For with_vwap_overrides | `ny` |
| `{SWEEP_ROUND}` | Sweep iteration number | `1` |
| `{START_DATE}` | Backtest start date | `2016-01-01` |
| `{DATA_YEARS}` | Number of full calendar years in sample | `10` |
| `{DATA_FILE_5M}` | 5m CSV filename | `NQ_5m.csv` |
| `{ENTRY_START}` | Entry window open | `09:35` |
| `{ENTRY_END}` | Entry window close | `12:00` |
| `{FLAT_START}` | Flat/EOD start | `15:50` |
| `{FLAT_END}` | Flat/EOD end | `16:00` |
| `{SESSION_OPEN}` | Session open (for cross-midnight) | `09:30` |
| `{DEV_MODE}` | Deviation mode anchor | `atr` |
| `{DEV_ATR_PCT}` | deviation_atr_pct anchor | `30.0` |
| `{DEV_STD}` | deviation_std anchor | `2.0` |
| `{REJECTION_MODE}` | Rejection mode anchor | `close` |
| `{STOP_ATR}` | stop_atr_pct anchor (buffer) | `0.0` |
| `{RR_RATIO}` | rr anchor value | `2.5` |
| `{TP1_RATIO}` | tp1_ratio anchor value | `0.5` |
| `{TP2_MODE}` | tp2_mode anchor value | `fixed_rr` |
| `{ATR_PERIOD}` | atr_length anchor value | `14` |
| `{DIRECTION}` | direction_filter anchor value | `both` |
| `{EXCLUDED_DAYS}` | DOW exclusion set (Python literal) | `set()` or `{3}` |
| `{EXCLUDED_DAYS_LABEL}` | Human-readable DOW label | `none` or `excl Thu` |
| `{WEEKLY_CAP}` | Weekly loss cap in R (0 = OFF) | `0.0` |
| `{MONTHLY_CAP}` | Monthly loss cap in R (0 = OFF) | `0.0` |
| `{PREV_ADOPTIONS}` | Summary of what changed from last round | `stop: 0.0% -> 3.0% (+0.45)` |

## Session-Appropriate Sweep Values

When filling in the sweep arrays, use session-appropriate times:

**NY session** (entry from 09:35):
- entry_end: `["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "14:00", "15:00"]`
- flat_start: `["13:00", "14:00", "14:30", "15:00", "15:30", "15:50"]`

**Asia session** (entry from 20:15, crosses midnight):
- entry_end: `["21:30", "22:00", "23:00", "23:15", "00:00", "01:00", "02:00"]`
- flat_start: `["04:00", "05:00", "06:00", "06:30", "06:45"]`

**LDN session** (entry from 03:15):
- entry_end: `["04:30", "05:00", "06:00", "07:00", "08:00", "08:20"]`
- flat_start: `["07:00", "07:30", "08:00", "08:20"]`

---

## Stand-Alone Template (Step 2a -- `_vwap_variable_sweeps_1.py`)

This template sweeps 12 independent dimensions in a single pass. No re-sweeping -- adoptions are
collected and applied once to form the anchor for the core convergence loop.

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} VWAP -- Stand-Alone Variable Sweeps (Round 1).

R1 anchor:
  entry {ENTRY_START}-{ENTRY_END}, flat {FLAT_START}-{FLAT_END}
  dev_mode={DEV_MODE}, dev_atr={DEV_ATR_PCT}%, dev_std={DEV_STD}, rejection={REJECTION_MODE}
  stop_buf={STOP_ATR}%, rr={RR_RATIO}, tp1={TP1_RATIO}, tp2={TP2_MODE}
  ATR={ATR_PERIOD}, direction={DIRECTION}, 1m magnifier
  DOW gate: {EXCLUDED_DAYS_LABEL}

Stand-alone pass: 12 independent dimensions swept once (direction, deviation mode,
rejection mode, TP2 mode, entry end, flat time, ATR length, deviation threshold,
DOW, weekly loss cap, monthly loss cap). Adoptions feed into core convergence.

Adoption rule: Calmar delta > +0.3 AND no NEW negative full years AND trades > 100.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import (
    apply_dow_filter,
    apply_weekly_loss_cap,
    apply_monthly_loss_cap,
)
from orb_backtest.vwap_config import (
    VWAPSessionConfig, VWAPStrategyConfig,
    with_vwap_overrides,
)
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT_NAME = "{INSTRUMENT}"
SESSION_NAME = "{SESSION_UPPER}"
SWEEP_ROUND = 1

START_DATE = "{START_DATE}"
DATA_YEARS = {DATA_YEARS}

ANCHOR_SESSION = VWAPSessionConfig(
    name="{SESSION}",
    session_open="{SESSION_OPEN}",
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_START}",
    flat_end="{FLAT_END}",
    deviation_mode="{DEV_MODE}",
    deviation_atr_pct={DEV_ATR_PCT},
    deviation_std={DEV_STD},
    rejection_mode="{REJECTION_MODE}",
    stop_atr_pct={STOP_ATR},
)

ANCHOR = VWAPStrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument={INSTRUMENT_IMPORT},
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="{DIRECTION}",
    rr={RR_RATIO},
    tp1_ratio={TP1_RATIO},
    tp2_mode="{TP2_MODE}",
    atr_length={ATR_PERIOD},
    name="{INSTRUMENT} {SESSION_UPPER} VWAP R1 Stand-Alone",
)

ANCHOR_DOW_EXCL = {EXCLUDED_DAYS}
ANCHOR_WEEKLY_CAP = {WEEKLY_CAP}        # 0.0 = OFF
ANCHOR_MONTHLY_CAP = {MONTHLY_CAP}      # 0.0 = OFF


# -- Helpers -------------------------------------------------------------------

def run_and_metric(df_5m, df_1m, df_1s, config, dow_excl=None,
                   weekly_cap=None, monthly_cap=None):
    """Run VWAP backtest and apply the full filter chain.

    Filter order: DOW -> Weekly cap -> Monthly cap.
    Loss caps are order-sensitive and must be applied last.
    """
    trades = run_vwap_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    # DOW filter
    excl = dow_excl if dow_excl is not None else ANCHOR_DOW_EXCL
    if excl:
        trades = apply_dow_filter(trades, excl)
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
    return median(t.risk_points / {INSTRUMENT_IMPORT}.min_tick for t in filled)


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
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} VWAP -- Stand-Alone Variable Sweeps (Round 1)")
    print("=" * 90)
    print(f"Anchor: rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, stop_buf={ANCHOR_SESSION.stop_atr_pct}%, "
          f"dev_mode={ANCHOR_SESSION.deviation_mode}")
    dev_desc = (f"dev_atr={ANCHOR_SESSION.deviation_atr_pct}%" if ANCHOR_SESSION.deviation_mode == "atr"
                else f"dev_std={ANCHOR_SESSION.deviation_std}")
    print(f"  {dev_desc}, reject={ANCHOR_SESSION.rejection_mode}, tp2={ANCHOR.tp2_mode}")
    print(f"  entry {ANCHOR_SESSION.entry_start}-{ANCHOR_SESSION.entry_end}, "
          f"flat={ANCHOR_SESSION.flat_start}, ATR={ANCHOR.atr_length}, dir={ANCHOR.direction_filter}")
    wcap_desc = f"WkCap={ANCHOR_WEEKLY_CAP}R" if ANCHOR_WEEKLY_CAP > 0 else "WkCap=OFF"
    mcap_desc = f"MoCap={ANCHOR_MONTHLY_CAP}R" if ANCHOR_MONTHLY_CAP > 0 else "MoCap=OFF"
    print(f"  DOW excl={ANCHOR_DOW_EXCL or 'none'}, {wcap_desc}, {mcap_desc}")
    print("\nPhase: STAND-ALONE (12 dims, single pass, no re-sweep)")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("{DATA_FILE_5M}")
    try:
        df_1m = load_1m_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1m data not found -- using 5m only")
        df_1m = None
    df_1s = load_1s_for_5m("{DATA_FILE_5M}")  # returns None if missing
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

    # ===========================================================================
    # STAND-ALONE SWEEPS (12 dims -- single pass, no re-sweep)
    # ===========================================================================

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

    # -- SA-2. DEVIATION MODE --------------------------------------------------
    print_header(f"SA-2. DEVIATION MODE (anchor={ANCHOR_SESSION.deviation_mode})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, dm in enumerate(["atr", "std"], 1):
        sess = replace(ANCHOR_SESSION, deviation_mode=dm)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"dev_mode={dm}", m, is_base=(dm == ANCHOR_SESSION.deviation_mode))
        print_years(m)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"dev_mode={dm}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("deviation_mode", best_lbl, delta))

    # -- SA-3. REJECTION MODE --------------------------------------------------
    print_header(f"SA-3. REJECTION MODE (anchor={ANCHOR_SESSION.rejection_mode})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, rm in enumerate(["close", "pinbar"], 1):
        sess = replace(ANCHOR_SESSION, rejection_mode=rm)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"reject={rm}", m, is_base=(rm == ANCHOR_SESSION.rejection_mode))
        print_years(m)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"reject={rm}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("rejection_mode", best_lbl, delta))

    # -- SA-4. TP2 MODE --------------------------------------------------------
    print_header(f"SA-4. TP2 MODE (anchor={ANCHOR.tp2_mode})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, tp2 in enumerate(["fixed_rr", "vwap"], 1):
        cfg = replace(ANCHOR, tp2_mode=tp2)
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"tp2={tp2}", m, is_base=(tp2 == ANCHOR.tp2_mode))
        print_years(m)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"tp2={tp2}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("tp2_mode", best_lbl, delta))

    # -- SA-5. ENTRY END TIME --------------------------------------------------
    entry_ends = [...]  # fill with session-appropriate values
    print_header(f"SA-5. ENTRY END TIME (anchor={ANCHOR_SESSION.entry_end})")
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

    # -- SA-6. FLAT START TIME -------------------------------------------------
    flat_starts = [...]  # fill with session-appropriate values
    print_header(f"SA-6. FLAT START (anchor={ANCHOR_SESSION.flat_start})")
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

    # -- SA-7. ATR LENGTH ------------------------------------------------------
    atr_vals = [5, 7, 10, 14, 20, 30]
    print_header(f"SA-7. ATR LENGTH (anchor={ANCHOR.atr_length})")
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

    # -- SA-8. DEVIATION THRESHOLD (mode-dependent) ----------------------------
    # Only sweep the threshold matching the current (possibly adopted) deviation_mode
    current_dev_mode = ANCHOR_SESSION.deviation_mode
    # NOTE: If deviation_mode was adopted in SA-2, update current_dev_mode accordingly
    # before running SA-8 (check adoptions list for deviation_mode adoption)

    if current_dev_mode == "atr":
        dev_vals = [10, 15, 20, 25, 30, 40, 50]
        print_header(f"SA-8. DEVIATION ATR % (anchor={ANCHOR_SESSION.deviation_atr_pct}%)")
        best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
        for i, dv in enumerate(dev_vals, 1):
            sess = replace(ANCHOR_SESSION, deviation_atr_pct=dv)
            cfg = replace(ANCHOR, sessions=(sess,))
            _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
            print_row(i, f"dev_atr={dv}%", m, is_base=(abs(dv - ANCHOR_SESSION.deviation_atr_pct) < 0.01))
            if m["calmar_ratio"] > best_cal:
                best_cal, best_lbl, best_m = m["calmar_ratio"], f"dev_atr={dv}%", m
        ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
        if ok:
            adoptions.append(("deviation_atr_pct", best_lbl, delta))
    else:
        dev_vals = [1.0, 1.5, 2.0, 2.5, 3.0]
        print_header(f"SA-8. DEVIATION STD (anchor={ANCHOR_SESSION.deviation_std})")
        best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
        for i, dv in enumerate(dev_vals, 1):
            sess = replace(ANCHOR_SESSION, deviation_std=dv)
            cfg = replace(ANCHOR, sessions=(sess,))
            _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
            print_row(i, f"dev_std={dv}", m, is_base=(abs(dv - ANCHOR_SESSION.deviation_std) < 0.01))
            if m["calmar_ratio"] > best_cal:
                best_cal, best_lbl, best_m = m["calmar_ratio"], f"dev_std={dv}", m
        ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
        if ok:
            adoptions.append(("deviation_std", best_lbl, delta))

    # -- SA-9. DOW EXCLUSION (post-filter on raw trades) -----------------------
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
    print_header(f"SA-9. DOW EXCLUSION (anchor={ANCHOR_DOW_EXCL or 'none'})")
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

    # -- SA-10. WEEKLY LOSS CAP ------------------------------------------------
    wcap_vals = [0.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]  # 0 = OFF
    print_header(f"SA-10. WEEKLY LOSS CAP (anchor={'OFF' if ANCHOR_WEEKLY_CAP == 0 else str(ANCHOR_WEEKLY_CAP) + 'R'})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, wcap in enumerate(wcap_vals, 1):
        label = "WkCap=OFF" if wcap == 0 else f"WkCap={wcap}R"
        if wcap == 0:
            m = m_anc
        else:
            capped = apply_weekly_loss_cap(anchor_trades, cap_r=wcap)
            m = compute_metrics(capped)
        is_base = (abs(wcap - ANCHOR_WEEKLY_CAP) < 0.01)
        print_row(i, label, m, is_base=is_base)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("weekly_loss_cap", best_lbl, delta))

    # -- SA-11. MONTHLY LOSS CAP -----------------------------------------------
    mcap_vals = [0.0, 3.0, 5.0, 7.0, 10.0, 15.0]  # 0 = OFF
    print_header(f"SA-11. MONTHLY LOSS CAP (anchor={'OFF' if ANCHOR_MONTHLY_CAP == 0 else str(ANCHOR_MONTHLY_CAP) + 'R'})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, mcap in enumerate(mcap_vals, 1):
        label = "MoCap=OFF" if mcap == 0 else f"MoCap={mcap}R"
        if mcap == 0:
            m = m_anc
        else:
            capped = apply_monthly_loss_cap(anchor_trades, cap_r=mcap)
            m = compute_metrics(capped)
        is_base = (abs(mcap - ANCHOR_MONTHLY_CAP) < 0.01)
        print_row(i, label, m, is_base=is_base)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("monthly_loss_cap", best_lbl, delta))

    # ===========================================================================
    # SUMMARY -- STAND-ALONE PASS
    # ===========================================================================
    elapsed = time.time() - t0
    print(f"\n{'='*90}")
    print(f"  SUMMARY -- Stand-Alone Pass (12 dimensions)")
    print(f"  Anchor Calmar: {anc_cal:.2f} | Neg years: {sorted(anc_neg) if anc_neg else 'none'}")
    print(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"{'='*90}")

    if adoptions:
        print(f"\n  STAND-ALONE ADOPTIONS ({len(adoptions)}):")
        for var, lbl, delta in adoptions:
            print(f"    {var:<20s} -> {lbl:<20s} (Calmar delta {delta:+.2f})")
        print(f"\n  ** Update anchor with stand-alone adoptions, then run Core Convergence (R2) **")
    else:
        print(f"\n  ** No stand-alone adoptions -- proceed to Core Convergence (R2) with current anchor **")


if __name__ == "__main__":
    main()
```

---

## Core Convergence Template (Step 2b -- `_vwap_variable_sweeps_{N}.py`, N>=2)

This template sweeps 3 core dimensions (stop_buffer, RR, TP1) that form a tight feedback loop.
Re-sweep until 0 adoptions in a full pass. Each round generates a new script with N incremented.

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} VWAP -- Core Convergence Round {SWEEP_ROUND}.

R{SWEEP_ROUND} anchor:
  entry {ENTRY_START}-{ENTRY_END}, flat {FLAT_START}-{FLAT_END}
  dev_mode={DEV_MODE}, dev_atr={DEV_ATR_PCT}%, dev_std={DEV_STD}, rejection={REJECTION_MODE}
  stop_buf={STOP_ATR}%, rr={RR_RATIO}, tp1={TP1_RATIO}, tp2={TP2_MODE}
  ATR={ATR_PERIOD}, direction={DIRECTION}, 1m magnifier
  DOW gate: {EXCLUDED_DAYS_LABEL}

{PREV_ADOPTIONS}

Core convergence: 3 dimensions (stop_buffer, RR, TP1) swept iteratively until 0 adoptions.
Adoption rule: Calmar delta > +0.3 AND no NEW negative full years AND trades > 100.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import (
    apply_dow_filter,
    apply_weekly_loss_cap,
    apply_monthly_loss_cap,
)
from orb_backtest.vwap_config import (
    VWAPSessionConfig, VWAPStrategyConfig,
    with_vwap_overrides,
)
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT_NAME = "{INSTRUMENT}"
SESSION_NAME = "{SESSION_UPPER}"
SWEEP_ROUND = {SWEEP_ROUND}

START_DATE = "{START_DATE}"
DATA_YEARS = {DATA_YEARS}

ANCHOR_SESSION = VWAPSessionConfig(
    name="{SESSION}",
    session_open="{SESSION_OPEN}",
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_START}",
    flat_end="{FLAT_END}",
    deviation_mode="{DEV_MODE}",
    deviation_atr_pct={DEV_ATR_PCT},
    deviation_std={DEV_STD},
    rejection_mode="{REJECTION_MODE}",
    stop_atr_pct={STOP_ATR},
)

ANCHOR = VWAPStrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument={INSTRUMENT_IMPORT},
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="{DIRECTION}",
    rr={RR_RATIO},
    tp1_ratio={TP1_RATIO},
    tp2_mode="{TP2_MODE}",
    atr_length={ATR_PERIOD},
    name="{INSTRUMENT} {SESSION_UPPER} VWAP R{SWEEP_ROUND} Core",
)

ANCHOR_DOW_EXCL = {EXCLUDED_DAYS}
ANCHOR_WEEKLY_CAP = {WEEKLY_CAP}        # 0.0 = OFF
ANCHOR_MONTHLY_CAP = {MONTHLY_CAP}      # 0.0 = OFF


# -- Helpers (same as stand-alone template) ------------------------------------

def run_and_metric(df_5m, df_1m, df_1s, config, dow_excl=None,
                   weekly_cap=None, monthly_cap=None):
    trades = run_vwap_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    excl = dow_excl if dow_excl is not None else ANCHOR_DOW_EXCL
    if excl:
        trades = apply_dow_filter(trades, excl)
    wcap = weekly_cap if weekly_cap is not None else ANCHOR_WEEKLY_CAP
    if wcap > 0:
        trades = apply_weekly_loss_cap(trades, cap_r=wcap)
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
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / {INSTRUMENT_IMPORT}.min_tick for t in filled)

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
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} VWAP -- Core Convergence Round {SWEEP_ROUND}")
    print("=" * 90)
    print(f"Anchor: rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, stop_buf={ANCHOR_SESSION.stop_atr_pct}%")
    dev_desc = (f"dev_atr={ANCHOR_SESSION.deviation_atr_pct}%" if ANCHOR_SESSION.deviation_mode == "atr"
                else f"dev_std={ANCHOR_SESSION.deviation_std}")
    print(f"  {dev_desc}, reject={ANCHOR_SESSION.rejection_mode}, tp2={ANCHOR.tp2_mode}")
    print(f"  entry {ANCHOR_SESSION.entry_start}-{ANCHOR_SESSION.entry_end}, "
          f"flat={ANCHOR_SESSION.flat_start}, ATR={ANCHOR.atr_length}, dir={ANCHOR.direction_filter}")
    print(f"\nPhase: CORE CONVERGENCE (3 dims: stop_buffer, RR, TP1)")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("{DATA_FILE_5M}")
    try:
        df_1m = load_1m_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1m data not found -- using 5m only")
        df_1m = None
    df_1s = load_1s_for_5m("{DATA_FILE_5M}")
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

    # ===========================================================================
    # CORE CONVERGENCE (3 dims -- iterative until 0 adoptions)
    # ===========================================================================

    # -- C-1. STOP BUFFER (ATR %) ----------------------------------------------
    stop_vals = [0, 1, 2, 3, 5, 7.5, 10]
    print_header(f"C-1. STOP BUFFER ATR % (anchor={ANCHOR_SESSION.stop_atr_pct}%)")
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
    MIN_TP1 = 0.2  # hard constraint -- never test tp1 below 0.2
    tp1_vals = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
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

    # ===========================================================================
    # SUMMARY -- CORE CONVERGENCE
    # ===========================================================================
    elapsed = time.time() - t0
    print(f"\n{'='*90}")
    print(f"  SUMMARY -- Core Convergence Round {SWEEP_ROUND}")
    print(f"  Anchor Calmar: {anc_cal:.2f} | Neg years: {sorted(anc_neg) if anc_neg else 'none'}")
    print(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"{'='*90}")

    if adoptions:
        print(f"\n  CORE ADOPTIONS ({len(adoptions)}):")
        for var, lbl, delta in adoptions:
            print(f"    {var:<20s} -> {lbl:<20s} (Calmar delta {delta:+.2f})")
        print(f"\n  ** NOT CONVERGED -- Update anchor and re-sweep core dims as R{SWEEP_ROUND + 1} **")
    else:
        print(f"\n  ** CONVERGED -- No core dimensions pass adoption threshold **")
        print(f"  Ready for grid sweep on stop_buffer x rr x tp1 x deviation_threshold.")


if __name__ == "__main__":
    main()
```

---

## Generation Rules

1. **Fill `entry_ends` and `flat_starts`** with the session-appropriate values from the table above.
   Always include the anchor value in the array.

2. **Adjust sweep value ranges** to center around the anchor. For example, if anchor deviation_atr_pct is 25%,
   sweep `[10, 15, 20, 25, 30, 40, 50]`. The anchor value must always appear in the sweep array.

3. **`ANCHOR_DOW_EXCL`** is `set()` for the stand-alone pass (round 1). Subsequent core rounds
   carry forward adopted exclusions from the stand-alone pass.

4. **`DATA_YEARS`** should be calculated from `START_DATE` to today, counting only full calendar years.
   E.g., `2016-01-01` to `2026-02-23` has 10 full years (2016-2025).

5. **1s data**: Always attempt `load_1s_for_5m()`. The loader returns `None` if unavailable; the
   simulator gracefully falls back to 1m then 5m.

6. **Round 1 (stand-alone) uses default anchor values** from the session defaults in `vwap_config.py`.
   Round 2+ (core) updates the anchor with all adoptions from prior rounds and documents
   those changes in the docstring's `PREV_ADOPTIONS` block.

7. **Mode-dependent sweep (SA-8)**: If deviation_mode was adopted in SA-2, the agent must manually
   update `current_dev_mode` before generating SA-8 code. The template shows the branching logic.

8. **Two-phase script naming**:
   - Stand-alone pass: `run_{INSTRUMENT_LOWER}_{SESSION_LOWER}_vwap_variable_sweeps_1.py`
   - Core convergence rounds: `run_{INSTRUMENT_LOWER}_{SESSION_LOWER}_vwap_variable_sweeps_{N}.py` (N=2, 3, ...)

9. **Loss Caps (SA-10/11)**: Weekly and monthly loss caps are order-sensitive risk overlays.
   Apply LAST in the filter chain (after DOW). `OFF` (0.0) means no cap.

10. **No SMA/ICF/QM/ORB/gap dims**: These are ORB-specific and must NOT appear in VWAP sweeps.
