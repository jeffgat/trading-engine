# LSI Research - April

## Scope

This report summarizes the April research branch for a new `reference_lsi` variant on `NQ` during the NY session.

The idea was to keep the core 5-minute LSI structure, but replace swing-pivot sweeps with sweeps of completed reference levels:

- `previous_day_high`
- `previous_day_low`
- `asia_high`
- `asia_low`
- `london_high`
- `london_low`

The branch was run using the workflow in `CURRENT_STRATEGY_WORKFLOW.md`:

1. baseline on pre-holdout data
2. broad structural sweep
3. reward-shape sweep on shortlisted structures
4. narrow follow-up around the winning family
5. final pre-holdout confirmation pass

The final holdout was frozen at `2025-01-01+` and was not used.

## Strategy Definition

The tested setup was:

- session: `NQ NY`
- active window: `08:30-14:00 ET`
- flat by `14:00`
- sweep of one completed reference level during the session
- use only FVGs formed before the sweep
- require the inversion within a fixed bar limit after the sweep
- limit entry at the FVG edge
- allow multiple trades per day, but never overlapping
- one published level instance can only be consumed once
- one sweep can only produce one trade

Risk handling:

- structural stop = sweep extreme through inversion bar
- hard minimum stop = `5%` of daily ATR
- hard maximum stop = no wider than a `1-contract` risk

## Baseline

Baseline config:

- `direction_filter=both`
- `entry_end=14:00`
- `ref_lsi_gap_entry_edge=near`
- `ref_lsi_gap_lookback_bars=12`
- `ref_lsi_inversion_max_bars=18`
- `rr=2.0`
- `tp1_ratio=0.5`
- `atr_length=10`

Baseline result on `2016-01-01` to `2024-12-31`:

- `251` trades
- PF `1.0561`
- avg R `0.0136`
- total R `+3.42`
- max DD `-7.12R`

Validation result on `2023-01-01` to `2024-12-31`:

- `57` trades
- PF `1.2182`
- avg R `0.0735`
- total R `+4.19`

Conclusion: the branch was structurally alive and worth exploring further.

## Broad Discovery Findings

### Stage A: structural sweep

The broad structure sweep tested:

- `direction_filter`: `long`, `short`, `both`
- `entry_end`: `11:00`, `12:00`, `13:00`, `14:00`
- `gap_entry_edge`: `near`, `far`
- `gap_lookback_bars`: `3, 6, 9, 12`
- `inversion_max_bars`: `6, 12, 18`

Main findings:

- the strongest raw validation pockets were short-side and early-session
- `11:00` cutoff repeatedly beat later entry windows
- `near` entries clearly beat `far`
- the thin short-only leaders were too sparse to promote
- the live family that survived trade-count and PF requirements converged around:
  - `both`
  - `11:00`
  - `near`

### Stage B: reward-shape sweep

Stage B tested reward shape on the surviving structures:

- `rr`: `1.5, 1.75, 2.0, 2.25, 2.5, 3.0`
- `tp1_ratio`: `0.5, 0.6, 0.7, 0.8`

Main findings:

- the family shifted decisively toward higher reward targets
- the best region was:
  - `RR = 3.0`
  - `TP1 = 0.7-0.8`
- strongest candidates after the broad pass:
  - `both 11:00 near gap6 inv18 rr3.0 tp0.8`
  - `both 11:00 near gap12 inv12 rr3.0 tp0.8`
  - `both 11:00 near gap6 inv18 rr3.0 tp0.7`

Broad-pass promoted results:

- `gap6 inv18 rr3.0 tp0.8`: WF avg R `0.1272`, PF `1.3495`, PSR `0.788`, DSR `0.1687`
- `gap12 inv12 rr3.0 tp0.8`: WF avg R `0.1044`, PF `1.2838`, PSR `0.7686`, DSR `0.1550`
- `gap6 inv18 rr3.0 tp0.7`: WF avg R `0.1016`, PF `1.2825`, PSR `0.7306`, DSR `0.1295`

Conclusion: good structural signal, but too weak on the Bailey-style overfitting gate to promote.

## Narrow Follow-Up

Because the branch was alive but not promotion-ready, the search was narrowed to the winning family only:

- fixed `both`
- fixed `11:00`
- fixed `near`
- structures centered on:
  - `gap6 / inv18`
  - `gap12 / inv12`
- reward neighborhood around:
  - `RR = 3.0-3.25`
  - `TP1 = 0.7-0.8`

Top validation rows in the narrowed pass:

- `gap12 inv12 rr3.25 tp0.7`: val avg R `0.3810`, PF `1.9663`
- `gap12 inv12 rr3.0 tp0.8`: val avg R `0.3786`, PF `1.9596`
- `gap6 inv15 rr3.25 tp0.7`: val avg R `0.3732`, PF `1.9705`
- `gap6 inv18 rr3.25 tp0.7`: val avg R `0.3732`, PF `1.9705`
- `gap6 inv15 rr3.0 tp0.8`: val avg R `0.3713`, PF `1.9652`
- `gap6 inv18 rr3.0 tp0.8`: val avg R `0.3713`, PF `1.9652`

