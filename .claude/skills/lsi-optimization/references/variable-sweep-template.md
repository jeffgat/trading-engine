# LSI Variable Sweep Script Template

Produce a **complete, runnable** Python file. Replace all `{PLACEHOLDERS}` with concrete values.

## Placeholders

| Placeholder | Example |
|---|---|
| `{INSTRUMENT}` | `NQ` |
| `{INSTRUMENT_LOWER}` | `nq` |
| `{INSTRUMENT_IMPORT}` | `NQ` |
| `{SESSION}` | `NY` |
| `{SESSION_LOWER}` | `ny` |
| `{SWEEP_ROUND}` | `1` |
| `{START_DATE}` | `2016-01-01` |
| `{DATA_YEARS}` | `10.15` |
| `{CURRENT_PARTIAL_YEAR}` | `2026` |
| `{ENTRY_START}` | `09:35` |
| `{ENTRY_END}` | `15:30` |
| `{FLAT_START}` | `15:50` |
| `{FLAT_END}` | `16:00` |
| `{MIN_GAP_ATR}` | `2.25` |
| `{LSI_N_LEFT}` | `3` |
| `{LSI_N_RIGHT}` | `3` |
| `{LSI_FVG_LEFT}` | `10` |
| `{LSI_FVG_RIGHT}` | `10` |
| `{RR}` | `2.625` |
| `{TP1}` | `0.3` |
| `{ATR_LEN}` | `14` |
| `{DIRECTION}` | `long` |

---

## Stand-Alone Template (`_variable_sweeps_1.py`)

