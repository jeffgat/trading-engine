# NQ NY HTF-LSI Uncapped Rerun

- Uncapped rerun means `htf_trade_max_per_session=0` (disabled) for the research engine.
- The original execution-side `max_open_contracts=1` cap was not part of the original 1m/2m/3m transfer research and was not part of this research rerun either.

## Uncapped Transfer Winners

| Timeframe | Direction | Entry | Val PF | Val Avg R | Val Calmar | Val Trades | Disc PF | Disc Avg R | Disc Trades |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m | long | fvg_limit | 1.556 | 0.224 | 6.208 | 151 | 1.164 | 0.072 | 424 |
| 3m | long | fvg_limit | 1.525 | 0.208 | 4.275 | 146 | 0.938 | -0.032 | 473 |
| 2m | both | fvg_limit | 1.204 | 0.098 | 2.108 | 257 | 0.965 | -0.024 | 819 |
| 1m | both | fvg_limit | 1.279 | 0.132 | 3.762 | 255 | 1.024 | 0.012 | 788 |

## Best Uncapped Lag Winner Vs Best Capped Lag Winner

| Timeframe | Uncapped Winner | Uncapped Val PF | Uncapped Val Avg R | Uncapped Val Calmar | Uncapped Val Trades | Capped Winner | Capped Val PF | Capped Val Avg R | Capped Val Calmar | Capped Val Trades |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 5m | lag24 / long / fvg_limit / cap0 | 1.597 | 0.268 | 6.382 | 127 | lag24 / long / fvg_limit / cap2 | 1.597 | 0.268 | 6.382 | 127 |
| 3m | lag19 / long / fvg_limit / cap0 | 1.637 | 0.273 | 4.975 | 94 | lag0 / long / fvg_limit / cap2 | 1.545 | 0.219 | 5.210 | 159 |
| 2m | lag1 / both / fvg_limit / cap0 | 3.295 | 0.948 | 5.688 | 12 | lag1 / long / fvg_limit / cap1 | 5.069 | 1.196 | 7.177 | 6 |
| 1m | lag0 / both / fvg_limit / cap0 | 1.279 | 0.132 | 3.762 | 255 | lag10 / long / close / cap2 | 1.888 | 0.420 | 4.913 | 76 |

## Read

- `5m`: uncapping did not change the winner. The branch stayed `long / fvg_limit / lag24` with the same validation metrics as the capped study.
- `3m`: uncapping shifted the best validation row to `lag19`, but it still had negative discovery avg R and lower validation Calmar than the capped `lag0` winner, so it looks less robust despite a higher validation PF.
- `2m`: uncapping surfaced a tiny-sample both-direction pop (`12` validation trades). It is not trustworthy enough to promote over the capped read.
- `1m`: uncapping broadened the winner to `both / fvg_limit / lag0`, but the capped `long / close / lag10` winner still had materially better validation PF, avg R, and Calmar on a smaller sample.
- Net: removing the session trade cap does not dethrone `5m lag24`; it actually strengthens the case that `5m` is the cleanest branch because it was unchanged while the lower timeframes got noisier or more sample-fragile.