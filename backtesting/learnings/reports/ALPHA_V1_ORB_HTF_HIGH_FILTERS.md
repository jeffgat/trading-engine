# ALPHA_V1 ORB HTF-High Filters

Date: 2026-04-17

## Question

For the active `ALPHA_V1` ORB legs, do either of these HTF-high ideas help?

1. **Pending-order cancel**: if the ORB limit is still open, price reaches `TP2` before entry, and a fresh HTF high is also swept before fill, cancel the order.
2. **Headroom filter**: only keep ORB signals where the active published HTF high is already at `TP1` or greater when the order arms.

## HTF Assumption

The ORB legs do not currently define their own HTF detector settings, so this read used the instrument-native HTF families already established in prior HTF-LSI discovery:

- `NQ`: published unswept `60m` highs, `n_left=3`
- `ES`: published unswept `90m` highs, `n_left=3`

This uses the repo's existing `compute_htf_unswept_levels(...)` model, which tracks the latest published unswept HTF high available on each base bar.

## Method

- Scope: the three active `ALPHA_V1` ORB legs from the earlier pre-entry target-cancel packet
  - `ORB/NQ_ASIA-RR6`
  - `ORB/ES_ASIA-RR1.5`
  - `ORB/ES_NY-RR5`
- Baselines here match the earlier research-side `ALPHA_V1` pre-entry target-cancel packet, not the separate exact lifecycle tables in `ALPHA_V1.md`.
- Both ideas were treated as **trade-removal filters**:
  - no new fills are created
  - qualifying filled trades are converted to `no_fill`
- Cancel rule:
  - scan only the pending-order window
  - require both pre-entry `TP2` touch and a fresh HTF-high sweep before the first fill bar
  - if fill and cancel would occur on the same bar, fill still wins
- Headroom filter:
  - check the active published HTF high on the order-arm bar (`signal_bar + 1`)
  - keep the trade only if that high is `>= TP1`
- Windows:
  - Full history
  - Recent: `2024-01-01+`

Artifacts:
- Script: `backtesting/scripts/run_alpha_v1_orb_htf_high_filters.py`
- Raw summary: `backtesting/data/results/alpha_v1_orb_htf_high_filters_20260417/summary.json`

## Pending-Order Cancel Result

This rule did **not** help on any ORB leg.

### Full History

| Leg | Canceled fills | Delta R | Delta DD | Verdict |
|---|---:|---:|---:|---|
| `ORB/NQ_ASIA-RR6` | 0 | +0.0R | +0.0R | No-op |
| `ORB/ES_ASIA-RR1.5` | 10 | -2.5R | -0.2R | Harmful |
| `ORB/ES_NY-RR5` | 4 | -1.9R | -0.5R | Harmful |

### Recent (`2024-01-01+`)

| Leg | Canceled fills | Delta R | Delta DD | Verdict |
|---|---:|---:|---:|---|
| `ORB/NQ_ASIA-RR6` | 0 | +0.0R | +0.0R | No-op |
| `ORB/ES_ASIA-RR1.5` | 4 | -3.0R | -0.7R | Harmful |
| `ORB/ES_NY-RR5` | 2 | -1.0R | -0.5R | Harmful |

## Headroom Filter Result

As a **strategy filter**, `HTF high >= TP1` was too destructive everywhere. It removed a large share of trades and reduced total R on every leg.

### Full History

| Leg | Kept fills | Delta R | Delta DD | Read |
|---|---:|---:|---:|---|
| `ORB/NQ_ASIA-RR6` | 189 / 753 | -142.4R | -3.0R | Too selective; DD worsens materially |
| `ORB/ES_ASIA-RR1.5` | 551 / 1468 | -81.0R | +2.3R | Cleaner DD, but too much R lost |
| `ORB/ES_NY-RR5` | 236 / 876 | -122.5R | +0.4R | Not viable as a filter |

### Recent (`2024-01-01+`)

| Leg | Kept fills | Delta R | Delta DD | Read |
|---|---:|---:|---:|---|
| `ORB/NQ_ASIA-RR6` | 31 / 156 | -51.6R | -1.1R | Clearly worse |
| `ORB/ES_ASIA-RR1.5` | 136 / 320 | -30.8R | +0.9R | Lower DD, but not enough quality gain |
| `ORB/ES_NY-RR5` | 65 / 201 | -29.2R | +1.3R | Recent sample turns negative |

## Trade-Quality Read

The better question is whether the trades that pass `HTF high >= TP1` are actually better.

### `ORB/NQ_ASIA-RR6`

- Full history: mild historical improvement
  - with headroom: WR `46.6%`, avg R `0.368`, TP2 rate `7.4%`
  - without headroom: WR `44.7%`, avg R `0.253`, TP2 rate `4.3%`
- Recent: the relationship **reversed sharply**
  - with headroom: WR `35.5%`, avg R `0.095`
  - without headroom: WR `50.4%`, avg R `0.412`
- Conclusion: not robust. Treat as a historical curiosity, not a live-quality signal.

### `ORB/ES_ASIA-RR1.5`

- Full history: slight quality improvement with headroom
  - with headroom: WR `56.8%`, avg R `0.119`, TP2 rate `25.2%`
  - without headroom: WR `52.6%`, avg R `0.088`, TP2 rate `19.5%`
- Recent: advantage mostly disappears
  - with headroom: WR `57.4%`, avg R `0.119`
  - without headroom: WR `56.5%`, avg R `0.167`
- Conclusion: there may be a weak old-sample quality bias here, but it does **not** survive the recent window cleanly.

### `ORB/ES_NY-RR5`

- Full history: no quality gain
  - with headroom: WR `61.4%`, avg R `0.085`, TP2 rate `5.1%`
  - without headroom: WR `61.3%`, avg R `0.191`, TP2 rate `7.0%`
- Recent: clearly worse with headroom
  - with headroom: WR `55.4%`, avg R `-0.122`, TP2 rate `1.5%`
  - without headroom: WR `66.2%`, avg R `0.215`, TP2 rate `7.4%`
- Conclusion: hard reject.

## Decision

Do **not** promote either ORB HTF-high idea into the active `ALPHA_V1` ORB legs.

- **Pre-entry `TP2 + fresh HTF-high sweep` cancel**: reject. It is either a no-op or mildly harmful.
- **`HTF high >= TP1` filter**: reject as a live rule. It destroys too much trade flow, and its quality read is not robust across the recent window.

If we revisit HTF context on the ORB legs, the next honest step should be a **soft scoring / ranking read** rather than a hard binary filter.
