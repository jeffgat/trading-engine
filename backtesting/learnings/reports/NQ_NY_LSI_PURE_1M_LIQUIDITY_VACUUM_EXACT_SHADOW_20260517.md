# NQ NY LSI Pure 1m Liquidity-Vacuum Exact Shadow Replay

- Date: 2026-05-17
- Profile: `NQ_LSI_PURE_1M_OBV_SHADOW`
- Session: `NQ_NY_LSI_PURE_1M`
- Candidate: `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`
- Branch: `liquidity_vacuum_book_pull`
- Feature: `ob_vacuum_confirm_last_10s_score`
- DataBento fetches: `0`
- Trades: `21`
- Date match: `True`
- Active decisions: `21`
- Fallback decisions: `0`
- Tier counts: `{'high': 8, 'low': 10, 'mid': 3}`

## Frozen Rule

- Low: feature `< 0.054561`, weight `0.5x`
- Mid: feature `[0.054561, 0.461590)`, weight `1.0x`
- High: feature `>= 0.461590`, weight `1.5x`

## Exact Replay Read

- Baseline exact R: `+5.500R`
- Baseline exact avg: `0.262R`
- Baseline exact PF: `1.79`
- Baseline exact max DD: `-1.500R`
- Shadow weighted R: `+7.250R`
- Shadow weighted avg: `0.345R`
- Shadow weighted PF: `2.21`
- Shadow weighted max DD: `-2.250R`
- Shadow delta: `+1.750R`

## Interpretation

This pushes liquidity-vacuum one step closer to implementation, but it is still a scored-feature replay. It now clears exact live-engine trade-date replay with zero fallbacks, while remaining behind the pure 1m velocity champion's exact-shadow result of `+9.25R`.

Keep liquidity-vacuum as a side research or future ensemble branch. To make it live-native, the execution order-book cache needs MBP-10 depth/microprice fields, not only top-of-book midpoint samples.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_liquidity_vacuum_exact_shadow_20260517/liquidity_vacuum_scored_replay.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_liquidity_vacuum_exact_shadow_20260517/exact_shadow_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_liquidity_vacuum_exact_shadow_20260517/summary.json`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_lsi_pure_1m_liquidity_vacuum_exact_shadow_20260517/report.md`