Best walk-forward rows from the narrowed pass:

- `gap6 inv15 rr3.0 tp0.8`: WF avg R `0.1315`, PF `1.3534`, PSR `0.7891`, DSR `0.7891`
- `gap6 inv18 rr3.0 tp0.8`: WF avg R `0.1272`, PF `1.3495`, PSR `0.7880`, DSR `0.7880`
- `gap6 inv15 rr3.25 tp0.7`: WF avg R `0.1217`, PF `1.3272`, PSR `0.7542`, DSR `0.7542`

Important nuance:

- raw validation tended to like `gap12 inv12`
- walk-forward leadership shifted back to `gap6 / inv15-18`

## Final Confirmation Pass

A final micro-branch was run to avoid reopening the full search:

- structures:
  - `gap6 / inv15`
  - `gap6 / inv18`
  - `gap8 / inv18`
  - `gap12 / inv12`
- reward grid:
  - `RR = 3.0, 3.25`
  - `TP1 = 0.7, 0.8`

Raw trials: `16`

Effective trials: `1`

Key result:

- `gap12 inv12` still won raw validation
- but after scoring the full 16-config set with walk-forward, the best OOS config was:
  - `both 11:00 near gap6 inv15 rr3.0 tp0.8`

Final confirmed leader:

- trades: `70`
- WF avg R: `0.1315`
- WF PF: `1.3534`
- total R: `+9.21`
- max DD: `-7.38R`
- PSR: `0.7891`
- DSR: `0.7891`

Second-best:

- `both 11:00 near gap6 inv18 rr3.0 tp0.8`
- WF avg R `0.1272`
- WF PF `1.3495`

The `gap8 inv18` challenger degraded materially and did not remain competitive.

## Final Interpretation

What looks real:

- the branch is causally implemented and structurally alive
- the edge is concentrated in a much tighter family than the initial baseline suggested
- the best family is:
  - `both`
  - `11:00` cutoff
  - `near`
  - `gap6`
  - `inversion_max 15-18`
  - `RR around 3.0`
  - `TP1 around 0.8`

What did not hold up strongly enough:

- broader parameter freedom
- `far` entries
- later entry windows
- the apparent raw-validation leadership of `gap12 inv12`
- promotion into holdout based on PSR strength

## Verdict

This branch should remain **DISCOVERY ONLY** for now.

Reasons:

- the pre-holdout walk-forward results are positive
- the strategy family clearly has structure
- but the best confirmed PSR is still only `0.7891`
- that is below the repo's moderate promotion bar

So the correct decision is:

- do **not** open the `2025-01-01+` holdout yet
- do **not** move this into phase-one
- keep the branch documented as a live candidate family, not a promoted strategy

## 2026-04-08 Follow-Up: ALPHA_V1 NQ NY LSI Retest Plan

### Target Leg

This follow-up is for the single LSI leg in `ALPHA_V1`:

- `strategy=lsi`
- `entry_mode=fvg_limit`
- `session=NY`
- `direction=long`
- `rr=3.0`
- `tp1_ratio=0.34`
- `atr_length=10`
- `min_gap_atr_pct=5.0`
- `lsi_n_left=8`
- `lsi_n_right=60`
- `lsi_fvg_window_left=20`
- `lsi_fvg_window_right=5`
- `excluded_days=(Wed, Thu)` in the frozen baseline
- `1s` magnifier

Frozen code references:

- `backtesting/learnings/ALPHA_V1.md`
- `backtesting/src/orb_backtest/analysis/alpha_v1_downside.py`
- `backtesting/scripts/alpha_v1_combined_backtest.py`

### Confirmed Engine Issue

The current LSI extraction path only recognizes sweep events inside the session's
`in_rth` mask. For the frozen ALPHA_V1 leg, `rth_start="09:30"`, so a pivot low
that is already swept before `09:30` is not consumed by the engine. That stale
pivot can then still appear valid later in the entry window and generate a false
"fresh" sweep/setup.

Important nuance:

- this is not a pivot-detection bug
- pivots are still detected from the full series
- the bug is that sweep consumption is session-gated

Correct semantics for the retest:

- pivots may form anywhere
- once a pivot is violated, it is no longer eligible, even if the violation
  happened outside the valid LSI sweep window
- only sweeps that occur inside the valid sweep window may seed an LSI setup

### Requested Rule Changes

For this retest, the requested structural changes are:

- remove DOW filtering from the config and let the strategy trade all weekdays
- require the liquidity sweep to occur inside `08:30-14:30 ET`
- keep `lsi_n_right=60`
- run a broad sweep on `lsi_n_left` to test whether more left-side structure
  improves quality versus the current `8`

Base assumption for the first pass:

- only the sweep-validity window changes to `08:30-14:30 ET`
- the entry window remains `09:35-15:30`
- the flat logic remains `15:50-16:00`

That keeps the first comparison focused on sweep semantics instead of changing
multiple timing dimensions at once.

### Implementation Needed Before Testing

