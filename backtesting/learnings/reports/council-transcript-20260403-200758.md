# Council Transcript: ALPHA_V1 & TESTING Config Audit

**Date:** 2026-04-03 20:07 ET
**Question:** Audit ALPHA_V1 and TESTING execution configs against backtested research configs for parameter mismatches.

---

## Framed Question

Two new execution configs (ALPHA_V1 live with webhook, TESTING dry-run) must exactly match backtested research configs. Compare every parameter field-by-field. Flag mismatches that would cause live execution to differ from validated backtest results.

---

## Advisor Responses

### 1. The Contrarian

Found NQ_Asia flat_end 04:10 vs research 04:00 as real drift. Questioned whether `block_full_medium_vol` is equivalent to blocking both `bull_medium_vol + sideways_medium_vol` — recommended immediate verification. Flagged ALPHA_V1 NQ_NY_LSI missing explicit `long_only` as implicit dependency risk. Ranked findings: (1) regime gate verification critical, (2) flat_end drift confirmed, (3) implicit long_only dependency.

**Post-review verification:** Gate is correct (gates.py:307-310 confirms both regimes blocked). long_only defaults to True at engine build time.

### 2. The First Principles Thinker

Confirmed merge architecture is field-level patch via `{**sess_cfg, **toml_overrides, **runtime_overrides, **exec_overrides}` — missing fields fall back to SESSION_CONFIGS defaults. Naming consistent: `min_stop_pts`/`min_tp1_pts` in both main.py and exec config. ES_Asia `stop_orb_pct=125` override redundant (main.py default already 125). Only real discrepancy: NQ_Asia flat_end 04:10 vs 04:00.

### 3. The Expansionist

ALPHA_V1's NQ_NY_LSI-RR3 runs ungated despite regime gate research showing +8.8R holdout improvement for LSI strategies. TESTING is the right proving ground for gates before retrofitting ALPHA_V1. GC dry-run at $200 banks live regime data for when Apex ban lifts. NQ_Asia has no gate research — bull_high_vol is the drag bucket. Single-account ALPHA_V1 config doesn't match separate-account ambition from docs.

### 4. The Outsider

Webhook URL in plaintext in git-tracked file — critical credential exposure. Missing explicit `long_only` on ES_Asia and ES_NY. TESTING's thin override pattern (3 fields on GC_Asia) is a silent drift risk. No version tracking in config JSON. Disabled configs still in file as re-enable risk.

### 5. The Executor

Deployment order: deploy.sh first (pushes main.py with GC_Asia defaults), then manual scp of exec_configs.json, then restart. flat_end 04:10 is a liquidation window (engine needs time to confirm flatten). Verification: curl status, check engine creation logs, watch for regime gate messages on TESTING, confirm no FAST_V2 engines.

---

## Peer Reviews

**Anonymization mapping:** A=Contrarian, B=First Principles, C=Expansionist, D=Outsider, E=Executor

### Reviewer 1
- Strongest: B (First Principles) — correctly identified merge semantics as foundational
- Biggest blind spot: E (Executor) — answered deployment question instead of auditing
- All missed: Engine hard constraints (5% ATR floor, TP1>=1R) not checked against configs

### Reviewer 2
- Strongest: D (Outsider) — only production-critical finding (webhook URL)
- Biggest blind spot: A, B, D — none verified params at value level
- All missed: Hard constraints not verified against config values

### Reviewer 3
- Strongest: B (First Principles) — focused on actual diff, no noise
- Biggest blind spot: D (Outsider) — buried security finding in equal-weight list
- All missed: Data universe consistency between backtest and live instrument specs

### Reviewer 4
- Strongest: D (Outsider) — identifies systemic risks with real consequences
- Biggest blind spot: long_only inheritance for GC_Asia not traced to resolution
- All missed: bear_medium_vol not blocked by block_full_medium_vol (note: this is by design per research)

### Reviewer 5
- Strongest: D (Outsider) — structural reliability audit
- Biggest blind spot: C (Expansionist) — contributed no critique
- All missed: long_only enforcement path from config to signal filter

---

## Chairman's Synthesis

### Where the Council Agrees
- Merge architecture sound, field names consistent, gate logic correct
- long_only resolves correctly everywhere
- One real mismatch: NQ_Asia flat_end 04:10 vs 04:00

### Where the Council Clashes
- flat_end 04:10 interpretation (deliberate buffer vs unvalidated drift)
- Webhook URL security (Outsider flagged, others silent)

### Blind Spots Caught
- Engine hard constraints not verified against config values
- ES_Asia stop_orb_pct override redundant

### Recommendation
1. Fix NQ_Asia flat_end (04:00 or document 04:10)
2. Rotate webhook URL out of git
3. Document or remove redundant ES_Asia override
4. Verify hard constraint margins
5. Plan regime gate for ALPHA_V1 NQ_NY_LSI after TESTING validates

### The One Thing to Do First
Decide whether NQ_Asia flat_end is 04:00 or 04:10, and make the config match that decision.
