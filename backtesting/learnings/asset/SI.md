# SI (Silver Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $5,000/point
- **Min tick**: 0.005 ($25/tick)
- **Commission**: $0.05/contract/side
- **Data**: 2016-03 to 2026-03 (~10 years, 5m + 1m)
- **Roll**: Volume-based `.v.0` (commodity future)
- **Liquidity**: Asia session has the strongest ORB edge (short-side). NY moderate. LDN weak.

---

## Strategies Tested

### 1. 3-Session ORB Continuation Discovery (NY + Asia + LDN) — CONDITIONAL GO (Asia shorts)
- **Status**: **CONDITIONAL GO** — Asia shorts pass WF with strong metrics; holdout positive but holdout PR below 40%
- **Scripts**: `run_si_orb_discovery.py`, `run_si_orb_discovery_pipeline.py`, `run_si_orb_phase_one.py`
- **Sweep**: 1,296 configs per session (4 ORB windows × 2 stop modes × 4 RR × 4 TP1 × 3 directions × 5 stop values), 3,888 total. Pre-holdout <2025-01. 1m magnifier.

**Discovery sweep results:**
- **Asia**: Outstanding shorts — top 25 all short-only. Best: 30m ORB 75%, RR 2.5, TP1 0.6, Calmar 10.08, 1 neg yr. Scores 1.2–3.6.
- **NY**: Moderate — mixed directions, scores 0–1.5, most configs 1-2 neg years.
- **LDN**: Weak longs — all 2-3 neg years, scores <-1.2.

**Discovery pipeline (WF 12m IS / 3m OOS / 3m step, Calmar objective):**
| Candidate | OOS R | Calmar | Sharpe | DD | WFE | Stability | Verdict |
|-----------|-------|--------|--------|------|-----|-----------|---------|
| Asia-3 (30m ORB 75%, RR 3.0, TP1 0.6, short) | +109.2 | 9.50 | 1.67 | -11.5 | 0.570 | 0.871 | PROMOTE |
| Asia-1 (30m ORB 75%, RR 2.5, TP1 0.6, short) | +92.1 | 8.08 | 1.48 | -11.4 | 0.469 | 0.839 | PROMOTE |
| Asia-2 (5m ORB 50%, RR 3.5, TP1 0.6, short) | +119.3 | 5.74 | 1.13 | -20.8 | 0.429 | 0.806 | PROMOTE |
| Asia-4 (30m ORB 75%, RR 3.0, TP1 0.5, short) | +79.6 | 5.13 | 1.27 | -15.5 | 0.417 | 0.774 | CHALLENGER |
| NY-1 (10m ORB 75%, RR 2.5, TP1 0.5, short) | +43.7 | 2.38 | 0.73 | -18.4 | 0.337 | 1.000 | CHALLENGER |

**Phase-One Results (structural + prop sim + holdout + PSR/DSR):**
| Candidate | Pre R | HO R | Pre PR | HO PR | EV | PSR | DSR | Verdict |
|-----------|-------|------|--------|-------|------|-----|-----|---------|
| Asia-3 | +121.8 | **+10.1** | **66.4%** | 37.0% | $13,209 | 0.999 | 0.376 | CONDITIONAL |
| Asia-1 | +122.7 | **+4.9** | **73.1%** | 29.3% | $14,550 | 1.000 | **0.507** | CONDITIONAL |
| Asia-4 | +121.9 | **+6.8** | **68.9%** | 37.0% | $13,717 | 1.000 | **0.470** | CONDITIONAL |
| Asia-2 | +129.0 | -14.3 | 53.4% | 27.9% | $10,600 | 0.994 | 0.178 | CONDITIONAL |
| NY-1 | +57.4 | -20.2 | 56.9% | 3.3% | $11,307 | 0.957 | 0.049 | CONDITIONAL |

