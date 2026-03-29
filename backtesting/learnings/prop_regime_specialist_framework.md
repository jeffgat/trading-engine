# Prop Regime-Specialist Framework

## Goal

Build a rough research framework for a prop-firm-oriented trading approach where:

- strategies are allowed to be strong in narrow market regimes
- strategies are allowed to fail badly outside their intended regime
- the business objective is payout extraction across many cheap account attempts
- evaluation is based on prop-firm expected value, not just long-run robustness

This is not a "holy grail" framework.
It is a specialist-strategy portfolio framework.

## The 3 Things To Determine

1. Regime definitions
2. Which strategy families belong in each regime
3. Which evaluation metrics matter for prop-firm EV

---

## 1. Determine Regime Definitions

### Objective

Create simple, objective labels for:

- bull
- bear
- sideways

These labels must be defined independently of strategy PnL.

### Working Principle

Do not define regimes by "when strategy X wins."
Define them by market structure and behavior first, then test strategy fit inside them.

### Candidate Regime Inputs

- Higher-timeframe trend structure
  - daily or 4H higher highs / higher lows
  - daily or 4H lower highs / lower lows
- Volatility state
  - low vol, normal vol, high vol
- Intraday participation / expansion
  - opening drive vs compression
  - range expansion vs failed expansion
- Position relative to a benchmark
  - above / below session VWAP
  - above / below prior day VWAP
  - above / below anchored weekly VWAP

### Proposed First-Pass Regime Labels

#### Bull

- Daily or 4H structure is up
- Pullbacks are shallow
- Market spends most of the session above its mean
- Breakouts tend to continue

#### Bear

- Daily or 4H structure is down
- Rallies fail quickly
- Market spends most of the session below its mean
- Breakdowns tend to continue

#### Sideways

- No persistent higher-timeframe structure
- Range rotation dominates
- Price frequently reverts through intraday mean
- Breakouts fail often

### Research Steps

1. Pick one regime model only for round 1.
2. Keep it simple enough to explain in 3-5 lines.
3. Label history day by day using only information available at that time.
4. Produce a regime calendar for the past several years.
5. Sanity-check whether the labels match obvious market behavior visually.

### Deliverables

- A written regime rule set
- A labeled historical regime table by date
- A confusion log of days that were hard to classify

---

## 2. Determine Which Strategy Families Fit Each Regime

### Objective

Match specialist strategy types to the regime where they should naturally have edge.

### Candidate Strategy Families

#### Bull Regime

- ORB continuation long
- breakout-pullback continuation
- FVG continuation in direction of trend
- buy-the-dip intraday continuation

#### Bear Regime

- ORB continuation short
- failed rally / breakdown continuation
- rejection trades from VWAP or resistance
- fast downside momentum entries

#### Sideways Regime

- mean reversion to VWAP
- fade session extremes
- failed breakout fades
- intraday rotation trades with smaller targets

### Matching Logic

Use a simple matrix:

| Regime | Expected market behavior | Best candidate strategy family |
| --- | --- | --- |
| Bull | directional continuation up | long continuation / breakout |
| Bear | directional continuation down | short continuation / breakdown |
| Sideways | failed expansion / reversion | mean reversion / fades |

### Research Steps

1. List existing strategies or ideas already in the repo.
2. Assign each one to a "natural" regime.
3. Backtest each strategy only inside its intended regime.
4. Compare against the same strategy outside its intended regime.
5. Reject strategies that do not show strong regime specialization.

### What Good Looks Like

A strategy is a good specialist if:

- it performs clearly better in its target regime than outside it
- the logic is intuitive for that regime
- it is not dependent on tiny parameter changes
- it retains enough trades to matter operationally

### Deliverables

- A regime-to-strategy mapping table
- In-regime vs out-of-regime performance comparison
- A shortlist of regime specialists worth paper trading

---

## 3. Determine Evaluation Metrics For Prop-Firm EV

### Objective

Stop judging strategies only by traditional portfolio metrics.
Measure them like a prop-firm business model.

### Core Insight

If accounts are cheap and payout upside is large, the relevant question is:

"What is the expected value of running this specialist across many account attempts?"

### Primary Metrics To Track

- pass rate
  - how often does the strategy survive challenge / eval rules
- first payout rate
  - how often does an account reach first payout before breach
- average payout per passed account
- average number of resets per payout
- average time to payout
- failure clustering
  - do many accounts fail in the same regime shift
- live decay rate
  - how quickly does performance fall after deployment

### Secondary Metrics

- win rate
- expectancy per trade
- max drawdown
- max daily drawdown pressure
- consistency with payout rules
- number of trading days to milestone

### Prop-Specific Risk Questions

- Can this strategy survive trailing drawdown rules?
- Can it reach payout fast enough before edge decays?
- Does it produce oversized correlation across multiple accounts?
- Does it rely on a regime that may disappear quickly?
- Are losses lumpy enough to wipe many accounts at once?

### Research Steps

1. Write down the exact economic model.
   - account cost
   - reset cost
   - payout split
   - typical payout size target
2. Convert backtest results into account-level outcomes.
3. Estimate EV per account attempt.
4. Estimate EV across a portfolio of parallel account attempts.
5. Stress-test clustered failures.

### Simple EV Formula To Start With

Expected value per attempt:

`EV = (probability of payout * average net payout) - (probability of failure * total account/reset cost)`

Then extend to:

- multiple accounts running simultaneously
- multiple regime specialists
- correlated failure assumptions

### Deliverables

- A prop-EV scorecard template
- A cohort model for 10 / 25 / 50 account attempts
- A kill-switch rule set for disabling broken specialists

---

## Rough Next-Step Sequence

1. Define one simple regime model.
2. Label history using that model.
3. Bucket existing ORB ideas into bull / bear / sideways families.
4. Test each family inside and outside its target regime.
5. Build a prop-EV scorecard for the best specialists.
6. Identify which specialists are worth live paper trading.
7. Add kill-switch rules before any real deployment.

---

## Round 1 Scope Recommendation

Keep round 1 small.

- Bull specialist:
  - NQ NY continuation long family
- Bear specialist:
  - NQ NY short continuation / rejection family
- Sideways specialist:
  - one VWAP mean-reversion or failed-breakout fade idea

Only after those 3 are clearly defined should the framework expand.

---

## Important Guardrails

- Keep regime definitions simple.
- Keep specialist logic interpretable.
- Do not tune too many strategy parameters inside each regime.
- Measure selection risk, not just backtest quality.
- Assume specialists decay and need replacement.
- Treat the business as a portfolio of specialist bets, not one forever system.

Current implementation note:
- The deployed NQ 4-leg package is a **generalist payout portfolio**, not the finished multi-specialist end state. It contains one true bull specialist plus three general long-biased payout legs, so it does not yet satisfy the intended regime-specialist portfolio architecture.
