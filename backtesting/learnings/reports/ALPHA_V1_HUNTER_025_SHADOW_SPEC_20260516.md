# ALPHA_V1 Hunter 0.25x Shadow Spec - 2026-05-16

## Action

Added execution profile `ALPHA_V1-HUNTER-SAFE-025-SHADOW` in `execution/config/exec_configs.json`.

This profile is enabled but has no webhooks, so it runs as dry-run/shadow only. It uses the existing live execution `hunter_orb` engine and the existing `H_ORB_SAFE` branch, scaled to `0.25x` of the Hunter research risk:

| Field | Value |
| --- | --- |
| profile | `ALPHA_V1-HUNTER-SAFE-025-SHADOW` |
| session key | `H_ORB_SAFE` |
| webhooks | none |
| risk_usd | `$87.50` |
| max_single_risk_usd | `$87.50` |
| max_contracts | `5` |
| deployability | `live_native` for dry-run/shadow |
| live_support_notes | `hunter_orb` engine supports the branch rules before order arming; profile has no webhooks |
| exact_replay_required | `yes_before_any_webhook_promotion` |

Verification: `load_exec_configs` reads the profile, and `build_engines` instantiates `HunterORBEngine H_ORB_SAFE` with risk `$87.50`, max single risk `$87.50`, max contracts `5`, the three stress regime gates, and dry-run broker mode.

## Inherited H_ORB_SAFE Parameters

| Parameter | Value |
| --- | --- |
| instrument / execution | `NQ` signal, `MNQ` execution |
| ORB | `09:30-09:45` |
| entry window | `09:45-11:00` |
| flat | `15:50-16:00` |
| direction | both long and short |
| excluded_dow | none |
| regime gates | block `bull_high_vol`, `bear_high_vol`, `bear_medium_vol` |
| candle body min | `55%` |
| rejection wick max | `100%` |
| stop | signal-bar structural stop plus `1.0` point buffer |
| target | `2R`; compress to `1R` when stop is at least `50` points |
| EMA bias | 15m EMA `14`, close source, `0` point tolerance |
| re-entry | `legacy_one_reentry_after_loss` |
| same-bar win re-entry | disabled |
| fast re-entry exhaustion filter | disabled |
| max hold | `270` minutes |

## Evidence Anchor

Source report: `backtesting/learnings/reports/ALPHA_V1_NEXT_STEPS_20260516.md`

Source artifacts: `backtesting/data/results/alpha_v1_next_steps_20260516/`

The current fee-aware ALPHA_V1 aggressive sprint baseline was compared against `0.25x` Hunter sidecars. The selected branch is `ema14_tol0_distnone__withTue__1055__rej100__stress`.

| Scenario | 2024 payout/breach | 2025 payout/breach | 2026_YTD | Max consecutive breaches | Portfolio net / DD |
| --- | --- | --- | --- | --- | --- |
| ALPHA_V1 aggressive sprint | `82.6% / 17.4%` | `73.1% / 26.9%` | `3` payouts / `0` breaches / `3` open | `7` in 2025 | `$53.8k / -$4.04k` |
| + Hunter 0.25x 10y-safe | `88.5% / 11.5%` | `84.6% / 15.4%` | `4` payouts / `0` breaches / `2` open | `4` in 2025 | `$74.5k / -$4.10k` |

The sidecar daily correlation to ALPHA was `0.0287` in the aggressive sprint packet, which is the main portfolio reason it deserves shadow time.

## Shadow Acceptance Checks

Before any live webhook promotion:

- Confirm startup logs show `ALPHA_V1-HUNTER-SAFE-025-SHADOW` as `DRY-RUN (no webhooks)`.
- Confirm engine creation logs show `H_ORB_SAFE`, `engine_type=hunter_orb`, risk `$87.5`, and the three stress regime gates.
- Confirm daily gate audit logs produce `REGIME_GATE_PASSED` or the expected blocking gate.
- Compare shadow `HUNTER_SETUP`, `HUNTER_FILTER_*`, exits, and skipped days against historical replay expectations for at least several active NY sessions.
- Re-run exact/parity replay if new post-`2026-03-24` data materially extends the sample.

## Operating Read

This is now a practical shadow sidecar, not just a research row. Keep it no-webhook until the dry-run logs prove the stress gate, EMA timing, re-entry behavior, and sizing are matching expectations in real time.
