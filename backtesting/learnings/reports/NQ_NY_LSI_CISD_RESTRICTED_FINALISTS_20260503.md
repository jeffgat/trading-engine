# NQ NY LSI CISD Restricted Finalists

- Latest data date: `2026-05-01`.
- Scope: pre-registered restrictions only: long-only, no Thursday, and entry cutoff at 12:00 ET.
- Base candidates: primary additive 1m and pure CISD 1m.
- DSR search-trial count: `258`.
- Engine note: this pass includes a correction so `excluded_days` applies to the LSI sweep/CISD path, not just FVG candidate detection.

## Top Restricted Rows

| Rank | Candidate | Robust | Full R | Full PF | Full DD | Validation R/PF | Holdout R/PF | Post-2023 R/PF/DD |
| ---: | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530` | `True` | 67.1 | 1.25 | -18.1 | 16.1 / 1.37 | 14.7 / 1.73 | 30.8 / 1.48 / -6.6 |
| 2 | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` | `True` | 88.6 | 1.45 | -9.0 | 20.3 / 1.62 | 12.0 / 1.75 | 32.3 / 1.66 / -7.1 |
| 3 | `add_1m_classic_atr10_b3_a7p5__long__allDOW__cut1530` | `True` | 77.7 | 1.41 | -9.4 | 13.3 / 1.39 | 9.9 / 1.66 | 23.2 / 1.47 / -6.6 |
| 4 | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` | `True` | 38.7 | 1.52 | -9.1 | 10.5 / 2.05 | 4.8 / 1.69 | 15.4 / 1.91 / -2.9 |
| 5 | `add_1m_classic_atr10_b3_a7p5__long__noThu__cut1530` | `True` | 77.2 | 1.53 | -9.1 | 14.5 / 1.56 | 8.9 / 1.81 | 23.3 / 1.63 / -7.1 |
| 6 | `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1200` | `True` | 76.1 | 1.55 | -8.0 | 14.3 / 1.62 | 6.5 / 1.54 | 20.8 / 1.59 / -6.5 |
| 7 | `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1200` | `True` | 70.6 | 1.38 | -11.5 | 8.0 / 1.24 | 10.1 / 1.68 | 18.2 / 1.38 / -7.1 |
| 8 | `pure_1m_classic_atr15_b2_a7p5__both__allDOW__cut1530` | `True` | 29.1 | 1.21 | -14.0 | 10.0 / 1.50 | 10.0 / 1.66 | 19.9 / 1.57 / -7.5 |
| 9 | `pure_1m_classic_atr15_b2_a7p5__long__noThu__cut1530` | `True` | 28.8 | 1.36 | -9.1 | 9.4 / 1.79 | 7.5 / 2.25 | 16.9 / 1.94 / -4.0 |
| 10 | `add_1m_classic_atr10_b3_a7p5__long__noThu__cut1200` | `True` | 64.7 | 1.68 | -9.0 | 9.4 / 1.59 | 4.6 / 1.66 | 14.0 / 1.61 / -5.5 |
| 11 | `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1530` | `True` | 36.3 | 1.36 | -8.8 | 11.4 / 1.82 | 4.4 / 1.37 | 15.9 / 1.61 / -4.5 |
| 12 | `pure_1m_classic_atr15_b2_a7p5__both__noThu__cut1530` | `True` | 21.9 | 1.20 | -14.1 | 9.0 / 1.53 | 8.9 / 1.98 | 17.8 / 1.69 / -7.5 |

## Restriction Deltas

### add_1m_classic_atr10_b3_a7p5 Post-2023 vs Unrestricted
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530`: dR `+1.5`, dPF `+0.18`, dDD `-0.4`, dCalmar `-0.07`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530`: dR `+0.0`, dPF `+0.00`, dDD `+0.0`, dCalmar `+0.00`.
- `add_1m_classic_atr10_b3_a7p5__long__noThu__cut1530`: dR `-7.5`, dPF `+0.15`, dDD `-0.4`, dCalmar `-1.35`.
- `add_1m_classic_atr10_b3_a7p5__long__allDOW__cut1530`: dR `-7.6`, dPF `-0.01`, dDD `-0.0`, dCalmar `-1.15`.
- `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1200`: dR `-10.0`, dPF `+0.11`, dDD `+0.2`, dCalmar `-1.43`.
- `add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1200`: dR `-12.7`, dPF `-0.10`, dDD `-0.5`, dCalmar `-2.10`.
- `add_1m_classic_atr10_b3_a7p5__long__noThu__cut1200`: dR `-16.8`, dPF `+0.13`, dDD `+1.2`, dCalmar `-2.08`.
- `add_1m_classic_atr10_b3_a7p5__long__allDOW__cut1200`: dR `-19.0`, dPF `-0.13`, dDD `-1.4`, dCalmar `-3.18`.

### pure_1m_classic_atr15_b2_a7p5 Post-2023 vs Unrestricted
- `pure_1m_classic_atr15_b2_a7p5__both__allDOW__cut1530`: dR `+0.0`, dPF `+0.00`, dDD `+0.0`, dCalmar `+0.00`.
- `pure_1m_classic_atr15_b2_a7p5__both__noThu__cut1530`: dR `-2.1`, dPF `+0.12`, dDD `+0.0`, dCalmar `-0.28`.
- `pure_1m_classic_atr15_b2_a7p5__long__noThu__cut1200`: dR `-3.0`, dPF `+1.13`, dDD `+5.1`, dCalmar `+4.28`.
- `pure_1m_classic_atr15_b2_a7p5__long__noThu__cut1530`: dR `-3.0`, dPF `+0.37`, dDD `+3.5`, dCalmar `+1.58`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1530`: dR `-4.1`, dPF `+0.04`, dDD `+3.0`, dCalmar `+0.87`.
- `pure_1m_classic_atr15_b2_a7p5__both__allDOW__cut1200`: dR `-4.3`, dPF `+0.01`, dDD `+0.1`, dCalmar `-0.56`.
- `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`: dR `-4.5`, dPF `+0.34`, dDD `+4.6`, dCalmar `+2.57`.
- `pure_1m_classic_atr15_b2_a7p5__both__noThu__cut1200`: dR `-4.8`, dPF `+0.22`, dDD `+0.1`, dCalmar `-0.63`.

