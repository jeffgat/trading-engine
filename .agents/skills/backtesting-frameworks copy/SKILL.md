---
name: backtesting-frameworks
description: Build robust backtesting systems for trading strategies with proper handling of look-ahead bias, survivorship bias, and transaction costs. Use when developing trading algorithms, validating strategies, or building backtesting infrastructure.
---

# Backtesting Frameworks

Use this skill to design and review backtests that are causally correct, operationally realistic, and decision-useful.

This is a general guide to carrying out effective backtests. It is not a recipe for maximizing any single metric. Metrics are outputs to interpret, not objectives to optimize in isolation.

## When to Use This Skill

- Building a new backtest or simulator
- Reviewing an existing backtest for bias or realism issues
- Comparing strategy variants without contaminating the test set
- Designing walk-forward or out-of-sample validation
- Adding transaction costs, slippage, and capacity constraints
- Turning a research idea into a reproducible evaluation pipeline

## What a Good Backtest Should Answer

A useful backtest should help answer these questions:

1. Was the strategy evaluated using only information that would have been available at the time?
2. Are fills, costs, leverage, and position sizing modeled realistically enough for the intended use?
3. Does performance persist out of sample and across different market conditions?
4. Are the reported results stable enough to support a real decision?
5. Is the whole process reproducible and auditable?

If the answer to any of these is "not sure," improve the backtest before drawing conclusions.

## Core Principles

### 1. Causality First

Never let the backtest use information that was not available at the decision time.

- Generate signals from information known at or before bar close, then execute no earlier than the next executable event unless your data and strategy logic justify same-bar execution.
- Use point-in-time data for fundamentals, universes, index membership, and corporate actions.
- Be explicit about timestamps, time zones, session boundaries, and publication delays.
- If labels or features overlap in time, use purged or embargoed validation rather than naive random splits.

### 2. Data Integrity Matters More Than Fancy Modeling

Bad data will dominate everything else.

- Validate timestamps, duplicate rows, missing bars, split adjustments, and symbol changes.
- For equities, handle delistings, mergers, dividends, and corporate actions correctly.
- For futures, specify contract roll rules, back-adjustment method, and whether signals trade front month or a continuous series proxy.
- For intraday systems, define exchange sessions, holidays, early closes, and daylight saving transitions.
- Keep raw data immutable and create derived research datasets from it.

### 3. Execution Assumptions Must Match the Strategy

The simulator should reflect how orders would plausibly interact with the market.

- Define what kinds of orders are allowed: market, limit, stop, passive, auction, etc.
- State when an order becomes eligible for execution.
- Model commissions, exchange fees, borrow fees, funding, slippage, spread crossing, and market impact where relevant.
- For higher-frequency or less liquid strategies, consider queue position, partial fills, latency, and volume limits.
- Reject impossible fills, such as a limit order filling outside the bar range without a justified execution model.

### 4. Portfolio Rules Are Part of the Strategy

Sizing and risk constraints are not separate from the backtest.

- Define position sizing, exposure limits, leverage, margin, and concentration constraints.
- Specify how cash, financing, and collateral are handled.
- Decide whether positions can overlap, pyramid, hedge, or reverse in one step.
- Model stops and exits using executable logic, not hindsight.

### 5. Validation Should Protect the Final Test

Keep a clean separation between development and evaluation.

- Use a development period for idea formation and implementation.
- Use validation for comparing variants or tuning parameters.
- Reserve a final untouched test set for the last honest check.
- For time series, prefer chronological splits over random shuffles.
- Use walk-forward analysis when parameters or model choices would realistically be revisited over time.

### 6. Robustness Matters More Than a Pretty Equity Curve

Look for stability, not just a strong headline number.

- Check performance across subperiods, regimes, days of week, sessions, symbols, and volatility environments.
- Perturb parameters and make sure results do not collapse immediately.
- Stress costs, slippage, and latency assumptions.
- Examine dependence on a small number of outsized trades or days.
- Use Monte Carlo carefully and explain what is being resampled.

## Practical Workflow

### Step 1: Define the Strategy Before Running It

Write down:

- The hypothesis
- The market and instrument set
- The trading horizon
- Entry and exit rules
- Position sizing rules
- Execution assumptions
- Risk limits
- What counts as success or failure for the research question

Do this before looking at the final test results. The goal is to reduce accidental story-fitting.

### Step 2: Build a Causal Dataset

Prepare a dataset that could exist in real time.

- Align all features to their first tradable timestamp.
- Shift signals or features when needed to preserve causality.
- Keep explicit columns for tradable prices such as open, high, low, close, bid, ask, or midpoint depending on the strategy.
- Track symbol metadata and contract metadata separately from price series.

### Step 3: Simulate Orders and Portfolio State

At minimum, the backtest should maintain:

- Open orders
- Fills
- Positions
- Cash
- Equity
- Realized and unrealized PnL
- Exposure and leverage

The simulation loop should usually look like:

1. Advance clock to the next event or bar.
2. Update market state for that timestamp.
3. Process orders that were already resting and are now executable.
4. Update portfolio state from fills and financing costs.
5. Generate new signals from information available at that timestamp.
6. Submit new orders that become eligible in the future according to the execution model.
7. Record state for later analysis.

### Step 4: Run Out-of-Sample Evaluation

