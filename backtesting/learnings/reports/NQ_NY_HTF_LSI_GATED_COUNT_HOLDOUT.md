# NQ NY HTF-LSI Gated Count Holdout

- One-time holdout comparison window: `2025-04-01` to `2026-03-24`.
- Candidates were frozen before opening holdout: current ungated `lag24` operating lead plus the two `gap2.5 lag0 + skip bear_high_vol` gated count challengers.

## Summary

| Candidate | Holdout Trades | PF | Avg R | Total R | Calmar | Prop Payout | Funded Payout |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `HTF_LSI 5m lag24 ungated lead` | 42.0 | 2.200 | 0.430 | 18.073 | 6.024 | 71.2% | 71.2% |
| `HTF_LSI 5m gap2.5 right2 lag0 skip bear_high_vol` | 46.0 | 1.899 | 0.346 | 15.939 | 5.107 | 65.7% | 65.7% |
| `HTF_LSI 5m gap2.5 right3 lag0 skip bear_high_vol` | 54.0 | 1.916 | 0.325 | 17.545 | 4.680 | 65.4% | 65.4% |

## Candidate Details

### HTF_LSI 5m lag24 ungated lead

- gate: `ungated`
- config: `long fvg_limit 08:30-15:00 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL20 fvgR2 lag24`
- holdout raw: trades `42.0`, PF `2.2003`, avg R `0.4303`, total R `18.073`, Calmar `6.0243`, DD `-3.0`
- holdout prop scorecard: payout `71.2%`, breach `3.3%`, open `25.5%`, EV/attempt `$14196.73`
- holdout funded scorecard: payout `71.2%`, breach `3.3%`, open `25.5%`, EV/start `$81.47`
- `2025-04-01` to `2025-12-31`: `{'total_trades': 32.0, 'win_rate': 0.625, 'profit_factor': 2.4606, 'avg_r': 0.4869, 'total_r': 15.5814, 'max_drawdown_r': -3.0, 'sharpe_ratio': 6.2251, 'calmar_ratio': 5.1938}`
- `2026-01-01` to `2026-03-24`: `{'total_trades': 10.0, 'win_rate': 0.5, 'profit_factor': 1.5596, 'avg_r': 0.2492, 'total_r': 2.4915, 'max_drawdown_r': -1.0168, 'sharpe_ratio': 2.8738, 'calmar_ratio': 2.4504}`

### HTF_LSI 5m gap2.5 right2 lag0 skip bear_high_vol

- gate: `skip_bear_high_vol`
- config: `long fvg_limit 08:30-15:00 rr3.0 tp0.6 gap2.5 htf60 n3 cap2 fvgL20 fvgR2 lag0`
- holdout raw: trades `46.0`, PF `1.8986`, avg R `0.3465`, total R `15.9391`, Calmar `5.1072`, DD `-3.1209`
- holdout prop scorecard: payout `65.7%`, breach `3.3%`, open `31.1%`, EV/attempt `$13085.62`
- holdout funded scorecard: payout `65.7%`, breach `3.3%`, open `31.1%`, EV/start `$59.67`
- `2025-04-01` to `2025-12-31`: `{'total_trades': 39.0, 'win_rate': 0.5897, 'profit_factor': 1.9385, 'avg_r': 0.3465, 'total_r': 13.512, 'max_drawdown_r': -3.1209, 'sharpe_ratio': 4.5908, 'calmar_ratio': 4.3295}`
- `2026-01-01` to `2026-03-24`: `{'total_trades': 7.0, 'win_rate': 0.4286, 'profit_factor': 1.7248, 'avg_r': 0.3467, 'total_r': 2.4271, 'max_drawdown_r': -1.5729, 'sharpe_ratio': 3.4956, 'calmar_ratio': 1.543}`

### HTF_LSI 5m gap2.5 right3 lag0 skip bear_high_vol

- gate: `skip_bear_high_vol`
- config: `long fvg_limit 08:30-15:00 rr3.0 tp0.6 gap2.5 htf60 n3 cap2 fvgL20 fvgR3 lag0`
- holdout raw: trades `54.0`, PF `1.9163`, avg R `0.3249`, total R `17.5446`, Calmar `4.6799`, DD `-3.7489`
- holdout prop scorecard: payout `65.4%`, breach `3.3%`, open `31.4%`, EV/attempt `$13020.26`
- holdout funded scorecard: payout `65.4%`, breach `3.3%`, open `31.4%`, EV/start `$94.0`
- `2025-04-01` to `2025-12-31`: `{'total_trades': 44.0, 'win_rate': 0.6591, 'profit_factor': 2.2959, 'avg_r': 0.4118, 'total_r': 18.1175, 'max_drawdown_r': -3.0, 'sharpe_ratio': 5.7179, 'calmar_ratio': 6.0392}`
- `2026-01-01` to `2026-03-24`: `{'total_trades': 10.0, 'win_rate': 0.3, 'profit_factor': 0.9818, 'avg_r': -0.0573, 'total_r': -0.5729, 'max_drawdown_r': -2.0, 'sharpe_ratio': -0.6312, 'calmar_ratio': -0.2865}`
