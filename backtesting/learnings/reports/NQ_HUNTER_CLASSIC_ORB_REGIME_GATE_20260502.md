# NQ Hunter Classic ORB Regime Gate Test (2026-05-02)

## Scope

This read tested whether the discretionary Hunter Classic ORB forward-test strength can be explained or improved by causal regime gates.

Evidence:

- Results directory: `backtesting/data/results/hunter_classic_regime_gate_test_20260502/`
- Canonical trades: `backtesting/data/results/hunter_classic_orb_replication_10y_ema15c14_20260426/trades.csv`
- Distance-capped trades: `backtesting/data/results/hunter_classic_orb_replication_10y_ema15c14_dist100_20260502/sim_trades.csv`
- Regime calendar rebuilt from `backtesting/data/raw/NQ_1s.parquet` through `2026-04-24`

The regime labels are point-in-time: 5-day return, close vs SMA20, and 21-day realized volatility are shifted one full session before being applied to trades. Volatility buckets use pre-`2024-03-01` thresholds.

## Key Results

### Canonical Hunter EMA15C14, No Distance Cap

| Gate | Window | Trades | Net | WR | PF | Closed DD |
|---|---:|---:|---:|---:|---:|---:|
| None | Last 10y | 1,506 | +46.9R | 40.2% | 1.03 | -161.9R |
| None | Last 2y | 325 | +159.4R | 49.5% | 1.32 | -44.8R |
| None | Last 1y | 154 | +130.3R | 55.8% | 1.61 | -26.8R |
| Skip all high-vol | Last 10y | 1,004 | +138.2R | 40.6% | 1.14 | -49.9R |
| Skip all high-vol | Last 2y | 239 | +129.7R | 50.2% | 1.39 | -32.5R |
| Skip all high-vol | Last 1y | 104 | +87.6R | 55.8% | 1.66 | -14.2R |
| Skip bull high, bear high, bear medium | Last 10y | 1,004 | +150.9R | 41.0% | 1.16 | -41.8R |
| Skip bull high, bear high, bear medium | Last 2y | 221 | +133.8R | 51.6% | 1.46 | -21.7R |
| Skip bull high, bear high, bear medium | Last 1y | 101 | +92.8R | 57.4% | 1.76 | -14.2R |
| Only historically positive combined buckets | Last 10y | 866 | +148.7R | 40.9% | 1.19 | -43.9R |
| Only historically positive combined buckets | Last 2y | 198 | +136.6R | 52.0% | 1.56 | -21.7R |
| Only historically positive combined buckets | Last 1y | 87 | +83.3R | 57.5% | 1.85 | -14.2R |

### EMA15 Distance Cap 100

| Gate | Window | Trades | Net | WR | PF | Closed DD |
|---|---:|---:|---:|---:|---:|---:|
| None | Last 10y | 1,356 | -0.0R | 39.3% | 1.00 | -122.6R |
| None | Last 2y | 233 | +81.9R | 47.2% | 1.26 | -45.2R |
| None | Last 1y | 105 | +90.5R | 55.2% | 1.71 | -14.2R |
| Skip bull high, bear high, bear medium | Last 10y | 935 | +110.0R | 40.2% | 1.13 | -42.2R |
| Skip bull high, bear high, bear medium | Last 2y | 174 | +110.7R | 51.1% | 1.54 | -15.4R |
| Skip bull high, bear high, bear medium | Last 1y | 77 | +77.1R | 58.4% | 1.90 | -14.2R |
| Only historically positive combined buckets | Last 10y | 817 | +116.3R | 40.3% | 1.17 | -44.2R |
| Only historically positive combined buckets | Last 2y | 158 | +107.6R | 51.3% | 1.61 | -15.4R |
| Only historically positive combined buckets | Last 1y | 68 | +72.1R | 58.8% | 2.03 | -14.2R |

## Regime Attribution

The no-cap Hunter profile is not simply a one-regime strategy. The last year was broadly strong across most buckets. The long-term damage is concentrated in specific stress buckets:

- `bear_high_vol`: last 10y `-54.8R`
- `bull_high_vol`: last 10y `-38.8R`
- `bear_medium_vol`: last 10y `-10.4R`

The strongest long-term contributors were:

- `bull_medium_vol`: `+46.0R`
- `sideways_low_vol`: `+43.4R`
- `sideways_medium_vol`: `+32.2R`
- `bear_low_vol`: `+16.0R`
- `bull_low_vol`: `+11.0R`

## Read

The cleanest operating hypothesis is not "only trade the last-year regime." The better explanation is that Hunter Classic has a real recent hot streak, but the 10-year curve is wrecked by high-volatility and bear-stress environments. A simple causal gate that skips bull high-vol, bear high-vol, and bear medium-vol preserves much of the recent edge while turning the 10-year profile from fragile to plausible:

- 10y: `+46.9R / -161.9R DD` ungated -> `+150.9R / -41.8R DD` gated
- 2y: `+159.4R / -44.8R DD` ungated -> `+133.8R / -21.7R DD` gated
- 1y: `+130.3R / -26.8R DD` ungated -> `+92.8R / -14.2R DD` gated

The side-specific gate `skip_bear_high_and_shorts_in_bull_bear` scored best in the recent-weighted ranking, but it is more flexible and therefore more likely to be overfit. Treat it as a research lead, not an operating gate.

## Conclusion

Status: CONDITIONAL research lead.

Recommended next test: validate the no-cap Hunter EMA15C14 with the simple stress gate `skip bull_high_vol, bear_high_vol, bear_medium_vol` through the full regime-specialist workflow, then compare it as a reduced-risk companion leg against the current ALPHA_V1 portfolio. The distance cap is useful for drawdown control, but on this read it gives up too much recent and 2-year edge to be the first candidate.
