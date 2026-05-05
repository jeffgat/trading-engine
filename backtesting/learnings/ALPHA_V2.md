# ALPHA_V2 Portfolio

Working promotion packet for the two live-native Asia ORB stop/target variants
selected from the constrained stop + TP1/R:R sweep and exact live-engine replay.

Status: research packet only. Do not treat this as deployed until
`execution/config/exec_configs.json` is explicitly updated and a fresh combined
portfolio exact replay is run.

Sources:
- `backtesting/data/results/alpha_v1_stop_target_live_engine_replay_20260504/`
- `backtesting/learnings/reports/ALPHA_V1_STOP_TARGET_LIVE_ENGINE_REPLAY_20260504.md`
- Current matching-leg comparison source:
  `backtesting/data/results/alpha_v1_live_replay_compare_20260503/comparison_metrics.csv`

## Proposed V2 Changes

| Leg | Current ALPHA_V1 Structure | ALPHA_V2 Variant | Deployability | Exact replay |
| --- | --- | --- | --- | --- |
| ES Asia ORB | `stop=ORB 125%`, `rr=1.5`, `tp1_ratio=0.70`, `TP1_R=1.05` | `stop=ORB 50%`, `rr=2.0`, `tp1_ratio=0.75`, `TP1_R=1.50` | `live_native` | complete |
| NQ Asia ORB | `stop=ORB 100%`, `rr=6.0`, `tp1_ratio=0.30`, `TP1_R=1.80` | `stop=ORB 125%`, `rr=2.5`, `tp1_ratio=0.60`, `TP1_R=1.50` | `live_native` | complete |

## Exact Replay Metrics

Live-engine exact replay over `2016-04-17` to `2026-03-24`, run as
single-candidate temporary execution profiles. No live config was edited.

| Leg | Structure | Last 1y Trades | Last 1y R | Last 1y WR | Last 1y PF | Last 1y DD | Full Trades | Full R | Full WR | Full PF | Full DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ES Asia ORB | Current ALPHA_V1 | 118 | 16.95 | 55.93% | 1.349 | -5.10 | 1116 | 136.68 | 54.93% | 1.287 | -12.23 |
| ES Asia ORB | ALPHA_V2 variant | 143 | 37.25 | 49.65% | 1.519 | -7.25 | 1429 | 209.88 | 47.17% | 1.288 | -16.25 |
| ES Asia ORB | Delta | +25 | +20.30 | -6.28 pts | +0.170 | -2.15 | +313 | +73.20 | -7.76 pts | +0.001 | -4.02 |
| NQ Asia ORB | Current ALPHA_V1 | 66 | 35.39 | 51.52% | 2.140 | -5.00 | 640 | 167.42 | 44.38% | 1.528 | -8.32 |
| NQ Asia ORB | ALPHA_V2 variant | 73 | 32.39 | 56.16% | 2.126 | -6.00 | 725 | 166.57 | 49.66% | 1.495 | -13.34 |
| NQ Asia ORB | Delta | +7 | -3.00 | +4.64 pts | -0.014 | -1.00 | +85 | -0.85 | +5.28 pts | -0.033 | -5.02 |

## Read

- `ES Asia ORB` is the stronger promotion candidate: substantially better
  recent and full-history R, but with lower win rate and deeper drawdown.
- `NQ Asia ORB` is a softer promotion: win rate improves, but recent R and
  full-history R do not improve, and full-history drawdown worsens.
- Both variants are `live_native` because the live ORB engine already supports
  the required stop, R:R, and TP1 fields.
- Exact replay is complete for each individual leg. A combined ALPHA_V2
  portfolio replay is still required before treating this as an operating
  profile because the portfolio-level drawdown and interaction effects have not
  been rerun.

## Live Support Notes

### ES Asia ORB

Execution session key: `ES_Asia`.

Required config changes:
- `stop_basis = "orb"`
- `stop_orb_pct = 50.0`
- `stop_atr_pct = 0.0`
- `rr = 2.0`
- `tp1_ratio = 0.75`

Preserve the rest of the current ALPHA_V1 `ES_Asia` execution settings unless
the combined ALPHA_V2 replay explicitly tests a broader change.

### NQ Asia ORB

Execution session key: `NQ_Asia`.

Required config changes:
- `stop_basis = "orb"`
- `stop_orb_pct = 125.0`
- `stop_atr_pct = 0.0`
- `rr = 2.5`
- `tp1_ratio = 0.60`

Preserve the rest of the current ALPHA_V1 `NQ_Asia` execution settings unless
the combined ALPHA_V2 replay explicitly tests a broader change.