1. Add an LSI-specific sweep-valid mask for `08:30-14:30 ET`.
2. Make active swing levels consumptive:
   - if price breaches the active swing low/high outside the valid sweep window,
     retire that pivot anyway
   - do not allow the same pivot to be "swept later" inside the entry window
3. Keep FVG/inversion logic tied to valid in-window sweeps only.
4. Add regression tests that cover:
   - pre-entry sweep invalidates the pivot and prevents later reuse
   - sweep at `08:45` is valid
   - sweep after `14:30` consumes the pivot but does not activate a setup
   - no new pivot after an early sweep means no trade

### Proposed 10-Year Test Sequence

Use `2016-01-01` through `2025-12-31` so the retest covers 10 full calendar
years instead of mixing in partial `2026` data.

Phase 0: controls

- run the frozen ALPHA_V1 leg as-is for `2016-01-01` to `2025-12-31`
- run the same legacy logic again with `excluded_days=()` to isolate pure DOW
  removal before any engine changes

Phase 1: corrected anchor

- rerun the leg with:
  - `excluded_days=()`
  - sweep-valid window `08:30-14:30 ET`
  - stale-pivot invalidation fixed
  - all other parameters unchanged

Suggested experiment name:

- `NQ NY 2016-2025 ALPHA_LSI allDays sweep0830-1430 anchor`

Phase 2: broad `lsi_n_left` sweep

- test `lsi_n_left` at:
  - `8, 10, 12, 15, 20, 25, 30, 40`
- keep fixed:
  - `lsi_n_right=60`
  - `rr=3.0`
  - `tp1_ratio=0.34`
  - `atr_length=10`
  - `min_gap_atr_pct=5.0`
  - `fvg_window_left=20`
  - `fvg_window_right=5`
  - `direction=long`
  - `entry_mode=fvg_limit`
  - `excluded_days=()`
- if the best result lands at the upper boundary, extend with:
  - `50, 60`

Phase 3: post-hoc DOW analysis

- do not reintroduce weekday exclusions during the main structural sweep
- after the corrected all-days trades are generated, run post-hoc weekday
  analysis on the anchor and any promoted `lsi_n_left` survivors
- test:
  - single-day exclusions
  - `Wed+Thu`
  - full 32-combination weekday subset table if needed

### Metrics To Compare

Track the following for every control and sweep row:

- trades
- trades per year
- win rate
- PF
- Sharpe
- Net R
- max DD
- Calmar
- median stop in ticks
- negative full years
- R by year
- weekday trade counts and weekday PnL

Primary question:

- does the corrected sweep logic improve structural quality without collapsing
  sample size too severely?

Secondary question:

- after correcting sweep semantics, is any DOW exclusion still worth the lost
  trade count?

### Executed Results (`2016-01-01` to `2025-12-31`)

The retest was executed on `2026-04-08` with the LSI engine patched so that:

- pivots are consumed on any breach
- only breaches inside the configured sweep window can seed an LSI setup
- the tested sweep-valid window is `08:30-14:30 ET`

Important 5-minute timing note:

- with the repo's standard half-open session-mask logic, a sweep window of
  `08:30-14:30` includes bars opening from `08:30` through `14:25`
  and excludes the bar opening at `14:30`

#### Pre-fix controls captured before the engine patch

- frozen alpha logic (`Wed+Thu` excluded):
  - `602` trades
  - WR `58.97%`
  - PF `1.59`
  - Sharpe `3.13`
  - Net R `+115.0`
  - Max DD `-6.63R`
  - Calmar `17.33`
  - median stop `185.5` ticks
  - `0` negative years
- legacy all-days logic:
  - `1011` trades
  - WR `56.68%`
  - PF `1.35`
  - Sharpe `1.96`
  - Net R `+119.4`
  - Max DD `-9.09R`
  - Calmar `13.14`
  - median stop `184.0` ticks
  - `2` negative years

Interpretation:

- the stale-pivot bug was materially inflating trade count and total R
- the effect was not small noise; it was a first-order structural issue

#### Patched controls after stale-pivot invalidation

- patched frozen alpha logic (`Wed+Thu` excluded, no new sweep window yet):
  - `182` trades
  - WR `58.24%`
  - PF `1.53`
  - Sharpe `2.93`
  - Net R `+31.5`
  - Max DD `-4.42R`
  - Calmar `7.11`
  - median stop `179.0` ticks
  - `1` negative year
- patched all-days logic:
  - `325` trades
  - WR `55.69%`
  - PF `1.32`
  - Sharpe `1.79`
  - Net R `+33.9`
  - Max DD `-6.28R`
  - Calmar `5.40`
  - median stop `180.0` ticks
  - `2` negative years

Interpretation:

- fixing stale-pivot reuse cut the old alpha leg down from `602 -> 182` trades
  in the filtered case and from `1011 -> 325` in the all-days case
- the original alpha headline should therefore be treated as overstated under
  the old sweep semantics

#### Corrected Anchor: all-days + sweep window `08:30-14:30`

- corrected anchor (`n_left=8`, `n_right=60`, all weekdays):
  - `319` trades
  - WR `55.49%`
  - PF `1.34`
  - Sharpe `1.89`
  - Net R `+35.5`
  - Max DD `-7.08R`
  - Calmar `5.01`
  - median stop `176.0` ticks
  - `2` negative years