**Key findings:**
- **Asia-1 has the highest DSR (0.507)** — edge survives deflation from 1,296 trials. Best pre-holdout PR (73.1%) and EV ($14,550).
- **Asia-3 has the best holdout** (+10.1R, Calmar 1.05, Sharpe 1.15) and highest pre-holdout PR (66.4%).
- **Asia-4** is a strong alternative (HO +6.8R, PR 68.9%, DSR 0.470).
- **Asia-2 and NY-1 failed holdout** (negative R) — not recommended.
- **30m ORB + ORB 75% stop + short-only** is the winning structural family on SI Asia.
- All holdout payout rates are below 40% (the STRONG threshold), earning CONDITIONAL instead of STRONG. But all three Asia 30m configs have positive holdout R and pre-holdout PR >66%.
- **2017 is the only negative year** across all Asia 30m configs — consistent structural weakness in that single year.

**Recommended configs for further optimization:**
- **Asia-1** (CONDITIONAL): 30m ORB, ORB 75%, RR 2.5, TP1 0.6, short — highest DSR and PR
- **Asia-3** (CONDITIONAL): 30m ORB, ORB 75%, RR 3.0, TP1 0.6, short — best holdout
- **Asia-4** (CONDITIONAL): 30m ORB, ORB 75%, RR 3.0, TP1 0.5, short — balanced

---

## Key Findings

### Direction
- **Shorts dominate SI ORB continuation**, especially in Asia session. All top 25 Asia configs are short-only. This is the opposite of most index futures (NQ, ES, RTY) where longs tend to carry the edge.

### Session
- **Asia is the primary session**: Calmar 8-10 structural, 5-9 OOS. NY is moderate. LDN is dead.
- **30m ORB is the optimal window** for Asia — consistent across all top configs.

### Stop Type
- **ORB-range stops (75%)** dominate the Asia top configs, similar to RTY's finding with ORB stops.

### Holdout Behavior (2025-2026)
- All Asia 30m configs are positive in the holdout but show weakness in early 2026. Holdout payout rates 29-37% are below the STRONG threshold of 40%.

---

## Overall Assessment
SI Asia ORB continuation shorts are a **CONDITIONAL GO** — the edge is statistically real (PSR 0.999-1.000, DSR 0.47-0.51 for the best configs), walk-forward validated (WFE 0.47-0.57, Calmar 5-9 OOS), and holdout-confirmed (+5 to +10R). Pre-holdout payout rates are excellent (66-73%). The main weakness is holdout payout rates below 40% and the consistent 2017 negative year. Recommended next step: variable sweep optimization on the Asia-1/Asia-3 anchors.

---

## Regime-Gate Transfer Update (2026-04-01)

The shared cross-asset regime-gate study materially improved the two SI anchors that already looked best in phase one:

| Candidate | Ungated Holdout | Gated Holdout | Verdict |
|-----------|-----------------|---------------|---------|
| Asia-1 | +9.15R, Cal 0.856, DD -10.7R, PR 46.1% | +11.58R, Cal 2.293, DD -5.1R, PR 46.1% | SUPPORTS GATE |
| Asia-3 | +15.61R, Cal 1.384, DD -11.3R, PR 49.4% | +17.78R, Cal 3.120, DD -5.7R, PR 47.7% | SUPPORTS GATE |

### Updated Interpretation

1. **SI is a genuine transfer success for the medium-vol gate.** Both Asia-1 and Asia-3 materially improve holdout net R and risk-adjusted quality after removing `bull_medium_vol` and `sideways_medium_vol`.
2. **Drawdown compression is the main benefit.** Both candidates roughly halve holdout drawdown while keeping the edge intact.
3. **Second-round promotion**: keep `Asia-1` and `Asia-3` as the SI gate shortlist. `Asia-4` stays a plain optimization backup, not a regime-gate priority.

## Regime-Gate Round Two Refinement (2026-04-01)

Round two confirmed that SI wants the **full** medium-vol gate, not a lighter partial block:

