# ALPHA_V1 Next-Step Packet (2026-05-16)

- Generated: `2026-05-16T09:17:55`
- Results packet: `backtesting/data/results/alpha_v1_next_steps_20260516`
- Repro script: `backtesting/scripts/run_alpha_v1_next_steps_20260516.py`
- Runtime: `4.0s`

## 1. Asia Sleeve Payoff Geometry

The active ES Asia leg remains the cleaner sleeve fit. ES Asia-B is strong, especially recently, but as a sleeve replacement it turns the Asia pair into two farther-target profiles. The active ES leg supplies the near-target ballast beside NQ Asia's far runner.

### Standalone Exit Geometry

| Stream | Trades | Net R | DD | WR | Full Target | EOD | SL |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NQ Asia RR6 | 726 | +137.9R | -18.9R | 45.2% | 6.1% | 25.5% | 53.3% |
| Active ES Asia RR1.5 | 1426 | +101.3R | -15.9R | 55.0% | 34.8% | 7.6% | 42.7% |
| ES Asia-B original RR3 | 911 | +69.9R | -21.4R | 47.0% | 7.0% | 44.6% | 43.5% |
| ES Asia-B constrained RR2 | 911 | +69.8R | -20.9R | 48.5% | 21.4% | 31.5% | 42.6% |

### Sleeve Daily / Risk-Weighted View

Risk-weighted rows use the current aggressive Asia risks: NQ Asia `$400`, ES Asia / ES Asia-B `$150`.

| Sleeve | Net R | DD R | Sharpe | Worst Month R | Weighted Net | Weighted DD |
| --- | --- | --- | --- | --- | --- | --- |
| NQ Asia + active ES Asia | +239.2R | -28.7R | 0.99 | -10.9R | $70,355 | $-8,231 |
| NQ Asia + ES Asia-B original | +207.8R | -28.6R | 0.85 | -10.9R | $65,639 | $-8,194 |
| NQ Asia + ES Asia-B constrained | +207.6R | -28.5R | 0.87 | -10.7R | $65,620 | $-8,198 |

### Asia Pair Interaction

| Variant | Corr | Both Active | Both Losing | Offset Days | Worst Overlap R |
| --- | --- | --- | --- | --- | --- |
| nq_plus_active_es | 0.25 | 465 | 172 | 127 | -4.4R |
| nq_plus_es_b_original | 0.39 | 400 | 149 | 80 | -4.4R |
| nq_plus_es_b_constrained | 0.35 | 386 | 145 | 85 | -4.4R |

### Asia-Only Phase-One Proxy

| Sleeve | Year | Accounts | Payout | Breach | Avg PayD | MCBch | EV/Start |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NQ Asia + active ES Asia | 2024 | 27 | 52.4% | 47.6% | 52.6 | 10 | $54 |
| NQ Asia + active ES Asia | 2025 | 27 | 80.0% | 20.0% | 42.4 | 3 | $220 |
| NQ Asia + ES Asia-B original | 2024 | 27 | 57.1% | 42.9% | 43.2 | 9 | $72 |
| NQ Asia + ES Asia-B original | 2025 | 27 | 92.0% | 8.0% | 42.0 | 2 | $276 |
| NQ Asia + ES Asia-B constrained | 2024 | 27 | 57.1% | 42.9% | 37.8 | 9 | $72 |
| NQ Asia + ES Asia-B constrained | 2025 | 27 | 92.0% | 8.0% | 40.6 | 2 | $276 |

## 2. NQ R11 15m Structure + VWAP Gate

Deployability: `post_filter_only_entry_minus_5m_proxy`. The signals are live-native concepts, but this exact-trade CSV does not carry the original signal bar, so the test uses the previous completed 5m bar before exact entry. A true promotion still needs engine-level replay at signal time.

