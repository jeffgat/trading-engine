# NQ NY LSI Legacy vs HTF-LSI Exact Comparison

- Comparison date run: `2026-04-11`
- Exact replay latest common end: `2026-03-24`
- Legacy branch tested as a single-leg exact replay of the `ALPHA_V1` NQ NY LSI leg:
  - `legacy-LSI`
  - `09:35-15:30`
  - `rr=3.0`
  - `tp1_ratio=0.34`
  - `atr_length=10`
  - `min_gap_atr_pct=5.0`
  - `lsi_n_left=8`
  - `lsi_n_right=60`
  - `fvg_window=20/5`
  - `excluded_dow=[2,3]`
- HTF branch tested as the current operating exact profile:
  - `htf-LSI`
  - `08:30-15:00`
  - `rr=3.0`
  - `tp1_ratio=0.6`
  - `atr_length=14`
  - `min_gap_atr_pct=3.0`
  - `htf_level_tf_minutes=60`
  - `htf_n_left=3`
  - `htf_trade_max_per_session=2`
  - `fvg_window=20/2`
  - `max_fvg_to_inversion_bars=24`
  - `excluded_dow=null`

## Shared Payout Models

- Funded first-payout model:
  - start `$50,000`
  - trailing drawdown `$2,000`
  - first payout floor `$52,500`
  - challenge fee `$100`
  - risk `$500/R`
- Prop R-model:
  - payout `+5R`
  - breach `-4R`
  - daily limit `-2R`
  - min trading days `5`
  - account fee `$50`
  - reset fee `$50`
  - risk `$400/R`

## 10 Years

- Window: `2016-01-01` to `2025-12-31`
- Legacy ALPHA_V1 single-leg exact replay:
  - raw: `427` trades, `58.3%` WR, PF `1.595`, avg R `0.189`, total R `+80.67`, DD `-6.36R`, Calmar `12.68`
  - funded: payout `81.6%`, breach `15.3%`, open `3.1%`, avg days `175.57`, EV/start `$117.83`
  - prop: payout `93.9%`, breach `2.9%`, open `3.2%`, avg days `203.73`, EV/attempt `$1451.35`
- HTF_LSI_5M_LAG24 exact replay:
  - raw: `530` trades, `44.0%` WR, PF `1.357`, avg R `0.165`, total R `+87.20`, DD `-12.97R`, Calmar `6.72`
  - funded: payout `52.0%`, breach `47.2%`, open `0.8%`, avg days `76.75`, EV/start `$160.89`
  - prop: payout `68.3%`, breach `30.9%`, open `0.8%`, avg days `110.50`, EV/attempt `$1027.45`

## 2024

- Window: `2024-01-01` to `2024-12-31`
- Legacy:
  - raw: `43` trades, `44.2%` WR, PF `1.007`, avg R `-0.014`, total R `-0.58`, DD `-4.35R`, Calmar `-0.13`
  - funded: payout `8.6%`, breach `31.9%`, open `59.4%`, EV/start `-$81.20`
  - prop: payout `8.6%`, breach `2.6%`, open `88.8%`, EV/attempt `$86.74`
- HTF lag24:
  - raw: `64` trades, `45.3%` WR, PF `1.651`, avg R `0.286`, total R `+18.28`, DD `-5.20R`, Calmar `3.51`
  - funded: payout `33.6%`, breach `51.4%`, open `15.0%`, EV/start `$113.42`
  - prop: payout `75.1%`, breach `9.6%`, open `15.3%`, EV/attempt `$1146.49`

## 2025

- Window: `2025-01-01` to `2025-12-31`
- Legacy:
  - raw: `33` trades, `66.7%` WR, PF `2.437`, avg R `0.354`, total R `+11.69`, DD `-4.40R`, Calmar `2.65`
  - funded: payout `50.0%`, breach `19.6%`, open `30.5%`, EV/start `$16.56`
  - prop: payout `65.4%`, breach `2.9%`, open `31.7%`, EV/attempt `$994.71`
- HTF lag24:
  - raw: `42` trades, `54.8%` WR, PF `1.497`, avg R `0.380`, total R `+15.94`, DD `-7.08R`, Calmar `2.25`
  - funded: payout `64.1%`, breach `27.9%`, open `8.0%`, EV/start `$149.67`
  - prop: payout `67.6%`, breach `24.4%`, open `8.0%`, EV/attempt `$1019.87`

## 2026 YTD

- Window: `2026-01-01` to `2026-03-24`
- Legacy:
  - raw: `7` trades, `71.4%` WR, PF `3.005`, avg R `0.512`, total R `+3.58`, DD `-1.00R`, Calmar `3.58`
  - funded: payout `0.0%`, breach `0.0%`, open `100.0%`, EV/start `-$100.00`
  - prop: payout `0.0%`, breach `0.0%`, open `100.0%`, EV/attempt `-$50.00`
- HTF lag24:
  - raw: `10` trades, `50.0%` WR, PF `1.517`, avg R `0.336`, total R `+3.36`, DD `-1.13R`, Calmar `2.98`
  - funded: payout `4.2%`, breach `0.0%`, open `95.8%`, EV/start `-$92.42`
  - prop: payout `4.2%`, breach `0.0%`, open `95.8%`, EV/attempt `$17.61`

## Takeaways

- On the exact single-leg `10y` comparison, legacy is still the stronger account-farming branch on robustness and payout rate.
- HTF lag24 traded more often and produced slightly more total R over `2016-2025`, but it did so with about double the drawdown and materially worse payout conversion.
- `2024` was the cleanest year in favor of HTF lag24; legacy was nearly flat while HTF lag24 stayed clearly profitable.
- `2025` split the result:
  - legacy had better raw PF and lower DD
  - HTF lag24 had more trades, higher total R, and materially better funded payout economics
- `2026 YTD` is too thin to over-interpret. Legacy raw quality is better so far, but neither branch has enough 2026 trade history to make the payout model meaningful yet.
