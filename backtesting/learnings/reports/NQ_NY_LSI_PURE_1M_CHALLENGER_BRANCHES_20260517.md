# NQ NY LSI Pure 1m Challenger Branches - 2026-05-17

## Objective

Start three challenger branches against the current pure 1m order-book velocity champion without new DataBento fetches.

Branches:

- Reversal violence relative to day: local 1s price movement normalized by same-day movement.
- Absorption then release: price sweep/reclaim and existing MBP-10 absorption/release features.
- Liquidity vacuum / book pull: existing MBP-10 depth/microprice improvement features.

## Baseline

- Validation trades: `33`, baseline `10.55R`.
- Holdout trades: `21`, baseline `4.84R`.
- Current pure 1m velocity champion holdout: `8.33R`, `0.397R` avg, PF `2.28`.
- DataBento fetches: `0`.

## Top Holdout Reads

| Branch | Feature | Holdout Weighted R | Holdout Avg | PF | Max DD | Holdout Read | Validation Read |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `liquidity_vacuum_book_pull` | `ob_vacuum_confirm_last_10s_score` | 7.02 | 0.334 | 2.17 | -2.25 | `supported_after_exposure_normalization` | `supported_after_exposure_normalization` |
| `liquidity_vacuum_book_pull` | `ob_vacuum_pre_confirm_30s_score` | 5.93 | 0.282 | 1.91 | -1.75 | `supported_after_exposure_normalization` | `failed_after_exposure_normalization` |
| `reversal_violence_relative_to_day` | `price_violence_last_30s_score` | 6.04 | 0.288 | 1.81 | -1.50 | `mild_after_exposure_normalization` | `supported_after_exposure_normalization` |
| `reversal_violence_relative_to_day` | `price_violence_signal_bar_score` | 6.17 | 0.294 | 1.77 | -2.00 | `mild_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `reversal_violence_relative_to_day` | `price_violence_last_10s_score` | 6.28 | 0.299 | 1.79 | -2.00 | `mild_after_exposure_normalization` | `mild_after_exposure_normalization` |
| `absorption_then_release` | `ob_absorption_release_confirm_full_score` | 5.30 | 0.253 | 1.66 | -2.50 | `failed_after_exposure_normalization` | `supported_after_exposure_normalization` |
| `liquidity_vacuum_book_pull` | `ob_vacuum_confirm_full_score` | 4.19 | 0.200 | 1.60 | -2.25 | `failed_after_exposure_normalization` | `supported_after_exposure_normalization` |
| `absorption_then_release` | `price_trapped_reversal_confirm_score` | 3.51 | 0.167 | 1.39 | -2.50 | `failed_after_exposure_normalization` | `failed_after_exposure_normalization` |
| `absorption_then_release` | `price_confirm_reclaim_score` | 3.51 | 0.167 | 1.39 | -2.50 | `failed_after_exposure_normalization` | `failed_after_exposure_normalization` |
| `absorption_then_release` | `ob_absorption_release_confirm_last_10s_score` | 7.26 | 0.346 | 1.69 | -2.50 | `exposure_only_no_tier_discrimination` | `exposure_only_no_tier_discrimination` |

## Interpretation

The only challenger supported on both validation and holdout was `ob_vacuum_confirm_last_10s_score` from `liquidity_vacuum_book_pull`. It improved holdout baseline from `4.84R` to `7.02R`, but remained below the current pure 1m velocity champion's `8.33R`.

The price-violence branch is directionally useful but mild; the absorption-release branch is unstable on this pure 1m trade set; the liquidity-vacuum confirm-last-10s branch is the only serious side branch from this pass.

These are challenger branches, not promotion candidates yet. Any strong read still needs exact execution implementation/replay and forward shadow testing before it can compete with the current pure 1m MBP-10 velocity champion.