Keep evaluation honest.

- Avoid repeated peeking at the final test set.
- If you revise the strategy after seeing test performance, that test is no longer a clean test.
- In walk-forward setups, re-estimate parameters only on the training window, then evaluate on the next unseen test window.
- When combining walk-forward results, stitch test-period returns or PnL in chronological order under consistent capital assumptions.

### Step 5: Interpret Results Broadly

Report a balanced set of outputs rather than chasing one number.

Useful outputs often include:

- Total and annualized return
- Volatility
- Drawdown depth and duration
- Exposure and turnover
- Trade count
- Average holding time
- Average win, average loss, and payoff asymmetry
- PnL by regime, instrument, or session
- Capacity sensitivity to costs and volume limits

Choose which outputs matter based on the strategy mandate. A market-making strategy, swing strategy, and intraday breakout system should not be judged the same way.

## Minimal Event-Driven Skeleton

Use this as a mental model, not as production-ready code.

```python
class BacktestEngine:
    def __init__(self, strategy, execution_model, portfolio):
        self.strategy = strategy
        self.execution_model = execution_model
        self.portfolio = portfolio
        self.pending_orders = []
        self.history = []

    def run(self, market_data):
        for timestamp, market_state in market_data:
            executable_orders = []

            for order in self.pending_orders:
                if self.execution_model.is_eligible(order, timestamp, market_state):
                    executable_orders.append(order)

            for order in executable_orders:
                fills = self.execution_model.execute(order, timestamp, market_state)
                self.portfolio.apply_fills(fills, timestamp, market_state)

            self.pending_orders = [
                order for order in self.pending_orders if order not in executable_orders
            ]

            visible_state = self.strategy.build_visible_state(
                timestamp=timestamp,
                market_state=market_state,
                portfolio=self.portfolio,
            )
            new_orders = self.strategy.generate_orders(visible_state)

            for order in new_orders:
                self.pending_orders.append(order)

            self.history.append(self.portfolio.snapshot(timestamp, market_state))

        return self.history
```

Important details this skeleton leaves open on purpose:

- Whether orders execute on next bar open, intrabar, auction, bid/ask, or custom events
- Whether fills are full or partial
- Whether financing, borrow, or funding costs accrue between events
- How multi-asset pricing and portfolio aggregation are handled

## Validation Patterns

### Simple Chronological Split

Use when the strategy is simple and parameter tuning is light.

```text
[Development............][Validation.....][Final Test.....]
```

### Walk-Forward Evaluation

Use when parameters or model choices would realistically be refreshed over time.

```text
Window 1: [Train........][Test....]
Window 2:     [Train........][Test....]
Window 3:         [Train........][Test....]
```

Good walk-forward practice:

- Keep the retraining schedule realistic.
- Carry forward only what would truly be known at each rebalance date.
- Combine test-period results chronologically.
- Do not pick one "best" configuration by looking across all future windows first.

## Common Failure Modes

Watch for these during reviews:

- Using the same-bar close to both generate a signal and assume execution at that close without a justified mechanism
- Using adjusted prices for execution without understanding what the adjustment represents
- Ignoring delisted names or historical universe changes
- Treating daily bars as if intraday path were known
- Counting bars with non-zero returns as trades
- Reporting a stitched walk-forward equity curve that quietly resets capital each segment
- Ignoring spread, borrow, funding, impact, or volume constraints
- Reusing the final test set after each idea change
- Assuming fills that exceed plausible market volume

## Monte Carlo and Resampling

Monte Carlo can be useful, but only with clear limits.

- Resampling trade outcomes can help estimate path variability.
- Simple iid return bootstraps ignore serial dependence and regime structure.
- For autocorrelated strategies, prefer block bootstrap or another method that preserves some dependence structure.
- Treat Monte Carlo as a robustness lens, not a substitute for clean out-of-sample testing.

## Review Checklist

Before trusting a backtest, confirm:

- Data is point-in-time where required.
- Signals only use information available at decision time.
- Execution timing and fill rules are explicitly defined.
- Costs and financing assumptions are appropriate for the market.
- Position sizing and constraints are implemented in the simulator.
- Validation is chronological and the final test remains untouched.
- Results are reproducible from code and inputs.
- Reported metrics match what is actually being counted.

## Best Practices

### Do

- Prefer the simplest simulator that is still faithful to the strategy's execution reality.
- Keep research, validation, and final testing separate.
- Write down assumptions for data, execution, and risk before interpreting results.
- Examine stability across regimes and under worse cost assumptions.
- Preserve enough logs and state to audit individual trades and portfolio changes.

### Don't

- Do not optimize the strategy around a single summary metric in the abstract.
- Do not assume fills just because a bar touched a price unless your execution model supports it.
- Do not mix signal-generation prices and executable prices carelessly.
- Do not infer trade statistics from bar-level returns.
- Do not trust a result you cannot reproduce exactly.

## Resources

- [Advances in Financial Machine Learning (Marcos Lopez de Prado)](https://www.amazon.com/Advances-Financial-Machine-Learning-Marcos/dp/1119482089)
- [Quantitative Trading (Ernest Chan)](https://www.amazon.com/Quantitative-Trading-Build-Algorithmic-Business/dp/1119800064)
- [Backtrader Documentation](https://www.backtrader.com/docu/)
