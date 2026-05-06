# HOT_REGIME_V1 NQ+ES Phase 1 Payout Risk Sweep

- Run slug: `hot_regime_v1_nq_es_phase1_payout_risk_20260505`
- Exact/live-engine window: `2025-03-24` to `2026-03-24`
- Scope: NQ and ES combinations from the constrained HOT_REGIME_V1 portfolio search.
- Account model: 50k account, 2k EOD trailing drawdown, first payout at 52.5k, $500 payout, $100 reset/account cost, account starts every 14 days.
- Risk sizing only changes USD risk per leg. Strategy logic, exact replay, and live overlap hooks remain unchanged.

## Headline

- Fastest guarded: `current_nq_es_all6` with `{"ES_Asia": 100, "ES_NY": 700, "ES_NY_LSI": 700, "NQ_Asia": 700, "NQ_NY": 700, "NQ_NY_LSI": 700}`.
  Result: 14/27 payouts, 12 breaches, avg 2.5 days, EV $159.26 per attempt.
- Best payout/breach guarded: `combo_all_cleaner_core5` with `{"ES_Asia": 300, "ES_NY": 300, "NQ_Asia": 450, "NQ_NY": 400, "NQ_NY_LSI": 450}`.
  Result: 25/27 payouts, 0 breaches, ratio inf, EV $362.96 per attempt.
- Best balanced score: `combo_all_cleaner_core5` with `{"ES_Asia": 300, "ES_NY": 300, "NQ_Asia": 450, "NQ_NY": 400, "NQ_NY_LSI": 450}`.

## Global Bests

| bucket | portfolio | payouts | breaches | open | payout_rate_pct | breach_rate_pct | payout_breach_ratio | ev_per_account_usd | avg_days_to_payout | max_consecutive_breaches | risk_map_json |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fastest_guarded | current_nq_es_all6 | 14 | 12 | 1 | 51.9 | 44.4 | 1.17 | 159 | 2.50 | 5 | {"ES_Asia": 100, "ES_NY": 700, "ES_NY_LSI": 700, "NQ_Asia": 700, "NQ_NY": 700, "NQ_NY_LSI": 700} |
| best_ratio_guarded | combo_all_cleaner_core5 | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 15.5 | 0 | {"ES_Asia": 300, "ES_NY": 300, "NQ_Asia": 450, "NQ_NY": 400, "NQ_NY_LSI": 450} |
| best_balanced_score | combo_all_cleaner_core5 | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 15.5 | 0 | {"ES_Asia": 300, "ES_NY": 300, "NQ_Asia": 450, "NQ_NY": 400, "NQ_NY_LSI": 450} |
| best_speed_score | current_nq_es_all6 | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 21.5 | 0 | {"ES_Asia": 0, "ES_NY": 175, "ES_NY_LSI": 0, "NQ_Asia": 350, "NQ_NY": 75, "NQ_NY_LSI": 450} |
| best_ratio_score | combo_all_cleaner_core5 | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 15.5 | 0 | {"ES_Asia": 300, "ES_NY": 300, "NQ_Asia": 450, "NQ_NY": 400, "NQ_NY_LSI": 450} |

## Per Portfolio Bests

