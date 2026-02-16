# CLI Reference

All scripts in `python/scripts/`. Run with `uv run python scripts/<script>.py`.

## run_backtest.py

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--data` | str | **required** | Data file in `data/raw/` or full path |
| `--start` | str | None | Start date (YYYY-MM-DD) |
| `--end` | str | None | End date (YYYY-MM-DD) |
| `--instrument` | str | NQ | NQ, ES, YM, MNQ |
| `--sessions` | str | NY | Comma-separated: NY,Asia,LDN |
| `--name` | str | None | Run label |
| `--notes` | str | None | Free-text notes |
| `--strategy` | str | None | `continuation` or `reversal` |
| `--no-trades` | flag | | Exclude trade list |
| `--quiet` | flag | | Minimal output |
| `--plot` | flag | | Show equity curve + monthly returns |

### Strategy Parameters (all optional, None = use defaults)

| Argument | Type | Default |
|----------|------|---------|
| `--rr` | float | 2.5 |
| `--tp1-ratio` | float | 0.5 |
| `--risk-usd` | float | 5000 |
| `--atr-length` | int | 14 |
| `--be-offset-ticks` | int | 4 |

### Session-Specific Parameters

Prefix with session name. Defaults vary by session.

| Argument | NY | Asia | LDN |
|----------|-----|------|-----|
| `--{sess}-stop-atr-pct` | 7.5 | 5.25 | 10.0 |
| `--{sess}-min-gap-atr-pct` | 2.25 | 0.9 | 1.0 |
| `--{sess}-max-gap-points` | 100 | 50 | 50 |

Where `{sess}` = `ny`, `asia`, `ldn`.

## run_optimize.py (Grid Sweep)

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--data` | str | **required** | Data file |
| `--start` | str | None | Start date |
| `--end` | str | None | End date |
| `--instrument` | str | NQ | Instrument symbol |
| `--sessions` | str | NY | Sessions |
| `--sweep` | str | **required** (1+) | `name=start:stop:step` or `name=v1,v2,v3` |
| `--workers` | int | None | Parallel workers |
| `--name` | str | None | Run label |
| `--strategy` | str | None | continuation/reversal |

Sweep param names use underscores: `ny_stop_atr_pct`, `asia_min_gap_atr_pct`, `rr`, `tp1_ratio`, `be_offset_ticks`.

## run_bayesian.py

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--data` | str | **required** | Data file |
| `--start` | str | None | Start date |
| `--end` | str | None | End date |
| `--instrument` | str | NQ | Instrument symbol |
| `--sessions` | str | NY | Sessions |
| `--param` | str | **required** (1+) | `name=low:high` or `name=low:high:step` |
| `--n-trials` | int | 100 | Bayesian trials |
| `--objective` | str | sharpe | sharpe, pnl, profit_factor, calmar, avg_r |
| `--sampler` | str | tpe | `tpe` or `gp` |
| `--seed` | int | None | Random seed |
| `--name` | str | None | Run label |
| `--strategy` | str | None | continuation/reversal |

## run_walkforward.py

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--data` | str | **required** | Data file |
| `--start` | str | None | Start date |
| `--end` | str | None | End date |
| `--instrument` | str | NQ | Instrument symbol |
| `--sessions` | str | NY | Sessions |
| `--sweep` | str | **required** (1+) | Same format as grid sweep |
| `--workers` | int | None | Parallel workers |
| `--name` | str | None | Run label |
| `--is-months` | int | 12 | In-sample window (months) |
| `--oos-months` | int | 3 | Out-of-sample window (months) |
| `--step-months` | int | 3 | Roll-forward step (months) |
| `--anchored` | flag | | Expanding IS window (start fixed) |
| `--objective` | str | sharpe | Optimization objective |
| `--strategy` | str | None | continuation/reversal |

## run_monte_carlo.py

### Trade Resampling Mode (default)

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--data` | str | conditional | Data file (if no --result) |
| `--result` | str | conditional | Saved backtest ID (if no --data) |
| `--start` | str | None | Start date |
| `--end` | str | None | End date |
| `--instrument` | str | NQ | Instrument symbol |
| `--sessions` | str | NY | Sessions |
| `--method` | str | bootstrap | `bootstrap` or `shuffle` |
| `--sims` | int | 1000 | Number of simulations |
| `--seed` | int | None | Random seed |
| `--ruin-threshold` | float | -8.0 | Drawdown threshold (R-multiples) |
| `--quiet` | flag | | Minimal output |

### Parameter-Space LHS Mode

Add `--param-sample` flag + `--param` specs:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--param-sample` | flag | | Enable LHS mode |
| `--param` | str | **required** | `name=low:high:step` |
| `--sims` | int | 1000 | Number of LHS samples |
| `--workers` | int | None | Parallel workers |