Versus the patched all-days control without the explicit sweep window:

- trades: `325 -> 319`
- PF: `1.32 -> 1.34`
- Sharpe: `1.79 -> 1.89`
- Net R: `+33.9 -> +35.5`
- Max DD: `-6.28R -> -7.08R`
- Calmar: `5.40 -> 5.01`

Interpretation:

- the `08:30-14:30` sweep window slightly improved raw edge and total R
- but it did not improve Calmar versus the patched all-days control
- so the sweep-window change is directionally reasonable, but not obviously
  superior on a risk-adjusted basis by itself

#### Broad `lsi_n_left` Sweep (`n_right=60` fixed)

Tested:

- `8, 10, 12, 15, 20, 25, 30, 40`

Top rows:

- `n_left=8`:
  - `319` trades, PF `1.34`, Sharpe `1.89`, Net R `+35.5`, DD `-7.08R`, Calmar `5.01`
- `n_left=15`:
  - `324` trades, PF `1.28`, Sharpe `1.61`, Net R `+30.7`, DD `-7.86R`, Calmar `3.91`
- `n_left=25`:
  - `327` trades, PF `1.22`, Sharpe `1.29`, Net R `+24.6`, DD `-8.21R`, Calmar `3.00`

Bottom line:

- increasing `n_left` did **not** improve this leg
- the current `n_left=8` remained the clear winner
- once `n_left` moved past `15`, the profile degraded materially
- `n_left=40` fell to PF `1.14`, Sharpe `0.73`, Net R `+13.8`, Calmar `1.34`

Conclusion:

- there is no evidence from this retest that a more "obvious" left-side
  structure improves the alpha leg
- the right-side confirmation width (`n_right=60`) may already be doing most of
  the structural heavy lifting

#### Post-hoc DOW Analysis On The Best Corrected Variant

Baseline for this section:

- corrected best variant = `n_left=8`
- all weekdays enabled
- `319` trades
- Net R `+35.5`
- DD `-7.08R`
- Calmar `5.01`

Best DOW exclusions by Calmar:

- exclude `Thu + Fri`:
  - `208` trades
  - Net R `+28.6`
  - DD `-3.96R`
  - Calmar `7.22`
  - `2` negative years
- exclude `Wed + Thu`:
  - `180` trades
  - Net R `+31.9`
  - DD `-4.42R`
  - Calmar `7.21`
  - `1` negative year
- exclude `Thu` only:
  - `257` trades
  - Net R `+37.9`
  - DD `-5.28R`
  - Calmar `7.17`
  - `1` negative year

Interpretation:

- DOW filtering still matters even after the sweep fix
- `Wed + Thu` remains a strong candidate and cleaned up the profile
  substantially versus all-days
- however, `Thu`-only is now also a serious contender:
  - more trades than `Wed + Thu`
  - higher total R than `Wed + Thu`
  - similar Calmar
  - the same `1` negative year count

### Final Takeaway

The main finding is not a new parameter winner. The main finding is that the
old alpha leg was relying heavily on stale-pivot reuse.

After fixing the sweep semantics:

- the original alpha headline compresses dramatically
- the explicit `08:30-14:30` sweep window is acceptable but not a standalone
  breakthrough
- increasing `n_left` above `8` does not help
- post-hoc DOW filtering still looks valuable

Current recommendation from this retest:

- keep the sweep-invalidated engine behavior
- if this leg is revisited live/research-side, keep `n_left=8`
- shortlist DOW filters for the corrected branch as:
  - `Thu` only
  - `Wed + Thu`

These are the two weekday cuts most worth deeper follow-up on the corrected
engine.

### Legacy / Live-Matched Variant Retest (`2016-01-01` to `2025-12-31`)

On `2026-04-08`, the backtester was extended with two explicit LSI sweep
semantics so the "bug" could be tested directly instead of inferred:

- `lsi_sweep_gate="rth"` + `lsi_stale_breach_consumes_pivot=False`
  - intended to approximate the old backtester-style session-gated reuse
- `lsi_sweep_gate="entry"` + `lsi_stale_breach_consumes_pivot=False`
  - intended to approximate the current live engine behavior, where swings are
    tracked continuously but sweep events are only acted on once the engine
    enters `SCANNING`

#### Headline Comparison

Corrected intended branch:

- corrected frozen (`Wed+Thu` excluded, sweep window `08:30-14:30 ET`):
  - `180` trades
  - WR `57.8%`
  - PF `1.54`
  - Sharpe `2.96`
  - Net R `+31.9`
  - Max DD `-4.42R`
  - Calmar `7.21`
  - `1` negative year
- corrected all-days:
  - `319` trades
  - WR `55.5%`
  - PF `1.34`
  - Sharpe `1.89`
  - Net R `+35.5`
  - Max DD `-7.08R`
  - Calmar `5.01`
  - `2` negative years

Live-matched legacy branch:

