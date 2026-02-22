# {INSTRUMENT} ({INSTRUMENT_NAME}) — Strategy Learnings

## Instrument Profile

| Property | Value |
|----------|-------|
| Symbol | {INSTRUMENT} |
| Exchange | {EXCHANGE} |
| Point Value | ${POINT_VALUE}/point |
| Min Tick | {TICK_SIZE} |
| Commission | ${COMMISSION}/contract/side |
| Sessions Tested | {SESSIONS_TESTED} |
| Data Range | {START_DATE} to {END_DATE} (5m + 1m + 1s) |
| Liquidity Notes | {LIQUIDITY_NOTES} |

## Strategies Tested

### 1. {STRATEGY_NAME} -- {GO / CONDITIONAL / NO-GO}

**Scripts**: `{SCRIPT_LIST}`

#### Converged Anchor Config

| Param | Value |
|-------|-------|
| strategy | {STRATEGY_TYPE} |
| direction | {DIRECTION} |
| rr | {RR_RATIO} |
| tp1_ratio | {TP1_RATIO} |
| atr_length | {ATR_PERIOD} |
| stop_atr_pct | {STOP_ATR}% |
| min_gap_atr_pct | {MIN_GAP_ATR}% |
| max_gap_atr_pct | {MAX_GAP_ATR}% |
| max_gap_points | {MAX_GAP_POINTS} |
| ORB window | {ORB_WINDOW} |
| entry_end | {ENTRY_END} |
| flat_start | {FLAT_START} |
| excluded_days | {EXCLUDED_DAYS} |
| excluded_dates | {EXCLUDED_DATES} |
| magnifier | {MAGNIFIER} |

**WF mode params (use for live trading):** {WF_MODE_PARAMS}

#### Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 -- Structural | {PASS/FAIL} | {TRADES} trades, {WIN_RATE}% WR, {NET_R}R net, Sharpe {SHARPE}, Calmar {CALMAR}, DD {MAX_DD}R, {NEG_YEARS} neg years |
| 2 -- Walk-Forward | {PASS/FAIL} | WF eff {WFE}, stability {STABILITY}, OOS {OOS_R}R, {OOS_FOLDS_POSITIVE}/{TOTAL_FOLDS} folds positive |
| 3 -- Prop Constraints | {PASS/FAIL} | {ANNUAL_R} R/yr avg, expectancy {EXPECTANCY}R |
| 4 -- Hold-Out | {PASS/FAIL} | {HOLDOUT_TRADES} trades, Sharpe {HOLDOUT_SHARPE}, PF {HOLDOUT_PF}, {HOLDOUT_R}R |
| 5 -- Monte Carlo | {PASS/FAIL} | {MC_SURVIVAL}% survival at -25R ruin |

**Verdict: {GO / CONDITIONAL / NO-GO}** -- {VERDICT_RATIONALE}

#### Anchor Evolution

| Round | Calmar | Change | Decision |
|-------|--------|--------|----------|
| R1 sweep | {CALMAR} | {DESCRIPTION} | {ADOPTED/CONFIRMED} |

**DB entry**: `{EXPERIMENT_NAME}`

## What Works

- {Bullet points of strategies/configs/parameters that showed promise}

## What Doesn't Work

- {Bullet points of strategies/configs that failed and why}

## Parameter Sensitivity

- **atr_length**: {Sensitivity notes}
- **stop_atr_pct**: {Sensitivity notes}
- **rr**: {Sensitivity notes}
- **tp1_ratio**: {Sensitivity notes}
- **min_gap_atr_pct**: {Sensitivity notes}
- **ORB window**: {Sensitivity notes}
- **entry_end**: {Sensitivity notes}
- **flat_start**: {Sensitivity notes}
- **DOW exclusion**: {Sensitivity notes}

## Prop Firm Considerations

- **OOS Max DD**: {DD}R
- **Sizing**: {Sizing guidance based on MC tail risk}
- **Win rate**: {WR}% -- expect {STREAK} loss streaks
- **Annual R expectation**: {ANNUAL_R} R/yr (WF OOS avg)

## Notes

- {Any other observations, quirks, or instrument-specific findings}
