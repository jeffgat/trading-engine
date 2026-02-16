# Optimization Methods

Advanced optimization techniques beyond simple grid sweeps. All examples use the existing engine infrastructure.

## Walk-Forward Optimization

Split data into rolling train/test windows. Optimize on train, validate on test, then slide forward.

### Why
A single in-sample optimization can overfit. Walk-forward tests whether optimized params hold up on unseen data across multiple periods.

### Implementation Pattern

```python
import pandas as pd
from datetime import datetime, timedelta
from orb_backtest.config import default_config
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

instrument = get_instrument("NQ")
df = load_5m_data(instrument.data_file)

# Define windows
train_months = 12  # optimize on 12 months
test_months = 3    # validate on next 3 months
step_months = 3    # slide forward by 3 months

param_ranges = {
    "ny_stop_atr_pct": [5, 7.5, 10, 12.5, 15, 17.5, 20],
    "rr": [2.0, 2.5, 3.0],
}

# Generate walk-forward windows
start = pd.Timestamp("2018-01-01")
end = pd.Timestamp("2025-01-01")
results = []

current = start
while current + pd.DateOffset(months=train_months + test_months) <= end:
    train_start = current
    train_end = current + pd.DateOffset(months=train_months)
    test_start = train_end
    test_end = test_start + pd.DateOffset(months=test_months)

    # Optimize on train period
    base = default_config(instrument)
    configs = generate_param_grid(base, param_ranges)
    train_results = run_sweep(
        df, configs, n_workers=4,
        start_date=str(train_start.date()),
    )
    # Filter to train period only
    train_scored = []
    for cfg, trades in train_results:
        in_period = [t for t in trades if t.date < str(test_start.date())]
        m = compute_metrics(in_period)
        train_scored.append((cfg, m))

    best_cfg = max(train_scored, key=lambda x: x[1]["sharpe_ratio"])[0]

    # Validate on test period
    from orb_backtest.engine.simulator import run_backtest
    test_trades = run_backtest(df, best_cfg, start_date=str(test_start.date()))
    test_trades = [t for t in test_trades if t.date < str(test_end.date())]
    test_metrics = compute_metrics(test_trades)

    results.append({
        "train_start": str(train_start.date()),
        "train_end": str(train_end.date()),
        "test_start": str(test_start.date()),
        "test_end": str(test_end.date()),
        "best_config": best_cfg,
        "train_sharpe": max(train_scored, key=lambda x: x[1]["sharpe_ratio"])[1]["sharpe_ratio"],
        "test_sharpe": test_metrics["sharpe_ratio"],
        "test_trades": test_metrics["total_trades"],
        "test_pnl": test_metrics["total_pnl_usd"],
        "test_win_rate": test_metrics["win_rate"],
    })

    current += pd.DateOffset(months=step_months)

# Summarize walk-forward results
for r in results:
    print(f"{r['test_start']} → {r['test_end']}: "
          f"Train Sharpe={r['train_sharpe']:.2f}, "
          f"Test Sharpe={r['test_sharpe']:.2f}, "
          f"Trades={r['test_trades']}, "
          f"PnL=${r['test_pnl']:,.0f}")
```

### Interpreting Walk-Forward Results

| Signal | Meaning |
|--------|---------|
| Test Sharpe consistently > 0 | Params generalize — good sign |
| Test Sharpe always < Train Sharpe | Normal — some degradation is expected |
| Test Sharpe is negative in many windows | Overfitting — the optimization is finding noise |
| Best params change wildly each window | Unstable — the strategy may not have a robust param set |
| Best params cluster tightly | Robust — a stable parameter region exists |

## Monte Carlo Bootstrap

Resample trade returns with replacement to estimate confidence intervals for drawdown, Sharpe, and total PnL.

### Why
A single equity curve is one realization. Monte Carlo shows the range of possible outcomes given the same trade distribution.

### Implementation Pattern

```python
import numpy as np
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# Run a backtest first
trades = run_backtest(df, config, start_date="2020-01-01")
filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
returns = np.array([t.pnl_usd for t in filled])

n_simulations = 1000
n_trades = len(returns)

max_drawdowns = []
final_pnls = []
sharpes = []

rng = np.random.default_rng(42)

for _ in range(n_simulations):
    # Resample with replacement
    sample = rng.choice(returns, size=n_trades, replace=True)

    # Compute equity curve
    equity = np.cumsum(sample)
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak
    max_dd = float(np.min(drawdown))

    # Compute Sharpe on resampled returns
    r_mean = np.mean(sample)
    r_std = np.std(sample, ddof=1)
    sharpe = (r_mean / r_std * np.sqrt(252)) if r_std > 0 else 0

    max_drawdowns.append(max_dd)
    final_pnls.append(float(equity[-1]))
    sharpes.append(sharpe)

# Confidence intervals
dd_5th = np.percentile(max_drawdowns, 5)
dd_50th = np.percentile(max_drawdowns, 50)
dd_95th = np.percentile(max_drawdowns, 95)

print(f"Max Drawdown — 5th: ${dd_5th:,.0f}, Median: ${dd_50th:,.0f}, 95th: ${dd_95th:,.0f}")
print(f"Final PnL — 5th: ${np.percentile(final_pnls, 5):,.0f}, "
      f"Median: ${np.percentile(final_pnls, 50):,.0f}, "
      f"95th: ${np.percentile(final_pnls, 95):,.0f}")
print(f"Sharpe — 5th: {np.percentile(sharpes, 5):.2f}, "
      f"Median: {np.percentile(sharpes, 50):.2f}, "
      f"95th: {np.percentile(sharpes, 95):.2f}")
```

