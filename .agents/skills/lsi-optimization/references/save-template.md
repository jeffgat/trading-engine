# Save Final Config Script Template

This template generates a script that saves a finalized (optimized) config to the experiments DB.
Placeholders are wrapped in `{CURLY_BRACES}` and get filled in at generation time.

```python
#!/usr/bin/env python3
"""{EXPERIMENT_NAME} — save to experiments DB.

{NOTES}
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

DOW_EXCL = {EXCLUDED_DAYS_SET}  # day-of-week exclusions (0=Mon, 4=Fri)

SESS = SessionConfig(
    name="{SESSION_UPPER}",
    orb_start="{ORB_START}",
    orb_end="{ORB_END}",
    entry_start="{ORB_END}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_TIME}",
    flat_end="{FLAT_END}",
    stop_atr_pct={STOP_ATR},
    min_gap_atr_pct={MIN_GAP_ATR},
    max_gap_points={MAX_GAP_POINTS},
    max_gap_atr_pct={MAX_GAP_ATR},
)

CONFIG = StrategyConfig(
    sessions=(SESS,),
    instrument={INSTRUMENT_IMPORT},
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="{DIRECTION}",
    rr={RR_RATIO},
    tp1_ratio={TP1_RATIO},
    atr_length={ATR_PERIOD},
    name="{EXPERIMENT_NAME}",
    notes=(
        "{NOTES}"
    ),
)

START_DATE = "{START_DATE}"


def main():
    print("Saving {EXPERIMENT_NAME} to DB")
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

    if DOW_EXCL:
        from orb_backtest.analysis.gates import apply_dow_filter
        trades = apply_dow_filter(trades, DOW_EXCL)

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

    result = results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)

    print(f"\n  Saved as: {result_id}")
    print(f"  Total runtime: {time.time() - t0:.0f}s")


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
| `{STOP_ATR}` | 3.0 | Stop distance as % of daily ATR |
| `{RR_RATIO}` | 2.0 | Risk-reward ratio |
| `{TP1_RATIO}` | 0.5 | Fraction taken at first take-profit |
| `{MIN_GAP_ATR}` | 0.5 | Min FVG size as % of daily ATR |
| `{MAX_GAP_ATR}` | 0.0 | Max FVG size as % of daily ATR (0 = no limit) |
| `{MAX_GAP_POINTS}` | 100.0, 50.0 | Max FVG size in points |
| `{ATR_PERIOD}` | 14 | ATR lookback length |
| `{DIRECTION}` | "both", "long", "short" | Direction filter |
| `{EXCLUDED_DAYS_SET}` | `set()` (none), `{3}` (Wed), `{0, 4}` (Mon+Fri) | Set literal for DOW exclusions (0=Mon ... 6=Sun) |
| `{DATA_FILE_5M}` | ES_5m.csv | Filename passed to loader |
| `{START_DATE}` | 2016-01-01 | Backtest start date |
| `{EXPERIMENT_NAME}` | ES Asia R5 Final | Follows CLAUDE.md naming convention |
| `{NOTES}` | Final config from R1-R5... | Description of what this config represents |