- legacy live frozen (`Wed+Thu` excluded, entry-gated non-consumptive sweeps):
  - `310` trades
  - WR `58.7%`
  - PF `1.61`
  - Sharpe `3.17`
  - Net R `+59.8`
  - Max DD `-5.61R`
  - Calmar `10.67`
  - `0` negative years
- legacy live all-days:
  - `544` trades
  - WR `56.4%`
  - PF `1.37`
  - Sharpe `1.95`
  - Net R `+62.8`
  - Max DD `-7.33R`
  - Calmar `8.58`
  - `2` negative years

Old-backtester-style reconstruction:

- legacy backtest frozen:
  - `293` trades
  - WR `58.4%`
  - PF `1.56`
  - Sharpe `2.98`
  - Net R `+53.4`
  - Max DD `-5.83R`
  - Calmar `9.16`
  - `1` negative year
- legacy backtest all-days:
  - `517` trades
  - WR `55.9%`
  - PF `1.33`
  - Sharpe `1.78`
  - Net R `+54.8`
  - Max DD `-7.60R`
  - Calmar `7.21`
  - `3` negative years

Interpretation:

- the live-matched legacy branch materially outperformed the corrected branch
  on both the filtered and all-days runs
- versus corrected all-days, the live-matched legacy branch improved:
  - trades: `319 -> 544`
  - Net R: `+35.5 -> +62.8`
  - Calmar: `5.01 -> 8.58`
- versus corrected frozen, the live-matched legacy branch improved:
  - trades: `180 -> 310`
  - Net R: `+31.9 -> +59.8`
  - Calmar: `7.21 -> 10.67`
  - negative years: `1 -> 0`
- the explicit `rth`-gated reconstruction did **not** fully recover the
  original pre-fix `602 / 1011` trade counts, which implies the historical
  bug was more distorted than a simple non-consumptive gate toggle

#### Legacy Live `lsi_n_left` Sweep

Tested on the live-matched all-days branch:

- `8, 10, 12, 15, 20, 25, 30, 40`

Top rows:

- `n_left=8`:
  - `544` trades, PF `1.37`, Sharpe `1.95`, Net R `+62.8`, DD `-7.33R`, Calmar `8.58`
- `n_left=10`:
  - `535` trades, PF `1.32`, Sharpe `1.74`, Net R `+54.8`, DD `-10.19R`, Calmar `5.38`
- `n_left=15`:
  - `526` trades, PF `1.29`, Sharpe `1.62`, Net R `+50.4`, DD `-9.40R`, Calmar `5.36`

Bottom line:

- even under the legacy/live-matched sweep semantics, `n_left=8` remained the
  clear winner
- increasing left-side structure still degraded the profile

#### Legacy Live Post-hoc DOW Analysis

Best exclusions by Calmar on the best live-matched branch (`n_left=8`, all days):

- exclude `Thu + Fri`:
  - `343` trades
  - Net R `+55.8`
  - DD `-4.56R`
  - Calmar `12.24`
  - `2` negative years
- exclude `Thu` only:
  - `428` trades
  - Net R `+66.3`
  - DD `-5.75R`
  - Calmar `11.52`
  - `1` negative year
- exclude `Wed + Thu + Fri`:
  - `225` trades
  - Net R `+49.3`
  - DD `-4.59R`
  - Calmar `10.75`
  - `0` negative years
- exclude `Wed + Thu`:
  - `310` trades
  - Net R `+59.8`
  - DD `-5.61R`
  - Calmar `10.67`
  - `0` negative years

Interpretation:

- if this legacy behavior is treated as an intentional strategy, Thursday is
  still the main drag day
- `Thu` only is now especially attractive because it keeps more trades and more
  total R than `Wed + Thu`, while still improving Calmar materially

#### Validity Assessment

This legacy/live-matched branch appears **causal and live-executable** in the
sense that it does not require future bars for sweep confirmation:

- the live swing tracker checks sweeps against the **previous bar's** confirmed
  swing level, not the current bar's future state
- the live LSI engine feeds the swing tracker on every bar, but only begins
  acting on sweep events once the engine enters the entry-window `SCANNING`
  state

However, there are still real problems if it is kept as a hidden bug:

- it is a different strategy thesis than "fresh sweep of liquidity"
- it is path-dependent across restarts:
  - continuous live operation preserves swing levels across days
  - NY restart recovery only warms the swing tracker with same-day bars before
    restoring `SCANNING`
- that means continuous-run behavior and post-restart behavior can diverge if
  the strategy is relying on older unretires swings
- if this branch is adopted, it should be promoted as an explicit named
  strategy variant, not left implicit as accidental behavior

Practical recommendation:

- the idea is valid enough to treat as a separate strategy candidate
- if promoted, define it explicitly as the "entry-gated non-consumptive LSI"
  branch
- keep `n_left=8`
- prioritize DOW follow-up on:
  - `Thu` only
  - `Wed + Thu`
  - `Thu + Fri`

#### Exact Execution Replay: `legacy-LSI` Single-Leg Check

After the live engine was updated to expose an explicit `legacy-LSI` variant
and to preserve prior-day swing context on restart recovery, a one-leg exact
execution replay was run through the live state machine itself on:

