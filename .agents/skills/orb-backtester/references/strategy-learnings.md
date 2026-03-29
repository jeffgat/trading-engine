# Strategy Learnings & Insights

Shared knowledge base for all agents working on ORB+FVG strategy development. Read this file before running backtests, optimizing parameters, or proposing strategy changes. Update it after discovering meaningful insights.

---

## Parameter Insights

- **max_gap_points=100 is too loose for ES**: NQ-optimized config applied to ES (Run #16) produced Sharpe 0.92 vs NQ's 1.39 over comparable 10yr period. ES has smaller absolute point moves than NQ, so 100-point max gap filter lets in low-quality setups. Needs its own sweep.
- **Best NQ config (Runs 9-14)**: rr=2.5, tp1_ratio=0.5, ny_stop_atr_pct=7.5, ny_min_gap_atr_pct=2.25, ny_max_gap_points=100, asia_stop_atr_pct=5.25, asia_min_gap_atr_pct=0.9, asia_max_gap_points=50. Sharpe 2.86 on 2024-2025, degrades to 1.39 on 2016-2026.

## Session Behavior

<!-- Record how different sessions (NY, Asia, London) behave differently -->

*No entries yet.*

## Signal Observations

- **ES has a strong long bias with NQ params**: Run #16 — longs $1.02M (48.7% WR) vs shorts $176K (45.6% WR) over 2015-2026. Short setups may need tighter filters or different gap criteria on ES.

## Failed Hypotheses

<!-- Record ideas that were tested and did NOT improve results — prevents re-testing -->

*No entries yet.*

## Known Edge Cases

<!-- Record specific dates, market conditions, or scenarios that cause problems -->

*No entries yet.*

## Optimization Results

<!-- Record notable sweep results: what parameter combinations performed best and on what data -->

*No entries yet.*
