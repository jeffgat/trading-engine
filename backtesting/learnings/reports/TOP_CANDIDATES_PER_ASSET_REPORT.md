# Top Candidates Per Asset — 3-Session Discovery Workflow (2026-03-31 to 2026-04-01)

Results from the standardized 3-session ORB discovery workflow run on all 7 instruments: ~1,296 configs/session → walk-forward discovery pipeline → phase-one robust pipeline with prop simulation + PSR/DSR. All candidates below come from this recent batch of testing.

Pre-holdout cutoff: 2025-01-01. Regime avoidance gate (bull_medium_vol + sideways_medium_vol) tested on NQ, ES, GC.

## Regime-Gate Follow-Up Note (2026-04-01)

Do **not** use this sheet by itself for the next cross-asset regime-gate round. The shared-holdout transfer study in `REGIME.md` supersedes the discovery-era gate assumptions for shortlist selection.

Second-round regime-gate shortlist:
- `NQ Asia-2` as the reference case
- `GC Asia-1` with `block_bull_medium_vol`
- `RTY NY-2` with `block_bull_medium_vol`
- `RTY NY-4` with `block_full_medium_vol`
- `SI Asia-1` with `block_full_medium_vol`
- `SI Asia-3` with `block_full_medium_vol`

De-prioritized for gating work:
- `ES Asia-B` remains the ES production leader, but **ungated**
- `RTY NY-1` stays useful as an ungated benchmark, not a gated branch
- `CL LDN-1` and `CL LDN-2` are not strong enough gate candidates
- `YM` remains excluded
- `NQ Asia-2` stays **ungated** under the shared transfer-study split
---

## Summary — All Viable Legs

| Asset | Leg | Session | Dir | ORB | Stop | RR | TP1 | Verdict | Pre R | HO R | Pre PR | HO PR | DSR |
|-------|-----|---------|-----|-----|------|----|-----|---------|-------|------|--------|-------|-----|
| **GC** | Asia-1 ungated | Asia | Both | 30m | ORB 25% | 2.5 | 0.6 | **STRONG** | +167.0 | +20.1 | 70.1% | 55.9% | 0.652 |
| **GC** | Asia-1 gated | Asia | Both | 30m | ORB 25% | 2.5 | 0.6 | **STRONG** | +131.9 | +20.4 | 68.1% | 58.4% | 0.508 |
| **GC** | Asia-2 gated | Asia | Short | 15m | ORB 75% | 2.0 | 0.6 | **STRONG** | +92.9 | -1.1 | 77.2% | 43.3% | 0.522 |
| **RTY** | NY-4 | NY | Both | 10m | ORB 100% | 3.0 | 0.4 | **STRONG** | +125.3 | +1.2 | 62.7% | 47.0% | 0.419 |
| **ES** | NY-A (gated) | NY | Both | 45m | ATR 8% | 3.5 | 0.3 | **STRONG** | +71.3 | +2.7 | 78.1% | 43.3% | 0.289 |
| **NQ** | Asia-B (gated) | Asia | Long | 15m | ORB 100% | 3.5 | 0.6 | CONDITIONAL | +119.2 | +42.5 | 57.1% | 76.7% | 0.310 |
| **NQ** | Asia-A (gated) | Asia | Long | 15m | ATR 8% | 3.0 | 0.5 | CONDITIONAL | +102.4 | +37.9 | 58.9% | 74.8% | 0.233 |
| **NQ** | NY-B (gated) | NY | Both | 45m | ORB 75% | 3.5 | 0.3 | CONDITIONAL | +62.6 | +1.8 | 76.6% | 30.8% | 0.209 |
| **RTY** | NY-1 | NY | Both | 10m | ORB 75% | 3.5 | 0.6 | CONDITIONAL | +182.3 | +11.0 | 58.1% | 43.1% | 0.590 |
| **RTY** | NY-2 | NY | Both | 10m | ORB 100% | 3.5 | 0.6 | CONDITIONAL | +156.1 | +8.8 | 59.9% | 52.2% | 0.527 |
| **SI** | Asia-1 | Asia | Short | 30m | ORB 75% | 2.5 | 0.6 | CONDITIONAL | +122.7 | +4.9 | 73.1% | 29.3% | 0.507 |
| **SI** | Asia-4 | Asia | Short | 30m | ORB 75% | 3.0 | 0.5 | CONDITIONAL | +121.9 | +6.8 | 68.9% | 37.0% | 0.470 |
| **SI** | Asia-3 | Asia | Short | 30m | ORB 75% | 3.0 | 0.6 | CONDITIONAL | +121.8 | +10.1 | 66.4% | 37.0% | 0.376 |
| **CL** | LDN-2 | LDN | Long | 30m | ATR 8% | 3.0 | 0.6 | CONDITIONAL | +129.1 | +7.3 | 58.0% | 55.0% | 0.294 |
| **CL** | LDN-3 | LDN | Long | 30m | ATR 8% | 3.5 | 0.5 | CONDITIONAL | +122.6 | +8.6 | 57.1% | 48.9% | 0.243 |
| **CL** | LDN-1 | LDN | Long | 30m | ATR 8% | 3.5 | 0.6 | CONDITIONAL | +123.1 | +12.8 | 58.6% | 54.1% | 0.186 |
| **ES** | Asia-A (gated) | Asia | Long | 60m | ORB 100% | 2.5 | 0.4 | CONDITIONAL | +65.6 | -0.4 | 87.3% | 0.0% | 0.517 |
| **YM** | — | — | — | — | — | — | — | **NO-GO** | — | — | — | — | <0.03 |

