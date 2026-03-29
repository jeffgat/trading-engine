# VWAP Save Final Config Script Template

This template generates a script that saves a finalized VWAP config to the experiments DB.
Placeholders are wrapped in `{CURLY_BRACES}` and get filled in at generation time.

```python
#!/usr/bin/env python3
"""{EXPERIMENT_NAME} -- save to experiments DB.

{NOTES}
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.vwap_config import VWAPSessionConfig, VWAPStrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.results.export import vwap_results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

DOW_EXCL = {EXCLUDED_DAYS_SET}  # day-of-week exclusions (0=Mon, 4=Fri)

SESS = VWAPSessionConfig(
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
    stop_atr_pct={STOP_ATR},
)

CONFIG = VWAPStrategyConfig(
    sessions=(SESS,),
    instrument={INSTRUMENT_IMPORT},
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="{DIRECTION}",
    rr={RR_RATIO},
    tp1_ratio={TP1_RATIO},
    tp2_mode="{TP2_MODE}",
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
        print("  WARNING: 1m data not found -- using 5m only")
        df_1m = None
    try:
        df_1s = load_1s_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1s data not found -- skipping")
        df_1s = None
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | 1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time() - t0:.1f}s]")

    print("\nRunning VWAP backtest...")
    t_bt = time.time()
    trades = run_vwap_backtest(df_5m, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)

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
        from datetime import datetime
        neg_years = [yr for yr, r in years if r < 0 and str(yr) != str(datetime.now().year)]
        print(f"  Negative full years: {neg_years if neg_years else 'none'}")

    result = vwap_results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)

    print(f"\n  Saved as: {result_id}")
    print(f"  Total runtime: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
```

## Placeholders

| Placeholder | Example | Description |
|---|---|---|
| `{INSTRUMENT}` | NQ | Instrument symbol |
| `{INSTRUMENT_IMPORT}` | NQ | Python import name |
| `{SESSION_UPPER}` | NY | Session name |
| `{SESSION_OPEN}` | "09:30" | Session open |
| `{ENTRY_START}` | "09:35" | Entry window start |
| `{ENTRY_END}` | "12:00" | Entry window end |
| `{FLAT_START}` | "15:50" | Flat time |
| `{FLAT_END}` | "16:00" | Session close |
| `{DEV_MODE}` | "atr" | Deviation mode |
| `{DEV_ATR_PCT}` | 30.0 | Deviation ATR % |
| `{DEV_STD}` | 2.0 | Deviation std |
| `{REJECTION_MODE}` | "close" | Rejection mode |
| `{STOP_ATR}` | 3.0 | Stop buffer % |
| `{RR_RATIO}` | 2.5 | Risk-reward |
| `{TP1_RATIO}` | 0.5 | TP1 ratio |
| `{TP2_MODE}` | "fixed_rr" | TP2 mode |
| `{ATR_PERIOD}` | 14 | ATR length |
| `{DIRECTION}` | "both" | Direction filter |
| `{EXCLUDED_DAYS_SET}` | `set()` or `{3}` | DOW exclusions |
| `{DATA_FILE_5M}` | NQ_5m.csv | Data file |
| `{START_DATE}` | 2016-01-01 | Start date |
| `{EXPERIMENT_NAME}` | NQ NY VWAP R1 Final | Experiment name |
| `{NOTES}` | Final config from... | Description |
