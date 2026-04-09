# ORB Indicator Confluence Initial Results

## Scope

- Frozen anchors tested: 9
- Discovery: 2016-01-01 to 2022-12-31
- Validation: 2023-01-01 to 2024-12-31
- Holdout untouched: 2025-01-01+
- Method: post-trade overlay filter on filled trades using prior-bar indicator states.
- Important: these results are heuristic and are not yet full engine-level reruns.

## Combined Base Book

- Discovery: 6689 trades | avgR=0.135 | PF=1.27 | totalR=904.9
- Validation: 1909 trades | avgR=0.123 | PF=1.24 | totalR=234.8

## Validation Leaders

- `sma20__aligned_near`: val avgR delta +0.038, retention 80.3%, val trades 1532, positive anchors 8/9
- `vwap_ema20__aligned_near`: val avgR delta +0.026, retention 73.2%, val trades 1398, positive anchors 7/9
- `ema20__aligned_near`: val avgR delta +0.022, retention 82.5%, val trades 1575, positive anchors 7/9
- `sma50__aligned_near`: val avgR delta +0.016, retention 71.3%, val trades 1362, positive anchors 6/9
- `ema50__aligned_near`: val avgR delta +0.013, retention 74.0%, val trades 1412, positive anchors 5/9
- `ema20_ema50__aligned_near`: val avgR delta +0.013, retention 67.6%, val trades 1291, positive anchors 5/9
- `vwap_ema20_ema50__aligned_near`: val avgR delta +0.009, retention 64.5%, val trades 1231, positive anchors 7/9
- `vwap__aligned_near`: val avgR delta +0.007, retention 80.3%, val trades 1532, positive anchors 6/9
- `vwap_ema50__aligned_near`: val avgR delta +0.002, retention 68.6%, val trades 1310, positive anchors 6/9

## Best Rule Per Anchor

- `alpha_es_asia_orb_long`: `vwap_ema20__reversion_near` | val avgR delta +0.183 | retention 7.1% | val trades 21
- `alpha_es_ny_orb_long`: `ema50__aligned_far` | val avgR delta +0.311 | retention 29.6% | val trades 53
- `alpha_nq_asia_orb_long`: `vwap_ema20__aligned_near` | val avgR delta +0.054 | retention 88.2% | val trades 127
- `cl_ldn2`: `sma50__reversion_near` | val avgR delta +0.566 | retention 5.7% | val trades 13
- `es_nya_gated`: `ema20_ema50__aligned_near` | val avgR delta +0.126 | retention 48.3% | val trades 42
- `gc_asia1_ungated`: `vwap__reversion_near` | val avgR delta +0.526 | retention 11.1% | val trades 36
- `nq_asiab_gated`: `ema50__reversion_near` | val avgR delta +0.153 | retention 13.6% | val trades 12
- `rty_ny1`: `sma50__aligned_near` | val avgR delta +0.106 | retention 44.1% | val trades 156
- `si_asia1`: `vwap_ema20_ema50__aligned_near` | val avgR delta +0.098 | retention 74.8% | val trades 157

## Notes

- Positive results here are promotion candidates for a second pass only.
- Second pass should rerun a very small frozen shortlist as true engine-level entry filters,
  then walk-forward again before touching the final holdout.

