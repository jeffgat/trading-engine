# VWAP Grid Sweep Script Template

This template generates a grid sweep script for VWAP strategy optimization.
Grid dimensionality depends on tp2_mode. Placeholders are wrapped in `{CURLY_BRACES}`.

## Fixed RR Mode (tp2_mode="fixed_rr") -- 4D Grid

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} VWAP Grid Sweep {ROUND_LABEL} -- 4D grid centered on anchor.

Anchor (from variable sweeps):
  entry {ENTRY_START}-{ENTRY_END}, flat {FLAT_START}-{FLAT_END}
  dev_mode={DEV_MODE}, dev_thresh={DEV_THRESH}, rejection={REJECTION_MODE}
  stop_buf={ANCHOR_STOP}%, rr={ANCHOR_RR}, tp1={ANCHOR_TP1}, tp2=fixed_rr
  ATR={ATR_PERIOD}, direction={DIRECTION}, bar magnifier
  {EXTRA_ANCHOR_NOTES}

Grid: stop_buffer x rr x tp1 x deviation_threshold
If winner differs from anchor (Calmar delta > 0.5) -> re-run variable sweeps.
"""

import sys
import time
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from itertools import product

sys.path.insert(0, "src")

from orb_backtest.vwap_config import VWAPSessionConfig, VWAPStrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "{START_DATE}"
START_YEAR = str({START_YEAR})
INSTRUMENT_NAME = "{INSTRUMENT}"
SESSION_NAME = "{SESSION_UPPER}"

ANCHOR_SESSION = VWAPSessionConfig(
    name="{SESSION_UPPER}",
    session_open="{SESSION_OPEN}",
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_START}",
    flat_end="{FLAT_END}",
    deviation_mode="{DEV_MODE}",
    deviation_atr_pct={DEV_ATR_PCT},
    deviation_std={DEV_STD},
    rejection_mode="{REJECTION_MODE}",
    stop_atr_pct={ANCHOR_STOP},
)

ANCHOR = VWAPStrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument={INSTRUMENT_IMPORT},
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="{DIRECTION}",
    rr={ANCHOR_RR},
    tp1_ratio={ANCHOR_TP1},
    tp2_mode="fixed_rr",
    atr_length={ATR_PERIOD},
    name="{INSTRUMENT} {SESSION_UPPER} VWAP Grid Sweep {ROUND_LABEL}",
)

# Grid dimensions -- narrow range centered on anchor
STOPS    = {STOP_GRID}       # stop_atr_pct values
RRS      = {RR_GRID}         # rr values
TP1S     = {TP1_GRID}        # tp1_ratio values
DEV_VALS = {DEV_GRID}        # deviation_atr_pct or deviation_std values

GRID = list(product(STOPS, RRS, TP1S, DEV_VALS))
print(f"Grid size: {len(GRID)} combos ({len(STOPS)}x{len(RRS)}x{len(TP1S)}x{len(DEV_VALS)})")

MIN_STOP_TICKS = 10
MIN_TP1 = 0.2


def median_stop_ticks(trades):
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / {INSTRUMENT_IMPORT}.min_tick for t in filled)


def neg_year_set(rby: dict) -> set:
    current_year = str(datetime.now().year)
    return {yr for yr, r in rby.items() if r < 0 and str(yr) != current_year}


def main():
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} VWAP -- Grid Sweep ({len(GRID)} combos)")
    print("=" * 110)
    print(f"Anchor: stop={ANCHOR_STOP}%, rr={ANCHOR_RR}, tp1={ANCHOR_TP1}, dev={DEV_THRESH}")
    print(f"Grid: stop={STOPS} x rr={RRS} x tp1={TP1S} x dev={DEV_VALS}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("{DATA_FILE_5M}")
    try:
        df_1m = load_1m_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1m data not found -- using 5m only")
        df_1m = None
    df_1s = load_1s_for_5m("{DATA_FILE_5M}")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | 1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time() - t0:.1f}s]")

    results = []
    skipped_ticks = 0
    skipped_tp1 = 0
    t_start = time.time()

    for i, (stop, rr, tp1, dev) in enumerate(GRID):
        if tp1 < MIN_TP1:
            skipped_tp1 += 1
            continue
        # Update session with stop buffer and deviation threshold
        # MANDATORY: Replace the line below based on deviation_mode:
        #   If deviation_mode == "atr":  sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, deviation_atr_pct=dev)
        #   If deviation_mode == "std":  sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, deviation_std=dev)
        sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, deviation_atr_pct=dev)  # <- change to deviation_std if mode="std"
        cfg = replace(ANCHOR, sessions=(sess,), rr=rr, tp1_ratio=tp1)
        trades = run_vwap_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        if median_stop_ticks(trades) < MIN_STOP_TICKS:
            skipped_ticks += 1
            continue
        m = compute_metrics(trades)

        rby = m.get("r_by_year", {})
        full_years = {y: r for y, r in rby.items() if y not in (START_YEAR, str(datetime.now().year))}
        neg_yrs = sum(1 for r in full_years.values() if r < 0)
        n_years = max(len(full_years), 1)
        calmar = m.get("calmar_ratio", 0)

        results.append({
            "stop": stop, "rr": rr, "tp1": tp1, "dev": dev,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
            "net_r": m["total_r"], "avg_annual": m["total_r"] / n_years,
            "max_dd": m["max_drawdown_r"], "calmar": calmar,
            "neg_yrs": neg_yrs,
            "neg_list": ",".join(y for y, r in sorted(full_years.items()) if r < 0),
            "r_by_year": rby,
        })

        if (i + 1) % 50 == 0 or i == len(GRID) - 1:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed
            eta = (len(GRID) - i - 1) / rate
            print(f"  {i+1}/{len(GRID)} done [{elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s]")

    total_time = time.time() - t_start
    print(f"\n  Grid complete in {total_time:.1f}s ({total_time / 60:.1f}m)")
    print(f"  Skipped: {skipped_ticks} (<10 tick stop), {skipped_tp1} (tp1 < {MIN_TP1})")

    results.sort(key=lambda x: x["calmar"], reverse=True)

    # -- Top 20 overall --
    HDR = (f"  {'#':>4} {'Stop':>5} {'RR':>4} {'TP1':>4} {'Dev':>5} "
           f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
           f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")

    print(f"\n{'='*110}")
    print(f"  TOP 20 BY CALMAR")
    print(f"{'='*110}")
    print(HDR)
    print(f"  {'-'*105}")

    for rank, r in enumerate(results[:20], 1):
        is_anchor = (abs(r["stop"] - {ANCHOR_STOP}) < 0.01 and abs(r["rr"] - {ANCHOR_RR}) < 0.01
                     and abs(r["tp1"] - {ANCHOR_TP1}) < 0.01 and abs(r["dev"] - {DEV_THRESH_NUM}) < 0.01)
        marker = " <<< ANCHOR" if is_anchor else ""
        print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.2f} {r['tp1']:>4.2f} {r['dev']:>5.1f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
              f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
              f"{r['calmar']:>7.2f} {r['neg_yrs']:>3} {r['neg_list']}{marker}")
        if rank <= 5:
            years = sorted(r["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{v:+.0f}" for yr, v in years)
            print(f"        R by year: {yr_str}")

    # Warn if winner is at grid boundary
    winner = results[0]
    edge_warnings = []
    if winner["stop"] in (STOPS[0], STOPS[-1]):
        edge_warnings.append(f"stop={winner['stop']}")
    if winner["rr"] in (RRS[0], RRS[-1]):
        edge_warnings.append(f"rr={winner['rr']}")
    if winner["tp1"] in (TP1S[0], TP1S[-1]):
        edge_warnings.append(f"tp1={winner['tp1']}")
    if winner["dev"] in (DEV_VALS[0], DEV_VALS[-1]):
        edge_warnings.append(f"dev={winner['dev']}")
    if edge_warnings:
        print(f"\n  WARNING: Winner at grid boundary on: {', '.join(edge_warnings)}")
        print("  Consider expanding the grid in those dimensions before trusting this result.")

    # -- Top 20 with 0 negative years --
    zero_neg = [r for r in results if r["neg_yrs"] == 0]
    print(f"\n  Combos with 0 negative years: {len(zero_neg)}/{len(results)}")
    if zero_neg:
        print(f"\n{'='*110}")
        print(f"  TOP 20 WITH 0 NEGATIVE YEARS (by Calmar)")
        print(f"{'='*110}")
        print(HDR)
        print(f"  {'-'*105}")
        for rank, r in enumerate(zero_neg[:20], 1):
            is_anchor = (abs(r["stop"] - {ANCHOR_STOP}) < 0.01 and abs(r["rr"] - {ANCHOR_RR}) < 0.01
                         and abs(r["tp1"] - {ANCHOR_TP1}) < 0.01 and abs(r["dev"] - {DEV_THRESH_NUM}) < 0.01)
            marker = " <<< ANCHOR" if is_anchor else ""
            print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.2f} {r['tp1']:>4.2f} {r['dev']:>5.1f} "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
                  f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
                  f"{r['calmar']:>7.2f} {r['neg_yrs']:>3}{marker}")
            if rank <= 5:
                years = sorted(r["r_by_year"].items())
                yr_str = "  ".join(f"{yr}:{v:+.0f}" for yr, v in years)
                print(f"        R by year: {yr_str}")

    # -- Dimension dominance (top 20) --
    print(f"\n{'='*110}")
    print(f"  DIMENSION DOMINANCE (top 20)")
    print(f"{'='*110}")
    for dim_name, dim_values, dim_key in [
        ("stop", STOPS, "stop"), ("rr", RRS, "rr"),
        ("tp1", TP1S, "tp1"), ("dev", DEV_VALS, "dev"),
    ]:
        counts = defaultdict(int)
        for r in results[:20]:
            counts[r[dim_key]] += 1
        parts = "  ".join(f"{v}={counts.get(v, 0)}" for v in dim_values)
        print(f"  {dim_name}: {parts}")

    # -- Decision --
    anchor_rank = None
    anchor_calmar = 0
    for rank, r in enumerate(results, 1):
        if (abs(r["stop"] - {ANCHOR_STOP}) < 0.01 and abs(r["rr"] - {ANCHOR_RR}) < 0.01
                and abs(r["tp1"] - {ANCHOR_TP1}) < 0.01 and abs(r["dev"] - {DEV_THRESH_NUM}) < 0.01):
            anchor_rank = rank
            anchor_calmar = r["calmar"]
            break
    if anchor_rank:
        print(f"\n  Anchor rank: #{anchor_rank}/{len(results)} (Calmar {anchor_calmar:.2f})")

    if results:
        winner_calmar = results[0]["calmar"]
        if anchor_rank and abs(winner_calmar - anchor_calmar) > 0.5:
            print(f"\n  *** GRID WINNER DIFFERS FROM ANCHOR (Calmar delta = "
                  f"{winner_calmar - anchor_calmar:+.2f}) ***")
            print(f"  --> Update anchor to grid winner and re-run variable sweeps")
        else:
            print(f"\n  Grid confirms anchor (Calmar delta <= 0.5). Proceed to robust pipeline.")

    print(f"\n  Total runtime: {total_time:.0f}s ({total_time / 60:.1f}m)")


if __name__ == "__main__":
    main()
```

## Placeholders

| Placeholder | Example | Description |
|---|---|---|
| `{INSTRUMENT}` | NQ | Instrument symbol |
| `{INSTRUMENT_IMPORT}` | NQ | Python import name |
| `{SESSION_UPPER}` | NY | Session name |
| `{SESSION_OPEN}` | "09:30" | Session open time |
| `{ROUND_LABEL}` | R1 | Grid sweep round |
| `{DIRECTION}` | both | Direction filter |
| `{ENTRY_START}` | "09:35" | Entry window start |
| `{ENTRY_END}` | "12:00" | Entry window end |
| `{FLAT_START}` | "15:50" | Flat time |
| `{FLAT_END}` | "16:00" | Session close |
| `{DEV_MODE}` | "atr" | Deviation mode |
| `{DEV_ATR_PCT}` | 30.0 | Deviation ATR % anchor |
| `{DEV_STD}` | 2.0 | Deviation std anchor |
| `{REJECTION_MODE}` | "close" | Rejection mode |
| `{ANCHOR_STOP}` | 3.0 | Stop buffer anchor |
| `{ANCHOR_RR}` | 2.5 | RR anchor |
| `{ANCHOR_TP1}` | 0.5 | TP1 anchor |
| `{DEV_THRESH}` | "atr=30%" | Display label for deviation threshold |
| `{DEV_THRESH_NUM}` | 30.0 | Numeric anchor value for deviation |
| `{DEV_FIELD}` | deviation_atr_pct | Field name to replace in session |
| `{ATR_PERIOD}` | 14 | ATR length |
| `{DATA_FILE_5M}` | NQ_5m.csv | Data file |
| `{START_DATE}` | 2016-01-01 | Start date |
| `{START_YEAR}` | 2016 | First year (partial excluded) |
| `{STOP_GRID}` | [1.0, 2.0, 3.0, 4.0, 5.0] | Stop buffer values |
| `{RR_GRID}` | [1.5, 2.0, 2.5, 3.0] | RR values |
| `{TP1_GRID}` | [0.3, 0.4, 0.5, 0.6] | TP1 values |
| `{DEV_GRID}` | [20, 25, 30, 35, 40] | Deviation threshold values |
| `{EXTRA_ANCHOR_NOTES}` | DOW gate: excl Thu | Optional notes |

## Grid Sizing Guidelines

Aim for 200-600 total combinations. Typical ranges centered on anchor:

| Dimension | Typical grid | Notes |
|---|---|---|
| `stop_atr_pct` | 4-6 values, +/-2 around anchor | e.g., anchor=3.0 -> [1.0, 2.0, 3.0, 4.0, 5.0] |
| `rr` | 4-6 values, +/-1.0 around anchor | e.g., anchor=2.5 -> [1.5, 2.0, 2.5, 3.0, 3.5] |
| `tp1_ratio` | 3-5 values, +/-0.1 around anchor | e.g., anchor=0.5 -> [0.3, 0.4, 0.5, 0.6] |
| `deviation_atr_pct` | 4-5 values, +/-10 around anchor | e.g., anchor=30 -> [15, 20, 25, 30, 40] |
| `deviation_std` | 3-5 values, +/-0.5 around anchor | e.g., anchor=2.0 -> [1.0, 1.5, 2.0, 2.5, 3.0] |

## VWAP TP2 Mode -- 3D Grid

When tp2_mode="vwap", RR has less direct impact (TP2 exits at VWAP touch). The grid may collapse
to 3D: stop_buffer x deviation_threshold x tp1. Remove RRS from the grid and adjust GRID accordingly:

```python
GRID = list(product(STOPS, TP1S, DEV_VALS))
# Adjust loop: for i, (stop, tp1, dev) in enumerate(GRID):
```
