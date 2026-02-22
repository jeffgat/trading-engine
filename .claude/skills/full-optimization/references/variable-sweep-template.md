# Variable Sweep Script Template

When generating a variable sweep script, produce a **complete, runnable** Python file
using the template below. Replace all `{PLACEHOLDERS}` with concrete values for the
asset, session, and current anchor config.

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

## Template

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} {STRATEGY} — Variable Sweeps Round {SWEEP_ROUND}.

R{SWEEP_ROUND} anchor:
  ORB: {ORB_START}-{ORB_END}, entry until {ENTRY_END}, flat {FLAT_START}-{FLAT_END}
  stop={STOP_ATR}%, min_gap_atr={MIN_GAP_ATR}%, max_gap_pts={MAX_GAP_POINTS}, max_gap_atr={MAX_GAP_ATR}
  rr={RR_RATIO}, tp1={TP1_RATIO}, ATR={ATR_PERIOD}, direction={DIRECTION}, ICF={ICF}, {STRATEGY}, 1s magnifier
  DOW gate: {EXCLUDED_DAYS_LABEL}

{PREV_ADOPTIONS}

Adoption rule: Calmar delta > +0.3 AND no NEW negative full years AND trades > 100.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
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
    name="{INSTRUMENT} {SESSION_UPPER} R{SWEEP_ROUND} Anchor",
)

