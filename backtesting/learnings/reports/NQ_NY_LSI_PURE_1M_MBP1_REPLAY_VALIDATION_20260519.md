# NQ NY LSI Pure 1m MBP-1 Replay Validation - 2026-05-19

## Objective

Retest the pure 1m order-book velocity survivor with `mbp-1` instead of
`mbp-10`, because the user's current DataBento Standard plan includes MBP-1
but not MBP-10.

Candidate:

- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`
- Overlay: `pure_1m_long_confirm_last_velocity`
- Feature: `confirm_last_10s_mid_velocity_ticks_per_second`
- Frozen sizing: `0.5x / 1.0x / 1.5x`
- Frozen thresholds: low `< -0.322`, mid `[-0.322, 0.912)`, high `>= 0.912`

## Data Fetch

Used the same 21 holdout morning-prefix windows created for the MBP-10 replay:

- Window CSV: `backtesting/data/results/nq_ny_lsi_pure_1m_mbp10_fetch_20260516/holdout_morning_prefix_windows.csv`
- Window policy: `09:30 ET` to `max(signal_end + 5m, 10:30 ET)` per holdout trade date.
- Dataset/schema: `GLBX.MDP3` / `mbp-1`
- Files expected/present: `21/21`
- Record count: `56,107,960`
- Billable size: `4.489 GB`
- Estimated/fetched cost: `$0.5676`
- Downloaded compressed size: `1.089 GB`
- Storage: `backtesting/data/raw/orderbook/NQ/mbp-1/`

The first cost attempt exposed an environment issue: the shell had a different
`DATABENTO_API_KEY` than `backtesting/.env`, so the downloader now prefers the
local `.env` file when present.

## Replay Validation

The replay validator now accepts `--schema mbp-1|mbp-10` and decodes best
bid/ask from either schema into the same execution-facing path:

1. DataBento DBN records
2. top-of-book samples
3. `OrderbookFeatureCache`
4. `OrderbookVelocityTierSizer`

MBP-1 result:

- Trades checked: `21`
- Active sizing decisions: `21/21`
- Feature exact matches: `20/21`
- Tier matches: `21/21`
- Weight matches: `21/21`
- Max raw feature drift: `0.05` ticks/second
- Sizing parity: `pass`
- Output: `backtesting/data/results/nq_ny_lsi_pure_1m_velocity_mbp1_replay_validation_20260519/replay_validation.csv`

The only raw feature mismatch was:

| Date | MBP-10 expected | MBP-1 replay | Diff | Tier | Weight |
| --- | ---: | ---: | ---: | --- | ---: |
| 2026-04-20 | `1.80` | `1.85` | `+0.05` | `high` | `1.5x` |

Control MBP-10 full replay:

- Trades checked: `21`
- Feature exact matches: `21/21`
- Tier matches: `21/21`
- Weight matches: `21/21`
- Output: `backtesting/data/results/nq_ny_lsi_pure_1m_velocity_mbp10_replay_validation_all_20260519/replay_validation.csv`

## Conclusion

MBP-1 is sufficient for the pure 1m midpoint-velocity survivor because the
live/replay feature only needs best bid and best ask. On the full 21-trade
holdout replay, MBP-1 preserved every frozen tier and every risk weight.

This does not validate deeper-book ideas. Liquidity-vacuum, absorption depth,
multi-level pull/reload, and book imbalance beyond best bid/ask still need
MBP-10 or MBO. For the current implementation champion, MBP-1 can replace
MBP-10 as the live/historical data source.

## Implementation Notes

- `backtesting/scripts/download_orderbook_data.py` now documents MBP-1 as valid
  for top-of-book velocity and prefers `backtesting/.env` over stale shell keys.
- `backtesting/scripts/validate_nq_lsi_pure_1m_velocity_mbp10_replay.py` now
  supports `--schema mbp-1`.
- Next execution work should rename the live order-book runtime away from
  MBP-10-specific flags and allow `schema = "mbp-1"` for the pure 1m shadow
  path.