- `NQ_NY_LSI`
- `rr=3.0`
- `tp1_ratio=0.34`
- `min_gap_atr_pct=5.0`
- `atr_length=10`
- `lsi_n_left=8`
- `lsi_n_right=60`
- `entry_mode=fvg_limit`
- `lsi_variant=legacy-LSI`
- all weekdays enabled
- `2016-01-01` to `2025-12-31`

Exact replay result:

- `599` trades
- WR `56.8%`
- PF `1.47`
- Sharpe `2.54`
- Net R `+83.0`
- Max DD `-5.51R`
- Calmar `15.06`
- all `10` full years positive

Post-hoc weekday cuts on the exact replayed trade set:

- all days:
  - `599` trades, `+83.0R`, DD `-5.51R`, Calmar `15.06`
- exclude `Thu`:
  - `471` trades, `+69.9R`, DD `-5.35R`, Calmar `13.05`
- exclude `Wed + Thu`:
  - `348` trades, `+67.1R`, DD `-6.32R`, Calmar `10.62`
- exclude `Thu + Fri`:
  - `364` trades, `+46.2R`, DD `-7.13R`, Calmar `6.48`

Interpretation:

- the exact live-engine replay is materially stronger than the research
  surrogate on this branch
- unlike the research backtester retest, the exact replay prefers **all days**
  over the tested DOW cuts
- if live deployment choices need a tie-breaker, the exact replay should take
  precedence over the surrogate because it is running the production state
  machine directly

## Recommendation If Revisited

If this branch is revisited later, do not broaden the search again.

Keep it pinned to:

- `both`
- `11:00`
- `near`
- `gap6`
- `inversion_max = 15 or 18`
- `RR around 3.0`
- `TP1 around 0.8`

If a future branch cannot improve the overfitting-adjusted statistics from that tight pocket, the idea should be considered exhausted without touching holdout.

## Timeframe Restart Check

A fresh restart check was run with the **same baseline-case parameters** but with gap detection and inversion logic moved from `5m` to lower base timeframes:

- same `reference_lsi` rules
- same `direction_filter=both`
- same `entry_end=14:00`
- same `near`
- same `gap_lookback=12`
- same `inversion_max=18`
- same `RR=2.0`
- same `TP1=0.5`
- same `ATR=10`
- same frozen holdout at `2025-01-01+`

Results:

| Base TF | Pre Trades | Pre PF | Pre avg R | Validation Trades | Validation PF | Validation avg R | Alive? |
|--------|-----------:|-------:|----------:|------------------:|--------------:|-----------------:|:------:|
| `5m` | 251 | 1.0561 | 0.0136 | 57 | 1.2182 | 0.0735 | YES |
| `3m` | 234 | 1.3730 | 0.1179 | 49 | 1.6685 | 0.2092 | YES |
| `1m` | 132 | 1.1493 | 0.0627 | 22 | 0.8750 | -0.0435 | NO |

Interpretation:

- `3m` materially improved the unchanged baseline over the original `5m` branch
- `1m` did not survive the alive gate because validation turned negative
- the next lower-timeframe branch, if pursued, should be a dedicated `3m` discovery branch
- `1m` should stay closed unless a different thesis is introduced, rather than simply shrinking the bar size again

## 3m Discovery Branch

The `3m` branch was then run through the full pre-holdout discovery workflow with the same all-level `reference_lsi` thesis and the same frozen holdout at `2025-01-01+`.

### What changed vs 5m

The winning family shifted materially away from the original `5m` pocket:

- still `both`
- later cutoffs became viable: `12:00-13:00`
- both `near` and `far` survived Stage A, with `far` no longer obviously inferior
- the winning structural pocket tightened around:
  - `inversion_max = 12`
  - `gap_lookback = 6-12`
  - `RR = 2.5-3.0`
  - `TP1 = 0.7-0.8`

Stage A survivors:

- `both 12:00 far gap12 inv12`
- `both 13:00 far gap9 inv12`
- `both 14:00 far gap6 inv12`
- `both 13:00 far gap3 inv18`
- `both 13:00 far gap12 inv12`
- `both 14:00 far gap3 inv18`
- `both 13:00 near gap6 inv12`
- `both 12:00 near gap6 inv12`

### Promoted 3m candidates

1. `both 13:00 far gap9 inv12 rr3.0 tp0.7`
   - pre-holdout: `107` trades, PF `1.611`, avg R `0.293`
   - walk-forward OOS: `67` trades, avg R `0.392`, PF `1.877`, total R `+26.25`, max DD `-4.41R`
   - PSR / DSR: `0.989 / 0.769`

2. `both 12:00 near gap6 inv12 rr3.0 tp0.8`
   - pre-holdout: `116` trades, PF `1.800`, avg R `0.296`
   - walk-forward OOS: `78` trades, avg R `0.300`, PF `1.837`, total R `+23.42`, max DD `-5.27R`
   - PSR / DSR: `0.997 / 0.886`

