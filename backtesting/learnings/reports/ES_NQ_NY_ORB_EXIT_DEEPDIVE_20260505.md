# ES/NQ NY ORB Exit Deep-Dive (2026-05-05)

- Run slug: `es_nq_ny_orb_exit_deepdive_20260505`
- Full window: `2016-04-17` to `2026-03-24`.
- Scope: `ES NY ORB` and `NQ NY ORB R11` only.
- Purpose: explore runner-management alternatives before spending effort on NQ Asia and NQ HTF-LSI target optimization.
- Important deployability note: baseline and normal rr/tp1 changes are live-native. As of the `exit_mode=single_target` implementation, single-target rows are also live-native candidates pending exact replay; no-BE and delayed-BE policies remain `research_only` until execution supports them directly.

## Policy Replay Ranking

| Leg | Policy | Family | Near | Loose | Full R/PF/DD | ΔR/ΔDD | 2Y ΔR | 1Y ΔR | TP2% | TP1-BE% | Deploy | Live Support | Exact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB | Full exit at current TP1 (1R) | single_target | True | True | 222.5/1.72/8.0 | +95.9/-2.9 | 36.93 | 16.80 | 61.9% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| ES NY ORB | Single target 1R | single_target | True | True | 222.5/1.72/8.0 | +95.9/-2.9 | 36.93 | 16.80 | 61.9% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| ES NY ORB | Current TP1 partial, BE only after 1.5R | split_delayed_be | True | True | 213.5/1.68/9.3 | +86.9/-1.6 | 36.28 | 12.09 | 11.8% | 24.8% | research_only | Delayed breakeven is a research-only runner-management rule until implemented in execution. | yes_after_live_native_impl |
| ES NY ORB | Current TP1 partial, no BE move | split_no_be | False | True | 201.9/1.64/12.3 | +75.3/+1.4 | 33.21 | 13.84 | 14.8% | 0.0% | research_only | Delayed/no breakeven runner management is not a current live-native ALPHA execution knob. | yes_after_live_native_impl |
| ES NY ORB | Current TP1 partial, BE only after 2R | split_delayed_be | True | True | 205.1/1.65/10.8 | +78.5/-0.0 | 31.27 | 11.68 | 12.9% | 14.2% | research_only | Delayed breakeven is a research-only runner-management rule until implemented in execution. | yes_after_live_native_impl |
| ES NY ORB | Current TP1 partial, BE only after 3R | split_delayed_be | True | True | 200.2/1.63/11.2 | +73.6/+0.3 | 32.75 | 13.78 | 13.7% | 7.0% | research_only | Delayed breakeven is a research-only runner-management rule until implemented in execution. | yes_after_live_native_impl |
| ES NY ORB | Current TP1 partial, BE only after 2.5R | split_delayed_be | True | True | 194.4/1.62/11.2 | +67.8/+0.3 | 28.65 | 10.21 | 13.0% | 10.1% | research_only | Delayed breakeven is a research-only runner-management rule until implemented in execution. | yes_after_live_native_impl |
| ES NY ORB | Single target 1.25R | single_target | True | True | 166.1/1.43/10.0 | +39.5/-0.9 | 24.18 | 8.05 | 51.3% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| ES NY ORB | Single target 4R | single_target | False | False | 188.7/1.32/22.2 | +62.1/+11.4 | 43.07 | 4.94 | 19.0% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| ES NY ORB | Single target 1.4R | single_target | False | True | 133.3/1.31/12.0 | +6.7/+1.1 | 22.53 | 4.00 | 46.2% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| NQ NY ORB R11 | Single target 1.25R | single_target | False | True | 147.2/1.61/7.0 | +17.8/+1.0 | 10.07 | 3.17 | 56.0% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| NQ NY ORB R11 | Single target 1R | single_target | True | True | 138.0/1.67/6.0 | +8.6/+0.0 | 10.82 | 0.67 | 62.1% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| NQ NY ORB R11 | Full exit at current TP1 (1.4R) | single_target | True | True | 155.2/1.61/6.4 | +25.8/+0.4 | 4.82 | -0.13 | 53.1% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| NQ NY ORB R11 | Single target 1.4R | single_target | True | True | 155.2/1.61/6.4 | +25.8/+0.4 | 4.82 | -0.13 | 53.1% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| NQ NY ORB R11 | Current TP1 partial, BE only after 1.5R | split_delayed_be | True | True | 160.7/1.63/6.0 | +31.3/+0.0 | 7.44 | -0.69 | 21.7% | 27.0% | research_only | Delayed breakeven is a research-only runner-management rule until implemented in execution. | yes_after_live_native_impl |
| NQ NY ORB R11 | Current TP1 partial, BE only after 2.5R | split_delayed_be | False | True | 149.8/1.58/6.9 | +20.4/+0.9 | 10.73 | -0.86 | 24.3% | 8.3% | research_only | Delayed breakeven is a research-only runner-management rule until implemented in execution. | yes_after_live_native_impl |
| NQ NY ORB R11 | Current TP1 partial, BE only after 2R | split_delayed_be | True | True | 150.8/1.59/6.1 | +21.4/+0.1 | 6.91 | -0.58 | 23.4% | 14.7% | research_only | Delayed breakeven is a research-only runner-management rule until implemented in execution. | yes_after_live_native_impl |
| NQ NY ORB R11 | Single target 1.5R | single_target | False | True | 144.9/1.53/7.5 | +15.5/+1.5 | 5.32 | -0.33 | 50.2% | 0.0% | live_native | `exit_mode=single_target` is now supported; exact replay required before deployment. | yes |
| NQ NY ORB R11 | Current TP1 partial, BE only after 3R | split_delayed_be | False | True | 142.7/1.56/7.3 | +13.3/+1.4 | 8.01 | -1.99 | 24.8% | 3.4% | research_only | Delayed breakeven is a research-only runner-management rule until implemented in execution. | yes_after_live_native_impl |
| NQ NY ORB R11 | Current live-native baseline | baseline | True | True | 129.4/1.50/6.0 | +0.0/+0.0 | 0.00 | 0.00 | 18.1% | 33.0% | live_native | Conditional NQ NY ORB R11 branch; standard ORB fields are supported. | yes_before_live_change |

