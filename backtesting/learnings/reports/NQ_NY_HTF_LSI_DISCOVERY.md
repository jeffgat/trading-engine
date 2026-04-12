# NQ NY HTF-LSI Discovery

## Summary

- Thesis: replace same-timeframe LSI pivots with published unswept `60m` bar extremes, while using patched invalidate-only sweep semantics and a per-session trade cap.
- Data used for discovery: `2016-01-01` to `2025-03-31`.
- Holdout status: opened once after PSR / DSR clearance.
- Result: the branch promoted from discovery to a conditional `5m` candidate, still only in a narrow long-only family.

## Structural Read

- Stage A survivors existed only in the `htf60`, `long`, `fvg_limit` family.
- Best structural window stayed at `08:30-15:00`, with `08:30-14:00` as a weaker but still alive sibling.
- Trade-cap sweep favored `cap=2`. `cap=3` tied `cap=2`, so the lower cap is preferred. `cap=1` was slightly worse.

## Parameter Findings

- One-at-a-time sweeps improved the family in a consistent direction:
  - `rr=2.75-3.0` beat the seed `rr=2.0`.
  - `tp1_ratio=0.6` beat `0.5`.
  - `lsi_fvg_window_right=2-3` beat `5`.
  - `htf_n_left=3` beat `5` on the more discovery-balanced branch.
  - `min_gap_atr_pct=3.0` stayed the cleanest balanced choice. `4.0-5.0` improved discovery but gave back too much on validation.
- Interaction sweep confirmed the family rather than collapsing it.

## Frozen Lead

- Balanced anchor:
  - `5m`, `long`, `fvg_limit`, `08:30-15:00`
  - `rr=3.0`, `tp1_ratio=0.6`
  - `min_gap_atr_pct=3.0`
  - `htf_level_tf_minutes=60`, `htf_n_left=3`
  - `htf_trade_max_per_session=2`
  - `lsi_fvg_window_left=20`, `lsi_fvg_window_right=2`
  - `max_fvg_to_inversion_bars=0`
- Pre-holdout discovery:
  - `424` trades, PF `1.164`, avg R `0.072`
- Validation:
  - `151` trades, PF `1.556`, avg R `0.224`, Calmar `6.208`

## Challenger

- Validation-led challenger:
  - same as above, but `htf_n_left=5` and `lsi_fvg_window_right=3`
- Discovery:
  - `426` trades, PF `1.059`, avg R `0.022`
- Validation:
  - `144` trades, PF `1.595`, avg R `0.246`, Calmar `6.556`

## Promotion Tie-Break

- `36m IS / 12m OOS / 12m step` walk-forward on frozen finalists favored the balanced anchor:
  - Balanced anchor: `376` stitched OOS trades, PF `1.298`, avg R `0.130`, Calmar `4.117`, DD `-11.83R`
  - Validation-led challenger: `369` stitched OOS trades, PF `1.180`, avg R `0.084`, Calmar `2.177`, DD `-14.18R`
- Conclusion: freeze the balanced anchor as the live branch lead.

## No-Promote Filters

- Inversion-speed caps did not help.
  - `lag=0` dominated. `lag<=1/2/3` mostly destroyed sample and discovery quality.
- Regime gate did not help.
  - `skip bull_medium_vol + sideways_medium_vol` reduced validation trade count too sharply and lost on validation Calmar versus ungated.
- Confluence overlays did not beat the baseline on validation Calmar.
  - Best challengers were `ema50 magnet`, `sma20 bounce`, and `vwap magnet`, but all were thinner and weaker on validation Calmar than the ungated baseline.

## Timeframe Transfer

- Transfer was tested with FVG windows scaled by real minutes from the frozen `5m` anchor.
- Ranking:
  - `5m` best overall
  - `2m` alive but clearly weaker
  - `1m` positive but much weaker
  - `3m` validation-strong but discovery-negative, so not promotable

## Stage I PSR / DSR

- Trial basis:
  - raw unique `5m` discovery configs from Stage A/B/C/D: `144`
  - effective trials by trade-date clustering: `8`
- Full pre-holdout candidate:
  - `575` trades, PF `1.250`, avg R `0.112`, total R `+64.37`, Calmar `5.27`, DD `-12.21R`, Sharpe `1.53`
  - PSR `0.9914`
  - DSR `0.8092`
- Stitched walk-forward OOS stream:
  - `376` trades, PF `1.298`, avg R `0.130`, total R `+48.70`, Calmar `4.12`, DD `-11.83R`, Sharpe `1.75`
  - PSR `0.9869`
  - DSR `0.7606`
- Interpretation:
  - The branch clears the repo’s moderate PSR / DSR bar and survives deflation.

## Holdout

- Holdout window: `2025-04-01+`
- Frozen balanced anchor:
  - `46` trades, PF `1.987`, avg R `0.361`, total R `+16.61`, Calmar `5.54`, DD `-3.0R`, Sharpe `4.66`
- Year breakdown:
  - `2025`: `35` trades, PF `2.205`, avg R `0.414`, total R `+14.50`, DD `-3.0R`
  - `2026 YTD`: `11` trades, PF `1.437`, avg R `0.192`, total R `+2.11`, DD `-1.38R`
- Interpretation:
  - The first honest holdout open confirmed the branch rather than exposing a collapse.

## Next Steps

- The balanced anchor was the correct frozen live lead.
- Update: dedicated phase-one review has since been completed in [NQ_NY_HTF_LSI_PHASE_ONE.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/NQ_NY_HTF_LSI_PHASE_ONE.md) and graded the branch `STRONG`.
- The next clean step is phase-two / post-first-payout preservation work or exact-execution live-alignment checks.
- Only reopen the challenger if the frozen lead fails those later-stage tests.