3. `both 13:00 near gap6 inv12 rr2.5 tp0.8`
   - pre-holdout: `130` trades, PF `1.739`, avg R `0.269`
   - walk-forward OOS: `87` trades, avg R `0.294`, PF `1.861`, total R `+25.54`, max DD `-5.57R`
   - PSR / DSR: `0.997 / 0.881`

### Interpretation

This is a very different outcome from the original `5m` branch:

- the `3m` branch is not just structurally alive
- it produced a small frozen shortlist with strong walk-forward transfer
- all three promoted candidates cleared the repo's moderate PSR bar
- all three also cleared the DSR threshold using `456` raw trials and `8` effective trials

So, unlike the original `5m` branch, the `3m` branch now looks promotion-worthy as a discovery output.

## Updated Verdict

- `5m` all-level branch: keep as discovery-only historical reference
- `1m` restart: no-go at baseline
- `3m` branch: **new lead branch**

If this research continues, the next clean step is to treat the `3m` shortlist as frozen promoted candidates and move them into downstream evaluation rather than reopening broad discovery again.

## 3m Phase-One Read

The frozen `3m` shortlist was then run through a phase-one payout-sprint evaluation using the repo default funded-account model:

- start: `$50,000`
- trailing DD: `$2,000`
- first payout floor: `$52,500`
- risk before first payout: `$500`
- risk after first payout: `$250`

Important methodology note:

- Phase 3 payout scorecards used the stitched discovery OOS stream from `2019-01-01` to `2024-12-31`
- Phase 4 then opened the frozen holdout once on `2025-01-01` to `2026-03-24`

### Phase-one candidates

1. `both 13:00 far gap9 inv12 rr3.0 tp0.7`
2. `both 12:00 near gap6 inv12 rr3.0 tp0.8`
3. `both 13:00 near gap6 inv12 rr2.5 tp0.8`

### Main result

The branch remained impressive on stitched OOS payout modeling, but the untouched holdout was too weak to turn it into a strong phase-one candidate.

Best candidate:

- `both 13:00 far gap9 inv12 rr3.0 tp0.7`
- stitched OOS metrics: `67` trades, PF `1.8766`, avg R `0.3917`, total R `+26.25`
- OOS funded scorecard: payout rate `77.1%`, breach rate `3.5%`, EV/start `$282.76`
- holdout metrics: `18` trades, PF `1.3016`, avg R `0.1812`, total R `+3.26`
- holdout funded scorecard: payout rate `1.6%`, breach rate `81.2%`, EV/start `-$99.74`

The two near-entry challengers were worse on holdout:

- `both 12:00 near gap6 inv12 rr3.0 tp0.8`
  - holdout PF `0.5372`, avg R `-0.2509`, funded payout `0.0%`, funded EV/start `-$100`
- `both 13:00 near gap6 inv12 rr2.5 tp0.8`
  - holdout PF `0.4970`, avg R `-0.2774`, funded payout `0.0%`, funded EV/start `-$100`

### Interpretation

This means:

- `3m` solved the discovery problem
- it did **not** fully solve the phase-one deployment problem
- the leader is still the only candidate with even modestly positive raw holdout trade quality
- but none of the candidates converted that into a convincing holdout first-payout business

## Current Recommendation

- keep `both 13:00 far gap9 inv12 rr3.0 tp0.7` as the only serious `3m` leader
- treat it as **conditional**, not strong
- do **not** promote the two near-entry challengers further
- do **not** move this branch to phase two

If this branch is revisited again, the next clean question is no longer “what timeframe?”
It is:

- why does the `3m` edge survive discovery but fail the holdout payout conversion?

That likely means the next research branch should be narrower and explanatory:

- attribution by reference-level family on the `3m` leader
- holdout-period failure analysis
- or a new `3m previous_day_* + asia_*` restricted thesis

## 3m Holdout Failure Analysis

A focused failure-analysis pass was then run on the all-level `3m` phase-one leader:

- candidate: `both 13:00 far gap9 inv12 rr3.0 tp0.7`
- stitched OOS comparison stream: `2019-01-01` to `2024-12-31`
- holdout read: `2025-01-01` to `2026-03-24`

### Key findings

- raw holdout edge did not fully collapse:
  - holdout: `18` trades, PF `1.3016`, avg R `0.1812`, total R `+3.26`
- the real failure was payout conversion speed:
  - OOS funded payout rate: `77.1%`
  - holdout funded payout rate: `1.6%`
  - holdout funded EV/start: `-$99.74`
- most starts either stayed open too long or breached before enough positive trades accumulated
- the drag was concentrated in high-side / short trades:
  - short holdout: `11` trades, avg R `-0.4615`, PF `0.2884`
  - long holdout: `7` trades, avg R `1.1911`, PF `5.7965`
- holdout time-of-day was also uneven:
  - `09:30-10:30` dragged
  - `10:30-12:00` held up materially better

### Important nuance

This was not a clean “London caused the holdout failure” story.
On the all-level leader, London was actually the best holdout level family on raw trade quality, though on a small sample.
So the all-level holdout miss is best described as:

- insufficient trade velocity for a payout model
- poor holdout behavior in short / high-side sweeps
- not enough evidence that the old far-entry all-level leader is a deployable phase-one business

