---
name: portfolio-month-optimizer
description: >
  Brute-force grid search to find optimal portfolio allocation for a specific calendar month.
  Sweeps all combinations of strategy risk sizes to minimize monthly drawdown while maximizing
  monthly returns. DD calculation matches the frontend's running-peak method exactly.
  Use when the user asks to "optimize portfolio for [month]", "find best allocation for [month]",
  "reduce [month] drawdown", "portfolio month optimizer", "monthly allocation grid search",
  or any request to find the risk-size combination that controls a specific month's DD.
---

# Portfolio Month Optimizer

Brute-force grid search that finds the optimal portfolio allocation for a specific calendar month. Sweeps all combinations of strategy risk sizes (e.g., $0/$50/$100/$150/$200/$250) to minimize that month's drawdown while maximizing that month's total R. The DD calculation matches the frontend's `computeCombinedMaxDrawdownByMonth` exactly: running cumR and peak persist across the entire trade history, never reset per month.

## Workflow

### Step 1: Collect Parameters

Gather from the user:

| Parameter | Required | Description |
|-----------|----------|-------------|
| **Month** | Yes | Which calendar month to optimize (1-12) |
| **Strategies** | Yes | Which strategies to include (names + result_file IDs) |
| **Current risk** | Yes | Current risk per strategy (e.g., $250, $0) |
| **Max DD threshold** | Yes | Maximum allowed DD in R for the target month (e.g., 8.0) |
| **Max violations** | Yes | How many years can exceed the threshold (e.g., 2) |
| **Risk levels** | No | Grid of risk values to test (default: [0, 50, 100, 150, 200, 250]) |
| **Year range** | Yes | Start and end year, both inclusive (e.g., [2016, 2025] tests 2016 through 2025) |

### Step 2: Build Config JSON

Create a JSON config file with the collected parameters. Each strategy needs:

```json
{
  "strategies": [
    {
      "name": "NQ NY Long ORB",
      "short": "NQ-NY",
      "result_file": "bt-nq-ny-cont-long-r11-final-2016-2026-aa7630",
      "base_scale": 1.0,
      "current_risk": 250
    }
  ],
  "month": 3,
  "max_dd_threshold": 8.0,
  "max_violations": 2,
  "risk_levels": [0, 50, 100, 150, 200, 250],
  "year_range": [2016, 2025],
  "chunk_size": 10000
}
```

**Fields:**
- `name`: Display name for the strategy
- `short`: Short label used in output tables (e.g., "NQ-NY", "GC-NY")
- `result_file`: The `result_file` column from the DB `runs` table (the unique hash-suffixed filename)
- `base_scale`: Normalization factor for R multiples. Use `1/N` if the strategy was backtested at `N x normal risk`. For example, if the backtest used `risk_usd=500` but all other strategies use `risk_usd=250`, set `base_scale: 0.5` to normalize to a common 250-unit baseline. Use `1.0` for strategies backtested at standard risk.
- `current_risk`: Current dollar risk for this strategy (used to show baseline comparison). Must be a value that appears in `risk_levels`.
- `risk_levels` (optional): Grid of risk values to sweep. Default `[0, 50, 100, 150, 200, 250]`
- `chunk_size` (optional): Vectorized chunk size for memory management. Default `10000`

### Step 3: Run the Optimizer

Write the config JSON to a temp file, then run:

```bash
cd python && uv run python ../.claude/skills/portfolio-month-optimizer/scripts/optimize_month.py /path/to/config.json
```

The script will:
1. Load trades for all strategies from `experiments.db`
2. Merge into a single sorted timeline
3. Compute month DD via chunked vectorized equity curves
4. Filter combos by violation count, rank by total month R
5. Print current setup baseline, top 20 combos, and summary

### Step 4: Present Results

Show the user:
1. **Current setup** vs **recommended #1** — highlight which strategies changed risk levels
2. **DD improvement** — current month DD row vs recommended month DD row
3. **R impact** — how total month R changes
4. **Trade-offs** — if strategies were reduced to $0, note the loss of those trades entirely

## Finding Strategy IDs

If the user doesn't know their `result_file` IDs, query the DB:

```sql
-- List starred/recent backtests
SELECT result_file, instrument, name, created_at
FROM runs
WHERE run_type = 'backtest' AND starred = 1
ORDER BY created_at DESC;

-- Or search by instrument
SELECT result_file, name, created_at
FROM runs
WHERE run_type = 'backtest' AND instrument = 'NQ'
ORDER BY created_at DESC
LIMIT 20;
```

Run via:
```bash
cd python && sqlite3 data/results/experiments.db "SELECT ..."
```

## Interpreting Results

- **Violations**: Years where the month's max DD exceeded the threshold. Marked with `*` in the DD row.
- **Max violations**: The constraint allows up to N years to exceed threshold. Fewer = stricter.
- **DD row**: Running-peak DD for the target month in each year. This is NOT the month's standalone DD — it accounts for cumulative equity from all prior months.
- **R row**: Net R earned during the target month in each year.
- **Total R**: Sum of the month's R across all years. Higher is better among passing combos.
- **Rank**: Where the current setup falls among all passing combos. Lower is better.

## Combo Count Warning

The total combinations = `len(risk_levels) ^ len(strategies)`. With 6 risk levels:
- 6 strategies: 46,656 combos (~seconds)
- 8 strategies: 1,679,616 combos (~minutes)
- 10 strategies: 60,466,176 combos (~hours, may need larger chunk_size or fewer risk levels)

If combo count is too high, suggest reducing risk levels (e.g., `[0, 100, 200, 250]`) or grouping correlated strategies.
