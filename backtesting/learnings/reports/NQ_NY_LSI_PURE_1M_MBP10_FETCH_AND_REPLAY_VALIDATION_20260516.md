# NQ NY LSI Pure 1m MBP-10 Fetch and Replay Validation - 2026-05-16

## Objective

Move the pure 1m order-book velocity survivor past the historical MBP-10 data blocker without exceeding the user's requested `$20` Databento spend ceiling.

Candidate:

- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`
- Overlay: `pure_1m_long_confirm_last_velocity`
- Feature: `confirm_last_10s_mid_velocity_ticks_per_second`
- Frozen sizing: `0.5x / 1.0x / 1.5x`
- Frozen thresholds: low `< -0.322`, mid `[-0.322, 0.912)`, high `>= 0.912`

## Data Fetch

Before fetching, the local manifest showed the exact pure-survivor trade windows were already covered, including a `+/-30s` buffer. To avoid paying for duplicate snippets, the new request targeted the next useful validation blocker: continuous morning-prefix MBP-10 for every holdout trade date, replayable from the RTH open into the signal.

Window policy:

- `09:30 ET` to `max(signal_end + 5m, 10:30 ET)` per holdout trade date.
- `21` holdout windows / `21` holdout trades.
- CSV: `backtesting/data/results/nq_ny_lsi_pure_1m_mbp10_fetch_20260516/holdout_morning_prefix_windows.csv`

Databento quote and fetch:

- Dataset/schema: `GLBX.MDP3` / `mbp-10`
- Record count: `84,835,005`
- Billable size: `31.219 GB`
- Estimated cost: `$12.1006`
- User ceiling: `$20.00`
- Downloaded compressed size: `2.311 GB`
- Files expected/present: `21/21`
- Cost summary: `backtesting/data/results/nq_ny_lsi_pure_1m_mbp10_fetch_20260516/download_cost_summary.json`
- Integrity summary: `backtesting/data/results/nq_ny_lsi_pure_1m_mbp10_fetch_20260516/download_integrity_summary.json`

The downloader now supports `--max-cost` and estimates all chunks before starting any download. This was used on both the quote-only run and the actual fetch.

## Live-Path Replay Validation

Added `backtesting/scripts/validate_nq_lsi_pure_1m_velocity_mbp10_replay.py` to replay fetched raw DBN files through the same execution-facing path intended for live trading:

1. DataBento `MBP10Msg`
2. top-of-book bid/ask samples
3. `OrderbookFeatureCache`
4. `OrderbookVelocityTierSizer`

Representative low/mid/high replay:

- Trades checked: `3`
- Feature matches: `3/3`
- Tier matches: `3/3`
- Weight matches: `3/3`
- Result: pass

Full holdout morning replay:

- Trades checked: `21`
- Feature matches: `21/21`
- Tier matches: `21/21`
- Weight matches: `21/21`
- Result: pass
- Output: `backtesting/data/results/nq_ny_lsi_pure_1m_velocity_mbp10_replay_validation_20260516/replay_validation.csv`

## Conclusion

The historical MBP-10 fetch path is now cost-gated and usable, and the fetched holdout morning-prefix data validates the raw DBN-to-live-cache path for the pure 1m velocity survivor.

Status: still not live-promoted, but the MBP-10 historical data blocker for this survivor is cleared. Remaining promotion work is execution-engine parity around the exact pure 1m LSI timing/entry path, then paper/shadow mode with `dynamic_sizing_shadow_enabled=true` before quantity-changing live use.