## Weak Pre-Trade Buckets

| Leg | Bucket | Trades | Net R | Avg R | PF | WR | TP2% | TP1-BE% | Skip ΔR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ NY ORB R11 | gap_q=Q3 | 139 | 8.03 | 0.06 | 1.12 | 48.2% | 13.7% | 32.4% | -8.03 |
| ES NY ORB | gap_q=Q4 | 226 | 16.55 | 0.07 | 1.18 | 61.5% | 6.2% | 55.3% | -16.55 |
| ES NY ORB | gap_q=Q3 | 201 | 18.13 | 0.09 | 1.19 | 53.2% | 9.0% | 38.3% | -18.13 |
| ES NY ORB | dow=Wed | 205 | 19.24 | 0.09 | 1.22 | 58.5% | 5.8% | 46.8% | -19.24 |
| ES NY ORB | dow=Tue | 206 | 22.31 | 0.11 | 1.25 | 57.8% | 8.2% | 46.6% | -22.31 |
| ES NY ORB | dow=Mon | 215 | 25.25 | 0.12 | 1.31 | 60.9% | 3.7% | 44.6% | -25.25 |
| ES NY ORB | entry_time=mid | 315 | 37.46 | 0.12 | 1.29 | 58.4% | 5.7% | 43.5% | -37.46 |
| ES NY ORB | risk_q=Q3 | 634 | 77.84 | 0.12 | 1.30 | 59.0% | 5.8% | 43.7% | -77.84 |
| ES NY ORB | entry_time=late | 239 | 30.83 | 0.13 | 1.34 | 61.5% | 5.0% | 45.2% | -30.83 |
| NQ NY ORB R11 | dow=Wed | 143 | 19.65 | 0.14 | 1.27 | 48.2% | 17.5% | 29.4% | -19.65 |
| NQ NY ORB R11 | risk_q=Q3 | 138 | 19.13 | 0.14 | 1.28 | 50.7% | 15.9% | 34.8% | -19.13 |
| NQ NY ORB R11 | dow=Thu | 145 | 20.14 | 0.14 | 1.30 | 52.4% | 14.5% | 37.2% | -20.14 |
| NQ NY ORB R11 | risk_q=Q4 | 138 | 20.85 | 0.15 | 1.30 | 50.7% | 15.9% | 31.9% | -20.85 |
| NQ NY ORB R11 | gap_q=Q4 | 138 | 24.27 | 0.18 | 1.35 | 51.5% | 16.7% | 34.1% | -24.27 |
| ES NY ORB | entry_time=early | 292 | 58.29 | 0.20 | 1.54 | 63.4% | 8.2% | 52.0% | -58.29 |
| NQ NY ORB R11 | dow=Tue | 131 | 26.36 | 0.20 | 1.41 | 51.1% | 18.3% | 31.3% | -26.36 |

## Read

- The missed branch is not plain TP2 compression; it is runner management. A true full-position exit at the current TP1 is the strongest research policy for both legs, especially ES NY.
- Delaying breakeven after TP1 also looks strong, but it changes the live risk profile by allowing partial winners to become `tp1_sl` givebacks. Treat it as secondary to the simpler full-at-TP1 thesis.
- Current execution now exposes a true full-position single-target mode via `exit_mode=single_target`; run exact replay before live consideration. The older wide-stop target compression path is still not equivalent.
- Bucket diagnostics did not find an obvious negative pre-trade slice. The weaker buckets are still positive, so gating is less attractive than fixing the exit policy.
