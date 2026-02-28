# Drawdown Analysis

Analyzes a strategy's risk profile from a prop firm perspective. Takes trade results and produces four reports:

1. **Max DD by Year** — Per-year max drawdown with Safe/Close/DANGER verdicts against a configurable prop DD limit
2. **DD Episodes** — Every drawdown episode exceeding the prop limit, with start, trough, and recovery dates
3. **Consecutive Loss Analysis** — Worst losing streaks ranked by R lost, plus full streak length distribution
4. **Monthly R** — Month-by-month returns with best/worst months summary

## When to Use

Use this skill when the user asks to analyze a strategy's risk, prop firm viability, drawdown profile, losing streaks, or monthly performance. Triggers on: "drawdown analysis", "DD analysis", "losing streaks", "consecutive losses", "monthly R", "is this tradeable", "prop firm risk", "drawdown by year", "prop risk".

## How to Use

### Step 1: Get the trades

Run the strategy's backtest to get filled trades. Filter out `EXIT_NO_FILL` trades.

```python
import sys
sys.path.insert(0, "src")

from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
# ... load data, build config ...

trades = run_backtest(df, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
# Apply any post-backtest filters (DOW, etc.)
trades = apply_dow_filter(trades, DOW_EXCLUDED)
filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
```

### Step 2: Run the analysis

```python
# Add the skill scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude/skills/drawdown-analysis/scripts"))
from analyze import run_prop_risk_analysis

run_prop_risk_analysis(
    filled_trades=filled,
    prop_dd_limit=10.0,   # Prop firm DD limit in R
    label="ES LDN R12",   # Optional header label
)
```

### Step 3: Interpret the verdicts

| Verdict | Meaning | Threshold |
|---------|---------|-----------|
| **Safe** | Max DD stays well under limit | < 80% of prop DD limit |
| **Close** | Max DD approaches limit | 80-100% of prop DD limit |
| **DANGER** | Max DD breaches limit | >= 100% of prop DD limit |

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `prop_dd_limit` | 10.0 | Prop firm max drawdown in R. Determines Safe/Close/DANGER thresholds. |
| `label` | `""` | Strategy name shown in the header. |

### Individual Functions

The script also exports individual functions for programmatic use:

```python
from analyze import compute_year_dd, compute_losing_streaks, compute_dd_episodes

# Per-year DD: returns [(year, max_dd, net_r), ...]
year_data = compute_year_dd(trades_r_by_year_dict)

# Losing streaks: returns [(streak_len, r_lost, start, end), ...]
streaks = compute_losing_streaks(filled_trades)

# DD episodes: returns [(start, trough, max_dd, recovery), ...]
episodes = compute_dd_episodes(filled_trades, threshold=-10.0)
```

## Example Output

```
============================================================
  PROP RISK ANALYSIS — NQ Asia R5
  Prop DD limit: 10R
============================================================

  Max DD by Year (clean view)

  Year     Max DD    Net R  Verdict
  ------ -------- --------  ----------
  2016     -6.0R     +28R  Safe
  2017     -9.1R     +17R  Close
  2018     -8.7R     +22R  Close
  ...

  On a 10R prop account: 7 of 11 years stay safe (<-8R),
  3 years get close (-8 to -10R), and no years breach the limit.


============================================================
  DD EPISODES EXCEEDING -10R
============================================================

  None — max DD never exceeded -10R.


============================================================
  CONSECUTIVE LOSS ANALYSIS
============================================================

  WORST 10 LOSING STREAKS (by R lost):
  Losses   R Lost  Start         End
  ------ --------  ------------  ------------
       9   -8.2R  2022-09-08    2022-10-03
  ...

  Streak distribution:
    1 consecutive losses: 131 times
    2 consecutive losses: 75 times
    ...
```
