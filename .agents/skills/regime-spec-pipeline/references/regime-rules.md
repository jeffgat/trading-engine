# Regime Rules

Use these rules whenever building or validating a regime specialist.

## 1. Bailey Still Applies

Bailey-style overfitting control still applies when the target is conditional:

- Wrong question: "Does this strategy work in every market?"
- Right question: "Does this strategy work when regime = X?"

What changes is the hypothesis, not the need for discipline.

## 2. Same-Regime OOS Is Correct

For a bull specialist, the main OOS test is another unseen bull period.

Do not reject a bull specialist just because it falls apart in bear markets if the live design is to not trade there.

But you still need a full-calendar gate test, because live trading includes the need to stay out when the regime is wrong.

## 3. Regime Labels Must Be Point-in-Time

Acceptable:

- prior-day trend
- rolling realized vol
- prior-session HH/HL structure
- ex ante macro state known before the session opens

Unacceptable:

- labels based on same-day close
- labels based on future returns
- clustering the full sample, then acting as if the states were known live without a proper online procedure

## 4. Multiple Testing Often Gets Worse

Regime work often increases overfitting risk because you now have more freedom:

- many regime definitions
- many thresholds
- many confidence filters
- many gates
- many strategy parameter sets inside each regime

All of those count as trials. Report them honestly.

## 5. Fewer Samples Means Higher Burden of Proof

A regime subset has fewer trades and fewer episodes.

That means:

- require more caution, not less
- prefer simpler parameterizations
- prefer repeated regime episodes over one huge run
- downgrade confidence when the sample is dominated by one calendar period

## 6. Separate Conditional Edge From Gate Quality

There are two objects under test:

- the strategy logic inside the target regime
- the regime gate that decides when the strategy is active

A strategy can be good and the gate can be bad.
A gate can be good and the strategy can still have no edge.

Validate both.

## 7. Regime Specialists Do Not Need All-Weather Robustness

A bull specialist does not need to be profitable in bear markets.

What it does need:

- strong enough edge in bull regimes
- a gate that mostly keeps it out of bear regimes
- acceptable live account behavior for the combined system

## 8. Honest Labels Matter

Use the evidence to classify the result honestly:

- true specialist
- biased specialist
- mixed-regime strategy
- failed specialist

If in-regime and out-of-regime performance are too similar, it is not really a specialist.

## 9. Preferred Repo Hooks

Useful repo components for this skill:

- `orb_backtest.analysis.prop_regime_specialist`
- `orb_backtest.analysis.regime_reports`
- `orb_backtest.signals.structure_15m.compute_session_regime`
- `orb_backtest.analysis.holdout_log`

If these tools are insufficient for the requested regime, extend them with the same rule: no lookahead.