---

## GC (Gold) — 2 STRONG legs, 1 additional STRONG gated variant

**Key finding from this sweep**: Asia session dominates NY for GC — the prior R3 NY longs config was beaten by Asia-1 on both DSR (0.652 vs not tested) and holdout stability. This is a major discovery since GC Asia was previously assumed "too thin."

### Asia-1 ungated — STRONG (top candidate)

| Param | Value |
|-------|-------|
| session | Asia (20:00-20:30 ORB, entry 20:30-23:15, flat 04:00) |
| stop | ORB 25% |
| rr | 2.5 |
| tp1_ratio | 0.6 |
| atr_length | 14 |
| direction | both |
| magnifier | 1s (required for GC) |
| gating | none |

Pre R: +167.0 | Calmar 11.71 | HO: +20.1R | PR 70.1% | HO PR 55.9% | PSR 1.000 | DSR **0.652**

### Asia-1 gated — STRONG

Same config with regime avoidance gate (skip bull_medium_vol + sideways_medium_vol).

Pre R: +131.9 | Calmar 9.59 | HO: +20.4R | PR 68.1% | HO PR **58.4%** | PSR 1.000 | DSR 0.508

### Asia-2 gated — STRONG

| Param | Value |
|-------|-------|
| session | Asia (20:00-20:15 ORB, entry 20:15-23:15, flat 04:00) |
| stop | ORB 75% |
| rr | 2.0 |
| tp1_ratio | 0.6 |
| direction | short only |
| gating | regime avoidance |

Pre R: +92.9 | Calmar 9.95 | HO: -1.1R | PR **77.2%** | HO PR 43.3% | DSR 0.522

Scripts: `run_gc_orb_discovery.py`, `run_gc_orb_discovery_pipeline.py`, `run_gc_orb_phase_one.py`

---

## RTY (Russell 2000) — 1 STRONG, 2 CONDITIONAL

### NY-4 — STRONG

| Param | Value |
|-------|-------|
| session | NY (09:30-09:40 ORB, entry 09:40-13:00, flat 15:50) |
| stop | ORB 100% |
| rr | 3.0 |
| tp1_ratio | 0.4 |
| atr_length | 14 |
| direction | both |
| magnifier | 1m |
| gating | none |

Pre R: +125.3 | Calmar 7.15 | HO: +1.2R | PR 62.7% | HO PR 47.0% | PSR 0.999 | DSR 0.419

### NY-1 — CONDITIONAL (highest DSR across all RTY)

Same session, ORB 75%, RR 3.5, TP1 0.6, both. Pre R: +182.3 | HO: +11.0R | DSR **0.590**

### NY-2 — CONDITIONAL (best holdout PR)

Same session, ORB 100%, RR 3.5, TP1 0.6, both. Pre R: +156.1 | HO: +8.8R | HO PR **52.2%** | DSR 0.527

Scripts: `run_rty_orb_discovery.py`, `run_rty_orb_discovery_pipeline.py`, `run_rty_orb_phase_one.py`

---

## ES (S&P 500) — 1 STRONG, 2 CONDITIONAL

### NY-A gated — STRONG

| Param | Value |
|-------|-------|
| session | NY (09:30-10:15 ORB, entry 10:15-12:00, flat 15:50) |
| stop | ATR 8% |
| rr | 3.5 |
| tp1_ratio | 0.3 |
| atr_length | 14 |
| direction | both |
| magnifier | off (no magnifier used in this sweep) |
| gating | regime avoidance |

Pre R: +71.3 | HO: +2.7R | PR 78.1% | HO PR 43.3% | PSR 0.999 | DSR 0.289

### Asia-A gated — CONDITIONAL

60m ORB, ORB 100% stop, RR 2.5, TP1 0.4, long, gated. Pre R: +65.6 | HO: -0.4R | PR **87.3%** | DSR 0.517

### LDN-B gated — CONDITIONAL

45m ORB, ATR 12% stop, RR 3.5, TP1 0.4, short, gated. Pre R: +40.0 | HO: -16.2R | DSR 0.029

Scripts: `run_es_orb_discovery_3session.py`, `run_es_orb_discovery_pipeline.py`