| Gate | Window | Trades | Keep | Net R | Delta | PF | DD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | full | 554 | 100.0% | +110.8R | +0.0R | 1.39 | -7.4R |
| baseline | 2025_plus | 60 | 100.0% | +9.4R | +0.0R | 1.30 | -6.1R |
| baseline | last_1y | 49 | 100.0% | +3.5R | +0.0R | 1.13 | -6.1R |
| any2of3_vwap_d10 | full | 480 | 86.6% | +110.8R | -0.0R | 1.46 | -7.0R |
| any2of3_vwap_d10 | 2025_plus | 47 | 78.3% | +10.7R | +1.3R | 1.45 | -5.1R |
| any2of3_vwap_d10 | last_1y | 38 | 77.5% | +7.9R | +4.4R | 1.41 | -5.1R |
| vwap_d15_only | full | 460 | 83.0% | +109.8R | -1.0R | 1.48 | -7.4R |
| vwap_d15_only | 2025_plus | 42 | 70.0% | +7.2R | -2.2R | 1.34 | -5.2R |
| vwap_d15_only | last_1y | 34 | 69.4% | +3.4R | -0.1R | 1.19 | -5.2R |
| vwap_side_only | full | 553 | 99.8% | +109.5R | -1.3R | 1.39 | -7.4R |
| vwap_side_only | 2025_plus | 60 | 100.0% | +9.4R | +0.0R | 1.30 | -6.1R |
| vwap_side_only | last_1y | 49 | 100.0% | +3.5R | +0.0R | 1.13 | -6.1R |
| vwap_d10_only | full | 525 | 94.8% | +108.8R | -2.0R | 1.41 | -7.3R |
| vwap_d10_only | 2025_plus | 53 | 88.3% | +8.0R | -1.4R | 1.28 | -6.1R |
| vwap_d10_only | last_1y | 44 | 89.8% | +5.2R | +1.7R | 1.21 | -6.1R |
| vwap_d05_only | full | 551 | 99.5% | +108.2R | -2.6R | 1.39 | -7.4R |
| vwap_d05_only | 2025_plus | 59 | 98.3% | +10.4R | +1.0R | 1.34 | -6.1R |
| vwap_d05_only | last_1y | 48 | 98.0% | +4.5R | +1.0R | 1.17 | -6.1R |
| any2of3_vwap | full | 500 | 90.2% | +108.0R | -2.8R | 1.43 | -8.0R |
| any2of3_vwap | 2025_plus | 51 | 85.0% | +10.0R | +0.6R | 1.39 | -5.1R |
| any2of3_vwap | last_1y | 41 | 83.7% | +6.5R | +3.0R | 1.30 | -5.1R |

## 3. Hunter 0.25x Sidecar on Fee-Aware ALPHA_V1

Rows below focus on the selected `aggressive_sprint` ALPHA_V1 fee-aware profile. Hunter 0.25x uses the prior downstream convention: Hunter trade R times `$350 * 0.25`.

### Account Outcomes

| Scenario | Year | Accounts | Payout | Breach | Avg PayD | MCBch | EV/Start |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ALPHA_V1 fee-aware baseline | 2024 | 27 | 82.6% | 17.4% | 40.6 | 2 | $202 |
| ALPHA_V1 fee-aware baseline | 2025 | 27 | 73.1% | 26.9% | 20.5 | 7 | $202 |
| + Hunter 0.25x 10y-Safe Branch | 2024 | 27 | 88.5% | 11.5% | 32.8 | 1 | $276 |
| + Hunter 0.25x 10y-Safe Branch | 2025 | 27 | 84.6% | 15.4% | 18.9 | 4 | $257 |
| + Hunter 0.25x Neutral Reference | 2024 | 27 | 76.9% | 23.1% | 36.7 | 2 | $220 |
| + Hunter 0.25x Neutral Reference | 2025 | 27 | 84.6% | 15.4% | 20.0 | 4 | $257 |
| + Hunter 0.25x Recent-Strength Branch | 2024 | 27 | 73.1% | 26.9% | 33.2 | 3 | $202 |
| + Hunter 0.25x Recent-Strength Branch | 2025 | 27 | 84.6% | 15.4% | 19.5 | 4 | $257 |

### Portfolio Fit

| Scenario | Net | Delta Net | DD | Worst Month | Corr |
| --- | --- | --- | --- | --- | --- |
| ALPHA_V1 fee-aware baseline | $53,825 | $0 | $-4,037 | $-2,469 | 0.00 |
| + Hunter 0.25x 10y-Safe Branch | $74,479 | $20,654 | $-4,098 | $-3,568 | 0.03 |
| + Hunter 0.25x Neutral Reference | $68,237 | $14,412 | $-3,900 | $-3,370 | 0.03 |
| + Hunter 0.25x Recent-Strength Branch | $69,400 | $15,575 | $-4,098 | $-3,568 | 0.03 |

### Hunter Overlap

| Candidate | Corr | Both Active | Both Losing | Offset Days | Worst Overlap |
| --- | --- | --- | --- | --- | --- |
| 10y-Safe Branch | 0.03 | 353 | 86 | 170 | $-1,261 |
| Neutral Reference | 0.03 | 241 | 55 | 119 | $-1,261 |
| Recent-Strength Branch | 0.03 | 290 | 65 | 147 | $-1,261 |

## Read

- Priority 1 does not justify replacing active ES Asia. Keep the current near-target ES Asia + far-runner NQ Asia sleeve logic.
- Priority 2 is only promotable if a gate improves recent R11 quality without gutting trade count; use the table above to decide whether it deserves a true engine replay.
- Priority 3 is a portfolio sidecar test, not a replacement test. If Hunter improves payout clustering without worsening breach clusters, it deserves a paper pilot as `research_only` until live execution parity is explicit.
