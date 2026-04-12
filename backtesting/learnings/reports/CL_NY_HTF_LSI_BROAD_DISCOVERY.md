# CL NY HTF-LSI Broad Discovery

- Instrument: `CL`
- Timeframes explored: `1m, 3m`
- Holdout remained closed during discovery.
- This CL packet was **intentionally frozen after Stage C**. The generic `1m` Stage D/E interaction + lag grid was disproportionately expensive on the full `2016-2025` 1m history, so the shortlist was taken from saved Stage B/C results and moved into stitched OOS.

## Stage A Structural

Top families were not the transferred NQ `5m fvg_limit` branch. CL discovery shifted hard into:

- `1m`
- `long`
- `close`
- later NY cutoffs, especially `13:00-15:00`
- `htf30 n5` first, with `htf60 n3` as the main structural alternate

Leading Stage A rows:

| Candidate | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: |
| `1m htf30 n5 long close 14:00` | 1.098 | 0.053 | 1.193 | 0.103 | 2.916 |
| `1m htf30 n5 long close 15:00` | 1.088 | 0.046 | 1.182 | 0.093 | 2.771 |
| `1m htf30 n5 long close 13:00` | 1.125 | 0.067 | 1.173 | 0.094 | 2.545 |
| `1m htf60 n3 long close 14:00` | 1.131 | 0.071 | 1.157 | 0.083 | 1.439 |
| `3m htf60 n3 both fvg_limit 15:00` | 1.053 | 0.028 | 1.099 | 0.049 | 1.052 |

## Stage B Trade Cap

Trade-cap testing showed:

- `cap=2` and `cap=3` were identical on the lead family
- `cap=2` is the honest default
- best Stage B row was `1m / long / close / 14:00 / htf30 n5 / cap2`

Leading Stage B rows:

| Candidate | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: |
| `1m htf30 n5 long close 14:00 cap2` | 1.084 | 0.046 | 1.230 | 0.121 | 3.938 |
| `1m htf30 n5 long close 13:00 cap2` | 1.128 | 0.069 | 1.222 | 0.119 | 3.573 |
| `1m htf30 n5 long close 15:00 cap2` | 1.059 | 0.032 | 1.173 | 0.088 | 3.204 |
| `1m htf60 n3 long close 14:00 cap2` | 1.126 | 0.067 | 1.211 | 0.110 | 2.281 |

## Stage C One-at-a-Time

Important local challengers around the best base:

- `entry_end=10:30` improved validation quality the most, but on much thinner sample
- `atr=10` and `atr=20` both improved validation versus the base
- `htf_n_left=7` was the best same-shape challenger
- `gap=3.0`, `rr=3.0`, `tp1=0.6`, `right=10` remained the stable defaults

Key Stage C rows:

| Candidate | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: |
| `entry_end=10:30` | 1.073 | 0.042 | 1.420 | 0.223 | 4.137 |
| `atr=10` | 1.068 | 0.038 | 1.247 | 0.131 | 4.268 |
| `atr=20` | 1.105 | 0.057 | 1.248 | 0.129 | 4.093 |
| `htf_n_left=7` | 1.098 | 0.054 | 1.291 | 0.151 | 4.019 |
| `left_minutes=140` | 1.084 | 0.045 | 1.224 | 0.118 | 3.974 |

## Freeze

Because CL `1m` interaction search was too expensive to finish proportionately, the stitched shortlist was frozen from Stage B/C:

- `control_stage_b_end14`
- `control_stage_b_end13`
- `count_stage_b_end15`
- `structural_alt_htf60_end14`
- `atr10_end14`
- `htf_n7_end14`
- `early_end1030`

These candidates were then evaluated in:

- [CL_NY_HTF_LSI_STITCHED_FOLLOWUP.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/CL_NY_HTF_LSI_STITCHED_FOLLOWUP.md)
- [CL_NY_HTF_LSI_PHASE_ONE.md](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/learnings/reports/CL_NY_HTF_LSI_PHASE_ONE.md)
