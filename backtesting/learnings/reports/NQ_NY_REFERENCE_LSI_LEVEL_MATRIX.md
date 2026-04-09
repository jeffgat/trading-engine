# NQ NY Reference LSI Level Matrix

This matrix lines up the exact swept liquidity levels across the two most useful studies:

- `5m pre-holdout`: from the frozen all-level attribution candidate in [NQ_NY_REFERENCE_LSI_ATTRIBUTION.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/NQ_NY_REFERENCE_LSI_ATTRIBUTION.md)
  - candidate: `both 11:00 near gap6 inv15 rr3.0 tp0.8`
- `3m OOS` and `3m holdout`: from the all-level `3m` phase-one leader failure analysis in [NQ_NY_REFERENCE_LSI_3M_FAILURE_ANALYSIS.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/NQ_NY_REFERENCE_LSI_3M_FAILURE_ANALYSIS.md)
  - candidate: `both 13:00 far gap9 inv12 rr3.0 tp0.7`

Important caveat:

- this is useful for comparing which levels tended to carry or drag edge
- but it is not a perfect apples-to-apples comparison, because the `5m` and `3m` rows come from different frozen candidates
- holdout exact-level samples are very small, so treat them as directional, not definitive

## Matrix

| Level | Shorthand | 5m pre trades | 5m pre avgR | 5m pre PF | 3m OOS trades | 3m OOS avgR | 3m OOS PF | 3m holdout trades | 3m holdout avgR | 3m holdout PF |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| previous_day_high | `PDH` | 10 | 0.6440 | 3.2655 | 12 | 0.8274 | 3.6957 | 2 | -1.0000 | 0.0000 |
| previous_day_low | `PDL` | 17 | 0.0716 | 1.0872 | 16 | 0.3720 | 1.5554 | 1 | 1.9038 | 0.0000 |
| asia_high | `Asia High` | 20 | 0.2333 | 1.6426 | 9 | -0.0949 | 0.9015 | 7 | -0.4779 | 0.2732 |
| asia_low | `Asia Low` | 21 | 0.1389 | 1.2940 | 15 | 0.5938 | 3.1868 | 3 | 1.1656 | 4.2016 |
| london_high | `London High` | 13 | -0.1867 | 0.6708 | 9 | 0.0767 | 1.1709 | 2 | 0.1341 | 0.9681 |
| london_low | `London Low` | 20 | -0.1697 | 0.7704 | 6 | 0.2704 | 1.7257 | 3 | 0.9791 | 5.2903 |

## Readout

- Most consistent exact winner before holdout: `PDH`
  - strongest `5m` pre-holdout exact level
  - strongest `3m` OOS exact level
  - but its `3m` holdout sample was only `2` trades and both lost, so it did not prove durable there

- Best low-side level overall: `Asia Low`
  - modestly positive on `5m`
  - very strong on `3m` OOS
  - still positive on `3m` holdout
  - this is the cleanest exact level that stayed constructive on both lower-timeframe OOS and holdout

- Weakest exact level overall: `Asia High`
  - only mildly positive on `5m`
  - negative on `3m` OOS
  - negative again on `3m` holdout with the largest holdout sample among exact levels
  - if one exact level looked like a recurring drag, it was `Asia High`

- `PDL` was okay, but not a standout
  - weak on `5m`
  - better on `3m` OOS
  - holdout was positive, but on only `1` trade

- London was unstable, not cleanly good or bad
  - both London levels were negative on the original `5m` pre-holdout attribution
  - both were positive on the `3m` OOS/holdout leader, especially `London Low`
  - sample sizes were small enough that I would still call London noisy rather than trustworthy

## Practical Ranking

If we rank exact levels by the full body of evidence we collected, the rough order is:

1. `PDH`
2. `Asia Low`
3. `PDL`
4. `London Low`
5. `London High`
6. `Asia High`

## Practical Takeaway

If we ever revisit this family as a genuinely new thesis, the exact levels that looked most worth building around were:

- `PDH`
- `Asia Low`

The exact level that looked most worth avoiding was:

- `Asia High`
