# FAST_V1.1 Portfolio

This file documents the exact `FAST_V1.1` execution profile currently defined in the execution engine.

Source of truth:

- `execution/config/exec_configs.json` selects the legs that belong to `FAST_V1.1`
- `execution/src/trader/main.py` provides the base leg definitions in `SESSION_CONFIGS` and `LSI_SESSION_CONFIGS`

`FAST_V1.1` is a 5-leg portfolio:

| Leg | Type | Signal instrument | Execution ticker | Core profile override |
|-----|------|-------------------|------------------|-----------------------|
| `NQ_Asia` | ORB continuation | `NQ` | `MNQ` | `risk_usd=400`, `max_single_risk_usd=500` |
| `ES_NY` | ORB continuation | `ES` | `MES` | `risk_usd=400`, `max_single_risk_usd=500` |
| `ES_Asia` | ORB continuation | `ES` | `MES` | `risk_usd=400`, `max_single_risk_usd=500` |
| `NQ_Asia_LSI` | LSI reversal | `NQ` | `MNQ` | `risk_usd=400`, `max_single_risk_usd=500`, `qty_multiplier=1.0` |
| `NQ_NY_LSI` | LSI reversal | `NQ` | `MNQ` | `tp1_ratio=0.34`, `risk_usd=400`, `max_single_risk_usd=500`, `qty_multiplier=1.0` |

Notes:

- `FAST_V1.1` is `enabled: true`
- `webhooks` is empty, so this profile is dry-run unless a webhook is added later
- `max_open_contracts` is not set in `exec_configs.json`, so it loads as `0.0`
- All DOW values below use Python weekday numbering: Monday=`0` through Sunday=`6`

## Included Legs

### `NQ_Asia`

Continuation leg on NQ Asia session, executed on `MNQ`.

| Field | Value |
|-------|-------|
| ORB window | `20:00` to `20:15` |
| Entry window | `20:15` to `22:30` |
| Flat window | `04:00` to `07:00` |
| Stop basis | `orb` |
| Stop config | `stop_orb_pct=100.0` |
| Gap filter | `gap_filter_basis=orb`, `min_gap_orb_pct=10.0` |
| RR / TP1 | `rr=6.0`, `tp1_ratio=0.3` |
| ATR length | `5` |
| Direction | `long_only=True` |
| ICF | `False` |
| Excluded DOW | `1` (`Tuesday`) |
| FOMC exclusion | `False` |
| Floors | `min_stop_pts=0.0`, `min_tp1_pts=0.0` |
| Risk | `risk_usd=400`, `max_single_risk_usd=500` |

### `ES_NY`

Continuation leg on ES NY session, executed on `MES`.

| Field | Value |
|-------|-------|
| ORB window | `09:30` to `09:45` |
| Entry window | `09:45` to `13:00` |
| Flat window | `15:50` to `16:00` |
| Stop basis | `atr` |
| Stop config | `stop_atr_pct=5.0` |
| Gap filter | `gap_filter_basis=atr`, `min_gap_atr_pct=0.25` |
| RR / TP1 | `rr=5.0`, `tp1_ratio=0.2` |
| ATR length | `7` |
| Direction | `long_only=True` |
| ICF | `False` |
| Excluded DOW | `3` (`Thursday`) |
| FOMC exclusion | `False` |
| Floors | `min_stop_pts=3.0`, `min_tp1_pts=3.0` |
| Risk | `risk_usd=400`, `max_single_risk_usd=500` |

### `ES_Asia`

Continuation leg on ES Asia session, executed on `MES`.

| Field | Value |
|-------|-------|
| ORB window | `20:00` to `20:15` |
| Entry window | `20:15` to `03:00` |
| Flat window | `07:00` to `07:00` |
| Stop basis | `orb` |
| Stop config | `stop_orb_pct=125.0` |
| Gap filter | `gap_filter_basis=atr`, `min_gap_atr_pct=0.5` |
| RR / TP1 | `rr=1.5`, `tp1_ratio=0.7` |
| ATR length | `14` |
| Direction | `long_only=True` |
| ICF | `False` |
| Excluded DOW | `None` |
| FOMC exclusion | `False` |
| Floors | `min_stop_pts=3.0`, `min_tp1_pts=3.0` |
| Risk | `risk_usd=400`, `max_single_risk_usd=500` |

`flat_start == flat_end == 07:00`, which the engine treats as an immediate flat time.

### `NQ_Asia_LSI`

LSI reversal leg on NQ Asia session, executed on `MNQ`.

