# Prop Firm Constraint Reference

R-based thresholds for prop firm account survival evaluation.

## Optimization vs Validation

Use different logic for optimization and validation:

- **During optimization**: Calmar is often the best ranking metric and DD can be a soft input.
- **During validation**: use the real prop-firm DD threshold. Do not hide drawdown with a dummy value like `999R`.

This distinction matters because downstream validation stages are pass/fail, not search stages.

## Optimization Priority Order

**Calmar ratio (Avg Annual R / |Max DD R|) is the primary optimization metric.**

Suggested ranking order:
1. **Calmar** — primary objective, always
2. **0 negative full years** — consistency across all full calendar years
3. **Sharpe** — secondary; useful for walk-forward objective
4. **Net R / Avg Annual R** — only meaningful relative to DD (i.e., as Calmar)

Do not use a fixed DD threshold as a hard optimization filter unless the user explicitly wants account-size-aware search.

---

## Default Thresholds

| Constraint | Default | Range | Rationale |
|-----------|---------|-------|-----------|
| Max Drawdown (R) | 10.0 | 8-12 | Prop firms breach at 8-10R; 10R is standard |
| Min Annual R | 24.0 | 12-36 | 2R/month target (24R/year) |
| Max Monthly Loss (R) | 5.0 | 3-6 | Half the DD limit as a single-month cap |
| Positive Expectancy | True | — | Average R per trade must be > 0 |

## Constraint Details

### Max Drawdown (R)

Peak-to-trough drawdown of the R equity curve. Computed as:
```
equity = cumsum(r_multiples)
peak = maximum.accumulate(equity)
drawdown = equity - peak
max_dd = min(drawdown)  # most negative value
```

The absolute value is compared against the threshold. A max DD of -7.2R passes a 10R threshold.

**Validation guidance**:
- Use the actual breach level for Phase 3 and Phase 5, typically `8R` to `10R`
- If you relax the threshold for a looser account profile, say so explicitly
- Never report Monte Carlo survival against `999R` as meaningful survival

**Adjustment guidance**:
- Use 8R for conservative prop firms (e.g., strict evaluation accounts)
- Use 10R as the standard default
- Use 12R for more lenient accounts or when payout ROI justifies occasional breaches

### Min Annual R

Total R earned per calendar year. Only **full years** (≥10 months of trading data) are gated. Partial years at the start/end of the dataset are reported but don't trigger a fail.

**Why 24R**: At 2R/month, a strategy needs ~24R/year to be worth trading on a prop firm account after accounting for evaluation fees and resets. This is a floor, not a target.

**Adjustment guidance**:
- Lower to 12-18R for commodities with fewer trading days (CL, GC)
- Raise to 30-36R for high-frequency instruments (NQ, ES) if you want stronger selection

### Max Monthly Loss (R)

The worst single-month R. If any month's total R is below `-max_monthly_loss_r`, the check fails.

**Why 5R**: A single -5R month is half the DD budget. Two bad months in sequence would breach most accounts. This catches strategies with lumpy, catastrophic loss months even if overall DD looks acceptable.

### Positive Expectancy

Average R per trade must be > 0. This is the most basic filter — a strategy that doesn't have positive expectancy has no edge.

## Using PropFirmConstraints

```python
from orb_backtest.optimize.prop_constraints import (
    PropFirmConstraints, evaluate_constraints, evaluate_constraints_mc,
)

# Default thresholds
constraints = PropFirmConstraints()

# Custom thresholds
tight = PropFirmConstraints(max_drawdown_r=8.0, min_annual_r=30.0)
lenient = PropFirmConstraints(max_drawdown_r=12.0, min_annual_r=18.0, max_monthly_loss_r=6.0)
```

## ConstraintResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `passed` | bool | All constraints met |
| `max_drawdown_r` | float | Peak-to-trough DD (negative) |
| `max_drawdown_passed` | bool | \|DD\| <= threshold |
| `annual_r_values` | dict | R per year (all years) |
| `annual_r_passed` | bool | All full years >= threshold |
| `monthly_r_values` | dict | R per month (YYYY-MM keys) |
| `worst_month_r` | float | Worst single month R |
| `monthly_loss_passed` | bool | \|worst month\| <= threshold |
| `expectancy` | float | Mean R per trade |
| `expectancy_passed` | bool | Expectancy > 0 |
| `total_r` | float | Cumulative R |
| `total_trades` | int | Filled trade count |
| `win_rate` | float | Fraction of winning trades |
| `avg_win_r` | float | Average R of winners |
| `avg_loss_r` | float | Average R of losers (negative) |
| `max_consecutive_losses` | int | Longest losing streak |

## Monte Carlo Survival

`evaluate_constraints_mc()` extends constraint evaluation to Monte Carlo simulated paths:

| Field | Description |
|-------|-------------|
| `survival_rate` | Fraction of sims where \|max DD\| <= threshold |
| `dd_percentiles` | p5/p25/p50/p75/p95 of absolute max DD |
| `monthly_loss_pass_rate` | Fraction of sims where no month exceeds loss cap |
| `annual_r_pass_rate` | Fraction of sims where all full years meet min annual R |

**Important implementation note**:
- In the current code, `survival_rate` is drawdown-based.
- Monthly and annual pass rates are separate diagnostics.
- Do not describe `survival_rate` as a combined monthly-plus-annual survival metric unless the implementation changes.

**Survival rate interpretation**:
- `>= 80%`: Strong — prop firm survival is highly likely
- `70-80%`: Acceptable — deploy with standard sizing
- `50-70%`: Risky — consider reduced position size
- `< 50%`: Too risky — strategy will likely breach the account
