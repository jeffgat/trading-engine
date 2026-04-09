# NQ NY Reference LSI Attribution

- Candidate: `NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.0 tp0.8`
- Holdout frozen at `2025-01-01` and not used.
- Discovery `2016-01-01` to `2022-12-31`.
- Validation `2023-01-01` to `2024-12-31`.

## Overall

- `pre-holdout`: trades `101`, avgR `0.0933`, PF `1.2252`, totalR `9.42`, WR `0.4455`
- `discovery`: trades `73`, avgR `-0.0134`, PF `0.9985`, totalR `-0.98`, WR `0.411`
- `validation`: trades `28`, avgR `0.3713`, PF `1.9652`, totalR `10.4`, WR `0.5357`

## Exact Levels

- `previous_day_high`: pre `10` / avgR `0.644` / PF `3.2655` / totalR `6.44`; validation `5` / avgR `1.1121` / PF `36.8209` / totalR `5.56`
- `previous_day_low`: pre `17` / avgR `0.0716` / PF `1.0872` / totalR `1.22`; validation `6` / avgR `0.1557` / PF `1.1909` / totalR `0.93`
- `asia_high`: pre `20` / avgR `0.2333` / PF `1.6426` / totalR `4.67`; validation `0` / avgR `0.0` / PF `0.0` / totalR `0.0`
- `asia_low`: pre `21` / avgR `0.1389` / PF `1.294` / totalR `2.92`; validation `8` / avgR `0.308` / PF `1.9144` / totalR `2.46`
- `london_high`: pre `13` / avgR `-0.1867` / PF `0.6708` / totalR `-2.43`; validation `4` / avgR `-0.1147` / PF `0.8216` / totalR `-0.46`
- `london_low`: pre `20` / avgR `-0.1697` / PF `0.7704` / totalR `-3.39`; validation `5` / avgR `0.3795` / PF `1.8121` / totalR `1.9`

## Families And Sides

### level_family

- `previous_day`: pre `27` / avgR `0.2836` / PF `1.7271` / totalR `7.66`; validation `11` / avgR `0.5904` / PF `3.0669` / totalR `6.49`
- `asia`: pre `41` / avgR `0.1849` / PF `1.4704` / totalR `7.58`; validation `8` / avgR `0.308` / PF `1.9144` / totalR `2.46`
- `london`: pre `33` / avgR `-0.1764` / PF `0.7345` / totalR `-5.82`; validation `9` / avgR `0.1599` / PF `1.3889` / totalR `1.44`

### level_side

- `high_side`: pre `43` / avgR `0.2018` / PF `1.5398` / totalR `8.68`; validation `9` / avgR `0.5669` / PF `3.1238` / totalR `5.1`
- `low_side`: pre `58` / avgR `0.0128` / PF `1.0142` / totalR `0.74`; validation `19` / avgR `0.2787` / PF `1.6673` / totalR `5.3`

### direction

- `short`: pre `43` / avgR `0.2018` / PF `1.5398` / totalR `8.68`; validation `9` / avgR `0.5669` / PF `3.1238` / totalR `5.1`
- `long`: pre `58` / avgR `0.0128` / PF `1.0142` / totalR `0.74`; validation `19` / avgR `0.2787` / PF `1.6673` / totalR `5.3`

### time_bucket

- `09:00-09:30`: pre `2` / avgR `-1.0` / PF `0.0` / totalR `-2.0`; validation `1` / avgR `-1.0` / PF `0.0` / totalR `-1.0`
- `09:30-10:00`: pre `24` / avgR `0.0816` / PF `1.122` / totalR `1.96`; validation `11` / avgR `0.135` / PF `1.2954` / totalR `1.48`
- `10:00-10:30`: pre `42` / avgR `0.1074` / PF `1.2644` / totalR `4.51`; validation `10` / avgR `0.5978` / PF `2.9077` / totalR `5.98`
- `10:30-11:00`: pre `33` / avgR `0.15` / PF `1.5371` / totalR `4.95`; validation `6` / avgR `0.6558` / PF `9.0566` / totalR `3.93`

