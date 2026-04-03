# Strategy Learnings & Insights

Shared knowledge base for all agents working on ORB+FVG strategy development. Read this file before running backtests, optimizing parameters, or proposing strategy changes. Update it after discovering meaningful insights.

---

## Parameter Insights

- **max_gap_points=100 is too loose for ES**: NQ-optimized config applied to ES (Run #16) produced Sharpe 0.92 vs NQ's 1.39 over comparable 10yr period. ES has smaller absolute point moves than NQ, so 100-point max gap filter lets in low-quality setups. Needs its own sweep.
- **Best NQ config (Runs 9-14)**: rr=2.5, tp1_ratio=0.5, ny_stop_atr_pct=7.5, ny_min_gap_atr_pct=2.25, ny_max_gap_points=100, asia_stop_atr_pct=5.25, asia_min_gap_atr_pct=0.9, asia_max_gap_points=50. Sharpe 2.86 on 2024-2025, degrades to 1.39 on 2016-2026.
- **NQ_NY_LSI medium-vol gate does not transfer cleanly to FAST_V1.1 params**: Reusing the RR2/TP0.5 regime-avoidance rule (`skip bull_medium_vol + sideways_medium_vol`) on FAST_V1.1 NQ_NY_LSI (`rr=3.0`, `tp1_ratio=0.34`, `atr_length=10`, Wed+Thu excluded) improved trade quality but hurt risk-adjusted return on a Calmar basis. On 2016-01-01 to 2026-03-31, trades fell 611→446, WR rose 59.3%→62.1%, PF rose 1.61→1.84, Sharpe rose 3.22→4.14, but Net R fell +120.1R→+113.9R and Calmar fell 18.10→17.18 with unchanged DD (-6.63R). On 2021-01-01 to 2026-03-31, the same pattern held: 312→211 trades, PF 1.70→1.96, Sharpe 3.44→4.28, but Net R +65.9R→+55.9R and Calmar 9.94→8.43. Conclusion: this gate is parameter-dependent; it helps the RR2/TP0.5 variant more than the FAST_V1.1 RR3/TP0.34 variant.

## Session Behavior

<!-- Record how different sessions (NY, Asia, London) behave differently -->

*No entries yet.*

## Signal Observations

- **ES has a strong long bias with NQ params**: Run #16 — longs $1.02M (48.7% WR) vs shorts $176K (45.6% WR) over 2015-2026. Short setups may need tighter filters or different gap criteria on ES.
- **Bull specialist 15m HH/HL must reset each session day**: The old `hh_hl_2_vwap` backtesting logic let 15m structure chains carry across session boundaries, which overstated the live-aligned bull specialist. On NQ NY FAST bull-specialist settings over 2016-01-01 to 2026-02-28, the legacy cross-day gate showed 90 trades / +33.68R / PF 1.75, while the live-matched day-reset gate showed 64 trades / +17.99R / PF 1.54. In the 2025-03-01 to 2026-02-28 holdout, results dropped from 5 trades / +5.2R to 3 trades / +0.4R. Treat pre-fix bull-specialist backtests as inflated if they used the old cross-day structure logic.

## Failed Hypotheses

<!-- Record ideas that were tested and did NOT improve results — prevents re-testing -->

*No entries yet.*

## Known Edge Cases

<!-- Record specific dates, market conditions, or scenarios that cause problems -->

*No entries yet.*

## Optimization Results

<!-- Record notable sweep results: what parameter combinations performed best and on what data -->

*No entries yet.*
