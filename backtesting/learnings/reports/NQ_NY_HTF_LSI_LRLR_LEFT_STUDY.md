# NQ NY HTF-LSI LRLR Left Study

- Scope: pre-holdout only (`2016-01-01` to `2025-03-31`). Holdout remains closed.
- Question: does a left-side LRLR structure help HTF-LSI branches enough to justify a hard gate?
- LRLR defaults: descending/ascending unswept pivot chain with `min_pivots=3`, `lookback=120m`, `max_gap=30m`, `max_price_span=0.18 ATR`, `line_tol=0.04 ATR`.

## 2m_anchor

- Timeframe: `2m`
- Validation segmentation: LRLR-present PF `0.776` / Avg R `-0.125` / Calmar `-0.699` vs LRLR-absent PF `1.478` / Avg R `0.209` / Calmar `5.116`
- Validation LRLR share: signals `26.1%`, filled trades `24.4%`
- Honest gate compare: `require` PF `0.792` / Avg R `-0.113` / Calmar `-0.886` / trades `47`; `exclude` PF `1.474` / Avg R `0.206` / Calmar `5.084` / trades `137`

## 1m_candidate

- Timeframe: `1m`
- Validation segmentation: LRLR-present PF `1.372` / Avg R `0.173` / Calmar `2.153` vs LRLR-absent PF `1.165` / Avg R `0.084` / Calmar `0.992`
- Validation LRLR share: signals `48.0%`, filled trades `47.5%`
- Honest gate compare: `require` PF `1.348` / Avg R `0.162` / Calmar `2.055` / trades `106`; `exclude` PF `1.165` / Avg R `0.084` / Calmar `0.992` / trades `115`

## 3m_candidate

- Timeframe: `3m`
- Validation segmentation: LRLR-present PF `1.237` / Avg R `0.145` / Calmar `0.543` vs LRLR-absent PF `1.606` / Avg R `0.231` / Calmar `4.868`
- Validation LRLR share: signals `12.8%`, filled trades `13.2%`
- Honest gate compare: `require` PF `1.237` / Avg R `0.145` / Calmar `0.543` / trades `21`; `exclude` PF `1.606` / Avg R `0.231` / Calmar `4.868` / trades `138`

## 5m_candidate

- Timeframe: `5m`
- Validation segmentation: LRLR-present PF `0.000` / Avg R `1.343` / Calmar `0.000` vs LRLR-absent PF `1.472` / Avg R `0.193` / Calmar `3.797`
- Validation LRLR share: signals `2.4%`, filled trades `2.6%`
- Honest gate compare: `require` PF `0.000` / Avg R `1.343` / Calmar `0.000` / trades `4`; `exclude` PF `1.472` / Avg R `0.193` / Calmar `3.797` / trades `147`

## 2m Sensitivity

| Min Pivots | Max Gap (m) | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 30 | 1.156 | 0.083 | 1.375 | 0.180 | 2.561 | 111 |
| 2 | 40 | 1.121 | 0.067 | 1.360 | 0.170 | 2.530 | 116 |
| 2 | 20 | 1.201 | 0.102 | 1.150 | 0.084 | 1.088 | 96 |
| 4 | 20 | 0.387 | -0.392 | 0.886 | -0.066 | -0.212 | 11 |
| 4 | 40 | 0.707 | -0.148 | 0.801 | -0.091 | -0.330 | 19 |
| 3 | 40 | 0.979 | -0.009 | 0.909 | -0.051 | -0.338 | 54 |
| 4 | 30 | 0.465 | -0.313 | 0.661 | -0.180 | -0.605 | 16 |
| 3 | 20 | 0.962 | -0.026 | 0.825 | -0.084 | -0.654 | 39 |
| 3 | 30 | 0.930 | -0.037 | 0.792 | -0.113 | -0.886 | 47 |
