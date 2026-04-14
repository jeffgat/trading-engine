# NQ NY HTF-LSI LRLR Ablation

- Scope: frozen `2m` NQ NY HTF-LSI anchor.
- Goal: isolate whether the apparent LRLR value comes from TP1-path liquidity location, from left-side structure, or from both together.
- Stitched OOS stream uses `36m IS / 12m OOS / 12m step` from `2016-01-01` to `2025-04-01`.
- Holdout window: `2025-04-01` to `2026-03-24`.

## Summary

| Candidate | Validation PF | Validation Avg R | Validation Calmar | OOS PF | OOS Avg R | OOS Calmar | OOS Trades | Holdout PF | Holdout Avg R | Holdout Calmar | Holdout Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 1.275 | 0.127 | 2.057 | 1.212 | 0.104 | 3.763 | 486 | 1.040 | 0.004 | 0.030 | 77 |
| `tp1_window_only` | 1.409 | 0.182 | 2.584 | 1.286 | 0.137 | 5.037 | 439 | 0.922 | -0.049 | -0.288 | 72 |
| `unswept_pair_only` | 1.310 | 0.149 | 2.137 | 1.184 | 0.095 | 1.749 | 305 | 0.843 | -0.090 | -0.551 | 43 |
| `full_tp1_aware_lrlr_lite` | 1.501 | 0.229 | 4.012 | 1.252 | 0.127 | 2.421 | 287 | 0.816 | -0.099 | -0.453 | 38 |

## Details

### baseline

- thesis: `ungated anchor`
- config: `long fvg_limit 08:30-15:00 cap1 rr3.0 tp10.6 left50 right5 lag0`
- pre-holdout validation: `{'total_signals': 199.0, 'total_trades': 180.0, 'no_fills': 19.0, 'win_rate': 0.4556, 'profit_factor': 1.2748, 'avg_r': 0.1273, 'total_r': 22.9179, 'calmar_ratio': 2.0568, 'max_drawdown_r': -11.1427, 'sharpe_ratio': 1.5908}`
- stitched OOS: `{'total_signals': 536.0, 'total_trades': 486.0, 'no_fills': 50.0, 'win_rate': 0.4486, 'profit_factor': 1.2121, 'avg_r': 0.1039, 'total_r': 50.4728, 'calmar_ratio': 3.7631, 'max_drawdown_r': -13.4126, 'sharpe_ratio': 1.3011}`
- holdout: `{'total_signals': 85.0, 'total_trades': 77.0, 'no_fills': 8.0, 'win_rate': 0.4026, 'profit_factor': 1.0395, 'avg_r': 0.0042, 'total_r': 0.3236, 'calmar_ratio': 0.03, 'max_drawdown_r': -10.7821, 'sharpe_ratio': 0.0546}`

### tp1_window_only

- thesis: `at least one unswept left-side pivot inside TP1 + 0.2 ATR, no cluster requirement`
- config: `long fvg_limit 08:30-15:00 cap1 rr3.0 tp10.6 left50 right5 lag0`
- pre-holdout validation: `{'total_signals': 175.0, 'total_trades': 158.0, 'no_fills': 17.0, 'win_rate': 0.4684, 'profit_factor': 1.4092, 'avg_r': 0.1822, 'total_r': 28.7922, 'calmar_ratio': 2.584, 'max_drawdown_r': -11.1427, 'sharpe_ratio': 2.2371}`
- stitched OOS: `{'total_signals': 484.0, 'total_trades': 439.0, 'no_fills': 45.0, 'win_rate': 0.4647, 'profit_factor': 1.2861, 'avg_r': 0.1373, 'total_r': 60.2819, 'calmar_ratio': 5.037, 'max_drawdown_r': -11.9679, 'sharpe_ratio': 1.7152}`
- holdout: `{'total_signals': 80.0, 'total_trades': 72.0, 'no_fills': 8.0, 'win_rate': 0.3889, 'profit_factor': 0.9222, 'avg_r': -0.049, 'total_r': -3.5255, 'calmar_ratio': -0.2882, 'max_drawdown_r': -12.2311, 'sharpe_ratio': -0.657}`

### unswept_pair_only

- thesis: `at least two unswept lower highs within 30m, no TP1 requirement and no tight channel fit`
- config: `long fvg_limit 08:30-15:00 cap1 rr3.0 tp10.6 left50 right5 lag0`
- pre-holdout validation: `{'total_signals': 127.0, 'total_trades': 112.0, 'no_fills': 15.0, 'win_rate': 0.4554, 'profit_factor': 1.3101, 'avg_r': 0.1488, 'total_r': 16.6608, 'calmar_ratio': 2.1369, 'max_drawdown_r': -7.7968, 'sharpe_ratio': 1.804}`
- stitched OOS: `{'total_signals': 338.0, 'total_trades': 305.0, 'no_fills': 33.0, 'win_rate': 0.4492, 'profit_factor': 1.1837, 'avg_r': 0.0952, 'total_r': 29.033, 'calmar_ratio': 1.7489, 'max_drawdown_r': -16.6006, 'sharpe_ratio': 1.1958}`
- holdout: `{'total_signals': 46.0, 'total_trades': 43.0, 'no_fills': 3.0, 'win_rate': 0.3953, 'profit_factor': 0.8432, 'avg_r': -0.0896, 'total_r': -3.8541, 'calmar_ratio': -0.5506, 'max_drawdown_r': -7.0, 'sharpe_ratio': -1.1566}`

### full_tp1_aware_lrlr_lite

- thesis: `two-pivot LRLR-lite plus TP1-path qualification`
- config: `long fvg_limit 08:30-15:00 cap1 rr3.0 tp10.6 left50 right5 lag0`
- pre-holdout validation: `{'total_signals': 119.0, 'total_trades': 105.0, 'no_fills': 14.0, 'win_rate': 0.4857, 'profit_factor': 1.5014, 'avg_r': 0.2292, 'total_r': 24.0673, 'calmar_ratio': 4.0118, 'max_drawdown_r': -5.9991, 'sharpe_ratio': 2.7281}`
- stitched OOS: `{'total_signals': 319.0, 'total_trades': 287.0, 'no_fills': 32.0, 'win_rate': 0.4634, 'profit_factor': 1.2517, 'avg_r': 0.1265, 'total_r': 36.3195, 'calmar_ratio': 2.4212, 'max_drawdown_r': -15.0006, 'sharpe_ratio': 1.5762}`
- holdout: `{'total_signals': 41.0, 'total_trades': 38.0, 'no_fills': 3.0, 'win_rate': 0.3947, 'profit_factor': 0.8162, 'avg_r': -0.0989, 'total_r': -3.7572, 'calmar_ratio': -0.4532, 'max_drawdown_r': -8.2903, 'sharpe_ratio': -1.2987}`
