# Bias Prevention & Best Practices

## Critical Biases

| Bias | Description | Mitigation |
|------|-------------|------------|
| **Look-ahead** | Using future data in signals | Point-in-time data only; signals shift by 1 bar before acting |
| **Overfitting** | Curve-fitting params to history | Walk-forward analysis; out-of-sample holdout |
| **Transaction costs** | Ignoring slippage/commissions | Realistic cost model (commission already in config) |
| **Selection bias** | Cherry-picking best param set | Pre-register hypotheses; test on unseen data |

## Optimization Discipline

1. **Train / Validation / Test Split** — Never optimize on the test set
2. **Walk-Forward Optimization** — Rolling train-then-test windows over single in-sample optimization
3. **Monte Carlo Bootstrap** — Resample trade returns to estimate drawdown confidence intervals
4. **Parameter Parsimony** — Fewer free parameters reduce overfitting risk; simpler models generalize better

## Engine-Specific Safeguards Already Implemented

- **Daily ATR shift**: ATR is shifted by 1 day (`[1]` offset) to prevent lookahead
- **Signal confirmation**: FVG detected on bar [0] but signal acts on next bar
- **One trade per session-day**: Prevents over-trading on correlated signals
- **Conservative same-bar conflict**: When SL and TP1 hit on same bar, SL wins
- **Commission per contract**: Applied in PnL calculation

## When Adding New Features

- Always shift any new indicator by at least 1 bar before using it for entry/exit decisions
- Never use `close[0]` for decisions that affect the current bar's trade
- Validate new filters don't create survivorship bias (filtering out losses retroactively)
- When adding new parameters, consider the total parameter count and overfitting risk
