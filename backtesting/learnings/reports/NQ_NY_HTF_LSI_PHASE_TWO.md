# NQ NY HTF-LSI Phase Two

- Frozen phase-one source: [NQ_NY_HTF_LSI_PHASE_ONE.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/NQ_NY_HTF_LSI_PHASE_ONE.md)
- Holdout opened once for phase two: `2025-04-01` to `2026-03-24`.
- Post-payout model: start from `$52,000`, fixed breach at `$50,000`, risk `$250/R`, and withdraw weekly above `$52,500` back to `$52,000`.

## Summary

- `NQ NY HTF_LSI 5m frozen balanced anchor`: verdict `CONDITIONAL`, OOS withdrawal `88.7%`, OOS breach `48.2%`, holdout withdrawal `91.5%`, holdout breach `0.0%`, MC survival `6.8%` at `8.0R`

## Candidate Details

### NQ NY HTF_LSI 5m frozen balanced anchor

- verdict: `CONDITIONAL`
- detail: 3/5 phases passed; weak points were Phase 3: Continuity, Phase 5: Path-Risk.
- config: `long fvg_limit 08:30-15:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL20 fvgR2`
- stitched OOS metrics: trades `376.0`, PF `1.298`, avgR `0.1295`, DD `-11.8294`
- phase 3 continuity filter: DD pass `True`, annual pass `False`, monthly pass `False`, expectancy `0.12951180579523308`
- OOS post-payout scorecard: withdrawal `88.7%`, breach `48.2%`, avg withdrawals/start `$4140.27`, avg payout count/start `5.44`
- holdout metrics: trades `46.0`, PF `1.9874`, avgR `0.3611`, DD `-3.0`
- holdout post-payout scorecard: withdrawal `91.5%`, breach `0.0%`, avg withdrawals/start `$2689.18`, avg payout count/start `3.96`
- phase 5 MC: survival `6.8%` at `8.0R`, ruin `93.2%`, monthly pass `60.4%`, annual pass `0.0%`