### Key Metrics from Monte Carlo

- **5th percentile drawdown**: Worst-case drawdown you should plan for
- **95th percentile PnL**: Best realistic outcome
- **5th percentile Sharpe**: If this is negative, the strategy's edge is uncertain
- **Median vs actual**: If actual results are near the 95th percentile, you got lucky — not a reliable edge

## Sensitivity Analysis

Test how results change when parameters move slightly from their optimized values.

### Why
A robust parameter set should degrade gracefully. If performance cliffs at +/-10%, the optimization found a noise artifact.

### Implementation Pattern

```python
# After finding best params from a sweep
best_stop = 10.0
best_rr = 2.5

# Create a fine grid around the best values
sensitivity_ranges = {
    "ny_stop_atr_pct": [best_stop * f for f in [0.8, 0.9, 1.0, 1.1, 1.2]],
    "rr": [best_rr * f for f in [0.8, 0.9, 1.0, 1.1, 1.2]],
}

configs = generate_param_grid(base, sensitivity_ranges)
results = run_sweep(df, configs, n_workers=4, start_date="2024-01-01")

# Build a 2D heatmap of Sharpe values
import numpy as np
stop_vals = sensitivity_ranges["ny_stop_atr_pct"]
rr_vals = sensitivity_ranges["rr"]
sharpe_grid = np.zeros((len(stop_vals), len(rr_vals)))

for cfg, trades in results:
    m = compute_metrics(trades)
    # Find indices
    stop_val = cfg.sessions[0].stop_atr_pct
    rr_val = cfg.rr
    i = stop_vals.index(stop_val)
    j = rr_vals.index(rr_val)
    sharpe_grid[i, j] = m["sharpe_ratio"]

# Print heatmap
print("Sharpe Sensitivity (rows=stop_atr_pct, cols=rr)")
header = "           " + "  ".join(f"{v:5.1f}" for v in rr_vals)
print(header)
for i, stop in enumerate(stop_vals):
    row = f"stop={stop:5.1f}  " + "  ".join(f"{sharpe_grid[i,j]:5.2f}" for j in range(len(rr_vals)))
    print(row)
```

### Interpreting Sensitivity

| Pattern | Meaning |
|---------|---------|
| Smooth gradient around peak | Robust — parameter surface is well-behaved |
| Sharp spike at one point | Fragile — likely overfitting to a specific data quirk |
| Flat plateau | Insensitive to this param — may not need to optimize it |
| Multiple peaks | Multiple regimes — consider different params per time period |

## In-Sample / Out-of-Sample Split

The simplest validation method. Optimize on one period, test on another.

### Recommended Splits

| Total Data | Train | Test | Notes |
|-----------|-------|------|-------|
| 2 years | 18 months | 6 months | Minimum viable split |
| 5 years | 3 years | 2 years | Good for most analyses |
| 10 years | 7 years | 3 years | Ideal — large test set |

### Implementation

```bash
# Train (optimize)
cd python && uv run python scripts/run_optimize.py \
  --instrument NQ --sessions ny \
  --start 2018-01-01 --end 2023-01-01 \
  --sweep ny_stop_atr_pct=5:20:2.5 --sweep rr=1.5,2.0,2.5,3.0

# Test (validate best config from above)
cd python && uv run python scripts/run_backtest.py \
  --instrument NQ --sessions ny \
  --start 2023-01-01 --end 2025-01-01 \
  --ny-stop-atr-pct 10.0 --rr 2.5 \
  --name "OOS validation of train best"
```

### Red Flags

- Train Sharpe > 2.0 but test Sharpe < 0.5 → significant overfitting
- Test drawdown > 2x train drawdown → regime change or overfitting
- Test win rate drops by >10 percentage points → param set is fragile
- Test has <30 trades → insufficient data for statistical significance

## Multi-Objective Optimization

When optimizing for one metric (e.g., Sharpe) sacrifices another (e.g., max drawdown):

```python
# Score combining Sharpe and drawdown
def composite_score(metrics):
    sharpe = metrics["sharpe_ratio"]
    dd_usd = abs(metrics["max_drawdown_usd"])
    pnl = metrics["total_pnl_usd"]
    trades = metrics["total_trades"]

    if trades < 30:
        return -999  # Not enough data

    # Penalize extreme drawdowns
    dd_penalty = max(0, dd_usd - 50000) / 10000  # penalty above $50k DD
    return sharpe - dd_penalty * 0.1

scored = [(c, compute_metrics(t), composite_score(compute_metrics(t)))
          for c, t in results]
best = max(scored, key=lambda x: x[2])
```

Adjust the scoring function to match the user's risk tolerance and objectives.