## 3m Restricted Thesis Restart (`previous_day_* + asia_*`)

After the failure analysis, discovery was restarted from the beginning on `3m`, but with a restricted level set:

- active levels only:
  - `previous_day_high`
  - `previous_day_low`
  - `asia_high`
  - `asia_low`
- excluded:
  - `london_high`
  - `london_low`
- same frozen holdout at `2025-01-01+`
- same discovery pipeline and trial accounting

### Restricted baseline

- pre-holdout: `188` trades, PF `1.4965`, avg R `0.1447`, total R `+27.2`
- validation: `41` trades, PF `2.0714`, avg R `0.2836`, total R `+11.63`

This is a materially stronger baseline than the original all-level `3m` branch.

### Restricted promoted shortlist

- `both 12:00 near gap9 inv12 rr3.0 tp0.8`
  - pre-holdout: `101` trades, PF `1.8329`, avg R `0.3016`
  - WF OOS: `68` trades, avg R `0.3248`, PF `1.9874`, total R `+22.09`
  - PSR / DSR: `0.9961 / 0.8198`
- `both 13:00 near gap9 inv12 rr2.5 tp0.8`
  - pre-holdout: `113` trades, PF `1.8014`, avg R `0.2747`
  - WF OOS: `75` trades, avg R `0.3189`, PF `2.0386`, total R `+23.92`
  - PSR / DSR: `0.9961 / 0.8280`
- `both 14:00 near gap6 inv12 rr2.5 tp0.8`
  - pre-holdout: `101` trades, PF `1.7967`, avg R `0.2742`
  - WF OOS: `69` trades, avg R `0.3007`, PF `1.9382`, total R `+20.75`
  - PSR / DSR: `0.9935 / 0.7771`

Trial posture:

- raw trials: `456`
- effective trials: `11`

### Interpretation

The restricted `3m` branch is now the cleaner live candidate than the old all-level `3m` family:

- stronger baseline
- cleaner promoted family
- all promoted configs converged on `near` entries, `inv12`, and `TP1=0.8`
- no holdout has been opened for this restricted branch yet

## Current Recommendation

- retire the old all-level `3m` far-entry leader as the main live candidate
- keep its failure analysis as the cautionary anchor
- promote the restricted `3m previous_day_* + asia_*` branch as the new frozen discovery lead
- next clean step: run downstream phase-one evaluation on the restricted shortlist only
- do not do more broad tuning before that, and do not touch the restricted holdout until the phase-one packet is ready

## Restricted 3m Previous Day + Asia Phase One

The restricted `3m previous_day_* + asia_*` shortlist was then taken into the same phase-one payout workflow, opening its frozen holdout once on `2025-01-01` to `2026-03-24`.

### Restricted phase-one summary

- `both 12:00 near gap9 inv12 rr3.0 tp0.8`
  - stitched OOS: `68` trades, PF `1.9874`, avg R `0.3248`
  - OOS funded payout: `77.1%`, EV/start `$270.00`
  - holdout: `15` trades, PF `0.7802`, avg R `-0.0865`, total R `-1.30`
  - holdout funded payout: `0.0%`, EV/start `-$100.00`
- `both 13:00 near gap9 inv12 rr2.5 tp0.8`
  - stitched OOS: `75` trades, PF `2.0386`, avg R `0.3189`
  - OOS funded payout: `75.0%`, EV/start `$215.90`
  - holdout: `15` trades, PF `0.7241`, avg R `-0.1197`, total R `-1.80`
  - holdout funded payout: `0.0%`, EV/start `-$100.00`
- `both 14:00 near gap6 inv12 rr2.5 tp0.8`
  - stitched OOS: `69` trades, PF `1.9382`, avg R `0.3007`
  - OOS funded payout: `64.7%`, EV/start `$190.54`
  - holdout: `13` trades, PF `0.3814`, avg R `-0.3564`, total R `-4.63`
  - holdout funded payout: `0.0%`, EV/start `-$100.00`

### Interpretation

This means the restricted thesis improved discovery quality but did **not** improve holdout payout conversion.
In fact, it was weaker on raw holdout trade quality than the older all-level `3m` far-entry leader:

- old all-level leader holdout: PF `1.3016`, avg R `0.1812`, total R `+3.26`
- restricted leader holdout: PF `0.7802`, avg R `-0.0865`, total R `-1.30`

So the restricted branch was a good Bailey-style follow-up, but it did not rescue the strategy family for phase-one deployment.

## Final April Read

- `5m` all-level branch: discovery-only, never strong enough to open holdout early
- `3m` all-level branch: strong discovery, weak holdout payout conversion
- `3m previous_day_* + asia_*` branch: stronger discovery still, but holdout failed outright on all three candidates

## Final Recommendation

- do **not** promote the current restricted `3m` candidate to live phase-one consideration
- do **not** tune this restricted branch further, because its holdout has now been opened
- keep the reports as a completed negative result on this family
- if this idea is revisited, it should be treated as a genuinely new thesis, not a continuation of this parameter line