## Finalist Diagnostics

### add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530
- PSR/DSR post-2023: `0.9900` / `0.2926` (overfit).
- MC post-2023 block bootstrap: final-R p5 `9.7897`, DD p5 `-12.1429`, ruin(-10R) `15.9%`.
- Phase-one post-2023 normal: payout `77.0%`, breach `16.1%`, EV `3.49R`.
- `baseline` post-2023: `164` tr, PF `1.48`, R `30.8`, DD `-6.6`.
- `slip_1t_per_side` post-2023: `164` tr, PF `1.43`, R `27.8`, DD `-7.1`.
- `slip_2t_per_side` post-2023: `164` tr, PF `1.37`, R `24.8`, DD `-7.6`.

### add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530
- PSR/DSR post-2023: `0.9963` / `0.4298` (overfit).
- MC post-2023 block bootstrap: final-R p5 `12.8847`, DD p5 `-9.7493`, ruin(-10R) `4.0%`.
- Phase-one post-2023 normal: payout `71.3%`, breach `11.5%`, EV `3.79R`.
- `baseline` post-2023: `132` tr, PF `1.66`, R `32.3`, DD `-7.1`.
- `slip_1t_per_side` post-2023: `132` tr, PF `1.60`, R `29.9`, DD `-7.5`.
- `slip_2t_per_side` post-2023: `132` tr, PF `1.54`, R `27.4`, DD `-8.0`.

### add_1m_classic_atr10_b3_a7p5__long__allDOW__cut1530
- PSR/DSR post-2023: `0.9769` / `0.1896` (overfit).
- MC post-2023 block bootstrap: final-R p5 `3.8803`, DD p5 `-12.0865`, ruin(-10R) `11.9%`.
- Phase-one post-2023 normal: payout `62.1%`, breach `16.1%`, EV `3.10R`.
- `baseline` post-2023: `123` tr, PF `1.47`, R `23.2`, DD `-6.6`.
- `slip_1t_per_side` post-2023: `123` tr, PF `1.42`, R `20.9`, DD `-7.0`.
- `slip_2t_per_side` post-2023: `123` tr, PF `1.37`, R `18.6`, DD `-7.4`.

### pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200
- PSR/DSR post-2023: `0.9818` / `0.2329` (overfit).
- MC post-2023 block bootstrap: final-R p5 `6.3294`, DD p5 `-5.1276`, ruin(-10R) `0.1%`.
- Phase-one post-2023 normal: payout `78.2%`, breach `0.0%`, EV `4.44R`.
- `baseline` post-2023: `54` tr, PF `1.91`, R `15.4`, DD `-2.9`.
- `slip_1t_per_side` post-2023: `54` tr, PF `1.85`, R `14.7`, DD `-3.1`.
- `slip_2t_per_side` post-2023: `54` tr, PF `1.80`, R `14.0`, DD `-3.2`.

### add_1m_classic_atr10_b3_a7p5__long__noThu__cut1530
- PSR/DSR post-2023: `0.9865` / `0.2575` (overfit).
- MC post-2023 block bootstrap: final-R p5 `6.2312`, DD p5 `-10.3378`, ruin(-10R) `6.3%`.
- Phase-one post-2023 normal: payout `63.2%`, breach `11.5%`, EV `3.40R`.
- `baseline` post-2023: `95` tr, PF `1.63`, R `23.3`, DD `-7.1`.
- `slip_1t_per_side` post-2023: `95` tr, PF `1.57`, R `21.5`, DD `-7.5`.
- `slip_2t_per_side` post-2023: `95` tr, PF `1.51`, R `19.7`, DD `-7.8`.

### add_1m_classic_atr10_b3_a7p5__both__noThu__cut1200
- PSR/DSR post-2023: `0.9797` / `0.2060` (overfit).
- MC post-2023 block bootstrap: final-R p5 `4.0146`, DD p5 `-10.5073`, ruin(-10R) `6.9%`.
- Phase-one post-2023 normal: payout `59.8%`, breach `13.8%`, EV `3.12R`.
- `baseline` post-2023: `91` tr, PF `1.59`, R `20.8`, DD `-6.5`.
- `slip_1t_per_side` post-2023: `91` tr, PF `1.53`, R `19.0`, DD `-6.8`.
- `slip_2t_per_side` post-2023: `91` tr, PF `1.47`, R `17.3`, DD `-7.1`.
