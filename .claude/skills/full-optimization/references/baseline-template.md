# Baseline Script Template

This template generates a baseline backtest script for a given instrument/session.
Placeholders are wrapped in `{CURLY_BRACES}` and get filled in at generation time.

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} Baseline — default params, full history."""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

SESS = SessionConfig(
    name="{SESSION_UPPER}",
    orb_start="{ORB_START}",
    orb_end="{ORB_END}",
    entry_start="{ORB_END}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_TIME}",
    flat_end="{FLAT_END}",
    stop_atr_pct={STOP_ATR_DEFAULT},
    min_gap_atr_pct={MIN_GAP_ATR_DEFAULT},
    max_gap_points={MAX_GAP_POINTS},
    max_gap_atr_pct=0.0,
)

CONFIG = StrategyConfig(
    sessions=(SESS,),
    instrument={INSTRUMENT_IMPORT},
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=2.5,
    tp1_ratio=0.5,
    atr_length=14,
    name="{INSTRUMENT} {SESSION_UPPER} Baseline",
)

START_DATE = "{START_DATE}"


def median_stop_ticks(trades):
    """Median stop distance in ticks. Configs with < 10 ticks are rejected."""
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / {INSTRUMENT_IMPORT}.tick_size for t in filled)


def main():
    print("{INSTRUMENT} {SESSION_UPPER} Baseline")
    print("=" * 60)

    print("\nLoading data...")
    t0 = time.time()
    df_5m = load_5m_data("{DATA_FILE_5M}")
    try:
        df_1m = load_1m_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1m data not found — using 5m only")
        df_1m = None
    try:
        df_1s = load_1s_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1s data not found — skipping")
        df_1s = None
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | 1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time() - t0:.1f}s]")

    print("\nRunning backtest...")
    t_bt = time.time()
    trades = run_backtest(df_5m, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    print(f"  Done [{time.time() - t_bt:.1f}s]")

    m = compute_metrics(trades)
    print(f"\n  Trades:   {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  PF:       {m['profit_factor']:.2f}")
    print(f"  Sharpe:   {m['sharpe_ratio']:.2f}")
    print(f"  Net R:    {m['total_r']:.1f}")
    print(f"  Max DD:   {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar:   {m['calmar_ratio']:.2f}")

    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"  R by year: {yr_str}")
        neg_years = [yr for yr, r in years if r < 0 and str(yr) != "2026"]
        print(f"  Negative full years: {neg_years if neg_years else 'none'}")

    # ── 10-tick minimum stop check ────────────────────────────────
    med_ticks = median_stop_ticks(trades)
    print(f"\n  Median stop: {med_ticks:.1f} ticks")

    # ── PASS / FAIL gate ──────────────────────────────────────────
    enough_trades = m["total_trades"] >= 100
    profitable = m["profit_factor"] > 1.0
    stop_ok = med_ticks >= 10
    verdict = "PASS" if (enough_trades and profitable and stop_ok) else "FAIL"
    print(f"\n  Baseline verdict: {verdict}")
    if not enough_trades:
        print(f"    FAIL: only {m['total_trades']} trades (need >= 100)")
    if not profitable:
        print(f"    FAIL: PF {m['profit_factor']:.2f} (need > 1.0)")
    if not stop_ok:
        print(f"    FAIL: median stop {med_ticks:.1f} ticks (need >= 10)")

    print(f"\n  Total runtime: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
```

## Placeholders

| Placeholder | Example | Description |
|---|---|---|
| `{INSTRUMENT}` | ES | Instrument symbol |
| `{INSTRUMENT_IMPORT}` | ES, SIX_B | Python import name from instruments.py |
| `{SESSION_UPPER}` | NY, ASIA, LDN | Session name for display and SessionConfig |
| `{ORB_START}` | "09:30" | ORB window start time |
| `{ORB_END}` | "09:45" | ORB window end time (also entry_start) |
| `{ENTRY_END}` | "12:00" | Last time an FVG entry can fill |
| `{FLAT_TIME}` | "15:50" | Flatten all positions |
| `{FLAT_END}` | "16:00" | Session close |
| `{MAX_GAP_POINTS}` | 100.0, 50.0 | Max FVG size in points |
| `{STOP_ATR_DEFAULT}` | `7.5` (NY), `5.25` (Asia) | Default stop ATR % for this session |
| `{MIN_GAP_ATR_DEFAULT}` | `2.25` (NY), `0.9` (Asia) | Default min gap ATR % for this session |
| `{DATA_FILE_5M}` | ES_5m.csv | Filename passed to loader |
| `{START_DATE}` | 2016-01-01 | Backtest start date |
