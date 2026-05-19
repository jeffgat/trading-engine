# ALPHA_V1 ES NY Runner-Trail Sweep

- Scope: active `ALPHA_V1` ES NY ORB leg, `rr=5.0`, `tp1_ratio=0.2`, long only.
- Date window: `2016-04-17` through `2026-03-25` exclusive.
- Magnifier: `5m -> 1m` -> 1s.
- Runtime: `55.1s`.
- Deployability: every trailing row is `research_only` until the execution engine supports the same runner stop policy and exact replay is rerun.

## Baseline

Baseline printed `846` trades, `+126.58R`, `-10.86R` max DD, Calmar `11.652`, last-2Y `+21.40R`, and 2025+ `+19.49R`.

## Verdict

Runner trailing confirms the recent discomfort but does not beat the current split ladder as an all-weather replacement. `risk_gap_0p75r` is the best recent challenger, improving last-2Y and 2025+ R/DD, but it gives up too much full-history R/PF. `atr_gap_5pct` is the smoothest DD candidate, but also leaves substantial full-history R on the table. Step locks are worse than the baseline on full-history quality. Treat all trailing rows as research-only until exact execution support exists and the candidate is rerun through the live/exact engine.

## Top Full-History Rows

| Variant | Mode | Trades | Net R | Max DD R | Calmar | PF | Last 2Y R | Last 2Y Calmar | 2025+ R | 2025+ DD R | Positive Runner Stops | Deployability |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `baseline` | none | 846 | +126.58 | -10.86 | 11.652 | 1.386 | +21.40 | 2.197 | +19.49 | -9.61 | 0 | live_native |
| `atr_gap_5pct` | atr | 846 | +99.23 | -8.93 | 11.108 | 1.302 | +18.99 | 2.355 | +19.55 | -7.85 | 500 | research_only |
| `risk_gap_0p75r` | risk | 846 | +104.76 | -10.29 | 10.178 | 1.319 | +25.03 | 3.279 | +24.99 | -7.59 | 500 | research_only |
| `atr_gap_25pct` | atr | 846 | +114.15 | -12.49 | 9.139 | 1.347 | +19.77 | 2.030 | +19.49 | -9.61 | 57 | research_only |
| `atr_gap_30pct` | atr | 846 | +116.78 | -12.84 | 9.095 | 1.356 | +19.42 | 1.994 | +19.49 | -9.61 | 37 | research_only |
| `atr_gap_20pct` | atr | 846 | +109.68 | -12.13 | 9.039 | 1.334 | +18.15 | 1.864 | +19.66 | -9.61 | 98 | research_only |
| `risk_gap_2p5r` | risk | 846 | +103.69 | -11.98 | 8.653 | 1.316 | +14.65 | 1.524 | +17.17 | -9.61 | 56 | research_only |
| `step_4r_lock_2r` | step_r | 846 | +105.50 | -12.93 | 8.157 | 1.321 | +18.71 | 1.929 | +19.90 | -9.61 | 30 | research_only |

## Top Recent Rows

| Variant | Mode | Trades | Net R | Max DD R | Calmar | PF | Last 2Y R | Last 2Y Calmar | 2025+ R | 2025+ DD R | Positive Runner Stops | Deployability |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `risk_gap_0p75r` | risk | 846 | +104.76 | -10.29 | 10.178 | 1.319 | +25.03 | 3.279 | +24.99 | -7.59 | 500 | research_only |
| `atr_gap_5pct` | atr | 846 | +99.23 | -8.93 | 11.108 | 1.302 | +18.99 | 2.355 | +19.55 | -7.85 | 500 | research_only |
| `baseline` | none | 846 | +126.58 | -10.86 | 11.652 | 1.386 | +21.40 | 2.197 | +19.49 | -9.61 | 0 | live_native |
| `atr_gap_25pct` | atr | 846 | +114.15 | -12.49 | 9.139 | 1.347 | +19.77 | 2.030 | +19.49 | -9.61 | 57 | research_only |
| `atr_gap_30pct` | atr | 846 | +116.78 | -12.84 | 9.095 | 1.356 | +19.42 | 1.994 | +19.49 | -9.61 | 37 | research_only |
| `step_4r_lock_2r` | step_r | 846 | +105.50 | -12.93 | 8.157 | 1.321 | +18.71 | 1.929 | +19.90 | -9.61 | 30 | research_only |
| `atr_gap_20pct` | atr | 846 | +109.68 | -12.13 | 9.039 | 1.334 | +18.15 | 1.864 | +19.66 | -9.61 | 98 | research_only |
| `atr_gap_15pct` | atr | 846 | +77.78 | -13.48 | 5.771 | 1.235 | +17.82 | 1.855 | +19.25 | -9.61 | 168 | research_only |

## Files

- Summary CSV: `backtesting/data/results/alpha_v1_es_ny_runner_trail_sweep_20260511/summary.csv`
- Summary JSON: `backtesting/data/results/alpha_v1_es_ny_runner_trail_sweep_20260511/summary.json`