```python
#!/usr/bin/env python3
"""Step 2a — Variable Sweeps Round 1: {INSTRUMENT} {SESSION} LSI.

Anchor:
  n_left={LSI_N_LEFT}, n_right={LSI_N_RIGHT}, fvg_left={LSI_FVG_LEFT}, fvg_right={LSI_FVG_RIGHT}
  rr={RR}, tp1={TP1}, atr={ATR_LEN}, gap={MIN_GAP_ATR}%
  entry={ENTRY_START}-{ENTRY_END}, flat={FLAT_START}, dir={DIRECTION}

13 stand-alone dimensions swept once. No re-sweeping.
"""

import sys
import time
import datetime
from dataclasses import replace
from pathlib import Path
from statistics import median

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_dow_filter, apply_sma_trend_gate, apply_weekly_loss_cap, apply_monthly_loss_cap

# ── Config ────────────────────────────────────────────────────────────────────

START_DATE = "{START_DATE}"
DATA_YEARS = {DATA_YEARS}
CURRENT_PARTIAL_YEAR = "{CURRENT_PARTIAL_YEAR}"

INSTRUMENT = {INSTRUMENT_IMPORT}

SESSION = SessionConfig(
    name="{SESSION}",
    orb_start="09:30", orb_end="09:35",   # minimal — unused by LSI
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_START}",
    flat_end="{FLAT_END}",
    stop_atr_pct=0.0,        # unused — LSI uses structural stop
    min_gap_atr_pct={MIN_GAP_ATR},
)

ANCHOR = StrategyConfig(
    rr={RR},
    tp1_ratio={TP1},
    risk_usd=5000.0,
    atr_length={ATR_LEN},
    sessions=(SESSION,),
    instrument=INSTRUMENT,
    strategy="lsi",
    direction_filter="{DIRECTION}",
    use_bar_magnifier=True,
    lsi_n_left={LSI_N_LEFT},
    lsi_n_right={LSI_N_RIGHT},
    lsi_fvg_window_left={LSI_FVG_LEFT},
    lsi_fvg_window_right={LSI_FVG_RIGHT},
    lsi_stop_mode="absolute",
)

# ── Data ──────────────────────────────────────────────────────────────────────

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(INSTRUMENT.data_file, start=START_DATE)
df_1m = load_1m_for_5m(INSTRUMENT.data_file, start=START_DATE)
df_1s = load_1s_for_5m(INSTRUMENT.data_file, start=START_DATE)
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | "
      f"1s: {len(df_1s):,}" if df_1s is not None else "  1s: None")
print(f"  Loaded in {time.time() - t0:.1f}s")

# ── Helpers ───────────────────────────────────────────────────────────────────

def neg_years(m):
    return sum(1 for y, r in m.get("r_by_year", {}).items()
               if r < 0 and y != CURRENT_PARTIAL_YEAR)


def median_stop_ticks(trades):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return 0.0
    return median(t.risk_points / INSTRUMENT.min_tick for t in filled)


def run_and_measure(config, trades_override=None):
    if trades_override is not None:
        trades = trades_override
    else:
        trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    m["neg_full_years"] = neg_years(m)
    m["r_per_yr"] = m["total_r"] / DATA_YEARS
    m["median_stop_ticks"] = median_stop_ticks(trades)
    return m


def print_sweep_table(results, dim_name):
    print(f"\n{'─'*100}")
    print(f"  DIMENSION: {dim_name}")
    print(f"{'─'*100}")
    hdr = (f"  {'Value':<14} {'Trades':>7} {'WR':>7} {'PF':>6} {'Sharpe':>8} "
           f"{'Net R':>8} {'R/yr':>7} {'MaxDD':>8} {'Calmar':>8} {'NegYr':>6} {'MedStop':>8}")
    print(hdr)
    print(f"  {'-'*98}")
    for r in results:
        marker = " <<ANCHOR" if r.get("is_anchor") else ""
        skip = " SKIP(<10t)" if r.get("median_stop_ticks", 999) < 10 else ""
        print(
            f"  {str(r['value']):<14} "
            f"{r['total_trades']:>7} "
            f"{r['win_rate']:>6.1%} "
            f"{r['profit_factor']:>6.2f} "
            f"{r['sharpe_ratio']:>8.3f} "
            f"{r['total_r']:>8.1f} "
            f"{r['r_per_yr']:>7.1f} "
            f"{r['max_drawdown_r']:>8.1f} "
            f"{r['calmar_ratio']:>8.2f} "
            f"{r['neg_full_years']:>6} "
            f"{r.get('median_stop_ticks', 0):>7.0f}"
            f"{marker}{skip}"
        )

# ── Sweep functions ───────────────────────────────────────────────────────────

def sweep_direction():
    results = []
    for v in ["both", "long", "short"]:
        cfg = replace(ANCHOR, direction_filter=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.direction_filter)
        results.append(m)
    print_sweep_table(results, "Direction")
    return results


def sweep_lsi_n_left():
    results = []
    for v in [2, 3, 4, 5, 6, 8, 10]:
        cfg = replace(ANCHOR, lsi_n_left=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.lsi_n_left)
        results.append(m)
    print_sweep_table(results, "LSI N-Left (swing pivot left bars)")
    return results


def sweep_lsi_n_right():
    results = []
    for v in [2, 3, 4, 5, 6, 8, 10]:
        cfg = replace(ANCHOR, lsi_n_right=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.lsi_n_right)
        results.append(m)
    print_sweep_table(results, "LSI N-Right (swing pivot right bars / confirmation lag)")
    return results


def sweep_fvg_window_left():
    results = []
    for v in [3, 5, 7, 10, 15, 20]:
        cfg = replace(ANCHOR, lsi_fvg_window_left=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.lsi_fvg_window_left)
        results.append(m)
    print_sweep_table(results, "FVG Window Left (FVG formed BEFORE sweep, max bars back)")
    return results


def sweep_fvg_window_right():
    results = []
    for v in [3, 5, 7, 10, 15, 20]:
        cfg = replace(ANCHOR, lsi_fvg_window_right=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.lsi_fvg_window_right)
        results.append(m)
    print_sweep_table(results, "FVG Window Right (FVG formed AFTER sweep, max bars back)")
    return results


def sweep_min_gap_atr():
    results = []
    for v in [0.5, 1.0, 1.5, 2.25, 3.0, 4.0, 5.0]:
        sess = replace(SESSION, min_gap_atr_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == SESSION.min_gap_atr_pct)
        results.append(m)
    print_sweep_table(results, "Min Gap ATR %")
    return results


def sweep_atr_length():
    results = []
    for v in [5, 7, 10, 14, 20, 30]:
        cfg = replace(ANCHOR, atr_length=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.atr_length)
        results.append(m)
    print_sweep_table(results, "ATR Length")
    return results


def sweep_entry_start():
    results = []
    for v in ["09:35", "10:00", "10:30"]:
        sess = replace(SESSION, entry_start=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == SESSION.entry_start)
        results.append(m)
    print_sweep_table(results, "Entry Start Time")
    return results


def sweep_entry_end():
    results = []
    for v in ["11:00", "12:00", "13:00", "14:00", "15:30"]:
        sess = replace(SESSION, entry_end=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == SESSION.entry_end)
        results.append(m)
    print_sweep_table(results, "Entry End Time")
    return results


def sweep_dow_exclusion():
    # Run once, then filter post-backtest
    trades_all = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    exclusions = {
        "none": set(),
        "Mon": {0}, "Tue": {1}, "Wed": {2}, "Thu": {3}, "Fri": {4},
        "Mon+Fri": {0, 4}, "Thu+Fri": {3, 4},
    }
    results = []
    for label, excl_set in exclusions.items():
        filtered = apply_dow_filter(trades_all, excl_set) if excl_set else trades_all
        m = run_and_measure(ANCHOR, trades_override=filtered)
        m["value"] = label
        m["is_anchor"] = (label == "none")
        results.append(m)
    print_sweep_table(results, "DOW Exclusion")
    return results


def sweep_sma_trend_gate():
    trades_all = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    results = []
    for v in [None, 20, 50, 100, 200]:
        if v is None:
            filtered = trades_all
            label = "OFF"
        else:
            filtered = apply_sma_trend_gate(trades_all, df_5m, sma_period=v)
            label = str(v)
        m = run_and_measure(ANCHOR, trades_override=filtered)
        m["value"] = label
        m["is_anchor"] = (v is None)
        results.append(m)
    print_sweep_table(results, "SMA Trend Gate")
    return results


def sweep_weekly_loss_cap():
    trades_all = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    results = []
    for v in [None, 2.0, 3.0, 4.0, 5.0, 7.0]:
        if v is None:
            filtered = trades_all
            label = "OFF"
        else:
            filtered = apply_weekly_loss_cap(trades_all, cap_r=v)
            label = str(v)
        m = run_and_measure(ANCHOR, trades_override=filtered)
        m["value"] = label
        m["is_anchor"] = (v is None)
        results.append(m)
    print_sweep_table(results, "Weekly Loss Cap (R)")
    return results


def sweep_monthly_loss_cap():
    trades_all = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    results = []
    for v in [None, 3.0, 5.0, 7.0, 10.0, 15.0]:
        if v is None:
            filtered = trades_all
            label = "OFF"
        else:
            filtered = apply_monthly_loss_cap(trades_all, cap_r=v)
            label = str(v)
        m = run_and_measure(ANCHOR, trades_override=filtered)
        m["value"] = label
        m["is_anchor"] = (v is None)
        results.append(m)
    print_sweep_table(results, "Monthly Loss Cap (R)")
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 100)
    print(f"  {INSTRUMENT.symbol} {SESSION.name} LSI — VARIABLE SWEEPS ROUND {SWEEP_ROUND}")
    print(f"  Anchor: n_left={ANCHOR.lsi_n_left}, n_right={ANCHOR.lsi_n_right}, "
          f"fvg_left={ANCHOR.lsi_fvg_window_left}, fvg_right={ANCHOR.lsi_fvg_window_right}")
    print(f"          rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, atr={ANCHOR.atr_length}, "
          f"gap={SESSION.min_gap_atr_pct}%, dir={ANCHOR.direction_filter}")
    print("=" * 100)

    t_start = time.time()

    # Anchor baseline
    print("\nRunning anchor...")
    anchor_trades = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    anchor_m = run_and_measure(ANCHOR, trades_override=anchor_trades)
    filled = [t for t in anchor_trades if t.exit_type != EXIT_NO_FILL]
    if filled:
        ticks = [t.risk_points / INSTRUMENT.min_tick for t in filled]
        print(f"  Stop ticks — median: {np.median(ticks):.0f}, p10: {np.percentile(ticks,10):.0f}, p25: {np.percentile(ticks,25):.0f}")
    print(f"  Anchor: {anchor_m['total_trades']} trades, Calmar {anchor_m['calmar_ratio']:.2f}, "
          f"Net R {anchor_m['total_r']:.1f}, DD {anchor_m['max_drawdown_r']:.1f}, "
          f"Neg years {anchor_m['neg_full_years']}")

    anchor_calmar = anchor_m["calmar_ratio"]
    anchor_neg_years = anchor_m["neg_full_years"]

    SWEEP_ROUND = {SWEEP_ROUND}
    all_sweeps = {}

    print("\n[1/13] Direction...")
    all_sweeps["direction"] = sweep_direction()

    print("\n[2/13] LSI N-Left...")
    all_sweeps["lsi_n_left"] = sweep_lsi_n_left()

    print("\n[3/13] LSI N-Right...")
    all_sweeps["lsi_n_right"] = sweep_lsi_n_right()

    print("\n[4/13] FVG Window Left...")
    all_sweeps["fvg_window_left"] = sweep_fvg_window_left()

    print("\n[5/13] FVG Window Right...")
    all_sweeps["fvg_window_right"] = sweep_fvg_window_right()

    print("\n[6/13] Min Gap ATR %...")
    all_sweeps["min_gap_atr"] = sweep_min_gap_atr()

    print("\n[7/13] ATR Length...")
    all_sweeps["atr_length"] = sweep_atr_length()

    print("\n[8/13] Entry Start...")
    all_sweeps["entry_start"] = sweep_entry_start()

    print("\n[9/13] Entry End...")
    all_sweeps["entry_end"] = sweep_entry_end()

    print("\n[10/13] DOW Exclusion...")
    all_sweeps["dow_exclusion"] = sweep_dow_exclusion()

    print("\n[11/13] SMA Trend Gate...")
    all_sweeps["sma_trend_gate"] = sweep_sma_trend_gate()

    print("\n[12/13] Weekly Loss Cap...")
    all_sweeps["weekly_loss_cap"] = sweep_weekly_loss_cap()

    print("\n[13/13] Monthly Loss Cap...")
    all_sweeps["monthly_loss_cap"] = sweep_monthly_loss_cap()

    # ── Summary ───────────────────────────────────────────────────────────────

    print("\n" + "=" * 100)
    print("  ROUND {SWEEP_ROUND} SUMMARY — Adoption Decisions")
    print(f"  Anchor Calmar: {anchor_calmar:.2f} | Neg full years: {anchor_neg_years}")
    print("  Rule: delta Calmar > +0.3 AND no new neg years AND trades > 100 AND median stop >= 10t")
    print("=" * 100)

    adoptions = []
    hdr = (f"  {'Dimension':<22} {'Best Value':<14} {'Best Calmar':>12} "
           f"{'delta Cal':>10} {'Neg Yr':>8} {'Trades':>8} {'MedStop':>8} {'Decision':>12}")
    print(hdr)
    print(f"  {'-'*98}")

    for dim_name, results in all_sweeps.items():
        valid = [r for r in results if r.get("median_stop_ticks", 999) >= 10]
        if not valid:
            print(f"  {dim_name:<22} {'ALL SKIP':<14} {'---':>12} {'---':>10} {'---':>8} {'---':>8} {'---':>8} {'SKIP(<10t)':>12}")
            continue

        best = max(valid, key=lambda r: r["calmar_ratio"])
        anchor_row = next((r for r in results if r.get("is_anchor")), results[0])
        delta = best["calmar_ratio"] - anchor_row["calmar_ratio"]

        if dim_name in ("dow_exclusion", "sma_trend_gate", "weekly_loss_cap", "monthly_loss_cap"):
            decision_str = "  INFO-ONLY"
            adopt = False
        else:
            adopt = (
                delta > 0.3
                and best["neg_full_years"] <= anchor_neg_years
                and best["total_trades"] > 100
                and best.get("median_stop_ticks", 0) >= 10
            )
            decision_str = "-> ADOPT" if adopt else "  keep"

        if adopt:
            adoptions.append((dim_name, best["value"], best["calmar_ratio"], delta))

        print(
            f"  {dim_name:<22} {str(best['value']):<14} "
            f"{best['calmar_ratio']:>12.2f} "
            f"{delta:>+10.2f} "
            f"{best['neg_full_years']:>8} "
            f"{best['total_trades']:>8} "
            f"{best.get('median_stop_ticks', 0):>7.0f} "
            f"{decision_str:>12}"
        )

    print(f"\n  Total adoptions: {len(adoptions)}")
    if adoptions:
        print("\n  Adopted changes:")
        for dim, val, calmar, delta in adoptions:
            print(f"    {dim}: {val} (Calmar {calmar:.2f}, delta={delta:+.2f})")
        print(f"\n  -> Update anchor, then run core convergence sweeps (Round 2).")
    else:
        print(f"\n  -> No structural adoptions. Run core convergence loop (RR + TP1).")

    elapsed = time.time() - t_start
    print(f"\n  Total elapsed: {elapsed:.0f}s ({elapsed/60:.1f}m)")
```

---

## Core Convergence Template (`_variable_sweeps_2.py`, `_3.py`, etc.)

Only sweep RR and TP1. Use the same helpers as above. Replace the main block with:

```python
    all_sweeps = {}

    print(f"\n[1/2] R:R Ratio...")
    results = []
    for v in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        cfg = replace(ANCHOR, rr=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.rr)
        results.append(m)
    print_sweep_table(results, "R:R Ratio")
    all_sweeps["rr"] = results

    print(f"\n[2/2] TP1 Ratio (min 0.2)...")
    results = []
    for v in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
        cfg = replace(ANCHOR, tp1_ratio=v)
        m = run_and_measure(cfg)
        m["value"] = v
        m["is_anchor"] = (v == ANCHOR.tp1_ratio)
        results.append(m)
    print_sweep_table(results, "TP1 Ratio")
    all_sweeps["tp1_ratio"] = results
```

Print summary with the same adoption logic. Print "CONVERGED — Ready for grid sweep." if 0 adoptions.