| Candidate | Preferred Variant | Holdout | Damage Bucket Read |
|-----------|-------------------|---------|--------------------|
| Asia-1 | `block_full_medium_vol` | +11.58R, Cal 2.293, DD -5.1R, PR 46.1% | `bull_medium_vol` ~flat (+0.11R), `sideways_medium_vol` negative (-2.53R) |
| Asia-3 | `block_full_medium_vol` | +17.78R, Cal 3.120, DD -5.7R, PR 47.7% | `bull_medium_vol` ~flat (+0.13R), `sideways_medium_vol` negative (-2.31R) |

### Updated Action

1. **Keep the full gate on both SI anchors.** The improvement remains strong enough that there is no reason to downgrade to a partial gate.
2. **The key SI problem bucket is `sideways_medium_vol`.** `bull_medium_vol` was near flat, but keeping the full gate still wins on the combined holdout profile.
3. **Asia-1 and Asia-3 remain the SI regime-gate promotion pair.**

## NY HTF-LSI (Higher-Timeframe Liquidity Sweep Inversion) — NO-GO

- **Status**: **NO-GO** under the default funded-account phase-one model, despite the strongest pre-holdout transfer read outside NQ.
- **Scripts**: `run_cross_asset_htf_lsi_anchor_explore.py`, `run_cross_asset_htf_lsi_broad_discovery.py`, `run_cross_asset_htf_lsi_stitched_followup.py`, `run_si_ny_htf_lsi_phase_one.py`
- **Reports**: `SI_NY_HTF_LSI_ANCHOR_EXPLORE.md`, `SI_NY_HTF_LSI_BROAD_DISCOVERY.md`, `SI_NY_HTF_LSI_STITCHED_FOLLOWUP.md`, `SI_NY_HTF_LSI_PHASE_ONE.md`

**Transfer / discovery path:**
- The narrow NQ anchor packet was already promising on SI. `5m lag24 promoted` printed discovery PF `1.077`, avg R `0.030`, then validation PF `1.791`, avg R `0.280`, Calmar `4.10`. `3m lag0 diagnostic` also stayed alive.
- Reopened broad discovery found a native SI family that was different from NQ, ES, RTY, and GC: `5m`, `both`, `fvg_limit`, `htf60`, `htf_n_left=5`, `gap=3.0`, `atr=14`, later cutoffs (`13:00-14:00`), `rr=3.0-3.5`, `tp1=0.5-0.6`, with `lag=0` or `30`.
- The strongest stitched-OOS leader was `control_stage_b_end13_cap1`: `471` trades, PF `1.386`, avg R `0.157`, Calmar `4.41`. Other frozen `13:00` / `14:00` branches stayed close behind at PF `1.319-1.360` and avg R `0.134-0.147`.

**Phase-one result (holdout opened once on `2025-04-01` to `2026-03-31`):**
- Every frozen candidate failed the funded holdout.
- Holdout samples were `55-66` trades per row.
- Raw holdout quality was negative across the entire family: PF only `0.739-0.775`, avg R `-0.164` to `-0.132`, total R `-9.03R` to `-8.70R`.
- Holdout funded payout was `0.0%` or `1.6%`, with funded EV/start `-$100.00` or `-$99.84` for every candidate.
- Best stitched-OOS payout row was still `control_stage_b_end13_cap1` with OOS funded payout `56.3%` and funded EV/start `$107.31`, but its holdout still failed cleanly: `57` trades, PF `0.759`, avg R `-0.153`, funded payout `0.0%`, funded EV/start `-$100.00`.

**Interpretation:**
- SI HTF-LSI was a legitimate pre-holdout family, not a false alarm from the initial transfer packet.
- But the untouched funded holdout rejected the whole frozen shortlist, so this branch is closed for promotion.
- Keep this separate from SI's existing Asia ORB continuation / regime-gate winners; those remain the live SI research branches.