---

## NQ (Nasdaq-100) — 3 CONDITIONAL

### Asia-B gated — top candidate (best holdout)

| Param | Value |
|-------|-------|
| session | Asia (20:00-20:15 ORB, entry 20:15-23:15, flat 04:00) |
| stop | ORB 100% |
| rr | 3.5 |
| tp1_ratio | 0.6 |
| atr_length | 14 |
| direction | long only |
| magnifier | off (this sweep) / 1s available |
| gating | regime avoidance |

Pre R: +119.2 | HO: **+42.5R** | PR 57.1% | HO PR **76.7%** | PSR 1.000 | DSR 0.310

### Asia-A gated — CONDITIONAL

15m ORB, ATR 8%, RR 3.0, TP1 0.5, long, gated. Pre R: +102.4 | HO: +37.9R | HO PR 74.8% | DSR 0.233

### NY-B gated — CONDITIONAL

45m ORB, ORB 75%, RR 3.5, TP1 0.3, both, gated. Pre R: +62.6 | HO: +1.8R | PR 76.6% | DSR 0.209

Scripts: `run_nq_orb_discovery_3session.py`, `run_nq_orb_discovery_3session_magnifier.py`, `run_nq_orb_discovery_pipeline.py`, `run_nq_orb_phase_one.py`

---

## SI (Silver) — 3 CONDITIONAL

### Asia-1 — top candidate (highest DSR)

| Param | Value |
|-------|-------|
| session | Asia (20:00-20:30 ORB, entry 20:30-23:15, flat 04:00) |
| stop | ORB 75% |
| rr | 2.5 |
| tp1_ratio | 0.6 |
| atr_length | 14 |
| direction | short only |
| magnifier | 1m |
| gating | none |

Pre R: +122.7 | Calmar 10.08 | HO: +4.9R | PR 73.1% | DSR **0.507**

### Asia-4 — CONDITIONAL

30m ORB 75%, RR 3.0, TP1 0.5, short. HO: +6.8R | DSR 0.470

### Asia-3 — CONDITIONAL (best holdout)

30m ORB 75%, RR 3.0, TP1 0.6, short. HO: **+10.1R** | DSR 0.376

Scripts: `run_si_orb_discovery.py`, `run_si_orb_discovery_pipeline.py`, `run_si_orb_phase_one.py`

---

## CL (Crude Oil) — 3 CONDITIONAL

### LDN-1 — top candidate (best holdout R)

| Param | Value |
|-------|-------|
| session | LDN (03:00-03:30 ORB, entry 03:30-07:00, flat 08:20) |
| stop | ATR 8% |
| rr | 3.5 |
| tp1_ratio | 0.6 |
| atr_length | 14 |
| direction | long only |
| magnifier | 1m |
| gating | none |

Pre R: +123.1 | Calmar 6.93 | HO: **+12.8R** | PR 58.6% | HO PR 54.1% | DSR 0.186

### LDN-2 — CONDITIONAL (best DSR and holdout PR)

30m ATR 8%, RR 3.0, TP1 0.6, long. HO: +7.3R | HO PR **55.0%** | DSR **0.294**

### LDN-3 — CONDITIONAL

30m ATR 8%, RR 3.5, TP1 0.5, long. HO: +8.6R | HO PR 48.9% | DSR 0.243

Scripts: `run_cl_orb_discovery.py`, `run_cl_orb_discovery_pipeline.py`, `run_cl_orb_phase_one.py`

---

## YM (Dow Jones) — NO-GO

3,888 configs across NY, Asia, LDN. All DSR < 0.031. $5/point value is the structural bottleneck.

Scripts: `run_ym_orb_discovery.py`, `run_ym_orb_discovery_pipeline.py`, `run_ym_orb_phase_one.py`

---

## Cross-Asset Patterns

1. **Asia session produced the top candidates for GC, NQ, and SI** — all 3 have their best leg in Asia. Prior testing focused heavily on NY.
2. **Regime avoidance gating helped GC and ES** — improved holdout PR by 2-3% for GC Asia-1, and was required for ES NY-A STRONG verdict.
3. **ORB-range stops dominate** on RTY (100%), NQ (100%), GC (25%), SI (75%). ATR stops only win on CL (8%) and ES (8%).
4. **30m ORB for commodities, 10-15m for indices** — consistent pattern across all instruments.
5. **Both-direction configs won on RTY, ES, GC Asia-1** — not just longs. SI is the only short-only winner.
6. **DSR > 0.50 achieved by**: GC Asia-1 ungated (0.652), GC Asia-3 gated (0.563), RTY NY-1 (0.590), RTY NY-2 (0.527), GC Asia-2 gated (0.522), GC Asia-1 gated (0.508), SI Asia-1 (0.507), ES Asia-A (0.517).
7. **YM is the only full NO-GO** — $5/pt point value cannot support prop firm R generation.