| Field | Value |
|-------|-------|
| Entry window | `20:40` to `23:30` |
| Flat window | `04:00` to `07:00` |
| RR / TP1 | `rr=2.0`, `tp1_ratio=0.7` |
| ATR length | `40` |
| Minimum gap | `min_gap_atr_pct=1.75` |
| Minimum stop | `min_stop_points=0.0` |
| FVG window | `fvg_window_left=15`, `fvg_window_right=2` |
| Entry mode | `close` |
| Structure params | `lsi_n_left=8`, `lsi_n_right=2` |
| Excluded DOW | `None` |
| Direction | `long_only=True` |
| Sizing | `qty_multiplier=1.0` |
| Risk | `risk_usd=400`, `max_single_risk_usd=500` |

### `NQ_NY_LSI`

LSI reversal leg on NQ NY session, executed on `MNQ`.

| Field | Value |
|-------|-------|
| Entry window | `09:35` to `15:30` |
| Flat window | `15:50` to `16:00` |
| RR / TP1 | `rr=3.0`, `tp1_ratio=0.34` |
| ATR length | `10` |
| Minimum gap | `min_gap_atr_pct=5.0` |
| Minimum stop | `min_stop_points=0.0` |
| FVG window | `fvg_window_left=20`, `fvg_window_right=5` |
| Entry mode | `fvg_limit` |
| Structure params | `lsi_n_left=8`, `lsi_n_right=60` |
| Excluded DOW | `[2, 3]` (`Wednesday`, `Thursday`) |
| Direction | `long_only=True` |
| Sizing | `qty_multiplier=1.0` |
| Risk | `risk_usd=400`, `max_single_risk_usd=500` |

## NQ_NY_LSI Comparison

This compares the live/execution `FAST_V1.1` `NQ_NY_LSI` leg to the saved research backtest `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2016-2026-174198`.

Comparison sources:

- `FAST_V1.1` execution leg: `execution/config/exec_configs.json` + `execution/src/trader/main.py`
- Research backtest: `backtesting/scripts/save_nq_ny_lsi_rr2_tp05_thu_gated_final.py`
- Published research summary: `backtesting/learnings/asset/NQ.md`
- Published FAST leg metrics: `backtesting/learnings/reports/FAST_PHASE1_ROBUST_PIPELINE_REPORT.md`

### Config Differences

| Field | `FAST_V1.1` `NQ_NY_LSI` | `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2016-2026-174198` |
|-------|-------------------------|-----------------------------------------------------|
| Strategy family | LSI reversal | LSI reversal |
| Session | NY | NY |
| Entry mode | `fvg_limit` | `fvg_limit` |
| Entry window | `09:35` to `15:30` | `09:35` to `15:30` |
| Flat window | `15:50` to `16:00` | `15:50` to `16:00` |
| Direction | Long only | Long only |
| RR | `3.0` | `2.0` |
| TP1 ratio | `0.34` | `0.5` |
| ATR length | `10` | `14` |
| Min gap ATR % | `5.0` | `5.0` |
| LSI structure | `lsi_n_left=8`, `lsi_n_right=60` | `lsi_n_left=8`, `lsi_n_right=60` |
| FVG window | `20 / 5` | `20 / 5` |
| DOW exclusion | `[2, 3]` = Wed + Thu | `(3,)` = Thu only |
| Regime gate | None in the exec config | Skip `bull_medium_vol` + `sideways_medium_vol` |
| Qty multiplier | `1.0` | Not separately scaled; standard backtest sizing |
| Risk normalization | `risk_usd=400`, `max_single_risk_usd=500` | `risk_usd=5000.0` backtest normalization |
| Magnifier | Live execution engine | `1s` bar magnifier |

### What Changed

- The research backtest is not the same leg with a different ID. It is a tuned variant of the same `NQ_NY_LSI` concept.
- The biggest structural changes are lower `rr` (`3.0 -> 2.0`), higher `tp1_ratio` (`0.34 -> 0.5`), longer `atr_length` (`10 -> 14`), Thu-only DOW exclusion instead of Wed+Thu, and the addition of a medium-vol avoidance gate.
- The core identity stays the same: NY-session LSI, `fvg_limit` entry, long-only, `min_gap_atr_pct=5.0`, `lsi_n_left=8`, `lsi_n_right=60`, and FVG window `20/5`.

### Published Performance

These are not perfectly apples-to-apples:

- `FAST_V1.1` metrics below come from the FAST phase-one robust pipeline on full pre-holdout history with a separate payout-sprint scorecard.
- `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2016-2026-174198` is a saved research backtest over `2016-01-01` to `2026-03-31` with Thu-only exclusion and regime gating.

| Metric | `FAST_V1.1` `NQ_NY_LSI` | Research backtest |
|--------|--------------------------|-------------------|
| Trades | `611` | `588` |
| Win rate | `59.2%` | `61.1%` |
| Profit factor | `1.61` | `1.70` |
| Net R | `+120.1R` | `+126.4R` |
| Sharpe | `3.217` | `3.646` |
| Max DD | `-6.6R` | `-7.6R` |

Additional published evaluation:

- `FAST_V1.1` phase-one payout scorecard: `92.7%` success rate, `+4.30R` EV/attempt, `126` average days to payout, `6` max consecutive breaches.
- Research backtest holdout simulation: `24` accounts, `15` payouts, `0` breaches, `9` open, reported as `100%` payout success rate on closed outcomes, EV `+4.36R/account`.

### Practical Read

- On published headline metrics, the RR2 / TP0.5 / Thu-only / regime-gated research variant looks stronger on per-trade quality: higher WR, PF, Net R, and Sharpe.
- `FAST_V1.1` keeps slightly shallower drawdown in the published FAST report and already scores extremely well on the portfolio payout-sprint framework.
- The cleanest interpretation is that the saved backtest is a more selective research refinement of the same `NQ_NY_LSI` edge, not a contradiction of the FAST leg.

## FAST_V1.1 NQ_NY_LSI With The Same Regime Gate

I also tested the actual `FAST_V1.1` `NQ_NY_LSI` parameters with the same regime avoidance logic used by `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2016-2026-174198`:

- Avoid buckets: `bull_medium_vol` + `sideways_medium_vol`
- Method reused from the saved RR2/TP0.5 workflow:
  1. run the raw backtest
  2. apply the regime gate to trades
  3. apply replay filters / DOW exclusions for display metrics
- FAST params held fixed:
  `rr=3.0`, `tp1_ratio=0.34`, `atr_length=10`, `min_gap_atr_pct=5.0`,
  `lsi_n_left=8`, `lsi_n_right=60`, `fvg_limit`, Wed+Thu excluded

### Full History Comparison

Window: `2016-01-01` to `2026-03-31`

| Metric | FAST_V1.1 baseline | FAST_V1.1 + same regime gate | Delta |
|--------|---------------------|-------------------------------|-------|
| Trades | `611` | `446` | `-165` (`-27.0%`) |
| Win rate | `59.25%` | `62.11%` | `+2.86%` |
| Profit factor | `1.608` | `1.844` | `+0.236` |
| Net R | `+120.07R` | `+113.94R` | `-6.13R` |
| Max DD | `-6.63R` | `-6.63R` | `0.00R` |
| Calmar | `18.10` | `17.18` | `-0.92` |
| Sharpe | `3.22` | `4.14` | `+0.93` |
| Negative years | `0` | `0` | `0` |

### Recent 5-Year Comparison

Window: `2021-01-01` to `2026-03-31`

| Metric | FAST_V1.1 baseline | FAST_V1.1 + same regime gate | Delta |
|--------|---------------------|-------------------------------|-------|
| Trades | `312` | `211` | `-101` (`-32.4%`) |
| Win rate | `60.90%` | `63.51%` | `+2.61%` |
| Profit factor | `1.704` | `1.963` | `+0.259` |
| Net R | `+65.92R` | `+55.95R` | `-9.97R` |
| Max DD | `-6.63R` | `-6.63R` | `0.00R` |
| Calmar | `9.94` | `8.43` | `-1.50` |
| Sharpe | `3.44` | `4.28` | `+0.83` |
| Negative years | `0` | `0` | `0` |

### Conclusion

- Reusing the same regime gate on the FAST_V1.1 `NQ_NY_LSI` leg improves trade quality materially: higher win rate, higher PF, and much higher Sharpe.
- It does **not** improve the FAST leg on Calmar in either full history or the recent 5-year slice.
- The reason is simple: the gate removes a lot of trades, but the drawdown does not improve enough to offset the lost Net R.
- So for the FAST_V1.1 parameterization, this gate looks like a **quality-improving but return-reducing filter**, not a clear portfolio upgrade.

## What FAST_V1.1 Does Not Include

These base execution-engine legs exist elsewhere, but they are not part of `FAST_V1.1`:

- `NQ_NY`
- `GC_NY`
- `NQ_LDN`