ANCHOR_DOW_EXCL = {EXCLUDED_DAYS}


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
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} ORB — Variable Sweeps Round {SWEEP_ROUND}")
    print("=" * 90)
    print(f"Anchor: rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, stop={ANCHOR_SESSION.stop_atr_pct}%, "
          f"gap={ANCHOR_SESSION.min_gap_atr_pct}%")
    print(f"ORB={ANCHOR_SESSION.orb_start}-{ANCHOR_SESSION.orb_end}, entry<={ANCHOR_SESSION.entry_end}, "
          f"flat={ANCHOR_SESSION.flat_start}, ATR={ANCHOR.atr_length}, dir={ANCHOR.direction_filter}, "
          f"DOW excl={ANCHOR_DOW_EXCL or 'none'}, ICF={'ON' if ANCHOR.impulse_close_filter else 'OFF'}")

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

    # -- 1. STOP ATR % ---------------------------------------------------------
    stop_vals = [1.0, 2.0, 3.0, 4.0, 5.0, 7.5, 10.0, 12.0, 15.0]
    print_header(f"1. STOP ATR % (anchor={ANCHOR_SESSION.stop_atr_pct}%)")
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

    # -- 2. ORB WINDOW ---------------------------------------------------------
    orb_windows = [
        ("5m",  "{ORB_START}", "??:??", "??:??"),   # fill with ORB_START + 5m
        ("10m", "{ORB_START}", "??:??", "??:??"),   # fill with ORB_START + 10m
        ("15m", "{ORB_START}", "??:??", "??:??"),   # fill with ORB_START + 15m
        ("20m", "{ORB_START}", "??:??", "??:??"),
        ("30m", "{ORB_START}", "??:??", "??:??"),
        ("45m", "{ORB_START}", "??:??", "??:??"),
        ("60m", "{ORB_START}", "??:??", "??:??"),
    ]
    print_header(f"2. ORB WINDOW (anchor={ANCHOR_SESSION.orb_start}-{ANCHOR_SESSION.orb_end})")
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

    # -- 3. ATR LENGTH ---------------------------------------------------------
    atr_vals = [5, 7, 10, 14, 20, 30]
    print_header(f"3. ATR LENGTH (anchor={ANCHOR.atr_length})")
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

    # -- 4. ENTRY END TIME -----------------------------------------------------
    entry_ends = [...]  # fill with session-appropriate values
    print_header(f"4. ENTRY END TIME (anchor={ANCHOR_SESSION.entry_end})")
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

    # -- 5. FLAT START TIME ----------------------------------------------------
    flat_starts = [...]  # fill with session-appropriate values
    print_header(f"5. FLAT START (anchor={ANCHOR_SESSION.flat_start})")
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

    # -- 6. DIRECTION ----------------------------------------------------------
    print_header(f"6. DIRECTION (anchor={ANCHOR.direction_filter})")
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

    # -- 7. REWARD:RISK --------------------------------------------------------
    rr_vals = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    print_header(f"7. REWARD:RISK (anchor={ANCHOR.rr})")
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

    # -- 8. TP1 RATIO ----------------------------------------------------------
    tp1_vals = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    print_header(f"8. TP1 RATIO (anchor={ANCHOR.tp1_ratio})")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, tp1 in enumerate(tp1_vals, 1):
        cfg = replace(ANCHOR, tp1_ratio=tp1)
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        print_row(i, f"tp1={tp1}", m, is_base=(abs(tp1 - ANCHOR.tp1_ratio) < 0.01))
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], f"tp1={tp1}", m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("tp1_ratio", best_lbl, delta))

    # -- 9. MIN GAP ATR % ------------------------------------------------------
    gap_vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0]
    print_header(f"9. MIN GAP ATR % (anchor={ANCHOR_SESSION.min_gap_atr_pct}%)")
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

    # -- 10. DOW EXCLUSION (post-filter on raw trades) -------------------------
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
    print_header(f"10. DOW EXCLUSION (anchor={ANCHOR_DOW_EXCL or 'none'})")
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

    # -- 11. MAX GAP ATR % -----------------------------------------------------
    maxgap_vals = [1.0, 1.5, 2.0, 3.0, 5.0, 999.0]
    print_header(f"11. MAX GAP ATR % (anchor={ANCHOR_SESSION.max_gap_atr_pct}, 0/999=off)")
    best_cal, best_lbl, best_m = anc_cal, "anchor", m_anc
    for i, mg in enumerate(maxgap_vals, 1):
        sess = replace(ANCHOR_SESSION, max_gap_atr_pct=mg if mg < 999 else 0.0)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        label = f"maxgap={mg}%" if mg < 999 else "maxgap=OFF"
        is_base = (abs(mg - ANCHOR_SESSION.max_gap_atr_pct) < 0.01) or (
            mg >= 999 and ANCHOR_SESSION.max_gap_atr_pct == 0.0
        )
        print_row(i, label, m, is_base=is_base)
        if m["calmar_ratio"] > best_cal:
            best_cal, best_lbl, best_m = m["calmar_ratio"], label, m
    ok, delta = check_adopt(best_lbl, best_m, anc_cal, anc_neg)
    if ok:
        adoptions.append(("max_gap_atr_pct", best_lbl, delta))

    # -- 12. ICF (Impulse Close Filter) ----------------------------------------
    print_header(f"12. ICF (anchor={'ON' if ANCHOR.impulse_close_filter else 'OFF'})")
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

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    elapsed = time.time() - t0
    print(f"\n{'='*90}")
    print(f"  SUMMARY — Round {SWEEP_ROUND}")
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
```

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

4. **`ANCHOR_DOW_EXCL`** is `set()` for round 1. Subsequent rounds carry forward adopted exclusions.

5. **`DATA_YEARS`** should be calculated from `START_DATE` to today, counting only full calendar years.
   E.g., `2016-01-01` to `2026-02-22` has 10 full years (2016-2025).

6. **1s data**: Always attempt `load_1s_for_5m()`. The loader returns `None` if unavailable; the
   simulator gracefully falls back to 1m then 5m.

7. **Round 1 uses default anchor values** from the asset's learnings file or `config.py` defaults.
   Subsequent rounds update the anchor with adoptions from the previous round and document those
   changes in the docstring's `PREV_ADOPTIONS` block.

8. **The `SWEEP_ROUND + 1` in the summary** uses the integer constant defined at the top of the script,
   so it computes the next round number automatically at runtime (e.g., if `SWEEP_ROUND=3`, it prints `R4`).

9. **Max gap dimension**: Some scripts use `max_gap_points` (absolute) instead of `max_gap_atr_pct`
   (percentage). Use whichever the asset's anchor config uses. If the anchor has `max_gap_atr_pct=0.0`
   (disabled) and a nonzero `max_gap_points`, sweep `max_gap_points` values instead:
   `[20, 30, 50, 75, 100, 9999]` where `9999 = no limit`.

10. **Script filename**: `run_{INSTRUMENT_LOWER}_{SESSION_LOWER}_variable_sweeps_{SWEEP_ROUND}.py`