## By Year

- `2016`: trades `9`, avgR `-0.4096`, PF `0.3774`, totalR `-3.69`
- `2017`: trades `11`, avgR `0.3515`, PF `2.0199`, totalR `3.87`
- `2018`: trades `11`, avgR `0.0028`, PF `1.0313`, totalR `0.03`
- `2019`: trades `8`, avgR `-0.0341`, PF `0.9636`, totalR `-0.27`
- `2020`: trades `13`, avgR `-0.3843`, PF `0.3381`, totalR `-5.0`
- `2021`: trades `12`, avgR `-0.034`, PF `0.989`, totalR `-0.41`
- `2022`: trades `9`, avgR `0.4987`, PF `2.8607`, totalR `4.49`
- `2023`: trades `16`, avgR `0.508`, PF `2.4813`, totalR `8.13`
- `2024`: trades `12`, avgR `0.1891`, PF `1.4424`, totalR `2.27`

## Simplification Hypotheses

- `high_side_exclude_london`: pre `30` / avgR `0.3702` / PF `2.0393` / totalR `11.11`; discovery `25` / avgR `0.2218` / PF `1.6157` / totalR `5.55`; validation `5` / avgR `1.1121` / PF `36.8209` / totalR `5.56`
- `previous_day_high_plus_asia_high`: pre `30` / avgR `0.3702` / PF `2.0393` / totalR `11.11`; discovery `25` / avgR `0.2218` / PF `1.6157` / totalR `5.55`; validation `5` / avgR `1.1121` / PF `36.8209` / totalR `5.56`
- `asia_only`: pre `41` / avgR `0.1849` / PF `1.4704` / totalR `7.58`; discovery `33` / avgR `0.1551` / PF `1.3683` / totalR `5.12`; validation `8` / avgR `0.308` / PF `1.9144` / totalR `2.46`
- `exclude_london`: pre `68` / avgR `0.2241` / PF `1.5622` / totalR `15.24`; discovery `49` / avgR `0.1282` / PF `1.319` / totalR `6.28`; validation `19` / avgR `0.4715` / PF `2.4333` / totalR `8.96`
- `high_side_only`: pre `43` / avgR `0.2018` / PF `1.5398` / totalR `8.68`; discovery `34` / avgR `0.1052` / PF `1.3249` / totalR `3.58`; validation `9` / avgR `0.5669` / PF `3.1238` / totalR `5.1`
- `previous_day_only`: pre `27` / avgR `0.2836` / PF `1.7271` / totalR `7.66`; discovery `16` / avgR `0.0727` / PF `1.2199` / totalR `1.16`; validation `11` / avgR `0.5904` / PF `3.0669` / totalR `6.49`

## Readout

- `London` is the clear drag. It is negative across the full pre-holdout sample and negative in discovery, even though the validation slice is modestly positive.
- `high-side / short` sweeps carry most of the edge. They are positive in both discovery and validation, while `low-side / long` is nearly flat across the full pre-holdout sample and negative in discovery.
- `previous_day` and `asia` are the useful level families. Both are positive in discovery and validation. `previous_day_high` is exceptionally strong in validation, but too thin to elevate on its own.
- The strongest balanced simplification hypothesis is `exclude_london`. It keeps both directions from `previous_day` and `asia`, stays positive in discovery and validation, and materially improves the pre-holdout profile versus the all-level candidate.
- `high_side_exclude_london` is even stronger, but the validation sample is only 5 trades. Treat it as a challenger thesis, not the primary restart.

## Recommendation

- Next fresh thesis: restart discovery with `reference_lsi` restricted to `previous_day_*` and `asia_*` only, keeping the current candidate otherwise frozen as the baseline anchor.
- Secondary challenger thesis: restrict to `previous_day_high` plus `asia_high` only.
- Do not open the `2025-01-01+` holdout for the current all-level candidate.