| portfolio | bucket | payouts | breaches | open | payout_rate_pct | breach_rate_pct | payout_breach_ratio | ev_per_account_usd | avg_days_to_payout | max_consecutive_breaches | risk_map_json |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_nq_es_all6 | fastest_guarded | 14 | 12 | 1 | 51.9 | 44.4 | 1.17 | 159 | 2.50 | 5 | {"ES_Asia": 100, "ES_NY": 700, "ES_NY_LSI": 700, "NQ_Asia": 700, "NQ_NY": 700, "NQ_NY_LSI": 700} |
| current_nq_es_all6 | best_ratio_guarded | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 21.5 | 0 | {"ES_Asia": 0, "ES_NY": 175, "ES_NY_LSI": 0, "NQ_Asia": 350, "NQ_NY": 75, "NQ_NY_LSI": 450} |
| current_nq_es_all6 | best_balanced_score | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 21.5 | 0 | {"ES_Asia": 0, "ES_NY": 175, "ES_NY_LSI": 0, "NQ_Asia": 350, "NQ_NY": 75, "NQ_NY_LSI": 450} |
| constrained_no_nq_orb_no_es_lsi | fastest_guarded | 16 | 9 | 2 | 59.3 | 33.3 | 1.78 | 196 | 3.60 | 3 | {"ES_Asia": 700, "ES_NY": 700, "NQ_Asia": 700, "NQ_NY_LSI": 75} |
| constrained_no_nq_orb_no_es_lsi | best_ratio_guarded | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 25.6 | 0 | {"ES_Asia": 50, "ES_NY": 300, "NQ_Asia": 250, "NQ_NY_LSI": 600} |
| constrained_no_nq_orb_no_es_lsi | best_balanced_score | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 25.6 | 0 | {"ES_Asia": 50, "ES_NY": 300, "NQ_Asia": 250, "NQ_NY_LSI": 600} |
| combo_all_cleaner_core5 | fastest_guarded | 16 | 10 | 1 | 59.3 | 37.0 | 1.60 | 196 | 3.00 | 3 | {"ES_Asia": 700, "ES_NY": 700, "NQ_Asia": 700, "NQ_NY": 700, "NQ_NY_LSI": 700} |
| combo_all_cleaner_core5 | best_ratio_guarded | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 15.5 | 0 | {"ES_Asia": 300, "ES_NY": 300, "NQ_Asia": 450, "NQ_NY": 400, "NQ_NY_LSI": 450} |
| combo_all_cleaner_core5 | best_balanced_score | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 15.5 | 0 | {"ES_Asia": 300, "ES_NY": 300, "NQ_Asia": 450, "NQ_NY": 400, "NQ_NY_LSI": 450} |
| alt_es_ny_lowdd_rr2_tp075 | fastest_guarded | 15 | 11 | 1 | 55.6 | 40.7 | 1.36 | 178 | 3.10 | 5 | {"ES_Asia": 700, "ES_NY": 700, "NQ_Asia": 700, "NQ_NY": 700, "NQ_NY_LSI": 700} |
| alt_es_ny_lowdd_rr2_tp075 | best_ratio_guarded | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 20.8 | 0 | {"ES_Asia": 200, "ES_NY": 400, "NQ_Asia": 300, "NQ_NY": 300, "NQ_NY_LSI": 300} |
| alt_es_ny_lowdd_rr2_tp075 | best_balanced_score | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 23.9 | 0 | {"ES_Asia": 175, "ES_NY": 450, "NQ_Asia": 250, "NQ_NY": 350, "NQ_NY_LSI": 200} |
| constrained_nq_es_all6 | fastest_guarded | 15 | 10 | 2 | 55.6 | 37.0 | 1.50 | 178 | 2.70 | 5 | {"ES_Asia": 700, "ES_NY": 700, "ES_NY_LSI": 250, "NQ_Asia": 700, "NQ_NY": 700, "NQ_NY_LSI": 250} |
| constrained_nq_es_all6 | best_ratio_guarded | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 19.3 | 0 | {"ES_Asia": 250, "ES_NY": 300, "ES_NY_LSI": 350, "NQ_Asia": 200, "NQ_NY": 350, "NQ_NY_LSI": 300} |
| constrained_nq_es_all6 | best_balanced_score | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 19.3 | 0 | {"ES_Asia": 250, "ES_NY": 300, "ES_NY_LSI": 350, "NQ_Asia": 200, "NQ_NY": 350, "NQ_NY_LSI": 300} |
| constrained_nq_es_no_es_lsi | fastest_guarded | 15 | 11 | 1 | 55.6 | 40.7 | 1.36 | 178 | 3.00 | 5 | {"ES_Asia": 700, "ES_NY": 700, "NQ_Asia": 700, "NQ_NY": 700, "NQ_NY_LSI": 700} |
| constrained_nq_es_no_es_lsi | best_ratio_guarded | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 21.2 | 0 | {"ES_Asia": 250, "ES_NY": 300, "NQ_Asia": 150, "NQ_NY": 350, "NQ_NY_LSI": 350} |
| constrained_nq_es_no_es_lsi | best_balanced_score | 25 | 0 | 2 | 92.6 | 0.00 | inf | 363 | 21.2 | 0 | {"ES_Asia": 250, "ES_NY": 300, "NQ_Asia": 150, "NQ_NY": 350, "NQ_NY_LSI": 350} |

## Notes

- This is intentionally recent-window Phase 1 sizing, not a 10-year robustness verdict.
- Infinite payout/breach ratio means the tested account starts had payouts and zero breaches in this exact window.
- The best ratio rows can be slower/lower-capacity than the fastest rows; the balanced row is the practical compromise bucket.
