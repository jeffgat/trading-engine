# NQ NY Reference LSI Discovery Spec

## Thesis

Test a first-pass `reference_lsi` branch on `NQ` during the NY session, using sweeps of:

- `previous_day_high`
- `previous_day_low`
- `asia_high`
- `asia_low`
- `london_high`
- `london_low`

Entry logic:

- sweep must occur during the active session window
- FVG must exist before the sweep
- inversion must occur after the sweep
- entry is a limit at either the inversion-side gap edge (`near`) or the opposite gap edge (`far`)

Risk logic:

- raw stop = sweep extreme through inversion bar
- hard stop floor = `5%` of daily ATR
- hard stop ceiling = `risk_usd / point_value` (1-contract max risk)

## Session / Instrument

- instrument: `NQ`
- session: `NY`
- `rth_start = 08:30`
- `entry_start = 08:30`
- `entry_end` is swept
- `flat_start = 14:00`
- `flat_end = 14:05`
- holdout frozen at `2025-01-01+`

## Baseline

- `direction_filter = both`
- `rr = 2.0`
- `tp1_ratio = 0.5`
- `atr_length = 10`
- `min_gap_atr_pct = 5.0`
- `ref_lsi_gap_lookback_bars = 12`
- `ref_lsi_inversion_max_bars = 18`
- `ref_lsi_gap_entry_edge = near`
- `risk_usd = 5000`
- `min_qty = 1`
- `qty_step = 1`

## Stage A

Structural sweep only, with reward fixed at baseline:

- `direction_filter`: `long`, `short`, `both`
- `entry_end`: `11:00`, `12:00`, `13:00`, `14:00`
- `ref_lsi_gap_entry_edge`: `near`, `far`
- `ref_lsi_gap_lookback_bars`: `3`, `6`, `9`, `12`
- `ref_lsi_inversion_max_bars`: `6`, `12`, `18`

Advance only if baseline is structurally alive:

- pre-holdout `profit_factor >= 1.05`
- pre-holdout `avg_r > 0`
- pre-holdout `total_trades >= 150`
- 2023-2024 validation `profit_factor >= 1.00`

## Stage B

Reward sweep only on Stage A survivors:

- `rr`: `1.5`, `1.75`, `2.0`, `2.25`, `2.5`, `3.0`
- `tp1_ratio`: `0.5`, `0.6`, `0.7`, `0.8`
- keep only pairs where `rr * tp1_ratio >= 1.0`

## Promotion

- discovery: `2016-01-01` to `2022-12-31`
- validation: `2023-01-01` to `2024-12-31`
- holdout: `2025-01-01+`
- walk-forward: `36m IS / 12m OOS / 12m step`
- promote only `2-3` configs
- run `PSR` and `DSR` on promoted configs only

## Outputs

Primary script:

- [run_nq_ny_reference_lsi_discovery.py](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/scripts/run_nq_ny_reference_lsi_discovery.py)

Primary report output:

- [NQ_NY_REFERENCE_LSI_DISCOVERY.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/NQ_NY_REFERENCE_LSI_DISCOVERY.md)
