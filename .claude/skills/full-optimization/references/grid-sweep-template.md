# Grid Sweep Script Template

This template generates a 4D grid sweep script for a given instrument/session.
Placeholders are wrapped in `{CURLY_BRACES}` and get filled in at generation time.

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} Grid Sweep {ROUND_LABEL} -- 4D grid centered on anchor.

Anchor (from variable sweeps):
  ORB: {ORB_START}-{ORB_END}, entry until {ENTRY_END}, flat {FLAT_START}-{FLAT_END}
  stop={ANCHOR_STOP}%, rr={ANCHOR_RR}, gap={ANCHOR_GAP}%, tp1={ANCHOR_TP1}
  ATR={ATR_PERIOD}, direction={DIRECTION}, ICF={ICF_STATE}, {STRATEGY}, 1s magnifier
  {EXTRA_ANCHOR_NOTES}

Grid: stop x rr x gap x tp1
If winner differs from anchor (Calmar delta > 0.5) -> re-run variable sweeps.
"""

import sys
import time
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from itertools import product

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "{START_DATE}"
START_YEAR = str({START_YEAR})  # partial year to exclude from neg-year count
INSTRUMENT_NAME = "{INSTRUMENT}"
SESSION_NAME = "{SESSION_UPPER}"

ANCHOR_SESSION = SessionConfig(
    name="{SESSION_UPPER}",
    orb_start="{ORB_START}",
    orb_end="{ORB_END}",
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_START}",
    flat_end="{FLAT_END}",
    stop_atr_pct={ANCHOR_STOP},
    min_gap_atr_pct={ANCHOR_GAP},
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
    rr={ANCHOR_RR},
    tp1_ratio={ANCHOR_TP1},
    atr_length={ATR_PERIOD},
    impulse_close_filter={ICF_BOOL},
    name="{INSTRUMENT} {SESSION_UPPER} Grid Sweep {ROUND_LABEL}",
)

# Grid dimensions -- narrow range centered on anchor
STOPS = {STOP_GRID}
RRS   = {RR_GRID}
GAPS  = {GAP_GRID}
TP1S  = {TP1_GRID}

GRID = list(product(STOPS, RRS, GAPS, TP1S))
print(f"Grid size: {len(GRID)} combos ({len(STOPS)}x{len(RRS)}x{len(GAPS)}x{len(TP1S)})")


def neg_year_set(rby: dict) -> set:
    """Return set of full calendar years with negative R (exclude current year)."""
    current_year = str(datetime.now().year)
    return {yr for yr, r in rby.items() if r < 0 and str(yr) != current_year}


def main():
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} -- Grid Sweep ({len(GRID)} combos)")
    print("=" * 110)
    print(f"Anchor: stop={ANCHOR_STOP}%, rr={ANCHOR_RR}, gap={ANCHOR_GAP}%, tp1={ANCHOR_TP1}")
    print(f"Grid: stop={STOPS} x rr={RRS} x gap={GAPS} x tp1={TP1S}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("{DATA_FILE_5M}")
    try:
        df_1m = load_1m_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1m data not found — using 5m only")
        df_1m = None
    df_1s = load_1s_for_5m("{DATA_FILE_5M}")  # returns None if missing
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | 1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time() - t0:.1f}s]")

    results = []
    t_start = time.time()

    for i, (stop, rr, gap, tp1) in enumerate(GRID):
        sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
        cfg = replace(ANCHOR, sessions=(sess,), rr=rr, tp1_ratio=tp1)
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)

        rby = m.get("r_by_year", {})
        full_years = {y: r for y, r in rby.items() if y not in (START_YEAR, str(datetime.now().year))}
        neg_yrs = sum(1 for r in full_years.values() if r < 0)
        n_years = max(len(full_years), 1)
        calmar = m.get("calmar_ratio", 0)

        results.append({
            "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
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

    # Sort by Calmar
    results.sort(key=lambda x: x["calmar"], reverse=True)

    # -- Top 20 overall --
    HDR = (f"  {'#':>4} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>4} "
           f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
           f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")

    print(f"\n{'='*110}")
    print(f"  TOP 20 BY CALMAR")
    print(f"{'='*110}")
    print(HDR)
    print(f"  {'-'*105}")

    for rank, r in enumerate(results[:20], 1):
        is_anchor = (abs(r["stop"] - {ANCHOR_STOP}) < 0.01 and abs(r["rr"] - {ANCHOR_RR}) < 0.01
                     and abs(r["gap"] - {ANCHOR_GAP}) < 0.01 and abs(r["tp1"] - {ANCHOR_TP1}) < 0.01)
        marker = " <<< ANCHOR" if is_anchor else ""
        print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.2f} {r['gap']:>5.2f} {r['tp1']:>4.2f} "
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
    if winner["gap"] in (GAPS[0], GAPS[-1]):
        edge_warnings.append(f"gap={winner['gap']}")
    if winner["tp1"] in (TP1S[0], TP1S[-1]):
        edge_warnings.append(f"tp1={winner['tp1']}")
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
                         and abs(r["gap"] - {ANCHOR_GAP}) < 0.01 and abs(r["tp1"] - {ANCHOR_TP1}) < 0.01)
            marker = " <<< ANCHOR" if is_anchor else ""
            print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.2f} {r['gap']:>5.2f} {r['tp1']:>4.2f} "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
                  f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
                  f"{r['calmar']:>7.2f} {r['neg_yrs']:>3}{marker}")
            if rank <= 5:
                years = sorted(r["r_by_year"].items())
                yr_str = "  ".join(f"{yr}:{v:+.0f}" for yr, v in years)
                print(f"        R by year: {yr_str}")

    # -- Anchor rank --
    anchor_rank = None
    for rank, r in enumerate(results, 1):
        if (abs(r["stop"] - {ANCHOR_STOP}) < 0.01 and abs(r["rr"] - {ANCHOR_RR}) < 0.01
                and abs(r["gap"] - {ANCHOR_GAP}) < 0.01 and abs(r["tp1"] - {ANCHOR_TP1}) < 0.01):
            anchor_rank = rank
            anchor_calmar = r["calmar"]
            break
    if anchor_rank:
        print(f"\n  Anchor rank: #{anchor_rank}/{len(results)} (Calmar {anchor_calmar:.2f})")

    # -- Dimension dominance (top 20) --
    print(f"\n{'='*110}")
    print(f"  DIMENSION DOMINANCE (top 20)")
    print(f"{'='*110}")
    for dim_name, dim_values, dim_key in [
        ("stop", STOPS, "stop"), ("rr", RRS, "rr"),
        ("gap", GAPS, "gap"), ("tp1", TP1S, "tp1"),
    ]:
        counts = defaultdict(int)
        for r in results[:20]:
            counts[r[dim_key]] += 1
        parts = "  ".join(f"{v}={counts.get(v, 0)}" for v in dim_values)
        print(f"  {dim_name}: {parts}")

    # -- Decision --
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
| `{INSTRUMENT}` | ES | Instrument symbol (display) |
| `{INSTRUMENT_IMPORT}` | ES, SIX_B, RTY | Python import name from `instruments.py` |
| `{SESSION_UPPER}` | NY, ASIA, LDN | Session name for display and SessionConfig |
| `{ROUND_LABEL}` | R1, R2, R3 | Grid sweep round number |
| `{STRATEGY}` | continuation, reversal, inversion | Strategy type |
| `{DIRECTION}` | both, long, short | Direction filter |
| `{ORB_START}` | "09:30" | ORB window start time |
| `{ORB_END}` | "09:45" | ORB window end time |
| `{ENTRY_START}` | "09:45" | Entry window start (usually same as ORB_END) |
| `{ENTRY_END}` | "12:00" | Last time an FVG entry can fill |
| `{FLAT_START}` | "15:50" | Flatten all positions |
| `{FLAT_END}` | "16:00" | Session close |
| `{ANCHOR_STOP}` | 3.0 | Anchor stop_atr_pct value |
| `{ANCHOR_RR}` | 2.0 | Anchor rr value |
| `{ANCHOR_GAP}` | 0.5 | Anchor min_gap_atr_pct value |
| `{ANCHOR_TP1}` | 0.5 | Anchor tp1_ratio value |
| `{MAX_GAP_POINTS}` | 50.0 | Max FVG size in points (0 = no limit) |
| `{MAX_GAP_ATR}` | 0.0 | Max FVG size as % of ATR (0 = no limit) |
| `{ATR_PERIOD}` | 14 | ATR lookback period |
| `{ICF_BOOL}` | True, False | Impulse close filter on/off |
| `{ICF_STATE}` | ON, OFF | Impulse close filter display label |
| `{DATA_FILE_5M}` | ES_5m.csv | Filename passed to loader |
| `{START_DATE}` | 2016-01-01 | Backtest start date |
| `{START_YEAR}` | `2016` | First year of data (partial year excluded from neg-year count). Substituted as an integer, converted to string internally to match `r_by_year` keys. |
| `{STOP_GRID}` | [2.0, 2.5, 3.0, 3.5, 4.0] | List of stop_atr_pct values to sweep |
| `{RR_GRID}` | [1.5, 2.0, 2.5, 3.0] | List of rr values to sweep |
| `{GAP_GRID}` | [0.25, 0.5, 0.75, 1.0] | List of min_gap_atr_pct values to sweep |
| `{TP1_GRID}` | [0.3, 0.4, 0.5, 0.6] | List of tp1_ratio values to sweep |
| `{EXTRA_ANCHOR_NOTES}` | DOW gate: excl Thu | Optional extra notes about the anchor config |

## Grid Sizing Guidelines

Aim for 200-600 total combinations. Typical ranges centered on anchor:

| Dimension | Typical grid | Notes |
|---|---|---|
| `stop_atr_pct` | 4-6 values, +/-1.0 around anchor | e.g., anchor=3.0 -> [2.0, 2.5, 3.0, 3.5, 4.0] |
| `rr` | 4-6 values, +/-1.0 around anchor | e.g., anchor=2.0 -> [1.5, 1.75, 2.0, 2.5, 3.0] |
| `min_gap_atr_pct` | 3-4 values, +/-0.25 around anchor | e.g., anchor=0.5 -> [0.25, 0.5, 0.75, 1.0] |
| `tp1_ratio` | 3-4 values, +/-0.1 around anchor | e.g., anchor=0.5 -> [0.3, 0.4, 0.5, 0.6] |

## Optional Extensions

### DOW Filter

If the anchor uses a day-of-week exclusion, add the filter after `run_backtest`:

```python
from orb_backtest.analysis.gates import apply_dow_filter

DOW_EXCL = {3}  # e.g., exclude Thursday (0=Mon, 6=Sun)

# Inside the grid loop, after run_backtest:
trades = apply_dow_filter(trades, DOW_EXCL)
```

### 5th Dimension (entry_end)

To add `entry_end` as a grid dimension:

```python
ENTRY_ENDS = ["12:00", "13:00", "14:00", "15:30"]
GRID = list(product(STOPS, RRS, GAPS, TP1S, ENTRY_ENDS))

# Inside the grid loop:
for i, (stop, rr, gap, tp1, ee) in enumerate(GRID):
    sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap, entry_end=ee)
    # ...add "ee" to results dict and printout columns
```

### No 1s Data Available

If the instrument does not have 1-second data, remove `df_1s` references:

```python
# Load only 5m and 1m
df_5m = load_5m_data("{DATA_FILE_5M}")
df_1m = load_1m_for_5m("{DATA_FILE_5M}")

# Run without df_1s
trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m)
```
