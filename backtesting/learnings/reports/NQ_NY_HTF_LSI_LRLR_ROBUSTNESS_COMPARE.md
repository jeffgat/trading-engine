# NQ NY HTF-LSI LRLR Robustness Compare

- Scope: frozen `2m` NQ NY HTF-LSI anchor versus the two LRLR follow-up finalists.
- Selection discipline: LRLR variants were frozen from pre-holdout work before this one-time holdout compare.
- Stitched OOS stream uses `36m IS / 12m OOS / 12m step` from `2016-01-01` to `2025-04-01`.
- Holdout window: `2025-04-01` to `2026-03-24`.

## Summary

| Candidate | Validation PF | Validation Avg R | Validation Calmar | OOS PF | OOS Avg R | OOS Calmar | OOS Trades | Holdout PF | Holdout Avg R | Holdout Calmar | Holdout Trades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline` | 1.275 | 0.127 | 2.057 | 1.212 | 0.104 | 3.763 | 486 | 1.040 | 0.004 | 0.030 | 77 |
| `lrlr_lite_30m` | 1.375 | 0.180 | 2.561 | 1.209 | 0.108 | 1.993 | 299 | 0.752 | -0.144 | -0.660 | 40 |
| `lrlr_tp1_30m_buffer_0.2` | 1.501 | 0.229 | 4.012 | 1.252 | 0.127 | 2.421 | 287 | 0.816 | -0.099 | -0.453 | 38 |

## Details

### baseline

- thesis: `ungated anchor`
- config: `long fvg_limit 08:30-15:00 cap1 rr3.0 tp10.6 left50 right5 lag0`
- pre-holdout validation: `{'total_signals': 199.0, 'total_trades': 180.0, 'no_fills': 19.0, 'win_rate': 0.4556, 'profit_factor': 1.2748, 'avg_r': 0.1273, 'total_r': 22.9179, 'calmar_ratio': 2.0568, 'max_drawdown_r': -11.1427, 'sharpe_ratio': 1.5908}`
- stitched OOS: `{'total_signals': 536.0, 'total_trades': 486.0, 'no_fills': 50.0, 'win_rate': 0.4486, 'profit_factor': 1.2121, 'avg_r': 0.1039, 'total_r': 50.4728, 'calmar_ratio': 3.7631, 'max_drawdown_r': -13.4126, 'sharpe_ratio': 1.3011}`
- holdout: `{'total_signals': 85.0, 'total_trades': 77.0, 'no_fills': 8.0, 'win_rate': 0.4026, 'profit_factor': 1.0395, 'avg_r': 0.0042, 'total_r': 0.3236, 'calmar_ratio': 0.03, 'max_drawdown_r': -10.7821, 'sharpe_ratio': 0.0546}`
- holdout `2025-04-01` to `2025-12-31`: `{'total_signals': 63.0, 'total_trades': 57.0, 'no_fills': 6.0, 'win_rate': 0.4035, 'profit_factor': 1.0973, 'avg_r': 0.038, 'total_r': 2.1677, 'calmar_ratio': 0.2277, 'max_drawdown_r': -9.5199, 'sharpe_ratio': 0.4765}`
- holdout `2026-01-01` to `2026-03-24`: `{'total_signals': 22.0, 'total_trades': 20.0, 'no_fills': 2.0, 'win_rate': 0.4, 'profit_factor': 0.8467, 'avg_r': -0.0922, 'total_r': -1.8441, 'calmar_ratio': -0.3688, 'max_drawdown_r': -5.0, 'sharpe_ratio': -1.3217}`

### lrlr_lite_30m

- thesis: `2 pivots + 30m spacing`
- config: `long fvg_limit 08:30-15:00 cap1 rr3.0 tp10.6 left50 right5 lag0`
- pre-holdout validation: `{'total_signals': 125.0, 'total_trades': 111.0, 'no_fills': 14.0, 'win_rate': 0.4685, 'profit_factor': 1.3745, 'avg_r': 0.1799, 'total_r': 19.9673, 'calmar_ratio': 2.561, 'max_drawdown_r': -7.7968, 'sharpe_ratio': 2.1572}`
- stitched OOS: `{'total_signals': 331.0, 'total_trades': 299.0, 'no_fills': 32.0, 'win_rate': 0.4548, 'profit_factor': 1.2087, 'avg_r': 0.1082, 'total_r': 32.3614, 'calmar_ratio': 1.993, 'max_drawdown_r': -16.2377, 'sharpe_ratio': 1.3478}`
- holdout: `{'total_signals': 43.0, 'total_trades': 40.0, 'no_fills': 3.0, 'win_rate': 0.375, 'profit_factor': 0.7525, 'avg_r': -0.1439, 'total_r': -5.7572, 'calmar_ratio': -0.6605, 'max_drawdown_r': -8.717, 'sharpe_ratio': -1.9138}`
- holdout `2025-04-01` to `2025-12-31`: `{'total_signals': 27.0, 'total_trades': 26.0, 'no_fills': 1.0, 'win_rate': 0.3462, 'profit_factor': 0.6887, 'avg_r': -0.1667, 'total_r': -4.3354, 'calmar_ratio': -0.5229, 'max_drawdown_r': -8.2903, 'sharpe_ratio': -2.1981}`
- holdout `2026-01-01` to `2026-03-24`: `{'total_signals': 16.0, 'total_trades': 14.0, 'no_fills': 2.0, 'win_rate': 0.4286, 'profit_factor': 0.9058, 'avg_r': -0.1016, 'total_r': -1.4218, 'calmar_ratio': -0.3555, 'max_drawdown_r': -4.0, 'sharpe_ratio': -1.3233}`

### lrlr_tp1_30m_buffer_0.2

- thesis: `2 pivots + 30m spacing + nearest LRLR level within 0.2 ATR beyond TP1`
- config: `long fvg_limit 08:30-15:00 cap1 rr3.0 tp10.6 left50 right5 lag0`
- pre-holdout validation: `{'total_signals': 119.0, 'total_trades': 105.0, 'no_fills': 14.0, 'win_rate': 0.4857, 'profit_factor': 1.5014, 'avg_r': 0.2292, 'total_r': 24.0673, 'calmar_ratio': 4.0118, 'max_drawdown_r': -5.9991, 'sharpe_ratio': 2.7281}`
- stitched OOS: `{'total_signals': 319.0, 'total_trades': 287.0, 'no_fills': 32.0, 'win_rate': 0.4634, 'profit_factor': 1.2517, 'avg_r': 0.1265, 'total_r': 36.3195, 'calmar_ratio': 2.4212, 'max_drawdown_r': -15.0006, 'sharpe_ratio': 1.5762}`
- holdout: `{'total_signals': 41.0, 'total_trades': 38.0, 'no_fills': 3.0, 'win_rate': 0.3947, 'profit_factor': 0.8162, 'avg_r': -0.0989, 'total_r': -3.7572, 'calmar_ratio': -0.4532, 'max_drawdown_r': -8.2903, 'sharpe_ratio': -1.2987}`
- holdout `2025-04-01` to `2025-12-31`: `{'total_signals': 27.0, 'total_trades': 26.0, 'no_fills': 1.0, 'win_rate': 0.3462, 'profit_factor': 0.6887, 'avg_r': -0.1667, 'total_r': -4.3354, 'calmar_ratio': -0.5229, 'max_drawdown_r': -8.2903, 'sharpe_ratio': -2.1981}`
- holdout `2026-01-01` to `2026-03-24`: `{'total_signals': 14.0, 'total_trades': 12.0, 'no_fills': 2.0, 'win_rate': 0.5, 'profit_factor': 1.234, 'avg_r': 0.0482, 'total_r': 0.5782, 'calmar_ratio': 0.2891, 'max_drawdown_r': -2.0, 'sharpe_ratio': 0.6079}`
